# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Kopplungsbestaetigung muss erscheinen, und sie muss ein Fenster sein.

WARUM DIESE DATEI EXISTIERT
    Weil der Ausfall, den sie bewacht, VOLLKOMMEN STILL war. Der Nutzer
    hat am 21.08.2026 gemeldet: "wenn ich mich bei zepos bluetooth
    versuche zu verbinden klappt das, es steht verbunden - aber es fehlt
    die kopplungsanfrage, die man mit ja oder nein bestaetigen muss. sie
    erscheint nicht als schwebendes fenster oben drauf."

    Es gab keinen Fehler, kein Protokoll, keinen leeren Dialog. Es gab
    nur eine Kopplung, die gelang, ohne zu fragen - und das ist die
    Beschreibung einer Sicherheitsluecke, nicht einer fehlenden Meldung.

DIE KETTE, GEMESSEN AM 21.08.2026 AN QUELLTEXT UND AM LAUFENDEN SYSTEM
    1. Niemand meldete auf ZepOS einen BlueZ-Agenten an. `grep` ueber
       den ganzen Baum: null Treffer fuer org.bluez.Agent1.
    2. bluetoothctl meldet im Stapelbetrieb ABSICHTLICH keinen an.
       bluez 5.87 client/main.c:501 haengt agent_register an
       `!bt_shell_get_env("NON_INTERACTIVE")`, und
       src/shared/shell.c:1415 setzt das, sobald Argumente da sind.
       `bluetoothctl connect <adresse>` - so ruft es
       ags-bluetooth.template - hat welche.
    3. Ohne Agenten setzt bluetoothd NoInputNoOutput
       (src/agent.c:126-137 -> src/adapter.c:9167-9173).
    4. Und dann bestaetigt der KERN selbst. Linux v7.1
       net/bluetooth/hci_event.c:5397 schickt HCI_OP_USER_CONFIRM_REPLY,
       ohne dem Benutzerland etwas zu sagen. Das Verfahren heisst Just
       Works und hat per Kernspezifikation KEINEN MITM-Schutz.

    Nebenbefund derselben Messung: eine Bluetooth-TASTATUR war auf
    ZepOS ueberhaupt nicht koppelbar. Sie braucht RequestPasskey, das
    laeuft ueber new_auth() (src/device.c:7620-7645), und das liefert
    ohne Agenten NULL.

DIE ZWEI STUFEN, UND WARUM DIESE DATEI BEIDE UEBERLEBT HAT
    STUFE 1 (21.08.2026, in 0.1.9 veroeffentlicht) war blueman-applet
    als Zwischenloesung - ein `exec-once` und drei Fensterregeln. Sie
    hat die Luecke am selben Tag geschlossen, um den Preis eines
    GTK3-Prozesses in der Sitzung.

    STUFE 2 (dieselbe Aufgabe) ist der eigene Agent:
    src/templates/ags-bluetooth-agent.template, ein org.bluez.Agent1 im
    AGS-Prozess. Mit ihm sind die Zeilen aus Stufe 1 GEFALLEN (Regel 14).

    Die Zusicherungen haben dabei die Zielangabe gewechselt, nicht den
    Zweck: die Frage "erscheint die Bestaetigung ueberhaupt, und kann
    man sie beantworten" ist von blueman unabhaengig. Deshalb prueft
    diese Datei jetzt BEIDE Richtungen - dass der eigene Agent
    vollstaendig da ist, UND dass der Vorgaenger wirklich weg ist.

WAS DIESE DATEI MISST UND WAS NICHT
    Sie misst TEXT. Ob das Fenster auf einem echten Schirm obenauf
    kommt und die Tastatur bekommt, wurde am 21.08.2026 in einem
    verschachtelten Compositor gegen ein nachgebautes org.bluez
    gemessen (der Bluetooth-Dienst des Nutzers blieb unberuehrt); die
    Zahlen stehen in den Zusicherungen, wo sie etwas begruenden. Ein
    Dauerlauf dafuer braeuchte einen Bluetooth-Adapter, den kein
    Testrechner hat.
