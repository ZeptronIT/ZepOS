#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt das Plymouth-Thema, das beim Starten nach der Passphrase fragt.

    ./packaging/make-plymouth-theme.py

    src/brand.py + src/sizes.py + src/branding/zepos-logo.svg
        ->  src/boot/plymouth-theme/zepos.script
        ->  src/boot/plymouth-theme/logo.png
        ->  src/boot/plymouth-theme/field.png
        ->  src/boot/plymouth-theme/bullet.png
        ->  src/boot/plymouth-theme/spinner-00.png ... spinner-11.png

Die Ergebnisse werden eingecheckt, wie iso/profile-release/grub/themes/
eingecheckt ist und aus demselben Grund: ein Thema, dessen Bilder beim
Starten fehlen, faellt nicht laut aus. Plymouth zeichnet dann gar nichts
und der Nutzer sieht einen schwarzen Schirm - also muessen die Dateien
mit derselben Sicherheit dasein wie die Skriptdatei selbst.

WARUM PYTHON UND NICHT BASH WIE DIE ZWEI NACHBARN
    packaging/make-brand-assets.sh und iso/make-boot-theme.sh schreiben
    ihre Farben als Literale hin - `xc:#0D3D47` steht in beiden. Das ist
    genau die zweite Kopie, vor der src/brand.py steht: aendert jemand
    dort PETROL, aendern sich der Schreibtisch und die Anmeldemaske, und
    das Startmenue bleibt auf dem alten Ton stehen, ohne dass etwas es
    meldet.

    Dieses Programm IMPORTIERT src/brand.py und src/sizes.py. Damit gibt
    es hier kein Farbliteral und keine zweite Rundungsleiter, und
    tests/boot/test_plymouth.py rechnet dieselbe Ableitung noch
    einmal nach und vergleicht sie mit der erzeugten Datei. Eine
    Aenderung an der Marke, die hier nicht nachgezogen wurde, ist damit
    ein roter Test und keine Entdeckung beim naechsten Einschalten.

WARUM PLYMOUTH HIER KEIN VERSTOSS GEGEN DIE GTK4-REGEL IST
    Die Regel dieses Projekts ist "jede Oberflaeche GTK4, GTK3 ist
    Ausschlusskriterium". Plymouth zeichnet mit KEINEM der beiden: es
    laeuft in der Initramfs, lange bevor es ein /usr, einen Compositor
    oder ein Toolkit gibt, und malt ueber /dev/dri direkt in den
    Bildspeicher (usr/lib/plymouth/renderers/drm.so). Gemessen am Paket
    extra/plymouth 26.134.222-2 aus dem angehefteten ALA-Schnappschuss
    2026/08/04: gtk3 steht dort unter optdepends mit der Bemerkung "x11
    renderer" und wird von ZepOS nicht installiert - der Weg ueber X11
    ist der, den diese Installation gerade nicht nimmt.

    Die Regel gilt fuer Oberflaechen, die AUF dem System laufen. Diese
    hier laeuft davor.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import brand  # noqa: E402
import sizes  # noqa: E402

THEME = REPO / "src/boot/plymouth-theme"
LOGO_SVG = REPO / "src/branding" / brand.LOGO_FILE

# Die Bezugshoehe, auf die alle Pixelmasse unten gerechnet sind.
#
# Plymouth skaliert nichts von sich aus - ein Sprite ist so gross wie
# sein PNG. Das Skript rechnet deshalb beim Start den Faktor
# Fensterhoehe/1080 aus und skaliert damit; die Bilder hier sind die
# Vorlage fuer eine 1080-zeilige Flaeche, wie iso/make-boot-theme.sh
# sein background.png auch fuer 1080 baut.
REFERENCE_HEIGHT = 1080

# Das Eingabefeld. Breite und Hoehe sind gesetzt, der Radius kommt aus
# der Rundungsleiter: sizes.radius_px(-1) ist die Stufe CONTROL, also
# die, die im uebrigen System jeder Knopf und jedes Eingabefeld traegt
# (sizes.RADIUS_ROLES). Ein Feld beim Starten, das anders gerundet ist
# als das Feld in der Anmeldemaske dreissig Sekunden spaeter, ist zwei
# Entwuerfe und nicht einer.
FIELD_W = 620
FIELD_H = 72
FIELD_RADIUS = sizes.radius_px(-1)

# Der Punkt je getipptem Zeichen. Kein Zeichen, kein Sternchen: ein
# runder Punkt ist das, was jede andere verdeckte Eingabe dieses Systems
# zeigt, und er zaehlt genauso gut.
BULLET_D = 14

# ---------------------------------------------------------------------
# Der Spinner
# ---------------------------------------------------------------------
# Er beantwortet die Meldung des Nutzers vom 16.08.2026: "ich haette
# auch gerne einen spinner im passphrase wenn wir das pw eingegeben
# haben das der user ein response bekommt".
#
# WORAUF ER SITZT: mitten im Feld, an der Stelle, an der eine Sekunde
# vorher die Punkte standen. Nichts sonst bewegt sich auf dieser Flaeche,
# und die Wartezeit dahinter ist keine Kleinigkeit - die Argon2id-
# Ableitung mit archinstalls DEFAULT_ITER_TIME von 10000 ms brauchte auf
# einem Core Ultra 7 255U 9,98 / 10,39 / 10,82 Sekunden (gemessen, siehe
# installer/core/crypt.py). Zehn Sekunden ohne jede Regung sind auf einem
# Startbildschirm nicht "es rechnet", sondern "es haengt".
#
# WARUM VORGERECHNETE BILDER UND KEIN Image.Rotate()
#     Plymouths Skriptsprache kann drehen (Image.Rotate steht in der in
#     script.so eingebetteten Skriptbibliothek). Aber der Bildtakt ist
#     50 Hz - siehe REFRESH_HZ -, und jede Drehung legt ein neues Bild
#     im Arbeitsspeicher der Initramfs an. Zwoelf fertige PNGs kosten
#     zusammen ein paar Kilobyte und zur Laufzeit gar nichts.
#
# ZWOELF PUNKTE AUF EINEM RING, einer hell, die anderen abfallend. Das
# ist dieselbe Form, die BULLET_D schon fuer die Eingabe benutzt - der
# Spinner ist damit kein zweites Formenvokabular, sondern derselbe Punkt
# in Bewegung.
SPIN_FRAMES = 12
SPIN_D = 40
SPIN_DOT = 6

# Wie durchsichtig der letzte Punkt hinter dem Kopf ist. Nicht 0: ein
# Ring, von dem Stuecke fehlen, liest sich als Fehler; ein Ring, der
# heller und dunkler wird, liest sich als Drehung.
SPIN_TAIL = 0.15

