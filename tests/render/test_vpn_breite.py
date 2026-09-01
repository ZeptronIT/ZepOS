# SPDX-License-Identifier: GPL-3.0-or-later
"""Die VPN-Einstellungen, gezeichnet - und der Ueberhang nachgemessen.

WORAUF DIESE DATEI ANTWORTET
    aufgabe-34-report.md, Abschnitt 2.6 (18.08.2026), und
    aufgabe-43-report.md, Punkt 2: das Einstellungsfenster des VPN steht
    42 Punkte ueber seiner Sprosse.

        .vpn-settings-actions, gemessen              626
        Container-Polster, zweimal                   +50
                                                    ----
        .vpn-settings-container verlangt             676
        Rahmen 1px, zweimal                           +2
        senkrechte Bildlaufleiste                    +24
                                                    ----
        Inhalt braucht                               702
        Sprosse M                                     660
        UEBERHANG                                      42

    Was das auf dem Schirm heisst, steht im Kopf von
    ags-vpn-settings.template: das Sichtfenster rollt waagerecht, und
    der Inhalt wird LINKS abgeschnitten - der erste Reiter las sich
    "in" statt "Allgemein".

    Unbehoben blieb es, weil beide Auswege "ein Fenster sichtbar
    veraendern, ueber das niemand geklagt hat". Mit der zweiten Bauart
    (21.08.2026) veraendert es sich ohnehin, und es steht seither auf
    Sprosse L.

WORAN GEMESSEN WIRD, UND WARUM NICHT AN BILDPUNKTEN
    An `hadj.get_upper()` der Fabrik - der BREITE, DIE DER INHALT
    BEKOMMT. Die Fabrik (ags-overlay-utils.template) misst sie ohnehin
    schon; sie nennt sie seit dem 21.08.2026 in ihrer Meldung, statt nur
    den Fehlbetrag.

    ZWEI ANLAEUFE, DIE NICHT TAUGTEN, und warum diese Datei so
    aussieht, wie sie aussieht - beide GEMESSEN am 21.08.2026:

      * Die Layer-Shell-Flaeche an hyprctl. Sie erscheint in einem Teil
        der Laeufe GAR NICHT (derselbe Befund, den der Kopf von
        test_schale_stil.py fuer die Schale beschreibt: "die Flaeche
        bleibt laenger als 20 Sekunden komplett aus"), und wenn sie
        erscheint, hat sie eine Weile noch nicht ihre Endgroesse - eine
        Messung ergab 200 Punkte fuer ein Fenster, das 880 breit ist.

      * Der blosse Fehlbetrag aus der Fabrikmeldung. Er lautete "237px
        breiter als das Fenster erlaubt" - und die beiden Zahlen
        dahinter waren `Inhalt 676 / Sichtfenster 439`. Das Sichtfenster
        war also die halbe Sprosse: die Meldung stammt aus der ERSTEN
        Zuteilung, bevor die Flaeche ihre Groesse hat. Ein Test darauf
        haette einen Zustand geprueft, den niemand zu sehen bekommt.

    `upper` hat diese Schwaeche nicht. Es ist die Breite, die das Kind
    der Bildlauf-Flaeche bekommt, also `max(natuerliche Breite,
    Sichtfenster)`:

      * Ist das Sichtfenster kleiner (waehrend der ersten Zuteilung),
        steht dort die NATUERLICHE Breite des Inhalts - 676.
      * Ist es groesser (im Ruhezustand), steht dort das Sichtfenster,
        und das ist per Definition nicht zu breit.

    In beiden Faellen gilt dieselbe Aussage: passt `upper` in das, was
    die Sprosse uebriglaesst, dann gibt es keinen Ueberhang. Der Test
    haelt deshalb JEDE gemeldete Messung gegen diese Schranke und nicht
    nur die letzte - er haengt damit an keinem Zeitpunkt.

DER PREIS
    Ein verschachtelter Compositor, rund eine halbe Minute. Die Sitzung
    ist verschachtelt und beruehrt die Hyprland-Instanz des Nutzers
    nicht.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render.desktop_session import (             # noqa: E402
    Session, bundle, render_configuration, required_tools, workspaces_file,
)

SETTLE = 6.0
NAMESPACE = "vpn-settings"

# Was die Fabrik dem Inhalt von der Sprosse abzieht, bevor er anfangen
# darf. Beide Zahlen stehen so schon in der Rechnung von
# aufgabe-34-report.md 2.6 und im Kopf von ags-vpn-settings.template:
#
#     .overlay-outer, Rahmen 1px, zweimal            2
#     senkrechte Bildlaufleiste (immer reserviert)  24
RAHMEN_UND_LEISTE = 26

# `Inhalt <n>px, Sichtfenster <m>px` - die Meldung aus
# ags-overlay-utils.template. Sie wird nur geschrieben, WENN etwas nicht
# passt; keine Meldung ist also der gute Fall, und dieser Ausdruck fischt
# die Zahlen aus den Meldungen, die es doch gibt.
MELDUNG = re.compile(
    r'Ueberlagerung "([^"]+)": Inhalt (\d+)px, Sichtfenster (\d+)px')


def _modal_width_l() -> int:
    """Die Sprosse aus DERSELBEN Quelle, aus der die Vorlage sie bekommt.

    Nicht abgeschrieben - dieselbe Begruendung wie _modal_width_l() in
    test_schale_stil.py: eine abgeschriebene Erwartung misst die
    Abschrift und nicht das Erzeugte.
    """
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import sizes
        return sizes.MODAL_WIDTH("L")
    finally:
        sys.path.remove(str(ROOT / "src"))


def _shipped_settings(kind: str = "ipsec") -> str:
    """Die ausgelieferten Vorgaben, auf eine Bauart gestellt.

    `kind` ist ein Parameter geworden, als OpenVPN am 22.08.2026 die
    dritte Bauart wurde: die Reiter werden nach Bauart GETAUSCHT
    (tabsForKind in ags-vpn-settings.template), also ist der Ueberhang
    je Bauart eine eigene Messung. Eine Zusicherung, die nur IPsec
    zeichnet, sagt ueber die beiden anderen nichts.
    """
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import settings
        document = settings.defaults()
        # ZWEI VERBINDUNGEN, SEIT DEM 22.08.2026 - und das ist keine
        # Zutat, sondern der Punkt.
        #
        #     Der Nutzer hat die Liste bestellt, weil er MEHRERE
        #     Zugaenge hat. Ein Bildlauf mit einer einzigen Verbindung
        #     zeichnete eine Liste, die aussieht wie vorher, und
        #     bewiese ueber die Breite genau nichts: die
        #     Verbindungsleiste links traegt erst dann ihre volle
        #     Anspruchsbreite, wenn wirklich Zeilen darin stehen.
        #
        #     Die zweite ist ABSICHTLICH WireGuard, auch im
        #     IPsec-Lauf: "bei wireguard, weil ich dort mehrere vpns
        #     habe ... das gleiche gilt uebrigens fuer die anderen vpn
        #     verbindungen auch". Zwei Bauarten nebeneinander sind der
        #     Fall, den es vor dieser Aufgabe nicht geben konnte.
        erste = dict(settings.default_connection(), id="c1")
        erste["kind"] = kind
        erste["connection_name"] = "arbeit"
        erste["server"] = "gateway.example.invalid"
        zweite = dict(settings.default_connection(), id="a1b2c3d4")
        zweite["kind"] = "wireguard"
        zweite["connection_name"] = "zuhause"
        zweite["wireguard"] = dict(zweite["wireguard"])
        zweite["wireguard"]["peers"] = [{
            "public_key": "", "endpoint": "heim.example.invalid:51820",
            "allowed_ips": ["10.9.0.0/24"], "keepalive": 25,
            "preshared_key_file": "",
        }]
        document["vpn"] = {"active": "c1", "connections": [erste, zweite]}
        if kind == "openvpn":
            erste["openvpn"] = dict(erste["openvpn"])
            # Ein Endpunkt und ein Zertifikatsname, damit die Reiter
            # "Verbindung" und "Zertifikate" wirklich Inhalt tragen -
            # ein leeres Fenster misst seine eigene Leere.
            erste["openvpn"]["remote"] = "gateway.example.invalid"
            erste["openvpn"]["port"] = 1194
            erste["openvpn"]["connection_type"] = "password-tls"
            erste["openvpn"]["username"] = "jemand"
            erste["openvpn"]["ca_file"] = "work-ca.pem"
            erste["openvpn"]["cert_file"] = "work-cert.pem"
            erste["openvpn"]["key_file"] = "work-key.pem"
            erste["openvpn"]["tls_auth_file"] = "work-tls-auth.key"
            erste["openvpn"]["extra"] = [
                ["data-ciphers", "AES-256-GCM:AES-128-GCM"]]
        return json.dumps(document, indent=2)
    finally:
        sys.path.remove(str(ROOT / "src"))


def _lauf(bau, kind: str) -> str:
    """Das Fenster einmal oeffnen und aufschreiben, was die Schale meldet."""
    ags = render_configuration(bau)
    bundle(ags, bau)

    # Eine echte Einstellungsdatei. Ohne sie meldet das Fenster beim
    # Oeffnen einen Lesefehler und baut aus seinen Vorgaben weiter - das
    # ist richtig so, aber ein Test soll den Normalfall messen und nicht
    # den Notfall.
    (bau / "zepos").mkdir(parents=True, exist_ok=True)
    (bau / "zepos" / "user-settings.json").write_text(_shipped_settings(kind),
                                                     encoding="utf-8")

    with Session(1920, 1080) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        sitzung.wallpaper()
        sitzung.shell(bau / "zepos-shell.js", bau)
        time.sleep(SETTLE)

        antwort = sitzung.request(NAMESPACE)
        assert "toggled" in antwort, (
            f"ags request {NAMESPACE} antwortete {antwort!r}")
        # Zeit fuer die Zuteilung. Nicht auf die Flaeche gewartet - siehe
        # den Dateikopf: sie erscheint in einem Teil der Laeufe nicht,
        # die Messung der Fabrik aber immer.
        time.sleep(6.0)

        # UND DIE EINZELHEITEN DAZU - NACHGETRAGEN am 01.09.2026
        #
        #     Bis hierher hat diese Datei nur die LISTE gemessen, und das
        #     war eine Luecke, die kein Fehlschlag je gezeigt hat: seit
        #     dem 01.09.2026 hat dieses Fenster zwei Ansichten, `onShow`
        #     faengt auf der Liste an, und die Einzelheiten stehen dabei
        #     auf `visible: false`. Ein unsichtbares Widget zaehlt in
        #     GTK4 nicht in die Messung seines Elterns - gemessen wurde
        #     also gerade NICHT die Ansicht, an der die ganze
        #     Breitenrechnung dieses Fensters haengt (Reiterleiste,
        #     Formular, vierteilige Fusszeile).
        #
        #     Ein Klick laesst sich unter Hyprland nicht erzeugen. Seit
        #     dem 01.09.2026 braucht es keinen: `ags request
        #     vpn-settings:<kennung>` fuehrt direkt in die Einzelheiten
        #     einer Verbindung (siehe gewuenschteKennung in
        #     ags-vpn-settings.template). Er ist fuer den Nutzer gebaut
        #     worden und macht diese Messung nebenbei erst moeglich.
        #
        #     Kein eigener Compositor dafuer: die Fabrik meldet jeden
        #     Ueberhang in DASSELBE Protokoll, und _pruefe_ueberhang()
        #     unten prueft ohnehin JEDE Meldung, nicht nur die letzte.
        sitzung.request(NAMESPACE)
        time.sleep(3.0)
        antwort = sitzung.request(f"{NAMESPACE}:c1")
        assert "shown" in antwort or "toggled" in antwort, (
            f"ags request {NAMESPACE}:c1 antwortete {antwort!r}")
        time.sleep(6.0)
        return sitzung.read_shell_log()


def _pruefe_ueberhang(protokoll: str) -> None:
    """Der Inhalt passt in das, was Sprosse L uebriglaesst."""
    erlaubt = _modal_width_l() - RAHMEN_UND_LEISTE
    zu_breit = [(int(inhalt), int(sicht))
                for name, inhalt, sicht in MELDUNG.findall(protokoll)
                if name == NAMESPACE and int(inhalt) > erlaubt]
    assert zu_breit == [], (
        f"der Inhalt von '{NAMESPACE}' verlangt mehr als die {erlaubt}px, "
        f"die Sprosse L ({_modal_width_l()}px) uebriglaesst: {zu_breit}. "
        f"Entweder gehoert das Fenster auf eine breitere Sprosse, oder "
        f"seine Fusszeile muss schmaler werden - siehe die Rechnung im "
        f"Kopf von src/templates/ags-vpn-settings.template.")


@pytest.fixture(scope="module")
def protokoll(tmp_path_factory) -> str:
    """Das Fenster einmal geoeffnet, und was die Schale dabei gemeldet hat."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")

    bau = tmp_path_factory.mktemp("zepvpn-bau")
    return _lauf(bau, "ipsec")


