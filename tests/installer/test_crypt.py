# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Plattenverschluesselung, gegen archinstalls echten Vertrag.

WAS DIESE DATEI ANDERS MACHT ALS EINE PRUEFUNG DES HAKENS
    Die naheliegende Zusicherung waere: "encrypt=True, also steht
    disk_encryption in der Konfiguration". Die ist richtig und faengt
    genau den Fehler NICHT, der zaehlt.

    archinstall 4.4 lehnt eine Verschluesselung ohne Passphrase nicht
    ab. DiskEncryption.parse_arg() gibt None zurueck (`if not password:
    return None`, lib/models/device.py Zeile 1537), disk_encryption
    bleibt None, und die Installation laeuft durch: Rueckgabewert 0, ein
    startendes System, eine Platte im Klartext. Wer nur prueft, ob der
    Haken gesetzt war, hat diesen Ausgang gruen gemeldet.

    Deshalb steht unten _archinstall_would_encrypt() - archinstalls
    eigene Entscheidungskette, Zeile fuer Zeile nachgebaut und mit
    Fundstellen belegt -, und die scharfen Zusicherungen fragen DIESE
    Funktion und nicht das Feld.

    Nachgebaut und nicht importiert, weil archinstall in .venv nicht
    liegt und auf dem Zielmedium eine andere Fassung liegen kann als
    hier. Was hier steht, ist eine Lesung des angehefteten
    ALA-Schnappschusses 2026/08/04 (archinstall 4.4-1) und sagt das auch:
    ein Vertrag, der sich aendert, muss hier auffallen.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from installer.core.crypt import (
    CPUINFO_PATH, ENCRYPTION_TYPE_LUKS, MIN_PASSPHRASE_LENGTH,
    accelerator_note, cpu_has_aes, effective_layout, encrypted_partitions,
    is_encryptable, keyboard_note, loss_warning, passphrase_error,
    plaintext_partitions, plaintext_warnings, unlock_note,
)
from installer.core.layout import (
    ESP_FILESYSTEM, ESP_FLAGS, ESP_MOUNTPOINT, PlannedPartition,
    SWAP_FILESYSTEM, suggested_layout,
)
from installer.core.model import DiskChoice, InstallConfig, UserAccount
from installer.core.source import PackageSource
from installer.core.translate import to_archinstall_config, to_archinstall_creds
from installer.core.validate import validate

DISK_BYTES = 64 * 1024**3


def _cfg(**disk_kwargs) -> InstallConfig:
    disk = dict(device="/dev/vda", wipe=True, filesystem="ext4",
                size_bytes=DISK_BYTES)
    disk.update(disk_kwargs)
    return InstallConfig(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(**disk),
        users=[UserAccount(username="lars", password="langgenug", sudo=True)],
        root_password="rootlanggenug",
    )


PASSPHRASE = "eine-lange-passphrase"


def _encrypted_cfg(**disk_kwargs) -> InstallConfig:
    return _cfg(encrypt=True, passphrase=PASSPHRASE, **disk_kwargs)


# --- archinstalls eigene Entscheidung, nachgebaut ----------------------


def _merged(cfg: InstallConfig) -> dict:
    """config.json und creds.json in EIN Woerterbuch, so wie archinstall
    sie zusammenlegt.

    ArgumentHandler._parse_config(): `config.update(json.loads(
    config_data))` und danach `config.update(json_data)` fuer die
    Zugangsdaten (lib/args.py, Zeile 692-703). Die beiden Dateien sind
    fuer archinstall also EINE Konfiguration - und genau deshalb kann der
    Verschluesselungsblock in der einen stehen und die Passphrase in der
    anderen.
    """
    return {
        **to_archinstall_config(cfg, PackageSource.ONLINE),
        **to_archinstall_creds(cfg, hasher=lambda plain: f"hash:{plain}"),
    }


