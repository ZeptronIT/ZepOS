# SPDX-License-Identifier: GPL-3.0-or-later
"""Welcher Bildschirm wo steht, wie gross und wie schnell - und der
Rueckweg, wenn die Antwort falsch war.

WAS DIESES MODUL VON src/monitors.py UNTERSCHEIDET
    src/monitors.py beantwortet "welcher ARBEITSBEREICH liegt auf welchem
    Schirm" und sagt in seinem Kopf ausdruecklich, dass die Modus-Zeilen
    (`monitor=desc:...,1920x1200@60,...`) ihm nicht gehoeren. Sie
    gehoerten bis zum 12.08.2026 nwg-displays. Dies hier ist die andere
    Haelfte: die Modus-Zeilen selbst, ~/.config/hypr/monitors.conf, und
    das Anwenden auf den laufenden Compositor.

    Zwei Module, weil es zwei Fragen sind, und eine Antwort je Frage. Wo
    sie sich beruehren, wird gerufen statt nachgebaut: wie ein Schirm in
    einer Hyprland-Regel heisst, entscheidet monitors.selector() - hier
    wie dort, mit derselben Begruendung und demselben Rueckfall auf den
    Anschlussnamen, wenn zwei Schirme dieselbe Beschreibung tragen.

DIE VORLAGE: nwg-displays 0.4.3, MIT
    GEMESSEN am 12.08.2026 an der installierten Fassung:
    /usr/lib/python3.14/site-packages/nwg_displays-0.4.3.dist-info/
    licenses/LICENSE traegt "MIT License, Copyright (c) 2022 Piotr
    Miller", `pacman -Qi nwg-displays` meldet "Lizenzen: MIT", und die
    GitHub-API sagt fuer nwg-piotr/nwg-displays "spdx_id": "MIT". MIT
    laesst sich in ein GPL-3.0-or-later-Projekt aufnehmen, also durfte
    hier abgeschrieben werden.

    UEBERNOMMEN ist die Bildsprache und das Verfahren:

      * Bildschirme als Rechtecke auf einer verkleinerten Zeichnung, die
        man schiebt (dort ein Gtk.Fixed voller Gtk.Button, main.py:395).
      * Das Einrasten an den vier Kanten jedes Nachbarn, mit einem
        Schwellwert (dort `snap-threshold`, 10 Zeichnungspixel, gegen
        `view-scale` 0.15 gerechnet - also rund 15; siehe SNAP_DISTANCE).
      * Dass die Anordnung als `monitor=`-Zeilen in eine Datei geht, die
        Hyprland per `source=` liest. Das Format der Zeile gehoert
        ohnehin Hyprland.

    NICHT uebernommen ist Code. nwg-displays ist GTK3 (main.py:26
    `gi.require_version("Gtk", "3.0")`, tools.py:12 Gdk 3.0, main.py:28
    GtkLayerShell 0.1) und war damit das letzte GTK3-Programm in ZepOS -
    der Grund, aus dem dieses Modul ueberhaupt entstanden ist.

DER RUECKFALL - WAS DIE VORLAGE HAT UND WAS IHR FEHLT
    Eine falsche Bildschirmeinstellung ist der Fehler, aus dem sich
    niemand herausklickt: der Schirm bleibt schwarz, und die Oberflaeche,
    mit der man es zuruecknehmen wuerde, ist genau die, die man nicht
    mehr sieht.

    nwg-displays hat dafuer etwas, und das ist beim Nachbauen wichtiger
    zu wissen als alles andere: `create_confirm_win()` (main.py:947) legt
    ein Fenster "Keep current settings?" mit einem Zaehler von
    `confirm-timeout` Sekunden (Vorgabe 10, tools.py:486) darueber, und
    `count_down()` (main.py:989) stellt ohne Antwort wieder her.

    Drei Dinge daran taugen fuer ZepOS nicht, und alle drei sind
    gemessen:

      1. DER ZEITGEBER LEBT IM PROGRAMM. `GLib.timeout_add_seconds(1,
         count_down, ...)` laeuft in derselben Hauptschleife wie das
         Fenster. Stirbt das Programm zwischen "angewandt" und
         "bestaetigt" - Absturz, SIGKILL, ein Fenstermanager, der es
         mitnimmt -, stirbt der Rueckfall mit ihm, und der schwarze
         Schirm bleibt. Ein Rueckfall, der nur laeuft, solange das
         Programm lebt, ist keiner.
      2. DER RUECKFALL SCHREIBT NUR DIE DATEI. `restore_old_settings()`
         (main.py:1017) legt fuer Hyprland die alte monitors.conf zurueck
         und wartet darauf, dass der Compositor sie von selbst bemerkt -
         der Kommentar dort sagt es woertlich ("Don't execute any command
         here, just save the file and wait for Hyprland to notice"). Ein
         Rueckweg, der von der Selbstbeobachtung des Compositors abhaengt,
         ist einer, der auch ausbleiben kann.
      3. DER PROFILWEG HAT GAR KEINEN. `apply_from_json()` -
         `nwg-displays-apply -p <profil>` - bekommt keinen
         Bestaetigungs-Rueckruf uebergeben und wendet ungefragt an.

    Hier laeuft der Rueckfall deshalb in einem EIGENEN PROZESS,
    src/bin/zepos-displays-guard, der ueber eine Pipe an der Oberflaeche
    haengt:

      * Er bekommt VOR dem Anwenden den Wiederherstellungsplan und meldet
        GUARD_READY. Erst dann darf angewandt werden.
      * Kommt GUARD_KEEP, endet er, ohne etwas zu tun.
      * Laeuft die Frist ab, stellt er den Plan wieder her - mit
        `hyprctl keyword monitor` und nicht durch das Zuruecklegen einer
        Datei, also ohne auf jemanden zu warten.
      * Bricht die Pipe, ist das Programm tot, und er stellt SOFORT
        wieder her. Der Absturz wird damit zum schnellsten Weg zurueck
        statt zu dem, der ihn verhindert.

WAS ZUERST GESCHRIEBEN WIRD - UND WAS NICHT
    ~/.config/hypr/monitors.conf wird ERST NACH der Bestaetigung
    geschrieben. Anwenden und Schreiben sind zwei Dinge, und die
    Reihenfolge ist die halbe Sicherheit: waere die Datei schon
    geschrieben, brauchte der Rueckfall einen zweiten Rueckfall fuer sie
    - und eine Sitzung, die nach einem Absturz mit der schlechten Datei
    startet, findet keinen Schirm mehr, auf dem sie fragen koennte.

    Deshalb auch `hyprctl keyword monitor` und nicht nwg-displays' Weg
    (Datei schreiben, dann `reload`): `keyword` aendert den laufenden
    Compositor, ohne eine Datei anzufassen. Anders herum liesse sich
    "auf Probe" gar nicht bauen.

DIE PROFILE
    profiles/<name>/monitors.conf unter paths.user_root(), und
    start-hyprland kopiert sie beim Sitzungsstart ueber
    ~/.config/hypr/monitors.conf. Eine Anordnung, die nur in
    ~/.config/hypr landet, waere damit beim naechsten Anmelden weg -
    "eine Einstellung, die nie ankommt", der Fehler, den
    settings/zepos_settings_gui/model.py in seinem Kopf benennt.
    targets() schreibt deshalb BEIDE Dateien, wenn ein Profil aktiv ist,
    und die Oberflaeche sagt welche.

    Der Profilpfad steht hier ueber paths.user_root() und nicht
    ausgeschrieben, weil er ausgeschrieben eine Behauptung waere: die
    Wurzel der Nutzereinstellungen ist verschiebbar, und
    tests/src/test_naming.py faengt genau diese Behauptung ab.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable

import monitors
import paths

Runner = Callable[..., subprocess.CompletedProcess]

# Die Frist, nach der ohne Antwort zurueckgestellt wird.
#
# 15 Sekunden. Die Vorlage nimmt 10 (tools.py:486), Windows fragt seit
# Vista 15 Sekunden lang "Diese Anzeigeeinstellungen beibehalten?".
# 15 und nicht 10, weil ein DisplayPort-Monitor nach einem Moduswechsel
# bis zu fuenf Sekunden braucht, bis er ueberhaupt etwas zeigt - eine
# Frist, die waehrend des Aufwachens ablaeuft, misst nicht, ob der Nutzer
# etwas sieht, sondern nur, wie schnell sein Monitor synchronisiert.
# Laenger waere die Zeit, die jemand vor einem schwarzen Schirm sitzt und
# glaubt, er habe seinen Rechner zerstoert.
CONFIRM_SECONDS = 15

# Was der Waechter obendrauf bekommt.
#
# Die Oberflaeche zaehlt selbst herunter und schickt bei 0 ein
# GUARD_REVERT; der Waechter faengt die Oberflaeche auf, die HAENGT statt
# abzustuerzen - eine abgestuerzte meldet sich ueber die gebrochene Pipe
# sofort. Beide auf dieselbe Sekunde zu legen hiesse, zwei Uhren
# gegeneinander laufen zu lassen und den Rueckfall doppelt auszufuehren.
GUARD_GRACE_SECONDS = 5

# Was ueber die Pipe geht. Ganze Zeilen, weil eine Pipe keine Nachrichten
# kennt, sondern Bytes - ein halb angekommenes Wort waere ein Rueckfall,
# der auf den Rest wartet.
GUARD_READY = "bereit"
GUARD_KEEP = "behalten"
GUARD_REVERT = "verwerfen"

# Womit der Waechter endet, damit ein Aufrufer den Grund kennt, ohne
# seine Ausgabe zu lesen.
EXIT_KEPT = 0
EXIT_REVERTED_DEADLINE = 10
EXIT_REVERTED_BROKEN_PIPE = 11
EXIT_REVERTED_ON_REQUEST = 12

# Der Name des Waechters, wie das Paket ihn nach /usr/bin legt.
GUARD_NAME = "zepos-displays-guard"

# Wie nah zwei Kanten sein muessen, damit die eine auf die andere
# springt, in BILDSCHIRMpixeln.
#
# Die Vorlage rechnet in Zeichnungspixeln: `snap-threshold` 10, mit
# `view-scale` 0.15 auf 15 hochgerechnet (main.py:511). Hier steht die
# Zahl in Bildschirmpixeln, weil das Einrasten in displays.py passiert
# und displays.py von der Zeichnung nichts weiss - 100 Bildschirmpixel
# sind bei einer Zeichnung im Verhaeltnis 1:10 zehn Zeichnungspixel, also
# dieselbe Groessenordnung.
#
# Ein Rest von dreissig Pixeln zwischen zwei Schirmen ist ausserdem kein
# Gestaltungswunsch, sondern ein Streifen, in dem der Mauszeiger
# haengenbleibt: Hyprland fuehrt ihn nicht ueber Nichts hinweg.
SNAP_DISTANCE = 100

# Wie eine Modus-Angabe aussieht: 1920x1200@60.001, oder ohne die Rate.
# Gebraucht, um in einer bestehenden monitors.conf die VOLLSTAENDIGE
# Regel einer Zeile von den Beisatzzeilen zu unterscheiden, die
# nwg-displays fuer die Drehung schreibt (`monitor=DP-1,transform,1`).
MODE_FIELD = re.compile(r"^\d+x\d+(@[\d.]+)?$")


class NoScreenLeft(ValueError):
    """Eine Anordnung, in der kein Schirm mehr an ist.

    Eigener Typ, weil ein Aufrufer hier etwas anderes tun muss als bei
    jedem anderen Eingabefehler: nicht melden und weitermachen, sondern
    gar nicht erst anwenden. Es gibt keinen Rueckfall aus einem
    Schreibtisch ohne Bild, weil die Frage, ob man ihn behalten will, auf
    keinem Schirm mehr stuende.
    """


# --------------------------------------------------------------------
# Was der Compositor ueber die angeschlossenen Schirme sagt
# --------------------------------------------------------------------

def number(value: float) -> str:
    """Eine Zahl fuer eine Konfigurationsdatei, ohne Nachkommanull.

    "60.0" und "1.0" sind gueltig und lesen sich in einer erzeugten Datei
    wie ein Versehen; "1.25" muss dagegen stehenbleiben. Fuenf
    Nachkommastellen, weil `hyprctl` die Bildwiederholrate so meldet
    (60.00100) und eine frueher abgeschnittene Zahl einen anderen Modus
    treffen kann.
    """
    text = f"{float(value):.5f}".rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class Mode:
    """Ein Modus, wie der Bildschirm selbst ihn anbietet."""

    width: int
    height: int
    refresh: float

    def __str__(self) -> str:
        return f"{self.width}x{self.height}@{number(self.refresh)}"

    @property
    def label(self) -> str:
        """Wie er in einer Auswahlliste steht - fuer Menschen, mit Hz."""
        return f"{self.width} x {self.height}, {number(self.refresh)} Hz"


@dataclass(frozen=True)
class Output:
    """Ein Eintrag aus `hyprctl monitors all -j`.

    `all` und nicht die Vorgabe: ohne das Wort zaehlt Hyprland nur die
    EINGESCHALTETEN Schirme auf. Ein abgeschalteter waere dann nicht
    vorhanden statt aus - er stuende in keiner Liste, liesse sich nicht
    wieder einschalten, und der Wiederherstellungsplan wuesste nichts von
    ihm. GEMESSEN am 12.08.2026 gegen Hyprland 0.55.4: die Antwort auf
    `monitors all -j` traegt das Feld "disabled", die auf `monitors -j`
    enthaelt die abgeschalteten gar nicht.

    Dieselbe Auskunft holt sich die Vorlage umstaendlicher: sie fragt
    BEIDE Listen ab und bildet die Differenz (tools.py:255-262).
    """

    name: str
    description: str
    width: int
    height: int
    refresh: float
    x: int
    y: int
    scale: float
    transform: int
    disabled: bool
    modes: tuple[Mode, ...] = ()

    @property
    def label(self) -> str:
        """Wie dieser Schirm einem Menschen gegenueber heisst.

        Der Anschlussname zuerst, weil er kurz ist und auf der Zeichnung
        steht; die Beschreibung dahinter, weil zwei gleiche Modelle sonst
        nicht zu unterscheiden waeren.
        """
        return f"{self.name} - {self.description}" if self.description else self.name


def _number(value: Any, fallback: float) -> float:
    """Ein Zahlenfeld der Compositor-Antwort, oder der Rueckfall.

    Dieselbe Begruendung wie in src/monitors.py: `hyprctl monitors -j`
    hat zwischen Hyprland-Fassungen die Form gewechselt, und ein
    fehlendes Feld darf hier keinen TypeError werfen - die Oberflaeche
    stuende dann leer da, ohne zu sagen warum.
    """
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def parse_mode(text: str) -> Mode | None:
    """"1920x1200@60.00Hz" - so steht ein Modus in `availableModes`.

    None fuer alles, was nicht so aussieht. Ein unlesbarer Eintrag darf
    die anderen nicht mitnehmen: die Liste kommt vom Bildschirm ueber den
    Kernel, und ein Monitor mit kaputtem EDID ist genau der, bei dem
    jemand diese Oberflaeche braucht.
    """
    body = text.strip()
    if body[-2:].lower() == "hz":
        body = body[:-2].strip()
    resolution, _, rate = body.partition("@")
    width, _, height = resolution.partition("x")
    try:
        return Mode(int(width), int(height), float(rate) if rate else 0.0)
    except ValueError:
        return None


def read_outputs(*, runner: Runner | None = None) -> list[Output]:
    """Jeder Schirm, den der laufende Compositor kennt - auch die aus.

    Wirft RuntimeError fuer alles, was "der Compositor hat nicht sinnvoll
    geantwortet" heisst: ein Typ, weil ein Aufrufer genau eine Sache
    damit tun kann, naemlich sagen, dass er nichts weiss.

    Ueber den Befehl `hyprctl` und nicht ueber seinen Unix-Socket, den
    die Vorlage selbst oeffnet (tools.py:92). Ihr Weg spart einen Prozess
    und hat dafuer ein einzelnes `s.recv(20480)` ohne Schleife: eine
    Antwort ueber 20 KiB - drei Bildschirme mit vielen Modi reichen dafuer
    - wird stillschweigend abgeschnitten und endet in einem
    JSONDecodeError. Der Befehl liest seinen Socket vollstaendig aus.
    """
    runner = runner or subprocess.run

    try:
        result = runner(["hyprctl", "monitors", "all", "-j"],
                        capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeError(f"hyprctl liess sich nicht starten: {exc}") from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"hyprctl endete mit {result.returncode}: "
            f"{(result.stderr or '').strip()}")

    try:
        entries = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError(f"hyprctl antwortete kein JSON: {exc}") from exc

    if not isinstance(entries, list):
        raise RuntimeError(
            f"hyprctl antwortete {type(entries).__name__} und keine Liste "
            "von Bildschirmen")

    outputs = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "") or "").strip()
        if not name:
            # Ein Schirm ohne Anschlussnamen laesst sich in keiner
            # `monitor=`-Zeile nennen. Ausgelassen statt in eine Zeile
            # geschrieben, die auf nichts passt - dieselbe Entscheidung
            # wie in monitors.layout().
            continue
        raw_modes = entry.get("availableModes")
        modes: tuple[Mode, ...] = ()
        if isinstance(raw_modes, list):
            modes = tuple(
                mode for mode in (parse_mode(str(text)) for text in raw_modes)
                if mode is not None)
        outputs.append(Output(
            name=name,
            description=str(entry.get("description", "") or ""),
            width=int(_number(entry.get("width"), 0.0)),
            height=int(_number(entry.get("height"), 0.0)),
            refresh=_number(entry.get("refreshRate"), 0.0),
            x=int(_number(entry.get("x"), 0.0)),
            y=int(_number(entry.get("y"), 0.0)),
            scale=_number(entry.get("scale"), 1.0),
            transform=int(_number(entry.get("transform"), 0.0)),
            disabled=bool(entry.get("disabled")),
            modes=modes,
        ))
    return outputs


# --------------------------------------------------------------------
# Was der Nutzer daraus machen will
# --------------------------------------------------------------------

@dataclass(frozen=True)
class Placement:
    """Ein Schirm, so wie er stehen soll.

    `selector` ist, wie die Hyprland-Regel ihn nennt - `desc:...`, solange
    das eindeutig ist, sonst der Anschlussname. Die Entscheidung faellt in
    monitors.selector() und nicht hier, weil es dieselbe Frage ist wie bei
    den Arbeitsbereichs-Regeln und zwei Antworten darauf zwei Antworten
    waeren. `name` bleibt daneben stehen, weil `hyprctl` seine Schirme
    beim Anschlussnamen nennt und die Zeichnung ihn zeigt.

    `extra` ist der Teil einer bestehenden `monitor=`-Zeile HINTER den
    vier Feldern, die diese Oberflaeche kennt - `mirror,DP-1`, `vrr,1`,
    `bitdepth,10`, `cm,hdr` und was Hyprland dort sonst entgegennimmt.

    WARUM DURCHGEREICHT UND NICHT ANGEBOTEN
        Weil "nicht angeboten" nicht "weg" heissen darf. Wer seinen
        zweiten Schirm spiegelt und danach hier eine Aufloesung aendert,
        haette die Spiegelung sonst still verloren - eine Oberflaeche, die
        beim Anfassen einer Einstellung eine andere loescht, ist
        schlimmer als eine, die die andere nicht kennt.

        Und "angeboten" waere hier nicht ehrlich. Die Vorlage zeigt,
        warum: `vrr` kennt in der Konfiguration drei Stellungen (0, 1, 2),
        `hyprctl` meldet dafuer ein true/false zurueck, und nwg-displays
        schreibt es fuer Hyprland deshalb GAR NICHT in die Datei
        (settings_applier.py:319 setzt adaptive_sync nur fuer sway; der
        Schalter ist unter Hyprland ausgegraut, main.py:1310). Ein
        Schalter hier machte beim blossen Oeffnen des Fensters aus einer 2
        eine 0.
    """

    name: str
    selector: str
    enabled: bool
    width: int
    height: int
    refresh: float
    x: int
    y: int
    scale: float
    transform: int
    extra: tuple[str, ...] = ()

    @property
    def is_rotated(self) -> bool:
        """Ob der Schirm auf der Seite steht.

        wl_output zaehlt seine Transformationen 0 bis 7, und die ungeraden
        sind die vier, die das Bild um 90 Grad drehen - 1 und 3 gedreht,
        5 und 7 gedreht und gespiegelt. Wortgleich zu
        monitors.Monitor.is_rotated, weil es dieselbe Tatsache ueber
        dasselbe Protokoll ist.
        """
        return self.transform % 2 == 1

    @property
    def displayed_width(self) -> int:
        """Die Breite, die dieser Schirm im Gesamtbild einnimmt.

        Nach der Drehung und nach dem Massstab, in dieser Reihenfolge:
        Hyprland dreht den Modus und teilt danach durch den Massstab, und
        die Zahl, die dabei herauskommt, ist die, gegen die die Position
        des Nachbarn zaehlt. Ein Nachbar, der gegen die MODUS-Breite
        gesetzt wird, ueberlappt bei jedem Massstab ausser 1.
        """
        long_side = self.height if self.is_rotated else self.width
        return max(1, round(long_side / self.scale))

    @property
    def displayed_height(self) -> int:
        short_side = self.width if self.is_rotated else self.height
        return max(1, round(short_side / self.scale))

    @property
    def right(self) -> int:
        return self.x + self.displayed_width

    @property
    def bottom(self) -> int:
        return self.y + self.displayed_height


def placement_of(output: Output, among: Iterable[Output] = (),
                 extra: tuple[str, ...] = ()) -> Placement:
    """Was gerade gilt, als Entwurf zum Verstellen."""
    return Placement(
        name=output.name,
        selector=monitors.selector(output, list(among) or [output]),
        enabled=not output.disabled,
        width=output.width,
        height=output.height,
        refresh=output.refresh,
        x=output.x,
        y=output.y,
        scale=output.scale,
        transform=output.transform,
        extra=extra,
    )


def current_layout(outputs: Iterable[Output],
                   options: dict[str, tuple[str, ...]] | None = None,
                   ) -> list[Placement]:
    """Der ganze Schreibtisch, so wie er in diesem Moment steht.

    `options` ist, was read_trailing_options() aus der bestehenden Datei
    geholt hat. Nachgeschlagen wird unter BEIDEN Namen, unter denen ein
    Schirm dort stehen kann: unter dem, den monitors.selector() heute
    waehlt, und unter dem Anschlussnamen. Eine Datei, die nwg-displays
    mit `use-desc` geschrieben hat, traegt `desc:...`; eine ohne den
    Schalter den Anschlussnamen. Nur unter einem von beiden zu suchen
    hiesse, die Spiegelung der Haelfte aller Nutzer wegzuwerfen.
    """
    outputs = list(outputs)
    options = options or {}
    layout = []
    for output in outputs:
        chosen = monitors.selector(output, outputs)
        extra = options.get(chosen)
        if extra is None:
            extra = options.get(output.name, ())
        layout.append(placement_of(output, outputs, tuple(extra)))
    return layout


# --------------------------------------------------------------------
# monitors.conf lesen und schreiben
# --------------------------------------------------------------------

def config_path() -> Path:
    """~/.config/hypr/monitors.conf - die Datei, die hyprland.conf sourcet.

    Ueber paths.output_root(), also unter XDG_CONFIG_HOME: derselbe Weg,
    den der Generator fuer jede erzeugte Datei nimmt, und damit derselbe,
    den ein Test umlenkt.
    """
    return paths.output_root() / "hypr" / "monitors.conf"


def profile_path(name: str) -> Path:
    return paths.user_root() / "profiles" / name / "monitors.conf"


def current_profile() -> str:
    """Welches Profil diese Sitzung gestartet hat, oder "".

    ~/.config/hypr/current-profile, geschrieben von
    hyprland-status-config.template. Gelesen und nicht geraten: der Name
    entscheidet, ob eine geaenderte Anordnung die naechste Anmeldung
    ueberlebt oder von start-hyprland wieder ueberschrieben wird.

    "unknown" schreibt hyprland-status, wenn es die Datei nicht gibt, und
    "auto" steht fuer den Erstaufbau ohne Profil. Beides ist kein
    Verzeichnis, und eine Datei dorthin zu schreiben legte eins an, das
    kein `start-hyprland` je liest.
    """
    marker = paths.output_root() / "hypr" / "current-profile"
    try:
        name = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if name in ("", "unknown", "auto") or "/" in name or name.startswith("."):
        return ""
    return name


def targets() -> list[Path]:
    """Jede Datei, in die diese Anordnung geschrieben werden muss.

    Zwei, wenn ein Profil aktiv ist und sein Verzeichnis auch existiert.
    Der Grund steht im Kopf: die zweite ist die, aus der start-hyprland
    beim naechsten Anmelden kopiert, und ohne sie waere jede Aenderung
    hier nur bis zur naechsten Anmeldung haltbar.

    Angelegt wird ein Profilverzeichnis hier NICHT. Ein Profil entsteht
    durch `save-profile <name>`, das fuenf Dateien ablegt; eins, das nur
    monitors.conf enthaelt, laesst start-hyprland beim naechsten `cp`
    scheitern.
    """
    found = [config_path()]
    name = current_profile()
    if name:
        profile = profile_path(name)
        if profile.parent.is_dir():
            found.append(profile)
    return found


def parse_line(line: str) -> tuple[str, tuple[str, ...]] | None:
    """Eine `monitor=`-Zeile in Namen und die Felder dahinter.

    Am ERSTEN Komma getrennt, genau wie Hyprland selbst: ein
    `desc:`-Name, dessen EDID-Zeichenkette ein Komma enthaelt, ist damit
    hier so kaputt wie dort, und nicht anders. src/monitors.py fuehrt die
    Messung dazu.

    None fuer jede Zeile, die keine `monitor=`-Zeile ist, und fuer die
    Auffangzeile mit leerem Namen: die gehoert
    hyprland-universal-config.template und benennt keinen Schirm.
    """
    text = line.split("#", 1)[0].strip()
    key, separator, value = text.partition("=")
    if not separator or key.strip() != "monitor":
        return None
    fields = [field.strip() for field in value.split(",")]
    name = fields[0]
    if not name:
        return None
    return name, tuple(fields[1:])


def trailing_options(text: str) -> dict[str, tuple[str, ...]]:
    """Was in einer bestehenden monitors.conf hinter den vier Feldern steht.

    Vier, weil eine vollstaendige Regel `name,modus,position,massstab`
    ist; alles danach sind Zusatzworte, die diese Oberflaeche nicht kennt
    und nicht wegwerfen darf - siehe Placement.extra.

    NUR vollstaendige Regeln werden gelesen, und das ist gemessen:
    nwg-displays schreibt die Drehung als EIGENE Zeile hinter die Regel
    (`monitor=DP-1,transform,1`, settings_applier.py:463). Ohne diese
    Pruefung ueberschriebe diese zweite Zeile die Zusatzworte der ersten
    mit nichts, und `mirror,DP-2` waere beim ersten Speichern weg.

    Eine `disable`-Zeile liefert nichts: hinter `disable` nimmt Hyprland
    ohnehin nichts mehr entgegen.
    """
    found: dict[str, tuple[str, ...]] = {}
    for line in text.splitlines():
        parsed = parse_line(line)
        if parsed is None:
            continue
        name, fields = parsed
        if not fields or not MODE_FIELD.match(fields[0]):
            continue
        found[name] = tuple(fields[3:]) if len(fields) > 3 else ()
    return found


def read_trailing_options(path: Path | None = None) -> dict[str, tuple[str, ...]]:
    target = path if path is not None else config_path()
    try:
        return trailing_options(target.read_text(encoding="utf-8"))
    except OSError:
        # Beim ersten Mal gibt es sie nicht, und der Generator legt sie
        # als einzeilige Platzhalterdatei an. Beides heisst dasselbe:
        # nichts durchzureichen.
        return {}


def spec(placement: Placement) -> str:
    """Der Rumpf einer `monitor=`-Zeile fuer diesen Schirm.

    Das Format gehoert Hyprland: `name,BREITExHOEHE@RATE,XxY,MASSSTAB`
    und danach beliebig viele Zusatzworte, oder `name,disable`.

    Die Drehung steht hier IN DERSELBEN ZEILE, als Zusatzwortpaar
    `transform,N`. nwg-displays schreibt dafuer eine zweite
    `monitor=`-Zeile fuer denselben Schirm (settings_applier.py:463);
    beides liest Hyprland, aber eine Regel je Schirm ist die Form, in der
    `hyprctl keyword monitor` sie auch anwenden kann - zwei Zeilen waeren
    zwei Aufrufe, und der zweite koennte den ersten ueberschreiben.

    Genannt wird sie nur, wenn sie nicht 0 ist: `transform,0` ist gueltig
    und bedeutet dasselbe wie nichts.
    """
    if not placement.enabled:
        return f"{placement.selector},disable"
    fields = [
        placement.selector,
        f"{placement.width}x{placement.height}@{number(placement.refresh)}",
        f"{placement.x}x{placement.y}",
        number(placement.scale),
    ]
    if placement.transform:
        fields += ["transform", str(placement.transform)]
    fields += list(placement.extra)
    return ",".join(fields)


HEADER = """\
# =========================================
# BILDSCHIRME
# Geschrieben von den ZepOS-Einstellungen, Seite "Bildschirme".
# =========================================
#
# Von Hand editieren geht - hyprland.conf sourcet diese Datei, und
# Hyprland liest sie beim Start und bei `hyprctl reload`. Was die Seite
# hinter dem Massstab findet (mirror, vrr, bitdepth), reicht sie
# unveraendert durch; sie loescht hier nichts, was sie nicht anbietet.
#
# Der Weg ueber die Seite hat eins, was das Editieren nicht hat: sie
# wendet auf Probe an und nimmt es nach {seconds} Sekunden ohne Antwort
# wieder zurueck - auch dann, wenn sie dabei abstuerzt. Eine falsche
# Zeile hier faellt erst bei der naechsten Anmeldung auf, und dann auf
# einem Schirm, der schwarz bleibt.
"""


def render(placements: Iterable[Placement]) -> str:
    """Die ganze Datei.

    Nach dem Anschlussnamen sortiert und nicht in der Reihenfolge, in der
    die Schirme angesteckt wurden: sonst unterscheidet sich die Datei
    zwischen zwei Laeufen an einem unveraenderten Schreibtisch, und ein
    `diff` auf einem gesicherten Profil zeigt eine Aenderung, die keine
    ist.
    """
    lines = [HEADER.format(seconds=CONFIRM_SECONDS)]
    for placement in sorted(placements, key=lambda item: item.name):
        lines.append(f"monitor={spec(placement)}")
    return "\n".join(lines) + "\n"


def write(placements: Iterable[Placement],
          where: Iterable[Path] | None = None) -> list[Path]:
    """Die Datei(en) schreiben, und sagen welche.

    Ueber eine Nachbardatei und os.replace(), wie settings.py und
    validate_output.py: ein Lauf, der zwischen zwei Zeilen abbricht,
    hinterliesse sonst eine halbe monitors.conf - und Hyprland liest sie
    beim naechsten Start als Konfigurationsfehler, also als Sitzung, die
    nicht hochkommt.
    """
    text = render(placements)
    written = []
    for target in (list(where) if where is not None else targets()):
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".neu")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
        written.append(target)
    return written


# --------------------------------------------------------------------
# Anordnen: einrasten und pruefen
# --------------------------------------------------------------------

def snap(placements: Iterable[Placement], name: str,
         distance: int = SNAP_DISTANCE) -> Placement:
    """Den genannten Schirm an die Kanten seiner Nachbarn ziehen.

    Betrachtet werden die vier Anlegungen, die einen Schreibtisch ohne
    Luecke ergeben - rechts an, links an, unter, ueber - und die zwei
    Ausrichtungen, die zwei Schirme buendig machen. Beide Achsen
    getrennt, weil ein Schirm rechts neben einem anderen stehen und
    gleichzeitig oben buendig sein soll; ein einziger Fangpunkt fuer
    beides koennte nur eins von beidem.

    UND DANN NOCH EINMAL HIN, WENN DABEI EINE UEBERLAPPUNG HERAUSKOMMT.

    GEMESSEN am 01.09.2026, und es ist die Ursache der Meldung "ich sehe
    seit dem anwenden alle sachen doppelt auf einem monitor":

        Zwei Schirme, 1920x1080 bei 0,0 und 1920x1080 bei 40,40.
        _snap_axis fand auf der x-Achse den Kandidaten "vorne buendig"
        (0, Abstand 40) und auf der y-Achse denselben (0, Abstand 40).
        Ergebnis: 0,0 - der gezogene Schirm lag EXAKT auf dem anderen.

    Die zwei buendigen Kandidaten sind AUSRICHTUNGEN und keine
    Anlegungen: "oben buendig" ist eine Aussage ueber die y-Achse, die
    erst dann etwas bedeutet, wenn die x-Achse ANLEGT. Getrennt
    gerechnet kann jede Achse fuer sich buendig ausfallen, und dann
    liegen beide Schirme aufeinander. Das Einrasten hat die Ueberlappung
    also nicht bloss durchgelassen - es hat sie ERZEUGT, und zwar genau
    dann, wenn jemand einen Schirm ungefaehr ueber einen anderen zieht.

    Deshalb wird das Ergebnis geprueft und noetigenfalls an die
    naechstgelegene KANTE des Schirms geschoben, den es trifft. Wer
    einen Schirm oben auf einen anderen zieht, bekommt ihn darueber -
    das ist, was er wollte, und nicht der Zustand, in dem sein
    Schreibtisch doppelt aussieht.

    Der Fangbereich gilt fuer das Ausweichen NICHT. Eine Ueberlappung
    ist eine Ueberlappung, auch 500 Pixel tief; `distance` sagt, wann
    zwei Kanten sich anziehen, und nicht, wann zwei Flaechen einander
    ausweichen duerfen.
    """
    placements = list(placements)
    moving = next(item for item in placements if item.name == name)
    if not moving.enabled:
        return moving

    others = [item for item in placements
              if item.name != name and item.enabled]

    x = _snap_axis(
        moving.x, moving.displayed_width,
        [(other.x, other.displayed_width) for other in others], distance)
    y = _snap_axis(
        moving.y, moving.displayed_height,
        [(other.y, other.displayed_height) for other in others], distance)
    return _stepped_aside(replace(moving, x=x, y=y), others)


def _hit(item: Placement, others: list[Placement]) -> Placement | None:
    """Der erste Schirm, auf dem dieser hier liegt - oder None."""
    for other in others:
        if (item.x < other.right and other.x < item.right
                and item.y < other.bottom and other.y < item.bottom):
            return other
    return None


def _stepped_aside(item: Placement, others: list[Placement]) -> Placement:
    """Denselben Schirm, aber neben und nicht auf seinen Nachbarn.

    Ausgewichen wird an die naechstgelegene der vier Kanten des Schirms,
    den er trifft: rechts daneben, links daneben, darunter, darueber.
    "Naechstgelegen" heisst hier "am wenigsten weit von der Stelle, an
    der er gerade liegt" - der Schirm rutscht also aus der Ueberdeckung
    heraus, statt an eine ausgesuchte Stelle zu springen.

    Die Schleife laeuft hoechstens so oft, wie es Nachbarn gibt, PLUS
    einmal: jeder Schritt legt den Schirm an einen Nachbarn an, und wenn
    er dabei auf den naechsten faellt, ist der schon abgearbeitet. Bleibt
    danach noch eine Ueberdeckung, wird rechts vom ganzen Schreibtisch
    angelegt - eine Stelle, die es immer gibt. Eine Schleife ohne Deckel
    waere ein Einstellungsfenster, das beim Ziehen stehenbleibt.
    """
    if not others:
        return item
    for _round in range(len(others) + 1):
        other = _hit(item, others)
        if other is None:
            return item
        item = min(
            (replace(item, x=other.right),
             replace(item, x=other.x - item.displayed_width),
             replace(item, y=other.bottom),
             replace(item, y=other.y - item.displayed_height)),
            key=lambda candidate: (abs(candidate.x - item.x)
                                   + abs(candidate.y - item.y)))
    if _hit(item, others) is None:
        return item
    return replace(item, x=max(other.right for other in others))


def _snap_axis(start: int, length: int,
               neighbours: list[tuple[int, int]], distance: int) -> int:
    """Eine Achse, und der naechstgelegene Fangpunkt darauf.

    Der NAECHSTE gewinnt, nicht der erste gefundene. Das ist der eine
    Punkt, an dem hier bewusst anders gerechnet wird als in der Vorlage:
    ihre Schleife bricht beim ersten Treffer ab (main.py:280-300), obwohl
    der Kommentar darueber "find nearest" sagt. Bei drei Schirmen
    nebeneinander liegen mehrere Kandidaten im Fangbereich, und "der
    erste in der Liste" ist die Reihenfolge, in der der Compositor seine
    Schirme aufzaehlt - also die Reihenfolge, in der die Kabel
    eingesteckt wurden.
    """
    best = start
    best_gap = distance
    for other_start, other_length in neighbours:
        for candidate in (
            other_start + other_length,             # rechts/unter anlegen
            other_start - length,                   # links/ueber anlegen
            other_start,                            # vorne buendig
            other_start + other_length - length,    # hinten buendig
        ):
            gap = abs(candidate - start)
            if gap <= best_gap:
                best_gap = gap
                best = candidate
    return best


def overlaps(placements: Iterable[Placement]) -> list[tuple[str, str]]:
    """Paare von Schirmen, die uebereinanderliegen.

    Hyprland nimmt das hin und rechnet den Schreibtisch trotzdem aus -
    was dabei herauskommt, ist ein Fenster, das auf zwei Schirmen halb zu
    sehen ist, oder ein Schirm, der ganz in einem anderen liegt und auf
    dem nie etwas aufgeht. Gemeldet und nicht verweigert: eine
    Ueberlappung ist fast immer ein Versehen, aber sie ist eine
    Anordnung, die man SEHEN und zuruecknehmen kann. Der Fall ohne
    Rueckweg steht in problems().
    """
    enabled = [item for item in placements if item.enabled]
    found = []
    for index, first in enumerate(enabled):
        for second in enabled[index + 1:]:
            if (first.x < second.right and second.x < first.right
                    and first.y < second.bottom and second.y < first.bottom):
                found.append(tuple(sorted((first.name, second.name))))
    return found


def blockers(placements: Iterable[Placement]) -> list[str]:
    """Was diese Anordnung wirklich VERBIETET, im Wortlaut.

    Genau ein Fall, und er ist der, aus dem es keinen Rueckweg gibt.
    Alles andere ist sichtbar und damit zuruecknehmbar und steht in
    remarks().

    GETRENNT SEIT DEM 01.09.2026, und die Trennung ist gemessen:
    settings/zepos_settings_gui/bridge.py hat bis dahin BEIDE Listen
    gleich behandelt und eine Ueberlappung abgelehnt, waehrend das
    GTK-Fenster sie nur gemeldet hat. Zwei Antworten auf dieselbe
    Anordnung waren eine zu viel - und die strengere kam ausgerechnet
    aus dem Fenster, das Schirme gar nicht verschieben kann.
    """
    if any(item.enabled for item in placements):
        return []
    return ["Kein Bildschirm bleibt an. Es gibt keinen Rückweg aus einem "
            "Schreibtisch ohne Bild: die Frage, ob man ihn behalten will, "
            "stünde auf keinem Schirm mehr."]


def remarks(placements: Iterable[Placement]) -> list[str]:
    """Was an dieser Anordnung auffaellt, ohne sie zu verbieten.

    Gemeldet und nicht verweigert, mit der Begruendung, die bei
    overlaps() steht: eine Ueberlappung ist fast immer ein Versehen,
    aber sie ist eine Anordnung, die man SIEHT und zuruecknehmen kann.
    """
    return [f"{first} und {second} liegen übereinander. Fenster gehen "
            "dann auf einem Schirm auf, der teilweise verdeckt ist."
            for first, second in overlaps(placements)]


def problems(placements: Iterable[Placement]) -> list[str]:
    """Was dieser Anordnung im Weg steht, im Wortlaut.

    Eine leere Liste heisst: nichts zu melden. Der Eintrag, der wirklich
    zaehlt, ist der erste - alles andere ist sichtbar und damit
    zuruecknehmbar.
    """
    placements = list(placements)
    return blockers(placements) + remarks(placements)


def normalised(placements: Iterable[Placement]) -> list[Placement]:
    """Den ganzen Schreibtisch so schieben, dass er bei 0,0 anfaengt.

    Hyprland nimmt negative Positionen entgegen, aber sie sind keine
    Aussage: der Schreibtisch ist ein Gitter ohne Ursprung, und "der
    linke Schirm steht bei -1920" bedeutet dasselbe wie "der rechte steht
    bei 1920". Ohne diese Normalisierung wanderten die Zahlen bei jedem
    Verschieben weiter ins Minus, und zwei Sitzungen, in denen dieselben
    zwei Schirme nebeneinanderstehen, haetten verschiedene
    monitors.conf-Dateien.

    Die ABGESCHALTETEN zaehlen nicht mit. Ein Schirm, der aus ist,
    nimmt keine Flaeche ein; liesse man ihn den Ursprung bestimmen, zoege
    ein abgeschalteter Schirm links aussen den ganzen sichtbaren
    Schreibtisch nach rechts.
    """
    placements = list(placements)
    enabled = [item for item in placements if item.enabled]
    if not enabled:
        return placements
    left = min(item.x for item in enabled)
    top = min(item.y for item in enabled)
    if not left and not top:
        return placements
    return [replace(item, x=item.x - left, y=item.y - top)
            for item in placements]


@dataclass
class Desk:
    """Der Schreibtisch, wie er ist, und wie er werden soll.

    Das Gegenstueck zu model.Draft der Einstellungs-Anwendung, und aus
    demselben Grund: waehrend jemand einen Schirm schiebt, laeuft er
    durch Dutzende Positionen, und jede davon anzuwenden waere ein
    Moduswechsel. Gesammelt wird hier, angewandt wird einmal.

    `original` ist der Stand beim Oeffnen. Er ist nicht nur fuer
    "geaendert?" da - er ist der Wiederherstellungsplan, den der Waechter
    bekommt, und damit die einzige Beschreibung des Zustands, in dem der
    Nutzer noch etwas sehen konnte.
    """

    outputs: tuple[Output, ...]
    placements: list[Placement]
    original: tuple[Placement, ...]

    @classmethod
    def load(cls, *, runner: Runner | None = None,
             options: dict[str, tuple[str, ...]] | None = None) -> "Desk":
        outputs = read_outputs(runner=runner)
        if options is None:
            options = read_trailing_options()
        layout = current_layout(outputs, options)
        return cls(outputs=tuple(outputs), placements=list(layout),
                   original=tuple(layout))

    def output(self, name: str) -> Output:
        return next(item for item in self.outputs if item.name == name)

    def get(self, name: str) -> Placement:
        return next(item for item in self.placements if item.name == name)

    def set(self, placement: Placement) -> None:
        """Einen Schirm ersetzen und den Schreibtisch neu ausrichten."""
        self.placements = normalised(
            placement if item.name == placement.name else item
            for item in self.placements)

    def change(self, name: str, **fields) -> None:
        self.set(replace(self.get(name), **fields))

    def move(self, name: str, x: int, y: int) -> None:
        """Einen Schirm an eine Stelle ziehen - und einrasten lassen.

        Eingerastet wird gegen die anderen an ihrer JETZIGEN Stelle, also
        nach dem Verschieben und vor dem Normalisieren. Andersherum
        gerechnet - erst normalisieren, dann einrasten - verschoebe das
        Normalisieren den gezogenen Schirm noch einmal, und er raste
        gegen eine Anordnung ein, die es nicht mehr gibt.
        """
        moved = [replace(item, x=int(x), y=int(y)) if item.name == name
                 else item
                 for item in self.placements]
        snapped = snap(moved, name)
        self.placements = normalised(
            snapped if item.name == name else item for item in moved)

    def changed(self) -> bool:
        return tuple(self.placements) != self.original

    def problems(self) -> list[str]:
        return problems(self.placements)


# --------------------------------------------------------------------
# Anwenden - und der Rueckweg
# --------------------------------------------------------------------

def apply_command(placements: Iterable[Placement]) -> list[str]:
    """Der EINE Aufruf, der eine ganze Anordnung setzt.

    `hyprctl --batch` und nicht ein Aufruf je Schirm, aus zwei Gruenden,
    von denen der zweite der wichtige ist:

      * Jeder einzelne Aufruf ist ein Moduswechsel, und jeder
        Moduswechsel ist ein Schwarzbild von bis zu zwei Sekunden. Drei
        Schirme waeren dreimal so lang dunkel wie noetig.
      * Der Rueckfall nimmt denselben Weg. Ein Rueckfall aus drei
        Aufrufen kann nach dem ersten unterbrochen werden und laesst dann
        eine Anordnung stehen, die es nie gab - halb alt, halb neu.

    Getrennt durch " ; ", weil hyprctl --batch daran trennt. Ein
    Semikolon kommt in keinem Feld einer `monitor=`-Zeile vor - Hyprland
    trennt die Felder mit Komma -, also kann kein Wert diese Trennung
    zerreissen.

    Wirft NoScreenLeft fuer eine Anordnung ohne eingeschalteten Schirm.
    Hier und nicht erst in der Oberflaeche, weil auch der Waechter durch
    diese Funktion geht: ein Wiederherstellungsplan, der alles abschaltet,
    waere ein Rueckfall in den Zustand, vor dem er schuetzen soll.
    """
    placements = list(placements)
    if not any(item.enabled for item in placements):
        raise NoScreenLeft(blockers(placements)[0])
    batch = " ; ".join(
        f"keyword monitor {spec(item)}"
        for item in sorted(placements, key=lambda item: item.name))
    return ["hyprctl", "--batch", batch]


def guard_plan(placements: Iterable[Placement],
               seconds: int = CONFIRM_SECONDS + GUARD_GRACE_SECONDS) -> dict:
    """Was der Waechter braucht, um genau diesen Stand wiederherzustellen.

    Der fertige BEFEHL und nicht die Anordnung: der Waechter soll im
    Ernstfall nichts mehr ausrechnen. Er laeuft dann moeglicherweise
    allein, weil das Programm, das ihn gestartet hat, gerade gestorben
    ist, und jede Zeile, die er zwischen dem Absturz und dem Bild noch
    ausfuehrt, ist eine Zeile, die auch scheitern kann.
    """
    return {"seconds": int(seconds),
            "command": apply_command(placements)}


def guard_command() -> list[str]:
    """Wie der Waechter gestartet wird.

    Erst auf PATH, dann neben diesem Modul. Der zweite Weg ist der
    Arbeitsbaum, in dem es kein installiertes Paket gibt; er nimmt
    ausdruecklich sys.executable, weil src/bin/zepos-displays-guard dort
    zwar ausfuehrbar ist, aber auf ein `python3` zeigt, das in der
    Umgebung eines Tests nicht auf PATH liegt.

    Wirft FileNotFoundError, wenn keiner von beiden da ist. Kein
    Rueckfall auf "dann eben ohne Waechter": ohne ihn wird hier nichts
    angewandt, und das ist die ganze Zusicherung dieser Seite.
    """
    found = shutil.which(GUARD_NAME)
    if found:
        return [found]
    local = Path(__file__).resolve().parent / "bin" / GUARD_NAME
    if local.is_file():
        return [sys.executable, str(local)]
    raise FileNotFoundError(
        f"{GUARD_NAME} ist weder auf PATH noch unter {local} zu finden. "
        "Ohne den Wächter gibt es keinen Rückfall, und ohne Rückfall "
        "wird hier nichts angewandt.")


def guard_log() -> Path:
    """Wohin der Waechter schreibt, was er getan hat.

    XDG_STATE_HOME und nicht XDG_RUNTIME_DIR, mit derselben Begruendung
    wie paths.user_state_root(): eine Sitzung, die nicht hochkommt, nimmt
    ihr Laufzeitverzeichnis beim Abmelden mit, und genau dann will jemand
    nachsehen, woran es lag.

    Nach einem Absturz ist diese Zeile das EINZIGE, was noch sagt, dass
    zurueckgestellt wurde - die Oberflaeche, die es sonst gesagt haette,
    gibt es dann nicht mehr.
    """
    return paths.user_state_root() / "displays-guard.log"


# Wie lange auf einen Waechter gewartet wird, der gerade zuruecknimmt.
#
# Grosszuegig, weil darin ein Moduswechsel steckt: `hyprctl --batch` gibt
# erst zurueck, wenn der Compositor die Schirme umgestellt hat, und ein
# DisplayPort-Monitor braucht dafuer Sekunden. Zu knapp bemessen hiesse,
# den Waechter mitten im Rueckweg abzuschiessen.
GUARD_WAIT_SECONDS = 60


class GuardRefused(RuntimeError):
    """Der Waechter ist nicht bereit geworden.

    Dann wird NICHT angewandt. Eine Anordnung ohne Rueckweg anzuwenden
    waere genau das, was diese ganze Vorrichtung verhindern soll - und
    ein "geht auch ohne" macht aus einer Zusicherung eine Gewohnheit.
    """


class ApplyFailed(RuntimeError):
    """`hyprctl` hat die Anordnung nicht angenommen."""


@dataclass(frozen=True)
class Outcome:
    """Wie der Versuch ausgegangen ist."""

    code: int
    report: str

    @property
    def kept(self) -> bool:
        return self.code == EXIT_KEPT


@dataclass
class Attempt:
    """Eine angewandte Anordnung, die noch nicht bestaetigt ist.

    Solange dieses Objekt lebt, laeuft ein Waechter mit. Wer es
    wegwirft, ohne keep() oder revert() gerufen zu haben, bekommt den
    Rueckfall trotzdem: die Pipe bricht, wenn der Prozess endet.
    """

    guard: subprocess.Popen
    applied: list[str]
    placements: tuple[Placement, ...]

    def keep(self) -> Outcome:
        """Behalten. Erst danach darf geschrieben werden."""
        return self._finish(GUARD_KEEP)

    def revert(self) -> Outcome:
        """Zuruecknehmen, jetzt."""
        return self._finish(GUARD_REVERT)

    def _finish(self, word: str) -> Outcome:
        """Das Wort schicken, die Pipe schliessen, auf das Ende warten.

        communicate() und nicht write()+wait(): es schliesst die Eingabe,
        liest die Ausgabe bis zum Ende und wartet, in einem Aufruf. Ein
        wait() ohne vorheriges Lesen kann an einer vollen Ausgabepipe
        haengenbleiben, und das waere ein Einstellungsfenster, das beim
        Bestaetigen einfriert.

        GEWARTET WIRD, und das ist Absicht. Ein revert() nimmt so lange,
        wie der Compositor fuer den Moduswechsel braucht; solange steht
        die Oberflaeche. Die Alternative - nicht warten - waere ein
        Fenster, das "zurueckgenommen" meldet, bevor irgendein Schirm
        sich bewegt hat.
        """
        try:
            output, _ = self.guard.communicate(input=word + "\n",
                                               timeout=GUARD_WAIT_SECONDS)
        except (subprocess.TimeoutExpired, BrokenPipeError, OSError, ValueError):
            self.guard.kill()
            output, _ = self.guard.communicate()
        return Outcome(self.guard.returncode, (output or "").strip())


def arm_and_apply(new: Iterable[Placement], previous: Iterable[Placement], *,
                  seconds: int = CONFIRM_SECONDS + GUARD_GRACE_SECONDS,
                  command: list[str] | None = None,
                  runner: Runner | None = None) -> Attempt:
    """Waechter scharfmachen, DANN anwenden. Nie andersherum.

    Die Reihenfolge ist die ganze Zusicherung dieser Seite:

      1. Der Waechter bekommt den Plan, mit dem er `previous`
         wiederherstellen kann, und meldet GUARD_READY.
      2. Erst dann laeuft `hyprctl --batch` mit `new`.

    Zwischen 1 und 2 gibt es keinen Moment, in dem etwas angewandt ist
    und niemand es zuruecknehmen kann. Wird der Waechter nicht bereit,
    wird gar nicht erst angewandt - GuardRefused, und der Aufrufer
    berichtet es.

    Schlaegt das Anwenden selbst fehl, wird sofort zurueckgenommen und
    ApplyFailed geworfen: `hyprctl --batch` meldet einen Fehler auch
    dann, wenn ein Teil der Zeilen schon durchgegangen ist, und ein halb
    angewandter Schreibtisch ist genau der Zustand, fuer den es den
    Waechter gibt.
    """
    new = list(new)
    previous = list(previous)
    plan = guard_plan(previous, seconds)
    apply_it = apply_command(new)

    process = subprocess.Popen(
        command if command is not None else guard_command(),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        # Eine eigene Sitzung, damit ein Signal an die Prozessgruppe der
        # Oberflaeche - ein Ctrl-C im Terminal, ein Fenstermanager, der
        # aufraeumt - den Waechter nicht mitnimmt. Er soll seinen Starter
        # ueberleben; das ist sein Beruf.
        start_new_session=True)

    try:
        process.stdin.write(json.dumps(plan) + "\n")
        process.stdin.flush()
        ready = (process.stdout.readline() or "").strip()
    except (BrokenPipeError, OSError) as problem:
        process.kill()
        raise GuardRefused(
            f"{GUARD_NAME} nahm den Plan nicht an: {problem}") from problem

    if ready != GUARD_READY:
        process.kill()
        process.communicate()
        raise GuardRefused(
            f"{GUARD_NAME} meldete {ready!r} statt {GUARD_READY!r}. Ohne "
            "einen bereiten Wächter wird nichts angewandt.")

    attempt = Attempt(guard=process, applied=apply_it,
                      placements=tuple(new))

    runner = runner or subprocess.run
    completed = runner(apply_it, capture_output=True, text=True)
    if completed.returncode != 0:
        outcome = attempt.revert()
        raise ApplyFailed(
            f"hyprctl endete mit {completed.returncode}: "
            f"{(completed.stderr or '').strip()}\n"
            f"Zurückgenommen: {outcome.report}")
    return attempt


# --------------------------------------------------------------------
# Der Waechter selbst
# --------------------------------------------------------------------

# Wie lange der Waechter auf seinen Plan wartet, bevor er aufgibt.
#
# Er meldet GUARD_READY erst, wenn er ihn hat, und die Oberflaeche wendet
# erst nach GUARD_READY an - ein Waechter, der ewig auf einen Plan
# wartet, der nie kommt, ist deshalb kein Sicherheitsproblem, sondern ein
# Prozess, der bis zum Abmelden stehenbleibt. Dreissig Sekunden sind
# reichlich fuer eine Zeile ueber eine Pipe.
ARMING_SECONDS = 30

# Womit er endet, wenn er nie einen Plan bekommen hat. Nichts wurde
# angewandt, also gibt es auch nichts zurueckzunehmen.
EXIT_NEVER_ARMED = 2


class _LineReader:
    """Zeilen von einem Dateideskriptor, mit Frist.

    Ueber os.read() und nicht ueber sys.stdin: ein gepufferter Leser
    kann Bytes schon geholt haben, die select() dann nicht mehr sieht -
    der Waechter wartete auf eine Antwort, die in seinem eigenen Puffer
    liegt, bis die Frist ablaeuft und er zurueckstellt. Das waere ein
    Rueckfall, den das Verfahren selbst ausloest.
    """

    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.buffer = b""
        self.closed = False

    def line(self, deadline: float) -> str | None:
        """Die naechste ganze Zeile, "" bei EOF, None wenn die Frist faellt."""
        import select
        import time

        while True:
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                text = self.buffer[:newline]
                self.buffer = self.buffer[newline + 1:]
                return text.decode("utf-8", "replace")
            if self.closed:
                return ""
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([self.fd], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(self.fd, 4096)
            if not chunk:
                self.closed = True
                # Und NICHT sofort "" zurueckgeben: im Puffer kann eine
                # letzte Zeile ohne Zeilenumbruch stehen. Ein "behalten"
                # ohne abschliessendes \n als EOF zu lesen hiesse,
                # zurueckzustellen, obwohl bestaetigt wurde.
                if self.buffer:
                    text, self.buffer = self.buffer, b""
                    return text.decode("utf-8", "replace")
                return ""
            self.buffer += chunk


def _say(text: str) -> None:
    """Eine Zeile an den Aufrufer, wenn es ihn noch gibt.

    Ein toter Aufrufer ist der Normalfall dieses Programms und kein
    Fehler: genau dann hat es etwas zu tun. Eine BrokenPipeError beim
    Berichten duerfte den Bericht nicht wichtiger machen als die Tat.

    Nach dem ersten Bruch wird die Ausgabe auf /dev/null umgehaengt.
    GEMESSEN am 12.08.2026: ohne das faengt zwar dieses `except` den
    Fehler, aber CPython leert sys.stdout beim Beenden NOCH EINMAL und
    schreibt dabei "Exception ignored while flushing sys.stdout:
    BrokenPipeError" nach stderr - eine Fehlermeldung ueber einen
    erfolgreichen Rueckfall, an genau der Stelle, an der jemand nach der
    Ursache sucht.
    """
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, OSError):
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass


def _note(reason: str) -> None:
    """Die eine Zeile ins Protokoll, die einen Absturz ueberlebt."""
    import datetime

    try:
        target = guard_log()
        target.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with target.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {reason}\n")
    except OSError:
        # Ein Protokoll, das nicht geschrieben werden kann, darf den
        # Rueckfall nicht aufhalten. Er ist die Aufgabe; das Protokoll
        # ist die Erklaerung hinterher.
        pass


def _tell_the_user(reason: str) -> None:
    """Sagen, dass zurueckgestellt wurde - falls jemand zuhoert.

    Ohne das flackert der Schirm einmal und stellt sich zurueck, und
    nichts sagt warum. `notify-send` und nicht mehr: es liegt bei
    libnotify, das zepos-desktop ohnehin nennt, und wenn es fehlt,
    passiert eben nichts. Der Rueckfall haengt nicht daran.
    """
    found = shutil.which("notify-send")
    if not found:
        return
    try:
        subprocess.run(
            [found, "--urgency=critical", "--app-name=ZepOS",
             "Bildschirme zurückgestellt", reason],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def _revert(command: list[str], code: int, reason: str) -> int:
    """Den alten Stand wiederherstellen, und es hinterlassen."""
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=30)
        outcome = ("wiederhergestellt" if completed.returncode == 0
                   else f"FEHLGESCHLAGEN ({completed.returncode}): "
                        f"{(completed.stderr or '').strip()}")
    except (OSError, subprocess.SubprocessError) as problem:
        outcome = f"FEHLGESCHLAGEN: {problem}"
    _note(f"{reason} - {outcome}")
    _say(f"{reason} - {outcome}")
    _tell_the_user(reason)
    return code


def guard_main(argv: list[str] | None = None) -> int:
    """Der Waechter: ein Plan, eine Frist, ein Rueckweg.

    Er liest EINE Zeile JSON von der Standardeingabe -
    `{"seconds": 20, "command": ["hyprctl", "--batch", "..."]}` -, meldet
    GUARD_READY, und wartet dann auf genau eins von drei Dingen:

        GUARD_KEEP      die Anordnung bleibt; er endet, ohne etwas zu tun
        GUARD_REVERT    zuruecknehmen, jetzt
        nichts          Frist abgelaufen oder Pipe gebrochen -> zuruecknehmen

    WARUM DER PLAN UEBER DIE PIPE KOMMT UND NICHT ALS ARGUMENT
        Weil eine Kommandozeile in `ps` steht. Der Plan ist harmlos, aber
        die Pipe ist ohnehin da und wird gebraucht - und ein Argument
        haette den zweiten Zweck nicht: die Pipe IST die Verbindung, an
        deren Bruch der Absturz erkannt wird.

    WARUM SIGHUP IGNORIERT WIRD
        Der Waechter ueberlebt seinen Starter mit Absicht. Stirbt der,
        kann sein Terminal oder seine Sitzung ein SIGHUP hinterherschicken
        - und ein Waechter, der daran stirbt, waere genau in dem Moment
        weg, in dem er gebraucht wird.
    """
    import signal
    import time

    argv = sys.argv[1:] if argv is None else list(argv)
    if argv:
        print(f"usage: {GUARD_NAME}\n"
              "Dieses Programm nimmt keine Schalter entgegen. Es liest "
              "seinen Plan als eine Zeile JSON von der Standardeingabe; "
              "src/displays.py beschreibt das Verfahren.", file=sys.stderr)
        return 64

    for name in ("SIGHUP", "SIGPIPE"):
        handler = getattr(signal, name, None)
        if handler is not None:
            signal.signal(handler, signal.SIG_IGN)

    reader = _LineReader(sys.stdin.fileno())

    first = reader.line(time.monotonic() + ARMING_SECONDS)
    if not first:
        _say("kein Plan")
        return EXIT_NEVER_ARMED
    try:
        plan = json.loads(first)
        seconds = float(plan["seconds"])
        command = [str(part) for part in plan["command"]]
    except (ValueError, TypeError, KeyError) as problem:
        print(f"{GUARD_NAME}: unlesbarer Plan: {problem}", file=sys.stderr)
        return EXIT_NEVER_ARMED
    if not command:
        print(f"{GUARD_NAME}: der Plan nennt keinen Befehl", file=sys.stderr)
        return EXIT_NEVER_ARMED

    # ERST JETZT. Die Oberflaeche wartet auf dieses Wort und wendet
    # nichts an, bevor es da ist - das ist die Zusicherung, dass es
    # keinen Moment gibt, in dem eine Anordnung angewandt ist und
    # niemand sie zuruecknehmen kann.
    _say(GUARD_READY)

    deadline = time.monotonic() + seconds
    while True:
        answer = reader.line(deadline)
        if answer is None:
            return _revert(
                command, EXIT_REVERTED_DEADLINE,
                f"Keine Bestätigung binnen {number(seconds)} Sekunden")
        if answer == "":
            return _revert(
                command, EXIT_REVERTED_BROKEN_PIPE,
                "Die Einstellungen sind beendet worden, bevor die "
                "Anordnung bestätigt war")
        answer = answer.strip()
        if answer == GUARD_KEEP:
            _say(GUARD_KEEP)
            return EXIT_KEPT
        if answer == GUARD_REVERT:
            return _revert(command, EXIT_REVERTED_ON_REQUEST,
                           "Auf Wunsch zurückgenommen")
        # Eine Zeile, die keins von beidem ist, wird ueberlesen. Ein
        # Waechter, der bei einem Tippfehler auf der Pipe zurueckstellt,
        # macht aus einem Verstaendigungsfehler einen Moduswechsel.
