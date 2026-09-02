# SPDX-License-Identifier: GPL-3.0-or-later
"""State behind the GTK4 pages.

Kept free of widgets on purpose: logic inside GTK callbacks cannot be
tested without a display, and would have to be rewritten if the surface
ever changed. Every method here is a pure function of PageState's own
fields (plus, where noted, an argument the caller already has, such as
the disk list from installer.core.disks.list_disks()) - nothing here
touches a subprocess, the filesystem, or a widget, which is also why
this module must never import gi: doing so would make it untestable in
this display-less environment and would drag a GTK dependency into the
text-only fallback path, which has no use for one.

installer.gui.app builds one PageState, has its widgets write into its
fields (plain assignment only - no branching), and reads the methods
below back to decide what the "next" button and the summary page show.

Note on a deferred idea from the text-interface review: installer.core.
disks.list_disks() silently drops mounted and virtual devices, and a
form has room to say so ("N devices hidden"). This module does not add
that hint. Computing an accurate count would need the number of raw
lsblk rows before list_disks()'s own filtering, which list_disks() does
not expose - list_disks() and mounted_disks() both return only the
devices they decided are relevant, not what they discarded. Recovering
that count would mean re-parsing lsblk output here, which is exactly
the duplication the reuse-don't-reimplement instruction warns against:
a second copy of the TYPE/virtual-device filtering that could drift
from installer.core.disks's own. Surfacing the count would require
extending installer.core.disks's public API instead (e.g. having
list_disks() also return what it excluded and why) - a change to an
already-reviewed module, out of scope for a GUI-only task.
"""
from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from installer.core.crypt import (
    effective_layout, keyboard_note, loss_warning, passphrase_error,
    plaintext_warnings, unlock_note,
)
from installer.core.disks import Disk, Partition, human_size
from installer.core.i18n import _, activate, ngettext
from installer.core.layout import (
    ESP_FILESYSTEM, ESP_FLAGS, ESP_MOUNTPOINT, MOUNTPOINTS, PlannedPartition,
    SWAP_FILESYSTEM, first_fit, free_mib, human_mib, largest_free_mib,
    layout_errors, parse_size_mib, suggested_layout,
)
from installer.core.model import (
    DiskChoice, InstallConfig, MIN_DISK_MIB, UserAccount, WifiCredentials,
    ZeposOptions,
)
from installer.core import timezones
from installer.core.runner import InstallationRefused
from installer.core.validate import HOSTNAME_PATTERN, MIN_PASSWORD_LENGTH, validate
from installer.core.wifi import (
    Connection, Network, WifiBackend, associate as _iwd_associate,
)

Installer = Callable[..., int]
Associator = Callable[[WifiBackend, str, str], Connection]

# WARUM DIE VERSCHLUESSELUNG ZWISCHEN EINTEILUNG UND BENUTZER STEHT
#     Hinter der Einteilung, weil sie sie braucht: welche Partitionen
#     eine Passphrase bekommen und welche im Klartext bleiben, ist eine
#     Aussage ueber die Einteilung, und die Seite zaehlt beide Listen
#     auf. Auf einer Seite VOR der Partitionierung waere sie eine Frage
#     ueber etwas, das es noch nicht gibt.
#
#     Vor dem Benutzer, weil danach nichts mehr ueber die Platte
#     entschieden wird - dieselbe Begruendung, mit der die
#     Partitionierung direkt hinter der Plattenwahl steht.
PAGE_ORDER = [
    "sprache", "netzwerk", "datentraeger", "partitionierung",
    "verschluesselung", "benutzer", "zeit", "zepos", "zusammenfassung",
]

# Die Einhaengepunkte, die die Seite zur Wahl stellt, in der Reihenfolge
# des Auswahlfelds. Die letzten beiden sind keine Einhaengepunkte,
# sondern die zwei Partitionen, die ueber etwas anderes definiert sind:
# die EFI-Systempartition ueber ihre Flaggen, die Auslagerung ueber ihr
# Dateisystem. Sie stehen trotzdem hier, weil der Nutzer EINE Frage
# beantwortet - "was soll das werden" - und nicht drei, die einander
# widersprechen koennen.
SWAP_CHOICE = "swap"
MOUNTPOINT_CHOICES: tuple[str, ...] = (*MOUNTPOINTS, ESP_MOUNTPOINT, SWAP_CHOICE)

# Die Dateisysteme, die zur Wahl stehen, wenn die Wahl ueberhaupt beim
# Nutzer liegt. fat32 fehlt mit Absicht: es ist die Antwort fuer die ESP
# und fuer nichts sonst auf dieser Platte, und es als Wurzel zu waehlen
# ist ein System, das nicht startet. linux-swap fehlt aus demselben
# Grund - dafuer gibt es den Eintrag im Auswahlfeld darueber.
FILESYSTEM_CHOICES: tuple[str, ...] = ("ext4", "btrfs", "xfs")

# (keymap, locale) per language. Identical values and identical
# rationale to installer.tui.app.LANGUAGES.
#
# DIE ZEITZONE STAND HIER BIS ZUM 02.09.2026 ALS DRITTER WERT, und sie
# ist ersatzlos herausgefallen. Sie war "de" -> Europe/Berlin und "en"
# -> UTC, also eine Ableitung von einem ORT aus einer SPRACHE - und die
# gibt es nicht. Englisch wird auf sechs Kontinenten gesprochen; wer auf
# Englisch installierte, bekam eine Uhr auf UTC - gleichgueltig, wo er
# sass - und, bis zu derselben Aufgabe, keinen Weg zurueck. Dieselbe Sorte
# Annahme, die src/clocks.py in der Gegenrichtung zurueckweist ("von
# einer Zeitzone gibt es keinen verlaesslichen Weg zurueck zu einem
# Land").
#
# An ihre Stelle tritt eine TATSACHE: timezones.running() liest, in
# welcher Zone dieses Medium gerade laeuft. Eine Tastaturbelegung und
# eine Sprachumgebung bleiben, weil beide wirklich an der Sprache
# haengen - eine deutsche Tastatur ist eine Aussage ueber die Sprache
# und nicht ueber den Ort.
LANGUAGE_DEFAULTS: dict[str, tuple[str, str]] = {
    "de": ("de-latin1", "de_DE"),
    "en": ("us", "en_US"),
}


