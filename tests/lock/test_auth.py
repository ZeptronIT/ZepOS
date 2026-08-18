# SPDX-License-Identifier: GPL-3.0-or-later
"""Wird das Passwort wirklich gegen PAM geprueft - und ein falsches abgewiesen?

WIE MAN DAS MISST, OHNE EIN ECHTES PASSWORT ZU KENNEN
    Gar nicht mit dem echten Konto, und das ist keine Bequemlichkeit,
    sondern eine Sicherheitsfrage. Archs auth-Stapel fuehrt
    pam_faillock; /etc/security/faillock.conf ist vollstaendig
    auskommentiert, es gilt also die Vorgabe deny=3, unlock_time=600.
    Drei Fehlversuche eines Tests gegen das Konto des Entwicklers - und
    dieser Mensch kommt zehn Minuten lang nicht mehr an seine eigene
    Maschine. Ein Test, der zum Messen einer Sperre eine Sperre
    verursacht, ist kein Test.

    Der Weg statt dessen: `unshare -Urm` erzeugt einen Benutzer- und
    einen Einhaengenamensraum, in dem dieser Prozess Wurzelrechte hat -
    OHNE sudo, und ohne dass irgendetwas davon ausserhalb sichtbar
    waere. Darin wird ein eigenes Verzeichnis ueber /etc/pam.d gelegt,
    das genau einen Dienst kennt: zepos-lock. Was in diesem Dienst
    steht, bestimmt der Test.

    Das misst mehr als eine Attrappe je koennte. Der Stapel fuehrt
    pam_exec mit expose_authtok, und das uebergibt dem Skript des Tests
    auf stdin GENAU DIE ZEICHENKETTE, die das Programm PAM gegeben hat.
    Damit ist die ganze Kette gemessen: getipptes Wort ->
    Gespraechsfunktion -> pam_authenticate -> Modul -> Antwort ->
    accepted.

WAS DIE MESSUNG NICHT KANN
    Sie sagt nichts darueber, ob pam_unix auf einer Installation
    richtig verdrahtet ist - das ist Archs Stapel und nicht unserer.
    Was sie sagt, ist: dieses Programm fragt PAM, es gibt das getippte
    Wort weiter, und es macht nur bei PAM_SUCCESS auf. Die zwei
    Zusicherungen ueber /etc/pam.d/zepos-lock unten decken die andere
    Haelfte: dass der Dienst, den es fragt, uns gehoert und der richtige
    Stapel darin steht.

DIE MUTATIONEN
    Jede Zusicherung hier wird einmal gebrochen, indem lock/
    zepos-lock-pam.c mit einer gezielten Aenderung neu uebersetzt und
    dieselbe Messung dagegen gefahren wird. Eine Zusicherung, die den
    Mutanten durchlaesst, misst nicht, was sie behauptet.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.lock import nested_compositor as nested

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "lock"
AUTH_SOURCE = LOCK / "zepos-lock-pam.c"
AUTH_HEADER = LOCK / "zepos-lock-auth.h"
PROBE_SOURCE = Path(__file__).with_name("auth_probe.c")

RIGHT = "das-eine-richtige"
WRONG = "das-eine-falsche"


def _tools_missing() -> list[str]:
    return nested.missing_tools("gcc", "pkg-config", "unshare")


def _namespaces_work() -> bool:
    """Ob `unshare -Urm` auf dieser Maschine erlaubt ist.

    Gefragt statt angenommen: einige Distributionen und einige
    Container-Laufzeiten schalten unprivilegierte Benutzernamensraeume
    ab, und dann ist das Ergebnis "Operation not permitted" und nicht
    ein Testfehler ueber PAM.
    """
    try:
        return subprocess.run(["unshare", "-Urm", "true"],
                              capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):        # pragma: no cover
        return False


requires = pytest.mark.skipif(
    bool(_tools_missing()) or not _namespaces_work(),
    reason=("braucht gcc, pkg-config und einen benutzbaren "
            "`unshare -Urm`; fehlt: "
            + (", ".join(_tools_missing()) or "unprivilegierte Namensraeume")))


# --------------------------------------------------------------------
# Der Prueftisch
# --------------------------------------------------------------------

def _pam_stack(directory: Path, body: str, log: Path | None = None) -> Path:
    """Ein /etc/pam.d, das genau einen Dienst kennt.

    Absichtlich NUR zepos-lock: faellt das Programm auf einen anderen
    Dienstnamen zurueck, findet Linux-PAM in diesem Verzeichnis nichts -
    auch kein `other` - und pam_start() antwortet mit PAM_ABORT. Der
    Test unten, der genau das prueft, haengt daran.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "zepos-lock").write_text(body, encoding="utf-8")
    if log is not None:
        log.write_text("", encoding="utf-8")
    return directory


