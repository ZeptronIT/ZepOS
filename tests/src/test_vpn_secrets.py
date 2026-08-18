# SPDX-License-Identifier: GPL-3.0-or-later
"""The three VPN scripts, executed, with every path they write measured.

The branch review found three secrets on disk, and none of them is
visible to a text-level assertion - each one is a file that exists only
while a script runs:

  * the login password, cached in $XDG_RUNTIME_DIR/vpn-sudo-cache so a
    background watcher could run `sudo -S` unattended. Written with
    `echo >` and narrowed by a `chmod` afterwards, so it was readable by
    everyone for the moment in between;
  * the swanctl configuration, containing the pre-shared key, written to
    /tmp/work.conf.$$ - a predictable name in a world-readable directory,
    mode 0644, surviving several `sudo` round trips;
  * the username and the one-time 2FA token, appended to
    /tmp/vpn-control-<date>.log.

Two things follow for the tests. A final-mode assertion is worthless
here: `echo > f; chmod 600 f` ends at 0600 and was still world-readable
in between. So the modes are sampled the way the review sampled them -
WHILE the file exists, from inside every stub the script calls, and the
child is started with `umask 000` so that a file whose privacy depends on
a later `chmod` is caught rather than accidentally created private.

And the mechanism that replaces the cached password has to be exercised,
not assumed: a `systemd --user` unit and hyprland's `exec-once` both give
a process no terminal and no askpass helper, so bare `sudo` cannot ask
anybody anything. The watcher tests below run under exactly that -
`env -i`, no TTY, no SUDO_ASKPASS, no password anywhere in the
environment or on disk - with a `sudo` stub that answers ONLY what the
generated sudoers drop-in allows, and refuses everything else the way
`sudo -n` does.

Safety: every child is started through `env -i` with PATH pointing at the
stub directory and nothing else, which _child_path() asserts before each
run. A command with no stub therefore fails with "command not found"
instead of reaching the real `sudo`, `ip` or `swanctl`. The `sudo` stub
never executes what it is handed - it answers from canned fixtures - so
no privileged command can run even by accident, and the file-touching
stubs refuse any path outside the test's own directory. Every address
used here is from a documentation range (RFC 5737), and every secret is
an obvious literal that exists nowhere but in this file.
"""
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

# The shared backstop, from tests/conftest.py: a command the stub
# directory does not provide has to be a failure, not an empty string.
import conftest

SRC = Path(__file__).resolve().parents[2] / "src"

BASH = "/bin/bash"
ENV = "/usr/bin/env"
PYTHON = "/usr/bin/python3"

# Obvious literals, so that finding one in a file is unambiguous.
USERNAME = "testnutzer"
PASSWORD = "GEHEIM-PASSWORT-4711"
SUDO_PASS = "GEHEIM-SUDOPASS-4712"
TOKEN = "GEHEIM-TOKEN-4713"
PSK = "GEHEIM-PSK-4714"
SECRETS = (PASSWORD, SUDO_PASS, TOKEN, PSK)

CONNECTION = "work"
# TEST-NET-2, reserved for documentation.
VPN_SERVER_PROBE = "198.51.100.9"


# --------------------------------------------------------------------
# stubs
# --------------------------------------------------------------------
#
# Every stub is a Python script with an absolute interpreter path, so it
# runs under a PATH that holds nothing but the stub directory. Python
# rather than bash because two of the things these tests have to do -
# read a file's mode at the instant a command is called, and refuse to
# touch a path outside the sandbox - have no honest shell equivalent
# once `stat` is not on PATH either.

STUB_PREAMBLE = '''#!{python}
"""Test stub for `{name}`. Records its call, samples modes, then answers."""
import os
import pathlib
import sys

NAME = {name!r}
CALLS = pathlib.Path({calls!r})
MODES = pathlib.Path({modes!r})
SANDBOX = [pathlib.Path(p) for p in {sandbox!r}]
FIXTURES = pathlib.Path({fixtures!r})

ARGS = sys.argv[1:]


def record_call():
    with CALLS.open("a", encoding="utf-8") as handle:
        handle.write(NAME + " " + " ".join(ARGS) + "\\n")


def sample(path):
    """One (command, path, mode) line - the measurement the review made.

    Taken while the file is in use rather than after the run, because a
    file that is created world-readable and narrowed a moment later ends
    the run at the right mode and was still readable in between.
    """
    try:
        mode = os.stat(path, follow_symlinks=False).st_mode
    except OSError:
        return
    with MODES.open("a", encoding="utf-8") as handle:
        handle.write("%s %s %04o\\n" % (NAME, path, mode & 0o7777))


def sample_everything():
    # Every path this call was handed...
    for argument in ARGS:
        if argument.startswith("/"):
            sample(argument)
    # ...and everything the scripts may have created meanwhile.
    for root in SANDBOX:
        for current, directories, files in os.walk(root):
            for entry in list(directories) + list(files):
                sample(os.path.join(current, entry))


def inside_sandbox(path):
    """Whether a file-touching stub may act on this path for real.

    Anything else is recorded and answered with success, never carried
    out: a stub that wrote where it was told would put /etc back within
    reach of a test run.
    """
    resolved = pathlib.Path(os.path.abspath(path))
    return any(resolved == root or root in resolved.parents for root in SANDBOX)


record_call()
sample_everything()
'''


def _write_stub(directory: Path, name: str, body: str, *,
                calls: Path, modes: Path, sandbox: list[Path],
                fixtures: Path) -> None:
    script = STUB_PREAMBLE.format(
        python=PYTHON, name=name, calls=str(calls), modes=str(modes),
        sandbox=[str(p) for p in sandbox], fixtures=str(fixtures),
    ) + body
    path = directory / name
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


