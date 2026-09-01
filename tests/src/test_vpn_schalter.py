# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Schalter der VPN-Liste, betaetigt statt betrachtet.

WAS GEMELDET WURDE, UND WAS DARAUS WURDE
    Der Nutzer am 22.08.2026, woertlich: "ich will, dass ich in der
    liste das auswaehlen kann per toggle, welche vpn aktiv sein soll -
    bei wireguard, weil ich dort mehrere vpns habe und alle darueber
    verwaltbar sein muessen. das gleiche gilt uebrigens fuer die anderen
    vpn verbindungen auch!!!"

    Die Antwort steht in bc93496: `vpn` traegt seither `connections` und
    `active`, und ags-vpn.template zeichnet je Verbindung eine Zeile mit
    einem Schalter.

WARUM DIESE DATEI SEIT DEM 22.08.2026 EXISTIERT
    GEZAEHLT ueber den ganzen Baum: `schalte`, `vpnListe` und
    `laufendeId` - die drei Stuecke, aus denen die Neuerung besteht -
    kamen in KEINER Testdatei vor. Der einzige Test, der die Seite
    ueberhaupt anfasste, war tests/render/test_vpn_breite.py, und der
    misst die BREITE des Einstellungsfensters. Ein Fenster ganz ohne
    Liste haette ihn genauso bestanden.

    Die Hauptneuerung einer Fassung, die veroeffentlicht werden soll,
    ohne einen einzigen Test, der sie bedient.

WAS HIER GEMESSEN WIRD
    Eine Liste mit ZWEI Verbindungen - eine WireGuard, eine IPsec, weil
    genau das Nebeneinander die Bestellung war. Dann wird der Schalter
    der zweiten wirklich umgelegt, und danach steht die Frage: ist jetzt
    die andere Verbindung die ausgewaehlte, und stimmen die
    Beschriftungen noch.

    Umgelegt wird die IPsec-Zeile, und das ist eine Entscheidung: eine
    Verbindung, die eine Anmeldung braucht, wird von schalte() nur
    AUSGEWAEHLT und zeigt ihr Formular - sie verbindet nicht (siehe "WAS
    DER SCHALTER BEDEUTET" in ags-vpn.template). Der Lauf misst damit
    genau den Weg, um den es geht, und startet dabei nichts, was einen
    Tunnel aufbauen koennte.

DIE GEGENPROBE, UND WARUM SIE HIER STEHT UND NICHT IM BERICHT
    test_ohne_schalter_bewegt_sich_nichts baut dieselbe Seite noch
    einmal, nimmt aber vorher den zepToggle aus der ERZEUGTEN Datei
    heraus - und verlangt, dass der Lauf dann "kein-schalter" meldet und
    die Auswahl stehenbleibt. Ohne sie waere nicht bewiesen, dass die
    Behauptungen oben am Schalter haengen und nicht an irgendetwas
    anderem, das die Zeile ohnehin tut.

SICHERHEIT
    Der Lauf faehrt gegen einen eigenen gtk4-broadwayd in einem eigenen
    XDG_RUNTIME_DIR und ruehrt die Hyprland-Sitzung des Entwicklers
    nicht an. `{{ZEPOS_SYSTEM_ROOT}}` zeigt auf ein Wegwerfverzeichnis
    mit einem vpn.py, das "disconnected" druckt - das echte vpn.py wird
    nicht ausgefuehrt, also fragt niemand NetworkManager oder strongSwan
    etwas.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT))

from tests.gtk4_headless import (                          # noqa: E402
    broadwayd, start_broadwayd, stop_broadwayd)

pytestmark = pytest.mark.allow_subprocess

CHILD = Path(__file__).resolve().parent / "vpn_schalter_child.tsx"

# Eine eigene Nummernreihe. test_bar_headless.py nimmt 120-159, und eine
# Anzeigenummer ist maschinenweit - siehe refuse_a_foreign_display() in
# tests/gtk4_headless.py, wo ein fremder Socket einen Nachmittag gekostet
# hat.
_DISPLAYS = iter(range(200, 220))

