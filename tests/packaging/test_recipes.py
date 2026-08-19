# SPDX-License-Identifier: GPL-3.0-or-later
"""The packaging recipes, checked without building a package.

WHY THESE TESTS EXIST
    A package build takes minutes and needs Docker and root; a repository
    build needs a signing key on top. None of that belongs in a suite
    that has to run in two minutes on a laptop. What CAN be read from the
    recipes is every property whose absence would be discovered late and
    expensively:

      * a version written into a recipe instead of derived from VERSION -
        found on the day two packages disagree about which release they
        belong to;
      * an unpinned or unchecksummed upstream source - found on the day
        upstream moves and the build produces something else;
      * a container without --network host - found immediately, but only
        by whoever has this machine's VPN up (spec §10.1);
      * a path a package owns still named in the ISO profile's
        file_permissions - found as a fatal mkarchiso error twenty
        minutes into an image build;
      * key material that could be committed - found by whoever clones.

    packaging/verify-install.sh does the half this cannot: it installs
    the built packages into a clean container and looks at the files.

WHAT IT DELIBERATELY DOES NOT DO
    It does not build, sign or install anything, and it does not run
    makepkg. Everything here is a file read.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "packaging"
ISO_PROFILE = ROOT / "iso" / "profile"

# The recipes that carry ZepOS's own code, as opposed to a packaged
# upstream. Only these derive their version from VERSION - astal and AGS
# have upstream versions, and inventing a ZepOS number for them would
# hide which upstream release is installed.
#
# Am 11.08.2026 sind zwei Plugin-Rezepte dazugekommen: zepos-hyprlaunch
# und zepos-hyprclipx bauten von da an aus plugins/ in DIESEM Baum,
# nicht mehr aus einem Tarball von github.com/azzuriel. Am 19.08.2026
# ist das WOHER zurueckgedreht worden - die Sicherheitspruefung vor der
# Veroeffentlichung von ZepOS (.superpowers/sdd/2026-08-18-ags-schale-
# und-breitenleiter/sicherheitsanalyse.md, Abschnitt 6) hat benannt,
# dass der Ursprungsbaum keine Lizenz traegt und eine bearbeitete Kopie
# davon im eigenen Repository zu fuehren immer noch eine Kopie ist. Die
# beiden Rezepte holen ihre Quelle seither wieder von github.com/
# azzuriel, auf einen Commit gepinnt, und wenden ZepOS' eigenes Diff an
# (packaging/zepos-hyprlaunch/zepos-hyprlaunch.patch, packaging/
# zepos-hyprclipx/zepos-hyprclipx.patch). Das WAS ist dabei nicht
# zurueckgedreht: das Aussehen der beiden Fenster kommt weiterhin aus
# src/brand.py und src/sizes.py, uebertragen durch den Patch statt
# durch eine Datei im Arbeitsbaum, und ist damit weiterhin ZepOS'
# eigener Code, an dessen Versionsnummer haengend - nicht die des
# gepinnten Commits.
#
# Die drei uebrigen Plugin-Rezepte bleiben draussen und das ist eine
# Entscheidung mit Messung, nicht ein Rest:
#   hyprzones          weiterhin ein fremder Tarball, gepinnt auf einen
#                      Commit. Es hat keine eigene Oberflaeche, die auf
#                      die Marke zu bringen waere.
#   hyprland-plugins   hyprbars und borders-plus-plus kommen vom
#                      Hyprland-Projekt selbst - 1433 Sterne, 69
#                      Beitragende, Tags im Gleichschritt mit dem
#                      Compositor. Uebernehmen hiesse, diese Pflege
#                      selbst zu leisten.
# tests/src/test_own_plugins.py haelt beide Entscheidungen fest, mit den
# Zahlen, auf denen sie stehen.
OWN_RECIPES = ("zepos-config", "zepos-installer", "zepos-keyring",
               "zepos-menu", "zepos-settings-gui", "zepos-lock",
               "zepos-desktop",
               "zepos-hyprlaunch", "zepos-hyprclipx")


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


def _recipes() -> list[Path]:
    found = sorted(PACKAGING.glob("*/PKGBUILD"))
    assert found, "no PKGBUILD under packaging/"
    return found


def _pkgbuild(name: str) -> str:
    return _read(PACKAGING / name / "PKGBUILD")


def _code(text: str) -> str:
    """The text with whole-line comments removed.

    Every file in packaging/ explains what it does NOT do as carefully as
    what it does - the AGS recipe quotes the `npm install` it refuses to
    run, packaging/build.sh quotes the --network host rule it is
    obeying - and a scan that reads those explanations as code finds a
    defect in the paragraph describing its absence.
    """
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def _build_order() -> list[str]:
    """The PACKAGES array of packaging/build.sh.

    Parsed rather than sourced: sourcing a shell script from the
    repository inside the test process is what the suite's isolation
    guard exists to prevent.
    """
    body = re.search(r"readonly PACKAGES=\((.*?)\n\)", _read(PACKAGING / "build.sh"), re.S)
    assert body, "packaging/build.sh has no PACKAGES array"
    return [line.strip() for line in body.group(1).splitlines() if line.strip()]


def _file_permissions() -> dict[str, str]:
    text = _read(ISO_PROFILE / "profiledef.sh")
    body = re.search(r"file_permissions=\((.*?)\n\)", text, re.S)
    assert body, "profiledef.sh has no file_permissions array"
    return dict(re.findall(r'\["([^"]+)"\]="([^"]+)"', body.group(1)))


def _packages_x86_64() -> set[str]:
    return {line.strip() for line in _read(ISO_PROFILE / "packages.x86_64").splitlines()
            if line.strip() and not line.startswith("#")}


# --------------------------------------------------------------------
# One version, in one place
# --------------------------------------------------------------------

def test_the_version_file_holds_something_pacman_would_accept():
    """VERSION is the single source spec §4.2's fifteen packages read.

    A pkgver may not contain a hyphen or a colon - pacman uses both as
    field separators in a package file name - and an empty file would
    produce `zepos-config--1-any.pkg.tar.zst`, which installs and then
    compares wrongly against every later release.
    """
    version = _read(ROOT / "VERSION").strip()
    assert version, "VERSION is empty"
    assert re.fullmatch(r"[0-9][0-9A-Za-z._+]*", version), (
        f"{version!r} is not usable as a pkgver")


@pytest.mark.parametrize("name", OWN_RECIPES)
def test_our_recipes_read_the_version_rather_than_repeat_it(name):
    """A version repeated in fifteen recipes is wrong in some of them by
    the second release. Each reads VERSION relative to its own location,
    so `makepkg` in the recipe directory and packaging/build.sh from the
    repository root produce the same number."""
    text = _pkgbuild(name)
    assert 'pkgver="$(<"$_zepos_repo/VERSION")"' in text, (
        f"{name} does not take its version from VERSION")
    assert re.search(r'_zepos_repo="\$\(cd -- "\$\(dirname -- "\$\{BASH_SOURCE\[0\]}"\)/\.\./\.\." && pwd\)"',
                     text), (
        f"{name} resolves VERSION from somewhere other than its own "
        f"location; makepkg run from the recipe directory would miss it")


# --------------------------------------------------------------------
# Upstream sources have to be pinned, or the build is not a build
# --------------------------------------------------------------------

@pytest.mark.parametrize("recipe", [p.parent.name for p in _recipes()])
def test_every_remote_source_carries_a_real_checksum(recipe):
    """Spec §4.3 rejected the AUR because its packages have "no cut-off
    date, no signature, no promise they still build tomorrow". A recipe
    with sha256sums=('SKIP') on a URL reintroduces exactly that: the
    build fetches whatever is at the address today.

    A local source - one packaging/build.sh produces from this tree
    moments earlier - is exempt, because a checksum of a file the same
    script just wrote verifies nothing.
    """
    text = _pkgbuild(recipe)
    sources = re.findall(r'^\s*"?([^"\s]+::)?(https?://[^"\s]+)"?', text, re.M)
    sums = re.search(r"sha256sums=\((.*?)\)", text, re.S)

    if not sources:
        return
    assert sums, f"{recipe} fetches from the network and has no sha256sums"
    values = re.findall(r"'([0-9a-fA-F]{64}|SKIP)'", sums.group(1))
    assert len(values) >= len(sources), (
        f"{recipe} has {len(sources)} remote sources and {len(values)} checksums")
    assert "SKIP" not in values[:len(sources)], (
        f"{recipe} skips the checksum of a source it downloads")


@pytest.mark.parametrize("recipe", [p.parent.name for p in _recipes()])
def test_no_recipe_builds_from_a_moving_reference(recipe):
    """`source=("git+...")` without a commit is a package whose contents
    are decided by the day it was built. astal has no tags at all - every
    AUR recipe for it is a -git package - so it is pinned by commit hash
    and the tarball at that hash is checksummed."""
    text = _pkgbuild(recipe)
    assert "git+" not in text, (
        f"{recipe} builds from a git URL; pin a commit and checksum the "
        f"tarball instead")
    assert not re.search(r"^pkgname=.*-git", text, re.M), (
        f"{recipe} is a -git package")


def test_the_astal_pin_is_a_full_commit_hash():
    """A short hash is ambiguous over a repository's lifetime, and a
    branch name is not a pin at all."""
    text = _pkgbuild("astal")
    match = re.search(r"^_commit=([0-9a-f]+)$", text, re.M)
    assert match, "packaging/astal/PKGBUILD does not pin a commit"
    assert len(match.group(1)) == 40, (
        f"the astal pin is {len(match.group(1))} characters, not a full hash")
    assert f"archive/${{_commit}}.tar.gz" in text or "archive/$_commit.tar.gz" in text, (
        "the source URL does not use the pinned commit")


def test_the_go_build_id_is_blanked_so_the_binary_is_reproducible():
    """Measured, twice, before and after.

    Two builds of an unmodified ags 3.1.2 differ in exactly 40 bytes of
    an 11 MB binary - .note.go.buildid and the .note.gnu.build-id ld
    computes over content containing it - and in nothing else. With
    -buildid= two consecutive builds produce a byte-identical package;
    the other four ZepOS packages already did.

    The patch has to be applied to meson.build rather than through
    GOFLAGS, because meson passes its own -ldflags to `go build` and an
    explicit flag overrides the same flag in GOFLAGS.
    """
    text = _pkgbuild("aylurs-gtk-shell")
    assert "-buildid=" in text, "the Go build id is not blanked"
    assert 'grep -q "buildid=" "$srcdir/ags-$pkgver/meson.build"' in text, (
        "the patch is not checked; a silently failing sed would leave "
        "the build unreproducible with nothing to say so")


def test_ags_does_not_run_a_package_manager_during_the_build():
    """Upstream's own recipe calls `npm install` in build(), which makes
    the result a function of what a registry serves and how npm resolves
    `gnim: ^1.9.1` on the day. The exact tarball is pinned by upstream's
    package-lock.json, so it is a source here with a checksum, and npm is
    needed neither to build nor to run."""
    text = _code(_pkgbuild("aylurs-gtk-shell"))
    assert "npm install" not in text, "the AGS build calls npm install"
    assert "registry.npmjs.org/gnim" in text, (
        "gnim is not a pinned source; something has to provide it")
    assert "npm" not in re.findall(r"depends=\((.*?)\)", text, re.S)[0], (
        "npm is a runtime dependency again")


# --------------------------------------------------------------------
# The build driver
# --------------------------------------------------------------------

def test_every_recipe_is_in_the_build_order():
    """A recipe that is not in PACKAGES is a recipe nothing ever builds,
    and nothing would say so: packaging/build.sh would simply not
    mention it."""
    order = _build_order()
    for recipe in _recipes():
        assert recipe.parent.name in order, (
            f"packaging/{recipe.parent.name}/PKGBUILD is not in "
            f"packaging/build.sh's PACKAGES array")


def test_the_build_order_is_dependency_order():
    """aylurs-gtk-shell declares libastal-io and libastal-4 among its
    depends, and makepkg --syncdeps cannot resolve them from any
    repository until the astal recipe has produced them. Measured, with
    the two the wrong way round: "error: target not found: libastal-io"."""
    order = _build_order()
    assert order.index("astal") < order.index("aylurs-gtk-shell"), (
        "astal is built after the package that depends on it")


def test_the_snapshot_is_read_from_the_iso_profile_and_not_repeated():
    """One pin, one file. A package built against a different Arch
    snapshot than the image it is installed into links against libraries
    that are not there - and a second copy of the date is how the two
    drift apart without anybody editing either on purpose."""
    build = _read(PACKAGING / "build.sh")
    assert "iso/profile/pacman.conf" in build, (
        "packaging/build.sh does not read the snapshot from the ISO profile")
    assert not re.search(r"archive\.archlinux\.org/repos/\d{4}/\d{2}/\d{2}", build), (
        "packaging/build.sh carries its own copy of the snapshot date")
    assert not re.search(r"\d{4}/\d{2}/\d{2}", _read(PACKAGING / "Dockerfile")), (
        "packaging/Dockerfile carries its own copy of the snapshot date")


@pytest.mark.parametrize("script", ["build.sh", "verify-install.sh"])
def test_every_container_runs_with_network_host(script):
    """Spec §10.1, measured on this machine: the IPsec tunnel routes all
    three RFC1918 ranges, the Docker bridge sits inside 10.0.0.0/8, and a
    bridged container's packets disappear into the tunnel. `pacman -Sy`
    does not fail slowly there, it fails completely, and there is no
    private range left to move the bridge into."""
    text = _code(_read(PACKAGING / script))
    invocations = re.findall(r"docker (?:run|build)((?:.|\n)*?)(?:\n\n|\Z)", text)
    assert invocations, f"packaging/{script} runs no container"
    for invocation in invocations:
        assert "--network host" in invocation, (
            f"a container in packaging/{script} runs without --network host")


def test_signing_is_refused_rather_than_skipped():
    """Spec §8.6: signatures from the first ISO, because a repository
    that starts unsigned makes every already-installed system import a
    key by hand on the day it stops being unsigned. So a build without a
    key has to stop and say so - not quietly produce an unsigned
    repository that looks exactly like a signed one from the outside."""
    build = _read(PACKAGING / "build.sh")
    assert "--no-sign" in build, "there is no way to build without a key at all"
    assert re.search(r'\$sign; then\n\s*\[\[ -n "\$key" \]\] \|\| die', build), (
        "a signing build with no key does not stop")
    assert "repo-add" in build and "--sign" in build, (
        "the repository database is never signed")


# --------------------------------------------------------------------
# No private key may ever be committed
# --------------------------------------------------------------------

def test_the_key_directory_is_ignored_in_full():
    """packaging/make-test-key.sh writes a GNUPGHOME under packaging/.
    A private key in a clone is a private key in every clone, and a test
    key is still a private key."""
    ignored = _read(ROOT / ".gitignore")
    assert "packaging/keys/" in ignored, "packaging/keys/ is not gitignored"


def test_no_private_key_material_is_in_the_working_tree_outside_the_ignored_directory():
    """The gitignore is a rule; this is the measurement.

    Walks the tree - .git, .venv and the ignored key directory excluded -
    and looks for the header of every private key format anything here
    could plausibly produce.
    """
    headers = (
        "BEGIN PGP PRIVATE KEY BLOCK",
        "BEGIN OPENSSH PRIVATE KEY",
        "BEGIN RSA PRIVATE KEY",
        "BEGIN EC PRIVATE KEY",
        "BEGIN PRIVATE KEY",
    )
    skip = {".git", ".venv", ".pytest_cache", "__pycache__", "keys", "out", "work"}

    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if skip & set(path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for header in headers:
            # The literal below is split so that this file does not
            # match its own search.
            if header in text and path != Path(__file__):
                offenders.append(f"{path.relative_to(ROOT)}: {header}")
    assert offenders == [], "private key material in the tree: " + "; ".join(offenders)


def test_the_signing_key_never_enters_the_build_container():
    """A build container runs build() functions out of upstream
    tarballs. A key mounted into it is a key every future upstream
    release can read, so signing happens on the host after the container
    has exited."""
    build = _read(PACKAGING / "build.sh")
    container = re.search(r"step \"makepkg\"(.*?)\n# ---", build, re.S)
    assert container, "the makepkg container step is no longer recognisable"
    for leak in ("GNUPGHOME", "keys/", "--key"):
        assert leak not in container.group(1), (
            f"the makepkg container is handed {leak}")


# --------------------------------------------------------------------
# What zepos-config installs, and where the ISO stopped doing it by hand
# --------------------------------------------------------------------

def test_the_three_commands_are_installed_executable_by_the_package():
    """This is where the ISO profile's file_permissions entries went.

    The first boot of the smoke image died because `zepos-generate --all`
    returned 126 - found, but not executable - and no session started.
    The profile answered that with four file_permissions entries; the
    package answers it with its own modes, which is the answer that also
    holds on an installed machine.
    """
    text = _pkgbuild("zepos-config")
    install = re.search(r"install -Dm755 -t \"\$pkgdir/usr/bin\"(.*?)\n\n", text, re.S)
    assert install, "zepos-config does not install anything into /usr/bin with -m755"
    for command in ("zepos-generate", "zepos-settings", "zepos-doctor",
                    "zepos-update"):
        assert f"bin/{command}" in install.group(1), (
            f"{command} is not installed executable")


def test_the_self_update_ships_its_timer_its_service_and_its_hook():
    """UP-1. Drei Dateien, und jede einzelne ist notwendig.

    Ohne den Zeitgeber loest nichts aus. Ohne den Dienst gibt es nichts
    auszuloesen. Ohne den ALPM-Haken bekommt eine Maschine, die den
    Aktualisierer erst als Paketaktualisierung erhaelt, alles ausser dem
    Symlink, der ihn einschaltet - und ein Paket kann unter Arch keinen
    Dienst aktivieren (installer/core/translate.py traegt die Messung).

    Gegen das Rezept OHNE Kommentare, weil dieses Rezept genau erklaert,
    wozu die drei da sind: eine Suche im Wortlaut faende die Erklaerung.
    """
    recipe = _code(_pkgbuild("zepos-config"))
    for source, destination in (
            ("system/zepos-update.service",
             "usr/lib/systemd/system/zepos-update.service"),
            ("system/zepos-update.timer",
             "usr/lib/systemd/system/zepos-update.timer"),
            ("system/zepos-update.hook",
             "usr/share/libalpm/hooks/90-zepos-update.hook")):
        assert source in recipe, f"{source} is not installed by the recipe"
        assert destination in recipe, f"nothing is installed to {destination}"
        assert (ROOT / "src" / source).is_file(), \
            f"the recipe installs src/{source}, which does not exist"


def test_the_hook_fires_on_the_file_the_recipe_installs():
    """Ein Haken auf einen Pfad, den kein Paket ablegt, laeuft nie - und
    zwar ohne Fehlermeldung, denn ein Ausloeser, der nicht zutrifft, ist
    fuer pacman der Normalfall."""
    hook = _read(ROOT / "src" / "system" / "zepos-update.hook")
    targets = re.findall(r"^Target\s*=\s*(\S+)", hook, re.M)
    execs = re.findall(r"^Exec\s*=\s*(.+)$", hook, re.M)

    assert targets == ["usr/lib/systemd/system/zepos-update.timer"]
    assert execs == ["/usr/bin/zepos-update --apply"]
    # Der Pfad im Haken traegt keinen fuehrenden Schraegstrich - pacman
    # vergleicht ihn gegen die Dateiliste des Pakets, und die ist relativ.
    assert not targets[0].startswith("/")
    for path in targets + [execs[0].split()[0].lstrip("/")]:
        assert path in _code(_pkgbuild("zepos-config")) or \
            path.endswith("zepos-update"), (
                f"the hook names {path}, which the recipe does not install")


def test_the_generator_may_execute_itself():
    """generate_config.sh runs its own path, and the start-hyprland it
    writes runs generate_config.sh. Both are direct execution rather than
    `bash <file>`, so the mode is load-bearing - it is simply set by the
    package now instead of by the ISO profile."""
    assert 'chmod 0755 "$pkgdir/usr/share/zepos/generate_config.sh"' in _pkgbuild("zepos-config")
    assert '"$SELF" --post' in _read(ROOT / "src" / "generate_config.sh"), \
        "the generator no longer executes itself; this test now guards nothing"


def test_nothing_a_package_owns_is_named_in_the_iso_profile():
    """file_permissions is applied BEFORE pacstrap, and mkarchiso does
    not skip an entry whose file is not there yet - it stops the build
    with "Cannot change permissions ... The file or directory does not
    exist". So a package-owned path left in that array is not redundant,
    it is fatal."""
    declared = _file_permissions()
    for path in declared:
        assert not path.startswith("/usr/share/zepos"), (
            f"{path} is owned by zepos-config and named in file_permissions")
        assert not re.fullmatch(r"/usr/bin/zepos-\w+", path), (
            f"{path} is owned by zepos-config and named in file_permissions")


def test_the_wallpaper_is_packaged_where_the_generator_will_look_for_it():
    """Two halves that cannot check each other, so this checks them.

    The generator substitutes {{ZEPOS_SYSTEM_ROOT}}/branding/... into
    wallpaper-manager; the package puts the file under /usr/share/zepos.
    A mismatch is an error nowhere: `restore` finds no file, returns, and
    the desktop is the compositor's black - which is the state this pair
    was added to end, and which nothing anywhere reports.
    """
    recipe = _pkgbuild("zepos-config")
    assert re.search(r"cp -a --no-preserve=ownership \\\n\s+branding ", recipe), (
        "zepos-config no longer packages src/branding, so the shipped "
        "wallpaper reaches no installed machine")

    manager = _read(ROOT / "src/templates/wallpaper-manager-config.template")
    assert 'DEFAULT_WALLPAPER="{{ZEPOS_SYSTEM_ROOT}}/branding/zepos-wallpaper.png"' \
        in manager, "the generated wallpaper-manager names a different path"
    assert (ROOT / "src/branding/zepos-wallpaper.png").is_file()

    # And the branch that reads it, because a path nothing uses is the
    # same black desktop.
    assert 'apply_default_wallpaper "$DEFAULT_WALLPAPER"' in manager


def test_the_brand_fonts_are_a_dependency_and_not_a_suggestion():
    """fontconfig answers a family it does not have by substituting one
    it does. A missing brand font is therefore not an error and not a
    blank screen: it is the whole product rendered in somebody else's
    typeface, with nothing anywhere saying so."""
    desktop = _pkgbuild("zepos-desktop")
    for font in ("ttf-fira-code", "ttf-roboto"):
        assert f"'{font}'" in desktop, f"{font} is not a dependency of the desktop"
        assert f"'{font}'" in _pkgbuild("zepos-installer"), \
            f"{font} is not a dependency of the graphical installer"

    # The icon font stays, and it stays behind the brand one in the
    # generated font lists - see tests/src/test_brand.py for that half.
    assert "'ttf-jetbrains-mono-nerd'" in desktop, (
        "the Nerd Font is gone; Fira Code carries none of the icon SSOT's "
        "glyphs and the bar would be a row of boxes")


def test_the_default_settings_are_written_by_the_code_that_defines_them():
    """A checked-in copy of the defaults would be a second definition of
    what a fresh ZepOS believes, and the two would part company at the
    first new setting. settings.defaults() writes /etc/skel itself."""
    text = _pkgbuild("zepos-config")
    assert "settings.save(settings.defaults())" in text
    assert "/etc/skel/.config/zepos" in text, "spec §4.3's /etc/skel default is missing"


def test_the_desktop_brings_everything_the_login_starts():
    """Vier Pakete, und ohne eines davon kommt kein Anmeldebildschirm.

    Sie stehen unter derselben Regel wie der Rest der Liste - die
    erzeugte Konfiguration startet sie selbst: /etc/greetd/zepos.toml
    nennt zepos-greeter, und zepos-greeter nennt cage, regreet und
    tuigreet. cage ist namentlich dabei und nicht dem virtuellen
    `wayland-compositor` ueberlassen, auf das regreet haengt: sonst
    entschiede pacman, welcher Compositor den Aufruf beantwortet, den
    dieses Projekt ausgeschrieben hat.

    Gemessen an dem, was ohne sie passiert: iso/test-boot.py --scenario
    release-installed erreichte "Reached target Graphical Interface" und
    dann nichts.
    """
    # _code() und nicht der Rohtext: dieses Rezept ERKLAERT vier
    # Abhaengigkeiten pro Zeile Code, und eine auskommentierte steht
    # danach immer noch im Text. Eine Mutationsprobe hat genau das
    # gezeigt - '#'cage'' liess die Pruefung gruen.
    depends = re.search(r"^depends=\((.*?)^\)", _code(_pkgbuild("zepos-desktop")),
                        re.S | re.M)
    assert depends, "zepos-desktop hat keine depends-Liste"
    for package in ("greetd", "greetd-regreet", "greetd-tuigreet", "cage"):
        assert re.search(rf"^\s*'{re.escape(package)}'", depends.group(1), re.M), (
            f"{package} ist keine Abhaengigkeit des Desktops")

    greeter = _read(ROOT / "src" / "bin" / "zepos-greeter")
    for command in ("cage", "regreet", "tuigreet"):
        assert re.search(rf"^\s*(exec\s+)?{command}\b", greeter, re.M), (
            f"zepos-greeter ruft {command} nicht mehr auf; die "
            "Abhaengigkeit daneben bewacht dann nichts mehr")


def test_the_boot_menu_travels_from_the_iso_profile_into_the_package():
    """Ein Menue, eine Kopie im Baum.

    Das Medium zeigt es beim Booten, und die Maschine, die davon
    installiert wurde, soll es danach zeigen. Ein zweiter Satz Dateien
    unter src/ waeren zwei Menues, sobald jemand eines davon anfasst -
    und tests/iso/test_boot_theme.py misst die Farben an der Datei im
    ISO-Profil, also an der einen, die es geben darf. Dieselbe Regel, aus
    der packaging/build.sh den ALA-Schnappschuss aus iso/profile/
    pacman.conf liest statt ihn zu wiederholen.
    """
    build = _read(PACKAGING / "build.sh")
    # Auf die rsync-Zeile und nicht auf den Pfad: eine Mutationsprobe hat
    # gezeigt, dass der Pfad in der Zuweisung stehenbleibt, waehrend
    # nichts mehr kopiert wird - und dann liegt das Menue in keinem
    # Paket, obwohl der Name noch dasteht.
    assert 'theme="$REPO/iso/profile-release/grub/themes/zepos"' in build, (
        "packaging/build.sh liest das Startmenue nicht aus dem ISO-Profil")
    assert re.search(r'rsync -a "\$theme"/ "\$stage/boot/grub-theme"/', build), (
        "packaging/build.sh legt das Startmenue nicht ins zepos-config-Tarball")
    assert not (ROOT / "src" / "boot" / "grub-theme").exists(), (
        "eine zweite Kopie des Startmenues unter src/")

    recipe = _pkgbuild("zepos-config")
    assert "/usr/share/grub/themes/zepos" in recipe, (
        "zepos-config installiert das Startmenue nicht")


def test_the_theme_fonts_land_where_grub_mkconfig_looks_for_them():
    """Auf dem Medium laedt grub.cfg die Schriften von Hand
    (`loadfont /boot/grub/fonts/roboto-24.pf2`). Auf einer Installation
    schreibt grub-mkconfig die Ladezeilen selbst, und /etc/grub.d/
    00_header sucht dafuer ausschliesslich in "$themedir"/*.pf2 und
    "$themedir"/f/*.pf2. Eine Schrift daneben wuerde nie geladen,
    theme.txt bekaeme fuer "Roboto Regular 24" keine Zuordnung, und GRUB
    zeichnet ein Thema ohne Schrift als Textmenue - ohne Fehler.
    """
    build = _read(PACKAGING / "build.sh")
    assert re.search(r'rsync -a "\$fonts"/ "\$stage/boot/grub-theme/f"/', build), (
        "die PF2-Schriften wandern nicht in das Themenverzeichnis")

    recipe = _pkgbuild("zepos-config")
    assert '"$pkgdir/usr/share/grub/themes/zepos/f" \\\n        boot/grub-theme/f/*.pf2' \
        in recipe, "das Rezept installiert die Schriften nicht unter f/"

    fonts = sorted((ROOT / "iso/profile-release/grub/fonts").glob("*.pf2"))
    assert fonts, "das ISO-Profil traegt keine PF2-Schriften mehr"


def test_the_theme_is_switched_on_and_not_only_shipped():
    """Der Teil, den man vergisst.

    /etc/grub.d/00_header umschliesst den ganzen Themenblock mit
    `if [ "x$gfxterm" = x1 ]`, und gfxterm wird nur gesetzt, wenn
    GRUB_TERMINAL_INPUT oder GRUB_TERMINAL_OUTPUT das Wort "gfxterm"
    enthaelt. Arch liefert GRUB_TERMINAL_OUTPUT auskommentiert aus.
    GRUB_THEME allein erzeugt also keine einzige Zeile in grub.cfg, und
    das Menue kommt als weisse Schrift auf Schwarz - ohne Fehler.
    """
    dropin = _read(ROOT / "src" / "boot" / "grub-zepos.cfg")
    assert re.search(r"^GRUB_TERMINAL_OUTPUT=gfxterm\s*$", dropin, re.M), (
        "ohne gfxterm ueberspringt 00_header den Themenblock vollstaendig")
    theme = re.search(r"^GRUB_THEME=(\S+)\s*$", dropin, re.M)
    assert theme, "das Drop-in nennt kein Thema"

    # Und der Name im Menue. Gemessen an der ersten Installation, die
    # durchlief: das Menue kam in den Farben von ZepOS hoch, mit der
    # Wortmarke darueber - und der ausgewaehlte Eintrag hiess "Arch
    # Linux". /etc/grub.d/10_linux baut ihn als "${GRUB_DISTRIBUTOR}
    # Linux", und Archs /etc/default/grub setzt GRUB_DISTRIBUTOR="Arch".
    assert re.search(r'^GRUB_DISTRIBUTOR="ZepOS"\s*$', dropin, re.M), (
        "ohne GRUB_DISTRIBUTOR heisst der Eintrag im ZepOS-Menue "
        "'Arch Linux'")

    recipe = _pkgbuild("zepos-config")
    assert '"$pkgdir/etc/default/grub.d/10-zepos.cfg"' in recipe, (
        "das Drop-in wird nicht installiert, also liest grub-mkconfig es nie")

    # Und der Pfad im Drop-in ist einer, den grub-mkconfig ANNIMMT.
    #
    # HIER STAND BIS ZUM 17.08.2026 /usr/share/grub/themes/zepos/
    # theme.txt, und diese Zeile hat den Fehler festgeschrieben, den der
    # Nutzer viermal gemeldet hat. Der Pfad war der, den das Rezept
    # belegt - das war die Absicht - aber er liegt auf der
    # verschluesselten Wurzel, und is_path_readable_by_grub
    # (/usr/share/grub/grub-mkconfig_lib, Zeilen 77-85) verwirft jeden
    # Pfad mit `cryptodisk` in der Abstraktionsliste, solange
    # GRUB_ENABLE_CRYPTODISK nicht `y` ist. Gemessen am Abbild der
    # Installation vom 17.08.2026:
    #
    #     $ grub-probe -t abstraction .../usr/share/grub/themes/zepos/theme.txt
    #     cryptodisk
    #     luks2
    #     ...
    #     $ grub-probe -t abstraction .../boot/grub/grub.cfg
    #     (leer)
    #
    # /etc/grub.d/00_header ueberspringt daraufhin den ganzen
    # Themenblock, ohne Fehler und ohne eine Zeile in grub.cfg.
    #
    # Die Bedingung ist deshalb nicht mehr "der Pfad ist der, den das
    # Rezept belegt", sondern die staerkere: er liegt unter /boot - dem
    # einen Dateisystem, das GRUB lesen KANN, sonst laege dort keine
    # grub.cfg - und es gibt einen Weg, der ihn dorthin bringt.
    assert theme.group(1).startswith("/boot/"), (
        "GRUB_THEME zeigt nicht nach /boot; alles andere kann auf einer "
        "verschluesselten Wurzel liegen, und von dort liest grub-mkconfig "
        "nichts - siehe src/boot/grub-zepos.cfg")
    assert theme.group(1) == "/boot/grub/themes/zepos/theme.txt"

    # Der Bestand, der dem Paket gehoert, bleibt unter /usr/share: eine
    # FAT-Partition kennt weder Rechte noch Besitzer, und ein nicht
    # eingehaengtes /boot bekaeme die Dateien auf die Wurzel.
    assert "/usr/share/grub/themes/zepos" in recipe

    # Und der Spiegel, ohne den der Pfad oben ins Leere zeigt. Beides
    # muss da sein: das Skript kopiert, der Haken loest aus.
    assert '"$pkgdir/usr/bin/zepos-grub-theme"' in recipe, (
        "das Rezept installiert den Spiegel nicht, also kommt das Thema "
        "nie unter /boot an")
    assert '"$pkgdir/usr/share/libalpm/hooks/90-zepos-grub-theme.hook"' \
        in recipe, ("ohne den ALPM-Haken laeuft der Spiegel nie - weder "
                    "bei der Installation noch bei einer Aktualisierung")

    hook = _read(ROOT / "src" / "boot" / "zepos-grub-theme.hook")
    assert re.search(r"^Exec = /usr/bin/zepos-grub-theme\s*$", hook, re.M), (
        "der Haken ruft den Spiegel nicht auf")
    assert re.search(r"^Target = usr/share/grub/themes/zepos/\*\s*$",
                     hook, re.M), (
        "der Haken haengt nicht am Themenverzeichnis, feuert also nicht, "
        "wenn sich das Thema aendert")


def test_only_one_session_entry_reaches_the_greeter():
    """Der Anmeldebildschirm darf keine Wahl anbieten, die ins Leere
    fuehrt.

    Hyprlands eigene hyprland.desktop und hyprland-uwsm.desktop starten
    den Compositor direkt und gehen damit an zepos-session vorbei - auf
    einer frisch installierten Maschine bedeutet das keine Konfiguration
    und keinen Desktop. Gemessen an ReGreet 0.5.0: die Sitzungen liegen
    in einer HashMap, und vorausgewaehlt wird der erste Schluessel beim
    Iterieren - Rust wuerfelt die Reihenfolge pro Prozess neu. Die
    Vorauswahl waere also bei jedem Start eine andere.

    Also entfernt zepos-hyprland die beiden, und zepos-config legt genau
    einen Eintrag ab.
    """
    compositor = _pkgbuild("zepos-hyprland")
    assert re.search(
        r'rm -f "\$pkgdir/usr/share/wayland-sessions/hyprland\.desktop" \\\n'
        r'\s+"\$pkgdir/usr/share/wayland-sessions/hyprland-uwsm\.desktop"',
        compositor), (
        "zepos-hyprland liefert Hyprlands eigene Sitzungseintraege wieder aus")

    config = _pkgbuild("zepos-config")
    entries = re.findall(r'"\$pkgdir/usr/share/wayland-sessions/(\S+?)"', config)
    assert entries == ["zepos.desktop"], (
        f"zepos-config legt {entries} statt genau eines ZepOS-Eintrags ab")


def test_no_package_brings_an_autologin():
    """"anmeldung immer". Das Rauchbild meldet sich per agetty selbst an,
    und das ist fuer einen Messlaeufer richtig; ein Paket, das dasselbe
    auf eine Maschine braechte, die jemandem gehoert, waere es nicht.
    iso/test-boot.py sucht in der fertigen ISO nach genau diesem Muster -
    hier steht die Entsprechung fuer das installierte System.
    """
    for recipe in _recipes():
        code = _code(_read(recipe))
        assert "autologin" not in code, f"{recipe.parent.name} bringt ein Autologin"
        assert "initial_session" not in code, (
            f"{recipe.parent.name} bringt greetds Autologin")


# --------------------------------------------------------------------
# The ISO installs the packages instead of copying src/
# --------------------------------------------------------------------

def test_the_iso_no_longer_copies_src_into_the_image():
    """The point of the exercise. A copy carries files and nothing else -
    no dependencies, no /etc/skel, no signature - and it tests a layout
    that never ships."""
    build = _read(ROOT / "iso" / "build.sh")
    assert not re.search(r'rsync[^\n]*"\$REPO/src"', build), (
        "iso/build.sh still copies src/ into the image by hand")
    assert "PKG_REPO" in build, "iso/build.sh does not use the package repository"


def test_the_image_installs_the_two_packages():
    packages = _packages_x86_64()
    for needed in ("zepos-config", "aylurs-gtk-shell"):
        assert needed in packages, f"{needed} is not in packages.x86_64"
    assert len(packages) == len(set(packages)), "duplicate package entries"


def test_the_notification_typelib_is_named_explicitly():
    """AGS lists libastal-notifd as optional. For ZepOS it is not:
    ags-notifications.template imports AstalNotifd, app.ts imports that
    widget at the top level, and a failed import there stops the WHOLE
    bundle - so the absence of one typelib would mean no AGS widgets at
    all rather than no notifications."""
    assert "libastal-notifd" in _packages_x86_64()
    assert 'import AstalNotifd from "gi://AstalNotifd' in \
        _read(ROOT / "src" / "templates" / "ags-notifications.template")


def test_the_stylesheet_compiler_is_in_the_image():
    """`ags run` shells out to dart-sass for the style.scss that
    ags-style.template generates."""
    assert "dart-sass" in _packages_x86_64()
    assert 'import style from "./style.scss"' in \
        _read(ROOT / "src" / "templates" / "ags-config.template")


# --------------------------------------------------------------------
# The repository, as the installer already described it
# --------------------------------------------------------------------

def test_the_repository_is_called_what_the_installer_writes_into_pacman_conf():
    """installer/core/source.py names the repository in the target's
    pacman.conf. If the database is called anything else, an installed
    system has a [zepos] section pointing at a repository that is not
    there, and the failure appears at the first `pacman -Syu`."""
    source = _read(ROOT / "installer" / "core" / "source.py")
    # The literal moved into a module constant when
    # installer/core/pacmanconf.py needed the same string in order to
    # FIND the section archinstall wrote and replace it (spec §8.5b).
    # Still one place; one level further out.
    name = re.search(r'^REPO_NAME = "([^"]+)"', source, re.M)
    assert name, "installer/core/source.py no longer names the repository"
    assert '"name": REPO_NAME' in source, (
        "mirror_config() spells the repository name a second time, so the "
        "constant above is no longer the one place it is decided")
    assert f'readonly REPO_NAME="{name.group(1)}"' in _read(PACKAGING / "build.sh"), (
        f"packaging/build.sh builds a database the installer would not find")
    assert f"[{name.group(1)}]" in _read(ISO_PROFILE / "pacman.conf"), (
        "the ISO profile has no section for the ZepOS repository")


# --------------------------------------------------------------------
# The compositor and the five plugins
# --------------------------------------------------------------------
# Written out rather than imported from src/plugins.py, for the reason
# tests/src/test_plugins.py gives for the same list: a roster that checks
# itself against itself agrees with every typo.
SPEC_PLUGINS = {
    "hyprbars": "hyprland-plugins",
    "borders-plus-plus": "hyprland-plugins",
    "hyprlaunch": "zepos-hyprlaunch",
    "hyprclipx": "zepos-hyprclipx",
    "hyprzones": "zepos-hyprzones",
}

# Spec §4.2's plugin object path, and §7.3's range. Both are quoted here
# because both are the kind of constant that is easy to retype slightly
# differently in the sixth file that needs it.
PLUGIN_OBJECT_DIR = "usr/lib/hyprland/plugins"
ABI_RANGE = ("zepos-hyprland>=0.56.1", "zepos-hyprland<0.57.0")


def test_the_compositor_is_pinned_to_the_version_the_plugins_were_ported_to():
    """Spec §4.3 and §7.1: 0.56.1, and not the 0.55.4 that stood there
    before. The three own plugins do not compile against 0.55.4 any more
    - Monitor.hpp moved, getMonitorFromCursor went away, m_realPosition
    became protected - so a compositor package at any other version would
    be a compositor nothing in packaging/ can build a plugin for."""
    text = _pkgbuild("zepos-hyprland")
    assert re.search(r"^pkgver=0\.56\.1$", text, re.M), (
        "zepos-hyprland is not pinned to the version §4.3 commits to")


def test_the_compositor_takes_the_place_of_the_one_in_extra():
    """Spec §4.2: provides/conflicts against `hyprland`.

    provides, because xdg-desktop-portal-hyprland and everything else in
    extra that wants a compositor depends on that name. conflicts,
    because two Hyprlands would disagree about which headers are in
    /usr/include/hyprland - and a plugin built against the wrong ones
    loads without complaint into a compositor whose structs have moved.
    """
    text = _code(_pkgbuild("zepos-hyprland"))
    assert re.search(r'provides=\([^)]*"hyprland=\$pkgver"', text, re.S), (
        "zepos-hyprland does not provide `hyprland`")
    assert re.search(r"^conflicts=\('hyprland'\)$", text, re.M), (
        "zepos-hyprland does not conflict with the hyprland in extra")


def test_the_compositor_does_not_ship_hyprpm():
    """Spec §7.2 rejected per-user plugin compilation, and shipping the
    tool anyway would leave a machine with two plugin directories of
    which src/plugins.py can name only one."""
    assert "-DNO_HYPRPM=true" in _code(_pkgbuild("zepos-hyprland")), (
        "hyprpm is compiled into zepos-hyprland; §7.2 rejected it")


def test_the_compositor_publishes_the_abi_its_plugins_are_compiled_against():
    """Hyprland's own load-time check is the literal string "0.1" -
    src/plugins/PluginAPI.hpp defines HYPRLAND_API_VERSION that way and
    PluginSystem.cpp compares against it, so every plugin ever built for
    a 0.x Hyprland passes. What actually has to match is the header set,
    and upstream's abiHash is the string that describes it: the commit
    plus five library versions at major.minor.

    Nothing consumes that string except hyprpm, which is not here. So
    zepos-hyprland publishes it as a provides and writes it next to the
    plugin directory, and the plugin packages depend on it - which is the
    only mechanism on the machine that can tell 0.56.1 built against
    aquamarine 0.14 from 0.56.1 built against 0.15.
    """
    text = _code(_pkgbuild("zepos-hyprland"))
    assert '"hyprland-plugin-abi=$_abi"' in text, (
        "zepos-hyprland does not publish an ABI token")
    assert "_abi_file=" in text and "plugin-abi" in text, (
        "the ABI token is not written anywhere a plugin build could read it")
    assert "_abi_from_header" in text, (
        "nothing checks the published token against the version.h that "
        "was shipped; a compositor whose published ABI is not its own "
        "would take every plugin and be built for none of them")


@pytest.mark.parametrize("plugin, recipe", sorted(SPEC_PLUGINS.items()))
def test_every_plugin_installs_where_the_generator_looks(plugin, recipe):
    """Spec §4.2, and the reason it is one sentence long: src/plugins.py
    keeps a plugin's configuration block only when
    /usr/lib/hyprland/plugins/<name>.so exists, so a package that
    installs the same object one directory away produces a desktop with
    no plugins, no error and nothing in any log.

    The recipes check it themselves at package() time as well. This
    checks that they check.
    """
    text = _code(_pkgbuild(recipe))
    assert f'_plugin_dir="{PLUGIN_OBJECT_DIR}"' in text, (
        f"packaging/{recipe} does not install into {PLUGIN_OBJECT_DIR}")
    assert plugin in text, (
        f"packaging/{recipe} never names {plugin} outside its comments")
    assert re.search(r'test -f "\$pkgdir/\$_plugin_dir/', text), (
        f"packaging/{recipe} does not check that the object it packaged "
        f"is at the path src/plugins.py will look at")


@pytest.mark.parametrize("recipe", sorted(set(SPEC_PLUGINS.values())))
def test_every_plugin_declares_the_range_and_the_abi(recipe):
    """Spec §7.3 wants the range, and the range is not enough.

    `zepos-hyprland>=0.56.1, <0.57.0` lets patch updates through and
    stops minor jumps, which is where the ABI breaks on paper. On the
    machine it also has to survive a REBUILD: 0.56.1 compiled against a
    newer aquamarine is still 0.56.1, satisfies the range, and has
    different struct layouts. So both, on every plugin package.
    """
    text = _code(_pkgbuild(recipe))
    for constraint in ABI_RANGE:
        assert f"'{constraint}'" in text, (
            f"packaging/{recipe} does not declare {constraint} (spec §7.3)")
    assert '"hyprland-plugin-abi=$_abi"' in text, (
        f"packaging/{recipe} does not pin the compositor's ABI token")
    assert '_abi="$(cat "$_abi_file"' in text, (
        f"packaging/{recipe} does not read the token from the file "
        f"zepos-hyprland installs")


def test_the_compositor_is_built_before_every_plugin():
    """Not a version constraint but a compile-time one: the plugins are
    C++ against Hyprland's own headers, and `pkg_check_modules(HYPRLAND
    REQUIRED hyprland)` reads the hyprland.pc that zepos-hyprland
    installs. Without it the plugin builds do not fail at link time, they
    fail at the configure step."""
    order = _build_order()
    assert "zepos-hyprland" in order, "the compositor is never built"
    for recipe in sorted(set(SPEC_PLUGINS.values())):
        assert order.index("zepos-hyprland") < order.index(recipe), (
            f"{recipe} is built before the compositor it compiles against")


def test_the_hyprwm_tree_is_one_recipe_and_two_packages():
    """Spec §4.3 corrected itself here. `hyprland-plugins` had been
    listed as a third missing component, "the collection repo of the
    first two" - a hyprpm sentence, because hyprpm adds a repo and
    enables plugins out of it. Without hyprpm it is one upstream tree
    that two packages are built from and there is no third thing to
    install."""
    text = _pkgbuild("hyprland-plugins")
    assert re.search(r"^pkgbase=hyprland-plugins$", text, re.M)
    assert re.search(r"^pkgname=\('zepos-hyprbars' 'zepos-borders-plus-plus'\)$",
                     text, re.M), (
        "the hyprwm tree does not produce exactly the two packages §4.2 names")
    assert text.count("source=(") == 1, (
        "the two packages are not built from one download")


def test_the_image_installs_the_compositor_and_the_five_plugins():
    """The measurement the whole exercise is for. src/plugins.py decides
    at generation time, from the objects on the machine, so an image
    without the plugin packages produces a plugins.conf of nothing but
    comments - a desktop that comes up, looks finished, and has no title
    bars, no zones and a launcher that fell back to zepos-menu."""
    packages = _packages_x86_64()
    assert "zepos-hyprland" in packages, "the image installs no compositor"
    assert "hyprland" not in packages, (
        "the image still installs the hyprland from extra; it conflicts "
        "with zepos-hyprland and pacstrap would refuse the transaction")
    for plugin in SPEC_PLUGINS:
        assert f"zepos-{plugin}" in packages, (
            f"zepos-{plugin} is not in packages.x86_64; src/plugins.py "
            f"names that package in the comment it writes when the object "
            f"is missing")


def test_the_build_image_is_rebuilt_when_the_dockerfile_changes():
    """Measured, and it cost a build: a dependency added to
    packaging/Dockerfile was ignored because build.sh reused the cached
    image, and the recipe failed on a tool the Dockerfile plainly
    installs. An image that does not match the file describing it is not
    a cache hit."""
    build = _read(PACKAGING / "build.sh")
    assert "zepos.dockerfile" in build, (
        "packaging/build.sh does not stamp the image with what built it")
    assert re.search(r'\$rebuild_image \|\| \[\[ "\$image_id" != "\$dockerfile_id" \]\]',
                     build), (
        "packaging/build.sh does not compare the image against the Dockerfile")


def test_the_published_layout_matches_the_online_url():
    """ONLINE_REPO_URL ends in $arch, so what is published is the
    directory ABOVE the architecture directory. Building into
    packaging/out/x86_64/ is what makes packaging/out/ that directory."""
    source = _read(ROOT / "installer" / "core" / "source.py")
    assert re.search(r'ONLINE_REPO_URL = "[^"]+/\$arch"', source), (
        "the online repository URL no longer ends in $arch")
    assert 'readonly REPO_DIR="$OUT/x86_64"' in _read(PACKAGING / "build.sh"), (
        "the build does not produce an architecture directory")


# --------------------------------------------------------------------
# The three installer packages
# --------------------------------------------------------------------
INSTALLER_PACKAGES = ("zepos-installer", "zepos-installer-gui",
                      "zepos-installer-tui")

# The toolkit spec §4.2 gives the GUI package and §8.5 keeps out of the
# text one. Written out here rather than read from the recipe, for the
# reason tests/src/test_plugins.py gives for its own roster: a list that
# checks itself against itself agrees with every typo.
GTK_STACK = ("gtk4", "libadwaita", "python-gobject")


def _package_function(recipe: str, package: str) -> str:
    """The body of one package_<name>() function of a split recipe."""
    text = _pkgbuild(recipe)
    body = re.search(rf"^package_{re.escape(package)}\(\) \{{(.*?)^\}}",
                     text, re.S | re.M)
    assert body, f"packaging/{recipe} has no package_{package}()"
    return body.group(1)


def test_the_installer_is_one_source_tree_and_three_packages():
    """Spec §8.1: the surface is replaceable because it only fills the
    data model. One package would throw that away at the last step - the
    GTK4 stack would arrive on every machine that installs the installer,
    including the one whose graphical session did not come up."""
    text = _pkgbuild("zepos-installer")
    assert re.search(r"^pkgbase=zepos-installer$", text, re.M)
    assert re.search(
        r"^pkgname=\('zepos-installer' 'zepos-installer-gui' 'zepos-installer-tui'\)$",
        text, re.M), "the installer tree does not produce the three packages §4.2 names"
    assert text.count("source=(") == 1, (
        "the three packages are not built from one source tree")


def test_the_text_interface_depends_on_nothing_but_the_core():
    """Spec §8.5, and the reason it is not merely tidiness: the text
    interface is what runs when GTK4 cannot. A dependency that pulls the
    toolkit in - directly, or through anything that carries it - is the
    same dependency under a second name, and it would go unnoticed
    because a machine that CAN run GTK4 never exercises the fallback."""
    body = _package_function("zepos-installer", "zepos-installer-tui")
    depends = re.search(r"depends=\((.*?)\)", body, re.S)
    assert depends, "zepos-installer-tui declares no depends at all"
    for toolkit in (*GTK_STACK, "gtk3", "gtk4-layer-shell"):
        assert toolkit not in depends.group(1), (
            f"zepos-installer-tui depends on {toolkit}; §8.5's fallback "
            f"is then a fallback onto the same toolkit")
    assert "zepos-installer=" in depends.group(1), (
        "the text interface is not pinned to the core it imports")


def test_the_graphical_interface_is_the_only_one_that_names_a_toolkit():
    """§4.2 gives zepos-installer-gui gtk4, libadwaita and
    python-gobject, and gives them to nothing else."""
    body = _package_function("zepos-installer", "zepos-installer-gui")
    depends = re.search(r"depends=\((.*?)\)", body, re.S)
    assert depends, "zepos-installer-gui declares no depends at all"
    for toolkit in GTK_STACK:
        assert f"'{toolkit}'" in depends.group(1), (
            f"zepos-installer-gui does not declare {toolkit}")


def test_the_installer_core_declares_the_programs_it_shells_out_to():
    """archinstall does the installation (§8.1). The other three are
    called by installer/core directly rather than through it - lsblk in
    disks.py, `openssl passwd -6` in passwords.py because python removed
    the crypt module in 3.13, and iwctl in wifi.py - and a dependency
    that is only true transitively disappears when somebody else's
    package changes its mind."""
    body = _package_function("zepos-installer", "zepos-installer")
    depends = re.search(r"depends=\((.*?)\)", body, re.S)
    assert depends, "zepos-installer declares no depends at all"
    for needed in ("python", "archinstall", "util-linux", "openssl", "iwd"):
        assert f"'{needed}'" in depends.group(1), (
            f"zepos-installer does not declare {needed}")


def test_the_installer_modules_do_not_go_into_site_packages():
    """`installer` is a top-level name python-installer already owns in
    site-packages. Two packages claiming
    .../site-packages/installer/__init__.py is a pacman file conflict,
    not a shadowing problem - so the tree goes to
    /usr/share/zepos-installer and the entry point resolves it."""
    text = _pkgbuild("zepos-installer")
    assert '_root="usr/share/zepos-installer"' in text, (
        "the installer modules do not go to /usr/share/zepos-installer")
    assert "site-packages" not in _code(text), (
        "the recipe installs into site-packages")
    entry = _read(ROOT / "installer" / "bin" / "zepos-install")
    assert '"/usr/share/zepos-installer"' in entry, (
        "installer/bin/zepos-install does not know where the package put "
        "its modules; the installed command would import nothing")


def test_the_installer_is_in_the_iso_and_not_in_the_desktop():
    """Spec §4.2, the line under the table: "Die drei Installer-Pakete
    liegen nur in der ISO, nicht im installierten System." A machine that
    carries the program which erases disks carries archinstall and iwd
    with it, and offers to reinstall itself from its own menu."""
    meta = _code(_pkgbuild("zepos-desktop"))
    for package in INSTALLER_PACKAGES:
        assert package not in meta, (
            f"zepos-desktop pulls in {package}; §4.2 keeps the installer "
            f"in the ISO")
    assert "archinstall" not in meta, (
        "zepos-desktop pulls in archinstall, which only the installer needs")


# --------------------------------------------------------------------
# The keyring
# --------------------------------------------------------------------

def test_the_keyring_ships_both_files_pacman_key_reads():
    """Read out of /usr/bin/pacman-key rather than guessed. populate_keyring()
    imports <name>.gpg and then LOCALLY SIGNS every fingerprint listed in
    <name>-trusted; without the second file the key is imported and pacman
    still rejects every signature made with it, because an imported key is
    not a trusted key."""
    text = _code(_pkgbuild("zepos-keyring"))
    assert "usr/share/pacman/keyrings/zepos.gpg" in text, (
        "zepos-keyring installs no keyring file")
    assert "usr/share/pacman/keyrings/zepos-trusted" in text, (
        "zepos-keyring installs no ownertrust file; pacman-key --populate "
        "would import the key and never trust it")
    assert re.search(r"printf '%s:4:", text), (
        "the ownertrust file is not written in the format pacman-key reads")


def test_the_keyring_reads_its_fingerprint_out_of_the_key():
    """A fingerprint typed into a recipe next to the key it describes is
    a fingerprint that can disagree with it - and the disagreement shows
    up as every signature being rejected on a machine that has the right
    key."""
    text = _code(_pkgbuild("zepos-keyring"))
    assert "gpg --with-colons --show-keys" in text, (
        "zepos-keyring does not derive the fingerprint from the key file")
    assert not re.search(r"[0-9A-F]{40}", text), (
        "a 40-digit fingerprint is written into the recipe")


def test_the_keyring_refuses_to_ship_no_key():
    """A zepos-keyring with no key installs, runs its scriptlet, populates
    nothing, and leaves a machine failing its next `pacman -Syu` on a
    signature from a key nobody can find."""
    text = _code(_pkgbuild("zepos-keyring"))
    assert re.search(r'\[\[ -s "\$srcdir/zepos-repo\.pub" \]\] \|\|', text), (
        "the recipe would package an empty or missing key")


def test_the_keyring_scriptlet_survives_a_root_with_no_keyring():
    """A scriptlet runs chrooted into the root pacman is installing into,
    and two of the roots that matter here have no keyring at all:
    mkarchiso builds with `pacstrap -G`, and archinstall pacstraps the
    target before `pacman-key --init` has run there. `pacman-key -l`
    fails on such a root, which is the guard archlinux-keyring uses for
    exactly these situations."""
    install = _read(PACKAGING / "zepos-keyring" / "zepos-keyring.install")
    assert "pacman-key -l" in install, (
        "the scriptlet populates without checking there is a keyring to "
        "populate; mkarchiso would stop the ISO build")
    assert "pacman-key --populate zepos" in install
    assert "post_install" in install and "post_upgrade" in install, (
        "the scriptlet does not cover both a fresh install and an upgrade "
        "- the upgrade path is what recovers a root that had no keyring "
        "the first time")
    assert not re.search(r"^\s*/usr/bin/pacman-key", install, re.M), (
        "the scriptlet calls pacman-key by an absolute path; inside a "
        "--root installation that names the host binary")


