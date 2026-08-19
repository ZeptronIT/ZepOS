# Packaging

Spec §4.2 lists about fifteen packages. Thirteen recipes are here,
producing eighteen packages, and that is all of them.

| Recipe | Produces | Why this one |
|---|---|---|
| `zepos-config` | `zepos-config` | The core. Everything depends on it and nothing can be tested without it. |
| `zepos-keyring` | `zepos-keyring` | The package that makes `SigLevel = Required` mean something. Without it every signature in the repository is a signature from a key the machine has never been told to trust. |
| `zepos-installer` | `zepos-installer`, `zepos-installer-gui`, `zepos-installer-tui` | One source tree, three packages, so that the text interface §8.5 falls back to does not carry the toolkit whose absence it exists to survive. |
| `aylurs-gtk-shell` | `aylurs-gtk-shell` | Sixteen templates generate AGS widgets - including the session window and the dock's power button, both added 19.08.2026 when the standalone `zepos-logout` package was deleted - and AGS is in no Arch repository (spec §4.3), so until now not one of them had ever been executed by the program it is written for. |
| `astal` | `libastal-io`, `libastal-4`, `libastal-notifd` | Not optional. `ags run` bundles TypeScript whose first lines are `import Astal from "gi://Astal"`; without these typelibs AGS installs, starts and dies on the first import. |
| `zepos-lock` | `zepos-lock` | ZepOS's own lock screen, on GTK4 and `ext-session-lock-v1`. It replaced a packaged `hyprlock` on 12.08.2026: SUPER+L binds to it unconditionally, and `hyprlock` renders itself with GLES and Cairo (`objdump -p` names `libEGL`, `libGLESv2`, `libcairo` and no `gtk`), so its colours could never come from `brand.py`. The protocol reaches GTK4 through `gtk4-session-lock.h`, which ships in the same `gtk4-layer-shell` `aylurs-gtk-shell` already needs. |
| `zepos-hyprland` | `zepos-hyprland` | Hyprland 0.56.1 (§4.3). Five packages are compiled against its headers, so it cannot be a package somebody else's release schedule moves. The longest build in the project by a wide margin. |
| `zepos-hyprlaunch` | `zepos-hyprlaunch` | ZepOS's own launcher plugin, and the one whose absence §7.4 works hardest to survive: SUPER+SPACE. |
| `zepos-hyprclipx` | `zepos-hyprclipx` | ZepOS's own clipboard plugin. |
| `zepos-hyprzones` | `zepos-hyprzones` | ZepOS's own zone-tiling plugin. |
| `hyprland-plugins` | `zepos-hyprbars`, `zepos-borders-plus-plus` | The two plugins from hyprwm (§7.1). One upstream tree, two packages - `hyprland-plugins` is not a third package, and §4.3 corrected itself on exactly that. |
| `zepos-menu` | `zepos-menu` | The GTK4 selection window: the application launcher SUPER+SPACE falls back to, and the dmenu five generated helper scripts choose with. It replaced wofi on 11.08.2026 - wofi is GTK3 (`objdump -p /usr/bin/wofi \| grep NEEDED` -> `libgtk-3.so.0`) and the pinned snapshot has no GTK4 equivalent among its 14860 packages. |
| `zepos-desktop` | `zepos-desktop` | The meta package. `installer/core/translate.py` hands archinstall this one name and nothing else, so this recipe is the shape of an installed ZepOS. |

`hyprland-qtutils` is **not** here, and that is the second correction to
§4.3 rather than an omission - see below.

```bash
./packaging/make-test-key.sh                       # once, if you have no key
ZEPOS_GNUPGHOME=packaging/keys/gnupg \
  ./packaging/build.sh --key <fingerprint>         # ~15 minutes, most of it Hyprland
./packaging/verify-install.sh                      # installs into three clean containers
./packaging/publish.sh                             # check and stage what Pages would serve
./packaging/serve-repo.sh                          # serve that, locally, to test an upgrade
```

`build.sh` builds in a container, signs on the host, and leaves a pacman
repository in `packaging/out/`. Nothing it writes is tracked by git.

## The decisions

### The version comes from `VERSION`

One file at the repository root. Each `zepos-*` recipe reads it relative
to its own location:

```bash
_zepos_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
pkgver="$(<"$_zepos_repo/VERSION")"
```

so `makepkg` run by hand in the recipe directory and `packaging/build.sh`
run from the repository root produce the same number. A version repeated
in fifteen recipes is wrong in some of them by the second release, and
nothing would say which.

Packaged upstreams keep the upstream version — `aylurs-gtk-shell` is
3.1.2 because that is what it is and `zepos-hyprland` is 0.56.1, and a
ZepOS number over the top of either would hide which release is
installed. The three plugin repositories have no tags at all,
so they carry the version their own `CMakeLists.txt` declares plus the
commit, in the convention `packaging/astal` already uses:
`0.3.2.r87.73171c7`.

### `zepos-keyring` is the key, and the key is supplied

Every package in `packaging/out/` is signed and every `[zepos]` section
says `SigLevel = Required`. Neither statement means anything on a machine
whose pacman keyring has never been told about the key: pacman rejects a
signature from a key it merely *has*. `zepos-keyring` is what closes
that, and it is three files —

```
/usr/share/pacman/keyrings/zepos.gpg      imported by pacman-key --populate
/usr/share/pacman/keyrings/zepos-trusted  every fingerprint in it is LOCALLY SIGNED
zepos-keyring.install                     runs --populate on the target
```

— of which the middle one is the half that is easy to miss. Read out of
`/usr/bin/pacman-key` rather than guessed: `populate_keyring()` imports
`<name>.gpg`, then reads `<name>-trusted` as a gpg ownertrust dump
(`<40 hex digits>:4:`, one per line, exactly like
`/usr/share/pacman/keyrings/archlinux-trusted` and its five master keys)
and `--lsign-key`s each fingerprint in it. Ship only the `.gpg` and the
key is imported and still refused.