# The `sudo` stub. It never runs what it was handed: it decides whether
# the generated policy allows the command, and answers from fixtures.
#
# The policy patterns come out of the generated sudoers drop-in, matched
# with fnmatch - which is what sudo itself uses for command arguments, and
# without FNM_PATHNAME, so a `*` covers a path separator here exactly as
# it does there. Nothing in the policy means nothing is allowed, which is
# what a machine without the drop-in installed looks like.
SUDO_BODY = '''
import fnmatch

POLICY = []
policy_file = FIXTURES / "policy.txt"
if policy_file.exists():
    POLICY = [line for line in
              policy_file.read_text(encoding="utf-8").splitlines() if line]

command = list(ARGS)
READS_PASSWORD = False
while command and command[0].startswith("-"):
    flag = command.pop(0)
    if flag in ("-S", "--stdin"):
        READS_PASSWORD = True
    if flag in ("-p", "-u", "-g") and command:
        command.pop(0)

# Only `sudo -S` reads a PASSWORD from standard input; otherwise stdin
# belongs to the command being run and may legitimately carry a
# configuration file. The distinction is the whole point: it is written
# down and then ACCEPTED, the way the real sudo -S accepts a correct
# password, so an implementation that still pipes the login password
# around fails on the assertion rather than on a stub that refused it.
PASSWORD_PIPED = ""
if READS_PASSWORD and not sys.stdin.isatty():
    PASSWORD_PIPED = sys.stdin.read().strip()
    if PASSWORD_PIPED:
        with CALLS.open("a", encoding="utf-8") as handle:
            handle.write("sudo-password-on-stdin " + PASSWORD_PIPED + "\\n")

if not command:
    # `sudo -v`: refresh the timestamp. Without a password there is
    # nobody to ask - no terminal, no askpass helper - so it fails.
    sys.exit(0 if PASSWORD_PIPED else 1)

# sudo resolves a bare command name through its own secure_path before
# matching it against the policy, so the stub does the same.
if "/" not in command[0]:
    command[0] = "/usr/bin/" + command[0]
line = " ".join(command)

if not PASSWORD_PIPED and not any(
        fnmatch.fnmatchcase(line, pattern) for pattern in POLICY):
    sys.stderr.write("sudo: a password is required\\n")
    sys.exit(1)

with CALLS.open("a", encoding="utf-8") as handle:
    handle.write("sudo-allowed " + line + "\\n")

# Canned answers for the few commands whose OUTPUT the scripts read.
text = " ".join(command)
if "--list-sas" in text:
    sas = FIXTURES / "sas.txt"
    sys.stdout.write(sas.read_text(encoding="utf-8") if sas.exists() else "")
elif "--initiate" in text:
    outcome = FIXTURES / "initiate.txt"
    sys.stdout.write(outcome.read_text(encoding="utf-8")
                     if outcome.exists() else "initiate completed successfully\\n")
elif "xfrm policy" in text and "update" not in text and "flush" not in text:
    policy = FIXTURES / "xfrm.txt"
    sys.stdout.write(policy.read_text(encoding="utf-8") if policy.exists() else "")
elif "is-active" in text:
    sys.stdout.write("active\\n")
elif text.endswith("/usr/bin/true"):
    pass
sys.exit(0)
'''

# The unprivileged network commands. `ip` answers from fixtures so a test
# can put the machine into a half-up state; it never touches the machine
# it runs on.
IP_BODY = '''
if ARGS[:2] == ["route", "show"] or ARGS[:1] == ["route"] and "show" in ARGS[:2]:
    route = FIXTURES / "route.txt"
    sys.stdout.write(route.read_text(encoding="utf-8") if route.exists() else "")
    sys.exit(0)
if ARGS[:2] == ["route", "get"]:
    sys.stdout.write("%s dev eth0 src 198.51.100.7\\n" % (ARGS[2] if len(ARGS) > 2 else ""))
    sys.exit(0)
if ARGS[:1] == ["route"]:
    route = FIXTURES / "route.txt"
    sys.stdout.write(route.read_text(encoding="utf-8") if route.exists() else "")
    sys.exit(0)
if "addr" in ARGS[:2]:
    addresses = FIXTURES / "addr.txt"
    sys.stdout.write(addresses.read_text(encoding="utf-8") if addresses.exists() else "")
    sys.exit(0)
if ARGS[:2] == ["xfrm", "policy"]:
    policy = FIXTURES / "xfrm.txt"
    sys.stdout.write(policy.read_text(encoding="utf-8") if policy.exists() else "")
    sys.exit(0)
sys.exit(0)
'''

PING_BODY = '''
target = ARGS[-1] if ARGS else ""
reachable = FIXTURES / "reachable.txt"
hosts = reachable.read_text(encoding="utf-8").split() if reachable.exists() else []
sys.exit(0 if target in hosts else 1)
'''

PGREP_BODY = '''
marker = FIXTURES / "charon-running"
sys.exit(0 if marker.exists() else 1)
'''

# The file-touching stubs. Each acts for real inside the test's own
# directory and only records what it was asked to do anywhere else, so a
# script reaching for /etc cannot reach it from here.
MKDIR_BODY = '''
targets = [a for a in ARGS if not a.startswith("-")]
for target in targets:
    if inside_sandbox(target):
        os.makedirs(target, exist_ok=True)
sys.exit(0)
'''

RM_BODY = '''
targets = [a for a in ARGS if not a.startswith("-")]
for target in targets:
    if inside_sandbox(target):
        try:
            os.unlink(target)
        except OSError:
            pass
sys.exit(0)
'''

# Recorded rather than passed through, because a `chmod` on a file that
# already carries a secret is the defect: it proves the file existed at
# some other mode first. It still does its job inside the sandbox, so a
# script that needs it keeps working - it just cannot do it unseen.
CHMOD_BODY = '''
mode, targets = None, []
for argument in ARGS:
    if argument.startswith("-"):
        continue
    if mode is None:
        mode = argument
    else:
        targets.append(argument)
for target in targets:
    if inside_sandbox(target):
        try:
            os.chmod(target, int(mode, 8))
        except (OSError, ValueError, TypeError):
            pass
sys.exit(0)
'''

TRUE_BODY = "sys.exit(0)\n"
FALSE_BODY = "sys.exit(1)\n"

# `date` and `tee` are plumbing for the scripts' log() functions. They
# stay real - `tee` writes where the script points it, inside the
# sandbox - because a log line the test cannot read is a leak the test
# cannot find.
#
# `python3` is the same kind of plumbing: it runs src/vpn.py, which is
# where the three scripts read the tunnel's own address and state out of
# `swanctl --list-sas` rather than each matching interface addresses
# against a pattern. Everything it does here is reading and parsing - the
# `ip` and `pgrep` it may reach for are stubs like every other command,
# because the child's PATH is the stub directory and nothing else.
PASSTHROUGH = ("date", "id", "cat", "grep", "sed", "awk", "head", "tail",
               "cut", "tr", "wc", "od", "sort", "flock", "timeout", "tee",
               "install", "cp", "true", "env", "stat", "readlink", "basename",
               "dirname", "mktemp", "sleep", "python3")