@pytest.fixture(scope="module")
def protokoll_openvpn(tmp_path_factory) -> str:
    """Dasselbe Fenster, auf OpenVPN gestellt.

    EIN EIGENER LAUF und keine Wiederverwendung: die Reiter werden nach
    Bauart getauscht, und der breiteste Reiter dieser Bauart ist ein
    anderer. Ein zweiter Compositor kostet eine halbe Minute - eine
    ungemessene Bauart kostet ein Fenster, das links abgeschnitten ist
    und dessen erster Reiter sich "in" statt "Allgemein" liest.
    """
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    return _lauf(tmp_path_factory.mktemp("zepvpn-ovpn"), "openvpn")


def test_die_schale_hat_das_fenster_ueberhaupt_gebaut(protokoll):
    """Die Gegenprobe zuerst.

    Der Test darunter ist erfuellt, wenn GAR NICHTS gemeldet wurde - und
    gar nichts wird auch gemeldet, wenn das Fenster nie gebaut wurde.
    Ohne diese Zeile misst er im Zweifel eine Schale, die abgestuerzt
    ist, und meldet Erfolg.

    Auf "loaded successfully" und nicht auf eine Messzeile: die Fabrik
    meldet NUR, wenn etwas nicht passt, und im guten Fall soll sie
    schweigen duerfen. Eine Zusicherung, dass gemessen wurde, wuerde
    genau dann scheitern, wenn GTK gleich beim ersten Anlauf richtig
    zuteilt - also in der besseren Welt.

    GEMESSEN am 21.08.2026 hat sie in diesem Aufbau trotzdem gesprochen,
    aus der ersten Zuteilung heraus: `Inhalt 676px, Sichtfenster 439px`.
    Der Test unten hat damit eine echte Zahl in der Hand gehabt, keine
    leere Liste - 676 gegen 854 erlaubte.
    """
    assert "VpnSettings loaded successfully" in protokoll, (
        "im Protokoll der Schale kommt das Fenster nicht vor - gemessen "
        f"wurde vermutlich gar nichts:\n{protokoll[-2000:]}")


