#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Secure Boot, gemessen statt angenommen.

    ./iso/secureboot.py inspect                 was traegt die Startkette
                                                des Mediums an Signaturen
    ./iso/secureboot.py inspect --iso datei.iso ein bestimmtes Medium
    ./iso/secureboot.py enroll                  einen OVMF-Variablenspeicher
                                                mit eingetragenem Schluessel

WARUM ES DIESE DATEI GIBT
    Aufgabe REL-5 heisst "das Medium startet auf einer Firmware mit
    aktivem Secure Boot". Bevor irgendein Weg dorthin gewaehlt werden
    kann, muss zwei Dinge gemessen sein: WAS die Firmware ablehnt, und
    dass sie es wegen Secure Boot ablehnt und nicht aus einem anderen
    Grund. Beides ist hier.

    Die billige Haelfte ist inspect(): sie liest die PE-Dateien der
    Startkette aus dem gebauten Medium und sagt, ob eine davon eine
    Authenticode-Signatur traegt. Das braucht keine virtuelle Maschine
    und beantwortet die Frage "was genau wird abgelehnt" vollstaendig -
    eine Firmware mit Secure Boot prueft genau dieses Feld.

    Die teure Haelfte ist enroll() und
    `./iso/test-boot.py --firmware uefi-secure`: ein OVMF, das wirklich
    erzwingt, und ein Bild von dem, was dabei auf dem Schirm steht.

WARUM DER VARIABLENSPEICHER HIER GEBAUT WIRD UND NICHT MITGELIEFERT
    Arch liefert /usr/share/edk2/x64/OVMF_CODE.secboot.4m.fd - eine
    Firmware, die Secure Boot KANN - aber keinen Variablenspeicher, in
    dem Schluessel stehen. Gemessen am 11.08.2026: das Paket edk2-ovmf
    202605-1 enthaelt genau fuenf .fd-Dateien und OVMF_VARS.4m.fd ist
    leer. Ohne Plattformschluessel steht die Firmware im Setup Mode, und
    im Setup Mode prueft sie NICHTS. Ein Lauf gegen diese Vorlage wuerde
    also melden "das Medium startet unter Secure Boot", und das waere
    schlicht falsch.

    Fedora liefert dafuer EnrollDefaultKeys.efi, Arch nicht. Das Paket
    virt-firmware waere der andere Weg und ist hier nicht installiert.
    Beides sind Abhaengigkeiten, die eine Messung von einer fremden
    Distribution abhaengig machen. Das Format ist stattdessen
    nachgebaut - es sind zwei Strukturen und sie stehen in
    edk2/MdeModulePkg/Include/Guid/VariableFormat.h:

      VARIABLE_STORE_HEADER          direkt hinter dem Kopf des
                                     Firmware-Volumes, Format 0x5A,
                                     Zustand 0xFE
      AUTHENTICATED_VARIABLE_HEADER  60 Byte, dann der Name als UCS-2
                                     mit Nullzeichen, dann die Daten,
                                     dann auf 4 Byte aufgerundet

    Der Schluessel selbst ist ein Wegwerfschluessel, den enroll() mit
    openssl erzeugt. Fuer die Ablehnung ist es gleichgueltig, WESSEN
    Schluessel in der Firmware steht: eine Datei ohne jede Signatur wird
    von jedem Schluessel abgelehnt. Fuer die Gegenprobe - eine signierte
    Kette, die durchkommt - ist es der Schluessel, mit dem signiert
    werden muesste, und darum wird er neben dem Speicher abgelegt statt
    weggeworfen.

WARUM DIE GEGENPROBE ZUM MESSAUFBAU GEHOERT
    "Das Medium startet nicht" ist ohne Kontrolle keine Aussage ueber
    Secure Boot. Dieselbe Firmware, dieselbe Maschine, derselbe Datei-
    stand, und der EINZIGE Unterschied ist der Variablenspeicher: mit
    eingetragenem Plattformschluessel erzwingt OVMF, ohne ihn steht es im
    Setup Mode und laesst alles durch. Startet das Medium im zweiten Fall
    und im ersten nicht, dann ist die Ursache benannt und nicht vermutet.
    `./iso/test-boot.py --scenario secure-boot` faehrt beide Laeufe.
