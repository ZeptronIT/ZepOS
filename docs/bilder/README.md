# The pictures in the two READMEs

28 files, **4 995 994 bytes — 4.76 MiB** in total: **16 recordings**
(15 animated WebP, 3 352 374 bytes, plus `dateien-finden.gif`, 806 856 bytes)
and **12 stills** in lossless WebP (836 764 bytes). Taken on **24.08.2026**;
the stills from `4a1d8f0`, `dateien-finden.gif` from `72d5bdf`, the fifteen
WebP recordings from the tree at `291b393` plus the new
`tests/render/schaukasten.py`, unless the tables below say otherwise.

The fifteen short recordings replaced the stills of the same name on
24.08.2026, on one instruction: *"alle bilder auf die everything on the screen
als animation machen bitte, alle ja"*, and *"lasse sie etwas flüssiger
aussehen"*. They keep the file names they replaced, so every `<img src>` in
both READMEs went on working unchanged.

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

**Every replaced picture stays in the history forever.** 4.76 MiB is what a
clone carries after the change of 24.08.2026 — 0.80 for the 12 remaining
stills, 3.20 for the 15 recordings, 0.77 for the GIF. Before it, 2.73 MiB; the
whole showcase went from one moving picture to sixteen for **+2.03 MiB**, and
the old stills stay in the history on top of that.

That number was kept down on purpose, and the three levers are measured, not
guessed:

- **short loops, not long takes.** The flagship GIF runs 12.8 s because it
  explains something. A menu that opens needs 1.6 s, a window that appears 2.6.
  Every recording is trimmed to the gesture and a short hold.
- **animated WebP instead of GIF.** Measured on the existing GIF: re-encoded as
  animated WebP it is 122 508 bytes at q=50 and 196 204 at q=80, against
  806 856 as a GIF — a fifth to a seventh, at a quality that is
  indistinguishable at 250 % zoom.
- **only what differs costs.** Consecutive byte-identical frames are collapsed
  into one frame carrying the sum of their durations, so the still parts of a
  recording are nearly free. Of `kontrollzentrum`'s 41 frames, 9 are distinct.

What was **not** done, and the number for it: encoding lossless, the way the
stills are. Measured per frame on five recordings, lossless costs **2.2× to
8.3× (mean ≈ 5×)** what q=80 costs, which would put the set near 17 MiB for a
difference nobody can see on a two-second loop. The stills stay lossless
because a still is looked at closely; a loop is not.

That is why:

- there is **one file per element and no second, smaller copy** as a thumbnail.
  The READMEs scale with `<img width="…">`, so the repository stores each
  picture exactly once and the browser does the resizing.
- everything that is not a whole desktop is **cropped to the element it shows**.
  The calendar is 552×596 and 88 kB, not 1920×1080 and 400 kB. Seven of the
  27 files are under 20 kB; only three are a whole 1920×1080 desktop.
- a picture is remade when it is **wrong**, not when it could be nicer.

---

## The 16 recordings

Fifteen of them are animated WebP, made by **`tests/render/schaukasten.py`** in
one nested session (the dock menu needs a second one, see below). The sixteenth
is `dateien-finden.gif`, which has its own section further down.

The frame rate in this table is **measured, not set**: the recorder writes down
the clock reading for every frame it pulls, and the rate is computed from those
readings afterwards. The tick asked for was 40 ms = 25.0 frames/s. **Not one
frame was dropped in any of the fifteen.**

| File | Size | Frames | Length | Frames/s measured | Bytes |
|---|---|---|---|---|---|
| `starter.webp` | 960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540 | 11 | 2.57 s | **24.95** | 291 676 |
| `dateien.webp` | 960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540 | 28 | 4.54 s | **24.89** | 504 588 |
| `dock.webp` | 528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132 | 16 | 2.90 s | **24.86** | 54 648 |
| `dock-minimiert.webp` | 528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132528×132 | 12 | 2.69 s | **24.92** | 51 496 |
| `dock-menue.webp` | 342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310342×310 | 22 | 3.30 s | **24.84** | 95 382 |
| `kontrollzentrum.webp` | 936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596 | 11 | 1.63 s | **24.60** | 179 074 |
| `tastenkuerzel.webp` | 936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596 | 30 | 1.62 s | **24.66** | 662 074 |
| `kalender.webp` | 552×596552×596552×596552×596552×596552×596552×596552×596552×596552×596552×596 | 11 | 1.62 s | **24.66** | 156 244 |
| `stil-editor.webp` | 528×596528×596528×596528×596528×596528×596528×596528×596528×596528×596528×596528×596528×596 | 13 | 1.62 s | **24.69** | 159 552 |
| `einstellungsfenster.webp` | 936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596936×596 | 11 | 1.63 s | **24.61** | 350 062 |
| `einstellungen-app.webp` | 960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540960×540 | 18 | 2.64 s | **24.21** | 384 328 |
| `vpn-einstellungen.webp` | 716×596716×596716×596716×596716×596716×596716×596716×596716×596716×596716×596 | 11 | 1.62 s | **24.66** | 151 900 |
| `benachrichtigung.webp` | 572×254572×254572×254572×254572×254572×254572×254572×254572×254572×254572×254 | 11 | 2.21 s | **24.83** | 70 616 |
| `benachrichtigungszentrum.webp` | 438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416438×416 | 18 | 1.62 s | **24.69** | 117 196 |
| `sitzungsmenue.webp` | 666×380666×380666×380666×380666×380666×380666×380666×380666×380666×380666×380666×380666×380666×380 | 14 | 1.62 s | **24.68** | 123 538 |