@dataclass
class PageState:
    """Everything the GTK4 pages collect, independent of any widget."""

    language: str = "de"
    hostname: str = "zepos"
    device: str = ""
    device_size_bytes: int = 0
    wipe: bool = True
    # Was auf der gewaehlten Platte HEUTE liegt, so wie lsblk es gemeldet
    # hat. Nur zum Anzeigen: es ist die Liste, die die Seite und die
    # letzte Rueckfrage aufzaehlen, damit "die Platte wird geloescht" ein
    # Satz mit Inhalt ist und nicht eine Floskel.
    device_partitions: tuple[Partition, ...] = ()
    # Die geplante neue Einteilung. Wird von select_disk() auf den
    # Vorschlag gesetzt, sobald feststeht, wie gross die Platte ist.
    layout: list[PlannedPartition] = field(default_factory=list)
    # Die drei Felder des Formulars "Partition hinzufuegen". Sie stehen
    # hier und nicht in app.py, weil sonst die Pruefung ihrer Eingabe in
    # einem GTK-Callback saesse - dort, wo kein Test dieser Suite
    # hinkommt.
    new_mountpoint: str = MOUNTPOINT_CHOICES[0]
    new_filesystem: str = FILESYSTEM_CHOICES[0]
    new_size: str = ""
    # Die Verschluesselung. AN, und das ist die Entscheidung dieser Seite.
    #
    # WARUM DIE VORGABE AN IST
    #     Weil der Nutzer am 12.08.2026 "von anfang an" und "immer"
    #     gesagt hat, und weil eine Vorgabe genau das ist, was fast
    #     niemand aendert - die Vorgabe IST also die Antwort fuer die
    #     meisten Installationen, und die soll die sichere sein.
    #
    # WARUM NIEMAND VERSEHENTLICH DURCHKLICKT
    #     Weil ein gesetzter Haken ohne Passphrase die Seite UNGUELTIG
    #     macht (page_error() unten), und ein ungueltiger Zustand macht
    #     "Weiter" unempfindlich. Wer stumpf durchdrueckt, kommt hier
    #     also nicht vorbei, sondern muss entweder eine Passphrase
    #     eingeben oder den Haken bewusst wegnehmen. Genau das ist der
    #     Unterschied zwischen einer Vorgabe und einer Falle: sie
    #     erzwingt eine Entscheidung, statt eine zu unterstellen.
    #
    # Der Gegensatz zu installer.core.model.DiskChoice.encrypt, das False
    # ist, ist Absicht und dort begruendet: hier aeussert sich ein Mensch,
    # dort eine Datei, in der von Verschluesselung nichts steht.
    encrypt: bool = True
    encryption_passphrase: str = ""
    encryption_passphrase_confirm: str = ""
    # Die Warnung ueber den fehlenden AES-Befehlssatz, oder "" auf einer
    # Maschine, die ihn hat.
    #
    # ALS FERTIGER SATZ UND NICHT ALS PRUEFUNG, genau wie firmware_error
    # weiter unten und aus demselben Grund: die Antwort steht in
    # /proc/cpuinfo, und dieses Modul fasst kein Dateisystem an (siehe
    # den Kopf). app.py fragt installer.core.crypt.accelerator_note()
    # einmal beim Bauen des Fensters und legt das Ergebnis hier ab.
    accelerator_warning: str = ""
    username: str = ""
    password: str = ""
    password_confirm: str = ""
    root_password: str = ""
    root_password_confirm: str = ""
    wifi_ssid: str = ""
    wifi_passphrase: str = ""
    wifi_networks: list[Network] = field(default_factory=list)
    # The (ssid, passphrase) pair the live session is currently joined
    # to, or None. Kept as the pair rather than a flag so that editing
    # either field invalidates the association by itself - a stale True
    # would let a corrected passphrase skip the reconnect it exists for.
    wifi_connected_to: tuple[str, str] | None = None
    # True while a wireless worker thread is running. Kept here rather
    # than read off the "next" button's own sensitivity in app.py: every
    # keystroke in the passphrase field recomputes that sensitivity from
    # is_page_valid() below, so the button was re-enabled mid-connect and
    # a second click started a second worker. Each worker's completion
    # advanced the form by one page, so two of them skipped the disk page
    # - the one page that shows which disk is about to be erased.
    wireless_busy: bool = False
    timezone: str = ""
    enable_plugins: bool = True
    weather_location: str = ""
    # Die drei Haken der ZepOS-Seite. Aus, bis jemand sie setzt - was
    # ZepOS von sich aus ausliefert, steht in packaging/zepos-apps und
    # nicht in einer Voreinstellung dieses Formulars.
    install_office: bool = False
    install_devel: bool = False
    # The refusal from installer.core.firmware.firmware_problem(), or ""
    # on a machine ZepOS can actually install onto. app.py reads it once
    # at window construction and assigns it here; every page then refuses
    # to be left (see page_error() and is_page_valid() below), so the user
    # learns it on the first page instead of after confirming an erase.
    # Kept as the finished string rather than a check of its own: this
    # module touches no filesystem, and /sys/firmware/efi is one.
    firmware_error: str = ""

    # --- language ----------------------------------------------------------

    def set_language(self, language: str) -> None:
        """Set the language and activate its catalogue immediately.

        Every message computed afterwards - a field's error text, the
        page titles app.py rebuilds, not only the eventual InstallConfig
        - must already be in the chosen language, exactly like
        installer.tui.app.collect() calling activate() as its very first
        action. to_config() also activates defensively (see its own
        docstring) so a caller that skipped this method still gets a
        correctly localised InstallConfig, but relying on that alone
        would leave every per-field error message shown before the user
        reaches a page that calls to_config() in the wrong language.
        """
        self.language = language
        activate(language)

    # --- disk selection --------------------------------------------------

    def select_disk(self, disk: Disk) -> None:
        """Set device and device_size_bytes together.

        The two must never be settable independently: a DiskChoice with
        a device but no size_bytes fails validate() and
        to_archinstall_config() outright (see installer.core.disks's own
        module docstring) - the exact defect the text interface review
        flagged twice. Going through this method rather than two plain
        field assignments in app.py makes that pairing structural rather
        than a discipline app.py's widget callbacks would have to
        remember.

        Die Einteilung gehoert zu derselben Klammer und wird deshalb hier
        mitgesetzt. Sie ist in MiB ab dem Anfang GENAU DIESER Platte
        gerechnet: eine Wurzel, die auf einer 40-GiB-Platte bis zum Ende
        reicht, ragt auf einer 20-GiB-Platte darueber hinaus, und
        archinstall lehnt dann die ganze Konfiguration ab
        ("Partition overlaps backup GPT header"). Ein Wechsel der Platte
        ist also ein Wechsel der Einteilung.

        Die Zuweisung geschieht nur, wenn sich das Geraet wirklich
        aendert. _build_datentraeger() ruft diese Methode beim Bauen der
        Seite fuer die erste Platte auf, und die Seite wird gebaut, bevor
        der Nutzer irgendetwas geplant hat - aber sie wird auch von
        _on_disk_toggled() gerufen, und ein Klick auf die schon gewaehlte
        Zeile duerfte eine von Hand gemachte Einteilung nicht wegwerfen.
        """
        if disk.device == self.device and disk.size_bytes == self.device_size_bytes:
            self.device_partitions = tuple(disk.partitions)
            return
        self.device = disk.device
        self.device_size_bytes = disk.size_bytes
        self.device_partitions = tuple(disk.partitions)
        self.reset_layout()

    @staticmethod
    def usable_disks(devices: Sequence[Disk]) -> list[Disk]:
        """Only disks at or above MIN_DISK_MIB should ever be offered.

        A too-small disk is a fact about the hardware, not a typo -
        re-prompting cannot fix it, so it must not be selectable in the
        first place. Same rule and same boundary (>=, not >) as
        installer.tui.app.collect() applies to the disks it lists.
        """
        return [
            disk for disk in devices
            if disk.size_bytes // (1024 * 1024) >= MIN_DISK_MIB
        ]

    def disk_error(self) -> str:
        if not self.device:
            return _("No disk was selected.")
        if self.device_size_bytes // (1024 * 1024) < MIN_DISK_MIB:
            return (
                _("The selected disk is too small. At least {minimum} MiB are required.")
                .format(minimum=MIN_DISK_MIB)
            )
        return ""

    # --- die Einteilung ----------------------------------------------------

    def reset_layout(self) -> None:
        """Den Vorschlag einsetzen: ESP und Wurzel, sonst nichts.

        Warum genau die zwei und keine Auslagerung und kein eigenes
        /home, steht in installer.core.layout.suggested_layout().
        """
        self.layout = suggested_layout(
            self.device_size_bytes, filesystem="ext4")

    def clear_layout(self) -> None:
        """Die Einteilung leeren - die Platte "bereinigen".

        OHNE RUECKFRAGE, und das ist die Entscheidung.
        Hier wird nichts geloescht. Es wird ein Plan geleert, und der
        Plan ist bis zur letzten Rueckfrage nichts als eine Liste im
        Arbeitsspeicher; der Vorschlag steht einen Knopf weiter wieder
        da. Eine Rueckfrage an dieser Stelle waere die zweite auf dem
        Weg, und die eine, die zaehlt - die vor dem Loeschen, mit der
        Aufzaehlung dessen, was verlorengeht - verliert genau dadurch
        ihr Gewicht: wer schon zweimal "ja" gesagt hat, liest das dritte
        Mal nicht mehr.
        """
        self.layout = []

    def filesystem_is_chosen(self) -> bool:
        """Ob das Dateisystem im Formular ueberhaupt zur Wahl steht.

        Bei der EFI-Systempartition und bei der Auslagerung nicht: dort
        ist es die Folge der Entscheidung darueber (fat32, weil die
        Firmware nur FAT liest; linux-swap, weil archinstall daran die
        Auslagerung erkennt). app.py schaltet die Zeile daraufhin
        unbedienbar, statt eine Eingabe entgegenzunehmen und still zu
        verwerfen.
        """
        return self.new_mountpoint not in (ESP_MOUNTPOINT, SWAP_CHOICE)

    def planned_filesystem(self) -> str:
        if self.new_mountpoint == ESP_MOUNTPOINT:
            return ESP_FILESYSTEM
        if self.new_mountpoint == SWAP_CHOICE:
            return SWAP_FILESYSTEM
        return self.new_filesystem

    def size_error(self) -> str:
        """Was an der eingetippten Groesse nicht stimmt, oder "".

        Getrennt von add_partition(), weil die Seite es bei jedem
        Tastendruck anzeigt: eine Groesse, die nicht passt, soll beim
        Tippen zu sehen sein und nicht erst, wenn der Knopf nichts tut.
        """
        _mib, problem = parse_size_mib(
            self.new_size,
            available_mib=largest_free_mib(self.layout, self.device_size_bytes))
        return problem

    def add_partition(self) -> str:
        """Die Partition aus dem Formular in die Einteilung aufnehmen.

        Gibt die Begruendung zurueck, wenn das nicht geht, sonst "". Der
        Anfang wird gesucht und nicht eingegeben: er ist die Folge
        dessen, was schon geplant ist, und eine von Hand eingetippte
        Sektorzahl waere die einzige Stelle auf dieser Seite, an der ein
        Nutzer eine Ueberlappung ueberhaupt herstellen koennte.
        """
        available = largest_free_mib(self.layout, self.device_size_bytes)
        size_mib, problem = parse_size_mib(self.new_size, available_mib=available)
        if problem:
            return problem
        start = first_fit(self.layout, self.device_size_bytes, size_mib)
        if start is None:
            # Kann parse_size_mib() nicht schon abgefangen haben: dort ist
            # die Grenze die groesste Luecke, und hier wird dieselbe Zahl
            # noch einmal gesucht. Bleibt trotzdem stehen - first_fit()
            # gibt None zurueck, und ein None in start_mib waere eine
            # Partition, die bei 0 anfaengt.
            return _("{wanted} does not fit; at most {available} are free.").format(
                wanted=human_mib(size_mib), available=human_mib(available))

        mountpoint = self.new_mountpoint
        flags: tuple[str, ...] = ()
        if mountpoint == ESP_MOUNTPOINT:
            flags = ESP_FLAGS
        elif mountpoint == SWAP_CHOICE:
            mountpoint = ""

        self.layout = sorted(
            [*self.layout, PlannedPartition(
                start_mib=start,
                size_mib=size_mib,
                filesystem=self.planned_filesystem(),
                mountpoint=mountpoint,
                flags=flags,
            )],
            key=lambda partition: partition.start_mib)
        self.new_size = ""
        return ""

    def remove_partition(self, planned: PlannedPartition) -> None:
        """Eine geplante Partition wieder herausnehmen.

        Nach dem Wert und nicht nach dem Index: app.py haengt den Knopf
        an die Zeile, und die Zeilen werden bei jeder Aenderung neu
        gebaut. Ein Index, der beim Bauen richtig war, zeigt nach dem
        naechsten Umbau auf die Nachbarin - und die zu loeschen ist der
        Fehler, den man erst auf der Zusammenfassung bemerkt.
        """
        self.layout = [p for p in self.layout if p != planned]

    def layout_error(self) -> str:
        """Der erste Grund, aus dem diese Einteilung nicht installiert
        werden kann, oder "".

        Der erste und nicht alle: die Seite hat eine Zeile dafuer, und
        layout_errors() sortiert schon danach, was am weitesten vorne im
        Weg steht. Die vollstaendige Liste steht auf der
        Zusammenfassung.
        """
        problems = layout_errors(self.layout, self.device_size_bytes)
        return problems[0] if problems else ""

    def existing_summary(self) -> str:
        """Ein Satz ueber das, was auf der Platte liegt - und darueber,
        dass es weg sein wird.

        Die Zahl steht vorn, weil sie die Frage beantwortet, die jemand
        an dieser Stelle hat: ist da etwas drauf.
        """
        count = len(self.device_partitions)
        if not count:
            return _("There is no partition on this disk.")
        return ngettext(
            "{count} partition will be deleted:",
            "{count} partitions will be deleted:",
            count).format(count=count)

    def layout_summary(self) -> str:
        """Vergeben und frei, in einer Zeile unter der neuen Einteilung.

        Das ist die "Belegung", die auf dieser Seite ueberhaupt zu haben
        ist - warum nicht der Fuellstand der Dateisysteme, steht im
        Kopf von installer/core/layout.py.
        """
        free = free_mib(self.layout, self.device_size_bytes)
        return _("{free} of {total} still free.").format(
            free=human_mib(free), total=human_size(self.device_size_bytes))

    # --- die Verschluesselung ----------------------------------------------

    def encryption_layout(self) -> list[PlannedPartition]:
        """Die Einteilung, ueber die diese Seite Aussagen macht.

        Ueber effective_layout() und nicht ueber self.layout, damit die
        Seite dasselbe aufzaehlt, was installer.core.translate spaeter
        wirklich anlegt. Die beiden weichen genau dann voneinander ab,
        wenn niemand eine Einteilung geplant hat - und eine Seite, die
        dann "nichts wird verschluesselt" sagt, waere falsch.
        """
        return effective_layout(self.layout, self.device_size_bytes)

    def encryption_error(self) -> str:
        """Was die Verschluesselung noch braucht, oder "".

        Leer, sobald der Haken weg ist: eine Installation ohne
        Verschluesselung ist eine gueltige Installation, und die Felder
        darunter entscheiden dann nichts mehr.
        """
        if not self.encrypt:
            return ""
        return passphrase_error(
            self.encryption_passphrase, self.encryption_passphrase_confirm)

    def encryption_notes(self) -> list[str]:
        """Alles, was auf dieser Seite stehen muss, bevor jemand
        weiterklickt - in der Reihenfolge, in der es zaehlt.

        Die Warnung zuerst, weil sie die einzige ist, deren Missachtung
        alle Daten kostet. Dann, was es im Betrieb kostet: die zehn
        Sekunden beim Einschalten, die Tastaturbelegung an der Abfrage,
        und - nur wenn es zutrifft - der fehlende AES-Befehlssatz.
        Zuletzt, was trotz Verschluesselung offen liegt.

        Eine Liste und kein fertiger Absatz: app.py macht daraus eine
        Zeile je Eintrag, und was auf einer eigenen Zeile steht, wird
        eher gelesen als was in einem Block untergeht.
        """
        notes = [loss_warning(), unlock_note(), keyboard_note()]
        if self.accelerator_warning:
            notes.append(self.accelerator_warning)
        notes.extend(plaintext_warnings(self.encryption_layout()))
        return notes

    # --- wireless ----------------------------------------------------------

    def should_skip(self, page: str) -> bool:
        """Whether a page should be skipped during navigation.

        Only the wireless step can be skipped, and only once
        discover_networks() found nothing to offer - the exact condition
        installer.tui.app.collect() itself checks (`if networks:`)
        before prompting at all, regardless of whether the reason was no
        wireless hardware, an empty scan, or a broken iwctl. Installing
        over Ethernet is normal, not an error.
        """
        return page == "netzwerk" and not self.wifi_networks

    def wifi_passphrase_error(self) -> str:
        if self.wifi_ssid and not self.wifi_passphrase:
            return _("No password was given for the wireless network.")
        return ""

    def begin_wireless_step(self) -> bool:
        """Claim the right to start ONE wireless worker, or refuse.

        Called on the main thread before the worker is spawned, which is
        where the race actually is: the check and the claim happen in one
        call that nothing can interleave with, unlike "is the button
        sensitive" (recomputed on every keystroke) or "am I on the network
        page" (still true while the connect runs).

        Returns False when a worker is already in flight; app.py then does
        nothing at all, so a second click cannot start a second connect
        whose completion would advance the form a second time.
        """
        if self.wireless_busy:
            return False
        self.wireless_busy = True
        return True

    def end_wireless_step(self) -> None:
        """Release the claim. Must run for EVERY started worker, including
        one that ended in a failure - wireless_step() therefore never
        raises, and app.py's completion callback runs on the main thread
        whatever the outcome was. A claim never released leaves the "next"
        button dead for the rest of the session."""
        self.wireless_busy = False

    def needs_association(self) -> bool:
        """Whether the live session still has to join the chosen network.

        False when no network was chosen at all (installing over ethernet
        is normal) and false while the session is already joined to
        exactly this ssid/passphrase pair, so paging back and forth does
        not re-run a slow iwctl connect for nothing.
        """
        if not self.wifi_ssid:
            return False
        return self.wifi_connected_to != (self.wifi_ssid, self.wifi_passphrase)

    # --- fields validated as they are entered -----------------------------

    def hostname_error(self) -> str:
        if HOSTNAME_PATTERN.match(self.hostname):
            return ""
        # Same single literal validate.py and installer.tui.app's
        # _ask_hostname() use for the identical rule - kept as one
        # msgid so the three descriptions of a valid hostname can never
        # drift apart.
        return _(
            "The hostname may contain only letters, digits and hyphens, and may not start or end with a hyphen."
        )

    def username_error(self) -> str:
        if self.username:
            return ""
        return _("This entry may not be empty.")

    def timezone_error(self) -> str:
        """Ein Zonenname, den die Datenbank nicht kennt.

        DIESE PRUEFUNG IST DER EIGENTLICHE FUND DIESER SEITE. Bis zum
        02.09.2026 war die Zeitzone ein freies Textfeld ohne jede
        Pruefung, und `date` nimmt jeden Namen an: "Europe/Berln" wird
        installiert, danach druckt date(1) die UTC-Zeit mit "Berln" als
        Kuerzel, Rueckgabewert 0, leere Fehlerausgabe. Ein Tippfehler
        wurde so zu einer Uhr, die still falsch geht - und der Mensch
        merkt es fruehestens, wenn eine Verabredung um zwei Stunden
        verrutscht.

        Die Seite bietet die Zonen seither zur AUSWAHL an; diese Zeilen
        sind das Netz darunter. Sie bleiben auch dann noetig, wenn das
        Feld eine Auswahl ist: die Seite laesst sich mit einer
        vorgeladenen Konfiguration fuellen, und ein leeres Feld ist
        keine Zone, sondern die laufende (siehe to_config()).
        """
        if not self.timezone or timezones.known(self.timezone):
            return ""
        return _(
            "This machine's timezone database does not have \"{zone}\"."
        ).format(zone=self.timezone)

    @staticmethod
    def _password_pair_error(value: str, confirm: str) -> str:
        """Shared by password_error() and root_password_error(), which
        differ only in which pair of fields they read - the length rule,
        the mismatch rule and both messages (reused from
        installer.tui.app, which already carries these exact msgids) are
        identical either way."""
        if len(value) < MIN_PASSWORD_LENGTH:
            return (
                _("The password is too short. At least {minimum} characters are required.")
                .format(minimum=MIN_PASSWORD_LENGTH)
            )
        if value != confirm:
            return _("The passwords do not match.")
        return ""

    def password_error(self) -> str:
        return self._password_pair_error(self.password, self.password_confirm)

    def root_password_error(self) -> str:
        return self._password_pair_error(self.root_password, self.root_password_confirm)

    def page_error(self, page: str) -> str:
        """The single most relevant error message for one page's own
        fields, or "" once they are all fine - what a form shows next
        to the fields themselves instead of only at the final summary
        (lesson 3 from the text interface review, applied to a form
        rather than a linear sequence of prompts). Used by app.py to
        drive a per-page error label, and by is_page_valid() below to
        gate the "next" button - kept as one dispatch rather than two,
        so a page's error text and its validity can never disagree.
        """
        if self.firmware_error:
            # Shown on whichever page the user is looking at, which is
            # the first one: this machine cannot boot what ZepOS
            # installs, so no page's fields matter any more.
            return self.firmware_error
        if page == "netzwerk":
            return self.wifi_passphrase_error()
        if page == "datentraeger":
            return self.disk_error()
        if page == "partitionierung":
            # NUR die Einteilung, nicht die halb getippte Groesse im
            # Formular. Die beiden gehoeren an verschiedene Stellen:
            # size_error() steht neben der Eingabezeile, zu der sie
            # gehoert, und haelt den Weiter-Knopf nicht auf - eine leere
            # Eingabezeile ist kein Grund, eine fertige Einteilung nicht
            # zu installieren. Diese hier ist der Grund und gehoert
            # deshalb an den Knopf.
            return self.layout_error()
        if page == "verschluesselung":
            return self.encryption_error()
        if page == "benutzer":
            return (
                self.hostname_error() or self.username_error()
                or self.password_error() or self.root_password_error()
            )
        if page == "zeit":
            return self.timezone_error()
        # "sprache", "zepos" and "zusammenfassung" have no single
        # field-level error of their own: a language is always one of the
        # two offered, the ZepOS options carry usable defaults, and the
        # summary page's own validity is the whole-config findings() list
        # below, not one field's message.
        return ""

    def is_page_valid(self, page: str) -> bool:
        """Whether a page's own fields are filled in correctly, so the
        "next" button can be gated per page instead of only at the
        final summary."""
        if self.firmware_error:
            return False
        if page == "netzwerk" and self.wireless_busy:
            # Deliberately NOT mirrored in page_error(): a connection in
            # progress is a transient state, not a mistake to correct, so
            # the button is dead while it runs and nothing appears in red.
            # This is the one place the two answers differ, and the reason
            # is that the button must also be dead in the fraction of a
            # second between the click and the toast.
            return False
        if page == "zusammenfassung":
            return not self.findings()
        return not self.page_error(page)

    # --- assembly ------------------------------------------------------

    def to_config(self) -> InstallConfig:
        """Build the InstallConfig this state currently describes.

        Activates the chosen language immediately, not only once the
        config is handed to the installer: every page shown after the
        language step must already speak the chosen language, exactly
        like installer.tui.app.collect() calling activate() as its very
        first action. Calling this repeatedly (e.g. once per keystroke,
        via findings()) is intentional and cheap - activate() only
        reselects an already-loaded catalogue.
        """
        activate(self.language)
        keymap, locale = LANGUAGE_DEFAULTS[self.language]
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
            # Die Zone, in der dieses Medium laeuft, wenn die Seite
            # nichts gesetzt hat - und nicht eine aus der Sprache
            # abgeleitete. Siehe LANGUAGE_DEFAULTS oben.
            timezone=self.timezone or timezones.running(),
            hostname=self.hostname,
            disk=DiskChoice(
                device=self.device, wipe=self.wipe,
                size_bytes=self.device_size_bytes,
                # Eine Kopie, keine Referenz: die InstallConfig geht an
                # einen Arbeitsthread, der sie waehrend der Installation
                # liest, und die Seite bleibt so lange bedienbar, wie sie
                # sichtbar ist.
                layout=list(self.layout),
                encrypt=self.encrypt,
                # Die Passphrase nur, solange der Haken steht. Eine
                # eingegebene und dann abgewaehlte Passphrase darf nicht
                # mitreisen: sie stuende sonst im Klartext in einer
                # InstallConfig, die niemand mehr benutzt, und ein
                # spaeterer Leser dieses Feldes koennte daraus schliessen,
                # verschluesselt worden sei doch.
                passphrase=self.encryption_passphrase if self.encrypt else "",
            ),
            users=users,
            root_password=self.root_password,
            wifi=wifi,
            zepos=ZeposOptions(
                enable_plugins=self.enable_plugins,
                weather_location=self.weather_location,
                install_office=self.install_office,
                install_devel=self.install_devel,
            ),
        )

    def findings(self) -> list[str]:
        return validate(self.to_config())


