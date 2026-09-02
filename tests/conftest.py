# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolation guard for the whole test suite.

The installer talks to iwctl, archinstall and NetworkManager. A careless
test could therefore drop the developer's wireless connection, overwrite
a live NetworkManager profile, or delete part of the machine running the
tests. All of those break a working system.

One hookwrapper around pytest_runtest_protocol makes that structurally
impossible rather than a matter of discipline:

  * no test may spawn a real process
  * no test may write outside a temporary directory - where "write"
    includes deleting, renaming, re-permissioning and symlinking, not
    only creating

Tests that genuinely need one of these opt in explicitly:

    @pytest.mark.allow_subprocess
    @pytest.mark.allow_system_writes

WAS DIE WACHE UEBERHAUPT VERLANGT
    Sie verbietet nicht, Prozesse zu starten oder ausserhalb von /tmp zu
    schreiben. Sie verlangt, dass es ERKLAERT ist. Siebenundachtzig
    berechtigte Faelle sind kein Problem; unerklaerte sind eins, weil
    niemand sie beim Lesen von einem Versehen unterscheiden kann.

BEIDE WACHEN HATTEN DASSELBE LOCH, GESCHLOSSEN AM 02.09.2026 (Aufgabe 86)
    Bis dahin war jede von beiden eine autouse-Vorrichtung OHNE scope,
    also FUNKTIONSWEIT. pytest baut Vorrichtungen nach
    Gueltigkeitsbereich auf - session, package, module, class, function -,
    und damit lief eine funktionsweite Wache NACH jeder modulweiten
    Vorrichtung. Eine modulweite Vorrichtung startete ihre Prozesse und
    schrieb ihre Dateien also VOR DER WACHE, und der Marker, der das
    haette erklaeren muessen, wurde nie gelesen.

    GEMESSEN, zwei instrumentierte Vollaeufe ueber die ganze Suite:
    1656 Prozessstarts kamen an der Wache vorbei, 1653 davon in der Phase
    "setup", aus 37 Vorrichtungen (36 modulweit, eine sitzungsweit) in
    22 Dateien. Nichts davon war ein Versehen - was da startete, war
    Hyprland, dbus-daemon, `ags bundle`, grim, swaybg, gtk4-broadwayd.
    Genau deshalb war es gefaehrlich: die Wache liess ausgerechnet die
    Aufrufe durch, die wirklich etwas anfassen.

    DASS BEIDE WACHEN ES HATTEN, IST DER EIGENTLICHE BEFUND, und eine
    allein zu flicken waere die halbe Arbeit an der ganzen Einsicht
    gewesen. Der Fehler steckte nicht in dem, WAS sie flicken, sondern
    darin, WANN sie eingebaut werden - und das war bei beiden dieselbe
    Zeile: `@pytest.fixture(autouse=True)`. Die Unterprozess-Wache
    verhindert, dass ein Test ein Programm startet; die Schreib-Wache
    verhindert, dass ein Test die PLATTE des Entwicklers anfasst. Die
    zweite Folge ist die groessere, und sie stand genauso offen. Gemessen
    an einer modulweiten Vorrichtung mit Path.write_text() auf einen Pfad
    im geschuetzten Arbeitsbaum: sie erreichte den echten Systemaufruf,
    derselbe Aufruf im Testkoerper kam als IsolationViolation zurueck.

    Behoben durch einen Hookwrapper um pytest_runtest_protocol. Der laeuft
    vor JEDER Vorrichtung dieses Laufs, gleich welchen
    Gueltigkeitsbereichs, weil das Aufbauen der Vorrichtungen INNERHALB
    dieses Hooks passiert.

    NICHT durch einen Wechsel des Gueltigkeitsbereichs der Wache selbst:
    eine session- oder packageweite Wache muesste unbedingt blocken, weil
    der Marker am einzelnen Lauf haengt und beim Aufbau einer
    sitzungsweiten Vorrichtung noch kein Lauf feststeht. Sie wuerde damit
    die 87 berechtigten Faelle mitreissen.

