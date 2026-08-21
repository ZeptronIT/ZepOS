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

      eine echte Einstellungsdatei
          Der Menuepunkt schreibt ueber `settings.py dock|home
          add|remove` - denselben Unterbefehl, den das Home und der
          Starter rufen (Aufgabe 53, 21.08.2026). Dieser Lauf legt
          deshalb eine user-settings.json hin und sieht danach nach, was
          darin steht. Bis dahin stand hier eine Attrappe von
          `zepos-settings-gui`; die Datei ist die bessere Messung, aus
          demselben Grund, aus dem tests/src/test_launcher_pin.py den
          echten Schreibweg uebersetzt statt ihn nachzubauen.

WAS SEIT DEM 21.08.2026 DAZUGEKOMMEN IST
    Die sechs Menuepunkte in beide Richtungen (anheften/abnehmen,
    aufs Home legen/abnehmen), der Umschlag eines Punktes, wenn das
    Programm schon dort liegt - und die Probe, die der Nutzer gemeldet
    hat: eine Aenderung, die ein ANDERES Fenster schreibt, muss beim
    Fuss ankommen, ohne dass irgendetwas neu startet
    (test_eine_fremde_anheftung_erscheint_ohne_neustart).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
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
# Das Zeichen der zwei Home-Punkte, seit dem 21.08.2026. In BEIDE
# Richtungen dasselbe - der Kopf von ags-dock.template begruendet, warum
# hier das ZIEL das Zeichen bestimmt und nicht die Richtung.
HOME_ICON = icons_db.icons["ICON_COMPUTER"]
NEW_WINDOW_ICON = icons_db.icons["ICON_WINDOW"]
CLOSE_ICON = icons_db.icons["ICON_WINDOW_CLOSE"]

# Die ausgelieferte Auswahl DIESES Baums - dieselbe Quelle, aus der der
# Erzeugungslauf PINNED in widget/Dock.tsx schreibt und aus der
# settings.shipped_pins() antwortet. Nicht abgeschrieben: eine getippte
# Liste waere eine zweite, die veraltet, sobald jemand eine Anwendung
# aus packaging/zepos-apps/PKGBUILD nimmt.
SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))
import apps as _apps_modul  # noqa: E402

SHIPPED = _apps_modul.shipped(SRC)


def _einstellungen(root: Path, pins: list[str],
                   home: list[str] | None = None) -> Path:
    """Die Einstellungsdatei, wie sie VOR dem Lauf aussieht.

    KEINE ATTRAPPE MEHR, SEIT DEM 21.08.2026 (Aufgabe 53)
        Hier stand bis dahin ein nachgebautes `zepos-settings-gui`, das
        `--json get` mit einem Dokument beantwortete und `--json set`
        aufhob. Der Fuss ruft diesen Befehl nicht mehr: er ruft
        `settings.py dock add|remove`, denselben Unterbefehl, den das
        Home und der Starter rufen (siehe den Abschnitt "DIE
        ANHEFTUNGEN DES NUTZERS" in ags-dock.template).

        Damit braucht dieser Lauf keine Attrappe, sondern eine DATEI -
        und das ist die bessere Messung: gemessen wird, was in
        user-settings.json steht, nachdem der echte Schreibweg gelaufen
        ist, und nicht, was ein Nachbau aufgeschrieben hat. Dieselbe
        Entscheidung wie in tests/src/test_launcher_pin.py, wo der echte
        AppDiscovery.cpp gegen den echten Schreibweg laeuft.

    DIE ZWEI ANDEREN ABSCHNITTE STEHEN MIT DRIN, und zwar absichtlich:
    settings.merge() ERSETZT einen Abschnitt (siehe dort). Ein Schreiber,
    der nur die Anheftungen zurueckgibt, loescht die Leiste des Nutzers -
    und genau das kann dieser Lauf danach nachsehen.
    """
    wurzel = root / "zepos"
    wurzel.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": 1,
        "colors": {"accent": "#abcdef"},
        "bar": {
            "modules_left": ["custom/date"],
            "modules_right": ["tray"],
            "dock_pins": pins,
            "dock_baseline": SHIPPED,
        },
    }
    if home is not None:
        document["home"] = {"icons": [{"name": name} for name in home],
                            "baseline": SHIPPED}
    (wurzel / "user-settings.json").write_text(
        json.dumps(document, indent=2), encoding="utf-8")
    return wurzel


