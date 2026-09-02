# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Rueckfall, als echter Prozess gemessen.

DIE EINE FRAGE, DIE DIESE DATEI BEANTWORTET
    Kommt der alte Schirm wieder, wenn niemand antwortet - AUCH DANN,
    wenn das Programm, das die Anordnung angewandt hat, in der
    Zwischenzeit gestorben ist?

    Das laesst sich nicht mit einem Platzhalter fuer subprocess.run
    messen. Der Waechter IST ein eigener Prozess; genau das ist seine
    Aussage. Ein Test, der ihn nachbaut, misst den Nachbau - und der
    Nachbau stirbt mit dem Testlauf, also gerade nicht.

    Deshalb laeuft hier der echte src/bin/zepos-displays-guard, mit einer
    echten Pipe, und `hyprctl` ist ein Stellvertreter, der aufschreibt,
    was er bekommen haette.

WARUM `hyprctl` EIN STELLVERTRETER SEIN MUSS UND NICHT DAS ECHTE
    tests/conftest.py fuehrt es namentlich in NEVER_PASSTHROUGH: es
    aendert die Sitzung, in der diese Suite laeuft. Ein Waechter, der
    hier wirklich `hyprctl keyword monitor` riefe, stellte die Schirme
    des Entwicklers um - und zwar auf eine Anordnung, die dieser Test
    sich ausgedacht hat.

WARUM DIE FRISTEN HIER KURZ SIND
    displays.CONFIRM_SECONDS ist 15, und ein Testlauf, der zwei Minuten
    Fristen abwartet, wird abgeschaltet statt repariert. Gemessen wird
    der Mechanismus, und der ist derselbe: `plan["seconds"]` kommt ueber
    die Pipe, der Waechter kennt keine eingebaute Zahl.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
GUARD = SRC / "bin" / "zepos-displays-guard"

# Die Anordnung, in die zurueckgestellt werden soll. Eine Zeichenkette,
# die nirgends sonst vorkommt - dann beweist ihr Auftauchen im Protokoll
# des Stellvertreters, dass genau DIESER Plan ausgefuehrt wurde und nicht
# irgendein Aufruf.
RESTORE = ["hyprctl", "--batch",
           "keyword monitor DP-1,3440x1440@59.97,0x0,1 ; "
           "keyword monitor eDP-1,1920x1200@60.001,3440x0,1"]

# Ein Stellvertreter, der jeden Aufruf in eine Datei schreibt.
#
# Kein `exec /usr/bin/hyprctl` - conftest.assert_safe_to_passthrough()
# verbietet es fuer genau diesen Namen, und der Grund ist die Sitzung des
# Entwicklers.
HYPRCTL_STUB = textwrap.dedent("""\
    #!/bin/sh
    printf '%s\\n' "$*" >> "$HYPRCTL_LOG"
    exit "${HYPRCTL_EXIT:-0}"
    """)


