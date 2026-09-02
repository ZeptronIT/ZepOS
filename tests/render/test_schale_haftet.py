# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Seitenleiste bleibt stehen, wenn die Seite blaettert.

WARUM ES DIESE DATEI GIBT
    GEMELDET am 02.09.2026: "uebrigens frage ich mich warum die
    seitenleiste in unseren ags fenster die sidebar nicht sticky ist bei
    scroll scrollen wir alles runter".

    Die Ursache lag in createShellWindow() (ags-overlay-utils.template):
    die Fabrik legt EINE Gtk.ScrolledWindow um alles, was buildContent()
    zurueckgibt, und der Rumpf der Schale IST Seitenleiste plus Seite.
    Die Seitenleiste lag damit im Sichtfenster der Fabrik und fuhr beim
    Blaettern mit hinaus. Die Reparatur steht dort; hier steht, wie sie
    nachgemessen wird.

WAS GEMESSEN WIRD, UND ZWEIMAL - EINMAL IM PROZESS, EINMAL AM BILD
    Der Prozess (tests/render/schale_haftet_child.ts) sagt, WIEVIELE
    Bildlaufflaechen es im Fenster gibt, welche davon ueberhaupt etwas
    zu blaettern hat und wo die Seitenleiste vor und nach dem Blaettern
    liegt. Das Bild sagt, was davon auch GEMALT wurde: welche
    Bildpunkte sich zwischen den beiden Abzuegen geaendert haben, in der
    Spalte der Seitenleiste und in der Spalte der Seite - getrennt.

    Beides zusammen, weil keines allein reicht. Ein Widget, das seine
    Zuteilung behauptet, muss dort noch nicht malen; und ein Bild ohne
    die Zahlen aus dem Prozess kann nicht sagen, ob ueberhaupt etwas zu
    blaettern war.

DIE ZWEI HAELFTEN DER ZUSICHERUNG SIND BEIDE NOETIG
    (i) die Seite hat sich bewegt - sonst waere "die Seitenleiste hat
        sich nicht bewegt" fuer JEDEN Aufbau wahr, auch fuer den
        kaputten. An diesem Tag sind acht Pruefstellen aufgeflogen, die
        gruen waren und nichts gemessen haben; diese hier faellt, wenn
        nichts geblaettert wurde.
    (ii) die Seitenleiste hat sich NICHT bewegt.

DIE GEGENPROBE IST GEFAHREN, UND SIE IST DER EIGENTLICHE BEWEIS
    Dieselbe Sonde, gegen den Baum VOR der Reparatur - zwei Zeilen im
    ERZEUGTEN ags/utils/overlay.ts unter /tmp zurueckgedreht
    (`rumpf.append(seitenBildlauf)` -> `rumpf.append(seitenStapel)`),
    sonst nichts. Die Vorlage selbst ist dafuer nicht angefasst worden.
    GEMESSEN am 02.09.2026, 1920x1080, beide Laeufe:

                              vorher (kaputt)      nachher (reparatur)
        Bildlaufflaechen      1                    2
        blaetterbar           f0 = 2996/731        f1 = 2996/731
        haelt die Sidebar     f0 -> ja             f0 -> ja, f1 -> nein
        Lage der Sidebar      1,78,209,2996        1,78,209,731
          nach dem Blaettern  1,-2187,209,2996     1,78,209,731
        Bildpunkte gewechselt
          Spalte Sidebar      11 423               0
          Spalte Seite        47 390               45 435

    Die Seitenleiste fuhr also um 2265 Punkte mit - genau den Weg der
    vadjustment - und war ausserdem 2996 statt 731 Punkte hoch
    zugeteilt, weil sie im Blaetterinhalt hing statt neben ihm.

    GENAU ZWEI der sieben Zusicherungen unten fallen an diesem Baum, und
    das ist nachgerechnet und nicht geschaetzt: die Artefakte der
    Gegenprobe (Protokoll und die beiden Bilder) sind durch DIESE
    Zusicherungen selbst geschickt worden, nicht durch einen Nachbau.

        ROT    test_keine_blaetternde_flaeche_haelt_die_seitenleiste
        ROT    test_die_seitenleiste_bleibt_beim_blaettern_stehen
        gruen  die uebrigen fuenf

    Dass fuenf gruen bleiben, ist kein Mangel, sondern ihre Aufgabe: sie
    bewachen die Voraussetzungen der Messung (Fenster da, Stylesheet
    geladen, Flaeche steht still, es wurde ueberhaupt geblaettert) und
    die Frage, die der Umbau offengelassen hat (zwei Leisten). Bei jeder
    steht unten, in welchem Zustand sie faellt.

