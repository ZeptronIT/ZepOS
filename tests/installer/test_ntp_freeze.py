# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Einfrieren selbst - vorgefuehrt statt beschrieben.

DER BEFUND, 15.08.2026, von echter Hardware
    "Installation Wizard mit dem Terminal freezed wenn ich versuche ohne
    Internet und ohne Passphrase zu installieren."

WAS HIER FEHLTE
    Der Befund war beschrieben, die Ursache benannt und die Reparatur
    eingebaut - aber nichts in dieser Reihe hat den Stillstand je
    ANGEFASST. tests/installer/test_runner.py prueft, dass `--skip-ntp`
    in der Befehlszeile steht; das ist eine Aussage ueber eine
    Zeichenkette, nicht ueber archinstall. Faende archinstall 4.5 einen
    anderen Namen fuer den Schalter, oder zoege es die Schleife vor die
    Stelle, die er abschaltet, bliebe diese Pruefung gruen und der
    Assistent stuende wieder.

    Hier laeuft deshalb archinstalls EIGENER Code, aus der Fassung, die
    dieses Medium ausliefert.

GEMESSEN AM 17.08.2026, archinstall 4.4
    ohne --skip-ntp   von `timeout` nach 20 s abgeschnitten, rc=124
                      (die Schleife hat keine Frist - sie haette bis
                      zum Ausschalten des Rechners gedreht)
    mit  --skip-ntp   zurueck nach 0,001 s

WO DAS IM AUSGELIEFERTEN BAUM STEHT
    archinstall/lib/installer.py, _verify_service_stop(), Zeilen
    189-202: `while True`, verlassen nur, wenn `timedatectl show
    --property=NTPSynchronized --value` `yes` sagt. Ohne Netz sagt es
    das nie.

    Und die Stelle ist die schlimmstmoegliche: archinstall/scripts/
    guided.py ruft erst :249 perform_filesystem_operations() - da ist
    die Platte schon geteilt und formatiert - und danach :251
    perform_installation(), worin :88 sanity_check() steht. Der Nutzer
    haengt also vor einer halb beschriebenen Platte.

WARUM DIESE REIHE UEBERSPRUNGEN WERDEN DARF
    Das archinstall, gegen das hier gemessen wird, liegt in iso/work/ -
    einem Bauverzeichnis, das .gitignore Zeile 33 ausschliesst. In einem
    frischen Klon ist es nicht da. Ein Test, der dann ROT wuerde, waere
    eine Meldung ueber ein fehlendes Bauverzeichnis und nicht ueber
    ZepOS; deshalb wird er uebersprungen - und `test_the_shipped_tree_is
    _searched_where_it_really_lies` haelt fest, dass der Pfad, an dem
    gesucht wird, noch der ist, den iso/build.sh wirklich fuellt.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
KIND = Path(__file__).resolve().parent / "ntp_freeze_child.py"

# Die Frist, nach der ein Lauf als "haengt" gilt. Gemessen (siehe Kopf)
# kehrt der reparierte Fall in 0,001 s zurueck, also ist alles jenseits
# weniger Sekunden nicht "langsam", sondern stehend. Acht Sekunden, damit
# eine Maschine unter Last nicht faelschlich einen Stillstand meldet.
FRIST = 8.0


def _ausgeliefertes_archinstall() -> Path | None:
    """Das site-packages des gebauten Mediums, oder None.

    Ueber ein Muster und nicht ueber einen festen Pfad: die Python-
    Version im Abbild steigt mit Arch (heute 3.14), und ein
    festgeschriebenes `python3.14` waere beim naechsten Sprung ein
    uebersprungener Test, den niemand bemerkt.
    """
    for kandidat in sorted(WURZEL.glob(
            "iso/work/*/x86_64/airootfs/usr/lib/python*/site-packages")):
        if (kandidat / "archinstall" / "lib" / "installer.py").is_file():
            return kandidat
    return None


AUSGELIEFERT = _ausgeliefertes_archinstall()
braucht_medium = pytest.mark.skipif(
    AUSGELIEFERT is None,
    reason="kein gebautes Medium unter iso/work/ - dort liegt das "
           "archinstall, gegen das hier gemessen wird")


def _lauf(fall: str, tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(KIND), fall, str(AUSGELIEFERT), str(tmp_path)],
        capture_output=True, text=True, timeout=FRIST)


# --------------------------------------------------------------------
# Der Stillstand
# --------------------------------------------------------------------

@braucht_medium
@pytest.mark.allow_subprocess
def test_without_the_switch_archinstall_never_comes_back(tmp_path):
    """DIE REPRODUKTION.

    Ohne `--skip-ntp` kehrt archinstalls eigener Code nicht zurueck.
    Nicht "langsam", sondern gar nicht: die Schleife hat keine obere
    Schranke, und die Bedingung, die sie verliesse, kann ohne Netz nicht
    eintreten.

    Der Beweis ist die Frist, die REISST - deshalb ist das erwartete
    Ergebnis eine TimeoutExpired und kein Rueckgabewert. Kehrte das Kind
    zurueck, waere entweder die Schleife weg (dann darf dieser Test
    gehen) oder sie kaeme nicht mehr an dieser Stelle vorbei (dann muss
    er neu gemessen werden) - in beiden Faellen soll ein Mensch
    hinsehen.
    """
    with pytest.raises(subprocess.TimeoutExpired):
        _lauf("ohne-skip", tmp_path)


