# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Anmeldung: dass es sie gibt, dass sie fragt, und dass sie faellt.

WAS DIESE DATEI BEWACHT UND WARUM SIE GEBRAUCHT WIRD
    Gemessen mit iso/test-boot.py --scenario release-installed auf
    iso/out/release-target.img: das installierte System erreichte
    "Reached target Graphical Interface" und dann passierte nichts. Es
    gab keinen Anmeldedienst, keinen Sitzungseintrag und nichts, was
    einen Compositor gestartet haette - und kein einziger Test hat das
    bemerkt, weil kein Test danach gefragt hat.

    Die Pruefungen unten fragen danach, und die Haelfte von ihnen tut es,
    indem sie die Skripte AUSFUEHRT statt sie zu lesen. Ein Greeter, der
    nur auf dem Papier zurueckfaellt, ist genau der Fehler, der hier
    gerade behoben wird.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests import conftest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
LOGIN = SRC / "login"
BIN = SRC / "bin"
RECIPE = ROOT / "packaging" / "zepos-config" / "PKGBUILD"

ENV = "/usr/bin/env"

GREETER = BIN / "zepos-greeter"
SESSION = BIN / "zepos-session"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------
# Die Pfade, die kein zweites Paket besitzen darf
# --------------------------------------------------------------------

def test_the_configuration_never_claims_a_path_greetd_owns():
    """greetd besitzt /etc/greetd/config.toml und greetd-regreet besitzt
    /etc/greetd/regreet.toml - beides an den Paketen nachgemessen. Zwei
    Pakete auf einem Pfad sind in pacman ein Dateikonflikt, und der
    bricht die Installation ab, statt sie nur zu verfaerben.

    Deshalb steht hier ein Verbot und keine Erlaubnis: die Pruefung
    faellt durch, sobald irgendein install-Aufruf des Rezepts einen der
    beiden Namen als ZIEL nennt.
    """
    recipe = _read(RECIPE)
    for owned in ("/etc/greetd/config.toml", "/etc/greetd/regreet.toml"):
        assert f'"$pkgdir{owned}"' not in recipe, (
            f"zepos-config beansprucht {owned} - das gehoert einem "
            "anderen Paket und ist ein Dateikonflikt")


def test_the_package_installs_every_file_the_login_needs():
    """Vier Dateien, und keine von ihnen faellt einzeln auf.

    Fehlt die greetd-Konfiguration, startet agreety mit /bin/sh. Fehlt
    das Drop-in, liest greetd die Paketvorgabe und die
    ZepOS-Konfiguration liegt ungelesen daneben. Fehlt regreet.toml,
    steht die Maske ohne Hintergrund da. Fehlt der Sitzungseintrag, gibt
    es nach der Anmeldung nichts zu starten. Kein Fall davon meldet sich.
    """
    recipe = _read(RECIPE)
    for source, target in (
        ("login/greetd.toml", "/etc/greetd/zepos.toml"),
        ("login/regreet.toml", "/etc/greetd/zepos-regreet.toml"),
        ("login/greetd-service.conf",
         "/usr/lib/systemd/system/greetd.service.d/10-zepos.conf"),
        ("login/zepos.desktop", "/usr/share/wayland-sessions/zepos.desktop"),
    ):
        assert (SRC / source).is_file(), f"{source} fehlt im Baum"
        assert re.search(rf"install -Dm644 {re.escape(source)} \\?\s*\n?\s*"
                         rf'"\$pkgdir{re.escape(target)}"', recipe), (
            f"{source} wird nicht nach {target} installiert")


def test_the_two_login_commands_are_installed_executable():
    """Ein Greeter mit Modus 644 ist ein Anmeldebildschirm, der nicht
    kommt: greetd startet die Zeile aus seiner Konfiguration ueber sh,
    und sh antwortet auf eine nicht ausfuehrbare Datei mit "Permission
    denied" und sonst nichts. Der erste Start des Rauchbilds starb an
    genau diesem Fehler, mit 126 und ohne Sitzung.
    """
    recipe = _read(RECIPE)
    install = re.search(r'install -Dm755 -t "\$pkgdir/usr/bin"(.*?)\n\n',
                        recipe, re.S)
    assert install, "zepos-config installiert nichts mit -m755 nach /usr/bin"
    for command in ("zepos-greeter", "zepos-session"):
        assert f"bin/{command}" in install.group(1), (
            f"{command} wird nicht ausfuehrbar installiert")
        assert os.access(BIN / command, os.X_OK), (
            f"src/bin/{command} ist im Baum nicht ausfuehrbar")


def test_the_two_editable_files_survive_an_upgrade():
    """Die beiden Dateien unter /etc sind das, woran ein Administrator
    dreht. Ohne backup= ueberschreibt sie das naechste `pacman -Syu`
    wortlos, und die Aenderung ist weg."""
    recipe = _read(RECIPE)
    backup = re.search(r"^backup=\((.*?)^\)", recipe, re.S | re.M)
    assert backup, "zepos-config hat keine backup-Liste"
    for path in ("etc/greetd/zepos.toml", "etc/greetd/zepos-regreet.toml"):
        assert f"'{path}'" in backup.group(1), f"{path} steht nicht in backup="


# --------------------------------------------------------------------
# Es wird gefragt
# --------------------------------------------------------------------

def test_the_login_asks_and_never_logs_anybody_in_by_itself():
    """"anmeldung immer" ist die Vorgabe, und sie hat zwei Gegenspieler,
    die beide still sind.

    greetd(5) kennt [initial_session] - das ist sein Autologin, "commonly
    referred to as auto-login", und es meldet beim ersten Start nach dem
    Booten ohne Frage an. agetty kennt --autologin, was das Rauchbild
    benutzt. Keins von beiden darf in einer Datei stehen, die auf ein
    installiertes System geht.
    """
    for path in sorted(LOGIN.rglob("*")) + [GREETER, SESSION]:
        if not path.is_file():
            continue
        # Ohne die Kommentare, und das ist keine Bequemlichkeit: die
        # Begruendung, warum ZepOS kein Autologin hat, MUSS das Wort
        # nennen duerfen. Ein Wachhund, der die Erklaerung seiner eigenen
        # Regel verbietet, wird umgangen, indem man die Erklaerung
        # loescht.
        code = "\n".join(line for line in _read(path).splitlines()
                         if not line.lstrip().startswith("#"))
        assert "[initial_session]" not in code, (
            f"{path.relative_to(ROOT)} traegt greetds Autologin")
        assert "--autologin" not in code, (
            f"{path.relative_to(ROOT)} traegt ein getty-Autologin")