WARUM EINE MODULWEITE VORRICHTUNG NUR MODULWEIT FREIGEGEBEN WERDEN KANN
    Ein Marker am EINZELNEN LAUF gibt eine modulweite Vorrichtung
    REIHENFOLGEABHAENGIG frei, und das ist gemessen, nicht befuerchtet:

      markierter Lauf zuerst   -> 2 passed
      unmarkierter Lauf zuerst -> 3 errors, auch der markierte

    pytest legt eine modulweite Vorrichtung beim ERSTEN Lauf an, der sie
    anfordert, und speichert ihren Fehlschlag zwischen; jeder weitere
    Lauf bekommt denselben Fehler noch einmal vorgelegt, sein eigener
    Marker hin oder her. Ein Test, dessen Ergebnis an der Reihenfolge
    haengt, ist kein Test.

    Modulweites `pytestmark = pytest.mark.allow_subprocess` ist in beiden
    Reihenfolgen gruen, weil pytest es auf JEDEN Lauf des Moduls legt -
    der erste Anforderer ist damit immer markiert. Eine modulweite
    Vorrichtung braucht also eine MODULWEITE Erklaerung. Vierzehn Dateien
    dieses Baums trugen sie schon, bevor dieses Loch auffiel; die
    uebrigen wurden am 02.09.2026 nachgezogen, jede mit dem sachlichen
    Grund in ihrem Modul-Docstring.

WAS DIE WACHE AUCH JETZT NICHT SIEHT
    Alles, was ausserhalb eines Laufs passiert: Prozessstarts und
    Schreibzugriffe waehrend des SAMMELNS, also im Kopf eines
    Testmoduls. Gemessen wurden dabei zwei Aufrufe, beide harmlose
    Abfragen nach vorhandenen Werkzeugen. Der Hookwrapper haengt am
    einzelnen Lauf, weil die Freigabe an dessen Marker haengt; ein Modul,
    das beim Import ein Programm startet, hat noch keinen Lauf, an dem
    ein Marker sitzen koennte. Wer das schliessen will, braucht eine
    andere Erklaerungsform als einen Marker - und muss zuerst zeigen,
    dass es ein Problem gibt.

WHAT allow_subprocess ACTUALLY COSTS
    Not "this test may run `true`". Both guards are per-process
    monkeypatching, and monkeypatching cannot reach into a child. A test
    carrying allow_subprocess therefore hands its child BOTH permissions
    at once: the child may write anywhere the developer's own account
    may, and the write guard will never hear about it.

    Eighty-seven tests carry the marker, because the artifacts this
    project generates are shell scripts and the only honest way to test a
    shell script is to run it. So the marker is not rare and cannot be:
    what keeps it safe is the harness discipline every one of those tests
    follows, and none of it is enforced by anything in this file -

      * `env -i` with the stub directory as the WHOLE of PATH, asserted
        before the run, so a command nothing stubbed cannot reach the
        real one;
      * HOME, XDG_CONFIG_HOME and XDG_CACHE_HOME redirected inside
        tmp_path, because every path the artifact derives comes from one
        of them;
      * assert_no_missing_command() on the result, so a hole in the stub
        directory is a failure instead of an empty string the artifact
        reads as "nothing configured".

    That third one is here rather than in each harness precisely because
    it is the load-bearing half: see its own docstring.

