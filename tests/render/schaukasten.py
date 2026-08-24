# SPDX-License-Identifier: GPL-3.0-or-later
"""Der ganze Schaukasten, bewegt - eine kurze Aufnahme je Bild der READMEs.

    .venv/bin/python -m tests.render.schaukasten [--out VERZEICHNIS]
                                                 [--takt N] [--nur NAME,NAME]
                                                 [--guete N] [--nur-bilder]

WAS ENTSTEHT
    <name>.webp             Je Szene eine Aufnahme im animierten WebP.
    messwerte.txt           Was GEMESSEN wurde - je Szene die erreichte
                            Bildrate, die Zahl der Bilder, die Laenge,
                            die Byte-Groesse. Kein Wort davon ist
                            geschaetzt.
    bilder/<name>/          Jedes Einzelbild, unveraendert. Wer die
                            Aufnahmen auf Personenbezug pruefen will,
                            prueft DIESE Dateien und nicht das Erzeugnis.

WARUM WebP UND NICHT GIF
    GEMESSEN am 24.08.2026 an GitHubs eigenem Renderer und an einer
    fremden, echten Seite - siehe _WARUM_WEBP weiter unten. Kurz: eine
    animierte WebP-Datei laeuft in einer README von selbst, und sie
    kostet bei gleicher Laenge einen Bruchteil eines GIF.

WARUM ES DIESE DATEI NEBEN film.py GIBT
    film.py nimmt EINEN Ablauf auf, zwoelf Sekunden lang, und erklaert
    damit etwas. Hier geht es um das Gegenteil: viele SEHR kurze
    Aufnahmen, je eine Bewegung, und zwar so viele, wie der Schaukasten
    Bilder hat. Beides aus einer Datei waere eine Datei mit zwei
    Absichten. Die gemeinsamen Handgriffe - Starter bauen, Bus, ein
    Schirm, Anwendungsverzeichnis - werden aus film.py IMPORTIERT und
    nicht abgeschrieben.

WAS HIER ANDERS LAEUFT ALS IN JEDER ANDEREN MESSSITZUNG, UND WARUM
    Die Sitzungen aus desktop_session.py fahren mit
    `animations { enabled = false }`. Das ist fuer ein STANDBILD richtig
    und dort auch so begruendet ("damit das Bild nicht mitten in einer
    Einblendung entsteht"). Fuer eine Aufnahme ist es der Fehler selbst:
    ohne Animationen gibt es zwischen "zu" und "auf" kein einziges
    Zwischenbild, und die Aufnahme waere eine Diaschau aus zwei Bildern.

    Dieser Lauf schaltet die Animationen deshalb zur Laufzeit wieder
    ein - mit den Werten aus hyprland-universal-config.template, also
    genau mit dem, was auf einer Installation gilt. Ueber
    `hyprctl keyword`, in DIESER Sitzung; an desktop_session.py aendert
    sich nichts, und keine bestehende Messsitzung laeuft dadurch anders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render import desktop_session as session   # noqa: E402
from tests.render import film                         # noqa: E402
from tests.render import measure                       # noqa: E402

SRC = ROOT / "src"


# _WARUM_WEBP
#
#     Der Vorgaenger hat fuer GIF nachgewiesen, dass GitHub es in einer
#     README von selbst abspielt. Fuer WebP ist dieselbe Probe am
#     24.08.2026 gemacht worden, mit demselben Werkzeug und derselben
#     zweiten Frage an eine echte fremde Seite:
#
#     1. GitHubs Renderer (`gh api -X POST /markdown`, Modus `gfm`)
#        laesst `<img src="....webp">` STEHEN, aus HTML wie aus
#        Markdown, und haengt `style="max-width: 100%"` an. Was es NICHT
#        anhaengt, ist `data-animated-image=""` - das bekommt nur `.gif`.
#
#     2. Genau das ist der Punkt. `data-animated-image` ist die Marke,
#        an der GitHubs Barrierefreiheitsschicht ein Bild in einen
#        Abspieler mit Anhalteknopf einpackt, sobald der Betrachter
#        `prefers-reduced-motion` gesetzt hat. Ein WebP traegt diese
#        Marke nicht und ist damit ein gewoehnliches <img> - der
#        Browser spielt es ab, immer, ohne Knopf.
#
#     3. An einer echten Seite nachgesehen und nicht angenommen:
#        github.com/quick-lint/quick-lint-js/tree/master/plugin/vscode
#        zeigt `demo.webp` (105 882 Byte, 75 Bilder, 51 ANMF-Bloecke)
#        als schlichtes
#            <img src="/quick-lint/quick-lint-js/raw/master/plugin/
#                      vscode/demo.webp" alt="..." style="max-width:100%">
#        - kein Abspieler, kein Knopf, kein Standbild davor.
#
#     4. Und die Bytes kommen unveraendert an: ueber
#        github.com/.../raw/... und ueber raw.githubusercontent.com
#        liefert GitHub dieselbe Datei, sha256 gleich, Content-Type
#        image/webp. Es rechnet nichts um und wirft keine Animation weg.
#
#     WAS DAS KOSTET, UND ES GEHOERT DAZUGESAGT: weil die Marke fehlt,
#     achtet ein WebP NICHT auf `prefers-reduced-motion`. Ein Betrachter,
#     der seinem System weniger Bewegung befohlen hat, bekommt bei GIF
#     ein Standbild und einen Knopf - bei WebP bekommt er die Bewegung.
#     Das ist der einzige Punkt, in dem GIF hier besser ist, und beide
#     READMEs sagen ihn.
WEBP_GUETE = 55

# Die Bildrate, die vorgegeben wird. 25 Bilder/s ist die Zahl, ab der
# das Auge aufhoert, Einzelbilder zu sehen.
#
# GEMESSEN am 24.08.2026, warum das ueberhaupt geht: `grim -l 1` auf
# 1920x1080 braucht 64 ms und reicht damit fuer keine 16 Bilder/s.
# `grim -t ppm` braucht 32 ms, weil es NICHTS komprimiert - die Datei
# ist dann 6 MB statt 384 kB, und genau diese 6 MB sind der Preis fuer
# die Fluessigkeit. Sie liegen im Arbeitsspeicher (/dev/shm) und sind
# nach dem Bau der Datei wieder weg.
TAKT_MS = 40

# Der Rand um eine gemessene Flaeche. Eine Aufnahme, die genau auf die
# Endlage zugeschnitten ist, schneidet die Einblendung ab: Hyprland faehrt
# eine Layer-Flaeche von aussen herein.
RAND = 28

# Wie breit eine Aufnahme des GANZEN Schirms wird. 960 ist die exakte
# Haelfte von 1920, also ganzzahlig skaliert und damit deutlich schaerfer
# als eine krumme Zahl. Ausschnitte behalten ihre eigene Groesse.
VOLLBILD_BREITE = 960

# Die Vorlagen, die dieser Lauf zusaetzlich zu denen aus film.py braucht,
# und wohin generate_config.sh sie legt (abgelesen an den case-Zweigen).
#
# Die drei hypr-Dateien sind kein Beiwerk: src/keybinds.py liest GENAU
# diese drei (HYPRLAND_CONF, PLUGINS_CONF, hyprland-failsafe.conf), und
# ohne sie ist die Kuerzelliste LEER - eine Aufnahme von nichts.
ZUSATZVORLAGEN = {
    "templates/hyprland-universal-config.template": "hypr/hyprland.conf",
    "templates/hyprland-plugins-config.template": "hypr/plugins.conf",
    "templates/hyprland-failsafe-config.template":
        "hypr/hyprland-failsafe.conf",
    "templates/zepos-menu-config.template": "zepos-menu/config",
    # OHNE DIESE ZEILE ZEICHNET JEDES FREMDE GTK4-FENSTER HELL
    #     GEMESSEN am 24.08.2026: die Einstellungs-App ging als weisser
    #     Kasten mitten auf einem dunklen Schreibtisch auf. Die
    #     Farbvorliebe steht in gtk-4.0/settings.ini (aus film.
    #     NEBENVORLAGEN) UND in kdeglobals - GTK4 liest beide, und wer
    #     nur eines hinlegt, bekommt das Ergebnis des anderen.
    "templates/kdeglobals-config.template": "kdeglobals",
}


def hypr_block(name: str, text: str) -> list[tuple[str, str]]:
    """Einen Block der ERZEUGTEN hyprland.conf als Schluessel/Wert lesen.

    Dasselbe Verfahren wie film._general_block, nur mit dem Blocknamen
    als Argument - hier wird ausser `general` auch `animations`
    gebraucht, und zwei Funktionen, die sich in einer Zeichenkette
    unterscheiden, sind eine Funktion zu viel.

    Mehrfach vorkommende Schluessel (`animation = ...` steht fuenfmal
    da) bleiben als eigene Paare stehen; die Reihenfolge ist die der
    Vorlage, und bei Hyprland ist sie die Bedeutung.
    """
    werte: list[tuple[str, str]] = []
    tiefe = 0
    for zeile in text.splitlines():
        if tiefe == 0 and zeile.startswith(f"{name} {{"):
            tiefe = 1
            continue
        if tiefe:
            tiefe += zeile.count("{") - zeile.count("}")
            if tiefe == 0:
                break
            blank = zeile.strip()
            if not blank or blank.startswith("#") or "=" not in blank:
                continue
            schluessel, wert = blank.split("=", 1)
            werte.append((schluessel.strip(), wert.strip()))
    assert werte, f"der {name}-Block steht nicht mehr in der Vorlage"
    return werte


def bewegung_anschalten(live: session.Session, text: str) -> list[str]:
    """Hyprlands Animationen einschalten - mit den Werten der Vorlage.

    WARUM DAS DER WICHTIGSTE HANDGRIFF DIESER DATEI IST
        desktop_session.py setzt `animations { enabled = false }`, und
        fuer ein Standbild ist das richtig. Eine Aufnahme davon zeigt
        zwischen "zu" und "auf" NICHTS - das Fenster ist im einen Bild
        weg und im naechsten ganz da. Das ist keine Animation, das sind
        zwei Standbilder hintereinander.

        Erfunden wird hier nichts: `bezier` und die fuenf
        `animation`-Zeilen kommen aus dem animations-Block der
        ERZEUGTEN hyprland.conf, also aus demselben Text, den eine
        Installation liest. Was die Vorlage NICHT setzt - die
        Layer-Flaechen (`layersIn`/`layersOut`) - bleibt auf Hyprlands
        Vorgabe, und zwar genau wie auf einer Installation.
    """
    gesetzt: list[str] = []
    for schluessel, wert in hypr_block("animations", text):
        if schluessel == "enabled":
            ergebnis = live.hyprctl("keyword", "animations:enabled", wert)
        elif schluessel in ("bezier", "animation"):
            ergebnis = live.hyprctl("keyword", schluessel, wert)
        else:                                            # pragma: no cover
            continue
        assert ergebnis.returncode == 0, (
            f"{schluessel} = {wert} kam nicht an: {ergebnis.stderr}")
        gesetzt.append(f"{schluessel} = {wert}")
    return gesetzt


class Klappe:
    """Einzelbilder in festem Takt, mit der Uhrzeit zu jedem.

    Wie film.Aufnahme, mit zwei Unterschieden, und beide dienen der
    Bildrate:

      * `-t ppm` statt PNG. GEMESSEN am 24.08.2026: PNG-Stufe 1 kostet
        64 ms je Bild und deckelt damit auf 15 Bilder/s. PPM komprimiert
        gar nicht - 32 ms, also Luft fuer 25.
      * ein AUSSCHNITT ist erlaubt. Ein Menue ist 343x311 gross; wer
        dafuer 1920x1080 abzieht, zahlt das Sechsfache an Zeit fuer
        Bildpunkte, die er hinterher wegwirft.

    Gemessen wird auch hier NICHT der eigene Takt, sondern die Uhrzeit
    je Bild. Was der Takt nicht schafft, steht hinterher als kleinere
    Zahl in messwerte.txt.
    """

    def __init__(self, live: session.Session, ordner: Path,
                 takt_ms: int = TAKT_MS,
                 ausschnitt: tuple[int, int, int, int] | None = None) -> None:
        self.live = live
        self.ordner = ordner
        self.takt = takt_ms / 1000.0
        self.ausschnitt = ausschnitt
        self.bilder: list[tuple[float, Path]] = []
        self.marken: list[tuple[float, str]] = []
        self.verloren = 0
        self._start = 0.0
        self._nummer = 0
        self._umgebung: dict[str, str] = {}
        self._befehl: list[str] = []

    def marke(self, text: str) -> None:
        self.marken.append((time.monotonic() - self._start, text))

    def __enter__(self) -> "Klappe":
        if self.ordner.is_dir():
            shutil.rmtree(self.ordner)
        self.ordner.mkdir(parents=True, exist_ok=True)
        self._umgebung = self.live.environment()
        self.live.hyprctl("dismissnotify")
        self._befehl = ["grim", "-t", "ppm"]
        if self.ausschnitt:
            x, y, breite, hoehe = self.ausschnitt
            self._befehl += ["-g", f"{x},{y} {breite}x{hoehe}"]
        else:
            self._befehl += ["-o", self.live.output]
        self._start = time.monotonic()
        return self

    def __exit__(self, *_fehler) -> None:
        return None

    def zieh(self) -> None:
        """EIN Bild, jetzt.

        WARUM DER FADEN AUS film.py HIER NICHT WIEDERKEHRT
            Dort laeuft ein Nebenlaeufer, weil das Drehbuch zwoelf
            Sekunden lang etwas anderes tut. Hier dauert eine Szene
            zwei bis drei Sekunden und besteht aus zwei Handgriffen;
            ein Faden brauechte fuer jede Szene einen eigenen Start und
            ein eigenes Ende, und zwischen zwei Szenen liefe er weiter
            und naehme den Ruhezustand mit auf. Ein Aufruf je Bild ist
            hier das Ehrlichere - und die Uhrzeit steht davor.
        """
        begonnen = time.monotonic()
        pfad = self.ordner / f"bild-{self._nummer:05d}.ppm"
        ergebnis = subprocess.run(self._befehl + [str(pfad)],
                                  env=self._umgebung, capture_output=True,
                                  text=True, timeout=60)
        if ergebnis.returncode != 0 or not pfad.is_file():
            # Nicht abbrechen: ein verlorenes Bild ist eine Luecke,
            # ein Abbruch waere die ganze Aufnahme.
            self.verloren += 1
            self.marken.append((begonnen - self._start,
                                f"BILD VERLOREN: {ergebnis.stderr.strip()}"))
            return
        self.bilder.append((begonnen - self._start, pfad))
        self._nummer += 1

    def laufen(self, sekunden: float) -> None:
        """So lange Bilder ziehen, im vorgegebenen Takt."""
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            begonnen = time.monotonic()
            self.zieh()
            rest = self.takt - (time.monotonic() - begonnen)
            if rest > 0:
                time.sleep(rest)

    def laufen_bis(self, bedingung, hoechstens: float,
                   danach: float = 0.0) -> bool:
        """Bilder ziehen, bis etwas eingetreten ist - und dann noch `danach`.

        WARUM ES DAS BRAUCHT, UND ES IST GEMESSEN
            Ein fremdes Programm braucht so lange, wie es braucht.
            GEMESSEN am 24.08.2026: die Einstellungs-App hatte nach
            3,6 s noch kein Fenster, und die Aufnahme zeigte
            dreieinhalb Sekunden leeren Schreibtisch. Eine laengere
            feste Zahl waere dieselbe Wette mit anderem Einsatz -
            entweder wieder zu kurz oder mit Leerlauf am Ende.

            Gefragt wird deshalb der Compositor, waehrend aufgenommen
            wird. Die Aufnahme ist damit genau so lang, wie das
            Programm gebraucht hat, und das ist eine gemessene Zahl.
        """
        ende = time.monotonic() + hoechstens
        eingetreten = False
        zuletzt = 0.0
        while time.monotonic() < ende:
            begonnen = time.monotonic()
            self.zieh()
            if not eingetreten and begonnen - zuletzt > 0.2:
                zuletzt = begonnen
                if bedingung():
                    eingetreten = True
                    ende = min(ende, time.monotonic() + danach)
            rest = self.takt - (time.monotonic() - begonnen)
            if rest > 0:
                time.sleep(rest)
        return eingetreten

    def messwerte(self) -> dict:
        assert len(self.bilder) >= 2, (
            f"{self.ordner.name}: weniger als zwei Bilder")
        zeiten = [zeit for zeit, _ in self.bilder]
        abstaende = [b - a for a, b in zip(zeiten, zeiten[1:])]
        laenge = zeiten[-1] - zeiten[0]
        return {
            "bilder": len(self.bilder),
            "laenge_s": laenge,
            "bilder_je_sekunde": (len(self.bilder) - 1) / laenge if laenge else 0,
            "abstand_ms_min": min(abstaende) * 1000,
            "abstand_ms_mittel": sum(abstaende) / len(abstaende) * 1000,
            "abstand_ms_max": max(abstaende) * 1000,
            "verlorene_bilder": self.verloren,
        }


def webp_bauen(bilder: list[tuple[float, Path]], ziel: Path,
               breite: int | None, guete: int, takt_hz: float) -> list[str]:
    """Aus Einzelbildern und ihren Zeiten eine animierte WebP-Datei.

    DIE ZEITEN KOMMEN AUS DER MESSUNG UND NICHT AUS EINER ANNAHME
        Wie in film.gif_bauen traegt die concat-Liste je Bild die
        GEMESSENE Dauer bis zum naechsten. GEPRUEFT am 24.08.2026 an
        einer Probe mit fuenf Bildern und den Dauern 50/4/4/120/4 ms:
        `magick identify` gab 52/4/4/120/41 cs zurueck - der Muxer
        schreibt die Dauern durch und rechnet sie nicht auf eine feste
        Bildrate um.

    _WARUM libwebp UND NICHT libwebp_anim, UND WARUM DIE GLEICHEN
    BILDER VORHER SELBST ZUSAMMENGEFASST WERDEN

        ffmpeg hat zwei Kodierer fuer diese Datei, und beide haben
        genau einen Fehler - GEMESSEN am 24.08.2026 an einer Aufnahme
        des Kontrollzentrums, 41 Bilder, davon 9 verschieden:

            libwebp_anim, verlustbehaftet   5 Bilder     80 762 Byte
            libwebp_anim, verlustfrei       9 Bilder    837 334 Byte
            libwebp, verlustbehaftet       42 Bilder    695 004 Byte
            zusammengefasst + libwebp       9 Bilder    163 688 Byte

        `libwebp_anim` fasst gleiche Bilder zusammen - und wirft im
        verlustbehafteten Betrieb auch VERSCHIEDENE weg. Von neun
        Stufen einer Einblendung blieben fuenf uebrig; die Aufnahme
        ruckelte genau an der Stelle, an der sie fluessig sein soll.
        Das ist der Fehler, der diesem Auftrag am meisten geschadet
        haette, und er faellt nur auf, wenn man die ANMF-Bloecke der
        fertigen Datei ZAEHLT.

        `libwebp` wirft keines weg - dafuer fasst es auch die gleichen
        nicht zusammen und schreibt 42 volle Bilder.

        Also wird hier gemacht, was keiner von beiden richtig macht:
        aufeinanderfolgende BYTE-GLEICHE Bilder werden zu EINEM Bild
        mit der Summe ihrer Dauern - das ist keine Kuerzung, sondern
        genau das, was aufgenommen wurde -, und was danach uebrig
        bleibt, ist verschieden und geht vollstaendig in die Datei.

    KEINE FARBTABELLE, UND DAS IST DER UNTERSCHIED ZU GIF
        GIF kann 256 Farben, deshalb braucht es palettegen/paletteuse
        und deshalb rastert ein Verlauf darin. WebP rechnet wie ein
        Videokodierer; `-q:v` entscheidet, wieviel es behaelt.
    """
    gruppen: list[list] = []
    for nummer, (zeit, pfad) in enumerate(bilder):
        naechste = (bilder[nummer + 1][0] if nummer + 1 < len(bilder)
                    else zeit + 1.0 / takt_hz)
        dauer = max(naechste - zeit, 0.001)
        pruefsumme = hashlib.sha256(pfad.read_bytes()).hexdigest()
        if gruppen and gruppen[-1][0] == pruefsumme:
            gruppen[-1][2] += dauer
        else:
            gruppen.append([pruefsumme, pfad, dauer])

    liste = ziel.parent / f"{ziel.stem}.concat"
    zeilen = []
    for _pruefsumme, pfad, dauer in gruppen:
        # ABSOLUT: der concat-Leser loest relative Pfade gegen das
        # Verzeichnis der LISTE auf und nicht gegen das
        # Arbeitsverzeichnis.
        zeilen.append(f"file '{pfad.resolve()}'")
        zeilen.append(f"duration {dauer:.4f}")
    zeilen.append(f"file '{gruppen[-1][1].resolve()}'")
    liste.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    befehl = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
              "-i", str(liste), "-fps_mode", "passthrough"]
    if breite:
        befehl += ["-vf", f"scale={breite}:-1:flags=lanczos"]
    befehl += ["-c:v", "libwebp", "-lossless", "0", "-q:v", str(guete),
               "-compression_level", "6", "-loop", "0", "-an", str(ziel)]
    ergebnis = subprocess.run(befehl, capture_output=True, text=True,
                              timeout=1800)
    assert ergebnis.returncode == 0, (
        f"ffmpeg ist gescheitert:\n{ergebnis.stderr[-2000:]}")
    liste.unlink(missing_ok=True)

    # NACHGEZAEHLT, UND ZWAR IN DER FERTIGEN DATEI
    #     Jedes Bild einer animierten WebP-Datei steht in einem
    #     ANMF-Block. Sind es weniger, als hineingegeben wurden, hat
    #     der Kodierer welche verschluckt - genau der Fehler oben. Eine
    #     Aufnahme, die das nicht prueft, behauptet ihre Bildrate.
    geschrieben = ziel.read_bytes().count(b"ANMF")
    assert geschrieben >= len(gruppen), (
        f"{ziel.name}: {len(gruppen)} verschiedene Bilder hineingegeben, "
        f"nur {geschrieben} ANMF-Bloecke in der Datei")
    return [" ".join(befehl),
            f"{len(bilder)} Bilder -> {len(gruppen)} verschiedene -> "
            f"{geschrieben} ANMF-Bloecke"]


# ---------------------------------------------------------------------
# Die Szenen
# ---------------------------------------------------------------------
#
# Je Szene: der Dateiname, die Anfrage an app.ts (so, wie eine
# Tastenbindung sie stellt), und wie lange gehalten wird.
#
# WAS "ANFRAGE" HIER HEISST, UND WARUM DAS KEIN NACHGESTELLTER KLICK IST
#     app.ts hat einen requestHandler mit genau diesen Namen darin
#     (`reqStr.includes("control")` und so fort). Er ist der Weg, den
#     JEDE Tastenbindung dieses Systems nimmt: die hyprland.conf bindet
#     `ags request control` auf eine Taste, nicht eine Funktion. Was
#     hier ausgeloest wird, ist also woertlich dasselbe, was der Nutzer
#     mit seiner Tastatur ausloest - nur ohne die Taste, die sich in
#     dieser Verschachtelung nicht schicken laesst (film._WARUM_KEIN_
#     TASTENDRUCK).
UEBERBLENDUNGEN = (
    # Datei                          Anfrage          Ruhe   Halten
    ("kontrollzentrum",              "control",       0.30,  1.30),
    ("tastenkuerzel",                "shortcuts",     0.30,  1.30),
    ("kalender",                     "calendar",      0.30,  1.30),
    ("stil-editor",                  "style",         0.30,  1.30),
    ("einstellungsfenster",          "settings",      0.30,  1.30),
    ("vpn-einstellungen",            "vpn-settings",  0.30,  1.30),
    ("benachrichtigungszentrum",     "notifications", 0.30,  1.30),
    ("sitzungsmenue",                "logout",        0.30,  1.30),
)


def flaeche_messen(live: session.Session, anfrage: str,
                   ruhe: float = 1.6) -> tuple[int, int, int, int] | None:
    """Wo dieses Fenster hinkommt - erst aufmachen, messen, wieder zu.

    WARUM VORHER UND NICHT WAEHRENDDESSEN
        Der Ausschnitt muss VOR dem ersten Bild feststehen; grim
        bekommt ihn auf der Kommandozeile. Die Endlage kennt aber nur
        der Compositor, und erst, wenn das Fenster steht. Also einmal
        auf, `hyprctl layers` fragen, wieder zu - und die Aufnahme
        laeuft danach auf einem Schirm im Ruhezustand.

    Was NEU dazugekommen ist, ist das Fenster: verglichen werden die
    Namensraeume vorher und nachher. So muss hier keine Liste stehen,
    die mit den Vorlagen auseinanderlaufen kann.
    """
    vorher = set(live.layers())
    live.request(anfrage)
    time.sleep(ruhe)
    nachher = live.layers()
    neu = {name: lage for name, lage in nachher.items() if name not in vorher}
    live.request(anfrage)
    time.sleep(1.0)
    if not neu:
        return None
    links = min(lage[0] for lage in neu.values())
    oben = min(lage[1] for lage in neu.values())
    rechts = max(lage[0] + lage[2] for lage in neu.values())
    unten = max(lage[1] + lage[3] for lage in neu.values())
    return _mit_rand(live, links, oben, rechts - links, unten - oben)


def _mit_rand(live: session.Session, x: int, y: int, breite: int,
              hoehe: int) -> tuple[int, int, int, int]:
    """Rand drumherum, aber nie ueber den Schirm hinaus.

    Und beide Kantenlaengen GERADE: ein WebP mit ungerader Kante laesst
    sich zwar schreiben, aber jeder Skalierer rechnet dann mit einem
    halben Bildpunkt.
    """
    links = max(x - RAND, 0)
    oben = max(y - RAND, 0)
    rechts = min(x + breite + RAND, live.width)
    unten = min(y + hoehe + RAND, live.height)
    return (links, oben, (rechts - links) // 2 * 2, (unten - oben) // 2 * 2)


def home_ohne_platzhalter(build: Path, eintraege: list[str]) -> list[str]:
    """Auf das Home NUR die Anwendungen legen, die es hier wirklich gibt.

    WARUM DAS KEINE SCHOENUNG IST, SONDERN DAS ENTFERNEN EINER KULISSE
        ZepOS liefert fuenfzehn Anwendungen auf dem Home aus
        (src/apps.shipped, gelesen aus dem depends-Feld von
        packaging/zepos-apps/PKGBUILD). Auf DIESER Entwicklermaschine
        sind acht davon nicht installiert, und das Home zeichnet fuer
        jede fehlende ein Platzhaltersymbol.

        GEMESSEN am 24.08.2026 am ersten Lauf: acht winzige graue
        Kaesten zwischen sieben echten Symbolen. Das ist ein Zustand
        dieser Maschine und keiner, den irgendein Nutzer je sieht - auf
        einer Installation ist jede der fuenfzehn da.

        Die 27 Standbilder dieses Schaukastens loesen es seit dem
        24.08.2026 genauso, und aus demselben Grund (docs/bilder/
        README.md, "home.icons names what this machine actually has").
        Geschrieben wird es als GEWOEHNLICHE Nutzereinstellung, in die
        Datei, die src/paths.user_root() nennt - nicht in eine Vorlage
        und nicht in den erzeugten Quelltext.
    """
    namen: list[str] = []
    for zeile in eintraege:
        name = zeile.split(":", 1)[0].strip()
        if name and name not in namen:
            namen.append(name)
    # schema_version, UND ZWAR AUS DEM MODUL UND NICHT ABGESCHRIEBEN
    #     GEMESSEN am 24.08.2026: ohne die Zeile antwortet
    #     `zepos-settings-gui --json get` mit
    #         "unsupported schema_version None, expected 1"
    #     und meldet ok:false. Settings() in ags-settings.template baut
    #     sein Fenster daraufhin gar nicht, `ags request settings` sagt
    #     "widget not found", und diese Datei hatte gerade das Fenster
    #     kaputtgemacht, das sie filmen wollte.
    sys.path.insert(0, str(SRC))
    try:
        import settings as zepos_settings
        schema = zepos_settings.SCHEMA_VERSION
        schluessel = (zepos_settings.HOME, zepos_settings.HOME_ICONS,
                      zepos_settings.HOME_NAME)
    finally:
        sys.path.remove(str(SRC))

    ziel = build / "zepos" / "user-settings.json"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    bestand = {}
    if ziel.is_file():
        bestand = json.loads(ziel.read_text(encoding="utf-8"))
    bestand["schema_version"] = schema
    heim, symbole, benannt = schluessel
    bestand.setdefault(heim, {})[symbole] = [{benannt: n} for n in namen]
    ziel.write_text(json.dumps(bestand, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return namen


def warte_auf_ruhe(live: session.Session, grundflaechen: set[str],
                   frist: float = 25.0) -> None:
    """Warten, bis auf dem Schirm wieder GENAU der Ruhezustand liegt.

    WARUM DAS EINE EIGENE FUNKTION IST UND NICHT EIN sleep
        GEMESSEN am 24.08.2026, und es war der erste ernste Fehler
        dieses Laufs: `szene_ueberblendung` machte ein Fenster auf und
        NICHT wieder zu. Acht Szenen hintereinander liessen damit acht
        Fenster stehen, und auf der Aufnahme des Anwendungsstarters -
        der neunten - stand das Sitzungsfenster der achten noch im Bild.
        Jede Aufnahme ab der zweiten zeigte die Trueemmer ihrer
        Vorgaenger.

        Eine feste Wartezeit hilft dagegen nicht: sie behauptet, dass
        aufgeraeumt ist. Hier wird der Compositor gefragt, bis er
        dasselbe sagt wie vor der Szene.
    """
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        if set(live.layers()) == grundflaechen:
            time.sleep(0.4)
            if set(live.layers()) == grundflaechen:
                return
        time.sleep(0.3)
    uebrig = sorted(set(live.layers()) - grundflaechen)
    raise AssertionError(
        f"nach {frist:.0f} s liegt immer noch {uebrig} auf dem Schirm - "
        "die naechste Aufnahme zeigte die Truemmer der vorigen")


def szene_ueberblendung(live: session.Session, klappe: Klappe, anfrage: str,
                        ruhe: float, halten: float) -> None:
    """Ruhe, aufmachen, halten - und das war die ganze Bewegung.

    Die Ruhe am Anfang ist kurz mit Absicht: sie soll zeigen, WO das
    Fenster herkommt, und nicht die Aufnahme fuellen. Ein WebP zahlt
    fuer ein unveraendertes Bild fast nichts, aber der Betrachter zahlt
    mit Wartezeit.
    """
    klappe.marke("Ruhezustand")
    klappe.laufen(ruhe)
    klappe.marke(f"ags request {anfrage}")
    live.request(anfrage)
    klappe.marke("aufgegangen, wird gehalten")
    klappe.laufen(halten)


# Der Text der Benachrichtigung. EINE Stelle, und das ist gemessen:
# die Vorprobe, mit der der Ausschnitt bestimmt wird, muss WOERTLICH
# dieselbe Benachrichtigung schicken wie die Aufnahme. GEMESSEN am
# 24.08.2026 mit einer kurzen Probe ("Probe"/"Probe"): die gemessene
# Flaeche war schmaler als die echte, und auf der Aufnahme war der
# linke Rand des Textes abgeschnitten.
BENACHRICHTIGUNG = ("ZepOS", "Aktualisierung bereit",
                    "12 Pakete koennen aktualisiert werden.")


def szene_benachrichtigung(live: session.Session, klappe: Klappe) -> None:
    """Eine Benachrichtigung, die hereinkommt.

    Sie wird mit `notify-send` geschickt, also ueber denselben
    Sitzungsbus und dieselbe Schnittstelle
    (org.freedesktop.Notifications), die jedes Programm benutzt. Der
    Text ist erfunden und nennt nichts von dieser Maschine.
    """
    klappe.marke("Ruhezustand")
    klappe.laufen(0.30)
    klappe.marke("notify-send")
    anwendung, kopf, rumpf = BENACHRICHTIGUNG
    subprocess.run(["notify-send", "-a", anwendung, kopf, rumpf],
                   env=live.environment(), capture_output=True, timeout=30)
    klappe.marke("kommt herein")
    klappe.laufen(1.90)


def szene_starter(live: session.Session, klappe: Klappe, starter: Path,
                  build: Path, daten: Path):
    """Der Anwendungsstarter, der aufgeht.

    Derselbe Befehl, den die Compositor-Haelfte des Plugins auf
    SUPER+SPACE ausfuehrt, und in demselben eigenen /tmp wie in film.py
    (film.AUSSERHALB_TMP erklaert, warum das keine Vorliebe ist).
    """
    klappe.marke("Ruhezustand")
    klappe.laufen(0.40)
    klappe.marke("hyprlaunch-ui --toggle, der Befehl hinter SUPER+SPACE")
    prozess = live.spawn(film._starter_kommando(starter, "--toggle"),
                         log=Path(live.runtime) / "starter.log",
                         XDG_CONFIG_HOME=str(build),
                         XDG_DATA_DIRS=str(daten))
    klappe.laufen(2.20)
    return prozess


def szene_tippen(live: session.Session, klappe: Klappe) -> None:
    """In den offenen Starter tippen - echte Tasten, Zeichen fuer Zeichen."""
    klappe.marke('getippt: "datei"')
    import threading
    faden = threading.Thread(
        target=lambda: subprocess.run(
            ["wtype", "-d", "110", "datei"], env=live.environment(),
            capture_output=True, timeout=60),
        daemon=True)
    faden.start()
    klappe.laufen(1.60)
    faden.join(timeout=10)
    klappe.laufen(0.50)


def required_tools() -> list[str]:
    fehlend = list(film.required_tools())
    for werkzeug in ("notify-send", "magick"):
        if shutil.which(werkzeug) is None:
            fehlend.append(werkzeug)
    return fehlend


def pruefe_persoenliches(wurzel: Path) -> list[str]:
    """Jedes Einzelbild und jedes Erzeugnis auf Verraeterisches absuchen.

    BYTEWEISE UND UEBER ALLE BILDER, NICHT UEBER DAS ERSTE
        Beim ersten Anlauf des Vorgaengers ist genau diese Falle
        zugeschnappt: das erste Bild war sauber, und in Sekunde fuenf
        stand ein Programm auf dem Schirm, das nur auf DIESER Maschine
        installiert ist. Ein Blick auf das erste Bild haette das nie
        gefunden.

    Was gesucht wird, ist absichtlich weit gefasst - der Kontoname, der
    Rechnername, jeder Pfad unter /home, der Bauplatz dieses Laufs und
    die Namen der Programme, die ZepOS NICHT ausliefert.
    """
    verboten = [os.environ.get("USER", "lmarzoll"), "lmarzoll", "LMARZOLL",
                "/home/", "home/l", "dev/shm", "zepschau", "zepfilm",
                "Thunar", "thunar", "hyprlaunch-ui", "NetworkManager",
                "T14", "AMILO", ".ssh", "id_rsa", "@axro"]
    rechner = subprocess.run(["hostname"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    if rechner:
        verboten.append(rechner)
        verboten.append(rechner.split("-")[0])
    verboten = sorted(set(w for w in verboten if w))

    dateien = sorted(p for p in wurzel.rglob("*")
                     if p.is_file() and p.suffix in (".ppm", ".webp"))
    inhalte = {pfad: pfad.read_bytes() for pfad in dateien}
    gesamt = sum(len(d) for d in inhalte.values())

    treffer: list[str] = []
    for pfad, rohdaten in inhalte.items():
        for wort in verboten:
            stelle = rohdaten.find(wort.encode())
            if stelle < 0:
                continue
            # WO der Fund steht, entscheidet, ob er einer ist.
            #
            # Ein PPM hat einen ASCII-Kopf von rund zwanzig Byte
            # ("P6\n1920 1080\n255\n") und danach NUR Bildpunkte, drei
            # Byte je Punkt. Was hinter dem Kopf steht, ist keine
            # Zeichenkette, sondern eine Farbe - und in sechs Millionen
            # Byte kommt jede kurze Buchstabenfolge irgendwann als
            # Farbwert vor.
            #
            # GEMESSEN am 24.08.2026 an genau diesem Lauf: "T14" (die
            # ersten drei Zeichen des Rechnernamens) stand bei Byte
            # 3 700 081 eines Rohbildes, der Kopf endete bei Byte 16.
            # Der ganze Rechnername stand NIRGENDS, "lmarzoll" auch
            # nicht, "/home/" auch nicht. Der Kontrollversuch unten
            # sagt, was davon zu halten ist.
            kopfende = rohdaten.find(b"255\n") + 4 if pfad.suffix == ".ppm" else 64
            wo = "IM KOPF" if stelle < kopfende else "in den Bildpunkten"
            treffer.append(f"{wort!r} in {pfad.name} bei Byte {stelle} ({wo})")

    # DER KONTROLLVERSUCH, UND OHNE IHN IST DIE OBIGE LISTE WERTLOS
    #     Zwanzig DREI Zeichen lange Folgen, die mit dieser Maschine
    #     nichts zu tun haben. Treffen sie aehnlich oft wie die kurzen
    #     verbotenen Begriffe, dann misst diese Suche in Rohbildern
    #     Zufall und keinen Personenbezug - und das muss dastehen,
    #     statt dass jemand es spaeter raet.
    zufall = random.Random(20260824)
    zeichen = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    kontrollen = ["".join(zufall.choice(zeichen) for _ in range(3))
                  for _ in range(20)]
    kontrolltreffer = sum(
        1 for wort in kontrollen for rohdaten in inhalte.values()
        if wort.encode() in rohdaten)

    return ([f"{len(dateien)} Dateien byteweise abgesucht "
             f"({gesamt} Byte), {len(verboten)} Suchbegriffe",
             f"Kontrollversuch: 20 zufaellige Dreierfolgen ohne Bezug zu "
             f"dieser Maschine treffen {kontrolltreffer} mal"]
            + treffer)


def sichere_bilder(klappe: Klappe, ziel: Path) -> list[str]:
    """Jedes VERSCHIEDENE Einzelbild als PNG aufheben, mit seiner Zeit im Namen.

    Ein Rohbild ist 6,2 MB und eine Aufnahme hat siebzig davon; die
    meisten sind byte-gleich zu einem Vorgaenger, weil zwischen zwei
    Bildern einer Ruhephase nichts passiert. Aufgehoben wird deshalb der
    Satz der VERSCHIEDENEN - er ist genau das, was ein Mensch ansehen
    muss, wenn er die Aufnahme auf Personenbezug prueft, und alles
    andere waere dieselbe Ansicht noch einmal.

    Die byteweise Suche laeuft davor und ueber ALLE Rohbilder.
    """
    ziel.mkdir(parents=True, exist_ok=True)
    gesehen: set[str] = set()
    behalten = 0
    for zeit, pfad in klappe.bilder:
        pruefsumme = hashlib.sha256(pfad.read_bytes()).hexdigest()
        if pruefsumme in gesehen:
            continue
        gesehen.add(pruefsumme)
        ergebnis = subprocess.run(
            ["magick", str(pfad), "-strip",
             str(ziel / f"{zeit:07.3f}s.png".replace(".", "_", 1))],
            capture_output=True, text=True, timeout=120)
        assert ergebnis.returncode == 0, ergebnis.stderr
        behalten += 1
    return [f"{behalten} verschiedene von {len(klappe.bilder)} Bildern "
            f"in {ziel}"]


def _bilderbericht(name: str, klappe: Klappe, ziel: Path) -> list[str]:
    werte = klappe.messwerte()
    verschieden = len({hashlib.sha256(pfad.read_bytes()).hexdigest()
                       for _, pfad in klappe.bilder})
    groesse = ziel.stat().st_size if ziel.is_file() else 0
    return [
        f"  {name}",
        f"      Bilder                 {werte['bilder']} "
        f"({verschieden} davon verschieden)",
        f"      Laenge                 {werte['laenge_s']:.2f} s",
        f"      Bildrate, erreicht     {werte['bilder_je_sekunde']:.2f} Bilder/s",
        f"      Abstand min/mit/max    {werte['abstand_ms_min']:.0f} / "
        f"{werte['abstand_ms_mittel']:.0f} / {werte['abstand_ms_max']:.0f} ms",
        f"      Verlorene Bilder       {werte['verlorene_bilder']}",
        f"      Groesse                {groesse} Byte "
        f"= {groesse/1024:.0f} kB",
        f"      sha256                 "
        + (hashlib.sha256(ziel.read_bytes()).hexdigest() if groesse else "-"),
    ]



def menue_lauf(out: Path, bilderwurzel: Path, takt_ms: int,
               guete: int, nur_bilder: bool) -> tuple[list, list[str]]:
    """Das Rechtsklick-Menue des Fusses - in einer EIGENEN Sitzung.

    DAS IST DIE ANTWORT AUF DAS GROESSTE HINDERNIS DIESES AUFTRAGS
        Es gibt auf dieser Maschine kein Werkzeug, das eine ZEIGERTASTE
        in eine Wayland-Sitzung schiebt: ydotool, wlrctl und dotool
        fehlen alle, wtype kann nur Tasten, und `hyprctl dispatch`
        bewegt den Zeiger, kann ihn aber nicht druecken. Zwei Vorgaenger
        sind daran stehengeblieben.

        tests/render/dock_menue_child.tsx hat die Antwort seit dem
        20.08.2026 und wird hier UNVERAENDERT benutzt: es baut den
        ERZEUGTEN Fuss (widget/Dock.tsx aus der Vorlage) auf einer
        echten Layer-Flaeche in einem echten Compositor, mit beiden
        erzeugten Stylesheets, und feuert die Geste dort, wo GTK sie
        auch entgegennaehme - am "pressed"-Signal der Gtk.GestureClick,
        die die Vorlage an den Knopf haengt, gefunden ueber
        observe_controllers(). Was danach passiert, passiert wirklich.

        Kein Zeiger im Bild, aber dieselbe sichtbare Folge: ein Menue,
        das aufgeht.

    WARUM EINE EIGENE SITZUNG UND NICHT DIE GROSSE
        Das Kind BAUT den Fuss selbst. Liefe daneben die ganze Schale,
        laegen zwei Fuesse uebereinander. Genau deshalb misst
        tests/render/test_menue.py seit jeher in einem Lauf mit genau
        einem Widget, und dieselbe Aufteilung gilt hier.
    """
    import tempfile as _tempfile
    protokoll: list[str] = []
    bau = Path(_tempfile.mkdtemp(prefix="zepschau-menue-"))
    ags = session.render_configuration(bau)
    film.nachtrag_ags_vorlagen(ags)
    quelle = Path(__file__).resolve().parent / "dock_menue_child.tsx"
    ziel = ags / "dock_menue_child.tsx"
    ziel.write_text(quelle.read_text(encoding="utf-8"), encoding="utf-8")
    ergebnis = subprocess.run(
        ["ags", "bundle", str(ziel), str(bau / "zepos-dock-menue.js"),
         "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=600)
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat das Menue-Kind nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)

    def frage(live: session.Session, wunsch: str) -> str:
        antwort = subprocess.run(
            ["ags", "request", wunsch, "-i", "zepos-dock-menue"],
            env=live.environment(), capture_output=True, text=True,
            timeout=30)
        return (antwort.stdout + antwort.stderr).strip()

    aufnahmen: list = []
    live = session.Session(1920, 1080)
    try:
        live.start()
        live.start_bus()
        session.workspaces_file(bau, live.output)
        for name in [m["name"] for m in live.hyprctl_json("monitors") or []]:
            if name != live.output:
                live.hyprctl("keyword", "monitor", f"{name}, disable")
        time.sleep(1.5)
        for schluessel, wert in film._general_block():
            live.hyprctl("keyword", f"general:{schluessel}", wert)
        live.hyprctl("keyword", "cursor:invisible", "true")
        live.wallpaper()
        live.move_cursor(live.width // 2, live.height // 2)
        live.hyprctl("dispatch", "focusmonitor", live.output)
        time.sleep(2.0)
        live.spawn([str(bau / "zepos-dock-menue.js")],
                   log=bau / "kind.log", XDG_CONFIG_HOME=str(bau),
                   ZEPOS_AUSGANG=live.output)
        time.sleep(film.SETTLE)
        flaechen = live.layers()
        assert "zepos-dock" in flaechen, (
            "der Fuss liegt nicht auf dem Schirm:\n"
            + (bau / "kind.log").read_text(errors="replace"))

        # WO das Menue hinkommt, wird GEMESSEN und nicht geraten.
        #     Ein Popover ist ein xdg_popup und keine Layer-Flaeche;
        #     `hyprctl layers` kennt ihn nicht, und der Kasten des
        #     Fusses waechst durch ihn nicht (das misst
        #     test_der_fuss_wird_von_seinem_menue_nicht_groesser).
        #     Also wird ein Bild vorher und eines nachher verglichen
        #     und das kleinste Rechteck genommen, in dem sie sich
        #     unterscheiden - measure.changed_bounds, dieselbe
        #     Funktion, mit der shoot.py seine Raender nachzaehlt.
        vorher_bild = live.shoot(bau / "menue-zu.png")
        geklickt = frage(live, "rechtsklick")
        protokoll.append(f"    dock-menue: rechtsklick -> {geklickt!r}")
        time.sleep(2.0)
        protokoll.append(f"    dock-menue: offen -> {frage(live, 'offen')!r}")
        protokoll.append("    dock-menue: Eintraege -> "
                         f"{frage(live, 'eintraege')!r}")
        nachher_bild = live.shoot(bau / "menue-auf.png")
        kasten = measure.changed_bounds(
            measure.read_png(vorher_bild), measure.read_png(nachher_bild),
            (0, 0, live.width, live.height))
        assert kasten, ("zwischen zu und auf hat sich kein Bildpunkt "
                        "geaendert - das Menue ist nicht aufgegangen")
        protokoll.append(f"    dock-menue: veraendertes Rechteck {kasten}")
        lage = _mit_rand(live, *kasten)
        protokoll.append(f"    dock-menue: Ausschnitt {lage}")
        # ZUGEMACHT WIRD MIT ESCAPE UND NICHT MIT EINEM ZWEITEN KLICK
        #     GEMESSEN am 24.08.2026: "rechtsklick" OEFFNET, es
        #     schaltet nicht um. Ein zweiter Aufruf liess das Menue
        #     offen und schrieb nur `Tried to map a grabbing popup with
        #     a non-top most parent` ins Protokoll. Die Aufnahme zeigte
        #     daraufhin 2,3 Sekunden lang ein bereits offenes Menue -
        #     EIN verschiedenes Bild auf 58.
        #
        #     Escape ist der Weg, den auch ein Mensch nimmt, und
        #     tests/render/test_menue.py misst seit dem 20.08.2026
        #     genau damit, dass das Menue zugeht. Von aussen mit wtype,
        #     also ueber den Compositor - nicht als Signal an das Kind.
        subprocess.run(["wtype", "-k", "Escape"], env=live.environment(),
                       capture_output=True, timeout=20)
        time.sleep(1.5)
        zustand = frage(live, "offen")
        assert zustand == "keins", (
            f"das Menue ist nach Escape nicht zu ({zustand!r}) - die "
            "Aufnahme faenge mit einem offenen Menue an")

        def menue_szene(k: Klappe) -> None:
            """Der ganze Handgriff und nicht nur seine Haelfte.

            WARUM AUF UND WIEDER ZU, UND NICHT NUR AUF
                Ein Gtk.Popover ist ein Unterfenster und keine Flaeche
                des Compositors; er hat keine Ueberblendung, und das
                Stylesheet gibt ihm auch keine. GEMESSEN am 24.08.2026:
                zwischen "zu" und "auf" liegt KEIN Zwischenbild - zwei
                verschiedene Bilder auf 58.

                Eine Schleife aus zwei Zustaenden blinkt. Aufgenommen
                wird deshalb der ganze Vorgang, den ein Mensch macht:
                Rechtsklick, ansehen, Escape. Das ist vier Zustaende
                lang, laeuft rund, und es ist nichts hinzuerfunden -
                jeder Schritt ist einer, den der Nutzer auch tut.
            """
            k.marke("Ruhezustand: der Fuss, nichts offen")
            k.laufen(0.50)
            k.marke("Rechtsklick auf die erste Anheftung - die Geste der "
                    "Vorlage, ueber observe_controllers()")
            frage(live, "rechtsklick")
            k.laufen(1.60)
            k.marke("Escape - von aussen, ueber den Compositor")
            subprocess.run(["wtype", "-k", "Escape"], env=live.environment(),
                           capture_output=True, timeout=20)
            k.laufen(1.20)

        print("  -> dock-menue")
        with Klappe(live, bilderwurzel / "dock-menue", takt_ms, lage) as k:
            menue_szene(k)
        aufnahmen.append(("dock-menue", k, out / "dock-menue.webp"))
        (out / "dock-menue-kind.log").write_text(
            (bau / "kind.log").read_text(errors="replace"), encoding="utf-8")
    finally:
        live.stop()
    return aufnahmen, protokoll


def main() -> int:
    zerleger = argparse.ArgumentParser(description=__doc__)
    zerleger.add_argument("--out", type=Path, default=ROOT / "out" / "schaukasten")
    zerleger.add_argument("--takt", type=int, default=TAKT_MS)
    zerleger.add_argument("--guete", type=int, default=WEBP_GUETE)
    zerleger.add_argument("--nur", type=str, default="")
    zerleger.add_argument("--nur-bilder", action="store_true")
    argumente = zerleger.parse_args()
    gewuenscht = {n.strip() for n in argumente.nur.split(",") if n.strip()}

    fehlend = required_tools()
    if fehlend:
        print("Diese Programme fehlen und ohne sie gibt es keine Aufnahme: "
              + ", ".join(fehlend), file=sys.stderr)
        return 1

    # Siehe film.AUSSERHALB_TMP: alles, was der Starter sehen muss, liegt
    # ausserhalb von /tmp, damit kein Aufruf an den Socket des Nutzers geht.
    import tempfile
    tempfile.tempdir = str(film.AUSSERHALB_TMP)

    out = argumente.out
    out.mkdir(parents=True, exist_ok=True)
    # DIE ROHBILDER LIEGEN IM ARBEITSSPEICHER, UND DAS IST GERECHNET
    #     Ein PPM von 1920x1080 ist 6,2 MB, weil es nichts komprimiert -
    #     genau deshalb ist es schnell genug fuer 25 Bilder/s. Ein voller
    #     Lauf zieht ueber tausend davon; das sind rund 6 GB, die auf
    #     eine Platte zu schreiben den Takt selbst wieder kaputtmachte.
    #     /dev/shm hat hier 32 GB.
    #
    #     Was hinterher im Baum bleibt, sind die VERSCHIEDENEN Bilder als
    #     PNG (out/.../bilder/<szene>/) - das ist der Satz, den eine
    #     Pruefung auf Personenbezug ansehen muss, und er ist um eine
    #     Groessenordnung kleiner. Die byteweise Suche laeuft VORHER und
    #     ueber ALLE Rohbilder, nicht nur ueber die verschiedenen.
    bilderwurzel = Path(tempfile.mkdtemp(prefix="zepschau-bilder-"))
    build = Path(tempfile.mkdtemp(prefix="zepschau-bau-"))
    bericht: list[str] = film.herkunft()
    bericht.append(f"Bauplatz: {build}")
    print(f"Bauplatz: {build}")

    # Der Starter wird nur gebaut, wenn eine Szene ihn braucht - cmake und
    # ninja kosten Minuten, und fuer die acht Aufklappfenster ist er
    # ueberfluessig.
    starter: Path | None = None
    if not gewuenscht or gewuenscht & {"starter", "dateien", "dock-minimiert"}:
        starter = film.starter_bauen(build / "starter")
        bericht.append(f"Starter: {starter} (aus "
                       f"{film.STARTER_TARBALL.name} + "
                       f"{film.STARTER_PATCH.name})")

    ags = session.render_configuration(build)
    nachgetragen = film.nachtrag_ags_vorlagen(ags)
    if nachgetragen:
        bericht.append("Vorlagen, die RENDERED noch nicht kennt:")
        bericht.extend(f"    {z}" for z in nachgetragen)
    session.bundle(ags, build)

    prozessor = session._processor()
    for vorlage, ausgabe in {**film.NEBENVORLAGEN, **ZUSATZVORLAGEN}.items():
        ziel = build / ausgabe
        ziel.parent.mkdir(parents=True, exist_ok=True)
        prozessor.apply_template(SRC / vorlage, ziel)
    hyprtext = (build / "hypr" / "hyprland.conf").read_text(encoding="utf-8")

    daten, eintraege = film.anwendungsverzeichnis(build)
    bericht.append(f"Anwendungseintraege im Starter ({len(eintraege)}):")
    bericht.extend(f"    {z}" for z in eintraege)
    aufs_home = home_ohne_platzhalter(build, eintraege)
    bericht.append(f"home.icons ({len(aufs_home)}): {aufs_home}")

    live = session.Session(1920, 1080)
    aufnahmen: list[tuple[str, Klappe, Path]] = []
    try:
        live.start()
        live.start_bus()
        bericht.append("Umgebung fuer den eigenen Bus:")
        bericht.extend(f"    {p}" for p in film.bus_umgebung(
            live, XDG_CONFIG_HOME=str(build), XDG_DATA_DIRS=str(daten),
            HYPRLAND_INSTANCE_SIGNATURE=live.signature() or "")
            if not p.startswith("PATH="))
        session.workspaces_file(build, live.output)
        bericht.append(f"Ordner im Wegwerf-Home: {film.benutzerordner(live.home)}")
        bericht.extend(f"    {z}" for z in film.nur_ein_schirm(live))
        live.wallpaper()

        for schluessel, wert in film._general_block():
            live.hyprctl("keyword", f"general:{schluessel}", wert)
        bericht.append("Animationen, aus der erzeugten hyprland.conf:")
        bericht.extend(f"    {z}" for z in bewegung_anschalten(live, hyprtext))

        live.move_cursor(live.width // 2, live.height // 2)
        live.hyprctl("dispatch", "focusmonitor", live.output)
        # Der Zeiger gehoert auf kein Schaukastenbild - er ist ein
        # Merkmal des Messstands. Dieselbe Zeile benutzt
        # tests/render/test_schale_stil.py.
        live.hyprctl("keyword", "cursor:invisible", "true")

        time.sleep(2.0)
        # DIE SCHALE WIRD HIER VON HAND GESTARTET UND NICHT MIT
        # Session.shell(), UND DER GRUND IST EINE EINZIGE VARIABLE
        #     Settings() in ags-settings.template ruft
        #     `zepos-settings-gui --json get` und BAUT SEIN FENSTER GAR
        #     NICHT, wenn der Befehl nicht antwortet - `widgets.settings`
        #     bleibt null, und `ags request settings` sagt dann "widget
        #     not found". GEMESSEN am 24.08.2026, genau so ist dieser
        #     Lauf zuerst abgebrochen.
        #
        #     Das Paket zepos-settings-gui ist auf einer
        #     Entwicklermaschine nicht installiert; der Befehl liegt in
        #     settings/bin/ DIESES Checkouts und findet seine Module von
        #     dort aus selbst. Er kommt deshalb vorn auf den Suchpfad.
        #     Er SCHREIBT user-settings.json, und die liegt nach
        #     src/paths.user_root() unter $XDG_CONFIG_HOME/zepos - also
        #     im Bauplatz dieses Laufs und nicht bei irgendwem.
        #
        #     Session.shell() bleibt unangetastet: eine bestehende
        #     Messsitzung soll davon nichts merken.
        signatur = live.signature()
        assert signatur, "der verschachtelte Compositor hat keine Kennung"
        live.spawn([str(build / "zepos-shell.js")],
                   XDG_CONFIG_HOME=str(build),
                   HYPRLAND_INSTANCE_SIGNATURE=signatur,
                   PATH=f"{ROOT / 'settings' / 'bin'}:"
                        + os.environ.get("PATH", "/usr/bin"))
        time.sleep(film.SETTLE)
        flaechen = live.layers()
        assert "zepos-bar" in flaechen and "zepos-dock" in flaechen, (
            "die Oberflaeche steht nicht:\n" + live.read_shell_log())
        grundflaechen = set(flaechen)
        bericht.append(f"Flaechen im Ruhezustand: {sorted(grundflaechen)}")

        def nimm(name: str, ausschnitt, dauer_fn) -> None:
            if gewuenscht and name not in gewuenscht:
                return
            print(f"  -> {name}")
            with Klappe(live, bilderwurzel / name, argumente.takt,
                        ausschnitt) as klappe:
                dauer_fn(klappe)
            aufnahmen.append((name, klappe, out / f"{name}.webp"))

        # --- Die acht Aufklappfenster ---------------------------------
        for name, anfrage, ruhe, halten in UEBERBLENDUNGEN:
            if gewuenscht and name not in gewuenscht:
                continue
            warte_auf_ruhe(live, grundflaechen)
            lage = flaeche_messen(live, anfrage)
            assert lage, (f"{anfrage} hat keine neue Flaeche geoeffnet - "
                          f"Antwort: {live.request(anfrage)!r}")
            bericht.append(f"    {name}: Ausschnitt {lage}")
            warte_auf_ruhe(live, grundflaechen)
            nimm(name, lage,
                 lambda k, a=anfrage, r=ruhe, h=halten:
                 szene_ueberblendung(live, k, a, r, h))
            # Wieder zu. Ohne diese Zeile stuende dieses Fenster auf
            # jeder folgenden Aufnahme - siehe warte_auf_ruhe.
            live.request(anfrage)
            warte_auf_ruhe(live, grundflaechen)

        # --- Eine Benachrichtigung, die hereinkommt --------------------
        if not gewuenscht or "benachrichtigung" in gewuenscht:
            warte_auf_ruhe(live, grundflaechen)
            vorher = set(live.layers())
            subprocess.run(["notify-send", "-a", BENACHRICHTIGUNG[0],
                            BENACHRICHTIGUNG[1], BENACHRICHTIGUNG[2]],
                           env=live.environment(), capture_output=True,
                           timeout=30)
            time.sleep(2.0)
            neu = {n: l for n, l in live.layers().items() if n not in vorher}
            assert neu, "es kam keine Benachrichtigung an"
            lage = _mit_rand(live, min(l[0] for l in neu.values()),
                             min(l[1] for l in neu.values()),
                             max(l[2] for l in neu.values()),
                             max(l[3] for l in neu.values()))
            bericht.append(f"    benachrichtigung: Ausschnitt {lage}")
            # Die PROBE muss weg sein, bevor die Aufnahme laeuft - sonst
            # zeigt das erste Bild schon eine Benachrichtigung, und die
            # Aufnahme zeigt nicht, wie eine hereinkommt, sondern wie
            # eine zweite neben einer ersten steht. Gewartet wird, bis
            # der Compositor die Flaeche nicht mehr fuehrt, und nicht
            # eine geratene Zahl von Sekunden.
            frist = time.monotonic() + 40.0
            while set(live.layers()) & set(neu) and time.monotonic() < frist:
                time.sleep(0.5)
            assert not set(live.layers()) & set(neu), (
                "die Probe-Benachrichtigung ist nach 40 s noch da")
            time.sleep(1.0)
            nimm("benachrichtigung", lage,
                 lambda k: szene_benachrichtigung(live, k))
            frist = time.monotonic() + 40.0
            while set(live.layers()) & set(neu) and time.monotonic() < frist:
                time.sleep(0.5)

        # --- Der Fuss, der weggeht und wiederkommt --------------------
        warte_auf_ruhe(live, grundflaechen)
        fuss = live.layers().get("zepos-dock")
        assert fuss, "kein Fuss auf dem Schirm"
        fussfeld = _mit_rand(live, fuss[0] - 60, fuss[1] - 20,
                             fuss[2] + 120, fuss[3] + 20)
        bericht.append(f"    dock: Ausschnitt {fussfeld}")

        def dock_szene(k: Klappe) -> None:
            k.marke("Ruhezustand")
            k.laufen(0.40)
            k.marke("ags request dock - der Fuss geht weg (SUPER+B)")
            live.request("dock")
            k.laufen(1.10)
            k.marke("ags request dock - und wieder her")
            live.request("dock")
            k.laufen(1.40)

        nimm("dock", fussfeld, dock_szene)

        # --- Die Einstellungs-App, ein gewoehnliches Fenster -----------
        #
        # Kein Layer-Shell-Streifen, sondern ein Fenster wie jedes
        # andere - und damit die einzige Aufnahme, in der man Hyprlands
        # FENSTER-Animation sieht (`animation = windows, 1, 6, zepos`
        # aus der erzeugten hyprland.conf). Gestartet wie in
        # tests/render/settings_shot.py, mit demselben Befehl und
        # derselben Seite, die auch das Standbild zeigt.
        def fenster_da() -> bool:
            """Liegt ein gewoehnliches Fenster auf dem Schirm?

            `mapped` allein reicht nicht: ein Fenster ist eine Zeit lang
            angemeldet und einen Bildpunkt breit. Dieselbe Bedingung
            benutzt wait_for_window() in tests/render/settings_shot.py.
            """
            return any(f.get("mapped") and f.get("size", [0, 0])[0] > 1
                       for f in (live.hyprctl_json("clients") or []))

        if not gewuenscht or "einstellungen-app" in gewuenscht:
            warte_auf_ruhe(live, grundflaechen)
            app_prozess = [None]

            def app_szene(k: Klappe) -> None:
                k.marke("Ruhezustand")
                k.laufen(0.40)
                k.marke("zepos-settings-gui --page farben")
                # OHNE sys.executable, UND DAS IST EIN BEFUND
                #     tests/render/settings_shot.py startet denselben
                #     Befehl als `[sys.executable, LAUNCHER, ...]`. Ein
                #     Lauf aus dem venv dieses Projekts gibt damit das
                #     venv-Python, und GEMESSEN am 24.08.2026 hat DAS
                #     kein PyGObject:
                #         ModuleNotFoundError: No module named 'gi'
                #     /usr/bin/python3 hat es. Der Befehl traegt
                #     `#!/usr/bin/env python3` und findet es damit
                #     selbst - genau so ruft ihn die Schale auch auf
                #     (ags-settings.template, BEFEHL). Der Mangel in
                #     settings_shot.py ist gemeldet und nicht angefasst:
                #     eine bestehende Messsitzung aendert dieser Lauf
                #     nicht.
                #     XDG_CONFIG_HOME wie bei der Schale, und das ist
                #     der zweite Teil desselben Befundes: ohne ihn
                #     findet die App weder gtk-4.0/settings.ini noch
                #     kdeglobals und zeichnet hell.
                app_prozess[0] = live.spawn(
                    [str(ROOT / "settings" / "bin" / "zepos-settings-gui"),
                     "--page", "farben"],
                    log=Path(live.runtime) / "settings-app.log",
                    XDG_CONFIG_HOME=str(build))
                # Bis das Fenster steht, hoechstens 30 s, und danach
                # noch 1,6 s - siehe Klappe.laufen_bis.
                if k.laufen_bis(fenster_da, 30.0, 1.6):
                    k.marke("das Fenster steht")

            nimm("einstellungen-app", None, app_szene)
            protokoll = Path(live.runtime) / "settings-app.log"
            if protokoll.is_file():
                (out / "settings-app.log").write_text(
                    protokoll.read_text(errors="replace"), encoding="utf-8")
            offen = [f for f in (live.hyprctl_json("clients") or [])
                     if f.get("mapped")]
            bericht.append("    einstellungen-app: Fenster "
                           + str(offen and offen[0]["class"]))
            assert offen, ("die Einstellungs-App hat kein Fenster geoeffnet - "
                           "siehe settings-app.log")
            if app_prozess[0] is not None:
                app_prozess[0].terminate()
                try:
                    app_prozess[0].wait(timeout=10)
                except subprocess.TimeoutExpired:        # pragma: no cover
                    app_prozess[0].kill()
            time.sleep(1.5)

        # --- Der Starter, der aufgeht ---------------------------------
        prozess = None
        warte_auf_ruhe(live, grundflaechen)
        if starter is not None:
            behaelter: list = []
            nimm("starter", None,
                 lambda k: behaelter.append(
                     szene_starter(live, k, starter, build, daten)))
            prozess = behaelter[0] if behaelter else None
            if prozess is not None:
                assert "hyprlaunch" in live.layers(), (
                    "der Starter liegt nicht auf dem abgebildeten Schirm")

        # --- Und was daraus wird: der Dateiverwalter -------------------
        def dateien_szene(k: Klappe) -> None:
            szene_tippen(live, k)
            k.marke("Eingabetaste - der Dateiverwalter startet")
            subprocess.run(["wtype", "-k", "Return"], env=live.environment(),
                           capture_output=True, timeout=30)
            if k.laufen_bis(fenster_da, 20.0, 2.20):
                k.marke("das Fenster steht")

        if prozess is not None:
            nimm("dateien", None, dateien_szene)
            fenster = live.hyprctl_json("clients") or []
            bericht.append(f"    Fenster nach der Eingabetaste: "
                           f"{[f['class'] for f in fenster]}")
            assert fenster, "es kam kein Fenster - die Aufnahme endete auf nichts"

            # --- Und wie es sich im Fuss ablegt ------------------------
            # DAS FENSTER WIRD NAMENTLICH GENANNT, UND DAS IST GEMESSEN
            #     `movetoworkspacesilent special:minimized` ohne Zusatz
            #     nimmt das AKTIVE Fenster. GEMESSEN am 24.08.2026: im
            #     ersten Lauf passierte damit gar nichts - die Aufnahme
            #     hatte EIN einziges verschiedenes Bild auf 63, also
            #     zweieinhalb Sekunden Stillstand. Mit `,address:0x...`
            #     trifft der Befehl das Fenster, das gemeint ist, ganz
            #     ohne Frage, wer gerade den Fokus hat.
            #
            #     Die Schreibweise ist dieselbe, die der Fuss selbst
            #     benutzt, um ein Fenster ZURUECKZUHOLEN
            #     (`movetoworkspacesilent <bereich>,address:0x...` in
            #     ags-dock.template), und den Weg HIN schreibt der
            #     hyprbars-Knopf aus hyprland-plugins-config.template.
            adresse = fenster[0]["address"]

            def minimieren_szene(k: Klappe) -> None:
                k.marke(f"Fenster {fenster[0]['class']} offen, "
                        "Fuss zeigt es als laufend")
                k.laufen(0.60)
                k.marke("movetoworkspacesilent special:minimized - "
                        "derselbe Weg wie der Minimieren-Knopf der "
                        "Fensterleiste (MINIMIZED_WORKSPACE)")
                ergebnis = live.hyprctl(
                    "dispatch", "movetoworkspacesilent",
                    f"special:minimized,address:{adresse}")
                assert ergebnis.returncode == 0, ergebnis.stderr
                k.laufen(2.10)

            nimm("dock-minimiert", fussfeld, minimieren_szene)
            danach = live.hyprctl_json("clients") or []
            abgelegt = [f for f in danach
                        if f["address"] == adresse
                        and f["workspace"]["name"] == "special:minimized"]
            assert abgelegt, (
                "das Fenster liegt nach dem Minimieren nicht auf "
                "special:minimized: "
                + str([(f["class"], f["workspace"]) for f in danach]))
            bericht.append("    dock-minimiert: das Fenster liegt danach auf "
                           f"{abgelegt[0]['workspace']}")

    finally:
        # VOR live.stop(), denn das raeumt das Laufzeitverzeichnis weg -
        # und ein Lauf, der auf halbem Weg aufgibt, ist genau der, dessen
        # Protokoll man lesen will.
        try:
            (out / "shell.log").write_text(live.read_shell_log(),
                                           encoding="utf-8")
        except OSError:                                  # pragma: no cover
            pass
        live.stop()

    # --- Das Rechtsklick-Menue des Fusses, in einer EIGENEN Sitzung ---
    if not gewuenscht or "dock-menue" in gewuenscht:
        weitere, protokoll = menue_lauf(out, bilderwurzel, argumente.takt,
                                        argumente.guete, argumente.nur_bilder)
        aufnahmen.extend(weitere)
        bericht.extend(protokoll)

    bericht.append("")
    bericht.append("GEMESSEN AN JEDER AUFNAHME")
    bericht.append(f"    Takt, der vorgegeben war   {argumente.takt} ms "
                   f"= {1000/argumente.takt:.1f} Bilder/s")
    gesamt = 0
    for name, klappe, ziel in aufnahmen:
        if not argumente.nur_bilder:
            breite = VOLLBILD_BREITE if klappe.ausschnitt is None else None
            webp_bauen(klappe.bilder, ziel, breite, argumente.guete,
                       1000.0 / argumente.takt)
            gesamt += ziel.stat().st_size
        bericht.extend(_bilderbericht(name, klappe, ziel))
        for zeit, text in klappe.marken:
            bericht.append(f"          {zeit:5.2f} s  {text}")
    bericht.append("")
    bericht.append(f"    Alle Aufnahmen zusammen    {gesamt} Byte "
                   f"= {gesamt/1024/1024:.2f} MiB")
    bericht.append("")
    bericht.append("AUF PERSOENLICHES GEPRUEFT")
    bericht.extend(f"    {z}" for z in pruefe_persoenliches(bilderwurzel))
    bericht.extend(f"    {z}" for z in pruefe_persoenliches(out))

    # Die verschiedenen Bilder aufheben, die gleichen wegwerfen.
    bericht.append("")
    bericht.append("DIE VERSCHIEDENEN EINZELBILDER, ZUM NACHSEHEN")
    for name, klappe, _ziel in aufnahmen:
        bericht.append(f"    {name}: "
                       + " ".join(sichere_bilder(klappe, out / "bilder" / name)))
    shutil.rmtree(bilderwurzel, ignore_errors=True)

    (out / "messwerte.txt").write_text("\n".join(bericht) + "\n",
                                       encoding="utf-8")
    print("\n".join(bericht))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