def test_the_greeter_asks_for_the_session_too():
    """skip_selection = true uebernimmt stillschweigend die letzte
    Auswahl. Auf einem Anmeldebildschirm heisst das: es steht nicht mehr
    da, wer und was hier gleich gestartet wird."""
    assert re.search(r"^skip_selection\s*=\s*false\s*$",
                     _read(LOGIN / "regreet.toml"), re.M)


# --------------------------------------------------------------------
# Die Kette haelt zusammen
# --------------------------------------------------------------------

def test_greetd_is_pointed_at_the_zepos_configuration():
    """Das Drop-in ist der einzige Weg, greetd auf eine andere Datei zu
    zeigen, ohne eine fremde zu besitzen - und die LEERE ExecStart-Zeile
    davor ist der Teil, der leicht fehlt: ExecStart ist in systemd eine
    Liste, eine zweite Zeile HAENGT AN. Ohne die Leerzuweisung liefe
    greetd zweimal, das zweite Mal gegen ein belegtes tty1.
    """
    dropin = _read(LOGIN / "greetd-service.conf")
    lines = [line.strip() for line in dropin.splitlines()
             if line.strip().startswith("ExecStart")]
    assert lines[0] == "ExecStart=", (
        "die erste ExecStart-Zeile loescht die Liste nicht")
    assert len(lines) == 2, f"unerwartete ExecStart-Zeilen: {lines}"
    assert "--config /etc/greetd/zepos.toml" in lines[1]

    # Und die Datei, auf die gezeigt wird, ist die, die das Rezept dorthin
    # legt. Zwei Haelften, die einander nicht pruefen koennen.
    assert '"$pkgdir/etc/greetd/zepos.toml"' in _read(RECIPE)


def test_the_greeter_command_is_the_one_the_package_installs():
    """greetd startet, was in seiner Konfiguration steht. Ein Tippfehler
    dort ist kein Fehler, den irgendetwas meldet - es ist ein
    Anmeldebildschirm, der nicht erscheint."""
    assert 'command = "/usr/bin/zepos-greeter"' in _read(LOGIN / "greetd.toml")
    assert (BIN / "zepos-greeter").is_file()


def test_the_session_entry_starts_zepos_and_not_the_compositor():
    """hyprland.desktop startet /usr/bin/start-hyprland, also den
    Compositor. Fuer ZepOS ist das zu frueh: die Konfiguration entsteht
    unmittelbar davor, und src/plugins.py nennt "ein Login ueber einen
    Display-Manager an start-hyprland vorbei" ausdruecklich als die
    Luecke, die der Generator nicht schliessen kann. Dieser Eintrag
    schliesst sie - solange sein Exec durch zepos-session geht.
    """
    entry = _read(LOGIN / "zepos.desktop")
    assert re.search(r"^Exec=/usr/bin/zepos-session\s*$", entry, re.M)
    assert re.search(r"^Type=Application\s*$", entry, re.M)
    assert re.search(r"^Name=ZepOS\s*$", entry, re.M)


def test_the_greeter_background_is_a_file_this_repository_ships():
    """Dasselbe Bild wie hinter dem Installer, und es muss aus dem Paket
    kommen, das auf einer INSTALLATION liegt: die drei Installerpakete
    liegen nur in der ISO (Spec 4.2), also waere ein Pfad unter
    /usr/share/zepos-installer ein Hintergrund, den niemand je sieht.
    """
    background = re.search(r'^path\s*=\s*"([^"]+)"', _read(LOGIN / "regreet.toml"),
                           re.M)
    assert background, "regreet.toml nennt kein Hintergrundbild"
    path = background.group(1)
    prefix = "/usr/share/zepos/branding/"
    assert path.startswith(prefix), (
        f"{path} liegt nicht in dem Verzeichnis, das zepos-config packt")
    assert (SRC / "branding" / path[len(prefix):]).is_file(), (
        f"{path} zeigt auf eine Datei, die es im Baum nicht gibt")

    # Und das Rezept packt dieses Verzeichnis wirklich - dieselbe Zeile,
    # an der tests/packaging/test_recipes.py das Hintergrundbild misst.
    assert re.search(r"cp -a --no-preserve=ownership \\\n\s+branding ", _read(RECIPE))


# --------------------------------------------------------------------
# Und jetzt wird ausgefuehrt
# --------------------------------------------------------------------

# Was die beiden Skripte an gewoehnlichem Werkzeug brauchen. Jedes davon
# geht als Durchreiche an sein echtes Programm, und conftest.
# assert_safe_to_passthrough() sagt fuer jedes einzeln, ob das erlaubt
# ist - keins von ihnen aendert etwas ausserhalb von tmp_path, und `rm`
# wird nur auf die eigene Merkdatei angesetzt.
PASSTHROUGH = ("bash", "date", "id", "tty", "sed", "awk", "tail", "rm",
               "mkdir", "chmod")