def test_the_key_is_supplied_to_the_build_and_never_stored():
    """The same arrangement the signing key already has: build.sh takes a
    key id, exports the public half into the recipe directory before the
    container starts, and .gitignore keeps it out of every clone. Today
    that key is the throwaway one make-test-key.sh produces, and a
    keyring package committed around it would be a distribution trusting
    a key whose private half is in somebody's working tree."""
    build = _read(PACKAGING / "build.sh")
    assert 'KEYRING_SOURCE="$PACKAGING/zepos-keyring/zepos-repo.pub"' in build, (
        "build.sh does not export the public key for zepos-keyring")
    assert re.search(r"gpg --batch --yes --export --output \"\$KEYRING_SOURCE\"", build), (
        "the public half is not exported before the build container runs")
    assert "packaging/*/*.pub" in _read(ROOT / ".gitignore"), (
        "the exported key is not gitignored")


def test_the_iso_and_the_keyring_ship_the_same_bytes():
    """iso/build.sh trusts packaging/out/zepos-repo.pub in its build
    container and zepos-keyring installs its own copy on the target. Two
    separate `gpg --export` calls would almost always agree, and "almost
    always" is the wrong property for the pair of files that decide
    whether an installed system trusts the same key the image did."""
    build = _read(PACKAGING / "build.sh")
    assert re.search(
        r'install -Dm644 "\$KEYRING_SOURCE" "\$OUT/\$REPO_NAME-repo\.pub"', build), (
        "the published public key is not the file zepos-keyring was built from")


