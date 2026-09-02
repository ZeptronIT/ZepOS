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
    2   die Schalter sind keine - usage() auf stderr, wie in cli.py

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
import region
import settings as settings_file
import sizes
import theme
import update

from . import model
from desktop_i18n import N_, _

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

# Die beiden Maschinenwerte, die systemd selbst fuehrt. Blanke
# Schluessel wie `theme` und ohne Praefix, weil sie keine Gruppe unter
# sich haben - und weil sie in `--json set` genauso heissen sollen, wie
# ein Mensch sie nennt.
LANGUAGE_KEY = "language"
TIMEZONE_KEY = "timezone"

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

# Der Gebrauchstext, ZEILENWEISE durch den Katalog und nicht als ein
# Block.
#
# WARUM ER UEBERHAUPT DURCH DEN KATALOG GEHT
#     Weil ein Mensch ihn liest, wenn er einen Schalter falsch tippt -
#     und die Regel dieses Baums ist die aus installer/core/i18n.py:
#     "Anything a user can see goes through _()". Eine
#     Maschinenschnittstelle ist kein Grund, deutsch zu bleiben; sie ist
#     ein Grund, praezise zu sein.
#
# WARUM ZEILENWEISE
#     Ein msgid mit einem \n darin schreibt gettext in der
#     mehrzeiligen Form, und die Kataloguesicherung sucht die
#     einzeilige Zeichenfolge `msgid "<ganzer Text>"`. Ein Block mit
#     vierzehn Zeilen waere ein Eintrag, den keine Pruefung wiederfindet.
#
#     Die AUSRICHTUNG der zweiten Spalte bleibt dabei Sache des
#     Uebersetzers - darum stehen die Befehlsnamen mit im msgid und
#     nicht als Platzhalter davor.
USAGE_LINES = (
    N_("usage: zepos-settings-gui --json get"),
    N_("       zepos-settings-gui --json set <document>|-"),
    N_("       zepos-settings-gui --json apply"),
    N_("       zepos-settings-gui --json arm"),
    "",
    N_("get   writes the state of all pages as one JSON document."),
    N_("set   takes an object {key: value} - the same keys that `get` "
       "names"),
    N_("      under \"key\" in every control, so the same ones as "
       "`zepos-settings"),
    N_("      set`. \"-\" reads stdin."),
    N_("apply runs zepos-generate --all and clears the marker."),
    N_("arm   applies a screen arrangement ON TRIAL and STAYS RUNNING:"),
    N_("      line 1 on stdin is the arrangement, line 2 the answer"),
    N_("      (keep/discard). Without an answer the guard takes it back."),
    N_("      For a program that keeps running - not for the hand."),
)


def usage() -> str:
    """Der Gebrauchstext, in der Sprache, die jetzt gilt."""
    return "\n".join(_(line) if line else "" for line in USAGE_LINES)

# --------------------------------------------------------------------
# Die Klagen, die mehr als eine Stelle braucht
# --------------------------------------------------------------------
#
# Vier Saetze standen woertlich an je zwei bis vier Stellen - "ist kein
# Schalter" viermal, "ist keine Zahl" zweimal, "ist keins von" dreimal.
# Vier msgids und nicht dreizehn: dreizehn Eintraege waeren dreizehn
# Gelegenheiten, dieselbe Klage verschieden zu uebersetzen.
NOT_A_SWITCH = N_("{key}: {kind} is not a switch")
NOT_A_NUMBER = N_("{key}: {kind} is not a number")
NOT_ONE_OF = N_("{key}: {value!r} is not one of {options}")
NOT_JSON = N_("the document is not JSON: {problem}")

# Und drei, die wortgleich in screens.py stehen. Derselbe msgid, damit
# das Fenster und die Bruecke nicht zwei Wortlaute fuer eine Lage haben
# - die Bruecke bedient dasselbe Fenster, nur in AGS gezeichnet.
NOT_APPLIED = N_("Not applied: {problem}")
GUARD_REVERTED = N_("The guard had already reverted: {report}")
APPLIED_NOT_WRITTEN = N_(
    "Applied, but not written: {problem}. The arrangement stands until "
    "the next login.")


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
        # Zu welcher Gruppe der Seite dieses Element gehoert - der Name
        # aus `groups` seiner Seite, oder leer.
        #
        # NACHGETRAGEN am 19.08.2026 (Aufgabe 32): die Farben trugen
        # dieses Feld schon (brand.COLOR_GROUPS), die uebrigen sechs
        # Seiten nicht - und damit hatte das Dokument zwei Formen
        # desselben Bedienelements, genau das, was der Absatz oben
        # verbietet. Es steht jetzt an JEDEM, weil jede Seite Gruppen
        # hat: sie standen bisher nur als Adw.PreferencesGroup-Titel in
        # app.py, also in einem der beiden Fenster.
        "group": "",
    }
    control.update(rest)
    return control