# Never, under any circumstance, reached for real by these tests.
FORBIDDEN_PASSTHROUGH = ("sudo", "ip", "swanctl", "systemctl", "nmcli",
                         "pkexec", "killall", "pkill", "resolvectl",
                         "journalctl", "notify-send")


@pytest.fixture
def sandbox(tmp_path):
    """One prepared run: stub directory, fixtures, environment, roots."""
    return Sandbox(tmp_path)


class Sandbox:
    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.runtime = tmp_path / "runtime"
        self.config = tmp_path / "config"
        self.tmpdir = tmp_path / "tmp"
        self.stubs = tmp_path / "stubs"
        self.fixtures = tmp_path / "fixtures"
        self.calls = tmp_path / "calls.txt"
        self.modes = tmp_path / "modes.txt"
        for directory in (self.home, self.runtime, self.config, self.tmpdir,
                          self.stubs, self.fixtures):
            directory.mkdir(parents=True, exist_ok=True)
        # XDG_RUNTIME_DIR is 0700 on a real system; the tests reproduce
        # that so a mode measured inside it means what it means there.
        self.runtime.chmod(0o700)
        self._build_stubs()

    # -- construction -------------------------------------------------

    @property
    def sandbox_roots(self) -> list[Path]:
        return [self.home, self.runtime, self.config, self.tmpdir]

    def _stub(self, name: str, body: str) -> None:
        _write_stub(self.stubs, name, body, calls=self.calls,
                    modes=self.modes, sandbox=self.sandbox_roots,
                    fixtures=self.fixtures)

    def _build_stubs(self) -> None:
        self._stub("sudo", SUDO_BODY)
        self._stub("ip", IP_BODY)
        self._stub("ping", PING_BODY)
        self._stub("pgrep", PGREP_BODY)
        self._stub("mkdir", MKDIR_BODY)
        self._stub("rm", RM_BODY)
        self._stub("chmod", CHMOD_BODY)
        for name in ("notify-send", "swanctl", "systemctl", "journalctl",
                     "nmcli", "killall", "pkexec", "resolvectl", "curl",
                     "nslookup", "host", "yad", "kitty", "visudo", "logger",
                     "setsid"):
            self._stub(name, TRUE_BODY)
        for name in PASSTHROUGH:
            assert name not in FORBIDDEN_PASSTHROUGH, (
                f"{name} must never reach its real binary")
            real = shutil.which(name)
            assert real, f"the harness needs {name}"
            stub = self.stubs / name
            stub.write_text(f'#!/bin/bash\nexec "{real}" "$@"\n', encoding="utf-8")
            stub.chmod(0o755)

    # -- fixtures the stubs answer from -------------------------------

    def fixture(self, name: str, content: str) -> None:
        (self.fixtures / name).write_text(content, encoding="utf-8")

    def policy(self, patterns) -> None:
        self.fixture("policy.txt", "".join(f"{p}\n" for p in patterns))

    def charon_running(self, running: bool = True) -> None:
        marker = self.fixtures / "charon-running"
        if running:
            marker.write_text("", encoding="utf-8")
        elif marker.exists():
            marker.unlink()

    # -- running ------------------------------------------------------

    def environment(self) -> dict:
        return {
            "PATH": self._child_path(),
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "XDG_CONFIG_HOME": str(self.config),
            "TMPDIR": str(self.tmpdir),
        }

    def _child_path(self) -> str:
        """The stub directory and nothing else - asserted, not trusted."""
        path = str(self.stubs)
        assert path.split(os.pathsep) == [str(self.stubs)]
        assert not os.environ.get("PATH", "").startswith(path)
        return path

    def run(self, argv, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run argv with no environment, no terminal and umask 000.

        The permissive umask is the point: a file that is only private
        because something narrowed it after the fact is created 0666
        here, and every stub that runs afterwards writes that mode down.
        """
        environment = self.environment()
        result = subprocess.run(
            [ENV, "-i", *[f"{k}={v}" for k, v in environment.items()],
             BASH, "-c", 'umask 000; exec "$@"', "zepos-test", *argv],
            env={}, input="", capture_output=True, text=True, timeout=timeout,
        )
        conftest.assert_no_missing_command(result)
        return result

    # -- reading the result -------------------------------------------

    def transcript(self) -> list[str]:
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def transcript_text(self) -> str:
        return "\n".join(self.transcript())

    def observations(self) -> list[tuple[str, str, str]]:
        """(stub, path, mode) for every sample any stub took."""
        if not self.modes.exists():
            return []
        rows = []
        for line in self.modes.read_text(encoding="utf-8").splitlines():
            command, path, mode = line.rsplit(" ", 2)
            rows.append((command, path, mode))
        return rows

    def modes_of(self, path) -> set[str]:
        wanted = str(path)
        return {mode for _, seen, mode in self.observations() if seen == wanted}

    def files_with_secrets(self, ignore=()) -> dict[Path, list[str]]:
        """Every file under the test root that carries one of the secrets.

        The harness's own bookkeeping is left out - the transcript
        deliberately writes down anything a script pipes into `sudo`, and
        finding it there is a separate assertion with a separate meaning.
        """
        own = {self.calls, self.modes, *ignore}
        found = {}
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if path in own or self.fixtures in path.parents:
                continue
            # The stubs are the test's own input - a credential-answering
            # `yad` stub carries the credentials by construction.
            if self.stubs in path.parents:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            carried = [secret for secret in SECRETS if secret in text]
            if carried:
                found[path] = carried
        return found


# --------------------------------------------------------------------
# generation
# --------------------------------------------------------------------

@pytest.fixture
def generate(tmp_path, monkeypatch):
    """Generate a VPN template into tmp_path with settings of our own.

    The VPN values are overridden rather than read from the machine
    running the tests: a developer who has no VPN configured would
    otherwise generate a script that refuses to run at its own
    configuration check, and one who has would generate their employer's.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor
    from vpn import child_names, routed_networks_line, swanctl_children

    networks = ["203.0.113.0/24"]
    styles = dict(template_processor.STYLE_VARIABLES)
    styles["STYLE_VPN_SERVER"] = VPN_SERVER_PROBE
    styles["STYLE_VPN_CONNECTION_NAME"] = CONNECTION
    styles["STYLE_VPN_CHILDREN"] = swanctl_children(CONNECTION, networks)
    styles["STYLE_VPN_CHILD_NAMES"] = " ".join(child_names(CONNECTION, networks))
    styles["STYLE_VPN_ROUTED_NETWORKS"] = routed_networks_line(networks)
    styles["STYLE_VPN_BYPASS_NETWORKS"] = ""
    styles["STYLE_VPN_DNS_SERVERS"] = "198.51.100.53"
    styles["STYLE_VPN_SEARCH_DOMAIN"] = "example.org"
    styles["STYLE_VPN_TEST_HOST"] = "198.51.100.8"
    processor = template_processor.ConfigProcessor(styles=styles)

    def build(template: str, output: str, subdir: str = "templates",
              overrides: dict | None = None) -> Path:
        """`overrides` exists for the unconfigured case.

        A machine with no routed network is the state every fresh
        installation is in, and it is the one branch the configured
        styles above can never reach.
        """
        chosen = processor
        if overrides:
            merged = dict(styles)
            merged.update(overrides)
            chosen = template_processor.ConfigProcessor(styles=merged)
        path = tmp_path / output
        chosen.apply_template(SRC / subdir / f"{template}.template", path)
        path.chmod(0o755)
        return path

    return build


POLICY_TEMPLATE = "zepos-privileges-config"
POLICY_FILE = SRC / "system" / f"{POLICY_TEMPLATE}.template"


def _policy_patterns(text: str) -> list[str]:
    """The commands the drop-in actually grants.

    Aliases that are defined but never named on the grant line are not
    granted, and are deliberately not returned: a rule nobody references
    is a rule that does not exist, and the stub has to be as strict as
    sudo is.
    """
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    aliases, granted = {}, []
    for line in joined.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        alias = re.match(r"Cmnd_Alias\s+([A-Z_0-9]+)\s*=\s*(.+)$", line)
        if alias:
            aliases[alias.group(1)] = [
                entry.strip() for entry in alias.group(2).split(",")
                if entry.strip()]
            continue
        grant = re.match(r"\S+\s+ALL\s*=\s*\(root\)\s*NOPASSWD:\s*(.+)$", line)
        if grant:
            granted.extend(entry.strip() for entry in grant.group(1).split(","))
    patterns = []
    for entry in granted:
        if entry.startswith("/"):
            patterns.append(entry)
        else:
            patterns.extend(aliases.get(entry, []))
    return patterns


@pytest.fixture
def policy_patterns(generate):
    """The generated drop-in's command list, as the stub will match it."""
    generated = generate(POLICY_TEMPLATE, "zepos", subdir="system")
    return _policy_patterns(generated.read_text(encoding="utf-8"))


# --------------------------------------------------------------------
# the connect script
# --------------------------------------------------------------------

def _connect_argv(script: Path) -> list[str]:
    """The seven arguments the AGS widget passes, in its order."""
    return [BASH, str(script), USERNAME, PASSWORD, SUDO_PASS, TOKEN, PSK,
            CONNECTION, str(script.parent / "status.log")]


@pytest.fixture
def connected(sandbox):
    """A machine where the tunnel comes up: charon runs, a VIP is there."""
    sandbox.charon_running(True)
    sandbox.fixture("route.txt", "default via 198.51.100.1 dev eth0\n")
    sandbox.fixture("addr.txt",
                    "    inet 10.1.2.3/32 scope global eth0\n")
    sandbox.fixture("sas.txt",
                    "work: #1, ESTABLISHED, IKEv2\n"
                    "  work-1: #1, reqid 1, INSTALLED, TUNNEL\n")
    sandbox.fixture("initiate.txt", "initiate completed successfully\n")
    sandbox.fixture("reachable.txt",
                    "10.1.2.3 198.51.100.1 198.51.100.8 1.1.1.1\n")
    sandbox.fixture("xfrm.txt",
                    "src 0.0.0.0/0 dst 203.0.113.0/24\n"
                    "\ttmpl src 10.1.2.3 dst 198.51.100.9 reqid 1\n")
    return sandbox


@pytest.mark.allow_subprocess
def test_the_connect_script_caches_no_login_password(connected, generate,
                                                     policy_patterns):
    """The defect, measured: nothing on disk may carry the password.

    It used to be written to $XDG_RUNTIME_DIR/vpn-sudo-cache so that the
    watcher and the disconnect path could run `sudo -S` without a human,
    which is a login password stored for the convenience of a background
    process - the shape the review objected to, quite apart from the
    moment of world-readability that `echo >` plus a later `chmod`
    leaves behind.
    """
    connected.policy(policy_patterns)
    script = generate("vpn-connect-script", "vpn-connect.sh")

    connected.run(_connect_argv(script))

    assert not (connected.runtime / "vpn-sudo-cache").exists(), (
        "the login password is cached on disk again")
    carriers = connected.files_with_secrets()
    assert carriers == {}, (
        "secrets reached the filesystem: "
        + "; ".join(f"{path} ({', '.join(what)})"
                    for path, what in carriers.items()))


@pytest.mark.allow_subprocess
def test_the_swanctl_configuration_never_leaves_the_runtime_directory(
        connected, generate, policy_patterns):
    """The pre-shared key went to /tmp/work.conf.$$ at mode 0644.

    `$$` is a process id, not a secret, and /tmp is world-readable, so
    the key was readable by every account on the machine for as long as
    the connection took to establish. The modes are read from inside the
    stubs, while the file is in use - a check after the run would have
    passed on the old code too, because the script deleted the file at
    the end.
    """
    connected.policy(policy_patterns)
    script = generate("vpn-connect-script", "vpn-connect.sh")

    connected.run(_connect_argv(script))

    # The test's own directory happens to live under /tmp, so it is taken
    # out of the picture before looking for a shared temporary directory.
    outside = []
    for line in connected.transcript():
        cleaned = line.replace(str(connected.root), "<test>")
        if "/tmp/" in cleaned or "<test>/tmp/" in line:
            outside.append(line)
    assert outside == [], (
        "a shared temporary directory was used: " + "; ".join(outside))
    assert not list(connected.tmpdir.iterdir()), (
        "something was written to $TMPDIR: "
        + "; ".join(str(p) for p in connected.tmpdir.iterdir()))

    # The measurement itself. A loop over an empty list passes without
    # having measured anything, so the file has to have been SEEN first:
    # it is deleted as soon as the configuration is installed, and after
    # the run there is nothing left to check at all.
    seen = [(command, mode) for command, path, mode in connected.observations()
            if path.endswith("/zepos-vpn/work.conf")]
    assert seen, (
        "the configuration file was never observed while it existed - "
        "this assertion would pass over any implementation")
    for command, mode in seen:
        assert mode == "0600", (
            f"the configuration carrying the PSK was {mode} when {command} ran")

    for command, path, mode in connected.observations():
        if str(connected.runtime) not in path:
            continue
        expected = "0700" if Path(path).is_dir() else "0600"
        assert mode == expected, (
            f"{path} was {mode} when {command} ran, not {expected}")

    # ...and it is that mode from creation rather than from a `chmod`
    # afterwards. The child runs under `umask 000`, so anything created
    # without a narrowed umask arrives world-readable and would have to
    # be narrowed by a chmod to reach the modes asserted above - which is
    # exactly the window the review measured.
    narrowing = [line for line in connected.transcript()
                 if line.startswith("chmod ")
                 and (str(connected.runtime) in line or "vpn-logs" in line)]
    assert narrowing == [], (
        "a private file was created first and narrowed afterwards: "
        + "; ".join(narrowing))


@pytest.mark.allow_subprocess
def test_the_connect_script_logs_no_token_and_no_password_bytes(
        connected, generate, policy_patterns):
    """It wrote the password and the token out as hex, into a log file.

    `od -An -tx1` of both, plus the token in clear in two more lines and
    on standard output - which the AGS widget redirects into /tmp in
    silent mode. A one-time token in a log is either expired and useless
    or valid and dangerous.
    """
    connected.policy(policy_patterns)
    script = generate("vpn-connect-script", "vpn-connect.sh")

    result = connected.run(_connect_argv(script))

    for secret in SECRETS:
        assert secret not in result.stdout, f"{secret} was printed"
        assert secret not in result.stderr, f"{secret} was printed"
    # The hex dump defeats a plain string search, so the command that
    # made it is checked for as well.
    assert "od " not in connected.transcript_text(), (
        "the script still dumps credential bytes")


@pytest.mark.allow_subprocess
def test_the_connect_script_needs_no_password_at_all(connected, generate,
                                                     policy_patterns):
    """With the drop-in installed the password argument is not read.

    The AGS widget still collects a sudo password and still passes it as
    the third argument - that file belongs to another change - but the
    script must not need it: it is handed an empty one here and has to
    reach the same end.
    """
    connected.policy(policy_patterns)
    script = generate("vpn-connect-script", "vpn-connect.sh")

    argv = _connect_argv(script)
    argv[4] = ""  # the sudo password slot
    result = connected.run(argv)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "sudo-password-on-stdin" not in connected.transcript_text(), (
        "a password was piped into sudo")


# --------------------------------------------------------------------
# the control script
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_control_log_is_private_and_carries_no_token(sandbox, generate,
                                                         policy_patterns):
    """It appended the username and the 2FA token to
    /tmp/vpn-control-<date>.log, in clear, at whatever the umask allowed.
    """
    sandbox.policy(policy_patterns)
    sandbox.charon_running(False)
    sandbox.fixture("route.txt", "default via 198.51.100.1 dev eth0\n")
    sandbox.fixture("addr.txt", "    inet 198.51.100.7/24 scope global eth0\n")
    script = generate("vpn-control-config", "vpn-control.sh")

    # The user's own pre-shared key store, which the script reads rather
    # than writes. Without it the connect path stops at its first check
    # and everything below would be asserted over a run that did nothing.
    psk_file = sandbox.home / ".config" / "strongswan" / "psk"
    psk_file.parent.mkdir(parents=True, exist_ok=True)
    psk_file.write_text(PSK + "\n", encoding="utf-8")
    psk_file.chmod(0o600)

    # The generated connect script, which this one launches in a
    # terminal. It has to be there: the branch that regenerates a missing
    # one calls the real generator, which is not what this test is about.
    connect = sandbox.home / ".config" / "ags" / "scripts" / "vpn-connect.sh"
    connect.parent.mkdir(parents=True, exist_ok=True)
    connect.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    connect.chmod(0o755)

    # yad answers with the credentials the dialog asks for. There are
    # three: the sudo password is not one of them any more.
    (sandbox.stubs / "yad").write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n%s\\n%s\\n' '{USERNAME}' '{PASSWORD}' '{TOKEN}'\n",
        encoding="utf-8")
    (sandbox.stubs / "yad").chmod(0o755)

    sandbox.run([BASH, str(script), "connect"])

    carriers = sandbox.files_with_secrets(ignore=(psk_file,))
    assert carriers == {}, (
        "secrets reached the filesystem: "
        + "; ".join(f"{path} ({', '.join(what)})"
                    for path, what in carriers.items()))

    logs = [path for path in sandbox.root.rglob("vpn-control-*.log")]
    assert logs, "the control script wrote no log at all"
    for log in logs:
        assert str(sandbox.runtime) in str(log), (
            f"the control log is outside the runtime directory: {log}")
        assert TOKEN not in log.read_text(encoding="utf-8")
        observed = sandbox.modes_of(log)
        assert observed, f"{log} was never observed while it was written"
        assert observed == {"0600"}, (
            f"{log} was {sorted(observed)} while it was written")

    narrowing = [line for line in sandbox.transcript()
                 if line.startswith("chmod ")]
    assert narrowing == [], (
        "a file was created first and narrowed afterwards: "
        + "; ".join(narrowing))

    # A command line is not private either: /proc/<pid>/cmdline is
    # world-readable, so the sudo password handed to the connect script
    # as its third argument was visible to every account on the machine
    # for as long as the connection took. The dialog no longer asks for
    # it and the slot is passed empty.
    launched = [line for line in sandbox.transcript()
                if line.startswith("kitty ")]
    assert launched, ("the connect script was never launched, so there was "
                      "no command line to check")
    on_command_lines = [line for line in sandbox.transcript()
                        if SUDO_PASS in line]
    assert on_command_lines == [], (
        "the sudo password reached a command line: "
        + "; ".join(on_command_lines))