def _gelesen(wurzel: Path) -> dict:
    """Was nach dem Lauf in der Einstellungsdatei steht."""
    ziel = wurzel / "user-settings.json"
    return json.loads(ziel.read_text(encoding="utf-8")) if ziel.exists() else {}


@pytest.fixture(scope="module")
def bundle(tmp_path_factory) -> tuple[Path, Path]:
    """Das uebersetzte Kind, einmal fuer alle Laeufe darunter."""
    return _bundle(CHILD, tmp_path_factory.mktemp("menue-bundle"))


def _lauf(bundle: tuple[Path, Path], root: Path, *,
          menues: tuple[str, ...] = (), wahl: str = "",
          gepflegt: list[str] | None = None,
          home: list[str] | None = None,
          fremd: list[str] | None = None,
          abgelegt: bool = False) -> dict:
    """Ein Lauf des Kindes gegen einen Compositor und eine echte Datei.

    Zurueck kommen die Spur des Kindes, die Befehle an den Compositor UND
    die Einstellungsdatei, wie sie danach dasteht. Die dritte Haelfte ist
    das eigentlich Neue: ein Menuepunkt, der richtig AUSSIEHT und das
    falsche Dokument schreibt, waere derselbe Fehler wie ein Knopf, der
    den falschen Befehl absetzt.

    `fremd` ist ein Aufruf von settings.py, den DIESER Test waehrend des
    Laufs absetzt - also eine Aenderung, die von ausserhalb des Fusses
    kommt, so wie sie vom Starter oder vom Home kaeme. Er ist die Probe
    auf den Fehler, den der Nutzer aus 0.1.7 gemeldet hat ("wenn ich es
    dort mit der dock versuche dann passiert nichts").
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
    # Legt auch `bash` und `python3` als Weitergabeskripte ab - der Fuss
    # ruft settings.py darueber, und der PATH dieses Laufs besteht NUR
    # aus diesem Verzeichnis (siehe den Kopf von
    # dock_headless_child.tsx: sonst misst er, was der Entwickler
    # zufaellig installiert hat).
    _desktop_entries(share, binaries)

    # DAS PROGRAMM, DAS "gimp" HEISST. _desktop_entries legt dafuer ein
    # Bash-Skript ab, das sofort endet; comm waere dann der Interpreter
    # und der Prozess ohnehin fort. Eine Kopie von `sleep` heisst im
    # Kern so, wie ihre Datei heisst - GEMESSEN am 20.08.2026:
    # comm=gimp.
    shutil.copy(shutil.which("sleep"), binaries / "gimp")
    (binaries / "gimp").chmod(0o755)
    prozess = subprocess.Popen([str(binaries / "gimp"), "120"])

    wurzel = _einstellungen(
        root, gepflegt if gepflegt is not None else ANGEHEFTET, home)
    vorher = _gelesen(wurzel)

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    clients = [_client("0x900", "Gimp", GIMP_TITEL, SICHTBAR, str(SICHTBAR))]
    clients[0]["pid"] = prozess.pid
    if abgelegt:
        clients.append(_client("0xa00", "firefox", ABGELEGTES_FIREFOX,
                               MINIMIZED_ID, MINIMIZED))
    compositor = FakeCompositor(runtime, clients)
    umgebung = {
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
        # Die Einstellungsdatei DIESES Laufs. settings.py liest sie ueber
        # paths.user_root(), und der Fuss reicht die Umgebung an seinen
        # Unterprozess durch.
        "ZEPOS_USER_ROOT": str(wurzel),
        "ZEPOS_TRACE": str(trace),
        "ZEPOS_CSS": str(ags / "bar.css"),
        "ZEPOS_MENUES": "|".join(menues),
        "ZEPOS_WAEHLE": wahl,
        "ZEPOS_WARTEN": "2500" if fremd else "",
    }
    try:
        if fremd:
            kind = subprocess.Popen(
                [str(bundled)], env=umgebung,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            # WARTEN, BIS DER FUSS STEHT UND EINMAL GELESEN HAT. Ohne
            # diese Pause liefe die fremde Aenderung moeglicherweise VOR
            # dem ersten Lesevorgang durch, und der Lauf maesse dann den
            # Anfangswert und nicht die Meldung.
            time.sleep(1.2)
            fremdlauf = subprocess.run(
                [sys.executable, str(SRC / "settings.py"), *fremd],
                env={**umgebung, "ZEPOS_SYSTEM_ROOT": str(SRC),
                     "PATH": os.environ.get("PATH", "/usr/bin")},
                capture_output=True, text=True, timeout=60)
            assert fremdlauf.returncode == 0, (
                f"die fremde Aenderung ist gescheitert: {fremdlauf.stderr}")
            ausgabe, fehler = kind.communicate(timeout=CHILD_TIMEOUT)
            result = subprocess.CompletedProcess(
                [str(bundled)], kind.returncode, ausgabe, fehler)
        else:
            result = subprocess.run(
                [str(bundled)], env=umgebung,
                capture_output=True, text=True, timeout=CHILD_TIMEOUT)
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
        "vorher": vorher,
        "nachher": _gelesen(wurzel),
    }


# --------------------------------------------------------------------
# Was in einem Menue steht
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def menues(bundle, tmp_path_factory) -> dict:
    """Beide Menues aufgeklappt, nichts angeklickt.

    firefox liegt dabei AUF DEM HOME und gimp nicht - damit stehen in
    einem einzigen Lauf beide Richtungen des Home-Punktes nebeneinander.
    """
    return _lauf(bundle, tmp_path_factory.mktemp("menue-inhalt"),
                 menues=("Firefox", GIMP_TITEL), home=["firefox"])


def _pins(ergebnis: dict, marke: str) -> list[str]:
    """Die Aufschriften der ANGEHEFTETEN Knoepfe aus einer Marke."""
    return [teil.split("[")[0]
            for teil in ergebnis["lauf"].mark(marke).split(",")
            if "dock-pin" in teil]


def _menue(ergebnis: dict, knopf: str, marke: str = "menue") -> list[str]:
    text = ergebnis["lauf"].mark(f"{marke}-{knopf}")
    return [teil for teil in text.split(";") if teil]


def _pinliste(ergebnis: dict, wann: str = "nachher") -> list[str]:
    """Was in der Einstellungsdatei unter bar.dock_pins steht."""
    return ergebnis[wann].get("bar", {}).get("dock_pins")


def _homeliste(ergebnis: dict, wann: str = "nachher") -> list[str]:
    icons = ergebnis[wann].get("home", {}).get("icons") or []
    return [icon["name"] for icon in icons]


# --------------------------------------------------------------------
# Was in einem Menue steht
# --------------------------------------------------------------------

def test_eine_anheftung_bietet_drei_punkte(menues):
    """Die drei Punkte, die zu einem angehefteten Symbol gehoeren.

    "Neues Fenster" ist der EINZIGE Weg zu einem zweiten Fenster einer
    laufenden Anwendung - der Linksklick holt das erste nach vorn, und
    das soll er ("wie Apple OS", 11.08.2026).

    Der mittlere Punkt ist die Bestellung vom 21.08.2026: "das gleiche
    muss bei der dock auch funktionieren, weil ich nicht jedes icon auf
    der dock oder auf dem home haben will". firefox liegt in diesem Lauf
    auf dem Home, also steht dort die Gegenrichtung.
    """
    assert _menue(menues, "Firefox") == [
        f"{NEW_WINDOW_ICON} New window",
        f"{HOME_ICON} Remove from Home",
        f"{UNPIN_ICON} Remove from dock",
    ], menues["lauf"].trace


def test_ein_fenster_bietet_anheften_ablegen_und_schliessen(menues):
    """Und "Schliessen" ist derselbe Befehl wie der Mittelklick - eine
    Geste ohne Beschriftung findet nur, wer sie schon kennt.

    gimp liegt in diesem Lauf WEDER im Fuss NOCH auf dem Home, also
    zeigen beide Punkte in die Richtung "hinzufuegen".
    """
    assert _menue(menues, GIMP_TITEL) == [
        f"{PIN_ICON} Add to dock",
        f"{HOME_ICON} Add to Home",
        f"{CLOSE_ICON} Close",
    ], menues["lauf"].trace


def test_kein_menue_traegt_ein_zeichen_zweimal(menues):
    """Zwei gleiche Zeichen mit zwei verschiedenen Wirkungen sind ein
    Bedienfehler mit Ansage - besonders zwischen "Vom Dock entfernen"
    und "Schliessen", die nebeneinander stehen koennen.

    JE MENUE GEPRUEFT UND NICHT UEBER BEIDE, seit dem 21.08.2026: der
    Home-Punkt traegt in BEIDEN Menues dasselbe Zeichen, weil er in
    beiden dasselbe Ziel nennt. Zwei Menues sieht niemand gleichzeitig;
    zwei Zeilen EINES Menues schon.
    """
    for knopf in ("Firefox", GIMP_TITEL):
        zeichen = [zeile.split(" ")[0] for zeile in _menue(menues, knopf)]
        assert len(zeichen) == 3, f"{knopf}: {zeichen}"
        assert len(set(zeichen)) == 3, f"{knopf}: nicht verschieden {zeichen}"
        assert "" not in zeichen, f"{knopf}: eine Zeile ohne Zeichen"


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


def test_anheften_schreibt_den_namen_in_die_nutzerliste(anheften):
    """bar.dock_pins, kein zweiter Ort und keine zweite Datei."""
    assert _pinliste(anheften) == ANGEHEFTET + ["gimp"], (
        f"geschrieben wurde {_pinliste(anheften)!r}")


def test_anheften_schreibt_die_vorgabe_mit(anheften):
    """dock_baseline geht MIT hinaus, und der Menuepunkt schickt es nicht.

    Der Kopf bei BAR_BASELINE in src/settings.py fuehrt aus, woran das
    haengt: ohne frische Vorgabe erschiene alles, was ZepOS seither
    dazuliefert, beim naechsten Anmelden noch einmal - auch das, was der
    Nutzer gerade abgenommen hat. Geschrieben wird sie von
    `settings.py dock`, nicht vom Aufrufer; genau deshalb gibt es den
    Unterbefehl.
    """
    assert anheften["nachher"]["bar"]["dock_baseline"] == SHIPPED


def test_anheften_laesst_den_rest_der_datei_stehen(anheften):
    """settings.merge() ERSETZT einen Abschnitt.

    Ein Schreiber, der nur die Anheftungen zurueckgibt, loescht die
    Leiste des Nutzers - beide Modullisten stehen im SELBEN Abschnitt.
    Und die Farben, die in einem anderen stehen, gehen genauso wenig
    verloren.
    """
    bar = anheften["nachher"]["bar"]
    assert bar["modules_left"] == ["custom/date"], bar
    assert bar["modules_right"] == ["tray"], bar
    assert anheften["nachher"]["colors"] == {"accent": "#abcdef"}


def test_das_neue_symbol_steht_sofort_im_fuss(anheften):
    """OHNE Neustart der Oberflaeche, und das ist die halbe Bestellung.

    Die erzeugte Zeile PINNED in widget/Dock.tsx kennt gimp nicht - sie
    ist der Abzug des letzten Erzeugungslaufs. Was der Nutzer sieht,
    darf auf den naechsten nicht warten.
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
    assert _pinliste(abnehmen) == ["nautilus", "btop"], (
        f"geschrieben wurde {_pinliste(abnehmen)!r}")


