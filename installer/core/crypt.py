# SPDX-License-Identifier: GPL-3.0-or-later
"""Plattenverschluesselung: was verschluesselt wird, was es kostet, und
was ein Nutzer verliert, wenn er die Passphrase vergisst.

Oberflaechenfrei wie installer.core.layout: hier steht die Regel, beide
Assistenten fragen dieselben Dinge, und installer.core.translate
uebersetzt das Ergebnis in archinstalls Format.

WARUM ES DIESES MODUL GIBT
    Gemeldet am 12.08.2026: "ausserdem mache ich mir gedanken um
    verschluesselung der daten von anfang an das heisst ich will bei
    installation die daten schon immer militaer grade verschluesseln
    koennen wir das im wizard dazu bauen".

WAS "MILITAERISCH" HEISST, UND WARUM HIER TROTZDEM KEINE EIGENEN
PARAMETER STEHEN
    "Militaerisch" ist kein Fachbegriff. Was damit gemeint ist, ist in
    aller Regel AES-256 - der Algorithmus, den die NSA in ihrer CNSA-
    Liste bis einschliesslich TOP SECRET zulaesst. Die Frage ist also
    nicht, welche Zahlen man einstellt, sondern ob die Vorgabe schon
    AES-256 ist. Sie ist es.

    GEMESSEN AM 12.08.2026, nicht nachgelesen. archinstall 4.4-1 aus dem
    angehefteten ALA-Schnappschuss 2026/08/04 baut in
    lib/disk/luks.py, Luks2.encrypt(), genau diesen Aufruf:

        cryptsetup --batch-mode --verbose --type luks2
                   --pbkdf argon2id --hash sha512
                   --key-size 512 --iter-time 10000
                   --use-urandom luksFormat <geraet>

    Derselbe Aufruf, hier gegen eine 64-MiB-Datei im Zwischenspeicher
    ausgefuehrt (keine Platte, kein Geraet), und `cryptsetup luksDump`
    danach gefragt:

        Data segments: 0: crypt   cipher: aes-xts-plain64
        Keyslots:      0: luks2   Key: 512 bits
                                  Cipher: aes-xts-plain64
                                  Cipher key: 512 bits
                                  PBKDF: argon2id
                                  Time cost: 45
                                  Memory: 1048576
                                  Threads: 4

    Ein --cipher steht in dem Aufruf NICHT, also gilt cryptsetups eigene
    Vorgabe, und `cryptsetup --help` auf demselben Stand (2.8.6) nennt
    sie: "LUKS: aes-xts-plain64, Schluessel: 256 Bits" mit dem Zusatz
    "Standard-Schluesselgroesse mit XTS-Modus (zwei interne Schluessel)
    wird verdoppelt". 512 Bit im XTS-Modus sind zwei AES-Schluessel zu je
    256 Bit - also AES-256, und archinstalls --key-size 512 ist dieselbe
    Zahl, die cryptsetup von sich aus genommen haette.

    Damit ist die Antwort auf "militaerisch": die Vorgabe. Ein
    handgedrehter Parametersatz waere hier nur eine zweite Meinung ueber
    etwas, das schon richtig eingestellt ist - und jede Abweichung von
    der Vorgabe eines Werkzeugs ist eine Zeile, die jemand pflegen muss,
    wenn das Werkzeug sich aendert. Deshalb steht in diesem Modul KEIN
    Chiffrenname und KEINE Schluessellaenge: was ZepOS an archinstall
    uebergibt, ist "verschluessele diese Partitionen mit LUKS", und alles
    Weitere ist archinstalls Vorgabe.

WAS ES KOSTET, TEIL 1: DER DURCHSATZ
    Gemessen mit `cryptsetup benchmark` am 12.08.2026 auf einem Intel
    Core Ultra 7 255U (AES-NI vorhanden, das Flag `aes` steht in
    /proc/cpuinfo):

        aes-xts   512b   4820,6 MiB/s verschluesseln
                         6160,9 MiB/s entschluesseln

    Zum Vergleich, auf DERSELBEN Maschine, die Chiffren ohne
    Hardwarebefehl - das ist die Groessenordnung, in der eine CPU ohne
    AES-NI landet:

        twofish-xts 512b  477,2 MiB/s / 463,7 MiB/s
        serpent-xts 512b  707,7 MiB/s / 625,2 MiB/s

    Eine SATA-SSD schafft rund 550 MiB/s, eine NVMe-SSD einige Tausend.
    Mit AES-NI ist die Verschluesselung also nicht der Engpass; ohne
    AES-NI ist sie es fuer NVMe und liegt bei SATA gerade an der Grenze.
    Genau deshalb fragt cpu_has_aes() unten die Maschine, auf der der
    Assistent LAEUFT - und nicht die, auf der er geschrieben wurde.

WAS ES KOSTET, TEIL 2: DIE ZEHN SEKUNDEN BEIM EINSCHALTEN
    Das ist die Zahl, die ein Nutzer taeglich merkt, und sie ist die
    unangenehmere von beiden.

    archinstalls DEFAULT_ITER_TIME ist 10000 (lib/models/device.py,
    Zeile 21). Das ist die Zeit, auf die cryptsetup die Argon2id-
    Ableitung EINSTELLT - und damit auch die Zeit, die das Entsperren
    beim naechsten Start braucht. Gemessen, mit dem oben erzeugten
    LUKS-Kopf und `cryptsetup luksOpen --test-passphrase`:

        iter-time 10000 (archinstalls Vorgabe):  9,98 / 10,39 / 10,82 s
        iter-time  2000 (cryptsetups Vorgabe):   2,24 /  2,53 /  2,59 s

    archinstall weicht hier also vom Werkzeug ab, um das Fuenffache, und
    zwar nach oben. Das ist keine Nachlaessigkeit: mehr Rechenzeit je
    Versuch ist genau das, was einen Angreifer bremst, der die Platte in
    der Hand hat.

    ZepOS UEBERNIMMT DIESE VORGABE und schreibt kein eigenes iter_time.
    Zwei Gruende, und der zweite ist der wichtigere:

      * Es ist die Vorgabe des Werkzeugs, das die Arbeit macht. Wer sie
        aendert, uebernimmt die Begruendung dafuer auf Dauer.
      * Zehn Sekunden einmal beim Einschalten sind der Preis dafuer, dass
        ein Angreifer je Rateversuch ebenfalls zehn Sekunden zahlt. Wer
        sie auf zwei senkt, verbilligt das Raten um denselben Faktor
        fuenf. Der Nutzer hat "militaer grade" verlangt.

    Was ZepOS statt dessen tut: es SAGT die zehn Sekunden vorher. Sie
    stehen in unlock_note() und damit auf der Seite, auf der der Haken
    gesetzt wird - eine Maschine, die nach der Installation zehn Sekunden
    laenger braucht als vorher, sieht sonst kaputt aus.

    Der Wert wird auf der Maschine kalibriert, die formatiert, und auf
    derselben Maschine entsperrt. Eine langsamere CPU bekommt also
    weniger Argon2id-Durchlaeufe fuer dieselben zehn Sekunden - die
    Wartezeit ist auf jeder Maschine ungefaehr gleich, der Schutz ist es
    nicht.

WAS BEIM START PASSIERT - UND WARUM DAS GETHEMTE STARTMENUE BLEIBT
    Alles an archinstall 4.4 nachgelesen und hier aufgeschrieben, weil es
    die erste Oberflaeche ist, die ein Nutzer nach der Installation
    sieht - noch vor dem Startmenue-Thema und lange vor der Anmeldemaske.

      * Die ESP liegt bei ZepOS auf /boot (installer.core.layout,
        ESP_MOUNTPOINT), ist FAT32 und wird NICHT verschluesselt. Kernel
        und Initramfs liegen also im Klartext, GRUB liest sie ohne
        Schluessel, und GRUB_ENABLE_CRYPTODISK wird nirgends gebraucht.
        Das gethemte GRUB-Menue erscheint unveraendert.
      * Danach fragt die Initramfs. archinstall setzt dafuer
        GRUB_CMDLINE_LINUX auf `cryptdevice=UUID=<luks>:root`
        (lib/installer.py, _add_grub_bootloader() ruft
        _get_kernel_params(root, id_root=False, partuuid=False)) und
        haengt in mkinitcpio den `encrypt`-Haken vor `filesystems`
        (_prepare_encrypt()).
      * Der Haken ist der klassische, nicht der systemd-Haken:
        Installer.mkinitcpio() ersetzt ohne HSM `systemd` durch `udev`
        und `sd-vconsole` durch `keymap consolefont`. Was archinstall
        damit hinterlaesst, ist eine Textzeile auf der Konsole - bis zum
        13.08.2026 war das auch das, was ein Nutzer sah, und
        iso/out/run-release-installed/screen-0060s.png zeigt es.
      * SEIT DEM 13.08.2026 IST ES EIN FENSTER. ZepOS haengt nach der
        Installation `plymouth` vor `encrypt` in die HOOKS-Zeile und
        baut die Initramfs neu; der encrypt-Haken von mkinitcpio 41-4
        fragt von sich aus, ob plymouthd laeuft, und geht dann ueber
        `plymouth ask-for-password`. Wo das steht und warum es dort
        steht und nicht in einem Paket: installer/core/translate.py,
        PLYMOUTH_COMMAND. Was passiert, wenn plymouthd auf einer
        Maschine nicht hochkommt: derselbe Haken faellt in seinen
        else-Zweig zurueck, und dann steht dort wieder die Textzeile -
        niemand wird ausgesperrt, weil ein Bild nicht ging.
      * UND SIE BENUTZT DIE TASTATURBELEGUNG AUS /etc/vconsole.conf, die
        archinstall aus locale_config.kb_layout schreibt - das Fenster
        genauso wie die Textzeile davor. Plymouth zeichnet vor jedem
        Toolkit und bekommt seine Tasten nicht ueber XKB, sondern ueber
        den Konsolentreiber; die Belegung ist die, die der `keymap`-
        Haken geladen hat, und der steht in der HOOKS-Zeile vor
        `encrypt`. Das ist der Teil, der einen Menschen aus seiner
        eigenen Platte aussperren kann: wer die Passphrase mit z, y oder
        einem Umlaut auf einer deutschen Tastatur eingibt und am
        Startbildschirm eine amerikanische vorfindet, tippt etwas
        anderes als das, was er gesetzt hat - und sieht es hinter den
        Punkten nicht. Genau diese Kette hat dieses Projekt schon einmal
        getroffen (XKB_DEFAULT_LAYOUT im Live-Compositor, siehe
        iso/test-boot.py) - dort kostete es ein Benutzerkonto, hier
        kostet es die Platte. tests/installer/test_crypt.py haelt
        deshalb fest, dass eine verschluesselte Konfiguration niemals
        ohne kb_layout hinausgeht, und iso/test-boot.py tippt seit dem
        13.08.2026 eine Passphrase MIT y und z, damit ein Lauf es
        merkt.
      * ZepOS erzeugt das Startmenue anschliessend ein zweites Mal
        (installer.core.translate, GRUB_MKCONFIG_COMMAND). Das ist
        unschaedlich: guided.py ruft add_bootloader() VOR
        run_custom_user_commands(), /etc/default/grub traegt den
        cryptdevice-Parameter zu diesem Zeitpunkt also schon.

WAS EIN NUTZER VERLIERT
    Alles. Es gibt keine Wiederherstellung, keinen Zweitschluessel und
    keine Hintertuer - das ist der Sinn der Sache und nicht ein Mangel.
    Ein vergessenes Anmeldepasswort laesst sich von einem Live-Medium aus
    zuruecksetzen; eine vergessene LUKS-Passphrase laesst sich nicht
    zuruecksetzen, weil ohne sie der Hauptschluessel nicht entpackt
    werden kann, mit dem die Daten verschluesselt sind.

    Deshalb ist loss_warning() unten kein Hinweis, sondern eine Warnung,
    und deshalb steht sie an ZWEI Stellen: auf der Seite, auf der die
    Passphrase eingegeben wird, und in der letzten Rueckfrage vor dem
    Loeschen.
"""
from __future__ import annotations

