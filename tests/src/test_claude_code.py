# SPDX-License-Identifier: GPL-3.0-or-later
"""zepos-claude-code - der Befehl, der Eintrag und das Zeichen.

WAS AM 01.09.2026 GEFALLEN IST, UND WARUM DIESE DATEI NEU IST

    Bis dahin hiess sie tests/packaging/test_claude_code.py und prueft
    ein PAKET: packaging/zepos-claude-code/PKGBUILD baute Anthropics
    Programm aus einem npm-Archiv in ein signiertes ZepOS-Paket. Es gibt
    kein solches Paket mehr, also gibt es auch nichts mehr davon zu
    pruefen - die Haelfte jener Datei, die `options=('!strip')`,
    `sha512sums` und den Fundort der Binaerdatei im Tarball beschrieb,
    ist mit dem Rezept gegangen.

    DER NUTZER am 01.09.2026: "ich will claude nicht mit liefern bei
    zepos es muss per bash command dazu installiert werden sodass es
    ausfuehrbar ist aber ich will das packet nicht als meins verkaufen
    [...] weil jetzt bekommt es keine updates."

    Was blieb, ist ZepOS' eigene Arbeit, und die steht jetzt in src/:
    der Befehl src/bin/zepos-claude-code, der Eintrag
    src/system/zepos-claude-code.desktop und die vier Zeichen unter
    src/system/claude-code-icons/. Deshalb liegt diese Datei unter
    tests/src/.

WAS HIER GELESEN UND WAS AUSGEFUEHRT WIRD

    Der EINTRAG und das Rezept werden gelesen - eine .desktop-Datei ist
    ein Text, und ein Paketbau braucht Docker und root
    (tests/packaging/test_recipes.py begruendet das in seinem Kopf).

    DER BEFEHL WIRD AUSGEFUEHRT, und zwar in jeder seiner Fehlerlagen.
    Das ist die Bedingung dieser Aufgabe gewesen: ein Test, der nur den
    Quelltext durchsucht, misst nichts. Jeder Lauf unten bekommt ein
    VORGETAEUSCHTES npm auf einem eigenen PATH und ein eigenes HOME -
    `npm i -g` wird an keiner Stelle dieser Datei wirklich ausgefuehrt,
    und die Umgebung des Entwicklers bleibt unberuehrt.
"""
import os
import pty
import re
import select
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
SRC = REPOSITORY / "src"
BEFEHL = SRC / "bin" / "zepos-claude-code"
EINTRAG = SRC / "system" / "zepos-claude-code.desktop"
ZEICHEN = SRC / "system" / "claude-code-icons"
REZEPT = REPOSITORY / "packaging" / "zepos-config" / "PKGBUILD"

# Die Groessen, die der Starter und das Dock anfordern.
GROESSEN = (48, 64, 128, 256)


def _feld(text: str, name: str) -> str:
    treffer = re.search(rf"^{name}=(.*)$", text, re.M)
    assert treffer, f"{name}= fehlt in {EINTRAG.name}"
    return treffer.group(1).strip()


# --------------------------------------------------------------------
# Das vorgetaeuschte npm
# --------------------------------------------------------------------
# EIN SKRIPT UND KEIN MOCK-OBJEKT, weil der Pruefling eine Schale ist:
# er ruft `command -v npm`, `npm ping` und `npm install -g`, und was er
# daraus macht, haengt an Rueckgabewerten. Ein Objekt haette die eine
# Schnittstelle nachgebaut, die hier gerade nicht gemessen werden soll.
#
# Jeder Lauf schreibt seine Aufrufe mit. Damit misst der Test nicht nur,
# WAS der Befehl sagt, sondern auch, ob er `npm install` ueberhaupt
# angefasst hat - der Unterschied zwischen "hat abgelehnt" und "hat es
# versucht und dann abgelehnt" ist genau der, um den es geht.
def _claude_attrappe(fassung: str) -> str:
    """Ein `claude`, das seine Fassung nennt und sonst nur meldet, dass
    es lief. Zwei Fassungen kommen vor und der Unterschied ist der
    Punkt: 2.1.233 ist die, die das gefallene Paket eingefroren hatte,
    2.1.257 die, die npm am 01.09.2026 auslieferte."""
    return (
        "#!/bin/bash\n"
        'if [ "$1" = "--version" ]; then\n'
        f'    echo "{fassung} (Claude Code)"\n'
        "    exit 0\n"
        "fi\n"
        'echo "claude lief mit: $*"\n'
        "exit ${CLAUDE_RC:-0}\n"
    )


# Die Fassung, die das gefallene Paket festnagelte.
CLAUDE_ATTRAPPE = _claude_attrappe("2.1.233")

# Und die, die npm liefert. Ein npm-Lauf legt genau sie ab - so misst
# der Test, dass der Weg ueber npm wirklich eine NEUERE Fassung bringt
# und nicht dieselbe unter anderem Namen.
NPM_ATTRAPPE = "#!/bin/bash\n" + f"""\
echo "$@" >> "$NPM_PROTOKOLL"
case "$1" in
    ping)
        exit ${{NPM_PING_RC:-0}} ;;
    prefix)
        echo "$HOME/.local"; exit 0 ;;
    install)
        if [ "${{NPM_INSTALL_RC:-0}}" -ne 0 ]; then
            echo "npm error code E${{NPM_INSTALL_RC:-0}}" >&2
            exit "${{NPM_INSTALL_RC}}"
        fi
        # Was ein echtes `npm i -g` hinterlaesst: das Programm unter
        # dem Praefix. Genau das sucht der Pruefling danach - es sei
        # denn NPM_LEGT_NICHTS_AB steht, dann meldet npm Erfolg und legt
        # nichts hin (der Fall einer eigenen ~/.npmrc mit anderem Ziel).
        if [ -z "${{NPM_LEGT_NICHTS_AB:-}}" ]; then
            mkdir -p "$HOME/.local/bin"
            cat > "$HOME/.local/bin/claude" <<'CLAUDE'
{_claude_attrappe("2.1.257")}\
CLAUDE
            chmod 0755 "$HOME/.local/bin/claude"
        fi
        exit 0 ;;
esac
exit 0
"""


