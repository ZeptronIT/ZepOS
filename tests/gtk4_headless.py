# SPDX-License-Identifier: GPL-3.0-or-later
"""Eine GTK4-Anzeige, wo keine ist - fuer jeden Test, der Widgets baut.

WOHER DAS KOMMT
    tests/installer/test_gui_headless.py hat das hier zuerst gebraucht
    und in seinem Kopf begruendet. Als tests/menu/ dieselbe Anzeige
    brauchte, gab es zwei Moeglichkeiten: das Verfahren ein zweites Mal
    hinschreiben, oder es einmal hinschreiben. Zwei Kopien einer
    Anzeigeserver-Startroutine sind zwei Kopien, die auseinanderlaufen,
    sobald jemand eine davon anfasst - und die, die nicht angefasst
    wurde, ist dann die, die still etwas anderes misst.

DIE DREI MESSUNGEN, DIE DAS VERFAHREN ENTSCHIEDEN HABEN
      * `gi` fehlt in .venv, ist aber systemweit da. gi_interpreter()
        sucht eine lauffaehige Kombination, statt eine anzunehmen.
      * GTK4-Widgets ohne Anzeige zu bauen wirft keine Ausnahme, es
        SEGFAULTet (Exit 139). Innerhalb des pytest-Prozesses waere das
        das Ende der Sitzung ohne Bericht - deshalb laeuft jede
        GTK-Zeile in einem Kind.
      * gtk4-broadwayd ist GTKs eigener HTML5-Anzeigeserver. Er kommt
        mit dem Paket gtk4, braucht kein X, kein Wayland, keine GPU und
        keine Hardware, und er legt seinen Socket dorthin, wohin
        XDG_RUNTIME_DIR zeigt - also einen je Test unter tmp_path.

    Xvfb, die uebliche Antwort, ist hier nicht installiert und waere eine
    neue Abhaengigkeit; broadway ist auf jeder Maschine da, die GTK4
    ueberhaupt ausfuehren kann.
"""
from __future__ import annotations

import os
import shutil
import socket as socketlib
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

_PROBE_TEMPLATE = (
    "import gi;"
    "{requires}"
    "from gi.repository import {names};"
    "print('gi-ok')"
)


def _candidates() -> list[tuple[str, list[str]]]:
    """Interpreter samt zusaetzlicher sys.path-Eintraege, bester zuerst.

    Die virtuelle Umgebung ist ohne include-system-site-packages gebaut,
    sieht das systemweite PyGObject also nicht - sie IST aber derselbe
    Interpreter, aus demselben /usr/bin/python3, also laedt die
    kompilierte `gi`-Erweiterung des Systems hinein, sobald der Pfad
    dazukommt. Ihn vorzuziehen haelt das Kind auf genau dem Python, auf
    dem auch die Suite laeuft. /usr/bin/python3 ist der Rueckfall fuer
    einen Checkout, dessen venv aus einem anderen Python gebaut wurde.
    """
    system_site = sysconfig.get_paths(
        "posix_prefix", vars={"base": sys.base_prefix, "platbase": sys.base_prefix}
    )
    extras = [system_site["purelib"], system_site["platlib"]]
    return [
        (sys.executable, []),
        (sys.executable, [path for path in dict.fromkeys(extras) if path]),
        ("/usr/bin/python3", []),
    ]


