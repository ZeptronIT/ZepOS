# SPDX-License-Identifier: GPL-3.0-or-later
"""Das VPN-Fenster und das vierte Wort: ein Ausfall ist kein "getrennt".

WORUM ES GEHT
    `vpn.py --status` kannte drei Woerter, und `disconnected` trug zwei
    voellig verschiedene Aussagen: "der Nutzer hat getrennt" (eine
    Entscheidung) und "NetworkManager antwortet nicht" (ein Ausfall).
    Seit `55bae87` gibt es dafuer ein viertes Wort, `unknown`
    (vpn.STATUS_WORDS in src/vpn.py).

    tests/src/test_vpn_unbekannt.py misst, dass vpn.py es SAGT. Diese
    Datei misst, was das FENSTER daraus macht - der vierte Leser, den
    der Bericht zu Aufgabe 77 ausdruecklich offen gelassen hat:

        "Der vierte, src/templates/ags-vpn.template, faellt bei jedem
         unbekannten Wort auf 'disconnected' durch ... wartet auf einen
         eigenen Zweig; die Datei gehoert in dieser Sitzung einem
         anderen."

    Das ist dieser Zweig.

WARUM DER UNTERSCHIED NICHT KOSMETISCH IST
    Die zwei Irrtuemer sind nicht gleich teuer. Wer "getrennt" liest und
    in Wahrheit geschuetzt ist, verbindet unnoetig neu - laestig. Wer
    ungeschuetzt ist und "geschuetzt" liest, verliert Daten. Ein
    Fenster, das bei ausgefallenem NetworkManager "Nicht verbunden"
    sagt, behauptet etwas, das es nicht weiss - und der naheliegende
    Schluss daraus ("dann laeuft eben nichts") ist genau der, den
    niemand ziehen darf, solange es niemand weiss.

WAS GEMESSEN WIRD
    Drei Laeufe an derselben Seite, mit derselben Attrappe, die nur ein
    anderes Wort druckt: `unknown`, `disconnected`, `connected`. Gelesen
    werden Beschriftung, Zeichen und CSS-Klassen des Zustandssymbols.

    Der Vergleich UNTEREINANDER ist der eigentliche Beweis. Eine
    Zusicherung wie "bei unknown steht da etwas ueber NetworkManager"
    waere auch dann erfuellt, wenn dort IMMER dasselbe stuende. Drei
    Laeufe zeigen, dass sich das Fenster wirklich unterscheidet.

SICHERHEIT
    Eigener gtk4-broadwayd in einem eigenen XDG_RUNTIME_DIR. Das echte
    vpn.py laeuft nicht - `{{ZEPOS_SYSTEM_ROOT}}` zeigt auf ein
    Wegwerfverzeichnis mit einer Attrappe, die ein Wort druckt und sonst
    nichts. Niemand fragt NetworkManager oder strongSwan etwas.
"""
from __future__ import annotations

import gettext
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src import vpn                                        # noqa: E402

# Den Aufbau von test_vpn_schalter.py leihen statt ihn abzuschreiben -
# `_baue` ist dort fuer ein zweites und drittes Kind schon geoeffnet
# worden, samt Wegwerf-vpn.py und broadwayd.
_SPEC = importlib.util.spec_from_file_location(
    "_vpn_schalter_harness",
    ROOT / "tests" / "src" / "test_vpn_schalter.py")
_HARNESS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HARNESS)

pytestmark = pytest.mark.allow_subprocess

KIND = Path(__file__).resolve().parent / "vpn_unbekannt_child.tsx"

# Die englischen msgid - der Lauf setzt LC_ALL=C, damit die Erwartungen
# nicht an der Sprache dieser Maschine haengen. Dass die DEUTSCHE Fassung
# beim Nutzer ankommt, misst test_die_zwei_saetze_kommen_auf_deutsch_an
# weiter unten - und zwar am uebersetzten Katalog, nicht an de.po.
UNBEKANNT_1 = "VPN status unknown – NetworkManager is not responding."
UNBEKANNT_2 = "Nobody knows whether your traffic is protected."
GETRENNT = "Not connected"

PO_DE = ROOT / "po" / "desktop" / "de.po"
DOMAENE = "zepos-desktop"                # ags-i18n.template, `DOMAIN`


