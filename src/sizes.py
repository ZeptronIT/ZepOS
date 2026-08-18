# SPDX-License-Identifier: GPL-3.0-or-later
"""Wie gross der Schreibtisch ist, und was der Nutzer daran drehen kann.

Ein eigenes Modul aus demselben Grund wie audio.py, clocks.py und
vpn.py: die Tabelle wird von ZWEI Seiten gelesen. style_definition.py
baut die {{STYLE_*}}-Werte daraus, und user_settings.py braucht
dieselbe Tabelle, um `set-size` gegen sie zu pruefen und `list-sizes`
daraus zu drucken. Stuende sie in style_definition.py, muesste
user_settings.py das importieren - und das liest beim Import die
Einstellungsdatei und fragt monitors.py nach dem Schreibtisch, also
genau die beiden Dinge, die ein Befehl zum SCHREIBEN von Einstellungen
nicht tun darf.

Dieses Modul importiert nichts aus dem Projekt und hat keine
Nebenwirkung.


DER UMRECHNUNGSPUNKT ZWISCHEN DEN DREI GROESSENSYSTEMEN
    ZepOS misst Schrift an drei Stellen und in drei Einheiten. Das sind
    drei verschiedene FAEHIGKEITEN und kein Fehler:

      Startmenue    Pixel, fest in eine Schriftdatei gebrannt.
                    iso/make-boot-theme.sh ruft `grub-mkfont -s 24` auf
                    und legt roboto-24.pf2 an; theme.txt waehlt
                    "Roboto Regular 24". GRUB kann keine Groesse
                    rechnen, es kann nur eine geladene Datei benutzen.
      Assistent     rem, also ein Vielfaches der Systemschrift.
                    installer/gui/branding.py setzt `row, label, button`
                    auf 1.35rem. Er laeuft, BEVOR eine Monitor-
                    konfiguration existiert, und kann deshalb gar nicht
                    in Pixeln rechnen.
      Schreibtisch  Pixel, hier. Der einzige der drei, der weiss, was
                    angeschlossen ist.

    Der Zwang ist also nicht dieselbe Einheit, sondern dasselbe ERGEBNIS
    auf dem Schirm.

    GEMELDET am 11.08.2026: "ich will auch das wir das style groesser
    machen vergleichbar mit dem installation wizard genauso soll es sein
    aber voll anpassbar".

WARUM DER ANKER DAS STARTMENUE IST UND NICHT DER ASSISTENT
    1.35rem sind nur dann 24 px, wenn die Systemschrift 17.8 px gross
    ist. Das Medium setzt gtk-font-name nirgends - gemessen am
    11.08.2026, kein einziger Treffer im ganzen Baum - also gilt GTKs
    eigene Vorgabe (Cantarell 11 = 14.67 px bei 96 dpi), und branding.py
    beziffert sie selbst mit "nearer 15". Der Assistent zeichnet seinen
    Fliesstext also bei rund 19.8 px und VERFEHLT sein eigenes,
    ausgeschriebenes Ziel ("24px on a 1080 screen") um ein Fuenftel.

    Die 24 px des Startmenues sind dagegen kein Ziel, sondern eine
    Datei: `grub-mkfont -s 24`. Sie sind der einzige Wert der Kette, der
    nicht davon abhaengt, was jemand eingestellt hat oder nicht. Deshalb
    ist er der Anker.

WAS DAGEGEN SPRICHT, UND WARUM ES TROTZDEM SO IST
    branding.py argumentiert selbst, dass ein Installer groesser sein
    DARF als ein Schreibtisch: er wird einmal gelesen, auf fremder
    Hardware, oft auf Armeslaenge, manchmal auf einem Schirm, dessen
    Skalierung noch niemand gesetzt hat. Ein Schreibtisch wird den
    ganzen Tag am eigenen Tisch benutzt. Das ist ein gutes Argument, und
    der Nutzer hat es ueberstimmt, nachdem er beide nebeneinander
    gesehen hatte. Die Gegenrichtung kostet einen Befehl:

        zepos-settings set sizes.scale 1.0

WARUM EIN FAKTOR UND KEINE TABELLE PRO AUFLOESUNGSKLASSE
    MONITOR_WIDTH_SCALES gibt es, mit vier Klassen und vier Vorgaben.
    GEMESSEN am 11.08.2026: die Platzhalter, die daraus gebaut werden -
    STYLE_SCALE_FACTOR_MON0 bis MON4 - werden von KEINER Vorlage
    benutzt. Der Schreibtisch skaliert also faktisch nicht nach
    Aufloesung.

    Hier wird das nicht nachgeholt, und der Grund ist nicht Aufwand,
    sondern die Form der Ausgabe: base-style.template ist EIN Stylesheet
    fuer alle Leisten und ags-style.template EINES fuer alle
    Ueberlagerungen. GTK-CSS kennt keinen Selektor fuer einen Monitor.
    Eine Schriftgroesse pro Aufloesungsklasse laesst sich in diesen
    Dateien nicht ausdruecken - sie waere kein unverdrahteter Regler,
    sondern ein unverdrahtbarer.

    Was pro Schirm verschieden sein KANN, ist die Fenstergroesse der
    AGS-Ueberlagerungen, und die ist es bereits: widget_sizes.<breite>
    .<widget>.{width,height}. Sie wird hier absichtlich nicht auch noch
    mit dem Faktor multipliziert - siehe user_settings
    .RETIRED_SCALING_DIMENSION dafuer, was zwei Regler fuer eine Zahl
    kosten.
"""
from __future__ import annotations

import math

# Die Grundschrift des Startmenues, in Pixeln. iso/make-boot-theme.sh.
ANCHOR_PX = 24

# Die Grundschrift des Schreibtischs vor dieser Aenderung, in Pixeln.
# Sie ist auch weiterhin der Grundwert von STYLE_FONT_BODY unten - der
# Faktor multipliziert sie, er ersetzt sie nicht -, und seit dem
# 12.08.2026 zugleich der ANKER DER SCHRIFTLEITER: jede Sprosse ist
# BASE_PX mal einer Potenz von FONT_RATIO.
BASE_PX = 13

# Die Grundschrift, mit der der Schreibtisch AUSGELIEFERT wird.
#
# WARUM SIE SEIT DEM 12.08.2026 NICHT MEHR ANCHOR_PX IST
#     Hier stand `SCALE_DEFAULT = ANCHOR_PX / BASE_PX`, also 24/13 =
#     1.846, und die Begruendung war der Wunsch des Nutzers vom
#     11.08.2026: "ich will auch das wir das style groesser machen
#     vergleichbar mit dem installation wizard genauso soll es sein".
#     Der Schreibtisch sollte in derselben Groesse schreiben wie das
#     Startmenue.
#
#     Am 12.08.2026 hat derselbe Nutzer das Ergebnis auf echter Hardware
#     gesehen und die Kopplung widerrufen:
#
#         "die fontsize muss vlt ein bisschen kleiner gemacht werden
#          weil wir zu wenig inhalt drauf bekommen auf den header"
#
#     Das ist keine Geschmacksaenderung, sondern ein anderer Zwang. Das
#     Startmenue zeigt fuenf Zeilen untereinander auf einem leeren
#     Schirm; die Leiste zeigt achtzehn Module NEBENEINANDER auf einem
#     Schirm bekannter Breite. Zwei Flaechen mit verschiedenen Zwaengen
#     duerfen nicht an einer Zahl haengen - genau die Art Kopplung, die
#     diese Datei sonst aufloest.
#
#     ANCHOR_PX bleibt, weil es weiter etwas Wahres sagt: es ist die
#     Groesse, mit der `grub-mkfont -s 24` das Startmenue setzt, und
#     tests/src/test_sizes.py haelt die beiden Dateien darueber
#     zusammen. Es ist ab jetzt eine MESSUNG einer anderen Datei und
#     keine Entscheidung ueber diese.
#
# WORAUS DIE 20 KOMMT - GEMESSEN, NICHT GEWAEHLT
#     Aus der Frage, die der Nutzer gestellt hat, umgedreht: nicht
#     "welche Groesse nehmen wir", sondern "welche ist die groesste, bei
#     der ALLE Module auf den Schirm passen". Gemessen am 12.08.2026 mit
#     tests/src/bar_fit_child.tsx, kopflos unter gtk4-broadwayd, mit dem
#     erzeugten Stylesheet und den Inhalten einer frisch installierten
#     Maschine (kein Wetterort, keine zweite Zeitzone, keine
#     gespeicherte Anordnung - diese drei Module schweigen dann und
#     kosten nichts):
#
#         Grundschrift  Mindestbreite   eingeklappt bei Schirmbreite
#                                       1366   1600   1920   2560
#           20 px          1891           6      4      0      0
#           21 px          1973           7      5      2      0
#           22 px          2061           7      5      3      0
#           24 px (alt)    2528          12      9      6      0
#
#     20 ist die groesste Sprosse, bei der auf 1920 - dem verbreitetsten
#     Schirm - NICHTS in das Aufklappfenster wandert. Bei 21 sind es
#     zwei Module, bei der bisherigen 24 sechs. Und die sechs waren
#     genau die, die der Nutzer am selben Tag vermisst hat: "akku
#     anzeige fehlt btop in der waybar mikrofon und lautstaerke fehlt".
#     Sie fehlten nicht, sie lagen hinter dem Knopf.
#
#     DER PREIS STEHT DAZU: 1891 auf 1920 sind 29 Pixel Luft. Das ist
#     wenig, und es ist die Zeile, die faellt, wenn ein Modul um mehr
#     als das waechst - siehe
#     test_the_bar_holds_every_module_on_the_common_screen in
#     tests/src/test_bar_headless.py.
#
#     UND WAS DAMIT NICHT GELOEST IST: auf 1366 klappen auch bei 20 px
#     noch sechs Module ein, und selbst bei 13 px waeren es vier. Auf
#     diesem Schirm sind es zu viele Module, nicht zu grosse Schrift.
#     Das ist eine eigene Entscheidung - welche Module in die
#     Ueberlagerungen gehoeren - und keine, die ein Regler beantwortet.
#     Wer einen solchen Schirm hat, dreht ihn kleiner:
#     `zepos-settings set sizes.scale 1.0`.
DEFAULT_PX = 20

SCALE_DEFAULT = DEFAULT_PX / BASE_PX

# Der Abschnitt in user-settings.json, dem das hier alles gehoert.
SECTION = "sizes"


# Ob eine Groesse dem Faktor folgt.
#
# DIE GRENZE LAEUFT AN DER SCHRIFT ENTLANG, NICHT AM GESCHMACK.
# Skaliert wird, was Text IST oder was einen Text UMSCHLIESST: eine
# Zeilenhoehe, der Abstand zwischen zwei Beschriftungen, die Hoehe der
# Leiste. Nicht skaliert wird, was ein BILD ist - die Symbole im Dock und
# in der Statusablage sind Anwendungsgrafik aus fremden Prozessen, die
# das Symbolthema in ihrer eigenen Groesse liefert, und mit 48 px schon
# jetzt fast das Vierfache der Leistenschrift. Mit dem Faktor
# multipliziert waeren sie 89 px hoch.
#
# Beides bleibt EINZELN einstellbar; das ist der Sinn von sizes.values.
# Der Unterschied ist nur, wohin der eine Regler greift.
SCALED = True
FIXED = False

# Ob der erzeugte Wert ein "px" traegt. Das haengt nicht am Wert,
# sondern am Leser: ags-bar.template ist TypeScript und
# hyprland-plugins-config.template ist Hyprland-Syntax; beide nehmen
# eine nackte Zahl und scheitern an "50px" - im ersten Fall waere
# `const BAR_THICKNESS = 92px` ein Syntaxfehler, der die ganze Leiste
# kostet. Die Stylesheets brauchen die Einheit.
PX = "px"
BARE = ""

# Und eine dritte, fuer die Bewegungsleiter. CSS nimmt "300ms" oder
# "0.3s"; die Millisekunde ist die Einheit ohne Nachkommastelle, also
# die, in der sich eine ganze Zahl schreiben laesst.
MS = "ms"


