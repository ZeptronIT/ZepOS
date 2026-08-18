#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boot a ZepOS image in QEMU and bring back evidence of what it did.

    ./iso/test-boot.py                    boot the newest ISO in iso/out/
    ./iso/test-boot.py --iso path.iso     boot a particular one
    ./iso/test-boot.py --keep-running     leave the machine up afterwards

    ./iso/test-boot.py --scenario install    install onto a file-backed disk
    ./iso/test-boot.py --scenario installed  boot that disk, no ISO
    ./iso/test-boot.py --scenario update     and let it update itself

    ./iso/test-boot.py --scenario release    boot the SHIPPING medium and
                                             drive it like a person would
    ./iso/test-boot.py --scenario release-install    ... past the erase
    ./iso/test-boot.py --scenario release-installed  ... and boot the result

    ./iso/test-boot.py --scenario boot-menu               the first ten
    ./iso/test-boot.py --scenario boot-menu --firmware bios   seconds of it,
                                             on each firmware in turn

    ./iso/test-boot.py --scenario secure-boot    boot it TWICE on a
                                             firmware that enforces Secure
                                             Boot - once with a platform
                                             key in the variable store and
                                             once without - and compare

    ./iso/test-boot.py --attach --steps key:tab shot:where-is-the-focus
                                             drive a machine an earlier
                                             --keep-running run left up

THE LAST THREE SCENARIOS ARE DIFFERENT IN KIND
    The first four measure a guest that cooperates: it prints progress on
    a serial line and hands a tar of its own state over on a raw disk.
    The shipping image (iso/profile-release/) deliberately has none of
    that - no collector, no autologin, no console=ttyS0 - because every
    one of those is a thing a stranger's machine would be doing for the
    benefit of a test harness.

    So the release scenario measures it the way a person does: it looks
    at the screen and it presses keys. QEMU's framebuffer needs no
    cooperation from the guest - `screendump` reads what the display
    device holds - and `send-key` puts a scancode on the emulated
    keyboard whether or not anything inside is listening. What comes back
    is a numbered series of PNGs and a log of which keys produced which
    one; the judgement is a human's, which is the honest arrangement for
    a question that is "does this look like an installer".

    It also proves the absences, before it boots anything: see
    inspect_release_iso(), which reads the built ISO - the squashfs
    inside it, not the profile it was made from - and refuses to boot an
    image that has the harness in it.

    release          boot it, and get as far as the disk question.
    release-install  answer the confirmation, and let it install. There
                     is no progress to poll and no completion to wait
                     for, so watch() derives both from the one thing on
                     the screen that is known to move while the
                     installer's main loop lives - the pulsing progress
                     bar - and stops when it stops.
    release-installed  boot the disk with the medium detached, type the
                     login the previous run created, and start a session
                     by hand. Nothing in what was installed reports
                     anything either; this is a person at a keyboard,
                     written down.
    boot-menu        the exception to all of the above, and the only one
                     of the family whose exit code means something. It
                     photographs the first ten seconds and MEASURES the
                     frames: a GRUB theme or a syslinux splash that
                     cannot be loaded falls back to text without an
                     error, on every channel, so "it looked right once"
                     is the only report there would otherwise be. See
                     grade_boot_menu(). It is also the only one that has
                     a reason to be run under BIOS - the two firmwares
                     put up two different menus drawn by two different
                     programs, and a person sees whichever their machine
                     offers.

THE FOUR SCENARIOS, AND WHY THEY ARE ONE TOOL
    An installation is a different scenario, not a different harness.
    Everything the session run needed - a serial line the guest reports
    on, a raw disk it hands evidence over on, framebuffer dumps for the
    boots that never get that far - is exactly what an installation run
    needs, and a second script would be a second place for the marker
    string, the device name and the QMP client to drift.

    What differs between them is the machine, and it differs in ways the
    guest can see:

      session    the ISO, BIOS firmware, one disk (the evidence disk).
                 Unchanged from the run that first proved a desktop
                 comes up, deliberately: it is the measurement everything
                 else is compared against.
      install    the ISO, UEFI firmware, and a SECOND disk to install
                 onto. installer.core.firmware refuses a BIOS machine
                 outright - der Kopf jener Datei sagt, warum: der
                 STARTWEG ist seit dem 11.08.2026 gemessen
                 (iso/test-bios-chain.py), archinstalls Weg dorthin
                 nicht - so this scenario cannot be run the way
                 the session one is. The presence of the target disk is also
                 how the GUEST knows which run this is; see
                 airootfs/usr/local/bin/zepos-smoke.
      installed  no ISO at all, the target disk booted on its own, UEFI
                 with the same non-volatile variables the installation
                 wrote. This is the only scenario that can answer the
                 question the other two cannot: whether what was
                 installed is a system.
      update     the installed disk again, plus a THIRD disk carrying the
                 URL of a repository this machine is serving over HTTP.
                 That disk is both the decision and the address: its
                 presence is how the guest knows which run this is, and
                 its first line is where the packages are. It answers the
                 question an installation leaves open - whether the
                 `https://zeptronit.github.io/ZepOS/$arch` that
                 installer/core/source.py wrote into the target's
                 pacman.conf can be reached, verified and installed from
                 - without anything being published to that URL. See
                 packaging/publish.sh and packaging/serve-repo.sh.

                 Seit UP-1 misst dieser Lauf mehr als den Kanal: die
                 Sonde ruft pacman genau EINMAL - um den Aktualisierer
                 ueberhaupt auf eine Maschine zu bringen, die vor UP-1
                 installiert wurde - und sieht danach zu. Was dann
                 passiert, passiert, weil ein systemd-Zeitgeber ablaeuft.
                 Eine Aktualisierung, die man anstoessen muss, ist keine.

WHY EVIDENCE AND NOT AN ASSERTION
    "The desktop came up" is the claim everything after this task is
    built on. A harness that answers it with an exit code answers it with
    the harness's own opinion. This one brings back three things that can
    be looked at instead:

      * QEMU's framebuffer, dumped through QMP - what the screen shows;
      * the compositor's own screenshot and its log, written inside the
        guest and handed over on a raw disk;
      * the serial console, which is the only channel that survives a
        boot that dies before any of the above exists.

    The exit code is a convenience for scripting, not the result.

WHY THE GUEST TALKS THROUGH A SERIAL LINE AND A RAW DISK
    Both are present before any userspace of ours runs and neither can
    fail for a reason of its own. A network channel would need the
    guest's networking to work, which is one of the things under test; a
    shared filesystem would need a mount that can fail on the one boot
    being measured. iso/profile/airootfs/usr/local/bin/zepos-smoke-collect
    has the other half of this.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
ISO_DIR = REPO / "iso"
OUT = ISO_DIR / "out"

# iso/secureboot.py, which is a module and not a script with a hyphen in
# its name precisely so that this line can be an import. It carries the
# UEFI variable store format and the PE signature reader; both are
# needed here and neither is about booting a machine, which is what this
# file is about.
sys.path.insert(0, str(ISO_DIR))
import secureboot                                    # noqa: E402

# The guest's progress markers. zepos-smoke writes them to /dev/ttyS0 and
# this is the only agreement between the two halves of the harness.
PREFIX = "ZEPOS-SMOKE:"
DONE = f"{PREFIX} DONE"

# Big enough for the tar the collector writes - logs, the generated
# configuration and one screenshot - with room to spare, because a tar
# that runs off the end of the device is a truncated archive and the
# guest cannot report that any more usefully than "it failed".
EVIDENCE_BYTES = 512 * 1024 * 1024

# What the host calls each disk, and what udev therefore calls it in the
# guest: /dev/disk/by-id/virtio-<serial>. The guest side of this
# agreement is in airootfs/usr/local/bin/zepos-smoke-collect and
# zepos-install-unattended, and it replaced /dev/vda - which was right
# only for as long as there was exactly one virtio disk. There are two
# now, and on the installed system one of them is the root filesystem:
# `tar cf /dev/vda` onto that would destroy the system whose first boot
# is being measured.
EVIDENCE_SERIAL = "zepos-evidence"
TARGET_SERIAL = "zepos-target"

# The third disk, and the one that carries a message rather than a
# filesystem. Its presence tells the guest that this is an update run -
# the same discriminator the installation run uses, for the same reason:
# an installed system boots its own kernel and there is no command line
# to pass anything on. Its first line is the repository URL, which is
# what lets the host pick any free port instead of both halves agreeing
# on a number that is occupied on somebody else's machine.
UPDATE_SERIAL = "zepos-update"
UPDATE_BYTES = 1024 * 1024

# Where a QEMU user-mode guest finds the host. slirp's virtual router is
# 10.0.2.2 and it forwards to the host's loopback, which is why
# packaging/serve-repo.sh can bind 127.0.0.1 and still be reachable from
# the guest - the repository is not offered to the network.
SLIRP_HOST = "10.0.2.2"

# The GPT type GUID of a Linux x86-64 root partition, which is what
# archinstall gives the target's root and what tells it apart from the
# EFI system partition next to it. Used only by the probe-staging step
# below, and by name rather than by position: "the second partition" is
# true today and is not a fact about the layout.
LINUX_ROOT_GUID = "4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709"

# A file-backed virtual disk, and nothing else is ever pointed at.
# 24 GiB is comfortably above installer.core.model.MIN_DISK_MIB and
# leaves room for zepos-desktop's forty-four dependencies; the file is
# sparse, so it costs what is written to it and not what it claims.
TARGET_BYTES = 24 * 1024 * 1024 * 1024

# OVMF, for the two scenarios that need UEFI. Split firmware: the code
# is read-only and shared, the variables are per-machine and have to
# persist - `grub-install` ruft unter UEFI efibootmgr auf und schreibt
# damit einen Starteintrag hinein (archinstall 4.4,
# _add_grub_bootloader), und eine Installation, deren Variablen danach
# weggeworfen werden, startet nur noch ueber den Wechselmedien-Rueckfall.
# Das ist etwas anderes als das, was installiert wurde - und ZepOS
# installiert ausdruecklich NICHT mit --removable
# (installer/core/translate.py).
OVMF_CODE_CANDIDATES = (
    Path("/usr/share/edk2/x64/OVMF_CODE.4m.fd"),
    Path("/usr/share/edk2/x64/OVMF_CODE.fd"),
    Path("/usr/share/OVMF/OVMF_CODE.fd"),
    Path("/usr/share/ovmf/x64/OVMF_CODE.fd"),
)
OVMF_VARS_CANDIDATES = (
    Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd"),
    Path("/usr/share/edk2/x64/OVMF_VARS.fd"),
    Path("/usr/share/OVMF/OVMF_VARS.fd"),
    Path("/usr/share/ovmf/x64/OVMF_VARS.fd"),
)

# Per scenario: which firmware, how long to wait, and the string in the
# guest's own summary that counts as a pass. Nothing else in this file
# decides any of the three.
SCENARIOS = {
    "session": {
        "firmware": "bios",
        "timeout": 600,
        "pass": "session=up",
        "what": "does a Hyprland session come up on the generated configuration",
    },
    "release": {
        # UEFI, because that is the only firmware ZepOS can be installed
        # from - installer/core/firmware.py refuses a BIOS machine and
        # says so as its first act. A release run under SeaBIOS would
        # measure the refusal, correctly and uselessly.
        "firmware": "uefi",
        # Nothing reports DONE on this image, so the number is not a
        # deadline for a marker: it is how long the machine is left
        # running while the schedule takes pictures and the script
        # presses keys.
        "timeout": 900,
        # Deliberately empty. There is no guest summary to grade on, and
        # a harness that graded a shipping image on its own opinion of a
        # screenshot would be the thing this scenario exists to avoid.
        # main() grades this one on the image inspection instead, and on
        # the machine having stayed up; what is on the screen is reported,
        # not judged.
        "pass": "",
        "what": "does the shipping medium boot into the installer",
    },
    "boot-menu": {
        # The first ten seconds of the same medium, on either firmware,
        # and nothing after them. `--firmware bios` measures the syslinux
        # menu and the default measures GRUB's; a machine offers one or
        # the other, so both have to be run to have looked at what a
        # person sees.
        "firmware": "uefi",
        # Long enough for OVMF to POST and for the whole ten-second
        # timeout to run down, and no longer: this scenario is over
        # before the kernel is unpacked.
        "timeout": 60,
        # This is the one release-family scenario that IS graded, and it
        # is graded on the frame rather than on a guest's opinion -
        # grade_boot_menu() measures the palette. See its docstring for
        # why a boot menu is the one screen where that is possible: a
        # theme that fails to load is invisible in every other channel.
        "pass": "",
        "what": "does the boot menu come up branded rather than as text",
    },
    "secure-boot": {
        # Zwei Maschinen statt einer, und der Unterschied zwischen ihnen
        # ist das Messergebnis. Beide bekommen OVMF_CODE.secboot.4m.fd,
        # beide dasselbe Medium; die eine hat einen Plattformschluessel
        # im Variablenspeicher und die andere nicht. Siehe
        # run_secure_boot() - "firmware" steht hier trotzdem, weil
        # SCENARIOS die Stelle ist, an der jedes Szenario seine Maschine
        # nennt, und ein Loch in dieser Spalte waere eine Ausnahme, die
        # sich niemand merkt.
        "firmware": "uefi-secure",
        # Beide Laeufe zusammen. Es wird nichts gestartet, was ueber das
        # Startmenue hinausgeht - im erzwingenden Lauf kommt nicht einmal
        # das.
        "timeout": 120,
        "pass": "",
        "what": "lehnt eine Firmware mit Secure Boot das Medium ab, und warum",
    },
    "release-install": {
        # The same medium, driven past the erase confirmation and left to
        # install. Everything the release scenario says about grading
        # applies here twice over: nothing in this image reports an exit
        # code, so what came of it is on the screen and nowhere else.
        "firmware": "uefi",
        "timeout": 5400,
        "pass": "",
        "what": "does the shipping medium install onto a disk when somebody drives it",
    },
    "release-install-ohne-netz": {
        # Dasselbe Medium, dieselben Tasten - und eine Maschine OHNE
        # Netzwerkkarte.
        #
        # WARUM ES DIESEN LAUF GIBT
        #     Befund vom 17.08.2026, von echter Hardware: "Installation
        #     Wizard mit dem Terminal freezed wenn ich versuche ohne
        #     Internet und ohne Passphrase zu installieren." Der
        #     Assistent hing unbegrenzt - archinstall 4.4 wartet in
        #     lib/installer.py:189-202 in einem `while True` ohne Frist
        #     darauf, dass die Uhr aus dem Netz gestellt wird, und das
        #     geschieht ohne Netz nie. Gewartet wurde NACH
        #     perform_filesystem_operations(), also vor einer bereits
        #     geteilten Platte.
        #
        #     Kein Lauf dieser Reihe konnte das sehen, weil jeder von
        #     ihnen `-nic user` bekam. Der Fall ohne Netz war schlicht
        #     nie gefahren worden.
        #
        # WAS ER MISST
        #     Dass innerhalb weniger Minuten eine LESBARE Meldung auf
        #     dem Schirm steht. Nicht, dass etwas installiert wird - das
        #     kann ohne Netz nicht gelingen, solange die Arch-Basis vom
        #     festgenagelten ALA-Spiegel kommt (spec 8.4). Ein
        #     stehendes Bild ohne Text ist der Fehlschlag, und der ist
        #     auf den Bildern zu sehen.
        #
        # Und "ohne Passphrase", wie gemeldet: dieser Lauf ist der
        # einzige der Reihe, der die Verschluesselung ABWAEHLT.
        "firmware": "uefi",
        "timeout": 1800,
        "pass": "",
        "what": "sagt das Medium ohne Netz etwas Verstaendliches, statt einzufrieren",
    },
    "release-installed": {
        # And the only question the two above cannot answer: whether what
        # was installed is a system. No medium, no harness inside, no
        # autologin - so the login is typed in like any other.
        "firmware": "uefi",
        "timeout": 1800,
        "pass": "",
        "what": "does what the shipping medium installed boot with the medium gone",
    },
    "install": {
        # An installation downloads the base system and the forty-odd
        # Arch dependencies of zepos-desktop. Forty minutes is not
        # generous, it is the difference between "it failed" and "the
        # harness gave up on it".
        "firmware": "uefi",
        "timeout": 2400,
        "pass": "install=0",
        "what": "does the installer partition a real disk and complete",
    },
    "installed": {
        "firmware": "uefi",
        "timeout": 900,
        "pass": "session=up",
        "what": "does the installed system boot into a session of its own",
    },
    "update": {
        # No session comes up in this one, so the settling time the other
        # two spend is not spent here. Der Zeitgeber schon: die
        # ausgelieferte Einstellung ist OnBootSec=15min, und die Sonde
        # SIEHT ZU, statt den Dienst zu starten - das ist die ganze
        # Frage von UP-1. Fuenfundvierzig Minuten sind also nicht
        # grosszuegig, sondern eine Viertelstunde Warten plus der
        # Paketverkehr ueber ein QEMU-Benutzernetz plus Luft.
        "firmware": "uefi",
        "timeout": 2700,
        "pass": "update=0",
        "what": "does the installed system update itself, with nobody helping",
    },
}


