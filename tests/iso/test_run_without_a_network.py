# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Lauf, der das Medium OHNE Netzwerkkarte faehrt.

WARUM ES IHN GIBT
    Befund vom 17.08.2026, von echter Hardware: "Installation Wizard mit
    dem Terminal freezed wenn ich versuche ohne Internet und ohne
    Passphrase zu installieren."

    Gehangen hat archinstall 4.4 in lib/installer.py:189-202 - ein
    `while True` ohne Frist, das darauf wartet, dass `timedatectl show
    --property=NTPSynchronized` `yes` sagt. Ohne Netz sagt es das nie.
    Und gewartet wurde nach scripts/guided.py:249
    perform_filesystem_operations(), also vor einer bereits geteilten
    Platte.

    Kein Lauf dieser Reihe konnte das je sehen: qemu_command() gab jeder
    Maschine `-nic user`, ausnahmslos. Der Fall ohne Netz war nicht
    schwer zu messen - er war nie gefahren worden.

WAS HIER GEPRUEFT WIRD
    Nicht der Lauf selbst; der braucht QEMU und eine Viertelstunde. Hier
    steht das, was still kaputtgehen kann, ohne dass ein roter Lauf es
    meldet: dass die Maschine wirklich KEINE Karte bekommt, und dass sie
    die Platte und den Variablenspeicher der Nachbarlaeufe nicht
    anfasst.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ISO = Path(__file__).resolve().parents[2] / "iso"
SCENARIO = "release-install-ohne-netz"


def _module():
    spec = importlib.util.spec_from_file_location(
        "test_boot_module_ohne_netz", ISO / "test-boot.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_boot_module_ohne_netz"] = module
    spec.loader.exec_module(module)
    return module


def _command(module, *, network: bool, run: Path) -> list[str]:
    return module.qemu_command(
        run, iso=None, target=None, update=None, firmware="none",
        efivars=None, vga="virtio", memory="4G", kvm=False, network=network)


def test_the_scenario_exists_in_every_table_that_would_raise_without_it():
    """run_release() schlaegt den Namen in fuenf Verzeichnissen nach, und
    vier davon mit `[]`. Ein fehlender Eintrag ist kein sanftes
    Ausweichen, sondern ein KeyError mitten im Lauf - nachdem die ISO
    schon geprueft und die Platte schon angelegt wurde."""
    module = _module()
    for table in ("SCENARIOS", "ISO_PATTERNS", "RELEASE_TARGETS",
                  "DRIVE_SCRIPTS", "RELEASE_SETTLE", "RELEASE_LAYOUT"):
        assert SCENARIO in getattr(module, table), (
            f"{SCENARIO} fehlt in {table} - run_release() bricht damit "
            f"mitten im Lauf ab")
    assert SCENARIO in module.RELEASE_FAMILY, (
        "ohne diesen Eintrag schickt main() den Lauf in die Schleife, die "
        "eine serielle Leitung abfragt, auf die dieses Medium nichts "
        "schreibt")


def test_the_machine_really_gets_no_network_card(tmp_path):
    """`-nic none` und NICHT das Weglassen der Zeile.

    Ohne jedes -nic gibt QEMU dem Gast seine eingebaute Vorgabekarte -
    also genau das Gegenteil dessen, was dieser Lauf messen soll, und
    zwar lautlos: der Gast bekaeme eine Adresse, die Installation liefe
    durch, und der Lauf meldete gruen, dass es ohne Netz funktioniert.
    """
    module = _module()
    command = _command(module, network=False, run=tmp_path)

    assert "-nic" in command, (
        "gar kein -nic: QEMU gibt dem Gast dann seine Vorgabekarte, und "
        "der Lauf misst eine Maschine MIT Netz")
    assert command[command.index("-nic") + 1] == "none"
    for forbidden in ("user", "virtio-net-pci", "e1000"):
        assert not any(forbidden in argument for argument in command), (
            f"'{forbidden}' steht noch in der Befehlszeile: {command}")


def test_a_network_is_still_the_default(tmp_path):
    """Die andere Haelfte, ohne die die erste nichts aussagt.

    Waere `network` versehentlich ueberall falsch, liefe JEDER Lauf
    dieser Datei ohne Netz - und die Installationslaeufe scheiterten mit
    einer Begruendung, die nach einem Fehler von ZepOS aussieht.
    """
    module = _module()
    command = _command(module, network=True, run=tmp_path)
    assert command[command.index("-nic") + 1] == "user,model=virtio-net-pci"


def test_the_run_without_a_network_installs_onto_its_own_disk():
    """Dieser Lauf soll ABBRECHEN. Ein Abbruch, der die Installation der
    Nachbarlaeufe mitnimmt, ist ein teurer Weg, nichts zu erfahren -
    `release-installed` bootet genau die Platte, die `release-install`
    beschrieben hat."""
    module = _module()
    assert module.RELEASE_TARGETS[SCENARIO] != module.RELEASE_TARGET
    assert module.RELEASE_TARGETS[SCENARIO] != module.RELEASE_BOOT_TARGET
    assert module.RELEASE_TARGETS[SCENARIO] == module.RELEASE_OHNE_NETZ_TARGET


def test_the_run_without_a_network_has_its_own_efi_variables():
    """run_release() loescht RELEASE_EFIVARS fuer `release-install` und
    `release-installed` sucht darin den Starteintrag. Teilte dieser Lauf
    sich den Speicher, naehme er ihn mit - und zwar auch dann, wenn
    einer der beiden gerade laeuft. Gemessen am 17.08.2026: waehrend
    dieser Aenderung hatte ein `release-installed` genau diese Datei
    geoeffnet."""
    module = _module()
    harness = (ISO / "test-boot.py").read_text(encoding="utf-8")

    assert module.RELEASE_OHNE_NETZ_EFIVARS != module.RELEASE_EFIVARS
    assert f'scenario == "{SCENARIO}"' in harness
    # Der Zweig, der ihn waehlt, muss VOR dem `else` stehen, das
    # RELEASE_EFIVARS nimmt - sonst ist die eigene Datei da und wird nie
    # benutzt.
    eigener = harness.index("RELEASE_OHNE_NETZ_EFIVARS.unlink")
    geteilter = harness.index("efivars = efi_variables(RELEASE_EFIVARS)")
    assert eigener < geteilter, (
        "der Zweig fuer den eigenen Variablenspeicher steht hinter dem "
        "geteilten und wird nie erreicht")


def test_the_scenario_says_what_it_measures():
    """`--scenario` baut seine Hilfe aus diesen Saetzen. Einer, der die
    Frage nicht nennt, ist eine Zeile, die niemand wieder findet."""
    module = _module()
    what = module.SCENARIOS[SCENARIO]["what"].lower()
    assert "ohne netz" in what or "kein netz" in what, what


@pytest.mark.parametrize("other", ["release", "release-install",
                                   "release-installed", "boot-menu"])
def test_no_other_scenario_lost_its_network(other, tmp_path):
    """Die Voreinstellung ist `network=True`, und run_release() weicht
    nur fuer diesen einen Namen davon ab. Steht dort erst einmal ein
    `in`-Ausdruck oder ein Tippfehler, faehrt ein zweiter Lauf
    versehentlich ohne Netz und scheitert mit einer Meldung ueber ZepOS,
    die von QEMU handelt."""
    harness = (ISO / "test-boot.py").read_text(encoding="utf-8")
    assert f'network=scenario != "{SCENARIO}"' in harness, (
        "die eine Zeile, die entscheidet, welcher Lauf ohne Netz faehrt, "
        "sieht nicht mehr so aus wie gemessen")
    assert other != SCENARIO