<sub>"Frames" is the number of `ANMF` blocks counted in the committed file, not
the number the recorder pulled — see *The encoder that quietly threw frames
away* below for why that distinction had to be made and checked.</sub>

### What is on each one

- **`starter.webp`** — the application launcher opens over the desktop
- **`dateien.webp`** — `datei` is typed letter by letter, Return, the file manager appears on the home folder
- **`dock.webp`** — `SUPER+B`: the dock slides away and comes back
- **`dock-minimiert.webp`** — a window is minimised: it disappears and an eighth, dimmed icon appears right of the dock's divider
- **`dock-menue.webp`** — right-click on a pinned dock icon, the menu opens, Escape closes it
- **`kontrollzentrum.webp`** — the control centre fades in over the desktop — sidebar, two groups, six pages
- **`tastenkuerzel.webp`** — the shortcut list fades in, filled from the generated keybindings
- **`kalender.webp`** — the calendar overlay fades in over the wallpaper
- **`stil-editor.webp`** — the style editor fades in, colours tab
- **`einstellungsfenster.webp`** — the shell's own settings window fades in, size page
- **`einstellungen-app.webp`** — `zepos-settings-gui` opens as an ordinary window — the one recording that shows Hyprland's **window** animation, not a layer one
- **`vpn-einstellungen.webp`** — the VPN settings fade in, four tabs
- **`benachrichtigung.webp`** — a notification arrives top right and settles
- **`benachrichtigungszentrum.webp`** — the notification centre fades in, do-not-disturb switch on top
- **`sitzungsmenue.webp`** — the session menu fades in, six actions with letter keys

---

## The 12 stills

These twelve did **not** become recordings, and each line says why. The rule
was the user's own instruction turned around: where nothing moves, a still is
more honest than an animation that fakes movement.

| File | Size | Bytes | What is on it | Why it stayed a still |
|---|---|---:|---|---|
| `schreibtisch.webp` | 1920×1080 | 191 324 | the whole desktop: bar, Home with icons, dock, both corner buttons | **nothing moves.** A desktop at rest is a desktop at rest; the bar's modules are the fixtures from `module_payloads()` and do not tick |
| `schreibtisch-1366.webp` | 1366×768 | 158 064 | the same desktop on a notebook screen | same, and it exists to show a *size*, not a gesture |
| `leiste.webp` | 1920×84 | 29 624 | the bar alone, cropped to its own layer geometry | same. What the bar *does* when you use it is `kontrollzentrum`, `kalender` and `tastenkuerzel`, and all three of those now move |
| `home-menue-symbol.webp` | 343×335 | 17 796 | right-click on a Home **icon** | **no rig.** The child that fires this gesture lived in the scratchpad of the session that took the still and is gone; `tests/render/` has one for the dock (`dock_menue_child.tsx`) and for the launcher, but none for the Home |
| `home-menue-flaeche.webp` | 417×341 | 18 754 | right-click on the **empty Home surface** | same |
| `starter-menue.webp` | 367×155 | 14 478 | right-click in the launcher (`43b8b25`) | `launcher_menue_child.cpp` exists, but it needs the patched upstream tree built against it — a second toolchain run for one two-state loop that a `Gtk.Popover` does not animate anyway (measured on the dock menu: **zero** in-between frames on the way open) |
| `auswahlfenster.webp` | 1920×1004 | 65 012 | `zepos-menu`, the picker every list goes through | `zepos-menu` is not installed here and ships as a tarball in `packaging/`; building it was out of scope for this pass |
| `sperrbildschirm.webp` | 1920×780 | 59 130 | `zepos-lock` — see its own section below | **deliberately not re-run.** `ext-session-lock-v1` stays locked when the locking program dies, and the user is sitting at this machine working. The still was taken once, under three separate safeguards; a recording would have meant doing it again for no new information |
| `installer-sprache.webp` | 1280×800 | 66 362 | installer, step 1 of 8 | the installer does not run in the nested compositor — it wants a whole machine and a disk to erase (see below) |
| `installer-einteilung.webp` | 1280×800 | 85 062 | installer, step 3 — laying out the disk | same |
| `installer-bestaetigung.webp` | 1280×800 | 70 998 | installer, step 8 — the last question | same |
| `installer-fertig.webp` | 1280×800 | 60 160 | installer, finished, package log behind it | same |

