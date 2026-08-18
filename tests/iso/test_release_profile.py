# SPDX-License-Identifier: GPL-3.0-or-later
"""The shipping profile: what it is, and what it must never become.

WHY THIS FILE EXISTS
    iso/profile/ is a test harness and says so. iso/profile-release/ is
    the image a person downloads, and the difference between the two is
    not a feature list - it is an autologin, a shipped /etc/shadow, an
    answer file with a root password in it, a collector that hands the
    session's state to a raw disk, and a serial console on the kernel
    command line. Every one of those is correct in the harness.

    The danger was never that somebody decides to ship the harness. It is
    that the shipping image is grown out of it a file at a time, and no
    single step looks wrong. So the two profiles are not two copies:
    iso/build.sh --profile release assembles the shipping profile out of
    iso/shared-with-release.txt plus iso/profile-release/, and nothing
    else from the harness can reach it.

    This file checks that arrangement from both ends. Not "these three
    files are absent" - that assertion stays green the moment somebody
    renames one. What is checked is the PROPERTY: nothing in the shipping
    image logs anybody in, carries a credential, reports to a serial
    line, or writes evidence to a disk, and nothing that is in the
    harness profile and not on the shared list may appear in the shipping
    profile at all.

WHAT IT DELIBERATELY DOES NOT DO
    It does not build or boot anything. `./iso/build.sh --profile release`
    builds it and `./iso/test-boot.py --scenario release` boots it, looks
    at the screen and proves the same absences against the actual ISO -
    which is the check this one cannot make, because a profile is not an
    image.
"""
import re
from pathlib import Path

import pytest

ISO = Path(__file__).resolve().parents[2] / "iso"
HARNESS = ISO / "profile"
RELEASE = ISO / "profile-release"
SHARED_LIST = ISO / "shared-with-release.txt"


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def shared_entries() -> list[str]:
    """The allow-list, parsed the way iso/build.sh parses it."""
    lines = []
    for line in _read(SHARED_LIST).splitlines():
        line = re.sub(r"#.*", "", line).strip()
        if line:
            lines.append(line)
    return lines


