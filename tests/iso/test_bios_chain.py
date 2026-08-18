# SPDX-License-Identifier: GPL-3.0-or-later
"""Der BIOS-Startweg: was der Messaufbau baut, und woran er ihn erkennt.

WARUM DIESE DATEI EXISTIERT
    `./iso/test-bios-chain.py` braucht Docker, root im Container und
    sechs Minuten. In einer Testsuite, die keinen Prozess starten darf,
    ist davon nichts zu haben - und trotzdem sind es genau zwei Dinge,
    an denen dieser Lauf still falsch werden kann, und beide sind hier
    pruefbar:

      * die EINTEILUNG. Sie kommt aus
        installer.core.layout.suggested_layout(), damit die Messung ueber
        ZepOS etwas aussagt und nicht ueber abgeschriebene Zahlen. Loest
        sich diese Verbindung, dann misst der Lauf weiter - nur eben eine
        Platte, die ZepOS so nie baut.
      * die MARKEN. Gemessen am 11.08.2026: ein System, das bis zum
        Anmeldezeichen durchgelaufen war, wurde als "traegt NICHT"
        gemeldet, weil eine der Marken auf einer Zeile stand, die der
        Kernel schreibt, BEVOR console=ttyS0 eingerichtet ist. Eine
        Marke, die systematisch fehlt, macht aus jedem Erfolg einen
        Fehlschlag - und aus jedem Fehlschlag eine Zeile, die niemand
        mehr liest.

    Die Marken werden deshalb gegen einen Ausschnitt des ECHTEN
    Protokolls geprueft, das der Lauf vom 11.08.2026 gebracht hat, und
    nicht gegen einen erfundenen Text.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from installer.core.layout import ESP_MOUNTPOINT, ESP_SIZE_MIB, suggested_layout

ISO = Path(__file__).resolve().parents[2] / "iso"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ISO / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bios = _load("zepos_bios_chain", "test-bios-chain.py")


def script_lines() -> list[str]:
    """Die Befehle des Containerskripts, ohne seine Kommentare.

    Ohne diese Trennung waere jede Pruefung hier die Falle, vor der die
    Suite an mehreren Stellen warnt: `"i386-pc" in text` ist auch dann
    wahr, wenn i386-pc nur in einem Absatz darueber erklaert wird - und
    dieses Skript erklaert viel.
    """
    return [line.strip() for line in bios.CONTAINER_SCRIPT.splitlines()
            if line.strip() and not line.strip().startswith("#")]


# --------------------------------------------------------------------
# Die Einteilung
# --------------------------------------------------------------------
def test_the_layout_comes_from_zepos_own_suggestion():
    """Jede Zahl in den parted-Befehlen steht so in suggested_layout().

    Nachgerechnet und nicht abgeglichen: die erwarteten Zeilen werden aus
    dem Vorschlag ERZEUGT, also faellt eine Aenderung an ESP_SIZE_MIB hier
    nicht durch - sie aendert beide Seiten. Was hier durchfaellt, ist
    genau der Fall, um den es geht: parted_commands() rechnet selbst
    statt zu fragen.
    """
    plan = suggested_layout(bios.DISK_BYTES)
    commands = bios.parted_commands(bios.DISK_BYTES).splitlines()

    starts = [f"{planned.start_mib}MiB" for planned in plan]
    ends = [f"{planned.start_mib + planned.size_mib}MiB" for planned in plan]
    for start, end in zip(starts, ends):
        assert any(start in line and end in line for line in commands), \
            f"{start}..{end} steht in keinem parted-Befehl"

    # Und die ESP traegt beide Flaggen, in der Reihenfolge, in der ZepOS
    # sie nennt. "esp" nach "boot" ist der Typ 0xEF ueber der aktiven
    # Markierung; andersherum bliebe die Markierung stehen und der Typ
    # nicht.
    assert 'parted -s "$loop" set 1 boot on' in commands
    assert 'parted -s "$loop" set 1 esp on' in commands
    assert commands.index('parted -s "$loop" set 1 boot on') < \
        commands.index('parted -s "$loop" set 1 esp on')


def test_the_esp_is_the_first_partition_and_leaves_room_for_core_img():
    """Ein MiB vor der ersten Partition, und da liegt core.img.

    Auf MBR braucht GRUB keine BIOS-Boot-Partition, sondern den
    Zwischenraum zwischen dem MBR und der ersten Partition. Faengt die
    erste Partition bei Sektor 1 an, hat core.img keinen Platz und
    grub-install scheitert - oder schlimmer: es schreibt in Blocklisten
    und der Start bricht beim naechsten Dateisystemlauf ab.
    """
    plan = suggested_layout(bios.DISK_BYTES)
    assert plan[0].start_mib >= 1
    assert plan[0].start_mib * 1024 * 1024 > 32 * 1024      # core.img passt
    assert plan[0].mountpoint == ESP_MOUNTPOINT
    assert plan[0].size_mib == ESP_SIZE_MIB


def test_the_table_is_mbr_because_that_is_what_archinstall_would_make():
    """msdos und nicht gpt.

    PartitionTable.default() gibt MBR zurueck, wenn SysInfo.has_uefi()
    falsch ist (archinstall 4.4, lib/models/device.py). Eine
    GPT-Messplatte wuerde eine Einteilung starten, die auf einer
    BIOS-Maschine nie entstuende - und dabei die eine Frage umgehen, an
    der GPT und BIOS haengen: wo core.img hin soll.
    """
    assert 'parted -s "$loop" mklabel msdos' in script_lines()
    assert not [line for line in script_lines() if "mklabel gpt" in line]


def test_grub_is_installed_for_i386_pc_onto_the_whole_disk():
    """--target=i386-pc auf $loop und nicht auf ${loop}p1.

    Der MBR und die Luecke gehoeren der Platte. archinstall uebergibt an
    dieser Stelle get_parent_device_path() der Startpartition, also
    ebenfalls die Platte; ein grub-install auf die Partition schriebe in
    deren Bootsektor, den kein BIOS liest.
    """
    installs = [line for line in script_lines()
                if "grub-install" in line and not line.startswith("echo ")]
    assert len(installs) == 1
    assert "--target=i386-pc" in installs[0]
    assert '"$loop"' in installs[0]
    assert "${loop}p" not in installs[0]


def test_the_gap_before_the_first_partition_is_checked_for_content():
    """Ein grub-install, das nichts geschrieben hat, meldet keinen Fehler.

    "Installation finished. No error reported." kommt auch dann, wenn
    core.img in einer Luecke landet, die es nicht gibt. Was das
    unterscheidet, ist ein Blick in die Sektoren danach - und ein
    Vergleich, der bei leer abbricht.
    """
    lines = script_lines()
    assert any("skip=1" in line and "count=2047" in line for line in lines)
    assert any(line.startswith('[ "$belegt" -gt') for line in lines)


def test_the_fstab_is_written_from_uuids():
    """Und nicht mit genfstab.

    Der Grund ist der Messaufbau und nicht ZepOS: ein Container hat kein
    udev, also kein /dev/disk/by-uuid, also schreibt genfstab -U den
    Geraetepfad. /dev/loop0p2 gibt es im Gast nicht, und der Start endet
    im Notbetrieb - ein Fehlschlag, der ueber den BIOS-Startweg nichts
    aussagt.
    """
    lines = script_lines()
    assert any("blkid -s UUID -o value" in line for line in lines)
    assert not [line for line in lines if line.startswith("genfstab")]


# --------------------------------------------------------------------
# Die Marken
# --------------------------------------------------------------------
# Ein Ausschnitt des Protokolls, das der Lauf vom 11.08.2026 gebracht
# hat - Anfang und Ende, mit den Steuerzeichen, die wirklich darin
# stehen. Gegen einen erfundenen Text zu pruefen hiesse, die Marken
# gegen die Erwartung zu pruefen, aus der sie geschrieben wurden.
MEASURED_SERIAL = (
    "                             GNU GRUB  version 2:2.14-1\r\n"
    "\r\n"
    "   *Arch Linux                                                             \r\n"
    "    Advanced options for Arch Linux                                        \r\n"
    "[    0.048412] virt/tdx: TDX not supported by the host platform\r\n"
    "\x1b[0;1;39mBooting initrd of \x1b[0m\x1b[38;2;23;147;209mArch Linux\x1b[0m\r\n"
    "[\x1b[0;32m  OK  \x1b[0m] Reached target \x1b[0;1;39mBasic System\x1b[0m.\r\n"
    "[\x1b[0;32m  OK  \x1b[0m] Started \x1b[0;1;39mSerial Getty on ttyS0\x1b[0m.\r\n"
    "[\x1b[0;32m  OK  \x1b[0m] Reached target \x1b[0;1;39mMulti-User System\x1b[0m.\r\n"
    "\r\n"
    "Arch Linux 7.1.5-arch1-2 (ttyS0)\r\n"
    "\r\n"
    "archlinux login: "
)


def test_every_marker_fires_on_the_serial_log_that_was_measured():
    for name, pattern in bios.BOOT_MARKERS:
        assert pattern.search(MEASURED_SERIAL), f"{name} findet nichts"


def test_no_marker_fires_on_a_boot_that_never_started():
    """SeaBIOS ohne startfaehigen MBR: der Netzwerkstart und sonst nichts.

    Der Fall, den dieser Lauf finden soll. Faengt hier eine Marke, dann
    faengt sie auch bei jedem echten Fehlschlag.
    """
    nothing = ("SeaBIOS (version 1.17.0-1)\r\n"
               "Booting from Hard Disk...\r\n"
               "Boot failed: could not read the boot disk\r\n"
               "Booting from DVD/CD...\r\n"
               "Boot failed: Could not read from CDROM (code 0003)\r\n"
               "No bootable device.\r\n")
    for name, pattern in bios.BOOT_MARKERS:
        assert not pattern.search(nothing), f"{name} faengt einen toten Start"


def test_a_boot_that_stops_after_grub_is_not_a_pass():
    """Die Marken sind eine Kette und keine Auswahl.

    Ein GRUB, das den Kernel nicht findet, ist der zweithaeufigste
    BIOS-Fehlschlag - und der einzige, bei dem das erste Foto genauso
    aussieht wie bei einem gelungenen Start.
    """
    stalled = MEASURED_SERIAL.split("[    0.048412]")[0]
    fired = [name for name, pattern in bios.BOOT_MARKERS
             if pattern.search(stalled)]
    assert fired == ["GRUB"]


def test_the_kernel_marker_names_the_kernel_that_ran():
    """Nicht nur, DASS einer lief.

    "Linux version" steht bei 0.000000 auf der Leitung, also bevor
    console=ttyS0 eingerichtet ist, und fehlt in jedem Protokoll dieses
    Aufbaus. agettys Begruessung nennt dieselbe Fassung und kommt spaet
    genug.
    """
    marker = dict(bios.BOOT_MARKERS)["Kernel"]
    found = marker.search(MEASURED_SERIAL)
    assert found and found.group(1) == "7.1.5-arch1-2"
    assert not marker.search("[    0.000000] Linux version 7.1.5-arch1-2")


def test_grub_is_told_to_write_to_the_serial_line():
    """Sonst waere "GRUB lief" eine Vermutung aus dem, was danach kam.

    Messwerkzeug und keine Einstellung von ZepOS - dieselbe Rolle wie
    console=ttyS0 auf der Kernel-Zeile, und beides steht in derselben
    Datei.
    """
    lines = script_lines()
    assert any(line.startswith('GRUB_TERMINAL_OUTPUT="console serial"')
               for line in lines)
    assert any(line.startswith('GRUB_CMDLINE_LINUX_DEFAULT=') and "ttyS0" in line
               for line in lines)


# --------------------------------------------------------------------
# Die Maschine
# --------------------------------------------------------------------
def test_the_disk_is_booted_on_a_machine_with_no_uefi_firmware():
    """Kein pflash: das IST der BIOS-Modus.

    Eine QEMU-Maschine ohne Firmware-Flash startet unter SeaBIOS, und
    genau dann legt der Kernel /sys/firmware/efi nicht an - der Zustand,
    in dem installer.core.firmware.is_uefi() falsch antwortet und ZepOS
    heute ablehnt.
    """
    command = bios.test_boot.qemu_command(
        Path("/run"), iso=None, target=Path("/disk.img"), update=None,
        firmware="bios", efivars=None, vga="virtio", memory="2G", kvm=False)
    assert not [item for item in command if "pflash" in item]
    assert not [item for item in command if "OVMF" in item]
    # Und von der Platte, nicht von einem Medium.
    assert command[command.index("-boot") + 1] == "c"
    assert not [item for item in command if item == "-cdrom"]


def test_sudo_is_the_fallback_and_not_the_default():
    """Ein Konto in der Gruppe docker braucht keine Erhoehung.

    Diese Maschine sperrt das Konto bei einer fehlgeschlagenen
    sudo-Abfrage. Eine Erhoehung, die nicht gebraucht wird, ist damit
    nicht ueberfluessig, sondern das groesste Risiko im ganzen Lauf.
    """
    source = (ISO / "test-bios-chain.py").read_text(encoding="utf-8")
    body = source.split("def docker_command()")[1].split("\ndef ")[0]
    statements = [line.strip() for line in body.splitlines()
                  if line.strip().startswith("return")]
    assert statements[0] == 'return ["docker"]'
    assert statements[-1] == 'return ["sudo", "-n", "docker"]'