**Where the key comes from.** `build.sh` exports the public half of the
key it is about to sign with into `packaging/zepos-keyring/` *before* the
build container starts, and the same file is what lands next to the
repository as `zepos-repo.pub`. So the keyring package, the signatures
and the key `iso/build.sh` trusts in its build container are one key by
construction; there is no second place to update. The private half still
never leaves the host — the container gets the public half and nothing
else.

**What happens today.** The key is the one `make-test-key.sh` produces:
`ZepOS TEST KEY - DO NOT TRUST`, ed25519, no passphrase, ninety days.
The recipe notices — it reads the uid out of the key file — and the
package says so where `pacman -Qi` shows it:

```
Description : ZepOS repository key - TEST KEY, NOT A RELEASE KEY
              (ZepOS TEST KEY - DO NOT TRUST <test-key@zepos.invalid>)
```

It is not refused, because refusing would mean the whole signing and
trusting path could never be executed before the day it has to work.
`packaging/keys/` and `packaging/*/*.pub` are both gitignored, which is
why the public half is not committed either: a public key is harmless,
but a *keyring package built around a key whose private half sits in
somebody's working tree* is a distribution that trusts that working tree.
When there is a release key, its public half is a file to commit in
`packaging/zepos-keyring/` and the export becomes the check rather than
the source.

**How it is measured.** `verify-install.sh` sets the container up by
hand, as it always did, then takes it back out again: `pacman-key
--delete`, and the machine refuses the repository outright; `pacman-key
--populate zepos`, which is the only thing the scriptlet does, and it
accepts both the package signatures and the database signature again. A
keyring package tested on a machine that was already told about the key
proves nothing at all.

The scriptlet is guarded with `pacman-key -l`, which is what
`archlinux-keyring` does, and the guard is not decoration here: two of
the roots this package is installed into have no keyring at the time.
`mkarchiso` runs `pacstrap -G`, and `archinstall` pacstraps the target
before `pacman-key --init` has run there. Population then happens on the
next upgrade, once there is a keyring to populate. The smoke ISO
installs `zepos-keyring` for exactly this reason — it is the only place
that scriptlet can be executed under the conditions it was written for,
and if the guard were wrong the image build would stop.

### The installer is three packages so that the fallback is a fallback

`packaging/zepos-installer` is `packaging/astal`'s shape with astal's
answer: one source tree, three packages, one of which the other two
depend on. What makes it worth doing rather than shipping one package is
spec §8.5. The text interface exists for the machine whose graphical
session did not start; a text interface that pulls GTK4, libadwaita and
PyGObject in behind it is the same dependency under a second name, and
nobody would notice, because a machine that *can* run GTK4 never
exercises the fallback.

So `zepos-installer-tui` depends on `zepos-installer` and on nothing
else, `zepos-installer-gui` is the only one of the three that names a
toolkit, and `verify-install.sh` measures it rather than asserting it: a
container with `zepos-installer` and `zepos-installer-tui` on it, no
`gtk4`, no `gtk3`, no `libadwaita`, no `python-gobject`, and
`/usr/bin/zepos-install` run with `env -i`. It reaches
`installer.core.firmware`, finds no `/sys/firmware/efi`, and refuses in
German with exit 1 — which is a longer statement than it looks: the
command found `/usr/share/zepos-installer`, imported `installer.core` and
`installer.tui`, and loaded the catalogue the same package installed.

Three smaller decisions inside it:

- **`/usr/share/zepos-installer`, not `site-packages`.** `installer` is a
  top-level name `python-installer` already owns there, and two packages
  claiming `.../site-packages/installer/__init__.py` is a pacman file
  conflict rather than a shadowing problem. `installer/bin/zepos-install`
  therefore resolves its root before its first import, in the four lines
  `src/cli.py` describes for `zepos-generate` and for the same reason.
- **The catalogue is compiled, not committed.** `po/build.sh` is the same
  script a checkout runs; its header already said the PKGBUILD would call
  it. A `.mo` in git is a build artefact nobody notices going stale
  against the `.po` beside it.
- **`archinstall` is a hard dependency and the version is checked.** The
  pinned snapshot carries `archinstall 4.4-1`, which is the release
  `installer/core/translate.py` and `installer/core/runner.py` were read
  against — the config keys, the `Size`/`Unit` types, the spelling of
  `--mountpoint`. `verify-install.sh` fails if the snapshot ever moves off
  it, because a different archinstall is not a broken import: it is a
  configuration that is accepted and read differently.

None of the three is in `zepos-desktop`. Spec §4.2 puts them in the ISO
and nowhere else, and the third container of `verify-install.sh` installs
`zepos-desktop` on a machine where nobody has touched them and checks
that `zepos-installer`, `-gui`, `-tui` and `archinstall` are all absent
afterwards.

### `zepos-desktop` is a decision, not a transcription

`installer/core/translate.py` hands archinstall exactly one package name,
so this recipe *is* the installed system. §4.2's table names seven things;
the list has forty-four, and the rule that produced it is written at the
top of the recipe:

> A dependency is a program the generated configuration starts by itself,
> or one a default keybinding needs in order to do what the key says.
> Everything else is an optdepend or is absent.

That rule comes from §7.4 rather than from taste. `src/plugins.py` can
drop a plugin block when the object is missing; nothing does the
equivalent for `bind = $mainMod, L, exec, zepos-lock`. A key that silently
does nothing is the worst outcome this project can produce, because
nothing reports it — so every program a shipped bind names is in the
list, including `slurp`, `satty` and `wf-recorder`, which are one
screenshot bind and one recording bind between them. `bind = $mainMod, M,
exec, zepos-logout` used to be the same kind of example until 19.08.2026:
SUPER+M now runs `ags request logout` (a window inside the already-listed
`aylurs-gtk-shell`), so the standalone package this list once had to name
for it is gone.

Applied the other way it is just as sharp. `thunar`, `firefox` and
`blueman` appear in the templates too — a notification colour, a
windowrule, a button on the disk widget, a bar module's on-click — but ZepOS
did not put those on the screen and loses nothing it drew without them.
They are `optdepends`. A meta package that installs a browser has decided
which browser the distribution has, and no line of the spec does that.

Also deliberately absent, and each for its own reason:

| Not here | Why |
|---|---|
| `zepos-installer`, `-gui`, `-tui` | §4.2: the ISO, not the installed system. They would bring `archinstall` and `iwd` with them, and a machine that offers to reinstall itself from its own menu. |
| `linux`, `linux-firmware`, `base`, `mkinitcpio`, a bootloader | archinstall installs the base system and knows what this machine needs. A desktop package that owns the kernel cannot be installed next to `linux-lts`. |
| `mesa` and anything GPU-shaped | Hardware, decided per machine. `zepos-hyprland` depends on it anyway, so naming it here would only be a second place for it to be wrong. |
| an autologin | Hier stand „a display manager: There is none. A session starts through `start-hyprland` from a tty." Das stimmte für das Rauchbild, das sich per `agetty --autologin` selbst anmeldet, und für das installierte System stimmte es nicht: dort meldete sich niemand an, und `iso/test-boot.py --scenario release-installed` blieb bei „Reached target Graphical Interface" stehen. Es gibt jetzt einen Anmeldedienst — `greetd` mit `greetd-regreet` und `greetd-tuigreet` als Rückfall. Was weiterhin fehlt, ist der Autologin: auf einer Maschine, die jemandem gehört, wird gefragt. |
| `grub`, `efibootmgr` | Gemessen an archinstall 4.4: `_add_grub_bootloader()` ruft `self.pacman.strap('grub')` und, unter UEFI, `self.pacman.strap('efibootmgr')` selbst auf. Ein zweiter Ort für dieselbe Abhängigkeit wäre ein zweiter Ort, an dem sie falsch sein kann. |

One entry is easy to leave out and worst to leave out: `zepos-keyring`.
`installer/core/source.py` writes a `[zepos]` section with
`SigLevel = Required` into the installed `pacman.conf`, so a machine
without the keyring fails its first `pacman -Syu` on a key it was never
given, and the fix is a manual import the user has no way to know about.

### `hyprland-qtutils` stopped being missing

§4.3 lists it among the five components that are only in the AUR. That
was true when it was written and is not true at the pinned snapshot, and
packaging it now would be actively wrong rather than redundant:

- upstream renamed the project `hyprland-guiutils` — same programs,
  `hyprland-dialog`, `hyprland-donate-screen`, `hyprland-update-screen`;
- Arch carries `hyprland-guiutils 0.2.2-2` in `extra`, with
  `replaces = hyprland-qtutils`;
- `zepos-hyprland` already depends on it, because Hyprland 0.56.1 does —
  it is a hard `depends` of Arch's own `hyprland` at this snapshot;
- it is already in the smoke image, and has been since the compositor
  package existed.

A `zepos-hyprland-qtutils` would therefore be a second package installing
`/usr/bin/hyprland-dialog`, which is a file conflict, next to a package
that declares it obsolete. `tests/packaging/test_recipes.py` asserts the
recipe stays absent and that `zepos-hyprland` keeps the dependency, so
the next reader of §4.3 finds the answer rather than the table.

That left the logout menu as the one genuinely missing component, and
it was genuinely missing: nothing in `core` or `extra` at the snapshot is
called `wlogout` or provides it. ZepOS packaged upstream's until
11.08.2026 and then built its own, `zepos-logout`, from `logout/` in this
tree — the decision that day was that the surface is GTK4 throughout, and
`wlogout` measured `NEEDED libgtk-3.so.0` with `gtk+-wayland-3.0` in its
`meson.build` and no mention of GTK4 anywhere in the tree.

Its trap came along with it. Upstream made `gtk-layer-shell` an
*optional* build dependency, so a build without it produced a `wlogout`
that accepted `--protocol layer-shell`, printed "Falling back to xdg
protocol", and became an ordinary window the compositor places and
focuses. Nothing failed. `logout/meson.build` made the GTK4 equivalent
`required`, so that build stopped instead; the recipe asked
`readelf -d` afterwards whether the binary really linked against it, and
`verify-install.sh` asked the installed file the same question. Both also
asked whether `libgtk-3` came in through a side door, because a program
that loads both toolkits answers the GTK4 question with yes.

`zepos-logout` itself is gone as of 19.08.2026: SUPER+M now opens a
window inside the already-running AGS process (`ags request logout`,
see `src/templates/ags-logout.template`) instead of starting a separate
binary, so there is no second GTK4 toolkit left in this list to build,
sign or verify a linkage for. `logout/`, `packaging/zepos-logout/` and
the recipe row above are deleted with it, not archived.

### The plugin ABI is a fact about the headers, not about the version

This is the decision the five plugin packages exist around, and reading
Hyprland's own check is the shortest way to see why it had to be made.
`src/plugins/PluginSystem.cpp` dlopens the object, calls its
`pluginAPIVersion()` and compares the answer against
`HYPRLAND_API_VERSION`. That macro, in `src/plugins/PluginAPI.hpp`, is:

```cpp
#define HYPRLAND_API_VERSION "0.1"
```

A literal string. Every plugin ever compiled against any 0.x Hyprland
passes it, and there is no second check — the compositor then calls
`pluginInit`.

What actually has to match is the header set. A plugin is C++ compiled
against `CCompositor`, `CWindow`, `CMonitor` and about two hundred more,
so it carries their struct layouts, vtable orders and inline bodies
inside itself. Rebuild Hyprland against a newer aquamarine and those
change shape; the plugin still answers `"0.1"`, still loads, and then
reads the wrong offsets. There is no error message for that anywhere.

Upstream does compute a string describing exactly this — the `abiHash`
of `hyprctl version -j`, produced by `__hyprland_api_get_hash()`:

```
<commit>_aq_<major.minor>_hu_<...>_hg_<...>_hc_<...>_hlg_<...>
```

but nothing consumes it except `hyprpm`, which spec §7.2 rejects. So the
packages carry it:

- `zepos-hyprland` assembles the string from the pinned release commit
  and `pkg-config --modversion` of the five libraries, publishes it as
  `provides=("hyprland-plugin-abi=<string>")`, and writes it to
  `/usr/lib/hyprland/plugin-abi` — next to the directory the objects go
  in. `package()` then rebuilds the same string out of the `version.h`
  that is being **shipped** and fails the build if the two disagree, so
  the published ABI cannot be a different compositor's.