CHILD_TIMEOUT = 180

# Nur, was das Kind wirklich braucht. ags-vpn.template importiert `_`
# und `format` aus utils/i18n und vier Bauteile aus utils/kit; die
# ShellSeite ist ein `import type` und verschwindet beim Uebersetzen,
# also muss utils/overlay hier NICHT erzeugt werden.
RENDERED = {
    "templates/ags-i18n.template": "utils/i18n.ts",
    "templates/ags-kit.template": "utils/kit.ts",
    "templates/ags-vpn.template": "widget/VpnManager.tsx",
}

# Die Zeile, die den Schalter an eine Zeile haengt - woertlich aus
# ags-vpn.template. Die Gegenprobe schneidet genau sie heraus.
#
# Sie steht hier als Text und nicht als Muster, damit die Gegenprobe
# LAUT scheitert, sobald jemand die Vorlage an dieser Stelle umschreibt:
# ein Muster, das nichts mehr findet, entfernte stillschweigend nichts
# und die Gegenprobe waere gruen, ohne etwas ausgebaut zu haben.
SCHALTER_ZEILE = "          ende: zepToggle(steht, (an) => { void schalte(eintrag, an) }),"

# Die zwei Verbindungen. Zwei BAUARTEN, weil genau das die Bestellung
# war ("bei wireguard, weil ich dort mehrere vpns habe ... das gleiche
# gilt uebrigens fuer die anderen vpn verbindungen auch").
ZUHAUSE = "Zuhause"
ARBEIT = "Arbeit"
HEIM_ENDPUNKT = "heim.example.net:51820"
ARBEIT_SERVER = "vpn.arbeit.example"

# Was in der Nebenzeile stehen muss - eintragUnterzeile() in
# ags-vpn.template setzt "<Bauart> · <Ziel>" zusammen. Das Trennzeichen
# ist ein Mittelpunkt (U+00B7) und kein Bindestrich.
ZUHAUSE_UNTER = f"WireGuard · {HEIM_ENDPUNKT}"
ARBEIT_UNTER = f"IPsec · {ARBEIT_SERVER}"

# Welche Zeile das Kind umlegt: die zweite (IPsec). Siehe den Dateikopf.
UMGELEGT = 1


def _einstellungen(user_root: Path) -> None:
    """Die Einstellungsdatei, aus der die Seite ihre Liste liest.

    Aus settings.defaults() und settings.default_connection() gebaut und
    nicht getippt: `schema_version` und die Feldnamen einer Verbindung
    stehen damit an EINER Stelle. Eine abgeschriebene Datei waere die
    zweite, und sie waere die, die veraltet - dieselbe Begruendung wie in
    tests/render/test_vpn_breite.py.
    """
    sys.path.insert(0, str(SRC))
    try:
        import settings
        dokument = settings.defaults()
        zuhause = dict(settings.default_connection())
        zuhause.update({
            "id": "c1",
            "connection_name": ZUHAUSE,
            "kind": "wireguard",
        })
        zuhause["wireguard"] = dict(zuhause["wireguard"])
        zuhause["wireguard"]["peers"] = [{"endpoint": HEIM_ENDPUNKT}]

        arbeit = dict(settings.default_connection())
        arbeit.update({
            "id": "c2",
            "connection_name": ARBEIT,
            "kind": "ipsec",
            "server": ARBEIT_SERVER,
        })

        dokument["vpn"] = {"active": "c1", "connections": [zuhause, arbeit]}
    finally:
        sys.path.remove(str(SRC))

    user_root.mkdir(parents=True, exist_ok=True)
    (user_root / "user-settings.json").write_text(
        json.dumps(dokument), encoding="utf-8")


