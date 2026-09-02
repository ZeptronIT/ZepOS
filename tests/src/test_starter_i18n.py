# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Anwendungsstarter spricht die Sprache der Maschine - gehalten am Diff.

WORAUF DIESE DATEI ANTWORTET
    hyprlaunch ist C++ und lief bis zum 02.09.2026 an gettext VORBEI.
    Seine sichtbaren Zeichenketten standen fest auf Deutsch im
    Quelltext, waehrend derselbe Schreibtisch daneben einen
    vollstaendigen Katalog fuehrt - po/desktop/de.po, Domaene
    zepos-desktop. Der Starter war damit die eine Flaeche, die der
    Sprachwahl nicht folgte, und die vier Menuepunkte seines
    Rechtsklicks standen ein ZWEITES Mal neben denen des Fusses und des
    Home.

    Seit dem 02.09.2026 rufen sie _(). Diese Datei haelt das so.

WARUM SIE DEN PATCH LIEST UND KEINE .cpp
    Weil die .cpp nicht in diesem Repository liegt und nicht darf:
    plugins/LICENSE fuehrt aus, dass der uebernommene Baum von azzuriel
    gar keine Lizenz traegt und eine geaenderte KOPIE davon hier nichts
    zu suchen hat. Was hier liegt, ist ZepOS' EIGENES Diff - und genau
    die Zeilen, die es HINZUFUEGT, sind die Zeilen mit den
    Zeichenketten.

    Das ist ausdruecklich der billigere Weg und nicht der schlechtere:
    tests/adopted_plugin_source.py kann den ganzen Baum
    wiederherstellen, holt ihn dafuer aber uebers Netz und ueberspringt
    sich selbst, wenn keins da ist. Eine Zusicherung, die ohne Netz
    verschwindet, ist genau an dem Tag weg, an dem jemand ohne Netz
    etwas einbaut. Die Zeilen des Diffs liegen immer da.

WAS SIE NICHT PRUEFT
    Ob das Programm baut, und ob der Katalog zur Laufzeit greift. Beides
    ist am 02.09.2026 von Hand GEMESSEN worden - gepinnter Commit
    geholt, Patch angewendet, UI-Haelfte mit `g++ -std=c++23 -Wall
    -Wextra -Wpedantic` ohne Warnung gebaut, danach `dgettext` gegen das
    aus po/desktop/de.po gebaute .mo befragt:

        LANG=de_DE.UTF-8  "Add to dock" -> "Zum Dock hinzufügen"
        LANG=en_US.UTF-8  "Add to dock" -> "Add to dock"
        LANG=C            "Add to dock" -> "Add to dock"

    Ein Test kann das hier nicht wiederholen: er braeuchte das Netz, den
    Compiler, GTK4, gtk4-layer-shell und json-glib. Der Kopf des Patches
    haelt die Messung fest, damit sie nicht bloss in einer Sitzung
    stattgefunden hat.
