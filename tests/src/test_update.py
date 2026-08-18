# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Selbstaktualisierung, und die Frage, ob ihre Regler etwas bewegen.

WARUM JEDE EINSTELLUNG HIER ZWEIMAL VORKOMMT
    In diesem Baum ist schon einmal eine ganze Reglertabelle gebaut
    worden, die kein einziges erzeugtes Byte veraendert hat -
    src/sizes.py haelt die Messung fest: 479 von 679 Stilnamen werden von
    keiner Vorlage gelesen. Eine Einstellung ist erst dann eine
    Einstellung, wenn sich etwas Messbares aendert, wenn man sie aendert.

    Jeder Regler wird deshalb an dem geprueft, was aus ihm herauskommt:
    an der Zeitgeber-Ergaenzung Zeile fuer Zeile, an der Befehlszeile,
    die pacman bekommt, und an den Befehlen, die ein vollstaendiger Lauf
    wirklich abgesetzt hat.

WARUM DIE VERGLEICHE ZEILENGENAU UND OHNE KOMMENTARE SIND
    `"OnBootSec=2min" in text` ist auch dann wahr, wenn die Zeichenkette
    nur im Kommentarkopf steht, der erklaert, wozu OnBootSec da ist. Jede
    Zusicherung unten laeuft ueber _code(), das jede reine
    Kommentarzeile entfernt, und vergleicht danach ganze ZEILEN.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import conftest

SRC = Path(__file__).resolve().parents[2] / "src"
BIN = SRC / "bin"
REPO = SRC.parent


@pytest.fixture
def update(monkeypatch, tmp_path):
    """Das Modul, mit allen drei Wurzeln in tmp_path.

    Die Umlenkung ist nicht Bequemlichkeit: ohne sie schriebe jeder Test
    nach /etc/zepos, /var/lib/zepos und /etc/systemd/system. Die
    Isolationssperre in tests/conftest.py laesst das nicht zu - und genau
    deshalb ist sie da.
    """
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.setenv("ZEPOS_MACHINE_ROOT", str(tmp_path / "etc-zepos"))
    monkeypatch.setenv("ZEPOS_STATE_ROOT", str(tmp_path / "var-lib-zepos"))
    monkeypatch.setenv("ZEPOS_SYSTEMD_ETC", str(tmp_path / "etc"))
    import update as module

    return module


@pytest.fixture
def cli(monkeypatch, update):
    monkeypatch.syspath_prepend(str(SRC))
    import cli as module

    return module


@pytest.fixture
def doctor(monkeypatch, update):
    monkeypatch.syspath_prepend(str(SRC))
    import doctor as module

    return module


