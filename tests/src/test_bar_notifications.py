# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Mitteilungen: das Zentrum, "Nicht stoeren" und die Glocke.

WAS GEMELDET WURDE, sinngemaess am 12.08.2026
    ags-notifications.template war ein Einblendstapel und sonst nichts.
    Was man verpasst, war weg; einen Verlauf gab es nicht, "Nicht
    stoeren" gab es nicht.

    Das ist die einzige Stelle dieses Systems, an der eine Auskunft
    ENDGUELTIG weggeworfen wird: nach fuenf Sekunden ist die Karte fort,
    und es gibt keinen zweiten Ort, an dem sie stand.

WAS HIER GEMESSEN WIRD, IN ZWEI TEILEN
    AUSGEFUEHRT   das Glockenmodul der Leiste, auf einer echten
                  GTK4-Anzeige, in vier Zustaenden. Ob es sich zeigt,
                  wann es sich zeigt und ob es wieder verschwindet.
    GELESEN       die Zusagen der Vorlage, die sich nicht ausfuehren
                  lassen, ohne einen Benachrichtigungsdienst am
                  D-Bus-Sitzungsbus anzumelden - und das waere auf
                  dieser Maschine der Dienst des angemeldeten Nutzers.

DIE MESSUNG, DIE DEN AUFBAU BESTIMMT HAT
    /usr/share/gir-1.0/AstalNotifd-0.1.gir, Eigenschaft dont-disturb:
    "Tells frontends not to show popups to the user. This property does
    not have any effect on its own; it is merely a value shared between
    the daemon process and proxies."

    "Nicht stoeren" schaltet also NICHTS ab. Es ist eine Fahne, und wer
    sie nicht liest, blendet weiter ein. Deshalb ist die Zusicherung
    darauf, dass die Vorlage sie liest, keine Kosmetik: ohne sie waere
    der Schalter im Zentrum ein Bedienelement ohne Wirkung, und zwar
    eines, dessen Wirkungslosigkeit man erst merkt, wenn man gestoert
    wird.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.gtk4_headless import broadwayd, start_broadwayd, stop_broadwayd
from tests.src.test_bar_headless import (
    CHILD_TIMEOUT, _DISPLAYS, _bundle, _stub_scripts)

pytestmark = pytest.mark.allow_subprocess

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
NOTIFICATIONS = SRC / "templates" / "ags-notifications.template"
APP = SRC / "templates" / "ags-config.template"
BAR = SRC / "templates" / "ags-bar.template"
CHILD = Path(__file__).resolve().parent / "notification_bar_child.tsx"


def _code(path: Path) -> str:
    """Die Datei ohne ihre Kommentare - BEIDE Sorten.

    Jede Datei in diesem Baum ERKLAERT, was sie nicht mehr tut. Eine
    Suche nach "new Astal.Window" wuerde von der Erklaerung wahr, in der
    steht, warum es eines gibt.

    Die Blockkommentare stehen hier neben den Zeilenkommentaren, und das
    ist ein Befund dieser Datei: der Kopf von NotificationView in
    ags-bar.template ist ein /** ... */ und nennt darin den Import,
    den es gerade NICHT mehr gibt ("er war der erste Versuch - er ist
    gemessen falsch"). Ein Filter, der nur `//` kennt, hielte diese
    Erklaerung fuer den Import selbst.
    """
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("//"))


