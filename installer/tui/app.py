# SPDX-License-Identifier: GPL-3.0-or-later
"""Text interface. Fills the same model the GTK4 interface will.

Built first and on purpose: it needs no graphics stack, so it proves the
core layer (installer.core) can carry a complete installation on its
own. The GTK4 interface later fills the same InstallConfig through the
same core modules.

Every prompt goes through an injected `io` object with four methods -
ask(), ask_secret(), choose(), say() - so the whole flow is testable
without a terminal. main() goes one step further and takes the wifi
backend, the disk lister and the installer callable as injectable
dependencies too: a real run would otherwise shell out to iwctl, lsblk
and archinstall, exactly what the test suite's isolation guard (see
tests/conftest.py) exists to make impossible.
"""
from __future__ import annotations

import getpass
import sys
from typing import Any, Callable, Sequence

from installer.core.crypt import (
    accelerator_note, effective_layout, keyboard_note, loss_warning,
    passphrase_error, plaintext_warnings, unlock_note,
)
from installer.core import timezones
from installer.core.disks import Disk, human_size
from installer.core.disks import list_disks as _lsblk_list_disks
from installer.core.firmware import firmware_problem
from installer.core.i18n import _, activate, ngettext
from installer.core.model import (
    DiskChoice, InstallConfig, MIN_DISK_MIB, UserAccount, WifiCredentials,
    ZeposOptions,
)
from installer.core.runner import InstallationRefused
from installer.core.runner import install as _run_install
from installer.core.validate import HOSTNAME_PATTERN, MIN_PASSWORD_LENGTH, validate
from installer.core.wifi import (
    Connection, IwctlBackend, Network, WifiBackend, associate as _iwd_associate,
)

# (language, keymap, locale). Identical values and identical rationale
# to installer.gui.pages.LANGUAGE_DEFAULTS, where the whole reasoning
# stands.
#
# DIE ZEITZONE STAND HIER BIS ZUM 02.09.2026 ALS VIERTER WERT, und sie
# ist ersatzlos herausgefallen: "de" -> Europe/Berlin, "en" -> UTC, also
# eine Ableitung von einem ORT aus einer SPRACHE - und die gibt es
# nicht. Bemerkenswert ist, dass der Kommentar, der hier stand, den Fall
# selbst benannte ("a German-language install run from a machine
# physically located elsewhere would otherwise get the wrong clock") und
# eine ABGEFRAGTE Vorbelegung fuer die Antwort darauf hielt. Sie war es
# nicht: wer eine Vorbelegung bestaetigt, hat sie nicht geprueft, und
# durchdruecken ist der gewoehnliche Weg durch einen Assistenten.
#
# An ihre Stelle tritt eine TATSACHE - timezones.running() liest, in
# welcher Zone dieses Medium gerade laeuft. Tastaturbelegung und
# Sprachumgebung bleiben, weil beide wirklich an der Sprache haengen und
# nicht an einem Ort.
LANGUAGES: list[tuple[str, str, str]] = [
    ("de", "de-latin1", "de_DE"),
    ("en", "us", "en_US"),
]

DiskLister = Callable[..., Sequence[Disk]]
Installer = Callable[[InstallConfig], int]
Associator = Callable[[WifiBackend, str, str], Connection]


