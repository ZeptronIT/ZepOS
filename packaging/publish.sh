#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Turns packaging/out/ into the directory GitHub Pages serves, and - only
# when everything about the key is right - into a commit on gh-pages.
#
#     ./packaging/publish.sh                     check and stage into packaging/out/pages
#     ./packaging/publish.sh --into DIR          stage somewhere else
#     ./packaging/publish.sh --commit            also commit onto the local gh-pages branch
#
# It NEVER pushes. The last thing it prints is the push command, for a
# human to read and run.
#
# WHY THIS EXISTS AT ALL
#     installer/core/source.py writes
#     `https://zeptronit.github.io/ZepOS/$arch` into every installed
#     system's pacman.conf, so that URL is a promise the repository has
#     been making since before anything was built. Until something is
#     published, the first `pacman -Syu` of an installed ZepOS reaches a
#     404.
#
# WHAT IS PUBLISHED, AND WHY IT IS NOT A COPY OF packaging/out/
#     Three differences, each of them a property of GitHub Pages rather
#     than a preference:
#
#       symlinks are resolved   repo-add writes `zepos.db` as a symlink to
#                               `zepos.db.tar.gz`. Git stores that as a
#                               symlink and Pages does not resolve one -
#                               the fetch of `zepos.db` would return the
#                               19 bytes of the link target, which pacman
#                               reports as a corrupted database. Published
#                               as regular files.
#       .nojekyll               without it Pages runs the tree through
#                               Jekyll, which drops every path beginning
#                               with `_` or `.` and can fail the deploy
#                               for a file it does not understand. There
#                               is nothing to render here.
#       *.old is left behind    repo-add keeps the previous database next
#                               to the new one. It is a backup of a build
#                               artefact and no pacman ever asks for it.
#
# WHY AN ORPHAN COMMIT
#     Package tarballs are large - zepos-hyprland alone is 51 MB - and git
#     keeps every version of every blob forever. A gh-pages branch with
#     ordinary history would grow by the size of the whole repository on
#     every release and never shrink, and it would be carried by anybody
#     who clones with --no-single-branch.
#
#     So each publish is a commit with NO PARENT. The branch has exactly
#     one commit at all times, the previous release's blobs become
#     unreachable the moment it is written, and the push that ships it is
#     a forced push. The cost is written down where it belongs: there is
#     no history of what was published, which is why manifest.txt - the
#     commit, the snapshot and the sha256 of every package - is published
#     WITH the packages.
#
# WHY IT REFUSES A TEST KEY
#     A repository signed with `ZepOS TEST KEY - DO NOT TRUST` is worse
#     than an unsigned one. Unsigned fails loudly on every machine that
#     asks for a signature; signed-with-a-throwaway succeeds, and the
#     private half is in a working directory, in a container image, and
#     in whatever backup either of those reached. Staging one locally is
#     allowed - that is how the update path is measured without
#     publishing anything - and the staged tree then carries a marker
#     file that --commit refuses to commit.
set -euo pipefail

readonly REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PACKAGING="$REPO/packaging"
readonly OUT="$PACKAGING/out"
readonly ARCH_DIR="$OUT/x86_64"
readonly PUBLIC_KEY="$OUT/zepos-repo.pub"

# The branch GitHub Pages is configured to serve, at its root.
readonly PAGES_BRANCH="gh-pages"

# The file that says "this tree was signed by a key nobody should trust".
# Written by the staging step, read by the commit step, and the reason
# the two steps can be separate at all.
readonly TEST_KEY_MARKER="TEST-KEY-DO-NOT-PUBLISH"

# GitHub's two hard numbers. The 100 MB one is git's, not Pages': a push
# containing a larger blob is rejected outright, so it has to be caught
# here rather than discovered by whoever runs the push.
readonly MAX_FILE_BYTES=$(( 100 * 1000 * 1000 ))
readonly MAX_SITE_BYTES=$(( 1000 * 1000 * 1000 ))

