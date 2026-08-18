# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Ratsche auf den Knoepfen.

GEMELDET am 18.08.2026: "ausserdem wirken sie so billig durch die button
wie sie dargestellt sind weisst du was ich meine".

GEMESSEN am selben Tag in src/templates/ags-style.template: zuerst 45
Knopfregeln in 41 verschiedenen Klassen - mit einem Zaehler, der nur
Zeilen ansah, deren allererstes Zeichen ein Punkt war.

BERICHTIGT, noch am selben Tag, in der Pruefung dieses Tests: der
Zaehler hatte drei blinde Flecken, und alle drei kommen im Stylesheet
tatsaechlich vor.

  1. Eingerueckte Selektoren (SCSS-Verschachtelung): ".calendar-action-btn",
     ".sc-edit-btn", ".vpn-list-btn" stehen mit fuehrenden Leerzeichen in
     einem umschliessenden Block und begannen darum nie am Zeilenanfang.
  2. Das zweite (und jedes weitere) Glied einer Komma-Liste: in
     ".bt-power-btn, .bt-tool-btn {" sah der alte Zaehler nur das erste
     Glied, ".bt-tool-btn" fiel durch. Ebenso ".net-refresh-btn" hinter
     ".net-wifi-toggle,".
  3. Die Endung "-button" statt "-btn": ".cc-button" ist ein
     vollstaendig ausgepraegter Knopf (Hintergrund, Rahmen, Polster,
     32px), aber der alte Zaehler suchte nur nach "btn" als Teilstring -
     "button" enthaelt "btn" nicht als zusammenhaengende Buchstabenfolge.
     Die Behauptung weiter unten, "-btn" sei die einzige durchgehaltene
     Benennung, war damit falsch; der Bestand widerlegt sie.

Mit dem reparierten Zaehler (siehe _knopfklassen) neu gemessen, ebenfalls
am 18.08.2026: 51 Knopfregeln in 47 verschiedenen Klassen. Die Namen, die
der alte Zaehler nicht sah: bt-tool-btn, calendar-action-btn, cc-button,
net-refresh-btn, sc-edit-btn, vpn-list-btn - genau die sechs, die aus den
drei blinden Flecken oben folgen. AUSGANGSZAHL war darum 47, nicht 41;
wer die Differenz spaeter als Verschlechterung liest, findet hier den
Grund.

WARUM EINE RATSCHE UND NICHT "GENAU EINE": UI-1 stellt zwoelf Fenster
um, und das geht nicht in einem Zug (siehe Abschnitt 6 der
Spezifikation). Ein Test, der sofort genau eine verlangt, waere von der
ersten bis zur letzten Stufe rot - und ein Test, der monatelang rot ist,
ist ein Test, den jemand abschaltet.

Die Ratsche laesst die Zahl nur SINKEN. Wer eine Klasse hinzufuegt,
faellt sofort auf; wer eine entfernt, muss die Zahl hier senken und
sieht dabei, wie weit es noch ist. Die letzte Stufe von UI-1 setzt sie
auf 1.

DIE EINE AUSNAHME, NOCH AM 18.08.2026 (Ruling 1 des Controllers): task-1u4
hat die gemeinsame Knopfregel selbst angelegt - .zep-btn und seine vier
Rollen .zep-btn-voll/-umrandet/-still/-kritisch, aus ags-kit.template.
Das sind fuenf neue Klassennamen, die alle "btn" im Namen tragen, und sie
mussten VOR jeder Umstellung eines Fensters existieren, damit ueberhaupt
etwas da ist, worauf ein Fenster umgestellt werden kann. Gezaehlt nach
demselben _knopfklassen wie oben ergab das 52 statt 47 - kein Fenster hat
sich einen eigenen Knopf gebaut, das Bauteil-Kit selbst ist neu.
AUSGANGSZAHL und ERLAUBT stehen darum ab hier auf 52, und das ist die
EINZIGE Richtung, in der diese Ratsche je nach oben geht: einmal, fuer
das Fundament, nicht fuer ein einzelnes Fenster.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STIL = ROOT / "src" / "templates" / "ags-style.template"

