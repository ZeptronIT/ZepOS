# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Vertrag, an dem das AGS-Einstellungsfenster haengen wird.

WAS HIER GEMESSEN WIRD, UND WARUM ES NICHT DIE OBERFLAECHE IST
    bridge.py ist die Naht zwischen model.py und einem Fenster, das
    TypeScript ist. Ein Vertrag zwischen zwei Programmen hat genau vier
    Stellen, an denen er reisst, und jede davon hat unten eine Pruefung:

      unvollstaendig  Eine Seite, ein Regler, eine Farbe fehlt im
                      Dokument. Das Fenster zeichnet sie dann nicht, und
                      niemand merkt es - die Einstellung ist ja da, nur
                      unsichtbar. Genau so sind neunundzwanzig Farben
                      jahrelang im Stil-Editor gestanden, ohne ein
                      erzeugtes Byte zu bewegen.
      danebengeschrieben  Ein Schreibvorgang, der an settings.merge()
                      vorbeigeht, waere der zweite Schreiber mit der
                      zweiten Zusicherung - der Fehler, an dem die
                      Einstellungsdatei dieses Projekts schon einmal
                      gescheitert ist (Kopf von src/settings.py).
      gelogen         Ein Schalter fuer etwas, das dieses Konto nicht
                      schreiben darf. Der Nutzer legt ihn um, nichts
                      passiert, und er sucht den Fehler bei sich.
      ungeprueft      Ein Wert, den die Gtk.Adjustment im Fenster
                      abgefangen haette und den ein JSON-Aufrufer
                      einfach schickt.

    Keine dieser Fragen braucht eine Anzeige, und deshalb steht hier
    keine - dieselbe Aufteilung wie zwischen test_settings_model.py und
    test_settings_headless.py.
