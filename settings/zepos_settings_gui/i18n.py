# SPDX-License-Identifier: GPL-3.0-or-later
"""Der Katalog dieses Fensters. Kein `gi` in dieser Datei.

DIESELBE DOMAENE WIE DIE SCHALE, UND DAS IST EINE ENTSCHEIDUNG
    "zepos-desktop" - wortgleich zu src/region.py:150,
    src/templates/ags-i18n.template und po/build.sh. Dieses Fenster ist
    keine eigene Anwendung neben dem Schreibtisch, es IST eine seiner
    Oberflaechen, und es sagt dieselben Woerter: "Not connected" steht
    in der Leiste, im Kontrollzentrum und hier.

    Eine eigene Domaene haette drei Kosten und keinen Gewinn. Sie
    braeuchte einen eigenen Bauschritt (po/build.sh baut zepos-desktop
    schon, packaging/zepos-config ruft es schon), eine eigene
    Auslieferung, und sie haette denselben Satz zweimal im Baum - mit
    der Gewissheit, dass die zweite Fassung beim ersten Umformulieren
    abweicht. Genau die Begruendung, aus der die Beschriftungen in
    model.py stehen und nicht in app.py.

    Der Installer hat aus einem anderen Grund seine eigene
    (zepos-installer): eine installierte Maschine hat keinen Installer,
    und sein Katalog waere dort ein Katalog, dessen Name luegt. Dieses
    Fenster liegt auf JEDER Installation.

WARUM DIE SPRACHE AUS /etc/locale.conf KOMMT UND NICHT AUS DER UMGEBUNG
    Weil dieses Fenster die Sprache SELBST UMSTELLT. Nach
    `localectl set-locale` ist die Umgebung des laufenden Prozesses eine
    ABSCHRIFT von vorher - sie wurde bei der Anmeldung angefertigt - und
    die Datei ist die frische Angabe. Ein Fenster, das sich nach dem
    Umstellen aus seiner Umgebung neu uebersetzt, uebersetzt sich in die
    alte Sprache zurueck.

    Gelesen wird darum region.current_language(), also
    /etc/locale.conf ueber ZEPOS_ETC_ROOT - dieselbe Vorrichtung, mit
    der die Schale es seit dem 02.09.2026 tut, und derselbe Weg, auf
    dem ein Test die Sprache vorgeben kann, ohne die Umgebung des
    Laufs anzufassen.

WARUM `_()` BEIM AUFRUF NACHSCHAUT UND NICHT BEIM IMPORT
    GEMESSEN am 02.09.2026 mit einem gebauten Katalog:

        LABEL = _("Desktop size")   beim Import ausgewertet
        Katalog umschalten
        LABEL                       -> "Desktop size"     folgt NICHT
        _("Desktop size")           -> die Uebersetzung    folgt

    Die erste Haelfte loest dieses Modul (die Nachschau steht im
    Aufruf, nicht im Import - dieselbe Bauart wie
    installer/core/i18n.py). Die zweite Haelfte kann es nicht loesen:
    eine Konstante, die beim Import einen Satz gebacken hat, folgt
    keinem Katalogwechsel mehr. Dafuer gibt es N_() unten.

WAS activate() NICHT KANN, UND ES IST GEMESSEN
    Einen Katalog neu lesen, der sich AM SELBEN PFAD geaendert hat.
    `gettext.translation()` haelt einen Zwischenspeicher an (Klasse,
    absoluter Pfad der .mo) und prueft die Aenderungszeit nicht -
    GEMESSEN am 02.09.2026:

        .mo schreiben (ganz)  -> translation() -> die Uebersetzung
        dieselbe .mo kuerzen  -> translation() -> DIESELBE Antwort

    Fuer dieses Fenster ist das harmlos und darf trotzdem nicht
    unaufgeschrieben bleiben. Harmlos, weil ein Sprachwechsel eine
    ANDERE Datei liest (de/LC_MESSAGES statt en/LC_MESSAGES) und der
    Zwischenspeicher darum nie im Weg steht. Aufgeschrieben, weil der
    Naechste, der hier ein "Katalog neu laden" einbaut, sonst eine
    Stunde mit einer Datei verbringt, die richtig auf der Platte liegt
    und falsch im Prozess.
"""
from __future__ import annotations

import gettext
import struct
from pathlib import Path

