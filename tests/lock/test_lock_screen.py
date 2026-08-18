# SPDX-License-Identifier: GPL-3.0-or-later
"""Sperrt zepos-lock wirklich - und wer sagt das?

DIE FRAGE, AN DER DIESE DATEI HAENGT
    "Gesperrt" und "ein Fenster ist da" sind zwei verschiedene Dinge,
    und eine Zusicherung, die das erste behauptet und das zweite misst,
    faengt genau den Fehler nicht, der zaehlt. Ein Layer-Shell-Overlay
    ganz oben sieht auf jedem Bildschirmfoto wie eine Sperre aus; es gibt
    den Schreibtisch in dem Moment frei, in dem es abstuerzt.

    Deshalb glaubt hier nichts dem Programm. zepos-lock schreibt
    "zepos-lock: gesperrt" auf stdout, und diese Zeile wird als
    BEHAUPTUNG behandelt. Die MESSUNG macht tests/lock/
    session_lock_witness.c: ein unabhaengiger zweiter Client, der selbst
    zu sperren versucht. ext-session-lock-v1 vergibt die Sperre genau
    einmal, also ist seine Absage die Aussage des COMPOSITORS darueber,
    dass die Sitzung zu ist.

    Wie ernst der Unterschied ist, misst
    test_mutation_a_layer_shell_overlay_is_not_a_lock() unten: dasselbe
    Programm mit denselben Ausgaben, nur ohne Protokoll - und der Zeuge
    bekommt die Sperre anstandslos.

WARUM NIE AUF DER SITZUNG DES NUTZERS
    Weil ein Fehlschlag hier den Menschen aussperrt, der die Tests
    gestartet hat, und weil das Protokoll beim Absturz des
    Sperrprogramms ausdruecklich gesperrt BLEIBT. Jeder Lauf geht in ein
    verschachteltes Hyprland mit eigenem XDG_RUNTIME_DIR;
    nested_compositor.refuse_the_real_session() prueft die Umgebung
    JEDES Kindes, bevor es startet.

WARUM JEDER TEST SEINEN EIGENEN COMPOSITOR BEKOMMT
    Aus demselben Grund. Ein Compositor, in dem einmal ein
    Sperrprogramm gestorben ist, bleibt gesperrt - er ist danach fuer
    nichts mehr zu gebrauchen. Ein geteilter Compositor waere ein
    Testlauf, in dem ab dem Absturz-Test alles Weitere "gesperrt" misst,
    ohne dass es noch etwas bedeutete.

WARUM JEDER LAUF DES SPERRPROGRAMMS EIN EIGENES /etc/pam.d BEKOMMT
    Auch die Laeufe, in denen gar kein Passwort getippt wird. Archs
    auth-Stapel fuehrt pam_faillock mit deny=3; ein Versuch gegen das
    echte Konto des Entwicklers kostet ihn zehn Minuten Aussperrung. Der
    Namensraum macht das strukturell unmoeglich statt es zu vermeiden -
    _start_locker() unten startet deshalb IMMER durch `unshare -Urm`.

    Die eine Ausnahme ist der Test unter gtk4-broadwayd: dort endet das
    Programm, bevor es ueberhaupt ein Feld zeigt, und PAM kommt nie ins
    Spiel.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from tests import gtk4_headless
from tests.lock import nested_compositor as nested

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "lock"
HERE = Path(__file__).parent
WITNESS_SOURCE = HERE / "session_lock_witness.c"
FAKE_SOURCE = HERE / "fake_lock_layer_shell.c"

WITNESS_FREE = 0
WITNESS_LOCKED = 1

RIGHT = "das-eine-richtige"
WRONG = "das-eine-falsche"

TOOLS = ("Hyprland", "gcc", "pkg-config", "unshare")


def _why_not() -> str | None:
    missing = nested.missing_tools(*TOOLS)
    if missing:
        return "fehlt auf dieser Maschine: " + ", ".join(missing)
    if nested.host_wayland_socket() is None:
        return ("keine laufende Wayland-Sitzung, in die hinein verschachtelt "
                "werden koennte - Hyprland hat keinen Headless-Schalter")
    return None


requires = pytest.mark.skipif(_why_not() is not None, reason=_why_not() or "")


# --------------------------------------------------------------------
# Prueftisch
# --------------------------------------------------------------------

@pytest.fixture
def compositor():
    instance = nested.NestedHyprland()
    try:
        instance.start()
        yield instance
    finally:
        instance.stop()


@pytest.fixture(scope="module")
def zepos_lock(tmp_path_factory) -> Path:
    """Das ausgelieferte Programm, gebaut mit lock/meson.build.

    Mit meson und nicht mit gcc, damit auch das Bauskript gemessen wird -
    es ist die Stelle, an der gtk4-layer-shell und libpam ERFORDERLICH
    sind. Ein Bau, der ohne sie durchginge, ergaebe ein Programm, das
    entweder nicht sperrt oder nicht prueft.
    """
    if nested.missing_tools("meson", "ninja"):
        pytest.skip("meson oder ninja fehlt")
    build = tmp_path_factory.mktemp("meson")
    setup = subprocess.run(
        ["meson", "setup", str(build / "b"), str(LOCK)],
        capture_output=True, text=True)
    assert setup.returncode == 0, f"meson setup:\n{setup.stdout}{setup.stderr}"
    compile_ = subprocess.run(
        ["ninja", "-C", str(build / "b")], capture_output=True, text=True)
    assert compile_.returncode == 0, (
        f"ninja:\n{compile_.stdout}{compile_.stderr}")
    binary = build / "b" / "zepos-lock"
    assert binary.is_file(), "meson hat kein zepos-lock gebaut"
    return binary


def _pam_directory(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "pamd"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "zepos-lock").write_text(body, encoding="utf-8")
    return directory


def _deny_everything(tmp_path: Path) -> Path:
    """Ein Stapel, der nie aufmacht - fuer jeden Test, der nicht tippt."""
    return _pam_directory(tmp_path, "auth required pam_deny.so\n")


def _accepts(tmp_path: Path, expected: str, log: Path) -> Path:
    """Ein Stapel, der genau eine Zeichenkette annimmt und mitschreibt."""
    checker = tmp_path / "check.sh"
    checker.write_text(
        "#!/bin/sh\n"
        "read -r token\n"
        f"printf '%s\\n' \"$token\" >> {log}\n"
        f"[ \"$token\" = '{expected}' ] && exit 0\n"
        "exit 1\n",
        encoding="utf-8")
    checker.chmod(0o755)
    log.write_text("", encoding="utf-8")
    return _pam_directory(
        tmp_path,
        f"auth required pam_exec.so expose_authtok quiet {checker}\n")


def _start_locker(binary: Path, compositor_, pamd: Path, log: Path,
                  css: str = "/dev/null") -> subprocess.Popen:
    """Startet das Sperrprogramm IM verschachtelten Compositor.

    Der Namensraum ist der Grund, aus dem hier `unshare` und nicht das
    Programm selbst gestartet wird: das gebundene /etc/pam.d gilt nur
    fuer die Prozesse darin, und ausserhalb sieht niemand etwas davon.
    """
    environment = compositor_.environment()
    command = ["unshare", "-Urm", "sh", "-c",
               f"mount --bind '{pamd}' /etc/pam.d && "
               f"exec '{binary}' --css '{css}'"]
    with log.open("wb") as sink:
        return subprocess.Popen(command, env=environment,
                                stdout=sink, stderr=subprocess.STDOUT)


def _wait_for(log: Path, needle: str, timeout: float = 25.0,
              process: subprocess.Popen | None = None) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = log.read_text(encoding="utf-8", errors="replace")
        if needle in text:
            return text
        if process is not None and process.poll() is not None:
            raise AssertionError(
                f"das Programm endete mit {process.returncode}, bevor "
                f"{needle!r} erschien:\n{text}")
        time.sleep(0.05)
    raise AssertionError(
        f"{needle!r} kam in {timeout} s nicht:\n"
        + log.read_text(encoding="utf-8", errors="replace"))


def _ask_the_witness(witness: Path, compositor_) -> int:
    """Fragt den Compositor, ob die Sitzung gesperrt ist."""
    result = subprocess.run([str(witness)], env=compositor_.environment(),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode in (WITNESS_FREE, WITNESS_LOCKED), (
        "der Zeuge konnte nicht antworten - dann ist jede Aussage darueber, "
        f"ob gesperrt ist, ungedeckt:\n{result.stdout}{result.stderr}")
    return result.returncode


def _hyprctl(compositor_, *arguments: str) -> subprocess.CompletedProcess:
    """hyprctl gegen den VERSCHACHTELTEN Compositor.

    Die Instanzkennung wird ausdruecklich gesetzt und XDG_RUNTIME_DIR
    zeigt in das private Verzeichnis, also sucht hyprctl seinen Socket
    nur dort. Ohne beides fiele der Aufruf auf die Sitzung des Nutzers
    zurueck - deshalb bricht der Aufrufer ab, wenn die Kennung nicht
    eindeutig ist, statt es zu versuchen.
    """
    signature = compositor_.signature()
    assert signature is not None, (
        "die Instanzkennung des verschachtelten Hyprland ist nicht eindeutig")
    return subprocess.run(
        ["hyprctl", *arguments],
        env=compositor_.environment(HYPRLAND_INSTANCE_SIGNATURE=signature),
        capture_output=True, text=True, timeout=60)


def _type(compositor_, text: str) -> None:
    environment = compositor_.environment()
    subprocess.run(["wtype", "--", text], env=environment,
                   capture_output=True, text=True, timeout=60, check=True)
    subprocess.run(["wtype", "-k", "Return"], env=environment,
                   capture_output=True, text=True, timeout=60, check=True)


# --------------------------------------------------------------------
# 0. Der Wachhund vor allem anderen
# --------------------------------------------------------------------

def test_a_child_may_never_be_pointed_at_the_users_own_session(tmp_path):
    """Die Zusicherung, die diesen ganzen Zweig ueberhaupt fahrbar macht.

    Sie wird hier absichtlich als ERSTES gebrochen: eine Umgebung, die
    auf das Laufzeitverzeichnis der laufenden Sitzung zeigt, muss
    refuse_the_real_session() zum Abbruch bringen. Tut sie es nicht,
    ist jeder Test darunter ein Wuerfelwurf mit der Sitzung des
    Menschen, der ihn gestartet hat.
    """
    host_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not host_runtime:
        pytest.skip("ohne XDG_RUNTIME_DIR gibt es keine Sitzung zu schuetzen")

    with pytest.raises(AssertionError, match="Laufzeitverzeichnis der Sitzung"):
        nested.refuse_the_real_session(
            {"XDG_RUNTIME_DIR": host_runtime, "WAYLAND_DISPLAY": "wayland-1"})

    with pytest.raises(AssertionError, match="ohne XDG_RUNTIME_DIR"):
        nested.refuse_the_real_session({"WAYLAND_DISPLAY": "wayland-1"})

    # Und der absolute Pfad auf denselben Socket, aus einem harmlos
    # aussehenden fremden Laufzeitverzeichnis heraus.
    host_socket = nested.host_wayland_socket()
    if host_socket is not None:
        with pytest.raises(AssertionError, match="Socket der"):
            nested.refuse_the_real_session({
                "XDG_RUNTIME_DIR": str(tmp_path),
                "WAYLAND_DISPLAY": str(host_socket)})

    # Die Gegenrichtung: eine ordentliche Umgebung darf durch, sonst
    # waere die Pruefung mit `assert False` erfuellt.
    (tmp_path / "wayland-9").touch()
    nested.refuse_the_real_session(
        {"XDG_RUNTIME_DIR": str(tmp_path), "WAYLAND_DISPLAY": "wayland-9"})


# --------------------------------------------------------------------
# 1. Das Toolkit
# --------------------------------------------------------------------

@requires
@pytest.mark.allow_subprocess
def test_the_binary_stands_on_gtk4_and_never_loads_gtk3(zepos_lock):
    """Die Entscheidung vom 11.08.2026, am fertigen Objekt gemessen.

    Zwei Werkzeuge fuer zwei Fragen, wie in packaging/zepos-logout/
    PKGBUILD begruendet: readelf sagt, was DIESES Objekt angefordert hat,
    ldd sagt, was beim Start wirklich geladen wird - und nur ldd sieht
    ein libgtk-3, das eine Bibliothek dazwischen mitbringt.

    Die dritte Zeile gibt es nur hier: ohne libpam waere dieses Programm
    ein Bildschirm, der ein Passwortfeld ZEIGT.
    """
    needed = subprocess.run(["objdump", "-p", str(zepos_lock)],
                            capture_output=True, text=True, check=True).stdout
    required = [line.split()[1] for line in needed.splitlines()
                if "NEEDED" in line]

    assert any(name.startswith("libgtk-4") for name in required), (
        f"nicht gegen GTK4 gelinkt: {required}")
    assert any("gtk4-layer-shell" in name for name in required), (
        "nicht gegen gtk4-layer-shell gelinkt - dort steckt "
        f"gtk4-session-lock.h, der einzige Weg von GTK4 zum Protokoll: {required}")
    assert any(name.startswith("libpam") for name in required), (
        f"nicht gegen libpam gelinkt - es prueft dann nichts: {required}")

    loaded = subprocess.run(["ldd", str(zepos_lock)],
                            capture_output=True, text=True, check=True).stdout
    assert "libgtk-3" not in loaded, (
        "libgtk-3 wird beim Start geladen:\n"
        + "\n".join(line for line in loaded.splitlines() if "gtk" in line))


# --------------------------------------------------------------------
# 1b. Ohne das Protokoll wird NICHT gesperrt, und auch nicht so getan
# --------------------------------------------------------------------
#
# Der einzige Test dieser Datei, der KEIN verschachteltes Hyprland
# braucht - und deshalb auch dort laeuft, wo es keine Wayland-Sitzung
# gibt. gtk4-broadwayd ist GTKs eigener HTML5-Anzeigeserver: er kommt mit
# dem Paket gtk4, braucht keine GPU und spricht ext-session-lock-v1
# nicht. Damit ist er genau der Compositor, an dem sich zeigt, was
# passiert, wenn das Protokoll fehlt.

@pytest.mark.allow_subprocess
def test_without_the_protocol_it_refuses_instead_of_pretending(zepos_lock,
                                                               tmp_path):
    """Der Rueckfall, den es nicht gibt - und der Grund dafuer.

    Ein Programm, das ohne ext-session-lock-v1 ein Layer-Shell-Fenster
    zeigt, sieht in jedem Bild und in jedem Test wie ein
    Sperrbildschirm aus und ist keiner: stirbt es, liegt der
    Schreibtisch offen. Also endet zepos-lock hier mit einer Meldung.

    Zwei Dinge werden geprueft, und das zweite ist das wichtigere: der
    Rueckgabewert ist NICHT 0. `zepos-lock` steht in einer
    Tastenbindung, und ein Programm, das mit 0 endet, ohne gesperrt zu
    haben, ist eins, dem man das nicht ansieht.

    GEMESSEN am 12.08.2026 gegen gtk4-broadwayd aus GTK 4.22.4.
    """
    command = gtk4_headless.broadwayd()
    if command is None:
        pytest.skip("gtk4-broadwayd fehlt")

    display = nested.a_free_broadway_display()
    runtime = tmp_path / "rt"
    runtime.mkdir()
    runtime.chmod(0o700)
    server, _socket = gtk4_headless.start_broadwayd(command, runtime, display)
    try:
        result = subprocess.run(
            [str(zepos_lock), "--css", "/dev/null"],
            env={"PATH": "", "HOME": str(tmp_path),
                 "XDG_RUNTIME_DIR": str(runtime),
                 "XDG_CONFIG_HOME": str(tmp_path / "config"),
                 "GDK_BACKEND": "broadway",
                 "BROADWAY_DISPLAY": f":{display}",
                 "GTK_A11Y": "none", "LC_ALL": "C"},
            capture_output=True, text=True, timeout=120)
    finally:
        gtk4_headless.stop_broadwayd(server)

    assert result.returncode != 0, (
        "ohne das Protokoll endet das Programm mit 0 - eine Tastenbindung "
        f"kann dann nicht sehen, dass nichts gesperrt wurde:\n{result.stdout}")
    assert "ext-session-lock-v1" in result.stderr, (
        "es sagt nicht, was fehlt:\n" + result.stderr + result.stdout)
    assert "NICHT gesperrt" in result.stderr, (
        "es sagt nicht, dass nicht gesperrt ist:\n" + result.stderr)
    assert "zepos-lock: gesperrt" not in result.stdout, (
        "es behauptet gesperrt zu haben, ohne das Protokoll zu haben")


# --------------------------------------------------------------------
# 2. Sperrt es
# --------------------------------------------------------------------

@requires
@pytest.mark.allow_subprocess
def test_the_compositor_says_the_session_is_locked(compositor, zepos_lock,
                                                   tmp_path):
    """Der Zeuge, dreimal befragt: vorher frei, waehrend zu, danach frei.

    Alle drei Antworten werden gebraucht. "Waehrend zu" allein waere auch
    von einem Compositor wahr, der aus einem anderen Grund keine Sperre
    mehr vergibt; "vorher frei" schliesst das aus. Und "danach frei"
    zeigt, dass dieses Programm die Sperre auch wieder ABGIBT - ein
    Sperrbildschirm, der sie behaelt, hat den Nutzer ausgesperrt.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    log = tmp_path / "lock.log"
    seen = tmp_path / "gesehen.log"
    pamd = _accepts(tmp_path, RIGHT, seen)

    assert _ask_the_witness(witness, compositor) == WITNESS_FREE, (
        "der verschachtelte Compositor war schon gesperrt, bevor irgendetwas "
        "lief - dann sagt der Rest dieses Tests nichts")

    locker = _start_locker(zepos_lock, compositor, pamd, log)
    try:
        _wait_for(log, "zepos-lock: gesperrt", process=locker)
        assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED, (
            "das Programm behauptet gesperrt zu haben, und der Compositor "
            "gibt die Sperre einem zweiten Client - es ist also NICHT "
            "gesperrt")

        _type(compositor, RIGHT)
        assert locker.wait(timeout=60) == 0, (
            "mit dem richtigen Passwort endete das Programm nicht sauber:\n"
            + log.read_text(encoding="utf-8", errors="replace"))
    finally:
        if locker.poll() is None:                     # pragma: no cover
            locker.kill()
            locker.wait(timeout=30)

    assert seen.read_text(encoding="utf-8").split() == [RIGHT], (
        "PAM hat nicht das getippte Wort gesehen - dann hat der Lauf oben "
        "etwas anderes gemessen als die Kette vom Feld bis zum Modul")
    assert _ask_the_witness(witness, compositor) == WITNESS_FREE, (
        "nach dem Entsperren gibt der Compositor die Sperre nicht wieder her")