def _code(text: str) -> list[str]:
    """Die Zeilen ohne reine Kommentarzeilen und ohne Leerzeilen.

    Siehe den Kopf dieser Datei: eine Zusicherung gegen den Wortlaut
    einer Datei, die ihre eigene Begruendung mitliefert, trifft sonst die
    Begruendung.
    """
    return [line for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


class Machine:
    """Ein pacman, ein loginctl und ein systemctl, die nur antworten.

    Sie schreiben mit, was gefragt wurde. Was ein Lauf TUT, ist damit
    genau die Liste, die hier ankommt - und nicht das, was eine Zusage im
    Kopf des Moduls verspricht.
    """

    def __init__(self, *, upgradable: str = "", members: str = "",
                 sessions: str = "[]", codes: dict[str, int] | None = None,
                 output: dict[str, str] | None = None):
        self.upgradable = upgradable
        self.members = members
        self.sessions = sessions
        self.codes = codes or {}
        self.output = output or {}
        self.commands: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        argv = list(argv)
        self.commands.append(argv)
        stdout, code = "", 0
        if argv[:2] == ["pacman", "-Qu"]:
            stdout = self.upgradable
            code = 0 if self.upgradable.strip() else 1
        elif argv[:2] == ["pacman", "-Slq"]:
            stdout = self.members
        elif argv[0] == "loginctl":
            stdout = self.sessions
        for key, value in self.codes.items():
            if key in " ".join(argv):
                code = value
        for key, value in self.output.items():
            if key in " ".join(argv):
                stdout = value
        return subprocess.CompletedProcess(argv, code, stdout, "")

    @property
    def programs(self) -> list[str]:
        return [command[0] for command in self.commands]

    def called(self, program: str) -> list[list[str]]:
        return [c for c in self.commands if c[0] == program]


# Zwei Aktualisierungen aus [zepos] und eine aus der Arch-Basis. Der
# Name des dritten faengt NICHT mit zepos- an und der eine aus dem
# Repository heisst nicht so - genau die Verwechslung, die ein
# Praefixfilter machen wuerde.
UPGRADABLE = ("zepos-config 0.1.0-1 -> 0.1.1-1\n"
              "aylurs-gtk-shell 3.1.2-1 -> 3.1.3-1\n"
              "linux 6.16.1-1 -> 6.16.2-1\n")
MEMBERS = "zepos-config\naylurs-gtk-shell\nzepos-desktop\n"
SESSION = '[{"session":"1","uid":1000,"user":"zep","seat":"seat0"}]'


# --------------------------------------------------------------------
# Die ausgelieferte Einheit
# --------------------------------------------------------------------

def test_the_shipped_timer_is_exactly_what_the_defaults_render(update):
    """Zwei Definitionen einer Voreinstellung sind eine zu viel.

    src/system/zepos-update.timer wird ausgeliefert; update.defaults()
    ist das, was jeder Lauf und jede Ergaenzung fuer die Voreinstellung
    haelt. Liefen sie auseinander, saehe beides fuer sich richtig aus -
    und eine Maschine, an der niemand etwas eingestellt hat, haette einen
    anderen Zeitplan als eine, die einmal `zepos-settings set` gesehen
    hat.
    """
    shipped = (SRC / "system" / "zepos-update.timer").read_text(
        encoding="utf-8")
    assert shipped == update.timer_unit(update.defaults())


def test_the_timer_starts_the_service_and_the_service_starts_nothing(update):
    """Der [Install]-Abschnitt gehoert dem Zeitgeber und nur ihm.

    Ein WantedBy im Dienst waere eine Aktualisierung bei jedem Start -
    ohne Verzoegerung, ohne Streuung, und damit ohne alles, was die
    Entscheidung "wann" ausmacht.
    """
    timer = _code((SRC / "system" / "zepos-update.timer").read_text("utf-8"))
    service = _code((SRC / "system" / "zepos-update.service").read_text("utf-8"))

    assert "[Install]" in timer
    assert f"Unit={update.SERVICE_UNIT}" in timer
    assert "WantedBy=timers.target" in timer
    assert "[Install]" not in service, (
        "der Dienst hat einen [Install]-Abschnitt und laeuft damit bei "
        "jedem Start, am Zeitgeber vorbei")
    assert "ExecStart=/usr/bin/zepos-update" in service
    # Und die Zeile, deren FEHLEN gefaehrlich ist: ohne sie gilt
    # DefaultTimeoutStartSec = 90 Sekunden, und ein Type=oneshot, der
    # laenger braucht, wird abgeschossen - mitten in einer
    # pacman-Transaktion, auf einer Maschine, an der niemand sitzt.
    # Schon das `pacman -Sy` der Arch-Basis liegt darueber.
    assert "TimeoutStartSec=infinity" in service, (
        "der Dienst erbt die 90-Sekunden-Frist von systemd und wird "
        "mitten im Einspielen abgebrochen")


# --------------------------------------------------------------------
# "Wann?" - und ob eine Aenderung daran ankommt
# --------------------------------------------------------------------

@pytest.mark.parametrize("key, value, expected", [
    ("on_boot", "2min", "OnBootSec=2min"),
    ("interval", "weekly", "OnCalendar=weekly"),
    ("interval", "6h", "OnUnitActiveSec=6h"),
    ("randomized_delay", "0", "RandomizedDelaySec=0"),
])
def test_every_part_of_the_schedule_reaches_the_dropin(update, key, value,
                                                       expected):
    """Ein Regler, der die erzeugte Datei nicht veraendert, ist keiner.

    Geprueft wird beides: dass die neue Zeile da ist UND dass sich die
    Datei ueberhaupt unterscheidet. Die zweite Haelfte faengt den Fall,
    in dem die Voreinstellung zufaellig schon so aussah.
    """
    config = update.defaults()
    config["schedule"][key] = value

    changed = update.timer_dropin(config)
    assert changed != update.timer_dropin(update.defaults())
    assert expected in _code(changed)


def test_persistent_survives_only_where_systemd_reads_it(update):
    """systemd wertet Persistent= ausschliesslich mit OnCalendar= aus.

    Eine Zeile, die nichts tut, ist schlimmer als keine: jemand liest
    sie und glaubt, verpasste Laeufe wuerden nachgeholt.
    """
    calendar = update.defaults()
    assert "Persistent=true" in _code(update.timer_dropin(calendar))

    calendar["schedule"]["persistent"] = False
    assert "Persistent=false" in _code(update.timer_dropin(calendar))

    timespan = update.defaults()
    timespan["schedule"]["interval"] = "6h"
    rendered = _code(update.timer_dropin(timespan))
    assert not [line for line in rendered if line.startswith("Persistent=")], (
        "Persistent steht in einer Ergaenzung ohne OnCalendar und "
        "behauptet damit ein Nachholen, das systemd nicht macht")


def test_the_dropin_clears_every_list_it_could_be_adding_to(update):
    """OnBootSec, OnCalendar und OnUnitActiveSec sind LISTEN.

    Eine zweite Zuweisung legt einen zweiten Zeitpunkt an, statt den
    ersten zu ersetzen. Ohne die Ruecksetzung ergaebe `interval: 6h`
    einen Zeitgeber, der alle sechs Stunden UND taeglich um Mitternacht
    feuert - die Einstellung saehe aus, als haette sie gewirkt, und der
    alte Plan liefe daneben weiter.
    """
    config = update.defaults()
    config["schedule"]["interval"] = "6h"
    rendered = _code(update.timer_dropin(config))

    for name in update.TIMER_LISTS:
        assert f"{name}=" in rendered, (
            f"{name} wird nicht geleert - die ausgelieferte Unit bringt "
            f"ihren Wert dann zusaetzlich mit")
    assert rendered.index("OnBootSec=") < rendered.index("OnUnitActiveSec=6h"), (
        "die Ruecksetzung steht hinter dem Wert und loescht ihn damit "
        "gleich wieder")


def test_a_bare_number_is_a_timespan_the_way_a_person_types_it(update):
    """`zepos-settings set update.schedule.randomized_delay 0` liest
    seinen Wert wie jede andere Einstellung: was als JSON durchgeht, IST
    JSON - und "0" geht als Zahl durch. Eine Pruefung, die nur
    Zeichenketten annimmt, lehnt genau die Schreibweise ab, die ein
    Mensch tippt.

    Gemessen, bevor der Messstand daran gescheitert ist: die erste
    Fassung antwortete auf diesen Befehl mit "muss eine systemd-
    Zeitspanne sein (15min, 1d, 90s, 0), nicht 0".

    systemd liest eine blanke Zahl als Sekunden, also ist sie nicht nur
    bequem, sondern richtig. `true` bleibt abgelehnt - bool ist in Python
    ein int, und eine Sekunde Streuung hat niemand gemeint.
    """
    config = update.defaults()
    config["schedule"]["randomized_delay"] = 0
    assert "RandomizedDelaySec=0" in _code(update.timer_dropin(config))

    config["schedule"]["randomized_delay"] = True
    with pytest.raises(update.UnusableConfig):
        update.validate(config)


@pytest.mark.parametrize("key, value", [
    ("on_boot", "15 Minuten"),
    ("on_boot", ""),
    ("interval", "taeglich"),
    ("interval", "Mon *-*-* 04:00:00"),
    ("randomized_delay", "eine Stunde"),
    # Eine blanke Zahl IST eine Zeitspanne (Sekunden) - eine negative
    # nicht, und `null` ist der Wert, den ein halb bearbeitetes JSON
    # hinterlaesst.
    ("on_boot", -5),
    ("on_boot", None),
])
def test_a_schedule_systemd_cannot_read_is_refused_here(update, key, value):
    """Eine Unit mit unlesbarer Zeitspanne ist nicht falsch eingestellt -
    sie ist WEG. systemd weist sie ab, und ein Zeitgeber, den es nicht
    gibt, feuert nie und beschwert sich nie."""
    config = update.defaults()
    config["schedule"][key] = value
    with pytest.raises(update.UnusableConfig) as refused:
        update.validate(config)
    assert f"update.schedule.{key}" in str(refused.value)


# --------------------------------------------------------------------
# "Was?" - nur unsere Pakete, die Basis wird gezaehlt
# --------------------------------------------------------------------

def test_what_belongs_to_the_repository_is_asked_and_not_guessed(update):
    """`zepos-*` waere die naheliegende Regel und sie ist falsch.

    aylurs-gtk-shell, libastal-* und wlogout kommen aus demselben
    Repository und heissen nicht so; ein Praefixfilter haette genau die
    Pakete stehen gelassen, die den Schreibtisch ausmachen. Umgekehrt
    darf ein fremdes Paket, das zufaellig zepos- heisst, nicht
    mitgenommen werden.
    """
    changes = update.parse_upgradable(
        UPGRADABLE + "zepos-fremd 1-1 -> 2-1\n")
    ours, base = update.split(changes, update.parse_repository(MEMBERS))

    assert [change.name for change in ours] == ["zepos-config",
                                                "aylurs-gtk-shell"]
    assert [change.name for change in base] == ["linux", "zepos-fremd"]


def test_the_default_scope_names_every_package_and_never_upgrades_the_world(
        update):
    """`-u` im Bereich "zepos" waere ein unbeaufsichtigtes `pacman -Syu`
    auf einem Rolling Release."""
    command = update.upgrade_command(update.defaults(),
                                     ["zepos-config", "aylurs-gtk-shell"])

    assert command == ["pacman", "-S", "--needed", "--noconfirm",
                       "zepos-config", "aylurs-gtk-shell"]
    for flag in update.FULL_UPGRADE_FLAGS:
        assert flag not in command


def test_the_scope_all_is_the_full_upgrade_and_says_so(update):
    """Wer es will, bekommt es - und zwar, weil er es entschieden hat."""
    config = update.defaults()
    config["scope"] = update.SCOPE_ALL
    assert update.upgrade_command(config, ["egal"]) == \
        ["pacman", "-Syu", "--noconfirm"]


def test_a_run_installs_ours_and_only_counts_the_arch_base(update):
    """Die zweite der drei Entscheidungen, an dem gemessen, was ein
    vollstaendiger Lauf wirklich abgesetzt hat."""
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    outcome = update.perform(update.defaults(), runner=machine)

    assert outcome.result == update.Outcome.OK
    assert [c.name for c in outcome.upgraded] == ["zepos-config",
                                                  "aylurs-gtk-shell"]
    assert [c.name for c in outcome.base_available] == ["linux"]

    installs = [c for c in machine.called("pacman")
                if c[1] not in ("-Sy", "-Qu", "-Slq")]
    assert installs == [["pacman", "-S", "--needed", "--noconfirm",
                         "zepos-config", "aylurs-gtk-shell"]], installs
    assert "linux" not in " ".join(installs[0])


def test_the_base_can_be_left_uncounted(update):
    """report_base=false spart die Meldung und nicht die Zurueckhaltung:
    angefasst wird die Basis in keinem der beiden Faelle."""
    config = update.defaults()
    config["report_base"] = False
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS)

    outcome = update.perform(config, runner=machine)
    assert outcome.base_available == ()
    assert [c.name for c in outcome.upgraded] == ["zepos-config",
                                                  "aylurs-gtk-shell"]


