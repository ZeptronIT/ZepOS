# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Schirm kommt dazu, ein Schirm geht - und die Oberflaeche folgt.

WAS BESTELLT WURDE
    Der Nutzer am 01.09.2026, woertlich: "ich habe einen bildschirm
    hingezogen und ueber dem monitor geplaced und trotzdem wird die
    oberflaeche nicht erweitert - ich sehe auf dem monitor nicht den
    header usw, die dock dort nochmal, sondern einfach nur ein grauer
    bildschirm". Und, auf den Vorschlag, dafuer ein fremdes Programm zu
    nehmen: "nein, wir muessen das einfach richtig loesen, sodass man das
    auch verwenden kann".

DIE URSACHE, GEMESSEN am 01.09.2026
    Fuenf Bauteile bauten eine Layer-Shell-Flaeche je Schirm - Leiste,
    Dock, Home, Abschaltknopf, Starterknopf -, und alle fuenf fragten
    `Gdk.Display.get_monitors()` GENAU EINMAL, beim Start. Ein `grep`
    ueber src/templates fand am selben Tag KEIN "items-changed", kein
    "monitor-added", kein "monitor-removed". Ein Schirm, der nach dem
    Anmelden dazukam, bekam deshalb nie eine Flaeche.

WARUM DAS NUR HIER MESSBAR IST
    Weil "eine Flaeche liegt auf DIESEM Schirm" eine Aussage des
    Compositors ist und keine des Widgets. tests/src/ baut die Inhalte
    kopflos und misst ihre Breite; ob eine Astal.Window auf dem
    angesteckten Ausgang liegt, weiss nur `hyprctl layers`. Und das
    Anstecken selbst gibt es nur an einem echten Compositor:
    `hyprctl output create headless` legt einen Ausgang an, der an keiner
    Hardware haengt - dieselbe Zeile, mit der desktop_session.py schon
    seinen abgebildeten Schirm baut.

WAS HIER NICHT PASSIERT
    Nichts beruehrt die Sitzung des Menschen, der den Lauf gestartet hat.
    Der Compositor ist ein eigener (refuse_the_real_session() prueft das
    vor JEDEM Kindprozess), und `hyprctl` bekommt die Kennung genau
    dieses Compositors mit - siehe Session.hyprctl().
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.render.desktop_session import (                      # noqa: E402
    Session, bundle, render_configuration, required_tools, workspaces_file,
)

BREITE, HOEHE = 1920, 1080

# Wie lange die Oberflaeche nach dem Start braucht, bis sie steht.
# Dieselbe Zahl wie in test_dock_breite.py, und aus demselben Grund:
# gemessen wird das Ergebnis, nicht die Dauer.
RUHE = 7.0

# Wie lange nach einem Schirmwechsel gewartet wird. Ein Wechsel geht
# ueber drei Stationen - Compositor, GDK, die Rueckrufe der Oberflaeche -,
# und jede davon laeuft in ihrer eigenen Schleife.
WECHSEL = 6.0

# Die fuenf Flaechen, die es JE SCHIRM gibt. Nicht "die Leiste und das
# Dock": der Nutzer hat den Kopf und das Dock genannt, aber ein Schirm
# ohne Home hat keinen Hintergrund, auf dem seine Symbole liegen, und
# einer ohne die beiden Eckknoepfe hat zwei Bedienelemente weniger als
# der Schirm daneben. Wer nur zwei davon prueft, baut den naechsten
# grauen Schirm mit drei Bauteilen.
JE_SCHIRM = ("zepos-bar", "zepos-dock", "zepos-home", "zepos-power",
             "zepos-starter")

# Die modulweite Vorrichtung `umstecken` steckt in einer verschachtelten
# Sitzung einen Ausgang dazu und wieder ab. Ein Anstecken ist ein
# Ereignis des Compositors; dass die Oberflaeche ihm folgt, ist an
# keiner Vorlage abzulesen - der Nutzer sah einen grauen Bildschirm.
pytestmark = pytest.mark.allow_subprocess


def flaechen_je_schirm(sitzung: Session) -> dict[str, list[str]]:
    """{"WL-1": ["zepos-bar", ...], ...} - was auf welchem Ausgang liegt.

    Die Namensraeume werden GEZAEHLT und nicht in eine Menge gelegt: die
    Frage dieser Datei ist unter anderem, ob nach einem Umstecken ZWEI
    Leisten auf einem Schirm liegen, und eine Menge kann das nicht sagen.
    """
    daten = sitzung.hyprctl_json("layers") or {}
    gefunden: dict[str, list[str]] = {}
    for name, schirm in daten.items():
        namen: list[str] = []
        for ebene in schirm.get("levels", {}).values():
            for flaeche in ebene:
                namen.append(flaeche.get("namespace"))
        gefunden[name] = sorted(namen)
    return gefunden


def eigene(sitzung: Session) -> dict[str, list[str]]:
    """Dasselbe, aber nur die fuenf Flaechen dieses Projekts."""
    return {schirm: [name for name in namen if name in JE_SCHIRM]
            for schirm, namen in flaechen_je_schirm(sitzung).items()}


