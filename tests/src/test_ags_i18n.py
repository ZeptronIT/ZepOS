# SPDX-License-Identifier: GPL-3.0-or-later
"""Keine Beschriftung der Oberflaeche ist fest verdrahtet.

WORAUF DIESE DATEI ANTWORTET
    Eine Meldung vom 15.08.2026:

        "i18n wurde nicht Ordnungsgemaess gepflegt und meinche UI
         Elemente sind noch Deutsch und nicht variabel"

    Sie war richtig, und zwar vollstaendig: GEMESSEN am 17.08.2026 stand
    in den dreiundzwanzig AGS-Vorlagen KEIN einziger `_()`-Aufruf. Der
    Installer uebersetzt seit langem (installer/core/i18n.py, po/de.po),
    die Oberflaeche daneben trug 229 deutsche Zeichenketten im Quelltext.

WARUM EINE MESSUNG UND KEINE DURCHSICHT
    Eine Durchsicht sagt "sieht gut aus". Sie sagt nicht, wieviele
    Zeichenketten es gibt, und deshalb kann sie auch nicht sagen, wann
    man fertig ist. Der Kopf von ags-shortcuts.template hat denselben
    Satz schon einmal bezahlt: dort stand "74 Keybinds" ueber einer
    Tabelle mit 79 Eintraegen, und niemand konnte es merken.

    Diese Datei zaehlt deshalb bei jedem Lauf nach. Sie ist der Grund,
    aus dem eine spaeter hinzugefuegte deutsche Beschriftung nicht bis
    zur naechsten Meldung eines Nutzers unbemerkt bleibt.

WAS "SICHTBAR" HEISST
    Ein Zeichenketten-Literal, das in den Ausdruck einer GTK-Eigenschaft
    oder eines Setzers fliesst, den ein Mensch liest, oder das als Titel
    oder Text an notify-send geht. Nicht: Kommentare, CSS-Klassen,
    Signalnamen, Anmeldenamen von Fenstern, Vergleichswerte.

    Die Ausdruecke werden ueber Zeilengrenzen UND ueber
    Fallunterscheidungen hinweg verfolgt, weil beides hier vorkommt:

        emptyLabel.set_text(
          suchtGerade ? "Suche laeuft" : "Kein Geraet bekannt")

    sind ZWEI sichtbare Zeichenketten an EINEM Setzer. Ein Muster, das
    nur das erste Literal hinter der Klammer nimmt, haette am
    17.08.2026 sechsunddreissig von 229 nicht gesehen - gemessen, indem
    beide Fassungen gegen denselben Baum liefen.
"""
from __future__ import annotations

import gettext
import re
import shutil
import subprocess
from pathlib import Path

import pytest

# Auf diese Datei bezogen und nie auf das Arbeitsverzeichnis - dieselbe
# Begruendung wie im Kopf von tests/src/test_naming.py: pytest laesst
# sich von ueberall starten, und ein relatives Path("src") misst das
# Verzeichnis, in dem jemand gerade stand.
REPOSITORY = Path(__file__).resolve().parents[2]
TEMPLATES = REPOSITORY / "src" / "templates"
PO_FILE = REPOSITORY / "po" / "desktop" / "de.po"

# Der Baustein, aus dem `_()` kommt. Er ist selbst eine Vorlage und
# steht deshalb in derselben Liste, darf aber keine uebersetzte
# Zeichenkette enthalten - er IST die Uebersetzung.
I18N_TEMPLATE = "ags-i18n.template"

DOMAIN = "zepos-desktop"

# Eigenschaften, deren Wert auf dem Schirm steht.
#
# DIE ZWEI DEUTSCHEN NAMEN AM ENDE SIND DAS LOCH, DAS AM 02.09.2026
# GEFUNDEN WURDE, und es ist eins, das man nur durch Nachzaehlen findet:
#
#     Der eigene Bausteinkasten (ags-kit.template) nimmt seinen
#     Anzeigetext unter DEUTSCHEN Parameternamen entgegen - zepRow({
#     titel, unterzeile }). Diese Liste kannte nur englische. Damit war
#     jede Beschriftung, die durch zepRow geht, fuer die strukturelle
#     Suche unsichtbar, und das ist der am haeufigsten benutzte
#     Baustein der Schale.
#
#     GEMESSEN mit und ohne die zwei Namen: 409 -> 436 sichtbare
#     Zeichenketten, also 27 Literale mehr unter Beobachtung, davon 0
#     ohne _() und 0 Fehlalarme. Die Senke geht damit zu, ohne heute
#     etwas zu kosten.
SICHTBARE_EIGENSCHAFTEN = (
    "label", "headerTitle", "title", "subtitle", "tooltip", "tooltip_text",
    "tooltipText", "placeholder_text", "placeholderText", "text",
    "body", "summary", "heading", "message", "description", "name",
    "titel", "unterzeile",
)
SICHTBARE_SETZER = (
    "set_label", "set_title", "set_subtitle", "set_tooltip_text",
    "set_text", "set_placeholder_text", "set_heading", "set_body",
)

EIGENSCHAFT_RE = re.compile(
    r"(?<![\w.])(" + "|".join(SICHTBARE_EIGENSCHAFTEN) + r")\s*:")
SETZER_RE = re.compile(r"\.(" + "|".join(SICHTBARE_SETZER) + r")\s*\(")

# Eine Meldung auf dem Schirm ist Ausgabe an den Nutzer wie jede andere.
# Der Aufruf steht mal als Feld einer Argumentliste, mal in einer
# Kommandozeile - beide Formen kommen in diesem Baum vor.
NOTIFY_RE = re.compile(r"notify-send")

# Eine Beschriftung erreicht ein Widget auch, ohne je neben dem Wort
# `label:` zu stehen - naemlich als Argument einer eigenen Hilfsfunktion:
#
#     const createDetailRow = (labelText: string): [Gtk.Box, Gtk.Label] => …
#     const [ipRow, ipVal] = createDetailRow("IP-Adresse")
#
# GEMESSEN am 17.08.2026: sieben solche Funktionen in vier Vorlagen, und
# eine Messung, die nur Eigenschaften kennt, sieht KEINEN ihrer
# Aufrufe. Der Parametername ist die Angabe, die beide Seiten schon
# haben - hier wird er gelesen und nicht zweitgepflegt.
SICHTBARE_PARAMETER = (
    "label", "labelText", "title", "titleText", "text", "tooltip",
    "tooltipText", "placeholder", "placeholderText", "summary", "body",
    "heading", "description",
)

WORT_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")
PLATZHALTER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
EINSETZUNG_RE = re.compile(r"\$\{[^{}]*\}")

# Kleinschreibung mit Bindestrich ist in diesem Baum durchgehend ein
# MASCHINENNAME und keine Beschriftung: die Anmeldenamen der Fenster
# ("vpn-settings", "notification-center"), die Dringlichkeit von
# notify-send ("critical") und die Symbolnamen ("dialog-error"). Was ein
# Mensch liest, traegt einen Grossbuchstaben oder ein Leerzeichen.
MASCHINENNAME_RE = re.compile(r"^[a-z0-9-]*$")

# Einheiten sind keine Sprache: "300px" und "${value}px" enthalten ein
# Wort im Sinne der Regel und trotzdem nichts zu uebersetzen.
EINHEITEN = {"px"}

# Das zweite Argument von ngettext steht hinter einem Komma und nicht
# hinter der Klammer, ist aber genauso uebersetzt.
NGETTEXT_ZWEITES_RE = re.compile(
    r"ngettext\(\s*(?:\"[^\"]*\"|'[^']*'|`[^`]*`)\s*,\s*$")

# `pgettext("slider axis", "W")` - der Text ist das ZWEITE Argument, das
# erste ist der Zusatz fuer den Uebersetzer und steht nie auf dem Schirm.
PGETTEXT_ZWEITES_RE = re.compile(
    r"(?<!n)pgettext\(\s*(?:\"[^\"]*\"|'[^']*'|`[^`]*`)\s*,\s*$")

VERGLEICHE = ("===", "!==", "==", "!=")

# Die einzige Ausnahme von der Regel, und sie steht hier namentlich,
# damit sie niemand aus Versehen erweitert.
#
# Die sechs Themen des Stil-Editors tragen EIGENNAMEN. "Forest Dark" ist
# der Name eines Themas wie "Adwaita" oder "Breeze" der Name eines
# anderen ist; uebersetzt waere es ein anderes Thema, und zwei Nutzer
# koennten dasselbe nicht mehr beim selben Namen nennen. Ihre
# `description:` daneben ist Fliesstext und laeuft sehr wohl durch den
# Katalog - das ist die Grenze.
#
# "ZeptronIT" ist obendrein die Marke selbst.
EIGENNAMEN = (
    "ZeptronIT", "Cyber Neon", "Forest Dark", "Sunset Warm", "Ocean Blue",
    "Midnight Purple",
)


