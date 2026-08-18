# ZepOS-Basis und Generisierung — Implementierungsplan

> **Redigiert am 2026-08-04, absichtlich und nachvollziehbar.** Dieses
> Dokument nannte jede Vorlage, jeden Firmenrechner und jeden Ort beim
> echten Namen — also genau das, was `docs/specs/2026-08-03-zepos-design.md`
> §6.1 bereits als `internal-*`, `modelA/B`, `cityA/B`, `hypervisor-*` und
> `workstation-01..04` anonymisiert hatte. Damit war der Plan der Schlüssel
> zur Chiffre der Spezifikation, und das Repository soll veröffentlicht
> werden.
>
> Der Plan wurde **an Ort und Stelle bereinigt, nicht ausgelagert.** Gründe,
> in dieser Reihenfolge: er hält Entscheidungen fest, die das Projekt noch
> braucht (die Streichliste und ihre Begründung, die Aufgabenschnitte, die
> verifizierten Ausgangszahlen), und die Spezifikation verweist auf sie.
> Ein Verschieben aus dem Baum hätte die Daten ohnehin nicht entfernt — die
> Git-Historie dieses Repositorys enthält jede frühere Fassung — hätte aber
> das Dokument verloren. Die Platzhalter sind wörtlich die der
> Spezifikation, damit beide Dokumente dasselbe sagen, statt dass eines das
> andere entschlüsselt.
>
> Die Shell-Blöcke in Aufgabe 1 sind dadurch **historisch, nicht
> ausführbar**: sie halten fest, was getan wurde, mit den Platzhalternamen
> statt der echten. Die Streichungen sind seit Aufgabe 1 erledigt.
>
> **Die Historie ist damit nicht bereinigt.** Wer dieses Repository
> veröffentlicht, veröffentlicht auch `git log` — siehe den Abschnitt in
> `tests/origin_data.py` dazu, was diese Wächter leisten und was nicht.

> **Für agentische Bearbeitung:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Aufgabe für Aufgabe umzusetzen. Die Schritte nutzen Checkbox-Syntax (`- [ ]`).

**Ziel:** Das Konfigurationssystem des Icon-Managers nach `~/zepos/src/` überführen, von der Geschäftslogik des vorherigen Arbeitgebers befreien, generisch machen und auf ein Modell umstellen, das sich als Pacman-Paket ausliefern lässt.

**Architektur:** Das heutige `~/.config/iconmanager` ist gleichzeitig Quellcode, Konfiguration und Arbeitsverzeichnis. Ein Paket darf nichts unterhalb von `~` besitzen, deshalb wird getrennt: `/usr/share/zepos/` gehört dem Paket und ist schreibgeschützt, `~/.config/zepos/` gehört dem Nutzer, und der Generator schreibt nach `~/.config/hypr`, `~/.config/waybar` und so weiter. Eine neue Auflösungsschicht (`paths.py`) entscheidet für jeden Zugriff, welcher der beiden Orte gemeint ist.

**Tech-Stack:** Python 3.14, Bash, pytest. Kein neues Fremdpaket.

## Globale Randbedingungen

- Python 3.14. Das Modul `crypt` existiert nicht mehr — nirgends importieren.
- `# SPDX-License-Identifier: GPL-3.0-or-later` als erste Zeile jeder neuen Quelldatei, bei Skripten nach dem Shebang. Bestehende Dateien aus dem Icon-Manager bekommen ihn beim Anfassen.
- Codekommentare, Bezeichner und Docstrings **ausschließlich auf Englisch**. Nutzersichtbare Texte laufen durch `_()` aus `installer/core/i18n.py`, msgids englisch, Übersetzung in **beiden** Katalogdateien.
- Tests prüfen msgid, niemals die Übersetzung.
- Tests laufen mit `.venv/bin/python -m pytest`; `pytest` ist nicht systemweit installiert.
- `tests/conftest.py` ist eine Isolationsschranke: kein Test darf einen echten Prozess starten oder außerhalb eines Temp-Verzeichnisses schreiben. **Der Generator schreibt Dateien — jeder Test muss `tmp_path` benutzen.** Die Schranke nicht aufweichen.
- Injizierte Aufrufbare werden zur Aufrufzeit aufgelöst, nie als Vorgabewert gebunden (`runner: Runner | None = None`, dann `runner = runner or subprocess.run`).
- **Keine Datei im Ursprungs-Repo `~/.config/iconmanager` verändern.** Es wird ausschließlich gelesen.
- Der Zielbaum ist `~/zepos` auf Branch `feat/installer`, aktuell 347 Tests grün. Diese müssen grün bleiben.

## Ausgangslage, verifiziert

| | |
|---|---|
| Getrackte Dateien im Ursprung | 181 |
| Templates im Wurzelverzeichnis | 96 |
| Davon zu löschen | 21 — 16 aus der Namensliste, 5 weitere aus dem Inhalt |
| `templates/deprecated/` | 6 Dateien, toter Code |
| Vorkommen `iconmanager` | 232, davon **198 Pfadangaben** |
| Vorkommen `Icon Manager` | 96 |

---

## Dateistruktur

```
~/zepos/
  src/
    paths.py              NEU  Auflösung System- vs. Nutzerort, Template-Overrides
    icon_definition.py         Icon-SSOT, unverändert übernommen
    style_definition.py        Style-SSOT, Firmenwerte entfernt
    icons_db.py                generiert, nie von Hand editieren
    icon_manager.py            Template-Prozessor, nutzt paths.py
    user_settings.py           Settings-CLI, schema_version ergänzt
    fetch_icons.py
    generate_config.sh         Generator, atomar schreibend
    templates/                 77 (96 − 21 + 2)
    styles/
    profiles/                  generische Beispiele
  tests/src/
    test_paths.py         NEU
    test_settings.py      NEU
    test_generate.py      NEU
    test_vpn_config.py    NEU
    test_monitors.py      NEU
```

`paths.py` ist die einzige neue Kernkomponente. Alles andere ist Übernahme plus Bereinigung.

---

### Task 1: Übernahme und Entkernung

**Dateien:**
- Anlegen: `src/` mit den 181 getrackten Dateien aus `~/.config/iconmanager`, abzüglich der Streichungen
- Test: `tests/src/test_inventory.py`

**Schnittstellen:**
- Nutzt: nichts
- Liefert: den Dateibestand, auf dem alle folgenden Aufgaben arbeiten