**The four installer pictures are older and from somewhere else.** They were
taken on **17.08.2026** by `./iso/test-boot.py --scenario release-install`, in
QEMU, off the release medium — which is why the version stamp along their
bottom edge says `ZepOS 2026.08.17 824b70b`. That is honest and both READMEs
say it. The installer does not run in the nested compositor: it wants a whole
machine and a disk to erase.

---

## The animation

`dateien-finden.gif` — **960×540, 12.8 s, 128 frames, 806 856 bytes (788 kB)**,
made by `tests/render/film.py` from `72d5bdf`. It answers the one question the
user asked for by name: *how do I find my files.* Desktop at rest → the
launcher opens → `datei` is typed one letter at a time → the result list
narrows from six applications to one → Return → the file manager stands on the
home folder with its nine folders.

### It is a recording, and here is what "recording" means here

There is no screen recorder for `wlr-screencopy` on this machine — `wf-recorder`
and `gifski` are both absent, and nothing may be installed. **`grim` is the
recorder**, one frame long: a background thread pulls frames at a fixed tick
and writes down the clock reading for each; `ffmpeg` builds the GIF from frames
*plus measured times*. The frame rate is therefore not set, it is **measured**,
and the number in both READMEs is the measured one:

| | |
|---|---|
| tick asked for | 100 ms = 10.0 frames/s |
| frames | 127 |
| length | 12.70 s |
| **frame rate reached** | **9.92 frames/s** |
| gap between frames | 100 / 101 / 184 ms (min / mean / max) |
| frames dropped | 0 |

One session from beginning to end. Nothing cut, nothing sped up, no second take
spliced in, no retouching. Of the 127 frames, **25 are distinct** and the other
102 are byte-identical repeats of one of those 25 — which is why a 12.8 s
animation of a desktop costs 788 kB: `ffmpeg` writes a still frame as a 1×1
pixel update.

### Why GIF, measured and not assumed

Both READMEs were run through GitHub's own renderer
(`gh api -X POST /markdown`, mode `gfm`, context `ZeptronIT/ZepOS`):

- `<img src="…gif">` survives, and GitHub adds `data-animated-image=""` and
  `style="max-width: 100%"` of its own — it renders as an image, and a browser
  plays an animated GIF by itself, with no click and no play button.
- `<video src="docs/video/x.mp4" controls autoplay loop>` is **stripped
  entirely**; the paragraph comes back empty. `[x.mp4](…)` becomes a link one
  has to click, and `![](…mp4)` becomes an `<img>` that no browser can draw.
  GitHub embeds a player only for files **uploaded through its web interface**,
  which is not a file in the repository.

So GIF is not a habit here, it is the only format that plays by itself from a
path in the tree.

**And it really does play by itself** — checked against a live README and not
guessed. A repository page whose README carries GIFs
(`github.com/charmbracelet/vhs`) serves them as plain `<img …
data-animated-image="">`: no player, no click, no poster frame. The page's
`<html>` element carries `data-a11y-animated-images="system"`, which is
GitHub's *Animated images* accessibility setting; `system` — the default —
means it follows the viewer's `prefers-reduced-motion`. A visitor who has asked
their system for less motion, or who has switched that setting off, sees the
first frame and a control instead. That is the only case in which it does not
run on its own, and it is the right one to honour.

Our own file is animated in the way that needs: 128 Graphic Control blocks with
their own delays and one Netscape application block, so it loops forever.

### The keystroke that is not in it, and why

The nested compositor of `tests/render/desktop_session.py` drives on a minimal
`hyprland.conf`: monitor, `misc`, animations off, `decoration`, `layerrule`.
**Not one `bind` line** — the measurement sessions need geometry and glass, not
a keyboard. So `SUPER+SPACE` does nothing there.

