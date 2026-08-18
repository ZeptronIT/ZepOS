# SPDX-License-Identifier: GPL-3.0-or-later
"""Secure Boot: die beiden Formate, ohne die die Messung nichts misst.

WARUM DIESE DATEI EXISTIERT
    `./iso/test-boot.py --scenario secure-boot` bringt ein Bild mit, auf
    dem "Access Denied -- rejected probably by Secure Boot" steht. Dieses
    Bild ist nur so viel wert wie der Aufbau, der es erzeugt hat, und der
    Aufbau steht auf zwei Datenformaten, die beide still falsch sein
    koennen:

      * dem UEFI-Variablenspeicher. Schreibt iso/secureboot.py ihn
        falsch, dann findet OVMF keinen Plattformschluessel, bleibt im
        Setup Mode und prueft NICHTS - und der Lauf meldet dann, dass das
        Medium unter Secure Boot startet. Ein Fehler, der wie ein Erfolg
        aussieht.
      * der PE-Signaturtabelle. Liest certificate_table() das falsche
        Feld, dann meldet inspect "signiert" ueber eine Datei ohne
        Signatur, oder umgekehrt.

    Der zweite Fehler waere in einem Lauf sichtbar, der erste NICHT -
    und genau deshalb wird hier der Speicher zurueckgelesen statt
    geglaubt.

WARUM DIE VORLAGE HIER GEBAUT WIRD UND NICHT AUS /usr/share KOMMT
    Damit die Pruefung auf einer Maschine ohne edk2-ovmf laeuft, und weil
    eine selbstgebaute Vorlage die Grenzfaelle enthaelt, die die
    ausgelieferte nicht hat: einen Speicher, der zu klein ist, einen mit
    falscher Kennung, einen mit einem Kopf anderer Laenge. Ein Test gegen
    die eine Datei, die zufaellig installiert ist, prueft eine Datei und
    kein Format.

    Ein zusaetzlicher Test nimmt trotzdem die echte, wenn sie da ist.
    Ein Format, das nur die eigene Vorlage liest, waere die andere
    Haelfte desselben Fehlers.
"""
from __future__ import annotations

import importlib.util
import struct
import sys
import uuid
from pathlib import Path

import pytest

ISO = Path(__file__).resolve().parents[2] / "iso"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ISO / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


secureboot = _load("zepos_secureboot", "secureboot.py")
test_boot = _load("zepos_test_boot_secure", "test-boot.py")


# --------------------------------------------------------------------
# Eine Vorlage, wie OVMF sie ausliefert
# --------------------------------------------------------------------
def make_template(store_bytes: int = 0x10000, header_length: int = 72,
                  guid: uuid.UUID | None = None,
                  form: int = secureboot.VARIABLE_STORE_FORMATTED,
                  state: int = secureboot.VARIABLE_STORE_HEALTHY) -> bytes:
    """Ein EFI_FIRMWARE_VOLUME_HEADER mit leerem Variablenspeicher dahinter.

    Die Felder, die iso/secureboot.py liest, und Nullen fuer den Rest -
    OVMF liest hier mehr, dieser Test nicht, und ein nachgebauter
    Vollstaendigkeitsanspruch waere eine zweite Fehlerquelle.
    """
    volume = bytearray(header_length + store_bytes)
    volume[40:44] = secureboot.FV_SIGNATURE
    struct.pack_into("<Q", volume, 32, len(volume))          # FvLength
    struct.pack_into("<H", volume, 48, header_length)        # HeaderLength
    volume[header_length:header_length + 16] = (
        guid or secureboot.AUTHENTICATED_VARIABLE_STORE_GUID).bytes_le
    struct.pack_into("<IBBHI", volume, header_length + 16,
                     store_bytes, form, state, 0, 0)
    # Der freie Bereich eines Flash-Speichers ist geloescht, nicht null.
    for index in range(header_length + 16 + 12, len(volume)):
        volume[index] = 0xFF
    return bytes(volume)


CERTIFICATE = bytes(range(256)) * 3        # 768 Byte "Zertifikat"


