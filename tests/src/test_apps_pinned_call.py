# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Weg, den der Erzeuger wirklich geht - `apps.py filter`.

WARUM ES DIESE DATEI GIBT
    Am 13.08.2026 hat ein Mensch auf echter Hardware gemeldet: nach dem
    Anmelden ein schwarzer Schirm, dann wieder die Anmeldemaske. Endlos.

    Im Sitzungsprotokoll der installierten Maschine stand:

        TypeError: bar_order() missing 1 required positional
                   argument: 'shipped'
        Error: Pinned applications could not be resolved
        Total configs: 90   Successful: 89   Failed: 1
        zepos-generate --all rc=1
        !!! Sitzung nicht gestartet: der Starter wurde nicht erzeugt

    bar_order() hatte am Tag zuvor eine dritte Liste bekommen, und
    apps.pinned() rief weiter mit zweien. Der Erzeuger schreibt alles
    oder nichts - EINE von neunzig Konfigurationen genuegte also, damit
    ~/.local/bin/start-hyprland nie entstand, und ohne den beendet sich
    zepos-session mit exit 1.

    DIE SUITE WAR DABEI GRUEN, MIT 2681 ZUSICHERUNGEN
        Kein Test rief `apps.pinned()`, und keiner rief die
        Befehlszeile `apps.py filter`, die generate_config.sh fuer jedes
        erzeugte Dock aufruft (src/generate_config.sh, Zweig
        `ags-dock`). Die Funktion war ueber ihre Bausteine geprueft und
        auf ihrem einzigen echten Weg nie ausgefuehrt.

        Genau darum geht diese Datei durch `subprocess` und nicht ueber
        einen Import: was hier laeuft, ist die Zeile aus dem Erzeuger,
        mit derselben Umgebung. Ein Import wuerde die Signatur erneut
        aus der Sicht des Tests bedienen - und die war ja nie das
        Problem.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Diese Datei ruft apps.py sonst als UNTERPROZESS auf - das ist ihr
# ganzer Zweck, siehe den Kopf. Die Zusicherungen am Ende dieser Datei
# fragen dagegen nach der ausgelieferten Liste selbst, und dafuer wird
# das Modul gebraucht statt eines zweiten Prozesses.
sys.path.insert(0, str(SRC))
import apps  # noqa: E402

# Die Zeile, die apps.py sucht. Genau so steht sie in der erzeugten
# Dock-Datei; MARKER in src/apps.py verlangt sie unveraendert.
MARKER_LINE = 'const PINNED: string[] = []  // zepos-pinned\n'


def _lauf(tmp_path: Path, dokument: dict | None) -> subprocess.CompletedProcess:
    """`apps.py filter` so aufrufen, wie generate_config.sh es tut."""
    nutzerwurzel = tmp_path / "zepos"
    nutzerwurzel.mkdir(parents=True, exist_ok=True)
    if dokument is not None:
        (nutzerwurzel / "user-settings.json").write_text(
            json.dumps(dokument), encoding="utf-8")

    ziel = tmp_path / "Dock.tsx"
    ziel.write_text("// Kopf\n" + MARKER_LINE + "// Fuss\n", encoding="utf-8")

    return subprocess.run(
        [sys.executable, str(SRC / "apps.py"), "filter", str(ziel)],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin",
             "ZEPOS_SYSTEM_ROOT": str(SRC),
             "ZEPOS_USER_ROOT": str(nutzerwurzel)})


@pytest.mark.allow_subprocess
def test_der_erzeuger_kann_die_anheftungen_aufloesen(tmp_path):
    """Der Fall, der die Maschine unbenutzbar gemacht hat.

    Mit Einstellungsdatei, denn OHNE eine nimmt pinned() den kurzen Weg
    (`if not document: return listed, []`) und ruft bar_order() gar
    nicht. Genau deshalb faellt der Fehler erst auf einer INSTALLIERTEN
    Maschine auf - der Assistent legt dort eine an.
    """
    sys.path.insert(0, str(SRC))
    try:
        import settings
        vorgaben = settings.defaults()
    finally:
        sys.path.remove(str(SRC))

    fertig = _lauf(tmp_path, vorgaben)

    assert fertig.returncode == 0, (
        "apps.py filter ist gescheitert - der Erzeuger bricht damit ab, "
        "start-hyprland entsteht nicht, und die Anmeldung laeuft im "
        f"Kreis:\n{fertig.stdout}\n{fertig.stderr}")
    assert "TypeError" not in fertig.stderr, fertig.stderr


