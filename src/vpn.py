# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate a swanctl configuration from user settings.

The origin spelled out three child security associations for the
employer's networks. Anyone with a different number of routed networks had
no way to express it, so the list drives the output here instead.

The same list also drives the `ip route` commands the connect script
issues after the tunnel is up. The origin wrote its three networks out a
second and a third time there, which meant a fourth network would have
been tunnelled but not routed - the tunnel comes up, half the traffic
goes nowhere, and nothing says why.

Both entry points refuse an unconfigured VPN rather than filling in a
guess. A default that points at somebody else's network is worse than no
default at all: it either connects a fresh installation somewhere it was
never meant to reach, or it half-works in a way nobody can diagnose.

WHAT ANSWERS "WHICH ADDRESS IS THE TUNNEL'S"
    The second half of this module, and the reason it has a command line
    at all. Six artifacts used to work the assigned virtual address out
    for themselves, each by matching interface addresses against the
    prefix one particular gateway hands its pool out from. On anybody
    else's gateway all six matched nothing, and all six failed
    differently: no routes and no DNS after connecting, a disconnect that
    reported success without doing anything, half-up recovery that never
    ran, and two widgets plus the bar showing the wrong state over a
    healthy tunnel.

    An address is not recognisable by its shape. `swanctl --list-sas` is
    where strongSwan REPORTS the address it was assigned, so that is
    where it is read - see parse_sas() for the exact line, quoted from
    strongSwan's own list_sas.c.

    charon's VICI socket is root-only, so `swanctl` needs privileges and
    the three artifacts that have them - connect, control, watcher - ask
    it directly and pipe the report into `--virtual-address` or
    `--tunnel-health`. The three that poll from the bar and the two AGS
    widgets have none, and must not acquire any: `sudo -n` in a poll loop
    is a failed PAM authentication several times a minute, which on a
    machine with pam_faillock locks the account.

    They ask `--status` instead, which reads the address the connect
    script RECORDED in the state file and then checks whether that exact
    address is still on an interface. That is not the same as reading the
    pattern back one indirection later, which is what the state file was
    worth while `virtual_ip` held the result of that prefix match: the
    recorded value now comes from swanctl and from nowhere else, and it
    is verified against the machine rather than trusted.

    What an unprivileged reader therefore cannot say is anything about a
    tunnel it has no record of. Without the record, one address on an
    interface is indistinguishable from another - which is precisely the
    assumption being removed - so "no state file" is reported as
    disconnected rather than guessed at.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

# Loaded both ways, exactly as settings.py's own header describes: as
# `src.vpn` from the test suite, where src is a package, and as `vpn`
# from /usr/share/zepos, where every module sits flat beside every other.
# Relative first, so which copy of settings.py answers is decided by how
# THIS module was loaded and never by what an earlier import left on the
# path.
try:
    from .settings import UnusableSettings
except ImportError:
    from settings import UnusableSettings

# The same proposal set src/user_settings.py and src/style_definition.py
# already default to. A THIRD default would be one more thing that has to
# be kept in step, and the one place it would show up is a tunnel that
# negotiates something other than what the settings dialog displays.
PROPOSALS = "aes256-sha256-ecp521"

# Matches the connect script's own defaults so the two cannot drift into
# producing differently-tuned tunnels from the same settings file.
REKEY_TIME = "43200"
LIFE_TIME = "43200"
MODE = "tunnel"
REPLAY_WINDOW = "32"

# Phase 1, from the same set. IKEv2 in main mode: aggressive mode is an
# IKEv1 concept, and the connect script emits the `aggressive` line only
# for version 1, so this module must not emit it for version 2 either.
IKE_VERSION = "2"
KEYLIFE = "86400"
DPD_DELAY = "30"
DPD_TIMEOUT = "120"
ENCAP = "yes"
MOBIKE = "no"

# trap, not start: the origin's value. The child security association is
# installed as a policy and established when traffic matches it, which is
# what the connect script's explicit `swanctl --initiate --child` step
# then does. Switching this to `start` would change when the tunnel comes
# up, which is a behaviour change and not part of removing employer data.
START_ACTION = "trap"


def nonblank_entries(values: Sequence[Any] | None, *,
                     setting: str = "the setting") -> list[str]:
    """A list of settings values with blanks and surrounding space removed.

    Used for the routed networks, the bypassed networks and the DNS
    servers - all three user-editable lists. An empty string is neither a
    network nor a resolver. The AGS settings dialog appends exactly that
    when its "add" button is pressed, so a half-finished edit is the
    normal way one arrives here - and `remote_ts =` with nothing behind
    it is a configuration strongSwan refuses to load, which the user
    would meet as a tunnel that will not start rather than as the empty
    row they left behind.

    A str is refused rather than iterated. It satisfies every iterable
    signature a list does, so `"routed_networks": "10.8.0.0/24"` - one
    network where a list of one belongs, and the likeliest hand-edit of
    this file - was walked CHARACTER BY CHARACTER: eleven child security
    associations named work-1 to work-11, each with a single digit or a
    dot as its remote_ts, and eleven `ip route add` targets to match.
    Nothing in the chain could tell that apart from eleven networks the
    user meant. This module's premise is to refuse rather than guess, and
    an input that is neither absent nor a list defeats it - so it is
    named, with the value that has to be corrected, rather than
    interpreted.

    `setting` is the dotted name the value came from. Three settings are
    read through here and a message naming none of them would leave the
    user to work out which of the three they have to correct.
    """
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        raise UnusableSettings(
            f"{setting} is the single string {values!r} where a list of "
            f"entries belongs. One entry is a list of one: [{values!r}]."
        )
    if not isinstance(values, (list, tuple)):
        raise UnusableSettings(
            f"{setting} is a {type(values).__name__} ({values!r}) where a "
            f"list of entries belongs."
        )
    return [str(value).strip() for value in values if str(value).strip()]


def routed_networks_line(routed_networks: Sequence[Any] | None) -> str:
    """The networks as one whitespace-separated string, for a shell loop.

    Pure formatting. The refusal to accept an empty list lives in
    swanctl_children() alone, so there is one place that decides what an
    unusable VPN configuration is.
    """
    return " ".join(nonblank_entries(routed_networks,
                                     setting="vpn.routed_networks"))


# --------------------------------------------------------------------
# VOLLTUNNEL: LEITET DIESE VERBINDUNG DEN GESAMTEN VERKEHR UM?
# --------------------------------------------------------------------
#
# GEFRAGT am 22.08.2026: "und alle neuen vpn arten wireguard und openvpn
# folgen dem split tunneling wie ipsec oder? kein full routing?? ich
# meine wireguard war standard so"
#
# GEMESSEN am selben Tag, BEVOR hier etwas gebaut wurde: `0.0.0.0/0` kam
# in diesem Modul GENAU EINMAL vor, und zwar in einem Kommentar (der
# Beispielausgabe von swanctl weiter unten); in
# ags-vpn-settings.template kam es ueberhaupt nicht vor. Es gab also
# weder eine Erkennung noch einen Hinweis - der Nutzer haette einen
# Volltunnel an der Geschwindigkeit gemerkt und an nichts sonst.
#
# Und die Frage trifft, weil die drei Bauarten zwar DIESELBE Netzliste
# fuellen, aber aus Dateien mit sehr verschiedenen Gewohnheiten kommen:
#
#     IPsec       routed_networks steht von Hand da - ein Teiltunnel,
#                 solange niemand das ganze Netz hineinschreibt.
#     WireGuard   AllowedIPs eines Anbieters deckt fast immer alles ab.
#     OpenVPN     `redirect-gateway` sagt dasselbe in einem Wort.
#
# EINE Regel fuer alle drei, und nicht drei Sonderfaelle: was gezaehlt
# wird, ist die ABDECKUNG einer Liste von Netzen.
#
# WARUM GERECHNET UND NICHT VERGLICHEN
#     "Deckt alles ab" hat mehr als eine Schreibweise. Die haeufigste
#     zweite ist das Paar 0.0.0.0/1 + 128.0.0.0/1, und openvpn(8) nennt
#     unter der Fahne `def1` auch den Grund: "override the default
#     gateway by using 0.0.0.0/1 and 128.0.0.0/1 rather than 0.0.0.0/0.
#     This has the benefit of overriding but not wiping out the original
#     default gateway." Anbieter schreiben genau deshalb so. Ein
#     Zeichenkettenvergleich auf das Nullnetz sieht davon nichts.
#
#     ipaddress.collapse_addresses() fasst benachbarte und ueberlappende
#     Netze zusammen, solange es geht. Bleibt danach eines mit
#     Praefixlaenge 0 uebrig, ist der ganze Adressraum gedeckt - egal, in
#     wieviele Stuecke er zerlegt war. Zwei Haelften, vier Viertel und
#     das Nullnetz fallen damit unter dieselbe Regel, ohne dass eine
#     davon einzeln aufgeschrieben werden muesste.
#
# WAS HIER AUSDRUECKLICH NICHT PASSIERT
#     Es aendert sich keine Vorgabe und kein Verhalten. Ein Volltunnel
#     ist eine gueltige und oft gewollte Einstellung - bei einem
#     Anbieter-VPN ist er der ganze Zweck. Bestellt wurde am 22.08.2026
#     woertlich: "nein, ich will das jetzt nicht umstellen - ich will es
#     konfigurierbar haben". Ein Einleser, der aus einem Volltunnel
#     stillschweigend einen Teiltunnel machte, waere schlimmer als gar
#     keine Warnung: der Nutzer glaubte sich geschuetzt und waere es
#     nicht. Gezeigt wird, was in der Datei steht.
FULL_TUNNEL_V4 = "ipv4"
FULL_TUNNEL_V6 = "ipv6"

# Die Reihenfolge, in der die Familien gemeldet werden. Fest, damit zwei
# Aufrufe mit derselben Liste dieselbe Antwort geben - der Hinweis im
# Fenster wird bei jedem Tastendruck neu gebaut, und eine Antwort, deren
# Reihenfolge von der Eingabe abhaengt, liesse ihn flackern.
_FULL_TUNNEL_ORDER = (FULL_TUNNEL_V4, FULL_TUNNEL_V6)


def full_tunnel_families(networks: Sequence[Any] | None, *,
                         setting: str = "the network list") -> list[str]:
    """Welche Adressfamilien diese Netzliste VOLLSTAENDIG abdeckt.

    `["ipv4"]`, `["ipv6"]`, beides oder nichts. Nichts heisst
    Teiltunnel, und das ist der Normalfall.

    Ein Eintrag, der kein Netz ist, wird uebergangen statt geraten: er
    deckt nichts ab, und ihn zu MELDEN ist die Aufgabe des Einlesers,
    der ihn mit Datei und Zeilennummer vor sich hat. Ein `str` statt
    einer Liste faellt dagegen durch nonblank_entries() - dieselbe
    Stelle, die schon fuer die gerouteten Netze, die umgangenen Netze
    und die DNS-Server entscheidet, was eine unbrauchbare Liste ist.
    """
    per_family: dict[int, list[Any]] = {4: [], 6: []}
    for entry in nonblank_entries(networks, setting=setting):
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        per_family[network.version].append(network)

    covered = set()
    for version, family in ((4, FULL_TUNNEL_V4), (6, FULL_TUNNEL_V6)):
        if any(block.prefixlen == 0
               for block in ipaddress.collapse_addresses(per_family[version])):
            covered.add(family)
    return [family for family in _FULL_TUNNEL_ORDER if family in covered]


def child_names(connection: str, routed_networks: Sequence[Any] | None) -> list[str]:
    """The name of each child security association, in list order.

    Three separate places need these names: the configuration block, the
    connect script that initiates each child, and the watcher that
    re-initiates a dead one. The origin derived them independently in
    each place, from a settings file that could change in between, and
    the failure that produces is `child 'x' not found` - naming a child
    the user never configured, from a script they did not run.
    """
    return [
        f"{connection}-{index}"
        for index in range(1, len(nonblank_entries(
            routed_networks, setting="vpn.routed_networks")) + 1)
    ]


def swanctl_children(
    connection: str,
    routed_networks: Sequence[Any] | None,
    *,
    rekey_time: str = REKEY_TIME,
    life_time: str = LIFE_TIME,
    esp_proposals: str = PROPOSALS,
    mode: str = MODE,
    replay_window: str = REPLAY_WINDOW,
    start_action: str = START_ACTION,
) -> str:
    """One child security association per routed network.

    The phase-2 values stay parameters because the origin exposed every
    one of them in the settings dialog. Generating the blocks from a list
    is the change; taking the user's ESP tuning away with it would not be.
    """
    networks = nonblank_entries(routed_networks,
                                setting="vpn.routed_networks")
    if not networks:
        raise ValueError(
            "a VPN connection with no routed networks would carry no traffic"
        )

    blocks = []
    for name, network in zip(child_names(connection, networks), networks):
        blocks.append(f"""            {name} {{
                remote_ts = {network}
                rekey_time = {rekey_time}s
                life_time = {life_time}s
                dpd_action = restart
                esp_proposals = {esp_proposals}
                mode = {mode}
                replay_window = {replay_window}
                start_action = {start_action}
                policies = yes
            }}""")
    return "\n".join(blocks)


def _setting(section: dict[str, Any], key: str, fallback: str) -> str:
    """One phase value from the settings, or the project default."""
    value = section.get(key)
    if value is None or str(value).strip() == "":
        return fallback
    return str(value).strip()


def _yes_no(section: dict[str, Any], key: str, fallback: str) -> str:
    """A boolean phase value, in the spelling swanctl.conf uses."""
    value = section.get(key)
    if value is None:
        return fallback
    return "yes" if value else "no"