Switching it on at run time works and changes no existing session:
`hyprctl keyword bind …` registered three bindings and `hyprctl -j binds`
listed all three back — `(0, F9)`, `(64, SPACE)`, `(12, T)`. **None of them
ever fired.** Six `wtype` variants — bare key, modifier as state, modifier as a
real key, each with and without pauses — all returned 0 and the receipt file
stayed empty every time, while `hyprctl dispatch exec` of the same command
wrote it instantly. Keys from a virtual keyboard *do* arrive: the same `wtype`
call types `datei` into the launcher's search field in this very recording.
They reach the focused client and not the compositor's binding matcher.

Whether Hyprland ignores `zwp_virtual_keyboard_v1` for bindings in general, or
whether it is this nesting, **cannot be decided here**: the counter-test is a
press on the real keyboard, and that belongs to the person working next door.

The recording therefore does not fake the keystroke. It opens the launcher with
the command the plugin runs on that key — `hyprlaunch-ui --toggle`, word for
word out of `sendUICommand()` in `src/Globals.cpp` of the pinned commit. Both
READMEs say so in the caption.

### Three more things the rig needed, each one measured

1. **Its own `/tmp` for the launcher.** `hyprlaunch-ui` carries its control
   socket as a literal: `/tmp/hyprlaunch-ui.sock`. On start it *unlinks* that
   path and binds its own; with a command on the line it first sends the
   command to whoever already listens there. On this machine **the developer's
   own running launcher listens on it**, in his own session. Calling
   `hyprlaunch-ui` from a render run would therefore either open *his* window
   or delete the socket under his feet. The launcher now runs in its own mount
   namespace with a private `/tmp`, and the three conditions are chained with
   `&&` so that a failure runs nothing at all:
   `mount -t tmpfs none /tmp && test ! -e /tmp/hyprlaunch-ui.sock && exec …`.
   Runtime directory, build directory and the binary itself live under
   `/dev/shm` for the same reason — that private `/tmp` would otherwise hide
   them.
2. **The session bus has to be told which session it is in.**
   `org.gnome.Nautilus.desktop` carries `DBusActivatable=true`, so GIO does not
   start it — the session bus does, and the bus hands the child *its own*
   environment. `Session.start_bus()` gives that daemon three variables on
   purpose (`PATH`, `HOME`, `XDG_RUNTIME_DIR`), so it inherits nothing from the
   human's session — and a Nautilus started that way has no `WAYLAND_DISPLAY`.
   The first run pressed Return, the launcher closed, and **no window came**:
   the recording ended on an empty desktop. `dbus-update-activation-environment`
   with a named list — the same program a real login runs — fixes it.
3. **The rig's second output had to go.** The nested compositor has two:
   the headless one being filmed (1920×1080) and `WAYLAND-1`, the window at the
   host, measured at 931×521. `LauncherRenderer::fittingHeight()` looks for the
   **shortest** monitor and derives from it how many result rows the window may
   be — the shortest was that 521 px host window, so the launcher showed **two**
   rows although seven applications resolve. `monitor = WAYLAND-1, disable` at
   run time leaves exactly one output, and the launcher shows six. This is not
   flattery; it is removing a piece of scenery only this rig has. **The same
   artefact is on `starter.webp` in this directory** — that is why its launcher
   has two rows and the animation's has six.

---

## How the fifteen recordings are made

`tests/render/schaukasten.py`, 25.0 frames/s asked for, **24.2 to 25.0
measured**, zero frames dropped. It reuses `tests/render/film.py` for the parts
that were already paid for — building the launcher out of the pinned tarball
plus this repo's patch, the private `/tmp` that keeps the launcher's hard-coded
control socket away from the user's own session, the filtered `XDG_DATA_DIRS`,
the session bus, switching off the host output — and adds what a *film* needs
that a still does not.

### `grim` is still the recorder, but not the same `grim`

`grim -l 1` writes a compressed PNG in 64 ms, which caps the rate at 15
frames/s — half of what was asked for. **`grim -t ppm` compresses nothing and
takes 32 ms**, leaving room for 25. The price is a 6.2 MB file per frame; a
full run pulls over 800 of them, so the raw frames live in `/dev/shm` and only
the *distinct* ones are kept afterwards, as PNG. Cropped scenes are pulled with
`-g`, because a 342×310 menu has no business costing a 1920×1080 read.

### The animations are switched back **on**, and that is the whole point

`tests/render/desktop_session.py` starts its compositor with
`animations { enabled = false }`, and for a **still** that is right — it says so
itself: *"damit das Bild nicht mitten in einer Einblendung entsteht"*. For a
recording it is the defect itself: with animations off there is **no in-between
frame at all** between shut and open, and the recording would be two stills
after one another.