def wireless_step(
    state: PageState, backend: WifiBackend, *, associate: Associator | None = None
) -> Connection:
    """Join the chosen network before leaving the wireless page.

    The "verbinden" half of spec §8.2 step 2, which no surface used to
    perform: the passphrase was collected and only ever written into the
    TARGET system's profile, leaving the live session offline and every
    installation on wireless-only hardware silently on the offline path.

    Returns a Connection whose `connected` app.py uses to decide whether
    the page may be left, and whose `message` it shows either way. The
    real associate() is resolved here rather than bound as a default
    argument: it opens a socket to check the connection.

    Never raises, for the same reason run_installation() below does not:
    this runs on a worker thread, where an escaping exception reaches
    sys.excepthook and is shown to nobody. Here it would also skip the
    completion callback that releases PageState.begin_wireless_step()'s
    claim, leaving the "next" button dead for the rest of the session.
    A raw str(exc) is what associate() itself already puts into a failed
    Connection, so nothing new is invented for a case that should not
    happen at all.
    """
    associate = associate or _iwd_associate
    if not state.needs_association():
        return Connection(True, "")
    try:
        result = associate(backend, state.wifi_ssid, state.wifi_passphrase)
    except Exception as exc:
        state.wifi_connected_to = None
        return Connection(False, str(exc))
    state.wifi_connected_to = (
        (state.wifi_ssid, state.wifi_passphrase) if result.connected else None
    )
    return result