def schirme(sitzung: Session) -> list[str]:
    return sorted(monitor["name"]
                  for monitor in (sitzung.hyprctl_json("monitors") or []))


def steck_an(sitzung: Session, timeout: float = 20.0) -> str:
    """Einen weiteren headless-Ausgang anstecken und seinen Namen sagen."""
    vorher = set(schirme(sitzung))
    ergebnis = sitzung.hyprctl("output", "create", "headless")
    assert ergebnis.returncode == 0, (
        f"kein zweiter headless-Ausgang: {ergebnis.stdout}{ergebnis.stderr}")
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        neu = sorted(set(schirme(sitzung)) - vorher)
        if neu:
            return neu[0]
        time.sleep(0.2)
    raise AssertionError(
        f"der angesteckte Ausgang ist nicht erschienen: {schirme(sitzung)}")


def steck_ab(sitzung: Session, name: str, timeout: float = 20.0) -> None:
    ergebnis = sitzung.hyprctl("output", "remove", name)
    assert ergebnis.returncode == 0, (
        f"{name} liess sich nicht abstecken: "
        f"{ergebnis.stdout}{ergebnis.stderr}")
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        if name not in schirme(sitzung):
            return
        time.sleep(0.2)
    raise AssertionError(f"{name} steht immer noch da: {schirme(sitzung)}")


