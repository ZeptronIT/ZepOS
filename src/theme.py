# SPDX-License-Identifier: GPL-3.0-or-later
"""Welche Themen es gibt, und was ein Thema ueberhaupt AUSMACHT.

GEMELDET am 12.08.2026: "wenn wir spaeter ein weiteres theme entwickeln
soll das sofort umschaltbar sein" - und einen Satz davor: "login
bildschirm soll genauso dem theme angepasst sein". Das ist EINE
Forderung: es muss ein Thema als Ding geben, sonst kann weder etwas
umgeschaltet werden noch etwas anderes "genauso" aussehen.

WAS ES VORHER GAB
    Kein Thema. ZepOS WAR sein Aussehen: src/brand.py trug die Farben
    als Konstanten, src/style_definition.py setzte daraus die
    {{STYLE_*}}-Werte zusammen. Ein zweites Thema haette nirgends
    stehen koennen - es gab keine Liste, in die man es haette
    eintragen koennen, und keinen Namen, unter dem man es haette
    waehlen koennen. Die siebzig FARBEN waren einzeln einstellbar; das
    ist etwas anderes, und der Unterschied ist der Grund fuer diese
    Datei: siebzig Farben von Hand zu setzen ist kein Themenwechsel,
    sondern siebzig Aenderungen, die man auch wieder einzeln
    zuruecknehmen muesste.


=====================================================================
DIE REGEL - WAS IN EIN THEMA GEHOERT UND WAS NICHT
=====================================================================

Es ist dieselbe Regel, mit der dieser Baum am 12.08.2026 schon
neunundzwanzig Farben und hundertsechs Platzhalter geloescht hat, nur
in die andere Richtung angewandt:

    Ein Wert gehoert zum Thema, wenn er BESTIMMT, WIE ZepOS AUSSIEHT,
    und wenn eine Aenderung an ihm ein Byte in einer erzeugten Datei
    bewegt.

Beide Haelften zaehlen. Die zweite ist die, die gemessen wird -
tests/src/test_theme.py setzt jedes einzelne Feld unten auf einen
Sentinel, erzeugt damit neu und verlangt, dass der Sentinel in einer
erzeugten Datei ankommt. Ein Themenfeld ohne Wirkung waere die
Reglertabelle, die kein Byte bewegt, nur diesmal mit einem
Themenwaehler davor.


WAS DAMIT AUFGENOMMEN IST

  Die dreiundzwanzig Farben.  Jede Farbe, die src/style_definition.py
      in einen Platzhalter schreibt - unmittelbar oder ueber eine der
      siebzig Rollen in brand.COLOR_FIELDS. Das ist die Substanz.

  Die drei Deckkraefte.  GLASS_PANEL_ALPHA, GLASS_CHIP_ALPHA und
      LOCK_SCRIM_ALPHA. Der Kopf von src/brand.py begruendet
      ausfuehrlich, dass diese drei Zahlen FARBEN entscheiden - was
      ein Pixel der Leiste wirklich IST, wenn die Tapete
      hineingemischt ist - und dass die Grenze, die sie bindet, ein
      Kontrastverhaeltnis ist. Ein Thema ohne Glas und eines mit Glas
      sind zwei verschiedene Oberflaechen, auch bei gleicher Palette.

  Die zwei Schriftfamilien.  FONT_CODE und FONT_TEXT. Eine Schriftart
      ist keine Groesse - wie GROSS gelesen wird, entscheidet
      sizes.scale; WOMIT gelesen wird, ist eine Entscheidung des
      Aussehens und sonst nichts.

  Das Bild hinter der Anmeldung.  BACKDROP_FILE. Ein Thema, das
      dieselbe Tapete traegt wie das andere, ist eine Umfaerbung.
      Ausserdem haengt an diesem Bild eine MESSUNG: der Schleier des
      Sperrbildschirms wird gegen die Extremwerte genau dieser Datei
      gerechnet, also kann ein Thema mit hellem Text und ein Thema mit
      dunklem Text gar nicht dasselbe Bild benutzen.


WAS DRAUSSEN BLEIBT, UND WARUM - JEDES EINZELN

  Die Groessen (src/sizes.py).  Der ganze Inhalt von sizes.TABLE, der
      Massstab, die Schrift-, Symbol-, Abstands- und Bewegungsleiter.
      Wie GROSS etwas ist, haengt am Schirm, am Sitzabstand und an den
      Augen, die davorsitzen - nicht daran, welches Thema gewaehlt ist.
      Dafuer gibt es seit dem 11.08.2026 einen eigenen Regler, und
      zwei Regler fuer eine Zahl sind in diesem Baum bereits einmal
      teuer geworden (user_settings.RETIRED_SCALING_DIMENSION).

  FONT_RATIO, 1.2.  Der naheliegendste Grenzfall, und er faellt aus
      demselben Grund heraus: das Verhaeltnis einer Schriftskala sagt,
      wie weit eine Ueberschrift von einer Zeile ENTFERNT ist, und das
      ist eine Frage des Lesens und nicht der Marke. Es ist ausserdem
      GEMESSEN und nicht gewaehlt - src/sizes.py fuehrt die 128
      Textregeln an, aus denen es kommt -, und ein Thema, das eine
      Messung ueberschreibt, ist keine Gestaltung, sondern ein zweiter
      Anker.

  Die Rundungsleiter, RADIUS_ANCHOR und RADIUS_RATIO.  Der Kopf von
      src/sizes.py sagt "die Rundung traegt die FORM der Marke", und
      genau deshalb steht hier, warum sie trotzdem draussen bleibt:
      eine Ecke ist eine LAENGE. Sie steht in sizes.TABLE, folgt dem
      einen Massstab und ist ueber `sizes.values` einzeln
      ueberschreibbar, wie jede andere Laenge auch. Zoege man sie
      hierher, gaebe `zepos-settings get sizes` und
      `user_settings.py list-sizes` weiterhin die Sprossen der
      Standardleiter aus, waehrend der Generator andere schriebe -
      zwei Antworten auf eine Frage, und die eine davon in dem
      Werkzeug, das man fragt, WEIL man es nicht weiss.
      WAS ES KOSTEN WUERDE, ES DOCH ZU TUN, ist gemessen und nicht
      geschaetzt: sizes.TABLE wird beim Import gebaut und von
      user_settings.py gelesen, das die Einstellungsdatei nicht lesen
      darf. Die Tabelle muesste also eine Funktion der Palette werden,
      und `value_of(name, section)` ein drittes Argument bekommen -
      an 40 Fundstellen, darunter settings/zepos_settings_gui/model.py
      und die fuenf Drehknoepfe dort.

  Die Bewegung (MOTION_*).  Der Schalter dafuer ist eine
      Barrierefreiheits-Einstellung: bewegte Flaechen loesen bei einer
      vestibulaeren Stoerung Schwindel aus. Ein Thema, das Bewegung
      wieder einschaltet, weil es "lebendiger" gemeint ist,
      ueberstimmt eine koerperliche Notwendigkeit mit Geschmack.

  Die Code-Palette (CODE_*).  src/brand.py sagt es selbst: das ist "a
      named theme and not the chrome". Sie wird als
      "Terminal Green.sublime-color-scheme" ausgeliefert und vom
      Editor UNTER DIESEM NAMEN aus seinen eigenen Einstellungen
      gewaehlt. Sie mit dem Schreibtisch umzufaerben hiesse, ein Thema
      namens Terminal Green auszuliefern, das nicht gruen ist.

  FONT_ICONS.  Keine Gestaltung, sondern eine Abhaengigkeit: jedes
      Zeichen in src/icon_definition.py ist ein Nerd-Font-Codepunkt.
      Ein Thema, das diese Familie austauscht, zeichnet die ganze
      Symbolik der Leiste als Tofu.

  SHADE_2 und TRACK_EDGE.  GEMESSEN am 12.08.2026, mit `grep` ueber
      src/ und settings/: keine der beiden Farben erreicht einen
      {{STYLE_*}}-Platzhalter. Ihre einzigen Leser sind
      installer/gui/branding.py und das GRUB-Thema auf dem Medium -
      zwei Oberflaechen, die vor der Installation laufen und nicht aus
      dieser Mitte erzeugt werden. Sie hier aufzunehmen waere ein
      Regler, der nichts bewegt, und das ist genau die Sorte Eintrag,
      die dieser Baum schon neunundzwanzigmal geloescht hat.


=====================================================================
WEM DAS THEMA GEHOERT - DER MASCHINE, NICHT DEM KONTO
=====================================================================

Das ist die unbequeme Folgerung aus dem ersten Satz des Nutzers, und
sie ist gemessen und nicht gewaehlt:

    src/bin/zepos-greeter laeuft als Benutzer "greeter", bevor
    irgendjemand angemeldet ist. Er kann /home/<wer?>/.config/zepos/
    user-settings.json nicht lesen - es gibt zu diesem Zeitpunkt kein
    "wer", und auf einer Maschine mit zwei Konten gaebe es zwei
    Antworten auf eine Frage, die ein Anmeldebildschirm nur einmal
    beantworten kann.

Damit die Anmeldemaske "genauso" aussehen KANN, muss das Thema also
dort stehen, wo die Maschine ihre Entscheidungen hinschreibt:
/etc/zepos, paths.machine_root(), dieselbe Wurzel wie update.json.

    Die siebzig FARBEN bleiben dem Konto. Wer sein Gelb anders will,
    stellt sein Gelb anders ein, und das ueberlebt jeden
    Themenwechsel - get_user_color() fragt die Einstellungsdatei
    zuerst und die Palette danach. Das Thema ist die Palette, unter
    der die eigenen Aenderungen liegen.

EINE ZEILE UND KEIN JSON, und das ist ebenfalls gemessen: der einzige
Leser, der diese Datei ohne Python auskommen muss, ist
src/bin/zepos-greeter - ein Shell-Skript, das laufen muss, wenn von
ZepOS sonst noch nichts erzeugt wurde. `jq` ist keine Abhaengigkeit
dieses Systems, und ein Anmeldebildschirm, der an einem JSON-Parser
haengt, ist einer, der ausfallen kann. Eine Datei mit einem Namen
darin kann `read` lesen.

WAS BEI EINEM UNBEKANNTEN NAMEN PASSIERT, haengt daran, WER fragt, und
die beiden Antworten sind absichtlich verschieden:

    Der Generator     bricht ab (UnknownTheme). Er schreibt gerade den
                      ganzen Schreibtisch; ihn stillschweigend im
                      Standardthema zu schreiben hiesse, eine
                      Einstellung zu uebergehen und dabei "fertig" zu
                      melden - genau das, was _load_user_settings()
                      fuer eine kaputte Einstellungsdatei schon
                      verboten hat.
    Der Greeter       nimmt das Standardthema. Er ist die Maske vor
                      der Sitzung, und ein Tippfehler in einer
                      Themendatei darf keine Maschine sein, in die
                      niemand mehr hineinkommt. Das steht in
                      src/bin/zepos-greeter und nicht hier, weil es
                      dort auch ohne Python gelten muss.
"""
from __future__ import annotations