@requires
@pytest.mark.allow_subprocess
def test_a_wrong_password_leaves_the_session_locked(compositor, zepos_lock,
                                                    tmp_path):
    """Und man sieht, DASS versucht wurde.

    Ohne die Zeile "abgelehnt" waere dieser Test wertlos: von aussen
    sieht ein abgewiesener Versuch genauso aus wie einer, bei dem die
    Tasten nie angekommen sind, und beides laesst die Sitzung gesperrt.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    log = tmp_path / "lock.log"
    seen = tmp_path / "gesehen.log"
    pamd = _accepts(tmp_path, RIGHT, seen)

    locker = _start_locker(zepos_lock, compositor, pamd, log)
    try:
        _wait_for(log, "zepos-lock: gesperrt", process=locker)

        _type(compositor, WRONG)
        _wait_for(log, "zepos-lock: abgelehnt", process=locker)
        assert seen.read_text(encoding="utf-8").split() == [WRONG], (
            "PAM hat das falsche Wort nicht gesehen")
        assert locker.poll() is None, "das Programm endete nach einem "\
            "falschen Passwort"
        assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED, (
            "nach einem falschen Passwort ist die Sitzung offen")

        # Und danach geht es weiter - ein Sperrbildschirm, der nach einem
        # Tippfehler nichts mehr annimmt, sperrt den Nutzer aus.
        _type(compositor, RIGHT)
        assert locker.wait(timeout=60) == 0, log.read_text(
            encoding="utf-8", errors="replace")
    finally:
        if locker.poll() is None:                     # pragma: no cover
            locker.kill()
            locker.wait(timeout=30)

    assert seen.read_text(encoding="utf-8").split() == [WRONG, RIGHT]
    assert _ask_the_witness(witness, compositor) == WITNESS_FREE


@requires
@pytest.mark.allow_subprocess
def test_the_session_stays_locked_when_the_program_is_killed(
        compositor, zepos_lock, tmp_path):
    """Was beim Absturz passiert, gemessen statt geglaubt.

    ext-session-lock-v1.xml, Zeile 111: "If the client dies while the
    session is locked, the compositor must not unlock the session in
    response." Hier wird nachgesehen, ob Hyprland 0.55.4 sich daran
    haelt - mit SIGKILL, dem einzigen Signal, das ein Programm nicht
    abfangen kann, und damit dem nachstellbaren Absturz.

    Es ist zugleich der Grund fuer die Bauart von lock/zepos-lock.c:
    weil dieser Zustand nicht zuruecknehmbar ist, passiert dort alles,
    was fehlschlagen kann, VOR dem Sperren.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    log = tmp_path / "lock.log"
    pamd = _deny_everything(tmp_path)

    locker = _start_locker(zepos_lock, compositor, pamd, log)
    _wait_for(log, "zepos-lock: gesperrt", process=locker)
    assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED

    # unshare -Urm ist der Elternprozess; das Sperrprogramm haengt
    # darunter. Deshalb wird die ganze Gruppe erschlagen, sonst ueberlebt
    # das Kind seinen Vater und haelt die Sperre weiter - was den Test
    # bestehen liesse, ohne dass er den Absturz gemessen haette.
    locker.send_signal(signal.SIGKILL)
    locker.wait(timeout=30)
    subprocess.run(["pkill", "-9", "-f", f"{zepos_lock} --css"],
                   capture_output=True)
    time.sleep(2)

    assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED, (
        "nach dem Tod des Sperrprogramms gibt der Compositor die Sitzung "
        "frei - dann waere jeder Absturz ein offener Schreibtisch")


