#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Compiles the .po catalogues into the .mo files gettext reads at runtime.
# A development checkout has no installed catalogue, so this writes into
# po/build/ where i18n.py's DEV_LOCALEDIR looks. The PKGBUILD runs the
# same command against /usr/share/locale.
#
# ZWEI DOMAENEN, EIN SKRIPT (17.08.2026)
#     zepos-installer ist der Katalog des Installers, zepos-desktop der
#     der Oberflaeche. Getrennt sind sie, weil der Domaenenname im
#     Dateinamen des .mo steht und ein installiertes ZepOS keinen
#     Installer hat - es waere ein Katalog, dessen Name luegt.
#
#     Es ist ausdruecklich KEINE zweite Mechanik: dasselbe gettext,
#     dasselbe msgfmt, dasselbe .po-Format, dasselbe Ausgabeverzeichnis.
#     Nur der Name der erzeugten Datei unterscheidet sich, und genau
#     dafuer gibt es Domaenen.
#
#     Die Kataloge des Installers liegen weiterhin in po/*.po und wurden
#     NICHT verschoben: tests/installer/test_i18n.py nennt po/de.po beim
#     Namen, und ein Umzug haette einen Test gebrochen, um eine
#     Symmetrie zu gewinnen, die niemand liest.
set -euo pipefail

HIER="$(dirname "$0")"
OUT="${1:-$HIER/build}"

# domaene:verzeichnis - die Kataloge liegen je Domaene woanders.
DOMAENEN=(
    "zepos-installer:$HIER"
    "zepos-desktop:$HIER/desktop"
)

for eintrag in "${DOMAENEN[@]}"; do
    domain="${eintrag%%:*}"
    verzeichnis="${eintrag#*:}"
    for po in "$verzeichnis"/*.po; do
        # Eine Domaene ohne einen einzigen Katalog ist kein Fehler,
        # sondern eine Sprache, die noch niemand uebersetzt hat.
        [ -e "$po" ] || continue
        lang=$(basename "$po" .po)
        target="$OUT/$lang/LC_MESSAGES"
        mkdir -p "$target"
        msgfmt -o "$target/$domain.mo" "$po"
        echo "built: $target/$domain.mo"
    done
done