Die Übernahme erfolgt über `git ls-files` im Ursprung, nicht über einen Verzeichnis-Kopiervorgang: das Ursprungs-Repo enthält 698 `.backup.*`-Dateien, die nicht getrackt sind und nicht mitkommen dürfen.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_inventory.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""The inventory is a contract: later tasks assume exactly this set."""
from pathlib import Path

SRC = Path("src")

REMOVED_TEMPLATES = [
    "internal-terminals-config", "internal-assistant-config", "internal-logs-config",
    "internal-service-terminals-config", "ide-workspace-layout-config",
    "onedrive-control-config", "onedrive-status-config", "onedrive-debug-config",
    "printer-install-modelA", "printer-install-modelB", "printer-status",
    "kvm-switch-config", "kvm-profile-config",
    "waybar-wttr-cityA-config", "waybar-wttr-cityB-config",
    "network-repair-hypervisor-config",
]

KEPT_TEMPLATES = [
    "waybar-config", "ags-config", "kitty-config", "zshrc-config",
    "hyprland-universal-config", "hyprland-failsafe-config",
    "vpn-connect-script", "network-watchdog-config",
]


def test_source_tree_exists():
    assert (SRC / "templates").is_dir()
    assert (SRC / "generate_config.sh").is_file()


def test_removed_templates_are_gone():
    present = [n for n in REMOVED_TEMPLATES
               if (SRC / "templates" / f"{n}.template").exists()]
    assert present == [], f"should have been deleted: {present}"


def test_kept_templates_are_present():
    missing = [n for n in KEPT_TEMPLATES
               if not (SRC / "templates" / f"{n}.template").exists()]
    assert missing == [], f"missing: {missing}"


def test_dead_template_directory_is_gone():
    """templates/deprecated/ held six files superseded long ago. Carrying
    dead code into a new project is how it becomes permanent."""
    assert not (SRC / "templates" / "deprecated").exists()


def test_no_backup_files_were_carried_over():
    """The origin has 698 untracked .backup.* files. Copying the directory
    instead of the tracked file list would bring all of them."""
    strays = list(SRC.rglob("*.backup.*"))
    assert strays == [], f"{len(strays)} backup files came along"


def test_no_employer_profiles():
    """Profiles named after the previous employer's machines, with monitor
    serial numbers hardcoded. Worthless on any other hardware."""
    for name in ("workstation-01", "workstation-02", "workstation-03", "workstation-04"):
        assert not (SRC / "profiles" / name).exists()


def test_hypervisor_scripts_are_gone():
    assert not (SRC / "hypervisor-scripts").exists()


def test_template_count_is_seventy_five():
    """96 in the origin, 21 removed.

    The original list named 16 and was drawn from template NAMES alone.
    It missed five more that carry a device or a host in their content:
    two wlogout variants for specific notebooks, a wallpaper toggle and a
    hardware monitor for one screen, and a wrapper that ssh's into the
    machine's hypervisor to run a script this project deleted. Searching
    names instead of contents is what let them through.

    The two new generic ones arrive in Task 7, which raises this to 77."""
    assert len(list((SRC / "templates").glob("*.template"))) == 75
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `cd ~/zepos && .venv/bin/python -m pytest tests/src/test_inventory.py -v`
Erwartet: FAIL, `src/templates` existiert nicht

- [ ] **Schritt 3: Die getrackten Dateien übernehmen**

```bash
cd ~/zepos
mkdir -p src
ORIGIN=~/.config/iconmanager

# Nur getrackte Dateien: der Ursprung enthaelt 698 ungetrackte Sicherungen,
# die ein Verzeichnis-Kopiervorgang alle mitnehmen wuerde.
# rsync statt cp, weil die Hausregel des Projekts cp fuer Kopiervorgaenge
# untersagt - hier ohne praktischen Unterschied, aber die Regel gilt.
git -C "$ORIGIN" ls-files -z \
  | grep -zvE '^(\.idea/|\.github/|\.claude/|CLAUDE\.md$)' \
  > /tmp/zepos-carry.list
rsync -a --files-from=/tmp/zepos-carry.list --from0 "$ORIGIN/" src/
rm -f /tmp/zepos-carry.list
```

Ausgenommen sind Editor- und Werkzeugverzeichnisse sowie `CLAUDE.md`: die Regeln darin beschreiben die Arbeit am Ursprungsprojekt, nicht an ZepOS.

- [ ] **Schritt 4: Die Streichungen ausführen**

```bash
cd ~/zepos/src
for t in internal-terminals-config internal-assistant-config internal-logs-config \
         internal-service-terminals-config ide-workspace-layout-config \
         onedrive-control-config onedrive-status-config onedrive-debug-config \
         printer-install-modelA printer-install-modelB printer-status \
         kvm-switch-config kvm-profile-config \
         waybar-wttr-cityA-config waybar-wttr-cityB-config \
         network-repair-hypervisor-config; do
    rm -f "templates/$t.template"
done
rm -rf templates/deprecated hypervisor-scripts
rm -rf profiles/workstation-01 profiles/workstation-02 profiles/workstation-03 profiles/workstation-04
find . -name '*.backup.*' -delete
```

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_inventory.py -v`
Erwartet: 8 Tests PASS

- [ ] **Schritt 6: Gesamte Suite prüfen**

Ausführen: `.venv/bin/python -m pytest -q`
Erwartet: 347 bestehende plus 8 neue, keine Warnungen

- [ ] **Schritt 7: Committen**

```bash
git add src tests/src
git commit -m "feat(src): Konfigurationssystem uebernehmen und entkernen"
```

---

### Task 2: Pfadauflösung

**Dateien:**
- Anlegen: `src/paths.py`
- Test: `tests/src/test_paths.py`

**Schnittstellen:**
- Nutzt: nichts
- Liefert: `system_root() -> Path`, `user_root() -> Path`, `find_template(name: str) -> Path`, `output_root() -> Path`, Konstanten `SYSTEM_ROOT`, `USER_ROOT_ENV = "ZEPOS_USER_ROOT"`, `SYSTEM_ROOT_ENV = "ZEPOS_SYSTEM_ROOT"`

Dies ist die Kernkomponente der Umstellung. 198 der 232 Namensvorkommen sind Pfadangaben, und jede muss künftig durch diese Schicht laufen, statt einen festen Ort zu benennen.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_paths.py
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from src.paths import (
    SYSTEM_ROOT_ENV, USER_ROOT_ENV,
    find_template, output_root, system_root, user_root,
)


def test_system_root_defaults_to_the_package_location():
    assert str(system_root()) == "/usr/share/zepos"


def test_user_root_defaults_below_the_home_config():
    assert str(user_root()).endswith(".config/zepos")


def test_both_roots_are_overridable_for_testing(tmp_path, monkeypatch):
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    assert system_root() == tmp_path / "sys"
    assert user_root() == tmp_path / "usr"


def test_a_user_template_wins_over_the_system_one(tmp_path, monkeypatch):
    """The whole point of the split: pacman -Syu updates the system
    template without touching what the user changed."""
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    for root in ("sys", "usr"):
        (tmp_path / root / "templates").mkdir(parents=True)
    (tmp_path / "sys/templates/waybar-config.template").write_text("system")
    (tmp_path / "usr/templates/waybar-config.template").write_text("user")

    assert find_template("waybar-config").read_text() == "user"


def test_the_system_template_is_used_when_the_user_has_none(tmp_path, monkeypatch):
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    (tmp_path / "sys/templates").mkdir(parents=True)
    (tmp_path / "sys/templates/waybar-config.template").write_text("system")

    assert find_template("waybar-config").read_text() == "system"


def test_a_missing_template_names_both_places_it_looked(tmp_path, monkeypatch):
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    with pytest.raises(FileNotFoundError) as excinfo:
        find_template("does-not-exist")
    message = str(excinfo.value)
    assert "sys" in message and "usr" in message


def test_a_template_name_cannot_escape_its_directory(tmp_path, monkeypatch):
    """Template names reach this from configuration files. A name of
    '../../etc/passwd' must not resolve outside the template directory."""
    monkeypatch.setenv(SYSTEM_ROOT_ENV, str(tmp_path / "sys"))
    monkeypatch.setenv(USER_ROOT_ENV, str(tmp_path / "usr"))
    with pytest.raises(ValueError):
        find_template("../../etc/passwd")


def test_output_root_is_the_config_home_not_the_package(monkeypatch, tmp_path):
    """Generated files belong to the user, never below /usr/share."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert output_root() == tmp_path
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_paths.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'src.paths'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# src/paths.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where things live once ZepOS ships as a package.

