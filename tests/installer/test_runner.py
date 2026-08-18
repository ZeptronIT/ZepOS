# SPDX-License-Identifier: GPL-3.0-or-later
import json
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

from installer.core.disks import DISK_COLUMNS
from installer.core.model import InstallConfig, DiskChoice, UserAccount, WifiCredentials
from installer.core.source import PackageSource
from installer.core.runner import InstallationRefused
from installer.core.runner import install as _real_install


def install(cfg, **kw):
    """install() with the firmware answer filled in.

    Every test here injects one: install() refuses outright on a machine
    that started in BIOS mode (der Kopf von installer/core/firmware.py
    sagt, warum), and whether the machine RUNNING the tests booted
    through EFI is not what any of these tests are about. The two tests
    that do exercise that refusal pass their own is_uefi.

    Seit dem 17.08.2026 stehen die zwei Messungen aus
    installer/core/preflight.py daneben, und aus demselben Grund - mit
    einem Zusatz, der schwerer wiegt als Bequemlichkeit. Ohne diese zwei
    Zeilen fragt JEDER Test in dieser Datei, der bis zu archinstall
    kommt, den festgenagelten ALA-Spiegel ueber HTTPS. Die ganze Reihe
    haenge dann am Netz der Maschine, auf der sie laeuft, und auf einem
    Rechner ohne Netz waere jeder einzelne dieser Tests rot - mit einer
    Begruendung, die mit dem, was er misst, nichts zu tun hat. Die
    Tests, die die Ablehnung selbst messen, speisen ihre eigenen
    Antworten ein.
    """
    kw.setdefault("is_uefi", lambda: True)
    kw.setdefault("base_problem", lambda: "")
    kw.setdefault("clock_wait", lambda: "")
    return _real_install(cfg, **kw)


def _cfg(**over) -> InstallConfig:
    base = dict(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        # size_bytes must clear translate.MIN_DISK_MIB or
        # to_archinstall_config() refuses the disk as too small - the
        # brief's own sample fixture omits this and cannot pass a single
        # dry-run test as a result (confirmed by running it verbatim: every
        # test that reached translate() failed with "target disk is too
        # small"). 64 GiB matches the convention already used in
        # test_translate.py's own fixture.
        disk=DiskChoice(device="/dev/vda", size_bytes=64 * 1024**3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="rootlanggenug",
    )
    base.update(over)
    return InstallConfig(**base)


# install() routes its injected runner through to hash_password() as well
# (see runner.py), so every fake below also receives the incidental
# "openssl passwd -6 -stdin" call that to_archinstall_creds() triggers for
# each user password. Real openssl output is not needed by anything these
# tests check; this fixed stdout just has to look like one so
# hash_password()'s ".startswith(\"$6$\")"-shaped consumers are satisfied.
FAKE_HASH_STDOUT = "$6$fakesalt$fakehashvalue0123456789\n"


# What the disk re-check sees by default: one 64 GiB /dev/vda, nothing
# mounted - i.e. exactly the disk _cfg() selects, still present and still
# the same size.
#
# lsblk's -P format, because that is what list_disks() asks for now: it
# reads MODEL, which is a field with spaces in it, and a columnar split
# turns "Samsung SSD 980 1TB" into four columns.
LSBLK_DISKS_STDOUT = (
    'NAME="vda" SIZE="68719476736" TYPE="disk" MODEL="" TRAN="" RM="0"\n'
)


def _openssl_or(handle_archinstall, *, lsblk_stdout=LSBLK_DISKS_STDOUT):
    """Answer the incidental openssl and lsblk calls and forward
    everything else - i.e. the actual archinstall invocation - to the
    given callable.

    Both are incidental to what these tests check but unavoidable: the
    single injected runner drives every subprocess install() makes, which
    is openssl for the password hashes and lsblk for the disk re-check
    that runs immediately before the erase.
    """
    def runner(cmd, **kw):
        if cmd and cmd[0] == "openssl":
            return subprocess.CompletedProcess(cmd, 0, stdout=FAKE_HASH_STDOUT)
        if cmd and cmd[0] == "lsblk":
            # Three lsblk calls now, all of them -P, so they are told
            # apart by the columns they ask for and not by the format.
            # The other two enumerate mount points and partitions; an
            # empty answer to each means nothing is mounted and no disk
            # has partitions, so no disk is filtered out and none gains
            # a description.
            stdout = lsblk_stdout if DISK_COLUMNS in cmd else ""
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout)
        return handle_archinstall(cmd, **kw)
    return runner