@requires
@pytest.mark.allow_subprocess
def test_the_lock_surface_is_not_a_layer_shell_surface(compositor, zepos_lock,
                                                       tmp_path):
    """Warum es hier keinen Glaseffekt gibt, technisch nachgesehen.

    `layerrule` in der Hyprland-Vorlage spricht eine Flaeche ueber ihren
    Layer-Shell-Namensraum an. Eine ext_session_lock_surface_v1 hat
    keinen; sie steht in `hyprctl layers` gar nicht. Eine Regel fuer
    diesen Bildschirm koennte also nicht greifen, und die Entscheidung
    gegen Glas ist damit nicht nur eine Frage des Zwecks.

    Der Aufruf ist LESEND und geht an den verschachtelten Compositor -
    seine Instanzkennung wird dafuer erst gesucht und der Test
    uebersprungen, wenn sie nicht eindeutig ist. `hyprctl layers`
    veraendert nichts.
    """
    signature = compositor.signature()
    if signature is None:
        pytest.skip("die Instanzkennung des verschachtelten Hyprland ist "
                    "nicht eindeutig - dieser Test wuerde sonst den falschen "
                    "Compositor fragen")

    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    log = tmp_path / "lock.log"
    locker = _start_locker(zepos_lock, compositor, _deny_everything(tmp_path),
                           log)
    try:
        _wait_for(log, "zepos-lock: gesperrt", process=locker)
        layers = subprocess.run(
            ["hyprctl", "layers"],
            env=compositor.environment(HYPRLAND_INSTANCE_SIGNATURE=signature),
            capture_output=True, text=True, timeout=60)
        assert layers.returncode == 0, layers.stdout + layers.stderr
        assert "zepos-lock" not in layers.stdout, (
            "der Sperrbildschirm steht als Layer-Shell-Flaeche da:\n"
            + layers.stdout)
        # Und er sperrt dabei wirklich - sonst waere "steht nicht in
        # layers" auch von einem Programm wahr, das gar nichts zeichnet.
        assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED
    finally:
        locker.kill()
        locker.wait(timeout=30)


