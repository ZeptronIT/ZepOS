# SPDX-License-Identifier: GPL-3.0-or-later
"""Hand the finished configuration over to archinstall.

Integration happens through archinstall's documented CLI rather than its
Python modules: the CLI is a stable contract, the internals change
between releases.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Sequence

from .disks import Disk
from .disks import list_disks as _lsblk_list_disks
from .firmware import firmware_problem
from .i18n import _
from .model import InstallConfig
from .netprofile import profile_problem, write_profile
from .pacmanconf import rewrite_zepos_repository
from .passwords import hash_password
from .preflight import base_system_problem, clock_problem
from .source import PackageSource, probe
from .translate import to_archinstall_config, to_archinstall_creds
from .usersettings import write_user_settings
from .validate import validate

Runner = Callable[..., subprocess.CompletedProcess]
DiskLister = Callable[..., Sequence[Disk]]
Warner = Callable[[str], None]


class InstallationRefused(RuntimeError):
    """A refusal issued before archinstall was ever invoked.

    Its message is meant for the user like any other, but the TYPE
    carries a second fact no message can: nothing on the target disk has
    been touched. Every raise site below is reached before archinstall
    starts - the firmware check, the disk re-check, and archinstall
    failing to launch at all - so a surface catching this may tell the
    user their disk is unchanged, which after a confirmed erase and a
    "Starting installation." is the one thing they cannot see for
    themselves.

    Anything else escaping install() must NOT be turned into that
    statement: a failure raised while archinstall was running may well
    have left a partitioned disk behind, and "nothing was changed" would
    then be a dangerous claim rather than a reassuring one.
    """


def _warn_to_stderr(message: str) -> None:
    """Default warning channel: the text interface runs on a terminal, so
    a warning printed here is seen. A surface with no terminal (the GTK4
    one) injects its own collector instead and shows what it collected in
    its final dialog."""
    print(message, file=sys.stderr)


def _require_target_disk(
    cfg: InstallConfig, list_disks: DiskLister, runner: Runner
) -> None:
    """Re-enumerate the disks immediately before archinstall erases one.

    The disk was chosen when the surface built its list, which on the
    GTK4 side happens once at window construction. A device unplugged and
    plugged back in during the session keeps its name in the
    configuration while the kernel may have handed that name to a
    different device - and wipe defaults to True. Nothing else in this
    codebase looks at the hardware again between the choice and the
    erase: validate() only checks the stored size, and list_disks()
    itself runs only while a list is being built.

    Comparing the size as well as the name is what makes this more than a
    presence check: two devices can carry the same /dev name at different
    times, but not the same name AND the same byte count by accident.
    """
    present = {disk.device: disk.size_bytes for disk in list_disks(runner=runner)}
    if cfg.disk.device not in present:
        raise InstallationRefused(
            _("The selected disk {device} is no longer available. It may have been unplugged, or it may now be mounted.")
            .format(device=cfg.disk.device)
        )
    if present[cfg.disk.device] != cfg.disk.size_bytes:
        raise InstallationRefused(
            _("The disk {device} is not the one that was selected: its size has changed since then.")
            .format(device=cfg.disk.device)
        )


def install(
    cfg: InstallConfig,
    *,
    source: PackageSource | None = None,
    dry_run: bool = False,
    target_root: Path = Path("/mnt"),
    runner: Runner | None = None,
    log_path: Path | None = None,
    list_disks: DiskLister | None = None,
    is_uefi: Callable[[], bool] | None = None,
    on_warning: Warner | None = None,
    base_problem: Callable[[], str] | None = None,
    clock_wait: Callable[[], str] | None = None,
) -> int:
    """Run an installation and return archinstall's exit code.

    The injected `runner` drives EVERY subprocess this call makes, not
    only archinstall: password hashing and the disk re-check shell out to
    openssl and lsblk through the same callable. A runner scoped to
    archinstall alone would silently break credential hashing.

    `log_path`, when given, receives archinstall's own output (stdout and
    stderr combined). Without it the output goes wherever this process's
    output goes, which is right for a text interface running on a
    terminal and useless for a graphical one, whose terminal the user
    never sees.

    `on_warning` receives problems that must not stop an installation.
    Two kinds reach it, and neither may be raised as an error: the ones
    that appear AFTER archinstall reported success - at that point the
    machine is installed, and an error would tell the user their
    installation failed, inviting a second erase of a disk that already
    carries a working system - and the clock warning below, which is
    about a machine that will very probably install correctly anyway.

    `base_problem` and `clock_wait` are the two measurements taken before
    anything is touched; installer/core/preflight.py says what they
    measure and what hung before they existed. Injected rather than bound
    so a caller can run an installation without a network of its own.
    """
    # Resolved here, not bound as a default: a default argument captures
    # subprocess.run at import time, which the test suite's isolation guard
    # cannot intercept.
    runner = runner or subprocess.run
    list_disks = list_disks or _lsblk_list_disks
    on_warning = on_warning or _warn_to_stderr
    base_problem = base_problem or base_system_problem
    clock_wait = clock_wait or clock_problem
    # is_uefi is deliberately NOT resolved here: firmware_problem()
    # resolves it at call time itself, and doing it twice would leave two
    # places to change when the default moves.

    # Checked before anything else, because no answer the user could give
    # would change it. WARUM eine BIOS-Maschine abgelehnt wird, steht an
    # genau einer Stelle - im Kopf von installer/core/firmware.py - und
    # nicht hier. Hier stand einmal eine zweite Fassung derselben
    # Begruendung, und als translate.py von systemd-boot auf GRUB
    # umgestellt wurde, war sie an drei von vier Stellen falsch, ohne
    # dass irgendetwas es gemeldet haette.
    #
    # Both surfaces ask firmware_problem() the same question before their
    # first question, so a user on such a machine learns it up front
    # rather than here. This check stays regardless: it is the last point
    # before the erase, and it is the only one a caller cannot skip.
    problem = firmware_problem(is_uefi=is_uefi)
    if problem:
        raise InstallationRefused(problem)

    # Refused before anything else runs. disk.wipe defaults to True, so an
    # install that should never have started must not get anywhere near
    # invoking archinstall.
    findings = validate(cfg)
    if findings:
        raise ValueError("; ".join(findings))

    # DIE ZWEI MESSUNGEN VOR DER LOESCHUNG, und warum sie hier stehen
    # und nicht erst in archinstall.
    #
    # Gemessen am 17.08.2026 (die Belege stehen im Kopf von
    # installer/core/preflight.py): ohne Netz haengt archinstall 4.4 in
    # _verify_service_stop() unbegrenzt am Warten auf die Uhr - und zwar
    # NACH perform_filesystem_operations(), also vor einer bereits
    # geteilten und formatierten Platte. Der Nutzer sieht ein stehendes
    # Bild und weiss nicht, ob er warten oder ausschalten soll.
    #
    # Hier ist die frueheste Stelle, an der beide Fragen mit einer
    # Aussage beantwortet werden koennen, die noch stimmt: es ist nichts
    # geschrieben worden, also darf die Ablehnung ein
    # InstallationRefused sein - und das heisst fuer jede Oberflaeche
    # "Auf der Platte wurde nichts geaendert".
    #
    # Fuer einen Trockenlauf keines von beiden: --dry-run schreibt
    # nichts und holt kein Paket, also ist die Erreichbarkeit der Basis
    # dort keine Bedingung, sondern eine Huerde ohne Zweck.
    # tests/integration/test_dry_run.sh faehrt genau so.
    if not dry_run:
        problem = base_problem()
        if problem:
            raise InstallationRefused(problem)

        # Nach der Erreichbarkeit und nicht davor: die Frist laeuft nur
        # ab, wenn es ein Netz gibt, das HTTPS traegt - und dann stellt
        # timesyncd die Uhr binnen Sekunden. Umgekehrt haetten wir ohne
        # Netz erst dreissig Sekunden gewartet, um danach zu sagen, dass
        # es kein Netz gibt.
        warning = clock_wait()
        if warning:
            on_warning(warning)

    source = source or probe()

    workdir = Path(tempfile.mkdtemp(prefix="zepos-install-"))
    config_path = workdir / "config.json"
    creds_path = workdir / "creds.json"

    try:
        config_path.write_text(
            json.dumps(to_archinstall_config(cfg, source), indent=2), encoding="utf-8"
        )

        # The single injected runner drives every subprocess this call
        # makes, not just the final archinstall invocation:
        # to_archinstall_creds() hashes passwords via hash_password(),
        # which shells out to openssl by default. Routing that through
        # the same runner means one fake supplied by a caller (or a
        # test) is enough to keep the whole operation free of real
        # subprocesses - a second, hidden one would defeat that.
        creds_json = json.dumps(
            to_archinstall_creds(
                cfg, hasher=lambda plain: hash_password(plain, runner=runner)
            ),
            indent=2,
        )
        # creds.json holds password hashes. tempfile.mkdtemp() already
        # makes workdir readable only by its own creator (mode 0700), but
        # narrowing the umask closes the brief window between file
        # creation and the chmod below too - the same defence
        # netprofile.py applies to the wireless profile's passphrase.
        previous_umask = os.umask(0o077)
        try:
            creds_path.write_text(creds_json, encoding="utf-8")
        finally:
            os.umask(previous_umask)
        creds_path.chmod(0o600)
    except Exception:
        # Nothing has been handed to archinstall yet at this point, so an
        # empty or half-written workdir left behind here is just litter,
        # not diagnostic evidence - unlike a workdir left by a failed
        # archinstall RUN (see below), which is kept on purpose.
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    # As late as possible on purpose: this is the last moment before the
    # erase. Skipped for a dry run, which touches no disk at all - and
    # whose target may deliberately be a device list_disks() filters out,
    # such as the loop device tests/integration/test_dry_run.sh installs
    # onto.
    if not dry_run:
        try:
            _require_target_disk(cfg, list_disks, runner)
        except Exception:
            # Nothing has been handed to archinstall yet, so the workdir
            # is litter rather than evidence - same reasoning as above.
            shutil.rmtree(workdir, ignore_errors=True)
            raise

    command = [
        "archinstall",
        "--config", str(config_path),
        "--creds", str(creds_path),
        "--silent",
        # Verified against archinstall 4.4's own argument parser: the flag
        # is spelled "--mountpoint" (one word) and defaults to /mnt.
        "--mountpoint", str(target_root),
        # DER SCHALTER, DER DAS EINFRIEREN ABSTELLT.
        #
        # archinstall 4.4, lib/installer.py:189-202, wartet ohne diesen
        # Schalter in einem `while True` darauf, dass `timedatectl show
        # --property=NTPSynchronized` `yes` sagt. Ohne Netz sagt es das
        # nie, und die Schleife hat keine Frist - der Assistent steht
        # dann fuer immer, hinter einer schon geteilten Platte. Genau
        # dieser Befund kam am 17.08.2026 von echter Hardware.
        #
        # Abgeschaltet und ERSETZT, nicht bloss abgeschaltet: die Frage,
        # die archinstall stellt, ist berechtigt (eine falsch gehende
        # Uhr laesst gpg Signaturen ablehnen), nur ihre Wartezeit war
        # es nicht. preflight.clock_problem() stellt sie oben mit einer
        # Frist von dreissig Sekunden und macht aus dem Ablauf eine
        # Warnung statt eines Stillstands.
        "--skip-ntp",
    ]
    if source is PackageSource.OFFLINE:
        command.append("--offline")
    if dry_run:
        command.append("--dry-run")

    try:
        result = _run_archinstall(runner, command, log_path)
    except OSError as exc:
        # archinstall missing or not executable - a real scenario on a
        # live image whose squashfs was built without it. subprocess.run
        # raises before any CompletedProcess exists, so this has to be
        # caught around the call itself; inspecting result.returncode
        # afterwards would never see it. The workdir is deliberately left
        # in place: config.json and creds.json are the only record of
        # what was about to be attempted.
        raise InstallationRefused(
            _("Could not run archinstall: {reason}").format(reason=exc)
        ) from exc

    # Only touch the target, and only discard the credentials, once
    # archinstall reports success. Writing the wireless profile any
    # earlier would place it into a half-installed or absent filesystem;
    # discarding creds.json any earlier - or on failure - would destroy
    # the only record of what was attempted, which a failed install still
    # needs for diagnosis.
    if result.returncode == 0:
        try:
            # Never for a dry run: --dry-run installs nothing, so there is
            # no installed system to finish off and no target filesystem
            # to write into. target_root still points at the HOST's /mnt
            # by default, where these writes landed for real - one of them
            # the wireless passphrase in clear text, in a directory no
            # installation ever mounted and nobody ever cleans up.
            if not dry_run:
                _finish_target(cfg, target_root, on_warning)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    return result.returncode


def _run_archinstall(
    runner: Runner, command: list[str], log_path: Path | None
) -> subprocess.CompletedProcess:
    """Invoke archinstall, sending its output to log_path when one was given.

    Without a log path the output is inherited, which is what a text
    interface on a terminal wants. A graphical surface has no terminal
    the user can see, so it passes a path and reads the file back while
    the installation runs - the only progress the user gets during the
    minutes archinstall takes.
    """
    if log_path is None:
        return runner(command)
    with open(log_path, "w", encoding="utf-8") as log_file:
        return runner(command, stdout=log_file, stderr=subprocess.STDOUT)


def _finish_wireless(
    cfg: InstallConfig, target_root: Path, on_warning: Warner
) -> None:
    """Spec §8.3: the connection profile has to be written into the
    target explicitly, or a laptop with no ethernet port boots a freshly
    installed system with no way to get online."""
    if cfg.wifi is None:
        return
    problem = profile_problem(write_profile(cfg.wifi, target_root))
    if problem:
        on_warning(problem)


def _finish_user_settings(
    cfg: InstallConfig, target_root: Path, on_warning: Warner
) -> None:
    """The two ZepOS answers - plugins, weather location - that both
    surfaces ask for and that nothing else would carry into the target."""
    write_user_settings(
        cfg.zepos, target_root, [user.username for user in cfg.users]
    )


def _finish_repository(
    cfg: InstallConfig, target_root: Path, on_warning: Warner
) -> None:
    """Spec §8.5b: exactly one [zepos] section, pointing online.

    archinstall leaves two, and for an offline installation both name
    `file:///opt/zepos-repo` - a directory of the live medium that stops
    existing the moment it is unplugged. pacmanconf.py has the full
    account of how the duplicate arises.
    """
    rewrite_zepos_repository(target_root)


# Each step is guarded separately below, and that is the point of the
# split rather than a consequence of it: these are three independent
# obligations of spec §8, and one that cannot be met must not silently
# cancel the others. A single try block around all three meant that a
# wireless profile which could not be written - a target filesystem that
# cannot carry mode 0600, say - also left the machine pointing at a
# repository that no longer exists, with nothing said about the second
# failure because the first one had already jumped past it.
_FINISHING_STEPS = (_finish_wireless, _finish_user_settings, _finish_repository)


def _finish_target(
    cfg: InstallConfig, target_root: Path, on_warning: Warner
) -> None:
    """Everything that happens in the freshly installed system.

    Every failure in here is reported as a warning, never raised: by the
    time this runs archinstall has reported success, so the machine IS
    installed. An exception escaping install() at this point would be
    presented as a failed installation, and the obvious response to a
    failed installation - start it again - would erase a disk that
    already carries a working system.
    """
    for step in _FINISHING_STEPS:
        try:
            step(cfg, target_root, on_warning)
        except Exception as exc:
            on_warning(
                _("The system was installed, but a final step did not finish: {reason}")
                .format(reason=exc)
            )