def _lauf(wurzel: Path, wort: str):
    """Ein Lauf mit einer Attrappe, die genau `wort` druckt."""
    server_befehl = _HARNESS.broadwayd()
    if server_befehl is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    buendel, _system = _HARNESS._baue(wurzel, kind=KIND, wort=wort)

    laufzeit = wurzel / "run"
    laufzeit.mkdir()
    laufzeit.chmod(0o700)

    user_root = wurzel / "zepos"
    _HARNESS._einstellungen(user_root)

    spur = wurzel / "spur"
    nummer = next(_HARNESS._DISPLAYS)
    server, _socket = _HARNESS.start_broadwayd(server_befehl, laufzeit, nummer)
    try:
        import subprocess
        ergebnis = subprocess.run(
            [str(buendel)],
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(wurzel),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{nummer}",
                "XDG_RUNTIME_DIR": str(laufzeit),
                "XDG_CONFIG_HOME": str(wurzel / "config"),
                "ZEPOS_USER_ROOT": str(user_root),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={wurzel}/kein-bus",
                "LC_ALL": "C",
                "LANG": "C",
                "ZEPOS_TRACE": str(spur),
            },
            capture_output=True, text=True,
            timeout=_HARNESS.CHILD_TIMEOUT,
        )
    finally:
        _HARNESS.stop_broadwayd(server)

    return _HARNESS.Lauf(ergebnis.returncode, ergebnis.stdout,
                         ergebnis.stderr,
                         spur.read_text() if spur.exists() else "")


@pytest.fixture(scope="module")
def laeufe(tmp_path_factory) -> dict:
    """Drei Laeufe, einer je Wort. `ags bundle` kostet Sekunden."""
    return {wort: _lauf(tmp_path_factory.mktemp(f"vpn-{wort}"), wort)
            for wort in (vpn.UNKNOWN, vpn.DISCONNECTED, vpn.CONNECTED)}


def test_die_seite_steht_ueberhaupt(laeufe):
    """Die Gegenprobe zuerst.

    Jede Zusicherung darunter liest Marken. Faende das Kind Symbol oder
    Beschriftung gar nicht, waeren sie leer - und eine Zusicherung, die
    nur ein Wort NICHT sehen will, waere damit erfuellt, ohne dass es
    die Ansicht gibt.
    """
    for wort, lauf in laeufe.items():
        assert lauf.marke("symbol-da") == "ja", f"{wort}:\n{lauf.bericht}"
        assert lauf.marke("beschriftung-da") == "ja", f"{wort}:\n{lauf.bericht}"


def test_bei_unbekannt_steht_nicht_dass_nichts_laeuft(laeufe):
    """DIE ZUSICHERUNG DIESER DATEI.

    Bei `unknown` darf das Fenster NICHT "Nicht verbunden" sagen. Das
    ist der Satz, den der vierte Zustand beenden soll: er behauptet
    etwas ueber den Verkehr des Nutzers, das in diesem Moment niemand
    weiss.
    """
    lauf = laeufe[vpn.UNKNOWN]
    text = lauf.marke("beschriftung")
    assert GETRENNT not in text, (
        "bei `unknown` steht immer noch \"Not connected\" im Fenster - "
        "damit behauptet es, der Verkehr laufe ungeschuetzt, obwohl das "
        f"gerade niemand weiss.\n{lauf.bericht}")


def test_bei_unbekannt_steht_was_passiert_ist_und_was_es_bedeutet(laeufe):
    """Beide Haelften, und die zweite ist die wichtigere.

    "NetworkManager antwortet nicht" allein liesse den Leser selbst
    schliessen, was das fuer seinen Verkehr heisst - und der
    naheliegende Schluss ("dann laeuft wohl nichts") ist genau der
    falsche. Also muss beides dastehen.

    WOERTLICH DIESELBEN ZWEI SAETZE WIE IN DER LEISTE
    (bar-vpn-config.template, Zweig `vpn.UNKNOWN`). Sagten Fenster und
    Leiste denselben Zustand verschieden, muesste der Leser raten, ob
    sie dasselbe meinen.
    """
    lauf = laeufe[vpn.UNKNOWN]
    text = lauf.marke("beschriftung")
    assert UNBEKANNT_1 in text, (
        f"der Grund fehlt:\n{text}\n{lauf.bericht}")
    assert UNBEKANNT_2 in text, (
        "die FOLGE fehlt - ohne sie zieht der Leser den naheliegenden "
        f"und falschen Schluss:\n{text}\n{lauf.bericht}")


