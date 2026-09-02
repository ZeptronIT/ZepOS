# SPDX-License-Identifier: GPL-3.0-or-later
"""Jede Zeichenkette, die der Python-Teil des Schreibtischs uebersetzt
haben will, muss im Katalog auch eine Uebersetzung FINDEN.

WARUM ES DIESE DATEI GIBT
    GEMESSEN am 02.09.2026, unmittelbar bevor 0.1.14 gebaut werden
    sollte: das Einstellungsfenster, src/displays.py und src/apps.py
    riefen `_()` mit 226 englischen msgids - und 213 davon standen in
    keinem Katalog. po/desktop/extract.sh las die AGS-Vorlagen und den
    Starter-Patch, aber keine einzige .py-Datei.

    Die Wirkung war kein fehlender Text, sondern der falsche: gettext
    gibt den msgid zurueck, wenn es nichts findet. Ein Fenster, das
    vorher DEUTSCH war, sprach nach der "Uebersetzung" englisch. Kein
    Test sah es, weil jeder von ihnen den msgid erwartete - und den
    bekam er ja.

WARUM AM QUELLTEXT UND NICHT AN xgettext
    Weil diese Zusicherung genau dann etwas wert ist, wenn die Auslese
    kaputt ist. Ein Test, der po/desktop/extract.sh aufruft und dessen
    Ergebnis mit dem Katalog vergleicht, haette am 02.09.2026 gruen
    gemeldet: die Auslese kannte die Dateien nicht, also fehlten die
    msgids auf BEIDEN Seiten. Gelesen wird darum der Quelltext selbst.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
KATALOG = WURZEL / "po" / "desktop" / "de.po"

# Die Namen, unter denen desktop_i18n eingefuehrt wird. `N_()` markiert
# nur - aber was markiert wird, wird spaeter uebersetzt, also braucht es
# denselben Eintrag.
AUFRUFE = {"_": (0,), "N_": (0,), "ngettext": (0, 1)}


def _dateien() -> list[Path]:
    """Die Python-Dateien, die den Katalog des Schreibtischs benutzen."""
    gefunden = []
    for ordner in ("src", "settings"):
        for pfad in sorted((WURZEL / ordner).rglob("*.py")):
            if "desktop_i18n" in pfad.read_text(encoding="utf-8"):
                gefunden.append(pfad)
    return gefunden


def _msgids(pfad: Path) -> list[tuple[int, str]]:
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    raus = []
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        name = getattr(knoten.func, "id", None)
        if name not in AUFRUFE:
            continue
        for stelle in AUFRUFE[name]:
            if stelle >= len(knoten.args):
                continue
            wert = knoten.args[stelle]
            if isinstance(wert, ast.Constant) and isinstance(wert.value, str):
                raus.append((wert.lineno, wert.value))
            elif isinstance(wert, ast.JoinedStr):
                raus.append((wert.lineno, None))
    return raus


def _katalog() -> dict[str, str]:
    """msgid -> msgstr, ohne die ungenau markierten Eintraege.

    Ohne sie, weil `msgfmt` sie NICHT in die .mo nimmt: ein fuzzy
    markierter Eintrag steht im .po und fehlt auf der Maschine. Genau
    diese Falle hat dieses Projekt an einem Tag viermal gestellt.
    """
    text = KATALOG.read_text(encoding="utf-8")
    eintraege = {}
    for block in text.split("\n\n"):
        if re.search(r"^#, .*fuzzy", block, re.M):
            continue
        mid = re.search(r'^msgid "(.*)"$', block, re.M)
        if not mid or not mid.group(1):
            continue
        if "msgid_plural" in block:
            wert = re.search(r'^msgstr\[0\] "(.*)"$', block, re.M)
            zweit = re.search(r'^msgid_plural "(.*)"$', block, re.M)
            wert2 = re.search(r'^msgstr\[1\] "(.*)"$', block, re.M)
            if zweit and wert2:
                eintraege[zweit.group(1)] = wert2.group(1)
        else:
            wert = re.search(r'^msgstr "(.*)"$', block, re.M)
        if wert:
            eintraege[mid.group(1)] = wert.group(1)
    return eintraege


def _wie_im_katalog(text: str) -> str:
    return (text.replace("\\", "\\\\").replace('"', '\\"')
                .replace("\n", "\\n").replace("\t", "\\t"))


def test_der_katalog_kennt_jede_zeichenkette_aus_dem_python_teil():
    katalog = _katalog()
    ohne_eintrag, ohne_uebersetzung = [], []
    for pfad in _dateien():
        for zeile, text in _msgids(pfad):
            if text is None:
                continue
            schluessel = _wie_im_katalog(text)
            ort = f"{pfad.relative_to(WURZEL)}:{zeile}"
            if schluessel not in katalog:
                ohne_eintrag.append(f"{ort}  {text[:70]!r}")
            elif not katalog[schluessel]:
                ohne_uebersetzung.append(f"{ort}  {text[:70]!r}")

    assert not ohne_eintrag, (
        f"{len(ohne_eintrag)} Zeichenketten rufen _() und stehen in "
        f"keinem Katalogeintrag - auf einer deutschen Maschine kommt "
        f"dafuer der englische msgid heraus:\n  "
        + "\n  ".join(ohne_eintrag[:20]))
    assert not ohne_uebersetzung, (
        f"{len(ohne_uebersetzung)} Katalogeintraege sind leer - dasselbe "
        f"Ergebnis, nur eine Zeile weiter:\n  "
        + "\n  ".join(ohne_uebersetzung[:20]))


def test_keine_eingesetzte_zeichenkette_geht_an_gettext():
    """Ein f-String in `_()` ist ein msgid, den es nur zur Laufzeit gibt.

    xgettext sieht ihn nicht, der Katalog kann ihn nicht kennen, und das
    Ergebnis ist wieder englischer Text auf einer deutschen Maschine -
    dieselbe Falle wie beim Template-Literal in den AGS-Vorlagen, aus
    der `format()` in utils/i18n.ts entstanden ist. In Python heisst der
    Ausweg `_("... {name} ...").format(name=...)`.
    """
    gefunden = []
    for pfad in _dateien():
        for zeile, text in _msgids(pfad):
            if text is None:
                gefunden.append(f"{pfad.relative_to(WURZEL)}:{zeile}")
    assert not gefunden, (
        "diese Aufrufe geben gettext einen f-String:\n  "
        + "\n  ".join(gefunden))


def test_die_zusicherung_wuerde_die_luecke_vom_02_09_2026_sehen(tmp_path):
    """Ein Test, der nichts misst, ist gruen. Also hier der Gegenbeweis.

    Gebaut wird die Lage von damals - ein Aufruf mit einem msgid, den
    der Katalog nicht hat - und die Pruefung muss ihn finden.
    """
    quelle = tmp_path / "beispiel.py"
    quelle.write_text(
        "import desktop_i18n\n"
        "from desktop_i18n import _\n"
        "text = _(\"Desktop size\")\n"
        "fehlt = _(\"Eine Zeichenkette, die in keinem Katalog steht\")\n",
        encoding="utf-8")

    katalog = _katalog()
    fehlend = [text for _zeile, text in _msgids(quelle)
               if text is not None and _wie_im_katalog(text) not in katalog]
    assert fehlend == ["Eine Zeichenkette, die in keinem Katalog steht"], (
        "die Pruefung findet den fehlenden Eintrag nicht mehr - dann "
        "sagt der Test oben nichts mehr aus")


@pytest.mark.parametrize("name", ["_", "N_", "ngettext"])
def test_jeder_gelesene_aufruf_kommt_wirklich_vor(name):
    """Sonst prueft die Liste oben Namen, die niemand benutzt."""
    treffer = [pfad.relative_to(WURZEL) for pfad in _dateien()
               if re.search(rf"(?<![\w.]){re.escape(name)}\(", 
                            pfad.read_text(encoding="utf-8"))]
    assert treffer, (
        f"kein einziger Aufruf von {name}() im Python-Teil - dann ist "
        f"der Eintrag in AUFRUFE veraltet")
