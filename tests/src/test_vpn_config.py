# SPDX-License-Identifier: GPL-3.0-or-later
"""The VPN keeps working; the previous employer's values do not survive.

Everything the origin spelled out - a corporate domain, two internal DNS
servers, a file server hostname and three routed networks written out one
by one - is now read from the settings, and the child security
associations are generated from the network list instead of being three
fixed blocks.

The second half of this file is about a different kind of survival: not a
value the origin wrote down, but an ASSUMPTION six artifacts made about
the address range its gateway hands out. See
test_no_template_assumes_the_employers_vpn_address_range and the section
under it.
"""
import json
import re
from pathlib import Path

import pytest

from src.settings import defaults
from tests.origin_data import ORIGIN
from src.vpn import (
    child_names,
    routed_networks_line,
    swanctl_children,
    swanctl_config,
)

# Resolved from this file rather than from the working directory: a test
# that only passes when pytest happens to be started in the repository
# root is a test that reports on the caller's shell, not on the source.
SRC = Path(__file__).resolve().parents[2] / "src"


def test_no_employer_values_remain_in_the_templates():
    """The three strings this used to spell out are digests in
    tests/origin_data.py now, together with twenty-one more - so the set
    checked here got larger, not smaller, and the file stopped carrying
    the domain it forbids.

    The `if not path.exists(): continue` is kept and then closed off: a
    template that is renamed away makes this test pass by scanning
    nothing, so the three names are asserted to be present first.
    """
    names = ("vpn-connect-script", "ags-vpn-settings", "vpn-control-config")
    missing = [name for name in names
               if not (SRC / "templates" / f"{name}.template").exists()]
    assert missing == [], f"nothing to scan - these templates are gone: {missing}"

    for name in names:
        path = SRC / "templates" / f"{name}.template"
        lines = ORIGIN.offending_lines(path.read_text(encoding="utf-8"))
        assert lines == [], (
            f"an origin value survives in {name} at line(s) {lines} - see "
            "tests/origin_data.py")


def test_one_routed_network_yields_one_child():
    children = swanctl_children("work", ["10.0.0.0/8"])
    assert len(re.findall(r"work-\d+ \{", children)) == 1


def test_five_routed_networks_yield_five_children():
    """The origin wrote exactly three, spelled out. A user with five
    networks had no way to express that."""
    nets = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
            "100.64.0.0/10", "198.18.0.0/15"]
    children = swanctl_children("work", nets)
    assert len(re.findall(r"work-\d+ \{", children)) == 5
    for net in nets:
        assert f"remote_ts = {net}" in children


def test_no_routed_networks_is_refused():
    """A tunnel that routes nothing silently connects and carries no
    traffic - the user would see 'connected' and reach nothing."""
    try:
        swanctl_children("work", [])
    except ValueError:
        return
    raise AssertionError("an empty network list must be refused")


def test_config_uses_the_configured_server_not_a_constant():
    cfg = dict(defaults())
    cfg["vpn"]["server"] = "vpn.example.org"
    cfg["vpn"]["routed_networks"] = ["10.0.0.0/8"]
    out = swanctl_config(cfg)
    assert "vpn.example.org" in out


def test_config_honours_the_phase_settings_it_is_handed():
    """A user whose gateway leaves them no choice about IKEv1 aggressive
    mode is supported - the generator parameterises correctly for them.
    This function used to read only the server, the name and the networks
    and fill the rest from its own constants, so it answered with IKEv2
    and ecp521 for exactly that user, silently. A doctor built on it
    would report a configuration other than the deployed one."""
    cfg = dict(defaults())
    cfg["vpn"]["server"] = "vpn.example.org"
    cfg["vpn"]["routed_networks"] = ["10.0.0.0/8"]
    cfg["vpn"]["phase1"] = {
        "version": 1, "aggressive": True, "keylife": 28800,
        "proposals": "aes128-sha1-modp1536", "dpd_delay": 15,
        "dpd_timeout": 60, "encap": False, "mobike": True,
    }
    cfg["vpn"]["phase2"] = {
        "rekey_time": 3600, "life_time": 7200, "mode": "transport",
        "replay_window": 64, "esp_proposals": "aes128-sha1-modp1536",
    }

    out = swanctl_config(cfg)

    for expected in ("version = 1", "aggressive = yes",
                     "proposals = aes128-sha1-modp1536", "dpd_delay = 15s",
                     "dpd_timeout = 60s", "encap = no", "mobike = yes",
                     "rekey_time = 28800s", "life_time = 7200s",
                     "mode = transport", "replay_window = 64",
                     "esp_proposals = aes128-sha1-modp1536"):
        assert expected in out, f"{expected!r} was discarded"


def test_an_ikev2_config_carries_no_aggressive_keyword():
    """Aggressive mode is IKEv1 only; strongSwan rejects the keyword under
    version 2, and the connect script emits it only for version 1."""
    cfg = dict(defaults())
    cfg["vpn"]["server"] = "vpn.example.org"
    cfg["vpn"]["routed_networks"] = ["10.0.0.0/8"]
    cfg["vpn"]["phase1"] = {"version": 2, "aggressive": True}
    assert "aggressive" not in swanctl_config(cfg)


def test_defaults_produce_no_usable_config():
    """Shipping a working VPN config nobody asked for would connect a
    fresh installation to a stranger's network."""
    try:
        swanctl_config(defaults())
    except ValueError:
        return
    raise AssertionError("an unconfigured VPN must be refused, not guessed")


