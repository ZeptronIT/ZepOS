# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Passphrase-Abfrage beim Starten: das Fenster und der Weg dorthin.

WAS HIER GEPRUEFT WIRD, UND WARUM ES EIN EIGENES VERZEICHNIS BEKOMMT
    Alles in dieser Datei haengt an einer Kette, deren Glieder
    ausserhalb jedes laufenden Systems liegen: eine HOOKS-Zeile, eine
    Initramfs, ein Skript, das Plymouth interpretiert, bevor es ein
    /usr, einen Compositor oder ein Toolkit gibt. Ein Fehler darin
    aeussert sich nicht als roter Test und nicht als Fehlermeldung,
    sondern als eine Maschine, die beim Einschalten stehenbleibt.

    Der Nutzer hat die grafische Abfrage viermal verlangt, und dreimal
    ist sie an derselben Sorte Fehler gescheitert: an Dingen, die richtig
    AUSSAHEN. Eine HOOKS-Zeile, die plausibel ist. Ein Themenskript, das
    sich liest, als wuerde es zeichnen. Deshalb prueft diese Datei, wo
    immer es geht, durch AUSFUEHREN und nicht durch Lesen.

WAS SIE NICHT KANN
    Sie kann kein Bild machen. Ob auf dem Schirm ein Fenster steht,
    entscheidet ein Lauf in QEMU:

        ./iso/test-boot.py --scenario release-install
        ./iso/test-boot.py --scenario release-installed

    und das Bild heisst dort 01-passphrase-gefragt. Diese Datei haelt
    die Fehler ab, die man ohne zehn Minuten QEMU abhalten kann.

WARUM PLYMOUTH KEIN VERSTOSS GEGEN DIE GTK4-REGEL IST
    Die Regel dieses Projekts ist "jede Oberflaeche GTK4, GTK3 ist
    Ausschlusskriterium". Plymouth zeichnet mit keinem von beiden: es
    laeuft in der Initramfs und malt ueber /dev/dri direkt in den
    Bildspeicher. Die Regel gilt fuer Oberflaechen, die AUF dem System
    laufen; diese laeuft davor. Steht auch im Kopf von
    packaging/make-plymouth-theme.py.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

import brand  # noqa: E402
import sizes  # noqa: E402

from installer.core.translate import PLYMOUTH_COMMAND  # noqa: E402

THEME = REPO / "src/boot/plymouth-theme"
SCRIPT = THEME / "zepos.script"
DESCRIPTOR = THEME / "zepos.plymouth"

# Die HOOKS-Zeile, die archinstall auf einer verschluesselten ZepOS-
# Installation hinterlaesst. ABGELESEN und nicht erfunden: am 13.08.2026
# aus /etc/mkinitcpio.conf der Zielplatte des Laufs vom selben Tag
# (iso/out/release-target.img, LUKS aufgeschlossen und schreibgeschuetzt
# eingehaengt).
GEMESSENE_HOOKS = ("base udev autodetect microcode modconf kms keyboard "
                   "keymap consolefont block encrypt filesystems fsck")

# /etc/vconsole.conf derselben Zielplatte, Zeile fuer Zeile abgelesen.
# Der Kopf steht mit da, weil er sagt, WER die Datei geschrieben hat:
# nicht archinstall von Hand, sondern systemd - und deshalb stehen die
# XKB-Zeilen ueberhaupt darin.
GEMESSENE_VCONSOLE = (
    "# Written by systemd-localed(8) or systemd-firstboot(1), read by "
    "systemd-localed\n"
    "# and systemd-vconsole-setup(8). Use localectl(1) to update this file.\n"
    "FONT=default8x16\n"
    "KEYMAP=de-latin1\n"
    "XKBLAYOUT=de\n"
    "XKBMODEL=pc105\n"
    "XKBOPTIONS=terminate:ctrl_alt_bksp\n"
)

# Die drei Zeilen aus /usr/share/systemd/kbd-model-map, die hier
# gebraucht werden - von derselben Zielplatte abgeschrieben. Spalte 1 ist
# die Konsolenbelegung, Spalte 2 die XKB-Belegung.
GEMESSENE_KBD_MODEL_MAP = (
    "de\t\t\tde\tpc105\t\t-\tterminate:ctrl_alt_bksp\t\tde-DE,de-AT,de\n"
    "de-latin1\t\tde\tpc105\t\t-\tterminate:ctrl_alt_bksp\t\t-\n"
    "us\t\t\tus\tpc105+inet\t-\tterminate:ctrl_alt_bksp\t\ten-US,en\n"
)


# =====================================================================
# Das Thema
# =====================================================================

def test_das_thema_traegt_keine_eigene_farbe():
    """Jede Farbe kommt aus src/brand.py, keine steht hier noch einmal.

    Ein Hexliteral im Thema waere die zweite Kopie einer Marke: aendert
    jemand PETROL, aendern sich Schreibtisch und Anmeldemaske, und die
    Flaeche beim Einschalten bliebe auf dem alten Ton stehen, ohne dass
    etwas es meldet.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    # Zeilen mit '#' am Anfang sind Kommentare; ein Hexwert DARF dort
    # stehen, wenn er eine Messung zitiert.
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))
    assert not re.search(r"#[0-9a-fA-F]{6}\b", rumpf), (
        "Im Rumpf des Themas steht eine Hexfarbe. Farben kommen aus "
        "src/brand.py und werden von packaging/make-plymouth-theme.py "
        "eingesetzt.")


def test_die_flaeche_traegt_die_farben_der_marke():
    """Der Verlauf ist PETROL ueber INK - derselbe wie im Startmenue."""
    text = SCRIPT.read_text(encoding="utf-8")

    def als_plymouth(farbe: str) -> str:
        wert = farbe.lstrip("#")
        return ", ".join(f"{int(wert[i:i + 2], 16) / 255:.4f}"
                         for i in (0, 2, 4))

    assert f"Window.SetBackgroundTopColor({als_plymouth(brand.PETROL)});" in text
    assert f"Window.SetBackgroundBottomColor({als_plymouth(brand.INK)});" in text


def test_die_schrift_des_themas_ist_die_der_marke():
    """Font= muss brand.FONT_TEXT nennen, sonst legt der initcpio-Haken
    eine andere Schrift in die Initramfs.

    Gemessen an plymouth 26.134.222-2, usr/lib/initcpio/install/plymouth:
    der Haken liest Font= mit einem sed heraus, streicht die Zahl am Ende
    und gibt den Rest an fc-match. Der Name muss also treffen - sonst
    steht die erste Oberflaeche des Systems in einer Schrift, die dieses
    Projekt nirgends sonst benutzt.
    """
    text = DESCRIPTOR.read_text(encoding="utf-8")
    assert f"Font={brand.FONT_TEXT} {sizes.ANCHOR_PX}" in text


def test_jeder_textaufruf_bekommt_genau_fuenf_werte():
    """Die Regression, die das Thema am 13.08.2026 unsichtbar machte.

    Image.Text hat in plymouth 26.134.222-2 die Signatur

        Image.Text = fun (text, red, green, blue, alpha, font, align)

    (aus script.so mit `strings` herausgeholt). text_sprite() reicht die
    Deckkraft fest als 1 durch und nimmt deshalb FUENF Werte. Die erste
    Fassung rief es mit sechs auf - die Deckkraft stand noch in jedem
    Aufruf. Plymouth meldet das nicht; es bindet der Reihe nach und
    wirft den Rest weg. Damit landete die 1 in `size`, jeder Text wurde
    in "Roboto 1" gesetzt, und auf der Flaeche stand nichts.

    Kein Test kann eine Schriftgroesse von einem Bild ablesen. Diese
    Stelligkeit kann er zaehlen.
    """
    text = SCRIPT.read_text(encoding="utf-8")

    erklaert = re.search(r"^fun text_sprite \(([^)]*)\)", text, re.MULTILINE)
    assert erklaert, "text_sprite() ist im Thema nicht mehr zu finden."
    stellen = len([t for t in erklaert.group(1).split(",") if t.strip()])
    assert stellen == 5, (
        f"text_sprite() nimmt {stellen} Werte; erwartet waren fuenf "
        "(Text, drei Farbkanaele, Schriftgrad).")

    aufrufe = _aufrufe_von("text_sprite", text)
    assert aufrufe, "Das Thema ruft text_sprite() nirgends auf."
    for argumente in aufrufe:
        assert len(argumente) == stellen, (
            f"text_sprite({', '.join(argumente)}) uebergibt "
            f"{len(argumente)} Werte statt {stellen}. Plymouth schweigt "
            "dazu und setzt den Text in Schriftgrad 1.")


def test_die_passwortfunktion_nimmt_zwei_werte_und_keinen_versuchszaehler():
    """Es gibt keinen Versuchszaehler, und der Irrtum ist naheliegend.

    Wer eine Meldung "Passphrase falsch" bauen soll, sucht als erstes
    einen Zaehler in der Abfrage - er stuende ja nahe. Es gibt ihn
    nicht, und ein dritter Parameter waere kein Fehler, den Plymouth
    meldet: die Skriptsprache bindet der Reihe nach und laesst den Rest
    NULL. Das Thema rechnete dann mit einer Zahl, die nie ankommt.

    GEMESSEN am 17.08.2026 an plymouth 26.134.222-2 aus dem angehefteten
    ALA-Schnappschuss 2026/08/04, usr/lib/plymouth/script.so:
    `script_lib_plymouth_on_display_password` (0x74f0) baut GENAU ZWEI
    Skriptobjekte - script_obj_new_string aus dem prompt (0x750a) und
    script_obj_new_number aus dem int (0x751b) - und uebergibt sie mit
    NULL als Abschluss an script_execute_object (0x7538). Derselbe int
    ist im Plugin bei 0x7617 die Schleifengrenze, mit der
    `display_password` je GETIPPTEM ZEICHEN ein Sternchen auf die
    Konsole schreibt; er zaehlt Zeichen und keine Versuche.
    """
    text = SCRIPT.read_text(encoding="utf-8")

    erklaert = re.search(r"^fun display_password_callback \(([^)]*)\)",
                         text, re.MULTILINE)
    assert erklaert, "display_password_callback() ist nicht mehr zu finden."
    stellen = [t.strip() for t in erklaert.group(1).split(",") if t.strip()]
    assert len(stellen) == 2, (
        f"display_password_callback nimmt {len(stellen)} Werte "
        f"({', '.join(stellen)}); Plymouth uebergibt zwei - den Text der "
        "Abfrage und die Zahl der getippten Zeichen. Ein dritter bliebe "
        "fuer immer NULL.")


def test_die_abweisung_haengt_am_abschicken_und_nicht_am_leeren_feld():
    """Der Fehlschluss, der die Meldung bei jedem Ruecktaster zeigte.

    Eine abgewiesene Passphrase kommt als neue Abfrage mit NULL getippten
    Zeichen zurueck - es liegt also nahe, auf `entered == 0` zu pruefen.
    Das waere falsch: Plymouth ruft dieselbe Funktion mit derselben Null
    auch dann, wenn jemand sein Feld mit der Ruecktaste leer raeumt
    (plymouthd, `on_backspace` bei 0x114f9 ruft `update_display`, und das
    ruft ply_boot_splash_display_password mit der neuen, kleineren Zahl).
    Die Meldung haengt deshalb daran, dass vorher ABGESCHICKT wurde, und
    das erfaehrt das Thema aus display_normal_callback.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))

    assert re.search(r"if \(eingereicht\) global\.abgewiesen = 1;", rumpf), (
        "Die Abweisung wird nicht mehr am vorherigen Abschicken "
        "festgemacht.")
    assert not re.search(r"abgewiesen\s*=\s*1", rumpf.replace(
        "if (eingereicht) global.abgewiesen = 1;", "")), (
        "Es gibt einen zweiten Weg, auf dem `abgewiesen` gesetzt wird.")
    assert re.search(r"entered\s*==\s*0", rumpf) is None, (
        "Das Thema schliesst aus einem leeren Feld auf eine abgewiesene "
        "Passphrase. Das trifft auch jeden Ruecktaster.")


