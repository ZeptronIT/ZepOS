# ZepOS-Installer — Implementierungsplan

> **Für agentische Bearbeitung:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Aufgabe für Aufgabe umzusetzen. Die Schritte nutzen Checkbox-Syntax (`- [ ]`) zur Nachverfolgung.

**Ziel:** Ein Installer für ZepOS, der Sprache, Netzwerk (inklusive WLAN), Festplatte, Benutzer und ZepOS-Optionen über eine grafische Oberfläche einsammelt und die Installation an `archinstall` übergibt.

**Architektur:** Drei Schichten. Die Oberfläche (GTK4 oder TUI) füllt ausschließlich ein serialisierbares Datenmodell. Eine Übersetzungsschicht erzeugt daraus `config.json` und `creds.json` im Format von `archinstall`. Ein Aufrufer startet `archinstall --config … --creds … --silent`. Die Oberfläche kennt `archinstall` nicht.

**Tech-Stack:** Python 3.14, `archinstall` 4.4, GTK4 4.22 + libadwaita 1.9 über PyGObject 3.56, `iwd` für WLAN, `pytest`.

## Globale Randbedingungen

- Zielversionen, exakt: `archinstall` 4.4, GTK4 4.22.4, libadwaita 1.9.2, python-gobject 3.56.3, `iwd` 3.12, NetworkManager 1.58.0
- **Python 3.14 hat das Modul `crypt` entfernt** (seit 3.13). Passwort-Hashes werden über `openssl passwd -6` erzeugt, niemals über `crypt` oder `passlib`
- Die Integration mit `archinstall` erfolgt **ausschließlich über die CLI** (`--config`, `--creds`, `--silent`, `--offline`, `--dry-run`). Interne Python-Module von `archinstall` werden nicht importiert — sie ändern sich zwischen Releases, die CLI ist die stabile Zusage
- Alle Tests laufen **ohne root** und ohne echte Datenträger. Wo Systemwerkzeuge nötig sind (`iwctl`, `openssl`, `archinstall`), wird der Subprozess gemockt
- Build- und Testcontainer brauchen `--network host` (siehe Spec §10.1), sonst haben sie kein Netz
- Lizenzkopf GPL-3.0 in jeder neuen Quelldatei
- Klartext-Passwörter werden **nie** nach `config.json` geschrieben, ausschließlich als Hash nach `creds.json`, Modus 600
- **Zweisprachig, Deutsch und Englisch gleichrangig gepflegt.** Umsetzung über `gettext` aus der Standardbibliothek: Quelltext-Zeichenketten sind englisch und dienen als msgid, die deutsche Übersetzung liegt in `po/de.po`. Jede Zeichenkette, die ein Nutzer sehen kann, wird mit `_()` umschlossen — auch Ausnahme-Meldungen, denn eine unbehandelte Ausnahme *ist* Nutzerausgabe. Rein interne Zusicherungen, die nur bei einem Programmierfehler auslösen, bleiben unübersetzt und ohne `_()`.
- Codekommentare, Bezeichner und Docstrings ausschließlich auf Englisch
- Testnamen und Test-Assertions prüfen **msgid** (englisch), niemals die Übersetzung — sonst brechen die Tests, sobald jemand eine Formulierung im Katalog ändert

---

## Dateistruktur

```
installer/
  core/
    __init__.py
    model.py          Datenmodell (dataclasses) + Serialisierung
    validate.py       Validierung, liefert Liste von Befunden
    passwords.py      Hash-Erzeugung via openssl
    translate.py      Modell -> archinstall config.json / creds.json
    wifi.py           WLAN-Backend (Scan, Verbinden) hinter Interface
    netprofile.py     NetworkManager-Profil ins Zielsystem schreiben
    source.py         Hybride Paketquelle: online oder offline
    runner.py         archinstall-Aufruf
  tui/
    __init__.py
    app.py            Textoberfläche
  gui/
    __init__.py
    app.py            GTK4-Anwendung
    pages.py          Die sieben Seiten
  bin/
    zepos-install     Einstiegspunkt, wählt GUI oder TUI
tests/installer/
  test_model.py  test_validate.py  test_passwords.py  test_translate.py
  test_wifi.py   test_netprofile.py  test_source.py   test_runner.py
  test_entry.py
```

Trennung nach Verantwortung: `core/` ist vollständig oberflächenfrei und für sich testbar. `tui/` und `gui/` enthalten ausschließlich Darstellung und Eingabe.

---

### Task 1: Datenmodell

**Dateien:**
- Anlegen: `installer/core/model.py`
- Anlegen: `installer/core/__init__.py` (leer)
- Test: `tests/installer/test_model.py`

**Schnittstellen:**
- Nutzt: nichts
- Liefert: `InstallConfig`, `UserAccount`, `WifiCredentials`, `DiskChoice`, `ZeposOptions`; Methoden `InstallConfig.to_dict() -> dict`, `InstallConfig.from_dict(d: dict) -> InstallConfig`; Konstante `SCHEMA_VERSION: int = 1`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_model.py
from installer.core.model import (
    InstallConfig, UserAccount, WifiCredentials, DiskChoice,
    ZeposOptions, SCHEMA_VERSION,
)


def _sample() -> InstallConfig:
    return InstallConfig(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda", wipe=True, filesystem="ext4",
                        size_bytes=64 * 1024**3),
        users=[UserAccount(username="lars", password="geheim", sudo=True)],
        root_password="rootgeheim",
        wifi=WifiCredentials(ssid="Fritz", passphrase="wlanpw"),
        zepos=ZeposOptions(enable_plugins=True, weather_location="Musterstadt"),
    )


def test_roundtrip_preserves_all_fields():
    cfg = _sample()
    assert InstallConfig.from_dict(cfg.to_dict()) == cfg


def test_to_dict_carries_schema_version():
    assert _sample().to_dict()["schema_version"] == SCHEMA_VERSION


def test_from_dict_rejects_unknown_schema_version():
    d = _sample().to_dict()
    d["schema_version"] = 99
    try:
        InstallConfig.from_dict(d)
    except ValueError as exc:
        assert "99" in str(exc)
    else:
        raise AssertionError("erwartet: ValueError bei unbekannter Schemaversion")


def test_wifi_is_optional():
    cfg = _sample()
    cfg.wifi = None
    assert InstallConfig.from_dict(cfg.to_dict()).wifi is None
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_model.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.model'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/model.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Surface-independent data model for a ZepOS installation.

The UI fills this model and nothing else. Translation to archinstall's
own format happens in translate.py, so the UI never learns archinstall's
schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class UserAccount:
    username: str
    password: str
    sudo: bool = True


@dataclass
class WifiCredentials:
    ssid: str
    passphrase: str


@dataclass
class DiskChoice:
    device: str
    wipe: bool = True
    filesystem: str = "ext4"
    size_bytes: int = 0


@dataclass
class ZeposOptions:
    enable_plugins: bool = True
    weather_location: str = ""


@dataclass
class InstallConfig:
    language: str
    keymap: str
    timezone: str
    locale: str
    hostname: str
    disk: DiskChoice
    users: list[UserAccount] = field(default_factory=list)
    root_password: str = ""
    wifi: WifiCredentials | None = None
    zepos: ZeposOptions = field(default_factory=ZeposOptions)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = SCHEMA_VERSION
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstallConfig:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version {version}, expected {SCHEMA_VERSION}"
            )
        payload = {k: v for k, v in data.items() if k != "schema_version"}
        wifi = payload.pop("wifi", None)
        return cls(
            **payload | {
                "disk": DiskChoice(**payload["disk"]),
                "users": [UserAccount(**u) for u in payload["users"]],
                "zepos": ZeposOptions(**payload["zepos"]),
                "wifi": WifiCredentials(**wifi) if wifi else None,
            }
        )
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_model.py -v`
Erwartet: 4 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add installer/core/__init__.py installer/core/model.py tests/installer/test_model.py
git commit -m "feat(installer): Datenmodell fuer die Installkonfiguration"
```

---

### Task 1b: Zweisprachigkeit

**Dateien:**
- Anlegen: `installer/core/i18n.py`
- Anlegen: `po/zepos-installer.pot`, `po/de.po`
- Anlegen: `po/build.sh`
- Test: `tests/installer/test_i18n.py`

**Schnittstellen:**
- Nutzt: nichts
- Liefert: `_(message: str) -> str`, `activate(language: str, *, localedir: Path | None = None, translation=None) -> None`, `current_language() -> str`, Konstanten `DOMAIN = "zepos-installer"`, `SUPPORTED_LANGUAGES = ("en", "de")`

Muss vor Task 2 stehen: `validate.py` erzeugt Nutzertexte und braucht `_()`. Englisch ist die Quellsprache und damit die msgid; Deutsch ist ein gleichrangig gepflegter Katalog.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_i18n.py
# SPDX-License-Identifier: GPL-3.0-or-later
import gettext
import re
import struct
from pathlib import Path

import pytest

from installer.core.i18n import (
    DOMAIN, SUPPORTED_LANGUAGES, _, activate, current_language,
)

PO_FILE = Path("po/de.po")


class FakeTranslation(gettext.NullTranslations):
    def __init__(self, mapping):
        super().__init__()
        self._mapping = mapping

    def gettext(self, message):
        return self._mapping.get(message, message)


@pytest.fixture(autouse=True)
def _reset_catalogue():
    """activate() mutates module state. If the German catalogue stayed active
    after these tests, every other module's tests would stop finding their
    English msgids."""
    yield
    activate("en")


def test_supported_languages_are_english_and_german():
    assert SUPPORTED_LANGUAGES == ("en", "de")


def test_domain_is_stable():
    """The domain becomes the .mo filename; changing it breaks every
    installed translation."""
    assert DOMAIN == "zepos-installer"


def test_untranslated_message_falls_back_to_msgid():
    activate("en")
    assert _("Installation failed.") == "Installation failed."