# --- confirmation and installation ------------------------------------


def confirmation_body(
    device: str,
    *,
    existing: Sequence[Partition] = (),
    layout: Sequence[PlannedPartition] = (),
    encrypt: bool = False,
) -> str:
    """The body of the point-of-no-return dialog.

    Names the device. "This erases the entire disk" without saying which
    one is exactly the sentence a user confirms while thinking of a
    different disk than the installer selected - and the confirmation is
    the last moment at which that can still be noticed.

    UND NENNT, WAS DABEI VERLORENGEHT.
        Der Geraetename allein reicht dafuer nicht. "/dev/nvme0n1" ist
        auf einer Maschine mit zwei Platten kein Wort, an dem jemand die
        falsche erkennt; "ntfs 'Windows' 465,8 GiB" ist eines. Deshalb
        zaehlt die Rueckfrage jede vorhandene Partition mit Dateisystem,
        Bezeichnung und Groesse auf - dieselben Angaben, die auf der
        Partitionierungsseite standen, damit die letzte Frage nicht
        weniger weiss als die Seite davor.

        Danach, kuerzer, was entsteht. Eine Rueckfrage, die nur das
        Schlimme nennt, ist eine Warnung; eine, die beides nennt, ist
        eine Entscheidung.

    UND, WENN VERSCHLUESSELT WIRD, DIE WARNUNG EIN ZWEITES MAL.
        Sie stand schon auf der Verschluesselungsseite, und sie steht hier
        noch einmal, WOERTLICH gleich. Das ist kein Versehen und keine
        Doppelung aus Verlegenheit: dies ist der letzte Augenblick, in
        dem "ich habe die Passphrase nirgends notiert" noch ein
        korrigierbarer Zustand ist. Danach ist es der Zustand, in dem die
        Daten verloren sind.

        Ein zweiter, anders formulierter Satz waere hier schlechter als
        derselbe: wer ihn wiedererkennt, weiss, dass er ihn schon einmal
        gelesen hat - und zwei Formulierungen einer Warnung sind zwei,
        die auseinanderlaufen koennen.

    Die Listen und der Haken sind Schluesselwortargumente mit einer
    Vorgabe, damit ein Aufrufer, der nur den Geraetenamen hat, denselben
    Satz bekommt wie vorher.
    """
    lines = [_("This erases the entire disk {device}.").format(device=device)]

    if existing:
        lines.append("")
        lines.append(ngettext(
            "{count} partition will be deleted:",
            "{count} partitions will be deleted:",
            len(existing)).format(count=len(existing)))
        lines.extend(f"  \N{BULLET} {_describe_existing(part)}"
                     for part in existing)

    if layout:
        lines.append("")
        lines.append(_("The following will be created:"))
        lines.extend(f"  \N{BULLET} {planned.describe()} ({planned.filesystem})"
                     for planned in layout)

    if encrypt:
        lines.append("")
        lines.append(_("The disk will be encrypted."))
        lines.append(loss_warning())

    return "\n".join(lines)


