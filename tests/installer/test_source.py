# SPDX-License-Identifier: GPL-3.0-or-later
import urllib.error

from installer.core.source import (
    ONLINE_REPO_URL,
    PackageSource,
    REPO_DATABASE,
    database_url,
    internet_reachable,
    mirror_config,
    probe,
    repository_available,
    resolve_repo_url,
)


class _Response:
    """The smallest thing urlopen() can return that this code reads."""

    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _answering(*replies):
    """An opener that gives each reply in turn and records the requests.

    A reply is either a status code or an exception to raise.
    """
    seen: list[tuple[str, str]] = []
    remaining = list(replies)

    def opener(request, timeout=None):
        seen.append((request.get_method(), request.full_url))
        assert remaining, "the code under test made more requests than this opener answers"
        reply = remaining.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _Response(reply)

    opener.seen = seen  # type: ignore[attr-defined]
    return opener


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        database_url(), code, "no", hdrs=None, fp=None  # type: ignore[arg-type]
    )


def test_the_probe_asks_the_repository_it_is_deciding_about():
    """The defect this replaces, in one assertion.

    probe() used to open a socket to archlinux.org and read a successful
    connection as "the ZepOS repository is there". Those are two
    different questions and the answer to the first says nothing about
    the second: a real installation reached the erase, then died on
    `failed retrieving file 'zepos.db' ... 404`, on a machine whose
    network was perfect.
    """
    opener = _answering(200)
    assert repository_available(opener=opener) is True
    method, url = opener.seen[0]  # type: ignore[attr-defined]
    assert method == "HEAD"
    assert url.endswith("/" + REPO_DATABASE)
    assert "archlinux.org" not in url


def test_arch_is_resolved_before_the_question_is_asked():
    """$arch is a pacman variable, not a path component.

    Left unexpanded it asks a static host for a directory called
    "$arch", which answers 404 - indistinguishable from the answer an
    unpublished repository gives, and one of those is a bug here.
    """
    assert resolve_repo_url(machine="x86_64") == "https://zeptronit.github.io/ZepOS/x86_64"
    assert "$arch" not in database_url(machine="x86_64")
    assert database_url(machine="x86_64").endswith("/x86_64/zepos.db")
    assert "$" not in database_url(machine="aarch64")


def test_the_database_is_asked_for_and_not_the_directory():
    """A directory listing proves nothing about a pacman repository."""
    assert database_url(machine="x86_64") == ONLINE_REPO_URL.replace(
        "$arch", "x86_64") + "/zepos.db"


def test_a_published_repository_is_used():
    assert probe(check=lambda: repository_available(opener=_answering(200))) \
        is PackageSource.ONLINE


def test_a_repository_that_was_never_published_falls_back_to_the_medium():
    """404. Today's state, and the one that cost an installation."""
    assert repository_available(opener=_answering(_http_error(404))) is False
    assert probe(check=lambda: repository_available(opener=_answering(_http_error(404)))) \
        is PackageSource.OFFLINE


def test_a_published_repository_that_cannot_be_reached_falls_back_too():
    """Blocked, down, or behind a captive portal.

    The offline repository is on the medium and always complete, so this
    installation finishes. The previous probe got this case right only by
    accident - it happened to fail the same socket it was measuring.
    """
    for failure in (urllib.error.URLError("no route"),
                    TimeoutError("took too long"),
                    ValueError("certificate verify failed"),
                    _http_error(503)):
        assert repository_available(opener=_answering(failure)) is False


def test_a_host_that_refuses_head_is_asked_again_with_a_range():
    """405 says nothing about whether the database is there.

    Reading it as "not published" would send every installation to the
    medium the day the repository moves to a host that dislikes HEAD -
    silently, because installing from the medium works.
    """
    opener = _answering(_http_error(405), 206)
    assert repository_available(opener=opener) is True
    methods = [method for method, _url in opener.seen]  # type: ignore[attr-defined]
    assert methods == ["HEAD", "GET"]


def test_probe_never_raises_whatever_the_check_does():
    """Its whole job is to decide."""
    class Exploding:
        def __call__(self):
            raise RuntimeError("boom")

    assert probe(check=Exploding()) is PackageSource.OFFLINE


def test_internet_reachability_is_still_asked_and_is_a_different_question():
    """The wireless step needs it, and needs it not to be the repository.

    A user who has just joined a working WLAN must not be told there is
    no internet because nobody has published a package repository yet.
    """
    assert internet_reachable(connect=lambda *a, **k: _Response(200)) is True

    def refused(*_args, **_kwargs):
        raise OSError("connection refused")

    assert internet_reachable(connect=refused) is False


def test_probe_returns_online_when_reachable():
    assert probe(check=lambda: True) is PackageSource.ONLINE


def test_probe_falls_back_to_offline():
    assert probe(check=lambda: False) is PackageSource.OFFLINE


def test_probe_treats_check_error_as_offline():
    def boom():
        raise OSError("no network")

    assert probe(check=boom) is PackageSource.OFFLINE


def test_offline_repo_points_at_the_iso():
    cfg = mirror_config(PackageSource.OFFLINE)
    repo = cfg["custom_repositories"][0]
    assert repo["name"] == "zepos"
    assert repo["url"] == "file:///opt/zepos-repo"
    assert cfg["mirror_regions"] == {}


def test_online_adds_zepos_without_naming_a_mirror_region():
    """A named region is not a list of mirrors, it is a lookup key.

    Verified against archinstall 4.4: regions_config() ignores the URLs
    passed here and asks its own MirrorListHandler for the region NAME.
    When that handler has fallen back to the live medium's mirrorlist,
    "Germany" resolves to nothing but a comment header - and the
    installed system inherits a mirrorlist with no servers in it. A
    reflector-generated mirrorlist has no country headers at all, and the
    lookup is a plain dict subscript that then raises KeyError mid
    installation. Empty means archinstall writes no mirrorlist, which is
    also what spec 8.7's pinned ALA snapshot requires.
    """
    cfg = mirror_config(PackageSource.ONLINE)
    assert cfg["custom_repositories"][0]["name"] == "zepos"
    assert cfg["mirror_regions"] == {}


def test_zepos_repo_requires_signatures():
    """Unsigned packages must not slip through - see spec 8.6."""
    for source in PackageSource:
        repo = mirror_config(source)["custom_repositories"][0]
        assert repo["sign_check"] == "Required"


def test_probe_treats_any_exception_as_offline():
    """ssl.CertificateError is a ValueError, not an OSError. A probe that
    cannot decide must fall back, not abort the installation."""
    def boom():
        raise ValueError("certificate verify failed")

    assert probe(check=boom) is PackageSource.OFFLINE


def test_probe_still_lets_keyboard_interrupt_through():
    """The user pressing Ctrl-C must not be swallowed as "no network"."""
    def interrupted():
        raise KeyboardInterrupt

    try:
        probe(check=interrupted)
    except KeyboardInterrupt:
        return
    raise AssertionError("KeyboardInterrupt was swallowed")