def assembled() -> dict[str, Path]:
    """Every file the shipping image is built from: the path it has
    inside the profile, and where that content comes from.

    Computed the same way iso/build.sh assembles it - the shared files
    first, iso/profile-release/ over the top - so a test here is a test
    about the image and not about one of its two source directories.
    """
    files: dict[str, Path] = {}
    for entry in shared_entries():
        files[entry] = HARNESS / entry
    for path in sorted(RELEASE.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        if "__pycache__" in path.parts:
            continue
        files[path.relative_to(RELEASE).as_posix()] = path
    return files


def code_lines(path: Path) -> list[str]:
    """A file's content with whole-line comments removed.

    Comments are stripped everywhere in this file, and that is the point
    rather than a convenience: iso/profile-release/ explains at length
    why it carries no autologin, no serial console and no answer file,
    and those explanations name exactly the strings being searched for. A
    scan that could not tell an explanation from a reintroduction would
    force the explanations out, which is the opposite of what is wanted.
    """
    if path.is_symlink() and not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


def _kernel_arguments(text: str, marker: str) -> set[str]:
    line = next(l for l in text.splitlines() if marker in l)
    return {word for word in line.split() if "=" in word}


# --------------------------------------------------------------------
# The absences. This is the whole reason the profile exists.
# --------------------------------------------------------------------

def test_nothing_in_the_shipping_image_logs_anybody_in():
    """No autologin, and no user for one to log in as.

    The harness reaches its run through `agetty --autologin zepos` and a
    ~/.bash_profile. On a medium anybody can download, that is an
    unauthenticated shell handed to whoever boots it - and it is not
    needed, because the installer is a system service that owns tty1.
    """
    offenders = []
    for name, source in assembled().items():
        for line in code_lines(source):
            if "autologin" in line.lower() or re.search(r"\blogin\s+-f\b", line):
                offenders.append(f"{name}: {line.strip()}")
    assert offenders == [], (
        "the shipping image logs somebody in:\n  " + "\n  ".join(offenders))

    # And the other half: an autologin needs an account. The harness
    # creates one with sysusers.d; the shipping image creates none, so
    # even a drop-in that came back with a package would have nobody to
    # log in as.
    assert "airootfs/etc/sysusers.d/zepos.conf" not in assembled(), (
        "the shipping image creates a live user; it has no session for "
        "one to run in and no reason to carry one")


def test_the_shipping_image_ships_no_credential():
    """No password, no hash, no /etc/shadow of its own.

    The harness ships both: /etc/shadow so that root has an empty
    password, and unattended-install.json so that a run needs no human -
    with a root password in clear text, at mode 0600, inside the image.
    Neither can be in a file anybody can download; the medium uses the
    /etc/shadow the filesystem package brings, where root has no usable
    password at all, and iso/build.sh checks that against the built root.
    """
    keys = ("password", "root_password", "encryption_password", "passwd")
    offenders = []
    for name, source in assembled().items():
        if name == "airootfs/etc/shadow":
            offenders.append(f"{name}: the image ships its own /etc/shadow")
            continue
        for line in code_lines(source):
            lowered = line.lower()
            if any(f'"{key}"' in lowered for key in keys):
                offenders.append(f"{name}: {line.strip()}")
            elif re.search(r"\b(password|passwort)\s*[=:]\s*\S", lowered):
                offenders.append(f"{name}: {line.strip()}")
    assert offenders == [], (
        "the shipping image carries a credential:\n  " + "\n  ".join(offenders))


def test_the_shipping_image_reports_to_nobody():
    """No collector, no evidence disk, no serial console.

    Three separate channels in the harness and one reason for all three:
    something has to read the run without a human in front of the
    machine. The shipping image has a human in front of the machine.

    The serial console is the one worth spelling out. `console=ttyS0` on
    a medium somebody else boots sends their installation - including
    every password prompt in it - to whatever is wired to that machine's
    serial port, and slows the boot to 115200 baud on the way.
    """
    forbidden = {
        "ttyS0": "a serial console",
        "ZEPOS-SMOKE": "the harness's progress marker",
        "zepos-smoke": "the collector",
        "/dev/disk/by-id/virtio-": "an evidence or target disk by harness name",
        "unattended-install.json": "the unattended answer file",
    }
    offenders = []
    for name, source in assembled().items():
        for line in code_lines(source):
            for needle, what in forbidden.items():
                if needle in line:
                    offenders.append(f"{name}: {what}: {line.strip()}")
    assert offenders == [], (
        "the shipping image still measures itself:\n  " + "\n  ".join(offenders))


def test_neither_boot_path_carries_a_console_argument():
    """Both loader configurations, checked as configurations rather than
    as text: the arguments the kernel is actually given.

    They must also be the same arguments. Which of the two paths a
    machine offers is not the user's choice, and a medium that behaves
    differently depending on the firmware is a bug report nobody can
    reproduce.
    """
    bios = _kernel_arguments(_read(RELEASE / "syslinux/syslinux-linux.cfg"), "APPEND ")
    uefi = _kernel_arguments(_read(RELEASE / "grub/grub.cfg"), "vmlinuz-linux")

    for name, arguments in (("BIOS", bios), ("UEFI", uefi)):
        consoles = [word for word in arguments if word.startswith("console=")]
        assert consoles == [], f"the {name} entry carries {consoles}"

    assert bios == uefi, (
        f"the two boot paths disagree: BIOS has {bios - uefi}, UEFI has {uefi - bios}")


def test_nothing_of_the_harness_reaches_the_shipping_profile():
    """The rule the arrangement exists to keep, checked as a rule.

    Everything in iso/profile/ is harness by default; a file crosses over
    only by being named in iso/shared-with-release.txt. This is what
    fails when somebody copies a harness file into iso/profile-release/
    instead of adding it to the list - the copy has the same profile-
    relative path, and that is exactly what is looked for here.
    """
    allowed = set(shared_entries())

    # By content, and by content alone. Both profiles have a
    # profiledef.sh, a packages.x86_64 and two boot loader
    # configurations, and they SHOULD - those are the files that differ.
    # What may not happen is one of them arriving with the harness's
    # content, under that name or under any other.
    harness_bodies: dict[bytes, str] = {}
    for path in HARNESS.rglob("*"):
        if path.is_symlink() or not path.is_file() or "__pycache__" in path.parts:
            continue
        name = path.relative_to(HARNESS).as_posix()
        if name in allowed:
            continue
        harness_bodies[path.read_bytes()] = name

    offenders = []
    for name, source in assembled().items():
        if source.is_symlink() or not source.is_file():
            continue
        body = source.read_bytes()
        if body in harness_bodies:
            offenders.append(f"{name} is the harness's {harness_bodies[body]}")

    assert offenders == [], (
        "these belong to the harness and have been copied into the "
        "shipping profile. If one of them really belongs in both images, "
        "put it on the shared list and argue for it there:\n  "
        + "\n  ".join(offenders))

    # And the apparatus by name, for the case where it comes back
    # rewritten rather than copied. The properties those files carry are
    # checked above; these are the paths they live at.
    for path in ("airootfs/etc/shadow",
                 "airootfs/etc/sysusers.d/zepos.conf",
                 "airootfs/etc/systemd/system/getty@tty1.service.d/autologin.conf",
                 "airootfs/home/zepos/.bash_profile",
                 "airootfs/usr/local/bin/zepos-smoke",
                 "airootfs/usr/local/bin/zepos-smoke-collect",
                 "airootfs/usr/local/bin/zepos-smoke-update",
                 "airootfs/usr/local/bin/zepos-install-unattended",
                 "airootfs/usr/local/share/zepos-install/unattended-install.json"):
        assert path not in assembled(), f"the harness is back: {path}"


def test_the_shared_list_names_nothing_that_carries_the_harness():
    """The allow-list is the one place where a harness file could be let
    through deliberately, so the same properties are checked against
    every entry on it - and against the entry's real content, not
    against its name."""
    for entry in shared_entries():
        source = HARNESS / entry
        assert source.exists() or source.is_symlink(), (
            f"{entry} is on the shared list and not in iso/profile/; "
            f"iso/build.sh stops the build on this")
        for line in code_lines(source):
            for needle in ("autologin", "ttyS0", "ZEPOS-SMOKE", "password"):
                assert needle not in line, (
                    f"{entry} is shared with the shipping image and "
                    f"contains {needle!r}: {line.strip()}")


# --------------------------------------------------------------------
# What it does instead
# --------------------------------------------------------------------

def test_the_medium_boots_into_the_installer():
    """A service on tty1, and no getty next to it.

    Both halves matter. Without the mask, two programs share one virtual
    terminal and the screen is unreadable; without the unit, the medium
    boots to a login prompt for an account with no password - which is
    the one thing worse than an autologin.
    """
    files = assembled()

    unit = "airootfs/etc/systemd/system/zepos-install.service"
    wants = ("airootfs/etc/systemd/system/multi-user.target.wants/"
             "zepos-install.service")
    assert unit in files, "nothing starts the installer"
    assert wants in files, "the installer service is never started"
    assert Path(files[wants]).is_symlink()

    text = _read(files[unit])
    assert "ExecStart=/usr/local/bin/zepos-live-session" in text
    assert "TTYPath=/dev/tty1" in text
    assert "PAMName=login" in text, (
        "without a PAM session there is no logind session, no seat and no "
        "XDG_RUNTIME_DIR - the compositor cannot take the display and the "
        "medium falls through to the text interface on a machine whose "
        "graphics are fine")

    # The getty is masked on the kernel command line rather than by a
    # symlink in the profile. Both work; the file version is in place
    # while pacstrap runs, and systemd's own scriptlet then fails to
    # enable getty@tty1 and turns the build log into one that contains an
    # error somebody has to be told to ignore. The comment in
    # syslinux-linux.cfg has the measurement.
    assert "Conflicts=getty@tty1.service" in text, (
        "nothing stops a getty and the installer sharing tty1")
    for loader in ("syslinux/syslinux-linux.cfg", "grub/grub.cfg",
                   "grub/loopback.cfg"):
        assert "systemd.mask=getty@tty1.service" in _read(RELEASE / loader), (
            f"{loader} does not mask the getty, so a login prompt comes up "
            f"on the installer's screen")
    assert not (RELEASE / "airootfs/etc/systemd/system/getty@tty1.service").exists(), (
        "the getty is masked twice; the file version makes the build log "
        "carry a pacman error")


def test_the_session_tries_the_graphical_surface_and_then_the_text_one():
    """Spec §8.5, and specifically its last sentence: "Erkennung ueber den
    tatsaechlichen Startversuch, nicht ueber eine Hardware-Liste."

    So what is checked is that each step is an ATTEMPT and that the last
    one needs no display at all - not that some particular GPU is handled.
    """
    session = _read(RELEASE / "airootfs/usr/local/bin/zepos-live-session")
    surface = _read(RELEASE / "airootfs/usr/local/bin/zepos-live-surface")

    assert 'graphical_attempt ""' in session and 'graphical_attempt "pixman"' in session, (
        "the session makes only one attempt at a graphical surface")
    assert "console_attempt" in session, (
        "nothing runs the installer when no compositor comes up")
    assert "unset WAYLAND_DISPLAY DISPLAY" in session, (
        "the console fallback leaves a display variable set, so "
        "zepos-install would choose the graphical surface again")

    # The entry point, and not either surface directly: choosing between
    # them is its job, and a session that called installer.tui.app
    # itself would be a second implementation of spec §8.5.
    assert "zepos-install\n" in surface, (
        "the surface does not run the shipped entry point")
    for surface_module in ("installer.gui", "installer.tui", "zepos-install-gui"):
        assert surface_module not in session and surface_module not in surface, (
            f"{surface_module} is started directly; which surface runs is "
            f"/usr/bin/zepos-install's decision")


def test_the_installer_is_run_inside_a_terminal_so_the_fallback_is_visible():
    """The failure this catches has no symptom otherwise.

    If GTK4 cannot open a window inside a compositor that came up,
    /usr/bin/zepos-install prints why and starts the text interface - on
    the standard output it was given. Inside a bare compositor that is
    the journal, and the user is looking at an empty screen while a
    perfectly working installer waits for input nobody can give it.
    """
    surface_path = "usr/local/bin/zepos-live-surface"
    session = _read(RELEASE / "airootfs/usr/local/bin/zepos-live-session")
    assert re.search(rf"cage .*foot .*{re.escape(surface_path)}", session), (
        "the installer no longer runs inside a terminal inside the "
        "compositor; a GTK4 failure would happen on a blank screen")

    packages = {line.strip() for line in
                _read(RELEASE / "packages.x86_64").splitlines()
                if line.strip() and not line.startswith("#")}
    assert "foot" in packages, "the terminal the fallback appears in is not in the image"
    assert "cage" in packages, "no compositor is in the image"


def test_the_image_carries_the_installer_and_not_the_desktop():
    """Spec §4.2: the three installer packages are in the ISO and nowhere
    else, and what a ZepOS system is made of is what gets INSTALLED.

    An image that also unpacked zepos-desktop into itself would be
    carrying a copy of the system it installs, from a second source, at
    twice the download size.
    """
    packages = {line.strip() for line in
                _read(RELEASE / "packages.x86_64").splitlines()
                if line.strip() and not line.startswith("#")}

    for needed in ("zepos-installer", "zepos-installer-gui",
                   "zepos-installer-tui", "zepos-keyring"):
        assert needed in packages, f"{needed} is not in the shipping image"

    for absent in ("zepos-desktop", "zepos-config", "waybar",
                   "aylurs-gtk-shell", "zepos-hyprbars"):
        assert absent not in packages, (
            f"{absent} is part of what ZepOS INSTALLS, not of the medium "
            f"that installs it")

    # linux-firmware is the one package the harness leaves out on purpose
    # and this image cannot: a virtio guest needs no device firmware, and
    # the laptop this medium is booted on needs it before its wireless
    # adapter exists at all - which is the adapter spec §8.4 hangs the
    # offline fallback on.
    assert "linux-firmware" in packages, (
        "the medium carries no device firmware; on real hardware that is "
        "a machine with no wireless")

    assert len(packages) == len(set(packages)), "duplicate package entries"


def test_the_medium_can_reach_a_package_repository_before_it_installs():
    """Two things have to happen before pacstrap runs, and neither is the
    installer's job.

    The live medium's /etc/pacman.conf comes from the `pacman` package and
    points at a mirrorlist whose every server is commented out, so there
    is no Arch repository at all until something writes one. And
    mkarchiso builds with `pacstrap -G`, so there is no pacman keyring
    either, and spec §8.6's signatures could not be checked against
    anything.
    """
    prepare = _read(RELEASE / "airootfs/usr/local/bin/zepos-live-prepare")
    unit = _read(RELEASE / "airootfs/etc/systemd/system/zepos-live-prepare.service")
    build = _read(ISO / "build.sh")

    assert "SNAPSHOT_FILE=/usr/local/share/zepos-install/ala-snapshot" in prepare
    assert "archive.archlinux.org/repos/%s" in prepare, (
        "the mirrorlist is not written from the pinned snapshot (spec §8.7)")
    assert "usr/local/share/zepos-install/ala-snapshot" in build, (
        "nothing puts the pin into the image for it to be read from")

    assert "pacman-key --init" in prepare and "pacman-key --populate" in prepare, (
        "the medium never initialises a keyring, so every package an "
        "installation fetches is refused")

    assert "Before=zepos-install.service" in unit, (
        "the preparation is not ordered before the installer, so a user "
        "can reach the point of no return before the keyring exists")


def test_the_medium_does_not_abort_an_installation_on_a_slow_archive():
    """Measured on 11.08.2026, four minutes into an installation from
    this medium:

        error: failed retrieving file
        'linux-firmware-mediatek-20260622-1-any.pkg.tar.zst'
        from archive.archlinux.org : Operation too slow
        ==> ERROR: Failed to install packages to new root

    pacman gives up on a transfer that moves less than a byte per second
    for ten seconds and fails the WHOLE transaction. That default is
    written for a mirrorlist with somewhere else to go; the mirrorlist
    this medium writes two lines further up has exactly one server in
    it, and it is a rate-limited archive.

    The switch has to be in the LIVE /etc/pacman.conf, because that is
    the file pacstrap runs with (`pacstrap -C /etc/pacman.conf`) - not in
    the profile's pacman.conf, which only ever configured mkarchiso.
    """
    prepare = _read(RELEASE / "airootfs/usr/local/bin/zepos-live-prepare")
    # Comments stripped, because the reason this is here is written at
    # length in the header and a plain `in prepare` would be satisfied by
    # the prose alone. Measured: deleting the sed line left this test
    # green until the stripping was added.
    code = "\n".join(
        line for line in prepare.splitlines()
        if not line.lstrip().startswith("#")
    )

    # The whole line, not a substring of it: "/etc/pacman.conf.zepos"
    # contains "/etc/pacman.conf", and a substring check passed a script
    # that wrote the switch into a file pacstrap never opens.
    assert "PACMAN_CONF=/etc/pacman.conf" in code.splitlines(), (
        "the switch is aimed at some other file than the one pacstrap reads")
    assert "DisableDownloadTimeout" in code, (
        "a ten-second stall of archive.archlinux.org still ends the "
        "installation and discards a half-written disk")
    assert r"0,/^\[options\]/s//[options]\nDisableDownloadTimeout/" in code, (
        "the switch is not inserted into the [options] section - pacman "
        "ignores a setting that stands above every header, and a setting "
        "that is ignored looks exactly like one that is present")


def test_the_medium_speaks_one_language_before_it_has_asked():
    """The graphical surface defaults to German - PageState.language -
    and the text surface derives its first catalogue from the
    environment. Measured on the first medium that had both: the GUI
    asked "Sprache waehlen" and the TUI asked "Select language", on one
    image, depending only on which surface came up.

    LC_MESSAGES rather than LANG, and the locale generated rather than
    merely declared: the two halves are in different files and neither
    works alone, which is what this test is for.
    """
    unit = _read(RELEASE / "airootfs/etc/systemd/system/zepos-install.service")
    prepare = _read(RELEASE / "airootfs/usr/local/bin/zepos-live-prepare")
    locale_conf = _read(HARNESS / "airootfs/etc/locale.conf")

    assert "Environment=LC_MESSAGES=de_DE.UTF-8" in unit, (
        "the text interface would ask its first question in English on a "
        "medium whose graphical interface asks it in German")
    assert "locale-gen" in prepare and "LOCALE=de_DE.UTF-8" in prepare, (
        "the locale LC_MESSAGES names is never generated; GTK prints "
        "'Locale not supported by C library' above the first question")
    assert "LANG=C.UTF-8" in locale_conf, (
        "LC_CTYPE is no longer C.UTF-8; an unsupported one turns every "
        "umlaut in the text interface into a question mark")


def test_the_medium_types_on_the_keyboard_it_asks_questions_in():
    """MEASURED, before this existed: `xyz-abc`, sent as the key
    POSITIONS a German board needs for it, arrived in the installer's
    password field as `xzy/abc`. Every key produced what a US board
    produces.

    /etc/vconsole.conf's KEYMAP=de is loaded into the KERNEL's keymap by
    systemd-vconsole-setup and governs the console; a Wayland compositor
    never reads it. wlroots builds its keymap through libxkbcommon out of
    the XKB_DEFAULT_* variables, and with none of them set it takes
    libxkbcommon's compiled-in default, which is `us`.

    Why it is worse than cosmetic: the field is masked, both password
    fields agree with each other, and the installation completes. What
    the user gets is an account they cannot log into, on `y z - _ / : ; =
    +` and every shifted digit, with nothing anywhere reporting it.

    Both halves are asserted, because neither works alone - the console
    keymap for the text fallback, the XKB variable for the compositor.
    """
    session = _read(RELEASE / "airootfs/usr/local/bin/zepos-live-session")
    vconsole = _read(HARNESS / "airootfs/etc/vconsole.conf")

    assert "export XKB_DEFAULT_LAYOUT" in session, (
        "nothing sets XKB_DEFAULT_LAYOUT, so cage takes libxkbcommon's "
        "compiled-in `us` and the German installer asks for a password "
        "on a US keyboard")
    # Set BEFORE the compositor, which is the only moment it can be read:
    # wlroots builds the keymap once, at startup, and offers no way to
    # change a seat's layout afterwards.
    assert session.index("export XKB_DEFAULT_LAYOUT") < session.index("cage --"), (
        "XKB_DEFAULT_LAYOUT is exported after cage has already started, "
        "which is too late for it to be read at all")
    assert re.search(r"^\s*de\*\)\s*XKB_DEFAULT_LAYOUT=de", session, re.M)
    assert re.search(r"^\s*\*\)\s*XKB_DEFAULT_LAYOUT=de", session, re.M), (
        "the fallback for an unknown session language is not `de`; "
        "guessing `us` restores the defect this exists to remove")
    assert "KEYMAP=de" in vconsole, (
        "the console keymap is gone, so the TEXT fallback - the one path "
        "that always typed correctly - now types on a US board")


def test_the_harness_types_through_the_layout_the_medium_loads():
    """A qcode is a POSITION, so the table has to match what the guest
    thinks that position means. The medium now loads `de` inside the
    compositor as well as on the console, and a harness still typing
    through the US table would send `xyz-abc` and produce `xzy/abc` -
    reporting a defect that had just been fixed.
    """
    harness = _read(ISO / "test-boot.py")

    # Die Liste ist am 17.08.2026 um "release-install-ohne-netz"
    # gewachsen - den Lauf, der dasselbe Medium ohne Netzwerkkarte
    # faehrt. Er tippt dieselben Namen und Passwoerter wie die anderen,
    # also gilt fuer ihn dieselbe Aussage, und ein "us" waere hier
    # genauso falsch wie dort. Gemessen wird unveraendert: JEDER Lauf,
    # der Tasten drueckt, tippt durch die Belegung, die das Medium
    # laedt.
    assert re.search(
        r'RELEASE_LAYOUT = \{"release": "de", "release-install": "de",\s*'
        r'"release-install-ohne-netz": "de",\s*'
        r'"release-installed": "de"\}', harness), (
        "the harness no longer types through the layout the medium loads")
    assert 'shot:06-tastatur-xyz-abc' in harness, (
        "the release run no longer photographs a typed string, so the "
        "keyboard is asserted and not measured")


@pytest.mark.parametrize("path", [
    "usr/local/bin/zepos-live-prepare",
    "usr/local/bin/zepos-live-session",
    "usr/local/bin/zepos-live-surface",
])
def test_every_script_in_the_shipping_profile_is_declared_executable(path):
    """mkarchiso's copy is `cp -af --no-preserve=ownership,mode`, so the
    mode in git is discarded and everything arrives 0644. On this image
    the failure is a systemd unit exiting 126 and a black screen where the
    installer should be."""
    text = _read(RELEASE / "profiledef.sh")
    body = re.search(r"file_permissions=\((.*?)\n\)", text, re.S)
    assert body, "profiledef.sh has no file_permissions array"
    declared = dict(re.findall(r'\["([^"]+)"\]="([^"]+)"', body.group(1)))

    assert f"/{path}" in declared, f"/{path} would be installed 0644"
    assert declared[f"/{path}"].endswith("755")


def test_nothing_a_package_owns_is_declared_in_file_permissions():
    """file_permissions is applied BEFORE pacstrap, and mkarchiso does not
    skip an entry whose file does not exist yet - it stops the build with
    "Cannot change permissions of ... The file or directory does not
    exist." /usr/bin/zepos-install is the obvious one to get wrong here:
    it is the command this whole image is for, and it arrives with a
    package."""
    declared = _read(RELEASE / "profiledef.sh")
    for owned in ("/usr/bin/zepos-install", "/usr/bin/cage", "/usr/bin/foot"):
        assert f'["{owned}"]' not in declared, (
            f"{owned} comes from a package; naming it in file_permissions "
            f"stops the build before pacstrap has created it")


def test_the_two_images_are_pinned_to_the_same_snapshot():
    """The shipping medium installs the system the smoke image measured.

    It does that by sharing one pacman.conf rather than by two files
    agreeing, which is why this test is about the SHARED LIST: the moment
    the shipping profile grows a pacman.conf of its own, the pin is two
    numbers that can drift, and the image somebody downloads is no longer
    the image that was tested.
    """
    assert "pacman.conf" in shared_entries(), (
        "the shipping image does not share the harness's pacman.conf")
    assert not (RELEASE / "pacman.conf").exists(), (
        "the shipping profile has a pacman.conf of its own; there are now "
        "two pins")

    pinned = re.findall(
        r"^Server = https://archive\.archlinux\.org/repos/(\d{4}/\d{2}/\d{2})/",
        _read(HARNESS / "pacman.conf"), re.M)
    assert len(set(pinned)) == 1 and len(pinned) == 2


def test_the_build_assembles_the_shipping_profile_and_never_copies_it():
    """The one line of iso/build.sh this whole arrangement rests on.

    Shared files first, iso/profile-release/ over the top. A build that
    rsynced iso/profile/ wholesale and then deleted things would put the
    burden of remembering on whoever adds the next harness file.
    """
    build = _read(ISO / "build.sh")

    assert "--files-from=" in build and "SHARED_LIST" in build, (
        "the shipping profile is not assembled from the shared list")
    shared_at = build.index('rsync -a --files-from="$shared_files"')
    release_at = build.index('rsync -a --exclude \'__pycache__\' "$RELEASE_PROFILE"/')
    assert shared_at < release_at, (
        "the shared files are copied over the release profile, so the "
        "harness would win every collision")

    # And the build's own check against the tree it actually produced,
    # which is the only place a package's autologin drop-in or a
    # mis-assembled profile could still be caught.
    assert "the harness leaked into the image" in build, (
        "the build does not check the root it built for harness files")
    assert "in /etc/shadow has a usable password" in build, (
        "the build does not check the root it built for credentials")
