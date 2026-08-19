#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Liest die uebersetzbaren Zeichenketten aus den AGS-Vorlagen und
# schreibt sie in zepos-desktop.pot. Danach traegt `msgmerge` sie in
# de.po nach, ohne vorhandene Uebersetzungen zu verlieren:
#
#     ./extract.sh && msgmerge --no-wrap -U de.po zepos-desktop.pot
#
# WARUM --language=JavaScript AUF EINER .template-DATEI
#     Die Vorlagen sind TypeScript mit {{PLATZHALTERN}} darin, und
#     xgettext entscheidet sonst an der Endung, was es vor sich hat -
#     ".template" kennt es nicht. Gemessen am 17.08.2026: mit der Angabe
#     liest es `_("...")` und `ngettext("...", "...", n)` sauber aus.
#
# WAS ES NICHT SIEHT, und warum das hier steht statt in einem Fehler
#     Ein Template-Literal mit Einsetzung - `_(\`Tick ${x}\`)` - taucht
#     in KEINER erzeugten .pot-Datei auf, gemessen am selben Tag. Genau
#     deshalb gibt es format() in utils/i18n.ts: benannte Platzhalter in
#     einer gewoehnlichen Zeichenkette, die xgettext lesen kann.
#     tests/src/test_ags_i18n.py haelt beide Enden zusammen - es zaehlt
#     die sichtbaren Zeichenketten der Vorlagen und verlangt fuer jede
#     einen Katalogeintrag.
#
# WELCHE VORLAGEN GELESEN WERDEN
#     Die TypeScript-Widgets, und nur die. Nicht ags-style.template
#     (SCSS) und nicht die vier ags-*-scripts.template - das sind
#     SHELL-Skripte, und xgettext als JavaScript darauf losgelassen warf
#     am 17.08.2026 neununddreissig Warnungen ("Zeichenkette nicht
#     terminiert", "RegExp-Literal wurde zu frueh terminiert") ueber
#     Anfuehrungszeichen, die in einer Shell etwas anderes bedeuten.
#     Keine davon hatte einen Befund, aber neununddreissig Warnungen
#     sind der Ort, an dem die vierzigste ungelesen bleibt.
#
#     Die Liste hier kann trotzdem nicht still veralten: fuegt jemand
#     `_()` in eines dieser Skripte ein, verlangt
#     tests/src/test_ags_i18n.py fuer den msgid einen Katalogeintrag,
#     den diese Auslese nie erzeugt hat - und der Testlauf sagt es.
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
WURZEL="$(cd "$HIER/../.." && pwd)"

VORLAGEN=()
for pfad in "$WURZEL"/src/templates/ags-*.template; do
    name="$(basename "$pfad")"
    case "$name" in
        *-scripts.template|ags-style.template) continue ;;
    esac
    VORLAGEN+=("src/templates/$name")
done

# --no-wrap, UND DAS IST KEIN GESCHMACK
#     GEMESSEN am 19.08.2026 (Aufgabe 32): ohne die Angabe bricht
#     xgettext lange msgids nach 79 Spalten um -
#
#         msgid ""
#         "Position: every screen keeps the place it has. Dragging them "
#         "around each other is ..."
#
#     - und tests/src/test_ags_i18n.py sucht im Katalog nach der
#     ZEICHENFOLGE `msgid "<ganzer Text>"`. Ein umgebrochener Eintrag
#     findet sich darin nicht wieder; der Lauf meldete vier msgids ohne
#     Katalogeintrag und drei Eintraege ohne Uebersetzung, obwohl zwei
#     davon seit Tagen uebersetzt dastanden - ein `msgmerge` hatte sie
#     nur neu umgebrochen. de.po und die .pot sind seither ungebrochen
#     (`msgcat --no-wrap`), und diese Zeile haelt sie so.
xgettext \
    --no-wrap \
    --language=JavaScript \
    --from-code=UTF-8 \
    --keyword=_ \
    --keyword=ngettext:1,2 \
    --keyword=pgettext:1c,2 \
    --package-name=zepos-desktop \
    --msgid-bugs-address="https://github.com/ZeptronIT/ZepOS" \
    --add-comments=UEBERSETZER \
    --sort-by-file \
    --directory="$WURZEL" \
    --output="$HIER/zepos-desktop.pot" \
    "${VORLAGEN[@]}"

echo "geschrieben: $HIER/zepos-desktop.pot"
