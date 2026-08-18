# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Ratsche auf den Knoepfen.

GEMELDET am 18.08.2026: "ausserdem wirken sie so billig durch die button
wie sie dargestellt sind weisst du was ich meine".

GEMESSEN am selben Tag in src/templates/ags-style.template: zuerst 45
Knopfregeln in 41 verschiedenen Klassen - mit einem Zaehler, der nur
Zeilen ansah, deren allererstes Zeichen ein Punkt war.

BERICHTIGT, noch am selben Tag, in der Pruefung dieses Tests: der
Zaehler hatte drei blinde Flecken, und alle drei kommen im Stylesheet
tatsaechlich vor.

  1. Eingerueckte Selektoren (SCSS-Verschachtelung): ".calendar-action-btn",
     ".sc-edit-btn", ".vpn-list-btn" stehen mit fuehrenden Leerzeichen in
     einem umschliessenden Block und begannen darum nie am Zeilenanfang.
  2. Das zweite (und jedes weitere) Glied einer Komma-Liste: in
     ".bt-power-btn, .bt-tool-btn {" sah der alte Zaehler nur das erste
     Glied, ".bt-tool-btn" fiel durch. Ebenso ".net-refresh-btn" hinter
     ".net-wifi-toggle,".
  3. Die Endung "-button" statt "-btn": ".cc-button" ist ein
     vollstaendig ausgepraegter Knopf (Hintergrund, Rahmen, Polster,
     32px), aber der alte Zaehler suchte nur nach "btn" als Teilstring -
     "button" enthaelt "btn" nicht als zusammenhaengende Buchstabenfolge.
     Die Behauptung weiter unten, "-btn" sei die einzige durchgehaltene
     Benennung, war damit falsch; der Bestand widerlegt sie.

Mit dem reparierten Zaehler (siehe _knopfklassen) neu gemessen, ebenfalls
am 18.08.2026: 51 Knopfregeln in 47 verschiedenen Klassen. Die Namen, die
der alte Zaehler nicht sah: bt-tool-btn, calendar-action-btn, cc-button,
net-refresh-btn, sc-edit-btn, vpn-list-btn - genau die sechs, die aus den
drei blinden Flecken oben folgen. AUSGANGSZAHL war darum 47, nicht 41;
wer die Differenz spaeter als Verschlechterung liest, findet hier den
Grund.

WARUM EINE RATSCHE UND NICHT "GENAU EINE": UI-1 stellt zwoelf Fenster
um, und das geht nicht in einem Zug (siehe Abschnitt 6 der
Spezifikation). Ein Test, der sofort genau eine verlangt, waere von der
ersten bis zur letzten Stufe rot - und ein Test, der monatelang rot ist,
ist ein Test, den jemand abschaltet.

Die Ratsche laesst die Zahl nur SINKEN. Wer eine Klasse hinzufuegt,
faellt sofort auf; wer eine entfernt, muss die Zahl hier senken und
sieht dabei, wie weit es noch ist. Die letzte Stufe von UI-1 setzt sie
auf 1.

DIE EINE AUSNAHME, NOCH AM 18.08.2026 (Ruling 1 des Controllers): task-1u4
hat die gemeinsame Knopfregel selbst angelegt - .zep-btn und seine vier
Rollen .zep-btn-voll/-umrandet/-still/-kritisch, aus ags-kit.template.
Das sind fuenf neue Klassennamen, die alle "btn" im Namen tragen, und sie
mussten VOR jeder Umstellung eines Fensters existieren, damit ueberhaupt
etwas da ist, worauf ein Fenster umgestellt werden kann. Gezaehlt nach
demselben _knopfklassen wie oben ergab das 52 statt 47 - kein Fenster hat
sich einen eigenen Knopf gebaut, das Bauteil-Kit selbst ist neu.
AUSGANGSZAHL und ERLAUBT stehen darum ab hier auf 52, und das ist die
EINZIGE Richtung, in der diese Ratsche je nach oben geht: einmal, fuer
das Fundament, nicht fuer ein einzelnes Fenster.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STIL = ROOT / "src" / "templates" / "ags-style.template"