class Spy:
    """Records the archinstall command only; the openssl and lsblk calls
    needed to produce creds.json and to re-check the target disk are
    answered transparently by _openssl_or."""

    def __init__(self, returncode=0, lsblk_stdout=LSBLK_DISKS_STDOUT):
        self.returncode = returncode
        self.cmd = None
        self._call = _openssl_or(self._archinstall, lsblk_stdout=lsblk_stdout)

    def _archinstall(self, cmd, **kw):
        self.cmd = cmd
        return subprocess.CompletedProcess(cmd, self.returncode)

    def __call__(self, cmd, **kw):
        return self._call(cmd, **kw)


def test_invalid_config_is_refused_before_touching_disks():
    spy = Spy()
    # Asserts on the English msgid, not a translation: nothing in this
    # module activates a catalogue, so validate() always reports in
    # English regardless of cfg.language. (The brief's own sample matched
    # "Benutzer", the German translation - confirmed by running it
    # verbatim that this never matches, since the active catalogue here
    # is English by default. See task-8-report.md for the full trace.)
    with pytest.raises(ValueError, match="user account"):
        install(_cfg(users=[]), source=PackageSource.ONLINE, runner=spy)
    assert spy.cmd is None


def test_archinstall_is_called_with_config_creds_and_silent(tmp_path):
    spy = Spy()
    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=spy)
    assert spy.cmd[0] == "archinstall"
    assert "--silent" in spy.cmd
    assert "--dry-run" in spy.cmd
    assert "--config" in spy.cmd and "--creds" in spy.cmd


def test_the_target_root_is_passed_as_mountpoint(tmp_path):
    """The flag every real installation depends on and no test used to
    look at. Spelled "--mountpoint" (one word), verified against
    archinstall 4.4's own argument parser, where it defaults to /mnt.
    A wrong spelling here kills every real install at the argument
    parser, while every mocked test still passes."""
    spy = Spy()
    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=spy)
    assert "--mountpoint" in spy.cmd
    assert spy.cmd[spy.cmd.index("--mountpoint") + 1] == str(tmp_path)


def test_offline_source_adds_offline_flag(tmp_path):
    spy = Spy()
    install(_cfg(), source=PackageSource.OFFLINE, dry_run=True,
            target_root=tmp_path, runner=spy)
    assert "--offline" in spy.cmd


def test_an_online_source_does_not_add_the_offline_flag(tmp_path):
    """The half that makes the flag mean anything.

    Presence was asserted for OFFLINE and absence was asserted nowhere,
    so moving `command.append("--offline")` out of its `if` - appending
    it on every run - left the whole suite green. Every ONLINE
    installation would then be built from whatever package set was
    frozen into the live image, which is precisely the state a user
    picks ONLINE to avoid, and nothing in the run would say so.
    """
    spy = Spy()
    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=spy)
    assert spy.cmd is not None, "archinstall was never called"
    assert "--offline" not in spy.cmd, spy.cmd


# --------------------------------------------------------------------
# Kein Netz: ablehnen, statt einzufrieren
#
# DER BEFUND, 17.08.2026, von echter Hardware: "Installation Wizard mit
# dem Terminal freezed wenn ich versuche ohne Internet und ohne
# Passphrase zu installieren."
#
# Gehangen hat archinstall 4.4 in lib/installer.py:189-202, in einem
# `while True` ohne Frist, das darauf wartet, dass `timedatectl show
# --property=NTPSynchronized` `yes` sagt - was ohne Netz nie geschieht.
# Und es hing NACH scripts/guided.py:249
# perform_filesystem_operations(), also vor einer bereits geteilten und
# formatierten Platte.
#
# Die vier Pruefungen unten sind die vier Eigenschaften, ohne die dieser
# Befund wiederkommt.
# --------------------------------------------------------------------

def test_an_unreachable_base_system_is_refused_before_archinstall(tmp_path):
    """Und zwar als InstallationRefused, nicht als irgendeine Ausnahme.

    Der TYP ist hier die halbe Aussage: installer/gui/pages.py haengt
    genau an ihm den Satz "Auf der Platte {device} wurde nichts
    geaendert" an, und nach einer bestaetigten Loeschung ist das das
    einzige, was der Nutzer nicht selbst sehen kann.
    """
    spy = Spy()
    with pytest.raises(InstallationRefused, match="kein Netz|no network|not be reached"):
        install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                target_root=tmp_path, runner=spy,
                base_problem=lambda: "The Arch Linux package source cannot be reached: x")
    assert spy.cmd is None, "archinstall wurde trotzdem gestartet"


