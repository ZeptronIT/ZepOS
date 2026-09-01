# SPDX-License-Identifier: GPL-3.0-or-later
"""The isolation guard must actually bite.

A guard nobody verifies is a guard that silently stopped working.
"""
from __future__ import annotations

import io
import multiprocessing
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

import conftest

_REAL_RUN = subprocess.run


def test_subprocess_run_is_blocked():
    with pytest.raises(RuntimeError, match="real process"):
        subprocess.run(["true"])


def test_popen_is_blocked():
    with pytest.raises(RuntimeError, match="real process"):
        subprocess.Popen(["true"])


def test_os_system_is_blocked():
    with pytest.raises(RuntimeError, match="real process"):
        os.system("true")


def test_writing_into_etc_is_blocked():
    target = pathlib.Path("/etc/NetworkManager/system-connections/boom.nmconnection")
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        target.write_text("kaputt")


def test_creating_a_directory_under_etc_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        pathlib.Path("/etc/NetworkManager/system-connections").mkdir(parents=True)


def test_opening_a_system_file_for_writing_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        pathlib.Path("/etc/hosts").open("w")


def test_reading_a_system_file_still_works():
    """Only write access is blocked — reading must continue to work."""
    assert pathlib.Path("/etc/hostname").exists()


def test_tmp_path_is_writable(tmp_path):
    target = tmp_path / "etc" / "NetworkManager" / "x.nmconnection"
    target.parent.mkdir(parents=True)
    target.write_text("ok")
    assert target.read_text() == "ok"


@pytest.mark.allow_subprocess
def test_opt_in_marker_restores_subprocess():
    result = subprocess.run(["true"], capture_output=True)
    assert result.returncode == 0

def test_guard_survives_a_default_bound_runner():
    """Defense in depth.

    A function written as `def f(*, runner=subprocess.run)` captures the
    real subprocess.run at import time, so patching subprocess.run alone
    would not stop it. The guard also patches Popen, which the real
    subprocess.run looks up at call time - so the escape is closed anyway.

    Production code resolves its runner at call time instead of binding a
    default, but this test makes sure the backstop is not silently lost.
    """
    captured_at_import = _REAL_RUN

    def with_default_binding(*, runner=captured_at_import):
        return runner(["true"], capture_output=True)

    with pytest.raises(RuntimeError, match="real process"):
        with_default_binding()


def test_os_open_for_writing_is_blocked():
    """os.open bypasses every pathlib patch.

    A proposed fix in Task 7 would have created NetworkManager profiles
    through exactly this hole, writing into the developer's own /etc.
    """
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.open("/etc/zepos-guard-probe", os.O_WRONLY | os.O_CREAT, 0o600)


def test_os_open_for_reading_still_works():
    fd = os.open("/etc/hostname", os.O_RDONLY)
    os.close(fd)


# --- the backstop every subprocess harness rests on --------------------


