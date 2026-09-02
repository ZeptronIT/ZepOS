# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Fensterkopf nach SUPER+V, an einem echten Compositor gemessen.

WAS GEMELDET WURDE
    Der Nutzer am 01.09.2026, zweimal am selben Tag:

      "irgendwie haben seit der neusten version die kitty terminals oben
       der header wo x minimieren und vollbild ist keinen abstand zum
       oberen rand"

      "fenster die schweben mit super v sieht man auf dem header oben
       recht bei dem x ein flackern des headers voll komisch"

WARUM DIESE ZUSICHERUNG NICHT AN DER VORLAGE LAUFEN KANN
    Gefragt ist, wo eine DEKORATION liegt, die ein Plugin zeichnet -
    nicht was in einer Datei steht. hyprbars meldet seine Hoehe als
    `reserved` an Hyprlands Dekorationspositionierer, das Layout zieht
    sie ab, und die Lage eines schwebenden Fensters entsteht erst in
    fitBoxInWorkArea(). Keiner dieser drei Schritte steht in einer
    Vorlage. Die Vorlagenseite derselben Frage - welche Taste worauf
    zeigt und ob das Paket den Befehl ablegt - steht in
    tests/src/test_fensterkopf.py; dort steht auch die Arithmetik.

    Hier laeuft deshalb ein Hyprland im Hyprland, mit dieser Oberflaeche
    (damit die Leiste ihre Sperrzone wirklich anmeldet) und mit dem
    hyprbars, das ZepOS ausliefert.

WAS DABEI HERAUSKAM, GEMESSEN am 02.09.2026 (Hyprland 0.56.2,
1920x1080, ausgelieferte Groesse):

    Schirm            bei 4000,0, reserved [0, 84, 0, 84]
    Arbeitsflaeche    y 84..996, Hoehe 912
    bar_height 38, border_size 1, gaps_out 24

    gekachelt                    at (4025, 147)  1870x824
                                 Kopf oben 108 = 84 + 24
    nach `dispatch togglefloating`
                                 at (3999, -85)  1920x1080
                                 Kopf oben -124, also 208 Punkte ueber
                                 der Flaeche
    nach `zepos-float-toggle`    at (4001, 123)  1918x872
                                 Kopf oben 84, an der Kante

WARUM DIE ANIMATIONEN HIER AUS BLEIBEN, und das ist eine Lehre aus einer
falschen Messung
    Ein erster Aufbau am 02.09.2026 schaltete `animations:enabled 1` und
    setzte die Farbe der Kopfleiste danach mit `hyprctl keyword`. Im Bild
    war die Farbe daraufhin in keiner Zeile zu finden - und das sah aus
    wie ein Befund. Es war keiner: hyprbars fuehrt seine Balkenfarbe als
    ANIMIERTE Groesse (barDeco.cpp Zeile 51-54, Kurve "border"), und
    eine Farbe, die zur Laufzeit ein neues Ziel bekommt, faehrt darauf
    zu. Gemessen stand der Balken 2,5 s spaeter noch bei (17, 42, 48) -
    dem Grund dahinter -, waehrend seine KNOEPFE schon in ihren
    bestellten Farben dastanden (243,139,168 / 249,226,175 /
    166,227,161). Der Kopf war also da, nur nicht in der Farbe, nach der
    gesucht wurde.

    Deshalb hier: Farbe VOR dem Fenster gesetzt, Animationen aus - der
    Messstand von desktop_session.py tut beides von sich aus. Und
    deshalb prueft test_das_bild_zeigt_den_kopf_dort_wo_hyprctl_ihn_meldet
    unten, dass Bild und Abfrage UEBEREINSTIMMEN. Eine Farbsuche, die
    nichts findet, ist sonst von einem falsch eingestellten Messgeraet
    nicht zu unterscheiden.