class Size:
    """Eine einstellbare Groesse: Grundwert, Einheit, folgt dem Faktor.

    Eine Klasse und kein Tripel, damit die drei Felder an jeder
    Fundstelle benannt sind: `Size(13, PX, SCALED)` liest sich,
    `(13, "px", True)` nicht.
    """

    __slots__ = ("base", "unit", "scales")

    def __init__(self, base: int, unit: str, scales: bool) -> None:
        self.base = base
        self.unit = unit
        self.scales = scales


# =====================================================================
# DIE SCHRIFTLEITER - eine Skala, keine Liste von Pixelwerten
# =====================================================================
#
# GEMELDET am 12.08.2026: "wir muessen auch ein generelles layout fuer
# ZepOS festlegen icon groessen und schriftgroessen sowie maximale
# element groessen haben wir das schon das sorgt dafuer das wir ein sehr
# schoenes design haben mit glasmorpihms und so weiter".
#
# WAS HIER VORHER STAND, UND WARUM ES KEINE LEITER WAR
#     AGS_FONT_LADDER = (9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24,
#     32, 36, 48, 64) - sechzehn Sprossen, jede nach ihrer eigenen Zahl
#     benannt, eine pro Pixelwert, den irgendwann jemand gebraucht hat.
#     Dazu STYLE_FONT_SIZE 13, _SMALL 12 und _LARGE 14: drei Namen fuer
#     drei Zahlen, die einen Pixel auseinanderliegen.
#
#     Das war ein KATALOG. Er hatte gegenueber den 164 Literalen, die er
#     abgeloest hat, genau einen Vorteil - er folgte dem Regler - und
#     zwei Fehler behalten:
#
#       Ein Name sagt nicht, WOFUER er da ist. `STYLE_EWW_FONT_14` sagt
#       "vierzehn" und nicht "die Zeile, die man liest". Wer eine neue
#       Regel schreibt, kann daraus nicht ableiten, welche Sprosse er
#       nehmen soll, also nimmt er die, die zufaellig danebensteht.
#
#       Der Name luegt nach dem ersten Drehen. Bei der ausgelieferten
#       1.85 kommt aus FONT_14 eine 26 heraus. Der Platzhalter heisst
#       weiter 14, und das Stylesheet liest sich wie eine Datei voller
#       Vierzehner, in der nirgends eine 14 steht.
#
#     Und die sechzehn waren keine sechzehn Entscheidungen. GEMESSEN am
#     12.08.2026 ueber ags-style.template, hyprclipx-style.template und
#     hyprlaunch-style.template - 175 font-size-Regeln:
#
#         14px  30x     16px  14x     22px   8x     36px   1x
#         12px  29x     13px  15x     10px   7x     15px   1x
#         11px  28x     18px  20x     20px   4x     64px   1x
#          9px   9x     24px   4x     48px   3x     32px   2x
#
#     Die vier haeufigsten - 11, 12, 13, 14 - liegen ALLE einen Pixel
#     auseinander und machen zusammen zwei Drittel der Regeln aus. Das
#     sind nicht vier Groessen, das ist eine Groesse, die viermal
#     unabhaengig gewaehlt wurde.
#
# DAS VERHAELTNIS IST 1.2, UND ES IST GEMESSEN
#     Eine Skala braucht EINE Zahl. Die beiden ueblichen sind 1.2 (die
#     kleine Terz) und 1.25 (die grosse Terz). Welche zu ZepOS passt,
#     entscheidet nicht der Geschmack, sondern die Frage, wie weit sich
#     die 175 Regeln bewegen muessen, um auf einer Sprosse zu landen.
#
#     GERECHNET am 12.08.2026 ueber die 128 Regeln, die FLIESSTEXT
#     setzen (die uebrigen 47 sind Symbolzeichen, siehe unten), gegen
#     eine Leiter, die auf BASE_PX = 13 verankert ist:
#
#         Verhaeltnis   Sprossen im Textbereich   Bewegung je Regel
#         1.15          10, 11, 13, 15, 17              0.63 px
#         1.20           9, 11, 13, 16, 19              0.57 px
#         1.25          10, 13, 16                      0.89 px
#         1.30          10, 13, 17                      0.86 px
#
#     1.2 gewinnt, und nicht knapp: keine Textregel bewegt sich um mehr
#     als EINEN Pixel, waehrend 1.25 nur drei Sprossen im ganzen
#     Textbereich anbietet und Regeln um zwei Pixel verschiebt.
#
#     Drei seiner Sprossen - 9, 11, 13 - sind Zahlen, die der
#     Schreibtisch heute schon schreibt, darunter die zweithaeufigste
#     (11, 28 Regeln) und der Anker selbst. Und 1.2 hoch vier ist 2.07:
#     vier Schritte verdoppeln, und 9 bis 18 ist genau die Spanne, die
#     der Fliesstext dieses Schreibtischs einnimmt. Die Leiter ist an
#     dem gefunden worden, was da ist - dasselbe Vorgehen wie bei
#     SPACE_UNIT = 4 weiter unten.
#
# WARUM DIE SPROSSEN ROLLEN HEISSEN UND WAS DIE LUECKE SOLL
#     Der Name nennt die Aufgabe: CAPTION ist die beschriftende Haelfte
#     eines Paares, LEAD der Wert, um den es in der Zeile geht, TITLE die
#     Ueberschrift eines Fensters. Das ist die Frage, die jemand
#     beantworten kann, der eine neue Regel schreibt; "vierzehn oder
#     sechzehn" ist es nicht.
#
#     Die Sprossen sind als EXPONENT hinterlegt und nicht als Pixelwert.
#     Damit gibt es genau eine Zahl zu aendern - FONT_RATIO -, und alles
#     folgt; ein Pixelwert in dieser Tabelle waere die Skala noch einmal,
#     nur abgeschrieben.
#
#     Zwischen TITLE (Exponent 2) und DISPLAY (5) klafft eine Luecke, und
#     sie ist keine Nachlaessigkeit: Exponent 4 (27 px) hat KEINEN Leser.
#     Die Sprossen 3 und 6 dagegen sind besetzt - als Symbolgroesse von
#     TITLE und DISPLAY, siehe LINE_HEIGHT. Zwischen Exponent -2 und 8
#     ist damit genau eine Sprosse unbesetzt, und eine Sprosse ohne Leser
#     ist der Regler, den dieses Projekt schon zweimal geloescht hat.
FONT_RATIO = 1.2

FONT_PREFIX = "STYLE_FONT_"
ICON_PREFIX = "STYLE_ICON_"

# (Rolle, Exponent). Der Exponent ist die Potenz von FONT_RATIO, mit der
# BASE_PX multipliziert wird.
#
#   MICRO    -2   9 px   Zaehler, Abzeichen, Hinweise, Anzeiger
#   CAPTION  -1  11 px   die beschriftende Haelfte eines Paares
#   BODY      0  13 px   die Zeile, die man liest - der Anker
#   LEAD      1  16 px   der Wert, um den es in der Zeile geht
#   TITLE     2  19 px   die Ueberschrift eines Fensters
#   DISPLAY   5  32 px   die hervorgehobene Zahl einer Kachel
#   HERO      7  47 px   die eine Zahl, DIE das Fenster ist
#
# WARUM DISPLAY UND HERO DREI ZAHLEN AUF ZWEI ZUSAMMENZIEHEN
#     GEMESSEN: drei Fenster zeigen ihre eine grosse Zahl in drei
#     verschiedenen Groessen - der Akku 32, die Platte 48, der Kalender
#     64. Eine Rolle, drei Zahlen, ad hoc gewaehlt; das ist der Katalog
#     in Reinform, und genau der Zustand, den der Nutzer "nicht
#     einheitlich" nennt.
#
#     Zwei Rollen und nicht eine, weil die Messung zwei Gruppen zeigt und
#     nicht eine: 32 steht neben einer Statuszeile (der Akku zeigt
#     Prozent UND Zustand), 48 und 64 stehen allein auf ihrer Flaeche.
#     Der Akku bleibt damit auf 32, die Platte geht von 48 auf 47, und
#     nur der Kalendertag bewegt sich wirklich - von 64 auf 47. Bei der
#     ausgelieferten 1.85 sind das 87 px statt 118, und immer noch mehr
#     als das Doppelte der Ueberschrift daneben.
FONT_ROLES: tuple[tuple[str, int], ...] = (
    ("MICRO", -2),
    ("CAPTION", -1),
    ("BODY", 0),
    ("LEAD", 1),
    ("TITLE", 2),
    ("DISPLAY", 5),
    ("HERO", 7),
)

# Die Zeilenhoehe, und damit die Groesse eines SYMBOLS in einer Zeile.
#
# WARUM SYMBOLE UEBERHAUPT AN DIE ZEILE GEBUNDEN WERDEN
#     Die Symbole dieses Schreibtischs sind Nerd-Font-Zeichen, also
#     Schrift - `font-size: 22px` auf einem Label, dessen Text ein
#     Zeichen ist. Sie standen damit auf derselben Katalogleiter wie der
#     Fliesstext und wurden auch so gewaehlt: frei, Regel fuer Regel.
#     Ein Symbol IST aber keine Schrift, es ist ein Bild in einer Zeile,
#     und die einzige Groesse, die dafuer richtig ist, ist die HOEHE DER
#     ZEILE, in der es steht. Ein Zeichen, das kleiner ist als seine
#     Zeile, sitzt in einem Loch; eines, das groesser ist, drueckt die
#     Zeile auf.
#
# 1.2 IST GEMESSEN UND NICHT AUS DER LEITER ABGESCHRIEBEN
#     Elf Fenster tragen eine Kopfzeile aus Zeichen und Ueberschrift.
#     GEMESSEN am 12.08.2026 in ags-style.template: NEUN davon setzen
#     18 px Text neben 22 px Zeichen, also das 1.222-fache - und keine
#     zwei davon haben sich dabei abgesprochen, denn jede schreibt ihre
#     Zahl selbst hin. Das ist zugleich der Wert, den CSS `line-height:
#     normal` fuer Roboto und Fira Code aufloest.
#
#     Dass diese 1.2 dieselbe Zahl ist wie FONT_RATIO, ist eine
#     Uebereinstimmung und keine Ableitung: die eine kommt aus elf
#     Kopfzeilen, die andere aus 128 Textregeln. Sie sind deshalb ZWEI
#     Konstanten. Dass sie heute gleich sind, hat eine sichtbare Folge -
#     das Symbol einer Rolle liegt genau auf der naechsten Sprosse -, und
#     tests/src/test_design.py rechnet das nach, damit es auffaellt, wenn
#     eine der beiden wandert.
LINE_HEIGHT = 1.2


# Die Abstandsleiter. Dieselbe Grundeinheit wie die Schriftstufen - ein
# Full-HD-Pixel, mit demselben Faktor multipliziert -, nur in Vierteln
# davon gestuft.
#
# WARUM ABSTAND UEBERHAUPT EINE LEITER BRAUCHT
#     GEMELDET am 11.08.2026: "kein einheitlicher Abstand auf allen
#     Seiten von ZepOs". GEMESSEN am selben Tag in
#     ags-style.template, dem Stylesheet aller Ueberlagerungsfenster:
#     294 Zahlen in padding- und margin-Regeln, in elf verschiedenen
#     Werten - 2, 4, 5, 6, 8, 10, 12, 14, 16, 20, 24 -, und die
#     haeufigsten vier (8, 12, 4, 10) machen zusammen nur zwei Drittel
#     aus. Einheitlich ist das nicht, und es kann es auch nicht werden:
#     solange jede Regel ihre eigene Zahl traegt, ist jede Uebereinstimmung
#     zwischen zwei Regeln ein Zufall, der beim naechsten Anfassen einer
#     davon wieder verloren geht.
#
#     Eine Leiter ist der Unterschied zwischen "diese beiden Regeln haben
#     zufaellig dieselbe Zahl" und "diese beiden Regeln stehen auf
#     derselben Sprosse".
#
# WARUM VIER UND NICHT ZWEI ODER ACHT
#     Zwei waere keine Leiter, sondern die Erlaubnis, jede gerade Zahl zu
#     schreiben - die elf gemessenen Werte oben sind bis auf die 5 alle
#     gerade, eine Zweierleiter haette also genau EINE Regel geaendert.
#     Acht waere eine Leiter mit vier Sprossen fuer eine Oberflaeche, die
#     nachweislich sieben braucht: der Abstand zwischen zwei Zeilen einer
#     Liste und der Rand eines Fensters sind nicht dasselbe Mass.
#
#     Vier ist ausserdem die Einheit, auf der der Assistent BEREITS steht,
#     ohne dass das je aufgeschrieben wurde. installer/gui/branding.py
#     setzt seine Abstaende in rem, und gemessen am 11.08.2026 liegen
#     sechs seiner acht Werte - 1rem, 1.5rem, 1rem 1.5rem, 1.5rem - auf
#     einem halben rem, also auf genau dieser Leiter. Sie wurde hier nicht
#     erfunden, sondern gefunden.
#
# WIE DIE ELF GEMESSENEN WERTE AUF SIEBEN SPROSSEN KOMMEN
#     Kaufmaennisch auf das Vielfache von vier, also mit derselben Regel,
#     mit der value_of() unten die Schriftleiter rundet: 5 -> 4, 6 -> 8,
#     10 -> 12, 14 -> 16. Die 2 bleibt und ist die einzige halbe Sprosse -
#     sie ist der Haarabstand zwischen zwei Kacheln, und 4 daraus zu
#     machen hiesse, ihn zu verdoppeln.
#
# WARUM DER ABSTAND DEM FAKTOR FOLGT
#     Weil die Schrift es tut. Bei der ausgelieferten 1.85 traegt eine
#     Zeile 24 px hohe Buchstaben in 8 px Innenabstand - die Schrift ist
#     dreimal so hoch wie der Rand um sie herum. Das ist genau der
#     Zustand, den ein Nutzer "nicht einheitlich" nennt, und dieselbe
#     Begruendung, die STYLE_MODULE_SPACING unten schon traegt.
SPACE_UNIT = 4
SPACE_LADDER = (2, 4, 8, 12, 16, 20, 24)
SPACE_PREFIX = "STYLE_SPACE_"

