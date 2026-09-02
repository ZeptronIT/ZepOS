# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Fenster OHNE Seitenleiste blaettern weiter ganz.

WARUM ES DIESE DATEI GIBT
    Aufgabe 83 hat der Schale ihre EIGENE Bildlaufflaeche gegeben, damit
    die Seitenleiste beim Blaettern stehenbleibt (siehe
    test_schale_haftet.py daneben). Der Umbau steht in
    createShellWindow(), aber er steht in DERSELBEN Datei wie
    createOverlayWindow() - der Fabrik fuer ALLE zwoelf
    Aufklappfenster -, und der Waechter fuer waagerechten Ueberhang ist
    dabei aus der Fabrik herausgeloest worden.

    ZEHN dieser Fenster haben keine Seitenleiste (Kalender, Meldungen,
    Bluetooth-Agent, Datentraeger, Akku, Abmelden, VPN-Einstellungen,
    Hintergrundbild, Tastenkuerzel, Stil-Editor). Sie sollen unveraendert
    GANZ blaettern. "Ich habe die Fabrik nicht wirklich angefasst" ist
    dafuer kein Nachweis, sondern eine Behauptung ueber einen
    Unterschied - und an genau diesem Tag sind acht Pruefstellen
    aufgeflogen, die gruen waren und nichts gemessen haben. Also gemessen.

DER BEZUGSLAUF IST GEFAHREN, UND ER IST HIER DER EIGENTLICHE BEWEIS
    Die Gegenprobe dieser Datei ist keine kaputtgemachte Kopie, sondern
    der VORZUSTAND: dieselbe Sonde, aber `utils/overlay.ts` aus der
    Vorlage von `main` erzeugt (also ohne die Aenderung dieser Aufgabe),
    sonst nichts geaendert. GEMESSEN am 02.09.2026, 1920x1080, beide
    Laeufe - Zahl fuer Zahl gleich:

                                main (vorher)        dieser Zweig
        Shortcuts, Flaechen     2                    2
          Huellen ueber Inhalt  1                    1
          f0 (Fabrik)           700/601@0 -> @99     700/601@0 -> @99
          f1 (eigene)           580/580@0            580/580@0
          Inhalt, Lage          1,78,854,700         1,78,854,700
            nach dem Blaettern  1,-21,854,700        1,-21,854,700
          Bildpunkte gewechselt 13 821               13 821
        Calendar, Flaechen      1                    1
          f0 (Fabrik)           540/540@0            540/540@0
          Bildpunkte gewechselt 0                    0

    Der Inhalt wandert also um GENAU die 99 Punkte der vadjustment
    (78 -> -21), und zwar in beiden Baeumen gleich.

    ZUSAETZLICH ZWEI SCHARFE GEGENPROBEN, damit nicht nur Gleichheit
    belegt ist, sondern auch, dass diese Zusicherungen ueberhaupt
    umschlagen koennen - je eine fuer die strukturelle und fuer die
    blaetternde Haelfte, beide nur im ERZEUGTEN Baum:

        `nie`      die Flaeche der Fabrik auf Gtk.PolicyType.NEVER -
                   sie blaettert senkrecht nicht mehr.
        `doppelt`  eine ZWEITE Bildlaufflaeche um den Inhalt der
                   Fabrik - der Aufbau der Schale, in ein Fenster ohne
                   Seitenleiste geraten.

    Welche Zusicherung an welcher faellt, steht bei jeder einzeln. Die
    zweite hat dabei einen Fehlgriff in dieser Datei selbst aufgedeckt;
    er steht bei test_genau_eine_huelle_liegt_ueber_dem_inhalt.

WARUM Shortcuts UND Calendar
    Beide bauen sich ohne Systemdienst und laufen im verschachtelten
    Compositor durch. Shortcuts laeuft ueber (700 in 601) und ist damit
    der Fall, an dem BLAETTERN messbar ist; Calendar passt hinein
    (540/540) und ist der kurze. Die Zusicherung ueber den AUFBAU gilt
    fuer beide, die ueber das Blaettern nur fuer den, der ueberlaeuft.