DER PREIS
    Ein verschachtelter Compositor je Lauf, rund 25 Sekunden - dieselbe
    Rechnung wie in test_schale_stil.py daneben, und aus demselben
    Grund.
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

KIND = Path(__file__).resolve().parent / "schale_haftet_child.ts"

# Wie das Kind seine Flaeche nennt - wortgleich zu NAMENSRAUM dort. Zwei
# Schreibweisen waeren zwei Flaechen.
NAMENSRAUM = "haft-sonde"

# Der Fahrplan des Kindes (T_VOR 7 s, T_BLAETTERN 10 s, T_NACH 13 s,
# T_ENDE 17 s). Geknipst wird NACH der jeweiligen Meldung, damit Bild und
# Bericht denselben Zustand zeigen - dieselbe Lehre wie bei `platte` in
# test_schale_stil.py, wo Bild und Geometrie eine Runde
# auseinandergelaufen sind.
T_BILD_VORHER = 8.5
T_BILD_NACHHER = 14.5
T_LAUFZEIT = 18.0

# Die Breite der Seitenleiste, wie sie in ags-style.template steht -
# dieselbe Zahl und derselbe Grund wie SIDEBAR_BREITE_SOLL in
# test_schale_stil.py (Spezifikation Abschnitt 2.2). Plus ein Punkt fuer
# `border-right: 1px`, den die Zuteilung des Widgets mittraegt.
SIDEBAR_BREITE_SOLL = 208
SIDEBAR_ZUTEILUNG_SOLL = SIDEBAR_BREITE_SOLL + 1

# Wieviel Unruhe zwischen zwei Abzuegen desselben stehenden Fensters
# durchgeht. GEMESSEN am 02.09.2026, beide Abzuege im reparierten Baum,
# 1920x1080: in der Spalte der Seitenleiste aendert sich KEIN einziger
# Bildpunkt (0 von 149 552). Die GEGENPROBE am unreparierten Baum
# (derselbe Schirm, dieselbe Sonde) meldete dort 11 423 - die
# Seitenleiste fuhr um 2265 Punkte mit, genau den Weg, den die
# vadjustment zurueckgelegt hat.
#
# Der Zuschlag ist trotzdem nicht null, aus demselben Vorsichtsgrund wie
# die 1-Punkt-Toleranz in test_schale_stil.py: der Weichzeichner des
# Compositors rechnet in Gleitkomma, und eine einzelne Rundung ist kein
# Fehler. 200 gegen 0 auf der einen und 11 423 auf der anderen Seite
# liegt zwischen den beiden Zustaenden und nicht dicht an einem von
# ihnen.
RUHE_ZUSCHLAG = 200

# Wieviel sich in der Spalte der SEITE mindestens geaendert haben muss,
# damit "es wurde geblaettert" belegt ist. GEMESSEN (derselbe Lauf):
# 45 435 von 479 573. Dass es nicht mehr sind, liegt am Grund: zwischen
# den Zeilen ist die Seite Glas, und Glas sieht nach dem Blaettern
# genauso aus wie davor - gewechselt haben die Zeilen selbst. Die
# Schwelle liegt bei rund einem Siebtel des gemessenen Werts: hoch
# genug, dass ein blosses Aufblinken des Schiebers sie nicht erreicht,
# tief genug, dass sie nicht die Messung abschreibt.
SEITE_BEWEGUNG_MINDEST = 6000


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