def test_the_refusal_carries_the_measured_sentence(tmp_path):
    """Ein zweiter, eigener Satz an dieser Stelle waere eine zweite
    Beschreibung derselben Regel - und die zwei driften auseinander.
    Wie bei firmware_problem(): eine Funktion, eine msgid."""
    spy = Spy()
    with pytest.raises(InstallationRefused) as refusal:
        install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                target_root=tmp_path, runner=spy,
                base_problem=lambda: "GENAU DIESER SATZ")
    assert str(refusal.value) == "GENAU DIESER SATZ"


def test_a_dry_run_is_not_refused_for_want_of_a_network(tmp_path):
    """--dry-run schreibt nichts und holt kein Paket. Die
    Erreichbarkeit der Basis ist dort keine Bedingung, sondern eine
    Huerde ohne Zweck - und tests/integration/test_dry_run.sh faehrt
    genau so."""
    spy = Spy()
    asked = []
    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=spy,
            base_problem=lambda: asked.append("gefragt") or "kein Netz")
    assert spy.cmd is not None, "der Trockenlauf wurde abgelehnt"
    assert asked == [], "der Trockenlauf hat trotzdem am Netz gemessen"


def test_the_network_is_measured_before_the_disk_is_re_enumerated(tmp_path):
    """Die Reihenfolge ist die Aussage: die billigste Ablehnung zuerst.

    _require_target_disk() ist die letzte Pruefung vor der Loeschung und
    liest dafuer lsblk. Eine Maschine ohne Netz braucht das gar nicht
    mehr zu tun - und wer die Reihenfolge umdreht, laesst den Nutzer
    erst eine Platte bestaetigt bekommen, um ihm danach zu sagen, dass
    ohnehin nichts installiert werden kann.
    """
    seen = []

    def list_disks(**kw):
        seen.append("lsblk")
        return []

    with pytest.raises(InstallationRefused):
        install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                target_root=tmp_path, runner=Spy(), list_disks=list_disks,
                base_problem=lambda: "kein Netz")
    assert seen == [], "die Platten wurden trotz fehlendem Netz noch einmal gezaehlt"


def test_the_clock_wait_only_runs_once_the_base_is_reachable(tmp_path):
    """Sonst wartet eine Maschine ohne Netz erst die volle Frist ab, um
    danach zu sagen, dass es kein Netz gibt."""
    order = []

    with pytest.raises(InstallationRefused):
        install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                target_root=tmp_path, runner=Spy(),
                base_problem=lambda: order.append("basis") or "kein Netz",
                clock_wait=lambda: order.append("uhr") or "")
    assert order == ["basis"]


def test_an_unsynchronised_clock_is_a_warning_and_not_a_refusal(tmp_path):
    """Eine Maschine, deren Echtzeituhr richtig geht, installiert
    einwandfrei. Ihr das zu verweigern waere ein zweiter Fehler - und
    zwar einer, der Installationen kaputtmacht, die heute laufen."""
    spy = Spy()
    warnings = []
    code = install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                   target_root=tmp_path, runner=spy, on_warning=warnings.append,
                   clock_wait=lambda: "Die Uhr wurde nicht gestellt.")
    assert code == 0
    assert spy.cmd is not None, "archinstall wurde wegen der Uhr nicht gestartet"
    assert "Die Uhr wurde nicht gestellt." in warnings


def test_archinstall_is_told_not_to_wait_for_the_clock_itself(tmp_path):
    """DER SCHALTER, DER DAS EINFRIEREN ABSTELLT.

    Ohne `--skip-ntp` laeuft archinstalls eigene Schleife ohne Frist
    (lib/installer.py:189-202), und die steht hinter der schon
    geteilten Platte - dort kann keine Oberflaeche mehr etwas
    Vernuenftiges sagen. Ein falsch geschriebenes Flag faellt hier auf
    und nicht erst nach zwanzig Minuten Stillstand auf fremder
    Hardware.
    """
    spy = Spy()
    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=spy)
    assert "--skip-ntp" in spy.cmd, spy.cmd


