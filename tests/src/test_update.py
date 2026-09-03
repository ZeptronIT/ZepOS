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
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import conftest

SRC = Path(__file__).resolve().parents[2] / "src"
BIN = SRC / "bin"
REPO = SRC.parent


@pytest.fixture
def update(monkeypatch, tmp_path):
    """Das Modul, mit allen vier Wurzeln in tmp_path.

    Die Umlenkung ist nicht Bequemlichkeit: ohne sie schriebe jeder Test
    nach /etc/zepos, /var/lib/zepos und /etc/systemd/system. Die
    Isolationssperre in tests/conftest.py laesst das nicht zu - und genau
    deshalb ist sie da.

    DIE VIERTE KAM AM 20.08.2026 DAZU
        update.stamp_path() rechnet den Zeitstempel EINES KONTOS aus -
        erst XDG_STATE_HOME, dann dessen Heimatverzeichnis aus der
        Benutzerdatenbank. Ohne die Umlenkung befragte jeder Test, der
        eine uid setzt (_human setzt 1000), das echte
        ~/.local/state/zepos des Entwicklers: gelesen, nicht
        geschrieben, also von der Sperre unbemerkt - und das Ergebnis
        des Tests haenge daran, ob dieser Rechner gerade erzeugt hat.
    """
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.setenv("ZEPOS_MACHINE_ROOT", str(tmp_path / "etc-zepos"))
    monkeypatch.setenv("ZEPOS_STATE_ROOT", str(tmp_path / "var-lib-zepos"))
    monkeypatch.setenv("ZEPOS_SYSTEMD_ETC", str(tmp_path / "etc"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    # DIE FUENFTE KAM AM 03.09.2026 DAZU
    #     replaced_by_repository() liest /var/lib/pacman/sync/zepos.db.
    #     Ohne die Umlenkung befragte jeder Lauf die Datenbank DIESER
    #     Maschine: gelesen, nicht geschrieben, also von der Sperre
    #     unbemerkt - und das Ergebnis haenge daran, ob dieser Rechner
    #     das [zepos]-Repository eingetragen hat. Genau die Klasse
    #     Zusicherung, die gruen ist, weil ein Entwicklerrechner gerade
    #     so aussieht, wie er aussieht.
    monkeypatch.setenv("ZEPOS_PACMAN_SYNC", str(tmp_path / "pacman-sync"))
    import update as module

    return module


def _sync_db(verzeichnis: Path, ersetzt: dict[str, list[str]]) -> Path:
    """Eine Repository-Datenbank, gebaut wie repo-add sie schreibt.

    Ein tar.gz aus `<name>-<fassung>/desc`, und in jeder desc-Datei die
    Abschnitte in der Form `%NAME%`, Zeile, Leerzeile. Gebaut und nicht
    nachgeahmt: derselbe Aufbau, den packaging/out/x86_64/zepos.db
    wirklich hat - nachgesehen am 03.09.2026.
    """
    import tarfile

    verzeichnis.mkdir(parents=True, exist_ok=True)
    pfad = verzeichnis / "zepos.db"
    with tarfile.open(pfad, "w:gz") as archiv:
        for name, namen in ersetzt.items():
            text = f"%NAME%\n{name}\n\n%VERSION%\n1-1\n\n"
            if namen:
                text += "%REPLACES%\n" + "\n".join(namen) + "\n\n"
            rohdaten = text.encode("utf-8")
            eintrag = tarfile.TarInfo(f"{name}-1-1/desc")
            eintrag.size = len(rohdaten)
            import io
            archiv.addfile(eintrag, io.BytesIO(rohdaten))
    return pfad


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


# Die pacman-Aufrufe, die NUR FRAGEN. Ein Test, der prueft, was ein Lauf
# VERAENDERT, laesst sie weg - und er muss sie vollstaendig kennen, sonst
# faellt er, sobald eine neue Frage dazukommt. `-Qq` kam am 03.09.2026
# dazu: der Lauf fragt seither, was installiert ist, um ein ersetztes
# Paket zu finden.
ABFRAGEN = ("-Sy", "-Qu", "-Slq", "-Qq")


class Machine:
    """Ein pacman, ein loginctl und ein systemctl, die nur antworten.

    Sie schreiben mit, was gefragt wurde. Was ein Lauf TUT, ist damit
    genau die Liste, die hier ankommt - und nicht das, was eine Zusage im
    Kopf des Moduls verspricht.
    """

    def __init__(self, *, upgradable: str = "", members: str = "",
                 sessions: str = "[]", codes: dict[str, int] | None = None,
                 output: dict[str, str] | None = None,
                 installed: str = ""):
        self.upgradable = upgradable
        self.members = members
        self.installed = installed
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
        elif argv[:2] == ["pacman", "-Qq"]:
            stdout = self.installed
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
                if c[1] not in ABFRAGEN]
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
    # FUENF UND NICHT EINE ZAHL: die fuenf werden benannt. Eine reine
    # Anzahl faellt bei jeder neuen Frage und sagt dem Nachfolger nicht,
    # welche dazugekommen ist. `-Qq` kam am 03.09.2026 dazu.
    assert [c[1] for c in machine.called("pacman")] == [
        "-Sy", "-Qu", "-Slq", "-Qq", "-S"], machine.called("pacman")


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
# Und was ein Lauf, den ein MENSCH angestossen hat, tun DARF
# (19.08.2026)
# --------------------------------------------------------------------
#
# GEMELDET: "bei einem update --apply wird auch alles generiert und neue
# angezeigt sodass alle update direkt aktiv sind". Bis zu diesem Datum
# wurden beide Faelle behandelt wie der Zeitgeber - der Nutzer musste
# sich nach jeder Aktualisierung neu anmelden, um sie zu sehen.
#
# Die Sperre darueber bleibt Wort fuer Wort stehen. Diese Haelfte misst
# das Gegenstueck: dass der Mensch bekommt, was der Zeitgeber nicht darf.


def _human(monkeypatch, *, terminal: bool = True, uid: str | None = "1000",
           user: str = "zep", root: bool = True) -> None:
    """Die drei Merkmale aus caller() setzen, einzeln abschaltbar.

    _at_a_terminal und _euid sind in update.py eigene Funktionen, damit
    genau das hier geht, ohne sys oder os zu verbiegen - dieselbe Naht
    wie runner= ueberall sonst in diesem Modul.
    """
    import update as module

    monkeypatch.setattr(module, "_at_a_terminal", lambda: terminal)
    monkeypatch.setattr(module, "_euid", lambda: 0 if root else 1000)
    monkeypatch.delenv("SUDO_UID", raising=False)
    monkeypatch.delenv("PKEXEC_UID", raising=False)
    monkeypatch.delenv("SUDO_USER", raising=False)
    if uid is not None:
        monkeypatch.setenv("SUDO_UID", uid)
        monkeypatch.setenv("SUDO_USER", user)


def _forbidden_hits(update, commands: list[list[str]]) -> list[tuple]:
    """Jedes Wort in jedem Argument gegen FORBIDDEN_PROGRAMS.

    WORTWEISE UND NICHT ARGUMENTWEISE, und das ist der Unterschied zu der
    Pruefung weiter oben: die Vordergrund-Erzeugung reicht ein ganzes
    Skript als EIN Argument an `bash -c`, und "zepos-generate --all"
    steht darin mitten in einer Zeile. Eine Pruefung, die nur ganze
    Argumente vergleicht, saehe davon nichts - und genau das waere die
    Luecke, durch die die Erzeugung in den unbeaufsichtigten Lauf
    zurueckkaeme, ohne dass ein Test es merkt.
    """
    hits = []
    for command in commands:
        for part in command:
            for word in re.split(r"[\s;|&()]+", part):
                if word and Path(word).name in update.FORBIDDEN_PROGRAMS:
                    hits.append((word, command))
    return hits


def test_the_whole_unattended_command_still_calls_nothing_forbidden(
        update, monkeypatch):
    """Dieselbe Messung wie oben, aber am ganzen main() und wortweise.

    Der Test darueber misst perform() und announce(). Seit es daneben
    einen Weg gibt, der erzeugen DARF, muss auch der Weg gemessen werden,
    auf dem main() sich zwischen beiden entscheidet - sonst bewiese die
    Sperre nur noch etwas ueber zwei Funktionen und nichts mehr ueber den
    Befehl, den der Zeitgeber wirklich startet.
    """
    _human(monkeypatch, terminal=False, uid=None)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    assert _forbidden_hits(update, machine.commands) == []
    assert machine.called("runuser") == []
    # Und die Marke liegt, wie eh und je: der Zeitgeberweg ist derselbe.
    assert update.marker_path().is_file()


def test_a_run_a_human_started_in_his_own_session_regenerates_at_once(
        update, monkeypatch, capsys):
    """Die neue Haelfte, an den wirklich abgesetzten Befehlen gemessen.

    Ohne diesen Test waere die Aenderung eine Behauptung: dass die
    Sperre nicht mehr greift, ist an ihrem eigenen Test nicht zu sehen -
    der bliebe auch dann gruen, wenn hier gar nichts erzeugt wuerde.
    """
    _human(monkeypatch)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    assert machine.called("runuser") == [[
        "runuser", "-u", "zep", "--", "bash", "-c", update.REGENERATE_SCRIPT]]
    assert "zepos-generate --all" in update.REGENERATE_SCRIPT

    text = capsys.readouterr().out
    assert "zepos-config 0.1.0-1 -> 0.1.1-1" in text
    assert "Neu erzeugt" in text
    # Und der eine Satz, der nicht "fertig" sagt: Hyprland selbst hat
    # der Generator nicht neu geladen, und Plugins liest es nur beim
    # Start (src/plugins.py).
    assert "hyprctl reload" in text
    assert "Anmeldung" in text


@pytest.mark.parametrize("fehlt,merkmale", [
    ("kein Terminal", {"terminal": False}),
    ("kein Konto", {"uid": None}),
])
def test_a_missing_signal_alone_falls_back_to_the_marker(update, monkeypatch,
                                                         fehlt, merkmale):
    """Drei Merkmale mit UND, und das UND wird gemessen.

    Die Kostenverteilung steht im Kopf von src/update.py: eine falsch
    NICHT erkannte Sitzung kostet eine Neuanmeldung, eine falsch ERKANNTE
    reisst dem Nutzer die Leiste weg. Also faellt jedes einzelne fehlende
    Merkmal auf den Zeitgeberweg zurueck.
    """
    _human(monkeypatch, **merkmale)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    assert machine.called("runuser") == [], fehlt
    assert _forbidden_hits(update, machine.commands) == [], fehlt
    assert update.marker_path().is_file()


def test_a_human_without_a_graphical_session_gets_the_marker(update,
                                                             monkeypatch,
                                                             capsys):
    """Das dritte Merkmal, und es braucht eine eigene Maschine.

    root ueber SSH hat ein Terminal und ein SUDO_UID und trotzdem keinen
    Schreibtisch, den ein Neuerzeugen erreichen wuerde: `ags quit` ginge
    ins Leere, und der Zeitstempel dieses Kontos stuende danach auf
    "erzeugt", ohne dass etwas erzeugt worden waere.
    """
    _human(monkeypatch)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions="[]")
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    assert machine.called("runuser") == []
    text = capsys.readouterr().out
    assert "keine grafische Sitzung" in text
    assert "naechsten Anmeldung" in text