WAS HIER NICHT GEMESSEN WERDEN KONNTE, und das gehoert dazu
    Ein FLACKERN im engeren Sinn. Zeiger auf dem X, Animationen an, vier
    Sekunden lang: 0 % Rechenzeit im verschachtelten Compositor und
    keine Abweichung zwischen zwoelf aufeinanderfolgenden Aufnahmen des
    Kopfstreifens. Ein Zeichenpfad, der sich selbst beschaedigt und
    dadurch endlos neu zeichnet, laesst sich so finden - hier war keiner.

    Der naechstliegende Verdacht war widerlegbar und ist widerlegt:
    hyprbars/barDeco.cpp Zeile 421-427 kippt im ZEICHENPFAD ein
    Hover-Bit und ruft `damageEntire()`, und dieser Teil haengt NICHT an
    `icon_on_hover`. Er beruhigt sich aber nach einem Bild, weil das Bit
    danach mit `hovering` uebereinstimmt - gemessen: keine zweite
    Beschaedigung.

WARUM ER TROTZDEM ZUR ERSTEN MELDUNG GEHOERT
    Weil es ein Ereignis ist. Wer SUPER+V drueckt, sieht den Kopf an den
    oberen Rand springen; wer die Taste zum Pruefen zweimal drueckt,
    sieht ihn erscheinen und verschwinden. Das X sitzt in der Ecke, in
    der beides zusammenfaellt: bei 1920 Breite auf x 3999 liegt der
    rechte Fensterrand einen Punkt vor dem Schirmrand.

WARUM DIESER TEST UEBERSPRUNGEN WIRD, WO DAS PLUGIN FEHLT
    Dieselbe Regel, die CONTRIBUTING.md schon fuer QEMU, OVMF, ein
    gebautes Paketverzeichnis und ein echtes Hyprland festhaelt:
    uebersprungen, nicht durchgefallen, wenn die Sache fehlt, die der
    Test braucht. /usr/lib/hyprland/plugins/hyprbars.so liegt auf jeder
    installierten ZepOS-Maschine; auf einem Entwicklungsrechner ohne das
    Paket zeigt ZEPOS_HYPRBARS_SO auf ein selbst gebautes Objekt. Die
    Messung oben entstand auf diesem Weg - der Fehlgrund unten nennt die
    drei Befehle dafuer.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.render.desktop_session import (  # noqa: E402
    Session, bundle, render_configuration, required_tools,
)
from tests.render import measure  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[2]
BEFEHL = REPOSITORY / "src" / "bin" / "zepos-float-toggle"

# Das ausgelieferte Objekt, und der Ausweg fuer einen Rechner ohne das
# Paket.
GELIEFERT = Path("/usr/lib/hyprland/plugins/hyprbars.so")

# Ein Grellgruen, das in dieser Oberflaeche sonst nirgends vorkommt. Die
# Kopfleiste traegt im Betrieb STYLE_HYPRBARS_BG_COLOR; hier bekommt sie
# eine Farbe, die im Bild eindeutig ihr gehoert. Was gemessen wird, ist
# ihre LAGE, und dafuer ist die Farbe nur ein Griff.
GRUEN = (0, 255, 0)

# Die echte Regel aus hyprland-universal-config.template - die, mit der
# SUPER+Q sein kitty oeffnet.
REGEL_SCHWEBEND = ("match:class ^(floating-default)$, float on, "
                   "center on, size 800 600")

# Die modulweite Vorrichtung `gemessen` startet echte kitty-Fenster in
# einer verschachtelten Sitzung. Der Abstand des Fensterkopfs zum oberen
# Rand und das Flackern beim x sind bemalte Punkte - an der Vorlage ist
# beides nicht zu sehen. Fehlt kitty, ueberspringt die Vorrichtung sich
# selbst; der Marker gilt fuer den Fall, dass es da ist.
pytestmark = pytest.mark.allow_subprocess


