# SPDX-License-Identifier: GPL-3.0-or-later
"""The guard that stops an image being built from an older tree.

WHAT WENT WRONG, AND WHY A TEST OF THE GUARD IS NOT A TEST OF THE BUILD
    On 10.08.2026 the release ISO was built at 12:12 from packages built
    on 06.08 at 17:12, written to a USB stick and handed over. It was
    missing the TypeError fix in installer/gui/app.py it had been
    rebuilt for, and it still carried icon_manager.py under a name the
    tree had already stopped using. iso/build.sh checked that a
    repository existed; nothing checked that it was the same tree.

    packaging/check-current.py is that check. These tests do not build
    anything: each starts from a repository that matches this tree, puts
    exactly one thing back into a state that shipped, and requires the
    checker to name it. A guard that has only ever been run against a
    correct repository is a guard nobody has seen work.

WHY THE FIXTURE IS SYNTHESISED AND NOT packaging/out/
    Two reasons, and the second is the one that bites.

    Whether the packages on this machine are current is a fact about
    when somebody last ran packaging/build.sh. Asserting on it would
    turn every source edit into a red suite until a rebuild, and a
    suite that is red for a reason nobody has to act on is a suite
    people stop reading.

    Worse, injecting a defect into an already-stale repository proves
    nothing at all: the finding asserted on would appear with the
    injection removed. _repo_matching_the_tree() therefore rebuilds each
    package from the tree first, so the checker starts from silence and
    the one finding can only have come from the mutation - which is why
    the counts below are exact rather than `any(...)`.
"""
import importlib.util
import io
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REPO_DIR = REPO / "packaging" / "out" / "x86_64"

# packaging/check-current.py is a script with a hyphen in its name, so it
# cannot be imported by name. It is loaded as a file, the same way
# iso/build.sh runs it as a file.
_SPEC = importlib.util.spec_from_file_location(
    "check_current", REPO / "packaging" / "check-current.py")
assert _SPEC is not None and _SPEC.loader is not None
check_current = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_current)


needs_repo = pytest.mark.skipif(
    not (REPO_DIR / "zepos-config-0.1.0-1-any.pkg.tar.zst").exists(),
    reason="no built repository in packaging/out/ - run packaging/build.sh")

needs_zstd = pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason="tarfile reads zstd from Python 3.14")


def _rewrite(source: Path, destination: Path, *, rename=None, replace=None):
    """A copy of a package with one file renamed, or one file's bytes
    replaced. Everything else is carried across unchanged."""
    with tarfile.open(source, "r:zst") as archive, \
            tarfile.open(destination, "w:zst") as out:
        for entry in archive:
            data = b""
            if entry.isfile():
                extracted = archive.extractfile(entry)
                assert extracted is not None
                data = extracted.read()
            if rename and entry.name == rename[0]:
                entry.name = rename[1]
            if replace and entry.name == replace[0]:
                data = replace[1]
            entry.size = len(data)
            out.addfile(entry, io.BytesIO(data) if entry.isfile() else None)


def _break_one(tmp_path: Path, name: str, **mutation) -> Path:
    """A repository that matches the tree, with one thing wrong in it.

    Built on _repo_matching_the_tree() and not on packaging/out/,
    because the packages on this machine may already be stale - and a
    test that injects a defect into an already-defective repository
    proves nothing: it would pass with the injection removed. Starting
    from a repository the checker accepts means the finding asserted
    below can only have come from the mutation.
    """
    staged = _repo_matching_the_tree(tmp_path)
    package = staged / f"{name}-0.1.0-1-any.pkg.tar.zst"
    broken = tmp_path / f"broken-{package.name}"
    _rewrite(package, broken, **mutation)
    package.write_bytes(broken.read_bytes())
    return staged