def _ohne_kommentare(text: str, *, shell: bool = False) -> str:
    """Kommentare durch Leerzeichen ersetzen.

    Die LAENGE bleibt erhalten, damit jeder Versatz und damit jede
    Zeilennummer noch stimmt. Zeichenketten bleiben unberuehrt - ein
    `//` in einer URL ist kein Kommentaranfang.

    `shell=True` FUER DIE VIER *-scripts.template, seit dem 02.09.2026.
    Sie sind SHELL-Skripte und kommentieren mit '#'; ein Entferner, der
    nur `//` und `/* */` kennt, liest ihre Kommentare als Quelltext.
    GEMESSEN: 113 Scheinkandidaten allein in
    ags-network-scripts.template, dazu einer in
    ags-media-scripts.template:134, der in Wahrheit ein Kommentar ist.

    Das ist derselbe blinde Fleck wie eine Pruefung, die nichts sieht -
    nur in der anderen Richtung: sie sieht ZU VIEL, und eine Zusicherung
    mit Fehlalarmen ist eine, die abgeschaltet wird.

    WARUM EIN SCHALTER UND NICHT '#' IMMER: in TypeScript ist '#' ein
    gueltiger Namensanfang (private Felder, `#privat`) und in einer
    Farbe steht es mitten im Wort ("#1a1a1a"). Ein Entferner, der '#'
    ueberall als Kommentar liest, wuerde dort den Rest der Zeile
    verschlucken.
    """
    aus = list(text)
    i = 0
    n = len(text)
    anfuehrung = None
    while i < n:
        zeichen = text[i]
        if anfuehrung:
            if zeichen == "\\":
                i += 2
                continue
            if zeichen == anfuehrung:
                anfuehrung = None
            i += 1
            continue
        if shell and zeichen == "#":
            ende = text.find("\n", i)
            ende = n if ende == -1 else ende
            for j in range(i, ende):
                aus[j] = " "
            i = ende
            continue
        if zeichen in "\"'`":
            anfuehrung = zeichen
            i += 1
            continue
        if text.startswith("//", i):
            ende = text.find("\n", i)
            ende = n if ende == -1 else ende
            for j in range(i, ende):
                aus[j] = " "
            i = ende
            continue
        if text.startswith("/*", i):
            ende = text.find("*/", i + 2)
            ende = n if ende == -1 else ende + 2
            for j in range(i, ende):
                if aus[j] != "\n":
                    aus[j] = " "
            i = ende
            continue
        i += 1
    return "".join(aus)


# Was vor einem `/` stehen darf, damit es einen REGULAEREN AUSDRUCK
# einleitet und keine Division ist.
#
# GEMESSEN am 17.08.2026 an ags-bar.template:1787:
#
#     const sicher = device.replace(/'/g, "'\\''")
#
# Das Hochkomma IM regulaeren Ausdruck galt der Suche als Anfang einer
# Zeichenkette, und von da an war jedes Literal der Datei um eines
# versetzt - neun Scheinfunde in einer Datei, alle mit Bruchstuecken von
# Programmtext darin. Die vollstaendige Unterscheidung Regex/Division
# braucht einen Parser; diese Liste reicht fuer den Baum, den sie liest,
# und ein `a / b` mit einem Hochkomma dahinter kommt in ihm nicht vor.
VOR_EINEM_REGEX = ("(", ",", "=", ":", "[", "!", "&", "|", "?", "{", "}",
                   ";", "return", "\n", "")


def _regex_ende(text: str, start: int) -> int | None:
    """Index hinter dem regulaeren Ausdruck, der bei `start` anfaengt,
    oder None, wenn dort keiner steht."""
    if text[start] != "/":
        return None
    davor = text[:start].rstrip()
    if not davor.endswith(VOR_EINEM_REGEX):
        return None
    i = start + 1
    in_klasse = False
    while i < len(text):
        zeichen = text[i]
        if zeichen == "\\":
            i += 2
            continue
        if zeichen == "\n":
            return None
        if zeichen == "[":
            in_klasse = True
        elif zeichen == "]":
            in_klasse = False
        elif zeichen == "/" and not in_klasse:
            i += 1
            while i < len(text) and text[i].isalpha():
                i += 1
            return i
        i += 1
    return None


def _literal(text: str, start: int):
    """(Inhalt, Index dahinter) des Literals, das bei `start` anfaengt."""
    anfuehrung = text[start]
    if anfuehrung not in "\"'`":
        return None
    i = start + 1
    inhalt = []
    while i < len(text):
        zeichen = text[i]
        if zeichen == "\\":
            inhalt.append(text[i:i + 2])
            i += 2
            continue
        if zeichen == anfuehrung:
            return "".join(inhalt), i + 1
        inhalt.append(zeichen)
        i += 1
    return None


def _literal_bereiche(text: str) -> list[tuple[int, int]]:
    """(Anfang, Ende) jedes Literals der obersten Ebene."""
    bereiche = []
    i = 0
    while i < len(text):
        # Ein regulaerer Ausdruck darf jedes Zeichen enthalten, auch ein
        # Hochkomma. Er wird uebersprungen, nicht gelesen.
        hinter_regex = _regex_ende(text, i)
        if hinter_regex is not None:
            i = hinter_regex
            continue
        if text[i] in "\"'`":
            gefunden = _literal(text, i)
            if gefunden is None:
                break
            bereiche.append((i, gefunden[1]))
            i = gefunden[1]
            continue
        i += 1
    return bereiche


def _umgebendes_literal(bereiche: list[tuple[int, int]], index: int):
    for anfang, ende in bereiche:
        if anfang < index < ende:
            return anfang, ende
        if anfang > index:
            break
    return None


def _ausdruck_ende(text: str, start: int, *, bis_klammer: bool) -> int:
    """Ende des Ausdrucks ab `start`.

    Ein Setzer laeuft bis zur schliessenden Klammer, eine Eigenschaft bis
    zum Komma auf Tiefe 0 oder bis zur Klammer, die das Objekt schliesst.
    """
    tiefe = 0
    i = start
    while i < len(text):
        zeichen = text[i]
        if zeichen in "\"'`":
            gefunden = _literal(text, i)
            if gefunden is None:
                return i
            i = gefunden[1]
            continue
        if zeichen in "([{":
            tiefe += 1
        elif zeichen in ")]}":
            if tiefe == 0:
                return i
            tiefe -= 1
        elif tiefe == 0 and not bis_klammer and zeichen == ",":
            return i
        i += 1
    return len(text)


def _klammer_ende(text: str, offen: int) -> int:
    """Index der Klammer, die die bei `offen` schliesst."""
    tiefe = 0
    i = offen
    while i < len(text):
        zeichen = text[i]
        if zeichen in "\"'`":
            gefunden = _literal(text, i)
            if gefunden is None:
                return len(text)
            i = gefunden[1]
            continue
        if zeichen in "([{":
            tiefe += 1
        elif zeichen in ")]}":
            tiefe -= 1
            if tiefe == 0:
                return i
        i += 1
    return len(text)


def _felder(text: str, von: int, bis: int) -> list[tuple[int, int]]:
    """(Anfang, Ende) jedes durch Kommas der obersten Ebene getrennten
    Feldes zwischen zwei Klammern."""
    felder = []
    tiefe = 0
    anfang = von
    i = von
    while i < bis:
        zeichen = text[i]
        if zeichen in "\"'`":
            gefunden = _literal(text, i)
            if gefunden is None:
                break
            i = gefunden[1]
            continue
        if zeichen in "([{":
            tiefe += 1
        elif zeichen in ")]}":
            tiefe -= 1
        elif zeichen == "," and tiefe == 0:
            felder.append((anfang, i))
            anfang = i + 1
        i += 1
    felder.append((anfang, bis))
    return felder


# `function name(` und `const name = (` / `= async (`, beide Formen
# kommen in diesen Vorlagen vor.
DEKLARATION_RE = re.compile(
    r"(?:function\s+(?P<a>\w+)\s*\()"
    r"|(?:(?:const|let|var)\s+(?P<b>\w+)\s*(?::[^=\n]*)?=\s*(?:async\s+)?\()")


def _hilfsfunktionen(text: str):
    """({Funktionsname: {Nummern der Parameter, die eine Beschriftung
    sind}}, {Klammerstellen der Deklarationen}).

    Die zweite Haelfte ist noetig, um die Deklaration von einem Aufruf zu
    unterscheiden. Sie an der Zeichenkette davor zu erkennen ging nicht:
    `const [ipRow, ipVal] = createDetailRow("IP-Adresse")` endet vor der
    Klammer auf "=", genau wie eine Deklaration - gemessen am
    17.08.2026 an vier uebersehenen Aufrufen in ags-network.template.
    """
    gefunden: dict[str, set[int]] = {}
    deklarationen: set[int] = set()
    for treffer in DEKLARATION_RE.finditer(text):
        name = treffer.group("a") or treffer.group("b")
        offen = treffer.end() - 1
        zu = _klammer_ende(text, offen)
        stellen = set()
        for nummer, (von, bis) in enumerate(_felder(text, offen + 1, zu)):
            bezeichner = text[von:bis].strip().split(":")[0].strip()
            if bezeichner in SICHTBARE_PARAMETER:
                stellen.add(nummer)
        if stellen:
            gefunden.setdefault(name, set()).update(stellen)
            deklarationen.add(offen)
    return gefunden, deklarationen


def _ist_sichtbarer_text(wert: str, schluessel: str) -> bool:
    if not wert.strip():
        return False
    ohne = EINSETZUNG_RE.sub(" ", PLATZHALTER_RE.sub(" ", wert))
    woerter = WORT_RE.findall(ohne)
    if not woerter:
        return False
    if all(wort.lower() in EINHEITEN for wort in woerter):
        return False
    if schluessel in ("name", "notify-send"):
        if MASCHINENNAME_RE.match(EINSETZUNG_RE.sub("", wert)):
            return False
    return True


