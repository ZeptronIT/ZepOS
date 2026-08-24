# SPDX-License-Identifier: GPL-3.0-or-later
"""The inventory is a contract: later tasks assume exactly this set.

The content guards in the second half of this file used to be scoped to
`src/` and to hold the strings they forbid in their own source. Both
halves of that are now gone: the literals live as digests in
tests/origin_data.py, and the guard that used them reads every file in
the repository rather than only the ones that ship. See that module for
why, and for what a reader of the published repository can still learn.
"""
import re
from pathlib import Path

from tests.origin_data import (ORIGIN, REPOSITORY, repository_directories,
                               repository_files, what_kind)

# Anchored on this file, not on the working directory. As a relative path
# this resolved against wherever pytest happened to be started, and
# `Path("src").rglob("*")` over a directory that is not there yields
# nothing at all - so every content search below reported "clean" without
# having read a single file. A guard that scanned nothing must not be
# able to pass, which is what SCANNED_SUFFIXES and the emptiness
# assertions in the two content tests are for.
SRC = Path(__file__).resolve().parents[2] / "src"

# What ships and can therefore carry a name to a user's machine.
SCANNED_SUFFIXES = {".py", ".sh", ".template", ".conf", ".json", ".md"}


def _has_shebang(path: Path) -> bool:
    """Whether a file without a suffix is a script.

    src/bin/zepos-generate, -settings and -doctor are the commands that
    get installed into /usr/bin. They carry no extension - a command
    called "zepos-doctor.py" is not what anyone types - so a scan
    selecting on suffix alone walked past every one of them. The three
    files that end up furthest from this repository, on other people's
    machines, were the three no content guard here had ever read.
    """
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def _is_scanned(path: Path) -> bool:
    if path.suffix in SCANNED_SUFFIXES:
        return True
    return not path.suffix and _has_shebang(path)


def _shipped_files() -> list[Path]:
    """Every file under src/ a content guard has to read.

    Asserts it found some: an empty list is the failure mode that made
    the pattern-based guards below meaningless for as long as SRC was
    relative.
    """
    files = [path for path in sorted(SRC.rglob("*"))
             if path.is_file() and _is_scanned(path)]
    assert len(files) > 50, (
        f"only {len(files)} files found under {SRC} - the scan is not "
        "reading the source tree, so its result means nothing")
    # The suffix rule used to exclude exactly the files that get
    # installed into /usr/bin, because a command is not called
    # "zepos-doctor.py". Checked here rather than trusted: a selector
    # that quietly drops a file produces the same "clean" as one that
    # read it and found nothing.
    names = {path.relative_to(SRC).as_posix() for path in files}
    for command in ("bin/zepos-generate", "bin/zepos-settings",
                    "bin/zepos-doctor"):
        assert command in names, f"{command} is not read by these guards"
    return files

# Fifteen of the twenty-one templates Task 1 deleted. The other six are
# deliberately NOT named here: two carried an internal host, two a
# notebook model that doubles as a machine name, and two the cities the
# author's own weather modules pointed at. Writing them down would put
# back exactly what this file exists to take out - a deletion list is
# still a list of the things that were there.
#
# They are covered twice over instead, and more tightly than by
# membership in this list. test_no_device_or_employer_names_remain hashes
# every file's NAME as well as its contents, over the whole repository:
# any of the six coming back as a file fails on its name, and any
# reference to one from inside another file fails on that file's
# contents. The four here whose names contain a printer or notebook
# VENDOR stay in plaintext - a manufacturer says nothing about who wrote
# this - and are additionally covered by DISPLAY_VENDORS below.
# The four that carried the employer's build tool in their NAME are not
# listed: the history rewrite replaced that name with "zepos", and
# "zepos-terminals-config" is a template this project actually ships - so
# the list would have asserted that a live file must not exist. They are
# covered the same way the six below are, by the hashed name check in
# test_no_device_or_employer_names_remain, which reads every file name in
# the repository.
#
# THE FOURTH JOINED THEM ON 17.08.2026, before the history was dropped
# and the tree made public. It was still spelled out here, and this
# file's own opening argument applies to it as much as to the others: a
# deletion list is still a list of the things that were there. The name
# said which build host somebody worked on. REMOVED_ELSEWHERE carries it
# now, so the total below is unchanged - the entry moved from plaintext
# to the hashed check, which the paragraph above calls the tighter of
# the two.
REMOVED_TEMPLATES = [
    "onedrive-control-config", "onedrive-status-config", "onedrive-debug-config",
    "printer-install-dell", "printer-status",
    "kvm-switch-config", "kvm-profile-config",
    "wlogout-dell-config",
    "grid-wallpaper-toggle-dell-config", "hardware-monitor-dell-config",
    "network-repair-config",
]
REMOVED_ELSEWHERE = 10

# Vorlagen, die nach Aufgabe 1 gegangen sind. Eine eigene Liste, weil die
# obige eine Zahl traegt: sie ist auf 21 festgenagelt, damit niemand sie
# kuerzt, und ein neuer Eintrag darin waere kein Fund, sondern eine
# kaputte Rechnung.
#
# Am 11.08.2026 mit den beiden Leistenmodulen, die der Nutzer nicht mehr
# wollte ("herz und schild in der waybar oben kommen weg"):
# network-watchdog-bar-config schrieb das Herz, vpn-status-config das
# Schild, und beide hatten keinen zweiten Leser.
REMOVED_LATER = [
    "network-watchdog-bar-config",
    "vpn-status-config",
]

KEPT_TEMPLATES = [
    "ags-bar", "ags-config", "kitty-config", "zshrc-config",
    "hyprland-universal-config", "hyprland-failsafe-config",
    "vpn-connect-script", "network-watchdog-config",
]


def test_source_tree_exists():
    assert (SRC / "templates").is_dir()
    assert (SRC / "generate_config.sh").is_file()


def test_removed_templates_are_gone():
    present = [n for n in REMOVED_TEMPLATES
               if (SRC / "templates" / f"{n}.template").exists()]
    assert present == [], f"should have been deleted: {present}"
    # The list is short by six on purpose, not by accident. Without this
    # somebody trimming it further looks the same as the split above.
    assert len(REMOVED_TEMPLATES) + REMOVED_ELSEWHERE == 21, (
        "Task 1 deleted 21 templates; this list plus the ones covered by "
        "name in test_no_device_or_employer_names_remain must add up")


def test_kept_templates_are_present():
    missing = [n for n in KEPT_TEMPLATES
               if not (SRC / "templates" / f"{n}.template").exists()]
    assert missing == [], f"missing: {missing}"


def test_dead_template_directory_is_gone():
    """templates/deprecated/ held six files superseded long ago. Carrying
    dead code into a new project is how it becomes permanent."""
    assert not (SRC / "templates" / "deprecated").exists()