@requires
@pytest.mark.allow_subprocess
def test_it_locks_even_when_the_stylesheet_is_missing(compositor, zepos_lock,
                                                      tmp_path):
    """Der Ausfall, der nicht in eine offene Sitzung fuehren darf.

    Das Stylesheet ist die einzige erzeugte Datei, die dieser Bildschirm
    liest. Faellt sie weg - ein Paket halb eingespielt, ein Heimatverz-
    eichnis frisch -, muss er trotzdem sperren und sagen, was fehlt.
    Ein Sperrbildschirm, der wegen einer CSS-Datei nicht erscheint, ist
    der Fehler, der einen Schreibtisch offen stehen laesst.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    log = tmp_path / "lock.log"
    fehlt = tmp_path / "gibt-es-nicht.css"

    locker = _start_locker(zepos_lock, compositor, _deny_everything(tmp_path),
                           log, css=str(fehlt))
    try:
        text = _wait_for(log, "zepos-lock: gesperrt", process=locker)
        assert "generate_config.sh -lock-style" in text, (
            "es sperrt ungestylt und sagt nicht, welcher Befehl die Datei "
            f"schreibt:\n{text}")
        assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED
    finally:
        locker.kill()
        locker.wait(timeout=30)


@requires
@pytest.mark.allow_subprocess
def test_it_locks_even_when_the_backdrop_image_is_corrupt(compositor,
                                                          zepos_lock, tmp_path):
    """Die eine Stelle, an der "alles vor dem Sperren" NICHT ganz stimmt.

    Der Kopf von lock/zepos-lock.c sagt, alles Fehlschlagbare passiere
    vor dem Sperren, und fuer das Stylesheet gilt das auch: es wird
    gelesen und geparst, bevor lock() laeuft. Das BILD darin nicht -
    GTK4 laedt ein CSS-url()-Bild erst beim ersten Zeichnen, und das ist
    nach dem Sperren.

    Also wird nachgesehen, was ein kaputtes PNG dort anrichtet, statt es
    zu behaupten. GEMESSEN am 12.08.2026: GTK laesst die Regel fallen,
    der Grund darunter bleibt stehen, das Programm lebt weiter und der
    Compositor bestaetigt die Sperre. Ein Bild, das zepos-config
    ausliefert und das jemand beschaedigt, kostet also die Tapete und
    nicht die Sitzung.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)

    broken_png = tmp_path / "kaputt.png"
    broken_png.write_bytes(b"\x89PNG\r\n\x1a\n voellig kaputt, kein IHDR")
    css = tmp_path / "kaputt.css"
    css.write_text(
        "window#lock {\n"
        "    background-color: #08262C;\n"
        f'    background-image: url("{broken_png}");\n'
        "    background-size: cover;\n"
        "}\n", encoding="utf-8")

    log = tmp_path / "lock.log"
    locker = _start_locker(zepos_lock, compositor, _deny_everything(tmp_path),
                           log, css=str(css))
    try:
        _wait_for(log, "zepos-lock: gesperrt", process=locker)
        assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED, (
            "ein kaputtes Hintergrundbild kostet die Sperre")
        assert locker.poll() is None, (
            "das Programm ist am Hintergrundbild gestorben - und weil das "
            "Protokoll die Sitzung dann gesperrt LAESST, waere das eine "
            "Aussperrung:\n"
            + log.read_text(encoding="utf-8", errors="replace"))
    finally:
        locker.kill()
        locker.wait(timeout=30)