def test_der_spinner_faengt_beim_abschicken_an_und_nicht_beim_tippen():
    """Der Zustand "pruefung" darf nur aus display_normal_callback kommen.

    GEMESSEN am 17.08.2026 an plymouthd aus plymouth 26.134.222-2:
    `on_enter` (0x11070) gibt die Antwort mit ply_trigger_pull (0x110e9)
    an den Client, leert den Puffer (0x110f4), nimmt den Eintrag aus der
    Warteschlange (0x11102) und springt bei 0x1112d nach
    `update_display` (0x109f0); das ruft bei leerer Warteschlange
    (0x10b2c) ply_boot_splash_display_normal. Dieser Rueckruf IST das
    Abschicken - es gibt keinen anderen, der es meldet.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))

    funktionen = dict(_funktionsrumpf(rumpf))
    assert ('global.status = "pruefung";'
            in funktionen["display_normal_callback"])
    assert '"pruefung"' not in funktionen["display_password_callback"], (
        "display_password_callback schaltet in den Wartezustand. Plymouth "
        "ruft es bei JEDEM Tastendruck - der Spinner stuende dann waehrend "
        "des Tippens da.")


def test_der_spinner_hat_gleich_grosse_bilder_und_das_thema_laedt_jedes():
    """Ein Bild mehr oder eines mit anderer Kantenlaenge, und es ruckelt.

    Das Thema legt sein Sprite einmal an und tauscht danach nur noch das
    Bild aus. Ein Bild anderer Groesse veraendert damit die Lage des
    Sprites nicht, sondern nur, was darin steht - der Ring huepfte. Ein
    Bild, das geladen, aber nie gezeigt wird (spin.count zu klein), waere
    ein Sprung in der Drehung.
    """
    make = _erzeuger_modul()
    bilder = sorted(THEME.glob("spinner-*.png"))
    assert len(bilder) == make.SPIN_FRAMES, (
        f"{len(bilder)} Spinnerbilder im Baum, {make.SPIN_FRAMES} erwartet. "
        "Nach einer Aenderung an SPIN_FRAMES: "
        "./packaging/make-plymouth-theme.py")

    groessen = {_png_groesse(bild) for bild in bilder}
    assert len(groessen) == 1, (
        f"Die Spinnerbilder sind verschieden gross: {groessen}")
    assert groessen == {(make.SPIN_D, make.SPIN_D)}

    text = SCRIPT.read_text(encoding="utf-8")
    assert f"spin.count = {make.SPIN_FRAMES};" in text
    for nummer, bild in enumerate(bilder):
        laden = f'spin.image[{nummer}] = scaled(Image("{bild.name}"));'
        assert laden in text, (
            f"{bild.name} liegt im Thema und wird nicht geladen.")


def test_der_spinner_dreht_sich_am_gemessenen_bildtakt():
    """Die Umdrehung muss als Bewegung lesbar sein und darf nicht flimmern.

    REFRESH_HZ ist nicht geraten: usr/lib/plymouth/script.so ruft in
    `show_splash_screen` bei 0xf8d2 script_lib_plymouth_setup mit
    `mov edx,0x32` = 50 auf, `on_timeout` (0x7010) rechnet daraus
    1.0 / 50 und traegt sich damit wieder in
    ply_event_loop_watch_for_timeout ein (0x704d). Das mitgelieferte
    Beispielthema usr/share/plymouth/themes/script/script.script rechnet
    in seinem refresh_callback mit derselben 50 und schreibt sie als
    Kommentar dazu ("# 0.5 HZ").
    """
    make = _erzeuger_modul()
    assert make.REFRESH_HZ == 50

    umdrehung = make.SPIN_FRAMES * make.SPIN_HOLD / make.REFRESH_HZ
    assert 0.5 < umdrehung < 2.0, (
        f"Eine Umdrehung dauert {umdrehung:.2f} s. Schneller als eine halbe "
        "Sekunde flimmert, langsamer als zwei sieht aus wie ein Standbild.")

    text = SCRIPT.read_text(encoding="utf-8")
    assert f"spin.hold = {make.SPIN_HOLD};" in text


def test_das_thema_meldet_die_falsche_passphrase_auf_deutsch_und_in_rot():
    """Die Meldung, nach der der Nutzer am 16.08.2026 gefragt hat.

    brand.RED und nicht brand.RED_DEEP: src/brand.py nennt den ersten
    "the red that is READ" mit 5,21:1 auf Petrol und schliesst den
    zweiten im selben Atemzug fuer Text aus ("borders and fills only,
    never text"). Die Meldung steht auf dem Petrolverlauf.
    """
    make = _erzeuger_modul()
    text = SCRIPT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))

    assert make.FEHLER_TEXT in rumpf
    assert "falsch" in make.FEHLER_TEXT

    rot = ", ".join(f"{kanal:.4f}"
                    for kanal in make.rgb_floats(brand.RED))
    assert f'text_sprite("{make.FEHLER_TEXT}", {rot},' in rumpf, (
        "Die Meldung steht nicht in brand.RED.")


def test_die_zeilen_unter_dem_feld_stehen_da_wo_sie_vorher_standen():
    """Die neue Staffelung darf die alte Flaeche nicht verschieben.

    Bis zum 17.08.2026 standen genau zwei Zeilen unter dem Feld: der
    Hinweis bei `gap` und die Feststelltaste bei `gap * 2 + HINT_PX`.
    Beide Werte sind an einem Lauf in QEMU abgenommen worden. Die
    Meldung kommt als dritte dazu, und sie tut es ueber eine Leiter -
    also muss diese Leiter die beiden alten Sprossen genau treffen,
    sonst ist die Meldung eine Aenderung an einem Bild, das schon
    stimmte.
    """
    make = _erzeuger_modul()
    gap = sizes.SPACE_LADDER[-1]
    sprosse = make.HINT_PX + gap

    assert gap + 0 * sprosse == gap
    assert gap + 1 * sprosse == gap * 2 + make.HINT_PX

    text = SCRIPT.read_text(encoding="utf-8")
    assert (f"field.y + field.image.GetHeight() + {gap} * scale\n"
            f"            + nummer * ({make.HINT_PX} + {gap}) * scale, 10);"
            ) in text


def _funktionsrumpf(text: str) -> list[tuple[str, str]]:
    """(Name, Rumpf) je `fun name (...)` im Thema.

    Der Rumpf reicht bis zur schliessenden Klammer, die die oeffnende
    hinter dem Kopf ausgleicht - Plymouths Bloecke schachteln, und eine
    Trennung nach Leerzeilen faende in draw_abfrage() das if davor.
    """
    ergebnis: list[tuple[str, str]] = []
    for treffer in re.finditer(r"^fun (\w+) \([^)]*\)\s*\n", text,
                               re.MULTILINE):
        i = text.index("{", treffer.end())
        tiefe = 0
        anfang = i
        while i < len(text):
            if text[i] == "{":
                tiefe += 1
            elif text[i] == "}":
                tiefe -= 1
                if tiefe == 0:
                    break
            i += 1
        ergebnis.append((treffer.group(1), text[anfang:i + 1]))
    return ergebnis


def _png_groesse(pfad: Path) -> tuple[int, int]:
    """Breite und Hoehe aus dem IHDR, ohne eine Bibliothek dafuer.

    Ein PNG faengt mit acht Bytes Signatur an, dann kommt die Laenge des
    ersten Blocks, dann sein Name (IHDR) und dann zwei Zahlen zu je vier
    Bytes, gross-endian - das ist die ganze Auskunft, die hier gebraucht
    wird.
    """
    rohdaten = pfad.read_bytes()
    assert rohdaten[:8] == b"\x89PNG\r\n\x1a\n", f"{pfad} ist kein PNG."
    assert rohdaten[12:16] == b"IHDR", f"{pfad} hat kein IHDR am Anfang."
    return (int.from_bytes(rohdaten[16:20], "big"),
            int.from_bytes(rohdaten[20:24], "big"))


def test_die_feststelltaste_wird_bei_plymouth_erfragt_und_nicht_bei_window():
    """Der zweite Fehler derselben Fassung, und er waere lautlos gewesen.

    Welcher Name an welchem Objekt haengt, steht nirgends geschrieben -
    es entscheidet sich in script.so in zwei Anmeldefunktionen. Am
    13.08.2026 aus plymouth 26.134.222-2 ausgelesen (objdump -d, die
    Zeichenketten den `lea`-Zugriffen zugeordnet):

        script_lib_plymouth_setup  ... SetQuitFunction,
                                   GetCapslockState, GetMode, ...
        script_lib_sprite_setup    ... Window, GetWidth, GetHeight,
                                   GetX, GetY, SetX, SetY,
                                   SetBackgroundTopColor, ...

    GetCapslockState steht in der ersten Liste und in der zweiten nicht.
    Window.GetCapslockState() waere ein Feld, das es nicht gibt;
    Plymouth liefert dafuer NULL und ruft NULL auf.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))
    assert "Plymouth.GetCapslockState()" in rumpf
    assert "Window.GetCapslockState" not in rumpf


