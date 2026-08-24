# The pictures in the two READMEs

27 files, **2 058 966 bytes — 1.96 MiB** in total, lossless WebP, taken on
**24.08.2026** from `4a1d8f0` unless the table below says otherwise.

Every one of them is a screenshot of a program in this tree, running in a real
compositor. None is a mock-up, a composite, or retouched. What each one needed
in order to be *faithful* is written down below, because a picture whose setup
is undocumented is a claim, not evidence.

---

## Where they are, and why that changed

They are **committed to `main`, in this directory**, and both READMEs reference
them by **relative path** (`docs/bilder/<name>.webp`).

Until 24.08.2026 they lived on an orphan branch called `bilder`, and the two
READMEs linked to `raw.githubusercontent.com`. That was given up for two
reasons, both about how the project *looks* to somebody who arrives at it:

- GitHub shows a **"`bilder` had recent pushes"** banner on the repository
  front page, with an invitation to open a pull request against a branch that
  holds nothing but binaries. On a project trying to look trustworthy, that is
  the wrong first impression.
- An absolute `raw.githubusercontent` URL renders on github.com and **nowhere
  else** — not in a clone, not in an editor's preview, not on a mirror, not in
  the file you are reading right now. A relative path renders everywhere. That
  is a gain, not a concession.

`CONTRIBUTING.md` says screenshots do not belong in the history of a branch.
That rule is about **measurement screenshots** — the evidence a test run
produces, stale the day after, belonging in `out/`. Showcase pictures are a
different thing, and the rule now says so explicitly, in the same list.

### The price, named

**Every replaced picture stays in the history forever.** 1.96 MiB is what a
clone carries today; a second full set makes it 3.9, a third 5.9. There is no
taking one back out short of rewriting history.

That is why:

- there is **one file per element and no second, smaller copy** as a thumbnail.
  The READMEs scale with `<img width="…">`, so the repository stores each
  picture exactly once and the browser does the resizing.
- everything that is not a whole desktop is **cropped to the element it shows**.
  The calendar is 552×596 and 88 kB, not 1920×1080 and 400 kB. Nine of the
  crops are under 20 kB.
- a picture is remade when it is **wrong**, not when it could be nicer.

---

## The 27 pictures

| File | Size | Bytes | What is on it |
|---|---|---:|---|
| `schreibtisch.webp` | 1920×1080 | 191 324 | the whole desktop: bar, Home with seven icons, dock, both corner buttons |
| `starter.webp` | 1920×1080 | 215 578 | the same desktop with the **application launcher** open |
| `dateien.webp` | 1920×1080 | 68 642 | the same desktop **in use**: file manager open, dock marking the running window |
| `schreibtisch-1366.webp` | 1366×768 | 158 064 | the same desktop on a notebook screen |
| `leiste.webp` | 1920×84 | 29 624 | the bar alone, cropped to its own layer geometry |
| `dock.webp` | 441×128 | 14 812 | the dock alone, with wallpaper around it |
| `dock-minimiert.webp` | 499×128 | 16 644 | the same dock with **one minimised window** right of the divider |
| `kontrollzentrum.webp` | 936×596 | 129 538 | the control centre: sidebar, two groups, six pages |
| `tastenkuerzel.webp` | 936×596 | 141 126 | the shortcut list, filled from the generated keybindings |
| `sitzungsmenue.webp` | 667×381 | 41 894 | the session menu, six actions with letter keys |
| `kalender.webp` | 552×596 | 88 252 | the calendar overlay |
| `stil-editor.webp` | 528×596 | 78 658 | the style editor, colours tab |
| `einstellungsfenster.webp` | 936×596 | 173 554 | the shell's own settings window, size page |
| `einstellungen-app.webp` | 1920×1004 | 59 742 | `zepos-settings-gui`, the separate application, colours page |
| `vpn-einstellungen.webp` | 716×596 | 95 686 | the VPN settings, four tabs |
| `benachrichtigung.webp` | 505×206 | 19 368 | a notification arriving, top right |
| `benachrichtigungszentrum.webp` | 556×596 | 64 638 | the notification centre with the do-not-disturb switch |
| `home-menue-symbol.webp` | 343×335 | 17 796 | right-click on a Home **icon** |
| `home-menue-flaeche.webp` | 417×341 | 18 754 | right-click on the **empty Home surface** |
| `dock-menue.webp` | 343×311 | 14 070 | right-click in the dock |
| `starter-menue.webp` | 367×155 | 14 478 | right-click in the launcher (`43b8b25`) |
| `auswahlfenster.webp` | 1920×1004 | 65 012 | `zepos-menu`, the picker every list goes through |
| `sperrbildschirm.webp` | 1920×780 | 59 130 | `zepos-lock` — see its own section below |
| `installer-sprache.webp` | 1280×800 | 66 362 | installer, step 1 of 8 |
| `installer-einteilung.webp` | 1280×800 | 85 062 | installer, step 3 — laying out the disk |
| `installer-bestaetigung.webp` | 1280×800 | 70 998 | installer, step 8 — the last question |
| `installer-fertig.webp` | 1280×800 | 60 160 | installer, finished, package log behind it |