def _page(name: str, controls: list[dict], note: str = "",
          groups: list[dict] | None = None) -> dict:
    """Eine Seite mit ihren Gruppen.

    `groups` ist eine GEORDNETE Liste von {"name", "note"} und keine
    Abbildung: die Reihenfolge ist die, in der die Gruppen im Fenster
    stehen, und ein JSON-Objekt gibt sie nicht zuverlaessig her.

    Eine Gruppe OHNE Bedienelemente ist erlaubt und kommt zweimal vor
    ("Die uebrigen Groessen", "Die uebrigen Einstellungen"): im
    GTK-Fenster sind das Adw.ActionRows ohne Wirkung, die sagen, was
    diese Oberflaeche NICHT anbietet und wo es stattdessen steht. Sie
    sind Text und kein Bedienelement - als Bedienelement getarnt waeren
    sie eine Zeile, die aussieht, als koennte man sie anfassen.
    """
    label, icon = next((title, icon) for page, title, icon in model.PAGES
                       if page == name)
    return {"name": name, "label": label, "icon": icon, "note": note,
            "groups": groups or [], "controls": controls}


def _group(name: str, note: str = "") -> dict:
    return {"name": name, "note": note}


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
        SIZES_SCALE, NUMBER, _(model.LABEL_SCALE), draft.current_scale(),
        # Der Satz erklaert den Rueckstell-Knopf neben diesem Regler
        # (im GTK-Fenster eine eigene Zeile "Zuruecksetzen", hier das
        # `default`-Feld daneben) - siehe model.scale_reset_note().
        note=model.scale_reset_note(),
        default=sizes.SCALE_DEFAULT,
        minimum=model.SCALE_MINIMUM, maximum=model.SCALE_MAXIMUM,
        step=model.SCALE_STEP, digits=2, unit="", group=_(model.GROUP_SCALE))]

    for dial in model.DIALS:
        controls.append(_control(
            f"{SIZES_VALUE}{dial.name}", NUMBER, dial.label,
            draft.current_size(dial.name),
            note=dial.note,
            default=_scale_free(draft, dial.name),
            minimum=dial.minimum, maximum=dial.maximum,
            step=1, digits=0, unit=sizes.TABLE[dial.name].unit,
            group=_(model.GROUP_DIALS),
            # Der ganze Sinn der fuenf Ausnahmen: eine 24 kann heissen
            # "der Faktor hat 24 daraus gemacht" oder "hier steht fest
            # eine 24". null als Wert setzt sie wieder auf den Faktor.
            follows_scale=draft.follows_scale(dial.name)))

    controls.append(_control(
        SIZES_MOTION, SWITCH, _(model.LABEL_MOTION), draft.current_motion(),
        note=_(model.NOTE_MOTION), group=_(model.GROUP_MOTION),
        default=sizes.motion_enabled({})))
    return _page("groesse", controls, groups=[
        _group(model.GROUP_SCALE, model.scale_note()),
        _group(model.GROUP_DIALS, _(model.NOTE_DIALS_GROUP)),
        _group(model.GROUP_MOTION, model.motion_note()),
        # Die Gruppe ohne Bedienelemente - siehe _page(). Sie sagt, was
        # diese Oberflaeche nicht anbietet, und wo es stattdessen steht.
        _group(model.NOTE_SIZES_REST_TITLE, model.sizes_rest_note()),
    ])


DISPLAY_KEY = "displays.layout"