def test_das_symbol_ist_sofort_fort(abnehmen):
    vorher = abnehmen["lauf"].mark("kinder")
    nachher = abnehmen["lauf"].mark("kinder-danach")
    assert "Firefox[dock-button dock-pin]" in vorher, vorher
    assert "Firefox[dock-button dock-pin]" not in nachher, nachher
    # Und die uebrigen stehen noch da - ein Abnehmen, das die Reihe
    # leert, waere schlimmer als keines.
    assert "Dateien[dock-button dock-pin]" in nachher, nachher


# --------------------------------------------------------------------
# Zum Home hinzufuegen und wieder abnehmen
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def aufs_home(bundle, tmp_path_factory) -> dict:
    """Rechtsklick auf Firefox, "Add to Home" gewaehlt.

    Das Home ist in diesem Lauf LEER (`home=[]`), also steht dort die
    Richtung "hinzufuegen". Eine leere Liste und nicht `None`: null
    hiesse "wie ausgeliefert", und dann laege firefox schon darauf.
    """
    return _lauf(bundle, tmp_path_factory.mktemp("menue-aufs-home"),
                 wahl="Firefox>Add to Home", home=[])


def test_aufs_home_legen_schreibt_den_home_abschnitt(aufs_home):
    """Der Punkt, der dem Fuss bis zum 21.08.2026 gefehlt hat.

    Geschrieben wird ueber `settings.py home add` - denselben
    Unterbefehl, den das Home selbst und der Starter rufen. Der Fuss
    weiss von home.baseline nichts und muss es nicht.
    """
    assert _homeliste(aufs_home) == ["firefox"], aufs_home["nachher"]