# --------------------------------------------------------------------
# Die Glocke, ausgefuehrt
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def marks(tmp_path_factory) -> dict[str, tuple[str, str, str]]:
    """Vier Zustaende, gemessen an der echten Leiste unter GTK4.

    Modulweit: `ags bundle` braucht ueber eine Sekunde, und alle Tests
    darunter lesen dieselbe Spur.
    """
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    root = tmp_path_factory.mktemp("bell")
    bundle, _ = _bundle(CHILD, tmp_path_factory.mktemp("bell-bundle"))

    runtime = root / "run"
    runtime.mkdir()
    # GLib lehnt ein weltlesbares XDG_RUNTIME_DIR ab und sagt es auf stderr.
    runtime.chmod(0o700)

    config = root / "config"
    _stub_scripts(config / "ags" / "scripts")

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    try:
        result = subprocess.run(
            [str(bundle)],
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(root),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(config),
                # Kein Sitzungsbus. Dieselbe Zeile und derselbe Grund wie
                # in test_bar_headless.py: das Kind darf den Bus des
                # angemeldeten Nutzers nicht finden.
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={root}/kein-bus",
                "ZEPOS_TRACE": str(trace),
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(server)

    assert result.returncode == 0, (
        f"das Kind endete mit {result.returncode}:\n{result.stderr}")
    assert trace.is_file(), f"keine Spur geschrieben:\n{result.stderr}"

    found = {}
    for line in trace.read_text(encoding="utf-8").splitlines():
        label, state, text, classes = line.split(":", 3)
        found[label] = (state, text, classes)
    assert set(found) == {"ruhe", "ungesehen", "dnd", "zurueck"}, found
    return found


def test_a_quiet_session_has_no_bell(marks) -> None:
    """Der wichtigste Zustand: nichts an, nichts gesehen, nichts da.

    Die Leiste trug am 12.08.2026 achtzehn Module und lief auf 1366x768
    bei jeder Schriftgroesse ueber. Ein neunzehntes, das IMMER dasteht,
    macht das schlimmer; ein bedingtes nicht - ein unsichtbares Widget
    beantwortet gtk_widget_measure mit 0.
    """
    state, text, _classes = marks["ruhe"]
    assert state == "verborgen", (
        f"die Glocke steht auf einer ruhigen Sitzung da (Text {text!r})")


def test_what_was_missed_is_counted_on_the_bar(marks) -> None:
    """Drei Meldungen, seit das Zentrum zuletzt offen war."""
    state, text, classes = marks["ungesehen"]
    assert state == "sichtbar", f"die Glocke bleibt verborgen: {marks}"
    assert "3" in text, f"die Anzahl fehlt: {text!r}"
    assert "notifications-unseen" in classes, classes


def test_do_not_disturb_is_never_silent_about_itself(marks) -> None:
    """Ein Rechner, der heimlich nichts mehr einblendet, ist genau der
    Fehler, den Spec §7.4 fuer den schlimmsten haelt: nichts meldet ihn
    ausser dem Nutzer, dem etwas entgangen ist.

    Der Zaehler steht in diesem Zustand auf null - die Glocke ist also
    NICHT deshalb da, weil etwas anliegt, sondern weil der Schalter an
    ist.
    """
    state, text, classes = marks["dnd"]
    assert state == "sichtbar", (
        f"'Nicht stoeren' ist an und die Leiste sagt nichts: {marks}")
    assert "notifications-dnd" in classes, classes
    assert text.strip() != "", "die Glocke ist sichtbar und leer"


def test_the_bell_goes_away_again(marks) -> None:
    """Ein Modul, das einmal aufgegangen ist und nicht mehr
    verschwindet, ist kein bedingtes Modul, sondern ein verzoegertes.

    Die Klassen gehen MIT: ein verborgenes Widget, das noch
    `notifications-dnd` traegt, behauptet einen Zustand, der vorbei ist -
    und beim naechsten Aufgehen faerbte die alte Klasse den neuen
    Zustand, bis die richtige Zeile laeuft. GEMESSEN am 12.08.2026 im
    ersten Lauf dieser Datei, wo genau das der Fall war.
    """
    state, text, classes = marks["zurueck"]
    assert state == "verborgen", (
        f"die Glocke bleibt stehen, nachdem alles wieder ruhig ist "
        f"(Text {text!r})")
    assert "notifications-dnd" not in classes, (
        f"die Klasse des vorigen Zustands klebt am verborgenen Modul: "
        f"{classes}")


def test_the_two_states_do_not_look_the_same(marks) -> None:
    """Sonst waere die Glocke ein Lichtlein und keine Auskunft."""
    assert marks["dnd"][1] != marks["ungesehen"][1], (
        "'Nicht stoeren' und 'es liegt etwas an' zeigen dasselbe Zeichen")


# --------------------------------------------------------------------
# Das Zentrum, gelesen
# --------------------------------------------------------------------

def test_the_centre_comes_from_the_overlay_factory() -> None:
    """Es ist ein Aufklappfenster wie der Kalender - und kein zwoelftes
    selbstgebautes.

    createOverlayWindow() bringt Kopf, Schliesskreuz, ESC, die Lage am
    Zeiger, den Deckel aus MEASURE_MODAL_SHARE und die Bildlaufleiste
    mit. Ein Verlauf ohne Bildlaufleiste waere bei fuenfzig Karten ein
    Fenster, dessen unteres Ende unter dem Bildrand liegt - genau der
    Befund, den tests/src/test_overlay_windows.py am 12.08.2026 fuer das
    Kontrollzentrum festhaelt.
    """
    code = _code(NOTIFICATIONS)
    assert "createOverlayWindow({" in code, (
        "das Meldungszentrum baut sein Fenster wieder selbst")
    assert 'name: "notification-center"' in code, (
        "das Zentrum meldet sich unter keinem eigenen Namensraum an - "
        "eine layerrule auf einen Namensraum, den niemand anmeldet, "
        "greift lautlos nie")


def test_the_popup_stack_is_the_only_hand_built_window() -> None:
    """Die eine Flaeche, die NICHT aus der Fabrik kommen darf.

    Eine Einblendung mit Keymode ON_DEMAND naehme den Tastaturfokus -
    eine Meldung, die waehrend des Tippens hereinkommt, naehme dem
    Nutzer die Tastatur weg. Sie steht deshalb auf Keymode.NONE und an
    einer festen Ecke.

    Gezaehlt wird, damit aus dieser einen Ausnahme keine zweite wird.
    """
    code = _code(NOTIFICATIONS)
    assert code.count("new Astal.Window(") == 1, (
        "es gibt mehr als ein selbstgebautes Fenster in dieser Datei")
    assert "keymode: Astal.Keymode.NONE" in code, (
        "der Einblendstapel nimmt den Tastaturfokus")


def test_do_not_disturb_is_honoured_by_this_file() -> None:
    """Die Fahne schaltet nichts ab - sie muss gelesen werden.

    GEMESSEN in AstalNotifd-0.1.gir: "This property does not have any
    effect on its own; it is merely a value shared between the daemon
    process and proxies."
    """
    code = _code(NOTIFICATIONS)
    assert "dont_disturb" in code, (
        "die Datei kennt 'Nicht stoeren' nicht - der Schalter im Zentrum "
        "waere ein Bedienelement ohne Wirkung")
    assert re.search(r"if \(\w+\.dont_disturb\) \{", code), (
        "die Fahne wird gesetzt, aber beim Eintreffen einer Meldung "
        "nicht gelesen")


def test_do_not_disturb_still_writes_the_history() -> None:
    """"Nicht stoeren" heisst "unterbrich mich nicht", nicht "wirf es
    weg".

    Der Verlauf wird VOR der Fahne geschrieben. Andersherum waere der
    Schalter ein Loeschknopf mit einem freundlichen Namen - und das
    Zentrum, das ihn traegt, waere dann leer, gerade weil man ihn
    benutzt hat.
    """
    code = _code(NOTIFICATIONS)
    remembered = code.index("remember(id, notification")
    suppressed = code.index("dont_disturb) {")
    assert remembered < suppressed, (
        "die Meldung wird unterdrueckt, bevor sie im Verlauf steht")


def test_a_replaced_notification_does_not_fill_the_history() -> None:
    """Das zweite Signalargument, das diese Datei bis zum 12.08.2026
    nicht gelesen hat.

    GEMESSEN in AstalNotifd-0.1.gir: das Signal "notified" traegt
    `<parameter name="replaced"><type name="gboolean"/>`. Ein
    Kopiervorgang, der seinen Fortschritt in EINE Meldung schreibt,
    haette den Verlauf sonst hundertmal mit demselben Text gefuellt und
    den Zaehler auf hundert gestellt.
    """
    code = _code(NOTIFICATIONS)
    assert "replaced: boolean" in code, (
        "der Handler nimmt das zweite Signalargument nicht entgegen")
    assert "remember(id, notification, replaced)" in code, (
        "der Verlauf erfaehrt nicht, ob die Meldung eine ersetzte war")


def test_the_history_has_a_ceiling() -> None:
    """Eine Liste ohne Grenze im Speicher eines Prozesses, der wochenlang
    laeuft, ist ein Leck mit gutem Grund."""
    code = _code(NOTIFICATIONS)
    found = re.search(r"const HISTORY_MAX = (\d+)", code)
    assert found, "der Verlauf waechst ohne Grenze"
    assert 0 < int(found.group(1)) <= 200, found.group(1)
    assert "history.pop()" in code, (
        "die Grenze steht da und wird nicht angewendet")


def test_the_centre_offers_only_things_that_do_something() -> None:
    """Spec §7.4 an einem Fenster mit drei Bedienelementen.

    Der Schalter setzt dont_disturb, der Loeschknopf leert den Verlauf,
    das Kreuz an jeder Karte entfernt genau sie. Nichts davon ist eine
    Ansicht.
    """
    code = _code(NOTIFICATIONS)
    assert "history.length = 0" in code, "der Loeschknopf loescht nichts"
    assert "history.splice(index, 1)" in code, (
        "das Kreuz an einer Karte des Verlaufs entfernt sie nicht")


# --------------------------------------------------------------------
# Die Verdrahtung
# --------------------------------------------------------------------

def test_the_bar_gets_its_notifications_handed_in() -> None:
    """Die Leiste importiert den Melder NICHT.

    Ein Import zoege AstalNotifd in tests/src/bar_headless_child.tsx,
    und dessen get_default() meldet sich am D-Bus-Sitzungsbus an - auf
    einer Maschine, auf der jemand arbeitet, an seinem. Der Kopf jenes
    Kindes fuehrt genau das als Grund an, `ags run` nicht zu benutzen.
    """
    bar = _code(BAR)
    assert 'from "./Notifications"' not in bar, (
        "die Leiste importiert wieder das Melder-Widget")
    assert "notifications: NotificationView" in bar, (
        "die Leiste bekommt den Melder nicht mehr hereingereicht")


def test_the_app_wires_the_centre_and_the_hub() -> None:
    """Und app.ts reicht ihn wirklich herein.

    Eine Schnittstelle, die niemand bedient, ist ein Modul, das immer
    schweigt - und das saehe genauso aus wie eine ruhige Sitzung.
    """
    app = _code(APP)
    assert "Bar(toggleByName, notificationHub)" in app, (
        "die Leiste bekommt keinen Melder")
    assert "widgets.notifications = NotificationCenter()" in app, (
        "das Zentrum wird nicht gebaut - der Klick auf die Uhr und der "
        "auf die Glocke gingen ins Leere")
    assert 'reqStr.includes("notifications")' in app, (
        "es gibt keinen Weg von aussen zum Zentrum")


def test_the_clock_opens_the_centre() -> None:
    """Der Eingang, der nichts kostet.

    `custom/clocks` war am 12.08.2026 das einzige Modul der Leiste ohne
    jede Handlung. Das Datum daneben oeffnet weiterhin den Kalender:
    zwei Zeitmodule, zwei Fenster - was WANN ist, und was WAR.
    """
    bar = _code(BAR)
    clocks = bar.index('case "custom/clocks"')
    weather = bar.index('case "custom/weather"')
    branch = bar[clocks:weather] if weather > clocks else bar[clocks:clocks + 400]
    assert 'toggles: "notifications"' in branch, (
        "ein Klick auf die Uhr oeffnet das Meldungszentrum nicht")


def test_the_centre_is_a_glass_surface() -> None:
    """Eine Flaeche ohne Eintrag bekommt keine Unschaerfe, und niemand
    merkt es - sie sieht dann aus wie vorher.

    Die Regel schreibt src/style_definition.py aus GLASS_LAYERS; ohne
    Namen darin gibt es keine layerrule fuer diesen Namensraum.
    """
    import sys
    sys.path.insert(0, str(SRC))
    try:
        import style_definition as style
    finally:
        sys.path.remove(str(SRC))

    assert "notification-center" in style.GLASS_LAYERS, (
        "das Zentrum steht nicht in GLASS_LAYERS")
    assert "notification-center" in style.GLASS_PLATES, (
        "es steht nicht in GLASS_PLATES, also kann keine Pruefung "
        "nachsehen, wo es sich malt")
    assert style.GLASS_PLATES["notification-center"].selector == ".overlay-outer", (
        "das Zentrum malt sich woanders als die anderen "
        "Aufklappfenster - dann ist es keines")
