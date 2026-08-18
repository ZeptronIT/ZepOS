#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Serves the repository GitHub Pages would serve, from this machine.
#
#     ./packaging/serve-repo.sh                    stage and serve on 127.0.0.1:8765
#     ./packaging/serve-repo.sh --port 9000
#     ./packaging/serve-repo.sh --bind 0.0.0.0     reachable from the network
#     ./packaging/serve-repo.sh --no-stage         serve an already staged tree
#
# WHY THIS IS NOT `python3 -m http.server` IN packaging/out/
#     Because packaging/out/ is not what Pages serves. `zepos.db` there
#     is a symlink, there is a `.old` backup next to the database, and
#     neither survives a static host in the form it has on disk. This
#     runs packaging/publish.sh --into first, so what is served is the
#     staged tree - byte for byte the one a push would publish. A local
#     test against anything else measures a layout nobody will ever
#     fetch.
#
# WHY IT BINDS TO THE LOOPBACK
#     The repository being served is a directory of signed packages and,
#     today, they are signed with a test key. Binding to 0.0.0.0 offers
#     that to every machine that can reach this one, and on this machine
#     that is an IPsec tunnel (spec §10.1). It is available with --bind
#     and it is not the default.
#
#     A QEMU guest on user networking reaches the loopback anyway: slirp
#     maps 10.0.2.2 to the host, so `http://10.0.2.2:8765/$arch` in the
#     guest is this server. That is how iso/test-boot.py --scenario
#     update measures an installed system's `pacman -Syu` without
#     anything being published.
set -euo pipefail

readonly REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly PACKAGING="$REPO/packaging"

die() { printf 'packaging/serve-repo.sh: %s\n' "$*" >&2; exit 1; }

port=8765
bind=127.0.0.1
dest="$PACKAGING/out/pages"
stage=true

while (( $# )); do
    case "$1" in
        --port) [[ $# -ge 2 ]] || die "--port needs a number"; port="$2"; shift 2 ;;
        --bind) [[ $# -ge 2 ]] || die "--bind needs an address"; bind="$2"; shift 2 ;;
        --into) [[ $# -ge 2 ]] || die "--into needs a directory"; dest="$2"; shift 2 ;;
        --no-stage) stage=false; shift ;;
        -h|--help)
            sed -n '4,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

command -v python3 >/dev/null || die "python3 is not installed"

if $stage; then
    "$PACKAGING/publish.sh" --into "$dest"
fi

[[ -f "$dest/x86_64/zepos.db" ]] || die \
    "no staged repository at $dest - run without --no-stage"

cat <<INFO

Serving $dest
  http://$bind:$port/

An installed ZepOS reaches it with this in /etc/pacman.conf, and with
nothing else changed - SigLevel stays Required, because the point of
serving the staged tree is that the signatures still verify:

    [zepos]
    SigLevel = Required TrustedOnly
    Server = http://$bind:$port/\$arch

From a QEMU guest on user networking, the host is 10.0.2.2:

    Server = http://10.0.2.2:$port/\$arch

Ctrl-C stops it.

INFO

exec python3 -m http.server --directory "$dest" --bind "$bind" "$port"
