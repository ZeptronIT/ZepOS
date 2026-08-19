# ZepOS

ZepOS is an Arch-based Linux distribution with a Hyprland/Wayland desktop,
shipped as a bootable live medium with its own graphical installer. Everything
on the screen — installer, login screen, bar, dock, launcher, lock screen,
logout menu, settings — is written for this project, is GTK4, and takes its
colours, spacing and type scale from one file.

**Language note:** this README, the build scripts and the developer
documentation are English; source comments and the design documents in `docs/`
are largely German. The shipped user interface is English and German.

---

## Status: pre-release. Please read this part.

ZepOS boots, installs, and comes up as a working desktop. It is not yet
something you should put on a machine you care about, and these are the
specific reasons:

- **The packages are signed with a throwaway key.** Its user id is literally
  `ZepOS TEST KEY - DO NOT TRUST`, it has no passphrase, and it expires 90 days
  after it is generated. `packaging/publish.sh` refuses to publish a repository
  signed with it, and there is no override flag.
- **The update channel is built but not live.** Every installed system gets a
  `[zepos]` repository pointing at `https://zeptronit.github.io/ZepOS/$arch`.
  Nothing is published there yet, so the first `pacman -Syu` of an installed
  ZepOS reaches a 404. The self-update mechanism itself is finished and
  measured — it is the repository behind it that is missing.
- **Secure Boot does not work.** Measured: the boot chain carries no
  signatures, and firmware with Secure Boot enabled rejects the loader. You
  have to turn Secure Boot off.
- **A network connection is required to install.** The offline package source
  moves only the ZepOS packages onto the medium; the Arch base still comes over
  the network, so an installation without a network fails.
