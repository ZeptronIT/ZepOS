# SPDX-License-Identifier: GPL-3.0-or-later
"""What the AGS widgets hand to execAsync, run the way Astal runs it.

Astal's `execAsync` has two shapes and they are not interchangeable:

    execAsync(["cmd", "arg"])   spawns argv directly
    execAsync("cmd arg")        splits with GLib.shell_parse_argv, then
                                spawns argv directly

Neither starts a shell. `shell_parse_argv` understands quoting and
nothing else: measured here on this machine,

    GLib.shell_parse_argv("a > b")  ->  ["a", ">", "b"]

so a redirect, an `&&` or a pipe written into that string is not a
redirect, an `&&` or a pipe - it is three more arguments handed to the
program. Two things followed from that in this tree:

  * ags-vpn-settings' savePsk passed
    `python3 -c "..." > $PSK_FILE && chmod 600 $PSK_FILE`.
    python3 exits 0 having ignored the extra arguments, savePsk returned
    true, the dialog said "PSK wurde sicher gespeichert" - and the file
    was never created. ags-vpn then stops at "PSK nicht gefunden" every
    time, and sends the user back to the dialog that just claimed to have
    saved it. On a fresh installation there is no way out of that loop.
  * ags-vpn's connect path DID write a shell: it built a
    `bash -c '...'` string by pasting the username, the password and the
    2FA token into it. Inside `bash -c` those are program text. A
    password of `p"; id > /tmp/pwned; #` runs `id` - in the one flow that
    holds the user's credentials.

A .template written in TypeScript cannot be executed by this suite, so
what is executed is the argv it produces: the strings are taken out of
the generated artifact, split exactly as Astal would split them, and
run. That is the same measurement, at the one point where it matters.
"""
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
TEMPLATES = SRC / "templates"

BASH = "/bin/bash"
ENV = "/usr/bin/env"

# Shell syntax that means nothing to GLib.shell_parse_argv. A string
# handed to execAsync containing any of these is a string whose author
# believed a shell would read it.
SHELL_OPERATORS = (">", ">>", "<", "&&", "||", "|", ";", "&")


def _template(name: str) -> str:
    return (TEMPLATES / f"{name}.template").read_text(encoding="utf-8")


def _static(literal: str) -> str:
    """A template literal reduced to its static shape.

    Every ${...} becomes one placeholder word, because what is being
    asked is how the SHAPE is split, not what a particular home directory
    happens to be called.
    """
    return re.sub(r"\$\{[^}]*\}", "SUBSTITUTED", literal)


def _string_execasync_calls(text: str) -> list[tuple[int, str]]:
    """Every execAsync(<one string>) in a template, with its line number.

    Only the single-string form: the array form is spawned as argv and
    has nothing to split.

    A command assembled into a local `const` first counts too. That is
    exactly the shape savePsk used - `const cmd = ...` on one line and
    `await execAsync(cmd)` on the next - and a scan that only read
    inline literals walked straight past the defect this file exists for.
    """
    lines = text.splitlines()
    literals = {}
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        assigned = re.match(
            r"(?:const|let|var)\s+(\w+)\s*=\s*([`\"'])(.*)\2\s*$", stripped)
        if assigned:
            literals[assigned.group(1)] = (number, _static(assigned.group(3)))

    found = []
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        inline = re.search(r"execAsync\(\s*([`\"'])(.*?)\1\s*\)", stripped)
        if inline:
            found.append((number, _static(inline.group(2))))
            continue
        named = re.search(r"execAsync\(\s*(\w+)\s*\)", stripped)
        if named and named.group(1) in literals:
            declared, command = literals[named.group(1)]
            found.append((declared, command))
    return found


# --------------------------------------------------------------------
# no widget may write shell syntax into a string execAsync
# --------------------------------------------------------------------

@pytest.mark.parametrize("template", ["ags-vpn", "ags-vpn-settings"])
def test_no_string_handed_to_exec_async_contains_shell_syntax(template):
    """The rule, applied to the two VPN widgets.

    A redirect or an `&&` in one of these strings is not a mistake in the
    command - it is a command that was never run at all, and the caller
    is told it succeeded.
    """
    offenders = []
    for number, command in _string_execasync_calls(_template(template)):
        argv = shlex.split(command)
        for operator in SHELL_OPERATORS:
            if operator in argv:
                offenders.append(f"{template}:{number} {command!r}")
                break
    assert offenders == [], (
        "execAsync starts no shell, so this is passed as arguments: "
        + "; ".join(offenders))