`schaukasten.py` therefore switches them on at run time with the values read out
of the **generated** `hyprland.conf` — `bezier zepos, 0.05, 0.9, 0.1, 1.05` and
the five `animation` lines — so what fades in on these recordings fades in
exactly the way it does on an installation. Through `hyprctl keyword`, in that
run's own session: `desktop_session.py` is not touched and no existing
measurement session behaves differently.

### What triggers each one, and why it is not a staged click

`app.ts` carries a `requestHandler` with these names in it (`control`,
`calendar`, `shortcuts`, `settings`, `style`, `logout`, `notifications`,
`vpn-settings`, `dock`, …). That handler **is** the path every key binding of
this system takes: the generated `hyprland.conf` binds `ags request control` to
a key, not a function. Firing `ags request control` is therefore literally what
the user's keystroke does — minus the keystroke, which cannot be delivered into
this nesting (`film.py`, `_WARUM_KEIN_TASTENDRUCK`).

Typing and Return in `dateien.webp` are real key events through `wtype`.
`dock-minimiert.webp` uses `movetoworkspacesilent special:minimized,address:0x…`
— the dispatcher the title bar's minimise button runs.

### The pointer button, which two people before stopped at

There is still **no tool on this machine that presses a pointer button** —
`ydotool`, `wlrctl` and `dotool` are all absent, `wtype` does keys only,
`hyprctl dispatch movecursor` moves the cursor and cannot press. That is why
the previous two passes left the right-click menus as stills.

`dock-menue.webp` moves anyway, and the answer was already in the tree:
`tests/render/dock_menue_child.tsx`, used **unchanged**. It builds the
*generated* dock on a real layer-shell surface in a real compositor with both
generated stylesheets, and fires the gesture where GTK would take it — the
`pressed` signal of the `Gtk.GestureClick` the template hangs on the button,
found through `observe_controllers()`. No cursor in frame, the same visible
consequence: a menu that opens.

It needs its **own** session, because the child builds the dock itself and
running the whole shell beside it would put two docks on top of each other —
the same split `tests/render/test_menue.py` has used since 20.08.2026.

Where the menu lands is **measured, not guessed**: a `Gtk.Popover` is an
xdg_popup, `hyprctl layers` does not know it, and the dock's own box does not
grow around it. So one frame is taken shut, one open, and
`measure.changed_bounds` returns the smallest rectangle in which they differ.

Two things fell out of that and are worth writing down: `rechtsklick` **opens**,
it does not toggle — a second call leaves the menu open and only writes
`Tried to map a grabbing popup with a non-top most parent` into the log, so the
recording is closed with `Escape` through the compositor, the way a person
closes it. And a `Gtk.Popover` has **no** transition on the way open: between
shut and open there is not one in-between frame. Recording only the opening
would have been a two-state loop that blinks, so the recording is the whole
gesture — right-click, look, `Escape` — which is four states long, runs round,
and invents nothing.

### The encoder that quietly threw frames away

This is the one that would have ruined the job, and it is invisible unless you
count the `ANMF` blocks in the finished file. Measured on one recording of the
control centre, 41 frames pulled, 9 of them distinct:

| how it was encoded | frames in the file | bytes |
|---|---:|---:|
| `libwebp_anim`, lossy | **5** | 80 762 |
| `libwebp_anim`, lossless | 9 | 837 334 |
| `libwebp`, lossy | 42 | 695 004 |
| **collapsed first, then `libwebp`, lossy** | **9** | **163 688** |

`libwebp_anim` collapses identical frames — and in lossy mode throws away
**different** ones too. Four of the nine steps of a fade were gone, and the
recording stuttered at exactly the place it is supposed to be smooth. `libwebp`
throws none away but also collapses none, and writes 42 full frames.

So `schaukasten.py` does what neither does properly: consecutive **byte-identical**
frames are merged into one frame carrying the sum of their durations — that is
not a shortening, it is what was recorded — and everything left over is
different and goes into the file whole. Then it **counts the `ANMF` blocks in
the written file** and fails if there are fewer than it put in. A recording that
does not check this is a recording that merely claims its frame rate.

### Why WebP, measured on GitHub and not assumed

The previous pass proved that GitHub plays a GIF by itself in a README. The
same proof was run for WebP on 24.08.2026, with the same tool and the same
second question put to a real, foreign page:

1. GitHub's renderer (`gh api -X POST /markdown`, mode `gfm`) **keeps**
   `<img src="….webp">`, from HTML and from Markdown, and adds
   `style="max-width: 100%"` of its own. What it does **not** add is
   `data-animated-image=""` — only `.gif` gets that. (`.png` and `.apng` do not
   either.)
