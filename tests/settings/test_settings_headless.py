# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Einstellungs-Anwendung, bedient - und die erzeugte Datei danach.

WAS DAS SCHLIESST
    Die Luecke, die dieses Projekt schon zweimal getroffen hat: eine
    Reglertabelle, die kein erzeugtes Byte veraendert
    (MONITOR_HEIGHT_SCALES), und vier Regler in der Einstellungsdatei
    jedes Nutzers, die keine Zeile las ("fonts", "spacing"). Beide sahen
    in der Datei und in jeder Oberflaeche genauso aus wie ein Regler,
    der etwas tut.

    Ein Fenster, das nur GEBAUT wurde, sagt darueber nichts. Hier wird
    deshalb der Regler wirklich bewegt, wirklich gespeichert - und
    danach wird aus der geschriebenen Einstellungsdatei mit dem ECHTEN
    Prozessor eine Vorlage erzeugt und gegen dieselbe Vorlage ohne die
    Aenderung gehalten. Erst diese letzte Zeile ist der Beweis.

DIE ANZEIGE
    tests/gtk4_headless.py, dieselbe wie beim graphischen Installer und
    beim Auswahlfenster.

WAS HIER NICHT GEMESSEN WIRD
    Der Generator. `zepos-generate --all` beendet AGS und startet es neu
    - auf der Maschine, auf der diese Suite laeuft, waere das die Leiste
    des Entwicklers. Gemessen wird stattdessen, WELCHEN Befehl die
    Anwendung absetzt und was sie danach mit der Marke fuer die naechste
    Anmeldung tut; der Befehl selbst hat seine eigenen Tests.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from src import settings as settings_file