from pathlib import Path

from .i18n import _
from .layout import ESP_MOUNTPOINT, PlannedPartition, suggested_layout

# Der Wert, den archinstall fuer "LUKS" in einer Konfigurationsdatei
# erwartet. Nachgelesen an 4.4-1: EncryptionType ist eine StrEnum, deren
# Mitglieder mit auto() erzeugt werden, und auto() liefert dort den
# kleingeschriebenen Mitgliedsnamen. Nachgemessen mit derselben
# Klassendefinition in einem eigenen Interpreter: 'no_encryption',
# 'luks', 'lvm_on_luks', 'luks_on_lvm'.
#
# Ein falscher Wert waere hier kein stiller Fehler, sondern ein
# ValueError aus EncryptionType(...) beim Einlesen der Konfiguration -
# also bevor irgendetwas geloescht wird. Das ist der freundliche Fall;
# den unfreundlichen faengt installer.core.validate ab.
ENCRYPTION_TYPE_LUKS = "luks"

# Wo die CPU-Merkmale stehen. Als Konstante und nicht als Literal im
# Rumpf, damit ein Test eine nachgebaute Datei unterschieben kann - wie
# installer.core.firmware es mit /sys/firmware/efi macht.
CPUINFO_PATH = Path("/proc/cpuinfo")