def _archinstall_would_encrypt(merged: dict) -> bool:
    """Ob archinstall aus dieser Konfiguration wirklich eine
    verschluesselte Platte machen wuerde.

    Die Kette, in der Reihenfolge, in der archinstall sie geht:

      1. ArchConfig.from_config(): `enc_password = args_config.get(
         'encryption_password', '')`, dann `password = Password(...) if
         enc_password else None` (lib/args.py, Zeile 270-271). Ein
         leerer oder fehlender Wert wird zu None.
      2. DiskLayoutConfiguration.parse_arg(): nur wenn
         `disk_config.get('disk_encryption')` nicht None ist, wird
         ueberhaupt DiskEncryption.parse_arg gerufen (lib/models/
         device.py, Zeile 228-229).
      3. DiskEncryption.parse_arg(): `if not password: return None` -
         DAS ist die stille Abschaltung (Zeile 1537-1538).
      4. Danach werden die Partitionen ueber ihre obj_id gesucht:
         `if part.obj_id in disk_encryption.get('partitions', [])`
         (Zeile 1541-1544). Was sich nicht findet, faellt weg.
      5. DiskEncryption.__post_init__: `if self.encryption_type in
         [LUKS, LVM_ON_LUKS] and not self.partitions: raise ValueError`
         (Zeile 1483-1484). Eine leere Trefferliste ist also ein
         Abbruch, kein stilles Nichts.

    Gibt True zurueck, wenn am Ende ein DiskEncryption mit Partitionen
    steht. Wirft, wo archinstall wirft.
    """
    disk_config = merged.get("disk_config", {})
    enc = disk_config.get("disk_encryption")
    if enc is None:
        return False
    if not merged.get("encryption_password", ""):
        return False
    known = {
        part["obj_id"]
        for mod in disk_config.get("device_modifications", [])
        for part in mod.get("partitions", [])
    }
    matched = [obj_id for obj_id in enc["partitions"] if obj_id in known]
    if enc["encryption_type"] in ("luks", "lvm_on_luks") and not matched:
        raise ValueError(
            "Luks or LvmOnLuks encryption require partitions to be defined")
    return bool(matched)


def _encrypted_mountpoints(merged: dict) -> set[str]:
    """Welche EINHAENGEPUNKTE nach archinstalls Zuordnung verschluesselt
    waeren - nicht welche obj_ids in der Liste stehen.

    Der Unterschied ist der Punkt: eine obj_id ist eine Zeichenkette, die
    zu allem passen kann. Was zaehlt, ist, welche Partition sie
    bezeichnet.
    """
    disk_config = merged["disk_config"]
    wanted = set(disk_config["disk_encryption"]["partitions"])
    return {
        part["mountpoint"] or f"swap:{part['fs_type']}"
        for mod in disk_config["device_modifications"]
        for part in mod["partitions"]
        if part["obj_id"] in wanted
    }


# --- die scharfen Zusicherungen ---------------------------------------


def test_an_encrypted_config_really_is_encrypted_for_archinstall():
    """Die eine Zusicherung, um die es geht.

    Nicht "disk_encryption steht da", sondern "archinstall macht daraus
    eine verschluesselte Platte" - gemessen an seiner eigenen
    Entscheidungskette.
    """
    assert _archinstall_would_encrypt(_merged(_encrypted_cfg())) is True


def test_without_a_passphrase_nothing_is_written_at_all():
    """Und der Gegenbeweis, an genau der Stelle, an der archinstall
    stillschweigend abschalten wuerde.

    Die Konfiguration entsteht gar nicht erst: to_archinstall_config()
    weigert sich. Waere sie entstanden, haette
    _archinstall_would_encrypt() False gesagt und die Installation waere
    mit Rueckgabewert 0 und einer offenen Platte durchgelaufen.
    """
    cfg = _cfg(encrypt=True, passphrase="")
    with pytest.raises(ValueError) as refusal:
        to_archinstall_config(cfg, PackageSource.ONLINE)
    assert "passphrase" in str(refusal.value)

    with pytest.raises(ValueError):
        to_archinstall_creds(cfg, hasher=lambda plain: "x")


def test_a_config_that_lost_its_passphrase_would_not_encrypt():
    """Warum die Weigerung oben noetig ist, an einem gebauten Beispiel.

    Hier wird von Hand hergestellt, was eine vergessene Zeile in
    to_archinstall_creds() hergestellt haette: der Verschluesselungsblock
    in der Konfiguration, kein encryption_password daneben. archinstall
    laeuft damit durch - und verschluesselt nicht.

    Das ist die Probe darauf, dass _archinstall_would_encrypt() ueberhaupt
    etwas messen kann. Ohne sie waere eine Funktion, die immer True sagt,
    von den beiden Tests darueber nicht zu unterscheiden.
    """
    merged = _merged(_encrypted_cfg())
    del merged["encryption_password"]
    assert _archinstall_would_encrypt(merged) is False


