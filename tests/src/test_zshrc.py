# SPDX-License-Identifier: GPL-3.0-or-later
"""The login shell, after 570 lines were cut out of the middle of it.

generate_config.sh:514 writes this template to $HOME/.zshrc, so it is not
a dormant file: it is the first thing that runs when a user opens a
terminal. That makes two things worth proving mechanically, because
nothing else in the suite covers either.

  * It still PARSES. validate_output.py deliberately does not run
    `bash -n` over ~/.zshrc - bash would reject zsh's own syntax and
    report a broken file that is fine - so the generated login shell is
    the one artifact the staging validator cannot check. A cut that left
    an unbalanced `if` or a dangling `}` behind would be found by the
    user, at their next terminal, with no shell to fix it from.
  * The drop-in loader survives. User commands live in ~/.zshrc.d/*.zsh
    and the loader in this template is the only thing that reads them.
    Removing it does not break anything visibly: the file still parses,
    the shell still starts, and every command the user wrote is simply
    gone after the next regeneration.

`zsh -n` reads and parses without executing a single command, which is
why it may be pointed at a login shell at all. It is still run through
`env -i` with an empty stub PATH and a sandbox HOME, and with `-f` so no
startup file of the machine running the tests is consulted.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"

ENV = "/usr/bin/env"
TEMPLATE = "zshrc-config"


@pytest.fixture
def generated(tmp_path, monkeypatch):
    """The template, processed exactly as the generator processes it."""
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    written = tmp_path / ".zshrc"
    template_processor.ConfigProcessor().apply_template(
        SRC / "templates" / f"{TEMPLATE}.template", written)
    return written


@pytest.mark.allow_subprocess
def test_the_generated_zshrc_parses(generated, tmp_path):
    """`zsh -n`: parse the file, execute nothing in it."""
    zsh = shutil.which("zsh")
    assert zsh, (
        "zsh is not installed on this machine, so the one artifact the "
        "staging validator cannot check would go unchecked here too")

    empty = tmp_path / "nothing"
    empty.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    result = subprocess.run(
        [ENV, "-i", f"PATH={empty}", f"HOME={home}", zsh, "-f", "-n",
         str(generated)],
        env={},
        input="",
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == "", result.stderr


def test_the_drop_in_loader_is_still_there(generated):
    """~/.zshrc.d/*.zsh, sourced from the generated file.

    Asserted on the GENERATED output rather than on the template: a
    loader that survives the entkernung and then falls out of the
    processor's hands helps nobody.

    The (N) glob qualifier matters as much as the loop: without it an
    empty ~/.zshrc.d makes zsh report "no matches found" on every single
    login.
    """
    text = generated.read_text(encoding="utf-8")
    assert ".zshrc.d" in text, (
        "the drop-in loader is gone - every command the user put in "
        "~/.zshrc.d/*.zsh stops being loaded, silently, at the next "
        "regeneration")
    assert re.search(r"for\s+\w+\s+in\s+~/\.zshrc\.d/\*\.zsh\(N\)", text), (
        "the loader has to iterate ~/.zshrc.d/*.zsh with the (N) "
        "qualifier")
    assert re.search(r"source\s+\"?\$", text), "nothing is sourced in the loop"


def test_the_shell_starts_from_a_template_that_needs_no_secrets(generated):
    """What the file may not carry into a published distribution.

    Three of these were in it: the path of one user's GPG-encrypted sudo
    password inside a pass store, the SSH posture built around one
    person's YubiKey, and a completion file sourced from a home
    directory that exists on one machine. None of them is a placeholder
    somebody forgot to fill in - each one worked, for exactly one person,
    and told everyone else where his credentials live.
    """
    text = generated.read_text(encoding="utf-8").lower()
    for secret in ("password-store", "askpass", "yubikey", "gpg-agent",
                   "/home/"):
        assert secret not in text, f"the login shell still names {secret}"
