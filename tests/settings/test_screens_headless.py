# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Seite "Bildschirme", wirklich gebaut und wirklich bedient.

WAS HIER GEMESSEN WIRD, UND WAS DIE EIGENTLICHE FRAGE IST
    Die Frage ist NICHT "steht die Anordnung in der Datei". Eine Seite,
    die eine tadellose monitors.conf schreibt und den Compositor nie
    anspricht, sieht in jedem Dateitest richtig aus - und der Nutzer
    merkt beim naechsten Anmelden, dass sein Schirm schwarz bleibt.
    Umgekehrt genauso: eine Seite, die anwendet und nie schreibt, sieht
    auf dem Schirm richtig aus und ist nach der naechsten Anmeldung weg.

    Deshalb wird hier ueberall BEIDES gefragt: was `hyprctl` bekommen
    hat, und was in der Datei steht. Und die Reihenfolge dazwischen ist
    die eigentliche Zusicherung:

        angewandt  -> ja, sofort
        geschrieben -> ERST wenn bestaetigt

    Ohne diese Trennung braeuchte der Rueckfall einen zweiten Rueckfall
    fuer die Datei, und eine Sitzung, die nach einem Absturz mit der
    schlechten Datei startet, faende keinen Schirm mehr, auf dem sie
    fragen koennte.

WAS HIER NICHT GEMESSEN WIRD
    Der Rueckfall selbst. Er laeuft im Waechter, in einem eigenen
    Prozess, und tests/src/test_displays_guard.py laesst dessen Frist
    wirklich ablaufen und toetet dessen Starter wirklich. Hier laeuft der
    ECHTE Waechter mit - jeder Lauf startet einen -, aber was gemessen
    wird, ist, was die Seite ihm sagt.

DER STELLVERTRETER FUER hyprctl
    Ein Python-Skript mit absolutem Shebang, kein Shell-Skript: der PATH
    des Kindes enthaelt nur das Stellvertreterverzeichnis, also gibt es
    darin kein `cat`, mit dem eine Shell die hinterlegte Antwort
    ausgeben koennte.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from tests.settings.test_settings_headless import run_settings

MONITORS = [
    {
        "name": "DP-1",
        "description": "Acme Vision 34",
        "width": 3440, "height": 1440, "refreshRate": 59.97,
        "x": 0, "y": 0, "scale": 1.0, "transform": 0, "disabled": False,
        "availableModes": ["3440x1440@59.97Hz", "1920x1080@60.00Hz"],
    },
    {
        "name": "eDP-1",
        "description": "Panel Works 16",
        "width": 1920, "height": 1200, "refreshRate": 60.001,
        "x": 3440, "y": 0, "scale": 1.0, "transform": 0, "disabled": False,
        "availableModes": ["1920x1200@60.00Hz"],
    },
]

# Er antwortet auf `monitors ... -j` und schreibt alles andere auf.
#
# NIEMALS `exec /usr/bin/hyprctl`: der Name steht in
# conftest.NEVER_PASSTHROUGH, weil er die Sitzung aendert, in der diese
# Suite laeuft. run_settings() weist einen Stellvertreter zurueck, der es
# doch versucht.
HYPRCTL_STUB = textwrap.dedent("""\
    #!/usr/bin/python3
    import os, sys
    if sys.argv[1:2] == ["monitors"]:
        sys.stdout.write(open(os.environ["HYPRCTL_MONITORS"]).read())
    else:
        with open(os.environ["HYPRCTL_LOG"], "a") as handle:
            handle.write(" ".join(sys.argv[1:]) + "\\n")
    """)