# --------------------------------------------------------------------
# zepos-logout, und das Toolkit, das die Entscheidung vom 11.08.2026 fordert
# --------------------------------------------------------------------
#
# Hier stand test_wlogout_is_checked_for_the_protocol_the_bind_asks_for.
# Es hielt fest, dass das Rezept nach dem Bau `readelf -d` fragt, weil
# wlogouts meson.build gtk-layer-shell optional machte und ein Bau ohne
# die Bibliothek still auf das xdg-Protokoll zurueckfiel. Diese Frage
# bleibt und ist unten die dritte; dazu kommen die zwei, um die es bei
# dem Wechsel ging.

def test_the_logout_menu_is_measured_against_gtk4_after_the_build():
    """Der Bau darf nicht bloss GTK4 WOLLEN, er muss es geliefert haben.

    logout/meson.build fordert `dependency('gtk4')`, und das ist eine
    Zusicherung im Bauskript. Was das fertige Objekt dem Linker
    tatsaechlich abverlangt hat, steht nur im Objekt. Beide Richtungen
    werden gefragt: dass libgtk-4 da ist UND dass libgtk-3 es nicht ist.
    Die zweite ist nicht ueberfluessig - ein Programm kann beide laden,
    wenn eine Bibliothek dazwischen die alte hereinzieht, und dann ist
    die erste Antwort ja und der Bildschirm trotzdem halb GTK3.
    """
    text = _code(_pkgbuild("zepos-logout"))
    assert re.search(r'grep -q "libgtk-4"', text), (
        "nichts misst, ob das gebaute Objekt gegen GTK4 gelinkt ist")
    assert "readelf -d" in text, (
        "die Messung liest nicht das Objekt, sondern etwas anderes")

    # Und die Seitentuer wird mit ldd gemessen, nicht mit readelf.
    #
    # GEMESSEN, und die erste Fassung hatte es falsch: ein
    # logout/meson.build mit zusaetzlichem `dependency('gtk+-3.0')`
    # erzeugte ein Paket, das eine readelf-Pruefung auf libgtk-3
    # BESTAND - Archs `-Wl,--as-needed` traegt kein DT_NEEDED fuer eine
    # Bibliothek ein, aus der kein Symbol benutzt wird. readelf sieht
    # deshalb genau den Fall nicht, um den es geht: die Bibliothek, die
    # ihrerseits GTK3 mitbringt.
    assert re.search(r'ldd "\$binary"', text), (
        "die Seitentuer wird nicht mit ldd gemessen")
    assert re.search(r'grep -q "libgtk-3" <<<"\$loaded"', text), (
        "nichts misst, ob libgtk-3 beim Start geladen wuerde")


