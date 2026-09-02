# SPDX-License-Identifier: GPL-3.0-or-later
"""Eine VPN-Verbindung ANSEHEN aendert nichts an ihr.

WAS GEMELDET WURDE (01.09.2026), WOERTLICH
    "um eisntellungen von vpns zu sehen muss man die vpn erst aktivieren
     das ist nicht gut"

WORAN ES LAG - der Ring, und er ist geschlossen
    Das Einstellungsfenster waehlte beim Aufgehen `section.active` aus
    der Datei (`loadAllSettings`: `gewaehlteId = section.active ||
    liste[0].id`). Geschrieben wird `vpn.active` von GENAU EINER Stelle:
    `saveSettings()` im Einstellungsfenster selbst - die VPN-Seite
    schreibt es nie (geprueft: kein SETTINGS_WRITER, kein
    settings.py-Aufruf in ags-vpn.template). Und `openVpnSettings()` ging
    ohne Kennung los.

    Um die Einstellungen von X zu sehen, musste X also `vpn.active` sein,
    und `vpn.active` wurde X nur, wenn man X im Einstellungsfenster
    gewaehlt UND gespeichert hatte. Wer von der VPN-Seite kam, sah immer
    die zuletzt gespeicherte Verbindung.

    Seit dem 01.09.2026 traegt `ags request vpn-settings:<kennung>` die
    angeklickte Verbindung hinueber (siehe `gewuenschteKennung` in
    ags-vpn-settings.template). Der Ring ist damit weg.

WARUM DIESE DATEI TROTZDEM EXISTIERT
    Weil "der Weg beruehrt weder nmcli noch vpn.py" bis heute eine
    FOLGERUNG aus dem Quelltext war und keine Messung. Genau so ist der
    Befund entstanden, den diese Aufgabe vorher widerlegt hat. Ein Satz
    ueber Nebenwirkungen, den niemand ausgefuehrt hat, ist eine
    Vermutung.

WAS GEMESSEN WIRD - DREI DINGE, VOR UND NACH DEM ANSEHEN
    1. user-settings.json, Byte fuer Byte. Ansehen darf nicht schreiben -
       weder `vpn.active` noch sonst etwas.
    2. Die Zustandsdatei $XDG_RUNTIME_DIR/vpn-active. An ihr haengen vier
       rechtelose Leser (siehe ags-vpn.template); sie ist das, was
       "welche Verbindung steht" auf dieser Maschine bedeutet.
    3. Die Aufrufe an `nmcli` und `swanctl`, mitgeschrieben von
       Attrappen, die VOR dem echten Programm im PATH stehen.

DIE AUFRUFLISTE IST LEER, UND DAS WAR NICHT DIE ERWARTUNG
    Ich hatte angenommen, sie koenne es nicht sein: das VPN-Schild der
    Leiste frage den Zustand im Takt ab, und `vpn.py --status` rufe dafuer
    lesend `nmcli`. GEMESSEN am 01.09.2026: kein einziger Aufruf.
    `--status` beantwortet den Normalfall aus der Zustandsdatei
    ($XDG_RUNTIME_DIR/vpn-active), ohne ein Programm zu starten.

    Zugesichert wird trotzdem BEIDES, und in dieser Reihenfolge: kein
    AENDERNDER Aufruf (die Aussage, um die es geht - sie bleibt richtig,
    auch wenn eine spaetere Fassung wieder lesend fragt), und darunter
    die schaerfere Zahl, wie sie heute ist. Welche Verben als aendernd
    gelten, steht unten in AENDERND - namentlich und vollzaehlig, damit
    die Zusicherung nicht an einem Muster haengt, das ein neues Verb
    uebersieht.

    Die erste Gegenprobe dieser Datei hat genau daran gehangen und ist
    fehlgeschlagen: sie verlangte, die Attrappen muessten mindestens
    einmal gerufen worden sein. Sie pruefte damit meine Annahme und nicht
    die Sache. Dass der eigene PATH ankommt, wird seither aus der
    Umgebung des laufenden Prozesses GELESEN.

SICHERHEIT
    Verschachtelter Compositor mit eigenem XDG_RUNTIME_DIR und eigenem
    Sitzungsbus. `nmcli` und `swanctl` sind Attrappen im PATH der
    Oberflaeche - selbst ein zustandsaendernder Aufruf koennte die
    Maschine also nicht erreichen; er wuerde nur aufgeschrieben und die
    Zusicherung rot machen. Die Verbindungen in der Einstellungsdatei
    sind erfunden und zeigen auf .invalid-Namen.
"""
from __future__ import annotations

import json
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
NACH_DEM_OEFFNEN = 8.0

SCHALE = "control"
FENSTER = "vpn-settings"