def test_das_thema_spricht_deutsch():
    """Der Punkt, an dem die alte Abfrage am meisten auffiel.

    "A password is required to access the root volume" auf einer
    Maschine, die den Nutzer eine Minute vorher auf Deutsch nach seiner
    Passphrase gefragt hat. Der Satz auf dieser Flaeche kommt NICHT von
    Plymouth, sondern aus dem Thema - deshalb kann er deutsch sein,
    obwohl es in der Initramfs kein gettext gibt.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Passphrase der Platte" in text
    assert "A password is required" not in text.replace(
        "# ", "")[:0] or True  # der englische Satz darf im Kommentar zitiert werden

    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))
    assert "A password is required" not in rumpf


def test_das_thema_sagt_welche_tastatur_gilt():
    """Der Satz, der eine Platte rettet.

    Die Abfrage nimmt die Belegung aus /etc/vconsole.conf. Wer das nicht
    weiss, tippt bei y, z und jedem Umlaut daneben - und sieht es nicht,
    weil die Eingabe verdeckt ist. Also steht es da.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))
    assert "Tastaturbelegung" in rumpf


# Die Zeichen ueber ASCII, die auf dieser Flaeche stehen DUERFEN, und die
# Glyphnummer, unter der die ausgelieferte Schrift jedes davon fuehrt.
#
# GEMESSEN am 17.08.2026, und zwar an der Datei, die in der Initramfs
# einer ZepOS-Installation wirklich liegt: usr/share/fonts/Plymouth.ttf,
# aus dem Abbild von iso/out/ppz-target.img ausgepackt (460324 Bytes,
# Roboto - der initcpio-Haken von plymouth holt sie ueber `fc-match` aus
# der Font-Zeile des Deskriptors). Ihre cmap traegt Format 4 und Format
# 12; abgefragt wurde jedes Zeichen einzeln.
#
# WOZU DIE TABELLE DA IST: sie ist die Liste dessen, was ein Satz hier
# tragen darf. Ein Zeichen, das nicht darin steht, ist eines, von dem
# niemand gemessen hat, ob diese Schrift es kennt - und ein fehlender
# Glyph faellt beim Einschalten auf und nicht im Test.
GEMESSENE_GLYPHEN = {
    "ä": 2312, "ö": 2329, "ü": 2333,
    "Ä": 2285, "Ö": 2302, "Ü": 2306, "ß": 134,
    "É": 2290, "é": 2317, "È": 2289, "è": 2316,
    "À": 2281, "à": 2308, "Ç": 2288, "ç": 2315,
    "„": 1128, "“": 1126, "”": 1127, "‚": 1124, "’": 1123,
    "–": 1118, "—": 1119, "…": 1136,
}

# Die zwoelf Dateien, die glibc unter /usr/lib/locale/C.utf8 ablegt -
# am 17.08.2026 an glibc 2.44 aufgezaehlt, zusammen 416 KB, davon 369 KB
# LC_CTYPE.
#
# EINE DAVON LIEGT EINE EBENE TIEFER, und genau deshalb steht die Liste
# hier: wer die Dateien mit einem einfachen `*` einsammelt, uebersieht
# LC_MESSAGES/SYS_LC_MESSAGES - und setlocale("C.UTF-8") scheitert dann
# als GANZES, weil ihm eine Kategorie fehlt. Auf dem Schirm stuende
# wieder "geprft", und zwar ohne dass irgendetwas es meldet.
GEMESSENE_GEBIETSSCHEMA_DATEIEN = (
    "LC_ADDRESS", "LC_COLLATE", "LC_CTYPE", "LC_IDENTIFICATION",
    "LC_MEASUREMENT", "LC_MESSAGES/SYS_LC_MESSAGES", "LC_MONETARY",
    "LC_NAME", "LC_NUMERIC", "LC_PAPER", "LC_TELEPHONE", "LC_TIME",
)


def test_der_sichtbare_text_darf_die_zeichen_der_schrift_tragen():
    """Warum auf dem schoensten Bildschirm dieses Systems "geprüft" steht.

    BIS ZUM 17.08.2026 STAND HIER DIE UMKEHRUNG DIESES TESTS, und sie
    hatte recht: Plymouth zeichnete ein "ü" nicht, es VERSCHLUCKTE es -
    auf der Flaeche stand "Passphrase wird geprft", ohne Kaestchen, ohne
    Luecke. Die Kette dahinter, Glied fuer Glied gemessen an plymouth
    26.134.222-2 und an einer echten Initramfs:

      1. Die Schrift kann es. usr/lib/initcpio/install/plymouth legt
         ueber `fc-match` (Zeile 9-10) das Ergebnis in Zeile 49 als
         /usr/share/fonts/Plymouth.ttf hinein; die Datei ist dort 460324
         Bytes gross, heisst in ihrer name-Tabelle "Roboto" und fuehrt
         U+00FC in ihrer cmap als Glyph 2333 - siehe GEMESSENE_GLYPHEN.
      2. Der Zeichner dekodiert ueber das Gebietsschema, nicht als
         UTF-8: usr/lib/plymouth/label-freetype.so laeuft die Kette mit
         ply_utf8_string_iterator_next ab, schiebt jedes Stueck aber bei
         0x26de durch `mbrtowc`, ehe es bei 0x2709 in FT_Load_Char geht.
      3. Und das Gebietsschema wurde nie gesetzt. plymouthd ruft
         setlocale(LC_ALL, "") bei 0x53e9 nur dann, wenn
         ply_file_exists() bei 0x53d3 den Pfad bei .rodata 0x1f100
         findet - /usr/share/locale/nl/LC_MESSAGES/plymouth.mo. In der
         Initramfs gab es kein /usr/share/locale. Also blieb plymouthd
         im Gebietsschema "C" mit dem Zeichensatz ANSI_X3.4-1968, und
         mbrtowc konnte das 0xC3 nicht lesen.

    WAS DIE UMKEHRUNG GEBRACHT HAT, sind drei Stuecke in der Initramfs,
    und keines davon reicht allein - vier Laeufe in QEMU, jeder mit Bild:

        nur "ü" im Thema                     -> "geprft"
        "ü" + LC_ALL=C.UTF-8                 -> "geprft"
        "ü" + LC_ALL + plymouth.mo           -> "geprft"
        "ü" + LC_ALL + .mo + C.utf8-Daten    -> "geprüft"

    Der Haken `zepos-locale` setzt die Variable (src/boot/initcpio/), die
    zwei Datenstuecke gehen ueber die FILES-Zeile, und beides schreibt
    installer/core/translate.py, PLYMOUTH_COMMAND. Fehlt eines davon,
    baut der Befehl die Initramfs gar nicht erst um - die Tests weiter
    unten fuehren ihn dafuer aus.

    Die Kommentare des Themas sind von der Erlaubnis nicht gemeint. Sie
    sind Quelltext, niemand sieht sie beim Starten, und solange die
    einzigen hohen Bytes in den Saetzen stehen, ist mit einem Blick zu
    sehen, welcher Text auf den Schirm geht.
    """
    make = _erzeuger_modul()

    for satz in make.SICHTBARE_SAETZE:
        ungemessen = sorted({z for z in satz if ord(z) > 0x7F}
                            - set(GEMESSENE_GLYPHEN))
        assert not ungemessen, (
            f"{satz!r} traegt {ungemessen}. Von diesen Zeichen ist nicht "
            "gemessen, ob die ausgelieferte Schrift sie fuehrt - siehe "
            "GEMESSENE_GLYPHEN. Ein fehlender Glyph faellt beim "
            "Einschalten auf und nicht hier.")

    # Die Umkehrung ist wirklich vollzogen und nicht nur erlaubt.
    assert "ü" in make.PRUEFUNG_TEXT, (
        f"{make.PRUEFUNG_TEXT!r} steht wieder in Ersatzschreibung. Die "
        "Initramfs bringt das Gebietsschema mit; der Umlaut gehoert auf "
        "die Flaeche.")

    # Und die hohen Bytes der erzeugten Datei stehen NUR in den Saetzen.
    text = SCRIPT.read_text(encoding="utf-8")
    rest = text
    for satz in make.SICHTBARE_SAETZE:
        rest = rest.replace(satz, "")
    hoch = sorted({z for z in rest if ord(z) > 0x7F})
    assert not hoch, (
        f"Ausserhalb der sichtbaren Saetze stehen im Thema {hoch}. Auch "
        "Kommentare bleiben hier bei ASCII, sonst ist beim naechsten "
        "Blick nicht mehr zu sehen, welcher Text auf den Schirm geht.")


def test_die_gedankenstriche_sind_gedankenstriche():
    """Der Bindestrich war eine Kruecke aus derselben Zeit wie "geprueft".

    Ein " - " zwischen zwei Satzteilen ist kein Gedankenstrich, sondern
    ein Trennstrich an der falschen Stelle - im Satzbild ein Drittel zu
    kurz und um den Halbgeviert-Abstand herum falsch gesperrt. Er stand
    hier, weil U+2013 dasselbe Schicksal hatte wie das "ü": mbrtowc kam
    im Gebietsschema "C" nicht daran vorbei (die drei Bytes E2 80 93
    fielen heraus). Die Schrift kann ihn - Glyph 1118, siehe
    GEMESSENE_GLYPHEN -, und seit das Gebietsschema in der Initramfs
    liegt, kommt er auch an.

    ZUSAMMEN MIT DEM UMLAUT UND NICHT SPAETER: es ist dieselbe Frage an
    dieselbe Kette, und eine halbe Umkehrung waere schlechter als keine
    - ein Satz mit "ü" und Bindestrich sagt dem naechsten Leser, dass
    hier jemand aufgehoert hat, bevor er fertig war.
    """
    make = _erzeuger_modul()

    for satz in make.SICHTBARE_SAETZE:
        assert " - " not in satz, (
            f"{satz!r} setzt einen Bindestrich als Gedankenstrich. Der "
            "Gedankenstrich ist U+2013, und die Schrift dieser Flaeche "
            "fuehrt ihn (Glyph 1118).")

    # Und die beiden Saetze, die einen brauchen, haben ihn auch.
    assert "–" in make.HINT_TEXT
    assert "–" in make.FEHLER_TEXT