def _page_bildschirme(*, runner=None) -> dict:
    """Was der Compositor gerade zeigt - und wie man es aendert.

    WARUM `writable` HIER `false` IST UND DIE SEITE TROTZDEM BEDIENBAR
        `writable` ist eine Aussage ueber `--json set`, und die bleibt:
        durch `set` geht diese Anordnung nicht. displays.arm_and_apply()
        macht einen Waechter scharf, wendet dann an und gibt einen
        Attempt zurueck, der einen LAUFENDEN Kindprozess haelt: entweder
        bestaetigt jemand innerhalb von displays.CONFIRM_SECONDS
        Sekunden, oder der Waechter stellt die alte Anordnung wieder
        her. Genau deshalb ist er ein eigener Prozess - ein Zeitgeber im
        Programm stirbt mit ihm, und der schwarze Schirm bliebe.

        Ein Befehl, der nach seiner Ausgabe endet, kann diesen Prozess
        nicht halten. Er wuerde anwenden und sterben, der Waechter naehme
        zurueck, und die Oberflaeche haette einen Schalter, der
        nachweislich nichts bewirkt.

    WAS SICH AM 19.08.2026 (Aufgabe 32) GEAENDERT HAT
        Der Bericht der Aufgabe 29 schloss: "Das AGS-Fenster braucht
        dafuer einen eigenen, laufenden Weg - oder die Seite bleibt beim
        GTK-Fenster." Den laufenden Weg gibt es jetzt: `--json arm`
        (siehe arm() weiter unten) BLEIBT STEHEN, solange der Waechter
        laeuft, und nimmt die Antwort auf seiner eigenen Standardeingabe
        entgegen. AGS endet nicht - ein AGS-Fenster kann diesen Prozess
        also halten, und Astal.Process.write() schreibt ihm die Antwort.

        `armable` sagt, ob dieser Weg hier ueberhaupt offensteht (er
        braucht einen lesbaren Compositor UND einen auffindbaren
        Waechter), `arm` nennt den Befehl dafuer - aus derselben Regel
        wie `command` bei Thema und Aktualisierung: nicht getippt.
    """
    try:
        outputs = displays.read_outputs(runner=runner)
        layout = displays.current_layout(
            outputs, displays.read_trailing_options())
        available, reason = True, ""
    except (RuntimeError, OSError, ValueError) as problem:
        outputs, layout, available, reason = [], [], False, str(problem)

    # Die Modi je Schirm, aus `hyprctl monitors all -j` und nicht
    # geraten: ein Fenster, das eine Aufloesung anbietet, die dieser
    # Schirm nicht kann, bietet einen schwarzen Schirm an.
    modes = {output.name: [{"width": mode.width, "height": mode.height,
                            "refresh": mode.refresh, "label": mode.label}
                           for mode in output.modes]
             for output in outputs}

    control = _control(
        DISPLAY_KEY, LAYOUT, _("Arrangement of the screens"),
        [{"name": place.name, "selector": place.selector,
          "enabled": place.enabled,
          "width": place.width, "height": place.height,
          "refresh": place.refresh, "x": place.x, "y": place.y,
          "scale": place.scale, "transform": place.transform,
          "extra": list(place.extra),
          "label": next((output.label for output in outputs
                         if output.name == place.name), place.name),
          "modes": modes.get(place.name, [])}
         for place in layout],
        scope=DESKTOP, immediate=True, writable=False,
        reason=reason or _(
            "This arrangement does not go through `set`: it is applied "
            "via {guard}, which waits {seconds} seconds for a "
            "confirmation and otherwise takes it back. A command that "
            "ends with its output could not hold the guard - it is "
            "therefore applied via `{option} arm` from a program that "
            "keeps running.").format(
                guard=displays.GUARD_NAME,
                seconds=displays.CONFIRM_SECONDS, option=OPTION),
        available=available,
        armable=available and _guard_found(),
        arm=[OPTION, ARM],
        seconds=displays.CONFIRM_SECONDS,
        scales=list(model.SCALES),
        transforms=list(model.TRANSFORMS),
        # Nicht user-settings.json, und das ist der Grund, aus dem diese
        # Seite am Speichern-Knopf des Fensters nicht haengt.
        target=str(displays.config_path()),
        profile=displays.current_profile())
    return _page("bildschirme", [control])


def _guard_found() -> bool:
    """Ob es den Waechter auf dieser Maschine ueberhaupt gibt.

    displays.guard_command() wirft FileNotFoundError, wenn er weder auf
    PATH noch neben dem Modul liegt - dann wird ohnehin nichts
    angewandt (siehe dort, "kein Rueckfall auf 'dann eben ohne
    Waechter'"). Ein Fenster, das den Anwenden-Knopf trotzdem zeigt,
    haette einen Knopf, der nur eine Fehlermeldung kann.
    """
    try:
        displays.guard_command()
    except (FileNotFoundError, OSError):
        return False
    return True


def _page_leiste(draft: model.Draft) -> dict:
    shipped, labels, say = model.shipped_bar()
    controls = []
    for key, label, note in model.BAR_SIDES:
        chosen = draft.current_bar(key)
        placeable = model.placeable_in(shipped, key)
        # ANGEBOTEN und ANGENOMMEN sind im Dock zweierlei - siehe
        # model.acceptable_in(). Das Feld `placeable` traegt weiter das
        # ANGEBOT, weil ein Fenster daraus eine Liste zum Anklicken baut
        # ("Wieder hinzufuegen"); GEPRUEFT wird gegen das Weitere, sonst
        # faellt genau die Anheftung heraus, die der Nutzer selbst
        # hinzugefuegt hat, und `effective` zeigte sie als verworfen an.
        effective, discarded = settings_file.bar_order(
            chosen, model.acceptable_in(shipped, key), shipped[key],
            unknown=model.rejection_in(key))
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
        THEME_KEY, CHOICE, _(model.LABEL_THEME), model.current_theme(),
        note=_(model.THEME_TIMING),
        default=theme.DEFAULT, group=_(model.GROUP_THEME),
        options=[{"value": name, "label": model.theme_label(name),
                  "note": model.theme_description(name)} for name in names],
        scope=MACHINE, immediate=True, writable=writable,
        reason="" if writable else _(
            "The theme belongs to the machine and not to this account, "
            "because the login screen belongs to it. Permission is asked "
            "when changing it."),
        command=model.theme_elevated_command(theme.DEFAULT)[:-1])
    return _page("thema", [control],
                 groups=[_group(model.GROUP_THEME,
                                model.theme_note(writable))])


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
    # Die zwoelf Gruppen ohne eigenen Text: brand.py fuehrt zu ihnen
    # keinen, und im GTK-Fenster steht ueber ihnen ebenfalls nur der
    # Name (Adw.PreferencesGroup(title=name), ohne description).
    return _page("farben", controls,
                 groups=[_group(name) for name, _rows in brand.COLOR_GROUPS])


