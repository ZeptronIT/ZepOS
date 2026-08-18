# SPDX-License-Identifier: GPL-3.0-or-later
"""Translate a ZepOS InstallConfig into archinstall's JSON format.

Field names follow archinstall/examples/config-sample.json of version
4.4. The sample's own "version" key is stale (it still says 2.8.6) and
is deliberately not reproduced.

Passwords never enter the config; they belong in creds.json as hashes.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from .crypt import ENCRYPTION_TYPE_LUKS, effective_layout, is_encryptable
from .i18n import _
from .layout import PlannedPartition, layout_errors
from .model import InstallConfig, MIN_DISK_MIB
from .passwords import hash_password
from .source import PackageSource, mirror_config

ZEPOS_META_PACKAGE = "zepos-desktop"

# Was die ZepOS-Seite zusaetzlich anbietet, und der Name, der daraus wird.
#
# WARUM ZWEI DAVON METAPAKETE SIND
#     Weil eine Liste von Paketnamen in dieser Datei genau das waere,
#     wovor packaging/zepos-desktop/PKGBUILD im Kopf warnt: "not in a
#     list somebody types on the day they install". Welche Buerosoftware
#     ZepOS anbietet und warum, ist eine Entscheidung mit einer
#     Begruendung, und die gehoert in ein Rezept, wo sie neben der
#     Messung steht - nicht in ein Woerterbuch im Installer.
#
# HIER STAND EIN DRITTER EINTRAG - firefox
#     Er kam auf, weil diese Datei firefox fuer unvereinbar mit der
#     GTK4-Regel hielt und epiphany auslieferte; der Haken war der
#     Ausweg fuer den, der firefox trotzdem wollte.
#
#     Der Nutzer hat die Regel am 11.08.2026 praezisiert - "was externe
#     dienste und pakete angeht koennen wir das nicht verhindern daher
#     darf dort gtk3 verwendet werden" - und damit war der Ausweg
#     gegenstandslos: firefox ist seither harte Abhaengigkeit von
#     zepos-apps. Ein Haken fuer etwas, das ohnehin mitkommt, ist ein
#     Bedienelement, das nichts tut, und davon gab es in diesem Baum
#     heute schon genug (vier ungelesene Regler in der
#     Einstellungsdatei, 383 tote Stilplatzhalter). Geloescht statt
#     stehengelassen.
OPTIONAL_PACKAGES: tuple[tuple[str, str], ...] = (
    ("install_office", "zepos-apps-office"),
    ("install_devel", "zepos-apps-devel"),
)


def selected_packages(cfg: InstallConfig) -> list[str]:
    """Die Paketliste, die archinstall bekommt.

    Die Reihenfolge ist fest und nicht die eines Mengendurchlaufs: diese
    Liste landet in einer Konfigurationsdatei, die ein Mensch liest, wenn
    eine Installation schiefgegangen ist, und zwei Laeufe mit denselben
    Haken muessen dieselbe Datei ergeben. Ein `set` haette das nicht
    zugesagt.
    """
    packages = [ZEPOS_META_PACKAGE]
    packages.extend(
        package for field, package in OPTIONAL_PACKAGES
        if getattr(cfg.zepos, field)
    )
    return packages

# Das Startmenue ein zweites Mal erzeugen, nachdem das Thema da ist.
#
# WARUM EIN ZWEITES MAL NOETIG IST
#     Die Reihenfolge in archinstalls scripts/guided.py ist
#     add_bootloader() -> add_additional_packages() -> enable_service() ->
#     run_custom_user_commands(). Der erste Lauf von grub-mkconfig steckt
#     in add_bootloader() und passiert damit, bevor zepos-desktop und mit
#     ihm zepos-config installiert sind: /etc/default/grub.d/10-zepos.cfg
#     und /usr/share/grub/themes/zepos/ gibt es zu diesem Zeitpunkt noch
#     nicht, und die grub.cfg, die dabei entsteht, kennt kein Thema.
#
# WARUM DER ZWEITE LAUF SEIT DEM 17.08.2026 AUCH GENUEGT
#     Bis dahin tat er es nicht, und das war der Fehler, den der Nutzer
#     viermal gemeldet hat. Er lief, er lief zur richtigen Zeit - die
#     Zeitstempel der Zielplatte vom 17.08.2026 sagen zepos-config um
#     09:53:13 und grub.cfg um 09:53:26 -, und die grub.cfg enthielt
#     trotzdem null Zeilen mit `theme`. Der Grund lag nicht an der
#     Reihenfolge, sondern am Themenpfad: er zeigte auf die
#     verschluesselte Wurzel, und is_path_readable_by_grub verwirft von
#     dort alles. src/boot/grub-zepos.cfg schreibt die Messung aus.
#
#     Der Pfad zeigt seither nach /boot, und ein ALPM-Haken legt das
#     Thema dorthin. Der Haken laeuft in derselben pacman-Transaktion,
#     die zepos-config installiert - also VOR diesem Befehl, gemessen an
#     /var/log/pacman.log der Zielplatte: 90-zepos-update.hook um
#     07:53:23 UTC, drei Sekunden vor der grub.cfg. src/boot/
#     zepos-grub-theme traegt den Rest.
#
# WARUM DER BEFEHL NICHT SCHEITERN DARF
#     run_custom_user_commands() ruft `arch-chroot -S <ziel> bash <datei>`
#     ueber SysCommand, und SysCommand wirft bei einem Rueckgabewert != 0.
#     In guided.py steht danach - und nur danach - installation.genfstab().
#     Ein hier scheiternder Befehl kostet also nicht das Thema, sondern
#     die /etc/fstab, und das ist ein System, das nicht mehr bootet. Ein
#     unschoenes Startmenue ist dagegen ein unschoenes Startmenue.
#
# WARUM NACH "Found theme" GESUCHT WIRD
#     Weil ein fehlendes Thema sonst nichts sagt. GRUB antwortet auf ein
#     nicht lesbares Thema mit dem Textmodus und ohne Fehler, und
#     grub-mkconfig meldet den Fund nur als eine Zeile auf stderr. Die
#     einzige Stelle, an der das noch jemand liest, ist das
#     Installationsprotokoll - also wird die Zeile dort in einen Satz
#     uebersetzt statt zwischen hundert anderen zu verschwinden.
GRUB_MKCONFIG_COMMAND = """\
# ZepOS: das Startmenue neu erzeugen, jetzt wo das Thema installiert ist.
report="$(grub-mkconfig -o /boot/grub/grub.cfg 2>&1)"
printf '%s\\n' "$report"
case "$report" in
    *"Found theme"*)
        printf 'ZepOS: Startmenue erzeugt, mit dem ZepOS-Thema.\\n' ;;
    *)
        printf 'ZepOS: Startmenue erzeugt, aber OHNE das ZepOS-Thema.\\n' >&2 ;;