def test_activate_switches_the_catalogue():
    activate("de", translation=FakeTranslation({"Installation failed.": "Die Installation ist fehlgeschlagen."}))
    assert _("Installation failed.") == "Die Installation ist fehlgeschlagen."
    assert current_language() == "de"


def test_unknown_language_does_not_raise_and_yields_msgid():
    activate("kl")
    assert _("Installation failed.") == "Installation failed."


def test_missing_catalogue_does_not_raise(tmp_path):
    activate("de", localedir=tmp_path)
    assert _("Installation failed.") == "Installation failed."


def test_corrupt_catalogue_does_not_raise(tmp_path):
    """An interrupted installation can leave a half-written .mo behind.
    gettext then raises struct.error, which is NOT an OSError and must be
    caught anyway - otherwise the installer no longer starts."""
    target = tmp_path / "de" / "LC_MESSAGES"
    target.mkdir(parents=True)
    (target / "zepos-installer.mo").write_bytes(b"\xde\x12\x04")
    activate("de", localedir=tmp_path)
    assert _("Installation failed.") == "Installation failed."


def test_german_catalogue_exists_and_is_not_empty():
    assert PO_FILE.exists(), "po/de.po fehlt - Deutsch waere dann nicht gepflegt"
    assert 'msgstr ""' in PO_FILE.read_text(encoding="utf-8")


def test_every_msgid_in_the_german_catalogue_has_a_translation():
    """An empty msgstr means the user sees English despite choosing German."""
    text = PO_FILE.read_text(encoding="utf-8")
    entries = re.findall(r'^msgid "(.+)"\nmsgstr "(.*)"', text, re.MULTILINE)
    assert entries, "keine Eintraege im Katalog gefunden"
    untranslated = [msgid for msgid, msgstr in entries if not msgstr]
    assert untranslated == [], f"ohne Uebersetzung: {untranslated}"


def test_schema_version_message_is_translated():
    """The message from Task 1 - the reason this task exists."""
    text = PO_FILE.read_text(encoding="utf-8")
    assert "unsupported schema_version" in text
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/installer/test_i18n.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.i18n'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/i18n.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bilingual message catalogue.

English source strings are the msgids; German is a first-class catalogue
in po/de.po. Anything a user can see goes through _(), including
exception messages - an unhandled exception is user output.

Purely internal assertions that only fire on a programming error stay
untranslated, so translators are not asked to render text no user reads.
"""
from __future__ import annotations

import gettext
import struct
from pathlib import Path

DOMAIN = "zepos-installer"
SUPPORTED_LANGUAGES = ("en", "de")
SYSTEM_LOCALEDIR = Path("/usr/share/locale")
# A development checkout has no installed .mo; po/build.sh writes one here.
DEV_LOCALEDIR = Path(__file__).resolve().parents[2] / "po" / "build"

_translation: gettext.NullTranslations = gettext.NullTranslations()
_language = "en"


def activate(
    language: str,
    *,
    localedir: Path | None = None,
    translation: gettext.NullTranslations | None = None,
) -> None:
    """Select the catalogue. Never raises: a missing catalogue degrades to
    English rather than leaving the installer unable to print anything."""
    global _translation, _language
    _language = language

    if translation is not None:
        _translation = translation
        return

    candidates = [localedir] if localedir else [SYSTEM_LOCALEDIR, DEV_LOCALEDIR]
    for directory in candidates:
        try:
            _translation = gettext.translation(
                DOMAIN, localedir=str(directory), languages=[language]
            )
            return
        except (OSError, AttributeError, struct.error, ValueError):
            # struct.error: a truncated .mo, e.g. from an interrupted write.
            # It is not an OSError, so it must be named explicitly - an
            # installer that cannot start because a translation file is half
            # written would be worse than one printing English.
            continue

    _translation = gettext.NullTranslations()


def current_language() -> str:
    return _language


def _(message: str) -> str:
    """Look the catalogue up at call time, so activate() takes effect for
    strings imported before it ran."""
    return _translation.gettext(message)
```

- [ ] **Schritt 4: Katalog anlegen**

```
# po/zepos-installer.pot
msgid ""
msgstr ""
"Project-Id-Version: zepos-installer\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Language: \n"

#: installer/core/model.py
msgid "unsupported schema_version {version}, expected {expected}"
msgstr ""
```

```
# po/de.po
msgid ""
msgstr ""
"Project-Id-Version: zepos-installer\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Language: de\n"

#: installer/core/model.py
msgid "unsupported schema_version {version}, expected {expected}"
msgstr "Nicht unterstuetzte Schemaversion {version}, erwartet wird {expected}"
```

```bash
# po/build.sh
#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Compiles the .po catalogues into the .mo files gettext reads at runtime.
# A development checkout has no installed catalogue, so this writes into
# po/build/ where i18n.py's DEV_LOCALEDIR looks. The PKGBUILD runs the
# same command against /usr/share/locale.
set -euo pipefail

DOMAIN=zepos-installer
OUT="${1:-$(dirname "$0")/build}"

for po in "$(dirname "$0")"/*.po; do
    lang=$(basename "$po" .po)
    target="$OUT/$lang/LC_MESSAGES"
    mkdir -p "$target"
    msgfmt -o "$target/$DOMAIN.mo" "$po"
    echo "built: $target/$DOMAIN.mo"
done
```

- [ ] **Schritt 5: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/installer/test_i18n.py -v`
Erwartet: 9 Tests PASS

- [ ] **Schritt 6: Task 1 auf `_()` umstellen**

In `installer/core/model.py` die Meldung übersetzbar machen. Der englische Text bleibt als msgid unverändert:

```python
from .i18n import _

        if version != SCHEMA_VERSION:
            raise ValueError(
                _("unsupported schema_version {version}, expected {expected}").format(
                    version=version, expected=SCHEMA_VERSION
                )
            )
```

Der Test aus Task 1 (`test_from_dict_rejects_unknown_schema_version`) prüft weiterhin nur, dass `"99"` in der Meldung vorkommt — er bleibt damit unverändert gültig und ist unabhängig von der Katalogsprache.

- [ ] **Schritt 7: Gesamte Suite prüfen**

Ausführen: `.venv/bin/python -m pytest -q`
Erwartet: alle bisherigen Tests weiterhin PASS, keine Warnungen

- [ ] **Schritt 8: Committen**

```bash
chmod +x po/build.sh
git add installer/core/i18n.py installer/core/model.py po tests/installer/test_i18n.py
git commit -m "feat(installer): Zweisprachigkeit ueber gettext, Deutsch und Englisch"
```

---

### Task 2: Validierung

**Dateien:**
- Anlegen: `installer/core/validate.py`
- Test: `tests/installer/test_validate.py`

**Schnittstellen:**
- Nutzt: `InstallConfig` aus Task 1, `_` aus Task 1b
- Liefert: `validate(cfg: InstallConfig) -> list[str]` — leere Liste bedeutet gültig, sonst übersetzte Befunde; `MIN_PASSWORD_LENGTH: int = 8`

Alle Befunde laufen durch `_()`. Die msgids sind englisch, die Übersetzungen kommen nach `po/de.po` **und** `po/zepos-installer.pot`. Die Tests prüfen msgids, nicht Übersetzungen.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_validate.py
import pytest

from installer.core.model import InstallConfig, DiskChoice, UserAccount, WifiCredentials
from installer.core.validate import validate


def _cfg(**over) -> InstallConfig:
    base = dict(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda"),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="langgenug",
    )
    base.update(over)
    return InstallConfig(**base)


def test_valid_config_has_no_findings():
    assert validate(_cfg()) == []


def test_missing_user_is_reported():
    assert any("user" in f for f in validate(_cfg(users=[])))


def test_short_password_is_reported():
    cfg = _cfg(users=[UserAccount(username="lars", password="kurz")])
    assert any("password" in f for f in validate(cfg))


def test_short_password_finding_names_the_user():
    cfg = _cfg(users=[UserAccount(username="lars", password="kurz")])
    assert any("lars" in f for f in validate(cfg))


def test_invalid_hostname_is_reported():
    assert any("hostname" in f for f in validate(_cfg(hostname="zep os!")))


def test_hostname_with_leading_hyphen_is_reported():
    assert any("hostname" in f for f in validate(_cfg(hostname="-zepos")))


def test_empty_disk_device_is_reported():
    assert any("disk" in f for f in validate(_cfg(disk=DiskChoice(device=""))))


def test_wifi_without_passphrase_is_reported():
    cfg = _cfg(wifi=WifiCredentials(ssid="Fritz", passphrase=""))
    assert any("wireless" in f for f in validate(cfg))


def test_no_wifi_configured_is_not_a_finding():
    """Installing over ethernet is perfectly normal."""
    assert validate(_cfg(wifi=None)) == []


def test_user_without_a_name_is_reported():
    """UserAccount has no __post_init__ guard, so an empty username is
    constructible and this path is reachable."""
    cfg = _cfg(users=[UserAccount(username="", password="langgenug")])
    assert any("no name" in f for f in validate(cfg))
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_validate.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.validate'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/validate.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validation of an InstallConfig.

Returns findings the UI can present verbatim. An empty list means the
configuration may be installed. Every finding goes through _(), because
these strings are shown to the person installing the system.
"""
from __future__ import annotations

import re

from .i18n import _
from .model import InstallConfig

_HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
MIN_PASSWORD_LENGTH = 8