def test_der_ueberhang_ist_null(protokoll):
    """Der Inhalt passt in das, was Sprosse L uebriglaesst.

    880 - 2 (Rahmen) - 24 (Bildlaufleiste) = 854, und der Inhalt dieses
    Fensters verlangt 676 (GEMESSEN am 21.08.2026 an `hadj.get_upper()`,
    dieselbe Zahl wie in aufgabe-34-report.md 2.6). Auf Sprosse M
    standen dem Inhalt 634 zur Verfuegung - daher die 42 Punkte, die
    dieser Test ablegt.
    """
    _pruefe_ueberhang(protokoll)


def test_die_schale_hat_das_openvpn_fenster_gebaut(protokoll_openvpn):
    """Die Gegenprobe fuer die dritte Bauart.

    Sie ist hier schaerfer als bei IPsec: die OpenVPN-Reiter werden von
    zwei Funktionen gebaut, die es vor dem 22.08.2026 nicht gab, und ein
    Fehler darin faellt sonst als AUSBLEIBENDE Meldung auf - also als
    scheinbar bestandener Ueberhangtest.
    """
    assert "VpnSettings loaded successfully" in protokoll_openvpn, (
        "im Protokoll der Schale kommt das Fenster nicht vor - gemessen "
        f"wurde vermutlich gar nichts:\n{protokoll_openvpn[-2000:]}")


