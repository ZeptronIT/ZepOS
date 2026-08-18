# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Ratsche auf den Knoepfen.

GEMELDET am 18.08.2026: "ausserdem wirken sie so billig durch die button
wie sie dargestellt sind weisst du was ich meine".

GEMESSEN am selben Tag in src/templates/ags-style.template: 45
Knopfregeln in 41 verschiedenen Klassen, und keine einzige gemeinsame.
Jedes Fenster hatte sich seine Knoepfe selbst erfunden.

WARUM EINE RATSCHE UND NICHT "GENAU EINE": UI-1 stellt zwoelf Fenster
um, und das geht nicht in einem Zug (siehe Abschnitt 6 der
Spezifikation). Ein Test, der sofort genau eine verlangt, waere von der
ersten bis zur letzten Stufe rot - und ein Test, der monatelang rot ist,
ist ein Test, den jemand abschaltet.

Die Ratsche laesst die Zahl nur SINKEN. Wer eine Klasse hinzufuegt,
faellt sofort auf; wer eine entfernt, muss die Zahl hier senken und
sieht dabei, wie weit es noch ist. Die letzte Stufe von UI-1 setzt sie
auf 1.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STIL = ROOT / "src" / "templates" / "ags-style.template"

# Am 18.08.2026 gezaehlt, bevor irgendetwas umgestellt war.
AUSGANGSZAHL = 41

# Die Zahl, die HEUTE gilt. Sie darf nur kleiner werden, und wer sie
# senkt, schreibt dazu, welches Fenster er umgestellt hat.
#
#   41  18.08.2026  Ausgangszustand
ERLAUBT = 41


def _knopfklassen(text: str) -> set[str]:
    """Jede Klasse, deren Name auf einen Knopf hindeutet.

    Ueber den NAMEN und nicht ueber den Inhalt: eine Regel, die zufaellig
    wie ein Knopf aussieht, ist keine; eine, die -btn heisst, ist eine -
    und genau die Benennung ist es, die dieses Projekt durchgehalten hat.
    """
    return set(re.findall(r"^\.([a-z0-9-]*btn[a-z0-9-]*)", text, re.M))


def test_no_window_invents_another_button():
    gefunden = _knopfklassen(STIL.read_text(encoding="utf-8"))
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
    """Der Selbsttest. Ein Zaehler, der nichts findet, zaehlt auch nichts."""
    beispiel = ".a-btn {\n  color: red;\n}\n.b {\n  color: blue;\n}\n"
    assert _knopfklassen(beispiel) == {"a-btn"}