def test_the_logout_menu_is_checked_for_the_layer_shell_it_needs():
    """Die Frage, die zepos-logout von wlogout geerbt hat.

    wlogouts meson.build hatte `required : false` fuer gtk-layer-shell;
    ein Bau ohne die Bibliothek uebersetzte weiter, nahm `--protocol
    layer-shell` an und fiel still auf xdg zurueck - die Maske wurde ein
    gewoehnliches Fenster. logout/meson.build macht die GTK4-Entsprechung
    erforderlich, sodass der Bau ausfaellt; das Rezept misst trotzdem am
    Ergebnis nach.
    """
    text = _code(_pkgbuild("zepos-logout"))
    assert "'gtk4-layer-shell'" in text, (
        "zepos-logout haengt nicht an gtk4-layer-shell")
    assert re.search(r'grep -q "gtk4-layer-shell"', text), (
        "nichts prueft, ob das gebaute Objekt wirklich dagegen gelinkt hat")

    meson = _read(ROOT / "logout" / "meson.build")
    # Zeilengenau und ohne Kommentare, weil der Kopf dieser Datei
    # ERKLAERT, dass wlogout die Abhaengigkeit optional hatte. Ein
    # Teilzeichenketten-Test ueber die ganze Datei waere von dieser
    # Erklaerung wahr geworden.
    lines = [line.strip() for line in meson.splitlines()
             if not line.lstrip().startswith("#")]
    assert "layershell = dependency('gtk4-layer-shell-0')" in lines, (
        "gtk4-layer-shell ist im Bauskript nicht unbedingt erforderlich")