WARUM AUF PROTOKOLLZEILEN GEWARTET WIRD UND NICHT AUF DIE UHR
    GEMESSEN am 02.09.2026: in einem von drei Laeufen stand die
    Layer-Shell-Flaeche nach 7 Sekunden noch nicht, und ein Lauf nach
    festem Fahrplan meldete dann die erste Zuteilung (439x287) statt des
    Fensters. Dieselbe Flatterhaftigkeit steht im Blattkopf von
    test_schale_stil.py. Das Kind wartet darum auf einen ZUSTAND und
    meldet erst dann; dieser Test wartet auf die MELDUNG und knipst
    danach.

DER PREIS
    Ein verschachtelter Compositor, rund 35 Sekunden - dieselbe Rechnung
    wie in den beiden Nachbardateien und aus demselben Grund.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import measure                      # noqa: E402
from tests.render.desktop_session import (             # noqa: E402
    Session, render_configuration, required_tools, workspaces_file,
)

KIND = Path(__file__).resolve().parent / "ohne_sidebar_child.ts"

# Wie das Kind seine beiden Fenster nennt - `name` in ags-shortcuts.
# template bzw. ags-calendar.template, und damit der Name, unter dem
# `hyprctl layers` sie fuehrt.
FENSTER = {"a": "shortcuts", "b": "calendar"}

# Wie lange auf eine Meldung des Kindes gewartet wird. Grosszuegig, weil
# die Flaeche laut Blattkopf in einem Teil der Laeufe lange ausbleibt -
# das Kind wartet selbst bis zu 50 s darauf.
MELDE_FRIST = 75.0

# Wieviel sich im Rumpf von Shortcuts mindestens geaendert haben muss,
# damit "es wurde geblaettert" am BILD belegt ist. GEMESSEN (beide
# Laeufe): 13 821. Die Schwelle liegt bei rund einem Fuenftel davon -
# hoch genug, dass ein blosses Aufblinken der Leiste sie nicht erreicht,
# tief genug, dass sie nicht die Messung abschreibt.
BEWEGUNG_MINDEST = 2500

# Wieviel Unruhe im Rumpf von Calendar durchgeht, der NICHTS zu
# blaettern hat. GEMESSEN (beide Laeufe): 0 von 216 636. Nicht null
# gesetzt aus demselben Vorsichtsgrund wie RUHE_ZUSCHLAG in
# test_schale_haftet.py - der Weichzeichner rechnet in Gleitkomma.
RUHE_ZUSCHLAG = 200


def _sonde(protokoll: str, marke: str) -> dict[str, str] | None:
    """`SONDE:<marke>:a=1:b=2` als Abbildung - die LETZTE ihrer Art."""
    treffer = None
    for zeile in protokoll.splitlines():
        if not zeile.startswith(f"SONDE:{marke}:"):
            continue
        felder: dict[str, str] = {}
        for stueck in zeile.split(":")[2:]:
            name, trenner, wert = stueck.partition("=")
            if trenner:
                felder[name] = wert
        treffer = felder
    return treffer


def _flaeche(wert: str) -> tuple[int, int, int]:
    """`upper/page_size@value` als Zahlen."""
    rest, _, value = wert.partition("@")
    upper, _, page = rest.partition("/")
    return (int(float(upper)), int(float(page)), int(float(value or 0)))


