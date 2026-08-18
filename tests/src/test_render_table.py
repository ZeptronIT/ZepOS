# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Abschrift im Render-Aufbau muss zum Erzeuger passen.

WARUM ES DIESEN WAECHTER GIBT, GEMESSEN AM 19.08.2026
    `tests/render/desktop_session.py` traegt eine Tabelle RENDERED:
    welche Vorlage zu welcher Datei wird. Ihr Kommentar sagt, sie sei
    "aus den case-Zweigen von src/generate_config.sh abgelesen, nicht
    geraten" - und das stimmte einmal.

    Am 18.08.2026 entstand `src/templates/ags-kit.template`, das
    gemeinsame Bauteil-Kit aller AGS-Fenster. generate_config.sh bekam
    seinen Zweig, die Abschrift nicht. Gemerkt hat es niemand: die
    Render-Tests laufen nicht im sicheren Lauf, weil sie einen
    verschachtelten Compositor starten und Fenster auf den Bildschirm
    holen.

    Am 19.08.2026 lief die volle Suite zum ersten Mal wieder, und der
    Befund war:

        Could not resolve "../utils/kit"
          widget/NetworkManager.tsx:172
        44 passed, 15 errors

    Fuenfzehn Fehler, bevor der erste Bildpunkt gemessen war. Am echten
    System war nichts kaputt - generate_config.sh kannte das Kit die
    ganze Zeit. Kaputt war die Abschrift, und eine Abschrift, die
    lautlos veraltet, ist schlimmer als keine: sie sieht wie Deckung aus.

    Dieser Test ist die Antwort darauf. Er steht im SICHEREN Lauf, also
    laeuft er bei jeder Aenderung mit, und er wird rot, sobald
    generate_config.sh ein Ziel bekommt, das die Tabelle nicht kennt.

WAS ER NICHT PRUEFT
    Ob der Pfad stimmt. Das kann er nicht ohne den Erzeuger selbst
    auszufuehren, und generate_config.sh zu starten ist verboten - es
    beendet Waybar und AGS des Nutzers. Geprueft wird die Frage, an der
    es tatsaechlich gescheitert ist: KENNT die Tabelle jedes Ziel, das
    eine TypeScript-Datei erzeugt?
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
ERZEUGER = WURZEL / "src" / "generate_config.sh"

sys.path.insert(0, str(WURZEL / "tests" / "render"))


def _ziele_des_erzeugers():
    """Jeder `ags-…)`-Zweig mit seinem CONFIG_FILE.

    Gelesen wird der Text, nicht die Shell - der Erzeuger darf hier
    unter keinen Umstaenden laufen.
    """
    text = ERZEUGER.read_text(encoding="utf-8")
    ziele = {}
    aktuell = None
    for zeile in text.splitlines():
        # ZIFFERN GEHOEREN IN DIE KLASSE, und das ist gemessen: mein
        # erster Ausdruck hiess [a-z-]+ und uebersah `ags-i18n)` in
        # Zeile 750 - der dritte Test hier hat es sofort gemeldet.
        zweig = re.match(r"\s*(ags-[a-z0-9-]+)\)\s*$", zeile)
        if zweig:
            aktuell = zweig.group(1)
            continue
        if aktuell:
            datei = re.search(r'CONFIG_FILE="([^"]+)"', zeile)
            if datei:
                ziele[aktuell] = datei.group(1)
                aktuell = None
    return ziele


def test_der_erzeuger_ist_ueberhaupt_lesbar():
    """Ohne diese Zusicherung wuerde ein leeres Ergebnis alles gruen faerben."""
    ziele = _ziele_des_erzeugers()
    assert len(ziele) >= 20, (
        f"nur {len(ziele)} ags-Ziele in generate_config.sh gefunden - "
        "entweder hat sich seine Schreibweise geaendert, oder dieser "
        "Leser ist kaputt. Beides macht den Waechter darunter wertlos.")


def test_jede_erzeugte_typescript_datei_steht_in_der_abschrift():
    from desktop_session import RENDERED

    bekannt = {
        Path(pfad).name
        for pfad in RENDERED
        if pfad.startswith("templates/ags-")
    }

    fehlend = []
    for ziel, datei in sorted(_ziele_des_erzeugers().items()):
        # Nur was der Render-Aufbau ueberhaupt braucht: die Bausteine der
        # AGS-Sitzung. Die drei *-scripts erzeugen Shell-Dateien
        # (privacy.sh, media.sh, updates.sh) und werden von keiner
        # .tsx importiert - sie fehlen dort mit Absicht.
        if not datei.endswith((".ts", ".tsx")):
            continue
        if f"{ziel}.template" not in bekannt:
            fehlend.append(f"{ziel} -> {datei}")

    assert fehlend == [], (
        "generate_config.sh erzeugt TypeScript, das die Tabelle RENDERED "
        "in tests/render/desktop_session.py nicht kennt:\n  "
        + "\n  ".join(fehlend)
        + "\n\nDie Render-Tests koennen damit keine Sitzung bauen - "
        "esbuild bricht mit 'Could not resolve' ab, bevor irgendetwas "
        "gemessen wird. Trag das Ziel dort ein, so wie es im case-Zweig "
        "steht.")


def test_die_abschrift_erfindet_keine_ziele():
    """Die Gegenrichtung: eine Vorlage, die der Erzeuger gar nicht kennt.

    Sie waere genauso ein Auseinanderlaufen, nur andersherum - der
    Render-Aufbau baute etwas, das auf einem echten System nie entsteht,
    und pruefte damit eine Sitzung, die es nicht gibt.
    """
    from desktop_session import RENDERED

    ziele = _ziele_des_erzeugers()
    erfunden = [
        pfad for pfad in sorted(RENDERED)
        if pfad.startswith("templates/ags-")
        and Path(pfad).stem not in ziele
    ]
    assert erfunden == [], (
        "die Tabelle RENDERED nennt Vorlagen, zu denen generate_config.sh "
        f"keinen Zweig hat: {erfunden}")
