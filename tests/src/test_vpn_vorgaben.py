# SPDX-License-Identifier: GPL-3.0-or-later
"""EINE Vorgabentabelle fuer eine VPN-Verbindung, und was sie zusichert.

WAS HIER BEWACHT WIRD
    Bis zum 01.09.2026 fuehrte dieser Baum die Vorgaben EINER
    VPN-Verbindung an vier Stellen:

        src/settings.py::default_connection()      9 oben, 35 Blatt
        src/user_settings.py::DEFAULT_CONNECTION  15 oben, 52 Blatt
        src/style_definition.py                   27 Aufrufe mit
                                                  eingetipptem Vorgabewert
        src/vpn.py                                11 Modulkonstanten

    GEMESSEN am 01.09.2026 durch Vergleich der vier Mengen. Die WERTE
    stimmten ueberall ueberein - die Tabellen waren verschieden LANG.
    Siebzehn Blattschluessel (`username`, `remember_username`,
    `xauth_enabled`, `debug`, `phase1.*`, `phase2.*`) standen nur in
    user_settings.py.

    Was das kostete, stand seit dem 21.08.2026 als Satz in
    tests/src/test_vpn_wireguard.py und war nie gemessen worden: "sonst
    lehnt `zepos-settings set` einen Pfad ab, den das Fenster daneben
    schreibt." Genau das tat es - test_die_befehlszeile_erreicht_jeden_
    schluessel_der_vorgabe unten haelt es fest.

WARUM DIESE TESTS AUSFUEHREN UND NICHT LESEN
    Eine Zusicherung, die den Quelltext durchsucht, ist gruen, sobald
    jemand die Schreibweise aendert. Die Tests hier RUFEN jeden der vier
    Wege auf und vergleichen, was herauskommt. Nur der letzte
    (test_es_gibt_keine_zweite_vorgabentabelle) sieht in den Quelltext,
    und er steht NEBEN den ausfuehrenden, nicht an ihrer Stelle: eine
    neu aufgemachte zweite Tabelle faellt sonst erst auf, wenn sich ihre
    Werte irgendwann unterscheiden.
"""
import ast
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def blattwege(abschnitt, prefix=""):
    """Jeder Blattschluessel als gepunkteter Weg.

    `dns.servers` und nicht `dns`: die Getter dieses Baums nehmen
    gepunktete Wege, und ein Test, der nur die oberste Ebene durchgeht,
    haette die dreizehn phase1/phase2-Werte nie angefasst.
    """
    for schluessel, wert in abschnitt.items():
        weg = f"{prefix}{schluessel}"
        if isinstance(wert, dict):
            yield from blattwege(wert, weg + ".")
        else:
            yield weg


def hole(abschnitt, weg):
    """Den Wert an einem gepunkteten Weg."""
    wert = abschnitt
    for teil in weg.split("."):
        wert = wert[teil]
    return wert


@pytest.fixture
def vorgabe():
    from src.settings import default_connection

    return default_connection()


# --------------------------------------------------------------------
# 1. Der Fehler, der diese Aufgabe ausgeloest hat
# --------------------------------------------------------------------