# Wieviele Grundpixel ein rem sind, fuer die zwei Oberflaechen, die in
# rem rechnen MUESSEN: den Assistenten und die Anmeldemaske. Beide laufen,
# bevor irgendeine Monitorkonfiguration existiert, und koennen deshalb
# nicht in Pixeln rechnen - der Kopf dieser Datei sagt das fuer den
# Assistenten schon.
#
# GEMESSEN, NICHT GEWAEHLT: GTKs eigene Vorgabe ist Cantarell 11, also
# 14.67 px bei 96 dpi (branding.py beziffert sie selbst mit "nearer 15").
# Die Sprosse 8 ergibt bei der ausgelieferten 1.85 gerundet 15 px. Ein rem
# IST also die Sprosse 8, auf zwei Hundertstel genau, und damit fallen
# alle sieben Sprossen auf glatte Viertel-rem: 0.25, 0.5, 1, 1.5, 2, 2.5,
# 3.
#
# Was diese Umrechnung NICHT kann: dem Faktor folgen. Der Assistent liest
# die Einstellungsdatei des Zielsystems nicht - es gibt sie beim
# Installieren noch gar nicht -, also rechnet er immer mit der
# ausgelieferten Groesse. Wer den Schreibtisch kleiner stellt, stellt den
# Assistenten nicht mit, und das ist richtig so: der Assistent laeuft
# einmal, auf fremder Hardware.
SPACE_REM_UNIT = 8


def rem_of(step: int) -> str:
    """Eine Sprosse als rem-Wert, fuer Assistent und Anmeldemaske.

    Als Zeichenkette und ohne nachlaufende Nullen, damit "1rem" in der
    erzeugten Datei auch "1rem" heisst und nicht "1.0rem" - der
    Assistent traegt die Werte heute so, und ein Stylesheet, das sich
    beim Umstellen in jeder Zeile aendert, verdeckt die Zeilen, in denen
    sich wirklich etwas geaendert hat.
    """
    value = step / SPACE_REM_UNIT
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}rem"


# =====================================================================
# DIE RUNDUNGSLEITER - die Form der Marke, und was Glas braucht
# =====================================================================
#
# WARUM DAS HIER STEHT UND NICHT BEI DEN ABSTAENDEN
#     tests/src/test_spacing.py schreibt es aus: "das eine ist eine
#     Breite und das andere eine Ecke, und beide gehoeren nicht auf eine
#     Abstandsleiter". Trotzdem stand bar-style.template am 12.08.2026
#     mit `border-radius: {{STYLE_SPACE_12}}` und `{{STYLE_SPACE_8}}`
#     genau dort - weil es fuer eine Ecke nichts anderes gab.
#
# WAS GEMESSEN WURDE
#     Am 12.08.2026 ueber jede Regel im Baum, die eine Ecke setzt:
#
#         border-radius: 0        54x   in ags-style.template
#         STYLE_BORDER_RADIUS      7x   und war selbst "0px"
#         STYLE_BORDER_RADIUS_SMALL 3x  8px
#         5px                      4x   Menue, Starter, Ablage, mako
#         4px                      2x   im Stil-Editor
#         STYLE_SPACE_12 / _8      2x   die Leiste, ueber die Abstandsleiter
#         STYLE_TOOLTIP_BORDER_RADIUS 1x 10px
#         2px                      1x
#         50%                      1x
#         STYLE_WINDOW_ROUNDING         8px, fuer Hyprland
#
#     Dazu VIER Platzhalter mit null Lesern - STYLE_EWW_RADIUS_SM 3px,
#     _MD 4px, _BASE 6px, _LG 8px - und STYLE_EWW_RADIUS_CIRCLE und
#     STYLE_WALLPAPER_THUMBNAIL_RADIUS, ebenfalls null. Sechs tote
#     Regler, dieselbe Geschichte wie MONITOR_HEIGHT_SCALES.
#
#     Die 54 Nullen sind der eigentliche Befund, und sie stehen nicht
#     zufaellig: ELF davon auf `*-container` und `.overlay-outer`, also
#     auf jeder Glasscheibe, die dieser Schreibtisch hat, und rund
#     dreissig auf Knoepfen, Eingaben und Reitern. Der Schreibtisch hat
#     runde Fenster (Hyprland, 8), runde Leistenmodule (12) - und
#     quadratische Ueberlagerungen dazwischen.
#
# WARUM DAS FUER GLAS DOPPELT ZAEHLT
#     brand.glass_ignore_alpha() rechnet bereits MIT runden Ecken: "Die
#     antialiasten Pixel einer runden Ecke steigen von 0 auf
#     GLASS_PANEL_ALPHA; die Schwelle halbiert diese Rampe, damit die
#     Unschaerfe INNERHALB der Ecke endet statt sie eckig abzuschneiden."
#     Diese Rechnung stand seit dem 11.08.2026 da, und die Ecken, fuer
#     die sie gilt, gab es nicht. Glas lebt von seiner Kante; eine
#     unscharfe Flaeche mit rechten Ecken sieht nicht nach Scheibe aus,
#     sondern nach einem Fehler im Compositor.
#
# DAS VERHAELTNIS IST 1.6, UND ES IST AN DEN VORGEFUNDENEN WERTEN GEEICHT
#     Eine Ecke ist proportional zu dem Kasten, den sie rundet, und die
#     Kaesten dieses Schreibtischs kommen in drei Groessen: ein
#     Bedienelement (eine Zeile hoch), eine Kachel (ein paar Zeilen), eine
#     Scheibe (ein Fenster). Also drei Sprossen.
#
#     Verankert wird auf 8 - der Wert, den heute die meisten Regeln
#     tragen (STYLE_BORDER_RADIUS_SMALL dreimal, STYLE_WINDOW_ROUNDING,
#     die Leistenkacheln ueber SPACE_8). Mit 1.6 fallen die drei Sprossen
#     auf 5, 8 und 13, und ZWEI davon sind Zahlen, die der Baum schon
#     schreibt: die 5 steht viermal (Menue, Starter, Ablage, mako), die 8
#     fuenfmal. Die 13 ist die 12 der Leiste plus eins.
#
#     1.5 waere die naheliegende Alternative und faellt aus: sie ergibt
#     5.33 und 12, also nach dem Runden 5 und 12 - und eine vierte
#     Sprosse darunter waere 3.6, also 4, einen Pixel neben der 5. Zwei
#     Sprossen einen Pixel auseinander sind genau die Krankheit, die
#     diese Datei bei der Schrift gerade behandelt.
#
# WARUM DIE RUNDUNG DEM REGLER FOLGT
#     Weil sie es heute schon tut, an beiden Stellen, an denen es sie
#     ueberhaupt gibt: STYLE_WINDOW_ROUNDING steht unten als SCALED, und
#     die Leistenkacheln haengen ueber die Abstandsleiter am selben
#     Faktor. Eine Ecke, die stehenbleibt, waehrend ihr Kasten auf das
#     1.85-fache waechst, wird optisch spitzer - sie ist dann nicht mehr
#     dieselbe Form, sondern eine andere.
#
# WARUM SIE TROTZDEM NICHT EINZELN EINSTELLBAR IST
#     Die Rundung traegt die FORM der Marke, so wie die Farben ihren Ton
#     tragen. Drei Regler dafuer anzubieten hiesse, dem Nutzer die
#     Entscheidung zu geben, ob ZepOS wie ZepOS aussieht - und zwar in
#     einer Aufloesung, in der eine falsche Antwort (5 neben 13 auf
#     derselben Flaeche) wie ein Versehen aussieht. Die eine Ausnahme
#     bleibt STYLE_WINDOW_ROUNDING: sie steht seit dem 12.08.2026 als
#     Drehknopf in der Einstellungs-Anwendung, weil eine Fensterecke das
#     einzige an dieser Leiter ist, das ein Mensch von sich aus sucht.
RADIUS_ANCHOR = 8
RADIUS_RATIO = 1.6

RADIUS_PREFIX = "STYLE_RADIUS_"

#   CONTROL  -1   5 px   Knopf, Eingabe, Reiter, Abzeichen
#   CARD      0   8 px   Kachel, Zeile, Vorschaubild, Kurzhinweis
#   PANEL     1  13 px   die Scheibe: ein Ueberlagerungsfenster, die Leiste
RADIUS_ROLES: tuple[tuple[str, int], ...] = (
    ("CONTROL", -1),
    ("CARD", 0),
    ("PANEL", 1),
)

# Der Kreis. Keine Sprosse, weil er keine Laenge ist: 50 % einer Breite
# ist bei jedem Faktor ein Kreis, und ihn zu multiplizieren hiesse, ihn
# kaputtzumachen. Er steht hier trotzdem, damit die eine Regel, die ihn
# braucht, nicht wieder "50%" hinschreiben muss.
RADIUS_FULL = "50%"

# Die Pille. Aus demselben Grund keine Sprosse wie der Kreis: sie ist
# keine Laenge, sondern die Anweisung "so rund, wie die Hoehe es
# zulaesst". CSS hat dafuer kein Schluesselwort, deshalb eine Zahl, die
# jede vorkommende Hoehe sicher uebersteigt.
#
# Sie kam am 12.08.2026 aus dem Sperrbildschirm-Zweig als eigener Name
# STYLE_LOCK_FIELD_RADIUS mit 999px - der sechste Radiusname neben einer
# Leiter, die es zu dem Zeitpunkt schon gab. Genau die Sorte Zuwachs,
# gegen die test_no_corner_comes_from_a_placeholder_beside_the_ladder
# geschrieben wurde; sie ist nur durchgerutscht, weil dessen Muster
# geschweifte Klammern ausschloss und damit blind fuer Platzhalter war.
RADIUS_PILL = "999px"


