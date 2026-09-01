# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Dateiwaehler auf dem WEG DES NUTZERS - und was danach uebrig ist.

WARUM ES DIESE DATEI NEBEN test_dateiwaehler.py GIBT
    Die Datei daneben ist am Vormittag des 01.09.2026 entstanden und war
    gruen. Am selben Tag hat der Nutzer denselben Fehler ein zweites Mal
    gemeldet:

        "immernoch sobald ich den datei icon klick um die datei
         auszuwaehlen kommt kien datei auswaehler sondern alle ags sachen
         werden blockiert irgendwie voll komisch"

    Ein Test, der einen offenen Fehler gruen meldet, ist schlimmer als
    keiner. Deshalb steht hier zuerst, WORAN das lag.

VIER UNTERSCHIEDE ZWISCHEN JENEM MESSSTAND UND DER OBERFLAECHE
    1. dateiwaehler_child.ts baut seine Flaeche mit
       `new Astal.Window({...})` von HAND nach. Die Oberflaeche ruft
       createOverlayWindow(). Ebene und Tastenmodus kommen aus dieser
       Fabrik - und wurden dort bis zum 01.09.2026 nur EINMAL gesetzt,
       beim Bauen. Eine Flaeche, die einmal gesunken ist, kam damit bei
       JEDEM weiteren Aufgehen unten wieder hoch. Ein handgebautes
       Fenster kann das nicht zeigen.

    2. Es oeffnet den Waehler aus einem GLib.timeout heraus, nicht aus
       dem Rueckruf eines Knopfes.

    3. UND DAS IST DER GROESSTE: es bricht den Waehler in JEDEM Lauf aus
       dem Programm heraus ab (Gio.Cancellable). Damit feuerte der
       Rueckruf von Gtk.FileDialog.open() immer, und zurueck() lief
       immer. Der Fall, ueber den der Nutzer klagt, ist genau der, in dem
       dieser Rueckruf NIE feuert - und den hat dort nichts gemessen.

    4. Und einer, den kein Quelltext zeigt: in der Testsitzung lief KEIN
       xdg-desktop-portal. Auf der Maschine des Nutzers laeuft eines
       (xdg-desktop-portal 1.22.1, -gtk 1.15.3, -hyprland 1.4.1 sind
       dort installiert). GTK fragt beim Oeffnen danach; im Protokoll des
       alten Laufs steht woertlich:

           Cannot get portal org.freedesktop.portal.FileChooser version:
           ... No such interface "org.freedesktop.portal.FileChooser"

DIE MESSUNG, DIE DEN UNTERSCHIED ZEIGT (01.09.2026)
    Dasselbe Kind, einmal ohne und einmal mit einem xdg-desktop-portal
    auf dem Bus der Testsitzung, beide mit dem Aufruf
    `open(fenster, ...)`, wie er bis dahin dastand:

        ohne Portal   Waehlerfenster in hyprctl clients: JA
                      Prozess lebt danach:               JA
        mit Portal    Waehlerfenster in hyprctl clients: NEIN
                      Prozess lebt danach:               NEIN
                      "Gdk-Message: Lost connection to Wayland
                       compositor."

    GTK holt fuer den Portalweg einen Fenstergriff des ELTERNfensters
    (xdg_foreign, export_toplevel). Eine Layer-Shell-Flaeche ist kein
    xdg_toplevel - der Aufruf ist ein Wayland-Protokollfehler, und der
    Compositor wirft den Kunden hinaus. "Alle ags sachen" heisst
    woertlich alle: Leiste, Dock und jede Ueberlagerung liegen in EINEM
    gjs-Prozess, und der war weg.

WAS DIESE DATEI MISST
    Denselben Weg, den der Nutzer geht: die echte Fabrik, ein echter
    Knopfdruck, und KEIN Abbruch aus dem Programm. Gemessen wird, was
    danach von der Ueberlagerung uebrig ist - beim naechsten Aufgehen.

SICHERHEIT
    Verschachtelter Compositor mit eigenem XDG_RUNTIME_DIR und eigenem
    Sitzungsbus (tests/render/desktop_session.py), wie nebenan. Das
    xdg-desktop-portal startet auf DIESEM Bus und nicht auf dem des
    Nutzers. Es wird keine Datei gewaehlt und kein VPN angefasst.
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