def _repo_matching_the_tree(tmp_path: Path) -> Path:
    """A repository that IS this tree, built from it.

    Not packaging/out/ itself, deliberately. Whether the packages on
    this machine happen to be current is a fact about when somebody last
    ran packaging/build.sh, and asserting on it would turn every source
    edit into a red suite until a rebuild - which teaches people to stop
    reading the result. The property worth holding is the checker's:
    given a repository that matches, it finds nothing.

    So each real package is rewritten member by member - every file
    replaced with the tree's current bytes, every member whose source
    has been renamed away dropped, and every tree file the package's own
    directories should carry added. The layout stays the packages' own;
    only the contents become certain.
    """
    staged = tmp_path / "current"
    staged.mkdir()

    for name in check_current.OWN_PACKAGES:
        real = REPO_DIR / f"{name}-0.1.0-1-any.pkg.tar.zst"
        members: dict[str, bytes] = {}
        # Which tree directory each shipped directory came from, so a
        # file added to it can be given the right destination.
        roots: dict[Path, str] = {}

        with tarfile.open(real, "r:zst") as archive:
            for entry in archive:
                if not entry.isfile():
                    continue
                if check_current._is_generated(entry.name):
                    extracted = archive.extractfile(entry)
                    assert extracted is not None
                    members[entry.name] = extracted.read()
                    continue
                source = check_current._source_for(entry.name)
                if source is None or not source.exists():
                    continue        # renamed away: the package drops it
                members[entry.name] = source.read_bytes()
                # Nur, wenn der Name unterwegs gleich bleibt.
                #
                # "alles vor dem Dateinamen" ist genau dann ein
                # Verzeichnis, wenn der Zielname der Quellname ist. Seit
                # zepos-config Dateien UNTER ANDEREM NAMEN ablegt -
                # src/login/greetd.toml wird /etc/greetd/zepos.toml, weil
                # das Paket greetd config.toml selbst besitzt, und
                # src/boot/grub-zepos.cfg wird
                # /etc/default/grub.d/10-zepos.cfg - schneidet dieselbe
                # Rechnung mitten in einen Pfad. Gemessen als
                # "etc/default/grub.grub-zepos.cfg": ein Ziel, das es
                # nicht gibt, gegen das der Pruefer dann zu Recht
                # protestierte.
                #
                # Eine umbenannte Einzeldatei hat auch kein Verzeichnis,
                # in das etwas hinzukommen koennte - check-current.py's
                # SOURCE_OF nennt jede von ihnen einzeln, und genau
                # deshalb faellt sie hier heraus statt zu fehlen.
                if entry.name.rsplit("/", 1)[-1] == source.name:
                    roots[source.parent] = entry.name[
                        :len(entry.name) - len(source.name)]

        for directory, prefix in roots.items():
            shipped = {Path(m).name for m in members if m.startswith(prefix)}
            kinds = {Path(n).suffix for n in shipped}
            for entry_path in sorted(directory.iterdir()):
                if not entry_path.is_file() or entry_path.name in shipped:
                    continue
                if (entry_path.name.startswith(".")
                        or entry_path.suffix not in kinds):
                    continue
                members[prefix + entry_path.name] = entry_path.read_bytes()

        with tarfile.open(staged / real.name, "w:zst") as out:
            for member, data in members.items():
                info = tarfile.TarInfo(member)
                info.size = len(data)
                out.addfile(info, io.BytesIO(data))

    _stage_meta_package(staged)
    return staged