# =====================================================================
# DIE GRENZEN - wie breit eine Textspalte werden darf
# =====================================================================
#
# WAS ES DAZU GAB
#     `grep max-width` ueber den ganzen Baum: KEIN Treffer, am
#     12.08.2026. Was es gibt, sind vier Zahlen in Zeichen -
#     `set_max_width_chars(60)` in der Leiste, zweimal
#     `max_width_chars: 40` in den Benachrichtigungen und
#     `preview_chars = 60` in der Zwischenablage - dazu eine fuenfte,
#     hart in C++ (`gtk_label_set_max_width_chars(desc, 60)` im Starter).
#     Fuenf Stellen, drei Zahlen, keine davon irgendwo begruendet.
#
# WARUM DIE GRENZE IN ZEICHEN STEHT UND NICHT IN PIXELN
#     Zwei Gruende, und der zweite ist der wichtigere.
#
#     ERSTENS ist es die Einheit, in der GTK diese Grenze ueberhaupt
#     annimmt. Gtk.Label kennt `max-width-chars`; eine CSS-Regel
#     `max-width` gibt es in GTKs CSS-Teilmenge nicht, und die vier
#     Stellen oben zeigen, dass der Baum das laengst weiss.
#
#     ZWEITENS folgt eine Grenze in Zeichen dem Regler VON SELBST. Waechst
#     die Schrift auf das 1.85-fache, waechst die Spalte mit, und die
#     Zeile bleibt 66 Zeichen lang. Eine Grenze in Pixeln muesste
#     multipliziert werden und waere nach jeder Rundung eine andere Zahl
#     von Zeichen - also eine Lesbarkeitsgrenze, die sich beim Drehen am
#     Regler verschiebt. Deshalb stehen diese beiden als FIXED.
#
# DIE ZAHLEN SIND ZITIERT UND NICHT GEWAEHLT
#     Robert Bringhurst, "The Elements of Typographic Style", 3. Auflage,
#     Abschnitt 2.1.2: "Anything from 45 to 75 characters is widely
#     regarded as a satisfactory length of line for a single-column page
#     ... 66 characters (counting both letters and spaces) is widely
#     regarded as ideal."
#
#     Also die beiden Zahlen, die dort stehen: 45 als die schmale Spalte,
#     66 als die Vorgabe. 75 - das obere Ende des Bandes - waere eine
#     dritte Sprosse ohne Leser und steht deshalb nicht da.
MEASURE_PREFIX = "STYLE_MEASURE_"

MEASURE_LINE = 45
MEASURE_PROSE = 66

# Und die Grenze quer dazu: wie viel vom Schirm ein Fenster hoechstens
# nimmt, das sich VOR etwas anderes stellt.
#
# WARUM ES DIE ERSTE HOEHENGRENZE DIESES SYSTEMS IST
#     Die beiden Zahlen darueber begrenzen eine ZEILE, und dafuer gibt es
#     seit Bringhurst eine Antwort. Fuer die Hoehe gab es bis zum
#     12.08.2026 gar keine Regel, und das Ergebnis stand in
#     menu/zepos_menu/options.py als Literal: `height: 864`.
#
#     GEMELDET am 12.08.2026: "das Suchfenster ist zu hoch". GEMESSEN am
#     selben Tag, und die Zahl ist genauer als die Beschwerde: 864 sind
#     auf einem 1080er Schirm 80 %. Zieht man ab, was Kopf und Fuss sich
#     nehmen - je 83 px Streifen plus 25 px Rand, zusammen 216 -, bleiben
#     864 px frei. Das Suchfenster war also GENAU so hoch wie der ganze
#     Platz, der ueberhaupt noch da war, auf den Pixel, ohne einen Rand.
#     Es war kein Fenster mehr, das sich vor etwas stellt, sondern eines,
#     das alles ersetzt.
#
# WARUM DIE HAELFTE UND NICHT "DER FREIE PLATZ MINUS EIN RAND"
#     Weil "es passt gerade noch" keine Aussage ueber ein Fenster ist,
#     das man ueber seiner Arbeit aufmacht. Der Sinn eines Suchfensters
#     ist, dass man dahinter noch sieht, WORAN man war - deshalb liegt
#     darunter Glas und kein Deckel. Ein Fenster, das den ganzen freien
#     Platz nimmt, macht das Glas zur Dekoration.
#
#     Die Haelfte ist ausserdem die Zahl, die ohne Rechnung stimmt: sie
#     haengt nicht davon ab, wie dick Kopf und Fuss gerade sind, und
#     bleibt damit richtig, wenn jemand am Groessenregler dreht.
#
# EINE ANZAHL UND KEINE LAENGE, wie die beiden darueber: ein Anteil des
# Schirms, und der Schirm ist erst zur Laufzeit bekannt. Gelesen wird er
# deshalb nicht von einer Vorlage, sondern von den Programmen, die ein
# solches Fenster aufziehen.
#
# WER DIESE ZAHL TRAEGT, UND WARUM SIE NICHT IN DIE TABELLE DARUNTER KANN
#     Vier Programme fuehren sie noch einmal, weil keines von ihnen
#     dieses Modul importieren kann - zwei sind C++, eines ist ein
#     eigenes Python-Paket, eines ist TypeScript in einer erzeugten
#     Datei:
#
#         menu/zepos_menu/window.py
#         src/templates/ags-overlay-utils.template
#         plugins/hyprlaunch/include/hyprlaunch/Config.hpp
#         plugins/hyprclipx/include/hyprclipx/Config.hpp
#
#     Am 12.08.2026 hatte sie EINEN Leser, am selben Tag kam der zweite
#     dazu, und die beiden eigenen Programme daneben kannten die Regel
#     gar nicht. tests/src/test_modal_rule.py haelt seither alle vier an
#     einer Stelle gegen diese Zeile und sucht zugleich den ganzen Baum
#     nach einem fuenften Programm ab, das eine Layer-Shell-Flaeche
#     aufzieht.
#
#     Ein Platzhalter in TABLE waere der schoenere Weg und ist versperrt,
#     und das ist GEMESSEN: tests/src/test_sizes.py::
#     test_no_size_can_be_rounded_down_to_nothing prueft ueber JEDEN
#     erzeugten Wert `int(re.match(r"\d+", value).group()) >= 1`, und aus
#     "0.5" liest dieser Ausdruck eine 0. Die Tabelle darunter ist eine
#     Tabelle von LAENGEN; ein Anteil gehoert nicht hinein.
MEASURE_MODAL_SHARE = 0.5


# =====================================================================
# DIE BEWEGUNG - eine Kurve, drei Dauern
# =====================================================================
#
# GEMELDET am 12.08.2026, auf die Frage, ob Bewegung dazugehoert:
# "bewegung ja".
#
# WAS GEMESSEN WURDE
#     STYLE_TRANSITION_DEFAULT = "all 0.3s ease", DREI Leser: der
#     Abmeldeknopf, die Suchzeile des Menues und eine Trefferzeile.
#     Daneben SECHS Platzhalter STYLE_ANIMATION_PULSE_SYNC, _CHECK,
#     _ERROR, _DELETE, STYLE_ANIMATION_BLINK und _SUCCESS_FLASH mit
#     ZUSAMMEN NULL LESERN - dieselbe Geschichte wie die
#     Radius-Platzhalter, nur mit sechs Namen.
#
#     Und in hyprland-universal-config.template ein zweites, voellig
#     getrenntes System: `bezier = myBezier, 0.05, 0.9, 0.1, 1.05` und
#     fuenf Zeilen mit den Geschwindigkeiten 7, 7, 10, 7, 6 (in
#     Zehntelsekunden, also 0.7 / 1.0 / 0.6 s). Der Compositor und die
#     Oberflaeche darauf bewegten sich also nach zwei verschiedenen
#     Kurven und in vier verschiedenen Dauern, und keine der beiden
#     Seiten wusste von der anderen.
#
# DIE KURVE IST DIE, DIE ES SCHON GIBT
#     Genau EINE Kurve ist in diesem Baum je aufgeschrieben worden -
#     myBezier. Sie zu uebernehmen heisst, dass ein Fenster, das
#     aufgeht, und eine Kachel, die hell wird, dieselbe Bewegung machen;
#     eine zweite zu erfinden hiesse, das Problem zu verdoppeln, das
#     gerade behoben wird.
#
#     Ihre vier Zahlen stehen hier als Zahlen und nicht als
#     Zeichenkette, weil ZWEI Leser sie in zwei Schreibweisen brauchen:
#     GTK-CSS will `cubic-bezier(a, b, c, d)`, Hyprland will
#     `bezier = <name>, a, b, c, d`. Eine Zeichenkette waere fuer einen
#     der beiden falsch.
#
#     Das Ende bei 1.05 statt 1.0 ist ein Ueberschwinger - die Bewegung
#     geht fuenf Prozent ueber ihr Ziel hinaus und kommt zurueck. Das
#     ist gewollt (es ist das, was eine Bewegung lebendig statt
#     mechanisch aussehen laesst) und in CSS unbedenklich: eine Farbe
#     oder eine Deckkraft, die ueber ihr Ziel hinausliefe, wird vom
#     Zeichner auf den gueltigen Bereich beschnitten.
MOTION_CURVE_POINTS = (0.05, 0.9, 0.1, 1.05)

# Der Name, unter dem Hyprland die Kurve fuehrt. Hyprland verlangt einen
# Namen und keine Zahlenliste an der Verwendungsstelle.
MOTION_CURVE_NAME = "zepos"

MOTION_PREFIX = "STYLE_MOTION_"

# Die Dauern, in Millisekunden.
#
#   INSTANT  150 ms   Rueckmeldung unter dem Zeiger: eine Kachel wird
#                     hell, ein Knopf wird gedrueckt. Der Nutzer haelt
#                     die Hand still und wartet auf die Antwort.
#   BASE     300 ms   ein Zustandswechsel auf einer Flaeche, die bleibt:
#                     ein Rahmen wechselt die Farbe, etwas blendet auf.
#   ENTER    600 ms   eine Flaeche kommt oder geht: ein Fenster oeffnet,
#                     ein Arbeitsbereich schiebt sich herein.
#
# WARUM 300 DER ANKER IST UND DAS VERHAELTNIS 2
#     300 ms ist die einzige Dauer, die dieser Baum je fuer seine
#     Oberflaeche aufgeschrieben hat ("all 0.3s ease"). Sie bleibt also
#     stehen, und das Verhaeltnis waechst in beide Richtungen daraus.
#
#     Zwei und nicht 1.2 oder 1.6 wie bei den anderen Leitern, weil eine
#     Dauer anders wahrgenommen wird als eine Groesse: zwei Bewegungen,
#     die sich um zwanzig Prozent unterscheiden, sehen gleich lang aus.
#     Jakob Nielsen, "Response Times: The 3 Important Limits" (1993, nach
#     Miller 1968), nennt 0.1 s als die Grenze, unter der etwas
#     unmittelbar wirkt, und 1.0 s als die, bis zu der der Gedankenfluss
#     nicht abreisst. Zwischen diesen beiden Grenzen ist Platz fuer genau
#     drei Stufen im Verhaeltnis zwei, und die Leiter faellt mit 150 und
#     600 in beide hinein.
#
#     Die 600 ist zugleich die Zahl, die Hyprland fuer den
#     Arbeitsbereichswechsel schon traegt (Geschwindigkeit 6). Die
#     uebrigen drei Hyprland-Zeilen - 7, 7, 10 - ziehen darauf oder auf
#     die 300; vier ad hoc gewaehlte Geschwindigkeiten fuer zwei Sorten
#     Bewegung sind derselbe Katalog wie oben bei der Schrift.
MOTION_ANCHOR_MS = 300
MOTION_RATIO = 2

MOTION_ROLES: tuple[tuple[str, int], ...] = (
    ("INSTANT", -1),
    ("BASE", 0),
    ("ENTER", 1),
)


def motion_ms(step: int) -> int:
    """Eine Dauer der Bewegungsleiter, in Millisekunden."""
    return _rounded(MOTION_ANCHOR_MS * MOTION_RATIO ** step)


# Der Schluessel, mit dem Bewegung ganz abgeschaltet wird.
#
# WARUM ES DEN SCHALTER GIBT
#     Bewegung, die man nicht abstellen kann, ist ein
#     Zugaenglichkeitsproblem und keine Geschmacksfrage: fuer Menschen
#     mit vestibulaerer Stoerung loesen bewegte Flaechen Schwindel und
#     Uebelkeit aus. Beide Seiten dieses Schreibtischs koennen es -
#     GTK ueber `gtk-enable-animations` (GEMESSEN am 12.08.2026 gegen
#     gtk4-broadwayd: die Eigenschaft kommt als False an, wenn die
#     Datei sie auf 0 setzt), Hyprland ueber `animations { enabled }`.
#     Was fehlte, war die eine Stelle, an der man beides sagt.
#
# EIN SCHALTER UND KEIN REGLER JE ROLLE
#     Wer Bewegung abschaltet, will KEINE Bewegung, nicht kuerzere.
#     Drei Dauern auf null zu setzen waere derselbe Katalog wie oben,
#     nur mit Nullen darin.
MOTION_ENABLED = "motion"