import struct
import zlib

import brand
from paths import machine_root

# Die Datei, in der die Maschine ihren Namen stehen hat.
FILENAME = "theme"

# Das Thema, das ausgeliefert wird - und die Palette, die src/brand.py
# als Konstanten traegt. Deshalb steht es unten als leere Ueberlagerung
# und nicht als abgeschriebene Wertetabelle: eine zweite Kopie der
# ausgelieferten Farben ist genau der Zustand, mit dessen Beseitigung
# brand.py anfaengt.
DEFAULT = "zeptronit"


class UnknownTheme(ValueError):
    """Ein Themenname, den es nicht gibt."""


# Die Felder, die ein Thema ersetzt. JEDES Thema muss JEDES nennen -
# tests/src/test_theme.py prueft das in beide Richtungen.
#
# WARUM VOLLSTAENDIG UND NICHT TEILWEISE
#     Weil eine halbe Palette schlimmer ist als gar keine. Ein Thema,
#     das nur PETROL austauscht, laesst TEXT auf dem alten Grund
#     stehen - und TEXT ist genau deshalb #DCEEF4, WEIL der Grund
#     Petrol ist (9.90:1). Jede Zahl im Kopf von src/brand.py ist
#     gegen eine andere Zahl derselben Palette gerechnet; eine
#     Teilmenge davon ist keine Palette, sondern ein Bruch.
FIELDS: tuple[str, ...] = (
    # -- Die Flaechen ------------------------------------------------
    "PETROL", "INK", "INK_HOVER", "SHADE_1", "SHADE_3",
    # -- Die Schrift -------------------------------------------------
    "TEXT", "TEXT_DIM", "TEXT_MUTED",
    # -- Der Akzent --------------------------------------------------
    "CYAN", "CYAN_TEXT", "CYAN_BRIGHT", "CYAN_DIM",
    # -- Was etwas bedeutet ------------------------------------------
    "YELLOW", "YELLOW_DIM", "GREEN", "GREEN_DIM", "RED", "RED_DEEP",
    "STATE_WARNING_BG", "STATE_CRITICAL_BG", "STATE_OFFLINE_BG",
    "FOOTPRINT_BG",
    # -- Wieviel durchscheint ----------------------------------------
    "GLASS_PANEL_ALPHA", "GLASS_CHIP_ALPHA", "LOCK_SCRIM_ALPHA",
    # -- Womit gelesen wird ------------------------------------------
    "FONT_CODE", "FONT_TEXT",
    # -- Das Bild vor der Sitzung ------------------------------------
    "BACKDROP_FILE",
)


