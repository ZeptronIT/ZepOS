# SPDX-License-Identifier: GPL-3.0-or-later
"""Was vor dem Loeschen gemessen wird - und warum es diese Datei gibt.

DER BEFUND, 17.08.2026, auf echter Hardware
    "Installation Wizard mit dem Terminal freezed wenn ich versuche ohne
    Internet und ohne Passphrase zu installieren."

    Der Assistent hing. Nicht lange, sondern unbegrenzt: kein Fehler,
    kein Abbruch, ein stehendes Bild.

WO ER HING - GEMESSEN, NICHT VERMUTET
    Nicht in pacman. Das war die naheliegende Vermutung, weil sowohl
    iso/profile-release/airootfs/usr/local/bin/zepos-live-prepare als
    auch installer/core/pacmanconf.py `DisableDownloadTimeout` setzen,
    und weil das nach "wartet ewig" klingt. Gemessen am 17.08.2026 auf
    pacman 7.1.0.r9, zweimal, mit und ohne den Schalter:

        [options] ohne DisableDownloadTimeout, Server 192.0.2.1
            error: ... 'blackhole.db' ... Connection timed out
                   after 10002 milliseconds        -> 10,010 s

        [options] MIT DisableDownloadTimeout, derselbe Server
            error: ... 'blackhole.db' ... Connection timed out
                   after 10002 milliseconds        -> 10,011 s

        MIT DisableDownloadTimeout, gar kein Netz (unshare -rn),
        echter ALA-Spiegel
            error: ... 'core.db' ... Failed to connect to
                   archive.archlinux.org:443 after 23 ms
                                                   -> 0,031 s

    `DisableDownloadTimeout` schaltet also NUR den Durchsatz-Zeitablauf
    ab, nicht den Verbindungs-Zeitablauf. Ohne Netz scheitert pacman in
    einunddreissig Millisekunden. Der Schalter ist unschuldig, und die
    Begruendung, die in zepos-live-prepare dafuer steht, bleibt richtig.

    Gehangen hat archinstall 4.4, in
    archinstall/lib/installer.py:189-202, `_verify_service_stop()`:

        if not skip_ntp:
            info('Waiting for time sync (timedatectl show) to complete.')
            started_wait = time.monotonic()
            notified = False
            while True:
                if not notified and time.monotonic() - started_wait > 5:
                    notified = True
                    warn('Time synchronization not completing, ...')
                time_val = SysCommand('timedatectl show '
                                      '--property=NTPSynchronized '
                                      '--value').decode()
                if time_val and time_val.strip() == 'yes':
                    break
                time.sleep(1)

    `while True` ohne Frist. Ohne Netz wird NTPSynchronized nie `yes`,
    also laeuft diese Schleife bis zum Ausschalten des Rechners. Nach
    fuenf Sekunden schreibt sie EINEN Satz ins Protokoll und danach
    nichts mehr - genau das Bild, das der Nutzer gesehen hat.

    Und sie laeuft an der schlimmstmoeglichen Stelle:
    archinstall/scripts/guided.py ruft erst :249
    `fs_handler.perform_filesystem_operations()` - die Platte ist da
    schon geteilt und formatiert - und dann :251 `perform_installation()`,
    worin :88 `installation.sanity_check(...)` steht. Der Nutzer haengt
    also VOR einer halb beschriebenen Platte, ohne dass ihm jemand sagt,
    dass er sie nicht mehr unversehrt zurueckbekommt.

    Das war uebrigens schon einmal bekannt: der Kopf von
    iso/profile/airootfs/etc/systemd/network/20-ethernet.network nennt
    diese Schleife beim Namen. Die Antwort darauf war, dem Medium DHCP
    zu geben - richtig, aber es beantwortet nur den Fall, in dem ein
    Netz da ist. Fuer den Fall, dass keines da ist, stand nichts.

WAS DIESE DATEI DAGEGEN TUT
    Zwei Messungen, beide VOR der ersten Aenderung an der Platte:

    base_system_problem()   Ist die Arch-Basis erreichbar? Wenn nicht,
                            ist das eine Ablehnung - installer.core.
                            runner.install() macht daraus ein
                            InstallationRefused, und das heisst in
                            installer/gui/pages.py "Auf der Platte
                            wurde nichts geaendert".

    clock_problem()         Ist die Uhr gestellt? Mit Frist. Das ist
                            der Ersatz fuer archinstalls Schleife, die
                            runner.py mit `--skip-ntp` abschaltet: ein
                            Schutz, den man ausschaltet, ohne etwas
                            hinzustellen, ist keine Reparatur. Anders
                            als dort ist das Ergebnis eine WARNUNG und
                            keine Ablehnung - eine Maschine, deren
                            Echtzeituhr richtig geht, installiert
                            einwandfrei, und ihr das zu verweigern
                            waere ein zweiter Fehler.

WARUM DIE UHR AN EINER DATEI GEMESSEN WIRD UND NICHT AN timedatectl
    `timedatectl show --property=NTPSynchronized` fragt systemd-timedated
    ueber D-Bus, und das antwortet aus genau einer Quelle: systemd
    (src/basic/time-util.c, ntp_synced()) prueft, ob
    /run/systemd/timesync/synchronized existiert. Gemessen am
    17.08.2026 auf dieser Maschine:

        $ timedatectl show --property=NTPSynchronized --value
        yes
        $ ls -la /run/systemd/timesync/synchronized
        -rw-r--r-- 1 systemd-timesync systemd-timesync 0 17. Aug 09:58

    Dieselbe Auskunft, ohne Unterprozess. Das ist hier kein Geschmack:
    installer.core.runner.install() leitet JEDEN Unterprozess durch den
    einen eingespeisten `runner`, damit ein Aufrufer eine Installation
    vollstaendig ohne echte Prozesse fahren kann, und ein zweiter,
    versteckter Aufruf haette genau das zunichte gemacht.
"""
from __future__ import annotations