def _describe_existing(partition: Partition) -> str:
    """Eine vorhandene Partition in einer Zeile: Geraet, Dateisystem,
    Bezeichnung, Groesse.

    Dieselbe Reihenfolge und dieselben Bestandteile wie in
    installer.core.disks.describe_contents(), das die Kurzfassung fuer
    die Plattenliste baut - eine Partition soll in der Rueckfrage
    wiedererkennbar sein als die, die eine Seite vorher aufgefuehrt war.
    """
    parts = [partition.device, partition.fstype or _("unknown")]
    if partition.label:
        parts.append(f"\N{LEFT DOUBLE QUOTATION MARK}{partition.label}"
                     f"\N{RIGHT DOUBLE QUOTATION MARK}")
    parts.append(human_size(partition.size_bytes))
    return " ".join(parts)


@dataclass(frozen=True)
class InstallationOutcome:
    """How one installation run ended, in a form app.py can only read
    back: a flag, a dialog heading, a dialog body. Deciding what to say
    about a failure is exactly the kind of logic that must not sit inside
    a GTK callback, where no test in this display-less suite could reach
    it."""

    succeeded: bool
    heading: str
    message: str


def default_log_path() -> Path:
    """Where archinstall's output is collected for the graphical surface.

    A file rather than this process's own stdout: the graphical installer
    is started from a session whose terminal the user never sees, so
    output written there is output written to nobody.

    In a directory of its own rather than at a fixed name in the shared
    temporary directory. The installer runs as root and
    installer.core.runner opens this path with mode "w"; a predictable
    name in a world-writable sticky directory is a name anyone can claim
    first with a symlink, and root then truncates whatever it points at.
    tempfile.mkdtemp() creates a directory mode 0700 under a name nobody
    can guess, which closes the guess and the traversal at once.

    A fresh directory per call, so this must be called ONCE per run and
    the result kept - which is what app.py does. The directory is left
    behind on purpose: the log is the only record of what archinstall
    said, and it is wanted after a failed installation, not before.
    """
    return Path(tempfile.mkdtemp(prefix="zepos-install-")) / "install.log"