**The four installer pictures are older and from somewhere else.** They were
taken on **17.08.2026** by `./iso/test-boot.py --scenario release-install`, in
QEMU, off the release medium — which is why the version stamp along their
bottom edge says `ZepOS 2026.08.17 824b70b`. That is honest and both READMEs
say it. The installer does not run in the nested compositor: it wants a whole
machine and a disk to erase.

---

## How the other 23 are made

`tests/render/desktop_session.py` builds the configuration with the **real**
template processor, bundles the shell with `ags bundle`, starts a **Hyprland
inside Hyprland** with a headless output at the requested size, and takes the
picture with `grim`, naming that output. The scripts that drive it live in the
scratchpad of the session that made them; `tests/render/` was read and reused,
never modified.

Sizes are an argument to `Session(width, height)`, not a constant:
`_add_headless_output()` creates the output, sets its mode, and asks `hyprctl`
back whether the size arrived. `magick identify` on the stored files says
1920×1080 and 1366×768 — exactly 16:9, both of them.

### What the throwaway HOME is given first, and why each is necessary

Six things, each of which is on a real installation anyway. Without them the
picture would show a defect of the test rig and not of the system:

| Put there | Otherwise |
|---|---|
| `~/.config/gtk-4.0/settings.ini` + `gtk.css` + `kdeglobals` | every foreign GTK4 window draws in GTK's built-in **light** theme — white tiles in the middle of a dark desktop |
| `~/.local/bin/wallpaper-manager` | the wallpaper selector has nothing to call |
| `zepos-settings-gui` on `PATH`, from `settings/bin/` of this checkout | the settings window says "widget not found" — the package is not installed on a developer machine |
| `$XDG_CONFIG_HOME/hypr/hyprland.conf` + `plugins.conf` + `hyprland-failsafe.conf` | **the shortcut list is empty.** `src/keybinds.py` reads exactly those three, and the nested compositor drives on a different, minimal file in its private runtime directory |
| `~/.config/zepos-menu/style.css` + `config` | `zepos-menu` draws black on white in the built-in theme — the first attempt looked like that and was thrown away |
| `xdg-user-dirs-update` | the file manager looks into an empty home instead of the ten folders a first login creates |

Every one of these is written by the **real** `ConfigProcessor`, from the same
template `generate_config.sh` uses, to the same place it puts it.

### The three departures from `tests/render/shoot.py`, and why each is *more* faithful

1. **The cursor is invisible** (`cursor:invisible`, the line
   `tests/render/test_schale_stil.py` uses). A mouse pointer on a showcase
   picture is an artefact of the rig.
2. **The clock is real.** `shoot.py` feeds the date module a fixed
   `Di 12.08.2026 14:07`; next to it the calendar shows the machine's date —
   two contradicting dates in **one** picture, a defect no installation has.
   The placeholder is replaced by `date` in the format from
   `date-config.template`, so bar and calendar agree.
3. **`home.icons` names what this machine actually has.** ZepOS ships 15
   applications on the Home (`src/apps.py`, read out of
   `packaging/zepos-apps/PKGBUILD`); eight are not installed here, and the Home
   draws a placeholder for each. Seven broken icons would be a defect of the
   rig. `home.icons` therefore lists the seven that resolve — an ordinary user
   setting, written through the ordinary settings file.

### And one more, for the launcher only

`XDG_DATA_DIRS` points at a directory holding **only ZepOS' applications**,
plus symlinks to everything else under `/usr/share` so GTK still finds its icon
theme.

The launcher reads every `.desktop` entry on the machine — 74 here. The first
attempt put two of **this developer's own private programs** in the top two
rows of the picture. They are not on a ZepOS installation and have no business
on a showcase. The selection is not made by hand: `src/apps.shipped()` reads
the `depends` array of `packaging/zepos-apps/PKGBUILD`, and each name is
resolved to its entry the way the Home does it — by file name, then by the base
name of `Exec=`, because `nautilus` is `org.gnome.Nautilus.desktop`. Seven of
the 15 resolve here; the other eight are simply not installed on this machine
(`xdg-desktop-portal-gnome`, `loupe`, `papers`, `celluloid`,
`gnome-text-editor`, `gnome-calculator`, and ZepOS' own `zepos-claude-code` and
`zepos-settings`).

### The four menus, and why they were shot one widget at a time