# Der Bildtakt, mit dem Plymouth die Refresh-Funktion ruft.
#
# GEMESSEN am 17.08.2026 an plymouth 26.134.222-2 aus dem angehefteten
# ALA-Schnappschuss 2026/08/04, und zwar zweimal unabhaengig:
#
#   * usr/lib/plymouth/script.so, `show_splash_screen` bei 0xf8d2 ruft
#     script_lib_plymouth_setup mit `mov edx,0x32` = 50 auf; die Zahl
#     landet bei 0xea43 im Feld +0x84 der Bibliotheksdaten. `on_timeout`
#     bei 0x7010 rechnet daraus `1.0 / 50` (die 1.0 ist der Double bei
#     .rodata 0x130e0) und traegt sich damit bei 0x704d wieder in
#     ply_event_loop_watch_for_timeout ein. Also alle 20 ms.
#   * usr/share/plymouth/themes/script/script.script, das mitgelieferte
#     Beispielthema, rechnet in refresh_callback mit
#     `((2 * 3.14) / 50) * 0.5;  # 0.5 HZ` - dieselbe 50.
#
# Plymouth.SetRefreshRate() koennte sie aendern; dieses Thema laesst sie
# stehen, weil 50 Hz fuer eine Drehung reichlich sind.
REFRESH_HZ = 50

# Wieviele Takte ein Bild stehenbleibt. 4 ergibt 12,5 Bilder je Sekunde
# und damit 12 * 4 / 50 = 0,96 Sekunden fuer eine Umdrehung - schnell
# genug, um als Bewegung gelesen zu werden, langsam genug, um nicht zu
# flimmern.
SPIN_HOLD = 4

# Die drei Schriftgrade, und sie sind NICHT frei gewaehlt.
#
# sizes.ANCHOR_PX ist mit dem Satz "Die Grundschrift des Startmenues, in
# Pixeln. iso/make-boot-theme.sh" ausdruecklich der Grad einer
# START-Oberflaeche - nicht der des Schreibtisches (sizes.DEFAULT_PX,
# 20), der einem Skalierungsfaktor folgt, den es hier noch nicht gibt.
# Diese Flaeche kommt zwischen dem Startmenue und der Anmeldemaske, also
# nimmt sie den Grad des Startmenues.
#
# Die Aufforderung eine Stufe darueber, jede Zeile unter dem Feld eine
# darunter, beide ueber sizes.FONT_RATIO - dieselbe Leiter, auf der die
# ganze Oberflaeche steht. Die Zeilen unter dem Feld sind alle gleich
# gross, weil sie sich abwechseln und uebereinanderstapeln: der Hinweis
# zur Belegung, die Meldung ueber eine falsche Passphrase, die
# Feststelltaste und der Satz waehrend der Rechnung.
PROMPT_PX = round(sizes.ANCHOR_PX * sizes.FONT_RATIO)
HINT_PX = round(sizes.ANCHOR_PX / sizes.FONT_RATIO)

# Die Wortmarke. 26.8% der Hoehe ist der Anteil, den das Startmenue ihr
# gibt (iso/make-boot-theme.sh, logo_w = H * 268 / 1000) - hier als
# Breite bei 1080 Zeilen ausgerechnet, damit die Uebergabe vom Menue zu
# dieser Flaeche die Marke nicht springen laesst.
LOGO_W = 480


def rgb_floats(colour: str) -> tuple[float, float, float]:
    """"#rrggbb" als die drei Fliesskommazahlen, die Plymouth will.

    Plymouths Skriptsprache kennt keine Hexfarbe. Window.SetBackground
    TopColor() und Image.Text() nehmen drei Werte von 0 bis 1, und diese
    Umrechnung ist die einzige Stelle, an der eine Farbe dieses Projekts
    ihre Form wechselt.
    """
    value = colour.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def plymouth_colour(colour: str) -> str:
    """Dieselbe Farbe als Argumentliste, fertig zum Einsetzen."""
    return ", ".join(f"{channel:.4f}" for channel in rgb_floats(colour))


def require(tool: str) -> None:
    if shutil.which(tool) is None:
        sys.exit(f"make-plymouth-theme.py: {tool} ist nicht installiert")


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def render_logo() -> None:
    """Die Wortmarke, auf ihre eigene Tinte beschnitten.

    Dasselbe -trim wie in iso/make-boot-theme.sh: die SVG traegt eine
    Zeichenflaeche, die groesser ist als die Marke darin, und "mittig"
    soll die Marke meinen und nicht den leeren Rand um sie herum.
    """
    raw = THEME / "logo-raw.png"
    run("rsvg-convert", "-w", str(LOGO_W * 2), str(LOGO_SVG), "-o", str(raw))
    run("magick", str(raw), "-trim", "+repage", "-resize", f"{LOGO_W}x",
        "-depth", "8", "-strip", str(THEME / "logo.png"))
    raw.unlink()


def render_field() -> None:
    """Das Eingabefeld: eine gefuellte, gerundete Flaeche mit Rand.

    Die Fuellung ist INK und nicht PETROL - dieselbe Regel wie im
    laufenden System (src/brand.py: "Panels that sit ON the desktop go
    darker than the desktop itself, or they read as a hole in it rather
    than a surface over it"). Die Flaeche hinter dem Feld ist der
    Petrol-Verlauf, das Feld liegt darauf, also geht es darunter.

    Der Rand ist SHADE_2. Ohne ihn verschwindet ein dunkles Feld auf
    einem dunklen Grund, und ein Feld, das man nicht sieht, ist ein Feld,
    in das niemand tippt.
    """
    x1, y1 = FIELD_W - 1, FIELD_H - 1
    run("magick", "-size", f"{FIELD_W}x{FIELD_H}", "xc:none",
        "-fill", brand.INK, "-stroke", brand.SHADE_2, "-strokewidth", "2",
        "-draw", f"roundrectangle 1,1 {x1 - 1},{y1 - 1} "
                 f"{FIELD_RADIUS},{FIELD_RADIUS}",
        "-depth", "8", "-strip", str(THEME / "field.png"))


def render_bullet() -> None:
    """Ein Punkt in der Textfarbe."""
    radius = BULLET_D / 2
    run("magick", "-size", f"{BULLET_D}x{BULLET_D}", "xc:none",
        "-fill", brand.TEXT, "-stroke", "none",
        "-draw", f"circle {radius},{radius} {radius},{BULLET_D - 1}",
        "-depth", "8", "-strip", str(THEME / "bullet.png"))