def gi_interpreter(namespaces: dict[str, str]) -> tuple[str, list[str]] | None:
    """Ein Interpreter, der diese Typbibliotheken laden kann - oder None.

    `namespaces` ist {"Gtk": "4.0", "Adw": "1"} und so weiter. Gepruefte
    Frage statt angenommener: ein Kind, das an gi.require_version
    scheitert, waere sonst ein Testfehler ueber etwas, das gar nicht
    getestet wurde.
    """
    probe = _PROBE_TEMPLATE.format(
        requires="".join(f"gi.require_version({name!r},{version!r});"
                         for name, version in namespaces.items()),
        names=", ".join(sorted(namespaces)),
    )
    for executable, extra in _candidates():
        if not Path(executable).exists():
            continue
        environment = {"PATH": ""}
        if extra:
            environment["PYTHONPATH"] = os.pathsep.join(extra)
        try:
            result = subprocess.run(
                [executable, "-c", probe],
                env=environment, capture_output=True, text=True, timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and "gi-ok" in result.stdout:
            return executable, extra
    return None


def broadwayd() -> str | None:
    return shutil.which("gtk4-broadwayd")


def refuse_a_foreign_display(display: int) -> None:
    """Abbrechen, wenn die Anzeigenummer auf dieser Maschine schon belegt ist.

    GEMESSEN AM 11.08.2026, UND ES HAT EINEN NACHMITTAG GEKOSTET
        Ein verwaister /run/user/1000/broadway22.socket - liegengeblieben
        aus einem Handversuch, kein Prozess hielt ihn mehr - liess jeden
        Lauf auf Anzeige :21 haengen, obwohl XDG_RUNTIME_DIR des Kindes
        auf ein eigenes Verzeichnis unter tmp_path zeigte und der eigene
        broadwayd dort sauber lauschte. Das Kind baute sein Fenster,
        bediente es richtig, schrieb seine Spur - und endete dann nicht
        mehr: vier Threads im futex, 120 Sekunden bis zur Zeitgrenze von
        subprocess.run, kein Wort darueber, warum.

        :22 und :300 liefen im selben Moment in 0,2 Sekunden durch. Nach
        `rm /run/user/1000/broadway22.socket` auch :21.

    Die Nummer ist also ein maschinenweiter Name, egal was
    XDG_RUNTIME_DIR sagt. Ein Test, der darueber stolpert, muss es sagen
    und nicht warten - deshalb diese Pruefung vor dem Start.
    """
    machine_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not machine_runtime:
        return
    stale = Path(machine_runtime) / f"broadway{display + 1}.socket"
    if stale.exists():
        raise AssertionError(
            f"{stale} gibt es schon. Die Anzeigenummer :{display} ist auf "
            "dieser Maschine belegt - ein laufender oder ein verwaister "
            "gtk4-broadwayd. Der GTK-Client faende ihn statt des Servers "
            "dieses Tests und der Lauf bliebe am Ende haengen, ohne zu "
            "sagen warum. Entweder den Prozess beenden und die Datei "
            "loeschen, oder dem Test eine andere Nummer geben.")


def a_free_port() -> int:
    """Eine Portnummer, die in diesem Moment frei ist.

    WARUM NICHT `--port 0`, WAS HIER STAND
        Weil es nicht tut, was der Kommentar behauptet hat. Er sagte,
        die Null lasse den Kern den Port waehlen. GEMESSEN am 11.08.2026,
        als zwei Testlaeufe gleichzeitig auf dieser Maschine liefen:

            Listening on .../broadway13.socket
            Unable to listen to 127.0.0.1:8092:
            Error binding to address 127.0.0.1:8092: Address already in use

        8092 ist 8080 + 12, also die Vorgabe fuer Anzeige :12 - broadwayd
        rechnet den Port aus der Anzeigenummer aus und beachtet die Null
        nicht. Der Unix-Socket war zu diesem Zeitpunkt schon da; der
        Prozess ist trotzdem gestorben, und zwei Tests des graphischen
        Installers sind mit ihm gefallen.

        Ueber HTTP verbindet sich hier nie etwas - der GTK-Client nimmt
        den Unix-Socket. Der Port ist reine Nebenwirkung, und genau
        deshalb darf er nicht das sein, woran ein Lauf scheitert.

    Die Luecke zwischen close() und dem Start von broadwayd ist ein
    Rennen, und sie ist hier trotzdem die richtige Antwort: sie ist
    Millisekunden lang und trifft eine Nummer, die der Kern gerade als
    frei ausgewaehlt hat, statt einer festen, die auf jeder Maschine
    dieselbe ist.
    """
    with socketlib.socket(socketlib.AF_INET, socketlib.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_broadwayd(command: str, runtime_dir: Path, display: int):
    """Ein privater HTML5-Anzeigeserver, und der Socket, auf dem er lauscht.

    Der HTTP-Port kommt aus a_free_port(); siehe dort, warum nicht aus
    broadwayd selbst. Der GTK-Client nimmt ohnehin den Unix-Socket,
    dessen Namen broadwayd aus XDG_RUNTIME_DIR und der Anzeigenummer
    bildet.
    """
    refuse_a_foreign_display(display)
    socket = runtime_dir / f"broadway{display + 1}.socket"
    process = subprocess.Popen(
        [command, "--port", str(a_free_port()),
         "--address", "127.0.0.1", f":{display}"],
        env={"XDG_RUNTIME_DIR": str(runtime_dir), "PATH": ""},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if socket.exists():
            return process, socket
        if process.poll() is not None:
            raise AssertionError(
                "gtk4-broadwayd exited before it opened its socket:\n"
                + (process.stdout.read() if process.stdout else ""))
        time.sleep(0.05)
    process.terminate()
    raise AssertionError(f"gtk4-broadwayd never created {socket}")


def stop_broadwayd(process) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:                       # pragma: no cover
        process.kill()
