# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebuilds plugins/hyprlaunch and plugins/hyprclipx, the way packaging/
zepos-hyprlaunch/PKGBUILD and packaging/zepos-hyprclipx/PKGBUILD now build
them.

WHY THIS EXISTS (19.08.2026)
    Until 19.08.2026 both trees lived, already patched, under
    plugins/hyprlaunch/ and plugins/hyprclipx/ in this repository - a test
    could just read them. The security review before publishing ZepOS
    (.superpowers/sdd/2026-08-18-ags-schale-und-breitenleiter/
    sicherheitsanalyse.md, section 6) named why that had to stop: both
    upstream trees carry no licence at all - GitHub reports
    "license": null for both - and a modified COPY of unlicensed code
    checked into a public repository is still a copy, independent of
    whatever permission ZepOS itself has to build from it. plugins/
    LICENSE has the full account, and packaging/zepos-hyprlaunch/PKGBUILD
    and packaging/zepos-hyprclipx/PKGBUILD carry it in full at the top.

    Five test files used to read those files directly - test_own_plugins.py,
    test_modal_rule.py, test_glass.py, test_plugins.py, test_design.py -
    to check real claims about the real, patched source (a CSS literal
    that is gone, a field that reads a generated file, a namespace a real
    compiled object registers). Losing plugins/hyprlaunch/ and
    plugins/hyprclipx/ from the tree does not make those claims stop
    mattering, so this module rebuilds the exact tree the recipes build
    from: the pinned commit named in packaging/zepos-<name>/PKGBUILD,
    fetched over the network, patched by packaging/zepos-<name>/
    zepos-<name>.patch - ZepOS' own diff, not a copy of upstream's code.

WHY THIS IS ALLOWED TO TOUCH THE NETWORK
    CONTRIBUTING.md promises the suite "needs nothing but Python and
    pytest" elsewhere, and every test that calls plugin_source() depends
    on github.com/azzuriel being reachable. That is not an exception to
    the promise; it is the same one CONTRIBUTING.md already makes for
    QEMU, OVMF, a built package repository and a real Hyprland: skipped,
    not failed, when the resource the test needs is not there. Cached
    per plugin for the whole test session, so a run that exercises all
    five files still fetches each tree exactly once.

WHY NO SUBPROCESS
    Applying zepos-<name>.patch here does not shell out to `patch`.
    tests/conftest.py's isolation guard blocks subprocess.run/Popen for
    any test that does not carry @pytest.mark.allow_subprocess, and
    forcing that marker onto five otherwise plain, read-only tests only
    because THIS helper wants a subprocess is exactly the "looser
    pattern" CONTRIBUTING.md's isolation-guard section says not to
    invent. _apply_unified_patch() below is a plain, from-scratch reader
    of the one patch shape `diff -ruN` produces - context hunks, -p1, no
    renamed or binary files, both of which are true of both patches here
    - and needs neither subprocess nor a write outside tmp.