def render_spinner() -> None:
    """Die zwoelf Bilder der Drehung, jedes einzeln gezeichnet.

    NICHT GEDREHT, SONDERN GEZEICHNET: ein einmal gezeichneter Ring, den
    ImageMagick zwoelfmal um 30 Grad dreht, laeuft durch zwoelf
    Neuabtastungen - der Ring wird bei jeder Drehung ein bisschen
    weicher, und bei 30 Grad liegen die Punkte hinterher nicht mehr
    genau uebereinander. Jedes Bild aus denselben zwoelf Kreisen zu
    bauen und nur die Deckkraft weiterzuschieben kostet dasselbe und
    liefert zwoelf gleich scharfe Bilder.
    """
    ring = (SPIN_D - SPIN_DOT) / 2
    mitte = SPIN_D / 2
    rot, gruen, blau = (int(brand.TEXT.lstrip("#")[i:i + 2], 16)
                        for i in (0, 2, 4))

    for bild in range(SPIN_FRAMES):
        befehl = ["magick", "-size", f"{SPIN_D}x{SPIN_D}", "xc:none",
                  "-stroke", "none"]
        for punkt in range(SPIN_FRAMES):
            # Der Abstand hinter dem Kopf, im Uhrzeigersinn gezaehlt.
            alter = (bild - punkt) % SPIN_FRAMES
            deckkraft = 1.0 - alter * (1.0 - SPIN_TAIL) / (SPIN_FRAMES - 1)
            # Oben anfangen und im Uhrzeigersinn weiter: y zeigt im Bild
            # nach unten, also dreht ein wachsender Winkel von selbst in
            # die Richtung, die ein Mensch als "vorwaerts" liest.
            winkel = math.radians(punkt * 360 / SPIN_FRAMES - 90)
            x = mitte + ring * math.cos(winkel)
            y = mitte + ring * math.sin(winkel)
            befehl += [
                "-fill", f"rgba({rot},{gruen},{blau},{deckkraft:.3f})",
                "-draw", f"circle {x:.2f},{y:.2f} "
                         f"{x:.2f},{y + SPIN_DOT / 2:.2f}",
            ]
        befehl += ["-depth", "8", "-strip",
                   str(THEME / f"spinner-{bild:02d}.png")]
        run(*befehl)


# Die Beschreibungsdatei, die plymouth-set-default-theme liest.
#
# WARUM AUCH SIE ERZEUGT WIRD, obwohl nur eine Zeile darin einen Wert aus
# dem Designsystem traegt: wegen genau dieser Zeile. Der initcpio-Haken
# von Plymouth liest Font= mit einem sed heraus, streicht die Zahl am
# Ende und gibt den Rest an fc-match - der Name muss also mit
# brand.FONT_TEXT uebereinstimmen, sonst legt der Haken eine ANDERE
# Schrift als /usr/share/fonts/Plymouth.ttf in die Initramfs und der
# Startbildschirm ist in einer Schrift, die dieses Projekt nirgends sonst
# benutzt. Gemessen an extra/plymouth 26.134.222-2,
# usr/lib/initcpio/install/plymouth.
#
# ModuleName=script ist die Wahl gegen two-step: two-step spielt eine
# Bildfolge ab und kann eine Passphrase nur so abfragen, wie sein
# Plugin es vorsieht. script.so gibt dem Thema die Rueckrufe selbst -
# SetDisplayPasswordFunction, GetCapslockState -, und genau die braucht
# diese Flaeche.
DESCRIPTOR = '''\
[Plymouth Theme]
Name=ZepOS
Description=Die Passphrase-Abfrage von ZepOS, in der Marke.
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/zepos
ScriptFile=/usr/share/plymouth/themes/zepos/zepos.script
Font={font} {anchor}
'''


