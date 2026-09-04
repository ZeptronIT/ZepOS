# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Schirm kommt dazu - und alles, was daraus folgt, wird nachgezogen.

WAS GEMELDET WURDE (04.09.2026), WOERTLICH
    "bei anschliessen eines weiteren bildschirm wird der background
     schwarz und wenn ich verusche allgemein ags sachen dort zu machen
     erscheinen die fenster nur auf der edp also dem laptop monitor und
     sie werdne nicht als getrennte instanzen behandelt"

WAS DAHINTER STECKT - EINE URSACHE, DREI SYMPTOME
    Drei Dinge werden aus "welche Schirme haengen dran" abgeleitet, und
    alle drei standen bis zum 04.09.2026 als `exec-once` in
    hyprland-universal-config.template - sie liefen also GENAU EINMAL,
    beim Anmelden:

        swaybg je Ausgang            wallpaper-manager restore   (251)
        hypr/workspaces-             hypr-monitor-detect.sh      (171)
        generated.conf
        ags/workspaces.json          bar-workspace-detect.sh     (172)

    Ein Schirm, der spaeter dazukommt, bekommt deshalb kein swaybg (er
    ist SCHWARZ) und keine Arbeitsflaeche (jede liegt weiter auf dem
    ersten Schirm - wer auf dem neuen etwas oeffnet, springt zurueck).
    Das Zweite ist die Antwort auf "die fenster erscheinen nur auf der
    edp": es geht um Arbeitsflaechen und nicht um Fenster.

    Was einem Schirm FOLGT, sind allein die Layer-Flaechen der
    Oberflaeche - jeSchirm() in ags-kit.template, seit 0.1.13, gemessen
    in tests/render/test_mehrschirm.py. Genau deshalb sah der Nutzer die
    Leiste auf dem neuen Schirm und trotzdem einen unbrauchbaren Schirm.

WAS HIER GEMESSEN WIRD, UND WAS NICHT
    Gemessen wird, was der Waechter TUT: dass nach dem Anstecken ein
    swaybg fuer den neuen Ausgang laeuft, dass beide Dateien ihn nennen,
    und dass Hyprland zum Neulesen aufgefordert wurde.

    NICHT gemessen wird, ob Hyprland eine gesourcte Datei danach
    anwendet. Das ist seine dokumentierte Eigenschaft und keine unsere;
    der verschachtelte Compositor hier laeuft ausserdem mit der
    Konfiguration, die desktop_session.py schreibt, und die sourct
    workspaces-generated.conf nicht.

DER AUFRUFZAEHLER FUER hyprctl
    `reload` hinterlaesst keine Spur, die man von aussen lesen kann.
    Deshalb liegt ein hyprctl im PATH, das jeden Aufruf mitschreibt und
    dann das echte an seinem absoluten Pfad ausfuehrt - dasselbe
    Verfahren wie in tests/src/test_new_templates.py. Ohne das
    Weiterreichen misst der Lauf einen Waechter, der nichts erfaehrt.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.render.desktop_session import (                      # noqa: E402
    SRC, WALLPAPER, Session, _processor, required_tools,
)

BREITE, HOEHE = 1920, 1080

# Wie lange dem Waechter gelassen wird. Er entprellt (siehe die Vorlage),
# ruft danach drei Skripte, und `wallpaper-manager restore` faengt selbst
# mit `sleep 1` an.
NACHZUG = 12.0

# Die vier Vorlagen und wohin generate_config.sh sie legt. Ausgeschrieben
# und nicht aus dem Generator gelesen: eine Liste, die sich aus dem
# Generator ergibt, ist mit jedem Generator einverstanden - auch mit
# einem, der den Waechter gar nicht mehr kennt.
SKRIPTE = {
    "hypr-monitor-detect-config": ".config/hypr/hypr-monitor-detect.sh",
    "bar-workspace-detect-config": ".config/ags/bar-workspace-detect.sh",
    "wallpaper-manager-config": ".local/bin/wallpaper-manager",
    "hypr-monitor-watch-config": ".config/hypr/hypr-monitor-watch.py",
}

pytestmark = pytest.mark.allow_subprocess


def _lege_die_skripte(heim: Path) -> None:
    """Die vier erzeugten Skripte dorthin, wo sie im Betrieb liegen.

    Sie rechnen ihre eigenen Pfade aus $HOME und $XDG_CONFIG_HOME aus -
    ein Skript, das woanders liegt, schreibt woandershin, und der Lauf
    messe dann seinen eigenen Aufbau.
    """
    verarbeiter = _processor()
    for name, ziel in SKRIPTE.items():
        quelle = SRC / "templates" / f"{name}.template"
        assert quelle.is_file(), f"{quelle} fehlt"
        pfad = heim / ziel
        pfad.parent.mkdir(parents=True, exist_ok=True)
        verarbeiter.apply_template(quelle, pfad)
        pfad.chmod(0o755)