esac
# Immer 0: siehe installer/core/translate.py, GRUB_MKCONFIG_COMMAND.
exit 0
"""

# Aus der Textzeile beim Einschalten ein Fenster machen.
#
# WAS VORHER DA STAND, gemessen und nicht erinnert - iso/out/
# run-release-installed/screen-0060s.png vom 13.08.2026, zwei Zeilen
# weisse Schrift auf Schwarz, auf einem sonst durchgehend deutschen
# System:
#
#     A password is required to access the root volume:
#     Enter passphrase for /dev/vda2:
#
# WARUM DAS HIER STEHT UND NICHT IN EINEM PAKET
#     Weil es zwei Dinge tut, die ein Paket nicht tun darf. Es aendert
#     /etc/mkinitcpio.conf, eine Datei, die dem Administrator gehoert,
#     und es baut die Initramfs der Maschine neu. Ein Paketskript, das
#     das bei jedem `pacman -Syu` taete, waere ein Paket, das beim
#     Aktualisieren den Start riskiert. Hier laeuft es genau einmal, im
#     Chroot, waehrend der Installation.
#
#     archinstall baut die Initramfs vorher selbst
#     (Installer.minimal_installation() ruft mkinitcpio()), und zwar mit
#     dem klassischen encrypt-Haken und ohne plymouth. Dieser Befehl
#     laeuft in run_custom_user_commands() und damit NACH
#     add_additional_packages() - plymouth ist also da, wenn er es
#     braucht.
#
# WARUM `plymouth` UND NICHT `plymouth-encrypt`
#     Weil es plymouth-encrypt nicht mehr gibt. mkinitcpio 41-4 liefert
#     unter usr/lib/initcpio/hooks/ genau consolefont, encrypt, keymap,
#     memdisk, resume, shutdown, sleep, udev und usr; plymouth
#     26.134.222-2 legt hooks/plymouth daneben und sonst nichts (beide
#     Pakete am 13.08.2026 aus dem angehefteten ALA-Schnappschuss
#     2026/08/04 ausgepackt und aufgezaehlt). Der encrypt-Haken fragt
#     statt dessen selbst nach, ob plymouthd laeuft:
#
#         if command -v plymouth >/dev/null 2>&1 && plymouth --ping ...
#             plymouth ask-for-password --prompt=... --command=...
#         else
#             echo "A password is required to access the ... volume:"
#             while ! cryptsetup open ...; do sleep 2; done
#
#     Das ist zugleich DER RUECKWEG, und er kostet nichts: eine
#     Maschine, auf der plymouthd nicht hochkommt - fehlender KMS-
#     Treiber, exotische Grafik -, faellt in den else-Zweig und bekommt
#     die Textzeile von vorher. Niemand wird aus seiner Platte
#     ausgesperrt, weil ein Bild nicht ging.
#
# WOHIN DER HAKEN IN DER ZEILE GEHOERT
#     Unmittelbar VOR `encrypt`, und das ist gemessen. Von der
#     HOOKS-Zeile einer ZepOS-Installation
#
#         base udev autodetect microcode modconf kms keyboard keymap
#         consolefont block encrypt filesystems fsck
#
#     haben ueberhaupt nur udev, keymap, consolefont und encrypt einen
#     Laufzeitteil - die uebrigen sind reine Bau-Haken (mkinitcpio 41-4
#     legt fuer sie nichts unter hooks/ ab). Die Reihenfolge zur
#     Laufzeit ist also udev, keymap, consolefont, encrypt, und
#     zwischen "gleich nach udev" und "gleich vor encrypt" liegen zwei
#     schnelle Haken und keine Zeit.
#
#     Es bleibt trotzdem bei "gleich vor encrypt": `keymap` laedt die
#     Belegung in den Konsolentreiber, und die Textzeile des
#     else-Zweiges - der Rueckweg - liest von dort. Plymouth DAVOR zu
#     setzen kostet nichts und nuetzt nichts; plymouth DAHINTER laesst
#     den Rueckweg auf der richtigen Belegung tippen.
#
# UND DIE BELEGUNG DER ABFRAGE HAENGT NICHT AN DIESER REIHENFOLGE.
# DAS IST DIE TEURE MESSUNG DES 13.08.2026.
#     Der Lauf vom selben Tag zeigte das Fenster - und nahm die
#     Passphrase nicht an. Die Punkte erschienen (iso/out/
#     run-release-installed/key-13-05-passwort-getippt.png: elf Punkte
#     fuer elf getippte Zeichen), die Platte ging nicht auf, und die
#     Abfrage kam leer wieder. Getippt wurden deutsche
#     Tastenpositionen; die Platte liess sich hinterher von Hand mit
#     genau der Passphrase aufschliessen, die der Assistent bekommen
#     hatte. Also stimmte der Assistent, und die ABFRAGE bekam andere
#     Zeichen.
#
#     Der Grund, aus der ausgelieferten Initramfs ausgelesen und nicht
#     aus einer Anleitung abgeschrieben:
#
#         $ objdump -p usr/lib/libply-splash-core.so.5
#         NEEDED  libevdev.so.2
#         NEEDED  libxkbcommon.so.0
#
#     plymouth 26.134.222-2 liest Tastaturen ueber evdev und uebersetzt
#     sie mit libxkbcommon. Es setzt dazu KDSKBMODE auf dem Terminal
#     (0x4b45, dreimal im Maschinencode) - der Konsolentreiber
#     uebersetzt also gar nicht mehr, plymouth tut es selbst. Damit ist
#     `loadkmap` aus dem keymap-Haken fuer diese Abfrage ohne Wirkung,
#     und die Reihenfolge in der HOOKS-Zeile entscheidet ueber die
#     Belegung nichts.
#
#     WORAN plymouth SEINE BELEGUNG NIMMT, steht in denselben
#     Zeichenketten:
#
#         parse_vconsole_conf
#         /etc/vconsole.conf
#         KEYMAP: %s, XKBLAYOUT: %s, XKBMODEL %s, XKBVARIANT: %s, ...
#         Not creating devices for subsystem input because there is no
#         configure XKB layout
#
#     Es liest /etc/vconsole.conf - und zwar die IN DER INITRAMFS.
#     usr/lib/initcpio/install/plymouth kopiert /usr/share/X11/xkb und
#     /usr/share/X11/locale hinein, aber /etc/vconsole.conf NICHT
#     (Rezept am 13.08.2026 von der Zielplatte gelesen, Abschnitt "copy
#     xkb info and x11 locale"). Ohne Belegung nimmt libxkbcommon
#     seine eingebaute Vorgabe, und die ist `us`.
#
#     Das ist derselbe Fehler, den dieser Baum am 12.08.2026 schon
#     einmal hatte: cage im Live-System ohne XKB_DEFAULT_LAYOUT, also
#     ein deutscher Assistent auf einer amerikanischen Belegung (siehe
#     iso/test-boot.py, RELEASE_LAYOUT). Dieselbe Bibliothek, dieselbe
#     Vorgabe, eine Schicht tiefer - und hier ist der Preis nicht ein
#     falsch getipptes Passwort, sondern eine Platte, die zubleibt.
#
#     DESHALB LEGT DIESER BEFEHL /etc/vconsole.conf IN DIE INITRAMFS.
#     Ueber die FILES-Zeile von mkinitcpio, die jede Datei an derselben
#     Stelle im Abbild ablegt (mkinitcpio 41, functions: `map add_file
#     "${FILES[@]}"`, und add_file nimmt das Ziel aus dem Quellpfad,
#     wenn kein zweites Argument kommt). Danach findet plymouth
#     XKBLAYOUT=de neben KEYMAP=de-latin1 und uebersetzt so, wie der
#     Nutzer es im Assistenten gewaehlt hat.
#
#     UND WENN KEINE BELEGUNG ZU FINDEN IST, bleibt es bei der
#     Textzeile. Lieber der englische Satz auf der richtigen Belegung
#     als ein deutsches Fenster auf der falschen: das erste ist
#     haesslich, das zweite sperrt aus.
#
# UND SEIT DEM 17.08.2026 SCHREIBT DIE ABFRAGE UMLAUTE.
#     Bis dahin stand auf dem ersten Bildschirm dieses Systems
#     "Passphrase wird geprueft" - in Ersatzschreibung, weil ein "ü"
#     dort nicht als Kaestchen erschien, sondern spurlos verschwand
#     ("Passphrase wird geprft"). Die Kette dahinter ist an plymouth
#     26.134.222-2 Glied fuer Glied gemessen:
#
#       * Die Schrift kann es. Der plymouth-Haken legt ueber `fc-match`
#         Roboto als /usr/share/fonts/Plymouth.ttf in die Initramfs;
#         die Datei ist dort 460324 Bytes gross und fuehrt U+00FC in
#         ihrer cmap als Glyph 2333 (ae 2312, oe 2329, ss 134, der
#         Gedankenstrich U+2013 als 1118).
#       * Der Zeichner dekodiert ueber das GEBIETSSCHEMA:
#         usr/lib/plymouth/label-freetype.so schiebt jedes Zeichen bei
#         0x26de durch `mbrtowc`, ehe es bei 0x2709 in FT_Load_Char
#         geht. Im Gebietsschema "C" (ANSI_X3.4-1968) faellt das 0xC3
#         heraus.
#       * plymouthd nimmt sein Gebietsschema aus der UMGEBUNG
#         (setlocale(LC_ALL, "")), und der plymouth-Haken startet es
#         ohne jede.
#
#     DREI STUECKE MUESSEN DAFUER ZUSAMMENKOMMEN, jedes einzeln an
#     einem Lauf in QEMU nachgewiesen - mit nur einem oder zweien davon
#     stand weiterhin "geprft" auf dem Schirm:
#
#       1. DIE VARIABLE. `zepos-locale` in der HOOKS-Zeile, unmittelbar
#          vor `plymouth`. Der Haken kommt aus zepos-config
#          (src/boot/initcpio/), sein Laufzeitstueck setzt LC_ALL auf
#          C.UTF-8, und /init laesst jeden fruehen Haken vor jedem
#          spaeten laufen - plymouthd sieht die Variable also sicher.
#       2. DIE PROBEDATEI. plymouthd ruft setlocale ueberhaupt nur,
#          wenn ply_file_exists() bei 0x53d3 den Pfad bei .rodata
#          0x1f100 findet: /usr/share/locale/nl/LC_MESSAGES/plymouth.mo
#          (910 Bytes, aus dem Paket plymouth). Eine niederlaendische
#          Uebersetzung als Anwesenheitsprobe fuer Uebersetzungen
#          ueberhaupt - ohne sie sieht plymouthd die Variable nicht
#          einmal an.
#       3. DIE DATEN. "C.UTF-8" ist in dieser glibc NICHT eingebaut -
#          die Zeichenkette kommt in der libc.so.6 der Initramfs kein
#          einziges Mal vor. Das Gebietsschema liegt als Daten unter
#          /usr/lib/locale/C.utf8: 12 Dateien, zusammen 374805 Bytes,
#          davon 369120 allein LC_CTYPE. Eine davon liegt eine Ebene
#          tiefer (LC_MESSAGES/SYS_LC_MESSAGES) - wer sie mit einem
#          einfachen `*` einsammelt, laesst sie liegen, und setlocale
#          scheitert dann als GANZES, weil ihm eine Kategorie fehlt.
#
#     DIE ZWEI DATEIEN GEHEN UEBER `FILES`, die Variable NICHT. `FILES`
#     ist `map add_file "${FILES[@]}"` (mkinitcpio 41,
#     usr/lib/initcpio/functions Zeile 1131): ein Pfad je Eintrag, das
#     Ziel im Abbild ist der Quellpfad, Verzeichnisse weist add_file ab.
#     Also stehen die zwoelf Dateien des Gebietsschemas dort einzeln,
#     aufgezaehlt vom Ziel selbst und nicht aus einer Liste in dieser
#     Datei - welche Kategorien eine glibc mitbringt, ist ihre Sache und
#     nicht unsere. Eine Umgebungsvariable laesst sich so nicht
#     unterbringen: /config in der Initramfs traegt nur EARLYHOOKS,
#     HOOKS, LATEHOOKS, CLEANUPHOOKS und EMERGENCYHOOKS. Darum der
#     Haken.
#
#     WAS ES KOSTET, damit der naechste es nicht noch einmal misst: die
#     zwei Datenstuecke sind roh 375715 Bytes und schlagen im fertigen,
#     zstd-komprimierten Abbild mit 40934 Bytes zu Buche
#     (13076810 -> 13117744). Also 41 KB auf ein Abbild von 20 MB,
#     gemessen am 17.08.2026 an der Initramfs von iso/out/ppz-target.img
#     - einmal ohne und einmal mit den Dateien gepackt. Ein zweiter,
#     unabhaengiger Lauf desselben Tages an einer anders
#     zusammengesetzten Fassung kam auf 41175 Bytes.
#
#     UND WENN EINES DER DREI STUECKE FEHLT, bleibt die Abfrage eine
#     Textzeile - sie wird nicht etwa ohne Umlaute gebaut. Das ist
#     Absicht: der Text des Themas TRAEGT seit dem 17.08.2026 das "ü",
#     also zeigte ein Abbild mit dem Haken und ohne die Daten
#     "Passphrase wird geprft" und damit etwas Schlechteres als die
#     englische Zeile. Ein halb erfuelltes Versprechen ist hier
#     schlechter als gar keines.
#
# WARUM NUR BEI `encrypt`
#     Weil nur eine verschluesselte Installation ueberhaupt etwas fragt.
#     Auf einer unverschluesselten Platte waere plymouth ein Startbild
#     und sonst nichts - ein Weg, den dieser Baum nirgends misst, und
#     ein ungemessener Weg in der Initramfs ist genau die Sorte Zeile,
#     die eine Maschine nicht mehr starten laesst.
#
# WARUM DER RUECKBAU AM ENDE DRINSTEHT
#     Weil ein falscher HOOKS-Eintrag keine haessliche Oberflaeche ist,
#     sondern eine Maschine, die nicht mehr startet. Der Befehl sichert
#     deshalb die alte mkinitcpio.conf UND die alte Initramfs, prueft
#     hinterher, ob im neuen Abbild wirklich plymouthd und das Thema
#     liegen, und stellt beim kleinsten Zweifel den Zustand von vorher
#     wieder her. Was dabei herauskommt, ist im schlechtesten Fall die
#     englische Textzeile - also genau das, was ohne diesen Befehl
#     ohnehin dastuende.
#
# UND ER GIBT IMMER 0 ZURUECK, aus demselben Grund wie
# GRUB_MKCONFIG_COMMAND darueber: SysCommand wirft bei != 0, und in
# guided.py steht danach installation.genfstab(). Ein hier scheiternder
# Befehl kostet also nicht das Bild, sondern die /etc/fstab.
PLYMOUTH_COMMAND = r"""\
# ZepOS: die Passphrase-Abfrage von einer Textzeile auf ein Fenster
# umstellen. Warum das hier steht: installer/core/translate.py,
# PLYMOUTH_COMMAND.
set -u

