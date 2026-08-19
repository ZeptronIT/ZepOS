# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Einstellungsfenster als AGS-Fenster - was daran nachpruefbar ist.

WAS HIER GEMESSEN WIRD, UND WAS AUSDRUECKLICH NICHT
    Diese Datei startet kein Fenster. Sie prueft die drei Zusagen, an
    denen dieses Fenster haengt und die man ohne Anzeige pruefen kann:

      es benutzt den Bausatz    zepRow/zepButton/zepToggle/
                                zepSectionLabel/zepStateHeader aus
                                ags-kit.template - und baut sich keine
                                zweite Formensprache daneben. Genau das
                                war der Mangel, den der Bausatz behoben
                                hat (45 Knopfregeln in 41 Klassen,
                                keine gemeinsame - siehe dessen Kopf).
      alle sieben Seiten        die Seiten kommen aus model.PAGES ueber
                                das Dokument; was die Vorlage selbst
                                fuehrt, ist die Zuordnung Seite ->
                                Nerd-Font-Zeichen, und die muss
                                vollstaendig sein.
      eine gesperrte Zeile      zeigt ihren Grund. `writable: false`
                                ohne sichtbaren Grund ist ein Regler,
                                den das System still ablehnt.

    Ob das Fenster aufgeht, misst tests/render/ mit einem
    verschachtelten Compositor - hier laeuft kein Anzeigegeraet.