def _literale_im_bereich(text: str, start: int, ende: int):
    i = start
    while i < ende:
        if text[i] in "\"'`":
            gefunden = _literal(text, i)
            if gefunden is None:
                return
            wert, dahinter = gefunden
            kopf = text[:i].rstrip()
            uebersetzt = (kopf.endswith("_(")
                          or kopf.endswith("ngettext(")
                          or NGETTEXT_ZWEITES_RE.search(kopf) is not None
                          or PGETTEXT_ZWEITES_RE.search(kopf) is not None)
            # Zwei Arten von Literal stehen NIE auf dem Schirm:
            #
            #   ein Vergleichswert - `status === "Playing"` fragt
            #   playerctl ab, das Wort gehoert der Maschine;
            #
            #   der ZUSATZ von pgettext - das erste Argument ist die
            #   Erklaerung fuer den Uebersetzer, das zweite der Text.
            #   Ohne diese Zeile zaehlte die Messung ihre eigene
            #   Erklaerung als unuebersetzte Beschriftung, gemessen am
            #   17.08.2026 an "widget size, width".
            if not (kopf.endswith(VERGLEICHE)
                    or kopf.endswith("pgettext(")):
                yield wert, i, uebersetzt
            i = dahinter
            continue
        i += 1


def sichtbare_zeichenketten(pfad: Path) -> list[dict]:
    """Jede sichtbare Zeichenkette einer Vorlage, je mit der Angabe, ob
    sie durch den Katalog laeuft."""
    text = _ohne_kommentare(pfad.read_text(encoding="utf-8"))

    zeilen = [1] * (len(text) + 1)
    zeile = 1
    for index, zeichen in enumerate(text):
        zeilen[index] = zeile
        if zeichen == "\n":
            zeile += 1
    zeilen[len(text)] = zeile

    bereiche = []
    for treffer in EIGENSCHAFT_RE.finditer(text):
        start = treffer.end()
        while start < len(text) and text[start] in " \t\n":
            start += 1
        bereiche.append((treffer.group(1), start,
                         _ausdruck_ende(text, start, bis_klammer=False)))
    for treffer in SETZER_RE.finditer(text):
        start = treffer.end()
        while start < len(text) and text[start] in " \t\n":
            start += 1
        bereiche.append((treffer.group(1), start,
                         _ausdruck_ende(text, start, bis_klammer=True)))
    literale = _literal_bereiche(text)
    for treffer in NOTIFY_RE.finditer(text):
        # notify-send kommt in zwei Formen vor, und sie enden woanders.
        #
        #   ['notify-send', '-i', 'dialog-error', 'VPN', 'gespeichert']
        #       eine Argumentliste. Sie endet an ihrer Klammer.
        #
        #   `notify-send "Energieprofil" "${labels[profile]}"`
        #       eine KOMMANDOZEILE, also selbst ein Literal. Sichtbar
        #       sind die Stuecke DARIN, und der Bereich endet am
        #       schliessenden Anfuehrungszeichen. Ohne diese Grenze lief
        #       die Suche darueber hinaus und las das naechste
        #       Anfuehrungszeichen der Datei als Anfang eines Literals -
        #       gemessen am 17.08.2026 an vier Scheinfunden in
        #       ags-battery.template.
        umgebend = _umgebendes_literal(literale, treffer.start())
        # `'notify-send'` als erstes Feld der Liste ist selbst ein
        # Literal, und zwar genau dieses Wort. Das ist die Argumentliste
        # und nicht die Kommandozeile - und der Bereich faengt HINTER
        # dem schliessenden Anfuehrungszeichen an. Faengt er davor an,
        # liest die Suche dieses Zeichen als Anfang des naechsten
        # Literals und alles Weitere um eines versetzt; gemessen am
        # 17.08.2026 an drei Scheinfunden ("," und "])") in
        # ags-vpn-settings.template.
        eigenes_wort = umgebend is not None and (
            (umgebend[0] + 1, umgebend[1] - 1)
            == (treffer.start(), treffer.end()))
        if umgebend is None or eigenes_wort:
            start = umgebend[1] if eigenes_wort else treffer.end()
            ende = _ausdruck_ende(text, start, bis_klammer=True)
        else:
            start = treffer.end()
            ende = umgebend[1] - 1
        bereiche.append(("notify-send", start, ende))

    # Die Aufrufe der eigenen Hilfsfunktionen. Nur die Felder, die deren
    # Deklaration als Beschriftung benannt hat - das zweite Argument von
    # createEntryField ist ein Wert und keine Aufschrift.
    hilfen, deklarationen = _hilfsfunktionen(text)
    for name, stellen in hilfen.items():
        for treffer in re.finditer(r"(?<![\w.])" + re.escape(name) + r"\s*\(",
                                   text):
            offen = treffer.end() - 1
            if offen in deklarationen:
                continue
            zu = _klammer_ende(text, offen)
            felder = _felder(text, offen + 1, zu)
            for nummer in stellen:
                if nummer < len(felder):
                    bereiche.append((f"{name}()", *felder[nummer]))

    gefunden = {}
    for schluessel, start, ende in bereiche:
        for wert, index, uebersetzt in _literale_im_bereich(text, start, ende):
            if not _ist_sichtbarer_text(wert, schluessel):
                continue
            # Derselbe Index kann aus zwei Bereichen kommen (eine
            # Eigenschaft INNERHALB eines Setzers). Er zaehlt einmal.
            gefunden[index] = {
                "datei": pfad.name,
                "zeile": zeilen[index],
                "schluessel": schluessel,
                "wert": wert,
                "uebersetzt": uebersetzt,
            }
    return [gefunden[k] for k in sorted(gefunden)]


def _vorlagen() -> list[Path]:
    return sorted(TEMPLATES.glob("ags-*.template"))


def _alle_funde() -> list[dict]:
    return [fund for pfad in _vorlagen()
            if pfad.name != I18N_TEMPLATE
            for fund in sichtbare_zeichenketten(pfad)]


def test_der_scan_liest_die_vorlagen_wirklich():
    """Der blinde Fleck der Messung, offen gehalten.

    Eine Suche, die nichts oeffnet, meldet dasselbe "sauber" wie ein
    Baum, in dem nichts falsch ist. Weder die Zahl der Dateien noch die
    der Funde laesst sich von einem verirrten Pfad erfuellen.
    """
    vorlagen = _vorlagen()
    assert len(vorlagen) > 20, (
        f"nur {len(vorlagen)} Vorlagen unter {TEMPLATES} - die Messung "
        "liest die Oberflaeche nicht, ihr Ergebnis bedeutet also nichts")

    funde = _alle_funde()
    assert len(funde) > 150, (
        f"nur {len(funde)} sichtbare Zeichenketten in {len(vorlagen)} "
        "Vorlagen gefunden - das Muster hat aufgehoert zu greifen")


def test_keine_sichtbare_zeichenkette_ist_fest_verdrahtet():
    """Die Regel.

    Was hier steht, liest ein Mensch. Steht es nicht im Katalog, liest
    ein englischer Nutzer Deutsch - und zwar mitten in einer Oberflaeche,
    deren Rest sich uebersetzt hat.
    """
    fest = [f"{f['datei']}:{f['zeile']} {f['schluessel']}: {f['wert']}"
            for f in _alle_funde()
            if not f["uebersetzt"] and f["wert"] not in EIGENNAMEN]
    assert fest == [], (
        f"{len(fest)} sichtbare Zeichenketten laufen nicht durch _():\n  "
        + "\n  ".join(fest))


def test_die_ausnahme_ist_noch_die_ausnahme():
    """Die Ausnahmeliste, gegen den Baum gehalten.

    Eine Ausnahme, die niemand nachrechnet, wird zur Regel: bliebe ein
    Name in EIGENNAMEN stehen, nachdem das Thema umbenannt oder
    entfernt wurde, deckte der Eintrag ab morgen irgendetwas anderes ab -
    oder gar nichts, und niemand raeumte ihn weg.
    """
    gefunden = {f["wert"] for f in _alle_funde() if not f["uebersetzt"]}
    veraltet = sorted(set(EIGENNAMEN) - gefunden)
    assert veraltet == [], (
        "diese Eigennamen stehen in der Ausnahmeliste, aber in keiner "
        "Vorlage mehr: " + ", ".join(veraltet))


def test_die_domaene_ist_stabil():
    """Der Name steht im Dateinamen des .mo. Wer ihn aendert, macht jede
    installierte Uebersetzung unauffindbar - ohne einen Fehler, denn
    gettext faellt still auf den msgid zurueck."""
    vorlage = (TEMPLATES / I18N_TEMPLATE).read_text(encoding="utf-8")
    assert f'export const DOMAIN = "{DOMAIN}"' in vorlage


def test_jede_vorlage_mit_uebersetzung_holt_sich_auch_die_funktion():
    """`_` ist keine eingebaute Funktion.

    Ohne den Import uebersetzt die Datei nicht - sie stuerzt ab, und
    zwar erst, wenn jemand das Fenster oeffnet. Ein Import, den der
    Buendler nicht aufloest, faellt frueher auf als ein Fenster, das
    beim Klick verschwindet.
    """
    ohne = []
    for pfad in _vorlagen():
        if pfad.name == I18N_TEMPLATE:
            continue
        text = _ohne_kommentare(pfad.read_text(encoding="utf-8"))
        if not re.search(r"(?<![\w$])_\(", text):
            continue
        if "utils/i18n" not in text and "./i18n" not in text:
            ohne.append(pfad.name)
    assert ohne == [], (
        "diese Vorlagen rufen _() ohne es zu importieren: " + ", ".join(ohne))