def test_no_backup_files_were_carried_over():
    """Regression guard, not coverage.

    The origin holds 698 untracked .backup.* files. Copying the tracked
    file list cannot bring them, so this cannot fail against the current
    mechanism - it exists to go red if someone later swaps that for a
    directory copy, which would bring all of them."""
    strays = list(SRC.rglob("*.backup.*"))
    assert strays == [], f"{len(strays)} backup files came along"


def test_generic_profiles_exist():
    """The origin's profiles were named after the employer's machines,
    with monitor serial numbers written into them. They are gitignored
    there, so they were never copied - which means nothing here would
    have noticed that the generic replacements are missing."""
    profiles = SRC / "profiles"
    assert profiles.is_dir(), "src/profiles/ is a required deliverable"
    names = sorted(p.name for p in profiles.iterdir() if p.is_dir())
    assert names, "no example profile present"
    for name in names:
        # Two rules, because neither covers the other. The prefix check
        # catches a name that merely starts the way the origin's did -
        # two letters identify nobody, so it stays in plaintext. The
        # denylist catches the two full scheme names, which do.
        assert not name.startswith(("AX", "ax")), (
            f"{name} carries the origin's host-name prefix")
        assert not ORIGIN.hits(name), (
            f"{name} is one of the origin's machine names")


def test_hypervisor_scripts_are_gone():
    """The origin kept a directory of scripts that ssh'd into the
    machine's hypervisor. The directory was named after that host, so it
    cannot be named here - the check is that NO directory under src/
    carries a forbidden name, which is the same assertion without the
    leak and additionally catches a second one nobody has created yet."""
    offenders = [path.relative_to(SRC).as_posix()
                 for path in sorted(SRC.rglob("*"))
                 if path.is_dir() and ORIGIN.hits(path.name)]
    assert offenders == [], f"directories named after the origin: {offenders}"