def test_written_creds_file_is_mode_600(tmp_path):
    captured = {}

    def archinstall_call(cmd, **kw):
        idx = cmd.index("--creds")
        path = Path(cmd[idx + 1])
        captured["mode"] = stat.S_IMODE(path.stat().st_mode)
        captured["body"] = json.loads(path.read_text())
        return subprocess.CompletedProcess(cmd, 0)

    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=_openssl_or(archinstall_call))
    assert captured["mode"] == 0o600
    assert captured["body"]["users"][0]["enc_password"].startswith("$6$")


def test_wifi_profile_is_written_into_the_target(tmp_path):
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    install(cfg, source=PackageSource.ONLINE, dry_run=False,
            target_root=tmp_path, runner=Spy())
    profile = tmp_path / "etc/NetworkManager/system-connections/Fritz.nmconnection"
    assert profile.exists(), "without this profile the target boots with no network"
    # Spec 11 asks for exactly this check after an installation: the file
    # exists AND is readable by root alone. It carries the passphrase in
    # clear text, and NetworkManager refuses a keyfile anyone else can
    # read.
    assert stat.S_IMODE(profile.stat().st_mode) == 0o600


def test_a_profile_that_ends_up_readable_by_others_is_reported(tmp_path,
                                                               monkeypatch):
    """Spec §11's check, asserted where it is supposed to happen.

    The test above re-implements it: it stats the file itself and
    compares the mode. That is a statement about write_profile(), and
    install() could stop calling profile_problem() entirely - or keep
    calling it and drop the `if problem: on_warning(problem)` - and
    nothing in the suite would move. Mutating that branch to `if False:`
    left it green.

    So the failure is arranged instead of inspected. write_profile is
    replaced by one that writes the same file at 0644 - which is what a
    target filesystem that cannot carry the mode leaves behind - and the
    question asked is whether install() SAID SO. It matters because
    NetworkManager refuses a keyfile others can read: the machine boots
    with no wireless at all, having just been installed over wireless,
    and the passphrase is sitting in a world-readable file besides.
    """
    from installer.core import runner as runner_module

    real_write = runner_module.write_profile

    def writes_it_wide(wifi, target_root, **kwargs):
        path = real_write(wifi, target_root, **kwargs)
        path.chmod(0o644)
        return path

    monkeypatch.setattr(runner_module, "write_profile", writes_it_wide)

    warnings = []
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    rc = install(cfg, source=PackageSource.ONLINE, dry_run=False,
                 target_root=tmp_path, runner=Spy(), on_warning=warnings.append)

    # Still a success: the machine IS installed, and telling the user
    # otherwise invites them to run it again over a working system.
    assert rc == 0
    assert warnings, "the profile was never checked after it was written"
    assert any("readable by others" in message for message in warnings), warnings


def test_a_profile_written_correctly_produces_no_warning(tmp_path):
    """The other direction. A check that warns about every installation
    is a check the user learns to ignore."""
    warnings = []
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    rc = install(cfg, source=PackageSource.ONLINE, dry_run=False,
                 target_root=tmp_path, runner=Spy(), on_warning=warnings.append)

    assert rc == 0
    assert warnings == [], warnings


def test_no_wifi_means_no_profile(tmp_path):
    install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
            target_root=tmp_path, runner=Spy())
    assert not (tmp_path / "etc/NetworkManager/system-connections").exists()


def test_a_dry_run_writes_nothing_into_the_target(tmp_path):
    """A dry run installs nothing, so there is no installed system to
    finish off - and target_root still defaults to the HOST's /mnt.
    install(cfg, dry_run=True) used to write the wireless profile there,
    with the passphrase in clear text, plus the ZepOS settings, into a
    filesystem no installation ever mounted.
    """
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    rc = install(cfg, source=PackageSource.ONLINE, dry_run=True,
                 target_root=tmp_path, runner=Spy())
    assert rc == 0
    assert list(tmp_path.iterdir()) == [], (
        "a dry run must leave the target root exactly as it found it"
    )


def test_nonzero_exit_is_propagated(tmp_path):
    rc = install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
                 target_root=tmp_path, runner=Spy(returncode=7))
    assert rc == 7


def test_wifi_profile_is_not_written_when_archinstall_failed(tmp_path):
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    install(cfg, source=PackageSource.ONLINE, dry_run=False,
            target_root=tmp_path, runner=Spy(returncode=1))
    profile = tmp_path / "etc/NetworkManager/system-connections/Fritz.nmconnection"
    assert not profile.exists()