from tests.render.desktop_session import (             # noqa: E402
    Session, render_configuration, required_tools,
)

KIND = Path(__file__).resolve().parent / "dateiwaehler_echt_child.ts"

# Wie das Kind seine Flaeche und seinen Waehler nennt. Zwei
# Schreibweisen waeren zwei Flaechen.
NAMENSRAUM = "waehler-sonde"
FENSTERTITEL = "ZEPOS-SONDE-DIALOG"

# Astal.Layer und Astal.Keymode, wie das WIDGET sie zaehlt - nicht wie
# `hyprctl -j layers` sie zaehlt (das ist die Leiter in der Datei
# daneben). Benannt, damit ein Fehlschlag "1 statt 3" nicht als nackte
# Zahl dasteht.
WIDGET_EBENE_UNTEN = 1
WIDGET_EBENE_UEBERLAGERUNG = 3
WIDGET_TASTEN_KEINE = 0
WIDGET_TASTEN_BEI_BEDARF = 2

# Wie lange gemessen wird. Der Fahrplan des Kindes endet bei 19 s
# (T_ENDE dort); die fuenf Sekunden darueber sind die Luft, die ein
# `ags bundle` auf einer beschaeftigten Maschine braucht.
LAUFZEIT_S = 24.0

# Der Portal-Vordergrund. Als Pfad und nicht ueber die D-Bus-Aktivierung:
# so ist im Protokoll zu sehen, WANN er da war.
PORTAL = Path("/usr/lib/xdg-desktop-portal")


def _sonde(protokoll: str, marke: str) -> dict[str, str] | None:
    """Die Meldung `SONDE:<marke>:a=1:b=2` als Abbildung - oder None.

    Die LETZTE ihrer Art. Das Kind meldet jede Marke einmal; ein Kind,
    das haengt und wiederholt, wuerde sonst an seiner ersten Meldung
    gemessen statt an seinem Zustand am Ende.
    """
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


def _lauf(bau: Path, modus: str, portal: bool = False) -> dict:
    """Eine Sitzung, ein Knopfdruck, kein Abbruch."""
    ags = render_configuration(bau)

    # Das Kind IN den erzeugten Baum, damit `./utils/overlay` genau die
    # Datei trifft, die auch das Einstellungsfenster benutzt. Ein Nachbau
    # der Fabrik im Testverzeichnis wuerde den Nachbau messen - und genau
    # daran ist der Messstand nebenan gescheitert.
    ziel = ags / "dateiwaehler-sonde.ts"
    shutil.copyfile(KIND, ziel)
    bundle_pfad = bau / f"sonde-{modus}.js"
    ergebnis = subprocess.run(
        ["ags", "bundle", str(ziel), str(bundle_pfad), "-r", str(ags), "-g", "4"],
        capture_output=True, text=True, timeout=600)
    assert ergebnis.returncode == 0, (
        "`ags bundle` hat das Kind nicht uebersetzt:\n"
        + ergebnis.stdout + ergebnis.stderr)

    protokoll = bau / f"sonde-{modus}.log"
    messung: dict = {"modus": modus}
    # 1920x1200 - der Schirm des Nutzers, wie nebenan.
    with Session(1920, 1200) as sitzung:
        sitzung.start_bus()
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        sitzung.move_cursor(960, 600)
        if portal:
            # Auf dem EIGENEN Bus dieser Sitzung. Ob eine Rueckseite
            # (xdg-desktop-portal-gtk oder -hyprland) antwortet,
            # entscheidet die Maschine; fuer diese Messung reicht der
            # Vordergrund - schon seine blosse Anwesenheit schickt GTK
            # auf den Portalweg, und genau dort lag der Protokollfehler.
            sitzung.spawn([str(PORTAL)], log=bau / "portal.log",
                          XDG_CURRENT_DESKTOP="GNOME")
            time.sleep(4.0)
        kind = sitzung.spawn(
            [str(bundle_pfad)], log=protokoll,
            HYPRLAND_INSTANCE_SIGNATURE=sitzung.signature(),
            ZEPOS_SONDE=modus)

        # Sekuendlich nachsehen und nicht einmal am Ende: der Waehler
        # steht nur, solange das Kind ihn offen haelt, und ein einzelner
        # Blick zur falschen Zeit saehe ihn nicht.
        ende = time.monotonic() + LAUFZEIT_S
        sah_waehler = False
        while time.monotonic() < ende:
            time.sleep(1.0)
            for kunde in sitzung.hyprctl_json("clients") or []:
                if kunde.get("title") == FENSTERTITEL:
                    sah_waehler = True
        messung["waehler_gesehen"] = sah_waehler
        messung["lebt"] = kind.poll() is None
        messung["protokoll"] = (
            protokoll.read_text(encoding="utf-8", errors="replace")
            if protokoll.exists() else sitzung.read_shell_log())
        sitzung.shoot(bau / f"sonde-{modus}.png")
    return messung