The origin project kept sources, configuration and generated output in one
directory under the user's home. A pacman package may own nothing below ~,
so the three roles are separated here:

  /usr/share/zepos     templates, generator, SSOT   owned by the package
  ~/.config/zepos      settings and overrides       owned by the user
  ~/.config/<app>      generated output             written by the generator

Both roots are overridable through the environment so tests never touch
the real ones.
"""
from __future__ import annotations

import os
from pathlib import Path

SYSTEM_ROOT = Path("/usr/share/zepos")
SYSTEM_ROOT_ENV = "ZEPOS_SYSTEM_ROOT"
USER_ROOT_ENV = "ZEPOS_USER_ROOT"
TEMPLATE_SUFFIX = ".template"


def system_root() -> Path:
    override = os.environ.get(SYSTEM_ROOT_ENV)
    return Path(override) if override else SYSTEM_ROOT


def user_root() -> Path:
    override = os.environ.get(USER_ROOT_ENV)
    if override:
        return Path(override)
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "zepos"


def output_root() -> Path:
    """Where generated configuration goes - never below the package root."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    return Path(config_home) if config_home else Path.home() / ".config"


def find_template(name: str) -> Path:
    """Resolve a template name, user copy first.

    A user override wins so that updating the package does not discard
    what someone changed. Without this, pacman -Syu would silently revert
    every local edit.
    """
    if "/" in name or name.startswith("."):
        raise ValueError(f"invalid template name: {name!r}")

    candidates = [
        user_root() / "templates" / f"{name}{TEMPLATE_SUFFIX}",
        system_root() / "templates" / f"{name}{TEMPLATE_SUFFIX}",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    looked = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"template {name!r} not found; looked in: {looked}")
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_paths.py -v`
Erwartet: 8 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add src/paths.py tests/src/test_paths.py
git commit -m "feat(src): Pfadaufloesung mit Nutzer-Overrides"
```

---

### Task 3: Versionierte Nutzereinstellungen

**Dateien:**
- Ändern: `src/user_settings.py`
- Anlegen: `src/settings.py`
- Test: `tests/src/test_settings.py`

**Schnittstellen:**
- Nutzt: `user_root` aus Task 2
- Liefert: `SCHEMA_VERSION: int = 1`, `load(path: Path | None = None) -> dict`, `save(data: dict, path: Path | None = None) -> None`, `defaults() -> dict`

Ohne Versionsfeld ist bei der ersten Migration unbekannt, welche Struktur eine Datei auf einem fremden System hat. Eine Zeile jetzt, geraten werden müsste es später.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_settings.py
# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest

from src.settings import SCHEMA_VERSION, defaults, load, save


def test_defaults_carry_the_schema_version():
    assert defaults()["schema_version"] == SCHEMA_VERSION


def test_defaults_contain_no_employer_values():
    """The origin hardcoded a corporate domain, two internal DNS servers
    and a file server hostname. None of that belongs in a default."""
    blob = json.dumps(defaults()).lower()
    for forbidden in EMPLOYER_VALUES:   # siehe tests/origin_data.py
        assert forbidden not in blob, f"{forbidden} survives in the defaults"


def test_roundtrip_preserves_values(tmp_path):
    path = tmp_path / "user-settings.json"
    data = defaults()
    data["vpn"]["dns"]["search_domain"] = "example.org"
    save(data, path)
    assert load(path)["vpn"]["dns"]["search_domain"] == "example.org"


def test_a_missing_file_yields_the_defaults(tmp_path):
    assert load(tmp_path / "absent.json") == defaults()


def test_an_unknown_schema_version_is_refused(tmp_path):
    path = tmp_path / "user-settings.json"
    path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="99"):
        load(path)