@pytest.mark.allow_subprocess
def test_auch_mit_einer_eigenen_reihenfolge(tmp_path):
    """Und der Fall, in dem der Nutzer die Anheftungen selbst gesetzt hat.

    Der Weg darueber prueft nur, dass es ueberhaupt laeuft; dieser hier
    geht durch die Auswahl des Nutzers, also durch bar_choice() UND
    bar_order() mit einer nicht leeren Liste.
    """
    # NUR den Pfad zuruecknehmen, NICHT die Module aus sys.modules
    # werfen. Hier stand `sys.modules.pop(...)`, und drei fremde Tests
    # in test_clocks.py und test_hardware.py fielen daraufhin um - aber
    # nur, wenn diese Datei vor ihnen lief. Ein Modul aus dem Zwischen-
    # speicher zu nehmen, das andere schon geladen haben, macht aus einer
    # Zusicherung eine Frage der Reihenfolge.
    sys.path.insert(0, str(SRC))
    try:
        import settings
        import apps
        vorgaben = settings.defaults()
        ausgeliefert = apps.shipped(SRC)
    finally:
        sys.path.remove(str(SRC))

    assert ausgeliefert, "ohne ausgelieferte Auswahl prueft dieser Test nichts"
    vorgaben["bar"]["dock_pins"] = list(reversed(ausgeliefert))

    fertig = _lauf(tmp_path, vorgaben)

    assert fertig.returncode == 0, (
        f"{fertig.stdout}\n{fertig.stderr}")
    assert "TypeError" not in fertig.stderr, fertig.stderr


@pytest.mark.allow_subprocess
def test_ein_unbekannter_name_wird_genannt_und_bricht_nicht_ab(tmp_path):
    """Ein Name, den die Auswahl nicht kennt, ist kein Abbruch.

    Er wird verworfen und auf der Fehlerausgabe genannt - sonst haette
    der Nutzer einen Knopf im Dock, der nichts oeffnet, und das ist nach
    Spec 7.4 der schlimmste Fehler, den ZepOS erzeugen kann.
    """
    sys.path.insert(0, str(SRC))
    try:
        import settings
        vorgaben = settings.defaults()
    finally:
        sys.path.remove(str(SRC))

    vorgaben["bar"]["dock_pins"] = ["firefox", "gibtesnicht"]
    fertig = _lauf(tmp_path, vorgaben)

    assert fertig.returncode == 0, f"{fertig.stdout}\n{fertig.stderr}"
    assert "gibtesnicht" in fertig.stderr, (
        "der verworfene Name wird nicht genannt - er verschwindet still:\n"
        + fertig.stderr)


# ---------------------------------------------------------------------
# Ein Name, ein Platz
# ---------------------------------------------------------------------
# GEMELDET am 17.08.2026, in drei Meldungen, die alle dieselbe Wurzel
# hatten:
#
#     "ich sehe das claude roboter icon auch zweimal in der taskleiste"
#     "aktuell sind in der taskbar zwei claude code icon"
#     "wenn ich auf den claude icon druecke spammt er terminal mit claude
#      auf die oberflaeche immer mehr bis alles laggt"
#
# apps.shipped() haengt zwei Listen aneinander - die fremden Anwendungen
# aus dem depends-Block von zepos-apps und die eigenen Pakete.
# zepos-claude-code stand in BEIDEN: bei den fremden, weil zepos-apps es
# in den Abhaengigkeiten nannte (das war die Zeile, die es installierte),
# und bei den eigenen, weil es ein ZepOS-Paket war. Beide Haelften hatten
# recht; die Summe nicht.
#
# GENAU DIESE UEBERSCHNEIDUNG GIBT ES SEIT DEM 01.09.2026 NICHT MEHR.
# Der Nutzer hat das Paket gestuerzt ("ich will das packet nicht als
# meins verkaufen"); der Eintrag kommt jetzt aus zepos-config und steht
# nur noch in der eigenen Haelfte. Dieser Test bleibt trotzdem, und
# zwar unveraendert: er fragt nicht nach EINEM Namen, sondern nach der
# Eigenschaft "ein Name, ein Platz". Ein Test, der mit dem Paket
# verschwindet, das ihn ausgeloest hat, laesst die naechste
# Ueberschneidung wieder durch.
#
# WAS DAS GEKOSTET HAT, und deshalb steht dieser Test hier und nicht bei
# den Kosmetika: das Dock fuehrt seine Klick-Verbindungen in einer
# Tabelle, die nach dem Programmnamen geschluesselt war. Zwei Eintraege,
# ein Name, ein Platz - der zweite Durchlauf trennte die Verbindung des
# ERSTEN Knopfes am ZWEITEN, wo sie nicht sass, und der erste sammelte
# bei jedem Hyprland-Ereignis eine weitere an. Ein Klick startete danach
# so viele Terminals, wie seit dem Anmelden Ereignisse gekommen waren -
# und jedes neue Fenster war ein weiteres Ereignis. Der Rechner des
# Nutzers stand.
#
# Die zweite Haelfte der Reparatur sitzt in ags-dock.template: die
# Tabelle ist jetzt nach dem KNOPF geschluesselt, denn ein Knopf ist als
# Objekt eindeutig und ein Name ist es nicht.

