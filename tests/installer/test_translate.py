# SPDX-License-Identifier: GPL-3.0-or-later
import json
import subprocess
from pathlib import Path

import pytest

from installer.core.layout import PlannedPartition
from installer.core.model import InstallConfig, DiskChoice, UserAccount, ZeposOptions
from installer.core.source import PackageSource
from installer.core.translate import (GRUB_MKCONFIG_COMMAND, to_archinstall_config,
                                      to_archinstall_creds)


def _cfg() -> InstallConfig:
    return InstallConfig(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda", wipe=True, filesystem="ext4", size_bytes=64 * 1024**3),
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


def test_the_login_service_is_enabled():
    """Ohne diesen Schluessel erreicht das installierte System "Reached
    target Graphical Interface" und bleibt dort stehen - gemessen mit
    iso/test-boot.py --scenario release-installed.

    Ein Paket kann den Dienst nicht aktivieren; pacman fuehrt dafuer kein
    systemctl aus. archinstall 4.4 kann es: lib/args.py liest "services"
    und scripts/guided.py gibt die Liste an enable_service() weiter -
    NACH add_additional_packages(), also ist die Unit dann schon da.
    """
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert "greetd.service" in out["services"]


def test_the_installed_machine_updates_itself(monkeypatch):
    """UP-1: eine frisch installierte Maschine soll sich Aktualisierungen
    selbst holen. Ohne diesen Eintrag laege der Zeitgeber im Paket und
    niemand schaltete ihn ein - die Maschine haette alles ausser dem
    Symlink, der sie ausloest.

    Der Zeitgeber und NICHT der Dienst: `zepos-update.service` hier waere
    eine Aktualisierung bei jedem Start, sofort und ohne Streuung. Der
    Name wird aus src/update.py gelesen und nicht abgeschrieben, damit
    eine Umbenennung dort hier auffaellt und nicht als
    "Unit does not exist" mitten in einer Installation.
    """
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "src"))
    import update

    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert update.TIMER_UNIT in out["services"]
    assert update.SERVICE_UNIT not in out["services"]


def test_bluetooth_is_switched_on_and_not_only_installed():
    """bluez ohne laufenden Dienst ist der Zustand, in dem bluetoothctl
    haengt - und genau der lag auf der Testinstallation.

    GEMESSEN am 17.08.2026 an iso/out/release-target.img (LUKS
    entsperrt, Wurzel p2):

        bluez 5.87-2, bluez-utils 5.87-2, blueman 2.4.6-2 installiert
        /usr/lib/systemd/system/bluetooth.service   vorhanden
        /etc/systemd/system/bluetooth.target.wants/ FEHLT
        /etc/systemd/system/dbus-org.bluez.service  FEHLT

    Der zweite fehlende Name ist der Alias aus dem [Install]-Abschnitt
    der Unit, und /usr/share/dbus-1/system-services/org.bluez.service
    nennt genau ihn als "SystemdService" bei "Exec=/bin/false". Ohne ihn
    kann der Systembus org.bluez weder starten noch vermitteln:
    `bluetoothctl show` wartet auf einen Namen, der nie kommt.

    Der Nutzer hat am selben Tag gemeldet, dass das Statusskript
    einfriert, und im selben Atemzug "bluez vorinstalliert bluetooth
    soll funktionieren" bestellt. Installiert war es; eingeschaltet
    nicht.
    """
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert "bluetooth.service" in out["services"]


def test_the_target_gets_grub_and_not_systemd_boot():
    """Was nach einer Installation als Startmenue erschien, war
    systemd-boot: eine Liste aus /boot/loader/entries, die sich nicht
    themen laesst. Das Medium bootet dagegen in ein gethemtes
    GRUB-Menue - dieselbe Maschine zeigte vor der Installation ZepOS und
    danach nicht mehr.

    Die Schreibung ist die von archinstall 4.4: Bootloader.Grub == 'Grub'
    (lib/models/bootloader.py).
    """
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert out["bootloader_config"]["bootloader"] == "Grub"


def test_the_bootloader_is_not_installed_removable():
    """--removable schreibt nach EFI/BOOT/BOOTX64.EFI, den Pfad, den eine
    Firmware nimmt, wenn sie sonst nichts findet. Auf einem USB-Stick ist
    das richtig; auf der eingebauten Platte, die ZepOS installiert,
    ueberschreibt es den Rueckfalleintrag eines zweiten Systems."""
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert out["bootloader_config"]["removable"] is False