import platform
import time
from pathlib import Path
from typing import Callable

from .i18n import _
from .source import url_reachable

# Die Spiegelliste, die zepos-live-prepare beim Booten schreibt - aus dem
# ALA-Schnappschuss, auf den dieses Medium festgenagelt ist (spec 8.7).
# Genau die Datei liest pacstrap(8) spaeter mit `-C /etc/pacman.conf`,
# also ist sie die richtige und einzige Quelle fuer die Frage "woher
# kaeme die Basis".
MIRRORLIST = Path("/etc/pacman.d/mirrorlist")

# Das erste Paketverzeichnis, das pacman anfasst, und damit das erste,
# an dem eine Installation ohne Netz scheitert. `base`, `linux` und
# `systemd` liegen alle darin.
BASE_REPOSITORY = "core"

# Fuenf Sekunden, dieselben, die source.PROBE_TIMEOUT sich nimmt und aus
# demselben Grund: das hier laeuft einmal, vor einer Installation von
# zwanzig Minuten. Gemessen (siehe Kopf) scheitert der Verbindungsaufbau
# ohne Netz in 31 ms; die fuenf Sekunden sind fuer die Leitung, die
# langsam ist statt tot.
PROBE_TIMEOUT = 5.0

# systemds eigene Marke fuer "die Uhr ist gestellt". Siehe Kopf.
CLOCK_MARKER = Path("/run/systemd/timesync/synchronized")

# Wie lange auf die Uhr gewartet wird, bevor ohne sie weitergemacht wird.
#
# WARUM DREISSIG UND NICHT MEHR
#     Diese Frist wird nur erreicht, wenn base_system_problem() vorher
#     JA gesagt hat - es gibt also ein Netz, das HTTPS traegt. Dann
#     stellt systemd-timesyncd die Uhr binnen weniger Sekunden. Wer die
#     dreissig Sekunden trotzdem ausschoepft, sitzt hinter einer
#     Firewall, die NTP verbietet und HTTPS erlaubt; fuer den ist
#     Weitermachen richtig, und Warten waere nur teurer.
#
# WARUM UEBERHAUPT GEWARTET WIRD
#     Weil die Uhr etwas kostet, wenn sie falsch geht: pacman prueft
#     Signaturen, und gpg lehnt eine Signatur ab, die in der Zukunft
#     ausgestellt wurde. Das ist der Grund, aus dem archinstall
#     ueberhaupt wartet, und der bleibt richtig - falsch war nur, dass
#     es ohne Frist wartete.
CLOCK_DEADLINE = 30.0

# Wie oft nachgesehen wird. Eine Sekunde, wie bei archinstall: die Marke
# erscheint, wenn sie erscheint, und haeufigeres Nachsehen macht sie
# nicht frueher da.
CLOCK_INTERVAL = 1.0


def mirror_servers(text: str) -> list[str]:
    """Jede `Server = ...`-Zeile einer Spiegelliste, in ihrer Reihenfolge.

    Text hinein, Liste heraus, damit die Entscheidung ohne Dateisystem
    geprueft werden kann - und angewandt auf das, was zepos-live-prepare
    wirklich geschrieben hat, statt auf eine Datei, deren Form dieser
    Code selbst angenommen haette.

    Auskommentierte Zeilen zaehlen nicht: pacman-mirrorlist liefert eine
    Datei, in der JEDER Server auskommentiert ist, und sie als Spiegel
    zu lesen hiesse, ein Medium fuer versorgt zu halten, das es nicht
    ist. Genau das steht im Kopf von zepos-live-prepare als der Grund,
    aus dem die Liste ueberhaupt geschrieben wird.
    """
    servers: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if separator and key.strip() == "Server" and value.strip():
            servers.append(value.strip())
    return servers