# --------------------------------------------------------------------
# Der Variablenspeicher
# --------------------------------------------------------------------
def test_enroll_writes_the_three_variables_a_firmware_reads():
    """PK, KEK und db, und jede unter ihrer eigenen Kennung.

    Die Kennungen sind der Teil, den man nicht sieht und der alles
    entscheidet: eine "db" unter EFI_GLOBAL_VARIABLE ist fuer die
    Firmware eine andere Variable als die db, in der sie nachsieht, und
    ein Speicher mit dieser Verwechslung sieht in jeder Auflistung
    richtig aus.
    """
    store = secureboot.enroll(make_template(), CERTIFICATE)
    found = secureboot.read_variables(store)

    assert [entry["name"] for entry in found] == ["PK", "KEK", "db"]
    assert found[0]["vendor"] == secureboot.EFI_GLOBAL_VARIABLE_GUID
    assert found[1]["vendor"] == secureboot.EFI_GLOBAL_VARIABLE_GUID
    assert found[2]["vendor"] == secureboot.EFI_IMAGE_SECURITY_DATABASE_GUID


def test_every_enrolled_variable_is_time_based_authenticated():
    """Ohne die Flagge 0x20 zaehlt der Plattformschluessel nicht.

    AuthVariableLib entscheidet an genau diesem Bit, ob ein Eintrag eine
    authentifizierte Variable ist. Ohne es findet die Firmware kein PK,
    bleibt im Setup Mode - und der Lauf meldet, dass das Medium unter
    Secure Boot startet. Das ist der eine Fehler, den kein QEMU-Lauf als
    Fehler zeigen wuerde.
    """
    found = secureboot.read_variables(
        secureboot.enroll(make_template(), CERTIFICATE))
    for entry in found:
        assert entry["attributes"] == 0x27, entry["name"]
        assert entry["attributes"] & 0x20, entry["name"]
        assert entry["state"] == secureboot.VAR_ADDED, entry["name"]


def test_the_enrolled_data_is_a_signature_list_around_the_certificate():
    """Das Zertifikat steht in einer EFI_SIGNATURE_LIST, nicht nackt da.

    Nachgerechnet statt nachgesehen: eine Firmware liest SignatureSize
    und springt damit weiter, also muss die Zahl zu dem passen, was
    dahinter steht. Eine um sechzehn Byte falsche Zahl - genau die Groesse
    der Eigentuemerkennung - ergibt eine Liste, die sich lesen laesst und
    ein Zertifikat, das um sechzehn Byte verschoben ist.
    """
    data = secureboot.read_variables(
        secureboot.enroll(make_template(), CERTIFICATE))[0]["data"]

    assert uuid.UUID(bytes_le=data[:16]) == secureboot.EFI_CERT_X509_GUID
    list_size, header_size, signature_size = struct.unpack_from("<III", data, 16)
    assert list_size == len(data)
    assert header_size == 0
    assert signature_size == 16 + len(CERTIFICATE)
    assert uuid.UUID(bytes_le=data[28:44]) == secureboot.ZEPOS_SIGNATURE_OWNER
    assert data[44:] == CERTIFICATE


def test_records_are_aligned_to_four_bytes():
    """Ein Eintrag ungerader Laenge darf den naechsten nicht verschieben.

    edk2 rundet jeden Eintrag auf HEADER_ALIGNMENT auf. Ohne das liest
    die Firmware den zweiten Eintrag an einer Stelle, an der kein
    StartId steht, haelt den Speicher fuer zu Ende und findet KEK und db
    nicht mehr - und das faellt nur auf, wenn das Zertifikat zufaellig
    eine Laenge hat, die nicht durch vier teilbar ist.
    """
    odd = secureboot.enroll(make_template(), CERTIFICATE + b"\x01")
    assert [entry["name"] for entry in secureboot.read_variables(odd)] == \
        ["PK", "KEK", "db"]

    record = secureboot.variable_record("PK", secureboot.EFI_GLOBAL_VARIABLE_GUID,
                                        b"\x00" * 5)
    assert len(record) % secureboot.HEADER_ALIGNMENT == 0


def test_enroll_refuses_a_store_that_already_has_variables():
    once = secureboot.enroll(make_template(), CERTIFICATE)
    with pytest.raises(ValueError, match="bereits Variablen"):
        secureboot.enroll(once, CERTIFICATE)


def test_enroll_refuses_a_store_too_small_for_the_three_records():
    with pytest.raises(ValueError, match="Byte, im"):
        secureboot.enroll(make_template(store_bytes=512), CERTIFICATE)


