# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Startmenue einer INSTALLIERTEN Maschine - und der Weg des Themas
dorthin, wo GRUB es lesen kann.

WAS HIER GEPRUEFT WIRD, UND WARUM DURCH AUSFUEHREN
    Der Nutzer hat viermal gemeldet, dass das Menue seiner Installation
    nicht seins ist: der Name stimmte ("ZepOS Linux"), das Aussehen war
    nacktes GNU GRUB. Auf dem Medium war dasselbe Menue gethemt.

    Am 17.08.2026 wurde die Ursache am Abbild der Installation gemessen
    (iso/out/release-target.img). Alle Glieder der Kette waren da - das
    Thema unter /usr/share/grub/themes/zepos mit theme.txt, das Drop-in
    /etc/default/grub.d/10-zepos.cfg, ein grub, dessen grub-mkconfig das
    Drop-in-Verzeichnis liest, und der zweite grub-mkconfig-Lauf aus
    installer/core/translate.py, dreizehn Sekunden nach der
    Paketinstallation. Die erzeugte /boot/grub/grub.cfg enthielt
    trotzdem null Zeilen mit `theme`.

    Die Bedingung, die fehlte, ist die dritte in /etc/grub.d/00_header
    (grub 2:2.14-1, Zeile 272-273):

        if [ "x$GRUB_THEME" != x ] && [ -f "$GRUB_THEME" ] \\
            && is_path_readable_by_grub "$GRUB_THEME"; then

    is_path_readable_by_grub verwirft jeden Pfad, dessen
    Abstraktionsliste `cryptodisk` enthaelt, solange
    GRUB_ENABLE_CRYPTODISK nicht `y` ist:

        $ grub-probe -t abstraction .../usr/share/grub/themes/zepos/theme.txt
        cryptodisk
        luks2
        gcry_rijndael
        gcry_rijndael
        gcry_sha256

    Die Wurzel einer ZepOS-Installation ist verschluesselt, also war
    alles darauf fuer grub-mkconfig unlesbar - das Thema und, als
    Gegenprobe, auch /usr/share/grub/unicode.pf2, weshalb dieselbe
    grub.cfg nur den Rueckfall `if loadfont unicode ; then` bekam.

    Der Fehler war damit ein Pfad, und ein falscher Pfad meldet sich
    NICHT. GRUB antwortet auf ein unlesbares Thema mit dem Textmodus und
    ohne Fehler, grub-mkconfig schweigt, und die einzige Spur ist eine
    Datei, in der etwas fehlt. Genau die Sorte Fehler, gegen die ein
    Test hilft, der ausfuehrt statt liest - dieselbe Begruendung wie im
    Kopf von tests/boot/test_plymouth.py.

WAS DIESE DATEI NICHT KANN
    Sie kann kein Bild machen. Ob auf dem Schirm ein gethemtes Menue
    steht, entscheidet ein Lauf in QEMU:

        ./iso/test-boot.py --scenario release-install
        ./iso/test-boot.py --scenario release-installed

    und das Bild heisst dort 00-startmenue. Diese Datei haelt die
    Fehler ab, die man ohne zehn Minuten QEMU abhalten kann.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

SPIEGEL = REPO / "src/boot/zepos-grub-theme"
HAKEN = REPO / "src/boot/zepos-grub-theme.hook"
DROPIN = REPO / "src/boot/grub-zepos.cfg"

# Das Themenverzeichnis, aus dem packaging/build.sh das Paket fuellt.
# Eine Kopie im Baum, zwei Ziele - packaging/build.sh sagt, warum es aus
# dem ISO-Profil kommt und nicht aus src/.
PROFIL_THEMA = REPO / "iso/profile-release/grub/themes/zepos"