def test_missing_archinstall_binary_raises_a_clear_error(tmp_path):
    """subprocess.run raises FileNotFoundError before any CompletedProcess
    exists when the executable is missing - a real scenario on a live
    image whose squashfs was built without archinstall. Checking
    result.returncode can never see this; it must be caught around the
    call itself."""
    def archinstall_call(cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory", "archinstall")

    # InstallationRefused, not a bare RuntimeError: archinstall never
    # started, so a surface may tell the user the disk is untouched. See
    # the type's own docstring for why that distinction is load-bearing.
    with pytest.raises(InstallationRefused, match="archinstall"):
        install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
                target_root=tmp_path, runner=_openssl_or(archinstall_call))


def test_successful_install_cleans_up_the_temporary_workdir(tmp_path):
    """config.json and creds.json (password hashes) have no reason to
    linger on disk once archinstall has consumed them."""
    captured = {}

    def archinstall_call(cmd, **kw):
        idx = cmd.index("--config")
        captured["workdir"] = Path(cmd[idx + 1]).parent
        return subprocess.CompletedProcess(cmd, 0)

    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=_openssl_or(archinstall_call))
    assert not captured["workdir"].exists(), (
        "creds.json must not linger on disk after a successful install"
    )


def test_failed_install_preserves_the_temporary_workdir_for_diagnosis(tmp_path):
    """A failed install must stay diagnosable: config.json and creds.json
    are the only record of what archinstall was actually asked to do."""
    captured = {}

    def archinstall_call(cmd, **kw):
        idx = cmd.index("--config")
        captured["workdir"] = Path(cmd[idx + 1]).parent
        return subprocess.CompletedProcess(cmd, 1)

    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=_openssl_or(archinstall_call))
    assert captured["workdir"].exists()
    assert (captured["workdir"] / "config.json").exists()
    assert (captured["workdir"] / "creds.json").exists()


def test_workdir_is_removed_when_a_failure_happens_before_archinstall_runs(tmp_path, monkeypatch):
    """A ValueError/RuntimeError raised while building config.json or
    creds.json happens before archinstall is ever invoked, so nothing
    useful has been handed to it yet. That workdir must not be left
    behind - unlike one left by a failed archinstall RUN (tested above),
    which is kept on purpose for diagnosis. That distinction is
    deliberate and must survive.

    Failure is triggered here by a runner that raises for the *openssl*
    call to_archinstall_creds() makes while building creds.json - a
    realistic case (openssl missing from a damaged live image) that
    happens strictly before archinstall itself would ever be invoked.
    """
    captured = {}
    real_mkdtemp = tempfile.mkdtemp

    def spying_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        captured["workdir"] = Path(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", spying_mkdtemp)

    def broken_openssl(cmd, **kw):
        if cmd and cmd[0] == "openssl":
            raise FileNotFoundError(2, "No such file or directory", "openssl")
        raise AssertionError("archinstall must never be invoked in this scenario")

    with pytest.raises(RuntimeError, match="openssl"):
        install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
                target_root=tmp_path, runner=broken_openssl)

    assert "workdir" in captured, "install() must still have created a workdir"
    assert not captured["workdir"].exists(), (
        "a failure before archinstall ever runs must not leave a workdir behind"
    )


# --- firmware ------------------------------------------------------------


def test_a_bios_machine_is_refused_before_anything_is_erased(tmp_path):
    """Refused, and refused BEVOR archinstall aufgerufen wird.

    Der Grund steht im Kopf von installer/core/firmware.py: der
    BIOS-Startweg ist nicht gemessen, und die Loeschung kaeme vor der
    Antwort. Was hier gemessen wird, ist die Reihenfolge - spy.cmd bleibt
    None, also hat nichts die Platte angefasst."""
    spy = Spy()
    with pytest.raises(InstallationRefused, match="UEFI"):
        _real_install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
                      target_root=tmp_path, runner=spy, is_uefi=lambda: False)
    assert spy.cmd is None


def test_a_uefi_machine_is_accepted(tmp_path):
    spy = Spy()
    _real_install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
                  target_root=tmp_path, runner=spy, is_uefi=lambda: True)
    assert spy.cmd is not None


# --- the disk is re-checked at the moment of the erase --------------------


