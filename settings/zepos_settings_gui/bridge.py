# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Einstellungen als EIN JSON-Dokument, fuer eine Oberflaeche, die kein GTK ist.

WOFUER ES DAS GIBT, MIT DATUM
    GEFORDERT am 18.08.2026: "ich will auch fuer unsere einstellungen
    ein komplett eigenes ags fenster dafuer mit farben und alles drum
    und dran". Geliefert war bis dahin dieses GTK4-Fenster, und es hatte
    neue Farben bekommen - nicht das, was dastand.

    Ein AGS-Fenster ist TypeScript. Die Frage, die vor dem ersten
    Widget beantwortet werden muss, ist deshalb nicht "wie sieht es
    aus", sondern "woher weiss es, was es anbietet". Es gibt genau zwei
    Antworten:

      nachbauen   Die 559 Platzhalter, die 50 Groessen, die Grenzen der
                  fuenf Ausnahmen, die 69 Farben mit ihren
                  Vorgabewerten, die Regel, wann eine Leistenhaelfte
                  als "wie ausgeliefert" gilt, und die Frage, ob dieses
                  Konto /etc/zepos schreiben darf - alles noch einmal,
                  in einer zweiten Sprache. Das ist CONTRIBUTING.md
                  Regel 2 in ihrer reinsten Form: kein Wert, den eine
                  Vorlage tragen koennte, wird fest verdrahtet.
      fragen      Diese Datei.

    Also zeichnet AGS, und model.py bleibt das Hirn. Was hier steht,
    ist die Naht: model.py hinein, JSON heraus, JSON hinein, model.py
    heraus. Eine Entscheidung faellt in dieser Datei nicht - jede Zahl,
    jede Grenze, jeder Vorgabewert und jede Ablehnung kommt aus
    model.py, settings.py, sizes.py, brand.py, theme.py oder update.py.