def _lies(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8")


def _grub_theme() -> str:
    """Der Pfad, auf den das Drop-in GRUB_THEME setzt."""
    treffer = re.search(r"^GRUB_THEME=(\S+)\s*$", _lies(DROPIN), re.M)
    assert treffer, "das Drop-in nennt kein Thema"
    return treffer.group(1)


def _fake_wurzel(tmp_path: Path, *, mit_grub: bool = True) -> Path:
    """Eine Wurzel, wie der Haken sie im Chroot vorfindet.

    Das Thema kommt aus dem ISO-Profil und wird nicht erfunden: ein Test,
    der sich seine eigenen Dateien schreibt, prueft seine eigene
    Abschrift, und die Zahl der Dateien ist genau das, was der Spiegel
    hinterher vergleicht.
    """
    wurzel = tmp_path / "wurzel"
    quelle = wurzel / "usr/share/grub/themes/zepos"
    quelle.mkdir(parents=True)
    for datei in sorted(PROFIL_THEMA.iterdir()):
        if datei.is_file():
            (quelle / datei.name).write_bytes(datei.read_bytes())
    # Die Schriften liegen im Paket unter f/, weil 00_header nur dort und
    # im Themenverzeichnis selbst nach *.pf2 sucht (Zeile 281).
    schriften = quelle / "f"
    schriften.mkdir()
    for datei in sorted((REPO / "iso/profile-release/grub/fonts").glob("*.pf2")):
        (schriften / datei.name).write_bytes(datei.read_bytes())
    if mit_grub:
        (wurzel / "boot/grub").mkdir(parents=True)
    return wurzel


def _spiegeln(wurzel: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(SPIEGEL)],
        env={"PATH": "/usr/bin:/bin", "ZEPOS_WURZEL": str(wurzel)},
        capture_output=True, text=True, check=False,
    )


# ---------------------------------------------------------------------
# Der Pfad, an dem alles haengt.
# ---------------------------------------------------------------------

def test_das_thema_liegt_auf_einem_dateisystem_das_grub_lesen_kann():
    """Die eine Zeile, die den Fehler des 17.08.2026 ausmachte.

    /usr/share liegt auf der Wurzel, und die Wurzel einer
    ZepOS-Installation ist verschluesselt. is_path_readable_by_grub
    verwirft von dort alles, und 00_header ueberspringt daraufhin den
    ganzen Themenblock - ohne Fehler, ohne Warnung, ohne eine Zeile in
    grub.cfg.

    /boot ist per Definition das Dateisystem, aus dem GRUB liest: dort
    liegt grub.cfg, dort liegen die Module. Ein Thema dort ist damit das
    einzige, das die Bedingung ueberhaupt erfuellen KANN.
    """
    thema = _grub_theme()
    assert thema.startswith("/boot/"), (
        f"GRUB_THEME={thema} liegt nicht unter /boot - auf einer "
        "verschluesselten Wurzel liest grub-mkconfig von dort nichts")
    assert not thema.startswith("/usr/"), (
        "genau dieser Pfad war der Fehler, den der Nutzer viermal gemeldet hat")


def test_der_spiegel_schreibt_genau_dorthin_wohin_das_dropin_zeigt():
    """Die Naht zwischen zwei Dateien, die nichts voneinander wissen.

    Das Drop-in nennt einen Pfad, das Skript legt Dateien ab. Gehen die
    zwei auseinander, zeigt GRUB_THEME auf ein leeres Verzeichnis - und
    das faellt niemandem auf, weil GRUB dazu schweigt.
    """
    thema = _grub_theme()
    verzeichnis = thema.rsplit("/", 1)[0]
    quelle = _lies(SPIEGEL)
    assert 'ziel="$grubdir/themes/zepos"' in quelle
    assert 'grubdir="$wurzel/boot/grub"' in quelle
    assert verzeichnis == "/boot/grub/themes/zepos", (
        f"das Drop-in zeigt auf {verzeichnis}, der Spiegel schreibt nach "
        "/boot/grub/themes/zepos")