def _stage_meta_package(staged: Path, depends: list[str] | None = None) -> Path:
    """Ein zepos-desktop, dessen Abhaengigkeitsliste die des Rezepts ist.

    Nicht das echte Paket aus packaging/out/ kopiert, aus demselben
    Grund, aus dem die anderen hier neu zusammengesetzt werden: ob das
    Paket auf DIESER Maschine gerade aktuell ist, haengt daran, wann
    jemand zuletzt gebaut hat, und ein Test, der darauf besteht, wird bei
    jeder Quelltextaenderung rot, bis jemand baut.

    Ein Meta-Paket ist ausserdem billig nachzubauen: es besitzt genau
    eine Datei, und die einzige Aussage, die der Pruefer daran misst,
    steht in .PKGINFO.
    """
    if depends is None:
        depends = sorted(check_current._recipe_depends(check_current.META_PACKAGE))
    pkginfo = "pkgname = {}\npkgver = 0.1.0-1\narch = any\n".format(
        check_current.META_PACKAGE)
    pkginfo += "".join(f"depend = {name}\n" for name in depends)

    package = staged / f"{check_current.META_PACKAGE}-0.1.0-1-any.pkg.tar.zst"
    with tarfile.open(package, "w:zst") as out:
        data = pkginfo.encode("utf-8")
        info = tarfile.TarInfo(".PKGINFO")
        info.size = len(data)
        out.addfile(info, io.BytesIO(data))
    return package


@needs_repo
@needs_zstd
def test_a_repository_that_matches_the_tree_produces_no_findings(tmp_path):
    """The state the checker has to accept, or it blocks every build."""
    assert check_current.check(_repo_matching_the_tree(tmp_path)) == []


@needs_repo
@needs_zstd
def test_a_package_older_than_its_source_is_caught(tmp_path):
    """The first failure of 10.08: app.py in the package was four days
    behind app.py in the tree, and the version string was the same on
    both sides."""
    staged = _break_one(
        tmp_path, "zepos-installer-gui",
        replace=("usr/share/zepos-installer/installer/gui/app.py",
                 b"# what the package shipped before the fix\n"))

    problems = check_current.check(staged)

    assert len(problems) == 1, problems
    assert "gui/app.py differs" in problems[0]


@needs_repo
@needs_zstd
def test_a_package_carrying_a_renamed_file_is_caught(tmp_path):
    """The second failure of 10.08: the tree had template_processor.py,
    the package still had icon_manager.py. Comparing files that appear
    on both sides would have found nothing to compare - the check has to
    notice a package path with no source, and a source with no package
    path."""
    staged = _break_one(
        tmp_path, "zepos-config",
        rename=("usr/share/zepos/template_processor.py",
                "usr/share/zepos/icon_manager.py"))

    problems = check_current.check(staged)

    assert len(problems) == 2, problems
    assert any("icon_manager.py" in p and "does not exist" in p
               for p in problems), problems
    assert any("template_processor.py" in p and "no package ships" in p
               for p in problems), problems


@needs_repo
@needs_zstd
def test_a_package_that_was_never_built_is_caught(tmp_path):
    """A repository can be current and still be incomplete. Removing
    zepos-installer-tui leaves three packages that all match the tree."""
    staged = _repo_matching_the_tree(tmp_path)
    (staged / "zepos-installer-tui-0.1.0-1-any.pkg.tar.zst").unlink()

    problems = check_current.check(staged)

    assert any("not built at all" in p and "zepos-installer-tui" in p
               for p in problems), problems


@needs_repo
@needs_zstd
def test_two_builds_of_the_same_package_are_refused(tmp_path):
    """Two versions of one package in the repository means the checker
    would have to guess which one pacman will install. It must not
    guess: repo-add keeps the newest, but the older file is still there
    to be installed by name."""
    staged = _repo_matching_the_tree(tmp_path)
    (staged / "zepos-config-0.2.0-1-any.pkg.tar.zst").write_bytes(
        (staged / "zepos-config-0.1.0-1-any.pkg.tar.zst").read_bytes())

    with pytest.raises(SystemExit, match="2 builds of zepos-config"):
        check_current.check(staged)