# Die Aufrufe, aus denen ein Katalogeintrag werden muss. Dieselben zwei
# Muster wie in tests/installer/test_i18n.py und aus demselben Grund
# getrennt: `ngettext(` endet nicht auf `_(`.
AUFRUF_RE = re.compile(r'(?<![\w$])_\(\s*"((?:[^"\\]|\\.)*)"')
MEHRZAHL_RE = re.compile(
    r'ngettext\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"')


# `pgettext("slider axis", "W")` wird im Katalog zu ZWEI Zeilen -
# msgctxt ueber msgid -, und nur beide zusammen sind der Eintrag: ein
# blosses `msgid "W"` waere der Eintrag OHNE Zusatz und damit ein
# anderer. Gemessen am 17.08.2026, siehe pgettext() in utils/i18n.ts.
ZUSATZ_RE = re.compile(
    r'(?<!n)pgettext\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"')


def _msgids(text: str) -> list[tuple[str, str]]:
    """(Text zum Anzeigen, Zeichenfolge, die im Katalog stehen muss)."""
    gefunden = [(m, f'msgid "{m}"') for m in AUFRUF_RE.findall(text)]
    for einzahl, mehrzahl in MEHRZAHL_RE.findall(text):
        gefunden.append((einzahl, f'msgid "{einzahl}"'))
        gefunden.append((mehrzahl, f'msgid_plural "{mehrzahl}"'))
    for zusatz, text_ in ZUSATZ_RE.findall(text):
        gefunden.append((f"{text_} [{zusatz}]",
                         f'msgctxt "{zusatz}"\nmsgid "{text_}"'))
    return gefunden


def test_der_deutsche_katalog_ist_da_und_nicht_leer():
    assert PO_FILE.exists(), (
        f"{PO_FILE.relative_to(REPOSITORY)} fehlt - Deutsch waere dann "
        "nicht gepflegt, und das war die Meldung")
    text = PO_FILE.read_text(encoding="utf-8")
    uebersetzt = re.findall(r'^msgid "(.+)"\nmsgstr "(.+)"', text, re.M)
    assert len(uebersetzt) > 100, (
        f"nur {len(uebersetzt)} uebersetzte Eintraege im Katalog - ein "
        "deutscher Nutzer laese seine Oberflaeche auf Englisch")


def test_jeder_eintrag_des_katalogs_ist_uebersetzt():
    """Ein leerer msgstr heisst: der Nutzer liest Englisch, obwohl er
    Deutsch gewaehlt hat."""
    text = PO_FILE.read_text(encoding="utf-8")
    eintraege = re.findall(r'^msgid "(.+)"\nmsgstr "(.*)"', text, re.M)
    for einzahl, mehrzahl, block in re.findall(
            r'^msgid "(.+)"\nmsgid_plural "(.+)"\n'
            r'((?:msgstr\[\d+\] ".*"\n)+)', text, re.M):
        formen = re.findall(r'msgstr\[\d+\] "(.*)"', block)
        assert formen, f"{einzahl}/{mehrzahl} hat gar keine Mehrzahlformen"
        eintraege.extend((f"{einzahl}/{mehrzahl}", form) for form in formen)
    assert len(eintraege) > 100, (
        f"nur {len(eintraege)} Eintraege ausgelesen - 'nichts ohne "
        "Uebersetzung' ist auch die Antwort auf eine leere Liste")
    ohne = [msgid for msgid, msgstr in eintraege if not msgstr]
    assert ohne == [], f"ohne Uebersetzung: {ohne}"


def test_jeder_msgid_der_vorlagen_steht_im_katalog():
    """Ein msgid im Quelltext ohne Eintrag im Katalog heisst: ein
    deutscher Nutzer sieht an dieser Stelle still Englisch."""
    katalog = PO_FILE.read_text(encoding="utf-8")

    fehlend = []
    geprueft = 0
    for pfad in _vorlagen():
        text = _ohne_kommentare(pfad.read_text(encoding="utf-8"))
        for anzeige, gesucht in _msgids(text):
            geprueft += 1
            if gesucht not in katalog:
                fehlend.append(f"{pfad.name}: {anzeige}")

    assert geprueft, "es wurde ueberhaupt keine uebersetzte Meldung geprueft"
    assert fehlend == [], (
        "msgids ohne Katalogeintrag: " + "; ".join(fehlend))


# --------------------------------------------------------------------
# Das zweite Netz
# --------------------------------------------------------------------
#
# WARUM ES ZWEI GIBT
#     Die Suche oben kennt Eigenschaften und Setzer. Sie ist genau und
#     sie hat einen blinden Fleck, der am 17.08.2026 gemessen wurde:
#
#         const POWER_BUTTONS: Array<[string, string, string, string]> = [
#           [ICONS.shutdown, "Herunterfahren", "shutdown", ...],
#
#     Fuenf Beschriftungen in einer Tabelle von Tupeln. Sie werden erst
#     beim Durchlaufen zu einem Argument, stehen also neben keiner
#     Eigenschaft und in keinem Aufruf mit einem benannten Parameter -
#     die erste Suche sah KEINE davon.
#
#     Dieses Netz kennt dafuer die Struktur gar nicht und fragt nur:
#     steht hier ein deutsches Wort? Es findet damit alles, was die
#     erste Suche verpasst, und verpasst dafuer alles, was schon auf
#     Englisch dasteht. Zusammen decken sie sich gegenseitig ab; einzeln
#     tut es keines von beiden.
#
# WAS NICHT ZAEHLT
#     Meldungen an console.error/console.warn/console.log und der Text
#     eines new Error(): sie stehen im Protokoll und nicht auf dem
#     Schirm. Sie duerfen deutsch bleiben, und sie sind es reichlich.
DIAGNOSE_RE = re.compile(r"(?:console\.\w+|new\s+Error)\s*\(")

# Ein Wort, das es nur im Deutschen gibt, oder ein Umlaut.
#
# DIE PARTIZIPIEN STEHEN SEIT DEM 02.09.2026 MIT DRIN, und der Fall, der
# sie erzwungen hat, ist lehrreich:
#
#     const zustand = device.connected ? "Verbunden"
#       : device.paired ? "Gekoppelt" : "Gefunden"
#     ...
#     unterzeile: `${zustand} • ${device.address}`
#
#     Drei deutsche Beschriftungen in ags-bluetooth.template, die durch
#     BEIDE Netze fielen. Durch das strukturelle, weil das Literal ueber
#     eine VARIABLE in die Senke laeuft - an der Senke steht dann ein
#     Template-Literal, dessen Woerter die Einsetzung wegnimmt. Und
#     durch dieses hier, weil die Liste die INFINITIVE kannte
#     ("Verbinden", "Trennen", "Speichern") und nicht die PARTIZIPIEN.
#     NACHGEMESSEN: "Herunterfahren" -> Treffer, "Gerät" -> Treffer,
#     "Verbunden" -> KEIN Treffer.
#
# WARUM EINE WORTLISTE UND NICHT DEM DATENFLUSS FOLGEN
#     Weil der Datenfluss hier nicht entscheidbar ist, und das ist
#     GEMESSEN und nicht befuerchtet: eine einstufige Verfolgung von
#     const/let in eine Senke ergab 920 Treffer, ueberwiegend
#     Maschinenwerte ("bar-module", "playerctl next", "media.class").
#     Der Grund steht in derselben Messung - an einer SENKE sagt der
#     Schluesselname, dass der Wert angezeigt wird; in einer ZUWEISUNG
#     sagt er nichts. `const zustand = "Verbunden"` und
#     `const klasse = "aktiv"` sind strukturell dasselbe. Die
#     Unterscheidung braeuchte echte Gueltigkeitsbereiche,
#     Schliessungen und Weitergabe durch Funktionen - mit regulaeren
#     Ausdruecken ueber TypeScript ist das die Sorte Erkennung, die
#     grundlos rot ist und darum abgeschaltet wird. Eine Zusicherung mit
#     Fehlalarmen ist schlimmer als keine.
#
# DASS DIESE LISTE EINE UNTERGRENZE IST, UND WARUM SIE TROTZDEM RICHTIG
# IST
#     Sie ist per Bauart unvollstaendig. Jedes deutsche Wort, das nicht
#     darin steht und keinen Umlaut hat, faellt durch - "Leiste",
#     "Thema", "Dock" tun es heute. Das ist kein Versagen der Liste,
#     sondern ihre Form: sie nennt Woerter, und Woerter kann man immer
#     weitere finden.
#
#     Sie ist trotzdem die richtige Wahl, weil die Alternative nicht
#     "vollstaendig" heisst, sondern "Fehlalarme". Eine Liste, die zu
#     wenig findet, kostet einen Fund; eine Erkennung, die zu viel
#     findet, kostet die ganze Zusicherung, weil jemand sie abschaltet.
#
#     ERWEITERN IST DESHALB VORGESEHEN UND KEIN EINGESTAENDNIS. Wer ein
#     deutsches Wort im Quelltext findet, das hier durchfaellt, traegt
#     es ein - GEMESSEN am 02.09.2026 kostet das nichts: die vierzehn
#     Partizipien unten ergaben im ganzen Baum 3 Treffer, genau die drei
#     echten Faelle, 0 Fehlalarme, auch mit IGNORECASE.
#
#     Dieselbe Ehrlichkeit gilt fuer die Umlaut-Regel in
#     tests/src/test_desktop_i18n.py, und sie steht dort mit demselben
#     Satz: Untergrenze, nicht Beweis.
DEUTSCH_RE = re.compile(
    r"[ÄÖÜäöüß]"
    r"|(?<![\w-])(?:der|die|das|und|oder|mit|fuer|nicht|kein|keine|eine|"
    r"einen|zum|zur|vom|von|auf|ist|wird|werden|sind|dem|den|des|wie|noch|"
    r"schon|bitte|alle|alles|ohne|beim|dieser|diese|hat|haben|Herunterfahren|"
    r"Neustart|Bereitschaft|Sperren|Abmelden|Verbinden|Trennen|Speichern|"
    r"Abbrechen|Suchen|Laden|Fenster|Farben|Einstellungen|Beenden|Anzeigen|"
    # Die Partizipien - siehe den Block darueber. Ein Zustand IN WORTEN
    # ist die haeufigste Beschriftung, die keinen Umlaut braucht.
    r"Verbunden|Getrennt|Gekoppelt|Gefunden|Gespeichert|Geladen|Gesperrt|"
    r"Beendet|Fehlgeschlagen|Unbekannt|Angehalten|Abgebrochen|"
    r"Aktualisiert|Uebersprungen|"
    # Zwei Geraetenamen, die im Deutschen anders geschrieben werden als
    # im Englischen. GEMESSEN am 02.09.2026: sie ergeben 4 zusaetzliche
    # Treffer, alle echt (die Tooltips von ags-privacy-scripts), 0
    # Fehlalarme. Kein Zusammenstoss mit "camera"/"microphone" - die
    # unterscheiden sich im ersten Buchstaben, und daran aendert
    # IGNORECASE nichts.
    r"Mikrofon|Kamera)"
    r"(?![\w-])", re.IGNORECASE)