@pytest.mark.allow_subprocess
def test_disconnect_works_without_a_cached_password(sandbox, generate,
                                                    policy_patterns):
    """Disconnect refused to run without the cache and told the user to
    connect and disconnect again. With the drop-in it needs neither."""
    sandbox.policy(policy_patterns)
    sandbox.charon_running(True)
    sandbox.fixture("route.txt", "default via 198.51.100.1 dev eth0\n")
    sandbox.fixture("addr.txt", "    inet 10.1.2.3/32 scope global eth0\n")
    sandbox.fixture("reachable.txt", "198.51.100.1\n")
    script = generate("vpn-control-config", "vpn-control.sh")

    sandbox.run([BASH, str(script), "disconnect"])

    allowed = [line for line in sandbox.transcript()
               if line.startswith("sudo-allowed ")]
    for expected in ("systemctl stop strongswan",
                     "ip xfrm policy flush",
                     "ip route flush cache"):
        assert any(expected in line for line in allowed), (
            f"the disconnect never ran {expected}: "
            + "; ".join(sandbox.transcript()))
    # Every rule the disconnect needs is in the drop-in, so nothing may
    # fall back to a dialog the user has to click away command by command.
    assert not [line for line in sandbox.transcript()
                if line.startswith("pkexec ")], (
        "pkexec was used although the policy covers every command")
    assert not (sandbox.runtime / "vpn-sudo-cache").exists()
    assert sandbox.files_with_secrets() == {}