SCRIPT = '''\
# ZepOS - die Abfrage der Plattenpassphrase beim Starten.
#
# ERZEUGT VON packaging/make-plymouth-theme.py - NICHT DIREKT BEARBEITEN.
# Jede Farbe hier kommt aus src/brand.py, jede Rundung aus src/sizes.py.
# Wer hier etwas aendert, verliert es beim naechsten Lauf des Erzeugers;
# tests/boot/test_plymouth.py rechnet die Werte nach.
#
# WAS DIESE DATEI IST
#     Die erste Oberflaeche, die eine verschluesselte ZepOS-Installation
#     zeigt - vor der Anmeldemaske und direkt nach dem Startmenue. Bis
#     zum 13.08.2026 stand hier eine Textzeile auf der Konsole ("A
#     password is required to access the root volume"), weil archinstall
#     den klassischen encrypt-Haken einhaengt und nichts weiter.
#
#     Der encrypt-Haken von mkinitcpio 41-4 fragt selbst nach Plymouth
#     (usr/lib/initcpio/hooks/encrypt): laeuft plymouthd, dann geht die
#     Abfrage ueber `plymouth ask-for-password`, sonst ueber echo und
#     cryptsetup. Diese Datei ist die eine Haelfte davon, der Haken
#     `plymouth` in der HOOKS-Zeile die andere.
#
#     UND ES IST DER HAKEN `encrypt`, NICHT `plymouth-encrypt`. Der
#     zweite ist der Name, der in jeder Anleitung im Netz steht, und er
#     existiert in diesem Schnappschuss nicht mehr: mkinitcpio 41-4
#     liefert unter usr/lib/initcpio/hooks/ genau consolefont, encrypt,
#     keymap, memdisk, resume, shutdown, sleep, udev und usr, und
#     plymouth 26.134.222-2 legt nur hooks/plymouth daneben (beide
#     Pakete am 13.08.2026 aus dem angehefteten ALA-Schnappschuss
#     2026/08/04 ausgepackt und aufgezaehlt). Wer plymouth-encrypt in
#     die HOOKS-Zeile schriebe, bekaeme von mkinitcpio ein "Hook
#     'plymouth-encrypt' cannot be found" - und eine Initramfs ohne
#     JEDEN encrypt-Haken, also eine Maschine, die ihre eigene Wurzel
#     nicht mehr aufbekommt.
#
# WORAN DIESE FLAECHE MERKT, WAS GERADE PASSIERT
#     Sie hat drei Zustaende - "normal" (nichts steht da), "password"
#     (es wird getippt) und "pruefung" (es wird gerechnet) -, und
#     Plymouth sagt ihr keinen davon direkt. Alles unten ist am
#     17.08.2026 an plymouth 26.134.222-2 und mkinitcpio 41-4 aus dem
#     angehefteten ALA-Schnappschuss 2026/08/04 gemessen.
#
#     ES GIBT KEINEN VERSUCHSZAEHLER. Der zweite Wert, den
#     SetDisplayPasswordFunction durchreicht, ist die Zahl der GETIPPTEN
#     ZEICHEN und nicht die der Versuche: script_lib_plymouth_on_display_
#     password (script.so, 0x74f0) baut genau zwei Skriptobjekte - eine
#     Zeichenkette aus dem prompt (0x750a) und eine Zahl aus dem int
#     (0x751b) - und uebergibt sie mit NULL als Abschluss an
#     script_execute_object (0x7538). Derselbe int ist im Plugin bei
#     0x7617 die Schleifengrenze, mit der `display_password` je getipptem
#     Zeichen EIN Sternchen auf die Konsole schreibt. Ein dritter Wert
#     kaeme nie an.
#
#     WAS ES STATT DESSEN GIBT, ist die Reihenfolge der Rueckrufe:
#
#       Eingabetaste -> display_normal_callback.
#         plymouthd, `on_enter` (0x11070): nachdem die Antwort mit
#         ply_trigger_pull (0x110e9) beim Client ist, der Puffer geleert
#         (0x110f4) und der Eintrag aus der Warteschlange genommen wurde
#         (0x11102), springt es bei 0x1112d nach `update_display`
#         (0x109f0) - und das ruft bei leerer Warteschlange (0x10b2c)
#         ply_boot_splash_display_normal. Dieser Rueckruf IST also das
#         Abschicken, und genau da faengt der Spinner an.
#
#       Abgewiesen -> display_password_callback ZUM ZWEITEN MAL.
#         usr/lib/initcpio/hooks/encrypt (Zeile 104-107 in mkinitcpio
#         41-4) ruft `plymouth ask-for-password` OHNE --number-of-tries
#         auf; die Wiederholung steckt also im Client. Und sie hoert
#         nicht auf: `on_password_request` (usr/bin/plymouth, 0x6540)
#         liest die Zahl bei 0x65fe aus, prueft sie bei 0x660f und setzt
#         sie, wenn sie nicht groesser als 0 ist, bei 0x6614 auf
#         0x7fffffff. Eine falsche Passphrase kostet also einen weiteren
#         Versuch und nicht den Start.
#         plymouthd, `on_ask_for_password` (0x14cc0), haengt den Eintrag
#         an (0x14d45) und springt bei 0x14d7d wieder in
#         `update_display`, das diesmal ply_boot_splash_display_password
#         ruft (0x10abf). Eine neue Abfrage, NACHDEM schon einmal
#         abgeschickt wurde, kann nur eines heissen: cryptsetup hat die
#         vorige Passphrase nicht angenommen.
#
#     Mehr Auskunft gibt es nicht - plymouthd kennt das Wort "falsch"
#     nirgends -, und mehr wird auch nicht gebraucht.
#
# UND SIE SPRICHT NUR DEUTSCH
#     Kein Satz auf dieser Flaeche kann uebersetzt werden. In der
#     Initramfs liegt seit dem 17.08.2026 genau ein Katalog, und der ist
#     nicht unserer: die niederlaendische plymouth.mo, die dort als
#     Anwesenheitsprobe fuer plymouthds setlocale-Aufruf steht (siehe
#     weiter unten). Fuer die Saetze eines THEMAS kennt Plymouth keinen
#     Katalog; sie stehen als Literale in dieser Datei, weil sie beim
#     Erzeugen eingesetzt wurden. Wenn ZepOS eine zweite Sprache
#     bekommt, muessen sie beim Bauen der Initramfs auf der ZIELmaschine
#     aus deren locale.conf eingesetzt werden - das ist machbar und heute
#     nicht gebaut. Steht auch bei den Saetzen selbst, in
#     packaging/make-plymouth-theme.py.
#
#     UND SEIT DEM 17.08.2026 MIT UMLAUTEN, was drei Stuecke in der
#     Initramfs voraussetzt und deshalb hier angeschrieben steht.
#     Plymouth zeichnete ein U+00FC vorher nicht, es verschluckte es -
#     beide Bytes fielen heraus, es kam nicht einmal ein Kaestchen.
#
#     GEMESSEN am 17.08.2026, erst am Binaercode und dann viermal am
#     Schirm. Die Schrift war nie das Problem: der initcpio-Haken legt
#     ueber `fc-match` Roboto als /usr/share/fonts/Plymouth.ttf in die
#     Initramfs (460324 Bytes), und deren cmap fuehrt U+00FC als Glyph
#     2333 und U+2013 als 1118. Der Zeichner ist es:
#     usr/lib/plymouth/label-freetype.so schiebt jedes Zeichen bei
#     0x26de durch `mbrtowc`, also durch das GEBIETSSCHEMA - und
#     plymouthd ruft setlocale(LC_ALL, "") bei 0x53e9 nur dann, wenn
#     ply_file_exists() bei 0x53d3 die Datei bei .rodata 0x1f100
#     findet:
#
#         /usr/share/locale/nl/LC_MESSAGES/plymouth.mo
#
#     WAS DIE INITRAMFS SEITHER MITBRINGT, und ohne das Letzte davon
#     stand weiterhin "geprft" auf dem Schirm:
#
#       * den Haken `zepos-locale` vor `plymouth`, der LC_ALL=C.UTF-8
#         setzt, bevor plymouthd startet,
#       * jene .mo-Datei, damit setlocale ueberhaupt laeuft,
#       * und /usr/lib/locale/C.utf8, weil "C.UTF-8" in dieser glibc
#         nicht eingebaut ist, sondern als Daten daliegt.
#
#     Alle drei kommen aus installer/core/translate.py,
#     PLYMOUTH_COMMAND, und fehlt eines davon, dann baut der Befehl die
#     Initramfs gar nicht erst um: die Abfrage ist dann wieder die
#     englische Textzeile und nicht ein deutscher Satz mit Loechern.

# ---------------------------------------------------------------------
# Die Flaeche
# ---------------------------------------------------------------------
# Derselbe Verlauf, den das Startmenue eine Sekunde vorher zeigt: oben
# das Petrol der Marke, unten die dunklere Tiefe. Kein Bild, weil keins
# noetig ist - zwei Farben und der Verlauf dazwischen kosten in der
# Initramfs nichts und koennen nicht fehlen.
Window.SetBackgroundTopColor({top});
Window.SetBackgroundBottomColor({bottom});

# ---------------------------------------------------------------------
# Der Massstab
# ---------------------------------------------------------------------
# Plymouth skaliert nichts von sich aus. Die Bilder daneben sind fuer
# {reference} Zeilen gezeichnet; auf einer anderen Flaeche wird alles mit
# demselben Faktor umgerechnet, damit die Aufteilung dieselbe bleibt.
scale = Window.GetHeight() / {reference};
if (scale < 0.5) scale = 0.5;

fun scaled (image)
  {{
    return image.Scale(image.GetWidth() * scale, image.GetHeight() * scale);
  }}

centre_x = Window.GetX() + Window.GetWidth()  / 2;

# ---------------------------------------------------------------------
# Die Wortmarke
# ---------------------------------------------------------------------
# Auf 34% der Hoehe und nicht in der Mitte: darunter stehen das Feld und
# zwei Zeilen Text, und die Gruppe aus allem vieren soll mittig sitzen,
# nicht die Marke allein.
mark.image = scaled(Image("logo.png"));
mark.sprite = Sprite(mark.image);
mark.sprite.SetPosition(centre_x - mark.image.GetWidth() / 2,
                        Window.GetY() + Window.GetHeight() * 0.34
                            - mark.image.GetHeight() / 2,
                        1);

# ---------------------------------------------------------------------
# Das Feld, die Punkte und die zwei Zeilen Text
# ---------------------------------------------------------------------
field.image = scaled(Image("field.png"));
field.x = centre_x - field.image.GetWidth() / 2;
field.y = Window.GetY() + Window.GetHeight() * 0.52;

bullet.image = scaled(Image("bullet.png"));

# Der Abstand zwischen zwei Punkten. Der Durchmesser plus die Haelfte -
# Punkte, die sich beruehren, sind ein Balken und keine Anzahl.
bullet.step = bullet.image.GetWidth() * 1.5;

# Wieviele Punkte ins Feld passen. Eine lange Passphrase laeuft sonst
# rechts aus dem Feld heraus, und {minimum} Zeichen sind die Untergrenze,
# die installer/core/crypt.py verlangt - es sind also immer viele.
bullet.room = Math.Int((field.image.GetWidth() - {padding} * scale * 2)
                       / bullet.step);

# ---------------------------------------------------------------------
# Der Spinner
# ---------------------------------------------------------------------
# Zwoelf fertige Bilder, in der Reihenfolge der Drehung. Sie werden HIER
# geladen und nicht erst, wenn sie gebraucht werden: das Laden faellt in
# den Augenblick, in dem die Flaeche ohnehin aufgebaut wird, und nicht in
# den, in dem der Nutzer gerade auf eine Reaktion wartet.
#
# Die Liste steht ausgeschrieben da, weil diese Datei erzeugt wird. Eine
# Schleife muesste den Dateinamen aus einer Zahl zusammensetzen, und
# Plymouths Zahlenformat (%g) ist nichts, worauf ein Dateiname sich
# stuetzen sollte.
spin.count = {spin_frames};
spin.hold = {spin_hold};
spin.frame = 0;
spin.tick = 0;
spin.sprite = NULL;
{spin_loads}
# Ein Sprite mit Text darin.
#
# DIE FUENF PARAMETER SIND DIE VON Image.Text MINUS DER DECKKRAFT, und
# das ist gemessen und nicht geraten. In script.so von plymouth
# 26.134.222-2 steht die Signatur als Quelltext eingebettet
# (script-lib-image.script, mit `strings` herausgeholt am 13.08.2026):
#
#     Image.Text = fun (text, red, green, blue, alpha, font, align)
#
# Die Deckkraft steht hier fest auf 1: nichts auf dieser Flaeche wird
# eingeblendet, und ein durchscheinender Hinweis waere ein Hinweis, den
# jemand uebersieht.
#
# WARUM DAS HIER UEBERHAUPT ANGESCHRIEBEN STEHT: die Fassung vom
# 13.08.2026 rief diese Funktion mit SECHS Werten auf - die Deckkraft
# stand noch in jedem Aufruf. Plymouths Skriptsprache meldet das nicht;
# sie bindet der Reihe nach und wirft den Rest weg. Damit landete die 1
# in `size`, jeder Text wurde in "Roboto 1" gesetzt, und heraus kam eine
# Flaeche, auf der die Schrift zwar da, aber einen Pixel hoch ist.
fun text_sprite (message, colour_r, colour_g, colour_b, size)
  {{
    local.sprite = Sprite();
    local.image = Image.Text(message, colour_r, colour_g, colour_b, 1,
                             "{font} " + size);
    sprite.SetImage(image);
    return sprite;
  }}

status = "normal";
bullets = 0;

# Ob schon eine Passphrase abgeschickt und noch nicht beantwortet wurde,
# und ob die letzte abgewiesen worden ist. Die beiden zusammen sind die
# ganze Auskunft, die dieses Thema ueber den Ausgang eines Versuchs
# bekommt - warum, steht oben unter "WORAN DIESE FLAECHE MERKT".
eingereicht = 0;
abgewiesen = 0;

# ---------------------------------------------------------------------
# Die Abfrage
# ---------------------------------------------------------------------
# Plymouth ruft das hier bei jedem Tastendruck neu auf und uebergibt die
# ANZAHL der Zeichen, nie die Zeichen selbst - das Skript bekommt die
# Passphrase gar nicht zu sehen.
fun display_password_callback (prompt, entered)
  {{
    if (status != "password")
      {{
        # Eine NEUE Abfrage. Kommt sie, nachdem schon einmal abgeschickt
        # wurde, dann hat cryptsetup die vorige Passphrase abgelehnt -
        # das ist der einzige Weg, auf dem der Client hier wieder
        # hereinkommt.
        if (eingereicht) global.abgewiesen = 1;
        global.eingereicht = 0;
      }}
    global.status = "password";
    global.bullets = entered;
    draw_dialog();
  }}

fun display_normal_callback ()
  {{
    # Waehrend gerechnet wird, ruft Plymouth das hier noch einmal, wenn
    # jemand eine Taste anfasst. Der Spinner darf davon nicht neu
    # anfangen.
    if (status == "pruefung") return;

    if (status == "password")
      {{
        # Die Eingabetaste. Ab hier rechnet cryptsetup, und bis zur
        # Antwort vergehen zehn Sekunden - siehe den Spinner.
        global.eingereicht = 1;
        global.abgewiesen = 0;
        global.status = "pruefung";
      }}
    else
      {{
        global.status = "normal";
      }}
    draw_dialog();
  }}

fun draw_dialog ()
  {{
    if (status == "normal")
      {{
        global.field.sprite = NULL;
        global.prompt.sprite = NULL;
        global.hint.sprite = NULL;
        global.fehler.sprite = NULL;
        global.caps.sprite = NULL;
        global.warte.sprite = NULL;
        global.spin.sprite = NULL;
        global.bullets = 0;
        for (i = 0; global.dot[i]; i++) global.dot[i].sprite = NULL;
        return;
      }}

    # Das Feld bleibt in BEIDEN uebrigen Zustaenden stehen, und an
    # derselben Stelle. Eine Flaeche, deren Aufbau beim Abschicken
    # springt, sieht aus, als waere sie neu geladen worden - dabei ist
    # es dieselbe Frage, die gerade beantwortet wird.
    global.field.sprite = Sprite(field.image);
    field.sprite.SetPosition(field.x, field.y, 10);

    if (status == "pruefung")
      {{
        draw_pruefung();
        return;
      }}
    draw_abfrage();
  }}

# Die Zeilen unter dem Feld, in fester Reihenfolge und ohne Luecken.
#
# Zeile 0 sitzt {gap} unter dem Feld, jede weitere eine Zeilenhoehe
# tiefer. Damit steht die erste immer dort, wo der Hinweis vorher allein
# stand, und die Feststelltaste rutscht nur dann nach unten, wenn
# wirklich eine Meldung dazwischenkommt.
fun zeile_unter_dem_feld (sprite, nummer)
  {{
    sprite.SetPosition(
        centre_x - sprite.GetImage().GetWidth() / 2,
        field.y + field.image.GetHeight() + {gap} * scale
            + nummer * ({hint_px} + {gap}) * scale, 10);
  }}

fun draw_abfrage ()
  {{
    global.warte.sprite = NULL;
    global.spin.sprite = NULL;

    # Die Aufforderung ueber dem Feld. Der Text kommt NICHT von Plymouth
    # (der englische Satz des encrypt-Hakens), sondern steht hier - die
    # Maschine hat gerade auf Deutsch gefragt, ob sie verschluesseln
    # soll, und antwortet jetzt auf Englisch waere ein Bruch.
    global.prompt.sprite = text_sprite("{prompt_text}", {text},
                                       Math.Int({prompt_px} * scale));
    prompt.sprite.SetPosition(
        centre_x - prompt.sprite.GetImage().GetWidth() / 2,
        field.y - prompt.sprite.GetImage().GetHeight() - {gap} * scale, 10);

    # Die Meldung, nach der der Nutzer am 16.08.2026 gefragt hat: "bei pw
    # falsch sollte das auch darstehene".
    #
    # OHNE SIE kommt die Abfrage wortlos wieder, und zwar genau so, wie
    # sie vorher stand. Ein Mensch, der zehn Sekunden gewartet hat und
    # dann wieder ein leeres Feld sieht, kann daraus zwei voellig
    # verschiedene Dinge lesen: dass er sich vertippt hat, oder dass die
    # Maschine seine Eingabe nie bekommen hat. Der Unterschied
    # entscheidet, ob er es noch einmal versucht oder das Medium sucht.
    #
    # Sie steht ZUERST und schiebt den Hinweis eine Zeile tiefer: das
    # Neueste sitzt am naechsten am Feld, und der Satz zur
    # Tastaturbelegung liest sich direkt darunter als die Erklaerung, die
    # er in diesem Augenblick ist.
    if (abgewiesen)
      {{
        global.fehler.sprite = text_sprite("{fehler_text}", {red},
                                           Math.Int({hint_px} * scale));
        zeile_unter_dem_feld(fehler.sprite, 0);
        global.hint.zeile = 1;
      }}
    else
      {{
        global.fehler.sprite = NULL;
        global.hint.zeile = 0;
      }}

    # Und der Satz darunter, der eine Platte rettet.
    #
    # WORAUF ER SICH STUETZT, gemessen am 13.08.2026 an der
    # ausgelieferten Initramfs: plymouth liest Tastaturen ueber evdev
    # und uebersetzt sie mit libxkbcommon (objdump -p auf
    # libply-splash-core.so.5 zeigt beide als NEEDED), und die Belegung
    # dafuer holt es aus /etc/vconsole.conf IN DER INITRAMFS. Der
    # initcpio-Haken von plymouth legt diese Datei nicht hinein;
    # installer/core/translate.py, PLYMOUTH_COMMAND, tut es ueber die
    # FILES-Zeile und laesst die Abfrage sonst eine Textzeile bleiben.
    #
    # Es ist damit dieselbe Belegung, die im Assistenten gewaehlt wurde.
    # Wer sie kennt, tippt richtig; wer sie nicht kennt, tippt bei y, z
    # und jedem Umlaut daneben - und sieht es nicht, weil die Eingabe
    # verdeckt ist. Deshalb steht die Belegung DA, statt dass der Nutzer
    # sie raten muss.
    global.hint.sprite = text_sprite("{hint_text}", {text_dim},
                                     Math.Int({hint_px} * scale));
    zeile_unter_dem_feld(hint.sprite, hint.zeile);

    global.caps.zeile = hint.zeile + 1;

    draw_bullets();
    draw_capslock();
  }}

# ---------------------------------------------------------------------
# Waehrend gerechnet wird
# ---------------------------------------------------------------------
# Derselbe Aufbau wie die Abfrage, nur dass im Feld statt der Punkte der
# Spinner steht und ueber und unter dem Feld etwas anderes. Das Feld, die
# Wortmarke und die Mitte bleiben, wo sie waren.
fun draw_pruefung ()
  {{
    global.bullets = 0;
    draw_bullets();
    global.hint.sprite = NULL;
    global.fehler.sprite = NULL;
    global.caps.sprite = NULL;

    # "geprueft" und nicht "entsperrt": in diesem Augenblick ist noch
    # offen, ob die Platte aufgeht. Ein Satz, der das Ergebnis
    # vorwegnimmt, waere in jedem zweiten Fall gelogen.
    global.prompt.sprite = text_sprite("{pruefung_text}", {text},
                                       Math.Int({prompt_px} * scale));
    prompt.sprite.SetPosition(
        centre_x - prompt.sprite.GetImage().GetWidth() / 2,
        field.y - prompt.sprite.GetImage().GetHeight() - {gap} * scale, 10);

    global.warte.sprite = text_sprite("{warte_text}", {text_dim},
                                      Math.Int({hint_px} * scale));
    zeile_unter_dem_feld(warte.sprite, 0);

    # Den Spinner nur anlegen, wenn er noch nicht steht - sonst finge die
    # Drehung bei jedem Neuzeichnen wieder oben an.
    if (!spin.sprite)
      {{
        global.spin.frame = 0;
        global.spin.tick = 0;
        global.spin.sprite = Sprite(spin.image[0]);
        spin.sprite.SetPosition(
            field.x + field.image.GetWidth() / 2
                - spin.image[0].GetWidth() / 2,
            field.y + field.image.GetHeight() / 2
                - spin.image[0].GetHeight() / 2, 11);
      }}
  }}

fun drehe_den_spinner ()
  {{
    global.spin.tick = spin.tick + 1;
    if (spin.tick < spin.hold) return;
    global.spin.tick = 0;

    global.spin.frame = spin.frame + 1;
    if (spin.frame == spin.count) global.spin.frame = 0;
    spin.sprite.SetImage(spin.image[spin.frame]);
  }}

fun draw_bullets ()
  {{
    local.shown = bullets;
    if (shown > bullet.room) shown = bullet.room;

    # Zentriert im Feld und nicht linksbuendig: die Punkte sind kein
    # Text, sie sind eine Anzeige, und eine Anzeige, die von links
    # waechst, sieht aus wie eine Zeile, die gleich ueberlaeuft.
    local.total = shown * bullet.step - (bullet.step - bullet.image.GetWidth());
    local.start = field.x + field.image.GetWidth() / 2 - total / 2;
    local.y = field.y + field.image.GetHeight() / 2
              - bullet.image.GetHeight() / 2;

    for (i = 0; global.dot[i] || i < shown; i++)
      {{
        if (i < shown)
          {{
            global.dot[i].sprite = Sprite(bullet.image);
            global.dot[i].sprite.SetPosition(start + i * bullet.step, y, 11);
          }}
        else
          {{
            global.dot[i].sprite = NULL;
          }}
      }}
  }}

fun draw_capslock ()
  {{
    # Die Feststelltaste, und sie ist hier keine Spielerei.
    #
    # Eine verdeckte Eingabe zeigt ihren Tippfehler nicht, und eine
    # feststehende Umschaltung macht aus jeder Passphrase eine andere -
    # zehn Sekunden Argon2id spaeter steht dann "Fehler" da und niemand
    # weiss, warum. GetCapslockState() ist die einzige Auskunft, die
    # Plymouth darueber gibt.
    #
    # SIE HAENGT AN Plymouth UND NICHT AN Window, und das ist gemessen
    # statt abgeschrieben. Die Namen der eingebauten Funktionen stehen
    # nicht in einer Dokumentation, sondern in script.so; welcher Name
    # an welchem Objekt haengt, entscheidet sich dort in zwei
    # Anmeldefunktionen. Am 13.08.2026 aus plymouth 26.134.222-2
    # ausgelesen (objdump -d, Zeichenketten den `lea`-Zugriffen
    # zugeordnet):
    #
    #     script_lib_plymouth_setup   ... SetQuitFunction,
    #                                 GetCapslockState, GetMode, ...
    #     script_lib_sprite_setup     ... Window, GetWidth, GetHeight,
    #                                 GetX, GetY, SetX, SetY,
    #                                 SetBackgroundTopColor, ...
    #
    # GetCapslockState steht in der ERSTEN Liste und in der zweiten
    # nicht. Die Fassung vom 13.08.2026 rief Window.GetCapslockState()
    # auf - ein Feld, das es an Window nicht gibt. Plymouth kennt dafuer
    # keine Warnung; es liefert NULL und ruft NULL auf, und was davon
    # auf dem Schirm ankaeme, ist nichts.
    if (status != "password")
      {{
        global.caps.sprite = NULL;
        return;
      }}
    if (!Plymouth.GetCapslockState())
      {{
        global.caps.sprite = NULL;
        return;
      }}
    global.caps.sprite = text_sprite("{caps_text}", {yellow},
                                     Math.Int({hint_px} * scale));
    zeile_unter_dem_feld(caps.sprite, caps.zeile);
  }}

Plymouth.SetDisplayPasswordFunction(display_password_callback);
Plymouth.SetDisplayNormalFunction(display_normal_callback);

# Der Bildtakt. Plymouth ruft das hier {refresh_hz} mal je Sekunde
# (gemessen, siehe REFRESH_HZ in packaging/make-plymouth-theme.py), und
# es ist der einzige Takt, den dieses Thema hat: die Feststelltaste kann
# sich aendern, ohne dass ein Zeichen ankommt, und eine Drehung braucht
# ohnehin eine Uhr.
fun refresh_callback ()
  {{
    if (status == "pruefung")
      {{
        drehe_den_spinner();
        return;
      }}
    if (status == "password") draw_capslock();
  }}
Plymouth.SetRefreshFunction(refresh_callback);

# ---------------------------------------------------------------------
# Meldungen
# ---------------------------------------------------------------------
# Was Plymouth sonst noch sagen will, unten am Rand und klein. Ohne
# diesen Haken verschwindet es lautlos - darunter auch "Passphrase
# falsch", und das ist die eine Meldung, die ankommen muss.
fun display_message_callback (text)
  {{
    global.message.sprite = text_sprite(text, {text_dim},
                                        Math.Int({hint_px} * scale));
    message.sprite.SetPosition(
        centre_x - message.sprite.GetImage().GetWidth() / 2,
        Window.GetY() + Window.GetHeight() * 0.88, 10);
  }}

fun hide_message_callback (text)
  {{
    global.message.sprite = NULL;
  }}

Plymouth.SetMessageFunction(display_message_callback);
Plymouth.SetHideMessageFunction(hide_message_callback);
'''


