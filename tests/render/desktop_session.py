# SPDX-License-Identifier: GPL-3.0-or-later
"""Die erzeugte Oberflaeche, in einem eigenen Compositor, als Bilddatei.

WARUM ES DIESE DATEI GIBT
    Niemand hat die Leiste dieses Projekts jemals ANGESEHEN.
    tests/src/bar_headless_child.tsx baut sie kopflos und misst
    window.get_allocated_width() - es entsteht kein Bild. Jede Aussage
    ueber ihr AUSSEHEN war damit Arithmetik ueber Pixelzahlen: "1609 px
    passen auf 1920" ist wahr und sagt nichts darueber, ob die Symbole
    einander beruehren, ob der linke Rand so breit ist wie der rechte
    oder ob das Glas ueberhaupt durchscheint.

    Hier steht der Weg von der erzeugten Konfiguration zu einer PNG-Datei.

WARUM EIN VERSCHACHTELTER COMPOSITOR UND NICHT EIN Gsk-RENDERER
    Gtk.WidgetPaintable + Gsk.CairoRenderer zeichnet einen Widgetbaum in
    eine Textur. Das geht ohne Compositor und laesst genau das weg,
    worueber der Nutzer sich beklagt hat:

      * die Layer-Shell-Platzierung. Ob die Leiste oben buendig sitzt und
        das Dock unten denselben Randabstand hat, entscheidet der
        Compositor aus Anker, exklusiver Zone und Aussenrand - nicht das
        Widget.
      * die Unschaerfe. `layerrule = blur` ist eine Regel des
        Compositors. Ein Gsk-Bild zeigt die halbdurchsichtige Flaeche vor
        NICHTS, und halbdurchsichtig vor nichts ist einfach dunkel.
      * der Hintergrund. Ohne Tapete dahinter beweist ein Bild ueber
        Glasmorphismus gar nichts.

    Deshalb faehrt hier ein echtes Hyprland mit den echten Glasregeln aus
    src/style_definition.py, mit der ausgelieferten Tapete dahinter, und
    das Bild nimmt grim ueber wlr-screencopy.

DIE SICHERHEITSHALBE, und sie ist von tests/lock/nested_compositor.py
geliehen statt nachgebaut
    Ein zweites Hyprland auf der Sitzung des Nutzers waere ein zweites
    Hyprland auf der Sitzung des Nutzers. refuse_the_real_session()
    prueft vor JEDEM Kindprozess, dass XDG_RUNTIME_DIR und
    WAYLAND_DISPLAY woanders hinzeigen als die des Menschen, der das hier
    gestartet hat. Diese Datei importiert die Funktion, statt sie
    abzuschreiben: eine Kopie einer Sicherung ist eine Sicherung, die
    auseinanderlaufen kann.

WAS NICHT AUSGEFUEHRT WIRD
    src/generate_config.sh. Der Generator beendet am Ende eines Laufs die
    laufende Oberflaeche - `ags quit`, `pkill -f "gjs.*ags"`, `pkill -x
    waybar` - und trifft damit die Prozesse des Nutzers, egal welches
    HOME er bekommt. Die Vorlagen werden hier deshalb ueber
    src/template_processor.py direkt verarbeitet, genau wie
    tests/src/test_bar_headless.py es tut.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

sys.path.insert(0, str(ROOT))
from tests.lock.nested_compositor import (      # noqa: E402
    SUN_PATH_MAX, host_wayland_socket, missing_tools, refuse_the_real_session,
)
from installer.gui.pages import LANGUAGE_DEFAULTS  # noqa: E402

# Die Sprache der Sitzung - geholt aus der Tabelle, die der Assistent auf
# die Platte schreibt, und nicht danebengeschrieben.
#
# ZEPOS_RENDER_LANG waehlt eine der beiden, die der Assistent anbietet.
# Ohne Angabe bleibt es Deutsch: das ist die Sprache, in der die Bilder
# dieses Projekts seit jeher entstehen, und ein Schalter, der die Vorgabe
# aendert, aendert stillschweigend jeden Abzug.
#
# WOFUER ES DA IST (17.08.2026)
#     Seit die Oberflaeche uebersetzt ist, ist "die Beschriftungen sind
#     uebersetzbar" eine Behauptung, die man SEHEN koennen muss. Zwei
#     Laeufe mit demselben Baum und verschiedenem ZEPOS_RENDER_LANG
#     geben zwei Bildersaetze, und der Unterschied zwischen ihnen ist
#     der Beweis - oder er fehlt, und dann fehlt auch die Uebersetzung.
_RENDER_LANG = os.environ.get("ZEPOS_RENDER_LANG", "de")
if _RENDER_LANG not in LANGUAGE_DEFAULTS:
    raise SystemExit(
        f"ZEPOS_RENDER_LANG={_RENDER_LANG!r} - der Assistent kennt nur "
        + " und ".join(sorted(LANGUAGE_DEFAULTS)))
SESSION_LOCALE = f"{LANGUAGE_DEFAULTS[_RENDER_LANG][1]}.UTF-8"


def locale_is_generated(name: str) -> bool:
    """Ist diese Sprache auf DIESER Maschine ueberhaupt erzeugt?

    Eine Sprache, die `locale-gen` nie gesehen hat, ist kein Fehler, den
    ein Programm meldet: die C-Bibliothek faellt still auf C zurueck. Das
    Bild sieht dann englisch aus, und niemand weiss, ob das die Oberflaeche
    ist oder die Maschine. Genau diese Verwechslung hat am 12.08.2026
    einen Mangel in einen Bericht geschrieben, den es nicht gab - also
    wird gefragt, statt es zu hoffen.
    """
    try:
        vorhanden = subprocess.run(["locale", "-a"], capture_output=True,
                                   text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return False
    # `locale -a` schreibt "de_DE.utf8", die Umgebungsvariable will
    # "de_DE.UTF-8" - dieselbe Sprache, zwei Schreibweisen.
    gesucht = name.lower().replace("-", "")
    return any(eintrag.lower().replace("-", "") == gesucht
               for eintrag in vorhanden)

# Die ausgelieferte Tapete. Sie steht hinter dem Glas, und ohne sie
# waere jede Aussage ueber Durchsicht unbelegt.
WALLPAPER = SRC / "branding" / "zepos-wallpaper.png"

# Was aus welcher Vorlage wird. Die Liste ist aus den case-Zweigen von
# src/generate_config.sh abgelesen, nicht geraten - dort steht je Ziel
# CONFIG_DIR und CONFIG_FILE.
#
# SIE IST EINMAL ABGELESEN WORDEN UND DANN AUSEINANDERGELAUFEN
#     GEMESSEN am 19.08.2026: `templates/ags-kit.template` fehlte hier.
#     Das Bauteil-Kit ist am 18.08.2026 entstanden, generate_config.sh
#     bekam seinen Zweig (Zeile 744, kit.ts), diese Tabelle nicht - und
#     weil sie eine HANDGEPFLEGTE ABSCHRIFT ist, hat es niemand gemerkt.
#
#     Der Preis: seit dem Tag konnte KEIN EINZIGER Render-Test mehr eine
#     Sitzung bauen. Die erzeugten Fenster importieren "../utils/kit",
#     die Datei entstand hier nie, und esbuild brach mit "Could not
#     resolve" ab - 15 Fehler, bevor der erste Bildpunkt gemessen war.
#     Am echten System war nie etwas kaputt; kaputt war die Abschrift.
#
#     Dagegen steht seit dem 19.08.2026
#     tests/src/test_render_table.py: er haelt diese Tabelle gegen die
#     case-Zweige und wird rot, sobald ein Ziel dazukommt, das hier
#     fehlt. Ein Waechter im SICHEREN Lauf, damit die Luecke auffaellt,
#     ohne dass jemand einen Compositor starten muss.
RENDERED = {
    "templates/ags-i18n.template": "utils/i18n.ts",
    "templates/ags-kit.template": "utils/kit.ts",
    "templates/ags-overlay-utils.template": "utils/overlay.ts",
    "templates/ags-hyprland.template": "utils/hyprland.ts",
    "templates/ags-tray.template": "utils/tray.ts",
    "templates/ags-bar.template": "widget/Bar.tsx",
    "templates/ags-dock.template": "widget/Dock.tsx",
    "templates/ags-power-button.template": "widget/PowerButton.tsx",
    "templates/ags-calendar.template": "widget/Calendar.tsx",
    "templates/ags-shortcuts.template": "widget/Shortcuts.tsx",
    "templates/ags-battery.template": "widget/Battery.tsx",
    "templates/ags-disk.template": "widget/DiskUsage.tsx",
    "templates/ags-control-center.template": "widget/ControlCenter.tsx",
    "templates/ags-network.template": "widget/NetworkManager.tsx",
    "templates/ags-bluetooth.template": "widget/BluetoothManager.tsx",
    "templates/ags-wallpaper.template": "widget/WallpaperSelector.tsx",
    "templates/ags-style-editor.template": "widget/StyleEditor.tsx",
    "templates/ags-vpn.template": "widget/VpnManager.tsx",
    "templates/ags-vpn-settings.template": "widget/VpnSettings.tsx",
    "templates/ags-notifications.template": "widget/Notifications.tsx",
    "templates/ags-logout.template": "widget/Logout.tsx",
    "templates/ags-config.template": "app.ts",
    "templates/ags-style.template": "style.scss",
    "styles/bar-style.template": "bar.css",
}

def _icon(name: str) -> str:
    """Ein Zeichen aus src/icons_db.py - der Quelle, aus der die Skripte
    es auch bekommen.

    NICHT abgeschrieben, und das ist der Unterschied, der dieses Bild von
    einer Zeichnung trennt. Was die Vorlagen als `{{ICON_KEYBOARD}}`
    schreiben, loest der Generator aus dieser Tabelle auf; ein
    handgetipptes Zeichen hier waere ein Zeichen, das mit dem der
    Installation nichts zu tun haette.
    """
    sys.path.insert(0, str(SRC))
    try:
        import icons_db
        glyph = icons_db.ALL_ICONS.get(name)
        assert glyph, f"{name} steht nicht in icons_db.py"
        return glyph
    finally:
        sys.path.remove(str(SRC))


def module_payloads() -> tuple[dict[str, str], dict[str, str]]:
    """Was die zwoelf Skriptmodule auf einem Notebook sagen.

    ATTRAPPEN UND NICHT DIE ECHTEN SKRIPTE, UND DAS IST EINE ENTSCHEIDUNG
        Die echten fragen wttr.in, den NetworkManager, den Akku und den
        Compositor. Auf DIESER Maschine - einer VM ohne Akku, ohne
        Bluetooth-Adapter und ohne konfigurierten Ort - schweigen vier
        davon, und ein schweigendes Modul hat unter GTK4 die Breite null.
        Das Bild zeigte dann eine Leiste mit vier Modulen weniger als die
        auf dem Schirm eines Notebooks - also nicht die Leiste, um die es
        geht.

    DIE FORM JEDER ZEILE STEHT IN IHRER EIGENEN VORLAGE, und sie wurde
    dort abgelesen und nicht erfunden:

        date.sh          date-config.template:  "{{ICON_CALENDAR}}  %a
                         %d.%m.%Y  %H:%M"
        hypr-shortcuts   hypr-shortcuts-config.template:187
                         f"{{ICON_KEYBOARD}}  {gesamt}"
        helpers-bar      helpers-bar.template:156
                         f"{{ICON_CODE}}  {count}"
        hardware-monitor hardware-monitor-config.template: seit dem
                         13.08.2026 Prozessorlast und Arbeitsspeicher
                         aus /proc, also "{{ICON_CPU}} 12%
                         {{ICON_RAM}} 38%". Hier stand bis dahin
                         "{{ICON_MOTHERBOARD}} No HW" - der Rueckfall
                         der alten Fassung, die ausschliesslich nach
                         Wasserkuehlung, Grafikkarte und RGB fragte und
                         auf einem Notebook deshalb nie etwas fand.
                         Dieselbe Zeile steht in FIT_MODULES
                         (tests/src/test_bar_headless.py); zwei
                         Nachstellungen desselben Skripts, die
                         Verschiedenes sagen, messen zwei Leisten.
        status.sh        bar-status-config.template: seit dem
                         12.08.2026 NUR das Zeichen, und das Zeichen
                         traegt die Stufe: fuenf Akkustaende, drei
                         Lautstaerken, vier Feldstaerken. Die
                         Prozentzahl steht im Tooltip ("Symbol allein,
                         Zahl im Tooltip - so macht es macOS").

                         DER AKKU IST SEIT DEM 13.08.2026 AUSGENOMMEN
                         und traegt Zeichen UND Zahl - bestellt an dem
                         Tag: "ich will auch eine prozentzahl haben fuer
                         die batterie nicht nur ein symbol". Die
                         Begruendung, warum bei ihm und nicht bei Ton
                         und Mikrofon, steht im Kopf der Vorlage.

    WORIN DAS VON tests/src/test_bar_headless.py ABWEICHT, UND WARUM DAS
    EIN BEFUND IST
        Die Tabellen FIT_MODULES/FIT_STATUS dort tragen KEIN Zeichen -
        jeder Eintrag beginnt mit einem blanken Leerzeichen, wo die
        Vorlage ein Nerd-Font-Zeichen setzt. Die Breitenmessung der Suite
        rechnet damit je sprechendem Modul ein Zeichen zu wenig. Hier
        stehen die Zeichen, weil ein Bild ohne sie eine Leiste zeigte,
        die es nicht gibt.

    Leer bleiben sechs, die auf einer frischen und ruhigen Installation
    wirklich schweigen, und jede aus einem Grund, der in ihrer Vorlage
    steht: clocks.sh ohne zweite Zeitzone, weather.sh ohne Ort,
    floating-layouts ohne gespeicherte Anordnung - und die drei
    bedingten (media, updates, privacy), solange nichts spielt, nichts
    ansteht und niemand zuhoert.
    """
    modules = {
        "date.sh": f"{_icon('ICON_CALENDAR')}  Di 12.08.2026  14:07",
        "clocks.sh": "",
        "weather.sh": "",
        "hypr-shortcuts.py": f"{_icon('ICON_KEYBOARD')}  66",
        "floating-layouts-bar.sh": "",
        "helpers-bar.py": f"{_icon('ICON_CODE')}  8",
        "hardware-monitor.py": (f"{_icon('ICON_CPU')} 12% "
                                f"{_icon('ICON_RAM')} 38%"),
        # Die drei BEDINGTEN, im RUHEZUSTAND - und sie fehlten hier bis
        # zum 12.08.2026 ganz. Ohne ihre Attrappe rief die Leiste drei
        # Skripte, die es im Bauplatz nicht gibt, und schrieb bei jedem
        # Takt drei "Datei oder Verzeichnis nicht gefunden" ins
        # Protokoll - alle zwei Sekunden, waehrend das Bild entsteht.
        # Ein Protokoll, in dem staendig etwas Rotes steht, ist eines,
        # in dem niemand mehr das Echte findet.
        #
        # Leer und nicht sprechend: ein Rechner, auf dem gerade nichts
        # spielt, nichts ansteht und niemand zuhoert, ist der Normalfall -
        # und die drei zeigen dann nichts, weil sie genau dafuer gebaut
        # sind.
        "media.sh": "",
        "updates.sh": "",
        "privacy.sh": "",
    }
    status = {
        "audio": _icon("ICON_VOLUME_HIGH"),
        "microphone": _icon("ICON_MIC"),
        # Zeichen UND Zahl, seit dem 13.08.2026 - siehe oben. 87 % ist
        # nach der Staffelung in bar-status-config.template genau
        # ICON_BATTERY_HIGH, also dasselbe Zeichen wie vorher.
        "battery": f"{_icon('ICON_BATTERY_HIGH')} 87%",
        # Die dritte von vier Feldstaerken - 72 % waeren nach der
        # Staffelung in bar-status-config.template genau diese.
        "network": _icon("ICON_WIFI_3"),
        # Adapter an, nichts verbunden - der Zustand eines frisch
        # angemeldeten Notebooks. bar-status-config.template gibt dann
        # das blanke Zeichen ohne Zahl aus.
        "bluetooth": _icon("ICON_BLUETOOTH"),
    }
    return modules, status

# Zehn Arbeitsbereiche, wie sie auf dem Abnahmebild des 11.08.2026
# stehen. Sie sind der breiteste Posten der Leiste.
WORKSPACES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def _processor(scale: float | None = None, home: Path | None = None):
    """src/template_processor.py, so importiert, wie der Generator es tut.

    `scale` ist der Groessenregler (sizes.scale), unter dem die Vorlagen
    erzeugt werden. None heisst: der ausgelieferte.

    WARUM DAFUER EIN ZWEITER IMPORT NOETIG IST
        style_definition.py liest die Einstellungsdatei BEIM IMPORT und
        legt STYLE_VARIABLES dabei fest. Einen anderen Faktor bekommt man
        deshalb nur, indem die Datei mit einer anderen Wurzel noch einmal
        geladen wird - genau wie tests/src/test_bar_headless.py es tut,
        und aus demselben Grund.
    """
    sys.path.insert(0, str(SRC))
    try:
        import template_processor
        if scale is None:
            return template_processor.ConfigProcessor()

        assert home is not None, "ein Faktor braucht ein Verzeichnis dafuer"
        home.mkdir(parents=True, exist_ok=True)
        (home / "user-settings.json").write_text(
            json.dumps({"schema_version": 1, "sizes": {"scale": scale}}),
            encoding="utf-8")
        previous = {name: os.environ.get(name) for name in
                    ("ZEPOS_SYSTEM_ROOT", "ZEPOS_USER_ROOT", "XDG_CONFIG_HOME")}
        os.environ.pop("ZEPOS_SYSTEM_ROOT", None)
        os.environ["ZEPOS_USER_ROOT"] = str(home)
        os.environ["XDG_CONFIG_HOME"] = str(home)
        try:
            spec = importlib.util.spec_from_file_location(
                f"zepos_style_shot_{home.name}", SRC / "style_definition.py")
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


def size_of(name: str, scale: float | None = None) -> int:
    """Eine Groesse aus src/sizes.py, als ganze Zahl.

    Damit eine Messung ihre Erwartung aus DERSELBEN Quelle holt, aus der
    die erzeugte Datei sie hat - und nicht aus einer Zahl im Test.
    """
    sys.path.insert(0, str(SRC))
    try:
        import sizes
        section = {} if scale is None else {"scale": scale}
        return int(sizes.value_of(name, section))
    finally:
        sys.path.remove(str(SRC))


def _apps():
    sys.path.insert(0, str(SRC))
    try:
        import apps
        return apps
    finally:
        sys.path.remove(str(SRC))


def _decoration_and_glass() -> str:
    """Der `decoration`-Block und die Glasregeln, aus den echten Vorlagen.

    NICHT abgeschrieben. Ohne diese beiden Stuecke saehe man im Bild eine
    Leiste ohne Unschaerfe, ohne Schatten und mit anderer Rundung - also
    eine, die es auf keiner Installation gibt.

    Der Block wird ueber Klammerzaehlung aus der VERARBEITETEN Vorlage
    geschnitten, damit die {{STYLE_*}} darin schon aufgeloest sind.
    """
    processor = _processor()
    with tempfile.TemporaryDirectory(prefix="zepshot-hypr-") as scratch:
        rendered = Path(scratch) / "hyprland.conf"
        processor.apply_template(
            SRC / "templates" / "hyprland-universal-config.template", rendered)
        text = rendered.read_text(encoding="utf-8")

    lines = text.splitlines()
    block: list[str] = []
    depth = 0
    for line in lines:
        if not block and line.startswith("decoration {"):
            block.append(line)
            depth = 1
            continue
        if block:
            block.append(line)
            depth += line.count("{") - line.count("}")
            if depth == 0:
                break
    assert block and depth == 0, (
        "der decoration-Block steht nicht mehr in "
        "hyprland-universal-config.template - ohne ihn zeigt das Bild "
        "keine Unschaerfe")

    glass = [line for line in lines if line.startswith("layerrule = ")]
    assert glass, (
        "es gibt keine layerrule in der erzeugten Konfiguration; ohne sie "
        "waere jedes Bild ein Beweis ueber ein anderes System")
    return "\n".join(block + [""] + glass)


def render_configuration(target: Path, scale: float | None = None) -> Path:
    """Die AGS-Konfiguration, aus den Vorlagen erzeugt, in `target/ags`.

    `scale` ist der Groessenregler, unter dem erzeugt wird. None heisst:
    der ausgelieferte - und das ist der Normalfall, denn ein Bild soll
    zeigen, was der Nutzer bekommt. Ein anderer Faktor wird gebraucht,
    wo eine ABLEITUNG geprueft wird und nicht ihr Ergebnis; siehe
    tests/render/test_geometry.py.
    """
    ags = target / "ags"
    ags.mkdir(parents=True, exist_ok=True)
    processor = _processor(scale, target / "stil")
    for template, output in RENDERED.items():
        destination = ags / output
        destination.parent.mkdir(parents=True, exist_ok=True)
        processor.apply_template(SRC / template, destination)

    # Der Nachlauf, den generate_config.sh fuer ags-dock fuehrt. Ohne ihn
    # traegt das Dock die leere Liste aus der Vorlage und heftet nichts an.
    dock = ags / RENDERED["templates/ags-dock.template"]
    apps = _apps()
    dock.write_text(
        apps.render(dock.read_text(encoding="utf-8"), names=apps.shipped(SRC)),
        encoding="utf-8")

    scripts = ags / "scripts"
    scripts.mkdir(exist_ok=True)
    modules, status_text = module_payloads()
    for name, text in modules.items():
        script = scripts / name
        script.write_text(
            "#!/bin/bash\nprintf '%s' '{\"text\": \"" + text + "\"}'\n",
            encoding="utf-8")
        script.chmod(0o755)
    payload = ", ".join(f'"{key}": {{"text": "{value}"}}'
                        for key, value in status_text.items())
    status = scripts / "status.sh"
    status.write_text("#!/bin/bash\nprintf '%s' '{" + payload + "}'\n",
                      encoding="utf-8")
    status.chmod(0o755)
    return ags


def bundle(ags: Path, target: Path) -> Path:
    """app.ts, uebersetzt - die ganze Oberflaeche in einer Datei.

    `ags bundle` und nicht `ags run`: der Buendler liest Dateien und
    schreibt eine Datei. Gestartet wird das Ergebnis danach von Hand, mit
    einer Umgebung, die refuse_the_real_session() geprueft hat.
    """
    output = target / "zepos-shell.js"
    result = subprocess.run(
        ["ags", "bundle", str(ags / "app.ts"), str(output),
         "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, (
        "`ags bundle` hat die Oberflaeche nicht uebersetzt:\n"
        + result.stdout + result.stderr)
    return output


class Session:
    """Ein Hyprland im Hyprland, mit der Oberflaeche darin.

    Jeder Prozess, den diese Klasse startet, steht in `self.children`,
    und beendet wird ausschliesslich, was dort steht. Es gibt hier kein
    pkill: ein Mustertreffer im Prozessbaum der Maschine faende das AGS
    des Nutzers.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        # Kurzes Praefix unter /tmp, weil sockaddr_un.sun_path 108 Bytes
        # fasst und der Compositor <runtime>/wayland-N anlegt.
        self.runtime = Path(tempfile.mkdtemp(prefix="zepshot-"))
        self.runtime.chmod(0o700)
        self.home = self.runtime / "home"
        (self.home / ".config").mkdir(parents=True)
        self.log = self.runtime / "hyprland.log"
        self.shell_log = self.runtime / "shell.log"
        self.children: list[subprocess.Popen] = []
        self.compositor: subprocess.Popen | None = None
        self.display: str | None = None
        self.output: str | None = None
        # Erst gesetzt, wenn start_bus() gelaufen ist. Bis dahin zeigt
        # DBUS_SESSION_BUS_ADDRESS auf einen Pfad, den es nicht gibt -
        # nie auf den Bus des Nutzers.
        self.bus: str = f"unix:path={self.runtime}/kein-bus"

    # -- Umgebung ----------------------------------------------------

    def environment(self, **extra: str) -> dict[str, str]:
        assert self.display is not None, "start() wurde nicht gerufen"
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "WAYLAND_DISPLAY": self.display,
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "GDK_BACKEND": "wayland",
            "NO_AT_BRIDGE": "1",
            "GTK_A11Y": "none",
            # NIE der Bus des Nutzers. ags-tray.template ruft
            # Gio.bus_own_name auf org.kde.StatusNotifierWatcher und
            # Notifications.tsx auf org.freedesktop.Notifications - auf
            # dem echten Bus wuerde ein BILDLAUF die Ablage und den
            # Benachrichtigungsdienst seiner laufenden Sitzung
            # uebernehmen.
            "DBUS_SESSION_BUS_ADDRESS": self.bus,
            # DIE SPRACHE, WEIL IHR FEHLEN EINEN MANGEL ERFUNDEN HAT
            #     Diese Umgebung trug bis zum 12.08.2026 kein LANG. Ohne
            #     LANG steht jeder Kindprozess in der C-Locale, und
            #     Gtk.Calendar schreibt dort "Sun Mon Tue" und beginnt
            #     die Woche am Sonntag.
            #
            #     Genau das ist als Befund in einen Bericht gewandert -
            #     "die Wochentagszeile ist englisch". Auf einer deutschen
            #     Installation war sie es nie. Der Messstand hat einen
            #     Fehler behauptet, den es nicht gab, und der Bericht
            #     wirkte dadurch praeziser, als er war.
            #
            #     Der Name wird nicht abgeschrieben, sondern aus dem
            #     geholt, was der Assistent auf die Platte schreibt
            #     (installer.gui.pages.LANGUAGE_DEFAULTS) - sonst haette
            #     dieser Aufbau eine eigene Sprache, und die Bilder
            #     zeigten eine Maschine, die niemand installieren kann.
            "LANG": SESSION_LOCALE,
            "LC_ALL": SESSION_LOCALE,
        }
        environment.update(extra)
        refuse_the_real_session(environment)
        return environment

    # -- Start -------------------------------------------------------

    def start(self, timeout: float = 40.0) -> None:
        probe = self.runtime / "wayland-99"
        assert len(str(probe)) <= SUN_PATH_MAX, (
            f"{probe} ist {len(str(probe))} Bytes lang, sockaddr_un.sun_path "
            f"fasst {SUN_PATH_MAX}")
        host = host_wayland_socket()
        assert host is not None, (
            "Es laeuft keine Wayland-Sitzung, in die hinein verschachtelt "
            "werden koennte. Hyprland hat keinen Headless-Schalter.")

        # Laut sagen, wenn die Sprache fehlt. Die C-Bibliothek faellt
        # dann still auf C zurueck, und auf dem Bild sieht die
        # Oberflaeche englisch aus, obwohl sie es nicht ist - der Fehler,
        # den dieser Aufbau am 12.08.2026 selbst erzeugt und als Befund
        # weitergegeben hat. Kein Abbruch: ohne de_DE laesst sich alles
        # ausser der Sprache noch pruefen. Aber niemand soll das Bild
        # spaeter fuer eine Aussage ueber Uebersetzung halten.
        if not locale_is_generated(SESSION_LOCALE):
            print(f"WARNUNG: {SESSION_LOCALE} ist auf dieser Maschine nicht "
                  f"erzeugt (locale-gen). Die Bilder zeigen die C-Sprache - "
                  f"was darauf englisch aussieht, sagt nichts ueber ZepOS.",
                  file=sys.stderr)

        config = self.runtime / "hyprland.conf"
        config.write_text(
            # Der Ausgang des WAYLAND-BACKENDS, und er ist nicht der, der
            # abgebildet wird. Seine Groesse bestimmt der Wirt: gemessen
            # am 12.08.2026 gab ein `monitor = , 1920x1080@60` einen
            # Ausgang von 931x521 - Hyprland laeuft beim Wirt als
            # gekacheltes Fenster, und ein Bild davon belegte eine
            # Aufloesung, die es nicht hat.
            #
            # Deshalb steht er zur Seite und der echte Schirm entsteht
            # unten als HEADLESS-Ausgang, dessen Groesse niemand ausser
            # dieser Datei bestimmt.
            "monitor = , preferred, 4000x0, 1\n"
            "misc {\n"
            "    disable_hyprland_logo = true\n"
            "    disable_splash_rendering = true\n"
            "    force_default_wallpaper = 0\n"
            "}\n"
            # Aus, damit das Bild nicht mitten in einer Einblendung
            # entsteht. Was gemessen wird, ist der Ruhezustand.
            "animations { enabled = false }\n"
            "input { follow_mouse = 0 }\n"
            + _decoration_and_glass() + "\n",
            encoding="utf-8")

        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin"),
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            # Der WIRT, als absoluter Pfad: hier meldet sich der
            # verschachtelte Compositor als gewoehnliches Fenster an.
            "WAYLAND_DISPLAY": str(host),
            "HYPRLAND_NO_CRASHREPORTER": "1",
            "HYPRLAND_NO_SD_NOTIFY": "1",
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }
        with self.log.open("wb") as sink:
            self.compositor = subprocess.Popen(
                ["Hyprland", "-c", str(config)],
                env=environment, stdout=sink, stderr=subprocess.STDOUT)
        self.children.append(self.compositor)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = sorted(path.name for path in self.runtime.iterdir()
                           if path.name.startswith("wayland-")
                           and not path.name.endswith(".lock"))
            if found:
                self.display = found[0]
                break
            if self.compositor.poll() is not None:
                raise AssertionError(
                    "Das verschachtelte Hyprland endete, bevor es einen "
                    "Socket hatte:\n" + self.read_log())
            time.sleep(0.05)
        assert self.display, (
            f"kein Socket in {timeout} s:\n" + self.read_log())

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.hyprctl_json("monitors"):
                break
            time.sleep(0.2)
        else:
            raise AssertionError("der verschachtelte Compositor meldet "
                                 "keinen Ausgang:\n" + self.read_log())
        self._add_headless_output()

    def _add_headless_output(self, timeout: float = 20.0) -> None:
        """Der Schirm, der abgebildet wird - in der GEFORDERTEN Groesse.

        `hyprctl output create headless` legt einen Ausgang an, der an
        keiner Hardware und an keinem Wirtsfenster haengt. Seine
        Aufloesung setzt die Zeile darunter, und sie kommt an: gemessen
        am 12.08.2026 meldet hyprctl danach 1920x1080, und grim zieht ein
        PNG genau dieser Groesse.

        Das ist zugleich die einzige Art, in diesem Projekt ein Bild von
        1366x768 zu bekommen, ohne dass jemand seinen Bildschirm
        umstellt.
        """
        before = {monitor["name"] for monitor in self.hyprctl_json("monitors")}
        result = self.hyprctl("output", "create", "headless")
        assert result.returncode == 0, (
            f"kein headless-Ausgang: {result.stdout}{result.stderr}")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            names = {monitor["name"]
                     for monitor in self.hyprctl_json("monitors") or []}
            new = sorted(names - before)
            if new:
                self.output = new[0]
                break
            time.sleep(0.2)
        assert self.output, "der headless-Ausgang ist nicht erschienen"

        result = self.hyprctl(
            "keyword", "monitor",
            f"{self.output},{self.width}x{self.height}@60,0x0,1")
        assert result.returncode == 0, (
            f"der headless-Ausgang nahm die Groesse nicht an: {result.stderr}")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for monitor in self.hyprctl_json("monitors") or []:
                if monitor["name"] != self.output:
                    continue
                if (monitor["width"], monitor["height"]) == (self.width,
                                                             self.height):
                    return
            time.sleep(0.2)
        measured = [(m["name"], m["width"], m["height"])
                    for m in self.hyprctl_json("monitors") or []]
        raise AssertionError(
            f"der Schirm ist {measured} und nicht {self.width}x{self.height} - "
            "ein Bild davon belegte eine andere Aufloesung als die behauptete")

    # -- Steuerung ---------------------------------------------------

    def signature(self) -> str | None:
        directory = self.runtime / "hypr"
        if not directory.is_dir():
            return None
        entries = [path.name for path in directory.iterdir() if path.is_dir()]
        return entries[0] if len(entries) == 1 else None

    def hyprctl(self, *arguments: str) -> subprocess.CompletedProcess:
        """hyprctl auf DIESEN Compositor - nie auf den des Nutzers.

        Die Instanzkennung kommt aus dem privaten Laufzeitverzeichnis;
        ohne sie naehme hyprctl die erstbeste, und das waere die des
        Menschen, der diesen Lauf gestartet hat.
        """
        signature = self.signature()
        assert signature, "der verschachtelte Compositor hat keine Kennung"
        return subprocess.run(
            ["hyprctl", *arguments],
            env=self.environment(HYPRLAND_INSTANCE_SIGNATURE=signature),
            capture_output=True, text=True, timeout=20)

    def hyprctl_json(self, *arguments: str):
        if self.signature() is None:
            return None
        result = self.hyprctl("-j", *arguments)
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def spawn(self, command: list[str], log: Path | None = None,
              **extra: str) -> subprocess.Popen:
        sink = (log or self.shell_log).open("ab")
        process = subprocess.Popen(
            command, env=self.environment(**extra),
            stdout=sink, stderr=subprocess.STDOUT)
        self.children.append(process)
        return process

    def start_bus(self, timeout: float = 20.0) -> None:
        """Ein EIGENER Sitzungsbus, im privaten Laufzeitverzeichnis.

        WARUM ER GEBRAUCHT WIRD
            Die Aufklappfenster der Leiste werden von aussen ueber `ags
            request` erreicht - denselben Weg, den eine Tastenbindung
            nimmt. GEMESSEN am 12.08.2026: ohne Bus antwortet der Aufruf
            mit `dial unix .../kein-bus: connect: no such file or
            directory`, denn Astal meldet seine Instanz als GApplication
            am Sitzungsbus an. Ohne diesen Bus gaebe es kein Bild vom
            Kalender und keines vom Kontrollzentrum.

        WARUM ER EIGEN IST
            Auf dem Bus des Nutzers naehme dieser Lauf
            org.freedesktop.Notifications und
            org.kde.StatusNotifierWatcher - die Namen, an denen seine
            laufende Sitzung ihre Benachrichtigungen und ihre Ablage
            haengt. Ein Bildlauf, der die Meldungen des Nutzers
            abfaengt, ist kein Bildlauf mehr.
        """
        socket = self.runtime / "bus"
        address = f"unix:path={socket}"
        process = subprocess.Popen(
            ["dbus-daemon", "--session", f"--address={address}",
             "--nofork", "--nopidfile"],
            env={"PATH": os.environ.get("PATH", "/usr/bin"),
                 "HOME": str(self.home),
                 "XDG_RUNTIME_DIR": str(self.runtime)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.children.append(process)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if socket.exists():
                self.bus = address
                return
            if process.poll() is not None:
                raise AssertionError("dbus-daemon endete sofort")
            time.sleep(0.05)
        raise AssertionError(f"dbus-daemon hat {socket} nicht angelegt")

    def wallpaper(self) -> None:
        """Die ausgelieferte Tapete hinter das Glas.

        Ohne sie stuende die Leiste vor Schwarz, und halbdurchsichtig vor
        Schwarz ist von undurchsichtig nicht zu unterscheiden.
        """
        assert WALLPAPER.is_file(), f"{WALLPAPER} fehlt"
        self.spawn(["swaybg", "-i", str(WALLPAPER), "-m", "fill"])

    def shell(self, bundle_path: Path, config: Path) -> subprocess.Popen:
        """Die erzeugte Oberflaeche starten - Leiste, Dock, Ueberlagerungen.

        HYPRLAND_INSTANCE_SIGNATURE GEHOERT IN DIESE UMGEBUNG, und das ist
        gemessen
            In einer echten Sitzung ist AGS ein Kind des Compositors und
            erbt die Kennung. Hier wird es von Hand gestartet, und ohne
            die Zeile scheiterte jedes `hyprctl` IM AGS-Prozess:

                ags-CRITICAL: Failed to get overlay position: Error

            utils/overlay.ts faengt diesen Fehler ab und faellt auf
            `{marginTop: 20, marginLeft: 100, monitor: 0}` zurueck. Das
            Aufklappfenster entstand also - `ags request calendar`
            antwortete "toggled" - und lag auf Schirm 0, dem Wirtsfenster
            daneben. Auf dem Bild war nichts zu sehen.

            Eine Umgebung, in der ein Fehlerzweig laeuft statt des
            Normalfalls, misst den Fehlerzweig.
        """
        signature = self.signature()
        assert signature, "der verschachtelte Compositor hat keine Kennung"
        return self.spawn([str(bundle_path)],
                          XDG_CONFIG_HOME=str(config),
                          HYPRLAND_INSTANCE_SIGNATURE=signature)

    def move_cursor(self, x: int, y: int) -> None:
        """Den Zeiger auf den abgebildeten Schirm setzen.

        WARUM DAS NOETIG IST, UND ES IST GEMESSEN
            utils/overlay.ts fragt vor jedem Aufklappfenster `hyprctl
            cursorpos -j` und sucht den Schirm, auf dem der Zeiger steht.
            Der verschachtelte Compositor hat ZWEI Ausgaenge - den des
            Wirtsfensters und den headless-Ausgang, der abgebildet wird -,
            und der Zeiger stand beim ersten Lauf auf dem falschen. Das
            Fenster entstand, `ags request calendar` antwortete "toggled",
            und auf dem Bild war nichts: es lag auf dem anderen Schirm.

            Ein Bild, auf dem etwas fehlt, weil es woanders liegt, ist die
            gefaehrlichste Sorte Beleg - es sieht aus wie ein Befund.

        Die Stelle ist ausserdem nicht gleichgueltig: das Fenster wird
        WAAGERECHT AM ZEIGER ZENTRIERT. Wo der Zeiger steht, entscheidet
        also, wo das Modal steht.
        """
        result = self.hyprctl("dispatch", "movecursor", str(x), str(y))
        assert result.returncode == 0, (
            f"der Zeiger liess sich nicht setzen: {result.stderr}")

    def cursor_position(self) -> tuple[int, int] | None:
        data = self.hyprctl_json("cursorpos")
        if not data:
            return None
        return data["x"], data["y"]

    def request(self, message: str, timeout: float = 20.0) -> str:
        """Eine Anfrage an app.ts - so, wie eine Tastenbindung sie stellt."""
        result = subprocess.run(
            ["ags", "request", message, "-i", "ags"],
            env=self.environment(), capture_output=True, text=True,
            timeout=timeout)
        return (result.stdout + result.stderr).strip()

    def layers(self) -> dict[str, tuple[int, int, int, int]]:
        """Was auf DEM abgebildeten Schirm liegt: Namensraum -> x,y,b,h.

        Nur dieser Schirm. Die Leiste baut ein Fenster JE Ausgang, und der
        Wirtsausgang daneben traegt dieselben Namensraeume - eine Liste
        ueber alle Ausgaenge zaehlte jede Flaeche doppelt.
        """
        data = self.hyprctl_json("layers") or {}
        found: dict[str, tuple[int, int, int, int]] = {}
        for name, screen in data.items():
            if name != self.output:
                continue
            for level in screen.get("levels", {}).values():
                for layer in level:
                    found[layer.get("namespace")] = (
                        layer.get("x"), layer.get("y"),
                        layer.get("w"), layer.get("h"))
        return found

    # -- Bild --------------------------------------------------------

    def shoot(self, path: Path, geometry: str | None = None) -> Path:
        """Ein Bildschirmabzug des verschachtelten Schirms.

        grim ueber wlr-screencopy. Der Ausgang wird NAMENTLICH genannt:
        ohne -o nimmt grim alle Ausgaenge, die der Compositor kennt, und
        das waeren in einer verschachtelten Sitzung ohne diese Zeile
        moeglicherweise die des Wirts.
        """
        assert self.output, "start() hat keinen Ausgang gefunden"
        # Hyprlands EIGENE Meldungen wegraeumen. Es legt zwei davon in
        # die obere rechte Ecke - "Hyprland was started without
        # start-hyprland" (die Zeile steht im Binaerprogramm, `strings
        # /usr/bin/Hyprland`) und eine ueber die Anordnung der beiden
        # Ausgaenge dieses Aufbaus. Beide gehoeren zu DIESEM Aufbau und
        # nicht zur Oberflaeche; auf dem Bild waeren sie ein Befund, der
        # keiner ist.
        self.hyprctl("dismissnotify")
        path.parent.mkdir(parents=True, exist_ok=True)
        command = ["grim", "-l", "6"]
        if geometry:
            command += ["-g", geometry]
        else:
            command += ["-o", self.output]
        command.append(str(path))
        result = subprocess.run(command, env=self.environment(),
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, (
            f"grim hat kein Bild geschrieben:\n{result.stderr}")
        assert path.is_file() and path.stat().st_size > 0, (
            f"{path} ist leer")
        return path

    # -- Ende --------------------------------------------------------

    def read_log(self) -> str:
        return self.log.read_text(encoding="utf-8", errors="replace")

    def read_shell_log(self) -> str:
        if not self.shell_log.exists():
            return ""
        return self.shell_log.read_text(encoding="utf-8", errors="replace")

    def stop(self) -> None:
        """Nur die eigenen Kinder, und in umgekehrter Startreihenfolge."""
        for process in reversed(self.children):
            if process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        self.children.clear()
        self.compositor = None
        shutil.rmtree(self.runtime, ignore_errors=True)

    def __enter__(self) -> "Session":
        # EIN start(), DAS AUF HALBEM WEG AUFGIBT, MUSS TROTZDEM
        # AUFRAEUMEN - und ohne dieses try tut es das nicht.
        #
        #     Python ruft __exit__ NUR, wenn __enter__ zurueckgekehrt
        #     ist. Wirft start() eine der drei Zusicherungen darin
        #     ("kein Socket", "meldet keinen Ausgang", "kein headless
        #     -Ausgang"), ist das verschachtelte Hyprland aber schon
        #     gestartet und bleibt stehen.
        #
        #     GEMESSEN am 17.08.2026, nach einer Reihe fehlgeschlagener
        #     Laeufe: sechs Hyprland-Prozesse mit PPID 1, zwischen 16 und
        #     33 Minuten alt, jeder mit seinem eigenen
        #     /tmp/zepshot-*/hyprland.conf. Jeder haelt seine
        #     Wayland-Flaeche beim Wirt, und je mehr davon stehen, desto
        #     wahrscheinlicher scheitert der naechste Start. Ein Fehler,
        #     der sich selbst vermehrt - und der aussieht wie ein
        #     Befund ueber die Oberflaeche, obwohl er einer ueber den
        #     Messstand ist.
        try:
            self.start()
        except BaseException:
            self.stop()
            raise
        return self

    def __exit__(self, *_exception) -> None:
        self.stop()


def workspaces_file(config: Path, connector: str) -> None:
    """workspaces.json fuer den Ausgang, den der Compositor wirklich hat.

    Der Name kommt aus hyprctl und nicht aus einer Konstante: die Leiste
    schlaegt ihre Arbeitsbereiche unter monitor.connector nach, und
    welchen Namen ein verschachtelter Wayland-Ausgang traegt, entscheidet
    der Backend - nicht diese Datei.
    """
    ags = config / "ags"
    ags.mkdir(parents=True, exist_ok=True)
    (ags / "workspaces.json").write_text(
        json.dumps({"persistent-workspaces": {connector: WORKSPACES}}),
        encoding="utf-8")


def required_tools() -> list[str]:
    """Was diese Maschine braucht, damit ein Bild entsteht.

    Namentlich und vollzaehlig, damit ein Fehlschlag sagt, WAS fehlt:

        Hyprland   der verschachtelte Compositor. Er allein bringt
                   Layer-Shell, Unschaerfe und Rundung mit.
        hyprctl    der Weg, ihm einen headless-Ausgang in der gewuenschten
                   Groesse abzuverlangen.
        ags        der Buendler fuer die Oberflaeche.
        grim       der Bildschirmabzug ueber wlr-screencopy.
        swaybg     die Tapete. Ohne Hintergrund belegt ein Bild ueber
                   Glas nichts.
        dbus-daemon  der EIGENE Sitzungsbus, ohne den `ags request` die
                   Aufklappfenster nicht erreicht.
    """
    return missing_tools("Hyprland", "hyprctl", "ags", "grim", "swaybg",
                         "dbus-daemon")