def _completed(stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(["stub"], 0, stdout, stderr)


def test_a_missing_command_reported_on_stderr_is_caught():
    with pytest.raises(AssertionError, match="does not provide"):
        conftest.assert_no_missing_command(
            _completed(stderr="script.sh: line 4: lpadmin: command not found\n"))


def test_a_missing_command_reported_on_stdout_is_caught():
    """The half that was missing, and the half that mattered.

    Every harness in this suite checked stderr alone, while most
    privileged call sites in these templates are written `2>&1`,
    `2>/dev/null` or `&>/dev/null`. A stderr-only check is not a weaker
    version of this one - against a `2>&1` pipeline it is no check at
    all.
    """
    with pytest.raises(AssertionError, match="does not provide"):
        conftest.assert_no_missing_command(
            _completed(stdout="script.sh: line 4: traceroute: command not found\n"))


def test_an_artifact_that_found_everything_it_asked_for_passes():
    """The other direction: a backstop that fires on ordinary output
    gets deleted rather than fixed."""
    conftest.assert_no_missing_command(
        _completed(stdout="Gateway 198.51.100.1 erreichbar\n",
                   stderr="warning: nothing important\n"))


@pytest.mark.allow_subprocess
def test_bash_really_puts_that_message_where_the_backstop_looks(tmp_path):
    """Which stream carries it is a fact about bash, not about this file.

    Asserted against a real shell rather than reasoned about, because the
    whole argument for `env -i` with a stub-only PATH is that a command
    nobody stubbed becomes audible - and the shape below is precisely
    the one network-diagnostic-config.template uses.
    """
    # `head` is named absolutely: with the stub-only PATH below it would
    # otherwise be missing too, and the test would pass on the wrong
    # message - on stderr, from the pipeline's second command.
    head = shutil.which("head")
    assert head and head.startswith("/")

    script = tmp_path / "probe.sh"
    script.write_text(
        "#!/bin/bash\n"
        f"zepos-command-that-does-not-exist 2>&1 | {head} -1\n",
        encoding="utf-8")

    result = subprocess.run(
        ["/usr/bin/env", "-i", f"PATH={tmp_path}", "/bin/bash", str(script)],
        env={}, input="", capture_output=True, text=True, timeout=60)

    assert "command not found" in result.stdout, (
        "bash no longer writes it where the 2>&1 sends it; the backstop "
        "has to be pointed at whatever it does write instead")
    with pytest.raises(AssertionError, match="does not provide"):
        conftest.assert_no_missing_command(result)


# --- what may be handed through to a real binary ----------------------


@pytest.mark.parametrize("name", ["sudo", "hyprctl", "nmcli", "ip", "systemctl",
                                  "pkill", "lpadmin", "curl", "dd", "pacman"])
def test_a_command_that_changes_the_machine_may_not_be_handed_through(name):
    """The rule three harnesses each wrote inside their own loop.

    Each spelled it `assert name not in ("hyprctl", "sudo", "nmcli")` and
    ran it once per entry of a tuple containing none of those names - a
    line executed a dozen times per fixture that could not have failed
    once. Exercised here instead, where a name dropped from the set is a
    failure rather than a silent widening.
    """
    with pytest.raises(AssertionError, match="never reach its real binary"):
        conftest.assert_safe_to_passthrough(name)


@pytest.mark.parametrize("name", ["jq", "cat", "awk", "grep", "head", "mkdir",
                                  "mv", "rm", "seq", "tee"])
def test_read_only_plumbing_is_still_allowed_through(name):
    """The other direction. Every name here is in some harness's
    PASSTHROUGH tuple today, so a set widened until it refuses everything
    breaks this instead of quietly making the suite unrunnable."""
    conftest.assert_safe_to_passthrough(name)


# --- the guard's own core scenario -------------------------------------
#
# installer.core.runner.install() defaults target_root to /mnt. A test
# calling install(cfg, runner=fake) without target_root writes a
# NetworkManager profile - with a real wireless passphrase in it - into
# the HOST's /mnt, and the guard used to say nothing at all, because /mnt
# was not on its list.


def test_writing_into_the_default_install_target_is_blocked():
    target = pathlib.Path("/mnt/etc/NetworkManager/system-connections/x.nmconnection")
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        target.write_text("kaputt")


# One path per entry in PROTECTED_PREFIXES, and the list is derived from
# the tuple rather than written out beside it, so an entry added to
# conftest with no path here is a collection error instead of a silent
# gap. The test used to name five of sixteen and was called "every
# destructive prefix": deleting /usr, /boot, /bin, /sbin, /lib, /opt,
# /var, /run, /sys or /proc from the tuple left the whole suite green.
PROTECTED_EXAMPLES = {
    "/etc": "/etc/NetworkManager/system-connections/x.nmconnection",
    "/usr": "/usr/share/zepos/template_processor.py",
    "/boot": "/boot/loader/entries/arch.conf",
    "/bin": "/bin/zepos-doctor",
    "/sbin": "/sbin/mkinitcpio",
    "/lib": "/lib/modules/anything",
    "/opt": "/opt/vendor/thing",
    "/var": "/var/lib/pacman/local/desc",
    "/run": "/run/systemd/resolve/stub-resolv.conf",
    "/sys": "/sys/class/backlight/device/brightness",
    "/proc": "/proc/sys/kernel/hostname",
    "/mnt": "/mnt/etc/fstab",
    "/home": "/home/somebody/.bashrc",
    "/root": "/root/.ssh/authorized_keys",
    "/srv": "/srv/http/index.html",
    "/dev": "/dev/sda",
}


@pytest.mark.parametrize("path", sorted(PROTECTED_EXAMPLES.values()))
def test_every_destructive_prefix_is_protected(path):
    assert conftest._is_protected(path) is True


def test_the_list_of_protected_prefixes_has_an_example_for_each_entry():
    """The parametrisation above is only "every prefix" while this holds.

    Without it, adding a prefix to conftest and forgetting a path here
    leaves the new entry untested, and the test name goes on claiming
    otherwise.
    """
    assert sorted(PROTECTED_EXAMPLES) == sorted(conftest.PROTECTED_PREFIXES)


def test_no_protected_prefix_may_be_dropped():
    """The behavioural test above cannot see every deletion.

    /bin, /sbin and /lib are symlinks into /usr on this distribution, so
    _is_protected() answers True for a path under any of them through
    the realpath comparison alone - and would go on answering True with
    those three entries deleted, on this machine, while a distribution
    that keeps them separate lost its protection. The tuple is the
    contract; this asserts the contract directly.

    A superset, not equality: adding a prefix is always safe and must not
    need this test edited.
    """
    required = {
        "/etc", "/usr", "/boot", "/bin", "/sbin", "/lib", "/opt", "/var",
        "/run", "/sys", "/proc", "/mnt", "/home", "/root", "/srv", "/dev",
    }
    missing = required - set(conftest.PROTECTED_PREFIXES)
    assert missing == set(), f"protection was removed from: {sorted(missing)}"


def test_the_work_tree_itself_is_protected():
    """A checkout under /workspace or /build is outside every system
    prefix, and a test writing into it silently rewrites the source it is
    testing."""
    assert conftest._is_protected(pathlib.Path(__file__).resolve().parent) is True


def test_a_checkout_inside_the_temp_directory_is_still_protected(monkeypatch):
    """Where CI systems and throwaway clones put it. The temporary
    directory is exempt so tmp_path works, and that exemption used to
    switch the work tree's own protection off whenever the two
    overlapped - measured by cloning this repository into /tmp, where
    the test above failed and passed everywhere else."""
    monkeypatch.setattr(conftest, "TMP_ROOT", pathlib.Path("/tmp"))
    monkeypatch.setattr(conftest, "WORK_TREE", pathlib.Path("/tmp/build/zepos"))
    assert conftest._is_protected("/tmp/build/zepos/installer/core/runner.py") is True
    assert conftest._is_protected("/tmp/pytest-of-someone/test0/file") is False


def test_a_temp_directory_inside_the_checkout_stays_writable(monkeypatch):
    """The exception to that exception: with TMPDIR pointing into the
    work tree, every tmp_path write would otherwise be refused."""
    monkeypatch.setattr(conftest, "WORK_TREE", pathlib.Path("/build/zepos"))
    monkeypatch.setattr(conftest, "TMP_ROOT", pathlib.Path("/build/zepos/tmp"))
    assert conftest._is_protected("/build/zepos/tmp/pytest-0/file") is False
    assert conftest._is_protected("/build/zepos/installer/core/runner.py") is True


def test_protection_compares_path_components_not_string_prefixes(monkeypatch):
    """A str.startswith() comparison gets this wrong in both directions.

    "/etcetera" is not inside "/etc" and used to count as protected. The
    second half is the dangerous one: with TMPDIR pointing anywhere
    inside a protected tree, every sibling directory whose name merely
    STARTS with the temporary one used to be waved through as
    temporary.
    """
    assert conftest._is_protected("/etcetera/file") is False

    monkeypatch.setattr(conftest, "TMP_ROOT", pathlib.Path("/home/someone/tmp"))
    assert conftest._is_protected("/home/someone/tmp/scratch") is False
    assert conftest._is_protected("/home/someone/tmpsecrets/keys") is True


def test_the_guard_never_asks_tempfile_where_the_temp_directory_is(monkeypatch):
    """tempfile.gettempdir() is lazy, and its first call probes candidate
    directories by creating files in them - through os.open, which this
    guard patches, which calls straight back in here. Measured before
    TMP_ROOT was resolved at import time: an installation whose first
    tempfile use happened inside a guarded call spun there instead of
    finishing."""

    def boom():
        raise AssertionError("the guard must not call tempfile.gettempdir()")

    monkeypatch.setattr(tempfile, "gettempdir", boom)
    assert conftest._is_protected("/etc/hostname") is True


def test_a_real_temporary_directory_stays_writable(tmp_path):
    assert conftest._is_protected(tmp_path / "anything") is False


# --- deleting, renaming and re-permissioning are writes too ------------
#
# The guard only ever patched CREATION. A test could delete /etc/hostname
# or chmod 0777 a system file and never hear a word about it.


def test_removing_a_system_file_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.remove("/etc/hostname")


def test_unlinking_a_system_file_through_pathlib_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        pathlib.Path("/etc/hostname").unlink()


def test_renaming_a_system_file_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.rename("/etc/hostname", "/etc/hostname.bak")


def test_renaming_through_pathlib_is_blocked(tmp_path):
    source = tmp_path / "harmless"
    source.write_text("ok")
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        source.rename("/etc/hostname")


def test_removing_a_system_tree_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        shutil.rmtree("/etc/NetworkManager")


def test_changing_permissions_on_a_system_file_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.chmod("/etc/hostname", 0o777)


def test_symlinking_into_a_system_path_is_blocked(tmp_path):
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        pathlib.Path("/etc/zepos-guard-link").symlink_to(tmp_path)


def test_builtins_open_for_writing_is_blocked():
    """pathlib.Path.open was patched; the plain builtin was not."""
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        open("/etc/zepos-guard-probe", "w")


def test_io_open_for_writing_is_blocked():
    """The hole the guard's own comment argued was not one.

    The note above the builtins.open patch used to reason that
    pathlib.Path.open "goes through io.open, which still refers to the
    unpatched builtin, so both have to be wrapped" - and then wrapped
    only builtins.open, concluding the job was done. It is not the same
    object slot: `builtins.open` and `io.open` are two module attributes
    holding one function, and rebinding either leaves the other alone.

    Measured: with the guard active and every other patch in place,
    io.open(WORK_TREE / "src" / "template_processor.py", "w") truncated the
    source file it was testing and the guard said nothing.
    """
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        io.open("/etc/zepos-guard-probe", "w")


def test_io_open_for_reading_still_works():
    with io.open("/etc/hostname") as handle:
        assert handle.read() is not None


def test_builtins_open_for_reading_still_works():
    with open("/etc/hostname") as handle:
        assert handle.read() is not None


# --- the patched entry points nothing was asserting -------------------
#
# Nine of the roughly twenty-one patched calls could be REMOVED from
# conftest, all nine at once, and the whole suite stayed green. A patch
# nothing exercises is indistinguishable from a patch that was deleted,
# which is how a guard quietly shrinks. One test per call, each naming
# what the call does to a host.
#
# None of these is used by src/ or installer/ today. That is the reason
# to hold them: the guard has to be right about the code somebody writes
# next, not only about the code that is here.
#
# WHAT A MUTATION SWEEP OVER THESE ACTUALLY SHOWS, stated honestly
#   Removing the os-level patch of any of them fails a test here.
#   Removing SOME of the pathlib-level and shutil-level ones does not,
#   and that is not a gap in these tests - it is CPython's layering:
#   Path.rmdir() calls os.rmdir(), Path.replace() calls os.replace(),
#   Path.hardlink_to() calls os.link(), os.removedirs() calls os.rmdir()
#   and shutil.move() calls os.rename(). With the inner patch in place
#   the outer one has nothing left to catch. Measured by removing each
#   outer patch TOGETHER with the os function it delegates to, at which
#   point every one of them fails a test in this file.
#
#   So the outer patches are defense in depth against a pathlib that
#   stops going through os - not dead weight, and not separately
#   demonstrable while the delegation holds.


def test_chowning_a_system_file_is_blocked():
    """chown 1000:1000 /etc/shadow hands the password database to a
    user account."""
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.chown("/etc/hostname", 0, 0)


def test_truncating_a_system_file_is_blocked():
    """The quietest destruction there is: the file is still there, still
    owned by root, still mode 0644, and empty."""
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.truncate("/etc/hostname", 0)


def test_hardlinking_into_a_system_path_is_blocked(tmp_path):
    source = tmp_path / "harmless"
    source.write_text("ok")
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.link(source, "/etc/zepos-guard-link")


def test_hardlinking_through_pathlib_is_blocked(tmp_path):
    source = tmp_path / "harmless"
    source.write_text("ok")
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        pathlib.Path("/etc/zepos-guard-link").hardlink_to(source)


def test_removing_a_system_directory_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.rmdir("/etc/NetworkManager")


def test_removing_a_system_directory_through_pathlib_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        pathlib.Path("/etc/NetworkManager").rmdir()


def test_removedirs_on_a_system_path_is_blocked():
    """It deletes the leaf and then walks UPWARDS deleting every parent
    that has become empty, so one call reaches further than the path it
    was given."""
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.removedirs("/etc/NetworkManager/system-connections")


def test_replacing_a_system_file_is_blocked(tmp_path):
    """os.replace() is os.rename() that overwrites without asking."""
    source = tmp_path / "harmless"
    source.write_text("ok")
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.replace(source, "/etc/hostname")


def test_replacing_through_pathlib_is_blocked(tmp_path):
    source = tmp_path / "harmless"
    source.write_text("ok")
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        source.replace("/etc/hostname")


def test_moving_a_file_onto_a_system_path_is_blocked(tmp_path):
    """shutil.move() falls back to copy-and-delete across filesystems,
    so it reaches targets os.rename() would have refused."""
    source = tmp_path / "harmless"
    source.write_text("ok")
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        shutil.move(str(source), "/etc/zepos-guard-probe")


def test_creating_a_fifo_over_a_system_path_is_blocked():
    """A named pipe where /etc/hostname was is not a smaller loss than a
    deleted one: every reader now blocks forever instead of failing."""
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.mkfifo("/etc/zepos-guard-probe")


def test_creating_a_device_node_in_a_system_path_is_blocked():
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.mknod("/etc/zepos-guard-probe")


def test_restamping_a_system_file_is_blocked():
    """Modification times are what pacman, make and every backup tool
    decide on."""
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.utime("/etc/hostname", (0, 0))


def test_setting_an_extended_attribute_on_a_system_file_is_blocked():
    """security.* and system.posix_acl_access live here: an ACL written
    through this is a permission change the chmod patch never sees."""
    with pytest.raises(conftest.IsolationViolation, match="outside"):
        os.setxattr("/etc/hostname", "user.zepos", b"probe")


# --- starting a process without the subprocess module -----------------


def test_posix_spawn_is_blocked():
    """subprocess.run() is not the only door. os.posix_spawn() is the
    one subprocess itself uses on some platforms."""
    with pytest.raises(RuntimeError, match="real process"):
        os.posix_spawn("/bin/true", ["true"], {})


def test_spawnv_is_blocked():
    with pytest.raises(RuntimeError, match="real process"):
        os.spawnv(os.P_WAIT, "/bin/true", ["true"])


def test_fork_is_blocked():
    with pytest.raises(RuntimeError, match="real process"):
        os.fork()


def test_execv_is_blocked():
    """The worst of the set: exec does not start a process, it BECOMES
    one. The pytest session would be replaced by /bin/true, the
    remaining tests would never run, and the report would say nothing at
    all about why."""
    with pytest.raises(RuntimeError, match="real process"):
        os.execv("/bin/true", ["true"])


def test_multiprocessing_is_blocked():
    """fork() is its default start method on Linux, and the child
    inherits the guard's patches as they stood at fork time - then
    leaves their scope entirely."""
    with pytest.raises(RuntimeError, match="real process"):
        multiprocessing.Process(target=len, args=("",)).start()


def test_temporary_files_still_work_through_every_patched_call(tmp_path):
    """The guard must stay invisible to the tests that behave: the
    installer itself deletes, renames and chmods inside temporary
    directories on every single run."""
    path = tmp_path / "a"
    path.write_text("ok")
    path.chmod(0o600)
    renamed = path.rename(tmp_path / "b")
    with open(renamed) as handle:
        assert handle.read() == "ok"
    os.remove(renamed)
    (tmp_path / "tree").mkdir()
    shutil.rmtree(tmp_path / "tree")


def test_the_calls_added_to_the_guard_still_work_inside_a_temp_directory(tmp_path):
    """The other half of every patch above.

    A guard made strict enough to refuse legitimate work gets switched
    off, so each newly wrapped call is exercised once where it is
    allowed. os.mknod() is deliberately absent: an unprivileged account
    cannot create a device node anywhere, so a test for it would measure
    the kernel's permission check rather than this guard.
    """
    source = tmp_path / "source"
    with io.open(source, "w", encoding="utf-8") as handle:
        handle.write("ok")

    os.utime(source, (0, 0))
    os.chown(source, os.getuid(), os.getgid())
    os.link(source, tmp_path / "hard")
    (tmp_path / "hard2").hardlink_to(source)
    os.replace(tmp_path / "hard", tmp_path / "hard3")
    (tmp_path / "hard2").replace(tmp_path / "hard4")
    shutil.move(str(tmp_path / "hard3"), str(tmp_path / "moved"))
    os.truncate(tmp_path / "moved", 0)
    assert (tmp_path / "moved").read_bytes() == b""

    os.mkfifo(tmp_path / "pipe")
    assert (tmp_path / "pipe").is_fifo()

    (tmp_path / "empty").mkdir()
    os.rmdir(tmp_path / "empty")
    (tmp_path / "nest" / "deep").mkdir(parents=True)
    os.removedirs(tmp_path / "nest" / "deep")
    (tmp_path / "another").mkdir()
    (tmp_path / "another").rmdir()


def test_the_installers_own_default_target_trips_the_guard():
    """The scenario I6 named, end to end.

    installer.core.runner.install() defaults target_root to /mnt, so a
    test calling install(cfg, runner=fake) and forgetting target_root
    writes a NetworkManager profile - with a real wireless passphrase in
    it - into the HOST's filesystem. The guard used to say nothing at
    all, because /mnt was not on its list of protected prefixes.

    Driven with dry_run=False, which is what a forgetful caller gets by
    default anyway: a dry run no longer writes into the target at all (it
    installs nothing, so there is nothing to finish off), which closed one
    route to /mnt but not this one. The fake runner therefore also has to
    answer the disk re-check a real run performs immediately before the
    erase.

    base_problem und clock_wait sind seit dem 17.08.2026 eingespeist,
    und das ist keine Anpassung an neuen Code, sondern dieselbe
    Dichtigkeit, die runner und is_uefi hier schon haben: ohne sie
    fragte dieser Test den festgenagelten ALA-Spiegel ueber HTTPS und
    waere auf einer Maschine ohne Netz rot - mit einer Ablehnung, die
    /mnt nie erreicht und ueber den Waechter deshalb nichts aussagt.
    Was gemessen wird, steht unveraendert unten: IsolationViolation
    auf /mnt.
    """
    from installer.core.model import (
        DiskChoice, InstallConfig, UserAccount, WifiCredentials,
    )
    from installer.core.runner import install
    from installer.core.source import PackageSource

    def runner(cmd, **kwargs):
        if cmd and cmd[0] == "openssl":
            return subprocess.CompletedProcess(cmd, 0, stdout="$6$salt$hash\n")
        if cmd and cmd[0] == "lsblk":
            # Three lsblk calls, all of them -P, told apart by the
            # columns each asks for. The other two enumerate mount
            # points and partitions; an empty answer to each means
            # nothing is mounted and nothing is described. This one
            # lists the disks, and must report the chosen /dev/vda at
            # exactly its chosen size or the re-check refuses before
            # anything reaches /mnt.
            from installer.core.disks import DISK_COLUMNS
            stdout = (
                'NAME="vda" SIZE="68719476736" TYPE="disk" MODEL=""'
                ' TRAN="" RM="0"\n'
            ) if DISK_COLUMNS in cmd else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout)
        return subprocess.CompletedProcess(cmd, 0)

    cfg = InstallConfig(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda", size_bytes=64 * 1024 ** 3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="rootlanggenug",
        wifi=WifiCredentials("Fritz", "wlanpw"),
    )

    with pytest.raises(conftest.IsolationViolation, match="/mnt"):
        install(cfg, source=PackageSource.ONLINE, dry_run=False,
                runner=runner, is_uefi=lambda: True,
                base_problem=lambda: "", clock_wait=lambda: "")


