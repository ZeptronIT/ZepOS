# SPDX-License-Identifier: GPL-3.0-or-later
"""Where things live once ZepOS ships as a package.

The origin project kept sources, configuration and generated output in one
directory under the user's home. A pacman package may own nothing below ~,
so the three roles are separated here:

  /usr/share/zepos     templates, generator, SSOT   owned by the package
  ~/.config/zepos      settings and overrides       owned by the user
  ~/.config/<app>      generated output             written by the generator

Both roots are overridable through the environment so tests never touch
the real ones. ZEPOS_SYSTEM_ROOT and ZEPOS_USER_ROOT exist for tests and
packaging tools, not as end-user configuration: exporting either one
permanently in a shell profile makes every template lookup miss silently,
against a directory nothing else has written to, with no error to point
at the cause.

ZWEI WURZELN, DIE KEINEM BENUTZER GEHOEREN
    Die drei oben beschreiben je einen Benutzer. Die Selbstaktualisierung
    (src/update.py) beschreibt dagegen die MASCHINE: sie laeuft als
    Systemdienst, bevor sich jemand angemeldet hat, und ein Dienst als
    root darf nicht raten muessen, in wessen Heimatverzeichnis die
    Entscheidung liegt - auf einer Maschine mit zwei Konten gaebe es zwei
    Antworten auf eine Frage, die der Zeitgeber nur einmal beantworten
    kann.

      /etc/zepos      was die Maschine entschieden hat   machine_root()
      /var/lib/zepos  was zuletzt passiert ist           state_root()

    Beide sind aus demselben Grund ueber die Umgebung umlenkbar wie die
    zwei oben: ein Test darf /etc und /var nicht anfassen, und die
    Isolationssperre in tests/conftest.py laesst ihn auch gar nicht.
"""
from __future__ import annotations

import os
from pathlib import Path

SYSTEM_ROOT = Path("/usr/share/zepos")
SYSTEM_ROOT_ENV = "ZEPOS_SYSTEM_ROOT"
USER_ROOT_ENV = "ZEPOS_USER_ROOT"
MACHINE_ROOT = Path("/etc/zepos")
MACHINE_ROOT_ENV = "ZEPOS_MACHINE_ROOT"
STATE_ROOT = Path("/var/lib/zepos")
STATE_ROOT_ENV = "ZEPOS_STATE_ROOT"
TEMPLATE_SUFFIX = ".template"


