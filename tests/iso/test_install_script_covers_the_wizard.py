# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Messstand muss jede Seite des Assistenten kennen.

WAS AM 11.08.2026 PASSIERT IST
    Die Partitionierung kam in PAGE_ORDER zwischen "datentraeger" und
    "benutzer". iso/test-boot.py's RELEASE_INSTALL_SCRIPT wusste nichts
    davon: es ist eine feste Folge von Tastendruecken, und die zaehlt
    Seiten, ohne sie zu lesen.

    Der Lauf danach drueckte auf der Datentraegerseite "Weiter", landete
    auf der Partitionierung und tippte Rechnernamen und Passwoerter in
    deren GROESSENFELDER. Danach stand er auf "Benutzer" mit leeren
    Feldern und kam nicht weiter, weil ohne gueltigen Rechnernamen kein
    "Weiter" da ist.

    Gemessen: 0,0 GiB auf die Zielplatte geschrieben. Das Bild, das
    "installation-beendet" heisst, zeigte "Schritt 4 von 7". Und der
    Lauf endete mit `qemu exited rc=0` - also mit dem Rueckgabewert, den
    ein gelungener Lauf auch hat.

    DAS ist der Grund fuer diese Datei. Ein Assistent, der eine Seite
    dazubekommt, ist eine gewoehnliche Aenderung; ein Messstand, der sie
    stillschweigend ueberspringt und trotzdem gruen meldet, ist eine
    Messung, auf die man sich nicht mehr verlassen kann. Der Fehler war
    nicht die neue Seite - der Fehler war, dass nichts ihn bemerkte.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from installer.gui.pages import PAGE_ORDER

ISO = Path(__file__).resolve().parents[2] / "iso"

# Die Seitennamen von PAGE_ORDER und die Bildmarken im Skript sind nicht
# dieselben Woerter - "zeit" heisst dort "zeitzone", "zepos" heisst
# "zepos-optionen". Diese Zuordnung steht ausgeschrieben da, statt ueber
# Teilzeichenketten geraten zu werden: eine Seite "zeit" wuerde sonst von
# jeder Marke erfuellt, in der die vier Buchstaben vorkommen.
SHOT_FOR_PAGE = {
    "sprache": "sprache",
    "datentraeger": "datentraeger",
    "partitionierung": "partitionierung",
    "verschluesselung": "verschluesselung",
    "benutzer": "benutzer-leer",
    "zeit": "zeitzone",
    "zepos": "zepos-optionen",
    "zusammenfassung": "zusammenfassung",
}

# Die eine Seite, die dieser Lauf nicht sieht, und der Grund dafuer.
# Ausgeschrieben und nicht weggelassen: eine Seite, die niemand misst,
# soll hier stehen muessen, damit das Weglassen eine Entscheidung ist
# und kein Versehen.
SKIPPED = {
    "netzwerk": "PageState.should_skip() ueberspringt sie, wenn die "
                "Suche nichts gefunden hat, und ein QEMU-Gast hat keinen "
                "Funkadapter.",
}


# Die Skripte, fuer die das alles gilt. Seit dem 17.08.2026 sind es
# zwei: RELEASE_INSTALL_OHNE_NETZ_SCRIPT faehrt denselben Assistenten
# auf einer Maschine ohne Netzwerkkarte und mit abgewaehlter
# Verschluesselung. Es ist ein zweites festes Tastenprotokoll durch
# dieselben Seiten - also genau die Sorte Datei, die der Fehler vom
# 11.08.2026 unbemerkt kaputtmacht, und sie muss unter derselben Aufsicht
# stehen wie die erste. Eine Liste und keine zweite Kopie dieser Datei,
# damit ein drittes Skript nichts weiter kostet als einen Eintrag hier.
SCRIPTS = ("RELEASE_INSTALL_SCRIPT", "RELEASE_INSTALL_OHNE_NETZ_SCRIPT")


def _script(name: str = "RELEASE_INSTALL_SCRIPT") -> tuple[str, ...]:
    script = getattr(_module(), name, None)
    assert script, f"iso/test-boot.py hat kein {name} (mehr)"
    return script


def _shots(script: tuple[str, ...]) -> list[str]:
    return [step[len("shot:"):] for step in script if step.startswith("shot:")]