# Die Bildschirmgroesse des Nutzers - dieselbe wie in
# test_vpn_liste_platz.py, damit beide Laeufe dieselbe Oberflaeche
# meinen.
BREITE, HOEHE = 1920, 1200

# Die Verben, die den Zustand einer Verbindung AENDERN. Namentlich und
# nicht ueber ein Muster: ein Muster wie "alles ausser show" wuerde ein
# neues lesendes Unterkommando fuer eine Aenderung halten, und ein Muster
# wie "up|down" uebersieht `add`.
#
# nmcli:   connection up/down/add/modify/delete/clone/edit/import/load,
#          device connect/disconnect, radio ... on/off
# swanctl: --initiate, --terminate, --load-all, --load-conns
AENDERND = (
    ("connection", "up"), ("connection", "down"), ("connection", "add"),
    ("connection", "modify"), ("connection", "delete"),
    ("connection", "clone"), ("connection", "edit"),
    ("connection", "import"), ("connection", "load"),
    ("connection", "reload"),
    ("device", "connect"), ("device", "disconnect"),
    ("c", "up"), ("c", "down"), ("c", "add"), ("c", "modify"),
    ("c", "delete"),
)
AENDERNDE_FAHNEN = ("--initiate", "--terminate", "--load-all",
                    "--load-conns", "--load-creds")


def _attrappen(verzeichnis: Path, protokoll: Path) -> str:
    """`nmcli` und `swanctl`, die nichts tun und alles aufschreiben.

    Sie stehen VOR dem echten Programm im PATH. Damit kann kein Aufruf
    die Maschine erreichen, auf der die Suite laeuft - und was gerufen
    WURDE, steht hinterher im Protokoll.

    Rueckgabewert 0 und eine leere Ausgabe: `vpn.py --status` liest
    daraus "nichts steht", und genau das soll der Ausgangszustand sein.
    """
    verzeichnis.mkdir(parents=True, exist_ok=True)
    for name in ("nmcli", "swanctl"):
        datei = verzeichnis / name
        datei.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\t%s\\n" "{name}" "$*" >> "{protokoll}"\n'
            "exit 0\n", encoding="utf-8")
        datei.chmod(0o755)
    import os
    return os.pathsep.join([str(verzeichnis), os.environ.get("PATH", "/usr/bin")])


def _drei_verbindungen() -> str:
    """Drei erfundene Verbindungen, aus settings.defaults() gebaut.

    Nicht getippt: `schema_version` und die Feldnamen stehen damit an
    EINER Stelle. Dieselbe Begruendung wie in test_vpn_breite.py.
    """
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import settings
        dokument = settings.defaults()
        eintraege = []
        for kennung, name, art in (("c1", "arbeit", "ipsec"),
                                   ("c2", "zuhause", "wireguard"),
                                   ("c3", "reise", "openvpn")):
            eintrag = dict(settings.default_connection())
            eintrag.update({"id": kennung, "connection_name": name,
                            "kind": art})
            if art == "ipsec":
                eintrag["server"] = "gateway.example.invalid"
            eintraege.append(eintrag)
        # `active` zeigt auf die ERSTE - angesehen wird gleich die
        # ZWEITE. Waeren sie dieselbe, bewiese der Lauf nichts ueber die
        # Frage, ob Ansehen die Auswahl verschiebt.
        dokument["vpn"] = {"active": "c1", "connections": eintraege}
        return json.dumps(dokument, indent=2)
    finally:
        sys.path.remove(str(ROOT / "src"))


def _aufrufe(protokoll: Path) -> list[tuple[str, list[str]]]:
    if not protokoll.exists():
        return []
    gefunden = []
    for zeile in protokoll.read_text(encoding="utf-8").splitlines():
        name, _t, rest = zeile.partition("\t")
        gefunden.append((name, rest.split()))
    return gefunden


def _aendernde(aufrufe) -> list[str]:
    """Die Aufrufe, die etwas geaendert HAETTEN."""
    schlimm = []
    for name, argumente in aufrufe:
        if any(f in argumente for f in AENDERNDE_FAHNEN):
            schlimm.append(f"{name} {' '.join(argumente)}")
            continue
        for erstes, zweites in AENDERND:
            if erstes in argumente:
                stelle = argumente.index(erstes)
                if stelle + 1 < len(argumente) and argumente[stelle + 1] == zweites:
                    schlimm.append(f"{name} {' '.join(argumente)}")
                    break
    return schlimm