def swanctl_config(settings: dict[str, Any]) -> str:
    """A complete swanctl connection block from a settings document.

    The connect script builds its own copy in shell rather than calling
    this, because the file it writes also carries the pre-shared key, the
    XAuth secret and the interface the IKE source is pinned to - none of
    which exist at generation time. This is the settings-only form: what
    the configured networks and server amount to, without a connection
    attempt and without credentials, so a configuration can be inspected
    or checked before anything is dialled.

    Every phase-1 and phase-2 value in the document is honoured. An
    earlier version read only the server, the connection name and the
    networks and filled the rest from the constants above, which meant a
    document asking for IKEv1 aggressive mode with modp1536 - the one
    combination an old gateway may leave a user no choice about - came
    back as IKEv2 with ecp521. Nothing said so. For the doctor this
    function is meant to serve, that is the worst possible answer: a
    report about a configuration other than the one deployed.
    """
    vpn = settings.get("vpn", {})
    server = str(vpn.get("server", "")).strip()
    if not server:
        raise ValueError("no VPN server configured")

    connection = str(vpn.get("connection_name") or "work").strip()
    phase1 = vpn.get("phase1") or {}
    phase2 = vpn.get("phase2") or {}

    children = swanctl_children(
        connection,
        vpn.get("routed_networks"),
        rekey_time=_setting(phase2, "rekey_time", REKEY_TIME),
        life_time=_setting(phase2, "life_time", LIFE_TIME),
        esp_proposals=_setting(phase2, "esp_proposals", PROPOSALS),
        mode=_setting(phase2, "mode", MODE),
        replay_window=_setting(phase2, "replay_window", REPLAY_WINDOW),
    )

    version = _setting(phase1, "version", IKE_VERSION)
    # Aggressive mode is an IKEv1 concept. strongSwan rejects the keyword
    # under version 2, and the connect script emits it only for version 1,
    # so this must not emit it either - honouring the setting includes
    # honouring the version it belongs to.
    aggressive = ""
    if version == "1":
        aggressive = f"\n        aggressive = {_yes_no(phase1, 'aggressive', 'no')}"

    return f"""connections {{
    {connection} {{
        version = {version}{aggressive}
        proposals = {_setting(phase1, "proposals", PROPOSALS)}
        dpd_delay = {_setting(phase1, "dpd_delay", DPD_DELAY)}s
        dpd_timeout = {_setting(phase1, "dpd_timeout", DPD_TIMEOUT)}s
        encap = {_yes_no(phase1, "encap", ENCAP)}
        mobike = {_yes_no(phase1, "mobike", MOBIKE)}
        rekey_time = {_setting(phase1, "keylife", KEYLIFE)}s
        remote {{
            auth = psk
            id = {server}
        }}
        remote_addrs = {server}
        vips = 0.0.0.0
        children {{
{children}
        }}
    }}
}}
"""


# --------------------------------------------------------------------
# the address the gateway assigned
# --------------------------------------------------------------------
#
# `swanctl --list-sas` writes one IKE_SA per block. From strongSwan's own
# src/swanctl/commands/list_sas.c (6.0.7, the version installed here):
#
#     printf("%s: #%s, %s, IKEv%s, %s_i%s %s_r%s\n", name, uniqueid,
#            state, version, initiator-spi, ..., responder-spi, ...);
#     printf("  local  '%s' @ %s[%s]", local-id, local-host, local-port);
#     if (local-vips) printf(" [%s]", local-vips);
#     printf("\n");
#     printf("  remote '%s' @ %s[%s]", remote-id, remote-host, remote-port);
#     ...
#     printf("  %s: #%s, reqid %s", child-name, child-uniqueid, reqid);
#
# which on a client whose gateway assigned it 172.20.4.9 reads:
#
#     work: #1, ESTABLISHED, IKEv2, a1b2c3d4e5f60718_i* 90a1b2c3d4e5f607_r
#       local  'user@example.org' @ 198.51.100.7[4500] [172.20.4.9]
#       remote 'vpn.example.org' @ 198.51.100.9[4500]
#       AES_CBC-256/HMAC_SHA2_256_128/PRF_HMAC_SHA2_256/ECP_521
#       established 4s ago, rekeying in 13721s
#       work-1: #1, reqid 1, INSTALLED, TUNNEL, ESP:AES_CBC-256/HMAC_SHA2_256_128
#         installed 4s ago, rekeying in 3242s, expires in 3956s
#         local  0.0.0.0/0
#         remote 203.0.113.0/24
#
# The FIRST bracket on the local line is the port, and every bracket
# after it is a virtual address - one printf each, so several assigned
# addresses arrive as several brackets. The port is why this is matched
# rather than scanned: `grep -o '\[[^]]*\]'` on that line returns 4500.
#
# It is the LOCAL vips that matter. This machine is the initiator, and
# `vips = 0.0.0.0` in the connection block above is the request that
# makes the gateway assign one; the address it hands back is ours, so it
# is reported on our side of the SA. A gateway reports its clients'
# addresses on the remote line, which is a different machine's business.

# Indented by two spaces in the output; anchored to the line start so an
# address inside a child SA's traffic selector cannot be read as one.
LOCAL_LINE = re.compile(
    r"^\s+local\s+'.*'\s+@\s+(?P<host>\S+?)\[(?P<port>[^\[\]]*)\]"
    r"(?P<vips>(?:\s+\[[^\[\]]+\])*)\s*$")

# The IKE_SA header, which is the only line printed flush left.
IKE_SA_LINE = re.compile(
    r"^(?P<name>\S+):\s+#(?P<unique>\d+),\s+(?P<state>[A-Z_-]+),\s+IKEv\d")

# A CHILD_SA header, indented under its IKE_SA. `reqid` is what tells it
# apart from the IKE_SA line, which has no reqid.
CHILD_SA_LINE = re.compile(
    r"^\s+(?P<name>\S+):\s+#(?P<unique>\d+),\s+reqid\s+\d+,\s+(?P<state>[A-Z_-]+)")

BRACKETED = re.compile(r"\[([^\[\]]+)\]")

# The three answers tunnel_health() gives, and the exit codes the shell
# callers read them as. They are separate values rather than a boolean
# because two of the six callers used to treat "no address" and "no
# tunnel" as the same thing, which is how a half-up tunnel could go
# unrepaired: the watcher returned "nothing to do" for the one state it
# exists to fix.
HEALTHY = "healthy"
HALF_UP = "half-up"
NO_TUNNEL = "no-tunnel"
HEALTH_EXIT = {HEALTHY: 0, HALF_UP: 1, NO_TUNNEL: 2}

# What an unprivileged reader can say about the tunnel.
CONNECTED = "connected"
STALE = "stale"
DISCONNECTED = "disconnected"

# Written by vpn-connect.sh into $XDG_RUNTIME_DIR, removed on disconnect.
STATE_FILENAME = "vpn-active"

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class IkeSA:
    """One IKE_SA as `swanctl --list-sas` reports it.

    `addresses` are the virtual addresses assigned to THIS end, in the
    order strongSwan printed them. Empty is a legitimate state: a gateway
    that routes the client's own address instead of handing out one from
    a pool establishes a perfectly good tunnel with no virtual address at
    all, and calling that "not connected" is one of the six failures this
    replaced.
    """

    name: str
    state: str
    addresses: tuple[str, ...]
    installed_children: int


def parse_sas(report: str) -> list[IkeSA]:
    """Every IKE_SA in a `swanctl --list-sas` report.

    An empty report is no tunnel, not an error: `swanctl --list-sas`
    prints nothing at all when charon holds no security association, and
    that is also what a caller sees when swanctl is missing or refused
    the connection to the daemon. All three mean the same thing to
    everyone here - there is nothing to route through - and the caller
    that needs to tell them apart (the connect script, which has just
    tried to establish one) has swanctl's own exit status for it.
    """
    sas: list[IkeSA] = []
    name = state = ""
    addresses: list[str] = []
    installed = 0
    seen = False

    def flush() -> None:
        if seen:
            sas.append(IkeSA(name=name, state=state,
                             addresses=tuple(addresses),
                             installed_children=installed))

    for line in report.splitlines():
        header = IKE_SA_LINE.match(line)
        if header:
            flush()
            seen = True
            name = header.group("name")
            state = header.group("state")
            addresses = []
            installed = 0
            continue
        if not seen:
            continue
        child = CHILD_SA_LINE.match(line)
        if child:
            if child.group("state") == "INSTALLED":
                installed += 1
            continue
        local = LOCAL_LINE.match(line)
        if local:
            for bracket in BRACKETED.findall(local.group("vips")):
                # One printf per address, but a single vici value may
                # still carry several separated by whitespace or commas.
                addresses.extend(
                    entry for entry in re.split(r"[,\s]+", bracket.strip())
                    if entry)
    flush()
    return sas


def assigned_address(report: str) -> str:
    """The virtual address this end was assigned, or "".

    The first one reported. A machine with two tunnels up has two, and
    the callers here install routes and clean up after ONE connection -
    the one whose report they just fetched - so taking the first is the
    honest answer rather than a merge of both.
    """
    for sa in parse_sas(report):
        if sa.addresses:
            return sa.addresses[0]
    return ""


def tunnel_health(report: str) -> str:
    """HEALTHY, HALF_UP or NO_TUNNEL, from the SAs alone.

    CHILD_SAs are the data path: an ESTABLISHED IKE_SA with none of them
    installed is a connection that carries nothing while every visible
    sign says it worked. That is the state the watcher repairs, and it
    has to be distinguishable from "there is no tunnel here" - which is
    the state where re-initiating a child would be dialling out on the
    user's behalf uninvited.
    """
    established = [sa for sa in parse_sas(report) if sa.state == "ESTABLISHED"]
    if not established:
        return NO_TUNNEL
    if any(sa.installed_children for sa in established):
        return HEALTHY
    return HALF_UP


# --------------------------------------------------------------------
# what an unprivileged reader may say
# --------------------------------------------------------------------