def _stubs(directory: Path, **bodies: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in PASSTHROUGH:
        conftest.assert_safe_to_passthrough(name)
        real = shutil.which(name)
        assert real, f"{name} ist auf diesem Rechner nicht da"
        bodies.setdefault(name, f'exec "{real}" "$@"\n')
    for name, body in bodies.items():
        stub = directory / name
        stub.write_text("#!/bin/bash\n" + body, encoding="utf-8")
        stub.chmod(0o755)
    return directory


def _child_path(stubs: Path) -> str:
    """Das Stub-Verzeichnis und nichts sonst - darauf ruht die ganze
    Sicherheitsbegruendung dieser Datei."""
    path = str(stubs)
    assert path.split(os.pathsep) == [str(stubs)]
    assert not os.environ.get("PATH", "").startswith(path)
    return path


def _run(command: Path, stubs: Path, *, stdin: str = "", **environment: str):
    # stdin ist nicht ueberall leer, und das ist der Punkt: eine leere
    # Standardeingabe ist selbst schon ein Dateiende, also kann ein Test
    # mit input="" nicht unterscheiden, ob ein </dev/null im Skript steht
    # oder fehlt. Wer das messen will, gibt hier etwas zu lesen mit.
    return subprocess.run(
        [ENV, "-i", f"PATH={_child_path(stubs)}",
         *(f"{key}={value}" for key, value in environment.items()),
         str(command)],
        env={}, input=stdin, capture_output=True, text=True, timeout=120,
    )


def _greeter_root(tmp_path: Path, keymap: str = "de-latin1",
                  *, drm: bool = True) -> Path:
    """Ein nachgebautes Wurzelverzeichnis fuer den Greeter.

    Der echte Greeter liest /etc/vconsole.conf, /usr/share/systemd/
    kbd-model-map und /dev/dri unter genau diesen Namen. Sie werden hier
    nachgebaut statt vom Rechner genommen, weil ein Test, der die
    Tastaturbelegung des Entwicklers misst, auf dem naechsten Rechner
    etwas anderes misst.
    """
    root = tmp_path / "root"
    (root / "etc").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "vconsole.conf").write_text(
        f"KEYMAP={keymap}\nFONT=ter-v16n\n", encoding="utf-8")

    (root / "usr" / "share" / "systemd").mkdir(parents=True, exist_ok=True)
    # Drei Zeilen aus der echten Tabelle des systemd-Pakets, im echten
    # Format: Konsolenbelegung, XKB-Layout, Modell, Variante.
    (root / "usr" / "share" / "systemd" / "kbd-model-map").write_text(
        "# consoleKeymap\t\txkbLayout\txkbModel\txkbVariant\txkbOptions\n"
        "de-latin1\t\tde\tpc105\t-\tterminate:ctrl_alt_bksp\n"
        "de-latin1-nodeadkeys\tde\tpc105\tnodeadkeys\tterminate:ctrl_alt_bksp\n"
        "uk\t\t\tgb\tpc105\t-\tterminate:ctrl_alt_bksp\n"
        "us\t\t\tus\tpc105+inet\t-\tterminate:ctrl_alt_bksp\n",
        encoding="utf-8")

    (root / "var" / "log" / "regreet").mkdir(parents=True, exist_ok=True)
    if drm:
        (root / "dev" / "dri").mkdir(parents=True, exist_ok=True)
        (root / "dev" / "dri" / "card0").write_text("", encoding="utf-8")
    return root


def _runtime(tmp_path: Path) -> Path:
    """Das Laufzeitverzeichnis, das pam_systemd dem Benutzer greeter
    anlegt. Es MUSS existieren: der Greeter legt seine Merkdatei darin
    ab, und ohne sie sieht ein gelungener grafischer Start aus wie ein
    gescheiterter."""
    runtime = tmp_path / "run"
    runtime.mkdir(exist_ok=True)
    return runtime


