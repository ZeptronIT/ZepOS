# SPDX-License-Identifier: GPL-3.0-or-later
"""SUPER+V, und der Fensterkopf bleibt auf dem Schirm.

WAS GEMELDET WURDE
    Der Nutzer am 01.09.2026, zweimal am selben Tag:

      "irgendwie haben seit der neusten version die kitty terminals oben
       der header wo x minimieren und vollbild ist keinen abstand zum
       oberen rand"

      "fenster die schweben mit super v sieht man auf dem header oben
       recht bei dem x ein flackern des headers voll komisch"

WAS GEMESSEN IST, und die Zahlen unten sind genau diese
    Am 02.09.2026 an einem verschachtelten Hyprland 0.56.2 mit dieser
    Oberflaeche und diesem hyprbars, 1920x1080, ausgelieferte Groesse
    (tests/render/test_fensterkopf_bild.py fuehrt die Messung aus):

        Schirm            bei 4000,0, 1920x1080, reserved [0, 84, 0, 84]
        Arbeitsflaeche    y 84..996, Hoehe 912
        bar_height 38, border_size 1, gaps_out 24

        gekachelt              at (4025, 147)  1870x824
                               Kopf oben 108 = 84 + 24        RICHTIG
        dasselbe, roh geschwebt
                               at (3999, -85)  1920x1080
                               Kopf oben -124                 208 PUNKTE
                                                              UEBER DEM
                                                              RAND
        dasselbe ueber den Befehl
                               at (4001, 123)  1918x872
                               Kopf oben 84                   AN DER
                                                              KANTE

    Am Bild dasselbe: im rohen Fall stand die Farbe der Kopfleiste in
    keiner einzigen Zeile, im reparierten ab Zeile 84.

WO DER FEHLER ENTSTEHT, UND ES IST NICHT DIESES PROJEKT
    Hyprlands fitBoxInWorkArea() in src/layout/algorithm/floating/
    default/DefaultFloatingAlgorithm.cpp klemmt in zwei Schritten:
    zuerst `std::max(targetBox.y, WORK_AREA.y)`, dann bei Ueberlaenge
    `targetBox.y = WORK_AREA.y + WORK_AREA.h - targetBox.h`. Nach dem
    zweiten steht kein max() mehr. Ein Kasten, der HOEHER ist als die
    Arbeitsflaeche, wird deshalb oben herausgeschoben - genau um seinen
    Ueberschuss, und die Rechnung geht auf den Punkt auf:
    1080 + 39 + 1 = 1120, und 84 + 912 - 1120 = -124.

WARUM DIESER TEST OHNE COMPOSITOR LAEUFT UND EIN ZWEITER MIT
    Gefragt sind hier zwei verschiedene Dinge, und sie brauchen zwei
    verschiedene Aufbauten.

      Hier             RECHNET der Pruefling richtig? Das ist Arithmetik
                       auf vier Zahlen aus `hyprctl`, und ein echter
                       Compositor macht sie nicht richtiger - er macht
                       sie nur langsamer und von einer laufenden
                       Wayland-Sitzung abhaengig. Das vorgetaeuschte
                       hyprctl liefert deshalb GENAU die gemessenen
                       Zahlen, und geprueft wird, welche Dispatcher der
                       Befehl daraufhin abschickt.

      tests/render/    STIMMT die Rechnung mit dem, was der Schirm
                       zeigt? Das gibt es nur an einem echten Hyprland
                       mit echtem hyprbars, und dieser Test wird
                       uebersprungen, wo das Plugin fehlt.

    Ein Test, der nur die Vorlage durchsucht, waere keiner: der Befehl
    unten wird WIRKLICH ausgefuehrt, mit einem hyprctl auf dem PATH, das
    jeden Aufruf mitschreibt.

WARUM EIN SKRIPT UND KEIN MOCK-OBJEKT
    Dieselbe Ueberlegung wie in test_claude_code.py: der Pruefling ist
    eine Schale um `hyprctl`. Was er tut, haengt an Rueckgabewerten und
    an JSON - ein Objekt haette die eine Schnittstelle nachgebaut, die
    hier gerade nicht gemessen werden soll.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
BEFEHL = SRC / "bin" / "zepos-float-toggle"
VORLAGE = SRC / "templates" / "hyprland-universal-config.template"
REZEPT = REPOSITORY / "packaging" / "zepos-config" / "PKGBUILD"

# Die Kennung, unter der das Fenster in allen Abfragen steht. Eine echte
# Hyprland-Adresse, in der Form, in der `hyprctl -j` sie ausgibt: der
# Pruefling haengt sie an jeden Dispatcher, und ein Test mit "0x1" haette
# nicht gemessen, dass er das ueberhaupt tut.
ADRESSE = "0x5f8b2c4a1e30"

# Der Schirm, an dem gemessen wurde. reserved ist [links, oben, rechts,
# unten] - HyprCtl.cpp Zeile 281/282 schreibt sie in dieser Reihenfolge,
# und die 84 oben ist die Leiste dieses Schreibtischs
# (STYLE_BAR_THICKNESS 60 + gaps_out 24), die 84 unten das Dock.
SCHIRM = {
    "id": 1, "name": "HEADLESS-1",
    "x": 4000, "y": 0, "width": 1920, "height": 1080,
    "reserved": [0, 84, 0, 84], "scale": 1.0,
}

# Was `hyprctl -j clients` NACH dem Umschalten gemeldet hat. Nicht
# erfunden: genau diese vier Zahlen stehen im Kopf dieser Datei.
KAPUTT = {
    "address": ADRESSE, "class": "kitty", "floating": True,
    "monitor": 1, "at": [3999, -85], "size": [1920, 1080],
}

# Und das gekachelte Fenster davor.
GEKACHELT = {
    "address": ADRESSE, "class": "kitty", "floating": False,
    "monitor": 1, "at": [4025, 147], "size": [1870, 824],
}

# Das schwebende, zentrierte kitty, das SUPER+Q oeffnet - `windowrule =
# match:class ^(floating-default)$, float on, center on, size 800 600`.
# Gemessen am 02.09.2026 lag es bei (4560, 240), sein Kopf bei 201, und
# das ist richtig. Es steht hier, damit geprueft ist, dass der Befehl es
# NICHT anfasst.
HEIL = {
    "address": ADRESSE, "class": "floating-default", "floating": True,
    "monitor": 1, "at": [4560, 240], "size": [800, 600],
}

# Die Einstellungen, wie sie zur Messung standen.
OPTIONEN = {"plugin:hyprbars:bar_height": 38, "general:border_size": 1}

# Das vorgetaeuschte hyprctl. Es liest seinen ganzen Zustand aus einer
# Datei und schreibt jeden Aufruf in eine zweite - damit misst der Test
# nicht nur, WAS herauskommt, sondern auch, ob der Befehl eine Abfrage
# ueberhaupt gestellt hat. Der Unterschied zwischen "hat nichts
# geaendert" und "hat nicht einmal nachgesehen" ist genau der, um den es
# in test_eingekachelt_... geht.
#
# Der Deuter steht ABSOLUT in der ersten Zeile und nicht als `/usr/bin/env
# python3`: der PATH unten traegt nur das Stubverzeichnis, und `env`
# haette python3 darauf gesucht und nicht gefunden. Gemessen war das ein
# hyprctl, das gar nicht erst startete - und ein Pruefling, der brav
# nichts tat, weil er auf keine Abfrage eine Antwort bekam. Ein Test, der
# aus diesem Grund gruen wird, sagt nichts.
#
# Verkettet und nicht als f-String: der Rumpf darunter enthaelt
# {"int": ...} und {args[2]}, und ein f-String haette beide als
# Einsetzungen gelesen.
HYPRCTL_ATTRAPPE = "#!" + sys.executable + "\n" + '''\
import json, os, sys

args = sys.argv[1:]
with open(os.environ["HYPR_PROTOKOLL"], "a") as sink:
    sink.write(" ".join(args) + "\\n")

zustand = json.load(open(os.environ["HYPR_ZUSTAND"]))

if args[:1] == ["-j"]:
    was = args[1]
    if was == "activewindow":
        print(json.dumps(zustand["vorher"]))
    elif was == "clients":
        print(json.dumps(zustand["nachher"]))
    elif was == "monitors":
        print(json.dumps(zustand["schirme"]))
    elif was == "getoption":
        if args[2] not in zustand["optionen"]:
            # Genau das antwortet hyprctl, wenn hyprbars nicht geladen
            # ist: die Option gibt es nicht.
            print(f"no such option {args[2]}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"int": zustand["optionen"][args[2]]}))
    else:
        sys.exit(1)
    sys.exit(0)

print("ok")
'''


@pytest.fixture
def stand(tmp_path):
    """Ein PATH mit genau einem Werkzeug darauf: dem falschen hyprctl.

    NUR diesem, und das ist Absicht. Mit /usr/bin im PATH faende der
    Pruefling das ECHTE hyprctl dieser Maschine - und das spricht mit
    der laufenden Sitzung des Menschen, der den Test gestartet hat.
    Dieselbe Ueberlegung wie bei den Sitzungen in test_login.py.
    """
    stube = tmp_path / "bin"
    stube.mkdir()
    falsch = stube / "hyprctl"
    falsch.write_text(HYPRCTL_ATTRAPPE, encoding="utf-8")
    falsch.chmod(0o755)

    protokoll = tmp_path / "aufrufe.txt"
    zustand = tmp_path / "zustand.json"

    def lauf(vorher, nachher, schirme=(SCHIRM,), optionen=None):
        zustand.write_text(json.dumps({
            "vorher": vorher,
            "nachher": list(nachher),
            "schirme": list(schirme),
            "optionen": dict(OPTIONEN if optionen is None else optionen),
        }), encoding="utf-8")
        protokoll.write_text("", encoding="utf-8")
        ergebnis = subprocess.run(
            [sys.executable, str(BEFEHL)],
            env={"PATH": str(stube),
                 "HYPR_PROTOKOLL": str(protokoll),
                 "HYPR_ZUSTAND": str(zustand),
                 "HOME": str(tmp_path)},
            capture_output=True, text=True, timeout=60)
        assert ergebnis.returncode == 0, (
            f"zepos-float-toggle endete mit {ergebnis.returncode}:\n"
            f"{ergebnis.stdout}{ergebnis.stderr}")
        zeilen = [z for z in protokoll.read_text(encoding="utf-8").splitlines()
                  if z]
        return zeilen

    return lauf


def _dispatcher(zeilen, name):
    """Die Argumente des einen Dispatchers dieses Namens, oder None."""
    treffer = [z for z in zeilen if z.startswith(f"dispatch {name} ")]
    assert len(treffer) <= 1, f"{name} wurde mehrfach abgeschickt: {treffer}"
    return treffer[0] if treffer else None


@pytest.mark.allow_subprocess
def test_der_befehl_schaltet_zuerst_ueberhaupt_um(stand):
    """`togglefloating` bleibt der Dispatcher, der die Arbeit macht.

    Und er bekommt die ADRESSE mit. Ohne sie traefe er "das aktive
    Fenster" - und zwischen der Abfrage davor und dem Umschalten kann
    sich der Fokus geaendert haben, etwa weil eine Anwendung gerade ein
    Fenster oeffnet. Ein Befehl, der ein anderes Fenster umschaltet als
    das, dessen Lage er danach nachrechnet, ist schlimmer als keiner.
    """
    zeilen = stand(GEKACHELT, [KAPUTT])
    assert f"dispatch togglefloating address:{ADRESSE}" in zeilen


@pytest.mark.allow_subprocess
def test_das_gemessene_fenster_kommt_zurueck_auf_die_arbeitsflaeche(stand):
    """Der Fall aus der Meldung, mit den gemessenen Zahlen.

    Die Rechnung, Schritt fuer Schritt:

        Arbeitsflaeche   x 4000, y 84, 1920 breit, 912 hoch
        Grenzmass        1920 - 2*1        = 1918 breit
                         912 - 38 - 2*1    =  872 hoch
        1920x1080 ist zu gross            -> 1918x872
        Lage             y = max(-85, 84 + 38 + 1) = 123
        Kopf oben        123 - 38 - 1 = 84 = obere Kante der Flaeche

    Die letzte Zeile ist die Zusicherung: der Kopf liegt danach GENAU an
    der Kante und nicht darueber. Er klebt daran, weil der Befehl nur
    das Notwendige tut - wer Abstand will, zieht das Fenster.
    """
    zeilen = stand(GEKACHELT, [KAPUTT])

    assert _dispatcher(zeilen, "resizewindowpixel") == (
        f"dispatch resizewindowpixel exact 1918 872,address:{ADRESSE}")
    assert _dispatcher(zeilen, "movewindowpixel") == (
        f"dispatch movewindowpixel exact 4001 123,address:{ADRESSE}")

    kopf_oben = 123 - OPTIONEN["plugin:hyprbars:bar_height"] - 1
    assert kopf_oben == SCHIRM["y"] + SCHIRM["reserved"][1] == 84


@pytest.mark.allow_subprocess
def test_ein_fenster_das_schon_passt_wird_nicht_angefasst(stand):
    """Das schwebende kitty von SUPER+Q, und der Befehl laesst es stehen.

    WARUM DAS EINE EIGENE ZUSICHERUNG IST
        Ein Befehl, der jedes Fenster auf die Arbeitsflaeche setzt,
        haette denselben Test bestanden und trotzdem alles kaputt
        gemacht: SUPER+V wuerde dann jede gemerkte Schwebegroesse und
        jede Lage ueberschreiben. Der Fehler traf nur Fenster, die nicht
        hineinpassen; die Abhilfe darf auch nur die anfassen.
    """
    zeilen = stand(KAPUTT, [HEIL])
    assert _dispatcher(zeilen, "resizewindowpixel") is None
    assert _dispatcher(zeilen, "movewindowpixel") is None


@pytest.mark.allow_subprocess
def test_eingekacheltes_fenster_wird_nicht_nachgerechnet(stand):
    """Wer einkachelt, ueberlaesst die Lage dem Layout.

    Und das rechnet die Sperrzone von selbst mit: gemessen lag der Kopf
    des gekachelten Fensters bei 108, die Arbeitsflaeche beginnt bei 84,
    der Unterschied ist gaps_out. Hier ist nichts zu reparieren - und
    der Befehl fragt deshalb nicht einmal nach den Schirmen.
    """
    zeilen = stand(KAPUTT, [GEKACHELT])
    assert f"dispatch togglefloating address:{ADRESSE}" in zeilen
    assert _dispatcher(zeilen, "resizewindowpixel") is None
    assert _dispatcher(zeilen, "movewindowpixel") is None
    assert not [z for z in zeilen if "monitors" in z], (
        "der Befehl hat die Schirme abgefragt, obwohl das Fenster "
        "gekachelt ist - eine Abfrage, deren Antwort er nicht braucht")


@pytest.mark.allow_subprocess
def test_ohne_hyprbars_rechnet_der_befehl_mit_gar_keinem_kopf(stand):
    """Kein Plugin, kein Kopf - und die Rechnung stimmt trotzdem.

    src/plugins.py laesst den ganzen hyprbars-Block weg, wenn
    /usr/lib/hyprland/plugins/hyprbars.so fehlt; dann gibt es
    plugin:hyprbars:bar_height nicht, und `hyprctl getoption` scheitert.
    Ein eingesetztes {{STYLE_HYPRBARS_HEIGHT}} waere hier um 38 Punkte
    falsch - der Befehl liest die Zahl deshalb zur Laufzeit.

    Dasselbe gilt fuer SUPER+ALT+B: ~/.local/bin/hyprbars-toggle setzt
    bar_height auf 0, und danach ist genau dieser Fall der richtige.
    """
    zeilen = stand(GEKACHELT, [KAPUTT],
                   optionen={"general:border_size": 1})

    # 912 - 0 - 2*1 = 910 hoch, und die Untergrenze ist 84 + 0 + 1.
    assert _dispatcher(zeilen, "resizewindowpixel") == (
        f"dispatch resizewindowpixel exact 1918 910,address:{ADRESSE}")
    assert _dispatcher(zeilen, "movewindowpixel") == (
        f"dispatch movewindowpixel exact 4001 85,address:{ADRESSE}")


@pytest.mark.allow_subprocess
def test_oben_und_unten_werden_nicht_verwechselt(stand):
    """Ein Schirm mit Dock, aber ohne Leiste - reserved [0, 0, 0, 84].

    WARUM DIESER FALL DA IST
        `reserved` sind vier Zahlen in einer Liste, und oben mit unten
        zu verwechseln ist der Fehler, den man dabei macht. Er waere auf
        dem Schirm des Entwicklers unsichtbar: dort sind beide 84, und
        jede Verwechslung kommt auf dasselbe Ergebnis heraus. Also ein
        Schirm, auf dem sie sich unterscheiden.

        Arbeitsflaeche y 0..996. Untergrenze 0 + 38 + 1 = 39, und der
        Kopf liegt danach bei 39 - 39 = 0, der oberen Kante. Wer oben
        und unten tauscht, bekommt 123 - und ein Fenster, das nach jedem
        SUPER+V ein Stueck weiter nach unten rutscht.
    """
    schirm = dict(SCHIRM, reserved=[0, 0, 0, 84])
    zeilen = stand(GEKACHELT, [KAPUTT], schirme=(schirm,))

    assert _dispatcher(zeilen, "movewindowpixel") == (
        f"dispatch movewindowpixel exact 4001 39,address:{ADRESSE}")


@pytest.mark.allow_subprocess
def test_der_richtige_schirm_wird_gewaehlt(stand):
    """Zwei Schirme, und das Fenster liegt auf dem zweiten.

    Der Nutzer hat zwei Monitore. Ein Befehl, der den erstbesten Schirm
    aus der Liste nimmt, rechnet dann mit der falschen Arbeitsflaeche -
    und zwar um so falscher, je unterschiedlicher die beiden sind.
    Gemessen am 02.09.2026 an zwei verschachtelten Ausgaengen: BEIDE
    melden reserved [0, 84, 0, 84], die Leiste liegt also auf jedem.
    """
    links = dict(SCHIRM, id=0, name="HEADLESS-0", x=0, height=768,
                 reserved=[0, 84, 0, 0])
    zeilen = stand(GEKACHELT, [KAPUTT], schirme=(links, SCHIRM))

    # Gerechnet werden muss mit SCHIRM (id 1), nicht mit dem 768 hohen.
    assert _dispatcher(zeilen, "resizewindowpixel") == (
        f"dispatch resizewindowpixel exact 1918 872,address:{ADRESSE}")


@pytest.mark.allow_subprocess
def test_ohne_aktives_fenster_passiert_nichts(stand):
    """Keine Taste soll ins Leere greifen.

    `hyprctl -j activewindow` antwortet auf einem leeren Arbeitsbereich
    mit einem Objekt ohne address. Ein Umschalten waere dort wirkungslos
    - und der Befehl schickt es deshalb gar nicht erst ab.
    """
    zeilen = stand({}, [])
    assert not [z for z in zeilen if z.startswith("dispatch")]


def test_super_v_ruft_den_befehl():
    """Die Taste aus der Meldung zeigt auf den Befehl - und nur auf ihn.

    Ohne diese Zusicherung waere die ganze Rechnung darueber ein
    Programm, das niemand aufruft: `bind = $mainMod, V, togglefloating`
    ist genau die Zeile, die den Fehler gezeigt hat, und sie sieht der
    neuen zum Verwechseln aehnlich.
    """
    text = VORLAGE.read_text(encoding="utf-8")
    # `$mainMod, V,` und nicht `, V,`: es gibt eine zweite Taste auf
    # demselben Buchstaben - `bind = $mainMod ALT, V, exec,
    # ~/.config/hypr/cliphist-menu.sh` -, und die gehoert nicht hierher.
    binds = [z.strip() for z in text.splitlines()
             if z.startswith("bind") and "$mainMod, V," in z]
    assert binds == ["bind = $mainMod, V, exec, zepos-float-toggle"], (
        "SUPER+V ist nicht (mehr) zepos-float-toggle: " + repr(binds))


def test_das_rezept_legt_den_befehl_ab():
    """Ein gebundener Befehl, den kein Paket installiert, ist Spec 7.4.

    Die Bindung darueber wuerde auf jeder installierten Maschine ins
    Leere greifen, und zwar stumm: Hyprland meldet einen fehlgeschlagenen
    exec nicht auf dem Schirm.
    """
    assert BEFEHL.is_file(), f"{BEFEHL} fehlt"
    assert os.access(BEFEHL, os.X_OK), (
        f"{BEFEHL} ist nicht ausfuehrbar - `bind = ..., exec, ...` "
        "startet sie dann nicht")
    assert "bin/zepos-float-toggle" in REZEPT.read_text(encoding="utf-8"), (
        "packaging/zepos-config/PKGBUILD legt zepos-float-toggle nicht "
        "in /usr/bin ab")