def fill(template: str) -> str:
    """Eine Vorlage mit den Werten des Designsystems darin."""
    for placeholder, value in substitutions().items():
        template = template.replace("{" + placeholder + "}", str(value))
    return template.replace("{{", "{").replace("}}", "}")


def write_script() -> None:
    """Die zwei Textdateien des Themas."""
    (THEME / "zepos.script").write_text(fill(SCRIPT), encoding="utf-8")
    (THEME / "zepos.plymouth").write_text(fill(DESCRIPTOR), encoding="utf-8")


def substitutions() -> dict[str, str]:
    """Jeder Wert, den die erzeugte Datei aus dem Designsystem bekommt.

    Als eigene Funktion und nicht als Rumpf von write_script(), damit
    tests/boot/test_plymouth.py dieselbe Ableitung noch einmal
    ausrechnen und gegen die eingecheckte Datei halten kann. Ein Test,
    der die Zahlen selbst hinschreibt, prueft seine eigene Abschrift.
    """
    # Der Abstand zwischen dem Feld und dem, was darueber und darunter
    # steht - die oberste Stufe der Abstandsleiter. Die Zeile fuer die
    # Feststelltaste kommt eine ganze Leiter tiefer, damit sie nicht als
    # zweite Zeile desselben Hinweises gelesen wird.
    gap = sizes.SPACE_LADDER[-1]
    return {
        "top": plymouth_colour(brand.PETROL),
        "bottom": plymouth_colour(brand.INK),
        "text_dim": plymouth_colour(brand.TEXT_DIM),
        "text": plymouth_colour(brand.TEXT),
        "yellow": plymouth_colour(brand.YELLOW),
        # brand.RED ist "the red that is READ" - 5,21:1 auf Petrol.
        # RED_DEEP steht daneben und ist im selben Atemzug fuer Text
        # ausgeschlossen ("borders and fills only, never text").
        "red": plymouth_colour(brand.RED),
        "font": brand.FONT_TEXT,
        "anchor": sizes.ANCHOR_PX,
        "reference": REFERENCE_HEIGHT,
        "refresh_hz": REFRESH_HZ,
        "spin_frames": SPIN_FRAMES,
        "spin_hold": SPIN_HOLD,
        "spin_loads": spin_loads(),
        # Der Innenabstand des Feldes, damit die Punkte nicht am Rand
        # kleben. Dieselbe Stufe, die das System fuer den Inhalt eines
        # Bedienelements nimmt.
        "padding": sizes.radius_px(1),
        "prompt_px": PROMPT_PX,
        "hint_px": HINT_PX,
        "gap": gap,
        "minimum": MIN_PASSPHRASE_LENGTH,
        "prompt_text": PROMPT_TEXT,
        "hint_text": HINT_TEXT,
        "caps_text": CAPS_TEXT,
        "fehler_text": FEHLER_TEXT,
        "pruefung_text": PRUEFUNG_TEXT,
        "warte_text": WARTE_TEXT,
    }