class ConsoleIO:
    """The real io implementation: a terminal via input()/print()/getpass."""

    def ask(self, prompt: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        return input(f"{prompt}{suffix}: ").strip() or default

    def ask_secret(self, prompt: str) -> str:
        return getpass.getpass(f"{prompt}: ")

    def choose(self, prompt: str, options: Sequence[str]) -> int:
        print(prompt)
        for index, option in enumerate(options, start=1):
            print(f"  {index}) {option}")
        choice_prompt = _("Choice")
        while True:
            raw = input(f"{choice_prompt}: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return int(raw) - 1
            print(_("Please enter one of the offered numbers."))

    def say(self, text: str) -> None:
        print(text)


def _ask_password(io: Any, label: str) -> str:
    """Ask for a password, then ask again to confirm it.

    getpass echoes nothing, so a typo is otherwise invisible to the
    person typing it - they would only find out at a failed login,
    potentially on a machine with no other way in. Re-prompts on a
    mismatch, not just on insufficient length.
    """
    while True:
        value = io.ask_secret(label)
        if len(value) < MIN_PASSWORD_LENGTH:
            io.say(
                _("The password is too short. At least {minimum} characters are required.")
                .format(minimum=MIN_PASSWORD_LENGTH)
            )
            continue
        if value != io.ask_secret(_("Repeat the password")):
            io.say(_("The passwords do not match."))
            continue
        return value


def _ask_encryption(io: Any, disk: Disk) -> tuple[bool, str]:
    """Die Verschluesselungsfrage des Textassistenten.

    Gibt (verschluesseln, passphrase) zurueck. Dieselben Fragen wie auf
    der Seite der grafischen Oberflaeche.

    DIE REIHENFOLGE, und jeder Schritt steht dort, wo er noch etwas
    aendern kann:

      1. WAS ES IST UND WAS ES KOSTET - vor der Frage, weil das die
         Angaben sind, an denen jemand "ja" oder "nein" festmacht: die
         zehn Sekunden beim Einschalten, der fehlende AES-Befehlssatz
         (nur wenn er fehlt), und was trotzdem im Klartext bleibt.
      2. DIE FRAGE.
      3. WAS EIN VERLUST KOSTET - nach dem Ja und vor der Eingabe. Nach
         dem Ja, weil wer "nein" sagt, keine Warnung ueber eine
         Passphrase braucht, die es nicht geben wird; eine Warnung, die
         auch den Unbeteiligten trifft, wird beim naechsten Mal
         ueberlesen. Vor der Eingabe, weil sie danach nichts mehr
         entscheidet - wer schon getippt hat, sucht die naechste Frage.

    Dieselbe Stelle wie auf der grafischen Seite, wo die Warnung zwischen
    dem Schalter und den Eingabefeldern steht.
    tests/installer/test_tui.py haelt die Reihenfolge fest, gegen das
    Protokoll und nicht nur gegen die Ausgaben - eine fruehere Fassung
    dieses Tests konnte "danach" nicht von "davor" unterscheiden und hat
    eine Mutation ueberlebt, die genau das vertauschte.

    WARUM DIE VORGABE "JA" IST
        Dieselbe Entscheidung wie in installer.gui.pages.PageState und
        dort ausfuehrlich begruendet: der Nutzer hat "immer" gesagt, und
        eine Vorgabe ist das, was die meisten Installationen bekommen.
        Die Reihenfolge [Ja, Nein] mit dem Vergleich `== 0` ist dasselbe
        Muster, mit dem die Zusatzpakete weiter unten ihr "Nein" an die
        erste Stelle setzen - dort ist die Vorgabe "nein", hier "ja", und
        beide Male steht die Vorgabe vorn.
    """
    io.say(_("ZepOS can encrypt this disk with AES-256, the strength governments use for classified material. Without the passphrase the disk is unreadable, even taken out of this computer."))
    io.say(unlock_note())
    accelerator = accelerator_note()
    if accelerator:
        io.say(accelerator)
    # Die leere Einteilung ist hier kein Platzhalter, sondern die Lage:
    # der Textassistent plant keine, also wird der Vorschlag installiert,
    # und effective_layout() setzt genau den ein. Die Seite der
    # grafischen Oberflaeche reicht an derselben Stelle ihre eigene
    # Einteilung herein.
    for warning in plaintext_warnings(effective_layout([], disk.size_bytes)):
        io.say(warning)

    if io.choose(_("Encrypt this disk?"), [_("Yes"), _("No")]) != 0:
        return False, ""

    # Der Verlust zuerst, weil er das ist, was diese Passphrase von jedem
    # anderen Passwort unterscheidet, und die Tastaturbelegung direkt
    # danach, weil sie das ist, woran man beim Tippen denken muss.
    io.say(loss_warning())
    io.say(keyboard_note())
    return True, _ask_passphrase(io)


def _ask_passphrase(io: Any) -> str:
    """Die Passphrase, verdeckt, zweimal - bis beide Haelften stimmen.

    Gebaut wie _ask_password() daneben und trotzdem eine eigene
    Funktion: die Regel ist eine andere (eine hoehere Mindestlaenge,
    siehe installer.core.crypt fuer den Grund), und die Pruefung selbst
    kommt aus installer.core.crypt.passphrase_error() - derselben
    Funktion, an der die grafische Seite ihre Felder misst. Zwei
    Oberflaechen, eine Regel.

    Die Laenge wird geprueft, BEVOR nach der Wiederholung gefragt wird,
    und dafuer wird dieselbe Funktion mit dem Wert gegen sich selbst
    aufgerufen: so kann nur die Laengenregel anschlagen, und niemand
    tippt eine zu kurze Passphrase zweimal, um dann zu erfahren, dass sie
    zu kurz war. _ask_password() daneben macht es genauso.
    """
    while True:
        value = io.ask_secret(_("Disk passphrase"))
        problem = passphrase_error(value, value)
        if problem:
            io.say(problem)
            continue
        problem = passphrase_error(value, io.ask_secret(_("Repeat the passphrase")))
        if problem:
            io.say(problem)
            continue
        return value


def _ask_until(io: Any, getter: Callable[[], str]) -> str:
    """Re-prompt until a non-empty answer is given.

    Shared by _ask_required() and _ask_required_secret() below, which
    differ only in whether the answer is echoed - the empty-check and
    the re-prompt message are identical either way.
    """
    while True:
        value = getter().strip()
        if value:
            return value
        io.say(_("This entry may not be empty."))


def _ask_required(io: Any, label: str) -> str:
    return _ask_until(io, lambda: io.ask(label))


def _ask_required_secret(io: Any, label: str) -> str:
    """Same as _ask_required(), but the value is never echoed - used for
    the wireless passphrase, which is a credential like any password."""
    return _ask_until(io, lambda: io.ask_secret(label))


def _ask_hostname(io: Any) -> str:
    while True:
        value = io.ask(_("Hostname"), "zepos")
        if HOSTNAME_PATTERN.match(value):
            return value
        # Reuses validate()'s own hostname finding message rather than a
        # new msgid: the two must always describe the exact same rule,
        # and HOSTNAME_PATTERN is imported from validate.py for the same
        # reason - one source of truth for what a valid hostname is.
        io.say(
            _("The hostname may contain only letters, digits and hyphens, and may not start or end with a hyphen.")
        )


def _ask_timezone(io: Any) -> str:
    """Die Zeitzone - GEPRUEFT, seit dem 02.09.2026.

    WAS HIER STAND UND WARUM ES WEG IST
        Eine einzige Zeile: `io.ask(_("Timezone"), default_timezone)`.
        Kein Rueckfragen, keine Pruefung, und die Vorbelegung aus der
        SPRACHE. Zwei Fehler, und der zweite ist ein ausgelieferter:

          die Ableitung  "en" hiess UTC. Wer auf Englisch installierte,
                         bekam eine Uhr auf UTC - gleichgueltig, wo er
                         sass. Die Tabelle oben fuehrt es aus.
          die Annahme    `date` nimmt JEDEN Namen an. "Europe/Berln"
                         wurde anstandslos installiert; danach druckt
                         date(1) die UTC-Zeit mit "Berln" als Kuerzel,
                         Rueckgabewert 0, leere Fehlerausgabe (die
                         Messung steht in src/doctor.py). Ein
                         Tippfehler bei der Installation wurde so zu
                         einer Uhr, die still zwei Stunden falsch geht -
                         und der Mensch merkt es fruehestens, wenn eine
                         Verabredung verrutscht.

    WARUM DIES UND NICHT io.choose() MIT DER GANZEN LISTE
        Weil die Datenbank 598 Namen hat - GEMESSEN am 02.09.2026 -,
        io.choose() jede Zeile ausdruckt und ein Terminal
        herkoemmlicherweise vierundzwanzig hat. Eine numerierte Liste
        ueber 598 Zeilen ist keine Auswahl, sondern eine Wand.

        Die grafische Oberflaeche hat es leichter: ihr Auswahlfeld hat
        ein SUCHFELD (installer/gui/app.py:_build_zeit). Hier ist
        timezones.matching() dieses Suchfeld - dieselbe Quelle,
        dieselbe Ablehnung, nur ohne GTK darum. Wer den Namen kennt,
        tippt ihn; wer sich vertippt, bekommt den richtigen genannt.

    DIE VIER ZUSAGEN SIND DAMIT DIESELBEN WIE IN DER GRAFISCHEN:
        die Namen kommen aus der ECHTEN Datenbank, die Vorbelegung ist
        die laufende Zone statt einer aus der Sprache abgeleiteten, ein
        erfundener Name kommt NICHT durch, und man findet seinen Namen
        auch dann, wenn man ihn nicht auswendig weiss.
    """
    laufend = timezones.running()
    while True:
        value = io.ask(_("Timezone"), laufend).strip()
        if timezones.known(value):
            return value
        # Woertlich der msgid, den PageState.timezone_error() der
        # grafischen Oberflaeche benutzt, und aus demselben Grund, aus
        # dem _ask_hostname() sich die Meldung von validate() leiht:
        # zwei Oberflaechen, die dieselbe Regel verschieden erklaeren,
        # sind zwei Regeln.
        io.say(
            _("This machine's timezone database does not have \"{zone}\".")
            .format(zone=value)
        )
        vorschlaege = timezones.matching(value)
        if not vorschlaege:
            # Kein Vorschlag ist auch eine Auskunft, und es ist die, bei
            # der ein Mensch sonst dreimal dasselbe tippt. Der Befehl
            # steht dabei, weil er der einzige Weg ist, an die Namen zu
            # kommen, ohne den Assistenten zu verlassen.
            # EIN Literal und nicht zwei aneinandergesetzte: die
            # Vollstaendigkeitspruefung in tests/installer/test_i18n.py
            # kann Pythons stille Verkettung nicht verfolgen und meldete
            # am 02.09.2026 die erste Haelfte als msgid ohne
            # Katalogeintrag. Dieselbe Zeile und derselbe Grund stehen in
            # installer/core/validate.py und in netprofile.py.
            io.say(_("`timedatectl list-timezones` names the zones this machine knows."))
            continue
        gezeigt = vorschlaege[:timezones.SUGGESTION_LIMIT]
        io.say(_("Did you mean one of these?"))
        for name in gezeigt:
            # Ein Zonenname ist ein Name und keine natuerliche Sprache -
            # dieselbe Behandlung wie ein Geraetepfad in der
            # Plattenauswahl weiter unten.
            io.say(f"  {name}")
        uebrig = len(vorschlaege) - len(gezeigt)
        if uebrig:
            # GEZAEHLT und nicht abgeschnitten: eine Liste, die
            # stillschweigend endet, sieht aus wie die ganze Antwort.
            io.say(ngettext("{count} more name matches.",
                            "{count} more names match.", uebrig)
                   .format(count=uebrig))


def _connect_wireless(
    io: Any, wifi_backend: WifiBackend, ssid: str, associate: Associator
) -> WifiCredentials | None:
    """Ask for the passphrase, join the network, and offer another try.

    A mistyped passphrase is the most likely error in the whole
    installer, so one failed attempt must not silently end the wireless
    step - and must certainly not write that wrong passphrase into the
    target system's connection profile, where it would leave the
    installed machine unable to get online with no hint why.

    Returns None when the user gives up on wireless, which is not an
    error: installing over ethernet, or entirely offline, is normal.
    """
    while True:
        passphrase = _ask_required_secret(
            io, _("Password for {ssid}").format(ssid=ssid)
        )
        result = associate(wifi_backend, ssid, passphrase)
        if result.message:
            io.say(result.message)
        if result.connected:
            return WifiCredentials(ssid=ssid, passphrase=passphrase)
        if io.choose(_("Try the wireless network again?"), [_("Yes"), _("No")]) != 0:
            return None


def collect(
    io: Any,
    *,
    devices: Sequence[Disk],
    networks: Sequence[Network],
    wifi_backend: WifiBackend,
    associate: Associator | None = None,
) -> InstallConfig | None:
    """Walk the user through every step and return the finished config.

    Returns None if no offered disk is large enough to install onto -
    the one condition below that a re-prompt cannot fix, since it is a
    fact about the hardware, not something the user mistyped. Every
    other field is validated at the point of entry (hostname, username,
    both passwords, the wireless passphrase when a network was chosen),
    so a findings-bearing InstallConfig should never actually come out
    of this function; main() still runs validate() on the result as a
    last-resort net regardless.

    Order: language and keyboard, network, disk, user, timezone, ZepOS
    options. The summary and confirmation step that follows collect() in
    the overall flow lives in main(), not here - collect()'s only job is
    to turn answers into an InstallConfig (or None), not to decide
    whether to act on it.
    """
    # Resolved here, not bound as a signature default: the real
    # associate() opens a socket to check the connection, which the test
    # suite's isolation guard has nothing to say about - a default
    # argument would capture it at import time, out of reach of any
    # caller wanting to replace it.
    associate = associate or _iwd_associate

    # Step 1: language and keyboard. activate() runs immediately, not
    # after collect() returns, so every prompt below - in this very call
    # - is already shown in the language the user just picked.
    lang_index = io.choose(_("Select language"), [_("German"), _("English")])
    language, keymap, locale = LANGUAGES[lang_index]
    activate(language)

    # Step 2: network. Skipped silently when no networks were offered -
    # installing over ethernet is normal, not an error. main() is what
    # decides networks is empty (no wireless device, or iwctl missing);
    # collect() only has to honour that decision without a prompt.
    wifi = None
    if networks:
        options = [network.ssid for network in networks] + [_("Skip")]
        choice = io.choose(_("Select wireless network"), options)
        if choice < len(networks):
            # Joining the network here, in the live session, is the
            # "verbinden" half of spec 8.2 step 2. Collecting the
            # passphrase without it left wireless-only machines
            # permanently offline during the installation.
            wifi = _connect_wireless(
                io, wifi_backend, networks[choice].ssid, associate
            )

    # Step 3: disk. Only disks large enough to actually take an install
    # are offered at all - a too-small disk is a fact about the
    # hardware, not a typo, so unlike every other field below it cannot
    # be fixed by re-prompting and must not be selectable in the first
    # place. If nothing qualifies, this whole call ends here: there is
    # no point asking for a hostname, a username and two passwords only
    # to refuse at the very end.
    usable = [
        disk for disk in devices
        if disk.size_bytes // (1024 * 1024) >= MIN_DISK_MIB
    ]
    if not usable:
        io.say(
            _("No disk is large enough to install ZepOS. At least {minimum} MiB are required.")
            .format(minimum=MIN_DISK_MIB)
        )
        return None

    # Each option shows a human-readable size so otherwise identical-
    # looking devices can be told apart. Not passed through _(): a
    # device path and a size unit already treated as unlocalised (see
    # human_size()'s own docstring) are not natural-language text - the
    # byte count itself still goes into DiskChoice.size_bytes below,
    # since validate() and to_archinstall_config() both reject a disk
    # whose size is unset.
    disk_options = [
        f"{disk.device} ({human_size(disk.size_bytes)})" for disk in usable
    ]
    disk_index = io.choose(_("Select installation disk"), disk_options)
    chosen_disk = usable[disk_index]

    # Step 3b: die Verschluesselung. Direkt hinter der Plattenwahl, weil
    # sie eine Aussage ueber DIESE Platte ist und weil danach nichts mehr
    # ueber sie entschieden wird - dieselbe Stelle, an der die grafische
    # Oberflaeche ihre Seite hat (installer.gui.pages.PAGE_ORDER).
    encrypt, encryption_passphrase = _ask_encryption(io, chosen_disk)

    # Step 4: user. Hostname travels with the account questions rather
    # than getting its own top-level step - both describe who and what
    # this machine is, and no step of its own was named for it in the
    # resolved step order.
    hostname = _ask_hostname(io)
    username = _ask_required(io, _("Username"))
    password = _ask_password(io, _("Password"))
    root_password = _ask_password(io, _("Root password"))

    # Step 5: timezone. Asked explicitly, prefilled with the zone this
    # medium is RUNNING in, and re-asked until the name is one the
    # database actually has - see _ask_timezone(), which carries the
    # whole reasoning and the measurement behind it.
    timezone = _ask_timezone(io)

    # Step 6: ZepOS options.
    weather_location = io.ask(_("Location for the weather widget"), "")
    plugins_choice = io.choose(_("Enable ZepOS plugins?"), [_("Yes"), _("No")])

    # Die drei Zusatzpakete, dieselben wie auf der ZepOS-Seite der
    # grafischen Oberflaeche. Die Vorgabe ist bei allen dreien "Nein" und
    # steht deshalb an ZWEITER Stelle: io.choose() gibt einen Index
    # zurueck, und die Reihenfolge [Ja, Nein] mit dem Vergleich `== 0`
    # ist das Muster, das die Zeile darueber schon benutzt. Wer stumpf
    # durchdrueckt, bekommt hier also nichts dazu - was die Absicht ist.
    office_choice = io.choose(
        _("Install office applications (LibreOffice, about 646 MB)?"),
        [_("No"), _("Yes")])
    devel_choice = io.choose(
        _("Install development tools (base-devel and git, about 440 MB)?"),
        [_("No"), _("Yes")])

    return InstallConfig(
        language=language,
        keymap=keymap,
        timezone=timezone,
        locale=locale,
        hostname=hostname,
        disk=DiskChoice(
            device=chosen_disk.device, size_bytes=chosen_disk.size_bytes,
            encrypt=encrypt, passphrase=encryption_passphrase),
        users=[UserAccount(username=username, password=password, sudo=True)],
        root_password=root_password,
        wifi=wifi,
        zepos=ZeposOptions(
            enable_plugins=plugins_choice == 0,
            weather_location=weather_location,
            install_office=office_choice == 1,
            install_devel=devel_choice == 1,
        ),
    )


def _print_summary(io: Any, cfg: InstallConfig) -> None:
    io.say(_("Summary"))
    io.say(_("Hostname: {value}").format(value=cfg.hostname))
    io.say(_("Disk: {value}").format(value=cfg.disk.device))
    # Auch das "nein", und aus demselben Grund wie in der grafischen
    # Zusammenfassung: der Fall, den man hier bemerken koennen muss, ist
    # der, in dem NICHT verschluesselt wird.
    io.say(_("Encryption: {value}").format(
        value=_("yes, AES-256") if cfg.disk.encrypt else _("no")))
    username = cfg.users[0].username if cfg.users else ""
    io.say(_("Username: {value}").format(value=username))
    io.say(_("Timezone: {value}").format(value=cfg.timezone))


def _confirm(io: Any, cfg: InstallConfig) -> bool:
    """The point of no return. Names the disk.

    "This erases the entire disk" without saying which one is the
    sentence a user confirms while picturing a different disk than the
    one selected - and this is the last moment at which that can still be
    noticed. Same msgid as the graphical surface's confirmation dialog.
    """
    io.say(_("This erases the entire disk {device}.").format(device=cfg.disk.device))
    if cfg.disk.encrypt:
        # Woertlich derselbe Satz wie auf der Verschluesselungsseite und
        # in der Rueckfrage der grafischen Oberflaeche. Warum zweimal
        # derselbe und nicht zweimal ein anderer, steht in
        # installer.gui.pages.confirmation_body().
        io.say(_("The disk will be encrypted."))
        io.say(loss_warning())
    choice = io.choose(_("Start installation now?"), [_("Yes"), _("No")])
    return choice == 0


def _finish_installation(io: Any, cfg: InstallConfig, install: Installer) -> int:
    """Show the summary, refuse to start while any validate() finding
    remains, ask for confirmation, then hand off to the installer.

    By the time collect() has returned a config at all (rather than
    None), every finding validate() can produce should already be
    unreachable: hostname, username, both passwords and the wireless
    passphrase are validated at the point of entry, and the disks
    collect() offers are pre-filtered to only those large enough. This
    check stays in place anyway as a last-resort net - if it ever does
    fire, that is a bug in the per-field validation above, not a reason
    to let it through unannounced.
    """
    findings = validate(cfg)
    _print_summary(io, cfg)
    if findings:
        io.say(_("The installation cannot start:"))
        for finding in findings:
            io.say(f"  - {finding}")
        return 1

    if not _confirm(io, cfg):
        io.say(_("Installation cancelled."))
        return 0

    io.say(_("Starting installation."))
    return _run_and_report(io, cfg, install)


def _run_and_report(io: Any, cfg: InstallConfig, install: Installer) -> int:
    """Run the installation and turn every possible ending into a
    sentence, the way installer.gui.pages.run_installation() does for the
    graphical surface.

    Nothing here may escape as a traceback. install() raises at three
    separate points, and the user reaches all of them AFTER confirming
    "This erases the entire disk" and reading "Starting installation." -
    a Python traceback at that moment says nothing about the one question
    they now have, which is whether the disk was already touched. That
    question is what InstallationRefused answers: it is raised only where
    archinstall has provably not started yet.

    Every other failure is reported with no statement about the disk at
    all. Past the refusals, archinstall may have been partitioning
    already, and a wrong "nothing was changed" is far worse than no
    sentence about it.
    """
    try:
        code = install(cfg)
    except InstallationRefused as exc:
        io.say(
            _("The installation could not be carried out: {reason}")
            .format(reason=exc)
        )
        io.say(
            _("Nothing on the disk {device} was changed.")
            .format(device=cfg.disk.device)
        )
        return 1
    except Exception as exc:
        io.say(
            _("The installation could not be carried out: {reason}")
            .format(reason=exc)
        )
        return 1

    if code == 0:
        io.say(_("Installation completed successfully."))
    else:
        # archinstall failing is an exit code, not an exception, and used
        # to be returned to the shell without a word. Same msgid the
        # graphical surface reports it with.
        io.say(_("Installation failed (exit code {code}).").format(code=code))
    return code


def _discover_networks(wifi_backend: WifiBackend) -> list[Network]:
    """Scan for networks, or return none at all if that is not possible.

    Covers both a machine with no wireless hardware (devices() returns an
    empty list - not an error) and a broken or missing iwctl (devices(),
    scan() or networks() raising RuntimeError or FileNotFoundError). Both
    outcomes are treated the same way: proceed without wireless, since
    installing over ethernet is normal.
    """
    try:
        wifi_devices = wifi_backend.devices()
        if not wifi_devices:
            return []
        wifi_backend.scan(wifi_devices[0])
        return wifi_backend.networks(wifi_devices[0])
    except (RuntimeError, FileNotFoundError):
        return []


def main(
    argv: Sequence[str] | None = None,
    *,
    io: Any | None = None,
    wifi_backend: WifiBackend | None = None,
    list_disks: DiskLister | None = None,
    install: Installer | None = None,
    associate: Associator | None = None,
    is_uefi: Callable[[], bool] | None = None,
) -> int:
    # argv is accepted but not yet read: there are no command-line flags
    # this interface needs so far (e.g. a future --dry-run). Kept in the
    # signature now so callers and the __main__ entry point below do not
    # have to change shape once one is added.

    # Every dependency is resolved here, not bound as a signature
    # default: a default argument captures the real implementation at
    # import time, which the test suite's isolation guard cannot
    # intercept (see the identical note in installer.core.runner).
    io = io or ConsoleIO()
    wifi_backend = wifi_backend or IwctlBackend()
    list_disks = list_disks or _lsblk_list_disks
    install = install or _run_install

    # Before the first question, and before any hardware is enumerated: a
    # machine that started in BIOS mode cannot boot what ZepOS installs,
    # and no answer the user could give would change that. Discovering it
    # at the point of the erase - where installer.core.runner.install()
    # also checks, and must keep checking - meant seven questions, a
    # summary and a confirmed disk erase first, on exactly the old
    # hardware this interface exists for.
    problem = firmware_problem(is_uefi=is_uefi)
    if problem:
        io.say(problem)
        return 1

    try:
        disks = list_disks()
    except (RuntimeError, FileNotFoundError) as exc:
        io.say(_("Could not list disks: {reason}").format(reason=exc))
        return 1
    if not disks:
        io.say(_("No installable disk was found."))
        return 1

    networks = _discover_networks(wifi_backend)

    cfg = collect(
        io,
        devices=disks,
        networks=networks,
        wifi_backend=wifi_backend,
        associate=associate,
    )
    if cfg is None:
        # collect() has already told the user why (no disk was large
        # enough) via io.say() before returning None here.
        return 1

    # Step 7: summary and confirmation.
    return _finish_installation(io, cfg, install)


if __name__ == "__main__":
    sys.exit(main())