# Am 18.08.2026 mit dem reparierten Zaehler gemessen, bevor irgendetwas
# umgestellt war. Der urspruengliche Zaehler hatte an dieser Stelle
# faelschlich 41 stehen (siehe Modul-Docstring) - das war kein anderer
# Ausgangszustand, sondern derselbe Zustand, falsch gezaehlt.
#
# NOCH AM 18.08.2026, task-1u4: das Bauteil-Kit selbst (.zep-btn und
# seine vier Rollen) kam dazu, BEVOR ein Fenster umgestellt ist - siehe
# Modul-Docstring, Abschnitt "DIE EINE AUSNAHME". Gemessen mit
# _knopfklassen: 52. AUSGANGSZAHL zieht mit, weil sie sonst eine
# Obergrenze waere, die schon der erste erlaubte Schritt reisst - und
# test_the_ratchet_is_not_secretly_loose faende dann die Ausnahme, die
# der Controller ausdruecklich erlaubt hat, ununterscheidbar von einem
# Missbrauch.
AUSGANGSZAHL = 52

# Die Zahl, die HEUTE gilt. Sie darf nur kleiner werden - mit der einen
# Ausnahme oben, dem Bauteil-Kit selbst -, und wer sie senkt, schreibt
# dazu, welches Fenster er umgestellt hat.
#
#   41  18.08.2026  Ausgangszustand (Zaehler kaputt, siehe Docstring)
#   47  18.08.2026  Zaehler repariert, echter Ausgangswert
#   52  18.08.2026  task-1u4: .zep-btn + vier Rollen, das Bauteil-Kit
#                   selbst (Ruling 1 des Controllers - die eine erlaubte
#                   Ausnahme, siehe Modul-Docstring)
#   50  18.08.2026  task-5: Bluetooth auf die Bauteile. .bt-power-btn
#                   und .bt-tool-btn (eine gemeinsame Regel) sind
#                   gefallen, kein Fenster hat sich einen neuen Knopf
#                   gebaut - GEZAEHLT mit _knopfklassen/_ist_knopfname
#                   aus diesem Modul, nicht abgeschrieben.
#   45  18.08.2026  Task A (die sechs Fenster mit je einer Klasse):
#                   battery-profile-btn, calendar-action-btn,
#                   disk-action-btn, notif-close-btn und sc-edit-btn sind
#                   gefallen - fuenf von sechs benannten Klassen.
#                   overlay-close-btn bleibt stehen: er sitzt in
#                   createOverlayWindow() (ags-overlay-utils.template)
#                   und ist damit das x in JEDER Kopfzeile JEDES
#                   Fensters. GEMESSEN an den Sprossen in src/sizes.py:
#                   zep-btn setzt min-height auf STYLE_CONTROL_HEIGHT
#                   (32px) und padding auf "0 STYLE_SPACE_16" (0/16px);
#                   overlay-close-btn hat min-width/min-height fest auf
#                   28px und padding "STYLE_SPACE_4 STYLE_SPACE_8"
#                   (4/8px) stehen. zepButton mit Rolle "still" wuerde
#                   das Kreuz also hoeher (32 statt 28) UND breiter
#                   (16 statt 8px Innenabstand je Seite) machen, in allen
#                   zwoelf Fensterkoepfen zugleich - genau der Fall, den
#                   der Plan mit "lass ihn stehen und melde es"
#                   vorwegnimmt. GEZAEHLT mit _knopfklassen/
#                   _ist_knopfname aus diesem Modul, nicht abgeschrieben.
#   38  18.08.2026  Task B (Hintergruende und Stil-Editor): wp-action-btn,
#                   wp-import-btn, wp-monitor-btn (ags-wallpaper.template)
#                   sowie se-edit-btn, se-action-btn, cp-cancel-btn,
#                   cp-apply-btn (ags-style-editor.template) sind gefallen
#                   - sieben von neun benannten Klassen.
#                   se-tab-btn bleibt stehen: ein Reiter, kein Knopf. Die
#                   waagerechte Innenabstand von .se-tab-btn und .zep-btn
#                   ist GLEICH ({{STYLE_SPACE_16}} je Seite), eine
#                   Umstellung haette die gemessene Breite des breitesten
#                   Reiters (122px, Kommentar am Kopf von
#                   ags-style-editor.template) also NICHT veraendert -
#                   aber genau diese Breite ist die EINZIGE Grundlage der
#                   Fensterbreite (WIN_WIDTH = 474) dieses Fensters, staerker
#                   daran gekoppelt als jede andere Klasse in diesem
#                   Auftrag. Ein Fehler hier waere ein Fehler in der
#                   Fensterbreite, und die Breitenleiter ist Stufe 5, nicht
#                   dieser Auftrag - siehe Gruppenbericht.
#                   cp-preset-btn bleibt ebenfalls stehen: eine Farbkachel,
#                   kein Knopf mit Text. GEMESSEN: .cp-preset-btn hat
#                   padding {{STYLE_SPACE_2}} (2px) und min-width/
#                   min-height 0; .zep-btn erzwingt padding
#                   "0 {{STYLE_SPACE_16}}" (16px je Seite) und min-height
#                   {{STYLE_CONTROL_HEIGHT}} (32px). Acht Kacheln je Zeile
#                   in einem 474px breiten Fenster wuerden die verfuegbare
#                   Breite sprengen. GEZAEHLT mit _knopfklassen/
#                   _ist_knopfname aus diesem Modul, nicht abgeschrieben.
#   32  18.08.2026  Task C (Netzwerk): net-back-btn, net-connect-btn,
#                   net-detail-btn, net-disconnect-btn, net-nm-btn,
#                   net-refresh-btn (aus der gemeinsamen Regel mit
#                   net-wifi-toggle) sind gefallen - alle sechs benannten
#                   Klassen. net-wifi-toggle bleibt stehen: kein "btn"/
#                   "-button" im Namen, zaehlt also gar nicht zur
#                   Ratsche - kein Fall von "lass ihn stehen", sondern
#                   ausserhalb ihrer Zaehlung von Anfang an.
#                   GEZAEHLT mit _knopfklassen/_ist_knopfname aus diesem
#                   Modul (VORHER 38, NACHHER 32, `git show HEAD` gegen
#                   den Arbeitsbaum), nicht abgeschrieben.
#   23  18.08.2026  Task D (Kontrollzentrum): cc-button, cc-icon-btn,
#                   cc-power-btn (drei der zehn benannten Klassen, in
#                   ags-control-center.template tatsaechlich benutzt)
#                   sowie cc-expand-btn, cc-mini-btn, cc-pwr-btn,
#                   cc-service-btn, cc-svc-btn, cc-toggle-btn (sechs
#                   weitere der zehn genannten Klassen, aber OHNE Leser
#                   in irgendeiner Vorlage - Ueberbleibsel eines
#                   aelteren Kontrollzentrum-Entwurfs, nie von
#                   ags-control-center.template in seiner heutigen Form
#                   benutzt) sind gefallen - neun der zehn benannten
#                   Klassen. cc-action-btn (die zehnte) bleibt stehen:
#                   sie gehoert nicht zu ags-control-center.template
#                   (Plan-vs-Baum-Abweichung, siehe gruppe-D-report.md),
#                   sondern zu ags-notifications.template
#                   (clearButton, "Clear all") und wird dort weiterhin
#                   gebraucht. cc-power-btn/cc-pwr-btn (Dubletten-
#                   Verdacht laut Auftrag) waren beide keine Dubletten
#                   im eigentlichen Sinn: cc-power-btn war die einzige
#                   der beiden mit einem Leser, cc-pwr-btn war schon
#                   VOR diesem Auftrag tot. Ebenso cc-service-btn neben
#                   cc-svc-btn: BEIDE waren bereits tot, keine
#                   Dublette mit einer lebenden Seite.
#                   GEZAEHLT mit _knopfklassen/_ist_knopfname aus diesem
#                   Modul (VORHER 32, NACHHER 23, `git show HEAD` gegen
#                   den Arbeitsbaum), nicht abgeschrieben.
#    9  18.08.2026  Task E (VPN und VPN-Einstellungen), der letzte Auftrag
#                   von UI-1 Stufe 4. Dreizehn der vierzehn genannten
#                   Klassen auf zepButton umgestellt und entfernt:
#                   vpn-add-btn, vpn-back-btn, vpn-cancel-btn,
#                   vpn-connect-btn (Rolle voll), vpn-delete-btn (Rolle
#                   kritisch, wie verlangt), vpn-disconnect-btn (Rolle
#                   kritisch - Trennen ist zerstoerend, dieselbe
#                   Einordnung wie net-disconnect-btn, Task C),
#                   vpn-reset-btn (Rolle kritisch, wie verlangt),
#                   vpn-save-btn (Rolle voll), vpn-save-psk-btn,
#                   vpn-settings-btn, vpn-tab-btn (Rolle umrandet - ANDERS
#                   als se-tab-btn, Task B, blieb dieser Reiter nicht
#                   stehen: die waagerechte Innenabstand ist woertlich
#                   derselbe Platzhalter STYLE_SPACE_16 in beiden Regeln,
#                   und WIN_WIDTH von ags-vpn-settings.template haengt an
#                   den vier Fussknoepfen, nicht an der Reiterleiste - die
#                   Kopplung, die se-tab-btn stehen liess, griff hier
#                   nicht), vpn-toggle-btn und vpn-visibility-btn (Rolle
#                   still - GEPRUEFT wie beim x in Task A: .vpn-entry-row
#                   haengt an der Hoehe von .vpn-entry, ~60px aufgeloest
#                   mit dem ausgelieferten Faktor 1.85, groesser als
#                   zep-btns min-height von 49px - die Zeile bleibt vom
#                   Eingabefeld bestimmt, nicht vom Knopf, anders als bei
#                   overlay-close-btn keine harte Massvorgabe, die
#                   zep-btn unterlaeuft). Die vierzehnte genannte Klasse,
#                   vpn-list-btn, war repo-weit OHNE Leser (GEPRUEFT vor
#                   jeder Aenderung, `grep -rn` gegen alle Vorlagen) -
#                   Ueberbleibsel eines aelteren Listeneintrags-Entwurfs,
#                   einfach entfernt statt umgebaut (dieselbe Lage wie
#                   sechs der zehn Klassen in Task D).
#                   GEFUNDEN, WO DER WAECHTER UNERWARTET ANSCHLUG: die
#                   Ratsche zaehlte vpn-tab-btn nach dem Umbau weiter,
#                   weil ein ZWEITER Fundort auf ihn zeigte - die globale
#                   Uebergangsregel-Liste ("DIE BEWEGUNG") trug
#                   `.vpn-tab-btn.active` neben `.se-tab-btn.active`.
#                   REPARIERT im Code, nicht im Test: die verwaiste Zeile
#                   entfernt, dieselbe Reparatur, die Task D fuer
#                   cc-toggle-btn.active bereits an derselben Stelle
#                   gemacht hat. Die "aktiv"-Faerbung selbst lebt jetzt in
#                   `.vpn-tab-bar .zep-btn.active` (dieselbe Sprache wie
#                   `.battery-profile-buttons .zep-btn.active`, Task A,
#                   und `.wp-monitor-selector .zep-btn.active`, Task B)
#                   sowie `.vpn-toggle-group .zep-btn.active` fuer
#                   vpn-toggle-btn, mit denselben Farbwerten wie vorher.
#                   PLAN-VS-BAUM-ABWEICHUNG: der Auftrag verspricht "die
#                   Ratsche steht danach auf 5", weil er annimmt, alle
#                   anderen Fenster liessen keine eigene Klasse mehr
#                   stehen. Der Baum zeigt vier Klassen aus fruehen,
#                   bereits committeten Auftraegen, die bewusst NICHT zu
#                   den fuenf zep-Namen gehoeren und ausserhalb der
#                   Dateiliste dieses Auftrags liegen: overlay-close-btn
#                   (Task A - das x in jeder Fensterkopfzeile, haerte
#                   Massvorgabe als zep-btn), se-tab-btn und cp-preset-btn
#                   (Task B - Reiter bzw. Farbkachel, siehe deren
#                   Eintraege oben) und cc-action-btn (Task D - gehoert zu
#                   ags-notifications.template, nicht zu diesem Auftrag).
#                   ERLAUBT steht darum auf 9, nicht auf 5 - siehe
#                   gruppe-E-report.md.
#                   GEZAEHLT mit _knopfklassen/_ist_knopfname aus diesem
#                   Modul (VORHER 23, NACHHER 9, `git show HEAD` gegen den
#                   Arbeitsbaum), nicht abgeschrieben.
ERLAUBT = 9


