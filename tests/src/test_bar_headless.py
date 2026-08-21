# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Leiste und das Dock, gebaut und gemessen - auf einer echten Anzeige.

WAS DAS SCHLIESST
    Alle anderen Zusicherungen ueber die Leiste sind Textsuchen in einer
    Vorlage. Sie koennen sagen, dass ein `case "battery":` dasteht; sie
    koennen nicht sagen, ob GTK4 daraus einen Knopf macht, ob die zwanzig
    Module in der richtigen Reihenfolge nebeneinander stehen, ob ein
    Skriptmodul seine Antwort ueberhaupt anzeigt und ob ein Klick
    irgendwo ankommt. Genau das steht hier, und zwar aus dem Prozess
    heraus, der die Leiste gezeichnet hat.

DIE ANZEIGE
    tests/gtk4_headless.py, dieselbe wie beim graphischen Installer und
    beim Startmenue. Neu ist nur der Klient: die Leiste ist TypeScript,
    also uebersetzt `ags bundle` sie zuerst zu einer JS-Datei, die gjs
    ausfuehrt.

WARUM `ags bundle` UND NICHT `ags run`
    `ags run` startet app.ts - die ganze Oberflaeche - und meldet sich
    unter dem Instanznamen "ags" an einem Astal-Socket an. Auf der
    Maschine eines Entwicklers ist das der Socket SEINER Sitzung.
    `ags bundle` liest Dateien und schreibt eine Datei; es fasst nichts
    an, was laeuft. Der gebuendelte Klient importiert dann BarContent()
    und DockContent(), nicht Bar() und Dock() - siehe den Kopf von
    bar_headless_child.tsx dafuer, warum das nicht dasselbe ist.

DIE DREI DINGE, DIE ISOLIERT WERDEN MUESSEN, UND WARUM
      XDG_RUNTIME_DIR   broadwayd legt seinen Socket dorthin. Ein
                        Verzeichnis je Test.
      XDG_CONFIG_HOME   die Leiste liest ihre Skripte und
                        workspaces.json daraus. Ohne die Umleitung
                        liefe sie gegen ~/.config des Entwicklers.
      DBUS_SESSION_BUS_ADDRESS
                        DIE WICHTIGSTE, und sie hat eine Messung:
                        ags-tray.template ruft Gio.bus_own_name auf
                        org.kde.StatusNotifierWatcher. Ein erster Lauf
                        ohne diese Variable erreichte den echten
                        Sitzungsbus des Nutzers. Genommen wurde der Name
                        nicht - BusNameOwnerFlags.NONE, und waybar hielt
                        ihn -, aber auf einer Maschine, auf der er frei
                        ist, haette ein TESTLAUF die Ablage der laufenden
                        Sitzung uebernommen. Auf eine Adresse zu zeigen,
                        die es nicht gibt, macht daraus ein sauberes
                        "name lost".
                        Gemessen und nicht angenommen: mit der Variable
                        meldet ein Probelauf auf einen garantiert freien
                        Namen NAME-LOST, ohne sie NAME-ACQUIRED.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.gtk4_headless import broadwayd, start_broadwayd, stop_broadwayd

# Der Buendler und das Kind sind echte Prozesse. Die Marke steht auf dem
# MODUL und nicht auf dem ersten Test, aus demselben Grund wie in
# tests/src/test_reference_resolution.py: welchen Test pytest zuerst
# erreicht, entscheidet die Auswahl, und mit `-k` wuerde sonst die
# Weigerung des Waechters zum Fehlschlag.
#
# Ohne sie liefe es TROTZDEM - modulweite Fixtures werden vor den
# funktionsweiten autouse-Fixtures aufgebaut, also greift der Waechter
# gar nicht. Genau deshalb steht sie hier: eine Erlaubnis, die man nur
# durch die Reihenfolge der Fixtures hat, ist keine Erlaubnis, sondern
# ein Loch.
pytestmark = pytest.mark.allow_subprocess

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
CHILD = Path(__file__).resolve().parent / "bar_headless_child.tsx"
# bar_width_child hiess bis zum Umbau auf die Seitenleiste so; seit die
# Leiste links steht, misst dasselbe Kind nicht mehr nur Breite, sondern
# ob der Inhalt in die Flaeche PASST - daher bar_fit_child.
FIT_CHILD = Path(__file__).resolve().parent / "bar_fit_child.tsx"
DOCK_CHILD = Path(__file__).resolve().parent / "dock_headless_child.tsx"
# Die zwei freistehenden Knoepfe am Dock. Sie stehen NICHT auf der
# Leiste, also baut FIT_CHILD sie nicht - und genau deshalb ist derselbe
# Fehler an ihnen dreimal unbemerkt geblieben (20.08.2026, Aufgabe 47).
CORNER_CHILD = Path(__file__).resolve().parent / "corner_button_child.tsx"

# Eigene Anzeigenummern. 11 und 12 gehoeren tests/installer, 21 bis 98
# tests/menu.
_DISPLAYS = iter(range(120, 160))

CHILD_TIMEOUT = 180

# Was aus welcher Vorlage wird, damit das Kind es importieren kann.
RENDERED = {
    # Bar.tsx holt `_` daraus. Ohne diese Zeile findet `ags bundle` den
    # Import nicht und das Kind startet gar nicht erst.
    "templates/ags-i18n.template": "utils/i18n.ts",
    "templates/ags-hyprland.template": "utils/hyprland.ts",
    "templates/ags-tray.template": "utils/tray.ts",
    # Dock.tsx holt zepRow und zepDivider daraus. Ohne diese Zeile
    # meldet `ags bundle` "Could not resolve ../utils/kit" und KEIN Kind
    # dieser Datei startet mehr - auch die, die mit dem Dock nichts zu
    # tun haben, denn die Leiste und die zwei Knoepfe importieren es
    # ueber Dock.tsx mit.
    "templates/ags-kit.template": "utils/kit.ts",
    # Dock.tsx liest und schreibt die Einstellungen daraus, seit Aufgabe
    # 53 (21.08.2026) - und horcht darueber auf Aenderungen, die ein
    # anderes Fenster gemacht hat. Dieselbe Begruendung wie bei kit.ts
    # eine Zeile hoeher: ohne diesen Eintrag meldet `ags bundle` "Could
    # not resolve ../utils/user-settings", und KEIN Kind dieser Datei
    # startet mehr.
    "templates/ags-user-settings.template": "utils/user-settings.ts",
    "templates/ags-bar.template": "widget/Bar.tsx",
    "templates/ags-dock.template": "widget/Dock.tsx",
    # Die zwei Knoepfe am Dock, fuer CORNER_CHILD. Sie stehen in
    # DERSELBEN Liste und nicht in einer zweiten daneben: der Buendler
    # folgt Importen, also kostet eine Datei, die kein Kind importiert,
    # nichts ausser dem Erzeugen - und zwei Listen waeren zwei, die
    # auseinanderlaufen.
    "templates/ags-power-button.template": "widget/PowerButton.tsx",
    "templates/ags-starter-button.template": "widget/StarterButton.tsx",
    "styles/bar-style.template": "bar.css",
}

# Was die Skriptmodule sagen sollen. Ein Wort je Modul, damit sich in der
# Spur nachlesen laesst, welcher Kasten welche Antwort bekommen hat.
STUB_MODULES = {
    "date.sh": "DATUM",
    "clocks.sh": "UHREN",
    "weather.sh": "WETTER",
    "hypr-shortcuts.py": "TASTEN",
    "floating-layouts-bar.sh": "LAYOUTS",
    "helpers-bar.py": "HELFER",
    "hardware-monitor.py": "HARDWARE",
    # Die drei BEDINGTEN (Aufgabe #94). Sie antworten hier mit Text,
    # also im MELDEZUSTAND - das ist der Fall, den diese Datei messen
    # soll: eine Leiste, auf der alles steht, was ueberhaupt darauf
    # stehen kann. Der Ruhezustand ist der schmalere und deshalb der
    # uninteressantere; dass sie sich darin ausblenden, misst
    # tests/src/test_bar_notifications.py.
    "privacy.sh": "LAUSCHT",
    "media.sh": "MUSIK",
    "updates.sh": "UPDATE",
}

STATUS_KEYS = {
    "audio": "TON", "microphone": "MIKRO", "battery": "AKKU",
    "network": "NETZ", "bluetooth": "BLAU",
}


def _renderer(scale: float | None = None, home: Path | None = None,
              settings: dict | None = None):
    """Der Prozessor, so importiert, wie der Generator ihn importiert.

    Mit `scale` kommen die {{STYLE_*}} nicht aus den Einstellungen
    dieser Maschine, sondern aus einer Datei, die der Test in `home`
    schreibt. Dieselbe Form wie test_sizes._import_style: das
    Stilmodul liest die Einstellungen beim IMPORT, also gibt es keinen
    anderen Weg, ihm andere zu geben, als es neu zu importieren.

    Ohne die Umleitung waere jede Messung ueber Groessenfaktoren die
    Messung DES FAKTORS, DEN DER ENTWICKLER EINGESTELLT HAT - also
    viermal derselbe.

    `settings` geht auf demselben Weg in dieselbe Datei und ist seit dem
    12.08.2026 da: die ausgelieferte Leiste ist seither eine AUSWAHL,
    und der Lauf, der prueft, ob jedes Modul aus seinem Skript etwas
    anzeigt, braucht sie alle aufgestellt. Ohne ihn maesse er nur noch
    die sechs, die die Vorgabe zeigt - und die zehn zuschaltbaren
    waeren ungeprueft genau so lange, bis sie jemand zuschaltet.
    """
    sys.path.insert(0, str(SRC))
    try:
        import template_processor
        if scale is None and settings is None:
            return template_processor.ConfigProcessor()

        document: dict = {"schema_version": 1}
        if scale is not None:
            document["sizes"] = {"scale": scale}
        document.update(settings or {})
        home.mkdir(parents=True, exist_ok=True)
        (home / "user-settings.json").write_text(
            json.dumps(document), encoding="utf-8")
        previous = {name: os.environ.get(name) for name in
                    ("ZEPOS_SYSTEM_ROOT", "ZEPOS_USER_ROOT", "XDG_CONFIG_HOME")}
        os.environ.pop("ZEPOS_SYSTEM_ROOT", None)
        os.environ["ZEPOS_USER_ROOT"] = str(home)
        os.environ["XDG_CONFIG_HOME"] = str(home)
        try:
            spec = importlib.util.spec_from_file_location(
                f"zepos_style_fit_{home.name}", SRC / "style_definition.py")
            style = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(style)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        return template_processor.ConfigProcessor(
            styles=dict(style.STYLE_VARIABLES))
    finally:
        sys.path.remove(str(SRC))


def _apps():
    """src/apps.py, so importiert, wie der Generator es aufruft."""
    sys.path.insert(0, str(SRC))
    try:
        import apps
        return apps
    finally:
        sys.path.remove(str(SRC))


def _render(target: Path, scale: float | None = None,
            home: Path | None = None, settings: dict | None = None) -> None:
    processor = _renderer(scale, home, settings)
    for template, output in RENDERED.items():
        destination = target / output
        destination.parent.mkdir(parents=True, exist_ok=True)
        processor.apply_template(SRC / template, destination)

    # Der Nachlauf, den generate_config.sh fuer ags-dock fuehrt.
    #
    # Ohne ihn traegt das gebuendelte Dock die leere Liste aus der
    # Vorlage, und jede Messung darunter waere die eines Docks, das es
    # auf keiner Installation gibt - dieselbe Falle, die
    # bar_width_child.tsx fuer das fehlende Stylesheet beschreibt.
    dock = target / RENDERED["templates/ags-dock.template"]
    apps = _apps()
    dock.write_text(
        apps.render(dock.read_text(encoding="utf-8"), names=apps.shipped(SRC)),
        encoding="utf-8")


def _stub_scripts(scripts: Path) -> None:
    """Die zwoelf Modulskripte, durch Attrappen ersetzt.

    Die echten fragen den Compositor, NetworkManager, wttr.in und den
    Akku. Was hier gemessen wird, ist nicht ihre Antwort, sondern was die
    Leiste MIT einer Antwort tut - also ist die Antwort eine Konstante.
    Die Skripte selbst haben ihre eigenen Tests, je einen je Datei.
    """
    scripts.mkdir(parents=True, exist_ok=True)
    for name, text in STUB_MODULES.items():
        script = scripts / name
        script.write_text(
            "#!/bin/bash\n"
            f"printf '{{\"text\": \"{text}\", \"tooltip\": \"tt\", "
            f"\"class\": \"probe-{text.lower()}\"}}'\n")
        script.chmod(0o755)

    payload = ", ".join(
        f'"{key}": {{"text": "{value}"}}' for key, value in STATUS_KEYS.items())
    status = scripts / "status.sh"
    status.write_text("#!/bin/bash\nprintf '{" + payload + "}'\n")
    status.chmod(0o755)


# Was `hyprctl devices -j` antwortet, wenn es hier eines gaebe.
#
# WARUM DIESE ATTRAPPE SEIT DEM 17.08.2026 NOETIG IST
#     An diesem Tag hat die Leiste custom/keyboard bekommen, und dieses
#     Modul fragt genau diesen Befehl (siehe keyboardModule() in
#     ags-bar.template). Hier laeuft kein Compositor: das echte hyprctl
#     liegt zwar in /usr/bin, findet aber ohne
#     HYPRLAND_INSTANCE_SIGNATURE keine Instanz und scheitert. Das Modul
#     zeigte dann sein Fehlerbild - eine ANDERE Breite als die, die auf
#     einer laufenden Maschine gemessen werden soll.
#
#     Dieselbe Entscheidung wie bei den Modulskripten daneben: was hier
#     gemessen wird, ist nicht die Antwort des Werkzeugs, sondern was die
#     Leiste MIT einer Antwort tut.
#
# Die Felder sind von `hyprctl devices -j` auf dieser Maschine
# ABGELESEN und nicht erfunden (17.08.2026): sieben Eintraege, davon
# einer mit "main": true, dazu "layout" und "active_keymap".
HYPRCTL_KEYBOARDS = """{
  "mice": [],
  "keyboards": [
    {"address": "0x1", "name": "power-button", "rules": "", "model": "",
     "layout": "de", "variant": "", "options": "",
     "active_keymap": "German", "main": false},
    {"address": "0x2", "name": "at-translated-set-2-keyboard",
     "rules": "", "model": "", "layout": "de", "variant": "",
     "options": "", "active_keymap": "German", "main": true}
  ]
}"""


def _stub_hyprctl(root: Path) -> str:
    """Ein hyprctl, das antwortet. Zurueck kommt der PATH dafuer."""
    binaries = root / "attrappen"
    binaries.mkdir(parents=True, exist_ok=True)
    tool = binaries / "hyprctl"
    tool.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "devices" ]; then\n'
        "cat <<'JSON'\n" + HYPRCTL_KEYBOARDS + "\nJSON\n"
        "fi\n"
        "exit 0\n")
    tool.chmod(0o755)
    return f"{binaries}:/usr/bin:/bin"