def test_a_real_run_rechecks_the_target_disk_before_erasing_it(tmp_path):
    """Nothing between choosing a disk and erasing it used to look at the
    hardware again: validate() only re-reads the size that was stored
    when the choice was made. A device unplugged and plugged back in
    keeps its name in the configuration while the kernel may have given
    that name to something else - and wipe defaults to True."""
    spy = Spy(lsblk_stdout="")  # the chosen disk is simply not there any more
    with pytest.raises(InstallationRefused, match="no longer available"):
        install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                target_root=tmp_path, runner=spy)
    assert spy.cmd is None, "archinstall must not run against a disk that vanished"


def test_a_disk_whose_size_changed_is_refused(tmp_path):
    """Same name, different device: only the size can tell the two
    apart."""
    spy = Spy(lsblk_stdout=  # 32 GiB, not the 64 chosen
    'NAME="vda" SIZE="34359738368" TYPE="disk" MODEL="" TRAN="" RM="0"\n')
    with pytest.raises(InstallationRefused, match="size has changed"):
        install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                target_root=tmp_path, runner=spy)
    assert spy.cmd is None


def test_an_unchanged_disk_passes_the_recheck(tmp_path):
    spy = Spy()
    rc = install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                 target_root=tmp_path, runner=spy)
    assert rc == 0
    assert spy.cmd[0] == "archinstall"


def test_a_failed_recheck_leaves_no_workdir_behind(tmp_path, monkeypatch):
    captured = {}
    real_mkdtemp = tempfile.mkdtemp

    def spying_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        captured["workdir"] = Path(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", spying_mkdtemp)
    with pytest.raises(RuntimeError, match="no longer available"):
        install(_cfg(), source=PackageSource.ONLINE, dry_run=False,
                target_root=tmp_path, runner=Spy(lsblk_stdout=""))
    assert not captured["workdir"].exists(), (
        "nothing was handed to archinstall, so the creds must not linger"
    )


def test_a_failure_during_the_archinstall_run_is_not_reported_as_a_refusal(tmp_path):
    """The other half of InstallationRefused's contract. The type means
    "archinstall never started", and a surface is allowed to tell the
    user the disk is untouched on the strength of exactly that. A failure
    raised while archinstall itself was running proves nothing of the
    kind, so it must not arrive wearing that type."""
    def archinstall_call(cmd, **kw):
        raise RuntimeError("the run died halfway through")

    with pytest.raises(RuntimeError) as caught:
        install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
                target_root=tmp_path, runner=_openssl_or(archinstall_call))
    assert not isinstance(caught.value, InstallationRefused)


def test_a_dry_run_does_not_recheck_the_disk(tmp_path):
    """--dry-run erases nothing, and its target is deliberately allowed
    to be a device list_disks() filters out - the loop device
    tests/integration/test_dry_run.sh installs onto is exactly that."""
    def runner(cmd, **kw):
        if cmd and cmd[0] == "openssl":
            return subprocess.CompletedProcess(cmd, 0, stdout=FAKE_HASH_STDOUT)
        if cmd and cmd[0] == "lsblk":
            raise AssertionError("a dry run must not re-enumerate disks")
        return subprocess.CompletedProcess(cmd, 0)

    assert install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
                   target_root=tmp_path, runner=runner) == 0


# --- archinstall's output ------------------------------------------------


def test_archinstall_output_is_collected_when_a_log_path_is_given(tmp_path):
    """The graphical surface is started from a session whose terminal
    nobody sees, so archinstall's output has to land somewhere the
    installer can read back."""
    log_path = tmp_path / "install.log"

    def archinstall_call(cmd, **kw):
        assert kw["stderr"] is subprocess.STDOUT, "stderr must join stdout"
        kw["stdout"].write("Formatting /dev/vda2\n")
        return subprocess.CompletedProcess(cmd, 0)

    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, log_path=log_path,
            runner=_openssl_or(archinstall_call))
    assert "Formatting /dev/vda2" in log_path.read_text(encoding="utf-8")


def test_without_a_log_path_the_output_is_left_alone(tmp_path):
    """The text interface runs on a terminal the user is looking at:
    redirecting archinstall's output there would hide it."""
    seen = {}

    def archinstall_call(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0)

    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=_openssl_or(archinstall_call))
    assert "stdout" not in seen


# --- what happens after archinstall reported success ---------------------


