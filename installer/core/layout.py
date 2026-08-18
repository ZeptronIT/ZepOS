# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Einteilung einer Platte, so wie der Assistent sie plant.

Oberflaechenfrei wie installer.core.disks: hier steht, was eine geplante
Partition ist, welche Einteilung vorgeschlagen wird und welche Einteilung
gar nicht erst weitergereicht werden darf. Die GTK-Seite fuellt diese
Liste, der Textassistent koennte dieselbe fuellen, und
installer.core.translate uebersetzt sie in archinstalls Format.

WARUM ES DIESES MODUL UEBERHAUPT GIBT
    Gemeldet als "ausserdem soll man im wizard die festplatten bereinigen
    koennen und neu zuweisen mit partitionen usw. das fehlt noch
    komplett". Der Assistent konnte eine Platte aussuchen und loeschen
    lassen; was auf ihr liegt, sah man nicht, und die Einteilung, die
    danach entsteht, war eine Konstante in translate.py.

WARUM JEDE GEPLANTE PARTITION NEU ANGELEGT WIRD - UND KEINE BEHALTEN
    Das ist die Entscheidung, die dieses Modul klein und pruefbar haelt,
    und sie ist gemessen, nicht geraten.

    archinstall 4.4 nimmt in einer Einteilung auch Partitionen mit
    status "existing" oder "delete" entgegen - beide verlangen aber ein
    gesetztes dev_path (lib/models/device.py, PartitionModification.
    __post_init__ wirft sonst "If partition marked as existing a path
    must be set"), und BEIDE gehen anschliessend durch dieselbe
    Ueberlappungspruefung wie die neuen (DiskLayoutConfiguration.
    parse_arg: "Partitions overlap"). Der Startsektor einer vorhandenen
    Partition muesste also auf den Sektor genau stimmen, sonst weist
    archinstall die GANZE Konfiguration zurueck - mitten in einer sonst
    fertigen Installation. Die einzige Quelle dafuer waere lsblks
    START-Spalte, deren Wert dieses Programm nie gegen die
    Partitionstabelle nachprueft, die parted dann tatsaechlich vorfindet.

    Spec 8 sagt dazu: "Partitionierung, Bootloader und Basisinstallation
    uebernimmt ausschliesslich archinstall. Ein eigener Partitionierer
    waere Code, dessen Fehler fremde Festplatten loeschen." Eine geplante
    Einteilung, die vorhandene Partitionen stehen laesst, ist genau
    dieser Code. Also: die Platte wird geleert, die Einteilung ist neu,
    und die Seite sagt vorher, was dabei verlorengeht.

WAS "BELEGUNG" HIER HEISSEN KANN UND WAS NICHT
    Nicht der Fuellstand der Dateisysteme. Gemessen mit
    `lsblk -b -P -o NAME,PKNAME,SIZE,FSTYPE,LABEL,START,FSUSE%` auf
    dieser Maschine am 11.08.2026: FSUSE% ist genau bei den eingehaengten
    Partitionen gefuellt ("6%" fuer /dev/nvme0n1p1) und bei jeder anderen
    leer - lsblk fragt dafuer statvfs, und das gibt es ohne Einhaengepunkt
    nicht. installer.core.disks.list_disks() wirft ausserdem jede Platte
    weg, auf der irgendetwas eingehaengt ist. Eine Spalte "Belegung" aus
    FSUSE% waere auf dieser Seite also fuer JEDE anzeigbare Platte leer.

    Was stattdessen geht und dieselbe Frage beantwortet: wie viel von der
    Platte durch Partitionen vergeben ist und wie viel frei bleibt. Das
    steht in der Partitionstabelle und braucht kein Dateisystem -
    allocated_mib() und free_mib() unten.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .disks import human_size
from .i18n import _

# Wo die erste Partition fruehestens anfangen darf und wie viel am Ende
# frei bleiben muss.
#
# Beides ist archinstalls eigene Rechnung, nachgelesen an 4.4-1 aus dem
# angehefteten ALA-Schnappschuss 2026/08/04
# (usr/lib/python3.14/site-packages/archinstall/lib/models/device.py):
#
#   * Size.is_valid_start() ist `self >= Size(1, Unit.MiB, ...)`, und
#     DiskLayoutConfiguration.parse_arg wirft fuer die erste anzulegende
#     Partition sonst "First partition must start at no less than 1 MiB".
#   * Size.gpt_end() ist `self - Size(1, Unit.MiB, ...)`, und dieselbe
#     Funktion wirft "Partition overlaps backup GPT header", wenn die
#     letzte Partition darueber hinausgeht.
ALIGNMENT_MIB = 1
GPT_TAIL_MIB = 1

# Ebenfalls von dort: `if part.start != part.start.align() or
# part.length != part.length.align(): raise ValueError('Partition is
# misaligned')`, und align() rundet auf volle MiB ab. Deshalb rechnet
# dieses Modul ausschliesslich in ganzen MiB - eine Groesse, die sich
# nicht in MiB ausdruecken laesst, kann gar nicht erst entstehen.
MIB = 1024 * 1024

# Die EFI-Systempartition. 512 MiB, weil dort bei GRUB der Kernel und die
# Initramfs liegen (--efi-directory=/boot, siehe die Begruendung fuer den
# Einhaengepunkt weiter unten) und ein Kernel samt Rueckfall-Initramfs
# heute rund 150 MiB braucht.
ESP_SIZE_MIB = 512

# Was archinstall selbst als Untergrenze nennt: Installer._verify_boot_part
# wirft unter 200 MiB "The boot partition ... is not large enough to
# install a boot loader". Gemessen an 4.4-1: der Aufruf ist in
# sanity_check() auskommentiert, die Grenze gilt dort also gerade NICHT -
# weshalb sie hier steht. Eine 64-MiB-ESP faellt sonst erst auf, wenn
# grub-install auf einer schon geloeschten Platte keinen Platz mehr hat.
MIN_ESP_MIB = 200

# Genug fuer ein Basissystem plus zepos-desktop. Dieselbe Zahl, aus der
# MIN_DISK_MIB unten entsteht.
MIN_ROOT_MIB = 2048

# Die Untergrenze fuer eine ganze Platte, hergeleitet statt hingeschrieben:
# ESP + Ausrichtung + GPT-Schwanz + Wurzel. Stand als Konstante 2562 in
# model.py, das sie jetzt von hier bezieht - zwei Zahlen, die dasselbe
# meinen und getrennt gepflegt werden, sind die Sorte Fehler, die erst
# auffaellt, wenn eine von beiden geaendert wurde.
MIN_DISK_MIB = ESP_SIZE_MIB + ALIGNMENT_MIB + GPT_TAIL_MIB + MIN_ROOT_MIB

# Der Einhaengepunkt der ESP. /boot und nicht /efi, weil
# installer.core.translate GRUB einsetzt und dessen Aufruf in archinstall
# `--efi-directory=<mountpoint der ESP>` ist: liegt die ESP auf /efi,
# muesste /boot eine eigene Partition auf der Wurzel sein, und dann sind
# es zwei Partitionen, wo eine reicht.
ESP_MOUNTPOINT = "/boot"

# Die Flaggen, an denen archinstall die ESP wiedererkennt. BEIDE werden
# gebraucht und aus zwei verschiedenen Gruenden - nachgelesen an 4.4-1:
# DeviceModification.get_efi_partition() filtert auf is_efi() (Flagge
# "esp") UND einen gesetzten Einhaengepunkt, get_boot_partition() auf
# is_boot() (Flagge "boot"), und Installer.add_bootloader() wirft ohne
# die zweite "Could not detect boot at mountpoint".
ESP_FLAGS = ("boot", "esp")

# Die Dateisysteme, die angeboten werden. Jeder Wert ist ein Mitglied von
# archinstalls FilesystemType (lib/models/device.py, StrEnum) - ein Name,
# den die Aufzaehlung nicht kennt, laesst FilesystemType(fs_type) beim
# Laden der Konfiguration mit einem ValueError auflaufen.
#
# f2fs und ntfs bleiben weg: das erste braucht ein eigenes
# mkfs-Paket auf dem Medium, das zweite ist kein Dateisystem, auf dem ein
# Linux wurzeln kann. Was hier steht, ist das, was ZepOS auch installiert
# bekommt.
FILESYSTEMS = ("ext4", "btrfs", "xfs", "fat32", "linux-swap")

# Das Dateisystem einer EFI-Systempartition. Die Firmware liest FAT, und
# nur FAT.
ESP_FILESYSTEM = "fat32"

# Auslagerung hat keinen Einhaengepunkt. archinstall erkennt sie am
# Dateisystem: PartitionModification.is_swap() ist
# `self.fs_type == FilesystemType.LINUX_SWAP`, und Installer._mount_partition
# ruft dafuer swapon() statt mount().
SWAP_FILESYSTEM = "linux-swap"

# Die Einhaengepunkte, die zur Wahl stehen. Eine Liste und kein freies
# Textfeld: ein vertipptes "/hom" ist eine Partition, die im installierten
# System niemand findet, und der Assistent koennte es nicht von einer
# gewollten Entscheidung unterscheiden.
MOUNTPOINTS = ("/", "/home", "/var", "/srv")

# "20G", "512M", "1,5 TiB". Zahl, optionales Dezimalzeichen, Einheit.
_SIZE = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(B|K|KI?B|M|MI?B|G|GI?B|T|TI?B)\s*$",
    re.IGNORECASE)