# --------------------------------------------------------------------
# Der Waechter darf nicht durch eine zweite conftest.py verschwinden
# --------------------------------------------------------------------

def test_there_is_exactly_one_conftest_under_tests():
    """Sonst holt `import conftest` irgendeine, und der Waechter ist weg.

    GEMESSEN AM 11.08.2026
        tests/menu/ bekam eine eigene conftest.py, um menu/ in den
        Suchpfad zu haengen. pytest legt das Verzeichnis JEDER conftest.py
        vorne in sys.path, und vier Dateien dieser Suite holen die
        Isolationsregeln mit `import conftest` beim Namen - unter anderem
        diese hier. Die neue gewann.

        Der Lauf: 226 fehlgeschlagene Tests und 23 Fehler, davon 77 in
        dieser Datei, alle mit "module 'conftest' has no attribute
        '_is_protected'". Jede Datei fuer sich lief gruen, also war es
        nur im vollstaendigen Lauf zu sehen.

        Das ist kein Schoenheitsfehler. Was da fuer einen halben Lauf
        fehlte, ist die Sperre, die verhindert, dass ein Test auf
        /dev/sda schreibt. Sie war nicht ABGESCHALTET - die autouse-
        Fixtures kommen aus tests/conftest.py und liefen weiter -, aber
        jede Aussage DARUEBER war es.

    Ein Verzeichnis braucht keine conftest.py, um Pfade zu setzen: die
    beiden Module unter tests/menu/ tun es in ihrem eigenen Kopf, mit
    genau dieser Begruendung daneben.
    """
    tests = pathlib.Path(__file__).resolve().parent
    found = sorted(path.relative_to(tests).as_posix()
                   for path in tests.rglob("conftest.py"))

    assert found == ["conftest.py"], (
        "es gibt mehr als eine conftest.py unter tests/: "
        + ", ".join(found)
        + ". Die zweite legt ihr Verzeichnis vor tests/ in sys.path, und "
        "`import conftest` holt dann sie statt der Isolationsregeln.")