def test_ein_gesetzter_wert_erreicht_die_leser(tmp_path, monkeypatch, capsys):
    """`set vpn.server` auf einer FRISCHEN Installation, und wer ihn sieht.

    GEMESSEN am 01.09.2026, frisches ZEPOS_USER_ROOT ohne Datei:

        zepos-settings set vpn.server gw.example.org   -> 0
        zepos-settings get vpn.server                  -> gw.example.org
        vpn.connection(load())                         -> {}
        user_settings.get_vpn_setting("server")        -> ""

    Also derselbe Schluessel mit ZWEI Antworten, je nachdem wer fragt.
    Die Befehlszeile schrieb `server` als Geschwister von `active` und
    `connections` IN DEN ABSCHNITT - und der Abschnitt ist seit dem
    22.08.2026 keine Verbindung mehr, sondern eine Liste von
    Verbindungen. Gelesen hat den Wert danach niemand ausser der
    Befehlszeile selbst.

    Das ist die leiseste Art zu scheitern, die dieses Programm hat, und
    _unknown() in src/cli.py warnt woertlich davor: "der Nutzer aenderte
    eine Einstellung, der Befehl sagte 'gespeichert', und an der
    Maschine aenderte sich nichts". Hier tat es das trotzdem - der
    Rueckfall auf default_connection() liess die PRUEFUNG durchgehen und
    leitete den SCHREIBWEG nicht mit um.

    Der Test misst den Weg bis zu dem, der ihn benutzt, und nicht bis
    zur Datei: `get` liest denselben verlegten Wert zurueck und war
    damit gruen, waehrend der Tunnel ohne Server dastand.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import cli
    import settings
    import vpn

    assert cli.settings_command(["set", "vpn.server", "gw.example.org"]) == 0
    capsys.readouterr()

    dokument = settings.load()

    # DER LESER UND NICHT DIE DATEI. Jeder Verbraucher - der Erzeuger,
    # das Verbindungsskript, das Fenster - geht ueber vpn.connection().
    gewaehlt = vpn.connection(dokument)
    assert gewaehlt.get("server") == "gw.example.org", (
        "der geschriebene Server erreicht die gewaehlte Verbindung nicht: "
        f"{json.dumps(dokument.get('vpn'))}"
    )

    # Und die Verbindung, die dabei entsteht, ist eine RICHTIGE: sie
    # traegt eine Kennung, und `active` zeigt auf sie. Ohne beides
    # faende der Schalter sie beim naechsten Lesen nicht wieder.
    assert gewaehlt.get("id")
    assert dokument["vpn"]["active"] == gewaehlt["id"]


def test_der_zweite_schluessel_landet_in_derselben_verbindung(
        tmp_path, monkeypatch, capsys):
    """Zwei `set` hintereinander ergeben EINE Verbindung, nicht zwei.

    Ein Anlegen, das bei jedem Schreiben eine neue Verbindung erzeugt,
    haette den Fehler oben durch einen lauteren ersetzt: der Nutzer
    setzt Server und Netz und hat danach zwei halbe Zugaenge, von denen
    der gewaehlte je zur Haelfte ausgefuellt ist.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import cli
    import settings
    import vpn

    assert cli.settings_command(["set", "vpn.server", "gw.example.org"]) == 0
    assert cli.settings_command(["set", "vpn.connection_name", "buero"]) == 0
    capsys.readouterr()

    dokument = settings.load()
    assert len(dokument["vpn"]["connections"]) == 1
    gewaehlt = vpn.connection(dokument)
    assert gewaehlt["server"] == "gw.example.org"
    assert gewaehlt["connection_name"] == "buero"


# --------------------------------------------------------------------
# 2. Die Tabelle ist vollstaendig, und die Befehlszeile erreicht sie
# --------------------------------------------------------------------

def test_die_befehlszeile_erreicht_jeden_schluessel_der_vorgabe(
        tmp_path, monkeypatch, capsys, vorgabe):
    """Jeder Blattschluessel der Vorgabe ist von `set` aus erreichbar.

    src/cli.py prueft einen Pfad gegen settings.default_connection().
    Steht ein Schluessel dort nicht, antwortet `set` "no such setting" -
    und zwar fuer einen Schluessel, den das Einstellungsfenster daneben
    ohne Weiteres schreibt.

    GEMESSEN am 01.09.2026, vor der Zusammenlegung: siebzehn von
    zweiundfuenfzig Blattschluesseln wurden abgelehnt -

        vpn.username  vpn.remember_username  vpn.xauth_enabled
        vpn.debug     vpn.phase1.* (8)       vpn.phase2.* (5)

    Der Test geht die Tabelle durch statt eine eigene Liste zu fuehren:
    eine getippte Liste waere die naechste Menge, die veraltet.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import cli

    abgelehnt = []
    for weg in blattwege(vorgabe):
        # Der WERT ist hier gleichgueltig - geprueft wird, ob der Pfad
        # ueberhaupt als Einstellung gilt. Ein Text geht durch jede
        # Umwandlung, die _set() kennt.
        if cli.settings_command(["set", f"vpn.{weg}", "1"]) != 0:
            abgelehnt.append(weg)
    capsys.readouterr()

    assert abgelehnt == [], (
        "diese Schluessel der Vorgabentabelle lehnt `zepos-settings set` "
        f"ab: {abgelehnt}"
    )


# --------------------------------------------------------------------
# 3. Alle vier Wege antworten aus derselben Tabelle
# --------------------------------------------------------------------

def test_user_settings_faellt_auf_die_eine_vorgabe_zurueck(
        tmp_path, monkeypatch, vorgabe):
    """`get_vpn_setting()` ohne Datei antwortet die Vorgabentabelle.

    Ausgefuehrt und nicht gelesen: der Rueckfall in
    src/user_settings.py sucht den Wert selbst aus einer Tabelle
    heraus, und ob das DIESELBE Tabelle ist, sieht man nur an der
    Antwort.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import user_settings

    abweichungen = {}
    for weg in blattwege(vorgabe):
        erwartet = hole(vorgabe, weg)
        bekommen = user_settings.get_vpn_setting(weg)
        if bekommen != erwartet:
            abweichungen[weg] = (erwartet, bekommen)

    assert abweichungen == {}