def test_scope_all_takes_the_base_with_it(update):
    config = update.defaults()
    config["scope"] = update.SCOPE_ALL
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS)

    outcome = update.perform(config, runner=machine)
    assert [c.name for c in outcome.upgraded] == ["zepos-config",
                                                  "aylurs-gtk-shell", "linux"]
    assert outcome.base_available == ()
    assert ["pacman", "-Syu", "--noconfirm"] in machine.commands


def test_nothing_to_do_is_an_answer_and_not_a_failure(update):
    """`pacman -Qu` endet mit 1, wenn nichts anliegt. Ein Lauf, der das
    fuer einen Fehler haelt, meldet auf einer aktuellen Maschine taeglich
    einen Fehlschlag - und die eine Meldung, auf die es ankommt, geht
    darin unter."""
    machine = Machine(upgradable="", members=MEMBERS)
    outcome = update.perform(update.defaults(), runner=machine)

    assert outcome.result == update.Outcome.NOTHING
    assert not outcome.failed
    assert machine.called("pacman")[-1][:2] == ["pacman", "-Qu"], (
        "es wurde etwas eingespielt, obwohl nichts anlag")


# --------------------------------------------------------------------
# Der Schalter
# --------------------------------------------------------------------

def test_switching_it_off_stops_the_run_and_takes_the_timer_with_it(update):
    """Zwei Haelften, und beide sind noetig: der Dienst tut nichts mehr,
    UND systemd haelt die Einheit nicht mehr. Nur die erste waere ein
    Zeitgeber, der taeglich aufwacht, um festzustellen, dass er nicht
    gewollt ist."""
    config = update.defaults()
    config["enabled"] = False
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS)

    outcome = update.perform(config, runner=machine)
    assert outcome.result == update.Outcome.DISABLED
    assert machine.commands == [], machine.commands

    assert update.systemd_actions(config) == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "disable", update.TIMER_UNIT],
        ["systemctl", "stop", update.TIMER_UNIT],
    ]
    assert update.systemd_actions(update.defaults())[1][1] == "enable"