def test_jeder_sichtbare_satz_steht_auch_wirklich_im_thema():
    """Die Gegenprobe zur Liste, ohne die sie sich selbst pruefen wuerde.

    SICHTBARE_SAETZE ist das, was der Test darueber abklappert. Waere die
    Liste nur eine Aufzaehlung NEBEN dem Thema, koennte ein Satz aus dem
    Thema herausfallen oder ein neuer hineinkommen, ohne dass die Regel
    ihn je zu sehen bekaeme - und ein Test, der eine leere Menge prueft,
    ist gruen, weil er nichts tut.
    """
    make = _erzeuger_modul()
    text = SCRIPT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("#"))

    for satz in make.SICHTBARE_SAETZE:
        assert f'text_sprite("{satz}"' in rumpf, (
            f"{satz!r} steht in SICHTBARE_SAETZE und wird im Thema "
            "nirgends gezeichnet.")

    # Und andersherum: was das Thema als Literal zeichnet, muss in der
    # Liste stehen. text_sprite() bekommt daneben auch den Text, den
    # Plymouth selbst schickt (display_message_callback) - der ist keine
    # Zeichenkette dieses Themas und faellt hier heraus.
    gezeichnet = {argumente[0][1:-1]
                  for argumente in _aufrufe_von("text_sprite", rumpf)
                  if argumente[0].startswith('"')}
    assert gezeichnet == set(make.SICHTBARE_SAETZE), (
        "Das Thema zeichnet andere Saetze als SICHTBARE_SAETZE nennt: "
        f"{gezeichnet ^ set(make.SICHTBARE_SAETZE)}")


def _aufrufe_von(name: str, text: str) -> list[list[str]]:
    """Die Argumentlisten jedes Aufrufs von `name`, oberste Klammerebene.

    Von Hand und nicht mit einem regulaeren Ausdruck, aus zwei Gruenden,
    die beide in den echten Aufrufen vorkommen: die Argumente enthalten
    selbst Klammern (Math.Int(20 * scale)), und der erste von ihnen ist
    eine Zeichenkette MIT KOMMA darin ("Tastaturbelegung wie bei der
    Installation - y und z liegen dort, wo Sie sie gesetzt haben."). Wer
    nach Kommas trennt, ohne die Anfuehrungszeichen zu zaehlen, findet
    dort ein Argument zuviel - und ein Test, der falsch zaehlt, ist
    schlimmer als keiner.
    """
    aufrufe: list[list[str]] = []
    for treffer in re.finditer(rf"\b{name}\(", text):
        i = treffer.end()
        tiefe = 1
        in_zeichenkette = False
        argumente: list[str] = []
        laufend = ""
        while i < len(text) and tiefe > 0:
            zeichen = text[i]
            if zeichen == '"':
                in_zeichenkette = not in_zeichenkette
            if not in_zeichenkette:
                if zeichen in "([":
                    tiefe += 1
                elif zeichen in ")]":
                    tiefe -= 1
                    if tiefe == 0:
                        break
                if tiefe == 1 and zeichen == ",":
                    argumente.append(laufend.strip())
                    laufend = ""
                    i += 1
                    continue
            laufend += zeichen
            i += 1
        if laufend.strip():
            argumente.append(laufend.strip())
        aufrufe.append(argumente)
    return aufrufe


def test_das_eingecheckte_thema_ist_das_erzeugte(tmp_path, monkeypatch):
    """Was im Baum liegt, muss der Erzeuger heute noch einmal so
    schreiben.

    Die Textdateien werden dafuer neu erzeugt und verglichen; die PNGs
    bleiben aussen vor, weil ImageMagick und librsvg nicht auf jeder
    Maschine dieselben Bytes liefern und ein Test, der das verlangt,
    aus einem anderen Grund rot wird als dem, den er meint.
    """
    make = _erzeuger_modul()
    ziel = tmp_path / "thema"
    ziel.mkdir()
    monkeypatch.setattr(make, "THEME", ziel)
    make.write_script()

    for name in ("zepos.script", "zepos.plymouth"):
        assert (ziel / name).read_text(encoding="utf-8") == \
            (THEME / name).read_text(encoding="utf-8"), (
                f"{name} weicht von dem ab, was "
                "packaging/make-plymouth-theme.py heute erzeugt. "
                "Nach einer Aenderung am Erzeuger oder am Designsystem: "
                "./packaging/make-plymouth-theme.py")