- each plugin recipe reads that file when it is sourced and declares
  `hyprland-plugin-abi=<string>` among its `depends`, next to the
  `zepos-hyprland>=0.56.1` and `<0.57.0` of spec §7.3.

Both are needed and neither is enough alone. The range is what lets a
patch update through and stops a minor jump; the token is what notices a
**rebuild**, because 0.56.1 compiled against aquamarine 0.15 is still
0.56.1 and satisfies the range. `packaging/verify-install.sh` measures
all of it, including the sharp case: `extra` at this snapshot has
`hyprland 0.56.1-3` — the same upstream release, from the same commit,
inside the range — and pacman still refuses to put a plugin next to it,
because the range names `zepos-hyprland` and nothing but `zepos-hyprland`
publishes the token.

The token has to be assembled at the top of each recipe rather than in
`package()`, and that is makepkg's rule and not a preference:
`lint_provides` extracts the array out of the package functions too and
evaluates it with nothing set, so a token computed there is linted as an
empty version and the build stops with *"pkgver in provides is not
allowed to be empty"*. Measured. What the package functions do instead is
read the file a second time and refuse to package if it has changed since
the compile.

A plugin recipe built without `zepos-hyprland` installed falls back to
`hyprland-plugin-abi=zepos.hyprland.absent`, which no package provides,
so `makepkg --syncdeps` stops with a message naming the missing
compositor rather than guessing an ABI.

### Every plugin object goes to exactly one path

`/usr/lib/hyprland/plugins/<name>.so`, defined once in `src/plugins.py`
and written into spec §4.2. `src/plugins.py` keeps a plugin's whole
configuration block — the load line, the `plugin { }` settings and the
binds on its dispatchers — only when that exact file exists, so a package
that installs one directory away produces a desktop with no plugins, no
error and nothing in any log. Every plugin recipe therefore asserts the
path in its own `package()`, and `verify-install.sh` asks the module
itself rather than repeating the directory.

Two of the packages ship a second file, and it is not a slip. `hyprlaunch`
and `hyprclipx` are deliberately split: the plugin links no GTK at all
and starts its window as a separate layer-shell process with
`execlp("hyprlaunch-ui", ...)`. Without `/usr/bin/hyprlaunch-ui` the bind
loads a plugin, registers a dispatcher, forks and fails — and §7.4 went
to some length to make sure SUPER+SPACE is never a dead key.

### The Arch snapshot comes from `iso/profile/pacman.conf`

Also one place, and not a new one. The build container installs from the
same Arch Linux Archive snapshot the image does, because here the tool
and the material are the same packages: `libastal-4` links against the
GTK4 that is present while it builds and then has to run against the GTK4
in the image. `packaging/Dockerfile` takes the date as a build argument
and `build.sh` reads it out of the ISO profile.

This is a different line from the one `iso/Dockerfile` draws, and
deliberately: there, the tool (archiso) is current and only the material
is pinned.

### Signing: the key is supplied, never stored

`build.sh` takes a key id (`--key`, or `ZEPOS_SIGNING_KEY`) and
optionally a keyring (`ZEPOS_GNUPGHOME`). It knows nothing else about
either. On a release machine that is the maintainer's own keyring; here
it is `packaging/keys/gnupg`, which `make-test-key.sh` creates and
`.gitignore` excludes in full — a private key in a clone is a private key
in every clone, and a test key is still a private key. The test key says
`ZepOS TEST KEY - DO NOT TRUST` in its user id and expires in ninety
days.

Two consequences that are not obvious:

- **The signing key never enters the build container.** A build container
  runs `build()` functions out of upstream tarballs; a key mounted into
  it is a key every future upstream release can read. The container
  produces packages, the host signs them afterwards.
- **`pacstrap` verifies against the keyring of the machine it runs on**,
  not one inside the image being built — `mkarchiso` passes `-G`, and
  pacman does not prefix its `gpgdir` with `--root`. So `iso/build.sh`
  runs `pacman-key --init && --add && --lsign-key` in the build container
  before `mkarchiso`. Those are the same three commands `zepos-keyring`
  will run on an installed system, which is why they were worth getting
  right rather than working around.

Building without a key is possible (`--no-sign`) and never accidental:
`build.sh` refuses to sign with nothing and `iso/build.sh` prints a
paragraph to stderr and relaxes `SigLevel` in its working copy, so an
unsigned image cannot be produced silently. Spec §8.6 is the reason for
all of it: a repository that starts unsigned makes every
already-installed system import a key by hand on the day it stops being
unsigned.

### The repository layout was already decided

`installer/core/source.py` names it, so this build had to match rather
than choose:

```
packaging/out/                      <- the shape GitHub Pages serves
├── zepos-repo.pub                     the public key zepos-keyring will ship
├── manifest.txt
└── x86_64/                         <- ONLINE_REPO_URL ends in $arch
    ├── zepos.db -> zepos.db.tar.gz
    ├── zepos.files -> zepos.files.tar.gz
    ├── *.pkg.tar.zst
    └── *.pkg.tar.zst.sig
```

(The **shape**, not the bytes: `packaging/publish.sh` stages this into
`packaging/out/pages/` before anything is published, because two of the
entries above are symlinks and a static host does not resolve one. See
*Publishing*, below.)

`ONLINE_REPO_URL = "https://zeptronit.github.io/ZepOS/$arch"` ends in
`$arch`, so what is published is the directory **above** the architecture
directory. `OFFLINE_REPO_URL = "file:///opt/zepos-repo"` does not, so the
ISO copies the **contents** of `x86_64/` into `/opt/zepos-repo`. One
build, both layouts, no second copy of anything. `iso/build.sh` does that
now — into the working profile, not the committed one, since everything
under `packaging/out/` is a build artefact.

