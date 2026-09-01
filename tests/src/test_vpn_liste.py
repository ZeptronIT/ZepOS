# SPDX-License-Identifier: GPL-3.0-or-later
"""Aus einer VPN-Verbindung wird eine Liste - und keine Beschriftung faellt dabei weg.

DER AUFTRAG, WOERTLICH
    "ich will, dass ich in der liste das auswaehlen kann per toggle,
     welche vpn aktiv sein soll - bei wireguard, weil ich dort mehrere
     vpns habe und alle darueber verwaltbar sein muessen. das gleiche
     gilt uebrigens fuer die anderen vpn verbindungen auch!!!"

    Eine Liste mehrerer Verbindungen, jede mit einem Schalter, fuer ALLE
    DREI Bauarten. Kein neues Fenster: die beiden vorhandenen Flaechen
    (die Schalenseite und das Einstellungsfenster) bekommen die Liste,
    und jedes Feld, das es heute gibt, rueckt eine Ebene tiefer - hinter
    die gewaehlte Verbindung - statt zu verschwinden.

WARUM DIESE DATEI EINE EINGEFRORENE LISTE TRAEGT UND KEINE ZAHL
    Ein Umbau, der acht Reiterbauer, zwei Ansichten und eine Fusszeile
    anfasst, verliert ein Feld nicht mit einem Knall, sondern still: ein
    `build*Tab()`, das beim Umschreiben eine Zeile weniger anhaengt,
    faellt niemandem auf, der die Reiter nur ansieht. Der Nutzer merkt
    es, wenn er den Wert braucht - Wochen spaeter, an einem Tunnel, der
    etwas anderes aushandelt als vorher.

    GEZAEHLT am 22.08.2026, mit dem Leser aus test_ags_i18n.py
    (_ohne_kommentare + _msgids, damit Kommentartexte nicht mitzaehlen):
    27 Beschriftungen in ags-vpn.template, 135 in
    ags-vpn-settings.template, 162 zusammen, 161 verschiedene (eine
    steht in beiden Vorlagen).

    Eine blosse ZAHL haette dasselbe Problem wie die "74 Keybinds" ueber
    einer Tabelle mit 79 Eintraegen, die der Kopf von test_ags_i18n.py
    beschreibt: sie sagt nicht, WELCHE fehlt, und sie laesst sich durch
    eine neu hinzugefuegte Beschriftung ausgleichen, waehrend eine alte
    verschwindet. Darum die Namen selbst.

    TEILMENGE, NICHT GLEICHHEIT: neue Beschriftungen duerfen dazukommen
    (die Liste selbst braucht sieben), alte nicht wegfallen.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "_vpn_liste_i18n", Path(__file__).resolve().parent / "test_ags_i18n.py")
_I18N = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_I18N)

TEMPLATES = REPOSITORY / "src" / "templates"


def _beschriftungen(name: str) -> set[str]:
    """Die sichtbaren Beschriftungen einer Vorlage, Kommentare abgezogen.

    Ueber die Leser aus test_ags_i18n.py und nicht ueber ein eigenes
    Muster: zwei Muster fuer dieselbe Frage waeren zwei Antworten, und
    das hier ist die Datei, die nachweisen soll, dass sich nichts
    veraendert hat.
    """
    text = _I18N._ohne_kommentare(
        (TEMPLATES / name).read_text(encoding="utf-8"))
    return {anzeige for anzeige, _gesucht in _I18N._msgids(text)}


# Die 27 der Schalenseite, wie sie am 22.08.2026 dastanden.
SEITE_VORHER = {
    "2FA token (optional)",
    "6-digit code ...",
    "CONNECTIONS",
    "Connect",
    "Connected",
    "Connecting ...",
    "Connection failed",
    "Connection: {connection}",
    "Disconnect",
    "Disconnecting ...",
    "IP: {ip}",
    "No peer configured yet - open the settings.",
    "Not connected",
    "PSK not found! Please save it in the VPN settings.",
    "Password",
    "Password ...",
    "Password required",
    "Peer: {endpoint}",
    "Remember username",
    "Server: {server}",
    "This OpenVPN connection identifies itself with certificates - there is nothing to type here.",
    "Username",
    "Username ...",
    "Username required",
    "VPN",
    "VPN incomplete – please reconnect",
    "WireGuard identifies itself with keys - there is nothing to type here.",
}

# Die 135 des Einstellungsfensters, wie sie am 22.08.2026 dastanden.
DIALOG_VORHER = {
    "Add DNS server",
    "Add address",
    "Add network",
    "Add peer",
    "Addresses",
    "Aggressive",
    "Allowed networks",
    "Authentication",
    "Back to the VPN connection",
    "Blocks embedded in the .ovpn file were unpacked into ~/.config/openvpn, readable only by you (0600). Only their file names are stored in the settings.",
    "Both",
    "CA certificate",
    "Cancel",
    "Certificates",
    "Certificates and keys",
    "Certificates only - this connection comes back on its own after a network change or resume.",
    "Choose a WireGuard configuration",
    "Choose an OpenVPN configuration",
    "Cipher",
    "Connection",
    "Connection kind",
    "Connection name",
    "Connection settings",
    "Copy the public key",
    "Create a key pair",
    "DNS",
    "DNS servers",
    "DNS settings",
    "DPD delay (seconds)",
    "DPD timeout (seconds)",
    "Default username",
    "Delete peer",
    "Device",
    "ESP phase 2 settings",
    "ESP proposals",
    "Enable XAuth",
    "Endpoint",
    "Enter or show the PSK ...",
    "File name or absolute path ...",
    "Full tunnel: the file carries redirect-gateway, which sends all traffic through the tunnel - independently of this list.",
    "Full tunnel: these networks cover the entire IPv4 address space. All IPv4 traffic runs through the VPN.",
    "Full tunnel: these networks cover the entire IPv4 and IPv6 address space. All traffic runs through the VPN - nothing goes past it.",
    "Full tunnel: these networks cover the entire IPv6 address space. All IPv6 traffic runs through the VPN.",
    "General",
    "HMAC authentication",
    "IKE phase 1 settings",
    "IKE proposals",
    "IP address ...",
    "IPsec (IKEv1)",
    "IPsec (IKEv2)",
    "Import",
    "Imported",
    "Imported. These lines were NOT taken over, because they run commands: {lines}",
    "Interface",
    "Interface settings",
    "Keepalive (seconds, 0 = off)",
    "Key lifetime (seconds)",
    "Key present in {path}",
    "Life time (seconds)",
    "Listen port (0 = automatic)",
    "MOBIKE",
    "MTU (0 = automatic)",
    "Main",
    "Mode",
    "NAT encapsulation",
    "No file chooser available - please type the path.",
    "No key was created: {error}",
    "No key yet - create one, or import a .conf file",
    "Not imported: {error}",
    "Not saved: {error}",
    "Not set",
    "OpenVPN",
    "OpenVPN configuration",
    "Own certificate",
    "Own private key",
    "Own public key ...",
    "Path to a .conf file ...",
    "Path to an .ovpn file ...",
    "Peer {number}",
    "Peers",
    "Phase 1",
    "Phase 2",
    "Port (0 = 1194)",
    "Pre-shared key",
    "Present in {path}",
    "Private key",
    "Protocol",
    "Public key of the peer",
    "Rekey time (seconds)",
    "Replay window",
    "Reset",
    "Routed networks",
    "Save",
    "Save PSK",
    "Search domain",
    "Server",
    "Settings saved",
    "Show PSK",
    "Show debug terminal",
    "TCP",
    "TLS auth key",
    "TLS auth key direction (0, 1 or empty)",
    "TLS crypt key",
    "Test host (optional)",
    "The PSK could not be saved",
    "The PSK was stored securely",
    "The certificates and the key were stored privately. The original {path} still contains them in clear text - you may want to delete it.",
    "The connection was not set up: {error}",
    "The key was stored privately. The original {path} still contains it in clear text - you may want to delete it.",
    "The password is not stored. It is typed on the VPN page and handed to NetworkManager in a file that is deleted again.",
    "These lines have no effect here, because NetworkManager sets its own: {lines}",
    "This configuration routes all traffic through the tunnel. It was taken over exactly as the file has it - the networks can be changed in the tabs.",
    "This connection needs a password every time. After a network change or resume it stays down until you connect again.",
    "Transport",
    "Tunnel",
    "UDP",
    "Username",
    "Username and password",
    "VPN PSK",
    "VPN server",
    "VPN settings",
    "Verify server certificate (remote-cert-tls)",
    "WireGuard",
    "WireGuard configuration",
    "Without at least one network the tunnel comes up and carries no traffic.",
    "Without at least one peer with allowed networks the tunnel comes up and carries no traffic.",
    "e.g. 10.0.0.0/8",
    "e.g. 10.9.0.2/24",
    "tap (bridged)",
    "tun (routed)",
    "{count} further options were taken over from the file: {options}",
    "← VPN",
    "⚠ No PSK saved - please enter one and save it",
    "⚠ The PSK could not be saved",
    "✓ PSK present in {path}",
}


def test_die_gezaehlte_menge_ist_die_eingefrorene():
    """Die Gegenprobe zur Liste selbst.

    Ohne sie koennte jemand die beiden Mengen oben leeren und haette
    einen Test, der alles durchlaesst - genau der Fehler, den
    test_ags_i18n.py mit `assert geprueft` an zwei Stellen abfaengt.
    """
    assert len(SEITE_VORHER) == 27, (
        f"{len(SEITE_VORHER)} statt 27 eingefrorene Beschriftungen der "
        "Schalenseite - die Messung im Dateikopf und die Liste darunter "
        "sind auseinandergelaufen")
    assert len(DIALOG_VORHER) == 135, (
        f"{len(DIALOG_VORHER)} statt 135 eingefrorene Beschriftungen des "
        "Einstellungsfensters")
    assert len(SEITE_VORHER | DIALOG_VORHER) == 161, (
        "161 verschiedene war die Messung - eine Beschriftung steht in "
        "beiden Vorlagen")


def test_keine_beschriftung_der_vpn_seite_faellt_beim_umbau_weg():
    heute = _beschriftungen("ags-vpn.template")
    fehlend = sorted(SEITE_VORHER - heute)
    assert fehlend == [], (
        "diese Beschriftungen der VPN-Schalenseite gibt es nicht mehr: "
        + "; ".join(fehlend))


def test_keine_beschriftung_des_vpn_fensters_faellt_beim_umbau_weg():
    heute = _beschriftungen("ags-vpn-settings.template")
    fehlend = sorted(DIALOG_VORHER - heute)
    assert fehlend == [], (
        "diese Beschriftungen des VPN-Einstellungsfensters gibt es nicht "
        "mehr: " + "; ".join(fehlend))


# --------------------------------------------------------------------
# Die Klammer um eine Doppelung, die es schon gab
# --------------------------------------------------------------------
#
# DER FUND, DER DIESEN ABSCHNITT AUSGELOEST HAT (22.08.2026)
#     `src/vpn.py::swanctl_config()` hat AUSSERHALB DER TESTS KEINEN
#     AUFRUFER. Gemessen:
#
#         grep -rn swanctl_config src tests --include='*.py'
#             --include='*.template' --include='*.sh'
#
#     Fundorte in src/: genau einer, die Definition selbst. Produktiv
#     laeuft `swanctl_children()` (ueber {{STYLE_VPN_CHILDREN}} in
#     src/style_definition.py) UND, davon getrennt, ein eigenes
#     Heredoc in src/templates/vpn-connect-script.template.
#
#     DAS HEISST: der Zeichengleichheitstest
#     tests/src/test_vpn_volltunnel.py::
#     test_die_erzeugte_swanctl_conf_ist_zeichengleich pinnt eine
#     SPEZIFIKATION und keinen ERZEUGER. Er ist wertvoll - er sagt,
#     was eine Verbindung bedeuten SOLL -, aber er kann nicht
#     bemerken, wenn die Datei, die wirklich geschrieben wird, etwas
#     anderes sagt. Wer ihn fuer staerker haelt, als er ist, uebersieht
#     genau die Luecke, in der die zwei auseinanderlaufen.
#
# WARUM DIE DOPPELUNG HIER NICHT AUFGELOEST WIRD
#     Das Heredoc traegt fuenf Werte, die es zur Erzeugungszeit nicht
#     gibt (die Schnittstelle der Vorgaberoute, die
#     Aggressive-Zeile, den lokalen Auth-Block, den PSK und das
#     XAuth-Geheimnis) und einen ganzen `secrets {}`-Block, den
#     swanctl_config() nicht kennt. Beide zusammenzulegen waere richtig
#     und ist ein eigener Umbau - mitten in einem Umbau der
#     Einstellungen waere es ein Risiko zu viel an der einzigen Stelle,
#     die eine arbeitende IPsec-Verbindung kaputtmachen kann.
#
#     Also bleibt sie stehen - aber nicht unbewacht.

VERBINDUNGSSKRIPT = REPOSITORY / "src" / "templates" / "vpn-connect-script.template"
VPN_MODUL = REPOSITORY / "src" / "vpn.py"

# Die Felder, die BEIDE Seiten in den `connections { ... }`-Block
# schreiben. Was hier steht, muss auf beiden Seiten stehen.
GETEILTE_FELDER = {
    "version", "proposals", "dpd_delay", "dpd_timeout", "encap", "mobike",
    "rekey_time", "remote_addrs", "vips", "auth", "id",
}

# Und die benannten, begruendeten Abweichungen. Jede Zeile hier ist eine
# Entscheidung, keine Nachlaessigkeit - eine Abweichung OHNE Eintrag
# laesst den Test unten scheitern.
# Und umgekehrt: die Kind-Verknuepfungen (`esp_proposals`, `life_time`,
# `mode`, `replay_window`, `rekey_time`) stehen in KEINEM der beiden
# Texte ausgeschrieben - sie kommen auf BEIDEN Seiten aus derselben
# Funktion, `swanctl_children()`: im Modul ueber `{children}`, im Skript
# ueber `${CHILDREN_CONF}`, das der Erzeuger aus genau dieser Funktion
# einsetzt (src/style_definition.py::vpn_children_block()). Das ist der
# Teil der Doppelung, den es NICHT gibt - und der Grund, aus dem der
# Rest ueberhaupt ueberschaubar bleibt.
NUR_IM_SKRIPT = {
    # Bindet die IKE-Quelle an die Schnittstelle der Vorgaberoute. Gibt
    # es zur Erzeugungszeit nicht: welche das ist, entscheidet sich beim
    # Verbinden, und auf einem Rechner mit parallelem WireGuard-Tunnel
    # entscheidet genau sie darueber, ob die Verbindung zustande kommt.
    "local_addrs",
    # Der lokale Auth-Block (PSK bzw. XAuth) - er traegt den
    # Benutzernamen, den erst der Verbindungsdialog kennt.
    "local",
    # Der `secrets {}`-Block mit PSK und XAuth-Geheimnis. Er darf in
    # swanctl_config() gar nicht vorkommen: diese Funktion ist die
    # Form, die man ANSEHEN kann, ohne ein Geheimnis zu lesen.
    "secrets", "ike-work", "secret",
    # aggressive steht im Skript in einer eigenen, bedingten Zeile
    # (AGGRESSIVE_LINE) statt im Heredoc-Rumpf.
    "aggressive",
}


def _felder(text: str) -> set[str]:
    """Die swanctl-Feldnamen eines Konfigurationsblocks.

    `feld = wert` und `feld {` - beides, weil `remote {` und
    `remote_addrs =` in derselben Datei nebeneinander stehen.

    `{{` wird wie `{` gelesen: swanctl_config() baut seinen Block in
    einer f-Zeichenkette, und dort ist die geschweifte Klammer
    verdoppelt. Ohne diesen Schritt fehlte auf der Python-Seite genau
    der aeussere Blockname `connections` - GEMESSEN beim ersten Lauf
    dieses Tests am 22.08.2026.
    """
    import re
    # Der Anfang der f-Zeichenkette steht in derselben Zeile wie der
    # aeussere Blockname (`return f"""connections {{`) - ohne diesen
    # Schnitt fiele genau er heraus, GEMESSEN am 22.08.2026.
    text = text.replace('return f"""', "\n")
    return (set(re.findall(r"^\s*([a-z_][a-z0-9_-]*)\s*=", text, re.M))
            | set(re.findall(r"^\s*([a-z_][a-z0-9_-]*)\s*\{\{?", text, re.M)))


def _heredoc() -> str:
    text = VERBINDUNGSSKRIPT.read_text(encoding="utf-8")
    anfang = text.index('cat > "$WORK_CONF" << EOF')
    return text[anfang:text.index("\nEOF", anfang)]


def _swanctl_config_quelle() -> str:
    """NUR der Block, den swanctl_config() zurueckgibt.

    Nicht die ganze Funktion: die weist auf dem Weg dorthin `vpn`,
    `server`, `phase1`, `phase2` und `verbindungsname` zu, und ein
    Muster, das jede Zuweisung fuer ein swanctl-Feld haelt, meldete
    fuenf Felder, die es nicht gibt - GEMESSEN am 22.08.2026 beim
    dritten Lauf dieses Tests.
    """
    text = VPN_MODUL.read_text(encoding="utf-8")
    anfang = text.index("def swanctl_config(")
    block = text.index('return f"""', anfang)
    return text[block:text.index('"""', block + 11)]


def test_das_verbindungsskript_und_swanctl_config_schreiben_dieselben_felder():
    """Zwei Stellen, die dasselbe beschreiben - gegeneinander gehalten.

    Ein Bash-Heredoc kann kein Python importieren, also bleibt nur der
    Vergleich der beiden Texte. Dieselbe Form wie
    test_update.py::test_the_rule_for_pending_is_the_one_the_login_
    already_applies, und aus demselben Grund: zwei Antworten auf
    dieselbe Frage sind eine Antwort zu viel.
    """
    skript = _felder(_heredoc())
    modul = _felder(_swanctl_config_quelle())

    fehlt_im_modul = (skript - modul) - NUR_IM_SKRIPT
    assert fehlt_im_modul == set(), (
        "das Verbindungsskript schreibt Felder, die swanctl_config() "
        f"nicht kennt: {sorted(fehlt_im_modul)}. Entweder gehoeren sie "
        "dorthin, oder sie gehoeren mit Begruendung nach NUR_IM_SKRIPT.")

    fehlt_im_skript = modul - skript
    assert fehlt_im_skript == set(), (
        "swanctl_config() kennt Felder, die das Verbindungsskript nicht "
        f"schreibt: {sorted(fehlt_im_skript)} - dann baut der Erzeuger "
        "eine andere Verbindung als der, der wirklich waehlt.")

    # Die Gegenprobe: der Vergleich haelt nicht zwei leere Mengen
    # gegeneinander.
    assert GETEILTE_FELDER <= (skript & modul), (
        "diese Felder sollten auf BEIDEN Seiten stehen und tun es nicht: "
        f"{sorted(GETEILTE_FELDER - (skript & modul))}")


def test_swanctl_config_hat_ausserhalb_der_tests_keinen_aufrufer():
    """Der Fund selbst, festgehalten - damit er nicht wieder verlorengeht.

    Solange das so ist, pinnt der Zeichengleichheitstest eine
    Spezifikation und keinen Erzeuger. Bekommt swanctl_config() eines
    Tages einen produktiven Aufrufer (weil die Doppelung oben aufgeloest
    wurde), schlaegt dieser Test fehl - und das ist dann die gute
    Nachricht, die jemand hier vermerken soll.
    """
    # Ueber pathlib und nicht ueber grep(1): die Testhuelle dieses
    # Baums blockt echte Unterprozesse (tests/conftest.py), und fuer
    # eine Textsuche in src/ braucht es auch keinen.
    ausser_definition = []
    for pfad in sorted((REPOSITORY / "src").rglob("*")):
        if pfad.suffix not in (".py", ".template", ".sh") or not pfad.is_file():
            continue
        for nummer, zeile in enumerate(
                pfad.read_text(encoding="utf-8").splitlines(), start=1):
            nackt = zeile.strip()
            # Kommentare und Dokumentationszeilen zaehlen nicht: ein
            # Verweis im Fliesstext ist kein Aufrufer. Sonst meldete
            # ausgerechnet der Kommentar, der diese Lage BESCHREIBT,
            # sie als behoben.
            if nackt.startswith("#") or nackt.startswith("*"):
                continue
            if "swanctl_config" in zeile and "def swanctl_config(" not in zeile:
                ausser_definition.append(
                    f"{pfad.relative_to(REPOSITORY)}:{nummer}: {zeile.strip()}")
    assert ausser_definition == [], (
        "swanctl_config() hat jetzt einen Aufrufer in src/: "
        f"{ausser_definition}. Wenn die Doppelung mit dem Heredoc in "
        "vpn-connect-script.template damit aufgeloest ist, sind dieser "
        "Test und der Kommentar darueber zu streichen.")


# --------------------------------------------------------------------
# Die Wanderung verliert nichts
# --------------------------------------------------------------------
#
# DER WICHTIGSTE TEST DIESER AUFGABE, und er steht auf einer MESSUNG
# und nicht auf einer Vorgabentabelle.
#
#     GEPRUEFT am 22.08.2026 an einer echten, benutzten
#     Einstellungsdatei (nur die SCHLUESSELNAMEN gelesen - kein Wert,
#     kein Server, kein Geheimnis): sie traegt `debug`,
#     `remember_username`, `username`, `xauth_enabled`, `phase1`,
#     `phase2` - und in `phase2` ein `child_sas`.
#
#     `phase2.child_sas` steht in KEINER der beiden Vorgabentabellen
#     dieses Baums. Eine Wanderung, die den Eintrag aus einer bekannten
#     Schluesselliste NEU BAUT, haette ihn still fallen lassen: der
#     Tunnel des Nutzers haette sich danach anders verhalten, und
#     nichts haette gesagt, warum.
#
#     Darum wird hier nicht geprueft, ob die BEKANNTEN Schluessel
#     ankommen, sondern ob ueberhaupt EINER fehlt.

from src import settings as _settings  # noqa: E402


ECHTE_GESTALT = {
    # Nachgebildet nach der gemessenen Datei - dieselben SCHLUESSEL,
    # erfundene Werte. Kein Wert dieser Maschine steht in diesem Baum.
    "connection_name": "work",
    "server": "gw.example.invalid",
    "username": "konto",
    "remember_username": True,
    "xauth_enabled": True,
    "debug": False,
    "dns": {"servers": ["203.0.113.53"], "search_domain": "example.invalid"},
    "phase1": {"version": 2, "aggressive": False, "keylife": 86400},
    # Der Schluessel, den keine Vorgabentabelle kennt.
    "phase2": {"rekey_time": 43200, "child_sas": 3},
}


def test_die_wanderung_verliert_keinen_einzigen_schluessel():
    gewandert = _settings.migrate_vpn(ECHTE_GESTALT)
    eintrag = gewandert["connections"][0]

    fehlend = {k: v for k, v in ECHTE_GESTALT.items() if eintrag.get(k) != v}
    assert fehlend == {}, (
        f"die Wanderung hat Schluessel verloren oder veraendert: {fehlend}")

    # Und NICHTS ausser der Kennung ist dazugekommen. Ein stillschweigend
    # ergaenzter Schluessel waere eine Aussage ueber die Verbindung des
    # Nutzers, die er nie getroffen hat.
    dazu = set(eintrag) - set(ECHTE_GESTALT)
    assert dazu == {"id"}, f"unerwartet dazugekommen: {sorted(dazu)}"
    assert eintrag["id"] == _settings.MIGRATED_ID
    assert gewandert["active"] == _settings.MIGRATED_ID


def test_der_verschachtelte_schluessel_kommt_wirklich_mit():
    """Die Gegenprobe zum Test oben.

    `phase2.child_sas` liegt eine Ebene TIEFER, und ein Vergleich, der
    nur die obersten Schluessel prueft, haette ihn nicht bemerkt.
    """
    eintrag = _settings.migrate_vpn(ECHTE_GESTALT)["connections"][0]
    assert eintrag["phase2"]["child_sas"] == 3


def test_die_wanderung_wandert_nicht_zweimal():
    """migrate() laeuft bei JEDEM Lesen.

    Eine Wanderung, die sich selbst noch einmal wandert, legte die Liste
    bei jedem Lesen eine Ebene tiefer.
    """
    einmal = _settings.migrate_vpn(ECHTE_GESTALT)
    assert _settings.migrate_vpn(einmal) == einmal


def test_ein_leerer_abschnitt_wird_keine_leere_verbindung():
    """Keine Verbindung ist etwas anderes als eine unausgefuellte."""
    assert _settings.migrate_vpn({}) == {"active": "", "connections": []}


def test_die_kennung_der_gewanderten_ist_fest_und_nicht_gewuerfelt():
    """Sonst gaebe jeder Leser eine andere Antwort.

    migrate() laeuft im Speicher bei jedem Lesen, und mehrere Leser
    laufen nebeneinander - die Leiste fragt `vpn.py --status` mehrmals
    je Minute, waehrend der Erzeuger dieselbe Datei liest. Eine
    gewuerfelte Kennung hiesse: wer zuletzt speichert, gewinnt, und die
    Schluesseldateien zeigen auf eine Kennung, die es nicht mehr gibt.
    """
    a = _settings.migrate_vpn(ECHTE_GESTALT)["connections"][0]["id"]
    b = _settings.migrate_vpn(ECHTE_GESTALT)["connections"][0]["id"]
    assert a == b == "c1"


def test_das_ganze_dokument_wandert_und_nur_der_vpn_abschnitt_aendert_sich():
    dokument = {
        "schema_version": 1,
        "vpn": dict(ECHTE_GESTALT),
        "weather": {"location": "Bremen"},
        # Ein Abschnitt, den dieser Baum gar nicht kennt.
        "etwas_fremdes": {"a": 1},
    }
    gewandert = _settings.migrate(dokument)

    assert gewandert["schema_version"] == _settings.SCHEMA_VERSION == 2
    assert gewandert["weather"] == {"location": "Bremen"}
    assert gewandert["etwas_fremdes"] == {"a": 1}, (
        "ein fremder Abschnitt ist verlorengegangen - eine "
        "Einstellungsdatei ist das Dokument des Nutzers und nicht die "
        "Summe dessen, was wir davon verstehen")
    assert gewandert["vpn"]["connections"][0]["phase2"]["child_sas"] == 3


def test_der_psk_der_bestehenden_verbindung_behaelt_seinen_dateinamen():
    """Die Zeile, die die arbeitende Verbindung unangetastet laesst.

    Der IPsec-PSK lag unter dem FESTEN Pfad ~/.config/strongswan/psk und
    wurde in keiner Einstellung genannt. Die Wanderung traegt darum auch
    keinen Namen dafuer nach - ein fehlendes `psk_file` heisst genau
    das, was es immer geheissen hat. Waere es anders, muesste die
    Wanderung die Datei umbenennen, und das ist das Einzige, was sie
    nicht darf.
    """
    from src import vpn
    eintrag = _settings.migrate_vpn(ECHTE_GESTALT)["connections"][0]
    assert "psk_file" not in eintrag
    assert vpn.psk_file_name(eintrag) == "psk"