@pytest.fixture(scope="module")
def fenster(tmp_path_factory) -> dict:
    """Zwei echte Fenster ohne Seitenleiste, je zwei Abzuege."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zepohne-bau")
    bilder = tmp_path_factory.mktemp("zepohne-bild")
    ags = render_configuration(bau)

    # Das Kind IN den erzeugten Baum, damit `./widget/Shortcuts` und
    # `./utils/overlay` genau die Dateien treffen, die auch die Schale
    # benutzt - ein Nachbau im Testverzeichnis wuerde den Nachbau
    # messen. Derselbe Kunstgriff wie in test_schale_haftet.py.
    ziel = ags / "ohne-sidebar.ts"
    shutil.copyfile(KIND, ziel)
    buendel = bau / "ohne-sidebar.js"
    ergebnis = subprocess.run(
        ["ags", "bundle", str(ziel), str(buendel), "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=600)
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat das Kind nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)

    protokoll = bau / "ohne-sidebar.log"
    bild: dict[str, object] = {}
    platte: dict[str, tuple[int, int, int, int] | None] = {}

    def lies() -> str:
        return (protokoll.read_text(encoding="utf-8", errors="replace")
                if protokoll.exists() else "")

    with Session(1920, 1080) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # Derselbe Grund wie in den Nachbardateien: kein Hardware-Cursor
        # auf dem headless-Ausgang, der Compositor malt den Pfeil sonst
        # MIT in jedes Bild - und in ZWEI Bilder an verschiedenen
        # Stellen, was jeden Bildvergleich verdirbt.
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(960, 540)
        time.sleep(2.0)

        kind = sitzung.spawn([str(buendel)], log=protokoll,
                             HYPRLAND_INSTANCE_SIGNATURE=sitzung.signature())

        # NACH der Meldung knipsen, nicht nach einer Zeitmarke - die
        # Herleitung steht im Blattkopf. Das Kind haelt nach jeder
        # Meldung 3 Sekunden still; ein Takt von 0,2 s trifft dieses
        # Fenster sicher.
        for marke in ("a-vorher", "a-nachher", "b-vorher", "b-nachher"):
            frist = time.monotonic() + MELDE_FRIST
            while time.monotonic() < frist:
                if _sonde(lies(), marke) is not None:
                    break
                time.sleep(0.2)
            namensraum = FENSTER[marke[0]]
            platte[marke] = sitzung.layers().get(namensraum)
            bild[marke] = measure.read_png(
                sitzung.shoot(bilder / f"{marke}.png"))

        frist = time.monotonic() + 20.0
        while time.monotonic() < frist:
            if _sonde(lies(), "ende") is not None:
                break
            time.sleep(0.3)
        lebt = kind.poll() is None
        text = lies() or sitzung.read_shell_log()

    return {"platte": platte, "bild": bild, "protokoll": text, "lebt": lebt,
            "bilder": bilder}


def test_beide_fenster_sind_erschienen(fenster):
    """Die billigste Zusicherung, und darum zuerst: ohne Fenster ist jede
    Zahl darunter eine Zahl ueber die Tapete.

    Sie faengt genau den Lauf, der diese Datei ihren Aufbau gekostet hat -
    die Flaeche, die nach 7 Sekunden noch nicht stand (siehe Blattkopf).
    """
    for marke, namensraum in (("a-vorher", "shortcuts"),
                              ("b-vorher", "calendar")):
        assert fenster["platte"][marke], (
            f"keine Flaeche {namensraum!r} auf dem Schirm zur Marke "
            f"{marke!r} - Protokoll:\n" + fenster["protokoll"])
        steht = _sonde(fenster["protokoll"], f"{marke[0]}-steht")
        assert steht and steht.get("ok") == "1", (
            f"das Kind hat fuer {namensraum!r} keine ruhige Zuteilung "
            "abgewartet:\n" + fenster["protokoll"])
    assert fenster["lebt"], (
        "das Kind ist vor dem Ende seines Fahrplans gestorben:\n"
        + fenster["protokoll"])


def test_genau_eine_huelle_liegt_ueber_dem_inhalt(fenster):
    """DIE STRUKTURELLE ZUSICHERUNG, und sie ist die eigentliche Frage
    dieser Datei: die Fabrik legt um den Inhalt GENAU EINE
    Bildlaufflaeche, so wie vor dem Umbau.

    GEZAEHLT WIRD DIE KETTE UEBER DEM INHALT UND NICHT DER BESTAND DES
    FENSTERS - und der Unterschied ist an dieser Zusicherung zweimal
    gemessen worden
        Shortcuts bringt eine EIGENE Gtk.ScrolledWindow mit
        (`#shortcuts-scroll`, ags-shortcuts.template). Die liegt INNEN,
        im Inhalt, und gehoert dem Widget, nicht der Fabrik. GEMESSEN,
        beide Baeume: `flaechen=2`, aber `huellen=1`. Eine Zusicherung
        auf `flaechen == 1` haette gemeldet, was dem Widget gehoert.

        DER ZWEITE ENTWURF DIESER ZUSICHERUNG WAR AN IHRER EIGENEN
        GEGENPROBE GRUEN, und das ist der Grund, warum die Messung heute
        eine Kette abgeht: er zaehlte, wieviele Flaechen VORFAHREN des
        Inhalts sind, und bestimmte den Inhalt als Kind des ersten
        Sichtfensters. Legt man eine ZWEITE Huelle um den Inhalt, ist
        dieses Kind die zweite Flaeche selbst - mit genau einem Vorfahr
        ihrer Art. GEMESSEN an der Gegenprobe: `flaechen=3` und
        trotzdem `1`. Die Zusicherung, die die Doppelhuelle finden
        sollte, hat sie nicht gesehen.

    Zwei Huellen ueber demselben Inhalt waeren der Aufbau der SCHALE, in
    ein Fenster geraten, das keine Seitenleiste hat - genau der Fehler,
    den eine Betriebsart an der Fabrik hier haette anrichten koennen.

    FAELLT AN DER GEGENPROBE `doppelt` (eine zweite Bildlaufflaeche um
    den Inhalt der Fabrik): GEMESSEN `huellen=2`, gemeldet fuer
    Shortcuts - die Schleife bleibt dort stehen und kommt zu Calendar
    nicht mehr. Sie faellt ebenso, wenn die einzige Huelle verschwindet.

    BLEIBT GRUEN AN DER GEGENPROBE `nie`, und zu Recht: eine Flaeche,
    die nicht mehr blaettert, ist immer noch genau eine Huelle. Was
    dort faellt, sind die zwei Zusicherungen ueber das Blaettern.
    """
    for marke, namensraum in (("a-vorher", "shortcuts"),
                              ("b-vorher", "calendar")):
        felder = _sonde(fenster["protokoll"], marke)
        assert felder, (f"keine Marke {marke!r} im Protokoll:\n"
                        + fenster["protokoll"])
        huellen = felder.get("huellen")
        assert huellen == "1", (
            f"{namensraum!r}: {huellen} Bildlauf-Huellen liegen ueber dem "
            "Inhalt, erwartet wird GENAU EINE - die der Fabrik. 0 heisst: "
            "die Fabrik packt den Inhalt nicht mehr ein; 2 oder mehr "
            "heissen, dass eine zweite Huelle dazugekommen ist.\n"
            f"{felder}")


def test_das_lange_fenster_blaettert_wirklich(fenster):
    """HAELFTE (i): ohne Ueberlauf sagt der Lauf ueber Blaettern nichts.

    GEMESSEN, beide Baeume: Shortcuts hat 700 Punkte Inhalt in einem 601
    Punkte hohen Sichtfenster, und das Kind hat GENAU EINE Flaeche
    verstellt.

    FAELLT AN DER GEGENPROBE `nie` (Flaeche der Fabrik auf
    Gtk.PolicyType.NEVER): dort hat sie senkrecht nichts mehr zu
    blaettern. Und ebenso an `doppelt`, wo die aeussere Flaeche 601/601
    meldet und nur die eingezogene zweite noch blaettert.
    """
    felder = _sonde(fenster["protokoll"], "a-vorher")
    assert felder, ("keine Marke 'a-vorher' im Protokoll:\n"
                    + fenster["protokoll"])
    upper, page, _wert = _flaeche(felder["f0"])
    assert upper > page + 1, (
        "die Flaeche der Fabrik hat in Shortcuts nichts zu blaettern "
        f"(upper={upper}, page_size={page}) - dann misst dieser Lauf ueber "
        f"das Blaettern nichts.\n{felder}")

    gerollt = _sonde(fenster["protokoll"], "a-geblaettert")
    assert gerollt and int(gerollt.get("anzahl", "0")) >= 1, (
        "das Kind hat in Shortcuts keine einzige Flaeche verstellt:\n"
        + fenster["protokoll"])


def test_der_inhalt_des_langen_fensters_ist_mitgewandert(fenster):
    """HAELFTE (ii): der Inhalt bewegt sich um GENAU den Weg der
    vadjustment - gerechnet, und danach am BILD nachgesehen.

    Die beiden Wege koennen sich nicht gegenseitig stuetzen: das eine ist
    zugeteilt, das andere gemalt. GEMESSEN, beide Baeume: Lage
    `1,78,854,700` vor und `1,-21,854,700` nach dem Blaettern, also 99
    Punkte - genau der Wert, den f0 danach traegt. Im Bild wechselten
    dabei 13 821 Bildpunkte.

    FAELLT AN DER GEGENPROBE `nie` (Flaeche der Fabrik auf
    Gtk.PolicyType.NEVER) und an `doppelt`: dort steht die Flaeche der
    Fabrik nach dem Blaettern noch auf 0.
    """
    vorher = _sonde(fenster["protokoll"], "a-vorher")
    nachher = _sonde(fenster["protokoll"], "a-nachher")
    assert vorher and nachher, (
        "das Kind hat nicht beide Marken fuer Shortcuts gemeldet:\n"
        + fenster["protokoll"])

    weg = int(_flaeche(nachher["f0"])[2])
    assert weg > 0, (
        f"die Flaeche der Fabrik steht nach dem Blaettern noch auf {weg}:\n"
        f"{nachher}")
    y_vorher = int(vorher["inhalt"].split(",")[1])
    y_nachher = int(nachher["inhalt"].split(",")[1])
    assert y_vorher - y_nachher == weg, (
        f"der Inhalt ist um {y_vorher - y_nachher} Punkte gewandert, die "
        f"Flaeche aber um {weg} (Lage vorher {vorher['inhalt']}, nachher "
        f"{nachher['inhalt']}). Ein Inhalt, der dem Bildlauf nicht folgt, "
        "blaettert nicht - er wird beschnitten.")

    px, py, pb, ph = fenster["platte"]["a-vorher"]
    bewegt = measure.changed_pixels(
        fenster["bild"]["a-vorher"], fenster["bild"]["a-nachher"],
        (px + 1, py + 85, pb - 2, ph - 91))
    assert len(bewegt) >= BEWEGUNG_MINDEST, (
        f"im Rumpf von Shortcuts haben sich nur {len(bewegt)} Bildpunkte "
        f"geaendert (erwartet mindestens {BEWEGUNG_MINDEST}). Die Zuteilung "
        "sagt, der Inhalt sei gewandert - gemalt wurde es nicht. Rechteck "
        f"der Aenderung: {measure.bounds_of(bewegt)}\n"
        + fenster["protokoll"])


def test_das_kurze_fenster_blaettert_gar_nicht(fenster):
    """Der kurze Fall, und er bewacht die andere Richtung: wo nichts
    ueberlaeuft, darf auch nichts blaettern und keine Leiste erscheinen.

    GEMESSEN, beide Baeume: Calendar hat 540 Punkte Inhalt in einem 540
    Punkte hohen Sichtfenster, keine gemappte senkrechte Leiste, und
    zwischen den beiden Abzuegen wechselt KEIN Bildpunkt (0 von 216 636).

    LAEUFT DIESES FENSTER EINES TAGES UEBER, faellt diese Zusicherung -
    und dann ist sie zu lesen und nicht zu loeschen: sie sagt aus, dass
    der Kalender auf 1920x1080 hineinpasst. Ein Kalender, der ueberlaeuft,
    ist entweder gewachsen (dann gehoert die Zusicherung umgeschrieben)
    oder das Fenster ist zu klein geworden (dann ist es ein Befund).
    """
    felder = _sonde(fenster["protokoll"], "b-vorher")
    assert felder, ("keine Marke 'b-vorher' im Protokoll:\n"
                    + fenster["protokoll"])
    upper, page, _wert = _flaeche(felder["f0"])
    assert upper <= page + 1, (
        f"Calendar laeuft ueber (upper={upper}, page_size={page}) - siehe "
        f"den Blattkopf dieser Zusicherung.\n{felder}")
    assert felder.get("leiste-sichtbar", "").count("1") == 0, (
        "in Calendar ist eine senkrechte Bildlaufleiste gemappt, obwohl "
        f"nichts zu blaettern ist:\n{felder}")

    px, py, pb, ph = fenster["platte"]["b-vorher"]
    ruhig = measure.changed_pixels(
        fenster["bild"]["b-vorher"], fenster["bild"]["b-nachher"],
        (px + 1, py + 85, pb - 2, ph - 91))
    assert len(ruhig) <= RUHE_ZUSCHLAG, (
        f"im Rumpf von Calendar haben sich {len(ruhig)} Bildpunkte geaendert "
        f"(erlaubt sind {RUHE_ZUSCHLAG} als Rundungsunruhe), obwohl es "
        f"nichts zu blaettern gibt. Rechteck: {measure.bounds_of(ruhig)}\n"
        + fenster["protokoll"])