def _page_wetter(draft: model.Draft) -> dict:
    stored = settings_file.defaults().get("weather")
    control = _control(
        WEATHER_KEY, TEXT, _(model.LABEL_WEATHER), draft.current_weather(),
        group=_(model.GROUP_WEATHER),
        default=stored.get("location", "") if isinstance(stored, dict) else "")
    return _page("wetter", [control],
                 groups=[_group(model.GROUP_WEATHER,
                                _(model.NOTE_WEATHER_GROUP))])


def _page_aktualisierung() -> dict:
    try:
        config = update.load()
    except (ValueError, OSError) as problem:
        return _page("aktualisierung", [], note=str(problem))

    writable = model.update_writable()
    reason = "" if writable else _(
        "This setting belongs to the machine and not to this account: the "
        "service runs before anyone has logged in. Permission is asked "
        "when changing it.")
    shipped = update.defaults()

    def machine(key: str, kind: str, label: str, value: Any, **rest: Any) -> dict:
        return _control(f"{UPDATE_PREFIX}{key}", kind, label, value,
                        scope=MACHINE, immediate=True, writable=writable,
                        reason=reason, group=_(model.GROUP_UPDATE),
                        command=model.update_elevated_command(key, None)[:-1],
                        **rest)

    # Die Nebenzeilen der vier, aus model.py. Der Zeitgeber-Takt hat
    # keine - er hatte im GTK-Fenster auch keine, und ein erfundener
    # Satz hier waere ein Satz, den nur eines der beiden Fenster zeigt.
    notes = {
        model.UPDATE_ENABLED: _(model.NOTE_UPDATE_ENABLED),
        model.UPDATE_SCOPE: _(model.NOTE_UPDATE_SCOPE),
        model.UPDATE_NOTIFY: model.update_notify_note(),
        model.UPDATE_INTERVAL: "",
    }

    controls = [machine(
        model.UPDATE_ENABLED, SWITCH,
        model.UPDATE_LABELS[model.UPDATE_ENABLED],
        bool(config.get(model.UPDATE_ENABLED)),
        note=notes[model.UPDATE_ENABLED],
        default=bool(shipped.get(model.UPDATE_ENABLED)))]

    for key, labels in UPDATE_CHOICES.items():
        controls.append(machine(
            key, CHOICE, model.UPDATE_LABELS[key],
            _dotted(config, key),
            note=notes[key],
            default=_dotted(shipped, key),
            options=[{"value": name, "label": text}
                     for name, text in labels.items()]))
    return _page("aktualisierung", controls, groups=[
        _group(model.GROUP_UPDATE, model.update_note(writable)),
        _group(model.NOTE_UPDATE_REST_TITLE, _(model.NOTE_UPDATE_REST)),
    ])