# Was jede Einheit in MiB bedeutet. Binaer, nicht dezimal: der Rest des
# Programms (installer.core.disks.human_size) rechnet ebenfalls in KiB,
# MiB, GiB, und eine Seite, auf der "20G" eingegeben wird und "18.6 GiB"
# erscheint, sieht nach einem Fehler aus.
_UNIT_MIB: dict[str, float] = {
    "B": 1 / MIB,
    "K": 1 / 1024, "KB": 1 / 1024, "KIB": 1 / 1024,
    "M": 1, "MB": 1, "MIB": 1,
    "G": 1024, "GB": 1024, "GIB": 1024,
    "T": 1024 * 1024, "TB": 1024 * 1024, "TIB": 1024 * 1024,
}

# Das Wort, das "so gross wie moeglich" heisst. Beide Sprachen werden
# angenommen, egal welche gerade eingestellt ist: der Assistent laeuft auf
# einem Medium, dessen Sprache jemand gerade erst umgestellt haben kann,
# und ein Wort, das in der anderen Sprache noch richtig war, darf nicht
# plotzlich eine Fehlermeldung sein.
REST_WORDS = ("rest", "max", "maximum", "alles", "all", "*")


@dataclass(frozen=True)
class PlannedPartition:
    """Eine Partition, die angelegt werden soll.

    Start und Groesse getrennt und beide in MiB, weil archinstall genau
    das verlangt (siehe ALIGNMENT_MIB oben) und weil eine Einteilung, die
    nur Groessen kennt, keine Luecke ausdruecken kann - und eine Luecke ist
    das, was nach dem Entfernen einer Partition aus der Mitte uebrig
    bleibt.
    """

    start_mib: int
    size_mib: int
    filesystem: str
    mountpoint: str = ""
    flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def end_mib(self) -> int:
        """Das erste MiB, das schon NICHT mehr zu dieser Partition
        gehoert - dieselbe Rechnung wie archinstalls
        PartitionModification.end (`self.start + self.length`), damit die
        Ueberlappungspruefung hier und dort dasselbe Ergebnis hat."""
        return self.start_mib + self.size_mib

    def is_esp(self) -> bool:
        return "esp" in self.flags

    def is_root(self) -> bool:
        return self.mountpoint == "/"

    def is_swap(self) -> bool:
        return self.filesystem == SWAP_FILESYSTEM

    def describe(self) -> str:
        """Die eine Zeile, die eine geplante Partition benennt.

        Der Einhaengepunkt zuerst, weil er das ist, wonach jemand die
        Zeile sucht - "wo ist meine Wurzel". Die Auslagerung hat keinen
        und wird deshalb benannt statt leer gelassen.
        """
        if self.is_esp():
            name = _("EFI system partition ({mountpoint})").format(
                mountpoint=self.mountpoint)
        elif self.is_swap():
            name = _("Swap")
        elif self.mountpoint:
            name = self.mountpoint
        else:
            name = _("no mount point")
        return f"{name} \N{EN DASH} {human_mib(self.size_mib)}"

    def describe_contents(self) -> str:
        """Dateisystem und Lage, unter der Zeile darueber.

        Die Lage ist nicht Zierrat: sie ist das Einzige, woran man auf der
        Seite sieht, dass zwischen zwei Partitionen eine Luecke steht.

        Der Aufzaehlungspunkt steht ausserhalb von _(), wie in
        installer.core.disks.describe_contents und aus demselben Grund:
        die Vollstaendigkeitspruefung in tests/installer/test_i18n.py
        liest die msgids aus dem QUELLTEXT, und dort stuende "\\N{BULLET}"
        statt des Zeichens, das gettext zur Laufzeit nachschlaegt.
        """
        span = _("{start} to {end}").format(
            start=human_mib(self.start_mib), end=human_mib(self.end_mib))
        return f"{self.filesystem} \N{BULLET} {span}"


