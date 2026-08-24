# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Kopplungsbestaetigung muss erscheinen, und sie muss ein Fenster sein.

WARUM DIESE DATEI EXISTIERT
    Weil der Ausfall, den sie bewacht, VOLLKOMMEN STILL war. Der Nutzer
    hat am 21.08.2026 gemeldet: "wenn ich mich bei zepos bluetooth
    versuche zu verbinden klappt das, es steht verbunden - aber es fehlt
    die kopplungsanfrage, die man mit ja oder nein bestaetigen muss."

    Es gab keinen Fehler, kein Protokoll, keinen leeren Dialog. Es gab
    nur eine Kopplung, die gelang, ohne zu fragen - und das ist die
    Beschreibung einer Sicherheitsluecke, nicht einer fehlenden Meldung.

DIE KETTE, GEMESSEN AM 21.08.2026 AN QUELLTEXT UND AM LAUFENDEN SYSTEM
    1. Niemand meldet auf ZepOS einen BlueZ-Agenten an. `grep` ueber den
       ganzen Baum: null Treffer fuer org.bluez.Agent1 und
       AgentManager1.
    2. bluetoothctl meldet im Stapelbetrieb ABSICHTLICH keinen an.
       bluez 5.87 client/main.c:501 haengt agent_register an
       `!bt_shell_get_env("NON_INTERACTIVE")`, und
       src/shared/shell.c:1415 setzt das, sobald Argumente da sind.
       `bluetoothctl connect <adresse>` - so ruft es
       ags-bluetooth.template:642 - hat welche.
    3. Ohne Agenten setzt bluetoothd NoInputNoOutput
       (src/agent.c:126-137 -> src/adapter.c:9167-9173).
    4. Und dann bestaetigt der KERN selbst. Linux v7.1
       net/bluetooth/hci_event.c:5397 schickt HCI_OP_USER_CONFIRM_REPLY,
       ohne dem Benutzerland etwas zu sagen. Kein D-Bus-Ereignis, kein
       Fenster. Das Verfahren heisst Just Works und hat per
       Kernspezifikation KEINEN MITM-Schutz.

    Nebenbefund derselben Messung, den niemand kannte: eine
    Bluetooth-TASTATUR ist auf ZepOS ueberhaupt nicht koppelbar. Sie
    braucht RequestPasskey, das laeuft ueber new_auth()
    (src/device.c:7620-7645), und das liefert ohne Agenten NULL.

WAS DIESE DATEI MISST UND WAS NICHT
    Sie misst TEXT - die Vorlage und das Rezept. Ob der Dialog auf einem
    echten Schirm wirklich obenauf schwebt, wurde am 21.08.2026 EINMAL
    in einem verschachtelten Hyprland gegen ein nachgebautes org.bluez
    gemessen (der Bluetooth-Dienst des Nutzers blieb dabei unberuehrt);
    das Ergebnis steht in den einzelnen Zusicherungen, wo es die Zahl
    begruendet. Ein Dauerlauf dafuer haette einen Compositor UND einen
    Bluetooth-Adapter gebraucht - den zweiten hat kein Testrechner.

DIESE DATEI IST EINE ZWISCHENLOESUNG UND WEISS DAS
    blueman ist GTK3 (BluezAgent.py:18: gi.require_version("Gtk",
    "3.0")) und steht damit gegen die Entscheidung vom 11.08.2026, die
    tests/src/test_gtk4_only.py bewacht. Ein eigener Agent als
    AGS-Fenster loest ihn ab. Wenn das geschieht, faellt diese Datei
    NICHT weg - sie wechselt die Zielangabe. Die Frage "erscheint die
    Bestaetigung ueberhaupt" ist von blueman unabhaengig.