# Das zweite Thema, und wozu es da ist.
#
# EIN THEMA, DAS ES NUR EINMAL GIBT, IST KEINE UMSCHALTUNG. Solange
# nur die ausgelieferte Palette existiert, laesst sich nicht
# unterscheiden zwischen "der Wechsel wirkt" und "es gibt nichts, wohin
# gewechselt werden koennte" - dieselbe Sorte Tautologie, die
# tests/src/test_greeter.py mit seiner Gegenprobe schon einmal
# aufgedeckt hat.
#
# WARUM AUSGERECHNET HELL
#     Weil es das Einzige ist, was BEWEIST, dass hier eine Palette
#     ausgetauscht wird und nicht ein dunkler Schreibtisch umgefaerbt.
#     Jede Zusicherung dieses Baums ueber Kontrast war bis heute gegen
#     einen dunklen Grund gerechnet: "der schlechteste Fall ist die
#     hellste denkbare Tapete" (test_glass.py), "die hellste Stelle des
#     Bildes" (tests/lock/test_style.py). Beide Saetze sind fuer
#     dunklen Text richtig und fuer hellen falsch herum. Ein zweites
#     dunkles Thema haette das nie gezeigt; dieses hat die zwei
#     Messungen gezwungen, BEIDE Extreme zu rechnen, und das ist eine
#     echte Verschaerfung und keine Anpassung.
#
# JEDE ZAHL IST GERECHNET UND NICHT GEWAEHLT. tests/src/test_brand.py
# faehrt jetzt jede seiner Kontrastpruefungen ueber jedes Thema; was
# hier steht, ist das Ergebnis dieser Rechnung. Die drei engsten:
#
#     leerer Arbeitsbereich (TEXT bei 0.6 Deckkraft)   4.96:1
#     kritisch (RED) auf dem Grund                     7.06:1
#     Ablehnung (RED) auf der dunkelsten Stelle des
#         Anmeldebildes, unter dem Schleier            4.92:1
#
# Die erste ist der Grund, aus dem PETROL hier fast weiss ist: eine
# Schrift, die auf 60 % ihrer Deckkraft gesetzt wird, verliert Kontrast
# GEGEN den Grund, und bei dunklem Text auf hellem Grund geht das
# schneller als umgekehrt. Bei #EEF4F7 lag sie bei 4.08:1 und fiel
# durch.
_TAGESLICHT = {
    "PETROL": "#F7FAFC",
    "INK": "#E9F0F4",
    "INK_HOVER": "#DBE6EC",
    "SHADE_1": "#C2D3DA",
    "SHADE_3": "#4C7180",

    "TEXT": "#071115",
    "TEXT_DIM": "#365058",
    "TEXT_MUTED": "#4A656E",

    # Unveraendert, und das ist die Probe aufs Exempel: #0096C0 misst
    # auf diesem hellen Grund 3.27:1 und ist damit AUCH HIER keine
    # Textfarbe. Die Regel, aus der CYAN_TEXT ueberhaupt entstanden
    # ist, gilt also nicht wegen des Petrols, sondern wegen dieser
    # Farbe - und das laesst sich erst an zwei Themen sehen.
    "CYAN": "#0096C0",
    # Dunkel statt hell, aus demselben Grund, aus dem er dort hell ist:
    # er muss auf dem Grund LESBAR sein, und der Grund ist jetzt hell.
    "CYAN_TEXT": "#00566E",
    "CYAN_BRIGHT": "#003F52",
    "CYAN_DIM": "#004B60",

    "YELLOW": "#6B4900",
    "YELLOW_DIM": "#4F3600",
    "GREEN": "#0A6B48",
    "GREEN_DIM": "#0D7C54",
    "RED": "#A32118",
    "RED_DEEP": "#7E1A13",

    # Die drei Zustandsgruende sind hier blass statt fast schwarz - es
    # ist dieselbe Regel wie im dunklen Thema, nur andersherum: jeder
    # ist sein eigener Statuston, so weit zum GRUND hin genommen, dass
    # die Farbe darauf 4.5:1 haelt, ohne dass die Zeile schreit.
    "STATE_WARNING_BG": "#FCEFC4",
    "STATE_CRITICAL_BG": "#FADEDB",
    "STATE_OFFLINE_BG": "#DEE9ED",
    "FOOTPRINT_BG": "#CFDFE5",

    "GLASS_PANEL_ALPHA": 0.55,
    "GLASS_CHIP_ALPHA": 0.70,
    "LOCK_SCRIM_ALPHA": 0.35,

    # Zwei andere Familien, damit an diesem Thema auch abzulesen ist,
    # dass die Schriftfelder wirklich ankommen. DejaVu und nicht etwas
    # Ausgefalleneres: es liegt in fontconfigs Grundausstattung, also
    # ist das, was ein Schirm zeigt, auch das, was hier steht.
    "FONT_CODE": "DejaVu Sans Mono",
    "FONT_TEXT": "DejaVu Sans",

    # Ein eigenes Bild, und es MUSS eins sein. Das ausgelieferte
    # zepos-backdrop.png hat kanalweise Maxima von (31, 74, 83) - es
    # ist ein dunkles Bild, und dunkler Text darauf ist auch unter dem
    # dicksten zulaessigen Schleier nicht lesbar. Gerechnet:
    # brand.RED auf der hellsten Stelle unter einem Schleier von 0.35
    # kommt auf 2.8:1.
    "BACKDROP_FILE": "zepos-backdrop-tageslicht.png",
}