def human_mib(size_mib: int) -> str:
    """Eine MiB-Zahl so schreiben, wie die Plattenliste ihre Byte-Zahlen
    schreibt. Kein zweites Format fuer dieselbe Sache auf derselben
    Seite."""
    return human_size(size_mib * MIB)


def disk_mib(disk_size_bytes: int) -> int:
    """Die Platte in ganzen MiB. Abgerundet, immer: das letzte
    angefangene MiB ist Platz, den archinstall nicht vergeben kann."""
    return disk_size_bytes // MIB


def last_usable_mib(disk_size_bytes: int) -> int:
    """Das erste MiB hinter dem letzten, das eine Partition belegen darf.

    Das ist archinstalls total_size.gpt_end(), also die Plattengroesse
    minus dem MiB, in dem die Sicherungskopie des GPT-Kopfes liegt.
    """
    return disk_mib(disk_size_bytes) - GPT_TAIL_MIB


def suggested_layout(
    disk_size_bytes: int, *, filesystem: str = "ext4"
) -> list[PlannedPartition]:
    """Der Vorschlag: eine EFI-Systempartition, und der Rest ist Wurzel.

    WARUM KEINE EIGENE AUSLAGERUNGSPARTITION
        Weil es die Auslagerung schon gibt und sie kein Stueck Platte
        kostet. installer.core.translate schreibt
        "swap": {"enabled": True, "algorithm": "zstd"}, und das ist bei
        archinstall 4.4 zram und nicht eine Partition: scripts/guided.py
        ruft dafuer installation.setup_swap(algo=...), und die Funktion
        schreibt /etc/systemd/zram-generator.conf und aktiviert
        systemd-zram-setup@zram0.service (lib/installer.py, Zeile 1032 ff.
        der Fassung aus dem ALA-Schnappschuss). Sie setzt dabei
        _zram_enabled, woraufhin archinstall zswap abschaltet.

        Eine Auslagerungspartition zusaetzlich waere also Auslagerung
        zweimal, davon einmal langsamer und auf Kosten der Wurzel. Wer den
        Ruhezustand auf die Platte braucht, kann sie ausdruecklich
        hinzufuegen - das Dateisystem dafuer steht in FILESYSTEMS.

    WARUM KEIN EIGENES /home
        Weil die Aufteilung zwischen / und /home hier festgelegt wuerde,
        auf einer Maschine, von der niemand weiss, wofuer sie benutzt
        wird. Der haeufige Ausgang ist eine volle Wurzel neben freiem
        Platz in /home, und das ist nach der Installation nur noch mit
        Werkzeug zu aendern. Ein Dateisystem ueber die ganze Platte hat
        dieses Problem nicht. Wer die Trennung will, legt sie an - dafuer
        ist die Seite da.

    Eine leere Liste, wenn die Platte den Vorschlag nicht traegt. Der
    Aufrufer sieht das als "keine Einteilung" und layout_errors() sagt
    warum; eine Wurzel mit negativer Groesse waere die Alternative.
    """
    total = disk_mib(disk_size_bytes)
    root_start = ALIGNMENT_MIB + ESP_SIZE_MIB
    root_mib = total - root_start - GPT_TAIL_MIB
    if root_mib < MIN_ROOT_MIB:
        return []
    return [
        PlannedPartition(
            start_mib=ALIGNMENT_MIB,
            size_mib=ESP_SIZE_MIB,
            filesystem=ESP_FILESYSTEM,
            mountpoint=ESP_MOUNTPOINT,
            flags=ESP_FLAGS,
        ),
        PlannedPartition(
            start_mib=root_start,
            size_mib=root_mib,
            filesystem=filesystem,
            mountpoint="/",
        ),
    ]


