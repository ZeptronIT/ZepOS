# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Breitenleiter - drei Sprossen statt zwoelf gegriffener Zahlen.

Der Waechter prueft nicht, dass die Zahlen SCHOEN sind, sondern dass
keine von ihnen ein Fenster beschneidet und keine ueber den Deckel
laeuft. Beides ist am 18.08.2026 einzeln ausgemessen worden; die
Messungen stehen im Plan.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import sizes


# Was jedes Fenster am 18.08.2026 tatsaechlich brauchte, aus seinem
# eigenen WIN_WIDTH gelesen. KEINE dieser Zahlen darf durch die Leiter
# kleiner werden - ein Fenster, das seine Zahl nicht mehr bekommt,
# verliert Inhalt hinter der Kante, und das ist der Fehler, den
# ags-vpn.template im Kopf beschreibt.
GEMESSEN = {
    "notifications": 420,
    "battery": 436,
    "style_settings": 474,
    "calendar": 496,
    "disk": 556,
    "wallpaper": 616,
    "vpn_settings": 642,
}


def test_es_gibt_genau_drei_sprossen():
    assert sorted(sizes.MODAL_WIDTHS) == ["L", "M", "S"]


def test_keine_sprosse_beschneidet_ihr_engstes_fenster():
    for name, gemessen in GEMESSEN.items():
        passend = min(w for w in sizes.MODAL_WIDTHS.values() if w >= gemessen)
        assert passend >= gemessen, (
            f"{name} misst {gemessen}, bekaeme aber nur {passend}")


def test_die_groesste_sprosse_bleibt_unter_dem_deckel():
    # Der Deckel greift auf dem schmalsten unterstuetzten Schirm, 1920.
    deckel = int(1920 * sizes.MEASURE_MODAL_SHARE)
    assert max(sizes.MODAL_WIDTHS.values()) <= deckel


def test_die_sprossen_steigen():
    werte = [sizes.MODAL_WIDTHS[k] for k in ("S", "M", "L")]
    assert werte == sorted(set(werte))


def test_eine_unbekannte_sprosse_ist_ein_fehler_und_keine_null():
    # Ein Tippfehler im Fenster darf nicht in einer Breite 0 enden.
    try:
        sizes.MODAL_WIDTH("XL")
    except KeyError:
        return
    raise AssertionError("MODAL_WIDTH schluckt eine unbekannte Sprosse")