def test_aufs_home_legen_schreibt_die_home_vorgabe_mit(aufs_home):
    assert aufs_home["nachher"]["home"]["baseline"] == SHIPPED


def test_aufs_home_legen_fasst_die_anheftungen_nicht_an(aufs_home):
    """Zwei getrennte Auswahlen - das ist die Begruendung des Nutzers.

    "weil ich nicht jedes icon auf der dock oder auf dem home haben
    will": ein Symbol aufs Home zu legen darf es nicht aus dem Fuss
    nehmen und auch nicht hineinsetzen.
    """
    assert _pinliste(aufs_home) == ANGEHEFTET


@pytest.fixture(scope="module")
def vom_home(bundle, tmp_path_factory) -> dict:
    """Rechtsklick auf Firefox, "Remove from Home" gewaehlt."""
    return _lauf(bundle, tmp_path_factory.mktemp("menue-vom-home"),
                 wahl="Firefox>Remove from Home",
                 home=["firefox", "btop"])


def test_vom_home_nehmen_laesst_die_anderen_symbole_liegen(vom_home):
    assert _homeliste(vom_home) == ["btop"], vom_home["nachher"]
    assert _pinliste(vom_home) == ANGEHEFTET


# --------------------------------------------------------------------
# Dass eine FREMDE Aenderung ankommt
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def von_aussen(bundle, tmp_path_factory) -> dict:
    """Niemand klickt. Waehrend der Fuss steht, heftet ein ANDERER an.

    GEMELDET aus 0.1.7, woertlich: "auch im ags launcher bzw
    hyprlauncher kann ich nicht mit rechtsklick zu home hinzufügen, und
    wenn ich es dort mit der dock versuche dann passiert nichts".

    Der Starter schrieb richtig - die Anheftung stand in
    user-settings.json. Der Fuss erfuhr es nur nicht. Genau das ist
    hier nachgestellt: `settings.py dock add gimp` von aussen, waehrend
    der Fuss steht, ohne dass irgendetwas neu gestartet wird.

    DAS IST WOERTLICH DER BEFEHL DER ANDEREN ZWEI MENUES, und damit
    misst dieser eine Lauf beide Richtungen, die der Nutzer gemeldet
    hat:

        der Starter    AppDiscovery::pinToDock() setzt
                       `python3 <settings.py> dock add <name>` ab -
                       gemessen am UEBERSETZTEN Programm in
                       tests/src/test_launcher_pin.py
        das Home       dockAdd() in utils/user-settings.ts setzt
                       denselben Befehl ab - gemessen in
                       tests/src/test_dock_pins.py

    Es gibt keinen dritten Weg, auf dem eine Anheftung entstehen
    koennte, also gibt es auch keinen dritten Fall zu messen.
    """
    return _lauf(bundle, tmp_path_factory.mktemp("menue-von-aussen"),
                 menues=(GIMP_TITEL, "GIMP (1)"), home=[],
                 fremd=["dock", "add", "gimp"])


