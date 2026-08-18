# SPDX-License-Identifier: GPL-3.0-or-later
"""Surface-independent data model for a ZepOS installation.

The UI fills this model and nothing else. Translation to archinstall's
own format happens in translate.py, so the UI never learns archinstall's
schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from .i18n import _
from .layout import MIN_DISK_MIB, PlannedPartition

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


# The minimum disk size both validate() and translate() enforce: an EFI
# system partition, GPT's primary and backup headers, and headroom for
# the root filesystem.
#
# Re-exported from installer.core.layout rather than written out again.
# It used to be the literal 2562 with the sum in a comment beside it, and
# the four numbers it adds up are now the same four constants the planner
# lays a partition table out with - two copies of one rule are two copies
# that can be changed one at a time. Every existing caller imports it
# from here, which is why the name stays.
__all__ = [
    "DiskChoice", "InstallConfig", "MIN_DISK_MIB", "SCHEMA_VERSION",
    "UserAccount", "WifiCredentials", "ZeposOptions",
]


@dataclass
class DiskChoice:
    device: str
    wipe: bool = True
    filesystem: str = "ext4"
    size_bytes: int = 0
    # Die Einteilung, die der Assistent geplant hat, oder leer.
    #
    # Leer heisst NICHT "keine Partitionen" - das waere die eine Eingabe,
    # die eine Platte loescht und nichts anlegt. Leer heisst "niemand hat
    # sich geaeussert", und installer.core.translate setzt dafuer den
    # Vorschlag ein (ESP + Wurzel). Das ist der Zustand, in dem der
    # Textassistent und jede aeltere Konfigurationsdatei ankommen, und
    # beide sollen weiter genau das bekommen, was sie vorher bekamen.
    layout: list[PlannedPartition] = field(default_factory=list)
    # Ob die Platte verschluesselt wird, und womit sie aufgesperrt wird.
    #
    # WARUM DIE VORGABE HIER False IST, OBWOHL DER ASSISTENT DEN HAKEN
    # GESETZT ANBIETET
    #     Weil dieses Feld zwei Aufrufer hat und die Vorgabe nur fuer den
    #     zweiten gilt. Der Assistent SETZT den Haken ausdruecklich
    #     (installer.gui.pages.PageState.encrypt, installer.tui.app -
    #     dort steht auch die Begruendung dafuer). Was hier steht, ist,
    #     was eine Konfigurationsdatei bekommt, in der von
    #     Verschluesselung nichts steht - und das sind alle, die vor
    #     dieser Seite geschrieben wurden.
    #
    #     Dieselbe Unterscheidung wie bei `layout` darueber: leer heisst
    #     "niemand hat sich geaeussert", nicht "niemand will es". Waere
    #     die Vorgabe True, wuerde jede aeltere Datei mit einer
    #     Verschluesselung ohne Passphrase ankommen, und
    #     installer.core.validate lehnt sie dann zu Recht ab - eine
    #     Aenderung, die bestehende Dateien unbrauchbar macht, ohne dass
    #     jemand danach gefragt haette.
    encrypt: bool = False
    # Die Passphrase, im Klartext, mit derselben Auflage wie jedes andere
    # Passwort in dieser Datei: siehe InstallConfig.to_dict() unten.
    #
    # Sie MUSS im Klartext hierher, weil cryptsetup sie im Klartext
    # braucht - aus einem Hash laesst sich kein Schluessel ableiten, und
    # anders als bei einem Benutzerpasswort gibt es keinen zweiten Weg
    # ins System, ueber den man sie nachtraeglich setzen koennte.
    passphrase: str = ""


@dataclass
class ZeposOptions:
    enable_plugins: bool = True
    weather_location: str = ""
    # Die drei Zusatzpakete, die die ZepOS-Seite anbietet.
    #
    # Alle drei stehen auf False, und das ist die Aussage: ZepOS liefert
    # aus, was in packaging/zepos-apps steht, und fragt nach dem Rest.
    # Was hier angehakt wird, kostet Zeit und Platz - gemessen am
    # angehefteten Schnappschuss 2026/08/04 gegen die Maschine, auf der
    # der Haken gesetzt wird, also gegen archinstall-Basis plus
    # zepos-desktop plus zepos-apps (564 Pakete, 3,2 GiB installiert):
    #
    #     office    +42 Pakete   +177,5 MiB Download   +646,1 MiB
    #     devel     +31 Pakete    +99,2 MiB Download   +440,2 MiB
    #     firefox    +3 Pakete    +83,5 MiB Download   +292,1 MiB
    #
    # Die Rezepte nennen groessere Zahlen fuer dieselben Pakete
    # (724,4 und 510,3 MiB). Das ist kein Widerspruch, sondern eine
    # andere Grundlinie: dort ohne zepos-apps, hier mit. Was zepos-apps
    # schon mitbringt - poppler, perl, harfbuzz-icu, libxslt und drei
    # Dutzend andere - zahlt niemand zweimal.
    #
    # firefox ist der einzige, der nicht auf ein ZepOS-Metapaket zeigt,
    # und der einzige, der einen Namen aus den offiziellen Quellen
    # direkt setzt. Warum es ihn ueberhaupt gibt, steht in
    # installer/core/translate.py bei OPTIONAL_PACKAGES - kurz: der
    # Nutzer hat ihn am 11.08.2026 namentlich verlangt, und die
    # ausgelieferte Auswahl kann ihn aus einem gemessenen Grund nicht
    # enthalten.
    install_office: bool = False
    install_devel: bool = False


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
        """Serialise the whole configuration, PASSWORDS IN CLEAR TEXT.

        Every user password, the root password, the wireless passphrase
        AND THE DISK PASSPHRASE come out of here exactly as they were
        typed. That is what makes an unattended installation possible at
        all - the hashes in creds.json are derived from these, and
        nothing can reverse a hash back into what archinstall needs.

        The disk passphrase is the one that cannot even be hashed on the
        way: cryptsetup needs the characters themselves, so it travels in
        the clear from here to creds.json and nowhere else. Losing it
        costs the account; leaking it costs the disk.

        The consequence belongs to whoever calls this: the result must
        never be written to a path other people can read, logged, or put
        into a bug report. installer.core.runner writes only the DERIVED
        creds.json, with the umask narrowed and mode 0600 - this method
        is not used on that path.
        """
        data = asdict(self)
        data["schema_version"] = SCHEMA_VERSION
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstallConfig:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                _("unsupported schema_version {version}, expected {expected}").format(
                    version=version, expected=SCHEMA_VERSION
                )
            )
        payload = {k: v for k, v in data.items() if k != "schema_version"}
        wifi = payload.pop("wifi", None)
        return cls(
            **payload | {
                "disk": _disk_from_dict(payload["disk"]),
                "users": [UserAccount(**u) for u in payload["users"]],
                "zepos": ZeposOptions(**payload["zepos"]),
                "wifi": WifiCredentials(**wifi) if wifi else None,
            }
        )


def _disk_from_dict(payload: dict[str, Any]) -> DiskChoice:
    """Eine DiskChoice aus dem, was to_dict() geschrieben hat.

    Nicht `DiskChoice(**payload)`, und der Grund ist die Einteilung.
    asdict() macht aus jeder PlannedPartition ein dict, und JSON macht
    aus dem Tupel in `flags` eine Liste - beides kaeme hier sonst als
    dict bzw. list wieder herein, und ein dict hat kein .size_mib. Der
    Fehler faellt erst in installer.core.translate auf, also in dem
    Augenblick, in dem eine unbeaufsichtigte Installation die Platte
    schon fuer sich hat.

    `layout` fehlt in jeder Konfigurationsdatei, die vor dieser Seite
    geschrieben wurde. Das ist kein Fehler, sondern der Normalfall aus
    Sicht des Textassistenten: eine leere Einteilung heisst "nimm den
    Vorschlag" (siehe DiskChoice.layout).
    """
    fields = dict(payload)
    planned = fields.pop("layout", [])
    return DiskChoice(
        **fields,
        layout=[
            entry if isinstance(entry, PlannedPartition)
            else PlannedPartition(
                start_mib=entry["start_mib"],
                size_mib=entry["size_mib"],
                filesystem=entry["filesystem"],
                mountpoint=entry.get("mountpoint", ""),
                flags=tuple(entry.get("flags", ())),
            )
            for entry in planned
        ],
    )