# --------------------------------------------------------------------
# "Still oder mit Hinweis?"
# --------------------------------------------------------------------

def test_the_notification_setting_decides_who_hears_what(update):
    """Drei Einstellungen, drei Ausgaenge - und ein Fehlschlag, der auch
    dann durchkommt, wenn nur Aenderungen gemeldet werden sollen."""
    change = update.Change("zepos-config", "0.1.0-1", "0.1.1-1")
    changed = update.Outcome(result=update.Outcome.OK, upgraded=(change,))
    failed = update.Outcome(result=update.Outcome.FAILED, returncode=1,
                            message="Signatur unbekannt")
    quiet = update.Outcome(result=update.Outcome.NOTHING)

    config = update.defaults()
    assert update.notification(changed, config) is not None
    assert update.notification(failed, config).urgent
    assert update.notification(quiet, config) is None, (
        "eine taegliche Nachricht 'nichts zu tun' ist die zuverlaessigste "
        "Art, dafuer zu sorgen, dass die eine wichtige weggeklickt wird")

    config["notify"] = update.NOTIFY_FAILURES
    assert update.notification(changed, config) is None
    assert update.notification(failed, config) is not None

    config["notify"] = update.NOTIFY_NEVER
    assert update.notification(changed, config) is None
    assert update.notification(failed, config) is None