# Die Wurzel, unter der dieser Befehl arbeitet. Leer, wenn er das tut,
# wofuer er geschrieben ist - er laeuft im Chroot der frischen
# Installation, und dort IST / das Ziel.
#
# WARUM DIE VARIABLE TROTZDEM DA IST: damit tests/boot/test_plymouth.py
# ihn ausfuehren kann, statt ihn zu lesen. Ein Befehl, der eine
# HOOKS-Zeile umschreibt und eine Initramfs neu baut, ist die eine
# Stelle in diesem Baum, an der ein Tippfehler heisst, dass die Maschine
# nicht mehr startet; ein Test, der nur nachsieht, ob die richtigen
# Woerter dastehen, prueft seine eigene Abschrift. Dieselbe Naht wie
# CPUINFO_PATH in installer/core/crypt.py, und aus demselben Grund
# dort aufgeschrieben.
wurzel="${ZEPOS_WURZEL:-}"

conf="$wurzel/etc/mkinitcpio.conf"
image="$wurzel/boot/initramfs-linux.img"
thema="$wurzel/usr/share/plymouth/themes/zepos/zepos.plymouth"
vconsole="$wurzel/etc/vconsole.conf"
kartendatei="$wurzel/usr/share/systemd/kbd-model-map"

# Die drei Stuecke, an denen der Umlaut haengt - siehe den Kopf, "UND
# SEIT DEM 17.08.2026 SCHREIBT DIE ABFRAGE UMLAUTE". Sie stehen OHNE
# $wurzel da, weil sie in dieser Form in die FILES-Zeile und in die
# HOOKS-Zeile der Zielmaschine gehen; nachgesehen wird mit $wurzel davor.
haken_install="/usr/lib/initcpio/install/zepos-locale"
haken_lauf="/usr/lib/initcpio/hooks/zepos-locale"
uebersetzung="/usr/share/locale/nl/LC_MESSAGES/plymouth.mo"
gebietsschema="/usr/lib/locale/C.utf8"
sicherung_conf="$wurzel/root/zepos-mkinitcpio.conf.vorher"
sicherung_vconsole="$wurzel/root/zepos-vconsole.conf.vorher"
sicherung_image="$wurzel/root/zepos-initramfs-linux.img.vorher"

melde() { printf 'ZepOS: %s\n' "$1"; }
melde_fehler() { printf 'ZepOS: %s\n' "$1" >&2; }

# Ein Wert aus einer Datei im Stil KEY=wert. Der letzte gewinnt, so wie
# beim Einlesen durch die Shell, und Anfuehrungszeichen fallen weg.
wert_aus() {
    sed -n "s/^[[:space:]]*$2=//p" "$1" | tail -n1 | tr -d '"' | tr -d "'"
}

# Steht `plymouth` in dieser Haken-Liste vor `encrypt`?
#
# Wortweise und nicht als Textstueck: `sd-encrypt` enthaelt `encrypt`,
# und eine Pruefung, die das nicht auseinanderhaelt, meldet eine
# Reihenfolge, die es nicht gibt.
plymouth_vor_encrypt() {
    gesehen=nein
    for haken in $1; do
        [ "$haken" = plymouth ] && gesehen=ja
        [ "$haken" = encrypt ] && { [ "$gesehen" = ja ] && return 0; return 1; }
    done
    return 1
}