def _checker(path: Path, expected: str, log: Path) -> Path:
    """Das Modul, das der Test selbst schreibt.

    pam_exec mit expose_authtok schiebt ihm das Passwort auf stdin. Es
    schreibt mit, was ankommt - dadurch ist nachher belegbar, dass die
    getippten Zeichen wirklich bis zu PAM gelaufen sind, und nicht bloss,
    dass irgendetwas abgelehnt wurde.
    """
    path.write_text(
        "#!/bin/sh\n"
        "read -r token\n"
        f"printf '%s\\n' \"$token\" >> {log}\n"
        f"[ \"$token\" = '{expected}' ] && exit 0\n"
        "exit 1\n",
        encoding="utf-8")
    path.chmod(0o755)
    return path


def _run_in_namespace(pamd: Path, command: list[str]) -> subprocess.CompletedProcess:
    """Fuehrt command aus, mit pamd als /etc/pam.d - nur in diesem Prozess.

    Der Einhaengevorgang ist auf den Namensraum beschraenkt, den unshare
    gerade erzeugt hat. Das /etc/pam.d der Maschine bleibt unberuehrt;
    kein anderer Prozess sieht die Aenderung, und sie endet mit dem
    letzten Prozess darin.
    """
    quoted = " ".join(f"'{part}'" for part in command)
    return subprocess.run(
        ["unshare", "-Urm", "sh", "-c",
         f"mount --bind '{pamd}' /etc/pam.d && exec {quoted}"],
        capture_output=True, text=True, timeout=120)


def _probe(tmp_path: Path, sources: list[Path] | None = None,
           name: str = "auth_probe") -> Path:
    return nested.build(name, sources or [PROBE_SOURCE, AUTH_SOURCE], tmp_path)


def _mutate(tmp_path: Path, name: str, old: str, new: str) -> Path:
    """Eine Kopie von zepos-lock-pam.c mit genau einer Aenderung.

    Der Treffer wird gezaehlt statt ersetzt-und-gehofft: eine Mutation,
    die ins Leere greift, weil jemand die Zeile umformuliert hat, waere
    ein Mutant, der mit dem Original identisch ist - und ein
    Mutationstest, der immer besteht.
    """
    text = AUTH_SOURCE.read_text(encoding="utf-8")
    assert text.count(old) == 1, (
        f"die Mutation {name} findet ihre Stelle nicht ({text.count(old)}x): "
        f"{old!r}")
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "zepos-lock-pam.c").write_text(
        text.replace(old, new), encoding="utf-8")
    (directory / "zepos-lock-auth.h").write_text(
        AUTH_HEADER.read_text(encoding="utf-8"), encoding="utf-8")
    return nested.build(
        name, [PROBE_SOURCE, directory / "zepos-lock-pam.c"], directory)


# --------------------------------------------------------------------
# 1. Die Kette: getipptes Wort -> PAM -> Antwort
# --------------------------------------------------------------------