def test_no_application_is_pinned_twice():
    """Ein Name, ein Platz - egal aus welcher Haelfte er kommt."""
    import collections

    namen = [eintrag["name"] for eintrag in apps.imprint_pins()]
    doppelt = [name for name, anzahl
               in collections.Counter(namen).items() if anzahl > 1]

    assert doppelt == [], (
        f"diese Anwendungen stehen mehrfach im Dock: {doppelt}\n"
        "Zwei Knoepfe mit demselben Programmnamen sind nicht nur ein "
        "Zeichen zu viel - siehe der Kopf dieses Abschnitts.")


def test_the_deduplication_really_removes_an_overlap(tmp_path):
    """Der Selbsttest: ohne ihn waere der Test darueber eine Regel ohne
    Gegenstand.

    HIER STAND BIS ZUM 01.09.2026 EINE MESSUNG AM ECHTEN BAUM: die
    beiden Haelften ueberschnitten sich wirklich, und der Test las
    nach, dass sie es taten. Sein eigener Kopf sagte, was zu tun ist,
    wenn er bricht - "dann gehoert nachgesehen, ob zepos-apps das Paket
    nicht mehr nennt, und nicht etwa der Test darueber entfernt".

    GENAU DAS IST PASSIERT, und zwar mit Absicht. Der Nutzer hat
    zepos-claude-code gestuerzt ("ich will das packet nicht als meins
    verkaufen"); es war der EINZIGE Name, der in beiden Haelften stand,
    und der Eintrag kommt jetzt aus zepos-config, also nur noch aus der
    eigenen. Die Ueberschneidung ist weg.

    Der Filter in apps.shipped() bleibt trotzdem stehen, und deshalb
    bleibt auch dieser Test - nur misst er nicht mehr den Baum, sondern
    die FUNKTION. Ein Filter ohne Test ist Code, von dem niemand weiss,
    ob er noch tut, was sein Kommentar behauptet; ein Test, der auf
    einen Namen wartet, den es nicht mehr gibt, ist ein Test, der nie
    wieder etwas sagt.
    """
    from pathlib import Path

    # Ein Baum mit genau der Lage, die es am 17.08.2026 wirklich gab:
    # derselbe Name in zepos-apps' depends UND als Anwendungseintrag
    # eines eigenen Rezepts.
    # Der Aufbau eines CHECKOUTS und nicht der einer Installation: src/
    # liegt neben packaging/, und genau daran erkennt apps._recipe_path()
    # und apps.own(), dass sie die Rezepte lesen duerfen statt der
    # Abdruecke.
    wurzel = tmp_path / "src"
    rezepte = tmp_path / "packaging"
    wurzel.mkdir(parents=True)
    (rezepte / "zepos-apps").mkdir(parents=True)
    (rezepte / "zepos-doppelt").mkdir(parents=True)

    (rezepte / "zepos-apps" / "PKGBUILD").write_text(
        "depends=(\n    'firefox'\n    'zepos-doppelt'\n)\n", encoding="utf-8")
    (rezepte / "zepos-doppelt" / "PKGBUILD").write_text(
        'install -Dm644 x "$pkgdir/usr/share/applications/zepos-doppelt.desktop"\n',
        encoding="utf-8")

    fremde = apps.from_recipe(
        (rezepte / "zepos-apps" / "PKGBUILD").read_text(encoding="utf-8"))
    eigene = apps.own(Path(wurzel))
    assert "zepos-doppelt" in fremde and "zepos-doppelt" in eigene, (
        "der gebaute Fall ueberschneidet sich nicht - dann misst dieser "
        f"Test nichts.\n  fremd: {fremde}\n  eigen: {eigene}")

    angeheftet = apps.shipped(Path(wurzel))
    assert angeheftet.count("zepos-doppelt") == 1, (
        "apps.shipped() wirft die Doppelte nicht mehr weg. Was das "
        "kostet, steht im Kopf dieses Abschnitts: der Rechner des "
        f"Nutzers stand.\n  {angeheftet}")
    assert angeheftet.index("zepos-doppelt") < len(fremde), (
        "der Name ist nach hinten gewandert - der erste Platz gewinnt, "
        f"weil die Reihenfolge eine Entscheidung ist: {angeheftet}")


def test_a_terminal_is_within_reach():
    """GEMELDET am 17.08.2026: "es fehlt auch noch ein terminal icon".

    kitty war immer installiert - als Abhaengigkeit von zepos-desktop -,
    stand aber nie im Dock: die angeheftete Liste liest NUR den
    depends-Block von zepos-apps.
    """
    namen = [eintrag["name"] for eintrag in apps.imprint_pins()]
    assert "kitty" in namen, (
        f"kein Terminal unter den angehefteten Anwendungen: {namen}")