@pytest.mark.allow_subprocess
def test_the_psk_write_reaches_the_disk_when_run_as_astal_runs_it(tmp_path):
    """savePsk, executed rather than read.

    The old command is reproduced here beside the new one so the
    assertion is a comparison rather than a claim: the old shape is split
    and run first and MUST leave no file, which is what makes the second
    half mean something.
    """
    psk = "GEHEIM-PSK-4711"
    hex_psk = "".join(f"{ord(c):02x}" for c in psk)
    target = tmp_path / "psk"

    # The shape ags-vpn-settings shipped, split the way Astal splits it.
    old = (f'python3 -c "import sys; '
           f"sys.stdout.buffer.write(bytes.fromhex('{hex_psk}'))\" "
           f"> {target} && chmod 600 {target}")
    argv = shlex.split(old)
    assert ">" in argv and "&&" in argv, (
        "shlex must reproduce GLib.shell_parse_argv here: neither treats "
        f"a redirect as one - {argv}")
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, (
        "the caller saw a success, which is the whole defect: "
        + result.stdout + result.stderr)
    assert not target.exists(), (
        "the old shape wrote a file after all - this test no longer "
        "reproduces anything")


def test_the_psk_is_written_by_the_widget_itself_and_created_private():
    """The replacement is not another command line.

    A PSK on a command line is readable through /proc/<pid>/cmdline for
    as long as the process lives, whether it is written in hex or not, so
    the fix is not "quote it better" - it is not to spawn anything.
    Gio.FileCreateFlags.PRIVATE is what makes the file owner-only from
    its first byte rather than after a chmod, and REPLACE_DESTINATION is
    what stops an existing world-readable file from keeping its mode.
    """
    text = _template("ags-vpn-settings")
    body = re.search(r"function savePsk\(.*?\n\}", text, re.S)
    assert body, "savePsk is no longer a function this test can read"
    save = body.group(0)

    assert "execAsync" not in save, (
        "the pre-shared key is handed to another process again: " + save)
    assert "Gio.FileCreateFlags.PRIVATE" in save, (
        "nothing makes the PSK file private at creation: " + save)
    assert "REPLACE_DESTINATION" in save, (
        "an existing PSK file would keep whatever mode it had: " + save)
    assert "chmod" not in save, (
        "a chmod after the fact leaves the file readable in between")
    assert 'import Gio from "gi://Gio"' in text, "Gio is used but not imported"


def test_the_dialog_only_reports_a_save_it_can_see():
    """"PSK wurde sicher gespeichert" over a file that is not there is
    what made this unbreakable: the user does the one thing the error
    message asks for, is told it worked, and meets the same error."""
    text = _template("ags-vpn-settings")
    saved = re.search(r"const success = (.*)", text)
    assert saved, "the save is no longer decided by a `success` value"
    assert "pskFileExists()" in saved.group(1), (
        "the success message does not depend on the file existing: "
        + saved.group(1))
    # Der msgid, nicht der deutsche Satz.
    #
    # Bis zum 17.08.2026 stand hier "PSK konnte nicht gespeichert
    # werden" - der Text, den die Vorlage damals selbst trug. Seither
    # traegt sie ihn nicht mehr: jede Beschriftung der Oberflaeche laeuft
    # durch gettext, der msgid ist Englisch, und das Deutsche steht in
    # po/desktop/de.po. Geprueft wird also dasselbe an der Stelle, an der
    # es jetzt steht - dass ein gescheitertes Speichern ueberhaupt etwas
    # sagt. Dass es das auf Deutsch sagt, sichert
    # tests/src/test_ags_i18n.py zu: zu jedem msgid muss es einen
    # gefuellten Katalogeintrag geben.
    assert '_("The PSK could not be saved")' in text, (
        "a failed save says nothing at all")


# --------------------------------------------------------------------
# the connect path: credentials as arguments, never as program text
# --------------------------------------------------------------------

def _connect_argv_literal(text: str) -> str:
    """The connectArgv array as it stands in the template."""
    match = re.search(r"const connectArgv = \[(.*?)\n    \]", text, re.S)
    assert match, "connectArgv is no longer an array this test can read"
    return match.group(1)