# Und steht `zepos-locale` vor `plymouth`?
#
# WORTWEISE AUS DEMSELBEN GRUND wie eine Zeile darueber, und hier noch
# einen Tick strenger: der eigene Name TRAEGT den anderen nicht, aber er
# ist der laengere von beiden, und eine Suche nach dem Teilstueck
# `plymouth` faende ihn in `zepos-locale` nicht - wohl aber faende eine
# Suche nach `zepos-locale` sich selbst in einem spaeter einmal
# dazukommenden `zepos-locale-shutdown`. Ein Wort ist entweder gleich
# oder es ist es nicht.
#
# WAS DIE PRUEFUNG WERT IST: plymouthd sieht die Variable auch dann,
# wenn die Reihenfolge verrutscht - das Laufzeitstueck haengt in
# EARLYHOOKS und laeuft damit vor JEDEM run_hook, also auch vor dem von
# plymouth (gemessen, siehe src/boot/initcpio/hooks/zepos-locale). Die
# Reihenfolge in der HOOKS-Zeile ist trotzdem geprueft, weil sie
# aufschreibt, WOFUER der Haken da ist. Eine Zeile, deren Reihenfolge
# niemand mehr nachvollzieht, ist die Zeile, in der beim naechsten Umbau
# etwas verrutscht.
zepos_locale_vor_plymouth() {
    gesehen=nein
    for haken in $1; do
        [ "$haken" = zepos-locale ] && gesehen=ja
        [ "$haken" = plymouth ] && { [ "$gesehen" = ja ] && return 0; return 1; }
    done
    return 1
}

# ---------------------------------------------------------------------
# Vorbedingungen. Jede davon heisst "lass es bleiben", nicht "brich ab".
# ---------------------------------------------------------------------
if ! command -v plymouth-set-default-theme >/dev/null 2>&1; then
    melde_fehler 'plymouth fehlt, die Passphrase bleibt eine Textzeile.'
    exit 0
fi
if [ ! -r "$thema" ]; then
    melde_fehler 'Das ZepOS-Thema fehlt, die Passphrase bleibt eine Textzeile.'
    exit 0
fi
if [ ! -r "$conf" ]; then
    melde_fehler "$conf fehlt, die Passphrase bleibt eine Textzeile."
    exit 0
fi

hooks="$(sed -n 's/^HOOKS=(\(.*\))[[:space:]]*$/\1/p' "$conf")"
if [ -z "$hooks" ]; then
    melde_fehler 'Keine HOOKS-Zeile gefunden, mkinitcpio bleibt unberuehrt.'
    exit 0
fi
case " $hooks " in
    *' encrypt '*) ;;
    *)
        melde 'Keine verschluesselte Wurzel, also keine Abfrage - plymouth bleibt draussen.'
        exit 0 ;;
esac

# ---------------------------------------------------------------------
# Die Belegung, auf der die Abfrage tippen wird.
# ---------------------------------------------------------------------
# Ohne sie waere das Fenster ein Fenster auf `us` - siehe den Kopf.
# Jeder Ausgang hier heisst "lass es bleiben": die Textzeile liest ueber
# den Konsolentreiber und damit auf der Belegung des keymap-Hakens, also
# ist der Rueckweg der sichere Ausgang und nicht der schlechte.
if [ ! -r "$vconsole" ]; then
    melde_fehler "$vconsole fehlt - ohne bekannte Tastaturbelegung bleibt die Passphrase eine Textzeile."
    exit 0
fi
belegung="$(wert_aus "$vconsole" XKBLAYOUT)"
abgeleitet=nein
if [ -z "$belegung" ]; then
    # XKBLAYOUT fehlt, KEYMAP gibt es fast immer. systemd liefert die
    # Zuordnung als Tabelle mit, und src/bin/zepos-greeter schlaegt die
    # Belegung der Anmeldemaske in derselben Datei nach - eine zweite
    # Tabelle in diesem Baum waere eine, die auseinanderlaeuft.
    konsolenbelegung="$(wert_aus "$vconsole" KEYMAP)"
    if [ -n "$konsolenbelegung" ] && [ -r "$kartendatei" ]; then
        belegung="$(awk -v k="$konsolenbelegung" \
            '$1 == k { print $2; exit }' "$kartendatei")"
        [ -n "$belegung" ] && abgeleitet=ja
    fi
fi
if [ -z "$belegung" ]; then
    melde_fehler 'In /etc/vconsole.conf steht keine Tastaturbelegung - die Passphrase bleibt eine Textzeile, damit niemand auf der falschen Belegung tippt.'
    exit 0
fi

# ---------------------------------------------------------------------
# Das Gebietsschema, in dem die Abfrage ihre Umlaute schreibt.
# ---------------------------------------------------------------------
# Drei Stuecke, und jedes davon ist wieder ein "lass es bleiben" und kein
# Abbruch. Der Grund, aus dem hier nicht einfach ohne sie weitergebaut
# wird, steht im Kopf: das Thema TRAEGT das "ü", also zeigte ein Abbild
# ohne diese Stuecke "Passphrase wird geprft" - schlechter als die
# englische Textzeile, die es ersetzt.
if [ ! -r "$wurzel$haken_install" ] || [ ! -r "$wurzel$haken_lauf" ]; then
    melde_fehler "$haken_install fehlt - ohne den Gebietsschema-Haken bleibt die Passphrase eine Textzeile."
    exit 0
fi
if [ ! -r "$wurzel$uebersetzung" ]; then
    melde_fehler "$uebersetzung fehlt - ohne diese Datei ruft plymouthd setlocale gar nicht erst auf, und die Passphrase bleibt eine Textzeile."
    exit 0
fi

# Die Dateien des Gebietsschemas, VOM ZIEL AUFGEZAEHLT und nicht aus
# einer Liste in dieser Datei. Welche Kategorien eine glibc unter
# /usr/lib/locale/C.utf8 ablegt, ist ihre Sache; am 17.08.2026 waren es
# zwoelf (LC_CTYPE mit 369 KB davon der Loewenanteil), und eine
# abgeschriebene Liste waere beim naechsten glibc entweder zu kurz - dann
# scheitert setlocale und der Umlaut faellt wieder heraus - oder zu lang,
# und dann scheitert mkinitcpio an einer Datei, die es nicht gibt.
#
# Leerzeichen in einem dieser Pfade gaebe es nicht, und geben duerfte es
# sie auch nicht: die FILES-Zeile trennt mit Leerzeichen und kennt keine
# Anfuehrungszeichen.
gebietsdateien=""
for pfad in $(find "$wurzel$gebietsschema" ! -type d 2>/dev/null | sort); do
    gebietsdateien="$gebietsdateien ${pfad#"$wurzel"}"
done
if [ -z "$gebietsdateien" ]; then
    melde_fehler "$gebietsschema fehlt - ohne die Daten des Gebietsschemas bleibt die Passphrase eine Textzeile."
    exit 0
fi

# Was in der FILES-Zeile stehen muss, in dieser Reihenfolge: erst die
# Belegung, dann die Probedatei, dann die Daten.
pflicht_dateien="/etc/vconsole.conf $uebersetzung$gebietsdateien"

files="$(sed -n 's/^FILES=(\(.*\))[[:space:]]*$/\1/p' "$conf")"
hooks_fertig=nein
gebiet_fertig=nein
abschalt_fertig=nein
case " $hooks " in *' plymouth '*) hooks_fertig=ja ;; esac
case " $hooks " in *' zepos-locale '*) gebiet_fertig=ja ;; esac
case " $hooks " in *' shutdown '*) abschalt_fertig=ja ;; esac

# Wortweise auch hier, und nicht ueber ein einzelnes Beispiel: fehlte
# auch nur EINE Kategorie des Gebietsschemas, dann scheitert setlocale
# als Ganzes und der Umlaut faellt wieder heraus.
fehlende_dateien=""
for datei in $pflicht_dateien; do
    case " $files " in
        *" $datei "*) ;;
        *) fehlende_dateien="$fehlende_dateien $datei" ;;
    esac
done
files_fertig=nein
[ -z "$fehlende_dateien" ] && files_fertig=ja

if [ "$hooks_fertig" = ja ] && [ "$gebiet_fertig" = ja ] \
   && [ "$files_fertig" = ja ] && [ "$abschalt_fertig" = ja ]; then
    melde 'plymouth, das Gebietsschema, die Belegung und der Abschalt-Haken stehen schon in der Initramfs-Konfiguration.'
    exit 0
fi