def test_the_explicit_switches_beat_the_detection_in_both_directions(
        update, monkeypatch):
    """--regenerate und --no-regenerate, und warum beide noetig sind.

    --no-regenerate, weil ein Mensch am Terminal sonst keinen Weg haette,
    die halbe Minute Generatorlauf zu vermeiden. --regenerate, weil eine
    Oberflaeche, die den Lauf ohne Terminal startet, sonst keinen haette,
    ihn zu bekommen.
    """
    _human(monkeypatch)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)
    assert update.main(["--no-regenerate"]) == 0
    assert machine.called("runuser") == []

    _human(monkeypatch, terminal=False)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions="[]")
    monkeypatch.setattr(update.subprocess, "run", machine)
    assert update.main(["--now", "--regenerate"]) == 0
    assert len(machine.called("runuser")) == 1


def test_even_a_forced_run_refuses_to_guess_whose_desktop_it_is(update,
                                                                monkeypatch):
    """--regenerate ueberstimmt Terminal und Sitzung, NICHT das Konto.

    Ein root ohne SUDO_UID weiss nicht, in wessen ~/.config es erzeugen
    soll. Sich den Benutzer aus loginctl auszusuchen, waere auf einer
    Maschine mit zwei Anmeldungen genau der Fehler vom 11.08.2026, nur
    mit einer anderen uid.
    """
    _human(monkeypatch, uid=None)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main(["--regenerate"]) == 0
    assert machine.called("runuser") == []


