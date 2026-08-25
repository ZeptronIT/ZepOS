# SPDX-License-Identifier: GPL-3.0-or-later
"""Die VPN-Einstellungen, gezeichnet - und der Ueberhang nachgemessen.

WORAUF DIESE DATEI ANTWORTET
    aufgabe-34-report.md, Abschnitt 2.6 (18.08.2026), und
    aufgabe-43-report.md, Punkt 2: das Einstellungsfenster des VPN steht
    42 Punkte ueber seiner Sprosse.

        .vpn-settings-actions, gemessen              626
        Container-Polster, zweimal                   +50
                                                    ----
        .vpn-settings-container verlangt             676
        Rahmen 1px, zweimal                           +2
        senkrechte Bildlaufleiste                    +24
                                                    ----
        Inhalt braucht                               702
        Sprosse M                                     660
        UEBERHANG                                      42

    Was das auf dem Schirm heisst, steht im Kopf von
    ags-vpn-settings.template: das Sichtfenster rollt waagerecht, und
    der Inhalt wird LINKS abgeschnitten - der erste Reiter las sich
    "in" statt "Allgemein".

    Unbehoben blieb es, weil beide Auswege "ein Fenster sichtbar
    veraendern, ueber das niemand geklagt hat". Mit der zweiten Bauart
    (21.08.2026) veraendert es sich ohnehin, und es steht seither auf
    Sprosse L.

WORAN GEMESSEN WIRD, UND WARUM NICHT AN BILDPUNKTEN
    An `hadj.get_upper()` der Fabrik - der BREITE, DIE DER INHALT
    BEKOMMT. Die Fabrik (ags-overlay-utils.template) misst sie ohnehin
    schon; sie nennt sie seit dem 21.08.2026 in ihrer Meldung, statt nur
    den Fehlbetrag.

    ZWEI ANLAEUFE, DIE NICHT TAUGTEN, und warum diese Datei so
    aussieht, wie sie aussieht - beide GEMESSEN am 21.08.2026:

      * Die Layer-Shell-Flaeche an hyprctl. Sie erscheint in einem Teil
        der Laeufe GAR NICHT (derselbe Befund, den der Kopf von
        test_schale_stil.py fuer die Schale beschreibt: "die Flaeche
        bleibt laenger als 20 Sekunden komplett aus"), und wenn sie
        erscheint, hat sie eine Weile noch nicht ihre Endgroesse - eine
        Messung ergab 200 Punkte fuer ein Fenster, das 880 breit ist.

      * Der blosse Fehlbetrag aus der Fabrikmeldung. Er lautete "237px
        breiter als das Fenster erlaubt" - und die beiden Zahlen
        dahinter waren `Inhalt 676 / Sichtfenster 439`. Das Sichtfenster
        war also die halbe Sprosse: die Meldung stammt aus der ERSTEN
        Zuteilung, bevor die Flaeche ihre Groesse hat. Ein Test darauf
        haette einen Zustand geprueft, den niemand zu sehen bekommt.

    `upper` hat diese Schwaeche nicht. Es ist die Breite, die das Kind
    der Bildlauf-Flaeche bekommt, also `max(natuerliche Breite,
    Sichtfenster)`:

      * Ist das Sichtfenster kleiner (waehrend der ersten Zuteilung),
        steht dort die NATUERLICHE Breite des Inhalts - 676.
      * Ist es groesser (im Ruhezustand), steht dort das Sichtfenster,
        und das ist per Definition nicht zu breit.

    In beiden Faellen gilt dieselbe Aussage: passt `upper` in das, was
    die Sprosse uebriglaesst, dann gibt es keinen Ueberhang. Der Test
    haelt deshalb JEDE gemeldete Messung gegen diese Schranke und nicht
    nur die letzte - er haengt damit an keinem Zeitpunkt.

DER PREIS
    Ein verschachtelter Compositor, rund eine halbe Minute. Die Sitzung
    ist verschachtelt und beruehrt die Hyprland-Instanz des Nutzers
    nicht.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render.desktop_session import (             # noqa: E402
    Session, bundle, render_configuration, required_tools, workspaces_file,
)

SETTLE = 6.0
NAMESPACE = "vpn-settings"

# Was die Fabrik dem Inhalt von der Sprosse abzieht, bevor er anfangen
# darf. Beide Zahlen stehen so schon in der Rechnung von
# aufgabe-34-report.md 2.6 und im Kopf von ags-vpn-settings.template:
#
#     .overlay-outer, Rahmen 1px, zweimal            2
#     senkrechte Bildlaufleiste (immer reserviert)  24
RAHMEN_UND_LEISTE = 26

# `Inhalt <n>px, Sichtfenster <m>px` - die Meldung aus
# ags-overlay-utils.template. Sie wird nur geschrieben, WENN etwas nicht
# passt; keine Meldung ist also der gute Fall, und dieser Ausdruck fischt
# die Zahlen aus den Meldungen, die es doch gibt.
MELDUNG = re.compile(
    r'Ueberlagerung "([^"]+)": Inhalt (\d+)px, Sichtfenster (\d+)px')


def _modal_width_l() -> int:
    """Die Sprosse aus DERSELBEN Quelle, aus der die Vorlage sie bekommt.

    Nicht abgeschrieben - dieselbe Begruendung wie _modal_width_l() in
    test_schale_stil.py: eine abgeschriebene Erwartung misst die
    Abschrift und nicht das Erzeugte.
    """
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import sizes
        return sizes.MODAL_WIDTH("L")
    finally:
        sys.path.remove(str(ROOT / "src"))


def _shipped_settings() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import settings
        return json.dumps(settings.defaults(), indent=2)
    finally:
        sys.path.remove(str(ROOT / "src"))


@pytest.fixture(scope="module")
def protokoll(tmp_path_factory) -> str:
    """Das Fenster einmal geoeffnet, und was die Schale dabei gemeldet hat."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zepvpn-bau")
    ags = render_configuration(bau)
    bundle(ags, bau)

    # Eine echte Einstellungsdatei. Ohne sie meldet das Fenster beim
    # Oeffnen einen Lesefehler und baut aus seinen Vorgaben weiter - das
    # ist richtig so, aber ein Test soll den Normalfall messen und nicht
    # den Notfall.
    (bau / "zepos").mkdir(parents=True, exist_ok=True)
    (bau / "zepos" / "user-settings.json").write_text(_shipped_settings(),
                                                     encoding="utf-8")

    with Session(1920, 1080) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        sitzung.wallpaper()
        sitzung.shell(bau / "zepos-shell.js", bau)
        time.sleep(SETTLE)

        antwort = sitzung.request(NAMESPACE)
        assert "toggled" in antwort, (
            f"ags request {NAMESPACE} antwortete {antwort!r}")
        # Zeit fuer die Zuteilung. Nicht auf die Flaeche gewartet - siehe
        # den Dateikopf: sie erscheint in einem Teil der Laeufe nicht,
        # die Messung der Fabrik aber immer.
        time.sleep(6.0)
        return sitzung.read_shell_log()