"""
import re
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[2]
SRC = WURZEL / "src"
VORLAGE = SRC / "templates" / "ags-settings.template"
SETTINGS = WURZEL / "settings"


def _text() -> str:
    return VORLAGE.read_text(encoding="utf-8")


def _code() -> str:
    """Die Vorlage ohne ihre Zeilenkommentare.

    Dieselbe Vorsichtsmassnahme wie in tests/src/test_modal_rule.py:
    jede Datei dieses Baums ERKLAERT, was sie nicht tut, und eine Suche
    nach einem Namen wuerde von der Erklaerung wahr, in der steht, dass
    es ihn nicht gibt.
    """
    return "\n".join(zeile for zeile in _text().splitlines()
                     if not zeile.lstrip().startswith("//"))


@pytest.fixture
def model(monkeypatch):
    """model.py, ohne dass ein Test die echten Wurzeln anfasst."""
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.syspath_prepend(str(SETTINGS))
    for name in list(sys.modules):
        if name.startswith("zepos_settings_gui") or name in (
                "brand", "displays", "monitors", "paths", "settings",
                "sizes", "theme", "update"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    from zepos_settings_gui import model as modul

    return modul


@pytest.fixture
def bridge_modul(monkeypatch, model):
    from zepos_settings_gui import bridge as modul

    return modul


def test_die_vorlage_gibt_es_und_der_erzeuger_kennt_sie():
    """Eine Vorlage ohne Zweig im Erzeuger entsteht auf keiner Maschine."""
    assert VORLAGE.is_file()
    erzeuger = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    zweig = re.search(r"\n\s*ags-settings\)\s*\n(.*?)\n\s*;;", erzeuger,
                      re.DOTALL)
    assert zweig, "src/generate_config.sh hat keinen Zweig `ags-settings)`"
    assert 'CONFIG_FILE="Settings.tsx"' in zweig.group(1)
    assert 'ags/widget' in zweig.group(1)


def test_das_fenster_baut_aus_dem_bausatz_und_nicht_daneben():
    """Der Bausatz ist eine Schnittstelle, keine Bitte.

    GEZAEHLT wird das, was ein eigenes Aussehen ERZEUGEN wuerde: ein
    selbstgebauter Knopf und eine selbstgebaute Zeile. Gtk.Box,
    Gtk.Label und die vier Eingabefelder sind ausdruecklich erlaubt -
    der Bausatz kennt keinen Drehknopf und keine Auswahlliste, und ein
    Fenster, das Zahlen einstellt, braucht beide.
    """
    code = _code()
    for teil in ("zepRow", "zepButton", "zepToggle", "zepSectionLabel",
                 "zepStateHeader", "zepDivider"):
        assert teil + "(" in code, (
            f"{teil} wird nicht benutzt - dann hat dieses Fenster fuer "
            f"das Bauteil eine eigene Loesung")

    assert 'from "../utils/kit"' in code

    knoepfe = re.findall(r"new Gtk\.Button\s*\(", code)
    assert knoepfe == [], (
        f"{len(knoepfe)} selbstgebaute Gtk.Button - jeder Knopf dieses "
        "Systems kommt aus zepButton(), damit es EINE Hoehe, EINEN "
        "Radius und vier Rollen gibt (siehe den Kopf von "
        "ags-kit.template)")
    assert "new Gtk.Switch" not in code, (
        "ein selbstgebauter Schalter statt zepToggle()")

    # Und keine zweite Zeilenform: die Klassen dieses Fensters heissen
    # alle set-*, und keine davon ist eine Zeile oder ein Knopf.
    # Die Ausnahme "zep-shell-page" ist am 20.08.2026 weggefallen: die
    # Klasse gab es nur fuer den Mindestbreiten-Boden der Schale, und der
    # wird seither in createOverlayWindow() gemessen statt im Stylesheet
    # geschrieben (`config.fuelltDieSprosse`, ags-overlay-utils.template).
    # Eine Erlaubnisliste fuer eine Klasse, die es nicht mehr gibt, waere
    # die naechste Stelle, an der jemand ihr wieder begegnet.
    eigene = set(re.findall(r'add_css_class\("([^"]+)"\)', code))
    for name in eigene:
        assert name.startswith("set-"), (
            f"{name!r} ist keine set-*-Klasse dieses Fensters - eine Zeile "
            "oder ein Knopf mit eigener Klasse waere die zweite "
            "Formensprache")
        assert not name.endswith(("-row", "-btn", "-button")), (
            f"{name!r} klingt nach einer eigenen Zeile oder einem eigenen "
            "Knopf - beides kommt aus dem Bausatz")


def test_kein_zepbutton_umschliesst_eine_zeprow():
    """Der Fund vom 19.08.2026 (Aufgabe 15/16) wird nicht wiederholt.

    Beide Bauteile malen ihre eigene Flaeche; verschachtelt entsteht
    "Kasten in Kasten". Eine anklickbare Zeile bekommt ihr `aktion`
    seither von zepRow selbst. tests/src/test_kit_nesting.py haelt
    dieselbe Regel ueber alle Vorlagen; hier steht sie noch einmal fuer
    die eine, die neu dazugekommen ist.
    """
    code = _code()
    assert not re.search(r"set_child\s*\(\s*zepRow\s*\(", code)


def test_jede_seite_der_bruecke_hat_ihr_zeichen(model):
    """Die Seiten kommen aus dem Dokument - die ZEICHEN nicht.

    `page.icon` im Dokument ist ein freedesktop-Symbolname
    ("video-display-symbolic"), den das GTK-Fenster an Adw.ViewStack
    weiterreicht; eine Nerd-Font-Oberflaeche kann ihn nicht zeichnen.
    Die Zuordnung steht deshalb in der Vorlage - und muss vollstaendig
    sein, sonst traegt eine Seite das Zahnrad der Vorgabe.

    GERECHNET gegen model.PAGES und nicht abgeschrieben: eine achte
    Seite dort faellt hier auf.
    """
    zeichen = re.search(r"const SEITEN_ZEICHEN[^=]*=\s*\{(.*?)\n\}",
                        _text(), re.DOTALL)
    assert zeichen, "SEITEN_ZEICHEN steht nicht mehr in der Vorlage"
    genannt = set(re.findall(r"^\s*(\w+):", zeichen.group(1), re.M))

    assert genannt == set(model.PAGE_NAMES), (
        "die Zeichentabelle und model.PAGES sagen Verschiedenes: "
        f"{sorted(genannt ^ set(model.PAGE_NAMES))}")


def test_jede_art_die_die_bruecke_kennt_wird_gezeichnet(bridge_modul):
    """Eine geschlossene Liste auf beiden Seiten derselben Naht.

    bridge.py fuehrt `kind` als geschlossene Liste, "damit ein Fenster
    fuer jede genau einen Zeichner hat und ein unbekanntes `kind` ein
    Fehler ist und keine leere Zeile". Diese Zusicherung haelt die
    andere Haelfte: fuer jede Art, die die Bruecke ausgibt, muss die
    Vorlage einen Zweig haben.
    """
    code = _code()
    arten = {bridge_modul.NUMBER, bridge_modul.SWITCH, bridge_modul.TEXT,
             bridge_modul.CHOICE, bridge_modul.COLOUR, bridge_modul.ORDER,
             bridge_modul.LAYOUT}
    fehlend = [art for art in sorted(arten) if f'"{art}"' not in code]
    assert fehlend == [], (
        f"das Fenster kennt {fehlend} nicht - diese Bedienelemente "
        "blieben leer, und eine Einstellung, die da ist und die niemand "
        "findet, ist schlimmer als eine, die fehlt")

    # Und eine Art, die es NICHT kennt, wird gezeigt statt verschluckt.
    assert "unbekanntesElement" in code
    assert "set-unknown" in code


def test_eine_gesperrte_zeile_zeigt_ihren_grund_und_ihren_befehl():
    """Der ganze Zweck von `reason` und `command`.

    Ein Fenster, das einen Schalter anbietet, den das System ablehnt,
    luegt den Nutzer an: er legt ihn um, nichts passiert, und er sucht
    den Fehler bei sich (Kopf von bridge.py).
    """
    code = _code()
    assert "element.writable ? element.note : element.reason" in code, (
        "die Nebenzeile einer gesperrten Zeile traegt nicht mehr den "
        "Grund")
    assert "element.command.join" in code, (
        "der Befehl zum Abtippen wird nicht mehr gezeigt - ohne pkexec "
        "ist er der einzige Weg")
    assert "set_sensitive(false)" in code, (
        "ein gesperrtes Bedienelement laesst sich weiter anfassen")
    assert "ICONS.gesperrt" in code, (
        "eine gesperrte Zeile sieht aus wie jede andere")


def test_das_fenster_schreibt_nur_durch_die_bruecke():
    """Zwei Wege zu einer Einstellung, die verschiedene Dateien
    anfassen, sind zwei Einstellungen.

    Das ist der Fehler, an dem die Einstellungsdatei dieses Projekts
    schon einmal gescheitert ist (Kopf von src/settings.py), und der
    Grund, aus dem es die Bruecke ueberhaupt gibt.
    """
    code = _code()
    assert "user-settings.json" not in code, (
        "das Fenster kennt die Einstellungsdatei selbst - dann schreibt "
        "es frueher oder spaeter hinein")
    assert "settings.py" not in code

    # Jeder Prozessstart nennt entweder BEFEHL selbst oder die eine
    # Zeile, die aus BEFEHL gebaut ist. Der Umweg ueber `bash -c` hat
    # einen Grund, der am Kopf von bruecke() steht (execAsync verwirft
    # bei Rueckgabewert 1 und reicht STDERR weiter, waehrend die Klage
    # auf stdout steht); die Shell ist dabei kein zweites Werkzeug,
    # sondern die Roehre um dasselbe.
    starts = (re.findall(r"execAsync\(\[([^\]]*)\]", code)
              + re.findall(r"subprocess\(\s*\[([^\]]*)\]", code))
    assert len(starts) >= 3, f"nur {len(starts)} Prozessstarts gefunden"
    for start in starts:
        assert "BEFEHL" in start or "zeile" in start, (
            f"[{start}] startet etwas, das nicht aus BEFEHL gebaut ist")
    # Und die Zeile selbst wird aus BEFEHL gebaut, nicht getippt.
    assert re.search(r"const zeile = \[BEFEHL, JSON_SCHALTER", code)
    assert "GLib.shell_quote" in code, (
        "die Argumente werden von Hand in Anfuehrungszeichen gesetzt - "
        "eines davon ist ein JSON-Dokument voller Anfuehrungszeichen")


def test_kein_wert_der_aus_einer_vorlage_kommen_koennte_ist_getippt():
    """CONTRIBUTING.md Regel 2, an der Vorlage gemessen.

    Keine Farbe, keine Grenze, kein Vorgabewert: alles kommt aus dem
    Dokument oder aus einem Platzhalter. Die Zahlen, die uebrig sind,
    sind Abstaende zwischen Widgets - dieselbe Sprosse, die jede andere
    AGS-Vorlage dieses Baums als blanke Zahl schreibt.
    """
    code = _code()
    farben = re.findall(r"#[0-9a-fA-F]{6}\b", code)
    erlaubt = {"#000000"}  # der Rueckfall der Farbprobe, keine Marke
    assert set(farben) <= erlaubt, (
        f"feste Farben in der Vorlage: {sorted(set(farben) - erlaubt)}")

    zeichen = re.findall(r'"\{\{ICON_[A-Z_0-9]+\}\}"', _text())
    assert len(zeichen) >= 15, (
        f"nur {len(zeichen)} Zeichen kommen aus icons_db.py - der Rest "
        "waere getippt")


def test_der_laufende_weg_fuer_die_bildschirme_wird_wirklich_gehalten():
    """Warum diese Seite hier bedienbar ist und im Befehl nicht.

    `--json arm` bleibt stehen, solange der Waechter laeuft; ein
    Fenster, das ihn nur startet und die Antwort nicht schreibt, haette
    genau den Schalter, der nachweislich nichts bewirkt.
    """
    code = _code()
    assert 'subprocess(' in code, (
        "die Anordnung wird nicht ueber einen LAUFENDEN Prozess "
        "angewandt - execAsync endet mit seiner Ausgabe, und der "
        "Waechter naehme zurueck")
    assert re.search(r"\.write\(\s*wort", code), (
        "die Antwort wird dem Waechterprozess nicht geschrieben")
    assert "BEHALTEN" in code and "VERWERFEN" in code
    assert "armable" in code, (
        "der Anwenden-Knopf wird auch dann gezeigt, wenn es keinen "
        "Waechter gibt")


def test_app_ts_haengt_das_fenster_ein_und_faengt_vpn_settings_vorher_ab():
    """Ein Fenster, das niemand oeffnen kann, ist keines.

    Und die Reihenfolge im requestHandler ist die Falle: "vpn-settings"
    ENTHAELT "settings", also faenge ein frueher stehender
    settings-Zweig das andere Fenster mit ab.
    """
    app = (SRC / "templates" / "ags-config.template").read_text(
        encoding="utf-8")
    assert 'import Settings from "./widget/Settings"' in app
    assert "widgets.settings = fenster" in app

    vpn = app.index('reqStr.includes("vpn-settings")')
    settings = app.index('reqStr.includes("settings")')
    assert vpn < settings, (
        "der settings-Zweig steht vor dem vpn-settings-Zweig und faengt "
        "dessen Anfragen mit ab")
    assert 'name.startsWith("settings:")' in app, (
        "es gibt keinen Weg auf eine EINZELNE Seite des Fensters")


def test_die_flaeche_ist_als_glas_angemeldet():
    """Eine Flaeche ohne layerrule bleibt scharf, und zwar lautlos.

    tests/src/test_glass.py prueft beide Richtungen fuer ALLE Flaechen,
    indem es style_definition.py wirklich importiert - das ist die
    Messung. Hier steht die eine Flaeche, die mit diesem Fenster
    dazugekommen ist, noch einmal namentlich, damit ein Suchen nach
    "settings" sie findet; gelesen und nicht importiert, weil dieser
    Import in dieser Datei den Isolationswaechter reizt (er legt
    __pycache__ neben die Quelle).
    """
    quelle = (SRC / "style_definition.py").read_text(encoding="utf-8")
    # Bis zur schliessenden Klammer AM ZEILENANFANG: die Kommentare in
    # der Liste tragen selbst Klammern ("(ags-power-button.template)"),
    # und ein Schnitt an der ersten schneidet mitten hinein.
    liste = quelle.split("GLASS_LAYERS = (")[1].split("\n)")[0]
    assert '"settings",' in liste, (
        "der Namensraum settings steht nicht in GLASS_LAYERS - das "
        "Fenster bekaeme keine Unschaerfe")
    platten = quelle.split("GLASS_PLATES = {")[1].split("\n}")[0]
    assert '"settings": _OVERLAY,' in platten