# ---------------------------------------------------------------------
# Sichern, umstellen, neu bauen.
# ---------------------------------------------------------------------
cp -a "$conf" "$sicherung_conf" || exit 0
cp -a "$vconsole" "$sicherung_vconsole" || exit 0
[ -f "$image" ] && { cp -a "$image" "$sicherung_image" || exit 0; }

zurueck() {
    melde_fehler "$1"
    cp -a "$sicherung_conf" "$conf" 2>/dev/null
    cp -a "$sicherung_vconsole" "$vconsole" 2>/dev/null
    [ -f "$sicherung_image" ] && cp -a "$sicherung_image" "$image" 2>/dev/null
    rm -f "$sicherung_conf" "$sicherung_vconsole" "$sicherung_image"
    melde_fehler 'Der Zustand von vorher ist wiederhergestellt; die Abfrage ist eine Textzeile.'
    exit 0
}

plymouth-set-default-theme zepos || zurueck 'plymouth-set-default-theme ist gescheitert.'

# ---------------------------------------------------------------------
# Die Tastaturbelegung in die Initramfs.
# ---------------------------------------------------------------------
if [ "$abgeleitet" = ja ]; then
    # Genau die Zeile, die `localectl set-x11-keymap` selbst schriebe -
    # XKBLAYOUT gehoert seit systemd 249 in diese Datei. Sie wird
    # ergaenzt und nicht ersetzt, und die Sicherung oben holt sie
    # zurueck, falls danach noch etwas schiefgeht.
    printf 'XKBLAYOUT=%s\n' "$belegung" >> "$vconsole" \
        || zurueck 'XKBLAYOUT liess sich nicht in /etc/vconsole.conf schreiben.'
    melde "XKBLAYOUT=$belegung aus KEYMAP abgeleitet und in /etc/vconsole.conf ergaenzt."
fi

if [ "$files_fertig" = nein ]; then
    neue_dateien="${files:+$files}$fehlende_dateien"
    neue_dateien="${neue_dateien# }"
    if grep -q '^FILES=(' "$conf"; then
        sed -i "s|^FILES=(.*)[[:space:]]*$|FILES=($neue_dateien)|" "$conf"
    else
        printf 'FILES=(%s)\n' "$neue_dateien" >> "$conf"
    fi
    # Die Gegenprobe geht ueber JEDEN Eintrag und nicht ueber einen
    # Stellvertreter: eine sed-Ersetzung, die die Haelfte der Zeile
    # verschluckt, saehe an einem einzelnen Beispiel richtig aus.
    neue_files="$(sed -n 's/^FILES=(\(.*\))[[:space:]]*$/\1/p' "$conf")"
    for datei in $pflicht_dateien; do
        case " $neue_files " in
            *" $datei "*) ;;
            *) zurueck 'Die FILES-Zeile liess sich nicht umschreiben.' ;;
        esac
    done
fi
melde "Die Abfrage tippt auf der Belegung $belegung."
melde 'Das Gebietsschema C.UTF-8 liegt bei, die Abfrage schreibt Umlaute.'

# plymouth VOR encrypt.
#
# WORTWEISE UND NICHT MIT EINEM MUSTER AUF DER ZEILE. Ein `sed
# s/\bencrypt\b/plymouth encrypt/` sieht kuerzer aus und trifft auch
# `sd-encrypt`: der Bindestrich ist eine Wortgrenze, und heraus kaeme
# `sd-plymouth encrypt`, also zwei Haken, die es nicht gibt, und eine
# Maschine, die nicht mehr startet. Die Vorbedingung oben faengt diesen
# Fall zwar ab (sie sucht ' encrypt ' MIT Leerzeichen), aber eine
# Ersetzung, die nur deshalb harmlos ist, weil zwanzig Zeilen darueber
# jemand mitgedacht hat, ist eine Ersetzung, die beim naechsten Umbau
# gefaehrlich wird. Hier wird die Liste in Woerter zerlegt und wieder
# zusammengesetzt, und ein Wort ist entweder gleich `encrypt` oder es
# ist es nicht.
#
# UND `zepos-locale` UNMITTELBAR VOR plymouth. Der billigste Haken
# dieser Zeile: er setzt eine Umgebungsvariable und tut sonst nichts
# (src/boot/initcpio/hooks/zepos-locale - eine Zuweisung, keine
# Verzweigung, kein Programmaufruf). Ohne ihn verschluckt die Abfrage
# jeden Umlaut - die Messung steht im Kopf dieser Datei. Seine Stelle
# ist VOR plymouth, weil plymouthd sein Gebietsschema beim Start aus der
# Umgebung liest und danach nicht mehr danach fragt.
#
# UND `shutdown` GANZ AM ENDE. Der zweite Haken, den diese Zeile
# braucht, und der Grund steht am Ende der Datei nicht zufaellig:
#
#     Beim Ausschalten muss sich systemd von der Wurzel loesen, um sie
#     auszuhaengen. Auf einer verschluesselten Platte geht das nicht von
#     der Platte selbst aus - der Prozess, der aushaengt, laege auf dem,
#     was er aushaengt. Der Haken legt darum beim Start eine Kopie der
#     Initramfs nach /run/initramfs, und dorthin schwenkt systemd am
#     Ende zurueck. Fehlt er, bleibt die verschluesselte Wurzel
#     ungeloest liegen; beim naechsten Start laeuft dann still eine
#     Reparatur, die niemand angefordert hat.
#
# Sein Platz ist hinten, weil er nur einen Aufraeumschritt anmeldet und
# der ohnehin zuletzt laeuft - hinter `filesystems` und `fsck`, deren
# Ergebnis er mitkopiert.
#
# WARUM ER IN DIESEM BEFEHL STEHT UND NICHT IN EINEM EIGENEN: Es ist
# dieselbe HOOKS-Zeile, dieselbe Vorbedingung (`encrypt`, denn ohne
# Verschluesselung braucht ihn niemand) und vor allem derselbe
# `mkinitcpio -P` - ein zweiter Befehl hiesse ein zweiter Neubau, also
# eine Minute mehr Installationszeit fuer eine Zeile Text. Der Preis
# dafuer steht offen da: fehlt plymouth, springt der Befehl oben heraus,
# und dann bleibt auch dieser Haken aus. Eine Maschine ohne plymouth hat
# in diesem Baum allerdings groessere Sorgen als ihr Aushaengen.
if [ "$hooks_fertig" = nein ] || [ "$gebiet_fertig" = nein ] \
   || [ "$abschalt_fertig" = nein ]; then
    neu=""
    for haken in $hooks; do
        if [ "$haken" = encrypt ] && [ "$hooks_fertig" = nein ]; then
            # Beide auf einmal, in dieser Reihenfolge: das Gebietsschema
            # muss stehen, bevor plymouthd startet.
            [ "$gebiet_fertig" = nein ] && neu="$neu zepos-locale"
            neu="$neu plymouth"
        elif [ "$haken" = plymouth ] && [ "$gebiet_fertig" = nein ]; then
            # Die Maschine, auf der eine aeltere Fassung dieses Befehls
            # schon gelaufen ist: plymouth steht, der Umlaut fehlt.
            neu="$neu zepos-locale"
        fi
        neu="$neu $haken"
    done
    [ "$abschalt_fertig" = nein ] && neu="$neu shutdown"
    neu="${neu# }"
    sed -i "s/^HOOKS=(.*)[[:space:]]*$/HOOKS=($neu)/" "$conf"
fi
neue_hooks="$(sed -n 's/^HOOKS=(\(.*\))[[:space:]]*$/\1/p' "$conf")"
plymouth_vor_encrypt "$neue_hooks" \
    || zurueck 'Die HOOKS-Zeile liess sich nicht umschreiben.'
zepos_locale_vor_plymouth "$neue_hooks" \
    || zurueck 'Der Gebietsschema-Haken steht nicht vor plymouth.'
case " $neue_hooks " in
    *' shutdown '*) ;;
    *) zurueck 'Der Abschalt-Haken fehlt in der neuen HOOKS-Zeile.' ;;
esac
melde "HOOKS=($neue_hooks)"

mkinitcpio -P || zurueck 'mkinitcpio ist gescheitert.'