"""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
SETTINGS_ROOT = ROOT / "settings"

# Die Antwort, die `hyprctl monitors all -j` auf einer Maschine mit einem
# Schirm gibt - gekuerzt auf die Felder, die displays.read_outputs()
# liest. Als Text und nicht als Objekt, weil genau der Text durch die
# Rohrleitung kommt und das Auspacken mitgemessen gehoert.
ONE_SCREEN = json.dumps([{
    "name": "eDP-1", "description": "Ein Schirm", "width": 1920,
    "height": 1080, "refreshRate": 60.0, "x": 0, "y": 0, "scale": 1.0,
    "transform": 0, "disabled": False,
    "availableModes": ["1920x1080@60.00Hz"],
}])


class _Answer:
    """Ein Ergebnis, wie subprocess.run es zurueckgibt."""

    def __init__(self, stdout: str = "", returncode: int = 0,
                 stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def screen_runner(answer: str = ONE_SCREEN):
    """Ein Ersatz fuer subprocess.run, der genau hyprctl beantwortet.

    Kein Prozess wird gestartet, und das ist nicht nur die Regel des
    Isolationswaechters: `hyprctl` steht in dessen NEVER_PASSTHROUGH,
    weil es die laufende Sitzung des Entwicklers anfasst.
    """
    seen: list[list[str]] = []

    def runner(argv, **_kwargs):
        seen.append(list(argv))
        return _Answer(answer)

    runner.seen = seen                                       # type: ignore
    return runner


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    """bridge.py mit vier umgelenkten Wurzeln.

    Dieselbe Form wie die `model`-Fixture nebenan, und aus demselben
    Grund muss der Pfad ueber monkeypatch kommen: src/ hat kein
    __init__.py, jedes Modul darin importiert flach, und ein
    liegengelassenes src/ auf sys.path laesst
    tests/src/test_placeholders.py durchgehen, wo es abbrechen soll.

    VIER Wurzeln, weil dieses Dokument aus vier Dateien gespeist wird:
    den Einstellungen des Kontos, den zwei Dateien der Maschine unter
    /etc/zepos, dem Abdruck der Leiste unter /usr/share/zepos und der
    Marke unter XDG_STATE_HOME. Bliebe eine davon stehen, liefe der Test
    gegen den Schreibtisch, auf dem er laeuft.
    """
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.syspath_prepend(str(SETTINGS_ROOT))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "zepos"))
    monkeypatch.setenv("ZEPOS_MACHINE_ROOT", str(tmp_path / "etc-zepos"))
    monkeypatch.setenv("ZEPOS_SYSTEM_ROOT", str(tmp_path / "share-zepos"))
    monkeypatch.setenv("ZEPOS_SYSTEMD_ETC", str(tmp_path / "etc"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    for name in list(sys.modules):
        if name.startswith("zepos_settings_gui") or name in (
                "brand", "displays", "monitors", "paths", "settings",
                "sizes", "theme", "update"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    from zepos_settings_gui import bridge as module

    return module


def read(bridge, capsys, argv, runner=None, stdin=None):
    """Einen Aufruf machen und sein Dokument auspacken."""
    code = bridge.main(argv, runner=runner or screen_runner(), stdin=stdin)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def imprint(tmp_path, **lists):
    """Den Abdruck der ausgelieferten Leiste hinlegen.

    Dieselbe Datei, die packaging/zepos-config/PKGBUILD schreibt -
    /usr/share/zepos/shipped-bar.json. Ohne sie ist die ausgelieferte
    Reihenfolge UNBEKANNT, und settings.bar_order() verwirft dann
    nichts; ein Test, der eine Ablehnung erwartet, misst ohne diese
    Datei das Gegenteil von dem, was er glaubt.
    """
    root = tmp_path / "share-zepos"
    root.mkdir(parents=True, exist_ok=True)
    (root / "shipped-bar.json").write_text(
        json.dumps(lists), encoding="utf-8")


# --------------------------------------------------------------------
# Das Dokument ist vollstaendig
# --------------------------------------------------------------------

def test_das_dokument_traegt_alle_sieben_seiten(bridge, capsys):
    code, document, _err = read(bridge, capsys, ["get"])

    assert code == 0
    from zepos_settings_gui import model

    assert [(page["name"], page["label"], page["icon"])
            for page in document["pages"]] == [tuple(entry)
                                               for entry in model.PAGES], (
        "das Dokument nennt andere Seiten als das Fenster - ein AGS-"
        "Fenster, das ihm folgt, haette einen Reiter zuviel oder zuwenig")
    assert document["schema"] == bridge.SCHEMA


def test_jedes_bedienelement_traegt_was_eine_oberflaeche_braucht(bridge,
                                                                 capsys):
    """Beschriftung, Einheit, Grenzen, Vorgabe, und ob es aenderbar ist.

    ALLE Felder an ALLEN Bedienelementen, auch leer. Ein fehlendes Feld
    und ein leeres Feld sind in JavaScript dasselbe, bis jemand
    Object.keys() darueber laufen laesst - und dann sind es zwei Formen
    desselben Bedienelements, von denen das Fenster eine nicht zeichnet.
    """
    _code, document, _err = read(bridge, capsys, ["get"])

    base = {"key", "kind", "label", "note", "value", "default", "scope",
            "immediate", "writable", "reason", "command"}
    kinds = {bridge.NUMBER, bridge.SWITCH, bridge.TEXT, bridge.CHOICE,
             bridge.COLOUR, bridge.ORDER, bridge.LAYOUT}
    seen: set[str] = set()

    for page in document["pages"]:
        for control in page["controls"]:
            assert base <= set(control), (
                f"{control.get('key')} fehlen "
                f"{sorted(base - set(control))}")
            assert control["kind"] in kinds, control["kind"]
            assert control["label"], (
                f"{control['key']} hat keine Beschriftung - im Fenster "
                "waere das eine Zeile ohne Namen")
            assert control["key"] not in seen, (
                f"{control['key']} steht zweimal im Dokument; ein `set` "
                "darauf traefe zwei Bedienelemente")
            seen.add(control["key"])
            assert control["scope"] in (bridge.ACCOUNT, bridge.MACHINE,
                                        bridge.DESKTOP)
            if not control["writable"]:
                assert control["reason"], (
                    f"{control['key']} ist nicht schreibbar und sagt "
                    "nicht warum")


def test_jede_farbe_jede_ausnahme_und_jede_aktualisierung_steht_darin(
        bridge, capsys):
    """Der Umfang, gegen die Quellen gerechnet statt gezaehlt.

    Eine Zahl im Test ("69 Farben") waere beim naechsten Eintrag in
    brand.py falsch, und zwar in der Richtung, die niemand bemerkt: der
    Test bleibt gruen, die Farbe fehlt im Fenster.
    """
    _code, document, _err = read(bridge, capsys, ["get"])
    import brand
    from zepos_settings_gui import model

    keys = {control["key"] for page in document["pages"]
            for control in page["controls"]}

    for name in brand.COLORS:
        assert f"{bridge.COLOUR_PREFIX}{name}" in keys, (
            f"{name} steht in brand.COLORS und nicht im Dokument")
    for dial in model.DIALS:
        assert f"{bridge.SIZES_VALUE}{dial.name}" in keys
    for name in (model.UPDATE_ENABLED, model.UPDATE_SCOPE,
                 model.UPDATE_NOTIFY, model.UPDATE_INTERVAL):
        assert f"{bridge.UPDATE_PREFIX}{name}" in keys
    for half in ("modules_left", "modules_right", "dock_pins"):
        assert f"{bridge.BAR_PREFIX}{half}" in keys
    assert {bridge.SIZES_SCALE, bridge.SIZES_MOTION, bridge.WEATHER_KEY,
            bridge.THEME_KEY} <= keys


def test_die_grenzen_im_dokument_sind_die_aus_model_py(bridge, capsys):
    """Und nicht abgeschriebene Zahlen.

    Das ist die eine Zusicherung, die diesen ganzen Befehl rechtfertigt:
    ein Fenster, das die Grenzen selbst kennt, ist die zweite
    Wahrheitsquelle, gegen die CONTRIBUTING.md Regel 2 geschrieben ist.
    """
    _code, document, _err = read(bridge, capsys, ["get"])
    from zepos_settings_gui import model
    import sizes

    controls = {control["key"]: control for page in document["pages"]
                for control in page["controls"]}

    scale = controls[bridge.SIZES_SCALE]
    assert scale["minimum"] == model.SCALE_MINIMUM
    assert scale["maximum"] == model.SCALE_MAXIMUM
    assert scale["step"] == model.SCALE_STEP
    assert scale["default"] == sizes.SCALE_DEFAULT

    for dial in model.DIALS:
        control = controls[f"{bridge.SIZES_VALUE}{dial.name}"]
        assert control["minimum"] == dial.minimum
        assert control["maximum"] == dial.maximum
        assert control["label"] == dial.label
        assert control["note"] == dial.note
        assert control["unit"] == sizes.TABLE[dial.name].unit, (
            "ohne die Einheit schriebe das Fenster `92px` in eine Datei, "
            "in der `92` stehen muss - oder umgekehrt")

    import brand

    for name, value in brand.COLORS.items():
        assert controls[f"{bridge.COLOUR_PREFIX}{name}"]["default"] == value


# --------------------------------------------------------------------
# Ein Schreibvorgang geht durch model.py
# --------------------------------------------------------------------

def test_ein_schreibvorgang_geht_durch_settings_merge(bridge, capsys,
                                                      tmp_path):
    """Gespeichert wird durch model.save(), also durch settings.merge().

    Geprueft wird nicht, DASS etwas dasteht, sondern dass das
    Uebrige noch dasteht: merge() ersetzt Abschnitte und behaelt den
    Rest, und ein Schreiber, der das Dokument selbst zusammensetzt,
    verliert genau hier die VPN-Einstellungen des Nutzers.
    """
    code, document, _err = read(bridge, capsys, [
        "set", json.dumps({"sizes.scale": 2.0,
                           "colors.accent": "#FF0000",
                           "weather.location": "Bochum"})])

    assert code == 0, document
    assert document["ok"] and not document["problems"]
    assert set(document["written"]) == {"sizes.scale", "colors.accent",
                                        "weather.location"}

    import settings as settings_file

    target = tmp_path / "zepos" / settings_file.FILENAME
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored["sizes"]["scale"] == 2.0
    assert stored["colors"]["accent"] == "#FF0000"
    assert stored["weather"]["location"] == "Bochum"
    assert stored["schema_version"] == settings_file.SCHEMA_VERSION, (
        "ohne die Schemaversion weist jeder versionierte Leser die Datei "
        "zurueck - genau das haben die zwei AGS-Masken einmal getan")
    assert "vpn" in stored, (
        "der Rest des Dokuments ist verschwunden; dann hat hier jemand "
        "an settings.merge() vorbeigeschrieben")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600, (
        "diese Datei kann einen VPN-Schluessel tragen")


def test_gespeichert_wird_sofort_und_erzeugt_wird_nicht(bridge, capsys,
                                                        tmp_path):
    """Statt dessen faellt die Marke, die die naechste Anmeldung liest.

    Der Kopf von model.py fuehrt die drei denkbaren Antworten aus. Diese
    hier ist die dritte, und ohne die Marke waere "wirksam beim
    naechsten Anmelden" eine Behauptung: nichts erzeugt von selbst neu.
    """
    marker = tmp_path / "state" / "zepos" / "regenerate-required"
    assert not marker.exists()

    runner = screen_runner()
    code, document, _err = read(bridge, capsys,
                                ["set", json.dumps({"sizes.scale": 2.0})],
                                runner=runner)

    assert code == 0
    assert marker.exists(), (
        "ohne die Marke bliebe die Aenderung in der Datei liegen, bis "
        "jemand von sich aus erzeugt")
    assert document["pending_regenerate"] is True
    assert runner.seen == [], (
        "ein Speichern hat den Generator gerufen - er beendet die Leiste "
        "und AGS mitten in der Arbeit des Nutzers")


def test_eine_ausnahme_auf_null_faellt_wieder_an_den_massstab(bridge, capsys,
                                                             tmp_path):
    """null ist eine ANGABE und kein fehlender Wert.

    Ohne diesen Weg waere jede der fuenf Ausnahmen eine Einbahnstrasse,
    und der Rueckweg fuehrte durch das Editieren der JSON-Datei - also
    durch genau das, wofuer es diese Oberflaeche gibt.
    """
    from zepos_settings_gui import model

    dial = model.DIALS[1]
    read(bridge, capsys, ["set", json.dumps({
        f"{bridge.SIZES_VALUE}{dial.name}": 120})])

    import settings as settings_file

    target = tmp_path / "zepos" / settings_file.FILENAME
    stored = json.loads(target.read_text(encoding="utf-8"))
    # Durch model.size_text() und nicht gegen "120px" geprueft: die
    # Einheit steht in sizes.TABLE, und sie ist nicht ueberall "px" -
    # ags-bar.template scheitert an `const BAR_THICKNESS = 92px`.
    assert stored["sizes"]["values"][dial.name] == model.size_text(
        dial.name, 120)

    read(bridge, capsys, ["set", json.dumps({
        f"{bridge.SIZES_VALUE}{dial.name}": None})])
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert dial.name not in stored["sizes"]["values"], (
        "die Ausnahme steht noch da - sie folgt dem Regler nicht mehr, "
        "und niemand sieht es der Zahl an")


def test_die_maschinendatei_wird_durch_update_apply_geschrieben(bridge,
                                                               capsys,
                                                               tmp_path):
    """Und nicht nur in ein JSON gelegt.

    Der Unterschied ist der ganze Punkt: die Datei allein waere ein Wert
    in einem Dokument, das systemd nie liest. Erst update.apply()
    schreibt die Zeitgeber-Ergaenzung und sagt systemd Bescheid.
    """
    runner = screen_runner()
    code, document, _err = read(
        bridge, capsys,
        ["set", json.dumps({"update.notify": "never"})], runner=runner)

    assert code == 0, document
    assert document["reports"][0]["written"] is True

    import update

    assert update.load()["notify"] == "never"
    assert ["systemctl", "daemon-reload"] in runner.seen, (
        "systemd wurde nichts gesagt; der Zeitgeber liefe weiter wie "
        "vorher, und der Befehl haette gemeldet, dass er geschrieben hat")


# --------------------------------------------------------------------
# Was nicht schreibbar ist, wird als solches gemeldet
# --------------------------------------------------------------------

def test_was_dieses_konto_nicht_schreiben_darf_steht_so_im_dokument(
        bridge, capsys, monkeypatch, tmp_path):
    """theme_writable() und update_writable() gibt es aus gutem Grund.

    Ein Fenster, das einen Schalter anbietet, den das System ablehnt,
    luegt den Nutzer an: er legt ihn um, nichts passiert, und er sucht
    den Fehler bei sich.

    Die Maschinenwurzel zeigt dafuer in ein Verzeichnis, dessen ELTERN
    es nicht gibt - genau die Lage, auf die theme_writable() mit "nein"
    antwortet, ohne dass irgendwo Rechte geaendert werden muessten.
    """
    monkeypatch.setenv("ZEPOS_MACHINE_ROOT",
                       str(tmp_path / "gibt-es-nicht" / "etc-zepos"))

    _code, document, _err = read(bridge, capsys, ["get"])
    controls = {control["key"]: control for page in document["pages"]
                for control in page["controls"]}

    for key in ("theme", "update.enabled", "update.scope", "update.notify",
                "update.schedule.interval"):
        control = controls[key]
        assert control["scope"] == bridge.MACHINE
        assert control["immediate"] is True, (
            "diese Werte haengen an keinem Speichern-Knopf - sie werden "
            "sofort geschrieben, notfalls durch pkexec")
        assert control["writable"] is False, (
            f"{key} liegt unter einer Wurzel, die es nicht gibt, und "
            "gilt trotzdem als schreibbar")
        assert control["reason"]
        assert control["command"], (
            "ohne den Befehl bleibt dem Nutzer nichts zum Abtippen, "
            "wenn es kein pkexec gibt")


def test_die_bildschirme_werden_gezeigt_und_nicht_angewandt(bridge, capsys):
    """Die Anordnung steht im Dokument - zum Lesen.

    displays.arm_and_apply() haelt einen laufenden Waechterprozess, der
    displays.CONFIRM_SECONDS Sekunden auf eine Bestaetigung wartet und
    sonst zuruecknimmt. Ein Befehl, der mit seiner Ausgabe endet, kann
    ihn nicht halten - er wuerde anwenden, sterben, der Waechter naehme
    zurueck, und das Fenster haette einen Schalter, der nachweislich
    nichts bewirkt.
    """
    runner = screen_runner()
    _code, document, _err = read(bridge, capsys, ["get"], runner=runner)

    control = next(control for page in document["pages"]
                   for control in page["controls"]
                   if page["name"] == "bildschirme")
    assert control["available"] is True
    assert [screen["name"] for screen in control["value"]] == ["eDP-1"]
    assert control["value"][0]["width"] == 1920
    assert control["writable"] is False and control["reason"]
    assert control["scope"] == bridge.DESKTOP
    assert runner.seen == [["hyprctl", "monitors", "all", "-j"]]


def test_ein_stummer_compositor_ist_eine_meldung_und_kein_absturz(bridge,
                                                                  capsys):
    """Die sechs anderen Seiten duerfen nicht mit ihm untergehen.

    Ein Einstellungsfenster ohne laufendes Hyprland ist genau das
    Fenster, das man zum Reparieren braucht.
    """
    def broken(argv, **_kwargs):
        raise OSError("hyprctl gibt es hier nicht")

    _code, document, _err = read(bridge, capsys, ["get"], runner=broken)

    control = document["pages"][1]["controls"][0]
    assert control["available"] is False
    assert "hyprctl" in control["reason"]
    assert len(document["pages"]) == 7


# --------------------------------------------------------------------
# Ungueltige Eingabe wird abgelehnt statt gespeichert
# --------------------------------------------------------------------

@pytest.mark.parametrize("changes, expected", [
    ({"sizes.scale": 40}, "liegt nicht zwischen"),
    ({"sizes.scale": "gross"}, "ist keine Zahl"),
    ({"sizes.motion": "ja"}, "ist kein Schalter"),
    ({"colors.accent": "rot"}, "kein #rrggbb"),
    ({"colors.gibtsnicht": "#ff0000"}, "gibt es nicht"),
    ({"sizes.values.STYLE_LAUNCHER_ROW_MIN_HEIGHT": 40}, "list-sizes"),
    ({"theme": "neonpink"}, "ist keins von"),
    ({"update.notify": "manchmal"}, "ist keins von"),
    ({"update.report_base": True}, "zepos-update --help"),
    ({"weather.location": 5}, "ist kein Ortsname"),
    ({"bar.modules_oben": []}, "es gibt"),
    ({"quatsch": 1}, "kein Schluessel dieser Oberflaeche"),
])
def test_ungueltige_eingabe_wird_abgelehnt(bridge, capsys, tmp_path,
                                           changes, expected):
    code, document, _err = read(bridge, capsys, ["set", json.dumps(changes)])

    assert code == 1, document
    assert document["ok"] is False
    assert document["written"] == []
    assert any(expected in problem for problem in document["problems"]), (
        f"{document['problems']} nennt {expected!r} nicht")

    import settings as settings_file

    assert not (tmp_path / "zepos" / settings_file.FILENAME).exists(), (
        "abgelehnt und trotzdem geschrieben")
    assert not (tmp_path / "state" / "zepos" / "regenerate-required").exists()


def test_eine_ablehnung_nimmt_das_ganze_dokument_mit(bridge, capsys,
                                                     tmp_path):
    """Ein halb angewandtes Dokument waere schlimmer als gar keins.

    Genau der Zustand, gegen den settings.merge() geschrieben wurde: ein
    Schreiber, der mittendrin aufgibt, hinterlaesst eine Datei, deren
    Zustand niemand angefordert hat.
    """
    code, document, _err = read(bridge, capsys, ["set", json.dumps({
        "weather.location": "Bochum", "sizes.scale": 99})])

    assert code == 1
    assert len(document["problems"]) == 1
    import settings as settings_file

    assert not (tmp_path / "zepos" / settings_file.FILENAME).exists(), (
        "der gueltige Teil ist gespeichert worden, der ungueltige nicht")


def test_ein_modulname_den_die_leiste_nicht_kennt_wird_abgelehnt(
        bridge, capsys, tmp_path):
    """Mit der Klage aus settings.py und keiner eigenen.

    settings.bar_order() entscheidet auch im Erzeuger, was auf der
    Leiste landet. Eine Oberflaeche, die einen Namen annimmt, den die
    Leiste danach wegwirft, ist die Leiste, die anders dasteht als das
    Fenster, in dem man sie eingestellt hat.
    """
    imprint(tmp_path, modules_left=["clock"], modules_right=["battery"],
            modules_available=["clock", "battery", "cpu"],
            dock_pins=[{"name": "firefox", "label": "Firefox"}])

    code, document, _err = read(bridge, capsys, ["set", json.dumps({
        "bar.modules_left": ["clock", "gibtsnicht"]})])

    import settings as settings_file

    assert code == 1
    assert settings_file.BAR_UNKNOWN in document["problems"][0]
    assert not (tmp_path / "zepos" / settings_file.FILENAME).exists()


def test_die_leiste_nennt_das_moegliche_und_die_auslieferung(bridge, capsys,
                                                             tmp_path):
    """Ohne beides koennte ein Fenster keine Auswahl anbieten.

    Und null ist dabei eine ANGABE - "wie ausgeliefert" - und keine
    Abwesenheit; deshalb steht die ausgelieferte Liste daneben und nicht
    an Stelle des Werts.
    """
    imprint(tmp_path, modules_left=["clock"], modules_right=["battery"],
            modules_available=["clock", "battery", "cpu"],
            dock_pins=[{"name": "firefox", "label": "Firefox"}])

    _code, document, _err = read(bridge, capsys, ["get"])
    controls = {control["key"]: control for page in document["pages"]
                for control in page["controls"]}

    left = controls["bar.modules_left"]
    assert left["value"] is None
    assert left["default"] == ["clock"]
    assert left["placeable"] == ["clock", "battery", "cpu"]
    assert left["effective"] == ["clock"]

    pins = controls["bar.dock_pins"]
    assert pins["placeable"] == ["firefox"], (
        "im Dock ist anheftbar, was ZepOS ausliefert - ein frei "
        "getippter Paketname waere ein Knopf, hinter dem nichts passiert")
    assert pins["labels"] == {"firefox": "Firefox"}


def test_eine_haelfte_auf_null_heisst_wieder_wie_ausgeliefert(bridge, capsys,
                                                              tmp_path):
    imprint(tmp_path, modules_left=["clock"], modules_right=["battery"],
            modules_available=["clock", "battery", "cpu"], dock_pins=[])

    read(bridge, capsys, ["set", json.dumps({
        "bar.modules_left": ["cpu", "clock"]})])
    read(bridge, capsys, ["set", json.dumps({"bar.modules_left": None})])

    import settings as settings_file

    stored = json.loads(
        (tmp_path / "zepos" / settings_file.FILENAME).read_text("utf-8"))
    assert stored["bar"]["modules_left"] is None, (
        "eine hier eingefrorene Liste saehe heute richtig aus und zeigte "
        "nach dem naechsten neuen Modul auf eine Leiste, die es nicht "
        "mehr gibt")


# --------------------------------------------------------------------
# Der Befehl selbst
# --------------------------------------------------------------------

@pytest.mark.parametrize("argv", [[], ["quatsch"], ["get", "zuviel"],
                                  ["set"], ["set", "{}", "zuviel"],
                                  ["apply", "zuviel"]])
def test_falsche_schalter_geben_zwei_und_die_gebrauchsanweisung(bridge,
                                                                capsys, argv):
    """Zwei und auf stderr, wie in src/cli.py.

    Die Ausnahme von der Regel "stdout ist immer JSON": falsche Schalter
    tippt ein Mensch und kein Fenster.
    """
    assert bridge.main(argv, runner=screen_runner()) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage: zepos-settings-gui --json" in captured.err


def test_ein_dokument_das_kein_json_ist_wird_als_json_beklagt(bridge, capsys):
    code, document, _err = read(bridge, capsys, ["set", "{kaputt"])
    assert code == 1
    assert "kein JSON" in document["problems"][0]

    code, document, _err = read(bridge, capsys, ["set", "[1, 2]"])
    assert code == 1
    assert "Objekt" in document["problems"][0]


def test_das_dokument_kommt_auch_von_stdin(bridge, capsys):
    """Damit eine Farbliste nicht durch die Argumentliste passen muss."""
    import io

    code, document, _err = read(
        bridge, capsys, ["set", "-"],
        stdin=io.StringIO(json.dumps({"weather.location": "Bochum"})))
    assert code == 0, document
    assert document["written"] == ["weather.location"]


def test_eine_unlesbare_einstellungsdatei_meldet_sich_als_json(bridge, capsys,
                                                               tmp_path):
    """Und nicht als Satz auf stderr.

    Der Aufrufer ist eine Oberflaeche: sie muss die Klage ANZEIGEN und
    nicht nur weiterreichen. Und sie darf nicht mit den Vorgaben
    aufgehen - beim ersten Speichern schriebe sie ueber das, was der
    Nutzer noch hat.
    """
    import settings as settings_file

    target = tmp_path / "zepos" / settings_file.FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{kein json", encoding="utf-8")

    code, document, err = read(bridge, capsys, ["get"])
    assert code == 1
    assert document["ok"] is False
    assert str(target) in document["problems"][0]
    assert err == ""


def test_apply_ruft_den_generator_und_raeumt_die_marke_weg(bridge, capsys,
                                                           tmp_path):
    """Und nicht generate_config.sh unmittelbar.

    zepos-generate ist der Befehl, den das Paket nach /usr/bin legt, und
    er findet seine Module selbst. Ein zweiter Aufrufweg waere ein
    zweiter Satz Fehler.
    """
    from zepos_settings_gui import model

    marker = model.request_regeneration_at_login()
    assert marker.exists()

    runner = screen_runner()
    code, document, _err = read(bridge, capsys, ["apply"], runner=runner)

    assert code == 0, document
    assert runner.seen == [list(model.GENERATE_COMMAND)]
    assert not marker.exists()
    assert document["pending_regenerate"] is False


def test_ein_fehlgeschlagener_lauf_laesst_die_marke_stehen(bridge, capsys):
    """Die Aenderung liegt weiter in der Datei und soll noch einmal
    versucht werden."""
    from zepos_settings_gui import model

    marker = model.request_regeneration_at_login()

    def failing(argv, **_kwargs):
        return _Answer(returncode=3, stderr="kaputt")

    code, document, _err = read(bridge, capsys, ["apply"], runner=failing)

    assert code == 1
    assert marker.exists()
    assert "3" in document["problems"][0]


# --------------------------------------------------------------------
# Und der Befehl liegt im Paket
# --------------------------------------------------------------------

def test_der_json_weg_wird_mit_dem_paket_ausgeliefert():
    """Ein Befehl, der im Baum laeuft und im Paket fehlt, ist kein Befehl.

    GEMESSEN am 19.08.2026: packaging/zepos-settings-gui/PKGBUILD legt
    das Modulverzeichnis ueber einen GLOB ab und den Vorschalter unter
    seinem NAMEN. Deshalb ist der JSON-Weg ein Schalter von
    zepos-settings-gui und keine zweite Datei in settings/bin - die laege
    im Tarball und nicht im Paket.

    Diese Pruefung liest das Rezept und aendert es nicht. Faellt der
    Glob eines Tages weg, faellt bridge.py aus dem Paket, und das
    AGS-Fenster stuende auf einer Installation ohne seine Datenquelle
    da - ohne dass irgendetwas es meldet.
    """
    recipe = (ROOT / "packaging" / "zepos-settings-gui" / "PKGBUILD").read_text(
        encoding="utf-8")
    assert 'zepos_settings_gui"/*.py' in recipe, (
        "das Rezept legt die Module nicht mehr ueber einen Glob ab - "
        "dann muss bridge.py dort namentlich stehen")
    assert (SETTINGS_ROOT / "zepos_settings_gui" / "bridge.py").is_file()
    assert "bin/zepos-settings-gui" in recipe


def test_der_json_weg_zieht_kein_gtk_herein():
    """`--json get` muss auf einer Maschine ohne GTK4 noch antworten.

    Also genau dort, wo man die Einstellungen zum Reparieren braucht.
    main.py faengt den Schalter deshalb VOR dem Import von app.py ab,
    und bridge.py selbst kennt `gi` nicht.
    """
    source = (SETTINGS_ROOT / "zepos_settings_gui" / "bridge.py").read_text(
        encoding="utf-8")
    assert "import gi" not in source
    assert "gi.repository" not in source

    main_source = (SETTINGS_ROOT / "zepos_settings_gui" / "main.py").read_text(
        encoding="utf-8")
    before = main_source.split("bridge.main")[0]
    assert "from .app import" not in before


# --------------------------------------------------------------------
# Die Prosa der Seiten steht in model.py und nicht in einem Fenster
# --------------------------------------------------------------------

def test_die_erklaerenden_texte_kommen_aus_model_py(bridge, capsys):
    """Ein Satz, zwei Fenster - und deshalb genau eine Quelle.

    Bis zum 19.08.2026 standen die Beschreibungen der Seiten als
    `Adw.PreferencesGroup(description=...)` in app.py, also in EINEM der
    beiden Fenster; der Bericht zu Aufgabe 29 nannte das ausdruecklich
    als das, was die Bruecke noch nicht hergibt. Abgeschrieben ins
    AGS-Fenster waeren sie zwei Fassungen desselben Satzes, und ab der
    ersten Umformulierung laese der Nutzer je nach Fenster eine andere
    Begruendung fuer denselben Regler.

    Geprueft wird gegen model.py und NICHT gegen einen hier getippten
    Text: eine Abschrift in der Zusicherung waere dieselbe Doppelung,
    nur an einer dritten Stelle.
    """
    _code, document, _err = read(bridge, capsys, ["get"])
    from zepos_settings_gui import model

    seiten = {page["name"]: page for page in document["pages"]}
    gruppen = {page["name"]: {gruppe["name"]: gruppe["note"]
                              for gruppe in page["groups"]}
               for page in document["pages"]}

    assert gruppen["groesse"][model.GROUP_SCALE] == model.NOTE_SCALE_GROUP
    assert gruppen["groesse"][model.GROUP_DIALS] == model.NOTE_DIALS_GROUP
    assert gruppen["groesse"][model.GROUP_MOTION] == model.NOTE_MOTION_GROUP
    assert (gruppen["groesse"][model.NOTE_SIZES_REST_TITLE]
            == model.NOTE_SIZES_REST)
    assert gruppen["wetter"][model.GROUP_WEATHER] == model.NOTE_WEATHER_GROUP
    assert gruppen["thema"][model.GROUP_THEME] == model.theme_note(
        model.theme_writable())
    assert gruppen["aktualisierung"][model.GROUP_UPDATE] == model.update_note(
        model.update_writable())
    assert (gruppen["aktualisierung"][model.NOTE_UPDATE_REST_TITLE]
            == model.NOTE_UPDATE_REST)

    # Und die Nebenzeilen der einzelnen Bedienelemente.
    elemente = {control["key"]: control for page in document["pages"]
                for control in page["controls"]}
    assert elemente["sizes.motion"]["note"] == model.NOTE_MOTION
    assert elemente["sizes.scale"]["note"] == model.NOTE_SCALE_RESET
    assert elemente["update.enabled"]["note"] == model.NOTE_UPDATE_ENABLED
    assert elemente["update.scope"]["note"] == model.NOTE_UPDATE_SCOPE
    assert elemente["update.notify"]["note"] == model.NOTE_UPDATE_NOTIFY

    # Jede Gruppe, die ein Bedienelement nennt, gibt es auch.
    for page in document["pages"]:
        namen = {gruppe["name"] for gruppe in page["groups"]}
        for control in page["controls"]:
            if control["group"]:
                assert control["group"] in namen, (
                    f"{control['key']} steht in der Gruppe "
                    f"{control['group']!r}, die seine Seite nicht fuehrt")
    assert seiten["farben"]["groups"], "die Farbgruppen fehlen"


def test_app_py_schreibt_die_texte_nicht_mehr_selbst():
    """Die andere Haelfte derselben Aussage.

    Ohne sie waere "es steht in model.py" auch dann wahr, wenn daneben
    in app.py noch eine zweite Fassung stuende - und genau die waere die
    eine, die niemand mitpflegt.
    """
    app = (SETTINGS_ROOT / "zepos_settings_gui" / "app.py").read_text(
        encoding="utf-8")
    for anfang in ("Ein Faktor auf alles, was Text ist",
                   "Fuenf Groessen mit einem eigenen Grund",
                   "Aus heisst wirklich aus",
                   "Ein Ortsname, eine Postleitzahl",
                   "Die Palette, unter der die eigenen Farben liegen",
                   "Diese Einstellungen gehoeren der MASCHINE"):
        assert anfang not in app, (
            f"app.py traegt {anfang!r} wieder selbst - dann gibt es den "
            "Satz zweimal")


# --------------------------------------------------------------------
# Die Bildschirme: der laufende Weg
# --------------------------------------------------------------------

class _FakeAttempt:
    """Ein Versuch, ohne Waechter und ohne hyprctl.

    displays.arm_and_apply() startet einen echten Kindprozess und ruft
    `hyprctl --batch`. Beides ist in dieser Suite verboten - hyprctl
    steht in NEVER_PASSTHROUGH des Isolationswaechters, weil es die
    laufende Sitzung des Entwicklers anfasst. Geprueft wird deshalb, WAS
    bridge.arm() dem Waechter uebergibt und in welcher Reihenfolge, nicht
    ob Hyprland gehorcht.
    """

    def __init__(self, code: int = 0) -> None:
        self.applied = ["hyprctl", "--batch", "keyword monitor eDP-1,..."]
        self.antwort = None
        self.code = code

    def keep(self):
        self.antwort = "behalten"
        return _FakeOutcome(self.code)

    def revert(self):
        self.antwort = "verwerfen"
        return _FakeOutcome(12)


class _FakeOutcome:
    def __init__(self, code: int) -> None:
        self.code = code
        self.report = "nachgestellt"

    @property
    def kept(self) -> bool:
        return self.code == 0


def _arm(bridge, monkeypatch, eingabe: str, versuch=None):
    """`--json arm` mit einem nachgestellten Waechter."""
    import io

    gesehen = {}
    attempt = versuch if versuch is not None else _FakeAttempt()

    def arm_and_apply(neu, alt, **kwargs):
        gesehen["neu"] = list(neu)
        gesehen["alt"] = list(alt)
        return attempt

    monkeypatch.setattr(bridge.displays, "arm_and_apply", arm_and_apply)

    stdin = io.StringIO(eingabe)
    stdout = io.StringIO()
    code = bridge.arm(runner=screen_runner(), stdin=stdin, stdout=stdout)
    zeilen = [json.loads(zeile) for zeile in stdout.getvalue().splitlines()
              if zeile.strip()]
    return code, zeilen, gesehen, attempt


def test_arm_wendet_an_und_schreibt_erst_nach_der_bestaetigung(
        bridge, monkeypatch, tmp_path):
    """Die Reihenfolge IST die Zusicherung dieser Seite.

    Erst der Waechter, dann das Anwenden, dann die Frage - und die Datei
    zuletzt. Eine schon geschriebene Datei braeuchte einen zweiten
    Rueckfall, und eine Sitzung, die danach mit ihr startet, faende
    keinen Schirm mehr, auf dem sie fragen koennte (Kopf von
    src/displays.py).
    """
    import displays

    ziel = displays.config_path()
    assert not ziel.exists()

    code, zeilen, gesehen, attempt = _arm(
        bridge, monkeypatch,
        json.dumps({"layout": [{"name": "eDP-1", "scale": 2.0}]})
        + "\nbehalten\n")

    assert code == 0
    # Zeile 1 meldet "scharf und angewandt", Zeile 2 das Ergebnis. Zwei
    # Zeilen und nicht eine: dazwischen laeuft die Frist, und das
    # Fenster muss in dieser Zeit etwas anzeigen koennen.
    assert len(zeilen) == 2, zeilen
    assert zeilen[0]["armed"] is True
    assert zeilen[0]["seconds"] == displays.CONFIRM_SECONDS
    assert attempt.antwort == "behalten"
    assert zeilen[1]["kept"] is True
    assert [item.scale for item in gesehen["neu"]] == [2.0]
    assert [item.scale for item in gesehen["alt"]] == [1.0], (
        "der Waechter bekommt den Stand VOR der Aenderung - sonst stellt "
        "er im Ernstfall genau das wieder her, was niemand sehen konnte")
    assert ziel.exists(), "behalten und nicht geschrieben"
    assert str(ziel) in zeilen[1]["written"]


def test_ohne_antwort_wird_nichts_geschrieben(bridge, monkeypatch):
    """Ein Dateiende ist ein "ich sehe nichts".

    Wer die Verbindung verliert, hat die neue Anordnung nicht gesehen -
    also gilt sie nicht. Dieselbe Vorgabe wie beim Schliess-Ergebnis der
    Rueckfrage im GTK-Fenster (screens.py, _ask).
    """
    import displays

    code, zeilen, _gesehen, attempt = _arm(
        bridge, monkeypatch,
        json.dumps({"layout": [{"name": "eDP-1", "enabled": True}]}) + "\n")

    assert code == 0
    assert attempt.antwort == "verwerfen"
    assert zeilen[-1]["kept"] is False
    assert not displays.config_path().exists()


def test_ein_waechter_der_schon_zurueckstellte_schlaegt_die_absicht(
        bridge, monkeypatch):
    """Seine Frist lief genau in diesem Moment ab.

    Dann gilt SEIN Ergebnis und nicht die Absicht: auf dem Schirm steht
    die alte Anordnung, also wird auch keine neue geschrieben.
    """
    import displays

    code, zeilen, _gesehen, _attempt = _arm(
        bridge, monkeypatch,
        json.dumps({"layout": [{"name": "eDP-1", "scale": 2.0}]})
        + "\nbehalten\n",
        versuch=_FakeAttempt(code=10))

    assert code == 1
    assert zeilen[-1]["kept"] is False
    assert not displays.config_path().exists()
    assert "zurueckgestellt" in zeilen[-1]["problems"][0]


@pytest.mark.parametrize("dokument, erwartet", [
    ({"layout": [{"name": "gibt-es-nicht"}]}, "gibt es hier nicht"),
    ({"layout": [{"name": "eDP-1", "quatsch": 1}]}, "kennt diese Oberflaeche"),
    ({"layout": [{"name": "eDP-1", "scale": "gross"}]}, "ist keine Zahl"),
    ({"layout": [{"name": "eDP-1", "enabled": 1}]}, "ist kein Schalter"),
    ({"layout": [{"enabled": True}]}, "braucht seinen `name`"),
    ({"layout": [{"name": "eDP-1", "enabled": False}]}, "Kein Bildschirm"),
    ({"schirme": []}, "erwartet wird"),
])
def test_eine_anordnung_die_nicht_geht_wird_gar_nicht_erst_scharf(
        bridge, monkeypatch, dokument, erwartet):
    """Abgelehnt VOR dem Waechter, nicht nach ihm.

    Der letzte Fall ist der, der zaehlt: eine Anordnung ohne
    eingeschalteten Schirm ist genau der schwarze Schirm, vor dem die
    ganze Vorrichtung schuetzen soll - displays.guard_plan() wirft
    dafuer NoScreenLeft, und diese Pruefung kommt ihr zuvor.
    """
    import displays

    code, zeilen, gesehen, _attempt = _arm(
        bridge, monkeypatch, json.dumps(dokument) + "\nbehalten\n")

    assert code == 1
    assert zeilen[-1]["ok"] is False
    assert zeilen[-1]["armed"] is False
    assert any(erwartet in klage for klage in zeilen[-1]["problems"]), zeilen
    assert gesehen == {}, "es wurde trotz Ablehnung ein Waechter scharfgemacht"
    assert not displays.config_path().exists()


def test_das_dokument_nennt_den_laufenden_weg_und_seine_bedingung(
        bridge, capsys):
    """`writable: false` bleibt wahr - fuer `set`.

    Die Anordnung geht nicht durch `--json set`, und das steht weiter
    so da. Was dazugekommen ist, ist der ZWEITE Weg: `armable` sagt, ob
    er hier offensteht, `arm` nennt ihn, `seconds` sagt, wie lange die
    Frist ist. Ein Fenster, das den Anwenden-Knopf zeigt, ohne dass es
    einen Waechter gibt, haette einen Knopf, der nur Fehlermeldungen
    kann.
    """
    _code, document, _err = read(bridge, capsys, ["get"])
    from zepos_settings_gui import bridge as modul

    control = next(control for page in document["pages"]
                   for control in page["controls"]
                   if page["name"] == "bildschirme")
    assert control["writable"] is False
    assert "set" in control["reason"] and modul.ARM in control["reason"]
    assert control["arm"] == [modul.OPTION, modul.ARM]
    assert control["armable"] is True
    assert control["seconds"] > 0
    assert control["scales"] and control["transforms"]
    # Die Modi kommen aus `hyprctl monitors all -j` und nicht aus einer
    # Liste hier: ein Fenster, das eine Aufloesung anbietet, die dieser
    # Schirm nicht kann, bietet einen schwarzen Schirm an.
    assert control["value"][0]["modes"] == [
        {"width": 1920, "height": 1080, "refresh": 60.0,
         "label": "1920 x 1080, 60 Hz"}]


def test_ohne_waechter_wird_der_weg_nicht_angeboten(bridge, capsys,
                                                    monkeypatch):
    """Kein Rueckfall auf "dann eben ohne Waechter"."""
    def kein_waechter():
        raise FileNotFoundError("zepos-displays-guard fehlt")

    monkeypatch.setattr(bridge.displays, "guard_command", kein_waechter)
    _code, document, _err = read(bridge, capsys, ["get"])

    control = next(control for page in document["pages"]
                   for control in page["controls"]
                   if page["name"] == "bildschirme")
    assert control["armable"] is False