@requires
@pytest.mark.allow_subprocess
def test_every_monitor_gets_its_own_lock_surface(compositor, zepos_lock,
                                                 tmp_path):
    """Zwei Bildschirme, und die Sperre muss BEIDE nehmen.

    Der Fehler, den zepos-logout in seinem eigenen Kopf beschreibt -
    eine Maske, die einen Schirm von dreien nimmt - waere hier
    schlimmer: ein Sperrbildschirm auf Monitor 1, waehrend Monitor 2 den
    Schreibtisch zeigt.

    WARUM DAS ANDERS GEMESSEN WIRD ALS BEI DER ABMELDEMASKE
        Weil das Protokoll die Antwort selbst gibt. ext-session-lock-v1
        schickt `locked` erst, wenn auf JEDEM Ausgang eine Lock-Surface
        liegt. Bleibt einer ohne, kommt die Zeile "zepos-lock: gesperrt"
        nie - dieser Test faellt dann in _wait_for() und nicht an einer
        Zusicherung ueber Fensterzahlen, die man auch falsch zaehlen
        kann.

    Der zweite Ausgang ist ein Headless-Ausgang, den Hyprland auf
    Zuruf anlegt. Er kostet keine Hardware und ist fuer den Compositor
    ein Monitor wie jeder andere.
    """
    created = _hyprctl(compositor, "output", "create", "headless")
    assert created.returncode == 0, created.stdout + created.stderr

    monitors = _hyprctl(compositor, "-j", "monitors")
    assert monitors.returncode == 0, monitors.stdout + monitors.stderr
    assert monitors.stdout.count('"name"') >= 2, (
        "der zweite Ausgang ist nicht entstanden - dann misst dieser Test "
        f"denselben Fall wie die anderen:\n{monitors.stdout}")

    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    log = tmp_path / "lock.log"
    locker = _start_locker(zepos_lock, compositor, _deny_everything(tmp_path),
                           log)
    try:
        _wait_for(log, "zepos-lock: gesperrt", process=locker)
        assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED
    finally:
        locker.kill()
        locker.wait(timeout=30)