def test_a_config_whose_object_ids_do_not_match_would_break_the_run():
    """Und der zweite Weg, es falsch zu machen: eine obj_id, die zu
    keiner Partition gehoert.

    archinstall findet dann nichts, und DiskEncryption.__post_init__
    wirft mitten im Lauf. Die Zusicherung ist, dass unsere eigenen
    obj_ids das NICHT tun - was der Test darunter prueft.
    """
    merged = _merged(_encrypted_cfg())
    merged["disk_config"]["disk_encryption"]["partitions"] = ["nicht-vorhanden"]
    with pytest.raises(ValueError):
        _archinstall_would_encrypt(merged)


def test_every_encrypted_object_id_names_a_partition_that_exists():
    """Die obj_ids sind uuid4 und werden je Aufruf neu erzeugt. Dass die
    Liste in disk_encryption dieselben nennt, die auch in
    device_modifications stehen, ist deshalb keine Selbstverstaendlichkeit
    sondern die Aufgabe von translate._planned()."""
    config = to_archinstall_config(_encrypted_cfg(), PackageSource.ONLINE)
    disk_config = config["disk_config"]
    known = {
        part["obj_id"]
        for mod in disk_config["device_modifications"]
        for part in mod["partitions"]
    }
    wanted = disk_config["disk_encryption"]["partitions"]

    assert wanted, "die Liste der verschluesselten Partitionen ist leer"
    assert set(wanted) <= known
    assert len(set(wanted)) == len(wanted), "eine obj_id steht doppelt darin"


def test_the_root_is_encrypted_and_the_efi_partition_is_not():
    """Die Aufteilung, auf die es beim Start ankommt.

    Die Wurzel MUSS verschluesselt sein, sonst war die ganze Uebung
    umsonst. Die EFI-Systempartition darf es NICHT sein: die Firmware
    liest sie, bevor irgendetwas entschluesseln koennte, und bei ZepOS
    liegen dort auch Kernel und Initramfs (ESP_MOUNTPOINT ist /boot).
    Eine verschluesselte ESP ist eine Maschine vor einem leeren
    Startmenue.
    """
    encrypted = _encrypted_mountpoints(_merged(_encrypted_cfg()))
    assert "/" in encrypted
    assert ESP_MOUNTPOINT not in encrypted


def test_the_encryption_type_is_the_string_archinstall_accepts():
    """'luks' und nicht 'LUKS'. EncryptionType ist eine StrEnum mit
    auto(), deren Werte kleingeschrieben sind; ein anderer Wert ist ein
    ValueError aus EncryptionType(...) beim Laden der Konfiguration."""
    config = to_archinstall_config(_encrypted_cfg(), PackageSource.ONLINE)
    assert ENCRYPTION_TYPE_LUKS == "luks"
    assert config["disk_config"]["disk_encryption"]["encryption_type"] == "luks"


def test_the_encryption_block_carries_every_required_key():
    """_DiskEncryptionSerialization verlangt encryption_type, partitions
    und lvm_volumes; hsm_device und iter_time sind NotRequired."""
    block = to_archinstall_config(
        _encrypted_cfg(), PackageSource.ONLINE)["disk_config"]["disk_encryption"]
    assert set(block) == {"encryption_type", "partitions", "lvm_volumes"}
    assert block["lvm_volumes"] == []


def test_no_iter_time_is_written_so_archinstalls_default_applies():
    """Gemessen am 12.08.2026: archinstalls DEFAULT_ITER_TIME von 10000 ms
    kostet rund zehn Sekunden je Entsperrung (9,98 / 10,39 / 10,82 s auf
    einem Core Ultra 7 255U), cryptsetups eigene 2000 ms rund zweieinhalb
    (2,24 / 2,53 / 2,59 s). ZepOS nimmt die hoehere Vorgabe - siehe den
    Kopf von installer/core/crypt.py - und schreibt sie deshalb NICHT
    hin: DiskEncryption.json() laesst den Schluessel bei der Vorgabe
    selbst weg."""
    block = to_archinstall_config(
        _encrypted_cfg(), PackageSource.ONLINE)["disk_config"]["disk_encryption"]
    assert "iter_time" not in block