"""
from __future__ import annotations

import re
import tarfile
import tempfile
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"

# plugin name -> the recipe that fetches and patches it.
RECIPES = {
    "hyprlaunch": "zepos-hyprlaunch",
    "hyprclipx": "zepos-hyprclipx",
}

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

_cache: dict[str, Path] = {}
_error: dict[str, str] = {}


def _apply_unified_patch(patch_text: str, root: Path) -> None:
    """Applies a plain `diff -ruN a/ b/` patch (context hunks, -p1) to
    files under root, in place. No subprocess - see the module docstring
    for why that matters here.

    Deliberately narrow: no renamed files, no binary hunks, no "\\ No
    newline at end of file" handling. Both patches this module applies
    are `diff -ruN` output with none of those, verified when they were
    generated (packaging/zepos-hyprlaunch/PKGBUILD's and packaging/
    zepos-hyprclipx/PKGBUILD's own history has the measurement) - a
    patch that needed one of those would fail an assertion here rather
    than apply silently wrong.
    """
    lines = patch_text.splitlines(keepends=True)
    i, n = 0, len(lines)
    while i < n:
        if not lines[i].startswith("--- "):
            i += 1
            continue
        new_header = lines[i + 1]
        assert new_header.startswith("+++ "), (
            f"malformed patch header: {new_header!r}")
        new_path = new_header[4:].split("\t", 1)[0].strip()
        if "/" in new_path:
            new_path = new_path.split("/", 1)[1]  # strip -p1's a/ or b/
        target = root / new_path
        original = (target.read_text(encoding="utf-8").splitlines(keepends=True)
                    if target.exists() else [])
        i += 2

        out: list[str] = []
        pos = 0
        while i < n and lines[i].startswith("@@ "):
            match = _HUNK.match(lines[i])
            assert match, f"malformed hunk header: {lines[i]!r}"
            old_start = int(match.group(1)) - 1
            out.extend(original[pos:old_start])
            pos = old_start
            i += 1
            while i < n and lines[i][:1] in (" ", "-", "+"):
                tag, content = lines[i][0], lines[i][1:]
                if tag == " ":
                    assert original[pos] == content, (
                        f"context mismatch in {new_path} at line {pos + 1}: "
                        f"expected {original[pos]!r}, patch says {content!r}")
                    out.append(content)
                    pos += 1
                elif tag == "-":
                    assert original[pos] == content, (
                        f"remove mismatch in {new_path} at line {pos + 1}: "
                        f"expected {original[pos]!r}, patch says {content!r}")
                    pos += 1
                elif tag == "+":
                    out.append(content)
                i += 1
        out.extend(original[pos:])

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(out), encoding="utf-8")


def plugin_source(name: str) -> Path:
    """The reconstructed tree packaging/zepos-<name>/PKGBUILD builds
    from - fetched once per test session, cached, and skipped (not
    failed) when the network is not there. See the module docstring for
    why a skip and not a failure is the right answer here."""
    if name in _cache:
        return _cache[name]
    if name in _error:
        pytest.skip(_error[name])

    recipe = RECIPES[name]
    pkgbuild = (PACKAGING / recipe / "PKGBUILD").read_text(encoding="utf-8")
    match = re.search(r"^_commit=([0-9a-f]{40})$", pkgbuild, re.M)
    assert match, f"packaging/{recipe}/PKGBUILD pins no commit"
    commit = match.group(1)
    url = f"https://github.com/azzuriel/{name}/archive/{commit}.tar.gz"

    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            archive = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = (
            f"kein Netz zu {url} ({exc}) - plugins/LICENSE verbietet, die "
            f"unveraenderte Quelle in diesem Repository zu fuehren, also "
            f"muss dieser Test sie zur Laufzeit holen wie packaging/"
            f"{recipe}/PKGBUILD es tut")
        _error[name] = reason
        pytest.skip(reason)

    workdir = Path(tempfile.mkdtemp(prefix=f"zepos-plugin-source-{name}-"))
    with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as tar:
        tar.extractall(workdir, filter="data")
    entries = list(workdir.iterdir())
    assert len(entries) == 1, (
        f"unerwarteter Tarball-Aufbau fuer {name}: {entries}")
    root = entries[0]

    if name == "hyprclipx":
        # prepare()'s renames, before the patch: it only touches file
        # content from here on. packaging/zepos-hyprclipx/PKGBUILD has
        # the same four lines.
        helpers = root / "helpers"
        for original_name in ("clipman-daemon.py", "get-caret-position.py"):
            assert (helpers / original_name).is_file(), (
                f"{original_name} fehlt im heruntergeladenen Baum von "
                f"azzuriel/hyprclipx@{commit}")
        (helpers / "clipman-daemon.py").rename(helpers / "collector.py")
        (helpers / "get-caret-position.py").rename(
            helpers / "caret-position.py")
        (helpers / "clipman-client.py").unlink(missing_ok=True)
        (helpers / "clipman.service").unlink(missing_ok=True)

    patch_path = PACKAGING / recipe / f"zepos-{name}.patch"
    _apply_unified_patch(patch_path.read_text(encoding="utf-8"), root)

    _cache[name] = root
    return root
