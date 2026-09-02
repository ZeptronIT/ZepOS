# SPDX-License-Identifier: GPL-3.0-or-later
""".desktop-Dateien sprechen die Sprache ihres Lesers.

WORAUF DIESE DATEI ANTWORTET
    Bis zum 02.09.2026 trugen alle drei ausgelieferten .desktop-Dateien
    ihren sichtbaren Text NUR auf Deutsch, und zwar im unbezeichneten
    Schluessel - also in der Ausgangssprache. Wer ZepOS auf Englisch
    installierte, fand im Starter "Systemeinstellungen" mit acht
    deutschen Aktionen darunter, im Anmeldebildschirm einen deutschen
    Sitzungstext, und beim Assistenten einen deutschen Untertitel.

    Es ist dieselbe Fehlerklasse wie beim Anwendungsstarter, der am
    selben Tag an den Katalog gekommen ist - nur in einem Dateiformat,
    das an JEDEM Katalog vorbeilaeuft. Genau deshalb hat es keine der
    beiden Katalogpruefungen gefunden: po/desktop/de.po weiss nichts von
    .desktop-Dateien, und xgettext liest sie in diesem Baum nicht.

WIE EINE .desktop-DATEI UEBERSETZT WIRD
    Sie uebersetzt sich SELBST. Der unbezeichnete Schluessel traegt die
    Ausgangssprache, die bezeichneten die Uebersetzungen:

        Name=System settings
        Name[de]=Systemeinstellungen

    Jeder Leser - Starter, Menue, Greeter, Arbeitsumgebung - nimmt den
    Schluessel zur Sprache seiner Umgebung und faellt auf den
    unbezeichneten zurueck. Ein deutscher Text IM unbezeichneten
    Schluessel ist damit keine Uebersetzung, sondern eine falsche
    Ausgangssprache: er erreicht jeden, dessen Sprache nicht
    ausdruecklich dasteht.

WAS DIESE PRUEFUNG SIEHT UND WAS NICHT
    Sie erkennt Deutsch am UMLAUT - dieselbe Regel und derselbe Grund
    wie in tests/src/test_ags_i18n.py und tests/src/test_starter_i18n.py.
    Ein deutsches Wort ohne Umlaut ("Leiste", "Thema") faellt ihr nicht
    auf; sie ist die Untergrenze und nicht der Beweis. Was daneben
    steht: tests/settings/test_settings_model.py haelt jede Aktion der
    Einstellungsdatei einzeln gegen model.PAGES und verlangt fuer jede
    BEIDE Schluessel.
"""
from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]

# Die Schluessel, deren Wert ein Mensch LIEST. Nicht Exec, TryExec,
# Icon, Categories, Type - das sind Pfade, Namen aus einem Symbolthema
# und Begriffe der Spezifikation, und keins davon uebersetzt jemand.
SICHTBARE_SCHLUESSEL = ("Name", "GenericName", "Comment", "Keywords")

UMLAUTE = re.compile(r"[ÄÖÜäöüß]")

# Wo eine bezeichnete Fassung steht: Name[de], Comment[de_DE], ...
BEZEICHNET = re.compile(r"^([A-Za-z-]+)\[([^\]]+)\]$")


def _dateien() -> list[Path]:
    """Jede .desktop-Datei dieses Baums.

    Gesucht und nicht aufgezaehlt: eine Liste hier waere die erste
    Stelle, an der eine vierte Datei fehlt - und eine vierte Datei ist
    genau der Fall, in dem jemand die Umstellung nicht mitmacht. Der
    Bauplatz bleibt aussen vor, dort liegen Abschriften.
    """
    return sorted(
        pfad for pfad in WURZEL.rglob("*.desktop")
        if ".git" not in pfad.parts
        and "packaging/out" not in pfad.as_posix()
        and "iso/work" not in pfad.as_posix()
        and "po/build" not in pfad.as_posix())


def _gruppen(pfad: Path) -> dict[str, dict[str, str]]:
    """Die Datei nach ihren Gruppen getrennt, Kommentare weg.

    Getrennt, weil eine Datei mit Desktop Actions mehrere Gruppen hat
    und ein flacher Leser das letzte `Name=` fuer das der Anwendung
    hielte - derselbe Befund, den tests/settings/test_settings_model.py
    schon einmal bezahlt hat.
    """
    gruppen: dict[str, dict[str, str]] = {}
    jetzt: dict[str, str] = {}
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        roh = zeile.strip()
        if not roh or roh.startswith("#"):
            continue
        if roh.startswith("[") and roh.endswith("]"):
            jetzt = gruppen.setdefault(roh[1:-1], {})
            continue
        if "=" in roh:
            schluessel, wert = roh.split("=", 1)
            jetzt[schluessel.strip()] = wert
    return gruppen


def test_der_scan_liest_die_dateien_wirklich():
    """Eine Suche, die nichts findet, antwortet auf jede Frage
    dasselbe "sauber" wie ein Baum ohne Fehler."""
    dateien = _dateien()
    assert len(dateien) >= 3, (
        f"nur {len(dateien)} .desktop-Dateien gefunden: "
        f"{[p.name for p in dateien]}")
    namen = {p.name for p in dateien}
    for erwartet in ("zepos-settings.desktop", "zepos.desktop",
                     "zepos-claude-code.desktop"):
        assert erwartet in namen, f"{erwartet} wird nicht gelesen"
    # Und wirklich gelesen, nicht nur gefunden.
    gesamt = sum(len(_gruppen(p)) for p in dateien)
    assert gesamt >= 10, f"nur {gesamt} Gruppen gelesen"