def motion_enabled(section: dict) -> bool:
    """Ob dieser Schreibtisch sich bewegen darf.

    Alles ausser einem ausdruecklichen `false` ist ein Ja - dieselbe
    Haltung wie bei scale_of(): eine von Hand editierte Datei mit
    "nein" darin soll die Sitzung nicht in eine unbewegte Oberflaeche
    zwingen, deren Schalter der Nutzer dann suchen muss.
    """
    return section.get(MOTION_ENABLED, True) is not False


def motion_curve_hyprland_toggle(section: dict) -> str:
    """Derselbe Schalter, wie Hyprland ihn liest: yes oder no."""
    return "yes" if motion_enabled(section) else "no"


def motion_gtk_toggle(section: dict) -> str:
    """Und wie GTKs settings.ini ihn liest: 1 oder 0."""
    return "1" if motion_enabled(section) else "0"


def gtk_font_points(section: dict) -> int:
    """Die Grundschrift in PUNKT, fuer GTKs gtk-font-name.

    Die vierte Einheit dieses Systems, und wie beim Terminal keine
    vierte Faehigkeit: `gtk-font-name` nimmt eine Pango-Beschreibung
    ("Roboto 18"), und Pango zaehlt in Punkt. Bei 96 dpi ist
    pt = px * 72 / 96.

    Der Grundwert kommt aus derselben Sprosse, auf der jede gelesene
    Zeile des Schreibtischs steht - BODY -, damit ein fremdes
    GTK4-Fenster neben einem eigenen dieselbe Schrifthoehe hat. Bei der
    ausgelieferten 1.85 sind das 24 px und damit 18 pt, also genau die
    Zahl, auf die auch das Terminal faellt.
    """
    pixels = float(value_of(f"{FONT_PREFIX}BODY", section).removesuffix(PX))
    return max(1, math.floor(pixels * 72 / 96 + 0.5))


def motion_hyprland_speed(role: str, section: dict) -> str:
    """Dieselbe Dauer, wie Hyprland sie liest.

    Hyprland misst Animationsgeschwindigkeit in Zehntelsekunden, als
    ganze Zahl - `animation = windows, 1, 6, zepos` sind 600 ms. Ohne
    diese Umrechnung stuende dort eine zweite Zahlenreihe neben der
    Leiter, und genau so ist der heutige Zustand entstanden: vier
    Geschwindigkeiten im Compositor und eine Dauer im Stylesheet, ohne
    dass eine von der anderen wusste.

    Durch value_of() und nicht durch motion_ms(), damit ein Nutzer, der
    `sizes.values.STYLE_MOTION_ENTER` setzt, damit auch den Compositor
    bewegt. Sonst waere der Regler auf der einen Seite verdrahtet und
    auf der anderen nicht - und das faellt erst auf, wenn ein Fenster
    schneller aufgeht als die Kachel darin hell wird.

    Mindestens 1, weil eine 0 in dieser Spalte fuer Hyprland "sofort"
    heisst und damit die Kurve wegwirft, statt sie schnell zu spielen.
    """
    text = value_of(f"{MOTION_PREFIX}{role}", section)
    try:
        milliseconds = float(text.removesuffix(MS))
    except ValueError:
        # Ein von Hand gesetzter Unsinn darf die Sitzung nicht kosten:
        # eine unparsbare Dauer in dieser Zeile ist ein
        # Konfigurationsfehler in der Datei, ohne die Hyprland nicht
        # startet. Dieselbe Entscheidung wie bei scale_of().
        milliseconds = motion_ms(dict(MOTION_ROLES)[role])
    return str(max(1, math.floor(milliseconds / 100 + 0.5)))


def motion_curve_css() -> str:
    """Die Kurve, wie GTK-CSS sie liest."""
    points = ", ".join(f"{value:g}" for value in MOTION_CURVE_POINTS)
    return f"cubic-bezier({points})"


def motion_curve_hyprland() -> str:
    """Dieselbe Kurve, wie Hyprland sie deklariert."""
    points = ", ".join(f"{value:g}" for value in MOTION_CURVE_POINTS)
    return f"{MOTION_CURVE_NAME}, {points}"


def _rounded(value: float) -> int:
    """Kaufmaennisch gerundet, mindestens 1.

    Nicht round(): das rundet zur GERADEN Zahl, und eine Leiter, die an
    manchen Sprossen ab- und an anderen aufrundet, ist keine Leiter mehr.
    Dieselbe Regel wie in value_of() unten, und derselbe Grund.
    """
    return max(1, math.floor(value + 0.5))


def font_px(step: int) -> int:
    """Die Schriftgroesse einer Sprosse, in Full-HD-Pixeln."""
    return _rounded(BASE_PX * FONT_RATIO ** step)


def icon_px(step: int) -> int:
    """Die Symbolgroesse derselben Sprosse: ihre Zeilenhoehe.

    Aus dem UNGERUNDETEN Grundwert gerechnet und nicht aus font_px().
    Sonst wuerde zweimal gerundet, und aus der Sprosse 2 (18.72 -> 19)
    kaeme 19 * 1.2 = 22.8 -> 23 statt der 22.46 -> 22, die die Leiter an
    dieser Stelle wirklich traegt. Ein Pixel, den niemand bestellt hat.
    """
    return _rounded(BASE_PX * FONT_RATIO ** step * LINE_HEIGHT)


def radius_px(step: int) -> int:
    """Die Eckenrundung einer Sprosse, in Full-HD-Pixeln."""
    return _rounded(RADIUS_ANCHOR * RADIUS_RATIO ** step)