def test_a_problem_after_a_successful_install_is_a_warning_not_a_failure(tmp_path):
    """The machine IS installed by this point. Raising here would tell
    the user their installation failed, and the obvious answer to a
    failed installation - run it again - erases a disk that already
    carries a working system."""
    warnings = []
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    # A file where the profile directory has to go: mkdir(parents=True)
    # fails with NotADirectoryError, which is exactly the kind of failure
    # that must not become an exception out of install().
    (tmp_path / "etc").write_text("not a directory")

    rc = install(cfg, source=PackageSource.ONLINE, dry_run=False,
                 target_root=tmp_path, runner=Spy(), on_warning=warnings.append)
    assert rc == 0
    assert warnings and "installed" in warnings[0]


def test_zepos_options_reach_the_installed_system(tmp_path):
    """"Enable ZepOS plugins?" and the weather location are asked by both
    surfaces; they used to have no effect on anything."""
    cfg = _cfg()
    cfg.zepos.enable_plugins = False
    cfg.zepos.weather_location = "Wien"
    (tmp_path / "home" / "lars").mkdir(parents=True)

    install(cfg, source=PackageSource.ONLINE, dry_run=False,
            target_root=tmp_path, runner=Spy())

    skel = tmp_path / "etc/skel/.config/zepos/user-settings.json"
    home = tmp_path / "home/lars/.config/zepos/user-settings.json"
    for path in (skel, home):
        settings = json.loads(path.read_text(encoding="utf-8"))
        assert settings["plugins"]["enabled"] is False
        assert settings["weather"]["location"] == "Wien"


# --- what the installed system is left pointing at (spec 8.5b) -----------


def _target_pacman_conf(root: Path, text: str) -> Path:
    path = root / "etc/pacman.conf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# archinstall 4.4 appends the section to the LIVE pacman.conf, copies
# that file over the target's in minimal_installation(), and appends it
# to the copy - so an offline installation finishes with two of them,
# both naming a directory of the live medium. This is that file.
TWO_OFFLINE_SECTIONS = (
    "[options]\nHoldPkg = pacman glibc\n\n"
    "[core]\nInclude = /etc/pacman.d/mirrorlist\n\n"
    "[zepos]\nSigLevel = Required TrustedOnly\nServer = file:///opt/zepos-repo\n\n"
    "[zepos]\nSigLevel = Required TrustedOnly\nServer = file:///opt/zepos-repo\n"
)


def test_an_offline_install_does_not_leave_the_offline_repository_behind(tmp_path):
    """Spec §8.5b, and the reason it is not a detail: `/opt/zepos-repo`
    is a directory of the live medium. It exists for the length of the
    installation and never again, so a target left pointing at it fails
    its first `pacman -Syu` - on a machine whose owner has no way to know
    what the URL was supposed to be."""
    _target_pacman_conf(tmp_path, TWO_OFFLINE_SECTIONS)

    warnings = []
    rc = install(_cfg(), source=PackageSource.OFFLINE, dry_run=False,
                 target_root=tmp_path, runner=Spy(), on_warning=warnings.append)

    text = (tmp_path / "etc/pacman.conf").read_text(encoding="utf-8")
    assert rc == 0
    assert warnings == [], warnings
    assert text.count("[zepos]") == 1, text
    assert "file://" not in text, text
    assert "https://zeptronit.github.io/ZepOS/$arch" in text


def test_the_repository_rewrite_survives_a_failing_wireless_profile(tmp_path,
                                                                    monkeypatch):
    """Three independent obligations of spec §8, and one that cannot be
    met must not cancel the others.

    Arranged rather than inspected, for the reason
    test_a_profile_that_ends_up_readable_by_others_is_reported gives:
    with all three steps inside one try block, a wireless profile that
    raises jumps past the repository rewrite, and the machine is left
    pointing at `/opt/zepos-repo` with nothing said about it - the second
    failure hidden behind the first.
    """
    from installer.core import runner as runner_module

    def refuses(wifi, target_root, **kwargs):
        raise OSError("no room on the target for a connection profile")

    monkeypatch.setattr(runner_module, "write_profile", refuses)
    _target_pacman_conf(tmp_path, TWO_OFFLINE_SECTIONS)

    warnings = []
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    rc = install(cfg, source=PackageSource.OFFLINE, dry_run=False,
                 target_root=tmp_path, runner=Spy(), on_warning=warnings.append)

    text = (tmp_path / "etc/pacman.conf").read_text(encoding="utf-8")
    assert rc == 0
    assert any("no room on the target" in message for message in warnings), warnings
    assert text.count("[zepos]") == 1, text
    assert "file://" not in text, text