def test_unbekannt_sieht_anders_aus_als_getrennt(laeufe):
    """Der Vergleich, ohne den die Zusicherungen darueber nichts wiegen.

    Stuende in JEDEM Lauf dasselbe, waeren sie trotzdem erfuellt. Hier
    wird verlangt, dass sich Beschriftung UND Zeichen UND Klasse
    zwischen "unbekannt" und "getrennt" wirklich unterscheiden.
    """
    unbekannt = laeufe[vpn.UNKNOWN]
    getrennt = laeufe[vpn.DISCONNECTED]

    assert unbekannt.marke("beschriftung") != getrennt.marke("beschriftung")
    assert unbekannt.marke("symbol-zeichen") != getrennt.marke("symbol-zeichen"), (
        "unbekannt und getrennt tragen dasselbe Zeichen - dann "
        "unterscheidet sie auf einen Blick nichts:\n"
        f"{unbekannt.bericht}")

    klassen_unbekannt = unbekannt.marke("symbol-klassen").split(".")
    klassen_getrennt = getrennt.marke("symbol-klassen").split(".")
    assert "unknown" in klassen_unbekannt, (
        "dem Zustandssymbol fehlt die Klasse `unknown` - an ihr haengt "
        f"die Warnfarbe (ags-style.template):\n{unbekannt.bericht}")
    assert "disconnected" not in klassen_unbekannt, (
        "das Symbol traegt bei `unknown` NOCH die Klasse `disconnected` "
        "- dann faerbt es sich wie \"nicht verbunden\", egal was "
        f"danebensteht:\n{unbekannt.bericht}")
    assert "disconnected" in klassen_getrennt, (
        f"und die Gegenprobe dazu haelt nicht:\n{getrennt.bericht}")


def test_bei_unbekannt_nimmt_kein_schalter_eine_eingabe_an(laeufe):
    """DIE ZWEITE HAELFTE, und ohne sie waere die erste halb.

    Der Text sagt bei `unknown` "niemand weiss es". Stuenden daneben
    Schalter auf "aus", sagte dasselbe Fenster im selben Atemzug das
    Gegenteil - "aus" ist eine Behauptung ueber die Verbindung, nur
    unauffaelliger als ein Satz.

    Ein Gtk.Switch hat keine dritte STELLUNG, aber einen dritten
    ZUSTAND: nicht bedienbar. Der behauptet nichts. Und er ist auch in
    der Handlung ehrlich - bei `unknown` weiss niemand, was ein Umlegen
    bewirken wuerde.

    GEMESSEN je Schalter und nicht nur am ersten: eine Liste, in der
    einer sperrt und der andere nicht, waere schlimmer als gar keine
    Sperre - sie saehe nach einer Regel aus, die es nicht gibt.
    """
    unbekannt = laeufe[vpn.UNKNOWN]
    anzahl = int(unbekannt.marke("schalter-anzahl"))
    assert anzahl >= 2, (
        "die Liste zeigt weniger als zwei Schalter - dann misst diese "
        f"Zusicherung fast nichts:\n{unbekannt.bericht}")
    zustaende = unbekannt.marke("schalter-bedienbar").split(",")
    assert set(zustaende) == {"false"}, (
        "bei `unknown` nimmt mindestens ein Schalter noch Eingaben an "
        f"({zustaende}). Er zeigt dann \"aus\" und laesst sich umlegen, "
        "obwohl niemand weiss, was das bewirkt - waehrend danebensteht, "
        f"dass niemand es weiss.\n{unbekannt.bericht}")


def test_bei_den_anderen_zustaenden_bleiben_die_schalter_bedienbar(laeufe):
    """Die Gegenprobe dazu, und sie ist der eigentliche Beweis.

    "Alle Schalter gesperrt" waere auch dann erfuellt, wenn sie IMMER
    gesperrt waeren - dann haette der vierte Zustand nicht die Sperre
    eingefuehrt, sondern die Bedienbarkeit abgeschafft.
    """
    for wort in (vpn.DISCONNECTED, vpn.CONNECTED):
        lauf = laeufe[wort]
        zustaende = lauf.marke("schalter-bedienbar").split(",")
        assert set(zustaende) == {"true"}, (
            f"bei `{wort}` ist mindestens ein Schalter gesperrt "
            f"({zustaende}) - die Sperre gehoert allein zu `unknown`, "
            "sonst laesst sich gar keine Verbindung mehr schalten:\n"
            f"{lauf.bericht}")


def test_getrennt_und_verbunden_sagen_weiter_was_sie_sagten(laeufe):
    """Das vierte Wort darf die drei alten nicht anfassen.

    `unknown` ist rein additiv - wer vorher "getrennt" bekam, weil
    nmcli wirklich nachgesehen hatte, bekommt es weiter.
    """
    getrennt = laeufe[vpn.DISCONNECTED]
    assert GETRENNT in getrennt.marke("beschriftung"), getrennt.bericht
    assert "unknown" not in getrennt.marke("symbol-klassen").split("."), (
        getrennt.bericht)

    # Bei `connected` blendet die Seite die Formularansicht aus und
    # zeigt die verbundene. Das Zustandssymbol des Formulars bleibt
    # dabei stehen - gemessen wird hier darum nur, dass es NICHT die
    # Warnung des unbekannten Zustands traegt.
    verbunden = laeufe[vpn.CONNECTED]
    assert "unknown" not in verbunden.marke("symbol-klassen").split("."), (
        verbunden.bericht)