# --------------------------------------------------------------------
# what the generated values are FOR
# --------------------------------------------------------------------
#
# tests/src/test_vpn_config.py asserts that these templates carry the
# right placeholders. That is a statement about a file, and three
# mutations showed how far it is from a statement about the artifact:
#
#   * deleting the body of `if [ -z "$CHILDREN_CONF" ]` while leaving the
#     `if` line itself in place,
#   * adding `VPN_CONNECTION="work-ipsec"` AFTER the placeholder line,
#   * adding a second `CHILD_SA_NAMES=...` after its own,
#
# all three left the whole suite green, because a substring is still
# present in a file that no longer behaves. The tests below generate the
# scripts, run them, and read what they actually did out of the stub
# transcript.


@pytest.mark.allow_subprocess
def test_an_unconfigured_connect_script_dials_nothing_at_all(sandbox, generate,
                                                             policy_patterns):
    """A fresh installation has no routed network.

    The check has to REFUSE, not merely exist. A tunnel with no child
    security association establishes, reports "connected" and carries no
    traffic - the hardest VPN failure to recognise, because everything
    the user can see says it worked.

    Generation still has to succeed for such a machine: it needs its bar
    and its terminal whether or not it has a VPN. So the script IS
    written, with empty values, and has to stop by itself - which is
    exactly why only running it can show that it does.
    """
    sandbox.policy(policy_patterns)
    sandbox.charon_running(True)
    script = generate("vpn-connect-script", "vpn-connect.sh",
                      overrides={"STYLE_VPN_CHILDREN": "",
                                 "STYLE_VPN_ROUTED_NETWORKS": ""})

    result = sandbox.run(_connect_argv(script))

    assert result.returncode != 0, result.stdout + result.stderr
    dialled = [line for line in sandbox.transcript() if "swanctl" in line]
    assert dialled == [], (
        "an unconfigured machine dialled anyway: " + "; ".join(dialled))
    output = result.stdout + result.stderr
    assert "routed_networks" in output, (
        f"the refusal does not say what to configure:\n{output}")