def test_template_count_is_seventy_seven():
    """96 in the origin, 21 removed, 2 generic ones added, 2 orphans cut,
    2 place-bound clocks replaced by 1 generic one, 1 plugin include
    added, und am 11.08.2026 vier fuer waybar und nwg-dock gestrichen
    gegen fuenf fuer die AGS-Leiste (75 - 4 + 5 = 76).

    The original deletion list named 16 and was drawn from template NAMES
    alone. It missed five more that carry a device or a host in their
    content: two wlogout variants for specific notebooks, a wallpaper
    toggle and a hardware monitor for one screen, and a wrapper that
    ssh's into the machine's hypervisor to run a script this project
    deleted. Searching names instead of contents is what let them
    through.

    Task 7 added printer-manager-config and bar-weather-config, which
    between them replace five of the deleted ones: two printer installers
    bound to one device each, a printer status script, and two weather
    scripts bound to one city each. What they do rather than what they
    contain is covered by tests/src/test_new_templates.py.

    77 to 75, deliberately. clock-config and time-config generated
    ~/.config/ags/scripts/clock.sh and time.sh, one `date` call each,
    and no bar module, script, keybind or document named either: they are
    what date-config and the two second clocks were split out of, left
    behind when the split happened. This assertion exists to catch an
    UNINTENDED change to the set, so an intended one moves the number and
    says why - it is not a floor under templates nothing reaches. The
    same count is asserted a second time in
    tests/src/test_new_templates.py and both have to move together.

    75 to 74. The two remaining second clocks were one line each, with a
    timezone, a flag emoji and a locale of one country written into them,
    and both were placed on every bar unconditionally. waybar-clocks-
    config.template replaces both: any number of zones from
    `clocks.zones` in the user settings, and nothing rendered at all when
    none are set. Two out, one in - see tests/src/test_clocks.py, which
    generates it and runs it.

    74 to 75. hyprland-plugins-config.template is the one file in which a
    plugin may be depended on: the plugin= line, the plugin{} settings
    block, and every bind whose dispatcher comes from a plugin. All three
    used to live in hyprland-universal-config.template, where a missing
    object turns them into config errors in the file that starts the
    desktop. src/plugins.py writes a block into the generated
    ~/.config/hypr/plugins.conf only when the object it depends on is on
    the machine, so a machine with no plugins at all gets a file of
    comments - a valid Hyprland configuration - rather than a session
    that does not start. See tests/src/test_plugins.py, which generates
    it both ways and runs the generator over both.

    76 + 1 - 2 = 75, und beide Rechnungen sind vom 11.08.2026.

    PLUS EINS  gtk4-colors-config.template schreibt libadwaitas benannte
    Farben aus src/brand.py nach ~/.config/gtk-4.0/gtk.css. Es ist die
    einzige Stelle, an der eine Anwendung, die dieses Projekt nicht
    geschrieben hat, die Marke erfaehrt - ohne sie waeren die
    Anwendungen aus packaging/zepos-apps dunkelgraue Adwaita-Fenster vor
    einem petrolfarbenen Schreibtisch.

    MINUS ZWEI  Das Herz und das Schild sind von der Leiste verschwunden
    ("herz und schild in der waybar oben kommen weg"), und mit ihnen
    network-watchdog-bar-config und vpn-status-config. Beide hatten
    genau einen Leser, und der war der geloeschte case-Zweig in
    ags-bar.template. Der Wachhund selbst und der VPN-Verwalter bleiben:
    sie werden vom Kontrollzentrum aus erreicht.

    PLUS ZWEI  hyprlaunch-config und hyprclipx-config, als die beiden
    Plugins am 11.08.2026 in den Baum geholt wurden: ihre Fenstermasse
    standen vorher als `static constexpr` im C++ und liessen sich weder
    faerben noch skalieren. Ihre Stylesheets liegen unter src/styles/
    und zaehlen hier nicht mit - der Plugin-Zweig hatte mit 79
    gerechnet, weil er alle vier zaehlte.

    77 - 1 + 1 = 77, nachgezaehlt am 12.08.2026. Zwei Zweige desselben
    Tages, jeder mit einer Haelfte.

    MINUS EINS  hyprlock-config, weil hyprlock durch lock/zepos-lock.c
    ersetzt ist. Es war die einzige erzeugte Datei, deren Farben nicht
    aus brand.py kamen und auch nicht kommen KONNTEN: hyprlock ist kein
    GTK-Programm und nimmt kein Stylesheet, sondern eine eigene
    Konfigurationssprache - sie trug zwoelf rgb()-Literale in
    Terminalgruen. Der Ersatz ist GTK4 und liest
    src/styles/lock-style.template, das unter src/styles/ liegt und hier
    deshalb nicht mitzaehlt.

    PLUS EINS  gtk4-settings-config.template. Neben den FARBEN von
    gtk4-colors-config schreibt es die GROESSE nach
    ~/.config/gtk-4.0/settings.ini - bis dahin wuchsen beim Drehen des
    Reglers alle eigenen Oberflaechen mit und die fremden GTK4-Fenster
    nicht.

    77 - 1 + 1 = 77, nachgezaehlt am 12.08.2026 - dieselbe Rechnung ein
    drittes Mal an demselben Tag, und diesmal mit den zwei Haelften einer
    Eingabezeile.

    MINUS EINS  starship-config, und es ist der reinste Fall von
    "erzeugt und nirgends gelesen", den dieser Baum bisher hatte. Es
    schrieb ~/.config/starship.toml, eine vollstaendige
    Prompt-Konfiguration mit vier eigenen Farbliteralen (#00cc00,
    #00ff00, #1a1a1a, #0c0c0c) - waehrend starship in keiner Paketliste
    dieses Projekts steht und kein `starship init zsh` in
    zshrc-config.template. Der Rueckwaertslauf in
    tests/src/test_reference_resolution.py hat es durchgelassen, weil ein
    Eintrag unter READ_BY_CONVENTION einen Leser BEHAUPTETE.

    PLUS EINS  p10k-config, das ~/.p10k.zsh schreibt. Der Nutzer hat am
    12.08.2026 powerlevel10k verlangt; zshrc-config.template
    konfigurierte es seit jeher und sourcte eine ~/.p10k.zsh, die
    niemand erzeugte. Jetzt gibt es sie, mit den Farben des aktiven
    Themas und den Symbolen aus src/icon_definition.py.

    80 statt 77, am 12.08.2026: die drei Skripte der bedingten
    Leistenmodule (Aufgabe #94) - ags-privacy-scripts,
    ags-media-scripts, ags-updates-scripts. Die ganze Rechnung mit
    ihren Begruendungen fuehrt die Zwillingszusicherung in
    tests/src/test_new_templates.py.

    81 STATT 80, am 17.08.2026: ags-bluetooth. Der Klick auf das
    Bluetooth-Modul der Leiste startete bis dahin `blueman-manager` -
    einen GTK3-Prozess neben der Sitzung -, und der Nutzer hat verlangt,
    dass die Hauptfunktionen oben BEDIENBAR sind ("wlan soll direkt
    dahin ... bluetooth soll funktionieren"). Die Vorlage baut das
    Fenster dafuer, aus derselben Fabrik wie die anderen zehn.

    82 STATT 81, am 17.08.2026: ags-i18n. Der Nutzer hat gemeldet, "i18n
    wurde nicht Ordnungsgemaess gepflegt und meinche UI Elemente sind
    noch Deutsch und nicht variabel", und das war zu messen: in den
    AGS-Vorlagen standen 297 sichtbare Zeichenketten, davon 297 fest
    verdrahtet und keine einzige durch einen Katalog. Die neue Vorlage
    erzeugt ags/utils/i18n.ts - dasselbe gettext, das der Installer
    schon benutzt, nur unter der Domaene zepos-desktop. Nachgezaehlt
    wird seither bei jedem Lauf in tests/src/test_ags_i18n.py.

    83 STATT 82, am 18.08.2026: ags-kit. Der Nutzer hat gemeldet, die
    Fenster wirkten "zusammengebastelt" und die Knoepfe "billig", und
    das war zu messen: 45 Knopfregeln in 41 Klassen, keine gemeinsame.
    Die neue Vorlage erzeugt ags/utils/kit.ts - Funktionen, die fertige
    Widgets zurueckgeben, damit ein Fenster gar nicht erst in die Lage
    kommt, sich einen eigenen Knopf zu bauen.

    84 STATT 83, am 19.08.2026 (Aufgabe 26): netto plus eins. Der Nutzer
    wollte einen Knopf unten links am Dock, der ein AGS-Fenster mit
    Herunterfahren/Abmelden/... oeffnet - und zepos-logout, das C-Programm,
    das SUPER+M bis dahin dafuer startete, ist mit ihm gefallen (Regel
    14, "erscheint immer wieder wenn ich super m mache" war ein
    Prozessstart-Fehler, kein AGS-Fehler). logout-config.template faellt
    (-1, die erzeugte layout.json gibt es nicht mehr). ags-logout.
    template kommt dazu (+1, dieselben sechs Aktionen als TypeScript-
    Literal). ags-power-button.template kommt dazu (+1, der Dock-Knopf
    selbst, eine eigene kleine Layer-Shell-Flaeche). Die Zwillingszusicherung
    in tests/src/test_new_templates.py haelt dieselbe Rechnung.

    85 STATT 84, am 19.08.2026 (Aufgabe 32): ags-settings. Der Nutzer
    hatte am 18.08.2026 "ein komplett eigenes ags fenster" fuer die
    Einstellungen bestellt und am 19.08.2026 festgestellt, dass er
    stattdessen eine Umfaerbung der GTK4-Anwendung bekommen hatte
    ("uebrigens hast du die settings die du selber gebaut hast immernoch
    nicht in einem ags fenster umgesetzt was ich eigentlich wollte").
    Die neue Vorlage erzeugt ags/widget/Settings.tsx - die zweite Schale
    dieses Baums (createShellWindow) neben dem Kontrollzentrum. Sie
    traegt KEINE Einstellung selbst: sie zeichnet, was
    `zepos-settings-gui --json get` ausgibt.

    86 STATT 85, am 20.08.2026 (Aufgabe 44): ags-starter-button. Der
    Nutzer wollte zum Abschaltknopf unten links ein Gegenstueck unten
    rechts ("ich will wie shutdown icon unten links, will ich ein icon
    ganz unten rechts genauso, nur mit 6 punkten, was im Prinzip wie
    SUPER+SPACE macht"). Die neue Vorlage erzeugt
    ags/widget/StarterButton.tsx - dieselbe Bauart wie
    ags-power-button.template, in der anderen unteren Ecke, mit dem
    Rastersymbol aus sechs Punkten und mit dem Anwendungsstarter statt
    der Sitzungsmaske dahinter. Kein Teil von ags-dock.template, aus
    demselben Grund wie der Abschaltknopf: das Dock ist inhaltsbemessen
    und zentriert, ein angehaengter Knopf wanderte mit seinem Inhalt.
    Die Zwillingszusicherung in tests/src/test_new_templates.py haelt
    dieselbe Rechnung.

    87 STATT 86, am 20.08.2026 (Aufgabe 52): ags-home. Der Nutzer wollte
    einen Schreibtisch mit Programmsymbolen ("ich kann auch nicht auf dem
    hintergrund sozusagen wo die apps mit den logos sein sollen wie
    windows rechtsklick drücken und eine app spawnen"). Die neue Vorlage
    erzeugt ags/widget/Home.tsx - eine Layer-Shell-Flaeche je Schirm auf
    `bottom`, also ueber der Tapete und unter jedem Fenster. Ihr
    Stylesheet liegt unter src/styles/home-style.template und zaehlt hier
    NICHT mit, aus demselben Grund, aus dem lock-style.template dort
    nicht mitzaehlt (siehe die Rechnung weiter oben).

    88 STATT 87, am 21.08.2026 (Aufgabe 53): ags-user-settings. Der
    Nutzer wollte die Gegenrichtung in allen drei Rechtsklick-Menues
    ("das gleiche muss bei der dock auch funktionieren, weil ich nicht
    jedes icon auf der dock oder auf dem home haben will") und meldete
    dazu aus 0.1.7: "wenn ich es dort mit der dock versuche dann
    passiert nichts". Die neue Vorlage erzeugt
    ags/utils/user-settings.ts - der eine Weg, auf dem das Dock UND das
    Home die Einstellungsdatei lesen, ueber `settings.py dock|home
    add|remove` aendern und ueber einen Gio.FileMonitor voneinander
    erfahren. Sie ist ein Baustein wie kit.ts und i18n.ts und kein
    Fenster; die zwei Fenster verlieren dabei ihre eigenen Fassungen
    (bruecke()/gepflegtePins()/schreibePins() im Dock, frage()/lies()/
    schreibe() im Home), es ist also netto plus eine Datei und minus
    sechs Funktionen.

    89 STATT 88, am 21.08.2026 (Aufgabe 54, Stufe 2):
    ags-bluetooth-agent. Der Nutzer meldete, die Kopplung gelinge ohne
    Rueckfrage ("es fehlt die kopplungsanfrage, die man mit ja oder nein
    bestaetigen muss"). Gemessen war es keine fehlende Meldung, sondern
    eine Sicherheitsluecke: ohne angemeldeten BlueZ-Agenten setzt
    bluetoothd NoInputNoOutput, und der KERN bestaetigt die Kopplung
    dann selbst (Linux v7.1 net/bluetooth/hci_event.c:5397,
    HCI_OP_USER_CONFIRM_REPLY) - Just Works, ohne MITM-Schutz. Die neue
    Vorlage erzeugt ags/widget/BluetoothAgent.tsx: ein org.bluez.Agent1
    auf dem Systembus mit allen sieben Rueckfragen, dessen Fenster aus
    derselben createOverlayWindow()-Fabrik kommt wie die uebrigen zwoelf.

    Sie ist netto plus eine Datei und MINUS ein fremdes Programm in der
    Sitzung: die Zwischenloesung (`exec-once` auf blueman-applet samt
    drei Fensterregeln in hyprland-universal-config.template) faellt mit
    ihr, nach Regel 14. Das PAKET blueman bleibt - es ist der einzige
    Weg zur Bluetooth-Dateiuebertragung in diesem Baum.
    """
    assert len(list((SRC / "templates").glob("*.template"))) == 89