die() { printf 'packaging/publish.sh: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

dest="$OUT/pages"
commit=false

while (( $# )); do
    case "$1" in
        --into)
            [[ $# -ge 2 ]] || die "--into needs a directory"
            dest="$2"; shift 2 ;;
        --commit) commit=true; shift ;;
        -h|--help)
            sed -n '4,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

command -v gpg >/dev/null || die "gpg is not installed"
command -v rsync >/dev/null || die "rsync is not installed"

# --------------------------------------------------------------------
# Is there a repository to publish, and is it signed
# --------------------------------------------------------------------
step "The build in packaging/out/"

[[ -d "$ARCH_DIR" ]] || die \
"no packaging/out/x86_64/. Build the repository first:

    ./packaging/build.sh --key <id>"

[[ -f "$ARCH_DIR/zepos.db.tar.gz" ]] || die "no zepos.db.tar.gz in $ARCH_DIR"

# An unsigned repository is not publishable, and this is the check that
# says so rather than the one that would say so later. Spec §8.6: a
# repository that starts unsigned makes every already-installed system
# import a key by hand on the day it stops being unsigned - so the
# unsigned state must never reach a URL an installed system points at.
[[ -s "$PUBLIC_KEY" ]] || die \
"packaging/out/zepos-repo.pub is missing, so this repository was built with
--no-sign. Every installed ZepOS carries 'SigLevel = Required' for [zepos];
publishing an unsigned repository would make the first upgrade of every one
of them fail. Rebuild with:

    ./packaging/build.sh --key <id>"

[[ -f "$ARCH_DIR/zepos.db.tar.gz.sig" ]] || die \
"zepos.db.tar.gz has no signature. SigLevel = Required covers the DATABASE
as well as the packages: pacman refuses an unsigned database before it looks
at a single package."

packages=("$ARCH_DIR"/*.pkg.tar.zst)
(( ${#packages[@]} )) || die "no packages in $ARCH_DIR"

missing=()
for package in "${packages[@]}"; do
    [[ -f "$package.sig" ]] || missing+=("$(basename "$package")")
done
(( ${#missing[@]} == 0 )) || die \
    "these packages have no signature: ${missing[*]}"

echo "packages       ${#packages[@]}"

# --------------------------------------------------------------------
# Whose key, and does it verify what is here
# --------------------------------------------------------------------
# In a keyring built out of zepos-repo.pub ALONE, in a temporary
# directory. Verifying against the developer's own keyring would answer
# a different question - "can this machine verify it" - and would pass
# on the one machine where the answer does not matter. What has to be
# true is that the signatures verify against THE KEY THAT IS PUBLISHED
# NEXT TO THEM, because that key is the only one an installed system
# will have: it is the same file zepos-keyring ships.
step "Signatures, against the published key alone"

fingerprint="$(gpg --with-colons --show-keys "$PUBLIC_KEY" \
    | awk -F: '/^fpr:/ { print $10; exit }')"
key_uid="$(gpg --with-colons --show-keys "$PUBLIC_KEY" \
    | awk -F: '/^uid:/ { print $10; exit }')"
[[ ${#fingerprint} -eq 40 ]] || die "no fingerprint could be read out of $PUBLIC_KEY"

echo "fingerprint    $fingerprint"
echo "user id        $key_uid"

verify_home="$(mktemp -d)"
trap 'rm -rf "$verify_home"' EXIT
chmod 700 "$verify_home"
gpg --batch --quiet --homedir "$verify_home" --import "$PUBLIC_KEY" \
    || die "the published key could not be imported"

verify() {
    # --status-fd, because gpg's exit code is 0 for a good signature from
    # an untrusted key AND its human-readable output says WARNING in the
    # middle of it. GOODSIG is the machine-readable statement, and an
    # untrusted key is exactly what this keyring has - it was imported a
    # line ago and nothing has signed it.
    gpg --batch --quiet --homedir "$verify_home" --status-fd 1 \
        --verify "$1" "$2" 2>/dev/null | grep -q '^\[GNUPG:\] GOODSIG'
}

bad=()
verify "$ARCH_DIR/zepos.db.tar.gz.sig" "$ARCH_DIR/zepos.db.tar.gz" \
    || bad+=("zepos.db.tar.gz")
for package in "${packages[@]}"; do
    verify "$package.sig" "$package" || bad+=("$(basename "$package")")
done
(( ${#bad[@]} == 0 )) || die \
"these files are NOT signed by the key published next to them: ${bad[*]}

An installed system has that key and no other. A signature from anything
else is a signature it will refuse."
echo "verified       ${#packages[@]} packages and the database, all against $fingerprint"

# --------------------------------------------------------------------
# Does the database describe the directory
# --------------------------------------------------------------------
# A repository whose database names a package that is not there fails at
# download; one that omits a package that IS there simply never serves
# it. Both are silent until somebody installs, and both are produced by
# the ordinary accident of a build that was interrupted between makepkg
# and repo-add.
step "Database against directory"

in_db="$(tar tzf "$ARCH_DIR/zepos.db.tar.gz" \
    | sed -n 's#^\([^/]*\)/$#\1#p' | sort)"
on_disk="$(for package in "${packages[@]}"; do
        # <name>-<pkgver>-<pkgrel>-<arch>.pkg.tar.zst, which is the entry
        # name repo-add uses minus the architecture. Cut from the right,
        # because a package name may contain any number of dashes.
        base="$(basename "$package" .pkg.tar.zst)"
        echo "${base%-*}"
    done | sort)"

if [[ "$in_db" != "$on_disk" ]]; then
    printf 'in the database but not on disk:\n%s\n' \
        "$(comm -23 <(echo "$in_db") <(echo "$on_disk"))" >&2
    printf 'on disk but not in the database:\n%s\n' \
        "$(comm -13 <(echo "$in_db") <(echo "$on_disk"))" >&2
    die "zepos.db does not describe packaging/out/x86_64/. Re-run ./packaging/build.sh"
fi
echo "database       $(wc -l <<<"$in_db") entries, exactly the files present"

# --------------------------------------------------------------------
# Stage the tree Pages will serve
# --------------------------------------------------------------------
step "Stage into $dest"
rm -rf "$dest"
mkdir -p "$dest/x86_64"

# -L: every symlink becomes the file it points at. See the header - a
# symlink survives git and does not survive Pages, and `zepos.db` is one.
# --exclude '*.old': repo-add's backup of the previous database.
rsync -aL --exclude '*.old' --exclude '*.old.sig' \
    "$ARCH_DIR"/ "$dest/x86_64"/

# The key, above the architecture directory: ONLINE_REPO_URL ends in
# $arch, so this is what `https://zeptronit.github.io/ZepOS/zepos-repo.pub`
# resolves to. It is the same bytes zepos-keyring ships, which is what
# lets somebody who already installed ZepOS check the one against the
# other.
install -m644 "$PUBLIC_KEY" "$dest/zepos-repo.pub"

# What was built, from what. The orphan commit throws the history of the
# branch away on every publish, so this file is the only record of which
# tree and which Arch snapshot produced what is being served.
[[ -f "$OUT/manifest.txt" ]] && install -m644 "$OUT/manifest.txt" "$dest/manifest.txt"

# Not decoration. Without it Pages runs Jekyll over the tree.
: > "$dest/.nojekyll"

# --------------------------------------------------------------------
# A page for the person who types the URL into a browser
# --------------------------------------------------------------------
# pacman never fetches the root, so this exists only for a human - and
# for a specific human: somebody who has an installed ZepOS, has been
# told to trust a key, and wants to check the fingerprint against
# something other than the machine that told them. German, because every
# other user-facing string in this project is.
cat > "$dest/index.html" <<HTML
<!DOCTYPE html>
<html lang="de">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZepOS-Paketquelle</title>
<style>
  body { font-family: sans-serif; max-width: 46rem; margin: 2rem auto;
         padding: 0 1rem; line-height: 1.5; }
  code, pre { font-family: ui-monospace, monospace; }
  pre { background: #f4f4f4; padding: .75rem; overflow-x: auto; }
  @media (prefers-color-scheme: dark) {
    body { background: #16161a; color: #e6e6e6; }
    pre { background: #232329; }
  }
</style>
<h1>ZepOS-Paketquelle</h1>
<p>Dies ist die Paketquelle von ZepOS. Sie wird von <code>pacman</code>
gelesen, nicht von einem Browser.</p>
<h2>Eintrag in <code>/etc/pacman.conf</code></h2>
<pre>[zepos]
SigLevel = Required TrustedOnly
Server = https://zeptronit.github.io/ZepOS/\$arch</pre>
<p>Ein installiertes ZepOS hat diesen Eintrag bereits; das Paket
<code>zepos-keyring</code> bringt den Schluessel mit.</p>
<h2>Schluessel</h2>
<p>Fingerabdruck:</p>
<pre>$fingerprint</pre>
<p>$key_uid</p>
<p>Der oeffentliche Schluessel liegt als
<a href="zepos-repo.pub">zepos-repo.pub</a> daneben. Von Hand importiert
wird er so:</p>
<pre>pacman-key --add zepos-repo.pub
pacman-key --lsign-key $fingerprint</pre>
<h2>Was hier liegt</h2>
<p><a href="manifest.txt">manifest.txt</a> nennt den Commit, den
Arch-Stichtag und die sha256-Summe jedes Pakets.
<a href="x86_64/">x86_64/</a> ist das Verzeichnis, das <code>\$arch</code>
im Server-Eintrag aufloest.</p>
</html>
HTML

# --------------------------------------------------------------------
# The two limits that are somebody else's, and the marker that is ours
# --------------------------------------------------------------------
oversized="$(find "$dest" -type f -size +"$MAX_FILE_BYTES"c -printf '%f (%s bytes)\n')"
[[ -z "$oversized" ]] || die \
"git refuses a blob over 100 MB, so these can never be pushed:
$oversized"

total_bytes="$(du -sb "$dest" | cut -f1)"
(( total_bytes < MAX_SITE_BYTES )) || die \
"the staged site is $(( total_bytes / 1000 / 1000 )) MB and GitHub Pages
publishes at most 1 GB."

is_test_key=false
if [[ "$key_uid" == *"DO NOT TRUST"* ]]; then
    is_test_key=true
    cat > "$dest/$TEST_KEY_MARKER" <<MARKER
This tree was signed by a key whose own user id says it must not be
trusted:

    $key_uid
    $fingerprint

packaging/publish.sh refuses to commit any tree containing this file.
Delete it and you have a repository that LOOKS verified to every machine
that fetches it, signed by a private key that lives in a working
directory. Build with a release key instead; packaging/README.md has the
checklist.
MARKER
fi

echo "staged         $(du -sh "$dest" | cut -f1) in $dest"
printf '%s\n' \
    "  $dest/x86_64/zepos.db          -> .../ZepOS/x86_64/zepos.db" \
    "  $dest/zepos-repo.pub           -> .../ZepOS/zepos-repo.pub"

if $is_test_key; then
    cat >&2 <<WARNING

    WARNING: this repository is signed with a TEST key.

        $key_uid

    The tree in $dest carries $TEST_KEY_MARKER
    and cannot be committed. Serving it locally is what it is for -
    ./packaging/serve-repo.sh and iso/test-boot.py --scenario update
    measure the whole update path against it without publishing
    anything.

WARNING
fi

# --------------------------------------------------------------------
# Commit, if asked and if allowed
# --------------------------------------------------------------------
if ! $commit; then
    step "Not committed (--commit does that)"
    echo "Nothing was written to git. The staged tree above is what"
    echo "GitHub Pages would serve, byte for byte."
    exit 0
fi

$is_test_key && die \
"refusing to commit a repository signed with $key_uid.

There is no flag for this. A published repository signed with a throwaway
key is worse than an unsigned one: every machine that fetches it verifies
successfully against a private key that is in a working directory.
packaging/README.md lists what has to be true before the first publish."

step "Commit onto $PAGES_BRANCH"

# Plumbing rather than a worktree, for two reasons that both matter.
#
# A temporary index and --work-tree mean the checked-out branch is never
# touched: this can be run with uncommitted work in the tree and nothing
# of it is staged, moved or stashed.
#
# commit-tree with NO -p is what makes the commit an orphan. Every
# publish replaces the branch rather than extending it, so the branch is
# always exactly one commit and last release's 58 MB of blobs are
# unreachable the moment this runs.
# A path that does NOT exist yet, and that is the whole reason this is
# two lines instead of `$(mktemp)`. Measured: git refuses an index file
# that exists and is empty - "fatal: <path>: index file smaller than
# expected" - and mktemp's job is to create the file. It has to be a name
# in a directory nobody else can write to, which is what mktemp -d gives.
index_dir="$(mktemp -d)"
index="$index_dir/index"
trap 'rm -rf "$verify_home" "$index_dir"' EXIT

# -f, deliberately: everything being published is gitignored on purpose
# (.gitignore excludes packaging/out/ in full, and *.db, *.pkg.tar.zst
# and the key material by name). Those rules are right for the source
# branch and are exactly what this branch exists to hold instead.
GIT_INDEX_FILE="$index" git --git-dir="$REPO/.git" --work-tree="$dest" \
    add -A -f .
tree="$(GIT_INDEX_FILE="$index" git --git-dir="$REPO/.git" write-tree)"

source_commit="$(git -C "$REPO" rev-parse HEAD)"
version="$(<"$REPO/VERSION")"
new_commit="$(git --git-dir="$REPO/.git" commit-tree "$tree" -m \
"ZepOS $version repository

Built from $source_commit
Signed by $fingerprint
$key_uid

Orphan commit: this branch is replaced, never extended. See
packaging/publish.sh for why.")"

git --git-dir="$REPO/.git" update-ref "refs/heads/$PAGES_BRANCH" "$new_commit"

step "Done - and NOT pushed"
cat <<PUSH
$PAGES_BRANCH is now $new_commit (orphan, $(du -sh "$dest" | cut -f1)).

Nothing has left this machine. The push is a human's decision and a
FORCED one, because the branch has no shared history to fast-forward:

    git push --force origin $PAGES_BRANCH

Then, once, in the repository's settings:

    Settings -> Pages -> Source: "Deploy from a branch"
                         Branch: $PAGES_BRANCH / (root)

The first deploy takes a minute or two. Afterwards:

    curl -sI https://zeptronit.github.io/ZepOS/x86_64/zepos.db
PUSH