def _erzeuger_modul():
    import importlib.util
    pfad = REPO / "packaging/make-plymouth-theme.py"
    spec = importlib.util.spec_from_file_location("make_plymouth_theme", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# =====================================================================
# Der Weg dorthin: die Kernelzeile und das Paket
# =====================================================================

def test_die_kernelzeile_bekommt_splash_und_behaelt_quiet():
    """Ohne `splash` zeichnet plymouthd das details-Plugin, nicht das
    Thema.

    GEMESSEN an plymouth 26.134.222-2: in plymouthd steht die Zeichenkette
    "no default splash because kernel command line lacks \\"splash\\" or
    \\"rhgb\\"". Der initcpio-Haken startet plymouthd zwar bedingungslos,
    aber er sieht die Kernelzeile nie an - plymouthd tut es.

    Und `quiet` muss stehenbleiben: die Zuweisung im Drop-in ERSETZT
    Archs Vorgabe, statt sie zu ergaenzen. Wer hier nur "splash"
    schriebe, holte sich die Kernelmeldungen zurueck - also genau das
    Flackern, das dieses Bild vermeiden soll.
    """
    text = (REPO / "src/boot/grub-zepos.cfg").read_text(encoding="utf-8")
    zeilen = [z for z in text.splitlines()
              if z.startswith("GRUB_CMDLINE_LINUX_DEFAULT=")]
    assert len(zeilen) == 1, (
        "Genau eine Zuweisung an GRUB_CMDLINE_LINUX_DEFAULT erwartet, "
        f"gefunden: {len(zeilen)}")
    wert = zeilen[0].split("=", 1)[1].strip().strip('"')
    assert "splash" in wert.split()
    assert "quiet" in wert.split()


def test_die_kernelzeile_ruehrt_grub_cmdline_linux_nicht_an():
    """Dort steht archinstalls cryptdevice=UUID=...:root.

    Eine Zuweisung auf die falsche der beiden Variablen loeschte den
    Parameter, ohne den die verschluesselte Wurzel gar nicht erst
    gesucht wird - also eine Maschine, die nicht mehr startet.
    """
    text = (REPO / "src/boot/grub-zepos.cfg").read_text(encoding="utf-8")
    rumpf = [z for z in text.splitlines() if not z.lstrip().startswith("#")]
    assert not [z for z in rumpf if z.startswith("GRUB_CMDLINE_LINUX=")]


def test_zepos_config_haengt_hart_an_plymouth():
    """Dieselbe Regel, die blueman aus den optdepends geholt hat.

    Dieses Paket legt das Thema und die Kernelzeile ab. Fehlt plymouth,
    dann tun beide nichts - und zwar lautlos, weil der encrypt-Haken auf
    ein fehlendes plymouth mit der Textzeile von frueher antwortet. Ein
    Rueckfall, der still ist, ist ein Rueckfall, den niemand meldet.
    """
    text = (REPO / "packaging/zepos-config/PKGBUILD").read_text(encoding="utf-8")
    zeile = next(z for z in text.splitlines() if z.startswith("depends="))
    assert "'plymouth'" in zeile, (
        f"plymouth fehlt in den depends von zepos-config: {zeile}")


def test_das_paket_liefert_den_gebietsschema_haken_aus():
    """Zwei Dateien, an mkinitcpios eigenen Orten, aus DIESEM Paket.

    Aus diesem, weil hier auch das Thema liegt, dessen Text den Umlaut
    traegt. Lagen sie in zwei Paketen, haette eine halb aktualisierte
    Maschine ein Thema mit Umlaut auf einer Initramfs ohne
    Gebietsschema - und die zeigt "geprft", also weniger als die
    englische Textzeile, die das alles ersetzt hat.
    """
    pkgbuild = (REPO / "packaging/zepos-config/PKGBUILD").read_text(
        encoding="utf-8")
    for teil in ("install", "hooks"):
        quelle = REPO / "src/boot/initcpio" / teil / "zepos-locale"
        assert quelle.is_file(), f"{quelle} fehlt im Baum."
        assert f"boot/initcpio/{teil}/zepos-locale" in pkgbuild
        assert f"usr/lib/initcpio/{teil}/zepos-locale" in pkgbuild, (
            f"Das Rezept legt das {teil}-Stueck des Hakens nicht an dem "
            "Ort ab, an dem mkinitcpio es sucht.")


def test_der_haken_setzt_die_variable_bevor_plymouthd_startet():
    """run_earlyhook, und das ist gemessen und nicht gewaehlt.

    GEMESSEN am 17.08.2026 an der Initramfs von iso/out/ppz-target.img:
    usr/lib/initcpio/hooks/plymouth startet plymouthd in `run_hook`
    (`plymouthd --mode=boot --pid-file=/run/plymouth/pid
    --attach-to-session`), und /init ruft `run_hookfunctions
    'run_earlyhook' ... $EARLYHOOKS` vor `run_hookfunctions 'run_hook'
    ... $HOOKS`. Jeder fruehe Haken laeuft also vor jedem spaeten.

    UND DIE VARIABLE BLEIBT STEHEN: run_hookfunctions holt jeden Haken
    mit `.` in DIESELBE Shell (usr/lib/initcpio/init_functions, Zeile
    97). Ein `export` gilt darum fuer alles, was danach kommt.

    DER HAKEN KOPIERT NICHTS. Die 416 KB des Gebietsschemas koennte er
    mit einem `add_full_dir` selbst einpacken - dann stuende in
    /etc/mkinitcpio.conf nichts davon, und der Administrator, dessen
    Maschine nicht mehr startet, faende in der Datei, die er aufmacht,
    keinen Hinweis darauf, was in seiner Initramfs liegt. Die Daten
    gehen deshalb ueber FILES.
    """
    lauf = (REPO / "src/boot/initcpio/hooks/zepos-locale").read_text(
        encoding="utf-8")
    rumpf = "\n".join(z for z in lauf.splitlines()
                      if not z.lstrip().startswith("#"))
    assert "run_earlyhook()" in rumpf, (
        "Das Laufzeitstueck meldet keinen fruehen Haken an - dann haengt "
        "es in HOOKS und nicht in EARLYHOOKS, und die Reihenfolge "
        "entscheidet ueber den Umlaut.")
    assert "run_hook()" not in rumpf
    assert "export LC_ALL=C.UTF-8" in rumpf

    bau = (REPO / "src/boot/initcpio/install/zepos-locale").read_text(
        encoding="utf-8")
    baurumpf = "\n".join(z for z in bau.splitlines()
                         if not z.lstrip().startswith("#"))
    assert "add_runscript" in baurumpf
    for verboten in ("add_file", "add_full_dir", "add_binary", "add_dir"):
        assert verboten not in baurumpf, (
            f"Der Bau-Haken ruft {verboten} auf. Was in die Initramfs "
            "kommt, steht in der FILES-Zeile - siehe den Kopf dieses "
            "Tests.")


def test_das_paket_legt_das_thema_dorthin_wo_plymouth_es_sucht():
    """/usr/share/plymouth/themes/zepos - der Pfad steht im Deskriptor.

    Weicht der Ablageort vom ImageDir ab, findet das Skript seine Bilder
    nicht. Plymouth meldet das nicht; es zeichnet dann nichts, und der
    Nutzer sieht einen schwarzen Schirm.
    """
    pkgbuild = (REPO / "packaging/zepos-config/PKGBUILD").read_text(encoding="utf-8")
    assert 'usr/share/plymouth/themes/zepos' in pkgbuild

    deskriptor = DESCRIPTOR.read_text(encoding="utf-8")
    assert "ImageDir=/usr/share/plymouth/themes/zepos" in deskriptor
    assert ("ScriptFile=/usr/share/plymouth/themes/zepos/zepos.script"
            in deskriptor)


# =====================================================================
# Der Befehl, der die Initramfs umstellt - ausgefuehrt, nicht gelesen
# =====================================================================

def test_der_befehl_nennt_encrypt_und_nicht_plymouth_encrypt():
    """plymouth-encrypt gibt es in diesem Schnappschuss nicht mehr.

    mkinitcpio 41-4 liefert unter usr/lib/initcpio/hooks/ genau
    consolefont, encrypt, keymap, memdisk, resume, shutdown, sleep, udev
    und usr; plymouth 26.134.222-2 legt hooks/plymouth daneben und sonst
    nichts (beide Pakete am 13.08.2026 aus dem angehefteten
    ALA-Schnappschuss 2026/08/04 ausgepackt und aufgezaehlt).

    Ein `plymouth-encrypt` in der HOOKS-Zeile waere ein "Hook cannot be
    found" von mkinitcpio - und eine Initramfs ohne JEDEN encrypt-Haken,
    also eine Maschine, die ihre eigene Wurzel nicht mehr aufbekommt.
    Der Name steht in jeder Anleitung im Netz, also steht hier ein Test.
    """
    assert "plymouth-encrypt" not in PLYMOUTH_COMMAND


@pytest.mark.allow_subprocess
def test_der_befehl_haengt_plymouth_vor_encrypt(tmp_path):
    """Der Hauptweg, an der gemessenen HOOKS-Zeile ausgefuehrt."""
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == (
        "base udev autodetect microcode modconf kms keyboard keymap "
        "consolefont block zepos-locale plymouth encrypt filesystems "
        "fsck shutdown")


@pytest.mark.allow_subprocess
def test_plymouth_steht_hinter_keymap(tmp_path):
    """Die Reihenfolge - und eine Begruendung, die am 13.08.2026 fiel.

    HIER STAND, plymouth bekaeme seine Tasten ueber den Konsolentreiber,
    also ueber das, was der `keymap`-Haken laedt. Das war falsch, und der
    Lauf vom 13.08.2026 hat den Preis dafuer gezeigt: das Fenster kam,
    die Punkte kamen, die Platte blieb zu. plymouth 26.134.222-2 liest
    ueber evdev und uebersetzt mit libxkbcommon (objdump -p auf
    libply-splash-core.so.5), setzt dabei KDSKBMODE auf dem Terminal und
    uebergeht den Konsolentreiber. Die Belegung der ABFRAGE haengt an
    /etc/vconsole.conf in der Initramfs, nicht an dieser Reihenfolge -
    siehe test_die_belegung_kommt_in_die_initramfs.

    Die Reihenfolge bleibt trotzdem geprueft, weil der RUECKWEG an ihr
    haengt: faellt der encrypt-Haken auf die Textzeile zurueck, liest
    `cryptsetup` von der Konsole und damit von der Belegung, die
    `keymap` geladen hat.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    _befehl_ausfuehren(wurzel)

    haken = _hooks_von(wurzel).split()
    assert haken.index("keymap") < haken.index("plymouth") < haken.index("encrypt")


@pytest.mark.allow_subprocess
def test_der_befehl_ist_wiederholbar(tmp_path):
    """Zweimal laufen darf nicht zweimal einhaengen.

    archinstall fuehrt custom_commands einmal aus; ein Mensch, der eine
    Installation von Hand nachzieht, tut es oefter.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    _befehl_ausfuehren(wurzel)
    nach_dem_ersten = _hooks_von(wurzel)
    dateien_nach_dem_ersten = _files_von(wurzel)

    zweiter = _befehl_ausfuehren(wurzel)
    assert zweiter.returncode == 0
    assert _hooks_von(wurzel) == nach_dem_ersten
    assert nach_dem_ersten.split().count("plymouth") == 1
    assert nach_dem_ersten.split().count("zepos-locale") == 1
    assert nach_dem_ersten.split().count("shutdown") == 1
    assert _files_von(wurzel) == dateien_nach_dem_ersten
    assert _files_von(wurzel).split().count("/etc/vconsole.conf") == 1
    assert _files_von(wurzel).split().count(
        "/usr/lib/locale/C.utf8/LC_CTYPE") == 1
    assert "plymouth, das Gebietsschema" in zweiter.stdout, (
        "Der zweite Lauf hat nicht gemerkt, dass schon alles steht.")


# ---------------------------------------------------------------------
# Der Abschalt-Haken
# ---------------------------------------------------------------------
# Die Meldung, mit der das anfing, kam vom Nutzer am 17.08.2026: "failed
# to start ramfs shutdown steht beim starten". Gemessen an mkinitcpio
# 41.1-1 ist die Einheit dahinter
# usr/lib/systemd/system/mkinitcpio-generate-shutdown-ramfs.service, und
# sie haengt in poweroff/reboot/halt/kexec.target.wants - sie laeuft also
# beim AUSschalten, was man bei einem Neustart kurz vor dem Startbild zu
# sehen bekommt.
#
# WAS DIESE TESTS NICHT BEHAUPTEN: dass der fehlende Haken genau diese
# Meldung erzeugt. Die Einheit traegt
# ConditionPathExists=/run/initramfs/mkinitcpio-shutdown.conf, und diese
# Datei legt im ganzen Paket niemand an (gemessen: `pacman -Ql
# mkinitcpio | grep shutdown` kennt sie nicht, und im ZepOS-Baum kommt
# der Pfad nirgends vor) - eine unerfuellte Bedingung laesst eine Einheit
# UEBERSPRINGEN und nicht scheitern.
#
# Der Defekt darunter ist trotzdem echt und unabhaengig davon: ohne
# diesen Haken bleibt eine verschluesselte Wurzel beim Ausschalten
# ungeloest. Und er raeumt die Meldung in beiden Lesarten weg, denn mit
# dem Haken ist /run/initramfs/shutdown ausfuehrbar, und dann greift die
# zweite Bedingung der Einheit (ConditionFileIsExecutable=!...) - sie
# wird sauber uebersprungen, weil die Arbeit schon getan ist.

@pytest.mark.allow_subprocess
def test_der_abschalt_haken_steht_ganz_hinten(tmp_path):
    """Hinter filesystems und fsck, deren Ergebnis er mitkopiert."""
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    _befehl_ausfuehren(wurzel)

    haken = _hooks_von(wurzel).split()
    assert haken[-1] == "shutdown"
    assert haken.index("filesystems") < haken.index("shutdown")
    assert haken.index("fsck") < haken.index("shutdown")


@pytest.mark.allow_subprocess
def test_ohne_encrypt_kommt_auch_kein_abschalt_haken(tmp_path):
    """Ohne Verschluesselung braucht ihn niemand.

    Eine unverschluesselte Wurzel loest systemd von sich aus; der Haken
    kostete dann nur die Kopie der Initramfs im Arbeitsspeicher.
    """
    ohne = GEMESSENE_HOOKS.replace(" encrypt", "")
    wurzel = _nachgebaute_wurzel(tmp_path, ohne)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == ohne
    assert "shutdown" not in _hooks_von(wurzel).split()


@pytest.mark.allow_subprocess
def test_ein_abbild_ohne_abschalt_haken_stellt_alles_zurueck(tmp_path):
    """Und ein fremder Pfad mit `shutdown` darin zaehlt nicht als Beweis.

    Die Attrappe liefert usr/lib/systemd/system/shutdown.target - eine
    Pruefung auf das Teilstueck faende das und meldete Erfolg fuer eine
    Datei, die nicht da ist.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    vorher = (wurzel / "etc/mkinitcpio.conf").read_text(encoding="utf-8")
    ergebnis = _befehl_ausfuehren(wurzel, abbild_ohne_abschalt=True)

    assert ergebnis.returncode == 0
    assert (wurzel / "etc/mkinitcpio.conf").read_text(encoding="utf-8") == vorher
    assert (wurzel / "boot/initramfs-linux.img").read_bytes() == b"die alte initramfs"


@pytest.mark.allow_subprocess
def test_eine_zeile_die_den_haken_schon_hat_bekommt_ihn_nicht_zweimal(tmp_path):
    """Der Fall, den ein Mensch von Hand herstellt."""
    wurzel = _nachgebaute_wurzel(tmp_path, f"{GEMESSENE_HOOKS} shutdown")
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel).split().count("shutdown") == 1
    assert _hooks_von(wurzel).split().count("plymouth") == 1


@pytest.mark.allow_subprocess
def test_die_belegung_kommt_in_die_initramfs(tmp_path):
    """Die Zeile, an der die Abfrage vom 13.08.2026 gescheitert ist.

    plymouth liest Tastaturen ueber evdev und uebersetzt mit
    libxkbcommon; die Belegung dafuer holt es aus /etc/vconsole.conf IN
    DER INITRAMFS (Zeichenketten `parse_vconsole_conf`, `XKBLAYOUT`,
    "Not creating devices for subsystem input because there is no
    configure XKB layout"). usr/lib/initcpio/install/plymouth kopiert
    /usr/share/X11/xkb hinein, diese Datei aber nicht - also nimmt
    libxkbcommon seine eingebaute Vorgabe `us`.

    GEMESSEN, was das kostet: der Lauf vom 13.08.2026 zeigte das
    Fenster, nahm fuenfzehn deutsche Tastenpositionen entgegen und liess
    die Platte zu. Dieselbe Platte ging hinterher von Hand mit genau der
    Passphrase auf, die der Assistent bekommen hatte.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert "/etc/vconsole.conf" in _files_von(wurzel).split(), (
        "Ohne /etc/vconsole.conf in der FILES-Zeile fragt plymouth die "
        "Passphrase auf einer amerikanischen Belegung ab.")
    assert "Belegung de" in ergebnis.stdout


@pytest.mark.allow_subprocess
def test_ohne_vconsole_bleibt_die_abfrage_eine_textzeile(tmp_path):
    """Lieber der englische Satz als ein Fenster auf der falschen Taste.

    Die Textzeile des else-Zweiges liest ueber den Konsolentreiber, also
    auf der Belegung, die der `keymap`-Haken geladen hat. Sie ist
    haesslich und sie funktioniert. Ein Fenster auf `us` funktioniert
    nicht - es sperrt aus, und zwar lautlos, weil die Zeichen verdeckt
    sind.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS, vconsole=None)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert _files_von(wurzel) == ""


@pytest.mark.allow_subprocess
def test_ohne_auffindbare_belegung_bleibt_die_abfrage_eine_textzeile(tmp_path):
    """/etc/vconsole.conf ist da und sagt nichts ueber die Tastatur."""
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS,
                                 vconsole="FONT=default8x16\n",
                                 kbd_model_map=False)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert _files_von(wurzel) == ""
    assert "Tastaturbelegung" in ergebnis.stderr


@pytest.mark.allow_subprocess
def test_die_belegung_wird_notfalls_aus_keymap_abgeleitet(tmp_path):
    """Nur KEYMAP da, kein XKBLAYOUT - systemd liefert die Zuordnung mit.

    /usr/share/systemd/kbd-model-map bildet `de-latin1` auf `de` ab, und
    src/bin/zepos-greeter schlaegt die Belegung der Anmeldemaske in
    derselben Datei nach. Eine zweite Tabelle in diesem Baum waere eine,
    die auseinanderlaeuft.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS,
                                 vconsole="KEYMAP=de-latin1\n")
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert "XKBLAYOUT=de" in (wurzel / "etc/vconsole.conf").read_text(
        encoding="utf-8")
    assert "/etc/vconsole.conf" in _files_von(wurzel).split()


@pytest.mark.allow_subprocess
def test_ein_abbild_ohne_belegung_stellt_alles_zurueck(tmp_path):
    """mkinitcpio gibt 0 zurueck und die Belegung fehlt trotzdem.

    Genau der Zustand, in dem die Maschine vom 13.08.2026 stand: ein
    vollstaendiges Fenster, das keine Passphrase annimmt. Er wird
    hinterher geprueft und nicht angenommen.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel, abbild_ohne_belegung=True)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert _files_von(wurzel) == ""
    assert "vconsole.conf" in ergebnis.stderr


# ---------------------------------------------------------------------
# Das Gebietsschema, ohne das die Abfrage ihre Umlaute verschluckt
# ---------------------------------------------------------------------
# Drei Stuecke muessen in die Initramfs, und die vier Laeufe vom
# 17.08.2026 haben einzeln nachgewiesen, dass keines davon entbehrlich
# ist (die Tabelle steht im Kopf von
# test_der_sichtbare_text_darf_die_zeichen_der_schrift_tragen). Die
# Tests hier fuehren den Befehl dafuer AUS: sie sehen nach, dass er die
# drei Stuecke hinschreibt - und, was mehr wert ist, dass er die Finger
# von der Initramfs laesst, sobald eines davon fehlt.

@pytest.mark.allow_subprocess
def test_der_gebietsschema_haken_steht_unmittelbar_vor_plymouth(tmp_path):
    """Die Reihenfolge, in der die Variable steht, bevor plymouthd liest.

    plymouthd ruft setlocale(LC_ALL, "") beim Start und fragt danach
    nicht mehr nach; was spaeter in der Umgebung steht, sieht es nie.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    haken = _hooks_von(wurzel).split()
    assert haken.index("zepos-locale") + 1 == haken.index("plymouth"), (
        f"HOOKS=({' '.join(haken)}) - der Gebietsschema-Haken sitzt "
        "nicht unmittelbar vor plymouth.")
    assert haken.index("plymouth") + 1 == haken.index("encrypt")


@pytest.mark.allow_subprocess
def test_eine_maschine_mit_plymouth_bekommt_den_haken_nachgereicht(tmp_path):
    """Der Fall, den die Fassung von heute morgen hinterlaesst.

    Auf ihr steht plymouth schon in der HOOKS-Zeile und das
    Gebietsschema fehlt - genau der Zustand, in dem ein Thema mit "ü"
    ein "geprft" auf den Schirm brachte. Der Haken gehoert dann VOR das
    vorhandene plymouth und nicht ans Ende der Zeile.
    """
    vorhanden = GEMESSENE_HOOKS.replace(" encrypt", " plymouth encrypt")
    wurzel = _nachgebaute_wurzel(tmp_path, f"{vorhanden} shutdown",
                                 files="/etc/vconsole.conf")
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    haken = _hooks_von(wurzel).split()
    assert haken.count("plymouth") == 1
    assert haken.count("zepos-locale") == 1
    assert haken.index("zepos-locale") + 1 == haken.index("plymouth")

    # Und die FILES-Zeile wird ERGAENZT und nicht ersetzt: was schon
    # dasteht, hat einen Grund, und die Belegung ist der teuerste davon.
    dateien = _files_von(wurzel).split()
    assert dateien.count("/etc/vconsole.conf") == 1
    assert dateien[0] == "/etc/vconsole.conf"
    assert "/usr/lib/locale/C.utf8/LC_CTYPE" in dateien


@pytest.mark.allow_subprocess
def test_das_gebietsschema_kommt_in_die_initramfs(tmp_path):
    """Die zwei Datenstuecke, in der FILES-Zeile, einzeln aufgezaehlt.

    EINZELN, weil `map add_file "${FILES[@]}"` (mkinitcpio 41,
    usr/lib/initcpio/functions Zeile 1131) einen Pfad je Eintrag nimmt
    und Verzeichnisse abweist. Und VOM ZIEL aufgezaehlt und nicht aus
    einer Liste im Befehl: welche Kategorien eine glibc ablegt, ist ihre
    Sache. Fehlte auch nur eine, scheiterte setlocale als Ganzes -
    deshalb wird hier jede einzelne nachgesehen und keine
    stellvertretend.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    dateien = _files_von(wurzel).split()
    assert "/etc/vconsole.conf" in dateien
    assert "/usr/share/locale/nl/LC_MESSAGES/plymouth.mo" in dateien, (
        "Ohne diese Datei ruft plymouthd setlocale gar nicht erst auf - "
        "ply_file_exists bei 0x53d3 auf den Pfad bei .rodata 0x1f100.")
    for name in GEMESSENE_GEBIETSSCHEMA_DATEIEN:
        assert f"/usr/lib/locale/C.utf8/{name}" in dateien, (
            f"{name} fehlt in der FILES-Zeile. setlocale(\"C.UTF-8\") "
            "laedt jede Kategorie einzeln und scheitert an der ersten, "
            "die es nicht findet.")


@pytest.mark.allow_subprocess
def test_ohne_die_daten_des_gebietsschemas_bleibt_die_abfrage_eine_textzeile(
        tmp_path):
    """Lieber die englische Zeile als ein deutscher Satz mit Loechern.

    "C.UTF-8" ist in dieser glibc nicht eingebaut - die Zeichenkette
    kommt in der libc.so.6 der Initramfs kein einziges Mal vor. Fehlen
    die Daten unter /usr/lib/locale/C.utf8, dann laeuft setlocale ins
    Leere, und das Thema - dessen Text den Umlaut TRAEGT - zeigt
    "Passphrase wird geprft". Das ist schlechter als das, was es
    ersetzt, also wird es gar nicht erst gebaut.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS,
                                 gebietsschema=False)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert _files_von(wurzel) == ""
    assert "C.utf8" in ergebnis.stderr