def test_die_schale_hat_das_fenster_ueberhaupt_gebaut(protokoll):
    """Die Gegenprobe zuerst.

    Der Test darunter ist erfuellt, wenn GAR NICHTS gemeldet wurde - und
    gar nichts wird auch gemeldet, wenn das Fenster nie gebaut wurde.
    Ohne diese Zeile misst er im Zweifel eine Schale, die abgestuerzt
    ist, und meldet Erfolg.

    Auf "loaded successfully" und nicht auf eine Messzeile: die Fabrik
    meldet NUR, wenn etwas nicht passt, und im guten Fall soll sie
    schweigen duerfen. Eine Zusicherung, dass gemessen wurde, wuerde
    genau dann scheitern, wenn GTK gleich beim ersten Anlauf richtig
    zuteilt - also in der besseren Welt.

    GEMESSEN am 21.08.2026 hat sie in diesem Aufbau trotzdem gesprochen,
    aus der ersten Zuteilung heraus: `Inhalt 676px, Sichtfenster 439px`.
    Der Test unten hat damit eine echte Zahl in der Hand gehabt, keine
    leere Liste - 676 gegen 854 erlaubte.
    """
    assert "VpnSettings loaded successfully" in protokoll, (
        "im Protokoll der Schale kommt das Fenster nicht vor - gemessen "
        f"wurde vermutlich gar nichts:\n{protokoll[-2000:]}")


def test_der_ueberhang_ist_null(protokoll):
    """Der Inhalt passt in das, was Sprosse L uebriglaesst.

    880 - 2 (Rahmen) - 24 (Bildlaufleiste) = 854, und der Inhalt dieses
    Fensters verlangt 676 (GEMESSEN am 21.08.2026 an `hadj.get_upper()`,
    dieselbe Zahl wie in aufgabe-34-report.md 2.6). Auf Sprosse M
    standen dem Inhalt 634 zur Verfuegung - daher die 42 Punkte, die
    dieser Test ablegt.
    """
    erlaubt = _modal_width_l() - RAHMEN_UND_LEISTE

    zu_breit = [(int(inhalt), int(sicht))
                for name, inhalt, sicht in MELDUNG.findall(protokoll)
                if name == NAMESPACE and int(inhalt) > erlaubt]

    assert zu_breit == [], (
        f"der Inhalt von '{NAMESPACE}' verlangt mehr als die {erlaubt}px, "
        f"die Sprosse L ({_modal_width_l()}px) uebriglaesst: {zu_breit}. "
        f"Entweder gehoert das Fenster auf eine breitere Sprosse, oder "
        f"seine Fusszeile muss schmaler werden - siehe die Rechnung im "
        f"Kopf von src/templates/ags-vpn-settings.template.")