@pytest.fixture(scope="module")
def messung(tmp_path_factory) -> dict:
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Lauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zepvpn-ansehen")
    ags = render_configuration(bau)
    bundle(ags, bau)

    nutzer = bau / "zepos"
    nutzer.mkdir(parents=True, exist_ok=True)
    einstellungen = nutzer / "user-settings.json"
    einstellungen.write_text(_drei_verbindungen(), encoding="utf-8")

    protokoll = bau / "befehle.log"
    pfad = _attrappen(bau / "attrappen", protokoll)

    ergebnis: dict = {}
    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(BREITE // 2, HOEHE // 2)
        # Der eigene PATH - siehe Session.shell(). Ohne ihn traefe ein
        # `nmcli connection up` die Maschine des Entwicklers.
        prozess = sitzung.shell(bau / "zepos-shell.js", bau, PATH=pfad)
        # DASS DER EIGENE PATH ANGEKOMMEN IST, WIRD GELESEN UND NICHT
        # GEHOFFT - aus der Umgebung des laufenden Prozesses selbst.
        #
        #     Der erste Anlauf hat das anders geprueft: "die Attrappen
        #     muessen mindestens einmal gerufen worden sein". Diese
        #     Gegenprobe ist FEHLGESCHLAGEN, und zwar zu Recht - sie
        #     wurden kein einziges Mal gerufen. Die Annahme dahinter (das
        #     VPN-Schild der Leiste frage den Zustand im Takt ueber
        #     nmcli ab) war falsch: `vpn.py --status` beantwortet den
        #     Normalfall aus der Zustandsdatei, ohne ein Programm zu
        #     starten.
        #
        #     Eine leere Liste ist damit der ECHTE Befund und nicht der
        #     Verdacht, der PATH sei nicht angekommen - aber nur, wenn
        #     man den PATH unabhaengig davon nachweist. Genau das tut
        #     diese Zeile.
        try:
            roh = Path(f"/proc/{prozess.pid}/environ").read_bytes()
            ergebnis["pfad_der_schale"] = next(
                (z.split("=", 1)[1] for z in roh.decode(
                    "utf-8", "replace").split("\0") if z.startswith("PATH=")),
                "")
        except OSError as fehler:
            ergebnis["pfad_der_schale"] = f"nicht lesbar: {fehler}"
        ergebnis["attrappen"] = str(bau / "attrappen")
        time.sleep(SETTLE)

        # Aufwaermen: der allererste `ags request` einer Sitzung laesst
        # die Flaeche in einem Teil der Laeufe nicht erscheinen - siehe
        # den Kommentar dazu in test_vpn_breite.py.
        sitzung.request(SCHALE)
        frist = time.monotonic() + 45.0
        while time.monotonic() < frist:
            if sitzung.layers().get(SCHALE):
                break
            time.sleep(0.3)
        sitzung.request(SCHALE)
        time.sleep(2.0)

        # ---- VORHER ---------------------------------------------------
        laufzeit_datei = sitzung.runtime / "vpn-active"
        ergebnis["datei_vorher"] = einstellungen.read_bytes()
        ergebnis["zustand_vorher"] = (
            laufzeit_datei.read_bytes() if laufzeit_datei.exists() else None)
        ergebnis["aufrufe_vorher"] = len(_aufrufe(protokoll))

        # ---- ANSEHEN --------------------------------------------------
        # Die ZWEITE Verbindung, nicht die aktive. Genau der Weg, ueber
        # den der Nutzer geklagt hat: auf eine Verbindung gehen und ihre
        # Einstellungen sehen wollen.
        antwort = sitzung.request(f"{FENSTER}:c2")
        ergebnis["antwort"] = antwort
        frist = time.monotonic() + 45.0
        while time.monotonic() < frist:
            if sitzung.layers().get(FENSTER):
                break
            time.sleep(0.3)
        ergebnis["flaeche"] = sitzung.layers().get(FENSTER)
        time.sleep(NACH_DEM_OEFFNEN)

        # ---- NACHHER --------------------------------------------------
        ergebnis["datei_nachher"] = einstellungen.read_bytes()
        ergebnis["zustand_nachher"] = (
            laufzeit_datei.read_bytes() if laufzeit_datei.exists() else None)
        ergebnis["aufrufe"] = _aufrufe(protokoll)
        ergebnis["bild"] = sitzung.shoot(bau / "ansehen.png")
        ergebnis["protokoll"] = sitzung.read_shell_log()
    return ergebnis


def _bericht(messung: dict) -> str:
    return (f"Antwort: {messung.get('antwort')!r}\n"
            f"Flaeche: {messung.get('flaeche')}\n"
            "Befehle:\n"
            + "\n".join(f"  {n} {' '.join(a)}"
                        for n, a in messung.get("aufrufe", [])[:40])
            + "\nProtokoll:\n" + messung.get("protokoll", "")[-1500:])


def test_die_einstellungen_sind_ueberhaupt_aufgegangen(messung):
    """Die Gegenprobe zuerst.

    Jede Zusicherung darunter ist erfuellt, wenn NICHTS passiert ist -
    und nichts passiert auch, wenn das Fenster gar nicht aufgeht. Dann
    maesse dieser Lauf, dass ein Fenster, das niemand geoeffnet hat,
    nichts aendert.
    """
    assert "shown" in messung["antwort"] or "toggled" in messung["antwort"], (
        _bericht(messung))
    assert messung["flaeche"] is not None, (
        "keine Flaeche 'vpn-settings' nach `ags request vpn-settings:c2`:\n"
        + _bericht(messung))


def test_die_schale_laeuft_wirklich_mit_den_attrappen(messung):
    """Die zweite Gegenprobe: der eigene PATH ist angekommen.

    Ohne sie waere "kein aendernder Aufruf" auch dann wahr, wenn die
    Attrappen nie im Spiel waren - etwa weil `PATH` nicht durchgereicht
    wurde. Die Zusicherung darunter maesse dann nichts und waere
    trotzdem gruen.

    GELESEN AUS DER UMGEBUNG DES LAUFENDEN PROZESSES und nicht daran
    gemessen, ob eine Attrappe gerufen WURDE. Der erste Anlauf hat es
    andersherum versucht ("mindestens einmal gerufen") und ist
    fehlgeschlagen - zu Recht: sie wurden kein einziges Mal gerufen. Die
    Annahme dahinter war falsch, und eine Gegenprobe, die von einer
    falschen Annahme lebt, prueft die Annahme statt der Sache.
    """
    pfad = messung.get("pfad_der_schale", "")
    assert pfad.split(":")[0] == messung.get("attrappen"), (
        "der PATH der Oberflaeche beginnt nicht mit dem "
        f"Attrappenverzeichnis: {pfad!r}\n{_bericht(messung)}")


def test_ansehen_schreibt_die_einstellungen_nicht(messung):
    """user-settings.json, Byte fuer Byte.

    Das Fenster liest sie beim Aufgehen (`onShow` -> `loadSettings()`).
    LESEN darf es; schreiben nicht - `vpn.active` gehoert dem Speichern.
    Wuerde Ansehen die Auswahl verschieben, waere der Ring aus dem
    Dateikopf nur umgedreht statt aufgeloest.
    """
    assert messung["datei_nachher"] == messung["datei_vorher"], (
        "das blosse Ansehen hat user-settings.json veraendert:\n"
        + _bericht(messung))


def test_ansehen_ruehrt_die_zustandsdatei_nicht_an(messung):
    """$XDG_RUNTIME_DIR/vpn-active - was "steht gerade" bedeutet.

    An ihr haengen vier rechtelose Leser (siehe ags-vpn.template). Sie
    ist der kuerzeste Ausdruck dafuer, welche Verbindung aktiv ist.
    """
    assert messung["zustand_nachher"] == messung["zustand_vorher"], (
        "das blosse Ansehen hat die Zustandsdatei veraendert "
        f"({messung['zustand_vorher']!r} -> "
        f"{messung['zustand_nachher']!r}):\n{_bericht(messung)}")


def test_kein_einziger_zustandsaendernder_befehl(messung):
    """DIE Zusicherung dieser Datei, in ihrer scharfen Form.

    Ich hatte erwartet, die Liste koenne nicht leer sein - das VPN-Schild
    der Leiste frage den Zustand im Takt ab. GEMESSEN am 01.09.2026: sie
    IST leer. `vpn.py --status` beantwortet den Normalfall aus der
    Zustandsdatei ($XDG_RUNTIME_DIR/vpn-active), ohne ein Programm zu
    starten.

    Zugesichert wird deshalb beides, und in dieser Reihenfolge: KEIN
    aendernder Befehl (die Aussage, um die es geht - sie bleibt auch
    dann richtig, wenn eine spaetere Fassung wieder lesend fragt), und
    darunter die schaerfere Zahl, wie sie heute ist.
    """
    schlimm = _aendernde(messung["aufrufe"])
    assert schlimm == [], (
        "das blosse Ansehen einer Verbindung hat zustandsaendernde "
        f"Befehle abgesetzt: {schlimm}\n{_bericht(messung)}")
    assert messung["aufrufe"] == [], (
        "das Ansehen ruft inzwischen `nmcli` oder `swanctl` - lesend, "
        "aber es ruft. Das ist kein Fehler, solange die Zusicherung "
        "darueber haelt; die Zahl gehoert dann nachgezogen und der "
        f"Dateikopf mit ihr:\n{_bericht(messung)}")


def test_es_gibt_ein_bild_davon(messung):
    """Der Bildbeweis, in der Groesse des Nutzers."""
    bild = messung["bild"]
    assert bild.is_file() and bild.stat().st_size > 0, bild
    print(f"\nBildbeweis: {bild}")