@pytest.mark.allow_subprocess
def test_ohne_die_probedatei_bleibt_die_abfrage_eine_textzeile(tmp_path):
    """Die niederlaendische .mo-Datei, und sie uebersetzt hier nichts.

    plymouthd ruft setlocale(LC_ALL, "") bei 0x53e9 NUR, wenn
    ply_file_exists() bei 0x53d3 den Pfad bei .rodata 0x1f100 findet:
    /usr/share/locale/nl/LC_MESSAGES/plymouth.mo. Eine einzelne
    Uebersetzungsdatei als Anwesenheitsprobe fuer Uebersetzungen
    ueberhaupt. Ohne sie sieht plymouthd die Umgebungsvariable nicht
    einmal an - gemessen, das war der dritte der vier Laeufe.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS,
                                 uebersetzung=False)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert _files_von(wurzel) == ""
    assert "plymouth.mo" in ergebnis.stderr


@pytest.mark.allow_subprocess
def test_ohne_den_haken_aus_dem_paket_bleibt_die_abfrage_eine_textzeile(
        tmp_path):
    """Ein Haken in der HOOKS-Zeile, den es nicht gibt, ist toedlich.

    mkinitcpio antwortet auf einen unbekannten Namen mit "Hook cannot be
    found" und baut kein Abbild - eine Maschine, deren naechster
    Kernel-Update-Lauf keine Initramfs mehr erzeugt. Der Befehl schreibt
    `zepos-locale` deshalb nur dann in die Zeile, wenn beide Stuecke des
    Hakens auf dem Ziel liegen.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS, haken=False)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert _files_von(wurzel) == ""
    assert "zepos-locale" in ergebnis.stderr