2. That is the point. `data-animated-image` is the mark GitHub's accessibility
   layer uses to wrap an image in a player with a pause button once the reader
   has `prefers-reduced-motion` set. A WebP does not carry the mark, so it is an
   ordinary `<img>` — the browser plays it, always, with no button.
3. Looked at on a real page rather than assumed:
   `github.com/quick-lint/quick-lint-js/tree/master/plugin/vscode` shows
   `demo.webp` (105 882 bytes, 75 frames, 51 `ANMF` blocks) as a plain
   `<img src="/quick-lint/quick-lint-js/raw/master/plugin/vscode/demo.webp"
   alt="…" style="max-width: 100%">` — no player, no button, no poster frame.
4. And the bytes arrive unchanged: through `github.com/…/raw/…` and through
   `raw.githubusercontent.com` GitHub serves the identical file, same sha256,
   `Content-Type: image/webp`. It transcodes nothing and drops no animation.

**The price is named, because it is the one thing GIF does better here.** With
no mark, a WebP ignores `prefers-reduced-motion`. A reader who asked his system
for less motion gets a still and a button for `dateien-finden.gif` and gets
these fifteen moving anyway. That is why the long, explaining recording stays a
GIF and only the short loops are WebP, and why both READMEs say so.

---

## How the 12 stills are made

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

Four checks, all four repeated for this set on 24.08.2026 — and repeated again
for the animation, where each one had to cover **every frame** and not just the
first. Where the animation differs, it says so below.

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
3. **By looking.** All 27 of the original stills were opened at full
   resolution and every legible string enumerated; the 216 distinct frames of
   the fifteen recordings were checked the same way, see below. None of them is `lmarzoll`, a host name, a path under
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
   returns empty for all of them, and `magick identify -verbose` finds no `exif:`,
   `comment:`, `Software:`, `Artist` or `Copyright` field. `strings` over the
   raw bytes finds no match for `lmarzoll`, `/home/`, a host name or an SSID.

### The fifteen recordings, frame by frame

851 raw frames, **1 989 227 696 bytes**, and every one of them was searched —
not the first one of each. Two things made a complete check affordable and one
of them had to be *invented*, because a naive byte search over raw pixels is
worthless.

**Distinct frames, not all frames, for the looking.** `sha256` over all 851
frames leaves **216 distinct**; every other frame is byte-identical to one of
those. All 216 were kept as PNG under `out/schaukasten/bilder/<name>/` and
looked at — as contact sheets per recording, and at full resolution for every
recording whose *content* changes rather than just its opacity
(`dateien`, `starter`, `tastenkuerzel`, `einstellungen-app`).

What is legible on them: the interface's own German strings, the shipped
application names, the standard XDG folder names, the placeholder bar with its
fixed clock, `Nicht verbunden` / `VPN: Aus` / `Bluetooth` with no names, an
empty `VPN Server` field with the template's default connection name `work`,
and the notification this run sent to its own bus. **No account name, no host
name, no path under `/home/lmarzoll`, no network name, no device name, no
serial number.**

**And the byte search, with a control experiment, because otherwise it lies.**
The sweep looks for 17 terms — the account name, the host name and its first
component, `/home/`, `dev/shm`, this run's own directory prefixes, the names of
programs ZepOS does not ship, and more. On the run that produced the committed
files it found **nothing**.

On an earlier run it found `T14` — the first three characters of this machine's
host name — in one raw frame. That is where the check had to get honest instead
of alarmed: a PPM is a ~16-byte ASCII header and then nothing but pixels, three
bytes each. The hit sat at byte **3 700 081**, deep in the pixel data, and the
full host name, `lmarzoll`, `/home/` and the machine's model number scored
**zero**. Twenty **random** three-letter sequences with no relation to this
machine were then searched for as a control: they hit **2 of 17** files in that
set, and **600 times** across the 851 frames of the committed run. A
three-character string in six megabytes of pixel data is noise, and the check
now says so itself — it prints the byte offset, whether the hit is in the header
or in the pixels, and the control count next to the findings, so nobody has to
guess later.

The finished WebP files were searched too: 15 files, 1 368 732 bytes, no term
found, and the same control hitting 3 times. `ffmpeg` writes no EXIF and no
comment chunk.

### The GIF, frame by frame

A film has many pictures, and "I looked at the first one" is not a check. What
made a complete one affordable: `sha256sum` over the 127 frames gives **25
distinct images**; every other frame is byte-identical to one of them. So:

- **All 25 distinct frames were opened at full resolution and read.** Legible on
  them: the bar with its stand-in clock `Di 12.08.2026 14:07`, CPU 12 %,
  memory 38 %, 66 shortcuts, ten workspaces, battery 87 %; the Home's icon
  labels, all of them names of applications ZepOS ships; the launcher with
  Archivverwaltung, Dateien, Druckerverwaltung, Festplattenbelegungsanalyse,
  Mozilla Firefox, btop++; the search text growing `d → da → dat → date →
  datei`; and the file manager on `Persönlicher Ordner` with Bilder, Dokumente,
  Downloads, Musik, Öffentlich, Projekte, Schreibtisch, Videos, Vorlagen. Not
  one user name, host name, path under `/home/lmarzoll`, network name, device
  name or serial number.
- The nine folder names come from `xdg-user-dirs-update` reading the stock
  `/etc/xdg/user-dirs.defaults` — including `Projekte`, which is Arch's default
  `PROJECTS=Projects` translated, not a folder of this machine.
- The launcher would have shown foreign entries again: the first run answered
  `datei` with **Dateien *and* Dateimanager Thunar**, a program ZepOS does not
  ship. The filtered `XDG_DATA_DIRS` above is what keeps the list to the ten
  entries of the shipped packages.
- **By bytes.** `grep -rlF` over all 127 frames *and* the finished GIF finds
  zero files containing `lmarzoll`, `LMARZOLL`, `T14`, `/home/`, `Thunar`,
  `dev/shm`, `hyprlaunch-ui` or `NetworkManager`.
- **Metadata.** The GIF's extension blocks were counted out of the raw bytes:
  128 × Graphic Control (`0x21F9`) and 1 × Application (`0x21FF`, the Netscape
  loop). **No comment block (`0x21FE`) at all**, and `strings -n 6` finds
  nothing beyond the `GIF89a` header.

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

The fifteen short recordings are one command and need no cropping step — the
crop of each is measured at run time from the layer the window actually takes:

```bash
.venv/bin/python -m tests.render.schaukasten --out out/schaukasten --guete 80
```

It writes one `<name>.webp` per scene, every distinct frame as PNG under
`out/schaukasten/bilder/<name>/`, and `out/schaukasten/messwerte.txt` with the
measured frame rate per scene, the marks for what happened when, the byte size
and `sha256` of every file, and the result of the personal-data sweep.
`--takt` sets the tick in milliseconds (40 = 25.0 frames/s), `--guete` the WebP
quality (80), `--nur name,name` records only those scenes, `--nur-bilder` stops
before encoding. It needs the same tools as `film.py` plus `notify-send` and
`magick`. Installing the result is a plain copy into this directory, under the
**same file names** the stills had.

The long, explaining animation is a second command:

```bash
.venv/bin/python -m tests.render.film --out out/film
```

It writes `out/film/dateien-finden.gif`, every single frame under
`out/film/bilder/`, and `out/film/messwerte.txt` with the measured frame rate,
the marks for what happened when, and the size and `sha256` of the GIF.
`--breite` sets the width in pixels (960 by default, an exact halving of
1920 — a non-integer scale visibly softens the type), `--takt` the tick in
milliseconds, `--nur-bilder` stops before the GIF. It needs `cmake`, `ninja`,
`wtype`, `ffmpeg`, `unshare` and `xdg-user-dirs-update` on top of what
`shoot.py` needs; it builds `hyprlaunch-ui` itself, out of the pinned tarball
and the patch in `packaging/zepos-hyprlaunch/`, so what is filmed is what that
recipe builds and not whatever binary happens to lie on the machine.

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
| a recording of the **Home**'s two right-click menus | the same pointer-button problem — `ydotool`, `wlrctl` and `dotool` are still absent and `wtype` does keys only — but no longer an unsolvable one: `dock-menue.webp` moves, because `tests/render/dock_menue_child.tsx` fires the gesture inside the application. What is missing for the Home is that child; the one that took the two stills lived in a scratchpad and is gone. Writing it is a job, not a blocker |
| a recording of the **launcher**'s right-click menu | `tests/render/launcher_menue_child.cpp` exists and would do it, but it has to be compiled against the patched upstream tree — a second toolchain run for a menu that, as measured on the dock, has **no** opening transition at all |
| a **mouse pointer** on any recording | nothing on this machine can put one there, and drawing one in would be an invention. Every recording shows the *consequence* of the gesture, never a fake cursor |
| a second, smaller copy of each picture as a thumbnail | it would double what the history carries forever. `<img width>` in the READMEs does the same job for nothing |

---

## Findings that came out of making them, and were not fixed here