# Die Laengengrenze eines Unix-Sockets. sockaddr_un.sun_path fasst auf
# Linux 108 Bytes einschliesslich der abschliessenden Null; alles darueber
# beantwortet der Kernel mit "AF_UNIX path too long", und zwar erst beim
# connect(), also nachdem QEMU schon laeuft.
#
# GEMESSEN, 11.08.2026: ein Arbeitsbaum unter
# /tmp/claude-.../scratchpad/zepos-up1 ergibt fuer run/qmp.sock 130 Zeichen.
# Der Lauf startete die Maschine, brach beim ersten QMP-Befehl ab und
# hinterliess einen Traceback statt einer Messung. Ein Klon liegt nicht
# immer in /home/<name>/zepos - CI-Verzeichnisse, Worktrees und
# Wegwerf-Klone sind regelmaessig tiefer.
SOCKET_LIMIT = 100


def qmp_socket(run: Path) -> Path:
    """Der Pfad des QMP-Sockets, kurz genug fuer AF_UNIX.

    Normalerweise im Laufverzeichnis, wo er neben allem anderen liegt,
    was der Lauf hinterlaesst. Ist dieser Pfad zu lang, weicht er nach
    /tmp aus - unter einem Namen, der AUS DEM LAUFVERZEICHNIS ABGELEITET
    ist und nicht zufaellig: `--attach` verbindet sich mit dem Socket
    eines frueheren Laufs und muesste ihn sonst raten.
    """
    inside = run / "qmp.sock"
    if len(str(inside)) < SOCKET_LIMIT:
        return inside
    digest = hashlib.sha256(str(run).encode()).hexdigest()[:12]
    return Path("/tmp") / f"zepos-qmp-{digest}.sock"


class Qmp:
    """The smallest QMP client that can take a screenshot.

    QEMU's own Python bindings would be a dependency the repository does
    not otherwise have, for two commands.
    """

    # Wie lang der Pfad eines Unix-Sockets sein darf. Nicht PATH_MAX,
    # sondern sizeof(sun_path) aus linux/un.h, und der Rest des Feldes
    # ist die abschliessende Null.
    #
    # Gemessen am 11.08.2026, in einem git-Arbeitsbaum unter
    # /tmp/.../scratchpad/zepos-boot: connect() antwortete mit
    # "OSError: AF_UNIX path too long" und einem Rueckverfolgungsprotokoll
    # mitten aus dem Aufbau eines Laufs heraus. Der Fehler ist richtig und
    # sagt nur nicht, welcher Pfad gemeint ist und dass er nicht von QEMU
    # kommt - beides steht jetzt hier, weil ein Arbeitsbaum an einer
    # tiefen Stelle der Normalfall ist, sobald jemand an zwei Zweigen
    # gleichzeitig arbeitet.
    SUN_PATH_MAX = 107

    def __init__(self, path: Path, timeout: float = 30.0):
        if len(str(path).encode()) > self.SUN_PATH_MAX:
            raise SystemExit(
                f"der QMP-Socket liegt {len(str(path).encode())} Zeichen tief "
                f"und ein Unix-Socket darf {self.SUN_PATH_MAX} haben:\n"
                f"  {path}\n"
                f"Das ist eine Grenze des Kernels und keine von QEMU. Ein "
                f"Arbeitsbaum naeher an der Wurzel loest es.")
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(str(path))
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        self.sock.settimeout(30.0)
        self.buffer = b""
        self._read()                      # the greeting
        self.execute("qmp_capabilities")

    def _read(self) -> dict:
        """One JSON object, skipping the asynchronous events QEMU emits."""
        while True:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                message = json.loads(line)
                if "event" in message:
                    continue
                return message
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("QMP socket closed")
            self.buffer += chunk

    def execute(self, command: str, **arguments) -> dict:
        payload = {"execute": command}
        if arguments:
            payload["arguments"] = arguments
        self.sock.sendall(json.dumps(payload).encode() + b"\n")
        return self._read()

    def screenshot(self, target: Path) -> Path | None:
        """A framebuffer dump, as PNG where QEMU can and PPM where it cannot.

        format=png arrived in QEMU 7.1. Falling back rather than
        requiring it keeps the harness usable on an older host, and a PPM
        is still a picture.

        A dead QEMU is answered with None rather than an exception. The
        harness takes its last screenshot on the way out, including on
        the path where the machine has just died - and a crash there
        would throw away the serial log and the evidence disk that had
        already been collected. Measured, on a run whose QEMU was killed
        from outside: BrokenPipeError, no summary, no unpacked evidence.
        """
        for suffix, arguments in ((".png", {"format": "png"}), (".ppm", {})):
            path = target.with_suffix(suffix)
            try:
                reply = self.execute("screendump", filename=str(path), **arguments)
            except (OSError, ConnectionError, json.JSONDecodeError):
                return None
            if "error" not in reply and path.exists() and path.stat().st_size:
                return path
        return None

    def press(self, chord: str) -> None:
        """One keystroke on the emulated keyboard, e.g. "ret" or "alt-f4".

        The other half of a framebuffer dump, and the reason the release
        scenario needs nothing from inside the guest: `send-key` puts
        scancodes on the emulated keyboard controller, so it works on a
        boot menu, on a text console and on a Wayland surface alike -
        none of them has to agree to anything.

        The names are QEMU's qcodes, which are POSITIONS on a US
        keyboard. What the guest makes of a position is the guest's
        keymap: this medium sets a German one (/etc/vconsole.conf and
        XKB_DEFAULT_LAYOUT), so "y" produces z and "z" produces y. Digits
        and the keys below are the same on both, which is why the script
        that drives the installer uses those.
        """
        keys = [{"type": "qcode", "data": name} for name in chord.split("-")]
        self.execute("send-key", keys=keys)

    def type_text(self, text: str, layout: str = "us") -> None:
        """Type an ASCII string, one keystroke per character.

        `layout` names the keymap the GUEST has loaded, not the host's:
        a qcode is a position, so the same position has to be looked up
        in a different table depending on what the guest thinks that
        position means. See _QCODES_DE.
        """
        table = _LAYOUTS[layout]
        for character in text:
            qcode = table.get(character)
            if qcode is None:
                raise ValueError(
                    f"nothing maps the character {character!r} to a key "
                    f"on the {layout} layout")
            self.press(qcode)
            time.sleep(0.05)


# Enough of a keyboard to answer an installer's questions, and no more.
# Letters and digits are qcodes of the same name; everything else needs
# spelling out. Uppercase is deliberately absent: it needs a shift chord
# and the German layout puts three of the characters that would need one
# somewhere else entirely, so a test that typed them would be testing the
# harness's idea of a keyboard.
_QCODES: dict[str, str] = {
    **{character: character for character in "abcdefghijklmnopqrstuvwxyz0123456789"},
    " ": "spc",
    "-": "minus",
    ".": "dot",
    ",": "comma",
    "=": "equal",
    "/": "slash",
    # Shifted. Uppercase and the underscore are what a kernel parameter
    # needs, and they sit in the same place on the two layouts this
    # medium is typed on - GRUB's US and the German one the booted
    # system sets - with the y/z swap noted on press() applying to both
    # cases alike. Anything else that needs shift is left out on purpose.
    **{character.upper(): f"shift-{character}"
       for character in "abcdefghijklmnopqrstuvwxyz"},
    "_": "shift-minus",
    "\n": "ret",
}

# The same characters on the keymap the SHIPPING medium loads, and on the
# one every system installed from it loads with it: de-latin1 in
# /etc/vconsole.conf, de in XKB. A qcode names a POSITION, so this table
# says where each character sits on a US board - which is a different
# place for a third of the printable ASCII set.
#
# It exists because the release scenario is the first one that types
# anything into the GUEST rather than into a boot loader. GRUB reads the
# keyboard as US, which is what _QCODES above is for and why its entry
# for "_" (shift on the US minus key) is right there and wrong here: on a
# German board that position is "?" and the underscore has moved to the
# key left of the right shift.
#
# Only the characters this harness actually types are listed. A fuller
# table would be a keyboard driver written from memory, and every entry
# in it that is never pressed is an untested claim.
_QCODES_DE: dict[str, str] = {
    **_QCODES,
    # QWERTZ. The only two letters that move, in both cases.
    "y": "z", "z": "y",
    "Y": "shift-z", "Z": "shift-y",
    # The keys around the right-hand edge of the alphabetic block.
    "-": "slash",             # US "/?" carries "-_" here
    "_": "shift-slash",
    "/": "shift-7",           # and "/" has moved onto the digit row
    ":": "shift-dot",
    ";": "shift-comma",
    "=": "shift-0",
    "+": "bracket_right",
    "$": "shift-4",           # the one shifted digit both layouts agree on
}

_LAYOUTS: dict[str, dict[str, str]] = {"us": _QCODES, "de": _QCODES_DE}


# Which image a scenario boots. `*.iso` stopped being an answer when
# there were two profiles: both write into iso/out/, mkarchiso names the
# harness zepos-smoke-<date> and the shipping medium zepos-<date>, and
# "the newest file" would hand the release scenario whichever was built
# last. The pattern is per scenario and the digit is what keeps
# zepos-[0-9]* from matching zepos-smoke-*.
ISO_PATTERNS = {"release": "zepos-[0-9]*.iso",
                "release-install": "zepos-[0-9]*.iso",
                "release-install-ohne-netz": "zepos-[0-9]*.iso",
                "boot-menu": "zepos-[0-9]*.iso",
                "secure-boot": "zepos-[0-9]*.iso"}
SMOKE_ISO_PATTERN = "zepos-smoke-*.iso"

# The three scenarios that measure the shipping medium, and the one thing
# they have in common: the guest says nothing, so they are driven and
# photographed rather than listened to. main() sends all three to
# run_release() instead of to the loop that polls a serial line no image
# in this family writes to.
RELEASE_FAMILY = ("release", "release-install", "release-install-ohne-netz",
                  "release-installed", "boot-menu")

# The disk the shipping medium installs onto, and the EFI variables the
# installation writes its boot entry into. Both are separate from the
# smoke image's iso/out/target.img and iso/out/efivars.fd on purpose: the
# question here is what THIS medium produces, and a run that booted the
# other one's installation by accident would answer it wrongly and
# convincingly.
RELEASE_TARGET = OUT / "release-target.img"
RELEASE_EFIVARS = OUT / "release-efivars.fd"

# And a THIRD disk, for the scenario that only looks. `release` needs a
# disk because the installer has nothing to offer without one - but it
# never installs, and it recreates whatever it is pointed at. Pointed at
# RELEASE_TARGET it therefore erases the installation the pair above just
# produced, and the next `release-installed` run boots an empty disk and
# reports, correctly and uselessly, that there is no system on it.
# Measured, on this machine, immediately after the first installation run
# ever driven from this medium.
RELEASE_BOOT_TARGET = OUT / "release-boot-target.img"

# Und eine VIERTE Platte samt eigenem Variablenspeicher, fuer den Lauf
# ohne Netz. Aus genau demselben Grund wie RELEASE_BOOT_TARGET, nur
# schaerfer: dieser Lauf soll ABBRECHEN, und ein Abbruch, der die
# Installation der Nachbarlaeufe mitnimmt, waere ein teurer Weg,
# nichts zu erfahren. Der eigene Variablenspeicher kommt hinzu, weil
# `release-install` seinen loescht und `release-installed` genau darin
# den Starteintrag sucht - und weil auf dieser Maschine durchaus zwei
# Laeufe gleichzeitig laufen: am 17.08.2026 lief waehrend dieser
# Aenderung ein `release-installed` mit RELEASE_EFIVARS geoeffnet.
RELEASE_OHNE_NETZ_TARGET = OUT / "release-ohne-netz-target.img"
RELEASE_OHNE_NETZ_EFIVARS = OUT / "release-ohne-netz-efivars.fd"

RELEASE_TARGETS = {"release": RELEASE_BOOT_TARGET,
                   "release-install": RELEASE_TARGET,
                   "release-install-ohne-netz": RELEASE_OHNE_NETZ_TARGET,
                   "release-installed": RELEASE_TARGET,
                   # And none at all for the scenario that never reaches
                   # the installer. A boot menu has nothing to offer a
                   # disk, and creating one would erase whatever a
                   # previous run installed for the sake of a device
                   # nothing looks at.
                   "boot-menu": None}