def validate(cfg: InstallConfig) -> list[str]:
    findings: list[str] = []

    if not cfg.users:
        findings.append(_("At least one user account must be created."))

    for user in cfg.users:
        if not user.username:
            findings.append(_("A user account has no name."))
        if len(user.password) < MIN_PASSWORD_LENGTH:
            findings.append(
                _("The password for '{user}' is shorter than {minimum} characters.")
                .format(user=user.username, minimum=MIN_PASSWORD_LENGTH)
            )

    if not _HOSTNAME.match(cfg.hostname):
        findings.append(
            _(
                "The hostname may contain only letters, digits and hyphens, "
                "and may not start or end with a hyphen."
            )
        )

    if not cfg.disk.device:
        findings.append(_("No disk was selected."))

    if cfg.wifi is not None and not cfg.wifi.passphrase:
        findings.append(_("No password was given for the wireless network."))

    return findings
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `.venv/bin/python -m pytest tests/installer/test_validate.py -v`
Erwartet: 10 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add installer/core/validate.py tests/installer/test_validate.py
git commit -m "feat(installer): Validierung der Installkonfiguration"
```

---

### Task 3: Passwort-Hashing

**Dateien:**
- Anlegen: `installer/core/passwords.py`
- Test: `tests/installer/test_passwords.py`

**Schnittstellen:**
- Nutzt: nichts
- Liefert: `hash_password(plain: str, *, runner=subprocess.run) -> str`

Hintergrund: `archinstall` erwartet in `creds.json` das Feld `enc_password` mit einem fertigen Hash. Das Python-Modul `crypt` wurde in 3.13 entfernt, deshalb `openssl passwd -6` (SHA-512).

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_passwords.py
import subprocess

import pytest

from installer.core.passwords import hash_password


def test_uses_openssl_sha512_and_returns_hash():
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="$6$abc$def\n", stderr="")

    assert hash_password("geheim", runner=fake_run) == "$6$abc$def"
    assert calls[0][:3] == ["openssl", "passwd", "-6"]


def test_password_is_passed_via_stdin_not_argv():
    """A password in argv would be readable by every process on the system."""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["input"] = kw.get("input")
        return subprocess.CompletedProcess(cmd, 0, stdout="$6$x$y\n", stderr="")

    hash_password("streng-geheim", runner=fake_run)
    assert "streng-geheim" not in " ".join(seen["cmd"])
    assert seen["input"] == "streng-geheim"


def test_openssl_failure_raises():
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    with pytest.raises(RuntimeError, match="boom"):
        hash_password("geheim", runner=fake_run)


def test_empty_password_raises():
    with pytest.raises(ValueError):
        hash_password("", runner=lambda *a, **k: None)
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_passwords.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.passwords'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/passwords.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""SHA-512 password hashing for archinstall's creds.json.

Python removed the `crypt` module in 3.13, so this shells out to
openssl. The plaintext goes through stdin: an argument vector is world
readable via /proc, stdin is not.
"""
from __future__ import annotations

import subprocess
from typing import Callable

from .i18n import _

Runner = Callable[..., subprocess.CompletedProcess]


def hash_password(plain: str, *, runner: Runner | None = None) -> str:
    if not plain:
        raise ValueError("refusing to hash an empty password")

    # Resolved here, not bound as a default: a default argument captures
    # subprocess.run at import time, which the test suite's isolation guard
    # cannot intercept.
    runner = runner or subprocess.run

    try:
        result = runner(
        ["openssl", "passwd", "-6", "-stdin"],
            input=plain,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        # openssl missing or not executable. Reachable on a damaged live
        # image, so the user can see it - hence _().
        raise RuntimeError(
            _("Could not run openssl to hash the password: {reason}")
            .format(reason=exc)
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            _("Hashing the password failed: {reason}")
            .format(reason=result.stderr.strip())
        )
    return result.stdout.strip()
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_passwords.py -v`
Erwartet: 4 Tests PASS

- [ ] **Schritt 5: Gegen echtes openssl gegenprüfen**

Ausführen:
```bash
python -c "
from installer.core.passwords import hash_password
h = hash_password('testpasswort')
assert h.startswith('\$6\$'), h
print('OK:', h[:12], '...')
"
```
Erwartet: Ausgabe beginnt mit `OK: $6$`

- [ ] **Schritt 6: Committen**

```bash
git add installer/core/passwords.py tests/installer/test_passwords.py
git commit -m "feat(installer): Passwort-Hashing via openssl passwd -6"
```

---

### Task 4: Hybride Paketquelle

**Dateien:**
- Anlegen: `installer/core/source.py`
- Test: `tests/installer/test_source.py`

**Schnittstellen:**
- Nutzt: nichts
- Liefert: `PackageSource` (Enum `ONLINE` / `OFFLINE`), `probe(check=…) -> PackageSource`, `mirror_config(source: PackageSource) -> dict`

Das ZepOS-Repo wird über `mirror_config.custom_repositories` eingehängt — genau das Feld, das `archinstall` im Beispielschema dokumentiert. Offline zeigt es auf `file:///opt/zepos-repo`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_source.py
from installer.core.source import PackageSource, probe, mirror_config


def test_probe_returns_online_when_reachable():
    assert probe(check=lambda: True) is PackageSource.ONLINE


def test_probe_falls_back_to_offline():
    assert probe(check=lambda: False) is PackageSource.OFFLINE


def test_probe_treats_check_error_as_offline():
    def boom():
        raise OSError("no network")

    assert probe(check=boom) is PackageSource.OFFLINE


def test_probe_treats_any_exception_as_offline():
    """ssl.CertificateError is a ValueError, not an OSError. A probe that
    cannot decide must fall back, not abort the installation."""
    def boom():
        raise ValueError("certificate verify failed")

    assert probe(check=boom) is PackageSource.OFFLINE


def test_probe_still_lets_keyboard_interrupt_through():
    """The user pressing Ctrl-C must not be swallowed as "no network"."""
    def interrupted():
        raise KeyboardInterrupt

    try:
        probe(check=interrupted)
    except KeyboardInterrupt:
        return
    raise AssertionError("KeyboardInterrupt was swallowed")


def test_offline_repo_points_at_the_iso():
    cfg = mirror_config(PackageSource.OFFLINE)
    repo = cfg["custom_repositories"][0]
    assert repo["name"] == "zepos"
    assert repo["url"] == "file:///opt/zepos-repo"
    assert cfg["mirror_regions"] == {}


def test_online_keeps_arch_mirrors_and_adds_zepos():
    cfg = mirror_config(PackageSource.ONLINE)
    assert cfg["custom_repositories"][0]["name"] == "zepos"
    assert cfg["mirror_regions"] != {}


def test_zepos_repo_requires_signatures():
    """Unsigned packages must not slip through - see spec 8.6."""
    for source in PackageSource:
        repo = mirror_config(source)["custom_repositories"][0]
        assert repo["sign_check"] == "Required"
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_source.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.source'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/source.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decide where packages come from: Arch mirrors or the ISO's own repo.

Online is preferred because it yields current packages. The offline repo
shipped on the ISO is the fallback that keeps installation possible when
wireless firmware is missing.
"""
from __future__ import annotations

import enum
import socket
from typing import Any, Callable

OFFLINE_REPO_URL = "file:///opt/zepos-repo"
ONLINE_REPO_URL = "https://repo.zepos.org/$repo/os/$arch"
DEFAULT_MIRROR_REGION = "Germany"


class PackageSource(enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"


def _default_check() -> bool:
    with socket.create_connection(("archlinux.org", 443), timeout=5):
        return True


def probe(*, check: Callable[[], bool] | None = None) -> PackageSource:
    # Resolved here, not bound as a default - see passwords.py.
    check = check or _default_check
    try:
        return PackageSource.ONLINE if check() else PackageSource.OFFLINE
    except Exception:
        # Deliberately broad. This function's whole job is to decide, never
        # to fail: an injected check may raise ssl.CertificateError (a
        # ValueError), subprocess.CalledProcessError or an HTTP exception,
        # none of which are OSError. Any failure means "no network", which
        # is a fallback, not a reason to abort the installation.
        # BaseException (KeyboardInterrupt, SystemExit) still propagates.
        return PackageSource.OFFLINE


def mirror_config(source: PackageSource) -> dict[str, Any]:
    zepos_repo = {
        "name": "zepos",
        "url": OFFLINE_REPO_URL if source is PackageSource.OFFLINE else ONLINE_REPO_URL,
        "sign_check": "Required",
        "sign_option": "TrustedOnly",
    }
    regions: dict[str, list[str]] = {}
    if source is PackageSource.ONLINE:
        regions = {DEFAULT_MIRROR_REGION: []}

    return {
        "custom_servers": [],
        "mirror_regions": regions,
        "optional_repositories": [],
        "custom_repositories": [zepos_repo],
    }
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_source.py -v`
Erwartet: 6 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add installer/core/source.py tests/installer/test_source.py
git commit -m "feat(installer): hybride Paketquelle mit Offline-Rueckfall"
```

---

### Task 5: Übersetzung nach archinstall

**Dateien:**
- Anlegen: `installer/core/translate.py`
- Test: `tests/installer/test_translate.py`

**Schnittstellen:**
- Nutzt: `InstallConfig` (Task 1), `hash_password` (Task 3), `PackageSource` und `mirror_config` (Task 4)
- Liefert: `to_archinstall_config(cfg, source) -> dict`, `to_archinstall_creds(cfg, *, hasher=hash_password) -> dict`

Dies ist das Herzstück. Die Feldnamen stammen aus `archinstall/examples/config-sample.json` der Version 4.4.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_translate.py
from installer.core.model import InstallConfig, DiskChoice, UserAccount, ZeposOptions
from installer.core.source import PackageSource
from installer.core.translate import to_archinstall_config, to_archinstall_creds


def _cfg() -> InstallConfig:
    return InstallConfig(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda", wipe=True, filesystem="ext4",
                        size_bytes=64 * 1024**3),
        users=[UserAccount(username="lars", password="langgenug", sudo=True)],
        root_password="rootlanggenug",
        zepos=ZeposOptions(enable_plugins=True),
    )


def test_locale_and_hostname_are_mapped():
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert out["hostname"] == "zepos"
    assert out["locale_config"] == {
        "kb_layout": "de-latin1", "sys_enc": "UTF-8", "sys_lang": "de_DE",
    }
    assert out["timezone"] == "Europe/Berlin"


def test_zepos_desktop_is_requested():
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert "zepos-desktop" in out["packages"]


def test_disk_device_and_wipe_are_mapped():
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    mod = out["disk_config"]["device_modifications"][0]
    assert mod["device"] == "/dev/vda"
    assert mod["wipe"] is True


def test_partitions_are_never_empty_when_wiping():
    """archinstall does not compute a layout from a config file. An empty
    partition list with wipe=True erases the disk and creates nothing."""
    mod = to_archinstall_config(_cfg(), PackageSource.ONLINE)["disk_config"]["device_modifications"][0]
    assert mod["partitions"], "wipe=True with no partitions destroys the disk"


def test_layout_is_esp_plus_root():
    mod = to_archinstall_config(_cfg(), PackageSource.ONLINE)["disk_config"]["device_modifications"][0]
    esp, root = mod["partitions"]
    assert esp["mountpoint"] == "/boot" and esp["fs_type"] == "fat32"
    assert "boot" in esp["flags"] and "esp" in esp["flags"]
    assert root["mountpoint"] == "/" and root["fs_type"] == "ext4"
    assert root["size"]["unit"] == "MiB"


def test_root_partition_starts_after_the_esp():
    mod = to_archinstall_config(_cfg(), PackageSource.ONLINE)["disk_config"]["device_modifications"][0]
    esp, root = mod["partitions"]
    assert root["start"]["value"] > esp["start"]["value"] + esp["size"]["value"] - 1


def test_chosen_filesystem_reaches_the_root_partition():
    """The user's choice must not be silently replaced by a default."""
    cfg = _cfg()
    cfg.disk.filesystem = "btrfs"
    mod = to_archinstall_config(cfg, PackageSource.ONLINE)["disk_config"]["device_modifications"][0]
    assert mod["partitions"][1]["fs_type"] == "btrfs"


