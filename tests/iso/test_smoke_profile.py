# SPDX-License-Identifier: GPL-3.0-or-later
"""The smoke ISO profile, checked without building a gigabyte.

WHY THESE TESTS EXIST
    Every assertion here corresponds to a way the first boots of this
    image actually failed. Each one cost a full build-and-boot cycle to
    find, and every one of them was invisible in the profile source:

      * mkarchiso copies airootfs with `--no-preserve=mode`, so an
        executable that is not named in file_permissions arrives at 0644.
        `zepos-generate --all` returned 126 and the session never
        started.
      * the live user's uid is written in two files - as a number in
        profiledef.sh, as an account in sysusers.d - and nothing but
        agreement between them makes /home/zepos writable.
      * the guest and the host agree on a marker string and a device
        node. Change one side and the harness waits for a line that is
        never printed.

    None of that can be caught by building the ISO in CI either: the
    build takes minutes and a gigabyte. It can be caught by reading the
    profile, which is what this file does.

WHAT IT DELIBERATELY DOES NOT DO
    It does not build or boot anything. `./iso/build.sh` and
    `./iso/test-boot.py` are the tools for that, and they are meant to
    be run by a person looking at the result.
"""
import json
import re
from pathlib import Path

import pytest

ISO = Path(__file__).resolve().parents[2] / "iso"
PROFILE = ISO / "profile"
AIROOTFS = PROFILE / "airootfs"

# The live user, spelled once here and asserted to be spelled the same in
# every file that names it.
USER = "zepos"
UID = "1000"


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing from the profile"
    return path.read_text(encoding="utf-8")


def _file_permissions() -> dict[str, str]:
    """The file_permissions array of profiledef.sh, as a dictionary.

    Parsed rather than sourced: sourcing would run a shell script from
    the repository inside the test process, which the suite's isolation
    guard exists to prevent.
    """
    text = _read(PROFILE / "profiledef.sh")
    body = re.search(r"file_permissions=\((.*?)\n\)", text, re.S)
    assert body, "profiledef.sh has no file_permissions array"
    return dict(re.findall(r'\["([^"]+)"\]="([^"]+)"', body.group(1)))


# --------------------------------------------------------------------
# The executable bit
# --------------------------------------------------------------------

