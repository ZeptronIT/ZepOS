#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Creates a throwaway signing key for testing the package build.
#
#     ./packaging/make-test-key.sh
#     ZEPOS_GNUPGHOME=packaging/keys/gnupg ./packaging/build.sh --key <printed id>
#
# WHY THIS EXISTS AND WHAT IT IS NOT
#     Spec §8.6 requires signatures from the first ISO: a repository that
#     starts unsigned makes every already-installed system import a key by
#     hand on the day it stops being unsigned. But the release key is not
#     something a build script may create, and it is not something that
#     may live in a git repository - so this produces a key that is
#     obviously not it.
#
#     The user id says DO NOT TRUST, the key expires in ninety days, it
#     has no passphrase, and everything it writes lands in
#     packaging/keys/, which .gitignore excludes in full. It exists so
#     that the signing path can be executed and tested; it must never
#     sign anything anybody installs.
#
#     The real key is supplied the same way this one is, and that is the
#     point of the arrangement: packaging/build.sh takes a key id and a
#     GNUPGHOME and knows nothing else about either. On a release machine
#     that is the maintainer's own keyring; here it is this directory.
#     No private key ever enters the build container, and none is ever a
#     file the repository could carry.
set -euo pipefail

readonly REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly KEYS="$REPO/packaging/keys"
readonly GNUPGHOME_DIR="$KEYS/gnupg"

readonly NAME="ZepOS TEST KEY - DO NOT TRUST"
readonly EMAIL="test-key@zepos.invalid"

command -v gpg >/dev/null || { echo "gpg is not installed" >&2; exit 1; }

if [[ -d "$GNUPGHOME_DIR" ]]; then
    echo "packaging/keys/gnupg already exists - delete it to start over" >&2
    GNUPGHOME="$GNUPGHOME_DIR" gpg --list-secret-keys --keyid-format=long
    exit 1
fi

# 0700 before anything is written into it: gpg refuses a world-readable
# GNUPGHOME, and a secret key that existed at 0755 for a moment has
# existed at 0755.
mkdir -p "$GNUPGHOME_DIR"
chmod 0700 "$GNUPGHOME_DIR"
export GNUPGHOME="$GNUPGHOME_DIR"

gpg --batch --gen-key <<PARAMS
%no-protection
Key-Type: eddsa
Key-Curve: ed25519
Key-Usage: sign
Name-Real: $NAME
Name-Email: $EMAIL
Expire-Date: 90d
%commit
PARAMS

fingerprint="$(gpg --list-secret-keys --with-colons "$EMAIL" \
    | awk -F: '/^fpr:/ { print $10; exit }')"

# The public half, in the two shapes the rest of the build wants it:
# binary for `pacman-key --add`, armoured for a human to look at.
gpg --batch --yes --export --output "$KEYS/zepos-test.pub" "$fingerprint"
gpg --batch --yes --armor --export --output "$KEYS/zepos-test.asc" "$fingerprint"

cat <<INFO

Test key created. It is NOT a release key and packaging/keys/ is gitignored.

  fingerprint  $fingerprint
  user id      $NAME <$EMAIL>
  expires      in 90 days
  keyring      packaging/keys/gnupg   (mode $(stat -c %a "$GNUPGHOME_DIR"))

Build with it:

  ZEPOS_GNUPGHOME=packaging/keys/gnupg \\
    ./packaging/build.sh --key $fingerprint

INFO