def _hyprctl_mitschrift(heim: Path) -> tuple[Path, Path]:
    """Ein hyprctl im PATH, das mitschreibt und weiterreicht.

    Zurueck kommen das Verzeichnis fuer den PATH und die Datei mit den
    Aufrufen, eine Zeile je Aufruf.
    """
    echtes = shutil.which("hyprctl")
    assert echtes, "hyprctl liegt nicht im PATH"
    stelle = heim / "aufrufe"
    stelle.mkdir(parents=True, exist_ok=True)
    mitschrift = stelle / "hyprctl.log"
    stummel = stelle / "hyprctl"
    stummel.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "$*" >> {mitschrift}\n'
        f'exec {echtes} "$@"\n',
        encoding="utf-8")
    stummel.chmod(0o755)

    # UND EIN zepos-generate DANEBEN, sonst misst der Lauf den Rueckfall.
    #
    #     hypr-monitor-detect.sh holt die Aufteilung aus
    #     `zepos-generate --monitors` (src/cli.py -> monitors.main). Auf
    #     einem Rechner ohne installiertes ZepOS scheitert der Aufruf,
    #     das Skript nimmt seinen Rueckfall - "alle zehn
    #     Arbeitsflaechen auf den ERSTEN Schirm" - und ein neuer Schirm
    #     kommt dort nie vor. GEMESSEN am 04.09.2026: genau so war der
    #     erste Lauf dieser Datei rot, und zwar an einer Luecke des
    #     Messstands und nicht am Erzeugnis.
    #
    #     Der Stummel ruft GENAU die Datei, die das Paket nach
    #     /usr/bin legt (src/bin/zepos-generate) - sie findet ihre
    #     Module selbst, wenn cli.py neben ihrem Verzeichnis liegt.
    erzeuger = stelle / "zepos-generate"
    erzeuger.write_text(
        "#!/bin/bash\n"
        f'exec python3 {ROOT / "src" / "bin" / "zepos-generate"} "$@"\n',
        encoding="utf-8")
    erzeuger.chmod(0o755)
    return stelle, mitschrift


def _swaybg_ausgaenge(display: str) -> list[str]:
    """Welche Ausgaenge in DIESER Sitzung ein swaybg haben.

    Ueber /proc und nicht ueber `pgrep -a swaybg`: auf der Maschine, die
    diesen Lauf ausfuehrt, laeuft die Sitzung eines Menschen mit ihren
    eigenen swaybg-Prozessen. Ein Name aus der falschen Sitzung waere
    ein Befund ueber den falschen Rechner - und zwar ein gruener.
    """
    marke = f"WAYLAND_DISPLAY={display}".encode()
    gefunden: list[str] = []
    for eintrag in Path("/proc").iterdir():
        if not eintrag.name.isdigit():
            continue
        try:
            argumente = (eintrag / "cmdline").read_bytes().split(b"\0")
            if not argumente or not argumente[0].endswith(b"swaybg"):
                continue
            if marke not in (eintrag / "environ").read_bytes().split(b"\0"):
                continue
        except OSError:
            continue          # der Prozess ist zwischendurch gegangen
        worte = [wort.decode() for wort in argumente if wort]
        if "-o" in worte:
            stelle = worte.index("-o")
            if stelle + 1 < len(worte):
                gefunden.append(worte[stelle + 1])
    return sorted(gefunden)


def _schirme(sitzung: Session) -> list[str]:
    return sorted(monitor["name"]
                  for monitor in (sitzung.hyprctl_json("monitors") or []))


def _steck_an(sitzung: Session, timeout: float = 20.0) -> str:
    vorher = set(_schirme(sitzung))
    ergebnis = sitzung.hyprctl("output", "create", "headless")
    assert ergebnis.returncode == 0, (
        f"kein weiterer headless-Ausgang: {ergebnis.stdout}{ergebnis.stderr}")
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        neu = sorted(set(_schirme(sitzung)) - vorher)
        if neu:
            return neu[0]
        time.sleep(0.2)
    raise AssertionError(
        f"der angesteckte Ausgang ist nicht erschienen: {_schirme(sitzung)}")