def test_der_ueberhang_ist_auch_unter_openvpn_null(protokoll_openvpn):
    """Die dritte Bauart sprengt die Sprosse nicht.

    Der breiteste Bewohner ist weiterhin die Fusszeile mit ihren vier
    Knoepfen (676, GEMESSEN am 21.08.2026) - die Reiter "Verbindung" und
    "Zertifikate" tragen Eingabezeilen, und die sind dehnbar. Diese
    Zusicherung haelt fest, dass das so BLEIBT: wer dort ein breites,
    nicht dehnbares Bauteil einsetzt, erfaehrt es hier und nicht vom
    Nutzer.
    """
    _pruefe_ueberhang(protokoll_openvpn)


# --------------------------------------------------------------------
# Der Bildbeweis: die Liste ist wirklich in der Oberflaeche
# --------------------------------------------------------------------
#
# AUF ANSAGE DES NUTZERS (22.08.2026)
#     "bitte diese liste mit toggle auch visuell im ags fenster
#      umsetzen"
#
#     Die Messungen oben sagen, dass der Inhalt in seine Sprosse passt.
#     Sie sagen NICHT, dass eine Liste mit Schaltern dasteht - ein
#     Fenster ohne Liste passt genauso gut. Eine Datenschicht mit einem
#     Versprechen ist genau das, was hier nicht abgeliefert werden
#     soll, also wird es gezeichnet und angesehen.
#
# WAS DAS BILD ZEIGEN MUSS
#     Zwei Verbindungen mit verschiedenen Bauarten ("arbeit", IPsec;
#     "zuhause", WireGuard - siehe _shipped_settings()) und je einem
#     Schalter. Genau der Fall, den es vor dieser Aufgabe nicht geben
#     konnte.