def spin_loads() -> str:
    """Die zwoelf Ladezeilen des Spinners, ausgeschrieben."""
    return "".join(
        f'spin.image[{i}] = scaled(Image("spinner-{i:02d}.png"));\n'
        for i in range(SPIN_FRAMES))


# Die sechs Saetze, die auf der Flaeche stehen.
#
# WARUM SIE HIER STEHEN UND NICHT IN po/
#     Die Uebersetzung dieses Projekts laeuft ueber gettext und
#     /usr/share/locale. In der Initramfs liegt davon genau eine Datei,
#     und die ist die niederlaendische von plymouth selbst - sie steht
#     dort als Anwesenheitsprobe fuer setlocale und nicht, um etwas zu
#     uebersetzen (der Absatz weiter unten misst es aus). Das Thema ist
#     eine Datei, die mkinitcpio hineinkopiert, und fuer dessen Saetze
#     kennt Plymouth keinen Katalog. Ein Satz, der hier uebersetzt
#     aussehen soll, muesste beim Erzeugen der Initramfs eingesetzt
#     werden - also auf der Zielmaschine, aus deren locale.conf.
#
#     Das ist machbar und heute nicht gebaut. ZepOS liefert einen
#     deutschen Assistenten aus, der Nutzer waehlt dort seine Belegung,
#     und der Satz hier ist derselbe, den er dort gelesen hat. Wenn ZepOS
#     eine zweite Sprache bekommt, ist DIES die Stelle, die nachzieht -
#     und tests/boot/test_plymouth.py haelt fest, dass es dann
#     auffaellt.
PROMPT_TEXT = "Passphrase der Platte"
HINT_TEXT = ("Tastaturbelegung wie bei der Installation – "
             "y und z liegen dort, wo Sie sie gesetzt haben.")