There is **no tool on this machine that pushes a pointer button into a Wayland
session** — `ydotool`, `wlrctl` and `dotool` are all absent, `wtype` does keys
only, and `hyprctl dispatch` moves the cursor but cannot press. `tests/render/`
already had the answer and it is reused unchanged: a child process builds the
generated widget for real, on a real layer-shell surface, with both generated
stylesheets applied the way `app.ts` applies them, and fires the gesture
through `observe_controllers()` — the same callback a real right-click fires.

- the dock menu uses `tests/render/dock_menue_child.tsx` **unchanged**;
- the launcher menu uses `tests/render/launcher_menue_child.cpp` **unchanged**,
  compiled against the patched upstream tree that
  `packaging/zepos-hyprlaunch/PKGBUILD` builds, at the pinned commit
  `24e5c8b8`;
- the two Home menus use a child written for this job, in the scratchpad, built
  the same way and for the same reason.

A run that builds `widget/Home` cannot also run the whole shell — there would
be two Homes on top of each other, every icon twice. So the menu pictures come
from runs in which exactly one widget was built, which is what
`tests/render/test_menue.py` has done since 20.08.2026. They are cropped to the
menu; what is on them is the shipped widget with the shipped stylesheet.

### The lock screen, and how it was made safe

The user was sitting at this machine, working, while it was taken.
`ext-session-lock-v1` stays **locked** when the locking program dies (line 111
of its XML), so a run that locked the wrong session could not even be undone
with Ctrl-C. Three things ruled that out, and none of them is trust:

1. `zepos-lock` was handed `Session.environment()`, in which `XDG_RUNTIME_DIR`
   and `WAYLAND_DISPLAY` point into this run's private runtime directory.
   `refuse_the_real_session()` checks that before every child process; the
   script asserts it again itself and prints the socket it is about to lock
   (`/tmp/zepshot-…/wayland-1`).
2. What it locked is a **Hyprland inside Hyprland** — the same construction
   `tests/lock/test_lock_screen.py` has locked in since 12.08.2026. Afterwards
   `hyprctl layers` was asked, and `zepos-lock` is correctly *not* among them:
   a lock surface is not a layer-shell surface.
3. PAM pointed at a stack that **never opens** (`auth required pam_deny.so`),
   bind-mounted over `/etc/pam.d` inside a user namespace (`unshare -Urm`, no
   root needed) — word for word what `_start_locker()` in
   `tests/lock/test_lock_screen.py` does. The real authentication path was
   never entered.

The binary is built with `meson` + `ninja` from `lock/`, and the stylesheet
comes from `src/styles/lock-style.template` through the real processor.

**Why the picture says `root`:** `unshare -Urm` maps the caller to uid 0 inside
the namespace, so `getpwuid` answers `root`. On an installation the account
name stands there. It is an artefact of the safety measure, with one convenient
side effect: the real account name is not on the picture.

---

## Nothing personal is in them, and this is how that was checked

Four checks, all four repeated for this set on 24.08.2026.

1. **Structurally.** `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`,
   `XDG_DATA_HOME` and `DBUS_SESSION_BUS_ADDRESS` all point into a throwaway
   directory under `/tmp`; `refuse_the_real_session()` checks it before
   **every** child process. Nothing on a picture can reach the human's home
   directory. The two notifications on `benachrichtigung.webp` were sent to
   *this run's own* session bus (`Session.start_bus()`), not to his.
2. **By deliberate omission.** The **network** and **Bluetooth** pages of the
   control centre and the **disk** and **battery** overlays are *not* here.
   Those four talk over the **system bus** to the real NetworkManager and
   `bluetoothd`, and read `df -h`, `lsblk -dno MODEL` and
   `/sys/class/power_supply/BAT0/*` of the real machine — the rig redirects
   neither the system bus nor `/sys`, and they would show network names, device
   names, mount points and a disk model. Both daemons are reachable here
   (`nmcli`, `bluetoothctl` exist). The **control** page *was* checked on the
   picture itself: "Nicht verbunden", "VPN: Aus", "Bluetooth" — no name.
3. **By looking.** All 27 were opened at full resolution and every legible
   string enumerated. None of them is `lmarzoll`, a host name, a path under
   `/home/lmarzoll`, a network name, a device name, a serial number or an
   address. What is legible: application labels that exist on every Linux, the
   standard XDG folder names, the German strings of the interface itself, the
   two notifications this run sent to its own bus, the QEMU disk `/dev/vda`
   with its 24 GiB, and the date and time of the run.
   **One exception is named rather than hidden:** the shell's settings window
   shows the path of the settings file it edits, and on these pictures that is
   `/tmp/zepschau-…/zepos/user-s…`, the throwaway home of this run. On an
   installation it says `~/.config/zepos/user-settings.json`. It carries no
   name.