@requires
@pytest.mark.allow_subprocess
def test_a_monitor_that_appears_during_the_lock_gets_a_surface_too(
        compositor, zepos_lock, tmp_path):
    """Jemand dockt den Rechner an, WAEHREND er gesperrt ist.

    Das ist der Weg mit dem schlimmsten Ausgang im ganzen Entwurf.
    ext-session-lock-v1 verlangt fuer JEDEN Ausgang eine Lock-Surface;
    ein Client, der auf einen neuen Ausgang nicht reagiert oder dabei
    einen Protokollfehler baut, wird vom Compositor GETOETET - und weil
    die Sperre den Tod des Clients ueberlebt (siehe der Test darueber),
    waere das eine Aussperrung ohne Weg zurueck.

    Gemessen wird deshalb nicht, dass ein Fenster erscheint, sondern
    dass das Programm den Anschluss UEBERLEBT und danach immer noch
    aufschliessen kann - das letzte Stueck beweist, dass alle Flaechen
    in Ordnung sind und die Eingabe noch ankommt.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    seen = tmp_path / "gesehen.log"
    pamd = _accepts(tmp_path, RIGHT, seen)
    log = tmp_path / "lock.log"

    locker = _start_locker(zepos_lock, compositor, pamd, log)
    try:
        _wait_for(log, "zepos-lock: gesperrt", process=locker)

        created = _hyprctl(compositor, "output", "create", "headless")
        assert created.returncode == 0, created.stdout + created.stderr
        time.sleep(2)

        assert locker.poll() is None, (
            "das Sperrprogramm hat den neuen Monitor nicht ueberlebt - und "
            "die Sitzung bleibt nach dem Protokoll trotzdem gesperrt:\n"
            + log.read_text(encoding="utf-8", errors="replace"))
        assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED

        _type(compositor, RIGHT)
        assert locker.wait(timeout=60) == 0, (
            "nach dem Anschluss nimmt der Bildschirm kein Passwort mehr an:\n"
            + log.read_text(encoding="utf-8", errors="replace"))
    finally:
        if locker.poll() is None:                     # pragma: no cover
            locker.kill()
            locker.wait(timeout=30)

    assert seen.read_text(encoding="utf-8").split() == [RIGHT]
    assert _ask_the_witness(witness, compositor) == WITNESS_FREE


# --------------------------------------------------------------------
# 3. Die Mutationen
# --------------------------------------------------------------------

def _mutate(tmp_path: Path, name: str, changes: list[tuple[str, str]]) -> Path:
    source = (LOCK / "zepos-lock.c").read_text(encoding="utf-8")
    for old, new in changes:
        assert source.count(old) == 1, (
            f"die Mutation {name} findet ihre Stelle nicht "
            f"({source.count(old)}x): {old[:70]!r}")
        source = source.replace(old, new)
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    mutated = directory / "zepos-lock.c"
    mutated.write_text(source, encoding="utf-8")
    return nested.build(name, [mutated, LOCK / "zepos-lock-pam.c"], directory)


@requires
@pytest.mark.allow_subprocess
def test_mutation_a_layer_shell_overlay_is_not_a_lock(compositor, tmp_path):
    """MUTATION 5, UND DIE WICHTIGSTE VON ALLEN.

    tests/lock/fake_lock_layer_shell.c ist der Sperrbildschirm, den man
    baut, wenn man denkt, ein Fenster ganz oben sei eine Sperre: ein
    Overlay auf der obersten Ebene, ueber alles gespannt, mit exklusiver
    Tastatur, und mit derselben Zeile "zepos-lock: gesperrt" auf stdout.

    Ein Test, der auf diese Zeile hoert oder ein Bildschirmfoto
    vergleicht, kann ihn nicht vom echten unterscheiden. Der Zeuge kann:
    er bekommt die Sperre anstandslos, weil niemand sie haelt.

    Hier wird also gemessen, dass die MESSMETHODE der Tests darueber den
    Unterschied ueberhaupt sieht.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    fake = nested.build("fake_lock", [FAKE_SOURCE], tmp_path)
    log = tmp_path / "fake.log"

    with log.open("wb") as sink:
        process = subprocess.Popen([str(fake)], env=compositor.environment(),
                                   stdout=sink, stderr=subprocess.STDOUT)
    try:
        _wait_for(log, "zepos-lock: gesperrt", process=process)
        assert _ask_the_witness(witness, compositor) == WITNESS_FREE, (
            "der Zeuge haelt ein Layer-Shell-Overlay fuer eine Sperre - dann "
            "misst er nicht, was die Tests darueber behaupten")
    finally:
        process.kill()
        process.wait(timeout=30)