def test_the_header_length_is_read_and_not_assumed():
    """Eine Blockkarte aus zwei Eintraegen macht den Kopf 80 Byte lang.

    72 ist das Minimum und der Wert, den Arch ausliefert: 56 Byte fester
    Teil, ein Karteneintrag, ein Abschluss. Ein Volume mit zwei
    Blockgruppen hat einen mehr. Ein festverdrahtetes 72 wuerde dort auf
    die Blockkarte zeigen statt auf den Variablenspeicher - und der
    Fehler kaeme als "keine authentifizierten Variablen" heraus, also als
    eine Aussage ueber die falsche Sache.
    """
    store = secureboot.enroll(make_template(header_length=80), CERTIFICATE)
    assert [entry["name"] for entry in secureboot.read_variables(store)] == \
        ["PK", "KEK", "db"]


def test_a_store_without_authenticated_variables_is_refused():
    """Die andere Kennung ist gEfiVariableGuid - ein Speicher ohne
    Authentifizierung. Ein PK darin waere ein PK, den die Firmware nie
    liest."""
    plain = uuid.UUID("ddcf3616-3275-4164-98b6-fe85707ffe7d")
    with pytest.raises(ValueError, match="Kennung"):
        secureboot.enroll(make_template(guid=plain), CERTIFICATE)


def test_an_unformatted_store_is_refused():
    with pytest.raises(ValueError, match="Format"):
        secureboot.enroll(make_template(form=0x00), CERTIFICATE)


def test_a_volume_without_the_fvh_signature_is_refused():
    with pytest.raises(ValueError, match="_FVH"):
        secureboot.enroll(bytes(4096), CERTIFICATE)


@pytest.mark.skipif(
    not any(path.is_file() for path in secureboot.OVMF_VARS_CANDIDATES),
    reason="kein OVMF auf dieser Maschine - edk2-ovmf ist nicht installiert")
def test_the_real_ovmf_template_parses_and_takes_the_three_keys():
    """Und derselbe Ablauf gegen die Datei, die QEMU wirklich bekommt."""
    template = next(path for path in secureboot.OVMF_VARS_CANDIDATES
                    if path.is_file()).read_bytes()
    start, end = secureboot.variable_store_bounds(template)
    assert end > start
    assert secureboot.read_variables(template) == []

    store = secureboot.enroll(template, CERTIFICATE)
    assert len(store) == len(template)
    # Alles ausserhalb des beschriebenen Stuecks muss Byte fuer Byte die
    # Vorlage sein. Der Bereich hinter dem Variablenspeicher ist bei OVMF
    # der Arbeitsbereich der fehlertoleranten Schreiblogik, und ein
    # Werkzeug, das ihn mitueberschreibt, baut eine Firmware, die beim
    # ersten Schreiben stehenbleibt.
    written = start + sum(
        len(secureboot.variable_record(name, guid, secureboot.signature_list(CERTIFICATE)))
        for name, guid in (("PK", secureboot.EFI_GLOBAL_VARIABLE_GUID),
                           ("KEK", secureboot.EFI_GLOBAL_VARIABLE_GUID),
                           ("db", secureboot.EFI_IMAGE_SECURITY_DATABASE_GUID)))
    assert store[:start] == template[:start]
    assert store[written:] == template[written:]
    assert [entry["name"] for entry in secureboot.read_variables(store)] == \
        ["PK", "KEK", "db"]


# --------------------------------------------------------------------
# Die PE-Signaturtabelle
# --------------------------------------------------------------------
def make_pe(magic: int = 0x20B, directories: int = 16,
            security: tuple[int, int] = (0, 0)) -> bytes:
    """Gerade so viel PE/COFF, wie certificate_table() anfasst."""
    header_at = 0x80
    optional_at = header_at + 24
    directories_at = optional_at + (108 if magic == 0x20B else 92)
    image = bytearray(directories_at + 4 + 8 * 16)
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, header_at)
    image[header_at:header_at + 4] = b"PE\0\0"
    struct.pack_into("<H", image, optional_at, magic)
    struct.pack_into("<I", image, directories_at, directories)
    if directories > 4:
        struct.pack_into("<II", image, directories_at + 4 + 8 * 4, *security)
    return bytes(image)


def test_an_image_without_a_certificate_table_is_unsigned():
    assert secureboot.certificate_table(make_pe()) == (0, 0)
    assert secureboot.is_signed(make_pe()) is False