@requires
@pytest.mark.allow_subprocess
def test_the_typed_word_reaches_pam_and_only_pams_yes_opens(tmp_path):
    """Das eine Ergebnis, das dieser ganze Zweig schuldet.

    Drei Dinge in einem Lauf, weil sie nur zusammen etwas bedeuten:

      * ein richtiges Passwort wird angenommen
      * ein falsches wird abgelehnt
      * PAM hat BEIDE Zeichenketten woertlich gesehen

    Ohne den dritten Punkt waere der zweite wertlos: ein Programm, das
    ueberhaupt nichts an PAM weiterreicht, lehnt auch alles ab und
    bestuende die ersten beiden.
    """
    log = tmp_path / "gesehen.log"
    pamd = tmp_path / "pamd"
    checker = _checker(tmp_path / "check.sh", RIGHT, log)
    _pam_stack(pamd,
               f"auth required pam_exec.so expose_authtok quiet {checker}\n",
               log)
    probe = _probe(tmp_path)

    refused = _run_in_namespace(pamd, [str(probe), "tester", WRONG])
    assert refused.returncode == 1, (
        f"ein falsches Passwort wurde nicht abgelehnt:\n{refused.stdout}"
        f"{refused.stderr}")
    assert "accepted=0" in refused.stdout, refused.stdout

    accepted = _run_in_namespace(pamd, [str(probe), "tester", RIGHT])
    assert accepted.returncode == 0, (
        f"ein richtiges Passwort wurde nicht angenommen:\n{accepted.stdout}"
        f"{accepted.stderr}")
    assert "accepted=1 code=0" in accepted.stdout, accepted.stdout

    seen = log.read_text(encoding="utf-8").split()
    assert seen == [WRONG, RIGHT], (
        "PAM hat nicht die getippten Zeichenketten gesehen, sondern "
        f"{seen!r}. Was oben gemessen wurde, war dann nicht die Kette vom "
        "Feld bis zum Modul.")


@requires
@pytest.mark.allow_subprocess
def test_a_no_is_a_no_whatever_number_pam_puts_on_it(tmp_path):
    """Die Ablehnung, die NICHT PAM_AUTH_ERR heisst.

    GEMESSEN am 12.08.2026, und die Vermutung war falsch: pam_deny.so
    liefert 7 (PAM_AUTH_ERR), nicht 6 (PAM_PERM_DENIED). Ein Modul, das
    einen anderen Code liefert, ist pam_exec mit einem Skript, das
    ungleich null endet - das wird 4 (PAM_SYSTEM_ERR).

    Genau das ist der Grund, aus dem in zepos-lock-pam.c
    `== PAM_SUCCESS` steht und nicht `!= PAM_AUTH_ERR`: PAM kennt ein
    Dutzend Rueckgabewerte, und nur einer heisst ja. Der Mutationstest
    unten bricht die Zeile und braucht dafuer genau diesen Stapel.
    """
    log = tmp_path / "gesehen.log"
    checker = _checker(tmp_path / "check.sh", RIGHT, log)
    pamd = _pam_stack(
        tmp_path / "pamd",
        f"auth required pam_exec.so expose_authtok quiet {checker}\n", log)
    probe = _probe(tmp_path)

    result = _run_in_namespace(pamd, [str(probe), "tester", WRONG])
    assert result.returncode == 1, result.stdout + result.stderr
    codes = re.search(r"accepted=(\d+) code=(\d+)", result.stdout)
    assert codes is not None, result.stdout
    assert codes.group(1) == "0", result.stdout
    assert codes.group(2) not in ("0", "7"), (
        "dieser Stapel sollte weder Erfolg noch PAM_AUTH_ERR liefern - "
        "sonst prueft der Mutationstest darunter nichts: " + result.stdout)


@requires
@pytest.mark.allow_subprocess
def test_a_missing_pam_service_is_a_refusal_and_not_a_way_in(tmp_path):
    """Der Ausfall, der jemanden HEREINLIESSE, statt ihn auszusperren.

    Linux-PAM faellt fuer einen unbekannten Dienst auf /etc/pam.d/other
    zurueck. Archs `other` ist viermal pam_deny.so - der Rueckfall faellt
    dort also zu. Hier gibt es im Namensraum ueberhaupt kein `other`, und
    das ist der haertere Fall: pam_start() selbst muss dann abbrechen.

    Gemessen: PAM_ABORT (26). Und accepted bleibt 0, was die eigentliche
    Zusicherung ist - der Code darf hier alles sein, nur kein Erfolg.
    """
    pamd = _pam_stack(tmp_path / "pamd", "auth required pam_permit.so\n")
    # Ein Dienst, der sich NICHT zepos-lock nennt: der Stapel oben liegt
    # also da und wird nicht gefunden.
    (pamd / "zepos-lock").rename(pamd / "irgendein-anderer-dienst")
    probe = _probe(tmp_path)

    result = _run_in_namespace(pamd, [str(probe), "tester", RIGHT])
    assert result.returncode == 1, (
        "ohne PAM-Dienst wurde jemand hereingelassen:\n"
        + result.stdout + result.stderr)
    assert "accepted=0" in result.stdout, result.stdout


