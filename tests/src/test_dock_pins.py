# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Anheftungen des Nutzers - die Schicht unter dem Rechtsklick-Menue.

WORUM ES GEHT, MIT DATUM
    Der Nutzer will Anwendungen per Rechtsklick anheften und abnehmen,
    und spaeter eine Startseite mit seinen Programmen. Bis zum
    20.08.2026 scheiterten alle drei an derselben Stelle: die
    angehefteten Anwendungen waren eine ERZEUGTE Konstante in
    src/templates/ags-dock.template

        const PINNED: string[] = []  // zepos-pinned

    gefuellt beim Erzeugen aus der Paketliste. "bar.dock_pins" in
    user-settings.json konnte sie zwar ersetzen, und genau das war das
    Problem - ein Ersatz kann drei Faelle tragen und traegt nur zwei.

DIE DREI FAELLE, UND DER DRITTE IST DER, AN DEM ENTWUERFE SCHEITERN
    anheften        etwas kommt dazu, das die Vorgabe nicht kennt. Ging
                    vorher GAR NICHT: bar_order() prueft gegen die
                    ausgelieferte Auswahl, also fiel jeder andere Name
                    mit "kennt diese Leiste nicht" heraus.
    abnehmen        etwas aus der VORGABE verschwindet. Die Nutzerliste
                    muss also auch ein "nein" ausdruecken koennen und
                    nicht nur ein "ja".
    Vorgabe aendert ZepOS liefert in einer neuen Fassung eine andere
    sich            Anwendung mit. Eine Liste, die die Vorgabe ersetzt,
                    friert den Schreibtisch auf den Tag ein, an dem
                    jemand zum ersten Mal etwas angeheftet hat: seine
                    Liste nennt das Neue nicht, und sie kann gar nicht
                    bemerken, dass die Vorgabe sich geaendert hat.

    Die Loesung steht in src/settings.py bei BAR_BASELINE: neben der
    Wahl steht die Auslieferung, GEGEN DIE sie fiel. Damit ist
    "abgewaehlt" (in der Vorgabe von damals, nicht in der Wahl) von "neu
    geliefert" (in der heutigen Auslieferung, nicht in der Vorgabe von
    damals) unterscheidbar, ohne dass eine dritte Liste gepflegt werden
    muss.

WARUM DIESE DATEI EIGENE ANWENDUNGSVERZEICHNISSE HINLEGT
    settings.pinnable() fragt src/desktop_entries.py, was auf DIESER
    Maschine installiert ist. Ohne umgelenktes XDG_DATA_HOME und
    XDG_DATA_DIRS waere das der Schreibtisch des Entwicklers, und diese
    Zusicherungen haetten je nach Rechner ein anderes Ergebnis - ein
    Test, dessen Antwort die Maschine gibt, misst die Maschine.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Ein Anwendungseintrag, wie ihn eine Maschine traegt. Dieselbe Vorlage
# wie in tests/settings/test_settings_headless.py und aus demselben
# Grund: die Faelle, auf die es ankommt, unterscheiden sich in zwei
# Zeilen.
ENTRY = """[Desktop Entry]
Type=Application
Name={label}
Exec={name}
Terminal=false
NoDisplay={nodisplay}
"""