@requires
@pytest.mark.allow_subprocess
def test_mutation_unlocking_without_pams_yes_is_caught(compositor, tmp_path):
    """MUTATION 6: aufgeschlossen wird unabhaengig von der Antwort.

    Der Ausfall, der jemanden HEREINLAESST. Ein falsches Passwort muss
    diesen Mutanten oeffnen - und
    test_a_wrong_password_leaves_the_session_locked() oben faellt
    darueber.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    seen = tmp_path / "gesehen.log"
    pamd = _accepts(tmp_path, RIGHT, seen)
    log = tmp_path / "lock.log"
    mutant = _mutate(tmp_path, "mut_always_open",
                     [("    if (attempt->result.accepted) {",
                       "    if (1) {")])

    locker = _start_locker(mutant, compositor, pamd, log)
    try:
        _wait_for(log, "zepos-lock: gesperrt", process=locker)
        assert _ask_the_witness(witness, compositor) == WITNESS_LOCKED

        _type(compositor, WRONG)
        assert locker.wait(timeout=60) == 0, (
            "der Mutant sollte mit einem FALSCHEN Passwort aufmachen und tat "
            "es nicht:\n" + log.read_text(encoding="utf-8", errors="replace"))
    finally:
        if locker.poll() is None:                     # pragma: no cover
            locker.kill()
            locker.wait(timeout=30)

    assert seen.read_text(encoding="utf-8").split() == [WRONG], (
        "der Mutant hat gar nicht erst gefragt - dann bricht diese Mutation "
        "etwas anderes als gedacht")
    assert _ask_the_witness(witness, compositor) == WITNESS_FREE, (
        "der Mutant hat mit falschem Passwort nicht wirklich aufgeschlossen")


@requires
@pytest.mark.allow_subprocess
def test_mutation_a_missing_stylesheet_that_stops_the_lock_is_caught(
        compositor, tmp_path):
    """MUTATION 7: das fehlende Stylesheet wird toedlich.

    Der Ausfall, der jemanden AUSSPERRT - beziehungsweise hier: den
    Schreibtisch offen stehen laesst. Er sieht harmlos aus ("ohne Stil
    starte ich lieber nicht") und ist die Umkehrung der ganzen Bauart.
    test_it_locks_even_when_the_stylesheet_is_missing() oben muss
    darueber fallen.
    """
    witness = nested.build("witness", [WITNESS_SOURCE], tmp_path)
    log = tmp_path / "lock.log"
    mutant = _mutate(
        tmp_path, "mut_css_fatal",
        [("    if (!zep_load_css(css_path, &error)) {\n"
          "        g_printerr(",
          "    if (!zep_load_css(css_path, &error)) {\n"
          "        return ZEP_EXIT_NOT_LOCKED;\n"
          "    }\n"
          "    if (0) {\n"
          "        g_printerr(")])

    locker = _start_locker(mutant, compositor, _deny_everything(tmp_path), log,
                           css=str(tmp_path / "gibt-es-nicht.css"))
    try:
        assert locker.wait(timeout=60) != 0, (
            "der Mutant sollte ohne Stylesheet gar nicht erst sperren")
        assert _ask_the_witness(witness, compositor) == WITNESS_FREE, (
            "der Mutant hat trotz Abbruch gesperrt - dann bricht diese "
            "Mutation etwas anderes als gedacht")
    finally:
        if locker.poll() is None:                     # pragma: no cover
            locker.kill()
            locker.wait(timeout=30)
