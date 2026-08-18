# Contributing to ZepOS

Thank you for looking. ZepOS is pre-release and small, so the fastest way to
help is usually a precise bug report — see the
[issue templates](https://github.com/ZeptronIT/ZepOS/issues/new/choose). If you
want to change code, this page is what you need to know first.

---

## The three rules that are not negotiable

### 1. Never edit a generated file

Almost every configuration file in a running ZepOS is produced by
`zepos-generate` from a template in `src/templates/` or `src/styles/`, and
carries a "DO NOT EDIT" header. Editing the output means your change is gone at
the next generation, and the person after you cannot tell why.

The change goes into the template, or into one of the two single sources of
truth behind it:

| You want to change | Edit |
|---|---|
| An icon | `src/icon_definition.py`, then `./src/fetch_icons.sh` |
| A colour, a size, a spacing step | `src/brand.py`, `src/sizes.py`, `src/style_definition.py` |
| What a config file says | the template in `src/templates/` or `src/styles/` |
| What a package installs | the recipe in `packaging/<name>/PKGBUILD` |

Then regenerate. On an installed ZepOS that is `zepos-generate`; in a checkout
the same command is `src/bin/zepos-generate`:

```bash
./src/bin/zepos-generate --all      # or a single target; --help lists them
```

### 2. Never hardcode a value a template could carry

If a colour, a size or a path is written literally into a template, it is a
value that `zepos-settings` cannot reach and that `brand.py` cannot keep
consistent with the rest of the system. Use a `{{STYLE_*}}` or `{{ICON_*}}`
placeholder. Several tests exist purely to catch literals that slipped in.

### 3. Never weaken a test or a guard to make a change pass

The guards in this tree exist because something once went wrong. The isolation
guard exists because a test could otherwise drop the developer's wireless
connection; the allow-list in `iso/shared-with-release.txt` exists because a
deny-list would leak a known root password by omission. If a guard blocks you
and you believe it is wrong, say so in the pull request and explain why —
do not route around it.

---

## Getting set up

```bash
git clone https://github.com/ZeptronIT/ZepOS.git
cd ZepOS
python -m venv .venv          # Python 3.14
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

The full suite is 2931 tests in 110 files and takes about seven minutes. It
needs nothing but Python and pytest; tests that would need QEMU, OVMF, a built
package repository or a real Hyprland skip themselves when those are absent.

### The isolation guard

`tests/conftest.py` installs two autouse fixtures for the whole suite:

- no test may spawn a real process;
- no test may write outside a temporary directory — where "write" includes
  deleting, renaming, re-permissioning and symlinking.

The installer drives `iwctl`, `archinstall` and NetworkManager. Without the
guard, a careless test could overwrite your live network profiles or delete
part of the machine running it. A violation raises `IsolationViolation`, which
subclasses `BaseException` on purpose so that an `except Exception` in the code
under test cannot swallow it.

Tests that genuinely need an exception opt in visibly:

```python
@pytest.mark.allow_subprocess      # may spawn real processes
@pytest.mark.allow_system_writes   # may write outside a temp directory
```

`allow_subprocess` is not free: monkeypatching cannot reach into a child
process, so a test carrying it hands its child **both** permissions. Every test
that uses it therefore runs its child under `env -i` with a stub directory as
the entire `PATH`, with `HOME`, `XDG_CONFIG_HOME` and `XDG_CACHE_HOME`
redirected inside `tmp_path`, and asserts afterwards that no command was
missing. Follow that pattern; do not invent a looser one.

---

## Before you open a pull request

```bash
.venv/bin/python -m pytest              # always
```

If you touched `packaging/`:

```bash
./packaging/build.sh <recipe>           # build just what you changed
./packaging/check-current.py            # does the built repo still match the tree?
./packaging/verify-install.sh           # install into clean containers and look
```

If you touched an ISO profile:

```bash
./iso/build.sh --profile release
./iso/test-boot.py --scenario release   # ten scenarios; --help lists them
```

If you touched user-visible strings:

```bash
./po/desktop/extract.sh                 # desktop shell: re-extract and merge
./po/build.sh                           # compile both catalogues
.venv/bin/python -m pytest tests/src/test_ags_i18n.py tests/installer/test_i18n.py
```

Both catalogues are held complete by tests: an English string with no German
translation is a German user silently reading English, and the suite fails on
it.

---

## What a good change looks like here

- **A measurement beats an opinion.** The commit history of this project is
  unusual in that most messages name the thing that measured the claim — a test
  file, a byte count, a contrast ratio, a boot that was watched. If you write
  "this is faster" or "this fixes flicker", say how you know.
- **The reason goes next to the code, not only in the commit.** File and
  function headers in this tree carry the argument for why something is the way
  it is, including what was tried and rejected. That is deliberate: the commit
  is found by someone who already suspects the file, the header is found by
  everyone.
- **Delete dead code rather than marking it deprecated.** A `# DEPRECATED`
  comment is a decision postponed, and the postponement is what costs. Where
  the word does appear in this tree it is a *runtime* message telling a user
  that the command they typed has been replaced and by what — that is a
  redirection, not a tombstone.
- **Keep `SPDX-License-Identifier: GPL-3.0-or-later`** at the top of new
  source files, as the existing ones do.

Commit messages may be German or English — the history is mostly German and the
build scripts and developer docs are English. Either is fine; being specific is
not optional.

---

## What must never be committed

- **Private keys of any kind.** `packaging/keys/` is gitignored in full, and
  that includes the throwaway test key: a private key in a clone is a private
  key in every clone.
- **Build output.** `packaging/out/`, `iso/out/`, `iso/work/`, `po/build/`,
  `*.pkg.tar.zst`, `*.iso` — all gitignored, all reproducible.
- **Anything identifying a particular machine.** Monitor serial numbers, USB
  audio device ids, hardcoded timezones, pixel coordinates from one desk. The
  distribution was extracted from a personal configuration precisely by
  removing these; they must not come back. Machine-specific values come from
  settings or from detection.
- **Screenshots.** `out/` is gitignored. What an image *shows* belongs in a
  report; the image itself does not belong in the history of a branch.

---

## Where things are

```
src/            desktop: templates, the SSOTs, the generator, the zepos-* commands
installer/      installer: core / gui / tui
packaging/      20 PKGBUILD recipes, the build container, signing and publishing
iso/            two archiso profiles and the build that assembles them
lock/ logout/   zepos-lock, zepos-logout (C, GTK4, gtk4-layer-shell)
menu/ settings/ zepos-menu, zepos-settings-gui (Python, GTK4)
plugins/        hyprlaunch, hyprclipx (forked, see plugins/LICENSE)
po/             gettext: zepos-installer and zepos-desktop domains
tests/          110 test files and one isolation guard
docs/specs/     design document and roadmap (German)
```

`packaging/README.md` and `iso/README.md` are long and worth reading before
changing anything under them — they record what was measured, not only what was
decided.

---

## Licence

By contributing you agree that your contribution is licensed under
**GPL-3.0-or-later**, like the rest of the tree.
