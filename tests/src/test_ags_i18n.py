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

import re
from pathlib import Path

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
SICHTBARE_EIGENSCHAFTEN = (
    "label", "headerTitle", "title", "subtitle", "tooltip", "tooltip_text",
    "tooltipText", "placeholder_text", "placeholderText", "text",
    "body", "summary", "heading", "message", "description", "name",
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


def _ohne_kommentare(text: str) -> str:
    """Kommentare durch Leerzeichen ersetzen.

    Die LAENGE bleibt erhalten, damit jeder Versatz und damit jede
    Zeilennummer noch stimmt. Zeichenketten bleiben unberuehrt - ein
    `//` in einer URL ist kein Kommentaranfang.
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
DEUTSCH_RE = re.compile(
    r"[ÄÖÜäöüß]"
    r"|(?<![\w-])(?:der|die|das|und|oder|mit|fuer|nicht|kein|keine|eine|"
    r"einen|zum|zur|vom|von|auf|ist|wird|werden|sind|dem|den|des|wie|noch|"
    r"schon|bitte|alle|alles|ohne|beim|dieser|diese|hat|haben|Herunterfahren|"
    r"Neustart|Bereitschaft|Sperren|Abmelden|Verbinden|Trennen|Speichern|"
    r"Abbrechen|Suchen|Laden|Fenster|Farben|Einstellungen|Beenden|Anzeigen)"
    r"(?![\w-])", re.IGNORECASE)

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
PROTOKOLL_DES_SKRIPTS = ("Kabelverbindung", "Nicht verbunden", "Kein Drucker")


def test_keine_deutsche_zeichenkette_bleibt_in_der_oberflaeche():
    """Das zweite Netz - siehe den Block darueber."""
    deutsch = []
    for pfad in _vorlagen():
        if pfad.name.endswith("-scripts.template"):
            continue
        text = _ohne_kommentare(pfad.read_text(encoding="utf-8"))
        diagnosen = [(t.end() - 1, _klammer_ende(text, t.end() - 1))
                     for t in DIAGNOSE_RE.finditer(text)]
        for anfang, ende in _literal_bereiche(text):
            wert = text[anfang + 1:ende - 1]
            if not wert.strip() or wert in PROTOKOLL_DES_SKRIPTS:
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