@pytest.mark.allow_subprocess
def test_the_graphical_greeter_is_tried_first_and_the_text_one_not_at_all(tmp_path):
    """Auf einer Maschine mit funktionierendem Compositor darf der
    Textgreeter nicht anspringen. Er wuerde die grafische Maske
    ueberschreiben, die gerade laeuft."""
    root = _greeter_root(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    stubs = _stubs(
        tmp_path / "stubs",
        # cage fuehrt aus, was ihm uebergeben wurde - so wie das echte.
        # Der Renderer wird mitgeschrieben: ohne ihn saehe ein Lauf, der
        # den ersten Versuch ueberspringt und erst mit pixman zum Ziel
        # kommt, genauso aus wie einer, der gleich beim ersten
        # funktioniert - eine Mutationsprobe hat das gezeigt.
        cage=f'printf "cage(%s)" "${{WLR_RENDERER:-standard}}" >>"{evidence}/order"\n'
             'shift 3\nexec "$@"\n',
        regreet=f'printf " regreet" >>"{evidence}/order"\nexit 0\n',
        tuigreet=f'printf " tuigreet" >>"{evidence}/order"\nexit 0\n',
    )
    result = _run(GREETER, stubs, ZEPOS_GREETER_ROOT=str(root),
                  XDG_RUNTIME_DIR=str(_runtime(tmp_path)), HOME=str(tmp_path))
    conftest.assert_no_missing_command(result, "der Greeter")

    order = (evidence / "order").read_text(encoding="utf-8")
    assert order == "cage(standard) regreet", order
    assert result.returncode == 0, result.stderr


@pytest.mark.allow_subprocess
def test_the_text_greeter_takes_over_when_no_compositor_comes_up(tmp_path):
    """Spec 8.5, und die Erkennung laeuft ueber den tatsaechlichen
    Startversuch: cage scheitert zweimal - einmal mit dem gewoehnlichen
    Renderer, einmal mit pixman - und erst dann uebernimmt tuigreet.

    Gemessen wird an der Reihenfolge und nicht am Rueckgabewert: ein
    erfolgreicher Login sieht von aussen aus wie ein Absturz, weil greetd
    den Greeter beendet, sobald er die Sitzung anfordert.
    """
    root = _greeter_root(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    stubs = _stubs(
        tmp_path / "stubs",
        cage=f'printf "cage(%s) " "${{WLR_RENDERER:-standard}}" >>"{evidence}/order"\n'
             "exit 1\n",
        regreet="exit 0\n",
        tuigreet=f'printf tuigreet >>"{evidence}/order"\nexit 0\n',
    )
    result = _run(GREETER, stubs, ZEPOS_GREETER_ROOT=str(root),
                  XDG_RUNTIME_DIR=str(_runtime(tmp_path)), HOME=str(tmp_path))
    conftest.assert_no_missing_command(result, "der Greeter")

    order = (evidence / "order").read_text(encoding="utf-8")
    assert order == "cage(standard) cage(pixman) tuigreet", order


@pytest.mark.allow_subprocess
def test_the_text_greeter_offers_the_zepos_session_by_default(tmp_path):
    """tuigreet ohne --cmd fragt nach einem Befehl, den auf diesem
    Bildschirm niemand kennt."""
    root = _greeter_root(tmp_path, drm=False)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    stubs = _stubs(
        tmp_path / "stubs",
        cage="exit 1\n",
        tuigreet=f'printf "%s\\n" "$@" >>"{evidence}/args"\nexit 0\n',
    )
    result = _run(GREETER, stubs, ZEPOS_GREETER_ROOT=str(root),
                  XDG_RUNTIME_DIR=str(_runtime(tmp_path)), HOME=str(tmp_path))
    conftest.assert_no_missing_command(result, "der Greeter")

    arguments = (evidence / "args").read_text(encoding="utf-8").split("\n")
    assert "--cmd" in arguments
    assert arguments[arguments.index("--cmd") + 1] == "/usr/bin/zepos-session"


@pytest.mark.allow_subprocess
@pytest.mark.parametrize("keymap,layout,variant", [
    ("de-latin1", "de", ""),
    ("de-latin1-nodeadkeys", "de", "nodeadkeys"),
    # Der Fall, an dem jedes Abschneiden am Bindestrich scheitert: die
    # Konsolenbelegung heisst uk, das XKB-Layout heisst gb.
    ("uk", "gb", ""),
    # Und eine Belegung, die in keiner Tabelle steht. "us" zu raten waere
    # genau der Fehler, den dieser Block entfernt.
    ("erfundeneBelegung", "de", ""),
])
def test_the_console_keymap_reaches_the_compositor(tmp_path, keymap, layout, variant):
    """Auf diesem Bildschirm wird ein Passwort verdeckt getippt.

    archinstall schreibt in das Zielsystem nur KEYMAP nach
    /etc/vconsole.conf (lib/installer.py, set_vconsole) - kein XKBLAYOUT.
    Ein wlroots-Compositor nimmt ohne XKB_DEFAULT_* die eingebaute
    Vorgabe "us", und dann tippt ein deutscher Benutzer ein Passwort, das
    zu beiden Feldern passt und zu seinem Konto nicht. Gemessen genau so
    auf dem Installationsmedium, bevor es dort geradegezogen wurde.
    """
    root = _greeter_root(tmp_path, keymap)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    stubs = _stubs(
        tmp_path / "stubs",
        cage=f'printf "%s|%s" "${{XKB_DEFAULT_LAYOUT:-}}" "${{XKB_DEFAULT_VARIANT:-}}"'
             f' >"{evidence}/xkb"\n'
             f'printf 0 >"$XDG_RUNTIME_DIR/zepos-greeter.rc"\nexit 0\n',
        regreet="exit 0\n",
        tuigreet="exit 0\n",
    )
    result = _run(GREETER, stubs, ZEPOS_GREETER_ROOT=str(root),
                  XDG_RUNTIME_DIR=str(_runtime(tmp_path)), HOME=str(tmp_path))
    conftest.assert_no_missing_command(result, "der Greeter")

    assert (evidence / "xkb").read_text(encoding="utf-8") == f"{layout}|{variant}"


# --------------------------------------------------------------------
# Die Sitzung
# --------------------------------------------------------------------

def _session_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True, exist_ok=True)
    (home / ".local" / "bin").mkdir(parents=True, exist_ok=True)
    return home


def _launcher(home: Path, evidence: Path) -> Path:
    launcher = home / ".local" / "bin" / "start-hyprland"
    launcher.write_text(
        "#!/bin/bash\n"
        f'printf "%s\\n" "profil=${{1:-keins}}" >>"{evidence}/launcher"\n'
        # Liest stdin. Der echte start-hyprland tut das auch - mit einem
        # `read -p`, wenn kein Profil genannt wurde -, und ohne </dev/null
        # haengt eine Anmeldung genau dort.
        f'if read -r line; then printf "stdin=%s\\n" "$line" >>"{evidence}/launcher";'
        f' else printf "stdin=eof\\n" >>"{evidence}/launcher"; fi\n',
        encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


@pytest.mark.allow_subprocess
def test_the_first_login_generates_the_configuration_before_it_starts(tmp_path):
    """Auf einer frisch installierten Maschine gibt es
    ~/.local/bin/start-hyprland nicht: zepos-config legt nur
    /etc/skel/.config/zepos/user-settings.json an, und alles andere
    entsteht erst beim Erzeugen. Ohne diesen Schritt ist die erste
    Anmeldung eine Anmeldung in nichts - was auf dem installierten System
    gemessen wurde.
    """
    home = _session_home(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    launcher = home / ".local" / "bin" / "start-hyprland"
    stubs = _stubs(
        tmp_path / "stubs",
        # Der Stub tut, was der echte Generator tut: er schreibt den
        # Starter. Dass die Sitzung danach startet, ist damit die Folge
        # des Erzeugens und nicht eine zweite Behauptung.
        **{"zepos-generate": f'printf "%s\\n" "$@" >>"{evidence}/generate"\n'
                             f'printf "#!/bin/bash\\nprintf started >>{evidence}/launcher\\n"'
                             f' >"{launcher}"\nchmod 0755 "{launcher}"\n'},
    )
    result = _run(SESSION, stubs, HOME=str(home),
                  XDG_CONFIG_HOME=str(home / ".config"),
                  XDG_STATE_HOME=str(home / ".local" / "state"))
    conftest.assert_no_missing_command(result, "die Sitzung")

    assert (evidence / "generate").read_text(encoding="utf-8").split() == ["--all"]
    assert (evidence / "launcher").read_text(encoding="utf-8") == "started"


@pytest.mark.allow_subprocess
def test_a_saved_profile_is_handed_over_rather_than_auto_detected(tmp_path):
    """start-hyprland ohne Argument ueberschreibt monitors.conf mit
    "monitor=,preferred,auto,1". Bei jeder Anmeldung waere das die
    Monitoranordnung, die save-profile abgelegt hat, weggeworfen."""
    home = _session_home(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _launcher(home, evidence)
    (home / ".config" / "hypr").mkdir(parents=True)
    (home / ".config" / "hypr" / "current-profile").write_text(
        "schreibtisch\n", encoding="utf-8")
    (home / ".config" / "zepos" / "profiles" / "schreibtisch").mkdir(parents=True)

    stubs = _stubs(tmp_path / "stubs",
                   **{"zepos-generate": "exit 1\n"})
    result = _run(SESSION, stubs, HOME=str(home),
                  XDG_CONFIG_HOME=str(home / ".config"),
                  XDG_STATE_HOME=str(home / ".local" / "state"))
    conftest.assert_no_missing_command(result, "die Sitzung")

    assert "profil=schreibtisch" in (evidence / "launcher").read_text(encoding="utf-8")


@pytest.mark.allow_subprocess
def test_a_profile_that_is_gone_does_not_become_a_profile_argument(tmp_path):
    """current-profile ueberlebt ein geloeschtes Profil. Der Name daraus
    an start-hyprland gereicht ist ein "Profile 'x' not found!" und exit
    1 - also eine Anmeldung, die sofort wieder beim Greeter landet."""
    home = _session_home(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _launcher(home, evidence)
    (home / ".config" / "hypr").mkdir(parents=True)
    (home / ".config" / "hypr" / "current-profile").write_text(
        "weggeworfen\n", encoding="utf-8")

    stubs = _stubs(tmp_path / "stubs", **{"zepos-generate": "exit 1\n"})
    result = _run(SESSION, stubs, HOME=str(home),
                  XDG_CONFIG_HOME=str(home / ".config"),
                  XDG_STATE_HOME=str(home / ".local" / "state"))
    conftest.assert_no_missing_command(result, "die Sitzung")

    assert "profil=keins" in (evidence / "launcher").read_text(encoding="utf-8")


@pytest.mark.allow_subprocess
def test_the_launcher_is_never_left_waiting_for_an_answer(tmp_path):
    """Liegen Profile vor und wird keines genannt, fragt start-hyprland
    auf der Konsole nach. In einer Sitzung, die ein Greeter gestartet
    hat, sitzt dort niemand - ohne </dev/null bliebe die Anmeldung an
    einem read stehen, ohne Bild und ohne Meldung."""
    home = _session_home(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _launcher(home, evidence)

    stubs = _stubs(tmp_path / "stubs", **{"zepos-generate": "exit 1\n"})
    # Etwas zu lesen auf der Standardeingabe, damit die Messung ueberhaupt
    # eine ist: mit leerer Eingabe kaeme das Dateiende auch ohne
    # </dev/null, und der Test bewachte nichts.
    result = _run(SESSION, stubs, stdin="ja\n", HOME=str(home),
                  XDG_CONFIG_HOME=str(home / ".config"),
                  XDG_STATE_HOME=str(home / ".local" / "state"))
    conftest.assert_no_missing_command(result, "die Sitzung")

    assert "stdin=eof" in (evidence / "launcher").read_text(encoding="utf-8")


@pytest.mark.allow_subprocess
def test_a_session_that_cannot_start_says_so(tmp_path):
    """greetd startet nach einer beendeten Sitzung wieder den Greeter.
    Ein Bildschirm, der ohne ein Wort zur Anmeldemaske zurueckspringt,
    ist die Art Fehler, die niemand findet."""
    home = _session_home(tmp_path)
    stubs = _stubs(tmp_path / "stubs", **{"zepos-generate": "exit 1\n"})
    result = _run(SESSION, stubs, HOME=str(home),
                  XDG_CONFIG_HOME=str(home / ".config"),
                  XDG_STATE_HOME=str(home / ".local" / "state"))
    conftest.assert_no_missing_command(result, "die Sitzung")

    assert result.returncode == 1
    assert "start-hyprland" in result.stderr
    assert "zepos-doctor" in result.stderr


@pytest.mark.allow_subprocess
def test_what_went_wrong_outlives_the_session(tmp_path):
    """Unter XDG_STATE_HOME und nicht unter XDG_RUNTIME_DIR: eine
    Sitzung, die nicht hochkommt, nimmt ihr Laufzeitverzeichnis beim
    Abmelden mit - und genau dann will jemand nachlesen."""
    home = _session_home(tmp_path)
    state = home / ".local" / "state"
    stubs = _stubs(tmp_path / "stubs", **{"zepos-generate": "exit 1\n"})
    _run(SESSION, stubs, HOME=str(home),
         XDG_CONFIG_HOME=str(home / ".config"), XDG_STATE_HOME=str(state))

    log = state / "zepos" / "session.log"
    assert log.is_file(), f"kein Protokoll unter {log}"
    assert "Sitzung nicht gestartet" in log.read_text(encoding="utf-8")


# --------------------------------------------------------------------
# Was eine Aktualisierung mit der naechsten Anmeldung macht (UP-1)
# --------------------------------------------------------------------

def _updated_session(tmp_path: Path, *, marker_first: bool):
    """Eine Anmeldung, die einen Starter schon hat, und eine Marke.

    `marker_first` entscheidet die Reihenfolge der zwei Zeitstempel: die
    Marke der Selbstaktualisierung und der Stempel, den diese Sitzung
    beim letzten Erzeugen hinterlassen hat. Genau diese Reihenfolge ist
    die ganze Entscheidung.
    """
    home = _session_home(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    _launcher(home, evidence)

    state = home / ".local" / "state"
    stamp = state / "zepos" / "generated-at"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    marker_root = tmp_path / "var-lib-zepos"
    marker_root.mkdir(parents=True, exist_ok=True)
    marker = marker_root / "regenerate-required"

    first, second = (marker, stamp) if marker_first else (stamp, marker)
    first.write_text("", encoding="utf-8")
    os.utime(first, (1_700_000_000, 1_700_000_000))
    second.write_text("", encoding="utf-8")
    os.utime(second, (1_700_000_100, 1_700_000_100))

    stubs = _stubs(tmp_path / "stubs",
                   **{"zepos-generate": f'printf "%s\\n" "$@" '
                                        f'>>"{evidence}/generate"\n'})
    result = _run(SESSION, stubs, HOME=str(home),
                  XDG_CONFIG_HOME=str(home / ".config"),
                  XDG_STATE_HOME=str(state),
                  ZEPOS_STATE_ROOT=str(marker_root))
    conftest.assert_no_missing_command(result, "die Sitzung")
    return evidence, stamp


@pytest.mark.allow_subprocess
def test_an_update_reaches_the_desktop_at_the_next_login(tmp_path):
    """Die andere Haelfte von src/update.py.

    Ein `pacman -Syu` kann zepos-config austauschen, waehrend der
    Schreibtisch laeuft. Der Aktualisierer erzeugt deshalb NICHTS neu -
    generate_config.sh beendet an seinem Ende Waybar und AGS, und aus
    einem Zeitgeber heraus waere das eine Leiste, die dem Nutzer mitten
    in der Arbeit verschwindet. Er legt nur eine Marke ab.

    Ohne diesen Block waere die Folge, dass eine neue Fassung NIE
    ankommt: zepos-session erzeugt sonst ausschliesslich bei der ersten
    Anmeldung, und die war auf einer laufenden Maschine vor Monaten.
    """
    evidence, stamp = _updated_session(tmp_path, marker_first=False)

    assert (evidence / "generate").read_text(encoding="utf-8").split() == \
        ["--all"]
    assert (evidence / "launcher").read_text(encoding="utf-8"), \
        "die Sitzung ist nach dem Erzeugen nicht gestartet"
    assert stamp.stat().st_mtime > 1_700_000_100, (
        "der Stempel wurde nicht neu gesetzt - die naechste Anmeldung "
        "erzeugte wieder alles neu, jedes Mal")


@pytest.mark.allow_subprocess
def test_a_login_after_no_update_generates_nothing(tmp_path):
    """`zepos-generate --all` dauert auf einer frisch installierten
    Maschine rund 30 Sekunden, in denen der Nutzer einen schwarzen
    Bildschirm sieht. Bei jeder Anmeldung waere das der Preis fuer
    nichts."""
    evidence, _ = _updated_session(tmp_path, marker_first=True)

    assert not (evidence / "generate").exists(), (
        "es wurde neu erzeugt, obwohl die Marke aelter ist als das "
        "zuletzt Erzeugte")
    assert (evidence / "launcher").read_text(encoding="utf-8")


# --------------------------------------------------------------------
# Die Tastaturbelegung des Desktops
# --------------------------------------------------------------------
# GEFUNDEN am 17.08.2026: hyprland-universal-config.template trug
# `kb_layout = de` FEST EINGETRAGEN, fuer jede Installation dieselbe
# Zeile. Der Assistent laesst Deutsch oder Englisch waehlen, und die Wahl
# kam ueberall an ausser auf dem Desktop - eine englische Installation
# haette eine englische Konsole, eine englische Passphrase-Abfrage und
# eine deutsche Tastatur gehabt.
#
# Warum es niemand gemeldet hat: bisher hat niemand ZepOS auf Englisch
# installiert. Genau darum steht es hier als Test und nicht als Notiz.

VORLAGE = SRC / "templates" / "hyprland-universal-config.template"

# Vier Zeilen aus /usr/share/systemd/kbd-model-map, ABGESCHRIEBEN und
# nicht erfunden (gemessen am 17.08.2026). Die Spalten sind
# tabulatorgetrennt: Konsolenbelegung, XKB-Layout, Modell, Variante,
# Optionen. "-" heisst leer - und `de-latin1` traegt genau dort ein "-",
# waehrend `de-latin1-nodeadkeys` eine echte Variante hat. Beides wird
# unten gebraucht.
KBD_MODEL_MAP = (
    "us\t\t\tus\tpc105+inet\t-\t\tterminate:ctrl_alt_bksp\t\t\t\ten-US,en\n"
    "de-latin1\t\tde\tpc105\t\t-\t\tterminate:ctrl_alt_bksp\t\t\t\t-\n"
    "de-latin1-nodeadkeys\tde\tpc105\t\tnodeadkeys\tterminate:ctrl_alt_bksp\t\t\t\t-\n"
)


def _tastatur(tmp_path: Path, *, vconsole: str | None = None,
              mit_tabelle: bool = True, **umgebung: str) -> str:
    """Eine Anmeldung durchlaufen lassen und keyboard.conf zurueckgeben.

    Ausgefuehrt und nicht gelesen: welche der drei Quellen greift, ist
    eine Frage an die Verzweigung im Skript und nicht an seinen Text.
    """
    home = _session_home(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    _launcher(home, evidence)

    wurzel = tmp_path / "wurzel"
    (wurzel / "etc").mkdir(parents=True, exist_ok=True)
    if vconsole is not None:
        (wurzel / "etc" / "vconsole.conf").write_text(vconsole, encoding="utf-8")
    if mit_tabelle:
        (wurzel / "usr" / "share" / "systemd").mkdir(parents=True, exist_ok=True)
        (wurzel / "usr" / "share" / "systemd" / "kbd-model-map").write_text(
            KBD_MODEL_MAP, encoding="utf-8")

    stubs = _stubs(tmp_path / "stubs", **{"zepos-generate": "exit 1\n"})
    ergebnis = _run(SESSION, stubs, HOME=str(home),
                    XDG_CONFIG_HOME=str(home / ".config"),
                    XDG_STATE_HOME=str(home / ".local" / "state"),
                    ZEPOS_SESSION_ROOT=str(wurzel), **umgebung)
    conftest.assert_no_missing_command(ergebnis, "die Sitzung")
    return _read(home / ".config" / "hypr" / "keyboard.conf")


@pytest.mark.allow_subprocess
def test_the_layout_the_greeter_resolved_wins(tmp_path):
    """Erste Quelle: zepos-greeter hat die Frage schon beantwortet."""
    text = _tastatur(tmp_path, vconsole="KEYMAP=de-latin1\n",
                     XKB_DEFAULT_LAYOUT="fr", XKB_DEFAULT_VARIANT="bepo")

    assert "kb_layout = fr" in text
    assert "kb_variant = bepo" in text


@pytest.mark.allow_subprocess
def test_without_that_it_reads_the_layout_the_installer_wrote(tmp_path):
    """Zweite Quelle: XKBLAYOUT, von PLYMOUTH_COMMAND geschrieben."""
    text = _tastatur(tmp_path, vconsole="KEYMAP=de-latin1\nXKBLAYOUT=us\n")

    assert "kb_layout = us" in text, (
        "XKBLAYOUT steht in /etc/vconsole.conf und ist bereits aufgeloest")


@pytest.mark.allow_subprocess
def test_and_without_that_it_translates_the_console_keymap(tmp_path):
    """Dritte Quelle: archinstall schreibt NUR KEYMAP.

    Ohne diesen Schritt bliebe eine unverschluesselte englische
    Installation deutsch - PLYMOUTH_COMMAND laeuft dort nicht, also legt
    niemand XKBLAYOUT an.
    """
    text = _tastatur(tmp_path, vconsole="KEYMAP=us\n")
    assert "kb_layout = us" in text

    andere = _tastatur(tmp_path / "zweiter",
                       vconsole="KEYMAP=de-latin1-nodeadkeys\n")
    assert "kb_layout = de" in andere
    assert "kb_variant = nodeadkeys" in andere, (
        "die vierte Spalte der Tabelle ist die Variante und wird gebraucht")


@pytest.mark.allow_subprocess
def test_a_dash_in_the_table_is_not_a_variant(tmp_path):
    """`de-latin1` traegt in der Variantenspalte ein "-", und das heisst
    leer. Stuende es woertlich in der Datei, waere die Belegung kaputt."""
    text = _tastatur(tmp_path, vconsole="KEYMAP=de-latin1\n")

    assert "kb_layout = de" in text
    assert "kb_variant = -" not in text, '"-" heisst leer, nicht "-"'
    assert "kb_variant =" in text


@pytest.mark.allow_subprocess
def test_when_nothing_is_known_it_stays_german(tmp_path):
    """Dieselbe Wahl wie in zepos-greeter: "us" zu raten stellte genau
    den Fehler wieder her, den dieser Block entfernt."""
    text = _tastatur(tmp_path, vconsole=None, mit_tabelle=False)

    assert "kb_layout = de" in text


@pytest.mark.allow_subprocess
def test_a_session_still_starts_when_the_file_cannot_be_written(tmp_path):
    """Eine Sitzung, die wegen einer Tastaturzeile gar nicht erst
    startet, waere der teurere Fehler."""
    home = _session_home(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    _launcher(home, evidence)
    # Ein Hindernis, an dem `mkdir -p` scheitert: eine DATEI dort, wo das
    # Verzeichnis hin soll.
    (home / ".config" / "hypr").write_text("keine Sammelmappe", encoding="utf-8")

    stubs = _stubs(tmp_path / "stubs", **{"zepos-generate": "exit 1\n"})
    ergebnis = _run(SESSION, stubs, HOME=str(home),
                    XDG_CONFIG_HOME=str(home / ".config"),
                    XDG_STATE_HOME=str(home / ".local" / "state"))
    conftest.assert_no_missing_command(ergebnis, "die Sitzung")

    assert (evidence / "launcher").read_text(encoding="utf-8"), (
        "die Sitzung ist nicht gestartet, obwohl nur keyboard.conf fehlte")


def test_the_shipped_configuration_lets_that_file_override_it():
    """Die Einbindung muss HINTER dem input-Block stehen.

    Hyprland liest von oben nach unten. Stuende die Zeile davor, gewaenne
    die Auslieferung, und die Datei waere ein Stueck Text ohne Wirkung -
    ein Fehler, den man nur auf der Hardware saehe.
    """
    text = _read(VORLAGE)
    zeilen = text.splitlines()

    einbindung = [i for i, z in enumerate(zeilen)
                  if z.strip() == "source = ~/.config/hypr/keyboard.conf"]
    assert len(einbindung) == 1, (
        f"keyboard.conf wird {len(einbindung)}-mal eingebunden")

    ausgeliefert = [i for i, z in enumerate(zeilen)
                    if z.strip().startswith("kb_layout")]
    assert ausgeliefert, "die Vorlage nennt gar kein kb_layout mehr"
    assert max(ausgeliefert) < einbindung[0], (
        "die Einbindung steht VOR kb_layout - dann gewinnt die "
        "Auslieferung und die Belegung der Maschine wird nie wirksam")


# --------------------------------------------------------------------
# Die Sprache der Anmeldemaske
# --------------------------------------------------------------------
# DERSELBE BEFUND WIE OBEN, EINE SCHICHT FRUEHER (17.08.2026)
#     src/login/regreet.toml trug `locale = "de_DE"` und
#     `greeting_msg = "Willkommen bei ZepOS"` fest fuer jede
#     Installation. Eine englische Maschine bekam damit eine deutsche
#     Anmeldemaske - und das war die einzige deutsche Flaeche einer
#     sonst englischen Installation.
#
#     GEMESSEN an out/anmeldung/NACHHER-zeptronit-auswahl.png: von den
#     acht Zeichenketten dieser Maske sind genau diese zwei einstellbar.
#     Die restlichen sechs ("User:", "Session:", "Cancel", "Login",
#     "Reboot", "Power Off") sind Rust-Zeichenketten ohne gettext - es
#     gibt keinen Katalog zu fuellen und deshalb auch nichts anderes zu
#     uebersetzen.
#
# WARUM DIESE PRUEFUNGEN DAS SKRIPT AUSFUEHREN
#     Weil die Frage eine Verzweigung ist und keine Zeile Text: welche
#     Datei regreet am Ende BEKOMMT, entscheidet sich aus der Sprache,
#     aus XDG_RUNTIME_DIR und daraus, ob die Ersetzung ueberhaupt
#     zustande kam. Ein Test, der das Skript liest, kann jeden dieser
#     drei Faelle bestaetigen, ohne einen davon ausgeloest zu haben.
AUSGELIEFERTE_MASKE = LOGIN / "regreet.toml"


def _maske(tmp_path: Path, *, locale_conf: str | None = None,
           maske: str | None = None, **umgebung: str) -> tuple[str, str]:
    """Eine Anmeldung durchlaufen lassen.

    Zurueck kommt, was regreet WIRKLICH bekommen hat: der Pfad hinter
    --config und der Inhalt der Datei, die dort lag. Beides aus dem
    laufenden Prozess und nicht aus dem Skripttext.
    """
    root = _greeter_root(tmp_path)
    greetd = root / "etc" / "greetd"
    greetd.mkdir(parents=True, exist_ok=True)
    (greetd / "zepos-regreet.toml").write_text(
        maske if maske is not None else _read(AUSGELIEFERTE_MASKE),
        encoding="utf-8")
    if locale_conf is not None:
        (root / "etc" / "locale.conf").write_text(locale_conf,
                                                  encoding="utf-8")

    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    # regreet bekommt "--config PFAD --style PFAD", der Pfad ist also
    # $2. Gelesen wird die Datei mit bash allein: `cat` waere ein
    # weiteres Programm im Stub-Verzeichnis, und die Sicherheits-
    # begruendung dieser Datei zaehlt jedes einzeln auf.
    stubs = _stubs(
        tmp_path / "stubs",
        cage='shift 3\nexec "$@"\n',
        regreet=f'printf "%s" "$2" >"{evidence}/pfad"\n'
                'while IFS= read -r zeile || [[ -n "$zeile" ]]; do\n'
                '  printf "%s\\n" "$zeile"\n'
                f'done <"$2" >"{evidence}/maske"\n'
                "exit 0\n",
        tuigreet="exit 0\n",
    )
    ergebnis = _run(GREETER, stubs, ZEPOS_GREETER_ROOT=str(root),
                    XDG_RUNTIME_DIR=str(_runtime(tmp_path)),
                    HOME=str(tmp_path), **umgebung)
    conftest.assert_no_missing_command(ergebnis, "der Greeter")

    assert (evidence / "pfad").is_file(), (
        "regreet ist gar nicht gelaufen - die Maske kam nicht hoch:\n"
        + ergebnis.stdout + ergebnis.stderr)
    return (_read(evidence / "pfad"), _read(evidence / "maske"))


@pytest.mark.allow_subprocess
def test_a_german_machine_gets_exactly_what_the_package_ships(tmp_path):
    """Der Normalfall, und er muss der unveraenderte sein.

    /etc/greetd/zepos-regreet.toml steht in backup= des Pakets - es ist
    die Datei, an der ein Administrator dreht. Auf einer deutschen
    Maschine darf nichts danebengelegt und nichts ersetzt werden.
    """
    pfad, inhalt = _maske(tmp_path, locale_conf="LANG=de_DE.UTF-8\n")

    assert pfad.endswith("/etc/greetd/zepos-regreet.toml"), (
        f"regreet bekam {pfad} statt der ausgelieferten Datei")
    assert inhalt == _read(AUSGELIEFERTE_MASKE), (
        "die deutsche Maschine bekommt eine veraenderte Maske")


@pytest.mark.allow_subprocess
def test_an_english_machine_gets_an_english_mask(tmp_path):
    """Der Befund selbst: die Wahl des Assistenten kommt an.

    Geprueft wird ZEILENWEISE gegen die Auslieferung - dass genau zwei
    Zeilen anders sind und keine dritte. Eine Anmeldemaske, deren
    Konfiguration unterwegs noch etwas anderes verloren hat, faellt
    sonst erst auf der Hardware auf.
    """
    pfad, inhalt = _maske(tmp_path, locale_conf="LANG=en_US.UTF-8\n")

    assert not pfad.endswith("/etc/greetd/zepos-regreet.toml"), (
        "die englische Maschine bekommt weiter die deutsche Maske")

    ausgeliefert = _read(AUSGELIEFERTE_MASKE).splitlines()
    jetzt = inhalt.splitlines()
    assert len(jetzt) == len(ausgeliefert), (
        f"die Maske hat {len(jetzt)} Zeilen statt {len(ausgeliefert)}")
    anders = {alt: neu for alt, neu in zip(ausgeliefert, jetzt) if alt != neu}
    assert anders == {
        'locale = "de_DE"': 'locale = "en_US"',
        'greeting_msg = "Willkommen bei ZepOS"':
            'greeting_msg = "Welcome to ZepOS"',
    }, anders


@pytest.mark.allow_subprocess
def test_the_environment_is_asked_before_the_file(tmp_path):
    """Erste Quelle: LANG, das systemd an greetd.service weiterreicht.

    Ob es durch die PAM-Sitzung des Benutzers "greeter" ankommt, ist
    nicht zugesichert - deshalb ist es die erste und nicht die einzige
    Quelle. Wenn es ankommt, gilt es.
    """
    _pfad, inhalt = _maske(tmp_path, locale_conf="LANG=de_DE.UTF-8\n",
                           LANG="en_US.UTF-8")

    assert 'locale = "en_US"' in inhalt, (
        "die Umgebung sagt en_US und die Datei de_DE - gelesen wurde die "
        "Datei")


@pytest.mark.allow_subprocess
def test_without_a_language_it_stays_with_what_the_package_ships(tmp_path):
    """Es gibt keine /etc/locale.conf und kein LANG.

    Der Rueckfall MUSS die heutige Auslieferung sein: nicht leer, nicht
    halb, kein Abbruch. Hier wird ein Passwort getippt.
    """
    pfad, inhalt = _maske(tmp_path)

    assert pfad.endswith("/etc/greetd/zepos-regreet.toml")
    assert inhalt == _read(AUSGELIEFERTE_MASKE)


@pytest.mark.allow_subprocess
def test_a_language_this_tree_cannot_produce_is_not_written_in(tmp_path):
    """Eine Erlaubnisliste und keine Bequemlichkeit.

    regreets Uhr schlaegt ihren Namen in pure-rust-locales nach. Was ein
    unbekannter Name dort ausloest, laesst sich auf einer Maschine ohne
    Anmeldemaske nicht mehr nachmessen - also wird nur eingesetzt, was
    der Assistent selbst erzeugen kann.
    """
    pfad, inhalt = _maske(tmp_path, locale_conf="LANG=fr_FR.UTF-8\n")

    assert pfad.endswith("/etc/greetd/zepos-regreet.toml")
    assert inhalt == _read(AUSGELIEFERTE_MASKE)


@pytest.mark.allow_subprocess
def test_a_mask_without_those_two_keys_is_left_alone(tmp_path):
    """Ein Administrator hat eine der beiden Zeilen herausgenommen.

    Dann entsteht KEINE halbe Datei: es bleibt bei der seinen. Eine
    Ersetzung, die nur die Haelfte findet, waere eine Maske, in der
    genau der Wert fehlt, um dessentwillen sie entstanden ist.
    """
    ohne = "\n".join(
        zeile for zeile in _read(AUSGELIEFERTE_MASKE).splitlines()
        if not zeile.startswith("greeting_msg = ")) + "\n"
    pfad, inhalt = _maske(tmp_path, locale_conf="LANG=en_US.UTF-8\n",
                          maske=ohne)

    assert pfad.endswith("/etc/greetd/zepos-regreet.toml")
    assert inhalt == ohne


@pytest.mark.allow_subprocess
def test_without_a_runtime_directory_the_mask_still_comes_up(tmp_path):
    """Ohne XDG_RUNTIME_DIR gibt es keinen Platz fuer eine eigene Datei.

    Der grafische Versuch faellt dann ohnehin aus (siehe den Greeter),
    also darf hier nichts haengenbleiben und nichts abbrechen - der
    Textgreeter uebernimmt.
    """
    root = _greeter_root(tmp_path, drm=False)
    (root / "etc" / "greetd").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "greetd" / "zepos-regreet.toml").write_text(
        _read(AUSGELIEFERTE_MASKE), encoding="utf-8")
    (root / "etc" / "locale.conf").write_text("LANG=en_US.UTF-8\n",
                                              encoding="utf-8")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    stubs = _stubs(
        tmp_path / "stubs",
        cage="exit 1\n",
        tuigreet=f'printf tuigreet >>"{evidence}/order"\nexit 0\n',
    )
    ergebnis = _run(GREETER, stubs, ZEPOS_GREETER_ROOT=str(root),
                    HOME=str(tmp_path))
    conftest.assert_no_missing_command(ergebnis, "der Greeter")

    assert _read(evidence / "order") == "tuigreet", (
        "ohne Laufzeitverzeichnis kommt gar keine Maske mehr")


def test_the_two_languages_are_the_ones_the_installer_offers():
    """Die Erlaubnisliste im Greeter gegen die des Assistenten.

    LANGUAGE_DEFAULTS in installer/gui/pages.py ist die Quelle: was dort
    waehlbar ist, landet ueber archinstall in /etc/locale.conf. Eine
    dritte Sprache dort ohne eine Zeile im Greeter waere eine
    Installation, die sich waehlen laesst und deren Anmeldemaske
    trotzdem deutsch bleibt - genau der Befund, den dieser Abschnitt
    behebt, nur eine Sprache spaeter.
    """
    import sys

    sys.path.insert(0, str(ROOT))
    try:
        from installer.gui.pages import LANGUAGE_DEFAULTS
    finally:
        sys.path.remove(str(ROOT))

    text = _read(GREETER)
    fall = re.search(r"^case \"\$sprache\" in\n(.*?)^esac$", text, re.S | re.M)
    assert fall, "der Greeter entscheidet nicht mehr ueber die Sprache"

    for _kuerzel, (_keymap, locale, _zone) in sorted(LANGUAGE_DEFAULTS.items()):
        assert re.search(rf"^\s*{re.escape(locale)}\)", fall.group(1), re.M), (
            f"der Assistent bietet {locale} an, der Greeter kennt es "
            "nicht - diese Installation bekaeme eine deutsche Maske")