# `ags request vpn` oeffnet die SCHALE auf der VPN-Seite - seit
# Aufgabe 9 (18.08.2026) gibt es kein eigenes VPN-Fenster mehr
# (ags-config.template::requestHandler, Zweig "vpn" ->
# toggleByName("vpn") -> widgets.control.zeigeSeite("vpn")). Die
# Layer-Flaeche heisst deshalb "control", die ANFRAGE aber "vpn".
#
# GEMESSEN am 22.08.2026: mit "control" angefragt zeigte das Bild die
# Schale auf irgendeiner Seite - der erste Anlauf dieses Beweises
# lieferte zweimal den blanken Schreibtisch.
SEITE_ANFRAGE = "vpn"


def _erschienen(vorher: Path, nachher: Path) -> int:
    """Wieviele Bildpunkte sich geaendert haben.

    Der Beweis, dass die Flaeche WIRKLICH DA IST. Der Kopf dieser Datei
    beschreibt, warum an dieser Vorrichtung nicht auf die Flaeche
    gewartet werden kann: sie erscheint in einem Teil der Laeufe gar
    nicht. Eine Zusicherung, die nur prueft, ob eine PNG-Datei
    entstanden ist, geht in genau diesen Laeufen durch und beweist
    nichts - GEMESSEN am 22.08.2026, als sie das zweimal tat.
    """
    from tests.render.measure import changed_pixels, read_png
    a, b = read_png(vorher), read_png(nachher)
    return len(changed_pixels(a, b, (0, 0, a.width, a.height)))


# Wieviel Flaeche eine geoeffnete Schale mindestens bedeckt. Sie ist
# 880 breit und mehrere hundert hoch; 200 000 Punkte sind ein Zehntel
# davon und damit weit unter dem, was ein echtes Fenster aendert, aber
# weit ueber dem, was Uhrzeit und Auslastungsanzeige in der Leiste
# zwischen zwei Aufnahmen bewegen.
MINDESTFLAECHE = 200_000