def _bericht(nachgezogen: dict) -> str:
    """Was bei einem Fehlschlag zu lesen ist, in EINEM Stueck.

    Das Protokoll des Waechters zuerst: es sagt, ob er das Ereignis
    gesehen hat, ob er dieselben Schirme fand und was die vier Schritte
    gemeldet haben. Ohne es bliebe die Frage "hat er nichts getan oder
    hat es nicht gewirkt" offen.
    """
    return ("\n--- Waechter ---\n" + nachgezogen["waechter_log"][-3000:]
            + "\n--- Anmelden ---\n" + nachgezogen["anmelden_log"][-1500:]
            + "\n--- Oberflaeche ---\n" + nachgezogen["protokoll"][-1000:])


def _lies(pfad: Path) -> str:
    try:
        return pfad.read_text(encoding="utf-8")
    except OSError:
        return ""


def _lauf(tmp_path_factory, mit_waechter: bool) -> dict:
    """Anmelden, wahlweise den Waechter starten, einen Schirm anstecken."""
    fehlt = required_tools()
    if fehlt:
        pytest.skip(f"fuer den Bildlauf fehlt: {', '.join(fehlt)}")
    if not shutil.which("jq"):
        pytest.skip("jq fehlt - wallpaper-manager kann ohne es nichts lesen")

    with Session(BREITE, HOEHE) as sitzung:
        heim = sitzung.home
        _lege_die_skripte(heim)
        stelle, mitschrift = _hyprctl_mitschrift(heim)

        # Eine gewaehlte Tapete, damit `restore` den Zweig nimmt, den
        # eine benutzte Installation nimmt - und nicht den Rueckfall auf
        # das ausgelieferte Bild.
        (heim / ".cache").mkdir(parents=True, exist_ok=True)
        (heim / ".cache" / "current-wallpaper").write_text(
            f"{WALLPAPER}\n", encoding="utf-8")

        umgebung = {
            "HYPRLAND_INSTANCE_SIGNATURE": sitzung.signature() or "",
            # Der Stummel VOR allem anderen, und ein eigenes TMPDIR:
            # wallpaper-manager legt seine Drossel unter $TMPDIR ab, und
            # die des Menschen an diesem Rechner ist nicht unsere.
            "PATH": f"{stelle}:{os.environ.get('PATH', '/usr/bin')}",
            "TMPDIR": str(heim / "tmp"),
        }
        (heim / "tmp").mkdir(parents=True, exist_ok=True)

        # KEINE ROEHRE, SONDERN EINE DATEI - und das ist gemessen.
        #
        #     Mit `capture_output=True` blieb dieser Aufbau 120 Sekunden
        #     an `wallpaper-manager restore` haengen: `restore` startet
        #     swaybg mit `&` und `disown`, das Kind erbt die Roehre, und
        #     gelesen wird bis zum Dateiende - das bei einem Dienst nie
        #     kommt. Derselbe Fehler stand im Waechter, siehe fuehre()
        #     in hypr-monitor-watch-config.template.
        anmeldelog = heim / "anmelden.log"

        def lauf(*befehl: str) -> subprocess.CompletedProcess:
            with anmeldelog.open("ab") as senke:
                return subprocess.run(
                    list(befehl), stdin=subprocess.DEVNULL, stdout=senke,
                    stderr=subprocess.STDOUT, timeout=120,
                    env=sitzung.environment(**umgebung))

        # ---- das Anmelden, wie exec-once es fuehrt ------------------
        detect = lauf("bash", str(heim / SKRIPTE["hypr-monitor-detect-config"]))
        leiste = lauf("bash",
                      str(heim / SKRIPTE["bar-workspace-detect-config"]))
        tapete = lauf("bash", str(heim / SKRIPTE["wallpaper-manager-config"]),
                      "restore")

        arbeitsflaechen = heim / ".config" / "hypr" / "workspaces-generated.conf"
        leisten_datei = heim / ".config" / "ags" / "workspaces.json"

        vorher = {
            "schirme": _schirme(sitzung),
            "swaybg": _swaybg_ausgaenge(sitzung.display or ""),
            "arbeitsflaechen": _lies(arbeitsflaechen),
            "leiste": _lies(leisten_datei),
        }

        # ---- der Waechter, wie exec-once ihn startet ----------------
        waechter = None
        if mit_waechter:
            waechter = sitzung.spawn(
                ["python3", str(heim / SKRIPTE["hypr-monitor-watch-config"])],
                **umgebung)

        # Ihm einen Augenblick lassen, bevor das Ereignis kommt - eine
        # Verbindung, die erst nach dem Anstecken steht, hoert es nie.
        time.sleep(2.0)
        mitschrift.write_text("", encoding="utf-8")   # ab hier zaehlt es

        dazu = _steck_an(sitzung)
        time.sleep(NACHZUG)

        nachher = {
            "schirme": _schirme(sitzung),
            "swaybg": _swaybg_ausgaenge(sitzung.display or ""),
            "arbeitsflaechen": _lies(arbeitsflaechen),
            "leiste": _lies(leisten_datei),
        }

        aufrufe = [zeile for zeile in _lies(mitschrift).splitlines() if zeile]
        waechter_log = _lies(
            Path(sitzung.runtime) / "zepos-monitor-watch.log")
        anmelden_text = _lies(anmeldelog)
        laeuft_noch = waechter is not None and waechter.poll() is None
        protokoll = sitzung.read_shell_log()

    return {
        "mit_waechter": mit_waechter,
        "dazu": dazu, "vorher": vorher, "nachher": nachher,
        "aufrufe": aufrufe, "laeuft_noch": laeuft_noch,
        "protokoll": protokoll,
        "waechter_log": waechter_log,
        "anmelden_log": anmelden_text,
        "anmelden": {
            "detect": detect.returncode,
            "leiste": leiste.returncode,
            "tapete": tapete.returncode,
        },
    }