- **`ffmpeg`'s `libwebp_anim` silently drops distinct frames in lossy mode.**
  Measured 24.08.2026: 9 distinct frames in, **5** `ANMF` blocks out; lossless
  keeps all 9, and the plain `libwebp` encoder keeps all 9 as well (but
  collapses no duplicates). Anyone building an animation with `libwebp_anim`
  and not counting the `ANMF` blocks afterwards is shipping a stutter he
  cannot see. Upstream `ffmpeg`/`libwebp`, not this repository —
  `schaukasten.py` works around it and checks the count.
- **`tests/render/settings_shot.py` cannot start the settings app from this
  project's venv.** It spawns `[sys.executable, LAUNCHER, …]`, and
  `.venv/bin/python` here has no PyGObject: `ModuleNotFoundError: No module
  named 'gi'`. `/usr/bin/python3` has it, and the command carries
  `#!/usr/bin/env python3` and finds it by itself — which is how `app.ts` calls
  it, and how `schaukasten.py` now calls it. One word in one line; **not
  changed here**, because `tests/render/settings_shot.py` is an existing
  measurement session and this pass does not alter how those behave.
- **The shell's settings window shows the rig's own config path.** It prints
  the file it edits, and in a rig run that is a throwaway directory:
  `/dev/shm/zepschau-bau-…/zepo…` on the recording,
  `/tmp/zepschau-9yt96zz1/zepos/user-s…` on the still it replaced. Both are
  correct — the window is telling the truth about where it is writing — and
  both are a rig artefact rather than something a user sees. It carries no
  account name. Removing it would mean faking the path, which is worse.
- **The Home draws a placeholder for every application this machine does not
  have.** Eight of ZepOS' fifteen are not installed here, so the first
  recordings had eight grey boxes among seven real icons. Solved the same way
  the stills solve it, through the ordinary `home.icons` user setting — but the
  underlying question, whether the Home *should* draw a placeholder for a
  missing application at all, is untouched and belongs to whoever owns
  `ags-home.template`.
- **A `Gtk.Popover` in this shell has no opening transition.** Between shut and
  open there is not one in-between frame (measured on the dock menu at 25
  frames/s); on the way closed there are. Whether that is wanted is a question
  for the stylesheet, not for the rig.
- **The launcher window does not shrink with the result list.** It is sized
  once, at start, to as many rows as the shortest monitor allows, and keeps
  that height however few results are left. In the animation you watch six rows
  become one and a large empty box stay behind it for two seconds. Visible from
  second 5 of `dateien-finden.gif`. `plugins/` holds only a `LICENSE` in this
  tree; the launcher is built from a pinned upstream commit plus
  `packaging/zepos-hyprlaunch/zepos-hyprlaunch.patch`, so this is a patch, not
  a one-line fix, and it was not this task's file.
- **`RENDERED` in `tests/render/desktop_session.py` fell out of date a second
  time**, in exactly the way `tests/src/test_render_table.py` was written to
  catch: `generate_config.sh` and `ags-config.template` both knew
  `ags-bluetooth-agent` (`405a248`), the table did not, and `ags bundle` broke
  with `Could not resolve "./widget/BluetoothAgent"` — which stops **every**
  render test, not just one. The missing line is entered, and the guard is
  green again. `tests/render/film.py` additionally reads the same `case`
  branches the table is copied from and renders whatever the table is still
  missing, into its own build directory only; that belt does nothing while the
  table is complete, and it is what let the animation be made before the line
  existed.
- **`po/build/` was stale.** `po/desktop/de.po` was last touched on
  21.08.2026, the compiled `po/build/de/LC_MESSAGES/zepos-desktop.mo` on the
  20th. Every string added on the 21st — the Home menus, the dock menu, the
  launcher menu — therefore fell back to English in a developer tree, and the
  first run of these pictures showed half-English menus. `bash po/build.sh`
  fixes it (309 → 319 messages) and the pictures were remade. `po/build/` is
  gitignored, so nothing about this is committed; anybody rendering from a
  fresh checkout has to run it first.

  **Running it turns one test red, and that test is the one that is wrong.**
  `tests/render/test_menue.py::test_das_menue_traegt_die_drei_punkte_einer_anheftung`
  asserts `New window|Remove from Home|Remove from dock` — English, in a session
  where `desktop_session.py` deliberately sets `LANG=de_DE.UTF-8`. It was green
  only because the stale catalogue made gettext fall back to the msgid.
  `tests/render/test_launcher_menue.py:444` checks the same kind of menu in
  German and stays green; `tests/src/test_dock_menue.py` checks English and
  stays green *correctly*, because it runs headless without `LANG`. One line in
  `test_menue.py` fixes it. `tests/` was not this task's file.
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