# WAS ICH GEMESSEN UND WIEDER VERWORFEN HABE, damit es niemand ein
# zweites Mal versucht: "Aktualisierung", "Bildschirm" und
# "Lautstaerke" schienen naheliegend und ergaben je einen FEHLALARM -
#
#     ags-control-center.template:660    "settings:aktualisierung"
#                                        ein Seitenname, kein Satz
#     ags-control-center.template:1139   "${vol.lautstaerke}%"
#                                        ein Feldname in einer Einsetzung
#     ags-bar.template:2834              ein Kommentarrest
#
# Drei Woerter, drei Fehlalarme - und jeder von ihnen haette die
# Zusicherung bei jedem Lauf rot gemacht, ohne dass etwas falsch ist.
# Das ist der Grund, aus dem diese Liste WAECHST und nicht RAET: ein
# Wort kommt hinein, wenn es gemessen keinen Fehlalarm erzeugt.

# Die eine Stelle, an der ein deutsches Wort stehen BLEIBEN muss, und
# der Grund, aus dem es dort steht.
#
#     ags-network-scripts.template ist ein SHELL-Skript und schreibt
#     "Kabelverbindung" bzw. "Nicht verbunden" auf die Standardausgabe.
#     ags-network.template vergleicht darauf, um die Verbindungsart zu
#     erkennen (`if (name.trim() === WIRED_NAME) type = "ethernet"`).
#     Diese zwei Woerter sind damit ein PROTOKOLL zwischen zwei
#     Bausteinen und zugleich das, was der Nutzer liest.
#
#     Uebersetzt man sie, scheitert die Erkennung an der Sprache.
#     Uebersetzt man sie nur beim Anzeigen, steht die Vokabel des
#     Skripts ein zweites Mal in TypeScript - genau die zweite Wahrheit,
#     vor der dieser Baum an einem Dutzend Stellen warnt.
#
#     Richtig ist, dass das Skript eine MASCHINENANTWORT gibt und das
#     Widget sie beschriftet. Das aendert die Schnittstelle von
#     ags-network-scripts.template und trifft jeden ihrer Leser; es ist
#     eine eigene Aufgabe und keine Zeile hier. Bis dahin steht sie
#     namentlich hier, damit sie niemand uebersieht.
#
# DIE AUSNAHME HAENGT SEIT DEM 02.09.2026 AM ORT UND NICHT AM WERT, und
# das war ein echter Fehler und keine Verschoenerung.
#
#     Vorher war es eine blosse Wortliste. Damit entschuldigte sie JEDES
#     Vorkommen dieser Woerter - auch das, das auf dem Schirm steht.
#     GEMESSEN: dieselben zwei Woerter standen in ags-network.template
#     als `titel:` in drei Zeilen (556, 777, 787), also als Aufschrift
#     fuer den Nutzer, und die Ausnahme deckte sie mit.
#
#     Das ist dieselbe Krankheit wie eine Pruefung, die nichts sieht,
#     nur andersherum: eine AUSNAHME, DIE ZU VIEL DECKT. Und sie ist
#     schwerer zu bemerken, weil sie sich als Sorgfalt liest.
#
# WAS EIN "ORT" HIER IST
#     Die Datei. Praeziser waere die Senke - Standardausgabe eines
#     Skripts gegen `titel:` eines Widgets -, und das waere auch
#     richtiger. Es ist hier nicht noetig: die Skripte HABEN keine
#     andere Senke als ihre Ausgabe, und die Widgets haben keinen Grund,
#     ein Protokollwort zu drucken. Die Datei trennt die zwei Faelle
#     also vollstaendig, und eine feinere Unterscheidung waere Aufwand
#     ohne Wirkung.
#
#     Der Preis steht dabei: schreibt jemand in ags-network-scripts.
#     template einen NEUEN deutschen Satz, deckt ihn diese Ausnahme
#     NICHT - sie nennt die drei Woerter, die ein Protokoll sind, und
#     kein Freibrief fuer die Datei.
#     GEZAEHLT am 02.09.2026, wo die drei Woerter wirklich stehen:
#
#         ags-network-scripts.template:190   echo "Kein Drucker"
#         ags-network-scripts.template       "Kabelverbindung",
#                                            "Nicht verbunden"
#         ags-network.template:288/289       dieselben zwei als const,
#                                            und als `titel:` angezeigt
#         ags-control-center.template:292    `|| "Kein Drucker"` als
#                                            Rueckfall - also ANGEZEIGT
#
#     Alle drei stehen im NETZWERK-Skript; einen Drucker-Skriptbaustein
#     gibt es nicht. Die zwei Widget-Stellen sind keine Ausnahme,
#     sondern der Befund - sie gehen seit heute durch den Katalog.
#
# WARUM DIE ZWEI WIDGETS SEIT DEM 02.09.2026 EBENFALLS DARIN STEHEN, und
# es ist NICHT dieselbe Ausnahme wie beim Skript
#     Das Skript SCHREIBT die Woerter, die Widgets VERGLEICHEN darauf.
#     Beide brauchen den Wortlaut, und keins von beiden darf ihn
#     uebersetzen - ein uebersetztes Protokollwort bricht den Vergleich,
#     und zwar still.
#
#     Was die Widgets seit heute NICHT mehr tun, ist ihn ANZEIGEN. In
#     ags-network.template macht aufschrift() aus dem Protokollwort
#     einen Satz aus dem Katalog, in ags-control-center.template dieselbe
#     Funktion desselben Namens. Die Konstanten bleiben also als
#     VERGLEICHSWERT stehen, und genau dafuer gilt die Ausnahme.
#
#     Der Unterschied ist wichtig, weil er die Grenze der Ausnahme
#     bestimmt: sie deckt einen Wert, der mit `===` verglichen wird -
#     nicht einen, der in ein `titel:` fliesst. Wer hier eine Datei
#     hinzufuegt, muss denselben Satz sagen koennen.
#
#     DIE VOLLSTAENDIGE LOESUNG steht seit langem im Absatz darueber und
#     ist noch offen: das Skript gibt eine KENNUNG aus ("wired", "none"),
#     das Widget beschriftet sie. Dann braucht keine Datei diese
#     Ausnahme. Es aendert die Schnittstelle des Skripts und trifft jeden
#     ihrer Leser - eine eigene Aufgabe, und der Grund, aus dem sie hier
#     namentlich steht.
PROTOKOLL_DES_SKRIPTS = {
    "ags-network-scripts.template": (
        "Kabelverbindung", "Nicht verbunden", "Kein Drucker"),
    # Vergleichswerte, keine Aufschriften - siehe den Absatz darueber.
    "ags-network.template": ("Kabelverbindung", "Nicht verbunden"),
    "ags-control-center.template": ("Nicht verbunden", "Kein Drucker"),
}

