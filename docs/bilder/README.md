# The pictures in the two READMEs

Nine screenshots of the ZepOS desktop. This file says where they live, why they
live there and not here, how they are made, what was deliberately kept out of
frame, and what each one is evidence of.

Made **24.08.2026** from commit `54269d9` (`VERSION` 0.1.9, the same commit the
published repository was built from).

---

## Where they are, and what that costs

The image files are **not committed to `main`**. `CONTRIBUTING.md` says so in as
many words — *"Screenshots. `out/` is gitignored. What an image shows belongs in
a report; the image itself does not belong in the history of a branch"* — and
the reason is arithmetic: this repository already carries two package blobs over
50 MB and is close enough to GitHub's limits to care. One set of screenshots is
about 1.3 MB; a set per revision, forever, is how a repository becomes slow to
clone for everyone who never wanted the pictures.

They live on an **orphan branch called `bilder`**: a branch with no parent
commit, holding nothing but the images, *replaced* rather than extended every
time they are remade. The two READMEs link into it by raw URL:

```
https://raw.githubusercontent.com/ZeptronIT/ZepOS/bilder/schreibtisch.webp
```

**What that buys.** `main`'s history stays free of binaries, so `git log`,
`git bisect` and a shallow clone are unaffected. Because the branch is replaced
and not extended, its old commits become unreachable, and unreachable objects
are not sent to a client — so a clone carries **one** set of pictures, never the
history of all of them.

**What it costs, named honestly:**

- A plain `git clone` still fetches every branch, so it carries today's 1.3 MB
  even for someone who only wants the code. `--single-branch` avoids it.
- Replacing the branch needs `git push --force`. That is a destructive verb and
  it must never be aimed anywhere else. See the commands below.
- The pictures are **not versioned with the code**. A README read at an old
  commit shows today's pictures. For a beta whose screenshots are meant to show
  what it looks like *now*, that is the intended trade — but it is a trade, and
  it is the reason every picture below carries the commit it was taken from.
- `raw.githubusercontent.com` renders on github.com (through GitHub's image
  proxy). It does not render in a local Markdown preview or on a mirror that is
  not GitHub.

**What was considered and rejected.** `docs/bilder/` committed on `main` is
exactly what `CONTRIBUTING.md` forbids, and it accumulates. Release attachments
cost a clone nothing at all — the better answer on that one axis — but they need
a release to exist for every revision of the pictures, the link dies with the
release, and they cannot be produced from a checkout without an upload token.

---

## The pictures

| File | Size | What it is evidence of |
|---|---|---|
| `schreibtisch.webp` | 1920×1080 | The whole desktop: bar with all its modules on top, the Home with its application icons behind everything, the dock and the two corner buttons at the bottom. Head and foot in **one** picture, because "both are the same height and have the same margin" is a claim a number can make and a picture can show. |
| `dateien.webp` | 1920×1080 | The same desktop **in use**: the file manager open on the home folder, the bar above it, the dock below with the running window marked. |
| `kontrollzentrum.webp` | 1920×1080 | The control centre — one window, a sidebar with two groups and six pages. |
| `sitzungsmenue.webp` | 1920×1080 | The session menu on `SUPER+M`: six actions, each with its own letter key. |
| `kalender.webp` | 1920×1080 | The calendar overlay, opened from the date module at the left end of the bar. Note that the bar's clock and the calendar agree — see "the clock is real" below. |
| `einstellungen.webp` | 1920×1080 | The settings window on its colours page, in the dark theme ZepOS generates for foreign GTK4 windows. |
| `schreibtisch-1366.webp` | 1366×768 | The same desktop on the commonest notebook screen. Three status modules are folded behind the collapse button. |
| `leiste.webp` | 1920×124 | The bar alone, cropped with its lower edge, so the edge is part of the picture. |
| `dock.webp` | 433×124 | The dock alone, with wallpaper around it, so the glass has something to be transparent against. |

The two crops are not linked from the READMEs, so here they are:

![The bar alone, cropped with its lower edge](https://raw.githubusercontent.com/ZeptronIT/ZepOS/bilder/leiste.webp)

![The dock alone, with wallpaper around it](https://raw.githubusercontent.com/ZeptronIT/ZepOS/bilder/dock.webp)

All nine are **lossless WebP**: `magick <in>.png -strip -define
webp:lossless=true <out>.webp`, verified pixel for pixel with
`magick compare -metric AE`, which returned `0` for every one. About 40 % of the
PNG bytes, not one pixel different. 1.3 MB for the set.

---

## How they are made

`tests/render/desktop_session.py` starts a **second Hyprland inside the running
one**, gives it a headless output of exactly the size asked for, puts the
shipped wallpaper behind it, builds the AGS shell out of the templates of the
working tree, and takes the picture with `grim` over `wlr-screencopy`. The head
of that file explains why it is a nested compositor and not a `Gsk` renderer:
layer-shell placement, blur and the wallpaper behind the glass are all
properties of the compositor, and a widget tree rendered to a texture has none
of them.

**The size is a real size.** The nested compositor's Wayland-backend output is
whatever the host window happens to be — measured once at 931×521, which is not
a screen format at all. `Session._add_headless_output()` therefore creates a
*headless* output and sets its mode explicitly, and asserts afterwards that
`hyprctl` reports the size that was asked for. The published files were then
measured again with `magick identify`: 1920×1080 and 1366×768, both 16:9.

**Safety.** Every child process runs through `refuse_the_real_session()`, which
asserts that `XDG_RUNTIME_DIR` and `WAYLAND_DISPLAY` point somewhere other than
the session of the person who started the run. `HOME` and every `XDG_*` root is
a throwaway directory under `/tmp`, the D-Bus **session** bus is one this run
started itself, and nothing is ever killed by pattern — only the child
processes this class started, in reverse order. `src/generate_config.sh` is
never run: it ends a run by stopping the running shell, which would reach the
processes of whoever is sitting at the machine.

### The three departures from `tests/render/shoot.py`, and why

`shoot.py` makes the *measurement* pictures. These are presentation pictures,
and they differ in three ways, each of which makes them **more** faithful to an
installation, not less:

1. **The pointer is invisible** (`hyprctl keyword cursor:invisible true`, the
   same line `tests/render/test_schale_stil.py` uses). A mouse arrow on a
   presentation picture is an artefact of the rig.
2. **The clock is real.** `shoot.py` feeds the bar's date module a frozen string
   (`Di 12.08.2026 14:07`). That is right for a measurement and wrong here: the
   calendar window beside it shows the machine's own date, and the two would
   contradict each other in a single picture — a defect that exists on no
   installation. The stub was replaced with `date` in the format
   `src/templates/date-config.template` uses, so bar and calendar agree.
3. **The Home shows the applications this machine actually has.** ZepOS ships a
   Home with 15 applications on it (`src/apps.py`, read from
   `packaging/zepos-apps/PKGBUILD`). Seven of them are not installed on the
   machine that took these pictures, and the Home draws a placeholder for each —
   seven broken icons that exist on no ZepOS installation, where all 15 are
   installed. `home.icons` was therefore set to the seven that resolve here
   (`firefox`, `nautilus`, `file-roller`, `baobab`, `kitty`, `btop`, `cups`).
   That is an ordinary user setting, written through the ordinary settings file,
   and the picture is a real render of it.

The eleven other bar modules keep the stubs from
`desktop_session.module_payloads()`; the head of that function records, module
by module, which template each line was read out of.

For the settings window and the file manager, two more generated files are
written into the throwaway home first: `gtk-4.0/settings.ini` and
`gtk-4.0/gtk.css`, from `gtk4-settings-config.template` and
`gtk4-colors-config.template`, exactly where `generate_config.sh` puts them
(lines 1540 and 1548). Without them a foreign GTK4 window draws in GTK's
built-in *light* theme — white cards in a dark desktop, which is the
"[the test rig has no GTK theme](../../README.md#rough-edges-named-one-at-a-time)"
limit showing itself. For the file manager, `xdg-user-dirs-update` runs as well:
that is the same program that creates Documents, Pictures and the rest at a real
first login, so the folders in the picture are the folders a fresh account has.

---

## Nothing personal is in them, and this is how that was checked

1. **Structurally.** Nothing in the picture can reach the developer's home:
   `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME` and
   `DBUS_SESSION_BUS_ADDRESS` all point into a throwaway `/tmp` directory that is
   deleted at the end, and `refuse_the_real_session()` checks it before every
   child process.
2. **By omission, deliberately.** The **network** and **Bluetooth** pages of the
   control centre, and the **disk** and **battery** overlays, were not
   photographed. Those four talk to the real `NetworkManager`, `bluetoothd` and
   the real block devices over the **system** bus, which this rig does not
   redirect, and they would show network names, device names and disks. The
   general page was checked in the picture itself: `Not connected`, `VPN: off`,
   `Bluetooth` — no name anywhere.
3. **By reading every picture.** Each one was opened at full resolution and
   every readable string listed. None of them is the account name, the host
   name, a path under a real home directory, a network name, a device name, a
   serial number or an address. What is readable is: application labels that
   exist on any Linux (Firefox, Files, Archive Manager, Disk Usage, kitty,
   btop++, Print Settings), the standard XDG folder names, the interface's own
   German strings, and the date and time of the run — a timestamp, not an
   identifier.
4. **Metadata.** `grim` writes no `tEXt` or EXIF chunk, and the WebP conversion
   runs `-strip` regardless.

---

## Remaking them

The two drivers that made this set are not in the tree — they are twenty lines
each on top of `tests/render/desktop_session.py`, and `tests/render/` belongs to
the tests. What is reproducible without them:

```bash
.venv/bin/python -m tests.render.shoot --out out/render     # bar, dock, desktop, calendar,
                                                            # control centre, at 1920 and 1366
.venv/bin/python tests/render/settings_shot.py --out out/render   # the settings window
```

This needs `Hyprland`, `hyprctl`, `ags`, `grim`, `swaybg` and `dbus-daemon`, and
a running Wayland session to nest inside. `required_tools()` names whichever is
missing.

Convert what came out, checking that the conversion changed nothing:

```bash
for f in out/render/*.png; do
    magick "$f" -strip -define webp:lossless=true "docs/bilder/$(basename "${f%.png}").webp"
    magick compare -metric AE "$f" "docs/bilder/$(basename "${f%.png}").webp" null:   # must print 0
done
```

Then build the orphan commit. This uses a **second index file**, so `main`'s
index and the working tree are never touched and nothing can be committed to
`main` by accident:

```bash
export GIT_INDEX_FILE=$(mktemp -u /tmp/zepidx-XXXX)
git read-tree --empty
for f in docs/bilder/*.webp; do
    git update-index --add --cacheinfo 100644,"$(git hash-object -w "$f")","$(basename "$f")"
done
git update-index --add --cacheinfo 100644,"$(git hash-object -w docs/bilder/branch-readme.md)",README.md
tree=$(git write-tree)
commit=$(git commit-tree "$tree" -m "bilder: <what changed>, tree <short sha>")   # no -p: orphan
git update-ref refs/heads/bilder "$commit"
unset GIT_INDEX_FILE
git ls-tree -l refs/heads/bilder      # look at it before it leaves the machine
```

`git commit-tree` without `-p` is what makes the commit an orphan, and that is
the whole mechanism: every republish is a new root commit, so the branch never
grows a history.

Finally — **note the `--force`, and note that it is aimed at `bilder` and at
nothing else:**

```bash
git push --force origin bilder
```

---

## What is not here, and why

- **No video.** It was asked for and it is not possible from this rig today, for
  three separate reasons: there is no screen recorder for `wlr-screencopy` on
  this machine (`wf-recorder` is not installed, and `grim` in a loop is a
  stuttering few frames a second); there is no tool that can synthesise a
  **pointer** click into a Wayland session here (`ydotool`, `wlrctl` and
  `dotool` are all absent, only `wtype` for the keyboard); and the nested
  compositor deliberately runs *without* ZepOS' key bindings, so a demonstration
  driven by `SUPER+E` would first need the generated Hyprland configuration in
  the throwaway session — a change to `tests/render/`. `dateien.webp` is the
  still that answers the same question.
- **No picture of the launcher.** `hyprlaunch` is fetched and patched at build
  time from a pinned upstream commit and is not installed on the machine that
  took these pictures; `tests/render/test_launcher_menue.py` compiles it for its
  own run, which is a build, not a screenshot.
- **No picture of the shortcut overview.** It reads the key bindings by running
  `keybinds.py` against the *generated* configuration, which the throwaway
  session does not have. The window opens and is empty — a defect of the rig,
  not of ZepOS, so it is not published.
- **No picture of the installer or the login screen.** `tests/render/greeter_shot.py`
  and `iso/test-boot.py` cover those; they need QEMU and a built medium.

---

## One trap worth knowing

`tests/src/test_inventory.py` scans the **whole tree** — `docs/` included — for
names that must not survive from the project ZepOS was extracted from, and
`tests/origin_data.py` skips `.png`, `.jpg` and `.gif` by suffix but **not**
`.webp`. The pictures here are therefore read as if they were text. It passes
today (checked 24.08.2026, `16 passed`), and the failure mode if it ever does
not is a false positive on compressed bytes, not a real find —
`tests/render/shoot.py` records the same thing happening once to a 1.7 MB
bundle. The clean fix is one entry in `SKIP_SUFFIXES`.