def test_der_erzeuger_faellt_auf_die_eine_vorgabe_zurueck(
        tmp_path, monkeypatch, vorgabe):
    """`get_user_vpn_setting()` ohne Datei antwortet die Vorgabentabelle.

    src/style_definition.py trug bis zum 01.09.2026 an jeder der
    siebenundzwanzig Aufrufstellen den Vorgabewert EINGETIPPT im Aufruf.
    Das war die dritte Menge, und sie war die gefaehrlichste: sie stand
    nicht als Tabelle da, die jemand haette vergleichen koennen, sondern
    verteilt ueber zwei Bildschirmseiten.

    Der Erzeuger liest seine Einstellungen beim Import (USER_SETTINGS),
    also muss das Modul NACH dem Umbiegen von ZEPOS_USER_ROOT neu
    geladen werden - sonst antwortet hier die Datei des Entwicklers.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import style_definition

    style_definition = importlib.reload(style_definition)

    abweichungen = {}
    for weg in blattwege(vorgabe):
        erwartet = hole(vorgabe, weg)
        bekommen = style_definition.get_user_vpn_setting(weg)
        if bekommen != erwartet:
            abweichungen[weg] = (erwartet, bekommen)

    assert abweichungen == {}


def test_das_verbindungsskript_stimmt_auf_die_eine_vorgabe(
        tmp_path, monkeypatch, vorgabe):
    """Die Tuning-Konstanten in src/vpn.py sind die der Tabelle.

    src/vpn.py schreibt swanctl.conf und fuehrte dafuer elf eigene
    Konstanten. Sie sind TEXT ("43200", "2", "yes"), weil swanctl.conf
    Text ist, waehrend die Tabelle Zahlen und Wahrheitswerte traegt -
    verglichen wird darum in der Schreibweise, die swanctl sieht.

    Der Kopf von src/vpn.py nannte den Grund schon vor dieser Aufgabe:
    "A THIRD default would be one more thing that has to be kept in
    step, and the one place it would show up is a tunnel that negotiates
    something other than what the settings dialog displays."
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import vpn

    phase1 = vorgabe["phase1"]
    phase2 = vorgabe["phase2"]

    assert vpn.IKE_VERSION == str(phase1["version"])
    assert vpn.PROPOSALS == phase1["proposals"]
    assert vpn.KEYLIFE == str(phase1["keylife"])
    assert vpn.DPD_DELAY == str(phase1["dpd_delay"])
    assert vpn.DPD_TIMEOUT == str(phase1["dpd_timeout"])
    assert vpn.ENCAP == ("yes" if phase1["encap"] else "no")
    assert vpn.MOBIKE == ("yes" if phase1["mobike"] else "no")

    assert vpn.REKEY_TIME == str(phase2["rekey_time"])
    assert vpn.LIFE_TIME == str(phase2["life_time"])
    assert vpn.MODE == phase2["mode"]
    assert vpn.REPLAY_WINDOW == str(phase2["replay_window"])


def test_eine_leere_verbindung_ergibt_die_vorgegebene_swanctl_datei(
        tmp_path, monkeypatch, vorgabe):
    """Und die Konstanten wirken auch - nicht nur sie stimmen.

    Ein Vergleich von Konstanten allein waere gruen, wenn sie niemand
    mehr benutzt. Hier wird die Datei ERZEUGT und in ihr nachgesehen.
    """
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.syspath_prepend(str(SRC))
    import vpn

    dokument = {"vpn": {"active": "c1", "connections": [
        dict(vorgabe, id="c1", server="gw.example.org",
             routed_networks=["10.0.0.0/8"])]}}
    text = vpn.swanctl_config(dokument)

    assert f"proposals = {vorgabe['phase1']['proposals']}" in text
    assert f"dpd_delay = {vorgabe['phase1']['dpd_delay']}s" in text
    assert f"esp_proposals = {vorgabe['phase2']['esp_proposals']}" in text