def test_everything_executable_in_the_profile_is_declared():
    """A script in airootfs that is not in file_permissions is a 0644 file.

    mkarchiso's copy is `cp -af --no-preserve=ownership,mode`, so the
    mode in git is discarded. The failure is silent until something tries
    to run the file, and then it is exit 126 with no explanation.
    """
    declared = _file_permissions()
    for path in sorted(AIROOTFS.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if not path.stat().st_mode & 0o111:
            continue
        target = "/" + str(path.relative_to(AIROOTFS))
        assert target in declared, (
            f"{target} is executable in the profile but not in "
            f"file_permissions - mkarchiso will install it 0644 and "
            f"whatever runs it will get exit 126")
        assert declared[target].endswith("755"), (
            f"{target} is declared {declared[target]}, which is not executable")


def test_the_commands_the_live_session_runs_are_installed_by_a_package():
    """The three ZepOS commands used to be copied into the profile by
    iso/build.sh and declared 755 here. zepos-config installs them now,
    and the assertion that replaced the declaration stands in two places:

      * that the package installs them executable -
        tests/packaging/test_recipes.py, against the PKGBUILD;
      * that they are NOT in file_permissions any more - here, because
        this is the file that would be wrong.

    The second half is not tidiness. file_permissions is applied BEFORE
    pacstrap, and mkarchiso does not skip an entry whose file does not
    exist yet - it stops the build with

        Cannot change permissions of '.../usr/bin/zepos-generate'.
        The file or directory does not exist.

    So putting them back would not be redundant, it would stop every
    image build.
    """
    declared = _file_permissions()
    packages = {line.strip() for line in
                _read(PROFILE / "packages.x86_64").splitlines()
                if line.strip() and not line.startswith("#")}

    assert "zepos-config" in packages, (
        "nothing installs the three ZepOS commands into the image")

    for command in ("zepos-generate", "zepos-settings", "zepos-doctor"):
        assert f"/usr/bin/{command}" not in declared, (
            f"/usr/bin/{command} comes from zepos-config now; naming it in "
            f"file_permissions makes mkarchiso stop before pacstrap has "
            f"created it")


def test_the_generator_may_execute_itself():
    """generate_config.sh runs its own path, and start-hyprland runs it.

    Both are direct execution rather than `bash <file>`, so the mode
    matters. src/generate_config.sh:335 calls "$SELF" for every target's
    post-generation step. The mode is set by the zepos-config package -
    tests/packaging/test_recipes.py holds the recipe to it - and for the
    reason above it must no longer appear in file_permissions.
    """
    declared = _file_permissions()
    assert "/usr/share/zepos/generate_config.sh" not in declared, (
        "the generator is installed by zepos-config; file_permissions is "
        "applied before pacstrap and would stop the build")
    assert '"$SELF" --post' in (ISO.parent / "src" / "generate_config.sh").read_text(), \
        "the generator no longer executes itself; this test now guards nothing"


def test_the_repository_the_image_installs_from_is_signed_by_default():
    """Spec §8.6: signatures from the first ISO, because a repository
    that starts unsigned makes every already-installed system import a
    key by hand on the day it stops being unsigned.

    The committed profile says Required. iso/build.sh relaxes it in its
    working copy - loudly, on stderr - only when packaging/build.sh was
    run with --no-sign, so an unsigned image is possible and never
    accidental.
    """
    pacman_conf = _read(PROFILE / "pacman.conf")
    section = pacman_conf[pacman_conf.index("[zepos]"):]
    assert re.search(r"^SigLevel = Required\b", section, re.M), (
        "the ZepOS repository section does not require signatures")
    assert "pacman-key --lsign-key" in _read(ISO / "build.sh"), (
        "nothing tells the build container to trust the repository key; "
        "pacstrap verifies against ITS keyring, not one in the image")


# --------------------------------------------------------------------
# The live user
# --------------------------------------------------------------------

def test_the_uid_is_the_same_number_in_both_files():
    """profiledef.sh chowns /home/zepos numerically, before the user exists.

    It has to: file_permissions is applied before pacstrap, and the
    account is created by systemd-sysusers during it. The two numbers
    agreeing is the only thing that makes the home directory writable by
    the account that logs into it.
    """
    sysusers = _read(AIROOTFS / "etc/sysusers.d/zepos.conf")
    declared = _file_permissions()

    match = re.search(rf"^u\s+{USER}\s+(\d+)\b", sysusers, re.M)
    assert match, "sysusers.d/zepos.conf does not create the live user"
    assert match.group(1) == UID

    owner = declared[f"/home/{USER}"].split(":")[0]
    assert owner == UID, (
        f"/home/{USER} is chowned to uid {owner} but the account is "
        f"created with uid {match.group(1)}")


def test_the_autologin_names_the_account_that_exists():
    """agetty --autologin <name> against a name nothing creates is a
    login prompt on an image with no keyboard attached."""
    unit = _read(AIROOTFS / "etc/systemd/system/getty@tty1.service.d/autologin.conf")
    assert f"--autologin {USER}" in unit
    assert f"u {USER} " in _read(AIROOTFS / "etc/sysusers.d/zepos.conf")


@pytest.mark.parametrize("group, device", [
    ("uucp", "/dev/ttyS0"),
    ("disk", "/dev/vda"),
    ("systemd-journal", "journalctl -b"),
])
def test_the_user_may_reach_the_channels_the_evidence_leaves_through(group, device):
    """Both evidence channels are root-owned devices on Arch.

    Measured on a run that reached the autologin and then went silent for
    ten minutes: every progress line was dropped by a permission error
    the script's own 2>/dev/null swallowed, and the evidence disk would
    have failed the same way.
    """
    sysusers = _read(AIROOTFS / "etc/sysusers.d/zepos.conf")
    assert re.search(rf"^m\s+{USER}\s+{re.escape(group)}\s*$", sysusers, re.M), (
        f"the live user is not in {group}, so it cannot use {device}")


# --------------------------------------------------------------------
# The two halves of the harness have to agree
# --------------------------------------------------------------------

def test_guest_and_host_agree_on_the_completion_marker():
    """The host polls for a string the guest prints. One string."""
    harness = _read(ISO / "test-boot.py")
    collector = _read(AIROOTFS / "usr/local/bin/zepos-smoke-collect")

    assert 'PREFIX = "ZEPOS-SMOKE:"' in harness
    assert 'DONE = f"{PREFIX} DONE"' in harness
    assert 'say "DONE"' in collector, (
        "the collector no longer prints the line test-boot.py waits for; "
        "a run would report a timeout on a session that came up")


def test_guest_and_host_agree_on_the_evidence_device():
    """The guest writes a tar onto a block device the host attaches.

    This used to be `DISK=/dev/vda` on the guest side and "exactly one
    -drive on the command line" on the host side, which is an agreement
    about ENUMERATION ORDER: it holds only while there is one virtio
    disk. The installation scenario attaches a second one, and the
    installed system boots with the target disk present as well - so a
    positional name is now either the evidence disk or somebody's root
    filesystem, depending on how the guest happened to probe the bus.
    `tar cf` onto the second of those destroys the system whose first
    boot is being measured, after the measurement had succeeded.

    The agreement is therefore about a NAME the host chooses and udev
    reproduces: virtio-blk's `serial=` becomes
    /dev/disk/by-id/virtio-<serial>.
    """
    harness = _read(ISO / "test-boot.py")
    collector = _read(AIROOTFS / "usr/local/bin/zepos-smoke-collect")
    installer = _read(AIROOTFS / "usr/local/bin/zepos-install-unattended")

    assert 'EVIDENCE_SERIAL = "zepos-evidence"' in harness
    assert 'TARGET_SERIAL = "zepos-target"' in harness
    assert "serial={EVIDENCE_SERIAL}" in harness
    assert "serial={TARGET_SERIAL}" in harness

    assert "DISK=/dev/disk/by-id/virtio-zepos-evidence" in collector
    assert "EVIDENCE_DISK=/dev/disk/by-id/virtio-zepos-evidence" in installer
    assert "TARGET_DISK=/dev/disk/by-id/virtio-zepos-target" in installer


def test_no_script_in_the_image_writes_to_a_positional_disk_node():
    """The rule the test above exists to keep, stated as a rule.

    /dev/vda on the installed system is whichever virtio disk the kernel
    enumerated first, and one of the two is the root filesystem. There is
    no fallback to it anywhere, deliberately: a missing evidence disk
    costs a run its evidence, which the serial log survives; a fallback
    to a positional node costs somebody their filesystem.
    """
    for script in ("zepos-smoke", "zepos-smoke-collect", "zepos-install-unattended"):
        # Comments excluded on purpose: each of these three explains what
        # /dev/vda used to be and why it stopped being safe, and that
        # explanation is the reason the rule is followed rather than
        # rediscovered.
        code = [line for line in _read(AIROOTFS / "usr/local/bin" / script).splitlines()
                if not line.lstrip().startswith("#")]
        offenders = [line for line in code if "/dev/vd" in line]
        assert not offenders, (
            f"{script} names a positional block device; with two disks "
            f"attached that is a coin flip between the evidence disk and "
            f"the system disk: {offenders}")


def test_guest_and_host_agree_on_which_run_this_is():
    """The guest decides which of the runs this is by looking at the
    machine it woke up on, because nothing else can tell it: the ISO is
    one image, an installed system boots its own kernel, and a bootloader
    menu is not something an unattended run can answer.

    An installation happens exactly when there is a disk to install onto,
    which is the honest discriminator - and the /run/archiso half is what
    stops the INSTALLED system, which boots from a disk carrying that
    same serial and runs this same script, from reinstalling itself on
    every boot.

    The update run is the same idiom one disk further on, and it needs
    the OPPOSITE half of the /run/archiso test: it happens after the
    medium is gone.
    """
    harness = _read(ISO / "test-boot.py")
    smoke = _read(AIROOTFS / "usr/local/bin/zepos-smoke")
    update = _read(AIROOTFS / "usr/local/bin/zepos-smoke-update")

    assert "-b /dev/disk/by-id/virtio-zepos-target" in smoke
    assert "-e /run/archiso" in smoke, (
        "nothing stops the installed system from seeing its own root disk "
        "and deciding an installation was wanted")

    assert "-b /dev/disk/by-id/virtio-zepos-update" in smoke, (
        "the session would come up during an update run and compete with "
        "pacman for the machine")
    assert "UPDATE_DISK=/dev/disk/by-id/virtio-zepos-update" in update
    assert "-e /run/archiso" in update, (
        "the update probe does not refuse the live medium; it would "
        "rewrite the pacman.conf an installation is being performed with")

    # The host attaches the target disk for every scenario that has one,
    # and the update disk only for the scenario that is an update.
    assert 'if arguments.scenario in ("install", "installed", "update")' in harness
    assert 'if arguments.scenario == "update":' in harness


def test_the_run_asks_whether_the_ags_layer_came_up():
    """Fifteen templates generate AGS widgets, and before aylurs-gtk-shell
    was packaged not one of them had ever been executed by the program
    they are written for - the first boot of this image had no AGS at all
    and could only say so.

    The probe is `ags request calendar` rather than a process check for
    the same reason the session probe is `hyprctl monitors` and not
    pgrep: a gjs process that started and then failed on an import is
    still a running process. It also has to come BEFORE the layer probe,
    because the widgets are created hidden - a `hyprctl layers` taken
    first would show a working AGS as an empty screen.
    """
    collector = _read(AIROOTFS / "usr/local/bin/zepos-smoke-collect")

    assert "ags request calendar" in collector, "nothing asks AGS anything"
    assert "ags=$ags_status" in collector, (
        "the result line does not report whether AGS came up")

    probe = collector.index("ags request calendar")
    layers = collector.index('for probe in version monitors')
    assert probe < layers, (
        "the AGS widget is toggled after the layer list is taken, so the "
        "layer it maps cannot appear in it")


def test_the_harness_grades_on_what_the_guest_said():
    """test-boot.py exits 0 on the marker the guest itself printed, and
    on nothing else - not on QEMU's exit code, not on a screenshot that
    looks right.

    These assertions used to sit at the bottom of the AGS test above,
    under a second docstring and after its last assert, which is where a
    lost `def` line puts them. They are a test of their own and are one
    now.

    The marker is per scenario since the harness grew two more of them:
    `session=up` for the two that measure a desktop, `install=0` for the
    one that measures an installation. What must not happen is a harness
    that grades on something other than the guest's own summary.
    """
    harness = _read(ISO / "test-boot.py")
    collector = _read(AIROOTFS / "usr/local/bin/zepos-smoke-collect")

    assert 'return 0 if scenario["pass"] in result_line else 1' in harness
    assert re.search(r'"session":\s*\{[^}]*"pass":\s*"session=up"', harness, re.S), (
        "the session scenario no longer grades on session=up")
    assert re.search(r'"install":\s*\{[^}]*"pass":\s*"install=0"', harness, re.S), (
        "the installation scenario no longer grades on the installer's "
        "own return code")
    assert re.search(r'"installed":\s*\{[^}]*"pass":\s*"session=up"', harness, re.S), (
        "booting the installed system is graded on something other than a "
        "session coming up on it")

    assert 'say "RESULT session=$status' in collector
    assert "status=up" in collector, \
        "the collector never sets the status the harness grades on"
    assert 'say "RESULT install=${install_rc}' in \
        _read(AIROOTFS / "usr/local/bin/zepos-install-unattended"), (
        "the installation run prints no summary the harness could grade")


def test_the_run_reports_both_halves_of_the_plugin_question():
    """`session=up ags=up` was true of an image with no plugins at all,
    and would have stayed true of one whose five objects were installed
    and refused. Two different failures, one appearance, so two probes:

      pluginlines   what the GENERATOR wrote. src/plugins.py emits a
                    `plugin =` line only for an object that was on the
                    machine when the file was written and drops the whole
                    block otherwise, so a count of zero is a plugins.conf
                    of nothing but comments - a valid Hyprland
                    configuration and a desktop with no plugins.

      plugins       what the COMPOSITOR accepted. A load line is a path;
                    whether the object behind it loads is decided at
                    dlopen, and a refusal there costs the feature and
                    nothing else. `hyprctl plugin list` names the ones it
                    holds, by the name each gave in its own pluginInit.
    """
    collector = _read(AIROOTFS / "usr/local/bin/zepos-smoke-collect")

    assert "hyprctl -j plugin list" in collector, (
        "nothing asks the compositor which plugins it loaded")
    assert "plugins=${plugins:-none}" in collector, (
        "the result line does not name the loaded plugins")
    assert "pluginlines=$plugin_lines" in collector, (
        "the result line does not say how many load lines the generated "
        "plugins.conf actually got")

    # And the third: what the compositor SAID about one it would not
    # take. Not read from hyprland.log - Hyprland's debug:disable_logs
    # defaults to true and the generated configuration does not turn it
    # off, so a refused plugin leaves no trace there. Measured: 41400 log
    # lines from a working run, 41249 of them aquamarine's trace, not one
    # mentioning a plugin. `hyprctl plugin load` answers directly.
    assert "hyprctl plugin load" in collector, (
        "nothing asks the compositor why it refused a plugin, and the log "
        "does not say")
    assert "plugin-refused.txt" in collector, (
        "the compositor's own words about a refused plugin are not kept")
    assert "refused=${refused:-none}" in collector, (
        "the result line does not name a plugin that was refused")


def test_the_verification_phase_reports_what_it_can_still_be_right_about():
    """`Hyprland --verify-config` returns 1 on every machine where the
    plugins work.

    Measured on the first boot with the five plugin packages installed:
    three `Invalid dispatcher` errors for hyprlaunch:toggle,
    hyprlaunch:helpers and hyprclipx:toggle, on a run whose `hyprctl
    binds` lists all three. --verify-config does not load plugins and
    cannot - handlePluginLoads() returns immediately when there is no
    plugin system, and there is none without a compositor - so the
    dispatchers do not exist while it parses.

    That makes rc=1 permanent, and a permanently failing check hides the
    next real error behind it. The count of config errors that are NOT
    about a plugin dispatcher is the one that can still move.
    """
    smoke = _read(AIROOTFS / "usr/local/bin/zepos-smoke")
    collector = _read(AIROOTFS / "usr/local/bin/zepos-smoke-collect")

    assert "rc.verify_other" in smoke, (
        "nothing separates the errors --verify-config can be right about "
        "from the ones it cannot")
    assert "grep -vc 'Invalid dispatcher'" in smoke, (
        "the plugin dispatcher errors are not the ones being excluded")
    assert "verifyother=${verify_other:-?}" in collector, (
        "the result line does not carry the number that can still move")


# --------------------------------------------------------------------
# The GPU-less machine
# --------------------------------------------------------------------

def test_the_software_gl_override_is_not_reintroduced():
    """LIBGL_ALWAYS_SOFTWARE is the obvious fix and it is the wrong one.

    Measured against two images that differed only in this line: with it
    set, aquamarine loses EGL_EXT_device_drm, cannot match its EGL device
    to the DRM node it opened, names no renderer at all and logs
    "Failed to update renderer state for Virtual-1" once per frame for
    the whole session. Without it Mesa falls back to kms_swrast on its
    own and reports "Renderer: llvmpipe".

    Both sessions come up, which is what makes this worth a test: adding
    the variable back would not break anything visibly, it would only
    make the compositor worse and the log useless.
    """
    # Comments are stripped first, on purpose: the script's header names
    # the variable and quotes the export it does NOT do, and that
    # explanation is the point of the whole section.
    code = [line for line in
            _read(AIROOTFS / "usr/local/bin/zepos-smoke").splitlines()
            if not line.lstrip().startswith("#")]

    for variable in ("LIBGL_ALWAYS_SOFTWARE", "WLR_RENDERER_ALLOW_SOFTWARE",
                     "GALLIUM_DRIVER"):
        offenders = [line for line in code if variable in line]
        assert not offenders, (
            f"{variable} is set again: {offenders}. See the measurement in "
            f"the script's own header and in iso/README.md")


# --------------------------------------------------------------------
# Reproducibility
# --------------------------------------------------------------------

def test_the_image_is_pinned_to_an_archive_snapshot():
    """Spec §8.7: two builds of one commit have to give one system.

    A mirrorlist makes the contents of the image a function of the day it
    was built, and a bug report against it is then not reproducible.
    """
    pacman_conf = _read(PROFILE / "pacman.conf")
    servers = re.findall(
        r"^Server = https://archive\.archlinux\.org/repos/(\d{4}/\d{2}/\d{2})/",
        pacman_conf, re.M)
    assert len(servers) == 2, "core and extra must both be pinned"
    assert len(set(servers)) == 1, (
        f"core and extra point at different snapshots: {servers}")
    assert "Include = /etc/pacman.d/mirrorlist" not in pacman_conf


def test_no_build_output_is_tracked():
    """A gigabyte of ISO in a commit is a repository nobody can clone."""
    ignored = _read(ISO.parent / ".gitignore")
    for pattern in ("iso/work/", "iso/out/", "*.iso"):
        assert pattern in ignored, f"{pattern} is not ignored"


# --------------------------------------------------------------------
# Things whose absence stops a boot outright
# --------------------------------------------------------------------

def test_the_interactive_first_boot_unit_is_masked():
    """mkarchiso sets machine-id to "uninitialized", so ConditionFirstBoot
    is true on every boot and systemd-firstboot asks a human for a
    timezone before sysinit.target.

    Measured: the first boot of this image stopped at that prompt and
    never reached the autologin. An image that runs without a keyboard
    has no business owning an interactive setup unit.
    """
    unit = AIROOTFS / "etc/systemd/system/systemd-firstboot.service"
    assert unit.is_symlink() and str(unit.readlink()) == "/dev/null", \
        "systemd-firstboot.service is not masked"

    # The files that answer what it would have asked, so that masking it
    # does not leave the machine undefined instead.
    for answer in ("etc/locale.conf", "etc/vconsole.conf", "etc/hostname"):
        assert (AIROOTFS / answer).exists(), f"{answer} is missing"
    assert (AIROOTFS / "etc/localtime").is_symlink()


def test_the_archiso_boot_hook_is_configured():
    """Without the archiso mkinitcpio hook the image does not boot at all:
    the initramfs cannot mount the squashfs it was booted from."""
    hooks = _read(AIROOTFS / "etc/mkinitcpio.conf.d/archiso.conf")
    line = next((l for l in hooks.splitlines() if l.startswith("HOOKS=")), "")
    assert "archiso" in line, f"no archiso hook in HOOKS: {line!r}"
    assert "archiso" in _read(AIROOTFS / "etc/mkinitcpio.d/linux.preset")


def test_both_boot_paths_carry_the_same_kernel_command_line():
    """The harness drives BIOS. A UEFI entry that drifts from it is a
    difference nobody would find, because nothing looks at it."""
    # syslinux puts the kernel on LINUX and its arguments on APPEND;
    # GRUB puts both on one `linux` line. The comparison is over the
    # arguments, so each format is read where its arguments are.
    def options(text: str, marker: str) -> set[str]:
        line = next(l for l in text.splitlines() if marker in l)
        return {word for word in line.split() if "=" in word}

    bios = options(_read(PROFILE / "syslinux/syslinux-linux.cfg"), "APPEND ")
    uefi = options(_read(PROFILE / "grub/grub.cfg"), "vmlinuz-linux")

    for console in ("console=tty0", "console=ttyS0,115200"):
        assert console in bios, f"{console} is missing from the BIOS entry"
        assert console in uefi, f"{console} is missing from the UEFI entry"


def test_the_installed_system_keeps_its_serial_console():
    """Die Kernel-Zeile des ZIELS, und sie ist der Kanal, ueber den ein
    erster Start berichtet, der die Sitzung nie erreicht.

    Bis zur Umstellung auf GRUB verteilte zepos-install-unattended sie
    ueber eine Schleife auf "$TARGET"/boot/loader/entries/*.conf, also
    systemd-boots Format. Seit installer/core/translate.py GRUB
    einrichtet, gibt es dieses Verzeichnis nicht mehr - die Schleife lief
    ins Leere, ohne ein Wort zu sagen, und nichts haette gemeldet, dass
    der naechste Start stumm ist.
    """
    script = _read(AIROOTFS / "usr/local/bin/zepos-install-unattended")
    # Ohne die Kommentarzeilen: die Begruendung, warum der alte Weg weg
    # ist, MUSS ihn nennen duerfen. Ein Waechter, der die Erklaerung
    # seiner eigenen Regel verbietet, wird umgangen, indem man die
    # Erklaerung loescht.
    code = "\n".join(line for line in script.splitlines()
                     if not line.lstrip().startswith("#"))

    assert "/boot/loader/entries" not in code, (
        "die Kernel-Zeile wird ueber systemd-boots Eintraege gesetzt; die "
        "gibt es im Ziel nicht mehr")
    assert "/etc/default/grub.d/99-zepos-smoke-serial.cfg" in script, (
        "kein GRUB-Drop-in fuer die serielle Konsole im Ziel")
    for console in ("console=tty0", "console=ttyS0,115200"):
        assert console in script, f"{console} fehlt auf der Kernel-Zeile des Ziels"

    # Und das Neuerzeugen, ohne das die Datei nur daliegt.
    assert re.search(r'arch-chroot "\$TARGET" grub-mkconfig -o /boot/grub/grub\.cfg',
                     script), (
        "grub.cfg im Ziel wird nicht neu erzeugt, also wirkt das Drop-in nie")


def test_the_packages_the_smoke_run_calls_are_in_the_image():
    """A command the run invokes and the image does not carry produces an
    empty log rather than an error anybody reads."""
    packages = {line.strip() for line in
                _read(PROFILE / "packages.x86_64").splitlines()
                if line.strip() and not line.startswith("#")}

    # zepos-hyprland: the thing under test. It was `hyprland` until the
    # compositor became a ZepOS package - spec §4.2 and the revision to
    # §7 - and the name is the whole point of that change: five plugin
    # packages are compiled against its headers and name it in their
    # dependencies, which they could not do against a package Arch moves.
    # grim: the compositor-side screenshot, which is half the evidence.
    # python and jq: the generator and the artifacts it writes. mesa: the
    # software rasteriser, without which there is no session on a
    # GPU-less VM.
    for needed in ("zepos-hyprland", "grim", "python", "jq", "mesa",
                   "aylurs-gtk-shell"):
        assert needed in packages, f"{needed} is not in packages.x86_64"

    # And not both. zepos-hyprland conflicts with the hyprland in extra,
    # so a profile naming the two would stop pacstrap rather than pick
    # one - twenty minutes into an image build.
    assert "hyprland" not in packages, (
        "the image installs both compositors; they conflict")

    assert len(packages) == len(set(packages)), "duplicate package entries"


def test_the_image_installs_the_keyring():
    """zepos-keyring is in this image for a reason a container cannot
    supply.

    It is the only ZepOS package with an install scriptlet, and the
    conditions that scriptlet was written for exist during a real
    pacstrap and nowhere else: mkarchiso passes -G, so the root being
    built has no pacman keyring at all. The scriptlet has to notice and
    skip - `pacman-key -l` fails on such a root - or this build stops
    with a scriptlet error instead of producing an image.
    """
    packages = {line.strip() for line in
                _read(PROFILE / "packages.x86_64").splitlines()
                if line.strip() and not line.startswith("#")}

    assert "zepos-keyring" in packages, (
        "the image does not install zepos-keyring, so its install "
        "scriptlet is never executed against a root with no keyring")


def test_the_logout_menu_is_no_longer_a_separate_package():
    """SUPER+M lived on its own package until Aufgabe 26 (19.08.2026);
    now it lives inside aylurs-gtk-shell, like every other AGS window.

    BIS ZUM 19.08.2026 stand hier dieselbe Zusicherung umgekehrt:
    "zepos-logout is ... the last of spec §4.3's missing components" und
    "the package being in the image is the only thing that makes the
    bind live". Beides galt fuer das C-Programm - hyprland-universal-
    config.template band SUPER+M unbedingt darauf, ohne Rueckfall
    (§7.4 schreibt einen nur fuer SUPER+SPACE vor). Das Programm ist mit
    Aufgabe 26 geloescht (Regel 14): sein Nachfolger,
    src/templates/ags-logout.template, ist ein Fenster IM bereits
    installierten AGS-Prozess - SUPER+M ruft seither `ags request
    logout` statt `exec zepos-logout` (siehe hyprland-universal-config.
    template), und aylurs-gtk-shell macht diese Taste schon lebendig -
    dasselbe Paket, dessen Anwesenheit im Bild
    test_the_packages_the_smoke_run_calls_are_in_the_image bereits
    verlangt.

    Und der Vorgaenger ist nicht bloss unerwaehnt, sondern weg. Ein
    zepos-logout NEBEN dem AGS-Fenster waere die Doppelung, die
    Aufgabe 26 an vier Stellen desselben Tages abgeraeumt hat - und
    wlogout bliebe aus demselben Grund verboten, den es schon vor dieser
    Aufgabe hatte: es zoege libgtk-3 herein.
    """
    packages = {line.strip() for line in
                _read(PROFILE / "packages.x86_64").splitlines()
                if line.strip() and not line.startswith("#")}

    assert "zepos-logout" not in packages, (
        "das Bild installiert weiterhin ein zepos-logout-Paket, das es "
        "nach Aufgabe 26 nicht mehr gibt")
    assert "wlogout" not in packages, (
        "das Bild installiert wlogout weiterhin und damit libgtk-3")

    hypr = _read(ISO.parent / "src" / "templates"
                / "hyprland-universal-config.template")
    binds = [line.strip() for line in hypr.splitlines()
             if line.strip().startswith("bind")]
    assert "bind = $mainMod, M, exec, ags request logout" in binds, (
        "SUPER+M ruft nicht mehr das AGS-Fenster auf")

    # UND DER SPERRBILDSCHIRM GEHOERT NICHT HIERHER, obwohl dieselbe
    # Vorlage SUPER+L genauso unbedingt darauf bindet.
    #
    # GEMESSEN am 12.08.2026: airootfs/etc/sysusers.d/zepos.conf legt das
    # Live-Konto mit `u zepos 1000 ...` an, also mit GESPERRTEM
    # Passwortfeld - autologin.conf daneben sagt genau das und begruendet
    # damit `agetty --autologin`. pam_unix kann gegen ein gesperrtes Feld
    # nicht abgleichen, und `nullok` erlaubt ein LEERES Feld, kein
    # gesperrtes.
    #
    # Ein Sperrbildschirm auf dem Medium wiese also jedes Passwort ab, und
    # weil ext-session-lock-v1 die Sitzung auch beim Absturz des
    # Sperrprogramms gesperrt LAESST, saesse der Nutzer bis zum harten
    # Neustart vor einem Installationsassistenten, an den er nicht mehr
    # herankommt. Eine tote Taste ist billiger.
    assert "zepos-lock" not in packages, (
        "das Bild installiert den Sperrbildschirm - das Live-Konto hat ein "
        "gesperrtes Passwortfeld, also wuerde SUPER+L den Nutzer aus dem "
        "Installationsassistenten aussperren, ohne Weg zurueck")

    sysusers = _read(PROFILE / "airootfs/etc/sysusers.d/zepos.conf")
    assert "u zepos 1000" in sysusers, (
        "das Live-Konto wird anders angelegt als angenommen - dann steht die "
        "Begruendung darueber auf einer Messung, die nicht mehr stimmt")

    # zepos-desktop is deliberately NOT here, and that has not changed:
    # it is what gets installed ONTO a target out of /opt/zepos-repo, and
    # an image that also unpacked it into itself would be measuring a
    # different machine from the one it produces.
    #
    # The three installer packages used to be excluded next to it, on the
    # grounds that this image existed only to find out whether a Hyprland
    # session comes up. That was true of the image and is no longer true
    # of it: it now performs an installation as well, and spec §4.2 puts
    # those three packages in the ISO and nowhere else. The exclusion
    # they belong to is the other one - out of zepos-desktop - and that
    # is asserted by tests/packaging/test_recipes.py and measured by
    # packaging/verify-install.sh's third container.
    assert "zepos-desktop" not in packages, (
        "zepos-desktop is in the image; it is what the image INSTALLS, "
        "not what the image is")


def test_the_repository_probe_counts_active_sources_only():
    """Measured on the first installed system ZepOS ever produced: the
    probe reported `file-urls=1` on a machine that has none.

    The hit was line 100 of pacman's own default configuration -

        # An example of a custom package repository. [...]
        #[custom]
        #SigLevel = Optional TrustAll
        #Server = file:///home/custompkgs

    - which is documentation, not a source. A count that says 1 when the
    answer is 0 cannot say anything when the answer is 1, and 1 is
    exactly the case spec §8.5b exists to catch.
    """
    counter = (
        "grep -cE "
        "'^[[:space:]]*Server[[:space:]]*=[[:space:]]*file://'"
    )
    for script in ("zepos-smoke-collect", "zepos-install-unattended"):
        text = _read(AIROOTFS / "usr/local/bin" / script)
        assert counter in text, (
            f"{script} counts every occurrence of file://, including the "
            f"commented example every pacman.conf ships")


def test_the_image_carries_the_installer():
    """Spec §4.2: "Die drei Installer-Pakete liegen nur in der ISO, nicht
    im installierten System."

    The half that had never been built. Three boots of this image had
    proved a desktop comes up and none of them could have installed
    anything, because /usr/bin/zepos-install was not on the medium - and
    neither was archinstall, which zepos-installer is what brings.

    All three packages, not only the core: §8.5's fallback from the GTK4
    surface to the text one is a decision taken at run time on the
    machine in front of the user, and an image carrying only one surface
    has made that decision at build time instead.
    """
    packages = {line.strip() for line in
                _read(PROFILE / "packages.x86_64").splitlines()
                if line.strip() and not line.startswith("#")}

    for needed in ("zepos-installer", "zepos-installer-gui", "zepos-installer-tui"):
        assert needed in packages, (
            f"{needed} is not in packages.x86_64; spec §4.2 puts the "
            f"installer in the ISO and nowhere else")


def test_the_image_carries_the_offline_repository():
    """Spec §8.4's second row, and the path is not this build's to pick.

    installer/core/source.py's OFFLINE_REPO_URL is
    `file:///opt/zepos-repo` and does NOT end in $arch, while
    ONLINE_REPO_URL does - so what goes to /opt/zepos-repo is the
    CONTENTS of packaging/out/x86_64/, not the directory above it.
    packaging/README.md recorded that when the layout was decided; this
    is the half of it that is built.

    Asserted against iso/build.sh rather than against the committed
    profile because packaging/out/ is a build artefact: a repository of
    signed packages in the source tree would be the largest thing in it
    and stale the day after it was added.
    """
    build = _read(ISO / "build.sh")

    assert 'airootfs/opt/zepos-repo' in build, (
        "the image does not carry an offline repository, so an "
        "installation from it can install no ZepOS package at all")
    assert re.search(r'rsync -a "\$PKG_REPO/x86_64"/ .*opt/zepos-repo', build), (
        "the offline repository is not built from the CONTENTS of "
        "packaging/out/x86_64/ - the URL has no $arch in it")

    # The URL the guest will actually be given, read out of the module
    # that owns it rather than repeated here.
    source = _read(ISO.parent / "installer/core/source.py")
    assert 'OFFLINE_REPO_URL = "file:///opt/zepos-repo"' in source


def test_the_live_environment_can_reach_a_package_repository():
    """Measured on the run of a4b03d8: systemd-networkd was started by
    systemd's own first-boot preset, brought `lo` up, and then had no
    .network file for the ethernet interface - the guest had no address,
    and `journalctl -b` contains not one DHCP line.

    Nothing noticed, because a session run needs no network. An
    installation does: pacstrap fetches the base system, and
    archinstall's sanity_check() waits WITHOUT A DEADLINE for
    `timedatectl` to report NTPSynchronized=yes, which never happens on a
    machine that cannot reach a time server.
    """
    network = _read(AIROOTFS / "etc/systemd/network/20-ethernet.network")
    assert "DHCP=yes" in network

    resolv = AIROOTFS / "etc/resolv.conf"
    assert resolv.is_symlink(), (
        "/etc/resolv.conf is not the systemd-resolved stub; the guest "
        "resolves no names and every mirror is unreachable by name")
    assert str(resolv.readlink()) == "/run/systemd/resolve/stub-resolv.conf"

    # And the mirrors themselves, which cannot be shipped as a file: the
    # `pacman-mirrorlist` package owns /etc/pacman.d/mirrorlist, and a
    # profile that ships one stops the build with "exists in filesystem".
    # So the pin travels as a plain file under /usr/local/share, which no
    # package claims, and the installation writes the mirrorlist from it.
    build = _read(ISO / "build.sh")
    driver = _read(AIROOTFS / "usr/local/bin/zepos-install-unattended")
    assert "usr/local/share/zepos-install/ala-snapshot" in build
    assert "SNAPSHOT_FILE=/usr/local/share/zepos-install/ala-snapshot" in driver
    assert "archive.archlinux.org/repos/%s" in driver, (
        "the live mirrorlist is not written from the pinned snapshot")


def test_the_unattended_installation_drives_the_shipped_entry_points():
    """README.md: "an unattended installation needs only a serialized
    model rather than a second code path - InstallConfig.from_dict() plus
    installer.core.runner.install() is the whole of it."

    A driver that assembled its own `archinstall` command line would test
    a command line that ships nowhere, and `--mountpoint` and `--offline`
    would then appear in no real installation at all - a wrong spelling
    of either kills every installation at the argument parser while every
    mocked test keeps passing. The same reasoning
    tests/integration/test_dry_run.sh already applies to the dry run.
    """
    driver = _read(AIROOTFS / "usr/local/bin/zepos-install-unattended")

    assert "InstallConfig.from_dict(data)" in driver
    assert "from installer.core.runner import" in driver
    assert re.search(r"^\s*code = install\($", driver, re.M), (
        "the driver does not call installer.core.runner.install()")
    assert "archinstall --config" not in driver and '"archinstall"' not in driver, (
        "the driver builds its own archinstall command line")

    # The serialized model itself, committed so that the run repeats.
    config = json.loads(
        _read(AIROOTFS / "usr/local/share/zepos-install/unattended-install.json"))
    assert config["schema_version"] == 1, (
        "InstallConfig.from_dict() refuses any other schema_version")
    assert config["users"], "an installation with no user account is refused"
    assert len(config["users"][0]["password"]) >= 8, (
        "validate() refuses a password shorter than MIN_PASSWORD_LENGTH")
    # The two fields the file cannot carry: which device the target disk
    # is, and how big it is. install() re-enumerates and compares both
    # immediately before the erase, so a guess would be refused.
    assert config["disk"]["device"] == "" and config["disk"]["size_bytes"] == 0, (
        "the committed configuration names a disk; the device and its "
        "size are facts about the machine and are filled in at run time")


def test_the_unattended_run_probes_the_package_source_like_the_real_one():
    """The one line that kept a shipping defect invisible.

    This driver used to pass `source=PackageSource.OFFLINE` explicitly.
    The comment above it was correct - nothing has ever been published to
    https://zeptronit.github.io/ZepOS - and the override was still the
    defect: `--scenario install` therefore took a branch the shipping
    medium has no way to take, so it passed for months while
    `--scenario release-install` could not get past `pacman -Syy`. The
    404 was found by driving the release image by hand, after the erase.

    probe() now asks the repository whose location it is deciding, so
    both media reach the same answer by the same route, and the day the
    repository is published both change together.
    """
    driver = _read(AIROOTFS / "usr/local/bin/zepos-install-unattended")
    # Comments excluded on purpose: the account of why the override was
    # removed names it, and that paragraph is the thing worth keeping.
    code = "\n".join(line for line in driver.splitlines()
                     if not line.lstrip().startswith("#"))

    assert "PackageSource.OFFLINE" not in code, (
        "the unattended run hard-codes its package source again, which is "
        "how the shipping medium's 404 stayed invisible")
    assert "from installer.core.source import probe" in driver
    assert re.search(r"^source = probe\(\)$", driver, re.M), (
        "the driver does not probe the package source")
    assert re.search(r"^\s*source=source,$", driver, re.M), (
        "the probed source is not what install() is given")
    assert "pkgsource=${pkgsource:-unknown}" in driver, (
        "the run does not report which source it took, so a silent switch "
        "back to a constant would look like every other passing run")


def test_the_installation_runs_as_root_and_the_session_stands_down():
    """archinstall requires root and says so before doing anything else,
    and this image has no sudo - `sudo` is not in packages.x86_64, and
    zepos-desktop, which would bring it, is what gets installed onto the
    TARGET.

    So the installation is a system service, and the tty1 session has to
    know to stay out of its way: two things competing for seat0 while a
    disk is being partitioned makes an unreadable failure out of a clean
    one.
    """
    unit = AIROOTFS / "etc/systemd/system/zepos-install-unattended.service"
    wants = (AIROOTFS / "etc/systemd/system/multi-user.target.wants"
             / "zepos-install-unattended.service")

    assert unit.is_file()
    assert wants.is_symlink(), "the service is never started"
    assert str(wants.readlink()).endswith("zepos-install-unattended.service")

    text = _read(unit)
    assert "ExecStart=/usr/local/bin/zepos-install-unattended" in text
    assert "TimeoutStartSec=infinity" in text, (
        "systemd would kill pacstrap mid-transaction and leave a "
        "half-installed target")

    smoke = _read(AIROOTFS / "usr/local/bin/zepos-smoke")
    assert "this session stands down" in smoke


# --------------------------------------------------------------------
# this profile is a test harness, and must stay one
# --------------------------------------------------------------------
#
# iso/profile/ is not a shipping image and was never meant to be. It
# autologs in, carries its own /etc/shadow, runs a collector that writes
# the session's state to a raw disk, and installs unattended from answers
# that include a root password in clear text.
#
# All of that is right for a smoke test and wrong for anything a person
# would be handed. The danger is not that someone decides to ship it - it
# is that the distinction lives nowhere except in a sentence at the top
# of build.sh, so a shipping profile could be grown out of this one a
# file at a time without any single step looking wrong.
#
# Written after the credential file reached a public repository. It was
# committed deliberately and it is a throwaway for a disposable VM, but
# nobody had checked what its mode would be inside the image, and nothing
# said where the harness ends.

CREDENTIAL_KEYS = ("password", "root_password", "encryption_password")


def test_no_credential_in_the_image_is_world_readable():
    """A password that ships inside the image is readable by every
    process on the live system, whatever it is for."""
    permissions = _file_permissions()
    offenders = []

    for path in sorted(AIROOTFS.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not any(f'"{key}"' in text for key in CREDENTIAL_KEYS):
            continue

        target = "/" + path.relative_to(AIROOTFS).as_posix()
        mode = permissions.get(target, "").rsplit(":", 1)[-1]
        # No entry means archiso's default, which is 0644.
        if not mode or mode[-3:] not in ("600", "400"):
            offenders.append(f"{target} -> {mode or '0644 (no entry)'}")

    assert offenders == [], (
        "these ship a credential inside the image at a mode others can "
        "read:\n  " + "\n  ".join(offenders))


def test_the_profile_says_it_is_a_test_harness():
    """The boundary, written down where someone extending this will read
    it.

    Asserted rather than trusted: the three files below are what make
    this a harness rather than an image, and a profile that still has
    them while calling itself a shipping image is the failure this
    guards.

    THE SECOND HALF, ADDED WHEN THE SHIPPING IMAGE WAS BUILT
        There are two profiles now, and this test's original form would
        have stayed green through the worst possible change to that
        arrangement: copying iso/profile/ to iso/profile-release/ and
        editing a name. The three files would still be here, which is all
        it asked.

        So it also asks the other question. Not "is a file called
        zepos-smoke absent over there" - a rename defeats that - but
        whether the CONTENT of any of these three has appeared in the
        shipping profile under any name at all, and whether the allow-list
        that decides what crosses over has been made to name them.

        The properties themselves - no autologin, no credential, no
        serial console, no evidence disk - are checked in
        tests/iso/test_release_profile.py, against every file the
        shipping image is assembled from. This is the boundary; that is
        the wall.
    """
    build = (ISO / "build.sh").read_text(encoding="utf-8")
    assert "smoke ISO" in build, (
        "build.sh no longer says what kind of image this is")

    harness = (
        "usr/local/bin/zepos-smoke",
        "usr/local/bin/zepos-install-unattended",
        "usr/local/share/zepos-install/unattended-install.json",
    )
    present = [name for name in harness if (AIROOTFS / name).is_file()]
    assert present == list(harness), (
        "the harness lost a piece; if this profile is becoming a shipping "
        f"image, that is the change to argue for explicitly: {present}")

    release = ISO / "profile-release"
    shared_list = ISO / "shared-with-release.txt"
    assert release.is_dir() and shared_list.is_file(), (
        "the shipping profile and the list of what it shares with this "
        "one are what keep the harness from becoming the image; neither "
        "may simply disappear")

    # By content, so that a copy under another name is still a copy.
    bodies = {(AIROOTFS / name).read_text(encoding="utf-8"): name for name in harness}
    for path in sorted(release.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert text not in bodies, (
            f"{path.relative_to(ISO)} is a copy of the harness's "
            f"{bodies[text]}. The shipping image is assembled from an "
            f"allow-list precisely so this does not happen by accident.")

    # And the allow-list itself, which is the one door between them.
    allowed = {re.sub(r"#.*", "", line).strip()
               for line in shared_list.read_text(encoding="utf-8").splitlines()}
    for name in harness:
        assert f"airootfs/{name}" not in allowed, (
            f"airootfs/{name} has been put on the shared list; the "
            f"shipping image would carry it")


# --------------------------------------------------------------------
# UP-1: die Sonde misst eine Aktualisierung, die von selbst passiert
# --------------------------------------------------------------------

def _uncommented(text: str) -> list[str]:
    """Die Zeilen ohne reine Kommentarzeilen.

    Die Sonde erklaert ausfuehrlich, was sie NICHT mehr tut - "die erste
    Fassung fuehrte pacman -Syu von Hand aus" steht in ihrem Kopf. Eine
    Suche im Wortlaut faende genau diese Erklaerung und meldete den
    Befehl als vorhanden.
    """
    return [line for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def test_the_update_probe_watches_instead_of_driving():
    """Die Frage von UP-1 ist nicht, ob eine Maschine aktualisiert werden
    KANN - das war die Frage der ersten Fassung, und sie ist beantwortet.
    Sie ist, ob es ohne Zutun passiert.

    Eine Sonde, die `pacman -Syu` oder `systemctl start zepos-update`
    aufruft, misst genau das nicht mehr. Erlaubt ist der eine Handgriff,
    der eine VOR UP-1 installierte Maschine ueberhaupt erst in den Besitz
    des Aktualisierers bringt.
    """
    probe = _uncommented(
        _read(AIROOTFS / "usr/local/bin/zepos-smoke-update"))
    body = "\n".join(probe)

    assert "pacman -Syu" not in body, (
        "die Sonde aktualisiert selbst - dann misst der Lauf den Kanal "
        "und nicht die Selbstaktualisierung")
    assert "systemctl start" not in body, (
        "die Sonde stoesst den Dienst an; ein Zeitgeber, der angestossen "
        "werden muss, ist keiner")
    assert "systemctl enable" not in body, (
        "die Sonde schaltet den Zeitgeber selbst ein - dann misst sie "
        "nicht mehr, ob der ALPM-Haken aus zepos-config das tut")

    # Genau ein installierender pacman-Aufruf, und der ist der Handgriff.
    installs = [line for line in probe
                if re.search(r"^\s*pacman -S(?!lq)\S* ", line)]
    assert len(installs) == 2, installs      # -Sy (Datenbank) und -S (Paket)
    assert any("$BOOTSTRAP_PACKAGE" in line for line in installs)


def test_the_update_probe_measures_what_the_machine_left_behind():
    """Gemessen wird an dem, was der Dienst ABLEGT, und an der
    Paketdatenbank - nicht an seiner Prosa. src/update.py sagt, warum:
    ein installiertes ZepOS ist deutsch, pacman ist uebersetzt, und ein
    grep gegen die Ausgabe eines uebersetzten Programms schlaegt nur auf
    der Maschine des Entwicklers an."""
    probe = _read(AIROOTFS / "usr/local/bin/zepos-smoke-update")

    assert "STATE=/var/lib/zepos/update-state.json" in probe
    assert "MARKER=/var/lib/zepos/regenerate-required" in probe
    assert "DROPIN=/etc/systemd/system/zepos-update.timer.d/10-zepos.conf" in probe
    # Die Gegenprobe: ohne Schluessel muss der Aktualisierer scheitern
    # UND es hinterlassen.
    assert "without_key_said" in probe
    assert "pacman-key --delete" in probe


def test_the_scenario_waits_longer_than_the_shipped_schedule(monkeypatch):
    """Der ausgelieferte Zeitplan ist OnBootSec=15min. Eine Frist, die
    kuerzer ist als das, was gemessen werden soll, misst nur die Frist -
    und ein Messstand, der seine eigene Zusicherung nicht abwarten kann,
    faellt an dem Tag um, an dem jemand den Zeitplan hoeher setzt."""
    harness = _read(ISO / "test-boot.py")
    probe = _read(AIROOTFS / "usr/local/bin/zepos-smoke-update")

    scenario = re.search(r'"update":\s*\{(.*?)\n    \}', harness, re.S)
    assert scenario, "the update scenario is gone from test-boot.py"
    timeout = int(re.search(r'"timeout":\s*(\d+)', scenario.group(1)).group(1))
    deadline = int(re.search(r"^DEADLINE=(\d+)", probe, re.M).group(1))

    # monkeypatch und nicht sys.path.insert: ein Eintrag, den dieser
    # Test stehen laesst, gilt fuer die ganze Sitzung. Gemessen genau so -
    # tests/src/test_placeholders.py stellt fest, dass ein
    # template_processor.py OHNE style_definition.py abbricht, und mit
    # src/ dauerhaft auf dem Suchpfad fand es die Datei doch und brach
    # nicht ab. Ein Test, der einen anderen umbringt, ist teurer als der,
    # den er misst.
    monkeypatch.syspath_prepend(str(ISO.parent / "src"))
    import update

    shipped = update.defaults()["schedule"]["on_boot"]
    assert shipped.endswith("min"), shipped
    seconds = int(shipped[:-3]) * 60

    assert deadline > seconds, (
        f"die Sonde gibt nach {deadline}s auf, der Zeitgeber feuert erst "
        f"nach {seconds}s")
    assert timeout > deadline, (
        f"der Messstand bricht nach {timeout}s ab, die Sonde wartet aber "
        f"bis zu {deadline}s und hat danach noch die Gegenprobe vor sich")