def test_partition_ids_are_unique():
    mod = to_archinstall_config(_cfg(), PackageSource.ONLINE)["disk_config"]["device_modifications"][0]
    ids = [p["obj_id"] for p in mod["partitions"]]
    assert len(set(ids)) == len(ids)


def test_empty_device_is_refused():
    """Defense in depth: wipe defaults to True, so a config with no device
    must never be produced, even if validate() was skipped."""
    cfg = _cfg()
    cfg.disk.device = ""
    try:
        to_archinstall_config(cfg, PackageSource.ONLINE)
    except ValueError:
        return
    raise AssertionError("an empty device must be refused")


def test_offline_source_sets_offline_flag_and_repo():
    out = to_archinstall_config(_cfg(), PackageSource.OFFLINE)
    assert out["offline"] is True
    assert out["mirror_config"]["custom_repositories"][0]["url"].startswith("file://")


def test_online_source_clears_offline_flag():
    assert to_archinstall_config(_cfg(), PackageSource.ONLINE)["offline"] is False


def test_network_config_uses_networkmanager():
    """NetworkManager must be installed, otherwise Task 7 cannot place a
    connection profile."""
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert out["network_config"]["type"] == "nm"


def test_config_contains_no_plaintext_password():
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert "langgenug" not in repr(out)
    assert "rootlanggenug" not in repr(out)


def test_creds_carry_hashes_only():
    creds = to_archinstall_creds(_cfg(), hasher=lambda p: f"HASH({p})")
    assert creds["users"][0]["enc_password"] == "HASH(langgenug)"
    assert creds["users"][0]["username"] == "lars"
    assert creds["users"][0]["sudo"] is True
    assert creds["root_enc_password"] == "HASH(rootlanggenug)"
    assert "password" not in creds["users"][0]


def test_empty_root_password_disables_root_login():
    cfg = _cfg()
    cfg.root_password = ""
    creds = to_archinstall_creds(cfg, hasher=lambda p: f"HASH({p})")
    assert creds["root_enc_password"] is None


def test_version_field_is_not_copied_from_the_stale_sample():
    """The bundled sample still says 2.8.6; the package is 4.4."""
    assert "version" not in to_archinstall_config(_cfg(), PackageSource.ONLINE)
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_translate.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.translate'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/translate.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Translate a ZepOS InstallConfig into archinstall's JSON format.

Field names follow archinstall/examples/config-sample.json of version
4.4. The sample's own "version" key is stale (it still says 2.8.6) and
is deliberately not reproduced.

Passwords never enter the config; they belong in creds.json as hashes.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from .model import InstallConfig
from .passwords import hash_password
from .source import PackageSource, mirror_config

ZEPOS_META_PACKAGE = "zepos-desktop"


ESP_SIZE_MIB = 512
ALIGNMENT_MIB = 1        # GPT primary header
GPT_TAIL_MIB = 1         # GPT backup header at the end of the disk
MIN_DISK_MIB = ESP_SIZE_MIB + ALIGNMENT_MIB + GPT_TAIL_MIB + 2048  # ~2.5 GiB
SECTOR_SIZE = {"value": 512, "unit": "B"}


def _size(value: int, unit: str = "MiB") -> dict[str, Any]:
    """archinstall's Size.parse_args requires a sector_size dict.

    Its bundled config-sample.json passes null here and is therefore not
    loadable at all - verified against 4.4, where it raises TypeError.
    """
    return {"value": value, "unit": unit, "sector_size": SECTOR_SIZE}


def _partitions(filesystem: str, disk_size_bytes: int) -> list[dict[str, Any]]:
    """Build the partition table explicitly.

    archinstall does NOT compute a layout when loading a config file. Its
    parse_arg reads partitions only from this list, and
    suggest_single_disk_layout is reachable exclusively from the
    interactive menus. An empty list combined with wipe=True would erase
    the disk and create nothing - verified against archinstall 4.4.

    config_type is therefore "manual_partitioning": the layout is ours,
    not archinstall's.

    The root partition's size is computed rather than expressed as a
    percentage: archinstall's Unit enum has no Percent member, so the
    "Percent" unit in its own sample raises KeyError. Verified against 4.4.
    """
    disk_mib = disk_size_bytes // (1024 * 1024)
    root_start = ESP_SIZE_MIB + ALIGNMENT_MIB
    root_mib = disk_mib - root_start - GPT_TAIL_MIB

    return [
        {
            "obj_id": str(uuid.uuid4()),
            "status": "create",
            "type": "primary",
            "fs_type": "fat32",
            "start": _size(ALIGNMENT_MIB),
            "size": _size(ESP_SIZE_MIB),
            "mountpoint": "/boot",
            "mount_options": [],
            "dev_path": None,
            "flags": ["boot", "esp"],
            "btrfs": [],
        },
        {
            "obj_id": str(uuid.uuid4()),
            "status": "create",
            "type": "primary",
            "fs_type": filesystem,
            "start": _size(root_start),
            "size": _size(root_mib),
            "mountpoint": "/",
            "mount_options": [],
            "dev_path": None,
            "flags": [],
            "btrfs": [],
        },
    ]


def to_archinstall_config(cfg: InstallConfig, source: PackageSource) -> dict[str, Any]:
    if not cfg.disk.device:
        # Defense in depth. validate() rejects this too, but wipe defaults
        # to True and nothing forces callers to validate first.
        raise ValueError("refusing to build a config without a target device")

    if cfg.disk.size_bytes // (1024 * 1024) < MIN_DISK_MIB:
        raise ValueError(
            f"target disk is too small: need at least {MIN_DISK_MIB} MiB"
        )

    return {
        "archinstall-language": "English",
        "hostname": cfg.hostname,
        "kernels": ["linux"],
        "timezone": cfg.timezone,
        "ntp": True,
        "offline": source is PackageSource.OFFLINE,
        "packages": [ZEPOS_META_PACKAGE],
        "locale_config": {
            "kb_layout": cfg.keymap,
            "sys_enc": "UTF-8",
            "sys_lang": cfg.locale,
        },
        "mirror_config": mirror_config(source),
        "network_config": {"type": "nm"},
        "bootloader_config": {
            "bootloader": "Systemd-boot",
            "uki": False,
            "removable": False,
        },
        "audio_config": {"audio": "pipewire"},
        "swap": {"enabled": True, "algorithm": "zstd"},
        "disk_config": {
            "config_type": "manual_partitioning",
            "device_modifications": [
                {
                    "device": cfg.disk.device,
                    "wipe": cfg.disk.wipe,
                    "partitions": _partitions(cfg.disk.filesystem, cfg.disk.size_bytes),
                }
            ],
        },
        "pacman_config": {"color": False, "parallel_downloads": 5},
        "script": "guided",
        "silent": True,
        "debug": False,
        "no_pkg_lookups": False,
    }


def to_archinstall_creds(
    cfg: InstallConfig,
    *,
    hasher: Callable[[str], str] = hash_password,
) -> dict[str, Any]:
    return {
        "users": [
            {
                "username": user.username,
                "enc_password": hasher(user.password),
                "sudo": user.sudo,
            }
            for user in cfg.users
        ],
        "root_enc_password": hasher(cfg.root_password) if cfg.root_password else None,
    }
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_translate.py -v`
Erwartet: 10 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add installer/core/translate.py tests/installer/test_translate.py
git commit -m "feat(installer): Uebersetzung nach archinstall config/creds"
```

---

### Task 6: WLAN-Backend

**Dateien:**
- Anlegen: `installer/core/wifi.py`
- Test: `tests/installer/test_wifi.py`

**Schnittstellen:**
- Nutzt: nichts
- Liefert: `Network` (dataclass: `ssid: str`, `signal: int`, `secured: bool`), Protokoll `WifiBackend` mit `devices()`, `scan(device)`, `networks(device)`, `connect(device, ssid, passphrase)`; Implementierung `IwctlBackend(runner=subprocess.run)`