def test_a_dry_run_does_not_rewrite_a_repository_definition(tmp_path):
    """--dry-run installs nothing, so there is no target pacman.conf to
    correct. With the default target_root that file is the HOST's
    /mnt/etc/pacman.conf, and before the dry-run guard existed install()
    wrote into the target regardless."""
    rc = install(_cfg(), source=PackageSource.OFFLINE, dry_run=True,
                 target_root=tmp_path, runner=Spy())

    assert rc == 0
    assert not (tmp_path / "etc/pacman.conf").exists()


def test_a_failed_install_leaves_the_repository_definition_alone(tmp_path):
    """archinstall failed, so the disk may hold anything at all. Editing
    a pacman.conf on it would be the installer's only mark on a system it
    did not manage to build."""
    _target_pacman_conf(tmp_path, TWO_OFFLINE_SECTIONS)

    rc = install(_cfg(), source=PackageSource.OFFLINE, dry_run=False,
                 target_root=tmp_path, runner=Spy(returncode=1))

    assert rc == 1
    assert (tmp_path / "etc/pacman.conf").read_text(encoding="utf-8") == \
        TWO_OFFLINE_SECTIONS


# --- die Plattenpassphrase auf dem Weg zu archinstall ------------------


def _encrypted_cfg() -> InstallConfig:
    return _cfg(disk=DiskChoice(
        device="/dev/vda", size_bytes=64 * 1024**3,
        encrypt=True, passphrase="eine-lange-passphrase"))


def test_the_disk_passphrase_lands_in_creds_and_only_there(tmp_path):
    """Sie reist im Klartext - anders kann sie nicht reisen, cryptsetup
    braucht die Zeichen selbst - und deshalb in der Datei, die mit Modus
    0600 in einem Verzeichnis mit Modus 0700 liegt.

    Und NICHT in config.json. Das ist die Datei, die in einem
    Fehlerbericht landet, wenn eine Installation schiefgegangen ist.
    """
    captured = {}

    def archinstall_call(cmd, **kw):
        creds = Path(cmd[cmd.index("--creds") + 1])
        config = Path(cmd[cmd.index("--config") + 1])
        captured["creds_mode"] = stat.S_IMODE(creds.stat().st_mode)
        captured["creds"] = json.loads(creds.read_text())
        captured["config_text"] = config.read_text()
        return subprocess.CompletedProcess(cmd, 0)

    install(_encrypted_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=_openssl_or(archinstall_call))

    assert captured["creds"]["encryption_password"] == "eine-lange-passphrase"
    assert captured["creds_mode"] == 0o600
    assert "eine-lange-passphrase" not in captured["config_text"]


def test_the_encryption_block_reaches_archinstall_in_the_config(tmp_path):
    """Die andere Haelfte: der Block, der sagt WAS verschluesselt wird.
    Ohne ihn liegt die Passphrase in creds.json und archinstall macht
    nichts damit."""
    captured = {}

    def archinstall_call(cmd, **kw):
        config = Path(cmd[cmd.index("--config") + 1])
        captured["config"] = json.loads(config.read_text())
        return subprocess.CompletedProcess(cmd, 0)

    install(_encrypted_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=_openssl_or(archinstall_call))

    block = captured["config"]["disk_config"]["disk_encryption"]
    assert block["encryption_type"] == "luks"
    assert block["partitions"]


def test_an_encrypted_config_without_a_passphrase_never_reaches_archinstall(tmp_path):
    """validate() faengt es ab, bevor irgendetwas geschrieben oder
    gestartet wird - und das ist die letzte Pruefung vor dem Loeschen,
    durch die auch eine Konfigurationsdatei muss."""
    spy = Spy()
    cfg = _cfg(disk=DiskChoice(
        device="/dev/vda", size_bytes=64 * 1024**3,
        encrypt=True, passphrase=""))

    with pytest.raises(ValueError) as refusal:
        install(cfg, source=PackageSource.ONLINE, dry_run=True,
                target_root=tmp_path, runner=spy)

    assert "passphrase" in str(refusal.value)
    assert spy.cmd is None, "archinstall wurde trotzdem aufgerufen"