def test_the_foreground_run_dates_this_account_and_leaves_the_marker(
        update, monkeypatch):
    """Sonst erzeugt die naechste Anmeldung ein zweites Mal.

    src/bin/zepos-session vergleicht die Marke unter /var/lib mit
    ~/.local/state/zepos/generated-at DIESES Kontos. Der Vordergrundlauf
    setzt deshalb den Zeitstempel und laesst die Marke stehen: sie gehoert
    der Maschine, und ein zweites Konto auf derselben Maschine braucht
    sein eigenes Neuerzeugen noch.

    Und er setzt ihn NUR nach einem Erfolg - ein gescheiterter Generator
    hat nichts erzeugt, und ein Zeitstempel darueber entwertete die Marke.
    """
    _human(monkeypatch)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0
    assert update.marker_path().is_file()

    skript = update.REGENERATE_SCRIPT
    assert 'generated-at' in skript
    assert 'rc" -eq 0' in skript
    # Dieselbe Aufloesung wie in src/bin/zepos-session, Zeile fuer Zeile:
    # ein zweiter Ort fuer denselben Pfad waere ein Pfad, der auseinander
    # laeuft.
    assert '${XDG_STATE_HOME:-$HOME/.local/state}/zepos' in skript
    # Und die Bitte der Einstellungs-Anwendung ist mit demselben Lauf
    # erfuellt (paths.SESSION_REGENERATE_MARKER).
    assert 'rm -f "$zustand/regenerate-required"' in skript


def test_a_failed_regeneration_says_so_instead_of_saying_done(update,
                                                              monkeypatch,
                                                              capsys):
    """Was gedruckt wird, muss wahr sein - auch, wenn es unbequem ist."""
    _human(monkeypatch)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION,
                      codes={"runuser": 3})
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    text = capsys.readouterr().out
    assert "gescheitert (rc=3)" in text
    assert "Neu erzeugt" not in text


def test_the_notification_after_a_foreground_run_promises_no_new_login(
        update):
    """Der Satz "erscheint nach der naechsten Anmeldung" ist im
    Vordergrundfall schlicht falsch - die Schale, die diese Nachricht
    anzeigt, ist gerade deswegen neu gestartet worden."""
    outcome = update.Outcome(
        result=update.Outcome.OK,
        upgraded=(update.Change("zepos-config", "0.1.0-1", "0.1.1-1"),),
        sessions=(update.Session(1000, "zep", "seat0"),))

    davor = update.notification(outcome, update.defaults())
    danach = update.notification(outcome, update.defaults(), regenerated=True)

    assert "naechsten Anmeldung" in davor.body
    assert "naechsten Anmeldung" not in danach.body
    assert "neu erzeugt" in danach.body