def test_the_boot_menu_is_rebuilt_after_the_theme_is_installed():
    """Die Reihenfolge in archinstalls scripts/guided.py ist
    add_bootloader() -> add_additional_packages() -> enable_service() ->
    run_custom_user_commands(). Der erste grub-mkconfig-Lauf steckt in
    add_bootloader() und laeuft, bevor zepos-config das Thema und
    /etc/default/grub.d/10-zepos.cfg abgelegt hat. Ohne den zweiten Lauf
    traegt das Startmenue kein ZepOS - und meldet das nicht, weil GRUB
    ein fehlendes Thema mit dem Textmodus beantwortet.

    GEPRUEFT WIRD DIE ERSTE STELLE, NICHT MEHR DIE EINZIGE. Bis zum
    13.08.2026 stand hier `== [GRUB_MKCONFIG_COMMAND]`, also die
    Behauptung "es gibt genau einen solchen Befehl". Das war nie das
    Thema dieses Tests - sein Thema ist, DASS das Startmenue ein zweites
    Mal erzeugt wird - und seit PLYMOUTH_COMMAND daneben steht, waere es
    eine Behauptung ueber eine Liste, in die etwas Richtiges
    hinzugekommen ist.

    Die Zusicherung ist dabei nicht schwaecher geworden, sondern
    genauer: sie sagt jetzt zusaetzlich, dass der GRUB-Befehl der ERSTE
    ist. Das ist die Rangfolge, die installer/core/translate.py
    aufschreibt - was zuerst laeuft, laeuft auch dann, wenn das zweite
    haengt -, und vorher hat sie niemand geprueft.
    """
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert out["custom_commands"][0] == GRUB_MKCONFIG_COMMAND
    assert "grub-mkconfig -o /boot/grub/grub.cfg" in GRUB_MKCONFIG_COMMAND


