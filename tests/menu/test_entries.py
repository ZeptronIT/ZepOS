# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Zeilen, der Filter, die Reihenfolge und das Zaehlwerk.

Ohne Anzeige, weil menu/zepos_menu/entries.py ohne GTK auskommt - und es
kommt ohne GTK aus, damit genau diese Fragen hier beantwortet werden
koennen statt in einem Kind auf broadway.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# menu/ in den Suchpfad, bevor zepos_menu importiert wird.
#
# `zepos_menu` liegt nicht in site-packages und soll da auch nicht liegen -
# packaging/zepos-menu/PKGBUILD begruendet das -, also findet ein Import es
# nicht von selbst. /usr/bin/zepos-menu legt sich das Verzeichnis zur
# Laufzeit hin; hier steht dieselbe Zeile.
#
# NICHT IN EINER conftest.py, UND DAS IST TEUER GELERNT
#     Genau dafuer stand hier zuerst tests/menu/conftest.py. pytest legt
#     das Verzeichnis JEDER conftest.py vorne in sys.path, und die Suite
#     hat schon eine: tests/conftest.py, die vier Testdateien mit
#     `import conftest` beim Namen holen. Mit einer zweiten gewann meine.
#     Gemessen am 11.08.2026: 226 fehlgeschlagene Tests, darunter 77 in
#     tests/test_isolation_guard.py, alle mit
#     "module 'conftest' has no attribute '_is_protected'" - der
#     Isolationswaechter war fuer die halbe Suite verschwunden. Jede Datei
#     fuer sich lief gruen.
sys.path.insert(0, str(ROOT / "menu"))

from zepos_menu import entries as model      # noqa: E402


def read(text: str) -> list[str]:
    return [entry.value for entry in model.read_dmenu(io.StringIO(text))]


# --------------------------------------------------------------------
# Was von stdin hereinkommt
# --------------------------------------------------------------------

def test_every_line_becomes_one_entry():
    assert read("eins\nzwei\ndrei\n") == ["eins", "zwei", "drei"]


def test_a_line_without_a_final_newline_still_counts():
    """`printf '%s' "$letzte"` ohne Umbruch am Ende ist eine Zeile, und
    printer-manager erzeugt seine Liste mit printf."""
    assert read("eins\nzwei") == ["eins", "zwei"]


def test_the_tab_and_the_identifier_cliphist_needs_are_kept():
    """`cliphist list` stellt jeder Zeile eine Kennung und einen
    Tabulator voran, und cliphist-menu.sh reicht die gewaehlte Zeile
    unveraendert an `cliphist decode` weiter. Ein Ersatz, der die Zeile
    beschneidet, gibt dort eine Kennung aus, die es nicht gibt."""
    assert read("42\tHallo Welt\n") == ["42\tHallo Welt"]


def test_an_empty_line_is_not_an_entry():
    """Jeder der fuenf Aufrufer prueft die Ausgabe mit `[ -n "$x" ]`,
    also bedeutet die leere Zeichenkette dort bereits Abbruch. Eine
    waehlbare leere Zeile waere ein Klick, der wie Escape wirkt."""
    assert read("eins\n\n   \nzwei\n") == ["eins", "zwei"]


def test_the_same_line_twice_appears_once():
    """Der Zwischenablageverlauf ist voll davon: wer denselben Text
    zweimal kopiert, hat ihn zweimal darin. Zwei identische Zeilen sind
    zwei Zeilen, zwischen denen niemand waehlen kann."""
    assert read("Hallo\nWelt\nHallo\n") == ["Hallo", "Welt"]


def test_leading_whitespace_is_part_of_the_line():
    """network-manager-gui formatiert seine Liste mit printf und
    Spaltenbreiten - das fuehrende Leerzeichen IST die Spalte, in der bei
    einem verbundenen Netz das Haekchen steht, und handle_selection()
    schneidet spaeter genau sechs Zeichen ab."""
    assert read("  WLAN Gast  \n") == ["  WLAN Gast  "]


# --------------------------------------------------------------------
# Der Filter
# --------------------------------------------------------------------

def test_a_substring_anywhere_matches():
    assert model.matches("Systemwaechter", "waech", insensitive=False)
    assert not model.matches("Systemwaechter", "waechz", insensitive=False)