def test_the_certificate_table_is_read_from_the_fifth_directory():
    """Der fuenfte Eintrag und kein anderer.

    Vier Eintraege daneben ist IMAGE_DIRECTORY_ENTRY_EXCEPTION, und
    jedes signierte wie unsignierte Abbild hat dort irgendetwas stehen -
    ein Leser, der falsch zaehlt, meldet also "signiert" ueber alles.
    """
    signed = make_pe(security=(4096, 2048))
    assert secureboot.certificate_table(signed) == (4096, 2048)
    assert secureboot.is_signed(signed) is True

    # Und die Nachbarn duerfen nichts aendern.
    header_at = 0x80
    directories_at = header_at + 24 + 108
    image = bytearray(make_pe())
    for index in (0, 1, 2, 3, 5, 6, 7):
        struct.pack_into("<II", image, directories_at + 4 + 8 * index, 999, 999)
    assert secureboot.certificate_table(bytes(image)) == (0, 0)


def test_pe32_and_pe32_plus_put_the_directories_in_different_places():
    assert secureboot.certificate_table(
        make_pe(magic=0x10B, security=(77, 88))) == (77, 88)


def test_an_image_with_fewer_than_five_directories_has_no_signature():
    assert secureboot.certificate_table(make_pe(directories=2)) == (0, 0)


@pytest.mark.parametrize("rubbish, why", [
    (b"", "zu kurz oder kein MZ"),
    (b"NOTAPE" + bytes(4096), "kein MZ-Kopf"),
    (b"MZ" + bytes(10), "zu kurz fuer einen DOS-Kopf"),
])
def test_something_that_is_not_a_pe_image_says_so(rubbish, why):
    with pytest.raises(secureboot.NotPortableExecutable):
        secureboot.certificate_table(rubbish)


def test_a_dos_stub_pointing_nowhere_is_not_a_pe_image():
    image = bytearray(0x100)
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x40)      # dort steht kein "PE\0\0"
    with pytest.raises(secureboot.NotPortableExecutable, match="PE-Signatur"):
        secureboot.certificate_table(bytes(image))


def test_an_unknown_optional_header_magic_is_refused():
    with pytest.raises(secureboot.NotPortableExecutable, match="Magic"):
        secureboot.certificate_table(make_pe(magic=0x107))


# --------------------------------------------------------------------
# Der Messaufbau in iso/test-boot.py
# --------------------------------------------------------------------
def test_the_secure_boot_machine_uses_the_secboot_build_of_ovmf():
    """Und nicht das gewoehnliche OVMF.

    Der Unterschied ist unsichtbar: OVMF_CODE.4m.fd startet mit einem
    eingetragenen Plattformschluessel genauso wie ohne, weil es ohne
    SECURE_BOOT_ENABLE gebaut ist. Ein Lauf gegen die falsche Datei
    meldet also "das Medium startet unter Secure Boot" - der teuerste
    Fehler, den dieses Szenario machen kann.
    """
    command = test_boot.qemu_command(
        Path("/run"), iso=Path("/x.iso"), target=None, update=None,
        firmware="uefi-secure", efivars=Path("/vars.fd"), vga="virtio",
        memory="4G", kvm=False)

    pflash = [item for item in command if item.startswith("if=pflash")]
    assert len(pflash) == 2
    assert "secboot" in pflash[0]
    assert "readonly=on" in pflash[0]
    assert pflash[1].endswith("file=/vars.fd")


def test_the_secure_boot_machine_turns_smm_on_and_locks_the_variable_store():
    """Beide Schalter, und der zweite ist der, der die Messung traegt.

    Ohne smm=on startet die Firmware nicht. Ohne die geschuetzte
    pflash-Einheit startet sie - und laesst den Gast in seine eigene db
    schreiben, was auf keiner Hardware so ist.
    """
    command = test_boot.qemu_command(
        Path("/run"), iso=Path("/x.iso"), target=None, update=None,
        firmware="uefi-secure", efivars=Path("/vars.fd"), vga="virtio",
        memory="4G", kvm=False)

    assert command[command.index("-machine") + 1] == "q35,smm=on"
    assert "driver=cfi.pflash01,property=secure,value=on" in command
    assert "ICH9-LPC.disable_s3=1" in command