"""
from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
PATCH = WURZEL / "packaging" / "zepos-hyprlaunch" / "zepos-hyprlaunch.patch"
KATALOG = WURZEL / "po" / "desktop" / "de.po"
AUSLESE = WURZEL / "po" / "desktop" / "extract.sh"
CMAKE_BLOCK = "CMakeLists.txt"

# Die Zeichen, an denen eine deutsche Zeichenkette zu erkennen ist.
# Dieselbe Pruefung und derselbe Grund wie in
# tests/src/test_ags_i18n.py::test_die_msgids_sind_englisch.
UMLAUTE = re.compile(r"[ÄÖÜäöüß]")

# Die Woerter, die eine SCHNITTSTELLE sind und keine Sprache. Wer sie
# uebersetzt, bricht sie: `hyprctl` vergleicht sie als Text.
PROTOKOLLWOERTER = ("unknown command: ", "config reloaded")


def _bloecke() -> dict[str, list[str]]:
    """Die ZUGEFUEGTEN Zeilen des Patches, nach Datei.

    Nur die mit '+': die Zeilen mit ' ' sind Zusammenhang aus dem
    fremden Baum und die mit '-' sind weg. Was ZepOS zu verantworten
    hat, sind die zugefuegten.
    """
    out: dict[str, list[str]] = {}
    aktuell: list[str] | None = None
    for zeile in PATCH.read_text(encoding="utf-8").splitlines():
        if zeile.startswith("diff -ruN "):
            aktuell = out.setdefault(zeile.split(" b/")[-1], [])
        elif zeile.startswith(("--- ", "+++ ", "@@ ")):
            continue
        elif aktuell is not None and zeile.startswith("+"):
            aktuell.append(zeile[1:])
    return out


def _ohne_kommentare(zeilen: list[str]) -> str:
    """C++-Kommentare entfernen, Zeichenketten aber NICHT anfassen.

    Von Hand und nicht mit einem regulaeren Ausdruck: "~/.config/
    hyprlaunch/config" enthaelt zwei Schraegstriche, und ein Ausdruck,
    der `//` sucht, schneidet mitten in dieser Zeichenkette. Der Leser
    hier weiss, wann er in einer Zeichenkette steht.

    Warum ueberhaupt: die Kommentare des Patches NENNEN die deutschen
    Beschriftungen, um zu erklaeren, woher sie kommen (»"Zum Dock
    hinzufügen" steht im Menue des Fusses«). Ohne diesen Schritt
    meldete die Pruefung weiter unten genau diese Erklaerungen als
    fest verdrahtetes Deutsch.
    """
    ergebnis = []
    for zeile in zeilen:
        i, n = 0, len(zeile)
        raus = []
        while i < n:
            zeichen = zeile[i]
            if zeichen == '"':
                raus.append(zeichen)
                i += 1
                while i < n:
                    raus.append(zeile[i])
                    if zeile[i] == "\\":
                        i += 1
                        if i < n:
                            raus.append(zeile[i])
                    elif zeile[i] == '"':
                        i += 1
                        break
                    i += 1
                continue
            if zeichen == "'":
                raus.append(zeichen)
                i += 1
                while i < n:
                    raus.append(zeile[i])
                    if zeile[i] == "\\":
                        i += 1
                        if i < n:
                            raus.append(zeile[i])
                    elif zeile[i] == "'":
                        i += 1
                        break
                    i += 1
                continue
            if zeile.startswith("//", i):
                break
            raus.append(zeichen)
            i += 1
        ergebnis.append("".join(raus))
    return "\n".join(ergebnis)


def _cpp_bloecke() -> dict[str, str]:
    """Die zugefuegten C++-Zeilen, kommentarfrei, nach Datei.

    Dieselbe Auswahl nach Endung, die po/desktop/extract.sh trifft, und
    aus demselben gemessenen Grund: CMakeLists.txt-Kommentare beginnen
    mit '#', ein C++-Leser haelt das nicht fuer einen Kommentar, und
    ein Anfuehrungszeichen darin verschiebt ihm den ganzen Rest.
    """
    return {pfad: _ohne_kommentare(zeilen)
            for pfad, zeilen in _bloecke().items()
            if pfad.endswith((".cpp", ".hpp"))}


def _nachher() -> dict[str, list[str]]:
    """Die Zeilen, die NACH dem Patch dastehen - Zusammenhang UND Zusatz.

    Fuer die Fragen nach der REIHENFOLGE. `spracheAnwenden();` ist eine
    zugefuegte Zeile, `gtk_init();` eine Zusammenhangszeile: die eine
    steht in _bloecke(), die andere nicht, und ein Vergleich der beiden
    braucht sie zusammen. Was hier fehlt, sind die Zeilen ausserhalb
    aller Hunks - fuer die Reihenfolge zweier Zeilen INNERHALB der
    Hunks aendert das nichts.
    """
    out: dict[str, list[str]] = {}
    aktuell: list[str] | None = None
    for zeile in PATCH.read_text(encoding="utf-8").splitlines():
        if zeile.startswith("diff -ruN "):
            aktuell = out.setdefault(zeile.split(" b/")[-1], [])
        elif zeile.startswith(("--- ", "+++ ", "@@ ")):
            continue
        elif aktuell is not None and zeile[:1] in ("+", " "):
            aktuell.append(zeile[1:])
    return out


def _msgids(text: str) -> list[str]:
    return re.findall(r'_\(\s*"((?:[^"\\]|\\.)*)"', text)


def _alle_msgids() -> list[tuple[str, str]]:
    return [(pfad, msgid)
            for pfad, text in sorted(_cpp_bloecke().items())
            for msgid in _msgids(text)]


# --------------------------------------------------------------------
# Der eigene blinde Fleck, offengehalten
# --------------------------------------------------------------------

def test_die_auslese_liest_den_patch_wirklich():
    """Eine Auslese, die nichts oeffnet, antwortet auf jede Frage
    dasselbe "sauber" wie ein Projekt ohne Fehler.

    Genau dieser Fall hat in diesem Baum schon einmal elf gruene
    Zusicherungen erzeugt, die keine einzige Datei gelesen hatten (der
    Kopf von tests/installer/test_i18n.py fuehrt ihn aus). Weder die
    Zahl der Bloecke noch die der msgids laesst sich hier durch eine
    leere Lesung erfuellen.
    """
    assert PATCH.is_file(), f"{PATCH} fehlt"
    bloecke = _bloecke()
    assert CMAKE_BLOCK in bloecke, (
        "der Patch aendert CMakeLists.txt nicht mehr - dort stehen die "
        "Domaene und das Katalogverzeichnis")
    cpp = _cpp_bloecke()
    assert len(cpp) >= 4, f"nur {len(cpp)} C++-Bloecke gelesen"
    assert len(_alle_msgids()) >= 13, (
        f"nur {len(_alle_msgids())} uebersetzte Zeichenketten gefunden - "
        "am 02.09.2026 waren es dreizehn")


# --------------------------------------------------------------------
# Jede uebersetzte Zeichenkette steht im Katalog
# --------------------------------------------------------------------

def test_jeder_msgid_des_starters_steht_im_katalog():
    """Ein msgid ohne Katalogeintrag heisst: ein deutscher Nutzer sieht
    an dieser Stelle still Englisch - und zwar auf einer Flaeche, die
    vorher durchgehend deutsch war. Das waere ein Rueckschritt gegenüber
    dem Zustand vor der Uebersetzung."""
    katalog = KATALOG.read_text(encoding="utf-8")
    fehlend = [f"{pfad}: {msgid}" for pfad, msgid in _alle_msgids()
               if f'msgid "{msgid}"' not in katalog]
    assert fehlend == [], "msgids ohne Katalogeintrag: " + "; ".join(fehlend)


def test_die_msgids_des_starters_sind_englisch():
    """Die Ausgangssprache ist Englisch, hier wie in den Vorlagen.

    Ein deutscher msgid faellt sonst erst auf, wenn eine dritte Sprache
    dazukommt und der Uebersetzer Deutsch lesen koennen muss.
    """
    deutsch = [f"{pfad}: {msgid}" for pfad, msgid in _alle_msgids()
               if UMLAUTE.search(msgid)]
    assert deutsch == [], (
        "diese msgids sind deutsch statt englisch: " + "; ".join(deutsch))


def test_keine_deutsche_zeichenkette_bleibt_im_starter():
    """DIE ZUSICHERUNG, DIE DEN ZUSTAND VON GESTERN NICHT WIEDERKOMMEN
    LAESST.

    Vor dem 02.09.2026 standen "ZepOS Anwendungsstarter", "Anwendungen
    suchen ... (= rechnet)", "Enter kopiert das Ergebnis" und die vier
    Menuepunkte fest verdrahtet im Quelltext. Sie zu uebersetzen war
    die eine Haelfte der Arbeit; die andere ist, dass die naechste
    Beschriftung nicht wieder daneben entsteht.

    Geprueft wird am UMLAUT und nicht an einer Wortliste: eine deutsche
    Beschriftung ohne Umlaut gaebe es zwar auch, aber jede der sieben,
    die hier standen, hatte einen oder wuerde einen bekommen - und eine
    Wortliste waere eine Liste, die veraltet. Die Kommentare sind vorher
    entfernt (siehe _ohne_kommentare); sie NENNEN die deutschen
    Beschriftungen absichtlich, um ihre Herkunft zu erklaeren.
    """
    schuldig = []
    for pfad, text in sorted(_cpp_bloecke().items()):
        for zeile in text.splitlines():
            for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', zeile):
                if UMLAUTE.search(literal):
                    schuldig.append(f"{pfad}: {literal}")
    assert schuldig == [], (
        "diese Zeichenketten stehen deutsch im Quelltext statt im "
        "Katalog: " + "; ".join(schuldig))


# --------------------------------------------------------------------
# Eine Beschriftung, drei Menues
# --------------------------------------------------------------------

def test_die_vier_menuepunkte_teilen_ihre_msgids_mit_fuss_und_home():
    """DER ZWEITE FUND DIESER AUFGABE, und er ist der bleibende.

    Der Fuss (ags-dock.template), das Home (ags-home.template) und der
    Starter tragen dieselben vier Punkte - "Zum Dock hinzufügen" und
    die drei anderen. Der Starter schrieb sie fest und ein zweites Mal
    daneben; damit gab es zwei Orte fuer eine Beschriftung, von denen
    einer irgendwann abweicht. In DREI Menues, die dasselbe tun, ist
    das genau der Unterschied, den ein Nutzer bemerkt.

    Seit dem 02.09.2026 sind es dieselben vier msgids, und diese Zeilen
    halten das - fuer beide Richtungen: nimmt jemand dem Starter einen
    weg oder benennt er ihn um, faellt es hier auf, und schreibt jemand
    im Fuss einen neuen Wortlaut, kann er nur den Katalogeintrag
    aendern, den der Starter mitliest.
    """
    vorlagen = "\n".join(
        (WURZEL / "src" / "templates" / name).read_text(encoding="utf-8")
        for name in ("ags-dock.template", "ags-home.template"))
    im_starter = {msgid for _pfad, msgid in _alle_msgids()}

    for punkt in ("Add to dock", "Remove from dock",
                  "Add to Home", "Remove from Home"):
        assert punkt in im_starter, (
            f"der Starter holt {punkt!r} nicht mehr aus dem Katalog - "
            "damit kann sein Menue etwas anderes sagen als das des "
            "Fusses")
        assert f'"{punkt}"' in vorlagen, (
            f"{punkt!r} steht nicht mehr in den Vorlagen des Fusses "
            "oder des Home - dann teilt der Starter seine Beschriftung "
            "mit niemandem mehr, und diese Zusicherung misst nichts")


# --------------------------------------------------------------------
# Was absichtlich NICHT durch den Katalog geht
# --------------------------------------------------------------------

def test_die_protokollwoerter_bleiben_unuebersetzt():
    """"unknown command: " und "config reloaded" gehen ueber die
    IPC-Schnittstelle an `hyprctl`, das sie als TEXT vergleicht. Wer sie
    uebersetzt, bricht die Schnittstelle - dieselbe Regel, aus der die
    Kennung "hyprlaunch" in PLUGIN_INIT ein Bezeichner bleibt."""
    for pfad, text in _cpp_bloecke().items():
        for wort in PROTOKOLLWOERTER:
            for msgid in _msgids(text):
                assert wort not in msgid, (
                    f"{pfad}: {wort!r} laeuft durch den Katalog - "
                    "damit antwortet die IPC-Schnittstelle je nach "
                    "Sprache anders")


def test_die_compositor_haelfte_bekommt_keinen_katalog():
    """Das Objekt, das in HYPRLANDS Prozess geladen wird, bleibt ohne.

    Dieselbe Trennung, die CMakeLists.txt fuer json-glib schon
    begruendet, und sie ist der Grund, aus dem die Beschreibung in
    PLUGIN_INIT unuebersetzt bleibt: eine Katalogbindung im Compositor,
    fuer eine Zeile, die `hyprctl plugin list` ausgibt, ist der
    schlechtere Tausch.

    Geprueft an den Dateien, die CMakeLists.txt in PLUGIN_SOURCES
    nennt, und nicht an einer Liste hier: eine zweite Liste waere die
    erste Stelle, an der eine neue Datei nur in einer von beiden
    landet.
    """
    cmake = "\n".join(_bloecke()[CMAKE_BLOCK])
    # PLUGIN_SOURCES steht im Zusammenhang des Patches und nicht in
    # seinen zugefuegten Zeilen - zugefuegt ist nur die Kommentarzeile
    # darueber. Gelesen wird deshalb der ganze Block.
    ganz = PATCH.read_text(encoding="utf-8")
    block = re.search(r"set\(PLUGIN_SOURCES\n((?:[+ ]?\s*src/\S+\n)+)", ganz)
    assert block, "PLUGIN_SOURCES steht nicht mehr im Patch"
    plugin_dateien = re.findall(r"(src/\S+\.cpp)", block.group(1))
    assert plugin_dateien, "PLUGIN_SOURCES nennt keine Datei"

    cpp = _cpp_bloecke()
    for pfad in plugin_dateien:
        if pfad not in cpp:
            continue
        assert _msgids(cpp[pfad]) == [], (
            f"{pfad} steht in PLUGIN_SOURCES und ruft _() - damit "
            "braeuchte das Objekt im Compositor eine Katalogbindung")
        assert "i18n.hpp" not in cpp[pfad], (
            f"{pfad} steht in PLUGIN_SOURCES und bindet i18n.hpp ein")

    # Und die UI-Haelfte bekommt beides wirklich, sonst faende der
    # Starter seinen Katalog nicht und stuende stumm auf Englisch da -
    # ohne eine Zeile Fehlermeldung.
    assert 'GETTEXT_PACKAGE="zepos-desktop"' in cmake, (
        "CMakeLists.txt setzt die Domaene nicht mehr")
    assert "ZEPOS_LOCALEDIR=" in cmake, (
        "CMakeLists.txt setzt das Katalogverzeichnis nicht mehr")
    assert "target_compile_definitions(hyprlaunch-ui" in cmake, (
        "die zwei Angaben haengen nicht mehr am Ziel hyprlaunch-ui")


# --------------------------------------------------------------------
# Die Sprache wird auch wirklich gesetzt
# --------------------------------------------------------------------

def test_die_sprache_wird_vor_gtk_init_gesetzt():
    """Sonst kaeme das Fenster englisch zurueck, und zwar still.

    GEMESSEN und ausgefuehrt im Kopf von
    src/templates/ags-i18n.template: eine schon GEZEICHNETE
    Beschriftung folgt einem spaeteren Katalogwechsel nicht. Die
    Beschriftungen dieses Programms entstehen in
    renderer.initialize(); setlocale muss davor stehen.
    """
    # Zusammenhang UND Zusatz: gtk_init() ist eine Zeile des fremden
    # Baums und steht deshalb nicht in den zugefuegten - siehe
    # _nachher().
    zeilen = _nachher().get("src/main_ui.cpp", [])
    setzen = [i for i, z in enumerate(zeilen) if "spracheAnwenden();" in z]
    starten = [i for i, z in enumerate(zeilen) if z.strip() == "gtk_init();"]
    assert setzen, "main_ui.cpp setzt die Sprache nicht mehr"
    assert starten, (
        "gtk_init() steht nicht mehr im Zusammenhang dieses Patches - "
        "damit kann diese Zusicherung die Reihenfolge nicht mehr messen")
    assert setzen[0] < starten[0], (
        "spracheAnwenden() steht hinter gtk_init() - die Beschriftungen "
        "entstehen dann in der C-Sprachumgebung und bleiben englisch")


def test_der_katalog_wird_ueber_die_domaene_gefragt():
    """dgettext und nicht gettext: gettext nimmt die Domaene, die
    textdomain() gesetzt hat, also einen Prozesszustand. Dieselbe Wahl
    trifft src/templates/ags-i18n.template fuer dieselbe Domaene."""
    i18n = _cpp_bloecke().get("include/hyprlaunch/i18n.hpp", "")
    assert "dgettext(GETTEXT_PACKAGE, text)" in i18n, (
        "der Katalog wird nicht mehr ueber die Domaene gefragt")
    assert "bind_textdomain_codeset(GETTEXT_PACKAGE, \"UTF-8\")" in i18n, (
        "der Zeichensatz ist nicht mehr festgelegt - GTK4 nimmt "
        "ausschliesslich UTF-8, und gettext wandelte sonst in den "
        "Zeichensatz der Sprachumgebung um")


# --------------------------------------------------------------------
# Die Auslese kann nicht still veralten
# --------------------------------------------------------------------

def test_die_auslese_liest_die_zeilen_dieses_patches():
    """Ohne diesen Durchgang in extract.sh verschwinden die dreizehn
    msgids beim naechsten `./extract.sh` aus der .pot - und mit dem
    naechsten `msgmerge` aus dem Katalog. Die Zeichenketten stuenden
    dann auf dem Schirm und in keiner Liste.

    Geprueft wird, DASS die Auslese diesen Patch beim Namen nennt und
    ihn als C++ liest. Was dabei herauskommt, pruefen die Zusicherungen
    weiter oben am Katalog.
    """
    text = AUSLESE.read_text(encoding="utf-8")
    assert "packaging/zepos-hyprlaunch/zepos-hyprlaunch.patch" in text, (
        "po/desktop/extract.sh liest den Patch des Starters nicht mehr")
    assert "--language=C++" in text, (
        "extract.sh liest die zugefuegten Zeilen nicht mehr als C++")