@pytest.fixture(scope="module")
def nachgezogen(tmp_path_factory) -> dict:
    """Mit Waechter - so, wie eine Installation seit 0.1.19 laeuft."""
    return _lauf(tmp_path_factory, mit_waechter=True)


@pytest.fixture(scope="module")
def ohne_waechter(tmp_path_factory) -> dict:
    """OHNE Waechter - der Zustand, den der Nutzer gemeldet hat.

    Derselbe Ablauf, nur dass der Waechter nicht laeuft. Ohne diese
    Gegenprobe waere nicht zu unterscheiden, ob die Messungen darueber
    den Waechter messen oder etwas, das ohnehin passiert - und genau
    dieser Verdacht ist begruendet: eines der Drei kann seine Ausgaenge
    von sich aus nachziehen, wenn man es nur laesst.
    """
    return _lauf(tmp_path_factory, mit_waechter=False)


# --------------------------------------------------------------------
# Die Grundlage: das Anmelden selbst muss gesessen haben
# --------------------------------------------------------------------

def test_das_anmelden_hat_die_drei_schritte_gefuehrt(nachgezogen):
    """Ohne sie sagte "nach dem Anstecken steht es da" nichts.

    Ein Lauf, in dem schon das Anmelden nichts geschrieben hat, kann den
    Nachzug nicht von ihm unterscheiden.
    """
    assert nachgezogen["anmelden"] == {"detect": 0, "leiste": 0, "tapete": 0}, (
        f"die drei Schritte des Anmeldens: {nachgezogen['anmelden']}\n"
        + _bericht(nachgezogen))

    vorher = nachgezogen["vorher"]
    assert vorher["swaybg"], (
        "nach dem Anmelden laeuft in dieser Sitzung kein einziges swaybg "
        "mit -o - dann misst dieser Lauf die Tapete nicht.\n"
        + _bericht(nachgezogen))
    assert "workspace=" in vorher["arbeitsflaechen"], (
        f"workspaces-generated.conf traegt keine Zuordnung: "
        f"{vorher['arbeitsflaechen'][:400]!r}")
    assert vorher["leiste"].strip(), "workspaces.json der Leiste ist leer"


# --------------------------------------------------------------------
# Der neue Schirm, drei Symptome
# --------------------------------------------------------------------

def test_der_neue_schirm_bekommt_eine_tapete(nachgezogen):
    """SYMPTOM A, woertlich: "wird der background schwarz".

    Ein Ausgang ohne swaybg zeigt das Schwarz des Compositors. Gemessen
    wird nicht das Bild, sondern der Prozess mit `-o <name>`: das Bild
    eines headless-Ausgangs sagt nichts darueber, WARUM es schwarz ist.
    """
    dazu = nachgezogen["dazu"]
    assert dazu in nachgezogen["nachher"]["swaybg"], (
        f"fuer den angesteckten Ausgang {dazu} laeuft kein swaybg - er ist "
        f"schwarz. Vorhanden: {nachgezogen['nachher']['swaybg']}, vor dem "
        f"Anstecken: {nachgezogen['vorher']['swaybg']}\n"
        + _bericht(nachgezogen))


def test_der_neue_schirm_bekommt_arbeitsflaechen(nachgezogen):
    """SYMPTOM B, woertlich: "erscheinen die fenster nur auf der edp ...
    sie werdne nicht als getrennte instanzen behandelt".

    Nennt workspaces-generated.conf den neuen Ausgang nicht, dann liegt
    jede Arbeitsflaeche weiter auf dem ersten Schirm - und wer auf dem
    neuen etwas oeffnet, landet auf dem alten.
    """
    dazu = nachgezogen["dazu"]
    text = nachgezogen["nachher"]["arbeitsflaechen"]
    assert f"monitor:{dazu}" in text, (
        f"workspaces-generated.conf ordnet {dazu} keine Arbeitsflaeche zu:\n"
        f"{text[:600]}\n"
        + _bericht(nachgezogen))