CAPS_TEXT = "Feststelltaste ist an"

# Und die drei, die der Nutzer am 16.08.2026 verlangt hat.
#
# "falsch" und nicht "ungueltig": es gibt hier nur einen Grund, aus dem
# cryptsetup ablehnt, und der Nutzer soll nicht ueberlegen, ob seine
# Passphrase vielleicht ein verbotenes Zeichen enthaelt. Und "noch
# einmal" statt "erneut", weil die Flaeche zu dem Menschen spricht, der
# gerade davorsitzt.
FEHLER_TEXT = "Passphrase falsch – bitte noch einmal."

# Was waehrend der Rechnung ueber und unter dem Feld steht. Der zweite
# Satz ist die Erklaerung fuer die zehn Sekunden - ohne ihn ist ein
# Spinner nur die Auskunft, dass etwas laeuft, und nicht die, dass das
# so lange dauern darf.
PRUEFUNG_TEXT = "Passphrase wird geprüft"
WARTE_TEXT = "Das dauert einen Moment."

# Jeder Satz, der auf der Flaeche landet, an einer Stelle.
#
# Nicht als Bequemlichkeit: tests/boot/test_plymouth.py laeuft diese
# Liste ab, und ein Satz, der hier fehlte, entzoege sich jeder Pruefung.
# Ein zweiter Test haelt deshalb dagegen, dass jeder von ihnen wirklich
# in der erzeugten Datei steht.
SICHTBARE_SAETZE = (PROMPT_TEXT, HINT_TEXT, CAPS_TEXT, FEHLER_TEXT,
                    PRUEFUNG_TEXT, WARTE_TEXT)

