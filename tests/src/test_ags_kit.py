# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Bauteil-Kit: was es exportiert und was es NICHT tut."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "src" / "templates" / "ags-kit.template"

ERWARTETE_BAUTEILE = (
    "zepButton", "zepRow", "zepToggle", "zepSectionLabel", "zepDivider",
    # NACHGETRAGEN am 20.08.2026 (Aufgabe 36): die Wartezeile. Sie steht
    # hier und nicht in den beiden Seiten, die sie zuerst gebraucht
    # haben, weil "laedt" eine Aussage ist, die JEDE Seite treffen kann -
    # und weil es davor genau eine Fassung im ganzen Baum gab, von Hand
    # gebaut in ags-vpn.template, ohne CSS-Klasse.
    "zepBusy",
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


def test_zep_row_titles_are_capped_not_only_ellipsized():
    """NACHGETRAGEN am 18.08.2026, task-6.

    `ellipsize` senkt bei GTK nur die MINDESTBREITE eines Labels, nicht
    seine natuerliche - GEMESSEN am 17.08.2026: genau die fehlende
    Deckelung hat das Netzfenster auf 660 Punkte und (vor der Umstellung
    auf zepRow) ags-bluetooth.template auf 460 statt 312 Punkte
    aufgeblasen (Kopf beider Dateien). Elf der zwoelf Fenster tragen
    unbegrenzte Fremdtexte (VPN-Profilnamen, WLAN-Namen, Themennamen) -
    ohne `max_width_chars` wiederholt das Kit diesen Fehler elfmal,
    statt ihn zu verhindern. Titel UND Nebenzeile bekommen darum
    {{STYLE_MEASURE_LINE}} als Vorgabe, nicht nur eine von beiden.
    """
    text = KIT.read_text(encoding="utf-8")
    assert "titel.set_max_width_chars({{STYLE_MEASURE_LINE}})" in text, (
        "der Titel deckelt seine natuerliche Breite nicht mehr - "
        "ellipsize allein reicht nicht (siehe Funktionskopf von zepRow)")
    assert "unter.set_max_width_chars({{STYLE_MEASURE_LINE}})" in text, (
        "die Nebenzeile deckelt ihre natuerliche Breite nicht mehr")


def test_zep_row_can_opt_out_of_the_cap():
    """Ein Fenster, das ausnahmsweise den vollen Text braucht, muss
    abschalten koennen - Vorgabe bleibt KUERZEN, der Deckel greift nur,
    solange `opts.vollerText` nicht gesetzt ist.
    """
    text = KIT.read_text(encoding="utf-8")
    assert "vollerText?: boolean" in text, (
        "zepRow bietet kein opts-Feld, um die Kuerzung abzuschalten")
    # Die Abschaltung muss auch WIRKEN, nicht nur im Namen bestehen:
    # beide Deckel stehen hinter derselben Bedingung.
    assert ("if (!opts.vollerText) "
            "titel.set_max_width_chars({{STYLE_MEASURE_LINE}})") in text, (
        "die Abschaltung wirkt nicht auf den Titel")
    assert ("if (!opts.vollerText) "
            "unter.set_max_width_chars({{STYLE_MEASURE_LINE}})") in text, (
        "die Abschaltung wirkt nicht auf die Nebenzeile")