# Die Untergrenze fuer eine Passphrase.
#
# WARUM SIE NICHT MIN_PASSWORD_LENGTH IST, obwohl das die Zahl waere, die
# in diesem Programm schon existiert (8, in installer.core.validate):
# weil es ein anderer Angriff ist und ein anderer Ausgang.
#
#   * Ein Anmeldepasswort verteidigt ein LAUFENDES System. Wer es raten
#     will, muss an einer Anmeldemaske raten, die zaehlt und wartet.
#   * Eine LUKS-Passphrase verteidigt eine Platte, die jemand in der Hand
#     hat. Er raet, so oft er will, so schnell seine Hardware es
#     zulaesst, und niemand merkt es.
#
# Was das an Zeit heisst, mit der oben gemessenen Zahl: rund zehn
# Sekunden Argon2id je Versuch auf EINEM Kern-Satz, und Argon2id will
# dabei 1 GiB Speicher (gemessen: Memory 1048576). Der Speicher ist die
# eigentliche Bremse - eine Grafikkarte mit 24 GiB kann davon zwei
# Dutzend Versuche gleichzeitig fahren, nicht zehntausend. Rechnet man
# einem Angreifer grosszuegig 2000 Versuche je Sekunde zu, dann ist eine
# Liste von 10^10 realistischen Menschenpassworten in gut zwei Monaten
# durch. Acht Zeichen liegen in dieser Liste. Zwoelf liegen es seltener.
#
# WAS DIESE ZAHL NICHT IST: eine Zusicherung. Zwoelf Zeichen sind eine
# Untergrenze und kein Mass fuer Entropie - "passwortpasswort" ist
# sechzehn Zeichen lang und in jeder Liste. Was eine Laengenpruefung
# leisten kann, ist das kuerzeste und meistangegriffene Band
# auszuschliessen; mehr behauptet sie hier auch nicht.
MIN_PASSPHRASE_LENGTH = 12


