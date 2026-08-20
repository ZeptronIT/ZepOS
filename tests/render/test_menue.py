# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Rechtsklick-Menue des Fusses - auf einer echten Layer-Flaeche.

WAS BESTELLT WURDE
    Der Nutzer am 20.08.2026, woertlich: "rechtsklick funktioniert nicht
    bei hyprlaunch. kann ich rechtsklick auf die dock icons machen? wie
    füge ich sonst anwendungen hinzu?"

DIE FRAGE, DIE NUR EIN COMPOSITOR BEANTWORTEN KANN
    Ein Menue an einem gewoehnlichen Fenster ist eine Selbstverstaendlich-
    keit. An einer LAYER-SHELL-Flaeche ist es keine: die Flaeche des
    Fusses ist so gross wie seine Knopfreihe - GEMESSEN 385 x 45 Punkte
    in diesem Aufbau -, und ein Menue darin waere 45 Punkte hoch, also
    unbrauchbar. Es MUSS ueber ihren Rand hinausragen, und ob es das
    darf, entscheidet niemand im Programmtext.

    Der Weg dahin fuehrt ueber drei Protokolle, und jedes kann ihn
    abbrechen: GTK legt einen xdg_popup an, gtk4-layer-shell haengt ihn
    mit zwlr_layer_surface_v1.get_popup an die Layer-Flaeche statt an ein
    xdg_toplevel, und Hyprland platziert ihn. Diese Datei misst das
    Ergebnis auf dem Bild.

WAS DIE ERSTE MESSUNG GEKOSTET HAT, UND WARUM ES HIER STEHT
    Am 20.08.2026 hat derselbe Aufbau zuerst NULL veraenderte Punkte
    gemeldet - kein Menue, nirgends. Der Wayland-Mitschnitt
    (WAYLAND_DEBUG=1) hat gezeigt, dass jeder Schritt geklappt hatte:

        -> xdg_surface#142.get_popup(new id xdg_popup#143, nil, ...)
        -> zwlr_layer_surface_v1#77.get_popup(xdg_popup#143)
           xdg_popup#143.configure(-63, -87, 181, 87)
        -> wl_surface#178.attach(wl_buffer#201, 0, 0)
           wl_surface#178.enter(wl_output#29)

    Das Menue war da, mit Puffer, 181 x 87 Punkte ueber dem Fuss. Nur
    auf dem FALSCHEN Schirm: Dock() baut ein Fenster je Ausgang, der
    verschachtelte Compositor hat zwei, und grim bildet einen davon ab.
    Deshalb bekommt das Kind ZEPOS_AUSGANG und sucht sich seinen Fuss
    namentlich - siehe dort.

    Die Lehre gehoert in diese Datei, weil sie sonst beim naechsten Mal
    dieselbe Stunde kostet: ein Bild ohne Befund ist keine Antwort auf
    "geht das ueberhaupt", solange nicht feststeht, dass die Messung
    dorthin sieht, wo es passiert.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.render import measure                                # noqa: E402
from tests.render.desktop_session import (                      # noqa: E402
    Session, render_configuration, required_tools, workspaces_file,
)

BREITE, HOEHE = 1920, 1080

# Wie lange die Oberflaeche steht, bevor gemessen wird. Dieselbe Zahl
# wie in test_einfahrt.py und shoot.py.
SETTLE = 7.0

# Wie lange ein Menue braucht, bis es auf dem Bild steht. Grosszuegig:
# gemessen wird nicht die Dauer, sondern das Ergebnis.
RUHE = 2.5

DOCK = "zepos-dock"
INSTANZ = "zepos-dock-menue"

# Astal.Keymode, als Zahl - so wie das Kind sie meldet.
KEYMODE_NONE = "0"


