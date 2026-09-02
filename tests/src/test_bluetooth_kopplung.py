# SPDX-License-Identifier: GPL-3.0-or-later
"""Eine neue Maus koppeln - an einem laufenden Fenster gemessen.

WAS GEMELDET WURDE
    Der Nutzer, woertlich: "ausserdem habe ich irgendwie schwierigkeiten
    meine maus zu finden" und, auf die Rueckfrage, "nein ich finde per
    bluetooth meine maus nicht egal mache erstmal weiter mit dem rest".
    Er hat es zurueckgestellt; behoben war es nie.

WAS AN DER SEITE FEHLTE, UND ES IST NACHGEZAEHLT (02.09.2026)
    `grep -n "pair" src/templates/ags-bluetooth.template` fand acht
    Treffer, und KEINER davon war ein Aufruf:

        Zeile 211  `paired: boolean`          ein Feld
        Zeile 318  `bctl("devices Paired")`   eine Abfrage
        Zeile 341  `paired: gekoppelt.has()`  eine Zuweisung
        Zeile 602  `device.paired ? ...`      eine Beschriftung
        Zeile 648  "Connecting failed - is it paired?"
        Zeile 787  "Open Blueman - pairing, sending files"

    Das Fenster KONNTE also nichts koppeln. Der Klick auf ein gefundenes
    Geraet rief `bluetoothctl connect` - und `connect` auf ein Geraet,
    das nicht gekoppelt ist, schlaegt fehl. Was der Nutzer danach sah,
    war die Zeile "Connecting failed - is it paired?" und ein Verweis auf
    blueman. Eine neue Maus ist genau der Fall, den das nicht bedient:
    sie ist weder verbunden noch gekoppelt.

WARUM DIESE DATEI NEBEN test_bluetooth_pairing.py STEHT
    Die andere Datei prueft den AGENTEN, und sie prueft ihn als TEXT:
    `"RequestAuthorization" in code`, `'CAPABILITY = "KeyboardDisplay"'
    in code`. Das sind Zusicherungen darueber, welche Woerter in einer
    Vorlage stehen. Sie waeren alle gruen geblieben, waehrend das
    Fenster daneben nicht koppeln kann - und sie sind es gewesen.

    Hier wird deshalb das ERGEBNIS gemessen: ein echtes Fenster, eine
    echte Liste, ein echter Klick, und danach die Frage, welche Befehle
    dabei wirklich abgeschickt wurden.

WIE HIER GEMESSEN WIRD, OHNE DEN ADAPTER DES NUTZERS ANZUFASSEN
    `bluetoothctl` liegt im PATH dieses Laufs als Attrappe, und das
    Attrappenverzeichnis steht VORNE. Sie schreibt jeden Aufruf mit und
    antwortet aus einer Tabelle; der echte Adapter, der echte Dienst und
    die echten gekoppelten Geraete bleiben unberuehrt. `/usr/bin` bleibt
    im PATH, weil die Seite ihre Aufrufe als `timeout N bluetoothctl …`
    durch eine Shell schickt - `bash` und `timeout` kommen von dort.

    NICHT der Sitzungsbus des Nutzers: DBUS_SESSION_BUS_ADDRESS zeigt
    auf einen Pfad, den es nicht gibt. Dieselbe Vorkehrung wie in
    tests/src/test_vpn_schalter.py.

WAS DAMIT NICHT GEPRUEFT IST, und das gehoert dazu
    Ob eine ECHTE Maus sich koppelt. Das haengt am Funk, am Adapter und
    an der Maus, und keines der drei gibt es hier. Geprueft ist die eine
    Sache, die in unserer Hand liegt: dass das Fenster die richtigen
    Befehle in der richtigen Reihenfolge abschickt. Was der Nutzer
    zusaetzlich laufen lassen soll, steht im Bericht zu Aufgabe 84.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.gtk4_headless import broadwayd, start_broadwayd, stop_broadwayd
from tests.src.test_bar_headless import CHILD_TIMEOUT, _DISPLAYS

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
CHILD = Path(__file__).resolve().parent / "bluetooth_kopplung_child.tsx"

pytestmark = pytest.mark.allow_subprocess

# Nur, was das Kind wirklich braucht. ags-bluetooth.template holt `_`
# und `format` aus utils/i18n und sieben Bauteile aus utils/kit; die
# ShellSeite ist ein `import type` und verschwindet beim Uebersetzen,
# also muss utils/overlay hier NICHT erzeugt werden.
RENDERED = {
    "templates/ags-i18n.template": "utils/i18n.ts",
    "templates/ags-kit.template": "utils/kit.ts",
    "templates/ags-bluetooth.template": "widget/BluetoothManager.tsx",
}

# Die zwei Geraete, und der Unterschied zwischen ihnen IST die Messung.
#
# Die Maus ist in `devices` und in KEINER der beiden Filterlisten - also
# gefunden, nicht gekoppelt, nicht verbunden. Genau der Zustand, in dem
# eine frisch eingeschaltete Maus steht, und genau der, den die Seite
# nicht bedienen konnte.
MAUS = "ZepMouse M1"
MAUS_ADRESSE = "AA:BB:CC:DD:EE:01"

# Der Kopfhoerer ist gekoppelt, aber nicht verbunden. Er steht hier fuer
# die Gegenrichtung: bei ihm waere ein `pair` falsch - er ist schon
# gekoppelt, und ein zweites Koppeln ist ein Fehler, nicht eine
# Vorsichtsmassnahme.
HOERER = "ZepPhones"
HOERER_ADRESSE = "AA:BB:CC:DD:EE:02"

# Die Attrappe. Ein Skript und kein Mock-Objekt, weil der Pruefling eine
# Schale ist: er ruft `timeout N bluetoothctl <worte>` und liest die
# Ausgabe zeilenweise. Ein Objekt haette die eine Schnittstelle
# nachgebaut, die hier gerade nicht gemessen werden soll.
#
# JEDER AUFRUF WIRD MITGESCHRIEBEN, und das ist der Messwert. Der
# Unterschied zwischen "hat nicht gekoppelt" und "hat es versucht und es
# ging schief" ist genau der, um den es geht.
#
# EINGESETZT WIRD MIT .replace() UND NICHT MIT `%`, und das ist ein
# gemessener Fehler von heute: mit `% {...}` verschluckte Python das
# `%s` in `printf '%s\\n'` als eigene Einsetzung. Das Protokoll fuellte
# sich daraufhin mit `{maus: ZepMouse{maus: ...`, verben() fand nichts,
# und ZWEI Zusicherungen waren rot, ohne dass am Pruefling etwas falsch
# gewesen waere. Ein Messgeraet, das sich selbst zerschreibt, meldet
# Fehler, die es nicht gibt.
ATTRAPPE = """\
#!/bin/bash
printf '%s\\n' "$*" >> "$BT_PROTOKOLL"
case "$*" in
    show)
        echo "Controller AA:BB:CC:00:00:FF (public)"
        echo "        Name: ZepTest"
        echo "        Powered: yes"
        echo "        Discoverable: no"
        echo "        Pairable: yes"
        ;;
    "devices Connected")
        ;;
    "devices Paired")
        echo "Device @HOERER_ADR@ @HOERER@"
        ;;
    devices)
        echo "Device @MAUS_ADR@ @MAUS@"
        echo "Device @HOERER_ADR@ @HOERER@"
        ;;
    pair*)
        echo "Attempting to pair with ${*##* }"
        echo "Pairing successful"
        ;;
    trust*)
        echo "Changing ${*##* } trust succeeded"
        ;;
    connect*)
        echo "Attempting to connect to ${*##* }"
        echo "Connection successful"
        ;;
    *scan*)
        echo "Discovery started"
        ;;
