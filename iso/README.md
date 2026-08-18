# The ZepOS images

There are two, built by one script from two profiles, and the difference
between them is the whole of this file's first section.

| | `iso/profile/` | `iso/profile-release/` |
|---|---|---|
| built with | `./iso/build.sh` | `./iso/build.sh --profile release` |
| booted with | `./iso/test-boot.py` | `./iso/test-boot.py --scenario release`, `release-install`, `release-installed`, `boot-menu` |
| what it is | a test harness | the medium a person is handed |
| boots into | a Hyprland session, or an unattended installation | the installer |
| logs in | `agetty --autologin zepos` | nobody, ever |
| credentials | its own `/etc/shadow`, and a root password in `unattended-install.json` | none |
| reports on itself | serial console, evidence disk, `RESULT` lines | nothing; you look at the screen |

The rest of this file is about the first one, which came first and is
still what measures whether a ZepOS desktop comes up. [The shipping
medium](#the-shipping-medium) is at the bottom.

## The smoke ISO

The smallest bootable image that can answer three questions, of which
the first was the only one it could answer until now:

> ZepOS has never been installed and never been booted. Its unit tests
> say each component does what it claims. Does a desktop come up?

> The installer has 34 test call sites and every one of them runs dry or
> against a fake. Does it partition a real disk and finish?

> And is what it produced a system — does it boot on its own, with the
> medium that installed it removed?

Not the shipping ISO of spec §8, and it never becomes one: there is no
menu, no language selection, and the installation it performs is an
unattended one out of a configuration committed in the profile — with
the root password in it. The shipping ISO is a profile of its own, and
the table above is why.

Since TP3 it **installs** the ZepOS packages rather than copying `src/`
into the image by hand. `zepos-config`, `aylurs-gtk-shell`,
`zepos-hyprland` and the five plugin packages come out of the signed
repository `packaging/build.sh` produces, and the build container is
made to trust that repository's key before `pacstrap` will accept them.

The compositor is `zepos-hyprland` and not the `hyprland` in extra — the
two conflict, and a profile naming both would stop `pacstrap` rather
than pick one. Spec §4.2 and the revision to §7 have the argument: five
plugin packages are compiled against its headers, and a compositor that
arrives on somebody else's release schedule can move under them.

## Running it

```bash
./packaging/build.sh --key <id>   # first: the repository the image installs from
./iso/build.sh                    # ~5 minutes, needs docker; writes iso/out/*.iso
./iso/test-boot.py                # ~3 minutes, needs qemu; writes iso/out/run/
```

and, for the three runs that answer the other three questions:

```bash
./iso/test-boot.py --scenario install     # ~20 minutes; writes iso/out/target.img
./iso/test-boot.py --scenario installed   # boots that disk, ISO removed
./iso/test-boot.py --scenario update      # and lets it update itself, ~2 minutes
```

and, for the three questions a stranger's machine asks — see
[Secure Boot](#secure-boot-was-genau-abgelehnt-wird), [der
BIOS-Startweg](#der-bios-startweg-gemessen) und ["Offline
installieren"](#offline-installieren-was-es-kostet-und-was-es-heute-ist):

```bash
./iso/secureboot.py inspect               # ohne QEMU: traegt die Startkette Signaturen
./iso/test-boot.py --scenario secure-boot # ~2 Minuten; zwei Maschinen, ein Unterschied
./iso/test-boot.py --scenario release --firmware bios   # was ein BIOS-Nutzer sieht
./iso/test-bios-chain.py                  # ~8 Minuten, braucht docker; baut und startet
```

None of them writes anything the repository tracks. `iso/work/`,
`iso/out/` and `*.iso` are ignored by git — including `target.img`, the
file-backed virtual disk, and `efivars.fd`, the UEFI variable store.

The first line is not a convenience. `packaging/build.sh` has to run
again after **any** change under `src/`, `installer/` or `po/`, because
the image installs those directories as packages and never reads them
from the tree.

Nothing about a package says it is out of date. Every ZepOS package is
`0.1.0-1` and stays `0.1.0-1` across such a change: same file name, same
database entry, same answer from every version comparison pacman makes.
On 10.08.2026 that put an image on a USB stick that was missing the
`installer/gui/app.py` fix it had been rebuilt for, and still carried
`icon_manager.py` four days after the tree had renamed it. `iso/build.sh`
had checked that a repository existed, which it did.

So `iso/build.sh` now runs `packaging/check-current.py` before it starts
the container: it opens each package built from this repository and
compares its contents against the tree, both ways round — a file whose
source has changed, and a file whose source is gone. It refuses the
build rather than repairing it, because rebuilding needs the signing
key, and a build script that reaches for a key on its own is a worse
problem than a stale package.

### The four scenarios

They are one tool on purpose. An installation is a different scenario,
not a different harness: the serial line the guest reports on, the raw
disk it hands evidence over on and the framebuffer dumps for the boots
that never get that far are exactly the same apparatus, and a second
script would be a second place for the marker string, the device names
and the QMP client to drift.

| | machine | graded on |
|---|---|---|
| `session` | the ISO, **BIOS**, one disk (evidence) | `session=up` |
| `install` | the ISO, **UEFI**, plus a target disk | `install=0` |
| `installed` | **no ISO**, UEFI with the variables the installation wrote | `session=up` |
| `update` | the same, plus a third disk carrying a repository URL | `update=0` |

Three more scenarios — `release`, `release-install`, `release-installed`
— boot the shipping medium instead, and none of them appears in that
table because none of them can: that image reports nothing, so there is
no `graded on` column for it. They are in
[the shipping medium's section](#the-shipping-medium).

Four things in that table are decisions rather than settings.

**The firmware differs, and it has to.** `installer/core/firmware.py`
refuses a machine that started in BIOS mode outright. Der Kopf jener
Datei traegt den Grund, und er ist am 11.08.2026 wieder kleiner
geworden: der BIOS-STARTWEG ist gemessen — `./iso/test-bios-chain.py`
baut ZepOS' eigene Einteilung als MBR, richtet GRUB fuer `i386-pc` ein
und startet das Ergebnis unter SeaBIOS bis zum Anmeldezeichen —, aber
archinstalls Weg dorthin ist gelesen und nicht gefahren, und die
Loeschung kaeme vor der Antwort. So the installation
cannot be run the way the session run is. The session scenario keeps BIOS deliberately: it is
the measurement everything else is compared against, and changing it
would make the comparison to earlier runs meaningless.

**The UEFI variable store outlives the run.** `grub-install` ruft unter
UEFI `efibootmgr` auf und schreibt damit einen EFI-Starteintrag hinein,
and the `installed` scenario has to find that entry. A fresh copy would exercise the
removable-media fallback (`\EFI\BOOT\BOOTX64.EFI`) instead — which may
well work, and would quietly answer a different question.

**The guest works out which run it is by itself.** There is one image and
one bootloader entry, and an unattended run cannot answer a menu. So the
discriminator is the machine: an installation happens exactly when there
is a disk at `/dev/disk/by-id/virtio-zepos-target` **and** `/run/archiso`
exists. The second half is not redundant — the installed system boots
from a disk carrying that same serial and runs the same
`/usr/local/bin/zepos-smoke` to report on itself, and without the check
the first boot of a freshly installed machine would be an attempt to
reinstall it.

**The update run's disk carries a message rather than a filesystem.** It
is one megabyte of zeroes with a URL on the first line, and it does two
jobs at once: its presence is how the guest knows this is an update run —
on the installed system there is no `/run/archiso` to ask about — and its
contents are where the packages are, which is what lets the host bind
whatever port happens to be free instead of both halves agreeing on a
number. The guest reads it with `head -c`, so nothing has to be mounted
on the one boot being measured. `zepos-smoke-update` rewrites exactly one
line of `/etc/pacman.conf` — the `Server` inside `[zepos]`, never the
`SigLevel` — and puts the file back before the machine powers off.

The repository it points at is served by `packaging/serve-repo.sh` on the
host, out of the tree `packaging/publish.sh` stages: symlinks resolved,
`.nojekyll` in place, byte for byte what a push to `gh-pages` would
publish. The run therefore measures the published layout without
publishing anything. `packaging/README.md` has the result and the
negative control that makes it mean something.

Two notes for whoever runs it. The scenario refreshes the harness
scaffolding inside `target.img` first, through a privileged container
with a loop device, because a disk installed before the update probe
existed does not carry it — `--no-stage-probe` turns that off. And the
run **modifies the installed system**: it installs `zepos-installer-tui`
and re-downloads `zepos-config`, which is the point, and which the
`installed` scenario will see afterwards.

### The disks are named, not counted

`zepos-smoke-collect` used to write its tar to `/dev/vda`, which was
correct while there was exactly one virtio block device. There are two
now, and on the installed system one of them is the root filesystem —
`tar cf` onto that destroys the system whose first boot is being
measured, *after* the measurement has succeeded. Both disks therefore
carry a QEMU `serial=`, which udev turns into
`/dev/disk/by-id/virtio-<serial>`, and no script in the image names a
positional node at all. There is deliberately no fallback: a missing
evidence disk costs a run its evidence, which the serial log survives.

`build.sh` runs `mkarchiso` inside a container because mkarchiso needs
root and is not installed on the development machine. Every container
runs with `--network host`: this machine's IPsec tunnel routes all three
RFC1918 ranges, the Docker bridge lives inside `10.0.0.0/8`, and a
bridged container has no network at all. Spec §10.1 predicted it and it
was measured again here.

`test-boot.py` exits 0 only when the guest itself reported
`session=up`. The exit code is a convenience; the result is the evidence
in `iso/out/run/`:

| File | What it is |
|---|---|
| `serial.log` | the guest's console, from the first kernel line onwards |
| `screen-*.png` | QEMU's framebuffer — what the screen showed |
| `evidence/screenshot-compositor.png` | `grim`'s capture — what Hyprland drew |
| `evidence/hyprland.log` | the compositor's own log |
| `evidence/generate.log` | `zepos-generate --all`, in full |
| `evidence/hyprctl-*.json` | monitors, clients, binds, layers, plugins of the live session |
| `evidence/plugin-refused.txt` | what the compositor said about a plugin it would not load — empty when it took all of them |
| `evidence/config/` | the configuration that was actually generated |
| `evidence/journal.txt` | the boot's journal |
| `evidence/pacman.conf`, `evidence/mirrorlist` | what the machine will update from — the §8.5b question, asked of the running system |

and, from the `install` scenario:

| File | What it is |
|---|---|
| `evidence/archinstall.log` | everything archinstall printed, in full |
| `evidence/archinstall-logs/` | its own `/var/log/archinstall`, including the configuration it parsed |
| `evidence/target-pacman.conf`, `-mirrorlist` | the same two files, read off the target root while it was still mounted |
| `evidence/target-packages.txt` | `pacman -Q` against the target's database |
| `evidence/target-grub.cfg`, `-boot.txt` | die ESP: das erzeugte Startmenue und was `grub-install` wohin gelegt hat. Hieß bis zur Umstellung auf GRUB `target-loader/` und war systemd-boots Eintragsverzeichnis. |
| `evidence/lsblk.txt` | the partition table that was written |

and, from the `update` scenario:

| File | What it is |
|---|---|
| `repo-server.log` | the **host's** access log — every `GET` the guest's pacman made, from the other side of the wire |
| `evidence/pacman-sy.log` | `pacman -Sy`: the database and its signature |
| `evidence/pacman-s-control.log` | a package downloaded and verified, with the cache emptied first so it could not come from there |
| `evidence/pacman-syu.log` | the upgrade transaction itself |
| `evidence/pacman-s-new.log` | `zepos-installer-tui`, which spec §4.2 keeps out of an installed system — a genuine new installation out of the repository |
| `evidence/pacman-sy-without-key.log` | the negative control: the same repository, refused, after `pacman-key --delete` |
| `evidence/pacman-sy-with-key.log` | and accepted again after `pacman-key --populate zepos` |
| `evidence/pacman.conf.before`, `.pointed-at-local`, `.after` | the one line that was changed, and the file put back |

## What the boot showed

The answer to the question at the top is **yes**, and this is the
guest's own summary of the run that says so:

```
ZEPOS-SMOKE: generate rc=0
ZEPOS-SMOKE: verify-config rc=0
ZEPOS-SMOKE: session up after 2s
ZEPOS-SMOKE: RESULT session=up generate=0 verify=0 monitors=1 binds=80 \
             clients=1 layers=nwg-dock,waybar
```

Read out: `zepos-generate --all` produced the whole configuration;
`Hyprland --verify-config` answered `config ok` on it; the compositor
came up on `Virtual-1` at 1280x800; Waybar and nwg-dock are both live
layer-shell surfaces, which is why the monitor reports
`reserved: [0, 50, 0, 210]` — 50 px taken at the top by the bar and
210 px at the bottom by the dock; and eighty key bindings are
registered. Both screenshots show the bar with its Nerd Font glyphs, the
workspace pills, the clock, and a Kitty window.

### The AGS layer, once it was packaged

The run above had no AGS at all. The run after TP3 packaged it reports:

```
ZEPOS-SMOKE: PHASE ags
ZEPOS-SMOKE: ags up
ZEPOS-SMOKE: RESULT session=up generate=0 verify=0 monitors=1 binds=77 \
             clients=0 ags=up layers=calendar,nwg-dock,waybar
```

`ags request calendar` answered `toggled`, and the layer it mapped is in
the compositor's own list — `calendar`, 450x667 at 415,70, on
`Virtual-1`, belonging to the `gjs -m /run/user/1000/ags.js` that
`ags run` started. `evidence/screenshot-compositor.png` shows the widget
drawn: the German heading, the month grid with today highlighted, the
Nerd Font icons, all of it styled by the `style.scss` that
`ags-style.template` generated and `dart-sass` compiled.

The probe is a request rather than a process check for the same reason
the session probe is `hyprctl monitors` and not `pgrep`: a gjs process
that started and then failed on an import is still a running process. An
answer means the bundle compiled, every `gi://` import resolved, `main()`
ran and the widgets exist. It also has to come first — the widgets are
created hidden, so a `hyprctl layers` taken before the toggle would show
a working AGS as an empty screen.

### The plugins, once they were packaged

The two runs above had no Hyprland plugin loaded, because no plugin
package existed. `plugins.conf` came out as 81 comment lines naming each
missing object, its package and the command to rerun, plus exactly two
live lines — SUPER+SPACE on `wofi --show drun` and SUPER+SHIFT+V on
`cliphist-wofi.sh`. That was this image's most useful negative result:
the first real test of `07021b1`'s failsafe, and it held. `Hyprland
--verify-config` said `config ok` and all eighty binds used built-in
dispatchers. Before that commit the same machine produced three
`Invalid dispatcher` errors and no session at all.

The run with `zepos-hyprland` and the five plugin packages installed:

```
ZEPOS-SMOKE: verify-config rc=1
ZEPOS-SMOKE: verify-config errors that are not plugin dispatchers: 0
ZEPOS-SMOKE: plugins loaded=borders-plus-plus,hyprbars,hyprclipx,hyprlaunch,hyprzones refused=none
ZEPOS-SMOKE: RESULT session=up generate=0 verify=1 verifyother=0 monitors=1 \
             binds=92 clients=0 ags=up layers=calendar,nwg-dock,waybar \
             plugins=borders-plus-plus,hyprbars,hyprclipx,hyprlaunch,hyprzones \
             pluginlines=5 refused=none
```

All five objects loaded. `plugins.conf` carries five real `plugin =`
lines instead of the comments, the bind count went from 77 to 92, and
three of those binds are plugin dispatchers the compositor accepted:

```
SUPER       SPACE  ->  hyprlaunch:toggle
SUPER SHIFT H      ->  hyprlaunch:helpers
SUPER SHIFT V      ->  hyprclipx:toggle
```

`hyprctl plugin list` names each plugin by the string it registered in
its own `pluginInit`, which is the compositor's word that the object
*ran* rather than merely opened.

**`verify-config` now returns 1 on a machine where everything works, and
that is a limitation of `--verify-config`.** It reports exactly those
three dispatchers as `Invalid dispatcher`, because it does not load
plugins and cannot: `handlePlugin` in
`src/config/legacy/ConfigManager.cpp` only records the path, and
`handlePluginLoads()` returns immediately when there is no plugin
system — and there is none without a compositor. In the session the same
three errors appear once, during the first parse, and are gone after the
plugin system loads the objects and reloads the configuration.

Spec §7.4's measurement still holds — the dispatcher bind is the form
Hyprland rejects — it just now says something about the verifier rather
than about the configuration. Since a permanently failing check hides
the next real error behind it, `zepos-smoke` also counts the errors that
are *not* about a plugin dispatcher and reports that as `verifyother`.
That is the number which has to stay 0.

One thing worth knowing before reading the evidence: **the compositor's
log says nothing about plugins.** Hyprland's `debug:disable_logs`
defaults to true and the generated configuration does not turn it off,
so after the first few lines it writes nothing of its own —
`evidence/hyprland.log` from this run is 41400 lines of which 41249 are
aquamarine's trace and not one mentions a plugin. A refused plugin would
leave no trace anywhere. `zepos-smoke-collect` asks instead: for any
object with a load line that is not in `hyprctl plugin list`, it runs
`hyprctl plugin load` on it and keeps the compositor's own error string
in `evidence/plugin-refused.txt`.

Two things the run turned up about the desktop itself, neither of them
about the ISO:

- **Every login opens a full-size Kitty window tailing the Waybar log.**
  `generate_config.sh`'s post-generation step for `-waybar-config` starts
  `kitty --class floating-center -e tail -f .../waybar.log` whenever a
  Wayland display exists, and `start-hyprland` runs that step after the
  compositor is up. Both screenshots show it covering the desktop.
  *Behoben am 11.08.2026: der Zweig ist mit waybar selbst entfallen. Die
  Leiste ist `ags/widget/Bar.tsx` und wird von dem AGS-Prozess getragen,
  den ein `--all`-Lauf am Ende einmal neu startet - siehe
  `tests/src/test_generate.py::test_generating_the_bar_touches_no_running_process`.*
- **Two dead `exec-once` lines survive in
  `hyprland-universal-config.template`**: `systemctl --user start
  onedrive` and `sunshine`. OneDrive is listed for deletion in spec §6.1
  and neither program is anything ZepOS ships. They fail silently, so
  they cost nothing but a fork per login — which is exactly why nobody
  has noticed them.

## How the two halves talk

The guest writes progress markers to `/dev/ttyS0` and the harness polls
the file QEMU captures them into. Everything larger — logs, screenshots,
the generated configuration — is handed over as a tar stream written
straight onto a raw virtio disk, and unpacked on the host with
`tar xf evidence.img`. tar stops at its end-of-archive marker and ignores
the rest of the device, which is what makes an unformatted block device
a legitimate destination.

Both channels exist before any userspace of ours runs and neither can
fail for a reason of its own. A network channel would depend on the
guest's networking, which is one of the things under test; a shared
filesystem would add a mount that can fail on the one boot being
measured.

## What Hyprland needs on a machine with no GPU

Written down here because TP5-2 inherits it, and because the answer is
not the one that gets guessed.

**It needs no environment variable at all.** Two images were built and
booted, identical but for one line:

| | with `LIBGL_ALWAYS_SOFTWARE=1` | without it |
|---|---|---|
| session | comes up | comes up |
| renderer named in the log | none | `llvmpipe (LLVM 22.1.8, 256 bits)` |
| `CDRMRenderer: Can't create renderer` | yes | no |
| `Failed to update renderer state for Virtual-1` | **once per frame** | no |

Forcing the software device costs it `EGL_EXT_device_drm`, so aquamarine
can no longer match the EGL device against the DRM node it just opened,
and falls into its multi-GPU error path on every commit. Left alone,
Mesa prints `libEGL warning: NEEDS EXTENSION: falling back to
kms_swrast` and gets there by itself. The variable is not set.

What is actually required:

- **A DRM device with dumb buffers.** `-vga virtio` gives the guest
  `/dev/dri/card0` with the `virtio_gpu` driver; Hyprland reports the
  connector as `Virtual-1`, 1280x800, with an EDID that reads
  `Red Hat, Inc. QEMU Monitor` — which is what the EDID-based monitor
  detection of spec §6.5 has to work from on a VM.
- **A seat.** Hyprland takes the VT through libseat and logind, so the
  session starts from an autologin getty on tty1: that is what gives it
  `seat0`, a VT number and an `XDG_RUNTIME_DIR`. A systemd system
  service would have none of the three.
- **`no_hardware_cursors = true`**, which
  `hyprland-universal-config.template` already sets.
- **Not** `WLR_RENDERER=pixman` or `WLR_RENDERER_ALLOW_SOFTWARE`:
  Hyprland has not used wlroots since 0.42, and nothing else in this
  image is a compositor.

`AQ_TRACE=1` *is* exported — not because the session needs it, but
because it costs about 20 kB of log per second and is what made the
comparison above possible.

## What the first boots failed on

This image had never been booted before. None of the following was
visible in the profile source, each cost a full build-and-boot cycle to
find, and every one is now asserted by `tests/iso/test_smoke_profile.py`.
They are listed because the next person to extend this profile will meet
the same set.

1. **`systemd-firstboot` asked for a timezone and the boot stopped
   there.** mkarchiso writes `/etc/machine-id` as `"uninitialized"`, so
   systemd's `ConditionFirstBoot` is true on *every* boot of an archiso
   image, and `systemd-firstboot.service` runs before `sysinit.target`.
   The run reported a timeout with an empty serial log — the exact shape
   of "the desktop did not start". Fixed by masking the unit and shipping
   the four files it would have asked about (`locale.conf`, `localtime`,
   `vconsole.conf`, `hostname`). An image that boots without a keyboard
   has no business owning an interactive setup unit.

2. **A second build silently returned the first ISO.** mkarchiso records
   finished steps as marker files in its work directory and skips them.
   Two builds, one real fix in between, identical sha256. `build.sh` now
   removes the work directory inside the container before every run.

3. **`/run/zepos-smoke` could not be created.** `/run` belongs to root.
   Every write of the run — the progress log, the generator's output,
   both return codes — failed for the whole boot. The evidence directory
   is now `$XDG_RUNTIME_DIR/zepos-smoke`.

4. **`/dev/ttyS0` and `/dev/vda` are not writable by an ordinary user.**
   udev gives serial devices to `uucp` and block devices to `disk`. The
   progress markers were being dropped by a permission error the
   script's own `2>/dev/null` swallowed. The live user is now in both
   groups.

5. **`zepos-generate --all` returned 126.** mkarchiso copies the profile's
   airootfs with `--no-preserve=mode`, so every mode in git is discarded
   and everything lands 0644. Anything that is *run* has to be named in
   `file_permissions`. One missing mode, no configuration, no session.

6. **A working desktop was reported as `session=timeout`.** The readiness
   probe called `hyprctl`, which locates its instance through
   `HYPRLAND_INSTANCE_SIGNATURE` — and the collector is not a child of the
   compositor, so nothing had set it. That run's `grim` capture shows a
   complete desktop; the harness graded it a failure. The collector now
   derives the signature from `$XDG_RUNTIME_DIR/hypr/`.

7. **`monitors=3` for one monitor.** The count was a grep for `"name"`,
   and a monitor object also carries the name of its active workspace and
   of its special workspace. Now counted with `jq`.

## Version pinning

`iso/profile/pacman.conf` names an Arch Linux Archive snapshot, so the
contents of the image are a function of the commit and not of the day it
was built (spec §8.7). The pin is committed rather than passed on the
command line, because a pin that lives in somebody's shell history is not
a pin.

```bash
./iso/build.sh --snapshot 2026/07/01   # a different date
./iso/build.sh --snapshot current      # today's mirrors, deliberately awkward
```

Two things are pinned in two places and confusing them costs an
afternoon: what goes *into* the image is pinned by the profile's
`pacman.conf`; what *builds* the image is the container from
`iso/Dockerfile`, which takes current packages. `build.sh` records both
next to the ISO — `out/manifest-<profile>.txt`,
`out/packages-in-<profile>.txt`, `out/build-toolchain.txt`.

### How reproducible it actually is

Measured, over three clean builds of the same commit:

| | result |
|---|---|
| package set (name and version, 398 packages) | **identical** |
| ISO size | **identical**, 1 097 646 080 bytes |
| ISO sha256 | **different every time** |

So the *system* is reproducible in the sense spec §8.7 needs — a bug
report names a commit, and that commit installs the same versions of the
same packages — but the image is not bit-reproducible. `SOURCE_DATE_EPOCH`
is taken from the commit and honoured by mkarchiso and xorriso; what
remains varies inside the squashfs and the initramfs, and the pacman
keyring generated during pacstrap is not deterministic either.

That gap is named here rather than papered over: the comparable artifact
today is `out/packages-in-<profile>.txt`, not the checksum. Closing it is
work for TP5-2 and it is not free.

The ZepOS *packages* are a separate measurement and a better one.
`packaging/README.md` has that table, and what had to change to get it.

## What the installation showed

ZepOS had never been installed. It has been now, onto a 24 GiB
file-backed virtual disk, unattended, out of the configuration committed
at `airootfs/usr/local/share/zepos-install/unattended-install.json`. This
is the guest's own account of it:

```
ZEPOS-SMOKE: target /dev/disk/by-id/virtio-zepos-target -> /dev/vdb (25769803776 bytes)
ZEPOS-SMOKE: firmware UEFI
ZEPOS-SMOKE: mirrorlist pinned to 2026/08/04
ZEPOS-SMOKE: pacman-key rc=0 keys=183
ZEPOS-SMOKE: install rc=0
ZEPOS-SMOKE: driver: install() returned 0
ZEPOS-SMOKE: driver: warnings 0
ZEPOS-SMOKE: target pacman.conf zepos-sections=1 \
             servers=https://zeptronit.github.io/ZepOS/$arch file-urls=0
ZEPOS-SMOKE: target packages 515
ZEPOS-SMOKE: RESULT install=0 zepos-sections=1 file-urls=0 \
             servers=https://zeptronit.github.io/ZepOS/$arch
```

Read out: `archinstall` wiped `/dev/vdb`, wrote the GPT that
`installer/core/translate.py` builds — a 512 MiB ESP at 1 MiB and an ext4
root filling the rest — installed 515 packages, and returned 0. The disk
it partitioned is the first real one this code has ever seen; the 34 test
call sites that exercise it all run dry or against a fake.

`warnings 0` is the second half of that: `install()` reports everything
after archinstall as a warning rather than an error, so a wireless
profile that could not be written or a repository definition that could
not be corrected would appear there and nowhere else.

### Spec §8.5b, on the machine it is about

The measurement §8.5b asks for is *"nach der Installation pruefen, dass
die `pacman.conf` des Ziels keine `file://`-Quelle enthaelt"*, and it is
taken twice: once against the target root while it is still mounted, and
once by the installed system about itself, one reboot later. Both say the
same thing, and the file is this:

```
[options] … [core] … [extra] …

[zepos]
SigLevel = Required TrustedOnly
Server = https://zeptronit.github.io/ZepOS/$arch
```

One section, the online URL, no active `file://` source — although
`/opt/zepos-repo` is where every ZepOS package on that disk actually came
from. Without `installer/core/pacmanconf.py` there would be **two**
sections here, both naming the medium that has since been unplugged; the
module's own header has the account of how archinstall 4.4 produces the
duplicate.

Two things that came out of taking the measurement rather than reasoning
about it:

- **The first version of the probe reported `file-urls=1` on a machine
  that has none.** The hit was line 100 of pacman's own default
  configuration — `#Server = file:///home/custompkgs`, under a comment
  reading *"An example of a custom package repository"*. It is
  documentation, not a source. A count that says 1 when the answer is 0
  cannot say anything when the answer is 1, which is the only case
  §8.5b exists for, so the probe now counts uncommented `Server =` lines.
- **The installed system's keyring knows the ZepOS key.** That was an
  open question rather than a certainty: `archinstall` calls
  `pacstrap -K`, which *initialises* an empty keyring in the target and
  populates nothing. `pacman-key -l` on the booted system lists 183 keys,
  the ZepOS one among them and marked fully trusted — so
  `SigLevel = Required` on that `[zepos]` section is a promise the
  machine can keep.

The mirrorlist travelled too, which is what makes `[core]` and `[extra]`
usable on the installed machine at all:

```
# Pinned by ZepOS (spec 8.7): the Arch Linux Archive snapshot
# this image was built against.
Server = https://archive.archlinux.org/repos/2026/08/04/$repo/os/$arch
```

## What the first boot of an installed ZepOS showed

The disk above, booted with the ISO removed:

```
ZEPOS-SMOKE: generate rc=0
ZEPOS-SMOKE: verify-config rc=1
ZEPOS-SMOKE: verify-config errors that are not plugin dispatchers: 0
ZEPOS-SMOKE: session up after 2s
ZEPOS-SMOKE: ags up
ZEPOS-SMOKE: plugins loaded=borders-plus-plus,hyprbars,hyprclipx,hyprlaunch,hyprzones refused=none
ZEPOS-SMOKE: RESULT session=up generate=0 verify=1 verifyother=0 monitors=1 \
             binds=92 clients=0 ags=up layers=calendar,nwg-dock,waybar \
             plugins=borders-plus-plus,hyprbars,hyprclipx,hyprlaunch,hyprzones \
             pluginlines=5 refused=none zeposrepo=1/0
```

*Die Protokolle in diesem Abschnitt sind datierte Messungen und bleiben
unveraendert stehen. Seit dem 11.08.2026 heissen die beiden
Layer-Flaechen `zepos-bar` und `zepos-dock` statt `waybar` und
`nwg-dock`: beide sind Fenster desselben AGS-Prozesses.*

Line for line the same summary the live image produces, which is the
point of using the same probe: `zepos-generate --all` built the whole
configuration from nothing on a machine that had never had one, the
compositor came up on `Virtual-1`, all five plugins loaded, AGS answered,
and Waybar and nwg-dock are live layer surfaces. `verify=1` with
`verifyother=0` is the known limitation of `--verify-config` described
further down, unchanged.

`evidence/screenshot-compositor.png` from that run shows the desktop an
installed ZepOS draws: the bar with its Nerd Font glyphs and the guest's
DHCP address, the wallpaper, and the AGS calendar in German with the day
highlighted.

## What an installation needs that a session run does not

Three things, and none of them was missing in a way anybody would have
noticed, because a session run touches no repository and needs no
network.

**A network.** Measured on the run of `a4b03d8`: systemd-networkd was
started by systemd's own first-boot preset, brought `lo` up, and then
had no `.network` file for `enp0s2`. The interface stayed down and
`journalctl -b` from that run contains not one DHCP line. The session
came up regardless. An installation cannot: `pacstrap` fetches the base
system and the forty-odd Arch dependencies of `zepos-desktop` (spec §8.4
— with a network the base system comes from the pinned ALA snapshot and
only the ZepOS packages come from the ISO), and archinstall's
`sanity_check()` waits **without a deadline** for `timedatectl` to report
`NTPSynchronized=yes`, which never happens on a machine that cannot
reach a time server. `20-ethernet.network` and the resolved stub symlink
are the fix, both in archiso's own releng shape.

**Mirrors.** The live medium's `/etc/pacman.conf` is the one the `pacman`
package ships — `Include = /etc/pacman.d/mirrorlist` — against a
mirrorlist whose every server is commented out. The profile cannot ship
a mirrorlist of its own: `pacman-mirrorlist` owns that path, and a file
there stops the build with *"exists in filesystem"* (which is why
archiso's releng edits it from a pacman hook instead). So `iso/build.sh`
writes the ALA snapshot it already read out of `iso/profile/pacman.conf`
into `/usr/local/share/zepos-install/ala-snapshot`, a path no package
claims, and the installation writes the mirrorlist from it. That reaches
the installed system too, and on purpose: `pacstrap` copies the host's
mirrorlist into the new root (`copymirrorlist=1`, read out of
arch-install-scripts 31), so the pin the image was built with is the pin
the installed system keeps.

**A keyring.** `mkarchiso` builds the image with `pacstrap -G`, so the
live medium has no pacman keyring at all — which is also why
`zepos-keyring`'s install scriptlet skipped its own `--populate` during
the build, exactly as its guard intends. `pacman-key --init` and
`pacman-key --populate` run once, before anything is installed;
`--populate` with no argument takes every keyring in
`/usr/share/pacman/keyrings`, which is `archlinux.gpg` from the pacman
dependency and `zepos.gpg` from the package this image carries for this
moment.

None of the three is a workaround. Each is a thing the shipping ISO of
spec §8 will need in the same form.

## What is written into the installed system that is not ZepOS

Four pieces of harness scaffolding, each labelled as such in the file it
lands in, because the `installed` scenario has to be able to report on
itself and a system installed by ZepOS has no reason to be able to:

| written | why |
|---|---|
| `/usr/local/bin/zepos-smoke`, `-collect` | the same probe, so the answer is comparable and not merely similar |
| an autologin drop-in for `getty@tty1` | there is no display manager (§4.2) and nobody at the keyboard |
| `uucp`, `disk`, `systemd-journal` membership | `/dev/ttyS0` is `root:uucp` and block devices are `root:disk`; the evidence leaves through both |
| `console=tty0 console=ttyS0,115200` appended to the loader entry | a boot that dies before userspace otherwise leaves a black screen and nothing else |

The third is done twice — `gpasswd` through `arch-chroot`, and a
`sysusers.d` file. `systemd-sysusers.service` carries
`ConditionNeedsUpdate=/etc`, which is *probably* true on a freshly
installed system, and "probably" is the wrong word for the mechanism
that decides whether the evidence of that boot can be written at all.

## The profile

`iso/profile/` holds only what is ours. Since TP3, nothing of `src/` is
copied into it: `packages.x86_64` names `zepos-config` and pacstrap
installs it from the `[zepos]` repository, so the image carries the same
files, in the same places, with the same modes and the same signature as
an installed system will.

That change also removed four entries from `profiledef.sh`'s
`file_permissions`, and they must not come back. The array is applied
**before** pacstrap, and mkarchiso stops the build on an entry whose file
does not exist yet — so naming a package-owned path there is not
redundant, it is fatal. `tests/iso/test_smoke_profile.py` and
`tests/packaging/test_recipes.py` hold both halves of that.

The profile is derived from archiso's `baseline`, not from `releng`:
releng is a rescue system carrying 130 packages, and every one of them
would be a variable in an experiment that has never been run before.

---

# The shipping medium

`iso/profile-release/`, built with `./iso/build.sh --profile release`.
This is the one that can be handed to somebody: it boots into the
installer and carries nothing that exists only to be measured.

```bash
./packaging/build.sh --key <id>            # the repository it installs from
./iso/build.sh --profile release           # ~4 minutes; writes iso/out/zepos-<date>-x86_64.iso
./iso/test-boot.py --scenario release      # boots it, drives it, photographs it
./iso/test-boot.py --scenario release-install    # ... past the erase confirmation
./iso/test-boot.py --scenario release-installed  # ... and boots what that produced
```

The last two are what
[What an installation from this medium showed](#what-an-installation-from-this-medium-showed)
below is about, and they are worth reading before they are run:
`release-install` **erases `iso/out/release-target.img` and the EFI
variables next to it**, which is the point of it, and `release-installed`
boots exactly that disk with no medium attached. `release` has a disk of
its own — `release-boot-target.img` — because it recreates whatever it is
pointed at and never installs anything, and pointing it at the other
file wipes the installation the pair produced.

`--attach` is the third piece. It drives a machine an earlier
`--keep-running` run left standing, over the same QMP socket, and it is
how every keystroke in `RELEASE_INSTALL_SCRIPT` was found rather than
guessed — a cold boot per guess would have been twenty minutes each.

```bash
./iso/test-boot.py --scenario release-install --keep-running --steps shot:settled
./iso/test-boot.py --attach --label a --steps key:tab wait:1 shot:wo-ist-der-fokus
```

## The boot menu

The first thing anybody sees of ZepOS, and until it was themed it was
white text on black — `grub.cfg` set `terminal_output console` and the
BIOS side ran `menu.c32`, which cannot draw a background at all.

```bash
./iso/test-boot.py --scenario boot-menu                  # GRUB, under OVMF
./iso/test-boot.py --scenario boot-menu --firmware bios  # syslinux, under SeaBIOS
```

Half a minute each. It boots the shipping medium, photographs the first
ten seconds and **measures** the frames; it is the only run in the
release family whose exit code depends on what was on the screen.

### There are two menus and they cannot be one picture

`profiledef.sh` declares `bootmodes=('bios.syslinux' 'uefi.grub')`, and
the two are theming systems with nothing in common. GRUB reads
`grub/themes/zepos/theme.txt`: components with percentage geometry, a
PNG scaled by `desktop-image-scale-method`, PF2 fonts loaded by path and
used by name, a nine-slice pixmap behind the selected entry. syslinux
takes **one** background image at **one** fixed resolution — it does not
scale it — lays text out in character cells of a font it brings itself,
and colours each element with `#AARRGGBB`.

So the two carry the same brand and are not the same picture: same
petrol, same wordmark, same yellow block behind the selected entry, same
words, different geometry. Three things they genuinely cannot share:

* **Type.** Roboto at 24 px on the UEFI side; syslinux's own 8×16
  codepage font on the other. That is also why the help line has no
  umlaut in it — syslinux would draw two boxes.
* **Plurals.** `MENU AUTOBOOT` has a singular/plural form
  (`# Sekunde{,n}`); a GRUB label's text is a bare printf template. The
  UEFI menu says `Automatischer Start in %d s` because
  "in 1 Sekunden" is wrong German for one second of every countdown.
* **The edit key.** GRUB edits an entry on `e`, syslinux on Tab, so the
  one word in the help line that names it differs. Everything else in
  that sentence is identical, and `tests/iso/test_boot_theme.py` checks
  that it stays that way.

What still has to match **line by line** is the kernel command line. The
headers of `grub/grub.cfg` and `syslinux/syslinux.cfg` say which half is
which.

### A theme that fails to load is invisible

GRUB answers a missing theme file, a missing PF2 or an undecodable
background by putting up its plain text menu. It does not log, does not
fail, does not set an exit code — the medium boots, the installer comes
up, and the brand is gone. syslinux does the same with a `splash.png` it
cannot read: the colour attributes still work, over black.

So the frames are measured rather than looked at. Three fractions,
because there are three different ways for this to go wrong and each
moves a different one — `petrol` collapses when the picture is missing,
`yellow` when nothing is themed over it, `black` when the loader fell
back to text. Measured on this machine:

| | petrol | yellow | black | |
|---|---|---|---|---|
| GRUB, themed (1280×800) | 0.923 | 0.0427 | 0.000 | passes |
| syslinux, themed (800×600) | 0.965 | 0.0170 | 0.000 | passes |
| GRUB text fallback | 0.000 | 0.0000 | 0.967 | fails |

The thresholds are 0.60 / 0.006 / 0.15. The narrowest margin of the six
readings is the UEFI menu's petrol at 1.5× its floor; the yellow sits at
2.8× and the fallback's black at 6.4× over its ceiling. The fallback row
is not hypothetical: it is the release ISO built the commit before,
measured by the same code.

### Contrast

Recomputed from the two configuration files by
`tests/iso/test_boot_theme.py`, not read off these comments:

| | | |
|---|---|---|
| `#DCEEF4` on `#0D3D47` | 9.90:1 | an entry |
| `#0D3D47` on `#FFCB00` | 7.77:1 | the selected entry, on its block |
| `#FFCB00` on `#0D3D47` | 7.77:1 | the BIOS countdown's digits |
| `#A9C6CF` on `#0D3D47` | 6.57:1 | the help line, and the countdown |
| `#33C9EE` on `#0D3D47` | 6.04:1 | the BIOS command-line marker |
| `#8FB0BA` on `#0D3D47` | 5.12:1 | a disabled entry |
| `#0096C0` on `#0D3D47` | 3.45:1 | the countdown bar — a shape, so 1.4.11's 3:1 |

The petrol is the **worst** case and not an average: everything either
loader draws lands between 38% and 92% of the height, both pictures are
deliberately flat brand colour there, and the gradient across them only
darkens. That is checked as well.

One pair failed and was moved rather than tolerated. GRUB centres a
`progress_bar`'s own text over its fill, which put `#DCEEF4` on
`#0096C0` — **2.87:1**, on the one line of the menu that changes every
second. No text colour clears 4.5:1 on both the cyan fill and the
`#214F59` trough, so the countdown is a label above the bar instead of
text inside it.

### Regenerating the assets

```bash
./iso/make-boot-theme.sh
```

The fonts and both pictures are **committed**, not built. A theme whose
font or background is missing at boot fails silently, so it must not
depend on what the build container happened to have installed that day —
and `test_boot_theme.py` can then check the name inside each PF2 against
the name `theme.txt` asks for, which is not derivable from the file name.

## How the two profiles relate

Not as two copies. The shipping profile is **assembled** at build time
out of two sources:

```
iso/shared-with-release.txt   nine files, named one by one, taken from iso/profile/
iso/profile-release/          everything else, and it wins on any collision
```

The list is an **allow-list**, and that direction is the whole point. A
deny-list gets the difference wrong by omission: the next person who
adds a file to `iso/profile/` — a second collector, a rescue autologin,
another answer file — would get it into the shipping image unless they
remembered to exclude it, and nothing about their change would look
wrong. With an allow-list the same mistake produces an image that is
*missing* something, which is a build that fails or an image that
visibly does not work, rather than an image that quietly ships a known
root password.

Shared today: `pacman.conf` (the ALA pin, so the medium installs the
system the smoke image measured), `locale.conf`, `vconsole.conf`,
`localtime`, `resolv.conf`, the `systemd-firstboot` mask, the two
mkinitcpio files and the wired-network unit. Nothing else can cross
over.

Three separate things stop the harness leaking in:

| where | what it checks |
|---|---|
| `tests/iso/test_release_profile.py` | the assembled profile: no autologin, no credential, no `ttyS0`, no collector, and nothing of `iso/profile/` that is not on the list — by *content*, so a copy under another name is still a copy |
| `tests/iso/test_smoke_profile.py::test_the_profile_says_it_is_a_test_harness` | the boundary from the other side: the harness still has its three pieces, and none of them has been copied into the shipping profile or put on the shared list |
| `iso/build.sh` | the **built root**, which is the only place a package's own autologin drop-in could appear: installer present and executable, no harness paths, no `--autologin` anywhere under `/etc`, and no account in `/etc/shadow` with a usable password |

`./iso/test-boot.py --scenario release` adds a fourth: before it boots
anything it opens the **finished ISO** — the loader configurations out of
the ISO 9660 filesystem, the root filesystem out of the squashfs inside
it — and refuses to boot an image that has any of it back.

## What it boots into

There is no login on this medium at all. `getty@tty1` is masked from the
kernel command line, `/etc/shadow` is the one the `filesystem` package
ships (root has no usable password), and `zepos-install.service` owns
tty1 directly, with `PAMName=login` so that logind gives it a seat.

`zepos-live-session` then makes three attempts, in this order, and each
one is an attempt rather than a hardware check (spec §8.5: *"Erkennung
über den tatsächlichen Startversuch, nicht über eine Hardware-Liste"*):

1. `cage` with its ordinary renderer, running `foot`, running
   `/usr/bin/zepos-install`;
2. `cage` again with `WLR_RENDERER=pixman`;
3. `zepos-install` on the console with no display variable set at all,
   where its own `choose_surface()` picks the text interface.

The installer runs inside a terminal in the first two so that a GTK4
failure *inside* a working compositor is something the user can read
rather than a blank screen.

**Why `cage` and not `zepos-hyprland`.** The installer must run as root —
`archinstall` requires it, this medium has no `sudo`, and a live user
with passwordless root would be the one credential in an image built to
carry none. Hyprland refuses to start as root; measured against the
shipped 0.56.1 binary:

```
[ ERROR ] Hyprland was launched with superuser privileges, but the
          privileges check is not omitted.
          Hint: Use the --i-am-really-stupid flag to omit that check.
```

A shipping medium whose session is started with a flag called
`--i-am-really-stupid` is not a shipping medium. `cage` is 27 KiB, needs
no configuration file, fullscreens every window and exits with its
child. ZepOS's own compositor is what gets *installed*; it has no reason
to be the thing that installs it.

## What the boot showed

Measured under QEMU/OVMF, `-vga virtio` (a KMS device with dumb buffers
and no render node), 4 GiB, KVM. Screenshots in `iso/out/run-release/`.

| when | what was on the screen |
|---|---|
| 0–10 s | the GRUB menu, `ZepOS installieren (x86_64, UEFI)` |
| ~14 s | kernel and systemd messages; no login prompt at any point |
| ~17 s | `zepos-live-prepare`: `mirrorlist pinned to 2026/08/04`, then `pacman-key --init`/`--populate` — `Locally signed 6 keys`, `Appending keys from zepos.gpg` |
| ~21 s | the GTK4 installer, fullscreen: **Sprache wählen**, *Deutsch*, `Zurück`/`Weiter` |

Driven from there with nothing but `send-key`: one Tab focuses `Weiter`,
space activates it, and the next page is **Installationsdatenträger
wählen** showing `/dev/vda (24.0 GiB)` under *Dies löscht die gesamte
Festplatte.* — the disk question, on a real enumeration of the machine
it was running on. One page further is **Benutzer**, with `Weiter`
insensitive and *Diese Angabe darf nicht leer sein.* under the empty
fields.

The wireless page is skipped, correctly: the installer's own
`wireless_step()` drops it on a machine with no wireless adapter.

**The graphical installer typed on a US keyboard.** Measured, on the
medium before the repair: `xyz-abc`, sent as the qcodes a German board
would need for it, arrived in the password field as `xzy/abc` — i.e.
every key produced what a US board produces. `/etc/vconsole.conf`'s
`KEYMAP=de` is loaded into the *kernel's* keymap by
`systemd-vconsole-setup` and governs the console — which is why the text
fallback always typed correctly — and a Wayland compositor never reads
it. wlroots builds its keymap through libxkbcommon out of the
`XKB_DEFAULT_*` variables, and nothing on this medium set any of them, so
`cage` took libxkbcommon's compiled-in default, `us`.

Why that is worse than cosmetic: a German installer asks a German user
for a password, twice, in a *masked* field. On a US layout `y` and `z`
swap, `-` `_` `/` `:` `;` `=` `+` move, and every shifted digit is a
different character. The two fields agree with each other, the
installation completes, and the account it created cannot be logged
into. Nothing anywhere reports it.

[What was done about it](#the-keyboard-follows-the-language-the-session-speaks)
is below.

**The fallback, measured rather than assumed.** Booting the same medium
with `systemd.setenv=WLR_BACKENDS=kaputt` appended in the GRUB editor —
so that both `cage` attempts fail — produced:

```
Die grafische Sitzung konnte nicht gestartet werden. ZepOS wird im Textmodus installiert.

Sprache wählen
  1) Deutsch
  2) Englisch
Auswahl: 1
```

on the console, accepting keystrokes. Booting it with `nomodeset` did
*not* reach that path: the kernel falls back to `simpledrm` on the EFI
framebuffer, `cage` comes up on that, and the graphical installer
appears anyway — which is a better outcome than the one being tested
for.

### The keyboard follows the language the session speaks

`zepos-live-session` exports `XKB_DEFAULT_LAYOUT` before `cage`, derived
from `LC_MESSAGES` — which `zepos-install.service` sets, and which is the
same value that decides which catalogue the installer opens in and which
entry its language page preselects. `de*` gives `de`, `en*` gives `us`,
and anything else gives `de`: ZepOS is a German product, and guessing
`us` for an unknown value would restore exactly the defect being removed.

**Why the language the user picks cannot decide it.** It would be the
right source and it is not reachable. `cage` reads `XKB_DEFAULT_LAYOUT`
once, when it starts, and wlroots offers no way to change a seat's keymap
afterwards; *Sprache wählen* is the installer's first page and by then
the compositor is already up. So the layout follows the session's
language, and for everybody who keeps the preselection — which is the
whole point of preselecting it — that is the language they chose.
Somebody who switches the installer to English types on a German board:
a visibly wrong layout on a screen that says so, rather than an invisibly
wrong password. That residual is
[in the open questions](#what-is-not-proven).

The console keymap stays where it was. `/etc/vconsole.conf` is on the
shared list and the text fallback has always typed correctly; both halves
are needed and neither works alone, which is what
`tests/iso/test_release_profile.py::test_the_medium_types_on_the_keyboard_it_asks_questions_in`
asserts.

**Measured, and not asserted.** `--scenario release` now types the same
string that reported the defect — `xyz-abc`, sent as German key
*positions* — into *Rechnername*, which is the first tab stop on the user
page and, unlike the four password rows, is not masked. The picture is
`iso/out/run-release/key-*-06-tastatur-xyz-abc.png`, and the string in
the field is the whole measurement: `xyz-abc` means the compositor loaded
the layout the console has, `xzy/abc` means it did not.

## What an installation from this medium showed

`./iso/test-boot.py --scenario release-install`, same machine as above,
`iso/out/release-target.img` as an empty 24 GiB disk. Screenshots land in
`iso/out/run-release-install/`, which the **next** run of that scenario
wipes — so the series this section describes was copied aside first, and
on the machine it was taken on it is in `iso/out/release-install-404/`,
with the exploration series in `iso/out/release-form-map/` and the boot
of the resulting disk in `iso/out/release-installed-leer/`. None of it is
tracked; `iso/out/` is ignored, deliberately, and a rerun reproduces it.

### Driving it

The medium carries no harness, so it is driven the way a person drives
it — `send-key` onto the emulated keyboard, `screendump` off the display
device — and the whole path is written down as a list of steps in
`test-boot.py`'s `RELEASE_INSTALL_SCRIPT`. Three things about that path
were measured and are not obvious:

* **Focus stays on `Weiter` across a page change.** The button lives in
  the toolbar; only the stack's child is swapped. So one space bar per
  page walks the form — except where the new page is invalid, which
  makes the button insensitive and drops the focus. The user page is
  exactly that case.
* **The user page has twelve tab stops, not six.** Each of the four
  password rows carries a *show the password* eye button and every one
  of them is a stop: `Rechnername`, `Benutzername`, `Passwort`, eye,
  `wiederholen`, eye, `Root-Passwort`, eye, `wiederholen`, eye,
  `Zurück`, `Weiter`. Tabbing *into* an entry selects what is in it, so
  typing replaces rather than appends.
* **The confirmation opens with `Nein` focused invisibly**, so one Tab
  moves to `Ja`. `iso/out/run-release-install/key-53-11-ja-hat-den-fokus.png`
  is that state, photographed before the space bar answered it.

### The confirmation

This is the screen nothing had ever passed:

```
                    Installation jetzt starten?
              Dies löscht die gesamte Festplatte /dev/vda.
                       [ Nein ]   [ Ja ]
```

`Ja` is styled destructive (red). Answering `Nein` was tried first, on a
separate boot, and produces the toast *Installation abgebrochen.* with
the disk untouched — so the dialog is a real gate in both directions.

### What happened after it

The erase and the partitioning are real and they worked:

```
Wiping partitions and metadata: /dev/vda
Creating partitions: /dev/vda
Starting installation...
```

and `sfdisk -J iso/out/release-target.img` afterwards shows exactly the
layout `installer/core/translate.py::_partitions` describes — a 512 MiB
EFI system partition (`C12A7328-…`) formatted `vfat`, and a Linux root
(`4F68BCE3-…`) formatted `ext4`.

Then it failed, and it failed for a reason that has nothing to do with
disks:

```
Error: failed retrieving file 'zepos.db' from zeptronit.github.io :
       The requested URL returned error: 404
error: failed to synchronize all databases (failed to retrieve some files)
...
Installation fehlgeschlagen (Exit-Code 1).
```

**Why.** `installer/core/source.py::probe()` decided where the ZepOS
packages come from by opening a socket to `archlinux.org:443`. That
answers *is there internet*, and on a machine that has internet it
returned `ONLINE`, which points the `[zepos]` repository at
`ONLINE_REPO_URL` — `https://zeptronit.github.io/ZepOS/$arch`. Nothing
has ever been published there; the constant's own comment said so.
`pacman -Syy` therefore 404s on the first file it asks for, before a
single package is installed.

The consequence was the wrong way round. The offline repository is *on
the medium*, always present and always complete, and it was chosen only
when there was **no** network — so the better the connection, the more
certain the failure. [What was done about it](#the-package-source-now-asks-the-repository)
is below, after the rest of what this run showed.

That is not read off the screenshot. It reproduces in two lines, without
QEMU, on any machine with a network:

```console
$ .venv/bin/python -c 'from installer.core.source import probe, mirror_config
print(probe(), mirror_config(probe())["custom_repositories"][0]["url"])'
PackageSource.ONLINE https://zeptronit.github.io/ZepOS/$arch

$ curl -sS -o /dev/null -w '%{http_code}\n' https://zeptronit.github.io/ZepOS/x86_64/zepos.db
404
```

**Why no previous run saw it.** The smoke image never took that
decision. `iso/profile/airootfs/usr/local/bin/zepos-install-unattended`
passed `source=PackageSource.OFFLINE` explicitly, under a comment that
said why: *"the online repository (https://zeptronit.github.io/ZepOS)
does not exist yet - nothing has ever been published to it."* That one
argument was the entire difference between `--scenario install`, which
has always passed, and `--scenario release-install`, which could not. The
shipping medium has no equivalent, and no surface offers the user a way
to choose.

The disk afterwards carries the partitions, the two filesystems and one
file — `/etc/vconsole.conf`, 32 KiB in total. Booting it with the medium
removed (`--scenario release-installed`) reaches the firmware and stops
there:

```
BdsDxe: failed to load Boot0003 "UEFI Misc Device" ... : Not Found
>>Start PXE over IPv4.
```

which is the correct behaviour for a disk whose installation died long
before `bootctl install`.

### The package source now asks the repository

Three things could have closed the 404 above:

1. publish the repository (`packaging/publish.sh`), after which `ONLINE`
   becomes a true answer;
2. have `probe()` ask the repository whose location it is deciding —
   `$ONLINE_REPO_URL/zepos.db` — instead of `archlinux.org`, so that an
   unpublished repository falls back to the medium's own the way a
   missing network already does;
3. offer the source as a question in both surfaces.

**(2) is what was done**, and it is the only one of the three that is a
correction rather than a change of plan: reachability of Arch's mirrors
was never evidence about a ZepOS repository, and no amount of publishing
would have made it so. (1) remains a thing to do and this makes it a
thing that can be done without touching any code — the day `gh-pages`
carries a database, the same `probe()` starts answering `ONLINE` by
itself. (3) is still open and is a product decision; §8.5's page list
does not have a source question in it.

What `probe()` asks now is a `HEAD` on
`https://zeptronit.github.io/ZepOS/<uname -m>/zepos.db`, with a `GET`
carrying `Range: bytes=0-0` behind it for a host that refuses `HEAD`
(GitHub Pages does not; the fallback is for the day the repository moves
somewhere that does). `$arch` is resolved before the request — it is a
pacman variable, and a literal `$arch` in a URL is a 404 of its own,
which would be indistinguishable from the answer this probe exists to
give.

Three states, and the module is now right in all of them:

| the repository is | the answer | what installs |
|---|---|---|
| published and reachable | `ONLINE` | ZepOS packages over the network |
| published, blocked or down | `OFFLINE` | ZepOS packages from the medium |
| never published — today | `OFFLINE` | ZepOS packages from the medium |

Measured on this machine, before and after, with the same two lines that
found the defect:

```console
$ .venv/bin/python -c 'from installer.core.source import probe, mirror_config
print(probe(), mirror_config(probe())["custom_repositories"][0]["url"])'
PackageSource.OFFLINE file:///opt/zepos-repo

$ curl -sS -o /dev/null -w '%{http_code}\n' https://zeptronit.github.io/ZepOS/x86_64/zepos.db
404
```

Note that `OFFLINE` is not the same as "install offline":
`mirror_config()` leaves `mirror_regions` empty either way, so the *base
system* comes over the network from the pinned ALA snapshot in both
cases. `OFFLINE` only moves the `[zepos]` repository to
`file:///opt/zepos-repo`. That combination — network present, ZepOS
packages from the medium — is precisely what the smoke image's
installation has always measured, and what it produces boots.

**And the hard-coded override is gone.** `zepos-install-unattended` now
calls `probe()` like everything else and reports the answer as
`pkgsource=` on its `RESULT` line. That is the half of this that keeps
the defect from coming back: while the smoke image passed a constant, it
took a branch the shipping medium could not take, and the two runs
measured different code in the one line that decides whether an
installation can finish at all.

The wireless step still needs the old question, and it still asks it:
`source.internet_reachable()` is the archlinux.org socket check under the
name of the thing it measures. Without that split, a user who had just
successfully joined a WLAN would be told there is no internet — because
nobody has published a package repository yet.

### How a run this long is watched

There is no progress to poll: the image reports nothing, and the log view
on the progress page does not scroll, so it stops changing once the first
screenful of `archinstall` output has filled it. What does keep changing
is the `Gtk.ProgressBar` that `_on_tick()` pulses every 250 ms off the GTK
main loop, while the installation runs on a worker thread. So
`test-boot.py::watch()` photographs the screen every 17 seconds and reads
*moving* as "the main loop is alive" and *five identical frames* as "the
tick source has been removed", which happens in exactly one place —
`_on_installation_finished()`. The sampling interval is deliberately
coprime with the five-second pulse animation; a multiple of it would
photograph the same phase every time and report a running installation as
a frozen one.

That is the completion half. The liveness half is **not** proven by this
run: the installation died fifteen seconds in, so every frame the watch
took was already still.

## Eine Installation, die durchlief, und was sie zeigte

11.08.2026. `--scenario release-install` gefolgt von
`--scenario release-installed`, dieselbe Maschine, `release-target.img`
als leere 24-GiB-Platte. Der Abschnitt darueber beschreibt den Lauf, an
dem nichts davon ging; dieser beschreibt den ersten, an dem alles ging.

**Die Installation.** "Installation erfolgreich abgeschlossen", 5,1 GiB
auf der Zielplatte. Das Protokoll dazu liegt danach IM ZIEL, unter
`/var/log/archinstall/install.log`, und ist ohne root zu lesen:

```console
$ dd if=iso/out/release-target.img of=/var/tmp/root.img bs=1M skip=513 conv=sparse
$ debugfs -R "cat /var/log/archinstall/install.log" /var/tmp/root.img
```

513 ist der Anfang der Wurzelpartition in MiB (`parted -s <img> unit B
print`), und `conv=sparse` haelt die Kopie bei den 5 GiB, die wirklich
belegt sind. Das ist der Weg, auf dem der Lauf DAVOR seinen Abbruch
erklaert hat - `Failed to enable unit: Unit greetd.service does not
exist`, weil `zepos-desktop` aus einem aelteren Baum stammte. Seitdem
prueft `packaging/check-current.py` auch die Abhaengigkeitsliste des
Meta-Pakets.

**Das Startmenue der Installation** ist das ZepOS-Menue, und das ist
nicht nur angesehen, sondern gemessen: `grade_boot_menu()` misst die
Bilder der ersten zwanzig Sekunden mit derselben Palette wie beim
Medium.

```
screen-0005s.png   1280x800  petrol 0.920  yellow 0.0609  black 0.000  THEMED
```

Die `grub.cfg` auf der EFI-Partition traegt, was `grub-mkconfig` aus
`/etc/default/grub.d/10-zepos.cfg` gemacht hat:

```
terminal_output gfxterm
insmod gfxmenu
loadfont ($root)/usr/share/grub/themes/zepos/f/roboto-16.pf2
loadfont ($root)/usr/share/grub/themes/zepos/f/roboto-24.pf2
loadfont ($root)/usr/share/grub/themes/zepos/f/roboto-bold-24.pf2
set theme=($root)/usr/share/grub/themes/zepos/theme.txt
```

Die drei `loadfont`-Zeilen sind der Grund, aus dem die Schriften im
Paket unter `f/` liegen und nicht neben dem Thema wie in diesem Profil:
`/etc/grub.d/00_header` sucht nur in `"$themedir"/*.pf2` und
`"$themedir"/f/*.pf2`.

**Die Anmeldung.** Neunzig Sekunden nach dem Einschalten steht die
GTK4-Maske von ReGreet auf dem ZepOS-Hintergrund: "Willkommen bei
ZepOS", `User: tester`, `Session: ZepOS`. Genau eine Sitzung in der
Liste - `zepos-hyprland` liefert Hyprlands eigene Eintraege nicht mehr
aus, weil ReGreet die Sitzungen in einer HashMap haelt und die
Vorauswahl damit bei jedem Start eine andere waere.

Drei Tastendruecke fuehren hindurch: Eingabetaste (ReGreet setzt den
Anmeldeknopf als default widget), Passwort, Eingabetaste.

**Die Sitzung** steht dreissig Sekunden spaeter: Waybar oben mit
Arbeitsflaechen, Uhr, Adresse und Lautstaerke, darunter das
ZeptronIT-Bild. Die erste Anmeldung erzeugt dabei die ganze
Konfiguration - `zepos-session` ruft `zepos-generate --all`, weil
`zepos-config` nur `/etc/skel/.config/zepos/user-settings.json` anlegt
und alles andere einem Benutzer gehoert, den es zur Bauzeit nicht gab.

### Was an dieser Anmeldung noch nicht ZepOS ist

* **ReGreet spricht Englisch.** "User", "Session", "Login", "Cancel",
  "Reboot", "Power Off" stehen so im Programm; es bringt keine
  Uebersetzung mit und liest keine. Der Installer daneben ist deutsch.
* **Die Maske traegt libadwaita-Grau, nicht das Petrol der Marke.**
  Geteilt sind das Hintergrundbild und Roboto - das Stylesheet des
  Installers steht als Python-Zeichenkette in
  `installer/gui/branding.py`, gehoert dem Paket `zepos-installer` und
  ist auf einer Installation gar nicht da. Eine Kopie waere eine zweite
  Definition der Marke. `regreet -s <datei>` nimmt eigenes CSS, und
  damit waere es zu schliessen - als eigene Aufgabe, mit einer Quelle
  fuer beide Seiten.
* **Die erste Anmeldung zeigt eine halbe Minute nichts.**
  `zepos-generate --all` laeuft, bevor der Compositor startet, und der
  Greeter ist zu diesem Zeitpunkt schon weg.

## Secure Boot: was genau abgelehnt wird

Gemessen am 11.08.2026 mit `./iso/test-boot.py --scenario secure-boot`,
gegen `zepos-2026.08.11-x86_64.iso`.

**Die billige Haelfte.** `./iso/secureboot.py inspect` liest die
PE-Signaturtabelle jeder Stufe der Startkette aus dem gebauten Medium.
Das ist genau das Feld, das eine Firmware mit Secure Boot prueft
(`IMAGE_DIRECTORY_ENTRY_SECURITY`, der fuenfte Eintrag des Data
Directory, und der einzige, dessen erstes Feld ein Dateioffset ist statt
einer virtuellen Adresse):

```
EFI/BOOT/BOOTx64.EFI                 7712768 Byte  OHNE SIGNATUR
EFI/BOOT/BOOTIA32.EFI                6238208 Byte  OHNE SIGNATUR
zepos/boot/x86_64/vmlinuz-linux     17089024 Byte  OHNE SIGNATUR
```

Alle drei stehen auf 0/0. Es gibt also nichts, was eine Firmware pruefen
koennte — das ist die ganze Antwort auf "was wird abgelehnt".

**Die teure Haelfte, und warum sie eine Gegenprobe braucht.** "Das Medium
startet nicht" ist fuer sich keine Aussage ueber Secure Boot. Das
Szenario faehrt deshalb zwei Maschinen, die sich in genau einer Datei
unterscheiden — dem Variablenspeicher —, und zwar mit
`OVMF_CODE.secboot.4m.fd`, `-machine q35,smm=on` und
`-global driver=cfi.pflash01,property=secure,value=on`:

| Variablenspeicher | Zustand | Startmenue |
|---|---|---|
| `OVMF_VARS.4m.fd`, wie Arch ihn ausliefert | Setup Mode — die Firmware prueft nichts | **ja**, petrol 0,965 / gelb 0,0167 |
| derselbe, mit Plattformschluessel darin | User Mode — die Firmware prueft | **nein**, schwarz 0,979 |

Was auf dem Schirm der zweiten Maschine steht, wortwoertlich:

```
BdsDxe: loading Boot0002 "UEFI QEMU DVD-ROM QM00005 " from PciRoot(0x0)/Pci(0x1F,0x2)/Sata(0x2,0xFFFF,0x0)
BdsDxe: failed to load Boot0002 "UEFI QEMU DVD-ROM QM00005 " from PciRoot(0x0)/Pci(0x1F,0x2)/Sata(0x2,0xFFFF,0x0) : Access Denied -- rejected probably by Secure Boot
>>Start PXE over IPv4.
```

Abgelehnt wird `\EFI\BOOT\BOOTx64.EFI`, mit `Access Denied`, bevor eine
Zeile ZepOS laeuft. Danach faellt die Firmware auf den Netzwerkstart
durch — ein Nutzer sieht also nicht einmal eine Fehlermeldung, die nach
ZepOS aussieht.

**Warum der Variablenspeicher hier gebaut wird.** Arch liefert die
Firmware, die Secure Boot kann, aber keinen Speicher mit Schluesseln
darin. Ohne Plattformschluessel steht OVMF im Setup Mode und prueft
nichts — ein Lauf gegen die ausgelieferte Vorlage haette gemeldet, dass
das Medium unter Secure Boot startet. Fedora liefert dafuer
`EnrollDefaultKeys.efi`, Arch nicht; `virt-firmware` ist hier nicht
installiert. `iso/secureboot.py` schreibt PK, KEK und db deshalb selbst
in den Speicher (edk2, `MdeModulePkg/Include/Guid/VariableFormat.h`), und
`tests/iso/test_secure_boot.py` liest sie zurueck — der eine Fehler, den
kein QEMU-Lauf als Fehler zeigen wuerde.

### Die drei Wege, und was jeder einen Nutzer kostet

Der Fall, der zaehlt, ist der Nutzer, der die Firmware **nicht**
umstellen will.

| Weg | Was er verlangt | Fuer diesen Nutzer |
|---|---|---|
| **shim, von Microsoft signiert** | Ein shim-Bau durch das oeffentliche `shim-review`, ein CA-tauglich verwahrter Schluessel, ein GRUB mit dem eingeschraenkten Modulsatz, und Microsofts Signatur darauf. Wochen bis Monate, und der Schluessel muss danach so verwahrt bleiben, wie es im Antrag steht. | **Der einzige Weg, der ohne jede Handlung des Nutzers funktioniert** — vorausgesetzt, unser Zertifikat ist im shim eingebaut, den Microsoft signiert hat. |
| **shim eines anderen plus MOK** | Kein eigener Antrag; der Nutzer bestaetigt unser Zertifikat einmal im blauen MokManager-Schirm. | Die Firmware bleibt unangetastet, aber die erste Inbetriebnahme hat einen Schritt, den niemand erwartet und der auf Englisch stattfindet. Und die Weitergabe eines fremden signierten shim ist eine Lizenzfrage, keine technische. |
| **eigener Schluessel in die Firmware** (`sbctl`, `KeyTool`, das Setup-Menue) | Der Nutzer geht ins Firmware-Menue, setzt Secure Boot in den Setup Mode und traegt unseren Schluessel ein. | **Faellt fuer diesen Nutzer aus.** Ausserdem betrifft es nur das INSTALLIERTE System: die Binaerdateien auf dem Medium liegen auf einem Nur-Lese-Datentraeger und lassen sich nachtraeglich nicht signieren. |

Der Messaufbau steht fuer beide Richtungen bereit: `iso/out/`
`secboot-platform.key` ist der Schluessel, dessen Zertifikat in der db
der zweiten Maschine steht. Eine Kette, die mit ihm signiert waere, muss
dort durchkommen — das ist die Gegenprobe, die den Erfolg messbar macht,
sobald es etwas zu signieren gibt.

## Der BIOS-Startweg, gemessen

`./iso/test-bios-chain.py`, am 11.08.2026.

**Was der Lauf tut.** Er baut eine 6-GiB-Platte mit genau der Einteilung,
die `installer.core.layout.suggested_layout()` vorschlaegt — dieselbe
Funktion, aus der `translate.py` die archinstall-Konfiguration macht —,
als **MBR**, pacstrapt `base linux grub` vom angehefteten
ALA-Schnappschuss und ruft `grub-install --target=i386-pc --recheck` auf
das Elterngeraet. Dann startet er das Ergebnis unter SeaBIOS, also auf
einer QEMU-Maschine ohne Firmware-Flash.

```
Einteilung  1+512 MiB fat32 /boot [boot,esp] | 513+5630 MiB ext4 / [-]
core.img: 61577 Byte ungleich null in der Luecke
was im MBR steht: 55 aa

GRUB       JA   'GNU GRUB  version'
Wurzel     JA   'Multi-User System'
Kernel     JA   'Arch Linux 7.1.5-arch1-2 (ttyS0)'
Anmeldung  JA   'login:'
```

Damit sind zwei Saetze erledigt, die bis heute in
`installer/core/firmware.py` standen: "kein Lauf hat je" und
"`grub-install --target=i386-pc` ist in diesem Projekt noch nie
gelaufen". Der dritte — der GPT-Einwand — ebenfalls, aber durch Lesen:
die Tabellenart faellt in archinstall an einer Stelle,
`DeviceHandler.__init__` setzt sie auf `PartitionTable.default()`, und
die gibt MBR zurueck, wenn `SysInfo.has_uefi()` falsch ist (4.4,
`lib/disk/device_handler.py` Zeile 47). Auf einer BIOS-Maschine entsteht
also keine GPT-Platte, und die Frage nach einer BIOS-Boot-Partition
stellt sich dort nicht.

**Was der Lauf NICHT beantwortet, und warum die Ablehnung bleibt.** Hier
partitioniert ein Skript, nicht der Installer. Zwischen "GRUB startet
diese Einteilung" und "eine Installation baut sie" liegt archinstalls
eigener Weg, und der ist gelesen und nicht gefahren. Der Unterschied
zwischen den beiden ist genau die Stelle, an der eine Platte geloescht
wird.

**Was ein BIOS-Nutzer heute sieht**, fotografiert mit
`./iso/test-boot.py --scenario release --firmware bios`: das gethemte
syslinux-Menue (800x600, petrol 0,965), danach der grafische Installer,
und auf dessen erster Seite in Rot der Satz aus `firmware.py` — auf
Deutsch, weil die Sprache schon gewaehlt ist. Kein schwarzer Schirm und
keine Loeschung.

## "Offline installieren": was es kostet, und was es heute ist

**Was `offline` heute bedeutet.** Zwei verschiedene Dinge, und keines von
beiden ist "ohne Netz":

* archinstalls `--offline` (4.4, nachgelesen an der Fassung auf dem
  Medium) ueberspringt drei Dinge: das Warten auf `reflector`
  (`_verify_service_stop`), den Erreichbarkeitstest samt WLAN-Behandlung
  in `main.py` Zeile 143, und das Holen der Spiegelliste von
  archlinux.org (`MirrorListHandler.load_mirrors`). Woher `pacstrap` die
  Pakete nimmt, aendert keines davon.
* ZepOS' `PackageSource.OFFLINE` verschiebt allein das
  `[zepos]`-Repository auf `file:///opt/zepos-repo`. Der Kopf von
  `installer/core/source.py` sagt das selbst.

Die Arch-Basis kommt in beiden Faellen ueber das Netz vom angehefteten
ALA-Schnappschuss. Eine Installation ohne Netz gibt es heute nicht.

**Was das Medium mitbringen muesste.** Gemessen am 11.08.2026, gegen den
angehefteten Schnappschuss 2026/08/04 und das `[zepos]`-Repository aus
`packaging/out/`, mit der Paketliste, die archinstall wirklich
installiert (`base sudo linux-firmware mkinitcpio linux` aus
`installer.py` Zeile 69, die Mikrocode-Pakete, `grub`, `efibootmgr`,
`networkmanager` und `zepos-desktop`):

| | |
|---|---|
| Pakete in der Schliessung | **390** |
| Herunterzuladen, komprimiert | **1 061 018 061 Byte** = 0,988 GiB |
| Davon liegt schon auf dem Medium (`/opt/zepos-repo`) | 60 208 248 Byte, 46 Pakete |
| Installiert | 2,528 GiB |
| Medium heute | 1 231 060 992 Byte |
| Medium mit allem darauf | **rund 2,23 GB** |

**Die Entscheidung: die Groesse ist nicht das Hindernis.** 2,23 GB ist
fuer ein Installationsmedium gewoehnlich, und das ist nachgemessen statt
erinnert: `Fedora-Workstation-Live-43-1.6.x86_64.iso` antwortet am
11.08.2026 mit `Content-Length: 2742190080`, also 2,74 GB — ein ZepOS
mit allem darauf waere kleiner als das. Was dagegen steht, ist nicht ein
halbes Gigabyte, sondern dass es nicht
eine Aenderung ist, sondern vier — die Pakete und eine `pacman`-Datenbank
ins Abbild, `[core]`/`[extra]` im Ziel auf das Medium umgebogen,
`mirror_config()` entsprechend, und danach die Umkehrung im installierten
System, damit `pacman -Syu` nicht auf ein abgezogenes Medium zeigt. Der
letzte Punkt ist derselbe, den Spec §8.5b fuer `[zepos]` schon einmal
beschreiben musste, und dort hat er eine Installation gekostet.

Bis das gebaut und gemessen ist, gilt: **ZepOS installiert nicht ohne
Netz.** Spec §1, §2 und §8.4 versprachen das Gegenteil; die drei Stellen
sind am 11.08.2026 richtiggestellt worden.

## What is not proven

* ~~No installation from this medium has ever completed~~ — seit dem
  11.08.2026 nicht mehr wahr, siehe
  [Eine Installation, die durchlief](#eine-installation-die-durchlief-und-was-sie-zeigte).
  Der Satz bleibt hier stehen, weil der Abschnitt darueber den Lauf
  beschreibt, an dem er wahr war.
* **No real hardware.** Everything above is QEMU with a virtio GPU and a
  virtio disk. `linux-firmware` is in the image for the machines this
  cannot speak for.
* **The graphical failure was forced with an environment variable**, not
  by a GPU that genuinely cannot do it. Removing the DRM device
  altogether also removes the framebuffer the observation happens on —
  a boot with `modprobe.blacklist=virtio_gpu
  initcall_blacklist=simpledrm_platform_driver_init` produces a black
  screen and nothing to photograph.
* **A user who switches the installer to English keeps the German
  keyboard.** The layout is decided before the compositor starts and
  wlroots cannot change a seat's keymap afterwards; the language page
  runs inside that compositor. Closing it needs either a layout question
  of its own on the language page, or a session that restarts `cage`
  when the language changes — which would throw away everything typed so
  far. Neither is a repair to make while measuring the other two.