def test_the_dry_run_says_what_a_real_one_would_do_in_the_subjunctive(
        update, monkeypatch, capsys):
    """--check ist der Probelauf. Ob danach erzeugt wuerde, war bis heute
    die eine Frage, die man nur durch Ausfuehren beantworten konnte - und
    Ausfuehren ist genau das, was ein --check vermeidet."""
    _human(monkeypatch)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main(["--check"]) == 0

    text = capsys.readouterr().out
    assert "wuerde" in text
    assert "Neu erzeugt" not in text
    assert machine.called("runuser") == []
    assert not update.marker_path().exists()


# --------------------------------------------------------------------
# Die Sackgasse: eine Marke, die liegen bleibt (20.08.2026)
# --------------------------------------------------------------------
#
# GEMELDET, zum dritten Mal: "aktualsiert sich das ui mit generate all
# immernoch nicht nach zepos update warum ?"
#
# Der Weg hinein, aus der Sitzung mit dem Nutzer:
#
#   1. `sudo zepos-update` holt 0.1.3 - dabei lief noch das Programm aus
#      0.1.2: Marke gesetzt, nichts erzeugt. Richtig so.
#   2. jeder weitere Lauf sagt "nothing", `changed` ist falsch, und der
#      ganze Block wurde uebersprungen - samt caller(), also auch samt
#      --regenerate.
#   3. Die Marke bleibt liegen, die Oberflaeche bleibt alt, beliebig oft
#      wiederholbar. Kein Ausgang hat es je erwaehnt.
#
# Ohne die Tests hier kommt genau das wieder: die Sperre oben bleibt
# gruen, egal ob eine ausstehende Marke je etwas ausloest.


def _marke_von_frueher(update):
    """Was ein frueherer Lauf ohne Terminal hinterlassen hat.

    Eine Marke der MASCHINE und kein Zeitstempel des Kontos daneben -
    genau der Zustand nach Schritt 1.
    """
    marker = update.mark_regeneration()
    assert not update.stamp_path(1000).exists()
    return marker


def _dieses_konto_hat_erzeugt(update):
    """Und der Gegenzustand: das Konto hat nach der Marke erzeugt.

    Der Zeitstempel wird ausdruecklich in die Zukunft datiert und nicht
    nur angelegt: mark_regeneration() und dieser Aufruf liegen in
    derselben Millisekunde, und `-nt` vergleicht Zeiten, nicht
    Reihenfolgen.
    """
    stamp = update.stamp_path(1000)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("", encoding="utf-8")
    spaeter = update.marker_path().stat().st_mtime + 10
    os.utime(stamp, (spaeter, spaeter))
    return stamp