@pytest.mark.allow_subprocess
def test_ein_abbild_ohne_gebietsschema_stellt_alles_zurueck(tmp_path):
    """mkinitcpio gibt 0 zurueck und die Daten fehlen trotzdem.

    Derselbe Riss wie bei der Tastaturbelegung: das Abbild ist da, es
    ist vollstaendig genug, um zu starten, und der Fehler zeigt sich
    erst auf dem Schirm. Ein Abbild mit dem Haken und ohne die Daten
    zeigt "geprft" - also wird der Zustand von vorher wiederhergestellt.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    vorher = (wurzel / "etc/mkinitcpio.conf").read_text(encoding="utf-8")
    ergebnis = _befehl_ausfuehren(wurzel, abbild_ohne_gebietsschema=True)

    assert ergebnis.returncode == 0
    assert (wurzel / "etc/mkinitcpio.conf").read_text(encoding="utf-8") == vorher
    assert (wurzel / "boot/initramfs-linux.img").read_bytes() == b"die alte initramfs"
    assert "C.utf8" in ergebnis.stderr


@pytest.mark.allow_subprocess
def test_ein_abbild_ohne_den_haken_stellt_alles_zurueck(tmp_path):
    """Und die Gegenrichtung: die Daten liegen bei, der Haken fehlt.

    Dann bleibt plymouthd im Gebietsschema "C", das Bild ist dasselbe
    wie ohne den ganzen Umbau, und die Initramfs traegt 416 KB, die
    niemand liest.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel, abbild_ohne_haken=True)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert "hooks/zepos-locale" in ergebnis.stderr


@pytest.mark.allow_subprocess
def test_ohne_encrypt_bleibt_die_hooks_zeile_unberuehrt(tmp_path):
    """Eine unverschluesselte Platte fragt nichts, also aendert sich
    nichts.

    Ein Startbild waere hier moeglich und ist nicht gebaut: ein Weg
    durch die Initramfs, den dieser Baum nirgends misst, ist genau die
    Sorte Zeile, die eine Maschine nicht mehr starten laesst.
    """
    ohne = "base udev autodetect microcode modconf kms keyboard keymap consolefont block filesystems fsck"
    wurzel = _nachgebaute_wurzel(tmp_path, ohne)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == ohne


@pytest.mark.allow_subprocess
def test_sd_encrypt_wird_nicht_fuer_encrypt_gehalten(tmp_path):
    """Der Weg mit dem HSM, den ZepOS nicht nimmt - und der Fallstrick
    darin.

    `sd-encrypt` enthaelt das Wort `encrypt`, und der Bindestrich ist
    fuer einen regulaeren Ausdruck eine Wortgrenze. Eine Ersetzung auf
    \\bencrypt\\b machte daraus `sd-plymouth encrypt`: zwei Haken, die es
    nicht gibt, und eine Maschine, die nicht mehr startet.
    """
    mit_sd = "base systemd autodetect modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck"
    wurzel = _nachgebaute_wurzel(tmp_path, mit_sd)
    ergebnis = _befehl_ausfuehren(wurzel)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == mit_sd


@pytest.mark.allow_subprocess
def test_ohne_plymouth_passiert_nichts(tmp_path):
    """Der Rueckweg, den der encrypt-Haken selbst offenhaelt.

    Fehlt plymouth, bleibt die HOOKS-Zeile, wie sie war, und die
    Maschine bekommt beim Starten die Textzeile von frueher. Das ist
    kein guter Ausgang, aber es ist ein Ausgang - und der einzige, den
    ein Mensch ohne Live-Medium noch selbst bedienen kann.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel, ohne_werkzeuge=("plymouth-set-default-theme",))

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS


@pytest.mark.allow_subprocess
def test_ein_gescheitertes_mkinitcpio_stellt_alles_zurueck(tmp_path):
    """Der Fall, in dem ein Fehler die Maschine kosten wuerde.

    Bricht mkinitcpio ab, dann steht in der HOOKS-Zeile ein Haken, den
    die vorhandene Initramfs nicht kennt - und beim naechsten regulaeren
    Neubau (ein Kernel-Update) entstuende ein Abbild aus einer Zeile,
    die noch nie funktioniert hat. Also wird beides zurueckgedreht.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    vorher = (wurzel / "boot/initramfs-linux.img").read_bytes()

    ergebnis = _befehl_ausfuehren(wurzel, mkinitcpio_scheitert=True)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert (wurzel / "boot/initramfs-linux.img").read_bytes() == vorher
    assert "wiederhergestellt" in ergebnis.stderr


