#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Does the built repository still match the tree it was built from?

This exists because it did not, and the difference was handed to a
person on a USB stick.

Measured, 10.08.2026: the release ISO was built at 12:12 from packages
built on 06.08 at 17:12. iso/build.sh checks that packaging/out/ holds a
repository; nothing checked that the repository holds THIS tree. Four
days of fixes were absent from the image, including the TypeError in
installer/gui/app.py that stopped the installer on real hardware - the
very fix the image had been rebuilt for - and the rename of
icon_manager.py, which the image still shipped under its old name.

The version string cannot catch this. Every ZepOS package is 0.1.0-1
and stays 0.1.0-1 across such a change, so the package file name, the
database entry and pacman's own comparison are all identical before and
after. What differs is the content, so content is what this compares.

WHAT IS CHECKED

  forward   every file a package installs from this repository is
            byte-identical to the file it came from, and no package
            installs a file whose source no longer exists. The second
            half is what catches a rename: the tree had
            template_processor.py, the package still had
            icon_manager.py, and no comparison of matching names would
            ever have looked at either.

  backward  for every directory a package already ships, every file in
            the corresponding source directory is shipped. A file added
            to src/templates/ that the recipe never installs fails here.

  das Meta-Paket  seine Abhaengigkeitsliste, gegen die des Rezepts.
            Es gehoert in keinen der beiden Durchgaenge oben, weil es
            genau eine Datei besitzt - die Lizenz - und die ist
            GENERATED. Alles, WAS zepos-desktop ist, steht in seinem
            depends, und das steht in keiner Datei, die ein
            Bytevergleich anfassen wuerde.

            Gemessen, 11.08.2026: eine Installation vom fertigen Medium
            brach am Ende ab mit "Failed to enable unit: Unit
            greetd.service does not exist". Der Grund war ein
            zepos-desktop aus einem Baum von vorher, in dem greetd noch
            nicht in depends stand - fuenf Minuten Installation, eine
            geloeschte Zielplatte, und dieser Pruefer sagte "the built
            packages match this tree", weil er die einzige Zeile, die
            sich geaendert hatte, nicht ansah.

WHAT IS NOT CHECKED, AND WHY

  The backward pass derives its expectation from the directories the
  package ALREADY ships, deliberately: the alternative is to repeat the
  recipes' copy lists here, and a second copy of that list is a second
  definition that would part company with the first. The gap this
  leaves is a whole directory the recipe never installed at all - that
  is a recipe review, not a currency check.

  Generated files have no source to compare against and are listed as
  GENERATED below. A .mo is compiled from a .po, /etc/skel is written by
  settings.save(), and the licence is a copy under a different name.