def test_nothing_refers_to_a_deleted_template():
    """A generator entry or module pointing at a template that no longer
    exists fails at run time, on a user's machine, with a message they
    cannot act on."""
    offenders = []
    for path in _shipped_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for name in REMOVED_TEMPLATES + REMOVED_LATER:
            if name in text:
                offenders.append(f"{path.relative_to(SRC)}: {name}")
    assert offenders == [], "references to deleted templates: " + "; ".join(offenders[:12])


# --------------------------------------------------------------------
# hardcoded monitor identities
# --------------------------------------------------------------------
#
# Three rules, because one pattern cannot be both precise and general
# here. Each is written to fire on a SHAPE or on a fact about displays,
# never on a list of the strings that happen to be in the tree today: a
# pattern naming the three serials Task 6 left behind would have caught
# nothing before they were written and nothing after they were removed.

# An EDID serial as it appears in `hyprctl monitors -j`: one run of
# capitals and digits, no separators. The thresholds are measured against
# this tree rather than guessed - at eight characters with at least three
# digits and two letters, the only tokens in src/ that match are monitor
# serials. Loosening either threshold by one starts matching legitimate
# content: seven characters admits RFC1918 and the model name of a pair
# of headphones, and two digits admits the same.
SERIAL_TOKEN = re.compile(r"\b[A-Z0-9]{8,}\b")
SERIAL_MIN_DIGITS = 3
SERIAL_MIN_LETTERS = 2

# EDID manufacturer names. A configuration that is meant to work on any
# desk has no reason to name a display manufacturer at all - not in code,
# and not in a comment describing which screen stands where, which is the
# form the last one took ("Samsung Monitor Landscape (links beim
# Gaming)"). Invented vendors are unaffected, which is why the fixtures
# in test_monitors.py use "Acme, Inc." and "Screen Co".
#
# Short acronym vendors - AOC, LG, NEC, HP - are deliberately NOT in this
# list, and neither is Sharp: they collide with ordinary words and with
# kernel driver names, and a guard that cries wolf is one somebody
# weakens later. That is the trade this list makes, stated rather than
# hidden.
DISPLAY_VENDORS = (
    "Samsung", "Acer", "Dell", "BenQ", "Iiyama", "Philips", "ViewSonic",
    "Eizo", "Lenovo", "Goldstar", "LG Electronics", "Ancor", "Hewlett",
    "Fujitsu", "Medion", "Sceptre", "HannStar", "InfoVision", "Chimei",
    "AU Optronics", "Japan Display", "ASUSTek", "Sony",
)
VENDOR_NAME = re.compile(r"\b(" + "|".join(DISPLAY_VENDORS) + r")\b", re.I)

# A model designation is not recognisable by shape alone: a monitor's
# model reads exactly like the Unicode codepoints kitty-config.template
# is full of (F43A, E00A). What makes it recognisable is the company it
# keeps - a line that reads a monitor's identity fields. Both halves have
# to match, so the codepoints stay legitimate and a model name used to
# pick out one screen does not.
IDENTITY_CONTEXT = re.compile(
    r"\.description\b|\.make\b|\.model\b"
    r"|\$\{?description\b|\$\{?make\b|\$\{?model\b"
    r"|monitor:desc:|\bEDID\b|hyprctl monitors")
MODEL_DESIGNATION = re.compile(
    r"\b(?:[A-Za-z]{1,4}[0-9]{2,4}[A-Za-z][A-Za-z0-9]*"
    r"|[0-9]{2,3}[A-Za-z]{2,4}[0-9]{2,4}[A-Za-z0-9]*)\b")


def _looks_like_a_serial(token: str) -> bool:
    return (sum(c.isdigit() for c in token) >= SERIAL_MIN_DIGITS
            and sum(c.isalpha() for c in token) >= SERIAL_MIN_LETTERS)