def test_the_ordinary_uefi_machine_is_left_alone():
    """Die Gegenprobe zu den beiden darueber.

    Ein Schalter, der versehentlich fuer JEDE UEFI-Maschine gesetzt
    wuerde, aenderte still die vier Szenarien, die es schon gibt - und
    die messen etwas anderes.
    """
    command = test_boot.qemu_command(
        Path("/run"), iso=Path("/x.iso"), target=None, update=None,
        firmware="uefi", efivars=Path("/vars.fd"), vga="virtio",
        memory="4G", kvm=False)

    assert command[command.index("-machine") + 1] == "q35"
    assert not [item for item in command if "smm" in item]
    assert not [item for item in command if "secboot" in item]
    assert not [item for item in command if "cfi.pflash01" in item]


def test_a_bios_machine_gets_no_firmware_flash_at_all():
    command = test_boot.qemu_command(
        Path("/run"), iso=Path("/x.iso"), target=None, update=None,
        firmware="bios", efivars=None, vga="virtio", memory="4G", kvm=False)
    assert not [item for item in command if "pflash" in item]


def test_the_scenario_runs_two_machines_and_they_differ_only_in_the_store():
    """Die Kontrolle steht zuerst und beide Maschinen sind benannt.

    Die Reihenfolge ist keine Kosmetik: laeuft die erzwingende Maschine
    zuerst und die Kontrolle danach, dann steht das Ergebnis vierzig
    Sekunden lang ohne die Aussage da, die es ueberhaupt zu einem
    Ergebnis macht.
    """
    names = [name for name, _description in test_boot.SECURE_BOOT_MACHINES]
    assert names == ["setup", "enforcing"]
    assert test_boot.SCENARIOS["secure-boot"]["firmware"] == "uefi-secure"


def test_the_screenshot_schedule_covers_the_boot_menu_window():
    """Sonst waere "kein Startmenue" eine Aussage ueber den Zeitplan.

    grade_boot_menu() bewertet nur Bilder aus den ersten
    BOOT_MENU_WINDOW Sekunden. Ein Zeitplan ohne Marke darin haette in
    beiden Laeufen kein Bild zu bewerten - und der Vergleich der beiden
    waere "nein gegen nein", also bestanden aus dem falschen Grund.
    """
    inside = [mark for mark in test_boot.SECURE_BOOT_SETTLE
              if mark <= test_boot.BOOT_MENU_WINDOW]
    assert len(inside) >= 3
    # Und mindestens eine Marke dahinter, damit der Lauf, in dem nichts
    # startet, auch ein Bild von dem hat, was stattdessen dasteht.
    assert max(test_boot.SECURE_BOOT_SETTLE) > test_boot.BOOT_MENU_WINDOW


def test_the_boot_chain_names_the_files_mkarchiso_actually_writes():
    """Die Liste der geprueften Dateien gegen das Profil, das sie erzeugt.

    `uefi.grub` in profiledef.sh ist der Bauschritt, der
    EFI/BOOT/BOOTx64.EFI und BOOTIA32.EFI erzeugt, und install_dir sagt,
    unter welchem Namen der Kernel landet. Steht in BOOT_CHAIN ein Pfad,
    den kein Bauschritt schreibt, dann meldet inspect ihn als fehlend -
    und "fehlt" liest sich in einer Liste ueber Signaturen wie "hat
    keine".
    """
    profiledef = (ISO / "profile-release" / "profiledef.sh").read_text(
        encoding="utf-8")
    assert "'uefi.grub'" in profiledef
    install_dir = next(line.split('"')[1] for line in profiledef.splitlines()
                       if line.startswith("install_dir="))

    assert "EFI/BOOT/BOOTx64.EFI" in secureboot.BOOT_CHAIN
    assert f"{install_dir}/boot/x86_64/vmlinuz-linux" in secureboot.BOOT_CHAIN


def test_the_secure_boot_scenario_is_not_in_the_release_family():
    """Sonst liefe es durch run_release(), das genau eine Maschine faehrt.

    Der Vergleich zweier Firmware-Zustaende ist der ganze Inhalt dieses
    Szenarios; eine einzelne Maschine davon waere ein schwarzes Bild ohne
    Aussage.
    """
    assert "secure-boot" not in test_boot.RELEASE_FAMILY
    assert "secure-boot" in test_boot.SCENARIOS
    assert "secure-boot" in test_boot.ISO_PATTERNS