def _stub_vpn_tool(system_root: Path) -> None:
    """Ein vpn.py, das "disconnected" druckt und sonst nichts tut.

    Die Seite fragt beim Sichtbarwerden `python3 <ZEPOS_SYSTEM_ROOT>/
    vpn.py --status` (VPN_STATUS_QUERY in ags-vpn.template). Das ECHTE
    vpn.py wuerde dafuer NetworkManager oder strongSwan befragen - auf
    der Maschine, an der der Entwickler gerade sitzt. Hier antwortet
    stattdessen eine Zeile, und der Zustand des Laufs haengt nicht daran,
    ob nebenan ein Tunnel steht.
    """
    system_root.mkdir(parents=True, exist_ok=True)
    (system_root / "vpn.py").write_text(
        "# SPDX-License-Identifier: GPL-3.0-or-later\n"
        'print("disconnected")\n', encoding="utf-8")


def _render(target: Path, system_root: Path) -> None:
    """Die drei Vorlagen, uebersetzt wie der Generator sie uebersetzt."""
    sys.path.insert(0, str(SRC))
    try:
        import template_processor
        prozessor = template_processor.ConfigProcessor(
            paths={"ZEPOS_SYSTEM_ROOT": str(system_root)})
        for vorlage, ausgabe in RENDERED.items():
            ziel = target / ausgabe
            ziel.parent.mkdir(parents=True, exist_ok=True)
            prozessor.apply_template(SRC / vorlage, ziel)
    finally:
        sys.path.remove(str(SRC))


def _baue(wurzel: Path, ohne_schalter: bool = False) -> tuple[Path, Path]:
    """Die uebersetzte Seite. Zurueck kommen Buendel und Systemwurzel."""
    if shutil.which("ags") is None:
        pytest.skip("ags fehlt; es kommt mit dem Paket aylurs-gtk-shell")

    system_root = wurzel / "system"
    _stub_vpn_tool(system_root)

    ags = wurzel / "ags"
    ags.mkdir()
    _render(ags, system_root)

    if ohne_schalter:
        seite = ags / RENDERED["templates/ags-vpn.template"]
        text = seite.read_text(encoding="utf-8")
        assert SCHALTER_ZEILE in text, (
            "die Zeile, die den Schalter an die Zeile haengt, steht nicht "
            "mehr so in der erzeugten VpnManager.tsx. Diese Gegenprobe baut "
            "genau sie aus - findet sie sie nicht, baut sie nichts aus und "
            "bewiese nichts. SCHALTER_ZEILE nachziehen.")
        seite.write_text(text.replace(SCHALTER_ZEILE, ""), encoding="utf-8")

    shutil.copy(CHILD, ags / "child.tsx")
    buendel = wurzel / "child.js"
    ergebnis = subprocess.run(
        ["ags", "bundle", str(ags / "child.tsx"), str(buendel),
         "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=300,
    )
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat die VPN-Seite nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)
    return buendel, system_root