@needs_repo
@needs_zstd
def test_a_meta_package_missing_a_dependency_is_caught(tmp_path):
    """Der Fund, der diese Pruefung ueberhaupt gibt.

    Gemessen am 11.08.2026: eine Installation vom fertigen Medium brach
    nach fuenf Minuten und einer geloeschten Zielplatte ab mit "Failed to
    enable unit: Unit greetd.service does not exist". zepos-config und
    zepos-installer waren neu gebaut, zepos-desktop nicht - und weil ein
    Meta-Paket ausser der Lizenz keine Datei besitzt, verglich der
    Pruefer nichts und meldete "the built packages match this tree".
    """
    staged = _repo_matching_the_tree(tmp_path)
    wanted = sorted(check_current._recipe_depends(check_current.META_PACKAGE))
    assert "greetd" in wanted, (
        "der Desktop haengt nicht mehr auf greetd; dieser Test bewacht "
        "dann nichts mehr")
    _stage_meta_package(staged, [name for name in wanted if name != "greetd"])

    problems = check_current.check(staged)

    assert [p for p in problems if "greetd" in p], problems
    assert len(problems) == 1, problems


@needs_repo
@needs_zstd
def test_a_meta_package_carrying_a_dependency_the_recipe_dropped_is_caught(tmp_path):
    """Die andere Richtung, und sie ist keine Formalie: ein Paket, das
    mehr verlangt als sein Rezept, ist ein Paket aus einem aelteren Baum -
    und der naechste Bau nimmt die Abhaengigkeit weg, ohne dass irgendwo
    stuende, dass die Installation von gestern sie noch hat."""
    staged = _repo_matching_the_tree(tmp_path)
    wanted = sorted(check_current._recipe_depends(check_current.META_PACKAGE))
    _stage_meta_package(staged, wanted + ["ein-paket-das-niemand-mehr-will"])

    problems = check_current.check(staged)

    assert [p for p in problems if "ein-paket-das-niemand-mehr-will" in p], problems
    assert len(problems) == 1, problems


@needs_repo
@needs_zstd
def test_a_meta_package_that_was_not_built_is_caught(tmp_path):
    """Es steht nicht in OWN_PACKAGES, also faellt es nicht unter das
    "not built at all" der anderen vier - und ein Medium ohne Meta-Paket
    installiert einen Desktop, der aus nichts besteht."""
    staged = _repo_matching_the_tree(tmp_path)
    (staged / f"{check_current.META_PACKAGE}-0.1.0-1-any.pkg.tar.zst").unlink()

    problems = check_current.check(staged)

    assert problems == [f"not built at all: {check_current.META_PACKAGE}"], problems


def test_the_recipe_is_read_the_way_a_recipe_is_written():
    """Der Leser selbst, gegen die zwei Formen, die dieses Rezept
    benutzt - beide sind ihm beim ersten Lauf um die Ohren geflogen.

    Eine Begruendung NEBEN dem Eintrag benutzt auch Anfuehrungszeichen,
    und mehrere zusammengehoerende Namen stehen in einer Zeile.
    """
    depends = check_current._recipe_depends(check_current.META_PACKAGE)

    # Aus der Zeile "'papirus-icon-theme'   # ... icon-theme 'Papirus-Dark'".
    assert "papirus-icon-theme" in depends
    assert "Papirus-Dark" not in depends, (
        "der Leser haelt einen Namen aus einem Kommentar fuer eine "
        "Abhaengigkeit")

    # Aus der Zeile "'grim' 'slurp' 'satty'    # SUPER+S ...".
    for tool in ("grim", "slurp", "satty"):
        assert tool in depends, (
            f"{tool} fehlt - der Leser sieht nur den ersten Namen einer Zeile")


def test_the_iso_build_runs_the_checker_before_it_builds_anything():
    """The wiring, which no unit test of the checker can see.

    Position matters as much as presence: the check has to happen before
    the mkarchiso container starts, or it reports a stale repository
    twenty minutes after the image was made from it.
    """
    build = (REPO / "iso" / "build.sh").read_text(encoding="utf-8")

    assert "packaging/check-current.py" in build, (
        "iso/build.sh does not run the currency check at all")

    guard = build.index("packaging/check-current.py")
    mkarchiso = build.index("mkarchiso -v -w")
    assert guard < mkarchiso, (
        "the currency check runs after mkarchiso, which is too late")