def is_encryptable(planned: PlannedPartition) -> bool:
    """Ob diese geplante Partition verschluesselt werden DARF.

    Die Regel ist archinstalls eigene, nachgelesen an 4.4-1 in
    lib/disk/encryption_menu.py, select_partitions_to_encrypt():

        # do not allow encrypting the boot partition
        partitions += [p for p in mod.partitions
                       if p.mountpoint != Path('/boot') and not p.is_swap()]

    Abgeschrieben wird sie nicht, sondern hier noch einmal begruendet,
    weil die beiden Ausnahmen aus verschiedenen Gruenden bestehen:

    DIE EFI-SYSTEMPARTITION KANN NICHT.
        Sie ist das, was die Firmware liest, bevor irgendetwas laeuft,
        das entschluesseln koennte. Bei ZepOS liegt sie auf /boot und
        traegt deshalb auch Kernel und Initramfs - verschluesselte sie
        jemand, faende GRUB nichts zu starten und die Maschine bliebe
        vor einem leeren Menue stehen. Sie MUSS lesbar bleiben.

    DIE AUSLAGERUNG WIRD HIER NICHT VERSCHLUESSELT, und das ist eine
    Luecke, die dieser Assistent AUSSPRICHT statt sie zu verstecken:
        archinstall schliesst sie in seinem eigenen Menue aus, und was
        ZepOS vorschlaegt, hat gar keine Auslagerungspartition - die
        Auslagerung ist zram im Arbeitsspeicher (siehe
        installer.core.layout.suggested_layout). Wer sich auf der
        Partitionierungsseite trotzdem eine anlegt, bekommt sie im
        Klartext, und darin kann alles stehen, was der Rechner je im
        Speicher hatte. plaintext_warnings() unten sagt das auf der
        Seite, auf der es noch zu aendern ist.
    """
    return planned.mountpoint != ESP_MOUNTPOINT and not planned.is_swap()