def test_a_file_without_a_version_is_refused(tmp_path):
    """A file predating the versioning cannot be interpreted safely -
    refusing is honest, guessing is not."""
    path = tmp_path / "user-settings.json"
    path.write_text(json.dumps({"vpn": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load(path)


def test_saved_file_is_not_world_readable(tmp_path):
    """Settings may carry a VPN pre-shared key."""
    import stat
    path = tmp_path / "user-settings.json"
    save(defaults(), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_settings.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'src.settings'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# src/settings.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""User settings, versioned from the first release.

Without a version field the first migration would have to guess what
structure a file on someone else's machine has. The field costs one line
now and cannot be added retroactively.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .paths import user_root

SCHEMA_VERSION = 1
FILENAME = "user-settings.json"


def defaults() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "vpn": {
            "server": "",
            "connection_name": "work",
            "dns": {"servers": [], "search_domain": ""},
            "test_host": "",
            "routed_networks": [],
        },
        "weather": {"location": ""},
        "watchdog": {"interval_seconds": 60, "test_host": "1.1.1.1"},
    }


def _path(path: Path | None) -> Path:
    return path if path is not None else user_root() / FILENAME


def load(path: Path | None = None) -> dict[str, Any]:
    target = _path(path)
    if not target.is_file():
        return defaults()

    data = json.loads(target.read_text(encoding="utf-8"))
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {version}, expected {SCHEMA_VERSION}"
        )
    return data


def save(data: dict[str, Any], path: Path | None = None) -> None:
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Narrow the umask around the write: the file may hold a VPN
    # pre-shared key, and creating it at the default 0644 would expose it
    # to every local user until the chmod lands.
    previous = os.umask(0o077)
    try:
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    finally:
        os.umask(previous)
    target.chmod(0o600)
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_settings.py -v`
Erwartet: 7 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add src/settings.py tests/src/test_settings.py
git commit -m "feat(src): versionierte Nutzereinstellungen mit engen Rechten"
```

---

### Task 4: Umbenennung

**Dateien:**
- Ändern: alle Dateien unter `src/`, die `iconmanager` oder `Icon Manager` enthalten
- Test: `tests/src/test_naming.py`

**Schnittstellen:**
- Nutzt: `paths.py` aus Task 2
- Liefert: einen Baum ohne Verweise auf das Ursprungsprojekt

232 Vorkommen, davon **198 Pfadangaben**. Die Pfadangaben sind keine Textersetzung: je nach Zugriffsart wird daraus der System- oder der Nutzerort.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_naming.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""No reference to the origin project may survive.

A leftover path is worse than a leftover word: it points at a directory
that does not exist on an installed system, and the failure shows up at
runtime on someone else's machine.
"""
import re
from pathlib import Path

SRC = Path("src")
FORBIDDEN = re.compile(r"iconmanager|Icon\s+Manager", re.IGNORECASE)


def _sources():
    for path in SRC.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sh", ".template", ".conf", ".json"}:
            yield path


def test_no_file_mentions_the_origin_project():
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path}:{number}")
    assert offenders == [], "origin references left: " + ", ".join(offenders[:10])


def test_no_hardcoded_home_config_path():
    """Templates used to write $HOME/.config/iconmanager directly. Every
    such place must now go through paths.py, or a packaged install writes
    into a directory that does not exist."""
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\$HOME/\.config/zepos|~/\.config/zepos", text):
            if path.name not in {"paths.py", "test_naming.py"}:
                offenders.append(str(path))
    assert offenders == [], (
        "hardcoded user paths outside paths.py: " + ", ".join(offenders[:10])
    )


def test_generator_reads_from_the_system_root():
    text = (SRC / "generate_config.sh").read_text(encoding="utf-8")
    assert "ZEPOS_SYSTEM_ROOT" in text, (
        "the generator must honour the overridable system root, or tests "
        "cannot run without touching /usr/share"
    )
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_naming.py -v`
Erwartet: FAIL, hunderte Treffer im ersten Test

- [ ] **Schritt 3: Die reinen Namensvorkommen ersetzen**

```bash
cd ~/zepos/src
grep -rlIZ 'Icon Manager' . | xargs -0 -r sed -i 's/Icon Manager/ZepOS/g'
grep -rlIZ 'iconmanager' . --include='*.py' --include='*.sh' --include='*.template' \
  | xargs -0 -r sed -i 's/iconmanager/zepos/g'
```

- [ ] **Schritt 4: Die Pfadangaben von Hand auflösen**

Die vorige Ersetzung hat aus jedem `~/.config/iconmanager` ein `~/.config/zepos` gemacht. Das ist für **lesende** Zugriffe falsch: Templates und Generator liegen im System, nicht beim Nutzer.

Jede Fundstelle einzeln entscheiden:

| Zugriff | Wird zu |
|---|---|
| Template lesen | `find_template(name)` aus `paths.py` |
| Style oder SSOT lesen | `$ZEPOS_SYSTEM_ROOT` bzw. `system_root()` |
| Nutzereinstellung lesen oder schreiben | `user_root()` |
| Erzeugte Datei schreiben | `output_root()` |

In `generate_config.sh` am Kopf einführen:

```bash
ZEPOS_SYSTEM_ROOT="${ZEPOS_SYSTEM_ROOT:-/usr/share/zepos}"
ZEPOS_USER_ROOT="${ZEPOS_USER_ROOT:-${XDG_CONFIG_HOME:-$HOME/.config}/zepos}"
ZEPOS_OUTPUT_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}"

# Ein Nutzer-Template sticht das System-Template. Ohne diese Reihenfolge
# verwirft ein Paketupdate jede lokale Anpassung.
find_template() {
    local name="$1"
    if [ -f "$ZEPOS_USER_ROOT/templates/$name.template" ]; then
        printf '%s\n' "$ZEPOS_USER_ROOT/templates/$name.template"
    elif [ -f "$ZEPOS_SYSTEM_ROOT/templates/$name.template" ]; then
        printf '%s\n' "$ZEPOS_SYSTEM_ROOT/templates/$name.template"
    else
        echo "template not found: $name" >&2
        return 1
    fi
}
```

Die Kommentarköpfe der Templates verweisen auf den Bearbeitungsort. Sie müssen auf den **Nutzer**-Ort zeigen, denn dort legt man einen Override an:

```
# Generated by ZepOS - DO NOT EDIT DIRECTLY!
# To customise, copy this file to ~/.config/zepos/templates/<name>.template
```

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_naming.py -v`
Erwartet: 3 Tests PASS

- [ ] **Schritt 6: Gesamte Suite prüfen und committen**

```bash
.venv/bin/python -m pytest -q
git add src tests/src
git commit -m "refactor(src): Umbenennung und Trennung von System- und Nutzerort"
```

---

### Task 5: VPN generisch

**Dateien:**
- Ändern: `src/templates/vpn-connect-script.template`, `src/templates/ags-vpn-settings.template`, `src/style_definition.py`, `src/user_settings.py`
- Test: `tests/src/test_vpn_config.py`

**Schnittstellen:**
- Nutzt: `settings.load` aus Task 3
- Liefert: eine VPN-Konfiguration ohne festverdrahtete Firmenwerte, mit beliebig vielen gerouteten Netzen

Die Funktion bleibt vollständig erhalten. Entfernt werden ausschließlich die Werte des vorherigen Arbeitgebers, und die drei fest ausgeschriebenen Child-SAs werden aus einer Liste **erzeugt**.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_vpn_config.py
# SPDX-License-Identifier: GPL-3.0-or-later
import re
from pathlib import Path

from src.settings import defaults
from src.vpn import swanctl_children, swanctl_config

SRC = Path("src")


def test_no_employer_values_remain_in_the_templates():
    for name in ("vpn-connect-script", "ags-vpn-settings", "vpn-status-config"):
        path = SRC / "templates" / f"{name}.template"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in EMPLOYER_VALUES:   # siehe tests/origin_data.py
            assert forbidden not in text, f"{forbidden} survives in {name}"


def test_one_routed_network_yields_one_child():
    children = swanctl_children("work", ["10.0.0.0/8"])
    assert len(re.findall(r"work-\d+ \{", children)) == 1


def test_five_routed_networks_yield_five_children():
    """The origin wrote exactly three, spelled out. A user with five
    networks had no way to express that."""
    nets = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
            "100.64.0.0/10", "198.18.0.0/15"]
    children = swanctl_children("work", nets)
    assert len(re.findall(r"work-\d+ \{", children)) == 5
    for net in nets:
        assert f"remote_ts = {net}" in children


def test_no_routed_networks_is_refused():
    """A tunnel that routes nothing silently connects and carries no
    traffic - the user would see 'connected' and reach nothing."""
    try:
        swanctl_children("work", [])
    except ValueError:
        return
    raise AssertionError("an empty network list must be refused")


def test_config_uses_the_configured_server_not_a_constant():
    cfg = dict(defaults())
    cfg["vpn"]["server"] = "vpn.example.org"
    cfg["vpn"]["routed_networks"] = ["10.0.0.0/8"]
    out = swanctl_config(cfg)
    assert "vpn.example.org" in out


def test_defaults_produce_no_usable_config():
    """Shipping a working VPN config nobody asked for would connect a
    fresh installation to a stranger's network."""
    try:
        swanctl_config(defaults())
    except ValueError:
        return
    raise AssertionError("an unconfigured VPN must be refused, not guessed")
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_vpn_config.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'src.vpn'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# src/vpn.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate a swanctl configuration from user settings.

The origin spelled out three child security associations for the
employer's networks. Anyone with a different number of routed networks had
no way to express it, so the list drives the output here instead.
"""
from __future__ import annotations

from typing import Any

PROPOSALS = (
    "aes128-sha1-modp1536,aes256-sha1-modp1536,"
    "aes128-sha256-modp1536,aes256-sha256-modp1536"
)


def swanctl_children(connection: str, routed_networks: list[str]) -> str:
    if not routed_networks:
        raise ValueError(
            "a VPN connection with no routed networks would carry no traffic"
        )

    blocks = []
    for index, network in enumerate(routed_networks, start=1):
        blocks.append(f"""            {connection}-{index} {{
                remote_ts = {network}
                rekey_time = 43200s
                life_time = 43200s
                dpd_action = restart
                esp_proposals = {PROPOSALS}
                mode = tunnel
                replay_window = 32
                start_action = start
                policies = yes
            }}""")
    return "\n".join(blocks)


def swanctl_config(settings: dict[str, Any]) -> str:
    vpn = settings.get("vpn", {})
    server = vpn.get("server", "")
    if not server:
        raise ValueError("no VPN server configured")

    connection = vpn.get("connection_name") or "work"
    children = swanctl_children(connection, vpn.get("routed_networks", []))

    return f"""connections {{
    {connection} {{
        version = 1
        aggressive = yes
        proposals = {PROPOSALS}
        dpd_delay = 30s
        dpd_timeout = 120s
        encap = yes
        mobike = no
        remote {{
            auth = psk
            id = {server}
        }}
        remote_addrs = {server}
        vips = 0.0.0.0
        children {{
{children}
        }}
    }}
}}
"""
```

- [ ] **Schritt 4: Die Templates auf die Einstellungen umstellen**

In `vpn-connect-script.template` die festverdrahteten Werte durch Platzhalter ersetzen, die der Generator aus den Einstellungen füllt: `{{STYLE_VPN_SERVER}}` bleibt, `{{STYLE_VPN_DNS_SERVERS}}`, `{{STYLE_VPN_SEARCH_DOMAIN}}` und `{{STYLE_VPN_TEST_HOST}}` kommen hinzu. Der Block mit den drei ausgeschriebenen Child-SAs entfällt zugunsten von `{{STYLE_VPN_CHILDREN}}`, das `swanctl_children` liefert.

In `style_definition.py` die Vorgabewerte auf leer setzen — kein Default, der auf ein fremdes Netz zeigt.

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_vpn_config.py -v`
Erwartet: 6 Tests PASS

- [ ] **Schritt 6: Committen**

```bash
git add src/vpn.py src/templates src/style_definition.py tests/src/test_vpn_config.py
git commit -m "feat(src): VPN generisch, Child-SAs aus der Netzliste erzeugt"
```

---

### Task 6: Monitor-Erkennung über EDID

**Dateien:**
- Anlegen: `src/monitors.py`
- Ändern: `src/templates/hypr-monitor-detect-config.template`
- Test: `tests/src/test_monitors.py`

**Schnittstellen:**
- Nutzt: nichts
- Liefert: `detect(runner=None) -> list[Monitor]`, `Monitor(name, description, x, width, height, refresh, scale, transform)`, `ordered(monitors)`, `layout(monitors) -> list[tuple[Monitor, list[int]]]`, `workspace_assignments(monitors) -> str`

Die Erkennung läuft heute über `$(hostname)` und lädt ein vorgefertigtes Profil mit fest verdrahteten Seriennummern. Auf jedem fremden Rechner greift das ins Leere.

> **Korrektur beim Umsetzen.** Die Entwürfe unten waren an fünf Stellen falsch;
> umgesetzt ist jeweils die berichtigte Fassung:
>
> 1. **Keine `monitor=`-Zeilen.** `profile_from()` sollte Modus-Zeilen
>    (`monitor=desc:…,1920x1200@60,…`) schreiben. Die gehören nach
>    `~/.config/hypr/monitors.conf`, und die gehört der GUI nwg-displays.
>    Erzeugt werden Workspace-Zuordnungen (`workspace=N,monitor:desc:…`),
>    deshalb heißt die Funktion `workspace_assignments()`. Der Name
>    `profile_from` wäre in diesem Repo doppelt belegt: „Profil" ist das
>    Profilsystem, das `workspaces.conf` besitzt.
> 2. **Die Dataclass war zu klein.** Ohne `name` ist ein Notebook-Panel nicht
>    von einem externen Schirm zu unterscheiden, ohne `x` stehen die Monitore
>    in der Reihenfolge, in der die Kabel gesteckt wurden, und `transform`
>    braucht die Sicherheitsprüfung des Skripts.
> 3. **`detect()` überlebte kaputte Ausgabe nicht.** `json.loads()` wirft bei
>    leerem oder unvollständigem stdout einen `ValueError` — genau den Typ,
>    mit dem eine leere Monitorliste abgelehnt wird. Wird zu `RuntimeError`
>    übersetzt: ein Aufrufer soll einen Typ für „der Compositor hat nicht
>    brauchbar geantwortet" fangen können.
> 4. **Der Rückfall steht nicht in diesem Skript.**
>    `hyprland-failsafe-config.template` ist eine eigene Datei, auf die
>    `hypr-emergency-reset-config.template` zeigt — nicht dieses Skript. Der
>    eigene Rückfall lautet „alle Workspaces auf den ersten erreichbaren
>    Monitor"; der bleibt, ebenso `test_config_safety`.
> 5. **Niemand las die erzeugte Datei.** Das Skript schrieb
>    `workspaces-generated.conf`, die Hyprland-Konfiguration las
>    `workspaces.conf` — die berechnete Zuordnung landete in einer Datei, die
>    kein Compositor öffnet. `hyprland-universal-config.template` sourced sie
>    jetzt **nach** `workspaces.conf` (Hyprland ersetzt bei gleicher
>    Workspace-Nummer die frühere Regel: `CWorkspaceRuleManager::replaceOrAdd`),
>    und `generate_config.sh` legt sie als Platzhalter an. Gemessen an
>    Hyprland 0.55.4: `source =` auf eine fehlende Datei ist ein
>    Konfigurationsfehler — `Hyprland --verify-config` endet mit Status 1 und
>    „source= globbing error: found no match".

> **Nachtrag nach Abschluss.** Das in Schritt 5 genannte „Abschlusssignal" war
> keins. `test_no_device_or_employer_names_remain` sucht sieben Geräte- und
> Firmennamen; Seriennummern von Monitoren und Fabrikate standen in diesem
> Muster nie. Der Test wurde grün, während drei weitere Dateien denselben
> Schreibtisch fest verdrahtet hatten — und eine vierte ihn im Klartext
> beschrieb:
>
> * `waybar-workspace-detect-config.template` wählte drei Schirme über ihre
>   EDID-Seriennummern und leitete die Workspace-Aufteilung ein **zweites Mal**
>   her, aus dem aktiven Profil. Zwei Herleitungen derselben Aufteilung gehen
>   beim ersten umgesteckten Kabel auseinander, und der Nutzer sieht das als
>   Workspace-Knöpfe auf einem Schirm, auf dem die Fenster nie erscheinen.
>   Beide Seiten kommen jetzt aus `monitors.py`: `--waybar` rendert dieselbe
>   `layout()` in der Sprache, die die Bar liest (Anschlussnamen statt `desc:`,
>   das Waybar nicht kennt).
> * `grid-wallpaper-toggle.template` verteilte Hintergründe über den
>   EDID-Herstellernamen und sortierte hochkant stehende Schirme über zwei
>   feste x-Schwellen. Jeder Schirm bekommt sein Raster jetzt in seiner
>   eigenen Größe; der Zweig für Hochformat rechnete ohnehin mit Variablen,
>   die es seit Task 1 nicht mehr gibt.
> * `tty-monitor-rotation-config.template` zählte DP-Anschlüsse, tat unterhalb
>   von dreien nichts und schrieb sonst die feste Drehung 3. Die Drehung folgt
>   jetzt der gemessenen Lage der Schirme; ohne erreichbaren Compositor fragt
>   das Skript nach dem Winkel, statt einen zu raten.
> * `hypr-shortcuts-config.template` nannte in einer festen Liste zwei
>   Anschlüsse, zwei Fabrikate und eine Workspace-Aufteilung — ein dritter
>   Ort, der eine Aufteilung behauptet. Er liest sie jetzt aus derselben
>   `layout()`.
>
> Die Lücke selbst ist zu: `test_no_hardcoded_monitor_identity_remains` prüft
> **Formen** statt einer Namensliste — seriennummernförmige Tokens,
> Herstellernamen von Displays, Modellbezeichnungen neben einem Feld, das eine
> Monitoridentität liest — und benennt im Docstring, was es nicht abdeckt.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_monitors.py
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import subprocess

import pytest

from src.monitors import Monitor, detect, profile_from

SAMPLE = json.dumps([
    {"name": "eDP-1", "description": "Acme Display 12345",
     "width": 1920, "height": 1200, "refreshRate": 60.0, "scale": 1.0},
    {"name": "DP-2", "description": "Other Corp Screen 67890",
     "width": 3840, "height": 2160, "refreshRate": 60.0, "scale": 1.0},
])


def _runner(stdout, returncode=0):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return run


def test_monitors_are_read_from_the_running_compositor():
    found = detect(runner=_runner(SAMPLE))
    assert [m.description for m in found] == [
        "Acme Display 12345", "Other Corp Screen 67890"]


def test_resolution_and_scale_survive():
    first = detect(runner=_runner(SAMPLE))[0]
    assert (first.width, first.height, first.scale) == (1920, 1200, 1.0)


def test_the_layout_is_generated_from_what_is_attached():
    """The origin loaded a prewritten profile matching a known hostname.
    Nothing about the machine's name says what is plugged into it."""
    text = workspace_assignments(detect(runner=_runner(SAMPLE)))
    # Eine Zuordnung, keine Modus-Zeile: die Auflösung gehört
    # nwg-displays. Die Behauptung "1920x1200@60" aus dem Entwurf faellt
    # damit ersatzlos weg.
    assert "workspace=1,monitor:desc:Acme Display 12345" in text


def test_an_empty_monitor_list_is_refused():
    """No monitors means the query failed - writing an empty profile would
    leave the user with a black screen and no way back."""
    with pytest.raises(ValueError):
        profile_from([])


def test_a_failing_query_raises_rather_than_returning_nothing():
    with pytest.raises(RuntimeError):
        detect(runner=_runner("", returncode=1))


def test_a_missing_compositor_raises_a_clear_error():
    """hyprctl is absent outside a session. FileNotFoundError arrives
    before any CompletedProcess exists, so a returncode check never sees it."""
    def run(cmd, **kw):
        raise FileNotFoundError("hyprctl")

    with pytest.raises(RuntimeError, match="hyprctl"):
        detect(runner=run)


def test_the_hostname_plays_no_part():
    from pathlib import Path
    text = Path("src/templates/hypr-monitor-detect-config.template").read_text(
        encoding="utf-8")
    assert "hostname" not in text.lower(), (
        "monitor detection must not depend on the machine's name")
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_monitors.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'src.monitors'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# src/monitors.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Detect monitors from the running compositor.

The origin matched the machine's hostname against a list of known
workstations and loaded a profile with serial numbers written into it.
That works on exactly those machines and nowhere else. What is actually
attached is a question only the compositor can answer.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class Monitor:
    description: str
    width: int
    height: int
    refresh: float
    scale: float


def detect(*, runner: Runner | None = None) -> list[Monitor]:
    # Resolved here, not bound as a default: a default argument captures
    # subprocess.run at import time, which the test suite's isolation
    # guard cannot intercept.
    runner = runner or subprocess.run

    try:
        result = runner(
            ["hyprctl", "monitors", "-j"], capture_output=True, text=True
        )
    except OSError as exc:
        raise RuntimeError(f"could not run hyprctl: {exc}") from exc

    if result.returncode != 0:
        raise RuntimeError(f"hyprctl failed: {result.stderr.strip()}")

    return [
        Monitor(
            description=entry.get("description", ""),
            width=int(entry.get("width", 0)),
            height=int(entry.get("height", 0)),
            refresh=float(entry.get("refreshRate", 0.0)),
            scale=float(entry.get("scale", 1.0)),
        )
        for entry in json.loads(result.stdout)
    ]


def workspace_assignments(monitors: list[Monitor]) -> str:
    if not monitors:
        raise ValueError(
            "refusing to write workspace assignments with no monitors - the "
            "query failed, and an empty block would drop the layout the user "
            "already had"
        )

    lines = ["# Generated by ZepOS from the attached monitors.", ""]
    for monitor, workspaces in layout(monitors):
        target = selector(monitor, monitors)
        lines.extend(f"workspace={number},monitor:{target}"
                     for number in workspaces)
    return "\n".join(lines) + "\n"
```

`selector()` schneidet die Beschreibung am ersten Komma ab — eine
Workspace-Regel ist kommasepariert, und EDID-Herstellerfelder enthalten Kommata
(„Acme, Inc."). Hyprland akzeptiert die zerschnittene Zeile wortlos
(`--verify-config`: „config ok") und sucht dann einen Monitor `desc:Acme`, den
niemand hat. Wird die gekürzte Beschreibung dadurch mehrdeutig — Hyprland
vergleicht `desc:` als Präfix —, tritt der Anschlussname an ihre Stelle.

`layout()` verallgemeinert die beiden Hostnamen-Zweige des Ursprungs und
reproduziert beide: drei Externe plus Panel ergibt 1-3, 4-6, 7-9 und 10; ein
Externer plus Panel ergibt 1-9 und 10.

- [ ] **Schritt 4: Das Template umstellen**

`hypr-monitor-detect-config.template` wertet den Hostnamen nicht mehr aus,
sondern ruft `python3 "$ZEPOS_SYSTEM_ROOT/monitors.py"` auf. `zepos-generate`
gibt es erst mit Task 9; das Skript um ein Kommando herum zu bauen, das nicht
existiert, hätte es unbenutzbar gemacht. Wenn die CLI kommt, ruft sie dieselben
Funktionen — die Naht ist eine Zeile im Template.

Der Rückfall dieses Skripts lautet „alle Workspaces auf den ersten erreichbaren
Monitor" (siehe Korrektur 4 oben), und `test_config_safety` bleibt — geprüft
wird jetzt allerdings **vor** dem Verschieben statt danach: der Ursprung schob
die Datei erst an ihren Platz und meldete anschließend „configuration not
applied" über eine Datei, die bereits aktiv war.

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_monitors.py -v`
Erwartet: 39 Tests PASS. Danach die gesamte Suite: der xfail(strict) auf
`test_no_device_or_employer_names_remain` wird zum XPASS-FEHLER — das ist das
Abschlusssignal. Der Marker wird entfernt, der Test bleibt grün.

- [ ] **Schritt 6: Committen**

```bash
git add src/monitors.py src/templates/hypr-monitor-detect-config.template \
        src/templates/hyprland-universal-config.template src/generate_config.sh \
        tests/src/test_monitors.py tests/src/test_inventory.py
git commit -m "feat(src): Monitore ueber EDID erkennen statt ueber den Hostnamen"
```

---

### Task 7: Die zwei neuen generischen Templates

**Dateien:**
- Anlegen: `src/templates/printer-manager-config.template`, `src/templates/waybar-weather-config.template`
- Test: `tests/src/test_new_templates.py`

**Schnittstellen:**
- Nutzt: `settings.load` aus Task 3
- Liefert: Ersatz für die fünf gelöschten modell- und ortsgebundenen Templates

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_new_templates.py
# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

TEMPLATES = Path("src/templates")


def test_the_printer_template_exists():
    assert (TEMPLATES / "printer-manager-config.template").exists()


def test_the_printer_template_names_no_model():
    """It replaces printer-install-modelA and -modelB, which each drove one
    specific device."""
    text = (TEMPLATES / "printer-manager-config.template").read_text(encoding="utf-8")
    for model in ("modelA", "modelB"):
        assert model.lower() not in text.lower()


def test_the_printer_template_discovers_devices():
    text = (TEMPLATES / "printer-manager-config.template").read_text(encoding="utf-8")
    assert "lpstat" in text or "lpinfo" in text, (
        "a generic printer dialog must find what is there, not assume it")


def test_the_weather_template_exists():
    assert (TEMPLATES / "waybar-weather-config.template").exists()


def test_the_weather_template_names_no_city():
    text = (TEMPLATES / "waybar-weather-config.template").read_text(encoding="utf-8")
    for city in ("cityA", "cityB"):
        assert city not in text.lower()


def test_the_weather_template_takes_its_location_from_the_settings():
    text = (TEMPLATES / "waybar-weather-config.template").read_text(encoding="utf-8")
    assert "{{STYLE_WEATHER_LOCATION}}" in text


def test_the_template_count_is_seventy_seven():
    assert len(list(TEMPLATES.glob("*.template"))) == 77
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_new_templates.py -v`
Erwartet: FAIL, beide Dateien fehlen

- [ ] **Schritt 3: Die Templates anlegen**

```bash
# src/templates/printer-manager-config.template
#!/bin/bash
# Generated by ZepOS - DO NOT EDIT DIRECTLY!
# To customise, copy to ~/.config/zepos/templates/printer-manager-config.template
#
# Replaces the origin's two model-specific install scripts. Those drove one
# printer each and were useless on any other device.

case "$1" in
    list)
        lpstat -p 2>/dev/null | awk '{print $2}'
        ;;
    discover)
        # Whatever is reachable, rather than a device we assumed
        lpinfo -v 2>/dev/null | grep -E '^(network|direct)' | awk '{print $2}'
        ;;
    menu)
        printers=$(lpstat -p 2>/dev/null | awk '{print $2}')
        if [ -z "$printers" ]; then
            notify-send "{{ICON_PRINTER}} ZepOS" "No printer configured."
            exit 0
        fi
        printf '%s\n' "$printers" | wofi --dmenu --prompt "{{ICON_PRINTER}} Printer"
        ;;
    status)
        lpstat -t 2>/dev/null || echo "cups is not running"
        ;;
    *)
        echo "usage: $0 {list|discover|menu|status}" >&2
        exit 1
        ;;