def test_no_hardcoded_monitor_identity_remains():
    """The class the older guard below could not see.

    That pattern - seven device and employer names - reported this tree
    clean while bar-workspace-detect-config.template selected monitors
    by three EDID serial numbers, named its two branches after the desks
    those monitors stood on, and grid-wallpaper-toggle.template placed
    wallpapers by matching the EDID vendor field against two display
    manufacturers. None of that is a hostname or an employer, so none of
    it was ever in scope. The guard was green over a second copy of
    exactly the hardware binding Task 6 had just removed from its twin.

    The three serials and the two desk labels are in the denylist in
    tests/origin_data.py now, as digests, so they are also caught by
    name and by content anywhere in the repository - including in this
    file, which is how they came to be described here rather than
    quoted.

    WHAT THIS COVERS
      * EDID serial-shaped tokens, by shape - a serial nobody has seen
        yet is caught the same as the three above.
      * Named display manufacturers, in code and in comments alike.
      * Model designations on a line that reads a monitor's identity
        fields (.description, .make, .model, desc:, EDID).

    WHAT IT DOES NOT COVER, honestly
      * A model designation with no vendor beside it and no identity
        field on its line: "U2723QE" alone is the same shape as a hex
        constant, and there is no way to tell them apart without a list
        of models, which is the kind of list this guard exists to avoid.
      * Short serials. One large vendor's service tags are seven
        characters; the threshold is eight, because seven also matches
        RFC1918.
      * A serial glued into a longer identifier by underscores and dots,
        the shape a PipeWire or ALSA device node takes. `\b` finds no
        token boundary there. EDID descriptions are space-separated, so
        this does not affect monitors - but it is why the audio
        templates that bind one person's headset, microphone and webcam
        by USB id do not show up here. They are the same disease in
        another organ and need their own change, not a wider pattern:
        widening it far enough to see them makes it fire inside every
        device path in the tree. The one that is still in the tree is
        named, with its line count, in KNOWN_UNFIXED below - the
        denylist does see it, and says so until somebody fixes it.
      * Models whose designation ends in digits. The trailing letter is
        what separates a model name from sha256.
      * Anything outside src/. Hardware names in the spec, the plans and
        the test fixtures are not covered by THIS rule; the denylist in
        test_no_device_or_employer_names_remain covers the whole
        repository and the reasons the two scopes differ are set out
        there.
      * A desk encoded WITHOUT names - three monitors assumed by count,
        a wallpaper placed by a hardcoded x threshold. No pattern sees
        that. tests/src/test_grid_wallpaper.py and test_tty_rotation.py
        cover the two places it lived.
    """
    offenders = []
    for path in _shipped_files():
        for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1):
            where = f"{path.relative_to(SRC)}:{number}"
            for token in SERIAL_TOKEN.findall(line):
                if _looks_like_a_serial(token):
                    offenders.append(f"{where}: serial-shaped {token}")
            vendor = VENDOR_NAME.search(line)
            if vendor:
                offenders.append(f"{where}: display vendor {vendor.group(1)}")
            if IDENTITY_CONTEXT.search(line):
                for model in MODEL_DESIGNATION.findall(line):
                    offenders.append(f"{where}: model designation {model}")

    assert offenders == [], (
        "hardcoded monitor identities left: " + "; ".join(offenders[:15]))


def test_the_monitor_identity_guard_would_catch_a_new_one():
    """The guard's own regression test.

    Every pattern above is written to be precise, and precision tightened
    far enough stops catching anything - which is exactly how the older
    guard came to report clean over three serial numbers. So each rule is
    exercised against a line it must catch and a line it must leave
    alone, and the "must leave alone" half is the one that keeps this
    from being made to pass by widening the patterns until they match
    everything.
    """
    def offends(line: str) -> bool:
        if any(_looks_like_a_serial(t) for t in SERIAL_TOKEN.findall(line)):
            return True
        if VENDOR_NAME.search(line):
            return True
        return bool(IDENTITY_CONTEXT.search(line)
                    and MODEL_DESIGNATION.search(line))

    # Every serial, model and desk label below is INVENTED. The three
    # real serials the old guard missed are not written here any more,
    # and they do not need to be: this test measures the pattern, and a
    # pattern that catches an invented serial of the same shape catches
    # a real one. The real ones are covered, as digests, by
    # test_no_device_or_employer_names_remain.
    caught = [
        # The shape the three missed serials had.
        'select(.description | test("VKPQR00913")) | .name',
        'monitor=desc:Acme ABCD01234, 1920x1200@60',
        # A serial nobody has written yet.
        'if [[ "$description" =~ QQZZ99881 ]]; then',
        # Vendors, in code and in a comment.
        'elif [[ "$make" =~ Samsung ]]; then',
        '# Acer Monitor Landscape (rechts bei beiden Setups)',
        '            echo "Configuring the Samsung desk workspaces"',
        # A model designation next to an identity field.
        'jq -r \'.[] | select(.model == "ZQ915WX") | .name\'',
    ]
    for line in caught:
        assert offends(line), f"the guard would miss: {line}"

    left_alone = [
        # Hyprland's selector itself, and how monitors.py builds it.
        'return f"desc:{description}"',
        'lines.append(f"workspace={number},monitor:{target}")',
        # Reading the identity fields generically is the FIX, not the bug.
        "hyprctl monitors -j | jq -r '.[] | \"\\(.name) \\(.x)\"'",
        # Unicode codepoints, which have a model designation's shape and
        # nothing to do with monitors.
        'map U+F43A JetBrainsMono Nerd Font',
        # Documentation-range addresses, from the watchdog tests.
        'TEST_HOST = "198.51.100.1"',
        'default via 203.0.113.1 dev eth0 metric 600',
        # Constants that are capitals and digits but not serials.
        'RFC1918 networks are routed through the tunnel',
        'WORKSPACES = tuple(range(1, 11))',
        # An invented vendor, as the fixtures use.
        'LEFT = "Screen Co Model X 1111"',
    ]
    for line in left_alone:
        assert not offends(line), f"the guard cries wolf over: {line}"


# Files that are KNOWN to still carry one of the forbidden strings, with
# the exact number of lines each one carries. Not an exemption list: the
# assertion below checks the count in both directions, so a file that
# grows a second occurrence fails, and a file that is fixed fails too,
# with a message telling whoever fixed it to delete the entry. The same
# self-expiring shape KNOWN_PLACE_BOUND uses in test_new_templates.py.
#
#   * The audio template that pinned one person's webcam microphone by
#     its USB device id is FIXED and its entry is therefore gone. The
#     device names come from user settings now (src/audio.py,
#     tests/src/test_hardware.py), and an unset one produces a config
#     that says so instead of a rule matching nothing.
#   * The second clock was a timezone naming the author's other home
#     town, next to a flag emoji on the same line. It is FIXED too: both
#     one-line clock templates are gone, and bar-clocks-config.template
#     takes its zones from `clocks.zones` in the user settings and
#     renders nothing when there are none (src/clocks.py,
#     tests/src/test_clocks.py). test_new_templates.py carried the
#     identical exception and is empty for the same reason; the two
#     disappeared together, as both comments said they would.
#
# EMPTY is therefore the finished state, and the dict stays so that the
# next exception somebody has to make is an edit rather than a new
# mechanism.
KNOWN_UNFIXED = {}