"""
import re
from pathlib import Path

import pytest

from tests.generated_tree import GeneratedTree, build
# Auf Modulebene wie in tests/src/test_glass.py: ein Import
# INNERHALB eines Tests legt beim Uebersetzen ein __pycache__
# neben der Quelle an, und der Isolationswaechter in
# tests/conftest.py laesst das zu Recht nicht zu.
from tests.src import test_sizes

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
PACKAGING = REPOSITORY / "packaging"

UNIVERSAL = SRC / "templates" / "hyprland-universal-config.template"
AGENT = SRC / "templates" / "ags-bluetooth-agent.template"
APP = SRC / "templates" / "ags-config.template"
GENERATOR = SRC / "generate_config.sh"

# Der Namensraum der Layer-Shell-Flaeche. An EINER Stelle, weil mehrere
# Zusicherungen ihn brauchen.
NAMESPACE = "bluetooth-pairing"

pytestmark = pytest.mark.allow_subprocess


@pytest.fixture(scope="module")
def tree(tmp_path_factory) -> GeneratedTree:
    return build(tmp_path_factory.mktemp("bluetooth-pairing"))


def _ohne_kommentare(text: str, marker: str = "//") -> str:
    """Der Quelltext ohne die Zeilen, die nur Kommentar sind.

    DIESE DATEI BRAUCHT DAS DRINGENDER ALS JEDE ANDERE. Der Kopf von
    ags-bluetooth-agent.template ERKLAERT auf ueber hundert Zeilen, was
    ohne ihn passiert, und nennt dabei jeden Namen, nach dem hier
    gesucht wird - NoInputNoOutput, EXCLUSIVE, blueman-applet, die
    kaputte synchrone Form. Eine Pruefung als Teilzeichenkette waere von
    der Erklaerung wahr geworden, und zwar in beide Richtungen.
    """
    return "\n".join(zeile for zeile in text.splitlines()
                     if not zeile.lstrip().startswith(marker))


def _uncommented_lines(text: str, marker: str = "#") -> list[str]:
    return [zeile.strip() for zeile in text.splitlines()
            if not zeile.lstrip().startswith(marker)]


def _agent_code() -> str:
    return _ohne_kommentare(AGENT.read_text(encoding="utf-8"))


# --------------------------------------------------------------------
# 1. Es gibt einen Agenten - und GENAU einen
# --------------------------------------------------------------------

def test_the_tree_registers_exactly_one_bluetooth_agent():
    """Die Zusicherung, die den Ausfall vom 21.08.2026 gefunden haette -
    und zugleich die, die den Umstieg absichert.

    ZWEI Agenten am selben Adapter waeren schlimmer als einer: bluez
    fuehrt zwar mehrere, aber nur EINER ist der Vorgabe-Agent, und
    welcher gefragt wird, haengt dann daran, welche Anwendung die
    Kopplung angestossen hat. Der Nutzer saehe mal das eine Fenster,
    mal das andere - oder gar keines.

    Deshalb wird hier GEZAEHLT und nicht nur auf Vorhandensein geprueft.
    """
    aufrufe = []
    for pfad in sorted((SRC / "templates").glob("*.template")):
        code = _ohne_kommentare(pfad.read_text(encoding="utf-8"))
        if "RegisterAgent" in code:
            aufrufe.append(pfad.name)

    assert aufrufe == ["ags-bluetooth-agent.template"], (
        "genau eine Vorlage darf einen BlueZ-Agenten anmelden, gefunden: "
        f"{aufrufe}")


def test_the_agent_registers_with_the_only_capability_that_covers_all_seven():
    """KeyboardDisplay, und keine der anderen fuenf.

    org.bluez.AgentManager(5) laesst "", DisplayOnly, DisplayYesNo,
    KeyboardOnly, NoInputNoOutput und KeyboardDisplay zu. Nur die letzte
    deckt alle sieben Rueckfragen ab. NoInputNoOutput waere genau der
    Zustand, den diese Aufgabe beendet - der Adapter erzwaenge damit
    Just Works, also gar keine Rueckfrage.
    """
    code = _agent_code()
    assert 'CAPABILITY = "KeyboardDisplay"' in code, (
        "der Agent meldet sich nicht mit KeyboardDisplay an")
    for schwaecher in ("NoInputNoOutput", "DisplayOnly", "KeyboardOnly"):
        assert f'"{schwaecher}"' not in code, (
            f"{schwaecher} steht im Quelltext - eine schwaechere Faehigkeit "
            "schneidet Kopplungsverfahren weg")


def test_the_agent_also_asks_to_become_the_default_agent():
    """Ohne RequestDefaultAgent bleibt die halbe Luecke offen.

    org.bluez.AgentManager(5): ohne Vorgabe-Agenten bedient bluetoothd
    nur Kopplungen, die dieselbe Anwendung ANGESTOSSEN hat. Ein Geraet,
    das VON SICH AUS anklopft, faende dann niemanden - und genau das ist
    der Fall, in dem der Nutzer gar nichts tut und trotzdem etwas
    passiert.
    """
    assert "RequestDefaultAgent" in _agent_code(), (
        "der Agent bittet nicht darum, Vorgabe-Agent zu werden")


# --------------------------------------------------------------------
# 2. Alle sieben Rueckfragen, in der Form, die wirklich funktioniert
# --------------------------------------------------------------------

# Die sieben Rueckfragen an den Nutzer plus die zwei Verwaltungsaufrufe.
# Wortlaut aus org.bluez.Agent(5).
RUECKFRAGEN = (
    "RequestPinCode", "DisplayPinCode", "RequestPasskey", "DisplayPasskey",
    "RequestConfirmation", "RequestAuthorization", "AuthorizeService",
)
VERWALTUNG = ("Release", "Cancel")


def test_all_seven_questions_and_both_housekeeping_calls_are_answered():
    """Ein Agent, der nur eine davon kann, laesst den Nutzer beim
    naechsten Geraet wieder im Regen stehen.

    Eine fehlende Methode beantwortet bluetoothd mit UNKNOWN_METHOD, und
    die Kopplung laeuft in ihre Zeitgrenze - ohne dass irgendwo etwas
    stuende. Genau die Sorte Ausfall, die diese Datei bewacht.

    Geprueft wird BEIDES: dass die Methode in der angebotenen
    Schnittstelle steht (sonst ruft bluez sie nie) und dass es einen
    Rumpf dafuer gibt (sonst ruft es ins Leere).
    """
    code = _agent_code()
    fehlend = []
    for name in RUECKFRAGEN + VERWALTUNG:
        if f'<method name="{name}"' not in code:
            fehlend.append(f"{name} (nicht in der Schnittstelle)")
        if f"{name}Async(" not in code:
            fehlend.append(f"{name} (kein Rumpf)")
    assert fehlend == [], f"unbeantwortete Rueckfragen: {fehlend}"


def test_every_method_uses_the_async_form_that_was_measured_to_work():
    """Die Form ist gemessen, nicht abgeschrieben - und das ist hier
    keine Feinheit.

    GEMESSEN am 21.08.2026 an gjs 2:1.88.1-1 (die Fassung, von der
    aylurs-gtk-shell 3.1.2 abhaengt), gegen einen privaten Bus:

        Form                              zweites Argument
        --------------------------------  -------------------------
        Method(args…, x)                  NULL bzw. die UnixFDList
        MethodAsync(params, invocation)   die echte Invocation

    Der synchrone Pfad von gjs haengt die FD-Liste an, nicht die
    Invocation (Gio.js:371-390, `args.push(invocation.get_message().
    get_unix_fd_list())`). Ein `invocation.get_sender()` darin wirft bei
    JEDEM Aufruf `TypeError: invocation is null` - nachgestellt und
    reproduziert.

    Fuer diesen Agenten waere die synchrone Form nicht bloss unsauber,
    sondern falsch: er MUSS die Antwort zurueckhalten, bis der Mensch
    geklickt hat. Wer sofort zurueckkehrt, hat die Kopplung schon
    bestaetigt, bevor jemand die Zahl gelesen hat.
    """
    code = _agent_code()
    falsch = []
    for name in RUECKFRAGEN + VERWALTUNG:
        # Ein Methodenrumpf `Name(` OHNE das Async dahinter waere die
        # kaputte Form. Der Name kommt auch in der XML-Schnittstelle vor,
        # deshalb wird auf die Rumpfform geprueft: Name gefolgt von "(".
        if re.search(rf"(?<![\w])({name})\s*\(", code) \
                and f"{name}Async(" not in code:
            falsch.append(name)
    assert falsch == [], (
        "diese Methoden stehen in der synchronen Form da - auf gjs 1.88 "
        f"bekommen sie die Invocation nicht: {falsch}")


def test_a_refused_pairing_answers_with_the_error_name_bluez_expects():
    """Ablehnen ist eine ANTWORT, kein Schweigen.

    org.bluez.Agent(5) nennt org.bluez.Error.Rejected und
    org.bluez.Error.Canceled. Wer stattdessen gar nicht antwortet,
    laesst bluetoothd in seine Zeitgrenze laufen: die Kopplung haengt,
    und der Nutzer sieht ein Fenster, das nichts bewirkt hat.

    GEMESSEN am 21.08.2026, dass der Name wirklich ankommt:
    `invocation.return_dbus_error("org.bluez.Error.Rejected", …)` kommt
    beim Anrufer als genau dieser Fehler an.
    """
    code = _agent_code()
    assert "return_dbus_error(" in code, (
        "der Agent kann eine Kopplung gar nicht ablehnen")
    assert '"org.bluez.Error.Rejected"' in code, (
        "die Ablehnung traegt nicht den Namen, den org.bluez.Agent(5) nennt")


def test_no_way_out_of_the_window_leaves_bluez_waiting():
    """Das Fenster hat drei Ausgaenge, und alle drei muessen antworten.

    ESC, das Schliesskreuz im Kopf und ein `Cancel()` von der
    Gegenseite. createOverlayWindow() fuehrt die ersten beiden durch
    closeWindow(), und das ruft config.onHide - deshalb haengt die
    Ablehnung DORT und nicht an den Knoepfen. Ein Fenster, das zugeht,
    ohne zu antworten, ist der Ausfall dieser Datei in klein.
    """
    assert re.search(r"onHide:\s*\(\)\s*=>\s*ablehnen\(\)", _agent_code()), (
        "onHide beantwortet die offene Frage nicht - ESC und das "
        "Schliesskreuz liessen bluetoothd dann warten")


# --------------------------------------------------------------------
# 3. Die zwei Fallen aus der Messung
# --------------------------------------------------------------------

def test_a_repeated_display_passkey_updates_instead_of_opening_again():
    """FALLE 1, und sie steht so in org.bluez.Agent(5).

    "During the pairing process this method might be called multiple
    times to update the entered value" - der Parameter `entered` zaehlt
    die Tasten mit, die auf der Gegenstelle schon gedrueckt wurden, und
    bluetoothd ruft DisplayPasskey bei jeder Aenderung erneut.

    Wer daraufhin ein neues Fenster aufmacht, baut dem Nutzer beim
    Eintippen einer sechsstelligen Zahl bis zu sechs Fenster
    uebereinander - waehrend er auf die Tastatur sieht und es nicht
    merkt.
    """
    code = _agent_code()
    stelle = code.index("DisplayPasskeyAsync(")
    rumpf = code[stelle:stelle + 1600]
    assert "set_label(" in rumpf, (
        "DisplayPasskey aktualisiert die Zahl nicht - es oeffnet bei jeder "
        "Taste der Gegenstelle ein weiteres Fenster")
    assert "offen.geraet === pfad" in rumpf, (
        "DisplayPasskey erkennt nicht, dass dasselbe Geraet erneut fragt")


def test_the_two_display_calls_answer_at_once_and_do_not_wait_for_a_click():
    """FALLE 2: DisplayPasskey und DisplayPinCode sind ANZEIGEN, keine
    Fragen.

    Der Nutzer tippt die Zahl auf dem ANDEREN Geraet ein; hier gibt es
    nichts zu bestaetigen. Die leere D-Bus-Antwort muss sofort zurueck,
    und beendet wird die Anzeige von aussen ueber Cancel(). Wer hier auf
    einen Knopfdruck wartet, laesst bluetoothd in seine Zeitgrenze
    laufen - und die Kopplung scheitert, obwohl der Nutzer alles richtig
    gemacht hat.

    Woran man es im Quelltext abliest: die beiden bauen ihre Frage OHNE
    `beiZustimmung`, bekommen also gar keinen Bestaetigen-Knopf, und
    rufen return_value(null) unmittelbar.
    """
    code = _agent_code()
    for name in ("DisplayPasskeyAsync", "DisplayPinCodeAsync"):
        stelle = code.index(name + "(")
        rumpf = code[stelle:stelle + 1600]
        assert "invocation.return_value(null)" in rumpf, (
            f"{name} antwortet nicht sofort")
        assert "beiZustimmung" not in rumpf, (
            f"{name} baut einen Bestaetigen-Knopf - es ist aber eine "
            "Anzeige, auf die niemand antwortet")


def test_the_passkey_is_padded_to_six_digits():
    """org.bluez.Agent(5) sagt es zweimal ausdruecklich: "the passkey
    will always be a 6-digit number, so the display should be
    zero-padded at the start".

    Ohne die Nullen verglichen zwei Geraete verschiedene Zeichenfolgen -
    auf dem einen steht 001234, bei uns 1234 -, und der Nutzer lehnt
    eine Kopplung ab, die in Ordnung war. Genau die Sorte Fehler, die
    wie ein Angriff aussieht.
    """
    assert _agent_code().count('padStart(6, "0")') >= 2, (
        "der Zahlenschluessel wird nicht auf sechs Stellen aufgefuellt - "
        "RequestConfirmation und DisplayPasskey brauchen es beide")


# --------------------------------------------------------------------
# 4. Tastatur und Lage
# --------------------------------------------------------------------

def test_the_window_can_take_the_keyboard_and_never_locks_the_session():
    """Ohne Tastatur laesst sich ein Zahlenschluessel nicht eintippen -
    mit der falschen Einstellung ist die Sitzung weg.

    Das Fenster kommt aus createOverlayWindow() und erbt damit
    `Astal.Keymode.ON_DEMAND`: es nimmt den Fokus beim Aufgehen und gibt
    ihn beim Schliessen zurueck. Die beiden Gegenbeispiele sind in
    diesem Baum gemessen:

      NONE       nimmt die Tastatur NIE (ags-notifications.template,
                 ags-power-button.template). RequestPasskey waere damit
                 nicht bedienbar.
      EXCLUSIVE  SPERRT DIE SITZUNG AUS - zweimal gemessen, siehe den
                 Kopf von ags-home.template, Punkt 3: das Fenster
                 bekommt dann GAR KEINE Zeigerereignisse mehr.

    Diese Zusicherung haelt zweierlei fest: dass der Agent die Fabrik
    benutzt (und damit ON_DEMAND bekommt), und dass er sich NICHT selbst
    einen Tastenmodus setzt - denn dann waere die Wahl wieder offen.
    """
    code = _agent_code()
    assert "createOverlayWindow({" in code, (
        "der Agent baut sein Fenster nicht mit der Fabrik - dann haengt "
        "der Tastenmodus an einer eigenen Zeile")
    assert "keymode" not in code, (
        "der Agent setzt einen eigenen Tastenmodus, statt ON_DEMAND aus "
        "der Fabrik zu erben")

    fabrik = _ohne_kommentare(
        (SRC / "templates" / "ags-overlay-utils.template").read_text(
            encoding="utf-8"))
    assert "keymode: Astal.Keymode.ON_DEMAND" in fabrik, (
        "die Fabrik gibt nicht mehr ON_DEMAND - der Agent bekaeme dann "
        "einen anderen Tastenmodus, ohne dass hier etwas faellt")


def test_a_stray_return_key_cannot_confirm_a_pairing():
    """Die Bestaetigung darf nicht aus Reflex passieren.

    Dieselbe Regel wie in ags-logout.template ("der harmloseste der
    sechs Knoepfe bekommt den Fokus, damit eine zufaellige Eingabetaste
    nicht auf einem 'kritisch'-Knopf landet") - hier ist sie
    sicherheitsrelevant: das Fenster geht UNGEFRAGT auf, waehrend der
    Nutzer etwas anderes tut. Landet der Fokus auf "Bestaetigen", koppelt
    ein Tastendruck, der einem anderen Fenster galt.

    Gibt es ein Eingabefeld, bekommt DAS den Fokus - sonst koennte man
    den Zahlenschluessel nicht eintippen, ohne vorher zu klicken.
    """
    code = _agent_code()
    assert "onShow: () => zuFokussieren?.grab_focus()" in code, (
        "beim Aufgehen bekommt nichts den Fokus")
    assert "zuFokussieren = feld" in code, (
        "ein vorhandenes Eingabefeld bekommt den Fokus nicht")
    assert "if (!zuFokussieren) zuFokussieren = ablehnenBtn" in code, (
        "ohne Eingabefeld faellt der Fokus nicht auf ABLEHNEN")


def test_the_surface_is_named_in_exactly_one_of_the_three_glass_lists(
        monkeypatch, tmp_path):
    """Jede Flaeche dieses Baums steht in genau einer der drei Listen.

    Die Vollzaehligkeit selbst prueft tests/src/test_glass.py fuer ALLE
    Flaechen. Hier steht die Zeile, die sagt, WELCHE der drei es fuer
    diese Flaeche sein muss und warum: Glas.

    Sie malt einen Grund, den man messen kann - anders als das Home, das
    einzige Mitglied von PLAIN_LAYERS. Eine Kopplungsfrage ohne Platte
    laege als Schrift auf der Tapete, und zwar genau in dem Moment, in
    dem jemand eine sechsstellige Zahl vergleichen soll.
    """
    test_sizes._no_compositor(monkeypatch)
    style = test_sizes._import_style(tmp_path, monkeypatch)

    assert NAMESPACE in style.GLASS_LAYERS, (
        f"{NAMESPACE} steht nicht in GLASS_LAYERS")
    assert NAMESPACE not in style.PLAIN_LAYERS, (
        f"{NAMESPACE} steht in PLAIN_LAYERS - es malt aber einen Grund")
    assert NAMESPACE in style.GLASS_PLATES, (
        f"fuer {NAMESPACE} ist keine Platte aufgeschrieben")


# --------------------------------------------------------------------
# 5. Der Vorgaenger ist WEG, nicht bloss ueberholt
# --------------------------------------------------------------------

def test_the_session_no_longer_starts_a_second_agent_process():
    """Regel 14: geloescht, nicht als veraltet markiert.

    Stufe 1 startete blueman-applet beim Anmelden. Bliebe die Zeile
    neben dem eigenen Agenten stehen, waeren ZWEI Agenten am selben
    Adapter - und welcher gefragt wird, entschiede, wer zuerst
    Vorgabe-Agent geworden ist. Der Nutzer saehe mal ein GTK3-Fenster,
    mal unseres.

    Zeilengenau und ohne Kommentare: die Vorlage ERKLAERT an der Stelle
    ausdruecklich, was dort stand.
    """
    zeilen = _uncommented_lines(UNIVERSAL.read_text(encoding="utf-8"))
    startend = [z for z in zeilen if z.startswith(("exec-once", "exec "))]
    treffer = [z for z in startend if "blueman" in z]
    assert treffer == [], f"die Sitzung startet weiterhin blueman: {treffer}"

    regeln = [z for z in zeilen
              if z.startswith("windowrule") and "blueman" in z]
    assert regeln == [], (
        "es stehen noch Fensterregeln fuer blueman da - der eigene Agent "
        f"ist eine Layer-Flaeche, auf die keine greift: {regeln}")


def test_the_package_stays_because_it_is_the_only_way_to_send_a_file():
    """Die Gegenrichtung, und sie ist gemessen.

    `grep` nach obex/sendto ueber src/ und packaging/ am 21.08.2026:
    ausser blueman gibt es in diesem Baum KEINEN Weg, eine Datei ueber
    Bluetooth zu schicken. Der Knopf in ags-bluetooth.template fuehrt
    weiter dorthin.

    Nur der AGENT ist unserer geworden. Das Paket mit zu entfernen waere
    kein Aufraeumen, sondern der stille Verlust einer Funktion - genau
    die Sorte Schaden, vor der Regel 14 NICHT schuetzt, weil hier nichts
    tot ist.
    """
    zeilen = _uncommented_lines(
        (PACKAGING / "zepos-desktop" / "PKGBUILD").read_text(encoding="utf-8"))
    assert "'blueman'" in zeilen, (
        "blueman ist keine Abhaengigkeit mehr - damit faellt die "
        "Bluetooth-Dateiuebertragung ersatzlos weg")


# --------------------------------------------------------------------
# 6. Und es kommt wirklich an
# --------------------------------------------------------------------

def test_the_generator_and_the_shell_both_know_the_new_window(tree):
    """Eine Vorlage, die niemand erzeugt und niemand einhaengt, ist eine
    Datei im Baum und kein Fenster auf dem Schirm.

    Drei Enden muessen zusammenpassen, und jedes einzelne ist schon
    einmal das fehlende gewesen: die Route im Generator, der Import in
    app.ts und der Aufruf darin. Geprueft wird zusaetzlich am ERZEUGTEN
    Baum, nicht nur an den Vorlagen - der Unterschied ist der ganze
    Zweck.
    """
    generator = "\n".join(_uncommented_lines(
        GENERATOR.read_text(encoding="utf-8")))
    assert "ags-bluetooth-agent)" in generator, (
        "der Generator kennt keine Route fuer den Agenten")
    assert 'CONFIG_FILE="BluetoothAgent.tsx"' in generator, (
        "die Route schreibt nicht BluetoothAgent.tsx")

    app = _ohne_kommentare(APP.read_text(encoding="utf-8"))
    assert 'from "./widget/BluetoothAgent"' in app, (
        "app.ts importiert den Agenten nicht")
    assert "BluetoothAgent()" in app, (
        "app.ts ruft den Agenten nicht auf - er wuerde nie angemeldet")

    erzeugt = tree.config / "ags" / "widget" / "BluetoothAgent.tsx"
    assert erzeugt.is_file(), f"{erzeugt} wurde nicht erzeugt"
    code = _ohne_kommentare(erzeugt.read_text(encoding="utf-8"))
    assert "org.bluez.Agent1" in code, (
        "die erzeugte Datei bietet die Agentenschnittstelle nicht an")
    assert "{{" not in code, (
        "in der erzeugten Datei stehen noch Platzhalter")
    assert f'"{NAMESPACE}"' in code, (
        "die erzeugte Datei meldet den Namensraum nicht an, auf den die "
        "Glasregeln zeigen")