def run_screens(tmp_path: Path, script: str, *, monitors=None,
                profile: str | None = None,
                existing: str | None = None, **kwargs):
    """Ein Lauf mit einem antwortenden `hyprctl`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    answer = tmp_path / "monitors.json"
    answer.write_text(json.dumps(monitors if monitors is not None
                                 else MONITORS), encoding="utf-8")
    log = tmp_path / "hyprctl.txt"
    log.write_text("", encoding="utf-8")

    hypr = tmp_path / "config" / "hypr"
    hypr.mkdir(parents=True, exist_ok=True)
    if existing is not None:
        (hypr / "monitors.conf").write_text(existing, encoding="utf-8")
    if profile is not None:
        (hypr / "current-profile").write_text(profile, encoding="utf-8")
        (tmp_path / "home" / "zepos" / "profiles" / profile).mkdir(
            parents=True, exist_ok=True)

    run = run_settings(
        tmp_path, script,
        stubs={"hyprctl": HYPRCTL_STUB},
        environment_extra={"HYPRCTL_MONITORS": str(answer),
                           "HYPRCTL_LOG": str(log)},
        **kwargs)
    run.applied = [line for line in log.read_text(encoding="utf-8").splitlines()
                   if line]
    run.conf = hypr / "monitors.conf"
    run.profile_conf = (
        tmp_path / "home" / "zepos" / "profiles" / (profile or "-")
        / "monitors.conf")
    return run


def written(run) -> str:
    return run.conf.read_text(encoding="utf-8") if run.conf.is_file() else ""


def final(run) -> dict[str, list[str]]:
    """Der LETZTE Block der Spur, nach Praefix geordnet.

    Run.after() liefert die erste Marke eines Praefixes nach einer
    Anweisung, und das reicht hier fuer nichts: ein Block traegt eine
    `screen:`- und eine `spec:`-Zeile JE BILDSCHIRM, und ein Skript
    schaltet durchaus zweimal denselben Schalter. Was diese Pruefungen
    fragen, ist fast immer der Endzustand - also der Block hinter der
    letzten Anweisung, vollstaendig.
    """
    marks = run.marks
    starts = [index for index, line in enumerate(marks)
              if line.startswith("after-")]
    block = marks[starts[-1] + 1:] if starts else marks
    found: dict[str, list[str]] = {}
    for line in block:
        prefix, _, rest = line.partition(":")
        found.setdefault(prefix, []).append(rest)
    return found


def one(run, prefix: str) -> str:
    values = final(run).get(prefix)
    assert values, f"keine Marke {prefix} im letzten Block:\n{run.report}"
    return values[0]


def per_screen(run, prefix: str) -> dict[str, str]:
    """{"DP-1": "0x0:3440x1440:an:-", ...} aus den `screen:`- oder
    `spec:`-Zeilen des letzten Blocks."""
    return dict(line.split("=", 1) for line in final(run).get(prefix, []))


# --------------------------------------------------------------------
# Die Seite steht ueberhaupt
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_page_shows_what_the_compositor_reports(tmp_path):
    run = run_screens(tmp_path, "screen:eDP-1")

    assert run.mark("screens") == "2", run.report
    assert "screen:DP-1=0x0:3440x1440:an:gewaehlt" in run.marks, run.report
    assert run.after("screen", "screen").startswith("DP-1=0x0"), run.report
    assert "screen:eDP-1=3440x0:1920x1200:an:gewaehlt" in run.marks, run.report


@pytest.mark.allow_subprocess
def test_a_page_without_a_compositor_explains_itself(tmp_path):
    """Eine leere Flaeche saehe aus wie ein Fehler dieser Anwendung.

    Gefahren ohne Stellvertreter, also mit einem PATH ohne `hyprctl` -
    genau der Zustand ausserhalb einer Hyprland-Sitzung.
    """
    run = run_settings(tmp_path, "scale:2.0")

    assert run.mark("screens") == "keine", run.report
    assert run.returncode == 0, run.report


@pytest.mark.allow_subprocess
def test_nothing_reaches_the_compositor_before_the_button(tmp_path):
    """Ein Schirm, den jemand schiebt und wieder loslaesst, ist keine
    Bestellung.

    Jede Zwischenstellung anzuwenden waere ein Moduswechsel, also ein
    Schwarzbild - und beim Ziehen sind es Dutzende.
    """
    run = run_screens(tmp_path, "drag:eDP-1@2000,400")

    assert run.applied == [], run.report
    assert written(run) == "", run.report
    assert one(run, "screens-changed") == "True", run.report


# --------------------------------------------------------------------
# Anordnen
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_dragged_screen_snaps_to_its_neighbour(tmp_path):
    """Ein Rest von dreissig Pixeln zwischen zwei Schirmen ist kein
    Gestaltungswunsch, sondern ein Streifen, in dem der Mauszeiger
    haengenbleibt."""
    # Vierzig Pixel neben die rechte Kante von DP-1 und dreissig
    # darunter - beides innerhalb von SNAP_DISTANCE, beides in einer
    # Richtung, in der von Hand niemand trifft.
    run = run_screens(tmp_path, "drag:eDP-1@3400,30")

    assert per_screen(run, "screen") == {
        "DP-1": "0x0:3440x1440:an:-",
        "eDP-1": "3440x0:1920x1200:an:gewaehlt",
    }, run.report


@pytest.mark.allow_subprocess
def test_switching_a_screen_off_shows_up_in_its_line(tmp_path):
    run = run_screens(tmp_path, "screen:eDP-1 screen-off")

    assert per_screen(run, "spec")["eDP-1"].endswith(",disable"), run.report
    assert per_screen(run, "screen")["eDP-1"].endswith(":aus:gewaehlt"), (
        run.report)
    assert run.applied == [], run.report


@pytest.mark.allow_subprocess
def test_the_last_screen_cannot_be_switched_off_into_a_black_desk(tmp_path):
    """DIE ZUSICHERUNG, DIE KEINEN RUECKWEG HAT.

    Beide aus heisst: die Frage, ob man es behalten will, stuende auf
    keinem Schirm mehr. Der Knopf bleibt deshalb tot - und es ist der
    Knopf und nicht der Schalter, weil man den zweiten Schirm
    ausschalten koennen soll, um es sich anzusehen.
    """
    run = run_screens(
        tmp_path, "screen:DP-1 screen-off screen:eDP-1 screen-off")

    assert one(run, "screens-apply-sensitive") == "False", run.report
    assert one(run, "screens-changed") == "True", (
        "beide aus IST eine Aenderung - der Knopf ist tot, weil sie nicht "
        "anwendbar ist, und nicht, weil nichts passiert waere:\n"
        + run.report)
    assert run.applied == [], run.report


@pytest.mark.allow_subprocess
def test_a_scaled_screen_takes_less_room_on_the_desk(tmp_path):
    """Hyprland teilt die Aufloesung durch den Massstab. Ein Nachbar, der
    gegen die ungeteilte Breite gesetzt wird, ueberlappt."""
    run = run_screens(tmp_path, "screen:eDP-1 screen-scale:2")

    assert per_screen(run, "screen")["eDP-1"] == (
        "3440x0:960x600:an:gewaehlt"), run.report


# --------------------------------------------------------------------
# Anwenden: der Compositor bekommt es, die Datei noch nicht
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_applying_reaches_the_compositor_and_not_yet_the_file(tmp_path):
    """DIE PRUEFUNG, UM DERENTWILLEN ES DIESE DATEI GIBT.

    Eine Zusicherung, die "angewandt" mit "geschrieben" verwechselt,
    faengt den Fehler nicht, der zaehlt. Hier steht deshalb beides in
    einem Lauf: `hyprctl` hat die neue Anordnung, die Datei hat noch
    nichts.
    """
    run = run_screens(tmp_path, "screen:eDP-1 screen-scale:2 screen-apply")

    # IN DIESEM AUGENBLICK gefragt, nicht nach dem Lauf: was am Ende in
    # der Datei steht, sagt nichts darueber, ob sie beim Anwenden schon
    # dastand.
    assert one(run, "applied") == "1", run.report
    assert one(run, "applied-last").startswith("--batch keyword monitor "), (
        run.report)
    assert "1920x1200@60.001,3440x0,2" in one(run, "applied-last"), run.report
    assert one(run, "written") == "False", (
        "die Datei wurde geschrieben, bevor jemand bestaetigt hat - dann "
        "braeuchte der Rueckfall einen zweiten Rueckfall fuer sie:\n"
        + run.report)
    assert one(run, "screens-attempt") == "True", run.report
    # Und die Frage steht wirklich - ohne sie waere "auf Probe" nur ein
    # Wort im Bericht.
    assert one(run, "screens-countdown") == "15", run.report


@pytest.mark.allow_subprocess
def test_keeping_writes_the_file_that_was_applied(tmp_path):
    run = run_screens(
        tmp_path, "screen:eDP-1 screen-scale:2 screen-apply screen-keep")

    assert one(run, "written") == "True", run.report
    text = written(run)
    assert "monitor=desc:Panel Works 16,1920x1200@60.001,3440x0,2" in text, (
        run.report + "\n" + text)
    # Und zwar GENAU das, was der Compositor bekommen hat. Sonst zeigte
    # der Schirm etwas anderes als die Datei sagt, und der Unterschied
    # faellt erst bei der naechsten Anmeldung auf.
    for line in text.splitlines():
        if line.startswith("monitor="):
            assert f"keyword monitor {line[len('monitor='):]}" in run.applied[0], (
                run.report + "\n" + text)
    assert one(run, "screens-changed") == "False", run.report


@pytest.mark.allow_subprocess
def test_the_active_profile_gets_the_same_file(tmp_path):
    """Ohne sie waere die Anordnung bei der naechsten Anmeldung wieder
    weg: start-hyprland kopiert das Profil ueber ~/.config/hypr."""
    run = run_screens(
        tmp_path, "screen:eDP-1 screen-scale:2 screen-apply screen-keep",
        profile="buero")

    assert run.profile_conf.is_file(), run.report
    assert run.profile_conf.read_text(encoding="utf-8") == written(run)
    assert "buero" in one(run, "screens-report"), run.report


@pytest.mark.allow_subprocess
def test_what_the_page_does_not_offer_survives_the_rewrite(tmp_path):
    """Die Spiegelung. Eine Oberflaeche, die beim Anfassen einer
    Einstellung eine andere loescht, ist schlimmer als eine, die die
    andere nicht kennt."""
    run = run_screens(
        tmp_path, "screen:DP-1 screen-scale:2 screen-apply screen-keep",
        existing="monitor=desc:Panel Works 16,1920x1200@60.001,"
                 "3440x0,1,mirror,DP-1\n")

    assert ",mirror,DP-1" in written(run), run.report + "\n" + written(run)


# --------------------------------------------------------------------
# Nicht behalten: der Weg zurueck
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_giving_it_back_restores_the_old_arrangement_and_writes_nothing(
        tmp_path):
    run = run_screens(
        tmp_path, "screen:eDP-1 screen-scale:2 screen-apply screen-back")

    assert len(run.applied) == 2, run.report
    assert "3440x0,2" in run.applied[0], run.report
    assert "3440x0,1" in run.applied[1], (
        "der alte Stand wurde nicht wiederhergestellt:\n" + run.report)
    assert written(run) == "", run.report
    assert one(run, "screens-changed") == "False", (
        "nach dem Zuruecknehmen steht wieder der alte Stand da - sonst "
        "zeigt die Seite eine Anordnung, die auf keinem Schirm gilt:\n"
        + run.report)


@pytest.mark.allow_subprocess
def test_a_countdown_that_runs_out_gives_it_back_by_itself(tmp_path):
    """Wer nichts sieht, kann auch nicht antworten.

    Was hier laeuft, ist der Zaehler DER OBERFLAECHE. Der Rueckfall, der
    auch ohne sie greift, hat seine Belege in
    tests/src/test_displays_guard.py.
    """
    run = run_screens(
        tmp_path, "screen:eDP-1 screen-scale:2 screen-apply screen-wait")

    assert run.after("screen-apply", "screens-countdown") == "15", run.report
    assert len(run.applied) == 2, run.report
    assert "3440x0,1" in run.applied[1], run.report
    assert written(run) == "", run.report
    assert "Zurückgenommen" in one(run, "screens-report"), run.report


@pytest.mark.allow_subprocess
def test_the_question_defaults_to_giving_it_back(tmp_path):
    """Der Unterschied zwischen einer Rueckfrage und einer Falle.

    Die Escape-Taste und jedes versehentliche Schliessen bedeuten hier
    "ich sehe nichts" - also zuruecknehmen. Ein Dialog, dessen Vorgabe
    "behalten" waere, machte aus dem Wegklicken eine Zustimmung zu etwas,
    das man nicht sehen kann.
    """
    run = run_screens(
        tmp_path, "screen:eDP-1 screen-scale:2 screen-apply screen-shut")

    assert run.mark("dialog-default") == "zurueck", run.report
    assert run.mark("dialog-close") == "zurueck", run.report

    # Und das Zumachen des FENSTERS bedeutet dasselbe: libadwaita
    # schliesst dabei seine Dialoge mit dem Schliess-Ergebnis, also mit
    # "zurueck". Wer zumacht, statt zu antworten, sieht nicht, was er
    # bestaetigen soll.
    assert one(run, "applied") == "2", (
        "das Fenster ging zu, waehrend die Frage stand, und die Anordnung "
        "blieb stehen:\n" + run.report)
    assert "3440x0,1" in one(run, "applied-last"), run.report
    assert one(run, "written") == "False", run.report
    assert one(run, "screens-attempt") == "False", run.report


# --------------------------------------------------------------------
# Die Ueberlappung: sie entsteht nicht mehr, und sie wird gesagt
# --------------------------------------------------------------------

# Zwei Schirme, die uebereinanderliegen - so, wie der Compositor sie
# nach dem 01.09.2026 wirklich gemeldet hat. Kein erfundener Fall: der
# Nutzer hatte einen Schirm auf den anderen gezogen und die Anordnung
# bestaetigt, und danach standen beide auf demselben Fleck.
UEBEREINANDER = [
    {**MONITORS[0]},
    {**MONITORS[1], "x": 0, "y": 0},
]


@pytest.mark.allow_subprocess
def test_a_screen_dragged_onto_another_does_not_end_up_on_top_of_it(tmp_path):
    """DIE BESTELLUNG, woertlich (01.09.2026): "ich sehe seit dem
    anwenden alle sachen doppelt auf einem monitor, so buggy ist das".

    Gezogen wird eDP-1 mitten auf DP-1 - dieselbe Geste wie "einen
    bildschirm hingezogen und ueber dem monitor geplaced". Vor dem
    01.09.2026 rastete er dort EIN: _snap_axis fand auf beiden Achsen
    den Kandidaten "vorne buendig", und der gezogene Schirm lag exakt
    auf dem anderen. Zwei Schirme auf demselben Fleck sind zwei Leisten
    und zwei Docks an derselben Stelle.

    Geprueft wird die Seite und nicht nur die Rechnung darunter: was
    zaehlt, ist, wo das Rechteck liegt, nachdem man es losgelassen hat.
    """
    run = run_screens(tmp_path, "drag:eDP-1@40,40")

    stand = per_screen(run, "screen")
    orte = {name: wert.split(":")[0] for name, wert in stand.items()}
    assert orte["DP-1"] != orte["eDP-1"], (
        f"beide Schirme stehen auf {orte['DP-1']}:\n" + run.report)
    assert "übereinander" not in one(run, "screens-hint"), run.report
    assert run.applied == [], run.report


@pytest.mark.allow_subprocess
def test_an_overlap_that_is_already_there_is_named_under_the_drawing(tmp_path):
    """Sie kann noch immer dastehen - aus der Datei, aus einem Massstab,
    aus einer Aufloesung. Dann wird sie gesagt."""
    run = run_screens(tmp_path, "screen:eDP-1", monitors=UEBEREINANDER)

    assert "übereinander" in one(run, "screens-hint"), run.report
    # UND DER KNOPF BLEIBT LEBENDIG, sobald sich etwas geaendert hat.
    # Eine Oberflaeche, die eine bestehende Ueberlappung nicht mehr
    # anwenden laesst, ist die einzige, mit der man sie aufloesen wollte.
    assert one(run, "screens-changed") == "False", run.report


@pytest.mark.allow_subprocess
def test_the_question_names_the_overlap_before_the_countdown(tmp_path):
    """DIE ENTSCHEIDUNG VOM 01.09.2026: melden, nicht verweigern - aber
    an der Stelle, an der es zaehlt.

    Die Warnung stand schon vorher unter der Zeichnung. Gelesen wurde
    sie nicht, weil dort noch nichts passiert war. In der Rueckfrage
    steht sie in dem einzigen Augenblick, in dem sie eine Entscheidung
    aendern kann - und die Rueckfrage ist zugleich der Weg zurueck.
    """
    run = run_screens(tmp_path, "screen:eDP-1 screen-scale:2 screen-apply",
                      monitors=UEBEREINANDER)

    koerper = one(run, "dialog-body")
    assert "übereinander" in koerper, run.report
    assert koerper.index("übereinander") < koerper.index("Sekunden"), (
        "die Warnung steht hinter dem Zaehler - dann liest sie niemand:\n"
        + run.report)
    # GEMELDET UND NICHT VERWEIGERT: der Compositor hat die Anordnung
    # bekommen, waehrend die Frage steht. Gezaehlt wird die Marke aus
    # DIESEM Augenblick und nicht `run.applied` nach dem Lauf - beim
    # Aufraeumen nimmt der Waechter zurueck, und das ist ein zweiter
    # Aufruf, der zu dieser Frage nichts sagt.
    assert one(run, "applied") == "1", run.report
    assert one(run, "written") == "False", run.report