The online half is still nothing but a URL: no ZepOS package has ever
been published to `zeptronit.github.io`. That matters for one thing in
particular, and `installer/core/pacmanconf.py` says so in its own
header — after an installation the target's `pacman.conf` points **at
that URL** (spec §8.5b), because the offline one it was installed from
is a directory of a medium that has been unplugged. Until somebody
publishes, the first `pacman -Syu` of an installed ZepOS reaches a 404
rather than a missing path. That is the correct failure of the two.

It used to be more than that. `installer/core/source.py::probe()` chose
between the two URLs by opening a socket to `archlinux.org`, so every
machine with a working network was pointed at the unpublished one *during
the installation* — and `pacman -Syy` 404'd before a single package was
installed, on a disk that had already been erased. `probe()` now sends a
`HEAD` to `$ONLINE_REPO_URL/zepos.db` and falls back to the medium's own
repository when that is not there, which is why the paragraph above is
about the first upgrade rather than about the installation.
`iso/README.md`'s *"The package source now asks the repository"* has the
measurement.

The one thing publishing changes on its own, with no code to touch:
`probe()` starts answering `ONLINE`, and installations from then on take
their ZepOS packages over the network.

## Publishing

`packaging/publish.sh` is the whole of it, and it does not push.

```bash
./packaging/publish.sh              # check everything, stage into packaging/out/pages
./packaging/publish.sh --commit     # and commit that onto the local gh-pages branch
git push --force origin gh-pages    # a human, having read the above
```

It was written after the earlier conclusion — *"publishing is a human's
job and there is no workflow"* — was revisited, and that conclusion turns
out to have been half right. Automating the **build** in CI is still not
possible: it needs Docker with `--network host` (spec §10.1) and it needs
the release private key, and deciding where that key lives on a runner is
a decision about custody rather than about packaging. But the **publish**
is not the build. It is a check and a copy, it takes seconds, and it had
been described as "one `rsync`" for long enough that it was worth finding
out whether that was true.

It is not, and the three differences are the reason this is a script:

| | why a copy of `packaging/out/` would not work |
|---|---|
| symlinks | `repo-add` writes `zepos.db` as a symlink to `zepos.db.tar.gz`. Git stores it faithfully and a static host does not resolve it, so pacman fetches nineteen bytes of path and reports a corrupted database. Published as regular files. |
| Jekyll | Without a `.nojekyll` at the root, Pages runs the tree through Jekyll, which drops every path beginning with `_` or `.` and can fail a deploy over a file it does not understand. |
| `*.old` | `repo-add` keeps the previous database next to the new one. It is a backup of a build artefact, no pacman asks for it, and the branch would carry it forever. |

### What is checked before anything is staged

Each of these is a failure that is otherwise discovered by a user's
machine and nowhere earlier:

- **the build is signed at all.** No `zepos-repo.pub` means `--no-sign`,
  and every installed ZepOS carries `SigLevel = Required` for `[zepos]`.
  An unsigned repository at that URL is not a degraded service; it is a
  repository every installed machine refuses.
- **the database is signed.** `Required` covers the database before it
  covers a package.
- **every package has a `.sig`.**
- **every signature verifies against the key that is published next to
  it** — in a temporary keyring built out of `zepos-repo.pub` alone.
  Verifying against the developer's own keyring answers a different
  question and passes on the one machine where the answer does not
  matter. It is `--status-fd` and `GOODSIG` rather than gpg's exit code,
  because gpg exits 0 for a good signature from an untrusted key, and a
  keyring created a line earlier holds nothing else.
- **the database describes the directory.** A build interrupted between
  `makepkg` and `repo-add` produces a database and a directory that
  disagree, and neither half says so.