def test_networks_without_a_server_are_refused_by_the_server_check():
    """The refusal above, pinned to the check that is supposed to make it.

    defaults() has neither a server NOR any routed networks, so
    swanctl_config() refuses it twice over - and the test above cannot
    tell which refusal it got. Measured: giving the missing-server check
    a default value instead of raising left the whole suite green,
    because the empty-network path still raised underneath it.

    This is the configuration where only one of the two can answer: the
    user has said which networks belong in the tunnel and has not said
    where the tunnel goes. Without the server check they get a
    configuration pointing at whatever the default happened to be - a
    stranger's gateway, offered as theirs.
    """
    document = {"vpn": {"server": "", "routed_networks": ["10.0.0.0/8"]}}

    with pytest.raises(ValueError) as raised:
        swanctl_config(document)
    assert "server" in str(raised.value).lower(), raised.value

    # The same document with the one missing value supplied has to work,
    # or "it refuses" is a statement about something else entirely.
    document["vpn"]["server"] = "gw.example.org"
    assert "gw.example.org" in swanctl_config(document)


def test_a_server_of_nothing_but_spaces_is_still_no_server():
    """What the settings dialog writes when the field is cleared."""
    with pytest.raises(ValueError):
        swanctl_config({"vpn": {"server": "   ",
                                "routed_networks": ["10.0.0.0/8"]}})


def test_the_generated_script_refuses_to_run_unconfigured():
    """Generation must not fail for someone who has no VPN - a fresh
    installation still needs its bar, its terminal and its shell. So the
    script IS written, with empty values, and has to stop by itself
    rather than hand strongSwan a connection block that routes nothing.
    """
    text = (SRC / "templates" / "vpn-connect-script.template").read_text(
        encoding="utf-8")
    assert "{{STYLE_VPN_CHILDREN}}" in text
    assert 'if [ -z "$CHILDREN_CONF" ]' in text, (
        "nothing checks whether any network is routed before connecting")


def test_the_routing_commands_follow_the_same_list_as_the_children():
    """The origin wrote its three networks out twice more, as `ip route
    add` lines. A fourth network would have been tunnelled but not
    routed - the tunnel comes up and half the traffic goes nowhere."""
    nets = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"]
    assert routed_networks_line(nets) == " ".join(nets)

    text = (SRC / "templates" / "vpn-connect-script.template").read_text(
        encoding="utf-8")
    for spelled_out in ("ip route add 10.0.0.0/8", "ip route add 172.16.0.0/12",
                        "ip route add 192.168.0.0/16"):
        assert spelled_out not in text, f"{spelled_out} is still hardcoded"


def test_every_child_the_config_declares_is_a_child_someone_initiates():
    """The names in the configuration and the names the scripts initiate
    are one derivation, not three.

    The origin derived them separately in the connect script and in the
    watcher, live from the settings file, so an edit between generating
    and connecting produced `child 'x' not found` - a child the user
    never configured, named by a script they did not run. The watcher's
    fallback made it worse: with no settings it initiated the previous
    employer's connection name once a minute, indefinitely.
    """
    nets = ["10.0.0.0/8", "172.16.0.0/12", "192.168.5.0/24"]
    names = child_names("office", nets)
    assert names == ["office-1", "office-2", "office-3"]

    block = swanctl_children("office", nets)
    for name in names:
        assert f"{name} {{" in block

    for template in ("vpn-connect-script", "vpn-watcher-config"):
        text = (SRC / "templates" / f"{template}.template").read_text(
            encoding="utf-8")
        assert "{{STYLE_VPN_CHILD_NAMES}}" in text, (
            f"{template} does not use the generated names")
        assert "child_sas" not in text, (
            f"{template} still derives the names for itself")


def test_both_callers_of_the_connect_script_name_the_same_connection():
    """The AGS widget passes vpn.connection_name as the connect script's
    sixth argument; the control script wrote the origin's own name in by
    hand. They agreed only for the person who wrote them, and the
    disagreement showed up on DISCONNECT: `swanctl --terminate --ike
    work-ipsec` terminated nothing and left the tunnel up."""
    text = (SRC / "templates" / "vpn-control-config.template").read_text(
        encoding="utf-8")
    assert 'VPN_CONNECTION="{{STYLE_VPN_CONNECTION_NAME}}"' in text
    assert 'VPN_CONNECTION="work-ipsec"' not in text


def test_the_settings_dialog_shows_the_values_the_generator_uses():
    """The dialog is the only way to configure a VPN, and saving it
    replaces the whole vpn section. A second set of defaults written into
    the dialog therefore did not merely display something else - an
    untouched "Save" wrote it over the generator's values, moving the
    tunnel from IKEv2 main mode to IKEv1 aggressive mode with SHA-1
    without saying so."""
    text = (SRC / "templates" / "ags-vpn-settings.template").read_text(
        encoding="utf-8")
    for placeholder in ("{{STYLE_VPN_VERSION}}", "{{STYLE_VPN_AGGRESSIVE}}",
                        "{{STYLE_VPN_IKE_PROPOSALS}}", "{{STYLE_VPN_KEYLIFE}}",
                        "{{STYLE_VPN_ESP_PROPOSALS}}", "{{STYLE_VPN_MODE}}"):
        assert placeholder in text, f"{placeholder} is written in by hand"
    assert "modp1536" not in text, "a second proposal set survives in the dialog"


# "10.1." as an address prefix, whether written plain or backslash-escaped
# for a shell or Python regex. Deliberately does not match 10.10.10.x.
VIRTUAL_IP_ASSUMPTION = re.compile(r"10\\?\.1\\?\.")