# Die Werkzeuge, die der Pruefling wirklich braucht - und NUR sie.
#
# WARUM NICHT EINFACH /usr/bin AN DEN PATH
#     Weil auf DIESER Maschine ein echtes npm liegt. Ein Test, der
#     "kein npm" messen will und /usr/bin im PATH hat, misst statt
#     dessen den Rechner des Entwicklers - und er faellt genau dann um,
#     wenn jemand npm deinstalliert, also nie dort, wo er etwas sagt.
#     Gemessen: mit /usr/bin im PATH bestand
#     test_ohne_npm_... nicht, weil `command -v npm` /usr/bin/npm fand.
#
#     Dieselbe Ueberlegung wie bei den Sitzungen in test_login.py, die
#     unter `env -i` mit einem Stub-Verzeichnis als GANZEM PATH laufen.
WERKZEUGE = ("id", "timeout", "mkdir", "chmod", "head", "cat", "setsid",
             "sleep", "env", "bash", "sh")


@pytest.fixture
def welt(tmp_path):
    """Eine Maschine, auf der nichts liegt, was der Entwickler besitzt.

    Der PATH besteht aus zwei Verzeichnissen, die dieser Test selbst
    baut: den Attrappen und einer Handvoll Verweise auf die Werkzeuge
    oben. Was nicht in WERKZEUGE steht, gibt es fuer den Pruefling
    nicht - npm und claude also genau dann, wenn ein Test sie hinlegt.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    system = tmp_path / "system"
    system.mkdir()
    # Ein winziger Vorschalter statt eines Verweises: tests/conftest.py
    # verbietet jeden Verweis, der aus dem Zeitverzeichnis herauszeigt
    # ("This test tried to create a link on '/usr/bin/id'"), und die
    # Regel ist richtig - sie faengt Tests, die am laufenden System
    # drehen. Eine Datei, die ein Werkzeug AUFRUFT, dreht an nichts.
    for werkzeug in WERKZEUGE:
        gefunden = shutil.which(werkzeug)
        if not gefunden:
            continue
        vorschalter = system / werkzeug
        vorschalter.write_text(
            f'#!/bin/bash\nexec "{gefunden}" "$@"\n', encoding="utf-8")
        vorschalter.chmod(0o755)
    heim = tmp_path / "heim"
    (heim / ".local" / "bin").mkdir(parents=True)
    protokoll = tmp_path / "npm-aufrufe.txt"
    protokoll.write_text("", encoding="utf-8")

    class Welt:
        def __init__(self):
            self.stubs = stubs
            self.system = system
            self.heim = heim
            self.protokoll = protokoll

        def lege(self, name: str, inhalt: str) -> Path:
            ziel = self.stubs / name
            ziel.write_text(inhalt, encoding="utf-8")
            ziel.chmod(0o755)
            return ziel

        def mit_npm(self):
            self.lege("npm", NPM_ATTRAPPE)
            return self

        def mit_claude(self):
            self.lege("claude", CLAUDE_ATTRAPPE)
            return self

        def umgebung(self, **extra) -> dict:
            umwelt = {
                # ~/.local/bin GANZ VORNE, wie auf einem echten ZepOS:
                # /etc/npmrc setzt npms Praefix auf ${HOME}/.local, npm
                # legt unter einem Praefix X nach X/bin ab, und
                # src/templates/zshrc-config.template setzt genau dieses
                # Verzeichnis an den Anfang des PATH. Ohne diese Zeile
                # misst der Test einen Rechner, auf dem `npm i -g`
                # nichts erreichbar macht - und das ist eine andere Lage
                # (nachher_pruefen() faengt sie ab, und ein eigener Test
                # oben misst SIE).
                "PATH": f"{self.heim}/.local/bin:{self.stubs}:{self.system}",
                "HOME": str(self.heim),
                "XDG_STATE_HOME": str(self.heim / ".local" / "state"),
                "NPM_PROTOKOLL": str(self.protokoll),
                "LC_ALL": "C.UTF-8",
            }
            umwelt.update({k: str(v) for k, v in extra.items()})
            return umwelt

        def aufrufe(self) -> list[str]:
            return [zeile for zeile
                    in self.protokoll.read_text(encoding="utf-8").splitlines()
                    if zeile.strip()]

    return Welt()


def _lauf(welt, *argumente, eingabe: str = "", **extra):
    """Der Pruefling, ohne Terminal, mit vorgegebener Eingabe."""
    return subprocess.run(
        [str(BEFEHL), *argumente],
        env=welt.umgebung(**extra),
        input=eingabe,
        capture_output=True, text=True, timeout=60)


def _lauf_am_terminal(welt, *argumente, tippen: bytes = b"",
                      frist: float = 20.0, **extra):
    """Derselbe Lauf, aber an einem echten Pseudoterminal.

    Ob ein Fenster offen BLEIBT und ob eine Frage ueberhaupt gestellt
    wird, haengt an `[ -t 0 ]`. Ein subprocess.PIPE ist kein Terminal,
    also beantwortet er beide Fragen mit "nein" - und zwar unabhaengig
    davon, ob der Pruefling richtig liegt. Nur ein pty misst das.
    """
    haupt, neben = pty.openpty()
    prozess = subprocess.Popen(
        [str(BEFEHL), *argumente],
        env=welt.umgebung(**extra),
        stdin=neben, stdout=neben, stderr=neben,
        start_new_session=True)
    os.close(neben)

    gelesen = b""
    getippt = False
    ende = time.monotonic() + frist
    while time.monotonic() < ende:
        bereit, _, _ = select.select([haupt], [], [], 0.2)
        if bereit:
            try:
                stueck = os.read(haupt, 4096)
            except OSError:
                break
            if not stueck:
                break
            gelesen += stueck
        if tippen and not getippt and prozess.poll() is None and gelesen:
            os.write(haupt, tippen)
            getippt = True
        if prozess.poll() is not None and not bereit:
            break

    if prozess.poll() is None:
        prozess.kill()
    prozess.wait(timeout=10)
    os.close(haupt)
    return prozess.returncode, gelesen.decode("utf-8", "replace")


# --------------------------------------------------------------------
# 1. Die drei Lagen, und jede bekommt ihren eigenen Satz
# --------------------------------------------------------------------
# DIE REGEL steht in src/templates/ags-control-center.template bei der
# Geraeteliste: "die ersten beiden kann der Nutzer beheben, der dritte
# ist ein kaputter Lauf. Eine gemeinsame Meldung schickte ihn in die
# falsche Richtung."
#
# Hier sind es kein npm, kein Netz und schon installiert. Sie GEMESSEN
# auseinanderzuhalten und nicht nur im Quelltext auseinanderzuschreiben
# ist der Grund, aus dem diese drei Tests den Befehl ausfuehren.

@pytest.mark.allow_subprocess
def test_ohne_npm_nennt_der_befehl_npm_und_holt_nichts(welt):
    """Lage 1: keine JavaScript-Laufzeit auf der Maschine."""
    ergebnis = _lauf(welt, "install")

    assert ergebnis.returncode == 3, (
        f"ohne npm ist der Rueckgabewert {ergebnis.returncode}, nicht 3 - "
        "und ein eigener Wert ist der halbe Unterschied zwischen den "
        f"Lagen.\n{ergebnis.stdout}{ergebnis.stderr}")
    assert "npm" in ergebnis.stderr, (
        "die Meldung nennt npm nicht - dann weiss der Nutzer nicht, was "
        f"fehlt:\n{ergebnis.stderr}")
    assert "nodejs-lts-krypton" in ergebnis.stderr, (
        "die Meldung sagt nicht, WIE man npm bekommt. Genau das ist der "
        "Unterschied zwischen einer Klage und einem Weg:\n"
        f"{ergebnis.stderr}")
    assert welt.aufrufe() == [], (
        f"ohne npm wurde npm trotzdem aufgerufen: {welt.aufrufe()}")


@pytest.mark.allow_subprocess
def test_ohne_netz_nennt_der_befehl_das_netz_und_installiert_nicht(welt):
    """Lage 2: npm ist da, die Registry nicht.

    `npm ping` liefert hier 1, wie es das ohne Leitung tut. Gemessen
    wird, dass der Befehl DANACH aufhoert - ein `npm install`, das erst
    nach zwei Minuten Zeitablauf scheitert, waere dieselbe Antwort, nur
    zwei Minuten spaeter und mit einer Fehlermeldung von npm statt einer
    von ZepOS.
    """
    welt.mit_npm()
    ergebnis = _lauf(welt, "install", NPM_PING_RC=1)

    assert ergebnis.returncode == 4, (
        f"ohne Netz ist der Rueckgabewert {ergebnis.returncode}, nicht 4 - "
        "er waere damit nicht von 'kein npm' zu unterscheiden.\n"
        f"{ergebnis.stdout}{ergebnis.stderr}")
    assert "Registry" in ergebnis.stderr or "Netz" in ergebnis.stderr, (
        f"die Meldung nennt weder Registry noch Netz:\n{ergebnis.stderr}")
    assert ["ping"] == welt.aufrufe(), (
        "nach einem gescheiterten ping wurde weitergemacht: "
        f"{welt.aufrufe()}")


@pytest.mark.allow_subprocess
def test_schon_installiert_ist_kein_fehlschlag_sondern_ein_hinweis(welt):
    """Lage 3: alles da.

    UND SIE IST DIE, DIE AM LEICHTESTEN FALSCH WIRD. "Schon da" ist
    keine Stoerung: der Rueckgabewert ist 0, es wird nichts geladen, und
    die einzige sinnvolle Auskunft ist, wie man an eine NEUERE Fassung
    kommt. Genau das war der zweite Grund des Nutzers, das Paket fallen
    zu lassen.
    """
    welt.mit_npm().mit_claude()
    ergebnis = _lauf(welt, "install")

    assert ergebnis.returncode == 0, (
        "eine schon installierte Fassung ist ein Fehlschlag geworden: "
        f"{ergebnis.returncode}\n{ergebnis.stdout}{ergebnis.stderr}")
    assert "2.1.233" in ergebnis.stdout, (
        "der Befehl sagt nicht, WELCHE Fassung schon liegt:\n"
        f"{ergebnis.stdout}")
    assert "zepos-claude-code update" in ergebnis.stdout, (
        "der Weg zur neueren Fassung fehlt - und die fehlenden "
        "Aktualisierungen waren der Grund, aus dem das Paket gefallen "
        f"ist:\n{ergebnis.stdout}")
    assert "install" not in " ".join(welt.aufrufe()), (
        f"es wurde trotzdem installiert: {welt.aufrufe()}")


@pytest.mark.allow_subprocess
def test_als_root_wird_nicht_installiert(welt):
    """Die vierte Lage, und sie ist zugleich die Begruendung dafuer,
    warum der INSTALLER das nicht tun kann.

    /etc/npmrc setzt prefix=${HOME}/.local. Als root ist ${HOME} /root -
    das Programm laege unter /root/.local/bin/claude und waere fuer das
    Konto des Nutzers weder im PATH noch lesbar. Ein Lauf, der durchgeht
    und nichts erreichbar macht, ist schlimmer als einer, der abbricht.

    Gemessen ohne root-Rechte: der Pruefling fragt `id -u`, und ein `id`
    auf dem Attrappen-PATH beantwortet die Frage mit 0. Damit misst
    dieser Test genau den Zweig, den er messen will, und diese Testsuite
    laeuft weiterhin als gewoehnlicher Nutzer.
    """
    welt.mit_npm()
    welt.lege("id", "#!/bin/bash\necho 0\n")
    ergebnis = _lauf(welt, "install")

    assert ergebnis.returncode == 5, (
        f"als root ist der Rueckgabewert {ergebnis.returncode}, nicht 5\n"
        f"{ergebnis.stdout}{ergebnis.stderr}")
    assert "root" in ergebnis.stderr, (
        f"die Meldung nennt root nicht:\n{ergebnis.stderr}")
    assert welt.aufrufe() == [], (
        f"als root wurde npm trotzdem aufgerufen: {welt.aufrufe()}")


# --------------------------------------------------------------------
# 2. Der Weg hin - und er wird wirklich gegangen
# --------------------------------------------------------------------

@pytest.mark.allow_subprocess
def test_install_ruft_npm_mit_dem_nachlader_und_nicht_mit_der_binaerdatei(welt):
    """@anthropic-ai/claude-code und NICHT ...-linux-x64.

    Das alte Rezept holte die Binaerdatei direkt, weil ein Paketbau
    reproduzierbar sein muss - eine feste Fassung, eine Pruefsumme. `npm
    i -g` hat diese Pflicht nicht und darf tun, wofuer es da ist: den
    Nachlader holen, die Plattform messen und die passende Binaerdatei
    selbst dazulegen. Der Name mit -linux-x64 waere hier ein Paket ohne
    den Aufruf `claude` und damit ein Lauf, der meldet, er sei fertig.
    """
    welt.mit_npm()
    ergebnis = _lauf(welt, "install")

    assert ergebnis.returncode == 0, (
        f"{ergebnis.stdout}{ergebnis.stderr}")
    aufrufe = welt.aufrufe()
    assert any(zeile.startswith("install -g @anthropic-ai/claude-code")
               and "linux-x64" not in zeile for zeile in aufrufe), (
        f"npm wurde nicht mit dem Nachlader gerufen: {aufrufe}")


@pytest.mark.allow_subprocess
def test_nach_dem_lauf_wird_geprueft_ob_claude_wirklich_erreichbar_ist(welt):
    """npm meldet 0 - und das ist noch keine Zusicherung.

    Eine eigene ~/.npmrc gewinnt gegen /etc/npmrc (ausdruecklich so
    gewollt, siehe src/system/npmrc). Zeigt sie woandershin, laeuft npm
    durch, und `claude` liegt trotzdem nicht im PATH. Der Nutzer soll
    das ERFAHREN und nicht raten, warum die Schale "command not found"
    sagt.
    """
    welt.mit_npm()
    ergebnis = _lauf(welt, "install", NPM_LEGT_NICHTS_AB="1")

    assert ergebnis.returncode != 0, (
        "npm hat nichts abgelegt und der Befehl meldet trotzdem Erfolg:\n"
        f"{ergebnis.stdout}{ergebnis.stderr}")
    assert "PATH" in ergebnis.stderr, (
        f"die Meldung sagt nicht, woran es liegt:\n{ergebnis.stderr}")


@pytest.mark.allow_subprocess
def test_ein_gescheitertes_npm_gibt_seinen_eigenen_wert_zurueck(welt):
    """Die Ausgabe von npm wird nicht verschluckt und nicht uebersetzt.

    Im Fehlerfall steht die Ursache in npms eigener Meldung und in
    keiner Zusammenfassung, die dieses Skript daraus machen koennte.
    """
    welt.mit_npm()
    ergebnis = _lauf(welt, "install", NPM_INSTALL_RC=7)

    assert ergebnis.returncode == 7, (
        f"npms Rueckgabewert ist unterwegs verlorengegangen: "
        f"{ergebnis.returncode}")
    assert "npm error" in ergebnis.stderr, (
        f"npms eigene Meldung fehlt:\n{ergebnis.stderr}")


# --------------------------------------------------------------------
# 3. Der Weg weiter - der Grund, aus dem das Paket gefallen ist
# --------------------------------------------------------------------
# GEMELDET am 01.09.2026: "weil jetzt bekommt es keine updates". Ein
# Weg, den es zwar gibt, den aber niemand FINDET, haette den Grund nicht
# behoben, sondern nur verschoben.

@pytest.mark.allow_subprocess
def test_update_holt_die_neueste_fassung(welt):
    welt.mit_npm().mit_claude()
    ergebnis = _lauf(welt, "update")

    assert ergebnis.returncode == 0, (
        f"{ergebnis.stdout}{ergebnis.stderr}")
    assert any(zeile.startswith("install -g @anthropic-ai/claude-code")
               for zeile in welt.aufrufe()), (
        f"update hat npm nicht gerufen: {welt.aufrufe()}")
    assert "2.1.233" in ergebnis.stdout, (
        "update sagt nicht, was vorher lag - dann sieht niemand, dass "
        f"sich etwas bewegt hat:\n{ergebnis.stdout}")


@pytest.mark.allow_subprocess
def test_update_ohne_installation_schickt_zu_install(welt):
    """Und NICHT dieselbe Meldung wie ein Fehlschlag: hier ist nichts
    kaputt, es ist nur nichts da."""
    welt.mit_npm()
    ergebnis = _lauf(welt, "update")

    assert ergebnis.returncode == 6, (
        f"eigener Rueckgabewert fehlt: {ergebnis.returncode}")
    assert "zepos-claude-code install" in ergebnis.stderr, (
        f"der Weg dorthin fehlt:\n{ergebnis.stderr}")
    assert "install" not in " ".join(welt.aufrufe()), (
        f"es wurde trotzdem installiert: {welt.aufrufe()}")


@pytest.mark.allow_subprocess
def test_die_hilfe_nennt_update_beim_namen(welt):
    """Wer den Weg zur neuen Fassung nicht FINDET, hat ihn nicht."""
    ergebnis = _lauf(welt, "--help")

    assert ergebnis.returncode == 0
    assert "update" in ergebnis.stdout, (
        f"--help kennt update nicht:\n{ergebnis.stdout}")
    assert "npm i -g @anthropic-ai/claude-code" in ergebnis.stdout, (
        "die Hilfe verschweigt, was der Befehl eigentlich tut - und "
        "genau diese Offenheit ist der Punkt, an dem ZepOS aufhoert, so "
        f"zu tun, als sei das sein Programm:\n{ergebnis.stdout}")
    assert "NICHT mit" in ergebnis.stdout, (
        "die Hilfe sagt nicht, dass ZepOS Claude Code nicht ausliefert:\n"
        f"{ergebnis.stdout}")


@pytest.mark.allow_subprocess
def test_status_beantwortet_die_frage_in_beide_richtungen(welt):
    welt.mit_npm()
    ohne = _lauf(welt, "status")
    assert ohne.returncode == 1
    assert "nicht installiert" in ohne.stdout

    welt.mit_claude()
    mit = _lauf(welt, "status")
    assert mit.returncode == 0
    assert "2.1.233" in mit.stdout


# --------------------------------------------------------------------
# 4. Der Eintrag im Starter ist keine Sackgasse mehr
# --------------------------------------------------------------------
# HIER STAND, BIS ZUM 01.09.2026, DER TEST FUER DIE SACKGASSE:
#
#     "ZepOS: 'claude' ist auf dieser Maschine nicht installiert.
#      Das Paket dazu heisst zepos-claude-code."
#
# Das war richtig, solange es das Paket gab. Es gibt keines mehr, und
# ein Eintrag im Starter, der auf ein fehlendes Programm zeigt und dazu
# einen Paketnamen nennt, den es nicht gibt, waere Spec 7.4 - ein Knopf,
# der nichts oeffnet. Gemessen wird jetzt die Gegenrichtung.

@pytest.mark.allow_subprocess
def test_der_starter_fragt_am_terminal_und_installiert_nach(welt):
    """Ein Klick im Dock auf einer frischen Maschine.

    Am pty, weil die Frage an `[ -t 0 ]` haengt. Getippt wird eine
    Eingabetaste - die Vorgabe ist Ja.
    """
    welt.mit_npm()
    code, ausgabe = _lauf_am_terminal(welt, tippen=b"\n")

    assert "noch nicht installiert" in ausgabe, (
        f"der Starter sagt nicht, was los ist:\n{ausgabe}")
    assert "[J/n]" in ausgabe, (
        "es wird nicht gefragt - 50 MB gehen ueber die Leitung des "
        f"Nutzers und nicht ueber unsere:\n{ausgabe}")
    assert any(zeile.startswith("install -g @anthropic-ai/claude-code")
               for zeile in welt.aufrufe()), (
        f"nach dem Ja wurde nicht installiert: {welt.aufrufe()}\n{ausgabe}")
    assert "claude lief mit" in ausgabe, (
        "nach der Installation wurde Claude Code nicht gestartet - der "
        f"Klick war fuer nichts:\n{ausgabe}")


@pytest.mark.allow_subprocess
def test_ein_nein_laedt_nichts_und_aendert_nichts(welt):
    welt.mit_npm()
    code, ausgabe = _lauf_am_terminal(welt, tippen=b"n\n")

    assert welt.aufrufe() == [], (
        f"trotz Nein wurde npm gerufen: {welt.aufrufe()}\n{ausgabe}")
    assert "Abgebrochen" in ausgabe, (
        f"das Nein wird nicht bestaetigt:\n{ausgabe}")
    assert "zepos-claude-code install" in ausgabe, (
        f"der Weg fuer spaeter fehlt:\n{ausgabe}")
    assert code == 0, f"ein Nein ist kein Fehlschlag: {code}\n{ausgabe}"


@pytest.mark.allow_subprocess
def test_ohne_terminal_wird_nicht_gefragt_und_nicht_geladen(welt):
    """Ein Skript, das aus einem anderen Skript heraus laeuft, hat
    niemanden, der antwortet. `read` kaeme sofort leer zurueck, und aus
    einer Frage wuerde ein stillschweigendes Ja auf einen
    50-MB-Ladevorgang."""
    welt.mit_npm()
    ergebnis = _lauf(welt)

    assert welt.aufrufe() == [], (
        f"ohne Terminal wurde geladen: {welt.aufrufe()}")
    assert "zepos-claude-code install" in ergebnis.stderr, (
        f"der ausdrueckliche Weg fehlt:\n{ergebnis.stderr}")


@pytest.mark.allow_subprocess
def test_das_fenster_bleibt_offen_wenn_claude_scheitert(welt):
    """Die Messung vom 17.08.2026, unveraendert: `kitty -e claude`
    bindet das Fenster an das Programm, und ein Fehlschlag ist eine
    Zeile, die mit dem Fenster verschwindet."""
    welt.mit_npm().mit_claude()
    code, ausgabe = _lauf_am_terminal(welt, tippen=b"\n", CLAUDE_RC=1)

    assert "Eingabetaste" in ausgabe, (
        "nach einem Fehlschlag geht das Fenster sofort zu - genau der "
        f"Fehler vom 17.08.2026:\n{ausgabe}")
    assert code == 1, f"der Rueckgabewert ist unterwegs verlorengegangen: {code}"


@pytest.mark.allow_subprocess
def test_ein_gewolltes_ende_haelt_das_fenster_nicht_auf(welt):
    """--hold waere die falsche Antwort: es haelt IMMER offen, also auch
    nach einem gewollten Beenden."""
    welt.mit_npm().mit_claude()
    code, ausgabe = _lauf_am_terminal(welt, CLAUDE_RC=0)

    assert "Eingabetaste" not in ausgabe, (
        f"das Fenster wartet nach einem sauberen Ende:\n{ausgabe}")
    assert code == 0


# --------------------------------------------------------------------
# 5. Die erste Anmeldung - "bei der Installation mit installiert"
# --------------------------------------------------------------------
# GEMELDET am 01.09.2026: "es soll bei installation mit installiert
# werden genauso wie ruflo aber als bash command install script".
#
# WARUM NICHT IM INSTALLER: die drei Messungen stehen im Kopf von
# befehl_erstanmeldung() in src/bin/zepos-claude-code. Kurz: die
# Zusatzbefehle des Installers laufen als root im Chroot, /etc/npmrc
# setzt prefix=${HOME}/.local, und ${HOME} ist dort /root.

@pytest.mark.allow_subprocess
def test_die_erstanmeldung_schweigt_wenn_claude_schon_da_ist(welt):
    welt.mit_npm().mit_claude()
    ergebnis = _lauf(welt, "--erstanmeldung")

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == "" and ergebnis.stderr == "", (
        "die haeufigste Lage - alles da - kostet eine Meldung:\n"
        f"{ergebnis.stdout}{ergebnis.stderr}")


@pytest.mark.allow_subprocess
def test_die_erstanmeldung_fragt_genau_einmal(welt):
    """Dieselbe Regel, die src/bin/zepos-session fuer GENERATED_STAMP
    aufschreibt: sonst versucht es jede weitere Anmeldung wieder."""
    welt.mit_npm()
    welt.lege("kitty", '#!/bin/bash\necho "$@" >> "$NPM_PROTOKOLL"\n')
    welt.lege("setsid", '#!/bin/bash\nshift; exec "$@"\n')

    erst = _lauf(welt, "--erstanmeldung")
    assert erst.returncode == 0
    marke = welt.heim / ".local" / "state" / "zepos" / "claude-code-angeboten"
    assert marke.exists(), "die Marke wurde nicht gesetzt"
    nach_erst = welt.aufrufe()
    assert any("zepos-claude-code" in zeile for zeile in nach_erst), (
        f"beim ersten Mal ging kein Fenster auf: {nach_erst}")

    zweit = _lauf(welt, "--erstanmeldung")
    assert zweit.returncode == 0
    assert welt.aufrufe() == nach_erst, (
        "die zweite Anmeldung fragt noch einmal - ein Angebot, das jedes "
        f"Mal wiederkommt, ist eine Belaestigung: {welt.aufrufe()}")


@pytest.mark.allow_subprocess
def test_die_erstanmeldung_ohne_npm_setzt_keine_marke(welt):
    """Wer npm nachtraeglich installiert, soll das Angebot bekommen."""
    ergebnis = _lauf(welt, "--erstanmeldung")

    assert ergebnis.returncode == 0
    marke = welt.heim / ".local" / "state" / "zepos" / "claude-code-angeboten"
    assert not marke.exists(), (
        "ohne npm wurde die Frage als gestellt verbucht - dann bekommt "
        "sie niemand mehr, auch wenn npm spaeter dazukommt")


@pytest.mark.allow_subprocess
def test_die_erstanmeldung_ohne_kitty_setzt_keine_marke(welt):
    """Dieselbe Ueberlegung eine Stufe weiter: npm ist da, aber es gibt
    kein Fenster, in dem gefragt werden koennte.

    Eine Marke, die eine nie gestellte Frage als beantwortet verbucht,
    ist die teuerste Art, still zu sein - der Nutzer bekaeme das Angebot
    nie wieder, ohne je etwas gesehen zu haben.
    """
    welt.mit_npm()          # npm ja, kitty nein
    ergebnis = _lauf(welt, "--erstanmeldung")

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == "" and ergebnis.stderr == "", (
        f"es wurde geklagt statt geschwiegen:\n{ergebnis.stdout}{ergebnis.stderr}")
    marke = welt.heim / ".local" / "state" / "zepos" / "claude-code-angeboten"
    assert not marke.exists(), (
        "ohne kitty wurde die Frage als gestellt verbucht")
    assert welt.aufrufe() == [], (
        f"ohne Fenster wurde trotzdem etwas gerufen: {welt.aufrufe()}")


@pytest.mark.allow_subprocess
def test_die_erstanmeldung_oeffnet_dasselbe_fenster_wie_das_dock(welt):
    """Ein zweiter Weg mit einem zweiten Aussehen waere ein zweiter Ort,
    an dem etwas schiefgehen kann - und im Dock ein zweiter Knopf, weil
    belongsTo() die FENSTERKLASSE vergleicht."""
    welt.mit_npm()
    welt.lege("kitty", '#!/bin/bash\necho "kitty $*" >> "$NPM_PROTOKOLL"\n')
    welt.lege("setsid", '#!/bin/bash\nshift; exec "$@"\n')
    _lauf(welt, "--erstanmeldung")

    zeilen = [z for z in welt.aufrufe() if z.startswith("kitty ")]
    assert zeilen, f"kein Fenster: {welt.aufrufe()}"
    assert "--class zepos-claude-code" in zeilen[0], (
        f"die Fensterklasse fehlt - das Dock bekaeme einen zweiten Knopf: "
        f"{zeilen[0]}")
    assert zeilen[0].rstrip().endswith("-e zepos-claude-code"), (
        f"es wird nicht derselbe Befehl geoeffnet wie im Eintrag: {zeilen[0]}")


# --------------------------------------------------------------------
# 6. Der Eintrag im Starter
# --------------------------------------------------------------------

def test_der_eintrag_ruft_den_starter_und_nicht_claude_direkt():
    text = EINTRAG.read_text(encoding="utf-8")

    assert _feld(text, "Exec").split() == [
        "kitty", "--class", "zepos-claude-code", "-e", "zepos-claude-code"], (
        "Exec ruft nicht den Starter mit gesetzter Fensterklasse: "
        f"{_feld(text, 'Exec')}")
    assert _feld(text, "TryExec") == "/usr/bin/zepos-claude-code"
    assert _feld(text, "StartupWMClass") == "zepos-claude-code"
    assert _feld(text, "Terminal") == "false", (
        "Terminal=true findet kitty nicht - gemessen am 12.08.2026 an "
        "btop.desktop")


def test_der_eintrag_zeigt_auf_das_zeichen_das_daneben_liegt():
    """Der DATEINAME der Zeichen ist der Symbolname aus dem Eintrag.
    Stimmen die beiden nicht ueberein, zeigt der Starter einen leeren
    Kasten und sagt dazu nichts."""
    symbol = _feld(EINTRAG.read_text(encoding="utf-8"), "Icon")
    assert symbol == "zepos-claude-code", (
        f"Icon= ist {symbol}; packaging/zepos-config/PKGBUILD legt die "
        "Dateien unter zepos-claude-code.png ab")


def test_der_eintrag_ist_kein_terminalemulator():
    """Die Kategorie ist die Stelle, an der eine Arbeitsumgebung
    nachsieht, wenn sie "das Terminal" oeffnen will."""
    kategorien = _feld(EINTRAG.read_text(encoding="utf-8"), "Categories")
    assert "TerminalEmulator" not in kategorien, (
        f"Claude Code laeuft in einem Terminal, es IST keines: {kategorien}")


def test_der_eintrag_verschweigt_nicht_dass_claude_code_erst_geholt_wird():
    """Die Herkunftsfrage, an der Stelle, an der ein Mensch sie liest.

    GEMELDET am 01.09.2026: "ich will das packet nicht als meins
    verkaufen". Ein Eintrag, der so aussieht wie jeder andere, behauptet
    stillschweigend, das Programm liege schon da.
    """
    text = EINTRAG.read_text(encoding="utf-8")
    kommentar = _feld(text, "Comment")
    assert "npm" in kommentar, (
        "der Eintrag sagt nicht, dass Claude Code ueber npm kommt: "
        f"{kommentar}")


def test_kein_eintrag_und_kein_befehl_nennt_das_gefallene_paket():
    """Regel 14, kein Deprecated: `pacman -S zepos-claude-code` findet
    nichts mehr, und ein Hinweis darauf waere ein Weg ins Leere."""
    for datei in (EINTRAG, BEFEHL):
        text = datei.read_text(encoding="utf-8")
        ohne_kommentar = "\n".join(
            zeile for zeile in text.splitlines()
            if not zeile.lstrip().startswith("#"))
        assert "pacman -S zepos-claude-code" not in ohne_kommentar, (
            f"{datei.name} schickt den Nutzer zu einem Paket, das es "
            "nicht mehr gibt")


# --------------------------------------------------------------------
# 7. Das Zeichen, und wem es gehoert
# --------------------------------------------------------------------

@pytest.mark.parametrize("groesse", GROESSEN)
def test_jede_groesse_liegt_da_und_ist_ein_png(groesse):
    bild = ZEICHEN / f"claude-code-{groesse}.png"
    assert bild.is_file(), f"{bild.name} fehlt"
    assert bild.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", (
        f"{bild.name} ist kein PNG")


def test_die_herkunft_des_zeichens_steht_daneben():
    """Die Frage, die dem Nutzer die wichtigste war.

    plugins/LICENSE traegt dieselbe Unterscheidung fuer hyprlaunch und
    hyprclipx aus. Ein Zeichen ZEIGT AUF ein Programm; es IST nicht das
    Programm - und wer das behauptet bekommt, soll auch lesen koennen,
    woher die Datei stammt.
    """
    herkunft = ZEICHEN / "HERKUNFT"
    assert herkunft.is_file(), (
        "vier Dateien einer fremden Marke liegen ohne ein Wort dazu im "
        "Baum")
    text = herkunft.read_text(encoding="utf-8")
    assert "Anthropic" in text, "die Datei nennt den Rechteinhaber nicht"
    assert "claude.ai/images/claude_app_icon.png" in text, (
        "die Vorlage ist nicht genannt - dann ist die Herkunft eine "
        "Behauptung")


def test_das_rezept_legt_jede_groesse_unter_hicolor_ab():
    """hicolor, nicht Papirus: hicolor ist der Satz, in den ein Programm
    sein eigenes Zeichen legt und aus dem JEDES Thema es holt, wenn es
    selbst keines hat. Ein Zeichen in Papirus abzulegen hiesse, ein
    fremdes Thema zu veraendern."""
    rezept = REZEPT.read_text(encoding="utf-8")

    ziel = re.search(
        r'install -Dm644 "system/claude-code-icons/claude-code-\$groesse\.png"'
        r' \\\n\s*"\$pkgdir/usr/share/icons/hicolor/'
        r'\$\{groesse\}x\$\{groesse\}/apps/zepos-claude-code\.png"', rezept)
    assert ziel, (
        "packaging/zepos-config/PKGBUILD legt die Zeichen nicht unter "
        "hicolor ab - dann zeigt der Starter einen leeren Kasten")

    schleife = re.search(r"for groesse in ([\d ]+); do", rezept)
    assert schleife, "die Groessenschleife fehlt im Rezept"
    gelegt = tuple(int(zahl) for zahl in schleife.group(1).split())
    assert gelegt == GROESSEN, (
        f"das Rezept legt {gelegt} ab, im Baum liegen {GROESSEN} - eine "
        "Groesse ohne Datei bricht den Bau, eine Datei ohne Groesse ist "
        "17 KiB, die niemand sieht")


# --------------------------------------------------------------------
# 8. Das gefallene Paket ist wirklich weg
# --------------------------------------------------------------------

def test_kein_rezept_baut_claude_code_mehr():
    """Regel 14, und die Zahl gehoert dazu: 91831121 Bytes lagen als
    zepos-claude-code-2.1.233-4-x86_64.pkg.tar.zst auf gh-pages - das
    groesste Objekt im Repository, 87,58 MiB, und bei jedem Push die
    Warnung "larger than GitHub's recommended maximum file size of
    50.00 MB". Das naechstgroesste ist zepos-hyprland mit 53266906
    Bytes.

    GEMESSEN WIRD SEIT DEM 03.09.2026 AM REZEPT UND NICHT AM
    VERZEICHNISNAMEN. Bis dahin stand hier "packaging/zepos-claude-code/
    darf nicht existieren", und das war ein STELLVERTRETER fuer die
    Zusage - nicht die Zusage selbst. Der Unterschied ist kein
    Feinschliff: das Verzeichnis nicht zu haben hat den Nutzer zwei Tage
    von jeder Aktualisierung abgeschnitten.

        Ein geloeschter Name ist kein zurueckgezogenes Paket. pacman
        liest `replaces` NUR beim Sysupgrade (PKGBUILD(5)), und der
        Bereich "zepos" der Selbstaktualisierung setzt `pacman -S` ab -
        also blieb nur der `conflicts` von zepos-config wirksam, und der
        bricht ab. Der Nutzer am 03.09.2026: "dort steht zeppos config
        und zepos claude code are in a conflict und es kann nicht
        aktualsierst werden".

    Seither liegt dort ein UEBERGANGSPAKET: derselbe Name, leer, mit
    epoch. Die Zusage ist unveraendert - ZepOS baut und liefert Claude
    Code nicht aus -, und genau die wird jetzt gemessen: das Rezept hat
    keine Quelle, holt nichts und baut nichts.
    tests/packaging/test_uebergangspaket.py haelt die uebrige Form fest.
    """
    rezept = REPOSITORY / "packaging" / "zepos-claude-code" / "PKGBUILD"
    if rezept.exists():
        ohne = "\n".join(
            zeile for zeile in rezept.read_text(encoding="utf-8").splitlines()
            if not zeile.lstrip().startswith("#"))
        for feld in ("source", "sha256sums", "makedepends"):
            assert not re.search(rf"^{feld}=", ohne, re.M), (
                f"das Rezept traegt wieder {feld}= - dann holt oder baut es "
                f"etwas, und die Zusage vom 01.09.2026 ist gebrochen")
        for befehl in ("npm", "curl", "wget", "git"):
            gestartet = [z.strip() for z in ohne.splitlines()
                         if z.strip().split(" ")[0] == befehl]
            assert gestartet == [], (
                f"das Rezept ruft {befehl} auf: {gestartet}")
        assert "@anthropic-ai" not in ohne, (
            "das Rezept nennt das npm-Paket wieder in ausfuehrbarem Text")


def test_kein_paket_haengt_mehr_an_claude_code():
    """Auch nicht ueber zepos-apps' depends - das war die Zeile, die es
    ueberhaupt installiert hat."""
    for rezept in (REPOSITORY / "packaging").glob("*/PKGBUILD"):
        text = "\n".join(
            zeile for zeile in rezept.read_text(encoding="utf-8").splitlines()
            if not zeile.lstrip().startswith("#"))
        # replaces=/conflicts= trugen den Namen bis zum 03.09.2026 -
        # sie sind gefallen, der Weg ist jetzt das Uebergangspaket. Die
        # Ausnahme bleibt stehen, weil sie nichts kostet und weil ein
        # Rezept, das den Namen in replaces schreibt, damit noch nicht
        # an ihm HAENGT - das ist die Frage dieser Zusicherung.
        ohne_ersatz = re.sub(r"^(replaces|conflicts)=\([^)]*\)", "", text,
                             flags=re.M | re.S)
        assert "'zepos-claude-code'" not in ohne_ersatz, (
            f"{rezept.parent.name} haengt weiterhin an zepos-claude-code")


def test_das_alte_paket_wird_von_einer_installierten_maschine_geholt():
    """OHNE EINEN WEG BLIEBEN 309,6 MiB AUF JEDER SCHON INSTALLIERTEN
    MASCHINE LIEGEN.

    Die Zusage ist dieselbe wie am 01.09.2026, der WEG ist seit dem
    03.09.2026 ein anderer, und der Grund dafuer ist gemessen worden -
    an der Maschine des Nutzers, zwei Tage lang.

    WAS HIER STAND UND WARUM ES NICHT GEREICHT HAT
        `replaces=('zepos-claude-code')` und `conflicts=(...)` in
        zepos-config. PKGBUILD(5) sagt zu `replaces`: "Sysupgrade is
        currently the only pacman operation that utilizes this field. A
        normal sync or upgrade will not use its value." Die
        Selbstaktualisierung setzt im Bereich "zepos" `pacman -S` ab -
        also wurde `replaces` nie gelesen, `conflicts` schon, und mit
        `--noconfirm` bricht pacman ab statt zu fragen. Der Rechner
        bekam GAR KEINE Aktualisierung mehr.

    WAS JETZT DEN WEG TRAEGT
        Ein Uebergangspaket unter demselben Namen, leer, mit `epoch=1`.
        Damit ist die Ablesung eine gewoehnliche Aktualisierung
        (2.1.233-4 -> 1:0.1.x-1), die auch `pacman -S --needed`
        ausfuehrt. Das `epoch` ist der Teil, den die alte Begruendung
        nicht kannte: sie schrieb "ein gleichnamiger Nachfolger waere
        fuer pacman AELTER" - richtig, und genau dafuer gibt es das
        Feld.

    Geprueft wird der Weg und nicht ein einzelnes Feld: dass es das
    Rezept gibt, dass es den Namen traegt, dass sein epoch die alte
    Fassung schlaegt, und dass zepos-config den Konflikt NICHT mehr
    traegt - ein `conflicts` auf einen Namen, den dasselbe Repository
    anbietet, waere derselbe Abbruch noch einmal.
    """
    rezept = REPOSITORY / "packaging" / "zepos-claude-code" / "PKGBUILD"
    assert rezept.is_file(), (
        "es gibt keinen Weg von der alten Fassung weg: ohne Rezept ist der "
        "Name aus dem Repository verschwunden, und pacman kann ein Paket, "
        "das es nicht mehr gibt, nicht ablesen")

    text = rezept.read_text(encoding="utf-8")
    assert re.search(r"^pkgname=zepos-claude-code$", text, re.M), (
        "das Rezept traegt einen anderen Namen - abgelesen wird nur, was "
        "gleich heisst")
    assert re.search(r"^epoch=1$", text, re.M), (
        "ohne epoch haelt pacman 2.1.233-4 fuer neuer als 0.1.x und spielt "
        "nichts ein")

    config = REZEPT.read_text(encoding="utf-8")
    ohne = "\n".join(zeile for zeile in config.splitlines()
                      if not zeile.lstrip().startswith("#"))
    for feld in ("replaces", "conflicts"):
        treffer = re.search(rf"^{feld}=\((.*?)\)", ohne, re.M | re.S)
        assert not (treffer and "zepos-claude-code" in treffer.group(1)), (
            f"zepos-config traegt wieder {feld} auf zepos-claude-code - "
            f"damit ist die Aktualisierung fuer jede Maschine mit dem alten "
            f"Paket blockiert, nicht nur die dieses einen Pakets")