@pytest.mark.allow_subprocess
def test_the_connect_script_initiates_the_children_it_was_generated_with(
        connected, generate, policy_patterns):
    """The names in the configuration and the names that get initiated
    are one derivation.

    Deriving them a second time at run time - which is what the origin
    did, live from the settings file - produced `child 'x' not found`
    whenever that file was edited between generating and connecting: a
    child the user never configured, named by a script they did not run.
    A second derivation written into the script by hand does the same
    thing without even needing the edit.
    """
    connected.policy(policy_patterns)
    script = generate("vpn-connect-script", "vpn-connect.sh")

    connected.run(_connect_argv(script))

    initiated = [line.split("--child", 1)[1].strip().split()[0]
                 for line in connected.transcript()
                 if "swanctl" in line and "--child" in line]
    assert initiated, (
        "no child was initiated at all: " + "; ".join(connected.transcript()))

    # The expected names are DERIVED, not spelled out: this test must not
    # become a second place where the naming rule is written down.
    from vpn import child_names

    assert set(initiated) == set(child_names(CONNECTION, ["203.0.113.0/24"])), (
        f"initiated {sorted(set(initiated))}")


@pytest.mark.allow_subprocess
def test_the_disconnect_terminates_the_connection_that_was_configured(
        sandbox, generate, policy_patterns):
    """The disagreement showed up on DISCONNECT and nowhere else.

    The AGS widget passes vpn.connection_name to the connect script; the
    control script used to write the origin's own name in by hand. The
    two agreed for exactly one person, and for everybody else `swanctl
    --terminate --ike work-ipsec` terminated nothing, reported a
    successful disconnect, and left the tunnel up.

    The terminate is the FALLBACK - it runs when stopping the service
    failed - so the service stop is refused here to reach it. That is
    also the state it exists for.
    """
    sandbox.policy([p for p in policy_patterns if "systemctl" not in p])
    sandbox.charon_running(True)
    sandbox.fixture("route.txt", "default via 198.51.100.1 dev eth0\n")
    sandbox.fixture("addr.txt", "    inet 10.1.2.3/32 scope global eth0\n")
    sandbox.fixture("reachable.txt", "198.51.100.1\n")
    script = generate("vpn-control-config", "vpn-control.sh")

    sandbox.run([BASH, str(script), "disconnect"])

    terminated = [line for line in sandbox.transcript()
                  if "swanctl" in line and "--terminate" in line]
    assert terminated, (
        "the fallback never ran, so nothing about the name was measured: "
        + "; ".join(sandbox.transcript()))

    # The WHOLE token, not a substring of it. `"--ike work" in line` is
    # satisfied by `--ike work-ipsec`, which is precisely the wrong name
    # this test exists to catch - the assertion would have passed over
    # the defect it is named after.
    for line in terminated:
        words = line.split()
        named = words[words.index("--ike") + 1]
        assert named == CONNECTION, (
            f"the disconnect terminates {named!r}, which nobody "
            f"configured: {line}")