def test_no_template_assumes_the_employers_vpn_address_range():
    """Ten lines across six templates used to match interface addresses
    against 10.1.0.0/16 - the previous employer's VPN pool. Eight were
    functional and each one failed DIFFERENTLY for a user whose gateway
    hands out any other range: vpn-connect-script found no VPN IP and
    skipped ALL post-connect routing and DNS; vpn-control-config reported
    the status as disconnected, never removed the leftover virtual
    address, and reported every disconnect as a success;
    vpn-watcher-config returned "no tunnel" so half-up recovery never
    ran; ags-network-scripts showed the network widget as "Aus"; ags-vpn
    showed a red "Half-Up" on a healthy tunnel. The remaining two lines
    documented the same assumption in a comment and a log message.

    An earlier task removed the employer's VALUES; this was BEHAVIOUR and
    needed its own change. The address comes from `swanctl --list-sas`
    now, parsed in src/vpn.py - one derivation for all six.

    Reading it back out of the vpn-active state file would NOT have been
    an alternative, however the marker that used to sit here made it
    sound: vpn-connect.sh wrote `${VPN_IP:-unknown}` into that file, and
    VPN_IP *was* the result of the pattern match, so the file returned
    the same wrong answer one indirection later. The file is a usable
    publication channel for the three readers that have no privileges
    only because what goes into it now comes from swanctl and from
    nowhere else, and because those readers check that exact address
    against the interfaces instead of trusting it.

    This scan is a floor, not the measurement: it catches the literal
    coming back and nothing else. What the six artifacts DO is measured
    by running them - see the section at the end of this file, and
    tests/src/test_vpn_secrets.py.
    """
    offenders = []
    for path in sorted((SRC / "templates").glob("*.template")):
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            if VIRTUAL_IP_ASSUMPTION.search(line):
                offenders.append(f"{path.name}:{number}")
    assert offenders == [], (
        "templates assuming a 10.1.x.x virtual IP: " + "; ".join(offenders))


VPN_PLACEHOLDER = re.compile(r"\{\{STYLE_VPN_[A-Z0-9_]+\}\}")


def _vpn_templates_by_freshness():
    """Split the templates carrying a VPN setting into snapshots and
    live readers.

    A template that reads user-settings.json for itself is current
    whenever it runs, and its substituted values are only fallbacks for
    an absent key. Anything else holds whatever was substituted when it
    was generated, until something regenerates it.
    """
    snapshots, live = set(), set()
    for path in sorted((SRC / "templates").glob("*.template")):
        text = path.read_text(encoding="utf-8")
        if not VPN_PLACEHOLDER.search(text):
            continue
        if "GLib.file_get_contents(SETTINGS_FILE)" in text:
            live.add(path.stem)
        else:
            snapshots.add(path.stem)
    return snapshots, live


def test_every_snapshot_of_the_vpn_settings_has_something_that_refreshes_it():
    """Substituting a value at generation time and never regenerating it
    is a cache with no invalidation.

    Making the scripts read one generated list, instead of each deriving
    its own from the settings file, removed a class of disagreement - but
    it also turned three live readers into snapshots, and the settings
    dialog refreshed exactly one of them. Renaming the connection then
    left vpn-control.sh terminating a name that no longer existed, which
    reports a successful disconnect over a tunnel that is still up, and
    left vpn-watcher.sh re-initiating children under their old names, so
    half-up recovery silently never fired.

    Two sets compared, not a list checked: the next value baked into a
    template has to arrive together with its refresh path.
    """
    snapshots, live = _vpn_templates_by_freshness()

    assert live == {"ags-vpn", "ags-vpn-settings"}, (
        "the exemption is for AGS widgets that re-read the settings file; "
        f"unexpected members: {sorted(live)}")

    dialog = (SRC / "templates" / "ags-vpn-settings.template").read_text(
        encoding="utf-8")
    assert "generate_config.sh" in dialog, "the dialog regenerates nothing at all"
    # The list is matched by its exact shape rather than loosely scanned,
    # so that rewriting the loop into something this test can no longer
    # read fails here instead of quietly matching nothing.
    targets = re.search(r"for \(const target of \[(.*?)\]\)", dialog, re.S)
    assert targets, "the regeneration list is no longer a `for (const target of [...])`"
    regenerated = set(re.findall(r'"-([a-z0-9-]+)"', targets.group(1)))

    assert snapshots == regenerated, (
        "bakes a VPN setting but nothing regenerates it: "
        f"{sorted(snapshots - regenerated)}; "
        "regenerated but bakes no VPN setting: "
        f"{sorted(regenerated - snapshots)}")


