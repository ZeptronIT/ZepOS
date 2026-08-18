# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Paket zepos-claude-code - das Rezept, der Eintrag, der Starter.

DREI BEFUNDE VOM 17.08.2026, und der erste ist der teuerste.

1. DAS AUSGELIEFERTE /usr/bin/claude WAR NICHT CLAUDE CODE
   GEMELDET: "wenn ich claude im terminal eingeben will kommt claude is
   a fast javascript bla bla und claude selber wird nicht gestartet".

   Das ist die Hilfe von bun - dem Laufzeitsystem, mit dem Claude Code
   uebersetzt ist. GEMESSEN an der entschluesselten Wurzel der letzten
   Installation (iso/out/release-target.img):

       aus dem Tarball    324598064 Bytes  "not stripped"
           --version  ->  2.1.233 (Claude Code)
       aus dem Paket      324542688 Bytes  "stripped"
           --version  ->  1.4.0                    <- bun

   Und der Beweis, dass strip dazwischen liegt: `strip --strip-all` auf
   eine Kopie der Tarball-Datei ergibt Byte fuer Byte die Datei aus dem
   Paket - sha256 c8530870039bf80b50a7cca258919e47a4c3d05b8e86d34f405bd
   92c0c176a8c auf beiden Seiten.

   Eine mit `bun build --compile` erzeugte Datei traegt das uebersetzte
   Programm an sich; strip raeumt weg, was zu keinem geladenen Abschnitt
   gehoert, und uebrig bleibt der blanke bun. makepkg strippt von sich
   aus - `strip` steht in Arch' OPTIONS, und packaging/Dockerfile haengt
   nur `!debug` an.

2. DER KLICK IM STARTER ZEIGTE NICHTS
   `Exec=kitty -e claude` bindet das Fenster an das Programm. GEMESSEN
   an der ausgelieferten Binaerdatei: `claude --gibtsnicht` schreibt
   EINE Zeile und gibt 1 zurueck - im Dock ein Fenster, das aufblitzt
   und weg ist. --hold waere die falsche Antwort: es haelt auch nach
   einem gewollten Ende offen.

3. ZWEI EINTRAEGE IM DOCK WAREN NICHT ZU UNTERSCHEIDEN
   GEMESSEN am Abnahmebild
   iso/out/run-release-installed/key-41-15-super-q-terminal.png: das
   Terminal (Icon=kitty) und Claude Code (Icon=utilities-terminal)
   zeigen beide ">_" in einem dunklen Kasten.

WAS HIER GELESEN UND WAS AUSGEFUEHRT WIRD
    Das Rezept wird gelesen - ein Paketbau braucht Docker, root und
    einen Tarball von 310 MiB, und tests/packaging/test_recipes.py
    begruendet in seinem Kopf, warum das in dieser Suite nicht
    stattfindet. Der STARTER dagegen wird ausgefuehrt, mit einem echten
    Pseudoterminal: ob ein Fenster offen bleibt, ist eine Frage an das
    laufende Skript und nicht an seinen Text.
