# SPDX-License-Identifier: GPL-3.0-or-later
from installer.core.model import InstallConfig, DiskChoice, UserAccount, WifiCredentials
from installer.core.validate import validate


def _cfg(**over) -> InstallConfig:
    base = dict(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda", size_bytes=64 * 1024**3),
        users=[UserAccount(username="lars", password="langgenug")],
        root_password="langgenug",
    )
    base.update(over)
    return InstallConfig(**base)


def test_valid_config_has_no_findings():
    assert validate(_cfg()) == []


def test_missing_user_is_reported():
    assert any("user" in f for f in validate(_cfg(users=[])))


def test_short_password_is_reported():
    cfg = _cfg(users=[UserAccount(username="lars", password="kurz")])
    assert any("password" in f for f in validate(cfg))


def test_short_password_finding_names_the_user():
    cfg = _cfg(users=[UserAccount(username="lars", password="kurz")])
    assert any("lars" in f for f in validate(cfg))


def test_invalid_hostname_is_reported():
    assert any("hostname" in f for f in validate(_cfg(hostname="zep os!")))


def test_hostname_with_leading_hyphen_is_reported():
    assert any("hostname" in f for f in validate(_cfg(hostname="-zepos")))


def test_empty_disk_device_is_reported():
    assert any("disk" in f for f in validate(_cfg(disk=DiskChoice(device=""))))


def test_disk_too_small_is_reported():
    """A too-small disk must surface as a finding the user can act on,
    not as an exception during installation."""
    cfg = _cfg(disk=DiskChoice(device="/dev/vda", size_bytes=100 * 1024**2))
    assert any("too small" in f for f in validate(cfg))


def test_disk_large_enough_is_not_reported():
    cfg = _cfg(disk=DiskChoice(device="/dev/vda", size_bytes=64 * 1024**3))
    assert validate(cfg) == []


def test_wifi_without_passphrase_is_reported():
    cfg = _cfg(wifi=WifiCredentials(ssid="Fritz", passphrase=""))
    assert any("wireless" in f for f in validate(cfg))


def test_no_wifi_configured_is_not_a_finding():
    """Installing over ethernet is perfectly normal."""
    assert validate(_cfg(wifi=None)) == []


def test_user_without_a_name_is_reported():
    """UserAccount has no __post_init__ guard, so an empty username is
    constructible and this path is reachable."""
    cfg = _cfg(users=[UserAccount(username="", password="langgenug")])
    assert any("no name" in f for f in validate(cfg))


# --- die Verschluesselung ----------------------------------------------
#
# validate() ist die Pruefung, die installer.core.runner.install()
# UNMITTELBAR VOR dem Loeschen ausfuehrt, und die einzige, durch die auch
# eine Konfigurationsdatei muss, die niemand durch eine Oberflaeche
# geschickt hat. Was hier durchkommt, wird installiert.


def _encrypted(**over) -> InstallConfig:
    disk = DiskChoice(
        device="/dev/vda", size_bytes=64 * 1024**3,
        encrypt=True, passphrase=over.pop("passphrase", "eine-lange-passphrase"))
    return _cfg(disk=disk, **over)


def test_an_encrypted_config_with_a_good_passphrase_is_valid():
    assert validate(_encrypted()) == []


def test_encryption_without_a_passphrase_is_reported():
    """DER Befund, um den es geht. archinstall wuerde daraus eine
    unverschluesselte Installation mit Rueckgabewert 0 machen -
    DiskEncryption.parse_arg() gibt ohne Passwort None zurueck und sagt
    nichts."""
    findings = validate(_encrypted(passphrase=""))
    assert any("no passphrase" in f for f in findings)
    assert any("unencrypted" in f for f in findings)


def test_a_short_passphrase_is_reported_here_too():
    """Nicht nur auf der Seite: eine Konfigurationsdatei kommt nie an
    einer Seite vorbei."""
    assert any("too short" in f for f in validate(_encrypted(passphrase="kurz")))


def test_an_unencrypted_config_says_nothing_about_passphrases():
    """Ohne Haken ist ein leeres Feld kein Befund - eine Installation
    ohne Verschluesselung ist eine gueltige Installation."""
    cfg = _cfg(disk=DiskChoice(
        device="/dev/vda", size_bytes=64 * 1024**3, encrypt=False,
        passphrase=""))
    assert validate(cfg) == []


def test_a_layout_with_nothing_encryptable_is_reported():
    """Nur eine EFI-Systempartition und sonst nichts: archinstall wuerde
    beim Einlesen mit "Luks or LvmOnLuks encryption require partitions to
    be defined" abbrechen. Hier steht der Grund lesbar auf der Seite."""
    from installer.core.layout import ESP_FILESYSTEM, ESP_FLAGS, ESP_MOUNTPOINT, PlannedPartition
    cfg = _cfg(disk=DiskChoice(
        device="/dev/vda", size_bytes=64 * 1024**3,
        encrypt=True, passphrase="eine-lange-passphrase",
        layout=[PlannedPartition(
            start_mib=1, size_mib=512, filesystem=ESP_FILESYSTEM,
            mountpoint=ESP_MOUNTPOINT, flags=ESP_FLAGS)]))
    assert any("nothing that can be encrypted" in f for f in validate(cfg))


def test_an_empty_layout_is_not_reported_as_unencryptable():
    """Der Textassistent plant keine Einteilung. Ohne die Ersetzung durch
    den Vorschlag (installer.core.crypt.effective_layout) haette
    ausgerechnet der gewoehnlichste Weg hier einen Befund bekommen."""
    cfg = _encrypted()
    assert cfg.disk.layout == []
    assert validate(cfg) == []