esac
```

```bash
# src/templates/waybar-weather-config.template
#!/bin/bash
# Generated by ZepOS - DO NOT EDIT DIRECTLY!
# To customise, copy to ~/.config/zepos/templates/waybar-weather-config.template
#
# Replaces the origin's two location-specific scripts. The location comes
# from the user settings now.

LOCATION="{{STYLE_WEATHER_LOCATION}}"

if [ -z "$LOCATION" ]; then
    printf '{"text":"","tooltip":"No location configured"}\n'
    exit 0
fi

response=$(curl -fsS --max-time 5 "https://wttr.in/${LOCATION}?format=j1" 2>/dev/null) || {
    printf '{"text":"{{ICON_WEATHER_UNKNOWN}}","tooltip":"Weather unavailable"}\n'
    exit 0
}

temp=$(printf '%s' "$response" | jq -r '.current_condition[0].temp_C')
desc=$(printf '%s' "$response" | jq -r '.current_condition[0].weatherDesc[0].value')
printf '{"text":"%s°C","tooltip":"%s, %s"}\n' "$temp" "$LOCATION" "$desc"
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_new_templates.py -v`
Erwartet: 7 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add src/templates tests/src/test_new_templates.py
git commit -m "feat(src): generischer Drucker-Dialog und Wetter-Widget"
```

