# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Eingabezeile: dass sie da ist, und dass sie der Marke gehoert.

GEMELDET am 12.08.2026: "es soll irgendwie die moeglichkeit geben
powerlevel 10k einzurichten das theme fuer ein terminal voll automatisch
und andere themes auch."

GEMESSEN, und der Befund war der unangenehme: die EINRICHTUNG war da,
das Eingerichtete nicht.

    zshrc-config.template setzte ZSH_THEME="powerlevel10k/powerlevel10k",
    sourcte $ZSH/oh-my-zsh.sh und sourcte ~/.p10k.zsh. Keins der drei
    Stuecke existierte auf einer Installation: oh-my-zsh steht in keinem
    Arch-Repository (nur in der AUR), zsh-theme-powerlevel10k steht im
    angehefteten Schnappschuss 2026/08/04 ebenfalls nicht mehr, und
    ~/.p10k.zsh wurde von nichts erzeugt.

    Was eine erste Anmeldung wirklich bekam - `zsh -i` mit der erzeugten
    ~/.zshrc in einem leeren Heimatverzeichnis:

        ~/.zshrc:90: no such file or directory: ~/.oh-my-zsh/oh-my-zsh.sh
        PROMPT=[%m%# ]

    Dieselbe Fehlerklasse wie der Zwischenablage-Sammler vom selben Tag:
    ein Stueck, das auf ein anderes wartet, das niemand hinstellt.

DIE FALLE, DIE DIESE DATEI UMGEHT
    `"oh-my-zsh" in datei` ist auch dann wahr, wenn der Name nur in
    einem Kommentar steht - und der Kopf von zshrc-config.template
    ERZAEHLT ausfuehrlich von oh-my-zsh, weil er begruenden muss, warum
    es weg ist. Jede Zusicherung unten laeuft deshalb gegen
    _code(), also gegen den Text ohne ganzzeilige Kommentare. Dieselbe
    Vorsichtsmassnahme, die tests/packaging/test_recipes.py mit seinem
    _code() trifft, und aus demselben Anlass: dort hat eine
    Mutationsprobe gezeigt, dass '#'cage'' die Pruefung gruen liess.

WAS HIER NICHT BEANTWORTET WERDEN KANN
    Ob powerlevel10k mit dieser Datei wirklich einen Prompt zeichnet -
    dafuer muss das Theme auf der Maschine liegen. Der letzte Test unten
    tut genau das, sobald es da ist (das Paket legt es unter
    /usr/share/zsh-theme-powerlevel10k ab), und laesst sich sonst mit
    ZEPOS_P10K_ROOT auf einen ausgepackten Quellbaum zeigen. Gemessen
    wurde damit am 12.08.2026 gegen v1.20.0: die erzeugte Datei bringt
    einen zweizeiligen Prompt hervor, dessen %F{...}-Farben genau die
    sieben Rollen sind.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
TEMPLATES = SRC / "templates"
PACKAGING = REPOSITORY / "packaging"

ENV = "/usr/bin/env"

# Die Pfade der Pakete, an genau der Stelle, an der die erzeugte
# ~/.zshrc sie nennt. Sie stehen hier ein zweites Mal, damit eine
# Aenderung an einer der beiden Seiten auffaellt statt durchzugehen.
THEME_FILE = "/usr/share/zsh-theme-powerlevel10k/powerlevel10k.zsh-theme"
PLUGIN_FILES = (
    "/usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh",
    "/usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh",
)

# Jeder POWERLEVEL9K-Name, den p10k-config.template setzt, nach
# Klammer-Aufloesung. NACHGEMESSEN am 12.08.2026 gegen powerlevel10k
# v1.20.0 - dem Stand, den packaging/zsh-theme-powerlevel10k/PKGBUILD
# pinnt: jeder Name kommt entweder woertlich in config/*.zsh oder in
# internal/p10k.zsh vor, oder er wird dort aus Teilen zusammengesetzt
# (_p9k_param baut POWERLEVEL9K_<SEGMENT>_<ZUSTAND>_<SUFFIX> und faellt
# auf POWERLEVEL9K_<SEGMENT>_<SUFFIX> zurueck).
#
# WOZU DIE ZAHL DA IST: ein Name, den p10k nicht liest, tut nichts und
# sagt nichts - er sieht in der Datei aus wie eine Einstellung und ist
# eine Zeile Text. Die Zahl zwingt jeden, der eine zweiundneunzigste
# Einstellung hinzufuegt, die Messung zu wiederholen.
MEASURED_AGAINST_V1_20_0 = 91


def _code(text: str) -> str:
    """Der Text ohne ganzzeilige Kommentare."""
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def _expand_braces(name: str) -> list[str]:
    """typeset -g POWERLEVEL9K_{A,B}_X, wie zsh es liest."""
    match = re.search(r"\{([A-Za-z0-9_,]+)\}", name)
    if not match:
        return [name]
    found: list[str] = []
    for part in match.group(1).split(","):
        found += _expand_braces(name[:match.start()] + part
                                + name[match.end():])
    return found


def _p9k_names(text: str) -> set[str]:
    found: set[str] = set()
    for raw in re.findall(r"\b(POWERLEVEL9K_[A-Za-z0-9_{},]*)", text):
        for name in _expand_braces(raw):
            found.add(name.rstrip("_"))
    return found


def _generated(destination: Path, template: str, monkeypatch,
               theme_name: str | None = None) -> Path:
    """Eine Vorlage, verarbeitet wie der Generator sie verarbeitet."""
    monkeypatch.syspath_prepend(str(SRC))
    if theme_name is not None:
        root = destination.parent / f"machine-{theme_name}"
        root.mkdir(parents=True, exist_ok=True)
        (root / "theme").write_text(f"{theme_name}\n", encoding="utf-8")
        monkeypatch.setenv("ZEPOS_MACHINE_ROOT", str(root))

    # Frisch importieren, weil style_definition seine Werte beim Import
    # aus dem Thema aufloest: ein Modul, das schon im Speicher liegt,
    # traegt die Farben des vorigen Laufs.
    import importlib
    import sys
    for name in ("style_definition", "theme", "template_processor"):
        sys.modules.pop(name, None)
    processor = importlib.import_module("template_processor")
    processor.ConfigProcessor().apply_template(
        TEMPLATES / f"{template}.template", destination)
    for name in ("style_definition", "theme", "template_processor"):
        sys.modules.pop(name, None)
    return destination


# --------------------------------------------------------------------
# Die erzeugte Datei
# --------------------------------------------------------------------

def test_there_is_a_prompt_configuration_at_all(tmp_path, monkeypatch):
    """Der Kern des Befunds: es gab keine.

    ~/.p10k.zsh war die Datei, die ~/.zshrc sourcte und die niemand
    schrieb. Jetzt schreibt sie generate_config.sh - und die Route
    dorthin steht hier mit, weil eine Vorlage ohne Route eine Vorlage
    ist, die `--all` mit "unknown config" quittiert.
    """
    assert (TEMPLATES / "p10k-config.template").is_file()

    generator = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    route = re.search(r"^\s*p10k-config\)\n(.*?)\n\s*;;", generator,
                      re.S | re.M)
    assert route, "generate_config.sh kennt keine Route p10k-config"
    assert 'CONFIG_FILE=".p10k.zsh"' in route.group(1), route.group(1)
    assert 'CONFIG_DIR="$HOME"' in route.group(1), route.group(1)

    written = _generated(tmp_path / ".p10k.zsh", "p10k-config", monkeypatch)
    assert "{{" not in written.read_text(encoding="utf-8"), (
        "in der erzeugten Datei steht noch ein Platzhalter")


@pytest.mark.allow_subprocess
def test_the_generated_prompt_configuration_parses(tmp_path, monkeypatch):
    """`zsh -n`: lesen und uebersetzen, keinen Befehl ausfuehren.

    Dieselbe Begruendung wie in tests/src/test_zshrc.py: eine ~/.p10k.zsh
    mit einer unbalancierten Klammer bricht JEDE Anmeldung, und
    src/validate_output.py kann sie nicht pruefen - `bash -n` wuerde an
    zsh-Syntax scheitern und eine heile Datei fuer kaputt erklaeren.
    """
    zsh = shutil.which("zsh")
    assert zsh, "zsh ist auf diesem Rechner nicht da"
    written = _generated(tmp_path / ".p10k.zsh", "p10k-config", monkeypatch)

    empty = tmp_path / "nothing"
    empty.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run(
        [ENV, "-i", f"PATH={empty}", f"HOME={home}", zsh, "-f", "-n",
         str(written)],
        env={}, input="", capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stderr == "", result.stderr


def test_every_setting_in_it_is_one_powerlevel10k_reads(tmp_path, monkeypatch):
    """Eine Einstellung, die das Theme nicht kennt, ist eine Zeile Text.

    Sie faellt an nichts auf: die Datei parst, der Prompt erscheint, und
    genau die eine Sache, die eingestellt werden sollte, ist nicht
    eingestellt. Deshalb steht die Anzahl oben als Zahl - sie zwingt zur
    Wiederholung der Messung, sobald jemand einen Namen hinzufuegt.
    """
    written = _generated(tmp_path / ".p10k.zsh", "p10k-config", monkeypatch)
    names = _p9k_names(_code(written.read_text(encoding="utf-8")))
    assert len(names) == MEASURED_AGAINST_V1_20_0, (
        f"{len(names)} POWERLEVEL9K-Namen statt "
        f"{MEASURED_AGAINST_V1_20_0}. Wer einen hinzufuegt, misst ihn "
        f"gegen den Baum, den packaging/zsh-theme-powerlevel10k pinnt, "
        f"und traegt die neue Zahl hier ein.")


def test_the_prompt_never_lets_gitstatus_fetch_a_binary(tmp_path, monkeypatch):
    """Das eine Verhalten, das ein Paketsystem umgeht.

    powerlevel10k liest Git am liebsten mit gitstatusd. Findet es den
    Daemon nicht, LAEDT sein Installationspfad eine fertige Binaerdatei
    aus dem Netz - in das Heimatverzeichnis des Nutzers, an pacman
    vorbei, beim ersten Prompt. Zwei Zeilen verbieten das, und beide
    werden gebraucht: die erste betritt den Pfad gar nicht, die zweite
    haelt, wenn jemand die erste umlegt.
    """
    text = _code(_generated(tmp_path / ".p10k.zsh", "p10k-config",
                            monkeypatch).read_text(encoding="utf-8"))
    assert re.search(r"^\s*typeset -g POWERLEVEL9K_DISABLE_GITSTATUS=true$",
                     text, re.M), "gitstatus ist nicht abgeschaltet"
    assert re.search(r"^\s*typeset -g GITSTATUS_AUTO_INSTALL=0$", text, re.M), (
        "das Schloss gegen den Nachlade-Pfad fehlt")


# --------------------------------------------------------------------
# Dass die Farben aus der Mitte kommen
# --------------------------------------------------------------------

def test_the_prompt_carries_no_colour_of_its_own(tmp_path, monkeypatch):
    """Jede Farbe der Eingabezeile steht in der Palette des Themas.

    Ein Literal hier waere ein drittes Farbsystem neben src/brand.py und
    src/theme.py - genau das, was die geloeschte starship.toml war: vier
    hartcodierte Hex-Werte in einer Datei, die niemand geladen hat.
    """
    monkeypatch.syspath_prepend(str(SRC))
    written = _generated(tmp_path / ".p10k.zsh", "p10k-config", monkeypatch)
    import theme

    palette = theme.palette(theme.DEFAULT)
    erlaubt = {value.lower() for value in palette.COLORS.values()
               if isinstance(value, str) and value.startswith("#")}

    body = _code(written.read_text(encoding="utf-8"))
    fremd = sorted({found.lower()
                    for found in re.findall(r"#[0-9A-Fa-f]{6}", body)}
                   - erlaubt)
    assert fremd == [], (
        f"diese Farben stehen in keiner Rolle der Palette: {fremd}")


def test_switching_the_theme_rewrites_the_prompt(tmp_path, monkeypatch):
    """Der Beleg fuer "und andere themes auch".

    Zweimal erzeugt, mit zwei Themen, und die Dateien MUESSEN sich
    unterscheiden - und zwar in den Farben und nicht irgendwo. Das ist
    die Frage, die der Nutzer gestellt hat, als Messung.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import theme

    hell = _generated(tmp_path / "hell.zsh", "p10k-config", monkeypatch,
                      theme_name="tageslicht").read_text(encoding="utf-8")
    dunkel = _generated(tmp_path / "dunkel.zsh", "p10k-config", monkeypatch,
                        theme_name=theme.DEFAULT).read_text(encoding="utf-8")

    assert hell != dunkel, (
        "die Eingabezeile sieht in beiden Themen gleich aus - dann haengt "
        "sie nicht am Thema")

    farben = lambda text: {f.lower() for f in re.findall(r"#[0-9A-Fa-f]{6}",
                                                         _code(text))}
    assert farben(hell) & farben(dunkel) == set(), (
        "die beiden Themen teilen sich Prompt-Farben - dann ist mindestens "
        "eine davon nicht aus der Palette gekommen")

    for name, text in (("tageslicht", hell), (theme.DEFAULT, dunkel)):
        erwartet = {value.lower()
                    for role, value in theme.palette(name).COLORS.items()
                    if role.startswith("prompt_")}
        assert erwartet <= farben(text), (
            f"{name}: {sorted(erwartet - farben(text))} fehlt in der "
            f"erzeugten Datei")


# --------------------------------------------------------------------
# Dass das, was konfiguriert wird, auch installiert wird
# --------------------------------------------------------------------

def test_the_login_shell_no_longer_configures_a_framework_nobody_installs(
        tmp_path, monkeypatch):
    """oh-my-zsh, im CODE der erzeugten ~/.zshrc.

    Gegen _code() und nicht gegen den Rohtext: der Kopf der Vorlage
    ERKLAERT, warum oh-my-zsh weg ist, und nennt es dabei achtmal. Eine
    Suche im Wortlaut faende die Erklaerung und waere gruen, egal was
    darunter steht.
    """
    text = _code(_generated(tmp_path / ".zshrc", "zshrc-config",
                            monkeypatch).read_text(encoding="utf-8"))
    for gone in ("oh-my-zsh", "ZSH_THEME", "ZSH_CUSTOM", "$ZSH/"):
        assert gone not in text, (
            f"die erzeugte ~/.zshrc richtet weiterhin {gone} ein - ein "
            f"Paket, das keine Installation von ZepOS bekommt")


def test_the_login_shell_loads_the_files_the_packages_install(
        tmp_path, monkeypatch):
    """Die drei source-Zeilen, gegen die Rezepte gehalten, die sie
    anlegen.

    Ein Pfad, den nur eine Seite kennt, ist der Fehler von vorher noch
    einmal: eine Konfiguration, die auf eine Datei zeigt, die nirgends
    entsteht.
    """
    text = _code(_generated(tmp_path / ".zshrc", "zshrc-config",
                            monkeypatch).read_text(encoding="utf-8"))
    for path in (THEME_FILE, *PLUGIN_FILES):
        assert re.search(rf"^\s*source {re.escape(path)}$", text, re.M), (
            f"die erzeugte ~/.zshrc sourct {path} nicht")

    recipe = (PACKAGING / "zsh-theme-powerlevel10k" / "PKGBUILD").read_text(
        encoding="utf-8")
    assert "/usr/share/zsh-theme-powerlevel10k" in _code(recipe), (
        "das Rezept legt das Theme nicht dort ab, wo ~/.zshrc es sucht")

    desktop = _code((PACKAGING / "zepos-desktop" / "PKGBUILD").read_text(
        encoding="utf-8"))
    for package in ("zsh-theme-powerlevel10k", "zsh-autosuggestions",
                    "zsh-syntax-highlighting", "zsh-completions"):
        assert re.search(rf"^\s*'{re.escape(package)}'", desktop, re.M), (
            f"{package} ist keine Abhaengigkeit des Desktops - dann ist "
            f"die source-Zeile dafuer wieder eine Konfiguration ohne "
            f"ihr Programm")


def test_the_prompt_configuration_is_sourced_by_the_login_shell(
        tmp_path, monkeypatch):
    """Die andere Haelfte: ~/.p10k.zsh nuetzt nichts, wenn niemand sie
    liest. Und der Sofort-Prompt oben in ~/.zshrc gehoert dazu - er ist
    die Haelfte, die p10k selbst verlangt, ganz oben und vor allem, was
    etwas ausgibt.
    """
    text = _generated(tmp_path / ".zshrc", "zshrc-config",
                      monkeypatch).read_text(encoding="utf-8")
    assert re.search(r"^\[\[ ! -r ~/\.p10k\.zsh \]\] \|\| source ~/\.p10k\.zsh$",
                     _code(text), re.M), (
        "die erzeugte ~/.zshrc liest ~/.p10k.zsh nicht")

    kopf = _code(text).strip().splitlines()
    assert "p10k-instant-prompt" in "\n".join(kopf[:5]), (
        "der Sofort-Prompt steht nicht mehr am Anfang der Datei")


@pytest.mark.allow_subprocess
def test_a_first_login_no_longer_reports_a_missing_file(tmp_path, monkeypatch):
    """Die Regressionsprobe auf die gemessene Meldung.

    Eine echte interaktive zsh mit der erzeugten ~/.zshrc, in einem
    leeren Heimatverzeichnis - also genau die Lage nach der Installation.
    Vorher stand dort "no such file or directory:
    ~/.oh-my-zsh/oh-my-zsh.sh", bei jeder einzelnen Anmeldung.
    """
    zsh = shutil.which("zsh")
    assert zsh, "zsh ist auf diesem Rechner nicht da"

    home = tmp_path / "home"
    (home / ".cache").mkdir(parents=True)
    _generated(home / ".zshrc", "zshrc-config", monkeypatch)
    _generated(home / ".p10k.zsh", "p10k-config", monkeypatch)

    # MIT einem brauchbaren PATH und nicht mit einem leeren, anders als
    # in tests/src/test_zshrc.py: dort wird nur geparst, hier wird
    # AUSGEFUEHRT. Ein leeres PATH machte aus jeder Zeile, die ein
    # Programm ruft, ein "command not found" - und damit waere die
    # Zusicherung darunter, dass die Anmeldung STUMM ist, nicht mehr zu
    # halten. Zwei feste Verzeichnisse und nicht das PATH des
    # Entwicklers: sonst misst dieser Test, was auf dieser Maschine
    # zufaellig installiert ist.
    result = subprocess.run(
        [ENV, "-i", "PATH=/usr/bin:/bin", f"HOME={home}",
         f"XDG_CACHE_HOME={home}/.cache", f"XDG_STATE_HOME={home}/.state",
         "TERM=dumb", zsh, "-i", "-c", "exit 0"],
        env={}, input="", capture_output=True, text=True, timeout=120)

    # Nicht nur "keine fehlende Datei", sondern gar nichts. Die Meldung,
    # die gemeldet wurde, war eine von der Sorte "no such file or
    # directory" - aber eine Anmeldung, die stattdessen etwas anderes
    # ausgibt, ist genauso kaputt, und sie bricht ausserdem den
    # Sofort-Prompt, der ueber Ausgaben vor seiner Zeit stolpert.
    assert result.stderr == "", (
        "die Anmeldung gibt etwas aus:\n" + result.stderr)
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------
# Der PATH der Anmeldeschale, und was nicht mehr darin steht
# --------------------------------------------------------------------
#
# GEMELDET am 17.08.2026, sinngemaess: in der ausgelieferten
# Konfiguration steht Software, die es auf dieser Maschine nicht gibt.
#
# Er hatte recht, und es war mehr als haesslich. Der conda-Block RIEF
# /opt/anaconda/bin/conda bei jeder Anmeldung AUF, und drei Verzeichnisse
# standen VOR /usr/bin - ~/.npm-global/bin unter ihnen. Was vorne im PATH
# liegt, gewinnt gegen jedes Programm des Systems; am selben Tag lag
# genau dort der Verdacht, ein altes `claude` in einem dieser
# Verzeichnisse fange den Aufruf ab. (Es war es nicht - die Ursache stand
# im Paketrezept, siehe tests/packaging/test_claude_code.py -, aber die
# Falle bleibt eine, solange die Zeilen dastehen.)

# Die vier Orte, an denen die Vorlage Software vermutete, die keine
# Installation von ZepOS hat. NACHGESEHEN am 17.08.2026 auf der
# entschluesselten Wurzel der letzten Installation
# (iso/out/release-target.img): keiner von ihnen existiert dort.
FREMDE_ORTE = ("/opt/anaconda", "/opt/android-sdk", "/opt/android-ndk",
               "/usr/lib/jvm", ".npm-global")

# Und die Namen, die dieselben Bloecke gesetzt haben.
FREMDE_NAMEN = ("ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_NDK_HOME",
                "JAVA_HOME", "__conda_setup", "CRYPTOGRAPHY_OPENSSL_NO_LEGACY")


def test_the_login_shell_names_no_place_this_system_does_not_have(
        tmp_path, monkeypatch):
    """Gegen _code() und nicht gegen den Rohtext, aus demselben Grund wie
    bei oh-my-zsh: die Vorlage ERKLAERT, was hier stand, und nennt die
    Pfade dabei. Eine Suche im Wortlaut faende die Erklaerung."""
    text = _code(_generated(tmp_path / ".zshrc", "zshrc-config",
                            monkeypatch).read_text(encoding="utf-8"))
    for ort in FREMDE_ORTE:
        assert ort not in text, (
            f"die erzeugte ~/.zshrc zeigt weiterhin auf {ort} - ein Ort, "
            f"den keine Installation von ZepOS hat")
    for name in FREMDE_NAMEN:
        assert name not in text, (
            f"die erzeugte ~/.zshrc setzt weiterhin {name}")


def test_no_abbreviation_points_at_a_program_nobody_installs(
        tmp_path, monkeypatch):
    """Hier standen `lg`, `ti` und `gu` - auf lazygit, tig und gitui.
    Keines der drei liegt auf einer Installation, keines steht in einem
    depends. Drei Abkuerzungen, die "command not found" abkuerzen.

    Geprueft wird nicht gegen eine Liste dieser drei Namen, sondern gegen
    die Frage dahinter: JEDES Ziel eines Alias muss entweder ein Paket
    sein, das ein Rezept installiert, oder ein Hilfsskript, das der
    Generator schreibt. Sonst faellt der naechste tote Alias wieder erst
    dem Nutzer auf.
    """
    text = _code(_generated(tmp_path / ".zshrc", "zshrc-config",
                            monkeypatch).read_text(encoding="utf-8"))
    ziele = {treffer.split()[0]
             for treffer in re.findall(r"^\s*alias\s+\w+='([^']+)'", text,
                                       re.M)}
    assert ziele, "die erzeugte ~/.zshrc kennt gar keinen Alias mehr"

    rezepte = "\n".join(
        pfad.read_text(encoding="utf-8")
        for pfad in sorted(PACKAGING.glob("*/PKGBUILD")))
    generator = (SRC / "generate_config.sh").read_text(encoding="utf-8")

    for ziel in sorted(ziele):
        aus_paket = re.search(rf"^\s*'{re.escape(ziel)}'", _code(rezepte), re.M)
        erzeugt = f'CONFIG_FILE="{ziel}"' in generator
        assert aus_paket or erzeugt, (
            f"`{ziel}` ist das Ziel eines Alias, wird aber von keinem "
            f"Rezept installiert und von generate_config.sh nicht "
            f"erzeugt")


@pytest.mark.allow_subprocess
def test_the_generated_helpers_are_reachable_from_a_shell(tmp_path,
                                                          monkeypatch):
    """~/.local/bin ist der Ort, an den generate_config.sh
    start-hyprland, list-profiles und die uebrigen schreibt. Steht es
    nicht im PATH, ist `start-hyprland` ein Befehl, den es nicht gibt.

    Gemessen an einer echten interaktiven zsh mit der erzeugten Datei,
    unter `env -i` - nicht am Text der Vorlage.
    """
    zsh = shutil.which("zsh")
    assert zsh, "zsh ist auf diesem Rechner nicht da"

    home = tmp_path / "home"
    (home / ".cache").mkdir(parents=True)
    _generated(home / ".zshrc", "zshrc-config", monkeypatch)

    result = subprocess.run(
        [ENV, "-i", "PATH=/usr/bin:/bin", f"HOME={home}", f"ZDOTDIR={home}",
         f"XDG_CACHE_HOME={home}/.cache", f"XDG_STATE_HOME={home}/.state",
         "TERM=dumb", zsh, "-i", "-c", "printf %s $PATH"],
        env={}, input="", capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr

    eintraege = result.stdout.split(os.pathsep)
    assert eintraege[0] == f"{home}/.local/bin", (
        f"~/.local/bin steht nicht vorn im PATH: {result.stdout}")


@pytest.mark.allow_subprocess
def test_the_path_does_not_grow_with_every_nested_shell(tmp_path, monkeypatch):
    """`export PATH=~/.local/bin:$PATH` wiederholt sich in jeder
    verschachtelten Schale. GEMESSEN am 17.08.2026 auf dem Rechner, von
    dem diese Vorlage stammt: ~/.local/bin stand dort DREIMAL im PATH,
    ~/.npm-global/bin und /opt/anaconda/bin je zweimal.

    Drei Ebenen tief, weil zwei den Fehler noch nicht zeigen muessen.
    """
    zsh = shutil.which("zsh")
    assert zsh, "zsh ist auf diesem Rechner nicht da"

    home = tmp_path / "home"
    (home / ".cache").mkdir(parents=True)
    _generated(home / ".zshrc", "zshrc-config", monkeypatch)

    result = subprocess.run(
        [ENV, "-i", "PATH=/usr/bin:/bin", f"HOME={home}", f"ZDOTDIR={home}",
         f"XDG_CACHE_HOME={home}/.cache", f"XDG_STATE_HOME={home}/.state",
         "TERM=dumb", zsh, "-i", "-c",
         'zsh -i -c "zsh -i -c \'printf %s \\$PATH\'"'],
        env={}, input="", capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr

    lokal = f"{home}/.local/bin"
    assert result.stdout.split(os.pathsep).count(lokal) == 1, (
        f"{lokal} steht mehrfach im PATH: {result.stdout}")


# --------------------------------------------------------------------
# Und der Prompt selbst, wenn das Theme da ist
# --------------------------------------------------------------------

def _p10k_root() -> Path | None:
    override = os.environ.get("ZEPOS_P10K_ROOT")
    candidate = Path(override) if override else Path(
        "/usr/share/zsh-theme-powerlevel10k")
    return candidate if (candidate / "powerlevel10k.zsh-theme").is_file() \
        else None


@pytest.mark.allow_subprocess
def test_the_theme_really_draws_this_prompt(tmp_path, monkeypatch):
    """Der Prompt, gezeichnet, mit dem echten powerlevel10k.

    Alles darueber liest Dateien. Das hier fuehrt aus: Theme laden,
    ~/.p10k.zsh laden, die precmd-Haken durchlaufen und nachsehen, was in
    $PROMPT steht. Gemessen am 12.08.2026 gegen v1.20.0 - die sieben
    Rollenfarben standen als %F{...} darin, der Zweigname mit dem
    Nerd-Font-Symbol davor und das Eingabezeichen am Anfang der zweiten
    Zeile.

    Auf einer Maschine ohne das Paket wird uebersprungen. Das ist die
    ehrliche Grenze: der Test kann das Theme nicht herbeischaffen, und
    ein Nachladen aus dem Netz waere genau das, was diese Aenderung
    verbietet. Mit einem ausgepackten Quellbaum:

        ZEPOS_P10K_ROOT=/pfad/zu/powerlevel10k pytest tests/src/test_prompt.py
    """
    root = _p10k_root()
    if root is None:
        pytest.skip(
            "powerlevel10k liegt nicht auf dieser Maschine - damit bleibt "
            "ungeprueft, ob die erzeugte ~/.p10k.zsh wirklich einen Prompt "
            "hervorbringt. ZEPOS_P10K_ROOT zeigt auf einen Quellbaum.")

    zsh = shutil.which("zsh")
    assert zsh, "zsh ist auf diesem Rechner nicht da"

    home = tmp_path / "home"
    (home / ".cache").mkdir(parents=True)
    _generated(home / ".p10k.zsh", "p10k-config", monkeypatch)

    probe = home / "probe.zsh"
    probe.write_text(
        f"source {root}/powerlevel10k.zsh-theme\n"
        "source ~/.p10k.zsh\n"
        "for f in $precmd_functions; do $f; done\n"
        "print -r -- \"$PROMPT\"\n",
        encoding="utf-8")

    # Ein brauchbares PATH, und das ist gemessen und nicht vorsorglich:
    # powerlevel10k fragt beim Start `uname` und `locale`. Mit leerem
    # PATH bekommt es auf beides keine Antwort, faellt in die
    # C-Zeichensatzannahme und bricht beim ersten Nerd-Font-Symbol mit
    # "_p9k_get_icon: character not in range" ab.
    result = subprocess.run(
        [ENV, "-i", "PATH=/usr/bin:/bin", f"HOME={home}",
         f"XDG_CACHE_HOME={home}/.cache", "TERM=xterm-256color",
         zsh, "-f", "-i", "-c", f"source {probe}"],
        env={}, input="", capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr

    prompt = result.stdout
    assert len(prompt) > 200, (
        "der Prompt ist der zsh-Standardprompt geblieben - das Theme hat "
        f"diese Datei nicht angenommen: {prompt!r}")

    monkeypatch.syspath_prepend(str(SRC))
    import theme
    palette = theme.palette(theme.DEFAULT)
    for role, colour in palette.COLORS.items():
        if not role.startswith("prompt_"):
            continue
        assert f"%F{{{colour}".lower() in prompt.lower(), (
            f"{role} ({colour}) kommt im gezeichneten Prompt nicht vor")
