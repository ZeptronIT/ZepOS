# SPDX-License-Identifier: GPL-3.0-or-later
"""Ist dieser Schreibtisch BENUTZBAR - nicht: ist er installiert.

WARUM DIESE DATEI EXISTIERT, UND SIE HAT EIN DATUM
    Am 11.08.2026 war jede Pruefung dieses Projekts gruen. Die
    Auslieferung baute, die Installation lief durch, die Sitzung kam
    hoch, 1871 Zusicherungen bestanden. Dann hat sich ein Mensch
    davorgesetzt und gesagt:

        "die nwg dock unten geht nicht mehr dateien und datei manager
         ist auch nicht vorhanden und screenshot tool auch nicht es
         fehlt gefuehlt alles"

    Er hatte in jedem Punkt recht. Das Dock war unsichtbar, weil es sich
    ohne offene Fenster selbst versteckte. Der Dateimanager war
    vorhanden - und die Taste dafuer zeigte bis kurz zuvor auf thunar,
    das kein Paket installiert. Das Bildschirmfoto-Werkzeug lag
    vollstaendig auf der Platte und war nicht zu finden.

    Keine dieser drei Aussagen laesst sich einer Paketliste entnehmen,
    und genau daran ist die vorhandene Pruefung vorbeigelaufen: sie hat
    "ist installiert und startet" bestaetigt, waehrend "kann man damit
    arbeiten" nirgends gefragt wurde.

DIE FRAGE, DIE HIER GESTELLT WIRD
    Fuer jedes Bedienelement, das ZepOS anbietet: kommt dahinter etwas
    an? Fuenf Formen davon, und sie sind nach Kosten sortiert - die
    billigste zuerst, weil sie zugleich die ist, die den Fehler vom
    11.08.2026 vierfach gefunden haette:

      1. Jedes Programm, das eine Taste oder eine Startzeile der
         ERZEUGTEN Konfiguration nennt, kommt aus der ausgelieferten
         Auswahl. Eine reine Rechnung, kein QEMU, keine Maschine.
      2. Die Tastenuebersicht, die der Nutzer zu sehen bekommt, nennt
         dieselben Programme wie die Bindungen darunter.
      3. Ein Dateimanager ist da, und mehr als eine Stelle oeffnet ihn.
      4. Das Bildschirmfoto-Werkzeug ist vollstaendig UND auffindbar.
      5. Der Anwendungsstarter zeigt auf etwas, das es gibt.

    Was hier NICHT beantwortet werden kann, steht in
    test_the_acceptance_that_still_needs_a_machine unten - und es steht
    dort als Zusicherung ueber das Skript, das es beim naechsten
    QEMU-Lauf beantworten wird, nicht als Absichtserklaerung.

WOGEGEN GEMESSEN WIRD
    Gegen den Baum, den EIN vollstaendiger `--all`-Lauf hinterlaesst,
    nicht gegen die Vorlagen. Der Unterschied ist nicht kosmetisch:
    plugins.py entscheidet beim Erzeugen, welche Bindung ueberhaupt in
    die Datei kommt, und eine Pruefung an der Vorlage misst Zeilen, die
    auf keiner Installation stehen.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from tests.generated_tree import GeneratedTree, build

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
PACKAGING = REPOSITORY / "packaging"

# Der Lauf spawnt den Generator. Die Marke steht auf dem MODUL und nicht
# auf dem ersten Test, aus demselben Grund wie in
# tests/src/test_reference_resolution.py: welchen Test pytest zuerst
# erreicht, entscheidet die Auswahl, und mit `-k` wuerde sonst die
# Weigerung des Waechters zum Fehlschlag.
pytestmark = pytest.mark.allow_subprocess


def _module(name: str, path: Path):
    """Ein Modul aus src/, so geladen, wie der Generator es laedt.

    Dieselbe Form wie in tests/src/test_gtk4_only.py und aus demselben
    Grund: src/ hat kein __init__.py, und doctor.py importiert seine
    Nachbarn beim Namen.
    """
    sys.path.insert(0, str(SRC))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SRC))


doctor = _module("zepos_doctor_usable_probe", SRC / "doctor.py")
apps = _module("zepos_apps_usable_probe", SRC / "apps.py")
# Der eine Leser fuer Hyprlands Tastenzeilen. Seit dem 12.08.2026 kommen
# die Beschreibungen aus der Konfiguration selbst, also wird hier
# dieselbe Datei gelesen, die auch die Uebersicht liest - nicht eine
# Tabelle daneben, die es nicht mehr gibt.
keybinds = _module("zepos_keybinds_usable_probe", SRC / "keybinds.py")


@pytest.fixture(scope="module")
def tree(tmp_path_factory) -> GeneratedTree:
    return build(tmp_path_factory.mktemp("usable-desktop"))


# --------------------------------------------------------------------
# was die Auslieferung enthaelt
# --------------------------------------------------------------------

_DEPENDS = re.compile(r"^depends=\((.*?)^\)", re.S | re.M)


def _code(text: str) -> str:
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def _depends(recipe: str) -> list[str]:
    text = (PACKAGING / recipe / "PKGBUILD").read_text(encoding="utf-8")
    body = _DEPENDS.search(text)
    assert body, f"{recipe} hat keine depends-Liste"
    return re.findall(r"'([^']+)'", _code(body.group(1)))


def _provides(recipe: str) -> list[str]:
    text = _code((PACKAGING / recipe / "PKGBUILD").read_text(encoding="utf-8"))
    found: list[str] = []
    for block in re.findall(r"^provides=\((.*?)\)", text, re.S | re.M):
        for name in re.findall(r"""['"]?([A-Za-z][\w.+-]*)""", block):
            found.append(name.split("=")[0])
    return found


def shipped_packages() -> set[str]:
    """Jeder Paketname, den eine ZepOS-Installation bekommt.

    Die Rezepte selbst gehoeren dazu: `zepos-menu` ist ein Paket dieses
    Projekts, kein Fremdpaket, und ein Bedienelement, das darauf zeigt,
    zeigt auf etwas, das mitkommt.
    """
    names = {path.parent.name for path in PACKAGING.glob("*/PKGBUILD")}
    for recipe in ("zepos-desktop", "zepos-apps"):
        names.update(_depends(recipe))
        names.update(_provides(recipe))
    for recipe in sorted(path.parent.name
                         for path in PACKAGING.glob("zepos-*/PKGBUILD")):
        names.update(_provides(recipe))
    return names


# Kommando -> Paket, und NUR fuer die Faelle, in denen die beiden nicht
# gleich heissen.
#
# Keine Uebersetzungstabelle fuer alles: die grosse Mehrheit der Namen
# in einer Bindung IST der Paketname (grim, slurp, satty, kitty,
# nautilus, firefox, playerctl, ...), und eine Tabelle, die auch die
# aufzaehlt, ist eine Tabelle, die jemand pflegen muss. Was hier steht,
# ist genau das, was sich nicht ausrechnen laesst - jeder Eintrag mit
# dem Paket, das die Datei besitzt.
#
# Die Tabelle wird in BEIDE Richtungen geprueft: jedes Paket hier muss
# wirklich ausgeliefert werden, und jeder Eintrag muss von mindestens
# einer Bindung gebraucht werden. Ein Eintrag, den niemand mehr braucht,
# ist ein Freibrief, den beim naechsten Lesen jemand fuer gueltig haelt.
PROVIDED_BY = {
    "ags": "aylurs-gtk-shell",
    "hyprctl": "hyprland",
    "wl-paste": "wl-clipboard",
    "pactl": "libpulse",
    "notify-send": "libnotify",
    "gsettings": "glib2",
    # Das Fenster heisst nach seiner Aufgabe, das Paket nach seinem
    # Projekt. Aufgerufen wird es vom Bluetooth-Feld der Leiste und von
    # der Kontrollzentrale.
    "blueman-manager": "blueman",
    # nmcli, seit dem 17.08.2026. Es stand nie hier, weil der Waechter
    # nur `onClick:` und `spawn_command_line_async` gelesen hat - das
    # Netzfenster schaltet den Adapter aber ueber execAsync um, und
    # dieselbe Zeile ruft es zweimal. Das Paket ist ohnehin eine harte
    # Abhaengigkeit von zepos-desktop, weil die Statusskripte es rufen.
    "nmcli": "networkmanager",
    # Der volle Pfad und nicht der Dateiname: so steht er in der
    # exec-once-Zeile, und der Paketname steckt nicht darin.
    "/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1": "polkit-gnome",
    # zepos-claude-code, seit dem 01.09.2026. Der Befehl heisst wie das
    # PAKET, das ihn bis dahin trug - und dieses Paket gibt es nicht
    # mehr: der Nutzer hat es gestuerzt, weil es Anthropics Programm
    # unter einem ZepOS-Namen weitergab ("ich will das packet nicht als
    # meins verkaufen"). Der Befehl ist geblieben und liegt jetzt bei
    # den anderen neun zepos-* Befehlen in zepos-config.
    #
    # OHNE DIESE ZEILE WAERE DIE exec-once-STARTZEILE EINE TOTE
    # REFERENZ, und dieser Test hat genau das gemeldet, als sie
    # dazukam. tests/src/test_claude_code.py misst die andere Haelfte:
    # dass das Rezept den Befehl wirklich ablegt.
    "zepos-claude-code": "zepos-config",
}

# Kommandos aus dem Grundsystem, mit dem Paket, das jedes traegt -
# gemessen mit `pacman -Qo` am 11.08.2026 auf einer Arch-Maschine.
#
# WARUM DIESE LISTE ERLAUBT IST UND NICHT DIE NAECHSTE LUECKE
#     `LC_ALL=C pacman -Qi base` nennt am selben Tag: filesystem
#     gcc-libs glibc bash coreutils file findutils gawk grep procps-ng
#     sed tar gettext pciutils psmisc shadow util-linux bzip2 gzip xz
#     licenses pacman archlinux-keyring systemd systemd-sysvcompat
#     iputils iproute2. Jedes Paket unten steht darin, und `base` ist
#     das, was archinstall in JEDE Installation pacstrapt - eine
#     Installation ohne coreutils gibt es nicht.
#
#     Die eine Ausnahme ist dbus, und sie ist benannt statt verschwiegen:
#     es steht nicht selbst in `base`, sondern ist harte Abhaengigkeit
#     von systemd, das darin steht ("Depends On: ... dbus dbus-units
#     ...").
#
#     Was hier NICHT hineindarf, ist ein Programm mit einer Oberflaeche.
#     Genau diese Grenze macht die Liste harmlos: sie deckt `cp` und
#     `sleep` ab und kann keinen Dateimanager durchlassen.
#
#     VIER EINTRAEGE SIND AM 17.08.2026 DAZUGEKOMMEN, und sie sind kein
#     Zuwachs an Erlaubnis, sondern einer an Sicht: der Waechter las bis
#     dahin nur `onClick:` und `spawn_command_line_async`. Was die
#     Aufklappfenster ueber Astals execAsync rufen - `df` und `findmnt`
#     im Speicherplatzfenster, `pgrep` im Kontrollzentrum, `cat` in der
#     Hintergrundauswahl - war fuer ihn unsichtbar. Jetzt steht es da,
#     und jedes der vier kommt aus `base`.
BASE_SYSTEM = {
    "cat": "coreutils",
    "cp": "coreutils",
    "date": "coreutils",
    "df": "coreutils",
    "sleep": "coreutils",
    "grep": "grep",
    "pgrep": "procps-ng",
    "pkill": "procps-ng",
    "findmnt": "util-linux",
    "setsid": "util-linux",
    "systemctl": "systemd",
    "dbus-update-activation-environment": "dbus",
}

# Die Dateien einer Installation, die Tasten und Startzeilen tragen.
# Dieselben, die zepos-doctor auf der laufenden Maschine liest - die
# Liste steht dort und nicht hier, damit sie nicht zweimal existiert.
def _bound(tree: GeneratedTree) -> list[tuple[str, str, str]]:
    """(Datei, Taste, Programm) fuer jede Bindung im erzeugten Baum."""
    found: list[tuple[str, str, str]] = []
    for where in doctor.BOUND_CONFIGS:
        config = tree.config.joinpath(*where)
        if not config.is_file():
            continue
        for key, command in doctor.bound_commands(config.read_text()):
            found.append((config.name, key, command))
    assert found, "der erzeugte Baum enthaelt keine einzige Bindung"
    return found


# --------------------------------------------------------------------
# 1. jede Taste zeigt auf ein Programm, das mitkommt
# --------------------------------------------------------------------

def test_every_key_and_every_startup_line_names_a_program_zepos_ships(tree):
    """Die Zusicherung, die den Fehler vom 11.08.2026 vierfach gefunden
    haette.

    SUPER+E auf thunar, SUPER+T auf einen Symlink zu sublime-text-4,
    SUPER+SHIFT+T auf ferdium, der Druckerknopf auf ein lpstat, das es
    nicht gab - vier Bedienelemente, vier Programme, die kein Paket
    dieses Projekts installiert, und kein einziger Fehlschlag irgendwo.
    Hyprland fuehrt `exec` aus, die Shell findet nichts, und das war es.

    GEPRUEFT WIRD JEDES WORT DER ZEILE, NICHT DAS ERSTE
        `grim -g "$(slurp)" - | satty -f -` nennt drei Programme. Eine
        Pruefung, die nur `grim` liest, haette das Bildschirmfoto-
        Werkzeug fuer vollstaendig gehalten, waehrend die Haelfte davon
        fehlt - und genau diese Haelfte hat der Nutzer vermisst. Wie die
        Zerlegung geht und was sie nicht sieht, steht bei
        doctor.command_words().
    """
    shipped = shipped_packages()
    unreachable = []
    for config, key, command in _bound(tree):
        if command.startswith(("~", "./", "../")):
            # Ein Pfad im Heimatverzeichnis ist eine Datei, die dieser
            # Lauf erzeugt haben muss. Das ist die Frage der Zusicherung
            # darunter; hier geht es um Programme aus Paketen.
            continue
        # Ein absoluter Pfad ausserhalb des Heimatverzeichnisses gehoert
        # einem Fremdpaket - und dessen Name steht nicht im Pfad
        # (/usr/lib/polkit-gnome/... kommt aus polkit-gnome). Er MUSS
        # also in der Tabelle stehen, sonst faellt er durch jede Pruefung
        # dieser Datei hindurch.
        package = PROVIDED_BY.get(command, command)
        if package in shipped or command in BASE_SYSTEM:
            continue
        unreachable.append(f"{config}: {key} ruft {command}")

    assert unreachable == [], (
        "Bedienelemente, hinter denen kein ausgeliefertes Paket steht: "
        + "; ".join(unreachable))


def test_every_generated_path_a_key_calls_was_really_generated(tree):
    """Die andere Haelfte derselben Frage.

    Sechs Tasten und fuenf Startzeilen rufen keine Programme aus Paketen
    auf, sondern Skripte, die dieser Lauf selbst schreiben muss. Ein
    Skript, das keine Route im Generator hat, landet woanders oder gar
    nicht - und die Taste ist genauso stumm wie eine auf ein fehlendes
    Paket.
    """
    missing = []
    for config, key, command in _bound(tree):
        if not command.startswith(("~", "./", "../")):
            # Alles andere gehoert einem Paket und wird von der
            # Zusicherung darueber beantwortet.
            continue
        target = Path(tree.expand(command))
        if not target.is_file():
            missing.append(f"{config}: {key} ruft {command}")

    assert missing == [], (
        "Tasten auf Skripte, die der Lauf nicht erzeugt hat: "
        + "; ".join(missing))


def test_both_tables_are_honest_in_both_directions(tree):
    """Eine Tabelle, die nicht schrumpft, waechst zu einer Ausrede.

    Beide Richtungen, weil jede fuer sich harmlos aussieht: ein Eintrag,
    der auf ein Paket zeigt, das ZepOS gar nicht ausliefert, laesst eine
    Bindung durch, die ins Leere geht - und ein Eintrag, den keine
    Bindung mehr braucht, ist eine Erlaubnis, die beim naechsten Lesen
    jemand fuer eine Regel haelt.
    """
    shipped = shipped_packages()
    named = {command for _, _, command in _bound(tree)}
    # Und die Klicks. Seit dem 12.08.2026 gehoeren sie zu denselben
    # Tabellen - blueman-manager steht in KEINER Bindung und in zwei
    # Klicks, und ohne diese Zeile waere sein Eintrag oben ein
    # Freibrief, den die Richtungspruefung fuer unbenutzt erklaert.
    for _, command in _bar_clicks(tree):
        named.update(doctor.command_words(command))

    for command, package in sorted(PROVIDED_BY.items()):
        assert package in shipped, (
            f"PROVIDED_BY sagt, {command} komme aus {package} - und "
            f"{package} wird nicht ausgeliefert")
        assert command in named, (
            f"PROVIDED_BY nennt {command}, und keine Bindung ruft es "
            f"mehr auf. Eintrag loeschen.")

    for command in sorted(BASE_SYSTEM):
        assert command in named, (
            f"BASE_SYSTEM nennt {command}, und keine Bindung ruft es "
            f"mehr auf. Eintrag loeschen.")
        assert command not in PROVIDED_BY, (
            f"{command} steht in beiden Tabellen")


def test_the_check_would_catch_a_key_that_points_at_nothing():
    """Die Selbstpruefung, ohne die alles darueber wertlos ist.

    Eine Zerlegung, die nichts findet, laesst jede Bindung durch und
    meldet Ruhe - genau der Zustand, in dem die vorhandene Pruefung am
    11.08.2026 war. Also wird sie hier gegen Zeilen gehalten, die sie
    finden MUSS, und gegen Zeilen, die sie in Ruhe lassen muss.
    """
    findings = doctor.bound_commands(
        "bind = $mainMod, E, exec, thunar\n"
        "bind = $mainMod SHIFT, T, exec, ferdium\n"
        'bind = $mainMod, S, exec, grim -g "$(slurp)" - | satty -f -\n'
        "bind = , XF86AudioMute, exec, pactl set-sink-mute @DEFAULT_SINK@ toggle\n"
        "exec-once = wl-paste --watch cliphist store\n"
        "bind = $mainMod, L, exec, zepos-lock\n")
    programs = [command for _, command in findings]

    # Die vier, die am 11.08.2026 wirklich dastanden, und die drei
    # Haelften einer Kette, die nur eine Zerlegung sieht.
    # cliphist steht ABSICHTLICH nicht in dieser Reihe: in
    # `wl-paste --watch cliphist store` ist es ein Argument von wl-paste
    # und kein eigener Aufruf. Eine Zerlegung, die es trotzdem melden
    # wuerde, meldete jedes zweite Wort einer Kommandozeile.
    for expected in ("thunar", "ferdium", "grim", "slurp", "satty",
                     "pactl", "wl-paste", "zepos-lock"):
        assert expected in programs, (
            f"die Zerlegung findet {expected} nicht: {programs}")

    # Und die Taste steht dabei, sonst ist die Meldung nicht nachstellbar.
    assert ("SUPER+E", "thunar") in findings, findings

    # Was sie in Ruhe lassen muss: eine auskommentierte Zeile, ein
    # Dispatcher ohne exec, und die Woerter der Shell selbst.
    quiet = doctor.bound_commands(
        "# bind = $mainMod, E, exec, thunar\n"
        "bind = $mainMod SHIFT, Z, hyprzones:editor,\n"
        "bind = $mainMod, G, exec, hyprctl keyword general:layout "
        "\"$(hyprctl getoption general:layout | grep -q 'dwindle' "
        "&& echo 'master' || echo 'dwindle')\"\n")
    words = [command for _, command in quiet]
    assert "thunar" not in words, f"eine Kommentarzeile wurde gelesen: {words}"
    assert "hyprzones:editor" not in words, (
        f"ein Dispatcher wurde fuer ein Programm gehalten: {words}")
    assert "echo" not in words, f"ein Shell-Wort wurde gemeldet: {words}"
    assert sorted(set(words)) == ["grep", "hyprctl"], words


def test_the_doctor_reports_a_key_that_points_at_nothing(tmp_path):
    """Und dasselbe an der laufenden Maschine, ueber zepos-doctor.

    Die Testsuite faengt es vor der Auslieferung; sie kann aber nicht
    wissen, was auf der Maschine eines Nutzers wirklich liegt. Ein
    `pacman -Rns`, ein Paket, das ein Programm umbenennt, eine eigene
    Bindung in profile-keybinds.conf - drei Wege in denselben Zustand,
    und keiner davon geht durch diesen Baum.
    """
    conf = tmp_path / "hyprland.conf"
    conf.write_text(
        "bind = $mainMod, E, exec, ein-dateimanager-den-es-nicht-gibt\n"
        "bind = $mainMod, Q, exec, sh\n")

    findings = doctor.check_bindings([conf], home=tmp_path)
    assert len(findings) == 1, [str(finding) for finding in findings]
    assert "ein-dateimanager-den-es-nicht-gibt" in findings[0].what
    assert "SUPER+E" in findings[0].what, findings[0].what
    # Und die drei Teile, die eine Meldung dieses Programms tragen muss.
    assert findings[0].costs and findings[0].fix

    # Die Gegenrichtung: eine Datei, in der alles erreichbar ist, ergibt
    # nichts. Ohne das waere die Zusicherung darueber auch von einer
    # Pruefung erfuellt, die IMMER meldet.
    fine = tmp_path / "sauber.conf"
    fine.write_text("bind = $mainMod, Q, exec, sh\n")
    assert doctor.check_bindings([fine], home=tmp_path) == []


# --------------------------------------------------------------------
# 2. die Tastenuebersicht sagt dasselbe wie die Bindungen
# --------------------------------------------------------------------
#
# WAS HIER STAND UND WARUM ES WEG IST
#     Zwei Zusicherungen, die die von Hand gepflegte Tabelle in
#     ags/scripts/hypr-shortcuts.py gegen die bind-Zeilen der Vorlagen
#     hielten - Taste fuer Taste und Programmname fuer Programmname. Sie
#     haben den Fund gemacht, aus dem diese Datei ihren Namen hat:
#     "SUPER + SHIFT + B - Browser (Epiphany)" ueber einer Bindung, die
#     firefox startet.
#
#     Was sie nicht konnten: die ZWEITE Tabelle sehen. Dieselbe Luege
#     stand in ags/widget/Shortcuts.tsx, wurde dort nicht korrigiert und
#     stand am 12.08.2026 noch immer da. Und sie konnten nicht sehen, was
#     in KEINER Tabelle stand - 19 gebundene Tasten, gemessen an einem
#     vollstaendigen Lauf.
#
#     Beide Tabellen sind entfallen. Die Beschreibungen stehen jetzt als
#     `# @Gruppe: Text` ueber den bind-Zeilen selbst; die Uebersicht wird
#     daraus abgeleitet und kann nichts anderes mehr sagen als sie. Die
#     Zusicherungen dazu stehen in tests/src/test_keybinds.py.
#
#     Was hier BLEIBT, ist die eine Frage, die auch eine abgeleitete
#     Uebersicht falsch beantworten kann: eine Beschreibung, die ein
#     Programm nennt, das ZepOS gar nicht ausliefert. keybinds haelt
#     Taste und Text zusammen, nicht Text und Auswahl.

# Programme, die ZepOS abgewaehlt hat. Ein Name von hier in einer
# Beschreibung ist eine Anleitung zu etwas, das es auf keiner
# Installation gibt - und die Beschreibung ist die einzige Stelle, an der
# ein Nutzer nachsehen kann, was eine Taste tut.
#
# epiphany steht hier, weil genau das passiert war: die Auswahl hatte
# ihn, wurde am 11.08.2026 auf firefox geaendert, und die Uebersicht ist
# stehengeblieben.
DROPPED = ("epiphany", "thunar", "ferdium", "ncspot", "sublime", "chromium",
           "wofi", "waybar", "nwg-dock-hyprland", "mako", "dolphin")


def _descriptions(tree: GeneratedTree) -> list[tuple[str, str]]:
    """(Taste, Beschreibung) fuer jede beschriebene Bindung des Laufs."""
    found = [(binding.chord, binding.description)
             for binding in keybinds.described(
                 keybinds.read(root=tree.config))]
    assert found, "der erzeugte Baum hat keine beschriebene Bindung"
    return found


def test_no_description_names_a_program_zepos_does_not_ship(tree):
    """Die Haelfte, die eine Ableitung nicht von selbst richtig macht.

    Dass die Beschreibung neben ihrem Kommando steht, verhindert, dass
    sie eine ANDERE Taste beschreibt. Es verhindert nicht, dass jemand
    ein Programm hineinschreibt, das dieses Projekt abgewaehlt hat - und
    ein Nutzer, der dort "Thunar" liest, sucht danach einen
    Dateimanager, den seine Maschine nicht hat.
    """
    named = []
    for chord, description in _descriptions(tree):
        words = description.lower()
        for dropped in DROPPED:
            if dropped in words:
                named.append(f"{chord} nennt {dropped}")

    assert named == [], (
        "Beschreibungen, die Programme nennen, die ZepOS nicht mehr "
        "ausliefert: " + "; ".join(named))


def test_every_key_is_described_once_and_the_overview_shows_all_of_them(tree):
    """Die Zahl, die vorher niemand kannte.

    Die beiden Tabellen hielten 65 und 77 Eintraege fuer 86 gebundene
    Tastenkombinationen, und niemand konnte sagen, welche fehlten. Jetzt
    ist die Antwort eine Rechnung: so viele Beschreibungen wie
    Bindungen, in jeder Datei, die eine Taste tragen kann.
    """
    for where in keybinds.OVERVIEW_CONFIGS:
        config = tree.config.joinpath(*where)
        if not config.is_file():
            continue
        parsed = keybinds.parse(config.read_text(), config.name)
        nameless = [binding.where for binding in parsed
                    if not binding.description]
        assert nameless == [], (
            f"{config.name}: Tasten, die in keiner Uebersicht stehen "
            f"koennen: {nameless}")


# --------------------------------------------------------------------
# 3. der Dateimanager
# --------------------------------------------------------------------

def test_a_file_manager_is_shipped_and_more_than_one_place_opens_it(tree):
    """"datei manager ist auch nicht vorhanden", woertlich geprueft.

    Drei Wege muessen zu ihm fuehren, und dass es drei sind, ist die
    Aussage: eine Taste kennt nur, wer sie kennt. Ein Nutzer, der von
    einem anderen System kommt, sucht ein Symbol - und findet es seit
    dieser Aenderung auf dem Dock.
    """
    shipped = set(_depends("zepos-apps"))
    managers = [name for name in ("nautilus", "thunar", "dolphin", "nemo")
                if name in shipped]
    assert len(managers) == 1, (
        f"ZepOS liefert {len(managers)} Dateimanager aus: {managers}. "
        "Die Regel von zepos-apps ist EINE Anwendung je Aufgabe.")
    manager = managers[0]

    # 1. die Taste
    keys = [key for _, key, command in _bound(tree) if command == manager]
    assert keys, f"keine Taste oeffnet {manager}"

    # 2. der Knopf im Datentraeger-Widget
    disk = (tree.config / "ags" / "widget" / "DiskUsage.tsx").read_text()
    assert manager in disk, (
        f"der Dateien-Knopf des Datentraeger-Widgets oeffnet nicht {manager}")

    # 3. das Dock - und das ist der Weg, den es am 11.08.2026 nicht gab
    dock = (tree.config / "ags" / "widget" / "Dock.tsx").read_text()
    pinned = re.search(r"^const PINNED: string\[\] = (\[.*?\])", dock, re.M)
    assert pinned, "das erzeugte Dock traegt keine Liste angehefteter Anwendungen"
    assert f'"{manager}"' in pinned.group(1), (
        f"das Dock heftet {manager} nicht an: {pinned.group(1)}")


# --------------------------------------------------------------------
# 4. das Bildschirmfoto-Werkzeug
# --------------------------------------------------------------------

def test_the_screenshot_key_has_every_half_of_its_chain(tree):
    """"screenshot tool auch nicht" - und es war die ganze Zeit da.

    grim schneidet, slurp waehlt den Bereich, satty zeigt das Ergebnis
    zum Beschriften. Drei Programme in EINER Zeile, und eine Pruefung,
    die nur das erste Wort liest, haette die Kette fuer vollstaendig
    gehalten, waehrend zwei Drittel fehlen.
    """
    shipped = shipped_packages()
    screenshot = [(key, command) for _, key, command in _bound(tree)
                  if command in ("grim", "slurp", "satty")]
    assert {command for _, command in screenshot} == {"grim", "slurp", "satty"}, (
        f"die Bildschirmfoto-Kette ist nicht vollstaendig gebunden: {screenshot}")
    for _key, command in screenshot:
        assert command in shipped, f"{command} wird nicht ausgeliefert"

    # Und die Aufnahme daneben, aus derselben Beschwerde.
    recorder = [key for _, key, command in _bound(tree)
                if command == "wf-recorder"]
    assert recorder, "keine Taste nimmt den Bildschirm auf"
    assert "wf-recorder" in shipped


def test_the_screenshot_tool_can_be_found_without_knowing_the_key(tree):
    """Vorhanden und unauffindbar ist dasselbe wie nicht vorhanden.

    Das ist der Teil der Beschwerde, den keine Paketliste je gemeldet
    haette: grim, slurp und satty lagen auf der Maschine, SUPER+S rief
    sie, und der Nutzer hat es nicht gefunden.

    ZWEI WEGE, UND ZWAR SEIT DEM 12.08.2026 ZWEI
        Am 11.08.2026 gab es genau einen: die Tastenuebersicht der
        Leiste. Sie setzt voraus, dass jemand auf die Idee kommt, dort
        nachzusehen, und dass er sie findet. Der zweite Weg ist die
        Suche - man tippt "bild", und die Zeile steht da, mit ihrer
        Taste daneben.
    """
    described = dict(_descriptions(tree))
    assert "SUPER + S" in described, (
        "SUPER+S traegt keine Beschreibung und steht damit in keiner "
        "Uebersicht und in keiner Suche")

    text = " ".join(description for chord, description in described.items()
                    if chord in ("SUPER + S", "SUPER + ALT + S")).lower()
    assert any(word in text for word in ("screenshot", "bildschirm")), (
        f"SUPER+S ist nicht als Bildschirmfoto beschrieben - wer danach "
        f"sucht, findet es nicht: {text!r}")

    # Und der zweite Weg: eine Taste, die alles durchsucht, mit einer
    # Beschreibung, unter der man sie selbst findet.
    search = [key for _config, key, command in _bound(tree)
              if command == "zepos-menu"]
    assert search, "keine Taste oeffnet die Suche"


# --------------------------------------------------------------------
# 5. der Anwendungsstarter
# --------------------------------------------------------------------

def test_the_application_launcher_points_at_something_that_exists(tree):
    """SUPER+SPACE, in beiden Faellen.

    Mit hyprlaunch ist es das Plugin, ohne es zepos-menu. Der Testbaum
    hat absichtlich kein Plugin - also misst diese Zusicherung genau den
    Rueckfall, und der ist der wichtigere: er greift auf jeder Maschine,
    auf der das Plugin nicht gebaut werden konnte, und dort kann sich
    sonst niemand mehr beschweren.
    """
    launcher = [command for _, key, command in _bound(tree)
                if key == "SUPER+SPACE"]
    assert launcher, "SUPER+SPACE startet nichts"
    assert "zepos-menu" in launcher, (
        f"der Rueckfall des Anwendungsstarters fehlt: {launcher}")
    assert "zepos-menu" in shipped_packages()

    # Und das Programm dahinter ist eines, das dieses Projekt baut - also
    # muss es ein Rezept dafuer geben.
    assert (PACKAGING / "zepos-menu" / "PKGBUILD").is_file()


# --------------------------------------------------------------------
# 5b. jeder Klick auf der Leiste erreicht ein Programm, das mitkommt
# --------------------------------------------------------------------
#
# GEMELDET am 12.08.2026, nachdem ein Mensch das gebaute Medium benutzt
# hatte: "in der Leiste stehen Symbole ohne Funktion". Er hatte recht,
# und die Zahl dazu ist gemessen - DREI der achtzehn Module riefen ein
# Programm, das kein Rezept dieses Projekts ausliefert:
#
#     custom/hypr-shortcuts, rechter Klick   sub ~/.config/hypr/...
#     custom/hardware, linker Klick          kitty -e btop
#     custom/hardware, rechter Klick         kitty -e watch -n 1 sensors
#     bluetooth, linker Klick                blueman-manager  (optdepends)
#
# WARUM DIE VORHANDENE PRUEFUNG SIE NICHT GEFUNDEN HAT
#     Sie liest Hyprlands Konfigurationsdateien, und die Leiste ist
#     keine. `sub` ist derselbe tote Name, den dieselbe Suite in der
#     TASTE gefunden und berichtigt hat (siehe zepos-apps, SUPER+T) -
#     die Taste wurde repariert, die Leiste nicht, und niemand hat es
#     gemerkt, weil kein Test sie las. Ein Waechter, der die Haelfte der
#     Bedienelemente eines Systems nicht kennt, meldet Ruhe.

_BAR_CLICK = re.compile(
    r'on(?:Click|ClickRight|ClickMiddle|ScrollUp|ScrollDown)\s*:\s*"([^"]+)"')

# Was ein Klick ausserhalb der Leiste startet: die Kontrollzentrale ruft
# fremde Programme ueber GLib. Sie steht hier mit drin, weil ihr
# Druckerknopf bis zum 12.08.2026 `system-config-printer` rief - einen
# Namen, den packaging/zepos-apps/PKGBUILD ausdruecklich in der Liste
# des ABGEWAEHLTEN fuehrt.
_SPAWN = re.compile(r'spawn_command_line_async\(\s*"([^"$]+)"\s*\)')

# UND DERSELBE START UEBER Astals execAsync, seit dem 17.08.2026.
#
#     Das Bluetooth-Fenster startet blueman-manager damit, und zwar aus
#     demselben Grund, aus dem der Rest der Datei execAsync benutzt: es
#     ist der Weg, auf dem diese Oberflaeche fremde Programme ruft.
#     Ohne diese Zeile war blueman-manager nach dem Umzug der
#     Bluetooth-Zeile aus dem Kontrollzentrum fuer den Waechter
#     verschwunden - und sein Eintrag in PROVIDED_BY damit angeblich
#     unbenutzt, obwohl ein Knopf ihn ruft.
#
#     NUR die Form mit EINER schlichten Zeichenkette. Ein Feld
#     (`["bash", "-c", ...]`) ist kein Befehl, sondern eine Zerlegung,
#     und ein Template-Literal traegt eine Variable, die dieser Leser
#     nicht aufloesen kann.
_EXEC_ASYNC = re.compile(r'execAsync\(\s*"([^"$`]+)"\s*\)')


def _bar_clicks(tree: GeneratedTree) -> list[tuple[str, str]]:
    """(Datei, Shell-Zeile) fuer jeden Klick der erzeugten Oberflaechen."""
    widgets = tree.config / "ags" / "widget"
    found: list[tuple[str, str]] = []
    for source in sorted(widgets.glob("*.tsx")):
        body = "\n".join(line for line in source.read_text().splitlines()
                         if not line.lstrip().startswith("//"))
        for pattern in (_BAR_CLICK, _SPAWN, _EXEC_ASYNC):
            for command in pattern.findall(body):
                found.append((source.name, command))
    assert found, (
        "der erzeugte Baum enthaelt keinen einzigen Klickbefehl - "
        f"unter {widgets} liegt nichts, oder das Muster trifft nicht mehr")
    return found


def test_every_click_on_the_bar_names_a_program_zepos_ships(tree):
    """Dieselbe Frage wie bei den Tasten, an der anderen Oberflaeche.

    Zerlegt wird mit demselben Leser - doctor.command_words -, damit
    `kitty -e btop` als zwei Programme gezaehlt wird und nicht als
    eines. Genau diese Verkuerzung hat btop hier ueberleben lassen.
    """
    shipped = shipped_packages()
    unreachable = []
    for source, command in _bar_clicks(tree):
        for word in doctor.command_words(command):
            if word.startswith(("~", "./", "../", "/")) or "$" in word:
                # Ein Pfad im Heimatverzeichnis ist eine Datei, die
                # dieser Lauf erzeugt haben muss - die Zusicherung
                # darunter.
                continue
            package = PROVIDED_BY.get(word, word)
            if package in shipped or word in BASE_SYSTEM:
                continue
            unreachable.append(f"{source}: `{command}` ruft {word}")

    assert unreachable == [], (
        "Klicks auf Bedienelemente, hinter denen kein ausgeliefertes "
        "Paket steht: " + "; ".join(unreachable))


def test_every_generated_path_a_click_calls_was_really_generated(tree):
    """Die andere Haelfte: die Klicks auf eigene Skripte.

    Das Modul der schwebenden Fenster ruft drei davon, das Netzmodul
    eines und der Druckerknopf der Kontrollzentrale seit dem 12.08.2026
    ebenfalls. Ein Skript ohne Route im Generator landet nicht im Baum,
    und der Klick ist genauso stumm wie einer auf ein fehlendes Paket.
    """
    missing = []
    for source, command in _bar_clicks(tree):
        for word in doctor.command_words(command):
            if not (word.startswith(("~", "./", "../")) or "$" in word):
                continue
            target = Path(tree.expand(word))
            if not target.is_file():
                missing.append(f"{source}: `{command}` ruft {word}")

    assert missing == [], (
        "Klicks auf Skripte, die der Lauf nicht erzeugt hat: "
        + "; ".join(missing))


def test_the_click_check_would_catch_the_three_that_shipped():
    """Die Selbstpruefung, und sie legt dem Waechter einen Fund HIN.

    Ein sauberer Baum gibt nichts zu finden, also beweist ein gruener
    Lauf der beiden Zusicherungen darueber nichts ueber sie. Hier stehen
    die Zeilen, die am 12.08.2026 wirklich ausgeliefert waren, und der
    Waechter muss aus jeder von ihnen den Namen ziehen, der fehlte.
    """
    shipped = shipped_packages()

    # Genau die Form, in der die Zeilen in ags-bar.template standen.
    body = (
        '      case "custom/hypr-shortcuts": return scriptModule({\n'
        '        onClickRight: "sub ~/.config/hypr/hyprland.conf",\n'
        '      case "custom/hardware": return scriptModule({\n'
        '        onClick: "kitty -e btop",\n'
        '        onClickRight: "kitty -e watch -n 1 sensors",\n'
        '      // onClick: "nur ein Kommentar und kein Befehl",\n')
    lines = "\n".join(line for line in body.splitlines()
                      if not line.lstrip().startswith("//"))

    named = []
    for command in _BAR_CLICK.findall(lines):
        named.extend(doctor.command_words(command))

    assert "sub" in named, (
        "der Waechter zieht den Namen hinter einem rechten Klick nicht "
        f"heraus: {named}")
    assert "btop" in named, (
        "der Waechter sieht das Programm hinter `kitty -e` nicht - genau "
        f"die Verkuerzung, die btop hat ueberleben lassen: {named}")
    # Bei der dritten Zeile ist es `watch` und nicht `sensors`, und das
    # ist die ehrliche Antwort: die Zerlegung sieht ein Programm hinter
    # `-e` und keines hinter dem, was DIESES Programm wiederum startet.
    # Sie faengt die Zeile trotzdem - watch liefert ebenfalls kein
    # Rezept aus -, aber sie faengt sie ueber den falschen Namen, und das
    # steht hier, damit niemand mehr davon erwartet.
    assert "watch" in named, named
    assert "nur" not in named, (
        "der Waechter liest auskommentierte Zeilen mit: " + repr(named))

    # Und keiner der drei wird ausgeliefert - sonst pruefte der Fund
    # nichts.
    for dead in ("sub", "watch", "sensors"):
        assert dead not in shipped, (
            f"{dead} wird inzwischen ausgeliefert; dann ist diese "
            "Selbstpruefung ueber das Falsche")
    assert "btop" in shipped, (
        "btop wurde am 12.08.2026 in packaging/zepos-apps aufgenommen, "
        "weil ags-bar.template ihn oeffnet - er fehlt wieder")


# --------------------------------------------------------------------
# 6. das Dock
# --------------------------------------------------------------------

def test_the_dock_is_pinned_from_the_shipped_selection_and_from_nowhere_else(tree):
    """Die angeheftete Liste IST die Auswahl, nicht eine Kopie davon.

    Eine zweite Liste waere genau der Fehler, aus dem heraus die vier
    toten Tasten entstanden sind: jemand aendert die Auswahl an einer
    Stelle, und die andere zeigt weiter auf das, was es einmal gab.
    """
    dock = (tree.config / "ags" / "widget" / "Dock.tsx").read_text()
    pinned = re.search(r"^const PINNED: string\[\] = \[(.*?)\]", dock, re.M)
    assert pinned, "das erzeugte Dock traegt keine Liste angehefteter Anwendungen"
    listed = re.findall(r'"([^"]+)"', pinned.group(1))

    # HIER STAND `_depends("zepos-apps") + apps.own(SRC)` - die
    # Zusammensetzung ein zweites Mal nachgerechnet. Bis zum 17.08.2026
    # war das dieselbe Rechnung wie in apps.shipped(); seither ist es
    # das nicht mehr. shipped() wirft Doppelte weg, weil damals
    # zepos-claude-code in BEIDEN Haelften stand - und ein zweiter
    # Knopf mit demselben Programmnamen kostet weit mehr als ein
    # Zeichen zu viel (die Messung steht in
    # tests/src/test_apps_pinned_call.py). Der Filter blieb, auch
    # nachdem der Name am 01.09.2026 in die eigene Haelfte gewandert
    # ist; die Nachrechnung hier bleibt aus demselben Grund weg.
    #
    # Die Nachrechnung hat diesen Fehler also mitgespiegelt, statt ihn
    # zu fangen. Geprueft wird jetzt die ABSICHT dieses Tests - "die
    # Liste IST die Auswahl und keine zweite" - in drei Aussagen, von
    # denen keine die Zusammensetzung nachbaut.
    halves = set(_depends("zepos-apps")) | set(apps.own(SRC))

    unbekannt = [name for name in listed if name not in halves]
    assert unbekannt == [], (
        f"das Dock heftet {unbekannt} an - das steht in keiner der beiden "
        "Haelften der Auswahl, kommt also aus einer zweiten Liste")

    fehlend = sorted(halves - set(listed))
    assert fehlend == [], (
        f"{fehlend} wird ausgeliefert, steht aber nicht im Dock")

    assert listed == apps.shipped(SRC), (
        "src/apps.py liest eine andere Liste als das erzeugte Dock traegt."
        f"\n  Dock:     {listed}\n  apps.py:  {apps.shipped(SRC)}")


def test_every_pinned_entry_starts_a_program_that_exists():
    """Die Zusicherung, die den FEHLER faengt und nicht das Symptom.

    GEMELDET am 12.08.2026: "das einstellungs icon im footer laesst sich
    garnicht oeffnen es erscheint nie". Das Symptom war ein fehlendes
    Symbol; der Fehler war, dass das Dock nur EINE der beiden Haelften
    der Auswahl kannte.

    Gefragt wird deshalb nicht "steht die Einstellungsanwendung im
    Dock" - das waere wieder eine Liste, die jemand pflegt -, sondern
    fuer JEDEN angehefteten Namen: gibt es dahinter etwas, das startet?
    Zwei Wege fuehren zu einem Ja, und beide sind der Weg, den
    ags-dock.template zur Laufzeit geht:

      * ein Paket dieses Namens wird ausgeliefert. Dann liegt sein
        Anwendungseintrag auf der Maschine, oder das Programm hat keine
        Oberflaeche und faellt im Dock von selbst heraus (cups).
      * dieses Projekt liefert selbst einen Eintrag <name>.desktop aus.
        Dann muss die Exec-Zeile darin auf ein Programm zeigen, das
        ebenfalls hier gebaut wird.

    Ein Name, auf den keines von beidem zutrifft, ist ein Knopf, der
    nichts startet - beziehungsweise, wie am 12.08., ein Knopf, der gar
    nicht erst erscheint.
    """
    shipped = shipped_packages()
    entries = {path.stem: path
               for path in REPOSITORY.rglob("*.desktop")
               if ".git" not in path.parts}

    nowhere = []
    for name in apps.shipped(SRC):
        if name in shipped:
            continue
        entry = entries.get(name)
        if entry is None:
            nowhere.append(f"{name}: weder ein Paket noch ein Eintrag")
            continue
        execline = next(
            (line.split("=", 1)[1] for line in entry.read_text().splitlines()
             if line.startswith("Exec=")), "")
        program = Path(execline.split()[0]).name if execline.split() else ""
        if program not in shipped and f"{program}" not in {
                path.name for path in REPOSITORY.glob("*/bin/*")}:
            nowhere.append(f"{name}: Exec zeigt auf {program!r}")

    assert nowhere == [], (
        "angeheftete Eintraege, hinter denen nichts startet: "
        + "; ".join(nowhere))

    # Und die Gegenrichtung, in zwei Schritten. Ohne sie bestuende die
    # Zusicherung auch dann, wenn die eigene Haelfte gar nicht ankommt -
    # eine leere Menge erfuellt jede Allaussage. GEMESSEN am 12.08.2026:
    # eine Mutation, die `shipped()` wieder nur die fremden Anwendungen
    # zurueckgeben liess, kam ohne diese beiden Zeilen durch.
    listed = apps.own(SRC)
    assert listed, (
        "ZepOS heftet keine einzige eigene Anwendung an. Genau das war "
        "der Zustand am 12.08.2026, in dem das Einstellungssymbol nie "
        "erschienen ist.")
    assert "zepos-settings" in listed, listed

    pinned = apps.shipped(SRC)
    fehlend = [name for name in listed if name not in pinned]
    assert fehlend == [], (
        f"diese eigenen Anwendungen kommen im Dock nicht an: {fehlend}")


def test_the_recipe_reader_does_not_pin_what_a_comment_only_mentions():
    """Die Begruendungen des Rezepts nennen jedes ABGEWAEHLTE Programm.

    packaging/zepos-apps/PKGBUILD erklaert auf siebzig Kommentarzeilen,
    warum thunar, chromium, sublime-text-4 und ein Dutzend andere NICHT
    mitkommen. Ein Leser, der den Block als Text durchsucht, heftet
    danach genau die an - die schlechteste denkbare Umsetzung dieser
    Datei.

    Heute steht in keinem dieser Kommentare ein einfach angefuehrter
    Name, das Ueberspringen greift also gerade nicht. Das ist der Grund,
    warum es hier gemessen wird statt an der Wirklichkeit: eine
    Vorsichtsmassnahme, deren Bedingung heute nicht eintritt, ist morgen
    eine, die niemand mehr prueft.
    """
    recipe = (
        "depends=(\n"
        "    # thunar 4.20.9-1 haengt an GTK3 und kommt NICHT mit. Wer\n"
        "    # ihn will, nimmt 'thunar' von Hand.\n"
        "    'nautilus'\n"
        "    #'chromium'\n"
        "    'firefox'\n"
        ")\n")
    assert apps.from_recipe(recipe) == ["nautilus", "firefox"], (
        "der Leser nimmt Namen aus den Begruendungen mit: "
        + repr(apps.from_recipe(recipe)))


def test_the_dock_window_stands_on_the_screen_from_the_start(tree):
    """Die Layer-Shell-Flaeche selbst - und das ist die Zeile, die der
    Nutzer als "geht nicht mehr" gemeldet hat.

    WARUM DAS EINE TEXTPRUEFUNG IST UND KEINE MESSUNG, EHRLICH GESAGT
        Astal.Window ruft in ihrem Konstruktor gtk_layer_init_for_window
        auf, und das verlangt eine Wayland-Anzeige. Unter gtk4-broadwayd
        gibt es keine - deshalb baut der kopflose Lauf in
        test_bar_headless.py DockContent() und nicht Dock(), und deshalb
        kann er ueber `visible:` und `exclusivity:` nichts sagen.

        Zwei Zeilen bleiben damit ohne echte Messung uebrig, und beide
        entscheiden, ob ein Nutzer das Dock ueberhaupt zu Gesicht
        bekommt. Eine Textpruefung an der ERZEUGTEN Datei ist dafuer
        schwach - sie beweist nicht, dass Astal die Werte annimmt - und
        sie ist trotzdem stark genug fuer den Fall, um den es geht: dass
        jemand `visible: false` zurueckschreibt. Die eigentliche Antwort
        holt Bild 08 des QEMU-Laufs.
    """
    dock = (tree.config / "ags" / "widget" / "Dock.tsx").read_text()
    body = "\n".join(line for line in dock.splitlines()
                     if not line.lstrip().startswith("//"))

    # SEIT DEM 01.09.2026 STEHT DER ANFANGSSTAND EINE ZEILE HOEHER, und
    # diese Pruefung ist dadurch nicht schwaecher geworden.
    #
    #     Das Fenster entsteht seither mit `visible: sichtbar`, weil ein
    #     Schirm auch NACH dem Anmelden angesteckt werden kann (siehe
    #     jeSchirm() in src/templates/ags-kit.template): sein Dock muss
    #     so stehen wie die anderen, und "true" hiesse, dass bei jedem
    #     angesteckten Kabel ein Dock erschiene, obwohl der Nutzer es
    #     gerade mit SUPER+B weggeschickt hat.
    #
    #     Gefragt wird deshalb nach BEIDEN Haelften. Wer `let sichtbar =
    #     false` schreibt oder das Feld gegen einen anderen Wert
    #     tauscht, faellt hier genauso durch wie vorher, wer `visible:
    #     false` schrieb - und der Fall, den es gar nicht gab, ist jetzt
    #     mit abgedeckt: ein Fenster, das seinen Anfangsstand ueberhaupt
    #     nicht mehr liest.
    assert "visible: sichtbar," in body, (
        "das Dockfenster liest seinen Anfangsstand nicht mehr - dann "
        "haengt es davon ab, was in seiner Zeile zufaellig steht")
    assert "let sichtbar = true" in body, (
        "das Dockfenster startet unsichtbar - genau der Zustand, in dem "
        "es der Nutzer am 11.08.2026 nicht gefunden hat")
    assert "visible: false," not in body, body[-1200:]

    # Und der Streifen, den es sich nimmt. Ohne ihn liegt ein dauerhaft
    # sichtbares Dock ueber dem unteren Rand jedes Fensters.
    assert "Astal.Exclusivity.EXCLUSIVE" in body, (
        "das Dock reserviert seinen Platz nicht und deckt damit jedes "
        "Fenster darunter zu")


def test_no_window_in_the_dock_falls_back_to_the_settings_gear(tree):
    """"terminal icon auch bereitstellen aktuell kriegen die terminals
    das einstellung icon" - gemeldet am 13.08.2026.

    DREI MESSUNGEN, UND KEINE DAVON IST DIESE ZEILE
        Sie sind am selben Tag im verschachtelten Compositor gefahren
        worden, mit einem echten kitty, gestartet wie die Tastenbindung
        es tut (`kitty --directory ~ --class="floating-default"`, siehe
        hyprland-universal-config.template):

          * `hyprctl clients -j` meldet class="floating-default" - ein
            Name, der eine FENSTERREGEL ausloest und keine Anwendung
            benennt. Kein Symbolthema kennt ihn, also griff der
            Rueckfall.
          * `application-x-executable` zeigt in Papirus-Dark auf
            apps/application-default-icon.svg, und das ist ein ZAHNRAD.
            Nachgesehen, indem die Datei gezeichnet wurde.
          * /proc/<pid>/comm sagt "kitty", entryFor() findet
            /usr/share/applications/kitty.desktop, dessen Icon-Zeile
            "kitty" nennt, und hicolor fuehrt kitty.svg. Auf dem Bild
            des Fusses steht seither die Katze und kein Zahnrad.

    WAS HIER GEPRUEFT WIRD, UND WARUM ES EINE TEXTPRUEFUNG IST
        Das Bild braucht einen Compositor, ein Symbolthema und ein
        installiertes kitty; diese Zeile faellt auch ohne alles drei -
        naemlich in dem Moment, in dem jemand den Rueckfall wieder auf
        `application-x-executable` stellt. Sie prueft genau das und
        behauptet nichts darueber hinaus.
    """
    dock = (tree.config / "ags" / "widget" / "Dock.tsx").read_text()
    # BEIDE Kommentarformen weg, und nicht nur die Zeilenform: der Name,
    # um den es geht, steht in dieser Datei mehrfach in einem
    # /** ... */-Block - dort naemlich, wo begruendet ist, warum er kein
    # Rueckfall mehr ist. Ein Filter, der nur `//` kennt, faende ihn dort
    # und meldete die Begruendung als den Fehler, den sie beschreibt.
    body = re.sub(r"/\*.*?\*/", "", dock, flags=re.S)
    body = "\n".join(line for line in body.splitlines()
                     if not line.lstrip().startswith("//"))

    assert "application-x-executable" not in body, (
        "der Dock-Rueckfall ist wieder application-x-executable - in "
        "Papirus-Dark ein Zahnrad, also das Bild der Systemeinstellungen "
        "unter jedem Fenster, dessen Klasse das Thema nicht kennt")
    # Und der Weg, der das Terminal ueberhaupt erst findet: die Klasse
    # "floating-default" steht in keinem Symbolthema, das PROGRAMM
    # dahinter schon.
    assert "/proc/" in body and "comm" in body, (
        "das Dock fragt nicht mehr nach dem Programm hinter dem Fenster - "
        "dann bekommt jedes selbstgesetzte --class wieder das Ersatzbild")


def test_the_pinned_list_survives_the_generator_and_not_only_the_module(tree):
    """Die Marke im Dock ist gesetzt, nicht bloss vorhanden.

    Ohne den Nachlauf in generate_config.sh stuende dort weiterhin die
    leere Liste aus der Vorlage - eine Datei, die uebersetzt, laeuft und
    ein Dock ohne einen einzigen Knopf ergibt. Das ist der Zustand, den
    diese Aenderung behebt, und er saehe in jedem anderen Test genauso
    aus wie der behobene.
    """
    dock = (tree.config / "ags" / "widget" / "Dock.tsx").read_text()
    assert "const PINNED: string[] = []" not in dock, (
        "der Generator hat die angehefteten Anwendungen nicht eingesetzt")
    assert dock.count("// zepos-pinned") == 1, (
        "die Marke steht nicht genau einmal in der erzeugten Datei")


# --------------------------------------------------------------------
# was ohne Maschine nicht zu beantworten ist
# --------------------------------------------------------------------

def test_the_acceptance_that_still_needs_a_machine():
    """Was `iso/test-boot.py --scenario release-installed` messen MUSS.

    Alles oben ist eine Rechnung an einem erzeugten Baum. Sie kann
    sagen, dass SUPER+E nautilus ruft und dass nautilus ausgeliefert
    wird; sie kann nicht sagen, dass ein Fenster aufgeht. Genau dieser
    Unterschied ist der Grund, aus dem der Nutzer am 11.08.2026 Dinge
    gefunden hat, die gruen waren.

    Diese Zusicherung ist deshalb keine Absichtserklaerung, sondern eine
    Pruefung des SKRIPTS, das die Antwort holen wird: sie faellt, wenn
    jemand die Schritte wieder herausnimmt. Der Lauf selbst braucht
    QEMU, eine Stunde und ein gebautes Medium.
    """
    script = (REPOSITORY / "iso" / "test-boot.py").read_text()
    body = re.search(r"RELEASE_INSTALLED_SCRIPT: tuple\[str, \.\.\.\] = \((.*?)\n\)",
                     script, re.S)
    assert body, "iso/test-boot.py hat kein Skript fuer die Anmeldung"
    steps = body.group(1)

    # Die sechs Fragen, die nur eine laufende Sitzung beantwortet, jede
    # mit dem Bild, auf dem die Antwort steht. Auf die BILDNAMEN
    # gepruefft und nicht auf die Tastendruecke: ein `key:meta_l-e` ohne
    # `shot:` danach ist ein Tastendruck, dessen Ergebnis niemand sieht,
    # und genau das waere die Art Abnahme, aus der diese Datei entstanden
    # ist.
    #
    # OHNE DIE LAUFENDE NUMMER, und das ist eine Korrektur vom
    # 12.08.2026. Hier stand "shot:08-dock-ohne-fenster"; dann bekam der
    # Lauf zwei Bilder vorangestellt (die Passphrasenabfrage der
    # Initramfs und der Schirm danach), alles dahinter rueckte um zwei
    # weiter, und diese Zusicherung fiel - obwohl kein einziger Schritt
    # verschwunden war.
    #
    # Die Nummer ist Buchfuehrung und nicht die Behauptung. Behauptet
    # wird: es gibt ein Bild, das das Dock ohne offenes Fenster zeigt.
    # Wie es durchnummeriert ist, geht diese Datei nichts an.
    for what, label in (
            ("das Dock ohne offenes Fenster", "-dock-ohne-fenster"),
            ("der Dateimanager", "-super-e-dateimanager"),
            ("der Anwendungsstarter", "-super-spc-anwendungsstarter"),
            ("das Bildschirmfoto", "-super-s-bildschirmfoto"),
            ("die Selbstauskunft", "-abnahme-zepos-doctor"),
            ("die Sicherungskopien", "-abnahme-widget-verzeichnis")):
        assert re.search(rf'"shot:\d+{re.escape(label)}"', steps), (
            f"{what} wird beim naechsten Lauf nicht geprueft: ein Bild "
            f"`shot:<nr>{label}` fehlt in RELEASE_INSTALLED_SCRIPT")

    # UND DIE PASSPHRASE. Seit dem 12.08.2026 installiert der Lauf davor
    # eine verschluesselte Platte, also bootet diese Maschine nicht mehr
    # durch: ohne diesen Schritt kaeme das Skript nie bis zur
    # Anmeldemaske, und jede Zusicherung darueber waere eine Aussage
    # ueber einen Lauf, der vor der ersten Textzeile stehengeblieben ist.
    assert re.search(r'"shot:\d+-passphrase-gefragt"', steps), (
        "der Lauf fotografiert die Passphrasenabfrage der Initramfs "
        "nicht - sie ist die erste Oberflaeche nach dem Startmenue und "
        "der einzige Beleg dafuer, dass die Platte verschluesselt ist")
    assert "RELEASE_DISK_PASSPHRASE" in script, (
        "der Lauf tippt keine Plattenpassphrase - er kaeme nicht bis zur "
        "Anmeldung")

    # Und die Tasten, die die Bilder ueberhaupt erst etwas zeigen lassen.
    # meta_l ist die Position, die Hyprland $mainMod nennt - "super" ist
    # kein QEMU-qcode und waere ein Schritt, der beim Lauf abbricht.
    for chord in ("key:meta_l-e", "key:meta_l-spc", "key:meta_l-s",
                  "key:meta_l-q"):
        assert chord in steps, f"{chord} fehlt in RELEASE_INSTALLED_SCRIPT"

    assert steps.count("shot:") >= 12, (
        "die Anmeldung wird zu selten fotografiert, um etwas zu zeigen")