def test_the_bind_the_logout_package_exists_for_names_it():
    """Ein Rezept fuer ein Programm, das keine Taste mehr aufruft, ist
    ein Rezept, das nichts mehr absichert."""
    hypr = _read(ROOT / "src" / "templates" / "hyprland-universal-config.template")
    # Zeilengenau: `zepos-logout` steht in dieser Vorlage auch im
    # Kommentar ueber der Bindung, und der wuerde einen
    # Teilzeichenketten-Test bestehen lassen, nachdem jemand die Bindung
    # geloescht hat.
    binds = [line.strip() for line in hypr.splitlines()
             if line.strip().startswith("bind")]
    assert "bind = $mainMod, M, exec, zepos-logout" in binds, (
        "SUPER+M ruft die Abmeldemaske nicht mehr auf")


def test_the_lock_screen_is_measured_against_gtk4_and_pam_after_the_build():
    """Drei Fragen am fertigen Objekt, und die dritte gibt es nur hier.

    Die ersten beiden erbt dieses Rezept von zepos-logout, samt
    Begruendung: readelf sagt, was DIESES Objekt angefordert hat, ldd
    sagt, was beim Start wirklich geladen wird, und nur ldd sieht ein
    libgtk-3, das eine Bibliothek dazwischen hereinzieht.

    Die dritte ist libpam. Ohne sie waere zepos-lock ein Bildschirm, der
    ein Passwortfeld ZEIGT - und das ist der eine Fehler dieses
    Programms, den man ihm nicht ansieht: er sperrt richtig, er sieht
    richtig aus, und er laesst jeden herein.
    """
    text = _code(_pkgbuild("zepos-lock"))
    assert "readelf -d" in text, (
        "die Messung liest nicht das Objekt, sondern etwas anderes")
    assert re.search(r'grep -q "libgtk-4"', text), (
        "nichts misst, ob das gebaute Objekt gegen GTK4 gelinkt ist")
    assert re.search(r'grep -q "libpam"', text), (
        "nichts misst, ob das Passwort ueberhaupt gegen PAM geprueft werden "
        "kann")
    assert re.search(r'ldd "\$binary"', text), (
        "die Seitentuer wird nicht mit ldd gemessen")
    assert re.search(r'grep -q "libgtk-3" <<<"\$loaded"', text), (
        "nichts misst, ob libgtk-3 beim Start geladen wuerde")