@requires
@pytest.mark.allow_subprocess
def test_a_missing_user_is_refused_before_pam_is_asked(tmp_path):
    """Mit leerem Benutzernamen gaebe es niemanden, gegen den zu pruefen
    waere - und ein pam_permit-Stapel liesse trotzdem auf."""
    pamd = _pam_stack(tmp_path / "pamd", "auth required pam_permit.so\n")
    probe = _probe(tmp_path)

    result = _run_in_namespace(pamd, [str(probe), "", RIGHT])
    assert result.returncode == 1, result.stdout + result.stderr
    assert "kein Benutzername" in result.stdout, result.stdout


@requires
@pytest.mark.allow_subprocess
def test_what_pam_said_is_carried_out_of_the_check(tmp_path):
    """Die Meldung, wegen der ueberhaupt eine getragen wird.

    pam_faillock sagt nach drei Fehlversuchen selbst, dass und wie lange
    das Konto gesperrt ist. Ein Sperrbildschirm, der darauf mit seinem
    festen "Falsches Passwort" antwortet - so wie hyprlock es tat -,
    schickt seinen Benutzer los, ein Passwort zu suchen, das er schon
    hat. pam_echo steht hier stellvertretend fuer jedes Modul, das
    ueber das Gespraech redet.
    """
    message = tmp_path / "sagt.txt"
    message.write_text("Konto gesperrt, noch 600 Sekunden\n", encoding="utf-8")
    pamd = _pam_stack(
        tmp_path / "pamd",
        f"auth requisite pam_echo.so file={message}\n"
        "auth required pam_deny.so\n")
    probe = _probe(tmp_path)

    result = _run_in_namespace(pamd, [str(probe), "tester", RIGHT])
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Konto gesperrt, noch 600 Sekunden" in result.stdout, (
        "die Meldung von PAM kommt nicht aus der Pruefung heraus, also "
        "kann der Bildschirm sie nicht zeigen:\n" + result.stdout)


# --------------------------------------------------------------------
# 2. Die Datei unter /etc/pam.d, und was darin stehen muss
# --------------------------------------------------------------------

def _pam_lines() -> list[str]:
    text = (LOCK / "zepos-lock.pam").read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def test_the_lock_screen_has_a_pam_file_of_its_own():
    """Kein `include hyprlock`, kein geliehener Dienstname.

    Ein Programm, das den PAM-Dienst eines anderen benutzt, verliert
    seine Authentisierung mit dessen Paket - und genau dieses Paket geht
    mit dieser Aenderung.
    """
    assert (LOCK / "zepos-lock.pam").is_file(), "lock/zepos-lock.pam fehlt"

    source = AUTH_SOURCE.read_text(encoding="utf-8")
    code = [line for line in source.splitlines()
            if not line.lstrip().startswith((" *", "/*", "*"))]
    assert '#define ZEPOS_LOCK_PAM_SERVICE "zepos-lock"' in code, (
        "der Dienstname im Hinterbau ist nicht zepos-lock: " + "\n".join(code))

    # Und das Rezept installiert die Datei wirklich dorthin, wo PAM sie
    # sucht. meson.build ist die Zusicherung, der PKGBUILD die Messung
    # am fertigen Paket.
    meson = (LOCK / "meson.build").read_text(encoding="utf-8")
    body = [line.strip() for line in meson.splitlines()
            if not line.lstrip().startswith("#")]
    assert "install_dir : '/etc/pam.d'," in body, (
        "meson installiert die PAM-Datei nicht nach /etc/pam.d")
    assert "rename : 'zepos-lock'," in body, (
        "die Datei landet unter einem anderen Namen als dem Dienstnamen")