# --------------------------------------------------------------------
# the watcher - the one caller with nobody to ask
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_watcher_repairs_a_half_up_tunnel_with_no_password_anywhere(
        sandbox, generate, policy_patterns):
    """The evidence that the replacement works where the old one could not.

    hyprland starts this script detached and a `systemd --user` unit
    would too: no terminal, no askpass helper, no way to ask anybody for
    anything. Before, it read the cached login password; a run without
    that cache did nothing at all. Here there is no password in the
    environment, none on disk and none on standard input - the `sudo`
    stub records it if anything tries - and the repair still has to
    happen, purely because the generated drop-in grants those commands.
    """
    sandbox.policy(policy_patterns)
    sandbox.charon_running(True)
    sandbox.fixture("addr.txt", "    inet 10.1.2.3/32 scope global eth0\n")
    # IKE up, no CHILD_SA installed: the half-up state the watcher exists for.
    sandbox.fixture("sas.txt", "work: #1, ESTABLISHED, IKEv2\n")
    sandbox.fixture("initiate.txt", "initiate completed successfully\n")
    (sandbox.runtime / "vpn-active").write_text('{"status":"connected"}\n',
                                                encoding="utf-8")
    script = generate("vpn-watcher-config", "vpn-watcher.sh")

    result = sandbox.run([BASH, str(script), "--once"], timeout=30)

    assert result.returncode == 0, result.stdout + result.stderr
    log = (sandbox.home / ".local" / "share" / "vpn-logs" / "vpn-watcher.log")
    assert log.exists(), "the watcher wrote no log"
    text = log.read_text(encoding="utf-8")
    assert "Re-initiated CHILD_SA" in text, text
    assert "sudo-password-on-stdin" not in sandbox.transcript_text(), (
        "the watcher piped a password into sudo")
    assert not (sandbox.runtime / "vpn-sudo-cache").exists()


@pytest.mark.allow_subprocess
def test_the_watcher_names_the_missing_rule_instead_of_failing_forever(
        sandbox, generate):
    """Without the drop-in the watcher cannot repair anything.

    That is not a reason to try once a minute forever: bare `sudo` from a
    user unit fails with "a password is required" every time, which is
    what the watchdog next door has been doing since it was written. It
    has to say what is missing, once, and stop trying.
    """
    sandbox.policy([])  # nothing granted: no drop-in installed
    sandbox.charon_running(True)
    sandbox.fixture("addr.txt", "    inet 10.1.2.3/32 scope global eth0\n")
    sandbox.fixture("sas.txt", "work: #1, ESTABLISHED, IKEv2\n")
    (sandbox.runtime / "vpn-active").write_text('{"status":"connected"}\n',
                                                encoding="utf-8")
    script = generate("vpn-watcher-config", "vpn-watcher.sh")

    result = sandbox.run([BASH, str(script), "--once"], timeout=30)

    assert result.returncode == 0, result.stdout + result.stderr
    log = (sandbox.home / ".local" / "share" / "vpn-logs" / "vpn-watcher.log")
    text = log.read_text(encoding="utf-8")
    assert "sudoers" in text or "Rechte" in text, (
        "the watcher does not say what is missing: " + text)


# --------------------------------------------------------------------
# the policy itself
# --------------------------------------------------------------------

def test_the_drop_in_is_a_template_the_generator_can_fill(generate):
    """It is generated like everything else, not written by hand into
    /etc by an installer nobody can review."""
    generated = generate(POLICY_TEMPLATE, "zepos", subdir="system")
    text = generated.read_text(encoding="utf-8")
    assert "{{" not in text, "a placeholder survived generation"
    assert "NOPASSWD" in text