@pytest.fixture(scope="module")
def zweitesmal(tmp_path_factory) -> dict:
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    return _lauf(tmp_path_factory.mktemp("zepsonde-zwei"), "zweitesmal")


@pytest.fixture(scope="module")
def mit_portal(tmp_path_factory) -> dict:
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    if not PORTAL.exists():
        pytest.skip(f"{PORTAL} gibt es auf dieser Maschine nicht")
    return _lauf(tmp_path_factory.mktemp("zepsonde-portal"), "offen",
                 portal=True)


def test_der_knopf_oeffnet_ueberhaupt_einen_waehler(zweitesmal):
    """Die Gegenprobe zuerst.

    Alles darunter misst, was NACH einem Waehler von der Flaeche uebrig
    ist. Gab es gar keinen, sind die Zahlen beliebig - und der Test
    meldete Erfolg fuer ein Fenster, das nie da war.
    """
    assert "SONDE:waehleDatei:true" in zweitesmal["protokoll"], (
        "waehleDatei() hat false gemeldet - GTK konnte keinen Waehler "
        f"bauen:\n{zweitesmal['protokoll'][-3000:]}")
    assert zweitesmal["waehler_gesehen"], (
        "kein Fenster mit dem Titel des Waehlers in `hyprctl clients` - "
        "der Knopf hat keinen Waehler geoeffnet:\n"
        + zweitesmal["protokoll"][-3000:])


def test_die_flaeche_sinkt_auch_auf_dem_weg_des_nutzers(zweitesmal):
    """Waehrend der Waehler steht, liegt die Flaeche unten.

    Dieselbe Zusicherung wie in der Datei daneben, aber an dem Fenster,
    das die FABRIK gebaut hat, und ausgeloest von einem Knopf statt von
    einer Zeitschaltung.
    """
    waehrend = _sonde(zweitesmal["protokoll"], "waehrend-des-waehlers")
    assert waehrend, ("keine Meldung 'waehrend-des-waehlers':\n"
                      + zweitesmal["protokoll"][-3000:])
    assert int(waehrend["ebene"]) == WIDGET_EBENE_UNTEN, (
        f"die Flaeche liegt auf Ebene {waehrend['ebene']} statt "
        f"{WIDGET_EBENE_UNTEN} - der Waehler stuende wieder darunter, und "
        "der Nutzer saehe ihn nur zur Haelfte.")
    assert int(waehrend["tastenmodus"]) == WIDGET_TASTEN_KEINE, (
        f"die Flaeche haelt die Tastatur ({waehrend['tastenmodus']}) - "
        "dann laesst sich im Waehler kein Dateiname tippen.")