def test_the_lock_screen_is_checked_for_the_protocol_it_needs():
    """gtk4-layer-shell ist hier nicht die Layer-Shell, sondern das
    Protokoll.

    Dieselbe Bibliothek liefert gtk4-session-lock.h, und das ist der
    einzige Weg von GTK4 zu ext-session-lock-v1. Ohne sie gibt es keinen
    Rueckfall, der noch ein Sperrbildschirm waere - nur ein Fenster ganz
    oben, das beim Absturz den Schreibtisch freigibt. Deshalb ist die
    Abhaengigkeit im Bauskript ERFORDERLICH und wird am Ergebnis
    trotzdem nachgemessen.
    """
    text = _code(_pkgbuild("zepos-lock"))
    assert "'gtk4-layer-shell'" in text, (
        "zepos-lock haengt nicht an gtk4-layer-shell")
    assert re.search(r'grep -q "gtk4-layer-shell"', text), (
        "nichts prueft, ob das gebaute Objekt wirklich dagegen gelinkt hat")

    meson = _read(ROOT / "lock" / "meson.build")
    lines = [line.strip() for line in meson.splitlines()
             if not line.lstrip().startswith("#")]
    assert "sessionlock = dependency('gtk4-layer-shell-0')" in lines, (
        "gtk4-layer-shell ist im Bauskript nicht unbedingt erforderlich")
    assert any("has_header('gtk4-session-lock.h'" in line for line in lines), (
        "der Bau prueft nicht, ob die Bibliothek alt genug ist, um "
        "ext-session-lock-v1 NICHT zu koennen - dann faellt er erst am "
        "#include aus, und die Meldung nennt den Grund nicht")