def _without_comments(css: str) -> str:
    """CSS ohne Kommentare.

    Wortgleich zu tests/src/test_spacing.py und aus demselben Grund: jede
    Datei in diesem Baum ERKLAERT, was sie nicht mehr tut, und eine Suche
    nach einem Klassennamen wird von der Erklaerung wahr, in der steht,
    dass die Regel verschwunden ist.

    NACHGETRAGEN am 18.08.2026, task-6: GEMELDET war ein Zaehler, der
    Klassennamen auch in einem Loeschprotokoll findet - ein frueherer
    Umsetzer hatte sein Vorgehen als `// entfernt: .bt-power-btn`
    festgehalten, und der ungefilterte Zaehler zaehlte diesen Kommentar
    mit, obwohl die Regel selbst laengst weg war. Elf weitere Fenster
    stehen noch bevor, und jedes davon wird so ein Protokoll schreiben.
    NACHGEMESSEN mit `_knopfklassen` VOR und NACH diesem Filter auf dem
    heutigen Bestand von ags-style.template: 50 Klassen in beiden
    Faellen (siehe test_no_window_invents_another_button) - der Filter
    entfernt hier keinen echten Treffer, weil der Bestand heute keinen
    Kommentar dieser Art enthaelt. Er verhindert nur, dass einer der
    naechsten elf Auftraege die Ratsche scheinbar haelt, obwohl eine
    Regel gefallen ist.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return "\n".join(line for line in css.splitlines()
                     if not line.lstrip().startswith("//"))


# WAS DIESER ZAEHLER NICHT SIEHT
#     Er liest die Knopf-Klassen aus dem STYLESHEET. Eine Klasse, die
#     eine Vorlage an ein Widget haengt, zu der es aber gar keine Regel
#     gibt, kommt hier nie vor - sie ist unsichtbar und zugleich
#     schlimmer als eine doppelte Regel, weil der Knopf dann in blankem
#     GTK-Standard steht.
#
#     GEMESSEN am 18.08.2026: genau so lag wp-confirm-btn in
#     ags-wallpaper.template, durch fuenf Umbauten hindurch. Gefunden hat
#     es nicht dieser Zaehler, sondern der Auftrag, der totes CSS suchte
#     und auf die Gegenrichtung stiess.
#
#     Den Fall deckt seit dem 18.08.2026 tests/src/test_schale.py ab:
#     test_kein_ags_fenster_baut_sich_ein_gtk_window.
def _knopfklassen(text: str) -> set[str]:
    """Jede Klasse, deren Name auf einen Knopf hindeutet.

    Ueber den NAMEN und nicht ueber den Inhalt: eine Regel, die zufaellig
    wie ein Knopf aussieht, ist keine; eine, die "btn" enthaelt oder auf
    "-button" endet, ist eine. Beide Formen sind im Bestand belegt - die
    fruehere Behauptung, "-btn" sei die einzige durchgehaltene Benennung,
    stimmte nicht (siehe Modul-Docstring, Punkt 3).

    "-buttons" (Mehrzahl) zaehlt bewusst NICHT: das sind Container ohne
    eigenen Knopf-Stil, reines Layout fuer eine Gruppe von Knoepfen
    (z. B. ".battery-profile-buttons").

    Ein Klassenname zaehlt unabhaengig davon, WIE er im Stylesheet
    auftaucht: am Zeilenanfang, eingerueckt in einem verschachtelten
    Block, oder als zweites/weiteres Glied einer durch Komma getrennten
    Selektorliste. Nur ein direkt vorangehender Buchstabe, eine Ziffer
    oder ein Bindestrich schliesst eine Fundstelle aus - das ist genau
    der Fall bei einem angehaengten Compound-Selektor wie
    ".cc-toggle-btn.active", wo ".active" kein eigener Treffer sein darf.

    Kommentare zaehlen NICHT mit (siehe _without_comments) - ein Name,
    der nur in einem Loeschprotokoll wie `// entfernt: .foo-btn` steht,
    ist kein Treffer.
    """
    return set(re.findall(r"(?<![a-z0-9-])\.([a-z][a-z0-9-]*)",
                          _without_comments(text), re.M))


def _ist_knopfname(name: str) -> bool:
    """Enthaelt "btn" oder endet auf "-button" (Einzahl, nicht "-buttons")."""
    return "btn" in name or name.endswith("-button")


def test_no_window_invents_another_button():
    kandidaten = _knopfklassen(STIL.read_text(encoding="utf-8"))
    gefunden = {name for name in kandidaten if _ist_knopfname(name)}
    assert len(gefunden) <= ERLAUBT, (
        f"{len(gefunden)} Knopf-Klassen, erlaubt sind {ERLAUBT}.\n"
        f"Neu dazugekommen: {sorted(gefunden)[:60]}\n"
        "Ein Fenster hat sich wieder seinen eigenen Knopf gebaut. Nimm "
        "zepButton aus ags-kit.template.")


def test_the_ratchet_is_not_secretly_loose():
    """Die Zahl darf nicht ueber dem Ausgangswert stehen.

    Ohne diese Zusicherung koennte jemand ERLAUBT anheben, statt einen
    Knopf zu entfernen - und der Waechter waere still eine Erlaubnis.
    """
    assert ERLAUBT <= AUSGANGSZAHL, (
        f"ERLAUBT steht auf {ERLAUBT}, der Ausgangswert war "
        f"{AUSGANGSZAHL}. Die Ratsche dreht nur in eine Richtung.")


def test_the_counter_would_notice_a_new_class():
    """Der Selbsttest. Ein Zaehler, der nichts findet, zaehlt auch nichts.

    Deckt genau die drei Formen ab, an denen der Zaehler bis zum
    18.08.2026 vorbeigesehen hat (siehe Modul-Docstring): Einrueckung,
    das zweite Glied einer Komma-Liste, und die Endung "-button". Dazu
    den Gegenfall "-buttons" (Mehrzahl), der NICHT zaehlen darf.

    NACHGETRAGEN am 18.08.2026, task-6: den vierten blinden Fleck, den
    _without_comments schliesst - ein Klassenname, der NUR in einem
    Kommentar steht (`// entfernt: .commented-btn`), darf ebenfalls
    NICHT zaehlen. Das ist das Loeschprotokoll aus der Meldung, nur mit
    einem Namen, der sonst nirgends im Beispiel vorkommt.
    """
    beispiel = (
        ".a-btn {\n"                # unveraendert: eigene, unverschachtelte Zeile
        "  color: red;\n"
        "}\n"
        ".b {\n"                    # Gegenprobe: kein Knopfname
        "  color: blue;\n"
        "}\n"
        ".wrapper {\n"
        "  .indent-btn {\n"         # 1. Einrueckung
        "    color: green;\n"
        "  }\n"
        "}\n"
        ".first-btn, .second-btn {\n"  # 2. zweites Glied einer Komma-Liste
        "  color: yellow;\n"
        "}\n"
        ".solo-button {\n"          # 3. Endung "-button" statt "-btn"
        "  color: purple;\n"
        "}\n"
        ".group-buttons {\n"        # Gegenfall: Mehrzahl darf NICHT zaehlen
        "  color: grey;\n"
        "}\n"
        "// entfernt: .commented-btn\n"  # 4. nur im Kommentar - kein Treffer
    )
    kandidaten = _knopfklassen(beispiel)
    gefunden = {name for name in kandidaten if _ist_knopfname(name)}
    assert gefunden == {
        "a-btn", "indent-btn", "first-btn", "second-btn", "solo-button",
    }
    assert "commented-btn" not in gefunden


def test_the_shared_button_exists_and_has_four_roles():
    text = STIL.read_text(encoding="utf-8")
    assert re.search(r"^\.zep-btn\s*\{", text, re.M), (
        "die gemeinsame Knopfregel fehlt")
    for rolle in ("voll", "umrandet", "still", "kritisch"):
        assert re.search(rf"^\.zep-btn-{rolle}\s*\{{", text, re.M), (
            f"die Rolle {rolle} fehlt")


def test_the_shared_button_uses_the_rungs():
    """Hoehe und Radius als Platzhalter, nicht als Zahl."""
    block = re.search(r"^\.zep-btn\s*\{(.*?)^\}", 
                      STIL.read_text(encoding="utf-8"), re.M | re.S)
    assert block, "die Regel .zep-btn ist verschwunden"
    rumpf = block.group(1)
    assert "{{STYLE_CONTROL_HEIGHT}}" in rumpf, "die Hoehe ist keine Sprosse"
    assert "{{STYLE_RADIUS_CONTROL}}" in rumpf, "der Radius ist keine Sprosse"