def test_a_profile_switch_regenerates_the_same_snapshots():
    """The profile switcher regenerates the VPN scripts too, and it had
    missed the watcher for exactly the reason the dialog had.

    This used to read three `"home")`, `"office")`, `"gaming")` blocks out
    of the switcher and check each of them. Those three names were one
    person's desks; ZepOS ships laptop and desktop, and save-profile lets
    a user coin any name at all. Every one of them reached the `*)` arm,
    which regenerated waybar and the logout menu and nothing else - so
    this test was passing on three branches no installation can enter,
    while the branch every installation DOES enter refreshed none of the
    snapshots it asserts about.

    The switcher no longer branches on the profile name, so this reads
    the one list it now has. Held against the body of the function rather
    than against the whole file, because a `generate_config.sh -x` in the
    reintroduced fallback of a reintroduced branch would satisfy a plain
    text scan while the profile that actually runs refreshes nothing.
    """
    snapshots, _ = _vpn_templates_by_freshness()
    text = (SRC / "templates" / "hyprland-status-config.template").read_text(
        encoding="utf-8")

    assert not re.search(r'^\s*"(?:home|office|gaming)"\)', text, re.M), (
        "the switcher branches on profile names ZepOS does not ship again")

    body = re.search(r"generate_profile_configs\(\) \{\n(.*?)\n\}\n", text, re.S)
    assert body, "generate_profile_configs() is no longer a function this test can read"
    regenerated = set(re.findall(r"generate_config\.sh -([a-z0-9-]+)", body.group(1)))
    assert snapshots <= regenerated, (
        f"a profile switch does not refresh {sorted(snapshots - regenerated)}")