def _config_home() -> Path:
    """XDG_CONFIG_HOME if set, else the conventional ~/.config."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    return Path(config_home) if config_home else Path.home() / ".config"


def system_root() -> Path:
    override = os.environ.get(SYSTEM_ROOT_ENV)
    return Path(override) if override else SYSTEM_ROOT


def user_root() -> Path:
    override = os.environ.get(USER_ROOT_ENV)
    return Path(override) if override else _config_home() / "zepos"


def machine_root() -> Path:
    """Was die Maschine ueber sich selbst entschieden hat.

    Nur die Selbstaktualisierung liegt heute darin. /etc und nicht
    /usr/share, weil ein Administrator die Datei aendern koennen muss,
    ohne dass das naechste `pacman -Syu` sie wegwirft - dieselbe
    Unterscheidung, die zepos-configs backup=() fuer die zwei
    greetd-Dateien trifft.
    """
    override = os.environ.get(MACHINE_ROOT_ENV)
    return Path(override) if override else MACHINE_ROOT


def state_root() -> Path:
    """Was zuletzt passiert ist - kein Zustand, den jemand einstellt.

    Getrennt von machine_root(), weil das eine ein Protokoll ist und das
    andere eine Entscheidung: eine Sicherung von /etc soll die Frage
    "aktualisiert sich diese Maschine?" mitnehmen und nicht die Antwort
    auf "wann zuletzt?".
    """
    override = os.environ.get(STATE_ROOT_ENV)
    return Path(override) if override else STATE_ROOT


def user_state_root() -> Path:
    """Was DIESES Konto zuletzt getan hat - nicht, was es eingestellt hat.

    Die dritte Sorte Zustand, neben state_root() der Maschine und
    user_root() der Einstellungen. src/bin/zepos-session legt sein
    Protokoll und seinen Erzeugungs-Zeitstempel bereits hierhin und
    rechnet den Pfad dabei selbst aus; hier steht er, damit ein
    Python-Leser dieselbe Stelle findet.

    XDG_STATE_HOME und nicht XDG_RUNTIME_DIR: eine Sitzung, die nicht
    hochkommt, nimmt ihr Laufzeitverzeichnis beim Abmelden mit, und
    genau dann will jemand nachsehen, woran es lag.
    """
    state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(state_home) if state_home else Path.home() / ".local" / "state"
    return root / "zepos"


# Die Bitte dieses Kontos, beim naechsten Anmelden neu zu erzeugen.
#
# WARUM ES SIE GIBT
#     Eine geaenderte Einstellung veraendert die erzeugte Konfiguration
#     erst, wenn der Generator laeuft - und der beendet an seinem Ende
#     AGS und startet es neu. Auf einem laufenden Schreibtisch ist das
#     ein Eingriff: die Leiste und jedes Ueberlagerungsfenster
#     verschwinden fuer einen Moment, mitten in der Arbeit. GEMESSEN am
#     11.08.2026 an der Maschine des Entwicklers, und src/update.py
#     zieht daraus schon dieselbe Folgerung fuer den Aktualisierer.
#
#     Ohne diese Marke haette eine Einstellungs-Anwendung nur zwei
#     Antworten: sofort erzeugen (also eingreifen) oder gar nicht
#     erzeugen (also eine Einstellung, die nie ankommt - genau die
#     Reglertabelle, die kein Byte bewegt). Die Marke ist die dritte:
#     gespeichert ist gespeichert, und spaetestens die naechste
#     Anmeldung setzt es um.
#
# WARUM DERSELBE NAME WIE update.REGENERATE_MARKER
#     Weil es dieselbe Aussage ist, nur von jemand anderem: dort sagt die
#     MASCHINE "es wurden Pakete getauscht", hier sagt ein KONTO "ich
#     habe etwas eingestellt". src/bin/zepos-session liest beide und
#     erzeugt in beiden Faellen vor dem Compositor neu - an der einzigen
#     Stelle, an der ein vollstaendiges Neuerzeugen keine laufende
#     Sitzung trifft.
#
#     Getrennte Dateien, weil sie verschiedenen Leuten gehoeren: die
#     unter /var/lib gehoert root und kann von einer Sitzung nicht
#     geloescht werden, diese gehoert dem Konto und WIRD geloescht,
#     sobald sie erfuellt ist. Genau deshalb braucht die eine einen
#     Zeitstempelvergleich und diese nicht.
SESSION_REGENERATE_MARKER = "regenerate-required"


def session_regenerate_marker() -> Path:
    return user_state_root() / SESSION_REGENERATE_MARKER


def output_root() -> Path:
    """Where generated configuration goes - never below the package root."""
    return _config_home()


def find_template(name: str) -> Path:
    """Resolve a template name, user copy first.

    A user override wins so that updating the package does not discard
    what someone changed. Without this, pacman -Syu would silently revert
    every local edit.

    `name` reaches here from configuration files, so it is treated as
    untrusted. It is rejected unless it is a single, ordinary path
    component:

      - empty, or starting with "." - rules out "..", ".", and hidden
        files, none of which are legitimate template names.
      - containing "/" - rules out both a relative traversal such as
        "../../etc/passwd" *and* an absolute path such as "/etc/passwd".
        The second case matters on its own: pathlib's `/` operator does
        not append an absolute right-hand side to the base, it discards
        the base and returns the absolute path unchanged, so an
        absolute name would otherwise resolve outside both roots even
        though "escaping" is exactly what the slash check is meant to
        stop.

    With "/" excluded, `name` can only ever be a single filesystem path
    component. On POSIX, the only components that mean "leave this
    directory" are the literal strings "." and "..", and both start with
    ".", so nothing that reaches the filesystem call below can name
    anything outside `<root>/templates/`.
    """
    if not name or "/" in name or name.startswith("."):
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