# --------------------------------------------------------------------
# 4. Die Zusicherung gegen eine ZWEITE Tabelle
# --------------------------------------------------------------------

# Die Module, die je eine eigene Menge von VPN-Vorgaben fuehrten. Ein
# neuer Name gehoert nur dann hierher, wenn er wirklich eine Tabelle
# aufmacht - und dann ist die Frage, warum, und nicht, wie man den Test
# gruen bekommt.
OHNE_EIGENE_TABELLE = ("user_settings.py", "style_definition.py", "vpn.py")

# Die Schluessel, an denen man eine VPN-Vorgabentabelle erkennt. `kind`
# und `connection_name` stehen in JEDER der vier Mengen, die es gab.
VERRAETERISCHE_SCHLUESSEL = {"kind", "connection_name", "phase1", "phase2",
                             "routed_networks", "bypass_networks"}


def _dict_literale(baum):
    """Jedes dict-Literal, das wie eine Vorgabentabelle aussieht.

    ZWEI Bedingungen, und die zweite ist die, ohne die der Test falschen
    Alarm schlaegt: das Literal muss AUS LAUTER KONSTANTEN bestehen. In
    src/vpn.py steht bei remove_connection() ein Berichts-dict mit
    `kind` und `connection_name` darin - zwei der verraeterischen
    Schluessel, aber seine Werte sind Variablen. Eine Vorgabe kennt man
    daran, dass sie ohne Ausfuehrung dasteht.
    """
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Dict):
            continue
        namen = {k.value for k in knoten.keys
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if len(namen & VERRAETERISCHE_SCHLUESSEL) < 2:
            continue
        try:
            ast.literal_eval(knoten)
        except (ValueError, TypeError, SyntaxError, MemoryError,
                RecursionError):
            continue
        yield knoten


def test_es_gibt_keine_zweite_vorgabentabelle():
    """NEBEN den ausfuehrenden Tests, nicht an ihrer Stelle.

    Die vier Tests darueber messen, dass alle Wege HEUTE dasselbe
    antworten. Sie wuerden eine frisch aufgemachte zweite Tabelle
    trotzdem durchlassen, solange sie noch dieselben Werte traegt - und
    genau so ist die Doppelung dieses Baums entstanden: viermal
    dieselben Werte, dreimal davon unbemerkt, bis eine Menge laenger
    wurde als die andere.

    Dieser Test sieht darum in den Quelltext. Er sucht nach einem
    dict-Literal, das zwei oder mehr der Schluessel traegt, an denen
    eine VPN-Verbindung zu erkennen ist. In src/settings.py darf es
    genau das geben - das ist die Quelle. In den drei Modulen, die
    frueher eine eigene Menge fuehrten, darf es das nicht.
    """
    gefunden = {}
    for name in OHNE_EIGENE_TABELLE:
        datei = SRC / name
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        zeilen = [k.lineno for k in _dict_literale(baum)]
        if zeilen:
            gefunden[name] = zeilen

    assert gefunden == {}, (
        "hier steht wieder eine eigene Vorgabentabelle fuer eine "
        f"VPN-Verbindung: {gefunden}. Die eine Quelle ist "
        "src/settings.py::default_connection()."
    )


def test_die_quelle_traegt_die_tabelle_wirklich():
    """Und der Test darueber prueft nicht ins Leere.

    Ein Suchmuster, das nichts mehr findet, weil sich die Schreibweise
    geaendert hat, ist gruen und wertlos. Dieser hier haelt fest, dass
    dasselbe Muster in src/settings.py ANSCHLAEGT - faellt es dort aus,
    ist auch die Zusicherung darueber blind geworden.
    """
    baum = ast.parse((SRC / "settings.py").read_text(encoding="utf-8"))
    assert list(_dict_literale(baum)), (
        "das Muster findet die Vorgabentabelle in src/settings.py nicht "
        "mehr - damit ist test_es_gibt_keine_zweite_vorgabentabelle blind."
    )