# --------------------------------------------------------------------
# Die Saetze der Schalenskripte, und warum sie NOCH nicht durch den
# Katalog gehen
# --------------------------------------------------------------------
#
# SECHS SAETZE IN ZWEI DATEIEN, und sie stehen auf dem Schirm:
#     ags-updates-scripts.template setzt `short=`, und dieselbe Datei
#     macht daraus zwei Zeilen weiter den `tooltip` des Leistenmoduls.
#     ags-privacy-scripts.template setzt `tooltip=` unmittelbar.
#
# WARUM SIE HIER STEHEN UND NICHT BEHOBEN SIND: die Entscheidung ist
# gefallen, die Umsetzung braucht eine Datei, die diesem Auftrag nicht
# gehoert.
#
# DIE ENTSCHEIDUNG, und meine erste Vermutung war FALSCH
#     Zuerst hielt ich `gettext(1)` zur Laufzeit fuer zu teuer - "ein
#     Prozessstart je Takt". GEMESSEN ist das falsch: das
#     Aktualisierungsmodul laeuft mit intervalMs 600000, also alle ZEHN
#     MINUTEN (ags-bar.template). Vier Aufrufe alle zehn Minuten sind
#     nichts.
#
#     Was gegen die Laufzeit spricht, ist ein anderer gemessener Grund:
#
#         /usr/bin/gettext.sh gehoert dem Paket `gettext`, 20,79 MiB,
#         und gettext ist NICHT in der Gruppe `base` - auf dieser
#         Maschine liegt es nur als Abhaengigkeit eines anderen Pakets.
#         In den PKGBUILDs steht es als makedepends, NICHT als depends.
#
#     Eine Uebersetzung zur Laufzeit machte daraus also eine neue
#     LAUFZEIT-Abhaengigkeit des ganzen Schreibtischs - fuer sechs
#     Saetze. Und wo sie fehlte, zeigte das Leistenmodul nichts, ohne
#     eine Zeile Erklaerung.
#
#     RICHTIG IST DIE ERSETZUNG BEIM ERZEUGEN. Die Vorlagen laufen
#     ohnehin durch den Generator - ags-updates-scripts.template traegt
#     drei {{PLATZHALTER}} -, und die Sprache der Maschine steht beim
#     Erzeugen fest. Der Erzeugungslauf ist ausserdem GENAU das, was ein
#     Sprachwechsel ausloest; settings/zepos_settings_gui/model.py sagt
#     es im Wortlaut ("Leiste, Dock und die uebrigen Fenster nach einem
#     Erzeugungslauf"). Die Auffrischung stimmt damit schon, ohne dass
#     jemand etwas verspricht.
#
#     Der Preis, ausgeschrieben: die erzeugte Datei traegt EINE Sprache.
#     Wer umstellt, braucht einen Erzeugungslauf - genau das, was fuer
#     die Leiste ohnehin gilt.
#
# WAS NOCH FEHLT: der Generator (src/icon_manager.py) gehoert diesem
# Auftrag nicht. Bis das entschieden ist, stehen die sechs Saetze hier -
# einzeln, mit ihrer Datei, und NICHT als Freibrief fuer die Dateien.
# Ein SIEBTER Satz in derselben Datei faellt auf.
NOCH_NICHT_IM_KATALOG = {
    "ags-updates-scripts.template": (
        "Die letzte Aktualisierung ist gescheitert.",
        "Neue Vorlagen sind eingespielt - die Konfiguration ist noch die alte.",
        "Die Selbstaktualisierung ist abgeschaltet (update.enabled).",
    ),
    # DIE WERTE SO, WIE DER LESER SIE SIEHT, und nicht so, wie sie in
    # der Datei stehen. In einem Shell-Skript endet ein
    # Anfuehrungszeichen die Zeichenkette auch dann, wenn eine
    # Befehlseinsetzung `$( ... )` noch offen ist - der Leser hier
    # kennt Shell-Regeln nicht und darf sie auch nicht kennen (er
    # dient TypeScript). Die Bereiche zerfallen deshalb an den
    # inneren Anfuehrungszeichen.
    #
    # Abgeschrieben ist hier also die MESSUNG und nicht die Absicht -
    # wer die Saetze uebersetzt, loescht diese Eintraege ganz und
    # nicht Stueck fuer Stueck.
    "ags-privacy-scripts.template": (
        "Mikrofon: $(printf '%s' ",
        # Ein ECHTER Zeilenumbruch darin, kein "\\n": der Wert laeuft in
        # der Vorlage ueber zwei Zeilen.
        " | paste -sd ', ')\nKamera: $(printf '%s' ",
        "Kamera: $(printf '%s' ",
    ),
}

# UND ZWEI, DIE DIE WORTLISTE HEUTE NICHT SIEHT - gemessen, damit die
# Zahl ehrlich ist und niemand "sechs" fuer "alle" haelt:
#
#     ags-updates-scripts.template:107  "$base Arch-Aktualisierungen
#                                        liegen bereit."
#     ags-privacy-scripts.template       die dritte Tooltip-Zeile, die
#                                        mit den zwei anderen in einem
#                                        Literalbereich liegt
#
# "Arch-Aktualisierungen" faellt durch, weil der Bindestrich davor zum
# Wort gehoert und die Wortgrenze damit nicht greift. Das ist die
# Untergrenze der Wortliste in Zahlen - siehe den Block bei DEUTSCH_RE.


def test_keine_deutsche_zeichenkette_bleibt_in_der_oberflaeche():
    """Das zweite Netz - siehe den Block darueber.

    DIE SCHALENVORLAGEN SIND SEIT DEM 02.09.2026 MIT DABEI. Sie waren
    ausgenommen ("if pfad.name.endswith('-scripts.template'): continue"),
    und das war eine Ausnahme fuer eine ganze Dateiart - genau die Form,
    die zu viel deckt. Was darin steht, ist nicht weniger sichtbar:
    ags-updates-scripts.template setzt `short=`, und das wird in
    derselben Datei zum `tooltip` des Leistenmoduls.

    Moeglich wurde das erst durch die Reparatur an _ohne_kommentare():
    ein Entferner, der nur `//` kennt, liest in einem Shell-Skript die
    KOMMENTARE als Quelltext. GEMESSEN: 113 Scheinkandidaten allein in
    ags-network-scripts.template.
    """
    deutsch = []
    for pfad in _vorlagen():
        text = _ohne_kommentare(pfad.read_text(encoding="utf-8"),
                                shell=pfad.name.endswith("-scripts.template"))
        diagnosen = [(t.end() - 1, _klammer_ende(text, t.end() - 1))
                     for t in DIAGNOSE_RE.finditer(text)]
        # Die Ausnahme gilt je DATEI und nicht ueberall - siehe den Block
        # bei PROTOKOLL_DES_SKRIPTS. Dazu die sechs Saetze, deren Weg in
        # den Katalog entschieden aber noch nicht gebaut ist; auch sie
        # haengen an ihrer Datei und sind einzeln genannt.
        erlaubt = (PROTOKOLL_DES_SKRIPTS.get(pfad.name, ())
                   + NOCH_NICHT_IM_KATALOG.get(pfad.name, ()))
        for anfang, ende in _literal_bereiche(text):
            wert = text[anfang + 1:ende - 1]
            if not wert.strip() or wert in erlaubt:
                continue
            if not DEUTSCH_RE.search(wert):
                continue
            if any(a < anfang < b for a, b in diagnosen):
                continue
            zeile = text[:anfang].count("\n") + 1
            deutsch.append(f"{pfad.name}:{zeile} {wert[:70]}")
    assert deutsch == [], (
        f"{len(deutsch)} deutsche Zeichenketten stehen noch im "
        "Quelltext der Oberflaeche:\n  " + "\n  ".join(deutsch))


def test_das_zweite_netz_faengt_ueberhaupt_etwas():
    """Der Selbsttest des Musters.

    Ein Muster, das nichts mehr trifft, meldet dasselbe "sauber" wie
    eine Oberflaeche ohne einen deutschen Rest. Der Katalog ist voller
    deutscher Saetze - findet das Muster dort keinen, ist es kaputt und
    die Zusicherung darueber wertlos.
    """
    katalog = PO_FILE.read_text(encoding="utf-8")
    treffer = DEUTSCH_RE.findall(katalog)
    assert len(treffer) > 50, (
        f"das Muster findet nur {len(treffer)} deutsche Woerter im "
        "deutschen Katalog - es hat aufgehoert zu greifen")


def test_die_msgids_sind_englisch():
    """Die Ausgangssprache ist Englisch - dieselbe Entscheidung wie im
    Installer, deren Begruendung im Kopf von installer/core/i18n.py
    steht: Englisch ist der msgid, Deutsch ein Katalog wie jeder andere.

    Ein deutscher msgid faellt sonst erst auf, wenn eine dritte Sprache
    dazukommt und der Uebersetzer Deutsch lesen koennen muss.
    """
    deutsch = []
    for pfad in _vorlagen():
        text = _ohne_kommentare(pfad.read_text(encoding="utf-8"))
        for anzeige, _gesucht in _msgids(text):
            if re.search(r"[ÄÖÜäöüß]", anzeige):
                deutsch.append(f"{pfad.name}: {anzeige}")
    assert deutsch == [], (
        "diese msgids sind deutsch statt englisch: " + "; ".join(deutsch))