def test_the_conftest_the_suite_imports_by_name_is_the_isolation_guard():
    """Die Gegenprobe: nicht nur, dass es eine ist, sondern welche.

    Der Test darueber zaehlt Dateien. Dieser fragt den Interpreter, was
    `import conftest` in diesem Lauf tatsaechlich geladen hat - denn
    genau das ist die Frage, an der es haengt.
    """
    loaded = pathlib.Path(conftest.__file__).resolve()
    expected = pathlib.Path(__file__).resolve().parent / "conftest.py"

    assert loaded == expected, (
        f"`import conftest` hat {loaded} geladen und nicht {expected}")
    assert hasattr(conftest, "PROTECTED_PREFIXES")
    assert hasattr(conftest, "_is_protected")


def test_kein_testmodul_traegt_den_namen_eines_anderen():
    """Zwei gleich benannte Testdateien teilen die Sammlung in zwei.

    WAS GEMESSEN WURDE, 22.08.2026
        `pytest` ohne Argumente brach beim Sammeln ab:

            import file mismatch:
            imported module 'test_home' has this __file__ attribute:
              tests/render/test_home.py
            which is not the same as the test file we want to collect:
              tests/src/test_home.py

        Kein Verzeichnis unter tests/ traegt eine __init__.py - das ist
        Absicht, weil sonst jede Datei ueber einen Paketpfad importiert
        wuerde -, und ohne sie ist der MODULNAME einer Testdatei ihr
        blosser Dateiname. Zwei davon koennen nicht gleichzeitig im
        Interpreter stehen.

        Die Folge war nicht ein Fehler, sondern eine geteilte Sammlung:
        die Anleitung dieses Baums beschrieb zwei Aufrufe und eine
        Addition von Hand, damit ueberhaupt jede Datei einmal laeuft. Ein
        Lauf, den man addieren muss, ist ein Lauf, bei dem jemand eines
        Tages die zweite Haelfte vergisst.

    Behoben wurde es durch Umbenennen (tests/render/test_home.py heisst
    jetzt test_home_flaeche.py, nach dem, was sie misst); dieser Test ist
    die Sperre dagegen, dass es wiederkommt. Er zaehlt Dateien und
    braucht dafuer keine Sammlung - er faellt also auch dann, wenn der
    Zusammenstoss den Sammellauf gerade wieder abbricht.
    """
    tests = pathlib.Path(__file__).resolve().parent

    nach_namen: dict[str, list[str]] = {}
    for path in sorted(tests.rglob("test_*.py")):
        nach_namen.setdefault(path.stem, []).append(
            path.relative_to(tests).as_posix())

    doppelt = {name: pfade for name, pfade in nach_namen.items()
               if len(pfade) > 1}

    assert doppelt == {}, (
        "diese Testdateien tragen denselben Namen wie eine andere: "
        + "; ".join(f"{name}: {', '.join(pfade)}"
                    for name, pfade in sorted(doppelt.items()))
        + ". Ohne __init__.py ist der Dateiname der Modulname, und pytest "
        "bricht das Sammeln mit 'import file mismatch' ab - die Sammlung "
        "laesst sich dann nur noch in zwei Aufrufen abdecken. Eine der "
        "beiden umbenennen, nach dem, was sie misst.")
