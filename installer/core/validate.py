# SPDX-License-Identifier: GPL-3.0-or-later
"""Validation of an InstallConfig.

Returns findings the UI can present verbatim. An empty list means the
configuration may be installed. Every finding goes through _(), because
these strings are shown to the person installing the system.
"""
from __future__ import annotations

import re

from .crypt import (
    MIN_PASSPHRASE_LENGTH, effective_layout, encrypted_partitions,
)
from .i18n import _
from .model import InstallConfig, MIN_DISK_MIB

# Public: installer.tui.app validates a hostname interactively, at the
# point of entry, against this exact pattern - one source of truth, so
# the two can never drift into accepting different hostnames.
HOSTNAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
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

    if not HOSTNAME_PATTERN.match(cfg.hostname):
        # A single literal, not two concatenated ones: see the matching
        # comment in netprofile.py - the source-vs-catalogue completeness
        # check in test_i18n.py cannot follow Python's implicit string
        # concatenation across literals.
        findings.append(
            _("The hostname may contain only letters, digits and hyphens, and may not start or end with a hyphen.")
        )

    if not cfg.disk.device:
        findings.append(_("No disk was selected."))

    if cfg.disk.device and cfg.disk.size_bytes // (1024 * 1024) < MIN_DISK_MIB:
        findings.append(
            _("The selected disk is too small. At least {minimum} MiB are required.")
            .format(minimum=MIN_DISK_MIB)
        )

    if cfg.wifi is not None and not cfg.wifi.passphrase:
        findings.append(_("No password was given for the wireless network."))

    findings.extend(_encryption_findings(cfg))

    return findings


def _encryption_findings(cfg: InstallConfig) -> list[str]:
    """Was eine verschluesselte Installation daran hindert, eine zu sein.

    WARUM DAS HIER STEHT UND NICHT NUR AUF DER SEITE
        Weil die Seite nicht der einzige Weg hierher ist.
        installer.core.runner.install() ruft validate() unmittelbar vor
        dem Loeschen, und es ruft es auch fuer eine Konfigurationsdatei,
        die niemand durch eine Oberflaeche geschickt hat.

    WARUM EIN FEHLENDES PASSWORT EIN BEFUND IST UND NICHT NUR EIN
    LEERES FELD
        Das ist der Unterschied, auf den es bei dieser ganzen Aenderung
        ankommt. archinstall 4.4 lehnt eine Verschluesselung ohne
        Passphrase nicht ab - DiskEncryption.parse_arg() gibt None
        zurueck (`if not password: return None`), die Installation laeuft
        weiter, meldet Erfolg und hinterlaesst eine Platte im Klartext.
        Wer nur prueft, ob der Haken gesetzt war, prueft genau diesen
        Fall nicht.
    """
    if not cfg.disk.encrypt:
        return []

    findings: list[str] = []

    if not cfg.disk.passphrase:
        findings.append(_("Disk encryption is switched on, but no passphrase was given. Without one the disk would be installed unencrypted."))
    elif len(cfg.disk.passphrase) < MIN_PASSPHRASE_LENGTH:
        findings.append(_("The passphrase is too short. At least {minimum} characters are required, and there is no way to reset it later.").format(
            minimum=MIN_PASSPHRASE_LENGTH))

    # Die Einteilung ueber effective_layout(), also mit demselben
    # Vorschlag, den installer.core.translate einsetzen wuerde. Sonst
    # meldete diese Pruefung "nichts zu verschluesseln" fuer jede
    # Konfiguration ohne eigene Einteilung - also fuer den Textassistenten
    # und fuer jede aeltere Datei.
    plan = effective_layout(
        cfg.disk.layout, cfg.disk.size_bytes, filesystem=cfg.disk.filesystem)
    if not encrypted_partitions(plan):
        findings.append(_("Disk encryption is switched on, but this layout has nothing that can be encrypted."))

    return findings
