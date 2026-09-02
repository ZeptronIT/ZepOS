# SPDX-License-Identifier: GPL-3.0-or-later
import gettext
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from installer.core.i18n import (
    DOMAIN, SUPPORTED_LANGUAGES, _, activate, current_language,
)

# Anchored on this file, never on the working directory.
#
# This is the bug this repository already hit once, and it is the one a
# relative path always produces: pytest can be started from anywhere, and
# Path("po/de.po") then measures whatever directory the developer
# happened to be standing in. Run from a cwd that merely CONTAINS a
# po/de.po - a sibling checkout, a packaging tree - this file reported
# "11 passed" having opened not one source file of this project.
# tests/src/test_naming.py carries the same note for the same reason.
REPOSITORY = Path(__file__).resolve().parents[2]
PO_FILE = REPOSITORY / "po" / "de.po"
INSTALLER = REPOSITORY / "installer"


def _translatable_sources() -> list[Path]:
    """Every file that can contain a `_("...")` call.

    Not `rglob("*.py")`. installer/bin/zepos-install is the SHIPPED entry
    point, it carries two translated messages, and it has no suffix -
    nobody types "zepos-install.py" - so a suffix filter walked past the
    one file every user starts. Selected the way tests/src/test_naming.py
    selects the three src/bin commands, and for the same reason.
    """
    files = []
    for path in sorted(INSTALLER.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix == ".py":
            files.append(path)
        elif not path.suffix:
            try:
                with path.open("rb") as handle:
                    if handle.read(2) == b"#!":
                        files.append(path)
            except OSError:
                pass
    return files


class FakeTranslation(gettext.NullTranslations):
    def __init__(self, mapping):
        super().__init__()
        self._mapping = mapping

    def gettext(self, message):
        return self._mapping.get(message, message)


@pytest.fixture(autouse=True)
def _reset_catalogue():
    """activate() sets module state. If the German catalogue remained active
    after these tests, other modules' tests would no longer find their English
    msgids."""
    yield
    activate("en")


def test_supported_languages_are_english_and_german():
    assert SUPPORTED_LANGUAGES == ("en", "de")


def test_domain_is_stable():
    """The domain name appears later in the .mo filename — changes break
    every installed translation."""
    assert DOMAIN == "zepos-installer"


def test_untranslated_message_falls_back_to_msgid():
    activate("en")
    assert _("Installation failed.") == "Installation failed."


def test_activate_switches_the_catalogue():
    activate("de", translation=FakeTranslation({"Installation failed.": "Die Installation ist fehlgeschlagen."}))
    assert _("Installation failed.") == "Die Installation ist fehlgeschlagen."
    assert current_language() == "de"


def test_unknown_language_does_not_raise_and_yields_msgid():
    activate("kl")
    assert _("Installation failed.") == "Installation failed."


def test_missing_catalogue_does_not_raise(tmp_path):
    activate("de", localedir=tmp_path)
    assert _("Installation failed.") == "Installation failed."


def test_corrupt_catalogue_does_not_raise(tmp_path):
    """An interrupted installation can leave a half-written .mo file.
    gettext then raises struct.error — this is NOT an OSError and must
    still be caught or the installer won't start."""
    target = tmp_path / "de" / "LC_MESSAGES"
    target.mkdir(parents=True)
    (target / "zepos-installer.mo").write_bytes(b"\xde\x12\x04")
    activate("de", localedir=tmp_path)
    assert _("Installation failed.") == "Installation failed."


def test_german_catalogue_exists_and_is_not_empty():
    """Not `'msgstr ""' in po`.

    Every PO file opens with a mandatory header entry whose msgid and
    msgstr are both the empty string, so that assertion was satisfied by
    the two lines gettext requires and could not have failed over an
    otherwise empty catalogue. Measured: truncating de.po to its header
    alone left it green - and an empty msgstr is the very thing
    test_every_msgid_in_the_german_catalogue_has_a_translation refuses,
    so the check was not merely weak but pointed the wrong way.

    What is actually meant is "there are translated entries in here",
    which is what is counted.
    """
    assert PO_FILE.exists(), "po/de.po fehlt - Deutsch waere dann nicht gepflegt"
    text = PO_FILE.read_text(encoding="utf-8")

    translated = re.findall(r'^msgid "(.+)"\nmsgstr "(.+)"', text, re.MULTILINE)
    assert len(translated) > 10, (
        f"only {len(translated)} translated entries in the catalogue - a "
        "German user would read the installer in English")


def test_every_msgid_in_the_german_catalogue_has_a_translation():
    """An empty msgstr means the user sees English even though they chose
    German."""
    text = PO_FILE.read_text(encoding="utf-8")
    entries = re.findall(r'^msgid "(.+)"\nmsgstr "(.*)"', text, re.MULTILINE)
    # Plural entries, which the pattern above cannot see: msgid_plural
    # sits between the msgid and the first msgstr. Every form must be
    # filled, so each is checked on its own.
    for singular, plural, block in re.findall(
            r'^msgid "(.+)"\nmsgid_plural "(.+)"\n((?:msgstr\[\d+\] ".*"\n)+)',
            text, re.MULTILINE):
        forms = re.findall(r'msgstr\[\d+\] "(.*)"', block)
        assert forms, f"{singular}/{plural} has no plural forms at all"
        entries.extend((f"{singular}/{plural}", form) for form in forms)
    assert len(entries) > 10, (
        f"only {len(entries)} entries parsed out of the catalogue - "
        "'no untranslated entries' is also what an empty list answers")
    untranslated = [msgid for msgid, msgstr in entries if not msgstr]
    assert untranslated == [], f"ohne Uebersetzung: {untranslated}"


def test_schema_version_message_is_translated():
    """The message from Task 1 — the reason for this task."""
    text = PO_FILE.read_text(encoding="utf-8")
    assert "unsupported schema_version" in text


CALL = re.compile(r'_\(\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE)

# ngettext("one", "many", n) - two msgids per call, and neither is
# reachable through CALL above: that pattern anchors on `_(`, and this
# call ends in `t(`. Both forms have to be in the catalogue, and the
# plural one has to be there as msgid_plural, so the extraction returns
# them separately rather than as one string.
PLURAL_CALL = re.compile(
    r'ngettext\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"',
    re.MULTILINE)


def _msgids(text: str) -> list[tuple[str, str]]:
    """Every translatable string in one source file, each paired with the
    PO keyword the catalogue must spell it under."""
    found = [("msgid", m) for m in CALL.findall(text)]
    for singular, plural in PLURAL_CALL.findall(text):
        found.append(("msgid", singular))
        found.append(("msgid_plural", plural))
    return found


def test_the_scan_actually_reads_the_installer():
    """The guard's own blind spot, held open.

    A scan that opens nothing reports exactly the same "clean" as a
    project with nothing wrong in it - and with the relative path this
    file used to carry, opening nothing is what it did from any working
    directory but one. Neither the file count nor the msgid count below
    can be satisfied by an empty or misdirected scan.

    installer/bin/zepos-install is named explicitly because it is the
    file the suffix filter used to skip: the shipped entry point, with
    two translated messages in it, invisible to the completeness check
    that exists to find exactly those.
    """
    sources = _translatable_sources()
    assert len(sources) > 10, (
        f"only {len(sources)} source files found under {INSTALLER} - the "
        "scan is not reading the installer, so its result means nothing")

    names = {path.relative_to(REPOSITORY).as_posix() for path in sources}
    assert "installer/bin/zepos-install" in names, (
        "the shipped entry point is not read by the completeness check")

    found = [msgid for path in sources
             for msgid in CALL.findall(path.read_text(encoding="utf-8"))]
    assert len(found) > 20, (
        f"only {len(found)} translated messages found in {len(sources)} "
        "files - the pattern has stopped matching")


def test_every_msgid_in_the_source_is_in_the_catalogue():
    """A msgid present in code but missing from po/de.po means a German
    user silently sees English. The existing completeness test only checks
    the opposite direction and cannot catch this."""
    catalogue = PO_FILE.read_text(encoding="utf-8")

    missing = []
    checked = 0
    for source in _translatable_sources():
        for keyword, msgid in _msgids(source.read_text(encoding="utf-8")):
            checked += 1
            if f'{keyword} "{msgid}"' not in catalogue:
                missing.append(f"{source.relative_to(REPOSITORY)}: {msgid}")

    # "missing == []" is also what a scan that read nothing answers.
    assert checked, "no translated message was checked at all"
    assert missing == [], "msgids without a catalogue entry: " + "; ".join(missing)


# --------------------------------------------------------------------
# Das Ergebnis, nicht die Quelle
# --------------------------------------------------------------------
#
# DIESELBE LUECKE, DIE AM 02.09.2026 IM KATALOG DER OBERFLAECHE BEINAHE
# TEUER GEWORDEN IST - hier vorbeugend geschlossen, denn dieser Katalog
# hat sie auch.
#
#     Dort brachte ein Auftrag zwei neue Saetze ein. Beide standen
#     danach mit `#, fuzzy` in de.po, weil aus EINEM msgid mit "\n"
#     darin ZWEI geworden waren und `msgmerge` seine Zuordnung
#     vorsichtshalber als unsicher markiert hatte.
#
#         msgfmt nimmt einen fuzzy markierten Eintrag NICHT in die .mo
#         auf.
#
#     Die Uebersetzung stand also lesbar in der Quelldatei und kam beim
#     Nutzer nicht an. Ueber gettext nachgeschlagen gaben beide msgids
#     ihren englischen Text zurueck.
#
# WARUM DIE PRUEFUNGEN DARUEBER DAS NICHT SEHEN
#     Sie lesen den TEXT von po/de.po und verlangen einen nicht leeren
#     msgstr. Der war nicht leer. Und `#, fuzzy` steht eine Zeile
#     DARUEBER und in keinem ihrer Muster - geprueft wird die EINGABE
#     statt des ERGEBNISSES.
#
# WER IN DIESE GRUBE FAELLT
#     Jeder, der einen msgid aufteilt oder umformuliert und danach
#     `msgmerge` laufen laesst, also jeder, der einen Satz des
#     Assistenten verbessert. Und beim Assistenten wiegt es schwerer als
#     sonstwo: seine Saetze liest ein Mensch, der gerade ein System
#     installiert und dabei eine Platte loescht.
#
# GEZAEHLT am 02.09.2026: po/de.po hat 0 fuzzy-Marken und 0 msgctxt,
# 183 uebersetzte Meldungen. Diese zwei Zusicherungen halten das.

def _catalogue_entries(text: str) -> dict[tuple[str, str], str]:
    """Jeder einfache Eintrag als (context, msgid) -> msgstr.

    Der Zusatz gehoert zum Schluessel, auch wenn dieser Katalog heute
    keinen einzigen msgctxt hat: sonst waere die erste
    Unterscheidung nach Zusammenhang ein grundloser Fehlschlag. Genau
    das ist der Zwillingsdatei in tests/src/test_ags_i18n.py passiert,
    wo es drei solche Eintraege gibt.

    Mehrzahlformen bleiben aussen vor - fuer sie gilt "ein msgid, ein
    msgstr" nicht, und test_every_catalogue_entry_is_translated deckt
    sie ab.
    """
    found: dict[tuple[str, str], str] = {}
    for hit in re.finditer(
            r'^(?:msgctxt "((?:[^"\\]|\\.)*)"\n)?'
            r'^msgid "((?:[^"\\]|\\.)+)"\n'
            r'^msgstr "((?:[^"\\]|\\.)*)"$',
            text, re.M):
        context, msgid, msgstr = hit.groups()
        found[(context or "", msgid)] = msgstr
    return found


def test_no_catalogue_entry_is_marked_fuzzy():
    """`#, fuzzy` heisst hier: der Satz kommt englisch beim Nutzer an.

    Der eine legitime Fall fuer so eine Marke ist der KOPFEINTRAG einer
    .pot - xgettext schreibt sie dort, damit ein Werkzeug die
    Platzhalter erkennt ("FIRST AUTHOR <EMAIL@ADDRESS>"). Eine .pot wird
    nie nachgeschlagen; sie ist die Liste der Fragen.

    In einer de.po gibt es den Fall nicht. Ein fuzzy markierter Eintrag
    ist dort eine Uebersetzung, die dasteht und nicht ausgeliefert wird -
    und das ist die schlechteste der drei Lagen, weil sie beim Lesen der
    Datei wie erledigte Arbeit aussieht.
    """
    fuzzy = [line for line in PO_FILE.read_text(encoding="utf-8").splitlines()
             if line.startswith("#,") and "fuzzy" in line]
    assert fuzzy == [], (
        f"{len(fuzzy)} Eintrag/Eintraege in {PO_FILE.name} sind `#, fuzzy` "
        "markiert. msgfmt laesst sie AUS der .mo weg - die Uebersetzung "
        "steht in der Datei und kommt beim Nutzer nicht an. Pruef die "
        "Vermutung von msgmerge und nimm die Marke weg.")


@pytest.mark.allow_subprocess
def test_the_built_catalogue_really_hands_out_every_translation(tmp_path):
    """Gebaut mit msgfmt, gefragt mit gettext - wie der Installer fragt.

    po/build.sh ruft msgfmt, installer/core/i18n.py ruft
    gettext.translation() auf die Domaene zepos-installer. Zwischen
    po/de.po und dem Menschen stehen genau diese zwei Werkzeuge, und was
    msgfmt weglaesst, kann diese Zusicherung nicht fuer vorhanden
    halten.

    Verglichen wird mit dem ERWARTETEN Text und nicht auf "ungleich dem
    msgid": ein Eintrag, dessen Uebersetzung zufaellig gleich dem
    Englischen ist, waere sonst unpruefbar, und ein doppelt
    zusammengeklebter msgstr - der Fall vom 02.09.2026 - ist AUCH
    ungleich dem msgid und trotzdem keine Uebersetzung.
    """
    if shutil.which("msgfmt") is None:
        pytest.skip("msgfmt fehlt; es kommt mit dem Paket gettext")

    target = tmp_path / "de" / "LC_MESSAGES"
    target.mkdir(parents=True)
    built = subprocess.run(
        ["msgfmt", "--statistics", "-o", str(target / f"{DOMAIN}.mo"),
         str(PO_FILE)],
        capture_output=True, text=True)
    assert built.returncode == 0, (
        f"msgfmt uebersetzt {PO_FILE.name} nicht:\n{built.stderr}")

    # Die Zaehlung nennt "ungenau"/"fuzzy" nur, wenn es solche Eintraege
    # GIBT - ihr blosses Vorkommen ist der Befund. Auf die Sprache der
    # Umgebung kommt es dabei an, deshalb beide Schreibweisen.
    assert "fuzz" not in built.stderr and "ungenau" not in built.stderr, (
        f"msgfmt zaehlt ungenaue Meldungen in {PO_FILE.name} - genau die "
        f"landen NICHT in der .mo: {built.stderr.strip()}")
    assert "untransl" not in built.stderr and "unuebersetzt" not in built.stderr, (
        f"msgfmt zaehlt unuebersetzte Meldungen: {built.stderr.strip()}")

    expected = _catalogue_entries(PO_FILE.read_text(encoding="utf-8"))
    assert len(expected) > 100, (
        f"nur {len(expected)} Eintraege ausgelesen - 'alles kommt an' ist "
        "auch die Antwort auf eine leere Liste")

    def unescaped(raw: str) -> str:
        return raw.replace('\\"', '"').replace("\\n", "\n")

    catalogue = gettext.translation(DOMAIN, str(tmp_path), languages=["de"])
    missing = []
    for (context, msgid), msgstr in sorted(expected.items()):
        if context:
            delivered = catalogue.pgettext(unescaped(context),
                                           unescaped(msgid))
        else:
            delivered = catalogue.gettext(unescaped(msgid))
        if delivered != unescaped(msgstr):
            where = f"{msgid!r}" if not context else f"{msgid!r} [{context}]"
            missing.append(f"{where}: de.po sagt {unescaped(msgstr)!r}, der "
                           f"gebaute Katalog gibt {delivered!r}")
    assert missing == [], (
        f"{len(missing)} Uebersetzung(en) stehen in {PO_FILE.name} und "
        "kommen aus dem gebauten Katalog nicht heraus - fast immer eine "
        "`#, fuzzy`-Marke:\n  " + "\n  ".join(missing[:10]))
