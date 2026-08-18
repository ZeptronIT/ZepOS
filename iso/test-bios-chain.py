#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Startet der Startweg, den ZepOS auf einer BIOS-Maschine bauen wuerde?

    ./iso/test-bios-chain.py            bauen und starten
    ./iso/test-bios-chain.py --keep     die vorhandene Platte nur starten
    ./iso/test-bios-chain.py --build    nur bauen, nicht starten

WELCHE FRAGE DAS BEANTWORTET, UND WELCHE NICHT
    installer/core/firmware.py lehnt eine Maschine ab, die im BIOS-Modus
    gestartet ist, und der Kopf jener Datei nennt drei Gruende, von denen
    zwei bis zum 11.08.2026 keine Aussagen ueber ZepOS waren, sondern
    ueber die Abwesenheit einer Messung:

      * "Kein Lauf hat je ein INSTALLIERTES ZepOS im BIOS-Modus
        gestartet."
      * "`grub-install --target=i386-pc` ist in diesem Projekt noch nie
        gelaufen."

    Dieses Werkzeug beantwortet den zweiten vollstaendig und den ersten
    zur Haelfte. Es baut eine Platte mit GENAU der Einteilung, die
    installer.core.layout.suggested_layout() vorschlaegt - dieselbe
    Funktion, aus der translate.py die archinstall-Konfiguration macht -,
    legt sie als MBR an, richtet GRUB fuer i386-pc ein und startet das
    Ergebnis unter SeaBIOS.

    Was es NICHT beantwortet, und das ist der Grund, warum die Ablehnung
    in firmware.py davon nicht faellt: hier laeuft nicht archinstall,
    sondern pacstrap und grub-install von Hand. Zwischen "GRUB startet
    diese Einteilung" und "archinstall baut sie auf einer BIOS-Maschine
    so" liegt archinstalls eigener Weg - PartitionTable.default(),
    _add_grub_bootloader(), get_parent_device_path() -, und der ist an
    dieser Stelle gelesen und nicht gefahren. Der Beleg, den firmware.py
    verlangt, ist ein Lauf VOM MEDIUM; dies ist der Beleg, dass der
    darunter liegende Startweg traegt.

    Ein Werkzeug, das den Unterschied verwischte, waere schlimmer als
    keines: es wuerde eine Ablehnung aufheben, hinter der eine geloeschte
    Festplatte steht.

WARUM EIN CONTAINER
    losetup, parted, mkfs und pacstrap brauchen root. Dieselbe Antwort
    wie in iso/build.sh und in test-boot.py's stage_update_probe(), aus
    demselben Grund - und mit einem Unterschied: sudo ist hier die
    Rueckfallebene und nicht der Normalfall, weil ein Konto in der
    Gruppe docker gar keine Erhoehung braucht und ein fehlgeschlagenes
    sudo auf dieser Maschine das Konto sperrt.

WARUM DAS BASISSYSTEM UND NICHT zepos-desktop
    Weil die Frage der Startweg ist und nicht der Schreibtisch. base,
    linux und grub sind alles, was zwischen dem MBR und einem
    Anmeldezeichen liegt; jedes Paket mehr macht den Lauf laenger und die
    Aussage nicht staerker. Was ZepOS obendrauf installiert, ist auf der
    UEFI-Seite laengst gemessen (test-boot.py --scenario installed) und
    haengt an keinem Bit der Firmware.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ISO_DIR = REPO / "iso"
OUT = ISO_DIR / "out"

sys.path.insert(0, str(REPO))
from installer.core.layout import suggested_layout      # noqa: E402