def free_regions(
    layout: list[PlannedPartition], disk_size_bytes: int
) -> list[tuple[int, int]]:
    """Die Luecken, als (Anfang, Groesse) in MiB, in der Reihenfolge der
    Platte.

    Auch die Luecke vor der ersten und hinter der letzten Partition -
    beides sind Stellen, an denen eine neue Partition Platz hat, und die
    hinterste ist die haeufigste.
    """
    regions: list[tuple[int, int]] = []
    cursor = ALIGNMENT_MIB
    end = last_usable_mib(disk_size_bytes)
    for partition in sorted(layout, key=lambda p: p.start_mib):
        if partition.start_mib > cursor:
            regions.append((cursor, partition.start_mib - cursor))
        cursor = max(cursor, partition.end_mib)
    if end > cursor:
        regions.append((cursor, end - cursor))
    return regions


def allocated_mib(layout: list[PlannedPartition]) -> int:
    return sum(partition.size_mib for partition in layout)


def free_mib(layout: list[PlannedPartition], disk_size_bytes: int) -> int:
    """Wie viel noch zu vergeben ist. Die Summe der Luecken und nicht
    "Platte minus Partitionen": bei einer Einteilung, die ueber das Ende
    hinausragt, waere die zweite Rechnung negativ und wuerde eine
    Ueberbelegung als freien Platz ausgeben."""
    return sum(size for _start, size in free_regions(layout, disk_size_bytes))