- **Hardware coverage is one machine plus QEMU.** There is no hardware matrix.
- **Two languages only:** German and English.
- **Two of ZepOS's own plugins patch upstream trees that have no licence.**
  See [Licence](#licence) — ZepOS has permission to build and patch them; you
  do not automatically inherit one. Their unmodified source is not part of
  this repository; the two recipes fetch it themselves, from the author's
  own repository, at a pinned commit.

What is proven, and where the evidence is: `iso/README.md` records what each
boot and each installation actually did, `packaging/README.md` records what has
to be true before a first real release, and
`docs/specs/2026-08-11-weg-zum-eigenen-os.md` is the roadmap that orders the
remaining work.

---

## Who this is for

- People who want a Hyprland desktop that is configured, coherent and
  installable, rather than assembled from a dotfiles repository over a weekend.
- People who want to read why a system is put together the way it is. Nearly
  every decision in this tree is written down next to the code, with the
  measurement it came from.

## Who this is not for

These are stated non-goals, not omissions:

- **Architectures other than x86_64.**
- **Migration of an existing installation.** ZepOS is installed, not converted.
- **Desktop choice.** There is one desktop, and it is Hyprland. That is the
  point of the project.
- **Anyone who needs Secure Boot, an offline install, or a signed update
  channel today.** See the status section.

---

## Trying it

### Download a medium

Pre-release images are on the
[releases page](https://github.com/ZeptronIT/ZepOS/releases). Verify the
checksum before writing it:

```bash
sha256sum -c zepos-<version>-x86_64.iso.sha256
```

Write it to a USB stick with the tool you already trust, boot with Secure Boot
disabled, and the medium starts the installer. There is no live desktop to try
first — the release medium boots into the installer and nothing else.

Two things to know before you download: a published image lags `main` by
however long it has been since the last one, and it is signed with the
throwaway key described above. Building the medium yourself is the only way to
get today's tree.

### Build a medium yourself

Both builds run in Docker containers, because a package built against whatever
happens to be on a workstation has a dependency list that describes that
workstation.

You need `git`, `gpg`, `rsync`, `repo-add` (from `pacman`), and Docker
reachable as **`sudo -n docker`** — the scripts never prompt for a password,
so passwordless sudo for `docker` has to be configured first. Budget roughly
10 GB of free disk for one release build: measured, a 3.5 GB archiso work
directory, a 1.3 GB image, and the build containers on top.

```bash
git clone https://github.com/ZeptronIT/ZepOS.git
cd ZepOS

# 1. A signing key. The real key is never in this repository, so for a local
#    build you make a throwaway one. It says DO NOT TRUST on purpose, has no
#    passphrase, and expires after 90 days. It prints the exact next command.
./packaging/make-test-key.sh

# 2. The packages and the pacman repository they are served from.
ZEPOS_GNUPGHOME=packaging/keys/gnupg ./packaging/build.sh --key <printed id>

# 3. The installation medium, out of exactly those packages.
./iso/build.sh --profile release
```

The image and its manifest land in `iso/out/` as
`zepos-<YYYY.MM.DD>-x86_64.iso` and `manifest-release.txt`. The build's last
line is the command that boots what it just made in QEMU:

```bash
./iso/test-boot.py --scenario release
```

Useful variations — every one of these is in the script's own `--help`:

```bash
./packaging/build.sh zepos-config        # one recipe instead of all of them
./packaging/build.sh --no-sign           # an unsigned repository
./packaging/build.sh --rebuild-image     # rebuild the build container too
./iso/build.sh                           # the smoke ISO (see below), not the medium
./iso/build.sh --snapshot current        # build against today's mirrors
```

Note that `--no-sign` silently drops `zepos-keyring` and `zepos-desktop` from a
full build: a keyring package built around no key, and a meta package that
depends on it, are not things that can exist.

**There are two ISO profiles and they are not interchangeable.** `iso/profile/`
is a test harness: it logs a user in, ships its own `/etc/shadow`, installs
unattended from an answer file with a root password in it, and puts
`console=ttyS0` on the kernel command line. `iso/profile-release/` is the image
a person can be handed. The shipping profile is assembled from an allow-list
(`iso/shared-with-release.txt`) rather than being a second copy, so that a new
file in the harness cannot reach a download by being forgotten.

---

## How it is put together

### The template system is the core

Nothing in a running ZepOS is a configuration file somebody edited. Two
single sources of truth — `src/icon_definition.py` for icons and
`src/style_definition.py` plus `src/brand.py` for colours, sizes and spacing —
feed a processor that expands `{{ICON_*}}` and `{{STYLE_*}}` placeholders into
82 templates in `src/templates/` and 8 stylesheet templates in `src/styles/`.
The result is the configuration Hyprland, AGS, kitty and the rest actually read.

```
icon_definition.py ─┐
brand.py ───────────┼─► template_processor.py ─► generate_config.sh ─► ~/.config/{hypr,ags,kitty,…}
style_definition.py ┘        (82 + 8 templates)      (zepos-generate)
user-settings.json ─┘
```

Two consequences follow, and both are load-bearing:

- **Generated files are never edited.** They carry a "DO NOT EDIT" header and
  are overwritten on the next run. The change goes into the template.
- **Generation is atomic.** Write into a temporary directory, validate, then
  move. A failed run leaves the previous working configuration untouched.

```bash
zepos-generate --all          # regenerate everything
zepos-generate --help         # every individual target
zepos-doctor                  # what a generated configuration cannot check itself
zepos-settings get            # every setting, with its current value
```

### The installer is three layers, and the interface never talks to archinstall

| Layer | Contents |
|---|---|
| `installer/core/` | Data model, validation, disk enumeration, LUKS2 encryption, wireless, translation to `archinstall` |
| `installer/gui/` | GTK4 / libadwaita wizard — nine pages: language, network, disk, partitioning, encryption, user, time, ZepOS, summary |
| `installer/tui/` | Text interface, used when the graphical session cannot start |

The interface fills a serializable configuration model; a translation layer
converts that into `archinstall`'s JSON format; a runner invokes its documented
command-line interface. So the two interfaces are interchangeable, and an
unattended installation needs no second code path — `InstallConfig.from_dict()`
plus `installer.core.runner.install()` is the whole of it.

Partitioning, bootloader and base installation are done by
[`archinstall`](https://github.com/archlinux/archinstall). Writing our own
partitioner would mean writing code whose bugs erase other people's disks.

`zepos-install` takes **no command-line arguments**. It picks a surface and
starts it; there is no `--config` flag on a tool that erases disks. Setting
`ZEPOS_INSTALLER_SURFACE=gui` or `=tui` forces one of them, and the fallback to
text always happens before any window is shown.

### Packages

`packaging/` holds 20 recipes producing 25 signed packages, built in dependency
order inside a container pinned to the same Arch Linux Archive snapshot as the
ISO. `zepos-desktop` is a meta package, and its `depends` list is where the
shape of an installed ZepOS is decided — the rule it follows is written at the
top of its PKGBUILD: *a dependency is a program the generated configuration
starts by itself, or one a default keybinding needs in order to do what the key
says.*

The private signing key never enters the build container. Packages are built
there; signing happens on the host afterwards.

### What you get on a fresh installation

`zepos-desktop` pulls in Hyprland with five plugins, the AGS bar and dock, the
ZepOS menu / lock / logout / settings programs, kitty as the terminal, and
`zepos-apps` — the selection of *other people's* applications ZepOS makes:
Firefox, Nautilus, Loupe, Papers, Celluloid, GNOME Text Editor, Calculator,
Baobab, File Roller, btop, CUPS. Each was chosen GTK4-first where a GTK4
version exists, and the reason is written next to the name in
`packaging/zepos-apps/PKGBUILD`.

Two optional groups are not installed by default: `zepos-apps-office`
(LibreOffice with German dictionaries) and `zepos-apps-devel` (`base-devel`,
`git`).

`zepos-apps` also includes **Claude Code**, packaged as `zepos-claude-code`
from a pinned, checksummed upstream tarball and pinned in the dock. It is
Anthropic's proprietary CLI under its own licence, not part of ZepOS's GPL, and
it needs an Anthropic account to do anything. Remove the package if you do not
want it.

### What is on the screen, and why we wrote it

| | Replaces | Why |
|---|---|---|
| `zepos-menu` | wofi | GTK3, and six generated call sites depend on the chooser |
| `zepos-logout` | wlogout | GTK3, upstream dead since 2024 |
| `zepos-lock` | hyprlock | Renders with GLES and Cairo, so its colours could never come from `brand.py` |
| AGS bar and dock | waybar, nwg-dock-hyprland | waybar is gtkmm-3; nwg-dock has no GTK4 version |
| `zepos-settings-gui` | nwg-displays | GTK3, and its "keep these settings?" timer dies with the program it is protecting |
| `hyprlaunch`, `hyprclipx` | — | Built from [azzuriel](https://github.com/azzuriel)'s plugins, patched by ZepOS; 116 lines of hardcoded CSS replaced by generated stylesheets. See [Licence](#licence) |

GTK4 throughout is a hard rule, not a preference: a GTK3 component is a
component whose colours and spacing cannot come from the same source as
everything else, which is the one property that makes a distribution look like
one system.

Two more surfaces exist that a user meets before the desktop does:

- **The login screen** is `greetd` running `regreet` inside `cage`, styled from
  the same `brand.py` and the same backdrop as the installer, with `tuigreet`
  on the console as a fallback if the graphical attempt fails twice. There is
  no autologin — it always asks. It follows the language the machine was
  installed in, with the honest caveat that `regreet` itself translates only
  two of the eight strings on the mask; the other six are English no matter
  what.
- **The boot splash** is a generated Plymouth theme (`zepos.script` and its
  images, derived from `brand.py` and the logo, checked in and re-derived by a
  test). It is enabled **only for encrypted installations**, where it is the
  disk passphrase prompt; on an unencrypted disk it would be decoration over an
  unmeasured path, so the installer does not turn it on. Enabling it rewrites
  `mkinitcpio.conf`, verifies the result, and rolls back on any doubt.

---

## Design decisions worth knowing

- **The desktop must start even when plugins fail.** Hyprland plugins are tied
  to an exact Hyprland version, so a minor version moving before the plugin
  packages are rebuilt produces a machine whose plugins cannot load. Everything
  needing a loaded plugin — the `plugin =` line, the plugin's settings block,
  every key binding whose dispatcher comes from a plugin — lives in one
  generated file. A block is written only when the compiled object is on the
  machine; otherwise its place is taken by a comment naming the object, the
  package that provides it and the command to re-run. With no plugins at all
  the file is nothing but comments, which is still a configuration that parses
  — measured with `Hyprland --verify-config` and asserted both ways by
  `tests/src/test_plugins.py`. A version mismatch costs a feature, not a
  session.
- **Wireless credentials are carried into the installed system.** Associating
  in the live environment does not give the installed system network access, so
  the connection profile is written explicitly. Otherwise a laptop with no
  ethernet port boots with no way to get online.
- **The repository an installation is performed with is not the one that
  remains.** An offline install reads its ZepOS packages from
  `file:///opt/zepos-repo` on the medium; the moment that medium is unplugged
  the path is gone. `installer/core/pacmanconf.py` removes every `[zepos]`
  section from the target's `pacman.conf` and appends exactly one pointing at
  the online repository — replacing rather than editing is what makes the
  result independent of how many were there.
- **Updates are narrow on purpose.** A daily timer, delayed after boot and
  randomly spread, updates only what comes from `[zepos]`. The Arch base is
  counted and reported, never touched, unless you set `update.scope=all`. An
  unattended `pacman -Syu` on a rolling release is a machine that one morning
  does not start. The updater also never regenerates configuration or restarts
  anything: it leaves a marker, and the next login regenerates before the
  compositor starts.
- **German and English are maintained as equals**, via gettext, in two domains
  — the installer and the desktop shell. English source strings are the msgids;
  the German catalogues are first-class. Tests assert that every string in the
  source has a catalogue entry and that every entry is translated, because a
  missing entry means a German user silently reads English.
- **Contrast is a correctness question, not taste.** `src/brand.py` holds
  ZeptronIT's six colours and all 103 colour keys derived from them. WCAG AA
  asks 4.5:1 for text and the brand's own accent does not reach it — `#0096C0`
  on `#0D3D47` is 3.45:1 — so the cyan that is *read* is that hue lightened to
  6.04:1, while the untouched `#0096C0` stays where it is *seen*. The tests
  recompute every pair rather than trusting the numbers written beside them.
  Green and red are deliberately **not** on brand: a distribution that
  recolours its failure states to the company's cyan is hiding failures in
  order to look tidy.
- **Shipping a brand is not imposing one.** Every one of those colours is
  reachable with `zepos-settings set colors.<key>`, and the style editor's
  first theme preset *is* the shipped palette rather than a copy of it.

---

## Development

### Requirements

Python 3.14, `archinstall` 4.4, GTK4 with libadwaita and PyGObject for the
graphical interfaces, `iwd` for wireless, `gettext` to compile the catalogues,
`docker` for the package and ISO builds.

### Tests

```bash
python -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

110 test files, 2931 tests, roughly seven minutes. The suite has an **isolation
guard**: no test may spawn a real process or write outside a temporary
directory. The installer drives `iwctl`, `archinstall` and NetworkManager, so
without that guard a careless test could drop your wireless connection or
overwrite your live network profiles. Tests that genuinely need an exception
opt in visibly with `@pytest.mark.allow_subprocess` or
`@pytest.mark.allow_system_writes`.

### Layout

```
src/            the desktop: templates, the two SSOTs, the generator, zepos-* commands
installer/      the installer, in three layers
packaging/      20 PKGBUILD recipes, the container, the signing and publishing scripts
iso/            two archiso profiles and the build that assembles them
lock/ logout/   zepos-lock and zepos-logout (C, GTK4, gtk4-layer-shell)
menu/ settings/ zepos-menu and zepos-settings-gui (Python, GTK4)
plugins/        LICENCE only - ZepOS's patches for hyprlaunch and hyprclipx
                live next to their recipes in packaging/, not here (see Licence)
po/             gettext catalogues: zepos-installer and zepos-desktop
tests/          110 test files and one isolation guard
docs/specs/     the design document and the roadmap (German)
```

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version: changes go into
templates, not into generated files; a claim in a commit message is expected to
name the thing that measured it; and `pytest` is expected to pass before a pull
request.

### Reporting a vulnerability

See [SECURITY.md](SECURITY.md). Do not open a public issue for a security
problem.

---

## Licence

GPL-3.0-or-later for ZepOS's own code. See [LICENSE](LICENSE).

ZepOS's desktop depends on five compositor plugins it does not itself hold
the copyright to. Their situations are not the same, and this table exists
so a reader can tell them apart without reading five PKGBUILDs:

| Plugin | Author | Origin | Licence | What ZepOS does with it |
|---|---|---|---|---|
| `hyprbars` | [hyprwm](https://github.com/hyprwm) (the Hyprland project) | [hyprwm/hyprland-plugins](https://github.com/hyprwm/hyprland-plugins), tag-pinned commit | BSD-3-Clause, real `LICENSE` file | Built unmodified; configured with ZepOS's own colours and icons at the config layer only |
| `borders-plus-plus` | [hyprwm](https://github.com/hyprwm) (the Hyprland project) | [hyprwm/hyprland-plugins](https://github.com/hyprwm/hyprland-plugins), tag-pinned commit | BSD-3-Clause, real `LICENSE` file | Built unmodified, loaded with no settings of its own |
| `hyprzones` | Jan Ohlmann ([azzuriel](https://github.com/azzuriel)) | [azzuriel/hyprzones](https://github.com/azzuriel/hyprzones), commit-pinned | **None** — GitHub reports `license: null`; no `LICENSE` file, no copyright notice anywhere in the tree | Built unmodified, no ZepOS changes |
| `hyprlaunch` | Jan Ohlmann ([azzuriel](https://github.com/azzuriel)) | [azzuriel/hyprlaunch](https://github.com/azzuriel/hyprlaunch), commit-pinned | **None** — same as above | Fetched and patched at build time (see below); the patch is ZepOS's own work |
| `hyprclipx` | Jan Ohlmann ([azzuriel](https://github.com/azzuriel)) | [azzuriel/hyprclipx](https://github.com/azzuriel/hyprclipx), commit-pinned | **None** — same as above | Fetched and patched at build time (see below); the patch is ZepOS's own work |

`hyprbars` and `borders-plus-plus` are unremarkable: a serious upstream, a
real licence, no ZepOS changes to the plugin code itself. The other three are
not, and the reason is the same for all three — measured 11.08.2026, at the
GitHub API and in each tree by hand: no `LICENSE` file, no `Copyright` line,
`"license": null`. Code with no licence is, under copyright law, "all rights
reserved" regardless of what a file header claims.

**What that means, and what ZepOS actually did about it.** Leon Marzoll
(ZeptronIT) — who has contributed to these same upstream trees, and so holds
copyright in his own contributions to them — gave ZepOS permission on
11.08.2026 to build from and modify all three. That permission is recorded
verbatim, with the exact commits, in [`plugins/LICENSE`](plugins/LICENSE). It
is a **permission, not a licence**: it says what *ZepOS* may do, and says
nothing about what *you*, installing ZepOS, may do with the code you receive.
A security review ahead of this repository's publication
(`.superpowers/sdd/2026-08-18-ags-schale-und-breitenleiter/
sicherheitsanalyse.md`, section 6) drew the sharper line this permission does
not cross: it does not cover ZepOS republishing a *copy* of the unlicensed
source itself. Building from it is one thing; redistributing it is another.

**So, as of 19.08.2026, this repository does not carry the source of
`hyprlaunch` or `hyprclipx` at all.** `packaging/zepos-hyprlaunch/PKGBUILD`
and `packaging/zepos-hyprclipx/PKGBUILD` fetch it themselves at build time,
from the author's own repository, pinned to the exact commit
[`plugins/LICENSE`](plugins/LICENSE) names — never a moving branch, so the
build stays reproducible — the same way an AUR package would. `hyprzones` was
never vendored in the first place and works the same way. ZepOS's own
modifications to `hyprlaunch` and `hyprclipx` — replacing hardcoded CSS and
window sizes with ZepOS's generated stylesheets, adding the clipboard
collector, fixing a path that reached under `$HOME` — are ZepOS's own diffs,
not copies of upstream code, and live as `packaging/zepos-hyprlaunch/
zepos-hyprlaunch.patch` and `packaging/zepos-hyprclipx/zepos-hyprclipx.patch`,
applied at build time and licensed GPL-3.0-or-later. The built, published
package is unaffected by any of this — the ISO still ships the finished
plugin — only the unmodified upstream *source* is no longer redistributed by
this repository.

All three recipes therefore declare `license=('custom')` rather than assert a
licence that does not exist. Closing the underlying gap needs one commit in
Jan Ohlmann's own repositories — a `LICENSE` file, once, and the question
never comes up again for anyone downstream of it — and it should be closed;
until it is, `plugins/LICENSE` is the honest account of where things stand.
