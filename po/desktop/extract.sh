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

# --------------------------------------------------------------------
# Der Anwendungsstarter, seit dem 02.09.2026
# --------------------------------------------------------------------
#
# WARUM HIER UEBERHAUPT NOCH EIN DURCHGANG STEHT
#     hyprlaunch ist C++ und lief bis heute an gettext vorbei - seine
#     sichtbaren Zeichenketten standen fest auf Deutsch im Quelltext,
#     waehrend derselbe Schreibtisch daneben diesen Katalog fuehrt. Seit
#     dem 02.09.2026 rufen sie _(), und damit muessen sie hier
#     herauskommen.
#
# WARUM AUS EINEM PATCH UND NICHT AUS EINER .cpp
#     Weil die .cpp nicht in diesem Repository liegt und nicht darf:
#     plugins/LICENSE fuehrt aus, dass der uebernommene Baum von
#     azzuriel ueberhaupt keine Lizenz traegt und eine geaenderte KOPIE
#     davon hier nichts zu suchen hat. Was hier liegt, ist ZepOS'
#     EIGENES Diff - und genau die Zeilen, die es hinzufuegt, sind die
#     Zeilen mit den Zeichenketten. Sie zu lesen heisst also, ZepOS'
#     eigenen Quelltext zu lesen, und nichts sonst.
#
# WARUM NUR DIE C++-BLOECKE
#     GEMESSEN am 02.09.2026: nimmt man alle zugefuegten Zeilen, ist
#     CMakeLists.txt mit dabei, und dessen Kommentare beginnen mit '#'.
#     Fuer einen C++-Leser ist '#' keine Kommentarzeile, sondern eine
#     Praeprozessoranweisung - ein Anfuehrungszeichen in so einem
#     Kommentar ("Zum Dock hinzufügen" stand darin) galt damit als
#     Beginn einer Zeichenkette, xgettext warnte zweimal
#     "Zeichenkette nicht korrekt terminiert", und ZWEI msgids fielen
#     still aus der Auslese. Deshalb entscheidet die Endung des Blocks.
#
# WARUM --add-location=file UND NICHT MEHR
#     Die Zeilennummer der rekonstruierten Datei ist NICHT die
#     Zeilennummer im Patch - die Bloecke werden aneinandergehaengt und
#     die Kopfzeilen fallen weg. Eine Nummer, die nicht stimmt, ist
#     schlechter als keine; der Dateiname allein ist wahr und fuehrt
#     zum richtigen Ort.
STARTER="packaging/zepos-hyprlaunch/zepos-hyprlaunch.patch"
POT_STARTER="$(mktemp -d)"
trap 'rm -rf "$POT_STARTER"' EXIT

# Unter GENAU dem Pfad, den der Patch im Repository hat: xgettext
# schreibt den Dateinamen so in das '#:' des Katalogs, wie es ihn
# bekommt. So steht dort hinterher der Ort, an dem die Zeichenkette
# wirklich steht.
mkdir -p "$POT_STARTER/$(dirname "$STARTER")"
awk '
    /^diff -ruN /    { cpp = ($NF ~ /\.(cpp|hpp)$/); next }
    /^(---|\+\+\+) / { next }
    cpp && /^\+/     { print substr($0, 2) }
' "$WURZEL/$STARTER" > "$POT_STARTER/$STARTER"

xgettext \
    --no-wrap \
    --language=C++ \
    --from-code=UTF-8 \
    --keyword=_ \
    --package-name=zepos-desktop \
    --msgid-bugs-address="https://github.com/ZeptronIT/ZepOS" \
    --add-comments=UEBERSETZER \
    --add-location=file \
    --directory="$POT_STARTER" \
    --output="$POT_STARTER/starter.pot" \
    "$STARTER"

# Eine Auslese ohne einen einzigen Treffer schreibt GAR KEINE Datei -
# gemessen am selben Tag. Das ist kein Fehler, sondern ein Patch ohne
# uebersetzte Zeichenkette; dann bleibt die .pot von oben, wie sie ist.
if [ -f "$POT_STARTER/starter.pot" ]; then
    # --use-first, damit ein msgid, den es in beiden gibt, seine
    # Fundstelle aus den VORLAGEN behaelt. "Add to dock" ist so ein
    # Fall: der Fuss, das Home und der Starter tragen ihn, und genau
    # das ist der Zweck - eine Beschriftung, drei Menues.
    msgcat --no-wrap --use-first \
        "$HIER/zepos-desktop.pot" "$POT_STARTER/starter.pot" \
        --output-file="$POT_STARTER/zusammen.pot"
    mv "$POT_STARTER/zusammen.pot" "$HIER/zepos-desktop.pot"
fi

echo "geschrieben: $HIER/zepos-desktop.pot"