def effective_layout(
    layout: list[PlannedPartition], size_bytes: int, *, filesystem: str = "ext4"
) -> list[PlannedPartition]:
    """Die Einteilung, die wirklich installiert wird.

    Eine leere Liste heisst nicht "keine Partitionen", sondern "niemand
    hat sich geaeussert" - siehe installer.core.model.DiskChoice.layout -
    und dafuer steht der Vorschlag ein. Genau diese Ersetzung stand
    vorher in installer.core.translate._partitions() und musste, seit
    installer.core.validate dieselbe Frage stellt, an zwei Stellen
    stimmen. Zwei Kopien einer Regel sind zwei Kopien, die einzeln
    geaendert werden koennen; hier ist eine.
    """
    return list(layout) or suggested_layout(size_bytes, filesystem=filesystem)


def encrypted_partitions(
    layout: list[PlannedPartition],
) -> list[PlannedPartition]:
    """Die Partitionen, die eine Passphrase bekommen."""
    return [planned for planned in layout if is_encryptable(planned)]


def plaintext_partitions(
    layout: list[PlannedPartition],
) -> list[PlannedPartition]:
    """Die Partitionen, die im Klartext bleiben - die Gegenliste.

    Getrennt aufgehoben und nicht als "alles andere" ausgerechnet, weil
    sie das ist, was auf der Seite STEHEN muss. Eine Verschluesselung,
    von der jemand glaubt, sie umfasse die ganze Platte, waehrend eine
    Auslagerungspartition daneben offen liegt, ist schlimmer als keine:
    sie fuehrt zu Entscheidungen, die man ohne sie nicht treffen wuerde.
    """
    return [planned for planned in layout if not is_encryptable(planned)]