# ---------------------------------------------------------------------
# Und der Spiegel selbst, ausgefuehrt.
# ---------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_der_spiegel_legt_das_thema_vollstaendig_nach_boot(tmp_path):
    """Vollstaendig, nicht nur theme.txt.

    GRUB zeichnet ein Thema, dessen background.png oder dessen Schrift
    fehlt, als Textmenue - ohne Fehler. Eine halbe Kopie ist damit
    dasselbe Bild wie gar keine.
    """
    wurzel = _fake_wurzel(tmp_path)
    lauf = _spiegeln(wurzel)
    assert lauf.returncode == 0, lauf.stderr

    quelle = wurzel / "usr/share/grub/themes/zepos"
    ziel = wurzel / "boot/grub/themes/zepos"
    assert (ziel / "theme.txt").is_file(), lauf.stderr

    erwartet = sorted(p.relative_to(quelle) for p in quelle.rglob("*") if p.is_file())
    bekommen = sorted(p.relative_to(ziel) for p in ziel.rglob("*") if p.is_file())
    assert bekommen == erwartet
    assert erwartet, "das ISO-Profil traegt kein Thema mehr"

    # Die Schriften kommen mit, und sie kommen unter f/ an: 00_header
    # sucht nur in "$themedir"/*.pf2 und "$themedir"/f/*.pf2.
    assert sorted((ziel / "f").glob("*.pf2")), (
        "ohne die PF2-Schriften bekaeme theme.txt fuer 'Roboto Regular 24' "
        "keine Zuordnung, und GRUB zeichnete ein Textmenue")


@pytest.mark.allow_subprocess
def test_der_spiegel_raeumt_weg_was_aus_dem_thema_verschwindet(tmp_path):
    """Eine Aktualisierung, die eine Datei entfernt, muss sie auch unter
    /boot entfernen - sonst liegt dort ein Gemisch aus zwei Themen."""
    wurzel = _fake_wurzel(tmp_path)
    ziel = wurzel / "boot/grub/themes/zepos"
    ziel.mkdir(parents=True)
    (ziel / "von-gestern.png").write_bytes(b"alt")

    lauf = _spiegeln(wurzel)
    assert lauf.returncode == 0, lauf.stderr
    assert not (ziel / "von-gestern.png").exists()
    assert (ziel / "theme.txt").is_file()


@pytest.mark.allow_subprocess
def test_der_spiegel_legt_nichts_an_wo_kein_grub_ist(tmp_path):
    """Wo /boot/grub fehlt, bootet die Maschine ueber etwas anderes.

    Ein Themenverzeichnis unter /boot waere dort Muell, den niemand mehr
    wegraeumt - und ein `mkdir -p` auf ein nicht eingehaengtes /boot
    schriebe ihn auf die Wurzel.
    """
    wurzel = _fake_wurzel(tmp_path, mit_grub=False)
    lauf = _spiegeln(wurzel)
    assert lauf.returncode == 0, lauf.stderr
    assert not (wurzel / "boot/grub").exists()


@pytest.mark.allow_subprocess
def test_der_spiegel_endet_nie_mit_einem_fehler(tmp_path):
    """pacman meldet eine Transaktion als fehlgeschlagen, wenn ein Haken
    mit != 0 endet.

    Ein Startmenue ohne Thema ist haesslich; ein `pacman -Syu`, das
    mittendrin abbricht, ist ein halb aktualisiertes System. Derselbe
    Grund wie bei GRUB_MKCONFIG_COMMAND in installer/core/translate.py,
    nur mit einem anderen Preis.
    """
    leer = tmp_path / "leer"
    leer.mkdir()
    lauf = _spiegeln(leer)
    assert lauf.returncode == 0, (
        "ein Haken, der scheitert, laesst pacman die Transaktion abbrechen")
    assert "theme.txt" in lauf.stderr, (
        "und er sagt nicht, was fehlt - dann sucht es hinterher niemand")