def test_die_flaeche_kommt_beim_naechsten_aufgehen_zurueck(zweitesmal):
    """DER FEHLER, DEN DIE DATEI NEBENAN NICHT SEHEN KONNTE.

    Der Nutzer klickt auf das Zeichen, es kommt kein Waehler (oder er
    sieht ihn nicht), er macht das Fenster zu und wieder auf. Was er dann
    bekommt, steht hier.

    GEMESSEN am 01.09.2026, VOR der Reparatur, mit genau diesem Kind:

        SONDE:am-ende:ebene=1:tastenmodus=0:sichtbar=true

    Ebene 1 ist BOTTOM - unter jedem gewoehnlichen Fenster. Tastenmodus 0
    ist NONE - keine Tastatur, also auch kein ESC, mit dem man das
    Fenster wieder loswuerde. Ein einziger Klick vergiftete damit JEDES
    weitere Aufgehen dieses Fensters fuer die Lebensdauer des Prozesses.
    Genau das heisst "alle ags sachen werden blockiert".

    Die Reparatur steht an zwei Stellen, und beide werden hier gemessen:
    waehleDatei() holt die Flaeche auch ueber `notify::visible` zurueck,
    und show() in der Fabrik setzt Ebene und Tastenmodus bei jedem
    Aufgehen neu (beides ags-overlay-utils.template).
    """
    ende = _sonde(zweitesmal["protokoll"], "am-ende")
    assert ende, ("keine Meldung 'am-ende' - der Prozess hat den Waehler "
                  f"nicht ueberlebt:\n{zweitesmal['protokoll'][-3000:]}")
    assert ende["sichtbar"] == "true", (
        "das Fenster ist beim zweiten Mal gar nicht aufgegangen:\n"
        + zweitesmal["protokoll"][-3000:])
    assert int(ende["ebene"]) == WIDGET_EBENE_UEBERLAGERUNG, (
        f"das Fenster kommt auf Ebene {ende['ebene']} wieder hoch statt "
        f"auf {WIDGET_EBENE_UEBERLAGERUNG}. Es liegt damit unter jedem "
        "gewoehnlichen Fenster - der Nutzer sieht es nicht mehr, obwohl "
        "es offen ist.")
    assert int(ende["tastenmodus"]) == WIDGET_TASTEN_BEI_BEDARF, (
        f"das Fenster kommt mit Tastenmodus {ende['tastenmodus']} wieder "
        f"hoch statt mit {WIDGET_TASTEN_BEI_BEDARF}. Es nimmt damit keine "
        "Taste mehr an - auch kein ESC.")


def test_der_prozess_ueberlebt_einen_waehler_neben_einem_portal(mit_portal):
    """UND DER FEHLER, DEN DIE DATEI NEBENAN GAR NICHT SEHEN KONNTE.

    Sie lief in einer Sitzung OHNE xdg-desktop-portal. Auf der Maschine
    des Nutzers laeuft eines, und damit geht GTK einen anderen Weg: es
    holt fuer das Portal einen Fenstergriff des Elternfensters. Eine
    Layer-Shell-Flaeche kann keinen liefern, der Aufruf ist ein
    Protokollfehler, und der Compositor wirft den ganzen Prozess hinaus.

    GEMESSEN am 01.09.2026 mit `open(fenster, ...)` wie bis dahin und
    einem xdg-desktop-portal auf dem Bus dieser Sitzung: kein
    Waehlerfenster, und der gjs-Prozess war weg -
    "Gdk-Message: Lost connection to Wayland compositor." Das ist die
    Leiste, das Dock und jede Ueberlagerung auf einmal.

    WAS HIER ZUGESICHERT WIRD UND WAS NICHT
        Zugesichert wird die eine Richtung, die auf JEDER Maschine gilt:
        der Prozess muss den Versuch ueberleben. Ob ein Waehler
        ERSCHEINT, haengt daran, ob eine Portal-Rueckseite antwortet -
        das ist eine Eigenschaft der Maschine und keine dieses Baums.
        Diese Sitzung startet nur den Vordergrund; im Lauf vom 01.09.2026
        meldete er "Backend call failed: No such interface
        org.freedesktop.impl.portal.FileChooser", und genau deshalb steht
        darueber keine Zusicherung. Dass die Anfrage ueberhaupt ANKOMMT,
        steht dagegen fest - im selben Protokoll: "XDP: Handling
        OpenFile". Vor der Reparatur kam sie nie so weit.
    """
    assert "SONDE:waehleDatei:true" in mit_portal["protokoll"], (
        "waehleDatei() hat false gemeldet:\n"
        + mit_portal["protokoll"][-3000:])
    assert mit_portal["lebt"], (
        "der gjs-Prozess hat den Dateiwaehler neben einem Portal NICHT "
        "ueberlebt. Steht im Protokoll 'Lost connection to Wayland "
        "compositor', dann hat GTK wieder versucht, einen Fenstergriff "
        "der Layer-Flaeche zu exportieren - siehe waehleDatei() in "
        f"ags-overlay-utils.template:\n{mit_portal['protokoll'][-3000:]}")
    ende = _sonde(mit_portal["protokoll"], "am-ende")
    assert ende, ("keine Meldung 'am-ende' - der Prozess lebt, meldet aber "
                  f"nichts mehr:\n{mit_portal['protokoll'][-3000:]}")