`iwctl` gibt ANSI-Sequenzen und eine Tabellenüberschrift aus; beides muss entfernt werden. Das Backend liegt hinter einem Protokoll, damit es später gegen die D-Bus-Schnittstelle von `iwd` getauscht werden kann, ohne die Aufrufer anzufassen.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_wifi.py
import subprocess

import pytest

from installer.core.wifi import IwctlBackend, Network

GET_NETWORKS_OUTPUT = (
    "\x1b[0m                               Available networks\n"
    "--------------------------------------------------------------------\n"
    "      Network name                    Security            Signal\n"
    "--------------------------------------------------------------------\n"
    "  >   FRITZ!Box 7590                  psk                 ****\n"
    "      Nachbar-WLAN                    psk                 **\n"
    "      Gastnetz                        open                ***\n"
)

DEVICE_LIST_OUTPUT = (
    "                                 Devices\n"
    "--------------------------------------------------------------------\n"
    "      Name        Address            Powered    Adapter    Mode\n"
    "--------------------------------------------------------------------\n"
    "      wlan0       aa:bb:cc:dd:ee:ff  on         phy0       station\n"
)


def _runner(stdout: str, returncode: int = 0):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")
    return run


def test_devices_are_parsed():
    backend = IwctlBackend(runner=_runner(DEVICE_LIST_OUTPUT))
    assert backend.devices() == ["wlan0"]


def test_networks_are_parsed_without_ansi_or_headers():
    backend = IwctlBackend(runner=_runner(GET_NETWORKS_OUTPUT))
    nets = backend.networks("wlan0")
    assert Network(ssid="FRITZ!Box 7590", signal=4, secured=True) in nets
    assert Network(ssid="Gastnetz", signal=3, secured=False) in nets
    assert all("Network name" not in n.ssid for n in nets)
    assert all("\x1b" not in n.ssid for n in nets)


def test_networks_are_sorted_by_signal_strength():
    backend = IwctlBackend(runner=_runner(GET_NETWORKS_OUTPUT))
    signals = [n.signal for n in backend.networks("wlan0")]
    assert signals == sorted(signals, reverse=True)


def test_connect_passes_passphrase_out_of_argv():
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        seen["input"] = kw.get("input")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    IwctlBackend(runner=run).connect("wlan0", "FRITZ!Box 7590", "wlanpw")
    assert "wlanpw" not in " ".join(seen["cmd"])


def test_connect_raises_on_failure():
    backend = IwctlBackend(runner=_runner("Operation failed", returncode=1))
    with pytest.raises(RuntimeError):
        backend.connect("wlan0", "FRITZ!Box 7590", "falsch")
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_wifi.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.wifi'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/wifi.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Wireless scanning and association for the live environment.

Sits behind a protocol so the iwctl implementation can later be replaced
by iwd's D-Bus interface without touching any caller. iwctl emits ANSI
colour codes and table headers, both of which are stripped here.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Protocol

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SEPARATOR = re.compile(r"^-+$")

# The SSID group is greedy on purpose: the security keyword is the
# second-to-last column, so the LAST occurrence is the real one. That keeps
# an SSID such as "psk cafe wifi" from being cut at its own first word.
# A single space is enough of a separator - requiring two silently dropped
# long SSIDs, which iwctl renders with a narrow gap.
_NETWORK_LINE = re.compile(
    r"^(?P<ssid>.+)\s+(?P<security>psk|open|8021x|wep)\s*(?P<signal>\S*)\s*$"
)

Runner = Callable[..., subprocess.CompletedProcess]


@dataclass(frozen=True)
class Network:
    ssid: str
    signal: int
    secured: bool


class WifiBackend(Protocol):
    def devices(self) -> list[str]: ...
    def scan(self, device: str) -> None: ...
    def networks(self, device: str) -> list[Network]: ...
    def connect(self, device: str, ssid: str, passphrase: str) -> None: ...


class IwctlBackend:
    def __init__(self, *, runner: Runner | None = None) -> None:
        # Resolved at call time, not bound as a default - see passwords.py.
        self._run = runner or subprocess.run

    def _iwctl(self, *args: str, stdin: str | None = None) -> str:
        result = self._run(
            ["iwctl", *args],
            input=stdin,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"iwctl {' '.join(args)} failed: "
                f"{(result.stderr or result.stdout).strip()}"
            )
        return _ANSI.sub("", result.stdout)

    @staticmethod
    def _body(output: str) -> list[str]:
        """Drop ANSI, banners, separators and the column header row."""
        lines = [_ANSI.sub("", line).rstrip() for line in output.splitlines()]
        separators = [i for i, line in enumerate(lines) if _SEPARATOR.match(line.strip())]
        if not separators:
            # No table at all - iwctl said something else entirely ("no
            # wireless adapter", an error banner). Treating those lines as
            # data would invent device names like "No" and feed them back
            # into later iwctl calls.
            return []
        return [line for line in lines[separators[-1] + 1:] if line.strip()]

    def devices(self) -> list[str]:
        out = self._iwctl("device", "list")
        return [line.split()[0] for line in self._body(out)]

    def scan(self, device: str) -> None:
        self._iwctl("station", device, "scan")

    def networks(self, device: str) -> list[Network]:
        out = self._iwctl("station", device, "get-networks")
        found: list[Network] = []
        for line in self._body(out):
            stripped = line.lstrip()
            if stripped.startswith(">"):
                stripped = stripped[1:].lstrip()
            match = _NETWORK_LINE.match(stripped)
            if not match:
                # Not a network row (banner, stray text). Nothing to show.
                continue
            ssid = match.group("ssid").strip()
            signal = match.group("signal") or ""
            found.append(
                Network(
                    ssid=ssid,
                    # Count asterisks rather than requiring them. If iwctl
                    # ever renders signal with a different glyph, the network
                    # must still appear in the list - a user who cannot see
                    # their network is worse off than one seeing signal 0.
                    signal=signal.count("*"),
                    secured=match.group("security") != "open",
                )
            )
        return sorted(found, key=lambda n: n.signal, reverse=True)

    def connect(self, device: str, ssid: str, passphrase: str) -> None:
        self._iwctl("station", device, "connect", ssid, stdin=passphrase + "\n")
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_wifi.py -v`
Erwartet: 5 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add installer/core/wifi.py tests/installer/test_wifi.py
git commit -m "feat(installer): WLAN-Backend hinter austauschbarem Protokoll"
```

---

### Task 7: WLAN-Profil ins Zielsystem

**Dateien:**
- Anlegen: `installer/core/netprofile.py`
- Test: `tests/installer/test_netprofile.py`

**Schnittstellen:**
- Nutzt: `WifiCredentials` (Task 1)
- Liefert: `write_profile(wifi, target_root: Path, *, uuid_factory=uuid.uuid4) -> Path`

Dies erfüllt Spec §8.3. Ohne diesen Schritt startet der Nutzer ein frisch installiertes System ohne Netzwerk.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_netprofile.py
import configparser
import stat
import uuid

import pytest

from installer.core.model import WifiCredentials
from installer.core.netprofile import write_profile

FIXED = uuid.UUID("12345678-1234-5678-1234-567812345678")


def test_profile_is_written_to_the_expected_path(tmp_path):
    path = write_profile(
        WifiCredentials("FRITZ!Box 7590", "wlanpw"), tmp_path,
        uuid_factory=lambda: FIXED,
    )
    assert path == (
        tmp_path / "etc/NetworkManager/system-connections/FRITZ!Box 7590.nmconnection"
    )
    assert path.exists()


def test_profile_is_only_readable_by_root(tmp_path):
    """NetworkManager ignores profiles that are readable beyond mode 600."""
    path = write_profile(
        WifiCredentials("Fritz", "wlanpw"), tmp_path, uuid_factory=lambda: FIXED
    )
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_profile_contains_ssid_psk_and_autoconnect(tmp_path):
    path = write_profile(
        WifiCredentials("Fritz", "wlanpw"), tmp_path, uuid_factory=lambda: FIXED
    )
    parser = configparser.ConfigParser()
    parser.read(path)
    assert parser["wifi"]["ssid"] == "Fritz"
    assert parser["wifi-security"]["psk"] == "wlanpw"
    assert parser["connection"]["autoconnect"] == "true"
    assert parser["connection"]["type"] == "wifi"
    assert parser["connection"]["uuid"] == str(FIXED)
    assert parser["ipv4"]["method"] == "auto"


def test_slashes_in_ssid_do_not_escape_the_directory(tmp_path):
    path = write_profile(
        WifiCredentials("a/b/../etc", "pw"), tmp_path, uuid_factory=lambda: FIXED
    )
    expected_dir = tmp_path / "etc/NetworkManager/system-connections"
    assert path.parent == expected_dir


def test_empty_ssid_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        write_profile(WifiCredentials("", "pw"), tmp_path)
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_netprofile.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.netprofile'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/netprofile.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Carry the live environment's wireless credentials into the target.