def test_the_surface_knows_nothing_about_pam():
    """Die Naht, an der spaeter die ANMELDUNG haengen soll.

    Bei Apple sind Anmelde- und Sperrbildschirm dieselbe Flaeche - der
    Nutzer am 12.08.2026: "sorge dafuer das der login auch wirklich
    modern aussieht vgl. apple os login ja ?". Bei ZepOS sind es heute
    zwei fremde Programme; dieses hier ersetzt eines davon.

    Der einzige Unterschied zwischen beiden ist, WOHER die Antwort auf
    "ist das Passwort richtig" kommt: beim Sperren PAM direkt, beim
    Anmelden greetd ueber $GREETD_SOCK. Alles andere - Fenster,
    Hintergrund, Uhr, Feld, Meldung, Stylesheet - ist dasselbe.

    Damit die Anmeldung spaeter ein zweites HINTERTEIL sein kann und
    kein zweites Programm, darf die Oberflaeche PAM nicht kennen. Diese
    Zusicherung ist das, was verhindert, dass die Naht beim naechsten
    Anfassen wieder zuwaechst - ein einziges `#include
    <security/pam_appl.h>` in zepos-lock.c genuegte dafuer.

    Geprueft am Quelltext OHNE Kommentare, weil der Kopf beider Dateien
    PAM ausdruecklich NENNT, um die Aufteilung zu begruenden.
    """
    for path in (LOCK / "zepos-lock.c", LOCK / "zepos-lock-auth.h"):
        text = path.read_text(encoding="utf-8")
        code = [line for line in text.splitlines()
                if not line.lstrip().startswith(("*", "/*", "#     ", " *"))]
        body = "\n".join(code)
        assert "pam_appl.h" not in body, (
            f"{path.name} bindet PAM ein - dann ist die Oberflaeche an den "
            "Hinterbau geloetet")
        assert not re.search(r"\bPAM_[A-Z_]+\b", body), (
            f"{path.name} nennt eine PAM-Konstante: "
            + str(re.findall(r"\bPAM_[A-Z_]+\b", body)))
        assert not re.search(r"\bpam_[a-z_]+\(", body), (
            f"{path.name} ruft eine PAM-Funktion: "
            + str(re.findall(r"\bpam_[a-z_]+\(", body)))

    # Und die Gegenrichtung: der Hinterbau tut es sehr wohl, sonst
    # prueft die Zusicherung oben eine Trennung, hinter der nichts ist.
    backend = AUTH_SOURCE.read_text(encoding="utf-8")
    assert "pam_authenticate(" in backend, (
        "der Hinterbau ruft PAM gar nicht - dann trennt die Naht nichts")


def test_the_build_picks_the_backend_by_source_file():
    """Kein Umschalten zur Laufzeit, und das ist Absicht.

    Ein Sperrbildschirm, der sich aussuchen kann, WEN er nach dem
    Passwort fragt, ist genau ein Angriffsweg mehr. Die Auswahl gehoert
    an den Linker: lock/meson.build baut zepos-lock gegen
    zepos-lock-pam.c, und ein kuenftiges zepos-greeter baute dieselbe
    Oberflaeche gegen eine andere Datei.
    """
    meson = (LOCK / "meson.build").read_text(encoding="utf-8")
    code = [line.strip() for line in meson.splitlines()
            if not line.lstrip().startswith("#")]
    assert "['zepos-lock.c', 'zepos-lock-pam.c']," in code, (
        f"die Quelldateiliste nennt den Hinterbau nicht: {code}")

    # Und die Oberflaeche haengt nur am Kopf, nicht an einer .c-Datei.
    surface = (LOCK / "zepos-lock.c").read_text(encoding="utf-8")
    assert '#include "zepos-lock-auth.h"' in surface
    assert "zepos-lock-pam.c" not in "\n".join(
        line for line in surface.splitlines()
        if line.lstrip().startswith("#include"))


def test_the_pam_file_uses_system_auth_and_not_the_login_stack():
    """Warum nicht `include login`, was hyprlock, swaylock und gtklock tun.

    `login` bringt ueber system-login zwei Zeilen mit, die eine SITZUNG
    eroeffnen und nicht eine bestehende oeffnen:

        auth required   pam_shells.so     Anmeldeschale aus /etc/shells
        auth requisite  pam_nologin.so    kein /etc/nologin

    Beide koennen jemanden von seinem EIGENEN laufenden Schreibtisch
    aussperren, mit richtigem Passwort. Der Kopf von lock/zepos-lock.pam
    fuehrt die Messung.
    """
    lines = _pam_lines()
    assert lines == ["auth include system-auth"], (
        f"der PAM-Stapel ist nicht mehr genau eine auth-Zeile: {lines}")


