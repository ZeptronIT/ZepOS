# SPDX-License-Identifier: GPL-3.0-or-later
"""Which firmware the live session booted with.

WARUM ZepOS EINE BIOS-MASCHINE ABLEHNT, AUCH MIT GRUB
    Hier stand: "translate.py wires systemd-boot to an EFI system
    partition unconditionally, and systemd-boot cannot boot a machine
    whose firmware has no EFI at all." Der erste Halbsatz stimmt nicht
    mehr - translate.py schreibt "bootloader": "Grub" -, und der zweite
    gilt fuer GRUB nicht: Bootloader.Grub.is_uefi_only() ist False, und
    _add_grub_bootloader() hat einen i386-pc-Zweig (beides an
    archinstall 4.4 nachgelesen).

    Die Ablehnung bleibt. Der Grund ist jetzt ein anderer und wieder ein
    kleinerer: der STARTWEG ist seit dem 11.08.2026 gemessen, der WEG
    DORTHIN nicht - und am Ende eines ungemessenen Weges steht eine
    geloeschte Festplatte.

    GEMESSEN AM 11.08.2026, mit iso/test-bios-chain.py
        Eine Platte mit genau der Einteilung, die
        installer.core.layout.suggested_layout() vorschlaegt - MBR, 1 MiB
        Vorlauf, 512 MiB FAT32 mit boot+esp auf /boot, ext4 auf dem Rest
        -, darauf pacstrap base/linux/grub vom angehefteten
        ALA-Schnappschuss und `grub-install --target=i386-pc --recheck`
        auf das Elterngeraet. Das Ergebnis unter SeaBIOS gestartet:

            GNU GRUB  version 2:2.14-1     GRUB kam aus der Luecke
            Multi-User System              die ext4-Wurzel wurde gefunden
            Arch Linux 7.1.5-arch1-2 (ttyS0)
            archlinux login:

        core.img belegte 61577 Byte der 1023 KiB vor der ersten
        Partition, und im MBR stand 55 aa. Die beiden Saetze, die hier
        frueher standen - "kein Lauf hat je" und "grub-install
        --target=i386-pc ist noch nie gelaufen" - sind damit erledigt.

        Ebenfalls nachgesehen und damit erledigt: der GPT-Einwand. Die
        Tabellenart faellt in archinstall an genau einer Stelle,
        DeviceHandler.__init__ setzt sie auf PartitionTable.default(),
        und die gibt MBR zurueck, wenn SysInfo.has_uefi() falsch ist
        (4.4, lib/disk/device_handler.py Zeile 47). Auf einer
        BIOS-Maschine entsteht also keine GPT-Platte, und die Frage, ob
        sich eine BIOS-Boot-Partition in einer archinstall-Konfiguration
        ausdruecken laesst - sie laesst sich nicht, PartitionFlag kennt
        nur BOOT, XBOOTLDR, ESP, LINUX_HOME und SWAP -, stellt sich dort
        nicht.

    WAS DIE ABLEHNUNG TRAEGT, UND ES REICHT
        Zwischen "GRUB startet diese Einteilung" und "eine Installation
        baut sie" liegt archinstalls eigener Weg, und der ist gelesen und
        nicht gefahren: _add_grub_bootloader() nimmt im BIOS-Zweig
        get_parent_device_path() der Startpartition und ruft grub-install
        im chroot; _get_boot_partition() findet unsere ESP ueber die
        BOOT-Flagge. Beides sieht richtig aus. Beides ist eine Lesung.

        Und der Lauf, um den es geht, ist nicht der von
        iso/test-bios-chain.py: dort partitioniert ein Skript, nicht der
        Installer, und der Unterschied zwischen den beiden ist genau die
        Stelle, an der eine Platte geloescht wird.

    Wer die Ablehnung aufheben will, braucht weiterhin genau einen Beleg:
    einen Lauf, der VON DIESEM MEDIUM im BIOS-Modus installiert und die
    entstandene Platte danach ohne Medium startet. Was ein Nutzer im
    BIOS-Modus heute sieht, ist dagegen fotografiert: das Medium startet,
    das syslinux-Menue traegt die Marke, der Installer kommt hoch und
    sagt auf Schritt 1 den Satz weiter unten - er sieht also einen Grund
    und keinen schwarzen Schirm.

Der Kernel legt /sys/firmware/efi nur an, wenn er ueber EFI gestartet
ist - dieselbe Pruefung, die archinstall, systemd und der Arch
Installation Guide benutzen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .i18n import _

EFI_SYSFS_PATH = Path("/sys/firmware/efi")


def is_uefi(*, efi_path: Path | None = None) -> bool:
    """Whether this machine started in UEFI mode.

    efi_path is resolved here rather than bound as a default argument, so
    a caller (or a test) can point it somewhere else at call time - the
    same rule every injected dependency in this package follows.
    """
    return (efi_path or EFI_SYSFS_PATH).is_dir()


# Alias for the function above. firmware_problem()'s own `is_uefi`
# parameter shadows that name inside its body, and the parameter has to
# keep the name every caller already passes.
_sysfs_is_uefi = is_uefi


def firmware_problem(*, is_uefi: Callable[[], bool] | None = None) -> str:
    """The refusal to show on a machine ZepOS cannot install onto, or "".

    Lives here rather than at the point of the erase so that a surface can
    ask BEFORE its first question: whether the machine started in UEFI
    mode is a fact about the hardware, and no answer the user could give
    would change it. Learning it after seven questions and a confirmed
    disk erase - which is where installer.core.runner.install() alone
    could report it - is the worst possible moment, and lands on exactly
    the old, BIOS-era hardware the text interface exists for.

    One function, one msgid: runner.install() refuses with this same text
    immediately before handing anything to archinstall, so the two can
    never drift into two descriptions of one rule. Returning a string
    rather than raising is what lets a form show it next to its fields
    while the runner turns it into a refusal.
    """
    check = is_uefi or _sysfs_is_uefi
    if check():
        return ""
    # Der zweite Satz sagt jetzt, was gemessen ist, statt was fruher
    # behauptet wurde. "would leave it unable to boot" war unter
    # systemd-boot eine Tatsache; unter GRUB ist es eine Vermutung, und
    # eine Vermutung als Tatsache auszugeben ist genau das, was dieses
    # Projekt seinen Nutzern nicht antut. Der Grund, nicht zu
    # installieren, wird davon nicht schwaecher: eine Loeschung, deren
    # Ergebnis niemand je gestartet hat, ist keine, die man riskiert.
    return _(
        "ZepOS can only be installed on a computer started in UEFI mode. This computer started in BIOS mode. ZepOS has never been tested that way, and an installation would erase the disk before anybody could find out whether the result starts."
    )