def _blaetterbar(felder: dict[str, str]) -> dict[str, tuple[int, int, int]]:
    """Die Bildlaufflaechen, die etwas zu blaettern haben.

    Das Kind meldet je Flaeche `fN=<upper>/<page_size>@<value>`. Eine
    Flaeche mit upper <= page_size hat nichts zu blaettern und blendet
    ihre Leiste unter Gtk.PolicyType.AUTOMATIC gar nicht ein - genau der
    Vergleich, den GTK dafuer selbst anstellt (siehe der Kommentar bei
    notify::upper in ags-overlay-utils.template).
    """
    gefunden: dict[str, tuple[int, int, int]] = {}
    for name, wert in felder.items():
        if not name.startswith("f") or "/" not in wert:
            continue
        rest, _, value = wert.partition("@")
        upper, _, page = rest.partition("/")
        zahlen = (int(float(upper)), int(float(page)), int(float(value or 0)))
        if zahlen[0] > zahlen[1] + 1:
            gefunden[name] = zahlen
    return gefunden


@pytest.fixture(scope="module")
def haftung(tmp_path_factory) -> dict:
    """Eine Schale mit einer zu langen Seite, zwei Abzuege, ein Bericht."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zephaft-bau")
    bilder = tmp_path_factory.mktemp("zephaft-bild")
    ags = render_configuration(bau)

    # Das Kind IN den erzeugten Baum, damit `./utils/overlay` genau die
    # Datei trifft, die auch das Kontrollzentrum benutzt - ein Nachbau
    # der Fabrik im Testverzeichnis wuerde den Nachbau messen. Derselbe
    # Kunstgriff wie in test_dateiwaehler_echt.py.
    ziel = ags / "haft-sonde.ts"
    shutil.copyfile(KIND, ziel)
    buendel = bau / "haft-sonde.js"
    ergebnis = subprocess.run(
        ["ags", "bundle", str(ziel), str(buendel), "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=600)
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat das Kind nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)

    protokoll = bau / "haft-sonde.log"
    with Session(1920, 1080) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # Derselbe Grund wie in test_schale_stil.py: kein Hardware-Cursor
        # auf dem headless-Ausgang, der Compositor malt den Pfeil sonst
        # MIT in jedes Bild - und in ZWEI Bilder an verschiedenen
        # Stellen, was jeden Bildvergleich verdirbt.
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(960, 540)
        time.sleep(2.0)

        start = time.monotonic()
        kind = sitzung.spawn([str(buendel)], log=protokoll,
                             HYPRLAND_INSTANCE_SIGNATURE=sitzung.signature())

        platte = None
        frist = start + T_BILD_VORHER
        while time.monotonic() < frist:
            platte = sitzung.layers().get(NAMENSRAUM) or platte
            time.sleep(0.3)
        platte = sitzung.layers().get(NAMENSRAUM) or platte
        vorher = measure.read_png(sitzung.shoot(bilder / "vorher.png"))

        time.sleep(max(0.0, start + T_BILD_NACHHER - time.monotonic()))
        platte_nachher = sitzung.layers().get(NAMENSRAUM) or platte
        nachher = measure.read_png(sitzung.shoot(bilder / "nachher.png"))

        time.sleep(max(0.0, start + T_LAUFZEIT - time.monotonic()))
        lebt = kind.poll() is None
        text = (protokoll.read_text(encoding="utf-8", errors="replace")
                if protokoll.exists() else sitzung.read_shell_log())

    return {"platte": platte, "platte_nachher": platte_nachher,
            "vorher": vorher, "nachher": nachher,
            "protokoll": text, "lebt": lebt, "bilder": bilder}


def test_die_sonde_hat_ueberhaupt_eine_flaeche_gezeigt(haftung):
    """Die billigste Zusicherung, und darum zuerst: ohne Fenster ist
    jede Zahl darunter eine Zahl ueber die Tapete."""
    assert haftung["platte"], (
        f"keine Flaeche {NAMENSRAUM!r} auf dem Schirm - Protokoll:\n"
        + haftung["protokoll"])
    assert haftung["lebt"], (
        "das Kind ist vor dem Ende des Fahrplans gestorben:\n"
        + haftung["protokoll"])


def test_das_stylesheet_ist_geladen(haftung):
    """DIE GEGENPROBE ZUR GEGENPROBE, und sie steht hier, weil genau
    dieser Fehler an diesem Tag schon einmal einen Befund erfunden hat.

    tests/render/test_zeprow_verschachtelung.py hat am 01.09.2026 einen
    Bildvergleich gefahren, der nie ein Stylesheet geladen hatte, und
    GTKs Vorgabefarbe (128,165,211) fuer die des Projekts (#33C9EE)
    gehalten. Das Kind hier laedt style.scss ueber `app.start({ css })`,
    also dieselbe Zeile wie ags-config.template - aber das behauptet es
    nur.

    Nachgewiesen wird es an der BREITE der Seitenleiste: `.zep-sidebar`
    traegt min-width 208px - (2 * SPACE_8) plus padding SPACE_8 plus
    border-right 1px, macht 209 Punkte Zuteilung. Ohne geladenes
    Stylesheet waere die Spalte so breit wie ihr laengster Text, also
    irgendetwas - nur nicht 209.
    """
    felder = _sonde(haftung["protokoll"], "vorher")
    assert felder, ("das Kind hat keine Marke 'vorher' gemeldet:\n"
                    + haftung["protokoll"])
    lage = felder.get("sidebar", "?")
    assert lage != "?", (
        "das Kind hat kein Widget mit der Klasse 'zep-sidebar' gefunden "
        f"- dann baut createShellWindow() keine Seitenleiste mehr:\n{felder}")
    breite = int(lage.split(",")[2])
    assert abs(breite - SIDEBAR_ZUTEILUNG_SOLL) <= 1, (
        f"die Seitenleiste ist {breite}px breit zugeteilt, erwartet werden "
        f"{SIDEBAR_ZUTEILUNG_SOLL}px ({SIDEBAR_BREITE_SOLL}px Spalte plus "
        "1px border-right). Weicht sie ab, ist entweder das Stylesheet "
        "nicht geladen - dann messen die Zusicherungen darunter GTKs "
        f"Vorgabe und nicht dieses Projekt - oder .zep-sidebar hat sich "
        f"geaendert:\n{felder}")


def test_keine_blaetternde_flaeche_haelt_die_seitenleiste(haftung):
    """DIE STRUKTURELLE HAELFTE, und sie ist die scharfe: eine
    Bildlaufflaeche, in der die Seitenleiste HAENGT, nimmt sie beim
    Blaettern zwangslaeufig mit - unabhaengig davon, ob in DIESEM Lauf
    zufaellig geblaettert wurde.

    Genau das war der Fehler: die Fabrik legt EINE Gtk.ScrolledWindow um
    alles, was buildContent() zurueckgibt, und der Rumpf der Schale ist
    Seitenleiste plus Seite.

    GEMESSEN am 02.09.2026, dieselbe Sonde, beide Baeume (die Zahlen
    stammen aus den zwei Laeufen im Bericht dieser Aufgabe):

        vor der Reparatur   flaechen=1  f0=2996/731  haelt-sidebar=1
        nach der Reparatur  flaechen=2  f0=731/731   haelt-sidebar=10
                                        f1=2996/731

        Die Flaeche, die etwas zu blaettern hat, ist nach der Reparatur
        die ZWEITE - und die haelt die Seitenleiste nicht. Die erste
        (die der Fabrik) haelt sie weiterhin, hat aber nichts zu
        blaettern: 731 Inhalt in einem 731 hohen Sichtfenster.

    Diese Zusicherung faellt also am unreparierten Baum, und sie faellt
    aus dem richtigen Grund - nicht daran, dass zufaellig nichts
    geblaettert wurde.
    """
    felder = _sonde(haftung["protokoll"], "vorher")
    assert felder, ("das Kind hat keine Marke 'vorher' gemeldet:\n"
                    + haftung["protokoll"])
    haelt = felder.get("haelt-sidebar", "")
    assert len(haelt) == int(felder.get("flaechen", "0")), (
        "das Kind hat fuer nicht jede Bildlaufflaeche gemeldet, ob sie die "
        f"Seitenleiste haelt: flaechen={felder.get('flaechen')}, "
        f"haelt-sidebar={haelt!r}")

    blaetterbar = _blaetterbar(felder)
    schuldige = {name: werte for name, werte in blaetterbar.items()
                 if haelt[int(name[1:])] == "1"}
    assert not schuldige, (
        "eine Bildlaufflaeche, die etwas zu blaettern hat, HAELT die "
        f"Seitenleiste - sie faehrt damit mit: {schuldige} "
        "(upper, page_size, value). "
        + " ".join(f"{k}={v}" for k, v in sorted(felder.items())
                   if k.startswith("f"))
        + f"\nhaelt-sidebar={haelt}")


def test_keine_zwei_bildlaufleisten_uebereinander(haftung):
    """Die offene Frage am Umbau: legt die Schale ihre EIGENE
    Bildlaufflaeche um den Seitenstapel, liegt darueber weiterhin die
    der Fabrik. Zwei Leisten nebeneinander waeren ein sichtbarer Mangel.

    Sie bleibt aus, weil eine Gtk.ScrolledWindow mit AUTOMATIC eine
    KLEINE Mindesthoehe weitermeldet: das Sichtfenster der Fabrik reicht
    damit fuer die Seitenleiste, also hat ihre Flaeche nichts zu
    blaettern und blendet nach GTKs eigenem Vergleich (upper >
    page_size) keine Leiste ein.

    DIESE ZUSICHERUNG IST VOR UND NACH DEM UMBAU GRUEN, UND DAS STEHT
    HIER, WEIL ES SONST WIE EIN NACHWEIS AUSSAEHE, DER KEINER IST
        GEMESSEN am 02.09.2026, `leiste-sichtbar` der Sonde (eine
        Ziffer je Flaeche, 1 = die senkrechte Leiste ist gemappt):

            vor der Reparatur   flaechen=1  leiste-sichtbar=1
            nach der Reparatur  flaechen=2  leiste-sichtbar=01

        Eine sichtbare Leiste in beiden Faellen. Der Umbau wird also
        NICHT von dieser Zusicherung bewacht, sondern von der
        strukturellen darueber - diese hier bewacht die Frage, die er
        offengelassen hat, und faellt erst, wenn eine spaetere Aenderung
        wirklich zwei Leisten aufstellt.

        Zwei Leisten sind uebrigens nicht unmoeglich, sondern nur weit
        weg: sie erscheinen, sobald das Fenster nicht einmal fuer die
        SEITENLEISTE hoch genug ist - dann greift die Flaeche der Fabrik
        als letzter Ausweg. GEMESSEN mit einem 620 Punkte hohen Schirm
        (Fenster 465, Sichtfenster 386): auch dort noch f0=386/386, die
        Seitenleiste dieser Sonde passt hinein. Der Ausweg ist also
        vorhanden und liegt ausserhalb dessen, was ein Schirm dieses
        Projekts hergibt.
    """
    felder = _sonde(haftung["protokoll"], "vorher")
    assert felder, ("das Kind hat keine Marke 'vorher' gemeldet:\n"
                    + haftung["protokoll"])
    sichtbar = felder.get("leiste-sichtbar", "")
    assert sichtbar.count("1") == 1, (
        f"{sichtbar.count('1')} senkrechte Bildlaufleisten sind gemappt, "
        f"erwartet wird genau eine (leiste-sichtbar={sichtbar!r}, eine "
        "Ziffer je Bildlaufflaeche in Baumfolge). "
        + " ".join(f"{k}={v}" for k, v in sorted(felder.items())
                   if k.startswith("f")))


def test_die_seite_hat_sich_wirklich_bewegt(haftung):
    """HAELFTE (i) DER ZUSICHERUNG, und ohne sie waere die andere wertlos.

    Wenn nichts blaettert, steht auch die Seitenleiste still - und die
    Zusicherung darunter waere gruen, ohne etwas gemessen zu haben.
    Deshalb muss ZUERST belegt sein, dass ueberhaupt geblaettert wurde:
    das Kind meldet, wieviele Flaechen es verstellt hat, und das BILD
    muss es in der Spalte der Seite zeigen.
    """
    gerollt = _sonde(haftung["protokoll"], "geblaettert")
    assert gerollt and int(gerollt.get("anzahl", "0")) >= 1, (
        "das Kind hat keine einzige Bildlaufflaeche verstellt - dann sagt "
        "dieser Lauf ueber Haftung nichts:\n" + haftung["protokoll"])

    px, py, pb, ph = haftung["platte"]
    bewegt = measure.changed_pixels(
        haftung["vorher"], haftung["nachher"],
        (px + SIDEBAR_ZUTEILUNG_SOLL + 2, py + 85,
         pb - SIDEBAR_ZUTEILUNG_SOLL - 4, ph - 91))
    assert len(bewegt) >= SEITE_BEWEGUNG_MINDEST, (
        f"in der Spalte der SEITE haben sich nur {len(bewegt)} Bildpunkte "
        f"geaendert (erwartet mindestens {SEITE_BEWEGUNG_MINDEST}). Die "
        "Seite hat also nicht geblaettert, und damit misst die Zusicherung "
        "ueber die Seitenleiste nichts. Rechteck der Aenderung: "
        f"{measure.bounds_of(bewegt)}\n" + haftung["protokoll"])


def test_die_seitenleiste_bleibt_beim_blaettern_stehen(haftung):
    """HAELFTE (ii): "warum ist die sidebar nicht sticky bei scroll".

    Gemessen am BILD, in der Spalte der Seitenleiste allein - und
    zusaetzlich an der Zuteilung, die das Kind vor und nach dem
    Blaettern gemeldet hat. Die beiden Wege koennen sich nicht
    gegenseitig stuetzen: das eine ist gemalt, das andere gerechnet.

    GEGENPROBE, GEFAHREN am 02.09.2026 gegen den Baum VOR der Reparatur
    (die eigene Bildlaufflaeche der Schale herausgenommen, sonst nichts
    geaendert): dort meldete die Bild-Haelfte 11 423 geaenderte
    Bildpunkte in der Spalte der Seitenleiste statt 0 - daran fiel die
    Zusicherung. Die Zuteilungs-Haelfte darunter kam deshalb nicht mehr
    zum Zug, waere aber ebenso gefallen: `1,78,209,2996` gegen
    `1,-2187,209,2996`. Die ganze Tabelle steht im Blattkopf.
    """
    px, py, pb, ph = haftung["platte"]
    bewegt = measure.changed_pixels(
        haftung["vorher"], haftung["nachher"],
        (px + 1, py + 85, SIDEBAR_BREITE_SOLL, ph - 91))
    assert len(bewegt) <= RUHE_ZUSCHLAG, (
        f"in der Spalte der SEITENLEISTE haben sich {len(bewegt)} "
        f"Bildpunkte geaendert (erlaubt sind {RUHE_ZUSCHLAG} als "
        "Rundungsunruhe). Die Seitenleiste faehrt beim Blaettern mit - "
        "genau die Meldung, um derentwillen diese Datei entstanden ist. "
        f"Rechteck der Aenderung: {measure.bounds_of(bewegt)}\n"
        + haftung["protokoll"])

    vorher = _sonde(haftung["protokoll"], "vorher")
    nachher = _sonde(haftung["protokoll"], "nachher")
    assert vorher and nachher, (
        "das Kind hat nicht beide Marken gemeldet:\n" + haftung["protokoll"])
    assert vorher["sidebar"] == nachher["sidebar"], (
        f"die Zuteilung der Seitenleiste hat sich beim Blaettern geaendert: "
        f"vorher {vorher['sidebar']}, nachher {nachher['sidebar']} "
        "(x,y,Breite,Hoehe, bezogen auf das Fenster)")


def test_die_flaeche_der_schale_bleibt_stehen(haftung):
    """Das Fenster selbst wandert nicht, wenn drinnen geblaettert wird.

    Eine Flaeche, die beim Blaettern ihre Lage oder Groesse aendert,
    wuerde JEDEN Bildvergleich dieser Datei verderben - beide Spalten
    waeren dann voller Aenderungen, und die Zusicherung ueber die
    Seitenleiste faellt aus einem Grund, der nichts mit Haftung zu tun
    hat. Sie steht darum hier und nicht als Anmerkung.
    """
    assert haftung["platte"] == haftung["platte_nachher"], (
        f"die Flaeche {NAMENSRAUM!r} lag beim ersten Abzug bei "
        f"{haftung['platte']} und beim zweiten bei "
        f"{haftung['platte_nachher']}")