def test_hyprland_wird_zum_neulesen_aufgefordert(nachgezogen):
    """Eine geschriebene Datei ist noch keine angewandte Zuordnung.

    Hyprland sourct workspaces-generated.conf (hyprland-universal-
    config.template:47). Ohne ein `reload` steht die neue Zuordnung auf
    der Platte und die alte im Compositor.
    """
    reloads = [ruf for ruf in nachgezogen["aufrufe"]
               if ruf.split() and ruf.split()[0] == "reload"]
    assert reloads, (
        f"nach dem Anstecken kein `hyprctl reload`. Was gerufen wurde: "
        f"{nachgezogen['aufrufe'][:20]}\n"
        + _bericht(nachgezogen))


def test_die_leiste_erfaehrt_von_dem_neuen_schirm(nachgezogen):
    """Und die Arbeitsflaechenknoepfe muessen dasselbe wissen.

    Weiss die Leiste es nicht, zeigt sie Knoepfe fuer eine Aufteilung,
    die es nicht mehr gibt - der Fehler, den der Kopf von
    bar-workspace-detect-config.template beschreibt ("workspace buttons
    on a screen where the windows never appear").
    """
    dazu = nachgezogen["dazu"]
    assert dazu in nachgezogen["nachher"]["leiste"], (
        f"workspaces.json der Leiste nennt {dazu} nicht:\n"
        f"{nachgezogen['nachher']['leiste'][:600]}\n"
        + _bericht(nachgezogen))


def test_der_waechter_ueberlebt_den_wechsel(nachgezogen):
    """Ein Waechter, der beim ersten Ereignis stirbt, zieht genau einmal
    nach - und der zweite Schirm des Tages ist wieder schwarz."""
    assert nachgezogen["laeuft_noch"], (
        "der Waechter lief nach dem Anstecken nicht mehr:\n"
        + _bericht(nachgezogen))


# --------------------------------------------------------------------
# Der Gegenbeweis: ohne den Waechter bleibt der neue Schirm liegen
# --------------------------------------------------------------------

def test_ohne_waechter_bleibt_der_neue_schirm_schwarz(ohne_waechter):
    """Der gemeldete Zustand, nachgestellt.

    Laeuft der Waechter nicht, dann hat der angesteckte Ausgang kein
    swaybg - niemand hat eines fuer ihn gestartet, und `restore` lief
    zuletzt, als es ihn noch nicht gab.

    DAS IST DIE ZUSICHERUNG, DIE DIE ANDEREN ERST ZU MESSUNGEN MACHT.
    Waere sie gruen, dann waere auch das Gruen darueber ohne Aussage.
    """
    dazu = ohne_waechter["dazu"]
    assert dazu not in ohne_waechter["nachher"]["swaybg"], (
        f"ohne Waechter hat {dazu} trotzdem ein swaybg "
        f"({ohne_waechter['nachher']['swaybg']}) - dann zieht etwas anderes "
        f"nach, und die Messungen darueber messen nicht den Waechter.\n"
        + _bericht(ohne_waechter))


def test_ohne_waechter_bekommt_der_neue_schirm_keine_arbeitsflaeche(
        ohne_waechter):
    """Und die zweite Haelfte: keine Arbeitsflaeche, also liegt jede
    weiter auf dem ersten Schirm. Das ist "nur auf der edp"."""
    dazu = ohne_waechter["dazu"]
    assert f"monitor:{dazu}" not in ohne_waechter["nachher"]["arbeitsflaechen"], (
        f"ohne Waechter ordnet workspaces-generated.conf {dazu} trotzdem "
        f"eine Arbeitsflaeche zu - dann schreibt es jemand anders, und die "
        f"Messung darueber sagt nichts.\n" + _bericht(ohne_waechter))


def test_ohne_waechter_wird_hyprland_nicht_aufgefordert(ohne_waechter):
    """Kein `reload`, also bleibt im Compositor stehen, was war."""
    reloads = [ruf for ruf in ohne_waechter["aufrufe"]
               if ruf.split() and ruf.split()[0] == "reload"]
    assert not reloads, (
        f"ohne Waechter wurde Hyprland dennoch zum Neulesen aufgefordert: "
        f"{reloads}\n" + _bericht(ohne_waechter))