def _run(runner: Runner, argv: list[str]) -> str:
    """One command's stdout, or "" if it could not be run.

    A missing `ip` or `pgrep` is not an exception here. Every caller of
    this half is a bar module or a widget refreshing on a timer, and the
    answer they need for an unanswerable question is "I cannot tell",
    which the callers below express as `disconnected`.
    """
    try:
        completed = runner(argv, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout or ""


def configured_addresses(runner: Runner = subprocess.run) -> dict[str, str]:
    """Every address on this machine, mapped to its address/prefix form.

    `ip -o addr show` prints one address per line:

        2: eth0    inet 172.20.4.9/32 scope global eth0

    so the token after `inet` or `inet6` is the answer, and the map is
    keyed by the bare address because that is what the state file holds
    while `ip addr del` needs the prefix.
    """
    found: dict[str, str] = {}
    for line in _run(runner, ["ip", "-o", "addr", "show"]).splitlines():
        fields = line.split()
        for index, field in enumerate(fields[:-1]):
            if field in ("inet", "inet6"):
                cidr = fields[index + 1]
                found.setdefault(cidr.split("/")[0], cidr)
    return found


def address_present(address: str, runner: Runner = subprocess.run) -> str:
    """The address/prefix under which `address` is configured, or "".

    An exact comparison against the addresses the kernel reports, not a
    match against a shape. This is the whole replacement for the six
    prefix greps: the question "is the tunnel's address up" can
    only be asked once something has said which address that is.
    """
    if not address:
        return ""
    return configured_addresses(runner).get(address, "")


def state_path(runtime_dir: str | None = None) -> Path:
    """Where vpn-connect.sh records what it established."""
    root = (runtime_dir or os.environ.get("XDG_RUNTIME_DIR")
            or f"/run/user/{os.getuid()}")
    return Path(root) / STATE_FILENAME


def read_state(path: Path | None = None) -> dict[str, Any] | None:
    """The recorded connection, or None when there is no record.

    Absent, unreadable and unparseable all answer None. The file lives on
    the session's tmpfs and is written in one piece by the connect
    script, so a half-written one is a machine that crashed mid-connect -
    for which "we have no record" is the correct answer, not an error the
    bar has to render.
    """
    try:
        text = (path or state_path()).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    try:
        document = json.loads(text.strip())
    except json.JSONDecodeError:
        return None
    return document if isinstance(document, dict) else None


def charon_running(runner: Runner = subprocess.run) -> bool:
    try:
        completed = runner(["pgrep", "-f", "charon"],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def tunnel_status(path: Path | None = None,
                  runner: Runner = subprocess.run) -> tuple[str, str]:
    """(state, address) for a caller with no privileges.

    CONNECTED needs all the evidence there is: a record of a connection
    this machine established, charon still holding it, and - when an
    address was assigned - that exact address still on an interface.

    STALE is the record without the rest of it. It is worth its own value
    because the two ways of reaching it are the two ways a tunnel dies
    without saying so: charon gone while the desktop still believes it is
    connected, and the virtual address released while charon lives on.

    DISCONNECTED covers no record at all. charon running by itself does
    NOT make it stale: strongswan.service may be enabled at boot on a
    machine that has never dialled anything, and reporting a permanent
    fault on such a machine is the mirror image of the bug being removed.

    The address is returned whenever one was recorded, including for
    STALE - the disconnect path needs it precisely then, to take a
    virtual address off an interface that charon never released.
    """
    state = read_state(path)
    if not state:
        return DISCONNECTED, ""

    recorded = str(state.get("virtual_ip") or "").strip()
    if not charon_running(runner):
        return STALE, recorded
    if recorded and not address_present(recorded, runner):
        return STALE, recorded
    # No recorded address means the gateway assigned none. There is
    # nothing to verify against the interfaces, and the record plus a
    # live charon is then all the evidence that exists.
    return CONNECTED, recorded


# --------------------------------------------------------------------
# WireGuard - die zweite Bauart
# --------------------------------------------------------------------
#
# WARUM NETWORKMANAGER UND NICHT `wg-quick` - GEMESSEN am 21.08.2026
#     `wg-quick` liest die .conf ALS SHELL-SKRIPT ein. `PreUp`,
#     `PostUp`, `PreDown` und `PostDown` sind darin Befehlszeilen, und
#     sie laufen als Root. Eine sudoers-Regel `wg-quick up *` waere
#     damit "beliebiger Root-Befehl aus einer Datei, die der Nutzer
#     irgendwo herbekommen hat" - genau das, was der Kopf von
#     src/system/zepos-privileges-config.template unter "Was hier
#     bewusst NICHT steht" verbietet: "kein Werkzeug, das beliebige
#     Dateien schreiben kann ... eine solche Regel waere Root mit
#     Umweg."
#
#     NetworkManagers eigener Einleser fuehrt diese Zeilen NICHT aus.
#     GEMESSEN an der Zeichenkettentabelle von /usr/lib/libnm.so.0
#     (networkmanager 1.58.0-1): der Parser fuehrt PreUp, PreDown,
#     PostUp, PostDown und SaveConfig als BENANNTE Schluessel - damit
#     sie nicht in seine Meldung "unrecognized line at %s:%zu" laufen -
#     und tut nichts damit. Der Unterschied zwischen "ausfuehren" und
#     "erkennen und liegenlassen" ist der ganze Sicherheitsgewinn.
#
# WAS DAS AN RECHTEN KOSTET - GEMESSEN am 21.08.2026 mit `pkcheck`
#     (`pkcheck` fragt polkitd und fasst NetworkManager nicht an):
#
#         settings.modify.own        rc=0
#         settings.modify.system     rc=0, polkit.result=yes
#         settings.modify.hostname   rc=2, "requires authentication"
#
#     Die dritte Zeile ist die Gegenprobe und der Grund, dem Ergebnis zu
#     trauen: sie traegt in der Regeldatei dasselbe `auth_admin_keep`
#     wie modify.system und verlangt tatsaechlich eine Anmeldung.
#     modify.system verlangt sie nicht - weil das Paket networkmanager
#     SELBST /usr/share/polkit-1/rules.d/org.freedesktop.NetworkManager.rules
#     mitbringt und darin der Gruppe `wheel` an einer oertlichen Konsole
#     ein pauschales YES gibt. ZepOS legt das Konto des Nutzers in genau
#     dieser Gruppe an (archinstall, users[].sudo = true - dieselbe
#     Gruppe, auf die die letzte Zeile von
#     zepos-privileges-config.template zeigt).
#
#     ES KOMMT ALSO KEIN PASSWORTDIALOG. Trotzdem bekommt jede erzeugte
#     Verbindung `connection.permissions user:<Konto>`, aus zwei
#     Gruenden, die von dieser Messung unabhaengig sind: ein Konto OHNE
#     wheel faellt damit auf modify.own (allow_active=yes) statt auf
#     einen Dialog, und die Verbindung gehoert dann diesem Konto statt
#     allen Konten der Maschine.
#
#     UND: KEINE EINZIGE NEUE ZEILE IN /etc/sudoers.d/zepos. IPsec
#     braucht dort heute sieben Cmnd_Alias-Bloecke; WireGuard braucht
#     keinen.
#
# WARUM DER SCHLUESSEL UEBER EINE DATEI UND NICHT UEBER DIE BEFEHLSZEILE
#     `nmcli connection modify <c> wireguard.private-key <schluessel>`
#     waere der kuerzere Weg und ist versperrt: /proc/<pid>/cmdline ist
#     fuer jedes Konto der Maschine lesbar, solange der Prozess laeuft.
#     Aus genau diesem Grund traegt ags-vpn.template seit laengerem
#     einen LEEREN dritten Platz in `connectArgv` - dort stand das
#     Sudo-Passwort.
#
#     `nmcli connection import type wireguard file <datei>` reicht
#     stattdessen einen PFAD, und NetworkManager liest den Schluessel
#     selbst. Die Datei, die wir dafuer hinlegen, ist unsere eigene,
#     aus den Einstellungen zurueckgeschriebene .conf - ohne die
#     Haken-Zeilen, im Laufzeitverzeichnis des Nutzers, 0600, und sie
#     wird danach geloescht.
#
#     Der Preis, ausgesprochen: `import` legt die Verbindung an, BEVOR
#     `connection.permissions` gesetzt werden kann, faellt also fuer
#     diesen einen Schritt unter modify.system. Auf einem ZepOS-Konto
#     (wheel, oertliche Sitzung) ist das nach der Messung oben
#     folgenlos. Auf einem Konto ohne wheel kaeme dort ein
#     polkit-Dialog. Das ist der Tausch: ein moeglicher Dialog fuer ein
#     Konto, das ZepOS so nicht anlegt, gegen einen privaten Schluessel,
#     der NIE in einer Befehlszeile steht. Der Schluessel gewinnt.

WG_KIND = "wireguard"
IPSEC_KIND = "ipsec"
# OpenVPN, seit dem 22.08.2026 die dritte Bauart. Der ganze Teil dazu
# steht weiter unten unter "OpenVPN"; hier steht nur der Name, weil
# vpn_kind() EINE Liste braucht und zwei Listen an zwei Stellen genau
# die Krankheit sind, die der Kopf von src/brand.py beschreibt.
OVPN_KIND = "openvpn"
VPN_KINDS = (IPSEC_KIND, WG_KIND, OVPN_KIND)

# Die Zeilen, die `wg-quick` als Shell ausfuehren wuerde. Sie werden
# NICHT still verworfen: parse_wg_conf() sammelt sie mit ihrer
# Zeilennummer ein, der Aufrufer zeigt sie, und der Befehl endet mit
# einem eigenen Rueckgabewert (WG_IMPORT_REFUSED), damit ein Aufrufer,
# der sie uebergeht, das aktiv tun muss.
WG_HOOK_KEYS = ("PreUp", "PostUp", "PreDown", "PostDown", "SaveConfig")

# [Interface]. `Address`, `DNS`, `MTU` und `Table` kennt nur wg-quick,
# nicht das Kernelmodul - NetworkManager kann sie trotzdem alle, ueber
# ipv4./ipv6.- bzw. wireguard.-Eigenschaften.
WG_INTERFACE_KEYS = ("PrivateKey", "Address", "ListenPort", "DNS", "MTU",
                     "Table", "FwMark")

# [Peer].
WG_PEER_KEYS = ("PublicKey", "PresharedKey", "AllowedIPs", "Endpoint",
                "PersistentKeepalive")

_WG_CANONICAL = {name.lower(): name
                 for name in WG_INTERFACE_KEYS + WG_PEER_KEYS + WG_HOOK_KEYS}


class UnreadableWireGuardConfig(ValueError):
    """Diese .conf wird nicht halb eingelesen.

    Eine Datei, von der die Haelfte ankommt und der Rest still
    verschwindet, ist in einem Netzwerkzeug schlimmer als eine
    Fehlermeldung: was verworfen wurde, ist genau die Zeile, die den
    Verkehr eingegrenzt haette. Dieselbe Haltung, die
    nonblank_entries() weiter oben schon traegt ("refuse rather than
    guess"), nur mit Datei und Zeilennummer, weil der Nutzer die Datei
    vor sich hat und sie reparieren koennen soll.
    """


@dataclass
class WireGuardConf:
    """Was in einer .conf stand - und was davon abgelehnt wurde."""

    interface: dict[str, str]
    peers: list[dict[str, str]]
    # (Zeilennummer, Schluesselname) je Haken-Zeile, in der Reihenfolge
    # der Datei. Leer ist der Normalfall.
    refused: list[tuple[int, str]]


def _wg_strip_comment(line: str) -> str:
    """Alles ab dem ersten `#`, wie wg-quick es liest.

    Ein Base64-Schluessel enthaelt `#` nicht (das Alphabet ist
    A-Z a-z 0-9 + / =), eine Endpunkt-Adresse auch nicht - das
    Abschneiden kann also keinen Wert zerteilen.
    """
    return line.split("#", 1)[0]


def parse_wg_conf(text: str, source: str = "<eingabe>") -> WireGuardConf:
    """Eine wg-quick-.conf, Zeile fuer Zeile, ohne zu raten.

    Der Wert wird am ERSTEN `=` abgetrennt und nicht am letzten: ein
    Base64-Schluessel endet auf `=` oder `==`, und ein `split("=")`
    ueber alle Vorkommen haette aus `PrivateKey = aGVsbG8=` einen
    leeren Schluessel gemacht - eine Verbindung, die sich anlegen laesst
    und nie zustande kommt.

    Gross- und Kleinschreibung ist gleichgueltig (wg-quick liest so),
    gemeldet wird aber immer die kanonische Schreibweise, damit die
    Meldung zu dem passt, was in der Datei stehen sollte.
    """
    conf = WireGuardConf(interface={}, peers=[], refused=[])
    section: str | None = None
    seen_interface = False

    for number, raw in enumerate(text.splitlines(), start=1):
        line = _wg_strip_comment(raw).strip()
        if not line:
            continue

        if line.startswith("[") and line.endswith("]"):
            head = line[1:-1].strip().lower()
            if head == "interface":
                if seen_interface:
                    raise UnreadableWireGuardConfig(
                        f"{source}:{number}: a second [Interface] section - "
                        f"a WireGuard configuration has exactly one")
                seen_interface = True
                section = "interface"
            elif head == "peer":
                conf.peers.append({})
                section = "peer"
            else:
                raise UnreadableWireGuardConfig(
                    f"{source}:{number}: unknown section [{line[1:-1].strip()}]"
                    f" - only [Interface] and [Peer] exist")
            continue

        if "=" not in line:
            raise UnreadableWireGuardConfig(
                f"{source}:{number}: not a `key = value` line: {line!r}")

        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        canonical = _WG_CANONICAL.get(name.lower())

        if canonical is None:
            raise UnreadableWireGuardConfig(
                f"{source}:{number}: unknown key {name!r}. Nothing was "
                f"imported - a configuration that is read by halves is "
                f"worse than one that is refused")

        if section is None:
            raise UnreadableWireGuardConfig(
                f"{source}:{number}: {canonical} stands before any "
                f"[Interface] or [Peer] section")

        if canonical in WG_HOOK_KEYS:
            # Aufgehoben, nicht angewandt und nicht verschwiegen.
            conf.refused.append((number, canonical))
            continue

        allowed = WG_INTERFACE_KEYS if section == "interface" else WG_PEER_KEYS
        if canonical not in allowed:
            raise UnreadableWireGuardConfig(
                f"{source}:{number}: {canonical} does not belong in a "
                f"[{section.capitalize()}] section")

        target = conf.interface if section == "interface" else conf.peers[-1]
        if canonical == "AllowedIPs" and canonical in target:
            # wg-quick erlaubt mehrere AllowedIPs-Zeilen je Gegenstelle
            # und haengt sie aneinander. Die einzige Wiederholung, die
            # kein Fehler ist.
            target[canonical] = f"{target[canonical]},{value}"
            continue
        if canonical in target:
            raise UnreadableWireGuardConfig(
                f"{source}:{number}: {canonical} appears twice in the same "
                f"section")
        target[canonical] = value

    if not seen_interface:
        raise UnreadableWireGuardConfig(
            f"{source}: no [Interface] section - this is not a WireGuard "
            f"configuration")
    return conf


def _wg_list(value: str) -> list[str]:
    """`10.0.0.0/8, 192.168.0.0/16` als Liste, Leeres entfernt."""
    return [piece.strip() for piece in value.replace(" ", ",").split(",")
            if piece.strip()]


def _wg_number(value: str, *, field: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise UnreadableWireGuardConfig(
            f"{field} is not a number: {value!r}") from None


def wireguard_document(conf: WireGuardConf, *, private_key_file: str = "",
                       public_key: str = "",
                       preshared_key_files: Sequence[str] | None = None,
                       ) -> dict[str, Any]:
    """Der Abschnitt, der in user-settings.json darf - OHNE Geheimnisse.

    Der private Schluessel und die Gegenstellen-PSKs stehen hier
    ABSICHTLICH nicht. Dieses Dokument wird vom Stil-Erzeuger gelesen,
    von `zepos-settings` ausgegeben und vom Doktor angefasst; ein
    Geheimnis darin waere ein Geheimnis in vier Programmen. Getragen
    wird nur der DATEINAME, unter dem der Schluessel liegt - siehe
    write_wireguard_secret().
    """
    files = list(preshared_key_files or [])
    peers = []
    for index, peer in enumerate(conf.peers):
        peers.append({
            "public_key": peer.get("PublicKey", ""),
            "endpoint": peer.get("Endpoint", ""),
            "allowed_ips": _wg_list(peer.get("AllowedIPs", "")),
            "keepalive": (_wg_number(peer["PersistentKeepalive"],
                                     field="PersistentKeepalive")
                          if peer.get("PersistentKeepalive") else 0),
            "preshared_key_file": files[index] if index < len(files) else "",
        })

    interface = conf.interface
    return {
        "addresses": _wg_list(interface.get("Address", "")),
        "listen_port": (_wg_number(interface["ListenPort"], field="ListenPort")
                        if interface.get("ListenPort") else 0),
        "mtu": (_wg_number(interface["MTU"], field="MTU")
                if interface.get("MTU") else 0),
        "private_key_file": private_key_file,
        "public_key": public_key,
        "peers": peers,
    }


def wireguard_full_tunnel(document: dict[str, Any] | None) -> list[str]:
    """Deckt DIESE WireGuard-Verbindung den ganzen Adressraum ab?

    Ueber ALLE Gegenstellen zusammen und nicht je Gegenstelle: was in
    die Routentabelle kommt, ist die Vereinigung ihrer AllowedIPs, und
    zwei Gegenstellen mit je einer Haelfte sind zusammen ein Volltunnel,
    den keine von beiden allein waere.

    Arbeitet auf dem EINSTELLUNGSDOKUMENT und nicht auf der .conf, damit
    dieselbe Antwort beim Einlesen und beim Anzeigen einer bestehenden
    Konfiguration herauskommt - eine Erkennung, die nur beim Import
    laeuft, beschreibt einen Zustand von damals.
    """
    networks: list[str] = []
    for peer in (document or {}).get("peers") or []:
        if not isinstance(peer, dict):
            continue
        networks.extend(nonblank_entries(peer.get("allowed_ips"),
                                         setting="wireguard.peers.allowed_ips"))
    return full_tunnel_families(networks,
                                setting="wireguard.peers.allowed_ips")


def wireguard_dns(conf: WireGuardConf) -> dict[str, Any]:
    """Was `DNS =` aus der Datei in den bestehenden DNS-Reiter bringt.

    Ein Eintrag, der keine Adresse ist, ist bei wg-quick eine
    Suchdomaene. Beides landet dort, wo ZepOS es fuer IPsec schon fuehrt
    (vpn.dns), damit es EINEN DNS-Reiter gibt und nicht zwei.
    """
    servers, domains = [], []
    for entry in _wg_list(conf.interface.get("DNS", "")):
        (servers if re.fullmatch(r"[0-9a-fA-F:.]+", entry)
         else domains).append(entry)
    return {"servers": servers, "search_domain": " ".join(domains)}


def wireguard_conf_text(document: dict[str, Any], private_key: str,
                        dns: dict[str, Any] | None = None,
                        preshared_keys: Sequence[str] | None = None) -> str:
    """Unsere Einstellungen zurueck in wg-quick-Syntax.

    Das ist die Datei, die `nmcli connection import` bekommt - der
    einzige Weg, auf dem der private Schluessel NetworkManager erreicht,
    ohne durch eine Befehlszeile zu gehen (siehe den Abschnitt oben).

    Sie traegt KEINE Haken-Zeile. Was aus einer fremden Datei an
    PreUp/PostUp kam, ist beim Einlesen abgelehnt worden und kommt hier
    nicht wieder heraus - der Text, den NetworkManager zu sehen bekommt,
    ist unserer und nicht der fremde.
    """
    secrets = list(preshared_keys or [])
    lines = ["[Interface]", f"PrivateKey = {private_key}"]
    if document.get("addresses"):
        lines.append("Address = " + ", ".join(document["addresses"]))
    if document.get("listen_port"):
        lines.append(f"ListenPort = {document['listen_port']}")
    if document.get("mtu"):
        lines.append(f"MTU = {document['mtu']}")
    entries = list((dns or {}).get("servers") or [])
    domain = str((dns or {}).get("search_domain") or "").strip()
    if domain:
        entries.extend(domain.split())
    if entries:
        lines.append("DNS = " + ", ".join(entries))

    for index, peer in enumerate(document.get("peers") or []):
        lines.extend(["", "[Peer]", f"PublicKey = {peer.get('public_key', '')}"])
        if index < len(secrets) and secrets[index]:
            lines.append(f"PresharedKey = {secrets[index]}")
        if peer.get("allowed_ips"):
            lines.append("AllowedIPs = " + ", ".join(peer["allowed_ips"]))
        if peer.get("endpoint"):
            lines.append(f"Endpoint = {peer['endpoint']}")
        if peer.get("keepalive"):
            lines.append(f"PersistentKeepalive = {peer['keepalive']}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------
# Geheimnisse: 0600 vom ersten Byte, nie in einer Befehlszeile
# --------------------------------------------------------------------

def wireguard_key_dir(config_home: str | None = None) -> Path:
    root = (config_home or os.environ.get("XDG_CONFIG_HOME")
            or f"{os.path.expanduser('~')}/.config")
    return Path(root) / "wireguard"


def write_wireguard_secret(name: str, secret: str,
                           config_home: str | None = None) -> Path:
    """Einen Schluessel ablegen - 0600 vom ersten Byte an.

    `os.open` mit O_CREAT|O_EXCL|O_WRONLY und mode=0o600 statt
    open()+chmod: `echo > f; chmod 600 f` endet bei 0600 und war
    dazwischen fuer alle lesbar, und genau diesen Zwischenzustand misst
    tests/src/test_vpn_secrets.py - von innerhalb der Stubs, mit
    `umask 000` im Kind. O_EXCL heisst ausserdem, dass uns die Datei
    gehoert, die wir anlegen: eine vorhandene Datei oder ein Symlink an
    dieser Stelle laesst das Oeffnen scheitern, statt durch ihn hindurch
    zu schreiben. Dieselbe Begruendung wie settings.save().

    Das Verzeichnis bekommt 0700 - anders als
    ~/.config/strongswan, das 0755 traegt und dessen einzelne Datei
    allein den Schutz leistet (GEMESSEN am 21.08.2026 per `stat`:
    `drwxr-xr-x` fuer das Verzeichnis, `-rw-------` fuer psk). Hier
    liegen mehrere Schluessel, und ihre blossen NAMEN verraten schon,
    welche Gegenstellen es gibt.
    """
    return write_private_secret(wireguard_key_dir(config_home), name, secret)


def write_private_secret(directory: Path, name: str, secret: str) -> Path:
    """Der EINE Schreiber fuer jedes Geheimnis auf Platte.

    Herausgezogen am 22.08.2026, als OpenVPN als dritte Bauart dazukam:
    seine bis zu vier Zertifikats- und Schluesseldateien brauchen Byte
    fuer Byte dieselbe Sorgfalt wie ein WireGuard-Schluessel, und eine
    zweite Kopie dieser zehn Zeilen waere die Stelle, an der beim
    naechsten Mal eine von beiden ihr O_EXCL verliert. Die Begruendung
    fuer jede einzelne Zeile steht im Kopf von write_wireguard_secret().
    """
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    target = directory / name
    # Neu anlegen statt ueberschreiben, damit ein einmal zu weit
    # geoeffneter Speicher nicht zu weit geoeffnet bleibt - dasselbe,
    # was Gio.FileCreateFlags.REPLACE_DESTINATION im Einstellungsfenster
    # tut.
    target.unlink(missing_ok=True)
    handle = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(handle, (secret.strip() + "\n").encode("utf-8"))
    finally:
        os.close(handle)
    return target


def read_wireguard_secret(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def generate_wireguard_key(runner: Runner = subprocess.run) -> str:
    """`wg genkey`. Der Schluessel kommt ueber die AUSGABE, nie als Argument."""
    completed = runner(["wg", "genkey"], capture_output=True, text=True,
                       timeout=5)
    if completed.returncode != 0:
        raise UnreadableWireGuardConfig(
            "wg genkey failed - is wireguard-tools installed? "
            f"{(completed.stderr or '').strip()}")
    return (completed.stdout or "").strip()


def public_wireguard_key(private_key: str,
                         runner: Runner = subprocess.run) -> str:
    """`wg pubkey`, mit dem Schluessel auf der EINGABE.

    Nicht als Argument: /proc/<pid>/cmdline ist fuer jedes Konto der
    Maschine lesbar, solange der Prozess laeuft, und dieser hier laeuft
    nur Millisekunden - aber ein Geheimnis, das nur kurz sichtbar ist,
    ist ein sichtbares Geheimnis. Dieselbe Regel, aus der das
    Sudo-Passwort aus vpn-connect.sh verschwunden ist.
    """
    try:
        completed = runner(["wg", "pubkey"], input=private_key.strip() + "\n",
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        # Ohne wireguard-tools gibt es keinen oeffentlichen Schluessel zu
        # zeigen - aber die eingelesene Datei ist deswegen nicht
        # unbrauchbar, und ein Absturz beim Einlesen waere eine harte
        # Antwort auf ein weiches Problem. Das Feld bleibt leer, das
        # Fenster zeigt es leer, und der Schluessel ist trotzdem
        # gespeichert.
        return ""
    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


# --------------------------------------------------------------------
# OpenVPN - die dritte Bauart
# --------------------------------------------------------------------
#
# BESTELLT am 22.08.2026: "ausserdem will ich, dass wir bei vpn auch
# openvpn format unterstuetzen - das brauchen wir auch".
#
# DIE GEFAHR IST GROESSER ALS BEI WIREGUARD, UND SIE IST GEMESSEN
#     `wg-quick` fuehrt fuenf Zeilen als Root aus. OpenVPN fuehrt
#     ACHTZEHN aus, und eine davon (`plugin`) laedt eine gemeinsame
#     Bibliothek in den eigenen Prozess, ohne dass ueberhaupt ein
#     Skript im Spiel waere. Die Liste steht in OVPN_EXECUTING und
#     stammt aus `openvpn --help` und der Handbuchseite openvpn(8) der
#     INSTALLIERTEN Fassung 2.7.6 - abgezaehlt am 22.08.2026, nicht aus
#     dem Gedaechtnis.
#
# WAS NETWORKMANAGER DAMIT MACHT - ZWEIMAL GEMESSEN, EINMAL WIDERLEGT
#     Der WireGuard-Teil oben hat an der Zeichenkettentabelle von
#     libnm.so.0 gemessen. Hier taugt diese Methode NICHT: `up` und
#     `key` sind Endstuecke von `group` und `static-key`, und der
#     Uebersetzer legt solche Zeichenketten uebereinander. `grep -cx up`
#     antwortet 0, obwohl `group` in der Tabelle steht - ein Fehlen ist
#     dort also kein Beweis. Blind dieselbe Methode zu wiederholen
#     haette hier ein falsches Ergebnis geliefert.
#
#     Stattdessen wurde der Einleser AUSGEFUEHRT: als reiner
#     Bibliotheksaufruf (NM.VpnEditorPlugin.import_() ueber
#     python-gobject), ohne NM.Client, also ohne eine einzige
#     D-Bus-Nachricht an den NetworkManager, gegen eine Datei in einem
#     Wegwerfverzeichnis mit umgebogenem XDG_DATA_HOME. Vorgelegt:
#     script-security, up, down, route-up, ipchange, tls-verify und
#     plugin. Angekommen: KEINE davon. Gemeldet: NICHTS - Rueckgabewert
#     0, keine Warnung, keine Zeilennummer. Dasselbe bei einer frei
#     erfundenen Direktive, und `config <datei>` wird nicht verfolgt.
#
#     ZWEITE SPERRE, unabhaengig von der ersten: /usr/lib/nm-openvpn-service
#     baut die Befehlszeile fuer /usr/sbin/openvpn aus einer
#     GESCHLOSSENEN Liste benannter Eigenschaften. `--config` steht
#     nicht darin (`grep -cx -- --config` = 0) - OpenVPN bekommt unter
#     NetworkManager also NIE eine .ovpn zu lesen. Ebenso fehlen
#     --plugin, --down, --route-up, --ipchange, --client-connect,
#     --tls-verify, --auth-user-pass-verify, --dns-updown, --iproute
#     und --setenv. Das einzige --up ist NMs eigener Helfer
#     (/usr/lib/nm-openvpn-service-openvpn-helper), und eine
#     durchgerutschte Eigenschaft wuerde nicht ignoriert, sondern
#     abgelehnt ("property %s invalid or not supported").
#
# WARUM ES TROTZDEM EINEN EIGENEN EINLESER GIBT
#     Weil NMs Einleser SCHWEIGT. Der Nutzer legt die Datei seines
#     Anbieters hin, alles scheint zu klappen, und dass die Zeile, die
#     den Verkehr eingegrenzt haette, verschwunden ist, erfaehrt er
#     nie. Genau diese Haltung schliesst nonblank_entries() weiter oben
#     aus ("refuse rather than guess"). Hier wird deshalb benannt,
#     abgelehnt und mit einem eigenen Rueckgabewert geendet - und die
#     .ovpn, die NetworkManager zu sehen bekommt, ist AUS UNSEREN
#     EINSTELLUNGEN gebaut, nie die fremde weitergereicht.
#
# WO DIE GEHEIMNISSE LIEGEN
#     Eine .ovpn traegt Zertifikate und den privaten Schluessel im
#     KLARTEXT in der Datei (<ca>, <cert>, <key>, <tls-auth>,
#     <tls-crypt>). NetworkManagers Einleser packt sie selbst aus, nach
#     $XDG_DATA_HOME/networkmanagement/certificates/nm-openvpn/ -
#     GEMESSEN am 22.08.2026 mit umask 022: die Dateien 0600, das
#     VERZEICHNIS aber 0755. Wir packen darum selbst aus, nach
#     ~/.config/openvpn: Dateien 0600 vom ersten Byte, Verzeichnis
#     0700, ueber write_private_secret(). In user-settings.json stehen
#     nur DATEINAMEN.
#
#     Anders als bei WireGuard uebernimmt NetworkManager den privaten
#     Schluessel NICHT in sein Verbindungsprofil - die Verbindung traegt
#     den PFAD. Unsere Kopie bleibt damit die einzige Quelle.
#
# WARUM DAS PASSWORT UEBER EINE DATEI GEHT UND NICHT UEBER argv
#     Die IPsec-Seite reicht Nutzername, Passwort und Einmal-Token heute
#     als ARGUMENTE an vpn-connect.sh ($1, $2, $4). /proc/<pid>/cmdline
#     ist fuer jedes Konto der Maschine lesbar - das wird hier nicht
#     wiederholt. `nmcli connection up <name> passwd-file <datei>`
#     nimmt eine Datei mit `vpn.secrets.<name>:<wert>`-Zeilen
#     (GEMESSEN aus `nmcli connection up --help` und nmcli(1)); sie
#     liegt 0600 im Laufzeitverzeichnis und wird danach geloescht.
#
# WAS DER WAECHTER KANN UND WAS NICHT - GEMESSEN am 22.08.2026
#     NMs Einleser setzt aus `auth-user-pass` selbstaendig
#     `password-flags = 1` (agentengehalten): das Passwort wird NICHT
#     gespeichert und bei jedem Hochfahren neu erfragt. Eine reine
#     Zertifikatsverbindung (`connection-type = tls`) bekommt dagegen
#     GAR KEINE Geheimnisflagge - gemessen an vier eingelesenen
#     Dateien (nur Zertifikate / Zertifikate mit verschluesseltem
#     Schluessel / nur Anmeldung / beides).
#
#     Folge, und sie steht auch in der Oberflaeche: eine reine
#     Zertifikatsverbindung mit UNverschluesseltem Schluessel stellt
#     der Waechter unbeaufsichtigt wieder her; eine mit Nutzername und
#     Passwort - und ebenso eine mit verschluesseltem Schluessel, fuer
#     die nm-openvpn-service `cert-pass` erfragt - nicht. Das ist ein
#     Unterschied zur IPsec-Seite, wo strongSwan das Geheimnis in
#     seiner eigenen Konfiguration haelt, und er wird angesagt statt
#     spaeter entdeckt.

# DIE ACHTZEHN, DIE EINEN BEFEHL AUSFUEHREN.
#
#     Abgezaehlt am 22.08.2026 aus `openvpn --help` und openvpn(8) der
#     Fassung 2.7.6. `script-security` steht dabei, obwohl es selbst
#     nichts startet: es ist der Schalter, der die anderen siebzehn
#     ueberhaupt erst freigibt, und eine Datei, die ihn setzt, will
#     genau das.
OVPN_EXECUTING = (
    "up", "down", "down-pre", "up-restart",
    "route-up", "route-pre-down", "ipchange",
    "client-connect", "client-disconnect", "client-crresponse",
    "learn-address", "tls-verify", "auth-user-pass-verify",
    "tls-crypt-v2-verify", "dns-updown", "iproute", "plugin",
    "script-security",
)

# DIE, DIE AUSFUEHRUNG WEITERREICHEN, OHNE SELBST ZU STARTEN.
#
#     `config` zieht eine WEITERE Datei herein und mit ihr die ganze
#     Liste darueber - deshalb steht es hier und wird nicht verfolgt.
#     `setenv` fuellt die Umgebung, in der die achtzehn laufen. Die
#     management-Familie uebergibt die Steuerung von openvpn an einen
#     fremden Prozess ueber einen Sockel. Und `daemon`, `cd`, `chroot`,
#     `tmp-dir`, `tls-export-cert` und `client-config-dir` verschieben,
#     WO und ALS WER alles laeuft bzw. wohin openvpn schreiben darf.
OVPN_ENABLING = (
    "config", "setenv", "setenv-safe",
    "management", "management-client", "management-client-auth",
    "management-client-user", "management-client-group",
    "management-client-pf", "management-query-passwords",
    "management-query-proxy", "management-query-remote",
    "management-external-key", "management-external-cert",
    "management-up-down", "management-hold", "management-signal",
    "management-forget-disconnect", "management-log-cache",
    "daemon", "cd", "chroot", "tmp-dir",
    "tls-export-cert", "client-config-dir",
)

OVPN_REFUSED_KEYS = OVPN_EXECUTING + OVPN_ENABLING

# Bloecke, die als Datei bei uns landen. Alles davon ist PEM-Text.
#
#     `key-direction` gehoert begrifflich zu tls-auth und wird als
#     eigene Direktive gelesen; die Datei selbst traegt es nicht.
OVPN_BLOB_FILES = {
    "ca": "ca.pem",
    "cert": "cert.pem",
    "key": "key.pem",
    "tls-auth": "tls-auth.key",
    "tls-crypt": "tls-crypt.key",
    "tls-crypt-v2": "tls-crypt-v2.key",
    "extra-certs": "extra-certs.pem",
    "crl-verify": "crl.pem",
}

# Bloecke, die es gibt, die aber NICHT als eingebetteter Text bei uns
# ankommen duerfen.
#
#     <auth-user-pass> traegt Nutzername und Passwort im Klartext. Es
#     abzulegen hiesse, ein Passwort auf die Platte zu schreiben, das
#     heute nirgends auf der Platte steht - schlechter als der Zustand
#     vorher, und darum abgelehnt statt uebernommen. Getippt wird es auf
#     der VPN-Seite, und von dort geht es ueber passwd-file.
#
#     <pkcs12> und <secret> sind base64 bzw. eine statische
#     Schluesseldatei; beide gehoeren als PFAD in die Datei, nicht als
#     Block. <dh> ist serverseitig und hat in einer Client-Datei nichts
#     zu suchen.
OVPN_BLOB_REFUSED = {
    "auth-user-pass":
        "it carries a username and password in clear text - type them on "
        "the VPN page instead, they never touch the disk",
    "pkcs12": "a PKCS#12 block is base64-encoded binary - point at the "
              ".p12 file instead",
    "secret": "static key mode is not a client configuration - point at "
              "the key file instead",
    "dh": "Diffie-Hellman parameters are server-side",
    "peer-fingerprint": "peer fingerprints are not carried by "
                        "NetworkManager's OpenVPN plugin",
    "verify-hash": "certificate hash pinning is not carried by "
                   "NetworkManager's OpenVPN plugin",
    "http-proxy-user-pass": "it carries proxy credentials in clear text",
    "auth-gen-token-secret": "it is a server-side token secret",
}

OVPN_INLINE_TAGS = tuple(OVPN_BLOB_FILES) + tuple(OVPN_BLOB_REFUSED)

# Direktiven, die wir in EIGENE Einstellungsfelder uebernehmen und im
# Fenster zeigen.
OVPN_FIRST_CLASS = (
    "remote", "port", "rport", "proto", "dev", "dev-type",
    "auth-user-pass", "remote-cert-tls", "cipher", "auth",
    "key-direction", "comp-lzo", "tun-mtu", "tunnel-mtu", "reneg-sec",
    "pkcs12",
) + tuple(OVPN_BLOB_FILES)

# Direktiven, die wir MITNEHMEN, ohne ein eigenes Feld dafuer zu bauen.
#
#     Sie landen als Paar (Name, Argumente) in `openvpn.extra` und
#     werden von ovpn_conf_text() woertlich wieder ausgegeben, damit die
#     Verbindung das aushandelt, was der Anbieter vorgesehen hat. Das
#     ist eine ERLAUBNISLISTE und keine Durchreiche: was nicht hier
#     steht, kommt nicht hindurch, und die achtzehn oben sind lange
#     vorher abgelehnt.
#
#     Achtzehn Bedienelemente fuer Werte, die niemand von Hand aendert,
#     waeren ausserdem genau die Breitenrechnung, die dieses Fenster
#     schon einmal um 42 Punkte gesprengt hat.
OVPN_CARRIED_EXTRA = (
    "data-ciphers", "data-ciphers-fallback", "tls-cipher",
    "tls-version-min", "tls-version-max", "ns-cert-type",
    "verify-x509-name", "tls-remote", "remote-cert-ku", "remote-cert-eku",
    "compress", "allow-compression", "keysize", "mssfix", "fragment",
    "mtu-disc", "keepalive", "ping", "ping-exit", "ping-restart",
    "connect-timeout", "server-poll-timeout", "float", "max-routes",
    "remote-random", "remote-random-hostname", "push-peer-info",
    "tun-ipv6", "allow-pull-fqdn", "route-nopull", "redirect-gateway",
    "http-proxy", "http-proxy-retry", "socks-proxy", "socks-proxy-retry",
    "static-challenge", "auth-retry", "auth-token",
)

# Direktiven, die es gibt, die aber nichts an der Verbindung aendern,
# die NetworkManager herstellt - er setzt sein eigenes Gegenstueck.
#
#     Sie werden trotzdem GEMELDET (als `ignored`, ohne eigenen
#     Rueckgabewert), weil "still verworfen" genau der Vorwurf ist, den
#     dieser Einleser gegen NetworkManagers eigenen erhebt. Der
#     Unterschied zu OVPN_REFUSED_KEYS ist die Schwere: hier aendert
#     sich nichts am Verkehr, dort haette etwas ausgefuehrt werden
#     koennen.
OVPN_IGNORED_KEYS = (
    "client", "tls-client", "pull", "nobind", "persist-key",
    "persist-tun", "persist-local-ip", "persist-remote-ip",
    "resolv-retry", "verb", "mute", "mute-replay-warnings",
    "explicit-exit-notify", "auth-nocache", "topology", "user", "group",
    "nice", "log", "log-append", "status", "writepid", "syslog",
    "disable-occ", "ifconfig-nowarn", "ncp-disable", "dh",
    "allow-recursive-routing", "askpass", "route-delay", "route-metric",
    "ignore-unknown-option", "machine-readable-output", "suppress-timestamps",
    "block-outside-dns", "register-dns", "ip-win32", "route-method",
    "win-sys", "pause-exit", "service", "dhcp-release", "dhcp-renew",
    "show-net-up", "allow-nonadmin", "tap-sleep", "windows-driver",
)


class UnreadableOpenVpnConfig(ValueError):
    """Diese .ovpn wird nicht halb eingelesen.

    Dieselbe Haltung wie UnreadableWireGuardConfig, und aus demselben
    Grund: was still verschwindet, ist genau die Zeile, die den Verkehr
    eingegrenzt haette. Bei OpenVPN kommt dazu, dass NetworkManagers
    eigener Einleser GENAU DAS TUT (gemessen, siehe oben) - eine
    Fehlermeldung mit Datei und Zeilennummer ist hier also nicht nur
    besser als Schweigen, sie ist der ganze Unterschied.
    """


@dataclass
class OpenVpnConf:
    """Was in einer .ovpn stand - und was davon abgelehnt wurde."""

    # (Zeilennummer, Direktive, Argumente) in der Reihenfolge der Datei.
    directives: list[tuple[int, str, list[str]]]
    # Eingebettete Bloecke, Name -> Text, ohne die <tag>-Zeilen.
    blobs: dict[str, str]
    # (Zeilennummer, Name) je ausfuehrender oder ausfuehrung-
    # ermoeglichender Zeile. Leer ist der Normalfall.
    refused: list[tuple[int, str]]
    # (Zeilennummer, Name) je bekannter, aber folgenloser Zeile.
    ignored: list[tuple[int, str]]


def _ovpn_tokens(line: str, *, source: str, number: int) -> list[str]:
    """Eine Zeile in Direktive und Argumente zerlegen.

    OpenVPN kennt einfache und doppelte Anfuehrungszeichen und
    Rueckstrich-Maskierung (openvpn(8), Abschnitt OPTIONS: "OpenVPN 2.0
    and higher performs backslash-based shell escaping for characters
    not in single quotations"). Ein Pfad mit Leerzeichen steht in
    Anfuehrungszeichen, und ein `split()` haette daraus zwei Argumente
    gemacht - also einen Zertifikatspfad, den es nicht gibt.

    KOMMENTARE WERDEN NICHT MITTEN IN DER ZEILE ABGESCHNITTEN, anders
    als bei wg-quick: openvpn(8) sagt ausdruecklich `"#" or ";"
    characters IN THE FIRST COLUMN can be used to denote comments`.
    Ein `#` in einem Zertifikatsnamen oder in einem Passwortfeld ist
    also Inhalt, und wer es abschneidet, zerteilt einen Wert.
    """
    tokens: list[str] = []
    current = ""
    started = False
    quote = ""
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if char == "\\" and quote == '"' and index + 1 < len(line):
                index += 1
                current += line[index]
            elif char == quote:
                quote = ""
            else:
                current += char
        elif char in "\"'":
            quote = char
            started = True
        elif char == "\\" and index + 1 < len(line):
            index += 1
            current += line[index]
            started = True
        elif char.isspace():
            if started:
                tokens.append(current)
            current, started = "", False
        else:
            current += char
            started = True
        index += 1
    if quote:
        raise UnreadableOpenVpnConfig(
            f"{source}:{number}: unterminated {quote} quote")
    if started:
        tokens.append(current)
    return tokens


def parse_ovpn(text: str, source: str = "<eingabe>") -> OpenVpnConf:
    """Eine .ovpn, Zeile fuer Zeile, ohne zu raten.

    Vier Ausgaenge, und jeder ist sichtbar:

      * eine ausfuehrende Direktive wird BENANNT abgelehnt und faehrt
        mit Zeilennummer in `refused` - der Aufrufer endet dann mit
        OVPN_IMPORT_REFUSED statt mit 0;
      * eine bekannte, folgenlose Direktive faehrt in `ignored`;
      * eine getragene faehrt in `directives`;
      * alles andere BRICHT AB, mit Datei, Zeile und Namen.
    """
    conf = OpenVpnConf(directives=[], blobs={}, refused=[], ignored=[])
    tag = ""
    tag_line = 0
    collected: list[str] = []

    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()

        if tag:
            if stripped == f"</{tag}>":
                if tag in conf.blobs:
                    raise UnreadableOpenVpnConfig(
                        f"{source}:{tag_line}: <{tag}> appears twice")
                conf.blobs[tag] = "\n".join(collected).strip() + "\n"
                tag, collected = "", []
            else:
                collected.append(raw.rstrip())
            continue

        if not stripped:
            continue
        # Nur in der ersten Spalte, siehe _ovpn_tokens().
        if stripped[0] in "#;":
            continue

        if stripped.startswith("<") and stripped.endswith(">"):
            name = stripped[1:-1].strip()
            if name.startswith("/"):
                raise UnreadableOpenVpnConfig(
                    f"{source}:{number}: {stripped} closes a block that was "
                    f"never opened")
            if name not in OVPN_INLINE_TAGS:
                raise UnreadableOpenVpnConfig(
                    f"{source}:{number}: unknown inline block <{name}>. "
                    f"Nothing was imported - a configuration that is read by "
                    f"halves is worse than one that is refused")
            if name in OVPN_BLOB_REFUSED:
                raise UnreadableOpenVpnConfig(
                    f"{source}:{number}: <{name}> was NOT taken over - "
                    f"{OVPN_BLOB_REFUSED[name]}")
            tag, tag_line, collected = name, number, []
            continue

        tokens = _ovpn_tokens(stripped, source=source, number=number)
        if not tokens:
            continue
        # Eine fuehrende `--` ist erlaubt: viele Anbieter schreiben ihre
        # Dateien aus einer Befehlszeile heraus.
        name = tokens[0][2:] if tokens[0].startswith("--") else tokens[0]
        name = name.lower()
        arguments = tokens[1:]

        if name in OVPN_REFUSED_KEYS:
            conf.refused.append((number, name))
            continue
        if name in OVPN_IGNORED_KEYS:
            conf.ignored.append((number, name))
            continue
        if name in OVPN_FIRST_CLASS or name in OVPN_CARRIED_EXTRA \
                or name in ("route", "dhcp-option"):
            conf.directives.append((number, name, arguments))
            continue

        raise UnreadableOpenVpnConfig(
            f"{source}:{number}: unknown directive {name!r}. Nothing was "
            f"imported - a configuration that is read by halves is worse "
            f"than one that is refused")

    if tag:
        raise UnreadableOpenVpnConfig(
            f"{source}:{tag_line}: <{tag}> is never closed")
    return conf


def openvpn_key_dir(config_home: str | None = None) -> Path:
    """~/.config/openvpn - 0700, siehe write_private_secret().

    Nicht /etc/openvpn: dort liegen Systemverbindungen, dort braucht das
    Schreiben Rechte, und der Nutzer soll seine eigenen Zertifikate
    ansehen und loeschen koennen, ohne dafuer jemanden zu fragen.
    """
    root = (config_home or os.environ.get("XDG_CONFIG_HOME")
            or f"{os.path.expanduser('~')}/.config")
    return Path(root) / "openvpn"


def store_openvpn_blobs(conf: OpenVpnConf, name: str,
                        config_home: str | None = None) -> dict[str, str]:
    """Die eingebetteten Bloecke auspacken - 0600, Verzeichnis 0700.

    Gibt zurueck, unter welchem DATEINAMEN was liegt. Nur diese Namen
    stehen spaeter in user-settings.json; der Inhalt steht dort nie.
    """
    stored: dict[str, str] = {}
    for tag, suffix in OVPN_BLOB_FILES.items():
        text = conf.blobs.get(tag)
        if not text:
            continue
        stored[tag] = write_private_secret(openvpn_key_dir(config_home),
                                           f"{name}-{suffix}", text).name
    return stored


def _ovpn_first(conf: OpenVpnConf, name: str) -> list[str]:
    for _number, key, arguments in conf.directives:
        if key == name:
            return arguments
    return []


def _ovpn_route_cidr(arguments: Sequence[str]) -> str:
    """`route 10.0.0.0 255.0.0.0` als `10.0.0.0/8`.

    Die Netzliste dieses Projekts fuehrt CIDR - `routed_networks` treibt
    bei IPsec die Child-SAs und bei WireGuard die AllowedIPs, und eine
    vierte Schreibweise waere eine vierte Stelle, an der etwas anderes
    stehen kann. Eine Maske, die keine ist, faellt weg statt zu raten.
    """
    if not arguments:
        return ""
    network = arguments[0]
    mask = arguments[1] if len(arguments) > 1 else "255.255.255.255"
    if mask in ("vpn_gateway", "net_gateway", "remote_host"):
        mask = "255.255.255.255"
    try:
        return str(ipaddress.ip_network(f"{network}/{mask}", strict=False))
    except ValueError:
        return ""


def openvpn_document(conf: OpenVpnConf, *, stored_files: dict[str, str] | None = None,
                     ) -> dict[str, Any]:
    """Der Abschnitt, der in user-settings.json darf - OHNE Geheimnisse.

    Getragen werden Dateinamen, kein Zertifikat und kein Schluessel.
    Dieselbe Trennung wie bei wireguard_document(), aus demselben Grund:
    dieses Dokument liest der Stil-Erzeuger, gibt `zepos-settings` aus
    und fasst der Doktor an.
    """
    files = dict(stored_files or {})
    for _number, key, arguments in conf.directives:
        # Ein PFAD in der Datei (statt eines Blocks) bleibt ein Pfad -
        # er gehoert dem Nutzer, und ihn zu kopieren hiesse, ein
        # Geheimnis zu verdoppeln.
        if key in OVPN_BLOB_FILES and key not in files and arguments:
            files[key] = arguments[0]

    remote = _ovpn_first(conf, "remote")
    port = ""
    proto = ""
    if len(remote) > 1:
        port = remote[1]
    if len(remote) > 2:
        proto = remote[2]
    for key in ("port", "rport"):
        arguments = _ovpn_first(conf, key)
        if arguments:
            port = arguments[0]
    arguments = _ovpn_first(conf, "proto")
    if arguments:
        proto = arguments[0]

    device = _ovpn_first(conf, "dev")
    device_type = _ovpn_first(conf, "dev-type")

    has_certificate = bool(files.get("cert") and files.get("key")) \
        or bool(files.get("pkcs12"))
    wants_login = any(key == "auth-user-pass"
                      for _number, key, _arguments in conf.directives)
    if has_certificate and wants_login:
        connection_type = "password-tls"
    elif has_certificate:
        connection_type = "tls"
    elif wants_login:
        connection_type = "password"
    else:
        # Weder Zertifikat noch Anmeldung: NetworkManagers Einleser
        # verlangt mindestens ein --ca, und ohne beides gibt es nichts
        # auszuweisen. "tls" ist die Antwort, die das Fenster dann als
        # unvollstaendig zeigt, statt hier zu raten.
        connection_type = "tls"

    extra: list[list[str]] = []
    for _number, key, arguments in conf.directives:
        if key in OVPN_CARRIED_EXTRA:
            extra.append([key, *arguments])

    single = {}
    for key, field in (("cipher", "cipher"), ("auth", "auth"),
                       ("remote-cert-tls", "remote_cert_tls"),
                       ("comp-lzo", "comp_lzo")):
        arguments = _ovpn_first(conf, key)
        if arguments or key in ("comp-lzo",) and any(
                item == key for _n, item, _a in conf.directives):
            single[field] = arguments[0] if arguments else "yes"

    mtu = _ovpn_first(conf, "tun-mtu") or _ovpn_first(conf, "tunnel-mtu")
    reneg = _ovpn_first(conf, "reneg-sec")
    direction = _ovpn_first(conf, "key-direction")

    return {
        "remote": remote[0] if remote else "",
        "port": int(port) if str(port).isdigit() else 0,
        "proto": proto or "udp",
        "dev": device[0] if device else "tun",
        "dev_type": device_type[0] if device_type else "",
        "connection_type": connection_type,
        "username": "",
        "remote_cert_tls": single.get("remote_cert_tls", ""),
        "cipher": single.get("cipher", ""),
        "auth": single.get("auth", ""),
        "comp_lzo": single.get("comp_lzo", ""),
        "tunnel_mtu": int(mtu[0]) if mtu and mtu[0].isdigit() else 0,
        "reneg_seconds": int(reneg[0]) if reneg and reneg[0].isdigit() else -1,
        "ta_dir": direction[0] if direction else "",
        "ca_file": files.get("ca", ""),
        "cert_file": files.get("cert", ""),
        "key_file": files.get("key", ""),
        "tls_auth_file": files.get("tls-auth", ""),
        "tls_crypt_file": files.get("tls-crypt", ""),
        "pkcs12_file": files.get("pkcs12", ""),
        "extra": extra,
    }


def openvpn_dns(conf: OpenVpnConf) -> dict[str, Any]:
    """Was `dhcp-option DNS/DOMAIN` in den BESTEHENDEN DNS-Reiter bringt.

    Denselben Reiter benutzt WireGuards `DNS =` und benutzen die
    IPsec-Server. Ein zweiter waere derselbe Reiter zweimal.
    """
    servers, domains = [], []
    for _number, key, arguments in conf.directives:
        if key != "dhcp-option" or len(arguments) < 2:
            continue
        head = arguments[0].upper()
        if head == "DNS":
            servers.append(arguments[1])
        elif head in ("DOMAIN", "DOMAIN-SEARCH", "ADAPTER_DOMAIN_SUFFIX"):
            domains.append(arguments[1])
    return {"servers": servers, "search_domain": " ".join(domains)}


def openvpn_routes(conf: OpenVpnConf) -> list[str]:
    """`route`-Zeilen in die BESTEHENDE Netzliste (routed_networks)."""
    networks = []
    for _number, key, arguments in conf.directives:
        if key != "route":
            continue
        cidr = _ovpn_route_cidr(arguments)
        if cidr and cidr not in networks:
            networks.append(cidr)
    return networks


# `redirect-gateway` - die eine Direktive, die "alles" in ein Wort fasst.
#
# ABGELESEN an openvpn(8) am 22.08.2026, Abschnitt --redirect-gateway:
# "Automatically execute routing commands to cause all outgoing IP
# traffic to be redirected over the VPN." Von den acht Fahnen, die es
# dafuer kennt, aendern genau ZWEI etwas am OB:
#
#     ipv6    "Redirect IPv6 routing into the tunnel. This works similar
#             to the def1 flag, that is, more specific IPv6 routes are
#             added (2000::/4, 3000::/4), covering the whole IPv6
#             unicast space."
#     !ipv4   "Do not redirect IPv4 traffic - typically used in the flag
#             pair ipv6 !ipv4 to redirect IPv6-only."
#
# Die uebrigen sechs (local, autolocal, def1, bypass-dhcp, bypass-dns,
# block-local) aendern das WIE. `def1` etwa nimmt 0.0.0.0/1 +
# 128.0.0.0/1 statt 0.0.0.0/0 - dieselbe Abdeckung, andere Schreibweise,
# und genau der Fall, fuer den full_tunnel_families() rechnet statt zu
# vergleichen.
#
# `redirect-private` STEHT HIER ABSICHTLICH NICHT, und das ist abgelesen
# und nicht vermutet: openvpn(8) sagt woertlich "Like --redirect-gateway,
# but omit actually changing the default gateway. Useful when pushing
# private subnets." Es leitet also gerade NICHT alles um. Es als
# Volltunnel zu melden hiesse, die Datei zu bewarnen, die einen
# Teiltunnel beschreibt - und ein Hinweis, der auch bei harmlosen
# Dateien erscheint, ist nach dem dritten Mal keiner mehr.
OVPN_REDIRECT_KEY = "redirect-gateway"
OVPN_REDIRECT_V6 = "ipv6"
OVPN_REDIRECT_NO_V4 = "!ipv4"


def openvpn_redirect_families(extra: Sequence[Any] | None) -> list[str]:
    """Welche Familien `redirect-gateway` in dieser Datei umleitet.

    Gelesen wird `openvpn.extra` - die Paare (Name, Argumente) aus der
    Erlaubnisliste OVPN_CARRIED_EXTRA, in der `redirect-gateway` schon
    steht, seit OpenVPN als dritte Bauart dazukam. Es musste also nichts
    Neues durchgereicht werden, damit diese Frage beantwortbar wird; die
    Zeile war die ganze Zeit da und hat niemanden erreicht.
    """
    covered = set()
    for entry in extra or []:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        if str(entry[0]).strip().lower() != OVPN_REDIRECT_KEY:
            continue
        flags = [str(flag).strip().lower() for flag in entry[1:]]
        if OVPN_REDIRECT_NO_V4 not in flags:
            covered.add(FULL_TUNNEL_V4)
        if OVPN_REDIRECT_V6 in flags:
            covered.add(FULL_TUNNEL_V6)
    return [family for family in _FULL_TUNNEL_ORDER if family in covered]


def openvpn_full_tunnel(document: dict[str, Any] | None,
                        routed_networks: Sequence[Any] | None = None,
                        ) -> list[str]:
    """Beide Wege, auf denen eine .ovpn "alles" sagt, in EINER Antwort.

    Die Netzliste wird gerechnet wie bei den anderen zwei Bauarten, und
    `redirect-gateway` kommt dazu - eine Datei kann den Volltunnel auf
    beide Weisen erklaeren, und wer nur eine liest, meldet ihn bei der
    Haelfte der Anbieter nicht.

    WAS DIESE ANTWORT NICHT WEISS, und das gehoert in den Bericht und
    nicht in eine Fussnote: `redirect-gateway` wird bei den meisten
    Anbietern gar nicht in der Datei stehen, sondern vom SERVER
    GESCHOBEN (openvpn(8) fuehrt es unter den Optionen, die --push
    kennt). Was hier nicht steht, kann hier auch nicht gefunden werden.
    """
    covered = set(full_tunnel_families(routed_networks,
                                       setting="vpn.routed_networks"))
    covered.update(openvpn_redirect_families((document or {}).get("extra")))
    return [family for family in _FULL_TUNNEL_ORDER if family in covered]


def ovpn_conf_text(document: dict[str, Any],
                   dns: dict[str, Any] | None = None,
                   routed_networks: Sequence[str] | None = None,
                   key_dir: Path | None = None) -> str:
    """Unsere Einstellungen zurueck in .ovpn-Syntax.

    Das ist die Datei, die `nmcli connection import type openvpn`
    bekommt - und sie ist UNSERE. Was an ausfuehrenden Zeilen in der
    fremden Datei stand, ist beim Einlesen abgelehnt worden und kommt
    hier nicht wieder heraus: dieser Text wird aus dem
    Einstellungsdokument gebaut, und in das Dokument kommt nur, was
    OVPN_FIRST_CLASS und OVPN_CARRIED_EXTRA erlauben.

    Die Pfade zeigen auf ~/.config/openvpn - unsere eigenen Dateien,
    0600. NetworkManager uebernimmt bei OpenVPN nur den PFAD in sein
    Profil, nicht den Inhalt; unsere Kopie bleibt damit die Quelle.
    """
    directory = key_dir or openvpn_key_dir()

    def path_of(value: str) -> str:
        # Ein Dateiname ist einer von unseren, ein absoluter Pfad ist
        # der des Nutzers und bleibt, wo er ist.
        return value if value.startswith("/") else str(directory / value)

    lines = ["client"]
    device = str(document.get("dev") or "tun")
    lines.append(f"dev {device}")
    if document.get("dev_type"):
        lines.append(f"dev-type {document['dev_type']}")
    lines.append(f"proto {document.get('proto') or 'udp'}")
    remote = str(document.get("remote") or "")
    port = document.get("port") or 0
    if remote:
        lines.append(f"remote {remote} {port}" if port else f"remote {remote}")

    for field, directive in (("ca_file", "ca"), ("cert_file", "cert"),
                             ("key_file", "key"), ("pkcs12_file", "pkcs12")):
        value = str(document.get(field) or "")
        if value:
            lines.append(f"{directive} {path_of(value)}")

    tls_auth = str(document.get("tls_auth_file") or "")
    if tls_auth:
        direction = str(document.get("ta_dir") or "")
        lines.append(f"tls-auth {path_of(tls_auth)} {direction}".strip())
    tls_crypt = str(document.get("tls_crypt_file") or "")
    if tls_crypt:
        lines.append(f"tls-crypt {path_of(tls_crypt)}")

    if document.get("connection_type") in ("password", "password-tls"):
        # OHNE Dateinamen dahinter, und das ist der Punkt: eine
        # Zugangsdatendatei waere ein Passwort auf der Platte. Der Wert
        # kommt beim Verbinden ueber `nmcli ... passwd-file`.
        lines.append("auth-user-pass")

    for field, directive in (("remote_cert_tls", "remote-cert-tls"),
                             ("cipher", "cipher"), ("auth", "auth"),
                             ("comp_lzo", "comp-lzo")):
        value = str(document.get(field) or "")
        if value:
            lines.append(f"{directive} {value}")
    if document.get("tunnel_mtu"):
        lines.append(f"tun-mtu {document['tunnel_mtu']}")
    if int(document.get("reneg_seconds", -1) or -1) >= 0:
        lines.append(f"reneg-sec {document['reneg_seconds']}")

    for entry in document.get("extra") or []:
        if not entry:
            continue
        lines.append(" ".join(str(piece) for piece in entry))

    for network in routed_networks or []:
        try:
            parsed = ipaddress.ip_network(str(network), strict=False)
        except ValueError:
            continue
        if parsed.version == 4:
            lines.append(f"route {parsed.network_address} {parsed.netmask}")

    entries = list((dns or {}).get("servers") or [])
    for server in entries:
        lines.append(f"dhcp-option DNS {server}")
    domain = str((dns or {}).get("search_domain") or "").strip()
    for piece in domain.split():
        lines.append(f"dhcp-option DOMAIN {piece}")

    return "\n".join(lines) + "\n"


def openvpn_needs_a_secret(document: dict[str, Any]) -> bool:
    """Ob diese Verbindung ohne Zutun des Nutzers hochkommen kann.

    GEMESSEN am 22.08.2026 an NetworkManagers eigenem Einleser: eine
    Datei mit `auth-user-pass` ergibt `password-flags = 1`
    (agentengehalten, nicht gespeichert); eine reine Zertifikatsdatei
    ergibt gar keine Geheimnisflagge. Und nm-openvpn-service erfragt
    `cert-pass`, wenn der private Schluessel verschluesselt ist - seine
    Zeichenkettentabelle fuehrt dafuer eigens
    `-----BEGIN ENCRYPTED PRIVATE KEY-----` und `Proc-Type: 4,ENCRYPTED`.

    Daran haengt, ob vpn-watcher.sh die Verbindung nach einem Netzwechsel
    oder dem Aufwachen von selbst wiederherstellen kann - und die Antwort
    steht deshalb auch im Fenster, statt dass der Nutzer sie an einer
    Verbindung erlebt, die weg bleibt.
    """
    if document.get("connection_type") in ("password", "password-tls"):
        return True
    return openvpn_key_is_encrypted(document)


def openvpn_key_is_encrypted(document: dict[str, Any],
                             key_dir: Path | None = None) -> bool:
    """Ob der private Schluessel eine Passphrase traegt.

    Gelesen wird nur der KOPF der Datei und nur nach den beiden Markern,
    die openssl und openvpn selbst schreiben. Ein unlesbarer oder
    fehlender Schluessel antwortet False: eine Verbindung, die es nicht
    gibt, verlangt keine Passphrase, und ein Traceback an dieser Stelle
    haette das Fenster angehalten.
    """
    value = str(document.get("key_file") or "")
    if not value:
        return False
    directory = key_dir or openvpn_key_dir()
    path = Path(value) if value.startswith("/") else directory / value
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return False
    return ("ENCRYPTED PRIVATE KEY" in head
            or "Proc-Type: 4,ENCRYPTED" in head)


# --------------------------------------------------------------------
# NetworkManager: anlegen und abfragen
# --------------------------------------------------------------------

def nm_import_argv(conf_file: str, kind: str = WG_KIND) -> list[str]:
    """Der Einlesebefehl. Ein PFAD, kein Schluessel.

    `kind` ist der NetworkManager-Typ und heisst zufaellig genauso wie
    unsere Bauart ("wireguard" bzw. "openvpn"). Er steht trotzdem als
    Parameter da und nicht als Verzweigung im Rumpf: der Aufrufer weiss,
    welche Datei er geschrieben hat, und ein Einlesen mit dem falschen
    Typ waere eine Verbindung, die sich anlegen laesst und nie zustande
    kommt.
    """
    return ["nmcli", "connection", "import", "type", kind, "file", conf_file]


def nm_username_argv(connection: str, username: str) -> list[str]:
    """Den Nutzernamen an die OpenVPN-Verbindung schreiben.

    KEIN GEHEIMNIS - deshalb darf er hier als Argument stehen, und nur
    er. Das Passwort und das Einmal-Kennwort gehen ueber `passwd-file`,
    aus dem Grund, der im Kopf des OpenVPN-Teils steht.

    Der Schluessel heisst `username` in `vpn.data`. Das ist die EINE
    Stelle dieser Aufgabe, die am 22.08.2026 NICHT direkt gemessen
    werden konnte: `username` ist im Stringtable von
    libnm-vpn-plugin-openvpn.so als Endstueck von `http-proxy-username`
    zusammengelegt und dort nicht einzeln nachweisbar. Deshalb prueft
    _ovpn_apply() nach dem Schreiben nach, ob der Wert wirklich in der
    Verbindung steht, statt es anzunehmen - siehe nm_vpn_data_argv().
    """
    return ["nmcli", "connection", "modify", connection,
            "+vpn.data", f"username={username}"]


def nm_vpn_data_argv(connection: str) -> list[str]:
    """Die vpn.data der Verbindung zuruecklesen - die Gegenprobe."""
    return ["nmcli", "-t", "-f", "vpn.data", "connection", "show", connection]


def nm_up_argv(connection: str, passwd_file: str = "") -> list[str]:
    """`nmcli connection up`, das Passwort ueber eine DATEI.

    `passwd-file` nimmt Zeilen der Form
    `setting_name.property_name:wert` - fuer ein VPN also
    `vpn.secrets.password:...` (GEMESSEN am 22.08.2026 aus
    `nmcli connection up --help` und nmcli(1); nmcli fuehrt dafuer die
    Zeichenkette `vpn.secrets.%s`). Ohne diese Datei warnt nmcli
    ausdruecklich, dass es ohne `--ask` niemanden fragen kann - und
    `--ask` will ein Terminal, das eine Schale nicht hat.
    """
    argv = ["nmcli", "connection", "up", connection]
    if passwd_file:
        argv += ["passwd-file", passwd_file]
    return argv


def openvpn_secrets_text(password: str = "", token: str = "",
                         cert_pass: str = "") -> str:
    """Die passwd-file fuer `nmcli connection up`.

    Das Einmal-Kennwort geht als `challenge-response` mit und wird NICHT
    an das Passwort angehaengt: OpenVPN hat fuer diesen Fall die
    Rueckfrage-Antwort-Schiene, und nm-openvpn-service spricht sie ueber
    seine Verwaltungsschnittstelle (`CRV1::%s::%s`, in seiner
    Zeichenkettentabelle). Der Anmeldedialog des Zusatzpakets fuehrt das
    Geheimnis als `x-dynamic-challenge:challenge-response` - GEMESSEN am
    22.08.2026, indem er mit einer Wegwerf-Verbindung auf der
    Standardeingabe im `--external-ui-mode` gestartet wurde; er nennt
    dort genau vier Geheimnisse: password, cert-pass,
    http-proxy-password und challenge-response.

    Anhaengen waere geraten, und ein falsch geratenes Passwort ist bei
    einem Anbieter mit Sperrzaehler teurer als eine leere Zeile.
    """
    lines = []
    if password:
        lines.append(f"vpn.secrets.password:{password}")
    if cert_pass:
        lines.append(f"vpn.secrets.cert-pass:{cert_pass}")
    if token:
        lines.append(f"vpn.secrets.challenge-response:{token}")
    return "\n".join(lines) + "\n" if lines else ""


def openvpn_status(connection: str,
                   runner: Runner = subprocess.run) -> tuple[str, str]:
    """connected | stale | disconnected - derselbe Vertrag wie ueberall.

    Wortgleich zu wireguard_status(), weil dieselben vier Leser
    (ags-vpn.template, ags-network-scripts.template, vpn-control.sh und
    vpn-watcher.sh) dieselbe eine Zeile Text bekommen und keiner von
    ihnen wissen muss, welche Bauart eingestellt ist. Getrennt und nicht
    zusammengelegt, weil die beiden Bauarten verschiedene
    NetworkManager-Typen sind und die naechste Abweichung genau hier
    auftauchen wird - eine gemeinsame Funktion mit einem
    Bauart-Parameter waere die Stelle, an der sie dann still verschwaende.
    """
    return wireguard_status(connection, runner)


def nm_own_argv(connection: str, user: str, *,
                autoconnect: bool = False) -> list[str]:
    """Die Verbindung dem Konto zuschreiben - ohne jedes Geheimnis.

    `connection.permissions user:<konto>` ist der Grund, aus dem ein
    ZepOS-Konto OHNE wheel keinen polkit-Dialog sieht: NetworkManager
    prueft dann modify.own (allow_active=yes) statt modify.system.
    GEMESSEN am 21.08.2026, siehe der Abschnitt am Kopf dieses Teils.

    `autoconnect no`, weil ein VPN eine Handlung ist und kein Zustand -
    dieselbe Haltung, aus der die IPsec-Seite `start_action = trap`
    fuehrt und nicht `start`.
    """
    return ["nmcli", "connection", "modify", connection,
            "connection.permissions", f"user:{user}",
            "connection.autoconnect", "yes" if autoconnect else "no"]


def nm_state_argv(connection: str) -> list[str]:
    return ["nmcli", "-t", "-f", "GENERAL.STATE,IP4.ADDRESS",
            "connection", "show", connection]


def parse_nm_state(report: str) -> tuple[str, str]:
    """(Zustand, Adresse) aus `nmcli -t -f GENERAL.STATE,IP4.ADDRESS`.

    Das Feld heisst `IP4.ADDRESS[1]`, nicht `IP4.ADDRESS` - die eckige
    Klammer ist eine Nummer und keine Zierde, und ein Vergleich auf den
    blossen Namen findet sie nie. Der Wert kommt mit Praefix
    (`10.9.0.2/24`); zurueck geht die blosse Adresse, weil das der
    Wert ist, den `--status` seit jeher nennt.
    """
    state, address = "", ""
    for line in report.splitlines():
        field, _, value = line.partition(":")
        field, value = field.strip(), value.strip()
        if field == "GENERAL.STATE":
            state = value
        elif field.startswith("IP4.ADDRESS") and not address:
            address = value.split("/")[0]
    return state, address


def wireguard_status(connection: str,
                     runner: Runner = subprocess.run) -> tuple[str, str]:
    """connected | stale | disconnected, in genau dem Vertrag von tunnel_status().

    Vier Leser teilen sich diese eine Zeile Text - ags-vpn.template,
    ags-network-scripts.template, vpn-control.sh und vpn-watcher.sh -
    und keiner von ihnen darf wissen muessen, welche Bauart gerade
    eingestellt ist. Deshalb hat die WireGuard-Antwort dieselben drei
    Woerter und dieselbe Bedeutung:

      connected      NetworkManager fuehrt die Verbindung als aktiviert
                     UND nennt eine Adresse.
      stale          aktiviert, aber ohne Adresse: die Schnittstelle
                     steht und traegt nichts. Genau die halbe Verbindung,
                     fuer die es bei IPsec `stale` gibt.
      disconnected   alles andere, die fehlende Auskunft eingeschlossen.
                     Ohne Antwort wird nichts behauptet - dieselbe
                     Zurueckhaltung wie bei tunnel_status().
    """
    if not connection:
        return DISCONNECTED, ""
    state, address = parse_nm_state(_run(runner, nm_state_argv(connection)))
    if state != "activated":
        return DISCONNECTED, ""
    if not address:
        return STALE, ""
    return CONNECTED, address


def vpn_kind(settings: dict[str, Any]) -> str:
    """Welche Bauart eingestellt ist - und im Zweifel IPsec.

    Die Vorgabe ist NICHT geraten und darf es nie werden: jede
    Installation, die es vor dem 21.08.2026 gab, hat keinen Schluessel
    `kind`, und fuer sie muss jeder Pfad Zeile fuer Zeile der heutige
    bleiben. Ein unbekannter Wert antwortet ebenfalls "ipsec" - eine
    vertippte Bauart darf nicht in eine Verbindung fuehren, die der
    Nutzer nicht gemeint hat.
    """
    section = settings.get("vpn") if isinstance(settings, dict) else None
    value = (section or {}).get("kind") if isinstance(section, dict) else None
    return value if value in VPN_KINDS else IPSEC_KIND


def settings_full_tunnel(document: dict[str, Any] | None) -> list[str]:
    """Leitet die EINGESTELLTE Verbindung den gesamten Verkehr um?

    Die eine Regel fuer alle drei Bauarten, an derselben Stelle wie
    vpn_kind() und mit derselben Vorsicht: eine unbekannte Bauart
    antwortet wie IPsec, also aus der Netzliste. Die drei Zweige
    unterscheiden sich nur darin, WO die Netze stehen -
    full_tunnel_families() rechnet in allen dreien dasselbe.
    """
    kind = vpn_kind(document or {})
    if kind == WG_KIND:
        return wireguard_full_tunnel(_wg_section(document or {}))
    if kind == OVPN_KIND:
        return openvpn_full_tunnel(_ovpn_section(document or {}),
                                   _routed_networks(document or {}))
    return full_tunnel_families(_routed_networks(document or {}),
                                setting="vpn.routed_networks")


# --------------------------------------------------------------------
# the command line the artifacts ask through
# --------------------------------------------------------------------

USAGE = """usage: vpn.py --virtual-address | --tunnel-health
                 | --status | --full-tunnel | --address-present ADDRESS
                 | --wg-import FILE | --wg-genkey NAME
                 | --wg-apply | --wg-up | --wg-down
                 | --ovpn-import FILE | --ovpn-apply
                 | --ovpn-up | --ovpn-down | --ovpn-unattended

  --virtual-address    read `swanctl --list-sas` output on standard input
                       and print the virtual address it reports.
                       exit 0 printed, 1 no IKE_SA, 2 IKE_SA without one.
  --tunnel-health      same input; prints the number of installed
                       CHILD_SAs. exit 0 healthy, 1 half-up, 2 no tunnel.
  --status             print `connected|stale|disconnected` and, when one
                       was recorded, the tunnel's address. Which half
                       answers is decided by `vpn.kind` in the settings.
  --full-tunnel        print `ipv4`, `ipv6`, both or nothing: which
                       address families the configured connection routes
                       COMPLETELY through the tunnel. Reads the settings,
                       changes nothing, always exits 0.
  --address-present A  print A's address/prefix if it is configured on an
                       interface; exit 1 if it is not.
  --wg-import FILE     read a wg-quick configuration, store its secrets
                       at 0600 and print the settings section as JSON.
                       exit 0 taken over whole, 3 taken over with lines
                       refused (they are named in `refused`), 65 refused
                       outright with file and line on stderr.
  --wg-genkey NAME     create a WireGuard key pair, store the private
                       half as NAME at 0600, print the public half.
  --wg-apply           build the NetworkManager connection from the
                       settings. The private key travels as a FILE.
  --wg-up / --wg-down  activate / deactivate that connection.
  --ovpn-import FILE   read an OpenVPN configuration, store its embedded
                       certificates and keys at 0600 and print the
                       settings section as JSON. exit 0 taken over whole,
                       3 taken over with lines refused (they are named in
                       `refused`), 65 refused outright with file and line
                       on stderr.
  --ovpn-apply         build the NetworkManager connection from the
                       settings, and check afterwards that it kept the
                       username.
  --ovpn-up            activate it. Credentials arrive as JSON on
                       standard input - never as arguments - and travel
                       to nmcli in a 0600 file that is deleted again.
  --ovpn-down          deactivate it.
  --ovpn-unattended    print `yes` or `no`: whether this connection can
                       be restored without anybody typing anything.
"""

# Der eigene Rueckgabewert fuer "eingelesen, aber Zeilen abgelehnt". Ein
# Aufrufer, der die abgelehnten Haken-Zeilen uebergehen will, muss das
# damit AKTIV tun - `exit 0` haette ihm erlaubt, sie nicht zu bemerken.
WG_IMPORT_REFUSED = 3
# Derselbe Wert fuer OpenVPN, und ausgeschrieben statt geteilt: die
# beiden Bauarten lehnen aus demselben Grund ab, aber sie sind zwei
# Befehle mit zwei Vertraegen, und ein gemeinsamer Name waere die
# Stelle, an der eine Aenderung an der einen die andere still
# mitnimmt.
OVPN_IMPORT_REFUSED = 3


def _settings_document() -> dict[str, Any]:
    """Die Einstellungen, oder {} - fuer einen Leser, der nur fragt.

    `--status` laeuft mehrmals je Minute aus der Leiste und aus zwei
    Widgets. Ein Traceback ueber eine unlesbare Einstellungsdatei waere
    dort kein Fehlerbericht, sondern eine Leiste, die stehenbleibt - und
    die Antwort auf "welche Bauart?" ist ohne lesbare Datei ohnehin
    "die, die es vorher schon gab", also IPsec.
    """
    try:
        try:
            from .settings import load as _load
        except ImportError:
            from settings import load as _load
        return _load()
    except (ValueError, OSError):
        return {}


def _wg_connection_name(document: dict[str, Any]) -> str:
    section = document.get("vpn") if isinstance(document, dict) else None
    name = (section or {}).get("connection_name") if isinstance(section, dict) else None
    return str(name or "work")


def _wg_section(document: dict[str, Any]) -> dict[str, Any]:
    section = document.get("vpn") if isinstance(document, dict) else None
    block = (section or {}).get(WG_KIND) if isinstance(section, dict) else None
    return block if isinstance(block, dict) else {}


def _wg_dns(document: dict[str, Any]) -> dict[str, Any]:
    section = document.get("vpn") if isinstance(document, dict) else None
    block = (section or {}).get("dns") if isinstance(section, dict) else None
    return block if isinstance(block, dict) else {}


def _wg_apply(document: dict[str, Any],
              runner: Runner = subprocess.run) -> int:
    """Die Verbindung aus den Einstellungen bauen.

    Die .conf wird in das Laufzeitverzeichnis des Nutzers geschrieben
    (ein tmpfs, das nur ihm gehoert und beim Abmelden geleert wird),
    0600, und danach GELOESCHT - auch wenn `nmcli` scheitert. Sie traegt
    den privaten Schluessel, und sie ist der einzige Grund, aus dem er
    NICHT in einer Befehlszeile steht.
    """
    block = _wg_section(document)
    name = _wg_connection_name(document)
    key_file = str(block.get("private_key_file") or "")
    if not key_file:
        sys.stderr.write("no WireGuard private key is configured\n")
        return 1
    key_path = wireguard_key_dir() / key_file
    try:
        private_key = read_wireguard_secret(key_path)
    except OSError as exc:
        sys.stderr.write(f"{key_path}: {exc}\n")
        return 1

    secrets = []
    for peer in block.get("peers") or []:
        stored = str(peer.get("preshared_key_file") or "")
        try:
            secrets.append(read_wireguard_secret(wireguard_key_dir() / stored)
                           if stored else "")
        except OSError:
            secrets.append("")

    runtime = Path(os.environ.get("XDG_RUNTIME_DIR")
                   or f"/run/user/{os.getuid()}") / "zepos-vpn"
    runtime.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime, 0o700)
    # `nmcli connection import` benennt die Verbindung nach dem
    # DATEINAMEN - deshalb heisst sie hier wie die Verbindung heissen
    # soll, statt einen Zufallsnamen zu tragen, den wir danach
    # umbenennen muessten.
    conf_file = runtime / f"{name}.conf"
    conf_file.unlink(missing_ok=True)
    handle = os.open(conf_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(handle, wireguard_conf_text(
            block, private_key, _wg_dns(document), secrets).encode("utf-8"))
    finally:
        os.close(handle)

    try:
        for argv in (nm_import_argv(str(conf_file), WG_KIND),
                     nm_own_argv(name, os.environ.get("USER")
                                 or str(os.getuid()))):
            completed = runner(argv, capture_output=True, text=True,
                               timeout=30)
            if completed.returncode != 0:
                sys.stderr.write((completed.stderr or "").strip() + "\n")
                return 1
    finally:
        conf_file.unlink(missing_ok=True)
    print(name)
    return 0


def _ovpn_section(document: dict[str, Any]) -> dict[str, Any]:
    section = document.get("vpn") if isinstance(document, dict) else None
    block = (section or {}).get(OVPN_KIND) if isinstance(section, dict) else None
    return block if isinstance(block, dict) else {}


def _routed_networks(document: dict[str, Any]) -> list[str]:
    """Die Netzliste - DIESELBE fuer alle drei Bauarten.

    Hiess bis zum 22.08.2026 _ovpn_routed() und hat nie etwas
    OpenVPN-Eigenes gelesen: sie steht unter `vpn.routed_networks`, weil
    IPsec sie in Child-SAs, WireGuard sie in AllowedIPs und OpenVPN sie
    in `route`-Zeilen uebersetzt. Seit settings_full_tunnel() sie fuer
    alle drei liest, waere der alte Name die Stelle, an der jemand eine
    zweite Liste daneben anlegt.
    """
    section = document.get("vpn") if isinstance(document, dict) else None
    values = (section or {}).get("routed_networks") if isinstance(section, dict) else None
    return [str(entry) for entry in values] if isinstance(values, list) else []


def _runtime_dir() -> Path:
    """Das eigene Laufzeitverzeichnis - ein tmpfs, 0700, beim Abmelden leer.

    Dieselbe Wahl und dieselbe Begruendung wie in _wg_apply() und in
    ags-vpn.template: /tmp kann jedes Konto der Maschine lesen.
    """
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR")
                   or f"/run/user/{os.getuid()}") / "zepos-vpn"
    runtime.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime, 0o700)
    return runtime


def _write_private(path: Path, text: str) -> None:
    """0600 vom ersten Byte, ueber O_EXCL - siehe write_private_secret()."""
    path.unlink(missing_ok=True)
    handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(handle, text.encode("utf-8"))
    finally:
        os.close(handle)


def _ovpn_apply(document: dict[str, Any],
                runner: Runner = subprocess.run) -> int:
    """Die OpenVPN-Verbindung aus den Einstellungen bauen.

    Die .ovpn liegt 0600 im Laufzeitverzeichnis und wird danach
    GELOESCHT - auch wenn `nmcli` scheitert. Sie traegt zwar kein
    Geheimnis (die Zertifikate stehen als Pfad darin), aber sie ist die
    Datei, aus der die Verbindung entsteht, und eine liegengebliebene
    Kopie ist eine zweite Wahrheit.
    """
    block = _ovpn_section(document)
    name = _wg_connection_name(document)
    if not block.get("remote"):
        sys.stderr.write("no OpenVPN server is configured\n")
        return 1

    conf_file = _runtime_dir() / f"{name}.ovpn"
    _write_private(conf_file, ovpn_conf_text(block, _wg_dns(document),
                                             _routed_networks(document)))
    try:
        for argv in (nm_import_argv(str(conf_file), OVPN_KIND),
                     nm_own_argv(name, os.environ.get("USER")
                                 or str(os.getuid()))):
            completed = runner(argv, capture_output=True, text=True,
                               timeout=30)
            if completed.returncode != 0:
                sys.stderr.write((completed.stderr or "").strip() + "\n")
                return 1
    finally:
        conf_file.unlink(missing_ok=True)

    username = str(block.get("username") or "")
    if username:
        completed = runner(nm_username_argv(name, username),
                           capture_output=True, text=True, timeout=30)
        if completed.returncode != 0:
            sys.stderr.write((completed.stderr or "").strip() + "\n")
            return 1
        # DIE GEGENPROBE, und sie ist kein Luxus: der Eigenschaftsname
        # `username` liess sich am 22.08.2026 nicht direkt messen (er
        # ist im Stringtable als Endstueck von `http-proxy-username`
        # zusammengelegt). Ein falscher Name faellt ohne diese Zeilen
        # erst auf, wenn der Nutzer sich anzumelden versucht - und dann
        # sagt ihm niemand, woran es lag.
        report = _run(runner, nm_vpn_data_argv(name))
        if f"username = {username}" not in report \
                and f"username={username}" not in report:
            sys.stderr.write(
                f"NetworkManager did not keep the username: `nmcli "
                f"connection show {name}` reports no `username = "
                f"{username}` in vpn.data. The connection exists but "
                f"will ask for a user it does not have.\n")
            return 1
    print(name)
    return 0


def _ovpn_credentials() -> dict[str, str]:
    """Zugangsdaten von der STANDARDEINGABE, nie aus argv.

    /proc/<pid>/cmdline ist fuer jedes Konto der Maschine lesbar; die
    IPsec-Seite reicht Nutzername, Passwort und Token bis heute als
    Argumente durch, und genau das wird hier nicht wiederholt.

    Ein Terminal wird NICHT gelesen: eine reine Zertifikatsverbindung
    braucht kein Geheimnis, und ein `vpn.py --ovpn-up` von Hand oder aus
    einem Waechter heraus soll dort nicht haengen bleiben, wo es nichts
    zu lesen gibt.
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        raw = sys.stdin.read().strip()
    except (OSError, ValueError):
        return {}
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except ValueError:
        return {}
    return {key: str(value) for key, value in payload.items()
            if isinstance(payload, dict) and value}


def _ovpn_up(document: dict[str, Any],
             credentials: dict[str, str] | None = None,
             runner: Runner = subprocess.run) -> int:
    """Hochfahren - das Passwort ueber eine Datei, nie ueber argv.

    Die passwd-file liegt 0600 im Laufzeitverzeichnis und wird im
    `finally` geloescht, auch wenn `nmcli` scheitert oder eine Ausnahme
    fliegt. Bleibt sie liegen, ist ein Passwort auf der Platte, das
    vorher nirgends auf der Platte stand.
    """
    name = _wg_connection_name(document)
    given = credentials or {}
    text = openvpn_secrets_text(password=given.get("password", ""),
                                token=given.get("token", ""),
                                cert_pass=given.get("cert_pass", ""))
    secrets_file = None
    try:
        if text:
            secrets_file = _runtime_dir() / f"{name}.secrets"
            _write_private(secrets_file, text)
        completed = runner(nm_up_argv(name, str(secrets_file) if secrets_file
                                      else ""),
                           capture_output=True, text=True, timeout=90)
    finally:
        if secrets_file is not None:
            secrets_file.unlink(missing_ok=True)
    if completed.returncode != 0:
        sys.stderr.write((completed.stderr or "").strip() + "\n")
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        sys.stderr.write(USAGE)
        return 64

    query = arguments[0]
    if query == "--virtual-address":
        report = sys.stdin.read()
        address = assigned_address(report)
        if address:
            print(address)
            return 0
        return 1 if not parse_sas(report) else 2

    if query == "--tunnel-health":
        report = sys.stdin.read()
        # The count goes to stdout because the caller that needs the
        # verdict also needs the number - and counting `INSTALLED` again
        # with grep, which is what the connect script did, counts the
        # word wherever it appears rather than the CHILD_SAs that have
        # it.
        print(sum(sa.installed_children for sa in parse_sas(report)))
        return HEALTH_EXIT[tunnel_health(report)]

    if query == "--status":
        # Welche Haelfte antwortet, entscheidet `vpn.kind` - und im
        # Zweifel IPsec, siehe vpn_kind(). Der Vertrag nach aussen ist
        # in beiden Faellen derselbe: ein Wort, und dahinter, wenn es
        # eine gibt, die Adresse.
        document = _settings_document()
        kind = vpn_kind(document)
        if kind == WG_KIND:
            state, address = wireguard_status(_wg_connection_name(document))
        elif kind == OVPN_KIND:
            state, address = openvpn_status(_wg_connection_name(document))
        else:
            state, address = tunnel_status()
        print(state if not address else f"{state} {address}")
        return 0

    if query == "--wg-import":
        if len(arguments) < 2:
            sys.stderr.write(USAGE)
            return 64
        source = arguments[1]
        try:
            conf = parse_wg_conf(Path(source).read_text(encoding="utf-8"),
                                 source)
        except OSError as exc:
            sys.stderr.write(f"{source}: {exc}\n")
            return 65
        except UnreadableWireGuardConfig as exc:
            sys.stderr.write(f"{exc}\n")
            return 65

        document = _settings_document()
        name = _wg_connection_name(document)
        private_key = conf.interface.get("PrivateKey", "")
        key_file = ""
        if private_key:
            key_file = write_wireguard_secret(f"{name}.key", private_key).name
        stored = []
        for index, peer in enumerate(conf.peers, start=1):
            secret = peer.get("PresharedKey", "")
            stored.append(write_wireguard_secret(f"{name}-peer{index}.psk",
                                                 secret).name
                          if secret else "")
        block = wireguard_document(
            conf, private_key_file=key_file,
            public_key=public_wireguard_key(private_key) if private_key
            else "",
            preshared_key_files=stored)
        payload = {
            "wireguard": block,
            "dns": wireguard_dns(conf),
            # Was die Datei ueber den Umfang des Tunnels sagt - GEZEIGT,
            # nicht geaendert. Die AllowedIPs bleiben Zeichen fuer
            # Zeichen die der Datei; hier steht nur, was sie bedeuten.
            "full_tunnel": wireguard_full_tunnel(block),
            # Die abgelehnten Zeilen fahren MIT. Sie sind der Grund fuer
            # den eigenen Rueckgabewert unten, und der Aufrufer zeigt
            # sie - eine Datei, die halb ankommt und deren Rest still
            # verschwindet, ist schlimmer als eine Fehlermeldung.
            "refused": [[number, key] for number, key in conf.refused],
        }
        print(json.dumps(payload, indent=2))
        if conf.refused:
            for number, key in conf.refused:
                sys.stderr.write(
                    f"{source}:{number}: {key} was NOT taken over - it runs "
                    f"commands, and ZepOS connects through NetworkManager, "
                    f"which does not.\n")
            return WG_IMPORT_REFUSED
        return 0

    if query == "--wg-genkey":
        if len(arguments) < 2:
            sys.stderr.write(USAGE)
            return 64
        try:
            private_key = generate_wireguard_key()
        except (UnreadableWireGuardConfig, OSError,
                subprocess.SubprocessError) as exc:
            sys.stderr.write(f"{exc}\n")
            return 1
        write_wireguard_secret(arguments[1], private_key)
        print(public_wireguard_key(private_key))
        return 0

    if query == "--wg-apply":
        return _wg_apply(_settings_document())

    if query in ("--wg-up", "--wg-down"):
        name = _wg_connection_name(_settings_document())
        verb = "up" if query == "--wg-up" else "down"
        completed = subprocess.run(["nmcli", "connection", verb, name],
                                   capture_output=True, text=True, timeout=60)
        if completed.returncode != 0:
            sys.stderr.write((completed.stderr or "").strip() + "\n")
        return completed.returncode

    if query == "--ovpn-import":
        if len(arguments) < 2:
            sys.stderr.write(USAGE)
            return 64
        source = arguments[1]
        try:
            conf = parse_ovpn(Path(source).read_text(encoding="utf-8"), source)
        except OSError as exc:
            sys.stderr.write(f"{source}: {exc}\n")
            return 65
        except UnreadableOpenVpnConfig as exc:
            sys.stderr.write(f"{exc}\n")
            return 65

        document = _settings_document()
        name = _wg_connection_name(document)
        stored = store_openvpn_blobs(conf, name)
        block = openvpn_document(conf, stored_files=stored)
        # Der Nutzername aus den bestehenden Einstellungen bleibt
        # stehen: eine .ovpn traegt keinen (gemessen - NetworkManagers
        # Einleser liest nicht einmal die Datei hinter `auth-user-pass`),
        # und ihn beim Einlesen zu leeren hiesse, dem Nutzer etwas
        # wegzunehmen, das in der Datei gar nicht vorkam.
        block["username"] = str(_ovpn_section(document).get("username")
                                or (document.get("vpn") or {}).get("username")
                                or "")
        routed = openvpn_routes(conf)
        payload = {
            "openvpn": block,
            "dns": openvpn_dns(conf),
            # In die BESTEHENDE Netzliste, denselben Reiter, den IPsec
            # und WireGuard benutzen.
            "routed_networks": routed,
            # Beide Wege zusammen: die Netzliste UND `redirect-gateway`.
            # Gezeigt, nicht geaendert - siehe openvpn_full_tunnel().
            "full_tunnel": openvpn_full_tunnel(block, routed),
            # Beide Listen fahren mit. `refused` traegt den eigenen
            # Rueckgabewert, `ignored` nicht - der Unterschied ist die
            # Schwere, nicht die Sichtbarkeit: gezeigt wird beides.
            "refused": [[number, key] for number, key in conf.refused],
            "ignored": [[number, key] for number, key in conf.ignored],
            # Damit das Fenster den Satz ueber den unbeaufsichtigten
            # Wiederaufbau zeigen kann, ohne ihn selbst herzuleiten.
            "needs_a_secret": openvpn_needs_a_secret(block),
        }
        print(json.dumps(payload, indent=2))
        if conf.refused:
            for number, key in conf.refused:
                sys.stderr.write(
                    f"{source}:{number}: {key} was NOT taken over - it runs "
                    f"commands (or permits them to run), and ZepOS connects "
                    f"through NetworkManager, which does not.\n")
            return OVPN_IMPORT_REFUSED
        return 0

    if query == "--ovpn-apply":
        return _ovpn_apply(_settings_document())

    if query == "--ovpn-up":
        return _ovpn_up(_settings_document(), _ovpn_credentials())

    if query == "--ovpn-down":
        name = _wg_connection_name(_settings_document())
        completed = subprocess.run(["nmcli", "connection", "down", name],
                                   capture_output=True, text=True, timeout=60)
        if completed.returncode != 0:
            sys.stderr.write((completed.stderr or "").strip() + "\n")
        return completed.returncode

    if query == "--ovpn-unattended":
        # Ein Wort, wie `--status` eines ist. Der Aufrufer soll nicht
        # aus connection_type und dem Kopf einer Schluesseldatei selbst
        # herleiten muessen, was hier an EINER Stelle steht.
        print("no" if openvpn_needs_a_secret(
            _ovpn_section(_settings_document())) else "yes")
        return 0

    if query == "--full-tunnel":
        # Fuer JEDEN Leser, der keine Einstellungen im Speicher hat -
        # das Fenster rechnet bei jedem Tastendruck selbst (siehe
        # fullTunnelFamilies in ags-vpn-settings.template), ein Skript
        # oder eine Statuszeile kann es hier erfragen. Nichts wird
        # geschrieben und nichts angefasst; die Antwort ist eine Zeile
        # aus null, einem oder zwei Woertern.
        families = settings_full_tunnel(_settings_document())
        if families:
            print(" ".join(families))
        return 0

    if query == "--address-present":
        if len(arguments) < 2:
            sys.stderr.write(USAGE)
            return 64
        cidr = address_present(arguments[1])
        if not cidr:
            return 1
        print(cidr)
        return 0

    sys.stderr.write(USAGE)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