# ---------------------------------------------------------------------
# Und nachsehen, ob wirklich drin ist, was drin sein muss.
# ---------------------------------------------------------------------
# Ein mkinitcpio, das 0 zurueckgibt, hat noch nichts darueber gesagt, ob
# der plymouth-Haken seine Dateien gefunden hat: usr/lib/initcpio/install/
# plymouth bricht bei einem fehlenden Modul mit `error` ab, und
# mkinitcpio zaehlt das als Warnung. Ohne diese Pruefung waere das
# Ergebnis eine Initramfs, die plymouthd startet, das es nicht gibt.
#
# etc/vconsole.conf steht in derselben Liste und aus demselben Grund:
# fehlt es, dann kommt das Fenster trotzdem, aber auf `us` - und ein
# Fenster, in das der Nutzer seine eigene Passphrase nicht eintippen
# kann, ist schlimmer als die Textzeile, die es ersetzt.
#
# hooks/zepos-locale und die zwoelf Dateien des Gebietsschemas stehen aus
# demselben Grund in derselben Liste, und aus einem eigenen dazu: ein
# Abbild mit dem Haken und OHNE die Daten zeigt "Passphrase wird geprft"
# und damit weniger als die Textzeile, die es ersetzt. Geprueft wird
# jeder einzelne Eintrag - faellt auch nur eine Kategorie heraus,
# scheitert setlocale als Ganzes.
#
# Die Pfade kommen ohne fuehrenden Schraegstrich: `lsinitcpio -l` listet
# sie so, gemessen am 17.08.2026 an einem Abbild, das mkinitcpio 41.1-1
# aus genau dieser Konfiguration gebaut hat.
inhalt="$(lsinitcpio -l "$image" 2>/dev/null)" || zurueck 'Das neue Abbild liess sich nicht lesen.'
pflicht_im_abbild="usr/bin/plymouthd usr/share/plymouth/themes/zepos/zepos.script hooks/zepos-locale"
for datei in $pflicht_dateien; do
    pflicht_im_abbild="$pflicht_im_abbild ${datei#/}"
done
for datei in $pflicht_im_abbild; do
    case "$inhalt" in
        *"$datei"*) ;;
        *) zurueck "Im neuen Abbild fehlt $datei." ;;
    esac
done

# Und das Gegenstueck zum Abschalt-Haken. Er legt genau eine Datei an,
# und die liegt in der Wurzel der Initramfs: `add_binary
# /usr/lib/initcpio/shutdown /shutdown` in usr/lib/initcpio/install/
# shutdown, also der Eintrag `shutdown` ohne Verzeichnis davor.
#
# ZEILENGENAU UND NICHT ALS TEILSTUECK, anders als die Liste darueber:
# `shutdown` steckt als Wort in reichlich Pfaden, die eine Initramfs
# ohnehin mitbringt (usr/lib/systemd/system/shutdown.target ist der
# naechstliegende). Eine Suche nach dem Teilstueck faende einen davon
# und meldete Erfolg fuer eine Datei, die gar nicht da ist - eine
# Pruefung, die immer ja sagt, ist keine.
printf '%s\n' "$inhalt" | grep -qE '^(\./)?shutdown$' \
    || zurueck 'Im neuen Abbild fehlt der Abschalt-Haken.'