def _page_sprache() -> dict:
    """Die Sprache und die Zeitzone dieser Maschine.

    ZWEI WERTE AUF EINER SEITE, UND DAS IST KEINE BEQUEMLICHKEIT
        Sie beantworten dieselbe Frage - "wo und wie spricht diese
        Maschine" -, sie gehoeren beide der MASCHINE, und sie werden
        beide durch ein systemd-Werkzeug mit Polkit-Rueckfrage gesetzt.
        Der Kopf von model.py fuehrt es aus. Zwei Seiten dafuer waeren
        zwei Orte fuer eine Entscheidung, die man in einem Zug trifft:
        wer umzieht, stellt beides um.

    WARUM DIE ZEITZONE EINE AUSWAHL IST UND KEIN FELD
        Weil `date` jeden Namen annimmt. Der Assistent hat sie bis heute
        als freies Textfeld abgefragt, und ein Tippfehler darin - "Europe/
        Berlm" - wird dort zu einer Uhr, die still auf UTC laeuft (die
        Messung steht in src/doctor.py). Die Liste kommt aus
        `timedatectl list-timezones`, also aus genau dem, was der
        Setzbefehl danach auch annimmt.
    """
    sprachen = model.language_codes()
    zonen = model.timezone_names()
    sprache_geht = model.language_writable()
    zone_geht = model.timezone_writable()

    jetzt_sprache = model.current_language()
    jetzt_zone = model.current_timezone()

    sprache = _control(
        LANGUAGE_KEY, CHOICE, _(model.LABEL_LANGUAGE), jetzt_sprache,
        note=_(model.LANGUAGE_TIMING),
        group=_(model.GROUP_REGION),
        options=[{"value": code, "label": model.language_label(code)}
                 for code in sprachen],
        scope=MACHINE, immediate=True, writable=sprache_geht,
        reason="" if sprache_geht else _(
            "This system has no localectl. The language is in "
            "/etc/locale.conf, and that can only be reached with "
            "permission."),
        # Der Befehl OHNE seinen letzten Teil, wie ueberall auf dieser
        # Ebene: `localectl set-locale`. Was fehlt, ist der Wert.
        command=(model.language_elevated_command(jetzt_sprache)[:-1]
                 if sprachen else []))

    zone = _control(
        TIMEZONE_KEY, CHOICE, _(model.LABEL_TIMEZONE), jetzt_zone,
        note=_(model.TIMEZONE_TIMING),
        group=_(model.GROUP_REGION),
        options=[{"value": name, "label": name} for name in zonen],
        scope=MACHINE, immediate=True, writable=zone_geht,
        reason="" if zone_geht else _(
            "This system has no timedatectl. The time zone is in "
            "/etc/localtime, and that can only be reached with "
            "permission."),
        command=["timedatectl", "set-timezone"] if zone_geht else [])

    return _page("sprache", [sprache, zone],
                 groups=[_group(model.GROUP_REGION,
                                _(model.NOTE_REGION_GROUP))])


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
    """Alle Seiten, in der Reihenfolge von model.PAGES."""
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
        "cost": {"generate": _(model.GENERATE_COST),
                 "theme": _(model.THEME_TIMING),
                 # Was ein Sprach- und ein Zonenwechsel wann erreichen.
                 # Sie stehen NEBEN dem Thema und nicht statt seiner:
                 # das Fenster sagt nach jedem Schreiben, was gerade
                 # passiert ist, und die drei Saetze sind verschieden,
                 # weil die drei Wirkungen es sind.
                 "language": _(model.LANGUAGE_TIMING),
                 "timezone": _(model.TIMEZONE_TIMING)},
        "pages": [
            _page_groesse(draft),
            _page_bildschirme(runner=runner),
            _page_leiste(draft),
            _page_thema(),
            _page_farben(draft),
            _page_wetter(draft),
            _page_aktualisierung(),
            _page_sprache(),
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
        problems.append(_(NOT_A_NUMBER).format(
            key=key, kind=_kind(value)))
        return None
    if not low <= value <= high:
        problems.append(_("{key}: {value} is not between {low} and "
                          "{high}").format(key=key, value=value, low=low,
                                           high=high))
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
                problems.append(_(NOT_A_SWITCH).format(
                    key=key, kind=_kind(value)))
            else:
                draft.motion = value

        elif key.startswith(SIZES_VALUE):
            name = key[len(SIZES_VALUE):]
            dial = dials.get(name)
            if dial is None:
                problems.append(_(
                    "{key}: this interface only offers {offered}. The "
                    "remaining {rest} sizes are in `zepos-settings get "
                    "sizes` and `user_settings.py list-sizes`.").format(
                        key=key, offered=", ".join(sorted(dials)),
                        rest=len(sizes.TABLE) - len(dials)))
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
                problems.append(_("{key}: that colour does not "
                                  "exist").format(key=key))
            elif not isinstance(value, str) or not HEX.match(value):
                problems.append(_("{key}: {value!r} is not a "
                                  "#rrggbb").format(key=key, value=value))
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
                problems.append(_("{key}: {kind} is not a place "
                                  "name").format(key=key,
                                                 kind=_kind(value)))
            else:
                draft.weather = value

        elif key.startswith(BAR_PREFIX):
            _plan_bar(key[len(BAR_PREFIX):], key, value, draft, problems)

        elif key == THEME_KEY:
            if value not in theme.THEMES:
                problems.append(_(NOT_ONE_OF).format(
                    key=key, value=value,
                    options=", ".join(sorted(theme.THEMES))))
            else:
                machine.append((key, value))

        elif key == LANGUAGE_KEY:
            # Gegen die Liste geprueft, die DIESE Maschine anbietet, und
            # nicht gegen region.LANGUAGES: eine Sprache ohne Katalog
            # oder ohne erzeugte Sprachumgebung wird still ignoriert
            # (gemessen, siehe den Kopf von src/region.py), und still
            # ignoriert ist genau das, was eine Oberflaeche nicht
            # weiterreichen darf.
            moeglich = model.language_codes()
            if value not in moeglich:
                problems.append(
                    _(NOT_ONE_OF).format(
                        key=key, value=value,
                        options=", ".join(moeglich))
                    + " " + _("A language only stands here if there is a "
                              "catalogue for it AND this machine has "
                              "generated the locale."))
            else:
                machine.append((key, value))

        elif key == TIMEZONE_KEY:
            # An der Datenbank und nicht an der Liste: `timedatectl
            # list-timezones` kann auf einer Maschine ohne timedatectl
            # leer sein, waehrend /usr/share/zoneinfo dasteht - dann
            # waere jede Zone "keins von " und die Klage nennte nichts.
            if not isinstance(value, str) or not region.known_timezone(value):
                problems.append(_(
                    "{key}: {value!r} is not in {directory}. `{listing}` "
                    "names the ones this machine knows.").format(
                        key=key, value=value,
                        directory=region.zoneinfo_directory(),
                        listing=" ".join(region.ZONE_LISTING)))
            else:
                machine.append((key, value))

        elif key.startswith(UPDATE_PREFIX):
            _plan_update(key[len(UPDATE_PREFIX):], key, value, machine,
                         problems)

        else:
            problems.append(_(
                "{key}: not a key of this interface. `--json get` names "
                "every one there is.").format(key=key))

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
        problems.append(_("{key}: there are {keys}").format(
            key=key, keys=", ".join(settings_file.BAR_KEYS)))
        return
    if value is None:
        draft.reset_bar(half)
        return
    if not isinstance(value, list) or any(not isinstance(n, str) for n in value):
        problems.append(_(
            "{key}: a list of names or null for the shipped order is "
            "expected").format(key=key))
        return

    shipped, _labels, _say = model.shipped_bar()
    # acceptable_in() und nicht placeable_in(): im Dock darf angeheftet
    # werden, was auf DIESER Maschine einen Anwendungseintrag hat, und
    # nicht nur, was ZepOS ausliefert. Ohne diese Zeile waere der Wunsch
    # "per Rechtsklick anheften" durch die Bruecke nicht bedienbar - jeder
    # Name, den die Vorgabe nicht kennt, kaeme als Ablehnung zurueck.
    _kept, discarded = settings_file.bar_order(
        list(value), model.acceptable_in(shipped, half), shipped[half],
        unknown=model.rejection_in(half))
    if discarded:
        problems.append(settings_file.bar_complaint(half, discarded))
        return
    draft.set_bar(half, list(value))


def _plan_update(name: str, key: str, value: Any,
                 machine: list[tuple[str, Any]], problems: list[str]) -> None:
    if name == model.UPDATE_ENABLED:
        if not isinstance(value, bool):
            problems.append(_(NOT_A_SWITCH).format(
                key=key, kind=_kind(value)))
        else:
            machine.append((key, value))
        return
    labels = UPDATE_CHOICES.get(name)
    if labels is None:
        problems.append(_(
            "{key}: this interface offers {offered}. `zepos-update "
            "--help` names the rest.").format(
                key=key,
                offered=", ".join(
                    UPDATE_PREFIX + n for n in
                    [model.UPDATE_ENABLED, *UPDATE_CHOICES])))
    elif value not in labels:
        problems.append(_(NOT_ONE_OF).format(
            key=key, value=value, options=", ".join(labels)))
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
        elif key == LANGUAGE_KEY:
            outcome = model.set_language(value, runner=runner)
            # DIE MARKE, UND WARUM SIE HIER GESETZT WIRD
            #     Ihre Aufgabe ist "die Aenderung ist spaetestens bei
            #     der naechsten Anmeldung da, ohne dass jemand etwas
            #     anklickt" (siehe model.request_regeneration_at_login).
            #     Bei einer Groesse heisst das: die erzeugten Dateien
            #     sind veraltet. Hier heisst es etwas anderes und genau
            #     so viel: die laufende Schale spricht noch die alte
            #     Sprache, und der Erzeugungslauf ist das EINZIGE, was
            #     sie neu baut - GEMESSEN, eine schon gezeichnete
            #     Beschriftung folgt keinem Katalogwechsel (der Absatz
            #     zu LANGUAGE_TIMING in model.py fuehrt die Messung).
            #
            #     Sie ist damit zugleich der Knopf: das Fenster zeigt
            #     "Jetzt anwenden", solange sie liegt, und wer nicht
            #     klickt, bekommt es beim naechsten Anmelden.
            if outcome.written:
                model.request_regeneration_at_login()
        elif key == TIMEZONE_KEY:
            # OHNE Marke, und das ist der Unterschied zur Sprache: eine
            # Zeitzone steckt in keiner erzeugten Datei. `date` liest
            # /etc/localtime bei JEDEM Aufruf, und die Uhr der Leiste
            # ruft `date` einmal je Minute. Ein Erzeugungslauf dafuer
            # waere ein Neustart der ganzen Schale fuer nichts.
            outcome = model.set_timezone(value, runner=runner)
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


# --------------------------------------------------------------------
# Die Bildschirme - der laufende Weg
# --------------------------------------------------------------------

ARM = "arm"

# Die Felder einer Anordnung, die dieser Weg entgegennimmt, mit dem
# Typ, in den sie gebracht werden. `extra` und `selector` stehen NICHT
# darin: der eine wird durchgereicht (siehe Placement.extra, "nicht
# angeboten darf nicht weg heissen"), der andere kommt aus
# monitors.selector() und ist keine Einstellung.
ARM_FIELDS: dict[str, Any] = {
    "enabled": bool,
    "width": int,
    "height": int,
    "refresh": float,
    "x": int,
    "y": int,
    "scale": float,
    "transform": int,
}


def _arm_plan(document: Any, desk, problems: list[str]) -> None:
    """Die gewuenschte Anordnung in den Schreibtisch legen.

    Durch displays.Desk.change() und nicht durch selbstgebaute
    Placements: dort sitzen das Einrasten, das Normalisieren und die
    Frage, was ein Schirm im Gesamtbild einnimmt. Ein zweiter Rechenweg
    hier waere eine zweite Anordnung.
    """
    if not isinstance(document, dict) or not isinstance(
            document.get("layout"), list):
        problems.append(_(
            "{\"layout\": [{\"name\": ..., ...}]} is expected - the same "
            "shape that `--json get` prints under displays.layout"))
        return

    known = {place.name for place in desk.placements}
    for screen in document["layout"]:
        if not isinstance(screen, dict) or not isinstance(
                screen.get("name"), str):
            problems.append(_("{screen!r}: every screen needs its "
                              "`name`").format(screen=screen))
            continue
        name = screen["name"]
        if name not in known:
            problems.append(_(
                "{name}: this screen does not exist here. Known are "
                "{known}.").format(name=name,
                                   known=", ".join(sorted(known))))
            continue

        fields: dict[str, Any] = {}
        for field, kind in ARM_FIELDS.items():
            if field not in screen:
                continue
            value = screen[field]
            if kind is bool:
                if not isinstance(value, bool):
                    problems.append(_(NOT_A_SWITCH).format(
                        key=f"{name}.{field}", kind=_kind(value)))
                    continue
                fields[field] = value
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(_(NOT_A_NUMBER).format(
                    key=f"{name}.{field}", kind=_kind(value)))
            else:
                fields[field] = kind(value)

        unknown = sorted(set(screen) - set(ARM_FIELDS) - {"name"})
        if unknown:
            problems.append(_(
                "{name}: this interface does not know {unknown}. "
                "Adjustable are {fields}.").format(
                    name=name, unknown=", ".join(unknown),
                    fields=", ".join(ARM_FIELDS)))
            continue
        if fields:
            desk.change(name, **fields)


def arm(*, runner=None, stdin=None, stdout=None) -> int:
    """Anwenden, auf Probe - und stehenbleiben, bis jemand antwortet.

    DER GANZE PUNKT DIESES BEFEHLS IST, DASS ER NICHT ENDET.
        Zeile 1 auf der Standardeingabe ist die gewuenschte Anordnung.
        Danach schreibt er EINE Zeile JSON und bleibt stehen: der
        Waechter laeuft, die neue Anordnung ist auf dem Schirm, und die
        Frist von displays.CONFIRM_SECONDS Sekunden laeuft.

        Zeile 2 ist die Antwort - displays.GUARD_KEEP oder
        displays.GUARD_REVERT. Dieselben zwei Woerter, die auch der
        Waechter selbst versteht; ein drittes Vokabular waere eine
        dritte Stelle, an der man sich vertippen kann. Ein Dateiende
        zaehlt als GUARD_REVERT: wer die Verbindung verliert, hat nichts
        gesehen.

        Die Frist laeuft AUCH DANN ab, wenn dieser Prozess stirbt - der
        Waechter ist ein eigener Prozess in einer eigenen Sitzung, und
        die brechende Pipe ist ihm das Zeichen zum Zuruecknehmen. Das
        ist der Grund, aus dem hier kein Zeitgeber steht: der Rueckweg
        gehoert nicht in das Programm, dessen Absturz er auffangen soll.

    GESCHRIEBEN WIRD ERST NACH DEM BEHALTEN, und nie davor. Der Kopf
    von src/displays.py fuehrt aus, warum: eine schon geschriebene
    Datei braeuchte einen zweiten Rueckfall, und eine Sitzung, die
    danach mit ihr startet, findet keinen Schirm mehr, auf dem sie
    fragen koennte. screens.py macht es in _settle() genauso.
    """
    read_from = stdin if stdin is not None else sys.stdin
    write_to = stdout if stdout is not None else sys.stdout

    def say(document: dict) -> None:
        write_to.write(json.dumps(document, ensure_ascii=False) + "\n")
        write_to.flush()

    problems: list[str] = []
    try:
        desk = displays.Desk.load(runner=runner)
    except (RuntimeError, OSError, ValueError) as problem:
        say({"schema": SCHEMA, "ok": False, "armed": False,
             "problems": [str(problem)]})
        return 1

    raw = read_from.readline()
    try:
        document = json.loads(raw)
    except ValueError as problem:
        say({"schema": SCHEMA, "ok": False, "armed": False,
             "problems": [_(NOT_JSON).format(problem=problem)]})
        return 1

    _arm_plan(document, desk, problems)
    problems.extend(displays.blockers(desk.placements))
    if problems:
        say({"schema": SCHEMA, "ok": False, "armed": False,
             "problems": problems})
        return 1

    # WAS AUFFAELLT, ABER NICHT VERBIETET - seit dem 01.09.2026.
    #
    #     Hier stand `problems.extend(desk.problems())`, und damit war
    #     eine Ueberlappung in DIESEM Fenster eine Ablehnung, im
    #     GTK-Fenster dagegen nur eine Warnung (screens.py,
    #     _show_state()). Zwei Antworten auf dieselbe Anordnung sind eine
    #     zu viel, und die strengere war die falsche: dieses Fenster kann
    #     Schirme gar nicht gegeneinander VERSCHIEBEN - es sagt das
    #     ausdruecklich ("Position: every screen keeps the place it has",
    #     ags-settings.template). Wer sich hier mit einem Massstab oder
    #     einer Aufloesung eine Ueberlappung baut, bekam die Meldung
    #     "geht nicht" von genau dem Fenster, das sie nicht aufloesen
    #     kann. Eine Sackgasse ist keine Sicherung.
    #
    #     Der Fall OHNE Rueckweg bleibt eine Ablehnung, und er bleibt
    #     auch VOR dem Waechter: displays.blockers() steht eine Zeile
    #     ueber diesem Absatz in derselben Liste wie die Formfehler.
    hinweise = displays.remarks(desk.placements)

    try:
        attempt = displays.arm_and_apply(desk.placements, desk.original,
                                         runner=runner)
    except (displays.NoScreenLeft, displays.GuardRefused,
            displays.ApplyFailed, OSError) as problem:
        say({"schema": SCHEMA, "ok": False, "armed": False,
             "problems": [_(NOT_APPLIED).format(problem=problem)]})
        return 1

    # Von hier an steht die neue Anordnung auf dem Schirm, und die Frist
    # laeuft. Diese Zeile ist das Zeichen fuer das Fenster, seine
    # Rueckfrage zu zeigen.
    #
    # `warnings` steht NEBEN `problems` und nicht darin: `problems` heisst
    # in jeder anderen Antwort dieser Bruecke "es ist nichts passiert",
    # und ein Fenster, das beides gleich behandelt, meldete eine
    # angewandte Anordnung als gescheitert.
    say({"schema": SCHEMA, "ok": True, "armed": True,
         "seconds": displays.CONFIRM_SECONDS, "problems": [],
         "warnings": hinweise,
         "applied": list(attempt.applied)})

    answer = (read_from.readline() or "").strip()
    if answer != displays.GUARD_KEEP:
        outcome = attempt.revert()
        say({"schema": SCHEMA, "ok": True, "armed": False, "kept": False,
             "problems": [], "written": [], "report": outcome.report})
        return 0

    outcome = attempt.keep()
    if not outcome.kept:
        # Der Waechter hat trotz "behalten" zurueckgestellt: seine Frist
        # lief genau in diesem Moment ab. Dann gilt SEIN Ergebnis - auf
        # dem Schirm steht die alte Anordnung, also wird auch keine neue
        # geschrieben. Wortgleich zu screens.py, _settle().
        say({"schema": SCHEMA, "ok": False, "armed": False, "kept": False,
             "problems": [_(GUARD_REVERTED).format(
                 report=outcome.report)],
             "written": [], "report": outcome.report})
        return 1

    try:
        written = displays.write(desk.placements)
    except OSError as problem:
        say({"schema": SCHEMA, "ok": False, "armed": False, "kept": True,
             "problems": [_(APPLIED_NOT_WRITTEN).format(
                 problem=problem)],
             "written": [], "report": outcome.report})
        return 1

    say({"schema": SCHEMA, "ok": True, "armed": False, "kept": True,
         "problems": [], "written": [str(path) for path in written],
         "report": outcome.report})
    return 0


def apply_now(*, runner=None) -> tuple[dict, int]:
    """zepos-generate --all, und die Marke faellt bei Erfolg."""
    completed = model.regenerate(runner=runner)
    ok = completed.returncode == 0
    return ({"schema": SCHEMA, "ok": ok,
             "problems": [] if ok else [
                 _("zepos-generate --all exited with {code}: "
                   "{stderr}").format(
                       code=completed.returncode,
                       stderr=(completed.stderr or "").strip())],
             "returncode": completed.returncode,
             "pending_regenerate": model.marker_path().exists()},
            0 if ok else 1)


# --------------------------------------------------------------------
# Der Befehl
# --------------------------------------------------------------------

OPTION = "--json"


def main(arguments: list[str], *, runner=None, stdin=None) -> int:
    """`zepos-settings-gui --json ...`, ohne den Schalter selbst."""
    if not arguments or arguments[0] not in ("get", "set", "apply", ARM):
        print(usage(), file=sys.stderr)
        return 2

    verb, rest = arguments[0], arguments[1:]
    if (verb in ("get", "apply", ARM) and rest) or (
            verb == "set" and len(rest) != 1):
        print(usage(), file=sys.stderr)
        return 2

    if verb == ARM:
        # KEIN model.load() davor: diese Anordnung steht nicht in
        # user-settings.json (siehe `target` am Bedienelement), und eine
        # unlesbare Einstellungsdatei darf nicht der Grund sein, aus dem
        # jemand seinen zweiten Schirm nicht mehr einschalten kann -
        # dieses Fenster ist genau das, was man dann braucht.
        return arm(runner=runner, stdin=stdin)

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
             "problems": [_(NOT_JSON).format(problem=problem)]},
            ensure_ascii=False, indent=2))
        return 1
    if not isinstance(changes, dict):
        print(json.dumps(
            {"schema": SCHEMA, "ok": False,
             "problems": [_("an object {{key: value}} is expected, not "
                            "a JSON {kind}").format(
                                kind=_kind(changes))]},
            ensure_ascii=False, indent=2))
        return 1

    document, code = write(changes, runner=runner)
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return code