def test_no_device_or_employer_names_remain():
    """The first deletion list was built from template names. These are the
    names that only appear in file contents, which is why a name-based
    search missed them.

    Green over src/ since Task 6. It stood at xfail(strict=True) through
    Tasks 5 and 6, first over six lines in style_definition.py,
    user_settings.py, vpn-connect-script.template and
    ags-vpn-settings.template, and finally over the last two:
    hypr-monitor-detect-config.template matched the machine's name
    against two workstations to decide which monitor layout to load.
    Those two lines are gone, and the layout now comes from the monitors
    actually attached.

    WHAT CHANGED HERE, and why it is a widening
      * The seven literals are gone from this source. They are digests in
        tests/origin_data.py, and seventeen more are with them: the EDID
        serials, the service tag, the USB device id, the two desk labels,
        the two place names, the two one-machine paths, the file server,
        the internal address, the build tool's two product names and its
        issue-tracker prefix. A rule cannot be read off the page any more,
        and it no longer matches its own source - which is what let this
        guard be extended past src/ at all.
      * The scan was `src/` only, on the argument that "only what ships
        can carry a name to a machine". That argument is about machines.
        This repository is going to be PUBLISHED, and `tests/` and
        `docs/` are published with it - which is precisely where the data
        survived, in the files whose job was to remove it. The scan now
        reads every file in the repository.
      * File and DIRECTORY names are scanned as well as contents. A
        template named after a city or an internal host leaks it without
        a single line of content, and the name-based deletion list of
        Task 1 is exactly the kind of thing that would put one back. The
        directory half was added because a mutation test planted an
        empty one and this went green over it.

    WHAT THIS DOES NOT COVER, honestly
      * Anything not in the denylist. It is a list of known strings, and
        a list cannot catch what nobody has written down. That is what
        the shape rules above and below are for, and why they were not
        replaced by this.
      * The shape rules are still scoped to src/, deliberately. Widening
        THEM to tests/ would fire on their own meta-tests: a test that
        proves a serial-shaped pattern works has to contain a
        serial-shaped token. Measured before it was decided - over
        tests/ and docs/ those rules produce 60 findings, of which every
        single one is a fixture, a vendor list or a docstring that has to
        say what the rule catches. A denylist has no such problem once
        the literals are digests, which is why this rule could be
        widened and those could not.
    """
    offenders = []
    kinds = {}
    for path in repository_directories():
        relative = path.relative_to(REPOSITORY).as_posix()
        if ORIGIN.hits(relative):
            offenders.append(f"{relative}: the directory name itself")
            kinds[relative] = what_kind(relative)
    for path in repository_files():
        relative = path.relative_to(REPOSITORY).as_posix()
        if ORIGIN.hits(relative):
            offenders.append(f"{relative}: the file name itself")
            kinds[relative] = what_kind(relative)
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        for number in ORIGIN.offending_lines(text):
            offenders.append(f"{relative}:{number}")
            kinds.setdefault(relative, what_kind(lines[number - 1]))

    expected = sum(KNOWN_UNFIXED.values())
    counted = {name: 0 for name in KNOWN_UNFIXED}
    unexpected = []
    for offender in offenders:
        name = offender.rsplit(":", 1)[0]
        if name in counted:
            counted[name] += 1
        else:
            unexpected.append(offender)

    assert unexpected == [], (
        "the origin's data is still in the repository, at: "
        + "; ".join(unexpected[:15])
        + " - what kind, per file: "
        + "; ".join(f"{name} -> {kind}" for name, kind in sorted(kinds.items())
                    if any(o.startswith(name) for o in unexpected))
        + ". The string itself is deliberately not printed; see "
        "tests/origin_data.py for why.")
    assert counted == KNOWN_UNFIXED, (
        f"KNOWN_UNFIXED says {KNOWN_UNFIXED} but the scan found {counted}. "
        "A file that dropped to zero is fixed - delete its entry. A file "
        "that went up has gained a new occurrence.")
    # THE LIVE EVIDENCE IS GONE, and this is the note the previous
    # version of this comment asked for.
    #
    # It read: one of the twenty-four entries is demonstrably matching a
    # file in this tree right now, which is proof the digests still match
    # real content and not merely each other - proof no assertion built
    # from invented plaintext can give. It was two until the audio
    # templates were made settings-driven, one until the second clock
    # followed, and it is now none: nothing in the tree carries any of
    # the forbidden strings, which is the whole point of the exercise and
    # also the end of that proof.
    #
    # What is left in its place is test_the_denylist_would_catch_a_new_one
    # below, which puts the SAME machinery through a second denylist
    # built from invented plaintext, and checks that the real one has not
    # been emptied or trimmed. That is weaker in exactly one way, stated
    # rather than hidden: it proves the mechanism works and that the
    # table is populated, not that the table's contents are the strings
    # that were meant to go in it.
    assert expected == 0


def test_the_denylist_would_catch_a_new_one():
    """The machinery above, measured - without a real string anywhere.

    Every guard in this file has a companion like this because precision
    tightened far enough stops catching anything, and a denylist has an
    extra way to die: it can be emptied. The digests cannot be exercised
    directly, because exercising them means writing down what they hash.
    So this builds a SECOND denylist out of invented plaintext and puts
    the mechanism through the same lines the old regex was responsible
    for - normalisation, case folding, substring matching, the separator
    spellings, the length bounds - and then checks that the real one has
    not been emptied or trimmed.
    """
    from tests.origin_data import LONGEST, WINDOW, Denylist

    fake = Denylist.from_plaintext([
        "qzrx",                 # exactly the stage-one window, the minimum
        "qxro",                 # for the joining hazard, below
        "qzworkhost",
        "VKPQR00913",           # a serial's shape, invented
        "srv-nowhere",          # two parts, written with a hyphen
        "10.99.255.254",
        "Acme Branch Office",   # three parts, written with spaces
    ])

    caught = [
        "hostname = qzrx",
        "QZRX",                                   # case folded
        "template_for_qzrxxx.conf",               # substring, not token
        "profiles/QZWORKHOST1/monitors.conf",     # a digit appended
        'select(.description | test("VKPQR00913"))',
        "search_domain = srv-nowhere.example",
        "server: srv_nowhere",                    # underscore spelling
        "the srv nowhere box",                    # space spelling
        "nameserver 10.99.255.254",
        'echo "Configuring Acme Branch Office workspaces"',
        "acme-branch-office-config.template",     # hyphen spelling
        # The cost of matching every separator spelling, stated rather
        # than hidden: two identifiers that happen to sit next to each
        # other in the forbidden order also match. This line is not the
        # host - it is an assignment - and the guard fires on it anyway.
        # The trade is worth it because the alternative is missing the
        # host whenever somebody writes it with the other separator, and
        # because the price is one false positive on a line nobody writes.
        "srv = nowhere()",
    ]
    for line in caught:
        assert fake.hits(line), f"the denylist would miss: {line}"

    left_alone = [
        # The joining hazard that collapsing separators - rather than
        # deleting them - exists to prevent. Deleting would turn both of
        # these into an entry above; collapsing leaves the separator in
        # place, so neither matches.
        "for row in range(qx, rows):",
        "qz rx",
        # Near misses that are genuinely not the entry.
        "hostname = qzr",
        "nameserver 10.99.255.25",
        "qzworkhos",
        "VKPQR0091",
        "the acme office branch",                 # the parts, wrong order
    ]
    for line in left_alone:
        assert not fake.hits(line), f"the denylist cries wolf over: {line}"

    # An entry the mechanism could never find must be refused when it is
    # added, not silently ignored - a denylist that accepts an entry and
    # never matches it is the failure this whole file is about.
    for impossible in ("ab", "x" * (LONGEST + 1)):
        try:
            Denylist.from_plaintext([impossible])
        except ValueError:
            continue
        raise AssertionError(f"{impossible!r} was accepted and cannot match")

    # And the real list is still a list. Emptying it, or quietly dropping
    # entries while keeping the file, would leave every assertion above
    # passing over a guard that matches nothing.
    assert len(ORIGIN) == 24, (
        f"the denylist holds {len(ORIGIN)} entries, not 24 - if that is "
        "intended, say so here and in tests/origin_data.py")
    assert WINDOW == 4 and LONGEST >= 18