def test_the_encryption_block_sits_inside_disk_config_not_at_the_top():
    """Die oberste Ebene ist archinstalls Uebergangszweig, ueber dem
    woertlich 'DEPRECATED / backwards compatibility' steht (lib/args.py,
    Zeile 275). Ein Schluessel, den nur ein solcher Zweig am Leben
    haelt, ist eine Fassung davon entfernt, ignoriert zu werden - und
    ignoriert heisst hier: unverschluesselt."""
    config = to_archinstall_config(_encrypted_cfg(), PackageSource.ONLINE)
    assert "disk_encryption" in config["disk_config"]
    assert "disk_encryption" not in config


def test_the_passphrase_travels_in_the_credentials_and_not_the_config():
    """Im Klartext, weil cryptsetup die Zeichen selbst braucht - und
    deshalb in der Datei, die installer.core.runner mit Modus 0600
    schreibt und nach der Installation loescht."""
    cfg = _encrypted_cfg()
    creds = to_archinstall_creds(cfg, hasher=lambda plain: f"hash:{plain}")
    config = to_archinstall_config(cfg, PackageSource.ONLINE)

    assert creds["encryption_password"] == PASSPHRASE
    assert PASSPHRASE not in repr(config)


def test_no_passphrase_key_at_all_when_nothing_is_encrypted():
    """Kein leerer Wert. Ein Schluessel, der manchmal '' bedeutet und
    manchmal 'nichts angefordert', ist einer, bei dem niemand mehr sagen
    kann, was gemeint war - und '' ist ausgerechnet die Angabe, mit der
    archinstall stillschweigend abschaltet."""
    creds = to_archinstall_creds(_cfg(), hasher=lambda plain: "x")
    assert "encryption_password" not in creds


def test_an_unencrypted_config_is_byte_for_byte_what_it_was():
    """Die Aenderung darf den bestehenden Weg nicht anfassen."""
    config = to_archinstall_config(_cfg(), PackageSource.ONLINE)
    assert "disk_encryption" not in config["disk_config"]
    assert set(config["disk_config"]) == {
        "config_type", "device_modifications"}
    assert config["disk_config"]["config_type"] == "manual_partitioning"


def test_an_encrypted_config_still_carries_the_keyboard_layout():
    """DIE ZUSICHERUNG, DIE EINE PLATTE RETTET.

    Die Passphrase wird beim Start an einer Textzeile der Initramfs
    abgefragt, und der `keymap`-Haken laedt dafuer /etc/vconsole.conf.
    archinstall schreibt diese Datei aus locale_config.kb_layout
    (Installer.mkinitcpio() ersetzt ohne HSM `sd-vconsole` durch
    `keymap consolefont`, und der Haken liest KEYMAP).

    Faellt kb_layout weg, tippt ein deutscher Nutzer seine Passphrase auf
    einer amerikanischen Belegung ein - y und z vertauscht, keine
    Umlaute - und kommt an seine eigene Platte nicht mehr heran. Dieses
    Projekt hatte denselben Fehler schon einmal, im Live-Compositor
    (XKB_DEFAULT_LAYOUT, siehe iso/test-boot.py); dort kostete er ein
    Konto, hier kostet er alles.
    """
    config = to_archinstall_config(_encrypted_cfg(), PackageSource.ONLINE)
    assert config["locale_config"]["kb_layout"] == "de-latin1"


# --- welche Partition darf, welche nicht -------------------------------


def _swap(start_mib: int = 2048) -> PlannedPartition:
    return PlannedPartition(
        start_mib=start_mib, size_mib=1024, filesystem=SWAP_FILESYSTEM)


def _esp() -> PlannedPartition:
    return PlannedPartition(
        start_mib=1, size_mib=512, filesystem=ESP_FILESYSTEM,
        mountpoint=ESP_MOUNTPOINT, flags=ESP_FLAGS)