def test_a_notification_names_the_packages_and_the_next_login(update):
    """Die Antwort auf "was passiert mit meinem laufenden Schreibtisch",
    dort, wo der Nutzer sie liest."""
    change = update.Change("zepos-config", "0.1.0-1", "0.1.1-1")
    note = update.notification(
        update.Outcome(result=update.Outcome.OK, upgraded=(change,),
                       sessions=(update.Session(1000, "zep", "seat0"),)),
        update.defaults())

    assert "zepos-config" in note.body
    assert "Anmeldung" in note.body


def test_the_notification_reaches_the_session_and_not_root(update):
    """Der Dienst laeuft als root und muss in den Bus eines Benutzers
    sprechen. Ohne uid und Busadresse ginge die Nachricht an eine Sitzung,
    die es nicht gibt."""
    note = update.Notification("Kopf", "Text")
    commands = update.notify_commands(
        [update.Session(1000, "zep", "seat0"),
         update.Session(1001, "zwei", "seat1")], note)

    assert len(commands) == 2
    assert "--uid=1000" in commands[0]
    assert "--setenv=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus" \
        in commands[0]
    assert "--uid=1001" in commands[1]
    # Der Text kommt aus pacman und darf nirgends von einer Shell
    # gelesen werden: er steht als eigenes Argument da, nicht in einer
    # Zeichenkette, die noch einmal zerlegt wird.
    assert commands[0][-2:] == ["Kopf", "Text"]
    assert not any(part in ("sh", "bash", "-c") for part in commands[0])


def test_a_session_without_a_seat_gets_no_notification(update):
    """Eine SSH-Anmeldung hat keinen Sitzplatz, und eine Nachricht an sie
    geht ins Leere."""
    sessions = update.parse_sessions(json.dumps([
        {"session": "1", "uid": 1000, "user": "zep", "seat": "seat0"},
        {"session": "2", "uid": 1001, "user": "fern", "seat": ""},
    ]))
    assert [s.user for s in sessions] == ["zep"]


# --------------------------------------------------------------------
# Was ein unbeaufsichtigter Lauf NICHT tun darf
# --------------------------------------------------------------------

def test_an_unattended_run_never_regenerates_and_never_restarts_anything(
        update):
    """Die teuerste Zeile dieser Aufgabe, als Messung.

    generate_config.sh beendet an seinem Ende Waybar und AGS, damit die
    neue Konfiguration greift. Aus einem Zeitgeber heraus ist das eine
    Leiste, die dem Nutzer mitten in der Arbeit verschwindet - am
    11.08.2026 genau so passiert, auf der Maschine des Entwicklers.

    Gemessen an den Befehlen, die ein vollstaendiger Lauf samt
    Benachrichtigung wirklich abgesetzt hat, und nicht an einer Zusage im
    Kopf des Moduls.
    """
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    outcome = update.perform(update.defaults(), runner=machine)
    update.announce(outcome, update.defaults(), runner=machine)

    for command in machine.commands:
        for part in command:
            assert Path(part).name not in update.FORBIDDEN_PROGRAMS, (
                f"ein unbeaufsichtigter Lauf hat {part} aufgerufen: "
                f"{command}")
    assert machine.programs.count("pacman") == 4


