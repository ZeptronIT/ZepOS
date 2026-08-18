# SPDX-License-Identifier: GPL-3.0-or-later
"""Die zwei Messungen vor der Loeschung.

Der Befund, den sie beantworten, steht im Kopf von
installer/core/preflight.py: ohne Netz hing der Assistent unbegrenzt in
archinstalls Warten auf die Uhr - hinter einer bereits geteilten Platte.
Was hier geprueft wird, ist deshalb nicht "die Funktion gibt etwas
zurueck", sondern die drei Eigenschaften, ohne die dieser Befund
wiederkommt:

    * kein Netz  -> eine Ablehnung, und zwar SCHNELL,
    * ein Netz   -> keine Ablehnung, auch wenn der Spiegel langsam ist,
    * die Uhr    -> eine Frist, die wirklich ablaeuft.
"""
import time
from pathlib import Path

import pytest

from installer.core import preflight
from installer.core.preflight import (
    base_system_problem,
    clock_problem,
    database_url,
    mirror_servers,
)

# Die Zeile, die iso/profile-release/airootfs/usr/local/bin/
# zepos-live-prepare beim Booten wirklich schreibt - hier nicht neu
# erfunden, sondern in der Form, in der printf sie dort ausgibt.
PINNED = "Server = https://archive.archlinux.org/repos/2026/08/01/$repo/os/$arch"