def _plugin() -> Path | None:
    aus_umgebung = os.environ.get("ZEPOS_HYPRBARS_SO")
    if aus_umgebung and Path(aus_umgebung).is_file():
        return Path(aus_umgebung)
    if GELIEFERT.is_file():
        return GELIEFERT
    return None


def _kopfzeilen(bild, farbe=GRUEN, toleranz=60) -> tuple[int, int] | None:
    """Erste und letzte Bildzeile, in der diese Farbe steht.

    Jede zweite Spalte wird abgetastet und mehr als vier Treffer
    verlangt: ein einzelner Punkt dieser Farbe waere ein Randartefakt
    der Rundung, kein Streifen.
    """
    zeilen = []
    for y in range(bild.height):
        treffer = 0
        for x in range(0, bild.width, 2):
            punkt = bild.at(x, y)
            if all(abs(punkt[i] - farbe[i]) < toleranz for i in range(3)):
                treffer += 1
        if treffer > 4:
            zeilen.append(y)
    return (zeilen[0], zeilen[-1]) if zeilen else None


@pytest.fixture(scope="module")
def gemessen(tmp_path_factory) -> dict:
    """Dreimal dasselbe Fenster: gekachelt, roh geschwebt, repariert.

    Modulweit und nicht je Zusicherung: der Aufbau kostet einen
    Compositor, eine Oberflaeche und ein Terminal. Und modulweit heisst
    hier zugleich, dass er VOR der Prozesssperre aus tests/conftest.py
    laeuft - dieselbe Bauart wie in test_geometry.py.
    """
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    if not Path("/usr/bin/kitty").is_file():
        pytest.skip("kitty fehlt - die Meldung handelt von kitty-Fenstern")

    objekt = _plugin()
    if objekt is None:
        pytest.skip(
            f"{GELIEFERT} fehlt und ZEPOS_HYPRBARS_SO zeigt auf nichts. "
            "Ohne hyprbars gibt es keinen Fensterkopf, dessen Lage man "
            "messen koennte. Selbst bauen, aus dem in "
            "packaging/hyprland-plugins/PKGBUILD angepinnten Baum:\n"
            "  tar xzf hyprland-plugins-<commit>.tar.gz -C /tmp/hb\n"
            "  meson setup /tmp/bau /tmp/hb/<baum>/hyprbars\n"
            "  meson compile -C /tmp/bau\n"
            "und ZEPOS_HYPRBARS_SO auf /tmp/bau/libhyprbars.so setzen.")

    sys.path.insert(0, str(REPOSITORY / "src"))
    import sizes
    abschnitt: dict = {}
    hoehe = int(sizes.value_of("STYLE_HYPRBARS_HEIGHT", abschnitt))
    knopf = int(sizes.value_of("STYLE_HYPRBARS_BUTTON_SIZE", abschnitt))
    innen = int(sizes.value_of("STYLE_GAPS_IN", abschnitt))
    aussen = int(sizes.value_of("STYLE_GAPS_OUT", abschnitt))

    bau = tmp_path_factory.mktemp("zepkopf-bau")
    bilder = tmp_path_factory.mktemp("zepkopf-bild")
    bundle(render_configuration(bau), bau)

    befund: dict = {"hoehe": hoehe, "gaps_out": aussen, "rahmen": 1}
    sitzung = Session(1920, 1080)
    try:
        sitzung.start()
        sitzung.start_bus()
        sitzung.wallpaper()

        geladen = sitzung.hyprctl("plugin", "load", str(objekt))
        assert geladen.returncode == 0, (
            f"hyprbars liess sich nicht laden: {geladen.stdout}"
            f"{geladen.stderr}")
        # Ohne diese Pause ist die Option unten noch nicht angemeldet.
        time.sleep(1.0)
        assert "hyprbars" in sitzung.hyprctl("plugin", "list").stdout, (
            "das Plugin meldet sich nicht:\n" + sitzung.read_log()[-2000:])

        for schluessel, wert in (
                ("general:gaps_in", str(innen)),
                ("general:gaps_out", str(aussen)),
                ("general:border_size", str(befund["rahmen"])),
                ("plugin:hyprbars:bar_height", str(hoehe)),
                ("plugin:hyprbars:bar_color", "rgb(00ff00)"),
                ("plugin:hyprbars:bar_padding", "6"),
                ("plugin:hyprbars:bar_button_padding", "6")):
            ergebnis = sitzung.hyprctl("keyword", schluessel, wert)
            assert ergebnis.returncode == 0, (
                f"{schluessel} nahm {wert} nicht an: {ergebnis.stderr}")
        # Drei Knoepfe, so viele wie hyprland-plugins-config.template
        # bestellt. Ihre Zahl entscheidet, wie weit links der Streifen
        # anfaengt, in dem das X sitzt.
        for farbe in ("rgb(f38ba8)", "rgb(f9e2af)", "rgb(a6e3a1)"):
            sitzung.hyprctl("keyword", "plugin:hyprbars:hyprbars-button",
                            f"{farbe}, {knopf}, X, hyprctl dispatch killactive")
        sitzung.hyprctl("keyword", "windowrule", REGEL_SCHWEBEND)

        sitzung.shell(bau / "zepos-shell.js", bau)
        time.sleep(10.0)
        flaechen = sitzung.layers()
        assert "zepos-bar" in flaechen, (
            "es liegt keine Leiste auf dem Schirm, also reserviert nichts "
            "den oberen Streifen:\n" + sitzung.read_shell_log()[-1500:])

        schirm = next(m for m in sitzung.hyprctl_json("monitors")
                      if m["name"] == sitzung.output)
        befund["reserved"] = list(schirm["reserved"])
        befund["flaeche_oben"] = schirm["y"] + schirm["reserved"][1]
        befund["flaeche_hoehe"] = (schirm["height"] - schirm["reserved"][1]
                                   - schirm["reserved"][3])

        sitzung.move_cursor(schirm["x"] + 960, schirm["y"] + 540)
        sitzung.spawn(["kitty"])
        frist = time.monotonic() + 30
        while time.monotonic() < frist:
            if any(c.get("class") == "kitty"
                   for c in sitzung.hyprctl_json("clients") or []):
                break
            time.sleep(0.3)
        else:
            raise AssertionError("kitty ist nicht erschienen:\n"
                                 + sitzung.read_shell_log()[-1500:])
        time.sleep(4.0)

        def kitty():
            for c in sitzung.hyprctl_json("clients") or []:
                if c.get("class") == "kitty":
                    return c
            raise AssertionError("das kitty-Fenster ist fort")

        def notiere(name):
            c = kitty()
            bild = sitzung.shoot(bilder / f"{name}.png")
            befund[name] = {
                "at": list(c["at"]), "size": list(c["size"]),
                "floating": bool(c["floating"]),
                # Der Kasten aus at/size ist die HAUPTFLAECHE. Der Kopf
                # sitzt darueber, um bar_height plus den Rahmen.
                "kopf_oben": c["at"][1] - hoehe - befund["rahmen"],
                "gruen": _kopfzeilen(measure.read_png(bild)),
            }

        notiere("gekachelt")

        # ROH, so wie die Taste bis zum 02.09.2026 gebunden war.
        sitzung.hyprctl("dispatch", "focuswindow", "class:^(kitty)$")
        sitzung.hyprctl("dispatch", "togglefloating")
        time.sleep(2.5)
        notiere("roh_geschwebt")

        # Wieder einkacheln, und dann DERSELBE Weg ueber den Befehl.
        sitzung.hyprctl("dispatch", "togglefloating")
        time.sleep(2.5)
        kennung = sitzung.signature()
        lauf = subprocess.run(
            [sys.executable, str(BEFEHL)],
            env=sitzung.environment(HYPRLAND_INSTANCE_SIGNATURE=kennung),
            capture_output=True, text=True, timeout=60)
        befund["ausgang"] = lauf.returncode
        befund["meldung"] = (lauf.stdout + lauf.stderr).strip()
        time.sleep(2.5)
        notiere("repariert")

        befund["log"] = sitzung.read_log()[-3000:]
    finally:
        sitzung.stop()
    return befund