def test_the_lock_screen_ships_its_own_pam_service():
    """Ohne eigene Datei haengt die Pruefung an /etc/pam.d/other.

    Auf Arch ist `other` viermal pam_deny.so, der Rueckfall faellt also
    zufaellig richtig herum aus. Zufaellig ist bei einem
    Sperrbildschirm zu wenig: welches Paket `other` schreibt, ist nicht
    unsere Entscheidung, und ein `auth required pam_permit.so` darin
    machte jeden Bildschirm dieser Distribution auf.
    """
    text = _code(_pkgbuild("zepos-lock"))
    assert "/etc/pam.d/zepos-lock" in text, (
        "das Rezept sieht nicht nach, ob die PAM-Datei im Paket liegt")
    assert "'pam'" in text, "zepos-lock haengt nicht an pam"

    meson = _read(ROOT / "lock" / "meson.build")
    lines = [line.strip() for line in meson.splitlines()
             if not line.lstrip().startswith("#")]
    assert "install_data('zepos-lock.pam'," in lines, (
        "die PAM-Datei wird gar nicht installiert")
    assert "install_dir : '/etc/pam.d'," in lines, (
        "sie landet nicht dort, wo Linux-PAM sucht")


def test_the_lock_screen_package_pushes_hyprlock_out():
    """Zwei Sperrbildschirme nebeneinander waeren einer zu viel.

    conflicts und NICHT replaces: replaces liesse pacman ohne Rueckfrage
    ersetzen, auch auf einer Maschine, die hyprlock von Hand installiert
    hat, weil sie es benutzen will.
    """
    text = _code(_pkgbuild("zepos-lock"))
    assert "conflicts=('hyprlock')" in text, (
        "eine Maschine kann zepos-lock und hyprlock gleichzeitig haben")
    assert not re.search(r"^replaces=", text, re.MULTILINE), (
        "replaces ersetzt hyprlock ungefragt")


def test_the_bind_the_lock_package_exists_for_names_it():
    """Ein Rezept fuer ein Programm, das keine Taste mehr aufruft, ist
    ein Rezept, das nichts mehr absichert.

    Zeilengenau: `zepos-lock` steht in dieser Vorlage auch im Kommentar
    ueber der Bindung.
    """
    hypr = _read(ROOT / "src" / "templates" / "hyprland-universal-config.template")
    binds = [line.strip() for line in hypr.splitlines()
             if line.strip().startswith("bind")]
    assert "bind = $mainMod, L, exec, zepos-lock" in binds, (
        "SUPER+L ruft den Sperrbildschirm nicht mehr auf")


def test_the_lock_source_tree_travels_with_the_version_file():
    """lock/meson.build liest `cat ../VERSION` - also einen Pfad NEBEN
    dem Verzeichnis.

    Flach ausgepackt gaebe es dieses Neben nicht, und meson brueche beim
    Setup ab. Dieselbe Anordnung wie bei logout/, und derselbe Grund.
    """
    build = _read(PACKAGING / "build.sh")
    assert 'rsync -a "$REPO/lock" "$stage"/' in build, (
        "der Quell-Tarball von zepos-lock behaelt sein Verzeichnis nicht")
    assert "selected_holds zepos-lock" in build, (
        "build.sh baut fuer zepos-lock gar keinen Quell-Tarball")

    meson = _read(ROOT / "lock" / "meson.build")
    assert "'..', 'VERSION'" in meson, (
        "lock/meson.build liest die Version nicht aus VERSION - dann steht "
        "die Zahl zweimal im Baum")