def _root(size_mib: int = 8192) -> PlannedPartition:
    return PlannedPartition(
        start_mib=513, size_mib=size_mib, filesystem="ext4", mountpoint="/")


def test_the_efi_partition_is_never_encryptable():
    assert is_encryptable(_esp()) is False


def test_swap_is_never_encryptable():
    """archinstalls eigene Regel: select_partitions_to_encrypt() nimmt
    `p.mountpoint != Path('/boot') and not p.is_swap()`."""
    assert is_encryptable(_swap()) is False


def test_the_root_and_a_home_are_encryptable():
    assert is_encryptable(_root()) is True
    assert is_encryptable(PlannedPartition(
        start_mib=9000, size_mib=4096, filesystem="ext4",
        mountpoint="/home")) is True


def test_the_two_lists_together_are_the_whole_layout():
    """encrypted_partitions() und plaintext_partitions() teilen die
    Einteilung auf: keine Partition in beiden, keine in keiner.

    Eine, die in keiner der beiden steht, waere eine, ueber die die Seite
    schweigt - der Nutzer saehe weder "wird verschluesselt" noch "bleibt
    offen" und muesste raten.
    """
    layout = [_esp(), _root(), _swap(9000)]
    encrypted = encrypted_partitions(layout)
    plaintext = plaintext_partitions(layout)

    assert encrypted == [_root()]
    assert plaintext == [_esp(), _swap(9000)]
    # Zusammen die ganze Einteilung, und keine doppelt.
    assert sorted(encrypted + plaintext, key=lambda p: p.start_mib) == layout
    assert not set(encrypted) & set(plaintext)


def test_a_swap_partition_makes_it_into_the_encrypted_config_untouched():
    """Und die Folge davon in der fertigen Konfiguration: die
    Auslagerung wird angelegt, aber nicht verschluesselt. Das ist eine
    Luecke, und plaintext_warnings() spricht sie aus."""
    layout = [_esp(), _root(), _swap(9000)]
    merged = _merged(_encrypted_cfg(layout=layout))
    encrypted = _encrypted_mountpoints(merged)

    assert "/" in encrypted
    assert f"swap:{SWAP_FILESYSTEM}" not in encrypted
    assert any("swap" in warning.lower() or "Auslagerung" in warning
               for warning in plaintext_warnings(layout))


def test_plaintext_warnings_always_name_the_efi_partition():
    """Auch wenn sie harmlos ist. Wer nicht weiss, dass sie offen ist,
    wundert sich, warum eine 'vollverschluesselte' Platte einen lesbaren
    Anfang hat."""
    warnings = plaintext_warnings(suggested_layout(DISK_BYTES))
    assert len(warnings) == 1
    assert "EFI" in warnings[0]


# --- die Einteilung, wenn niemand eine geplant hat ---------------------


def test_an_empty_layout_falls_back_to_the_suggestion():
    """Leer heisst 'niemand hat sich geaeussert', nicht 'keine
    Partitionen' - dieselbe Unterscheidung, die DiskChoice.layout
    macht."""
    assert effective_layout([], DISK_BYTES) == suggested_layout(DISK_BYTES)


def test_a_planned_layout_is_used_as_it_is():
    layout = [_esp(), _root()]
    assert effective_layout(layout, DISK_BYTES) == layout


def test_the_text_interfaces_config_encrypts_its_root_too():
    """Der Textassistent plant keine Einteilung und schickt layout=[].
    Ohne effective_layout() haette validate() dort 'nichts zu
    verschluesseln' gemeldet und translate() haette geworfen - fuer die
    gewoehnlichste Konfiguration, die es gibt."""
    cfg = _encrypted_cfg(layout=[])
    assert validate(cfg) == []
    assert _archinstall_would_encrypt(_merged(cfg)) is True


# --- die Passphrase -----------------------------------------------------


def test_a_short_passphrase_is_refused_and_says_how_long():
    problem = passphrase_error("kurz", "kurz")
    assert problem
    assert str(MIN_PASSPHRASE_LENGTH) in problem


