from installer.core.model import (
    InstallConfig, UserAccount, WifiCredentials, DiskChoice,
    ZeposOptions, SCHEMA_VERSION,
)


def _sample() -> InstallConfig:
    return InstallConfig(
        language="de", keymap="de-latin1", timezone="Europe/Berlin",
        locale="de_DE", hostname="zepos",
        disk=DiskChoice(device="/dev/vda", wipe=True, filesystem="ext4"),
        users=[UserAccount(username="lars", password="geheim", sudo=True)],
        root_password="rootgeheim",
        wifi=WifiCredentials(ssid="Fritz", passphrase="wlanpw"),
        zepos=ZeposOptions(enable_plugins=True, weather_location="Musterstadt"),
    )


def test_roundtrip_preserves_all_fields():
    cfg = _sample()
    assert InstallConfig.from_dict(cfg.to_dict()) == cfg


def test_to_dict_carries_schema_version():
    assert _sample().to_dict()["schema_version"] == SCHEMA_VERSION


def test_from_dict_rejects_unknown_schema_version():
    d = _sample().to_dict()
    d["schema_version"] = 99
    try:
        InstallConfig.from_dict(d)
    except ValueError as exc:
        assert "99" in str(exc)
    else:
        raise AssertionError("erwartet: ValueError bei unbekannter Schemaversion")


def test_wifi_is_optional():
    cfg = _sample()
    cfg.wifi = None
    assert InstallConfig.from_dict(cfg.to_dict()).wifi is None


def test_roundtrip_preserves_the_encryption_choice_and_the_passphrase():
    """Beide Felder, und die Passphrase im Klartext - anders kann sie
    nicht reisen, weil cryptsetup die Zeichen selbst braucht. Faellt eines
    der beiden beim Umlauf weg, ist das Ergebnis eine Konfiguration, die
    verschluesseln WILL und es nicht kann."""
    cfg = _sample()
    cfg.disk.encrypt = True
    cfg.disk.passphrase = "eine-lange-passphrase"

    back = InstallConfig.from_dict(cfg.to_dict())
    assert back.disk.encrypt is True
    assert back.disk.passphrase == "eine-lange-passphrase"
    assert back == cfg


def test_a_config_file_written_before_encryption_existed_still_loads():
    """Der Fall, fuer den die Vorgabe False ist: eine Datei, in der von
    Verschluesselung nichts steht, heisst "niemand hat sich geaeussert" -
    dieselbe Unterscheidung wie bei DiskChoice.layout. Waere die Vorgabe
    True, kaeme jede aeltere Datei mit einer Verschluesselung ohne
    Passphrase an, und validate() lehnte sie zu Recht ab."""
    payload = _sample().to_dict()
    del payload["disk"]["encrypt"]
    del payload["disk"]["passphrase"]

    back = InstallConfig.from_dict(payload)
    assert back.disk.encrypt is False
    assert back.disk.passphrase == ""


def test_the_passphrase_is_in_the_dictionary_in_the_clear():
    """Kein Zufall und keine Nachlaessigkeit, sondern die dokumentierte
    Eigenschaft von to_dict() - und der Grund, aus dem das Ergebnis
    nirgends hingeschrieben werden darf, wo andere es lesen koennen."""
    cfg = _sample()
    cfg.disk.encrypt = True
    cfg.disk.passphrase = "eine-lange-passphrase"
    assert cfg.to_dict()["disk"]["passphrase"] == "eine-lange-passphrase"