@pytest.fixture(scope="module")
def umstecken(tmp_path_factory) -> dict:
    """Einer kommt, einer geht, einer kommt wieder - vier Messungen."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zepmehrschirm-bau")
    ags = render_configuration(bau)
    schale = bundle(ags, bau)

    with Session(BREITE, HOEHE) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()
        time.sleep(1.5)
        sitzung.shell(schale, bau)
        time.sleep(RUHE)

        vorher = eigene(sitzung)

        dazu = steck_an(sitzung)
        time.sleep(WECHSEL)
        mit = eigene(sitzung)

        steck_ab(sitzung, dazu)
        time.sleep(WECHSEL)
        ohne = eigene(sitzung)

        wieder = steck_an(sitzung)
        time.sleep(WECHSEL)
        erneut = eigene(sitzung)

        # UND ZULETZT DER SCHIRM, DER VON ANFANG AN FLAECHEN TRUG.
        #
        #     Die vier Messungen darueber stecken einen Schirm an und
        #     wieder ab, der erst NACH dem Start der Oberflaeche
        #     entstanden ist. Vor dem 01.09.2026 bekam der nie eine
        #     Flaeche - ihn abzustecken konnte also gar nichts
        #     hinterlassen, und die Frage "wandert eine Flaeche beim
        #     Abstecken auf einen anderen Schirm" waere unbeantwortet
        #     geblieben.
        #
        #     Der headless-Ausgang, den Session.start() anlegt, traegt
        #     seine fuenf Flaechen seit dem Start. An IHM ist die Frage
        #     wirklich zu stellen.
        alter = sitzung.output
        steck_ab(sitzung, alter)
        time.sleep(WECHSEL)
        danach = eigene(sitzung)

        protokoll = sitzung.read_shell_log()

    return {"vorher": vorher, "mit": mit, "ohne": ohne, "erneut": erneut,
            "danach": danach, "alter": alter,
            "dazu": dazu, "wieder": wieder, "protokoll": protokoll}


def test_am_anfang_traegt_jeder_schirm_die_fuenf_flaechen(umstecken):
    """Die Grundlage. Ohne sie sagte "auf dem neuen erscheinen sie" nichts
    - eine Oberflaeche, die nirgends etwas baut, erfuellt es auch.

    ZWEI Schirme sind es schon hier: der verschachtelte Compositor hat
    den Ausgang seines Wirtsfensters und den headless-Ausgang, den
    Session.start() anlegt.
    """
    vorher = umstecken["vorher"]
    assert len(vorher) >= 2, (
        f"der Aufbau hat nur {len(vorher)} Schirme: {vorher}")
    for schirm, namen in vorher.items():
        assert namen == sorted(JE_SCHIRM), (
            f"{schirm} traegt {namen} statt {sorted(JE_SCHIRM)}:\n"
            + umstecken["protokoll"])


def test_ein_angesteckter_schirm_bekommt_die_oberflaeche(umstecken):
    """DIE BESTELLUNG: "trotzdem wird die oberflaeche nicht erweitert ...
    sondern einfach nur ein grauer bildschirm".

    Vor dem 01.09.2026 stand der neue Ausgang in `hyprctl monitors` und
    trug KEINE einzige Flaeche - die fuenf Bauteile hatten ihre Schirme
    beim Start abgezaehlt und horchten auf keine Aenderung.
    """
    mit, dazu = umstecken["mit"], umstecken["dazu"]
    assert dazu in mit, (
        f"{dazu} steht in keiner Ebene: {mit}\n" + umstecken["protokoll"])
    assert mit[dazu] == sorted(JE_SCHIRM), (
        f"der angesteckte Schirm {dazu} traegt {mit[dazu]} statt "
        f"{sorted(JE_SCHIRM)}:\n" + umstecken["protokoll"])


def test_die_anderen_schirme_bleiben_dabei_wie_sie_waren(umstecken):
    """Die Gegenprobe zur Bestellung. Ein Anstecken, das die vorhandenen
    Schirme neu baut, waere ein Flackern auf jedem Schirm bei jedem
    Kabel."""
    vorher, mit = umstecken["vorher"], umstecken["mit"]
    for schirm, namen in vorher.items():
        assert mit.get(schirm) == namen, (
            f"{schirm} traegt nach dem Anstecken {mit.get(schirm)} statt "
            f"{namen}:\n" + umstecken["protokoll"])


def test_ein_abgesteckter_schirm_nimmt_seine_flaechen_mit(umstecken):
    """Die Haelfte, die weh tut.

    Eine Flaeche, deren Schirm verschwindet, haelt sonst einen Zeiger auf
    einen Gdk.Monitor, den es nicht mehr gibt - und landet beim naechsten
    Sichtbarmachen (SUPER+B setzt `visible` auf drei dieser fuenf) auf
    dem Schirm, den der Compositor sich aussucht.
    """
    ohne, dazu = umstecken["ohne"], umstecken["dazu"]
    assert dazu not in ohne, (
        f"{dazu} ist abgesteckt und traegt immer noch {ohne.get(dazu)}:\n"
        + umstecken["protokoll"])
    for schirm, namen in umstecken["vorher"].items():
        assert ohne.get(schirm) == namen, (
            f"{schirm} traegt nach dem Abstecken {ohne.get(schirm)} statt "
            f"{namen} - eine Flaeche des fortgenommenen Schirms ist "
            f"hierher gewandert:\n" + umstecken["protokoll"])


def test_nach_dem_wiederanstecken_liegt_nichts_doppelt(umstecken):
    """DIE ZWEITE BESTELLUNG: "ich sehe seit dem anwenden alle sachen
    doppelt auf einem monitor".

    Ein Schirm, der kurz weg ist und wiederkommt, heisst wieder "HEADLESS
    -2" - aber GDK wirft sein altes Objekt weg und legt ein neues an.
    jeSchirm() (src/templates/ags-kit.template) vergleicht deshalb die
    OBJEKTE und nicht die Namen: wer nach dem Namen vergleicht, haelt die
    tote Flaeche fuer die richtige.

    Gezaehlt wird, nicht auf Vorhandensein geprueft: die Frage ist
    ausdruecklich, ob eine Flaeche ZWEIMAL daliegt.
    """
    erneut = umstecken["erneut"]
    for schirm, namen in erneut.items():
        assert namen == sorted(set(namen)), (
            f"{schirm} traegt eine Flaeche doppelt: {namen}\n"
            + umstecken["protokoll"])
    assert erneut[umstecken["wieder"]] == sorted(JE_SCHIRM), (
        f"der wieder angesteckte Schirm traegt "
        f"{erneut[umstecken['wieder']]} statt {sorted(JE_SCHIRM)}:\n"
        + umstecken["protokoll"])
    assert len(erneut) == len(umstecken["vorher"]) + 1, (
        f"es stehen {len(erneut)} Schirme in den Ebenen: {erneut}")


def test_ein_schirm_der_flaechen_trug_laesst_keine_zurueck(umstecken):
    """DIE FRAGE, DIE "alles doppelt" BEANTWORTET ODER AUSSCHLIESST.

    Abgesteckt wird hier der Ausgang, der seine fuenf Flaechen SEIT DEM
    START traegt - nicht einer, der eben erst dazukam. Nur an ihm laesst
    sich messen, ob eine Flaeche beim Verschwinden ihres Schirms auf
    einen anderen wandert; die Vermutung war, dass genau so zwei Leisten
    auf einem Schirm entstehen.

    GEMESSEN am 01.09.2026, mit und ohne die Behebung: sie wandert
    NICHT. Der Compositor schliesst die Layer-Flaechen seines Ausgangs
    selbst, und keiner der verbleibenden Schirme bekommt etwas dazu.
    "Alles doppelt auf einem Monitor" kommt also nicht vom Umstecken -
    es kommt von zwei Schirmen, die uebereinanderliegen (siehe
    displays.snap() und tests/src/test_displays.py).

    Das entwertet die Behebung nicht, es entwertet nur diese eine
    Erklaerung: ohne sie bekam der ANGESTECKTE Schirm gar keine Flaeche,
    und das ist der graue Bildschirm aus derselben Meldung.
    """
    danach, alter = umstecken["danach"], umstecken["alter"]
    assert alter not in danach, (
        f"{alter} ist abgesteckt und traegt weiter {danach.get(alter)}:\n"
        + umstecken["protokoll"])
    for schirm, namen in danach.items():
        assert namen == sorted(JE_SCHIRM), (
            f"{schirm} traegt nach dem Abstecken von {alter} {namen} statt "
            f"{sorted(JE_SCHIRM)} - eine Flaeche ist hierher gewandert:\n"
            + umstecken["protokoll"])
    assert danach, "es ist gar kein Schirm mehr uebrig"