def _with_warnings(message: str, warnings: Sequence[str]) -> str:
    return "\n".join([message, *warnings])


def run_installation(
    cfg: InstallConfig, install: Installer, *, log_path: Path | None = None
) -> InstallationOutcome:
    """Run one installation and turn every possible ending into text.

    Never raises, and never touches a widget: this runs on a worker
    thread, because installer.core.runner.install() blocks for the entire
    archinstall run - minutes - and doing that on the GTK main thread
    freezes the window mid-erase, which the compositor reports as "not
    responding" and a user reasonably answers by killing it or cutting
    the power.

    An exception escaping a worker thread would reach sys.excepthook and
    be shown to nobody, leaving the last toast on screen still claiming
    the installation had just started. Hence: every ending, including a
    raised one, comes back as an InstallationOutcome.

    Warnings collected during the run are appended to the message instead
    of turning it into a failure - installer.core.runner.install() only
    reports warnings once archinstall has already succeeded, and telling
    the user their installation failed at that point would invite a
    second erase of an installed machine.
    """
    warnings: list[str] = []
    try:
        code = install(cfg, log_path=log_path, on_warning=warnings.append)
    except InstallationRefused as exc:
        # The one failure that can also say what happened to the disk:
        # this type is raised only where archinstall has provably not
        # started (see its own docstring). Every other failure below says
        # nothing about the disk, because past those points archinstall
        # may already have been partitioning.
        return InstallationOutcome(
            False,
            _("Installation failed"),
            "\n".join([
                _("The installation could not be carried out: {reason}")
                .format(reason=exc),
                _("Nothing on the disk {device} was changed.")
                .format(device=cfg.disk.device),
            ]),
        )
    except Exception as exc:
        return InstallationOutcome(
            False,
            _("Installation failed"),
            _("The installation could not be carried out: {reason}").format(reason=exc),
        )
    if code == 0:
        return InstallationOutcome(
            True,
            _("Installation completed"),
            _with_warnings(_("Installation completed successfully."), warnings),
        )
    return InstallationOutcome(
        False,
        _("Installation failed"),
        _with_warnings(
            _("Installation failed (exit code {code}).").format(code=code), warnings
        ),
    )