# Die Themen, unter ihren Namen.
#
# Der Name ist der Dateiname-taugliche Schluessel (er landet in
# /etc/greetd/zepos-greeter-<name>.css), die Beschriftung ist das, was
# ein Mensch in der Einstellungs-Anwendung liest.
THEMES: dict[str, dict[str, object]] = {
    DEFAULT: {field: getattr(brand, field) for field in FIELDS},
    "tageslicht": _TAGESLICHT,
}

LABELS: dict[str, str] = {
    DEFAULT: "ZeptronIT",
    "tageslicht": "Tageslicht",
}

DESCRIPTIONS: dict[str, str] = {
    DEFAULT: "Das Petrol der Marke, helle Schrift, Glas ueber der Tapete.",
    "tageslicht": "Hell: fast weisser Grund, dunkle Schrift, eigenes "
                  "Anmeldebild.",
}


# =====================================================================
# DAS BILD, DAS EIN THEMA MITBRINGT
# =====================================================================
#
# WARUM ES ERZEUGT WIRD UND NICHT DANEBENLIEGT
#     zepos-backdrop.png ist eine gestaltete Datei: sie kommt aus dem
#     Design-Ordner der Firma, niemand kann sie ausrechnen, und sie
#     liegt deshalb als Datei im Baum. Das Bild von "Tageslicht" ist
#     dagegen ein Verlauf zwischen zwei Zahlen, und diese zwei Zahlen
#     sind GERECHNET - die untere ist die dunkelste Stelle, bei der der
#     Schleier oben noch gebraucht wird und trotzdem reicht:
#
#         ohne Schleier, brand.RED auf (176,196,204)   4.17:1  faellt
#         mit  Schleier 0.35 aus INK darueber          4.92:1  haelt
#
#     Laege das Bild nur als Datei da, waere dieser Zusammenhang eine
#     Behauptung in einem Kommentar. So ist er Quelltext:
#     tests/src/test_theme.py baut die Datei neu und vergleicht sie Byte
#     fuer Byte mit der eingecheckten, und tests/lock/test_style.py
#     rechnet die zwei Verhaeltnisse aus dem BILD nach.
#
# WARUM FILTERTYP 0 UND KEIN BESSERER
#     Weil der PNG-Leser in tests/src/test_brand.py mit der
#     Standardbibliothek auskommt und nur die Formen liest, in denen
#     die ausgelieferten Bilder wirklich vorliegen. Ein Bild, das seine
#     eigenen Tests nicht lesen kann, ist ein ungeprueftes Bild.
BACKDROP_SIZE = (1920, 1080)