def test_no_recipe_pulls_gtk3_back_in():
    """Die Entscheidung vom 11.08.2026 gilt fuer die ganze Oberflaeche.

    Ein `depends=('gtk3')` in irgendeinem Rezept dieses Verzeichnisses
    waere der Weg, auf dem das alte Toolkit zurueckkommt - nicht als
    Fenster, das jemand sieht, sondern als Zeile, die niemand liest.
    """
    offenders = []
    for recipe in _recipes():
        text = _code(_read(recipe))
        if re.search(r"'gtk3'|'gtk\+-3", text):
            offenders.append(recipe.parent.name)
    assert offenders == [], f"Rezepte, die GTK3 fordern: {offenders}"


def test_nobody_packages_hyprland_qtutils_again():
    """Spec §4.3 lists hyprland-qtutils among the components that are
    only in the AUR. That stopped being true: upstream renamed the
    project hyprland-guiutils, Arch carries it in extra (0.2.2 at the
    pinned snapshot) with `replaces=hyprland-qtutils`, it ships the same
    /usr/bin/hyprland-dialog, and zepos-hyprland already depends on it
    because Hyprland 0.56.1 does. A second package installing that path
    would be a file conflict with the one that is already there."""
    assert not (PACKAGING / "hyprland-qtutils").exists(), (
        "packaging/hyprland-qtutils exists; hyprland-guiutils in extra is "
        "the same programs under the name upstream gave them")
    assert "'hyprland-guiutils'" in _code(_pkgbuild("zepos-hyprland")), (
        "zepos-hyprland no longer depends on hyprland-guiutils, so nothing "
        "provides /usr/bin/hyprland-dialog for Hyprland's own dialogs")


# --------------------------------------------------------------------
# The meta package
# --------------------------------------------------------------------

def test_the_meta_package_is_what_the_installer_installs():
    """installer/core/translate.py hands archinstall exactly one package
    name, so this recipe is where the shape of an installed ZepOS is
    decided. If the two disagree, the installation succeeds and produces
    a machine with a base system and no desktop."""
    translate = _read(ROOT / "installer" / "core" / "translate.py")
    name = re.search(r'ZEPOS_META_PACKAGE = "([^"]+)"', translate)
    assert name, "installer/core/translate.py no longer names a meta package"
    assert (PACKAGING / name.group(1) / "PKGBUILD").is_file(), (
        f"the installer installs {name.group(1)} and there is no recipe for it")


def test_the_meta_package_pulls_in_the_compositor_and_the_five_plugins():
    """src/plugins.py decides at generation time, from the objects on the
    machine. A desktop installed without them comes up, looks finished,
    and has no title bars, no zones and a launcher that fell back to
    zepos-menu - with nothing in any log."""
    text = _code(_pkgbuild("zepos-desktop"))
    for needed in ("zepos-config", "zepos-keyring", "zepos-hyprland"):
        assert f"'{needed}'" in text, f"zepos-desktop does not pull in {needed}"
    for plugin in SPEC_PLUGINS:
        assert f"'zepos-{plugin}'" in text, (
            f"zepos-desktop does not pull in zepos-{plugin}")


def test_the_meta_package_names_the_failsafe_launcher():
    """zepos-menu is not a preference in this list. src/plugins.py writes
    it into plugins.conf as the replacement for SUPER+SPACE when the
    hyprlaunch object is not there (§7.4), which is precisely the
    situation in which nothing else can be relied on - and five generated
    helper scripts pipe their lines into it as well."""
    assert "'zepos-menu'" in _code(_pkgbuild("zepos-desktop")), (
        "zepos-desktop does not pull in zepos-menu, so the §7.4 failsafe "
        "for SUPER+SPACE has nothing to fall back onto")


def test_no_recipe_and_no_image_carries_wofi_any_more():
    """Der Nachweis, dass der Ersatz einer IST.

    Ein Rezept, das zepos-menu benennt und wofi daneben stehen laesst,
    installiert beide - und niemand merkt, dass der Ersatz nie benutzt
    wird, weil das Alte ja noch da ist. Gemessen wird gegen den Code
    ohne Kommentare: packaging/zepos-desktop/PKGBUILD ERKLAERT die
    Ablesung, die zu diesem Wechsel gefuehrt hat, und eine Pruefung, die
    Erklaerungen als Code liest, faende den Fehler in dem Absatz, der
    seine Abwesenheit beschreibt.
    """
    for recipe in _recipes():
        assert "wofi" not in _code(_read(recipe)), (
            f"packaging/{recipe.parent.name}/PKGBUILD names wofi")
    assert "wofi" not in _packages_x86_64(), (
        "the smoke image still installs wofi")


def test_the_meta_package_leaves_the_kernel_to_archinstall():
    """archinstall installs the base system and knows which kernel and
    which firmware this machine needs. A desktop package that owns the
    kernel cannot be installed next to linux-lts."""
    depends = re.search(r"^depends=\((.*?)^\)", _pkgbuild("zepos-desktop"), re.S | re.M)
    assert depends, "zepos-desktop has no depends array"
    listed = set(re.findall(r"'([^']+)'", depends.group(1)))
    for absent in ("linux", "linux-firmware", "base", "mkinitcpio", "grub",
                   "systemd-boot", "mesa"):
        assert absent not in listed, (
            f"zepos-desktop depends on {absent}, which is not the desktop's "
            f"to decide")


# --------------------------------------------------------------------
# The build driver, once more
# --------------------------------------------------------------------

def test_the_meta_package_is_built_after_everything_it_names():
    """makepkg --syncdeps resolves a meta package's depends like any
    other recipe's, so building it is what proves every name in that list
    exists in some repository - the one failure mode a meta package has,
    and one that otherwise appears on a user's machine. Its ZepOS
    dependencies are the packages the recipes before it produced."""
    order = _build_order()
    assert order[-1] == "zepos-desktop", (
        "zepos-desktop is not the last recipe built; the packages it "
        "depends on would not be in the container yet")


def test_the_keyring_is_built_before_the_meta_package_that_needs_it():
    order = _build_order()
    assert order.index("zepos-keyring") < order.index("zepos-desktop")


def test_an_unsigned_build_refuses_the_two_recipes_that_need_a_key():
    """zepos-keyring IS the key, and zepos-desktop depends on it. The
    rest of the repository still builds with --no-sign, which is what the
    flag is for; it is simply not a complete repository, and saying so in
    the build is cheaper than discovering it from a meta package that
    resolves on the build machine and nowhere else."""
    build = _read(PACKAGING / "build.sh")
    assert "NEEDS_KEY=(zepos-keyring zepos-desktop)" in build, (
        "packaging/build.sh does not know which recipes need a key")
    assert "zepos-keyring and zepos-desktop are NOT being built" in build, (
        "an unsigned build does not say what it left out")


# --------------------------------------------------------------------
# Die Bildschirmanordnung - was die Pakete davon tragen muessen
# --------------------------------------------------------------------

def test_the_guard_is_a_command_the_package_installs():
    """Ohne ihn gibt es keinen Rueckweg aus einer falschen Anordnung.

    src/displays.py wendet nichts an, bevor der Waechter bereit ist
    (arm_and_apply -> GuardRefused). Liegt er nicht unter /usr/bin, ist
    das auf einer Installation kein stiller Verlust einer Bequemlichkeit,
    sondern eine Seite, die gar nichts mehr anwendet - und das ist die
    bessere Haelfte dieses Fehlers.
    """
    recipe = _pkgbuild("zepos-config")

    assert "bin/zepos-displays-guard" in recipe, (
        "zepos-config installiert den Waechter nicht nach /usr/bin")
    assert (ROOT / "src" / "bin" / "zepos-displays-guard").is_file()


def test_nothing_still_depends_on_the_last_gtk3_program():
    """nwg-displays war das letzte GTK3-Programm dieses Systems.

    GEMESSEN am 12.08.2026 an nwg-displays 0.4.3: main.py:26
    `gi.require_version("Gtk", "3.0")`, tools.py:12 Gdk 3.0, main.py:28
    GtkLayerShell 0.1. Ersetzt durch die Seite "Bildschirme" von
    zepos-settings-gui; eine Abhaengigkeit, die es zurueckholt, holt
    libgtk-3 mit zurueck.

    Gefragt werden die ABHAENGIGKEITSLISTEN und nicht die ganze Datei:
    zwei Rezepte erklaeren den Wegfall und nennen den Namen dabei, eins
    davon in einer Fehlermeldung, die makepkg wirklich ausgibt. Eine
    Pruefung ueber die ganze Datei verboete, die Begruendung
    hinzuschreiben - und damit genau das, was dieses Projekt an jeder
    anderen Stelle verlangt.
    """
    for recipe in _recipes():
        body = _code(_read(recipe))
        for field in ("depends", "makedepends", "optdepends", "checkdepends"):
            for block in re.findall(rf"^{field}=\((.*?)^\)", body, re.S | re.M):
                assert "nwg-displays" not in block, (
                    f"{recipe.parent.name} haengt in {field} wieder an "
                    "nwg-displays")


def test_the_desktop_ships_the_window_that_replaced_it():
    """Eine Monitoranordnung ohne Oberflaeche waere schlechter als die
    GTK3-Oberflaeche, die sie ersetzt hat."""
    depends = re.search(r"^depends=\((.*?)^\)",
                        _code(_pkgbuild("zepos-desktop")), re.S | re.M)
    assert depends, "zepos-desktop hat keine depends-Liste"
    assert re.search(r"^\s*\'zepos-settings-gui\'", depends.group(1), re.M), (
        "zepos-desktop bringt das Fenster nicht mit, in dem die Monitore "
        "eingestellt werden")
