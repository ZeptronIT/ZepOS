# SPDX-License-Identifier: GPL-3.0-or-later
"""Decide where the ZepOS packages come from: the published repository or
the one on the medium.

WHAT THIS MODULE DECIDES, AND WHAT IT USED TO ASK
    probe() used to open a socket to archlinux.org:443 and return ONLINE
    when it connected. That answers *is there internet*, which is a
    different question from *does the ZepOS repository exist*, and the
    difference is not academic - it cost a real installation, after the
    erase:

        Error: failed retrieving file 'zepos.db' from zeptronit.github.io:
               The requested URL returned error: 404

    Nothing has ever been published to ONLINE_REPO_URL, so every machine
    with a working network was sent to a repository that is not there,
    while the one on the ISO - always present, always complete - was
    chosen only when there was no network at all. The better the
    connection, the more certain the failure.

    So the question is now asked of the thing being decided: a HEAD on
    the repository's own database. The answer then means what the
    variable means, and it stays right in all three states -

        published and reachable      ONLINE
        published, blocked or down   OFFLINE, and the installation
                                     completes from the medium
        never published (today)      OFFLINE, which is what the smoke
                                     image has always installed from

    Note what this is NOT. OFFLINE moves only the [zepos] repository to
    file:///opt/zepos-repo; mirror_config() leaves mirror_regions empty
    either way, so the BASE system still comes over the network from the
    pinned ALA snapshot in both cases (spec §8.4). "Offline" here is a
    statement about ZepOS's own packages and about nothing else.

    Whether the live session can reach the internet is still a real
    question - the wireless step asks it - and internet_reachable() is
    where it now lives, in its own function, under its own name.
"""
from __future__ import annotations

import enum
import platform
import socket
import urllib.error
import urllib.request
from typing import Any, Callable

# The name pacman knows the repository by, in the [zepos] section header
# of every pacman.conf that mentions it. Spelled once here because three
# places depend on the same string and cannot check each other:
# packaging/build.sh names the database zepos.db.tar.gz, the ISO serves
# it, and pacmanconf.py has to FIND the section archinstall wrote in
# order to replace it (spec §8.5b). A rename in one of the three would
# leave a target with two repositories under two names, both of them
# half-right.
REPO_NAME = "zepos"

OFFLINE_REPO_URL = "file:///opt/zepos-repo"
# GitHub Pages serves a static directory, which is all pacman needs from a
# repository: no server to run, no certificate to renew, no availability to
# promise. The alternative considered was a host under our own domain; for a
# project whose first users can be counted on one hand, operating one buys
# nothing that this does not already provide.
#
# What puts a directory there is packaging/publish.sh - an orphan commit on
# gh-pages, checked against the key published beside it, and never pushed by
# the script itself. Nothing has been published yet, and packaging/README.md's
# "Publishing" says both why not and how the whole update path was measured
# without it: iso/test-boot.py --scenario update lets an installed system
# upgrade itself from exactly this layout, served locally.
#
# probe() asks this URL directly, so "nothing has been published yet" is
# no longer a fact that has to be remembered in the places that use it -
# it is measured, once, and answered with OFFLINE. The day publish.sh
# pushes, the same code returns ONLINE with nothing to change here.
ONLINE_REPO_URL = "https://zeptronit.github.io/ZepOS/$arch"


# The file pacman asks for first, and the one whose absence produced the
# 404 above. Spelled from REPO_NAME so it cannot drift from the section
# header, the database packaging/build.sh writes, or the file publish.sh
# stages.
REPO_DATABASE = f"{REPO_NAME}.db"

# Five seconds, the same budget the socket check had. This runs once, in
# front of an installation that takes twenty minutes, and a user on a
# captive-portal network must not wait on it: an unanswered probe is an
# installation from the medium, which works.
PROBE_TIMEOUT = 5.0

# Status codes that mean "not that method", rather than "not that file".
# A host answering any of these to a HEAD has said nothing about whether
# the database is there, so the probe asks again with a GET rather than
# reading the refusal as an absent repository. GitHub Pages answers HEAD
# properly; the fallback is for the day the repository moves somewhere
# that does not.
_METHOD_REFUSED = frozenset({400, 403, 405, 501})