---

### Task 8: Atomare Erzeugung

**Dateien:**
- Ändern: `src/generate_config.sh`
- Anlegen: `src/validate_output.py`
- Test: `tests/src/test_generate.py`

**Schnittstellen:**
- Nutzt: `paths.py`, `settings.py`
- Liefert: `validate(directory: Path) -> list[str]` — leere Liste bedeutet ausliefern

Der heutige Generator schreibt direkt nach `~/.config/hypr/`. Bricht er auf halber Strecke ab, bleibt eine kaputte `hyprland.conf` liegen — ein nicht startender Desktop.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_generate.py
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from src.validate_output import validate


def test_clean_output_has_no_findings(tmp_path):
    (tmp_path / "hyprland.conf").write_text("monitor=,preferred,auto,1\n")
    (tmp_path / "config.json").write_text(json.dumps({"layer": "top"}))
    (tmp_path / "helper.sh").write_text("#!/bin/bash\necho ok\n")
    assert validate(tmp_path) == []


def test_an_unresolved_placeholder_is_reported(tmp_path):
    """A surviving {{...}} means a template referenced something the SSOT
    does not define. Shipping it writes a literal {{ICON_FOO}} into the
    user's bar."""
    (tmp_path / "hyprland.conf").write_text("bar_text = {{ICON_MISSING}}\n")
    findings = validate(tmp_path)
    assert any("ICON_MISSING" in f for f in findings)