@braucht_medium
@pytest.mark.allow_subprocess
def test_with_the_switch_it_returns_at_once(tmp_path):
    """Die andere Haelfte, ohne die die erste nichts beweist.

    Ohne sie koennte das Kind aus irgendeinem Grund haengen - einem
    Import, der auf etwas wartet, einem Pfad, den es nicht gibt - und
    der Test oben waere gruen, ohne je eine Schleife gesehen zu haben.
    Derselbe Code, dieselbe Antwort `no` auf die Uhr, nur der Schalter
    ist gesetzt: kehrt er dann zurueck, war der Schalter der
    Unterschied.
    """
    ergebnis = _lauf("mit-skip", tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "ZURUECKGEKEHRT" in ergebnis.stdout, ergebnis.stdout


@braucht_medium
@pytest.mark.allow_subprocess
def test_the_child_runs_the_shipped_archinstall_and_not_some_other(tmp_path):
    """Sonst misst die Reihe eine Fassung, die niemand ausliefert.

    Auf dieser Maschine ist archinstall NICHT als Paket installiert
    (gemessen am 17.08.2026: `pacman -Q archinstall` sagt "Paket wurde
    nicht gefunden"), das Kind kann es also nur aus dem Bauverzeichnis
    haben. Das hier haelt fest, dass es das auch wirklich von dort
    nimmt.
    """
    ergebnis = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]);"
         "import archinstall.lib.installer as m; print(m.__file__)",
         str(AUSGELIEFERT)],
        capture_output=True, text=True, timeout=FRIST, cwd=tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert str(WURZEL / "iso" / "work") in ergebnis.stdout, ergebnis.stdout


# --------------------------------------------------------------------
# Die Schleife im ausgelieferten Baum
# --------------------------------------------------------------------

@braucht_medium
def test_the_loop_is_still_where_the_comments_say_it_is():
    """Drei Dateien nennen `lib/installer.py:189-202` mit Zeilennummer -
    installer/core/runner.py, installer/core/preflight.py und
    tests/installer/test_runner.py. Zeilennummern in Kommentaren
    veralten lautlos; diese Pruefung sagt Bescheid, sobald archinstall
    die Stelle verschiebt, damit die drei Verweise nachgezogen werden
    statt in die Irre zu fuehren."""
    quelle = (AUSGELIEFERT / "archinstall" / "lib" / "installer.py")
    zeilen = quelle.read_text(encoding="utf-8").splitlines()

    # 189-202 in menschlicher Zaehlung, also Index 188 bis 201.
    ausschnitt = "\n".join(zeilen[188:202])
    assert "while True:" in ausschnitt, ausschnitt
    assert "NTPSynchronized" in ausschnitt, ausschnitt
    assert "skip_ntp" in "\n".join(zeilen[185:190]), (
        "die Schleife haengt nicht mehr an `skip_ntp` - dann schaltet "
        "`--skip-ntp` sie auch nicht mehr ab")


@braucht_medium
def test_the_switch_is_still_spelled_the_way_runner_py_spells_it():
    """`--skip-ntp` ist eine Zeichenkette in einer Befehlszeile. Ein
    umbenannter Schalter faellt sonst erst auf fremder Hardware auf, und
    zwar als Stillstand - archinstall lehnt unbekannte Argumente zwar
    ab, aber das steht dann in einem Protokoll, das der Nutzer vor
    seinem stehenden Bild nicht sieht."""
    args = (AUSGELIEFERT / "archinstall" / "lib" / "args.py").read_text(
        encoding="utf-8")
    assert "'--skip-ntp'" in args or '"--skip-ntp"' in args, (
        "archinstall kennt `--skip-ntp` nicht mehr unter diesem Namen")

    runner = (WURZEL / "installer" / "core" / "runner.py").read_text(
        encoding="utf-8")
    assert '"--skip-ntp"' in runner, (
        "runner.py setzt den Schalter nicht mehr - genau der Zustand, "
        "in dem der Assistent ohne Netz wieder einfriert")


def test_the_shipped_tree_is_searched_where_it_really_lies():
    """Die Suche oben darf nicht ins Leere greifen.

    Findet _ausgeliefertes_archinstall() nichts, weil sich der
    Bauort geaendert hat, werden ALLE Pruefungen dieser Datei still
    uebersprungen - und der Befund vom 15.08.2026 haette wieder
    niemanden, der ihn misst. Diese eine Pruefung laeuft deshalb IMMER
    und haelt fest, wohin iso/build.sh wirklich baut.
    """
    build = (WURZEL / "iso" / "build.sh").read_text(encoding="utf-8")

    # Die zwei Stuecke, aus denen das Muster oben besteht, so wie
    # iso/build.sh sie am 17.08.2026 wirklich schreibt:
    #     work=/build/work/mkarchiso-$PROFILE      (Zeile 421)
    #     root=$work/x86_64/airootfs               (Zeile 426)
    # Aendert sich eines davon, greift der glob ins Leere und die
    # Messungen dieser Datei verschwinden lautlos.
    assert "work/mkarchiso-" in build, (
        "iso/build.sh baut nicht mehr nach work/mkarchiso-<profil> - "
        "dann sucht _ausgeliefertes_archinstall() am falschen Ort")
    assert "x86_64/airootfs" in build, (
        "iso/build.sh legt das Wurzeldateisystem nicht mehr unter "
        "x86_64/airootfs ab - derselbe Schaden")