def test_gekachelt_haelt_der_kopf_seinen_abstand(gemessen):
    """Der Ausgangspunkt, und er war nie kaputt.

    Ein gekacheltes Fenster bekommt seinen Platz vom Layout, und das
    zieht die Sperrzone der Leiste UND die reservierte Kopfhoehe ab. Was
    dann noch zwischen Kopf und Flaechenkante liegt, ist gaps_out.

    Diese Zusicherung steht zuerst, weil sie den Verdacht ausraeumt, mit
    dem die Untersuchung begann: nicht `gaps`, nicht `hyprbars`, nicht
    die Bildschirmanordnung. Gekachelt stimmt alles.
    """
    kopf = gemessen["gekachelt"]
    assert not kopf["floating"]
    assert kopf["kopf_oben"] - gemessen["flaeche_oben"] == gemessen["gaps_out"]
    assert kopf["gruen"] is not None, (
        "die Kopfleiste ist im Bild nicht zu finden, obwohl das Fenster "
        "gekachelt in der Flaeche liegt")


def test_roh_umgeschaltet_verlaesst_der_kopf_den_schirm(gemessen):
    """Der Fehler selbst, in Zahlen - und er ist nicht in diesem Projekt.

    `dispatch togglefloating` allein liefert einen Kasten, der hoeher
    ist als die Arbeitsflaeche, und fitBoxInWorkArea() schiebt ihn dann
    oben heraus statt ihn zu schrumpfen: sie klemmt erst mit max() nach
    unten und danach bei Ueberlaenge nach oben, ohne ein zweites max().

    WARUM DIESE ZUSICHERUNG DA IST, obwohl sie fremden Code beschreibt
        Ohne sie waere die Zusicherung darunter nichts wert. Ein
        Befehl, der ein Fenster in die Flaeche setzt, das ohnehin darin
        liegt, besteht jeden Test - und misst nichts. Hier steht, dass
        es OHNE ihn wirklich herausfaellt.

        Sie ist damit auch die Stelle, die ANSCHLAEGT, wenn Hyprland den
        fehlenden max() nachtraegt: dann ist zepos-float-toggle nicht
        mehr noetig und kann fallen. Ein Test, der eine Abhilfe
        ueberlebt, ist ein Test, der sie nie wieder loswird.
    """
    roh = gemessen["roh_geschwebt"]
    assert roh["floating"]
    assert roh["kopf_oben"] < gemessen["flaeche_oben"], (
        "der rohe Dispatcher laesst den Kopf in der Flaeche - dann ist "
        "der Fehler fort und dieser Umweg ueberfluessig: "
        f"{roh} gegen Flaechenkante {gemessen['flaeche_oben']}")
    # Und am Bild dasselbe. GEMESSEN lag der Kopf bei -124, also ganz
    # ausserhalb; seine Farbe kann dann in keiner Zeile stehen. Diese
    # Zeile ist nur deshalb ein Beleg, weil die Zusicherung darunter
    # zeigt, dass dieselbe Suche im reparierten Bild etwas FINDET - eine
    # Farbsuche, die nirgends anschlaegt, belegt sonst gar nichts.
    assert roh["gruen"] is None, (
        f"die Kopfleiste ist im Bild bei {roh['gruen']} zu sehen, "
        f"obwohl hyprctl sie bei {roh['kopf_oben']} meldet - ueber der "
        f"Kante {gemessen['flaeche_oben']}")