allow_system_writes is the rarer of the two and nothing in this suite
uses it today. Both exist so the escape hatch is visible in the test
source instead of hidden in a mock.
"""
from __future__ import annotations

import builtins
import io
import multiprocessing
import multiprocessing.process
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

# Writing anywhere below these breaks the host, not the test.
#
# /mnt is the one that matters most and was missing the longest:
# installer.core.runner.install() defaults target_root to Path("/mnt"),
# so a test calling install(cfg, runner=fake) without target_root writes
# a NetworkManager profile - carrying a real wireless passphrase - into
# the HOST's filesystem.
#
# /home, /root and /srv are where a developer's own data lives, and /dev
# is where os.open("/dev/sda", O_WRONLY) goes: the single most
# destructive thing this codebase could do by accident, given that
# erasing disks is what it is for.
PROTECTED_PREFIXES = (
    "/etc",
    "/usr",
    "/boot",
    "/bin",
    "/sbin",
    "/lib",
    "/opt",
    "/var",
    "/run",
    "/sys",
    "/proc",
    "/mnt",
    "/home",
    "/root",
    "/srv",
    "/dev",
)

# The checkout itself. A repository living somewhere outside every prefix
# above (a container's /workspace, a CI /build) is otherwise fair game,
# and a test writing there rewrites the very source it is testing.
WORK_TREE = pathlib.Path(__file__).resolve().parent.parent

# WORK_TREE deliberately does NOT live in here: _is_protected() reads it
# as a module global on every call, so a test can point it somewhere else
# to exercise the overlap rules below. Baking it into this tuple at
# import time would freeze the value of the one entry that has to move.
PROTECTED_PATHS = tuple(pathlib.Path(prefix) for prefix in PROTECTED_PREFIXES)

# Die Ausnahme innerhalb von /dev. Begruendung an der Stelle, die sie
# anwendet, unten in _is_protected().
WRITABLE_DEVICES = frozenset({"/dev/null", "/dev/zero", "/dev/full"})

# Resolved once, at import time, and never asked for again while a guard
# is active. tempfile.gettempdir() is lazy: its FIRST call probes
# candidate directories by creating files in them - through os.open,
# which the write guard patches, which calls back into _is_protected(),
# which would ask tempfile.gettempdir() again. Measured: an installation
# whose first tempfile use happened inside a guarded call spun there
# instead of finishing, because the cache tempfile.gettempdir() fills in
# is only written once its own call returns.
TMP_ROOT = pathlib.Path(os.path.realpath(tempfile.gettempdir()))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "allow_subprocess: test may spawn real processes"
    )
    config.addinivalue_line(
        "markers", "allow_system_writes: test may write outside a temp directory"
    )


class IsolationViolation(BaseException):
    """Raised when a test tries to modify the host system.

    Deliberately NOT an Exception. The code under test is full of
    deliberate `except Exception` handlers - probe() swallows anything to
    decide "no network", and install() turns every post-installation
    failure into a warning so a finished installation is never reported
    as a failed one. A guard raising an ordinary exception is caught by
    exactly those handlers: the host stays safe, but the test passes
    quietly, which is how a guard stops being noticed. Measured on
    install(cfg, runner=fake) without target_root, which writes the
    wireless profile into the host's /mnt and reported the block as a
    warning nobody read.
    """


# Commands no harness may ever hand through to its real binary.
#
# A "passthrough" stub is `exec /usr/bin/jq "$@"` - the real tool, at an
# absolute path, on a stub-only PATH. That is safe for read-only text
# plumbing and for tools whose every argument in these tests lies inside
# tmp_path. It is not safe for anything below, each of which reaches
# something the test cannot take back: a privilege, a running session, a
# network, a device, a disk.
#
# Three harnesses each wrote their own version of this rule INSIDE their
# passthrough loop -
#
#     for name in PASSTHROUGH:
#         assert name not in ("hyprctl", "sudo", "nmcli")
#
# - over tuples containing none of those names, so the line ran a dozen
# times per fixture and could not have failed once. The rule itself is
# worth keeping; what it lacked was a single place to live and one test
# proving it still refuses anything. Both are here.
NEVER_PASSTHROUGH = frozenset({
    # privilege
    "sudo", "su", "doas", "pkexec", "chsh", "usermod", "useradd", "passwd",
    # the running desktop session
    "hyprctl", "hyprpm", "ags", "waybar", "swaybg", "swaync", "zepos-menu",
    "notify-send", "pkill", "pgrep", "killall", "systemctl", "dbus-send",
    "setsid", "nohup", "gsettings",
    # the sound the developer is listening to. NACHGETRAGEN am
    # 22.08.2026 (Aufgabe 64): seit audio-devices-config.template gibt es
    # eine erzeugte Datei, die `wpctl set-default` ruft - einen
    # SCHREIBENDEN Aufruf. Ein Durchreich-Stummel dafuer waere das echte
    # Programm gegen den laufenden Tondienst des Entwicklers: sein
    # Kopfhoerer waere nach dem Testlauf nicht mehr das Vorgabegeraet,
    # und nichts im Protokoll saehe danach aus. pamixer steht daneben,
    # weil das Kontrollzentrum damit stumm schaltet und Regler zieht;
    # die drei uebrigen sind die anderen Wege an denselben Dienst.
    "wpctl", "pamixer", "pactl", "pw-cli", "pw-metadata",
    # the network
    "nmcli", "iwctl", "ip", "ifconfig", "ping", "traceroute", "curl",
    "wget", "ssh", "scp",
    # printers, disks, packages - what erases or installs
    "lpadmin", "lpstat", "lpinfo", "pacman", "archinstall", "mkfs",
    "sgdisk", "parted", "dd", "mount", "umount", "swapon",
})


def assert_safe_to_passthrough(name: str) -> None:
    """Refuse to exec the real binary for a command that changes things.

    Called from every harness that builds a passthrough stub, so the
    answer is the same in all of them and changing it is one edit rather
    than three that can drift apart.
    """
    assert name not in NEVER_PASSTHROUGH, (
        f"{name} must never reach its real binary: a passthrough stub is "
        "the real command at an absolute path, and this one changes the "
        "machine the tests are running on")


# The one message a shell emits for a command that is not on PATH. There
# is no locale below `env -i`, so it is not translated.
_MISSING_COMMAND = "command not found"


def assert_no_missing_command(result, what: str = "the artifact") -> None:
    """Fail if a child reached for a command its stub directory lacks.

    BOTH STREAMS, and that is the whole point of this function existing.

    Every harness in this suite runs its artifact under `env -i` with a
    stub directory as the entire PATH, and rests its safety argument on
    this check: a command nobody stubbed is supposed to become a loud
    failure rather than a silent empty string. The argument only holds if
    the message is actually looked for where it lands.

    Most privileged call sites in these templates are written
    `2>/dev/null`, `&>/dev/null` or `2>&1`, and a stderr-only check sees
    none of those. Measured on network-diagnostic-config.template, which
    runs

        traceroute -m 10 -w 2 "$INTERNET_TEST" 2>&1 | head -15 | tee -a ...

    with no traceroute stub anywhere: three tests took that branch on
    every run, bash wrote "traceroute: command not found" onto STDOUT
    because of the 2>&1, and the harness that exists to catch exactly
    this reported clean.

    A message the artifact swallows entirely - `2>/dev/null` - cannot be
    caught here by anything, which is why the stub directories are
    complete rather than merely mostly complete.
    """
    combined = (result.stdout or "") + (result.stderr or "")
    assert _MISSING_COMMAND not in combined, (
        f"{what} called something the stub directory does not provide - "
        "so it got an empty answer instead of the real command, and "
        "whatever this test then measured was measured on that:\n"
        + combined)


def _within(path: pathlib.Path, root: pathlib.Path) -> bool:
    """Whether path is root or lies below it, compared component by
    component.

    A str.startswith() comparison gets this wrong in both directions:
    "/etcetera" is not inside "/etc" (and used to be treated as
    protected), while "/tmpfoo" is not inside "/tmp" (and used to be
    waved through as temporary).
    """
    return path == root or root in path.parents


def _is_protected(path: os.PathLike[str] | str | int) -> bool:
    if isinstance(path, int):
        # An already-open file descriptor. Whatever it points at was
        # checked when it was opened, and there is no path to compare.
        return False
    try:
        resolved = pathlib.Path(os.path.abspath(os.fspath(path)))
    except TypeError:
        return False
    real = pathlib.Path(os.path.realpath(resolved))

    in_tmp = _within(real, TMP_ROOT) or _within(resolved, TMP_ROOT)
    in_work_tree = _within(real, WORK_TREE) or _within(resolved, WORK_TREE)

    # The temporary directory is exempt - that is what tmp_path is for -
    # but the checkout wins over that exemption when it happens to live
    # inside the temporary directory itself, which is where CI systems
    # and throwaway clones routinely put it. Without this, cloning the
    # repository into /tmp silently switched the work tree's own
    # protection off, and a test rewriting the source it is testing went
    # unnoticed. Measured exactly that way: the guard's own test failed
    # in a clone under /tmp and passed everywhere else.
    #
    # The exception to the exception: if TMPDIR points INSIDE the work
    # tree, the temp exemption has to win again, or every single
    # tmp_path write would be refused.
    tmp_lives_in_work_tree = _within(TMP_ROOT, WORK_TREE)
    if in_tmp and not (in_work_tree and not tmp_lives_in_work_tree):
        return False

    if in_work_tree:
        return True

    # Die drei Namen, die ein Schreibzugriff nicht kaputt machen KANN.
    #
    # GEMESSEN AM 02.09.2026 (Aufgabe 86), und zwar erst, nachdem die
    # Wache frueh genug eingebaut wurde: `subprocess.DEVNULL` laesst
    # CPython `os.open(os.devnull, os.O_RDWR)` rufen, und /dev steht -
    # zu Recht - unter den geschuetzten Praefixen. Damit wurde jede
    # modulweite Vorrichtung abgewiesen, die ein Kind nach /dev/null
    # umleitet, obwohl daran nichts gefaehrlich ist. Gemessen an
    # tests/render/test_dock_breite.py: vier Fehler, alle in
    # desktop_session.start_bus(), alle an der Zeile, mit der
    # subprocess seine eigene Verrohrung aufbaut.
    #
    # Die Antwort darauf ist NICHT allow_system_writes auf diese
    # Dateien: das schaltet die Wache gegen /dev/sda ab, und /dev/sda
    # ist der Grund, warum /dev ueberhaupt auf der Liste steht. Es ist
    # eine Ausnahme fuer genau diese drei Namen.
    #
    # EXAKTE NAMEN, KEIN PRAEFIX - "/dev/nullX" ist nicht /dev/null,
    # und ein Praefixvergleich hier waere derselbe Fehler, den _within()
    # weiter oben schon einmal beheben musste. Und jeder der drei
    # verwirft, was man hineinschreibt, statt es zu behalten: /dev/null
    # und /dev/full nehmen nichts an, /dev/zero gibt nur Nullen zurueck.
    # /dev/random und /dev/urandom stehen ABSICHTLICH nicht dabei - ein
    # Schreibzugriff dorthin speist den Entropievorrat des Kerns und
    # aendert damit sehr wohl etwas.
    #
    # Beide Pfade muessen in der Liste stehen, der buchstaebliche und
    # der aufgeloeste: waere /dev/null auf dieser Maschine ein Verweis
    # auf etwas anderes, duerfte der Name allein die Ausnahme nicht
    # erkaufen.
    if str(resolved) in WRITABLE_DEVICES and str(real) in WRITABLE_DEVICES:
        return False

    # Both the literal path and the symlink-resolved one are checked: a
    # symlink in a harmless-looking place still writes wherever it points.
    return any(
        _within(resolved, root) or _within(real, root) for root in PROTECTED_PATHS
    )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem):
    """Install both guards around EVERYTHING one run does.

    THIS HOOK IS THE FIX FOR THE HOLE DESCRIBED AT THE TOP OF THIS FILE,
    and the reason it is a hook rather than a fixture is the ONLY thing
    that matters about it: pytest sets a run's fixtures up INSIDE this
    hook, so code placed before the `yield` runs before every fixture of
    every scope - session, package, module, class and function alike.

    Both guards are installed here, together, because they had the same
    hole for the same reason and would grow it back the same way. A
    fixture cannot guard what builds a fixture.

    Teardown of a higher-scoped fixture happens inside the protocol of the
    LAST run that needed it (pytest decides that from `nextitem`), so it
    is governed by that run's marker - consistent with its setup, which
    was governed by the FIRST requesting run's marker. Both are the
    module's own marker whenever the declaration is modulweit, which is
    why modulweit is the form these files must use.
    """
    guard = pytest.MonkeyPatch()
    if not item.get_closest_marker("allow_subprocess"):
        _install_process_guard(guard)
    if not item.get_closest_marker("allow_system_writes"):
        _install_write_guard(guard)
    try:
        return (yield)
    finally:
        guard.undo()


def _install_process_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block process execution.

    The installer's own design already injects a runner callable, so unit
    tests pass a fake and never reach this. Anything that trips it is
    calling iwctl, archinstall or pacman for real.
    """

    def blocked(*args, **kwargs):
        raise RuntimeError(
            "This test tried to start a real process. That could change the "
            "running system (iwctl, archinstall, pacman). Inject a fake "
            "runner instead, or mark the test with "
            "@pytest.mark.allow_subprocess."
        )

    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(subprocess, "call", blocked)
    monkeypatch.setattr(subprocess, "check_output", blocked)
    monkeypatch.setattr(os, "system", blocked)

    # Everything below is a way to start a process that never touches the
    # subprocess module, so patching that module alone let all of them
    # through. Nothing in src/ or installer/ uses any of them today -
    # which is the reason to close them now rather than after the first
    # one is written: a guard is only worth what it refuses, and "we do
    # not do that yet" is not a refusal.
    #
    # os.exec*() is the worst of the set, because it does not START a
    # process, it BECOMES one: the pytest session is replaced, the
    # remaining tests never run, and the report says nothing at all.
    for name in ("posix_spawn", "posix_spawnp",
                 "spawnv", "spawnve", "spawnvp", "spawnvpe",
                 "spawnl", "spawnle", "spawnlp", "spawnlpe",
                 "execv", "execve", "execvp", "execvpe",
                 "execl", "execle", "execlp", "execlpe",
                 "fork", "forkpty"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, blocked)

    # multiprocessing's default start method on Linux is fork(), and its
    # child inherits neither of these fixtures' patches - it inherits the
    # state they had at fork time and then leaves the guard's scope
    # entirely.
    monkeypatch.setattr(multiprocessing, "Process", blocked)
    monkeypatch.setattr(multiprocessing.process.BaseProcess, "start", blocked)