# Die Seiten, die der Lauf nicht nur ANSEHEN, sondern AUSFUELLEN muss,
# und das Wort, an dem man erkennt, dass er es getan hat.
#
# WARUM DAS EINE ZWEITE PRUEFUNG BRAUCHT
#     Ein Bild beweist, dass die Seite gezeigt wurde. Es beweist nicht,
#     dass jemand geantwortet hat. Eine Seite, die UNGUELTIG ankommt -
#     die Benutzerseite und, seit dem 12.08.2026, die
#     Verschluesselungsseite - haelt den Lauf auf, bis ihre Felder
#     gefuellt sind; ein Skript, das sie fotografiert und dann
#     weiterdrueckt, kommt gar nicht weiter.
#
#     Der Fehler, den das hier faengt, ist der bequeme: jemand fuegt fuer
#     eine neue Seite eine Zeile "shot:..." ein, damit die Pruefung oben
#     wieder gruen wird, und vergisst die Tastendruecke. Dann ist die
#     Deckung nachgewiesen und der Lauf trotzdem kaputt.
#     Der Name ist der der Konstanten in iso/test-boot.py; der Wert wird
#     von dort gelesen und nicht abgeschrieben. Im Skript steht eine
#     f-Zeichenkette, also liegt zur Laufzeit der WERT im Tupel - eine
#     Suche nach dem Namen faende nichts.
TYPED_ON_PAGE = {
    "benutzer": "RELEASE_HOSTNAME",
    "verschluesselung": "RELEASE_DISK_PASSPHRASE",
}