def test_die_zwei_saetze_kommen_auf_deutsch_an(tmp_path):
    """GEMESSEN AM UEBERSETZTEN KATALOG, NICHT AN de.po.

    WAS HIER SCHON EINMAL DURCHGERUTSCHT IST
        Beide Eintraege standen am 02.09.2026 mit `#, fuzzy` in de.po,
        und daran haengt keine Kosmetik: msgfmt nimmt einen fuzzy
        markierten Eintrag NICHT in die .mo auf. Die Uebersetzung stand
        also lesbar in der Quelldatei und kam beim Nutzer trotzdem nicht
        an - nachgeschlagen ueber gettext lieferten beide msgids ihren
        ENGLISCHEN Text zurueck, wortgleich mit dem msgid.

        Ausgerechnet in diesem Fenster. Es ist das eine, das einem
        deutschen Nutzer sagen soll, dass niemand weiss, ob sein Verkehr
        geschuetzt ist - auf Englisch sagt es das dem, der kein Englisch
        liest, gar nicht.

        Dazu kam es, weil der Satz erst EIN msgid mit `\\n` darin war und
        dann zwei wurden: `msgmerge` hat die alte Uebersetzung auf die
        zwei neuen msgids grob zugeordnet, ihre Fortsetzungszeilen an
        beide angeklebt (der msgstr las den Satz doppelt) und beide
        vorsichtshalber fuzzy gesetzt.

    WARUM DIE BESTEHENDE PRUEFUNG DAS NICHT SAH
        tests/src/test_ags_i18n.py liest den TEXT von de.po und verlangt
        einen nicht leeren msgstr. Der war nicht leer. Die Marke `fuzzy`
        steht eine Zeile darueber und in keinem der Muster - der Katalog
        sah gepflegt aus, waehrend zwei Saetze der Oberflaeche englisch
        blieben.

        Deshalb wird hier nicht der Katalog gelesen, sondern GEBAUT und
        BEFRAGT, genau wie die Oberflaeche ihn befragt (Domaene
        `zepos-desktop`, ags-i18n.template). Was msgfmt weglaesst, kann
        dieser Test nicht fuer vorhanden halten.

    NUR DIE ZWEI SAETZE DIESES ZWEIGES
        Der Katalog als Ganzes gehoert test_ags_i18n.py; dort fehlt die
        Pruefung auf fuzzy fuer ALLE Eintraege noch.
    """
    if shutil.which("msgfmt") is None:
        pytest.skip("msgfmt fehlt; es kommt mit dem Paket gettext")
    assert PO_DE.exists(), f"{PO_DE} fehlt"

    ziel = tmp_path / "de" / "LC_MESSAGES"
    ziel.mkdir(parents=True)
    subprocess.run(
        ["msgfmt", "-o", str(ziel / f"{DOMAENE}.mo"), str(PO_DE)],
        check=True, capture_output=True)

    katalog = gettext.translation(DOMAENE, str(tmp_path), languages=["de"])
    for msgid in (UNBEKANNT_1, UNBEKANNT_2):
        deutsch = katalog.gettext(msgid)
        assert deutsch != msgid, (
            f"{msgid!r} kommt aus dem uebersetzten Katalog unveraendert "
            "zurueck - ein deutscher Nutzer liest diesen Satz auf "
            "Englisch. Steht die Uebersetzung in de.po, dann ist sie "
            "wahrscheinlich `#, fuzzy` markiert; msgfmt laesst solche "
            "Eintraege weg.")
        # Und die Gegenprobe zur Gegenprobe: der doppelte msgstr von
        # oben war AUCH ungleich dem msgid. Ein Satz, der sich selbst
        # zweimal sagt, darf nicht als Uebersetzung durchgehen.
        assert deutsch.count("VPN-Zustand unbekannt") <= 1, (
            f"die Uebersetzung sagt sich selbst zweimal: {deutsch!r}")
        assert deutsch.count("Niemand weiß") <= 1, (
            f"die Uebersetzung sagt sich selbst zweimal: {deutsch!r}")
        assert "\n" not in deutsch, (
            f"{msgid!r} wird auf einen ZWEIZEILIGEN Text uebersetzt: "
            f"{deutsch!r}. Die zwei Saetze sind zwei msgids, damit "
            "gettext sie einzeilig schreibt; werden sie im Katalog "
            "wieder zu einem, ist die Aufteilung im Fenster umsonst.")