@pytest.mark.allow_subprocess
def test_der_spiegel_endet_auch_dann_mit_null_wenn_das_kopieren_scheitert(tmp_path):
    """Der zweite Ausgang, und der teurere.

    Eine volle oder nicht beschreibbare EFI-Partition ist kein
    erfundener Fall - 512 MB, und Kernel und Initramfs liegen darauf.
    Mit `set -e` verliesse das Skript hier den Rueckgabewert von `cp`,
    und pacman meldete die ganze Transaktion als fehlgeschlagen: der
    Preis fuer ein Bild waere ein halb aktualisiertes System.
    """
    wurzel = _fake_wurzel(tmp_path)
    grubdir = wurzel / "boot/grub"
    grubdir.chmod(0o555)
    try:
        lauf = _spiegeln(wurzel)
    finally:
        grubdir.chmod(0o755)
    assert lauf.returncode == 0, (
        "ein gescheitertes Kopieren darf die pacman-Transaktion nicht "
        f"mitnehmen: {lauf.stdout}{lauf.stderr}")
    assert "ZepOS:" in lauf.stderr, (
        "und es muss gesagt werden, sonst sucht es hinterher niemand")


# ---------------------------------------------------------------------
# Der Haken, der ihn ausloest.
# ---------------------------------------------------------------------

def test_der_haken_feuert_bei_installation_und_aktualisierung():
    """Bei beiden.

    Nur Install liesse jede Aktualisierung mit einem veralteten Thema
    unter /boot zurueck; nur Upgrade liesse jede frische Installation
    ohne eins - und das ist genau der Fall, den der Nutzer gemeldet hat.
    """
    haken = _lies(HAKEN)
    assert re.search(r"^Type = Path\s*$", haken, re.M)
    assert re.search(r"^Operation = Install\s*$", haken, re.M)
    assert re.search(r"^Operation = Upgrade\s*$", haken, re.M)
    assert re.search(r"^Target = usr/share/grub/themes/zepos/\*\s*$", haken, re.M)
    assert re.search(r"^When = PostTransaction\s*$", haken, re.M), (
        "PreTransaction liefe, bevor die neuen Dateien liegen")
    assert re.search(r"^Exec = /usr/bin/zepos-grub-theme\s*$", haken, re.M)


def test_der_haken_raeumt_beim_entfernen_nicht_auf():
    """pacman fasst ein Upgrade als Remove+Install an.

    Ein `Operation = Remove` liefe damit bei jeder Aktualisierung mit und
    loeschte die Kopie, die die Install-Haelfte gerade angelegt hat.
    """
    assert not re.search(r"^Operation = Remove\s*$", _lies(HAKEN), re.M)


# ---------------------------------------------------------------------
# Und die zwei Zeilen im Drop-in, die es ohne das Thema auch nicht taete.
# ---------------------------------------------------------------------

def test_das_dropin_schaltet_gfxterm_ein():
    """00_header umschliesst den ganzen Themenblock mit
    `if [ "x$gfxterm" = x1 ]`, und gfxterm wird nur gesetzt, wenn
    GRUB_TERMINAL_INPUT oder GRUB_TERMINAL_OUTPUT das Wort "gfxterm"
    enthaelt. Arch liefert die Variable auskommentiert aus."""
    assert re.search(r"^GRUB_TERMINAL_OUTPUT=gfxterm\s*$", _lies(DROPIN), re.M)


def test_das_dropin_setzt_keine_kryptoplatte_frei():
    """Der Ausweg, der keiner ist.

    GRUB_ENABLE_CRYPTODISK=y machte /usr/share wieder lesbar - und
    setzte eine zweite Passphrase-Abfrage VOR das Menue, in nacktem Text
    und mit einer argon2id-Ableitung, die GRUB in Software rechnet. Der
    Nutzer tippte die Passphrase dann zweimal, die erste davon in genau
    dem schwarzen Kasten, den dieses Thema ersetzen soll.
    """
    assert not re.search(r"^GRUB_ENABLE_CRYPTODISK=", _lies(DROPIN), re.M)


@pytest.mark.parametrize("datei", [SPIEGEL, HAKEN, DROPIN])
def test_die_dateien_gibt_es(datei):
    assert datei.is_file(), f"{datei} fehlt"