# --------------------------------------------------------------------
# Das dritte Netz: gemessen wird das ERGEBNIS und nicht die Quelle
# --------------------------------------------------------------------
#
# WAS AM 02.09.2026 DURCH ALLE VORHANDENEN NETZE GEFALLEN IST
#     Ein Parallelauftrag brachte zwei neue Saetze in den Katalog. Beide
#     standen danach mit `#, fuzzy` in de.po, und ihr msgstr trug die
#     Fortsetzungszeilen der alten, EINTEILIGEN Fassung noch angeklebt -
#     `msgmerge` hatte grob zugeordnet, als aus EINEM msgid mit "\n"
#     darin ZWEI wurden, und beide vorsichtshalber fuzzy gesetzt.
#
#         msgfmt nimmt einen fuzzy markierten Eintrag NICHT in die .mo
#         auf.
#
#     Ueber gettext nachgeschlagen, also so, wie die Oberflaeche fragt:
#
#         vorher      -> "VPN status unknown - NetworkManager is not
#                         responding."   (der msgid, also Englisch)
#         repariert   -> "VPN-Zustand unbekannt - NetworkManager
#                         antwortet nicht."
#
#     Ausgerechnet dieses Fenster soll einem deutschen Nutzer sagen, dass
#     niemand weiss, ob sein Verkehr geschuetzt ist. Auf Englisch sagt es
#     das dem, der kein Englisch liest, gar nicht.
#
# WARUM DIE ZWEI NETZE DARUEBER ES NICHT GESEHEN HABEN
#     test_jeder_eintrag_des_katalogs_ist_uebersetzt() liest den TEXT von
#     de.po und verlangt einen nicht leeren msgstr. Der war nicht leer -
#     er war DOPPELT. Und `#, fuzzy` steht eine Zeile DARUEBER und in
#     keinem seiner Muster.
#
#     Das ist die Gattung: geprueft wurde die EINGABE statt des
#     ERGEBNISSES. Der Katalog sah gepflegt aus, waehrend zwei Saetze der
#     Oberflaeche englisch blieben. Die zwei Netze bleiben trotzdem
#     stehen - sie sagen genauer, WELCHER Eintrag fehlt, und sie brauchen
#     kein msgfmt.
#
# WER IN DIESE GRUBE FAELLT
#     Jeder, der einen msgid AUFTEILT oder UMFORMULIERT und danach
#     `msgmerge` laufen laesst - also jeder, der einen Satz der
#     Oberflaeche verbessert. msgmerge markiert seine Vermutung
#     absichtlich als unsicher; nur sagt niemand hinterher, dass die
#     Unsicherheit den Eintrag aus dem ausgelieferten Katalog nimmt.

def _po_eintraege(text: str) -> dict[tuple[str, str], str]:
    """Jeder Eintrag von de.po als (zusatz, msgid) -> msgstr.

    DER ZUSATZ GEHOERT ZUM SCHLUESSEL, und das ist gemessen und nicht
    Vorsicht. Ein `msgctxt` unterscheidet zwei Eintraege mit DEMSELBEN
    msgid, und dieser Katalog hat drei davon (GEZAEHLT am 02.09.2026):

        msgid "Open"  ohne Zusatz            -> "Öffnen"   (ags-home)
        msgid "Open"  mit "wifi security"    -> "Offen"    (ags-network)
        msgid "L"     mit "monitor ... "     -> "Q"        (ags-wallpaper)
        msgid "P"     mit "monitor ... "     -> "H"

    Eine erste Fassung dieses Lesers hat den Zusatz uebergangen und
    genau diese drei als Fehlschlag gemeldet - "de.po sagt 'Offen', der
    Katalog gibt 'Öffnen'". Der Katalog war richtig, der Leser falsch:
    er hat zwei verschiedene Eintraege fuer einen gehalten. Wer hier
    kuerzt, baut eine Zusicherung, die dreimal grundlos rot ist und
    darum abgeschaltet wird.

    Nur die EINFACHEN Eintraege, keine Mehrzahlformen: die Zuordnung
    msgid -> genau ein msgstr gilt fuer sie nicht, und
    test_jeder_eintrag_des_katalogs_ist_uebersetzt() deckt sie schon ab.
    Der Kopfeintrag (msgid "") faellt heraus - er ist keine Beschriftung,
    sondern die Angabe zum Zeichensatz.

    Ungebrochen gelesen und nicht zusammengesetzt: de.po und die .pot
    sind `--no-wrap`, und der Kopf von po/desktop/extract.sh fuehrt aus,
    warum sie es bleiben muessen.
    """
    gefunden: dict[tuple[str, str], str] = {}
    for treffer in re.finditer(
            r'^(?:msgctxt "((?:[^"\\]|\\.)*)"\n)?'
            r'^msgid "((?:[^"\\]|\\.)+)"\n'
            r'^msgstr "((?:[^"\\]|\\.)*)"$',
            text, re.M):
        zusatz, msgid, msgstr = treffer.groups()
        gefunden[(zusatz or "", msgid)] = msgstr
    return gefunden


def test_kein_eintrag_des_katalogs_ist_ungenau_markiert():
    """`#, fuzzy` in einem AUSGELIEFERTEN Katalog heisst: still englisch.

    GIBT ES EINEN LEGITIMEN GRUND FUER SO EINEN EINTRAG? Ja, aber nicht
    hier - und das ist gemessen, nicht vermutet. GEZAEHLT am 02.09.2026:

        po/desktop/zepos-desktop.pot    1 Marke, auf dem KOPFEINTRAG
        po/desktop/de.po                0
        po/de.po                        0

    Die eine ist die Ausnahme, und sie steht in einer VORLAGE: xgettext
    schreibt sie auf den Kopfeintrag jeder .pot, damit ein Werkzeug
    erkennt, dass dort noch Platzhalter stehen ("FIRST AUTHOR
    <EMAIL@ADDRESS>, YEAR"). Eine .pot wird nie nachgeschlagen; sie ist
    die Liste der Fragen und keine Liste der Antworten.

    In einer de.po gibt es diesen Grund nicht. Ein fuzzy markierter
    Eintrag ist dort eine Uebersetzung, die dasteht und nicht
    ausgeliefert wird - die schlechteste der drei moeglichen Lagen, weil
    sie beim Lesen der Datei wie erledigte Arbeit aussieht. Wer eine
    Vermutung von msgmerge behalten will, prueft sie und nimmt die Marke
    weg; wer sie nicht prueft, hat keine Uebersetzung.

    Diese Zusicherung liest deshalb den Text. Die naechste baut den
    Katalog und fragt ihn - sie ist die staerkere, aber diese nennt den
    Grund beim Namen, und zwar ohne msgfmt.
    """
    text = PO_FILE.read_text(encoding="utf-8")
    ungenau = [zeile for zeile in text.splitlines()
               if zeile.startswith("#,") and "fuzzy" in zeile]
    assert ungenau == [], (
        f"{len(ungenau)} Eintrag/Eintraege in {PO_FILE.name} sind `#, fuzzy` "
        "markiert. msgfmt laesst solche Eintraege AUS der .mo weg - die "
        "Uebersetzung steht in der Datei und kommt beim Nutzer nicht an. "
        "Pruef die Vermutung von msgmerge und nimm die Marke weg, oder "
        "uebersetz neu.")


@pytest.mark.allow_subprocess
def test_der_gebaute_katalog_gibt_jede_uebersetzung_wirklich_heraus(tmp_path):
    """DAS ERGEBNIS, nicht die Quelle - und fuer JEDEN Eintrag.

    Gebaut wird mit msgfmt und gefragt wird mit gettext, also mit genau
    den zwei Werkzeugen, die zwischen de.po und dem Nutzer stehen:
    po/build.sh ruft msgfmt, und src/templates/ags-i18n.template fragt
    die Domaene `zepos-desktop` ueber dgettext. Was msgfmt weglaesst,
    kann diese Zusicherung nicht fuer vorhanden halten.

    VERGLICHEN WIRD MIT DEM ERWARTETEN TEXT und nicht bloss auf
    "ungleich dem msgid" geprueft. Zwei Gruende, beide gemessen:

      * Ein fuzzy markierter Eintrag gibt den MSGID zurueck. "Ungleich"
        faende ihn - aber nur, solange die Uebersetzung sich vom
        Englischen unterscheidet. "VPN" heisst auf Deutsch "VPN", und so
        ein Eintrag waere dann unpruefbar.
      * Der doppelte msgstr vom 02.09.2026 war AUCH ungleich dem msgid.
        Ein Satz, der sich selbst zweimal sagt, ist keine Uebersetzung -
        gegen den erwarteten Text gehalten faellt er auf, gegen den
        msgid gehalten nicht.

    DIE ZAHL TUT DIE ARBEIT MIT, und sie ist billig: msgfmt
    --statistics sagt, wieviele Meldungen uebersetzt und wieviele ungenau
    sind. GEMESSEN am 02.09.2026 zaehlte der Katalog des
    Parallelauftrags 434/2, wo er 436/0 haette haben muessen. Eine
    einzige ungenaue Meldung ist damit sichtbar, auch wenn ihre
    Uebersetzung zufaellig gleich dem msgid waere.

    WAS DIE ZWEI HAELFTEN JE ABDECKEN, damit niemand eine Luecke dort
    vermutet, wo keine ist, oder eine uebersieht, wo eine waere.
    NACHGERECHNET am 02.09.2026:

        msgfmt zaehlt                        445 uebersetzt, 0 ungenau
        einzeln nachgeschlagen (unten)       443 einfache Eintraege
        nur ueber die Zahl geprueft            2 Mehrzahl-Eintraege
        nicht gezaehlt                         1 Kopfeintrag

    Die zwei Mehrzahl-Eintraege gehen NICHT einzeln durch gettext -
    _po_eintraege() laesst sie aus, weil "ein msgid, ein msgstr" fuer
    sie nicht gilt. Ungenau markiert waeren sie trotzdem sichtbar, denn
    dann nennt die Zaehlung oben eine ungenaue Meldung. Was fuer sie
    fehlt, ist allein die Gegenprobe auf den WORTLAUT je Form; die liest
    test_jeder_eintrag_des_katalogs_ist_uebersetzt() aus der Quelle.
    """
    if shutil.which("msgfmt") is None:
        pytest.skip("msgfmt fehlt; es kommt mit dem Paket gettext")

    ziel = tmp_path / "de" / "LC_MESSAGES"
    ziel.mkdir(parents=True)
    gebaut = subprocess.run(
        ["msgfmt", "--statistics", "-o", str(ziel / f"{DOMAIN}.mo"),
         str(PO_FILE)],
        capture_output=True, text=True)
    assert gebaut.returncode == 0, (
        f"msgfmt uebersetzt {PO_FILE.name} nicht:\n{gebaut.stderr}")

    # msgfmt schreibt die Zaehlung auf STDERR, in der Sprache der
    # Umgebung. Gesucht wird deshalb nach den ZAHLEN und nicht nach den
    # Woertern: "436 uebersetzte Meldungen" und "436 translated
    # messages" haben dieselbe erste Zahl, und ein Lauf auf einem
    # englischen Rechner soll dasselbe messen.
    zahlen = [int(n) for n in re.findall(r"(\d+)", gebaut.stderr)]
    assert zahlen, f"msgfmt nennt keine Zaehlung: {gebaut.stderr!r}"

    erwartet = _po_eintraege(PO_FILE.read_text(encoding="utf-8"))
    assert len(erwartet) > 100, (
        f"nur {len(erwartet)} Eintraege ausgelesen - 'alles kommt an' ist "
        "auch die Antwort auf eine leere Liste")

    # "ungenau" und "unuebersetzt" tauchen in der Zaehlung nur auf, wenn
    # es sie GIBT. Ihr blosses Vorkommen ist deshalb schon der Befund;
    # welche Zahl davorsteht, sagt die Meldung.
    assert "fuzz" not in gebaut.stderr and "ungenau" not in gebaut.stderr, (
        f"msgfmt zaehlt ungenaue Meldungen in {PO_FILE.name} - genau die "
        f"landen NICHT in der .mo: {gebaut.stderr.strip()}")
    assert "untransl" not in gebaut.stderr and "unuebersetzt" not in gebaut.stderr, (
        f"msgfmt zaehlt unuebersetzte Meldungen: {gebaut.stderr.strip()}")

    katalog = gettext.translation(DOMAIN, str(tmp_path), languages=["de"])

    def entmaskiert(rohtext: str) -> str:
        """Die Maskierungen der .po-Syntax aufloesen.

        Die Rohfassung aus der Datei traegt sie noch, gettext gibt den
        fertigen Text - verglichen werden muss an derselben Fassung.
        Diese zwei Folgen sind die, die in diesem Katalog vorkommen.
        """
        return rohtext.replace('\\"', '"').replace("\\n", "\n")

    fehlend = []
    for (zusatz, msgid), msgstr in sorted(erwartet.items()):
        erwarteter = entmaskiert(msgstr)
        # Mit Zusatz ueber pgettext, ohne ueber gettext - genau wie die
        # Vorlagen fragen (`pgettext("wifi security", "Open")` in
        # ags-network.template). Ein Zusatz ist im .mo Teil des
        # Schluessels; ihn beim Nachschlagen weglassen faende den
        # falschen Eintrag oder keinen.
        if zusatz:
            geliefert = katalog.pgettext(entmaskiert(zusatz),
                                         entmaskiert(msgid))
        else:
            geliefert = katalog.gettext(entmaskiert(msgid))
        if geliefert != erwarteter:
            wo = f"{msgid!r}" if not zusatz else f"{msgid!r} [{zusatz}]"
            fehlend.append(f"{wo}: de.po sagt {erwarteter!r}, der "
                           f"gebaute Katalog gibt {geliefert!r}")
    assert fehlend == [], (
        f"{len(fehlend)} Uebersetzung(en) stehen in {PO_FILE.name} und "
        "kommen aus dem gebauten Katalog nicht heraus - fast immer eine "
        "`#, fuzzy`-Marke, die msgfmt den Eintrag weglassen laesst:\n  "
        + "\n  ".join(fehlend[:10]))