def first_fit(
    layout: list[PlannedPartition], disk_size_bytes: int, size_mib: int
) -> int | None:
    """Der Anfang der ersten Luecke, in die size_mib passt, oder None.

    Erste passende und nicht groesste: eine neue Partition soll die
    Luecke schliessen, die schon da ist, statt eine zweite aufzumachen.
    """
    for start, size in free_regions(layout, disk_size_bytes):
        if size >= size_mib:
            return start
    return None


def largest_free_mib(
    layout: list[PlannedPartition], disk_size_bytes: int
) -> int:
    """Die groesste einzelne Luecke - das, was eine Partition hoechstens
    gross werden kann. Nicht dasselbe wie free_mib(): zwei Luecken von je
    10 GiB sind 20 GiB frei und tragen trotzdem keine 11-GiB-Partition."""
    regions = free_regions(layout, disk_size_bytes)
    return max((size for _start, size in regions), default=0)


def parse_size_mib(text: str, *, available_mib: int) -> tuple[int, str]:
    """Eine eingetippte Groesse in MiB, oder eine Begruendung.

    Gibt (mib, "") zurueck oder (0, meldung). Nie eine Ausnahme: der
    Aufrufer ist eine Eingabezeile, die bei jedem Tastendruck neu prueft,
    und eine halb getippte Zahl ist kein Fehler des Programms.

    EINE EINHEIT IST PFLICHT, und das ist der Punkt dieser Funktion.
    "20" ist auf einer Partitionierungsseite nicht eindeutig - 20 MiB und
    20 GiB unterscheiden sich um den Faktor tausend, und die Verwechslung
    faellt erst auf, wenn das installierte System keinen Platz hat.
    Deshalb wird nachgefragt statt geraten.

    Abgerundet auf volle MiB, nie aufgerundet: archinstall verlangt
    Vielfache von 1 MiB (siehe ALIGNMENT_MIB), und Aufrunden koennte die
    letzte Partition ueber gpt_end() schieben.
    """
    cleaned = text.strip()
    if not cleaned:
        return 0, _("Please enter a size, for example 20G.")
    if cleaned.lower() in REST_WORDS:
        if available_mib <= 0:
            return 0, _("There is no free space left on the disk.")
        return available_mib, ""

    found = _SIZE.match(cleaned)
    if not found:
        # Ein einziges Literal, nicht zwei aneinandergesetzte: siehe die
        # gleichlautende Anmerkung in installer/core/validate.py - die
        # Vollstaendigkeitspruefung in tests/installer/test_i18n.py kann
        # Pythons implizitem Zusammensetzen benachbarter Zeichenketten
        # nicht folgen und wuerde nur die erste Haelfte im Katalog suchen.
        return 0, _("A size needs a unit, for example 20G or 512M. The word rest means all remaining space.")
    number, unit = found.groups()
    mib = int(float(number.replace(",", ".")) * _UNIT_MIB[unit.upper()])
    if mib <= 0:
        return 0, _("A partition must be at least 1 MiB.")
    if mib > available_mib:
        return 0, _("{wanted} does not fit; at most {available} are free.").format(
            wanted=human_mib(mib), available=human_mib(available_mib))
    return mib, ""