def test_a_blank_watchdog_host_falls_back_instead_of_thrashing(tmp_path, monkeypatch):
    """Unlike the VPN settings, blank is not a meaningful state here: the
    watchdog answers a failed probe by taking the interface down and up
    again, so an empty target repairs a working connection every ten
    seconds, forever.

    Both roots are pointed at an empty temporary directory before the
    import, and every variable that could redirect them is cleared. The
    module reads user-settings.json at import time, so without this the
    result would depend on whether the person running the tests happens
    to have a VPN configured.
    """
    import importlib.util

    monkeypatch.delenv("ZEPOS_SYSTEM_ROOT", raising=False)
    monkeypatch.setenv("ZEPOS_USER_ROOT", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    spec = importlib.util.spec_from_file_location(
        "zepos_style_definition_probe", SRC / "style_definition.py")
    module = importlib.util.module_from_spec(spec)
    # style_definition uses flat imports (paths, vpn) because the
    # generator runs it as a sibling from the system root.
    monkeypatch.syspath_prepend(str(SRC))
    spec.loader.exec_module(module)

    assert module.USER_SETTINGS == {}, "the temporary root was not empty"

    module.USER_SETTINGS = {"watchdog": {"test_host": "   "}}
    assert module.get_user_watchdog_setting("test_host", "1.1.1.1") == "1.1.1.1"
    module.USER_SETTINGS = {"watchdog": {"test_host": " 9.9.9.9 "}}
    assert module.get_user_watchdog_setting("test_host", "1.1.1.1") == "9.9.9.9"
    module.USER_SETTINGS = {}
    assert module.get_user_watchdog_setting("test_host", "1.1.1.1") == "1.1.1.1"


def test_a_blank_entry_is_not_a_network():
    """The settings dialog's "add" button appends an empty string. A
    child with `remote_ts =` and nothing behind it is a configuration
    strongSwan refuses to load - which the user meets as a tunnel that
    will not start, not as the empty row they left behind."""
    assert routed_networks_line(["10.0.0.0/8", "", "  "]) == "10.0.0.0/8"
    assert child_names("work", ["10.0.0.0/8", ""]) == ["work-1"]
    try:
        swanctl_children("work", ["", "   "])
    except ValueError:
        return
    raise AssertionError("a list of blanks must be refused like an empty one")


def test_the_watchdog_test_host_comes_from_the_settings():
    """Ein fest verdrahtetes Sondenziel, in der Wachhundvorlage.

    Es waren zwei, bis das Leistenmodul mit dem Herzsymbol am 11.08.2026
    geloescht wurde. Die verbliebene ist die, die wirklich pingt - der
    Dienst.
    """
    assert defaults()["watchdog"]["test_host"]
    text = (SRC / "templates" / "network-watchdog-config.template").read_text(
        encoding="utf-8")
    assert "8.8.8.8" not in text, "the service still probes a fixed host"
    assert "{{STYLE_WATCHDOG_TEST_HOST}}" in text


# --------------------------------------------------------------------
# a list setting that is not a list
# --------------------------------------------------------------------

def test_one_network_written_as_a_string_is_refused():
    """`"routed_networks": "10.8.0.0/24"` - one network where a list of
    one was meant, and the likeliest hand-edit of this file.

    A str is iterable, so it satisfied the same signature a list does and
    was walked CHARACTER BY CHARACTER: eleven child security
    associations named work-1 to work-11, each with a single digit or a
    dot as its remote_ts, and eleven `ip route add` targets to match.
    This module's premise is to refuse rather than guess, and an input
    that is neither empty nor a list defeats it.
    """
    from src.vpn import nonblank_entries

    for call in (
        lambda: nonblank_entries("10.8.0.0/24"),
        lambda: routed_networks_line("10.8.0.0/24"),
        lambda: child_names("work", "10.8.0.0/24"),
        lambda: swanctl_children("work", "10.8.0.0/24"),
    ):
        with pytest.raises(ValueError) as raised:
            call()
        assert "10.8.0.0/24" in str(raised.value) or "list" in str(raised.value)


def test_a_string_where_a_list_belongs_is_refused_for_every_such_setting():
    """routed_networks is not the only one: dns.servers and
    bypass_networks are read by the same helper and hand-edited the same
    way."""
    from src.vpn import nonblank_entries

    for value in ("10.8.0.0/24", "9.9.9.9", "192.168.178.0/24"):
        with pytest.raises(ValueError):
            nonblank_entries(value)


def test_a_list_of_one_is_still_a_list():
    """The shape that is meant, beside the one that is refused."""
    from src.vpn import nonblank_entries

    assert nonblank_entries(["10.8.0.0/24"]) == ["10.8.0.0/24"]
    assert nonblank_entries(("9.9.9.9", " ")) == ["9.9.9.9"]
    assert nonblank_entries([]) == []
    assert nonblank_entries(None) == []


def test_a_settings_document_with_a_string_network_is_refused():
    """swanctl_config() is what the doctor would report a configuration
    from. Eleven invented children in that report would describe a
    machine nobody has."""
    document = {"vpn": {"server": "gw.example.org",
                        "routed_networks": "10.8.0.0/24"}}
    with pytest.raises(ValueError):
        swanctl_config(document)


# --------------------------------------------------------------------
# which address the tunnel got, and who is allowed to say
# --------------------------------------------------------------------
#
# The six artifacts above used to answer that question six times, each by
# matching interface addresses against one gateway's pool. The tests here
# measure the replacement in the two places it can be measured: the
# parser, against the shape strongSwan actually prints, and the generated
# artifacts, by running them.

from src.vpn import (  # noqa: E402  (grouped with what it belongs to)
    CONNECTED,
    DISCONNECTED,
    HALF_UP,
    HEALTHY,
    NO_TUNNEL,
    STALE,
    address_present,
    assigned_address,
    parse_sas,
    tunnel_health,
    tunnel_status,
)

# TEST-NET-1, reserved for documentation, and deliberately nowhere near
# the range the six artifacts used to look for. Every assertion below
# that finds this address is an assertion the old code could not pass.
ASSIGNED = "192.0.2.42"

# What `swanctl --list-sas` prints on a client whose gateway assigned it
# one address. The shape is strongSwan's own - see the block above
# parse_sas() in src/vpn.py, quoted from list_sas.c - not a guess: the
# port sits in the FIRST bracket of the local line and the virtual
# address in the second, which is why a bracket scan returns 4500.
def _list_sas(*, virtual_address: str = ASSIGNED, established: bool = True,
              installed_children: int = 1) -> str:
    lines = [
        "%s: #1, %s, IKEv2, a1b2c3d4e5f60718_i* 90a1b2c3d4e5f607_r" % (
            "work", "ESTABLISHED" if established else "CONNECTING"),
        "  local  'testnutzer' @ 198.51.100.7[4500]%s" % (
            f" [{virtual_address}]" if virtual_address else ""),
        "  remote '198.51.100.9' @ 198.51.100.9[4500]",
        "  AES_CBC-256/HMAC_SHA2_256_128/PRF_HMAC_SHA2_256/ECP_521",
        "  established 4s ago, rekeying in 13721s",
    ]
    for number in range(1, installed_children + 1):
        lines += [
            "  work-%d: #%d, reqid %d, INSTALLED, TUNNEL, "
            "ESP:AES_CBC-256/HMAC_SHA2_256_128" % (number, number, number),
            "    installed 4s ago, rekeying in 3242s, expires in 3956s",
            "    local  0.0.0.0/0",
            "    remote 203.0.113.0/24",
        ]
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("address", [
    ASSIGNED,
    "172.20.4.9",       # a private range that is not the assumed one
    "10.8.0.5",         # inside 10/8, outside the assumed /16
    "10.1.2.3",         # the assumed range itself still has to work
    "100.64.0.7",       # CGNAT, which some gateways hand out
])
def test_the_assigned_address_is_read_whatever_range_it_is_in(address):
    """The point of the change, stated as a parameter list.

    Five ranges, one of them the range the old code looked for - which
    has to keep working, or this would have swapped one assumption for
    another.
    """
    assert assigned_address(_list_sas(virtual_address=address)) == address


def test_the_port_is_not_read_as_the_address():
    """The local line carries TWO bracketed values when an address was
    assigned and one when it was not, and the first of them is the port.

    Measured because it is the mistake this parser is one line away from:
    `grep -o '\\[[^]]*\\]'` over that line answers 4500, and 4500 would
    then be installed as `ip route add ... src 4500` and written into the
    state file as this tunnel's address.
    """
    report = _list_sas(virtual_address="")
    assert "[4500]" in report, "the fixture no longer contains a port"
    assert assigned_address(report) == ""
    for sa in parse_sas(report):
        assert sa.addresses == ()


def test_a_tunnel_the_gateway_assigned_no_address_to_is_still_a_tunnel():
    """Not every gateway hands out a virtual address; a tunnel that
    routes the client's own address is a working tunnel.

    Three of the six artifacts read "no address" as "not connected",
    which is why the connect script skipped its whole post-connect
    section - routes, DNS, everything - on the same evidence that the
    final check used to report success.
    """
    report = _list_sas(virtual_address="")
    assert tunnel_health(report) == HEALTHY
    assert assigned_address(report) == ""


def test_a_half_up_tunnel_is_not_the_same_as_no_tunnel():
    """The distinction the watcher exists for: IKE up, no data path."""
    assert tunnel_health(_list_sas(installed_children=0)) == HALF_UP
    assert tunnel_health(_list_sas()) == HEALTHY
    assert tunnel_health("") == NO_TUNNEL
    assert tunnel_health(_list_sas(established=False)) == NO_TUNNEL


def test_the_address_belongs_to_this_end_of_the_association():
    """`local-vips` is what the gateway assigned to US. The remote line
    carries the peer's own addresses, and reading one of those would
    point every route and every cleanup at a machine across the
    tunnel."""
    report = _list_sas().replace(
        "  remote '198.51.100.9' @ 198.51.100.9[4500]",
        "  remote '198.51.100.9' @ 198.51.100.9[4500] [203.0.113.254]")
    assert assigned_address(report) == ASSIGNED


def test_an_address_in_a_traffic_selector_is_not_an_assigned_address():
    """A CHILD_SA prints `local  0.0.0.0/0` under itself, two spaces
    deeper and without an identity. Matching `local` loosely would have
    reported 0.0.0.0/0 as the address of a tunnel with no virtual address
    at all."""
    report = _list_sas(virtual_address="")
    assert "    local  0.0.0.0/0" in report, "the fixture lost its selectors"
    assert assigned_address(report) == ""


def test_several_assigned_addresses_are_all_reported():
    """strongSwan prints one bracket per address. A gateway handing out
    an IPv4 and an IPv6 is the normal dual-stack case."""
    report = _list_sas().replace(f"[{ASSIGNED}]", f"[{ASSIGNED}] [2001:db8::42]")
    assert parse_sas(report)[0].addresses == (ASSIGNED, "2001:db8::42")
    assert assigned_address(report) == ASSIGNED


def test_two_children_are_counted_as_two():
    """The connect script writes this number into the state file and the
    bar shows it. It used to `grep -c INSTALLED`, which counts the word
    wherever it appears rather than the CHILD_SAs carrying it."""
    assert parse_sas(_list_sas(installed_children=3))[0].installed_children == 3


# --------------------------------------------------------------------
# what a reader without privileges may say
# --------------------------------------------------------------------

def _fake_ip(addresses):
    """A `subprocess.run` that answers `ip -o addr show` and `pgrep`."""
    def runner(argv, **kwargs):
        import subprocess as sp
        if argv[0] == "pgrep":
            return sp.CompletedProcess(argv, 0 if _fake_ip.charon else 1, "", "")
        text = "".join(
            f"2: eth0    inet {entry} scope global eth0\n" for entry in addresses)
        return sp.CompletedProcess(argv, 0, text, "")
    return runner


_fake_ip.charon = True


def _state(tmp_path, **fields):
    path = tmp_path / "vpn-active"
    document = {"status": "connected", "connection_name": "work"}
    document.update(fields)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_a_recorded_address_that_is_on_an_interface_is_connected(tmp_path):
    _fake_ip.charon = True
    state, runner = _state(tmp_path, virtual_ip=ASSIGNED), _fake_ip([f"{ASSIGNED}/32"])
    assert tunnel_status(state, runner) == (CONNECTED, ASSIGNED)


def test_a_recorded_address_that_has_gone_is_stale_and_still_named(tmp_path):
    """Named, because the disconnect path needs it precisely then: an
    address charon never released has to be taken off the interface by
    the script, and it cannot ask charon for it any more."""
    _fake_ip.charon = True
    state = _state(tmp_path, virtual_ip=ASSIGNED)
    assert tunnel_status(state, _fake_ip(["198.51.100.7/24"])) == (STALE, ASSIGNED)


def test_a_record_without_charon_is_stale(tmp_path):
    _fake_ip.charon = False
    state = _state(tmp_path, virtual_ip=ASSIGNED)
    assert tunnel_status(state, _fake_ip([f"{ASSIGNED}/32"])) == (STALE, ASSIGNED)


def test_a_record_with_no_address_at_all_is_connected_on_the_rest(tmp_path):
    """The tunnel the gateway assigned nothing to. There is nothing to
    verify against the interfaces, and the record plus a live charon is
    all the evidence that exists - refusing to call that connected is
    what left the bar showing a fault over a healthy tunnel."""
    _fake_ip.charon = True
    state = _state(tmp_path, virtual_ip="")
    assert tunnel_status(state, _fake_ip(["198.51.100.7/24"])) == (CONNECTED, "")


def test_no_record_is_disconnected_even_with_charon_running(tmp_path):
    """strongswan.service can be enabled at boot on a machine that has
    never dialled anything. Reporting a permanent fault there would be
    the mirror image of the bug being removed - and without a record
    there is nothing an unprivileged reader could check an address
    against, which is exactly the assumption that got removed."""
    _fake_ip.charon = True
    assert tunnel_status(tmp_path / "vpn-active",
                         _fake_ip([f"{ASSIGNED}/32"])) == (DISCONNECTED, "")


def test_an_unreadable_record_is_no_record(tmp_path):
    path = tmp_path / "vpn-active"
    path.write_text("{ half written", encoding="utf-8")
    _fake_ip.charon = True
    assert tunnel_status(path, _fake_ip([]))[0] == DISCONNECTED


def test_the_prefix_length_comes_back_with_the_address():
    """`ip addr del` needs both, and the disconnect path has only the
    bare address to start from."""
    assert address_present(ASSIGNED, _fake_ip([f"{ASSIGNED}/32"])) == f"{ASSIGNED}/32"
    assert address_present(ASSIGNED, _fake_ip(["192.0.2.43/32"])) == ""
    assert address_present("", _fake_ip([f"{ASSIGNED}/32"])) == ""


# --------------------------------------------------------------------
# the six artifacts, run
# --------------------------------------------------------------------
#
# Everything above this line is a statement about a function or a file.
# What the six artifacts DO with the answer is a separate question, and
# four of the string-presence checks in this file were once shown to be
# unable to fail at all - so the tests below generate the artifacts and
# run them, reading the result out of the stub transcript.
#
# The harness is the one in tests/src/test_vpn_secrets.py: every child
# runs through `env -i` with a stub directory as the WHOLE of PATH, the
# `sudo` stub answers from canned fixtures and never executes anything,
# and no real `swanctl`, `ip` or `sudo` can be reached from here.

from tests.src.test_vpn_secrets import (  # noqa: E402
    BASH,
    _connect_argv,
    generate,          # noqa: F401  (a fixture, used by name)
    policy_patterns,   # noqa: F401
    sandbox,           # noqa: F401
)


def _tunnel_up(sandbox, *, address=ASSIGNED, installed=1, charon=True):
    """A machine whose gateway assigned `address`, or none if it is "".

    The addresses `ip` reports and the report `swanctl` gives are kept in
    step deliberately: the artifacts are supposed to agree with the
    daemon, and a fixture where they cannot would measure nothing.
    """
    sandbox.charon_running(charon)
    sandbox.fixture("route.txt", "default via 198.51.100.1 dev eth0\n")
    sandbox.fixture(
        "addr.txt",
        "2: eth0    inet 198.51.100.7/24 scope global eth0\n"
        + (f"2: eth0    inet {address}/32 scope global eth0\n" if address else ""))
    sandbox.fixture("sas.txt", _list_sas(virtual_address=address,
                                         installed_children=installed))
    sandbox.fixture("initiate.txt", "initiate completed successfully\n")
    sandbox.fixture("reachable.txt",
                    " ".join(filter(None, [address, "198.51.100.1",
                                           "198.51.100.8", "1.1.1.1"])) + "\n")
    return sandbox


def _record(sandbox, address=ASSIGNED):
    """The state file, as vpn-connect.sh writes it."""
    path = sandbox.runtime / "vpn-active"
    path.write_text(json.dumps({
        "status": "connected", "connection_name": "work",
        "server": "198.51.100.9", "virtual_ip": address,
        "installed_children": 1,
    }) + "\n", encoding="utf-8")
    return path


@pytest.mark.allow_subprocess
def test_the_connect_script_routes_from_the_address_strongswan_reported(
        sandbox, generate, policy_patterns):
    """The first of the six failures, measured on the artifact.

    Every post-connect step - routes in the main table, routes in table
    220, the local-network passthrough, the bypass networks, DNS - sat
    inside `if [ -n "$VPN_IP" ]`, and VPN_IP was the result of matching
    interface addresses against one gateway's pool. For a user with any
    other address the tunnel came up and NONE of it ran.
    """
    _tunnel_up(sandbox)
    sandbox.policy(policy_patterns)
    script = generate("vpn-connect-script", "vpn-connect.sh")

    result = sandbox.run(_connect_argv(script))

    assert result.returncode == 0, result.stdout + result.stderr
    added = [line for line in sandbox.transcript()
             if line.startswith("sudo-allowed ") and "ip route add" in line]
    assert added, ("no route was installed at all: "
                   + "; ".join(sandbox.transcript()))
    for line in added:
        assert f"src {ASSIGNED}" in line, (
            f"a route was installed from an address nobody assigned: {line}")

    assert any("tee /etc/resolv.conf" in line for line in sandbox.transcript()), (
        "DNS was never written: " + "; ".join(sandbox.transcript()))

    recorded = json.loads((sandbox.runtime / "vpn-active").read_text(
        encoding="utf-8"))
    assert recorded["virtual_ip"] == ASSIGNED
    assert recorded["installed_children"] == 1


@pytest.mark.allow_subprocess
def test_a_tunnel_with_no_assigned_address_is_still_routed_and_resolved(
        sandbox, generate, policy_patterns):
    """The edge the old code could not express at all.

    A gateway that routes the client's own address assigns no virtual
    address, and `ip addr show | grep <pool>` answers the same empty
    string for that as it does for a tunnel that never came up. The
    connect script has to set the routes anyway - without a `src` hint,
    because there is no address to hint with - and has to write DNS.
    """
    _tunnel_up(sandbox, address="")
    sandbox.policy(policy_patterns)
    script = generate("vpn-connect-script", "vpn-connect.sh")

    result = sandbox.run(_connect_argv(script))

    assert result.returncode == 0, result.stdout + result.stderr
    added = [line for line in sandbox.transcript()
             if line.startswith("sudo-allowed ") and "ip route add" in line]
    assert added, "the tunnel carried no routes at all"
    for line in added:
        assert " src " not in line, (
            f"a route was installed from an address that was never "
            f"assigned: {line}")

    assert any("tee /etc/resolv.conf" in line for line in sandbox.transcript()), (
        "DNS was skipped for a working tunnel")

    recorded = json.loads((sandbox.runtime / "vpn-active").read_text(
        encoding="utf-8"))
    assert recorded["virtual_ip"] == "", (
        "an address was invented for a tunnel that was assigned none")


@pytest.mark.allow_subprocess
def test_the_connect_script_fails_when_there_is_no_association_at_all(
        sandbox, generate, policy_patterns):
    """The other side of the same branch: nothing established.

    "No address" and "no tunnel" have to end differently, or the script
    reports a successful connection over a machine that never dialled.
    """
    _tunnel_up(sandbox)
    sandbox.fixture("sas.txt", "")
    sandbox.policy(policy_patterns)
    script = generate("vpn-connect-script", "vpn-connect.sh")

    result = sandbox.run(_connect_argv(script))

    assert result.returncode != 0, result.stdout + result.stderr
    assert not (sandbox.runtime / "vpn-active").exists(), (
        "a connection nothing established was recorded as one")


@pytest.mark.allow_subprocess
def test_the_watcher_repairs_a_half_up_tunnel_on_any_address(
        sandbox, generate, policy_patterns):
    """check_tunnel_health() opened with a pre-check on an address from
    one gateway's pool, meant as a cheap way out before sudo. For every
    other gateway it answered "no tunnel", so the repair this service
    exists for never ran - on the one machine state it is there for.
    """
    _tunnel_up(sandbox, installed=0)
    sandbox.policy(policy_patterns)
    _record(sandbox)
    script = generate("vpn-watcher-config", "vpn-watcher.sh")

    result = sandbox.run([BASH, str(script), "--once"], timeout=30)

    assert result.returncode == 0, result.stdout + result.stderr
    log = sandbox.home / ".local" / "share" / "vpn-logs" / "vpn-watcher.log"
    assert log.exists(), "the watcher wrote no log"
    assert "Re-initiated CHILD_SA" in log.read_text(encoding="utf-8"), (
        log.read_text(encoding="utf-8"))


@pytest.mark.allow_subprocess
def test_the_watcher_leaves_a_healthy_tunnel_alone(sandbox, generate,
                                                   policy_patterns):
    """The counterpart, so that "it repairs" is not satisfied by a
    watcher that re-initiates on every round."""
    _tunnel_up(sandbox)
    sandbox.policy(policy_patterns)
    _record(sandbox)
    script = generate("vpn-watcher-config", "vpn-watcher.sh")

    sandbox.run([BASH, str(script), "--once"], timeout=30)

    initiated = [line for line in sandbox.transcript() if "--initiate" in line]
    assert initiated == [], (
        "a healthy tunnel was re-initiated: " + "; ".join(initiated))


@pytest.mark.allow_subprocess
def test_the_disconnect_takes_off_the_address_that_was_assigned(
        sandbox, generate, policy_patterns):
    """Two of the six failures at once.

    The leftover virtual address was matched with a pattern, so on any
    other gateway it stayed on the interface after a disconnect - and the
    final check used the same pattern, so it never matched either and
    every disconnect reported success. Here the address is still there
    when the teardown ends (the stubs do not really remove it), and that
    has to be a FAILURE.

    charon is stopped in this fixture deliberately, so the surviving
    address is the ONLY thing that can decide the verdict. With charon
    still running this test passed over a version that had stopped
    looking at the address at all - measured, not assumed.
    """
    _tunnel_up(sandbox, charon=False)
    sandbox.policy(policy_patterns)
    state = _record(sandbox)
    script = generate("vpn-control-config", "vpn-control.sh")

    result = sandbox.run([BASH, str(script), "disconnect"])

    assert any(f"ip addr del {ASSIGNED}/32" in line
               for line in sandbox.transcript()), (
        "the virtual address was never taken off the interface: "
        + "; ".join(sandbox.transcript()))
    assert result.returncode != 0, (
        "a disconnect that left the address in place reported success")
    assert state.exists(), (
        "the record was dropped although the tunnel is still up")


@pytest.mark.allow_subprocess
def test_a_disconnect_that_worked_drops_the_record(sandbox, generate,
                                                    policy_patterns):
    """The success path, so the failure above is not simply "it always
    fails now": charon is gone and the address is off the interface."""
    _tunnel_up(sandbox, address="", charon=False)
    sandbox.policy(policy_patterns)
    state = _record(sandbox)
    script = generate("vpn-control-config", "vpn-control.sh")

    result = sandbox.run([BASH, str(script), "disconnect"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert not state.exists(), "the record survived a successful disconnect"


@pytest.mark.allow_subprocess
def test_the_control_script_reports_the_state_it_is_in(sandbox, generate,
                                                       policy_patterns):
    """`vpn-control.sh status` answered "disconnected" for every user
    whose gateway is not the one it was written for."""
    _tunnel_up(sandbox)
    sandbox.policy(policy_patterns)
    _record(sandbox)
    script = generate("vpn-control-config", "vpn-control.sh")

    result = sandbox.run([BASH, str(script), "status"])

    assert result.stdout.strip() == CONNECTED, result.stdout + result.stderr


@pytest.mark.allow_subprocess
def test_the_network_widget_names_the_tunnel_instead_of_saying_off(
        sandbox, generate):
    """ags-network-scripts' VPN row said "Aus" over a working tunnel."""
    _tunnel_up(sandbox)
    _record(sandbox)
    script = generate("ags-network-scripts", "ags-network-scripts")

    result = sandbox.run([BASH, str(script), "vpn"])

    assert result.stdout.strip() == f"Verbunden ({ASSIGNED})", (
        result.stdout + result.stderr)


@pytest.mark.allow_subprocess
def test_the_vpn_widget_asks_the_same_question_and_gets_the_same_answer(
        sandbox, generate):
    """A .template written in TypeScript cannot be executed by this
    suite, so what is executed is the argv it produces - the same
    measurement test_ags_exec.py makes, at the one point that matters
    here. The widget used to run `ip addr show` and match the output
    against one gateway's pool, which is why it showed a red "VPN
    unvollständig" on a healthy tunnel.
    """
    _tunnel_up(sandbox)
    _record(sandbox)
    widget = generate("ags-vpn", "vpn.tsx")

    written = re.search(r"const VPN_STATUS_QUERY = (\[.*?\])",
                        widget.read_text(encoding="utf-8"))
    assert written, "the widget no longer asks a command anything"
    argv = json.loads(written.group(1))

    result = sandbox.run(argv)

    assert result.stdout.split() == [CONNECTED, ASSIGNED], (
        result.stdout + result.stderr)