# --------------------------------------------------------------------
# Das Loch, das die Ortsbindung selbst aufgemacht hat
# --------------------------------------------------------------------
#
# WAS DIE AUSNAHME KOSTET, und ich habe es gemessen statt gehofft:
#     PROTOKOLL_DES_SKRIPTS erlaubt "Kabelverbindung" und "Nicht
#     verbunden" in ags-network.template, weil sie dort VERGLEICHSWERTE
#     sind. Damit ist das Literal an seiner Deklaration entschuldigt -
#     und niemand hindert jemanden daran, die KONSTANTE wieder direkt
#     anzuzeigen.
#
#     GEGENPROBE am 02.09.2026: `titel: aufschrift(WIRED_NAME)` zurueck
#     auf `titel: WIRED_NAME` gestellt - alle 13 Zusicherungen blieben
#     GRUEN. Der Fehler von heute morgen waere unbemerkt
#     zurueckgekommen.
#
# WARUM DIE ZWEI NETZE IHN NICHT SEHEN KOENNEN
#     Das strukturelle Netz liest LITERALE an sichtbaren Senken. An
#     `titel: WIRED_NAME` steht kein Literal, sondern ein BEZEICHNER -
#     und ein Bezeichner an einer Senke ist nicht beurteilbar:
#     `titel: connInfo.name` ist voellig richtig (ein SSID ist ein
#     Eigenname). Dieselbe Unentscheidbarkeit wie bei der
#     Datenflussverfolgung, nur eine Zeile spaeter.
#
#     Das sprachliche Netz sieht das Literal - aber genau dort, wo die
#     Ausnahme gilt.
#
# DESHALB EINE EIGENE, ENGE ZUSICHERUNG. Sie beurteilt keine Bezeichner
# im Allgemeinen, sondern nennt die vier Konstanten beim Namen und sagt,
# was mit ihnen erlaubt ist. Eine Ausnahme, die ein Risiko aufmacht,
# bekommt eine Wache fuer genau dieses Risiko.
PROTOKOLL_KONSTANTEN = {
    "ags-network.template": ("WIRED_NAME", "NOT_CONNECTED"),
    "ags-control-center.template": ("SKRIPT_NICHT_VERBUNDEN",
                                    "SKRIPT_KEIN_DRUCKER"),
}

# Die Funktion, die aus einem Protokollwort eine Aufschrift macht. In
# beiden Dateien heisst sie gleich, und das ist Absicht - es ist
# dieselbe Naht zwischen denselben zwei Rollen.
AUFSCHRIFT = "aufschrift("


def test_ein_protokollwort_kommt_nur_ueber_aufschrift_auf_den_schirm():
    """Die vier Konstanten duerfen VERGLICHEN, aber nicht ANGEZEIGT werden.

    Erlaubt ist genau dreierlei, und jedes ist an der Zeile zu erkennen:

      die Deklaration     `const WIRED_NAME = "..."`
      ein Vergleich       `=== WIRED_NAME`, `!== NOT_CONNECTED`
      der Weg zum Schirm  irgendwo in derselben Zeile `aufschrift(`

    Alles andere ist ein Protokollwort auf dem Weg an eine Stelle, die
    diese Zusicherung nicht kennt - und das ist genau der Fall, den sie
    verhindern soll. Sie ist ABSICHTLICH streng: eine neue, richtige
    Verwendung faellt hier auf und muss ihren Weg dazuschreiben, statt
    dass eine falsche durchrutscht.

    Ein Sonderfall steht namentlich drin: `name: name.trim() ||
    NOT_CONNECTED` in getConnectionInfo() setzt das Protokollwort in die
    DATENSTRUKTUR, nicht auf den Schirm - dort ist es richtig, weil der
    Vergleich danach darauf laeuft. Die Anzeige holt es sich von dort
    ueber aufschrift().
    """
    verstoesse = []
    for name, konstanten in PROTOKOLL_KONSTANTEN.items():
        pfad = TEMPLATES / name
        text = _ohne_kommentare(pfad.read_text(encoding="utf-8"))
        for nummer, zeile in enumerate(text.splitlines(), start=1):
            for konstante in konstanten:
                if not re.search(rf"(?<![\w]){konstante}(?![\w])", zeile):
                    continue
                if re.search(rf"const\s+{konstante}\s*=", zeile):
                    continue
                if re.search(rf"[=!]==\s*{konstante}(?![\w])", zeile):
                    continue
                if AUFSCHRIFT in zeile:
                    continue
                # Die Datenstruktur - siehe den Docstring.
                if re.search(rf"name:\s*[^,]*\|\|\s*{konstante}(?![\w])",
                             zeile):
                    continue
                if re.search(rf"name:\s*{konstante}(?![\w])", zeile):
                    continue
                verstoesse.append(f"{name}:{nummer} {zeile.strip()[:70]}")
    assert verstoesse == [], (
        "ein Protokollwort steht an einer Stelle, die weder Vergleich "
        "noch Deklaration noch aufschrift() ist - auf einer englischen "
        "Installation stuende dort Deutsch:\n  " + "\n  ".join(verstoesse))


def test_die_wache_fuer_die_protokollwoerter_faengt_ueberhaupt_etwas():
    """Der Selbsttest: findet sie die Konstanten ueberhaupt?

    Eine Wache, die ihre Konstanten nicht mehr findet - umbenannt,
    verschoben, geloescht -, meldet dasselbe "sauber" wie eine Datei
    ohne Fehler. Gezaehlt wird deshalb, dass jede genannte Konstante
    wirklich in ihrer Datei steht.
    """
    for name, konstanten in PROTOKOLL_KONSTANTEN.items():
        text = (TEMPLATES / name).read_text(encoding="utf-8")
        for konstante in konstanten:
            assert re.search(rf"const\s+{konstante}\s*=", text), (
                f"{name} erklaert {konstante} nicht mehr - die Wache "
                "darueber prueft damit nichts")
        assert AUFSCHRIFT in text, (
            f"{name} hat keine aufschrift() mehr - dann kommt das "
            "Protokollwort entweder gar nicht oder ungefiltert auf den "
            "Schirm")