def test_the_minimum_is_stricter_than_the_login_password():
    """Und das ist Absicht, nicht Zufall: ein Anmeldepasswort verteidigt
    ein laufendes System hinter einer Maske, die zaehlt und wartet; eine
    LUKS-Passphrase verteidigt eine Platte, die jemand in der Hand hat
    und offline durchprobieren kann. Der ganze Grund steht in
    installer/core/crypt.py."""
    from installer.core.validate import MIN_PASSWORD_LENGTH
    assert MIN_PASSPHRASE_LENGTH > MIN_PASSWORD_LENGTH


def test_two_different_entries_are_refused():
    problem = passphrase_error("langgenug1234", "langgenug1235")
    assert problem
    assert "match" in problem or "überein" in problem


def test_a_long_matching_passphrase_is_accepted():
    assert passphrase_error("langgenug1234", "langgenug1234") == ""


def test_the_length_rule_is_checked_before_the_match_rule():
    """Zwei gleiche, zu kurze Eingaben sind zu kurz und nicht 'stimmen
    ueberein'. Die Reihenfolge ist das, worauf sich der Textassistent
    verlaesst, wenn er den Wert gegen sich selbst prueft, um nicht
    zweimal nach einer zu kurzen Passphrase zu fragen."""
    assert passphrase_error("kurz", "kurz") == passphrase_error("kurz", "kurz")
    assert str(MIN_PASSPHRASE_LENGTH) in passphrase_error("kurz", "anders")


# --- was es kostet ------------------------------------------------------


def test_aes_is_found_in_a_flags_line(tmp_path: Path):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        "processor\t: 0\n"
        "model name\t: Intel(R) Core(TM) Ultra 7 255U\n"
        "flags\t\t: fpu vme de pse tsc aes avx2 sha_ni\n",
        encoding="utf-8")
    assert cpu_has_aes(cpuinfo=cpuinfo) is True
    assert accelerator_note(cpuinfo=cpuinfo) == ""


def test_a_processor_without_aes_gets_a_warning(tmp_path: Path):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        "processor\t: 0\n"
        "flags\t\t: fpu vme de pse tsc\n", encoding="utf-8")
    assert cpu_has_aes(cpuinfo=cpuinfo) is False
    assert "AES" in accelerator_note(cpuinfo=cpuinfo)


def test_aes_in_a_model_name_is_not_a_flag(tmp_path: Path):
    """Ein `in`-Test auf die ganze Datei faende 'aes' auch hier. Die
    Flags stehen als leerzeichengetrennte Liste hinter 'flags:', und nur
    dort wird gesucht."""
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        "model name\t: Praesidium aes 9000\n"
        "flags\t\t: fpu vme de pse tsc\n", encoding="utf-8")
    assert cpu_has_aes(cpuinfo=cpuinfo) is False


def test_a_substring_of_a_flag_is_not_the_flag(tmp_path: Path):
    """'aes' ist nicht 'aeskeygen' und nicht 'vaes'."""
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("flags\t\t: fpu vaes aeskeygen\n", encoding="utf-8")
    assert cpu_has_aes(cpuinfo=cpuinfo) is False


def test_an_unreadable_cpuinfo_answers_pessimistically(tmp_path: Path):
    """Eine Warnung zu viel ist ein Satz zu viel; eine Warnung zu wenig
    ist eine Maschine, die nach der Installation unerklaerlich langsam
    ist."""
    assert cpu_has_aes(cpuinfo=tmp_path / "gibt-es-nicht") is False


def test_the_default_path_is_proc_cpuinfo():
    assert CPUINFO_PATH == Path("/proc/cpuinfo")


# --- die Warnungen selbst ----------------------------------------------


def test_the_loss_warning_says_that_nothing_can_be_recovered():
    warning = loss_warning()
    assert "reset" in warning.lower()
    assert "lost" in warning.lower() or "verloren" in warning.lower()


def test_the_unlock_note_names_the_measured_wait():
    """Zehn Sekunden, gemessen. Eine Maschine, die nach der Installation
    zehn Sekunden laenger braucht, sieht ohne diesen Satz kaputt aus."""
    assert "ten seconds" in unlock_note() or "zehn Sekunden" in unlock_note()


def test_the_keyboard_note_warns_about_the_layout():
    note = keyboard_note()
    assert "keyboard layout" in note or "Tastaturbelegung" in note