def test_a_package_swap_leaves_a_mark_for_the_next_login(update, monkeypatch):
    """Die neue Fassung erscheint nach der naechsten Anmeldung - und
    zwar, weil hier eine Marke liegt, die src/bin/zepos-session liest."""
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0
    assert update.marker_path().is_file()

    state = update.read_state()
    assert state["result"] == update.Outcome.OK
    assert [entry["name"] for entry in state["upgraded"]] == [
        "zepos-config", "aylurs-gtk-shell"]


def test_a_run_that_changed_nothing_leaves_no_mark(update, monkeypatch):
    """Sonst erzeugt jede Anmeldung alles neu, taeglich, fuer nichts -
    und das kostet den Nutzer 30 Sekunden schwarzen Bildschirm."""
    machine = Machine(upgradable="", members=MEMBERS)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0
    assert not update.marker_path().exists()


# --------------------------------------------------------------------
# SigLevel = Required, und was ein Fehlschlag sagen muss
# --------------------------------------------------------------------

def test_a_repository_it_cannot_verify_fails_loudly(update, monkeypatch):
    """Ein Update aus einem Repository ohne gueltige Unterschrift muss
    fehlschlagen und das SAGEN.

    Der Wortlaut ist pacmans eigener und wird nicht durchsucht: ein
    installiertes ZepOS ist ein deutsches System, pacman ist uebersetzt,
    und ein `grep signature` gegen die Ausgabe eines uebersetzten
    Programms schlaegt nur auf der Maschine des Entwicklers an. Gemessen
    wird der Rueckgabewert; berichtet wird der Wortlaut.
    """
    refused = ("Fehler: zepos: Signatur von \"ZepOS\" ist unbekannt\n"
               "Fehler: Datenbank 'zepos' konnte nicht aktualisiert werden\n")
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS,
                      sessions=SESSION,
                      codes={"pacman -Sy": 1},
                      output={"pacman -Sy": refused})
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 1

    state = update.read_state()
    assert state["result"] == update.Outcome.FAILED
    assert state["returncode"] == 1
    assert "unbekannt" in state["message"]
    assert not update.marker_path().exists(), (
        "ein gescheiterter Lauf laesst die naechste Anmeldung alles neu "
        "erzeugen, obwohl sich nichts geaendert hat")

    notified = [c for c in machine.commands if "notify-send" in c]
    assert notified, "der Fehlschlag wurde niemandem gesagt"
    assert "--urgency=critical" in notified[0]


def test_a_failure_before_anything_was_installed_installs_nothing(
        update, monkeypatch):
    """Nach einem gescheiterten `-Sy` ist die Datenbank in einem Zustand,
    ueber den nichts bekannt ist. Ein `pacman -S` darauf waere eine
    Installation aus einer Datenbank, die gerade abgelehnt wurde."""
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS,
                      codes={"pacman -Sy": 1})
    outcome = update.perform(update.defaults(), runner=machine)

    assert outcome.failed
    assert [c for c in machine.commands if c[0] == "pacman"] == \
        [["pacman", "-Sy", "--noconfirm"]]


# --------------------------------------------------------------------
# Die Einstellungsschiene: zepos-settings set update.*
# --------------------------------------------------------------------