def test_the_check_asks_only_for_authentication():
    """pam_acct_mgmt steht absichtlich nicht im Code.

    Kontoverwaltung entscheidet, ob eine Sitzung BEGONNEN werden darf.
    Hinter diesem Bildschirm laeuft eine bereits. Ein abgelaufenes
    Passwort hiesse sonst: der Nutzer kommt an seine offenen Dateien
    nicht mehr heran, und der Sperrbildschirm hat keinen Weg zurueck.

    Geprueft am Code ohne Kommentare, weil sowohl die .c als auch die
    .pam den Aufruf beim Namen NENNEN, um zu begruenden, warum es ihn
    nicht gibt.
    """
    text = AUTH_SOURCE.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith(("*", "/*")))
    assert "pam_authenticate(" in code, "es wird gar nicht authentisiert"
    assert "pam_acct_mgmt" not in code, (
        "pam_acct_mgmt ist zurueck - ein abgelaufenes Passwort sperrt damit "
        "jemanden aus seiner laufenden Sitzung aus")


@pytest.mark.allow_subprocess
def test_the_check_has_no_display_to_ask(tmp_path):
    """Die Pruefung darf nichts von GTK wissen.

    Sie laeuft in einem eigenen Faden, waehrend die Oberflaeche zeichnet;
    und sie ist die Stelle, an der eine Entscheidung faellt, die kein
    Widget beeinflussen darf. Gemessen am Uebersetzungslauf: die Datei
    wird OHNE die GTK-Flaggen uebersetzt, und wenn sie einen GTK-Kopf
    einbindet, faellt das hier aus.
    """
    if nested.missing_tools("gcc"):
        pytest.skip("kein gcc")
    result = subprocess.run(
        ["gcc", "-c", "-o", str(tmp_path / "auth.o"), str(AUTH_SOURCE),
         f"-I{LOCK}", "-Wall", "-Wextra", "-Werror"],
        capture_output=True, text=True)
    assert result.returncode == 0, (
        "zepos-lock-pam.c laesst sich nicht ohne GTK uebersetzen:\n"
        + result.stderr)


# --------------------------------------------------------------------
# 3. Die Mutationen
# --------------------------------------------------------------------
#
# Jede bricht genau eine Zeile und faehrt dieselbe Messung wie oben
# dagegen. Faellt der Mutant nicht durch, misst die Zusicherung darueber
# nicht, was sie behauptet.

@requires
@pytest.mark.allow_subprocess
def test_mutation_accepting_anything_but_auth_err_is_caught(tmp_path):
    """MUTATION 1: `== PAM_SUCCESS` wird zu `!= PAM_AUTH_ERR`.

    Der naheliegende Denkfehler, und der gefaehrlichste: pam_deny
    antwortet mit PAM_PERM_DENIED, pam_faillock nach dem Zaehler mit
    PAM_MAXTRIES, ein kaputter Stapel mit PAM_ABORT. Der Mutant liesse
    alle drei als Erfolg durch.
    """
    log = tmp_path / "gesehen.log"
    checker = _checker(tmp_path / "check.sh", RIGHT, log)
    pamd = _pam_stack(
        tmp_path / "pamd",
        f"auth required pam_exec.so expose_authtok quiet {checker}\n", log)
    mutant = _mutate(tmp_path, "mut_auth_err",
                     "result->accepted = (code == PAM_SUCCESS) ? 1 : 0;",
                     "result->accepted = (code != PAM_AUTH_ERR) ? 1 : 0;")

    result = _run_in_namespace(pamd, [str(mutant), "tester", WRONG])
    assert result.returncode == 0 and "accepted=1" in result.stdout, (
        "der Mutant haette mit einem FALSCHEN Passwort hereinlassen sollen "
        "und tat es nicht - dann misst der Stapel etwas anderes als "
        "gedacht:\n" + result.stdout)

    original = _probe(tmp_path)
    good = _run_in_namespace(pamd, [str(original), "tester", WRONG])
    assert good.returncode == 1 and "accepted=0" in good.stdout, (
        "das Original laesst denselben Stapel durch wie der Mutant")