4. **Metadata.** `grim` writes no `tEXt` and no EXIF block, and the WebP
   conversion runs with `-strip` anyway. `magick identify -format "%[profiles]"`
   returns empty for all 27, and `magick identify -verbose` finds no `exif:`,
   `comment:`, `Software:`, `Artist` or `Copyright` field. `strings` over the
   raw bytes finds no match for `lmarzoll`, `/home/`, a host name or an SSID.

---

## Remaking them

Nothing to install, nothing to push to a branch. The pictures are ordinary
files in `main`:

1. Run the rendering scripts. Everything they build on is
   `tests/render/desktop_session.py`, which is in the tree. **Run
   `bash po/build.sh` first** — see the findings below.
2. Crop against the base picture of the same run, and convert:

   ```bash
   # the rectangle in which the picture differs from the base, below the bar
   magick grund.png fenster.png -compose difference -composite \
          -colorspace Gray -threshold 4% -crop +0+84 +repage -format '%@' info:
   # then, with that rectangle plus 28 px of air:
   magick fenster.png -crop 552x596+684+80 +repage \
          -strip -define webp:lossless=true kalender.webp
   ```

   The bar is left out of the search on purpose: otherwise every comparison
   would find the clock, which moved on between two shots, and the rectangle
   would always reach the top edge.
3. Check it is lossless: `magick compare -metric AE a.png b.webp null:` must
   print `0`. It did, for every picture converted whole.
4. Repeat all four checks above. Then `git add docs/bilder/<name>.webp` **by
   name**, and commit.

Lossless was chosen over `-q92` deliberately: it costs about four times the
bytes of lossy but lets "no retouching" stand without a footnote. Against PNG
it *saves* about 40 %.

---

## What is not here, and why

| Not here | Why |
|---|---|
| network page, Bluetooth page, disk overlay, battery overlay | check 2 above — real devices, over the system bus and `/sys` |
| the wallpaper selector | it opens and it is **empty**: the rig has no wallpaper directory, and the monitor buttons read `WAYLAND-1 [Q]` / `HEADLESS-1 [Q]`, which are names of the test rig. That is a picture of a rig, not of ZepOS |
| the login screen (`regreet`) | not installed here, and it does not start without `$GREETD_SOCK`. `tests/render/greeter_shot.py` **rebuilds** its widget tree to measure colours; a reconstruction has no business being called a screenshot |
| a video or a GIF | no screen recorder for `wlr-screencopy` here (`wf-recorder`, `gifski` both absent) and no tool for synthetic pointer clicks. A demonstration *without clicks* is not a demonstration. `dateien.webp` answers "how do I find my files" as a still |
| a second, smaller copy of each picture as a thumbnail | it would double what the history carries forever. `<img width>` in the READMEs does the same job for nothing |

---

## Findings that came out of making them, and were not fixed here

- **`po/build/` was stale.** `po/desktop/de.po` was last touched on
  21.08.2026, the compiled `po/build/de/LC_MESSAGES/zepos-desktop.mo` on the
  20th. Every string added on the 21st — the Home menus, the dock menu, the
  launcher menu — therefore fell back to English in a developer tree, and the
  first run of these pictures showed half-English menus. `bash po/build.sh`
  fixes it (309 → 319 messages) and the pictures were remade. `po/build/` is
  gitignored, so nothing about this is committed; anybody rendering from a
  fresh checkout has to run it first.
- **`Open` is translated as `Offen`** in `po/desktop/de.po` — an adjective
  where the menu wants a verb (`Öffnen`). It is legible on
  `home-menue-symbol.webp`. Not changed here: `po/` is not this task's file.
- **The bar does not fit on 1366×768.** Three status modules (tray, WLAN,
  Bluetooth) sit behind the collapse button, visible on
  `schreibtisch-1366.webp`. `tests/render/shoot.py` claims in its own header
  that "since the default was rebuilt the bar fits completely". Either that
  sentence is out of date or `COMPLETE_FROM` measures something other than the
  picture.
- **The Home does not filter `NoDisplay`.** It lists
  `xdg-desktop-portal-gnome` as an icon although its entry carries
  `NoDisplay=true` — which is exactly why `desktop_entries.installed()` keeps
  it out of the dock. Not visible on these pictures, because `home.icons` is
  set.
- **`.webp` is not in `SKIP_SUFFIXES`.** `tests/origin_data.py` skips `.png`,
  `.jpg` and `.gif` by suffix but not `.webp`, and `test_inventory.py` reads
  `docs/` in full — so these files are read as text. It passes today (checked),
  and the failure mode would be a false positive on compressed bytes, not a
  real find. The clean fix is one entry in `SKIP_SUFFIXES`; `tests/` is not
  this task's file. **This matters more now than it did on a branch:** the
  pictures are in `main`, so the inventory test reads them on every run.