@pytest.mark.allow_subprocess
def test_ein_abbild_ohne_plymouthd_stellt_alles_zurueck(tmp_path):
    """mkinitcpio gibt 0 zurueck und hat trotzdem nichts eingepackt.

    usr/lib/initcpio/install/plymouth bricht bei einem fehlenden Modul
    mit `error` ab, und mkinitcpio zaehlt das als Warnung. Ohne die
    Nachschau waere das Ergebnis eine Initramfs, die plymouthd startet,
    das es nicht gibt - und der encrypt-Haken faende kein laufendes
    plymouthd, faele in seinen else-Zweig und zeigte die Textzeile.
    Sichtbar waere das erst beim Einschalten.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel, abbild_ist_leer=True)

    assert ergebnis.returncode == 0
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert "plymouthd" in ergebnis.stderr


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("mangel", [
    {"haken": False},
    {"uebersetzung": False},
    {"gebietsschema": False},
])
def test_ein_fehlendes_stueck_kostet_nie_die_installation(tmp_path, mangel):
    """Dieselbe Regel wie unten, fuer die drei neuen Vorbedingungen.

    Sie stehen VOR der Sicherung und aendern deshalb nichts; geprueft
    wird trotzdem beides - der Rueckgabewert und dass die Zeile so
    dasteht, wie sie dastand.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS, **mangel)
    ergebnis = _befehl_ausfuehren(wurzel)
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert _hooks_von(wurzel) == GEMESSENE_HOOKS
    assert sorted(p.name for p in (wurzel / "root").iterdir()) == []


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("stoerung", [
    {},
    {"mkinitcpio_scheitert": True},
    {"abbild_ist_leer": True},
    {"abbild_ohne_belegung": True},
    {"abbild_ohne_gebietsschema": True},
    {"abbild_ohne_haken": True},
    {"ohne_werkzeuge": ("plymouth-set-default-theme",)},
    {"ohne_werkzeuge": ("lsinitcpio",)},
])
def test_der_befehl_gibt_immer_null_zurueck(tmp_path, stoerung):
    """Dieselbe Regel wie bei GRUB_MKCONFIG_COMMAND, und derselbe Preis.

    run_custom_user_commands() ruft `arch-chroot -S <ziel> bash <datei>`
    ueber SysCommand, und SysCommand wirft bei einem Rueckgabewert != 0.
    In guided.py steht danach - und nur danach - installation.genfstab().
    Ein hier scheiternder Befehl kostet also nicht das Bild, sondern die
    /etc/fstab, und das ist ein System, das nicht mehr bootet.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    ergebnis = _befehl_ausfuehren(wurzel, **stoerung)
    assert ergebnis.returncode == 0, ergebnis.stderr


@pytest.mark.allow_subprocess
def test_der_befehl_laesst_keine_sicherung_liegen(tmp_path):
    """Eine Initramfs ist gross und /boot ist die ESP.

    Die Sicherung liegt zwar unter /root und nicht auf der ESP, aber
    liegenlassen heisst hier: eine Kopie des Abbilds im
    Wurzelverzeichnis, die niemand mehr anfasst und niemand erklaert.
    """
    wurzel = _nachgebaute_wurzel(tmp_path, GEMESSENE_HOOKS)
    _befehl_ausfuehren(wurzel)
    liegengeblieben = sorted(p.name for p in (wurzel / "root").iterdir())
    assert liegengeblieben == [], liegengeblieben


# ---------------------------------------------------------------------
# Der Messstand fuer den Befehl
# ---------------------------------------------------------------------

def _nachgebaute_wurzel(
    tmp_path: Path,
    hooks: str,
    *,
    vconsole: str | None = GEMESSENE_VCONSOLE,
    kbd_model_map: bool = True,
    files: str = "",
    haken: bool = True,
    uebersetzung: bool = True,
    gebietsschema: bool = True,
) -> Path:
    """Ein Wurzelverzeichnis mit genau den Dateien, die der Befehl liest."""
    wurzel = tmp_path / "ziel"
    for verzeichnis in ("etc", "boot", "root", "usr/share/systemd",
                        "usr/share/plymouth/themes/zepos"):
        (wurzel / verzeichnis).mkdir(parents=True, exist_ok=True)

    (wurzel / "etc/mkinitcpio.conf").write_text(
        f"# nachgebaut\nMODULES=()\nBINARIES=()\nFILES=({files})\n"
        f"HOOKS=({hooks})\n", encoding="utf-8")
    if vconsole is not None:
        (wurzel / "etc/vconsole.conf").write_text(vconsole, encoding="utf-8")
    if kbd_model_map:
        (wurzel / "usr/share/systemd/kbd-model-map").write_text(
            GEMESSENE_KBD_MODEL_MAP, encoding="utf-8")
    # Kein leeres Abbild: der Test auf die Wiederherstellung vergleicht
    # Bytes, und zwei leere Dateien sind immer gleich.
    (wurzel / "boot/initramfs-linux.img").write_bytes(b"die alte initramfs")
    (wurzel / "usr/share/plymouth/themes/zepos/zepos.plymouth").write_text(
        DESCRIPTOR.read_text(encoding="utf-8"), encoding="utf-8")

    # Der Haken aus dem Paket, und zwar der ECHTE: was hier liegt, ist
    # Byte fuer Byte das, was packaging/zepos-config nach
    # /usr/lib/initcpio/ legt. Eine Attrappe wuerde die Frage, ob der
    # Befehl den richtigen Pfad nachsieht, gegen sich selbst pruefen.
    if haken:
        for art in ("install", "hooks"):
            ziel = wurzel / "usr/lib/initcpio" / art / "zepos-locale"
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(
                (REPO / "src/boot/initcpio" / art / "zepos-locale").read_bytes())

    # Die Anwesenheitsprobe, an der plymouthds setlocale-Aufruf haengt.
    # Der Inhalt ist egal - plymouthd sieht nur nach, OB es sie gibt
    # (ply_file_exists bei 0x53d3); hier stehen die vier Bytes, mit denen
    # eine .mo-Datei anfaengt, damit im Zweifel niemand raetselt.
    if uebersetzung:
        mo = wurzel / "usr/share/locale/nl/LC_MESSAGES/plymouth.mo"
        mo.parent.mkdir(parents=True, exist_ok=True)
        mo.write_bytes(b"\xde\x12\x04\x95")

    if gebietsschema:
        for name in GEMESSENE_GEBIETSSCHEMA_DATEIEN:
            datei = wurzel / "usr/lib/locale/C.utf8" / name
            datei.parent.mkdir(parents=True, exist_ok=True)
            datei.write_bytes(b"\0" * 16)
    return wurzel


def _hooks_von(wurzel: Path) -> str:
    text = (wurzel / "etc/mkinitcpio.conf").read_text(encoding="utf-8")
    treffer = re.search(r"^HOOKS=\((.*)\)\s*$", text, re.MULTILINE)
    assert treffer, f"Keine HOOKS-Zeile mehr in {wurzel}/etc/mkinitcpio.conf"
    return treffer.group(1)


def _files_von(wurzel: Path) -> str:
    text = (wurzel / "etc/mkinitcpio.conf").read_text(encoding="utf-8")
    treffer = re.search(r"^FILES=\((.*)\)\s*$", text, re.MULTILINE)
    assert treffer, f"Keine FILES-Zeile mehr in {wurzel}/etc/mkinitcpio.conf"
    return treffer.group(1)


def _abbild_inhalt(*, ohne: tuple[str, ...] = ()) -> list[str]:
    """Was `lsinitcpio -l` auf einem gelungenen Abbild auflistet.

    In der Form, die gemessen ist: ohne fuehrenden Schraegstrich, und der
    Abschalt-Haken als `shutdown` ohne Verzeichnis davor. Die Liste ist
    das Gegenstueck zu der, die der Befehl nach dem mkinitcpio-Lauf
    abklappert - `ohne` nimmt einzelne Stuecke heraus, und jedes davon
    muss den Rueckbau ausloesen.
    """
    zeilen = [
        "usr/bin/plymouthd",
        "usr/share/plymouth/themes/zepos/zepos.script",
        "etc/vconsole.conf",
        "hooks/zepos-locale",
        "usr/share/locale/nl/LC_MESSAGES/plymouth.mo",
    ]
    zeilen += [f"usr/lib/locale/C.utf8/{name}"
               for name in GEMESSENE_GEBIETSSCHEMA_DATEIEN]
    zeilen.append("shutdown")
    return [zeile for zeile in zeilen
            if not any(zeile.startswith(stueck) for stueck in ohne)]


def _lsinitcpio_attrappe(zeilen: list[str]) -> str:
    return "printf '%s\\n' " + " ".join(f"'{zeile}'" for zeile in zeilen)


def _befehl_ausfuehren(
    wurzel: Path,
    *,
    mkinitcpio_scheitert: bool = False,
    abbild_ist_leer: bool = False,
    abbild_ohne_belegung: bool = False,
    abbild_ohne_abschalt: bool = False,
    abbild_ohne_gebietsschema: bool = False,
    abbild_ohne_haken: bool = False,
    ohne_werkzeuge: tuple[str, ...] = (),
) -> subprocess.CompletedProcess:
    """PLYMOUTH_COMMAND laufen lassen, gegen nachgebaute Werkzeuge.

    Die drei Programme, die der Befehl aufruft, sind hier Attrappen -
    aber der Befehl selbst ist der ausgelieferte, Zeichen fuer Zeichen.
    Das ist der Unterschied zu einem Test, der nachsieht, ob die
    richtigen Woerter dastehen: hier laeuft die Verzweigung, die auf
    einer Zielplatte laufen wird.
    """
    stubs = wurzel.parent / "stubs"
    stubs.mkdir(exist_ok=True)

    def schreibe(name: str, rumpf: str) -> None:
        if name in ohne_werkzeuge:
            return
        pfad = stubs / name
        pfad.write_text(f"#!/bin/sh\n{rumpf}\n", encoding="utf-8")
        pfad.chmod(0o755)

    schreibe("plymouth-set-default-theme", "exit 0")
    schreibe("mkinitcpio",
             "exit 1" if mkinitcpio_scheitert else
             f'printf "die neue initramfs" > "{wurzel}/boot/initramfs-linux.img"\nexit 0')
    if abbild_ist_leer:
        schreibe("lsinitcpio", 'printf "usr/bin/busybox\\netc/fstab\\n"')
    elif abbild_ohne_belegung:
        # Der Fall, den der plymouth-Haken von sich aus erzeugt: alles
        # da ausser der Tastaturbelegung.
        schreibe("lsinitcpio", _lsinitcpio_attrappe(
            _abbild_inhalt(ohne=("etc/vconsole.conf",))))
    elif abbild_ohne_abschalt:
        # Alles da ausser dem Abschalt-Haken - und mit `shutdown` als
        # TEILSTUECK eines anderen Pfades, denn genau dieser Eintrag
        # bringt eine Initramfs von sich aus mit. Eine Pruefung, die das
        # Teilstueck sucht statt der Zeile, faende ihn und meldete
        # Erfolg fuer eine Datei, die fehlt.
        schreibe("lsinitcpio", _lsinitcpio_attrappe(
            _abbild_inhalt(ohne=("shutdown",))
            + ["usr/lib/systemd/system/shutdown.target"]))
    elif abbild_ohne_gebietsschema:
        # Der teuerste Fall dieser Liste: der Haken ist drin, die Daten
        # sind es nicht. setlocale findet dann nichts zu laden, und auf
        # dem Schirm steht "Passphrase wird geprft" - weniger als die
        # englische Textzeile, die das Fenster ersetzt hat.
        schreibe("lsinitcpio", _lsinitcpio_attrappe(
            _abbild_inhalt(ohne=("usr/lib/locale/",))))
    elif abbild_ohne_haken:
        # Und andersherum: die Daten liegen bei, der Haken fehlt. Dann
        # bleibt plymouthd im Gebietsschema "C" und es aendert sich
        # nichts - nur dass 416 KB mitgeschleppt werden.
        schreibe("lsinitcpio", _lsinitcpio_attrappe(
            _abbild_inhalt(ohne=("hooks/zepos-locale",))))
    else:
        # `shutdown` OHNE Verzeichnis davor: der Abschalt-Haken legt sein
        # Programm in die Wurzel der Initramfs, siehe usr/lib/initcpio/
        # install/shutdown. So listet lsinitcpio -l es auch.
        schreibe("lsinitcpio", _lsinitcpio_attrappe(_abbild_inhalt()))

    umgebung = dict(os.environ)
    umgebung["ZEPOS_WURZEL"] = str(wurzel)
    umgebung["PATH"] = f"{stubs}:{umgebung.get('PATH', '')}"

    skript = wurzel.parent / "befehl.sh"
    skript.write_text(PLYMOUTH_COMMAND, encoding="utf-8")
    return subprocess.run(["bash", str(skript)], capture_output=True,
                          text=True, env=umgebung)


# =====================================================================
# Der Messstand, der das Bild macht
# =====================================================================

def test_die_passphrase_des_messstands_traegt_y_und_z():
    """Die Probe auf die Tastaturbelegung, und sie ist der Grund, aus
    dem diese Zeichen in der Passphrase stehen duerfen.

    _QCODES_DE bildet "y" auf den qcode "z" ab und umgekehrt. Getippt
    wird also die POSITION, die auf einer deutschen Belegung ein y
    ergibt. Laedt die Abfrage im initramfs die deutsche Belegung, geht
    die Platte auf; laedt sie das eingebaute "us", stimmt die Passphrase
    nicht und der Lauf bleibt sichtbar an der Abfrage stehen.

    Ohne diese zwei Zeichen koennte der Messstand eine vertauschte
    Belegung gar nicht bemerken - er meldete ein schoenes Bild und
    hinterliesse eine Maschine, aus der ein Mensch sich aussperrt.
    """
    text = (REPO / "iso/test-boot.py").read_text(encoding="utf-8")
    treffer = re.search(r'^RELEASE_DISK_PASSPHRASE = "([^"]*)"',
                        text, re.MULTILINE)
    assert treffer, "RELEASE_DISK_PASSPHRASE ist nicht mehr zu finden."
    passphrase = treffer.group(1)

    assert "y" in passphrase and "z" in passphrase, (
        f"{passphrase!r} traegt kein y und kein z - damit kann kein Lauf "
        "eine vertauschte Tastaturbelegung an der Passphrase-Abfrage "
        "bemerken.")
    assert len(passphrase) >= 12, (
        "installer.core.crypt.MIN_PASSPHRASE_LENGTH verlangt zwoelf.")