import region

DOMAIN = region.DOMAIN

_translation: gettext.NullTranslations = gettext.NullTranslations()
_language = region.SOURCE_LANGUAGE


def activate(language: str | None = None, *,
             localedir: Path | None = None,
             translation: gettext.NullTranslations | None = None) -> str:
    """Den Katalog waehlen. Wirft nie.

    Ohne Angabe: die Sprache, die /etc/locale.conf gerade nennt.

    EIN FEHLENDER KATALOG FAELLT AUF ENGLISCH ZURUECK UND NICHT AUS.
    Die msgids sind englisch (siehe den Kopf von src/region.py), also
    ist der Rueckfall eine vollstaendige Oberflaeche und keine leere.
    Ein Einstellungsfenster, das an einer halb geschriebenen .mo-Datei
    nicht mehr startet, waere genau an der Stelle unbrauchbar, an der
    man es zum Reparieren braucht.

    Gibt den Code zurueck, der wirklich gilt - der Aufrufer soll nicht
    raten muessen, ob seine Bitte angekommen ist.
    """
    global _translation, _language

    if translation is not None:
        _translation = translation
        _language = language or region.SOURCE_LANGUAGE
        return _language

    code = language or region.current_language()
    _language = code

    # Die Quellsprache hat keinen Katalog - sie IST der Katalog.
    if code == region.SOURCE_LANGUAGE:
        _translation = gettext.NullTranslations()
        return code

    orte = [localedir] if localedir else region.catalogue_directories()
    for ort in orte:
        try:
            _translation = gettext.translation(
                DOMAIN, localedir=str(ort), languages=[code])
            return code
        except (OSError, AttributeError, struct.error, ValueError):
            # struct.error: eine abgeschnittene .mo, etwa aus einem
            # unterbrochenen Schreiben. Sie ist KEIN OSError und muss
            # darum eigens genannt werden - dieselbe Zeile und derselbe
            # Grund wie in installer/core/i18n.py.
            continue

    _translation = gettext.NullTranslations()
    return code


def current_language() -> str:
    """Welche Sprache dieser Prozess gerade spricht."""
    return _language


def _(message: str) -> str:
    """Der Anzeigetext, in der Sprache, die JETZT gilt.

    Beim Aufruf nachgeschlagen, damit activate() auch fuer Texte
    wirkt, deren Modul schon importiert war - und damit ein
    Sprachwechsel im laufenden Fenster ankommt, sobald die Seite neu
    gebaut wird.
    """
    return _translation.gettext(message)


def N_(message: str) -> str:
    """Die MARKE fuer die Auslese. Uebersetzt wird an der Senke.

    `xgettext --keyword=N_` liest den Text hier heraus, auch mitten in
    einer Tabelle; zurueck kommt er unveraendert. Gebraucht wird das
    ueberall, wo ein Anzeigetext NICHT an der Stelle entsteht, an der er
    gebraucht wird:

        LABEL_SCALE = N_("Desktop size")     # Definition, nur markiert
        title=_(model.LABEL_SCALE)           # Senke, hier uebersetzt

    Ohne diese Teilung muessten die 93 Beschriftungen in model.py von
    Tabellen zu Funktionen werden - und DIALS, PAGES, BAR_SIDES und
    UPDATE_LABELS sind genau in ihrer Form als Tabelle das, wogegen
    tests/settings/test_settings_model.py sizes.TABLE und die
    .desktop-Datei haelt. Eine Tabelle in vierzig Funktionen aufzuloesen
    haette zwoelf ganze Erwartungen in zwoelf Aufrufe verwandelt.

    Sie tut absichtlich nichts. Was sie leistet, leistet sie fuer
    xgettext und fuer den Leser.
    """
    return message


def ngettext(singular: str, plural: str, n: int) -> str:
    """Dasselbe fuer einen Text, dessen Form von einer Anzahl abhaengt.

    Keine Bequemlichkeit ueber `_()`: wie viele Pluralformen eine
    Sprache hat und welche Anzahl welche nimmt, entscheidet die Sprache
    selbst, und diese Regel steht im Plural-Forms-Kopf des Katalogs.
    "1 Einträge stehen nicht da" ist der Fehler, den es verhindert, und
    er ist einem Leser sofort anzusehen.
    """
    return _translation.ngettext(singular, plural, n)