def test_every_credential_is_its_own_argument():
    """The injection, structurally.

    `bash -c '"$script" "${username}" "${password}" ...'` puts every one
    of those values inside a program bash then parses. As elements of an
    argv array they are data: nothing between JavaScript and execve()
    looks at their contents.
    """
    text = _template("ags-vpn")
    argv = _connect_argv_literal(text)
    for value in ("username", "password", "token", "psk"):
        assert re.search(rf"\b{value}\b", argv), (
            f"{value} is no longer passed as an argument: {argv}")
    # No template literal may carry a credential into a single string.
    for number, command in _string_execasync_calls(text):
        for value in ("username", "password", "token", "psk"):
            assert value not in command, (
                f"ags-vpn:{number} builds a command text around {value}")


@pytest.mark.allow_subprocess
def test_a_password_that_looks_like_a_command_stays_a_password(tmp_path):
    """The redirection wrapper, executed with a hostile password.

    The silent branch is the one place a shell is still needed - for
    `>> logfile` - so its program text is a constant and everything
    variable arrives behind it as an argument. This runs that exact
    constant, with the password the review measured, and looks for what
    it would have created.
    """
    text = _template("ags-vpn")
    wrapper = re.search(r'"bash", "-c",\n\s*(\'[^\']*\')', text)
    assert wrapper, "the silent branch no longer wraps a constant program"
    program = wrapper.group(1).strip("'")

    marker = tmp_path / "pwned"
    hostile = f'p"; touch {marker}; #'

    echo = tmp_path / "connect.sh"
    echo.write_text("#!/bin/bash\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    echo.chmod(0o755)
    detail = tmp_path / "vpn.log.detail"

    result = subprocess.run(
        [BASH, "-c", program, "zepos-vpn-connect", str(detail),
         str(echo), "nutzer", hostile, "", "123456", "psk", "work",
         str(tmp_path / "vpn.log")],
        capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists(), "the password was executed"
    # The password reached the script whole, as one argument.
    arguments = detail.read_text(encoding="utf-8").splitlines()
    assert arguments[1] == hostile, arguments
    # ...and the third slot - once the sudo password - is empty.
    assert arguments[2] == "", arguments
    # The redirect created the log, and umask 077 made it private from
    # the start: this file carries the username.
    assert detail.stat().st_mode & 0o077 == 0, oct(detail.stat().st_mode)


def test_the_widget_asks_for_no_sudo_password_any_more():
    """A command line is not private: /proc/<pid>/cmdline is readable by
    every account on the machine, so the login password the widget put in
    the connect script's third argument was visible for as long as the
    connection took. Nothing reads it - the privileged commands come from
    /etc/sudoers.d/zepos - so the field is gone, not merely unused."""
    text = _template("ags-vpn")
    assert "sudoPasswordEntry" not in text, "the sudo password field survives"
    assert "Sudo Passwort" not in text, "the dialog still asks for it"
    assert "Sudo-Passwort erforderlich" not in text, (
        "connecting still refuses without one")

    # The slot itself stays, empty, because the six arguments behind it
    # keep their positions. Both callers pass it the same way.
    argv = _connect_argv_literal(text)
    assert re.search(r"password,\s*\"\",", argv), (
        "the third argument is no longer an explicit empty slot: " + argv)
    control = _template("vpn-control-config")
    assert '"$USERNAME" "$PASSWORD" "" "$TOKEN"' in control, (
        "the two callers disagree about the argument order")


def test_the_connect_log_stays_on_the_users_own_tmpfs():
    """It carries the username, and it was written to /tmp under a name
    made from the date - predictable, in a directory every account on the
    machine can read. vpn-control.sh moved its log to
    $XDG_RUNTIME_DIR/zepos-vpn; this redirect pointed straight back at
    /tmp."""
    text = _template("ags-vpn")
    assert "/tmp/vpn-control-" not in text, "the log is in /tmp again"
    assert "get_user_runtime_dir()}/zepos-vpn" in text, (
        "the log does not go where vpn-control.sh puts its own")
    # Same directory, same name, on both sides.
    control = _template("vpn-control-config")
    assert 'RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/zepos-vpn"' \
        in control, "vpn-control.sh moved and nothing followed it"


# --------------------------------------------------------------------
# a note the whole file rests on
# --------------------------------------------------------------------

def test_shlex_splits_the_way_glib_does_for_what_is_asserted_here():
    """shlex stands in for GLib.shell_parse_argv above, so the one
    property that matters is written down: both split on quoting and
    NEITHER gives an operator any meaning. Measured against the real
    GLib on this machine:

        GLib.shell_parse_argv("a > b") -> (True, ['a', '>', 'b'])
    """
    assert shlex.split("a > b") == ["a", ">", "b"]
    assert shlex.split("x && y") == ["x", "&&", "y"]
    assert shlex.split('cat "two words"') == ["cat", "two words"]