"""
from __future__ import annotations

import argparse
import struct
import subprocess
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ISO_DIR = REPO / "iso"
OUT = ISO_DIR / "out"

# --------------------------------------------------------------------
# Die Kennungen, alle aus der UEFI-Spezifikation 2.10
# --------------------------------------------------------------------
EFI_GLOBAL_VARIABLE_GUID = uuid.UUID("8be4df61-93ca-11d2-aa0d-00e098032b8c")
EFI_IMAGE_SECURITY_DATABASE_GUID = uuid.UUID("d719b2cb-3d3a-4596-a3bc-dad00e67656f")
EFI_CERT_X509_GUID = uuid.UUID("a5c059a1-94e4-4aa7-87b5-ab155c2bf072")

# Der Eigentuemer, der neben jeder Signatur steht. Frei waehlbar - die
# Firmware benutzt ihn nur, um beim Loeschen einer Signatur zu wissen,
# welche gemeint ist. Eine eigene, damit ein Speicher, den dieses
# Projekt gebaut hat, in `efi-readvar` als solcher zu erkennen ist.
ZEPOS_SIGNATURE_OWNER = uuid.UUID("7e50b05e-0000-4000-a000-7a65704f5300")

# edk2, MdeModulePkg/Include/Guid/VariableFormat.h
AUTHENTICATED_VARIABLE_STORE_GUID = uuid.UUID("aaf32c78-947b-439a-a180-2e144ec37792")
VARIABLE_STORE_FORMATTED = 0x5A
VARIABLE_STORE_HEALTHY = 0xFE
VARIABLE_DATA = 0x55AA          # StartId jedes Eintrags
VAR_ADDED = 0x3F                # Zustand eines gueltigen Eintrags
AUTH_VARIABLE_HEADER_SIZE = 60
HEADER_ALIGNMENT = 4

# NON_VOLATILE | BOOTSERVICE_ACCESS | RUNTIME_ACCESS |
# TIME_BASED_AUTHENTICATED_WRITE_ACCESS. Die letzte Flagge ist die, die
# PK, KEK und db von einer gewoehnlichen Variablen unterscheidet; ohne
# sie liest AuthVariableLib den Eintrag als unauthentifiziert und der
# Plattformschluessel zaehlt nicht.
EFI_VARIABLE_AUTHENTICATED = 0x27

FV_SIGNATURE = b"_FVH"

# Die Vorlage, aus der ein eingetragener Speicher entsteht. Dieselbe
# Liste wie OVMF_VARS_CANDIDATES in iso/test-boot.py und bewusst nicht
# aus ihr importiert: diese Datei muss ohne test-boot.py benutzbar sein,
# und zwei Listen von vier Pfaden sind billiger als ein Importzyklus.
OVMF_VARS_CANDIDATES = (
    Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd"),
    Path("/usr/share/edk2/x64/OVMF_VARS.fd"),
    Path("/usr/share/OVMF/OVMF_VARS.fd"),
    Path("/usr/share/ovmf/x64/OVMF_VARS.fd"),
)

# Die Firmware, die Secure Boot ueberhaupt erzwingen kann. Die gewoehn-
# liche OVMF_CODE.4m.fd ist ohne SECURE_BOOT_ENABLE gebaut und laesst
# auch mit eingetragenem Schluessel alles durch - das ist der Fehlschlag,
# der wie ein Erfolg aussieht, und deshalb steht die Liste getrennt.
OVMF_SECBOOT_CODE_CANDIDATES = (
    Path("/usr/share/edk2/x64/OVMF_CODE.secboot.4m.fd"),
    Path("/usr/share/edk2/x64/OVMF_CODE.secboot.fd"),
    Path("/usr/share/OVMF/OVMF_CODE.secboot.fd"),
)

# Die Dateien im gebauten Medium, die eine Firmware mit Secure Boot
# nacheinander pruefen wuerde. Der Ladeweg ist
# Firmware -> EFI/BOOT/BOOTx64.EFI -> Kernel, und mkarchiso baut den
# mittleren Schritt mit grub-mkstandalone, weshalb es kein getrenntes
# grubx64.efi gibt, das hier fehlen koennte.
#
# BOOTIA32.EFI steht mit in der Liste, obwohl keine 64-Bit-Firmware ihn
# je laedt: eine 32-Bit-UEFI-Maschine nimmt genau diesen, und "die Kette
# ist unsigniert" waere sonst eine Aussage ueber die Haelfte des Mediums.
BOOT_CHAIN = (
    "EFI/BOOT/BOOTx64.EFI",
    "EFI/BOOT/BOOTIA32.EFI",
    "zepos/boot/x86_64/vmlinuz-linux",
)


# --------------------------------------------------------------------
# Was in einer PE-Datei steht
# --------------------------------------------------------------------
class NotPortableExecutable(ValueError):
    """Die Datei ist kein PE/COFF-Abbild.

    Ein eigener Typ und keine nackte ValueError, weil der Aufrufer die
    beiden Faelle unterscheiden koennen muss: eine Datei, die kein PE
    ist, kann von einer Firmware gar nicht geladen werden, und eine, die
    eines ist und keine Signatur traegt, wird geladen und abgelehnt. Das
    sind zwei verschiedene Befunde.
    """


def certificate_table(image: bytes) -> tuple[int, int]:
    """(Offset, Groesse) der Authenticode-Signatur, oder (0, 0).

    Eintrag 4 des Data Directory, IMAGE_DIRECTORY_ENTRY_SECURITY. Er ist
    der einzige, dessen erstes Feld KEINE relative virtuelle Adresse ist,
    sondern ein Dateioffset - genau deshalb kann eine Signatur angehaengt
    werden, ohne das Abbild neu zu binden.

    Ohne Fremdbibliothek, weil das hier vier Feldzugriffe sind: die
    Alternative waere pefile, und eine Abhaengigkeit fuer vier
    struct.unpack_from ist eine Abhaengigkeit zu viel in einem Werkzeug,
    das auf einem frisch gebauten Rechner laufen koennen soll.
    """
    if image[:2] != b"MZ":
        raise NotPortableExecutable("kein MZ-Kopf")
    if len(image) < 0x40:
        raise NotPortableExecutable("zu kurz fuer einen DOS-Kopf")

    pe_offset = struct.unpack_from("<I", image, 0x3C)[0]
    if len(image) < pe_offset + 24 or image[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise NotPortableExecutable("keine PE-Signatur")

    optional_header = pe_offset + 24
    magic = struct.unpack_from("<H", image, optional_header)[0]
    if magic == 0x20B:          # PE32+
        directories_at = optional_header + 108
    elif magic == 0x10B:        # PE32
        directories_at = optional_header + 92
    else:
        raise NotPortableExecutable(f"unbekanntes Optional-Header-Magic {magic:#x}")

    count = struct.unpack_from("<I", image, directories_at)[0]
    if count < 5:
        # Eine Firmware kann hier nicht nachsehen, also gibt es auch
        # keine Signatur. Kein Fehler, ein Befund.
        return (0, 0)
    offset, size = struct.unpack_from("<II", image, directories_at + 4 + 8 * 4)
    return (offset, size)


def is_signed(image: bytes) -> bool:
    """Ob das Abbild eine Authenticode-Signatur mitbringt.

    Nicht, ob sie GUELTIG ist - das kann nur die Firmware gegen ihre
    eigene db entscheiden. Was diese Funktion beantwortet, ist die Frage
    davor: ob ueberhaupt etwas da ist, das geprueft werden koennte.
    """
    offset, size = certificate_table(image)
    return offset != 0 and size != 0


# --------------------------------------------------------------------
# Was in einem UEFI-Variablenspeicher steht
# --------------------------------------------------------------------
def signature_list(certificate_der: bytes,
                   owner: uuid.UUID = ZEPOS_SIGNATURE_OWNER) -> bytes:
    """Ein X.509-Zertifikat als EFI_SIGNATURE_LIST.

    Genau ein Zertifikat pro Liste, und das ist keine Vereinfachung: die
    Struktur traegt ein einziges SignatureSize fuer alle Eintraege, und
    zwei X.509-Zertifikate sind fast nie gleich lang. Wer zwei will,
    haengt zwei Listen aneinander - das ist auch das, was jede Firmware
    tut, die man sich ansieht.
    """
    signature = owner.bytes_le + certificate_der
    return (
        EFI_CERT_X509_GUID.bytes_le
        + struct.pack("<III",
                      16 + 4 + 4 + 4 + len(signature),  # SignatureListSize
                      0,                                # SignatureHeaderSize
                      len(signature))                   # SignatureSize
        + signature
    )


def variable_record(name: str, vendor: uuid.UUID, data: bytes,
                    attributes: int = EFI_VARIABLE_AUTHENTICATED) -> bytes:
    """Ein AUTHENTICATED_VARIABLE_HEADER samt Name und Daten.

    Der Zeitstempel bleibt null. Er ist der Schutz gegen das Zuruecksetzen
    auf eine aeltere signierte Fassung, und hier wird nicht ueber die
    Laufzeitschnittstelle geschrieben, sondern in die Datei - wo es
    ohnehin keine Signatur gibt, gegen die er zaehlen koennte. Ein
    Nullstempel heisst nur, dass die Firmware jede spaetere
    authentifizierte Aenderung annehmen wuerde, und das ist genau das
    Verhalten einer Maschine, auf der jemand gerade Schluessel eingetragen
    hat.
    """
    encoded = name.encode("utf-16-le") + b"\0\0"
    record = (
        struct.pack("<HBBI", VARIABLE_DATA, VAR_ADDED, 0, attributes)
        + struct.pack("<Q", 0)          # MonotonicCount
        + bytes(16)                     # EFI_TIME
        + struct.pack("<III", 0, len(encoded), len(data))
        + vendor.bytes_le
        + encoded
        + data
    )
    assert len(record) == AUTH_VARIABLE_HEADER_SIZE + len(encoded) + len(data)
    padding = -len(record) % HEADER_ALIGNMENT
    return record + b"\xff" * padding


def variable_store_bounds(template: bytes) -> tuple[int, int]:
    """(Anfang, Ende) des Variablenbereichs in einer OVMF_VARS-Datei.

    Gelesen und nicht angenommen. Die Datei faengt mit einem
    EFI_FIRMWARE_VOLUME_HEADER an, dessen HeaderLength sagt, wo der
    Variablenspeicher beginnt. Bei der 4-MB-Fassung von Arch sind das 72
    Byte - 56 fuer den festen Teil, dann eine Blockkarte aus einem
    Eintrag und ihrem Abschluss zu je acht. Eine Firmware, die den
    Speicher in zwei verschieden grossen Blockgruppen fuehrt, hat 80, und
    ein festverdrahtetes 72 waere dort ein Werkzeug, das die Blockkarte
    fuer den Anfang der Variablen haelt und sie ueberschreibt.
    """
    if template[40:44] != FV_SIGNATURE:
        raise ValueError("keine _FVH-Signatur - das ist kein Firmware-Volume")
    header_length = struct.unpack_from("<H", template, 48)[0]

    guid = uuid.UUID(bytes_le=template[header_length:header_length + 16])
    if guid != AUTHENTICATED_VARIABLE_STORE_GUID:
        raise ValueError(
            f"der Variablenspeicher hat die Kennung {guid}, erwartet war "
            f"{AUTHENTICATED_VARIABLE_STORE_GUID} - eine Vorlage ohne "
            f"authentifizierte Variablen kann keinen Plattformschluessel "
            f"tragen"
        )
    size, form, state = struct.unpack_from("<IBB", template, header_length + 16)
    if form != VARIABLE_STORE_FORMATTED or state != VARIABLE_STORE_HEALTHY:
        raise ValueError(
            f"der Variablenspeicher ist Format {form:#x} Zustand {state:#x}, "
            f"erwartet war {VARIABLE_STORE_FORMATTED:#x}/"
            f"{VARIABLE_STORE_HEALTHY:#x}"
        )
    return (header_length + 16 + 12, header_length + size)


def enroll(template: bytes, certificate_der: bytes) -> bytes:
    """Ein OVMF-Variablenspeicher mit PK, KEK und db aus einem Zertifikat.

    Alle drei aus DEMSELBEN Zertifikat, weil die Frage, die dieser
    Speicher beantworten soll, keine ueber Schluesselhierarchien ist. Was
    eine Firmware beim Laden prueft, ist db; PK ist das, was sie aus dem
    Setup Mode holt und damit ueberhaupt erst pruefen laesst; KEK steht
    dazwischen und wird beim Laden nie gelesen. Ein Speicher ohne KEK
    waere trotzdem eine Firmware, die es so nicht gibt.

    Die Vorlage muss leer sein. Sonst muesste diese Funktion entscheiden,
    was mit einem schon vorhandenen PK geschieht, und die einzige
    ehrliche Antwort darauf waere, dass ein Werkzeug zum Aufsetzen eines
    Messaufbaus die Frage nicht zu beantworten hat.
    """
    start, end = variable_store_bounds(template)
    first = struct.unpack_from("<H", template, start)[0]
    if first == VARIABLE_DATA:
        raise ValueError(
            "die Vorlage enthaelt bereits Variablen - enroll() schreibt nur "
            "in einen leeren Speicher"
        )

    payload = signature_list(certificate_der)
    records = (
        variable_record("PK", EFI_GLOBAL_VARIABLE_GUID, payload)
        + variable_record("KEK", EFI_GLOBAL_VARIABLE_GUID, payload)
        + variable_record("db", EFI_IMAGE_SECURITY_DATABASE_GUID, payload)
    )
    if start + len(records) > end:
        raise ValueError(
            f"die drei Eintraege brauchen {len(records)} Byte, im "
            f"Variablenbereich sind {end - start} frei"
        )
    return template[:start] + records + template[start + len(records):]


def read_variables(store: bytes) -> list[dict]:
    """Die Eintraege eines Variablenspeichers, als Liste von Angaben.

    Die Gegenrichtung von enroll(), und sie ist der Grund, warum enroll()
    ueberhaupt geprueft werden kann: ein Speicher, den nur der eigene
    Schreiber lesen kann, ist ein Speicher, dessen Fehler erst OVMF
    findet - also in einem Lauf, der zwanzig Sekunden dauert und dessen
    einzige Aussage "startet nicht" waere.
    """
    start, end = variable_store_bounds(store)
    found: list[dict] = []
    offset = start
    while offset + AUTH_VARIABLE_HEADER_SIZE <= end:
        start_id, state, _reserved, attributes = struct.unpack_from(
            "<HBBI", store, offset)
        if start_id != VARIABLE_DATA:
            break
        name_size, data_size = struct.unpack_from("<II", store, offset + 36)
        vendor = uuid.UUID(bytes_le=store[offset + 44:offset + 60])
        name_at = offset + AUTH_VARIABLE_HEADER_SIZE
        name = store[name_at:name_at + name_size].decode("utf-16-le").rstrip("\0")
        data = store[name_at + name_size:name_at + name_size + data_size]
        found.append({"name": name, "vendor": vendor, "state": state,
                      "attributes": attributes, "data": data})
        offset = name_at + name_size + data_size
        offset += -offset % HEADER_ALIGNMENT
    return found


# --------------------------------------------------------------------
# Der Wegwerfschluessel
# --------------------------------------------------------------------
def make_platform_key(directory: Path) -> tuple[Path, Path]:
    """Ein selbstsigniertes Zertifikat, einmal erzeugt und dann behalten.

    Behalten aus demselben Grund, aus dem iso/test-boot.py seinen
    Variablenspeicher behaelt: der Lauf, der eine SIGNIERTE Kette misst,
    muss mit demselben Schluessel signieren, den der Lauf davor in die
    Firmware geschrieben hat. Ein bei jedem Aufruf neuer Schluessel waere
    ein Messaufbau, in dem die Gegenprobe nie gelingen kann.

    openssl und nicht python-cryptography: cryptography ist in der
    Umgebung dieses Projekts nicht installiert (gemessen 11.08.2026),
    openssl ist eine Abhaengigkeit von pacman selbst und damit auf jedem
    Arch-System da, auf dem dieses Werkzeug ueberhaupt sinnvoll ist.

    -addext basicConstraints=critical,CA:TRUE, weil ein
    Plattformschluessel ein Zertifizierungsschluessel ist: er signiert
    KEK, KEK signiert db. Ein Blattzertifikat an dieser Stelle ist ein
    Speicher, mit dem sich nichts weiter eintragen laesst.
    """
    directory.mkdir(parents=True, exist_ok=True)
    key = directory / "secboot-platform.key"
    certificate = directory / "secboot-platform.der"
    if key.is_file() and certificate.is_file():
        return (key, certificate)

    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(certificate), "-outform", "DER",
         "-days", "3650", "-sha256",
         "-subj", "/CN=ZepOS Secure Boot measurement key/O=ZeptronIT/",
         "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,digitalSignature,keyCertSign"],
        check=True, capture_output=True)
    key.chmod(0o600)
    return (key, certificate)


def secure_boot_variables(out: Path = OUT) -> Path:
    """Der eingetragene Variablenspeicher, erzeugt falls noch nicht da.

    Der Rueckgabewert ist der Pfad, den iso/test-boot.py an QEMU haengt.
    Neben efivars.fd und release-efivars.fd, und mit einem dritten Namen,
    weil ein Speicher mit Plattformschluessel und einer ohne nicht
    dasselbe Messmittel sind und ein Lauf, der versehentlich den falschen
    nimmt, keinen Fehler machen wuerde - nur eine andere Antwort geben.
    """
    store = out / "secboot-efivars.fd"
    if store.is_file():
        return store
    template = first_existing(OVMF_VARS_CANDIDATES, "OVMF-Variablenvorlage")
    _key, certificate = make_platform_key(out)
    out.mkdir(parents=True, exist_ok=True)
    store.write_bytes(enroll(template.read_bytes(), certificate.read_bytes()))
    return store


def first_existing(candidates, what: str) -> Path:
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit(
        f"kein {what} gefunden. Auf Arch liegt beides im Paket edk2-ovmf. "
        f"Gesucht in: " + ", ".join(str(path) for path in candidates)
    )


# --------------------------------------------------------------------
# Die Startkette eines gebauten Mediums
# --------------------------------------------------------------------
def read_from_iso(iso: Path, member: str) -> bytes:
    """Eine Datei aus einem ISO9660-Abbild, ohne es einzuhaengen.

    bsdtar und nicht mount: ein Einhaengen braucht root oder eine
    Schleifeneinrichtung, und die Frage, ob eine Datei signiert ist, ist
    keine, fuer die ein Messwerkzeug Rechte verlangen sollte. bsdtar
    kommt mit libarchive und damit mit pacman.
    """
    result = subprocess.run(["bsdtar", "-xOf", str(iso), member],
                            capture_output=True)
    if result.returncode != 0 or not result.stdout:
        raise FileNotFoundError(
            f"{member} nicht in {iso.name}: "
            f"{result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def inspect_boot_chain(iso: Path) -> list[dict]:
    """Was jede Stufe der Startkette an Signatur mitbringt."""
    report = []
    for member in BOOT_CHAIN:
        entry: dict = {"member": member}
        try:
            image = read_from_iso(iso, member)
        except FileNotFoundError as missing:
            entry["error"] = str(missing)
            report.append(entry)
            continue
        entry["bytes"] = len(image)
        try:
            offset, size = certificate_table(image)
        except NotPortableExecutable as reason:
            entry["error"] = f"kein PE/COFF-Abbild: {reason}"
        else:
            entry["signed"] = offset != 0 and size != 0
            entry["certificate_offset"] = offset
            entry["certificate_bytes"] = size
        report.append(entry)
    return report


# --------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    look = sub.add_parser("inspect", help="Signaturen der Startkette")
    look.add_argument("--iso", type=Path, help="ein bestimmtes Medium")

    keys = sub.add_parser("enroll", help="Variablenspeicher mit Schluessel")
    keys.add_argument("--out", type=Path, default=OUT,
                      help="Verzeichnis fuer Speicher und Schluessel")

    arguments = parser.parse_args()

    if arguments.command == "enroll":
        store = secure_boot_variables(arguments.out)
        entries = read_variables(store.read_bytes())
        print(f"Variablenspeicher {store} ({store.stat().st_size} Byte)")
        for entry in entries:
            print(f"  {entry['name']:<4} {entry['vendor']} "
                  f"Attribute {entry['attributes']:#x} "
                  f"{len(entry['data'])} Byte")
        return 0

    iso = arguments.iso
    if iso is None:
        images = sorted(OUT.glob("zepos-*-x86_64.iso"),
                        key=lambda path: path.stat().st_mtime)
        images = [path for path in images if "smoke" not in path.name]
        if not images:
            raise SystemExit("kein zepos-*.iso in iso/out/ - "
                             "erst ./iso/build.sh --profile release")
        iso = images[-1]

    print(f"Medium {iso.name}")
    unsigned = 0
    for entry in inspect_boot_chain(iso):
        if "error" in entry:
            print(f"  {entry['member']:<34} {entry['error']}")
            continue
        state = "signiert" if entry["signed"] else "OHNE SIGNATUR"
        unsigned += 0 if entry["signed"] else 1
        print(f"  {entry['member']:<34} {entry['bytes']:>9} Byte  {state}")
    print(f"\n{unsigned} von {len(BOOT_CHAIN)} Stufen ohne Signatur.")
    if unsigned:
        print("Eine Firmware mit aktivem Secure Boot lehnt die erste davon ab,\n"
              "bevor irgendetwas von ZepOS laeuft.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
