# SPDX-License-Identifier: GPL-3.0-or-later
"""Was ein Rechtsklick auf dem Fuss anbietet - und was er tut.

WAS GEMELDET WURDE
    Der Nutzer am 20.08.2026, woertlich: "rechtsklick funktioniert nicht
    bei hyprlaunch. kann ich rechtsklick auf die dock icons machen? wie
    füge ich sonst anwendungen hinzu?"

    Die dritte Frage ist die tragende. Anheften ging bis dahin NUR ueber
    `zepos-settings-gui`, Seite "Leiste" - ein Fenster oeffnen, eine
    Seite finden, eine Liste bedienen, um ein Symbol anzuheften, das man
    gerade vor sich sieht.

WAS HIER GEMESSEN WIRD UND WAS NEBENAN
    Hier: WELCHE Punkte ein Menue traegt, wann ein Punkt fehlt, welchen
    Befehl er absetzt, welches Dokument er schreibt, und ob die Reihe
    danach OHNE Neustart anders aussieht.

    Nebenan (tests/render/test_menue.py): ob ein Menue auf einer
    Layer-Shell-Flaeche ueberhaupt erscheint, ob es ueber ihren Rand
    hinausragen darf und ob es auf allen Wegen wieder verschwindet. Das
    braucht einen Compositor und ein Bild; hier braucht es keins.

DER AUFBAU
    Derselbe wie in test_dock_minimized.py - ein Hyprland, das nur aus
    seinen beiden Sockets besteht und jedes `dispatch` mitschreibt -,
    plus zwei Zutaten, die es dort nicht gibt:

      ein PROZESS mit dem richtigen Namen
          "Zum Dock hinzufuegen" fragt nicht die Fensterklasse, sondern
          /proc/<pid>/comm (siehe anheftbar() in ags-dock.template).
          Eine erfundene PID beantwortet das mit nichts. Also laeuft
          hier ein echtes Programm, das "gimp" heisst - eine Kopie von
          `sleep` unter diesem Namen, GEMESSEN: comm=gimp.

      ein zepos-settings-gui, das jedes Dokument aufhebt
          Der Menuepunkt schreibt ueber diesen Befehl. Eine Attrappe,
          die seine Aufrufe mitschreibt und antwortet wie die echte
          Bruecke, macht aus "es hat wohl geklappt" eine Messung: das
          Dokument steht danach auf der Platte und wird verglichen.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.gtk4_headless import broadwayd, start_broadwayd, stop_broadwayd
from tests.src.test_bar_headless import (
    CHILD_TIMEOUT, Run, _DISPLAYS, _bundle, _desktop_entries)
from tests.src.test_dock_minimized import (
    FakeCompositor, MINIMIZED, MINIMIZED_ID, SICHTBAR, _client)

CHILD = Path(__file__).resolve().parent / "dock_menue_child.tsx"

# Die drei angehefteten Namen, die in diesem Aufbau ueberhaupt einen
# Knopf bekommen. Die uebrigen aus src/apps.py fallen heraus, weil ihr
# Programm nicht in DESKTOP_ENTRIES steht - genau das misst
# test_bar_headless.py schon, hier ist es nur die Ausgangslage.
ANGEHEFTET = ["firefox", "nautilus", "btop"]

# Das Fenster, an dem "Zum Dock hinzufuegen" gemessen wird. Seine Klasse
# ist die StartupWMClass des gimp-Eintrags (siehe DESKTOP_ENTRIES), sein
# Programm heisst gimp, und gimp ist NICHT angeheftet - also gehoert es
# hinter den Trenner und traegt den Punkt.
GIMP_TITEL = "Gimp-Fenster"

# Ein abgelegtes Fenster einer ANGEHEFTETEN Anwendung. Es steht
# hinter dem Trenner (siehe den Kopf von ags-dock.template) und
# darf trotzdem kein zweites Firefox-Symbol anbieten.
ABGELEGTES_FIREFOX = "Firefox abgelegt"

# Die Zeichen, die das Menue traegt. Sie kommen aus src/icon_definition.py
# und stehen hier NICHT als Zeichen, sondern als Name: ein Zeichen im
# Testtext waere eine zweite Quelle, die auseinanderlaufen kann.
from src import icons_db  # noqa: E402

PIN_ICON = icons_db.icons["ICON_PIN"]
UNPIN_ICON = icons_db.icons["ICON_MINUS"]
NEW_WINDOW_ICON = icons_db.icons["ICON_WINDOW"]
CLOSE_ICON = icons_db.icons["ICON_WINDOW_CLOSE"]


def _bruecke(binaries: Path, mitschrift: Path, antwort: Path,
             dokument: Path) -> None:
    """Eine Attrappe von zepos-settings-gui, die alles aufhebt.

    Sie antwortet auf `--json get` mit dem Dokument, das der Test
    hinlegt, und legt bei `--json set` das uebergebene Dokument ab.
    Beides ist genau der Ausschnitt, den ags-dock.template benutzt -
    mehr nachzubauen hiesse, die Bruecke nachzubauen und damit zu
    messen, was der Nachbau tut.

    PYTHON UND KEIN SHELLSKRIPT, und das ist gemessen: der PATH dieses
    Laufs enthaelt NUR das Programmverzeichnis (siehe den Kopf von
    dock_headless_child.tsx). Eine Fassung mit `cat` darin hat am
    20.08.2026 eine LEERE Antwort geliefert - `cat` liegt in /usr/bin
    und stand nicht auf dem PATH -, und das Dock hat daraufhin
    ordnungsgemaess auf seinen eigenen Stand zurueckgegriffen. Der Test
    war gruen im Aussehen und falsch in der Sache. Ein absoluter
    Shebang holt sich seinen Interpreter, ohne den PATH zu fragen.
    """
    binaries.mkdir(parents=True, exist_ok=True)
    stub = binaries / "zepos-settings-gui"
    stub.write_text(
        "#!/usr/bin/python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        f"with Path({str(mitschrift)!r}).open('a') as f:\n"
        "    f.write(' '.join(args) + '\\n')\n"
        "schalter = args[1] if len(args) > 1 else ''\n"
        "if schalter == 'get':\n"
        f"    sys.stdout.write(Path({str(antwort)!r}).read_text())\n"
        "elif schalter == 'set':\n"
        f"    Path({str(dokument)!r}).write_text(args[2])\n"
        "    sys.stdout.write('{\"ok\": true, \"problems\": [], "
        "\"written\": [\"bar.dock_pins\"]}')\n"
        "else:\n"
        "    sys.stdout.write('{\"ok\": false, \"problems\": "
        "[\"unbekannt\"]}')\n",
        encoding="utf-8")
    stub.chmod(0o755)


def _antwortdokument(pins: list[str]) -> str:
    """Was `--json get` liefert - nur die Felder, die das Dock liest.

    Die Form steht im Bericht zu Aufgabe 45 und in bridge.py,
    _page_leiste(): pages[name="leiste"].controls[key="bar.dock_pins"]
    .effective.
    """
    return json.dumps({
        "schema": 1,
        "ok": True,
        "pages": [
            {"name": "leiste", "controls": [
                {"key": "bar.dock_pins", "kind": "order",
                 "value": pins, "default": pins, "effective": pins,
                 "labels": {}, "discarded": []},
            ]},
        ],
    })


@pytest.fixture(scope="module")
def bundle(tmp_path_factory) -> tuple[Path, Path]:
    """Das uebersetzte Kind, einmal fuer alle Laeufe darunter."""
    return _bundle(CHILD, tmp_path_factory.mktemp("menue-bundle"))


def _lauf(bundle: tuple[Path, Path], root: Path, *,
          menues: tuple[str, ...] = (), wahl: str = "",
          gepflegt: list[str] | None = None,
          abgelegt: bool = False) -> dict:
    """Ein Lauf des Kindes gegen einen Compositor und eine Bruecke.

    Zurueck kommen die Spur des Kindes, die Befehle an den Compositor UND
    das Dokument, das die Bruecke bekommen hat. Die dritte Haelfte ist
    das eigentlich Neue: ein Menuepunkt, der richtig AUSSIEHT und das
    falsche Dokument schreibt, waere derselbe Fehler wie ein Knopf, der
    den falschen Befehl absetzt.
    """
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")
    if shutil.which("sleep") is None:
        pytest.skip("kein `sleep` - ohne echtes Programm gibt es kein comm")

    bundled, ags = bundle
    runtime = root / "run"
    runtime.mkdir()
    runtime.chmod(0o700)
    share = root / "share"
    binaries = root / "bin"
    _desktop_entries(share, binaries)

    # DAS PROGRAMM, DAS "gimp" HEISST. _desktop_entries legt dafuer ein
    # Bash-Skript ab, das sofort endet; comm waere dann der Interpreter
    # und der Prozess ohnehin fort. Eine Kopie von `sleep` heisst im
    # Kern so, wie ihre Datei heisst - GEMESSEN am 20.08.2026:
    # comm=gimp.
    shutil.copy(shutil.which("sleep"), binaries / "gimp")
    (binaries / "gimp").chmod(0o755)
    prozess = subprocess.Popen([str(binaries / "gimp"), "120"])

    # UND EIN `bash` IM SELBEN VERZEICHNIS, weil der PATH dieses Laufs
    # NUR daraus besteht (siehe den Kopf von dock_headless_child.tsx:
    # sonst misst er, was der Entwickler zufaellig installiert hat).
    # ags-dock.template ruft die Bruecke ueber `bash -c` - dieselbe
    # Zeile wie ags-settings.template, mit derselben Begruendung -, und
    # ohne bash auf dem PATH scheitert der Aufruf, bevor die Attrappe
    # ueberhaupt gerufen wird. GEMESSEN am 20.08.2026: der Lauf war
    # gruen im Aussehen und leer in der Wirkung, keine einzige Zeile in
    # der Mitschrift.
    #
    # Eine Verknuepfung und keine Kopie, und `bash` ist keine Anwendung:
    # es traegt keinen .desktop-Eintrag, faellt also nicht in die
    # Auswahl, die dieser Lauf misst.
    bash = shutil.which("bash")
    assert bash, "ohne bash kann das Dock seine Bruecke nicht rufen"
    (binaries / "bash").symlink_to(bash)

    mitschrift = root / "bruecke.log"
    antwort = root / "bruecke-get.json"
    dokument = root / "bruecke-set.json"
    antwort.write_text(_antwortdokument(gepflegt if gepflegt is not None
                                        else ANGEHEFTET), encoding="utf-8")
    _bruecke(binaries, mitschrift, antwort, dokument)

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    clients = [_client("0x900", "Gimp", GIMP_TITEL, SICHTBAR, str(SICHTBAR))]
    clients[0]["pid"] = prozess.pid
    if abgelegt:
        clients.append(_client("0xa00", "firefox", ABGELEGTES_FIREFOX,
                               MINIMIZED_ID, MINIMIZED))
    compositor = FakeCompositor(runtime, clients)
    try:
        result = subprocess.run(
            [str(bundled)],
            env={
                "PATH": str(binaries),
                "HOME": str(root),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_DIRS": str(share),
                "XDG_DATA_HOME": str(root / "data"),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={root}/kein-bus",
                "HYPRLAND_INSTANCE_SIGNATURE": FakeCompositor.SIGNATURE,
                "ZEPOS_TRACE": str(trace),
                "ZEPOS_CSS": str(ags / "bar.css"),
                "ZEPOS_MENUES": "|".join(menues),
                "ZEPOS_WAEHLE": wahl,
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        compositor.stop()
        stop_broadwayd(server)
        prozess.terminate()
        prozess.wait(timeout=10)

    lauf = Run(result.returncode, result.stdout, result.stderr,
               trace.read_text() if trace.exists() else "", "")
    return {
        "lauf": lauf,
        "dispatches": list(compositor.dispatches),
        "aufrufe": (mitschrift.read_text().splitlines()
                    if mitschrift.exists() else []),
        "dokument": (json.loads(dokument.read_text())
                     if dokument.exists() else None),
    }


# --------------------------------------------------------------------
# Was in einem Menue steht
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def menues(bundle, tmp_path_factory) -> dict:
    """Beide Menues aufgeklappt, nichts angeklickt."""
    return _lauf(bundle, tmp_path_factory.mktemp("menue-inhalt"),
                 menues=("Firefox", GIMP_TITEL))


def _pins(ergebnis: dict, marke: str) -> list[str]:
    """Die Aufschriften der ANGEHEFTETEN Knoepfe aus einer Marke."""
    return [teil.split("[")[0]
            for teil in ergebnis["lauf"].mark(marke).split(",")
            if "dock-pin" in teil]


def _menue(ergebnis: dict, knopf: str) -> list[str]:
    marke = ergebnis["lauf"].mark(f"menue-{knopf}")
    return [teil for teil in marke.split(";") if teil]


def test_eine_anheftung_bietet_neues_fenster_und_abnehmen(menues):
    """Die zwei Punkte, die zu einem angehefteten Symbol gehoeren.

    "Neues Fenster" ist der EINZIGE Weg zu einem zweiten Fenster einer
    laufenden Anwendung - der Linksklick holt das erste nach vorn, und
    das soll er ("wie Apple OS", 11.08.2026).
    """
    assert _menue(menues, "Firefox") == [
        f"{NEW_WINDOW_ICON} New window",
        f"{UNPIN_ICON} Remove from dock",
    ], menues["lauf"].trace


def test_ein_fenster_bietet_anheften_und_schliessen(menues):
    """Und "Schliessen" ist derselbe Befehl wie der Mittelklick - eine
    Geste ohne Beschriftung findet nur, wer sie schon kennt."""
    assert _menue(menues, GIMP_TITEL) == [
        f"{PIN_ICON} Add to dock",
        f"{CLOSE_ICON} Close",
    ], menues["lauf"].trace


def test_jede_zeile_traegt_ihr_eigenes_zeichen(menues):
    """Vier Punkte, vier verschiedene Zeichen.

    Zwei gleiche Zeichen mit zwei verschiedenen Wirkungen sind ein
    Bedienfehler mit Ansage - besonders zwischen "Vom Dock entfernen"
    und "Schliessen", die nebeneinander stehen koennen.
    """
    zeichen = [zeile.split(" ")[0]
               for knopf in ("Firefox", GIMP_TITEL)
               for zeile in _menue(menues, knopf)]
    assert len(zeichen) == 4, zeichen
    assert len(set(zeichen)) == 4, f"nicht alle verschieden: {zeichen}"
    assert "" not in zeichen, f"eine Zeile ohne Zeichen: {zeichen}"


def test_kein_menue_ist_leer(menues):
    """Ein Rechtsklick, der nichts aufklappt, ist ein Rechtsklick, der
    nicht funktioniert - genau die Meldung, die hier beantwortet wird."""
    for knopf in ("Firefox", GIMP_TITEL):
        assert _menue(menues, knopf), f"{knopf} klappt ein leeres Menue auf"


# --------------------------------------------------------------------
# Zum Dock hinzufuegen
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def anheften(bundle, tmp_path_factory) -> dict:
    """Rechtsklick auf das Gimp-Fenster, "Add to dock" gewaehlt."""
    return _lauf(bundle, tmp_path_factory.mktemp("menue-anheften"),
                 wahl=f"{GIMP_TITEL}>Add to dock")


def test_anheften_schreibt_genau_ein_dokument_an_die_bruecke(anheften):
    """Die Nutzerliste aus Aufgabe 45, kein zweiter Ort.

    `dock_baseline` steht ABSICHTLICH nicht darin: den Schluessel
    schreibt der Befehl selbst mit (Bericht Aufgabe 45). Wer ihn von
    hier aus mitschickte, ueberschriebe die Vorgabe, gegen die der
    Nutzer sich einmal entschieden hat.
    """
    assert anheften["dokument"] == {
        "bar.dock_pins": ANGEHEFTET + ["gimp"]}, (
        f"geschrieben wurde {anheften['dokument']!r}\n"
        + "\n".join(anheften["aufrufe"]))


def test_anheften_liest_erst_und_schreibt_dann(anheften):
    """GELESEN WIRD ZUERST, und zwar bei der Bruecke.

    Der Stand DIESER Sitzung ist nicht die Wahrheit - das
    Einstellungsfenster schreibt in dieselbe Liste. Auf ihn aufzubauen
    hiesse, eine fremde Aenderung beim naechsten Anheften
    stillschweigend zurueckzunehmen.
    """
    schalter = [zeile.split()[1] for zeile in anheften["aufrufe"]
                if len(zeile.split()) > 1]
    assert schalter == ["get", "set"], (
        f"die Bruecke wurde so gerufen: {anheften['aufrufe']}")


def test_das_neue_symbol_steht_sofort_im_fuss(anheften):
    """OHNE Neustart der Oberflaeche, und das ist die halbe Bestellung.

    Die erzeugte Zeile PINNED in widget/Dock.tsx kennt gimp nicht; sie
    kommt erst beim naechsten Erzeugungslauf nach (die Marke dafuer legt
    `zepos-settings-gui --json set`, src/bin/zepos-session liest sie
    beim naechsten Anmelden). Was der Nutzer sieht, darf darauf nicht
    warten.
    """
    vorher = _pins(anheften, "kinder")
    nachher = _pins(anheften, "kinder-danach")
    assert vorher, "vorher war gar nichts angeheftet"
    assert not [name for name in vorher if name.startswith("GIMP")], (
        f"gimp war schon vorher angeheftet - dann misst dieser Lauf "
        f"nichts: {vorher}")
    assert [name for name in nachher if name.startswith("GIMP")], (
        f"nach dem Anheften steht auf dem Fuss: {nachher}")


def test_das_fenster_steht_danach_unter_seinem_symbol(anheften):
    """Und nicht mehr daneben.

    Sobald gimp angeheftet ist, gehoert sein Fenster zu dieser
    Anheftung - die Regel aus dem Kopf von ags-dock.template ("ein
    Fenster an beiden Stellen waere dasselbe Programm zweimal im Dock")
    gilt ab demselben Augenblick. Der eigene Knopf verschwindet, und das
    Symbol zaehlt das Fenster mit.
    """
    nachher = anheften["lauf"].mark("kinder-danach")
    assert f"{GIMP_TITEL}[" not in nachher, (
        f"das Fenster hat noch einen eigenen Knopf: {nachher}")
    assert "GIMP (1)[" in nachher, (
        f"das Symbol zaehlt sein Fenster nicht mit: {nachher}")


# --------------------------------------------------------------------
# Vom Dock entfernen
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def abnehmen(bundle, tmp_path_factory) -> dict:
    """Rechtsklick auf Firefox, "Remove from dock" gewaehlt."""
    return _lauf(bundle, tmp_path_factory.mktemp("menue-abnehmen"),
                 wahl="Firefox>Remove from dock")


def test_abnehmen_schreibt_die_liste_ohne_diesen_namen(abnehmen):
    assert abnehmen["dokument"] == {
        "bar.dock_pins": ["nautilus", "btop"]}, (
        f"geschrieben wurde {abnehmen['dokument']!r}")


def test_das_symbol_ist_sofort_fort(abnehmen):
    vorher = abnehmen["lauf"].mark("kinder")
    nachher = abnehmen["lauf"].mark("kinder-danach")
    assert "Firefox[dock-button dock-pin]" in vorher, vorher
    assert "Firefox[dock-button dock-pin]" not in nachher, nachher
    # Und die uebrigen stehen noch da - ein Abnehmen, das die Reihe
    # leert, waere schlimmer als keines.
    assert "Dateien[dock-button dock-pin]" in nachher, nachher


# --------------------------------------------------------------------
# Was ein Punkt an den Compositor schickt
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def schliessen(bundle, tmp_path_factory) -> dict:
    """Rechtsklick auf das Gimp-Fenster, "Close" gewaehlt."""
    return _lauf(bundle, tmp_path_factory.mktemp("menue-schliessen"),
                 wahl=f"{GIMP_TITEL}>Close")


def test_schliessen_setzt_denselben_befehl_ab_wie_der_mittelklick(schliessen):
    assert schliessen["dispatches"] == ["closewindow address:0x900"], (
        f"abgesetzt wurde {schliessen['dispatches']!r}")


def test_schliessen_fasst_die_anheftungen_nicht_an(schliessen):
    """Es ruft die Bruecke gar nicht - ein Fenster zu schliessen hat mit
    der Anheftungsliste nichts zu tun."""
    assert schliessen["aufrufe"] == [], schliessen["aufrufe"]
    assert schliessen["dokument"] is None


# --------------------------------------------------------------------
# Wann "Zum Dock hinzufuegen" NICHT dasteht
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def schon_vertreten(bundle, tmp_path_factory) -> dict:
    """Ein ABGELEGTES Fenster einer Anwendung, die schon angeheftet ist.

    Der einzige Fall, in dem ein Fenster hinter dem Trenner steht,
    obwohl seine Anwendung ein Symbol hat - siehe den Kopf von
    ags-dock.template, "WOHIN EIN ABGELEGTES FENSTER GEHOERT". Genau
    dort darf "Zum Dock hinzufuegen" nicht stehen.
    """
    return _lauf(bundle, tmp_path_factory.mktemp("menue-vertreten"),
                 menues=(ABGELEGTES_FIREFOX,), abgelegt=True)


def test_ein_bereits_vertretener_name_wird_nicht_zweimal_angeboten(
        schon_vertreten):
    """Spec §7.4: ein Bedienelement, das nichts tut, ist der schlimmste
    Fehler, den ZepOS erzeugen kann.

    Ein zweites Firefox-Symbol waere genau das - es sieht aus wie eine
    Anheftung und heftet nichts an, weil Firefox schon dasteht. Uebrig
    bleibt "Schliessen", und das ist ein vollstaendiges Menue.
    """
    assert _menue(schon_vertreten, ABGELEGTES_FIREFOX) == [
        f"{CLOSE_ICON} Close"], schon_vertreten["lauf"].trace


def test_der_lauf_meldet_nichts_ueber_ein_fehlendes_zeichen(menues):
    """Ein Menuezeichen, das die Zeichenquelle nicht kennt, waere ein
    leeres Kaestchen - und das faellt in einem Menue mehr auf als
    irgendwo sonst."""
    for name in ("ICON_PIN", "ICON_MINUS", "ICON_WINDOW", "ICON_WINDOW_CLOSE"):
        assert icons_db.icons.get(name), f"{name} fehlt in icons_db"