def test_a_pending_mark_regenerates_even_though_nothing_was_installed(
        update, monkeypatch, capsys):
    """Der Fehler selbst, als Messung.

    Nichts einzuspielen, eine Marke von frueher, ein Mensch am Terminal:
    bis heute ist hier gar nichts passiert, weil die Neuerzeugung an
    `outcome.changed` hing. Sie haengt jetzt daran, ob eine aussteht.
    """
    _human(monkeypatch)
    _marke_von_frueher(update)
    machine = Machine(upgradable="", members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    assert machine.called("runuser") == [[
        "runuser", "-u", "zep", "--", "bash", "-c", update.REGENERATE_SCRIPT]]
    text = capsys.readouterr().out
    assert "zepos-update: nothing" in text
    assert "Neu erzeugt" in text


def test_the_same_pending_mark_without_a_terminal_regenerates_nothing(
        update, monkeypatch):
    """Die andere Haelfte, und sie ist die teurere.

    Der Zeitgeber trifft dieselbe Marke bei jedem taeglichen Lauf. Er
    darf davon nichts anfassen - ein Generatorlauf im Hintergrund
    beendet Waybar und AGS mitten in der Sitzung (11.08.2026). Die Marke
    aendert an dieser Sperre nichts.
    """
    _human(monkeypatch, terminal=False, uid=None)
    _marke_von_frueher(update)
    machine = Machine(upgradable="", members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    assert machine.called("runuser") == []
    assert _forbidden_hits(update, machine.commands) == []


def test_a_mark_this_account_has_already_answered_regenerates_nothing(
        update, monkeypatch):
    """WORAN "steht aus" haengt, und woran ausdruecklich nicht.

    Nicht an der Marke allein: die gilt der Maschine, gehoert root und
    wird ABSICHTLICH nie geloescht - ein zweites Konto braucht sein
    eigenes Neuerzeugen noch. Wer nur `marker_path().exists()` fragte,
    haette eine Maschine, die von der ersten Aktualisierung an bei JEDEM
    Lauf 30 Sekunden lang alles neu erzeugt, fuer immer.
    """
    _human(monkeypatch)
    _marke_von_frueher(update)
    _dieses_konto_hat_erzeugt(update)
    machine = Machine(upgradable="", members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    assert update.marker_path().is_file()
    assert machine.called("runuser") == []


def test_the_rule_for_pending_is_the_one_the_login_already_applies(update):
    """Keine zweite Antwort auf dieselbe Frage.

    src/bin/zepos-session entscheidet bei jeder Anmeldung, ob neu
    erzeugt wird, und tut es mit bashs `-nt` ueber genau diese zwei
    Dateien. regeneration_pending() rechnet dasselbe in Python. Waeren es
    zwei Regeln, koennte eine Anmeldung erzeugen, wo der Aktualisierer
    schweigt - und der Nutzer haette wieder einen Unterschied, den
    niemand erraten kann. Ein Bash-Skript kann kein Python importieren,
    also wird es hier gegeneinander gehalten.
    """
    sitzung = (BIN / "zepos-session").read_text(encoding="utf-8")

    assert f'UPDATE_MARKER="$ZEPOS_STATE_ROOT/{update.REGENERATE_MARKER}"' \
        in sitzung
    assert ('GENERATED_STAMP="${XDG_STATE_HOME:-$HOME/.local/state}/zepos/'
            f'{update.GENERATED_STAMP}"') in sitzung
    assert '"$UPDATE_MARKER" -nt "$GENERATED_STAMP"' in sitzung

    # Und dieselbe Datei ist es, die REGENERATE_SCRIPT nach einem
    # erfolgreichen Lauf datiert - sonst erzeugte die naechste Anmeldung
    # ein zweites Mal.
    assert f'"$zustand/{update.GENERATED_STAMP}"' in update.REGENERATE_SCRIPT


@pytest.mark.parametrize("lage,marke,stempel,erwartet", [
    ("nichts liegt", False, False, False),
    ("Marke, nie erzeugt", True, False, True),
    ("Marke, danach erzeugt", True, True, False),
])
def test_pending_is_the_comparison_and_not_the_mere_marker(
        update, lage, marke, stempel, erwartet):
    """Dieselben drei Faelle direkt an der Funktion, ohne main() dazwischen."""
    invocation = update.Invocation(True, 1000, "zep", True, "")
    if marke:
        _marke_von_frueher(update)
    if stempel:
        _dieses_konto_hat_erzeugt(update)

    assert update.regeneration_pending(invocation) is erwartet, lage


def test_a_run_that_belongs_to_no_account_answers_nothing_at_all(update):
    """Ohne Konto gibt es den Vergleich nicht - und ohne Konto wird
    ohnehin nicht erzeugt (caller()). "Die Marke liegt" auszugeben, waere
    genau die Aussage ueber die MASCHINE, die diese Sackgasse gebaut hat.
    """
    _marke_von_frueher(update)
    invocation = update.Invocation(False, None, "", True, "")

    assert update.stamp_path(None) is None
    assert update.regeneration_pending(invocation) is False


def test_the_switch_forces_a_run_that_has_nothing_to_do_at_all(
        update, monkeypatch, capsys):
    """--regenerate ohne alles: nichts eingespielt, nichts ausstehend.

    Ein ausdruecklicher Schalter, der schweigend nichts tut, ist
    schlimmer als keiner - dann glaubt der Nutzer, es sei versucht
    worden. Bis heute war er wirkungslos, sobald `changed` falsch war:
    caller() wurde INNERHALB dieses Blocks gefragt.
    """
    _human(monkeypatch)
    machine = Machine(upgradable="", members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main(["--regenerate"]) == 0

    assert not update.marker_path().exists()
    assert len(machine.called("runuser")) == 1
    assert "Neu erzeugt" in capsys.readouterr().out


def test_check_names_the_pending_regeneration_and_the_command_for_it(
        update, monkeypatch, capsys):
    """Die Lage, die drei Runden lang unsichtbar war, gehoert in die
    Ausgabe - samt dem Befehl, der sie aufloest."""
    _human(monkeypatch)
    _marke_von_frueher(update)
    machine = Machine(upgradable="", members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main(["--check"]) == 0

    text = capsys.readouterr().out
    assert "Eine Neuerzeugung steht aus" in text
    assert str(update.marker_path()) in text
    assert str(update.stamp_path(1000)) in text
    assert "zepos-update --regenerate" in text
    # Und ein Probelauf bleibt ein Probelauf.
    assert machine.called("runuser") == []


def test_check_says_nothing_about_a_regeneration_that_is_not_pending(
        update, monkeypatch, capsys):
    """Ein Satz, der bei jedem Lauf steht, wird nicht mehr gelesen."""
    _human(monkeypatch)
    machine = Machine(upgradable="", members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main(["--check"]) == 0

    assert "steht aus" not in capsys.readouterr().out


def test_a_finished_regeneration_is_not_reported_as_still_pending(
        update, monkeypatch, capsys):
    """Jede Zeile muss wahr sein, auch die, die gerade unwahr geworden
    ist: nach einem erfolgreichen Lauf steht nichts mehr aus."""
    _human(monkeypatch)
    _marke_von_frueher(update)
    machine = Machine(upgradable="", members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    text = capsys.readouterr().out
    assert "steht aus" not in text
    assert "Neu erzeugt" in text


# --------------------------------------------------------------------
# Was ein Mensch waehrenddessen sieht (20.08.2026)
# --------------------------------------------------------------------
#
# GEMELDET: "ich will eine coole asci animation im terminal sehen statt
# nach zepos-update immer nicht". Die vier Auflagen misst
# tests/src/test_terminal.py an den geschriebenen Zeichen; hier steht
# die Haelfte, die den Aktualisierer betrifft: dass die Ausgabe des
# Generators vollstaendig durchkommt, dass gezaehlt wird, was er selbst
# sagt, und dass ein Lauf ohne Terminal kein einziges Steuerzeichen
# hinterlaesst.


class Generator:
    """Ein `zepos-generate --all`, das nur redet - mit seinen Farben."""

    def __init__(self, lines, code: int = 0):
        self.stdout = iter(line + "\n" for line in lines)
        self._code = code

    def wait(self, timeout=None) -> int:
        return self._code

    def poll(self) -> int:
        return self._code

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None


class Bildschirm:
    """Ein Terminal, das mitschreibt (siehe tests/src/test_terminal.py)."""

    encoding = "utf-8"

    def __init__(self) -> None:
        self.parts: list[str] = []

    def isatty(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self.parts.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    @property
    def text(self) -> str:
        return "".join(self.parts)


GENERATOR_AUSGABE = [
    "\033[1;33m=== Generating ALL configs ===\033[0m",
    "\033[0;32m→ Processing:\033[0m ags-bar",
    "  \033[0;32m✓ Success\033[0m",
    "\033[0;32m→ Processing:\033[0m waybar",
    "  \033[0;31m✗ Failed\033[0m",
    "\033[0;31m✗ Some configs failed!\033[0m",
]


def test_the_generator_is_read_along_and_not_a_word_of_it_is_lost(update):
    """Die zweite Auflage, am Aktualisierer gemessen.

    Die Statuszeile weicht der Ausgabe des Kindes aus, nicht umgekehrt:
    "✗ Failed" ist das Wichtigste, was durch diese Roehre kommt.
    """
    screen = Bildschirm()
    gesehen = []

    def opener(argv, **kwargs):
        gesehen.append((argv, kwargs))
        return Generator(GENERATOR_AUSGABE, code=1)

    code = update._regenerate_live(["runuser", "-u", "zep"], opener, screen)

    assert code == 1
    for zeile in GENERATOR_AUSGABE:
        assert zeile + "\n" in screen.text, zeile
    # Gezaehlt wird, was der Generator selbst sagt, und zwar an seiner
    # einen Zeile "→ Processing:": die zweite Vorlage ist die zweite.
    # NICHT an "✓ Success" - derselbe Schritt endet auch mit "✗ Failed",
    # und eine Zaehlung, die an einem Wortlaut haengt, zaehlt still
    # falsch, sobald dort ein Wort dazukommt.
    assert "1. ags-bar" in screen.text
    assert "2. waybar" in screen.text
    assert screen.text.endswith(update.terminal.SHOW_CURSOR)
    # stderr geht in denselben Strom, sonst stuende eine Fehlermeldung
    # nicht da, wo sie entstanden ist.
    assert gesehen[0][1]["stderr"] is update.subprocess.STDOUT


def test_a_generator_that_cannot_be_started_is_not_a_crash(update):
    """127, dieselbe Zahl wie im stummen Weg - in beiden Faellen ist
    nichts erzeugt worden, und der Aufrufer behandelt beide gleich."""

    def opener(argv, **kwargs):
        raise OSError("runuser gibt es nicht")

    assert update._regenerate_live(["runuser"], opener, Bildschirm()) == 127


def test_a_pipe_that_never_closes_does_not_hang_the_update(update,
                                                           monkeypatch):
    """Der teuerste Ausgang, den es hier gibt, und deshalb gemessen.

    Die Leseschleife endet, wenn die Roehre schliesst - und die
    schliesst erst, wenn JEDER Schreiber sie losgelassen hat, auch ein
    Kind, das der Generator im Hintergrund gestartet hat.
    generate_config.sh haengt seinen beiden ">/dev/null 2>&1" an
    (Abschnitt "Start/restart AGS", nachgesehen am 20.08.2026); verloere
    eines davon diese
    Umleitung, haenge `sudo zepos-update` ohne die Uhr fuer immer - mit
    einem freundlich drehenden Ring, was es schlimmer macht und nicht
    besser.
    """

    class Haengend:
        def __init__(self) -> None:
            self._los = threading.Event()
            self.getoetet = False
            self.stdout = self._zeilen()

        def _zeilen(self):
            yield "→ Processing: ags-bar\n"
            self._los.wait(10)

        def kill(self) -> None:
            self.getoetet = True
            self._los.set()

        def terminate(self) -> None:
            self.kill()

        def wait(self, timeout=None) -> int:
            return -9

        def poll(self):
            return -9 if self.getoetet else None

    kind = Haengend()
    monkeypatch.setattr(update, "GENERATOR_TIMEOUT", 0.2)

    code = update._regenerate_live(["runuser"], lambda argv, **kw: kind,
                                   Bildschirm())

    assert kind.getoetet, "die Uhr hat das Kind nicht abgebrochen"
    assert code == 127


def test_a_whole_run_whose_output_is_not_a_terminal_stays_free_of_them(
        update, monkeypatch, capsys):
    """Die erste Auflage, am ganzen main() gemessen.

    Ein Mensch am Terminal, aber die Ausgabe geht in eine Roehre
    (`sudo zepos-update | tee protokoll`) - genau der Fall, in dem ein
    Protokoll entsteht, das jemand lesen will. Kein einziges
    Steuerzeichen darf hinein.
    """
    _human(monkeypatch)
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS, sessions=SESSION)
    monkeypatch.setattr(update.subprocess, "run", machine)

    assert update.main([]) == 0

    ausgabe = capsys.readouterr()
    assert "\x1b" not in ausgabe.out + ausgabe.err
    assert "\r" not in ausgabe.out + ausgabe.err


# --------------------------------------------------------------------
# --apply heisst nicht, was es zu heissen scheint
# --------------------------------------------------------------------

def test_apply_sets_the_timer_and_tells_a_human_that_it_installed_nothing(
        update, monkeypatch, capsys):
    """GEMELDET am 19.08.2026: der Nutzer hat gefragt, ob er "apply
    versuchen" solle, um Aktualisierungen einzuspielen. Es haette nichts
    getan.

    Der Hinweis geht an den MENSCHEN und nicht an den ALPM-Haken: an dem
    haengt kein Terminal, und eine Zeile Prosa in jeder pacman-
    Transaktion ist Laerm, den niemand bestellt hat.
    """
    machine = Machine()
    monkeypatch.setattr(update.subprocess, "run", machine)

    _human(monkeypatch, terminal=True)
    assert update.main(["--apply"]) == 0
    am_terminal = capsys.readouterr().out
    assert "es wurde nichts eingespielt" in am_terminal
    assert "sudo zepos-update" in am_terminal
    assert "--apply-schedule" in am_terminal

    _human(monkeypatch, terminal=False)
    assert update.main(["--apply"]) == 0
    im_haken = capsys.readouterr().out
    assert "eingespielt" not in im_haken

    # Und der sprechende Name tut dasselbe. Beide schreiben die
    # Ergaenzung; keiner von beiden ruft pacman.
    assert update.dropin_path().is_file()
    _human(monkeypatch, terminal=True)
    assert update.main(["--apply-schedule"]) == 0
    assert "pacman" not in machine.programs


def test_the_help_separates_installing_from_setting_the_timer(update):
    """`usage_text()` ist die Stelle, an der ein Mensch den Unterschied
    heute lesen koennte. Er stand dort - als "systemd auf die
    Einstellungen bringen", was die Frage "spielt das etwas ein?" nicht
    beantwortet."""
    text = update.usage_text()

    assert "--apply-schedule" in text
    assert "--now" in text
    assert "NICHTS" in text
    assert "--regenerate" in text


def test_a_switch_that_cannot_work_is_refused_rather_than_ignored(update):
    """`zepos-update --status --regenerate` waere eine Anweisung, die ins
    Leere geht. Ein Programm, das sie schluckt, laesst den Nutzer glauben,
    sie habe gewirkt."""
    assert update.main(["--status", "--regenerate"]) == 2
    assert update.main(["--apply", "--no-regenerate"]) == 2
    assert update.main(["--check", "--now"]) == 2
    assert update.main(["--unfug"]) == 2


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


# --------------------------------------------------------------------
# Ein Paket, das ein anderes ERSETZT - seit dem 03.09.2026
# --------------------------------------------------------------------
#
# Der Nutzer am 03.09.2026: "wegen claude code kann ich aktuell keine
# update ziehen". Der Grund steht nicht in diesem Baum, sondern in
# PKGBUILD(5), woertlich:
#
#     "Sysupgrade is currently the only pacman operation that utilizes
#     this field. A normal sync or upgrade will not use its value."
#
# Der Bereich "zepos" setzt `pacman -S` ab - kein Sysupgrade. `replaces`
# wird damit nicht gelesen, `conflicts` desselben Pakets schon, und ein
# Konflikt mit `--noconfirm` bricht den GANZEN Vorgang ab. Der Rechner
# bekam also keine Aktualisierung mehr; nicht die von zepos-config,
# sondern gar keine.


def test_a_replaced_package_is_read_from_the_database_and_not_from_prose(
        update, tmp_path):
    """%REPLACES% aus der Datenbank, nicht "Ersetzt :" aus pacmans Ausgabe.

    Der Kopf dieses Moduls verbietet das Durchsuchen von pacmans Prosa,
    weil sie uebersetzt ist. Die Datenbank ist dieselbe Angabe in dem
    Format, das repo-add geschrieben hat.
    """
    verzeichnis = tmp_path / "pacman-sync"
    _sync_db(verzeichnis, {"zepos-config": ["zepos-claude-code"],
                           "zepos-menu": []})

    assert update.replaced_by_repository(verzeichnis) == {"zepos-claude-code"}


def test_a_versioned_replaces_still_names_a_package(update, tmp_path):
    """`replaces=('alt<2.0')` ist erlaubt und nennt trotzdem "alt"."""
    verzeichnis = tmp_path / "pacman-sync"
    _sync_db(verzeichnis, {"zepos-config": ["alt<2.0", "zweit>=1"]})

    assert update.replaced_by_repository(verzeichnis) == {"alt", "zweit"}


def test_a_missing_database_is_no_finding_of_this_run(update, tmp_path):
    """Fehlt sie, faellt `pacman -Sy` vorher - und dieser Lauf hat kein
    zweites Urteil darueber zu faellen."""
    assert update.replaced_by_repository(tmp_path / "gibt-es-nicht") == set()


def test_the_run_removes_what_a_new_package_replaces_before_it_installs(
        update, tmp_path):
    """DER FALL DES NUTZERS, an den Befehlen gemessen.

    Die Reihenfolge ist der ganze Punkt: erst `-Rdd`, dann `-S`. Umkehrt
    scheitert das `-S` am Konflikt, und danach ist nichts mehr zu
    entfernen, weil nichts eingespielt wurde.
    """
    _sync_db(tmp_path / "pacman-sync", {"zepos-config": ["zepos-claude-code"]})
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS,
                      sessions=SESSION,
                      installed="zepos-config\nzepos-claude-code\nlinux\n")

    outcome = update.perform(update.defaults(), runner=machine)

    assert outcome.result == update.Outcome.OK
    assert outcome.replaced == ("zepos-claude-code",)

    veraendernd = [c for c in machine.called("pacman") if c[1] not in ABFRAGEN]
    assert veraendernd == [
        ["pacman", "-Rdd", "--noconfirm", "zepos-claude-code"],
        ["pacman", "-S", "--needed", "--noconfirm",
         "zepos-config", "aylurs-gtk-shell"],
    ], veraendernd


def test_nothing_is_removed_when_the_replaced_package_is_not_installed(
        update, tmp_path):
    """Die Gegenprobe zum Test darueber. Ohne sie sagte er nur, dass der
    Lauf `-Rdd` absetzt - nicht, dass er es aus einem GRUND tut."""
    _sync_db(tmp_path / "pacman-sync", {"zepos-config": ["zepos-claude-code"]})
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS,
                      sessions=SESSION,
                      installed="zepos-config\naylurs-gtk-shell\n")

    outcome = update.perform(update.defaults(), runner=machine)

    assert outcome.replaced == ()
    assert not [c for c in machine.called("pacman") if c[1] == "-Rdd"]


def test_the_full_upgrade_does_not_need_the_extra_step(update, tmp_path):
    """`-Syu` IST das Sysupgrade und liest `replaces` selbst. Ein
    zusaetzliches `-Rdd` waere dort ein Eingriff ohne Anlass."""
    _sync_db(tmp_path / "pacman-sync", {"zepos-config": ["zepos-claude-code"]})
    config = update.defaults()
    config["scope"] = update.SCOPE_ALL
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS,
                      sessions=SESSION,
                      installed="zepos-config\nzepos-claude-code\n")

    outcome = update.perform(config, runner=machine)

    assert outcome.replaced == ()
    assert not [c for c in machine.called("pacman") if c[1] in ("-Rdd", "-Qq")]


def test_a_check_removes_nothing(update, tmp_path):
    """`--check` sagt, was passieren WUERDE. Ein Lauf, der dabei ein
    Paket entfernt, hat die Frage nicht beantwortet, sondern die
    Maschine veraendert."""
    _sync_db(tmp_path / "pacman-sync", {"zepos-config": ["zepos-claude-code"]})
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS,
                      sessions=SESSION,
                      installed="zepos-config\nzepos-claude-code\n")

    outcome = update.perform(update.defaults(), runner=machine, check_only=True)

    assert outcome.result == update.Outcome.PENDING
    assert not [c for c in machine.called("pacman") if c[1] not in ABFRAGEN]


def test_a_removal_that_fails_stops_the_run_instead_of_installing_anyway(
        update, tmp_path):
    """Scheitert das Abraeumen, waere das `-S` danach genau der Abbruch,
    den dieser Schritt verhindern soll - nur mit einer Meldung, die vom
    falschen Befehl kommt."""
    _sync_db(tmp_path / "pacman-sync", {"zepos-config": ["zepos-claude-code"]})
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS,
                      sessions=SESSION,
                      installed="zepos-config\nzepos-claude-code\n",
                      codes={"-Rdd": 1})

    outcome = update.perform(update.defaults(), runner=machine)

    assert outcome.result == update.Outcome.FAILED
    assert outcome.returncode == 1
    assert not [c for c in machine.called("pacman") if c[1] == "-S"]


def test_the_notification_names_what_was_removed(update, tmp_path):
    """Ein Lauf, der etwas abraeumt und nur die Neuzugaenge meldet,
    laesst den Nutzer spaeter raten, wohin ein Befehl verschwunden ist."""
    _sync_db(tmp_path / "pacman-sync", {"zepos-config": ["zepos-claude-code"]})
    machine = Machine(upgradable=UPGRADABLE, members=MEMBERS,
                      sessions=SESSION,
                      installed="zepos-config\nzepos-claude-code\n")

    outcome = update.perform(update.defaults(), runner=machine)
    note = update.notification(outcome, update.defaults())

    assert note is not None
    assert "zepos-claude-code" in note.body
    assert "ersetzt" in note.body.lower()