# (oben, unten) je Thema, dessen Bild gerechnet wird. Themen ohne
# Eintrag bringen eine gestaltete Datei mit.
BACKDROP_GRADIENTS: dict[str, tuple[str, str]] = {
    "tageslicht": ("#F7FAFC", "#B0C4CC"),
}


def _rgb(colour: str) -> tuple[int, int, int]:
    digits = colour.lstrip("#")
    return tuple(int(digits[index:index + 2], 16) for index in (0, 2, 4))


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return (struct.pack(">I", len(payload)) + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))


def backdrop_png(name: str) -> bytes:
    """Das Bild dieses Themas, als vollstaendige PNG-Datei.

    Nur fuer die Themen in BACKDROP_GRADIENTS; fuer jedes andere ist
    das Bild eine gestaltete Datei, die niemand ausrechnen kann.
    """
    try:
        top, bottom = (_rgb(end) for end in BACKDROP_GRADIENTS[name])
    except KeyError:
        raise UnknownTheme(
            f"das Bild von {name!r} wird nicht gerechnet - es liegt als "
            f"Datei in src/branding/ oder es gibt das Thema nicht"
        ) from None

    width, height = BACKDROP_SIZE
    rows = bytearray()
    for line in range(height):
        share = line / (height - 1)
        pixel = bytes(round(top[c] + (bottom[c] - top[c]) * share)
                      for c in range(3))
        rows.append(0)
        rows.extend(pixel * width)

    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR",
                         struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 9))
            + _png_chunk(b"IEND", b""))