def _bundle(child: Path, root: Path, scale: float | None = None,
            settings: dict | None = None) -> tuple[Path, Path]:
    """Ein Kind, uebersetzt gegen die erzeugte Leiste.

    Zurueck kommen die Buendeldatei UND das Verzeichnis der erzeugten
    Dateien: bar.css liegt darin, und die Kinder, die MESSEN, laden es
    zur Laufzeit - ohne das Stylesheet misst man eine Leiste ohne
    Schriftgroesse und ohne Abstaende.
    """
    if shutil.which("ags") is None:
        pytest.skip("ags fehlt; es kommt mit dem Paket aylurs-gtk-shell")

    ags = root / "ags"
    ags.mkdir()
    _render(ags, scale, root / "stil", settings)
    shutil.copy(child, ags / "child.tsx")

    bundle = root / "child.js"
    result = subprocess.run(
        ["ags", "bundle", str(ags / "child.tsx"), str(bundle),
         "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (
        "`ags bundle` hat die Leiste nicht uebersetzt:\n"
        + result.stdout + result.stderr)
    assert bundle.is_file(), "der Buendler hat keine Datei geschrieben"
    return bundle, ags


# Jedes Modul, das die Leiste bauen kann, aufgestellt - und nur fuer
# DIESEN Lauf.
#
# WARUM NICHT DIE VORGABE (12.08.2026)
#     Die Frage dieses Laufs ist "baut die Leiste jedes Modul, und zeigt
#     jedes, was sein Skript geantwortet hat". Mit der VORGABE hat sie
#     nichts zu tun: die stellt seit dem 12.08.2026 zehn von einundzwanzig
#     Modulen nicht mehr auf (siehe BAR_MODULES_AVAILABLE in
#     src/style_definition.py), und ein Lauf mit ihr maesse zehn Zweige
#     ueberhaupt nicht mehr - lautlos, bis sie jemand zuschaltet.
#
#     Ob die VORGABE auf einen Schirm passt, ist die andere Frage, und
#     sie stellt der `fit`-Lauf weiter unten. Der bekommt diese
#     Einstellung deshalb NICHT.
#
# hyprland/workspaces steht nicht darin: die Mitte des Gtk.CenterBox ist
# sein fester Platz, und ein Widget hat einen Elternteil.
def _marke(modul: str) -> str:
    """Der Name, unter dem die Leiste ein Modul in ihrer Spur meldet.

    ABGELESEN an einem echten Lauf (`run.report`, 17.08.2026): aus
    `custom/date` wird `custom-date`, aus `hyprland/window` wird
    `window`, und `pulseaudio#microphone` bleibt, wie es ist. Der
    Schraegstrich taugt nicht als Teil eines Widgetnamens; der
    hyprland-Vorsatz faellt ganz weg, weil er nur sagt, WOHER das Modul
    kommt.
    """
    if modul.startswith("hyprland/"):
        return modul.split("/", 1)[1]
    return modul.replace("/", "-")


BAR_EVERYTHING = {"bar": {
    # custom/hardware steht links, seit dem 17.08.2026 - in derselben
    # Nachbarschaft wie in der Vorgabe (siehe _modules_left in
    # src/style_definition.py). Diese Liste soll jeden Zweig EINMAL
    # aufstellen; wo ein Modul dabei steht, wird von der Vorgabe
    # abgelesen, damit die beiden Laeufe dieselbe Leiste messen. Was die
    # Vorgabe nicht aufstellt - hier custom/keyboard und
    # hyprland/window -, steht am Ende, in keiner besonderen Ordnung
    # zueinander: fuer sie gibt es keine Vorgabe-Nachbarschaft, von der
    # abzulesen waere.
    #
    # DASS DAS SO BLEIBT, HAELT test_die_nachbarschaft_ist_die_der_vorgabe
    # weiter unten. Am 17.08.2026 hat der Nutzer die Reihenfolge von
    # custom/keyboard und custom/date getauscht, die Vorgabe wanderte, und
    # diese Kopie blieb stehen - 31 Tests blieben gruen und massen dabei
    # eine Leiste, die es nicht mehr gab. Genau dafuer gibt es den Test.
    #
    # GEAENDERT am 19.08.2026: custom/hypr-shortcuts stand hier bereits
    # (es war zuschaltbar), und ist jetzt zusaetzlich in der Vorgabe -
    # es bleibt deshalb stehen, nur seine Nachbarschaft ist jetzt die
    # von _modules_left. custom/keyboard war Teil der Vorgabe und ist
    # es nicht mehr ("in die leiste und keyboard icon mit de oder us
    # weg", woertlich) - sein Zweig bleibt aber gebaut (siehe
    # _bar_optional in src/style_definition.py), also bleibt es auch
    # hier stehen, jetzt am Ende bei den anderen Nicht-Vorgabe-Modulen.
    #
    # UND AM 20.08.2026 IST DIE RECHTE HAELFTE NACHGEZOGEN WORDEN, GLEICH
    # AN DREI STELLEN (Aufgabe 42).
    #
    #     Der Waechter darueber prueft nur die LINKE Haelfte - er hiess
    #     _vorgabe_links() und las auch nur die. Die rechte Abschrift ist
    #     deshalb still veraltet, und zwar zweifach, seit es sie gibt:
    #
    #         custom/disk    stand hier hinter `tray`, in der Vorgabe
    #                        aber an zweiter Stelle, direkt hinter
    #                        custom/media.
    #         custom/updates stand hier VOR custom/privacy, in der
    #                        Vorgabe aber dahinter.
    #
    #     Genau die Sorte Fehler, gegen die dieser Block seit dem
    #     17.08.2026 gewarnt hat - nur eben in der Haelfte, die der
    #     Waechter nicht ansah. Er sieht seit heute beide (siehe
    #     test_die_nachbarschaft_ist_die_der_vorgabe unten).
    #
    #     DAZU DER UMZUG DES TAGES: `tray` steht in der Vorgabe jetzt an
    #     zweiter Stelle, direkt hinter custom/media - die Ablage
    #     waechst, und nichts, was man anklickt, darf rechts davon
    #     stehen. Die ganze Begruendung steht bei _modules_right in
    #     src/style_definition.py.
    "modules_left": ["custom/date", "custom/hardware",
                     "custom/weather", "custom/clocks",
                     "custom/notifications", "custom/hypr-shortcuts",
                     "custom/keyboard", "hyprland/window"],
    "modules_right": ["custom/media", "tray",
                      "custom/floating-layouts", "custom/helpers",
                      "custom/disk", "custom/wallpaper",
                      "network", "bluetooth",
                      "pulseaudio", "pulseaudio#microphone", "battery",
                      "custom/privacy", "custom/updates",
                      "custom/theme", "custom/system"],
}}


@pytest.fixture(scope="module")
def bundled(tmp_path_factory) -> Path:
    """Die uebersetzte Leiste, einmal je Lauf.

    Modulweit, weil `ags bundle` ueber eine Sekunde braucht und jeder
    Test darunter dieselbe Datei ausfuehrt - mit einer eigenen Anzeige
    und einem eigenen Konfigurationsverzeichnis.
    """
    bundle, _ = _bundle(CHILD, tmp_path_factory.mktemp("bar-bundle"),
                        settings=BAR_EVERYTHING)
    return bundle


class Run:
    """Was ein Lauf hinterlassen hat."""

    def __init__(self, returncode: int, stdout: str, stderr: str,
                 trace: str, maps: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.trace = trace
        self.maps = maps

    def mark(self, prefix: str) -> str:
        found = [line for line in self.trace.splitlines()
                 if line.startswith(prefix + ":")]
        assert found, f"keine Marke {prefix} in der Spur:\n{self.report}"
        return found[0].split(":", 1)[1]

    @property
    def report(self) -> str:
        return (f"rueckgabewert: {self.returncode}\n"
                f"stdout: {self.stdout!r}\nstderr:\n{self.stderr}\n"
                f"spur:\n{self.trace}")


@pytest.fixture(scope="module")
def run(bundled, tmp_path_factory) -> Run:
    """Ein Lauf, und alles, was die Tests darunter daran messen.

    Modulweit aus demselben Grund wie das Buendeln: das Kind wartet
    absichtlich anderthalb Sekunden auf die Antworten seiner
    Skriptmodule, und neun Tests waeren neun mal anderthalb Sekunden fuer
    dieselbe Messung.
    """
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    root = tmp_path_factory.mktemp("bar-run")
    runtime = root / "run"
    runtime.mkdir()
    # GLib lehnt ein weltlesbares XDG_RUNTIME_DIR ab und sagt es auf stderr.
    runtime.chmod(0o700)

    config = root / "config"
    _stub_scripts(config / "ags" / "scripts")
    (config / "ags" / "workspaces.json").write_text(
        '{"persistent-workspaces": {"PROBE-1": [1, 2, 3]},'
        ' "format-icons": {"3": "LAPTOP"}}')

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    try:
        result = subprocess.run(
            [str(bundled)],
            env={
                "PATH": _stub_hyprctl(root),
                "HOME": str(root),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(config),
                # Siehe den Kopf dieser Datei.
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={root}/kein-bus",
                "ZEPOS_TRACE": str(trace),
                "ZEPOS_MONITOR": "PROBE-1",
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(server)

    maps = trace.with_suffix(".maps")
    return Run(result.returncode, result.stdout, result.stderr,
               trace.read_text() if trace.exists() else "",
               maps.read_text() if maps.exists() else "")


# --------------------------------------------------------------------
# der Toolkit-Nachweis
# --------------------------------------------------------------------

def test_the_bar_is_drawn_by_gtk4_and_by_nothing_else(run):
    """Kein libgtk-3 mehr, und zwar gemessen am laufenden Prozess.

    `readelf -d` sagt, wogegen eine Datei gelinkt wurde. Das genuegt hier
    nicht: gjs laedt seine Bibliotheken ueber GObject-Introspection zur
    Laufzeit nach, also stuende in keinem Binary ein libgtk-4. Was der
    Prozess WIRKLICH geladen hat, steht in /proc/self/maps, und das Kind
    schreibt es heraus, waehrend sein Fenster steht.
    """
    assert run.maps, "das Kind hat seine geladenen Bibliotheken nicht gemeldet"

    loaded = sorted({Path(line.split()[-1]).name
                     for line in run.maps.splitlines()
                     if line.rstrip().endswith(".so")
                     or ".so." in line.split()[-1]})

    assert any(name.startswith("libgtk-4.so") for name in loaded), (
        f"die Leiste laeuft nicht auf GTK4. Geladen: {loaded}")
    gtk3 = [name for name in loaded if name.startswith("libgtk-3.so")]
    assert gtk3 == [], f"die Leiste hat GTK3 geladen: {gtk3}"


def test_the_dock_is_drawn_by_the_same_process(run):
    """Das Dock ist kein zweites Programm mehr.

    nwg-dock-hyprland war ein eigener Prozess mit einer eigenen
    GTK3-Abhaengigkeit, gestartet aus exec-once. DockContent() steht in
    derselben Datei, wird von demselben gjs geladen und ist damit von
    demselben /proc/self/maps oben abgedeckt.
    """
    assert run.mark("dock") == "dock", (
        "das Dock hat seinen Kasten nicht gebaut:\n" + run.report)


# --------------------------------------------------------------------
# was auf dem Dock steht
# --------------------------------------------------------------------
#
# Der Anlass, am 11.08.2026: "die nwg dock unten geht nicht mehr". Das
# Dock zeigte einen Knopf je offenem Fenster und versteckte sich, wenn es
# keine gab - auf einem frischen Schreibtisch also immer. Was hier
# gemessen wird, ist der Zustand, in dem es der Nutzer sieht: kein
# Fenster offen, keine Sitzung, kein Compositor.

# Die Anwendungseintraege, die es in DIESEM Lauf gibt. Zwei aus der
# Auswahl und einer, der nicht darin steht.
#
# Zwei und nicht alle, weil die eine Haelfte der Messung die
# GEGENRICHTUNG ist: die uebrigen Namen der Auswahl haben hier keinen
# Eintrag, duerfen keinen Knopf bekommen, und das Dock muss trotzdem
# dastehen. Ein Lauf, in dem alles aufloest, kann das nicht zeigen.
DESKTOP_ENTRIES = {
    "nautilus": ("Dateien", "org.gnome.Nautilus"),
    "firefox": ("Firefox", "firefox"),
    # Der Konsoleneintrag aus der Auswahl - Terminal=true, siehe
    # TERMINAL_ENTRIES unten. Er steht in DIESER Tabelle, weil er ein
    # ganz normaler Knopf des Docks ist; was ihn unterscheidet, ist
    # allein, womit er startet.
    "btop": ("btop++", "btop"),
    # Nicht in zepos-apps. Er liegt hier, damit die Messung unten nicht
    # bloss "es sind zwei" sagt, sondern "es sind GENAU die beiden aus
    # der Auswahl": ein Dock, das alles anheftet, was auf der Maschine
    # installiert ist, waere keine Auswahl mehr.
    "gimp": ("GIMP", "Gimp"),
}

# DER DIENST, DER WIE DIE EINSTELLUNGEN AUSSAH (Aufgabe #93).
#
# Er steht hier, weil dieses Verzeichnis bis zum 12.08.2026 GENAU DEN
# FALL AUSGELASSEN HAT, der den Fehler ausmacht - und der Test darunter
# hat deshalb einen Zustand gemessen, den es auf keiner Installation
# gab. Sein Kopf behauptete, cups und xdg-desktop-portal-gnome traegen
# keine .desktop-Datei; GEMESSEN mit `pacman -Ql` gegen die Pakete des
# angehefteten Schnappschusses (cups 2:2.4.19-1,
# xdg-desktop-portal-gnome 50.0-1) traegt jedes von beiden eine.
#
# Die Werte hier sind die des echten Eintrags, Zeile fuer Zeile
# abgeschrieben aus /usr/share/applications/xdg-desktop-portal-gnome
# .desktop:
#
#     Name=Portal
#     Icon=applications-system-symbolic   <- das Zahnrad, in Papirus
#                                            wie in Adwaita
#     Exec=/usr/lib/xdg-desktop-portal-gnome
#     NoDisplay=true
#
# Ein Knopf dafuer sah aus wie die Systemeinstellungen und rief einen
# D-Bus-Dienst auf, der kein Fenster hat: "es erscheint nie".
SERVICE_ENTRY = "xdg-desktop-portal-gnome"
SERVICE_NAME = "Portal"

# Die Eintraege, die ein Terminal brauchen. GEMESSEN am 12.08.2026 mit
# gjs auf einer vollstaendigen Maschine: btop.desktop traegt
# Terminal=true, und GIOs launch() wirft dafuer "Fuer die Anwendung
# benoetigtes Terminal konnte nicht gefunden werden" - auch mit kitty
# und foot auf dem PATH, weil GLib nur eine feste Liste anderer
# Terminals kennt.
TERMINAL_ENTRIES = {"btop"}


def _desktop_entries(share: Path, binaries: Path) -> None:
    """Ein Anwendungsverzeichnis, in dem genau diese drei Programme sind.

    ZWEI VERZEICHNISSE UND NICHT EINES, UND DAS IST GEMESSEN
        Eine .desktop-Datei allein genuegt GIO nicht. GEMESSEN am
        11.08.2026 mit gjs gegen ein Verzeichnis mit drei identisch
        gebauten Eintraegen:

            firefox   P-firefox
            gimp      NULL
            nautilus  P-nautilus
            alle:     firefox.desktop, nautilus.desktop

        Der Unterschied war nicht die Datei, sondern der PATH: firefox
        und nautilus liegen auf dieser Maschine in /usr/bin, gimp nicht.
        GIO liefert einen Eintrag nur aus, wenn das Programm seiner
        Exec-Zeile auffindbar ist.

        Fuer das Dock ist das ein Geschenk - "nicht installiert" heisst
        damit automatisch "kein Knopf", auch wenn eine verwaiste
        .desktop-Datei liegenbleibt. Fuer diesen Test ist es die Falle,
        vor der der Kopf von dock_headless_child.tsx warnt: ohne eigene
        Programme misst er, was der Entwickler zufaellig installiert
        hat. Also bekommt jeder Eintrag hier ein Programm, und der PATH
        des Kindes enthaelt nur dieses Verzeichnis.
    """
    applications = share / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    binaries.mkdir(parents=True, exist_ok=True)
    for program, (name, wm_class) in DESKTOP_ENTRIES.items():
        terminal = "true" if program in TERMINAL_ENTRIES else "false"
        (applications / f"{program}.desktop").write_text(
            "[Desktop Entry]\nType=Application\n"
            f"Name={name}\nExec={program} %U\n"
            f"Terminal={terminal}\n"
            f"StartupWMClass={wm_class}\nIcon={program}\n")
        stub = binaries / program
        stub.write_text(f"#!/bin/bash\necho {program}\n")
        stub.chmod(0o755)

    # Und der Dienst, mit allem, was ihn auffindbar macht: eigener
    # Eintrag, eigenes Programm auf dem PATH. Ohne das Programm faende
    # GIO ihn nicht, und der Test darunter wuerde "kein Knopf" messen
    # und "NoDisplay wirkt" darueber schreiben - die Art Zusicherung,
    # die gruen ist, weil sie den Fall nicht herstellt.
    (applications / f"{SERVICE_ENTRY}.desktop").write_text(
        "[Desktop Entry]\nType=Application\n"
        f"Name={SERVICE_NAME}\nExec={SERVICE_ENTRY}\n"
        "Icon=applications-system-symbolic\nNoDisplay=true\n")
    stub = binaries / SERVICE_ENTRY
    stub.write_text(f"#!/bin/bash\necho {SERVICE_ENTRY}\n")
    stub.chmod(0o755)

    _werkzeuge(binaries)


# Was das Dock BRAUCHT, um seine Einstellungen zu lesen - kein Programm
# dieses Schreibtischs, sondern Werkzeug.
#
# SEIT DEM 21.08.2026 (Aufgabe 53), UND ES IST GEMESSEN
#     Der Fuss liest seine Anheftungen jetzt beim Bauen, ueber
#     `bash -c "... python3 <wurzel>/settings.py dock"` (siehe
#     utils/user-settings.ts). Der PATH dieser Laeufe besteht NUR aus
#     dem Programmverzeichnis - siehe den Kopf von
#     dock_headless_child.tsx, und das ist richtig so: mit /usr/bin
#     darin maesse der Lauf, was der Entwickler zufaellig installiert
#     hat.
#
#     Ohne diese zwei Verknuepfungen meldete jeder Lauf am 21.08.2026
#     zweimal `Failed to execute child process "bash"` auf STDERR, und
#     test_the_run_produced_no_critical_warning fiel darueber. Die
#     Meldung war RICHTIG - das Kind konnte seine Einstellungen wirklich
#     nicht lesen.
#
# WEITERGABEN UND KEINE VERKNUEPFUNGEN, und das ist keine Vorliebe:
# tests/conftest.py prueft bei einem Symlink auch das ZIEL ("moving a
# harmless temporary file onto /etc/passwd is a write to /etc/passwd"),
# und /usr/bin/bash ist geschuetzt. Eine Kopie waere fuer python3 falsch -
# der Interpreter findet seine Standardbibliothek ueber den Ort seiner
# eigenen Datei, und eine Kopie unter /tmp faende sie nicht. Ein
# Weitergabeskript loest beides: es liegt im Programmverzeichnis, und
# das Programm dahinter startet an seinem eigenen Ort.
#
# Keines von beiden ist eine Anwendung: sie tragen keinen
# .desktop-Eintrag, fallen also nicht in die Auswahl, die diese Laeufe
# messen.
def _werkzeuge(binaries: Path) -> None:
    binaries.mkdir(parents=True, exist_ok=True)
    for werkzeug in ("bash", "python3"):
        ziel = shutil.which(werkzeug)
        assert ziel, (f"ohne {werkzeug} kann das Dock seine Einstellungen "
                      f"nicht lesen")
        stub = binaries / werkzeug
        stub.write_text(f'#!/bin/sh\nexec {ziel} "$@"\n')
        stub.chmod(0o755)


@pytest.fixture(scope="module")
def dock_run(tmp_path_factory) -> Run:
    """Das erzeugte Dock, gebaut, in einem Lauf fuer sich.

    Eigener Lauf und nicht der oben, weil dieses Kind ein
    XDG_DATA_DIRS bekommt, das nur auf sein eigenes Verzeichnis zeigt -
    siehe den Kopf von dock_headless_child.tsx. Die Leiste braucht das
    Gegenteil und wuerde ohne Symbolthema andere Breiten melden.

    MIT Stylesheet, und das ist seit dem 12.08.2026 noetig: dieser Lauf
    misst jetzt auch, wie HOCH die Fusszeile ist, und diese Zahl kommt
    aus bar.css - Innenabstand, Rahmen und Aussenrand der Knoepfe. Ohne
    das Stylesheet waere es die Hoehe einer Adwaita-Knopfreihe.
    """
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    root = tmp_path_factory.mktemp("dock-run")
    build = root / "build"
    build.mkdir()
    bundle, ags = _bundle(DOCK_CHILD, build)

    runtime = root / "run"
    runtime.mkdir()
    runtime.chmod(0o700)
    share = root / "share"
    binaries = root / "bin"
    _desktop_entries(share, binaries)

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    try:
        result = subprocess.run(
            [str(bundle)],
            env={
                # NUR das Stub-Verzeichnis, und das ist die Haelfte der
                # Isolierung, die man vergisst: GIO liefert einen
                # Anwendungseintrag nur aus, wenn dessen Programm auf dem
                # PATH liegt. Mit /usr/bin darin haette dieser Lauf
                # gemessen, welche der zehn Anwendungen der Entwickler
                # zufaellig installiert hat. Siehe _desktop_entries().
                "PATH": str(binaries),
                "HOME": str(root),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(root / "config"),
                # Die andere Haelfte. Nur dieses Verzeichnis: was auf der
                # Maschine des Entwicklers installiert ist, darf das
                # Ergebnis nicht bewegen.
                "XDG_DATA_DIRS": str(share),
                "XDG_DATA_HOME": str(root / "data"),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={root}/kein-bus",
                "ZEPOS_TRACE": str(trace),
                "ZEPOS_CSS": str(ags / "bar.css"),
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(server)

    return Run(result.returncode, result.stdout, result.stderr,
               trace.read_text() if trace.exists() else "", "")


# --------------------------------------------------------------------
# die Ablage auf einer Maschine mit zwei Schirmen (Aufgabe #96)
# --------------------------------------------------------------------

TRAY_CHILD = Path(__file__).resolve().parent / "tray_headless_child.tsx"


@pytest.fixture(scope="module")
def tray_run(tmp_path_factory) -> Run:
    """Die erzeugte Ablage, ZWEIMAL gebaut, auf einem eigenen Bus.

    DER EIGENE BUS IST DER GANZE AUFWAND, UND ER IST NOETIG
        Alle anderen Kinder dieser Datei zeigen auf eine Busadresse, die
        es nicht gibt - siehe den Kopf des Moduls. Das ist richtig und
        macht diesen einen Fehler unsichtbar: er steckt im
        Erwerbs-Rueckruf von Gio.bus_own_name, und ohne Bus laeuft der
        nie.

        `dbus-run-session` gibt dem Kind einen frisch gestarteten
        Sitzungsbus, der mit ihm stirbt. Der Bus des Entwicklers wird
        dabei NICHT angefasst - und er waere fuer diese Messung auch
        untauglich, weil dort seine eigene Leiste den Watcher-Namen
        schon haelt.
    """
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")
    if shutil.which("dbus-run-session") is None:
        pytest.skip("dbus-run-session fehlt; es kommt mit dem Paket dbus")

    root = tmp_path_factory.mktemp("tray-run")
    build = root / "build"
    build.mkdir()
    bundle, _ags = _bundle(TRAY_CHILD, build)

    runtime = root / "run"
    runtime.mkdir()
    runtime.chmod(0o700)

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    try:
        result = subprocess.run(
            ["dbus-run-session", "--", str(bundle)],
            env={
                "PATH": _stub_hyprctl(root),
                "HOME": str(root),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(root / "config"),
                "ZEPOS_TRACE": str(trace),
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(server)

    return Run(result.returncode, result.stdout, result.stderr,
               trace.read_text() if trace.exists() else "", "")


def test_the_tray_survives_a_second_screen(tray_run):
    """GEMELDET am 12.08.2026, aus dem AGS-Protokoll einer Maschine mit
    zwei Schirmen:

        JS ERROR: Gio.IOErrorEnum: An object is already exported for the
        interface org.kde.StatusNotifierWatcher at /StatusNotifierWatcher

    Tray() lief einmal JE SCHIRM - ags-bar.template baut eine Leiste je
    Gdk.Monitor -, und der Watcher steckte im Rumpf. Der zweite Aufruf
    nahm damit denselben Busnamen auf DERSELBEN Verbindung noch einmal;
    GDBus antwortet darauf mit ALREADY_OWNER und ruft den
    Erwerbs-Rueckruf trotzdem, der dann dasselbe Objekt ein zweites Mal
    auf denselben Pfad exportierte.

    Die Meldung, die der Nutzer stattdessen zu lesen bekam, war noch
    dazu falsch: "gehoert schon einem anderen Programm" - es war
    derselbe Prozess.
    """
    assert tray_run.returncode == 0, tray_run.report

    protokoll = tray_run.stdout + tray_run.stderr
    assert "already exported" not in protokoll, (
        "die zweite Ablage exportiert den Watcher ein zweites Mal - auf "
        "jeder Maschine mit zwei Schirmen:\n" + tray_run.report)
    assert "gehoert schon einem anderen Programm" not in protokoll, (
        "die zweite Ablage haelt den eigenen Prozess fuer ein fremdes "
        "Programm:\n" + tray_run.report)

    assert tray_run.mark("boxen") == "zwei", (
        "beide Schirme bekamen dieselbe Box - ein Gtk.Widget hat genau "
        "einen Elternteil, also saehe der zweite Schirm keine Ablage:\n"
        + tray_run.report)


def test_an_empty_tray_shows_nothing_at_all(tray_run):
    """GEMESSEN auf out/render/schreibtisch-1920.png am 12.08.2026:
    ein volldeckender Block (33, 79, 89) von 30x47 Bildpunkten bei
    x=1707..1736, zwischen "87%" und den drei Symbolknoepfen rechts.

    Es war der Normalfall - eine frisch angemeldete Sitzung, in der noch
    kein Programm ein Ablagesymbol angemeldet hat. Die Box war leer und
    trug trotzdem die Kachel, die die Leiste jedem Modul anhaengt.

    Die Kachel ist inzwischen ueberall fort; diese Zeile haelt die
    zweite Haelfte: eine leere Ablage nimmt auch keinen PLATZ. Ein
    unsichtbares Widget beantwortet gtk_widget_measure mit 0, also
    kostet sie in der Einklapp-Rechnung nichts - das ist der
    Unterschied, der bei 1920 zwei Module vor den Einklapp-Knopf
    zurueckgeholt hat.
    """
    assert tray_run.mark("leer-sichtbar") == "nein", (
        "eine Ablage ohne ein einziges Symbol zeigt sich trotzdem:\n"
        + tray_run.report)


def test_the_dock_stands_there_with_no_window_open(dock_run):
    """Die Frage, die der Nutzer gestellt hat, als Zusicherung.

    Hier stand `box.set_visible(clients.length > 0)`. Ohne Compositor
    gibt es keine Fenster, also war der Kasten unsichtbar - und mit ihm
    das Dock auf jedem frisch angemeldeten Schreibtisch. Ein Dock, das
    erst erscheint, wenn schon etwas offen ist, ist genau dann weg, wenn
    man es braucht.
    """
    assert dock_run.returncode == 0, dock_run.report
    assert dock_run.mark("dock") == "dock", dock_run.report
    assert dock_run.mark("sichtbar") == "ja", (
        "das Dock versteckt sich, wenn kein Fenster offen ist:\n"
        + dock_run.report)


def test_the_dock_pins_the_applications_zepos_ships_and_only_those(dock_run):
    """Angeheftet ist, was zepos-apps ausliefert - nicht mehr und nicht
    weniger.

    GENAU diese Menge und keine Obermenge. GIMP liegt in demselben
    Anwendungsverzeichnis wie die beiden anderen und darf trotzdem nicht
    auf dem Dock stehen: die Auswahl ist eine Entscheidung dieses
    Projekts, und ein Dock, das alles anheftet, was installiert ist, hat
    sie nicht getroffen.
    """
    pinned = [entry for entry in dock_run.mark("angeheftet").split(",") if entry]
    assert pinned == ["Firefox", "Dateien", "btop++"], (
        "das Dock heftet nicht die ausgelieferte Auswahl an:\n"
        + dock_run.report)


def test_a_pinned_application_that_is_not_installed_gets_no_button(dock_run):
    """Spec §7.4, an der Stelle, an der sie sonst gebrochen wuerde.

    Die meisten Namen aus zepos-apps haben in diesem Lauf keinen
    Anwendungseintrag, weil das Stub-Verzeichnis nur drei kennt. Ein
    Knopf fuer sie waere ein Bedienelement, das nichts tut, und das ist
    der Fehler, den §7.4 fuer den schlimmsten haelt.

    Die Gegenprobe steckt in der Zusicherung darueber: das Dock steht
    trotzdem da. "Ein Name fehlt" darf nicht heissen "es gibt kein
    Dock" - genau dieser Kurzschluss war der Fehler, der behoben wird.

    HIER STAND, cups und xdg-desktop-portal-gnome haetten "auf keiner
    Maschine" einen Eintrag. Das war falsch - siehe SERVICE_ENTRY oben -
    und der Satz ist der Grund, aus dem dieser Test den Fehler nicht
    gefunden hat, den ein Mensch dann gefunden hat.
    """
    shipped = _apps().shipped(SRC)
    assert len(shipped) > 5, f"die Auswahl ist zu klein zum Messen: {shipped}"

    kinder = dock_run.mark("kinder")
    for program in shipped:
        if program in DESKTOP_ENTRIES:
            continue
        assert program.lower() not in kinder.lower(), (
            f"{program} hat einen Knopf, obwohl es keinen "
            f"Anwendungseintrag gibt:\n" + dock_run.report)

    # Und die Meldung darueber steht im Protokoll, statt still zu sein.
    for program in ("cups", "loupe"):
        assert program in dock_run.stdout + dock_run.stderr, (
            f"das Dock sagt nicht, dass es {program} nicht anheften "
            f"konnte:\n" + dock_run.report)


def test_a_pinned_service_gets_no_button_and_says_so(dock_run):
    """Das Zahnrad im Fuss, als Zusicherung (Aufgabe #93).

    GEMELDET am 12.08.2026: "das einstellungs icon im footer laesst sich
    garnicht oeffnen es erscheint nie" - und noch einmal: "im footer war
    ein einstellungs icon was man nicht oeffnen konnte".

    Es war der Eintrag des Portal-Dienstes: ein Zahnrad
    (Icon=applications-system-symbolic, in Papirus wie in Adwaita ein
    Zahnkranz), ein Klick, und dahinter ein D-Bus-Dienst ohne Fenster.
    Der Unterschied zu allem anderen auf dem Dock steht in seiner
    eigenen Datei, nach der Freedesktop-Spezifikation: NoDisplay=true.

    ZWEI ZUSICHERUNGEN UND NICHT EINE, weil "kein Knopf" allein auch
    dann gruen waere, wenn GIO den Eintrag ueberhaupt nicht ausgeliefert
    haette - und dann pruefte dieser Test das Stub-Verzeichnis statt der
    Regel. Die Meldung im Protokoll ist der Beleg, dass der Eintrag DA
    war und BEWUSST abgelehnt wurde.
    """
    kinder = dock_run.mark("kinder")
    assert SERVICE_NAME not in kinder, (
        f"der Dienst {SERVICE_ENTRY} hat einen Knopf im Dock, obwohl "
        f"sein Eintrag NoDisplay=true traegt - genau das Zahnrad, das "
        f"sich nicht oeffnen liess:\n" + dock_run.report)

    protokoll = dock_run.stdout + dock_run.stderr
    assert "NoDisplay" in protokoll and SERVICE_ENTRY in protokoll, (
        f"das Dock sagt nicht, dass es {SERVICE_ENTRY} als Dienst "
        f"abgelehnt hat - dann kann es ihn auch nicht gefunden haben, "
        f"und dieser Test misst das Stub-Verzeichnis statt der Regel:\n"
        + dock_run.report)


def test_a_console_application_is_started_in_the_terminal_zepos_ships(dock_run):
    """Die zweite tote Taste im Fuss, als Zusicherung.

    GEMESSEN am 12.08.2026 mit gjs, auf einer Maschine mit kitty und
    foot auf dem PATH:

        DesktopAppInfo.new("btop.desktop").launch([], null)
        -> WIRFT "Fuer die Anwendung benoetigtes Terminal konnte nicht
                  gefunden werden"

    btop steht in der Auswahl, sein Knopf stand im Dock, und ein Klick
    darauf hat nichts geoeffnet - weil GLib fuer Terminal=true nur eine
    feste Liste fremder Terminals kennt und ZepOS keins davon
    ausliefert. Derselbe Fehler wie beim Zahnrad, an einem anderen
    Knopf.

    Die zweite Zeile ist die Gegenprobe: ein gewoehnlicher Eintrag darf
    NICHT durch ein Terminal geschickt werden, sonst startete Firefox in
    einer Konsole.
    """
    assert dock_run.mark("terminal-btop") == "kitty -e btop", (
        "ein Konsoleneintrag wird nicht durch das Terminal geschickt, das "
        "ZepOS ausliefert - sein Knopf oeffnet also nichts:\n"
        + dock_run.report)
    assert dock_run.mark("terminal-firefox") == "selbst", (
        "ein gewoehnlicher Eintrag wird durch ein Terminal geschickt:\n"
        + dock_run.report)


def test_the_dock_pins_the_settings_application(dock_run):
    """Die zweite Haelfte von #93: die Einstellungen sind anklickbar.

    Ein Betriebssystem, dessen Systemeinstellungen man nicht anklicken
    kann, ist nicht fertig - der Nutzer vergleicht ausdruecklich mit
    Apple. Gemessen wird hier die AUSWAHL und nicht der Knopf: in diesem
    Lauf gibt es keinen Eintrag fuer zepos-settings, weil das
    Stub-Verzeichnis nur drei kennt.

    Der Weg dorthin ist src/apps.py own() - die Anwendungen, die ZepOS
    selbst baut und fuer die ein Rezept einen Anwendungseintrag ablegt.
    Ohne diese Zusicherung faellt eine Umbenennung des Rezepts oder ein
    weggelassenes `install ... zepos-settings.desktop` nur einem Menschen
    auf, der das gebaute Medium benutzt.
    """
    shipped = _apps().shipped(SRC)
    assert "zepos-settings" in shipped, (
        "die Einstellungen stehen nicht in der Auswahl, sind also vom "
        f"Dock aus nicht erreichbar: {shipped}")


def test_the_dock_separates_the_pins_from_the_loose_windows(dock_run):
    """Der Trenner steht im Kasten und ist hier unsichtbar.

    Er darf nicht erst entstehen, wenn ein fremdes Fenster aufgeht: ein
    Kind, das mitten in einer Reihe eingehaengt wird, verschiebt jeden
    Knopf rechts davon. Ohne offene Fenster hat er nichts zu trennen und
    ist deshalb aus - dass er DA ist und AUS, ist die Aussage.
    """
    kinder = dock_run.mark("kinder")
    trenner = [part for part in kinder.split(",") if "dock-separator" in part]
    assert len(trenner) == 1, (
        "der Trenner steht nicht genau einmal im Dock:\n" + dock_run.report)
    assert trenner[0].endswith("(aus)"), (
        "der Trenner ist sichtbar, obwohl er nichts zu trennen hat:\n"
        + dock_run.report)


# --------------------------------------------------------------------
# was auf der Leiste steht
# --------------------------------------------------------------------

def test_the_bar_builds_every_module_in_its_place(run):
    """Einundzwanzig Module, drei Kaesten, und die Reihenfolge ist die
    aus BAR_EVERYTHING.

    Namen und nicht Anzahl: eine Leiste, auf der zwei Module ihre Plaetze
    getauscht haben, hat dieselbe Anzahl.

    ES WAREN ACHTZEHN BIS ZUM 12.08.2026. Die vier bedingten (Aufgabe
    #94) zeigen sich nur, wenn ihr Skript etwas zu sagen hat, und ein
    unsichtbares Widget beantwortet gtk_widget_measure mit 0. Sie stehen
    hier trotzdem, weil dieser Lauf nach dem BAU fragt und nicht nach
    der Sichtbarkeit: `case`-Zweig gelaufen, Widget gebaut, in seinen
    Kasten gehaengt. Ob sie sich auch wieder ausblenden, misst
    tests/src/test_bar_notifications.py an derselben Leiste.

    DIESER LAUF STELLT ALLE AUF, die VORGABE tut es nicht mehr - siehe
    BAR_EVERYTHING oben. Was die Vorgabe aufstellt und ob es passt,
    misst der `fit`-Lauf weiter unten.
    """
    # ABGELEITET UND NICHT ABGESCHRIEBEN.
    #
    # Hier stand die Reihenfolge ein DRITTES Mal woertlich - neben
    # BAR_EVERYTHING und neben _modules_left in src/style_definition.py.
    # Am 17.08.2026 hat der Nutzer custom/keyboard und custom/date
    # getauscht, und die drei Kopien liefen auseinander, ohne dass etwas
    # rot wurde: die Zusicherung hier prueft, was BAR_EVERYTHING
    # aufstellt, und BAR_EVERYTHING war seinerseits von der Vorgabe
    # abgekommen. Drei Stellen, eine Wahrheit, keine Verbindung.
    #
    # Jetzt gibt es die Verbindung: diese Zeile liest, was der Lauf
    # aufgestellt bekommen hat, und
    # test_die_nachbarschaft_ist_die_der_vorgabe haelt BAR_EVERYTHING
    # gegen die Auslieferung. Damit reicht EINE Aenderung an der Vorgabe.
    assert run.mark("left").split(",") == [
        _marke(modul) for modul in BAR_EVERYTHING["bar"]["modules_left"]
    ], run.report

    # Die ARBEITSBEREICHE stehen in der Mitte, seit der Nutzer am
    # 12.08.2026 "in der mitte die arbeitsbereiche" bestellt hat. Der
    # Platz ist derselbe geblieben und seine Eigenschaft auch: was in der
    # Mitte eines Gtk.CenterBox haengt, wird gemessen und nie
    # eingeklappt. Vorher lag dort der Fenstertitel - der steht jetzt
    # links, gibt weiter nach statt zu weichen, und wird ebenfalls nicht
    # eingeklappt (siehe place() in ags-bar.template).
    assert run.mark("center") == "workspaces", run.report

    # bar-overflow steht als erstes Kind im rechten Kasten.
    #
    # custom-media steht direkt dahinter, also GANZ VORN unter den
    # Modulen: die Reihenfolge im rechten Kasten ist zugleich die
    # Einklappreihenfolge, von innen nach aussen. Was gerade laeuft, ist
    # damit das erste, was ins Aufklappfenster wandert - und es ist auch
    # das breiteste der vier neuen, weil es einen Titel traegt und kein
    # Zeichen.
    #
    # custom-privacy und custom-updates stehen ganz hinten, kurz vor
    # dem Kontrollzentrum, aus demselben Grund umgekehrt.
    #
    # tray STEHT SEIT DEM 20.08.2026 DIREKT HINTER custom-media und nicht
    # mehr hinter dem Akku (Aufgabe 42): die Ablage waechst um ein ganzes
    # Symbol, sobald ein fremdes Programm eines hineinstellt, und das
    # Wachstum geht nach INNEN - an ihrem alten Platz hat es GEMESSEN
    # sechs Klickziele um dieselben 160 Punkte nach links geschoben. Die
    # ganze Begruendung mit der Messung steht bei _modules_right in
    # src/style_definition.py.
    assert run.mark("right").split(",") == [
        "bar-overflow",
        "custom-media", "tray",
        "custom-floating-layouts", "custom-helpers",
        # custom-hardware stand hier, zwischen bluetooth und pulseaudio.
        # Es steht seit dem 17.08.2026 LINKS neben dem Datum - bestellt:
        # "hardware monitor icon soll nach links recht neben die zeit
        # anzeige".
        "custom-disk", "custom-wallpaper",
        "network", "bluetooth",
        "pulseaudio", "pulseaudio#microphone", "battery",
        "custom-privacy", "custom-updates",
        # custom-theme steht zwischen den beiden bedingten Modulen und
        # dem Kontrollzentrum, also GANZ AUSSEN und damit als vorletztes
        # in der Einklappreihenfolge. Der Nutzer hat das Zeichen fuer das
        # Aussehen mehrfach vermisst; weiter vorn waere es auf einem
        # schmalen Schirm als eines der ersten hinter dem Knopf
        # verschwunden.
        "custom-theme", "custom-system"], run.report

    # Und nichts ist eingeklappt: dieser Lauf laedt KEIN Stylesheet,
    # also sind die Module schmal, und sein Schirm ist 3840 px breit.
    # Ein eingeklapptes Modul hier hiesse, dass die Regel klappt, ohne
    # dass Platz fehlt.
    assert run.mark("gefaltet") == "", (
        "auf einem 3840 px breiten Schirm ohne Stylesheet passt alles - "
        "trotzdem liegt etwas im Aufklappfenster:\n" + run.report)


def test_every_script_module_shows_what_its_script_answered(run):
    """Die Kette vom Skript bis auf den Schirm, einmal ganz.

    Ein Modul, das seinen Kasten baut und seine Antwort nicht anzeigt,
    ist von aussen dasselbe wie eines, das gar nichts tut - und beide
    bestehen jede Textsuche in der Vorlage.
    """
    shown = dict(entry.split("=", 1) for entry in run.mark("shown").split(",")
                 if "=" in entry)

    expected = {
        "custom-date": "DATUM", "custom-clocks": "UHREN",
        "custom-weather": "WETTER", "custom-hypr-shortcuts": "TASTEN",
        "custom-floating-layouts": "LAYOUTS", "custom-helpers": "HELFER",
        "custom-hardware": "HARDWARE",
    }
    for name, text in expected.items():
        assert shown.get(name) == text, (
            f"{name} zeigt {shown.get(name)!r} statt {text!r}:\n" + run.report)


def test_the_five_shared_modules_read_one_answer(run):
    """Ton, Mikrofon, Akku, Netz und Bluetooth kommen aus EINEM Aufruf.

    Der Gegenbeweis dazu, dass sie fuenf einzelne Skripte sind: es gibt
    nur status.sh im Attrappenverzeichnis, und alle fuenf zeigen etwas.
    Waere einer der fuenf ein eigener Aufruf, faende er dort nichts.
    """
    shown = dict(entry.split("=", 1) for entry in run.mark("shown").split(",")
                 if "=" in entry)

    for name, text in (("pulseaudio", "TON"), ("pulseaudio#microphone", "MIKRO"),
                       ("battery", "AKKU"), ("network", "NETZ"),
                       ("bluetooth", "BLAU")):
        assert shown.get(name) == text, (
            f"{name} zeigt {shown.get(name)!r} statt {text!r}:\n" + run.report)


def test_the_workspace_buttons_come_from_the_detected_layout(run):
    """workspaces.json ist die Quelle, nicht eine Zehnerreihe.

    Drei Knoepfe, weil die Datei drei Bereiche fuer diesen Schirm nennt -
    und der dritte traegt das Zeichen AUS DER DATEI und nicht das aus der
    Vorlage: das Laptop-Symbol auf dem Bereich, den der eingebaute Schirm
    allein haelt, ist die einzige Zuordnung, die erst auf dem
    Schreibtisch des Nutzers entsteht.
    """
    buttons = run.mark("workspaces").split(",")
    assert len(buttons) == 3, (
        f"die Leiste zeigt {len(buttons)} Arbeitsbereiche statt der drei "
        "aus workspaces.json:\n" + run.report)
    assert buttons[2].startswith("LAPTOP["), (
        "das Zeichen aus workspaces.json hat das aus der Vorlage nicht "
        f"ersetzt: {buttons[2]}\n" + run.report)
    assert all("empty" in button for button in buttons), (
        "ohne Compositor hat kein Bereich Fenster, also muessen alle drei "
        f"Knoepfe .empty tragen: {buttons}\n" + run.report)


def test_a_click_on_the_date_reaches_a_function_and_not_a_process(run):
    """Der Grund, aus dem die Leiste ueberhaupt nach AGS gehoert.

    Das Waybar-Modul hatte `"on-click": "ags request calendar"`: ein
    Prozessstart, der einen Socket oeffnet, um denselben Prozess zu
    erreichen, in dem das Fenster liegt. Hier wird die Funktion
    aufgerufen, die app.ts uebergeben hat - und das Kind kann sie
    mitschreiben, weil sie ihm gehoert.

    BEIDE TASTEN, seit dem 12.08.2026. Die rechte oeffnet das
    Meldungszentrum, und das ist eine Reparatur: seine bis dahin
    einzigen zwei Eingaenge waren die bedingte Glocke und `custom/clocks`,
    das ohne eingestellte Zusatzuhr einen leeren Text ausgibt und damit
    unsichtbar ist. Auf einer frischen Installation war der Verlauf der
    Meldungen also nicht erreichbar, solange nichts anlag.

    Sortiert verglichen: welche Reihenfolge Gtk.Widget seine Controller
    zurueckgibt, ist nicht zugesagt, und ein Test, der an ihr haengt,
    misst das Toolkit statt die Leiste.
    """
    assert sorted(run.mark("toggled").split(",")) == [
        "1=calendar", "3=notifications"], (
        "die zwei Tasten des Datums erreichen nicht Kalender und "
        "Meldungszentrum:\n" + run.report)


def test_the_bar_is_as_thick_as_the_size_table_says(run):
    """Die Dicke kommt aus src/sizes.py und nicht aus einer 50.

    Gemessen am zugeteilten Platz des Fensters, nicht an der Vorlage: was
    dort steht, prueft tests/src/test_sizes.py, und was daraus auf dem
    Schirm wird, nur das hier.

    QUER, nicht laengs: die Kopfleiste ist so breit wie der Schirm, und
    ihre Dicke ist ihre HOEHE.
    """
    sys.path.insert(0, str(SRC))
    try:
        import sizes
    finally:
        sys.path.remove(str(SRC))

    expected = int(sizes.value_of("STYLE_BAR_THICKNESS", {}))
    width, height = run.mark("allocated").split("x")

    assert int(height) > 0 and int(width) > 0, run.report
    assert run.mark("thickness") == str(expected), (
        f"die erzeugte Leiste traegt {run.mark('thickness')}, die Tabelle "
        f"sagt {expected}:\n" + run.report)

    # DASS DIE ZAHL AUCH AUF DEM SCHIRM ANKOMMT, PRUEFT DIESER LAUF NICHT
    #     Er laedt ABSICHTLICH kein Stylesheet - er misst, WAS die Leiste
    #     enthaelt, nicht wie gross das wird. Ohne bar.css gilt Adwaita,
    #     und dessen Knoepfe haben andere Masse als unsere; ein
    #     Gtk.Window wird ausserdem nie kleiner als sein Inhalt, also
    #     saehe man hier die Adwaita-Groesse und nicht die der Tabelle.
    #
    #     Die Frage ist deshalb dort, wo sie hingehoert:
    #     test_no_module_is_taller_than_the_bar_it_hangs_in misst MIT
    #     Stylesheet und ueber vier Groessenfaktoren, ob die Dicke aus
    #     der Tabelle fuer das hoechste Modul reicht.


def test_the_run_produced_no_critical_warning(run):
    """Eine kritische GTK-Meldung ist in diesem Projekt ein Testfehler.

    Drei sind erlaubt und alle drei sagen dasselbe: ohne Compositor gibt
    es keinen Hyprland-Socket, ohne Sitzungsbus keine Statusablage, ohne
    pipewire-Socket keinen Tondienst. Das sind die Antworten dieser
    Umgebung, nicht Fehler der Leiste - und sie stehen NAMENTLICH hier,
    damit eine vierte auffaellt.

    DIE DRITTE KAM AM 20.08.2026 DAZU, und sie ist keine Aufweichung,
    sondern das Gegenstueck zum Test darunter: die Leiste laesst sich
    seither von wireplumber wecken, statt die Lautstaerke nur im Takt
    abzufragen (tonVerbinden() in ags-bar.template). `run` reicht ein
    EIGENES, leeres XDG_RUNTIME_DIR durch und kein PIPEWIRE_RUNTIME_DIR
    - dort gibt es garantiert keinen pipewire-Socket, und die Klage ist
    die RICHTIGE Antwort darauf.
    test_the_bar_says_so_when_it_cannot_reach_wireplumber haelt fest,
    dass sie ueberhaupt kommt; dass sie hier stehen DARF, macht sie also
    nicht unsichtbar.
    """
    expected = (
        "Kein Hyprland-Ereignissocket",
        "org.kde.StatusNotifierWatcher gehoert schon einem anderen Programm",
        "keine Verbindung zu wireplumber",
    )
    unexpected = [line for line in run.stderr.splitlines()
                  if ("CRITICAL" in line or "WARNING" in line)
                  and not any(text in line for text in expected)]

    assert unexpected == [], (
        "die Leiste hat sich beklagt:\n" + "\n".join(unexpected))
    assert run.returncode == 0, run.report


def test_the_bar_says_so_when_it_cannot_reach_wireplumber(run):
    """Ohne Tondienst faellt die Leiste auf den Takt zurueck - und SAGT es.

    SEIT DEM 20.08.2026 hat die Leiste zwei Wege zur Lautstaerke: die
    Meldung von wireplumber und, darunter, den Takt von 2000 ms. Der
    Rueckfall ist der Sinn der Sache - er ist auch der gefaehrlichste
    Teil daran, denn er funktioniert LAUTLOS. Eine Maschine, auf der die
    Anbindung nie zustande kommt, saehe genau aus wie eine, auf der sie
    laeuft, nur langsamer; und "die Anzeige haengt manchmal" ist die
    Sorte Fehler, die niemand meldet und niemand findet.

    Dieser Lauf IST diese Maschine: eigenes, leeres XDG_RUNTIME_DIR, kein
    pipewire-Socket. Geprueft wird deshalb beides zusammen -

        die Klage steht auf stderr, mit dem Grund und mit dem, was
        stattdessen passiert ("aus dem Takt"),

    und, im selben Lauf, dass die fuenf Module aus status.sh trotzdem
    dastehen. Ein Rueckfall, der die Leiste mitnimmt, waere keiner.
    """
    beschwerde = [line for line in run.stderr.splitlines()
                  if "wireplumber" in line]

    assert beschwerde, (
        "ohne pipewire-Socket muss die Leiste sagen, dass sie den Ton "
        "nur noch im Takt bekommt - sie hat geschwiegen:\n" + run.report)
    assert any("Takt" in line for line in beschwerde), (
        "die Klage nennt den Grund, aber nicht die Folge - ohne sie weiss "
        "niemand, ob die Anzeige noch stimmt:\n" + "\n".join(beschwerde))

    # Und Ton und Mikrofon stehen trotzdem da - aus dem Takt, wie eh und
    # je. `pulseaudio` und `pulseaudio#microphone` sind ihre Waybar-Namen,
    # STATUS_KEYS gibt die Texte vor.
    shown = dict(entry.split("=", 1) for entry in run.mark("shown").split(",")
                 if "=" in entry)
    for name, text in (("pulseaudio", "TON"),
                       ("pulseaudio#microphone", "MIKRO")):
        assert shown.get(name) == text, (
            f"ohne wireplumber zeigt {name} {shown.get(name)!r} statt "
            f"{text!r} - der Rueckfall traegt nicht:\n" + run.report)




# --------------------------------------------------------------------
# passt die Leiste auf den Schirm
# --------------------------------------------------------------------
#
# WAS DAS SCHLIESST, UND WAS ES GEKOSTET HAT, DASS ES FEHLTE
#     Am 11.08.2026 wurde die Grundschrift des Schreibtischs von 13 auf
#     24 px angehoben (Commit b96f90d) und die Leiste von 50 auf 92.
#     Die Module wuchsen mit, der Schirm nicht. Auf dem Bild
#     iso/out/run-release-installed/key-16-07-sitzung-nach-240s.png -
#     1280x800, der Abnahmelauf desselben Tages - ist vom Hardwaremodul
#     noch "No" zu lesen, und alles rechts davon fehlt.
#
#     Aufgefallen ist das einem MENSCHEN, der ein Bild angesehen hat.
#     Keine der 1817 Zusicherungen der Suite konnte es sehen: sie messen,
#     WAS die Leiste enthaelt, und keine, wie gross das wird.
#
# ZWEI FRAGEN AUF ZWEI ACHSEN, UND SIE WERDEN VERSCHIEDEN BEANTWORTET
#     Die Leiste laeuft seit dem 12.08.2026 wieder waagerecht.
#
#       Laengs   Passt die Summe aller Module in die BREITE des Schirms.
#                Das haengt am TEXT, den die Skripte gerade liefern, und
#                aendert sich damit im Betrieb - deshalb entscheidet es
#                eine Regel zur Laufzeit, und deshalb wird sie hier auf
#                vier Schirmbreiten nachgemessen.
#       Quer     Passt das hoechste Modul in die DICKE der Leiste. Das
#                haengt an keinem Text - eine Beschriftung bricht nicht
#                um -, sondern nur an Sprossen aus src/sizes.py. Es ist
#                damit eine Eigenschaft des Entwurfs und keine des
#                Betriebs, und es wird ueber vier GROESSENFAKTOREN
#                nachgemessen statt ueber vier Schirme.
#
#     Beide getrennt, weil eine Leiste, deren Module alle in die Breite
#     passen und von denen die Haelfte oben und unten angeschnitten
#     wird, jede Breitenpruefung besteht.
#
# DIE BREITEN, UND WARUM DIESE
#     1280  der Schirm des Abnahmelaufs (1280x800), und zugleich die
#           Klasse, in der die alten Notebooks liegen. Hier passt bei
#           Vorgabegroesse laengst nicht alles, und das ist die
#           interessante Zeile.
#     1366  1366x768, der verbreitetste Notebookschirm ueberhaupt.
#     1600  1600x900. Der Zwischenschritt.
#     1920  Full HD. Hier steht heute alles auf der Leiste, und die
#           Zusicherung unten besteht darauf.

# Was die Skriptmodule fuer diese Messung sagen. Nicht die Kunstwoerter
# von oben, sondern das, was auf dem Bild des Abnahmelaufs steht: die
# Groesse der Leiste ist die Groesse ihres TEXTES, und "DATUM" ist fuenf
# Zeichen, wo "Di 11.08.2026" dreizehn hat.
#
# EIN LAPTOP MIT DEN AUSGELIEFERTEN EINSTELLUNGEN, UND DAS IST SEIT DEM
# 12.08.2026 DER GANZE PUNKT DIESER TABELLE
#     Vorher standen hier vier LEERE Antworten - microphone, battery,
#     network und bluetooth -, und ein leeres Modul ist ein Modul ohne
#     Breite: `applyPayload` blendet es aus, und ein unsichtbares Widget
#     beantwortet gtk_widget_measure mit 0. Die Leiste, die hier gemessen
#     wurde, war also eine mit vier Modulen weniger als die auf dem
#     Schirm des Nutzers.
#
#     Was das gekostet hat, ist gemessen: bei der damals ausgelieferten
#     Groesse wollte diese Leiste 1609 px und alles passte auf 1920. Mit
#     denselben vier Modulen SPRECHEND waren es 2528 px, und auf 1920
#     klappten SECHS Module ein. Der Nutzer am 12.08.2026: "akku anzeige
#     fehlt btop in der waybar mikrofon und lautstaerke fehlt". Sie
#     fehlten nicht - sie lagen hinter dem Knopf, und keine Zusicherung
#     dieser Datei konnte das sehen, weil die Messung sie gar nicht erst
#     eingeschaltet hatte.
#
#     Leer bleiben hier nur noch die drei, die auf einer frischen
#     Installation WIRKLICH schweigen, und jede aus einem Grund, der in
#     ihrer Vorlage steht: clocks.sh ohne konfigurierte zweite Zeitzone,
#     weather.sh ohne Ort, floating-layouts ohne gespeicherte Anordnung.
#     Alles andere spricht auf einem Laptop vom ersten Anmelden an.
#
# UND DIE GLYPHEN KOMMEN AUS DER SSOT, WEIL SIE HIER GEFEHLT HABEN
# (Aufgabe #96, 12.08.2026)
#     Bis heute stand in dieser Tabelle KEIN EINZIGES Nerd-Font-Zeichen.
#     Jeder Eintrag begann mit einem blanken Leerzeichen - genau dort,
#     wo die Vorlage ein Glyph setzt:
#
#         hier          " Di 12.08.2026  14:07"
#         date-config   date +"{ICON_CALENDAR}  %a %d.%m.%Y  %H:%M"
#
#     Die Messung war damit je sprechendem Modul um ein Zeichen zu
#     schmal, bei acht sprechenden Modulen also um acht. Daher stammte
#     die Aussage "bei 1920 passt alles". Auf out/render/leiste-1920.png
#     - einem Bild der WIRKLICHEN Leiste bei 1920 - lagen zwei Module
#     hinter dem Einklapp-Knopf.
#
#     Eine Attrappe, die neben der Wahrheit steht, misst die Attrappe.
#     Die Zeichen stehen deshalb nicht mehr hier, sondern kommen aus
#     src/icons_db.py - derselben Datei, aus der der Erzeuger die
#     Vorlagen fuellt. Von Hand steht hier nur noch, was eine
#     ENTSCHEIDUNG ist: welcher Zustand gemessen wird (ein Laptop, frisch
#     angemeldet) und mit welchen Zahlen.
#
#     `hardware-monitor.py` stand ausserdem auf " 12% 4.2G", und diese
#     Zeichenkette kann die Vorlage gar nicht erzeugen: sie baut ihren
#     Text aus "{ICON_COOLER} 45°C", "{ICON_TEMP} 62°C" und
#     "{ICON_RGB} 3" - und ohne Wasserkuehlung und ohne eigene
#     Grafikkarte, also auf jedem Laptop, aus "{ICON_MOTHERBOARD} No HW".
#     Genau das steht auch auf out/render/leiste-1920.png.


def _icons() -> dict[str, str]:
    """Die Zeichentabelle des Erzeugers.

    Ueber sys.path und nicht ueber einen Import oben: src/ ist kein
    Paket, und dieselbe Vorrichtung steht weiter unten in den Tests, die
    src/sizes.py brauchen.
    """
    sys.path.insert(0, str(SRC))
    try:
        import icons_db
        return dict(icons_db.icons)
    finally:
        sys.path.remove(str(SRC))


_ICONS = _icons()


def _glyph(name: str) -> str:
    """Ein Zeichen aus der SSOT, oder ein Abbruch.

    KEIN Rueckfall, und das ist der Punkt: icons_db.get_icon() antwortet
    auf einen unbekannten Namen mit "?" - einem Zeichen, das eine Breite
    hat und deshalb NICHT auffaellt. Eine Messvorrichtung, die sich
    stillschweigend mit einem Fragezeichen begnuegt, ist wieder die
    Attrappe neben der Wahrheit.
    """
    glyph = _ICONS.get(f"ICON_{name}")
    if not glyph:
        raise KeyError(
            f"src/icons_db.py kennt ICON_{name} nicht - entweder ist das "
            "Zeichen umbenannt worden, dann gehoert der Name hier "
            "nachgezogen, oder es fehlt, dann malt auch die Leiste nichts")
    return glyph


FIT_MODULES = {
    "date.sh": f"{_glyph('CALENDAR')}  Di 12.08.2026  14:07",
    "clocks.sh": "",
    "weather.sh": "",
    "hypr-shortcuts.py": f"{_glyph('KEYBOARD')}  66",
    "floating-layouts-bar.sh": "",
    "helpers-bar.py": f"{_glyph('CODE')}  8",
    # ZWEI PROZENTZAHLEN UND NICHT "No HW", seit dem 13.08.2026.
    #
    # Der Rueckfalltext stand hier, weil das Skript bis dahin nur nach
    # Wasserkuehlung, Grafikkarte und RGB fragte und auf einem Notebook
    # keines davon fand. Seither liest es Prozessorlast und
    # Arbeitsspeicher aus /proc - siehe hardware-monitor-config.template -,
    # und die stehen auf JEDER Maschine da. Ein Messaufbau, der den
    # Rueckfalltext nachstellt, maesse ein Modul von 76 px, das es nicht
    # mehr gibt.
    "hardware-monitor.py": f"{_glyph('CPU')} 12% {_glyph('RAM')} 38%",
    # DIE DREI BEDINGTEN, IM RUHEZUSTAND - und sie haben hier bis zum
    # 13.08.2026 gefehlt.
    #
    # Sie stehen in der ausgelieferten Vorgabe, die Leiste baut sie also
    # und ruft ihre Skripte. Im Bauplatz gab es die drei Dateien nicht,
    # der Aufruf scheiterte, und scriptModule() blendete den Kasten aus
    # - das sah aus wie "spielt nichts, steht nichts an, hoert niemand
    # zu" und war in Wahrheit "das Skript ist nicht da".
    #
    # Solange der Fehlerzweig dasselbe tat wie der Ruhezustand, fiel das
    # nicht auf. Seit er das Warnzeichen zeigt (siehe scriptModule in
    # ags-bar.template), sind es zwei verschiedene Leisten - und die
    # gemessene waere die mit drei Warnzeichen, die es auf keiner
    # Installation gibt. Leer und nicht fehlend ist der Ruhezustand
    # einer frischen Maschine; dieselben drei Attrappen stehen aus
    # demselben Grund in tests/render/desktop_session.py.
    "media.sh": "",
    "updates.sh": "",
    "privacy.sh": "",
}

# DREI PROZENTZAHLEN, SEIT DEM 19.08.2026 - genau die, die
# bar-status-config.template heute ausgibt. Ein Messaufbau, der Texte
# nachstellt, die das Skript nicht (mehr) schreibt, misst eine Leiste,
# die es nicht gibt.
#
# DIE GESCHICHTE DIESER FUENF ZEILEN, WEIL SIE DIE ZAHLEN UNTEN ERKLAERT
#     12.08.2026  alle vier Zahlen weg ("Symbol allein, Zahl im Tooltip -
#                 so macht es macOS").
#     13.08.2026  der Akku bekommt seine zurueck ("ich will auch eine
#                 prozentzahl haben fuer die batterie nicht nur ein
#                 symbol").
#     19.08.2026  Ton und Mikrofon bekommen ihre zurueck: "in dem header
#                 fehlen ausserdem beim lautstaerke und mikrofon icon die
#                 prozent zahlen auf wie viel prozent sie gestellt sind".
#                 Auf Nachfrage ausdruecklich beide DAUERHAFT mit Zahl,
#                 so wie der Akku es macht. Die ganze Begruendung steht
#                 im Kopf von bar-status-config.template.
#
# Das Netz behaelt seine Zahl im Tooltip: sie wird vom Zeichen getragen
# (nf-md-wifi_strength_1..4, vier Balken fuer vier Viertel), und darum
# ist sie daneben keine zweite Auskunft. Genau diese Voraussetzung fehlt
# bei Ton und Mikrofon - siehe wieder den Kopf der Vorlage.
#
# Das Bluetooth-Modul behaelt seine Zahl: sie ist die ANZAHL der
# verbundenen Geraete, und die malt kein Zeichen.
#
# WARUM "100%" UND "45%" UND NICHT ZWEIMAL DASSELBE
#     Es sind die Werte, die vor dem 12.08.2026 hier standen - damit
#     bleibt die Messung mit den Zahlen vergleichbar, die der Kopf der
#     Vorlage von damals nennt. Drei Stellen sind zugleich das Breiteste,
#     was das Skript schreiben kann.
#
#     GEMESSEN am 19.08.2026 auch im unguenstigsten Fall - BEIDE auf
#     "100%" -, weil die Schwelle darunter dafuer gerade stehen muss:
#     die Leiste will dann 1598 px statt 1586, und auf 1600 steht immer
#     noch alles. Die Einklappliste auf 1366 ist in beiden Faellen
#     dieselbe.
FIT_STATUS = {
    "audio": f"{_glyph('VOLUME_HIGH')} 100%",
    "microphone": f"{_glyph('MIC')} 45%",
    "battery": f"{_glyph('BATTERY_HIGH')} 87%",
    "network": _glyph("WIFI_3"),
    "bluetooth": f"{_glyph('BLUETOOTH_CONNECTED')} 2",
}

# Die Module, die der Nutzer am 12.08.2026 vermisst hat ("akku anzeige
# fehlt btop in der waybar mikrofon und lautstaerke fehlt"), mit ihren
# Namen auf der Leiste. Sie stehen hier, weil eine Zusicherung ueber
# "nichts ist eingeklappt" auch dann gruen ist, wenn ein Modul gar
# nicht erst gebaut wurde.
#
# ALLE VIER SIND SEIT DEM 13.08.2026 WIEDER AUF DER LEISTE.
#
# Am Abend des 12.08. waren zwei davon - der Mikrofonpegel und die
# Hardwareanzeige - ins Kontrollzentrum gezogen, weil der Nutzer rechts
# "EINE Statusgruppe aus Netz + Ton + Akku" bestellt hatte. Einen Tag
# spaeter hat er beide namentlich zurueckverlangt ("im header sollte
# btop dargestellt werden wie am anfang auch", "und lautstaerke und
# mikrofon auch"), und die Vorgabe stellt sie wieder auf.
#
# Ihre Zeile im Kontrollzentrum bleibt und wird hier nicht mehr geprueft:
# sie ist jetzt der zweite Weg zu einer Sache, die auf der Leiste steht,
# und kein Ersatz fuer ein verschwundenes Modul.
MISSED_ON_12_08 = ("battery", "pulseaudio", "pulseaudio#microphone",
                   "custom-hardware")

# Fuenf Breiten, und die schmalste ist seit dem 12.08.2026 dabei.
#
# 1024 ist der Fall, den es sonst nicht mehr gaebe: die ausgelieferte
# Leiste will seit dem Umbau 1210 px und passt damit auf jeden Schirm,
# den die vier anderen Zeilen nennen. Ein Einklapper, der nie einklappt,
# ist eine Regel ohne Messung - und die erste Sitzung auf einem alten
# 1024x768-Bildschirm waere der erste Lauf ueberhaupt.
#
# 1680 ist am 17.08.2026 dazugekommen, und zwar aus zwei Gruenden
# zugleich: 1680x1050 (WSXGA+) ist ein wirklicher Bildschirm, und es ist
# seit diesem Tag die Breite, ab der die ausgelieferte Leiste
# vollstaendig ankommt (COMPLETE_FROM unten). Eine Grenze, die zwischen
# zwei gemessenen Zeilen liegt, ist eine behauptete Grenze - die
# Zusicherungen darunter schlagen COMPLETE_FROM in genau dieser Tabelle
# nach.
WIDTHS = (1024, 1280, 1366, 1600, 1680, 1920)

# Auf welchen Breiten heute alles steht, was auf die Leiste gehoert.
#
# DIE ENTSCHEIDUNG, UND SEIT DEM 12.08.2026 IST SIE EINE ANDERE FRAGE
#     Die ausgelieferte Liste ist seit heute EINSTELLBAR
#     (user-settings.json, Abschnitt "bar"; siehe src/settings.py). Die
#     Vorgabe muss deshalb nicht mehr alles enthalten, was jemand
#     brauchen koennte, sondern das, was auf einem gewoehnlichen Schirm
#     VOLLSTAENDIG ANKOMMT - wer mehr will, schaltet es zu.
#
# GEMESSEN, UND ZWAR AN DER ECHTEN OBERFLAECHE UND NICHT NUR HIER
#     tests/render/shoot.py, 12.08.2026, verschachteltes Hyprland mit
#     den WIRKLICHEN Skripten dieser Maschine:
#
#         mittags  achtzehn Module, 1902 px Mindestbreite. Bei 1920
#                  stand alles; bei 1366 lagen SECHS hinter dem
#                  Einklapp-Knopf (custom/helpers, network, bluetooth,
#                  custom/hardware, pulseaudio, pulseaudio#microphone),
#                  bei 1280 sieben.
#         abends   elf Module, und die Zahl steht unten in
#                  test_the_bar_holds_every_module_on_the_common_screen.
#                  Bei 1366 steht alles, ohne Knopf.
#
# WARUM DIE ZAHL VON 1920 AUF 1366 GEHT
#     BESTELLT am 12.08.2026: die Leiste soll auf 1366x768 VOLLSTAENDIG
#     ankommen. Das ist der verbreitetste Notebookschirm ueberhaupt, und
#     eine Vorgabe, die dort sechs Module wegklappt, ist keine Vorgabe,
#     sondern eine Annahme ueber die Hardware des Nutzers.
#
#     Der Mittagsstand hatte dazu eine Gegenrechnung: kuerzen hiesse
#     sechs Module wegnehmen, darunter vier eben erst vermisste. Die
#     Rechnung stimmte und ihre Voraussetzung nicht mehr - die vier sind
#     nicht weg, sondern umgezogen (Kontrollzentrum, Abschnitt
#     SCHREIBTISCH), und was auf der Leiste bleiben soll, hat der Nutzer
#     am selben Abend selbst gesagt: "in der mitte die arbeitsbereiche
#     links die uhrzeit und datum den rest kennst du".
#
#     Die Breite, ab der es reicht, steht hier NICHT als gemessene Zahl -
#     sie waere eine zweite Kopie dessen, was die Messung selbst ergibt,
#     und muesste bei jeder Schriftaenderung nachgezogen werden. Was hier
#     steht, ist die Entscheidung.
#     UND AM 13.08.2026 IST SIE WIEDER 1600, UND ZWAR GEMESSEN
#         An diesem Tag hat der Nutzer die Kuerzung viermal beanstandet
#         ("rechts ist zu leer", "wir brauchen mehr informationen im
#         header", dazu Akku, Lautstaerke und Mikrofon namentlich) und
#         btop zurueckbestellt. Die Vorgabe traegt seither zwoelf Module
#         rechts und vier links; die Begruendung dafuer steht in
#         src/style_definition.py bei _modules_left.
#
#         GEMESSEN mit genau diesem Aufbau, Vorgabegroesse (20 px), zehn
#         Arbeitsbereichen, echten Zeichen:
#
#             Schirm   Mindestbreite   eingeklappt
#              1024        974         7 (alles ausser Datum und Zahnrad)
#              1280       1225         4 (hardware, disk, network, bluetooth)
#              1366       1322         3 (hardware, disk, network)
#              1600       1510         0
#              1920       1510         0
#
#         Die volle Liste WILL 1510 px. Auf 1366 fehlen also 144, und
#         drei Module wandern hinter den Knopf.
#
#         UND AM 17.08.2026 IST EIN MODUL DAZUGEKOMMEN, custom/theme.
#         Der Nutzer hat das Zeichen fuer das Aussehen zum wiederholten
#         Mal vermisst ("theme manager icon im header fehlt immernoch");
#         die ganze Begruendung steht in src/style_definition.py bei
#         _modules_right. NACHGEMESSEN im selben Aufbau:
#
#             Schirm   Mindestbreite   eingeklappt
#              1024       1022         7
#              1280       1273         4 (hardware, disk, network, bluetooth)
#              1366       1273         4 (hardware, disk, network, bluetooth)
#              1600       1558         0
#              1920       1558         0
#
#         48 Punkte mehr - die Zeichenbreite des Knopfes und kein Rand,
#         weil er im Block am rechten Ende steht (margin-left/right: 0).
#         Die Zahl unten bleibt deshalb 1600: 1558 passt darauf.
#
#         AUF 1366 FAELLT DAFUER EIN MODUL MEHR, und zwar `bluetooth`.
#         Das steht hier, weil es NICHT still passieren darf - der
#         Nutzer hat genau diese Sorte Kuerzung am 13.08.2026 viermal
#         beanstandet. Es ist nicht fort, sondern hinter dem
#         Einklapp-Knopf, und der Schirm des Nutzers ist 1920x1200 bei
#         Faktor 1.00, wo alles steht.
#
#         DAS IST EIN BEFUND UND KEINE ENTSCHEIDUNG DIESER ZEILE. Die
#         beiden groessten Posten sind die Arbeitsbereiche (408 px bei
#         zehn Stueck) und das Datum (313 px mit vollem Jahr); beide sind
#         bestellt worden, wie sie sind. Was sich ohne Informationsverlust
#         kuerzen liesse - custom/disk ist ein Knopf ohne Anzeige, das
#         Datum koennte das Jahr weglassen -, ist im Bericht vom
#         13.08.2026 aufgeschrieben und wartet auf die Entscheidung des
#         Nutzers.
#
#         Diese Zeile sagt deshalb nur, ab welchem Schirm heute alles
#         steht, und test_the_bar_holds_every_module_on_the_common_screen
#         haelt zusaetzlich fest, WAS auf 1366 einklappt - damit ein
#         weiteres Modul nicht unbemerkt dazukommt.
#
#     UND AM NACHMITTAG DES 17.08.2026 IST SIE 1680, NICHT MEHR 1600.
#     DAS IST DIE ZAHL, UM DIE ES HIER GEHT, UND SIE STEHT AUCH IM
#     BERICHT AN DEN NUTZER.
#
#         Zwei Aenderungen desselben Tages, beide woertlich bestellt:
#
#             "die tastatur icon fehlt auch noch links neben dem datum"
#             -> custom/keyboard, ein NEUES Modul, GEMESSEN 92 px breit
#                plus 15 px Aussenrand.
#             "hardware monitor icon soll nach links recht neben die
#              zeit anzeige"
#             -> custom/hardware ist von der rechten in die linke
#                Haelfte gezogen. Es ist NICHT weg und nicht kleiner; es
#                steht woanders.
#
#         GEMESSEN im selben Aufbau wie die Tabellen darueber
#         (Vorgabegroesse, zehn Arbeitsbereiche, echte Zeichen):
#
#             Schirm   Mindestbreite   eingeklappt
#              1024        705         10
#              1280       1243         7
#              1366       1339         6
#              1600       1590         3 (disk, network, bluetooth)
#              1920       1680         0
#
#         Die volle Liste WILL 1680 px statt 1558. Der Zuwachs sind 122
#         Punkte: 107 fuer das neue Modul mitsamt Rand, 15 fuer den
#         Randwechsel, den der Umzug der Hardwareanzeige mit sich bringt.
#
#         NACHGEMESSEN am 17.08.2026, nachdem der Nutzer "weniger platz
#         fuer keyboard icon" verlangt hat: zwischen Zeichen und Kuerzel
#         standen ZWEI Leerzeichen - als einzige Stelle der ganzen
#         Leiste. Mit einem misst das Modul 79 px statt 92, also 13
#         weniger, und mitsamt Rand 94 statt 107. Auf 1280 klappt
#         seither EIN Modul weniger ein (7 statt 8); auf 1366, 1600 und
#         1680 aendert sich nichts - 13 Punkte sind schmaler als jedes
#         Modul, das dort an der Reihe waere.
#
#         Zum Vergleich, im selben Lauf gemessen: custom-date 313 px
#         (Datum UND Uhrzeit in einer Zeile), custom-hardware 165 px.
#         Die Belegungsanzeige ist damit das schmalste der drei.
#
#         AUF 1366 FALLEN DAMIT SECHS STATT VIER, und die zwei
#         zusaetzlichen sind `pulseaudio`, `pulseaudio#microphone` und
#         `battery` gegen `custom-hardware`, das dort jetzt STEHT.
#         Warum: die Einklappreihenfolge geht ERST durch den rechten
#         Kasten und dann durch den linken (siehe `order` in
#         ags-bar.template). custom/hardware ist mit 165 px der
#         breiteste einklappbare Posten, und es liegt seit heute im
#         linken Kasten - also gibt der rechte sechs kleine Module ab,
#         wo vorher vier reichten, weil eines davon das grosse war.
#
#         DAS STEHT HIER, WEIL ES NICHT STILL PASSIEREN DARF. Der
#         Nutzer hat genau diese drei am 13.08.2026 namentlich verlangt
#         ("es fehlt auch ein batterie icon ich weiss nicht wie voll der
#         laptop ist" - "und lautstaerke und mikrofon auch"). Auf SEINEM
#         Schirm - 1920x1200 bei Faktor 1.00 - steht weiterhin alles,
#         nichts liegt hinter dem Knopf. Auf einem 1366er Notebook ist
#         das seit heute anders, und die Entscheidung darueber gehoert
#         ihm: entweder die Belegungsanzeige oder die Hardwareanzeige
#         waere dort der Posten, den man wieder nach rechts stellt.
#
#     UND AM 19.08.2026 IST SIE 1600, ALSO EINE STUFE KLEINER - OBWOHL
#     ZWEI MODULE AN DIESEM TAG GEWACHSEN SIND.
#
#         BESTELLT: "in dem header fehlen ausserdem beim lautstaerke und
#         mikrofon icon die prozent zahlen auf wie viel prozent sie
#         gestellt sind", beide dauerhaft mit Zahl. Ton und Mikrofon
#         tragen ihre Prozentzahl seither auf der Leiste; die
#         Begruendung steht im Kopf von bar-status-config.template.
#
#         GEMESSEN mit genau diesem Aufbau (Vorgabegroesse, zehn
#         Arbeitsbereiche, echte Zeichen), einmal ohne und einmal mit den
#         beiden Zahlen:
#
#             Schirm   ohne Zahl   mit Zahl   eingeklappt (mit Zahl)
#              1024       1022       1022     9
#              1280       1208       1208     6
#              1366       1361       1298     5
#              1600       1520       1586     0
#              1680       1520       1586     0
#              1920       1520       1586     0
#
#         DIE EINZELNEN MODULE, im selben Lauf gemessen:
#
#             pulseaudio             51 px -> 90 px   (+39, "100%")
#             pulseaudio#microphone  51 px -> 78 px   (+27, "45%")
#
#         Zusammen 66 px, und genau um die steigt die Mindestbreite der
#         vollen Liste: 1520 -> 1586.
#
#         WARUM DIE ZAHL TROTZDEM FAELLT: 1680 war seit dem Vormittag
#         des 19.08.2026 stehengeblieben. An dem Tag ist der doppelte
#         Modulrand gefallen (siehe FOLDED_ON_COMMON_NOTEBOOK unten), und
#         die volle Liste wollte seither 1520 statt 1680 px - die Zahl
#         hier wurde nur nicht nachgezogen. Sie ist damit KEINE
#         Aufweichung: 1600 wird jetzt mitgeprueft, wo es vorher
#         uebersprungen wurde (siehe
#         test_a_screen_with_room_keeps_every_module_on_the_bar).
#
#         DER SCHIRM DES NUTZERS - 1920x1200 bei Faktor 1.00 - traegt
#         weiterhin alles.
#
#     UND NOCH AM SPAETEN 19.08.2026 IST DIE VOLLE LISTE 81 PUNKTE
#     SCHMALER GEWORDEN - DIE ZAHL HIER BLEIBT TROTZDEM 1600.
#
#         BESTELLT: "die kaestchen viel zu breit sie koennen alle enger
#         nebene einandern sein und ich rede hier nur von der rechten
#         seite nicht linksen siete die links ist in ordnung", dazu "die
#         icon im header sind immernoch nicht zentreirt in ihrem
#         kaestchen". Beides hatte dieselbe Ursache; sie steht in
#         bar-style.template ueber #modules-right .bar-module > label
#         und in sizes.py bei STYLE_BAR_SYMBOL_WIDTH.
#
#         GEMESSEN mit genau diesem Aufbau (Vorgabegroesse, zehn
#         Arbeitsbereiche, echte Zeichen), vorher und nachher:
#
#             Schirm   vorher   nachher   eingeklappt (nachher)
#              1024     1022      1016     9
#              1280     1208      1262     5   (vorher 6)
#              1366     1298      1346     4   (vorher 5)
#              1600     1586      1505     0
#              1680     1586      1505     0
#              1920     1586      1505     0
#
#         DIE EINZELNEN MODULE DER RECHTEN HAELFTE, im selben Lauf:
#
#             custom-disk             48 px -> 36 px
#             network                 51 px -> 36 px
#             bluetooth               53 px -> 53 px  (Text, unberuehrt)
#             pulseaudio              90 px -> 90 px  (Text)
#             pulseaudio#microphone   78 px -> 78 px  (Text)
#             battery                 78 px -> 78 px  (Text)
#             custom-theme            48 px -> 36 px
#             custom-system           48 px -> 36 px
#
#         Dazu fuenf Fugen von 12 auf 6 Punkte. Die rechte Haelfte misst
#         damit 473 statt 554 Punkte; die linke ist unveraendert, wie
#         bestellt.
#
#         WARUM DIE ZAHL HIER TROTZDEM STEHENBLEIBT: die volle Liste
#         will 1505 px, und die naechstkleinere Zeile der Tabelle oben
#         ist 1366. 1505 passt nicht auf 1366, also waere jede kleinere
#         Zahl hier eine Behauptung statt einer Messung. 1600 ist
#         weiterhin die kleinste GEMESSENE Breite, auf der alles steht -
#         mit 95 px Luft statt 14.
#
#     UND AM 20.08.2026 SIND ES 1504 PUNKTE - EINER WENIGER, UND DIE
#     ZAHL HIER BLEIBT WIEDER 1600 (Aufgabe 41).
#
#         BESTELLT: "wlan symbol immernoch nicht zentriert" und "das
#         control zentrum icon soll genau platziert werden rechts wie
#         links der kalender". Das Zeichen sitzt seither in einer
#         eigenen Zelle (ModuleLabel in ags-bar.template, .bar-symbol in
#         bar-style.template), und der Trenner zwischen Zeichen und Wert
#         kommt aus der Abstandsleiter statt als Leerzeichen aus zwoelf
#         Skripten.
#
#         GEMESSEN mit genau diesem Aufbau (Vorgabegroesse, zehn
#         Arbeitsbereiche, echte Zeichen), vorher und nachher:
#
#             Schirm   vorher   nachher   eingeklappt (nachher)
#              1024     1016      1020     9
#              1280     1262      1256     5
#              1366     1346      1341     4
#              1600     1505      1504     0
#              1680     1505      1504     0
#              1920     1505      1504     0
#
#         DIE EINZELNEN MODULE MIT WERT, im selben Lauf - sie sind es,
#         die der Trenner betrifft:
#
#             custom-date            299 px -> 289 px
#             custom-hardware        151 px -> 153 px
#             custom-hypr-shortcuts   78 px ->  67 px
#             bluetooth               53 px ->  55 px
#             pulseaudio              90 px ->  92 px
#             pulseaudio#microphone   78 px ->  79 px
#             battery                 78 px ->  79 px
#
#         Die reinen Zeichenmodule bleiben Punkt fuer Punkt gleich
#         (36 px): ihre Zelle ist genau so breit, wie ihre Beschriftung
#         vorher mindestens war. Die beiden Module mit ZWEI Leerzeichen
#         (Datum, Tastenkuerzel) werden schmaler, die fuenf mit einem
#         um zwei Punkte breiter - STYLE_SPACE_4 ist eine halbe Sprosse
#         schmaler als ein Leerzeichen, aber die Zelle ist um zweieinhalb
#         breiter als der Vorschub eines Zeichens.
#
#         DAZU ZWOELF PUNKTE FUER DEN RECHTEN PLATTENRAND, und die sind
#         die zweite Bestellung: #modules-right traegt jetzt
#         margin-right, damit rechts derselbe Abstand zur Plattenkante
#         steht wie links (test_the_bar_keeps_the_same_edge_on_both_
#         sides). Auf 1024 px, wo neun Module eingeklappt sind und die
#         Ersparnis der Zellen deshalb gar nicht anfaellt, kosten sie
#         vier Punkte netto - die Leiste will dort 1020 statt 1016 und
#         passt weiter auf den Schirm.
#
#         WARUM DIE ZAHL HIER WIEDER STEHENBLEIBT: 1504 passt nicht auf
#         1366, also bliebe jede kleinere Zahl eine Behauptung. Die Luft
#         auf 1600 bleibt bei 96 Punkten.
#
#     UND AM 20.08.2026 IST DIE RECHTE HAELFTE UMGERAEUMT WORDEN, OHNE
#     DASS SICH EINE EINZIGE DIESER ZAHLEN BEWEGT HAT (Aufgabe 42).
#
#         BESTELLT: "ich wollte auch das du sie zentrierst die icon und
#         sie anders anordnest logisch gesehen im header". Bewegt hat
#         sich dabei genau ein Modul - `tray` steht jetzt an zweiter
#         Stelle statt an achter, weil es das einzige ist, dessen Breite
#         ein fremdes Programm bestimmt. Die ganze Begruendung steht bei
#         _modules_right in src/style_definition.py.
#
#         GEMESSEN im selben Aufbau, vorher und nachher:
#
#             Schirm   vorher   nachher   eingeklappt (nachher)
#              1024     1020      1020     9
#              1280     1256      1256     5
#              1366     1341      1341     4
#              1600     1504      1504     0
#              1680     1504      1504     0
#              1920     1504      1504     0
#
#         Punkt fuer Punkt dieselbe Leiste, und der Grund steht in
#         ags-tray.template: eine LEERE Ablage macht sich unsichtbar
#         (`box.set_visible(items.size > 0)`), und ein unsichtbares
#         Widget beantwortet gtk_widget_measure mit 0. Der Messaufbau
#         hier hat keinen Sitzungsbus, also ist sie in JEDER Zeile
#         dieser Tabelle leer - ein Umzug, der im Ruhezustand nichts
#         kostet und nichts spart.
#
#         WAS SICH AENDERT, SOBALD EIN SYMBOL DARIN LIEGT, steht
#         deshalb nicht in dieser Tabelle, sondern in der Messung bei
#         _modules_right: an ihrem alten Platz hat die Ablage sechs
#         Klickziele geschoben, an ihrem neuen schiebt sie keines.
COMPLETE_FROM = 1600

# Der verbreitetste Notebookschirm, und auf ihm reicht es seit dem
# 13.08.2026 nicht mehr fuer alles. Was dort einklappt, steht hier
# namentlich: die Zusicherung darueber ist nicht "es klappt etwas ein"
# (das waere mit jeder Verschlechterung erfuellt), sondern "es klappt
# GENAU das ein".
COMMON_NOTEBOOK = 1366
# GEMESSEN am Nachmittag des 17.08.2026, in der Reihenfolge, in der die
# Regel sie abgibt. Vier waren es vorher; die ganze Rechnung dazu steht
# oben bei COMPLETE_FROM. custom-hardware ist NICHT mehr dabei - es steht
# jetzt links und bleibt deshalb stehen.
# NACHGEZOGEN am 19.08.2026, und die Liste ist KUERZER geworden.
#
#     Sechs Module klappten hier ein, jetzt sind es vier. Die Zahl
#     hat sich an diesem Tag ZWEIMAL bewegt: erst auf drei, als der
#     doppelte Rand fiel, dann zurueck auf vier, als STYLE_CHIP_GAP
#     ganz durch die Abstandssprosse ersetzt wurde und die Polsterung
#     ihren eigenen Wert bekam. Beide Male gemessen, nicht geschaetzt. Der Grund ist
#     keine Verschlechterung, sondern die Behebung einer Doppelzaehlung:
#     jedes Modul trug einen linken Rand aus .bar-module UND einen
#     rechten aus seiner eigenen Regel, beide 15 Punkte. Zwischen zwei
#     Symbolen lagen damit 46 Punkte statt heute 28.
#
#     GEMELDET vom Nutzer als "sie sind viel zu weit voneinander
#     entfernt und auch nicht zentriert in ihrer box" - das Ungleiche
#     kam daher, dass nicht jedes Modul die zweite Regel trug.
#
#     Die Zusicherung bleibt, was sie war: nicht "es klappt etwas ein",
#     sondern "es klappt GENAU das ein". Dass die Liste schrumpft, ist
#     der messbare Gewinn - auf demselben Schirm passt jetzt mehr.
#
# UND AM SPAETEN 19.08.2026 IST SIE WIEDER LAENGER: FUENF STATT VIER.
#
#     `pulseaudio#microphone` ist dazugekommen, und das ist der Preis
#     der Bestellung desselben Tages - Ton und Mikrofon tragen ihre
#     Prozentzahl jetzt auf der Leiste (siehe COMPLETE_FROM oben, mit
#     der Messung). Die beiden Module wachsen zusammen um 66 px, und auf
#     1366 ist genau dafuer kein Platz.
#
#     GEMESSEN am 19.08.2026, in der Reihenfolge, in der die Regel sie
#     abgibt: auf 1366 px will die Leiste 1298 px und gibt fuenf Module
#     ab. Vorher waren es vier bei 1361 px.
#
#     DAS IST EIN BEFUND UND KEINE ENTSCHEIDUNG DIESER ZEILE. Auf dem
#     Schirm des Nutzers (1920x1200, Faktor 1.00) steht weiterhin alles;
#     auf einem 1366er Notebook liegt seit heute ein Modul mehr hinter
#     dem Knopf, und der Nutzer erfaehrt das im Bericht. Wer dort alles
#     sehen will, nimmt ein Modul aus der Vorgabe (user-settings.json,
#     Abschnitt "bar") - fort ist keines, sie liegen hinter dem Knopf.
#
# UND NOCH AM SPAETEN 19.08.2026 IST SIE WIEDER VIER: `pulseaudio#micro-
# phone` IST ZURUECK AUF DER LEISTE.
#
#     Kein Rueckbau der Prozentzahl - die bleibt, sie war bestellt. Was
#     die 66 px wieder eingebracht hat, ist die rechte Haelfte selbst:
#     die reinen Symbolmodule sind eine Polsterbreite zu breit gewesen
#     (STYLE_BAR_SYMBOL_WIDTH stand auf dem Kasten statt auf dem
#     Zeichen), die drei Knoepfe am Ende trugen ausserdem eine eigene,
#     doppelt so grosse Polsterung, und die Fugen sind auf Bestellung
#     eine Sprosse enger. Die ganze Rechnung steht bei COMPLETE_FROM.
#
#     GEMESSEN am 19.08.2026, in der Reihenfolge, in der die Regel sie
#     abgibt: auf 1366 px will die Leiste 1346 px und gibt VIER Module
#     ab. Vorher waren es fuenf bei 1298 px.
#
#     Auf 1280 sind es aus demselben Grund fuenf statt sechs.
#
# AM 20.08.2026 NACHGEMESSEN UND UNVERAENDERT GEBLIEBEN - DIESELBEN VIER,
# in derselben Reihenfolge (Aufgabe 41). Die Leiste will auf 1366 px an
# diesem Tag 1341 statt 1346 Punkte (die ganze Zeile steht bei
# COMPLETE_FROM), und fuenf Punkte reichen weder fuer ein fuenftes Modul
# noch dafuer, dass ein viertes zurueckkommt: das schmalste eingeklappte
# ist #custom-disk mit 36 Punkten plus Fuge. Dass die Liste trotz einer
# Aenderung an JEDEM Modul gleich bleibt, ist die Aussage dieses
# Nachmessens.
#
# UND AM 20.08.2026 EIN ZWEITES MAL NACHGEMESSEN, NACH DEM UMBAU DER
# RECHTEN HAELFTE (Aufgabe 42) - WIEDER DIESELBEN VIER, in derselben
# Reihenfolge, bei denselben 1341 Punkten.
#
#     `tray` ist an die zweite Stelle gewandert und damit an den
#     zweiten Platz der EINKLAPPREIHENFOLGE. In dieser Liste taucht es
#     trotzdem nicht auf, und das ist kein Versehen: die Regel
#     ueberspringt unsichtbare Module (`if (!entry.widget.visible)` in
#     foldingOf(), ags-bar.template), und ohne Sitzungsbus ist die
#     Ablage leer und damit unsichtbar. Sie wird hier also weder
#     eingeklappt noch gezaehlt.
#
#     AUF EINER ECHTEN MASCHINE MIT ABLAGESYMBOLEN steht sie in dieser
#     Liste an erster Stelle, noch vor custom-disk - und genau das ist
#     der Sinn des Umbaus: was der schmale Schirm zuerst abgibt, ist die
#     Ablage und nicht der Akku. Der Akku steht in dieser Liste
#     unveraendert NICHT.
FOLDED_ON_COMMON_NOTEBOOK = ("custom-disk", "network", "bluetooth",
                             "pulseaudio")

# Die Groessenfaktoren, ueber die die Dicke geprueft wird.
#
#   1.00  DER BINDENDE FALL. Das hoechste Modul enthaelt zwei Betraege,
#         die dem Faktor NICHT folgen - die 3 px Aussenrand oben und
#         unten aus STYLE_MARGIN_VERTICAL und die Rahmenstaerke -, und
#         die wiegen bei kleiner Schrift anteilig am schwersten.
#         GEMESSEN am 12.08.2026: gefordert 54, vorhanden 54. Null Luft,
#         und das mit Absicht - waechst ein Modul um einen Pixel, faellt
#         diese Zeile, und dann ist STYLE_BAR_THICKNESS neu abzuleiten.
#   1.30  und
#   1.50  die Zwischenschritte, an denen sich zeigt, dass die Luft
#         monoton waechst und nicht irgendwo einbricht.
#   2.50  das obere Ende dessen, was user_settings zulaesst.
#
# Der ausgelieferte Faktor fehlt in dieser Liste und wird trotzdem
# geprueft: dafuer gibt es die Vorrichtung `fit`, die ihn ohnehin baut.
THICKNESS_SCALES = (1.0, 1.3, 1.5, 2.5)


def _fit_environment(root: Path) -> tuple[Path, Path]:
    """Konfigurationsverzeichnis und Attrappen fuer einen Passt-es-Lauf."""
    config = root / "config"
    scripts = config / "ags" / "scripts"
    scripts.mkdir(parents=True)
    for name, text in FIT_MODULES.items():
        script = scripts / name
        script.write_text("#!/bin/bash\nprintf '%s' '{\"text\": \""
                          + text + "\"}'\n", encoding="utf-8")
        script.chmod(0o755)
    payload = ", ".join(f'"{key}": {{"text": "{value}"}}'
                        for key, value in FIT_STATUS.items())
    status = scripts / "status.sh"
    status.write_text("#!/bin/bash\nprintf '%s' '{" + payload + "}'\n",
                      encoding="utf-8")
    status.chmod(0o755)
    # Zehn Arbeitsbereiche, wie sie das Bild des Abnahmelaufs zeigt. Sie
    # sind mit 439 px bei Vorgabegroesse der breiteste Posten der Leiste.
    (config / "ags" / "workspaces.json").write_text(
        '{"persistent-workspaces": {"PROBE-1": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}}')

    runtime = root / "run"
    runtime.mkdir()
    runtime.chmod(0o700)
    return config, runtime


def _parse_fit(spur: str, widths, report: str) -> dict:
    """Zwei Runden in einer Spur.

    "breite <B>" ist die Leiste auf einem <B> px breiten Schirm,
    "wieder <B>" dieselbe Leiste, nachdem ihr gesagt wurde, der Schirm
    sei 7680 px breit.
    """
    measured = {"breite": {}, "wieder": {}, "report": report}
    current = None
    for line in spur.splitlines():
        head, _, tail = line.partition(" ")
        if head in ("breite", "wieder"):
            current = measured[head].setdefault(int(tail), {})
        elif current is not None and line.startswith("  "):
            key, _, value = line.strip().partition(" ")
            current[key] = value
    for phase in ("breite", "wieder"):
        assert sorted(measured[phase]) == sorted(widths), (
            f"das Kind hat in der Runde {phase} nicht alle Breiten "
            "gemessen:\n" + report)
    return measured


def _fit_run(root: Path, widths, scale: float | None = None) -> dict:
    """Die Leiste auf mehreren Schirmbreiten bauen und vermessen.

    `scale` ist der Groessenfaktor, unter dem die Vorlagen erzeugt
    werden. None heisst: der ausgelieferte.
    """
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    bundle, ags = _bundle(FIT_CHILD, root, scale=scale)
    config, runtime = _fit_environment(root)

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    try:
        result = subprocess.run(
            [str(bundle)],
            env={
                "PATH": _stub_hyprctl(root),
                "HOME": str(root),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(config),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={root}/kein-bus",
                "ZEPOS_TRACE": str(trace),
                "ZEPOS_CSS": str(ags / "bar.css"),
                "ZEPOS_WIDTHS": ",".join(str(width) for width in widths),
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(server)

    spur = trace.read_text() if trace.exists() else ""
    report = (f"faktor: {scale}\nrueckgabewert: {result.returncode}\n"
              f"stderr:\n{result.stderr}\nspur:\n{spur}")
    assert result.returncode == 0, report
    return _parse_fit(spur, widths, report)


@pytest.fixture(scope="module")
def fit(tmp_path_factory):
    """Ein Lauf, der die Leiste auf vier Schirmbreiten baut und vermisst."""
    return _fit_run(tmp_path_factory.mktemp("bar-fit"), WIDTHS)


@pytest.fixture(scope="module")
def thickness_fits(tmp_path_factory) -> dict:
    """Dieselbe Leiste unter vier anderen Groessenfaktoren.

    EIN Schirm je Faktor, und zwar der breiteste: gemessen wird hier
    nicht, was eingeklappt wird, sondern wie HOCH die Leiste sein will.
    Ein Modul im Aufklappfenster wuerde diese Frage nur verstellen.
    """
    return {scale: _fit_run(tmp_path_factory.mktemp(f"bar-dick-{scale}"),
                            (max(WIDTHS),), scale=scale)
            for scale in THICKNESS_SCALES}


def _placed(measured, width, phase="breite"):
    """Was auf dieser Breite sichtbar dasteht: Name -> (links, Breite)."""
    entries = {}
    for token in measured[phase][width]["gestellt"].split():
        name, _, geometry = token.partition("@")
        left, _, size = geometry.partition("+")
        entries[name] = (int(left), int(size))
    return entries


def _breadth(measured, width, phase="breite"):
    """Wie hoch jedes Modul sein WILL: Name -> Mindesthoehe."""
    entries = {}
    for token in measured[phase][width]["breite"].split():
        name, _, value = token.partition("=")
        entries[name] = int(value)
    return entries


def _sides(measured, width, key, phase="breite"):
    """Eine Zeile aus Paaren: Name -> (links, rechts).

    Drei Zeilen des Kindes haben diese Form, und sie beantworten drei
    verschiedene Fragen ueber DASSELBE Modul:

        zentriert   der ganze Satz im Modul - sagt, ob die POLSTERUNG
                    symmetrisch liegt, und sonst nichts.
        zeichen     das Zeichen in seiner Zelle, nach VORSCHUB.
        tinte       das Zeichen in seiner Zelle, nach TINTE - das, was
                    der Nutzer sieht.

    Dass es drei sind und nicht eine, ist die Lehre aus dem 19.08.2026:
    damals stand nur `zentriert` zur Verfuegung, meldete fuer jedes
    Modul mit Text 8:8 und hat die Meldung des Nutzers damit als behoben
    ausgewiesen, obwohl das Zeichen am Rand sass.
    """
    entries = {}
    for token in measured[phase][width][key].split():
        name, _, pair = token.partition("=")
        left, _, right = pair.partition(":")
        entries[name] = (int(left), int(right))
    return entries


def _groups(measured, width, phase="breite"):
    """Wo die Platte und die drei Gruppen liegen: Name -> (links, Breite)."""
    entries = {}
    for token in measured[phase][width]["gruppen"].split():
        name, _, geometry = token.partition("@")
        left, _, size = geometry.partition("+")
        entries[name] = (int(left), int(size))
    return entries


# --------------------------------------------------------------------
# laengs: passt die Summe in die Breite
# --------------------------------------------------------------------

def test_no_module_ends_outside_the_screen_it_is_drawn_on(fit):
    """Die Zusicherung, die am 11.08.2026 gefehlt hat.

    Gemessen mit compute_bounds() gegen die Flaeche, der die Leiste
    zugeteilt wurde - also in denselben Koordinaten, in denen der
    Compositor sie abschneidet.

    ALLEIN GENUEGT DAS NICHT, UND DAS IST GEMESSEN
        Die Mutation "die Einklappregel tut nichts mehr" kam hier
        DURCH. Ein Gtk.CenterBox, dem weniger zugeteilt wird als sein
        Minimum, schiebt sein Ende naemlich nicht ueber den Rand, es
        legt Anfang und Ende UEBEREINANDER.

        Deshalb gehoeren zu dieser Frage drei Zusicherungen und nicht
        eine: diese hier fuer die Kanten, die naechste fuer die
        Ueberlappung, und die dritte fuer GTKs eigene Untergrenze.
    """
    for width in WIDTHS:
        for name, (left, size) in _placed(fit, width).items():
            assert left >= 0, (
                f"{name} beginnt bei {left} und damit links vom Schirm "
                f"({width} px):\n" + fit["report"])
            assert left + size <= width, (
                f"{name} endet bei {left + size} auf einem {width} px "
                "breiten Schirm - es wird abgeschnitten:\n" + fit["report"])


def test_no_two_modules_are_drawn_on_top_of_each_other(fit):
    """Die Form, die der Ueberlauf unter GTK4 wirklich annimmt.

    Die Module stehen in einer Reihe, also darf keines dort anfangen,
    wo ein frueheres noch nicht aufgehoert hat. Genau das passiert,
    sobald der Leiste weniger zugeteilt wird als ihre Mindestbreite -
    und genau das faengt die Kantenpruefung oben nicht.

    GEMESSEN am 11.08.2026 bei 1280 px, mit abgeschalteter Regel: die
    Arbeitsbereiche reichten bis x=865, und das erste Modul des rechten
    Kastens begann bei x=622 - 243 px Ueberdeckung, und keine einzige
    Kante lag ausserhalb des Schirms.

    SIE HAT SICH BEIM DREHEN ZWEIMAL BEZAHLT GEMACHT. Der erste Anlauf
    von Aufgabe #88 drehte die drei Kaesten und vergass das CenterBox
    selbst; die drei standen damit als SPALTEN nebeneinander, der obere
    Kasten begann bei y=48 und der untere ebenfalls bei y=48. Nur diese
    Pruefung sah es - und beim Zurueckdrehen bewacht sie dieselbe Zeile
    in der Gegenrichtung.
    """
    for width in WIDTHS:
        entries = sorted(_placed(fit, width).items(),
                         key=lambda item: item[1][0])
        for (before, (left, size)), (after, (next_left, _)) in zip(
                entries, entries[1:]):
            assert left + size <= next_left, (
                f"auf {width} px endet {before} bei {left + size} und "
                f"{after} beginnt schon bei {next_left} - die beiden "
                "liegen uebereinander:\n" + fit["report"])


def test_the_bar_never_asks_for_more_room_than_the_screen_is_wide(fit):
    """Die scharfe Fassung derselben Frage.

    Die Kantenpruefung oben kann eine Leiste durchlassen, die um weniger
    ueberlaeuft als der Aussenabstand ihres letzten Moduls. GTKs eigene
    Untergrenze kann das nicht: sie ist die Breite, unter der die Module
    beginnen, EINANDER zu ueberlappen.

    Sie hat beim Drehen zwei echte Fehler gefangen, beide zu klein fuer
    eine Kante: die Platte haelt links und rechts ihren Abstand zum Rand
    (2*30 px), und der fehlte im Platzbudget.
    """
    for width in WIDTHS:
        minimum = int(fit["breite"][width]["minimum"])
        assert minimum <= width, (
            f"die Leiste will mindestens {minimum} px Breite und hat "
            f"{width}:\n" + fit["report"])


# --------------------------------------------------------------------
# die Mitte: sitzt das Zeichen dort, wo man es sieht
# --------------------------------------------------------------------
#
# DREI MELDUNGEN UEBER DIESELBE SACHE, UND KEINE DAVON HATTE EINEN
# WAECHTER
#
#     19.08.2026 vormittags  "sie sind viel zu weit voneinander
#                            entfernt und auch nicht zentriert in ihrer
#                            box"
#     19.08.2026 abends      "die icon im header sind immernoch nicht
#                            zentreirt in ihrem kaestchen"
#     20.08.2026             "wlan symbol immernoch nicht zentriert",
#                            davor "bluetooth icon oben im header ist
#                            nicht zentriert auch das wlan icon nicht"
#
#     Zweimal ist repariert und zweimal gemessen worden, und beide Male
#     ist die Messung in einem Bericht stehengeblieben statt in einer
#     Zusicherung. Eine Messung, die niemand wiederholt, faellt beim
#     naechsten Umbau lautlos - genau das ist zwischen dem 19. und dem
#     20.08.2026 passiert.
#
# DIE ZWEI ZUSICHERUNGEN HIER SIND DIE BEIDEN URSACHEN, JEDE FUER SICH
#
#     Die erste haelt fest, dass das Zeichen in seiner Zelle mittig
#     sitzt - nach TINTE gemessen. Sie faellt, wenn jemand wieder den
#     Vorschub zentriert (der Fall vom 20.08.2026, ICON_WIFI: Vorschub
#     12 px, Tinte 20 px).
#
#     Die zweite haelt fest, dass das AUCH fuer ein Modul mit Wert gilt.
#     Sie faellt, wenn Zeichen und Wert wieder in EINER Beschriftung
#     landen (der Fall vom 19.08.2026, #bluetooth: Zeichen 8:33 im Modul,
#     waehrend `zentriert` 8:8 meldete).

# Ein halber Bildpunkt, und mehr ist nicht zu holen: die Zelle ist
# STYLE_BAR_SYMBOL_WIDTH breit (gemessene 20 px), ein Zeichen darin 10
# bis 20 px - bleibt eine ungerade Zahl uebrig, teilt GTK sie nicht in
# Halbe. Das Kind rundet ausserdem beide Kanten fuer sich, also koennen
# aus zweimal 1,5 einmal 2 und einmal 1 werden.
CENTRED_TOLERANCE = 1


def _with_value(measured, width, phase="breite"):
    """Die Module, die ein Zeichen UND einen Wert tragen.

    Gemessen und nicht aufgezaehlt: welches Modul gerade etwas neben
    seinem Zeichen sagt, entscheidet sein Skript. Eine Liste von Namen
    hier waere eine zweite Wahrheit darueber und ginge beim naechsten
    Wechsel auseinander - #pulseaudio hat seinen Wert am 12.08.2026
    verloren und am 19.08.2026 zurueckbekommen.
    """
    zellen = _sides(measured, width, "tinte", phase)
    werte = {}
    for token in measured[phase][width]["wert"].split():
        name, _, breite = token.partition("=")
        werte[name] = int(breite)
    return [name for name in werte if name in zellen]


def test_a_module_puts_its_symbol_in_the_middle_of_its_cell(fit):
    """Die TINTE liegt mittig in der Zelle - nicht der Vorschub.

    GEMESSEN am 20.08.2026 mit Pango, "Fira Code, JetBrainsMono Nerd
    Font" bei 20 px: jedes Zeichen dieser Leiste hat einen Vorschub von
    12 px, seine Tinte ist 10 bis 20 px breit und beginnt am Stift.
    Ein Zeichen, dessen VORSCHUB mittig sitzt, sitzt damit bis zu vier
    Punkte zu weit rechts - beim WLAN-Zeichen genau vier, und das ist
    die Meldung "wlan symbol immernoch nicht zentriert".

    Die Zeile `zentriert` sieht das nicht: sie misst logische Ausmasse.
    Deshalb liest diese Zusicherung `tinte`.
    """
    for width in WIDTHS:
        for phase in ("breite", "wieder"):
            for name, (left, right) in _sides(
                    fit, width, "tinte", phase).items():
                assert abs(left - right) <= CENTRED_TOLERANCE, (
                    f"das Zeichen von {name} sitzt auf {width} px "
                    f"({phase}) nicht mittig in seiner Zelle: links "
                    f"{left}, rechts {right} - gemessen an der TINTE, "
                    "also an dem, was zu sehen ist:\n" + fit["report"])


def test_a_module_with_a_value_centres_its_symbol_too(fit):
    """Ein Zeichen NEBEN einem Wert sitzt genauso mittig.

    Das ist die Zusicherung, die am 19.08.2026 gefehlt hat. Damals
    wurde die Mindestbreite an die Beschriftung gehaengt, und die trug
    Zeichen UND Wert: zentriert wurde die Zeichenkette, das Zeichen
    stand an ihrem Anfang. GEMESSEN am 20.08.2026, VOR der Behebung,
    Lage des Zeichens im Modul: #bluetooth 8:33, #pulseaudio 8:70,
    #battery 8:58 - waehrend `zentriert` fuer alle drei 8:8 meldete und
    sie damit als in Ordnung auswies.

    Dass hier ueberhaupt Module geprueft werden, ist Teil der
    Zusicherung: faende der Aufbau keines mit Wert, waere die Zeile
    darunter leer und gruen.
    """
    for width in WIDTHS:
        if width < COMPLETE_FROM:
            continue
        mit_wert = _with_value(fit, width)
        assert len(mit_wert) >= 4, (
            "auf dieser Leiste tragen weniger als vier Module einen Wert "
            "neben ihrem Zeichen - dann misst diese Zusicherung nichts:\n"
            + fit["report"])
        tinte = _sides(fit, width, "tinte")
        for name in mit_wert:
            left, right = tinte[name]
            assert abs(left - right) <= CENTRED_TOLERANCE, (
                f"{name} traegt einen Wert neben seinem Zeichen, und das "
                f"Zeichen sitzt auf {width} px nicht mittig in seiner "
                f"Zelle: links {left}, rechts {right}:\n" + fit["report"])


def test_the_bar_keeps_the_same_edge_on_both_sides(fit):
    """Links wie rechts derselbe Abstand zur Kante der Platte.

    BESTELLT am 20.08.2026: "das control zentrum icon soll genau
    platziert werden rechts wie links der kalender, aktuell geht er
    rechts in die sidebar".

    GEMESSEN an diesem Tag, VOR der Behebung, Vorgabegroesse, 1920 px:
    die Platte lag von 24 bis 1896, das erste Modul der linken Haelfte
    begann bei 36 (also 12 Punkte Rand), das letzte der rechten endete
    bei 1896 (also null). Die Ursache ist das Abstandsmodell: jedes
    Modul traegt seine Fuge LINKS, also bekommt das erste links seinen
    Plattenrand geschenkt und das letzte rechts hat keinen.

    Gemessen wird gegen die GRUPPE und nicht gegen das letzte Modul:
    was gerade das letzte ist, entscheidet der Einklapper, und auf
    1024 px bleiben nur unsichtbare Module im Kasten stehen.
    """
    for width in WIDTHS:
        for phase in ("breite", "wieder"):
            gruppen = _groups(fit, width, phase)
            platte_links, platte_breit = gruppen["bar"]
            platte_rechts = platte_links + platte_breit
            erstes = min(
                (links for links, _ in _placed(fit, width, phase).values()),
                default=platte_links)
            rechts_links, rechts_breit = gruppen["modules-right"]
            links_rand = erstes - platte_links
            rechts_rand = platte_rechts - (rechts_links + rechts_breit)
            assert links_rand == rechts_rand, (
                f"die Leiste haelt auf {width} px ({phase}) links "
                f"{links_rand} und rechts {rechts_rand} Punkte Abstand "
                "zur Kante der Platte:\n" + fit["report"])


# --------------------------------------------------------------------
# Die zwei Ecken: ein Zeichen, das in KEINEM dieser Laeufe vorkommt
# --------------------------------------------------------------------
#
# GEMELDET am 20.08.2026, woertlich: "die 6 punkte sind nicht zentriert"
# - der Starterknopf unten rechts (Aufgabe 47).
#
# DIE ZUSICHERUNGEN DARUEBER KONNTEN DAS NICHT SEHEN, UND ZWAR AUS EINEM
# EINZIGEN GRUND: sie bauen BarContent(). Was in einem EIGENEN Fenster
# steht, kommt in keiner ihrer Zeilen vor.
#
# DAS IST DERSELBE GRUND ZUM VIERTEN MAL. Dreimal ist an genau diesen
# zwei Knoepfen dasselbe passiert, und jedes Mal hat es der Nutzer
# gemeldet und keine Zusicherung:
#
#     19.08.2026  keine Schriftgroesse  Zeichen 10 x 11 statt 20 x 22
#     20.08.2026  keine Schriftfamilie  Adwaita Sans statt Nerd Font,
#                                       Platte 53 x 54 statt 53 x 57
#     20.08.2026  keine Zelle           Tinte 3,5 Punkte rechts der Mitte
#
# Die gemeinsame Ursache ist EINE: ein eigenes Fenster erbt nichts von
# window.bar-window. Deshalb ist der Waechter hier unten allgemein
# gefasst - er fragt nicht "sitzen DIESE zwei Zeichen mittig", sondern
# "tut es JEDES freistehende Knopffenster, das es gibt", und er sucht
# sich die Liste selbst aus den Vorlagen.

# Was ein freistehendes Knopffenster ist, in Merkmalen und nicht in
# Namen: eine Vorlage, die ihre Astal.Window SELBST baut (die fuenf aus
# tests/src/test_modal_rule.py), darin GENAU EINEN Gtk.Button aufstellt
# und GENAU EIN Zeichen fuehrt.
#
# Das trennt sie von den anderen dreien: die Leiste fuehrt zwanzig
# Zeichen, das Dock und die Benachrichtigungen bauen je zwei Knoepfe.
# Und es ist keine Aufzaehlung - ein dritter Knopf in einer dritten Ecke
# faellt am Tag, an dem er geschrieben wird, in dieselbe Menge.
CORNER_WINDOW = "new Astal.Window("
CORNER_BUTTON = "new Gtk.Button("
CORNER_ICON = re.compile(r"\{\{ICON_[A-Z0-9_]+\}\}")

# Die Fabrik faellt heraus, und das ist keine Ausnahme fuer diesen
# Waechter, sondern DIE Grenze, die dieses Projekt ohnehin zieht:
# tests/src/test_modal_rule.py teilt die Vorlagen genau hier in "baut
# sich sein Fenster selbst" und "geht durch die Fabrik". Ein Fenster,
# das die Fabrik fuer einen AUFRUFER baut, ist keine feste Ecke am
# Bildschirmrand - es hat einen Kopf, eine Bildlaufleiste und einen
# Schliessknopf, und dessen Zeichen ist das eine, das sie hier sonst
# faelschlich hereinzoege.
CORNER_FACTORY = "ags-overlay-utils.template"

# Das Bauteil, das die Leiste benutzt - und damit das, was die Knoepfe
# benutzen. Keine zweite Fassung von centreInk(): die Rechnung ist an
# EINEM Tag dreimal falsch gewesen, eine Abschrift davon waere die
# vierte.
CORNER_CELL = "SymbolCell"


def _template_code(path: Path) -> str:
    """Die Vorlage ohne ihre Zeilenkommentare.

    Dieselbe Vorsicht wie in tests/src/test_modal_rule.py: jede Datei in
    diesem Baum ERKLAERT, was sie nicht mehr tut. Eine Suche nach
    `new Gtk.Label` wuerde von der Erklaerung wahr, in der steht, dass
    dort kein `new Gtk.Label` mehr steht.
    """
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("//"))


def _corner_templates() -> dict[str, str]:
    """Jede Vorlage, die ein freistehendes Knopffenster baut."""
    gefunden = {}
    for template in sorted((SRC / "templates").glob("ags-*.template")):
        if template.name == CORNER_FACTORY:
            continue
        code = _template_code(template)
        if CORNER_WINDOW not in code:
            continue
        if code.count(CORNER_BUTTON) != 1:
            continue
        if len(set(CORNER_ICON.findall(code))) != 1:
            continue
        gefunden[template.name] = code
    return gefunden


def _corner_run(root: Path) -> dict:
    """Die zwei Platten bauen und vermessen - je in einem eigenen Fenster."""
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    bundle, ags = _bundle(CORNER_CHILD, root)
    runtime = root / "run"
    runtime.mkdir()
    runtime.chmod(0o700)

    trace = root / "trace"
    display = next(_DISPLAYS)
    server, _socket = start_broadwayd(display_server, runtime, display)
    try:
        result = subprocess.run(
            [str(bundle)],
            env={
                "PATH": _stub_hyprctl(root),
                "HOME": str(root),
                "GDK_BACKEND": "broadway",
                "BROADWAY_DISPLAY": f":{display}",
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(root / "config"),
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path={root}/kein-bus",
                "ZEPOS_TRACE": str(trace),
                "ZEPOS_CSS": str(ags / "bar.css"),
            },
            capture_output=True, text=True, timeout=CHILD_TIMEOUT,
        )
    finally:
        stop_broadwayd(server)

    spur = trace.read_text() if trace.exists() else ""
    report = (f"rueckgabewert: {result.returncode}\nstderr:\n{result.stderr}"
              f"\nspur:\n{spur}")
    assert result.returncode == 0, report

    gemessen: dict = {"report": report}
    aktuell = None
    for line in spur.splitlines():
        head, _, tail = line.partition(" ")
        if head == "knopf":
            aktuell = gemessen.setdefault(tail, {})
        elif aktuell is not None and line.startswith("  "):
            key, _, value = line.strip().partition(" ")
            aktuell[key] = value
    return gemessen


@pytest.fixture(scope="module")
def corner(tmp_path_factory) -> dict:
    """Ein Lauf, der die zwei Knoepfe am Dock baut und vermisst."""
    return _corner_run(tmp_path_factory.mktemp("ecken"))


def _corner_measured(corner: dict) -> list[str]:
    """Die Platten, die der Lauf wirklich gemessen hat."""
    return sorted(name for name in corner if name != "report")


def _pair(corner: dict, name: str, key: str) -> tuple[int, int]:
    """Eine Zeile der Form `links:rechts`."""
    left, _, right = corner[name][key].partition(":")
    return int(left), int(right)


def test_a_freestanding_button_centres_the_ink_of_its_symbol(corner):
    """Die TINTE sitzt mittig in der Platte - bei JEDEM der Knoepfe.

    GEMELDET am 20.08.2026: "die 6 punkte sind nicht zentriert".

    GEMESSEN am selben Tag mit diesem Lauf, Vorgabegroesse, Lage der
    Tinte in der Platte (53 x 57), VORHER -> NACHHER:

        starter-button   17:12  ->  14:15    Tinte 24 x 18, Versatz +3
        power-button     17:16  ->  16:17    Tinte 20 x 22, Versatz +1

    Eine Gtk.Label mittet den VORSCHUB (hier 18 Punkte), gesehen wird
    die TINTE. Beim Rastersymbol ist sie ein Drittel breiter als er,
    also sass sie drei Punkte rechts der Mitte - fuenf Punkte
    Unterschied zwischen den Raendern. Das ist die Meldung.

    DER ABSCHALTKNOPF FAELLT DABEI UNTER DIE TOLERANZ, VORHER WIE
    NACHHER, und das ist eine Eigenschaft SEINES Zeichens und keine
    Schwaeche dieser Zeile: bei zwei Punkten Unterschied zwischen Tinte
    und Vorschub bleibt in einem 35 Punkte breiten Knopf ohnehin ein
    ungerader Punkt uebrig. Dass auch er die Zelle traegt, haelt der
    Waechter darunter fest - an der Quelle, wo die Frage nicht von der
    Breite eines einzelnen Glyphs abhaengt.

    Gemessen wird gegen die PLATTE und nicht gegen die Zelle: die Platte
    ist das, was der Nutzer sieht.
    """
    gemessen = _corner_measured(corner)
    assert len(gemessen) >= 2, (
        "dieser Lauf hat weniger als zwei Platten gemessen - dann sagt "
        "die Zeile darunter nichts:\n" + corner["report"])
    for name in gemessen:
        left, right = _pair(corner, name, "tinte")
        assert abs(left - right) <= CENTRED_TOLERANCE, (
            f"das Zeichen von {name} sitzt nicht mittig in seiner "
            f"Platte: links {left}, rechts {right} - gemessen an der "
            "TINTE, also an dem, was zu sehen ist:\n" + corner["report"])


def test_every_freestanding_button_window_uses_the_cell_the_bar_uses(corner):
    """Es gibt EIN Bauteil fuer die Mitte eines Zeichens, nicht drei.

    Die Behebung vom 20.08.2026 (dea3f0b) hat die Zelle gebaut und jedem
    Modul der LEISTE gegeben. Die zwei freistehenden Knoepfe haben davon
    nichts abbekommen - nicht aus einer Entscheidung, sondern weil das
    Bauteil in ags-bar.template eingeschlossen war und niemand es
    importieren konnte.

    Diese Zusicherung zaehlt keine Namen auf: sie sucht in den Vorlagen
    nach dem MERKMAL - eine eigene Astal.Window, ein Knopf, ein Zeichen.
    Ein dritter Knopf in einer dritten Ecke faellt an dem Tag darunter,
    an dem er geschrieben wird, und nicht an dem, an dem es jemand
    meldet.
    """
    knoepfe = _corner_templates()
    assert len(knoepfe) >= 2, (
        "es sind weniger als zwei freistehende Knopffenster gefunden "
        f"worden ({sorted(knoepfe)}) - erwartet sind mindestens der "
        "Abschaltknopf und der Starterknopf am Dock. Findet diese Suche "
        "nichts mehr, ist sie gruen und wertlos")

    for name, code in knoepfe.items():
        assert f'import {{ {CORNER_CELL} }} from "./Bar"' in code, (
            f"{name} baut ein freistehendes Knopffenster, importiert aber "
            f"{CORNER_CELL} nicht aus ./Bar - dann mittet es sein Zeichen "
            "entweder gar nicht oder in einer zweiten Fassung derselben "
            "Rechnung")
        assert f"new {CORNER_CELL}(" in code, (
            f"{name} importiert {CORNER_CELL}, benutzt es aber nicht")
        assert "set_child(new Gtk.Label(" not in code, (
            f"{name} setzt eine blanke Gtk.Label in seinen Knopf. Genau "
            "das ist die Meldung vom 20.08.2026: eine Gtk.Label mittet "
            "den Vorschub, gesehen wird die Tinte")

    # Und das Messgeraet muss jeden davon auch WIRKLICH bauen. Ohne diese
    # Zeile koennte ein dritter Knopf dazukommen, die Quellenpruefung
    # oben bestehen und trotzdem nie gemessen werden.
    platten = {name.removeprefix("ags-").removesuffix(".template")
               for name in knoepfe}
    assert platten == set(_corner_measured(corner)), (
        f"die Vorlagen bauen {sorted(platten)}, gemessen wurden "
        f"{_corner_measured(corner)} - tests/src/corner_button_child.tsx "
        "muss jeden freistehenden Knopf bauen, sonst ist er ungehalten:\n"
        + corner["report"])


def test_every_freestanding_button_names_the_font_it_cannot_inherit(corner):
    """Familie, Schnitt und Groesse - alle drei, gemessen am Widget.

    DIE DREI SIND EINE LISTE UND KEIN ZUFALL. window.bar-window nennt
    sie, und ein EIGENES Fenster erbt keine davon; genau diese Luecke
    hat an diesen zwei Knoepfen dreimal zugeschlagen:

        19.08.2026  Groesse fehlte    Tinte 10 x 11 statt 20 x 22
        20.08.2026  Familie fehlte    Adwaita Sans zeichnete bei U+EE56
                                      einen ANDEREN Glyph (15 x 17)
        20.08.2026  Schnitt fehlte    (heute nachgetragen)

    GEMESSEN WIRD, WAS DAS WIDGET BEKOMMEN HAT, und nicht, was in
    bar.css steht: `get_pango_context().get_font_description()` gibt die
    Schrift, die GTK aus dem Stil gemacht hat. Eine Regel, die den
    Wahlausdruck verfehlt, steht in der Datei und wirkt nicht - und
    genau das war der Fall vom 19.08.2026.

    Verglichen wird gegen die Tabellen dieses Hauses (STYLE_FONT_FAMILY,
    STYLE_FONT_WEIGHT, STYLE_ICON_LEAD) und nicht gegen eine Zahl hier.
    """
    styles = _renderer().styles
    familie = [teil.strip().strip('"')
               for teil in styles["STYLE_FONT_FAMILY"].split(",")]
    schnitte = {"normal": 400, "bold": 700}
    schnitt = schnitte.get(styles["STYLE_FONT_WEIGHT"].strip(),
                           styles["STYLE_FONT_WEIGHT"].strip())
    groesse = styles["STYLE_ICON_LEAD"].strip()

    for name in _corner_measured(corner):
        roh = corner[name]["schrift"]
        hat_familie, hat_schnitt, hat_groesse, absolut = roh.split("|")
        assert [teil.strip() for teil in hat_familie.split(",")] == familie, (
            f"{name} zeichnet sein Zeichen in {hat_familie!r} statt in "
            f"der ausgelieferten Schriftliste. Ein eigenes Fenster erbt "
            "die Familie nicht - sie muss in seinem eigenen "
            "Wahlausdruck stehen:\n" + corner["report"])
        assert int(hat_schnitt) == int(schnitt), (
            f"{name} zeichnet im Schnitt {hat_schnitt} statt "
            f"{schnitt} - derselbe Posten wie die Familie, nur der "
            "dritte:\n" + corner["report"])
        assert f"{hat_groesse}{absolut}".replace(".0", "") == groesse, (
            f"{name} zeichnet in {hat_groesse}{absolut} statt in "
            f"{groesse}. Ohne eigene Zeile faellt die Groesse auf die "
            "Vorgabe des GTK-Themas zurueck, und das war die Meldung "
            "'etwas zu klein' vom 19.08.2026:\n" + corner["report"])


def test_the_freestanding_buttons_are_all_the_same_plate(corner):
    """"Genauso" ist eine Anweisung: gleiche Platte, auf den Punkt.

    BESTELLT am 20.08.2026: "ich will wie shutdown icon unten links,
    will ich ein icon ganz unten rechts genauso".

    Diese Zeile hat einen gemessenen Anlass. Bevor
    window.starter-button-window seine Schriftfamilie bekam, war der
    Starterknopf 53 x 54 und der Abschaltknopf 53 x 57 - drei Punkte
    auseinander, weil das GTK-Thema fuer U+EE56 eine andere Zeilenhoehe
    fuehrt. Die Groesse der Platte ist damit der billigste Beweis, dass
    beide Fenster wirklich dieselbe Schrift bekommen haben.
    """
    platten = {name: corner[name]["platte"] for name in _corner_measured(corner)}
    assert len(set(platten.values())) == 1, (
        f"die freistehenden Knoepfe haben verschiedene Platten: "
        f"{platten} - sie sollen 'genauso' sein:\n" + corner["report"])


# --------------------------------------------------------------------
# quer: passt das hoechste Modul in die Dicke
# --------------------------------------------------------------------

def test_no_module_is_taller_than_the_bar_it_hangs_in(fit, thickness_fits):
    """Die zweite Achse, ueber fuenf Groessenfaktoren gemessen.

    Ein Modul, das hoeher ist als der Streifen, in dem es liegt, wird
    oben und unten abgeschnitten - und zwar ohne dass eine
    Breitenpruefung davon etwas merkt.

    WARUM UEBER FAKTOREN UND NICHT UEBER SCHIRME
        Die Hoehe eines Moduls haengt an keinem Text: eine Beschriftung
        bricht nicht um, ein Nerd-Font-Zeichen ist eine Zeile, und die
        Symbole der Ablage haben eine feste Pixelgroesse. Sie haengt
        allein an Sprossen aus src/sizes.py - und die bewegt der
        Groessenregler. Vier Schirme mit demselben Faktor messen
        deshalb viermal dasselbe.

    WARUM GEGEN DIE GANZE LEISTE UND NICHT GEGEN DAS EINZELNE MODUL
        `measure(VERTICAL)` auf das CenterBox zaehlt den Rand mit, den
        die Platte nach oben haelt, und ihre Kante unten. Genau die
        beiden fehlten am 11.08.2026 in der Rechnung der gedrehten
        Fassung, und die Leiste wollte 902 px auf einem 900 px hohen
        Schirm. Ein Modul allein zu messen liesse dieselbe Luecke
        wieder offen.

    ZWEI ZAHLEN, ZWEI BEZUGSGROESSEN - UND BIS ZUM 13.08.2026 WAREN ES
    ZWEI ZAHLEN UND EINE BEZUGSGROESSE
        `hoechste` ist die Messung des CenterBox SAMT seines
        Aussenrandes (margin-top: STYLE_GAPS_OUT). Sie gehoert zur
        FLAECHE, und die ist seit dem 12.08.2026 BAR_THICKNESS +
        EDGE_GAP hoch - siehe set_default_size in ags-bar.template.
        `innen` ist derselbe Inhalt OHNE diesen Rand und gehoert zur
        PLATTE, also zu den bemalten BAR_THICKNESS.

        Bis heute wurde `hoechste` gegen BAR_THICKNESS gehalten. Das war
        richtig, solange die Flaeche selbst BAR_THICKNESS hoch war; seit
        sie um einen Rand hoeher ist, verlangte diese Zeile den Rand
        ZWEIMAL. Aufgefallen ist es, als die Dicke am 13.08.2026 auf die
        bestellten 60 px fiel: die Zusicherung meldete bei Faktor 1.00
        "50 passt nicht in 47", waehrend der Bildschirmabzug desselben
        Standes eine Leiste ohne jeden Anschnitt zeigte
        (tests/render/test_geometry.py). Eine Zusicherung, die eine
        Verbesserung als Fehler meldet, misst nicht die Sache.
    """
    sys.path.insert(0, str(SRC))
    try:
        import sizes
        table = {scale: int(sizes.value_of("STYLE_BAR_THICKNESS",
                                           {"scale": scale}))
                 for scale in THICKNESS_SCALES}
        edge = {scale: int(sizes.value_of("STYLE_GAPS_OUT", {"scale": scale}))
                for scale in THICKNESS_SCALES}
        edge[None] = int(sizes.value_of("STYLE_GAPS_OUT", {}))
    finally:
        sys.path.remove(str(SRC))

    runs = {scale: (thickness_fits[scale], max(WIDTHS))
            for scale in THICKNESS_SCALES}
    runs[None] = (fit, max(WIDTHS))

    for scale, (measured, width) in runs.items():
        wanted = int(measured["breite"][width]["hoechste"])
        inner = int(measured["breite"][width]["innen"])
        thickness = int(measured["breite"][width]["dicke"])
        if scale is not None:
            assert thickness == table[scale], (
                f"bei sizes.scale {scale} traegt die erzeugte Leiste "
                f"{thickness} px, die Tabelle sagt {table[scale]}:\n"
                + measured["report"])
        assert inner <= thickness, (
            f"bei sizes.scale {scale} will der Inhalt der Platte {inner} px "
            f"und die Platte bemalt {thickness} px - ihr hoechstes Modul "
            "wird angeschnitten:\n" + measured["report"])
        assert wanted <= thickness + edge[scale], (
            f"bei sizes.scale {scale} will die Leiste {wanted} px Hoehe und "
            f"ihre Flaeche ist {thickness} + {edge[scale]} px hoch:\n"
            + measured["report"])

    # Und jedes EINZELNE Modul passt hinein, auch die eingeklappten:
    # ein Modul im Aufklappfenster ist dasselbe Modul, und es kommt
    # zurueck, sobald wieder Platz ist.
    #
    # Gegen die ganze Dicke und nicht gegen den Streifen darin, und das
    # ist absichtlich die schwaechere Frage: was von der Dicke abgeht,
    # steckt schon in `hoechste` oben, und zweimal denselben Abzug zu
    # rechnen hiesse, ihn doppelt zu verlangen.
    thickness = int(fit["breite"][max(WIDTHS)]["dicke"])
    for width in WIDTHS:
        for name, height in _breadth(fit, width).items():
            assert height <= thickness, (
                f"{name} will {height} px Hoehe und die Leiste ist "
                f"{thickness} px dick:\n" + fit["report"])


def test_the_bar_is_not_a_hairline(fit):
    """Die Gegenrichtung, und ohne sie sind alle Pruefungen oben mit
    einer Leiste zu erfuellen, auf der nichts steht.

    Eine Dicke, die kleiner ist als die Schrift, die darauf steht, ist
    genau der Zustand, in dem die Leiste vor dem 11.08.2026 war: 50 px
    aus einer Zeit mit 13 px Schrift, unter 24 px Text.
    """
    sys.path.insert(0, str(SRC))
    try:
        import sizes
        body = int(sizes.value_of("STYLE_FONT_BODY", {}).removesuffix("px"))
    finally:
        sys.path.remove(str(SRC))

    for width in WIDTHS:
        thickness = int(fit["breite"][width]["dicke"])
        assert thickness > body, (
            f"die Leiste ist {thickness} px dick und traegt {body} px "
            "Schrift:\n" + fit["report"])
        breadth = _breadth(fit, width)
        assert "bar-overflow" in breadth, fit["report"]
        assert breadth["bar-overflow"] <= thickness, (
            "der Ueberlaufknopf passt nicht in die Leiste, in der er "
            f"haengt: {breadth['bar-overflow']} px in {thickness} px:\n"
            + fit["report"])


# --------------------------------------------------------------------
# was weichen muss, und was zurueckkommt
# --------------------------------------------------------------------

def test_what_does_not_fit_is_folded_away_and_not_lost(fit):
    """Eingeklappt heisst: im Aufklappfenster, nicht fort.

    Der Unterschied ist der ganze Grund, aus dem hier ein Knopf steht
    statt eines set_visible(false). Beides raeumt die Leiste auf; nur
    eines laesst den Nutzer noch an die Auskunft.
    """
    # 1024 und nicht mehr 1280: die ausgelieferte Leiste passt seit dem
    # 12.08.2026 auf 1280 vollstaendig, und ein Einklapper, der nie
    # einklappt, ist eine Regel ohne Messung. Der Fall ist derselbe
    # geblieben - ein Schirm, auf dem es nicht reicht -, nur ist er
    # schmaler geworden.
    folded = fit["breite"][1024]["eingeklappt"].split()
    assert folded, (
        "auf 1024 px passt die Leiste bei Vorgabegroesse nicht - dann "
        "muss auch etwas eingeklappt sein:\n" + fit["report"])
    assert fit["breite"][1024]["knopf"] == "sichtbar", (
        "es ist etwas eingeklappt, aber der Knopf dazu steht nicht auf der "
        "Leiste - die Module waeren nicht erreichbar:\n" + fit["report"])

    # Und sie stehen nicht doppelt da: was eingeklappt ist, ist von der
    # Leiste verschwunden.
    placed = _placed(fit, 1024)
    doubled = [name for name in folded if name in placed]
    assert doubled == [], (
        f"eingeklappt UND auf der Leiste: {doubled}\n" + fit["report"])


def test_a_screen_with_room_keeps_every_module_on_the_bar(fit):
    """Die Gegenrichtung, und ohne sie waere die Zusicherung oben mit
    einer Leiste zu erfuellen, die immer alles einklappt.

    Auf Full HD steht heute alles, und der Knopf ist dann aus. Genau
    das ist der Unterschied zur Seitenleiste vom 11.08.2026: dort
    gehoerten zwei Module - der Fenstertitel und das Datum - auf keinen
    einzigen Schirm, weil sie QUER nicht hineinpassten. Waagerecht gibt
    es diese Klasse nicht mehr.
    """
    for width in WIDTHS:
        if width < COMPLETE_FROM:
            continue
        folded = fit["breite"][width]["eingeklappt"].split()
        assert folded == [], (
            f"auf {width} px ist Platz fuer alles, trotzdem wurde "
            f"{folded} eingeklappt:\n" + fit["report"])
        assert fit["breite"][width]["knopf"] == "aus", (
            f"auf {width} px ist nichts eingeklappt, und der Knopf steht "
            "trotzdem da:\n" + fit["report"])
        # custom-theme steht seit dem 17.08.2026 mit in dieser Reihe.
        # Der Nutzer hat es mehrfach vermisst; eine Zusicherung, die nur
        # sagt "nichts ist eingeklappt", faende ein Modul nicht, das gar
        # nicht erst aufgestellt wurde.
        for name in ("custom-date", "workspaces", "network",
                     "pulseaudio", "battery", "custom-theme",
                     "custom-system"):
            assert name in _placed(fit, width), (
                f"auf {width} px fehlt {name}:\n" + fit["report"])


def test_the_bar_holds_every_module_on_the_common_screen(fit):
    """Die Zusicherung zu "akku anzeige fehlt ... mikrofon und
    lautstaerke fehlt", und sie faengt den FEHLER und nicht das Symptom.

    Das Symptom waren vier Module. Der Fehler war, dass die Leiste bei
    der ausgelieferten Schriftgroesse mehr Platz wollte, als ein
    verbreiteter Schirm hat, und die Regel den Ueberschuss klaglos
    wegklappte - genau wie vorgesehen, nur eben ueber sechs Module, von
    denen vier eine Auskunft tragen, die man im Blick behalten will.

    Gemessen wird deshalb die BREITE, die die Leiste haben WILL, gegen
    den Schirm, auf dem sie stehen soll. Faellt diese Zeile, ist die
    Antwort nicht, den Knopf huebscher zu machen, sondern eine von
    zweien: die ausgelieferte Groesse ist zu gross (siehe DEFAULT_PX in
    src/sizes.py, wo die Ableitung steht), oder es sind zu viele Module.

    DER SCHIRM WAR VOM 12. AUF DEN 13.08.2026 EIN KLEINERER - 1366 -
    und ist seither wieder 1600, siehe COMPLETE_FROM. Der Grund ist
    keine Nachlaessigkeit, sondern eine zweite Ansage desselben Nutzers:
    er hat die Leiste, die auf 1366 vollstaendig ankam, viermal als "zu
    leer" beanstandet. Was die volle Liste kostet und was auf 1366
    einklappt, steht bei COMPLETE_FROM - mit Zahlen.
    """
    minimum = int(fit["breite"][COMPLETE_FROM]["minimum"])
    assert minimum <= COMPLETE_FROM, (
        f"die Leiste will {minimum} px und der Schirm hat "
        f"{COMPLETE_FROM} - {minimum - COMPLETE_FROM} px zu viel:\n"
        + fit["report"])

    # Und namentlich die vier, deren Fehlen der Nutzer gemeldet hat.
    # Ohne diese Zeilen bestuende die Zusicherung auch mit einer Leiste,
    # die sie gar nicht baut.
    placed = _placed(fit, COMPLETE_FROM)
    missing = [name for name in MISSED_ON_12_08 if name not in placed]
    assert missing == [], (
        f"auf {COMPLETE_FROM} px fehlen {missing} - genau die Module, "
        "deren Fehlen der Nutzer gemeldet hat:\n" + fit["report"])

    # UND WAS DER VERBREITETSTE NOTEBOOKSCHIRM DAVON NICHT MEHR TRAEGT.
    #
    # Namentlich und nicht als Anzahl: "drei Module klappen ein" waere
    # auch dann noch wahr, wenn es drei ANDERE waeren - etwa der Akku,
    # nach dem der Nutzer heute ausdruecklich gefragt hat. Diese Zeile
    # faellt, sobald ein Modul waechst oder eines dazukommt, und dann
    # gehoert die Liste bei COMPLETE_FROM neu gemessen.
    folded = tuple(fit["breite"][COMMON_NOTEBOOK]["eingeklappt"].split())
    assert folded == FOLDED_ON_COMMON_NOTEBOOK, (
        f"auf {COMMON_NOTEBOOK} px klappt die Leiste {folded} ein, "
        f"erwartet war {FOLDED_ON_COMMON_NOTEBOOK}:\n" + fit["report"])
    # WAS AUF DEM SCHMALEN SCHIRM STEHENBLEIBT, UND WAS SEIT DEM
    # 17.08.2026 NICHT MEHR.
    #
    #     Hier stand: Akku, Lautstaerke und Mikrofon muessen auch auf
    #     1366 dastehen - nach diesen dreien hat der Nutzer am
    #     13.08.2026 einzeln gefragt ("es fehlt auch ein batterie icon
    #     ich weiss nicht wie voll der laptop ist" - "und lautstaerke und
    #     mikrofon auch").
    #
    #     SIE LIEGEN DORT SEIT DEM 17.08.2026 HINTER DEM KNOPF, und das
    #     ist eine Folge zweier Ansagen desselben Nutzers vom selben Tag:
    #     eine neue Belegungsanzeige links (92 px) und der Umzug der
    #     Hardwareanzeige (165 px) von der rechten in die linke Haelfte.
    #     Der rechte Kasten wird zuerst geleert, also muss er jetzt sechs
    #     kleine Module abgeben, wo vorher vier reichten, weil eines
    #     davon das grosse war. Die gemessene Tabelle steht bei
    #     COMPLETE_FROM.
    #
    #     Es ist KEINE stille Kuerzung: kein Modul ist von der Leiste
    #     genommen, und auf dem Schirm des Nutzers (1920x1200, Faktor
    #     1.00) steht weiterhin jedes. Der Fall betrifft den 1366er
    #     Notebookschirm, und welcher der beiden neuen Posten dort
    #     weichen soll, ist eine Entscheidung des Nutzers und nicht
    #     dieser Zeile.
    #
    #     Gehalten wird deshalb, was er ZULETZT bestellt hat: die linke
    #     Haelfte steht auch auf dem schmalen Schirm vollstaendig - das
    #     Datum und die Hardwareanzeige nebeneinander. Ohne diese Zeilen
    #     waere die Zusicherung darueber auch mit einer Leiste erfuellt,
    #     die stattdessen links kuerzt.
    #
    #     GEAENDERT am 19.08.2026: die Belegungsanzeige (custom/keyboard)
    #     ist aus der Vorgabe genommen ("in die leiste und keyboard icon
    #     mit de oder us weg", woertlich) und wird deshalb auf keiner
    #     Breite mehr gebaut - auch nicht hier. An ihrer alten Stelle
    #     steht seither die Tastenkuerzel-Anzeige (custom/hypr-shortcuts,
    #     siehe _modules_left in src/style_definition.py), und sie
    #     GEMESSEN heute genauso breit wie vorher die Belegung: 92 px.
    #     Die Tabelle bei COMPLETE_FROM und FOLDED_ON_COMMON_NOTEBOOK
    #     oben aendert sich dadurch nicht - nachgemessen mit genau
    #     diesem Testlauf, gruen ohne eine einzige Zahl anzufassen.
    on_notebook = _placed(fit, COMMON_NOTEBOOK)
    for name in ("custom-hypr-shortcuts", "custom-date", "custom-hardware"):
        assert name in on_notebook, (
            f"auf {COMMON_NOTEBOOK} px liegt {name} hinter dem Knopf - "
            "die drei stehen seit dem 19.08.2026 nebeneinander links, "
            "und genau so hat der Nutzer sie bestellt:\n" + fit["report"])


def test_the_bar_folds_only_as_much_as_it_has_to(fit):
    """Eine Regel, die zu viel einklappt, besteht jede Zusicherung oben.

    Deshalb wird hier nachgezaehlt, dass eine schmalere Leiste nicht
    WENIGER einklappt als eine breitere.
    """
    counts = {width: len(fit["breite"][width]["eingeklappt"].split())
              for width in WIDTHS}
    for narrow, wide in zip(WIDTHS, WIDTHS[1:]):
        assert counts[narrow] >= counts[wide], (
            f"auf {narrow} px sind {counts[narrow]} Module eingeklappt, auf "
            f"{wide} px aber {counts[wide]} - schmaler muss mehr heissen:\n"
            + fit["report"])
    # Und die beiden Enden bleiben stehen, solange ueberhaupt Platz
    # dafuer ist: links das Datum, rechts der Knopf zum
    # Kontrollzentrum - das eine ist der Anfang der Leiste, das andere
    # der einzige Weg ins Kontrollzentrum.
    for name in ("custom-date", "custom-system"):
        assert name in _placed(fit, 1600), (
            f"{name} wurde auf 1600 px eingeklappt, obwohl es am "
            "aeusseren Ende steht und zuletzt gehen muss:\n"
            + fit["report"])


def test_a_folded_module_comes_back_when_there_is_room_again(fit):
    """Die Gegenrichtung des Einklappens, und ohne sie ist die Regel eine
    Einbahnstrasse.

    Auf dem Schreibtisch aendert sich nicht der Schirm, sondern der TEXT
    der Module: das Wetter verschwindet, die Hardwarezeile faellt von
    "88C 12GB" auf "No HW", und was dafuer weichen musste, hat wieder
    Platz. Bliebe es liegen, waere die Leiste nach einem einzigen engen
    Moment fuer den Rest der Sitzung halb leer - und nichts an ihr wuerde
    sagen, warum.

    Gemessen ueber die einfachere Schraube: derselben Leiste wird gesagt,
    ihr Schirm sei jetzt 7680 px breit. Angestossen wird die
    Neuberechnung von niemandem - sie faellt beim naechsten Takt eines
    Moduls, und dass das reicht, ist die zweite Haelfte dieser Messung.
    """
    for width in WIDTHS:
        folded = fit["wieder"][width]["eingeklappt"].split()
        assert folded == [], (
            f"die Leiste von {width} px hat auf einem 7680 px breiten "
            f"Schirm {folded} eingeklappt:\n" + fit["report"])
        assert fit["wieder"][width]["knopf"] == "aus", (
            "es ist nichts mehr eingeklappt, also gehoert auch der Knopf "
            "fort:\n" + fit["report"])

    # Und sie stehen wieder an ihrem Platz, nicht in irgendeiner
    # Reihenfolge: das Ausklappen setzt jedes Modul hinter das letzte
    # nicht eingeklappte davor.
    order = list(_placed(fit, 1280, "wieder"))
    assert order == list(_placed(fit, 1920, "wieder")), (
        "die ausgeklappte Leiste steht in einer anderen Reihenfolge da als "
        "eine, die nie eingeklappt hat:\n" + fit["report"])


# --------------------------------------------------------------------
# die Fusszeile, und was sie kostet
# --------------------------------------------------------------------
#
# GEMELDET am 12.08.2026: "und nwg dock auch nachgebaut gtk4 immer
# angezeigt unten im footer sozusagen".
#
# Das Dock war schon vorher unten verankert, exklusiv und sichtbar -
# nachgelesen in ags-dock.template, nicht angenommen. Was gefehlt hat,
# ist die Messung: eine Fusszeile, die dauerhaft steht, nimmt dauerhaft
# Hoehe weg, und diese Zahl darf niemand schaetzen muessen.

def test_the_footer_is_not_taller_than_the_icons_it_carries(dock_run):
    """Was der Fuss hoch ist, kommt von seinen Symbolen und nicht von
    Luft.

    Die Symbolgroesse ist der groesste Posten und einzeln einstellbar
    (STYLE_DOCK_ICON_SIZE, FIXED - sie folgt dem Schriftregler
    absichtlich nicht). Alles darueber hinaus sind Innenabstand, Rahmen
    und Aussenrand der Knoepfe; ein Fuss, der doppelt so hoch ist wie
    seine Symbole, hat irgendwo eine Zahl zu viel.
    """
    sys.path.insert(0, str(SRC))
    try:
        import sizes
        icon = int(sizes.value_of("STYLE_DOCK_ICON_SIZE", {}))
    finally:
        sys.path.remove(str(SRC))

    content = int(dock_run.mark("hoehe"))
    assert content >= icon, (
        f"der Fuss ist {content} px hoch und traegt {icon} px grosse "
        "Symbole - eines davon ist falsch:\n" + dock_run.report)
    assert content <= 2 * icon, (
        f"der Fuss ist {content} px hoch fuer {icon} px grosse Symbole - "
        "mehr als die Haelfte davon ist Luft:\n" + dock_run.report)


def test_the_bar_and_the_footer_leave_the_windows_room(fit, dock_run):
    """Der Preis der Fusszeile, in Pixeln und in Prozent.

    Kopf und Fuss reservieren beide einen Streifen, den kein Fenster
    bekommt. Zusammen sind das auf dem kuerzesten Schirm, den ZepOS
    ernst nimmt, ein knappes Viertel der Hoehe - und weil das eine Zahl
    ist, die beim naechsten dickeren Knopf unbemerkt waechst, steht sie
    hier.

    GEMESSEN am 12.08.2026 bei Vorgabegroesse: Leiste 100 px, Fuss 76 px
    Inhalt plus 10 px Aussenabstand, zusammen 186 px. Auf 768 px sind
    das 24.2 % - sechs Pixel unter der Grenze, und das ist knapp genug,
    dass der naechste dickere Knopf hier auffaellt.

    DIE GRENZE IST EIN VIERTEL, und sie ist eine Entscheidung: mehr als
    ein Viertel der Hoehe fuer zwei Leisten heisst, dass ein Editor auf
    einem alten Notebook mehr Rahmen als Text zeigt. Wer sie reissen
    will, muss entweder die Symbole kleiner machen oder begruenden,
    warum ein Viertel nicht mehr genug ist.
    """
    shortest = 768
    bar = int(fit["breite"][max(WIDTHS)]["dicke"])
    footer = int(dock_run.mark("hoehe")) + int(dock_run.mark("rand"))
    together = bar + footer

    assert together < shortest // 4, (
        f"Leiste {bar} px und Fusszeile {footer} px nehmen zusammen "
        f"{together} px - auf einem {shortest} px hohen Schirm sind das "
        f"{100 * together / shortest:.1f} %, und mehr als ein Viertel "
        "gehoert nicht zwei Leisten:\n" + fit["report"] + dock_run.report)

    # Und die Gegenrichtung: ein Fuss ohne Hoehe ist keiner. Ohne diese
    # Zeile waere die Zusicherung oben mit einem Dock zu erfuellen, das
    # gar nicht da ist.
    assert footer > int(dock_run.mark("rand")), (
        "die Fusszeile hat keine eigene Hoehe - dann steht nichts "
        "darauf:\n" + dock_run.report)



# --------------------------------------------------------------------
# die ganze Oberflaeche, nicht nur die Leiste
# --------------------------------------------------------------------

def test_the_whole_shell_still_compiles(tmp_path):
    """app.ts mit allem, was es importiert - dreizehn Widgets, drei
    Bausteine, ein Stylesheet.

    WAS DAS FAENGT, WAS SONST NICHTS FAENGT
        Die Vorlagen sind TypeScript, und `ags bundle` uebersetzt sie mit
        esbuild. esbuild PRUEFT KEINE TYPEN - es entfernt sie -, aber es
        loest Importe auf und liest die Syntax. Ein Tippfehler in einem
        Importpfad, eine fehlende Klammer, ein Widget, das app.ts
        importiert und das der Generator nicht mehr erzeugt: jedes davon
        ist hier ein Fehlschlag und sonst nirgends einer, bis der Nutzer
        sich anmeldet und einen leeren Schreibtisch bekommt.

        Der Test darueber baut nur die Leiste, und zwar aus einem eigenen
        Kind heraus. app.ts selbst wird von ihm nie angefasst.

    Die Zuordnung Route -> Datei kommt aus generate_config.sh, nicht aus
    einer Liste hier: eine zweite Liste waere eine, die auseinanderlaeuft,
    und zwar in der Richtung, die dieser Test gerade ausschliessen soll.
    """
    if shutil.which("ags") is None:
        pytest.skip("ags fehlt; es kommt mit dem Paket aylurs-gtk-shell")
    if shutil.which("sass") is None:
        pytest.skip("dart-sass fehlt; `ags bundle` schickt style.scss hindurch")

    generator = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    # Auch das Vorlagenverzeichnis kommt aus dem Generator: ags-style
    # liegt in templates/, bar-style in styles/, und beide enden auf
    # "-style". Eine Heuristik ueber den Namen hat genau daran gelegen.
    routes = re.findall(
        r'\n    ([a-z0-9-]+)\)\n\s*CONFIG_DIR="\$ZEPOS_OUTPUT_ROOT/ags([^"]*)"'
        r'\n\s*CONFIG_FILE="([^"]+)"'
        r'(\n\s*ZEPOS_TEMPLATE_SUBDIR="styles")?', generator)
    assert len(routes) >= 15, (
        f"nur {len(routes)} AGS-Routen gefunden - der Generator wird nicht "
        "gelesen, also sagt dieses Ergebnis nichts")

    processor = _renderer()
    for route, subdirectory, filename, styles in routes:
        source = SRC / ("styles" if styles else "templates")
        target = tmp_path / subdirectory.lstrip("/") / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        processor.apply_template(source / f"{route}.template", target)

    assert (tmp_path / "app.ts").is_file(), "app.ts hat keine Route"

    bundle = tmp_path / "shell.js"
    result = subprocess.run(
        ["ags", "bundle", str(tmp_path / "app.ts"), str(bundle),
         "-r", str(tmp_path), "-g", "4"],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (
        "die Oberflaeche laesst sich nicht mehr uebersetzen:\n"
        + result.stdout + result.stderr)
    assert bundle.is_file()



# ---------------------------------------------------------------------
# Die Kopie gegen das Original
# ---------------------------------------------------------------------
# BAR_EVERYTHING oben ist eine ABSCHRIFT der ausgelieferten Modulliste,
# und Abschriften veralten. Am 17.08.2026 ist genau das passiert: der
# Nutzer wollte custom/keyboard rechts vom Datum statt links, die Vorgabe
# in src/style_definition.py wanderte - und diese Datei blieb stehen.
# Einunddreissig Tests blieben gruen und massen dabei eine Leiste, die es
# nicht mehr gab.
#
# Das ist die teuerste Sorte Fehler in diesem Baum: kein rotes Ergebnis,
# keine Meldung, nur ein Messgeraet, das eine andere Sache misst als die,
# die ausgeliefert wird.

# UND ER HAT BIS ZUM 20.08.2026 NUR DIE LINKE HAELFTE ANGESEHEN
# (Aufgabe 42).
#
#     _vorgabe_links() hiess so, weil es auch nur die linke las - der
#     Anlass am 17.08.2026 war ein Tausch links, und der Waechter ist
#     genau so weit gebaut worden, wie der Anlass reichte. Die rechte
#     Abschrift war damit von Anfang an ungehalten, und sie war auch von
#     Anfang an falsch: custom/disk stand darin hinter `tray` statt an
#     zweiter Stelle, und custom/updates vor custom/privacy statt
#     dahinter.
#
#     Ein Waechter, der die HAELFTE seines Gegenstandes ansieht, ist
#     kein halber Waechter, sondern eine ganze Zusicherung ueber die
#     falsche Sache. Er liest seit heute beide Haelften.
_SEITEN = {"left": "linke", "right": "rechte"}


def _vorgabe(seite: str) -> list[str]:
    """Eine ausgelieferte Modulliste, aus der Quelle gelesen.

    `seite` ist "left" oder "right".
    """
    import style_definition
    daten = style_definition.shipped_bar_imprint()
    namen = (f"modules_{seite}", f"bar_{seite}")
    for schluessel in namen:
        if schluessel in daten:
            return list(daten[schluessel])
    # Die Aufteilung kann verschachtelt sein - dann eine Ebene tiefer.
    leiste = daten.get("bar", {})
    for schluessel in namen:
        if schluessel in leiste:
            return list(leiste[schluessel])
    raise AssertionError(
        f"in der Vorgabe steht keine {_SEITEN[seite]} Modulliste: "
        f"{sorted(daten)}")


@pytest.mark.parametrize("seite", sorted(_SEITEN))
def test_die_nachbarschaft_ist_die_der_vorgabe(seite):
    """Wo ein Modul steht, wird von der Vorgabe abgelesen - so sagt es
    der Kommentar an BAR_EVERYTHING, und so wird es hier gehalten.

    Verglichen wird die REIHENFOLGE der gemeinsamen Module, nicht die
    Menge: BAR_EVERYTHING stellt absichtlich jeden Zweig einmal auf und
    traegt deshalb mehr Module als die Vorgabe. Die Reihenfolge ist
    zugleich die Einklappreihenfolge, also keine Kosmetik - sie
    entscheidet, was auf einem engen Schirm zuerst verschwindet.
    """
    vorgabe = _vorgabe(seite)
    abschrift = BAR_EVERYTHING["bar"][f"modules_{seite}"]

    gemeinsam_vorgabe = [m for m in vorgabe if m in abschrift]
    gemeinsam_abschrift = [m for m in abschrift if m in vorgabe]

    assert gemeinsam_vorgabe, (
        f"die {_SEITEN[seite]} Abschrift und die Vorgabe haben kein Modul "
        "gemeinsam - eine von beiden meint etwas voellig anderes")
    assert gemeinsam_abschrift == gemeinsam_vorgabe, (
        f"BAR_EVERYTHING ist in der {_SEITEN[seite]}n Haelfte gegenueber "
        "src/style_definition.py veraltet.\n"
        f"  Vorgabe:   {gemeinsam_vorgabe}\n"
        f"  Abschrift: {gemeinsam_abschrift}\n"
        "Jede Breitenzusicherung in dieser Datei misst damit eine Leiste, "
        "die so nicht ausgeliefert wird.")


@pytest.mark.parametrize("seite", sorted(_SEITEN))
def test_that_guard_would_notice_a_swap(seite):
    """Der Waechter selbst, gegen eine verfaelschte Abschrift gehalten.

    Ein Test, der auch dann gruen bleibt, wenn man die Sache kaputtmacht,
    ist keiner - und dieser hier ist erst entstanden, weil sein Gegenstand
    unbemerkt kaputtgegangen war.

    GEAENDERT am 20.08.2026: er hielt bloss fest, dass ein Tausch die
    Liste veraendert - das haette auch eine Zusicherung ueber `list`
    getan. Jetzt laeuft der VERGLEICH des Waechters gegen die
    verfaelschte Abschrift, und er muss ihn abweisen.
    """
    vorgabe = _vorgabe(seite)
    abschrift = BAR_EVERYTHING["bar"][f"modules_{seite}"]
    gemeinsam = [m for m in vorgabe if m in abschrift]
    if len(gemeinsam) < 2:
        pytest.skip("weniger als zwei gemeinsame Module - nichts zu tauschen")

    vertauscht = list(gemeinsam)
    vertauscht[0], vertauscht[1] = vertauscht[1], vertauscht[0]
    assert vertauscht != gemeinsam, "der Tausch hat nichts veraendert"
    # Und genau das ist der Vergleich, den der Test darueber anstellt.
    assert [m for m in vertauscht if m in vorgabe] != gemeinsam, (
        "der Waechter vergleicht die Reihenfolge nicht - eine vertauschte "
        "Abschrift kaeme bei ihm durch")


# ---------------------------------------------------------------------
# Was waechst, steht innen
# ---------------------------------------------------------------------
# BESTELLT am 20.08.2026 (Aufgabe 42): "ich wollte auch das du sie
# zentrierst die icon und sie anders anordnest logisch gesehen im
# header". Der gewaehlte Entwurf stellt alles Wachsende nach innen -
# `custom/media` und `tray` -, damit die Knoepfe am Rand stillstehen.
#
# WAS DABEI SCHIEBT, UND IN WELCHE RICHTUNG - GEMESSEN an diesem Tag mit
# dem `fit`-Aufbau dieser Datei, 1920 px, Vorgabegroesse:
#
#     Der rechte Kasten ist das Endstueck eines Gtk.CenterBox und haengt
#     an der RECHTEN Kante. Ein Modul dort um 160 Punkte verbreitert -
#     an genau dem Platz, an dem die Ablage bis dahin stand -, und sechs
#     Klickziele wandern um dieselben 160 Punkte nach links
#     (custom-disk, network, bluetooth, pulseaudio,
#     pulseaudio#microphone, battery), waehrend custom-theme und
#     custom-system auf ihrem Punkt bleiben.
#
#     Dieselbe Verbreiterung am INNERSTEN Platz bewegt KEIN einziges
#     Modul: custom-media mit 121 Punkten aufgestellt, und custom-disk
#     steht weiter auf 1405, custom-system weiter auf 1848.
#
# DARAUS DIE REGEL, UND SIE IST FUER JEDE HAELFTE EINE ANDERE RICHTUNG:
# ein wachsendes Modul schiebt alles, was zwischen ihm und der KANTE
# steht, an der sein Kasten haengt. Rechts ist das alles VOR ihm in der
# Liste, links alles DAHINTER. Ein festes Klickziel darf dort nicht
# stehen.
#
# WARUM DIE EINTEILUNG AUS DER QUELLE KOMMT UND NICHT AUS EINER LISTE
# HIER: eine abgeschriebene Liste veraltet still. Diese Datei hat am
# selben Tag drei solche Abschriften gefunden - zwei in der rechten
# Haelfte von BAR_EVERYTHING und eine im Kommentar bei _modules_right.
# Gelesen wird deshalb, was die Leiste WIRKLICH baut: die `case`-Zweige
# aus ags-bar.template und die Skripte, die sie namentlich nennen.

BAR_VORLAGE = SRC / "templates" / "ags-bar.template"
ERZEUGER = SRC / "generate_config.sh"

# Ein Text, der auf eine Sprosse der Messleiter geschnitten wird, ist
# genau einer, der von sich aus keine Grenze hat - sonst brauchte er den
# Schnitt nicht. Das ist das Kennzeichen, an dem ein wachsendes Modul in
# dieser Quelle zu erkennen ist, und es steht an genau zwei Stellen:
# TITLE_LIMIT in ags-media-scripts.template und set_max_width_chars() in
# windowModule().
MASS_GRENZE = re.compile(r"\{\{STYLE_MEASURE_[A-Z_]+\}\}")


def _modulzweige() -> dict[str, str]:
    """Name -> Quelltext seines `case`-Zweiges in ags-bar.template."""
    text = BAR_VORLAGE.read_text(encoding="utf-8")
    zweige = {}
    for stueck in re.split(r'\n\s*case "', text)[1:]:
        name, _, rest = stueck.partition('"')
        # Der letzte Zweig laeuft sonst in `default:` und den Rest der
        # Datei hinein.
        zweige[name] = re.split(r"\n\s*default:", rest)[0]
    return zweige


def _skriptvorlagen() -> dict[str, str]:
    """Dateiname eines Leistenskripts -> Quelltext seiner Vorlage.

    Gelesen aus src/generate_config.sh, weil dort steht, welche Vorlage
    welche Datei erzeugt. Eine zweite Zuordnung an dieser Stelle waere
    die vierte Abschrift in dieser Sache.
    """
    erzeuger = ERZEUGER.read_text(encoding="utf-8")
    # Zwischen dem Namen der Route und ihren Zeilen duerfen Kommentare
    # stehen, und bei bar-weather-config tun sie es auch.
    kommentar = r"(?:\s*#[^\n]*\n)*"
    routen = re.findall(
        r'\n    ([a-z0-9-]+)\)\n' + kommentar
        + r'\s*CONFIG_DIR="\$ZEPOS_OUTPUT_ROOT/ags/scripts"\n' + kommentar
        + r'\s*CONFIG_FILE="([^"]+)"', erzeuger)
    vorlagen = {}
    for route, datei in routen:
        quelle = SRC / "templates" / f"{route}.template"
        if quelle.is_file():
            vorlagen[datei] = quelle.read_text(encoding="utf-8")
    return vorlagen


def _feste_klickziele(zweige: dict[str, str]) -> set[str]:
    """Module, die ein Zeichen und einen Klick sind und sonst nichts.

    staticModule() bekommt das Zeichen als Zeichenkette aus der Vorlage
    und ruft kein Skript. Seine Breite steht damit im Baum und nicht in
    der Laufzeit - es ist das Ziel, das man blind anfaehrt.
    """
    return {name for name, text in zweige.items()
            if "staticModule(" in text}


def _wachsende(zweige: dict[str, str],
               skripte: dict[str, str]) -> set[str]:
    """Module, deren Breite etwas ausserhalb dieses Baumes bestimmt.

    Zwei Kennzeichen, beide aus der Quelle:

        Tray(          die Ablage haengt ihre Kinder an, eines je
                       fremdem Dienst, ohne Obergrenze.
        eine Sprosse   der Text muss geschnitten werden, hat also von
        der Messleiter sich aus keine Grenze - im Zweig selbst oder in
                       dem Skript, das er namentlich ruft.
    """
    wachsend = set()
    for name, text in zweige.items():
        if "Tray(" in text or MASS_GRENZE.search(text):
            wachsend.add(name)
            continue
        gerufen = re.search(r"\$\{SCRIPTS\}/([\w.-]+)", text)
        if gerufen and MASS_GRENZE.search(skripte.get(gerufen.group(1), "")):
            wachsend.add(name)
    return wachsend


def _verschobene_klickziele(reihe: list[str], wachsend: set[str],
                            fest: set[str], seite: str) -> list[str]:
    """Jedes Paar aus wachsendem Modul und Klickziel, das es schiebt."""
    treffer = []
    for platz, modul in enumerate(reihe):
        if modul not in wachsend:
            continue
        if seite == "right":
            geschoben, versatz = reihe[:platz], 0
        else:
            geschoben, versatz = reihe[platz + 1:], platz + 1
        for weiter, ziel in enumerate(geschoben):
            if ziel in fest:
                treffer.append(
                    f"{modul} (Platz {platz}) waechst und schiebt "
                    f"{ziel} (Platz {versatz + weiter})")
    return treffer


def test_kein_wachsendes_modul_steht_rechts_von_einem_festen_klickziel():
    """Die Zusicherung zu "sie anders anordnest logisch gesehen".

    Sie faellt, sobald jemand ein wachsendes Modul zwischen die festen
    Knoepfe stellt - und genau das war bis zum 20.08.2026 der Fall: die
    Ablage stand an achter Stelle, und jedes neue Ablagesymbol hat sechs
    Klickziele unter dem Zeiger weggezogen. Die Messung dazu steht im
    Kopf dieses Abschnitts.
    """
    zweige = _modulzweige()
    fest = _feste_klickziele(zweige)
    wachsend = _wachsende(zweige, _skriptvorlagen())

    # Ohne diese drei Zeilen waere alles darunter mit einer Einteilung
    # erfuellt, die nichts gefunden hat.
    assert fest, ("in ags-bar.template steht kein einziger "
                  "staticModule()-Zweig - die Einteilung hat nichts "
                  "gefunden, also misst dieser Test nichts")
    assert wachsend, ("kein einziges wachsendes Modul gefunden - "
                      "entweder ist Tray() umbenannt oder die Messleiter "
                      "heisst nicht mehr STYLE_MEASURE_*")
    assert "tray" in wachsend, (
        "die Ablage gilt der Einteilung nicht als wachsend, obwohl sie "
        "je fremdem Dienst ein Symbol anhaengt - dann taugt die "
        "Einteilung nicht:\n" + repr(sorted(wachsend)))

    for seite in sorted(_SEITEN):
        reihe = _vorgabe(seite)
        fehlt = [modul for modul in reihe if modul not in zweige]
        assert fehlt == [], (
            f"die {_SEITEN[seite]} Vorgabe nennt {fehlt}, und "
            "ags-bar.template hat dafuer keinen `case`-Zweig - die "
            "Einteilung kann ueber diese Module nichts sagen")
        verstoesse = _verschobene_klickziele(reihe, wachsend, fest, seite)
        assert verstoesse == [], (
            f"in der {_SEITEN[seite]}n Haelfte steht ein wachsendes Modul "
            "zwischen der Kante und einem festen Klickziel:\n  "
            + "\n  ".join(verstoesse)
            + "\n\nWachsend: " + ", ".join(sorted(wachsend))
            + "\nFeste Klickziele: " + ", ".join(sorted(fest))
            + "\nReihe: " + ", ".join(reihe)
            + "\n\nDas Klickziel wandert dann bei jeder Aenderung des "
              "wachsenden Moduls unter dem Zeiger weg. Siehe "
              "_modules_right in src/style_definition.py.")

    # UND DASS DIE RECHTE HAELFTE BEIDE SORTEN UEBERHAUPT TRAEGT.
    #
    # Sie ist die Haelfte, um die es geht: dort stehen die Ablage, die
    # Wiedergabe und die beiden Knoepfe. Waere eine der beiden Sorten
    # dort leer, waere die Schleife oben auf dieser Seite gruen, ohne
    # etwas verglichen zu haben.
    rechts = _vorgabe("right")
    assert [m for m in rechts if m in wachsend], (
        "die rechte Vorgabe traegt kein wachsendes Modul - dann sagt "
        "dieser Test ueber sie nichts:\n" + ", ".join(rechts))
    assert [m for m in rechts if m in fest], (
        "die rechte Vorgabe traegt kein festes Klickziel - dann sagt "
        "dieser Test ueber sie nichts:\n" + ", ".join(rechts))

    # DIE EINE LUECKE DIESER EINTEILUNG, MIT NAMEN.
    #
    # hyprland/window traegt einen Fenstertitel und ist damit von
    # derselben Sorte wie custom/media - seine Obergrenze steht aber in
    # windowModule() und nicht im `case`-Zweig, also findet die
    # Einteilung es nicht. Es ist nicht ausgeliefert (siehe
    # _bar_optional in src/style_definition.py), die Luecke trifft also
    # heute nichts. Diese Zeile faellt an dem Tag, an dem jemand es
    # aufstellt - und dann gehoert die Einteilung erweitert und nicht
    # diese Zeile gestrichen.
    for seite in sorted(_SEITEN):
        assert "hyprland/window" not in _vorgabe(seite), (
            "hyprland/window steht in der Vorgabe, und die Einteilung "
            "oben erkennt es nicht als wachsend - seine Obergrenze steht "
            "in windowModule() statt im `case`-Zweig")


def test_der_waechter_faende_die_ablage_an_ihrem_alten_platz():
    """Der Waechter gegen die Reihenfolge von gestern gehalten.

    Bis zum 20.08.2026 stand `tray` zwischen dem Akku und
    custom/privacy, also RECHTS von custom/disk. Ein Waechter, der das
    durchgehen liesse, haette den Umbau des Tages nicht gehalten,
    sondern nur begleitet.
    """
    zweige = _modulzweige()
    fest = _feste_klickziele(zweige)
    wachsend = _wachsende(zweige, _skriptvorlagen())

    vorher = ["custom/media", "custom/disk", "network", "bluetooth",
              "pulseaudio", "pulseaudio#microphone", "battery", "tray",
              "custom/privacy", "custom/updates", "custom/theme",
              "custom/system"]
    verstoesse = _verschobene_klickziele(vorher, wachsend, fest, "right")
    assert verstoesse, (
        "der Waechter findet an der Reihenfolge vom 19.08.2026 nichts - "
        "dann findet er auch nichts, wenn sie jemand wiederherstellt:\n"
        + ", ".join(vorher))
    # Namentlich, und nicht als Anzahl: "es hat etwas gefunden" waere
    # auch mit einem ganz anderen Fund erfuellt.
    assert any("tray" in treffer and "custom/disk" in treffer
               for treffer in verstoesse), (
        "der Waechter meldet etwas, aber nicht die Ablage vor "
        "custom/disk - und genau das war der Fund:\n  "
        + "\n  ".join(verstoesse))

    # Und an der HEUTIGEN Reihenfolge findet derselbe Aufruf nichts.
    assert _verschobene_klickziele(_vorgabe("right"), wachsend, fest,
                                   "right") == []