# --------------------------------------------------------------------
# the previous employer's toolchain
# --------------------------------------------------------------------
#
# Every guard above searches for a NAME that stood on a file. Task 1's
# deletion list did the same, and that is precisely what let the largest
# survivor through: zshrc-config.template - which generate_config.sh
# writes to $HOME/.zshrc, so it ships and runs - carried 485 lines of the
# employer's build tool INSIDE it, as a shell function called `ZepOS`. The
# file's own name says nothing about that, and neither does any of the
# three patterns above. Two more templates carried the same toolchain in
# smaller pieces: window rules for two of its binaries, and comments
# naming its network component.
#
# So these rules read the same way the monitor-identity guard does - on
# the SHAPE of what a private toolchain looks like inside a config, not
# on the strings that happen to be in the tree today.

# The toolchain's own identifier: the command, the variable holding its
# checkout, its binaries and its application ids. Word-bounded on both
# sides, with `_` spelled out because the underscore is itself a word
# character: `\base\b` finds the tool's name inside a hyphenated binary
# name and inside a dotted application id, but walks straight past the
# variable that appends `_root` to it.
#
# The three letters stay in plaintext here, where the other literals did
# not. Two reasons, both of them true. A three-letter sequence is below
# the denylist's minimum entry length and would be recovered from a
# digest in milliseconds, so hashing it would buy nothing and pretend to
# buy something. And this rule is not a string comparison: what makes it
# work is the word boundary on one side and the underscore alternative
# on the other, which a hashed substring search cannot express.
#
# Three letters is short enough to worry about. It does not fire inside
# database, please, phase, release or case, because none of those has a
# word boundary in front of the name - which is what the boundary is
# there for.
#
# The name is assembled from its code points rather than written out.
# The history rewrite removed it from every revision of this repository,
# and a file that spells it puts it straight back. But a guard against a
# word has to know the word, and this one cannot move into
# tests/origin_data.py: that mechanism needs at least four characters and
# cannot express a word boundary.
#
# This is not secrecy - anyone reading this line can evaluate it in a
# second. It keeps the literal out of the file, out of a grep and out of
# a search engine, while the guard and the proof below stay exact.
TOOLCHAIN = "".join(map(chr, (97, 115, 101)))
TOOLCHAIN_NAME = re.compile(rf"\b{TOOLCHAIN}(?:\b|_)", re.IGNORECASE)

# Its per-module repositories. Six products x two tiers, all named to one
# scheme: <product>-client-<surface>, <product>-server-<role>. The six
# product codes are deliberately neither listed here nor in the denylist
# - two of them are ordinary English words, and a guard that fires on
# those is one somebody weakens later. The scheme is what is
# recognisable, and it catches a seventh product nobody has written yet.
PRODUCT_MODULE = re.compile(r"\b[a-z]{2,4}-(?:client|server)-[a-z]+\b")

# An identifier from the employer's issue tracker: three or four capitals,
# an underscore, and a six-digit date. Constants of the STYLE_COLOR_1920
# kind do not match - four digits, not six, and no boundary before the
# capitals - and neither does a timestamp of the .backup.20260101 kind,
# because eight digits leave no word boundary after the sixth.
TICKET_ID = re.compile(r"\b[A-Z]{2,4}_[0-9]{6}\b")

# The part that is not merely embarrassing. The tool advertised a mode
# that runs a build through a cgroup-confined WireGuard tunnel and named,
# in its own --help, the commercial intrusion-detection system that mode
# exists to be invisible to. Publishing that in a distribution documents
# an evasion technique against a product by name - which is why the
# product's name and the tunnel component's name are not written here.
# They moved into the denylist in tests/origin_data.py, where they are
# digests and where the scan is the whole repository rather than src/
# alone: strictly more coverage than this line had, in a form that does
# not reproduce the disclosure in the act of preventing it.
#
# What stays is "covert", which is a real English word and belongs here
# anyway: a desktop configuration has no use for it, and the one place it
# appeared was that flag. It is bounded at the FRONT only - the help text
# also said "run covertly", and a closing boundary would have let the
# adverb through - which leaves "convert", "recover" and "coverage"
# unaffected, since none of them begins with "covert" at a word boundary.
EVASION = re.compile(r"\bcovert", re.IGNORECASE)

# An absolute path that exists on exactly one machine: somebody's home
# directory by name, or a source root mounted at /mnt. Both were in the
# tree - an absolute path into one person's home seven times, and the
# build tool's checkout under /mnt twice - and neither is reachable by
# searching for `~`, which is the search the design document based its
# "the repo is already path-portable" claim on.
#
# `/home` without a following segment is deliberately allowed:
# ags-disk.template asks whether a MOUNT POINT starts with it, which is a
# fact about Linux rather than about a user.
FOREIGN_PATH = re.compile(r"/home/[A-Za-z0-9._-]|/mnt/[A-Za-z0-9._-]")


def _toolchain_findings(line: str) -> list[str]:
    """What is wrong with one line, named. Empty means nothing."""
    findings = []
    if TOOLCHAIN_NAME.search(line):
        findings.append("toolchain name")
    if PRODUCT_MODULE.search(line):
        findings.append("product module")
    if TICKET_ID.search(line):
        findings.append("ticket id")
    if EVASION.search(line):
        findings.append("evasion vocabulary")
    return findings