def test_eine_fremde_anheftung_erscheint_ohne_neustart(von_aussen):
    vorher = _pins(von_aussen, "kinder")
    nachher = _pins(von_aussen, "kinder-danach")
    assert not [name for name in vorher if name.startswith("GIMP")], (
        f"gimp stand schon vorher im Fuss: {vorher}")
    assert [name for name in nachher if name.startswith("GIMP")], (
        f"die fremde Anheftung ist nicht angekommen: {nachher}\n"
        + von_aussen["lauf"].trace)


def test_der_menuepunkt_schlaegt_nach_einer_fremden_aenderung_um(von_aussen):
    """Ein Menue, das "Zum Dock hinzufuegen" anbietet, waehrend das
    Symbol schon unten steht, ist genau die Sorte Punkt, die nichts tut.

    Nach dem Anheften steht das Fenster UNTER SEINEM SYMBOL und hat
    keinen eigenen Knopf mehr (siehe den Kopf von ags-dock.template) -
    der alte Punkt kann also gar nicht mehr aufgeklappt werden, und das
    Menue steht am Symbol.
    """
    vorher = _menue(von_aussen, GIMP_TITEL)
    assert vorher and vorher[0].endswith("Add to dock"), vorher
    assert von_aussen["lauf"].mark(f"menue-danach-{GIMP_TITEL}") \
        == "kein-knopf", von_aussen["lauf"].trace
    am_symbol = _menue(von_aussen, "GIMP (1)", "menue-danach")
    assert am_symbol and am_symbol[-1].endswith("Remove from dock"), (
        f"am Symbol steht: {am_symbol}\n" + von_aussen["lauf"].trace)


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