esac
exit 0
""".replace("@MAUS_ADR@", MAUS_ADRESSE).replace("@MAUS@", MAUS) \
   .replace("@HOERER_ADR@", HOERER_ADRESSE).replace("@HOERER@", HOERER)


# Die Bedingung, unter der ueberhaupt gekoppelt wird - WOERTLICH aus
# ags-bluetooth.template. Die Gegenprobe stellt sie auf `false` und
# legt damit den GANZEN Kopplungszweig still.
#
# WARUM DIE BEDINGUNG UND NICHT DER `pair`-AUFRUF
#     Zuerst schnitt diese Gegenprobe nur die zwei Zeilen mit `pair`
#     heraus. Gemessen kam dabei `trust`, `connect` heraus - ein
#     Zustand, den es nie gegeben hat. Eine Gegenprobe soll den ALTEN
#     Zustand herstellen und nicht einen dritten: mit `if (false)`
#     bleibt genau der Weg uebrig, den die Seite bis zum 02.09.2026
#     nahm, `connect` und sonst nichts.
#
# Sie steht hier als Text und nicht als Muster, damit die Gegenprobe
# LAUT scheitert, sobald jemand die Vorlage an dieser Stelle
# umschreibt: ein Muster, das nichts mehr findet, entfernte
# stillschweigend nichts, und die Gegenprobe waere gruen, ohne etwas
# ausgebaut zu haben. Dieselbe Vorkehrung wie bei SCHALTER_ZEILE in
# tests/src/test_vpn_schalter.py - und die hat sich dort schon bewaehrt.
KOPPEL_BEDINGUNG = "              if (!device.paired) {"
KOPPEL_STILLGELEGT = "              if (false) {"

# Und dasselbe fuer die Suche. Es sind ZWEI Stellen, und dass es zwei
# sind, hat diese Gegenprobe herausgebracht.
#
# ZUERST STAND HIER NUR DER `map`-RUECKRUF, und die Gegenprobe fiel aus:
# gesucht wurde trotzdem, `--timeout 10 scan on` stand im Protokoll. Der
# Grund ist `notify::visible` - das Kind ruft `window.present()`, damit
# wird das Fenster sichtbar, und dieser zweite Rueckruf stoesst
# denselben Suchlauf an. Eine Annahme von mir, die falsch war, und die
# Gegenprobe war das, was sie widerlegt hat.
#
# UND DER TAKT MUSSTE DOCH MIT HEREIN, und auch das hat die Gegenprobe
# herausgebracht. Mit den zwei Schnitten unten allein stand immer noch
# genau EIN `--timeout 10 scan on` im Protokoll, obwohl dieser Lauf nach
# 2,4 s vorbei ist und UPDATE_INTERVAL bei 5000 ms steht.
#
# Der Grund ist Astals `interval` aus ags/time: es ruft seinen Rueckruf
# SOFORT und danach im Takt. GEMESSEN so - mit dem dritten Schnitt sind
# es null Suchlaeufe, ohne ihn einer. Das ist zugleich der Beleg, dass
# der Takt allein die Suche beim Aufschlagen schon traegt; die zwei
# anderen Stellen decken den SEITENWECHSEL ab, den er nicht sieht.
SUCHE_SCHNITTE = (
    ("    interval(UPDATE_INTERVAL, () => {\n"
     "      if (win.visible && istAktiv()) {\n"
     "        updateDisplay()\n"
     "        void sucheAnstossen(false)\n"
     "      }\n"
     "    })",
     "    interval(UPDATE_INTERVAL, () => {\n"
     "      if (win.visible && istAktiv()) { updateDisplay() }\n"
     "    })"),
    ('    container.connect("map", () => {\n'
     "      updateDisplay()\n"
     "      void sucheAnstossen(false)\n"
     "    })",
     '    container.connect("map", () => { updateDisplay() })'),
    ('    win.connect("notify::visible", () => {\n'
     "      if (win.visible && istAktiv()) {\n"
     "        updateDisplay()\n"
     "        void sucheAnstossen(false)\n"
     "      }\n"
     "    })",
     '    win.connect("notify::visible", () => {\n'
     "      if (win.visible && istAktiv()) { updateDisplay() }\n"
     "    })"),
)


def _render(target: Path) -> None:
    """Die drei Vorlagen, uebersetzt wie der Generator sie uebersetzt."""
    sys.path.insert(0, str(SRC))
    try:
        import template_processor
        prozessor = template_processor.ConfigProcessor(
            paths={"ZEPOS_SYSTEM_ROOT": str(SRC)})
        for vorlage, ausgabe in RENDERED.items():
            ziel = target / ausgabe
            ziel.parent.mkdir(parents=True, exist_ok=True)
            prozessor.apply_template(SRC / vorlage, ziel)
    finally:
        sys.path.remove(str(SRC))


class Lauf:
    """Was ein Lauf hinterlassen hat - dieselbe Form wie Lauf in
    tests/src/test_vpn_schalter.py, plus das Befehlsprotokoll."""

    def __init__(self, returncode: int, stdout: str, stderr: str,
                 spur: str, befehle: list[str]) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.spur = spur
        self.befehle = befehle

    def marke(self, name: str) -> str:
        treffer = [zeile for zeile in self.spur.splitlines()
                   if zeile.startswith(name + ":")]
        assert treffer, f"keine Marke {name} in der Spur:\n{self.bericht}"
        return treffer[0].split(":", 1)[1]

    def zeilen(self, name: str) -> list[list[str]]:
        roh = self.marke(name)
        return [eintrag.split("|") for eintrag in roh.split(";") if eintrag]

    def verben(self) -> list[str]:
        """Nur die ZUSTANDSAENDERNDEN Aufrufe, in ihrer Reihenfolge.

        Die Abfragen (`show`, `devices …`) fallen heraus: sie laufen im
        Takt der Seite und ihre Zahl haengt daran, wie lange dieser Lauf
        gedauert hat. Was gemessen werden soll, ist die Kette, die EIN
        Klick ausloest.
        """
        return [zeile for zeile in self.befehle
                if zeile.split(" ", 1)[0] in ("pair", "trust", "connect",
                                              "disconnect", "remove")]

    @property
    def bericht(self) -> str:
        return (f"rueckgabewert: {self.returncode}\n"
                f"stdout: {self.stdout!r}\nstderr:\n{self.stderr}\n"
                f"spur:\n{self.spur}\n"
                f"bluetoothctl-aufrufe:\n  " + "\n  ".join(self.befehle))


def _lauf(wurzel: Path, ziel: str,
          schnitte: tuple[tuple[str, str], ...] = ()) -> Lauf:
    """Ein Fenster, ein Klick auf die Zeile `ziel`, und das Protokoll.

    `schnitte` ist die Gegenprobe: Paare (suchen, ersetzen), die in der
    ERZEUGTEN BluetoothManager.tsx angewandt werden, bevor sie
    uebersetzt wird. Findet ein `suchen` sich nicht, bricht der Lauf ab -
    eine Gegenprobe, die nichts ausbaut, bewiese nichts.

    MEHRERE und nicht eines: eine Gegenprobe brauchte zwei Schnitte, und
    dass sie zwei braucht, hat sie selbst herausgebracht (siehe
    SUCHE_SCHNITTE).
    """
    if shutil.which("ags") is None:
        pytest.skip("ags fehlt; es kommt mit dem Paket aylurs-gtk-shell")
    server_befehl = broadwayd()
    if server_befehl is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    ags = wurzel / "ags"
    ags.mkdir()
    _render(ags)

    if schnitte:
        seite = ags / RENDERED["templates/ags-bluetooth.template"]
        code = seite.read_text(encoding="utf-8")
        for suchen, ersetzen in schnitte:
            assert suchen in code, (
                "die Stelle, die diese Gegenprobe ausbaut, steht nicht mehr "
                "so in der erzeugten BluetoothManager.tsx:\n"
                f"{suchen!r}\n"
                "Ohne Treffer baut die Gegenprobe nichts aus und bewiese "
                "nichts. Den Schnitt nachziehen.")
            code = code.replace(suchen, ersetzen)
        seite.write_text(code, encoding="utf-8")

    # Die Attrappe, VORNE im PATH.
    stube = wurzel / "bin"
    stube.mkdir()
    falsch = stube / "bluetoothctl"
    falsch.write_text(ATTRAPPE, encoding="utf-8")
    falsch.chmod(0o755)
    protokoll = wurzel / "aufrufe.txt"
    protokoll.write_text("", encoding="utf-8")

    shutil.copy(CHILD, ags / "child.tsx")
    buendel = wurzel / "child.js"
    ergebnis = subprocess.run(
        ["ags", "bundle", str(ags / "child.tsx"), str(buendel),
         "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=300)
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat die Bluetooth-Seite nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)

    laufzeit = wurzel / "run"
    laufzeit.mkdir()
    # GLib lehnt ein weltlesbares XDG_RUNTIME_DIR ab und sagt es auf
    # stderr.
    laufzeit.chmod(0o700)
    spur = wurzel / "spur"
    nummer = next(_DISPLAYS)
    server, _socket = start_broadwayd(server_befehl, laufzeit, nummer)
    try:
        gelaufen = subprocess.run(
            [str(buendel)],
            env={
                # Die Attrappe VORNE. /usr/bin bleibt hinten, weil die
                # Seite `bash -c "timeout N bluetoothctl …"` ruft.
                "PATH": f"{stube}:/usr/bin:/bin",
                "HOME": str(wurzel),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{nummer}",
                "XDG_RUNTIME_DIR": str(laufzeit),
                "XDG_CONFIG_HOME": str(wurzel / "config"),
                # NIE der Bus des Nutzers.
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={wurzel}/kein-bus",
                # Damit `_` die englischen msgid zurueckgibt und die
                # Erwartungen unten nicht an der Sprache dieser Maschine
                # haengen.
                "LC_ALL": "C",
                "LANG": "C",
                "ZEPOS_TRACE": str(spur),
                "ZEPOS_ZIEL": ziel,
                "BT_PROTOKOLL": str(protokoll),
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT)
    finally:
        stop_broadwayd(server)

    return Lauf(gelaufen.returncode, gelaufen.stdout, gelaufen.stderr,
                spur.read_text() if spur.exists() else "",
                [z for z in protokoll.read_text(encoding="utf-8").splitlines()
                 if z])


@pytest.fixture(scope="module")
def maus(tmp_path_factory) -> Lauf:
    """Ein Klick auf die gefundene, nicht gekoppelte Maus.

    Modulweit, weil `ags bundle` und der Anzeigeserver zusammen mehrere
    Sekunden brauchen und mehrere Zusicherungen dieselbe Messung lesen.
    """
    return _lauf(tmp_path_factory.mktemp("bt-maus"), MAUS)


@pytest.fixture(scope="module")
def hoerer(tmp_path_factory) -> Lauf:
    """Ein Klick auf den schon gekoppelten Kopfhoerer."""
    return _lauf(tmp_path_factory.mktemp("bt-hoerer"), HOERER)


def test_die_liste_zeigt_das_nicht_gekoppelte_geraet(maus):
    """Die Maus steht in der Liste, und ihr Zustand steht daneben.

    Das ist der Ausgangspunkt und war nie kaputt: `bluetoothctl devices`
    ohne Filter meldet auch Geraete, die weder gekoppelt noch verbunden
    sind. Diese Zusicherung steht zuerst, weil sie den naechstliegenden
    Verdacht ausraeumt - die Seite zeigt NICHT nur `Paired`.
    """
    assert maus.marke("liste") == "da", maus.bericht
    titel = [zeile[0] for zeile in maus.zeilen("zeilen-vorher")]
    assert MAUS in titel, maus.bericht
    assert HOERER in titel, maus.bericht


def test_die_zeile_der_maus_ist_ueberhaupt_anklickbar(maus):
    """Ohne diese Zusicherung messen die beiden darunter nichts.

    Ein Klick, der auf keine Huelle traf, hinterliesse ein leeres
    Protokoll - und "keine Kopplung" waere von "kein Knopf" nicht zu
    unterscheiden.
    """
    assert maus.marke("geklickt") == MAUS, maus.bericht
    klickbar = {zeile[0]: zeile[2] for zeile in maus.zeilen("zeilen-vorher")}
    assert klickbar.get(MAUS) == "klickbar", maus.bericht


def test_ein_klick_auf_die_maus_koppelt_sie_bevor_er_verbindet(maus):
    """DIE Zusicherung dieser Datei.

    Die Kette, die BlueZ fuer ein neues Geraet verlangt, ist
    `pair` → `trust` → `connect`, und in dieser Reihenfolge:

      pair     die Kopplung selbst. Hier kommt der Agent ins Spiel
               (ags-bluetooth-agent.template); ohne diesen Aufruf wird
               er nie gefragt.
      trust    damit die Maus sich SPAETER von selbst wieder verbindet.
               Ohne trust muesste man nach jedem Neustart von Hand
               verbinden - fuer ein Zeigegeraet ist das derselbe Mangel
               noch einmal.
      connect  erst danach, und erst danach kann es klappen.

    Vor dem 02.09.2026 stand hier nur `connect`, und die Seite konnte
    kein Geraet koppeln.
    """
    verben = maus.verben()
    assert verben == [
        f"pair {MAUS_ADRESSE}",
        f"trust {MAUS_ADRESSE}",
        f"connect {MAUS_ADRESSE}",
    ], maus.bericht


def test_die_seite_sucht_von_selbst_ohne_dass_jemand_den_knopf_findet(maus):
    """Gesucht werden muss, ohne dass der Nutzer erst einen Knopf sucht.

    WAS VORHER WAR, UND ES IST NACHGEZAEHLT (02.09.2026)
        `bluetoothctl scan on` lief AUSSCHLIESSLICH im Rueckruf des
        Suchknopfes, zehn Sekunden lang. Wer die Seite oeffnete, bekam
        eine Liste aus der Datenbank von BlueZ und keinen einzigen
        Suchlauf. Im Protokoll dieses Laufs stand vor der Aenderung
        kein `scan`.

    WARUM DAS FUER EINE MAUS DER UNTERSCHIED IST
        Eine Maus funkt nur, waehrend sie im Kopplungsmodus ist - man
        haelt dafuer einen Knopf an ihrer Unterseite. Mit einem
        Suchlauf, der zehn Sekunden ab Knopfdruck laeuft, muss der
        Nutzer BEIDES gleichzeitig treffen: den Knopf im Fenster und
        den Knopf an der Maus. Trifft er es nicht, erscheint sie nie -
        und genau das hat er gemeldet ("ich finde per bluetooth meine
        maus nicht").

        Solange die Seite offen ist, wird jetzt gesucht. Das ist die
        Bedingung, die der Nutzer selbst steuert, und dieselbe, die
        blueman und die GNOME-Einstellungen benutzen.

    Der Knopf bleibt trotzdem: er ist der Weg, einen Suchlauf SOFORT
    anzustossen, statt auf den naechsten Takt zu warten.
    """
    scans = [zeile for zeile in maus.befehle if "scan" in zeile]
    assert scans, (
        "die Seite hat in diesem ganzen Lauf keinen einzigen Suchlauf "
        "gestartet - ein Geraet, das erst jetzt eingeschaltet wird, "
        "erscheint dann nie:\n" + maus.bericht)


def test_ohne_den_anstoss_beim_aufschlagen_wird_nicht_gesucht(
        tmp_path_factory):
    """Die zweite Gegenprobe - fuer die Suche.

    Sie stellt den Zustand von VOR dem 02.09.2026 her: der
    `map`-Rueckruf liest nur noch die Liste und stoesst keinen Suchlauf
    an. Uebrig bleibt genau das, was der Nutzer hatte - eine Seite, die
    die Datenbank von BlueZ zeigt und nicht funkt.

    Ohne diesen Lauf waere die Zusicherung darueber von einer
    Zusicherung, die immer gruen ist, nicht zu unterscheiden.
    """
    lauf = _lauf(tmp_path_factory.mktemp("bt-ohne-suche"), MAUS,
                 schnitte=SUCHE_SCHNITTE)

    # Die Liste muss trotzdem stehen, sonst maesse dieser Lauf nur, dass
    # ein zerschnittenes Fenster nichts tut.
    assert lauf.marke("liste") == "da", lauf.bericht
    assert [zeile for zeile in lauf.befehle if "scan" in zeile] == [], (
        "es wurde gesucht, obwohl der Anstoss ausgebaut ist - dann misst "
        "die Zusicherung darueber etwas anderes als diese Stelle:\n"
        + lauf.bericht)


def test_ohne_den_koppelaufruf_bleibt_genau_der_alte_zustand_uebrig(
        tmp_path_factory):
    """DIE GEGENPROBE, und ohne sie waere die Zusicherung darueber wertlos.

    WARUM SIE DA IST
        Eine Zusicherung, die nicht umschlagen kann, misst nichts. In
        diesem Auftragsbuendel sind an einem Tag ACHT Pruefstellen
        aufgefallen, die gruen waren und nichts gemessen haben - dieser
        Lauf ist der Beleg, dass diese hier nicht die neunte ist.

    WAS SIE HERSTELLT
        Genau den Zustand von VOR dem 02.09.2026: die Bedingung, unter
        der gekoppelt wird, steht in der ERZEUGTEN BluetoothManager.tsx
        auf `false`, bevor sie uebersetzt wird. Uebrig bleibt der Weg,
        den die Seite damals nahm.

        GEMESSEN, und es ist genau das, was am 02.09.2026 als roter
        Test dastand: ein Klick auf die gefundene Maus schickte GENAU
        EINEN zustandsaendernden Befehl, `connect`. Kein `pair`, kein
        `trust`.

        Findet der Schnitt seine Stelle nicht mehr, bricht der Lauf mit
        eigenem Text ab - eine Gegenprobe, die nichts ausbaut, waere
        gruen, ohne etwas bewiesen zu haben.
    """
    lauf = _lauf(tmp_path_factory.mktemp("bt-gegenprobe"), MAUS,
                 schnitte=((KOPPEL_BEDINGUNG, KOPPEL_STILLGELEGT),))

    # Der Klick muss trotzdem gelandet sein, sonst maesse dieser Lauf
    # nur, dass ein zerschnittenes Fenster nichts tut.
    assert lauf.marke("geklickt") == MAUS, lauf.bericht
    assert lauf.verben() == [f"connect {MAUS_ADRESSE}"], lauf.bericht


def test_ein_schon_gekoppeltes_geraet_wird_nicht_neu_gekoppelt(hoerer):
    """Die Gegenrichtung, und sie ist keine Formsache.

    Ein `pair` auf ein Geraet, das schon gekoppelt ist, antwortet
    "Already paired" und ist ein Fehlschlag - eine Seite, die vor JEDEM
    Verbinden koppelt, haette die Zusicherung darueber bestanden und
    dabei jeden Kopfhoerer unbrauchbar gemacht.
    """
    assert hoerer.marke("geklickt") == HOERER, hoerer.bericht
    assert hoerer.verben() == [f"connect {HOERER_ADRESSE}"], hoerer.bericht