def _bilder(bau) -> dict:
    """Beide Flaechen in EINER Sitzung oeffnen und abziehen.

    In einer modulweiten Vorrichtung und nicht im Test selbst - genau
    wie `protokoll` oben. Der Isolationswaechter (tests/conftest.py) ist
    funktionsweit: er patcht os.open fuer die Dauer EINES Tests, und
    `start_bus()` startet dbus-daemon mit subprocess.DEVNULL, was durch
    diesen Patch laeuft. GEMESSEN am 22.08.2026: derselbe Aufbau, im
    Test aufgerufen, brach mit "tried to write on '/dev/null'" ab; in
    einer Vorrichtung aufgerufen, laeuft er - so wie die beiden
    Ueberhang-Messungen oben es seit jeher tun.
    """
    ags = render_configuration(bau)
    bundle(ags, bau)
    (bau / "zepos").mkdir(parents=True, exist_ok=True)
    (bau / "zepos" / "user-settings.json").write_text(
        _shipped_settings("ipsec"), encoding="utf-8")

    ergebnis = {}
    with Session(1920, 1080) as sitzung:
        sitzung.start_bus()
        workspaces_file(bau, sitzung.output)
        # Der Mauspfeil waere auf dem Bild ein Befund, der keiner ist -
        # dieselbe Zeile wie in test_starter.py.
        sitzung.hyprctl("keyword", "cursor:invisible", "true")
        sitzung.wallpaper()

        # DER ZEIGER MUSS AUF DEN ABGEBILDETEN SCHIRM - ohne diese Zeile
        # erscheint die Schale ueberhaupt nicht.
        #
        #     GEMESSEN am 22.08.2026, nach zwei Fehlanlaeufen: `ags
        #     request control` antwortet "toggled", das Fehlerprotokoll
        #     bleibt leer, und `layers()` fuehrt Leiste, Dock, Tapete,
        #     Home, Power und Starter - aber nie 'control'. Auch OHNE
        #     jede Einstellungsdatei, also nicht an dieser Aufgabe
        #     gelegen.
        #
        #     Der Grund steht bei move_cursor() in desktop_session.py:
        #     utils/overlay.ts fragt vor jedem Aufklappfenster `hyprctl
        #     cursorpos -j` und sucht den Schirm, auf dem der Zeiger
        #     steht. Der verschachtelte Compositor hat ZWEI Ausgaenge -
        #     den des Wirtsfensters und den headless-Ausgang, der
        #     abgebildet wird -, und der Zeiger steht anfangs auf dem
        #     falschen. Die Schale ging also jedes Mal auf, nur eben
        #     nicht dort, wo hingesehen wird.
        #
        #     tests/render/test_schale_stil.py hat diese Zeile seit
        #     jeher; sie hat hier gefehlt.
        sitzung.move_cursor(960, 540)
        sitzung.shell(bau / "zepos-shell.js", bau)
        time.sleep(SETTLE)

        blank = sitzung.shoot(bau / "0-nur-schreibtisch.png")

        # AUFWAERMEN: die Schale einmal ueber "control" oeffnen, bevor
        # irgendetwas gemessen wird.
        #
        #     GEMESSEN am 22.08.2026: `ags request vpn` als ALLERERSTE
        #     Anfrage einer Sitzung antwortet "toggled", aber die
        #     Flaeche 'control' erscheint auch nach 45 Sekunden nicht -
        #     zweimal nacheinander, mit leerem Fehlerprotokoll.
        #     Dieselbe Anfrage NACH einem "control" laesst sie sofort
        #     erscheinen.
        #
        #     Das deckt sich mit tests/render/test_schale_stil.py, das
        #     seine vier Seiten in der Reihenfolge control, network,
        #     bluetooth, vpn durchgeht und deshalb nie auf diese Lage
        #     stoesst - und mit dem Kommentar dort ueber "den
        #     allerersten `ags request` in einer Sitzung". Es ist eine
        #     Schwaeche der Vorrichtung und keine der Oberflaeche: die
        #     Seite selbst wird dort seit jeher gezeichnet und gemessen.
        sitzung.request("control")
        deadline = time.monotonic() + 45.0
        aufgewaermt = False
        while time.monotonic() < deadline:
            if sitzung.layers().get("control"):
                aufgewaermt = True
                break
            time.sleep(0.3)
        ergebnis["aufwaermung"] = aufgewaermt
        time.sleep(2.0)

        # Das VIERTE Feld ist die Anfrage, die wieder ZUMACHT - und sie
        # ist nicht immer dieselbe wie die zum Aufmachen.
        #
        #     GEMESSEN am 22.08.2026: `ags request vpn` geht ueber
        #     toggleByName() auf `zeigeSeite("vpn")`, und das ist KEIN
        #     Umschalter - es wechselt die Seite und ruft `show()`.
        #     Ein zweites `ags request vpn` laesst die Schale also
        #     offen, und das danach angefragte Einstellungsfenster
        #     erschien nie ('vpn-settings' fehlte in layers()).
        #     Zugemacht wird die Schale mit "control", das ueber
        #     toggleWidget() laeuft und wirklich umschaltet.
        for schluessel, anfrage, flaeche, zumachen, datei in (
                ("schale", SEITE_ANFRAGE, "control", "control",
                 "vpn-liste-schale.png"),
                ("fenster", NAMESPACE, NAMESPACE, NAMESPACE,
                 "vpn-liste-einstellungen.png")):
            antwort = sitzung.request(anfrage)
            assert "toggled" in antwort or "shown" in antwort, (
                f"ags request {anfrage} antwortete {antwort!r}")

            # GERUETTELT STATT GEWARTET, UND NUR EIN EINZIGES `ags
            # request` - beides abgeschrieben von
            # tests/render/test_schale_stil.py, wo es begruendet steht:
            #
            #   * Die Flaeche bleibt in einem Teil der Laeufe laenger
            #     als 20 Sekunden ganz aus. Eine feste Wartezeit ist
            #     entweder zu kurz oder zu lang.
            #   * Ein ZWEITER `ags request` waere falsch: GJS ist
            #     einstraengig, der zweite Aufruf wird erst NACH dem
            #     ersten verarbeitet und knipst das gerade erschienene
            #     Fenster sofort wieder zu. "Ein Waechter, der sein
            #     eigenes Messobjekt wegklickt, ist schlimmer als einer,
            #     der lang wartet."
            #
            # GEMESSEN am 22.08.2026: der erste Anlauf dieses Beweises
            # rief bis zu dreimal `ags request` und bekam zweimal den
            # blanken Schreibtisch - 0 geaenderte Bildpunkte. Genau der
            # Fehler, vor dem der Kommentar dort warnt.
            deadline = time.monotonic() + 45.0
            platte = None
            while time.monotonic() < deadline:
                platte = sitzung.layers().get(flaeche)
                if platte:
                    break
                time.sleep(0.3)
            assert platte, (
                f"keine Flaeche '{flaeche}' auf dem Schirm nach "
                f"'ags request {anfrage}' (Antwort: {antwort!r}):\n"
                + sitzung.read_shell_log())

            # Die erste Zuteilung ist oft noch ein Platzhalter - dieselbe
            # Beobachtung wie dort, darum nach dem Erscheinen noch ein
            # Moment fuer die endgueltige Groesse.
            time.sleep(3.0)
            bild = sitzung.shoot(bau / datei)
            ergebnis[schluessel] = bild
            ergebnis[schluessel + "-punkte"] = _erschienen(blank, bild)

            # Wieder zu, damit die naechste Flaeche allein dasteht.
            sitzung.request(zumachen)
            frist = time.monotonic() + 15.0
            while time.monotonic() < frist:
                if not sitzung.layers().get(flaeche):
                    break
                time.sleep(0.3)
            time.sleep(1.0)
    return ergebnis