# Everything a terminal would have eaten. CSI is the long family -
# colours, cursor moves, line clears; OSC sets the window title and ends
# in a bell or a string terminator.
_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_OTHER_ESCAPE = re.compile(r"\x1b[@-Z\\-_]")

# "(12/345) installing foo" - pacman's own counter, and the only honest
# number in the whole run. Anchored at the start of the line so that a
# package whose NAME contains something like (2/3) cannot be mistaken
# for it.
_PACMAN_COUNT = re.compile(r"^\((\d+)/(\d+)\)")

# How far each phase has got by the time it is announced. Derived from
# what a run actually prints, in the order it prints it - see
# TerminalLog.progress() for what these are and are not.
_PHASES: tuple[tuple[str, float], ...] = (
    ("Wiping partitions", 0.02),
    ("Creating partitions", 0.05),
    ("Starting installation", 0.08),
    ("Installing packages", 0.10),
    ("Synchronizing package databases", 0.12),
    ("Creating install root", 0.14),
)

# Where the package phase ends. Everything after it - the bootloader,
# the users, the profile, the ZepOS options - is the remaining fifth.
_PACKAGES_END = 0.80


class TerminalLog:
    """What archinstall wrote, rendered the way a terminal would show it.

    THE PROBLEM THIS SOLVES, reported from the medium: "zeigt komische
    Zeichen und alles nicht korrekt eingerueckt". The installation log
    was inserted into a text view exactly as it came off the process,
    and it is not text - it is a stream written FOR a terminal. It
    carries colours, it hides and shows the cursor, it returns to the
    start of a line to redraw a progress bar, and it moves the cursor UP
    to redraw the two lines above. A text view understands none of that,
    so every escape became a box and every redraw became another line.

    This is not a terminal emulator and does not try to be. It
    understands the four things pacman and archinstall actually use:

        \n          the next line
        \r          this line again, from the start
        ESC[<n>F    n lines up, and carry on from there
        ESC[K       forget the rest of this line

    Everything else in the escape family is dropped rather than
    interpreted, which is the right trade for a log: a colour that is
    lost costs nothing, and a cursor movement that is not understood
    would cost the shape of the whole page.
    """

    # How much of the log is kept, and therefore how far back the
    # reader can scroll.
    #
    # It was 4000, then 500 to make the redraw cheap - and 500 threw
    # away output somebody wanted to scroll back to. The redraw is no
    # longer the reason: app.py appends what is new instead of handing
    # over the whole text, so the cost of a tick is the size of the
    # chunk and not the size of the log. 5000 lines is more than an
    # installation writes and costs a few hundred kilobytes.
    def __init__(self, *, max_lines: int = 5000) -> None:
        self._lines: list[str] = [""]
        self._max_lines = max_lines
        self._done = 0
        self._total = 0
        self._floor = 0.0

    def feed(self, chunk: str) -> None:
        """Take the next piece of the stream.

        Chunks arrive at whatever size the process flushed, so a line -
        and an escape sequence - can be split across two of them. The
        line under construction is kept in _lines[-1] between calls,
        which is what makes that safe.
        """
        index = 0
        while index < len(chunk):
            match = _CSI.match(chunk, index) or _OSC.match(chunk, index) \
                or _OTHER_ESCAPE.match(chunk, index)
            if match:
                self._escape(match.group(0))
                index = match.end()
                continue
            character = chunk[index]
            index += 1
            if character == "\n":
                self._newline()
            elif character == "\r":
                self._lines[-1] = ""
            elif character == "\b":
                self._lines[-1] = self._lines[-1][:-1]
            elif character == "\t":
                self._lines[-1] += "    "
            elif character.isprintable() or character == " ":
                self._lines[-1] += character
            # Anything else - a bell, a stray control byte - is dropped.

    def _escape(self, sequence: str) -> None:
        # ESC[<n>F and ESC[<n>A both put the cursor n lines up. What
        # follows overwrites from there, which for pacman means "draw
        # these two progress lines again".
        up = re.fullmatch(r"\x1b\[(\d*)([FA])", sequence)
        if up:
            count = int(up.group(1) or 1)
            for _ in range(count):
                if len(self._lines) > 1:
                    self._lines.pop()
            self._lines[-1] = ""
            return
        if re.fullmatch(r"\x1b\[[02]?K", sequence):
            self._lines[-1] = ""

    def _newline(self) -> None:
        self._count(self._lines[-1])
        self._lines.append("")
        if len(self._lines) > self._max_lines:
            # A log longer than the window can ever show costs memory and
            # buys nothing. The head goes; what is happening now stays.
            del self._lines[:len(self._lines) - self._max_lines]

    def _count(self, line: str) -> None:
        found = _PACMAN_COUNT.match(line.lstrip())
        if found:
            self._done, self._total = int(found.group(1)), int(found.group(2))
            return
        for marker, fraction in _PHASES:
            if marker in line:
                self._floor = max(self._floor, fraction)

    def text(self) -> str:
        return "\n".join(self._lines)

    def progress(self) -> float:
        """How far the installation has got, between 0 and 1.

        WHAT THIS NUMBER IS. Two things, and neither is a timer:

          * pacman's own "(12/345)" while packages are being installed,
            which is exact for that phase and is most of the run;
          * otherwise the last phase this log announced, from the table
            above.

        WHAT IT IS NOT. It is not linear in time - unpacking 345 small
        packages and writing one kernel are not the same work - and the
        last fifth, after the packages, moves in steps rather than
        smoothly. An earlier version of this page therefore showed a
        pulsing bar and said so: "a fake percentage that stalls at 40%
        is worse than an honest still-working".

        That argument was against INVENTED numbers. These are read out
        of the log, and the bar only ever moves forward: max() keeps a
        phase marker arriving late from pulling it backwards.
        """
        if self._total:
            share = self._done / self._total
            return max(self._floor, 0.14 + share * (_PACKAGES_END - 0.14))
        return self._floor