def test_kein_deutscher_text_steht_in_der_ausgangssprache():
    """DIE ZUSICHERUNG, DIE DEN ZUSTAND VON GESTERN NICHT WIEDERKOMMEN
    LAESST.

    Ein Umlaut in einem UNBEZEICHNETEN sichtbaren Schluessel heisst:
    dieser Text erreicht jeden, dessen Sprache nicht ausdruecklich
    dasteht. Genau so sahen die drei Dateien bis zum 02.09.2026 aus.
    """
    schuldig = []
    for pfad in _dateien():
        for gruppe, felder in _gruppen(pfad).items():
            for schluessel, wert in felder.items():
                if schluessel not in SICHTBARE_SCHLUESSEL:
                    continue
                if UMLAUTE.search(wert):
                    schuldig.append(
                        f"{pfad.relative_to(WURZEL)} [{gruppe}] "
                        f"{schluessel}={wert}")
    assert schuldig == [], (
        "diese Werte stehen deutsch in der Ausgangssprache - gehoert in "
        "einen [de]-Schluessel, sonst liest sie jeder, dessen Sprache "
        "nicht dasteht:\n  " + "\n  ".join(schuldig))


def test_keine_uebersetzung_ohne_ihre_ausgangssprache():
    """Ein `Name[de]` ohne `Name` ist ein Text, auf den niemand
    zurueckfaellt.

    Die Spezifikation sagt es so: der unbezeichnete Schluessel ist der
    Wert, den ein Leser nimmt, wenn seine Sprache fehlt. Fehlt ER, hat
    ein englischer Starter fuer diesen Eintrag GAR keine Beschriftung -
    eine leere Zeile im Menue, und zwar nur fuer die eine Haelfte der
    Nutzer, die sie nicht sieht.
    """
    fehlend = []
    for pfad in _dateien():
        for gruppe, felder in _gruppen(pfad).items():
            for schluessel in felder:
                treffer = BEZEICHNET.match(schluessel)
                if not treffer:
                    continue
                grund = treffer.group(1)
                if grund not in SICHTBARE_SCHLUESSEL:
                    continue
                if grund not in felder:
                    fehlend.append(
                        f"{pfad.relative_to(WURZEL)} [{gruppe}]: "
                        f"{schluessel} ohne {grund}")
    assert fehlend == [], (
        "diese Uebersetzungen haben keine Ausgangssprache neben sich:\n  "
        + "\n  ".join(fehlend))


def test_die_drei_ausgelieferten_dateien_sind_wirklich_zweisprachig():
    """Und nicht bloss frei von Umlauten.

    Die zwei Zusicherungen darueber liessen sich auch erfuellen, indem
    jemand den deutschen Text LOESCHT statt ihn zu bezeichnen. Das waere
    kein Fortschritt, sondern ein Verlust: der deutsche Nutzer ist der,
    fuer den dieses System zuerst gebaut wurde.

    Geprueft wird deshalb, dass die Uebersetzung DA ist - je Datei an
    dem Schluessel, der ihren Text traegt. `Name` fehlt bei zweien
    absichtlich: "ZepOS" und "Claude Code" sind Eigennamen und lauten in
    jeder Sprache so.
    """
    erwartet = {
        "settings/zepos-settings.desktop": ("Name[de]", "Comment[de]",
                                            "Keywords[de]"),
        "src/login/zepos.desktop": ("Comment[de]",),
        "src/system/zepos-claude-code.desktop": ("GenericName[de]",
                                                 "Comment[de]",
                                                 "Keywords[de]"),
    }
    for relativ, schluessel in erwartet.items():
        felder = _gruppen(WURZEL / relativ)["Desktop Entry"]
        for name in schluessel:
            assert name in felder, (
                f"{relativ} hat kein {name} mehr - der deutsche Nutzer "
                "liest diesen Eintrag dann auf Englisch")
            assert felder[name].strip(), f"{relativ}: {name} ist leer"


def test_die_aktionen_der_einstellungen_sind_zweisprachig():
    """Jede Desktop Action, beide Schluessel.

    Acht Aktionen, und jede ist eine eigene Zeile im Starter. Fehlt bei
    einer die Uebersetzung, ist genau diese eine Zeile englisch,
    waehrend die sieben daneben deutsch sind - der Fall, der wie ein
    Versehen aussieht und keines ist.

    Dass die deutschen Namen mit den Reitern des Fensters
    uebereinstimmen, haelt tests/settings/test_settings_model.py; hier
    geht es nur um die Vollstaendigkeit.
    """
    gruppen = _gruppen(WURZEL / "settings/zepos-settings.desktop")
    aktionen = [name for name in gruppen
                if name.startswith("Desktop Action ")]
    assert len(aktionen) >= 8, f"nur {len(aktionen)} Aktionen gefunden"
    for gruppe in aktionen:
        felder = gruppen[gruppe]
        assert felder.get("Name", "").strip(), (
            f"[{gruppe}] hat keinen Namen in der Ausgangssprache")
        assert felder.get("Name[de]", "").strip(), (
            f"[{gruppe}] hat keinen deutschen Namen")