def test_the_settings_command_writes_the_machine_file_and_applies_it(
        cli, update, monkeypatch, capsys):
    """Der Weg, den ein Nutzer geht, von einem Ende zum anderen.

    Ohne den Aufruf von apply() waere `zepos-settings set update.enabled
    false` ein Wert in einem JSON: der Befehl meldete Erfolg, und die
    Maschine aktualisierte sich am naechsten Morgen weiter.
    """
    machine = Machine()
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert cli.settings_command(["set", "update.enabled", "false"]) == 0

    written = json.loads(update.config_path().read_text(encoding="utf-8"))
    assert written["enabled"] is False
    assert _code(update.dropin_path().read_text(encoding="utf-8"))[0] == \
        "[Timer]"
    assert ["systemctl", "disable", update.TIMER_UNIT] in machine.commands

    assert cli.settings_command(["get", "update.enabled"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "false"


def test_the_settings_command_makes_the_schedule_take_effect(
        cli, update, monkeypatch):
    """Dieselbe Kette fuer "wann": Datei, Ergaenzung, daemon-reload."""
    machine = Machine()
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert cli.settings_command(
        ["set", "update.schedule.on_boot", "2min"]) == 0

    assert "OnBootSec=2min" in _code(
        update.dropin_path().read_text(encoding="utf-8"))
    assert ["systemctl", "daemon-reload"] in machine.commands


def test_a_mistyped_update_setting_is_refused_rather_than_created(cli, update,
                                                                 capsys):
    """Eine Einstellung, die niemand liest, ist die leiseste Art, eine
    Maschine nicht zu aktualisieren."""
    assert cli.settings_command(["set", "update.enabeld", "false"]) == 1
    assert not update.config_path().exists()
    assert "update.enabeld" in capsys.readouterr().err


def test_an_update_setting_never_lands_in_the_user_document(cli, update,
                                                            monkeypatch,
                                                            tmp_path):
    """Der Dienst laeuft als root, moeglicherweise bevor sich jemand
    angemeldet hat. Eine Einstellung in einem Heimatverzeichnis waere
    fuer ihn nicht auffindbar, nicht lesbar und auf einer Maschine mit
    zwei Konten zweideutig."""
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "home-zepos"))
    machine = Machine()
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert cli.settings_command(["set", "update.scope", "all"]) == 0

    import settings

    assert not (tmp_path / "home-zepos" / settings.FILENAME).exists(), (
        "die Einstellung ist im Dokument dieses Kontos gelandet, wo der "
        "Systemdienst sie nicht findet")
    assert "update" not in settings.load()
    assert json.loads(update.config_path().read_text("utf-8"))["scope"] == "all"


def test_a_value_the_machine_cannot_use_never_reaches_the_file(cli, update,
                                                               capsys):
    """Geprueft wird vor dem Schreiben. Eine Datei mit einem Wert, den
    systemd nicht liest, waere ein Zeitgeber, den es nicht mehr gibt."""
    assert cli.settings_command(["set", "update.scope", "vielleicht"]) == 1
    assert not update.config_path().exists()
    assert "update.scope" in capsys.readouterr().err


def test_settings_that_are_not_updates_still_go_to_the_user_document(
        cli, update, monkeypatch, tmp_path):
    """Die Umleitung darf genau einen Praefix treffen und keinen zweiten
    Buchstaben mehr."""
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path / "home-zepos"))
    assert cli.settings_command(["set", "weather.location", "Kiel"]) == 0

    import settings

    assert settings.load()["weather"]["location"] == "Kiel"
    assert not update.config_path().exists()


# --------------------------------------------------------------------
# Was zepos-doctor daraus macht
# --------------------------------------------------------------------

def test_the_doctor_reports_a_failed_update(doctor, update):
    """Ein Fehlschlag, den niemand gesehen hat, weil er nachts passiert
    ist."""
    findings = doctor.check_update(
        update.defaults(),
        {"result": update.Outcome.FAILED, "returncode": 1,
         "finished": "2026-08-11T02:15:00Z",
         "message": "Fehler: Signatur ist unbekannt"},
        "enabled")

    assert len(findings) == 1
    assert "gescheitert" in findings[0].what
    assert findings[0].costs.strip() and findings[0].fix.strip()


def test_the_doctor_reports_a_timer_that_is_off_while_the_setting_is_on(
        doctor, update):
    """Der leiseste Fehler von allen: eine Maschine, die sich seit Wochen
    nichts holt, sieht genauso aus wie eine, die auf dem Stand ist."""
    findings = doctor.check_update(update.defaults(), None, "disabled")

    assert len(findings) == 1
    assert update.TIMER_UNIT in findings[0].what
    assert "zepos-update --apply" in findings[0].fix


def test_the_doctor_is_quiet_about_a_machine_that_is_simply_new(doctor,
                                                                update):
    """Kein Lauf verzeichnet, Zeitgeber an: das ist jede Maschine an
    ihrem ersten Tag. Ein Doktor, der eine frische Installation
    anmeckert, ist einer, den man nicht mehr ernst nimmt."""
    assert doctor.check_update(update.defaults(), None, "enabled") == []


def test_the_doctor_says_when_the_settings_themselves_are_broken(doctor,
                                                                 update):
    """Der Dienst liest dieselbe Datei und tut dann gar nichts."""
    findings = doctor.check_update(None, None, "enabled")
    assert len(findings) == 1
    assert str(update.config_path()) in findings[0].what


def test_the_doctor_asks_systemd_with_a_command_that_changes_nothing(doctor):
    """Der Doktor aendert nichts und braucht keine Rechte - das steht in
    seinem Kopf, und diese Zeile haelt es fest. `is-enabled` liest."""
    assert doctor.TIMER_STATE_COMMAND[:2] == ("systemctl", "is-enabled")
    assert "sudo" not in " ".join(doctor.TIMER_STATE_COMMAND)