"""
import os
import pty
import re
import select
import subprocess
import time
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
PAKET = REPOSITORY / "packaging" / "zepos-claude-code"
REZEPT = PAKET / "PKGBUILD"
EINTRAG = PAKET / "zepos-claude-code.desktop"
STARTER = PAKET / "zepos-claude-code"


def _feld(text: str, name: str) -> str:
    treffer = re.search(rf"^{name}=(.*)$", text, re.M)
    assert treffer, f"{name}= fehlt in {EINTRAG.name}"
    return treffer.group(1).strip()


# --------------------------------------------------------------------
# 1. Das Rezept
# --------------------------------------------------------------------

def test_the_recipe_forbids_the_step_that_turned_the_assistant_into_bun():
    """options=('!strip'), und der Grund daneben.

    Ohne diese Zeile baut makepkg ein Paket, das sich installieren,
    starten und im Dock anzeigen laesst - und beim Tippen von `claude`
    die Hilfe eines JavaScript-Laufzeitsystems ausgibt. Kein
    Bauwerkzeug meldet dabei etwas.
    """
    rezept = REZEPT.read_text(encoding="utf-8")
    treffer = re.search(r"^options=\((.*)\)$", rezept, re.M)
    assert treffer, "das Rezept setzt kein options="
    assert "!strip" in treffer.group(1), (
        f"options={treffer.group(1)} enthaelt kein !strip - makepkg "
        "strippt dann wieder, und /usr/bin/claude ist wieder bun")


def test_the_reason_for_that_option_is_written_where_it_stands():
    """Eine Option ohne Begruendung ist eine, die der naechste
    Aufraeumlauf entfernt. Hier steht die Messung daneben - beide
    Versionsnummern, die den Unterschied ausmachen."""
    rezept = REZEPT.read_text(encoding="utf-8")
    kopf = rezept.split("options=(")[0]
    for wort in ("bun", "strip", "1.4.0", "2.1.233"):
        assert wort in kopf, (
            f"'{wort}' steht nicht in der Begruendung ueber options=")


def test_the_default_makepkg_configuration_really_does_strip():
    """Die Voraussetzung des ganzen Befunds, auf diesem Rechner
    nachgesehen: `strip` steht in Arch' Vorgabe. Steht es dort eines
    Tages nicht mehr, ist die Option oben harmlos - aber der Kommentar
    daneben waere falsch, und ein falscher Kommentar ist schlimmer als
    keiner."""
    conf = Path("/etc/makepkg.conf")
    if not conf.is_file():
        pytest.skip("kein /etc/makepkg.conf auf diesem Rechner")
    treffer = re.search(r"^OPTIONS=\((.*)\)$", conf.read_text(encoding="utf-8"),
                        re.M)
    assert treffer, "/etc/makepkg.conf setzt kein OPTIONS="
    assert re.search(r"(^|\s)strip(\s|$)", treffer.group(1)), treffer.group(1)


def test_the_starter_is_a_source_and_reaches_usr_bin():
    """Eine Datei, die im Baum liegt und in keinem source= steht, kommt
    beim Bau nicht in $srcdir an - und package() bricht ab. Und eine, die
    package() nicht installiert, kommt nicht auf die Maschine."""
    rezept = REZEPT.read_text(encoding="utf-8")
    quellen = re.search(r"^source=\((.*?)\)$", rezept, re.M | re.S)
    assert quellen, "das Rezept setzt kein source="
    assert '"zepos-claude-code"' in quellen.group(1), (
        "der Starter steht nicht in source=")

    pruefsummen = re.search(r"^sha512sums=\((.*?)\)$", rezept, re.M | re.S)
    assert pruefsummen, "das Rezept setzt kein sha512sums="
    assert (len(re.findall(r"'[^']*'", pruefsummen.group(1)))
            == len(re.findall(r'"[^"]*"', quellen.group(1)))), (
        "source= und sha512sums= sind unterschiedlich lang - makepkg "
        "bricht damit ab, bevor irgendetwas gebaut wird")

    assert re.search(
        r'install -Dm755 "\$srcdir/zepos-claude-code" \\\n\s*'
        r'"\$pkgdir/usr/bin/zepos-claude-code"', rezept), (
        "package() legt den Starter nicht ausfuehrbar nach /usr/bin")


def test_the_package_revision_moved_with_its_contents():
    """Dieselbe Fassung von Claude Code, ein anderes Paket. Bliebe pkgrel
    stehen, saehe pacman auf einer schon installierten Maschine kein
    Update - und das kaputte Paket bliebe liegen."""
    rezept = REZEPT.read_text(encoding="utf-8")
    treffer = re.search(r"^pkgrel=(\d+)$", rezept, re.M)
    assert treffer, "kein pkgrel im Rezept"
    assert int(treffer.group(1)) >= 2, (
        "pkgrel steht noch auf dem Stand des Pakets, das bun ausgeliefert "
        "hat")


# --------------------------------------------------------------------
# 2. Der Eintrag im Starter
# --------------------------------------------------------------------

def test_the_entry_goes_through_the_starter_and_not_straight_to_claude():
    text = EINTRAG.read_text(encoding="utf-8")
    exec_zeile = _feld(text, "Exec")
    assert exec_zeile.split() == [
        "kitty", "--class", "zepos-claude-code", "-e", "zepos-claude-code"], (
        f"Exec={exec_zeile} - ein Fenster, das mit claude endet, zeigt "
        "eine Fehlerzeile nicht lange genug; und ohne --class heisst das "
        "Fenster 'kitty' und steht ein zweites Mal im Dock")
    assert "--hold" not in exec_zeile, (
        "--hold haelt das Fenster auch nach einem gewollten Ende offen")
    assert _feld(text, "TryExec") == "/usr/bin/zepos-claude-code"


def test_the_entry_no_longer_wears_the_terminal_s_icon():
    """Der Eintrag steht neben dem Terminal im Dock. Traegt er dessen
    Zeichen, ist er nicht der Eintrag eines Programms, sondern ein
    zweites Terminal."""
    symbol = _feld(EINTRAG.read_text(encoding="utf-8"), "Icon")
    assert symbol not in ("utilities-terminal", "utilities-x-terminal",
                          "terminal", "kitty"), (
        f"Icon={symbol} ist wieder ein Terminalzeichen")


def test_the_entry_does_not_claim_to_be_a_terminal_emulator():
    """Dieselbe Verwechslung eine Ebene tiefer. TerminalEmulator ist die
    Kategorie, in der eine Arbeitsumgebung nachsieht, wenn sie "das
    Terminal" oeffnen will. Claude Code IST keines - es laeuft in
    einem."""
    kategorien = _feld(EINTRAG.read_text(encoding="utf-8"),
                       "Categories").split(";")
    assert "TerminalEmulator" not in kategorien, kategorien
    assert "Development" in kategorien, kategorien


# Der Test hier HIESS bis zum 17.08.2026
# test_that_icon_exists_in_the_theme_the_session_sets und sah in
# Papirus-Dark nach, ob das Thema den Namen kennt. Diese Frage ist seit
# demselben Tag die falsche: das Paket bringt sein Zeichen jetzt SELBST
# mit, und Papirus kennt es folglich nicht - so wenig, wie es irgendein
# anderes Programm kennt, das seine eigene Marke mitliefert.
#
# Ersetzt und nicht gelockert: gefragt wird weiter, ob der Name aufloest,
# nur eben dort, wo er jetzt aufloesen MUSS. Und zwei Dinge, die die
# alte Fassung gar nicht pruefen konnte, kommen dazu - dass die Dateien
# ueberhaupt da sind, und dass ihre Kantenlaenge zu dem Verzeichnis
# passt, in das sie das Rezept legt. Ein 64er Bild in 256x256/apps ist
# ein unscharfer Fleck, und kein Bauwerkzeug meldet das.

def _png_kantenlaenge(pfad: Path) -> tuple[int, int]:
    """Breite und Hoehe aus dem IHDR, ohne Bildbibliothek.

    Ein PNG faengt mit acht Bytes Signatur an, dann kommt die Laenge des
    ersten Blocks, dann sein Name (IHDR), dann Breite und Hoehe als je
    vier Bytes, hoechstwertiges zuerst.
    """
    rohdaten = pfad.read_bytes()
    assert rohdaten[:8] == b"\x89PNG\r\n\x1a\n", f"{pfad.name} ist kein PNG"
    assert rohdaten[12:16] == b"IHDR", f"{pfad.name} faengt nicht mit IHDR an"
    return (int.from_bytes(rohdaten[16:20], "big"),
            int.from_bytes(rohdaten[20:24], "big"))


def test_the_package_brings_its_own_icon_along():
    """Der Symbolname im Eintrag und die Dateinamen im Rezept sind
    dieselbe Zeichenkette - sonst ist es ein leerer Kasten."""
    symbol = _feld(EINTRAG.read_text(encoding="utf-8"), "Icon")
    rezept = REZEPT.read_text(encoding="utf-8")

    assert symbol == "zepos-claude-code", (
        f"Icon={symbol} - das Paket legt sein Zeichen unter dem Namen "
        "zepos-claude-code ab")
    assert f"apps/{symbol}.png" in rezept, (
        f"das Rezept installiert kein apps/{symbol}.png - der Eintrag "
        "zeigt dann auf einen Namen, den niemand ablegt")
    assert "icons/hicolor/" in rezept, (
        "das Zeichen gehoert nach hicolor: der Satz, aus dem JEDES Thema "
        "holt, was es selbst nicht hat")
    # Der PFAD und nicht das Wort: "Papirus" steht im Rezept auch dort,
    # wo begruendet ist, warum das Zeichen NICHT dorthin geht.
    assert "icons/Papirus" not in rezept, (
        "ein Zeichen in ein fremdes Thema zu legen veraendert dieses Thema")


def test_that_icon_is_no_longer_the_robot_arm():
    """GEMELDET am 17.08.2026: "ich will das das logo von claude benutzt
    wird statt ein roboter arm". applications-engineering IST in
    Papirus-Dark ein Roboterarm."""
    symbol = _feld(EINTRAG.read_text(encoding="utf-8"), "Icon")
    assert symbol != "applications-engineering", (
        "der Roboterarm ist zurueck")


def test_every_declared_size_is_there_and_is_that_size():
    """Die Groessen aus dem Rezept, an den Dateien nachgemessen."""
    rezept = REZEPT.read_text(encoding="utf-8")
    treffer = re.search(r"^_zeichen_groessen=\((.*)\)$", rezept, re.M)
    assert treffer, "das Rezept nennt keine _zeichen_groessen"
    groessen = [int(w) for w in treffer.group(1).split()]
    assert groessen, "die Liste der Groessen ist leer"

    for groesse in groessen:
        bild = PAKET / f"claude-code-{groesse}.png"
        assert bild.is_file(), (
            f"{bild.name} fehlt - das Rezept nennt die Groesse {groesse}, "
            "der Bau braeche also ab")
        assert _png_kantenlaenge(bild) == (groesse, groesse), (
            f"{bild.name} misst {_png_kantenlaenge(bild)} und nicht "
            f"{groesse}x{groesse} - im Verzeichnis {groesse}x{groesse}/apps "
            "waere das ein unscharfer Fleck")


def test_the_source_array_carries_every_icon_the_package_installs():
    """Was package() aus $srcdir liest, muss in source= stehen.

    Eine Datei, die nur im Verzeichnis liegt, ist beim Bauen nicht da -
    makepkg verlinkt ausschliesslich, was in source= genannt ist.
    """
    rezept = REZEPT.read_text(encoding="utf-8")
    quellen = re.search(r"^source=\((.*?)\)$", rezept, re.M | re.S)
    assert quellen, "das Rezept setzt kein source="
    treffer = re.search(r"^_zeichen_groessen=\((.*)\)$", rezept, re.M)
    assert treffer
    for groesse in treffer.group(1).split():
        assert f"claude-code-{groesse}.png" in quellen.group(1), (
            f"claude-code-{groesse}.png fehlt in source= - package() "
            "liest es aus $srcdir, wo es dann nicht liegt")


# --------------------------------------------------------------------
# 3. Der Starter, ausgefuehrt
# --------------------------------------------------------------------

def _stub(tmp_path: Path, koerper: str | None) -> Path:
    """Ein Verzeichnis, das als GANZER PATH dient. Liegt darin kein
    `claude`, ist das der Fall "nicht installiert"."""
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    if koerper is not None:
        stub = stubs / "claude"
        stub.write_text("#!/bin/sh\n" + koerper, encoding="utf-8")
        stub.chmod(0o755)
    return stubs


def _am_terminal(stubs: Path, eingabe: bytes = b"\n") -> tuple[int, str]:
    """Den Starter an einem echten Pseudoterminal laufen lassen.

    Ohne Terminal kann `read` nicht warten - die Frage "bleibt das
    Fenster offen" waere dann gar nicht gestellt. Die Eingabe liegt vor
    dem Start in der Leitung; die Zeilendisziplin haelt sie, bis jemand
    liest.
    """
    haupt, neben = pty.openpty()
    prozess = subprocess.Popen(
        [str(STARTER)], stdin=neben, stdout=neben, stderr=neben,
        env={"PATH": str(stubs)}, close_fds=True)
    os.close(neben)
    os.write(haupt, eingabe)

    gesehen = b""
    ende = time.time() + 60
    while time.time() < ende:
        bereit, _, _ = select.select([haupt], [], [], 0.5)
        if bereit:
            try:
                stueck = os.read(haupt, 4096)
            except OSError:      # EIO: das Kind hat das Terminal losgelassen
                break
            if not stueck:
                break
            gesehen += stueck
        elif prozess.poll() is not None:
            break
    os.close(haupt)
    return prozess.wait(timeout=30), gesehen.decode("utf-8", "replace")


@pytest.mark.allow_subprocess
def test_a_failure_keeps_the_window_open_and_names_the_exit_code(tmp_path):
    """Der eigentliche Auftrag. GEMESSEN an der echten Binaerdatei:
    `claude --gibtsnicht` -> eine Zeile, Rueckgabewert 1. Ohne diesen
    Starter waere die Zeile mit dem Fenster weg."""
    stubs = _stub(tmp_path, 'echo "error: unknown option" >&2\nexit 1\n')
    ende, gesehen = _am_terminal(stubs)
    assert ende == 1, f"der Rueckgabewert des Programms geht verloren: {ende}"
    assert "error: unknown option" in gesehen
    assert "Rueckgabewert 1" in gesehen, gesehen
    assert "Eingabetaste" in gesehen, gesehen


@pytest.mark.allow_subprocess
def test_the_window_really_waits_instead_of_only_saying_so(tmp_path):
    """Die Frage ist nicht, ob der Satz dasteht, sondern ob jemand ihn
    lesen KANN.

    Gemessen wird ohne Eingabe: nachdem die Frage auf dem Terminal
    steht, muss der Prozess noch leben. Ein Starter, der die Zeile
    druckt und im selben Atemzug endet, faellt hier durch - und genau
    das ist der Unterschied, den ein Test ueber den Text allein nicht
    sieht.
    """
    stubs = _stub(tmp_path, "exit 1\n")
    haupt, neben = pty.openpty()
    prozess = subprocess.Popen(
        [str(STARTER)], stdin=neben, stdout=neben, stderr=neben,
        env={"PATH": str(stubs)}, close_fds=True)
    os.close(neben)
    try:
        gesehen = ""
        ende = time.time() + 30
        while "Eingabetaste" not in gesehen and time.time() < ende:
            bereit, _, _ = select.select([haupt], [], [], 0.5)
            if not bereit:
                continue
            try:
                gesehen += os.read(haupt, 4096).decode("utf-8", "replace")
            except OSError:
                break
        assert "Eingabetaste" in gesehen, gesehen

        # Ein halber Wimpernschlag, damit ein Prozess, der nach dem
        # Drucken sofort endet, das auch getan haben KANN, bevor
        # gemessen wird. Ohne diese Pause waere ein bestandener Test eine
        # gewonnene Wettlaufbedingung.
        time.sleep(0.5)
        assert prozess.poll() is None, (
            "der Starter war schon fertig, als die Frage dastand - das "
            "Fenster haette sich mit ihr geschlossen")

        os.write(haupt, b"\n")
        assert prozess.wait(timeout=30) == 1
    finally:
        if prozess.poll() is None:
            prozess.kill()
            prozess.wait(timeout=30)
        os.close(haupt)


@pytest.mark.allow_subprocess
def test_a_normal_end_closes_the_window_without_a_word(tmp_path):
    """Die Haelfte, die `--hold` nicht kann. Nach einem gewollten Ende
    darf nichts stehenbleiben - weder ein totes Terminal noch eine
    Frage."""
    stubs = _stub(tmp_path, 'echo fertig\nexit 0\n')
    ende, gesehen = _am_terminal(stubs)
    assert ende == 0
    assert "Eingabetaste" not in gesehen, (
        f"das Fenster fragt nach einem gewollten Ende nach: {gesehen}")


@pytest.mark.allow_subprocess
def test_an_interrupt_is_a_deliberate_end_too(tmp_path):
    """130 ist 128+SIGINT: Strg+C. Wer abbricht, hat entschieden - da
    braucht niemand eine Taste zu druecken, um ein Fenster loszuwerden,
    das er gerade selbst beendet hat."""
    stubs = _stub(tmp_path, "exit 130\n")
    ende, gesehen = _am_terminal(stubs)
    assert ende == 130
    assert "Eingabetaste" not in gesehen, gesehen


@pytest.mark.allow_subprocess
def test_a_missing_claude_says_so_instead_of_blinking(tmp_path):
    """Der Fall nach `pacman -Rdd zepos-claude-code`: der Eintrag im
    Menue ueberlebt das Programm. 127 ist der Wert, mit dem jede Schale
    "command not found" meldet."""
    stubs = _stub(tmp_path, None)
    ende, gesehen = _am_terminal(stubs)
    assert ende == 127
    assert "nicht installiert" in gesehen, gesehen
    assert "Eingabetaste" in gesehen, gesehen


@pytest.mark.allow_subprocess
def test_the_starter_hands_its_arguments_through(tmp_path):
    """`zepos-claude-code --version` muss claude erreichen. Ein Starter,
    der Argumente frisst, ist einer, den niemand von Hand benutzen
    kann."""
    stubs = _stub(tmp_path, 'printf "%s\\n" "$@"\nexit 0\n')
    prozess = subprocess.run(
        [str(STARTER), "--eins", "zwei drei"],
        env={"PATH": str(stubs)}, capture_output=True, text=True, timeout=60)
    assert prozess.returncode == 0, prozess.stderr
    assert prozess.stdout.splitlines() == ["--eins", "zwei drei"], (
        prozess.stdout)


@pytest.mark.allow_subprocess
def test_without_a_terminal_nothing_waits(tmp_path):
    """Aus einem Skript heraus gibt es niemanden, der eine Taste
    druecken kann. Ein `read` ohne Eingabe kaeme sofort zurueck, die
    Meldung stuende trotzdem da - also wird sie dort gar nicht erst
    gedruckt."""
    stubs = _stub(tmp_path, "exit 1\n")
    # input="" und nicht stdin=DEVNULL: die Isolationswache dieser Suite
    # verbietet ein Oeffnen von /dev/null zum Schreiben, und eine Roehre
    # mit sofortigem Dateiende ist fuer `[ -t 0 ]` genau derselbe Fall -
    # kein Terminal.
    prozess = subprocess.run(
        [str(STARTER)], input="",
        env={"PATH": str(stubs)}, capture_output=True, text=True, timeout=60)
    assert prozess.returncode == 1
    assert "Eingabetaste" not in prozess.stdout + prozess.stderr


def test_the_starter_is_executable_in_the_tree():
    """makepkg uebernimmt den Modus aus install -Dm755, aber ein Skript,
    das im Baum nicht ausfuehrbar ist, kann diese Datei auch nicht
    messen."""
    assert os.access(STARTER, os.X_OK), f"{STARTER} ist nicht ausfuehrbar"


# --------------------------------------------------------------------
# 4. Ein Programm, ein Knopf
# --------------------------------------------------------------------
# GEMELDET am 17.08.2026: "ich sehe das claude roboter icon auch zweimal
# in der taskleiste".
#
# Es gab nie zwei Eintraege - im ganzen Baum liegt genau eine
# .desktop-Datei fuer Claude Code. Der zweite Knopf war das FENSTER: das
# Dock vergleicht die Klasse eines Fensters mit dem Programmnamen, der
# Kennung des Eintrags und StartupWMClass (belongsTo() in
# src/templates/ags-dock.template), und ein Fenster, das zu keiner
# angehefteten Anwendung passt, bekommt einen eigenen Knopf.
#
# `kitty -e zepos-claude-code` erzeugt ein Fenster der Klasse `kitty`,
# und /proc/<pid>/comm sagt ebenfalls `kitty` - beide Wege des Docks
# fuehrten zur selben falschen Antwort. Der Eintrag konnte sein eigenes
# Fenster nicht als seines erkennen.

def _dock_vergleichsformen(text: str) -> set[str]:
    """Die drei Formen, gegen die belongsTo() eine Fensterklasse haelt.

    Nachgebaut aus src/templates/ags-dock.template - Programmname,
    Kennung des Eintrags ohne .desktop, StartupWMClass. Wer die Funktion
    dort aendert, muss diese Liste mitaendern, und der Test daneben sagt,
    woran man das merkt.
    """
    formen = {"zepos-claude-code"}          # Programmname = Dateiname
    treffer = re.search(r"^StartupWMClass=(.*)$", text, re.M)
    if treffer:
        formen.add(treffer.group(1).strip())
    return formen


def test_the_window_it_opens_can_be_recognised_as_its_own():
    """Die Klasse, die das Fenster traegt, muss eine der Vergleichsformen
    sein - sonst steht dasselbe Programm zweimal im Dock."""
    text = EINTRAG.read_text(encoding="utf-8")
    exec_teile = _feld(text, "Exec").split()

    assert "--class" in exec_teile, (
        "Exec setzt keine Fensterklasse - kitty nennt das Fenster dann "
        "'kitty' (Vorgabe laut kitty 0.48.2), und das Dock kann es dem "
        "Eintrag nicht zuordnen")
    klasse = exec_teile[exec_teile.index("--class") + 1]

    assert klasse in _dock_vergleichsformen(text), (
        f"das Fenster heisst '{klasse}', aber das Dock vergleicht gegen "
        f"{sorted(_dock_vergleichsformen(text))} - es bekaeme einen "
        "eigenen Knopf neben dem angehefteten")


def test_that_recognition_does_not_hang_on_one_argument_alone():
    """StartupWMClass sagt dasselbe fuer jeden anderen Leser.

    Eine Zuordnung, die nur funktioniert, weil eine Exec-Zeile ein
    bestimmtes Argument traegt, zerfaellt beim naechsten Umbau der
    Exec-Zeile still - und "still" heisst hier: ein zweiter Knopf im
    Dock, den niemand mit der Aenderung in Verbindung bringt.
    """
    text = EINTRAG.read_text(encoding="utf-8")
    treffer = re.search(r"^StartupWMClass=(.*)$", text, re.M)

    assert treffer, "StartupWMClass fehlt"
    exec_teile = _feld(text, "Exec").split()
    klasse = exec_teile[exec_teile.index("--class") + 1]
    assert treffer.group(1).strip() == klasse, (
        f"StartupWMClass={treffer.group(1).strip()} und --class {klasse} "
        "sagen Verschiedenes - dann stimmt je nach Leser das eine oder "
        "das andere nicht")


def test_the_dock_still_compares_against_what_this_test_assumes():
    """Der Nachbau oben gegen das Original gehalten.

    _dock_vergleichsformen() ist eine Abschrift, und eine Abschrift
    veraltet. Bricht dieser Test, hat jemand belongsTo() geaendert - dann
    gehoert die Abschrift nachgezogen und nicht dieser Test entfernt.
    """
    dock = (REPOSITORY / "src" / "templates" / "ags-dock.template").read_text(
        encoding="utf-8")
    koerper = re.search(r"function belongsTo\b.*?\n}", dock, re.S)
    assert koerper, "belongsTo() ist in ags-dock.template nicht mehr zu finden"

    for form in ("program", "get_id", "get_startup_wm_class"):
        assert form in koerper.group(0), (
            f"belongsTo() vergleicht nicht mehr ueber {form} - die "
            "Abschrift in _dock_vergleichsformen() stimmt nicht mehr")