def _module():
    spec = importlib.util.spec_from_file_location(
        "test_boot_module", ISO / "test-boot.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_boot_module"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", SCRIPTS)
def test_every_page_of_the_wizard_is_visited(name):
    """Die Zusicherung selbst: keine Seite ohne Schritt."""
    shots = _shots(_script(name))

    for page in PAGE_ORDER:
        if page in SKIPPED:
            continue
        marker = SHOT_FOR_PAGE.get(page)
        assert marker is not None, (
            f"'{page}' steht in PAGE_ORDER, aber weder in SHOT_FOR_PAGE "
            f"noch in SKIPPED. Der Messstand wuerde sie ueberspringen und "
            f"trotzdem gruen melden - genau der Fehler vom 11.08.2026.")
        assert any(marker in shot for shot in shots), (
            f"Der Assistent zeigt '{page}', der Lauf fotografiert sie "
            f"nicht. Wenn eine Seite neu ist, braucht "
            f"RELEASE_INSTALL_SCRIPT einen Schritt dafuer.")


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_pages_are_visited_in_the_order_the_wizard_shows_them(name):
    """Reihenfolge, nicht nur Vorhandensein.

    Eine Seite, die zwar fotografiert wird, aber an der falschen Stelle,
    heisst: die Tastendruecke davor landen woanders. Das war der
    eigentliche Schaden - nicht ein fehlendes Bild, sondern Text in den
    Feldern der falschen Seite.
    """
    shots = _shots(_script(name))
    wanted = [SHOT_FOR_PAGE[p] for p in PAGE_ORDER if p not in SKIPPED]

    positions = []
    for marker in wanted:
        matches = [i for i, shot in enumerate(shots) if marker in shot]
        assert matches, f"'{marker}' kommt im Skript nicht vor"
        positions.append(matches[0])

    assert positions == sorted(positions), (
        f"Die Seiten werden in einer anderen Reihenfolge fotografiert, "
        f"als der Assistent sie zeigt: {wanted} gegen {shots}")


def test_every_page_that_blocks_is_actually_answered():
    """Ein Bild ist keine Antwort.

    Fuer jede Seite in TYPED_ON_PAGE muss zwischen ihrem Bild und dem
    Bild der naechsten Seite mindestens ein `text:`-Schritt mit dem
    erwarteten Wert stehen. Beide Seiten kommen UNGUELTIG an - die
    Verschluesselungsseite, weil der Haken steht und die Passphrase
    fehlt -, und ohne Eingabe gibt es dort kein "Weiter".
    """
    module = _module()
    script = module.RELEASE_INSTALL_SCRIPT
    shots = _shots(script)
    visible = [p for p in PAGE_ORDER if p not in SKIPPED]

    for page, constant in TYPED_ON_PAGE.items():
        assert page in visible, (
            f"'{page}' steht in TYPED_ON_PAGE, aber der Lauf sieht sie "
            f"gar nicht - die Zuordnung ist veraltet")
        value = getattr(module, constant, None)
        assert value, f"iso/test-boot.py hat kein {constant} (mehr)"

        marker = SHOT_FOR_PAGE[page]
        start = next(i for i, step in enumerate(script)
                     if step.startswith("shot:") and marker in step)
        following = visible[visible.index(page) + 1:]
        end = len(script)
        for later in following:
            later_marker = SHOT_FOR_PAGE[later]
            found = [i for i, step in enumerate(script)
                     if i > start and step.startswith("shot:")
                     and later_marker in step]
            if found:
                end = found[0]
                break

        assert f"text:{value}" in script[start:end], (
            f"Der Lauf fotografiert '{page}' und tippt dann nichts hinein. "
            f"Die Seite kommt ungueltig an, also gibt es dort kein "
            f"'Weiter' - der Lauf bliebe stehen. Erwartet wurde ein "
            f"Schritt 'text:{value}' zwischen Bild {start} und {end}, "
            f"gefunden: {list(script[start:end])}")


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_shot_names_are_unique(name):
    """Zwei Bilder unter demselben Namen sind ein Bild.

    Die Aufnahmen werden nach ihrer Marke abgelegt, also ueberschreibt
    die zweite die erste - und was ueberschrieben wurde, faellt beim
    Durchsehen nicht auf, weil die Datei ja da ist. Beim Einfuegen einer
    Seite in die Mitte einer durchnummerierten Folge ist das der
    naheliegendste Fehler.
    """
    shots = _shots(_script(name))
    doubled = sorted({shot for shot in shots if shots.count(shot) > 1})
    assert doubled == [], f"doppelt vergebene Bildmarken: {doubled}"


def test_the_run_without_a_network_switches_the_encryption_off():
    """Der Lauf ohne Netz ist der einzige, der den Haken ABWAEHLT - und
    das ist keine Laune, sondern der gemeldete Fall.

    BEFUND VOM 17.08.2026, von echter Hardware: "Installation Wizard mit
    dem Terminal freezed wenn ich versuche ohne Internet und ohne
    Passphrase zu installieren." Jeder andere Lauf dieser Reihe
    verschluesselt, also war der Weg OHNE Passphrase durch dieses Medium
    ungemessen.

    Der Fehler, den diese Pruefung faengt, ist der bequeme: jemand
    kopiert die Zeilen aus RELEASE_INSTALL_SCRIPT herueber, tippt wieder
    eine Passphrase, und der Lauf misst zum zweiten Mal genau das, was
    schon gemessen war - waehrend sein Name etwas anderes verspricht.
    """
    module = _module()
    script = module.RELEASE_INSTALL_OHNE_NETZ_SCRIPT
    passphrase = module.RELEASE_DISK_PASSPHRASE

    assert f"text:{passphrase}" not in script, (
        "der Lauf ohne Netz tippt eine Plattenpassphrase - dann faehrt er "
        "denselben Weg wie der Lauf mit Netz und nicht den gemeldeten")

    # Und die Seite wird trotzdem BEANTWORTET: zwischen ihrem Bild und
    # dem der Benutzerseite muss eine Leertaste stehen, die den Schalter
    # umlegt. Ohne sie bliebe die Seite ungueltig und der Lauf stuende
    # dort - was auf den Bildern zu sehen waere, aber erst nach einer
    # halben Stunde QEMU.
    start = next(i for i, step in enumerate(script)
                 if step.startswith("shot:") and "verschluesselung" in step)
    end = next(i for i, step in enumerate(script)
               if i > start and step.startswith("shot:")
               and "benutzer-leer" in step)
    between = list(script[start:end])
    assert "key:spc" in between, (
        f"zwischen der Verschluesselungsseite und der Benutzerseite wird "
        f"keine Leertaste gedrueckt - der Haken bliebe stehen, die "
        f"Passphrase leer, und die Seite gaebe kein 'Weiter' frei. "
        f"Gefunden: {between}")
    assert between.count("key:tab") == 3, (
        f"die Tabulatoren auf der Verschluesselungsseite sind nicht mehr "
        f"die gemessenen drei (Schalter, Zurueck, Weiter). Mit gesetztem "
        f"Haken sind es sieben Halte, ohne ihn drei - die zwei "
        f"Passphrasenzeilen werden unempfindlich und sind dann keine "
        f"Halte mehr (installer/gui/app.py, _refresh_encryption). "
        f"Gefunden: {between}")


def test_the_run_without_a_network_does_not_wait_an_hour_for_nothing():
    """`watch:` mit einer kleinen Grenze, und der Grund dafuer.

    Der Lauf mit Netz gibt der Installation 5100 Sekunden, weil sie so
    lange dauern darf. Dieser hier installiert nichts - er wartet auf
    einen Satz auf dem Schirm. Was hier laenger als ein paar Minuten
    braucht, IST der gesuchte Fehler, und dann soll der Lauf ihn
    fotografieren statt eine Stunde lang darauf zu warten.
    """
    script = _module().RELEASE_INSTALL_OHNE_NETZ_SCRIPT
    watches = [step for step in script if step.startswith("watch:")]
    assert len(watches) == 1, watches
    limit = int(watches[0].split(":")[2])
    assert limit <= 900, (
        f"der Lauf ohne Netz wartet bis zu {limit}s auf ein Bild, das "
        f"sich nicht mehr aendert - das ist laenger als der Fehler, den "
        f"er sucht, ueberhaupt braucht, um sichtbar zu werden")


def test_no_page_is_silently_absent_from_both_lists():
    """Die Gegenrichtung: eine Marke in SHOT_FOR_PAGE, die es in
    PAGE_ORDER nicht mehr gibt, ist ebenfalls ein Fund. Sonst bleibt die
    Zuordnung stehen, nachdem eine Seite entfernt wurde, und behauptet
    Deckung fuer etwas, das es nicht gibt."""
    known = set(SHOT_FOR_PAGE) | set(SKIPPED)

    assert known == set(PAGE_ORDER), (
        f"nur in der Zuordnung: {sorted(known - set(PAGE_ORDER))}\n"
        f"nur in PAGE_ORDER:   {sorted(set(PAGE_ORDER) - known)}")