def _buendle(eintrag: Path, ags: Path, ziel: Path) -> Path:
    """Wie bundle() in desktop_session.py, nur fuer einen anderen Eingang."""
    ergebnis = subprocess.run(
        ["ags", "bundle", str(eintrag), str(ziel), "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=600)
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat das Menue-Kind nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)
    return ziel


def _frage(sitzung: Session, wunsch: str) -> str:
    """Eine Anfrage an das Kind - derselbe Weg wie eine Tastenbindung."""
    ergebnis = subprocess.run(
        ["ags", "request", wunsch, "-i", INSTANZ],
        env=sitzung.environment(), capture_output=True, text=True, timeout=30)
    return (ergebnis.stdout + ergebnis.stderr).strip()


def _taste(sitzung: Session, name: str) -> None:
    """Eine Taste an den Compositor - von aussen, wie ein Mensch.

    wtype und nicht ein Signal an das Kind: gefragt ist, ob die Taste bei
    der Flaeche ANKOMMT, und das entscheidet der Compositor anhand der
    keyboard_interactivity der Layer-Flaeche. Ein Tastendruck, den sich
    das Programm selbst schickt, beantwortet die Frage nicht.
    """
    subprocess.run(["wtype", "-k", name], env=sitzung.environment(),
                   capture_output=True, text=True, timeout=20)


@pytest.fixture(scope="module")
def menue(tmp_path_factory) -> dict:
    """Einmal auf, einmal mit Escape zu, einmal mit einer Auswahl zu."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    if not subprocess.run(["which", "wtype"], capture_output=True).returncode == 0:
        pytest.skip("wtype fehlt - ohne Tastendruck von aussen sagt der "
                    "Escape-Teil dieses Laufs nichts")

    bau = tmp_path_factory.mktemp("zepmenue-bau")
    bilder = tmp_path_factory.mktemp("zepmenue-bild")
    ags = render_configuration(bau)

    quelle = Path(__file__).resolve().parent / "dock_menue_child.tsx"
    ziel = ags / "dock_menue_child.tsx"
    ziel.write_text(quelle.read_text(encoding="utf-8"), encoding="utf-8")
    kind = _buendle(ziel, ags, bau / "zepos-dock-menue.js")
    kindlog = bau / "kind.log"

    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # Wie in test_geometry.py: der Mauspfeil waere auf dem Bild ein
        # Befund, der keiner ist.
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(BREITE // 2, HOEHE // 2)
        time.sleep(2.0)
        tapete = sitzung.shoot(bilder / "0-tapete.png")

        sitzung.spawn([str(kind)], log=kindlog, XDG_CONFIG_HOME=str(bau),
                      ZEPOS_AUSGANG=sitzung.output)
        time.sleep(SETTLE)

        flaechen = sitzung.layers()
        assert DOCK in flaechen, (
            "der Fuss liegt gar nicht auf dem Schirm - dann sagt dieser "
            "Lauf ueber sein Menue nichts:\n" + _log(kindlog))
        kasten_zu = flaechen[DOCK]
        tastatur_zu = _frage(sitzung, "tastatur")
        zu = sitzung.shoot(bilder / "1-menue-zu.png")

        # -- auf ------------------------------------------------------
        geklickt = _frage(sitzung, "rechtsklick")
        time.sleep(RUHE)
        offen = _frage(sitzung, "offen")
        punkte = _frage(sitzung, "eintraege")
        tastatur_auf = _frage(sitzung, "tastatur")
        kasten_auf = sitzung.layers().get(DOCK)
        auf = sitzung.shoot(bilder / "2-menue-auf.png")

        # -- Escape ---------------------------------------------------
        _taste(sitzung, "Escape")
        time.sleep(RUHE)
        offen_nach_escape = _frage(sitzung, "offen")
        tastatur_nach_escape = _frage(sitzung, "tastatur")
        kasten_nach_escape = sitzung.layers().get(DOCK)
        nach_escape = sitzung.shoot(bilder / "3-nach-escape.png")

        # -- noch einmal auf, und diesmal eine Auswahl ----------------
        angeheftet_vorher = _frage(sitzung, "angeheftete")
        _frage(sitzung, "rechtsklick")
        time.sleep(RUHE)
        offen_zweitens = _frage(sitzung, "offen")
        gewaehlt = _frage(sitzung, "waehle")
        time.sleep(RUHE)
        offen_nach_auswahl = _frage(sitzung, "offen")
        tastatur_nach_auswahl = _frage(sitzung, "tastatur")
        angeheftet_nachher = _frage(sitzung, "angeheftete")
        nach_auswahl = sitzung.shoot(bilder / "4-nach-auswahl.png")

        protokoll = _log(kindlog)

    leer = measure.read_png(tapete)
    ohne = measure.read_png(zu)
    mit = measure.read_png(auf)
    danach = measure.read_png(nach_escape)
    gewaehlt_bild = measure.read_png(nach_auswahl)

    # ALLES OBERHALB der Layer-Flaeche des Fusses. Steht das Menue nur in
    # ihr, ist dieser Bereich leer - und genau das ist die Frage.
    oben = (0, 0, BREITE, kasten_zu[1])

    return {
        "kasten_zu": kasten_zu,
        "kasten_auf": kasten_auf,
        "kasten_nach_escape": kasten_nach_escape,
        "geklickt": geklickt,
        "offen": offen,
        "punkte": punkte,
        "offen_zweitens": offen_zweitens,
        "gewaehlt": gewaehlt,
        "offen_nach_escape": offen_nach_escape,
        "offen_nach_auswahl": offen_nach_auswahl,
        "angeheftet": (angeheftet_vorher, angeheftet_nachher),
        "tastatur": (tastatur_zu, tastatur_auf, tastatur_nach_escape,
                     tastatur_nach_auswahl),
        "oben": oben,
        # Die Gegenprobe der Messung selbst: der Fuss MUSS zwischen
        # Tapete und Bild eins auftauchen. Ein Lauf, dessen Bilder nichts
        # zeigen, meldete sonst dieselbe Null wie ein fehlendes Menue.
        "fuss_punkte": measure.changed_pixels(leer, ohne,
                                              (0, 0, BREITE, HOEHE)),
        "menue_oben": measure.changed_pixels(ohne, mit, oben),
        "nach_escape_oben": measure.changed_pixels(ohne, danach, oben),
        "nach_auswahl_oben": measure.changed_pixels(ohne, gewaehlt_bild, oben),
        "protokoll": protokoll,
        "bilder": bilder,
    }


def _log(pfad: Path) -> str:
    return (pfad.read_text(encoding="utf-8", errors="replace")
            if pfad.exists() else "")


# --------------------------------------------------------------------
# Die Messung misst ueberhaupt etwas
# --------------------------------------------------------------------

def test_der_lauf_sieht_den_fuss_ueberhaupt(menue):
    """Ohne diese Zusicherung waere jede Null darunter zweideutig."""
    punkte = menue["fuss_punkte"]
    assert len(punkte) > 1000, (
        f"zwischen Tapete und erstem Bild haben sich nur {len(punkte)} "
        "Punkte geaendert - dann steht der Fuss nicht auf dem Bild, und "
        "die Messungen darunter sagen nichts:\n" + menue["protokoll"])
    assert measure.bounds_of(punkte) == menue["kasten_zu"], (
        "der bemalte Kasten ist nicht der, den `hyprctl layers` fuer den "
        f"Fuss nennt: {measure.bounds_of(punkte)} gegen "
        f"{menue['kasten_zu']}")


def test_der_rechtsklick_findet_seine_geste(menue):
    assert menue["geklickt"] == "geklickt", (
        "am angehefteten Knopf haengt keine Rechtsklick-Geste: "
        f"{menue['geklickt']!r}")


# --------------------------------------------------------------------
# Die eine Frage, um die es geht
# --------------------------------------------------------------------

def test_das_menue_steht_ueber_der_layer_flaeche(menue):
    """Ein Menue, das in den 45 Punkten des Fusses bleiben muesste, waere
    keines. GEMESSEN am 20.08.2026: der Popup wird als eigene
    Wayland-Flaeche angelegt (zwlr_layer_surface_v1.get_popup) und von
    Hyprland ueber dem Fuss platziert."""
    assert menue["offen"] == "abgebildet", (
        f"das Menue ist nicht abgebildet: {menue['offen']!r}\n"
        + menue["protokoll"])
    punkte = menue["menue_oben"]
    kasten = measure.bounds_of(punkte)
    assert len(punkte) > 500, (
        f"ueber dem Fuss haben sich nur {len(punkte)} Punkte geaendert - "
        "das Menue steht also nicht dort. Bilder: "
        f"{menue['bilder']}\n" + menue["protokoll"])
    # Und es steht wirklich DARUEBER und nicht bloss am Rand: sein Kasten
    # beginnt oberhalb der Oberkante des Fusses.
    assert kasten is not None and kasten[1] < menue["kasten_zu"][1], (
        f"der bemalte Kasten {kasten} faengt nicht oberhalb des Fusses "
        f"({menue['kasten_zu']}) an")


def test_das_menue_traegt_die_beiden_punkte_einer_anheftung(menue):
    """Auf einem angehefteten Symbol: neues Fenster, abnehmen."""
    assert menue["punkte"] == "New window|Remove from dock", (
        f"das Menue einer Anheftung zeigt {menue['punkte']!r}")


def test_der_fuss_wird_von_seinem_menue_nicht_groesser(menue):
    """Der Fuss haelt eine EXKLUSIVE Zone. Waechst seine Flaeche, waehrend
    ein Menue offen ist, schiebt er jedes Fenster des Schirms - und zwar
    fuer ein Menue, das gleich wieder zugeht."""
    assert menue["kasten_auf"] == menue["kasten_zu"], (
        f"der Fuss war {menue['kasten_zu']} und ist mit offenem Menue "
        f"{menue['kasten_auf']}")
    assert menue["kasten_nach_escape"] == menue["kasten_zu"], (
        f"der Fuss ist nach dem Menue {menue['kasten_nach_escape']} "
        f"statt {menue['kasten_zu']}")


# --------------------------------------------------------------------
# Es geht wieder zu - auf beiden Wegen, die von aussen messbar sind
# --------------------------------------------------------------------

def test_escape_schliesst_das_menue(menue):
    """Die Taste kommt von aussen (wtype), also ueber den Compositor.

    Das ist zugleich die Messung fuer die Umschaltung der
    Tastaturannahme: ohne sie bekaeme die Layer-Flaeche gar kein
    Tastenereignis, und dieser Test bliebe rot.
    """
    assert menue["offen_nach_escape"] == "keins", (
        f"nach Escape ist das Menue {menue['offen_nach_escape']!r}")
    rest = menue["nach_escape_oben"]
    assert rest == set(), (
        f"nach Escape bemalen noch {len(rest)} Punkte den Bereich ueber "
        f"dem Fuss, Kasten {measure.bounds_of(rest)} - ein Menue, das "
        "haengenbleibt, ist schlimmer als keines")


def test_eine_auswahl_schliesst_das_menue(menue):
    """Gewaehlt wird die LETZTE Zeile - siehe das Kind, warum nicht die
    erste: "Neues Fenster" startet einen Browser, und ueber einem
    Browser ist nicht mehr zu sehen, ob das Menue fort oder verdeckt
    ist."""
    assert menue["offen_zweitens"] == "abgebildet", (
        "das Menue geht beim zweiten Mal gar nicht erst auf: "
        f"{menue['offen_zweitens']!r}")
    assert menue["gewaehlt"] == "gewaehlt", (
        f"die letzte Zeile liess sich nicht anklicken: {menue['gewaehlt']!r}")
    assert menue["offen_nach_auswahl"] == "keins", (
        f"nach der Auswahl ist das Menue {menue['offen_nach_auswahl']!r}")
    rest = menue["nach_auswahl_oben"]
    assert rest == set(), (
        f"nach der Auswahl bemalen noch {len(rest)} Punkte den Bereich "
        f"ueber dem Fuss, Kasten {measure.bounds_of(rest)}")


def test_ein_gescheiterter_schreibversuch_nimmt_kein_symbol_weg(menue):
    """Die Gegenprobe zum Abnehmen, und sie faellt hier von selbst an.

    "Vom Dock entfernen" schreibt ueber zepos-settings-gui. Auf einer
    Entwicklermaschine gibt es den Befehl nicht (`which
    zepos-settings-gui` findet nichts), der Schreibversuch scheitert -
    und GENAU DANN darf die Reihe sich nicht aendern. Ein Symbol, das
    verschwindet und beim naechsten Anmelden wieder dasteht, waere die
    schlechtere Haelfte beider Welten.
    """
    vorher, nachher = menue["angeheftet"]
    assert vorher, "es war ueberhaupt nichts angeheftet"
    assert nachher == vorher, (
        f"die Reihe war {vorher!r} und ist nach dem gescheiterten "
        f"Schreibversuch {nachher!r}")


def test_der_fuss_nimmt_die_tastatur_nie(menue):
    """Auch nicht, waehrend sein Menue steht.

    Der Fuss verspricht an drei Stellen, die Tastatur nie zu nehmen
    (ags-power-button.template, ags-starter-button.template, Dock()).
    Ein Menue ist kein Grund, das zu brechen: den Tastaturfokus bekommt
    die Flaeche des POPUPS ueber seinen Griff, nicht der Fuss darunter -
    `wl_keyboard.enter(..., wl_surface#178)` im Wayland-Mitschnitt vom
    20.08.2026, und der Escape-Test daneben ist der Beleg dafuer, dass
    es reicht.

    Diese Zusicherung ist die Gegenprobe zu einer Zeile, die es einmal
    gab: der Fuss schaltete waehrend des Menues auf
    Astal.Keymode.ON_DEMAND. Derselbe Lauf ohne sie war gruen - also
    war sie wirkungslos, und eine wirkungslose Zeile, die ein
    Versprechen bricht, ist teurer als keine.
    """
    for wann, wert in zip(("zu", "offen", "nach Escape", "nach der Auswahl"),
                          menue["tastatur"]):
        assert wert == KEYMODE_NONE, (
            f"{wann} nimmt der Fuss die Tastatur: keymode={wert}")


def test_der_lauf_hat_nichts_kritisches_gemeldet(menue):
    """Eine Warnung ist in diesem Projekt ein Testfehler."""
    schlimm = [zeile for zeile in menue["protokoll"].splitlines()
               if "CRITICAL" in zeile
               # Ohne Compositor-Ereignissocket meldet der Fuss das - er
               # HAT hier einen, aber das Kind startet vor Hyprlands
               # erster Antwort. Steht in jedem Lauf und gehoert zum
               # Aufbau.
               and "Ereignissocket" not in zeile
               # UND die Klage ueber den fehlenden Einstellungsbefehl.
               # Sie ist der BELEG dieses Laufs und kein Mangel: der
               # Test waehlt absichtlich "Vom Dock entfernen", der
               # Befehl fehlt auf dieser Maschine, und dass das Dock das
               # SAGT statt still nichts zu tun, ist die Zusicherung
               # test_ein_gescheiterter_schreibversuch_nimmt_kein_symbol_weg.
               and "zepos-settings-gui" not in zeile
               # UND eine Warnung, die NICHT aus dieser Vorlage kommt.
               # Sie steht unten in ihrer eigenen Zusicherung, samt
               # Eingrenzung - hier waere sie nur eine Zahl.
               and "gtk_widget_is_ancestor" not in zeile]
    assert schlimm == [], "\n".join(schlimm)


def test_die_eine_fremde_warnung_bleibt_die_eine_fremde_warnung(menue):
    """Gtk-CRITICAL beim Aufklappen - eingegrenzt, nicht weggesehen.

    WAS GEMELDET WIRD, genau zweimal je Lauf und damit einmal je
    Aufklappen:

        Gtk-CRITICAL: gtk_widget_is_ancestor:
                      assertion 'GTK_IS_WIDGET (widget)' failed

    WO SIE HERKOMMT, EINGEGRENZT am 20.08.2026 in fuenf Laeufen:

        beim SCHLIESSEN?              nein. Marken um jede Anfrage herum
                                      zeigen sie zwischen MARKE-ANFANG
                                      und MARKE-ENDE des RECHTSKLICKS,
                                      nie beim Zugehen.
        an den Zeilen?                nein. Ein Popover OHNE jede Zeile,
                                      direkt mit popup() aufgeklappt,
                                      meldet sie genauso.
        an der synthetischen Geste?   nein, aus demselben Lauf: ohne
                                      Geste erscheint sie auch.
        an der Tastatur-Umschaltung?  nein. Der Lauf ohne sie meldet sie
                                      unveraendert.
        am Fokus des Fusses?          nein. set_focus(null) davor aendert
                                      nichts.
        an `autohide`?                JA. Mit `autohide: false`
                                      verschwindet sie restlos.

    Damit steht sie in GTKs eigener Buchfuehrung fuer den Griff eines
    Popovers ueber einer Layer-Shell-Flaeche - nicht in dieser Vorlage.
    `autohide` ist genau das, was "Klick daneben schliesst das Menue"
    ausmacht; es abzuschalten hiesse, ein haengendes Menue gegen eine
    Logzeile zu tauschen.

    Diese Zusicherung haelt den Befund fest UND deckelt ihn: bleibt es
    bei zwei, ist alles beim Alten. Werden es mehr, hat jemand etwas
    hinzugefuegt, und das faellt hier auf statt im Protokoll des
    Nutzers.
    """
    treffer = [zeile for zeile in menue["protokoll"].splitlines()
               if "gtk_widget_is_ancestor" in zeile]
    assert len(treffer) == 2, (
        f"{len(treffer)} statt zwei - je Aufklappen eine war der Stand "
        "vom 20.08.2026:\n" + "\n".join(treffer))