def test_an_empty_query_matches_everything():
    assert model.matches("irgendwas", "", insensitive=False)


def test_case_matters_unless_it_is_switched_off():
    assert not model.matches("WLAN Gast", "wlan", insensitive=False)
    assert model.matches("WLAN Gast", "wlan", insensitive=True)


def test_case_folding_reaches_the_german_sharp_s():
    """casefold() und nicht lower(): "STRASSE".lower() ist "strasse" und
    "Straße".lower() ist "straße" - die beiden faenden einander nicht.
    Deutsche Netznamen und Fenstertitel sind hier der Normalfall."""
    assert model.matches("Straße 4", "STRASSE", insensitive=True)


# --------------------------------------------------------------------
# Die Reihenfolge
# --------------------------------------------------------------------

def entries(*labels) -> list[model.Entry]:
    return [model.Entry(label=label, value=label) for label in labels]


def labels(found) -> list[str]:
    return [entry.label for entry in found]


def test_default_leaves_the_input_order_alone():
    given = entries("Etage2", "Buero", "Labor")
    assert labels(model.order(given, "default", {})) == \
        ["Etage2", "Buero", "Labor"]


def test_alphabetical_sorts_without_regard_to_case():
    given = entries("etage2", "Buero", "labor")
    assert labels(model.order(given, "alphabetical", {})) == \
        ["Buero", "etage2", "labor"]


def test_the_count_lifts_what_was_chosen_before_to_the_top():
    given = entries("Etage2", "Buero", "Labor")
    order = model.order(given, "default", {"Labor": 3, "Buero": 1})
    assert labels(order) == ["Labor", "Buero", "Etage2"]


def test_entries_with_the_same_count_keep_the_base_order():
    """Beide Sortierungen sind stabil. Ohne das waere die Reihenfolge
    zweier gleich oft gewaehlter Eintraege von Lauf zu Lauf anders, und
    der Pfeil nach unten zeigte jedes Mal auf etwas anderes."""
    given = entries("Etage2", "Buero", "Labor", "Keller")
    order = model.order(given, "default", {"Labor": 2, "Etage2": 2})
    assert labels(order) == ["Etage2", "Labor", "Buero", "Keller"]


def test_an_empty_count_changes_nothing_at_all():
    given = entries("Etage2", "Buero")
    assert labels(model.order(given, "default", {})) == ["Etage2", "Buero"]


# --------------------------------------------------------------------
# Das Zaehlwerk
# --------------------------------------------------------------------

def test_a_file_that_is_not_there_reads_as_no_count(tmp_path):
    assert model.read_usage(tmp_path / "fehlt") == {}


def test_a_count_survives_being_written_and_read(tmp_path):
    path = tmp_path / "zaehlwerk"
    model.write_usage(path, {}, "Labor")
    model.write_usage(path, model.read_usage(path), "Labor")
    model.write_usage(path, model.read_usage(path), "Buero")

    assert model.read_usage(path) == {"Labor": 2, "Buero": 1}


def test_a_value_with_a_space_in_it_comes_back_whole(tmp_path):
    """Getrennt wird an genau EINEM Leerzeichen. Anwendungsnamen und
    Zwischenablagezeilen haben mehrere."""
    path = tmp_path / "zaehlwerk"
    model.write_usage(path, {}, "Firefox Web Browser")

    assert model.read_usage(path) == {"Firefox Web Browser": 1}


def test_a_damaged_line_costs_that_line_and_nothing_else(tmp_path):
    """Es ist ein Zaehlwerk. Was sich nicht lesen laesst, zaehlt eben
    nicht - eine Ausnahme hier waere ein Starter, der wegen einer
    kaputten Zwischendatei nicht mehr aufgeht."""
    path = tmp_path / "zaehlwerk"
    # Drei Sorten Schaden, und die dritte ist die, auf die es ankommt:
    # "kaputt" allein hat gar keinen Wert hinter sich und faellt schon
    # vorher heraus, "drei Etage2" hat einen - und nur dort entscheidet
    # sich, ob eine unlesbare Zahl die ganze Datei mitreisst. Gemessen am
    # 11.08.2026: ohne diese Zeile blieb die Suite gruen, als das
    # try/except entfernt wurde.
    path.write_text("3 Labor\nkaputt\ndrei Etage2\n1 Buero\n",
                    encoding="utf-8")

    assert model.read_usage(path) == {"Labor": 3, "Buero": 1}