class LogTail:
    """Read a growing log file in pieces, remembering where it stopped.

    The graphical surface polls this from the GTK main loop while the
    installation runs, so the user sees archinstall doing something
    rather than a window that has stopped repainting. Missing or
    unreadable files yield "" rather than raising: the log not existing
    yet is the normal state during the first fraction of a second, and no
    log is a reason to show less, never to interrupt an installation.

    Note that archinstall's own output is block-buffered when it is not
    writing to a terminal, so this delivers it in chunks rather than line
    by line. Chunks are what makes the difference between "something is
    happening" and a frozen window; smooth line-by-line output would need
    a pseudo-terminal, which is a change to how the process is started,
    not to how its output is read.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._offset = 0

    def read_new(self) -> str:
        try:
            with self._path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
                self._offset = handle.tell()
        except OSError:
            return ""
        return chunk


# How long discover_networks() will wait for a scan to finish, and how
# often it looks. Measured against what iwd actually does: a full scan of
# the 2.4 and 5 GHz channels takes a few seconds, and the networks appear
# in get-networks as each channel is heard rather than all at the end.
SCAN_BUDGET_SECONDS = 6.0
SCAN_POLL_SECONDS = 0.5


def discover_networks(
    wifi_backend: WifiBackend,
    *,
    budget: float = SCAN_BUDGET_SECONDS,
    poll: float = SCAN_POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Network]:
    """Scan for wireless networks, or return none at all if that is not
    possible.

    Covers both a machine with no wireless hardware (devices() returns
    an empty list - not an error) and a broken or missing iwctl
    (devices(), scan() or networks() raising RuntimeError or
    FileNotFoundError). Both outcomes are treated the same way: proceed
    without wireless, since installing over Ethernet is normal.

    WHY IT WAITS
        `iwctl station <dev> scan` STARTS a scan and returns immediately.
        Reading get-networks on the next line therefore returns whatever
        iwd already knew - on a freshly booted machine, the handful of
        access points from its own passive scan. Reported from the
        shipping medium on 10.08.2026: three networks in a place with
        many more, always the same three, and no way to reach the rest.

        So the list is read repeatedly until it stops growing, and only
        then returned. Stability, not a fixed sleep: a scan that finishes
        in a second costs a second, and one busy channel does not cost
        the same as thirty.

        The budget is a ceiling and not a target. Every path out of here
        returns the best list seen so far, because an installer that will
        not appear is worse than one offering four networks instead of
        five - and Ethernet, which needs none of this, is the common
        case.

    Identical rationale and identical exception handling to
    installer.tui.app._discover_networks, defined separately here rather
    than imported from there: that function is private to the text
    interface module, and this module must not depend on a
    presentation-layer module belonging to a different surface. Both
    wrap the exact same installer.core.wifi.WifiBackend calls the same
    way, so the two cannot drift into treating a missing adapter or a
    broken iwctl differently.
    """
    try:
        devices = wifi_backend.devices()
        if not devices:
            return []
        device = devices[0]
        wifi_backend.scan(device)

        found = wifi_backend.networks(device)
        waited = 0.0
        while waited < budget:
            sleep(poll)
            waited += poll
            again = wifi_backend.networks(device)
            if len(again) <= len(found):
                # Not "== len(found)": iwd drops an access point it can
                # no longer hear, and a list that shrinks is finished
                # just as much as one that stopped growing. Taking the
                # longer of the two keeps a network that was heard once.
                return again if len(again) > len(found) else found
            found = again
        return found
    except (RuntimeError, FileNotFoundError):
        return []