# --- ein Paket ohne Rezept ------------------------------------------------
#
# AM 11.08.2026 AUSGELIEFERT
#     wlogout-1.2.2-1 lag um 11:08 in packaging/out. Noch am selben Tag
#     loeste zepos-logout es ab und sein Rezept wurde geloescht. Der Bau
#     um 19:32 signierte die Datei trotzdem NEU, nahm sie in die
#     Datenbank auf und legte sie auf das Medium - und check-current.py
#     sagte "the built packages match this tree".
#
#     Die Aussage stimmte und war nutzlos: beide Durchgaenge vergleichen
#     Paketinhalte GEGEN den Baum, und ein Paket, das der Baum nicht mehr
#     kennt, hat nichts, wogegen es verglichen wuerde. Niemand fragte, ob
#     es ueberhaupt noch hergehoert.


# Die beiden Wachen fehlten hier als einzigen zweien in dieser Datei, und
# das faellt nur dort auf, wo noch nie jemand gebaut hat: beide gehen
# ueber _repo_matching_the_tree(), das die echten Pakete aus
# packaging/out/x86_64/ liest. In einem frischen Arbeitsbaum gibt es das
# Verzeichnis nicht - gemessen am 11.08.2026 in einem git-worktree, wo
# genau diese zwei mit FileNotFoundError auf
# zepos-config-0.1.0-1-any.pkg.tar.zst umfielen, waehrend die acht
# anderen ordentlich uebersprungen wurden. Ein Test, dessen Ergebnis
# davon abhaengt, wann jemand zuletzt gebaut hat, ist genau das, was der
# Kopf von _stage_meta_package() vermeiden wollte.
@needs_repo
@needs_zstd
def test_a_package_whose_recipe_is_gone_is_found(tmp_path):
    """Die Luecke selbst. Ein Paket, das kein Rezept mehr hat, ist auf
    einem Medium schlimmer als ein veraltetes: es wird mitsigniert, also
    bekommt ein Nutzer auf `pacman -S <name>` etwas aus unserer Hand,
    das wir nicht mehr bauen und nicht mehr berichtigen koennen."""
    staged = _repo_matching_the_tree(tmp_path)
    (staged / "wlogout-1.2.2-1-x86_64.pkg.tar.zst").write_bytes(b"")

    findings = check_current.check(staged)

    assert len(findings) == 1, findings
    assert findings[0].startswith("wlogout:"), findings[0]


@needs_repo
@needs_zstd
def test_a_package_that_still_has_a_recipe_is_not_reported(tmp_path):
    """Die Gegenrichtung, und sie ist der Grund, aus dem die Namen aus
    den PKGBUILDs gelesen werden statt hier aufgezaehlt: packaging/astal/
    bringt drei Namen hervor, von denen keiner "astal" heisst, und
    packaging/hyprland-plugins/ drei weitere. Eine Aufzaehlung haette
    sechs Pakete als verwaist gemeldet."""
    staged = _repo_matching_the_tree(tmp_path)
    for name in ("libastal-4-r912.9dac92f-1-x86_64",
                 "zepos-hyprbars-0.56.0-1-x86_64",
                 "zepos-lock-0.1.0-1-x86_64"):
        (staged / f"{name}.pkg.tar.zst").write_bytes(b"")

    assert check_current.check(staged) == []


def test_the_names_come_from_the_recipes_and_include_the_multi_package_ones():
    """Gemessen statt angenommen: astal und hyprland-plugins liefern
    Namen, die nicht wie ihr Verzeichnis heissen."""
    names = check_current._built_names()

    for expected in ("libastal-io", "libastal-4", "libastal-notifd",
                     "zepos-config", "zepos-lock", "zepos-menu",
                     "zepos-desktop"):
        assert expected in names, f"{expected} fehlt in {sorted(names)}"
    assert "wlogout" not in names, "das Rezept ist geloescht"
    assert "zepos-logout" not in names, (
        "das Rezept ist mit dem Programm geloescht (Aufgabe 26, "
        "19.08.2026, Regel 14)")