def passphrase_error(passphrase: str, confirm: str) -> str:
    """Was an der eingegebenen Passphrase nicht stimmt, oder "".

    Dieselbe Sorgfalt wie bei den Benutzerpasswoertern - Eingabe,
    Wiederholung, beide geprueft - und aus demselben Grund wie dort: eine
    verdeckte Eingabe zeigt dem Tippenden seinen Tippfehler nicht. Der
    Unterschied zu dort ist der Ausgang. Ein falsch getipptes
    Benutzerpasswort ist ein Konto, in das man nicht hineinkommt und das
    root zuruecksetzt; eine falsch getippte Plattenpassphrase ist eine
    Platte, in die NIEMAND mehr hineinkommt.

    Gibt eine Zeichenkette zurueck statt zu werfen, wie jede andere
    Feldpruefung in diesem Programm: der Aufrufer ist eine Eingabezeile,
    die bei jedem Tastendruck neu fragt.
    """
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        return _("The passphrase is too short. At least {minimum} characters are required, and there is no way to reset it later.").format(
            minimum=MIN_PASSPHRASE_LENGTH)
    if passphrase != confirm:
        return _("The passphrases do not match.")
    return ""


def cpu_has_aes(*, cpuinfo: Path | None = None) -> bool:
    """Ob diese CPU AES in Hardware kann (AES-NI).

    Der Pfad wird beim Aufruf aufgeloest und nicht als Vorgabewert
    gebunden - dieselbe Regel wie ueberall sonst in diesem Paket, damit
    ein Test eine nachgebaute Datei unterschieben kann.

    Gesucht wird das Wort `aes` in einer flags-Zeile, und zwar als ganzes
    Wort zwischen Leerzeichen. Ein `in`-Test auf die ganze Datei faende
    auch `aes` in einem Modellnamen; die Flags stehen dagegen als
    leerzeichengetrennte Liste hinter "flags\t: ".

    Eine nicht lesbare /proc/cpuinfo ergibt False, also die pessimistische
    Antwort. Der Aufrufer benutzt sie, um eine WARNUNG zu zeigen; eine
    Warnung zu viel ist ein Satz zu viel, eine Warnung zu wenig ist eine
    Maschine, die nach der Installation unerklaerlich langsam ist.
    """
    path = cpuinfo or CPUINFO_PATH
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip() == "flags":
            if "aes" in value.split():
                return True
    return False


def loss_warning() -> str:
    """Der eine Satz, den niemand ueberlesen darf.

    Er steht auf der Verschluesselungsseite UND in der letzten
    Rueckfrage. Zweimal derselbe Satz und nicht zwei verschiedene: wer
    ihn beim zweiten Mal wiedererkennt, hat ihn beim ersten Mal gelesen,
    und zwei Formulierungen derselben Warnung sind zwei, die
    auseinanderlaufen koennen.
    """
    return _("If you lose this passphrase, every file on this disk is lost with it. There is no reset, no second key and no back door - not by ZepOS, not by anybody. Write it down and keep it somewhere that is not this computer.")


def unlock_note() -> str:
    """Was die Verschluesselung im Betrieb kostet, in einem Satz.

    Die zehn Sekunden sind gemessen (siehe Modulkopf) und stehen hier,
    weil eine Maschine, die nach der Installation zehn Sekunden laenger
    zum Starten braucht als vorher, ohne diesen Satz kaputt aussieht.
    """
    return _("At every start ZepOS asks for this passphrase before anything else appears, and unlocking then takes about ten seconds. That wait is the protection: an attacker guessing at your disk pays it for every attempt.")