@requires
@pytest.mark.allow_subprocess
def test_mutation_never_asking_pam_at_all_is_caught(tmp_path):
    """MUTATION 2: pam_authenticate wird gar nicht mehr gerufen.

    Ein Bildschirm, der ein Passwortfeld ZEIGT. Die Zusicherung ganz
    oben faellt hierueber nur, weil sie auch das MITSCHREIBEN des
    Moduls prueft - ein falsches Passwort abzulehnen kann ein Programm
    auch, indem es alles ablehnt.
    """
    log = tmp_path / "gesehen.log"
    checker = _checker(tmp_path / "check.sh", RIGHT, log)
    pamd = _pam_stack(
        tmp_path / "pamd",
        f"auth required pam_exec.so expose_authtok quiet {checker}\n", log)
    mutant = _mutate(tmp_path, "mut_no_pam",
                     "    code = pam_authenticate(pam, 0);",
                     "    code = PAM_SUCCESS;")

    result = _run_in_namespace(pamd, [str(mutant), "tester", WRONG])
    assert result.returncode == 0, (
        "der Mutant sollte ohne PAM aufmachen:\n" + result.stdout)
    assert log.read_text(encoding="utf-8").strip() == "", (
        "das Modul wurde gerufen, obwohl der Mutant pam_authenticate "
        "uebersprungen hat - die Mutation greift nicht")


@requires
@pytest.mark.allow_subprocess
def test_mutation_sending_the_username_instead_of_the_password_is_caught(tmp_path):
    """MUTATION 3: die Gespraechsfunktion antwortet mit dem Benutzernamen.

    Ein Programm, das PAM etwas anderes gibt als das Getippte, lehnt
    jedes Passwort ab und sieht dabei aus wie eines, das sehr streng
    prueft. Gefangen wird das nur, weil das Modul mitschreibt, WAS
    ankam.
    """
    log = tmp_path / "gesehen.log"
    checker = _checker(tmp_path / "check.sh", RIGHT, log)
    pamd = _pam_stack(
        tmp_path / "pamd",
        f"auth required pam_exec.so expose_authtok quiet {checker}\n", log)
    mutant = _mutate(
        tmp_path, "mut_wrong_answer",
        "        case PAM_PROMPT_ECHO_OFF:\n"
        "            replies[index].resp =\n"
        "                strdup(state->password != NULL ? state->password : \"\");",
        "        case PAM_PROMPT_ECHO_OFF:\n"
        "            replies[index].resp =\n"
        "                strdup(state->user != NULL ? state->user : \"\");")

    result = _run_in_namespace(pamd, [str(mutant), "tester", RIGHT])
    assert result.returncode == 1, (
        "der Mutant hat mit dem Benutzernamen aufgemacht:\n" + result.stdout)
    assert log.read_text(encoding="utf-8").split() == ["tester"], (
        "PAM hat nicht den Benutzernamen gesehen - die Mutation greift nicht")

    log.write_text("", encoding="utf-8")
    original = _probe(tmp_path)
    good = _run_in_namespace(pamd, [str(original), "tester", RIGHT])
    assert good.returncode == 0, (
        "das Original kommt mit demselben Stapel nicht durch:\n" + good.stdout)
    assert log.read_text(encoding="utf-8").split() == [RIGHT]


@requires
@pytest.mark.allow_subprocess
def test_mutation_dropping_the_empty_user_guard_is_caught(tmp_path):
    """MUTATION 4: die Pruefung auf den leeren Benutzernamen faellt weg.

    Dann fragt PAM ueber das Gespraech nach dem Namen, die
    Antwortfunktion gibt die leere Zeichenkette zurueck, und ein
    freundlicher Stapel macht auf.
    """
    pamd = _pam_stack(tmp_path / "pamd", "auth required pam_permit.so\n")
    mutant = _mutate(
        tmp_path, "mut_no_user_guard",
        '    if (user == NULL || user[0] == \'\\0\') {',
        '    if (0) {')

    result = _run_in_namespace(pamd, [str(mutant), "", RIGHT])
    assert result.returncode == 0, (
        "der Mutant sollte ohne Benutzernamen bis zu PAM durchlaufen:\n"
        + result.stdout)

    original = _probe(tmp_path)
    good = _run_in_namespace(pamd, [str(original), "", RIGHT])
    assert good.returncode == 1, (
        "das Original laesst einen leeren Benutzernamen durch")