"""
import re
from pathlib import Path

import pytest

from tests.generated_tree import GeneratedTree, build

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
PACKAGING = REPOSITORY / "packaging"

UNIVERSAL = SRC / "templates" / "hyprland-universal-config.template"

# Der Lauf spawnt den Generator - dieselbe Marke und derselbe Grund wie
# in tests/src/test_usable_desktop.py.
pytestmark = pytest.mark.allow_subprocess


@pytest.fixture(scope="module")
def tree(tmp_path_factory) -> GeneratedTree:
    return build(tmp_path_factory.mktemp("bluetooth-pairing"))


def _uncommented(text: str) -> list[str]:
    """Die Zeilen ohne die, die nur Kommentar sind.

    Dieselbe Falle wie in tests/src/test_gtk4_only.py, und hier ist sie
    besonders scharf: der Block ueber der Startzeile ERKLAERT auf
    achtzig Zeilen, was ohne ihn passiert, und nennt dabei jeden Namen,
    nach dem hier gesucht wird. Eine Pruefung als Teilzeichenkette waere
    von der Erklaerung wahr geworden.
    """
    return [line.strip() for line in text.splitlines()
            if not line.lstrip().startswith("#")]


def _startup_lines(text: str) -> list[str]:
    return [line for line in _uncommented(text) if line.startswith("exec-once")]


def _agent_line(text: str) -> str:
    """Die eine Startzeile, die den Kopplungsagenten hochbringt."""
    found = [line for line in _startup_lines(text) if "blueman-applet" in line]
    assert len(found) == 1, (
        "es gibt nicht genau eine Startzeile fuer den Kopplungsagenten: "
        f"{found}")
    return found[0]


# --------------------------------------------------------------------
# 1. Es gibt ueberhaupt einen Agenten
# --------------------------------------------------------------------

def test_the_session_starts_a_bluetooth_pairing_agent_at_all():
    """Die Zusicherung, die den Ausfall vom 21.08.2026 gefunden haette.

    Ohne sie ist "es koppelt ohne zu fragen" ein Zustand, den niemand
    bemerkt - es gibt keinen Fehler, den man sehen koennte. Genau
    deshalb hat er es bis in eine veroeffentlichte Fassung geschafft.
    """
    line = _agent_line(UNIVERSAL.read_text(encoding="utf-8"))
    assert "setsid -f blueman-applet" in line, (
        "der Agent wird nicht abgekoppelt gestartet - ohne setsid haengt "
        f"er an der Startzeile: {line}")


def test_the_desktop_really_ships_the_agent_it_starts():
    """Eine Startzeile auf ein Programm, das kein Paket installiert,
    scheitert einmal pro Anmeldung, lautlos.

    WARUM DAS HIER STEHT UND NICHT IN test_usable_desktop.py
        Der dortige Waechter liest Startzeilen mit
        keybinds.command_words(), und das nimmt von jedem
        `&&`-Abschnitt nur das ERSTE Wort. In `setsid -f blueman-applet`
        ist das `setsid`, ein Programm des Grundsystems - der Name
        dahinter faellt durch. GEMESSEN am 21.08.2026: die Suite lief
        gruen, obwohl `blueman-applet` in keiner Tabelle stand.
        Dieselbe Luecke haben die Zeilen fuer ags und vpn-watcher; sie
        zu schliessen hiesse, command_words() eine setsid-Klammer
        beizubringen, und das gehoert nicht in diese Aufgabe. Bis dahin
        deckt diese Zusicherung den einen Namen ab, den sie einbringt.
    """
    recipe = (PACKAGING / "zepos-desktop" / "PKGBUILD").read_text(
        encoding="utf-8")
    depends = [line.strip() for line in _uncommented(recipe)]
    assert "'blueman'" in depends, (
        "die Sitzung startet blueman-applet, aber zepos-desktop "
        "installiert blueman nicht als harte Abhaengigkeit")


# --------------------------------------------------------------------
# 2. Die Frage wird ein FENSTER, keine Blase
# --------------------------------------------------------------------

def test_the_pairing_question_is_forced_into_a_window():
    """Die Zeile, ohne die der ganze Rest wirkungslos waere.

    WAS GEMESSEN WURDE, UND ES HAT DIE ENTSCHEIDUNG GEDREHT
        blueman zeigt RequestConfirmation NICHT als Fenster, sondern als
        Benachrichtigung mit den Aktionen confirm/deny
        (BluezAgent.py:200-217). Welche der beiden Formen es nimmt,
        entscheidet gui/Notification.py:287-305 an den Faehigkeiten des
        Benachrichtigungsdienstes.

        AstalNotifd meldet "actions" - gemessen mit `strings` an
        /usr/lib/libastal-notifd.so.0.1.0: body, actions, action-icons.
        ZepOS zeichnet aber NIRGENDS Aktionsknoepfe; `grep` nach
        `.actions`, `invoke(` und `get_actions` ueber alle Vorlagen
        findet nichts, und in ags-notifications.template ist der einzige
        Knopf einer Karte das X zum Schliessen.

        Am 21.08.2026 in einem verschachtelten Hyprland gegen ein
        nachgebautes org.bluez, mit einem Dienst, der genau AstalNotifds
        Faehigkeiten meldet:
          OHNE diese Zeile:  0 Fenster, dafuer eine Benachrichtigung mit
                             actions=[confirm, Confirm, deny, Deny] und
                             Zeitlimit 0 - sie verfaellt also nie und
                             traegt in ZepOS keinen einzigen Knopf.
          MIT dieser Zeile:  1 Fenster, Klasse blueman-applet,
                             Titel "Bluetooth".

        Ohne sie waere die Behebung also keine: der Nutzer saehe die
        Anfrage und koennte sie nicht beantworten, waehrend die Kopplung
        wartet. Die Zeile stand seit dem 03.08.2026 als offener Posten
        in docs/specs/2026-08-03-zepos-design.md:589.
    """
    line = _agent_line(UNIVERSAL.read_text(encoding="utf-8"))
    assert "gsettings set org.blueman.general notification-daemon false" in line, (
        "ohne notification-daemon=false zeigt blueman eine "
        "Benachrichtigung, und ZepOS zeichnet deren Knoepfe nicht")


def test_the_settings_are_applied_before_the_agent_starts():
    """Nebenlaeufigkeit, und sie ist hier nicht theoretisch.

    Hyprland fuehrt exec-once-Zeilen NICHT nacheinander aus. Stuenden
    die beiden `gsettings set` als eigene Zeilen ueber dem Start, dann
    entschiede der Zufall, ob blueman sie beim Lesen schon sieht - und
    ein Fehler, der nur manchmal auftritt, ist teurer als einer, der
    immer auftritt. Deshalb EINE Zeile mit `&&`.
    """
    line = _agent_line(UNIVERSAL.read_text(encoding="utf-8"))

    for setting in ("notification-daemon", "plugin-list"):
        assert line.index(setting) < line.index("blueman-applet"), (
            f"{setting} wird erst nach dem Start des Agenten gesetzt")

    # Und keine der beiden Einstellungen darf zusaetzlich als EIGENE
    # Startzeile auftauchen - das waere die nebenlaeufige Form zurueck.
    others = [other for other in _startup_lines(
                  UNIVERSAL.read_text(encoding="utf-8"))
              if "org.blueman" in other and other != line]
    assert others == [], (
        f"Blueman-Einstellungen in eigenen, nebenlaeufigen Zeilen: {others}")


# --------------------------------------------------------------------
# 3. Was abgeschaltet gehoert - und was auf keinen Fall
# --------------------------------------------------------------------

def _disabled(line: str) -> set[str]:
    """Die Namen aus der plugin-list, ohne das `!`."""
    match = re.search(r"plugin-list\s+\"\[(.*?)\]\"", line)
    assert match, f"keine plugin-list in der Startzeile: {line}"
    return set(re.findall(r"'!([A-Za-z]+)'", match.group(1)))


def test_the_tray_icon_is_off_together_with_the_plugin_that_pulls_it_back():
    """Die Falle, die eine reine Quelltextlesung uebersehen hat.

    ZepOS hat ein eigenes Bluetooth-Feld in der Leiste. Ein zweites
    Ablagesymbol daneben waere ein Rueckschritt, und `StatusIcon` ist
    abschaltbar - es traegt kein `__unloadable__ = False`.

    NUR REICHT DAS NICHT, UND DAS IST GEMESSEN
        __load_plugin in main/PluginManager.py:137-141 laedt
        `cls.__depends__` BEDINGUNGSLOS - die Abschaltliste wird dabei
        gar nicht gefragt. `ShowConnected` haengt an `StatusIcon` und
        holt es damit zurueck.

        Am 21.08.2026 im verschachtelten Lauf nachgestellt:
          plugin-list=['!StatusIcon']                  -> blueman-tray LAEUFT
          plugin-list=['!StatusIcon','!ShowConnected'] -> blueman-tray WEG
    """
    disabled = _disabled(_agent_line(UNIVERSAL.read_text(encoding="utf-8")))
    assert "StatusIcon" in disabled, (
        "das Ablagesymbol von blueman ist an - zwei Symbole fuer dieselbe "
        "Sache")
    assert "ShowConnected" in disabled, (
        "ShowConnected haengt an StatusIcon und holt es ueber "
        "__load_plugin zurueck - GEMESSEN lief blueman-tray dann weiter")


def test_the_agent_itself_is_never_switched_off():
    """Die Gegenrichtung, und ohne sie waere jede Zusicherung oben auch
    fuer eine Sitzung ohne Kopplungsbestaetigung wahr.

    `AuthAgent` IST der Zweck der ganzen Zeile. Es traegt kein
    __depends__ und niemand haengt daran, es ueberlebt also jede
    Abschaltung oben - solange niemand es selbst hineinschreibt.
    """
    disabled = _disabled(_agent_line(UNIVERSAL.read_text(encoding="utf-8")))
    assert "AuthAgent" not in disabled, (
        "AuthAgent ist abgeschaltet - damit startet ein Agentenprozess "
        "ohne Agenten, und die Luecke ist zurueck")


def test_the_plugins_that_fight_the_bar_over_the_adapter_are_off():
    """blueman-applet bringt ein Dutzend Module mit, nicht nur den
    Agenten. Fuenf davon fassen denselben Adapter an wie das
    Bluetooth-Feld der Leiste.

    WARUM JEDER EINZELNE NAME
        AutoConnect       verbindet von sich aus wieder, was der Nutzer
                          getrennt hat - es arbeitet gegen seine
                          Entscheidungen, und niemand braechte das mit
                          Bluetooth in Verbindung.
        DiscvManager      schaltet die Sichtbarkeit ein. Bei einer
                          Aufgabe, die gerade eine Kopplungsluecke
                          schliesst, ist das genau das Falsche.
        ConnectionNotifier meldet ein zweites Mal, was ZepOS meldet.
        PowerManager      schaltet den Adapter ein und aus.
        KillSwitch        MUSS mit: es haengt an PowerManager und holte
                          es sonst nach derselben Regel zurueck, mit der
                          ShowConnected das Symbol zurueckholt.
    """
    disabled = _disabled(_agent_line(UNIVERSAL.read_text(encoding="utf-8")))
    for plugin in ("AutoConnect", "DiscvManager", "ConnectionNotifier",
                   "PowerManager", "KillSwitch"):
        assert plugin in disabled, (
            f"{plugin} laeuft mit und fasst denselben Adapter an wie das "
            "Bluetooth-Feld der Leiste")


# --------------------------------------------------------------------
# 4. Das Fenster steht obenauf
# --------------------------------------------------------------------

def _rules_for(text: str, klass: str) -> list[str]:
    return [line for line in _uncommented(text)
            if line.startswith("windowrule") and f"^({klass})$" in line]


def test_the_pairing_window_floats_centred_and_pinned():
    """Die woertliche Beschwerde des Nutzers: sie erscheine "nicht als
    schwebendes fenster oben drauf".

    DIE KLASSE IST GEMESSEN, NICHT GERATEN
        Am 21.08.2026 im verschachtelten Hyprland meldete
        `hyprctl -j clients`: class=blueman-applet,
        initialClass=blueman-applet, title=Bluetooth, xwayland=false.
        Es ist die Klasse des APPLETS - der Dialog gehoert dem
        Agentenprozess, nicht blueman-manager.

    WAS DIE REGEL WIRKLICH AENDERT, EHRLICH
        float und center beschreiben, was ohnehin geschieht: der Dialog
        kam auch ohne Regel floating und mittig (Ausgang 456x521 an
        (4000,0), Fenster 438x198 an (4009,162) - das IST die Mitte).
        Sie stehen trotzdem da, damit die Lage nicht an einer
        GTK-Vorgabe haengt. `pin` ist der gemessene Unterschied: pinned
        sprang von false auf true, und damit folgt die Frage dem Nutzer
        ueber die Arbeitsbereiche.
    """
    rules = _rules_for(UNIVERSAL.read_text(encoding="utf-8"), "blueman-applet")
    assert rules, "es gibt keine Fensterregel fuer den Kopplungsdialog"

    body = " ".join(rules)
    for wanted in ("float on", "center on", "pin on"):
        assert wanted in body, (
            f"der Kopplungsdialog hat kein `{wanted}`: {rules}")


def test_the_pairing_rule_uses_the_syntax_hyprland_still_understands():
    """Hyprland 0.53 hat `windowrulev2` fallengelassen.

    Eine Regel in der alten Form wird nicht etwa abgelehnt - sie wird
    ignoriert, und der Dialog geht wieder irgendwo auf. Derselbe stille
    Ausfall wie der, den diese Datei bewacht.
    """
    rules = _rules_for(UNIVERSAL.read_text(encoding="utf-8"), "blueman-applet")
    for rule in rules:
        assert rule.startswith("windowrule ="), (
            f"keine 0.53er-Schreibweise: {rule}")
        assert "match:class" in rule, (
            f"die Regel waehlt das Fenster nicht ueber match:class: {rule}")

    # Und die alte Form nirgends in der ganzen Vorlage - sonst waere die
    # Zusicherung oben erfuellt und die Datei trotzdem halb veraltet.
    stale = [line for line in _uncommented(UNIVERSAL.read_text(encoding="utf-8"))
             if line.startswith("windowrulev2")]
    assert stale == [], f"abgelegte windowrulev2-Zeilen: {stale}"


# --------------------------------------------------------------------
# 5. Und es ueberlebt den Generator
# --------------------------------------------------------------------

def test_all_of_it_survives_the_generator_and_not_only_the_template(tree):
    """Die Vorlage ist nicht die Datei, die Hyprland liest.

    Jede Zusicherung darueber misst src/templates/. Wenn der Generator
    die Zeile verschluckte - an einem Platzhalter, an einer
    Anfuehrungszeichen-Behandlung, an einer Route, die es fuer diese
    Vorlage gar nicht gibt - waere alles davon gruen und der Schreibtisch
    trotzdem ohne Kopplungsbestaetigung.

    Die Anfuehrungszeichen sind hier kein Nebenschauplatz: die
    plugin-list traegt einfache Anfuehrungszeichen INNERHALB doppelter,
    und genau so muss sie bei der Shell ankommen.
    """
    generated = tree.config / "hypr" / "hyprland.conf"
    assert generated.is_file(), f"{generated} wurde nicht erzeugt"
    text = generated.read_text(encoding="utf-8")

    line = _agent_line(text)
    assert "notification-daemon false" in line
    assert "'!StatusIcon'" in line and "'!ShowConnected'" in line, (
        "die plugin-list hat die Anfuehrungszeichen nicht ueberlebt: "
        f"{line}")

    rules = _rules_for(text, "blueman-applet")
    body = " ".join(rules)
    for wanted in ("float on", "center on", "pin on"):
        assert wanted in body, (
            f"`{wanted}` fehlt in der ERZEUGTEN Konfiguration: {rules}")