def test_the_status_line_says_when_and_what(update):
    """"Wann war das letzte Update, was ist passiert" - in einem Satz."""
    assert "noch nie" in update.describe(None)

    text = update.describe({
        "result": update.Outcome.OK, "finished": "2026-08-11T03:00:00Z",
        "upgraded": [{"name": "zepos-config", "from": "0.1.0-1",
                      "to": "0.1.1-1"}],
        "base_available": [{"name": "linux", "from": "1", "to": "2"}]})
    assert "2026-08-11T03:00:00Z" in text
    assert "zepos-config 0.1.0-1 -> 0.1.1-1" in text
    assert "1 Arch-Aktualisierungen" in text


# --------------------------------------------------------------------
# Die Datei selbst
# --------------------------------------------------------------------

def test_a_settings_file_that_cannot_be_read_stops_the_run(update):
    """Nicht stillschweigend durch die Vorgaben ersetzen: sonst
    aktualisiert sich eine Maschine, auf der jemand `enabled: false`
    schreiben wollte und sich vertippt hat, weiter, als haette er nichts
    gesagt."""
    update.config_path().parent.mkdir(parents=True, exist_ok=True)
    update.config_path().write_text("{kaputt", encoding="utf-8")

    with pytest.raises(update.UnusableConfig):
        update.load()
    assert update.main([]) == 1


def test_the_file_is_readable_by_everyone_and_written_atomically(update):
    """0644 und nicht 0600 wie user-settings.json: hier steht kein
    Geheimnis, und wer nachsehen will, ob seine Maschine sich
    aktualisiert, soll das ohne root koennen."""
    path = update.save(update.defaults())
    assert oct(path.stat().st_mode & 0o777) == "0o644"
    assert json.loads(path.read_text("utf-8"))["schema_version"] == 1


def test_an_older_settings_file_keeps_working(update):
    """Eine Datei aus einer Fassung, die einen Schluessel noch nicht
    kannte, darf nicht dazu fuehren, dass der Dienst ihn vermisst."""
    update.config_path().parent.mkdir(parents=True, exist_ok=True)
    update.config_path().write_text(
        json.dumps({"schema_version": 1, "enabled": False}), encoding="utf-8")

    config = update.load()
    assert config["enabled"] is False
    assert config["scope"] == update.SCOPE_ZEPOS
    assert config["schedule"]["on_boot"] == "15min"


def test_the_repository_is_the_one_the_installer_wrote_into_pacman_conf(
        update):
    """Der Name steht an zwei Stellen, weil das installierte System den
    Installer nicht mitbringt (Spec 4.2). Eine Umbenennung faellt hier
    auf und nicht auf der Maschine eines Nutzers, deren Aktualisierer
    plaetzlich kein einziges Paket mehr fuer "unseres" haelt."""
    from installer.core.source import REPO_NAME

    assert update.REPOSITORY == REPO_NAME
    assert update.repository_command() == ["pacman", "-Slq", REPO_NAME]


# --------------------------------------------------------------------
# Der Befehl, wie ihn ein Mensch startet
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_the_command_starts_and_says_what_it_would_do(tmp_path):
    """/usr/bin/zepos-update mit den Modulen anderswo - dieselbe Frage
    wie fuer die anderen vier Befehle, und nur zu beantworten, indem man
    ihn startet."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    interpreter = stubs / "python3"
    interpreter.write_text(f'#!/bin/bash\nexec "{sys.executable}" "$@"\n',
                           encoding="utf-8")
    interpreter.chmod(0o755)

    environment = {
        "PATH": str(stubs),
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "home" / ".config"),
        "ZEPOS_MACHINE_ROOT": str(tmp_path / "etc-zepos"),
        "ZEPOS_STATE_ROOT": str(tmp_path / "var-lib-zepos"),
        "ZEPOS_SYSTEMD_ETC": str(tmp_path / "etc"),
    }
    result = subprocess.run(
        ["/usr/bin/env", "-i", *(f"{k}={v}" for k, v in environment.items()),
         str(BIN / "zepos-update"), "--status"],
        env={}, input="", capture_output=True, text=True, timeout=60)

    conftest.assert_no_missing_command(result, "zepos-update")
    assert result.returncode == 0, result.stderr
    assert "noch nie" in result.stdout
    # Ein --status darf die Maschine nicht anfassen. Waere es anders,
    # laege hier jetzt eine Zustandsdatei.
    assert not (tmp_path / "var-lib-zepos").exists()