def test_der_befehl_holt_den_kopf_zurueck_auf_die_flaeche(gemessen):
    """Die Zusicherung, um die es geht.

    Nach SUPER+V liegt der Kopf INNERHALB der Arbeitsflaeche - und das
    ist an Bildpunkten geprueft und nicht nur an at/size: seine Farbe
    steht im Bild, und ihre erste Zeile ist nicht ueber der Kante.
    """
    assert gemessen["ausgang"] == 0, (
        f"zepos-float-toggle endete mit {gemessen['ausgang']}: "
        f"{gemessen['meldung']}")
    fest = gemessen["repariert"]
    assert fest["floating"], (
        "das Fenster schwebt nach dem Befehl nicht - dann hat er die "
        "Taste um ihre eigentliche Wirkung gebracht")
    assert fest["kopf_oben"] >= gemessen["flaeche_oben"], (
        f"der Kopf liegt bei {fest['kopf_oben']}, die Flaeche beginnt "
        f"bei {gemessen['flaeche_oben']}")
    assert fest["gruen"] is not None, (
        "die Kopfleiste ist im Bild nicht zu finden")
    assert fest["gruen"][0] >= gemessen["flaeche_oben"], (
        f"die oberste bemalte Zeile der Kopfleiste ist "
        f"{fest['gruen'][0]}, die Flaeche beginnt bei "
        f"{gemessen['flaeche_oben']}")