def layout_errors(
    layout: list[PlannedPartition], disk_size_bytes: int
) -> list[str]:
    """Alles, was diese Einteilung daran hindert, installiert zu werden.

    Eine leere Liste heisst: archinstall wird sie annehmen und ein
    installiertes System wird davon starten. Die Reihenfolge ist die, in
    der man die Fehler beheben wuerde - die Oberflaeche zeigt den ersten
    an, und der soll der sein, der am weitesten vorne im Weg steht.

    Jede Pruefung hier hat ein Gegenstueck in archinstall oder im
    Bootvorgang, und der Unterschied ist der Zeitpunkt: archinstalls
    eigene Pruefungen laufen, nachdem der Assistent zugemacht hat und die
    Installation angefangen hat zu loeschen. Was hier steht, steht auf der
    Seite, auf der es noch jemand aendern kann.
    """
    findings: list[str] = []
    total = disk_mib(disk_size_bytes)
    end = last_usable_mib(disk_size_bytes)

    if not layout:
        # Der Fall, den translate.py schon einmal als toedlich beschrieben
        # hat: wipe=True mit einer leeren Partitionsliste loescht die
        # Platte und legt nichts an.
        return [_("The layout is empty. Nothing would be installed.")]

    ordered = sorted(layout, key=lambda p: p.start_mib)

    for partition in ordered:
        if partition.size_mib < 1:
            findings.append(
                _("A partition must be at least 1 MiB."))
            break

    esps = [p for p in ordered if p.is_esp()]
    roots = [p for p in ordered if p.is_root()]

    # Jede dieser Meldungen ist EIN Literal, auch wo es die Zeile lang
    # macht - siehe die Anmerkung in parse_size_mib() oben.
    if not esps:
        findings.append(_("There is no EFI system partition. ZepOS cannot boot without one."))
    if not roots:
        findings.append(_("There is no root partition. Add one with the mount point /."))
    if len(esps) > 1:
        findings.append(_("There is more than one EFI system partition."))
    if len(roots) > 1:
        findings.append(_("There is more than one root partition."))

    for esp in esps:
        if esp.filesystem != ESP_FILESYSTEM:
            findings.append(_("The EFI system partition must be formatted as {expected}, not {actual}.").format(
                expected=ESP_FILESYSTEM, actual=esp.filesystem))
        if esp.size_mib < MIN_ESP_MIB:
            findings.append(_("The EFI system partition is only {size}; a boot loader needs at least {minimum}.").format(
                size=human_mib(esp.size_mib), minimum=human_mib(MIN_ESP_MIB)))

    for root in roots:
        if root.size_mib < MIN_ROOT_MIB:
            findings.append(_("The root partition is only {size}; at least {minimum} are required.").format(
                size=human_mib(root.size_mib), minimum=human_mib(MIN_ROOT_MIB)))
        if root.is_swap():
            findings.append(_("The root partition cannot be swap space."))

    # Doppelte Einhaengepunkte. Die Wurzel hat ihre eigene Meldung oben,
    # weil sie die ist, die man sucht; jeder andere Punkt zweimal ist
    # ebenso ein System, in dem eine der beiden Partitionen unerreichbar
    # ist.
    seen: set[str] = set()
    for partition in ordered:
        if not partition.mountpoint or partition.is_root():
            continue
        if partition.mountpoint in seen:
            findings.append(_("Two partitions are mounted at {mountpoint}.").format(
                mountpoint=partition.mountpoint))
        seen.add(partition.mountpoint)

    if ordered[0].start_mib < ALIGNMENT_MIB:
        findings.append(_("A partition starts before {minimum}; the GPT header is there.").format(
            minimum=human_mib(ALIGNMENT_MIB)))

    for previous, current in zip(ordered, ordered[1:]):
        if current.start_mib < previous.end_mib:
            findings.append(_("{first} and {second} overlap.").format(
                first=previous.describe(), second=current.describe()))

    beyond = [p for p in ordered if p.end_mib > end]
    if beyond:
        findings.append(_("{partition} runs past the end of the disk; only {available} of {total} can be used.").format(
            partition=beyond[-1].describe(),
            available=human_mib(end - ALIGNMENT_MIB),
            total=human_mib(total)))

    return findings