def _foreign_path_findings(line: str) -> list[str]:
    match = FOREIGN_PATH.search(line)
    return [f"one machine's path ({match.group(0)})"] if match else []


def test_no_employer_toolchain_remains():
    """The 485 lines Task 1 reported as removed and never opened.

    WHAT THIS COVERS
      * The tool's name wherever it is used as one - command, variable,
        binary, application id, syntax-highlighting rule.
      * Its module naming scheme, so a product that was never in the
        portfolio is caught the same as the six that were.
      * Issue-tracker identifiers, by shape.
      * The vocabulary of the covert-tunnel mode.

    WHAT IT DOES NOT COVER, honestly
      * The product codes themselves. Two of the six are ordinary English
        words and two more are ordinary abbreviations; a pattern matching
        them fires on half the tree.
      * Service ports. 8080 and 9001 belong to nobody, and a guard on
        them would be a guard on every HTTP example ever written.
      * Build tooling by name (npm, node, cmake). They are in a
        distribution's repositories; using them is not a leak.
      * Anything outside src/, by shape. These are shape rules and their
        own meta-test has to contain the shapes, so widening them to
        tests/ would make this file fail over itself. The two NAMES that
        used to be in EVASION - the tunnel component and the
        intrusion-detection product - are in the denylist instead, and
        that scan does cover the whole repository. The scope narrowed for
        the shapes and widened for the names, which is the right way
        round: a shape has a legitimate reason to appear in a test, and
        a name does not.
    """
    offenders = []
    for path in _shipped_files():
        for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1):
            for finding in _toolchain_findings(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {finding}")

    assert offenders == [], (
        "the employer's toolchain is still in the tree: "
        + "; ".join(offenders[:15]))


def test_no_path_from_one_machine_remains():
    """A hardcoded home is not a cosmetic defect.

    restore-latest-backup is the tool validate_output.py names as the
    reason backups are written at all - "so a bad generation can be
    undone". With its author's own home directory compiled into the
    config path, every other user got "Config file not found" and exit 1
    while a perfectly good backup sat next to the file it names.
    """
    offenders = []
    for path in _shipped_files():
        for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1):
            for finding in _foreign_path_findings(line):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {finding}")

    assert offenders == [], (
        "paths that exist on one machine only: " + "; ".join(offenders[:15]))


def test_the_toolchain_guard_would_catch_a_new_one():
    """The two guards above, tested against lines they must catch and
    lines they must leave alone.

    Without this half, both are free to be "fixed" by tightening a
    pattern until it matches nothing - which is exactly the state the
    inventory was in when a template-name list reported the entkernung
    complete over 485 lines of the tool it was supposed to remove.
    """
    # The constant, pinned before anything derived from it is trusted.
    #
    # Both the guard's pattern and every fixture below are built from
    # TOOLCHAIN, so changing it changes both in step and this test would
    # pass over any word at all - measured: setting it to "qqzz" left
    # this test green. A digest is what makes the two independent again:
    # it says WHICH word the guard is for without spelling it, so a
    # tightened or emptied constant fails here instead of quietly
    # redefining what the guard is about.
    from tests.origin_data import _digest, normalise
    assert _digest(normalise(TOOLCHAIN)) == "02a137baa7e806b7838e399083b4b1df", (
        "TOOLCHAIN is no longer the name this guard exists for")

    def offends(line: str) -> bool:
        return bool(_toolchain_findings(line) or _foreign_path_findings(line))

    # The paths, the application id, the module name and the ticket
    # identifiers below are INVENTED and have the shape of the real ones.
    # A shape rule is measured by shapes; putting the real strings here
    # to prove the rule would leave the file carrying exactly what the
    # rule exists to remove, which is the state this whole review found.
    caught = [
        # The function's own head and the checkout it hardcoded.
        f'{TOOLCHAIN}() {{',
        f'    local {TOOLCHAIN}_root="/mnt/build/checkout/{TOOLCHAIN}"',
        f"alias lga='cd /mnt/build/checkout/{TOOLCHAIN} && lazygit'",
        # The highlighting that made the command look native to the shell.
        f"ZSH_HIGHLIGHT_REGEXP+=('^{TOOLCHAIN} ' 'fg=#ff8800,bold')",
        # One of its binaries, as a window rule in a compositor config.
        rf'windowrule = match:class ^(com\.example\.{TOOLCHAIN}\.viewer)$, float on',
        # A branding line in a stylesheet header.
        f'// Generated by ZepOS - {TOOLCHAIN.upper()} Muted Dark Theme',
        # A module named to the portfolio's scheme with the tool's name
        # nowhere on the line, and a product that never existed.
        '(cd "$root/clients/qzr-client-web" && node run.cjs dev)',
        'zzz_dir="$root/servers/zzz-server-world"',
        # The covert mode, with every name removed - the evasion
        # vocabulary alone has to be enough, and both the adjective and
        # the adverb have to land.
        'echo "  -C   Run the build through the covert slice"',
        'echo "  build, run covertly through the tunnel"',
        # Issue-tracker identifiers.
        '# --- sudo-askpass via pass (security hardening, ZQR_260504) ---',
        '# Bind IKE source to default-route interface (Phase 9 / ZQR_260507)',
        # One machine's paths, in the two shapes they took.
        '[[ -f "/home/someone/.local/completions/tool.zsh" ]]',
        'CONFIG_PATH="/home/someone/.config/hypr/hyprland.conf"',
        f'local conda_python="/mnt/data/.conda/envs/{TOOLCHAIN}/bin/python"',
    ]
    for line in caught:
        assert offends(line), f"the guard would miss: {line}"

    left_alone = [
        # the name inside ordinary words, which is why the boundaries exist.
        '# the database is released in phases, and each case is handled',
        '# please rebase before merging',
        # The correct way to name the user's configuration, in both the
        # generator's spelling and the fixed restore tool's.
        'ZEPOS_USER_ROOT="${ZEPOS_USER_ROOT:-${XDG_CONFIG_HOME:-$HOME/.config}/zepos}"',
        'CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"',
        # A mount point that happens to be spelled /home. ags-disk.template
        # asks exactly this, and it is a fact about Linux, not a user.
        'if (mount.startsWith("/home")) return ICONS.home',
        # Constants that have a ticket id's rough shape and are not one.
        'BACKUP_SUFFIX = ".backup.%Y-%m-%d-%H%M%S"',
        'STYLE_COLOR_1920 = "#1e1e2e"',
        'workspaces-generated.conf.backup-20260101-120000',
        # Words the evasion pattern must not swallow.
        '# the watchdog recovers the connection without covering it up',
        '# convert the value before the coverage report is written',
        # Hyphenated names this tree is full of.
        'network-manager-gui-config.template',
        'bar-workspace-detect-config.template',
    ]
    for line in left_alone:
        assert not offends(line), f"the guard cries wolf over: {line}"