@pytest.fixture
def bench(tmp_path):
    """Ein Stellvertreterverzeichnis, ein Protokoll, eine Umgebung."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    stub = stubs / "hyprctl"
    stub.write_text(HYPRCTL_STUB, encoding="utf-8")
    stub.chmod(0o755)
    log = tmp_path / "applied.txt"
    log.write_text("", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()

    return {
        "root": tmp_path,
        "log": log,
        "environment": {
            # NUR die Stellvertreter. Ein leerer PATH waere nicht dasselbe:
            # der Waechter sucht auch `notify-send`, und ein PATH, auf dem
            # der echte liegt, liesse ihn dem Entwickler eine Meldung
            # schicken.
            "PATH": str(stubs),
            "HOME": str(tmp_path),
            "XDG_STATE_HOME": str(state),
            "HYPRCTL_LOG": str(log),
            "ZEPOS_SYSTEM_ROOT": str(SRC),
            "PYTHONUNBUFFERED": "1",
        },
    }


def start(bench, seconds: float, command=None) -> subprocess.Popen:
    """Den Waechter starten und warten, bis er bereit meldet."""
    process = subprocess.Popen(
        [sys.executable, str(GUARD)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
        env=bench["environment"], start_new_session=True)
    plan = {"seconds": seconds,
            "command": command if command is not None else RESTORE}
    process.stdin.write(json.dumps(plan) + "\n")
    process.stdin.flush()
    assert process.stdout.readline().strip() == "bereit"
    return process


def applied(bench) -> list[str]:
    return [line for line in
            bench["log"].read_text(encoding="utf-8").splitlines() if line]


def wait_for(condition, seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


# --------------------------------------------------------------------
# Die zwei Wege zurueck
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_deadline_puts_the_old_arrangement_back(bench):
    """DER BELEG, DASS DER RUECKFALL NACH ZEIT GREIFT.

    Niemand antwortet. Nach der Frist ist der alte Stand wieder da, und
    zwar durch einen Befehl an den Compositor - nicht dadurch, dass eine
    Datei zurueckgelegt und gehofft wird, dass jemand sie bemerkt. Genau
    das tut die Vorlage (nwg-displays, main.py:1017: "just save the file
    and wait for Hyprland to notice").
    """
    process = start(bench, seconds=1.0)

    assert process.wait(timeout=30) == 10, (
        "der Waechter hat die Frist nicht als Grund gemeldet")
    assert applied(bench) == [" ".join(RESTORE[1:])]


@pytest.mark.allow_subprocess
def test_a_crash_puts_the_old_arrangement_back_at_once(bench, tmp_path):
    """DER BELEG, DASS DER RUECKFALL AUCH NACH EINEM ABSTURZ GREIFT.

    Der Elternprozess wird mit SIGKILL beendet - kein Aufraeumen, kein
    atexit, kein Signalbehandler, das haerteste Ende, das es gibt. Sein
    Schreibende der Pipe faellt damit weg, der Waechter liest EOF und
    stellt SOFORT zurueck.

    Das ist die Zusicherung, die ein Zeitgeber IM Programm nicht geben
    kann: nwg-displays haengt seinen an GLib.timeout_add_seconds
    (main.py:986), also an dieselbe Hauptschleife, die mit dem Programm
    stirbt.

    Und es ist SCHNELLER als die Frist: die Frist ist hier auf 300
    Sekunden gesetzt, damit ein Rueckfall, der trotzdem kommt, nur ueber
    die gebrochene Pipe gekommen sein kann.
    """
    parent = tmp_path / "eltern.py"
    parent.write_text(textwrap.dedent(f"""\
        import json, os, subprocess, sys, time
        process = subprocess.Popen(
            [sys.executable, {str(GUARD)!r}],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            start_new_session=True)
        process.stdin.write(json.dumps(
            {{"seconds": 300, "command": {RESTORE!r}}}) + "\\n")
        process.stdin.flush()
        assert process.stdout.readline().strip() == "bereit"
        print(process.pid, flush=True)
        os.kill(os.getpid(), 9)
        """), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(parent)], env=bench["environment"],
        capture_output=True, text=True, timeout=60)

    assert completed.returncode == -signal.SIGKILL, (
        "der Elternprozess ist nicht abgestuerzt, also misst dieser Lauf "
        f"nichts: {completed.stdout}{completed.stderr}")
    assert wait_for(lambda: applied(bench)), (
        "der Waechter hat nach dem Absturz seines Starters nichts "
        "wiederhergestellt")
    assert applied(bench) == [" ".join(RESTORE[1:])]

    guard_pid = int(completed.stdout.strip())
    assert wait_for(lambda: not _alive(guard_pid)), (
        "der Waechter laeuft noch, obwohl er zurueckgestellt hat")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:                                  # pragma: no cover
        return True
    return True


@pytest.mark.allow_subprocess
def test_a_confirmed_arrangement_is_left_alone(bench):
    """Die Gegenprobe, ohne die "es stellt zurueck" auch dann wahr waere,
    wenn es IMMER zurueckstellt."""
    process = start(bench, seconds=60)

    output, _ = process.communicate(input="behalten\n", timeout=30)

    assert process.returncode == 0, output
    assert applied(bench) == [], (
        "der Waechter hat trotz Bestaetigung zurueckgestellt")


@pytest.mark.allow_subprocess
def test_the_arrangement_can_be_given_back_before_the_deadline(bench):
    """Wer sofort sieht, dass es falsch ist, soll nicht warten muessen."""
    process = start(bench, seconds=300)

    output, _ = process.communicate(input="verwerfen\n", timeout=30)

    assert process.returncode == 12, output
    assert applied(bench) == [" ".join(RESTORE[1:])]


@pytest.mark.allow_subprocess
def test_a_word_the_guard_does_not_know_is_not_an_answer(bench):
    """Ein unbekanntes Wort ist WEDER eine Bestaetigung NOCH ein Grund
    zurueckzustellen. Es wird ueberlesen, und die Frist laeuft weiter.

    BEIDE HAELFTEN, und die zweite ist der Grund fuer die Bauart dieser
    Pruefung: mit einer Frist von 300 Sekunden sieht ein Waechter, der
    ein unbekanntes Wort als "behalten" liest, GENAUSO aus wie einer, der
    es ueberliest - beide enden mit 0 und stellen nichts zurueck.
    Gemessen wird deshalb gegen eine Frist von einer Sekunde: wer das
    Wort ueberliest, laeuft in sie hinein und stellt zurueck; wer es als
    Antwort nimmt, endet vorher mit 0.
    """
    process = start(bench, seconds=1.0)

    process.stdin.write("vielleicht\n")
    process.stdin.flush()

    assert process.wait(timeout=30) == 10, (
        "das unbekannte Wort wurde als Antwort genommen - dann ist jeder "
        "Tippfehler auf der Pipe eine Bestaetigung fuer eine Anordnung, "
        "die niemand gesehen hat")
    assert applied(bench) == [" ".join(RESTORE[1:])]


@pytest.mark.allow_subprocess
def test_a_known_word_after_an_unknown_one_still_counts(bench):
    """Die andere Haelfte: ueberlesen heisst weiterhoeren."""
    process = start(bench, seconds=300)

    process.stdin.write("vielleicht\nbehalten\n")
    output, _ = process.communicate(timeout=30)

    assert process.returncode == 0, output
    assert applied(bench) == []


@pytest.mark.allow_subprocess
def test_a_confirmation_without_a_final_newline_still_counts(bench):
    """Sonst waere das Schliessen der Pipe unmittelbar nach dem Wort ein
    Rueckfall - und genau so schliesst subprocess.communicate()."""
    process = start(bench, seconds=300)

    output, _ = process.communicate(input="behalten", timeout=30)

    assert process.returncode == 0, output
    assert applied(bench) == []


@pytest.mark.allow_subprocess
def test_nothing_is_restored_when_nothing_was_ever_applied(bench):
    """Die Pipe bricht, bevor ein Plan angekommen ist.

    Dann hat der Starter auch nichts angewandt - er wartet auf "bereit",
    und das kommt erst mit dem Plan. Zurueckzustellen gaebe es also
    nichts, und ein Waechter, der es trotzdem taete, aenderte die
    Schirme eines Nutzers, der nur ein Fenster geoeffnet hat.
    """
    process = subprocess.Popen(
        [sys.executable, str(GUARD)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        env=bench["environment"], start_new_session=True)

    output, _ = process.communicate(timeout=30)

    assert process.returncode == 2, output
    assert applied(bench) == []


@pytest.mark.allow_subprocess
def test_a_plan_that_is_not_a_plan_arms_nothing(bench):
    process = subprocess.Popen(
        [sys.executable, str(GUARD)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
        env=bench["environment"], start_new_session=True)

    output, errors = process.communicate(input="{kein json\n", timeout=30)

    assert process.returncode == 2, output
    assert "unreadable plan" in errors
    assert applied(bench) == []


@pytest.mark.allow_subprocess
def test_the_guard_takes_no_switches(bench):
    completed = subprocess.run(
        [sys.executable, str(GUARD), "--sofort"],
        env=bench["environment"], capture_output=True, text=True, timeout=30)

    assert completed.returncode == 64
    assert "takes no switches" in completed.stderr


# --------------------------------------------------------------------
# Was hinterher noch davon zeugt
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_a_rollback_leaves_a_line_that_survives_the_crash(bench):
    """Nach einem Absturz ist dieses Protokoll das EINZIGE, was noch
    sagt, dass zurueckgestellt wurde - die Oberflaeche, die es sonst
    gesagt haette, gibt es dann nicht mehr."""
    process = start(bench, seconds=1.0)
    process.wait(timeout=30)

    log = (Path(bench["environment"]["XDG_STATE_HOME"]) / "zepos"
           / "displays-guard.log")
    assert log.is_file(), "der Waechter hat nichts hinterlassen"
    text = log.read_text(encoding="utf-8")
    assert "No confirmation" in text
    assert "restored" in text


@pytest.mark.allow_subprocess
def test_a_rollback_that_fails_says_so_instead_of_claiming_success(bench):
    """Ein `hyprctl`, das den Rueckweg nicht geht, ist der schlimmste
    Fall dieser ganzen Vorrichtung. Er darf nicht wie ein Erfolg
    aussehen."""
    bench["environment"]["HYPRCTL_EXIT"] = "1"
    process = start(bench, seconds=1.0)

    # wait() und NICHT communicate(): letzteres schliesst die Eingabe,
    # und eine geschlossene Eingabe ist fuer den Waechter ein Absturz -
    # er stellte dann aus dem anderen Grund zurueck, und dieser Lauf
    # maesse die Frist nicht mehr.
    assert process.wait(timeout=30) == 10
    output = process.stdout.read()
    assert "FAILED" in output
    log = (Path(bench["environment"]["XDG_STATE_HOME"]) / "zepos"
           / "displays-guard.log")
    assert "FAILED" in log.read_text(encoding="utf-8")


@pytest.mark.allow_subprocess
def test_a_dead_listener_does_not_turn_a_rollback_into_a_traceback(bench,
                                                                  tmp_path):
    """CPython leert sys.stdout beim Beenden noch einmal.

    Ohne das Umhaengen auf /dev/null schriebe es dabei "Exception ignored
    while flushing sys.stdout: BrokenPipeError" nach stderr - eine
    Fehlermeldung ueber einen ERFOLGREICHEN Rueckfall, an genau der
    Stelle, an der jemand nach der Ursache sucht.
    """
    parent = tmp_path / "eltern.py"
    parent.write_text(textwrap.dedent(f"""\
        import json, os, subprocess, sys
        errors = open({str(tmp_path / 'guard-stderr.txt')!r}, "w")
        process = subprocess.Popen(
            [sys.executable, {str(GUARD)!r}],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
            text=True, start_new_session=True)
        process.stdin.write(json.dumps(
            {{"seconds": 1, "command": {RESTORE!r}}}) + "\\n")
        process.stdin.flush()
        assert process.stdout.readline().strip() == "bereit"
        print(process.pid, flush=True)
        os.kill(os.getpid(), 9)
        """), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(parent)], env=bench["environment"],
        capture_output=True, text=True, timeout=60)
    guard_pid = int(completed.stdout.strip())
    assert wait_for(lambda: not _alive(guard_pid))

    assert applied(bench) == [" ".join(RESTORE[1:])]
    assert (tmp_path / "guard-stderr.txt").read_text(encoding="utf-8") == "", (
        "der Waechter hat beim Zurueckstellen auf stderr geschrieben")


# --------------------------------------------------------------------
# Scharfmachen und Anwenden - die Reihenfolge, die alles traegt
# --------------------------------------------------------------------

# Ein Vorschalter vor den ECHTEN Waechter, der EINE Zeile ins selbe
# Protokoll schreibt, in das auch der hyprctl-Stellvertreter schreibt -
# und zwar genau dann, wenn der Waechter "bereit" gemeldet hat.
#
# WARUM ES DEN BRAUCHT
#     Weil sonst nichts die REIHENFOLGE misst. Ein arm_and_apply(), das
#     erst anwendet und dann scharf macht, hinterlaesst denselben
#     Zustand wie eins, das es richtig herum tut: der Waechter laeuft,
#     der Befehl ist abgesetzt, alle Zustandsfragen antworten gleich. Der
#     Unterschied ist AUSSCHLIESSLICH die Reihenfolge, und die steht
#     nirgends, solange nicht beide Ereignisse in dieselbe Datei
#     schreiben. GEMESSEN: die erste Fassung dieser Pruefung fragte den
#     Zustand ab und ueberlebte die Mutation "anwenden vor dem
#     Scharfmachen" ohne ein Wort.
#
# Der echte Waechter laeuft dabei unveraendert weiter - der Vorschalter
# reicht Plan und Antworten durch und gibt dessen Rueckgabewert zurueck.
GUARD_PROXY = textwrap.dedent("""\
    import os, subprocess, sys
    guard = subprocess.Popen(
        [sys.executable, sys.argv[1]],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    guard.stdin.write(sys.stdin.readline())
    guard.stdin.flush()
    ready = guard.stdout.readline()
    with open(os.environ["HYPRCTL_LOG"], "a") as handle:
        handle.write("waechter-bereit\\n")
    sys.stdout.write(ready)
    sys.stdout.flush()
    for line in sys.stdin:
        guard.stdin.write(line)
        guard.stdin.flush()
    guard.stdin.close()
    sys.stdout.write(guard.stdout.read())
    sys.stdout.flush()
    sys.exit(guard.wait())
    """)


@pytest.mark.allow_subprocess
def test_the_guard_is_ready_before_anything_is_applied(bench, monkeypatch):
    """Zwischen "angewandt" und "es gibt einen Rueckweg" darf es keinen
    Moment geben.

    Gemessen an der REIHENFOLGE zweier Zeilen in derselben Datei: der
    Waechter meldet seine Bereitschaft, und danach - nicht davor - laeuft
    `hyprctl`.

    Beides ist echt: der Waechter ist der echte, hinter einem
    Vorschalter, der nur mitschreibt; das Anwenden geht durch
    subprocess.run auf den `hyprctl`-Stellvertreter, den PATH hergibt.
    """
    displays = _displays()
    for key, value in bench["environment"].items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(displays, "guard_command", lambda: [
        sys.executable, "-c", GUARD_PROXY, str(GUARD)])

    attempt = displays.arm_and_apply(
        _layout(displays, 100), _layout(displays, 0), seconds=300)
    try:
        assert applied(bench) == [
            "waechter-bereit",
            "--batch keyword monitor DP-1,1920x1080@60,100x0,1",
        ], ("die Anordnung wurde angewandt, bevor es einen Rueckweg gab")
    finally:
        outcome = attempt.keep()
    assert outcome.kept, outcome.report


@pytest.mark.allow_subprocess
def test_without_a_guard_nothing_is_applied_at_all(bench, monkeypatch):
    """DIE ZUSICHERUNG, DIE SICH AM LEICHTESTEN AUFWEICHEN LIESSE.

    Ein "geht auch ohne" macht aus einer Zusicherung eine Gewohnheit -
    und der eine Lauf ohne Waechter ist dann genau der, in dem der Schirm
    schwarz bleibt.
    """
    displays = _displays()
    for key, value in bench["environment"].items():
        monkeypatch.setenv(key, value)

    ran = []
    monkeypatch.setattr(displays, "guard_command",
                        lambda: [sys.executable, "-c", "print('nein')"])

    with pytest.raises(displays.GuardRefused):
        displays.arm_and_apply(
            _layout(displays, 100), _layout(displays, 0),
            seconds=300, runner=lambda *a, **k: ran.append(a) or None)

    assert ran == [], "es wurde angewandt, obwohl kein Waechter bereit war"
    assert applied(bench) == []


@pytest.mark.allow_subprocess
def test_an_apply_that_fails_is_taken_back_immediately(bench, monkeypatch):
    """`hyprctl --batch` meldet einen Fehler auch dann, wenn ein Teil der
    Zeilen schon durchgegangen ist - ein halb angewandter Schreibtisch
    ist genau der Zustand, fuer den es den Waechter gibt."""
    displays = _displays()
    for key, value in bench["environment"].items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(displays, "guard_command",
                        lambda: [sys.executable, str(GUARD)])

    with pytest.raises(displays.ApplyFailed):
        displays.arm_and_apply(
            _layout(displays, 100), _layout(displays, 0), seconds=300,
            runner=lambda argv, **kwargs: subprocess.CompletedProcess(
                argv, 1, "", "unbekannter Modus"))

    assert wait_for(lambda: applied(bench)), (
        "ein fehlgeschlagenes Anwenden wurde nicht zurueckgenommen")


def _displays():
    import importlib

    sys.path.insert(0, str(SRC))
    try:
        return importlib.import_module("displays")
    finally:
        sys.path.remove(str(SRC))


def _layout(displays, x: int):
    return [displays.Placement("DP-1", "DP-1", True, 1920, 1080, 60.0,
                               x, 0, 1.0, 0)]
