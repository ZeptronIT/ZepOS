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
# the command line the artifacts ask through
# --------------------------------------------------------------------

USAGE = """usage: vpn.py --virtual-address | --tunnel-health
                 | --status | --address-present ADDRESS

  --virtual-address    read `swanctl --list-sas` output on standard input
                       and print the virtual address it reports.
                       exit 0 printed, 1 no IKE_SA, 2 IKE_SA without one.
  --tunnel-health      same input; prints the number of installed
                       CHILD_SAs. exit 0 healthy, 1 half-up, 2 no tunnel.
  --status             print `connected|stale|disconnected` and, when one
                       was recorded, the tunnel's address.
  --address-present A  print A's address/prefix if it is configured on an
                       interface; exit 1 if it is not.
"""


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
        state, address = tunnel_status()
        print(state if not address else f"{state} {address}")
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