def _mirrorlist(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "mirrorlist"
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------
# Die Spiegelliste lesen
# --------------------------------------------------------------------

def test_the_pinned_snapshot_line_is_found():
    assert mirror_servers(PINNED) == [
        "https://archive.archlinux.org/repos/2026/08/01/$repo/os/$arch"
    ]


def test_commented_out_servers_do_not_count():
    """pacman-mirrorlist liefert eine Datei, in der JEDER Server
    auskommentiert ist. Wer sie als Spiegel liest, haelt ein Medium fuer
    versorgt, das pacstrap beim ersten `pacman -Sy` stehen laesst -
    genau der Grund, aus dem zepos-live-prepare die Liste ueberhaupt
    neu schreibt."""
    text = (
        "## Germany\n"
        "#Server = https://mirror.example.org/$repo/os/$arch\n"
        "#Server = https://zweiter.example.org/$repo/os/$arch\n"
    )
    assert mirror_servers(text) == []


def test_the_order_of_the_file_is_kept():
    text = (
        "Server = https://erster.example.org/$repo/os/$arch\n"
        "Server = https://zweiter.example.org/$repo/os/$arch\n"
    )
    assert mirror_servers(text) == [
        "https://erster.example.org/$repo/os/$arch",
        "https://zweiter.example.org/$repo/os/$arch",
    ]


def test_a_server_line_without_a_value_is_not_a_server():
    assert mirror_servers("Server =\nServer = \n") == []


# --------------------------------------------------------------------
# Die Adresse, die daraus wird
# --------------------------------------------------------------------

def test_the_pacman_variables_are_expanded():
    """`$repo` und `$arch` ersetzt pacman und sonst niemand. Eine
    unersetzte Adresse fragt einen Server nach einem Verzeichnis namens
    `$repo` und bekommt 404 - dieselbe Antwort wie bei einem Spiegel,
    den es nicht gibt. Die zwei duerfen nie verwechselbar sein."""
    assert database_url(
        "https://archive.archlinux.org/repos/2026/08/01/$repo/os/$arch",
        machine="x86_64",
    ) == "https://archive.archlinux.org/repos/2026/08/01/core/os/x86_64/core.db"


def test_no_dollar_sign_survives_the_expansion():
    url = database_url(PINNED.partition("= ")[2], machine="aarch64")
    assert "$" not in url, url
    assert url.endswith("/core/os/aarch64/core.db")


def test_a_trailing_slash_does_not_double():
    assert database_url("https://example.org/$repo/os/$arch/", machine="x86_64") \
        == "https://example.org/core/os/x86_64/core.db"


def test_the_database_asked_for_is_the_one_pacman_asks_for_first():
    """`core` und nicht `extra`: dort liegen base, linux und systemd,
    also das erste, woran eine Installation ohne Netz scheitert."""
    assert preflight.BASE_REPOSITORY == "core"
    url = database_url("https://example.org/$repo/os/$arch", machine="x86_64")
    assert url == "https://example.org/core/os/x86_64/core.db"


# --------------------------------------------------------------------
# Die Ablehnung
# --------------------------------------------------------------------

def test_a_reachable_base_is_no_problem(tmp_path):
    asked = []

    def available(url, **kw):
        asked.append(url)
        return True

    assert base_system_problem(
        mirrorlist=_mirrorlist(tmp_path, PINNED + "\n"),
        available=available, machine="x86_64",
    ) == ""
    assert asked == [
        "https://archive.archlinux.org/repos/2026/08/01/core/os/x86_64/core.db"
    ]


def test_an_unreachable_base_is_refused_and_the_reason_is_readable(tmp_path):
    problem = base_system_problem(
        mirrorlist=_mirrorlist(tmp_path, PINNED + "\n"),
        available=lambda url, **kw: False, machine="x86_64",
    )
    assert problem
    # Die Adresse gehoert in den Satz: sie ist das einzige, woran ein
    # Mensch erkennt, ob sein Rechner am Netz haengt oder ob der Spiegel
    # weg ist.
    assert "archive.archlinux.org" in problem
    # Und ein Rat, der ausfuehrbar ist. Ohne ihn ist die Meldung eine
    # Sackgasse mit Begruendung.
    assert "cable" in problem or "Kabel" in problem


def test_a_mirrorlist_that_does_not_exist_is_refused(tmp_path):
    """Nicht `False` und nicht eine Ausnahme: zepos-live-prepare
    schreibt diese Datei, und wenn sie fehlt, hat es den Schnappschuss
    nicht gefunden. Das ist eine Aussage ueber das Medium und muss vor
    der Loeschung auf dem Bildschirm stehen."""
    problem = base_system_problem(
        mirrorlist=tmp_path / "gibt-es-nicht",
        available=lambda url, **kw: True, machine="x86_64",
    )
    assert problem
    assert "gibt-es-nicht" in problem


def test_a_mirrorlist_with_only_comments_is_refused(tmp_path):
    problem = base_system_problem(
        mirrorlist=_mirrorlist(tmp_path, "## Germany\n#Server = https://x/$repo\n"),
        available=lambda url, **kw: True, machine="x86_64",
    )
    assert problem


def test_only_the_first_server_is_probed(tmp_path):
    """Ein Durchprobieren aller Zeilen macht aus einer Messung von fuenf
    Sekunden eine von unbekannter Dauer - das Gegenteil dessen, wofuer
    diese Pruefung da ist."""
    asked = []

    def available(url, **kw):
        asked.append(url)
        return False

    base_system_problem(
        mirrorlist=_mirrorlist(
            tmp_path,
            "Server = https://erster.example.org/$repo/os/$arch\n"
            "Server = https://zweiter.example.org/$repo/os/$arch\n",
        ),
        available=available, machine="x86_64",
    )
    assert asked == ["https://erster.example.org/core/os/x86_64/core.db"]


def test_the_probe_is_given_a_deadline(tmp_path):
    """Ohne Frist waere die Pruefung gegen das Einfrieren selbst eine
    Stelle, an der es einfriert."""
    seen = {}

    def available(url, **kw):
        seen.update(kw)
        return True

    base_system_problem(
        mirrorlist=_mirrorlist(tmp_path, PINNED + "\n"),
        available=available, machine="x86_64",
    )
    assert seen["timeout"] == preflight.PROBE_TIMEOUT
    assert 0 < preflight.PROBE_TIMEOUT <= 15


# --------------------------------------------------------------------
# Die Uhr
# --------------------------------------------------------------------

def test_a_clock_that_is_already_set_costs_no_sleep(tmp_path):
    """Erst nachsehen, dann schlafen. Wer zuerst schlaeft, kostet jede
    Installation auf einer Maschine mit gestellter Uhr eine Sekunde
    umsonst."""
    marker = tmp_path / "synchronized"
    marker.write_bytes(b"")
    slept = []

    assert clock_problem(marker=marker, sleep=slept.append) == ""
    assert slept == []


def test_the_clock_wait_gives_up_and_says_so(tmp_path):
    """DIE EIGENSCHAFT, UM DIE ES IN DIESER GANZEN DATEI GEHT.

    archinstall 4.4 wartet hier in einem `while True` ohne Frist
    (lib/installer.py:189-202). Diese Pruefung faehrt die Uhr kuenstlich
    ueber die Frist hinaus und verlangt, dass die Schleife ENDET. Ginge
    sie weiter, liefe dieser Test bis zum Zeitablauf von pytest - was
    der ehrlichste denkbare Befund fuer genau diesen Fehler ist.
    """
    ticks = iter([0.0, 10.0, 20.0, 30.0, 40.0])
    slept = []

    problem = clock_problem(
        marker=tmp_path / "nie-da",
        deadline=30.0,
        now=lambda: next(ticks),
        sleep=slept.append,
    )
    assert problem
    assert "30" in problem
    # Und weitergemacht wird trotzdem: eine Maschine mit richtig
    # gehender Echtzeituhr installiert einwandfrei, und ihr das zu
    # verweigern waere ein zweiter Fehler.
    assert "continues" in problem or "weiter" in problem


def test_a_clock_that_arrives_late_is_still_no_problem(tmp_path):
    """Der haeufige Fall: das Netz ist da, timesyncd braucht ein paar
    Sekunden. Das darf keine Warnung geben."""
    marker = tmp_path / "synchronized"
    steps = []

    def sleep(_seconds):
        steps.append(1)
        if len(steps) == 3:
            marker.write_bytes(b"")

    assert clock_problem(marker=marker, sleep=sleep) == ""
    assert len(steps) == 3


def test_the_deadline_is_a_number_a_person_would_wait(tmp_path):
    """Die Frist wird nur erreicht, wenn ein Netz da ist, das HTTPS
    traegt - dann stellt timesyncd die Uhr binnen Sekunden. Wer sie
    ausschoepft, sitzt hinter einer Firewall, die NTP verbietet; fuer
    den ist Weitermachen richtig und langes Warten nur teurer."""
    assert 5 <= preflight.CLOCK_DEADLINE <= 120


def test_the_marker_is_the_file_systemd_actually_writes():
    """Gemessen am 17.08.2026 auf dieser Maschine:

        $ timedatectl show --property=NTPSynchronized --value
        yes
        $ ls -la /run/systemd/timesync/synchronized
        -rw-r--r-- 1 systemd-timesync systemd-timesync 0 17. Aug 09:58

    systemd (src/basic/time-util.c, ntp_synced()) beantwortet die
    D-Bus-Eigenschaft aus genau dieser Datei. Ein Tippfehler im Pfad
    waere eine Uhr, die nie als gestellt gilt - also jede Installation
    um die volle Frist verlangsamt und jede mit einer Warnung versehen,
    die nicht stimmt."""
    assert preflight.CLOCK_MARKER == Path("/run/systemd/timesync/synchronized")


# --------------------------------------------------------------------
# Und der Weg ohne Einspeisung
# --------------------------------------------------------------------

def test_the_defaults_point_at_the_live_medium():
    """Die Voreinstellungen sind die Dateien des laufenden Mediums, und
    keine Erfindung dieses Moduls: zepos-live-prepare schreibt genau
    diese Spiegelliste, und pacstrap liest genau sie."""
    assert preflight.MIRRORLIST == Path("/etc/pacman.d/mirrorlist")


def test_nothing_here_needs_a_subprocess(monkeypatch):
    """installer.core.runner.install() leitet JEDEN Unterprozess durch
    den einen eingespeisten `runner`, damit eine Installation
    vollstaendig ohne echte Prozesse gefahren werden kann. Ein
    `timedatectl` in dieser Datei haette genau das zunichte gemacht -
    und der Waechter in tests/conftest.py haette es als
    IsolationViolation gemeldet, mitten in einer Installation.

    Deshalb hier ausdruecklich: die Uhr wird an einer Datei gemessen.
    """
    source = Path(preflight.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]
    for forbidden in ("subprocess", "timedatectl", "os.system", "Popen"):
        assert forbidden not in body, (
            f"preflight.py ruft {forbidden} auf - damit laesst sich eine "
            f"Installation nicht mehr ohne echte Prozesse fahren")


def test_the_probe_uses_the_one_shared_reachability_check():
    """Eine zweite Fassung von "erreichbar" gaebe frueher oder spaeter
    zwei verschiedene Antworten auf dieselbe Frage. base_system_problem()
    fragt deshalb source.url_reachable() - dieselbe Mechanik, die
    source.repository_available() fuer das [zepos]-Verzeichnis benutzt,
    nur nach einer anderen Datei."""
    from installer.core import source

    called = []
    original = source.url_reachable

    def spy(url, **kw):
        called.append(url)
        return True

    source.url_reachable = spy
    try:
        # Ohne `available` - also ueber den Weg, den eine echte
        # Installation nimmt.
        base_system_problem(
            mirrorlist=Path("/nonexistent-for-this-test"), machine="x86_64")
        assert called == []  # keine Spiegelliste, also gar kein Versuch
    finally:
        source.url_reachable = original


def test_a_real_probe_is_never_started_by_importing_this_module():
    """Ein Modul, das beim Import misst, misst in jedem Test - und in
    jedem Werkzeug, das den Installer nur einliest."""
    started = time.monotonic()
    import importlib
    importlib.reload(preflight)
    assert time.monotonic() - started < 1.0


@pytest.mark.parametrize("machine", ["x86_64", "aarch64"])
def test_the_architecture_comes_from_the_machine_and_not_from_a_guess(machine):
    assert f"/os/{machine}/" in database_url(
        "https://example.org/$repo/os/$arch", machine=machine)