# UND SEIT DEM 17.08.2026 SCHREIBEN SIE "ü" UND "–" - MIT NETZ DARUNTER.
#
# Bis dahin stand hier "geprueft" und ein Bindestrich als
# Gedankenstrich, und beides war keine Nachlaessigkeit, sondern das
# einzige, was ankam: Plymouth ZEICHNETE das U+00FC nicht, es
# VERSCHLUCKTE es. Auf dem Schirm stand "Passphrase wird geprft" - ohne
# Kaestchen, ohne Luecke. Die Kette dahinter, am 17.08.2026 erst am
# Binaercode und dann viermal am Schirm gemessen:
#
#   1. Die Schrift kann es. usr/lib/initcpio/install/plymouth streicht
#      in Zeile 9 die Zahl von der Font-Zeile des Deskriptors, gibt den
#      Rest in Zeile 10 an `fc-match -f %{file}` und legt das Ergebnis
#      in Zeile 49 als /usr/share/fonts/Plymouth.ttf in die Initramfs.
#      Diese Datei ist dort 460324 Bytes gross, heisst in ihrer
#      name-Tabelle "Roboto" und fuehrt U+00FC in ihrer cmap als Glyph
#      2333 (U+00E4 2312, U+00F6 2329, U+00C4 2285, U+00D6 2302,
#      U+00DC 2306, U+00DF 134, U+2013 1118, U+201E 1128, U+201C 1126,
#      U+2026 1136). Die Tabelle steht in tests/boot/test_plymouth.py,
#      und der Test laesst nur Zeichen zu, die darin stehen.
#
#   2. Der Zeichner dekodiert aber ueber das GEBIETSSCHEMA und nicht als
#      UTF-8. usr/lib/plymouth/label-freetype.so laeuft die Zeichenkette
#      zwar mit ply_utf8_string_iterator_next ab, schiebt jedes Stueck
#      dann aber bei 0x26de durch `mbrtowc`, bevor es bei 0x2709 in
#      FT_Load_Char geht.
#
#   3. Und das Gebietsschema wurde nie gesetzt. plymouthd ruft
#      setlocale(LC_ALL, "") bei 0x53e9 - aber nur, wenn
#      ply_file_exists() bei 0x53d3 die Datei bejaht, deren Pfad bei
#      .rodata 0x1f100 steht:
#
#          /usr/share/locale/nl/LC_MESSAGES/plymouth.mo
#
#      In der Initramfs lag kein /usr/share/locale, kein locale-archive
#      und keine locale.conf. Also fiel der Aufruf aus, plymouthd blieb
#      im Gebietsschema "C" (Zeichensatz ANSI_X3.4-1968), und mbrtowc
#      konnte 0xC3 nicht lesen.
#
# VIER LAEUFE IN QEMU, jeder mit Bild belegt, und erst der vierte hat es
# gebracht - jedes einzelne Stueck ist noetig:
#
#      nur "ü" im Thema                          -> "geprft"
#      "ü" + LC_ALL=C.UTF-8                      -> "geprft"
#      "ü" + LC_ALL + plymouth.mo                -> "geprft"
#      "ü" + LC_ALL + .mo + /usr/lib/locale/     -> "geprüft"
#
# Der dritte Lauf ist der lehrreiche: setlocale LIEF, fand aber nichts
# zu laden. "C.UTF-8" ist in dieser glibc nicht eingebaut - die
# Zeichenkette kommt in der libc.so.6 der Initramfs kein einziges Mal
# vor; das Gebietsschema liegt als Daten unter /usr/lib/locale/C.utf8
# (12 Dateien, zusammen 374805 Bytes, davon 369120 LC_CTYPE).
#
# WER DAS TRAEGT: installer/core/translate.py, PLYMOUTH_COMMAND. Der
# Haken `zepos-locale` (src/boot/initcpio/) setzt LC_ALL, bevor
# plymouthd startet, und die zwei Datenstuecke gehen ueber die
# FILES-Zeile. Preis im fertigen Abbild: 40934 Bytes, also 41 KB auf
# 20 MB (13076810 -> 13117744, einmal ohne und einmal mit den Dateien
# gepackt).
#
# UND DAS NETZ: fehlt dort auch nur eines der Stuecke, dann baut der
# Befehl die Initramfs GAR NICHT um und die Abfrage bleibt die englische
# Textzeile. Das ist die richtige Reihenfolge der Uebel - ein Thema mit
# "ü" auf einer Initramfs ohne Gebietsschema zeigte "geprft", also
# weniger als die Zeile, die es ersetzt.
#
# WAS HIER TROTZDEM ASCII BLEIBT: die Kommentare, auch in der erzeugten
# Datei. Sie sind Quelltext, niemand sieht sie beim Starten, und solange
# die einzigen hohen Bytes im Thema in den Saetzen unten stehen, ist mit
# einem Blick zu sehen, welcher Text auf den Schirm geht.

# Nur fuer den Kommentar in der erzeugten Datei.
MIN_PASSPHRASE_LENGTH = 12


def main() -> int:
    for tool in ("magick", "rsvg-convert"):
        require(tool)
    if not LOGO_SVG.is_file():
        sys.exit(f"make-plymouth-theme.py: {LOGO_SVG} fehlt")

    THEME.mkdir(parents=True, exist_ok=True)
    render_logo()
    render_field()
    render_bullet()
    render_spinner()
    write_script()

    print("geschrieben:")
    for path in sorted(THEME.iterdir()):
        print(f"  {path.relative_to(REPO)}  {path.stat().st_size} Bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