def test_schliessen_fasst_die_einstellungen_nicht_an(schliessen):
    """Ein Fenster zu schliessen hat mit der Anheftungsliste nichts zu
    tun - die Datei steht danach Zeichen fuer Zeichen so da wie vorher."""
    assert schliessen["nachher"] == schliessen["vorher"]


# --------------------------------------------------------------------
# Ein Fenster, dessen Anwendung schon im Fuss steht
# --------------------------------------------------------------------

@pytest.fixture(scope="module")
def schon_vertreten(bundle, tmp_path_factory) -> dict:
    """Ein ABGELEGTES Fenster einer Anwendung, die schon angeheftet ist.

    Der einzige Fall, in dem ein Fenster hinter dem Trenner steht,
    obwohl seine Anwendung ein Symbol hat - siehe den Kopf von
    ags-dock.template, "WOHIN EIN ABGELEGTES FENSTER GEHOERT".
    """
    return _lauf(bundle, tmp_path_factory.mktemp("menue-vertreten"),
                 menues=(ABGELEGTES_FIREFOX,), abgelegt=True, home=[])


def test_ein_bereits_vertretener_name_wird_nicht_zweimal_angeboten(
        schon_vertreten):
    """Spec §7.4: ein Bedienelement, das nichts tut, ist der schlimmste
    Fehler, den ZepOS erzeugen kann.

    Ein zweites Firefox-Symbol waere genau das - es sieht aus wie eine
    Anheftung und heftet nichts an, weil Firefox schon dasteht. Statt
    dessen steht die GEGENRICHTUNG da, und sie trifft den Namen der
    ANHEFTUNG: wer hier "Vom Dock entfernen" waehlt, nimmt das Symbol
    weg, das er vor sich sieht.
    """
    zeilen = _menue(schon_vertreten, ABGELEGTES_FIREFOX)
    assert zeilen == [
        f"{UNPIN_ICON} Remove from dock",
        f"{HOME_ICON} Add to Home",
        f"{CLOSE_ICON} Close",
    ], schon_vertreten["lauf"].trace


def test_der_lauf_meldet_nichts_ueber_ein_fehlendes_zeichen(menues):
    """Ein Menuezeichen, das die Zeichenquelle nicht kennt, waere ein
    leeres Kaestchen - und das faellt in einem Menue mehr auf als
    irgendwo sonst."""
    for name in ("ICON_PIN", "ICON_MINUS", "ICON_COMPUTER", "ICON_WINDOW",
                 "ICON_WINDOW_CLOSE"):
        assert icons_db.icons.get(name), f"{name} fehlt in icons_db"
