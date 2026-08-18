# SPDX-License-Identifier: GPL-3.0-or-later
"""The firmware check that keeps a BIOS machine from being erased.

WARUM die Ablehnung bleibt, seit der Bootloader GRUB ist, steht im Kopf
von installer/core/firmware.py und nur dort. Seit dem 11.08.2026 ist der
STARTWEG gemessen - iso/test-bios-chain.py baut ZepOS' Einteilung als
MBR, richtet GRUB fuer i386-pc ein und startet das Ergebnis unter SeaBIOS
bis zum Anmeldezeichen -, der Weg dorthin nicht: dort partitioniert ein
Skript und nicht archinstall, und der Unterschied zwischen den beiden ist
genau die Stelle, an der eine Platte geloescht wird.
"""
from __future__ import annotations

from installer.core.firmware import EFI_SYSFS_PATH, firmware_problem, is_uefi


def test_uefi_is_reported_when_the_efi_directory_exists(tmp_path):
    (tmp_path / "efivars").mkdir()
    assert is_uefi(efi_path=tmp_path) is True


def test_bios_is_reported_when_the_efi_directory_is_absent(tmp_path):
    assert is_uefi(efi_path=tmp_path / "firmware" / "efi") is False


def test_a_file_where_the_directory_belongs_is_not_uefi(tmp_path):
    """The kernel creates a directory. Anything else there means the
    check cannot conclude UEFI, and guessing UEFI is the answer that
    erases a disk."""
    path = tmp_path / "efi"
    path.write_text("not a directory")
    assert is_uefi(efi_path=path) is False


def test_the_default_location_is_the_kernels_own():
    """The same path archinstall, systemd and the Arch installation guide
    all use. A typo here would report BIOS on every machine."""
    assert str(EFI_SYSFS_PATH) == "/sys/firmware/efi"


# --- the refusal, as text both surfaces can show before asking anything ---
#
# The check itself was only ever reachable through
# installer.core.runner.install(), i.e. after the user had answered every
# question and confirmed an erase. Whether a machine started in UEFI mode
# is knowable before the first question, so the message has to be
# available on its own - and from exactly one place, or the two surfaces
# and the runner would drift into three descriptions of the same refusal.


def test_no_problem_is_reported_on_a_uefi_machine():
    assert firmware_problem(is_uefi=lambda: True) == ""


def test_a_bios_machine_yields_the_refusal():
    """Asserted on the msgid, like the rest of the suite."""
    problem = firmware_problem(is_uefi=lambda: False)
    assert "UEFI" in problem
    assert "BIOS" in problem


def test_the_answer_is_taken_at_call_time(tmp_path):
    """is_uefi is resolved inside the call rather than bound as a default
    argument, so a caller can point the whole check at a directory of its
    own - the same rule every injected dependency in this package
    follows."""
    efi = tmp_path / "efi"
    assert firmware_problem(is_uefi=lambda: is_uefi(efi_path=efi)) != ""
    efi.mkdir()
    assert firmware_problem(is_uefi=lambda: is_uefi(efi_path=efi)) == ""