rm -f "$sicherung_conf" "$sicherung_vconsole" "$sicherung_image"
melde 'Die Passphrase wird jetzt in einem Fenster abgefragt, nicht auf der Konsole.'
melde 'Die verschluesselte Wurzel wird beim Ausschalten sauber ausgehaengt.'
exit 0
"""
SECTOR_SIZE = {"value": 512, "unit": "B"}


def _size(value: int, unit: str = "MiB") -> dict[str, Any]:
    """archinstall's Size.parse_args requires a sector_size dict.

    Its bundled config-sample.json passes null here and is therefore not
    loadable at all - verified against 4.4, where it raises TypeError.
    """
    return {"value": value, "unit": unit, "sector_size": SECTOR_SIZE}


def _partition(planned: PlannedPartition) -> dict[str, Any]:
    """Eine geplante Partition in archinstalls Schluesselnamen.

    JEDER Schluessel hier ist Pflicht, und das ist nachgelesen und nicht
    abgeschrieben: DiskLayoutConfiguration.parse_arg (4.4-1 aus dem
    angehefteten ALA-Schnappschuss 2026/08/04, lib/models/device.py)
    greift auf 'status', 'type', 'start', 'size', 'mount_options',
    'mountpoint', 'dev_path' und 'obj_id' mit dem Index zu - ein
    fehlender Schluessel ist dort ein KeyError, keine Vorgabe. Nur
    'flags', 'fs_type' und 'btrfs' gehen ueber .get().

    status "create" und dev_path None gehoeren zusammen. Die anderen drei
    Zustaende, die archinstall kennt ('existing', 'delete', 'modify'),
    verlangen umgekehrt ein gesetztes dev_path - PartitionModification.
    __post_init__ wirft sonst "If partition marked as existing a path
    must be set". Warum ZepOS ausschliesslich anlegt, steht in
    installer/core/layout.py.
    """
    return {
        "obj_id": str(uuid.uuid4()),
        "status": "create",
        # 'primary' und nicht 'boot', auch fuer die ESP. PartitionType
        # ist eine eigene Aufzaehlung neben den Flaggen, und das, woran
        # archinstall die EFI-Partition erkennt, sind die Flaggen:
        # get_efi_partition() filtert auf is_efi(), also auf
        # PartitionFlag.ESP. PartitionType.BOOT setzt dagegen parteds
        # PARTITION_BOOT-Code, den eine GPT-Platte nicht kennt.
        "type": "primary",
        "fs_type": planned.filesystem,
        "start": _size(planned.start_mib),
        "size": _size(planned.size_mib),
        # None und nicht "", weil parse_arg genau darauf prueft
        # (`Path(partition['mountpoint']) if partition['mountpoint']`) -
        # eine Auslagerungspartition hat keinen Einhaengepunkt und wird
        # ueber swapon() eingebunden.
        "mountpoint": planned.mountpoint or None,
        "mount_options": [],
        "dev_path": None,
        "flags": list(planned.flags),
        "btrfs": [],
    }


def _planned(cfg: InstallConfig) -> list[tuple[PlannedPartition, dict[str, Any]]]:
    """Build the partition table explicitly, each entry beside its plan.

    PAARWEISE UND NICHT NUR ALS LISTE VON dicts, und das ist der ganze
    Grund fuer diese Funktion: die Verschluesselung wird in archinstalls
    Format ueber obj_id angesprochen, nicht ueber den Einhaengepunkt.
    _partition() erzeugt diese obj_id frisch je Aufruf (uuid4), also ist
    die einzige Stelle, an der man weiss, WELCHE Partition welche obj_id
    bekommen hat, genau hier. Wer die Zuordnung spaeter noch einmal
    ausrechnen wollte, muesste raten - und ein Fehlgriff waere eine
    verschluesselte EFI-Partition, also eine Maschine, die nicht startet.

    archinstall does NOT compute a layout when loading a config file. Its
    parse_arg reads partitions only from this list, and
    suggest_single_disk_layout is reachable exclusively from the
    interactive menus. An empty list combined with wipe=True would erase
    the disk and create nothing - verified against archinstall 4.4.

    config_type is therefore "manual_partitioning": the layout is ours,
    not archinstall's.

    Sizes are given in MiB rather than as a percentage: archinstall's
    Unit enum has no Percent member, so the "Percent" unit in its own
    sample raises KeyError. Verified against 4.4.

    WOHER DIE EINTELUNG KOMMT
        Aus cfg.disk.layout, wenn der Assistent eine geplant hat - das
        ist die Seite, die es seit UI-5 gibt. Sonst aus
        installer.core.layout.suggested_layout(), demselben Vorschlag,
        den diese Funktion frueher selbst ausgerechnet hat: ESP von 512
        MiB ab 1 MiB, Wurzel bis 1 MiB vor Schluss. Der Textassistent und
        jede bereits geschriebene Konfigurationsdatei laufen ueber diesen
        zweiten Weg und bekommen Byte fuer Byte, was sie vorher bekamen.

    Die Einteilung wird hier ein zweites Mal geprueft. Nicht aus
    Misstrauen gegen die Oberflaeche, sondern weil dies der Weg ist, den
    auch eine Konfigurationsdatei nimmt, die niemand durch eine
    Oberflaeche geschickt hat (`zepos-install --config datei.json`, Spec
    8.1) - und weil archinstalls eigene Pruefung erst laeuft, wenn das
    Loeschen schon angefangen hat.
    """
    plan = effective_layout(
        cfg.disk.layout, cfg.disk.size_bytes, filesystem=cfg.disk.filesystem)

    problems = layout_errors(plan, cfg.disk.size_bytes)
    if problems:
        raise ValueError(problems[0])

    return [(planned, _partition(planned)) for planned in plan]


def _disk_config(cfg: InstallConfig) -> dict[str, Any]:
    """Die Einteilung und, wenn sie verlangt wurde, die Verschluesselung.

    WO DIE VERSCHLUESSELUNG HINGEHOERT, UND WO NICHT
        In disk_config, nicht auf die oberste Ebene. archinstall 4.4
        nimmt BEIDE Schreibweisen entgegen, aber die obere nur durch
        einen Zweig, ueber dem in lib/args.py woertlich "DEPRECATED /
        backwards compatibility for main level disk_encryption entry"
        steht (Zeile 275-286). Dieselbe Ueberlegung wie bei audio_config
        eine Funktion weiter unten: ein Schluessel, den nur noch ein
        Uebergangszweig am Leben haelt, ist eine Fassung davon entfernt,
        stillschweigend ignoriert zu werden - und ein ignorierter
        Verschluesselungsschluessel ist eine Platte, die im Klartext
        liegt, waehrend der Nutzer glaubt, sie sei verschluesselt.

        Der nicht-veraltete Weg ist DiskLayoutConfiguration.parse_arg,
        die `disk_config['disk_encryption']` liest (lib/models/device.py,
        Zeile 228-229). Genau dort steht es jetzt.

    JEDER SCHLUESSEL IST NACHGELESEN, nicht abgeschrieben:
    _DiskEncryptionSerialization (lib/models/device.py, Zeile 1465)
    verlangt 'encryption_type', 'partitions' und 'lvm_volumes';
    'hsm_device' und 'iter_time' sind NotRequired.

    WARUM iter_time FEHLT
        Weil archinstalls Vorgabe genommen wird - siehe den Kopf von
        installer/core/crypt.py, wo sie gemessen ist (zehn Sekunden
        Argon2id je Entsperrung, gegen cryptsetups eigene zwei). Das
        Weglassen ist dabei nicht nur bequem, sondern die richtige Form:
        DiskEncryption.json() schreibt den Schluessel selbst nur, wenn er
        von DEFAULT_ITER_TIME abweicht ("# Only include if not default",
        Zeile 1505). Was hier entsteht, sieht also aus wie eine Datei,
        die archinstall selbst geschrieben haette.

    WARUM hsm_device FEHLT
        Weil ZepOS keinen FIDO2-Stick abfragt. Der Zweig dahinter
        vertauscht in archinstall die halbe Initramfs (sd-encrypt statt
        encrypt, siehe Installer.mkinitcpio()), und was ZepOS an dieser
        Stelle misst, ist der Weg mit der Passphrase.
    """
    paired = _planned(cfg)
    config: dict[str, Any] = {
        "config_type": "manual_partitioning",
        "device_modifications": [
            {
                "device": cfg.disk.device,
                "wipe": cfg.disk.wipe,
                "partitions": [entry for _planned_part, entry in paired],
            }
        ],
    }

    if not cfg.disk.encrypt:
        return config

    # Die beiden Faelle, in denen archinstall die Verschluesselung STILL
    # fallen liesse oder mitten im Lauf abbraeche. Beide werden hier
    # abgefangen, weil dies der Weg ist, den auch eine
    # Konfigurationsdatei nimmt, durch die niemand eine Oberflaeche
    # geschickt hat (`zepos-install --config datei.json`).
    #
    #   * OHNE PASSPHRASE gibt DiskEncryption.parse_arg schlicht None
    #     zurueck (`if not password: return None`, Zeile 1537), das
    #     disk_encryption bleibt None, und die Installation laeuft durch
    #     - mit Rueckgabewert 0 und einer unverschluesselten Platte. Das
    #     ist der gefaehrlichste Ausgang dieses ganzen Moduls: kein
    #     Fehler, kein Hinweis, nur eine Zusicherung, die nicht gilt.
    #   * OHNE VERSCHLUESSELBARE PARTITION wirft
    #     DiskEncryption.__post_init__ "Luks or LvmOnLuks encryption
    #     require partitions to be defined" (Zeile 1483). Das faellt auf,
    #     aber es faellt in archinstall auf statt hier.
    if not cfg.disk.passphrase:
        raise ValueError(_("Disk encryption was requested without a passphrase. archinstall would silently install an unencrypted system."))

    encrypted = [
        entry["obj_id"] for planned, entry in paired if is_encryptable(planned)
    ]
    if not encrypted:
        raise ValueError(_("Disk encryption was requested, but no partition in this layout can be encrypted."))

    config["disk_encryption"] = {
        "encryption_type": ENCRYPTION_TYPE_LUKS,
        "partitions": encrypted,
        # Leer und nicht weggelassen: der Schluessel ist in
        # _DiskEncryptionSerialization Pflicht, und parse_arg liest ihn
        # zwar ueber .get() - aber ZepOS legt keine LVM-Baende an, und
        # das ausdruecklich hinzuschreiben ist die Aussage, dass hier
        # keines fehlt.
        "lvm_volumes": [],
    }
    return config


def to_archinstall_config(cfg: InstallConfig, source: PackageSource) -> dict[str, Any]:
    if not cfg.disk.device:
        # Defense in depth. validate() rejects this too, but wipe defaults
        # to True and nothing forces callers to validate first.
        raise ValueError(_("No target disk was selected."))

    if cfg.disk.size_bytes // (1024 * 1024) < MIN_DISK_MIB:
        raise ValueError(
            _("The selected disk is too small. At least {minimum} MiB are required.")
            .format(minimum=MIN_DISK_MIB)
        )

    return {
        "archinstall-language": "English",
        "hostname": cfg.hostname,
        "kernels": ["linux"],
        "timezone": cfg.timezone,
        "ntp": True,
        "offline": source is PackageSource.OFFLINE,
        "packages": selected_packages(cfg),
        # Der Dienst, ohne den ein installiertes ZepOS "Reached target
        # Graphical Interface" erreicht und dann stehenbleibt - genau das
        # zeigte iso/test-boot.py --scenario release-installed.
        #
        # HIER UND NICHT IN EINEM PAKET, UND DAS IST GEMESSEN
        #     Ein Paket kann keinen Dienst aktivieren; pacman fuehrt
        #     dafuer kein systemctl aus, und ein Scriptlet, das es taete,
        #     liefe im pacstrap-Chroot gegen ein System, das noch keine
        #     Ziele kennt. archinstall 4.4 kann es: lib/args.py liest
        #     einen Schluessel "services" (Zeile 347), und
        #     scripts/guided.py gibt ihn an installation.enable_service(),
        #     die `systemctl --root=<ziel> enable` aufruft. Beides
        #     nachgelesen an der Fassung, die auf dem Medium liegt.
        #
        #     Die REIHENFOLGE in guided.py ist der Teil, der das
        #     ueberhaupt tragfaehig macht: add_additional_packages() steht
        #     dort vor enable_service(). Die Unit ist also schon da, wenn
        #     sie aktiviert wird - andersherum waere es ein
        #     "Unit greetd.service does not exist" mitten in einer sonst
        #     fertigen Installation.
        #
        # WARUM DAS REICHT, OBWOHL greetd.service KEIN WantedBy HAT
        #     Gemessen: die ausgelieferte Unit hat unter [Install] nur
        #     "Alias=display-manager.service". `systemctl --root=<dir>
        #     enable greetd.service` gegen ein nachgebautes Wurzelverzeich-
        #     nis legt daraufhin genau einen Symlink an,
        #     /etc/systemd/system/display-manager.service, und
        #     /usr/lib/systemd/system/graphical.target traegt
        #     "Wants=display-manager.service". Das ist der Weg, auf dem
        #     jeder Anmeldedienst unter Arch startet.
        #
        # DER ZWEITE EINTRAG IST DIE SELBSTAKTUALISIERUNG (UP-1)
        #     Ohne ihn haette eine frisch installierte Maschine den
        #     Zeitgeber liegen und niemanden, der ihn einschaltet. Der
        #     ALPM-Haken in zepos-config faengt den Fall der bereits
        #     installierten Maschine ab, die den Aktualisierer erst
        #     nachtraeglich bekommt - hier steht der Fall, der haeufiger
        #     ist: eine Installation von diesem Medium.
        #
        #     Der Zeitgeber und nicht der Dienst. `systemctl enable
        #     zepos-update.service` waere eine Aktualisierung bei jedem
        #     Start, sofort und ohne Streuung; der [Install]-Abschnitt
        #     steht deshalb nur in der .timer-Datei, und src/update.py
        #     sagt, warum das die einzige richtige Form ist.
        #
        # DER DRITTE EINTRAG IST BLUETOOTH, UND ER IST GEMESSEN
        #     GEMELDET am 17.08.2026: das Statusskript der Leiste friert
        #     ein. Es hat daraufhin Fristen bekommen
        #     (bar-status-config.template, `frag`) - das behebt das
        #     Einfrieren und beantwortet nicht, WARUM `bluetoothctl show`
        #     haengt.
        #
        #     GEMESSEN an der Testinstallation (iso/out/release-target
        #     .img, LUKS entsperrt, Wurzel p2), am selben Tag:
        #
        #         bluez 5.87-2, bluez-utils 5.87-2, blueman 2.4.6-2
        #             installiert - zepos-desktop nennt alle drei hart
        #         /usr/lib/systemd/system/bluetooth.service   vorhanden
        #         /etc/systemd/system/bluetooth.target.wants/ FEHLT
        #         /etc/systemd/system/dbus-org.bluez.service  FEHLT
        #
        #     Die beiden fehlenden Namen sind genau das, was `systemctl
        #     enable bluetooth.service` schreibt: die Unit traegt unter
        #     [Install] "WantedBy=bluetooth.target" UND
        #     "Alias=dbus-org.bluez.service".
        #
        #     Der Alias ist der Teil, der das Haengen erklaert.
        #     /usr/share/dbus-1/system-services/org.bluez.service - die
        #     Datei, mit der der Systembus org.bluez bei Bedarf starten
        #     koennte - nennt als Starter "SystemdService=dbus-org.bluez
        #     .service" bei "Exec=/bin/false". Ohne den Alias gibt es
        #     diesen Dienstnamen nicht: der Bus kann org.bluez WEDER
        #     starten NOCH auf einen laufenden verweisen, und
        #     bluetoothctl wartet auf einen Namen, der nie kommt.
        #
        #     Ein Paket kann das nicht heilen - der Absatz ganz oben
        #     fuehrt aus, warum Dienste HIER aktiviert werden. bluez
        #     steht als Abhaengigkeit von zepos-desktop in derselben
        #     Transaktion wie greetd, ist beim enable_service() also
        #     ebenso vorhanden.
        "services": ["greetd.service", "zepos-update.timer",
                     "bluetooth.service"],
        "locale_config": {
            "kb_layout": cfg.keymap,
            "sys_enc": "UTF-8",
            "sys_lang": cfg.locale,
        },
        "mirror_config": mirror_config(source),
        "network_config": {"type": "nm"},
        # GRUB und nicht mehr systemd-boot, und der Grund ist das, was
        # der Nutzer beim Einschalten sieht.
        #
        # Was nach einer Installation als "GRUB-Menue mit Arch Linux" auf
        # dem Schirm stand, war systemd-boot: eine Liste, die aus den
        # Dateien in /boot/loader/entries entsteht, und die sich nicht
        # themen laesst - es gibt kein Hintergrundbild, keine Schrift und
        # keine Farbe, die man ihr geben koennte. Das Installationsmedium
        # bootet dagegen seit jeher in ein gethemtes GRUB-Menue
        # (iso/profile-release/grub/), also zeigte dieselbe Maschine vor
        # der Installation ZepOS und danach nicht mehr.
        #
        # Der Name ist "Grub", mit dieser Schreibung: archinstall 4.4
        # nimmt ihn ueber Bootloader.from_arg(), das den Wert mit
        # .capitalize() normalisiert, und die Enum-Werte sind
        # 'Systemd-boot', 'Grub', 'Efistub', 'Limine', 'Refind'
        # (lib/models/bootloader.py, nachgelesen an der Fassung auf dem
        # Medium).
        #
        # grub und efibootmgr muessen NICHT in zepos-desktop stehen:
        # _add_grub_bootloader() ruft self.pacman.strap('grub') und, unter
        # UEFI, self.pacman.strap('efibootmgr') selbst auf.
        "bootloader_config": {
            "bootloader": "Grub",
            "uki": False,
            # False, obwohl Bootloader.Grub.has_removable_support() True
            # sagt. --removable schreibt den Loader nach
            # EFI/BOOT/BOOTX64.EFI, den Pfad, den eine Firmware nimmt,
            # wenn sie sonst nichts findet - richtig fuer einen USB-Stick
            # und falsch fuer eine eingebaute Platte, wo er den Eintrag
            # eines zweiten Systems ueberschreibt. Das Ziel dieser
            # Installation ist eine eingebaute Platte.
            "removable": False,
        },
        # Nested under app_config, not the top-level "audio_config" key.
        # Read against archinstall 4.4: ArchConfig.from_config still
        # accepts the top-level spelling, but only through a branch
        # commented "DEPRECATED: backwards compatibility", and the
        # configuration it writes back out uses app_config. A key kept
        # alive only by a deprecation branch is one release away from
        # being ignored in silence - and an ignored audio key means an
        # installed desktop with no sound server, which nothing in a
        # --dry-run would reveal.
        "app_config": {"audio_config": {"audio": "pipewire"}},
        "swap": {"enabled": True, "algorithm": "zstd"},
        "disk_config": _disk_config(cfg),
        "pacman_config": {"color": False, "parallel_downloads": 5},
        # Das Startmenue zuerst, die Passphrase-Abfrage danach. Die
        # Reihenfolge ist keine Abhaengigkeit, sondern eine Rangfolge:
        # der GRUB-Befehl ist der laenger gemessene von beiden, und was
        # zuerst laeuft, laeuft auch dann, wenn das zweite haengt.
        "custom_commands": [GRUB_MKCONFIG_COMMAND, PLYMOUTH_COMMAND],
        "script": "guided",
        "silent": True,
        "debug": False,
        "no_pkg_lookups": False,
    }


def to_archinstall_creds(
    cfg: InstallConfig,
    *,
    hasher: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Die Geheimnisse, getrennt von der Konfiguration.

    DIE PLATTENPASSPHRASE STEHT HIER IM KLARTEXT, und das ist keine
    Nachlaessigkeit, sondern die einzige Form, in der sie funktionieren
    kann: cryptsetup leitet daraus den Schluessel ab, und aus einem Hash
    laesst sich nichts ableiten. Deshalb gehoert sie in DIESE Datei und
    nicht in config.json - installer.core.runner schreibt creds.json mit
    verengter umask und Modus 0600 in ein Verzeichnis mit Modus 0700 und
    loescht es, sobald archinstall fertig ist.

    WO archinstall SIE ERWARTET, nachgelesen an 4.4-1: auf der obersten
    Ebene unter "encryption_password". ArgumentHandler._parse_config()
    liest config und creds in EIN Woerterbuch (`config.update(json_data)`,
    lib/args.py Zeile 700-703), und ArchConfig.from_config() nimmt den
    Wert von dort: `enc_password = args_config.get('encryption_password',
    '')` (Zeile 270). Der Schluessel gehoert also zu disk_config und
    steht trotzdem daneben - das ist archinstalls Aufteilung, nicht
    unsere, und sie ist die richtige: so kommt das Geheimnis in die Datei
    mit den Geheimnissen.

    NUR WENN VERSCHLUESSELT WIRD. Ein leerer Wert waere hier nicht
    harmlos, sondern genau die Angabe, mit der archinstall die
    Verschluesselung stillschweigend fallen laesst - und ein Schluessel,
    der manchmal "" bedeutet und manchmal "nichts angefordert", ist einer,
    bei dem niemand mehr sagen kann, was gemeint war.
    """
    # Resolved here, not bound as a default: a default argument captures
    # hash_password at import time, which the test suite's isolation guard
    # cannot intercept.
    hasher = hasher or hash_password
    creds: dict[str, Any] = {
        "users": [
            {
                "username": user.username,
                "enc_password": hasher(user.password),
                "sudo": user.sudo,
            }
            for user in cfg.users
        ],
        "root_enc_password": hasher(cfg.root_password) if cfg.root_password else None,
    }
    if cfg.disk.encrypt:
        # Dieselbe Weigerung wie in _disk_config(), und sie muss auch hier
        # stehen: die beiden Dateien werden getrennt erzeugt, und eine
        # Konfiguration mit disk_encryption neben einer creds.json ohne
        # Passphrase ist genau die Kombination, die unverschluesselt
        # durchlaeuft.
        if not cfg.disk.passphrase:
            raise ValueError(_("Disk encryption was requested without a passphrase. archinstall would silently install an unencrypted system."))
        creds["encryption_password"] = cfg.disk.passphrase
    return creds