def test_the_count_does_not_grow_without_end(tmp_path):
    """Der Zwischenablageverlauf liefert bei jedem Aufruf andere Zeilen,
    also wird jede genau einmal gezaehlt und nie wieder gefunden. Ohne
    Deckel waechst die Datei mit jeder Auswahl um eine Zeile und wird nie
    wieder kleiner."""
    path = tmp_path / "zaehlwerk"
    usage = {f"zeile-{number}": 1 for number in range(model.USAGE_LIMIT + 50)}

    model.write_usage(path, usage, "haeufig")

    written = model.read_usage(path)
    assert len(written) == model.USAGE_LIMIT
    assert written["haeufig"] == 1, (
        "die gerade getroffene Auswahl ist beim Kuerzen herausgefallen")


def test_the_most_used_survive_the_pruning(tmp_path):
    path = tmp_path / "zaehlwerk"
    usage = {f"selten-{number}": 1 for number in range(model.USAGE_LIMIT)}
    usage["oft"] = 99

    model.write_usage(path, usage, "neu")

    written = model.read_usage(path)
    assert written["oft"] == 99
    assert len(written) == model.USAGE_LIMIT


def test_the_count_does_not_touch_a_directory_that_is_already_there(
        tmp_path, monkeypatch):
    """Kein mkdir auf einem fremden Pfad.

    `mkdir(parents=True, exist_ok=True)` ueber ein vorhandenes
    Verzeichnis ist zwar kein Fehler, aber ein Schreibversuch: bei
    `--cache-file /dev/null` waere es ein mkdir auf /dev, bei jedem
    einzelnen Aufruf der fuenf Skripte.

    Gemessen statt behauptet, weil der Unterschied sonst unsichtbar ist -
    beide Fassungen schreiben dieselbe Datei. Also wird gezaehlt, ob
    Path.mkdir ueberhaupt gerufen wurde.
    """
    calls: list = []
    real = type(tmp_path).mkdir
    monkeypatch.setattr(type(tmp_path), "mkdir",
                        lambda self, *a, **k: (calls.append(self),
                                               real(self, *a, **k))[1])

    model.write_usage(tmp_path / "zaehlwerk", {}, "Labor")
    assert calls == [], f"write_usage hat mkdir gerufen: {calls}"

    tief = tmp_path / "noch" / "nicht" / "da"
    model.write_usage(tief / "zaehlwerk", {}, "Labor")
    # calls[0], nicht die ganze Liste: parents=True steigt ueber
    # Path.mkdir selbst nach oben, der Zaehler sieht also auch die
    # Elternverzeichnisse. Was hier zaehlt, ist der erste Aufruf.
    assert calls and calls[0] == tief, (
        "ein fehlendes Verzeichnis muss dagegen angelegt werden: "
        f"{calls}")
    assert model.read_usage(tief / "zaehlwerk") == {"Labor": 1}


def test_dev_null_reads_as_no_count(tmp_path):
    """Der Sonderfall, der keiner sein darf: alle fuenf Skripte
    uebergeben `--cache-file /dev/null`, und es steht kein einziges `if`
    dafuer im Code - /dev/null liest sich als leere Datei.

    Nur die LESESEITE steht hier. Ein Schreibversuch auf /dev/null
    innerhalb dieses Prozesses waere ein Schreibversuch unter /dev, den
    der Isolationswaechter aus tests/conftest.py zu Recht abweist. Die
    Schreibseite ist in tests/menu/test_menu_headless.py gemessen -
    `test_dev_null_keeps_no_count_at_all`, im Kindprozess, mit dem
    echten Programm und der echten Datei."""
    from pathlib import Path

    assert model.read_usage(Path("/dev/null")) == {}


def test_a_directory_that_cannot_be_written_costs_only_the_count(tmp_path):
    """Ein nicht schreibbares Zaehlwerk ist kein Grund, die getroffene
    Auswahl nicht auszugeben - der Aufrufer wartet auf stdout."""
    locked = tmp_path / "gesperrt"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        model.write_usage(locked / "zaehlwerk", {}, "Labor")
    finally:
        locked.chmod(0o700)
