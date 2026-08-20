# SPDX-License-Identifier: GPL-3.0-or-later
"""Eine Regel fuer jede Flaeche, die sich vor die Arbeit stellt.

WAS GEMELDET WURDE
    Der Nutzer am 12.08.2026: "alle styles von ZEPOS muessen einheitlich
    aussehen". Den Grund hat er selbst genannt - die Modale gingen ueber
    den Schirmrand hinaus.

WARUM DIESE DATEI NEBEN test_overlay_windows.py STEHT UND NICHT DARIN
    Dort geht es um die Fabrik SELBST: ob sie deckelt, ob sie eine
    Bildlaufleiste haengt, ob der Kalender am Montag beginnt. Hier geht
    es um die Frage davor, und sie ist die einzige, die verhindert, dass
    dasselbe in vier Wochen wieder dasteht:

        Gibt es noch einen ZWEITEN Weg, so ein Fenster zu bauen?

    GEMESSEN am 12.08.2026, im verschachtelten Compositor von
    tests/render/, Schirm 1920x1080, Leiste 107 Punkte:

        netzwerk        462 x 721      selbst gebaut
        speicherplatz   532 x 540      aus der Fabrik
        kalender        472 x 540      aus der Fabrik

    540 ist MEASURE_MODAL_SHARE mal 1080. Die beiden aus der Fabrik
    hielten den Deckel auf den Punkt; das eine daneben stand 181 Punkte
    darueber - nicht, weil seine Zahlen falsch waren, sondern weil es an
    der Stelle vorbeiging, an der die Zahlen angewendet werden.

    Von elf Flaechen ging EINE vorbei. Eine Zusicherung, die nur das eine
    Fenster repariert haette, waere in vier Wochen wieder faellig; genau
    so ist dieses entstanden.

WAS HIER GEPRUEFT WIRD UND WAS NICHT
    Was in den Quellen STEHT. Was daraus auf dem Schirm wird, misst
    tests/render/ an einem echten Compositor - dieselbe Trennung wie
    zwischen test_placement.py und test_geometry.py.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src import sizes
from tests.adopted_plugin_source import plugin_source

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TEMPLATES = SRC / "templates"
FACTORY = TEMPLATES / "ags-overlay-utils.template"


# --------------------------------------------------------------------
# Handwerkszeug
# --------------------------------------------------------------------

def _code(path: Path) -> str:
    """Die Datei ohne ihre Zeilenkommentare.

    Jede Datei in diesem Baum ERKLAERT, was sie nicht mehr tut. Eine
    Suche nach "new Astal.Window" wuerde von der Erklaerung wahr, in der
    steht, dass es dort kein `new Astal.Window` mehr gibt.
    """
    marker = "#" if path.suffix == ".py" else "//"
    return "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith(marker))


def _object_literals(code: str, after: str) -> list[str]:
    """Jedes `{...}`, das auf `after` folgt, ueber Klammerzaehlung.

    Nicht ueber einen regulaeren Ausdruck: die Eigenschaften eines
    Astal.Window enthalten selbst geschweifte Klammern, und ein
    nicht-gieriges `\\{.*?\\}` schnitte beim ersten inneren `}` ab -
    also mitten in dem Aufbau, ueber den hier entschieden wird.
    """
    found: list[str] = []
    start = 0
    while True:
        hit = code.find(after, start)
        if hit < 0:
            return found
        brace = code.find("{", hit)
        if brace < 0:
            return found
        depth = 0
        for index in range(brace, len(code)):
            if code[index] == "{":
                depth += 1
            elif code[index] == "}":
                depth -= 1
                if depth == 0:
                    found.append(code[brace:index + 1])
                    start = index
                    break
        else:
            return found


def _ags_templates() -> list[Path]:
    return sorted(TEMPLATES.glob("ags-*.template"))


# --------------------------------------------------------------------
# 1. Die AGS-Oberflaeche: ein Weg, ein Fenster zu bauen
# --------------------------------------------------------------------

# Woran eine selbst gebaute Flaeche beweist, dass sie KEIN Modal ist.
#
# ES IST EIN BEWEIS UND KEINE AUSNAHMELISTE, UND DAS IST DER GANZE PUNKT
#     Eine Liste von Dateinamen waere genau das, was hier schiefgegangen
#     ist: jemand traegt seine Datei ein, und die Regel gilt fuer alle
#     ausser ihm. Diese beiden Merkmale stehen dagegen IM Fenster, und
#     sie sagen etwas darueber, was es ist:
#
#       exclusivity: EXCLUSIVE   die Flaeche RESERVIERT sich einen
#                                Streifen am Schirmrand. Der Compositor
#                                verkleinert dafuer den Arbeitsbereich
#                                aller anderen Fenster - sie stellt sich
#                                also nicht VOR die Arbeit, sie macht
#                                ihr Platz. Leiste und Dock.
#
#       keymode: NONE            die Flaeche nimmt die Tastatur NIE. Sie
#                                ist nichts, was man bedient, sondern
#                                etwas, das erscheint und wieder geht -
#                                eine Einblendung. Die
#                                Benachrichtigungen.
#
#     Wer ein Fenster baut, das die Tastatur nimmt und keinen Platz
#     reserviert, hat ein Modal gebaut, und Modale kommen aus der
#     Fabrik. Ein neues Widget faellt damit BEIM NAMEN auf, ohne dass
#     jemand diese Datei anfassen muss.
NOT_A_MODAL = (
    "exclusivity: Astal.Exclusivity.EXCLUSIVE",
    "keymode: Astal.Keymode.NONE",
)


def test_only_the_factory_builds_an_overlay_window():
    """Der eigentliche Befund, als Regel ueber ALLE Vorlagen.

    Bis zum 12.08.2026 baute ags-network.template sein Astal.Window
    selbst und holte aus utils/overlay.ts nur die Raender. Es war die
    einzige der elf Flaechen, die das tat, und die einzige ohne Deckel
    und ohne Bildlaufleiste.
    """
    guilty: list[str] = []
    for template in _ags_templates():
        if template == FACTORY:
            continue
        code = _code(template)
        for literal in _object_literals(code, "new Astal.Window("):
            if not any(proof in literal for proof in NOT_A_MODAL):
                guilty.append(template.name)
                break

    assert guilty == [], (
        "diese Vorlagen bauen sich ihr Ueberlagerungsfenster selbst, "
        "statt createOverlayWindow() aus ags-overlay-utils.template zu "
        "rufen: " + ", ".join(guilty) + ". Damit bekommen sie weder den "
        "Deckel aus MEASURE_MODAL_SHARE noch die Bildlaufleiste noch die "
        "Aufloesung des Monitors ueber den Anschlussnamen. Wenn die "
        "Flaeche ein Streifen ist, reserviert sie eine exklusive Zone; "
        "wenn sie eine Einblendung ist, nimmt sie die Tastatur nie - "
        "beides steht dann IM Fenster und wird hier als Beweis "
        "angenommen.")


def test_every_self_built_surface_says_what_it_is():
    """Die Gegenprobe: die, die sich selbst bauen duerfen, tun es aus
    einem Grund, der in ihrem Fenster steht.

    Ohne diese Zusicherung koennte der Beweis oben leerlaufen - eine
    Regel, die auf nichts mehr zutrifft, ist gruen und wertlos. Gemessen
    am 12.08.2026 waren es genau drei: die Leiste und das Dock
    reservieren einen Streifen, die Benachrichtigungen nehmen die
    Tastatur nie.

    VIER STATT DREI, SEIT DEM 19.08.2026 (Aufgabe 26): der Abschaltknopf
    am Dock (ags-power-button.template) baut ebenfalls sein eigenes
    Astal.Window je Schirm, aus demselben Grund wie Dock/Bar/Notifications
    zusammen - eine eigene, feste Layer-Shell-Flaeche, kein Aufklapp-
    fenster, das die Fabrik liefern koennte (createOverlayWindow() baut
    ein positioniertes Modal mit Kopf und Bildlaufleiste, keine
    dauerhafte Ecke am Bildschirmrand). Er reserviert KEINEN Streifen
    (er soll dem Dock keinen Platz wegnehmen) und nimmt NIE die Tastatur
    (ein Klick, kein Formular) - dieselbe zweite Begruendung wie bei den
    Benachrichtigungen, nicht die erste wie bei Leiste und Dock.

    FUENF STATT VIER, SEIT DEM 20.08.2026 (Aufgabe 44): der Starterknopf
    am Dock (ags-starter-button.template), das Gegenstueck zum
    Abschaltknopf in der anderen unteren Ecke. Wort fuer Wort dieselbe
    Begruendung wie dort - eine feste Ecke am Bildschirmrand, kein
    Aufklappfenster; IGNORE, damit er dem Dock keinen Platz wegnimmt;
    keymode NONE, weil man ihn klickt und nicht ausfuellt.

    SECHS STATT FUENF, SEIT DEM 20.08.2026 (Aufgabe 52): das Home
    (ags-home.template), die Flaeche hinter allen Fenstern. Es ist der
    Gegenpol zu allem anderen in dieser Liste - kein Streifen, keine
    Ecke, sondern die ganze freie Flaeche - und kann aus demselben Grund
    nicht aus der Fabrik kommen: createOverlayWindow() baut ein Modal mit
    Kopf, Deckel und Bildlaufleiste, das AUF VERLANGEN aufgeht. Das Home
    geht nie auf und nie zu; es ist immer da.

    Seine Begruendung ist die ZWEITE, wie bei den Benachrichtigungen und
    den zwei Knoepfen: `keymode: Astal.Keymode.NONE`. Und die ist hier
    keine Formalie, sondern gemessen - mit EXCLUSIVE bekam ein
    gewoehnliches Fenster im Versuch GAR KEINE Zeigerereignisse mehr
    (zweimal gelaufen, siehe den Kopf von ags-home.template). Einen
    Streifen reserviert es nicht; es haelt sich an die Streifen der
    anderen (Exclusivity.NORMAL), damit keine Symbolzeile unter Leiste
    oder Fuss liegt.
    """
    builders = {
        template.name: _code(template)
        for template in _ags_templates()
        if template != FACTORY and "new Astal.Window(" in _code(template)
    }
    assert set(builders) == {"ags-bar.template", "ags-dock.template",
                             "ags-home.template",
                             "ags-notifications.template",
                             "ags-power-button.template",
                             "ags-starter-button.template"}, (
        f"es bauen sich {sorted(builders)} ihr Fenster selbst - erwartet "
        f"sind die Leiste, das Dock, das Home, die Benachrichtigungen und "
        f"die zwei Knoepfe am Dock (Abschalten links, Starter rechts). "
        f"Kommt eine Flaeche dazu, gehoert sie durch die Fabrik; faellt "
        f"eine weg, ist diese Aufzaehlung veraltet")

    for name in ("ags-bar.template", "ags-dock.template"):
        assert NOT_A_MODAL[0] in builders[name], (
            f"{name} reserviert keine exklusive Zone mehr - dann ist es "
            f"kein Streifen, sondern ein Fenster vor der Arbeit")
    for name in ("ags-notifications.template", "ags-power-button.template",
                 "ags-starter-button.template"):
        assert NOT_A_MODAL[1] in builders[name], (
            f"{name} nimmt die Tastatur - dann ist es etwas, das man "
            f"bedient, und gehoert durch die Fabrik. Diese Datei gehoert "
            f"einem anderen Auftrag; wenn diese Zeile rot ist, ist das "
            f"ein Befund fuer ihn und keine Einladung, hier eine "
            f"Ausnahme einzutragen")


def test_there_is_no_side_door_into_the_placement():
    """Die Abkuerzung ist zu.

    getOverlayPosition() war exportiert, und genau ein Widget hat davon
    Gebrauch gemacht - das eine, das dann ohne Deckel dastand. Eine
    exportierte Abkuerzung wird genommen.
    """
    factory = _code(FACTORY)
    assert "export async function getOverlayPosition" not in factory, (
        "die Lageberechnung ist wieder exportiert. Damit gibt es einen "
        "zweiten Weg, ein Fenster zu stellen, und er fuehrt an jedem "
        "Deckel vorbei")
    assert "export function createOverlayWindow" in factory, (
        "die Fabrik ist nicht mehr exportiert")

    for template in _ags_templates():
        if template == FACTORY:
            continue
        code = _code(template)
        assert "getOverlayPosition" not in code, (
            f"{template.name} holt sich die Lage an der Fabrik vorbei")


# Wer aus utils/overlay NUR EINEN TYP holt.
#
# DAS WAR BIS ZUM 17.08.2026 EIN DATEINAME, UND GENAU DAVOR WARNT DER
# KOPF DIESER DATEI
#     "Eine Liste von Dateinamen waere genau das, was hier schiefgegangen
#     ist: jemand traegt seine Datei ein, und die Regel gilt fuer alle
#     ausser ihm." Ausgenommen war `ags-config.template`, mit der
#     richtigen Begruendung - es holt sich den TYP OverlayWidget und baut
#     selbst kein Fenster - und mit dem falschen Mittel, dem Namen.
#
#     Am 17.08.2026 kam ein zweiter solcher Leser dazu:
#     ags-bar.template braucht OverlayAnchor, um zu sagen, WO geklickt
#     wurde. Ein zweiter Name in derselben Liste waere der Anfang von
#     einer Liste, in der jeder steht.
#
# DIE EIGENSCHAFT STATT DES NAMENS, und sie ist SCHAERFER als vorher
#     `import type` ist die eine Einfuhrform, von der nachweislich
#     nichts uebrig bleibt: esbuild wirft sie restlos weg, es gibt zur
#     Laufzeit keinen Zugriff auf irgendein Teil der Fabrik. Wer
#     dagegen einen WERT holt - und sei es nur getOverlayPosition -,
#     faellt jetzt auch dann auf, wenn er ags-config.template heisst.
#     Die alte Ausnahme war ein Freibrief fuer eine ganze Datei; diese
#     hier gilt fuer eine Zeilenform.
_TYPE_ONLY = re.compile(
    r'^\s*import\s+(type\s+)?\{[^}]*\}\s+from\s+"[^"]*utils/overlay"',
    re.M)


def _takes_only_types(path: Path) -> bool:
    holt = _TYPE_ONLY.findall(_code(path))
    return bool(holt) and all(gruppe.strip() == "type" for gruppe in holt)


_TOOLBOX_READERS = [
    path for path in _ags_templates()
    if "utils/overlay" in path.read_text(encoding="utf-8")
    and path.name != "ags-overlay-utils.template"]


def test_the_type_only_exemption_still_lets_the_rule_reach_somebody():
    """Ein Kriterium, das alle durchlaesst, ist keines.

    GEZAEHLT am 17.08.2026: dreizehn Vorlagen lesen utils/overlay, elf
    davon rufen die Fabrik, zwei holen nur einen Typ (app.ts und die
    Leiste).

    DIE SCHWELLE IST SEIT DEM 18.08.2026 EINE RATSCHE, DIESELBE FORM WIE
    ERLAUBT IN tests/src/test_button_kit.py, UND AUS DEMSELBEN GRUND
        Bluetooth (Aufgabe 7), Netzwerk (Aufgabe 8) und VPN (Aufgabe 9)
        sind je zur Seite der Schale geworden und rufen darum
        createOverlayWindow nicht mehr selbst - sie holen aus
        utils/overlay seither NUR NOCH den Typ ShellSeite (`import type`)
        und zaehlen deshalb zu Recht als "nur ein Typ". Das ist keine
        Aufweichung des Kriteriums, sondern die Bevoelkerung, gegen die
        es geprueft wird, wird ECHT kleiner - dieselbe Verschiebung, die
        die Knopf-Ratsche in test_button_kit.py schon fuer CSS-Klassen
        durchlaeuft.

        GEZAEHLT nach jeder der drei Aufgaben (`_TOOLBOX_READERS`/
        `_takes_only_types` aus diesem Modul, nicht abgeschrieben):

            11  18.08.2026  Aufgabe 7 (Bluetooth): 14 Leser insgesamt,
                            3 "nur ein Typ" (bar, bluetooth, config).
            10  18.08.2026  Aufgabe 8 (Netzwerk): 4 "nur ein Typ" (+
                            network) - genau an der damaligen Schwelle,
                            noch gruen.
             9  18.08.2026  Aufgabe 9 (VPN): 5 "nur ein Typ" (+ vpn) -
                            unter der alten Schwelle von 10. GESENKT auf
                            9, mit dieser Historie, nicht stillschweigend
                            anders herum abgeschwaecht (etwa durch
                            Entfernen der Zusicherung).

        NEUN VORLAGEN WERDEN DANACH IMMER NOCH GEGEN DIE FABRIKPFLICHT
        GEHALTEN - das Kriterium laesst also weiterhin echte Faelle
        durchfallen, wenn eine von ihnen ihr eigenes Fenster baut
        (battery, calendar, control-center, disk, notifications,
        shortcuts, style-editor, vpn-settings, wallpaper). Faellt diese
        Zahl kuenftig weiter (ein zehntes Fenster wird zur Seite), sinkt
        die Schwelle mit derselben Begruendung weiter - sie darf nur
        SINKEN, nie angehoben werden, um ein Kriterium zu retten, das zu
        viel durchlaesst.
    """
    geprueft = [path for path in _TOOLBOX_READERS
                if not _takes_only_types(path)]
    assert len(geprueft) >= 9, (
        f"nur {len(geprueft)} Vorlagen werden noch gegen die Fabrikregel "
        "gehalten - das Kriterium 'nur ein Typ' laesst zu viele durch")


@pytest.mark.parametrize("template", [
    path for path in _TOOLBOX_READERS if not _takes_only_types(path)])
def test_who_imports_the_toolbox_imports_the_factory(template):
    """Wer utils/overlay anfasst, ruft EINE der beiden Fabriken.

    Ausgenommen ist, wer AUSSCHLIESSLICH `import type` schreibt - siehe
    _takes_only_types() darueber. Das sind app.ts, das die Fenster in
    einem Feld fuehrt, und die Leiste, die sagen muss, wo geklickt
    wurde. Beide bauen kein Fenster, und beide koennen es nach dem
    Uebersetzen auch gar nicht mehr.

    ZWEI NAMEN SEIT DEM 19.08.2026 (Aufgabe 32), UND DAS IST EINE
    VERSCHAERFUNG UND KEINE AUFWEICHUNG
        utils/overlay hat seit Aufgabe 5 (18.08.2026) ZWEI Fabriken:
        createOverlayWindow und createShellWindow, und die zweite ruft
        die erste (siehe ihren Kopf dort - "createShellWindow BAUT KEIN
        ZWEITES ASTAL.WINDOW VON HAND"). Diese Zusicherung kannte nur
        die erste.

        GEMESSEN am 19.08.2026: ags-control-center.template ruft seit
        Aufgabe 6 ausschliesslich createShellWindow und bestand hier
        trotzdem - der Name createOverlayWindow steht dort nur noch
        dreimal, zweimal in einem `//`-Kommentar (die _code() streicht)
        und einmal in einer `*`-Zeile eines Blockkommentars (die sie
        NICHT streicht). Die Fabrikpflicht war fuer die Schale also seit
        einem Tag folgenlos: haette das Kontrollzentrum sein Fenster von
        Hand zusammengesetzt, waere es hier gruen geblieben, solange nur
        der alte Fabrikname irgendwo im Fliesstext stand.

        Mit beiden Namen greift sie fuer beide Bauweisen WIRKLICH - und
        ein Blockkommentar allein rettet keine Vorlage mehr, weil der
        Aufruf, den sie tatsaechlich macht, jetzt auch benannt ist.
    """
    code = _code(template)
    assert "createOverlayWindow" in code or "createShellWindow" in code, (
        f"{template.name} importiert aus utils/overlay, ruft aber weder "
        f"createOverlayWindow noch createShellWindow - dann holt es sich "
        f"Teile und setzt sie selbst zusammen")


def test_the_factory_can_do_what_the_bypass_was_built_for():
    """Warum die Umgehung ueberhaupt entstanden ist.

    ags-network.template brauchte EIN Verhalten, das die Fabrik nicht
    konnte: ESC soll aus der Passwort- und der Detailansicht zurueck zur
    Liste, statt zu schliessen. Dafuer hat es sich ein ganzes Fenster
    gebaut und alles andere gleich mit verloren.

    Eine Fabrik, der eine Sache fehlt, wird umgangen. Also fehlt sie
    nicht mehr.

    KORRIGIERT am 18.08.2026 (Aufgabe 8, "Netzwerk wird eine Seite"):
    hier stand bis dahin `network = _code(TEMPLATES / "ags-network
    .template"); assert "onEscape:" in network` - das war der Beweis,
    dass `OverlayConfig.onEscape` einen Leser hat. Netzwerk ist seit
    Aufgabe 8 keine eigene `createOverlayWindow`-Aufruferin mehr (siehe
    tests/src/test_modal_rule.py::test_who_imports_the_toolbox_imports_the_factory,
    das es fuer diese Vorlage seither NICHT mehr verlangt) und kann
    darum auch `OverlayConfig.onEscape` nicht mehr setzen - das Feld
    gehoert zu einer Fabrik, die diese Vorlage nicht mehr direkt ruft.
    Netzwerk verlangt darum nicht mehr, ESC selbst zu schliessen, ist
    also NICHT die alte Behauptung geworden, sondern eine ANDERE
    Vorlage: `ags-wallpaper.template` (Loeschbestaetigung) ist seit
    Aufgabe 10 ein zweiter, unabhaengiger Nutzer von `OverlayConfig
    .onEscape` und haelt das Feld allein am Leben - die Zusicherung
    zeigt jetzt auf diese Datei.

    Netzwerk bekommt eine EIGENE, zweite Pruefung darunter: es benutzt
    denselben Grundsatz (ESC geht aus der Unteransicht zurueck, nicht
    zu) jetzt eine Stufe tiefer - ein EIGENER
    `Gtk.EventControllerKey`, angehaengt an das Wurzel-Widget der
    Seite und NICHT an `win` (siehe die Begruendung in
    ags-overlay-utils.template bei `buildContent` von
    `createShellWindow` und im Bericht zu Aufgabe 8).
    """
    factory = _code(FACTORY)
    assert "onEscape?: () => boolean" in factory, (
        "die Fabrik kann ESC nicht mehr an das Fenster weiterreichen - "
        "dann braucht das naechste Fenster mit einer Unteransicht wieder "
        "einen eigenen Bau")
    assert "if (config.onEscape?.()) return true" in factory, (
        "onEscape wird angeboten und nicht gerufen")

    wallpaper = _code(TEMPLATES / "ags-wallpaper.template")
    assert "onEscape:" in wallpaper, (
        "kein Fenster benutzt OverlayConfig.onEscape mehr - dann ist das "
        "Feld in der Fabrik ohne Leser")

    network = _code(TEMPLATES / "ags-network.template")
    assert "onEscape:" not in network, (
        "das Netzwerkfenster setzt wieder OverlayConfig.onEscape - das "
        "Feld gehoert zu createOverlayWindow(), das diese Seite seit "
        "Aufgabe 8 nicht mehr selbst ruft (siehe "
        "test_who_imports_the_toolbox_imports_the_factory)")
    assert "new Gtk.EventControllerKey()" in network, (
        "die Netzwerk-Seite hat keinen eigenen Tastenabfaenger mehr - "
        "ohne ihn geht ESC aus der Passwort-/Detailansicht nicht mehr "
        "zurueck zur Liste, sondern schliesst sofort die ganze Schale")
    assert "container.add_controller(escController)" in network, (
        "der Tastenabfaenger der Netzwerk-Seite haengt nicht mehr an "
        "ihrem eigenen Wurzel-Widget (`container`) - haenge er "
        "stattdessen an `win`, liefe er NACH dem Controller der Schale "
        "und niemals VOR ihm (Bubble-Reihenfolge), und die Ruecknahme "
        "aus der Unteransicht wuerfe die ganze Schale zu, statt zur "
        "Liste zurueckzugehen")


# --------------------------------------------------------------------
# 2. Die eigenen Programme: derselbe Deckel aus derselben Quelle
# --------------------------------------------------------------------

# Die Abdruecke von MEASURE_MODAL_SHARE, und warum es sie gibt.
#
# src/sizes.py sagt es selbst: "eine Anzahl und keine Laenge ... gelesen
# wird sie nicht von einer Vorlage, sondern von den Programmen, die ein
# solches Fenster aufziehen". Vier von fuenf dieser Programme koennen
# src/sizes.py nicht importieren - zwei sind C++, eines ist ein eigenes
# Python-Paket, eines ist TypeScript. Also traegt jedes die Zahl selbst,
# und DIESE Stelle haelt sie zusammen.
#
# WARUM DIE ZAHL NICHT EINFACH EIN PLATZHALTER IST
#     GEMESSEN am 12.08.2026: ein Eintrag in sizes.TABLE muesste
#     tests/src/test_sizes.py::test_no_size_can_be_rounded_down_to_nothing
#     bestehen, und das prueft `int(re.match(r"\\d+", value).group()) >= 1`
#     ueber JEDEN erzeugten Wert. Aus 0.5 liest dieser Ausdruck eine 0.
#     Ein Anteil ist keine Laenge, und die Groessentabelle ist eine
#     Tabelle von Laengen.
IMPRINTS = {
    "menu/zepos_menu/window.py": r"^MODAL_SHARE = ([0-9.]+)$",
    "src/templates/ags-overlay-utils.template":
        r"^const MODAL_SHARE = ([0-9.]+)$",
    "plugins/hyprlaunch/include/hyprlaunch/Config.hpp":
        r"static constexpr double MODAL_SHARE = ([0-9.]+);",
    "plugins/hyprclipx/include/hyprclipx/Config.hpp":
        r"static constexpr double MODAL_SHARE = ([0-9.]+);",
}


def _read_source(path: str) -> str:
    """Reads one of the paths above or below.

    Most of them live in this tree and are read from ROOT directly. The
    two plugins/ ones are not, since 19.08.2026: the unmodified upstream
    source they patch cannot live in this repository (plugins/LICENSE
    has the account), so tests/adopted_plugin_source.py reconstructs it
    from the network, exactly as packaging/zepos-hyprlaunch/PKGBUILD and
    packaging/zepos-hyprclipx/PKGBUILD now build it.
    """
    for name in ("hyprlaunch", "hyprclipx"):
        prefix = f"plugins/{name}/"
        if path.startswith(prefix):
            return (plugin_source(name) / path[len(prefix):]).read_text(
                encoding="utf-8")
    return (ROOT / path).read_text(encoding="utf-8")


@pytest.mark.parametrize("path,pattern", sorted(IMPRINTS.items()))
def test_every_own_program_caps_at_the_share_from_the_size_table(path, pattern):
    """Vier Programme, eine Zahl.

    Bis zum 12.08.2026 hatte MEASURE_MODAL_SHARE genau EINEN Leser
    (menu/zepos_menu/window.py); ein zweiter kam an dem Tag dazu
    (ags-overlay-utils.template). hyprlaunch rechnete gegen den GANZEN
    Schirm, hyprclipx gegen gar nichts. Drei Programme mit derselben
    Aufgabe und drei Regeln sind drei Regeln.
    """
    source = _read_source(path)
    found = re.search(pattern, source, re.M)
    assert found, f"{path} kennt keinen Anteil MODAL_SHARE mehr"
    assert float(found.group(1)) == sizes.MEASURE_MODAL_SHARE, (
        f"{path} deckelt bei {found.group(1)}, die Groessentabelle sagt "
        f"{sizes.MEASURE_MODAL_SHARE}")


@pytest.mark.parametrize("path,rule", sorted({
    # Wo der Anteil angewendet wird, und woran man es erkennt. Die Zahl
    # zu KENNEN ist die halbe Sache - ags-network.template kannte den
    # Deckel auch und stand trotzdem 181 Punkte darueber.
    "menu/zepos_menu/window.py": "int(shortest * MODAL_SHARE)",
    "src/templates/ags-overlay-utils.template": "mh * MODAL_SHARE",
    "plugins/hyprlaunch/include/hyprlaunch/Config.hpp":
        "screenEdge * MODAL_SHARE",
    "plugins/hyprclipx/include/hyprclipx/Config.hpp":
        "screenEdge * MODAL_SHARE",
}.items()))
def test_the_share_is_multiplied_by_something_measured(path, rule):
    """Und der Anteil trifft auf einen GEMESSENEN Schirm.

    Nicht auf eine Zahl aus der Konfiguration: der Deckel soll ja
    gerade das begrenzen, was dort steht.
    """
    assert rule in _read_source(path), (
        f"{path} multipliziert den Anteil nicht mehr mit {rule}")


# Wonach im Baum gesucht wird, um ein Programm zu finden, das eine
# Layer-Shell-Flaeche aufzieht. Beide Bindungen, weil zwei Sprachen im
# Spiel sind.
LAYER_SHELL_CALLS = ("gtk_layer_init_for_window", "LayerShell.init_for_window")

# Die Programme, die eine solche Flaeche aufziehen, ohne sich zu
# deckeln - und was sie stattdessen sind.
#
# LEER SEIT DEM 19.08.2026 (Aufgabe 26), UND DAS IST DER RICHTIGE STAND
#     Der einzige Eintrag, den dieses Woerterbuch je hatte, war
#     "logout/zepos-logout.c": eine Abmeldemaske, die sich an ALLEN VIER
#     Kanten verankerte, um die Sitzung zurueckzunehmen. Das Programm ist
#     mit Aufgabe 26 gefallen (Regel 14 - geloescht, nicht als veraltet
#     markiert); sein Nachfolger, ags-logout.template, ist KEIN eigenes
#     Layer-Shell-Programm mehr, sondern ein Fenster aus
#     createOverlayWindow() wie jedes andere - es deckelt sich auf
#     MEASURE_MODAL_SHARE genau wie die uebrigen elf AGS-Ueberlagerungen
#     und braucht darum keine Sonderrolle als "Maske ohne Deckel".
#
#     Ein leeres Woerterbuch ist hier keine Luecke: es bedeutet wortwoertlich,
#     dass KEIN eigenes Programm dieses Baums sich mehr unbedeckelt an
#     alle vier Kanten haengt. test_no_program_opens_a_layer_shell_
#     window_without_a_rule() unten prueft das GEGEN DEN BAUM (nicht
#     gegen diese Liste) und faende ein neues full-screen-Programm auch
#     ohne einen Eintrag hier.
FULL_SCREEN_MASKS: dict[str, str] = {}


def _own_layer_shell_programs() -> set[str]:
    """Jedes eigene Programm, das eine Layer-Shell-Flaeche aufzieht - im
    Arbeitsbaum UND in den beiden rekonstruierten Plugin-Baeumen, als
    dieselbe Art relativer Pfad, die FULL_SCREEN_MASKS und `known` unten
    schon immer benutzt haben.

    hyprlaunch und hyprclipx liegen seit dem 19.08.2026 nicht mehr unter
    root/plugins/ (siehe tests/adopted_plugin_source.py, plugins/
    LICENSE) - ein blosses ROOT.rglob() faende ihre beiden Aufrufer
    darum nicht mehr, und `known` unten wuerde zwei Eintraege nennen, die
    programs nie erreicht. Deshalb der zweite Durchgang.
    """
    programs: set[str] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in (".c", ".cpp", ".py"):
            continue
        relative = path.relative_to(ROOT).as_posix()
        # tests/ baut Attrappen, um genau diese Programme zu messen.
        if relative.startswith(("tests/", ".venv/", "out/")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(call in text for call in LAYER_SHELL_CALLS):
            programs.add(relative)

    for name in ("hyprlaunch", "hyprclipx"):
        plugin_root = plugin_source(name)
        for sub in ("src", "include"):
            directory = plugin_root / sub
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.suffix not in (
                        ".c", ".cpp", ".py"):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if any(call in text for call in LAYER_SHELL_CALLS):
                    programs.add(
                        f"plugins/{name}/{sub}/"
                        f"{path.relative_to(directory).as_posix()}")
    return programs


def test_no_program_opens_a_layer_shell_window_without_a_rule():
    """Die Vollzaehligkeit, aus dem Baum gelesen statt aufgezaehlt.

    Eine Liste von Hand haette genau das Programm nicht, das jemand
    hinzufuegt, ohne die Regel zu kennen - also genau den Fall, den
    diese Zusicherung fangen soll.
    """
    programs = _own_layer_shell_programs()

    known = set(FULL_SCREEN_MASKS) | {
        "menu/zepos_menu/window.py",
        "plugins/hyprlaunch/src/LauncherRenderer.cpp",
        "plugins/hyprclipx/src/ClipboardRenderer.cpp",
    }
    assert programs == known, (
        f"diese Programme ziehen eine Layer-Shell-Flaeche auf, ohne dass "
        f"eine Regel fuer ihre Groesse aufgeschrieben ist: "
        f"{sorted(programs - known)}. Entweder deckeln sie sich auf "
        f"MEASURE_MODAL_SHARE, oder sie sind eine Maske ueber den ganzen "
        f"Schirm und verankern sich an allen vier Kanten. "
        f"Fehlend: {sorted(known - programs)}")


@pytest.mark.parametrize("path,proof", sorted(FULL_SCREEN_MASKS.items()))
def test_a_program_without_a_cap_is_a_full_screen_mask(path, proof):
    """Wer sich nicht deckelt, deckt ab - und beweist es im Quelltext."""
    code = _code(ROOT / path)
    assert proof in code, (
        f"{path} deckelt sich nicht auf MEASURE_MODAL_SHARE und "
        f"verankert sich auch nicht an allen Kanten. Damit ist es weder "
        f"eine Maske noch ein Fenster, das sich vorstellt")
    assert "GTK_LAYER_SHELL_EDGE_ENTRY_NUMBER" in code, (
        f"{path} verankert nicht mehr jede Kante - eine Maske, die drei "
        f"Kanten haelt, laesst einen Streifen der Sitzung bedienbar")