WARUM DAS EIN SCHALTER VON zepos-settings-gui IST UND KEIN EIGENER BEFEHL
    GEMESSEN am 19.08.2026 an den zwei Rezepten, die dafuer in Frage
    kommen:

      packaging/zepos-config/PKGBUILD   `install -Dm755 -t $pkgdir/usr/bin`
                                        mit SIEBEN namentlich genannten
                                        Dateien. Und /usr/share/zepos
                                        traegt settings/ nicht - ein
                                        Befehl dort koennte model.py
                                        gar nicht importieren.
      packaging/zepos-settings-gui/     `install -Dm755 .../bin/zepos-
      PKGBUILD                          settings-gui` - EINE namentlich
                                        genannte Datei. Das
                                        Modulverzeichnis dagegen kommt
                                        ueber `zepos_settings_gui/*.py`,
                                        also als Glob.

    Eine neue Datei in bin/ laege damit im Tarball (packaging/build.sh
    rsync't ganz settings/) und NICHT im Paket - "ein Befehl, der im
    Baum laeuft und im Paket fehlt, ist kein Befehl". Eine neue Datei
    neben dieser hier liegt durch den Glob im Paket, ohne dass ein
    Rezept angefasst werden muss.

    Und der Vorschalter, den es schon gibt, ist genau der richtige: er
    legt BEIDE Wurzeln auf den Suchpfad (/usr/share/zepos-settings-gui
    und /usr/share/zepos), er bricht mit einer Erklaerung ab, wenn eine
    davon fehlt, und zepos-config ist seine harte Abhaengigkeit. Ein
    zweiter Befehl waere ein zweites Mal dieselben 40 Zeilen.

DIE AUFRUFFORM IST DIE VON zepos-settings, ABSICHTLICH
    zepos-settings-gui --json get           liest
    zepos-settings-gui --json set DOKUMENT  schreibt ("-" liest stdin)
    zepos-settings-gui --json apply         erzeugt neu

    get/set und dieselben Schluessel: `sizes.scale`, `colors.accent`,
    `weather.location`, `bar.modules_left`, `theme`, `update.enabled`.
    Das ist KEINE Aehnlichkeit, sondern derselbe Namensraum - wer im
    Fenster etwas verstellt und danach `zepos-settings get sizes.scale`
    tippt, sieht denselben Schluessel. Ein eigener Namensraum
    ("size.factor", "page.groesse.regler") waere eine zweite Sprache
    fuer dieselben Werte und damit die Uebersetzungstabelle, die als
    erste veraltet.

DIE RUECKGABEWERTE, UND WARUM STDOUT IMMER JSON IST
    0   getan
    1   abgelehnt oder fehlgeschlagen - stdout traegt {"ok": false,
        "problems": [...]}
    2   die Schalter sind keine - USAGE auf stderr, wie in cli.py

    Die 1 traegt ihre Begruendung als JSON und nicht als Satz auf
    stderr, weil der Aufrufer eine Oberflaeche ist: sie muss die Klage
    ANZEIGEN und nicht nur weiterreichen, und ein Fenster, das deutsche
    Prosa aus einem Fehlerstrom fischt, liest beim naechsten Wortlaut
    das Falsche. Die 2 ist die Ausnahme und folgt cli.py: falsche
    Schalter tippt ein Mensch, kein Fenster.

WAS EIN set NICHT TUT: ANWENDEN
    Dieselbe Antwort wie im Fenster, und aus demselben Grund - der Kopf
    von model.py fuehrt sie in ganzer Laenge: gespeichert wird sofort,
    dabei faellt paths.session_regenerate_marker(), und wer nicht bis
    zur naechsten Anmeldung warten will, ruft `--json apply`. Ein set,
    das von sich aus erzeugt, beendet die Leiste des Nutzers, waehrend
    er einen Regler zieht.

WAS EIN set ENTWEDER GANZ ODER GAR NICHT TUT
    Erst wird JEDER Schluessel geprueft, dann wird geschrieben. Eine
    Ablehnung mitten in einem Dokument mit zwanzig Farben darin waere
    ein halb angewandtes Dokument - genau der Zustand, gegen den
    settings.merge() geschrieben wurde.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

import brand
import displays
import paths
import settings as settings_file
import sizes
import theme
import update

from . import model

# Die Fassung dieses Vertrags. Sie steht IM Dokument, weil das Fenster
# aelter oder juenger sein kann als der Befehl: ein AGS-Fenster wird von
# zepos-config ausgeliefert, dieser Befehl von zepos-settings-gui, und
# das sind zwei Pakete, die einzeln aktualisiert werden.
SCHEMA = 1

# Wem ein Wert gehoert. Der Unterschied ist keine Beschriftung: was der
# MASCHINE gehoert, wird beim Verstellen SOFORT geschrieben, notfalls
# durch pkexec, und haengt an keinem Speichern-Knopf.
ACCOUNT = "konto"
MACHINE = "maschine"
DESKTOP = "schreibtisch"

# Die Arten von Bedienelement, die dieses Dokument kennt. Eine
# geschlossene Liste, damit ein Fenster fuer jede genau einen Zeichner
# hat und ein unbekanntes `kind` ein Fehler ist und keine leere Zeile.
NUMBER = "zahl"
SWITCH = "schalter"
TEXT = "text"
CHOICE = "auswahl"
COLOUR = "farbe"
ORDER = "reihenfolge"
LAYOUT = "anordnung"

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Die Schluessel-Praefixe, die set() auseinanderhaelt.
SIZES_SCALE = f"{sizes.SECTION}.scale"
SIZES_MOTION = f"{sizes.SECTION}.{sizes.MOTION_ENABLED}"
SIZES_VALUE = f"{sizes.SECTION}.values."
COLOUR_PREFIX = "colors."
WEATHER_KEY = "weather.location"
BAR_PREFIX = f"{settings_file.BAR}."
THEME_KEY = "theme"
UPDATE_PREFIX = "update."

# Die vier Aktualisierungsschluessel, die model.py anbietet, mit der
# Pruefung, die ihr Wert bestehen muss. update.validate() prueft sie
# beim Schreiben noch einmal; das hier ist die Ablehnung VOR dem
# Schreiben, damit ein Dokument mit einem falschen Wert darin gar nicht
# erst halb angewandt wird.
UPDATE_CHOICES: dict[str, dict[str, str]] = {
    model.UPDATE_SCOPE: model.UPDATE_SCOPE_LABELS,
    model.UPDATE_NOTIFY: model.UPDATE_NOTIFY_LABELS,
    model.UPDATE_INTERVAL: model.UPDATE_INTERVAL_LABELS,
}

USAGE = """usage: zepos-settings-gui --json get
       zepos-settings-gui --json set <dokument>|-
       zepos-settings-gui --json apply

get   schreibt den Zustand aller sieben Seiten als ein JSON-Dokument.
set   nimmt ein Objekt {schluessel: wert} entgegen - dieselben
      Schluessel, die `get` in jedem Bedienelement unter "key" nennt,
      also dieselben wie bei `zepos-settings set`. "-" liest stdin.
apply laesst zepos-generate --all laufen und raeumt die Marke weg."""


# --------------------------------------------------------------------
# Ein Bedienelement
# --------------------------------------------------------------------

def _control(key: str, kind: str, label: str, value: Any, **rest: Any) -> dict:
    """Die Felder, die JEDES Bedienelement traegt, plus die eigenen.

    WARUM SIE ALLE IMMER DASTEHEN, AUCH LEER
        Weil ein Fenster sonst je Art einen anderen Zugriff braucht und
        `control.note ?? ""` an sechzig Stellen steht. Ein fehlendes
        Feld und ein leeres Feld sind in JavaScript dasselbe, bis
        jemand `Object.keys()` darueber laufen laesst - und dann sind
        es zwei Formen desselben Bedienelements.

    `writable` ist das Feld, um dessentwillen es diese Funktion gibt.
    theme_writable() und update_writable() antworten auf einer
    Installation "nein", und ein Fenster, das trotzdem einen Schalter
    anbietet, luegt den Nutzer an: er legt ihn um, nichts passiert, und
    er sucht den Fehler bei sich. Steht er auf false, gehoert `reason`
    daneben und `command` sagt, wie es von Hand ginge.
    """
    control = {
        "key": key,
        "kind": kind,
        "label": label,
        "note": "",
        "value": value,
        "default": None,
        "scope": ACCOUNT,
        # Ob ein Verstellen sofort wirkt oder erst beim naechsten `set`
        # mit anschliessendem Erzeugungslauf ankommt. Thema und
        # Aktualisierung sind sofort - sie haengen an keinem Entwurf.
        "immediate": False,
        "writable": True,
        "reason": "",
        # Der Befehl OHNE seinen letzten Teil, den Wert. Aus
        # model.theme_elevated_command() beziehungsweise
        # update_elevated_command() und nicht getippt, damit hier nicht
        # eine zweite Fassung derselben Befehlszeile steht.
        "command": [],
    }
    control.update(rest)
    return control


def _page(name: str, controls: list[dict], note: str = "") -> dict:
    label, icon = next((title, icon) for page, title, icon in model.PAGES
                       if page == name)
    return {"name": name, "label": label, "icon": icon, "note": note,
            "controls": controls}


# --------------------------------------------------------------------
# Die sieben Seiten
# --------------------------------------------------------------------

def _scale_free(draft: model.Draft, name: str) -> float:
    """Was diese Groesse waere, wenn sie wieder dem Regler folgte.

    Durch Draft.current_size() und nicht durch eine eigene Rechnung:
    die Frage "was macht der Faktor aus diesem Namen" ist dort schon
    beantwortet, einschliesslich der Sprosse, der Einheit und der
    Rundung. Der Entwurf wird dafuer kurz auf None gestellt und danach
    zurueckgelegt - eine Kopie des ganzen Entwurfs waere dieselbe
    Rechnung mit mehr Zeilen.
    """
    keep = draft.values.get(name, ...)
    draft.values[name] = None
    try:
        return draft.current_size(name)
    finally:
        if keep is ...:
            draft.values.pop(name, None)
        else:
            draft.values[name] = keep


def _page_groesse(draft: model.Draft) -> dict:
    controls = [_control(
        SIZES_SCALE, NUMBER, model.LABEL_SCALE, draft.current_scale(),
        default=sizes.SCALE_DEFAULT,
        minimum=model.SCALE_MINIMUM, maximum=model.SCALE_MAXIMUM,
        step=model.SCALE_STEP, digits=2, unit="")]

    for dial in model.DIALS:
        controls.append(_control(
            f"{SIZES_VALUE}{dial.name}", NUMBER, dial.label,
            draft.current_size(dial.name),
            note=dial.note,
            default=_scale_free(draft, dial.name),
            minimum=dial.minimum, maximum=dial.maximum,
            step=1, digits=0, unit=sizes.TABLE[dial.name].unit,
            # Der ganze Sinn der fuenf Ausnahmen: eine 24 kann heissen
            # "der Faktor hat 24 daraus gemacht" oder "hier steht fest
            # eine 24". null als Wert setzt sie wieder auf den Faktor.
            follows_scale=draft.follows_scale(dial.name)))

    controls.append(_control(
        SIZES_MOTION, SWITCH, model.LABEL_MOTION, draft.current_motion(),
        default=sizes.motion_enabled({})))
    return _page("groesse", controls)


def _page_bildschirme(*, runner=None) -> dict:
    """Was der Compositor gerade zeigt - zum LESEN.

    WARUM HIER NICHTS EINGESTELLT WIRD, OBWOHL DIE SEITE ES KANN
        displays.arm_and_apply() macht einen Waechter scharf, wendet
        dann an und gibt einen Attempt zurueck, der einen LAUFENDEN
        Kindprozess haelt: entweder bestaetigt jemand innerhalb von
        displays.CONFIRM_SECONDS Sekunden, oder der Waechter stellt die
        alte Anordnung wieder her. Genau deshalb ist er ein eigener
        Prozess - ein Zeitgeber im Programm stirbt mit ihm, und der
        schwarze Schirm bliebe.

        Ein einmaliger Befehl, der nach seiner Ausgabe endet, kann
        diesen Prozess nicht halten. Er wuerde anwenden und sterben,
        der Waechter naehme zurueck, und die Oberflaeche haette einen
        Schalter, der nachweislich nichts bewirkt. Also steht die
        Anordnung hier zum Lesen, und das Anwenden bleibt bei dem, was
        laufen bleibt.
    """
    try:
        outputs = displays.read_outputs(runner=runner)
        layout = displays.current_layout(
            outputs, displays.read_trailing_options())
        available, reason = True, ""
    except (RuntimeError, OSError, ValueError) as problem:
        layout, available, reason = [], False, str(problem)

    control = _control(
        "displays.layout", LAYOUT, "Anordnung der Bildschirme",
        [{"name": place.name, "selector": place.selector,
          "enabled": place.enabled,
          "width": place.width, "height": place.height,
          "refresh": place.refresh, "x": place.x, "y": place.y,
          "scale": place.scale, "transform": place.transform,
          "extra": list(place.extra)}
         for place in layout],
        scope=DESKTOP, immediate=True, writable=False,
        reason=reason or (
            f"Eine Anordnung wird ueber {displays.GUARD_NAME} angewandt, "
            f"der {displays.CONFIRM_SECONDS} Sekunden auf eine "
            f"Bestaetigung wartet und sonst zuruecknimmt. Dieser Befehl "
            f"endet mit seiner Ausgabe und koennte den Waechter nicht "
            f"halten - angewandt wird deshalb aus einem Programm, das "
            f"laufen bleibt."),
        available=available,
        # Nicht user-settings.json, und das ist der Grund, aus dem diese
        # Seite am Speichern-Knopf des Fensters nicht haengt.
        target=str(displays.config_path()),
        profile=displays.current_profile())
    return _page("bildschirme", [control])


def _page_leiste(draft: model.Draft) -> dict:
    shipped, labels, say = model.shipped_bar()
    controls = []
    for key, label, note in model.BAR_SIDES:
        chosen = draft.current_bar(key)
        placeable = model.placeable_in(shipped, key)
        effective, discarded = settings_file.bar_order(
            chosen, placeable, shipped[key])
        controls.append(_control(
            f"{BAR_PREFIX}{key}", ORDER, label, chosen,
            note=note,
            # null heisst "wie ausgeliefert" und ist eine ANGABE, keine
            # Abwesenheit - siehe model.bar_stored(). Deshalb steht die
            # ausgelieferte Liste daneben und nicht an Stelle des Werts.
            default=shipped[key],
            placeable=placeable,
            labels=labels if key == settings_file.BAR_PINS else {},
            effective=effective,
            discarded=[{"name": name, "why": why} for name, why in discarded]))
    return _page("leiste", controls, note=say)


def _page_thema() -> dict:
    writable = model.theme_writable()
    names = model.theme_names()
    control = _control(
        THEME_KEY, CHOICE, model.LABEL_THEME, model.current_theme(),
        note=model.THEME_TIMING,
        default=theme.DEFAULT,
        options=[{"value": name, "label": model.theme_label(name),
                  "note": model.theme_description(name)} for name in names],
        scope=MACHINE, immediate=True, writable=writable,
        reason="" if writable else (
            "Das Thema gehoert der Maschine und nicht diesem Konto, weil "
            "der Anmeldebildschirm dazugehoert. Beim Wechseln wird nach "
            "Rechten gefragt."),
        command=model.theme_elevated_command(theme.DEFAULT)[:-1])
    return _page("thema", [control])


def _page_farben(draft: model.Draft) -> dict:
    controls = []
    for group, rows in brand.COLOR_GROUPS:
        for key, label in rows:
            controls.append(_control(
                f"{COLOUR_PREFIX}{key}", COLOUR, label,
                draft.current_colour(key),
                default=model.colour_default(key),
                # Die Gruppe steht am Bedienelement und nicht als eigene
                # Ebene darueber: eine zweite Verschachtelung nur fuer
                # die Farben haette das Fenster gezwungen, diese eine
                # Seite anders zu lesen als die sechs anderen.
                group=group))
    return _page("farben", controls)


def _page_wetter(draft: model.Draft) -> dict:
    stored = settings_file.defaults().get("weather")
    control = _control(
        WEATHER_KEY, TEXT, model.LABEL_WEATHER, draft.current_weather(),
        default=stored.get("location", "") if isinstance(stored, dict) else "")
    return _page("wetter", [control])


def _page_aktualisierung() -> dict:
    try:
        config = update.load()
    except (ValueError, OSError) as problem:
        return _page("aktualisierung", [], note=str(problem))

    writable = model.update_writable()
    reason = "" if writable else (
        "Diese Einstellung gehoert der Maschine und nicht diesem Konto: "
        "der Dienst laeuft, bevor sich jemand angemeldet hat. Beim "
        "Verstellen wird nach Rechten gefragt.")
    shipped = update.defaults()

    def machine(key: str, kind: str, label: str, value: Any, **rest: Any) -> dict:
        return _control(f"{UPDATE_PREFIX}{key}", kind, label, value,
                        scope=MACHINE, immediate=True, writable=writable,
                        reason=reason,
                        command=model.update_elevated_command(key, None)[:-1],
                        **rest)

    controls = [machine(
        model.UPDATE_ENABLED, SWITCH,
        model.UPDATE_LABELS[model.UPDATE_ENABLED],
        bool(config.get(model.UPDATE_ENABLED)),
        default=bool(shipped.get(model.UPDATE_ENABLED)))]

    for key, labels in UPDATE_CHOICES.items():
        controls.append(machine(
            key, CHOICE, model.UPDATE_LABELS[key],
            _dotted(config, key),
            default=_dotted(shipped, key),
            options=[{"value": name, "label": text}
                     for name, text in labels.items()]))
    return _page("aktualisierung", controls)


def _dotted(document: dict, key: str) -> Any:
    """`schedule.interval` in einem verschachtelten Dokument nachschlagen.

    update.set_value() nimmt genau diese Schreibweise entgegen, also
    liest sie hier auch so - eine Auswahl, deren Schluessel beim Lesen
    anders heisst als beim Schreiben, ist zwei Schluessel.
    """
    value: Any = document
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


# --------------------------------------------------------------------
# Lesen
# --------------------------------------------------------------------

def state(draft: model.Draft, *, runner=None) -> dict:
    """Alle sieben Seiten, in der Reihenfolge von model.PAGES."""
    return {
        "schema": SCHEMA,
        "ok": True,
        "problems": [],
        "settings_file": str(paths.user_root() / settings_file.FILENAME),
        # Leer, wenn es kein pkexec gibt. Dann bleibt bei einer
        # Maschineneinstellung nur der Befehl zum Abtippen, und das
        # Fenster soll das sagen koennen, BEVOR jemand einen Schalter
        # umlegt.
        "elevator": model.elevator(),
        "pending_regenerate": model.marker_path().exists(),
        "cost": {"generate": model.GENERATE_COST,
                 "theme": model.THEME_TIMING},
        "pages": [
            _page_groesse(draft),
            _page_bildschirme(runner=runner),
            _page_leiste(draft),
            _page_thema(),
            _page_farben(draft),
            _page_wetter(draft),
            _page_aktualisierung(),
        ],
    }


# --------------------------------------------------------------------
# Schreiben
# --------------------------------------------------------------------

def _number(key: str, value: Any, low: float, high: float,
            problems: list[str]) -> float | None:
    """Eine Zahl in ihren Grenzen, oder eine Klage.

    DIE GRENZEN WERDEN HIER GEPRUEFT UND NICHT IN model.py, UND DAS IST
    KEIN ZWEITER SATZ REGELN: die Zahlen kommen aus model.SCALE_MINIMUM
    und Dial.minimum/maximum. Im Fenster hielt sie eine
    Gtk.Adjustment - ein Aufrufer ueber JSON hat keine, und
    sizes.value_of() nimmt jede Zahl entgegen. Ohne diese Zeilen waere
    `{"sizes.scale": 40}` eine Seitenleiste, die breiter ist als der
    Schirm, und der Rueckweg fuehrte durch das Editieren der Datei -
    also durch genau das, wofuer es diese Oberflaeche gibt.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(f"{key}: {_kind(value)} ist keine Zahl")
        return None
    if not low <= value <= high:
        problems.append(f"{key}: {value} liegt nicht zwischen {low} und {high}")
        return None
    return float(value)


def _kind(value: Any) -> str:
    return settings_file.JSON_TYPES.get(type(value), type(value).__name__)


def _plan(changes: dict[str, Any], draft: model.Draft,
          problems: list[str]) -> list[tuple[str, Any]]:
    """Jede Aenderung pruefen und in den Entwurf legen; Maschinenwerte merken.

    Zurueck kommen die Schluessel, die NICHT in den Entwurf gehen -
    Thema und Aktualisierung, die der Maschine gehoeren und einzeln
    geschrieben werden. Der Rest liegt danach im Entwurf und geht mit
    einem einzigen settings.merge() hinaus.
    """
    machine: list[tuple[str, Any]] = []
    dials = {dial.name: dial for dial in model.DIALS}

    for key, value in changes.items():
        if key == SIZES_SCALE:
            number = _number(key, value, model.SCALE_MINIMUM,
                             model.SCALE_MAXIMUM, problems)
            if number is not None:
                draft.scale = number

        elif key == SIZES_MOTION:
            if not isinstance(value, bool):
                problems.append(f"{key}: {_kind(value)} ist kein Schalter")
            else:
                draft.motion = value

        elif key.startswith(SIZES_VALUE):
            name = key[len(SIZES_VALUE):]
            dial = dials.get(name)
            if dial is None:
                problems.append(
                    f"{key}: diese Oberflaeche bietet nur "
                    f"{', '.join(sorted(dials))} an. Die uebrigen "
                    f"{len(sizes.TABLE) - len(dials)} Groessen stehen in "
                    f"`zepos-settings get sizes` und `user_settings.py "
                    f"list-sizes`.")
            elif value is None:
                draft.clear_dial(dial)
            else:
                number = _number(key, value, dial.minimum, dial.maximum,
                                 problems)
                if number is not None:
                    draft.set_dial(dial, number)

        elif key.startswith(COLOUR_PREFIX):
            name = key[len(COLOUR_PREFIX):]
            if name not in brand.COLORS:
                problems.append(f"{key}: diese Farbe gibt es nicht")
            elif not isinstance(value, str) or not HEX.match(value):
                problems.append(f"{key}: {value!r} ist kein #rrggbb")
            else:
                # Buchstabe fuer Buchstabe so, wie er hereinkam. Weder
                # gross noch klein geschrieben: brand.COLORS traegt
                # Grossbuchstaben, model.hex_of() schreibt kleine, und
                # eine dritte Regel hier hiesse, dass ein `set` auf den
                # ausgelieferten Wert etwas anderes in die Datei legt
                # als der ausgelieferte Wert - "unveraendert" saehe
                # dann wie eine Aenderung aus.
                draft.colours[name] = value

        elif key == WEATHER_KEY:
            if not isinstance(value, str):
                problems.append(f"{key}: {_kind(value)} ist kein Ortsname")
            else:
                draft.weather = value

        elif key.startswith(BAR_PREFIX):
            _plan_bar(key[len(BAR_PREFIX):], key, value, draft, problems)

        elif key == THEME_KEY:
            if value not in theme.THEMES:
                problems.append(
                    f"{key}: {value!r} ist keins von "
                    f"{', '.join(sorted(theme.THEMES))}")
            else:
                machine.append((key, value))

        elif key.startswith(UPDATE_PREFIX):
            _plan_update(key[len(UPDATE_PREFIX):], key, value, machine,
                         problems)

        else:
            problems.append(
                f"{key}: kein Schluessel dieser Oberflaeche. `--json get` "
                f"nennt jeden, den es gibt.")

    return machine


def _plan_bar(half: str, key: str, value: Any, draft: model.Draft,
              problems: list[str]) -> None:
    """Eine Leistenhaelfte, gegen die Regeln von settings.py geprueft.

    settings.bar_order() und nicht eine eigene Pruefung: der Erzeuger
    verwirft nach genau dieser Funktion, und eine Oberflaeche, die einen
    Namen annimmt, den die Leiste danach wegwirft, ist die Leiste, die
    anders dasteht als das Fenster, in dem man sie eingestellt hat.

    Abgelehnt statt still verworfen, anders als beim Erzeugen: dort ist
    die Liste schon gespeichert und der Nutzer nicht mehr da. Hier
    steht er davor und kann es richtigstellen.
    """
    if half not in settings_file.BAR_KEYS:
        problems.append(f"{key}: es gibt {', '.join(settings_file.BAR_KEYS)}")
        return
    if value is None:
        draft.reset_bar(half)
        return
    if not isinstance(value, list) or any(not isinstance(n, str) for n in value):
        problems.append(
            f"{key}: erwartet wird eine Liste von Namen oder null fuer "
            f"die ausgelieferte Reihenfolge")
        return

    shipped, _labels, _say = model.shipped_bar()
    _kept, discarded = settings_file.bar_order(
        list(value), model.placeable_in(shipped, half), shipped[half])
    if discarded:
        problems.append(settings_file.bar_complaint(half, discarded))
        return
    draft.set_bar(half, list(value))


def _plan_update(name: str, key: str, value: Any,
                 machine: list[tuple[str, Any]], problems: list[str]) -> None:
    if name == model.UPDATE_ENABLED:
        if not isinstance(value, bool):
            problems.append(f"{key}: {_kind(value)} ist kein Schalter")
        else:
            machine.append((key, value))
        return
    labels = UPDATE_CHOICES.get(name)
    if labels is None:
        problems.append(
            f"{key}: diese Oberflaeche bietet "
            f"{', '.join(UPDATE_PREFIX + n for n in [model.UPDATE_ENABLED, *UPDATE_CHOICES])} "
            f"an. `zepos-update --help` nennt die uebrigen.")
    elif value not in labels:
        problems.append(f"{key}: {value!r} ist keins von "
                        f"{', '.join(labels)}")
    else:
        machine.append((key, value))


def write(changes: dict[str, Any], *, runner=None) -> tuple[dict, int]:
    """Pruefen, speichern, die Maschinenwerte einzeln setzen."""
    problems: list[str] = []
    draft = model.load()
    machine = _plan(changes, draft, problems)

    if problems:
        return ({"schema": SCHEMA, "ok": False, "problems": problems,
                 "written": [], "reports": [],
                 "pending_regenerate": model.marker_path().exists()}, 1)

    written: list[str] = []
    if draft.dirty():
        model.save(draft)
        # Die Marke, ohne die "beim naechsten Anmelden" eine Behauptung
        # waere. src/bin/zepos-session liest und loescht sie.
        model.request_regeneration_at_login()
        written = [key for key in changes if key not in dict(machine)]

    reports = []
    for key, value in machine:
        if key == THEME_KEY:
            outcome = model.set_theme(value, runner=runner)
        else:
            outcome = model.set_update_value(
                key[len(UPDATE_PREFIX):], value, runner=runner)
        reports.append({"key": key, "written": outcome.written,
                        "message": outcome.message,
                        "command": list(outcome.command)})
        if outcome.written:
            written.append(key)
        else:
            problems.append(f"{key}: {outcome.message}")

    return ({"schema": SCHEMA, "ok": not problems, "problems": problems,
             "written": written, "reports": reports,
             "pending_regenerate": model.marker_path().exists()},
            0 if not problems else 1)


def apply_now(*, runner=None) -> tuple[dict, int]:
    """zepos-generate --all, und die Marke faellt bei Erfolg."""
    completed = model.regenerate(runner=runner)
    ok = completed.returncode == 0
    return ({"schema": SCHEMA, "ok": ok,
             "problems": [] if ok else [
                 f"zepos-generate --all endete mit {completed.returncode}: "
                 f"{(completed.stderr or '').strip()}"],
             "returncode": completed.returncode,
             "pending_regenerate": model.marker_path().exists()},
            0 if ok else 1)


# --------------------------------------------------------------------
# Der Befehl
# --------------------------------------------------------------------

OPTION = "--json"


def main(arguments: list[str], *, runner=None, stdin=None) -> int:
    """`zepos-settings-gui --json ...`, ohne den Schalter selbst."""
    if not arguments or arguments[0] not in ("get", "set", "apply"):
        print(USAGE, file=sys.stderr)
        return 2

    verb, rest = arguments[0], arguments[1:]
    if (verb in ("get", "apply") and rest) or (verb == "set" and len(rest) != 1):
        print(USAGE, file=sys.stderr)
        return 2

    if verb == "apply":
        document, code = apply_now(runner=runner)
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return code

    try:
        draft = model.load()
    except (ValueError, OSError) as problem:
        # Denselben Wortlaut wie main.py und cli.py, nur als JSON: die
        # Datei gehoert settings.py, und vier Formulierungen fuer eine
        # Lage lesen sich wie vier Lagen.
        target = paths.user_root() / settings_file.FILENAME
        print(json.dumps(
            {"schema": SCHEMA, "ok": False,
             "problems": [settings_file.unreadable(target, problem)]},
            ensure_ascii=False, indent=2))
        return 1

    if verb == "get":
        print(json.dumps(state(draft, runner=runner),
                         ensure_ascii=False, indent=2))
        return 0

    raw = rest[0]
    if raw == "-":
        raw = (stdin if stdin is not None else sys.stdin).read()
    try:
        changes = json.loads(raw)
    except ValueError as problem:
        print(json.dumps(
            {"schema": SCHEMA, "ok": False,
             "problems": [f"das Dokument ist kein JSON: {problem}"]},
            ensure_ascii=False, indent=2))
        return 1
    if not isinstance(changes, dict):
        print(json.dumps(
            {"schema": SCHEMA, "ok": False,
             "problems": [f"erwartet wird ein Objekt {{schluessel: wert}}, "
                          f"nicht ein JSON {_kind(changes)}"]},
            ensure_ascii=False, indent=2))
        return 1

    document, code = write(changes, runner=runner)
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return code