"""
import argparse
import hashlib
import re
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPO_DIR = REPO / "packaging" / "out" / "x86_64"

# Where a package path comes from in this tree. Longest prefix wins, so
# usr/share/zepos-installer/ is tried before usr/share/zepos/ would be -
# they are distinct prefixes, but only because of the hyphen, and
# sorting by length rather than relying on that is one less thing to get
# wrong later.
SOURCE_OF = {
    "usr/share/zepos/": "src/",
    "usr/share/zepos-installer/installer/": "installer/",
    "usr/share/zepos-installer/branding/": "src/branding/",
    "usr/bin/zepos-install": "installer/bin/zepos-install",
    "usr/bin/zepos-generate": "src/bin/zepos-generate",
    "usr/bin/zepos-settings": "src/bin/zepos-settings",
    "usr/bin/zepos-doctor": "src/bin/zepos-doctor",
    "usr/bin/zepos-update": "src/bin/zepos-update",
    "usr/bin/zepos-greeter": "src/bin/zepos-greeter",
    "usr/bin/zepos-session": "src/bin/zepos-session",
    # Der Waechter der Bildschirmseite. Ein EIGENER Prozess, und das ist
    # der ganze Grund, aus dem er hier steht: ein Rueckfall, der in der
    # Hauptschleife des Fensters laeuft, stirbt mit dem Fenster - genau
    # der Fehler, den nwg-displays hatte (main.py:1017, "hofft, dass der
    # Compositor es merkt").
    "usr/bin/zepos-displays-guard": "src/bin/zepos-displays-guard",
    # Die Selbstaktualisierung. Drei Dateien aus src/system/, die unter
    # drei verschiedenen Namen landen - genau der Fall, fuer den diese
    # Tabelle Eintraege statt einer Regel hat. Der Haken traegt eine
    # Nummer im Namen, weil pacman seine Haken alphabetisch abarbeitet
    # und die Reihenfolge damit lesbar bleibt.
    "usr/lib/systemd/system/zepos-update.service":
        "src/system/zepos-update.service",
    "usr/lib/systemd/system/zepos-update.timer":
        "src/system/zepos-update.timer",
    "usr/share/libalpm/hooks/90-zepos-update.hook":
        "src/system/zepos-update.hook",
    # Die systemweite npm-Konfiguration, seit dem 20.08.2026. Auch hier
    # aendert sich der Name unterwegs: im Baum liegt sie bei den uebrigen
    # Systemdateien unter src/system/, auf der Maschine heisst sie
    # /etc/npmrc, weil npm genau diesen Pfad als globalconfig liest.
    "etc/npmrc": "src/system/npmrc",
    "etc/xdg-desktop-portal/hyprland-portals.conf":
        "src/system/hyprland-portals.conf",
    # Die Anmeldung, und die Namen aendern sich unterwegs. Das ist kein
    # Versehen: /etc/greetd/config.toml gehoert dem Paket greetd und
    # /etc/greetd/regreet.toml dem Paket greetd-regreet, also legt ZepOS
    # daneben ab - src/login/greetd.toml traegt die Messung. Genau fuer
    # so ein Umbenennen hat diese Tabelle Eintraege statt einer Regel.
    "etc/greetd/zepos.toml": "src/login/greetd.toml",
    "etc/greetd/zepos-regreet.toml": "src/login/regreet.toml",
    # Erzeugt aus src/greeter.py, im Baum abgelegt und von dort gepackt -
    # die Datei ist hier der Vergleichsgegenstand, weil das Paket sie
    # kopiert und nicht baut. Dass sie zu ihrem Erzeuger passt, prueft
    # tests/src/test_greeter.py.
    #
    # EINE JE THEMA, seit dem 12.08.2026. Sie liegen alle unter /etc,
    # und src/bin/zepos-greeter waehlt beim Start ueber /etc/zepos/theme
    # zwischen ihnen - das ist die ganze Umschaltung der Anmeldemaske,
    # und sie kommt ohne einen Lauf mit Rechten aus.
    "etc/greetd/zepos-greeter-zeptronit.css":
        "src/login/zepos-greeter-zeptronit.css",
    "etc/greetd/zepos-greeter-tageslicht.css":
        "src/login/zepos-greeter-tageslicht.css",
    "usr/share/wayland-sessions/zepos.desktop": "src/login/zepos.desktop",
    "usr/lib/systemd/system/greetd.service.d/10-zepos.conf":
        "src/login/greetd-service.conf",
    # Das Startmenue. Es kommt aus dem ISO-Profil und nicht aus src/,
    # weil das Medium und die Installation dasselbe Menue zeigen und eine
    # zweite Kopie im Baum die zweite waere, die veraltet -
    # packaging/build.sh legt es von dort ins Tarball. Die Schriften
    # liegen drueben in einem eigenen Verzeichnis und hier unter f/,
    # weil /etc/grub.d/00_header nur dort und im Themenverzeichnis
    # selbst nach *.pf2 sucht; die zwei Praefixe halten trotzdem je ein
    # Verzeichnis auf je eines ab.
    "etc/default/grub.d/10-zepos.cfg": "src/boot/grub-zepos.cfg",
    "usr/share/grub/themes/zepos/f/": "iso/profile-release/grub/fonts/",
    "usr/share/grub/themes/zepos/": "iso/profile-release/grub/themes/zepos/",
    # Und die zwei, die das Verzeichnis darueber ueberhaupt erst
    # erreichbar machen. Es liegt auf der verschluesselten Wurzel, und
    # grub-mkconfig verwirft von dort alles - src/boot/grub-zepos.cfg
    # traegt die Messung vom 17.08.2026. Der Haken spiegelt es nach
    # /boot; sie stehen hier einzeln, weil sie aus einem Verzeichnis
    # kommen und in zwei sehr verschiedene gehen.
    "usr/bin/zepos-grub-theme": "src/boot/zepos-grub-theme",
    "usr/share/libalpm/hooks/90-zepos-grub-theme.hook":
        "src/boot/zepos-grub-theme.hook",
    # Die Passphrase-Abfrage beim Starten. Sie kommt - anders als das
    # Startmenue eine Zeile darueber - NICHT aus dem ISO-Profil, und das
    # ist kein Versehen: das Medium fragt nach keiner Passphrase, es
    # installiert ja erst. Es gibt hier also nichts, was zwei Baeume
    # gemeinsam haetten, und die Dateien liegen unter src/.
    #
    # Erzeugt von packaging/make-plymouth-theme.py aus src/brand.py und
    # src/sizes.py, im Baum abgelegt und von dort gepackt - wie die
    # Anmeldemaske aus src/greeter.py. Das Paket kopiert sie, es baut
    # sie nicht; dass sie zu ihrem Erzeuger passen, prueft
    # tests/boot/test_plymouth.py.
    "usr/share/plymouth/themes/zepos/": "src/boot/plymouth-theme/",
    # Der Haken, der in der Initramfs das Gebietsschema setzt - zwei
    # Dateien, weil mkinitcpio beide Haelften verlangt: install/ wird
    # beim BAUEN der Initramfs gelesen, hooks/ laeuft beim STARTEN
    # darin. Sie sind auch deshalb einzeln aufgefuehrt und nicht ueber
    # ein Praefix: /usr/lib/initcpio/ gehoert dem Paket mkinitcpio, und
    # ein Praefix darauf haette jede fremde Datei dieses Verzeichnisses
    # als "aus unserem Baum" ausgegeben.
    #
    # Warum es sie gibt: plymouth schiebt jedes Zeichen durch mbrtowc,
    # also durch das Gebietsschema. Ohne UTF-8 verwirft es das erste
    # Byte jedes Umlauts, und auf dem Startbildschirm stand "geprft".
    # Die ganze Messung steht in installer/core/translate.py bei
    # PLYMOUTH_COMMAND.
    "usr/lib/initcpio/hooks/zepos-locale":
        "src/boot/initcpio/hooks/zepos-locale",
    "usr/lib/initcpio/install/zepos-locale":
        "src/boot/initcpio/install/zepos-locale",
}

# Installed by a recipe but not copied from a file in this tree. Each is
# a prefix.
GENERATED = (
    ".BUILDINFO", ".MTREE", ".PKGINFO", ".INSTALL",
    "etc/skel/",                    # written by settings.save()
    "usr/share/licenses/",          # LICENSE under another name
    "usr/share/locale/",            # compiled from po/
    "usr/share/applications/",      # desktop entries live in packaging/
    "usr/share/polkit-1/",
    # DIE ZWEI ABDRUECKE, UND SIE STEHEN ALS GANZE PFADE DA
    #
    #     Beide schreibt package() von zepos-config aus dem Baum, statt
    #     sie aus src/ zu kopieren - dort gibt es sie also nicht, und
    #     dieser Waechter meldete am 13.08.2026 zu Recht:
    #
    #         installs usr/share/zepos/shipped-bar.json, but
    #         src/shipped-bar.json does not exist
    #
    #     own-applications  die eigenen Anwendungen, aus den Rezepten
    #                       gelesen - src/apps.py, own().
    #     shipped-bar.json  die ausgelieferte Reihenfolge der Leiste, aus
    #                       style_definition.shipped_bar_imprint().
    #
    #     NICHT als Praefix "usr/share/zepos/": darunter liegt der ganze
    #     Quellbaum dieses Pakets, und ein Praefix naehme jede einzelne
    #     Datei davon von der Pruefung aus. Genau davor warnt der Absatz
    #     unter dieser Liste - ein Praefix ueber /usr/lib/systemd haette
    #     dort ein Drop-in ungeprueft durchgelassen.
    "usr/share/zepos/own-applications",
    "usr/share/zepos/shipped-bar.json",
)
# Hier stand "usr/lib/systemd/  # units live in packaging/". Das war
# richtig, solange dort nichts lag; seit zepos-config das greetd-Drop-in
# ausliefert, kommt der einzige Pfad unter /usr/lib/systemd aus src/login/
# und steht deshalb oben in SOURCE_OF. Ein Praefix, das alles unter
# /usr/lib/systemd von der Pruefung ausnimmt, haette das Drop-in
# ungeprueft durchgelassen - und ein Drop-in, das nicht mehr zu seiner
# Quelle passt, zeigt greetd auf eine Konfigurationsdatei, die es nicht
# gibt.

# The packages built from this repository's own sources. The rest of the
# repository is repackaged upstream software, whose currency is a
# version number and not this tree.
OWN_PACKAGES = (
    "zepos-config",
    "zepos-installer",
    "zepos-installer-gui",
    "zepos-installer-tui",
)

# Das Meta-Paket. Es steht NICHT in OWN_PACKAGES, weil die beiden
# Durchgaenge dort Dateien vergleichen und dieses Paket genau eine
# besitzt - die Lizenz, und die ist GENERATED. Seine ganze Aussage ist
# das depends, und das wird unten gegen das Rezept gehalten.
META_PACKAGE = "zepos-desktop"


def _recipe_depends(name: str) -> set[str]:
    """Die depends-Liste eines Rezepts, als Namen.

    Jede Zeile zaehlt nur bis zu ihrem ersten "#", und beide Haelften
    dieser Regel sind gemessen worden statt angenommen.

    Der Schnitt muss sein, weil das Rezept seine Begruendung NEBEN den
    Eintrag schreibt und dort ebenfalls Anfuehrungszeichen benutzt:

        'papirus-icon-theme'      # exec-once sets icon-theme 'Papirus-Dark'

    Ohne ihn liest das Muster "Papirus-Dark" und "Adwaita-dark" als
    Abhaengigkeiten - zwei Funde, die es nicht gibt.

    Am Zeilenanfang zu verankern waere der naheliegende Ausweg und der
    falsche: das Rezept schreibt mehrere Namen in eine Zeile, wo sie
    zusammengehoeren -

        'grim' 'slurp' 'satty'    # SUPER+S pipes grim through slurp
        'pipewire' 'pipewire-pulse' 'wireplumber'

    - und ein Anker verliert vier davon. Beides wurde beim ersten Lauf
    dieser Funktion gemessen, im selben Durchgang und in beide
    Richtungen: erst zwei erfundene Abhaengigkeiten, dann vier, die es
    im Rezept angeblich nicht mehr gab.

    Nur der Name vor einem etwaigen Versionsvergleich zaehlt: das Rezept
    schreibt 'zepos-hyprland>=0.56.1', und pacman speichert genau diese
    Zeichenkette - aber ein Vergleich, der an der Version haengt, meldet
    einen Unterschied bei jeder Versionsanhebung, ohne dass sich die
    LISTE geaendert haette.
    """
    text = (REPO / "packaging" / name / "PKGBUILD").read_text(encoding="utf-8")
    body = re.search(r"^depends=\((.*?)^\)", text, re.S | re.M)
    if body is None:
        return set()
    return {re.split(r"[<>=]", entry)[0]
            for line in body.group(1).splitlines()
            for entry in re.findall(r"'([^']+)'", line.split("#", 1)[0])}


def _package_depends(package: Path) -> set[str]:
    """Die depends-Liste, wie sie IM GEBAUTEN PAKET steht.

    .PKGINFO ist die Datei, die pacman liest; makepkg schreibt sie aus
    dem depends des Rezepts, das beim Bauen galt. Der Unterschied
    zwischen beiden ist genau die Frage, die dieser Pruefer stellt.
    """
    with tarfile.open(package, "r:zst") as archive:
        for entry in archive:
            if entry.name != ".PKGINFO":
                continue
            extracted = archive.extractfile(entry)
            assert extracted is not None
            text = extracted.read().decode("utf-8", errors="replace")
            return {re.split(r"[<>=]", value.strip())[0]
                    for line in text.splitlines()
                    if line.startswith("depend =")
                    for value in [line.split("=", 1)[1]]}
    return set()


def _meta_package_findings(repo_dir: Path) -> list[str]:
    """Ob das gebaute Meta-Paket noch dieselbe Liste traegt wie sein
    Rezept."""
    matches = sorted(repo_dir.glob(f"{META_PACKAGE}-[0-9]*.pkg.tar.zst"))
    if not matches:
        return [f"not built at all: {META_PACKAGE}"]

    built = _package_depends(matches[0])
    wanted = _recipe_depends(META_PACKAGE)

    problems = []
    for missing in sorted(wanted - built):
        problems.append(
            f"{META_PACKAGE}: the recipe depends on {missing} and the built "
            f"package does not. An installation would not get it - and for a "
            f"meta package the dependency list is the whole content, so no "
            f"file comparison can see this.")
    for extra in sorted(built - wanted):
        problems.append(
            f"{META_PACKAGE}: the built package depends on {extra} and the "
            f"recipe no longer does. The package was built from an older tree.")
    return problems


def _built_names() -> set[str]:
    """Jeder Paketname, den die Rezepte dieses Baums hervorbringen.

    Aus den PKGBUILDs gelesen und nicht hier aufgezaehlt: ein Rezept
    bringt nicht zwingend ein Paket mit seinem eigenen Namen hervor.
    packaging/astal/ liefert libastal-io, libastal-4 und
    libastal-notifd; packaging/hyprland-plugins/ liefert drei
    zepos-*-Namen. Eine Liste hier waere eine vierte Stelle, die mit den
    Rezepten Schritt halten muesste.

    Bash wird dafuer nicht gestartet - `pkgname=` ist in allen Rezepten
    dieses Baums entweder ein Wort oder eine Klammer voller Woerter,
    beides ohne Ersetzung.
    """
    names: set[str] = set()
    for recipe in sorted((REPO / "packaging").glob("*/PKGBUILD")):
        text = recipe.read_text(encoding="utf-8")
        match = re.search(r"^pkgname=\(([^)]*)\)", text, re.MULTILINE)
        if match:
            names.update(word.strip("'\"") for word in match.group(1).split())
            continue
        match = re.search(r"^pkgname=(\S+)", text, re.MULTILINE)
        if match:
            names.add(match.group(1).strip("'\""))
    return names


def _orphan_findings(repo_dir: Path) -> list[str]:
    """Pakete im Repository, zu denen es kein Rezept mehr gibt.

    WAS AM 11.08.2026 AUSGELIEFERT WURDE
        wlogout-1.2.2-1 lag um 11:08 in packaging/out. Am selben Tag
        wurde es durch das eigene zepos-logout abgeloest und sein Rezept
        geloescht. Der Bau um 19:32 hat die Datei trotzdem NEU SIGNIERT,
        in die Datenbank aufgenommen und auf das Medium gelegt - und
        dieser Pruefer sagte dazu "the built packages match this tree".

        Er sagte die Wahrheit, und sie war nutzlos: beide Durchgaenge
        vergleichen Paketinhalte gegen den Baum, und ein Paket, das der
        Baum nicht mehr kennt, hat nichts, wogegen es verglichen wuerde.
        Die Frage "gehoert das hier ueberhaupt noch her" wurde nie
        gestellt.

    Warum das nicht nur unordentlich ist: die Datei wird MITSIGNIERT.
    Ein Nutzer, der unserem Repository vertraut, bekommt auf
    `pacman -S wlogout` ein GTK3-Programm aus unserer Hand - aus einem
    Rezept, das es nicht mehr gibt, also auch ohne jede Moeglichkeit, es
    je wieder zu bauen oder zu berichtigen.
    """
    known = _built_names()
    problems = []
    for package in sorted(repo_dir.glob("*.pkg.tar.zst")):
        # Name ohne -pkgver-pkgrel-arch: drei Bindestrich-Felder von
        # hinten. Kuerzer als ein Muster ueber erlaubte Versionszeichen,
        # und es kommt ohne Annahme darueber aus, was in einer Version
        # stehen darf - r912.9dac92f und 0.1.0.r20.1eed6ee sind beide da.
        stem = package.name[:-len(".pkg.tar.zst")]
        name = stem.rsplit("-", 3)[0]
        if name not in known:
            problems.append(
                f"{name}: liegt im Repository, aber kein Rezept unter "
                f"packaging/ bringt diesen Namen hervor. Es wurde aus "
                f"einem aelteren Baum gebaut, wird bei jedem Bau neu "
                f"signiert und landet auf dem Medium. Loeschen: "
                f"{package.name}")
    return problems


def _source_for(member: str) -> Path | None:
    """The tree file a package path was copied from, or None."""
    for prefix in sorted(SOURCE_OF, key=len, reverse=True):
        if member == prefix:
            return REPO / SOURCE_OF[prefix]
        if prefix.endswith("/") and member.startswith(prefix):
            return REPO / SOURCE_OF[prefix] / member[len(prefix):]
    return None


def _is_generated(member: str) -> bool:
    return any(member == p or member.startswith(p) for p in GENERATED)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _packages(repo_dir: Path) -> dict[str, Path]:
    found = {}
    for name in OWN_PACKAGES:
        matches = sorted(repo_dir.glob(f"{name}-[0-9]*.pkg.tar.zst"))
        # zepos-installer-gui-*.pkg.tar.zst also matches zepos-installer's
        # glob only if the version could start with a letter; it cannot,
        # but be explicit rather than rely on that.
        matches = [m for m in matches
                   if m.name[len(name) + 1:len(name) + 2].isdigit()]
        if len(matches) > 1:
            raise SystemExit(
                f"check-current.py: {len(matches)} builds of {name} in "
                f"{repo_dir} - remove the stale ones:\n  " +
                "\n  ".join(m.name for m in matches))
        if matches:
            found[name] = matches[0]
    return found


def check(repo_dir: Path = REPO_DIR) -> list[str]:
    """Every way the built repository differs from this tree."""
    problems: list[str] = []
    packages = _packages(repo_dir)

    missing = [n for n in OWN_PACKAGES if n not in packages]
    if missing:
        problems.append(
            "not built at all: " + ", ".join(missing))

    # Which source directories are shipped, for the backward pass. A
    # directory the package ships is a directory whose every file it is
    # expected to ship.
    shipped_dirs: dict[Path, set[str]] = {}

    for name, path in sorted(packages.items()):
        with tarfile.open(path, "r:zst") as archive:
            for entry in archive:
                if not entry.isfile():
                    continue
                member = entry.name
                if _is_generated(member):
                    continue
                source = _source_for(member)
                if source is None:
                    problems.append(
                        f"{name}: installs {member}, and nothing in this "
                        f"tree says where that comes from. Either the "
                        f"recipe grew a new destination, or "
                        f"check-current.py's SOURCE_OF has not been told "
                        f"about it.")
                    continue
                if not source.exists():
                    problems.append(
                        f"{name}: installs {member}, but "
                        f"{source.relative_to(REPO)} does not exist. The "
                        f"package was built before that file was renamed "
                        f"or deleted.")
                    continue
                extracted = archive.extractfile(entry)
                assert extracted is not None
                built = _digest(extracted.read())
                current = _digest(source.read_bytes())
                if built != current:
                    problems.append(
                        f"{name}: {member} differs from "
                        f"{source.relative_to(REPO)}. The package is "
                        f"older than the source it was built from.")
                shipped_dirs.setdefault(source.parent, set()).add(source.name)

    for directory, shipped in sorted(shipped_dirs.items()):
        if not directory.is_dir():
            continue
        # Which KINDS of file this directory is shipped from, read off
        # the package rather than declared here. src/ ships *.py and
        # *.sh and nothing else at its top level, so a README.md added
        # there is not a missing file - it is a file of a kind this
        # directory never ships, and demanding it would block builds
        # over documentation.
        kinds = {Path(name).suffix for name in shipped}
        for entry in sorted(directory.iterdir()):
            if not entry.is_file() or entry.name in shipped:
                continue
            if entry.name.startswith(".") or entry.suffix not in kinds:
                continue
            problems.append(
                f"{entry.relative_to(REPO)} exists but no package ships "
                f"it, although {directory.relative_to(REPO)}/ is a "
                f"directory the packages do ship {entry.suffix} files "
                f"from.")

    problems.extend(_meta_package_findings(repo_dir))
    problems.extend(_orphan_findings(repo_dir))

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo", type=Path, default=REPO_DIR,
        help="the built repository (default: packaging/out/x86_64)")
    parser.add_argument(
        "--quiet", action="store_true",
        help="say nothing when the repository is current")
    arguments = parser.parse_args()

    if sys.version_info < (3, 14):
        # tarfile learned "r:zst" in 3.14. On anything older every
        # package would raise CompressionError, and a guard that fails
        # for its own reasons teaches people to skip it.
        print(f"check-current.py needs Python 3.14 or newer to read "
              f"zstd packages; this is {sys.version.split()[0]}",
              file=sys.stderr)
        return 2

    if not arguments.repo.is_dir():
        print(f"check-current.py: no repository at {arguments.repo}",
              file=sys.stderr)
        return 2

    problems = check(arguments.repo)
    if not problems:
        if not arguments.quiet:
            print("the built packages match this tree")
        return 0

    print("The built packages do NOT match this tree:\n", file=sys.stderr)
    for problem in problems:
        print(f"  * {problem}", file=sys.stderr)
    # Die Namen kommen aus den Funden und nicht aus einer Liste hier.
    # Bis das Meta-Paket mitgeprueft wurde, nannte diese Zeile zwei feste
    # Rezepte - und wer ihr folgte, baute genau die zwei neu, an denen es
    # nicht lag.
    named = sorted({problem.split(":", 1)[0] for problem in problems
                    if ":" in problem} & _built_names())
    # Der Schnitt mit _built_names() und nicht die blosse Menge: ein
    # verwaistes Paket traegt seinen Namen im Fund, hat aber definitions-
    # gemaess kein Rezept mehr. Ohne den Schnitt riet diese Zeile am
    # 11.08.2026 zu `build.sh wlogout` - einem Rezept, das es nicht gibt,
    # gegen einen Fund, dessen Loesung Loeschen heisst. Dieselbe Falle
    # wie oben, eine Zeile weiter.
    # Nur drucken, wenn es wirklich etwas zu bauen gibt. Bei einem reinen
    # Waisen-Fund lautet die Loesung Loeschen, und ein Bauvorschlag
    # daneben schickt den Leser in die falsche Richtung - der Fund selbst
    # nennt die zu loeschende Datei beim Namen.
    if named:
        print("\nBuild them again before building an image from them:\n"
              f"\n    ./packaging/build.sh --key <id> {' '.join(named)}\n",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