def newest_iso(pattern: str = SMOKE_ISO_PATTERN) -> Path:
    images = sorted(OUT.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not images:
        build = ("./iso/build.sh --profile release" if pattern != SMOKE_ISO_PATTERN
                 else "./iso/build.sh")
        sys.exit(f"no {pattern} in iso/out/ - run {build} first")
    return images[-1]


def _first_existing(candidates, what: str) -> Path:
    for path in candidates:
        if path.is_file():
            return path
    sys.exit(
        f"no {what} found. UEFI scenarios need OVMF; on Arch it is the "
        f"edk2-ovmf package. Looked in: "
        + ", ".join(str(path) for path in candidates)
    )


def efi_variables(store: Path) -> Path:
    """A writable copy of OVMF's variable store, made once and kept.

    Kept, and that is the point of it being here rather than in the run
    directory the harness wipes: `bootctl install` writes an EFI boot
    entry into these variables during the installation, and the run that
    boots the installed disk has to find it. A fresh copy for that run
    would test the removable-media fallback path
    (\\EFI\\BOOT\\BOOTX64.EFI) instead - which may well work, and would
    quietly answer a different question from the one asked.
    """
    if not store.is_file():
        template = _first_existing(OVMF_VARS_CANDIDATES, "OVMF variable template")
        store.write_bytes(template.read_bytes())
    return store


def qemu_command(
    run: Path,
    *,
    iso: Path | None,
    target: Path | None,
    update: Path | None,
    firmware: str,
    efivars: Path | None,
    vga: str,
    memory: str,
    kvm: bool,
    evidence: Path | None = None,
    network: bool = True,
) -> list[str]:
    """The machine the guest wakes up on.

    Every device here is a decision the guest can see:

      -vga virtio      a KMS device with dumb buffers and NO render node.
                       That is the GPU-less case ZepOS has to survive,
                       and the reason iso/README.md's table about
                       LIBGL_ALWAYS_SOFTWARE exists.
      -display none    nothing is shown on the developer's screen; the
                       framebuffer is still there and screendump reads
                       it. A run must not need a human watching.
      virtio-blk       the disks, each with a `serial` that udev turns
                       into /dev/disk/by-id/virtio-<serial> in the guest.
                       Named rather than positional because there is more
                       than one of them now - see EVIDENCE_SERIAL.
      -nic user        slirp, entirely inside the QEMU process. It gives
                       the guest a working DHCP lease without touching
                       the host's routing - which matters on this
                       machine, where an IPsec tunnel owns all of
                       RFC1918 (spec §10.1). An installation needs it:
                       pacstrap fetches the base system over it.
      -nic none        UND DER FALL OHNE. `network=False` gibt der
                       Maschine ueberhaupt keine Netzwerkkarte - nicht
                       eine ohne Verbindung, sondern gar keine. Das ist
                       der Zustand, den ein Nutzer am 17.08.2026 auf
                       echter Hardware gemeldet hat ("ohne Internet"),
                       und der Assistent fror darin ein statt zu
                       scheitern. `none` und nicht das Weglassen der
                       Zeile: ohne jedes -nic gibt QEMU dem Gast seine
                       eingebaute Vorgabekarte, also genau das
                       Gegenteil.
      -no-reboot       a guest that decides to reboot has failed; let it
                       stop so the failure is visible. It is also what
                       makes the installation run end cleanly - the guest
                       powers itself off when it is done.
      pflash           UEFI. Two units: read-only firmware code, and a
                       writable variable store that outlives the run.
                       `uefi-secure` is the same two units with the
                       secboot build of OVMF in the first, and see there
                       for the three settings that build needs.
    """
    command = [
        "qemu-system-x86_64",
        "-machine", "q35",
        "-m", memory,
        "-smp", "2",
        "-vga", vga,
        "-display", "none",
        "-no-reboot",
        "-device", "virtio-rng-pci",
        "-nic", "user,model=virtio-net-pci" if network else "none",
        "-serial", f"file:{run / 'serial.log'}",
        "-qmp", f"unix:{qmp_socket(run)},server,nowait",
    ]

    if firmware == "uefi":
        code = _first_existing(OVMF_CODE_CANDIDATES, "OVMF firmware")
        command += [
            "-drive", f"if=pflash,unit=0,format=raw,readonly=on,file={code}",
            "-drive", f"if=pflash,unit=1,format=raw,file={efivars}",
        ]
    elif firmware == "uefi-secure":
        # Dieselben zwei pflash-Einheiten und eine ANDERE Firmware, plus
        # drei Einstellungen, ohne die die andere Firmware nicht laeuft.
        #
        # OVMF_CODE.secboot.4m.fd ist mit SMM_REQUIRE gebaut - das sagt
        # /usr/share/qemu/firmware/50-edk2-ovmf-x86_64-secure-4m.json in
        # seiner features-Liste ("requires-smm"), und es ist der Grund
        # fuer alle drei:
        #
        #   smm=on            der Systemverwaltungsmodus selbst. Ohne ihn
        #                     bleibt die Firmware beim Aufsetzen stehen.
        #   pflash01 secure   nur SMM-Code darf in den Variablenspeicher
        #                     schreiben. Das ist der ganze Sinn der Sache:
        #                     ohne diese Zeile koennte ein Gast seine
        #                     eigene db aendern, und dann misst der Lauf
        #                     eine Firmware, die es auf keiner Hardware
        #                     gibt.
        #   disable_s3        edk2 unterstuetzt S3 unter SMM_REQUIRE
        #                     nicht und sagt das mit einer Warnung, die
        #                     im seriellen Protokoll steht statt auf dem
        #                     Schirm - also abschalten, statt sie zu
        #                     ueberlesen.
        code = _first_existing(secureboot.OVMF_SECBOOT_CODE_CANDIDATES,
                               "OVMF mit Secure Boot")
        command[1:3] = ["-machine", "q35,smm=on"]
        command += [
            "-global", "driver=cfi.pflash01,property=secure,value=on",
            "-global", "ICH9-LPC.disable_s3=1",
            "-drive", f"if=pflash,unit=0,format=raw,readonly=on,file={code}",
            "-drive", f"if=pflash,unit=1,format=raw,file={efivars}",
        ]

    if iso is not None:
        command += ["-boot", "d", "-cdrom", str(iso)]
    else:
        command += ["-boot", "c"]

    # The shipping image has no collector, so it gets no evidence disk:
    # an unexplained blank disk on the bus is one more thing the person
    # driving the installer would have to tell apart from their own.
    if evidence is not None:
        command += [
            "-drive", f"file={evidence},format=raw,if=none,id=evidence",
            "-device", f"virtio-blk-pci,drive=evidence,serial={EVIDENCE_SERIAL}",
        ]
    if target is not None:
        command += [
            "-drive", f"file={target},format=raw,if=none,id=target",
            "-device", f"virtio-blk-pci,drive=target,serial={TARGET_SERIAL}",
        ]
    if update is not None:
        command += [
            "-drive", f"file={update},format=raw,if=none,id=update",
            "-device", f"virtio-blk-pci,drive=update,serial={UPDATE_SERIAL}",
        ]

    if kvm:
        # KVM or the software-rendered compositor takes long enough that
        # the run's timeouts stop meaning anything.
        command[1:1] = ["-enable-kvm", "-cpu", "host"]
    return command


# --------------------------------------------------------------------
# The update run's three extra pieces
# --------------------------------------------------------------------

def free_port() -> int:
    """A port the kernel has just told us is free.

    Asked for rather than agreed on. The guest learns the number from the
    update disk, so nothing here has to be a constant - and a constant
    would be the one part of this harness that fails on a machine where
    somebody else got there first.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def serve_repository(run: Path, port: int, repo_dir: Path | None) -> subprocess.Popen:
    """Start packaging/serve-repo.sh and wait until it answers.

    Through the script rather than through `http.server` directly,
    because what has to be served is not packaging/out/ but the STAGED
    tree - publish.sh resolves the symlink repo-add makes for zepos.db,
    drops the .old backup and adds .nojekyll, and a static host serves
    what is there rather than what was meant. Measuring against
    packaging/out/ would measure a layout that will never be published.
    """
    log = open(run / "repo-server.log", "w")
    command = [str(REPO / "packaging" / "serve-repo.sh"),
               "--port", str(port), "--bind", "127.0.0.1"]
    if repo_dir is not None:
        command += ["--into", str(repo_dir), "--no-stage"]
    else:
        command += ["--into", str(run / "pages")]
    print("  " + " ".join(command))
    server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)

    # Poll the one file pacman asks for first. A server that is up but
    # serving the wrong directory answers 404 here, which is a failure
    # worth having now rather than as a guest that reports "target not
    # found" twenty minutes later.
    deadline = time.monotonic() + 60
    url = f"http://127.0.0.1:{port}/x86_64/zepos.db"
    while time.monotonic() < deadline:
        if server.poll() is not None:
            sys.exit(f"the repository server exited rc={server.returncode}; "
                     f"see {run / 'repo-server.log'}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    print(f"  repository server: {url} ({response.length} bytes)")
                    return server
        except Exception:
            time.sleep(0.5)
    server.terminate()
    sys.exit(f"the repository server never served {url}")


def write_update_disk(path: Path, url: str) -> Path:
    """The disk that says which run this is and where the packages are.

    A megabyte of zeroes with one line at the front. No filesystem,
    deliberately: the guest reads it with `head -c`, which needs no mount
    that could fail for a reason of its own on the one boot being
    measured - the same argument the evidence disk is written under, in
    the other direction.
    """
    with open(path, "wb") as handle:
        handle.truncate(UPDATE_BYTES)
        handle.seek(0)
        handle.write((url + "\n").encode())
    return path


def stage_update_probe(target: Path) -> None:
    """Put the current harness scaffolding into the installed system.

    zepos-install-unattended writes exactly these files during phase 5 of
    an installation, so on a disk installed from a current ISO this
    rewrites four files with the same content. It exists for the disk
    that was installed BEFORE the update probe was written, which is
    every disk today - reinstalling in order to test an update would mean
    a forty-minute installation before every ten-minute measurement, and
    the scaffolding is the harness's own, not the distribution's.

    Through a privileged container because loop devices need root, and
    `sudo -n docker` is the only elevation this project has. iso/build.sh
    already runs mkarchiso the same way and for the same reason.
    """
    layout = subprocess.run(["sfdisk", "-J", str(target)],
                            capture_output=True, text=True)
    if layout.returncode != 0:
        sys.exit(f"could not read the partition table of {target}: {layout.stderr}")
    partitions = json.loads(layout.stdout)["partitiontable"]
    sector = partitions.get("sectorsize", 512)
    roots = [p for p in partitions["partitions"]
             if p.get("type", "").upper() == LINUX_ROOT_GUID]
    if len(roots) != 1:
        sys.exit(f"{target} has {len(roots)} Linux root partitions; expected one")
    offset = roots[0]["start"] * sector

    airootfs = ISO_DIR / "profile" / "airootfs"
    script = f"""
        set -euo pipefail

        # A privileged container gets a fresh /dev with no loop nodes in
        # it, so `losetup --find` fails with "device node is lost": the
        # kernel allocates an index and there is nothing in this /dev to
        # address it by. The nodes are therefore made here - rather than
        # by bind-mounting the host's /dev, which would hand the
        # container every disk on this machine to write to.
        #
        # And they are TRIED rather than picked. /dev/loop9 was a
        # constant here for exactly one run: a leftover from an earlier
        # session still held it, and the whole scenario died on
        # "Device or resource busy" - a failure that says nothing about
        # ZepOS and cost the run.
        mknod /dev/loop-control c 10 237 2>/dev/null || true
        device=""
        for index in $(seq 0 15); do
            mknod "/dev/loop$index" b 7 "$index" 2>/dev/null || true
            if losetup -o {offset} "/dev/loop$index" /target/{target.name} 2>/dev/null; then
                device="/dev/loop$index"
                break
            fi
        done
        [ -n "$device" ] || {{ echo "no free loop device" >&2; exit 1; }}
        echo "loop device $device at offset {offset}"

        # Detach on the way out however this ends. A loop device left
        # attached to the target image is what makes the NEXT run fail,
        # and it fails with a message about a busy device rather than
        # about the leftover.
        cleanup() {{
            umount /mnt/root 2>/dev/null || true
            losetup -d "$device" 2>/dev/null || true
        }}
        trap cleanup EXIT

        mkdir -p /mnt/root
        mount "$device" /mnt/root
        install -Dm755 /probe/usr/local/bin/zepos-smoke         /mnt/root/usr/local/bin/zepos-smoke
        install -Dm755 /probe/usr/local/bin/zepos-smoke-collect /mnt/root/usr/local/bin/zepos-smoke-collect
        install -Dm755 /probe/usr/local/bin/zepos-smoke-update  /mnt/root/usr/local/bin/zepos-smoke-update
        install -Dm644 /probe/etc/systemd/system/zepos-update-probe.service \\
            /mnt/root/etc/systemd/system/zepos-update-probe.service
        # The symlink `systemctl enable` would write for this unit's
        # [Install] section. Written directly because chrooting into the
        # target only to run systemctl needs /proc, /sys and a working
        # dbus for a command whose whole output is this one link.
        install -d /mnt/root/etc/systemd/system/multi-user.target.wants
        ln -sf /etc/systemd/system/zepos-update-probe.service \\
            /mnt/root/etc/systemd/system/multi-user.target.wants/zepos-update-probe.service
        ls -la /mnt/root/usr/local/bin/
        sync
    """
    staged = subprocess.run(
        ["sudo", "-n", "docker", "run", "--rm", "--privileged",
         "-v", f"{target.parent}:/target",
         "-v", f"{airootfs}:/probe:ro",
         "archlinux:latest", "bash", "-c", script],
        capture_output=True, text=True)
    if staged.returncode != 0:
        sys.exit("could not stage the update probe into the target disk:\n"
                 + staged.stdout + staged.stderr)
    print("  update probe staged into the installed system")


# --------------------------------------------------------------------
# The shipping medium
# --------------------------------------------------------------------

# Paths that must not exist in the image somebody downloads, and the
# reason each of them is a harness. Checked against the squashfs inside
# the built ISO rather than against iso/profile-release/, because the
# profile is not the image: a package can bring an autologin drop-in, and
# a mis-assembled profile is exactly the mistake worth catching.
HARNESS_PATHS = (
    ("usr/local/bin/zepos-smoke", "the smoke run"),
    ("usr/local/bin/zepos-smoke-collect", "the evidence collector"),
    ("usr/local/bin/zepos-smoke-update", "the update probe"),
    ("usr/local/bin/zepos-install-unattended", "the unattended installation"),
    ("usr/local/share/zepos-install/unattended-install.json",
     "the answer file, root password included"),
    ("etc/systemd/system/getty@tty1.service.d/autologin.conf", "the autologin"),
    ("home/zepos/.bash_profile", "the live user's session"),
)

# What the release run does after the machine has settled, when nothing
# else was asked for. Deliberately short: everything past the first
# screen depends on what the previous screen showed, and a script that
# guessed would produce a series of pictures of a form nobody filled in.
RELEASE_SCRIPT = (
    "shot:01-erste-seite",
    # Tab moves off the language dropdown and onto "Weiter", which the
    # focus ring in the next picture shows: that alone answers "does it
    # respond to input", before anything has been changed.
    "key:tab", "wait:1", "shot:02-weiter-fokussiert",
    # And through to the disk question, which is the one that matters -
    # it is the last screen before an erase and the first that shows the
    # installer has seen the machine it is running on. The wireless page
    # in between is skipped by the installer itself when the machine has
    # no wireless adapter, which a QEMU guest has not.
    "key:spc", "wait:4", "shot:03-datentraeger",
    # The disk list itself. Measured focus order on that page: the row,
    # then Zurueck, then Weiter - so two tabs from the row is forward and
    # one is back.
    "key:tab", "wait:1", "key:spc", "wait:2", "shot:04-datentraeger-liste",
    "key:esc", "wait:1",
    "key:tab", "key:tab", "wait:1", "key:spc", "wait:4", "shot:05-benutzer",
    # THE KEYBOARD PROBE, and the reason this scenario types anything at
    # all. `xyz-abc` is the exact string whose arrival as `xzy/abc`
    # reported the US-layout defect; it goes into "Rechnername", which is
    # the first tab stop on this page and - unlike the four password
    # rows - is NOT masked, so the picture is the measurement rather than
    # six dots. Every character in it moves between the two layouts:
    # y and z swap, and `-` is on the US `/?` key.
    #
    # It is also a valid hostname (validate.HOSTNAME_PATTERN), so nothing
    # here depends on an error message that might be reworded. This
    # scenario installs nothing, so what it leaves in the field is
    # discarded when the machine is powered off.
    "key:tab", "wait:0.5", "text:xyz-abc", "wait:1",
    "shot:06-tastatur-xyz-abc",
)

# The answers the installation run gives to the user page, and then to
# the login prompt of the system that comes out of it. They are here
# rather than inside the script below because the second run has to type
# the same two strings the first one did, and a password that exists in
# two places is a password that is wrong in one of them.
#
# Letters and digits only, and no y or z. Not because the keyboard table
# cannot reach them - _QCODES_DE has the QWERTZ swap and the moved
# punctuation - but because the ONE thing that must not be a guess is the
# pair of strings the login prompt is going to compare against. A wrong
# character in the password costs a whole installation to find out.
# `.local/bin/start-hyprland` and `zepos-generate` in the installed run
# exercise the swapped keys instead, where being wrong costs a retry.
RELEASE_USER = "tester"
RELEASE_PASSWORD = "installer42"
RELEASE_ROOT_PASSWORD = "rootpass99"
RELEASE_HOSTNAME = "zepos"

# Die Plattenpassphrase - und sie ist als EINZIGE in dieser Datei
# absichtlich mit y und z gebaut.
#
# WARUM SIE FRUEHER KEINS VON BEIDEN HATTE
#     Bis zum 13.08.2026 stand hier "plattenkennwort4", unter derselben
#     Regel wie die zwei Passwoerter darueber: Buchstaben und Ziffern,
#     kein y und kein z. Die Begruendung war Vorsicht - die Passphrase
#     wird nach der Installation ein zweites Mal gebraucht, an einer
#     Abfrage im initramfs, die die Tastaturbelegung aus
#     /etc/vconsole.conf benutzt, und ein Zeichen, das dort anders
#     liegt, waere eine Platte gewesen, die dieser Messstand selbst
#     nicht mehr aufbekommt.
#
# WARUM SIE JETZT GENAU DAS ENTHAELT
#     Weil diese Vorsicht die eine Frage wegdefiniert hat, die an dieser
#     Stelle zaehlt. Seit dem 13.08.2026 fragt ZepOS die Passphrase in
#     einem Plymouth-Fenster ab (installer/core/translate.py,
#     PLYMOUTH_COMMAND), und das Gefaehrliche an einem solchen Fenster
#     ist nicht sein Aussehen, sondern dass es die Zeichen VERDECKT: wer
#     auf der falschen Belegung tippt, sieht Punkte wie jeder andere
#     auch und erfaehrt es erst, wenn nach zehn Sekunden Argon2id
#     "falsch" dasteht. Mit einer Passphrase ohne y und z konnte dieser
#     Messstand eine vertauschte Belegung gar nicht bemerken - er haette
#     ein schoenes Bild gemeldet und eine Maschine hinterlassen, aus der
#     ein Mensch sich aussperrt.
#
#     Jetzt ist die Passphrase selbst die Probe. _QCODES_DE bildet "y"
#     auf den qcode "z" ab und umgekehrt (die QWERTZ-Vertauschung, siehe
#     dort); getippt wird also die POSITION, die auf einer deutschen
#     Belegung ein y ergibt. Laedt die Abfrage im initramfs die deutsche
#     Belegung, geht die Platte auf. Laedt sie das eingebaute "us", kommt
#     an derselben Position ein z an, die Passphrase stimmt nicht, und
#     der Lauf bleibt sichtbar an der Abfrage stehen. Beides ist ein
#     Befund; das Schweigen von vorher war keiner.
#
# Mindestens zwoelf Zeichen, weil installer.core.crypt kuerzere ablehnt
# (MIN_PASSPHRASE_LENGTH, und warum gerade zwoelf steht dort). Diese hier
# hat fuenfzehn und traegt y wie z je einmal.
RELEASE_DISK_PASSPHRASE = "plattenzyklus47"

# WHICH KEYBOARD EACH RUN TYPES ON
#     All three of them the German one now, and that was not always true.
#
#     MEASURED, on the medium before the repair: `xyz-abc` typed through
#     the German table above arrived in the installer's password field as
#     `xzy/abc` - i.e. every qcode produced what a US board would produce.
#     The graphical installer runs inside cage (see
#     iso/profile-release/airootfs/usr/local/bin/zepos-live-session), and
#     nothing on the medium set XKB_DEFAULT_LAYOUT, so wlroots took
#     libxkbcommon's compiled-in default, which is `us`.
#     /etc/vconsole.conf's KEYMAP=de governs the CONSOLE - which is why
#     the text fallback always typed correctly - and does not reach a
#     Wayland compositor at all.
#
#     That was a defect of the medium and not of this harness: a German
#     installer asking a German user for a password, twice, in a masked
#     field, on a layout that is not the one printed on their keys. The
#     fields agree with each other, the installation completes, and the
#     account cannot be logged into.
#
#     zepos-live-session now exports XKB_DEFAULT_LAYOUT before cage,
#     derived from the language the session speaks, so the compositor
#     loads the same layout the console has. The `de` entries below are
#     therefore what this harness has to type through, and the run that
#     proves it is RELEASE_SCRIPT's keyboard probe: `xyz-abc` sent as
#     German positions into a VISIBLE field, photographed.
#
#     "release-installed" ist ebenfalls `de`, und das ist seit der
#     Anmeldung keine Ableitung mehr, sondern eine Kette: archinstall
#     schreibt KEYMAP=de-latin1 aus locale_config.kb_layout nach
#     /etc/vconsole.conf, und src/bin/zepos-greeter schlaegt daraus ueber
#     /usr/share/systemd/kbd-model-map das XKB-Layout nach und exportiert
#     es, bevor der Compositor startet. Getippt wird jetzt IN einem
#     Compositor - vorher war es eine Konsole -, und ohne diesen Schritt
#     waere es libxkbcommons eingebautes "us".
#
# Only the scenarios that TYPE are in here, and the boot-menu one is
# deliberately absent rather than present with a value nothing reads: it
# presses no keys at all. run_release() looks it up with .get(), so this
# dict stays a list of the runs whose keyboard is a claim about the
# medium - which is what tests/iso/test_release_profile.py reads it as.
RELEASE_LAYOUT = {"release": "de", "release-install": "de",
                  "release-install-ohne-netz": "de",
                  "release-installed": "de"}

# The whole installation, as keystrokes. Every position in it was
# measured on a booted machine through --attach and is written down here
# so that the next person does not have to measure it again:
#
#   * Focus stays on "Weiter" across a page change, because the button is
#     in the toolbar and only the stack's child is swapped. So one space
#     bar per page walks the form - EXCEPT where the new page is invalid,
#     which makes the button insensitive and drops the focus.
#   * The user page is exactly that exception, and its tab chain is
#     twelve stops long, because each of the four password rows has a
#     "show the password" eye button and every one of them is a tab stop:
#       1 Rechnername  2 Benutzername  3 Passwort  4 eye
#       5 wiederholen  6 eye  7 Root-Passwort  8 eye
#       9 wiederholen  10 eye  11 Zurueck  12 Weiter
#     Stop 12 only exists once the page validates; before that "Weiter"
#     is insensitive and not focusable.
#   * Tabbing INTO an entry selects what is already in it, so typing
#     replaces rather than appends. That is what lets this script write
#     the hostname over the default without clearing anything first.
#   * The network page is not in here at all: PageState.should_skip()
#     skips it when the scan found nothing, and a QEMU guest has no
#     wireless adapter.
RELEASE_INSTALL_SCRIPT: tuple[str, ...] = (
    "shot:01-sprache",
    # One tab from a machine nobody has touched lands on "Weiter", and
    # the focus ring in this picture is the proof that the installer is
    # taking input at all - before anything has been changed.
    "key:tab", "wait:1", "shot:02-weiter-hat-den-fokus",
    "key:spc", "wait:6", "shot:03-datentraeger",
    # DIE PARTITIONIERUNG, und warum sie hier stehen MUSS.
    #
    # Sie kam am 11.08.2026 in PAGE_ORDER zwischen "datentraeger" und
    # "benutzer". Dieses Skript wusste nichts davon, und der erste Lauf
    # danach tippte Rechnernamen und Passwoerter in die GROESSENFELDER
    # dieser Seite, landete mit leeren Feldern auf "Benutzer" und blieb
    # dort stehen - ohne gueltigen Rechnernamen gibt es kein "Weiter".
    # Gemessen: 0,0 GiB geschrieben, und das Bild, das
    # "13-installation-beendet" heisst, zeigte "Schritt 4 von 7".
    #
    # Ein einziger Tastendruck genuegt, weil die Seite gueltig ANKOMMT:
    # app.py ruft _refresh_partitioning() bei jedem Seitenwechsel, und
    # pages.py setzt reset_layout() sobald eine Platte gewaehlt ist -
    # ESP und Wurzel, "Weiter" empfindlich.
    #
    # Damit misst dieser Lauf den VORSCHLAGSWEG. Was eine von Hand
    # gebaute Einteilung tut, misst er nicht; das tut der kopflose Lauf
    # in tests/installer/. Beides zusammen deckt die Seite ab, keines
    # allein.
    "key:spc", "wait:4", "shot:04-partitionierung",
    # DIE VERSCHLUESSELUNG, und sie ist die zweite Seite, die anders ist
    # als alle davor: sie kommt UNGUELTIG an.
    #
    # Der Haken steht (installer.gui.pages.PageState.encrypt ist True -
    # der Nutzer hat am 12.08.2026 "immer" verlangt), die Passphrase ist
    # leer, also ist "Weiter" unempfindlich und der Fokus faellt ab.
    # Genau wie auf der Benutzerseite muss deshalb getabbt statt
    # durchgedrueckt werden.
    #
    # DIE KETTE, gemessen und nicht gezaehlt: tests/installer/
    # gui_headless_child.py baut diese Seite an einem echten
    # gtk4-broadwayd und vergleicht ihre Bedienelemente mit
    # VERSCHLUESSELUNG_WIDGETS. Daraus folgen fuenf Halte auf der Seite:
    #   1 Schalter  2 Passphrase  3 Auge  4 wiederholen  5 Auge
    # und danach 6 Zurueck, 7 Weiter - Halt 7 erst, sobald beide Felder
    # gleich und lang genug sind.
    #
    # WAS PASSIERT, WENN DIESE ZAHLEN FALSCH SIND: die Passphrase landet
    # im falschen Feld, die Seite bleibt ungueltig, "Weiter" bleibt tot -
    # und der Lauf bleibt SICHTBAR hier stehen. Das ist der Unterschied
    # zum 11.08.2026: damals nahm die falsche Seite die Eingaben
    # klaglos an und der Lauf endete mit rc=0 und 0,0 GiB.
    "key:spc", "wait:4", "shot:05-verschluesselung",
    "key:tab", "wait:0.4",
    "key:tab", "wait:0.4", f"text:{RELEASE_DISK_PASSPHRASE}",
    "key:tab", "key:tab", "wait:0.4", f"text:{RELEASE_DISK_PASSPHRASE}",
    "wait:1", "shot:06-verschluesselung-ausgefuellt",
    # Halte 5, 6, 7: das letzte Auge, "Zurueck", "Weiter".
    "key:tab", "key:tab", "key:tab", "wait:1",
    "shot:07-verschluesselung-weiter-frei",
    "key:spc", "wait:4", "shot:08-benutzer-leer",
    # The six fields. The doubled tabs step over an eye button.
    "key:tab", "wait:0.4", f"text:{RELEASE_HOSTNAME}",
    "key:tab", "wait:0.4", f"text:{RELEASE_USER}",
    "key:tab", "wait:0.4", f"text:{RELEASE_PASSWORD}",
    "key:tab", "key:tab", "wait:0.4", f"text:{RELEASE_PASSWORD}",
    "key:tab", "key:tab", "wait:0.4", f"text:{RELEASE_ROOT_PASSWORD}",
    "key:tab", "key:tab", "wait:0.4", f"text:{RELEASE_ROOT_PASSWORD}",
    "wait:1", "shot:09-benutzer-ausgefuellt",
    # Stops 10, 11, 12: the last eye, "Zurueck", "Weiter". The picture is
    # taken before the space bar, so the record shows which button was
    # focused when it was pressed.
    "key:tab", "key:tab", "key:tab", "wait:1", "shot:10-weiter-ist-wieder-frei",
    "key:spc", "wait:3", "shot:11-zeitzone",
    "key:spc", "wait:3", "shot:12-zepos-optionen",
    "key:spc", "wait:3", "shot:13-zusammenfassung",
    # THE CONFIRMATION. "Installation jetzt starten?" over
    # "Dies loescht die gesamte Festplatte /dev/vda.", with Nein and Ja.
    # Measured: the dialog opens with "Nein" holding an invisible focus,
    # so ONE tab moves to "Ja" - which is photographed, with its focus
    # ring, before the space bar answers it.
    "key:spc", "wait:5", "shot:14-bestaetigung",
    "key:tab", "wait:1", "shot:15-ja-hat-den-fokus",
    "key:spc", "wait:15", "shot:16-installation-laeuft",
    # And then there is nothing to do but look. See watch().
    "watch:installation:5100",
    "wait:3", "shot:17-installation-beendet",
    # ACPI, not a kill: the target filesystem is what this whole run
    # produced and it is unmounted by a shutdown, not by a power cut.
    "power:240",
)

# DERSELBE ASSISTENT AUF EINER MASCHINE OHNE NETZWERKKARTE - und ohne
# Verschluesselung, weil der Befund genau so lautete.
#
# DER BEFUND, 17.08.2026, von echter Hardware
#     "Installation Wizard mit dem Terminal freezed wenn ich versuche
#     ohne Internet und ohne Passphrase zu installieren."
#
# WAS DIESES SKRIPT ANDERS MACHT ALS DAS DARUEBER, UND WARUM
#     Zwei Dinge, und beide sind der Befund selbst:
#
#     1. Die Maschine bekommt `-nic none` (siehe qemu_command). Kein
#        Kabel ohne Gegenstelle, keine Karte ohne Adresse - gar keine
#        Karte. Das ist der einzige Zustand, in dem sich die Frage
#        stellt, und es ist der einzige, den kein Lauf dieser Reihe je
#        gefahren hat.
#
#     2. Der Haken auf der Verschluesselungsseite wird ABGEWAEHLT.
#        Jeder andere Lauf hier verschluesselt, also war der Weg ohne
#        Passphrase durch dieses Medium bis heute ungemessen - und der
#        Nutzer ist genau ihn gegangen.
#
# DIE TABULATOREN AUF DER VERSCHLUESSELUNGSSEITE, MIT ABGEWAEHLTEM HAKEN
#     Die Seite kommt UNGUELTIG an (der Haken steht, die Passphrase ist
#     leer), also ist "Weiter" unempfindlich und der Fokus faellt ab -
#     genau wie im Skript darueber. Ein Tabulator landet auf dem
#     Schalter, die Leertaste legt ihn um.
#
#     Danach ist die Seite eine ANDERE: installer/gui/app.py's
#     _refresh_encryption() setzt die zwei Passphrasenzeilen auf
#     unempfindlich (der Kopf von _build_verschluesselung sagt, warum
#     sie nicht verschwinden), und ein unempfindliches Bedienelement ist
#     in GTK kein Tabulatorhalt. Aus den sieben Halten mit Haken werden
#     drei ohne: Schalter, Zurueck, Weiter.
#
#     GEMESSEN und nicht gezaehlt - siehe die Bilder
#     06-verschluesselung-aus und 07-weiter-frei dieses Laufs. Stimmen
#     die Zahlen nicht, bleibt der Lauf SICHTBAR auf dieser Seite
#     stehen, statt seine Eingaben still in die falschen Felder zu
#     tippen.
RELEASE_INSTALL_OHNE_NETZ_SCRIPT: tuple[str, ...] = (
    "shot:01-sprache",
    "key:tab", "wait:1", "shot:02-weiter-hat-den-fokus",
    "key:spc", "wait:6", "shot:03-datentraeger",
    "key:spc", "wait:4", "shot:04-partitionierung",
    "key:spc", "wait:4", "shot:05-verschluesselung",
    # Halt 1: der Schalter. Die Leertaste legt ihn um - eine
    # Adw.SwitchRow ist aktivierbar, und die Zeile zu aktivieren schaltet
    # den Schalter.
    "key:tab", "wait:0.6", "key:spc", "wait:1.5",
    "shot:06-verschluesselung-aus",
    # Halte 2 und 3: "Zurueck" und "Weiter". Das Bild davor zeigt, auf
    # welcher Schaltflaeche der Fokusring stand, als die Leertaste kam.
    "key:tab", "key:tab", "wait:1", "shot:07-weiter-frei",
    "key:spc", "wait:4", "shot:08-benutzer-leer",
    # Von hier an Zeichen fuer Zeichen dasselbe wie im Lauf mit Netz.
    "key:tab", "wait:0.4", f"text:{RELEASE_HOSTNAME}",
    "key:tab", "wait:0.4", f"text:{RELEASE_USER}",
    "key:tab", "wait:0.4", f"text:{RELEASE_PASSWORD}",
    "key:tab", "key:tab", "wait:0.4", f"text:{RELEASE_PASSWORD}",
    "key:tab", "key:tab", "wait:0.4", f"text:{RELEASE_ROOT_PASSWORD}",
    "key:tab", "key:tab", "wait:0.4", f"text:{RELEASE_ROOT_PASSWORD}",
    "wait:1", "shot:09-benutzer-ausgefuellt",
    "key:tab", "key:tab", "key:tab", "wait:1", "shot:10-weiter-ist-wieder-frei",
    "key:spc", "wait:3", "shot:11-zeitzone",
    "key:spc", "wait:3", "shot:12-zepos-optionen",
    "key:spc", "wait:3", "shot:13-zusammenfassung",
    "key:spc", "wait:5", "shot:14-bestaetigung",
    "key:tab", "wait:1", "shot:15-ja-hat-den-fokus",
    # UND HIER ENTSCHEIDET SICH ALLES.
    #
    # Vor dem 17.08.2026 stand ab dieser Stelle ein stehendes Bild, und
    # zwar fuer immer. Jetzt muss innerhalb weniger Sekunden ein Fenster
    # mit einem Satz darin da sein - installer/core/preflight.py's
    # Ablehnung, durchgereicht als InstallationRefused.
    #
    # Zwanzig Sekunden, nicht fuenfzehn: die Messung selbst darf bis zu
    # fuenf Sekunden dauern (preflight.PROBE_TIMEOUT), und ohne Netz
    # scheitert sie in Millisekunden - der Rest ist Luft fuer eine
    # langsame Maschine.
    "key:spc", "wait:20", "shot:16-was-der-assistent-sagt",
    # Und dann hinsehen. Die Grenze ist absichtlich klein: was hier
    # laenger als zehn Minuten braucht, ist genau der Fehler, den dieser
    # Lauf sucht, und dann soll er dabei fotografiert werden statt eine
    # Stunde lang zu warten.
    "watch:ohne-netz:600",
    "wait:3", "shot:17-stand-am-ende",
    # ACPI und kein Abschuss, wie im Lauf mit Netz: sollte doch etwas
    # auf die Platte geschrieben worden sein, will man es hinterher
    # lesen koennen.
    "power:120",
)

# Und die andere Seite davon: die Anmeldung an dem, was da installiert
# wurde, und die Sitzung dahinter.
#
# WAS SICH GEAENDERT HAT, UND WARUM DAS SKRIPT SO KURZ WURDE
#     Hier stand ein Login an einem getty, gefolgt von `zepos-generate
#     --all` und `.local/bin/start-hyprland`, von Hand getippt. Das war
#     kein Test, das war die Reparatur: das installierte System richtete
#     keinen Sitzungsstart ein, blieb bei "Reached target Graphical
#     Interface" stehen, und die zwei Befehle haben das umgangen statt es
#     zu messen.
#
#     Jetzt gibt es greetd. Der Bildschirm nach dem Booten ist eine
#     GTK4-Maske, und die drei Tastendruecke unten sind alles, was ein
#     Mensch davor auch tun wuerde.
#
# WARUM DIE EINGABETASTE REICHT UND NICHT GETABBT WIRD
#     Nachgelesen an ReGreet 0.5.0: src/gui/component.rs ruft
#     root.set_default_widget(login_button), und der Knopf traegt
#     set_receives_default. Die Eingabetaste loest ihn also aus, egal wo
#     der Fokus gerade steht. Danach uebernimmt secret_entry den Fokus von
#     selbst (grab_focus, sobald der Eingabemodus beginnt) und meldet die
#     Eingabetaste ueber connect_activate an greetd weiter.
#
#     Die beiden Auswahlfelder darueber brauchen niemanden: es gibt genau
#     einen Benutzer und genau eine Sitzung. Die zweite Haelfte davon ist
#     eine Entscheidung des Compositor-Pakets - zepos-hyprland entfernt
#     Hyprlands eigene hyprland.desktop und hyprland-uwsm.desktop, weil
#     ReGreet die Sitzungen in einer HashMap haelt und die Vorauswahl
#     damit bei jedem Start eine andere waere.
#
# UNGEMESSEN, und es sagt das lieber, als es zu verschweigen: die
# Wartezeiten unten sind Schaetzungen. Die erste Anmeldung erzeugt die
# ganze ZepOS-Konfiguration, bevor der Compositor startet (zepos-session
# ruft zepos-generate --all), und wie lange das auf dieser Maschine
# dauert, hat noch niemand von hier aus gemessen. Wer eine Installation
# durchbekommt, sollte damit rechnen, sie zu korrigieren.
#
# DIE ABNAHME AB SCHRITT 8, UND WARUM SIE HIER STEHT UND NICHT IN pytest
#     Am 11.08.2026 war die ganze Suite gruen, und dann hat sich ein
#     Mensch vor die fertige Installation gesetzt: "die nwg dock unten
#     geht nicht mehr dateien und datei manager ist auch nicht vorhanden
#     und screenshot tool auch nicht es fehlt gefuehlt alles".
#
#     tests/src/test_usable_desktop.py beantwortet seither die Haelfte
#     davon ohne Maschine: dass SUPER+E nautilus ruft, dass nautilus
#     ausgeliefert wird, dass das Dock eine angeheftete Liste traegt. Was
#     es NICHT beantworten kann, ist die Frage, die der Nutzer wirklich
#     gestellt hat - geht ein Fenster auf? Dafuer braucht es eine
#     Sitzung, und die gibt es nur hier.
#
#     Sechs Schritte, jeder eine der Beschwerden, und jeder mit einem
#     Bild. Ein Tastendruck ohne Aufnahme ist ein Tastendruck, dessen
#     Ergebnis niemand sieht.
#
# WAS EIN MENSCH AUF DEN BILDERN SEHEN MUSS
#     01  die Passphrasenabfrage der Initramfs. Seit dem 13.08.2026 ein
#         FENSTER - Petrolverlauf, Wortmarke, ein gerundetes Feld - und
#         nicht mehr die englische Textzeile. Sie ist die ERSTE
#         Oberflaeche nach dem Startmenue, und wenn sie fehlt, ist die
#         Platte nicht verschluesselt; das Bild ist der einzige Beleg
#         dafuer, den dieser Lauf hat.
#     02  dasselbe Fenster mit fuenfzehn Punkten im Feld, einem je
#         Zeichen der Passphrase. Das Bild, das "keine Taste kommt an"
#         von "die Passphrase wird abgewiesen" trennt.
#     03  ein Schirm, auf dem es weitergegangen ist. Steht hier noch
#         dieselbe Abfrage, obwohl auf 02 fuenfzehn Punkte standen, dann
#         kommen die Zeichen an und werden falsch uebersetzt - die
#         Tastaturbelegung der Abfrage (siehe installer/core/crypt.py,
#         keyboard_note(), und installer/core/translate.py,
#         PLYMOUTH_COMMAND).
#     11  unten eine Reihe Symbole, auf einem Schreibtisch ohne ein
#         einziges Fenster. Genau das fehlte.
#     12  ein Dateimanagerfenster.
#     13  das Auswahlfenster des Anwendungsstarters.
#     14  slurp: der Schirm wird abgedunkelt und der Zeiger zieht ein
#         Rechteck auf. Ein Ziehen kann diese Steuerung nicht, also ist
#         die Abdunklung die Antwort - sie beweist, dass die Kette
#         grim/slurp/satty startet.
#     16  `zepos-doctor` ohne Befund, oder mit einem, den man lesen kann.
#         Seit dem 11.08.2026 meldet er auch jede Taste, deren Programm
#         auf DIESER Maschine fehlt.
#     17  das Widget-Verzeichnis. Es darf keine .backup.*-Datei
#         enthalten: auf einer frischen Installation gibt es nichts, was
#         zu sichern waere, und was dort lag, war die Kopie einer Datei,
#         die drei Sekunden zuvor derselbe Login geschrieben hatte.
#
# UNGEMESSEN, und es sagt das lieber, als es zu verschweigen: die
# Wartezeiten sind Schaetzungen. Die erste Anmeldung erzeugt die ganze
# ZepOS-Konfiguration, bevor der Compositor startet (zepos-session ruft
# zepos-generate --all), und wie lange das auf dieser Maschine dauert,
# hat noch niemand von hier aus gemessen. Wer eine Installation
# durchbekommt, sollte damit rechnen, sie zu korrigieren.
RELEASE_INSTALLED_SCRIPT: tuple[str, ...] = (
    # DIE PLATTENPASSPHRASE, und sie kommt VOR allem anderen.
    #
    # Der Installationslauf verschluesselt seit dem 12.08.2026, also
    # bootet diese Maschine nicht mehr durch. Was ein Mensch hier sieht:
    # das gethemte GRUB-Menue wie bisher (die ESP liegt auf /boot, ist
    # FAT32 und bleibt lesbar - deshalb braucht GRUB kein
    # GRUB_ENABLE_CRYPTODISK), dann den Kernel, und dann die Abfrage.
    #
    # BIS ZUM 13.08.2026 WAR DIESE ABFRAGE EINE TEXTZEILE, und
    # iso/out/run-release-installed/screen-0060s.png aus dem Lauf davor
    # zeigt sie - zwei Zeilen weisse Schrift auf Schwarz, auf Englisch,
    # auf einem sonst durchgehend deutschen System:
    #
    #     A password is required to access the root volume:
    #     Enter passphrase for /dev/vda2:
    #
    # SEITHER IST ES EIN FENSTER: Petrolverlauf, Wortmarke, ein
    # gerundetes Feld, das je getipptem Zeichen einen Punkt zeigt, und
    # darunter der Satz zur Tastaturbelegung. Das ist derselbe
    # `encrypt`-Haken von mkinitcpio - er fragt von sich aus, ob
    # plymouthd laeuft, und geht dann ueber `plymouth ask-for-password`.
    # Wo das eingestellt wird: installer/core/translate.py,
    # PLYMOUTH_COMMAND.
    #
    # DAS BILD 01-passphrase-gefragt IST DIE ABNAHME DAVON. Steht darauf
    # wieder Text, dann ist plymouthd nicht hochgekommen und der Haken
    # ist in seinen else-Zweig gefallen - die Maschine startet dann
    # immer noch, und genau das ist der Sinn dieses Rueckwegs, aber die
    # Arbeit ist nicht fertig.
    #
    # DIE WARTEZEIT DAVOR ist die Summe aus GRUB (Vorgabe fuenf Sekunden,
    # archinstall setzt GRUB_TIMEOUT nicht um), OVMFs POST (drei bis
    # vier) und dem Start des Kernels. 25 Sekunden sind reichlich; ein
    # Bild davor und eines danach zeigen, ob die Abfrage ueberhaupt kam.
    #
    # DIE ZEHN SEKUNDEN DANACH sind gemessen und nicht geschaetzt: die
    # Argon2id-Ableitung mit archinstalls DEFAULT_ITER_TIME von 10000 ms
    # brauchte auf einem Core Ultra 7 255U 9,98 / 10,39 / 10,82 Sekunden
    # (installer/core/crypt.py, Modulkopf). Unter QEMU ohne
    # Hardwarebeschleunigung darf es laenger dauern, deshalb 30.
    #
    # UND DAS BILD WAEHREND DES TIPPENS IST DIE ZWEITE HAELFTE DER
    # ABNAHME, nicht Schmuck. Am 13.08.2026 blieb die Maschine an dieser
    # Abfrage stehen, und aus "01 zeigt ein Fenster, 02 zeigt dasselbe
    # Fenster" liessen sich zwei voellig verschiedene Ursachen lesen:
    # entweder kommt keine Taste an, oder die Passphrase wird
    # abgewiesen. Entschieden hat es erst ein Bild, das WAEHREND einer
    # Eingabe entstand - elf Punkte fuer elf getippte Zeichen. Das war
    # damals ein Zufallsfund an der falschen Stelle (dem Benutzer-
    # passwort); jetzt entsteht es an der richtigen und immer.
    #
    # Fuenfzehn Punkte muessen darauf stehen, so viele wie
    # RELEASE_DISK_PASSPHRASE Zeichen hat. Keiner heisst, dass plymouth
    # keine Tastatur sieht; weniger heisst, dass Tasten verlorengehen;
    # fuenfzehn und trotzdem eine geschlossene Platte heisst, dass die
    # Zeichen ankommen und FALSCH UEBERSETZT werden - der Fall vom
    # 13.08.2026, den installer/core/translate.py mit /etc/vconsole.conf
    # in der Initramfs abstellt.
    "wait:25", "shot:01-passphrase-gefragt",
    f"text:{RELEASE_DISK_PASSPHRASE}", "wait:1",
    "shot:02-passphrase-getippt",
    "key:ret", "wait:30",
    "shot:03-nach-dem-entsperren",
    "shot:04-anmeldung",
    "key:ret", "wait:2", "shot:05-passwort-gefragt",
    f"text:{RELEASE_PASSWORD}", "wait:1", "shot:06-passwort-getippt",
    "key:ret", "wait:30", "shot:07-sitzung-nach-30s",
    "wait:60", "shot:08-sitzung-nach-90s",
    "wait:60", "shot:09-sitzung-nach-150s",
    "wait:90", "shot:10-sitzung-nach-240s",

    # 1. Das Dock, bevor irgendetwas offen ist.
    "shot:11-dock-ohne-fenster",

    # 2. Der Dateimanager. `meta_l` ist die Position, die Hyprland
    #    $mainMod nennt.
    "key:meta_l-e", "wait:25", "shot:12-super-e-dateimanager",

    # 3. Der Anwendungsstarter, und Escape wieder heraus - was danach
    #    kommt, soll auf einem Schreibtisch getippt werden und nicht in
    #    ein Suchfeld.
    "key:meta_l-spc", "wait:10", "shot:13-super-spc-anwendungsstarter",
    "key:esc", "wait:3",

    # 4. Das Bildschirmfoto.
    "key:meta_l-s", "wait:8", "shot:14-super-s-bildschirmfoto",
    "key:esc", "wait:3",

    # 5. Ein Terminal, und darin die Selbstauskunft.
    "key:meta_l-q", "wait:20", "shot:15-super-q-terminal",
    "text:zepos-doctor", "key:ret", "wait:25",
    "shot:16-abnahme-zepos-doctor",

    # 6. Und der Nebenbefund vom 11.08.2026, an der Stelle, an der er
    #    aufgefallen ist. Ohne ~ getippt: die Zeichentabelle dieser
    #    Steuerung hat keine Tilde, und `ls` steht ohnehin im
    #    Heimatverzeichnis.
    "text:ls -a .config/ags/widget/", "key:ret", "wait:6",
    "shot:17-abnahme-widget-verzeichnis",

    # ACPI und kein Abwuergen: dieselbe Begruendung wie beim
    # Installationslauf - die Platte ist das, was gemessen wird.
    "power:240",
)

DRIVE_SCRIPTS = {
    "release": RELEASE_SCRIPT,
    "release-install": RELEASE_INSTALL_SCRIPT,
    "release-install-ohne-netz": RELEASE_INSTALL_OHNE_NETZ_SCRIPT,
    "release-installed": RELEASE_INSTALLED_SCRIPT,
    # Nothing is pressed at a boot menu. Pressing anything would answer
    # it, and what is being measured is the screen it puts up when
    # nobody does.
    "boot-menu": (),
}

# When to photograph a machine that has been left to itself, per
# scenario. The release run watches a boot it knows nothing about; the
# other two have a specific moment they are waiting for and are driven
# from there.
RELEASE_SETTLE = {
    # The first three are new and they are the boot menu: grub.cfg's
    # timeout is ten seconds and OVMF takes three or four to POST, so 6
    # and 10 are inside the window on this machine and 14 is usually
    # past it. They are here as well as in the boot-menu scenario
    # because the release run is the one anybody actually runs, and a
    # medium whose identity fell off should be visible in its pictures
    # without a second run being remembered.
    "release": [6, 10, 14, 20, 40, 60, 90, 120, 180],
    "release-install": [30, 60],
    # Dieselben zwei Marken wie beim Lauf mit Netz. Ohne Netzwerkkarte
    # bootet das Medium eher schneller - es gibt keine Schnittstelle, auf
    # die etwas warten koennte -, also deckt derselbe Zeitplan denselben
    # Moment ab.
    "release-install-ohne-netz": [30, 60],
    # Die ersten drei sind das Startmenue DER INSTALLATION, und seit
    # installer/core/translate.py GRUB statt systemd-boot einrichtet ist
    # das ein gethemtes Menue statt einer Textliste. Es ist die einzige
    # Stelle, an der man sieht, ob das Thema die Installation ueberlebt
    # hat: GRUB antwortet auf ein Thema, das es nicht lesen kann, mit dem
    # Textmodus und ohne Fehler.
    #
    # archinstall setzt GRUB_TIMEOUT nicht um, also gilt Archs Vorgabe
    # von fuenf Sekunden; OVMF braucht drei bis vier zum POST. 5, 7 und 9
    # liegen um das Fenster herum.
    #
    # Alles ab 20 zeigt seit dem 12.08.2026 die Passphrasenabfrage der
    # Initramfs und nicht mehr eine startende Sitzung: eine
    # verschluesselte Maschine, die sich selbst ueberlassen bleibt,
    # bootet nicht fertig. Das ist kein Fehler des Zeitplans, sondern
    # der Sinn der Verschluesselung - was danach kommt, treibt
    # RELEASE_INSTALLED_SCRIPT.
    "release-installed": [5, 7, 9, 20, 40, 60, 90],
}

# And the whole of the boot-menu scenario, which is a schedule and
# nothing else. Per firmware, because the two POST at completely
# different speeds: OVMF spends three or four seconds before GRUB is
# reached and SeaBIOS is at the syslinux menu inside two.
#
# Deliberately more marks than are needed. The frames on either side of
# the menu cost a screendump each and grade_boot_menu() only needs ONE of
# them to be the menu - a schedule with two marks would turn a slow POST
# on somebody else's machine into a failure about the theme.
BOOT_MENU_SETTLE = {
    "uefi": [4, 5, 6, 7, 9, 11, 13],
    "bios": [2, 3, 4, 5, 6, 8, 10],
}

# After this many seconds a frame is no longer a boot menu, whatever it
# looks like. Both loaders count ten seconds down and then boot; twenty
# is that plus the slowest POST measured on this machine. The number
# exists because the INSTALLER is drawn in the same palette as the menu -
# it is one brand - so a frame of its first page passes every test
# grade_boot_menu() makes, and without a cut-off a release run whose menu
# was never photographed would report a themed one.
BOOT_MENU_WINDOW = 20


def _run_text(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True)


def _remove_unpacked(path: Path) -> None:
    """rm -rf, for a tree unsquashfs made.

    unsquashfs reproduces the image's modes, and an image has directories
    at dr-xr-xr-x in it - /etc among them. Nothing can be unlinked
    through a directory with no write bit, not even by the user who owns
    it, so a plain rmtree fails with EACCES on the second run and on
    every run after that.
    """
    if not path.exists():
        return
    for entry in sorted(path.rglob("*"), reverse=True):
        if entry.is_dir() and not entry.is_symlink():
            entry.chmod(entry.stat().st_mode | 0o700)
    path.chmod(path.stat().st_mode | 0o700)
    shutil.rmtree(path)


def inspect_release_iso(iso: Path, into: Path) -> tuple[list[str], list[str]]:
    """Read the built image and check what is NOT in it.

    Returns (problems, notes). A non-empty problems list means the image
    must not be handed to anybody, and the caller does not boot it.

    WHY THIS READS THE ISO AND NOT THE PROFILE
        tests/iso/test_release_profile.py already checks the profile, and
        that check is cheap in both senses: it runs in milliseconds and
        it can only ever see what the profile authors wrote. The image is
        made of 335 packages on top of that. systemd's own scriptlet
        enables getty@tty1, a package could ship an autologin drop-in of
        its own, and the assembly step could have gone wrong in a way no
        test of its inputs would notice.

        So this opens the actual artefact: the ISO9660 filesystem for the
        boot loader configurations, and the squashfs inside it - through
        `unsquashfs -l`, which reads the metadata and not the gigabyte -
        for everything else.
    """
    problems: list[str] = []
    notes: list[str] = []
    # From scratch, every time. Both the extracted squashfs and the
    # unpacked /etc below are named after the directory and not after the
    # image, so a kept copy would let a run check a NEW ISO against an
    # OLD root - and report that a harness which is back is gone.
    _remove_unpacked(into)
    into.mkdir(parents=True)

    listing = _run_text(["bsdtar", "tf", str(iso)])
    if listing.returncode != 0:
        return [f"the ISO cannot be read: {listing.stderr.strip()}"], notes
    entries = listing.stdout.splitlines()

    # ---- the kernel command line, as it is on the medium ----
    loaders = [name for name in entries
               if name.endswith(("syslinux-linux.cfg", "grub.cfg", "loopback.cfg"))]
    if not loaders:
        problems.append("the ISO carries no boot loader configuration at all")
    for name in loaders:
        content = _run_text(["bsdtar", "xOf", str(iso), name])
        # The lines that give the kernel its arguments, and not the
        # comments around them. Both configurations explain at length why
        # they carry no serial console, and a check that could not tell an
        # explanation from a command line would force the explanation out.
        arguments = [line.strip() for line in content.stdout.splitlines()
                     if not line.lstrip().startswith("#")
                     and ("vmlinuz-linux" in line or line.strip().startswith("APPEND"))]
        for line in arguments:
            if "console=" in line:
                problems.append(f"{name} puts a console on the kernel command line: {line}")
        notes.append(f"loader {name}: " + " ".join(arguments))

    # ---- the root filesystem ----
    squashfs = next((name for name in entries if name.endswith("airootfs.sfs")), None)
    if squashfs is None:
        problems.append("the ISO carries no airootfs.sfs")
        return problems, notes

    image = into / "airootfs.sfs"
    with open(image, "wb") as handle:
        extracted = subprocess.run(["bsdtar", "xOf", str(iso), squashfs],
                                   stdout=handle, stderr=subprocess.PIPE, text=True)
    if extracted.returncode != 0:
        return problems + [f"airootfs.sfs could not be extracted: {extracted.stderr}"], notes

    contents = _run_text(["unsquashfs", "-l", str(image)])
    if contents.returncode != 0:
        return problems + [f"the squashfs cannot be listed: {contents.stderr.strip()}"], notes
    inside = {line[len("squashfs-root/"):]
              for line in contents.stdout.splitlines()
              if line.startswith("squashfs-root/")}
    notes.append(f"{len(inside)} paths in the root filesystem")

    for path, what in HARNESS_PATHS:
        if path in inside:
            problems.append(f"/{path} is in the image - {what}")

    if "usr/bin/zepos-install" not in inside:
        problems.append("/usr/bin/zepos-install is NOT in the image; "
                        "there is nothing for it to boot into")

    # ---- the two files that decide who may log in ----
    wanted = ["etc/shadow", "etc/systemd/system", "etc/passwd"]
    unpacked = into / "root"
    opened = _run_text(["unsquashfs", "-q", "-n", "-no-xattrs",
                        "-d", str(unpacked), str(image), *wanted])
    if opened.returncode != 0:
        problems.append(f"could not unpack {wanted} from the image: {opened.stderr}")
        return problems, notes

    shadow = unpacked / "etc/shadow"
    if not shadow.is_file():
        problems.append("the image has no /etc/shadow at all")
    else:
        for line in shadow.read_text(encoding="utf-8", errors="replace").splitlines():
            account, _, rest = line.partition(":")
            secret = rest.split(":")[0]
            if secret in ("*",) or secret.startswith("!"):
                continue
            problems.append(
                f"the account {account!r} can be logged into: password field "
                f"{secret!r}" if secret else
                f"the account {account!r} has an EMPTY password")

    autologins = [str(path.relative_to(unpacked))
                  for path in (unpacked / "etc/systemd").rglob("*")
                  if path.is_file()
                  and "--autologin" in path.read_text(encoding="utf-8", errors="replace")]
    for found in autologins:
        problems.append(f"/{found} logs somebody in without asking")

    # is_symlink() and not exists(): the enable symlink points at an
    # absolute path INSIDE the image, and Path.exists() resolves it
    # against the host, where /etc/systemd/system/zepos-install.service
    # is not a file anybody has. Measured, as "nothing in the image
    # starts the installer" against an image that starts it.
    installer_unit = unpacked / "etc/systemd/system/multi-user.target.wants/zepos-install.service"
    if not (installer_unit.is_symlink() or installer_unit.exists()):
        problems.append("nothing in the image starts the installer at boot")
    else:
        notes.append("the installer service is enabled in the image")

    # Whether a login prompt would come up on the same screen. Not a
    # problem in itself - the accounts are all locked, checked above - but
    # two programs on tty1 is an unreadable screen, and it is the one
    # thing about this image that a systemd package update could change
    # underneath it.
    getty = "usr/lib/systemd/system/getty.target.wants/getty@tty1.service"
    masked = (unpacked / "etc/systemd/system/getty@tty1.service")
    if getty in inside:
        notes.append("getty@tty1 is enabled by the systemd package"
                     + (" and masked by the profile" if masked.is_symlink()
                        else " and NOT masked - see the kernel command line"))

    return problems, notes


# --------------------------------------------------------------------
# The boot menu, graded from the framebuffer
# --------------------------------------------------------------------
# WHY A MEASUREMENT AND NOT A LOOK
#     A GRUB theme that cannot be loaded is not an error. If the theme
#     file, the PF2 font or the background PNG is missing, unreadable, or
#     at a path the configuration does not name, GRUB writes nothing
#     anywhere and puts up its plain text menu instead - the same menu
#     this medium had before it had an identity at all. The BIOS path
#     fails the same way: a splash.png syslinux cannot decode leaves the
#     colour attributes over a black screen.
#
#     So "the theme is in the image" is not something a build can be
#     trusted to report, and "it looked right when I ran it" is not
#     something the next person inherits. What follows measures the one
#     artefact that cannot lie about it: the frame the display device
#     held while the menu was on the screen.
#
# WHAT SEPARATES A THEMED FRAME FROM A FALLBACK, IN NUMBERS
#     Measured on this machine, on real frames - the themed ones from the
#     medium built out of iso/profile-release/, the fallback one from the
#     release ISO built before it, which had `terminal_output console`:
#
#                             ground   yellow   black
#       themed, GRUB/UEFI      0.923   0.0427   0.000
#       themed, syslinux/BIOS  0.965   0.0170   0.000
#       fallback, GRUB text    0.000   0.0000   0.967
#
#     Three measures rather than one, because there are three different
#     ways for this to go wrong and each of them moves a different
#     number:
#
#       ground  the fraction of the frame that is the brand petrol or the
#               gradient under it. It is what the BACKGROUND IMAGE
#               produces, and it is the one that collapses when the PNG
#               is missing while the colours still work - a syslinux menu
#               with no splash still draws its yellow bar.
#       yellow  the fraction that is the brand yellow, which on both
#               menus is the block behind the SELECTED ENTRY. It is what
#               collapses when the picture loads and nothing is themed
#               over it.
#       black   how much of the frame is near-black. A text console is
#               almost all of it; neither themed menu has any.
#
#     All three have to hold, and the thresholds sit far from both sides:
#     the tightest is the yellow on the BIOS menu at 0.0170 against a
#     0.0060 floor.
BRAND_GROUND = ((0x0D, 0x3D, 0x47),   # the petrol
                (0x0B, 0x34, 0x3C),   # the middle of the gradient
                (0x09, 0x2A, 0x31))   # and its dark end
BRAND_YELLOW = (0xFF, 0xCB, 0x00)
BRAND_CYAN = (0x00, 0x96, 0xC0)

# Euclidean, in sRGB, per channel triple. Loose enough for what a scaler
# does to a flat colour and for the dithering an emulated framebuffer
# adds; far tighter than the distance between any brand colour and any
# colour a text console produces.
GROUND_TOLERANCE = 26
ACCENT_TOLERANCE = 40
NEAR_BLACK = 24

BOOT_MENU_MIN_GROUND = 0.60
BOOT_MENU_MIN_YELLOW = 0.006
BOOT_MENU_MAX_BLACK = 0.15

# Every third pixel in both directions - a ninth of the frame. The
# smallest thing being counted is a menu bar several hundred pixels wide
# and sixteen tall, so a ninth of it is still thousands of samples, and
# the whole of a 1280x800 frame is then a little over half a second of
# pure Python instead of five.
FRAME_SAMPLE_STEP = 3


def read_png(path: Path) -> tuple[int, int, int, bytes]:
    """Decode a PNG to (width, height, channels, rows) with the standard
    library alone.

    Pillow is not a dependency of this repository and must not become one
    so that a harness can count pixels. QEMU's screendump writes 8-bit
    non-interlaced truecolour and nothing else, so that is the only shape
    handled - anything else raises rather than guessing, because a silent
    wrong answer here would grade a boot menu nobody looked at.

    tests/src/test_brand.py has a smaller version of this that reads one
    pixel out of the shipped wallpaper. This one has to undo the filter
    on every row, which is the whole of the extra length.
    """
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    depth, colour_type, _compression, _filter, interlace = data[24:29]
    if (depth, interlace) != (8, 0):
        raise ValueError(f"{path} is {depth}-bit, interlace {interlace}; "
                         f"this reader handles 8-bit non-interlaced only")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(colour_type)
    if channels is None or channels < 3:
        raise ValueError(f"{path} has colour type {colour_type}, not truecolour")

    stream, offset = bytearray(), 8
    while offset < len(data):
        length, kind = struct.unpack(">I4s", data[offset:offset + 8])
        if kind == b"IDAT":
            stream += data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"IEND":
            break
    raw = zlib.decompress(bytes(stream))

    stride = width * channels
    out = bytearray(height * stride)
    previous = bytearray(stride)
    position = 0
    for y in range(height):
        kind = raw[position]
        position += 1
        line = bytearray(raw[position:position + stride])
        position += stride
        if kind == 1:                                   # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif kind == 2:                                 # Up
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif kind == 3:                                 # Average
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif kind == 4:                                 # Paeth
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                up = previous[i]
                corner = previous[i - channels] if i >= channels else 0
                estimate = left + up - corner
                da, db, dc = (abs(estimate - left), abs(estimate - up),
                              abs(estimate - corner))
                best = left if (da <= db and da <= dc) else (up if db <= dc else corner)
                line[i] = (line[i] + best) & 0xFF
        elif kind != 0:
            raise ValueError(f"{path} row {y} uses PNG filter {kind}")
        out[y * stride:(y + 1) * stride] = line
        previous = line
    return width, height, channels, bytes(out)


def _within(pixel, reference, tolerance: int) -> bool:
    dr = pixel[0] - reference[0]
    dg = pixel[1] - reference[1]
    db = pixel[2] - reference[2]
    return dr * dr + dg * dg + db * db <= tolerance * tolerance


def measure_frame(path: Path, step: int = FRAME_SAMPLE_STEP) -> dict:
    """How much of one framebuffer dump is the ZeptronIT palette.

    Returns fractions of the sampled pixels, not counts, so that the
    numbers mean the same thing whatever mode the firmware picked - the
    UEFI menu comes up at 1280x800 on OVMF and the BIOS one is pinned to
    800x600, and a threshold in pixels would be two thresholds.
    """
    width, height, channels, pixels = read_png(path)
    stride = width * channels
    sampled = ground = yellow = cyan = black = 0
    for y in range(0, height, step):
        row = y * stride
        for x in range(0, width, step):
            i = row + x * channels
            pixel = (pixels[i], pixels[i + 1], pixels[i + 2])
            sampled += 1
            if any(_within(pixel, g, GROUND_TOLERANCE) for g in BRAND_GROUND):
                ground += 1
            elif _within(pixel, BRAND_YELLOW, ACCENT_TOLERANCE):
                yellow += 1
            elif _within(pixel, BRAND_CYAN, ACCENT_TOLERANCE):
                cyan += 1
            if max(pixel) <= NEAR_BLACK:
                black += 1
    return {
        "frame": path.name,
        "size": f"{width}x{height}",
        "ground": ground / sampled,
        "yellow": yellow / sampled,
        "cyan": cyan / sampled,
        "black": black / sampled,
    }


def is_themed(measured: dict) -> bool:
    """Whether one frame is the branded menu rather than the fallback."""
    return (measured["ground"] >= BOOT_MENU_MIN_GROUND
            and measured["yellow"] >= BOOT_MENU_MIN_YELLOW
            and measured["black"] <= BOOT_MENU_MAX_BLACK)


def grade_boot_menu(frames: list[Path]) -> tuple[bool, list[str]]:
    """Look at every frame of a boot and say whether one of them was the
    themed menu.

    ONE of them, and not all of them, because the frames either side of
    the menu are legitimately something else: firmware output before it,
    a kernel scrolling over it afterwards. What is being asked is whether
    the menu was ever on the screen with its identity on it, and the
    answer is a frame that can be looked at next to the numbers.
    """
    report: list[str] = []
    themed = False
    for frame in frames:
        try:
            measured = measure_frame(frame)
        except (ValueError, OSError) as unreadable:
            report.append(f"  {frame.name}: not measurable ({unreadable})")
            continue
        good = is_themed(measured)
        themed = themed or good
        report.append(
            f"  {measured['frame']:<24} {measured['size']:>9}  "
            f"petrol {measured['ground']:.3f}  yellow {measured['yellow']:.4f}  "
            f"cyan {measured['cyan']:.4f}  black {measured['black']:.3f}  "
            f"{'THEMED' if good else '-'}")
    if not frames:
        # NICHT dieselbe Meldung wie "gemessen und nichts gefunden", und
        # der Unterschied ist der, den dieses Modul sonst ueberall macht:
        # eine Pruefung, die nichts gelesen hat, darf nicht aussehen wie
        # eine, die etwas gefunden hat.
        #
        # Gemessen an einem release-install-Lauf: dessen Zeitplan
        # fotografiert bei 30 und 60 Sekunden, beide weit hinter dem
        # Menuefenster, also war die Liste leer - und darunter stand
        # trotzdem "That is what a GRUB theme ... that could not be
        # loaded looks like", ueber einem Medium, dessen Menue in diesem
        # Lauf niemand angesehen hatte.
        report.append(
            f"  no frame of this run falls inside the first "
            f"{BOOT_MENU_WINDOW} seconds, so the boot menu was not looked "
            f"at here. `--scenario boot-menu` is the run that looks at it.")
        return False, report
    if not themed:
        report.append(
            f"  no frame reached petrol >= {BOOT_MENU_MIN_GROUND}, "
            f"yellow >= {BOOT_MENU_MIN_YELLOW} and black <= {BOOT_MENU_MAX_BLACK}.")
        report.append(
            "  That is what a GRUB theme or a syslinux splash that could not "
            "be loaded looks like: the menu still works and has lost the "
            "brand, and neither loader says so.")
    return themed, report


# How the release-install run knows an installation is still running, and
# how it knows it has stopped. Both come off the same signal, and there is
# nothing else on this image to have them from - see watch().
#
# 17 seconds rather than a round number, and that is the whole reason for
# it: Gtk.ProgressBar.pulse() moves the block by pulse-step (0.1 by
# default) per call and bounces, so it returns to the same place every 20
# calls - and installer/gui/app.py::_run_installation calls it on a 250 ms
# timeout, which makes the animation exactly five seconds long. A sampling
# interval that is a multiple of five would photograph the same phase
# every time and report a working installation as a frozen screen. 17 is
# coprime with it.
WATCH_INTERVAL = 17.0
WATCH_STILL = 5

# Before every framebuffer dump. MEASURED, and it cost an hour: a
# screendump taken in the same millisecond as the send-key before it
# shows the screen as it was BEFORE the key - the guest has not painted
# yet - and a series of such pictures is a series that is one step behind
# itself, which reads as a form filling itself in in the wrong order.
SHOT_SETTLE = 0.6


def watch(
    qmp: Qmp,
    run: Path,
    *,
    label: str,
    limit: float,
    interval: float = WATCH_INTERVAL,
    still: int = WATCH_STILL,
    alive: Callable[[], bool] | None = None,
) -> tuple[list[str], Path | None]:
    """Photograph the screen until it stops moving, and say when it did.

    THE PROBLEM THIS SOLVES
        An installation takes half an hour and this image tells nobody
        anything: no serial line, no collector, no exit code until the
        machine is switched off. "Is it working or has it hung" has to be
        answered from the framebuffer alone.

    THE SIGNAL
        installer/gui/app.py::_build_progress_page puts a Gtk.ProgressBar
        on the screen for the whole run and _on_tick() pulses it every
        250 ms off the GTK main loop, while the installation itself runs
        on a worker thread. So a moving pulse means the main loop is
        alive; two consecutive frames that are byte-identical mean it is
        not pulsing, which happens in exactly one place -
        _on_installation_finished() removes the tick source, sets the
        fraction to 1.0 and puts a dialog up.

        That makes "the screen stopped changing" the completion signal
        and "the screen keeps changing" the liveness one, and neither is
        a guess about pixels: both are properties of code in this
        repository. What it CANNOT tell apart is a finished installation
        from a frozen main loop - both are a still picture - which is why
        the frame is kept and looked at rather than graded here.

        Note that the log view is NOT the signal, although it is on the
        same page: nothing scrolls it, so it stops changing once the
        first screenful of archinstall's output has filled it, long
        before the installation is over.

    Returns (timeline, last_frame). Every sample is kept on disk - the
    series IS the record of the run - and the timeline says, per sample,
    how long in, how large the frame was and whether it differed from the
    one before it.
    """
    timeline: list[str] = []
    started = time.monotonic()
    previous = ""
    unchanged = 0
    index = 0
    frame: Path | None = None

    while time.monotonic() - started < limit:
        time.sleep(interval)
        if alive is not None and not alive():
            timeline.append(f"{time.monotonic() - started:7.0f}s  the machine is gone")
            break
        index += 1
        frame = qmp.screenshot(run / f"{label}-{index:03d}")
        if frame is None:
            timeline.append(
                f"{time.monotonic() - started:7.0f}s  no answer to screendump")
            break
        digest = hashlib.sha256(frame.read_bytes()).hexdigest()[:12]
        moved = digest != previous
        unchanged = 0 if moved else unchanged + 1
        previous = digest
        line = (f"{time.monotonic() - started:7.0f}s  {frame.name}  "
                f"{frame.stat().st_size:7d} bytes  {digest}  "
                f"{'moving' if moved else f'still x{unchanged}'}")
        timeline.append(line)
        print("    " + line)
        if unchanged >= still:
            timeline.append(
                f"{time.monotonic() - started:7.0f}s  the screen has been "
                f"identical for {still * interval:.0f}s - nothing is pulsing "
                f"any more")
            break
    else:
        timeline.append(f"{limit:7.0f}s  the watch ran out of time")
    return timeline, frame


def drive(
    qmp: Qmp,
    steps,
    run: Path,
    shots: list[Path],
    *,
    layout: str = "us",
    alive: Callable[[], bool] | None = None,
    prefix: str = "key",
) -> list[str]:
    """Press keys and take pictures, in the order asked for.

    Six kinds of step:

        wait:<seconds>       let the guest get on with it
        shot:<label>         a framebuffer dump, named so the series reads
        key:<chord>          one keystroke, e.g. `ret` or `ctrl-alt-f2`
        text:<string>        typed one keystroke per character
        watch:<label>:<max>  photograph the screen until it stops moving
        power:<seconds>      the ACPI power button, then wait for the
                             machine to go

    `layout` is the keymap the guest has loaded, which text: is typed
    through. `prefix` names the picture series, so that a second run
    driving the same machine over the same run directory does not
    overwrite the first one's evidence.

    Everything it did is returned as a transcript, because a screenshot
    of a filled-in form says nothing about which keys filled it in.
    """
    transcript: list[str] = []
    for index, step in enumerate(steps, start=1):
        # A machine that has gone is asked nothing more. Without this the
        # next send-key writes to a closed socket, and the BrokenPipeError
        # that follows escapes as a traceback - throwing away the
        # screenshots and the transcript of everything that DID happen,
        # which on a run this long is the whole result.
        if alive is not None and not alive():
            transcript.append(f"{index:02d} (the machine is gone; {step!r} "
                              f"and everything after it was not sent)")
            print(f"  {transcript[-1]}")
            break
        kind, _, argument = step.partition(":")
        if kind == "wait":
            time.sleep(float(argument))
        elif kind == "shot":
            time.sleep(SHOT_SETTLE)
            shot = qmp.screenshot(run / f"{prefix}-{index:02d}-{argument}")
            if shot:
                shots.append(shot)
        elif kind == "key":
            qmp.press(argument)
        elif kind == "text":
            qmp.type_text(argument, layout)
        elif kind == "watch":
            label, _, limit = argument.partition(":")
            timeline, frame = watch(qmp, run, label=label,
                                    limit=float(limit), alive=alive)
            (run / f"{label}-timeline.txt").write_text("\n".join(timeline) + "\n")
            if frame:
                shots.append(frame)
            transcript.extend("   " + line for line in timeline)
        elif kind == "power":
            # ACPI rather than `quit`: the live medium runs systemd, which
            # answers the power button by shutting down, and a guest that
            # is killed mid-write is a guest whose target disk cannot be
            # trusted to be what the installation left behind.
            qmp.execute("system_powerdown")
            deadline = time.monotonic() + float(argument or 120)
            while time.monotonic() < deadline:
                if alive is not None and not alive():
                    break
                time.sleep(1.0)
        else:
            sys.exit(f"unknown step {step!r} - use wait:, shot:, key:, "
                     f"text:, watch: or power:")
        transcript.append(f"{index:02d} {step}")
        print(f"  {index:02d} {step}")
    return transcript


def _release_steps(arguments, scenario: str) -> tuple[str, ...]:
    """The script a release-family run drives with.

    A file given with --script wins, because the whole point of the
    driving being data rather than code is that a screen nobody has seen
    before can be answered without editing this file.
    """
    if arguments.script:
        return tuple(line.strip() for line
                     in Path(arguments.script).read_text().splitlines()
                     if line.strip() and not line.startswith("#"))
    if arguments.steps:
        return tuple(arguments.steps)
    return DRIVE_SCRIPTS[scenario]


def run_release(arguments, scenario: str) -> int:
    """Boot the shipping medium (or what it installed) and press keys at it."""
    installed = scenario == "release-installed"
    iso = None if installed else (arguments.iso or newest_iso(ISO_PATTERNS[scenario]))
    run = OUT / f"run-{scenario}"
    if run.exists():
        shutil.rmtree(run)
    run.mkdir(parents=True)

    # The boot menu is over before the root filesystem is touched, so
    # this scenario is the one release-family run whose firmware is a
    # real choice rather than a constraint. UEFI shows GRUB's menu and
    # BIOS shows syslinux's; they are two different mechanisms with two
    # different theming systems, and only running both looks at both.
    firmware = arguments.firmware or SCENARIOS[scenario]["firmware"]
    menu_only = scenario == "boot-menu"

    print(f"scenario    {scenario} ({SCENARIOS[scenario]['what']})")
    print(f"image       {iso or '(none - the disk boots on its own)'}")
    if menu_only:
        print(f"firmware    {firmware} "
              f"({'GRUB' if firmware == 'uefi' else 'syslinux'})")

    # Not on the boot-menu run. inspect_release_iso() extracts a
    # gigabyte of squashfs out of the ISO to prove the absences, which is
    # the release scenario's question and takes longer than this whole
    # run - and every one of the absences it checks is a property of the
    # root filesystem, which a boot menu has not reached.
    if iso is not None and not menu_only:
        print("\n== what is NOT in the image ==")
        problems, notes = inspect_release_iso(iso, OUT / "release-inspection")
        for note in notes:
            print(f"  {note}")
        for problem in problems:
            print(f"  PROBLEM: {problem}")
        if problems:
            print("\nThis image must not be given to anybody. Not booting it.")
            return 1
        print("  no autologin, no credential, no collector, no serial console")

    # A disk to install onto, or the installer has nothing to offer:
    # installer.core.disks.list_disks() excludes the medium it booted
    # from, and installer.core.model.MIN_DISK_MIB rules out anything
    # smaller than 2562 MiB. Its own file, never iso/out/target.img -
    # that one carries what the SMOKE image installed, and the whole
    # point of this family is that the two are never confused. Which file
    # is per scenario, for the same reason one file further down: see
    # RELEASE_BOOT_TARGET.
    target = arguments.disk or RELEASE_TARGETS[scenario]
    if target is None:
        pass
    elif installed:
        if not target.is_file():
            sys.exit(f"no disk at {target}. Run "
                     f"`./iso/test-boot.py --scenario release-install` first - "
                     f"this scenario boots what that one installed.")
    elif not arguments.keep_disk:
        target.unlink(missing_ok=True)
        with open(target, "wb") as handle:
            handle.truncate(TARGET_BYTES)

    if firmware != "uefi":
        # The BIOS half of the boot-menu run. Asking for a variable store
        # here would make a machine with no OVMF installed fail on a
        # scenario that does not use it - and _first_existing() exits
        # rather than returning, so the failure would be about firmware
        # this run never loads.
        efivars = None
    elif scenario in ("release", "boot-menu"):
        # Its own variable store, made fresh and thrown away with the
        # run. Any kept store holds the boot entry a previous
        # installation wrote, and a firmware that finds one boots that
        # disk instead of this medium.
        efivars = efi_variables(run / "efivars.fd")
    elif scenario == "release-install-ohne-netz":
        # Ein eigener, frischer Speicher, und NICHT der von
        # RELEASE_EFIVARS. Dieser Lauf soll scheitern; teilte er sich den
        # Speicher mit `release-install`/`release-installed`, naehme er
        # deren Starteintrag mit - und zwar auch dann, wenn einer davon
        # gerade laeuft. Gemessen am 17.08.2026: waehrend dieser
        # Aenderung hatte ein `release-installed` genau diese Datei
        # geoeffnet.
        RELEASE_OHNE_NETZ_EFIVARS.unlink(missing_ok=True)
        efivars = efi_variables(RELEASE_OHNE_NETZ_EFIVARS)
    else:
        # The installing and the installed run SHARE one, because that is
        # where the installation's own `bootctl install` puts the boot
        # entry and the only place the next run can find it. Made fresh
        # for the installation - a leftover entry would let the run that
        # boots the disk boot a PREVIOUS installation of it - and then
        # kept, deliberately, past the wipe of the run directory.
        if scenario == "release-install" and not arguments.keep_disk:
            RELEASE_EFIVARS.unlink(missing_ok=True)
        if installed and not RELEASE_EFIVARS.is_file():
            sys.exit(f"no EFI variables at {RELEASE_EFIVARS}; the "
                     f"installation that should have written a boot entry "
                     f"into them has not been run")
        efivars = efi_variables(RELEASE_EFIVARS)
    print(f"efivars     {efivars}")

    kvm = not arguments.no_kvm and os.access("/dev/kvm", os.W_OK)
    command = qemu_command(
        run,
        iso=iso,
        target=target,
        update=None,
        firmware=firmware,
        efivars=efivars,
        vga=arguments.vga,
        memory=arguments.memory,
        kvm=kvm,
        evidence=None,
        # Die eine Zeile, um die es in diesem Szenario geht.
        network=scenario != "release-install-ohne-netz",
    )
    print("\n== booting ==")
    print("  " + " ".join(command))
    qemu = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    shots: list[Path] = []
    # The subset of them that can still be a boot menu. Kept apart from
    # `shots` because the installer is drawn in the SAME palette this
    # medium's boot menu is - it is one brand - so a frame of the first
    # installer page would satisfy every test grade_boot_menu() makes and
    # report a themed menu on a run whose menu was never photographed.
    # Nothing past twenty seconds can be the menu: grub.cfg's timeout is
    # ten and syslinux's is ten.
    menu_frames: list[Path] = []
    transcript: list[str] = []
    died = ""
    qmp: Qmp | None = None
    try:
        qmp = Qmp(qmp_socket(run))
        # A picture every so often for as long as the machine is left to
        # itself. This is the whole of what the harness can observe on
        # this image, so it observes often enough to see a boot menu, a
        # kernel, a compositor starting and an installer, rather than
        # only the last of those.
        started = time.monotonic()
        schedule = (arguments.settle
                    or (BOOT_MENU_SETTLE[firmware] if menu_only
                        else RELEASE_SETTLE[scenario]))
        for mark in schedule:
            while time.monotonic() - started < mark:
                if qemu.poll() is not None:
                    died = f"qemu exited rc={qemu.returncode} after " \
                           f"{time.monotonic() - started:.0f}s"
                    break
                time.sleep(1.0)
            if died:
                break
            shot = qmp.screenshot(run / f"screen-{mark:04d}s")
            if shot:
                shots.append(shot)
                if mark <= BOOT_MENU_WINDOW and shot.suffix == ".png":
                    menu_frames.append(shot)
                print(f"  screenshot at {mark}s -> {shot.name}")

        if not died:
            print("\n== driving it ==")
            transcript = drive(qmp, _release_steps(arguments, scenario), run, shots,
                               layout=(arguments.layout
                                       or RELEASE_LAYOUT.get(scenario, "us")),
                               alive=lambda: qemu.poll() is None)
            if qemu.poll() is not None:
                died = f"qemu exited rc={qemu.returncode}"
    finally:
        if qmp is not None:
            shot = qmp.screenshot(run / "screen-final")
            if shot:
                shots.append(shot)
            if not arguments.keep_running:
                try:
                    qmp.execute("quit")
                except Exception:
                    pass
        if not arguments.keep_running:
            try:
                qemu.wait(timeout=20)
            except subprocess.TimeoutExpired:
                qemu.kill()

    # ----------------------------------------------------------------
    # The one thing on these screens that CAN be graded
    # ----------------------------------------------------------------
    # Everything else a release-family run photographs is a form, and
    # whether a form is right is a human's judgement. The boot menu is
    # not: it is the brand's own palette or it is the fallback, the two
    # are nowhere near each other in a histogram, and the failure mode is
    # specifically one that reports nothing anywhere else. So the frames
    # are measured here on every scenario in the family - and the
    # boot-menu run, which exists for this question, is the one whose
    # exit code depends on the answer.
    themed, palette = grade_boot_menu(menu_frames)
    if palette:
        print("\n== the boot menu, measured ==")
        for line in palette:
            print(line)

    print()
    if died:
        print(f"status      {died}")
    else:
        print("status      the machine ran and answered every screenshot")
    if target is not None:
        print(f"target disk {target} ({_written_bytes(target)})")
    for shot in shots:
        print(f"screenshot  {shot}")
    if transcript:
        (run / "transcript.txt").write_text("\n".join(transcript) + "\n")
        print(f"transcript  {run / 'transcript.txt'}")

    if menu_only:
        print("\nboot menu   " + ("branded on both counts - petrol behind it "
                                  "and the brand yellow on the selected entry"
                                  if themed else
                                  "FELL BACK. Nothing on this medium will say "
                                  "so; the numbers above are the only report."))
        return 0 if themed and not died else 1

    print("\nWhat is on those screenshots is not something this harness can "
          "grade. Look at them.")

    # A machine that powered itself off at the end of a script that asked
    # it to is not a failure - `power:` is the last step of the
    # installation run, and -no-reboot makes qemu exit when the guest
    # goes. Only a death the script did not ask for counts.
    return 1 if died and "power" not in " ".join(transcript) else 0


# Wann im Secure-Boot-Lauf fotografiert wird.
#
# Dieselbe Lage wie BOOT_MENU_SETTLE["uefi"] und noch drei Marken
# dahinter. Die ersten sieben sind das Fenster, in dem das Startmenue
# stehen muesste; die letzten drei sind dafuer da, dass der Lauf, in dem
# es NICHT kommt, nicht nur ein leeres Fenster meldet, sondern auch das
# Bild dessen, was stattdessen da steht. Gemessen 11.08.2026: OVMF mit
# SMM braucht laenger zum Aufsetzen als das gewoehnliche - die Ablehnung
# steht bei 13 Sekunden noch nicht auf dem Schirm.
SECURE_BOOT_SETTLE = [4, 5, 6, 7, 9, 11, 13, 18, 25, 35]

# Die zwei Maschinen dieses Szenarios, in der Reihenfolge, in der sie
# laufen. Die Kontrolle zuerst: ein Aufbau, in dem die Kontrolle nicht
# das tut, was sie soll, sagt ueber den anderen Lauf nichts aus, und das
# will man vor und nicht nach vierzig Sekunden Warten wissen.
SECURE_BOOT_MACHINES = (
    ("setup", "Setup Mode - kein Plattformschluessel, die Firmware prueft nichts"),
    ("enforcing", "User Mode - Plattformschluessel eingetragen, die Firmware prueft"),
)


def run_secure_boot(arguments) -> int:
    """Startet das Medium zweimal und vergleicht die beiden Bildschirme.

    WAS HIER GEMESSEN WIRD, UND WAS EIN EINZELNER LAUF NICHT MESSEN KANN
        "Das Medium startet unter Secure Boot nicht" ist fuer sich keine
        Aussage ueber Secure Boot. Ein Medium startet auch nicht, wenn
        die Firmware zu wenig Speicher hat, wenn das Abbild kaputt ist
        oder wenn QEMU anders aufgerufen wurde als beim letzten Mal. Was
        die Aussage traegt, ist der Unterschied zwischen zwei Laeufen,
        die sich in genau einer Datei unterscheiden: dem
        Variablenspeicher.

        Beide bekommen OVMF_CODE.secboot.4m.fd, dieselbe Maschine,
        dasselbe ISO, denselben Zeitplan. Der eine bekommt
        OVMF_VARS.4m.fd, wie Arch es ausliefert - leer, also Setup Mode,
        also keine Pruefung. Der andere bekommt denselben Speicher mit
        einem Plattformschluessel darin, den iso/secureboot.py
        hineingeschrieben hat, und OVMF geht daraufhin von selbst in den
        User Mode und erzwingt.

    WIE ES BEWERTET WIRD
        Mit demselben Messgeraet, mit dem `--scenario boot-menu` das
        Startmenue bewertet: grade_boot_menu() sucht in den Bildern des
        Startfensters eine Flaeche in Petrol mit dem Markengelb darauf.
        Das ist hier genau die richtige Frage - denn GRUB ist das erste
        eigene Programm der Kette, und ein Bild seines Menues heisst, die
        Firmware hat BOOTx64.EFI geladen.

        Bestanden ist der Lauf, wenn die Kontrolle das Menue zeigt und
        die erzwingende Maschine es nicht. Zeigen es beide, dann erzwingt
        die Firmware nichts und der Aufbau misst nichts; zeigt es keine,
        dann ist etwas anderes kaputt und die Ablehnung waere nicht dem
        Secure Boot zuzuschreiben.
    """
    iso = arguments.iso or newest_iso(ISO_PATTERNS["secure-boot"])
    run_root = OUT / "run-secure-boot"
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)

    print(f"scenario    secure-boot ({SCENARIOS['secure-boot']['what']})")
    print(f"image       {iso}")

    # Die billige Haelfte zuerst, weil sie die teure erklaert: wenn keine
    # Stufe der Kette eine Signatur traegt, ist die Ablehnung weiter
    # unten kein Raetsel, sondern die Bestaetigung.
    print("\n== was die Startkette an Signaturen traegt ==")
    unsigned = []
    for entry in secureboot.inspect_boot_chain(iso):
        if "error" in entry:
            print(f"  {entry['member']:<34} {entry['error']}")
            continue
        state = (f"signiert, {entry['certificate_bytes']} Byte"
                 if entry["signed"] else "OHNE SIGNATUR")
        if not entry["signed"]:
            unsigned.append(entry["member"])
        print(f"  {entry['member']:<34} {entry['bytes']:>9} Byte  {state}")

    code = _first_existing(secureboot.OVMF_SECBOOT_CODE_CANDIDATES,
                           "OVMF mit Secure Boot")
    print(f"\nfirmware    {code}")

    kvm = not arguments.no_kvm and os.access("/dev/kvm", os.W_OK)
    results: dict[str, tuple[bool, list[Path]]] = {}

    for name, description in SECURE_BOOT_MACHINES:
        run = run_root / name
        run.mkdir()
        efivars = run / "efivars.fd"
        if name == "enforcing":
            # Eine KOPIE des eingetragenen Speichers, nicht er selbst.
            # OVMF schreibt beim Start hinein (SecureBootEnable,
            # Startreihenfolge), und ein Speicher, der einen Lauf
            # ueberlebt, waere beim naechsten Mal ein anderer.
            efivars.write_bytes(secureboot.secure_boot_variables(OUT).read_bytes())
        else:
            template = _first_existing(OVMF_VARS_CANDIDATES,
                                       "OVMF variable template")
            efivars.write_bytes(template.read_bytes())

        variables = secureboot.read_variables(efivars.read_bytes())
        print(f"\n== {name}: {description} ==")
        print(f"  Variablenspeicher {efivars} "
              f"({', '.join(v['name'] for v in variables) or 'leer'})")

        command = qemu_command(
            run, iso=iso, target=None, update=None,
            firmware="uefi-secure", efivars=efivars,
            vga=arguments.vga, memory=arguments.memory, kvm=kvm, evidence=None)
        print("  " + " ".join(command))
        qemu = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)

        frames: list[Path] = []
        menu_frames: list[Path] = []
        qmp: Qmp | None = None
        died = ""
        try:
            qmp = Qmp(run / "qmp.sock")
            started = time.monotonic()
            for mark in (arguments.settle or SECURE_BOOT_SETTLE):
                while time.monotonic() - started < mark:
                    if qemu.poll() is not None:
                        died = (f"qemu exited rc={qemu.returncode} after "
                                f"{time.monotonic() - started:.0f}s")
                        break
                    time.sleep(1.0)
                if died:
                    break
                shot = qmp.screenshot(run / f"screen-{mark:04d}s")
                if shot:
                    frames.append(shot)
                    if mark <= BOOT_MENU_WINDOW and shot.suffix == ".png":
                        menu_frames.append(shot)
                    print(f"  screenshot at {mark}s -> {shot.name}")
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

        if died:
            print(f"  {died}")
        themed, palette = grade_boot_menu(menu_frames)
        for line in palette:
            print(line)
        results[name] = (themed, frames)

    # ----------------------------------------------------------------
    # Der Vergleich, der die Aussage traegt
    # ----------------------------------------------------------------
    control, _control_frames = results["setup"]
    enforced, _enforced_frames = results["enforcing"]

    print("\n== Ergebnis ==")
    print(f"  Setup Mode     Startmenue {'JA' if control else 'nein'}")
    print(f"  User Mode      Startmenue {'JA' if enforced else 'nein'}")
    for name, _description in SECURE_BOOT_MACHINES:
        for frame in results[name][1]:
            print(f"  Bild           {frame}")

    if not control:
        print("\nDie Kontrolle hat das Startmenue nicht gezeigt. Dann sagt "
              "dieser Lauf\nueber Secure Boot nichts - erst muss der Aufbau "
              "selbst stimmen.")
        return 1
    if enforced:
        print("\nBEIDE Maschinen haben das Medium gestartet. Die Firmware "
              "erzwingt also\nnichts, und der Lauf misst nicht, was er "
              "messen soll.")
        return 1

    print(f"\nDas Medium startet mit derselben Firmware ohne "
          f"Plattformschluessel und\nnicht mit einem. Die "
          f"{len(unsigned)} Stufen der Startkette ohne Signatur oben "
          f"sagen,\nwarum: es gibt nichts, was die Firmware pruefen "
          f"koennte.")
    return 0


def _written_bytes(image: Path) -> str:
    """How much of a sparse image has actually been written to.

    The one fact about the target disk the host can read without mounting
    anything, and the cheapest answer to "did the installation put
    anything on it at all": the file claims 24 GiB from the moment it is
    created, and occupies nothing until something writes.
    """
    if not image.is_file():
        return "missing"
    stat = image.stat()
    return (f"{stat.st_blocks * 512 / 1024**3:.1f} GiB written of "
            f"{stat.st_size / 1024**3:.0f} GiB claimed")


def attach(arguments) -> int:
    """Drive a machine an earlier --keep-running run left standing.

    WHY THIS EXISTS
        Every screen of the installer is answered by a key whose effect
        depends on what the previous screen did with the one before it,
        and none of it is documented anywhere but on the screen. Working
        that out by booting from cold for each guess would be a
        twenty-minute cycle per keystroke; this makes it one second, and
        - the part that matters - it makes the ANSWER a list of steps
        that can then be pasted into DRIVE_SCRIPTS verbatim, rather than
        a procedure somebody carried out by hand once.

        QEMU's QMP socket is a listening server, so it accepts a second
        client after the first has gone. Nothing about the guest is
        disturbed in between.
    """
    run = arguments.run_dir or (OUT / "run-release-install")
    if not qmp_socket(run).exists():
        sys.exit(f"no machine to attach to: {qmp_socket(run)} does not exist. "
                 f"A run has to have been started with --keep-running.")
    # Asked for explicitly, never defaulted. A standing machine is
    # somewhere in the middle of a form, and running a scenario's whole
    # script at it - which is written for a machine that has just booted -
    # would press twenty keys into a screen nobody chose them for.
    if not (arguments.steps or arguments.script):
        sys.exit("--attach needs --steps or --script: there is no sensible "
                 "default set of keys to press at a machine somebody left "
                 "standing.")
    steps = _release_steps(arguments, "release")
    qmp = Qmp(qmp_socket(run))
    shots: list[Path] = []
    print(f"attached    {qmp_socket(run)}")
    transcript = drive(qmp, steps, run, shots,
                       layout=arguments.layout or "us", prefix=arguments.label)
    with open(run / "transcript.txt", "a") as handle:
        handle.write("\n".join(transcript) + "\n")
    for shot in shots:
        print(f"screenshot  {shot}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="session",
                        help="; ".join(f"{name}: {spec['what']}"
                                       for name, spec in SCENARIOS.items()))
    parser.add_argument("--iso", type=Path, help="image to boot (default: newest in iso/out/)")
    parser.add_argument("--timeout", type=int,
                        help="seconds to wait for the guest to report DONE "
                             "(default: per scenario)")
    parser.add_argument("--firmware", choices=("bios", "uefi", "uefi-secure"),
                        help="override the scenario's firmware")
    parser.add_argument("--disk", type=Path,
                        help="the target disk image (default: iso/out/target.img)")
    parser.add_argument("--keep-disk", action="store_true",
                        help="do not recreate the target disk before installing")
    parser.add_argument("--repo-port", type=int,
                        help="port the repository is served on "
                             "(default: whatever is free)")
    parser.add_argument("--repo-dir", type=Path,
                        help="serve an already staged repository instead of "
                             "staging packaging/out/ - point this at a build "
                             "from a bumped VERSION to watch a real upgrade")
    parser.add_argument("--no-stage-probe", action="store_true",
                        help="do not refresh the update probe inside the "
                             "target disk before booting it")
    parser.add_argument("--vga", default="virtio",
                        help="QEMU display adapter (virtio, std, ...)")
    parser.add_argument("--memory", default="4G")
    parser.add_argument("--no-kvm", action="store_true")
    parser.add_argument("--keep-running", action="store_true",
                        help="do not shut the machine down when the run ends")
    parser.add_argument("--script", type=Path,
                        help="release scenarios: a file of wait:/shot:/key:/"
                             "text:/watch:/power: steps to drive with")
    parser.add_argument("--steps", nargs="+",
                        help="release scenarios: the same steps given "
                             "directly, one per argument")
    parser.add_argument("--layout", choices=("us", "de"),
                        help="the keymap the GUEST has loaded, which text: "
                             "steps are typed through (default: per "
                             "scenario, see RELEASE_LAYOUT)")
    parser.add_argument("--settle", type=int, nargs="+",
                        help="release scenarios: seconds at which to take a "
                             "screenshot before the script runs")
    parser.add_argument("--attach", action="store_true",
                        help="do not boot anything: drive a machine an "
                             "earlier --keep-running run left standing")
    parser.add_argument("--run-dir", type=Path,
                        help="--attach: which run directory's qmp.sock to "
                             "connect to (default: iso/out/run-release-install)")
    parser.add_argument("--label", default="key",
                        help="--attach: what to call this batch of "
                             "screenshots, so a second batch does not "
                             "overwrite the first")
    arguments = parser.parse_args()

    if arguments.attach:
        # No machine is started here, so qemu need not even be installed
        # - one is already running, and this only talks to it.
        return attach(arguments)

    if not shutil.which("qemu-system-x86_64"):
        sys.exit("qemu-system-x86_64 is not installed")

    # The shipping medium is driven, not listened to: no serial marker, no
    # evidence disk, no guest that says anything. It has a run of its own
    # rather than a branch in the loop below, which polls for a line this
    # image never prints.
    # Zwei Maschinen statt einer, also weder run_release() noch die
    # Schleife darunter: beide fahren genau einen Gast, und der Vergleich
    # zweier Firmware-Zustaende ist der ganze Inhalt dieses Szenarios.
    if arguments.scenario == "secure-boot":
        return run_secure_boot(arguments)

    if arguments.scenario in RELEASE_FAMILY:
        return run_release(arguments, arguments.scenario)

    scenario = SCENARIOS[arguments.scenario]
    firmware = arguments.firmware or scenario["firmware"]
    timeout = arguments.timeout or scenario["timeout"]

    # The ISO is what the installed system is booted WITHOUT. That is not
    # decoration: an installed system that only boots while the medium it
    # was installed from is still in the drive has not been shown to
    # boot.
    iso = None
    if arguments.scenario not in ("installed", "update"):
        iso = arguments.iso or newest_iso()

    target = None
    if arguments.scenario in ("install", "installed", "update"):
        target = arguments.disk or (OUT / "target.img")

    run = OUT / "run"
    if run.exists():
        shutil.rmtree(run)
    run.mkdir(parents=True)

    # Sparse: the file is 512 MB of address space and a few megabytes of
    # disk until the guest writes to it.
    with open(run / "evidence.img", "wb") as handle:
        handle.truncate(EVIDENCE_BYTES)

    if arguments.scenario == "install" and not arguments.keep_disk:
        # A fresh disk every time, and the EFI variables with it. An
        # installation onto a disk that already carries one is a
        # different experiment - archinstall would find existing
        # partitions - and a boot entry left over from the previous run
        # would let the "installed" scenario boot the previous
        # installation without anybody noticing.
        if target.exists():
            target.unlink()
        (OUT / "efivars.fd").unlink(missing_ok=True)
        with open(target, "wb") as handle:
            handle.truncate(TARGET_BYTES)
        print(f"target disk {target} ({TARGET_BYTES // 1024**3} GiB, sparse)")

    if target is not None and not target.is_file():
        sys.exit(
            f"no target disk at {target}. Run "
            f"`./iso/test-boot.py --scenario install` first - the installed "
            f"system is booted from the disk that scenario writes."
        )

    efivars = efi_variables(OUT / "efivars.fd") if firmware == "uefi" else None

    # ----------------------------------------------------------------
    # The update run's server, and the disk that addresses it
    # ----------------------------------------------------------------
    # Started BEFORE qemu, deliberately: the guest's pacman reaches for
    # the database within seconds of the unit starting, and a server that
    # is still binding its socket at that moment produces a run that
    # fails for a reason that is not about ZepOS.
    update_disk = None
    repo_server: subprocess.Popen | None = None
    repo_url = ""
    if arguments.scenario == "update":
        if not arguments.no_stage_probe:
            stage_update_probe(target)
        port = arguments.repo_port or free_port()
        repo_server = serve_repository(run, port, arguments.repo_dir)
        # `$arch` stays literal all the way to the guest's pacman.conf,
        # exactly as installer/core/source.py's ONLINE_REPO_URL does -
        # the URL under test is the SHAPE of the published one, with a
        # different host and port.
        repo_url = f"http://{SLIRP_HOST}:{port}/$arch"
        update_disk = write_update_disk(run / "update.img", repo_url)
        print(f"repository  {repo_url}")

    kvm = not arguments.no_kvm and os.access("/dev/kvm", os.W_OK)
    if not kvm and not arguments.no_kvm:
        print("warning: /dev/kvm is not writable - falling back to emulation")

    command = qemu_command(
        run,
        iso=iso,
        target=target,
        update=update_disk,
        firmware=firmware,
        efivars=efivars,
        vga=arguments.vga,
        memory=arguments.memory,
        kvm=kvm,
        evidence=run / "evidence.img",
    )
    print(f"scenario    {arguments.scenario} ({scenario['what']})")
    print(f"firmware    {firmware}")
    print(f"booting     {iso.name if iso else target}")
    print("  " + " ".join(command))
    qemu = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    serial = run / "serial.log"
    qmp: Qmp | None = None
    shots: list[Path] = []
    result_line = ""
    status = "timeout"
    started = time.monotonic()
    seen = 0
    # Two scheduled dumps before the guest says anything, so that a run
    # which never reports still comes back with a picture of where it
    # stopped.
    scheduled = [60, 150]

    def read_serial() -> bool:
        """Consume whatever the guest has said since the last call.

        Returns whether it has said DONE. Pulled out of the loop because
        it also has to run ONCE MORE after the loop ends: the
        installation scenario finishes by powering the machine off, and
        `qemu.poll()` is then true on an iteration that has not yet read
        the guest's summary. Without this the harness would report "qemu
        exited rc=0" and "the guest never reported one" for a run that
        printed both RESULT and DONE a second earlier - grading a
        successful installation as a failure on a timing accident.
        """
        nonlocal seen, result_line
        if not serial.exists():
            return False
        text = serial.read_text(errors="replace")
        for line in text[seen:].splitlines():
            if PREFIX in line:
                print("  " + line.strip())
            if "RESULT " in line:
                result_line = line.strip()
        seen = len(text)
        return DONE in text

    try:
        qmp = Qmp(qmp_socket(run))
        while True:
            elapsed = time.monotonic() - started

            if qemu.poll() is not None:
                status = f"qemu exited rc={qemu.returncode}"
                break

            if read_serial():
                status = "done"
                break

            while scheduled and elapsed >= scheduled[0]:
                mark = scheduled.pop(0)
                shot = qmp.screenshot(run / f"screen-{mark:04d}s")
                if shot:
                    shots.append(shot)
                    print(f"  screenshot at {mark}s -> {shot.name}")

            if elapsed > timeout:
                break
            time.sleep(1.0)

        # Everything the guest said between the last poll and now. See
        # read_serial()'s docstring: the run that powers itself off ends
        # on the branch that has not read it yet.
        if read_serial() and status.startswith("qemu exited"):
            status = f"done ({status})"

        # The decisive screenshot. zepos-smoke-collect only says DONE
        # after the session has had its settling time, so this is the
        # frame that answers the question.
        if qmp is not None:
            shot = qmp.screenshot(run / f"screen-{status}")
            if shot:
                shots.append(shot)
    finally:
        if qmp is not None and not arguments.keep_running:
            try:
                qmp.execute("quit")
            except Exception:
                pass
        if not arguments.keep_running:
            try:
                qemu.wait(timeout=20)
            except subprocess.TimeoutExpired:
                qemu.kill()
        # The repository server outlives qemu only when --keep-running
        # asked for a machine to poke at, which is the one case where it
        # is still needed. Otherwise it goes with the run: a static
        # server left listening on a port nobody remembers is how a
        # LATER run ends up measuring an OLDER repository.
        if repo_server is not None and not arguments.keep_running:
            repo_server.terminate()
            try:
                repo_server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                repo_server.kill()

    # --------------------------------------------------------------
    # Unpack what the guest handed over
    # --------------------------------------------------------------
    evidence = run / "evidence"
    evidence.mkdir(exist_ok=True)
    unpacked = subprocess.run(
        ["tar", "xf", str(run / "evidence.img"), "-C", str(evidence)],
        capture_output=True, text=True)
    if unpacked.returncode != 0:
        print(f"  evidence disk unreadable: {unpacked.stderr.strip()}")

    print()
    print(f"status      {status}")
    print(f"result      {result_line or '(the guest never reported one)'}")
    print(f"serial      {serial}")
    print(f"evidence    {evidence}")
    if target is not None:
        print(f"target disk {target}")
    if repo_url:
        print(f"repository  {repo_url}")
        print(f"server log  {run / 'repo-server.log'}")
    for shot in shots:
        print(f"screenshot  {shot}")

    # The scenario's own marker in the guest's own summary is the only
    # thing that counts as a pass - `session=up` for the two that measure
    # a desktop, `install=0` for the one that measures an installation,
    # `update=0` for the one that measures an upgrade. Anything else,
    # including a clean-looking timeout, is a run whose result has to be
    # read rather than trusted.
    return 0 if scenario["pass"] in result_line else 1


if __name__ == "__main__":
    raise SystemExit(main())
