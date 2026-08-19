# SPDX-License-Identifier: GPL-3.0-or-later
"""Report the configuration problems that otherwise surface as silence.

Every check here answers a failure that was met during development and
produced no error message anywhere: not in a log, not on a status line,
not on the terminal. That is what makes them worth a command of their
own - a failure that announces itself needs no doctor.

  * A VPN that routes the whole private address space. Container and
    virtualisation bridges live in RFC1918; when the tunnel claims all of
    it, their traffic is captured by the tunnel's policies and disappears
    there. Nothing logs it, and there is no subnet left to move the
    bridge into. This is not hypothetical: it is why this project's own
    build containers have to run with --network host.

  * A plugin ABI mismatch. Hyprland refuses a plugin whose ABI hash
    differs from its own, and the desktop is deliberately built to start
    anyway - a mismatch costs a feature, not a session. Which is exactly
    why nothing tells the user their title bars are gone.

  * A message with no entry in the German catalogue. A user who chose
    German reads that one message in English and has no way to tell that
    a translation was supposed to exist.

  * A clock in a timezone this machine's tzdata does not know. `date`
    accepts the name, exits 0 and prints UTC, so the bar module refuses
    to render a time for it - and says so in a TOOLTIP, over one small
    module of one bar, to a user who has to be suspicious enough to
    hover there. A typo in clocks.zones is exactly the case where nobody
    is suspicious, because a clock that is silently hours wrong looks
    like a clock.

  * Eine Selbstaktualisierung, die nicht laeuft. Das ist der leiseste
    Fehler von allen: eine Maschine, die sich seit Wochen nichts mehr
    holt, sieht genauso aus wie eine, die auf dem Stand ist. Drei Formen
    davon werden gemeldet - der Zeitgeber ist aus, obwohl die Einstellung
    an sagt; der letzte Lauf ist gescheitert (an einer Unterschrift zum
    Beispiel, was SigLevel = Required genau so vorsieht); es hat noch nie
    einen gegeben. Was zuletzt war, sagt `zepos-update --status`.

WHAT A FINDING HAS TO SAY
    Three things, which is why Finding has three fields rather than being
    a string: what is wrong, what it costs the user, and what to do about
    it. A diagnostic that only names a condition leaves the user to
    search for the fix themselves, which is barely better than the
    silence it replaced.

WHAT THIS DOES NOT DO
    It changes nothing and it needs no privileges. Every command it runs
    is a read: `ip -j route`, `ip -j addr`, `hyprctl version`. There is
    no sudo anywhere in here, and the test suite asserts it stays that
    way - on this machine a failed sudo locks the account out.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple

import clocks
import settings
import update
import validate_output
from paths import output_root, user_root
from vpn import nonblank_entries

# Where the generated Hyprland configuration ends up, and how a bind line
# is read. Both used to be written out here; they now come from
# src/keybinds.py, because the shortcut overview reads the same files
# through the same parser and a second copy of either would be a second
# answer to "what does this key do" - which is the defect that module
# exists to remove.
from keybinds import (BOUND_CONFIGS, HYPRLAND_CONF, PLUGINS_CONF,
                      bound_commands, command_words)

Runner = Callable[..., "subprocess.CompletedProcess"]

# Re-exported on purpose: zepos-doctor is the command that names a key
# pointing at nothing, and its callers - the test suite among them - ask
# this module for both the file list and the parser.
__all__ = ["BOUND_CONFIGS", "HYPRLAND_CONF", "PLUGINS_CONF",
           "bound_commands", "command_words"]

# The catalogue, as it ships beside the modules. Both places are looked
# at: below the system root is where a package puts it, and one directory
# above is where a checkout keeps it - po/ is a sibling of src/ there.
CATALOGUE_DIRECTORY = "po"
CATALOGUE_TEMPLATE = "zepos-installer.pot"
CATALOGUE = "de.po"

# One entry of a .po file, in the shape both catalogues in this project
# are written in. Multi-line msgids are not matched, and none are used;
# what this misses is an entry nobody would have translated differently.
PO_ENTRY = re.compile(r'^msgid "(.*)"\nmsgstr "(.*)"', re.MULTILINE)

# The libraries Hyprland reports itself built against, beside what is
# installed. `hyprctl version -j` answers with buildAquamarine /
# systemAquamarine and so on for each of them.
ABI_LIBRARIES = ("Aquamarine", "Hyprlang", "Hyprutils", "Hyprcursor",
                 "Hyprgraphics")

# Where glibc looks a timezone up, and the variable that moves it. Both
# spellings are here because the generated clock module reads exactly
# these two - `ZEITZONEN="${TZDIR:-/usr/share/zoneinfo}"` - and a doctor
# looking somewhere else would be answering about a different machine
# than the bar the user is looking at.
ZONEINFO = Path("/usr/share/zoneinfo")
ZONEINFO_VARIABLE = "TZDIR"

# What prints the names this database does have. Named in the finding
# rather than a list of zones: the answer belongs to tzdata, changes with
# it, and is one command away.
ZONE_LISTING = "timedatectl list-timezones"


class Network(NamedTuple):
    """A network, and the interface it was found on.

    `where` is a device name for both routes and bridges, so a route on
    the bridge's own device can be recognised as the bridge's own route.
    It is empty for a network that came from the settings file rather
    than from the running system.
    """

    address: str
    where: str


@dataclass(frozen=True)
class Finding:
    """One problem, in the three parts a user needs to act on it."""

    what: str
    costs: str
    fix: str

    def __str__(self) -> str:
        return f"- {self.what}\n  Costs: {self.costs}\n  Fix:   {self.fix}"


# --------------------------------------------------------------------
# a VPN that swallows the private address space
# --------------------------------------------------------------------

def check_vpn_networks(routed: Iterable[Network], *,
                       bridges: Iterable[Network],
                       bypassed: Iterable[str] = ()) -> list[Finding]:
    """Local bridges that a routed network covers.

    Both lists come from the machine this runs on - see discover_routes()
    and discover_bridges(). A version of this that took its input from
    the caller and was never called by anything would report on nothing
    at all, which is indistinguishable from a healthy machine.
    """
    bridges = list(bridges)
    routed = list(routed)
    excluded = [network for network in
                (_network(value) for value in bypassed) if network]

    findings = []
    for bridge in bridges:
        bridge_network = _network(bridge.address)
        if bridge_network is None:
            continue
        if any(_covers(exclusion, bridge_network) for exclusion in excluded):
            # Already kept out of the tunnel on purpose. Reporting it
            # would tell the user to fix what they have fixed, and a
            # check that cries wolf is one somebody switches off.
            continue

        for route in routed:
            if route.where and route.where == bridge.where:
                # Every bridge has a route to its own network, on itself.
                continue
            route_network = _network(route.address)
            if route_network is None or not _covers(route_network,
                                                    bridge_network):
                continue

            findings.append(Finding(
                what=(f"{route.address} {_source(route)} and covers the local "
                      f"bridge {bridge.where} ({bridge.address})."),
                costs=("containers and virtual machines on that bridge lose "
                       "their network: the tunnel's policies capture their "
                       "traffic and it goes nowhere. Nothing logs it - the "
                       "tools simply stop working."),
                fix=(f"move {bridge.where} into a range the tunnel does not "
                     f"carry, add its network to vpn.bypass_networks in the "
                     f"settings file, or run the containers with "
                     f"--network host."),
            ))
    return findings


def _source(route: Network) -> str:
    return f"is routed via {route.where}" if route.where else (
        "is listed in vpn.routed_networks")


def _network(value: Any) -> ipaddress._BaseNetwork | None:
    """A network object, or None for anything that is not one.

    routed_networks and bypass_networks are hand-edited lists in a
    settings file, and the AGS dialog appends an empty entry the moment
    its "add" button is pressed. strict=False so that 10.0.0.1/8 - a
    host address where a network was meant - is read as the network it
    names rather than refused.
    """
    try:
        return ipaddress.ip_network(str(value).strip(), strict=False)
    except ValueError:
        return None


def _covers(outer, inner) -> bool:
    """Whether `outer` contains `inner`, across address families.

    subnet_of() raises TypeError when the two are not the same family, so
    an IPv6 bridge beside an IPv4 route would have ended the whole run
    with a traceback - a doctor that dies on the first machine with a
    modern bridge on it reports nothing about anything.
    """
    if outer.version != inner.version:
        return False
    return inner.subnet_of(outer)


def discover_bridges(*, runner: Runner | None = None) -> list[Network]:
    """Every local bridge and the network it serves.

    `ip -j addr show type bridge` answers for docker0, podman0, virbr0
    and the br-* interfaces Docker creates per network - all of them are
    ordinary Linux bridges, which is what the filter asks for.
    """
    entries = _ip_json(["ip", "-j", "-4", "addr", "show", "type", "bridge"],
                       runner=runner)
    bridges = []
    for entry in entries:
        device = entry.get("ifname", "")
        for address in entry.get("addr_info", []):
            if address.get("family") != "inet":
                continue
            network = _network(
                f"{address.get('local')}/{address.get('prefixlen')}")
            if network:
                bridges.append(Network(str(network), device))
    return bridges


def discover_routes(*, runner: Runner | None = None) -> list[Network]:
    """Every routed network, with the device carrying it.

    The default route is left out: it has no network to compare against,
    and everything is inside it.
    """
    routes = []
    for entry in _ip_json(["ip", "-j", "route", "show"], runner=runner):
        destination = entry.get("dst", "")
        if not destination or destination == "default":
            continue
        if _network(destination) is None:
            continue
        routes.append(Network(destination, entry.get("dev", "")))
    return routes


def _ip_json(argv: list[str], *, runner: Runner | None = None) -> list[dict]:
    """Read one `ip -j` answer, or nothing at all.

    A machine without iproute2, an `ip` too old for -j, a route table
    that is not JSON: none of those are findings. They mean this check
    could not be made, and inventing a finding out of that would be worse
    than the silence the doctor exists to break.
    """
    runner = runner or subprocess.run
    try:
        result = runner(argv, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    try:
        parsed = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [entry for entry in parsed if isinstance(entry, dict)]


# --------------------------------------------------------------------
# plugins
# --------------------------------------------------------------------

def check_plugin_abi(version: dict[str, Any]) -> list[Finding]:
    """Libraries Hyprland was built against that are not the ones here.

    Hyprland's plugin ABI hash carries the MAJOR.MINOR of each of these
    libraries - `hyprctl version -j` reports it as, for instance,
    <commit>_aq_0.12_hu_0.13_hg_0.5_hc_0.1_hlg_0.6. A plugin built on
    this machine is built against the libraries that are INSTALLED here;
    when Hyprland was built against different ones, the two hashes differ
    and Hyprland refuses the plugin.

    Compared at major.minor, therefore, and not at patch level: 0.12.0
    against 0.12.1 produces the same hash, and reporting it would fire on
    a machine where every plugin loads.
    """
    findings = []
    for library in ABI_LIBRARIES:
        built = str(version.get(f"build{library}", ""))
        installed = str(version.get(f"system{library}", ""))
        if not built or not installed:
            continue
        if _abi_level(built) == _abi_level(installed):
            continue

        findings.append(Finding(
            what=(f"Hyprland was built against {library} {built}, but "
                  f"{installed} is installed."),
            costs=("a plugin built here carries a different ABI hash than "
                   "the running Hyprland and is refused at load time. The "
                   "session still starts, so the only sign is that the "
                   "feature the plugin provided - title bars, extra borders "
                   "- is simply not there, with nothing in any log."),
            fix=("install the zepos-<plugin> packages built against the "
                 "Hyprland that is actually installed, or install the "
                 "Hyprland build these libraries match. The objects come "
                 "from packages and live in /usr/lib/hyprland/plugins; "
                 "nothing is compiled on this machine."),
        ))
    return findings


def _abi_level(version: str) -> tuple[str, ...]:
    return tuple(version.split(".")[:2])


def discover_hyprland_version(*, runner: Runner | None = None) -> dict[str, Any]:
    """What the running compositor says about itself, or nothing.

    Nothing is the normal answer from a TTY, and it is not a finding:
    there is nothing true to say about the ABI of a compositor that is
    not running.
    """
    runner = runner or subprocess.run
    try:
        result = runner(["hyprctl", "version", "-j"],
                        capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def check_plugin_objects(hyprland_conf: Path) -> list[Finding]:
    """Plugin objects the configuration names and cannot load.

    WHERE THE DRIFT COMES FROM, and why this is not the same question
    the generator already answered
        zepos-generate writes a load line only for an object that was on
        the machine at that moment. Packages move afterwards: a
        `pacman -Syu` that removes or replaces a plugin leaves the
        configuration IN PLACE naming an object that is gone, and nothing
        rewrites it until the next generation - which for a login through
        a display manager may be never. That gap is exactly what this
        reads, and it is why it reads the published file rather than the
        staged one.

    Both files that can carry a load line are checked by collect(): the
    include plugins.py writes, and hyprland.conf itself, which a user
    override can put one in.

    The rule for WHICH plugin lines can be answered at all belongs to
    validate_output._plugin_findings and is used from there rather than
    written a second time. Its header records what it deliberately leaves
    alone: a bare name, which cannot be turned into a path, and a
    relative path, which would be measured against whatever directory the
    user happened to be standing in when they ran this.
    """
    if not hyprland_conf.is_file():
        return []

    try:
        text = hyprland_conf.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    return [
        Finding(
            what=f"{finding}.",
            costs=("Hyprland refuses to start a plugin whose object is "
                   "absent. The feature it provides is missing from the "
                   "session, and the reason appears only in Hyprland's own "
                   "startup log, which nobody reads after a successful "
                   "login."),
            fix=("reinstall the package that provides the object, or remove "
                 f"the plugin line from {hyprland_conf}."),
        )
        for finding in validate_output._plugin_findings(
            Path(hyprland_conf.name), text)
    ]


# --------------------------------------------------------------------
# the message catalogue
# --------------------------------------------------------------------

def check_catalogue(template: Path, catalogue: Path) -> list[Finding]:
    """Messages the German catalogue does not translate.

    A missing entry and an empty msgstr have the same effect - gettext
    falls back to the English msgid - so both are reported. A catalogue
    that is not there at all is not a finding: it means this check could
    not be made.
    """
    if not template.is_file() or not catalogue.is_file():
        return []

    translated = {
        msgid for msgid, msgstr in PO_ENTRY.findall(
            catalogue.read_text(encoding="utf-8"))
        if msgid and msgstr
    }

    findings = []
    for msgid, _msgstr in PO_ENTRY.findall(
            template.read_text(encoding="utf-8")):
        if not msgid or msgid in translated:
            continue
        findings.append(Finding(
            what=f'the German catalogue has no translation for "{msgid}".',
            costs=("a user who chose German reads that message in English, "
                   "with nothing to tell them a translation was meant to "
                   "exist."),
            fix=(f"add the entry to {catalogue} and rebuild the catalogues "
                 f"with po/build.sh."),
        ))
    return findings


def catalogue_paths() -> tuple[Path, Path]:
    """Where the catalogue is, in the package and in a checkout.

    Measured from THIS file rather than from system_root(): the command
    that started us already resolved which of the two trees it is running
    out of, and this module is in it. system_root() answers the INSTALLED
    location whenever its environment override is unset, which is the
    normal case in a checkout - and the catalogue check would then read a
    package that need not even be installed and silently check nothing.

    The package puts po/ below that root; a checkout keeps it beside
    src/. Both are looked at, in that order, and the first that holds a
    catalogue answers.
    """
    root = Path(__file__).resolve().parent
    for directory in (root / CATALOGUE_DIRECTORY,
                      root.parent / CATALOGUE_DIRECTORY):
        template = directory / CATALOGUE_TEMPLATE
        catalogue = directory / CATALOGUE
        if template.is_file() and catalogue.is_file():
            return template, catalogue
    return root / CATALOGUE_DIRECTORY / CATALOGUE_TEMPLATE, \
        root / CATALOGUE_DIRECTORY / CATALOGUE


# --------------------------------------------------------------------
# a clock in a timezone this machine does not have
# --------------------------------------------------------------------

def zoneinfo_directory() -> Path:
    """The timezone database, honouring TZDIR the way glibc does."""
    return Path(os.environ.get(ZONEINFO_VARIABLE) or ZONEINFO)


def check_clock_zones(configured: Iterable[clocks.Clock], *,
                      database: Path | None = None) -> list[Finding]:
    """Configured zones the database does not hold.

    A zone is known when the database has a file for it - the same test
    the generated module makes, and the only one available without
    asking `date`, which answers the question wrongly on purpose:
    `TZ=Mars/Olympus_Mons date` exits 0 and prints the UTC time with
    "Mars" as the abbreviation.

    An absent database is not a finding. It means this check could not be
    made, exactly as check_catalogue treats a catalogue that is not
    there; reporting every zone as unknown because tzdata is missing
    would bury the one that is actually a typo.
    """
    directory = database or zoneinfo_directory()
    if not directory.is_dir():
        return []

    findings = []
    for clock in configured:
        if (directory / clock.zone).is_file():
            continue
        findings.append(Finding(
            what=(f"clocks.zones names \"{clock.zone}\", which {directory} "
                  f"does not have."),
            costs=("the bar cannot show that clock. `date` would accept the "
                   "name, exit 0 and print UTC, so the module refuses a time "
                   "for it and marks it - in its tooltip, which is only read "
                   "by somebody who already suspects the clock."),
            fix=(f"`{ZONE_LISTING}` prints the names this machine knows; "
                 f"write the corrected list with `zepos-settings set "
                 f"clocks.zones '[\"Europe/Lisbon\"]'`."),
        ))
    return findings


def configured_clocks() -> tuple[list[clocks.Clock], list[Finding]]:
    """The clocks from the settings file, and what is wrong with the list.

    A settings file that cannot be read at all answers with nothing:
    configured_networks() below reports that failure once, and a second
    finding saying the same thing about the same file is noise in front
    of it.

    A file that reads and whose clocks section is unusable IS reported
    here, because nothing else looks at that section. clocks.py refuses
    `"zones": "Asia/Tokyo"` - one zone written as a string, which walks
    character by character into ten clocks called A, s, i, a... - and a
    doctor that let that exception out would report nothing about
    anything else either.
    """
    try:
        document = settings.load()
    except (ValueError, OSError):
        return [], []

    try:
        return clocks.zones(clocks.settings_section(document)), []
    except settings.UnusableSettings as exc:
        return [], [Finding(
            what=f"in {user_root() / settings.FILENAME}, {exc}",
            costs=("the clock module cannot be generated from it - "
                   "zepos-generate refuses the whole run - so the bar keeps "
                   "whatever clocks it was last generated with, and every "
                   "further change to any setting is refused too."),
            fix=(f"correct the entry named above; `{ZONE_LISTING}` prints "
                 f"the zone names this machine knows."),
        )]


# --------------------------------------------------------------------
# die Selbstaktualisierung
# --------------------------------------------------------------------

# Was `systemctl is-enabled` antwortet, wenn die Einheit laeuft, wie sie
# soll. "static" kann zepos-update.timer nicht sein - sie hat einen
# [Install]-Abschnitt -, und "linked" ist der Fall, den ein Entwickler
# selbst gebaut hat und der ebenso funktioniert.
TIMER_ENABLED_STATES = ("enabled", "enabled-runtime", "linked",
                        "linked-runtime")

TIMER_STATE_COMMAND = ("systemctl", "is-enabled", update.TIMER_UNIT)


def timer_state(*, runner: Runner | None = None) -> str:
    """Was systemd ueber den Zeitgeber sagt, oder "".

    Ein Lesebefehl, wie jeder andere hier: `is-enabled` aendert nichts
    und braucht keine Rechte. Eine leere Antwort heisst "die Frage liess
    sich nicht stellen" - kein systemd, keine Einheit, kein Fund - und
    daraus wird ausdruecklich keine Meldung gemacht: der Doktor laeuft
    auch in einem Container und auf der Maschine eines Entwicklers.
    """
    runner = runner or subprocess.run
    try:
        result = runner(list(TIMER_STATE_COMMAND), capture_output=True,
                        text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    # `is-enabled` endet bei "disabled" mit 1 und druckt trotzdem die
    # Antwort. Der Rueckgabewert ist hier also nicht die Auskunft - die
    # steht auf stdout.
    return (result.stdout or "").strip()


def check_update(config: dict[str, Any] | None, state: dict[str, Any] | None,
                 enabled_state: str) -> list[Finding]:
    """Warum sich diese Maschine nicht aktualisiert.

    `config is None` heisst: die Einstellungsdatei ist da und unlesbar.
    Das ist selbst der erste Fund, denn der Dienst liest sie genauso und
    tut dann gar nichts.
    """
    if config is None:
        return [Finding(
            what=f"{update.config_path()} kann nicht gelesen werden.",
            costs=("die Selbstaktualisierung laeuft nicht. Der Dienst liest "
                   "dieselbe Datei, bricht ab und hinterlaesst nichts, was "
                   "auf dem Schreibtisch sichtbar waere - die Maschine holt "
                   "sich schlicht keine neuen Fassungen mehr."),
            fix=("die Datei ist ein JSON-Objekt; `zepos-update --help` "
                 "nennt jede Einstellung. Zur Not beiseitelegen - fehlt "
                 "sie, gelten die Vorgaben."),
        )]

    findings: list[Finding] = []
    if config["enabled"] and enabled_state and \
            enabled_state not in TIMER_ENABLED_STATES:
        findings.append(Finding(
            what=(f"update.enabled ist true, aber {update.TIMER_UNIT} ist "
                  f"\"{enabled_state}\"."),
            costs=("nichts loest die Aktualisierung aus. Die Maschine sieht "
                   "aus wie eine, die auf dem Stand ist, und bleibt auf dem "
                   "Stand des Tages, an dem der Zeitgeber abgeschaltet "
                   "wurde - auch fuer Sicherheitskorrekturen."),
            fix=("`sudo zepos-update --apply-schedule` bringt systemd auf "
                 "die Einstellungen (der Befehl hiess frueher --apply und "
                 "spielt NICHTS ein). Wenn die Aktualisierung wirklich aus sein "
                 "soll, gehoert das in die Einstellung: `sudo "
                 "zepos-settings set update.enabled false`."),
        ))

    if state is None:
        # Kein Lauf verzeichnet. AUSDRUECKLICH KEINE MELDUNG: das ist der
        # Zustand jeder Maschine an ihrem ersten Tag, und ein Doktor, der
        # eine frische Installation anmeckert, ist einer, den man nicht
        # mehr ernst nimmt. Ob und wann etwas laufen wird, beantwortet
        # der Zeitgeber - und ob er dafuer eingeschaltet ist, steht oben.
        # "Wann war das letzte Mal" beantwortet `zepos-update --status`.
        return findings

    if state.get("result") == update.Outcome.FAILED:
        message = (state.get("message") or "").strip().splitlines()
        findings.append(Finding(
            what=(f"die letzte Aktualisierung ({state.get('finished')}) ist "
                  f"gescheitert, pacman endete mit "
                  f"{state.get('returncode')}"
                  + (f": {message[-1]}" if message else ".")),
            costs=("die Maschine bleibt auf ihrem Stand. Ist die Ursache "
                   "eine Unterschrift, ist das genau das gewollte Verhalten "
                   "von SigLevel = Required - und dann ist die Meldung hier "
                   "das Einzige, was davon zu sehen ist."),
            fix=(f"`zepos-update --status` zeigt den Wortlaut, "
                 f"`journalctl -u {update.SERVICE_UNIT}` den ganzen Lauf. "
                 f"Bei einer abgelehnten Unterschrift: `pacman-key -l` "
                 f"zeigt, ob der ZepOS-Schluessel noch da ist."),
        ))
    return findings


def update_configuration() -> dict[str, Any] | None:
    try:
        return update.load()
    except (ValueError, OSError):
        return None


# --------------------------------------------------------------------
# the settings the VPN check reads
# --------------------------------------------------------------------

def configured_networks() -> tuple[list[Network], list[str], list[Finding]]:
    """The routed and bypassed networks from the settings file.

    Read in ADDITION to the routing table, because the two answer
    different questions: the table says what is being routed right now,
    the settings say what will be routed the next time the tunnel comes
    up. A configuration that swallows a bridge is worth reporting while
    the tunnel is down, which is exactly when the user has a chance to
    change it.

    A settings file that cannot be read is itself a finding: nothing on
    the machine can be regenerated until it is repaired, and the checks
    below cannot say anything about a VPN configuration they cannot read.
    """
    try:
        # JSONDecodeError is a ValueError, so a corrupt file and an
        # unknown schema version arrive here through the same door.
        document = settings.load()
    except (ValueError, OSError) as exc:
        path = user_root() / settings.FILENAME
        return [], [], [Finding(
            what=f"{path} cannot be read: {exc}.",
            costs=("every setting in it is out of reach. zepos-settings "
                   "refuses to run and zepos-generate refuses to generate, "
                   "so nothing on this machine can be reconfigured until the "
                   "file is repaired - and the VPN check below cannot say "
                   "which of your networks would swallow a local bridge, "
                   "because it cannot read them."),
            fix=(f"check that the file is valid JSON and carries "
                 f"\"schema_version\": {settings.SCHEMA_VERSION}, or move it "
                 f"aside and let the defaults be written again."),
        )]

    vpn = document.get("vpn") or {}
    try:
        # The same reader the generator uses, so that a list which is not
        # a list is refused here too. Iterated directly, a
        # `"routed_networks": "10.8.0.0/24"` - one network as a string,
        # which is the likeliest hand-edit of this file - was walked
        # character by character into eleven entries, four of which parse
        # as networks (1.0.0.0/32 and friends). The doctor then reported
        # on routes this machine has never had, and would have named a
        # local bridge as covered by one of them.
        routed = [Network(value, "") for value in nonblank_entries(
            vpn.get("routed_networks"), setting="vpn.routed_networks")]
        bypassed = nonblank_entries(vpn.get("bypass_networks"),
                                    setting="vpn.bypass_networks")
    except ValueError as exc:
        return [], [], [Finding(
            what=f"in {user_root() / settings.FILENAME}, {exc}",
            costs=("the tunnel cannot be generated from it - every script "
                   "that carries the network list refuses to build - and "
                   "this check cannot say which of your networks would "
                   "swallow a local bridge."),
            fix=("write each network as its own entry of a list: "
                 "[\"10.8.0.0/24\"], not \"10.8.0.0/24\"."),
        )]
    return routed, bypassed, []


# --------------------------------------------------------------------
# Tasten und Startzeilen, die ins Leere zeigen
# --------------------------------------------------------------------
#
# WARUM DAS HIERHER GEHOERT UND NICHT NUR IN DIE TESTSUITE
#     Der Nutzer am 11.08.2026, nachdem er das gebaute System zum ersten
#     Mal benutzt hat: "dateien und datei manager ist auch nicht
#     vorhanden und screenshot tool auch nicht es fehlt gefuehlt alles".
#     Vier Bedienelemente zeigten damals auf Programme, die kein Paket
#     dieses Projekts installiert - SUPER+E auf thunar, SUPER+T auf einen
#     Symlink zu sublime-text-4, SUPER+SHIFT+T auf ferdium, die
#     Druckerzeile auf ein lpstat, das es nicht gab.
#
#     Keines davon hat sich je gemeldet. Hyprland fuehrt `exec` aus, die
#     Shell findet nichts, und das war es: kein Fenster, keine Meldung,
#     kein Protokolleintrag, den jemand liest. Das ist die Definition
#     dessen, wofuer dieses Programm da ist.
#
#     Die Testsuite fragt dasselbe an der ausgelieferten AUSWAHL und
#     faengt es damit vor der Auslieferung. Sie kann aber nicht wissen,
#     was auf DIESER Maschine wirklich liegt: ein `pacman -Rns`, ein
#     Paket, das ein Programm umbenennt, eine Nutzervorlage mit einer
#     eigenen Bindung. Das ist die Luecke, die hier gemessen wird - am
#     PATH dieser Sitzung, an der Konfiguration, die IN PLACE liegt.
#
# Gelesen wird mit keybinds.bound_commands(), das oben importiert ist.
# Der Auswerter stand bis zum 12.08.2026 hier; er ist gewandert, als die
# Tastenuebersicht denselben brauchte. Zwei Auswerter fuer eine Syntax
# heissen zwei Antworten auf "was tut diese Taste", und die eine davon,
# die niemand ansieht, ist die, die falsch wird.


def _reachable(command: str, home: Path) -> bool:
    """Ob dieser Aufruf auf dieser Maschine etwas erreicht."""
    if command.startswith(("/", "~", "./", "../")):
        expanded = command.replace("~", str(home), 1) if command.startswith("~") \
            else command
        return os.access(expanded, os.X_OK)
    return shutil.which(command) is not None


def check_bindings(configs: Iterable[Path], *,
                   home: Path | None = None) -> list[Finding]:
    """Jede Taste und jede Startzeile, deren Programm es hier nicht gibt.

    Eine Meldung JE PROGRAMM und nicht je Zeile: `pactl` steht in zehn
    Bindungen, und zehn Meldungen ueber dieselbe fehlende Datei sind eine
    Liste, die niemand zu Ende liest. Welche Tasten betroffen sind, steht
    trotzdem darin - das ist die Angabe, mit der ein Nutzer es
    nachstellen kann.
    """
    directory = Path(home) if home else Path.home()

    missing: dict[str, list[str]] = {}
    for config in configs:
        if not Path(config).is_file():
            continue
        try:
            text = Path(config).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for where, command in bound_commands(text):
            if _reachable(command, directory):
                continue
            missing.setdefault(command, [])
            if where not in missing[command]:
                missing[command].append(where)

    return [
        Finding(
            what=(f"{command} is named by {', '.join(sorted(places))} and is "
                  f"not on this machine."),
            costs=("The key does nothing at all. Hyprland runs the exec, the "
                   "shell finds no such command, and neither of them says so "
                   "anywhere - which is why a control that points at nothing "
                   "is the one kind of defect a user never reports."),
            fix=(f"install the package that provides {command}, or take the "
                 f"line out of the Hyprland configuration."),
        )
        for command, places in sorted(missing.items())
    ]


# --------------------------------------------------------------------
# command line
# --------------------------------------------------------------------

def collect(*, runner: Runner | None = None) -> list[Finding]:
    """Everything wrong with this machine, discovered on this machine."""
    routed, bypassed, findings = configured_networks()
    findings = list(findings)

    bridges = discover_bridges(runner=runner)
    findings += check_vpn_networks(
        routed + discover_routes(runner=runner),
        bridges=bridges, bypassed=bypassed)

    findings += check_plugin_abi(discover_hyprland_version(runner=runner))
    for where in (HYPRLAND_CONF, PLUGINS_CONF):
        findings += check_plugin_objects(output_root().joinpath(*where))
    findings += check_bindings(
        [output_root().joinpath(*where) for where in BOUND_CONFIGS])
    findings += check_catalogue(*catalogue_paths())

    configured, unusable = configured_clocks()
    findings += unusable
    findings += check_clock_zones(configured)

    findings += check_update(update_configuration(), update.read_state(),
                             timer_state(runner=runner))
    return findings


USAGE = """usage: zepos-doctor

Reports what is wrong with this machine's configuration and takes no
arguments. Exits non-zero when there is something to report, so a script
can act on it."""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["-h"], ["--help"]):
        # On stdout and with a zero status: asking for help is not a
        # mistake, and a user piping this into a pager sees nothing when
        # it goes to stderr.
        print(USAGE)
        return 0
    if argv:
        print(USAGE, file=sys.stderr)
        return 2

    findings = collect()
    if not findings:
        # Said out loud, because "nothing to report" and "did not run"
        # look identical when both print nothing.
        print("zepos-doctor: nothing to report.")
        return 0

    print(f"zepos-doctor found {len(findings)} problem(s):\n")
    for finding in findings:
        print(finding)
        print()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