# JEDER EINTRAG HIER MUSS VON MINDESTENS EINER VORLAGE BENUTZT WERDEN.
#
# Das ist keine Stilfrage, sondern die Lehre aus MONITOR_HEIGHT_SCALES:
# eine Einstellung mit Vorgabewerten, Migration und Befehlszeile, die
# kein einziges erzeugtes Byte veraenderte und deshalb geloescht wurde.
# Ein Regler, der nichts bewegt, ist schlimmer als keiner - er kostet
# den Nutzer die Zeit, herauszufinden, dass er nichts tut.
#
# tests/src/test_sizes.py haelt diese Tabelle gegen die Vorlagen und
# faellt um, sobald hier ein Name steht, den keine Vorlage nennt. Eine
# neue Groesse heisst also: Platzhalter in eine Vorlage schreiben, sonst
# geht die Suite nicht mehr durch.
TABLE: dict[str, Size] = {
    # Die Schrift im Terminal, IN PUNKT.
    #
    # DIE VIERTE EINHEIT, UND WARUM SIE KEINE VIERTE FAEHIGKEIT IST
    #     Oben stehen drei Groessensysteme - Pixel im Startmenue, rem im
    #     Assistenten, Pixel hier - und jedes hat einen Grund, aus dem es
    #     nicht das der anderen sein kann. Punkt ist keiner davon,
    #     sondern eine Umrechnung: kitty nimmt seine Schriftgroesse nur
    #     in Punkt entgegen (`font_size`), und bei 96 dpi sind das
    #     px = pt * 96 / 72.
    #
    #     Der Grundwert steht deshalb so da, dass die Umrechnung an
    #     BEIDEN Enden auf die Zahlen des uebrigen Systems faellt:
    #       Faktor 1.00  ->  10 pt  =  13.3 px, die Grundschrift BASE_PX
    #       Faktor 1.85  ->  18 pt  =  24.0 px, der Anker ANCHOR_PX
    #     Das ist nicht gerundet hingebogen, sondern faellt aus 10 * 24/13
    #     heraus.
    #
    # GEMESSEN am 11.08.2026, nachdem der Nutzer "die font size im
    # terminal ist zu beginn zu klein" gemeldet hatte: in
    # kitty-config.template stand `font_size 7.0` als Literal - 9.3 px,
    # also nicht einmal die alte Grundschrift von 13 px und gut ein
    # Drittel der 24 px, die derselbe Schreibtisch seit b96f90d
    # ueberall sonst zeigt. Der Regler bewegte 29 Werte und den einen
    # nicht, den man den ganzen Tag ansieht.
    #
    # Ohne Einheit: kitty liest eine nackte Zahl und scheitert an "18px".
    "STYLE_TERMINAL_FONT_SIZE": Size(10, BARE, SCALED),

    # Die DICKE der Leiste, also ihr Mass quer zu ihrer Laufrichtung. Sie
    # MUSS der Schrift folgen: 50 px trugen 13 px Text, und 24 px Text in
    # einer 50 px dicken Leiste werden an beiden Raendern beschnitten.
    #
    # WARUM "THICKNESS" UND NICHT "HEIGHT"
    #     Die Leiste lag vom 11. bis zum 12.08.2026 links und liegt
    #     seither wieder oben. Der Name hat beide Drehungen unveraendert
    #     ueberstanden, und genau das ist sein Zweck: "Dicke" ist das
    #     Mass quer zur Laufrichtung, ganz gleich, an welcher Kante die
    #     Leiste klebt. Ein `BAR_HEIGHT` haette nach der ersten Drehung
    #     die falsche Achse genannt und nach der zweiten wieder die
    #     richtige - ein Name, der davon abhaengt, welchen Tag man hat,
    #     ist keiner.
    #
    # WARUM 39, UND WORAUS DIE ZAHL KOMMT
    #     BESTELLT am 13.08.2026, woertlich: "header und footer auf 60
    #     setzen". Das ist eine Zahl fuer die AUSLIEFERUNG und nicht fuer
    #     diese Zeile - hier steht der Grundwert, den der Faktor
    #     multipliziert. 39 * SCALE_DEFAULT = 39 * 20/13 = 60, und zwar
    #     ohne Rundung: 39 ist 3 * BASE_PX.
    #
    #     DAMIT IST DIE DICKE DAS DREIFACHE DER GRUNDSCHRIFT, bei JEDEM
    #     Faktor - 60 zu 20 wie 39 zu 13 -, und das ist der Grund, aus dem
    #     die 60 hier als 3 * BASE_PX und nicht als 39 steht. Wer an
    #     BASE_PX oder an DEFAULT_PX dreht, bekommt eine Leiste, die
    #     dieselben Verhaeltnisse haelt, statt eine, in der eine
    #     handgetippte 39 stehengeblieben ist.
    #
    #     WAS DAVOR DASTAND: 54, also 83 bei Vorgabegroesse. GEMESSEN am
    #     13.08.2026 an Bildpunkten im verschachtelten Compositor
    #     (tests/render/): die Platte bemalte 83 px, und der hoechste
    #     Inhalt darin - ein Modulkasten mit seinem Zeigergrund - war
    #     54 px hoch. Ein knappes Drittel der Leiste war leer. Der Nutzer
    #     hat dazu am selben Tag zweimal dasselbe gesagt ("die groesse von
    #     header und footer ... etwas kleiner", "auf 60 setzen").
    #
    #     WAS DIE 60 TRAGEN MUSS, und das ist die Rechnung, die sie
    #     zulaessig macht: der Innenraum ist die Dicke minus dem
    #     Aussenrand der Module (STYLE_MARGIN_VERTICAL, 3 px oben und
    #     unten), also 54 px fuer eine Zeile aus 20 px Schrift. Die
    #     Zeilenhoehe eines Nerd-Font-Zeichens auf dieser Sprosse ist
    #     LINE_HEIGHT * 20 = 24 px. Es bleiben 30 px Luft; der Innenraum
    #     ist mehr als das Doppelte dessen, was darin steht.
    #
    # WAS DIE UNTERGRENZE DARAUS MACHT, UND WARUM SIE JETZT GREIFT
    #     bar_thickness_px() haelt zusaetzlich fest, dass das Docksymbol
    #     nicht unter MINIMUM_DOCK_ICON faellt. GERECHNET am 13.08.2026
    #     ueber die Faktoren, die user_settings zulaesst:
    #
    #         Faktor   39*f   Beiwerk   Untergrenze   Dicke   Docksymbol
    #          1.00      39      23         47         47        24
    #          1.20      47      23         47         47        24
    #          1.3846    54      25         49         54        29
    #          1.5385    60      25         49         60        35
    #          1.846     72      27         51         72        45
    #          2.50      98      29         53         98        69
    #
    #     Unterhalb von Faktor 1.2 bindet also die Untergrenze und nicht
    #     mehr die Schrift - mit dem alten Grundwert 54 tat sie das nie.
    #     Das ist kein Nebeneffekt, sondern genau ihr Zweck: eine Leiste,
    #     die dem Regler bis unter die kleinste gezeichnete Symbolgroesse
    #     folgt, waere eine Leiste mit einem heruntergerechneten Fuss.
    #
    #     Nachgemessen wird beides an einer echten Anzeige und nicht hier:
    #     test_no_module_is_taller_than_the_bar_it_hangs_in in
    #     tests/src/test_bar_headless.py fuer den Inhalt, und
    #     tests/render/test_geometry.py an Bildpunkten fuer die bemalte
    #     Hoehe - dort ueber mehrere Schirme und mehrere Faktoren.
    #
    # WARUM "THICKNESS" UND NICHT "HEIGHT" - siehe oben.
    #
    # Ohne Einheit, weil ags-bar.template daraus eine TypeScript-Konstante
    # macht. Der Wert stand in style_definition.py als "50px" und wurde
    # von keiner Vorlage gelesen, waehrend die Leistendicke als nackte 50
    # in der Vorlage stand: zwei Zahlen fuer ein Mass, von denen die
    # eine nichts tat.
    "STYLE_BAR_THICKNESS": Size(3 * BASE_PX, BARE, SCALED),

    # Die abgesetzte Kante unten an der Leiste und an jedem ihrer Module -
    # der 3D-Effekt, der summer-day-and-night sein Aussehen gibt.
    #
    # NACHGEBAUT UND NICHT UEBERNOMMEN. Das Vorbild hat KEINE LIZENZ, also
    # ist von dort nur die Messung genommen, keine Zeile: sie setzt
    # `border-bottom: 5px solid <dunklere Fassung der eigenen Farbe>` bei
    # 16 px Schrift. Auf unsere Grundschrift von 13 px umgerechnet sind
    # das 5 * 13/16 = 4.06 px, also auf zwei Hundertstel genau die
    # Sprosse 4 der Abstandsleiter.
    #
    # SCALED, obwohl es ein Rahmen ist und Rahmen hier sonst duenn
    # bleiben: das hier ist kein Haarstrich, der eine Flaeche begrenzt,
    # sondern die sichtbare DICKE einer Kachel, die Text traegt. Bliebe
    # sie stehen, saesse bei doppelter Schrift dieselbe 4-px-Kante unter
    # einer doppelt so hohen Kachel und der Koerper verloere seine Tiefe.
    #
    # OHNE EINHEIT, obwohl der Hauptleser ein Stylesheet ist: die Kante
    # steht auch in hyprland-universal-config.template, als
    # `decoration:shadow:offset`, damit die FENSTER dieselbe Tiefe
    # bekommen wie die Kacheln. Hyprland liest dort eine nackte Zahl und
    # scheitert an "7px" - und zwar mit einem Konfigurationsfehler in
    # der Datei, deren Scheitern den Nutzer die Sitzung kostet.
    # bar-style.template haengt sich das px selbst an, so wie es das bei
    # STYLE_DOCK_PADDING schon tut.
    "STYLE_BAR_SHELF": Size(4, BARE, SCALED),

    # Die Eckenrundung der FENSTER, fuer Hyprlands decoration:rounding.
    #
    # Der Grundwert kommt aus radius_px(), also aus der Rundungsleiter
    # oben, und ist nicht mehr abgeschrieben.
    #
    # SPROSSE PANEL SEIT DEM 17.08.2026, UND VORHER CARD
    #     GEMELDET, woertlich: "ausserdem sind nicht alle modale ags
    #     fenster so rund wie unser style auch die fenster die erscheinen
    #     wie terminal mit dem hyprland header sind nicht so rund wie
    #     unsere waybar das muss alles angepasst werden".
    #
    #     GEMESSEN am selben Tag, bei ausgeliefertem Regler:
    #
    #         Leiste (#bar) und Dock (#dock)      PANEL   20 px
    #         jedes Aufklappfenster               PANEL   20 px
    #             (.overlay-outer, alle zwoelf)
    #         Einblendung (.notif-card)           PANEL   20 px
    #         Startmenue (#outer-box)             PANEL   20 px
    #         Starter (.launcher-container)       PANEL   20 px
    #         FENSTER (decoration:rounding)       CARD    12 px
    #
    #     Sechs Flaechen auf einer Sprosse und eine daneben. Der Nutzer
    #     sieht genau diese eine.
    #
    #     DIE ROLLE, UND SIE IST JETZT ENTSCHIEDEN: die Leiter sortiert
    #     nach dem, WAS eine Flaeche ist, und nicht danach, wer sie malt.
    #
    #         PANEL    eine Flaeche, die FUER SICH auf dem Schreibtisch
    #                  steht - Leiste, Dock, Aufklappfenster,
    #                  Einblendung, Startmenue. Ein Terminalfenster ist
    #                  genau das.
    #         CARD     etwas, das AUF so einer Flaeche liegt: eine
    #                  Leistenkachel, eine Listenzeile, ein
    #                  Vorschaubild, ein Kurzhinweis.
    #         CONTROL  etwas, das man bedient: Knopf, Eingabe, Reiter.
    #
    #     Hier stand "ein Fenster ist eine Kachel im Grossen". Das ist
    #     die Beschreibung einer GROESSE, und Groesse ist genau das, was
    #     die Leiter unterscheidet - "im Grossen" heisst eine Sprosse
    #     hoeher.
    #
    #     WAS DIESE EINE ZAHL MITZIEHT, und beides ist gemessen:
    #
    #       hyprbars   Die Titelleiste hat KEINE eigene Rundung. Ihre
    #                  Optionen sind bar_height, bar_color, col.text,
    #                  bar_text_size/-weight/-font/-align, bar_padding,
    #                  bar_button_padding, bar_blur, bar_part_of_window,
    #                  bar_precedence_over_border, bar_buttons_alignment,
    #                  icon_on_hover, on_double_click - nachgezaehlt am
    #                  17.08.2026 an den addConfigValueV2-Zeilen in
    #                  hyprbars/main.cpp der ausgelieferten Quelle. Kein
    #                  "rounding".
    #                  barDeco.cpp Zeile 489 nimmt stattdessen
    #                  `PWINDOW->rounding() + getRealBorderSize()` und
    #                  rundet damit die beiden OBEREN Ecken. Die
    #                  Titelleiste folgt dieser Zahl also von selbst -
    #                  ein Befund, der die Aenderung erst vollstaendig
    #                  macht.
    #       mako       liest denselben Platzhalter fuer seine
    #                  Einblendungen und kommt damit auf dieselbe
    #                  Sprosse wie .notif-card, das dasselbe zeigt.
    #
    #                  UND DAS SIEHT AUF EINER ZEPOS-INSTALLATION
    #                  NIEMAND, was hier steht, weil es sonst als
    #                  Wirkung gelesen wuerde: GEMESSEN am 17.08.2026
    #                  nennt KEIN Rezept dieses Baums mako, und
    #                  src/generate_config.sh maskiert mako.service
    #                  ausdruecklich ("AGS handles notifications").
    #                  mako-config.template schreibt eine Datei fuer
    #                  einen Dienst, den dieses System abschaltet - ein
    #                  Befund fuer sich, und keiner, den eine
    #                  Groessentabelle behebt.
    #
    # Ein eigener Eintrag und nicht {{STYLE_RADIUS_CARD}}, obwohl die
    # Zahl dieselbe ist: die Sprossen tragen "px", und Hyprland nimmt
    # hier nur eine nackte Zahl - `rounding = 8px` ist ein
    # Konfigurationsfehler in der Datei, deren Scheitern den Nutzer die
    # Sitzung kostet. Es ist derselbe Riss zwischen Leser und Wert, den
    # PX/BARE oben schon beschreibt.
    #
    # Vorher stand hier eine 8 als Literal, mit dem Kommentar, sie sei
    # "Sprosse 8" der ABSTANDSleiter - also eine Ecke, die sich als
    # Abstand ausgab, weil es fuer Ecken nichts gab.
    "STYLE_WINDOW_ROUNDING": Size(radius_px(1), BARE, SCALED),

    # Der Abstand der Fenster zum Rand und zueinander, fuer Hyprlands
    # general:gaps_in und general:gaps_out.
    #
    # GEMELDET am 11.08.2026: "die fenster auch den selben abstand zum
    # rand nutzen". "Denselben" heisst: dieselbe Zahl wie die
    # Seitenleiste, und zwar auch dann noch, wenn jemand am Regler dreht.
    # Deshalb stehen sie HIER und nicht als 5 und 20 in
    # hyprland-universal-config.template - dort waren sie zwei Literale,
    # die von keinem Regler bewegt wurden, waehrend die Leiste daneben
    # mitwuchs.
    #
    # WARUM 8 UND 16 UND NICHT DIE 5 UND 20 VON VORHER
    #     Hyprland legt gaps_in an JEDE Seite eines Fensters, gaps_out nur
    #     nach aussen. Zwischen zwei Fenstern sieht man also 2*gaps_in,
    #     zum Schirmrand gaps_out. "Ueberall derselbe Abstand" ist damit
    #     genau die Gleichung 2*gaps_in == gaps_out - und die alten 5 und
    #     20 erfuellten sie nicht: 10 innen gegen 20 aussen.
    #
    #     Die Vorlage erfuellt sie: gaps_in 10, gaps_out 20 bei 16 px
    #     Schrift. Auf unsere 13 px umgerechnet sind das 8.13 und 16.25 -
    #     die Sprossen 8 und 16, auf ein Viertel Pixel genau. Die
    #     Abstandsleiter bietet fuer diese Gleichung nur drei Paare an
    #     (4/8, 8/16, 12/24), und die Messung trifft eines davon, statt
    #     dass eines gewaehlt werden musste.
    #
    # Ohne Einheit: Hyprland liest eine nackte Zahl und scheitert an
    # "16px" - mit einem Konfigurationsfehler in der Datei, deren
    # Scheitern den Nutzer die Sitzung kostet.
    # STYLE_GAPS_OUT ist ABGELEITET - siehe gaps_out_px() unten. Der
    # Grundwert bleibt hier stehen, damit die Tabelle vollstaendig ist
    # und ein Einzelwert ihn weiter schlagen kann.
    "STYLE_GAPS_IN": Size(8, BARE, SCALED),
    "STYLE_GAPS_OUT": Size(16, BARE, SCALED),

    # Die Abstaende in der Leiste. Sie umschliessen Text und muessen mit
    # ihm wachsen, sonst stossen die Beschriftungen bei grosser Schrift
    # aneinander.
    #
    # STYLE_CHIP_GAP hiess bis zum 12.08.2026 STYLE_MARGIN_TOP. Der Name
    # nannte eine HIMMELSRICHTUNG, und die galt nur, solange die Leiste
    # senkrecht lief: dort war der Abstand zwischen zwei Kacheln der
    # nach oben. Waagerecht ist derselbe Abstand ein margin-left, und
    # ein Name, der bei jeder Drehung falsch wird, ist genau der Riss
    # zwischen Namen und Sache, den der Kopf dieser Tabelle verbietet.
    # Der neue nennt die Sache: der Abstand zwischen zwei Kacheln.
    # src/user_settings.py zieht eine vorhandene Einstellung mit
    # RENAMED_SIZE_VALUES auf den neuen Namen.
    "STYLE_MODULE_SPACING": Size(10, PX, SCALED),
    # STYLE_BAR_EDGE_SPACING stand hier, mit dem Grundwert 20 - also 31
    # px bei der ausgelieferten Groesse, links vor dem ersten und rechts
    # hinter dem letzten Modul, ZUSAETZLICH zu dem Rand, den die Platte
    # selbst schon haelt.
    #
    # GEMELDET am 12.08.2026: "der header mit den icon kann rechts und
    # links mehr platz benutzen damit es mit dem terminal gleich
    # aufliegt".
    #
    # GEMESSEN am selben Tag, und die Zahl erklaert die Beschwerde
    # genau: die Platte haelt STYLE_GAPS_OUT zum Schirmrand, also
    # dieselben 25 px, die auch ein Fenster haelt - waagerecht lagen
    # Leiste und Terminal also schon gleich auf. Was NICHT gleich auflag,
    # waren die Symbole: sie standen 25 + 31 = 56 px vom Rand, ein
    # Fensterinhalt bei 25. Der Nutzer hat nicht die Platte verglichen,
    # sondern das, was er sieht.
    #
    # Die Zeile ist deshalb geloescht und nicht auf 0 gesetzt: eine
    # Groesse mit dem Wert 0 ist ein Regler, an dem man drehen kann und
    # der etwas kaputtmacht. Der Abstand zum Schirmrand hat einen Namen,
    # und es ist STYLE_GAPS_OUT - dieselbe Zahl fuer die Fenster, die
    # Platte, den Fuss. Die Module bekommen ihren Innenabstand von
    # STYLE_PADDING_BUTTON, also von der Kachel, in der sie sitzen.
    #
    # Nebenbei ist es die billigste Breite, die auf dieser Leiste zu
    # holen war: 62 px, ohne dass ein Modul verschwindet.
    "STYLE_CHIP_GAP": Size(10, PX, SCALED),
    "STYLE_PADDING_BUTTON": Size(5, PX, SCALED),

    # Die Fenstertitelleiste von hyprbars. Nackte Zahlen, weil Hyprland
    # sie so liest.
    "STYLE_HYPRBARS_HEIGHT": Size(25, BARE, SCALED),
    "STYLE_HYPRBARS_TEXT_SIZE": Size(10, BARE, SCALED),
    # Die drei Punkte rechts in der Titelleiste. Ein Bild - aber eines,
    # das in einer Leiste sitzt, deren Hoehe hier mitwaechst. Bliebe es
    # stehen, saessen drei kleine Punkte in einer doppelt so hohen
    # Leiste.
    "STYLE_HYPRBARS_BUTTON_SIZE": Size(18, BARE, SCALED),

    # Bilder, nicht Schrift: das Dock zeichnet Anwendungssymbole und die
    # Statusablage die Symbole fremder Programme. Sie stehen hier, damit
    # sie EINZELN einstellbar sind, und sie folgen dem Faktor nicht -
    # siehe SCALED/FIXED oben.
    #
    # Alle vier ohne Einheit: ags-dock.template und ags-bar.template
    # machen daraus `pixel_size`, eine Zahl fuer Gtk.Image, und
    # bar-style.template haengt das px selbst an, wo es eines braucht.
    "STYLE_TRAY_ICON_SIZE": Size(18, BARE, FIXED),
    # STYLE_DOCK_ICON_SIZE stand hier mit 48 und FIXED. Es ist seit dem
    # 12.08.2026 ABGELEITET - siehe dock_icon_px() weiter unten - und
    # steht deshalb in DERIVED statt hier. Der Grundwert bleibt in der
    # Tabelle, damit `list-sizes` es weiter kennt und ein Nutzer es
    # weiter einzeln setzen kann.
    "STYLE_DOCK_ICON_SIZE": Size(48, BARE, FIXED),
    "STYLE_DOCK_PADDING": Size(4, BARE, FIXED),
    # STYLE_DOCK_MARGIN_BOTTOM stand hier, Size(10, BARE, FIXED).
    #
    # GEMELDET am 12.08.2026: "der abstand des header zum rand kann
    # genauso lang sein wie der nwg dock zum footer abstand hat ja".
    #
    # Es waren zwei Zahlen aus zwei Quellen fuer denselben sichtbaren
    # Abstand, und sie liefen beim Drehen auseinander: die Leiste haelt
    # STYLE_GAPS_OUT (SCALED, 16 -> 25 bei Vorgabegroesse), der Fuss
    # hielt eine feste 10. Bei Faktor 1 waeren es 16 gegen 10 gewesen,
    # bei 2.5 vierzig gegen zehn.
    #
    # Zwei Zahlen, die gleich sein SOLLEN, sind eine Zahl. Uebrig bleibt
    # STYLE_GAPS_OUT, und zwar nicht, weil es die groessere ist: es ist
    # der Abstand, den auch die FENSTER zum Rand halten, und der Nutzer
    # hat am 11.08.2026 ausdruecklich verlangt, dass sie "den selben
    # abstand zum rand nutzen". Damit ist es die eine Zahl fuer alles,
    # was einen Rand zum Schirm haelt, und ein FIXED daneben war
    # ausserdem die falsche Sorte: ein Abstand, der Text umschliesst,
    # folgt dem Faktor.

    # Der Anwendungsstarter auf SUPER+SPACE (plugins/hyprlaunch).
    #
    # WARUM DIESE FUENF UND NICHT DIE ZWANZIG, DIE IM STYLESHEET STEHEN
    #     Weil nur diese fuenf darueber entscheiden, ob das Fenster auf
    #     den Schirm passt. Alles andere - Randstaerken, die
    #     Mindestbreite eines Symbolkastens - ist eine Zahl im
    #     Stylesheet, und tests/src/test_spacing.py schreibt
    #     ausdruecklich auf, dass min-width und border-radius nicht auf
    #     die Abstandsleiter gehoeren ("das eine ist eine Breite und das
    #     andere eine Ecke"). Ein Regler pro Zahl waere derselbe Fehler
    #     wie die vierundachtzig Platzhalter, die vor dieser Datei
    #     standen und die keine Vorlage las.
    #
    # WARUM DIE DREI HOEHEN EINZELN UND NICHT ALS EINE
    #     Weil sie eine Rechnung sind, die auch das Programm anstellt:
    #     Fensterhoehe = Suchzeile + Zeilen * Zeilenhoehe + Rahmen. Die
    #     Zahlen stehen in plugins/hyprlaunch/include/hyprlaunch/
    #     Config.hpp, sie kamen von upstream, und sie standen dort als
    #     `static constexpr` - also im uebersetzten Objekt, wo dieser
    #     Regler sie nie erreichen konnte.
    #
    # ROW_MIN_HEIGHT UND ROW_HEIGHT SIND NICHT DASSELBE, UND BEIDE MUESSEN
    #     32 ist die Mindesthoehe, die das Stylesheet einer Zeile gibt;
    #     45 ist die Hoehe, mit der das Programm rechnet, wenn es das
    #     Fenster aufzieht. Upstream schreibt die Beziehung selbst hin:
    #     "32 min-height + 5+5 padding + 2 border + 1 margin". Folgte
    #     nur eine der beiden dem Faktor, waere die Rechnung ab dem
    #     ersten Drehen falsch - entweder klaffte unten Leerraum oder
    #     die letzte Zeile waere abgeschnitten.
    "STYLE_LAUNCHER_WIDTH": Size(530, BARE, SCALED),
    "STYLE_LAUNCHER_SEARCH_HEIGHT": Size(52, BARE, SCALED),
    "STYLE_LAUNCHER_ROW_HEIGHT": Size(45, BARE, SCALED),
    "STYLE_LAUNCHER_ROW_MIN_HEIGHT": Size(32, PX, SCALED),
    # Ein Bild, also FIXED - dieselbe Grenze wie beim Dock. Es ist das
    # Anwendungssymbol aus dem Symbolthema, das ein fremdes Paket
    # liefert, und mit dem Faktor 1.85 waere es 67 Pixel hoch in einer
    # Zeile von 83.
    "STYLE_LAUNCHER_ICON_SIZE": Size(36, BARE, FIXED),

    # Der Zwischenablage-Verlauf auf SUPER+SHIFT+V (plugins/hyprclipx).
    #
    # Nur zwei, weil das Fenster keine feste Zeilenzahl aufzieht: es
    # oeffnet in dieser Groesse und scrollt. Die Zeilenhoehe wird dort
    # gemessen statt angenommen - siehe den Kopf von
    # plugins/hyprclipx/include/hyprclipx/ClipboardRenderer.hpp, wo die
    # angenommene 28 deshalb geloescht ist.
    "STYLE_CLIPBOARD_WIDTH": Size(600, BARE, SCALED),
    "STYLE_CLIPBOARD_HEIGHT": Size(220, BARE, SCALED),

    # Die Schriftleiter, siehe oben. Sieben Rollen, jede zweimal: einmal
    # als Schrift und einmal als die Hoehe der Zeile, in der ein Symbol
    # steht.
    **{f"{FONT_PREFIX}{role}": Size(font_px(step), PX, SCALED)
       for role, step in FONT_ROLES},
    **{f"{ICON_PREFIX}{role}": Size(icon_px(step), PX, SCALED)
       for role, step in FONT_ROLES},

    # Die Rundungsleiter, siehe oben. SCALED, weil eine Ecke, die
    # stehenbleibt, waehrend ihr Kasten waechst, eine andere Form ist.
    **{f"{RADIUS_PREFIX}{role}": Size(radius_px(step), PX, SCALED)
       for role, step in RADIUS_ROLES},

    # Die Abstandsleiter, siehe oben. SCALED aus demselben Grund wie
    # STYLE_MODULE_SPACING: sie umschliesst Text.
    **{f"{SPACE_PREFIX}{step}": Size(step, PX, SCALED)
       for step in SPACE_LADDER},

    # Die Bewegungsleiter, siehe oben.
    #
    # FIXED, und das ist die dritte Sorte Grenze in dieser Datei: eine
    # Dauer ist kein Mass auf dem Schirm. Wer die Schrift verdoppelt,
    # will groesser lesen und nicht laenger warten - eine mit dem Faktor
    # multiplizierte Bewegung waere bei 1.85 mehr als eine Sekunde lang
    # und damit ueber der Grenze, ab der der Gedankenfluss abreisst.
    **{f"{MOTION_PREFIX}{role}": Size(motion_ms(step), MS, FIXED)
       for role, step in MOTION_ROLES},

    # Die Grenzen, siehe oben. FIXED und ohne Einheit: es sind Anzahlen
    # von Zeichen, keine Laengen, und sie folgen dem Regler dadurch, dass
    # das Zeichen mitwaechst und nicht die Zahl.
    f"{MEASURE_PREFIX}LINE": Size(MEASURE_LINE, BARE, FIXED),
    f"{MEASURE_PREFIX}PROSE": Size(MEASURE_PROSE, BARE, FIXED),
}