# Am 18.08.2026 mit dem reparierten Zaehler gemessen, bevor irgendetwas
# umgestellt war. Der urspruengliche Zaehler hatte an dieser Stelle
# faelschlich 41 stehen (siehe Modul-Docstring) - das war kein anderer
# Ausgangszustand, sondern derselbe Zustand, falsch gezaehlt.
#
# NOCH AM 18.08.2026, task-1u4: das Bauteil-Kit selbst (.zep-btn und
# seine vier Rollen) kam dazu, BEVOR ein Fenster umgestellt ist - siehe
# Modul-Docstring, Abschnitt "DIE EINE AUSNAHME". Gemessen mit
# _knopfklassen: 52. AUSGANGSZAHL zieht mit, weil sie sonst eine
# Obergrenze waere, die schon der erste erlaubte Schritt reisst - und
# test_the_ratchet_is_not_secretly_loose faende dann die Ausnahme, die
# der Controller ausdruecklich erlaubt hat, ununterscheidbar von einem
# Missbrauch.
AUSGANGSZAHL = 52

# Die Zahl, die HEUTE gilt. Sie darf nur kleiner werden - mit der einen
# Ausnahme oben, dem Bauteil-Kit selbst -, und wer sie senkt, schreibt
# dazu, welches Fenster er umgestellt hat.
#
#   41  18.08.2026  Ausgangszustand (Zaehler kaputt, siehe Docstring)
#   47  18.08.2026  Zaehler repariert, echter Ausgangswert
#   52  18.08.2026  task-1u4: .zep-btn + vier Rollen, das Bauteil-Kit
#                   selbst (Ruling 1 des Controllers - die eine erlaubte
#                   Ausnahme, siehe Modul-Docstring)
#   50  18.08.2026  task-5: Bluetooth auf die Bauteile. .bt-power-btn
#                   und .bt-tool-btn (eine gemeinsame Regel) sind
#                   gefallen, kein Fenster hat sich einen neuen Knopf
#                   gebaut - GEZAEHLT mit _knopfklassen/_ist_knopfname
#                   aus diesem Modul, nicht abgeschrieben.
ERLAUBT = 50


def _knopfklassen(text: str) -> set[str]:
    """Jede Klasse, deren Name auf einen Knopf hindeutet.

    Ueber den NAMEN und nicht ueber den Inhalt: eine Regel, die zufaellig
    wie ein Knopf aussieht, ist keine; eine, die "btn" enthaelt oder auf
    "-button" endet, ist eine. Beide Formen sind im Bestand belegt - die
    fruehere Behauptung, "-btn" sei die einzige durchgehaltene Benennung,
    stimmte nicht (siehe Modul-Docstring, Punkt 3).

    "-buttons" (Mehrzahl) zaehlt bewusst NICHT: das sind Container ohne
    eigenen Knopf-Stil, reines Layout fuer eine Gruppe von Knoepfen
    (z. B. ".battery-profile-buttons").

    Ein Klassenname zaehlt unabhaengig davon, WIE er im Stylesheet
    auftaucht: am Zeilenanfang, eingerueckt in einem verschachtelten
    Block, oder als zweites/weiteres Glied einer durch Komma getrennten
    Selektorliste. Nur ein direkt vorangehender Buchstabe, eine Ziffer
    oder ein Bindestrich schliesst eine Fundstelle aus - das ist genau
    der Fall bei einem angehaengten Compound-Selektor wie
    ".cc-toggle-btn.active", wo ".active" kein eigener Treffer sein darf.
    """
    return set(re.findall(r"(?<![a-z0-9-])\.([a-z][a-z0-9-]*)", text, re.M))


def _ist_knopfname(name: str) -> bool:
    """Enthaelt "btn" oder endet auf "-button" (Einzahl, nicht "-buttons")."""
    return "btn" in name or name.endswith("-button")