def test_broken_shell_is_reported(tmp_path):
    (tmp_path / "helper.sh").write_text("#!/bin/bash\nif [ -z ; then\n")
    assert any("helper.sh" in f for f in validate(tmp_path))


def test_broken_json_is_reported(tmp_path):
    (tmp_path / "config.json").write_text('{"layer": "top",}')
    assert any("config.json" in f for f in validate(tmp_path))


def test_a_plugin_line_without_the_object_is_reported(tmp_path):
    """Hyprland refuses to load a plugin whose .so is absent. Writing the
    line anyway costs the user their session."""
    (tmp_path / "hyprland.conf").write_text(
        "plugin = /usr/lib/hyprland/plugins/absent.so\n")
    assert any("absent.so" in f for f in validate(tmp_path))


def test_an_existing_plugin_object_is_accepted(tmp_path):
    plugin = tmp_path / "present.so"
    plugin.write_bytes(b"\x7fELF")
    (tmp_path / "hyprland.conf").write_text(f"plugin = {plugin}\n")
    assert validate(tmp_path) == []
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_generate.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'src.validate_output'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# src/validate_output.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check generated configuration before it replaces the working one.

The origin wrote straight into the live configuration directory. An abort
halfway through left a broken hyprland.conf behind, which is a session
that does not start. Generating into a temporary directory and validating
before the move turns that into a failed run with the old configuration
still in place.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
PLUGIN_LINE = re.compile(r"^\s*plugin\s*=\s*(\S+)", re.MULTILINE)

Runner = Callable[..., subprocess.CompletedProcess]


def validate(directory: Path, *, runner: Runner | None = None) -> list[str]:
    runner = runner or subprocess.run
    findings: list[str] = []

    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for match in PLACEHOLDER.finditer(text):
            findings.append(
                f"{path.name}: unresolved placeholder {match.group(1)}"
            )

        if path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                findings.append(f"{path.name}: invalid JSON ({exc.msg})")

        if path.suffix == ".sh" or text.startswith("#!/bin/bash"):
            result = runner(
                ["bash", "-n", str(path)], capture_output=True, text=True
            )
            if result.returncode != 0:
                findings.append(
                    f"{path.name}: shell syntax error "
                    f"({result.stderr.strip().splitlines()[0] if result.stderr else 'unknown'})"
                )

        for match in PLUGIN_LINE.finditer(text):
            plugin = Path(match.group(1))
            if not plugin.is_file():
                findings.append(
                    f"{path.name}: plugin object missing: {plugin.name}"
                )

    return findings