class PackageSource(enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"


def resolve_repo_url(url: str = ONLINE_REPO_URL, *, machine: str | None = None) -> str:
    """Expand pacman's variables so the string can actually be fetched.

    `$arch` and `$repo` are pacman.conf variables. Pacman substitutes
    them when it builds a request; nothing else does. Handing
    ONLINE_REPO_URL to urllib unchanged asks a static host for a
    directory literally named `$arch`, which answers 404 - the same
    answer an unpublished repository gives. Those two must never be
    confusable, because one of them is a bug in this file and the other
    is the state the project is actually in.
    """
    machine = machine or platform.machine()
    return url.replace("$arch", machine).replace("$repo", REPO_NAME)


def database_url(url: str = ONLINE_REPO_URL, *, machine: str | None = None) -> str:
    """The URL of the repository database itself.

    Not the directory: a directory listing proves nothing about a pacman
    repository, and a static host may answer one for a path that carries
    no database at all.
    """
    return f"{resolve_repo_url(url, machine=machine).rstrip('/')}/{REPO_DATABASE}"


def url_reachable(
    target: str,
    *,
    opener: Callable[..., Any] | None = None,
    timeout: float = PROBE_TIMEOUT,
) -> bool:
    """Whether exactly this URL can be fetched.

    Nothing is downloaded: a HEAD asks the one question that matters, and
    the fallback GET carries a Range header so a host that ignores HEAD
    still costs a byte rather than a database.

    Never raises for a network reason. Every way this can fail - no
    route, no DNS, a certificate that does not verify, a 404, a proxy
    that answers HTML - means the same thing to the caller: that file is
    not obtainable from here. `opener` is injected rather than bound, so
    the three states this function distinguishes can be tested without a
    network and without publishing anything.

    Getrennt von repository_available() seit dem 17.08.2026, und nicht
    aus Ordnungsliebe: installer/core/preflight.py muss dieselbe Frage
    nach einer ANDEREN Datei stellen - nach `core.db` auf dem
    festgenagelten ALA-Spiegel, von dem die Arch-Basis kommt. Solange
    der Datenbankname hier eingebacken war, blieb dieser Stelle nur, den
    ganzen Ablauf ein zweites Mal hinzuschreiben, und zwei Fassungen von
    "erreichbar" haetten frueher oder spaeter zwei verschiedene
    Antworten auf eine Frage gegeben.
    """
    opener = opener or urllib.request.urlopen

    def _ok(response: Any) -> bool:
        status = getattr(response, "status", None)
        if status is None:
            status = response.getcode()
        return 200 <= int(status) < 300

    try:
        with opener(urllib.request.Request(target, method="HEAD"), timeout=timeout) as response:
            return _ok(response)
    except urllib.error.HTTPError as refusal:
        if refusal.code not in _METHOD_REFUSED:
            # 404 lands here, and it is the answer rather than an error:
            # the repository is not published at this URL.
            return False
    except Exception:
        # Deliberately broad, and for the same reason probe() is: an
        # unreachable repository is a fallback, never a reason to abort
        # an installation. socket.timeout, ssl.SSLCertVerificationError
        # (a ValueError) and http.client's own exceptions are not all
        # OSError. BaseException still propagates.
        return False

    try:
        request = urllib.request.Request(target)
        request.add_header("Range", "bytes=0-0")
        with opener(request, timeout=timeout) as response:
            return _ok(response)
    except Exception:
        return False


def repository_available(
    url: str = ONLINE_REPO_URL,
    *,
    opener: Callable[..., Any] | None = None,
    timeout: float = PROBE_TIMEOUT,
    machine: str | None = None,
) -> bool:
    """Whether the ZepOS repository's database can be fetched from `url`.

    The question probe() asks. Which file that is - `zepos.db`, spelled
    from REPO_NAME - is decided here; whether a URL answers is decided by
    url_reachable() above, so the two cannot drift apart.
    """
    return url_reachable(
        database_url(url, machine=machine), opener=opener, timeout=timeout
    )


def internet_reachable(
    *,
    connect: Callable[..., Any] | None = None,
    timeout: float = PROBE_TIMEOUT,
) -> bool:
    """Whether this machine can reach the outside world at all.

    The question probe() used to ask and no longer does. It still has one
    caller - wifi.associate() checks whether the network it just joined
    leads anywhere - and that caller wants exactly this and not the
    repository question: a machine on a working network whose ZepOS
    repository happens to be unpublished has an internet connection, and
    telling its user otherwise while they are typing a WLAN passphrase
    would send them looking for a fault that is not theirs.
    """
    connect = connect or socket.create_connection
    try:
        with connect(("archlinux.org", 443), timeout=timeout):
            return True
    except Exception:
        return False


def _default_check() -> bool:
    return repository_available()


def probe(*, check: Callable[[], bool] | None = None) -> PackageSource:
    # Resolve check at call time, not import time, so the test isolation
    # guard can intercept it. Never bind a function default argument.
    check = check or _default_check
    try:
        return PackageSource.ONLINE if check() else PackageSource.OFFLINE
    except Exception:
        # Deliberately broad. This function's whole job is to decide, never
        # to fail: an injected check may raise ssl.CertificateError (a
        # ValueError), subprocess.CalledProcessError or an HTTP exception,
        # none of which are OSError. Any failure means "the repository is
        # not there", which is a fallback, not a reason to abort the
        # installation.
        # BaseException (KeyboardInterrupt, SystemExit) still propagates.
        return PackageSource.OFFLINE


def mirror_config(source: PackageSource) -> dict[str, Any]:
    zepos_repo = {
        "name": REPO_NAME,
        "url": OFFLINE_REPO_URL if source is PackageSource.OFFLINE else ONLINE_REPO_URL,
        "sign_check": "Required",
        "sign_option": "TrustedOnly",
    }
    # Deliberately empty, for both sources. Read against archinstall 4.4:
    # MirrorConfiguration.parse_args turns each mirror_regions entry into a
    # MirrorRegion, and regions_config() then IGNORES the URLs given here -
    # it asks MirrorListHandler.get_status_by_region(name) instead, i.e.
    # only the region NAME is load-bearing. Installer.set_mirrors()
    # overwrites the target's mirrorlist with whatever comes back, but
    # only when the result is non-empty.
    #
    # Naming a region therefore has two failure modes and no upside here.
    # If the mirror status API cannot be reached, the handler falls back
    # to the live medium's own mirrorlist, whose "## Germany" section on
    # an Arch ISO contains nothing but commented-out servers - the
    # installed system then gets a mirrorlist consisting of one comment
    # line. If that ISO's mirrorlist has no country headers at all (a
    # reflector-generated one has none), the lookup is a plain dict
    # subscript and raises KeyError in the middle of the installation.
    #
    # It also contradicts spec §8.7: the base system is meant to come
    # from the pinned Arch Linux Archive snapshot the ISO carries, not
    # from whichever German mirror is fastest today. Leaving this empty
    # means archinstall writes no mirrorlist at all, which keeps the
    # decision where the pinning lives.
    regions: dict[str, list[str]] = {}

    return {
        "custom_servers": [],
        "mirror_regions": regions,
        "optional_repositories": [],
        "custom_repositories": [zepos_repo],
    }
