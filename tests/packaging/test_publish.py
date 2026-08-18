# SPDX-License-Identifier: GPL-3.0-or-later
"""The publishing path, checked without publishing anything.

WHY THESE TESTS EXIST
    packaging/publish.sh is the one script in this repository whose
    mistakes are irreversible by somebody else's clock. A push to a
    public branch is public the moment it lands; a repository signed with
    the throwaway key from packaging/make-test-key.sh looks verified to
    every machine that fetches it, and the private half of that key is in
    a working directory. Neither can be taken back by fixing the script
    afterwards.

    So the properties that must hold are read out of the script itself,
    here, rather than discovered on the day somebody runs it:

      * it never pushes;
      * it refuses a test key, with no flag that says otherwise;
      * what it stages is what a static host can actually serve - which
        is not a copy of packaging/out/, because repo-add writes a
        symlink and GitHub Pages does not resolve one;
      * the branch it writes cannot grow without bound.

WHAT THEY DELIBERATELY DO NOT DO
    They do not run it. Staging needs a signed build in packaging/out/,
    which needs Docker, twenty minutes and a key - all of which
    packaging/README.md describes and none of which belongs in a suite
    that has to run in two minutes.

    The half that cannot be read out of a file is measured elsewhere and
    by a machine: iso/test-boot.py --scenario update serves the staged
    tree over HTTP and lets an installed ZepOS upgrade itself from it.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "packaging"
ISO = ROOT / "iso"


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _publish() -> str:
    return _read(PACKAGING / "publish.sh")


def _code(text: str) -> str:
    """The text with whole-line comments removed.

    Every script in packaging/ explains what it refuses as carefully as
    what it does, so a scan that reads the explanation as code finds the
    defect in the paragraph describing its absence.
    """
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


# --------------------------------------------------------------------
# It does not push
# --------------------------------------------------------------------

def test_publishing_never_pushes_by_itself():
    """The last thing the script does is PRINT a push command.

    A script that pushes is a script whose --help has to be read before
    it is run, and whose mistake is public. Everything up to the commit
    is reversible on this machine; the push is not, and it is therefore
    the one step a human takes.
    """
    text = _publish()
    heredoc = text.index("<<PUSH")
    for match in re.finditer(r"git push", text):
        assert match.start() > heredoc, (
            "packaging/publish.sh runs `git push` outside the here-document "
            "that merely prints it")
    assert "--force origin" in text, (
        "the printed command is not a forced push, which an orphan branch "
        "always needs - it has no shared history to fast-forward")


def test_publishing_never_touches_the_checked_out_branch():
    """It runs with uncommitted work in the tree, or it is a script
    nobody dares run.

    A worktree, a checkout or a stash would move somebody else's work to
    publish a directory of build artefacts. The commit is made with
    plumbing against a temporary index instead, so the working tree is
    only ever read.
    """
    code = _code(_publish())
    for forbidden in ("git checkout", "git restore", "git stash",
                      "git reset", "git worktree"):
        assert forbidden not in code, (
            f"packaging/publish.sh runs `{forbidden}`, which can destroy "
            f"uncommitted work that has nothing to do with publishing")
    assert "GIT_INDEX_FILE=" in code, "the commit is not made against its own index"
    assert '--work-tree="$dest"' in code, (
        "the commit is made against the checked-out tree rather than the "
        "staged one")

    # Measured, and it stopped the commit dead: `index="$(mktemp)"`
    # CREATES the file, and git refuses an index that exists and is empty
    # with "index file smaller than expected". The temporary index has to
    # be a name in a private directory, not a file.
    assert 'index="$(mktemp)"' not in code, (
        "the temporary index is an existing empty file, which git refuses")
    assert 'index_dir="$(mktemp -d)"' in code


# --------------------------------------------------------------------
# It refuses the key that must not be published
# --------------------------------------------------------------------

def test_a_test_key_cannot_be_committed_and_there_is_no_flag_for_it():
    """A repository signed with `ZepOS TEST KEY - DO NOT TRUST` is worse
    than an unsigned one: unsigned fails loudly on every machine that
    asks for a signature, and signed-with-a-throwaway succeeds.

    packaging/zepos-keyring/PKGBUILD reads the same user id and says so
    in the package description; this is where the same fact stops a
    publish.
    """
    code = _code(_publish())
    assert 'DO NOT TRUST' in code, (
        "publish.sh no longer notices the test key's own user id")
    assert re.search(r'\$is_test_key && die', code), (
        "a test key does not stop the commit")

    # No override, and this is read out of the argument parser rather
    # than out of a list of names somebody might have thought of. The
    # point of the refusal is that it cannot be argued with at three in
    # the morning, and a new option is exactly how it would be.
    options = re.search(r'while \(\( \$# \)\); do\n\s*case "\$1" in(.*?)\n\s*esac',
                        code, re.S)
    assert options, "publish.sh has no argument parser to read"
    accepted = set(re.findall(r'^\s*((?:-{1,2}[\w|-]+)+)\)', options.group(1), re.M))
    assert accepted == {"--into", "--commit", "-h|--help"}, (
        f"packaging/publish.sh accepts {sorted(accepted)}; anything beyond "
        f"--into, --commit and --help is a way around the test-key refusal")


def test_a_staged_test_key_carries_its_own_warning():
    """Staging one IS allowed - it is how the update path is measured
    without publishing anything - so the staged tree has to say what it
    is. The marker is also what the commit step reads, which is why the
    two steps can be separate at all."""
    code = _code(_publish())
    assert 'TEST_KEY_MARKER="TEST-KEY-DO-NOT-PUBLISH"' in code
    assert '"$dest/$TEST_KEY_MARKER"' in code, (
        "the marker is never written into the staged tree")


def test_an_unsigned_build_is_refused_outright():
    """Spec §8.6. Every installed ZepOS carries `SigLevel = Required` for
    [zepos] - installer/core/source.py writes it - so an unsigned
    repository at that URL is not a degraded service, it is a repository
    every installed machine refuses."""
    code = _code(_publish())
    assert re.search(r'\[\[ -s "\$PUBLIC_KEY" \]\] \|\| die', code), (
        "publish.sh does not refuse a build made with --no-sign")
    assert 'zepos.db.tar.gz.sig' in code, (
        "the database signature is never checked, and SigLevel = Required "
        "covers the database before it covers a package")


def test_signatures_are_verified_against_the_published_key_and_not_this_machine():
    """The only key an installed system has for this repository is the
    one zepos-keyring shipped, which is the same file that is published
    next to the packages. Verifying against the developer's own keyring
    would answer a different question and would pass on the one machine
    where the answer does not matter."""
    code = _code(_publish())
    assert 'verify_home="$(mktemp -d)"' in code, (
        "verification does not use a keyring of its own")
    assert '--homedir "$verify_home" --import "$PUBLIC_KEY"' in code, (
        "the verification keyring is not built out of the published key alone")
    assert 'GOODSIG' in code, (
        "verification reads gpg's prose rather than its status output; gpg "
        "exits 0 for a good signature from an untrusted key, which is "
        "exactly what a fresh keyring holds")


# --------------------------------------------------------------------
# What is staged is what a static host can serve
# --------------------------------------------------------------------

def test_the_staged_layout_is_what_the_online_url_asks_for():
    """ONLINE_REPO_URL ends in $arch, so what is published is the
    directory ABOVE the architecture directory - the key sits there and
    the packages sit below it. installer/core/source.py decided this
    before anything was built; publish.sh has to match it rather than
    choose."""
    source = _read(ROOT / "installer" / "core" / "source.py")
    assert re.search(r'ONLINE_REPO_URL = "[^"]+/\$arch"', source)

    code = _code(_publish())
    assert 'mkdir -p "$dest/x86_64"' in code, (
        "the staged tree has no architecture directory for $arch to resolve to")
    assert '"$dest/zepos-repo.pub"' in code, (
        "the public key is not published above the architecture directory, "
        "where a URL ending in $arch leaves it")


def test_symlinks_are_resolved_because_pages_does_not_follow_them():
    """repo-add writes `zepos.db` as a symlink to `zepos.db.tar.gz`. Git
    stores that faithfully and a static host serves the link rather than
    the file, so pacman fetches nineteen bytes of path and reports a
    corrupted database. Published as regular files."""
    code = _code(_publish())
    assert re.search(r'rsync -aL', code), (
        "the staging copy does not dereference symlinks, so zepos.db would "
        "be published as a link")


def test_the_repo_add_backup_is_not_published():
    """repo-add keeps the previous database as *.old next to the new one.
    It is a backup of a build artefact, no pacman ever asks for it, and
    it is one more file to keep forever in a branch."""
    assert "--exclude '*.old'" in _code(_publish())


def test_jekyll_is_turned_off():
    """Without .nojekyll, Pages runs the tree through Jekyll, which drops
    every path beginning with an underscore or a dot and can fail a
    deploy over a file it does not understand. There is nothing here to
    render."""
    assert '"$dest/.nojekyll"' in _code(_publish())


def test_the_database_is_compared_against_the_directory():
    """A database naming a package that is not there fails at download; a
    directory holding a package the database omits simply never serves
    it. Both are produced by the ordinary accident of a build interrupted
    between makepkg and repo-add, and both are silent until somebody
    installs."""
    code = _code(_publish())
    assert 'tar tzf "$ARCH_DIR/zepos.db.tar.gz"' in code, (
        "the database is never read")
    assert re.search(r'in_db.*!=.*on_disk|"\$in_db" != "\$on_disk"', code), (
        "the database contents are never compared with the files present")


# --------------------------------------------------------------------
# The branch cannot grow without bound
# --------------------------------------------------------------------

def test_every_publish_is_an_orphan_commit():
    """Package tarballs are large - zepos-hyprland alone is 51 MB - and
    git keeps every version of every blob forever. A gh-pages branch with
    ordinary history would grow by the size of the whole repository on
    every release and never shrink.

    `commit-tree` with no -p is what stops that: the branch is exactly
    one commit at all times and the previous release's blobs are
    unreachable the moment a new one is written.
    """
    code = _code(_publish())
    commit_tree = re.search(r'commit-tree ([^\n]*)', code)
    assert commit_tree, "publish.sh does not make a commit object"
    assert " -p " not in commit_tree.group(1), (
        "the publish commit has a parent, so the branch keeps every "
        "package tarball ever published")


def test_the_orphan_commit_is_why_the_manifest_is_published():
    """The cost of throwing the history away is that nothing records what
    was served last week. manifest.txt - the commit, the Arch snapshot
    and the sha256 of every package - is therefore published WITH the
    packages rather than kept in a branch history that does not exist."""
    assert '"$dest/manifest.txt"' in _code(_publish())


def test_the_two_limits_that_belong_to_github_are_checked_here():
    """A blob over 100 MB is rejected by git itself, so a push that
    contains one fails after uploading everything else. Pages publishes
    at most 1 GB. Both are cheaper to find before the push than during
    it."""
    code = _code(_publish())
    assert "MAX_FILE_BYTES" in code and "MAX_SITE_BYTES" in code
    assert "-size +\"$MAX_FILE_BYTES\"c" in code, (
        "no file size is checked before a push that git would reject")


def test_nothing_staged_can_reach_the_source_branch():
    """The staged tree defaults to a directory inside packaging/out/,
    which .gitignore excludes in full. That is deliberate: `git add -A`
    in the source tree must never pick up 57 MB of packages, and the
    publish commit uses -f precisely because the ignore rules that are
    right for the source branch are what the publish branch exists to
    hold instead."""
    code = _code(_publish())
    assert 'dest="$OUT/pages"' in code, (
        "the staging default is no longer inside packaging/out/")
    assert "packaging/out/" in _read(ROOT / ".gitignore")


# --------------------------------------------------------------------
# The local server, and the run that measures the whole path
# --------------------------------------------------------------------

def test_the_local_server_serves_the_staged_tree_and_not_the_build():
    """A test against packaging/out/ measures a layout that will never be
    published - zepos.db is a symlink there and a `.old` backup sits next
    to it. serve-repo.sh runs the staging step first, so what an
    installed system is pointed at during a measurement is the byte-for-
    byte output of publish.sh."""
    serve = _code(_read(PACKAGING / "serve-repo.sh"))
    assert '"$PACKAGING/publish.sh" --into "$dest"' in serve, (
        "serve-repo.sh serves something other than the staged tree")
    assert "http.server" in serve


def test_the_local_server_does_not_offer_the_repository_to_the_network():
    """The packages being served are signed, and today they are signed
    with a test key. On this machine an IPsec tunnel routes all three
    RFC1918 ranges (spec §10.1), so 0.0.0.0 is not a small default. A
    QEMU guest reaches the loopback through slirp anyway."""
    serve = _code(_read(PACKAGING / "serve-repo.sh"))
    assert "bind=127.0.0.1" in serve, "the default bind address is not the loopback"


def test_the_update_scenario_measures_the_published_shape():
    """iso/test-boot.py --scenario update is the half of this that no
    file read can do. It hands the guest a URL ending in $arch, exactly
    as installer/core/source.py's does, so what is measured is the shape
    of the published URL with a different host in front of it."""
    harness = _read(ISO / "test-boot.py")
    assert 'repo_url = f"http://{SLIRP_HOST}:{port}/$arch"' in harness, (
        "the guest is pointed at a URL that is not the shape of the "
        "published one")
    assert '"pass": "update=0"' in harness, (
        "the update scenario grades on something other than the guest's own "
        "summary")
    assert "serve_repository(run, port, arguments.repo_dir)" in harness


def test_the_update_run_changes_nothing_but_the_server_line():
    """A run that had to relax SigLevel in order to succeed would be
    measuring the relaxation. The guest rewrites one line, and puts the
    file back before the machine powers off - which is also the cheapest
    possible check that it only ever touched one line."""
    update = _read(ISO / "profile/airootfs/usr/local/bin/zepos-smoke-update")
    code = _code(update)
    assert re.search(r"sed -i \"/\^\\\[zepos\\\]/,/\^\\\[/\{s#\^Server \*=", code), (
        "the update probe does not restrict its rewrite to the Server line "
        "inside [zepos]")
    # Reading the SigLevel in order to report it is the point; writing
    # one into the machine's pacman.conf would be the thing that
    # invalidates the run. Every in-place edit of that file is examined,
    # and there may be exactly one.
    edits = re.findall(r'^sed -i .*"\$PACMAN_CONF"', code, re.M)
    assert len(edits) == 1, (
        f"the update probe edits /etc/pacman.conf {len(edits)} times; one "
        f"of them is not the Server line: {edits}")
    assert "SigLevel" not in edits[0]
    # Und die Sonde schreibt ueberhaupt kein SigLevel mehr, nirgends.
    #
    # Bis UP-1 legte die Gegenprobe eine eigene, nur [zepos] nennende
    # pacman.conf an und trug dort "SigLevel = Required TrustedOnly" ein
    # - diese Zeile war das, was diese Zusicherung frueher geprueft hat.
    # Die Gegenprobe laeuft jetzt ueber `zepos-update` gegen die
    # AUSGELIEFERTE Konfiguration, was strenger ist: gemessen wird die
    # Datei, die auf der Maschine liegt, und nicht eine, die der
    # Messstand gerade geschrieben hat. Eine geschriebene SigLevel-Zeile
    # waere ab hier also in jedem Fall ein Rueckschritt.
    assert not re.findall(r"^SigLevel\s*=", code, re.M), (
        "die Sonde schreibt eine SigLevel-Zeile - gemessen wird dann ihre "
        "eigene Konfiguration und nicht die der Maschine")
    # Gelesen wird sie sehr wohl, und das ist der Beleg dafuer, dass die
    # Maschine mit `Required` in die Messung gegangen ist.
    assert "/^SigLevel/p" in code
    assert 'cp "$BACKUP" "$PACMAN_CONF"' in code, (
        "the machine is left pointing at the harness's server")


def test_the_update_run_proves_the_verification_is_real():
    """Everything else in that run passes just as well on a machine that
    verifies nothing. Taking the key away and asking again is the half
    that says the signatures matter - and `pacman-key --populate zepos`
    afterwards is the only thing zepos-keyring's scriptlet does, so a
    machine that recovers by running it has shown the PACKAGE is what
    makes the repository usable."""
    code = _code(_read(ISO / "profile/airootfs/usr/local/bin/zepos-smoke-update"))
    assert 'pacman-key --delete "$fingerprint"' in code
    assert "pacman-key --populate zepos" in code
    assert re.search(r"^\(\( without_key_rc != 0 \)\)\s*\|\| update_rc=\d+$",
                     code, re.M), (
        "a repository accepted without the key would still be graded a pass")
    # Und die zweite Haelfte, die es seit UP-1 gibt: es reicht nicht,
    # dass der Aktualisierer scheitert - er muss es HINTERLASSEN. Ein
    # Dienst, der nachts an einer Unterschrift scheitert und nichts
    # ablegt, ist von einer Maschine, die auf dem Stand ist, nicht zu
    # unterscheiden.
    assert re.search(r"^\(\( without_key_said == 0 \)\)\s*\|\| update_rc=\d+$",
                     code, re.M), (
        "ein Fehlschlag, den niemand hinterlaesst, wuerde noch immer als "
        "bestanden gelten")
    assert "/usr/share/pacman/keyrings/zepos-trusted" in code, (
        "the fingerprint comes from somewhere other than the file "
        "zepos-keyring ships")


def test_the_download_check_does_not_read_a_translation():
    """Measured, and it cost a run: the first version counted the string
    `Total Download Size` in pacman's output. An installed ZepOS is a
    German system, pacman is translated, and the line says
    "Gesamtgröße des Downloads" - so the check reported 0 for a run that
    had downloaded the package perfectly well.

    The cache is the fact rather than a rendering of it, and it is
    emptied immediately before the transaction so that a file in it
    afterwards can only have come from the server.
    """
    code = _code(_read(ISO / "profile/airootfs/usr/local/bin/zepos-smoke-update"))
    assert "Total Download Size" not in code
    assert "rm -f /var/cache/pacman/pkg/zepos-*.pkg.tar.zst*" in code, (
        "the cache is not emptied, so pacman can satisfy the transaction "
        "without contacting the repository at all")
    assert 'find /var/cache/pacman/pkg' in code, (
        "whether anything was downloaded is not read out of the cache")