def test_no_window_invents_another_button():
    kandidaten = _knopfklassen(STIL.read_text(encoding="utf-8"))
    gefunden = {name for name in kandidaten if _ist_knopfname(name)}
    assert len(gefunden) <= ERLAUBT, (
        f"{len(gefunden)} Knopf-Klassen, erlaubt sind {ERLAUBT}.\n"
        f"Neu dazugekommen: {sorted(gefunden)[:60]}\n"
        "Ein Fenster hat sich wieder seinen eigenen Knopf gebaut. Nimm "
        "zepButton aus ags-kit.template.")


def test_the_ratchet_is_not_secretly_loose():
    """Die Zahl darf nicht ueber dem Ausgangswert stehen.

    Ohne diese Zusicherung koennte jemand ERLAUBT anheben, statt einen
    Knopf zu entfernen - und der Waechter waere still eine Erlaubnis.
    """
    assert ERLAUBT <= AUSGANGSZAHL, (
        f"ERLAUBT steht auf {ERLAUBT}, der Ausgangswert war "
        f"{AUSGANGSZAHL}. Die Ratsche dreht nur in eine Richtung.")


def test_the_counter_would_notice_a_new_class():
    """Der Selbsttest. Ein Zaehler, der nichts findet, zaehlt auch nichts.

    Deckt genau die drei Formen ab, an denen der Zaehler bis zum
    18.08.2026 vorbeigesehen hat (siehe Modul-Docstring): Einrueckung,
    das zweite Glied einer Komma-Liste, und die Endung "-button". Dazu
    den Gegenfall "-buttons" (Mehrzahl), der NICHT zaehlen darf.
    """
    beispiel = (
        ".a-btn {\n"                # unveraendert: eigene, unverschachtelte Zeile
        "  color: red;\n"
        "}\n"
        ".b {\n"                    # Gegenprobe: kein Knopfname
        "  color: blue;\n"
        "}\n"
        ".wrapper {\n"
        "  .indent-btn {\n"         # 1. Einrueckung
        "    color: green;\n"
        "  }\n"
        "}\n"
        ".first-btn, .second-btn {\n"  # 2. zweites Glied einer Komma-Liste
        "  color: yellow;\n"
        "}\n"
        ".solo-button {\n"          # 3. Endung "-button" statt "-btn"
        "  color: purple;\n"
        "}\n"
        ".group-buttons {\n"        # Gegenfall: Mehrzahl darf NICHT zaehlen
        "  color: grey;\n"
        "}\n"
    )
    kandidaten = _knopfklassen(beispiel)
    gefunden = {name for name in kandidaten if _ist_knopfname(name)}
    assert gefunden == {
        "a-btn", "indent-btn", "first-btn", "second-btn", "solo-button",
    }


def test_the_shared_button_exists_and_has_four_roles():
    text = STIL.read_text(encoding="utf-8")
    assert re.search(r"^\.zep-btn\s*\{", text, re.M), (
        "die gemeinsame Knopfregel fehlt")
    for rolle in ("voll", "umrandet", "still", "kritisch"):
        assert re.search(rf"^\.zep-btn-{rolle}\s*\{{", text, re.M), (
            f"die Rolle {rolle} fehlt")


def test_the_shared_button_uses_the_rungs():
    """Hoehe und Radius als Platzhalter, nicht als Zahl."""
    block = re.search(r"^\.zep-btn\s*\{(.*?)^\}", 
                      STIL.read_text(encoding="utf-8"), re.M | re.S)
    assert block, "die Regel .zep-btn ist verschwunden"
    rumpf = block.group(1)
    assert "{{STYLE_CONTROL_HEIGHT}}" in rumpf, "die Hoehe ist keine Sprosse"
    assert "{{STYLE_RADIUS_CONTROL}}" in rumpf, "der Radius ist keine Sprosse"
