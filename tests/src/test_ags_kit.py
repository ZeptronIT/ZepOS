# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Bauteil-Kit: was es exportiert und was es NICHT tut."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "src" / "templates" / "ags-kit.template"

ERWARTETE_BAUTEILE = (
    "zepButton", "zepRow", "zepToggle", "zepSectionLabel", "zepDivider",
)


def test_the_kit_exports_every_part():
    text = KIT.read_text(encoding="utf-8")
    fehlend = [n for n in ERWARTETE_BAUTEILE
               if not re.search(rf"^export function {n}\b", text, re.M)]
    assert fehlend == [], f"das Kit exportiert nicht: {fehlend}"


def test_the_kit_carries_no_bare_numbers():
    """Jedes Mass als Platzhalter.

    Ein Bauteil mit einer festen 32 folgt dem Groessenregler nicht - und
    es waere genau die Sorte Zahl, aus der die 41 Knopf-Klassen
    entstanden sind.
    """
    text = KIT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("//"))
    nackt = re.findall(r"(?:padding|margin|height|width|font-size|"
                       r"border-radius)\s*[:=]\s*[\"']?\d+", rumpf)
    assert nackt == [], f"nackte Masse im Kit: {nackt}"


def test_the_kit_defines_no_colour_of_its_own():
    """UI-2 ist vertagt - das Kit fuehrt keine neue Farbe ein."""
    text = KIT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("//"))
    assert not re.search(r"#[0-9a-fA-F]{6}\b", rumpf), (
        "eine Hexfarbe im Kit - Farben kommen aus brand.py")