# =====================================================================
# DER STREIFEN - eine Dicke fuer Kopf UND Fuss
# =====================================================================
#
# GEMELDET am 12.08.2026: "der header soll immer genauso gross sein wie
# unser nwg dock".
#
# WAS VORHER DASTAND, UND WARUM ES ZWEI ZAHLEN WAREN
#     STYLE_BAR_THICKNESS = Size(54, BARE, SCALED) auf der einen Seite,
#     und auf der anderen die NATUERLICHE Hoehe des Fusses - die stand
#     nirgends, sondern ergab sich aus Symbolgroesse, Innenabstand,
#     Knopfrand und Rahmen. GEMESSEN am 12.08.2026, kopflos unter
#     gtk4-broadwayd, ueber acht Faktoren:
#
#         Faktor   Leiste (54*f)   Fuss    gleich?
#          1.00        54           72       nein, 18 zu wenig
#          1.20        65           72       nein
#          1.30        70           74       nein
#          1.5385      83           74       nein, 9 zu viel
#          1.846      100           76       nein, 24 zu viel
#          2.50       135           78       nein, 57 zu viel
#
#     Sie waren an KEINEM Faktor gleich, und sie kreuzten sich unterwegs
#     - unter 1.4 war die Leiste duenner als der Fuss, darueber dicker.
#     Zwei Zahlen fuer ein Mass, und beide bewegten sich anders.
#
# DIE EINE ZAHL IST DIE LEISTE, UND DER FUSS FOLGT IHR
#     Herum und nicht andersherum, weil nur eine der beiden Seiten einen
#     ZWANG hat: die Leiste traegt Text, und Text, der nicht hineinpasst,
#     wird beschnitten. Der Fuss traegt Bilder, und ein Bild kann jede
#     Groesse haben. Die Seite mit dem Zwang bestimmt, die andere folgt.
#
#     Der Fuss folgt ueber seine SYMBOLGROESSE und nicht ueber ein
#     min-height: ein Kasten, der hoeher ist als sein Inhalt, ist eine
#     Reihe kleiner Symbole mit Luft darum, und genau so sah das Dock
#     bei Vorgabegroesse aus - 48 px Symbole in einem 100 px hohen
#     Streifen. Jetzt fuellt das Symbol den Streifen aus, den es kostet.
#
# WAS DAMIT AUFGEGEBEN WIRD, UND DAS IST EINE ENTSCHEIDUNG
#     Bis heute stand ueber SCALED/FIXED: "Nicht skaliert wird, was ein
#     BILD ist - die Symbole im Dock sind Anwendungsgrafik aus fremden
#     Prozessen". Das war richtig, solange der Fuss seine eigene Hoehe
#     haben durfte. Er darf es nicht mehr; der Nutzer hat verlangt, dass
#     beide Streifen gleich hoch sind, und zwei gleich hohe Streifen, von
#     denen einer dem Regler folgt, gibt es nicht.
#
#     Einzeln einstellbar bleibt es: sizes.values.STYLE_DOCK_ICON_SIZE
#     schlaegt die Ableitung, wie jeder andere Einzelwert auch. Wer das
#     tut, hat dann allerdings wieder zwei verschieden hohe Streifen -
#     und das ist dann seine Entscheidung und nicht die dieser Datei.