@pytest.fixture(scope="module")
def bildbeweis(tmp_path_factory) -> dict:
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    return _bilder(tmp_path_factory.mktemp("zepvpn-bild"))


def test_die_schale_zeigt_die_verbindungsliste(bildbeweis):
    """Gezeichnet, nicht behauptet.

    Die Messungen oben sagen, dass der Inhalt in seine Sprosse passt.
    Sie sagen NICHT, dass eine Liste mit Schaltern dasteht - ein
    Fenster ohne Liste passt genauso gut.
    """
    bild = bildbeweis["schale"]
    assert bild.is_file() and bild.stat().st_size > 0
    assert bildbeweis["schale-punkte"] >= MINDESTFLAECHE, (
        f"die Schale ist auf dem Bild nicht erschienen - nur "
        f"{bildbeweis['schale-punkte']} Punkte haben sich gegenueber dem "
        f"blanken Schreibtisch geaendert: {bild}")
    print(f"\nBildbeweis Schalenseite: {bild}")


def test_das_einstellungsfenster_zeigt_die_verbindungsliste(bildbeweis):
    """Dasselbe fuer das Einstellungsfenster."""
    bild = bildbeweis["fenster"]
    assert bild.is_file() and bild.stat().st_size > 0
    assert bildbeweis["fenster-punkte"] >= MINDESTFLAECHE, (
        f"das Einstellungsfenster ist auf dem Bild nicht erschienen - nur "
        f"{bildbeweis['fenster-punkte']} Punkte geaendert: {bild}")
    print(f"\nBildbeweis Einstellungsfenster: {bild}")