class Lauf:
    """Was ein Lauf hinterlassen hat - dieselbe Form wie Run in
    tests/src/test_bar_headless.py."""

    def __init__(self, returncode: int, stdout: str, stderr: str,
                 spur: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.spur = spur

    def marke(self, name: str) -> str:
        treffer = [zeile for zeile in self.spur.splitlines()
                   if zeile.startswith(name + ":")]
        assert treffer, f"keine Marke {name} in der Spur:\n{self.bericht}"
        return treffer[0].split(":", 1)[1]

    def zeilen(self, name: str) -> list[list[str]]:
        """Eine Zeilenmarke, aufgeloest in Titel/Nebenzeile/Auswahl/Schalter."""
        roh = self.marke(name)
        return [eintrag.split("|") for eintrag in roh.split(";") if eintrag]

    @property
    def bericht(self) -> str:
        return (f"rueckgabewert: {self.returncode}\n"
                f"stdout: {self.stdout!r}\nstderr:\n{self.stderr}\n"
                f"spur:\n{self.spur}")


def _lauf(wurzel: Path, ohne_schalter: bool = False) -> Lauf:
    server_befehl = broadwayd()
    if server_befehl is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    buendel, _system_root = _baue(wurzel, ohne_schalter=ohne_schalter)

    laufzeit = wurzel / "run"
    laufzeit.mkdir()
    # GLib lehnt ein weltlesbares XDG_RUNTIME_DIR ab und sagt es auf
    # stderr.
    laufzeit.chmod(0o700)

    user_root = wurzel / "zepos"
    _einstellungen(user_root)

    spur = wurzel / "spur"
    nummer = next(_DISPLAYS)
    server, _socket = start_broadwayd(server_befehl, laufzeit, nummer)
    try:
        ergebnis = subprocess.run(
            [str(buendel)],
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(wurzel),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{nummer}",
                "XDG_RUNTIME_DIR": str(laufzeit),
                "XDG_CONFIG_HOME": str(wurzel / "config"),
                # Die Seite liest ihre Liste von hier - siehe
                # SETTINGS_FILE in ags-vpn.template.
                "ZEPOS_USER_ROOT": str(user_root),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={wurzel}/kein-bus",
                # Damit `_` die englischen msgid zurueckgibt und die
                # Erwartungen unten nicht an der Sprache dieser Maschine
                # haengen.
                "LC_ALL": "C",
                "LANG": "C",
                "ZEPOS_TRACE": str(spur),
                "ZEPOS_SCHALTER": str(UMGELEGT),
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(server)

    return Lauf(ergebnis.returncode, ergebnis.stdout, ergebnis.stderr,
                spur.read_text() if spur.exists() else "")


@pytest.fixture(scope="module")
def lauf(tmp_path_factory) -> Lauf:
    """Ein Lauf mit Schalter, fuer alle Zusicherungen darunter.

    Modulweit, weil `ags bundle` und der Anzeigeserver zusammen mehrere
    Sekunden brauchen und jede Zusicherung darunter dieselbe Messung
    liest.
    """
    return _lauf(tmp_path_factory.mktemp("vpn-schalter"))


def test_die_liste_traegt_beide_verbindungen(lauf):
    """Zwei Verbindungen, zwei Zeilen - und die Beschriftungen stimmen.

    Die Nebenzeile ist der Punkt: sie nennt die BAUART, und die Bauart
    ist der Grund, aus dem der Nutzer die Liste bestellt hat. Ein Zaehlen
    der Zeilen allein bewiese nur, dass zweimal irgendetwas dasteht.
    """
    assert lauf.marke("liste") == "da", lauf.bericht
    assert lauf.marke("marke") == "VPN connections", lauf.bericht

    zeilen = lauf.zeilen("zeilen-vorher")
    assert len(zeilen) == 2, lauf.bericht
    assert [z[0] for z in zeilen] == [ZUHAUSE, ARBEIT], lauf.bericht
    assert [z[1] for z in zeilen] == [ZUHAUSE_UNTER, ARBEIT_UNTER], lauf.bericht


def test_jede_zeile_hat_einen_schalter_und_keiner_steht_an(lauf):
    """Der Schalter sagt "dieser Tunnel steht" - und es steht keiner.

    `vpn.py --status` antwortet in diesem Aufbau "disconnected", also
    MUSS jeder Schalter auf aus stehen. Ein Schalter, der "an" zeigt,
    waehrend nichts steht, waere schlimmer als gar keiner - so steht es
    in ags-vpn.template, und hier wird es gemessen.
    """
    zeilen = lauf.zeilen("zeilen-vorher")
    assert [z[3] for z in zeilen] == ["aus", "aus"], lauf.bericht


def test_vor_dem_umlegen_ist_die_erste_verbindung_die_gewaehlte(lauf):
    """Die Ausgangslage, und sie kommt aus `vpn.active` - nicht aus der
    Reihenfolge. Ohne diese Zusicherung koennte der Test unten eine
    Auswahl feiern, die schon vorher dastand."""
    zeilen = lauf.zeilen("zeilen-vorher")
    assert [z[2] for z in zeilen] == ["gewaehlt", "-"], lauf.bericht


def test_der_schalter_laesst_sich_betaetigen_und_waehlt_die_andere(lauf):
    """Die Frage, fuer die es diese Datei gibt.

    Nach dem Umlegen ist die ZWEITE Verbindung die gewaehlte, und die
    erste ist es nicht mehr. Gemessen wird nach einer Wartezeit (siehe
    NACHLAUF_MS im Kind): eine Auswahl, die der naechste Zeichenlauf
    wieder einkassiert, ist keine.
    """
    assert lauf.marke("betaetigt") == ARBEIT, lauf.bericht

    zeilen = lauf.zeilen("zeilen-nachher")
    assert len(zeilen) == 2, lauf.bericht
    assert [z[2] for z in zeilen] == ["-", "gewaehlt"], lauf.bericht


def test_das_umlegen_laesst_die_beschriftungen_in_ruhe(lauf):
    """zeichneListe() baut die Zeilen NEU auf - jede Zeile ist nach dem
    Umlegen ein anderes Widget als vorher. Genau deshalb wird hier
    nachgesehen, ob dabei Titel und Nebenzeile dieselben geblieben sind:
    ein Neuzeichnen, das aus der Liste eine andere Liste macht, waere
    kein Umschalten."""
    vorher = lauf.zeilen("zeilen-vorher")
    nachher = lauf.zeilen("zeilen-nachher")

    assert [z[0] for z in nachher] == [z[0] for z in vorher], lauf.bericht
    assert [z[1] for z in nachher] == [z[1] for z in vorher], lauf.bericht


def test_eine_verbindung_mit_anmeldung_verbindet_nicht_von_selbst(lauf):
    """Der Schalter der IPsec-Zeile WAEHLT aus, er verbindet nicht.

    "Ein Schalter, der 'an' zeigt, waehrend nichts steht, waere schlimmer
    als gar keiner" - ags-vpn.template. Nach dem Umlegen steht die Zeile
    also auf ausgewaehlt UND ihr Schalter auf aus, weil kein Tunnel
    steht. Beides zusammen ist die Aussage; jede Haelfte allein waere
    auch mit einem kaputten Schalter zu haben.
    """
    nachher = lauf.zeilen("zeilen-nachher")
    assert nachher[UMGELEGT][2] == "gewaehlt", lauf.bericht
    assert [z[3] for z in nachher] == ["aus", "aus"], lauf.bericht


def test_ohne_schalter_bewegt_sich_nichts(tmp_path):
    """DIE GEGENPROBE.

    Dieselbe Seite, dieselbe Einstellungsdatei, derselbe Griff des
    Kindes - nur ist der zepToggle aus der erzeugten VpnManager.tsx
    herausgeschnitten. Die Zeilen stehen dann immer noch da (die Liste
    kommt aus vpnListe, nicht aus dem Schalter), aber es gibt nichts
    mehr umzulegen, und die Auswahl bleibt, wo sie war.

    Ohne diesen Lauf waere nicht bewiesen, dass die fuenf Zusicherungen
    oben am Schalter haengen: eine Zeile hat auch ein `aktion`, das beim
    Anklicken dasselbe tut, und ein Kind, das versehentlich die Zeile
    statt den Schalter betaetigt, saehe genau dasselbe Ergebnis.
    """
    ohne = _lauf(tmp_path, ohne_schalter=True)

    assert ohne.marke("liste") == "da", ohne.bericht
    zeilen = ohne.zeilen("zeilen-vorher")
    assert len(zeilen) == 2, ohne.bericht
    assert [z[3] for z in zeilen] == ["ohne", "ohne"], ohne.bericht

    assert ohne.marke("betaetigt") == "kein-schalter", ohne.bericht

    # Und die Auswahl steht, wo sie stand.
    nachher = ohne.zeilen("zeilen-nachher")
    assert [z[2] for z in nachher] == ["gewaehlt", "-"], ohne.bericht