Associating in the live session does not give the installed system
network access. Without this profile a freshly installed laptop without
an ethernet port boots with no way to get online.
"""
from __future__ import annotations

import uuid as uuid_module
from pathlib import Path
from typing import Callable

from .model import WifiCredentials

PROFILE_DIR = "etc/NetworkManager/system-connections"


def _safe_filename(ssid: str) -> str:
    """Keep a slash-bearing SSID from escaping the profile directory."""
    return ssid.replace("/", "_").replace("\x00", "")


def write_profile(
    wifi: WifiCredentials,
    target_root: Path,
    *,
    uuid_factory: Callable[[], uuid_module.UUID] = uuid_module.uuid4,
) -> Path:
    if not wifi.ssid:
        raise ValueError("refusing to write a profile without an SSID")

    directory = Path(target_root) / PROFILE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_filename(wifi.ssid)}.nmconnection"

    content = (
        "[connection]\n"
        f"id={wifi.ssid}\n"
        f"uuid={uuid_factory()}\n"
        "type=wifi\n"
        "autoconnect=true\n"
        "\n"
        "[wifi]\n"
        "mode=infrastructure\n"
        f"ssid={wifi.ssid}\n"
        "\n"
        "[wifi-security]\n"
        "key-mgmt=wpa-psk\n"
        f"psk={wifi.passphrase}\n"
        "\n"
        "[ipv4]\n"
        "method=auto\n"
        "\n"
        "[ipv6]\n"
        "method=auto\n"
    )

    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)
    return path
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_netprofile.py -v`
Erwartet: 5 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add installer/core/netprofile.py tests/installer/test_netprofile.py
git commit -m "feat(installer): WLAN-Profil in das Zielsystem uebertragen"
```

---

### Task 8: archinstall-Aufruf

**Dateien:**
- Anlegen: `installer/core/runner.py`
- Test: `tests/installer/test_runner.py`

**Schnittstellen:**
- Nutzt: `InstallConfig` (1), `validate` (2), `to_archinstall_config` / `to_archinstall_creds` (5), `probe` (4), `write_profile` (7)
- Liefert: `install(cfg, *, source=None, dry_run=False, target_root=Path('/mnt'), runner=subprocess.run) -> int`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_runner.py
import json
import stat
import subprocess
from pathlib import Path

import pytest

from installer.core.model import InstallConfig, DiskChoice, UserAccount, WifiCredentials
from installer.core.source import PackageSource
from installer.core.runner import install


def _cfg(**over) -> InstallConfig:
    base = dict(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda"),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="rootlanggenug",
    )
    base.update(over)
    return InstallConfig(**base)


class Spy:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.cmd = None

    def __call__(self, cmd, **kw):
        self.cmd = cmd
        return subprocess.CompletedProcess(cmd, self.returncode)


def test_invalid_config_is_refused_before_touching_disks():
    spy = Spy()
    with pytest.raises(ValueError, match="Benutzer"):
        install(_cfg(users=[]), source=PackageSource.ONLINE, runner=spy)
    assert spy.cmd is None


def test_archinstall_is_called_with_config_creds_and_silent(tmp_path):
    spy = Spy()
    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=spy)
    assert spy.cmd[0] == "archinstall"
    assert "--silent" in spy.cmd
    assert "--dry-run" in spy.cmd
    assert "--config" in spy.cmd and "--creds" in spy.cmd


def test_offline_source_adds_offline_flag(tmp_path):
    spy = Spy()
    install(_cfg(), source=PackageSource.OFFLINE, dry_run=True,
            target_root=tmp_path, runner=spy)
    assert "--offline" in spy.cmd


def test_written_creds_file_is_mode_600(tmp_path):
    captured = {}

    def spy(cmd, **kw):
        idx = cmd.index("--creds")
        path = Path(cmd[idx + 1])
        captured["mode"] = stat.S_IMODE(path.stat().st_mode)
        captured["body"] = json.loads(path.read_text())
        return subprocess.CompletedProcess(cmd, 0)

    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=spy)
    assert captured["mode"] == 0o600
    assert captured["body"]["users"][0]["enc_password"].startswith("$6$")


def test_wifi_profile_is_written_into_the_target(tmp_path):
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    install(cfg, source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=Spy())
    profile = tmp_path / "etc/NetworkManager/system-connections/Fritz.nmconnection"
    assert profile.exists(), "ohne dieses Profil bootet das Zielsystem ohne Netz"


def test_no_wifi_means_no_profile(tmp_path):
    install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=Spy())
    assert not (tmp_path / "etc/NetworkManager/system-connections").exists()


def test_nonzero_exit_is_propagated(tmp_path):
    rc = install(_cfg(), source=PackageSource.ONLINE, dry_run=True,
                 target_root=tmp_path, runner=Spy(returncode=7))
    assert rc == 7


def test_wifi_profile_is_not_written_when_archinstall_failed(tmp_path):
    cfg = _cfg(wifi=WifiCredentials("Fritz", "wlanpw"))
    install(cfg, source=PackageSource.ONLINE, dry_run=True,
            target_root=tmp_path, runner=Spy(returncode=1))
    profile = tmp_path / "etc/NetworkManager/system-connections/Fritz.nmconnection"
    assert not profile.exists()
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_runner.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.core.runner'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/core/runner.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hand the finished configuration over to archinstall.

Integration happens through archinstall's documented CLI rather than its
Python modules: the CLI is a stable contract, the internals change
between releases.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .model import InstallConfig
from .netprofile import write_profile
from .source import PackageSource, probe
from .translate import to_archinstall_config, to_archinstall_creds
from .validate import validate

Runner = Callable[..., subprocess.CompletedProcess]


def install(
    cfg: InstallConfig,
    *,
    source: PackageSource | None = None,
    dry_run: bool = False,
    target_root: Path = Path("/mnt"),
    runner: Runner | None = None,
) -> int:
    runner = runner or subprocess.run  # not a default: see passwords.py
    findings = validate(cfg)
    if findings:
        raise ValueError("; ".join(findings))

    source = source or probe()

    workdir = Path(tempfile.mkdtemp(prefix="zepos-install-"))
    config_path = workdir / "config.json"
    creds_path = workdir / "creds.json"

    config_path.write_text(
        json.dumps(to_archinstall_config(cfg, source), indent=2), encoding="utf-8"
    )
    creds_path.write_text(
        json.dumps(to_archinstall_creds(cfg), indent=2), encoding="utf-8"
    )
    creds_path.chmod(0o600)

    command = [
        "archinstall",
        "--config", str(config_path),
        "--creds", str(creds_path),
        "--silent",
        "--mountpoint", str(target_root),
    ]
    if source is PackageSource.OFFLINE:
        command.append("--offline")
    if dry_run:
        command.append("--dry-run")

    result = runner(command)

    # Only touch the target once archinstall reports success - otherwise
    # the profile would land in a half-installed or absent filesystem.
    if result.returncode == 0 and cfg.wifi is not None:
        write_profile(cfg.wifi, target_root)

    return result.returncode
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_runner.py -v`
Erwartet: 8 Tests PASS

- [ ] **Schritt 5: Gesamte Kernschicht prüfen**

Ausführen: `python -m pytest tests/installer -v`
Erwartet: alle Tests aus Task 1–8 PASS

- [ ] **Schritt 6: Committen**

```bash
git add installer/core/runner.py tests/installer/test_runner.py
git commit -m "feat(installer): archinstall-Aufruf ueber die dokumentierte CLI"
```

---

### Task 9: Textoberfläche

**Dateien:**
- Anlegen: `installer/tui/__init__.py` (leer), `installer/tui/app.py`
- Test: `tests/installer/test_tui.py`

**Schnittstellen:**
- Nutzt: alles aus `installer.core`
- Liefert: `collect(io, *, devices: Sequence[str], networks: Sequence[Network]) -> InstallConfig`, `main(argv=None) -> int`, `ConsoleIO`; `io` ist ein Objekt mit `ask(prompt, default="") -> str`, `ask_secret(prompt) -> str`, `choose(prompt, options) -> int`, `say(text) -> None`

Die TUI wird zuerst gebaut: sie ist ohne Grafikstack testbar und beweist, dass die Kernschicht eine vollständige Installation trägt. Die GTK4-Oberfläche in Task 10 füllt danach dasselbe Modell.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_tui.py
import pytest

from installer.tui.app import collect


class ScriptedIO:
    """Answers prompts in order from a scripted list."""

    def __init__(self, answers, choices):
        self.answers = list(answers)
        self.choices = list(choices)
        self.said = []

    def ask(self, prompt, default=""):
        return self.answers.pop(0) or default

    def ask_secret(self, prompt):
        return self.answers.pop(0)

    def choose(self, prompt, options):
        return self.choices.pop(0)

    def say(self, text):
        self.said.append(text)


def test_collect_builds_a_valid_config():
    io = ScriptedIO(
        answers=["zepos", "lars", "langgenug", "rootlanggenug", ""],
        choices=[0, 0, 0],   # Sprache, Datentraeger, WLAN ueberspringen
    )
    cfg = collect(io, devices=["/dev/vda"], networks=[])
    assert cfg.hostname == "zepos"
    assert cfg.users[0].username == "lars"
    assert cfg.disk.device == "/dev/vda"
    assert cfg.wifi is None


def test_collect_reports_validation_findings_and_reasks():
    io = ScriptedIO(
        answers=["zepos", "lars", "kurz", "langgenug", "rootlanggenug", ""],
        choices=[0, 0, 0],
    )
    cfg = collect(io, devices=["/dev/vda"], networks=[])
    assert any("Passwort" in text for text in io.said)
    assert cfg.users[0].password == "langgenug"
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_tui.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.tui.app'`

- [ ] **Schritt 3: Minimale Implementierung**

```python
# installer/tui/app.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Text interface. Fills the same model the GTK4 interface does.

All prompts go through an injected io object so the whole flow is
testable without a terminal.
"""
from __future__ import annotations

import getpass
import sys
from typing import Any, Sequence

from installer.core.model import (
    DiskChoice, InstallConfig, UserAccount, WifiCredentials, ZeposOptions,
)
from installer.core.runner import install
from installer.core.validate import MIN_PASSWORD_LENGTH
from installer.core.wifi import IwctlBackend, Network

LANGUAGES = [("de", "de-latin1", "de_DE", "Europe/Berlin"),
             ("en", "us", "en_US", "UTC")]