def test_das_bild_zeigt_den_kopf_dort_wo_hyprctl_ihn_meldet(gemessen):
    """Abfrage und Bild muessen dasselbe sagen, sonst sagt keines etwas.

    WARUM DIESE ZUSICHERUNG DA IST
        Ein erster Aufbau suchte eine Farbe, die der Balken zu diesem
        Zeitpunkt nicht trug (der Kopf dieser Datei erzaehlt es), und
        fand deshalb nichts - bei einem Fenster, dessen Kopf in
        Wirklichkeit gut sichtbar dastand. "Nicht gefunden" und "nicht
        da" sind zwei verschiedene Dinge, und nur diese Zeile trennt sie:
        was hyprctl als Lage meldet, muss die Farbsuche an derselben
        Stelle wiederfinden.

    Zwei Punkte Spielraum, und zwar nach unten: die oberste Zeile des
    Balkens traegt die Rundung aus `decoration:rounding`, und dort ist
    nur ein Teil der Breite bemalt - weniger als die vier Treffer, die
    _kopfzeilen() verlangt.
    """
    for name in ("gekachelt", "repariert"):
        fall = gemessen[name]
        assert fall["gruen"] is not None, (
            f"{name}: die Kopfleiste ist im Bild nicht zu finden, obwohl "
            f"hyprctl sie bei {fall['kopf_oben']} meldet")
        gemalt = fall["gruen"][0]
        assert 0 <= gemalt - fall["kopf_oben"] <= 2, (
            f"{name}: das Bild zeigt die Kopfleiste ab Zeile {gemalt}, "
            f"hyprctl meldet sie ab {fall['kopf_oben']}")


def test_das_fenster_bleibt_dabei_ganz_in_der_flaeche(gemessen):
    """Nicht nur der Kopf, und das ist kein Beiwerk.

    Ein Befehl, der den Kopf hereinholt und den Fuss dafuer unter das
    Dock schiebt, hat die Meldung beantwortet und ein zweites Mal
    dasselbe getan. Geprueft wird deshalb der GANZE Kasten mitsamt
    Rahmen, gegen beide Kanten.
    """
    fest = gemessen["repariert"]
    oben = fest["kopf_oben"]
    unten = fest["at"][1] + fest["size"][1] + gemessen["rahmen"]
    kante = gemessen["flaeche_oben"] + gemessen["flaeche_hoehe"]
    assert oben >= gemessen["flaeche_oben"]
    assert unten <= kante, (
        f"die Unterkante liegt bei {unten}, die Flaeche endet bei "
        f"{kante}")