@pytest.mark.allow_subprocess
def test_the_generated_drop_in_passes_visudo(generate):
    """A syntactically broken file in /etc/sudoers.d/ is not a small
    mistake: sudo refuses to parse the whole set and the machine loses
    every rule it has, including the one that makes the account an
    administrator at all. visudo is what tells us before that happens."""
    visudo = shutil.which("visudo")
    if not visudo:
        pytest.skip("visudo is not installed")
    generated = generate(POLICY_TEMPLATE, "zepos", subdir="system")
    result = subprocess.run([visudo, "-c", "-f", str(generated)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_policy_grants_no_shell_and_no_open_ended_writer():
    """A NOPASSWD rule is only as narrow as its commands.

    `sudo bash -c ...` or `sudo sed -i ... /etc/resolv.conf` are both
    root with extra steps - sed writes any file through its `w` command -
    so neither may appear. The write path has to be a command whose
    destination is spelled out and carries no wildcard.
    """
    patterns = _policy_patterns(POLICY_FILE.read_text(encoding="utf-8"))
    assert patterns, "the drop-in grants nothing at all"
    for pattern in patterns:
        command = pattern.split()[0]
        assert Path(command).name not in (
            "bash", "sh", "zsh", "dash", "env", "sed", "awk", "perl",
            "python", "python3", "vi", "vim", "tee-all"), (
            f"{pattern} is a shell in disguise")
        if Path(command).name in ("tee", "install", "cp", "dd", "mv", "chown",
                                  "chmod", "ln"):
            assert "*" not in pattern, (
                f"{pattern} lets the caller choose the destination")


def test_every_privileged_command_the_scripts_run_is_covered():
    """A script reaching for something the drop-in does not grant fails
    at run time on a user's machine, silently - `sudo -n` writes its
    refusal to a stderr nobody reads. The two lists are compared here
    instead."""
    import fnmatch

    patterns = _policy_patterns(POLICY_FILE.read_text(encoding="utf-8"))
    uncovered = []
    for name in ("vpn-connect-script", "vpn-control-config",
                 "vpn-watcher-config"):
        text = (SRC / "templates" / f"{name}.template").read_text(
            encoding="utf-8")
        for line, command in _privileged_calls(text):
            resolved = command if command.startswith("/") else "/usr/bin/" + command
            if not any(fnmatch.fnmatchcase(resolved, pattern)
                       for pattern in patterns):
                uncovered.append(f"{name}:{line} {command}")
    assert uncovered == [], (
        "privileged commands no rule covers: " + "; ".join(uncovered))


VPN_TEMPLATES = ("vpn-connect-script", "vpn-control-config",
                 "vpn-watcher-config")

# The only `sudo` invocations allowed to stand on their own. Everything
# else has to go through the helper, so that the policy check, the
# fallback and the message a user can act on all live in one place.
#
#   * the helper itself, in its two shapes;
#   * the capability probe;
#   * and the one command that installs the policy - it cannot be
#     covered by the policy it installs, and it runs only when the user
#     asks for it by name.
ALLOWED_SUDO_LINES = (
    re.compile(r"^sudo -n \"\$@\" 2>/dev/null$"),
    re.compile(r"^rule\)\s+sudo -n \"\$@\" ;;$"),
    re.compile(r"^ask\)\s+sudo \"\$@\" ;;$"),
    re.compile(r"^if sudo -n true 2>/dev/null; then$"),
    re.compile(r"^if sudo install -m 0440 -o root -g root "
               r"\"\$POLICY_FILE\" \"\$POLICY_TARGET\"; then$"),
)


def test_no_script_pipes_a_password_into_sudo():
    """`sudo -S` reads a password from standard input, and a password on
    standard input has to come from somewhere - a file, an argument, an
    environment variable. All three are how this went wrong. The flag
    does not appear in these scripts at all any more."""
    offenders = []
    for name in VPN_TEMPLATES:
        for number, line in enumerate(
                (SRC / "templates" / f"{name}.template").read_text(
                    encoding="utf-8").splitlines(), start=1):
            if line.strip().startswith("#"):
                continue
            if re.search(r"\bsudo\b[^|]*\s(-S|--stdin)\b", line):
                offenders.append(f"{name}:{number}")
    assert offenders == [], "sudo -S survives in: " + "; ".join(offenders)


def test_every_sudo_call_goes_through_the_one_helper():
    """A second call site is a second place where the fallback, the
    message and the policy check would have to be repeated - and the one
    that gets forgotten is the one that fails silently on a machine
    without the drop-in."""
    offenders = []
    for name in VPN_TEMPLATES:
        for number, line in enumerate(
                (SRC / "templates" / f"{name}.template").read_text(
                    encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # A message that mentions sudo is not a call to it. Quoted
            # text is removed before looking, so the German hint telling
            # the user what sudo is about to do does not count.
            code = re.sub(r'"[^"]*"', '""', stripped)
            if not re.search(r"(^|\s)sudo\s", code):
                continue
            if any(pattern.match(stripped) for pattern in ALLOWED_SUDO_LINES):
                continue
            offenders.append(f"{name}:{number} {stripped}")
    assert offenders == [], (
        "sudo is called outside the helper: " + "; ".join(offenders))


@pytest.mark.allow_subprocess
def test_the_network_watchdog_can_finally_repair_anything(sandbox, generate,
                                                          policy_patterns):
    """The other half of what the missing rule cost.

    network-watchdog.sh runs as a `systemd --user` unit and calls bare
    `sudo`. With no terminal, no askpass helper and no rule, every one of
    those calls fails - so the service logged "Reparatur fehlgeschlagen"
    every ten seconds and had never repaired anything. It is not this
    change's file, and it does not have to be: the four commands it runs
    are in the drop-in, and that is enough to make them work.

    Measured against the policy, not against a stub that says yes to
    everything: with an empty policy the same run repairs nothing.
    """
    script = generate("network-watchdog-config", "network-watchdog.sh")
    sandbox.fixture("route.txt", "default via 198.51.100.1 dev eth0\n")
    sandbox.fixture("reachable.txt", "198.51.100.1\n")  # gateway up, no internet

    sandbox.policy(policy_patterns)
    sandbox.run([BASH, str(script), "--once"])
    allowed = [line for line in sandbox.transcript()
               if line.startswith("sudo-allowed ")]
    for expected in ("ip neigh flush dev eth0", "ip link set eth0 down",
                     "ip link set eth0 up", "nmcli device reapply eth0"):
        assert any(expected in line for line in allowed), (
            f"the drop-in does not cover `{expected}`: " + "; ".join(allowed))


# `run_sudo ...` / `run_privileged ...` call sites, with the shell's own
# expansions turned into the wildcard sudo would match them against.
PRIVILEGED_CALL = re.compile(
    r"^\s*(?:\S+=\S+\s+)*(?:run_sudo|run_privileged)\s+(.+?)\s*$")


def _privileged_calls(text: str) -> list[tuple[int, str]]:
    calls = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # A call may sit inside a substitution or after a pipe.
        for match in re.finditer(r"(?:run_sudo|run_privileged)\s+([^\n|&;)]+)",
                                 stripped):
            command = _as_sudo_sees_it(match.group(1))
            if not command or command.startswith(("(", "*")):
                continue
            calls.append((number, command))
    return calls


# Everything the shell eats before sudo ever sees it. The second form
# catches a redirection the call-site scan already cut in half: it stops
# at `&`, so `2>&1` arrives here as a dangling `2>`.
REDIRECTION = re.compile(r"\s(?:\d?>>?|\d?<)\s*\S*")


def _as_sudo_sees_it(command: str) -> str:
    """Every shell expansion becomes the wildcard the rule has to allow.

    A rule has to cover what sudo receives, and sudo receives the
    EXPANDED line: `run_sudo ip route add "$NET" dev $IFACE` arrives as
    `ip route add 203.0.113.0/24 dev eth0`. Both variables are turned
    into `*` here, which is exactly what the rule that covers them has to
    contain - and redirections are dropped, because the shell consumes
    them.
    """
    command = REDIRECTION.sub("", " " + command)
    command = re.sub(r"\$\{[^}]+\}", "*", command)
    command = re.sub(r"\$\([^)]*\)", "*", command)
    command = re.sub(r"\$[A-Za-z_][A-Za-z_0-9]*", "*", command)
    command = command.replace('"', "").replace("'", "")
    return re.sub(r"\s+", " ", command).strip()