def _run_rebuild(tmp_path, grub_mkconfig: str):
    """Den Befehl ausfuehren, den archinstall im Ziel ausfuehren wird.

    `arch-chroot ... bash <datei>` ist genau das hier, nur mit einem
    grub-mkconfig, das der Test schreibt. Unter `env -i` mit dem
    Stubverzeichnis als ganzem PATH, damit kein echtes grub-mkconfig
    erreichbar ist - auf dem Rechner, der die Tests laeuft, gibt es
    eines, und es schreibt /boot/grub/grub.cfg.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    stub = stubs / "grub-mkconfig"
    stub.write_text("#!/bin/bash\n" + grub_mkconfig, encoding="utf-8")
    stub.chmod(0o755)

    script = tmp_path / "user-command.0.sh"
    script.write_text(GRUB_MKCONFIG_COMMAND, encoding="utf-8")
    return subprocess.run(
        ["/usr/bin/env", "-i", f"PATH={stubs}", "/bin/bash", str(script)],
        env={}, input="", capture_output=True, text=True, timeout=60)


@pytest.mark.allow_subprocess
def test_the_rebuild_can_never_fail_the_installation(tmp_path):
    """run_custom_user_commands() laeuft ueber SysCommand, das bei einem
    Rueckgabewert != 0 wirft, und in guided.py steht danach - und nur
    danach - installation.genfstab(). Ein hier scheiternder Befehl kostet
    also nicht das Startmenue, sondern die /etc/fstab: ein System, das
    nicht mehr bootet, weil sein Menue haette huebsch werden sollen.
    """
    result = _run_rebuild(tmp_path, 'echo "grub-mkconfig kaputt" >&2\nexit 1\n')
    assert result.returncode == 0, result.stderr


@pytest.mark.allow_subprocess
def test_a_boot_menu_without_the_theme_says_so(tmp_path):
    """GRUB antwortet auf ein Thema, das es nicht lesen kann, mit dem
    Textmodus und ohne Fehler - iso/profile-release/grub/grub.cfg
    schreibt denselben Satz auf. grub-mkconfig meldet den Fund nur als
    eine Zeile auf stderr, und die einzige Stelle, an der die noch jemand
    liest, ist das Installationsprotokoll.
    """
    # Der Pfad ist der aus src/boot/grub-zepos.cfg, und er liegt seit dem
    # 17.08.2026 unter /boot: /usr/share liegt auf der verschluesselten
    # Wurzel, und is_path_readable_by_grub verwirft von dort alles - dann
    # kommt diese Zeile gar nicht erst, und das Menue ist ein nacktes
    # GRUB. tests/boot/test_grub_theme.py traegt die ganze Messung.
    found = _run_rebuild(
        tmp_path, 'echo "Found theme: /boot/grub/themes/zepos/theme.txt" >&2\n')
    assert "mit dem ZepOS-Thema" in found.stdout, found.stdout + found.stderr

    missing = _run_rebuild(tmp_path, 'echo "Generating grub configuration ..." >&2\n')
    assert "OHNE das ZepOS-Thema" in missing.stderr, missing.stdout + missing.stderr
    assert missing.returncode == 0


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


def test_sizes_carry_a_sector_size_dict():
    """archinstall's Size.parse_args subscripts sector_size; null raises
    TypeError. Its own bundled sample gets this wrong."""
    mod = to_archinstall_config(_cfg(), PackageSource.ONLINE)["disk_config"]["device_modifications"][0]
    for part in mod["partitions"]:
        for key in ("start", "size"):
            assert part[key]["sector_size"] == {"value": 512, "unit": "B"}


def test_no_partition_uses_a_percent_unit():
    """Unit has no Percent member; it would raise KeyError at load time."""
    mod = to_archinstall_config(_cfg(), PackageSource.ONLINE)["disk_config"]["device_modifications"][0]
    for part in mod["partitions"]:
        assert part["start"]["unit"] != "Percent"
        assert part["size"]["unit"] != "Percent"


def test_root_partition_fills_the_rest_of_the_disk():
    cfg = _cfg()
    cfg.disk.size_bytes = 64 * 1024**3
    mod = to_archinstall_config(cfg, PackageSource.ONLINE)["disk_config"]["device_modifications"][0]
    esp, root = mod["partitions"]
    disk_mib = 64 * 1024
    assert root["start"]["value"] + root["size"]["value"] == disk_mib - 1


def test_disk_too_small_is_refused():
    cfg = _cfg()
    cfg.disk.size_bytes = 100 * 1024**2   # 100 MiB
    try:
        to_archinstall_config(cfg, PackageSource.ONLINE)
    except ValueError:
        return
    raise AssertionError("a disk too small for the layout must be refused")


def test_offline_source_sets_offline_flag_and_repo():
    out = to_archinstall_config(_cfg(), PackageSource.OFFLINE)
    assert out["offline"] is True
    assert out["mirror_config"]["custom_repositories"][0]["url"].startswith("file://")


def test_online_source_clears_offline_flag():
    assert to_archinstall_config(_cfg(), PackageSource.ONLINE)["offline"] is False


def test_audio_is_configured_under_app_config():
    """archinstall 4.4 reads a top-level "audio_config" only through a
    branch marked DEPRECATED, and writes app_config back out. A key that
    survives on a deprecation branch is one release from being ignored
    without a word - and no --dry-run would show that the installed
    desktop ended up with no sound server."""
    out = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert out["app_config"]["audio_config"]["audio"] == "pipewire"
    assert "audio_config" not in out


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


# --- die geplante Einteilung, gegen archinstalls eigenen Vertrag -------
#
# WORAN DIESER ABSCHNITT MISST, UND WORAN NICHT
#     Nicht an archinstall selbst. Das Paket ist auf dieser Maschine
#     nicht installiert, sein lib/models/device.py beginnt mit
#     `import parted`, und DiskLayoutConfiguration.parse_arg ruft als
#     Erstes device_handler.get_device(<pfad>) - auf einer Maschine ohne
#     /dev/vda kommt None zurueck, und die Schleife ueberspringt die
#     ganze Einteilung, samt aller Pruefungen, um die es hier geht. Ein
#     Lauf gegen das echte archinstall wuerde also gruen melden, ohne
#     eine einzige Partition angesehen zu haben.
#
#     Gemessen wird stattdessen gegen eine ABSCHRIFT seiner Regeln, aus
#     archinstall 4.4-1 des angehefteten ALA-Schnappschusses 2026/08/04
#     (usr/lib/python3.14/site-packages/archinstall/lib/models/device.py,
#     DiskLayoutConfiguration.parse_arg). Jede Regel steht unten mit dem
#     Wortlaut ihrer Fehlermeldung, damit sich die Abschrift gegen die
#     Quelle halten laesst. Was diese Tests NICHT koennen: bemerken, dass
#     archinstall seine Regeln in einer neuen Fassung geaendert hat.

# Die Schluessel, die _PartitionModificationSerialization deklariert -
# abgeschrieben aus derselben Datei. Die ersten acht liest parse_arg mit
# dem Index (partition['status'] usw.), sind dort also Pflicht und kein
# Vorgabewert; flags, fs_type und btrfs gehen ueber .get().
ARCHINSTALL_PARTITION_KEYS = {
    "obj_id", "status", "type", "start", "size", "fs_type", "mountpoint",
    "mount_options", "flags", "btrfs", "dev_path",
}

# FilesystemType, StrEnum, gleiche Datei. FilesystemType(<wert>) wirft
# ValueError fuer alles andere.
ARCHINSTALL_FILESYSTEMS = {
    "btrfs", "ext2", "ext3", "ext4", "f2fs", "fat12", "fat16", "fat32",
    "ntfs", "xfs", "linux-swap",
}

# PartitionFlag.from_string() vergleicht gegen name.lower() und alias.
# Ein Name, den es nicht kennt, wird still verworfen ("Partition flag not
# supported") - also ohne Fehler und ohne ESP.
ARCHINSTALL_FLAGS = {"boot", "bls_boot", "esp", "linux-home", "swap"}

# ModificationStatus, gleiche Datei: EXIST = 'existing', der Rest ueber
# auto() kleingeschrieben.
ARCHINSTALL_STATUS = {"existing", "modify", "delete", "create"}

# PartitionType, StrEnum ueber auto(), plus _UNKNOWN = 'unknown'.
ARCHINSTALL_TYPES = {"boot", "primary", "unknown"}


def _mods(cfg: InstallConfig) -> list[dict]:
    out = to_archinstall_config(cfg, PackageSource.ONLINE)
    return out["disk_config"]["device_modifications"][0]["partitions"]


def _mib(entry: dict) -> int:
    """Der nackte Zahlenwert einer Groesse aus der Konfiguration.

    Nur sinnvoll, solange die Einheit MiB ist - was die Abschrift unten
    fuer jede anzulegende Partition eigens prueft, statt es hier
    stillschweigend anzunehmen.
    """
    return entry["value"]


def _archinstall_would_accept(partitions: list[dict], disk_size_bytes: int) -> list[str]:
    """archinstalls eigene Pruefungen, abgeschrieben. Leere Liste = nimmt es an."""
    problems: list[str] = []
    ordered = sorted(partitions, key=lambda p: _mib(p["start"]))

    for entry in ordered:
        if set(entry) != ARCHINSTALL_PARTITION_KEYS:
            problems.append(f"KeyError in parse_arg: {set(entry)}")
        if entry["status"] not in ARCHINSTALL_STATUS:
            problems.append(f"ModificationStatus({entry['status']!r})")
        if entry["type"] not in ARCHINSTALL_TYPES:
            problems.append(f"PartitionType({entry['type']!r})")
        if entry["fs_type"] is not None and entry["fs_type"] not in ARCHINSTALL_FILESYSTEMS:
            problems.append(f"FilesystemType({entry['fs_type']!r})")
        for flag in entry["flags"]:
            if flag not in ARCHINSTALL_FLAGS:
                problems.append(f"Partition flag not supported: {flag}")
        # PartitionModification.__post_init__: "If partition marked as
        # existing a path must be set" - gilt fuer existing, delete und
        # modify.
        if entry["status"] != "create" and not entry["dev_path"]:
            problems.append("If partition marked as existing a path must be set")

    creating = [e for e in ordered if e["status"] == "create"]
    if creating and not _mib(creating[0]["start"]) >= 1:
        problems.append("First partition must start at no less than 1 MiB")
    for previous, current in zip(ordered, ordered[1:]):
        if current["status"] != "create":
            continue
        if _mib(current["start"]) < _mib(previous["start"]) + _mib(previous["size"]):
            problems.append("Partitions overlap")
    for entry in creating:
        # Size.align() rundet auf volle MiB ab, und parse_arg wirft
        # "Partition is misaligned", wenn start oder length das nicht
        # schon sind. Eine Angabe in MiB ist immer ausgerichtet - was
        # hier geprueft wird, ist also, dass sie in MiB angegeben IST und
        # nicht in Sektoren oder Byte.
        if entry["start"]["unit"] != "MiB" or entry["size"]["unit"] != "MiB":
            problems.append("Partition is misaligned")
    if creating:
        last = creating[-1]
        end = _mib(last["start"]) + _mib(last["size"])
        # total_size.gpt_end() ist total - 1 MiB.
        if end > disk_size_bytes // (1024 * 1024) - 1:
            problems.append("Partition overlaps backup GPT header")
    return problems


def _with_layout(layout):
    cfg = _cfg()
    cfg.disk.layout = layout
    return cfg


def test_a_planned_layout_reaches_archinstall():
    """Ohne das waere die Partitionierungsseite eine Anzeige."""
    plan = [
        PlannedPartition(start_mib=1, size_mib=512, filesystem="fat32",
                         mountpoint="/boot", flags=("boot", "esp")),
        PlannedPartition(start_mib=513, size_mib=4096,
                         filesystem="linux-swap"),
        PlannedPartition(start_mib=4609, size_mib=8192, filesystem="btrfs",
                         mountpoint="/"),
    ]
    partitions = _mods(_with_layout(plan))
    assert [p["mountpoint"] for p in partitions] == ["/boot", None, "/"]
    assert [p["fs_type"] for p in partitions] == ["fat32", "linux-swap", "btrfs"]
    assert [p["start"]["value"] for p in partitions] == [1, 513, 4609]
    assert [p["size"]["value"] for p in partitions] == [512, 4096, 8192]


def test_the_planned_layout_is_one_archinstall_accepts():
    plan = [
        PlannedPartition(start_mib=1, size_mib=512, filesystem="fat32",
                         mountpoint="/boot", flags=("boot", "esp")),
        PlannedPartition(start_mib=513, size_mib=8192, filesystem="ext4",
                         mountpoint="/"),
    ]
    cfg = _with_layout(plan)
    assert _archinstall_would_accept(_mods(cfg), cfg.disk.size_bytes) == []


def test_the_suggestion_is_one_archinstall_accepts():
    """Der Weg ohne Oberflaeche: der Textassistent und jede
    Konfigurationsdatei ohne "layout" laufen hierueber."""
    cfg = _cfg()
    assert cfg.disk.layout == []
    assert _archinstall_would_accept(_mods(cfg), cfg.disk.size_bytes) == []


def test_the_transcription_of_archinstalls_rules_actually_bites():
    """Der Waechter seines eigenen Waechters.

    Eine Abschrift, die nichts ablehnt, meldet dasselbe Gruen wie eine
    richtige Konfiguration. Also drei Einteilungen, die archinstall
    nachweislich zurueckweist, jede mit dem Wortlaut aus seiner Quelle.
    """
    def entry(start, size, **rest):
        base = {
            "obj_id": "x", "status": "create", "type": "primary",
            "fs_type": "ext4", "mountpoint": "/", "mount_options": [],
            "flags": [], "btrfs": [], "dev_path": None,
            "start": {"value": start, "unit": "MiB", "sector_size": {}},
            "size": {"value": size, "unit": "MiB", "sector_size": {}},
        }
        return base | rest

    disk = 40 * 1024 ** 3
    assert "First partition must start at no less than 1 MiB" in \
        _archinstall_would_accept([entry(0, 1024)], disk)
    assert "Partitions overlap" in \
        _archinstall_would_accept([entry(1, 1024), entry(512, 1024)], disk)
    assert "Partition overlaps backup GPT header" in \
        _archinstall_would_accept([entry(1, 40 * 1024)], disk)
    assert "If partition marked as existing a path must be set" in \
        _archinstall_would_accept([entry(1, 1024, status="delete")], disk)
    in_sectors = entry(1, 1024)
    in_sectors["size"] = {"value": 2048, "unit": "sectors", "sector_size": {}}
    assert "Partition is misaligned" in _archinstall_would_accept(
        [in_sectors], disk)
    assert "FilesystemType('ntfs3')" in _archinstall_would_accept(
        [entry(1, 1024, fs_type="ntfs3")], disk)
    assert "Partition flag not supported: efi" in _archinstall_would_accept(
        [entry(1, 1024, flags=["efi"])], disk)


def test_every_partition_carries_exactly_the_keys_parse_arg_reads():
    """parse_arg greift auf acht davon mit dem Index zu. Ein fehlender
    Schluessel ist dort ein KeyError - mitten in einer Installation, die
    ihre Konfiguration erst beim Laden zu Gesicht bekommt."""
    for partition in _mods(_cfg()):
        assert set(partition) == ARCHINSTALL_PARTITION_KEYS


def test_every_partition_is_created_and_has_no_device_path():
    """Die anderen drei Zustaende verlangen umgekehrt ein gesetztes
    dev_path. Warum ZepOS ausschliesslich anlegt, steht in
    installer/core/layout.py."""
    for partition in _mods(_cfg()):
        assert partition["status"] == "create"
        assert partition["dev_path"] is None


def test_the_esp_is_a_primary_partition_and_not_type_boot():
    """PartitionType.BOOT setzt parteds PARTITION_BOOT-Code, den eine
    GPT-Platte nicht kennt. Woran archinstall die EFI-Partition erkennt,
    sind die Flaggen: get_efi_partition() filtert auf is_efi()."""
    esp = _mods(_cfg())[0]
    assert esp["type"] == "primary"
    assert "esp" in esp["flags"]


def test_a_swap_partition_gets_no_mountpoint():
    """`Path(partition['mountpoint']) if partition['mountpoint']` - ein
    leerer String waere hier dasselbe wie None, aber None ist das, was
    archinstall selbst schreibt (PartitionModification.json)."""
    plan = [
        PlannedPartition(start_mib=1, size_mib=512, filesystem="fat32",
                         mountpoint="/boot", flags=("boot", "esp")),
        PlannedPartition(start_mib=513, size_mib=4096,
                         filesystem="linux-swap"),
        PlannedPartition(start_mib=4609, size_mib=8192, filesystem="ext4",
                         mountpoint="/"),
    ]
    assert _mods(_with_layout(plan))[1]["mountpoint"] is None


def test_a_layout_without_a_root_never_reaches_archinstall():
    """Die zweite Pruefung, und sie ist nicht ueberfluessig: dies ist der
    Weg, den auch `zepos-install --config datei.json` nimmt, und den hat
    keine Oberflaeche geprueft. archinstalls eigene Antwort darauf kaeme
    als "Could not detect root at mountpoint" - nachdem es die Platte
    geloescht hat."""
    plan = [PlannedPartition(start_mib=1, size_mib=512, filesystem="fat32",
                             mountpoint="/boot", flags=("boot", "esp"))]
    with pytest.raises(ValueError, match="root partition"):
        to_archinstall_config(_with_layout(plan), PackageSource.ONLINE)


def test_an_overlapping_layout_never_reaches_archinstall():
    plan = [
        PlannedPartition(start_mib=1, size_mib=1024, filesystem="fat32",
                         mountpoint="/boot", flags=("boot", "esp")),
        PlannedPartition(start_mib=512, size_mib=8192, filesystem="ext4",
                         mountpoint="/"),
    ]
    with pytest.raises(ValueError, match="overlap"):
        to_archinstall_config(_with_layout(plan), PackageSource.ONLINE)


def test_a_layout_larger_than_the_disk_never_reaches_archinstall():
    plan = [
        PlannedPartition(start_mib=1, size_mib=512, filesystem="fat32",
                         mountpoint="/boot", flags=("boot", "esp")),
        PlannedPartition(start_mib=513, size_mib=64 * 1024, filesystem="ext4",
                         mountpoint="/"),
    ]
    with pytest.raises(ValueError, match="past the end"):
        to_archinstall_config(_with_layout(plan), PackageSource.ONLINE)


def test_the_layout_survives_a_round_trip_through_the_config_file():
    """`zepos-install --config datei.json` laedt eine InstallConfig aus
    JSON. asdict() macht aus jeder PlannedPartition ein dict und aus dem
    Tupel in flags eine Liste - kaemen die so zurueck, haette
    installer.core.translate ein dict ohne .size_mib in der Hand, und
    zwar in dem Augenblick, in dem eine unbeaufsichtigte Installation die
    Platte schon fuer sich hat."""
    plan = [
        PlannedPartition(start_mib=1, size_mib=512, filesystem="fat32",
                         mountpoint="/boot", flags=("boot", "esp")),
        PlannedPartition(start_mib=513, size_mib=8192, filesystem="ext4",
                         mountpoint="/"),
    ]
    cfg = _with_layout(plan)
    restored = InstallConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
    assert restored.disk.layout == plan
    # obj_id ist bei jedem Aufruf eine neue UUID (und muss es sein: sie
    # ist der Schluessel, unter dem archinstall die Partitionen
    # auseinanderhaelt), also bleibt sie beim Vergleich draussen.
    without_ids = [
        [{k: v for k, v in entry.items() if k != "obj_id"} for entry in mods]
        for mods in (_mods(restored), _mods(cfg))
    ]
    assert without_ids[0] == without_ids[1]