@pytest.fixture
def maschine(monkeypatch, tmp_path):
    """src/ auf dem Pfad, und beide Wurzeln umgelenkt.

    Dieselbe Fixture-Form wie in tests/settings/test_settings_model.py,
    einschliesslich des Herunternehmens danach: src/ hat kein
    __init__.py, und ein liegengelassener Pfad laesst
    tests/src/test_placeholders.py durchgehen, wo es abbrechen soll.
    """
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "zepos"))
    monkeypatch.setenv("ZEPOS_SYSTEM_ROOT", str(tmp_path / "system"))
    # Kein Datenverzeichnis ausser den hier hingelegten. Der zweite
    # Schluessel ist der wichtigere: ohne ihn stuende die Vorgabe der
    # Spezifikation da (/usr/local/share:/usr/share), also die
    # Anwendungen des Entwicklers.
    (tmp_path / "data" / "applications").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "leer"))
    for name in list(sys.modules):
        if name in ("settings", "paths", "apps", "desktop_entries", "sizes"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    import apps
    import desktop_entries
    import settings

    return apps, settings, desktop_entries


def liefere(tmp_path, *namen: str) -> None:
    """Was ZepOS auf dieser "Maschine" ausliefert.

    Der Abdruck, den package() von zepos-apps schreibt - dieselbe Datei,
    die apps.shipped() auf einer Installation liest. Nicht das Rezept:
    ein Test, der packaging/ nachbaut, misst den Parser und nicht die
    Entscheidung.
    """
    root = tmp_path / "system"
    root.mkdir(parents=True, exist_ok=True)
    (root / "shipped-applications").write_text(
        "\n".join(namen) + "\n", encoding="utf-8")
    (root / "own-applications").write_text("", encoding="utf-8")


def installiere(tmp_path, *namen: str, versteckt: tuple[str, ...] = ()) -> None:
    """Anwendungseintraege in das umgelenkte Datenverzeichnis legen."""
    share = tmp_path / "data" / "applications"
    share.mkdir(parents=True, exist_ok=True)
    for name in namen:
        (share / f"{name}.desktop").write_text(
            ENTRY.format(name=name, label=name.title(),
                         nodisplay="true" if name in versteckt else "false"),
            encoding="utf-8")


def dokument(pins=None, baseline=None) -> dict:
    """Eine Einstellungsdatei mit genau diesem Leisten-Abschnitt.

    `schema_version` steht dabei, weil settings.load() sie verlangt -
    und weil ein Dokument ohne sie in apps.pinned() den kurzen Weg
    naehme (`if not document`), also die Auslieferung unveraendert
    zurueckgaebe und nichts von dem messen wuerde, was hier gemeint ist.
    """
    return {"schema_version": 1,
            "bar": {"modules_left": None, "modules_right": None,
                    "dock_pins": pins, "dock_baseline": baseline}}


# --------------------------------------------------------------------
# Fall 1: anheften, was die Vorgabe nicht kennt
# --------------------------------------------------------------------

def test_eine_anwendung_die_zepos_nicht_ausliefert_laesst_sich_anheften(
        maschine, tmp_path):
    """Der Fall, der vor dem 20.08.2026 nicht abgelehnt, sondern
    unmoeglich war.

    settings.bar_order() prueft gegen `placeable`, und fuer die
    Anheftungen war das die AUSGELIEFERTE Auswahl. Ein Programm, das der
    Nutzer selbst installiert hat, fiel damit heraus - mit einer Klage
    daneben, die ihn in die falsche Datei schickte.
    """
    apps, _settings, _entries = maschine
    liefere(tmp_path, "firefox", "kitty")
    installiere(tmp_path, "firefox", "kitty", "inkscape")

    namen, verworfen = apps.pinned(
        dokument(pins=["firefox", "inkscape", "kitty"],
                 baseline=["firefox", "kitty"]),
        tmp_path / "system")

    assert namen == ["firefox", "inkscape", "kitty"], (
        "eine selbst installierte Anwendung laesst sich nicht anheften - "
        "dann kann es das Rechtsklick-Menue nicht geben")
    assert verworfen == []


def test_ein_name_ohne_anwendungseintrag_wird_verworfen_und_genannt(
        maschine, tmp_path):
    """Und die Gegenprobe: erlaubt ist nicht alles, sondern das, was es
    gibt.

    Ein Knopf im Dock, der nichts oeffnet, ist nach Spec 7.4 der
    schlimmste Fehler, den ZepOS erzeugen kann - weil ihn niemand
    meldet.
    """
    apps, settings, _entries = maschine
    liefere(tmp_path, "firefox")
    installiere(tmp_path, "firefox")

    namen, verworfen = apps.pinned(
        dokument(pins=["firefox", "gibtesnicht"], baseline=["firefox"]),
        tmp_path / "system")

    assert namen == ["firefox"]
    assert verworfen == [("gibtesnicht", settings.BAR_GONE)]


def test_ein_dienst_ohne_fenster_ist_nicht_anheftbar(maschine, tmp_path):
    """NoDisplay=true unterscheidet einen DIENST von einer Anwendung.

    Genau daran ist am 12.08.2026 das Zahnrad im Fuss aufgefallen, das
    sich "garnicht oeffnen" liess: xdg-desktop-portal-gnome traegt die
    Markierung. Was ZepOS ausliefert, bleibt trotzdem anheftbar - das
    Dock selbst laesst es dann weg, und diese Entscheidung faellt dort,
    wo GIO danebensteht.
    """
    _apps, settings, entries = maschine
    installiere(tmp_path, "portal-dienst", versteckt=("portal-dienst",))

    assert entries.installed("portal-dienst") is False
    assert entries.names() == []
    assert settings.pinnable([]) == []


# --------------------------------------------------------------------
# Fall 2: eine Vorgabe abwaehlen
# --------------------------------------------------------------------

def test_eine_ausgelieferte_anwendung_laesst_sich_abwaehlen(maschine,
                                                            tmp_path):
    """Das "nein". Es steht nicht als eigener Schluessel in der Datei,
    sondern als Fehlen in der Wahl - lesbar, WEIL die Vorgabe von damals
    danebensteht.
    """
    apps, _settings, _entries = maschine
    liefere(tmp_path, "firefox", "kitty", "loupe")
    installiere(tmp_path, "firefox", "kitty", "loupe")

    namen, verworfen = apps.pinned(
        dokument(pins=["firefox", "loupe"],
                 baseline=["firefox", "kitty", "loupe"]),
        tmp_path / "system")

    assert namen == ["firefox", "loupe"], (
        "das abgewaehlte kitty ist zurueck - dann ist Abnehmen keine "
        "Bedienung, sondern eine Anzeige, die beim naechsten Erzeugen "
        "wieder verschwindet")
    assert verworfen == []


def test_das_abgewaehlte_bleibt_auch_weg_wenn_die_vorgabe_waechst(maschine,
                                                                  tmp_path):
    """Der Fall, in dem beide Regeln zugleich greifen.

    Eine Vorgabe ist abgewaehlt, eine andere ist neu dazugekommen. Ein
    Entwurf, der nur EINE der beiden Aussagen ableiten kann, holt hier
    entweder das Abgewaehlte zurueck oder unterschlaegt das Neue.
    """
    apps, _settings, _entries = maschine
    liefere(tmp_path, "firefox", "kitty", "loupe", "papers")
    installiere(tmp_path, "firefox", "kitty", "loupe", "papers")

    namen, _verworfen = apps.pinned(
        dokument(pins=["firefox", "loupe"],
                 baseline=["firefox", "kitty", "loupe"]),
        tmp_path / "system")

    assert namen == ["firefox", "loupe", "papers"], (
        "kitty war abgewaehlt und muss weg bleiben, papers ist neu und "
        "muss erscheinen - beides aus derselben Datei abgelesen")


# --------------------------------------------------------------------
# Fall 3: die Vorgabe aendert sich
# --------------------------------------------------------------------

def test_eine_neu_ausgelieferte_anwendung_erreicht_auch_wer_umsortiert_hat(
        maschine, tmp_path):
    """DIE PRUEFUNG, DERENTWEGEN ES BAR_BASELINE GIBT.

    Ohne die hinterlegte Vorgabe sieht dieser Fall am selben Tag richtig
    aus - dieselben Namen, dieselbe Reihenfolge - und wird erst Wochen
    spaeter falsch: bei der naechsten Fassung von ZepOS. Wer einmal
    etwas angefasst hat, saehe die neue Anwendung nie, und er koennte
    nicht einmal sagen, wann er das bestellt hat.
    """
    apps, _settings, _entries = maschine
    liefere(tmp_path, "firefox", "kitty", "papers")
    installiere(tmp_path, "firefox", "kitty", "papers")

    namen, _verworfen = apps.pinned(
        dokument(pins=["kitty", "firefox"], baseline=["firefox", "kitty"]),
        tmp_path / "system")

    assert namen == ["kitty", "firefox", "papers"]


def test_das_neue_kommt_ans_ende_und_nicht_unter_den_mauszeiger(maschine,
                                                                tmp_path):
    """Die Reihenfolge des Nutzers bleibt Zeichen fuer Zeichen stehen.

    An seinen Platz in der ausgelieferten Reihenfolge einsortiert waere
    huebscher - die Auswahl ist dort nach Aufgaben gruppiert. Es waere
    aber auch die einzige Stelle, an der sich die Reihenfolge des
    Nutzers von selbst aendert, und zwar unter dem Mauszeiger.
    """
    apps, _settings, _entries = maschine
    liefere(tmp_path, "a", "neu", "b", "c")
    installiere(tmp_path, "a", "b", "c", "neu")

    namen, _verworfen = apps.pinned(
        dokument(pins=["c", "b", "a"], baseline=["a", "b", "c"]),
        tmp_path / "system")

    assert namen == ["c", "b", "a", "neu"], (
        "das Neue steht mitten in der Reihenfolge des Nutzers - dann "
        "wandern beim naechsten Anmelden seine Symbole")


# --------------------------------------------------------------------
# Wanderung: eine Datei von vorher
# --------------------------------------------------------------------

def test_ohne_hinterlegte_vorgabe_laeuft_alles_weiter_wie_bisher(maschine,
                                                                 tmp_path):
    """Eine Installation von vor dem 20.08.2026 hat den Schluessel nicht.

    Dann ist unbekannt, wogegen der Nutzer entschieden hat, und aus
    einem fehlenden Namen laesst sich nicht ablesen, ob er abgewaehlt
    oder erst spaeter dazugekommen ist. Angehaengt wird deshalb NICHTS -
    lieber ein Symbol zu wenig, das ein Klick zurueckholt, als eines
    zurueck, das jemand ausdruecklich weggenommen hat.

    Und vor allem: es LAEUFT. Ein fehlender Schluessel ist kein Fehler.
    """
    apps, settings, _entries = maschine
    liefere(tmp_path, "firefox", "kitty", "papers")
    installiere(tmp_path, "firefox", "kitty", "papers")

    alt = {"schema_version": 1,
           "bar": {"modules_left": None, "modules_right": None,
                   "dock_pins": ["kitty", "firefox"]}}

    assert settings.bar_baseline(alt) is None
    assert settings.check_bar(alt) == []

    namen, verworfen = apps.pinned(alt, tmp_path / "system")
    assert namen == ["kitty", "firefox"]
    assert verworfen == []


def test_eine_kaputte_vorgabe_wird_gemeldet_und_nicht_uebergangen(maschine):
    """Was in der Datei steht, muss dieselbe Form haben wie die Wahl.

    Sonst haelt der Erzeuger beim naechsten Lauf eine Zahl gegen eine
    Namensliste. Gemeldet wird es durch dieselbe Pruefung wie die drei
    Haelften - `settings.py check` sagt es, statt still weiterzumachen.
    """
    _apps, settings, _entries = maschine
    kaputt = {"schema_version": 1, "bar": {"dock_baseline": 5}}

    with pytest.raises(settings.UnusableSettings):
        settings.bar_baseline(kaputt)
    assert settings.check_bar(kaputt), (
        "check_bar() uebergeht die hinterlegte Vorgabe - dann meldet "
        "`settings.py check` \"nichts zu beanstanden\" ueber eine Datei, "
        "an der der Erzeuger gleich scheitert")


# --------------------------------------------------------------------
# Ein angeheftetes Programm verschwindet
# --------------------------------------------------------------------

def test_ein_deinstalliertes_programm_verliert_seinen_knopf_und_nicht_seinen_platz(
        maschine, tmp_path):
    """Was passiert, wenn jemand ein angeheftetes Programm entfernt.

    ZWEI ANTWORTEN, UND BEIDE SIND NOETIG
        Im DOCK verschwindet es. Ein Symbol, das ins Leere zeigt, ist
        schlechter als keines: es meldet sich nie von selbst, und der
        Nutzer haelt den Klick fuer kaputt statt das Programm fuer
        deinstalliert. Genannt wird es trotzdem - auf der
        Fehlerausgabe, ueber settings.bar_complaint().

        In der DATEI bleibt es stehen. apps.pinned() liest die
        Einstellungen und schreibt sie nicht; wer das Programm wieder
        installiert, findet sein Symbol an genau der Stelle wieder, an
        die er es gezogen hatte. Eine Nutzerliste, die sich beim Lesen
        selbst aufraeumt, verliert eine Entscheidung an eine
        Paketaktion.
    """
    apps, settings, _entries = maschine
    liefere(tmp_path, "firefox")
    installiere(tmp_path, "firefox", "inkscape")

    doc = dokument(pins=["firefox", "inkscape"], baseline=["firefox"])
    namen, _verworfen = apps.pinned(doc, tmp_path / "system")
    assert namen == ["firefox", "inkscape"]

    # Und jetzt wird es deinstalliert - der Eintrag verschwindet.
    (tmp_path / "data" / "applications" / "inkscape.desktop").unlink()

    namen, verworfen = apps.pinned(doc, tmp_path / "system")
    assert namen == ["firefox"], "das tote Symbol steht noch im Dock"
    assert verworfen == [("inkscape", settings.BAR_GONE)]
    assert "inkscape" in settings.bar_complaint(settings.BAR_PINS, verworfen)

    # Die Einstellungen sind unberuehrt: der Platz bleibt reserviert.
    assert doc["bar"]["dock_pins"] == ["firefox", "inkscape"], (
        "apps.pinned() hat die Einstellungen des Nutzers veraendert - "
        "eine Paketaktion darf keine Entscheidung loeschen")

    # Wieder installiert, wieder da, an derselben Stelle.
    installiere(tmp_path, "inkscape")
    namen, verworfen = apps.pinned(doc, tmp_path / "system")
    assert namen == ["firefox", "inkscape"]
    assert verworfen == []


# --------------------------------------------------------------------
# Der Weg, den der Erzeuger wirklich geht
# --------------------------------------------------------------------

MARKER_LINE = 'const PINNED: string[] = []  // zepos-pinned\n'


@pytest.mark.allow_subprocess
def test_der_erzeuger_setzt_die_gewanderte_liste_in_die_erzeugte_datei(
        tmp_path):
    """`apps.py filter`, so wie src/generate_config.sh es aufruft.

    Ueber einen Unterprozess und nicht ueber einen Import, aus demselben
    Grund wie in tests/src/test_apps_pinned_call.py: am 13.08.2026 hat
    eine geaenderte Signatur eine installierte Maschine in eine
    Anmeldeschleife geschickt, und die Suite war dabei gruen - kein Test
    ging den einzigen echten Weg.

    Gemessen wird hier die ganze Kette an einem Stueck: abgewaehlt
    bleibt weg, neu geliefert kommt dazu, selbst angeheftet bleibt
    stehen, und das Ergebnis steht in der erzeugten Zeile.
    """
    import subprocess

    system = tmp_path / "system"
    system.mkdir(parents=True)
    (system / "shipped-applications").write_text(
        "firefox\nkitty\npapers\n", encoding="utf-8")
    (system / "own-applications").write_text("", encoding="utf-8")

    share = tmp_path / "data" / "applications"
    share.mkdir(parents=True)
    for name in ("firefox", "kitty", "papers", "inkscape"):
        (share / f"{name}.desktop").write_text(
            ENTRY.format(name=name, label=name, nodisplay="false"),
            encoding="utf-8")

    nutzer = tmp_path / "zepos"
    nutzer.mkdir(parents=True)
    (nutzer / "user-settings.json").write_text(json.dumps(
        dokument(pins=["inkscape", "firefox"],
                 baseline=["firefox", "kitty"])), encoding="utf-8")

    ziel = tmp_path / "Dock.tsx"
    ziel.write_text("// Kopf\n" + MARKER_LINE + "// Fuss\n", encoding="utf-8")

    fertig = subprocess.run(
        [sys.executable, str(SRC / "apps.py"), "filter", str(ziel)],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin",
             "ZEPOS_SYSTEM_ROOT": str(system),
             "ZEPOS_USER_ROOT": str(nutzer),
             "XDG_DATA_HOME": str(tmp_path / "data"),
             "XDG_DATA_DIRS": str(tmp_path / "leer")})

    assert fertig.returncode == 0, f"{fertig.stdout}\n{fertig.stderr}"
    assert "Traceback" not in fertig.stderr, fertig.stderr

    gesetzt = json.loads(ziel.read_text(encoding="utf-8")
                         .splitlines()[1].split("=", 1)[1]
                         .rsplit("//", 1)[0].strip())
    assert gesetzt == ["inkscape", "firefox", "papers"], (
        "die erzeugte Zeile traegt nicht, was die Einstellungen sagen: "
        "kitty war abgewaehlt, papers ist neu ausgeliefert, inkscape hat "
        "der Nutzer selbst angeheftet")