class Palette:
    """Ein Thema, wie der Generator es liest.

    WARUM EINE KLASSE UND NICHT DAS WOERTERBUCH VON OBEN
        Weil src/style_definition.py bisher `brand.PETROL` geschrieben
        hat, an neunzig Stellen, und `THEME.PETROL` genau dieselbe
        Zeile ist. Ein Wechsel auf `palette["PETROL"]` waere neunzig
        Aenderungen mehr gewesen, ohne dass eine davon etwas
        aussagt - und der Test, der Farbliterale in dieser Datei
        verbietet, haette dabei nichts gemerkt.

    WARUM __getattr__ AUF brand ZURUECKFAELLT
        Weil ein Thema die FELDER oben ersetzt und sonst nichts.
        brand.CODE_GREEN, brand.FONT_ICONS, brand.COLOR_GROUPS,
        brand.rgba - alles, was aus den oben aufgezaehlten Gruenden
        NICHT zum Thema gehoert - kommt weiter aus derselben Datei.
        Waeren sie hier noch einmal aufgefuehrt, gaebe es zwei Orte,
        an denen die Antwort steht, und der Kopf von src/brand.py
        erzaehlt, was das das letzte Mal gekostet hat.
    """

    __slots__ = ("name", "_values", "COLORS", "GLASS_IGNORE_ALPHA",
                 "GLASS_SOLO_ALPHA", "FONT_FAMILY_CODE", "FONT_FAMILY_TEXT")

    def __init__(self, name: str, values: dict[str, object]) -> None:
        self.name = name
        self._values = values

        # Die siebzig Rollen, mit den Werten DIESES Themas. Die Tabelle
        # der Rollen steht in brand.COLOR_FIELDS und ist die einzige;
        # hier wird sie nur aufgeloest.
        self.COLORS = {role: values[field]
                       for role, field in brand.COLOR_FIELDS.items()}

        # Abgeleitet, und deshalb hier statt in der Tabelle: die
        # Rechnung dahinter steht in src/brand.py und darf sich nicht
        # je Thema unterscheiden.
        # Mit DIESES Themas Zahlen gerechnet, aber nach brands Formel.
        # Ein Thema, das nur eine der zwei Deckkraefte verstellt,
        # bekaeme sonst eine Platte, die weniger Material traegt als
        # seine eigene Leiste - und das faellt an nichts auf, weil
        # beide Themen heute dieselben zwei Zahlen tragen.
        #
        # Die Formeln stehen in src/brand.py und nicht hier, samt ihrer
        # Begruendung. Waeren sie hier ausgeschrieben, gaebe es sie
        # zweimal, und die Fassung dort haette keinen Leser - genau der
        # Zustand, den die Mutationspruefung am 12.08.2026 aufgedeckt
        # hat: die Konstante liess sich verstellen, ohne dass sich ein
        # erzeugtes Byte bewegte.
        self.GLASS_IGNORE_ALPHA = brand.glass_ignore_alpha(
            float(values["GLASS_PANEL_ALPHA"]))
        self.GLASS_SOLO_ALPHA = brand.glass_solo_alpha(
            float(values["GLASS_PANEL_ALPHA"]),
            float(values["GLASS_CHIP_ALPHA"]))
        self.FONT_FAMILY_CODE = brand.font_family_code(values["FONT_CODE"])
        self.FONT_FAMILY_TEXT = brand.font_family_text(values["FONT_TEXT"])

    def __getattr__(self, name: str):
        values = object.__getattribute__(self, "_values")
        if name in values:
            return values[name]
        return getattr(brand, name)