class ConsoleIO:
    def ask(self, prompt: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        return input(f"{prompt}{suffix}: ").strip() or default

    def ask_secret(self, prompt: str) -> str:
        return getpass.getpass(f"{prompt}: ")

    def choose(self, prompt: str, options: Sequence[str]) -> int:
        print(prompt)
        for index, option in enumerate(options, start=1):
            print(f"  {index}) {option}")
        while True:
            raw = input("Auswahl: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return int(raw) - 1
            print("Bitte eine der angebotenen Nummern eingeben.")

    def say(self, text: str) -> None:
        print(text)


def _ask_password(io: Any, label: str) -> str:
    while True:
        value = io.ask_secret(label)
        if len(value) >= MIN_PASSWORD_LENGTH:
            return value
        io.say(
            f"Das Passwort ist zu kurz. Mindestens {MIN_PASSWORD_LENGTH} Zeichen."
        )


def collect(
    io: Any,
    *,
    devices: Sequence[str],
    networks: Sequence[Network],
) -> InstallConfig:
    lang_index = io.choose("Sprache waehlen", ["Deutsch", "English"])
    language, keymap, locale, timezone = LANGUAGES[lang_index]

    hostname = io.ask("Rechnername", "zepos")

    disk_index = io.choose("Datentraeger waehlen", list(devices))
    device = devices[disk_index]

    username = io.ask("Benutzername")
    password = _ask_password(io, "Passwort")
    root_password = _ask_password(io, "Root-Passwort")

    wifi = None
    if networks:
        options = [n.ssid for n in networks] + ["Ueberspringen"]
        choice = io.choose("WLAN waehlen", options)
        if choice < len(networks):
            selected = networks[choice]
            passphrase = io.ask_secret(f"Passwort fuer {selected.ssid}")
            wifi = WifiCredentials(ssid=selected.ssid, passphrase=passphrase)

    weather = io.ask("Ort fuer das Wetter-Widget", "")

    return InstallConfig(
        language=language, keymap=keymap, timezone=timezone, locale=locale,
        hostname=hostname,
        disk=DiskChoice(device=device),
        users=[UserAccount(username=username, password=password, sudo=True)],
        root_password=root_password,
        wifi=wifi,
        zepos=ZeposOptions(enable_plugins=True, weather_location=weather),
    )


def main(argv: Sequence[str] | None = None) -> int:
    io = ConsoleIO()
    backend = IwctlBackend()

    try:
        wifi_devices = backend.devices()
        if wifi_devices:
            backend.scan(wifi_devices[0])
        networks = backend.networks(wifi_devices[0]) if wifi_devices else []
    except (RuntimeError, FileNotFoundError):
        networks = []

    import glob
    devices = sorted(glob.glob("/dev/sd?") + glob.glob("/dev/nvme?n?")
                     + glob.glob("/dev/vd?"))
    if not devices:
        io.say("Es wurde kein Datentraeger gefunden.")
        return 1

    cfg = collect(io, devices=devices, networks=networks)
    io.say("Installation wird gestartet.")
    return install(cfg)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_tui.py -v`
Erwartet: 2 Tests PASS

- [ ] **Schritt 5: Committen**

```bash
git add installer/tui tests/installer/test_tui.py
git commit -m "feat(installer): Textoberflaeche auf der Kernschicht"
```

---

### Task 10: GTK4-Oberfläche

**Dateien:**
- Anlegen: `installer/gui/__init__.py` (leer), `installer/gui/pages.py`, `installer/gui/app.py`
- Test: `tests/installer/test_gui.py`

**Schnittstellen:**
- Nutzt: alles aus `installer.core`
- Liefert: `PageState` (sammelt Eingaben unabhängig von Widgets), `PageState.to_config() -> InstallConfig`, `ZeposInstallerApp`, `main(argv=None) -> int`

Getestet wird `PageState`, nicht die Widgets. Widget-Tests brauchen eine laufende Anzeige und würden im Container nicht laufen; die Logik gehört ohnehin nicht in Callbacks.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_gui.py
import pytest

from installer.core.validate import validate
from installer.gui.pages import PageState, PAGE_ORDER


def test_page_order_matches_the_spec():
    assert PAGE_ORDER == [
        "sprache", "netzwerk", "datentraeger", "benutzer",
        "zeit", "zepos", "zusammenfassung",
    ]


def test_state_produces_a_valid_config():
    state = PageState()
    state.language = "de"
    state.hostname = "zepos"
    state.device = "/dev/vda"
    state.username = "lars"
    state.password = "langgenug"
    state.root_password = "rootlanggenug"
    assert validate(state.to_config()) == []


def test_wifi_only_set_when_ssid_present():
    state = PageState()
    state.hostname = "zepos"
    state.device = "/dev/vda"
    state.username = "lars"
    state.password = "langgenug"
    state.root_password = "rootlanggenug"
    assert state.to_config().wifi is None
    state.wifi_ssid = "Fritz"
    state.wifi_passphrase = "wlanpw"
    assert state.to_config().wifi.ssid == "Fritz"


def test_language_selection_sets_keymap_locale_and_timezone():
    state = PageState()
    state.language = "de"
    cfg = state.to_config()
    assert (cfg.keymap, cfg.locale, cfg.timezone) == (
        "de-latin1", "de_DE", "Europe/Berlin"
    )


def test_findings_are_exposed_for_the_summary_page():
    state = PageState()
    assert any("Benutzer" in f for f in state.findings())
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_gui.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'installer.gui.pages'`

- [ ] **Schritt 3: Zustandsmodell implementieren**

```python
# installer/gui/pages.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""State behind the GTK4 pages.

Kept free of widgets on purpose: logic inside callbacks cannot be tested
without a display, and would have to be rewritten if the surface changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from installer.core.model import (
    DiskChoice, InstallConfig, UserAccount, WifiCredentials, ZeposOptions,
)
from installer.core.validate import validate

PAGE_ORDER = [
    "sprache", "netzwerk", "datentraeger", "benutzer",
    "zeit", "zepos", "zusammenfassung",
]

LANGUAGE_DEFAULTS = {
    "de": ("de-latin1", "de_DE", "Europe/Berlin"),
    "en": ("us", "en_US", "UTC"),
}


@dataclass
class PageState:
    language: str = "de"
    hostname: str = "zepos"
    device: str = ""
    wipe: bool = True
    username: str = ""
    password: str = ""
    root_password: str = ""
    wifi_ssid: str = ""
    wifi_passphrase: str = ""
    timezone: str = ""
    enable_plugins: bool = True
    weather_location: str = ""

    def to_config(self) -> InstallConfig:
        keymap, locale, default_tz = LANGUAGE_DEFAULTS[self.language]
        wifi = (
            WifiCredentials(ssid=self.wifi_ssid, passphrase=self.wifi_passphrase)
            if self.wifi_ssid
            else None
        )
        users = (
            [UserAccount(username=self.username, password=self.password, sudo=True)]
            if self.username
            else []
        )
        return InstallConfig(
            language=self.language,
            keymap=keymap,
            locale=locale,
            timezone=self.timezone or default_tz,
            hostname=self.hostname,
            disk=DiskChoice(device=self.device, wipe=self.wipe),
            users=users,
            root_password=self.root_password,
            wifi=wifi,
            zepos=ZeposOptions(
                enable_plugins=self.enable_plugins,
                weather_location=self.weather_location,
            ),
        )

    def findings(self) -> list[str]:
        return validate(self.to_config())
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_gui.py -v`
Erwartet: 5 Tests PASS

- [ ] **Schritt 5: GTK4-Hülle implementieren**

```python
# installer/gui/app.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK4/libadwaita surface. Widgets only - all logic lives in pages.py."""
from __future__ import annotations

import sys
from typing import Sequence

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from installer.core.runner import install  # noqa: E402
from .pages import PAGE_ORDER, PageState  # noqa: E402

PAGE_TITLES = {
    "sprache": "Sprache und Tastatur",
    "netzwerk": "Netzwerk",
    "datentraeger": "Datentraeger",
    "benutzer": "Benutzer",
    "zeit": "Zeitzone",
    "zepos": "ZepOS-Optionen",
    "zusammenfassung": "Zusammenfassung",
}


class InstallerWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, state: PageState) -> None:
        super().__init__(application=app, title="ZepOS installieren")
        self.set_default_size(900, 620)
        self.state = state
        self.index = 0

        self.stack = Gtk.Stack()
        for name in PAGE_ORDER:
            self.stack.add_named(self._build_page(name), name)

        self.back = Gtk.Button(label="Zurueck")
        self.back.connect("clicked", lambda _b: self._step(-1))
        self.forward = Gtk.Button(label="Weiter")
        self.forward.connect("clicked", lambda _b: self._step(1))

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        actions.set_margin_top(12)
        actions.set_margin_bottom(12)
        actions.set_margin_end(12)
        actions.append(self.back)
        actions.append(self.forward)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        layout.append(Adw.HeaderBar())
        layout.append(self.stack)
        layout.append(actions)
        self.set_content(layout)
        self._sync()

    def _build_page(self, name: str) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title=PAGE_TITLES[name])
        page.add(group)
        return page

    def _step(self, delta: int) -> None:
        target = self.index + delta
        if not 0 <= target < len(PAGE_ORDER):
            return
        self.index = target
        self._sync()

    def _sync(self) -> None:
        self.stack.set_visible_child_name(PAGE_ORDER[self.index])
        self.back.set_sensitive(self.index > 0)
        last = self.index == len(PAGE_ORDER) - 1
        self.forward.set_label("Installieren" if last else "Weiter")
        self.forward.set_sensitive(not last or not self.state.findings())


class ZeposInstallerApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.zepos.Installer")
        self.state = PageState()

    def do_activate(self) -> None:
        InstallerWindow(self, self.state).present()


def main(argv: Sequence[str] | None = None) -> int:
    return ZeposInstallerApp().run(list(argv) if argv else [])


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Schritt 6: Prüfen, dass die Anwendung ohne Anzeige sauber scheitert**

Ausführen:
```bash
python -m pytest tests/installer/test_gui.py -v
python -c "import installer.gui.pages" && echo "pages importierbar ohne GTK"
```
Erwartet: Tests PASS, und der Import von `pages` gelingt ohne GTK-Bibliotheken

- [ ] **Schritt 7: Committen**

```bash
git add installer/gui tests/installer/test_gui.py
git commit -m "feat(installer): GTK4-Oberflaeche mit widgetfreiem Zustandsmodell"
```

---

### Task 11: Einstiegspunkt mit Rückfall

**Dateien:**
- Anlegen: `installer/bin/zepos-install`
- Test: `tests/installer/test_entry.py`

**Schnittstellen:**
- Nutzt: `installer.gui.app.main`, `installer.tui.app.main`
- Liefert: `choose_surface(env, gui_available) -> str`, `main(argv=None) -> int`

Erfüllt Spec §8.5: Startet die grafische Sitzung nicht, übernimmt die TUI. Erkennung über den tatsächlichen Startversuch, nicht über eine Hardware-Liste.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
# tests/installer/test_entry.py
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "zepos_install", Path("installer/bin/zepos-install")
)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def test_gui_chosen_when_display_and_gtk_available():
    assert entry.choose_surface({"WAYLAND_DISPLAY": "wayland-0"}, True) == "gui"


def test_tui_chosen_without_display():
    assert entry.choose_surface({}, True) == "tui"


def test_tui_chosen_when_gtk_import_fails():
    assert entry.choose_surface({"WAYLAND_DISPLAY": "wayland-0"}, False) == "tui"


def test_explicit_tui_request_wins():
    assert entry.choose_surface(
        {"WAYLAND_DISPLAY": "wayland-0", "ZEPOS_INSTALLER_SURFACE": "tui"}, True
    ) == "tui"


def test_x11_display_also_counts():
    assert entry.choose_surface({"DISPLAY": ":0"}, True) == "gui"
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen: `python -m pytest tests/installer/test_entry.py -v`
Erwartet: FAIL, weil `installer/bin/zepos-install` nicht existiert

- [ ] **Schritt 3: Minimale Implementierung**

```python
#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point. Picks the graphical surface when one can actually run.

Detection is by attempting the import and looking for a display, not by
matching hardware: an unknown GPU must degrade to the text interface
rather than leave the ISO without any installer at all.
"""
from __future__ import annotations

import os
import sys
from typing import Mapping, Sequence


def gtk_importable() -> bool:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk  # noqa: F401
    except (ImportError, ValueError):
        return False
    return True


def choose_surface(env: Mapping[str, str], gui_available: bool) -> str:
    requested = env.get("ZEPOS_INSTALLER_SURFACE")
    if requested in {"gui", "tui"}:
        return requested
    has_display = bool(env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"))
    return "gui" if has_display and gui_available else "tui"


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    surface = choose_surface(os.environ, gtk_importable())

    if surface == "gui":
        from installer.gui.app import main as gui_main

        try:
            return gui_main(argv)
        except Exception as exc:  # noqa: BLE001 - a broken GUI must not end the install
            print(f"Grafische Oberflaeche nicht verfuegbar ({exc}).", file=sys.stderr)
            print("Es wird auf die Textoberflaeche gewechselt.", file=sys.stderr)

    from installer.tui.app import main as tui_main

    return tui_main(argv)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: `python -m pytest tests/installer/test_entry.py -v`
Erwartet: 5 Tests PASS

- [ ] **Schritt 5: Ausführbar machen und committen**

```bash
chmod +x installer/bin/zepos-install
git add installer/bin/zepos-install tests/installer/test_entry.py
git commit -m "feat(installer): Einstiegspunkt mit Rueckfall auf die Textoberflaeche"
```

---

### Task 12: Integrationstest in QEMU

**Dateien:**
- Anlegen: `tests/integration/test_dry_run.sh`
- Anlegen: `tests/integration/README.md`

**Schnittstellen:**
- Nutzt: `installer/bin/zepos-install`, gesamte Kernschicht
- Liefert: ein Skript, das ohne root und ohne echten Datenträger beweist, dass eine vollständige Konfiguration von `archinstall` angenommen wird

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```bash
# tests/integration/test_dry_run.sh
#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Prueft, dass eine vom Installer erzeugte Konfiguration von archinstall
# tatsaechlich akzeptiert wird. Laeuft im Container, ohne root, ohne
# Datentraeger - --dry-run erzeugt die Konfiguration und beendet sich.
set -euo pipefail

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

python - "$WORK" <<'PY'
import json, sys
from pathlib import Path
from installer.core.model import (
    InstallConfig, DiskChoice, UserAccount, WifiCredentials, ZeposOptions,
)
from installer.core.source import PackageSource
from installer.core.translate import to_archinstall_config, to_archinstall_creds

work = Path(sys.argv[1])
cfg = InstallConfig(
    language="de", keymap="de-latin1", timezone="Europe/Berlin",
    locale="de_DE", hostname="zepos",
    disk=DiskChoice(device="/dev/vda"),
    users=[UserAccount(username="lars", password="langgenug")],
    root_password="rootlanggenug",
    wifi=WifiCredentials("Fritz", "wlanpw"),
    zepos=ZeposOptions(),
)
(work / "config.json").write_text(
    json.dumps(to_archinstall_config(cfg, PackageSource.OFFLINE), indent=2))
(work / "creds.json").write_text(json.dumps(to_archinstall_creds(cfg), indent=2))
PY

echo "--- archinstall nimmt die Konfiguration an? ---"
archinstall --config "$WORK/config.json" \
            --creds "$WORK/creds.json" \
            --silent --dry-run --skip-version-check --skip-wifi-check

echo "OK: archinstall hat die ZepOS-Konfiguration akzeptiert."
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

Ausführen:
```bash
chmod +x tests/integration/test_dry_run.sh
sudo -n docker run --rm --network host -v "$PWD":/src -w /src archlinux:latest \
  bash -c 'pacman -Sy --noconfirm >/dev/null && \
           pacman -S --noconfirm archinstall python openssl >/dev/null && \
           ./tests/integration/test_dry_run.sh'
```
Erwartet: FAIL, solange die Kernschicht nicht vollständig ist

- [ ] **Schritt 3: Auftretende Feldabweichungen beheben**

`archinstall` meldet unbekannte oder fehlende Felder im Klartext. Jede Meldung wird in `installer/core/translate.py` korrigiert **und** durch einen Testfall in `tests/installer/test_translate.py` festgehalten, damit sie nicht zurückkehrt.

- [ ] **Schritt 4: Test laufen lassen, Erfolg bestätigen**

Ausführen: derselbe Befehl wie in Schritt 2
Erwartet: `OK: archinstall hat die ZepOS-Konfiguration akzeptiert.`

- [ ] **Schritt 5: Anleitung schreiben**

```markdown
# tests/integration/README.md

## Voraussetzungen

Der Container braucht `--network host`. Der aktive IPsec-Tunnel routet
10.0.0.0/8, 172.16.0.0/12 und 192.168.0.0/16; die Docker-Bridge liegt bei
<Docker-Bridge> und damit innerhalb von 10.0.0.0/8. Ohne `--network host`
hat der Container kein Netz. Siehe Spec §10.1.

## Ausfuehren

    sudo docker run --rm --network host -v "$PWD":/src -w /src \
      archlinux:latest bash -c \
      'pacman -Sy --noconfirm >/dev/null && \
       pacman -S --noconfirm archinstall python openssl >/dev/null && \
       ./tests/integration/test_dry_run.sh'

## Was geprueft wird

Dass `archinstall` die vom Installer erzeugten `config.json` und
`creds.json` annimmt. `--dry-run` erzeugt die Konfiguration und beendet
sich, ohne einen Datentraeger zu beruehren. Kein root noetig.

## Was hier NICHT geprueft wird

Eine echte Installation. Die gehoert in Teilprojekt 5 gegen ein
QEMU-Abbild, sobald die ISO existiert.
```

- [ ] **Schritt 6: Committen**

```bash
git add tests/integration
git commit -m "test(installer): Integrationstest gegen archinstall --dry-run"
```

---

## Abgleich mit der Spezifikation

| Spec | Umgesetzt in |
|---|---|
| §8.1 Drei Schichten, UI kennt archinstall nicht | Task 1 (Modell), Task 5 (Übersetzung), Tasks 9/10 (Oberflächen ohne archinstall-Import) |
| §8.1 Serialisierbares Modell für unbeaufsichtigte Installation | Task 1 (`to_dict`/`from_dict`, `schema_version`) |
| §8.1 archinstall macht Partitionierung und Bootloader | Task 8 (kein eigener Partitionierungscode) |
| §8.2 Sieben Schritte | Task 9 (`collect`), Task 10 (`PAGE_ORDER`) |
| §8.3 WLAN-Profil ins Zielsystem, Modus 600 | Task 7, geprüft in Task 8 |
| §8.4 Hybride Paketquelle | Task 4, verdrahtet in Task 5 und 8 |
| §8.5 Rückfall GTK4 → TUI über Startversuch | Task 11 |
| §8.6 Signierung: `sign_check` Required | Task 4 |
| Global: keine Klartextpasswörter in `config.json` | Task 5 (`test_config_contains_no_plaintext_password`) |
| Global: kein `crypt`-Modul | Task 3 |
| Global: Tests ohne root | Tasks 1–11 gemockt, Task 12 über `--dry-run` |

## Offen, gehört in Teilprojekt 5

- Die tatsächliche Installation gegen ein QEMU-Abbild — braucht die fertige ISO
- Die Partitionsdefinition in `disk_config.device_modifications[].partitions`: Task 5 setzt sie leer und überlässt `archinstall` das Standardschema. Sobald der Datenträgerschritt in der Oberfläche eigene Layouts anbietet, muss die Struktur aus `archinstall/examples/disk_layouts-sample.json` nachgebildet werden
- `ONLINE_REPO_URL` in `source.py` zeigt auf `repo.zepos.org`; die Adresse existiert noch nicht. Solange nur offline installiert wird, ist das folgenlos