# Was der Fuss ausser dem Symbol noch braucht, in Vielfachen der Werte
# darueber, plus einer gemessenen Konstanten.
#
# GEMESSEN am 12.08.2026 gegen die echte Hoehe unter gtk4-broadwayd, bei
# den Faktoren 1.0, 1.2, 1.3, 1.385, 1.4615, 1.5, 1.846 und 2.5. Sie
# steht als Zahl da, weil sie in bar-style.template als `1px solid`
# steht und nicht als Sprosse.
#
# ES WAREN 4, UND DIE VIERTE GIBT ES NICHT MEHR
#     Gezaehlt wurden urspruenglich zwei Rahmen - einer um den Kasten
#     und einer um den KNOPF -, je oben und unten. Den Knopfrahmen hat
#     es gegeben, solange jedes Docksymbol auf einer eigenen Kachel sass.
#     Am 12.08.2026 ist die Kachel gefallen, auf Ansage des Nutzers:
#     "die icon sollen im header nicht nochmal ein element haben". Damit
#     verschwand der Rahmen, die 4 blieb stehen.
#
#     Was der Fuss heute wirklich hat: der Rahmen des Kastens, oben und
#     unten (2), und der Zustandsstrich, der nur UNTEN liegt (1).
#
#     Aufgefallen ist die ueberzaehlige Vierte nicht der kopflosen
#     Messung - die misst das Widget und kam auf 83 -, sondern dem
#     Bildschirmabzug des verschachtelten Compositors: die Layer-Flaeche
#     des Fusses war 82 hoch, der Kopf bemalte 83. Ein Pixel, und
#     trotzdem der Unterschied zwischen einer Ableitung, die stimmt, und
#     einer, die ungefaehr stimmt. Gehalten wird das jetzt von
#     tests/render/test_geometry.py, das beide Streifen an Bildpunkten
#     misst statt an der Tabelle.
DOCK_BORDERS = 3


def dock_chrome(section: dict) -> int:
    """Alles am Fuss, was nicht das Symbol ist.

    Innenabstand des Kastens und des Knopfes (je zweimal, oben und
    unten), der Aussenrand des Knopfes und die Rahmen.
    """
    padding = int(value_of("STYLE_DOCK_PADDING", section))
    gap = int(value_of(f"{SPACE_PREFIX}2", section).removesuffix(PX))
    return 4 * padding + 2 * gap + DOCK_BORDERS


def bar_thickness_px(section: dict) -> int:
    """Wie dick der Streifen ist - fuer Kopf UND Fuss.

    Der Grundwert ist 3 * BASE_PX und damit bei Vorgabegroesse die 60,
    die der Nutzer am 13.08.2026 bestellt hat (siehe
    STYLE_BAR_THICKNESS oben); die Untergrenze ist, was der Fuss
    mindestens braucht, damit sein Symbol nicht auf null schrumpft.

    BIS ZUM 13.08.2026 STAND HIER "der Grundwert 54" UND "unterhalb von
    Faktor 1.4", und beide Zahlen waren nach der Umstellung falsch.
    GERECHNET am selben Tag ueber value_of(): 39 * f schlaegt die
    Untergrenze von 47 px erst ab f = 1.2052, also bindet unterhalb von
    Faktor 1.21 die Untergrenze und darueber die Schrift. Die ganze
    Tabelle steht bei STYLE_BAR_THICKNESS.
    """
    size = TABLE["STYLE_BAR_THICKNESS"]
    text = max(1, math.floor(size.base * scale_of(section) + 0.5))
    return max(text, MINIMUM_DOCK_ICON + dock_chrome(section))


# Wie klein ein Dock-Symbol werden darf. 24 px ist die kleinste Groesse,
# die jedes Symbolthema als eigene Zeichnung fuehrt; darunter skaliert
# GTK eine groessere herunter, und das sieht man.
MINIMUM_DOCK_ICON = 24


def dock_icon_px(section: dict) -> int:
    """Wie gross ein Dock-Symbol ist: der Streifen minus sein Beiwerk.

    Ueber value_of() und nicht ueber bar_thickness_px(): wer die Dicke
    von Hand nennt, stellt damit BEIDE Streifen, und ein direkter Aufruf
    der Rechnung ginge an seiner Zahl vorbei. Das ist genau der
    Unterschied zwischen "abgeleitet" und "gleich gross gemacht".

    STYLE_BAR_THICKNESS IST DIE BEMALTE HOEHE, NICHT DER STREIFEN
        Bis zum 12.08.2026 lasen Kopf und Fuss diese Zahl verschieden,
        und deshalb waren sie verschieden dick, obwohl beide aus
        derselben Zahl kamen:

            Fuss   BEMALTE Hoehe. Der Rand kam obendrauf:
                   83 bemalt + 24 Rand = 107 reserviert.
            Kopf   RESERVIERTER Streifen. Der Rand lag darin:
                   24 Rand + 59 bemalt = 83.

        Gemessen an einem Bildschirmabzug des verschachtelten
        Compositors (tests/render/): Kopf bemalt 59, Fuss bemalt 83 -
        die Differenz war exakt ein STYLE_GAPS_OUT, kein Zufall,
        sondern die zwei Lesarten.

        Aufgeloest wurde es auf der Seite des KOPFES, auf Ansage des
        Nutzers: die Leiste zieht ihre Flaeche jetzt auf
        BAR_THICKNESS + EDGE_GAP auf und bemalt davon BAR_THICKNESS
        (ags-bar.template, set_default_size). Damit gilt fuer beide
        Streifen dasselbe: die Zahl ist, was man SIEHT, und der Rand
        kommt obendrauf. Diese Funktion bleibt deshalb, wie sie war.
    """
    return max(MINIMUM_DOCK_ICON,
               int(value_of("STYLE_BAR_THICKNESS", section))
               - dock_chrome(section))


# Die Groessen, deren Wert sich aus anderen ergibt. Sie stehen trotzdem
# in TABLE, damit `list-sizes` sie kennt und ein Einzelwert sie weiter
# schlagen kann - value_of() fragt hier erst NACH dem Einzelwert.
def gaps_out_px(section: dict) -> int:
    """Der Abstand zum Rand: genau zweimal der zwischen zwei Fenstern.

    Hyprland legt gaps_in an JEDE Seite eines Fensters und gaps_out nur
    nach aussen; zwischen zwei Fenstern sieht man also 2*gaps_in und zum
    Rand gaps_out. "Ueberall derselbe Abstand" IST die Gleichung
    2*gaps_in == gaps_out, und sie stand bis zum 12.08.2026 als zwei
    Grundwerte da, die sie beim Grundwert erfuellten.

    GEMESSEN am 12.08.2026, nachdem die ausgelieferte Groesse auf 20 px
    gefallen ist: bei Faktor 1.5385 wird aus 8 eine 12 (12.31 abgerundet)
    und aus 16 eine 25 (24.62 aufgerundet). 24 gegen 25 - die Gleichung
    war um einen Pixel gebrochen, und zwar genau bei der Groesse, mit der
    ausgeliefert wird. Zwei Zahlen, die in einer Gleichung stehen, sind
    eine Zahl.
    """
    return 2 * int(value_of("STYLE_GAPS_IN", section))


DERIVED = {
    "STYLE_BAR_THICKNESS": bar_thickness_px,
    "STYLE_DOCK_ICON_SIZE": dock_icon_px,
    "STYLE_GAPS_OUT": gaps_out_px,
}


def settings_section(settings: dict) -> dict:
    """Der sizes-Abschnitt, oder ein leerer, wenn er fehlt oder Unfug ist.

    Ein Abschnitt, der kein Objekt ist, wird wie keiner behandelt statt
    zu einem AttributeError mitten in der Erzeugung: die Datei ist von
    Hand editierbar, und `"sizes": 1.5` ist der naheliegendste Fehler,
    den jemand macht, der den Faktor sucht.
    """
    section = settings.get(SECTION)
    return section if isinstance(section, dict) else {}


def scale_of(section: dict) -> float:
    """Der Faktor aus dem Abschnitt, oder der ausgelieferte.

    Ein Wert, der keine Zahl ist oder nicht positiv, faellt auf die
    Vorgabe zurueck statt durchzuschlagen. Es reichte sonst, "gross" in
    die Datei zu schreiben, damit JEDE Groesse mit einem TypeError
    mitten in der Erzeugung stirbt - ein Abbruch wegen EINES Wertes,
    ohne dass irgendetwas sagt, welcher es war.

    Null faellt aus demselben Grund zurueck wie ein negativer Wert: eine
    Oberflaeche der Groesse 0 ist unsichtbar, und der Weg zurueck fuehrt
    durch genau diese Oberflaeche.
    """
    try:
        scale = float(section.get("scale", SCALE_DEFAULT))
    except (TypeError, ValueError):
        return SCALE_DEFAULT
    return scale if scale > 0 else SCALE_DEFAULT


def override_of(section: dict, name: str):
    """Was der Nutzer fuer genau diese Groesse gesagt hat, oder None."""
    values = section.get("values")
    if not isinstance(values, dict):
        return None
    return values.get(name)


def value_of(name: str, section: dict) -> str:
    """Der erzeugte Wert einer Groesse, als Zeichenkette mit Einheit.

    Drei Stufen, und ihre Reihenfolge ist die Antwort auf "ein Regler
    oder 365":

      1. sizes.values.<NAME>   was der Nutzer fuer genau diese Groesse
                               gesagt hat. Wortwoertlich uebernommen.
      2. Grundwert * Faktor    fuer alles, was Schrift ist.
      3. Grundwert             fuer die Bilder.

    Die erste Stufe umgeht den Faktor, statt von ihm multipliziert zu
    werden. Wer eine genaue Groesse nennt, hat gesagt, was auf dem
    Schirm stehen soll; eine anschliessende Multiplikation hiesse, dass
    die getippte Zahl dort nirgends vorkommt.

    Gerundet wird kaufmaennisch und nicht mit round(), das zur GERADEN
    Zahl rundet: 11 * 1.5 sind 16.5 und wuerden damit zu 16, 13 * 1.5
    sind 19.5 und wuerden zu 20. Eine Leiter, die an manchen Sprossen ab-
    und an anderen aufrundet, ist keine Leiter mehr.

    Mindestens 1, damit ein sehr kleiner Faktor keine 0 erzeugt.
    """
    override = override_of(section, name)
    if override is not None:
        return str(override)

    size = TABLE[name]
    # Abgeleitet, aber erst nach dem Einzelwert: wer eine Zahl nennt,
    # hat gesagt, was auf dem Schirm stehen soll.
    derived = DERIVED.get(name)
    if derived is not None:
        return f"{derived(section)}{size.unit}"

    if not size.scales:
        return f"{size.base}{size.unit}"
    return f"{max(1, math.floor(size.base * scale_of(section) + 0.5))}{size.unit}"


def defaults() -> dict:
    """Der Abschnitt, wie eine frische Installation ihn hat.

    `values` ist leer und bleibt es, bis jemand eine einzelne Groesse
    nennt. Es mit allen 29 Namen und ihren Grundwerten zu fuellen waere
    dieselbe Falle, in die die Farben schon einmal getappt sind: eine
    zweite Kopie der Tabelle, in einer Datei, die niemand mitpflegt,
    und ab dem ersten Speichern gewinnt die Kopie.
    """
    return {"scale": SCALE_DEFAULT, "values": {}, MOTION_ENABLED: True}