def keyboard_note() -> str:
    """Die Warnung, die eine Platte rettet.

    Die Passphrase wird spaeter in einem eigenen Fenster abgefragt
    (Plymouth, siehe installer/core/translate.py, PLYMOUTH_COMMAND), und
    dieses Fenster liegt VOR jedem Toolkit: es zeichnet aus der
    Initramfs direkt in den Bildspeicher.

    SEINE TASTEN KOMMEN TROTZDEM UEBER XKB, und das ist am 13.08.2026
    an der ausgelieferten Initramfs gemessen worden - nachdem ein Lauf
    das Fenster zeigte und die Passphrase nicht annahm: `objdump -p` auf
    libply-splash-core.so.5 nennt libevdev.so.2 und libxkbcommon.so.0
    als NEEDED, und plymouth setzt KDSKBMODE auf dem Terminal, uebersetzt
    also selbst. Der Konsolentreiber und mit ihm der `keymap`-Haken haben
    auf diese Abfrage keinen Einfluss.

    Die Belegung nimmt plymouth aus /etc/vconsole.conf IN DER INITRAMFS
    (Zeichenketten `parse_vconsole_conf` und `XKBLAYOUT` im selben
    Maschinencode). Der initcpio-Haken von plymouth kopiert diese Datei
    nicht hinein; PLYMOUTH_COMMAND tut es ueber die FILES-Zeile und
    laesst die Abfrage sonst eine Textzeile bleiben. Damit gilt der Satz
    unten wieder: es ist die Belegung, die auf der ersten Seite gewaehlt
    wurde (gemessen an der Zielplatte vom 13.08.2026: KEYMAP=de-latin1,
    XKBLAYOUT=de).

    Es ist also DIESELBE Belegung, die hier gewaehlt wurde, und trotzdem
    steht der Satz weiter da. Der Grund hat sich nur verschoben: er
    warnte vorher davor, dass eine Textzeile eine andere Oberflaeche ist
    als dieses Fenster, und er sagt jetzt, WELCHE Belegung das Fenster
    beim Start benutzt. Wer sich darauf nicht verlassen will, nimmt
    Zeichen, die auf jeder Belegung an derselben Stelle liegen. Das ist
    ein Rat und keine Regel: eine Passphrase auf Buchstaben und Ziffern
    einzuschraenken waere eine Schwaechung, die dieses Programm nicht
    erzwingen darf.
    """
    return _("At the start ZepOS asks for this passphrase in its own window, before the desktop exists. That window uses the keyboard layout you chose on the first page, so letters such as y and z and any accented character land where that layout puts them - and you cannot see it, because the characters stay hidden.")


def accelerator_note(*, cpuinfo: Path | None = None) -> str:
    """Was die Verschluesselung DIESE Maschine an Durchsatz kostet, oder
    "" wenn die Antwort "so gut wie nichts" ist.

    Nur die schlechte Nachricht wird gesagt. Auf einer Maschine mit
    AES-NI ist die Verschluesselung nicht der Engpass (gemessen: 4820
    MiB/s gegen die 550 MiB/s einer SATA-SSD), und ein Satz, der
    "kostet Sie nichts" sagt, ist ein Satz, den man beim naechsten Mal
    auch dann ueberliest, wenn dort etwas anderes steht.
    """
    if cpu_has_aes(cpuinfo=cpuinfo):
        return ""
    return _("This processor has no AES hardware support, so encryption runs in software. Expect roughly 500 MB/s instead of several thousand - noticeable on a fast SSD, not on an older one.")


def plaintext_warnings(layout: list[PlannedPartition]) -> list[str]:
    """Was trotz Verschluesselung offen liegt, je Partition eine Zeile.

    Die EFI-Systempartition steht IMMER darunter und wird nicht
    verschwiegen, obwohl sie harmlos ist: dort liegen Kernel und
    Initramfs und sonst nichts, und wer nicht weiss, dass sie offen ist,
    wundert sich spaeter, warum eine "vollverschluesselte" Platte einen
    lesbaren Anfang hat.

    Eine Auslagerungspartition ist dagegen nicht harmlos, und sie bekommt
    deshalb ihren eigenen Satz statt in einer Aufzaehlung mitzulaufen.
    """
    findings: list[str] = []
    for planned in plaintext_partitions(layout):
        if planned.is_swap():
            findings.append(_("A swap partition stays unencrypted. Anything the machine held in memory can end up there in the clear, including what you were working on."))
        else:
            findings.append(_("The EFI system partition stays unencrypted. It has to: the firmware reads it before anything could decrypt it. It carries the kernel and the start-up files, not your data."))
    return findings