def _load_test_boot():
    """iso/test-boot.py, ueber den Pfad geladen.

    Wegen des Bindestrichs im Namen kein gewoehnlicher Import - und
    trotzdem der richtige Weg: Qmp, qemu_command und die Bildbewertung
    sind dort, sie sind hier dieselben, und eine zweite Fassung von
    ihnen waere eine zweite Stelle, an der der Maschinenaufbau treiben
    kann.
    """
    spec = importlib.util.spec_from_file_location("zepos_test_boot",
                                                  ISO_DIR / "test-boot.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["zepos_test_boot"] = module
    spec.loader.exec_module(module)
    return module


test_boot = _load_test_boot()

# 6 GiB. Ueber installer.core.model.MIN_DISK_MIB, gross genug fuer die
# 512-MiB-ESP plus base und linux (gemessen 11.08.2026: 1,4 GiB im Ziel)
# und klein genug, dass die Datei auf einem tmpfs gebaut werden kann.
DISK_BYTES = 6 * 1024 * 1024 * 1024

IMAGE = OUT / "bios-chain.img"
RUN = OUT / "run-bios-chain"

# Woran ein Start erkannt wird, und alle vier muessen kommen.
#
# Auf der seriellen Leitung und nicht im Bild, weil ein Bild nur zeigt,
# was gerade dasteht: der Kernel scrollt, das Anmeldezeichen kommt nach
# dem letzten Foto, und ein Lauf, der genau dazwischen fotografiert,
# meldet einen schwarzen Schirm ueber einem funktionierenden System.
#
#   GRUB      dass SeaBIOS den MBR gelesen und core.img aus der Luecke
#             davor geholt hat. Das ist die Stelle, an der ein BIOS-Start
#             scheitert, wenn er scheitert.
#   Wurzel    dass systemd durchgelaufen ist, also die ext4-Wurzel unter
#             der Kennung gefunden wurde, die in der fstab steht.
#   Kernel    welcher Kernel gelaufen ist. agettys Begruessung nennt ihn,
#             und damit steht die Fassung, die GRUB von der
#             FAT32-Partition geladen hat, namentlich im Protokoll.
#   Anmeldung das Anmeldezeichen selbst.
#
# NICHT "Linux version", und das ist gemessen: der Kernel schreibt diese
# Zeile bei 0.000000, also bevor console=ttyS0 eingerichtet ist. Das
# serielle Protokoll dieses Laufs faengt bei 0.048412 an. Eine Marke, die
# systematisch fehlt, macht aus jedem gelungenen Start einen Fehlschlag -
# gemessen am 11.08.2026, an einem System, das bis zum Anmeldezeichen
# durchgelaufen war und als "traegt NICHT" gemeldet wurde.
BOOT_MARKERS = (
    ("GRUB", re.compile(r"GNU GRUB\s+version")),
    ("Wurzel", re.compile(r"Multi-User System")),
    ("Kernel", re.compile(r"Arch Linux (\S+) \(ttyS0\)")),
    ("Anmeldung", re.compile(r"login:")),
)


def docker_command() -> list[str]:
    """`docker`, mit sudo davor nur wenn es ohne nicht geht.

    iso/build.sh schreibt `sudo -n docker` unbedingt hin, und der Kopf
    jener Datei sagt auch warum: sie kannte nur diesen Weg. Ein Konto in
    der Gruppe docker spricht mit dem Daemon ohne jede Erhoehung, und
    diese Maschine sperrt das Konto bei einer fehlgeschlagenen
    sudo-Abfrage - eine Erhoehung, die nicht gebraucht wird, ist also
    nicht nur ueberfluessig, sondern das groesste Risiko im ganzen Lauf.
    """
    socket = Path("/var/run/docker.sock")
    if socket.exists() and os.access(socket, os.R_OK | os.W_OK):
        return ["docker"]
    return ["sudo", "-n", "docker"]


def pinned_snapshot() -> str:
    """Der ALA-Stichtag aus iso/profile/pacman.conf.

    Aus derselben Datei wie iso/build.sh und mit demselben Ausdruck. Das
    Basissystem, das hier gestartet wird, muss dasselbe sein, das eine
    Installation bekaeme - sonst misst dieser Lauf einen GRUB, den ZepOS
    nie ausliefert.
    """
    text = (ISO_DIR / "profile" / "pacman.conf").read_text(encoding="utf-8")
    found = re.search(r"^Server = https://archive\.archlinux\.org/repos/"
                      r"([0-9/]+)/\$repo", text, re.MULTILINE)
    if not found:
        sys.exit("kein ALA-Stichtag in iso/profile/pacman.conf")
    return found.group(1)


# Das Skript im Container. Ein einziges bash -c, weil jeder Schritt auf
# der Schleifeneinrichtung des vorigen steht und ein zweites `docker run`
# sie nicht mehr faende.
#
# Keine einfachen Anfuehrungszeichen darin: das Ganze ist auf der
# Hostseite ein einziges einfach angefuehrtes Argument. Dieselbe Regel
# und derselbe gemessene Grund wie in iso/build.sh.
CONTAINER_SCRIPT = r"""
set -euo pipefail

echo "== Werkzeuge =="
pacman -Sy --noconfirm --needed --quiet \
    arch-install-scripts parted dosfstools e2fsprogs grub gptfdisk >/dev/null

echo "== der Stichtag, aus dem das Ziel kommt =="
printf "Server = https://archive.archlinux.org/repos/%s/\$repo/os/\$arch\n" \
    "$SNAPSHOT" >/etc/pacman.d/mirrorlist
cat /etc/pacman.d/mirrorlist
pacman-key --init >/dev/null 2>&1
pacman-key --populate archlinux >/dev/null 2>&1

echo "== Schleifeneinrichtung =="
# Ein privilegierter Container bekommt ein frisches /dev ohne
# loop-Knoten, also scheitert `losetup --find` mit "device node is
# lost". Die Knoten werden deshalb hier angelegt und der Reihe nach
# PROBIERT - beides steht schon in test-boot.py's stage_update_probe()
# und aus denselben zwei Gruenden: das /dev des Wirts hereinzuhaengen
# gaebe dem Container jede Platte dieser Maschine, und eine feste Nummer
# war dort genau einen Lauf lang richtig.
mknod /dev/loop-control c 10 237 2>/dev/null || true
loop=""
for index in $(seq 0 15); do
    mknod "/dev/loop$index" b 7 "$index" 2>/dev/null || true
    if losetup -P "/dev/loop$index" /out/$IMAGE_NAME 2>/dev/null; then
        loop="/dev/loop$index"
        break
    fi
done
[ -n "$loop" ] || { echo "keine freie Schleifeneinrichtung" >&2; exit 1; }
echo "loop $loop"
trap "umount -R /mnt 2>/dev/null || true; losetup -d $loop || true" EXIT

echo "== MBR und die Einteilung, die ZepOS vorschlaegt =="
# msdos und nicht gpt, weil archinstalls PartitionTable.default() auf
# einer Maschine ohne /sys/firmware/efi MBR zurueckgibt (4.4,
# lib/models/device.py). Diese Platte soll die sein, die dort entstuende.
parted -s "$loop" mklabel msdos
eval "$PARTED_COMMANDS"
parted -s "$loop" print
partprobe "$loop" || true
sleep 1

echo "== die Partitionsknoten, aus sysfs =="
# max_part des loop-Moduls ist auf dieser Maschine 0 (gemessen
# 11.08.2026, /sys/module/loop/parameters/max_part), also vergibt der
# Kernel den Partitionen dynamische Geraetenummern - 259:4 und 259:5
# statt 7:1 und 7:2. Ein `mknod ... b 7 1` waere hier ein Knoten, der auf
# eine andere Schleifeneinrichtung zeigt, und mkfs schriebe in sie
# hinein. Die Nummern werden deshalb gelesen.
base="$(basename $loop)"
for part in 1 2; do
    node="/sys/block/$base/${base}p${part}/dev"
    [ -f "$node" ] || { echo "keine Partition $part in sysfs" >&2; exit 1; }
    mknod "${loop}p${part}" b "$(cut -d: -f1 $node)" "$(cut -d: -f2 $node)" \
        2>/dev/null || true
    echo "${loop}p${part} -> $(cat $node)"
done

echo "== Dateisysteme =="
mkfs.fat -F32 "${loop}p1"
mkfs.ext4 -F -q "${loop}p2"

echo "== einhaengen =="
mount "${loop}p2" /mnt
mkdir -p /mnt/boot
mount "${loop}p1" /mnt/boot

echo "== pacstrap =="
pacstrap -K /mnt base linux grub

echo "== fstab =="
# VON HAND und nicht mit genfstab, und das ist eine Eigenschaft dieses
# Messaufbaus und keine von ZepOS.
#
# genfstab schreibt die Kennungen aus /dev/disk/by-uuid, und die legt
# udev an. Ein Container hat kein udev. Gemessen 11.08.2026: genfstab -U
# schrieb "/dev/loop0p2 / ext4" in die fstab - einen Pfad, den es im Gast
# nicht gibt, weshalb systemd beim Wiedereinhaengen der Wurzel in den
# Notbetrieb faellt. Ein Start, der daran scheitert, haette ueber den
# BIOS-Startweg nichts gesagt.
#
# Auf dem Installationsmedium tritt das nicht auf: dort laeuft udev, und
# archinstall ruft genfstab in genau dieser Umgebung.
#
# Ausserdem sieht der Container /proc/swaps des WIRTS, und genfstab
# uebernahm dessen Auslagerungspartition in die fstab des Gastes. Auch
# das ist ein Ausschnitt dieses Aufbaus und nichts, was eine Installation
# je schriebe.
root_uuid="$(blkid -s UUID -o value ${loop}p2)"
boot_uuid="$(blkid -s UUID -o value ${loop}p1)"
[ -n "$root_uuid" ] && [ -n "$boot_uuid" ] || { echo "keine UUIDs" >&2; exit 1; }
cat >/mnt/etc/fstab <<FSTABEOF
UUID=$root_uuid  /      ext4  rw,relatime  0 1
UUID=$boot_uuid  /boot  vfat  rw,relatime,fmask=0022,dmask=0022,utf8  0 2
FSTABEOF
cat /mnt/etc/fstab

echo "== die serielle Leitung auf die Kernel-Zeile =="
# Damit der Start ueberhaupt etwas erzaehlt. Archs Vorgabe ist
# "loglevel=3 quiet", und das ist das Gegenteil dessen, was ein Messlauf
# von einem Start wissen will. Dieselbe Datei und derselbe Grund wie in
# zepos-install-unattended, Phase 5.
#
# GRUB_TERMINAL_OUTPUT steht daneben, und aus demselben Grund: ohne das
# schreibt GRUB nur auf den Bildschirm, und ob GRUB ueberhaupt lief,
# waere dann eine Vermutung aus dem, was danach kam. Mit "console
# serial" steht seine Kopfzeile im Protokoll - die eine Marke, die
# beweist, dass SeaBIOS den MBR gelesen und core.img ausgefuehrt hat.
# Beides ist Messwerkzeug und keine Einstellung von ZepOS.
mkdir -p /mnt/etc/default/grub.d
cat >/mnt/etc/default/grub.d/99-zepos-bios-chain.cfg <<GRUBEOF
GRUB_CMDLINE_LINUX_DEFAULT="console=tty0 console=ttyS0,115200"
GRUB_TERMINAL_OUTPUT="console serial"
GRUB_SERIAL_COMMAND="serial --unit=0 --speed=115200"
GRUBEOF

echo "== grub-install --target=i386-pc =="
# Auf das ELTERNGERAET und nicht auf die Partition: der MBR und die
# Luecke dahinter gehoeren der Platte. archinstall macht an dieser
# Stelle get_parent_device_path() und uebergibt genau das (4.4,
# lib/installer.py, _add_grub_bootloader).
arch-chroot /mnt grub-install --target=i386-pc --recheck "$loop"

echo "== grub-mkconfig =="
arch-chroot /mnt grub-mkconfig -o /boot/grub/grub.cfg
grep -m1 -o "console=ttyS0[^ \"]*" /mnt/boot/grub/grub.cfg || \
    echo "WARNUNG: keine serielle Konsole auf der Kernel-Zeile"
# Womit GRUB die Wurzel adressiert. Ein root=/dev/loop0p2 waere im Gast
# ein Geraet, das es nicht gibt - dieselbe Falle wie bei der fstab, nur
# eine Stufe frueher und ohne Notbetrieb dahinter. grub-probe fragt
# blkid und nicht udev, also sollte hier eine Kennung stehen; geprueft
# wird es trotzdem.
grep -m1 -o "root=[^ ]*" /mnt/boot/grub/grub.cfg

echo "== ein Konto, damit die Anmeldung etwas anzuzeigen hat =="
# Kein Passwort gesetzt - dieser Lauf tippt nichts ein. Was gemessen
# wird, ist das Anmeldezeichen auf der seriellen Leitung, und das kommt
# von agetty, nicht von einem Konto.
arch-chroot /mnt systemctl enable serial-getty@ttyS0.service

echo "== was im MBR steht =="
# Die eine Stelle, an der ein BIOS-Start scheitert, ohne dass irgendwer
# etwas sagt. 0x55AA am Ende des ersten Sektors ist die Startkennung;
# ohne sie sucht SeaBIOS weiter und landet beim Netzwerkstart.
dd if="$loop" bs=512 count=1 2>/dev/null | od -An -tx1 -j510 -N2
echo "== Sektoren 1..2047, in denen core.img liegt =="
# Wie viele der 1023 KiB vor der ersten Partition nicht null sind.
# core.img ist bei einem gewoehnlichen grub-install etwa 25 bis 30 KiB
# gross; eine Null hier waere ein grub-install, das "no error reported"
# gesagt und nichts geschrieben hat - und das faende erst SeaBIOS heraus.
belegt="$(dd if=$loop bs=512 skip=1 count=2047 2>/dev/null | tr -d "\000" | wc -c)"
echo "core.img: $belegt Byte ungleich null in der Luecke"
[ "$belegt" -gt 4096 ] || { echo "die Luecke ist leer" >&2; exit 1; }

sync
# Erst die Schluesselverwaltung von pacstrap beenden, dann aushaengen.
# Gemessen 11.08.2026: "umount: /mnt: target is busy" und rc=32 am Ende
# eines sonst vollstaendigen Baus - pacstrap -K laesst gpg-agent und
# dirmngr mit offenen Dateien unter /mnt zurueck.
gpgconf --homedir /mnt/etc/pacman.d/gnupg --kill all 2>/dev/null || true
sleep 1
umount -R /mnt || { sleep 3; umount -R -l /mnt; }
losetup -d "$loop"
trap - EXIT
echo "== fertig =="
"""


def parted_commands(disk_bytes: int) -> str:
    """Die Einteilung als parted-Befehle, aus ZepOS' eigenem Vorschlag.

    suggested_layout() und keine Zahlen von Hand. Das ist der ganze Grund,
    warum dieser Lauf ueber ZepOS etwas aussagt: waeren die Groessen hier
    abgeschrieben, dann liefe die Messung gegen eine Platte, die ZepOS so
    nie baut, und eine spaetere Aenderung an ESP_SIZE_MIB wuerde sie
    stillschweigend ungueltig machen.
    """
    plan = suggested_layout(disk_bytes)
    if not plan:
        sys.exit(f"suggested_layout() traegt {disk_bytes} Byte nicht")
    lines = []
    for index, planned in enumerate(plan, start=1):
        end = planned.start_mib + planned.size_mib
        filesystem = "fat32" if planned.filesystem == "fat32" else "ext2"
        lines.append(
            f'parted -s "$loop" mkpart primary {filesystem} '
            f'{planned.start_mib}MiB {end}MiB')
        for flag in planned.flags:
            lines.append(f'parted -s "$loop" set {index} {flag} on')
    return "\n".join(lines)


def build(image: Path) -> None:
    image.parent.mkdir(parents=True, exist_ok=True)
    image.unlink(missing_ok=True)
    with open(image, "wb") as handle:
        handle.truncate(DISK_BYTES)

    snapshot = pinned_snapshot()
    print(f"Stichtag    {snapshot}")
    print(f"Platte      {image} ({DISK_BYTES // 1024**3} GiB, duenn belegt)")
    print("Einteilung  " + " | ".join(
        f"{p.start_mib}+{p.size_mib} MiB {p.filesystem} "
        f"{p.mountpoint or '-'} [{','.join(p.flags) or '-'}]"
        for p in suggested_layout(DISK_BYTES)))

    command = docker_command() + [
        "run", "--rm", "--network", "host", "--privileged",
        "-v", f"{image.parent}:/out",
        "-e", f"SNAPSHOT={snapshot}",
        "-e", f"IMAGE_NAME={image.name}",
        "-e", f"PARTED_COMMANDS={parted_commands(DISK_BYTES)}",
        "archlinux:latest",
        "bash", "-c", CONTAINER_SCRIPT,
    ]
    print("\n== bauen ==")
    print("  " + " ".join(command[:8]) + " ...")
    result = subprocess.run(command)
    if result.returncode != 0:
        sys.exit(f"der Bau der Platte scheiterte rc={result.returncode}")

    # Alles, was der Container geschrieben hat, gehoert root. Zurueckgeben,
    # sonst kann der naechste Lauf die Datei nicht einmal loeschen.
    subprocess.run(docker_command() + [
        "run", "--rm", "--network", "host",
        "-v", f"{image.parent}:/out", "archlinux:latest",
        "chown", f"{os.getuid()}:{os.getgid()}", f"/out/{image.name}"],
        check=True)


def boot(image: Path, arguments) -> int:
    if RUN.exists():
        shutil.rmtree(RUN)
    RUN.mkdir(parents=True)

    kvm = not arguments.no_kvm and os.access("/dev/kvm", os.W_OK)
    command = test_boot.qemu_command(
        RUN, iso=None, target=image, update=None,
        # Kein pflash: eine QEMU-Maschine ohne Firmware-Flash startet
        # unter SeaBIOS, und das IST der BIOS-Modus. Genau der Zustand,
        # in dem der Kernel /sys/firmware/efi nicht anlegt und
        # installer/core/firmware.is_uefi() falsch antwortet.
        firmware="bios", efivars=None, vga=arguments.vga,
        memory=arguments.memory, kvm=kvm, evidence=None)
    print("\n== starten ==")
    print("  " + " ".join(command))
    qemu = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)

    serial = RUN / "serial.log"
    shots: list[Path] = []
    qmp: test_boot.Qmp | None = None
    died = ""
    try:
        qmp = test_boot.Qmp(RUN / "qmp.sock")
        started = time.monotonic()
        for mark in arguments.settle:
            while time.monotonic() - started < mark:
                if qemu.poll() is not None:
                    died = (f"qemu beendete sich rc={qemu.returncode} nach "
                            f"{time.monotonic() - started:.0f}s")
                    break
                time.sleep(1.0)
            if died:
                break
            shot = qmp.screenshot(RUN / f"screen-{mark:04d}s")
            if shot:
                shots.append(shot)
                print(f"  Bild bei {mark}s -> {shot.name}")
    finally:
        if qmp is not None:
            try:
                qmp.execute("quit")
            except Exception:
                pass
        try:
            qemu.wait(timeout=20)
        except subprocess.TimeoutExpired:
            qemu.kill()

    text = serial.read_text(errors="replace") if serial.is_file() else ""
    print("\n== die serielle Leitung ==")
    print(f"  {len(text)} Zeichen in {serial}")
    reached = []
    for name, pattern in BOOT_MARKERS:
        found = pattern.search(text)
        reached.append(bool(found))
        print(f"  {name:<10} {'JA' if found else 'nein'}"
              + (f"   {found.group(0)!r}" if found else ""))
    for shot in shots:
        print(f"  Bild       {shot}")
    if died:
        print(f"  {died}")

    print()
    if all(reached):
        print("Der BIOS-Startweg traegt: MBR gelesen, core.img aus der Luecke,\n"
              "Kernel von der FAT32-Partition, Wurzel gefunden, Anmeldung da.")
        return 0
    print("Der BIOS-Startweg traegt NICHT. Die erste Marke, die fehlt, sagt\n"
          "wo es aufhoert; das vollstaendige Protokoll steht in\n"
          f"{serial}.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true",
                        help="die vorhandene Platte nicht neu bauen")
    parser.add_argument("--build", action="store_true",
                        help="nur bauen, nicht starten")
    parser.add_argument("--image", type=Path, default=IMAGE)
    parser.add_argument("--vga", default="virtio")
    parser.add_argument("--memory", default="2G")
    parser.add_argument("--no-kvm", action="store_true")
    parser.add_argument("--settle", type=int, nargs="+",
                        # SeaBIOS ist in zwei Sekunden am GRUB-Menue, das
                        # fuenf Sekunden zaehlt; danach ist der Kernel
                        # dran. Die letzten Marken sind fuer den Fall,
                        # dass irgendetwas laenger braucht als hier.
                        default=[3, 5, 7, 12, 25, 45, 70])
    arguments = parser.parse_args()

    if not arguments.keep:
        build(arguments.image)
    elif not arguments.image.is_file():
        sys.exit(f"keine Platte bei {arguments.image} - ohne --keep bauen")

    if arguments.build:
        return 0
    if not shutil.which("qemu-system-x86_64"):
        sys.exit("qemu-system-x86_64 ist nicht installiert")
    return boot(arguments.image, arguments)


if __name__ == "__main__":
    sys.exit(main())