def palette(name: str) -> Palette:
    """Die Palette dieses Themas, oder eine Ausnahme.

    Keine stille Vorgabe: ein Name, den es nicht gibt, ist entweder ein
    Tippfehler oder ein Thema aus einer neueren Fassung, und in beiden
    Faellen ist ein Schreibtisch im Standardthema die falsche Antwort -
    er saehe vollstaendig richtig aus und waere nicht das, was
    eingestellt ist.
    """
    try:
        values = THEMES[name]
    except KeyError:
        raise UnknownTheme(
            f"es gibt kein Thema namens {name!r}. Bekannt sind: "
            f"{', '.join(sorted(THEMES))}. Der Name steht in "
            f"{name_path()}."
        ) from None
    return Palette(name, values)


def name_path():
    """Die Datei, in der der Name der Maschine steht."""
    return machine_root() / FILENAME


def read_name(path=None) -> str:
    """Was in der Datei steht, oder das ausgelieferte Thema.

    KEINE Datei ist die Antwort "noch nie etwas eingestellt", und das
    ist der normale Zustand einer frischen Installation - dieselbe
    Unterscheidung, die _load_user_settings() zwischen "keine Datei"
    und "unlesbare Datei" trifft. Eine Datei, die es GIBT und die nicht
    gelesen werden kann, faellt hier trotzdem auf die Vorgabe zurueck
    und nicht in eine Ausnahme: sie enthaelt einen Namen und keine
    Konfiguration, es geht also nichts verloren, was jemand
    eingestellt hat und was ueberschrieben werden koennte.

    Der NAME wird geprueft, nicht die Datei: palette() faellt ueber
    einen unbekannten Namen, und zwar dort, wo etwas erzeugt wird.
    """
    target = path if path is not None else name_path()
    try:
        found = target.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT
    return found or DEFAULT


def write_name(name: str, path=None):
    """Den Namen hinschreiben - nachdem geprueft ist, dass es ihn gibt.

    Geprueft VOR dem Schreiben, weil die Datei sonst eine Maschine
    beschreiben koennte, deren Schreibtisch sich nicht mehr erzeugen
    laesst: der Generator bricht ueber einen unbekannten Namen ab, und
    der Weg zurueck fuehrt durch dieselbe Datei.
    """
    if name not in THEMES:
        raise UnknownTheme(
            f"es gibt kein Thema namens {name!r}. Bekannt sind: "
            f"{', '.join(sorted(THEMES))}.")
    target = path if path is not None else name_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{name}\n", encoding="utf-8")
    return target


def active(path=None) -> Palette:
    """Die Palette, mit der auf dieser Maschine erzeugt wird."""
    return palette(read_name(path))