- **no file over 100 MB** (git rejects the blob outright) and **no site
  over 1 GB** (Pages' limit). `zepos-hyprland` is 51 MB, so the first one
  is not hypothetical.

### `gh-pages`, one orphan commit, and what that costs

The three options were a `docs/` directory on the source branch, a
`gh-pages` branch, and a GitHub Actions workflow using
`deploy-pages`.

`docs/` was rejected first: it puts 57 MB of package tarballs into the
history of the branch everybody clones, on every release, forever. An
Action was rejected second, and not because Actions are unavailable — the
artefact it would deploy has to come from somewhere, and the build cannot
run there. A workflow whose input is a human uploading a 57 MB artefact
is not simpler than a human pushing a branch; it is the same act with
more moving parts and a second place for the key question to be asked.

So: **`gh-pages`, and every publish is a commit with no parent.**

That is the decision worth writing down, because git keeps every version
of every blob forever and a repository of package tarballs is the worst
possible thing to accumulate. With ordinary history the branch would grow
by the size of the whole repository on every release and never shrink.
With an orphan commit the branch is exactly one commit at all times, last
release's blobs are unreachable the moment a new one is written, and
`git clone` of the default branch never sees any of it.

The costs, all three of them:

- **the push is forced.** There is no shared history to fast-forward.
  `publish.sh` prints `git push --force origin gh-pages` and does not run
  it.
- **there is no record of what was published last week.** Which is why
  `manifest.txt` — the source commit, the Arch snapshot and the sha256 of
  every package — is published *with* the packages rather than left in a
  branch history that no longer exists.
- **the remote keeps the unreachable objects for a while.** GitHub garbage
  collects on its own schedule; a `gh-pages` that has been rewritten a
  dozen times is not immediately a dozen times smaller on their disk. It
  is bounded and it is not in anybody's clone.

Pages then needs configuring once, by hand: *Settings → Pages → Deploy
from a branch → `gh-pages` / (root)*.

### Key custody: what has to be true before the first publish

Today there is one key and its user id is
`ZepOS TEST KEY - DO NOT TRUST`. **`publish.sh` refuses to commit a tree
signed by it, and there is no flag that says otherwise** —
`tests/packaging/test_publish.py` reads the argument parser and fails if
one appears. Staging it locally is allowed and is what the update
measurement below runs against; the staged tree then carries a file
called `TEST-KEY-DO-NOT-PUBLISH`, which is what the commit step reads.

The reason for the asymmetry is that a repository signed with a throwaway
key is **worse than an unsigned one**. Unsigned fails loudly on every
machine that asks for a signature. Signed-with-a-throwaway succeeds — and
the private half is in a working directory, in whatever backup that
directory reached, and in every clone that ever had it.

Before there can be a first real publish:

1. **A release key exists and its private half has never been in this
   repository.** `packaging/keys/` is gitignored in full and stays that
   way. `build.sh` takes `--key` and `ZEPOS_GNUPGHOME` and knows nothing
   else about either, so a key on a smartcard or in a separate keyring
   needs no change here.
2. **It has no expiry that will pass unnoticed**, or a documented
   renewal. The test key expires in ninety days on purpose; a release key
   that expires silently makes every installed machine fail its next
   upgrade with an error about a signature rather than about a date.
3. **A revocation certificate exists and is stored away from the key.**
   `gpg --gen-revoke` at creation time. There is no `zepos-revoked` file
   in `zepos-keyring` today because there is nothing to record; the day
   there is, that is where it goes.
4. **Its public half is committed** to `packaging/zepos-keyring/`. The
   `.gitignore` entry `packaging/*/*.pub` exists because today's export is
   the throwaway key; with a release key the committed file becomes the
   source and `build.sh`'s export becomes the check against it.
5. **`packaging/build.sh --key <release key>` has been run**, so that the
   signatures, `zepos-keyring` and `zepos-repo.pub` all describe that one
   key — which they do by construction, since `build.sh` exports the
   public half before the build container starts.
6. **`./packaging/publish.sh` runs clean**, which is now a single command
   that checks all of the above except the custody itself.
7. **The update path has been measured against that build** with
   `./iso/test-boot.py --scenario update`, below.

And one thing that is *not* on the list, deliberately: publishing does
not have to wait for a release key in order to be **tested**. That is the
whole point of the next section.

### How to make that key

The list above says what must be true. This says how, because "generate a
GPG key" is the easy part and the shape of it is the part that decides
what happens on a bad day.

**One key that both certifies and signs is the wrong shape.** Make a
primary key that only ever certifies, and a signing subkey that does the
daily work:

**Run these at a terminal, not from a script.** Every step that touches
a secret key opens a pinentry prompt — on a desktop that is a window, and
it is the reason this cannot be automated here. Measured against GnuPG
2.4.9: the two generate steps below ran exactly as written; the export
and delete steps below them each stopped for a prompt.

```bash
export GNUPGHOME=/some/directory/not/in/this/repository

# Primary: certify only, no expiry. This one is the identity.
# It asks for a passphrase. Give it one - see the export step for why.
gpg --quick-generate-key "ZepOS <zepos@zeptronit.example>" ed25519 cert never

FPR=$(gpg --list-keys --with-colons | awk -F: '/^fpr:/ {print $10; exit}')

# The subkey that signs packages. One year, renewable.
gpg --quick-add-key "$FPR" ed25519 sign 1y
```

That produces exactly the shape this section is about, and `--list-keys`
is worth reading once to see it:

```
sec   ed25519/B0E54487 [C]                      <- certifies, nothing else
ssb   ed25519/7B50074D [S] [expires: 2027-…]    <- signs packages
```

GnuPG 2.4 writes a revocation certificate by itself, into
`$GNUPGHOME/openpgp-revocs.d/<FPR>.rev`, and says so. That file is the
one requirement 3 above is about — **move it somewhere else now**, before
it is backed up together with the key it revokes. `gpg --gen-revoke` also
exists if a second one with your own reason text is wanted.

Then take the primary out of daily reach. This is the step that is worth
the trouble:

```bash
gpg --export-secret-keys --armor "$FPR" > primary-FULL-BACKUP.asc  # goes offline
gpg --export-secret-subkeys --armor "$FPR" > subkeys.asc
gpg --delete-secret-keys "$FPR"
gpg --import subkeys.asc
gpg --list-secret-keys   # the primary now shows sec#  - the # is the point
```

`sec#` means the private half of the primary is not there. The build
machine can sign packages and cannot certify anything, which is exactly
the authority it needs and no more.

**Why this shape.** The difference shows up on the day something leaks.
A compromised *subkey* is revoked, replaced, and the fix reaches users as
a `zepos-keyring` update under the same identity they already trust. A
compromised *primary* means starting over: a new identity, and every
installed machine has to be told about it through a channel it has no
reason to believe. The two cases cost a package update and a public
apology respectively.

**Where the primary lives.** Encrypted storage that is not the build
machine, or a smartcard. On a YubiKey (`gpg --edit-key` → `keytocard`)
the private half never exists as a file at all: it can be used and not
copied. For a distribution handed to strangers that is the honest answer,
and `build.sh` needs no change for it — it takes `--key` and
`ZEPOS_GNUPGHOME` and does not care where the secret actually is.

**The expiry is a dead-man switch, not bureaucracy.** A subkey that
expires in a year stops being usable if the key is lost, instead of
staying valid forever. The cost is that `zepos-keyring` has to be
maintained: an expired key with no update path does not fail politely, it
stops every installed machine from updating. That is the trade, and it is
the right way round only because the keyring is a package like any other.

**Publish the fingerprint** in the top-level `README.md` and anywhere
else the project is described. It is what lets somebody check that the
keyring they received is the one that was meant — the one thing the
signature chain itself cannot tell them, because a forged chain is
self-consistent.

**What the ISO does with all this.** The image ships `zepos-keyring` and
the installed system trusts it implicitly; that is the trust root, and it
is established by the user choosing to boot that medium. Everything after
arrives signed. So the question that decides the design is never "how do
I make a key" but **who can use it, and what happens when it is gone** —
which is why nothing in this repository generates a release key for you.

### Whether to publish yet: not yet, and here is what was measured instead

The recommendation is **do not publish**, for one reason that has nothing
to do with the mechanism: the only key that exists says `DO NOT TRUST` in
its own user id. Everything else is ready.

What was done instead is the stronger test anyway, because it proves the
mechanism without making anything public:

```bash
./packaging/serve-repo.sh                 # stage and serve on 127.0.0.1
./iso/test-boot.py --scenario update      # and let an installed ZepOS update itself
```

The `update` scenario boots the disk the `install` scenario wrote, with
no ISO, and attaches a third disk whose presence tells the guest which
run this is and whose first line is the URL of a repository this machine
is serving. The guest — `zepos-smoke-update`, run as root by
`zepos-update-probe.service` — rewrites **one line** of
`/etc/pacman.conf`, the `Server` inside `[zepos]`, leaves
`SigLevel = Required TrustedOnly` exactly as installed, and puts the file
back before the machine powers off.

Since UP-1 the probe calls `pacman` exactly **once** — for the one thing
a machine installed *before* UP-1 cannot do for itself: obtain the
updater at all. Everything after that is watched, not driven. What
happens then happens because a systemd timer runs down.

Measured, 11.08.2026, on the system `--scenario install` produced,
against a repository built from a bumped `VERSION`:

```
RESULT update=0 db=0 bootstrap=0 downloaded=1 command=0 timer=enabled
       setting=0 dropin=0 unattended=0 wartete=901s state=ok
       moved=3 pending=3 foreign=0 marker=0
       nokey=1 nokeysaid=0 withkey=0
       server=https://zeptronit.github.io/ZepOS/$arch
       restored=https://zeptronit.github.io/ZepOS/$arch
```

Read it in order, because the numbers are the whole claim:

- `timer=enabled` — nobody ran `systemctl enable`. The machine received
  `zepos-config` as an ordinary package upgrade, and the ALPM hook in it
  ran `zepos-update --apply`.
- `setting=0 dropin=0` — `zepos-settings set
  update.schedule.randomized_delay 0` reached
  `/etc/systemd/system/zepos-update.timer.d/10-zepos.conf`. Before that
  command, `systemctl list-timers` said the next run was **1h 10min**
  away (15 minutes plus the shipped hour of jitter); after it, the timer
  fired at `OnBootSec=15min` on the dot.
- `wartete=901s unattended=0` — the probe then sat still for fifteen
  minutes and the service ran on its own: `Starting
  ZepOS-Aktualisierung...` at 18:46:41, finished 786 ms later.
- `moved=3 pending=3 foreign=0` — `zepos-installer`,
  `zepos-installer-tui` and `zepos-keyring` went from `0.1.0-1` to
  `0.1.1-1`, counted from the package database rather than from the
  service's prose, and **not one** package outside `[zepos]` moved. The
  Arch base is reported, never touched.
- `marker=0` — `/var/lib/zepos/regenerate-required` is there, which is
  what makes the next login regenerate the configuration. The running
  session is not touched; `src/update.py` says why at length.
- `nokey=1 nokeysaid=0` — the negative control, and it is stricter than
  before: the key is deleted, the synced database is deleted with it (a
  `pacman -Sy` that answers *"is up to date"* verifies nothing), and
  `zepos-update` itself is asked again. It fails with `1` **and leaves
  `"result": "failed"` plus 556 characters of pacman's own words** in
  `/var/lib/zepos/update-state.json`. A failure nobody can see afterwards
  would be indistinguishable from a machine that is up to date.

and, from the other side, the server's own access log — the four packages
after the first one were fetched by nobody:

```
3x "GET /x86_64/zepos.db"                                    200
4x "GET /x86_64/zepos.db.sig"                                200
2x "GET /x86_64/zepos.db"                                    304
   "GET /x86_64/zepos-config-0.1.1-1-any.pkg.tar.zst"        200   <- der Handgriff
   "GET /x86_64/zepos-config-0.1.1-1-any.pkg.tar.zst.sig"    200
   "GET /x86_64/zepos-installer-0.1.1-1-any.pkg.tar.zst"     200   <- der Zeitgeber
   "GET /x86_64/zepos-installer-0.1.1-1-any.pkg.tar.zst.sig" 200
   "GET /x86_64/zepos-installer-tui-0.1.1-1-any.pkg.tar.zst" 200
   "GET /x86_64/zepos-installer-tui-...pkg.tar.zst.sig"      200
   "GET /x86_64/zepos-keyring-0.1.1-1-any.pkg.tar.zst"       200
   "GET /x86_64/zepos-keyring-0.1.1-1-any.pkg.tar.zst.sig"   200
```

Every `.pkg.tar.zst` is followed by its `.sig`, which is what
`SigLevel = Required` looks like from the server's side.

The phases behind those numbers, and the last one is what makes the
others mean anything:

- **the database.** `pacman -Sy` with `SigLevel = Required`, which is a
  statement about `zepos.db.sig` before it is a statement about any
  package.
- **a package, downloaded.** The cache is emptied first — and that is not
  tidiness: `pacstrap` copied every package it installed into the
  target's `/var/cache/pacman/pkg`, so `pacman -S zepos-config` would
  otherwise have found the file locally and reported success for a
  repository it never contacted.
- **the unattended run.** Not a command in this script: the timer. The
  probe records what `pacman -Qu` still offered out of `[zepos]` — asked
  through `pacman -Slq zepos`, because `aylurs-gtk-shell`, `libastal-*`
  and `wlogout` come from that repository and are not called `zepos-*` —
  and then compares it afterwards against what the package database
  actually shows. `moved == pending` is the assertion, and it is graded
  against a snapshot taken **after** the one manual step, so that step
  cannot be mistaken for something the machine did by itself.
- **the negative control.** `pacman-key --delete <fingerprint>`, and the
  same repository is **refused**: *"Keine Datenbank konnte synchronisiert
  werden (Ungültige oder beschädigte Datenbank (PGP-Signatur))"*. Then
  `pacman-key --populate zepos` — which is the only thing
  `zepos-keyring`'s install scriptlet does — and it is accepted again.
  Without this half, every line above passes just as well on a machine
  that verifies nothing.

Two things that this does **not** prove, stated plainly:

- **that `zeptronit.github.io` behaves like `python3 -m http.server`.**
  The layout, the symlink resolution and the `.nojekyll` are what the
  difference between them was expected to be, and they are handled; a
  redirect or a content-type surprise from Pages would only show up on
  the first real publish. `curl -sI .../x86_64/zepos.db` immediately
  after it is the check.
- **that anybody was told.** `sessions: []` — the update run has no
  graphical session by design (`zepos-smoke` stands down when the update
  disk is present, so that a desktop does not compete with pacman for the
  machine). The notification path is therefore measured in the test suite
  and not here.

One thing that was found on the way and is worth keeping: pacman is
translated, and an installed ZepOS is a German system. The first version
of the download check counted the string `Total Download Size` and
reported 0 for a run that had downloaded the package perfectly well. Any
check against the output of a program the user reads in their own
language is a check that passes only on the developer's machine.

### Reproducibility: measured, and now yes

Two consecutive full builds of the same tree produce **eleven
byte-identical packages** — every one of them, including the 51 MB
`zepos-hyprland`. The two `manifest.txt` files differ in the `built`
timestamp and in nothing else.

That was not true at first:

| | first measurement | after |
|---|---|---|
| `zepos-config` | identical | identical |
| `libastal-io`, `libastal-4`, `libastal-notifd` | identical | identical |
| `aylurs-gtk-shell` | **differed** | identical |
| `zepos-hyprland` | identical | identical |
| the five plugin packages | identical | identical |

The AGS difference was 40 bytes in an 11 MB binary — `.note.go.buildid`
and the `.note.gnu.build-id` `ld` computes over content containing it —
and nothing else in the package. `-buildid=` fixes it, and it has to be
patched into `meson.build` rather than passed through `GOFLAGS`, because
meson gives `go build` its own `-ldflags` and an explicit flag overrides
the same flag in `GOFLAGS`. (The AUR recipe's
`-ldflags=-linkmode=external` is silently discarded for that reason.)

Nothing had to be done for the six C++ packages, which was not obvious in
advance. Three things could have gone wrong there and did not: the
release tarball carries its own `version.h.in` with the commit already
substituted, so no build reaches for `git`; LTO across 953 objects is
deterministic given the same inputs; and the two hyprwm plugins list
their sources with `run_command('find', '.', '-name', '*.cpp')`, whose
output order is `readdir` order — the same tarball unpacked twice on the
same filesystem gives the same order, so the link order and the binary
are the same. That last one is luck rather than design, and worth
knowing before someone concludes the build is reproducible on a machine
with a different filesystem.

What makes the rest of it hold:

- `SOURCE_DATE_EPOCH` comes from the commit, not the clock, and makepkg
  clamps every file modification time in the package to it;
- `zepos-config`'s source tarball is built with `--sort=name`, fixed
  ownership and that same timestamp, so one tree gives one tarball;
- the build container is pinned to the ISO's Arch snapshot.

Two caveats, both real:

- `.BUILDINFO` records the packages installed in the build container.
  `build.sh` installs everything already in `packaging/out/` before it
  starts — it has to, or building one recipe whose dependency was built
  by an earlier run fails with `target not found: libastal-io` — so a
  build against an empty `packaging/out/` and a build against a populated
  one produce different `.BUILDINFO`, and different packages. Full
  rebuilds are stable because the set reaches a fixed point immediately;
  a clean-room rebuild is a different measurement and has not been made.
  Measured again when the five plugin packages arrived: the run that
  first produced them and the run after it disagree about every package,
  because the second one had `zepos-hyprland` and the plugins installed
  in the container while it built `zepos-config`. The run after **that**
  matches. So "two consecutive builds" means the second and third of
  three, and that is what was compared.
- The Go module cache is downloaded during the build. `go.sum` pins the
  content, so it cannot be substituted, but it does mean the build needs
  a network. Vendoring the modules into a source tarball would remove
  that; it has not been done.

The **image** is still not bit-reproducible; `iso/README.md` has that
measurement and it is unchanged by any of this.

## The build order, and what it is ordering

`PACKAGES` in `build.sh` is the order, and each package is installed into
the container as it finishes — which is what makes the next one
resolvable. Three different kinds of dependency run through it:

- **Headers.** The five plugin packages depend on `zepos-hyprland` in the
  strongest sense there is: `pkg_check_modules(HYPRLAND REQUIRED
  hyprland)` reads the `hyprland.pc` it installs, so without it they do
  not fail at link time, they fail at the configure step.
- **Typelibs and sonames.** `aylurs-gtk-shell` names `libastal-io` and
  `libastal-4` among its `depends`, and `makepkg --syncdeps` cannot
  resolve those from any repository until `astal` has produced them.
- **Names.** `zepos-desktop` is last, and it is the only recipe whose
  build is *entirely* a dependency check: a meta package has no source
  and no compile, so `makepkg --syncdeps` resolving its forty-four
  `depends` is the whole of what building it proves. That is worth the
  minutes it costs — a misspelled package name in a meta package is
  otherwise discovered on a user's machine, and nowhere before it.

Three shapes recur, and each is written down once:

- **Split packages.** `packaging/astal/PKGBUILD` produces three packages
  from one source tree, including two that depend on the first — which
  needs a staging install inside `build()`, and the five environment
  variables its comments explain. `packaging/hyprland-plugins` is the
  easy version: two packages, one tarball, no dependency between them.
  `packaging/zepos-installer` is astal's problem with astal's answer,
  minus the staging: three python packages need no build against each
  other, only a division of one tree that no two of them may both own.
- **A local source that is not downloaded.** `zepos-config` packages this
  repository's own `src/`, `zepos-installer` packages `installer/` and
  `po/`, and `zepos-keyring` packages a key `build.sh` exported moments
  earlier. All three are made from the **working tree**, with `--sort=name`
  and mtimes clamped to `SOURCE_DATE_EPOCH`, so one tree gives one
  tarball; all three are `sha256sums=('SKIP')`, because a checksum of a
  file the same script just wrote verifies nothing.
- **Pinning upstreams that do not want to be pinned.** astal has no tags
  at all, so it is pinned by commit hash with a checksum over the tarball
  at that hash. The three own plugin repositories are the same case;
  `hyprwm/hyprland-plugins` does have tags, and is pinned by the commit
  the tag resolves to rather than by the tag name, because a tag can be
  moved and a commit cannot.

And one thing that only the ISO can show: `zepos-hyprland` provides
`hyprland` and conflicts with it, so naming both compositors in
`iso/profile/packages.x86_64` stops `pacstrap` rather than picking one.