def _install_write_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block every modifying access to a system directory.

    write_profile() takes a target root so tests can point it at tmp_path.
    If one ever points it at "/" - or leaves runner.install()'s default of
    /mnt in place - this turns a wrecked host into a failed test.

    Creation is not the only way to wreck a host, which is why deleting,
    renaming, re-permissioning and symlinking are patched here too: a
    test could previously not create /etc/hostname, but could delete it.
    """

    def guard(path, action: str) -> None:
        if _is_protected(path):
            raise IsolationViolation(
                f"This test tried {action} on '{path}'. That is outside a "
                "temporary directory and would change the running system. "
                "Use the tmp_path fixture."
            )

    WRITE = "to write"
    DELETE = "to delete"
    RENAME = "to rename"
    CHMOD = "to change the permissions"
    LINK = "to create a link"
    MKDIR = "to create a directory"

    def patch_path_method(name: str, action: str, *, arguments: bool = False) -> None:
        """Wrap one pathlib.Path method so it checks before it acts.

        arguments=True also checks the method's first positional argument,
        which is where the DESTINATION of a rename or a symlink lives -
        moving a harmless temporary file onto /etc/passwd is a write to
        /etc/passwd, however innocent the source looks.
        """
        real = getattr(pathlib.Path, name)

        def wrapper(self, *args, **kwargs):
            guard(self, action)
            if arguments and args:
                guard(args[0], action)
            return real(self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, name, wrapper)

    def patch_os_function(name: str, action: str, *, paths: int = 1) -> None:
        """Wrap one os function the same way.

        Calls carrying a dir_fd are let through: their path is relative to
        a directory file descriptor and cannot be resolved here at all -
        os.path.abspath() would silently measure it against the current
        working directory instead, and reject perfectly legitimate work.
        shutil.rmtree() takes exactly that route on Linux, and every
        installer test that cleans up a temporary workdir goes through it.
        The path handed to rmtree() itself is checked below, before any of
        those relative calls happen.
        """
        real = getattr(os, name)

        def wrapper(*args, **kwargs):
            if kwargs.get("dir_fd") is None:
                for argument in args[:paths]:
                    guard(argument, action)
            return real(*args, **kwargs)

        monkeypatch.setattr(os, name, wrapper)

    patch_path_method("write_text", WRITE)
    patch_path_method("write_bytes", WRITE)
    patch_path_method("touch", WRITE)
    patch_path_method("mkdir", MKDIR)
    patch_path_method("unlink", DELETE)
    patch_path_method("rmdir", DELETE)
    patch_path_method("chmod", CHMOD)
    patch_path_method("rename", RENAME, arguments=True)
    patch_path_method("replace", RENAME, arguments=True)
    patch_path_method("symlink_to", LINK, arguments=True)
    patch_path_method("hardlink_to", LINK, arguments=True)

    patch_os_function("remove", DELETE)
    patch_os_function("unlink", DELETE)
    patch_os_function("rmdir", DELETE)
    patch_os_function("removedirs", DELETE)
    patch_os_function("mkdir", MKDIR)
    patch_os_function("makedirs", MKDIR)
    patch_os_function("chmod", CHMOD)
    patch_os_function("chown", CHMOD)
    patch_os_function("truncate", WRITE)
    patch_os_function("rename", RENAME, paths=2)
    patch_os_function("replace", RENAME, paths=2)
    patch_os_function("symlink", LINK, paths=2)
    patch_os_function("link", LINK, paths=2)

    # Four more ways to modify something that is already there, none of
    # which goes anywhere near open(). mkfifo and mknod CREATE - a named
    # pipe over /etc/hostname is still a destroyed /etc/hostname - and
    # utime and setxattr change a file the guard would otherwise have to
    # watch somebody else notice.
    for name, action in (("mkfifo", WRITE), ("mknod", WRITE),
                         ("utime", WRITE), ("setxattr", WRITE),
                         ("removexattr", WRITE), ("lchown", CHMOD)):
        if hasattr(os, name):
            patch_os_function(name, action)

    real_path_open = pathlib.Path.open
    real_builtin_open = builtins.open
    real_io_open = io.open
    real_os_open = os.open
    real_rmtree = shutil.rmtree
    real_move = shutil.move

    def _is_write_mode(mode: str) -> bool:
        return any(flag in mode for flag in ("w", "a", "x", "+"))

    def path_open(self, mode="r", *args, **kwargs):
        if _is_write_mode(mode):
            guard(self, WRITE)
        return real_path_open(self, mode, *args, **kwargs)

    def builtin_open(file, mode="r", *args, **kwargs):
        # A test calling the plain builtin used to slip past the guard
        # entirely, because only pathlib.Path.open was wrapped.
        if _is_write_mode(mode):
            guard(file, WRITE)
        return real_builtin_open(file, mode, *args, **kwargs)

    def io_open(file, mode="r", *args, **kwargs):
        # io.open and builtins.open are the SAME function object and two
        # DIFFERENT module attributes. The comment that used to sit above
        # builtin_open reasoned that wrapping the builtin covered io.open
        # as well, and it does not: rebinding builtins.open leaves
        # io.open pointing at the original, so `io.open(p, "w")` wrote
        # into the protected work tree with the guard active and said
        # nothing. Measured, not deduced.
        if _is_write_mode(mode):
            guard(file, WRITE)
        return real_io_open(file, mode, *args, **kwargs)

    def os_open(path, flags, mode=0o777, **kwargs):
        # os.open bypasses every pathlib patch. A Task 7 review surfaced a
        # proposed fix that would have written through this hole into the
        # developer's own /etc/NetworkManager.
        if kwargs.get("dir_fd") is None and flags & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
        ):
            guard(path, WRITE)
        return real_os_open(path, flags, mode, **kwargs)

    def rmtree(path, *args, **kwargs):
        guard(path, DELETE)
        return real_rmtree(path, *args, **kwargs)

    def move(src, dst, *args, **kwargs):
        guard(src, RENAME)
        guard(dst, RENAME)
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", path_open)
    monkeypatch.setattr(builtins, "open", builtin_open)
    monkeypatch.setattr(io, "open", io_open)
    monkeypatch.setattr(os, "open", os_open)
    monkeypatch.setattr(shutil, "rmtree", rmtree)
    monkeypatch.setattr(shutil, "move", move)