def database_url(server: str, *, machine: str | None = None) -> str:
    """Die Adresse der Paketdatenbank, die pacman als erstes holt.

    `$repo` und `$arch` sind Variablen der pacman.conf; pacman ersetzt
    sie beim Bauen einer Anfrage, sonst niemand. Wer die Zeile
    unveraendert an urllib gibt, fragt einen Server nach einem
    Verzeichnis, das buchstaeblich `$repo` heisst - und bekommt 404,
    also dieselbe Antwort wie bei einem Spiegel, den es nicht gibt.
    Dieselbe Falle steht in installer/core/source.py bei
    resolve_repo_url(), und sie hat dort schon einmal eine Installation
    gekostet.
    """
    machine = machine or platform.machine()
    expanded = server.replace("$repo", BASE_REPOSITORY).replace("$arch", machine)
    return f"{expanded.rstrip('/')}/{BASE_REPOSITORY}.db"


def base_system_problem(
    *,
    mirrorlist: Path = MIRRORLIST,
    available: Callable[..., bool] | None = None,
    machine: str | None = None,
    timeout: float = PROBE_TIMEOUT,
) -> str:
    """Die Ablehnung, wenn die Arch-Basis nicht erreichbar ist, sonst "".

    WARUM DIESE FRAGE NICHT SCHON source.probe() BEANTWORTET
        Weil probe() eine andere Frage stellt. Ihr Ergebnis, OFFLINE,
        verlegt allein das [zepos]-Verzeichnis auf das Medium
        (source.OFFLINE_REPO_URL); die Arch-Basis - base, linux,
        systemd und die vierzig Abhaengigkeiten von zepos-desktop -
        kommt in BEIDEN Faellen ueber das Netz, aus dem festgenagelten
        ALA-Schnappschuss (spec 8.4). "Offline" heisst in dieser
        Kennung nichts weiter als "unsere eigenen Pakete kommen vom
        Medium", und eine Installation ganz ohne Netz gibt es heute
        nicht.

        probe() darf ausserdem grundsaetzlich nicht ablehnen - sie
        verschluckt jede Ausnahme und faellt auf das Medium zurueck.
        Das ist dort richtig und hier falsch: hier ist die
        Unerreichbarkeit kein Rueckfallweg, sondern das Ende.

    Eine Zeichenkette statt einer Ausnahme, aus demselben Grund wie bei
    firmware.firmware_problem(): eine Maske kann sie neben ihre Felder
    schreiben, und runner.install() macht eine Ablehnung daraus.
    """
    available = available or url_reachable

    try:
        text = mirrorlist.read_text(encoding="utf-8")
    except OSError:
        text = ""

    servers = mirror_servers(text)
    if not servers:
        # Kein Spiegel heisst: zepos-live-prepare hat den Schnappschuss
        # nicht gefunden und sagt das auch (sein `else`-Zweig schreibt
        # nach stderr). Das hier ist dieselbe Tatsache, an der Stelle,
        # an der ein Mensch sie zu sehen bekommt.
        return _(
            "This medium names no package source: {mirrorlist} contains no server. ZepOS fetches the Arch Linux base system from there during every installation, so none can be carried out from this medium."
        ).format(mirrorlist=mirrorlist)

    # Der erste Server und nur der erste: zepos-live-prepare schreibt
    # genau eine Zeile, und wo doch mehrere stuenden, ist die erste die,
    # die pacman zuerst versucht. Ein Durchprobieren aller Zeilen wuerde
    # aus einer Messung von fuenf Sekunden eine von unbekannter Dauer
    # machen - das Gegenteil dessen, wofuer diese Datei da ist.
    server = servers[0]
    if available(database_url(server, machine=machine), timeout=timeout):
        return ""

    return _(
        "The Arch Linux package source cannot be reached: {url}. ZepOS fetches the base system from there during every installation - without a network there is nothing to install from. Connect a network cable, or go back and join a wireless network, and try again."
    ).format(url=database_url(server, machine=machine))


def clock_problem(
    *,
    marker: Path = CLOCK_MARKER,
    deadline: float = CLOCK_DEADLINE,
    interval: float = CLOCK_INTERVAL,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> str:
    """Warte, bis die Uhr gestellt ist - hoechstens `deadline` Sekunden.
    Gibt die Warnung zurueck, wenn sie es nicht wurde, sonst "".

    Der Ersatz fuer archinstalls Schleife ohne Frist (siehe Kopf), und
    absichtlich in derselben Reihenfolge gebaut: erst nachsehen, dann
    schlafen. Wer zuerst schlaeft, kostet jede Installation auf einer
    Maschine mit laengst gestellter Uhr eine Sekunde umsonst.

    `now` und `sleep` sind eingespeist, damit die Frist geprueft werden
    kann, ohne sie abzuwarten - eine Pruefung, die dreissig Sekunden
    dauert, wird abgeschaltet, und dann ist die Frist ungeprueft.
    """
    now = now or time.monotonic
    sleep = sleep or time.sleep

    started = now()
    while True:
        if marker.exists():
            return ""
        if now() - started >= deadline:
            return _(
                "The clock was not set from the network within {seconds} seconds. The installation continues with the time this computer started with. If that time is far wrong, package signatures can be refused and the installation fails at the first package."
            ).format(seconds=int(deadline))
        sleep(interval)