```

- [ ] **Schritt 4: Den Generator dreistufig machen**

In `generate_config.sh`: statt direkt in das Zielverzeichnis zu schreiben, in ein Temp-Verzeichnis erzeugen, `validate_output.py` darauf laufen lassen und nur bei leerem Ergebnis verschieben. Bei Befunden das Temp-Verzeichnis stehen lassen und den Grund ausgeben — die alte Konfiguration bleibt unangetastet.

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_generate.py -v`
Erwartet: 6 Tests PASS

- [ ] **Schritt 6: Gesamte Suite prüfen und committen**

```bash
.venv/bin/python -m pytest -q
git add src tests/src
git commit -m "feat(src): atomare Erzeugung mit Validierung vor dem Ersetzen"
```

---

### Task 9: Kommandozeilen-Einstiegspunkte

**Dateien:**
- Anlegen: `src/bin/zepos-generate`, `src/bin/zepos-settings`, `src/bin/zepos-doctor`
- Test: `tests/src/test_cli.py`

**Schnittstellen:**
- Nutzt: alles Vorherige
- Liefert: die drei Kommandos, die `zepos-config` später nach `/usr/bin/` legt

`zepos-doctor` ist die Stelle, an der die in Teilprojekt 4 gefundenen Fehlerklassen zusammenlaufen: nicht passende Plugin-ABI, ein VPN, der den gesamten privaten Adressraum routet und damit Container lahmlegt, fehlende Katalogeinträge.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/src/test_cli.py
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib.machinery
import importlib.util
from pathlib import Path


def _load(name):
    path = Path("src/bin") / name
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_all_three_commands_exist():
    for name in ("zepos-generate", "zepos-settings", "zepos-doctor"):
        assert (Path("src/bin") / name).is_file()


def test_they_are_executable():
    import os
    for name in ("zepos-generate", "zepos-settings", "zepos-doctor"):
        assert os.access(Path("src/bin") / name, os.X_OK), f"{name} is not executable"


def test_loading_a_command_runs_nothing():
    """Loaded by path in tests, so module scope must hold definitions only."""
    module = _load("zepos-doctor")
    assert hasattr(module, "main")


def test_doctor_reports_a_vpn_that_swallows_the_private_address_space():
    """Routing all three RFC1918 ranges leaves no subnet for container and
    virtualisation bridges. This cost a working Docker setup during
    development and produced no error message anywhere."""
    module = _load("zepos-doctor")
    findings = module.check_vpn_networks(
        ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
        bridges=["10.222.0.0/24"],
    )
    assert any("10.222.0.0/24" in f for f in findings)


def test_doctor_is_quiet_when_no_bridge_collides():
    module = _load("zepos-doctor")
    assert module.check_vpn_networks(["10.0.0.0/8"], bridges=["172.17.0.0/16"]) == []


def test_doctor_reports_a_plugin_whose_object_is_missing(tmp_path):
    module = _load("zepos-doctor")
    conf = tmp_path / "hyprland.conf"
    conf.write_text("plugin = /nonexistent/foo.so\n")
    assert any("foo.so" in f for f in module.check_plugins(conf))
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_cli.py -v`
Erwartet: FAIL, `src/bin/` existiert nicht

- [ ] **Schritt 3: `zepos-doctor` implementieren**

```python
#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Report configuration problems that otherwise surface as silence.

Each check here corresponds to a failure seen during development that
produced no error message at all - the kind a user cannot diagnose because
nothing tells them anything is wrong.
"""
from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path

PLUGIN_LINE = re.compile(r"^\s*plugin\s*=\s*(\S+)", re.MULTILINE)


def check_vpn_networks(routed: list[str], *, bridges: list[str]) -> list[str]:
    """A VPN routing all of RFC1918 leaves nothing for local bridges.

    Container and virtualisation bridges live in private space. When the
    tunnel claims all of it, their traffic disappears into the tunnel and
    the tools simply stop working, with no error anywhere.
    """
    findings = []
    for bridge in bridges:
        bridge_net = ipaddress.ip_network(bridge)
        for route in routed:
            if bridge_net.subnet_of(ipaddress.ip_network(route)):
                findings.append(
                    f"the VPN routes {route}, which swallows the local "
                    f"bridge {bridge} - containers on it will have no network"
                )
    return findings


def check_plugins(hyprland_conf: Path) -> list[str]:
    """Hyprland refuses to start a plugin whose object is absent."""
    if not hyprland_conf.is_file():
        return []
    findings = []
    for match in PLUGIN_LINE.finditer(hyprland_conf.read_text(encoding="utf-8")):
        plugin = Path(match.group(1))
        if not plugin.is_file():
            findings.append(f"plugin object missing: {plugin}")
    return findings


def main(argv: list[str] | None = None) -> int:
    from src.paths import output_root

    findings = check_plugins(output_root() / "hypr" / "hyprland.conf")
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
```

`zepos-generate` ruft den Generator mit der dreistufigen Erzeugung auf und unterstützt `--monitors`, um ein Monitorprofil aus `monitors.detect()` zu schreiben. `zepos-settings` liest und schreibt über `settings.load`/`save`.

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/src/test_cli.py -v`
Erwartet: 7 Tests PASS

- [ ] **Schritt 5: Ausführbar machen und committen**

```bash
chmod +x src/bin/zepos-generate src/bin/zepos-settings src/bin/zepos-doctor
git add src/bin tests/src/test_cli.py
git commit -m "feat(src): zepos-generate, zepos-settings und zepos-doctor"
```

---

## Abgleich mit der Spezifikation

| Spec | Umgesetzt in |
|---|---|
| §3 Frischer `git init`, kein Klon | bereits erfüllt; Task 1 kopiert nur getrackte Dateien |
| §5 Trennung `/usr/share` und `~/.config` | Task 2 |
| §5.1 Template-Overrides ab Tag 1 | Task 2 |
| §5.2 `schema_version` ab Tag 1 | Task 3 |
| §6.1 16 Templates und 5 Verzeichnisse gelöscht | Task 1 |
| §6.2 Zwei neue generische Templates | Task 7 |
| §6.3 VPN entkoppelt, Child-SAs erzeugt | Task 5 |
| §6.4 Umbenennung, 232 Vorkommen | Task 4 |
| §6.5 Monitor-Erkennung über EDID | Task 6 |
| §9.1 Atomare Erzeugung | Task 8 |
| §9.2 Vier Validierungen | Task 8 |
| §4.2 `zepos-generate`, `-settings`, `-doctor` | Task 9 |

## Offen, gehört zu Teilprojekt 3

- Die PKGBUILDs, die `src/` nach `/usr/share/zepos` und `src/bin/` nach `/usr/bin/` legen
- `/etc/skel/.config/zepos/user-settings.json` für neu angelegte Nutzer
- Nichts weiter. Die Netzwerk-Watchdog-Templates tragen keine Firmenwerte,
  nur einen fest verdrahteten Test-Host. Der wird in **Task 5** mit umgestellt,
  auf `watchdog.test_host` aus den Einstellungen — eine Zeile, im selben
  Commit wie die VPN-Umstellung.