from src import sizes
from tests.conftest import NEVER_PASSTHROUGH, assert_safe_to_passthrough
from tests.gtk4_headless import (
    broadwayd, gi_interpreter, start_broadwayd, stop_broadwayd,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
SETTINGS_ROOT = ROOT / "settings"
CHILD = Path(__file__).resolve().parent / "settings_headless_child.py"

CHILD_TIMEOUT = 120

# Eine eigene Anzeigenummer je Lauf. 11 und 12 gehoeren
# tests/installer/test_gui_headless.py, 21 bis 98 tests/menu/. Zwei
# broadwayd auf derselben Nummer teilen sich einen Socketnamen, und der
# zweite findet den Socket des ersten - der Lauf misst dann ein Fenster
# im falschen Prozess.
_DISPLAYS = iter(range(121, 199))


def _interpreter():
    return gi_interpreter({"Gtk": "4.0", "Adw": "1"})


@pytest.fixture
def bar_model(monkeypatch):
    """model.py dieser Anwendung, hier im Testprozess gelesen.

    Nur fuer die WORTLAUTE, die das Kind gleich anzeigen soll. Sie hier
    abzuschreiben waere die Art Test, die gruen bleibt, wenn die
    Oberflaeche etwas anderes sagt.

    Dieselbe Form wie die `model`-Fixture in test_settings_model.py, und
    aus demselben Grund muss der Pfad danach wieder herunter: ein
    liegengelassenes src/ laesst tests/src/test_placeholders.py
    durchgehen, wo es abbrechen soll. model.py bringt kein `gi` herein -
    das ist seine tragende Regel -, also geht das hier ohne Kind.
    """
    import sys

    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.syspath_prepend(str(SETTINGS_ROOT))
    for name in list(sys.modules):
        if name.startswith("zepos_settings_gui") or name in (
                "brand", "sizes", "settings", "update", "paths", "theme"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    from zepos_settings_gui import model as module

    return module


class Run:
    """Was ein Lauf hinterlassen hat."""

    def __init__(self, returncode: int, stdout: str, stderr: str,
                 trace: str, home: Path) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.trace = trace
        self.home = home

    @property
    def marks(self) -> list[str]:
        return self.trace.splitlines()

    def mark(self, prefix: str) -> str:
        found = [line for line in self.marks if line.startswith(prefix + ":")]
        assert found, f"keine Marke {prefix} in der Spur:\n{self.report}"
        return found[0].split(":", 1)[1]

    def after(self, verb: str, prefix: str) -> str:
        """Die Marke `prefix`, wie sie NACH dieser Anweisung stand.

        Die Spur ist eine Folge von Bloecken: ein Block beim Aufbau, dann
        einer nach jeder Anweisung, jeder mit demselben Satz Marken.
        Ohne diesen Zugriff koennte ein Test nur den ersten Block lesen -
        also genau den Zustand vor jeder Bedienung.
        """
        marks = self.marks
        start = marks.index(f"after-{verb}:")
        for line in marks[start + 1:]:
            if line.startswith("after-"):
                break
            if line.startswith(prefix + ":"):
                return line.split(":", 1)[1]
        raise AssertionError(
            f"keine Marke {prefix} nach {verb} in der Spur:\n{self.report}")

    @property
    def settings(self) -> dict:
        path = self.home / "zepos" / "user-settings.json"
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @property
    def report(self) -> str:
        return (f"rueckgabewert: {self.returncode}\n"
                f"stdout: {self.stdout!r}\n"
                f"stderr:\n{self.stderr}\n"
                f"spur:\n{self.trace}")


def run_settings(tmp_path: Path, script: str, *,
                 document: dict | None = None,
                 update_config: dict | None = None,
                 shipped_bar: dict | None = None,
                 applications: dict[str, str] | None = None,
                 stubs: dict[str, str] | None = None,
                 environment_extra: dict[str, str] | None = None,
                 extra: list[str] | None = None) -> Run:
    interpreter = _interpreter()
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4/Adw laden - "
                    "python-gobject, gtk4 und libadwaita installieren")
    display_server = broadwayd()
    if display_server is None:
        pytest.skip("gtk4-broadwayd fehlt; es kommt mit dem Paket gtk4")

    executable, extra_path = interpreter
    display = next(_DISPLAYS)

    tmp_path.mkdir(parents=True, exist_ok=True)
    runtime_dir = tmp_path / "run"
    runtime_dir.mkdir(exist_ok=True)
    # GLib lehnt ein weltlesbares XDG_RUNTIME_DIR ab und sagt es auf stderr.
    runtime_dir.chmod(0o700)
    for name in ("tmp", "home", "cache", "config", "state", "etc",
                 "etc-zepos", "var-zepos"):
        (tmp_path / name).mkdir(exist_ok=True)
    empty_path = tmp_path / "no-binaries-here"
    empty_path.mkdir(exist_ok=True)

    # Der ganze PATH des Kindes. Leer, solange niemand einen
    # Stellvertreter bestellt - siehe die Begruendung bei "PATH" unten.
    #
    # WARUM DIE BILDSCHIRMSEITE EINEN BRAUCHT UND DER GENERATOR NICHT
    #     Der Generator bekommt einen `runner`, der ihn nur aufschreibt:
    #     ihn wirklich zu rufen beendete AGS des Entwicklers. `hyprctl`
    #     ist der andere Fall - die Bildschirmseite ruft es WIRKLICH, und
    #     der Waechter, der den Rueckfall ausfuehrt, ist ein eigener
    #     Prozess und geht an jedem `runner` vorbei. Ein Stellvertreter
    #     auf PATH ist der einzige Ort, an dem beide zu fassen sind.
    #
    #     conftest.NEVER_PASSTHROUGH fuehrt hyprctl namentlich. Ein
    #     "Durchreicher" - das echte Programm unter einem absoluten Pfad -
    #     ist fuer diese Namen verboten, und die Pruefung steht hier
    #     statt in der Disziplin dessen, der einen Stellvertreter
    #     hinschreibt: sie aenderte die Sitzung, in der diese Suite
    #     laeuft.
    for name, script_text in (stubs or {}).items():
        if name in NEVER_PASSTHROUGH:
            for place in ("/usr/bin/", "/bin/", "/usr/local/bin/"):
                assert place + name not in script_text, (
                    f"der Stellvertreter fuer {name} ruft das echte "
                    f"Programm unter {place}{name}. Genau dieser Name "
                    "steht in conftest.NEVER_PASSTHROUGH, weil er die "
                    "Maschine aendert, auf der die Tests laufen.")
        else:
            assert_safe_to_passthrough(name)
        stub = empty_path / name
        stub.write_text(script_text, encoding="utf-8")
        stub.chmod(0o755)

    user_root = tmp_path / "home" / "zepos"
    user_root.mkdir(parents=True, exist_ok=True)
    if document is not None:
        (user_root / "user-settings.json").write_text(
            json.dumps({"schema_version": 1, **document}), encoding="utf-8")
    if update_config is not None:
        (tmp_path / "etc-zepos" / "update.json").write_text(
            json.dumps({"schema_version": 1, **update_config}),
            encoding="utf-8")

    # Der Abdruck der ausgelieferten Leiste liegt unter der
    # SYSTEMwurzel, und die zeigt sonst auf src/ dieses Checkouts. Ein
    # Lauf, der einen bestellt, bekommt deshalb eine eigene Wurzel: eine
    # Datei in src/ abzulegen hiesse, den Arbeitsbaum des Entwicklers zu
    # aendern, um einen Test zu bedienen.
    #
    # Umgelenkt wird NUR dann. Die Anwendung fragt die Systemwurzel
    # heute ausschliesslich nach diesem Abdruck - GEMESSEN am
    # 12.08.2026, `grep -rn "system_root()" src/*.py` nennt ausser
    # paths.py selbst nur src/settings.py -, aber ein Lauf, der etwas
    # anderes misst, soll dieselbe Umgebung haben wie vorher.
    system_root = SRC
    if shipped_bar is not None:
        system_root = tmp_path / "system"
        system_root.mkdir(exist_ok=True)
        (system_root / settings_file.SHIPPED_BAR).write_text(
            json.dumps(shipped_bar), encoding="utf-8")

    # Die Anwendungseintraege, die GIO auf dieser "Maschine" findet.
    #
    # In einem EIGENEN Datenverzeichnis vor /usr/share, nicht statt
    # dessen: die Symbole der Reiter kommen von dort, und ohne sie meldet
    # GTK Warnungen, auf die dieser Lauf prueft. Die Reihenfolge in
    # XDG_DATA_DIRS entscheidet nur, wer zuerst gefragt wird.
    data_dirs = "/usr/share"
    if applications is not None:
        share = tmp_path / "share" / "applications"
        share.mkdir(parents=True, exist_ok=True)
        for name, text in applications.items():
            (share / name).write_text(text, encoding="utf-8")
        data_dirs = f"{tmp_path / 'share'}:{data_dirs}"

    trace_file = tmp_path / "trace.txt"

    environment = {
        # Ein Verzeichnis, das NUR die bestellten Stellvertreter
        # enthaelt, als ganzer PATH. Ohne das faende model.elevator() das
        # pkexec des Entwicklers, und der Test maesse eine Maschine statt
        # einer Anwendung.
        "PATH": str(empty_path),
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "XDG_RUNTIME_DIR": str(runtime_dir),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        # NICHT leer, anders als beim Auswahlfenster: dieses Fenster
        # zeichnet Symbole aus dem Thema (die Reiter, die
        # Zuruecksetzen-Pfeile), und ohne /usr/share findet GTK keins
        # davon und meldet es als Warnung - eine Warnung ueber den
        # Testaufbau, die die Pruefung auf echte Warnungen unbrauchbar
        # macht. `applications` haengt ein eigenes Verzeichnis davor,
        # siehe oben.
        "XDG_DATA_DIRS": data_dirs,
        "ZEPOS_USER_ROOT": str(user_root),
        "ZEPOS_MACHINE_ROOT": str(tmp_path / "etc-zepos"),
        "ZEPOS_STATE_ROOT": str(tmp_path / "var-zepos"),
        "ZEPOS_SYSTEMD_ETC": str(tmp_path / "etc"),
        "ZEPOS_SYSTEM_ROOT": str(system_root),
        "GDK_BACKEND": "broadway",
        "BROADWAY_DISPLAY": f":{display}",
        "GSETTINGS_BACKEND": "memory",
        "NO_AT_BRIDGE": "1",
        "LC_ALL": "C",
        "PYTHONPATH": os.pathsep.join(
            [str(ROOT), str(SETTINGS_ROOT), str(SRC), *extra_path]),
        "PYTHONUNBUFFERED": "1",
    }

    # Was ein Stellvertreter braucht, um zu antworten: der Pfad seiner
    # hinterlegten Antwort und der seines Protokolls. Zuletzt gesetzt,
    # damit sichtbar bleibt, dass die Umgebung oben vollstaendig ist -
    # ein Test, der PATH oder HOME hierueber verstellte, waere ein Test,
    # der die Isolation aufweicht, ohne dass es an der Isolation steht.
    for key, value in (environment_extra or {}).items():
        assert key not in environment, (
            f"{key} steht schon in der Umgebung dieses Laufs; ein "
            "Stellvertreter darf sie ergaenzen und nicht umschreiben")
        environment[key] = value

    stdout_file = tmp_path / "stdout.txt"
    stderr_file = tmp_path / "stderr.txt"

    process, _socket = start_broadwayd(display_server, runtime_dir, display)
    try:
        with stdout_file.open("w", encoding="utf-8") as out, \
                stderr_file.open("w", encoding="utf-8") as err:
            completed = subprocess.run(
                [executable, str(CHILD), str(trace_file), script,
                 *(extra or [])],
                env=environment, cwd=str(tmp_path),
                stdout=out, stderr=err, text=True, timeout=CHILD_TIMEOUT,
            )
    finally:
        stop_broadwayd(process)

    trace = trace_file.read_text(encoding="utf-8") if trace_file.exists() else ""
    run = Run(completed.returncode,
              stdout_file.read_text(encoding="utf-8"),
              stderr_file.read_text(encoding="utf-8"),
              trace, tmp_path / "home")

    assert run.returncode != 139, (
        "das Kind ist abgestuerzt - das ist, was GTK ohne Anzeige tut, "
        "also hat broadway die Verbindung nicht angenommen:\n" + run.report)
    assert "FAILURE" not in trace, run.report
    for level in ("-CRITICAL **:", "-WARNING **:", "-ERROR **:"):
        assert level not in run.stderr, (
            f"GLib hat ein {level.strip(' *:-')} gemeldet:\n" + run.report)
    return run


# --------------------------------------------------------------------
# Die Erzeugung, gegen die gemessen wird
# --------------------------------------------------------------------

def _render(tmp_path: Path, document: dict | None,
            templates: list[Path]) -> str:
    """Die genannten Vorlagen, erzeugt ueber einer Einstellungsdatei.

    Wortgleich zum Verfahren in tests/src/test_sizes.py: die Stil-SSOT
    liest die Datei beim IMPORT, also gibt es keinen anderen Weg, ihr
    andere Einstellungen zu geben, als sie neu zu importieren. Und
    erzeugt wird mit dem echten ConfigProcessor - ein str.replace()
    dieses Tests maesse seine eigene Ersetzung.

    EIGENER monkeypatch-KONTEXT UND NICHT DER DER PRUEFUNG, und das ist
    eine Messung vom 12.08.2026: die Stil-SSOT fragt beim Import
    `hyprctl` nach den Bildschirmen, also muss subprocess.run hier
    ausfallen, damit die Werte allein an den Einstellungen haengen. Mit
    der Fixture der Pruefung blieb dieser Ausfall bis zu deren Ende
    stehen - und die naechste run_settings() derselben Pruefung konnte
    dann keinen Interpreter mehr suchen, weil gi_interpreter() dafuer
    ein Kind startet und ein OSError als "kann kein gi" liest. Das
    Ergebnis war eine Pruefung, die sich selbst UEBERSPRANG statt zu
    scheitern: gruen im Bericht, nichts gemessen.
    """
    home = tmp_path / "rendering"
    home.mkdir(parents=True, exist_ok=True)

    with pytest.MonkeyPatch.context() as patched:
        patched.delenv("ZEPOS_SYSTEM_ROOT", raising=False)
        patched.setenv("ZEPOS_USER_ROOT", str(home))
        patched.setenv("XDG_CONFIG_HOME", str(home))
        patched.syspath_prepend(str(SRC))
        patched.setattr(
            subprocess, "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                FileNotFoundError("hyprctl")))
        if document is not None:
            (home / "user-settings.json").write_text(
                json.dumps(document), encoding="utf-8")

        spec = importlib.util.spec_from_file_location(
            f"zepos_style_probe_{home.parent.name}_{id(document)}",
            SRC / "style_definition.py")
        style = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(style)

        import template_processor

        out = home / "out"
        out.mkdir(exist_ok=True)
        rendered = []
        for template in templates:
            target = out / template.stem
            template_processor.ConfigProcessor(
                styles=dict(style.STYLE_VARIABLES)).apply_template(
                    template, target)
            rendered.append(target.read_text(encoding="utf-8"))
    return "\n".join(rendered)


def _templates_naming(placeholder: str) -> list[Path]:
    needle = "{{" + placeholder + "}}"
    return [path
            for directory in (SRC / "templates", SRC / "styles")
            for path in sorted(directory.glob("*.template"))
            if needle in path.read_text(encoding="utf-8")]


# --------------------------------------------------------------------
# Der Massstab - der eine Regler, den der Nutzer selbst genannt hat
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_scale_reaches_the_file_and_the_generated_bytes(tmp_path):
    """Der ganze Weg in einem Lauf.

    Regler auf 2.5, speichern - und danach steht die 2.5 in
    user-settings.json UND das erzeugte Stylesheet ist ein anderes als
    dasselbe Stylesheet ohne die Aenderung.

    Die letzte Haelfte ist die, um derentwillen es diesen Test gibt.
    Ohne sie waere "gespeichert" die ganze Aussage, und genau so sahen
    die vier Regler aus, die niemand las.
    """
    run = run_settings(tmp_path, "scale:2.5 save")

    assert run.after("save", "scale") == "2.5000", run.report
    assert run.settings["sizes"]["scale"] == 2.5, run.report

    templates = _templates_naming(f"{sizes.FONT_PREFIX}BODY")
    assert templates
    before = _render(tmp_path / "a", None, templates)
    after = _render(tmp_path / "b", run.settings, templates)
    assert after != before, (
        "der Massstab wurde gespeichert und veraendert keine erzeugte "
        "Datei")
    # Und zwar mit genau dieser Zahl: 13 * 2.5 = 32.5, kaufmaennisch 33.
    assert "font-size: 33px" in after, after[:2000]


@pytest.mark.allow_subprocess
def test_nothing_is_written_before_the_save_button(tmp_path):
    """Ein Regler, den jemand anfasst und wieder loslaesst, ist keine
    Bestellung.

    Ohne diese Zusicherung waere jede Bewegung ein atomares Schreiben
    der ganzen Datei UND eine Marke fuer die naechste Anmeldung - wer
    nur nachgesehen hat, wie es aussieht, haette danach eine
    Neuerzeugung bestellt.
    """
    run = run_settings(tmp_path, "scale:2.5")

    assert run.after("scale", "dirty") == "True", run.report
    assert run.after("scale", "save-sensitive") == "True", run.report
    assert run.after("scale", "marker") == "False", run.report
    assert run.settings == {}, run.report


@pytest.mark.allow_subprocess
def test_the_scale_moves_the_exceptions_without_pinning_them(tmp_path):
    """Der Fehler, den der Stillhalte-Schalter in app.py verhindert.

    Der Massstab schreibt die neuen Zahlen in die fuenf
    Ausnahmen-Zeilen, damit man sieht, was daraus wird. Loeste jede
    dieser Zuweisungen ihren eigenen Rueckruf aus, stuenden die fuenf
    danach FEST - und beim naechsten Ziehen bewegte sich keine mehr mit.
    """
    run = run_settings(tmp_path, "scale:1.0 scale:2.0")

    # 10 pt Grundwert, Faktor 2.0 -> 20; und weiterhin dem Faktor folgend.
    assert run.after("scale", "dial") != run.marks[0]
    later = [line for line in run.marks
             if line.startswith("dial:STYLE_TERMINAL_FONT_SIZE=")]
    assert later[-1] == "dial:STYLE_TERMINAL_FONT_SIZE=20:inherited", run.report
    assert "named" not in "\n".join(later), run.report


@pytest.mark.allow_subprocess
def test_an_exception_beats_the_scale_and_can_be_handed_back(tmp_path):
    """Die zweite Haelfte der Groessenseite.

    Eine genannte Zahl gilt genau so, wie sie dasteht - sie wird nicht
    noch mit dem Faktor multipliziert -, und der Weg zurueck fuehrt
    nicht durch das Editieren der JSON-Datei.
    """
    run = run_settings(tmp_path, "scale:2.0 dial:STYLE_BAR_THICKNESS=140 save")

    assert run.after("dial", "dial").startswith("STYLE_TERMINAL_FONT_SIZE")
    assert run.settings["sizes"]["values"]["STYLE_BAR_THICKNESS"] == "140"

    templates = _templates_naming("STYLE_BAR_THICKNESS")
    assert templates
    rendered = _render(tmp_path / "c", run.settings, templates)
    assert "140" in rendered, rendered[:2000]

    back = run_settings(
        tmp_path / "back",
        "dial-reset:STYLE_BAR_THICKNESS save",
        document={"sizes": {"scale": 2.0,
                            "values": {"STYLE_BAR_THICKNESS": "140"}}})
    assert back.settings["sizes"]["values"] == {}, back.report


@pytest.mark.allow_subprocess
def test_the_window_gap_keeps_the_equation_hyprland_needs(tmp_path):
    """"Ueberall derselbe Abstand" IST 2*gaps_in == gaps_out.

    Hyprland legt den inneren Abstand an JEDE Seite eines Fensters, den
    aeusseren nur nach aussen. Ein Regler, der nur einen der beiden
    Werte setzt, bricht genau die Zusicherung, fuer die es ihn gibt -
    und die alten Literale 5 und 20 erfuellten sie schon nicht.

    Seit dem 12.08.2026 ist die Gleichung KEINE Begleitzahl mehr,
    sondern eine Ableitung: STYLE_GAPS_OUT wird in src/sizes.py aus
    STYLE_GAPS_IN gerechnet. Der Grund steht dort - bei der neuen
    ausgelieferten Groesse rundete der eine Wert ab und der andere auf,
    und die Gleichung war genau bei der Vorgabe um einen Pixel
    gebrochen. Einstellbar ist deshalb nur noch der innere Abstand.
    """
    import sys

    sys.path.insert(0, str(SRC))
    try:
        import sizes
    finally:
        sys.path.remove(str(SRC))

    run = run_settings(tmp_path, "dial:STYLE_GAPS_IN=10 save")

    values = run.settings["sizes"]["values"]
    assert values["STYLE_GAPS_IN"] == "10", run.report
    assert "STYLE_GAPS_OUT" not in values, (
        "der aeussere Abstand wird wieder daneben geschrieben, statt "
        "abgeleitet zu werden: " + run.report)

    section = {"scale": 1.0, "values": values}
    assert sizes.value_of("STYLE_GAPS_OUT", section) == "20", run.report

    # Und ueber mehrere Skalenwerte, ohne dass jemand etwas einstellt:
    # das Runden darf die Gleichung an keiner Sprosse brechen.
    for scale in (1.0, 1.3, sizes.SCALE_DEFAULT, 2.0, 2.5):
        only_scale = {"scale": scale}
        inner = int(sizes.value_of("STYLE_GAPS_IN", only_scale))
        outer = int(sizes.value_of("STYLE_GAPS_OUT", only_scale))
        assert 2 * inner == outer, (
            f"bei sizes.scale {scale} sind es {2 * inner} px zwischen "
            f"zwei Fenstern und {outer} zum Rand")


# --------------------------------------------------------------------
# Die Farben
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_every_colour_zepos_has_is_on_the_page(tmp_path):
    """Alle neunundneunzig, und nicht die fuenfundneunzig von vorher.

    Der Stil-Editor im Schreibtisch zeigte vier davon nicht -
    background, overlay_accent_dim, vpn, vpn_connecting -, und sie waren
    damit nur ueber das Editieren der JSON-Datei erreichbar.
    """
    import sys

    sys.path.insert(0, str(SRC))
    try:
        import brand
    finally:
        sys.path.remove(str(SRC))

    run = run_settings(tmp_path, "colour:accent=#ff0000")
    assert run.mark("colours") == str(len(brand.COLORS)), run.report


@pytest.mark.allow_subprocess
def test_a_colour_reaches_the_file_and_the_generated_bytes(tmp_path):
    """overlay_bg, weil es die Flaeche jedes Ueberlagerungsfensters ist
    und ueber zwei Platzhalter ankommt - STYLE_COLOR_OVERLAY_BG im
    Stylesheet der Widgets und STYLE_GTK4_VIEW_BG in der gtk.css, die
    jede fremde GTK4-Anwendung liest.

    Dass ALLE siebzig ankommen, prueft
    tests/settings/test_settings_model.py::test_every_colour_the_application_
    offers_reaches_a_generated_file - hier geht es um die Kette vom
    Knopf bis dorthin.
    """
    run = run_settings(tmp_path, "colour:overlay_bg=#ff0000 save")

    assert run.settings["colors"]["overlay_bg"] == "#ff0000", run.report

    templates = _templates_naming("STYLE_COLOR_OVERLAY_BG")
    assert templates
    before = _render(tmp_path / "a", None, templates)
    after = _render(tmp_path / "b", run.settings, templates)
    assert after != before, (
        "eine Farbe wurde gespeichert und veraendert keine erzeugte Datei")
    assert "#ff0000" in after


@pytest.mark.allow_subprocess
def test_saving_one_colour_keeps_the_others(tmp_path):
    """settings.merge() ERSETZT einen Abschnitt.

    Nur die geaenderte Farbe zu schicken hiesse, jede andere zu
    loeschen, die schon in der Datei stand - genau der Fehler, den die
    beiden AGS-Dialoge einmal hatten, nur an einer anderen Stelle.
    """
    run = run_settings(
        tmp_path, "colour:accent=#ff0000 save",
        document={"colors": {"warning": "#123456"}})

    assert run.settings["colors"]["warning"] == "#123456", run.report
    assert run.settings["colors"]["accent"] == "#ff0000", run.report


@pytest.mark.allow_subprocess
def test_a_colour_can_be_put_back_without_editing_json(tmp_path):
    run = run_settings(
        tmp_path, "colour-reset:accent save",
        document={"colors": {"accent": "#ff0000"}})

    import sys

    sys.path.insert(0, str(SRC))
    try:
        import brand
    finally:
        sys.path.remove(str(SRC))

    assert run.settings["colors"]["accent"] == brand.COLORS["accent"], run.report


# --------------------------------------------------------------------
# Der Wetterort
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_weather_location_reaches_the_file_and_the_generated_bytes(
        tmp_path):
    """Der eine Wert, der etwas ueber diese Maschine an einen Dritten
    schickt - und bis heute nur auf der Kommandozeile zu setzen war."""
    run = run_settings(tmp_path, "weather:Bochum save")

    assert run.settings["weather"]["location"] == "Bochum", run.report

    templates = _templates_naming("STYLE_WEATHER_LOCATION")
    if not templates:
        pytest.skip("kein Platzhalter fuer den Wetterort in den Vorlagen")
    after = _render(tmp_path / "b", run.settings, templates)
    assert "Bochum" in after, after[:2000]


# --------------------------------------------------------------------
# Die Leiste und das Dock
# --------------------------------------------------------------------
#
# WAS HIER GEMESSEN WIRD UND WAS NICHT
#     Gemessen wird die ganze Strecke vom Knopf bis in die Datei: was
#     die Seite zeigt, was ein Klick daraus macht, und was danach in
#     user-settings.json steht. Das ist die Haelfte, die diese Dateien
#     besitzen.
#
#     NICHT gemessen wird, ob die erzeugte Bar.tsx sich danach bewegt.
#     Das haengt daran, dass STYLE_BAR_MODULES_LEFT und
#     STYLE_BAR_MODULES_RIGHT den Abschnitt "bar" lesen, und das ist die
#     andere Haelfte des Vertrags: beide Listen stehen seit dem
#     12.08.2026 in src/style_definition.py, die Vorlage traegt nur noch
#     die Platzhalter, und tests/src/test_style_definition.py misst
#     diese Haelfte. Ein Test, der sie hier vorwegnaehme, maesse eine
#     Erwartung.

# Der Abdruck, wie ihn package() von zepos-config hinterlegt. Kurz und
# nicht vollstaendig: was diese Pruefungen brauchen, ist eine
# Reihenfolge mit genug Eintraegen, um sie umzustellen - nicht die
# Leiste selbst.
#
# DIE LEEREN `label` SIND KEINE NACHLAESSIGKEIT, SONDERN DIE MESSUNG.
#     apps.imprint_pins() liest die Beschriftung aus den .desktop-Dateien
#     DIESES Baums, und darin liegt genau eine: die der
#     Einstellungs-Anwendung. Der Abdruck entsteht ausserdem in einem
#     Bau-Chroot, in dem GIO nichts beantworten kann. Ein Fixture mit
#     "Firefox" und "Dateien" darin maesse also eine Datei, die auf
#     keiner Installation so ankommt - und verdeckte damit die Frage,
#     ob die Seite einen leeren Namen anstaendig anzeigt.
#
#     `desktop` ist aus demselben Grund immer `<name>.desktop`: das ist,
#     was imprint_pins() schreibt, auch fuer nautilus, dessen Eintrag in
#     Wirklichkeit org.gnome.Nautilus.desktop heisst.
#
# "modules_available" IST SEIT DEM 12.08.2026 DABEI, und ohne den
# Schluessel maesse diese Datei etwas anderes, als sie soll: der Abdruck
# gilt dann als einer, der das MOEGLICHE nicht kennt, und die Seite
# bietet zu Recht gar nichts an. Genau dieser dritte Zustand wird unten
# in test_an_imprint_without_the_catalogue_offers_nothing eigens
# gemessen.
#
# Hier steht die Vereinigung der beiden Haelften - damit die
# Zusicherungen darunter unveraendert gelten, die von einer
# vollstaendig aufgestellten Leiste ausgehen.
SHIPPED_BAR = {
    "modules_left": ["custom/date", "custom/clocks", "hyprland/workspaces"],
    "modules_right": ["network", "battery", "tray"],
    "modules_available": ["custom/date", "custom/clocks",
                          "hyprland/workspaces", "network", "battery",
                          "tray"],
    "dock_pins": [
        {"name": "firefox", "desktop": "firefox.desktop", "label": ""},
        {"name": "nautilus", "desktop": "nautilus.desktop", "label": ""},
        {"name": "zepos-settings", "desktop": "zepos-settings.desktop",
         "label": "Systemeinstellungen"},
    ],
}

# Ein Anwendungseintrag, wie ihn eine Maschine traegt. Als Vorlage, weil
# die drei Zustaende, auf die es ankommt, sich nur in zwei Zeilen
# unterscheiden - und weil ein Eintrag ohne auffindbares Programm von GIO
# gar nicht erst ausgeliefert wird (gemessen, siehe der Kopf von
# ags-dock.template): das `Exec` zeigt deshalb auf einen Stellvertreter
# auf dem PATH des Laufs.
DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Name={label}
Exec={program}
Icon=application-x-executable
Terminal=false
NoDisplay={nodisplay}
"""


def desktop_entries(entries: dict[str, tuple[str, bool]]) -> dict[str, str]:
    """name -> (Beschriftung, NoDisplay) als Dateiinhalte."""
    return {f"{name}.desktop": DESKTOP_ENTRY.format(
        label=label, program=name, nodisplay="true" if hidden else "false")
        for name, (label, hidden) in entries.items()}


@pytest.mark.allow_subprocess
def test_the_bar_shows_what_is_shipped_when_nothing_is_configured(tmp_path):
    """Ohne eigene Einstellung steht da, was ZepOS ausliefert - und zwar
    aus dem Abdruck und nicht aus einer Liste in dieser Anwendung.

    Und die zwei Enden sind Enden: der Pfeil nach oben an der ersten
    Zeile und der nach unten an der letzten sind unanwaehlbar. Ein Knopf,
    hinter dem nichts passiert, ist genau der Fehler, gegen den diese
    Seite gebaut ist.
    """
    run = run_settings(tmp_path, "", shipped_bar=SHIPPED_BAR)

    assert run.mark("bar-note") == "-", run.report
    assert run.mark("bar-modules_right") == "network,battery,tray", run.report
    assert run.mark("bar-modules_left") == (
        "custom/date,custom/clocks,hyprland/workspaces"), run.report
    assert run.mark("bar-dock_pins") == (
        "firefox,nautilus,zepos-settings"), run.report

    # Nichts fehlt, also gibt es nichts hinzuzufuegen und nichts
    # zurueckzusetzen.
    assert run.mark("bar-missing-modules_right") == "", run.report
    assert run.mark("bar-add-modules_right") == "False", run.report
    assert run.mark("bar-reset-modules_right") == "False", run.report
    assert run.mark("bar-ends-modules_right") == "False,False", run.report

    assert run.settings == {}, run.report


@pytest.mark.allow_subprocess
def test_a_module_can_be_taken_off_and_put_back_without_editing_json(tmp_path):
    """Die Bedienung, die es bis zum 12.08.2026 ueberhaupt nicht gab.

    Entfernen, umsortieren, wieder hinzufuegen - alles ueber die
    Knoepfe der Zeilen, und danach steht die Reihenfolge in der Datei.
    """
    run = run_settings(
        tmp_path,
        "bar-remove:modules_right=battery "
        "bar-up:modules_right=tray "
        "bar-add:modules_right=battery save",
        shipped_bar=SHIPPED_BAR)

    assert run.after("bar-remove", "bar-modules_right") == "network,tray"
    # Nach dem Entfernen ist es das eine, was fehlt - und der Rueckweg
    # steht ab da bereit.
    assert run.after("bar-remove", "bar-missing-modules_right") == "battery"
    assert run.after("bar-remove", "bar-add-modules_right") == "True"

    assert run.after("bar-up", "bar-modules_right") == "tray,network"
    assert run.after("bar-add", "bar-modules_right") == "tray,network,battery"

    assert run.settings["bar"]["modules_right"] == [
        "tray", "network", "battery"], run.report
    # Die zwei Haelften, die niemand angefasst hat, bleiben auf "wie
    # ausgeliefert" stehen. Sie mitzuschreiben waere die eingefrorene
    # Liste, nur an einer Stelle, an der sie niemand bestellt hat.
    assert run.settings["bar"]["modules_left"] is None, run.report
    assert run.settings["bar"]["dock_pins"] is None, run.report


@pytest.mark.allow_subprocess
def test_resetting_writes_null_and_not_the_list_that_is_shown(tmp_path):
    """DIE PRUEFUNG, DERENTWEGEN "wie ausgeliefert" null IST.

    Ein Zuruecksetzen, das die gerade sichtbare Liste in die Datei
    schreibt, sieht am selben Tag richtig aus: dieselben Namen, dieselbe
    Reihenfolge. Es ist trotzdem falsch, und der Unterschied zeigt sich
    erst Wochen spaeter - beim naechsten Modul, das ZepOS ausliefert.
    Wer einmal zurueckgesetzt hat, saehe es nie, weil seine Liste es
    nicht nennt. Genau diese Kopie hat dieses Projekt an drei Stellen
    Catppuccin gekostet.

    Gemessen wird deshalb der WERT in der Datei und nicht, was die Seite
    danach zeigt: beides sieht gleich aus, und nur eines bleibt richtig.
    """
    run = run_settings(
        tmp_path,
        "bar-remove:modules_right=battery save bar-reset:modules_right save",
        shipped_bar=SHIPPED_BAR,
        document={"bar": {"modules_left": ["custom/date"]}})

    assert run.after("save", "bar-modules_right") == "network,tray"

    marks = run.marks
    assert marks.index("after-bar-reset:") > marks.index("after-save:")

    # Nach dem Zuruecksetzen steht die Auslieferung wieder da - und in
    # der Datei steht null, nicht diese drei Namen.
    assert run.after("bar-reset", "bar-modules_right") == (
        "network,battery,tray"), run.report
    assert run.after("bar-reset", "bar-reset-modules_right") == "False"

    assert run.settings["bar"]["modules_right"] is None, run.report
    # Und die Haelfte, die der Nutzer eingestellt hatte, ueberlebt das
    # Zuruecksetzen der anderen.
    assert run.settings["bar"]["modules_left"] == ["custom/date"], run.report


@pytest.mark.allow_subprocess
def test_trying_something_out_and_undoing_it_leaves_nothing_behind(tmp_path):
    """Herunternehmen und wieder aufstellen ist kein Einfrieren.

    Der Nutzer steht danach genau da, wo er angefangen hat. Schriebe das
    Fenster ihm dafuer die ganze Liste in die Datei, haette ein Versuch
    ohne Ergebnis seine Leiste festgenagelt - und das naechste Modul,
    das ZepOS ausliefert, erschiene bei ihm nie.
    """
    run = run_settings(
        tmp_path,
        "bar-remove:modules_right=battery bar-add:modules_right=battery save",
        shipped_bar=SHIPPED_BAR)

    assert run.after("bar-add", "bar-modules_right") == (
        "network,tray,battery"), run.report
    # Wieder heruntergenommen und ans Ende gestellt ist NICHT dasselbe
    # wie die Auslieferung - das ist der Fall, der gespeichert wird.
    assert run.settings["bar"]["modules_right"] == [
        "network", "tray", "battery"], run.report

    # Und derselbe Versuch mit dem LETZTEN Eintrag: heruntergenommen und
    # wieder aufgestellt landet er wieder am Ende, also steht Zeichen
    # fuer Zeichen die Auslieferung da - und dann steht in der Datei
    # null und nicht diese drei Namen.
    zurueck = run_settings(
        tmp_path / "zweiter",
        "bar-remove:modules_right=tray bar-add:modules_right=tray save",
        shipped_bar=SHIPPED_BAR)

    assert zurueck.after("bar-add", "bar-modules_right") == (
        "network,battery,tray"), zurueck.report
    assert zurueck.after("bar-add", "bar-reset-modules_right") == "False", (
        "die Seite behauptet, hier sei etwas eingestellt")
    assert zurueck.settings["bar"]["modules_right"] is None, zurueck.report


@pytest.mark.allow_subprocess
def test_a_module_that_no_longer_exists_is_reported_and_not_swallowed(
        tmp_path):
    """Ein Name ohne Zweig ist ein leerer Platz, und ein leerer Platz
    meldet sich nie.

    Er kommt nicht von Hand: er entsteht von selbst, sobald ein Modul
    umbenannt oder entfernt wird und in der Einstellungsdatei eines
    Nutzers noch dasteht. Die Seite laesst ihn weg - er wuerde sonst auf
    der Leiste fehlen, ohne dass jemand sagt, warum - und schreibt
    daneben, WAS sie weggelassen hat.
    """
    run = run_settings(
        tmp_path, "", shipped_bar=SHIPPED_BAR,
        document={"bar": {"modules_right": ["tray", "custom/gibtsnicht",
                                            "network", "tray"]}})

    assert run.mark("bar-modules_right") == "tray,network", run.report

    complaint = run.mark("bar-complaint-modules_right")
    assert "custom/gibtsnicht" in complaint, run.report
    assert settings_file.BAR_UNKNOWN in complaint, run.report
    # Und der zweite Grund, aus dem ein Eintrag wegfaellt: derselbe Name
    # zweimal waere dasselbe Modul zweimal auf derselben Leiste.
    assert settings_file.BAR_REPEATED in complaint, run.report


@pytest.mark.allow_subprocess
def test_a_module_zepos_does_not_place_can_still_be_switched_on(tmp_path):
    """DIE ZUSICHERUNG, OHNE DIE DER UMBAU VOM 12.08.2026 EIN LOESCHEN
    WAERE.

    Die ausgelieferte Leiste ist seit diesem Tag eine AUSWAHL: zehn
    Module haben ihren Zweig, ihr Skript und ihre Stilregeln und stehen
    trotzdem nicht darauf. Ob das ein Umraeumen oder ein Wegnehmen war,
    entscheidet genau diese Seite - kommt das Wetter hier zur Wahl, ist
    es umgeraeumt; kommt es nicht, ist es weg.

    GEMESSEN, dass es vorher NICHT ging: `missing` las bis dahin die
    ausgelieferte Haelfte, also bot die Seite nur an, was ZepOS ohnehin
    aufstellt. Ein Name, den die Vorgabe auslaesst, war damit weder
    hier noch ueber user-settings.json erreichbar - bar_order() verwarf
    ihn als "kennt diese Leiste nicht".
    """
    run = run_settings(
        tmp_path, "bar-add:modules_right=custom/weather save",
        shipped_bar={**SHIPPED_BAR,
                     "modules_available": [*SHIPPED_BAR["modules_available"],
                                           "custom/weather"]})

    assert run.mark("bar-missing-modules_right") == "custom/weather", run.report
    assert run.mark("bar-add-modules_right") == "True", run.report
    assert run.after("bar-add", "bar-modules_right") == (
        "network,battery,tray,custom/weather"), run.report
    assert run.settings["bar"]["modules_right"] == [
        "network", "battery", "tray", "custom/weather"], run.report


@pytest.mark.allow_subprocess
def test_an_imprint_without_the_catalogue_offers_nothing(tmp_path):
    """Der dritte Zustand: der Abdruck ist da und kennt das Moegliche
    nicht.

    Er entsteht auf einer Maschine, deren zepos-config aelter ist als
    dieser Schluessel. Dann ist das Moegliche UNBEKANNT und nicht LEER -
    dieselbe Unterscheidung wie beim ganzen Abdruck, und aus demselben
    Grund: gegen eine leere Liste geprueft waere jeder gespeicherte Name
    unbekannt, und der Nutzer verlaere seine Leiste an eine alte Datei.

    Also: die Reihenfolge steht da, es wird NICHTS verworfen, und
    angeboten wird nichts - mit dem Satz daneben, warum.
    """
    ohne = {key: value for key, value in SHIPPED_BAR.items()
            if key != "modules_available"}
    run = run_settings(
        tmp_path, "", shipped_bar=ohne,
        document={"bar": {"modules_right": ["tray", "custom/weather"]}})

    assert run.mark("bar-modules_right") == "tray,custom/weather", run.report
    # "-" ist der Strich, den das Kind fuer eine leere Marke schreibt.
    assert run.mark("bar-complaint-modules_right") == "-", run.report
    assert run.mark("bar-missing-modules_right") == "", run.report
    assert run.mark("bar-add-modules_right") == "False", run.report


@pytest.mark.allow_subprocess
def test_a_pin_the_dock_will_never_show_is_named_and_not_offered(tmp_path,
                                                                 bar_model):
    """DER FEHLER, DER DIESE GANZE AUFGABE AUSGELOEST HAT - hier in der
    Einstellungsseite.

    GEMESSEN am 12.08.2026: xdg-desktop-portal-gnome steht in der
    ausgelieferten Auswahl, traegt NoDisplay=true und ist ein D-Bus-
    Dienst ohne Fenster. Sein Eintrag hiess "Portal" und trug ein
    Zahnrad - das Symbol, das der Nutzer "garnicht oeffnen" konnte. Das
    Dock verwirft ihn seit demselben Tag.

    Eine Einstellungsseite, die ihn trotzdem zum Anheften anbietet,
    baute denselben toten Knopf noch einmal, nur mit einem Umweg. Also:
    angezeigt und BENANNT, solange er in der Liste steht - der Nutzer
    sieht sonst ein Symbol weniger, als hier Zeilen stehen -, und nie
    zur Wahl gestellt.

    Gefragt wird dieselbe Quelle, aus der das Dock es liest: der
    Anwendungseintrag dieser Maschine, ueber GIO. Nicht der Abdruck -
    der entsteht in einem Bau-Chroot, in dem GIO nichts beantworten
    kann.
    """
    run = run_settings(
        tmp_path, "bar-remove:dock_pins=portal-dienst",
        shipped_bar={**SHIPPED_BAR, "dock_pins": [
            *SHIPPED_BAR["dock_pins"],
            {"name": "portal-dienst", "desktop": "portal-dienst.desktop",
             "label": ""},
            # Weder ein Eintrag auf dieser Maschine noch eine
            # Beschriftung im Abdruck: der letzte Rueckfall, und der
            # einzige, bei dem eine leere Zeile entstuende.
            {"name": "nicht-installiert",
             "desktop": "nicht-installiert.desktop", "label": ""},
        ]},
        applications=desktop_entries({
            "firefox": ("Firefox", False),
            "nautilus": ("Dateien", False),
            "portal-dienst": ("Portal", True),
        }),
        stubs={"firefox": "#!/bin/sh\n", "nautilus": "#!/bin/sh\n",
               "portal-dienst": "#!/bin/sh\n"})

    marks = run.marks
    assert "bar-dock:firefox=Firefox|" in marks, run.report
    assert (f"bar-dock:portal-dienst=Portal|{bar_model.DOCK_SERVICE}"
            in marks), run.report

    # SOLANGE ER IN DER LISTE STEHT, STEHT DER GRUND AN SEINER ZEILE.
    # Ohne ihn zeigte diese Seite eine Zeile mehr, als der Fuss Symbole
    # hat, und niemand koennte sagen, welche fehlt.
    before = run.mark("bar-sub-dock_pins").split("|")
    assert f"portal-dienst=portal-dienst - {bar_model.DOCK_SERVICE}" in before, (
        run.report)

    # UND WENN ER EINMAL HERUNTERGENOMMEN IST, KOMMT ER NICHT ZURUECK.
    # Nicht, weil er vergessen wird, sondern weil er nie ankaeme - und
    # die Zeile darunter sagt genau das.
    assert run.after("bar-remove", "bar-missing-dock_pins") == "", run.report
    assert run.after("bar-remove", "bar-add-dock_pins") == "False", run.report
    offer = run.after("bar-remove", "bar-offer-dock_pins")
    assert "portal-dienst" in offer and "NoDisplay" in offer, offer

    # DIE BESCHRIFTUNGEN, UND DASS KEINE ZEILE LEER BLEIBT.
    #
    # Der Abdruck traegt fuer fremde Anwendungen ein LEERES label - er
    # entsteht in einem Bau-Chroot ohne GIO. Die Beschriftung kommt
    # deshalb aus dem Eintrag DIESER Maschine ("Dateien"), und wo es
    # den nicht gibt, aus dem Abdruck ("Systemeinstellungen"); bleibt
    # auch der leer, steht der Paketname da. Keiner der drei Faelle darf
    # eine leere Zeile ergeben.
    titles = run.mark("bar-title-dock_pins").split("|")
    assert "firefox=Firefox" in titles, run.report
    assert "nautilus=Dateien" in titles, run.report
    assert "zepos-settings=Systemeinstellungen" in titles, run.report
    assert "portal-dienst=Portal" in titles, run.report
    assert "nicht-installiert=nicht-installiert" in titles, run.report
    assert all(pair.split("=", 1)[1] for pair in titles), titles

    # Und der dritte Zustand steht ebenfalls an seiner Zeile: das
    # Programm gibt es auf dieser Maschine nicht.
    assert (f"nicht-installiert=nicht-installiert - "
            f"{bar_model.DOCK_NO_ENTRY}") in before, run.report

    # zepos-settings hat auf dieser "Maschine" keinen Anwendungseintrag,
    # heftet das Dock also nicht an - auch das steht an seiner Zeile.
    assert "bar-dock:zepos-settings=|" + bar_model.DOCK_NO_ENTRY in marks, (
        run.report)


@pytest.mark.allow_subprocess
def test_without_the_imprint_the_page_says_so_instead_of_showing_nothing(
        tmp_path):
    """Die dritte Lage, die es wirklich gibt: kein Abdruck.

    Ein frischer Checkout, ein Paket, das aelter ist als diese Seite.
    Ohne diese Unterscheidung zeigte die Seite drei leere Gruppen - also
    die Behauptung, diese Leiste habe keine Module -, und ein
    Zuruecksetzen waere der einzige Knopf, der noch etwas tut.

    Was der Nutzer gespeichert hat, steht trotzdem da: gegen einen
    fehlenden Abdruck geprueft waere JEDER Name unbekannt, und die
    Anwendung wuerfe eine Leiste weg, weil ihr eine Datei fehlt.
    """
    run = run_settings(
        tmp_path, "",
        document={"bar": {"modules_right": ["tray", "network"]}})

    note = run.mark("bar-note")
    assert settings_file.SHIPPED_BAR in note, run.report

    assert run.mark("bar-modules_right") == "tray,network", run.report
    assert run.mark("bar-complaint-modules_right") == "-", run.report
    assert run.mark("bar-add-modules_right") == "False", run.report
    # Der Rueckweg bleibt: er braucht den Abdruck nicht, er streicht nur
    # den eigenen Eintrag.
    assert run.mark("bar-reset-modules_right") == "True", run.report
    assert run.mark("bar-reset-modules_left") == "False", run.report


# --------------------------------------------------------------------
# Die Aktualisierung - die Einstellung, die der Maschine gehoert
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_an_update_switch_rewrites_the_timer_dropin(tmp_path):
    """Hier ist die erzeugte Datei kein Stylesheet, sondern die
    systemd-Ergaenzung - und sie wird SOFORT geschrieben, ohne
    Speichern-Knopf.

    Das ist kein Widerspruch zur Groessenseite: diese Einstellung geht
    an systemd und nicht an den Generator, also beendet sie nichts und
    startet nichts neu. Was sie kostet, ist ein daemon-reload.
    """
    dropin = (tmp_path / "etc" / "systemd" / "system"
              / "zepos-update.timer.d" / "10-zepos.conf")

    run = run_settings(tmp_path, "update:enabled=false")

    assert dropin.is_file(), run.report
    written = json.loads(
        (tmp_path / "etc-zepos" / "update.json").read_text(encoding="utf-8"))
    assert written["enabled"] is False, run.report
    assert "systemctl disable zepos-update.timer" in run.trace, run.report

    # Und die Gegenprobe: mit `enabled` an sieht die Ergaenzung anders
    # aus. Ohne sie waere "die Datei ist da" auch dann wahr, wenn sie
    # immer dieselbe ist.
    other = run_settings(tmp_path / "an", "update:notify=never")
    assert "systemctl enable zepos-update.timer" in other.trace, other.report


@pytest.mark.allow_subprocess
def test_the_interval_reaches_the_dropin(tmp_path):
    dropin = (tmp_path / "etc" / "systemd" / "system"
              / "zepos-update.timer.d" / "10-zepos.conf")

    run = run_settings(tmp_path, "update:schedule.interval=weekly")

    assert "OnCalendar=weekly" in dropin.read_text(encoding="utf-8"), run.report


@pytest.mark.allow_subprocess
def test_a_value_the_page_does_not_offer_is_shown_and_not_overwritten(
        tmp_path):
    """`zepos-settings set update.schedule.interval 6h` ist erlaubt, und
    diese Seite bietet nur drei Kalenderworte an.

    Eine Auswahl, die beim blossen Oeffnen des Fensters etwas anderes
    einstellt, waere kein Anzeigen, sondern eine Aenderung, die niemand
    vorgenommen hat.
    """
    run = run_settings(tmp_path, "scale:2.0",
                       update_config={"schedule": {"interval": "6h"}})

    # Die Datei allein genuegt als Beweis NICHT, und das ist gemessen:
    # ein Fenster, das den unbekannten Wert durch "daily" ersetzt,
    # schreibt erst, wenn jemand die Auswahl anfasst - bis dahin steht
    # in der Datei weiter "6h" und alles sieht richtig aus. Also wird
    # gefragt, was die ZEILE zeigt.
    assert "choice:schedule.interval=6h|6h,daily,weekly,monthly" in run.marks, (
        run.report)

    stored = json.loads(
        (tmp_path / "etc-zepos" / "update.json").read_text(encoding="utf-8"))
    assert stored["schedule"]["interval"] == "6h", run.report


# --------------------------------------------------------------------
# Was nach dem Speichern passiert
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_saving_asks_the_next_login_to_regenerate(tmp_path):
    """Der Teil, ohne den "wirksam beim naechsten Anmelden" eine
    Behauptung waere.

    Nichts erzeugt von selbst neu: zepos-session tut es bei der ERSTEN
    Anmeldung und nach einer Paketaktualisierung, und eine geaenderte
    Einstellung ist keins von beidem. Ohne diese Marke waere die
    Anwendung eine Oberflaeche, die speichert und deren Ergebnis nie
    ankommt.
    """
    run = run_settings(tmp_path, "scale:2.0 save")

    marker = tmp_path / "state" / "zepos" / "regenerate-required"
    assert marker.exists(), run.report
    assert run.after("save", "marker") == "True", run.report
    assert "next login" in run.after("save", "banner"), run.report


@pytest.mark.allow_subprocess
def test_applying_now_runs_the_generator_and_drops_the_request(tmp_path):
    """"Jetzt anwenden" ist der Weg fuer den, der nicht warten will -
    und danach gibt es nichts mehr nachzuholen."""
    run = run_settings(tmp_path, "scale:2.0 save apply")

    # mark() und nicht after(): der Befehl faellt WAEHREND der
    # Anweisung, also vor der Marke, die den Zustand danach beschreibt.
    assert run.mark("cmd") == "zepos-generate --all", run.report
    assert run.after("apply", "marker") == "False", run.report
    assert run.after("apply", "banner").endswith("Applied."), run.report
    marker = tmp_path / "state" / "zepos" / "regenerate-required"
    assert not marker.exists(), run.report


@pytest.mark.allow_subprocess
def test_a_failed_generator_keeps_the_request_for_the_next_login(tmp_path):
    """Ein fehlgeschlagener Lauf hat nichts erzeugt.

    Die Marke faellt deshalb nur bei 0. Sonst waere die Aenderung
    gespeichert, nicht angewendet und auch nicht mehr vorgemerkt - also
    verloren, ohne dass irgendwo etwas fehlt.
    """
    run = run_settings(tmp_path, "scale:2.0 save apply",
                       extra=["fail-generator"])

    assert run.after("apply", "marker") == "True", run.report
    assert run.mark("apply-rc") == "1", run.report
    marker = tmp_path / "state" / "zepos" / "regenerate-required"
    assert marker.exists(), run.report


@pytest.mark.allow_subprocess
def test_the_cost_of_applying_is_said_before_it_is_paid(tmp_path):
    """Der Knopf im Banner oeffnet einen Dialog und nicht den Generator.

    Was dort steht, ist gemessen und nicht beschwichtigt: der Lauf
    beendet AGS und startet es neu, also sind Leiste, Dock und jedes
    Ueberlagerungsfenster fuer Sekunden weg.
    """
    run = run_settings(tmp_path, "scale:2.0 save ask")

    # Der Dialog laeuft, der Generator nicht.
    assert "cmd:zepos-generate" not in run.trace, run.report


# --------------------------------------------------------------------
# Das Toolkit, gemessen statt behauptet
# --------------------------------------------------------------------

_TOOLKIT_PROBE = r"""
import re, sys
import zepos_settings_gui.app
mapped = sorted({m.group(0) for line in open("/proc/self/maps")
                 for m in [re.search(r"/usr/lib/lib(gtk|adwaita)[^\s]*", line)] if m})
print("\n".join(mapped))
"""


@pytest.mark.allow_subprocess
def test_the_application_maps_gtk4_and_no_gtk3(tmp_path):
    """Die Entscheidung vom 11.08.2026 gilt fuer jede Oberflaeche, die
    ZepOS selbst baut - und ein Python-Programm hat kein Objekt, an dem
    `readelf -d` sie nachpruefen koennte. Was es hat, sind die
    gi.require_version-Zeilen, und was daraus wirklich geladen wird,
    steht in /proc/self/maps."""
    interpreter = _interpreter()
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4/Adw laden")
    executable, extra_path = interpreter

    result = subprocess.run(
        [executable, "-c", _TOOLKIT_PROBE],
        env={"PATH": "", "HOME": str(tmp_path),
             "PYTHONPATH": os.pathsep.join(
                 [str(SETTINGS_ROOT), str(SRC), *extra_path])},
        capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    mapped = result.stdout.split()
    assert any("libgtk-4.so" in name for name in mapped), (
        "die Einstellungs-Anwendung bildet kein GTK4 ab:\n" + result.stdout)
    assert any("libadwaita" in name for name in mapped), (
        "sie bildet libadwaita nicht ab, obwohl jede Zeile darin eine "
        "Adw.PreferencesRow ist:\n" + result.stdout)
    assert not any("libgtk-3.so" in name for name in mapped), (
        "sie bildet GTK3 ab. ZepOS ist GTK4:\n" + result.stdout)


@pytest.mark.allow_subprocess
def test_importing_the_window_says_nothing_on_stderr(tmp_path):
    """Ein sauberer Import.

    Gemessen an zepos-menu und dort begruendet: ein `import Gdk` ohne
    gi.require_version schreibt bei jedem Start eine PyGIWarning, und
    welche Fassung hereinkommt, entscheidet dann die Reihenfolge der
    Importe.
    """
    interpreter = _interpreter()
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4/Adw laden")
    executable, extra_path = interpreter

    result = subprocess.run(
        [executable, "-c", "import zepos_settings_gui.app"],
        env={"PATH": "", "HOME": str(tmp_path),
             "PYTHONPATH": os.pathsep.join(
                 [str(SETTINGS_ROOT), str(SRC), *extra_path])},
        capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == "", (
        "der blosse Import schreibt auf stderr:\n" + result.stderr)


@pytest.mark.allow_subprocess
def test_the_command_finds_both_of_its_directories(tmp_path):
    """settings/bin/zepos-settings-gui, so wie das Paket sie nach
    /usr/bin legt.

    Sie ist die einzige Datei, die kein anderer Test anfasst, und sie
    hat zwei Aufgaben: das Modulverzeichnis UND /usr/share/zepos vor dem
    ersten Import auf den Suchpfad legen. Faellt eine davon aus, ist die
    Meldung ein ModuleNotFoundError auf einem Eintrag im Starter, der
    nichts tut.

    Gefahren wird mit einem Schalter, den es nicht gibt: damit endet
    main() vor dem Fenster, und der Lauf braucht keine Anzeige. Bewiesen
    ist trotzdem die ganze Kette.
    """
    interpreter = _interpreter()
    if interpreter is None:
        pytest.skip("kein Interpreter hier kann gi/Gtk4/Adw laden")
    executable, extra_path = interpreter
    command = SETTINGS_ROOT / "bin" / "zepos-settings-gui"

    assert os.access(command, os.X_OK), (
        f"{command} ist nicht ausfuehrbar; das Paket installiert sie mit 0755")

    result = subprocess.run(
        [executable, str(command), "--was-auch-immer"],
        env={"PATH": "", "HOME": str(tmp_path),
             "XDG_CONFIG_HOME": str(tmp_path / "config"),
             # NICHT auf settings/ oder src/ zeigend: der Befehl muss
             # sich beide Verzeichnisse selbst hinlegen, und genau das
             # wird gemessen.
             "PYTHONPATH": os.pathsep.join(extra_path)},
        capture_output=True, text=True, timeout=120)

    assert "ModuleNotFoundError" not in result.stderr, (
        "der Befehl findet seine Verzeichnisse nicht:\n" + result.stderr)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--was-auch-immer" in result.stderr, result.stdout + result.stderr
