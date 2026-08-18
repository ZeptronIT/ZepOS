#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Die eine Stelle, die Hyprlands Tastenzeilen liest.

WOZU, UND ES HAT EIN DATUM
    Am 11.08.2026 hat ein Mensch das gebaute System benutzt und gemeldet,
    das Bildschirmfoto-Werkzeug fehle. Es fehlte nicht: grim, slurp und
    satty lagen auf der Platte und SUPER+S rief sie. Er hat es nicht
    gefunden. Fuer einen Nutzer ist "vorhanden, aber unauffindbar"
    dasselbe wie "fehlt".

    Nachsehen konnte er an zwei Stellen, und beide waren von Hand
    gepflegte Listen NEBEN der Konfiguration:

        ags/scripts/hypr-shortcuts.py   das Leistenmodul, 65 Eintraege
        ags/widget/Shortcuts.tsx        die Ueberlagerung, 77 Eintraege

    GEMESSEN am 12.08.2026 an einem vollstaendigen `--all`-Lauf: der
    erzeugte Baum bindet 86 Tastenkombinationen. 19 davon nennt keine der
    beiden Listen, 26 Eintraege der Listen haben im erzeugten Baum keine
    Bindung, und die beiden Listen widersprechen einander. Die
    Ueberlagerung schrieb an dem Tag noch "Browser (Epiphany)", waehrend
    die Bindung firefox startet - dieselbe Luege, die im Leistenmodul
    einen Tag zuvor korrigiert worden war. Die Korrektur hat die zweite
    Liste nicht erreicht, weil niemand wusste, dass es sie gibt.

    Das ist kein Fluechtigkeitsfehler, sondern die Bauart: zwei Listen
    neben einer Wahrheit laufen auseinander, immer, und zwar leise.

DIE ANTWORT: DIE BESCHREIBUNG STEHT IN DER KONFIGURATION SELBST
    Ueber jeder bind-Zeile steht eine Markierung:

        # @Bildschirm: Bildschirmfoto vom gewaehlten Bereich (grim, slurp, satty)
        bind = $mainMod, S, exec, grim -g "$(slurp)" - | satty -f -

    Damit gibt es keine zweite Liste mehr. Wer die Taste aendert, hat die
    Beschreibung vor der Nase; wer die Zeile loescht, loescht beide; und
    jede Oberflaeche, die zeigt, was eine Taste tut, liest DIESE Datei.

    Die Markierung muss unmittelbar ueber der bind-Zeile stehen. Nicht,
    weil das bequemer zu lesen waere, sondern weil "unmittelbar" die
    einzige Regel ist, die eine Pruefung vollstaendig durchsetzen kann:
    bei jedem Abstand dazwischen muesste sie entscheiden, wie weit eine
    Markierung traegt, und jede solche Entscheidung ist die Luecke, durch
    die eine Beschreibung an die falsche Taste rutscht.

WARUM KEIN `bindd`
    Hyprland kann eine Beschreibung selbst tragen: `bindd = MODS, taste,
    beschreibung, dispatcher, argumente`, und `hyprctl binds -j` gibt sie
    zurueck - GEMESSEN am 12.08.2026 gegen Hyprland 0.55.4, das Feld
    heisst "description" und "has_description" ist auf dieser Maschine
    ueberall false.

    Trotzdem nicht. Die Flaggen hinter `bind` sind kombinierbar, also
    muesste `bindm` zu `binddm` werden - und ob Hyprlands Auswerter genau
    diese Kombination annimmt, kann in diesem Baum NIEMAND messen: dafuer
    braucht es einen laufenden Compositor, und der einzige in Reichweite
    ist der des Nutzers. Eine unmessbare Annahme in der Datei, deren
    Scheitern die Sitzung kostet (Spec §7.4), ist genau der Handel, den
    dieses Projekt nicht macht. Ein Kommentar ist in jeder Fassung von
    Hyprland ein Kommentar.

    Was dadurch verloren geht, ist eine Beschreibung in `hyprctl binds`.
    Gebraucht wird sie dort von nichts: alle Leser hier lesen die Datei,
    und die Datei kennen sie auch aus einer TTY, in der kein Compositor
    laeuft.

WAS DIE MARKIERUNG NICHT VERHINDERT, UND WER ES DANN TUT
    Sie haelt Taste und Beschreibung zusammen. Dass die Beschreibung das
    RICHTIGE Programm nennt, haelt sie nicht - "Browser (Epiphany)" ueber
    `exec, firefox` waere weiterhin schreibbar. Das faengt
    tests/src/test_keybinds.py: jeder eingeklammerte Name einer
    Beschreibung muss ein Wort des Kommandos DERSELBEN Zeile sein. Ohne
    Ausnahmeliste, fuer jede Bindung.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from .paths import output_root
except ImportError:  # als flaches Modul aus /usr/share/zepos geladen
    from paths import output_root

# Jede Datei einer Installation, die eine Taste oder eine Startzeile
# tragen kann. Sie stand in doctor.py und ist hierher gewandert, weil
# jetzt mehr als der Doktor sie braucht - und zwei Listen derselben
# Dateien waeren genau der Fehler, den dieses Modul abschafft.
HYPRLAND_CONF = ("hypr", "hyprland.conf")
PLUGINS_CONF = ("hypr", "plugins.conf")

BOUND_CONFIGS = (
    HYPRLAND_CONF,
    PLUGINS_CONF,
    # Die Datei, in der eine stumme Taste am teuersten ist: sie wird
    # geladen, wenn die normale Konfiguration schon nicht mehr geht, und
    # ihre vier notify-send-Zeilen sind das Einzige, was dann noch
    # erklaert, was gerade passiert.
    ("hypr", "hyprland-failsafe.conf"),
    ("hypr", "profile-autostart.conf"),
    # Und die, die man vergisst: profile-keybinds.conf schreibt
    # save-profile aus dem, was der Nutzer selbst gebunden hat. Eine
    # Bindung von dort zeigt genauso ins Leere wie eine aus einer
    # Vorlage, und sie ist die einzige, die kein Test dieses Projekts je
    # zu Gesicht bekommt.
    ("hypr", "profile-keybinds.conf"),
)

# Die Dateien, die eine Uebersicht zeigt. Nicht alle fuenf von oben:
# profile-autostart.conf traegt keine Tasten, sondern Startzeilen, und
# eine Uebersicht ueber Tasten, in der Startzeilen stehen, beantwortet
# eine Frage, die niemand gestellt hat.
OVERVIEW_CONFIGS = (
    HYPRLAND_CONF,
    PLUGINS_CONF,
    ("hypr", "hyprland-failsafe.conf"),
    ("hypr", "profile-keybinds.conf"),
)

# Die Markierung: `# @Gruppe: Beschreibung`.
#
# Die Gruppe darf keinen Doppelpunkt tragen - getrennt wird am ERSTEN -,
# und die Beschreibung darf nicht leer sein. Beides prueft
# tests/src/test_keybinds.py an den erzeugten Dateien; hier wird eine
# Zeile, die nicht passt, einfach nicht als Markierung gelesen. Ein
# Muster, das auch die halbe Form annimmt, macht aus einem Tippfehler
# eine leere Beschreibung, und eine leere Beschreibung sieht in jeder
# Uebersicht aus wie eine Taste, die nichts tut.
MARKER = re.compile(r"^[ \t]*#[ \t]*@([^:\n]+?)[ \t]*:[ \t]*(\S.*?)[ \t]*$")

# Hyprlands Bindungsformen. Die Buchstaben hinter `bind` sind Flaggen und
# in beliebiger Reihenfolge kombinierbar - l gesperrt, r beim Loslassen,
# e wiederholend, n ohne Modifikator, m Maus, t durchlassend, i
# Modifikatoren ignorierend, s Mehrfachtaste, d mit Beschreibung, p am
# Inhibitor vorbei, o langer Druck.
BIND = re.compile(r"^[ \t]*bind([lrenmtisdpo]*)[ \t]*=[ \t]*(.*?)[ \t]*$")

# Und die Zeilen, die eine Sitzung startet, ohne dass jemand eine Taste
# drueckt. exec-once laeuft beim Start, exec bei jedem Reload.
EXEC_LINE = re.compile(r"^\s*exec(?:-once|-shutdown)?\s*=\s*(.+?)\s*$")

# Wo eine Shell-Zeile aufhoert und die naechste anfaengt. Ohne das waere
# `grim -g "$(slurp)" - | satty -f -` EIN Kommando namens grim, und
# slurp und satty - die beiden Haelften des Bildschirmfotos, das der
# Nutzer nicht gefunden hat - waeren nie geprueft worden.
COMMAND_SEPARATOR = re.compile(r"\|\||&&|\||;|&(?!&)|\$\(|`|\)|\n")

# Eine Zuweisung vor dem Kommando: `FOO=bar programm`. Sie gehoert
# uebersprungen, sonst waere `FOO=bar` der Programmname.
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+")

# Was die Shell selbst kann. Ein Test darauf, ob `if` installiert ist,
# waere eine Meldung ueber nichts - und `echo`, `test` und `[` sind zwar
# auch Dateien in coreutils, werden aber von jeder Shell eingebaut
# beantwortet, bevor der PATH ueberhaupt befragt wird.
SHELL_WORDS = frozenset({
    "if", "then", "elif", "else", "fi", "for", "while", "until", "do",
    "done", "case", "esac", "in", "function", "select", "time",
    "cd", "echo", "printf", "test", "[", "[[", "]]", "]", "source", ".",
    "eval", "exit", "return", "true", "false", "read", "local", "export",
    "set", "unset", "shift", "wait", "trap", ":", "break", "continue",
    "declare", "typeset", "alias", "unalias", "pwd", "umask",
})

# Wie ein Kommandoname aussieht. Ein Wort, das damit nicht uebereinstimmt,
# ist ein Argument, das durch die Trennung gerutscht ist - eine Zahl, ein
# Dateiname, ein halbes Anfuehrungszeichen - und keine Meldung wert.
COMMAND_NAME = re.compile(r"^(?:(?:~|\.{1,2})?/[\w./~@+-]*|[A-Za-z][\w.@+-]*)$")

# Programme, deren `-e` das eigentliche Programm einleitet.
#
# WARUM DAS HIER STEHEN MUSS
#     GEMESSEN am 12.08.2026: `kitty -e btop` in ags-bar.template nennt
#     zwei Programme, und die Zerlegung oben sah nur das erste. btop
#     stand in KEINEM Rezept dieses Projekts - `grep -rn btop` fand
#     genau jene eine Zeile -, also oeffnete der Klick auf das
#     Hardware-Modul ein Terminal, das sofort wieder zuging. Es ist
#     derselbe Fehler wie `grim -g "$(slurp)"`, nur hinter einem
#     Schalter statt hinter einer Roehre: das gesuchte Programm steht
#     nicht vorn.
#
# WARUM EINE LISTE UND NICHT "JEDES -e"
#     Weil `-e` ausserhalb eines Terminals etwas anderes heisst -
#     `grep -e muster` waere sonst ein Aufruf des Programms `muster`.
#     Die Liste hat genau einen Eintrag, und das ist kein Zufall:
#     kitty ist das einzige Terminal, das ZepOS ausliefert, und "eine
#     Anwendung je Aufgabe" ist die Regel, nach der zepos-apps
#     ausgewaehlt ist. Ein zweiter Name hier waere ein zweites Terminal.
TERMINAL_WRAPPERS = frozenset({"kitty"})

# Der Name, unter dem Hyprlands eigene Konfiguration die Super-Taste
# fuehrt. Er wird ueberall ausgeschrieben, weil "$mainMod + S" auf keiner
# Tastatur steht.
MAIN_MOD = "$mainMod"
MAIN_MOD_NAME = "SUPER"


@dataclass(frozen=True)
class Binding:
    """Eine Tastenzeile, so wie sie in der Datei steht.

    `group` und `description` kommen aus der Markierung darueber und sind
    leer, wenn keine dastand. Leer heisst NICHT "unwichtig": es heisst,
    dass diese Bindung in keiner Uebersicht erscheinen wird, und genau
    deshalb prueft die Testsuite, dass es im erzeugten Baum keine solche
    Bindung gibt.
    """

    source: str
    flags: str
    modifiers: str
    key: str
    dispatcher: str
    argument: str
    group: str = ""
    description: str = ""

    @property
    def where(self) -> str:
        """Die Taste, wie eine Fehlermeldung sie nennt: `SUPER SHIFT+B`.

        Die Form stammt aus zepos-doctor und bleibt es: sie steht in
        jedem Fund, den ein Nutzer nachstellen soll, und in den
        Zusicherungen, die diese Funde messen.
        """
        modifiers = self.modifiers.replace(MAIN_MOD, MAIN_MOD_NAME)
        return f"{modifiers}+{self.key}" if modifiers else self.key

    @property
    def chord(self) -> str:
        """Die Taste, wie ein Mensch sie liest: `SUPER + SHIFT + B`.

        Aus denselben zwei Feldern gerechnet wie `where` und nicht daneben
        gespeichert - zwei Schreibweisen derselben Taste, die getrennt
        gepflegt werden, sind der Fehler dieser ganzen Aufgabe im Kleinen.
        """
        parts = self.modifiers.replace(MAIN_MOD, MAIN_MOD_NAME).split()
        parts.append(self.key)
        return " + ".join(parts)

    @property
    def commands(self) -> list[str]:
        """Die Programme, die diese Taste startet - leer bei jedem
        Dispatcher, der kein `exec` ist."""
        return command_words(self.argument) if self.dispatcher == "exec" else []

    @property
    def runnable(self) -> str:
        """Diese Bindung von aussen ausloesen, ohne die Taste zu druecken.

        DAS IST DIE HAELFTE DER AUFGABE, DIE "zusaetzlich zu den keybinds"
        heisst. Ein `exec` ist schon eine Shell-Zeile; alles andere ist
        ein Dispatcher, und den erreicht man von aussen ueber
        `hyprctl dispatch`. Damit wird jede einzelne Bindung anklickbar,
        ohne dass irgendwo eine zweite Liste entsteht, die sagt, wie.
        """
        if self.dispatcher == "exec":
            return self.argument
        argument = f" {self.argument}" if self.argument else ""
        return f"hyprctl dispatch {self.dispatcher}{argument}"


def command_words(line: str) -> list[str]:
    """Jedes Programm, das diese Shell-Zeile aufruft, in ihrer Reihenfolge.

    Nicht nur das erste. Genau diese Verkuerzung war der Grund, aus dem
    das Bildschirmfoto-Werkzeug nie geprueft wurde: `grim -g "$(slurp)" -
    | satty -f -` nennt drei Programme, und die beiden, die der Nutzer
    vermisst hat, stehen hinten.

    Was NICHT erkannt wird, und es steht hier statt in einer Ausrede: ein
    Programmname, der aus einer Variablen kommt (`$EDITOR`), und einer,
    der in einer Zeichenkette steckt, die erst eine zweite Shell
    aufmacht (`bash -c "..."`). Beides ist in diesem Baum in keiner
    Bindung vorhanden, und eine Auswertung dafuer waere eine halbe Shell.
    """
    found: list[str] = []
    for part in COMMAND_SEPARATOR.split(line):
        part = part.strip()
        while True:
            match = ASSIGNMENT.match(part)
            if not match:
                break
            part = part[match.end():]
        if not part:
            continue
        words = part.split()
        word = words[0].strip("\"'")
        if not word or word in SHELL_WORDS:
            continue
        if not COMMAND_NAME.match(word):
            continue
        found.append(word)
        # Und das Programm hinter dem `-e` eines Terminals. Siehe
        # TERMINAL_WRAPPERS: bei `kitty -e btop` ist btop das Programm,
        # nach dem gefragt wird, und kitty nur das Fenster darum.
        if word.split("/")[-1] in TERMINAL_WRAPPERS and "-e" in words:
            after = words[words.index("-e") + 1:]
            if after:
                nested = after[0].strip("\"'")
                if nested not in SHELL_WORDS and COMMAND_NAME.match(nested):
                    found.append(nested)
    return found


def _fields(rest: str, described: bool) -> tuple[str, str, str, str] | None:
    """Modifikatoren, Taste, Dispatcher, Argumente einer bind-Zeile.

    Hyprland erlaubt das Argument wegzulassen - `bindm = $mainMod,
    mouse:272, movewindow` hat gar keines und `bind = $mainMod SHIFT, Z,
    hyprzones:editor,` ein leeres. Beide Formen kommen in diesem Projekt
    vor, also ist alles ab dem dritten Feld optional.

    `described` ist die `d`-Flagge: dann liegt zwischen Taste und
    Dispatcher noch eine Beschreibung. Dieses Projekt schreibt sie nicht
    (siehe Kopf), gelesen wird sie trotzdem - eine eigene Bindung des
    Nutzers in profile-keybinds.conf darf sie tragen, und ohne diesen
    Zweig waere dort die Beschreibung der Dispatcher.
    """
    parts = rest.split(",", 4 if described else 3)
    if len(parts) < 3:
        return None
    modifiers = parts[0].strip()
    key = parts[1].strip()
    if described:
        dispatcher = parts[3].strip() if len(parts) > 3 else ""
        argument = parts[4].strip() if len(parts) > 4 else ""
    else:
        dispatcher = parts[2].strip()
        argument = parts[3].strip() if len(parts) > 3 else ""
    if not key or not dispatcher:
        return None
    return modifiers, key, dispatcher, argument


def parse(text: str, source: str = "") -> list[Binding]:
    """Jede Tastenzeile einer Hyprland-Konfiguration, mit ihrer Markierung.

    Eine auskommentierte bind-Zeile ist keine Bindung. Das ist nicht
    selbstverstaendlich, sondern gemessen: `# bind = $mainMod, E, exec,
    thunar` stand in diesem Baum, und eine Pruefung, die sie liest,
    meldet ein Programm, das keine Taste mehr aufruft.
    """
    found: list[Binding] = []
    pending: tuple[str, str] | None = None

    for line in text.splitlines():
        marker = MARKER.match(line)
        if marker:
            pending = (marker.group(1), marker.group(2))
            continue

        bind = BIND.match(line)
        if not bind:
            # Alles andere loescht die Markierung. Sie gilt fuer die
            # NAECHSTE Zeile, und wenn die keine Bindung ist, gilt sie
            # fuer nichts - eine Markierung, die ueber eine Leerzeile
            # hinweg traegt, landet frueher oder spaeter an der falschen
            # Taste.
            pending = None
            continue

        fields = _fields(bind.group(2), "d" in bind.group(1))
        if fields is None:
            pending = None
            continue

        modifiers, key, dispatcher, argument = fields
        group, description = pending or ("", "")
        pending = None
        found.append(Binding(
            source=source, flags=bind.group(1), modifiers=modifiers,
            key=key, dispatcher=dispatcher, argument=argument,
            group=group, description=description))

    return found


def bound_commands(text: str) -> list[tuple[str, str]]:
    """(Wo es steht, welches Programm) fuer jede Taste und jede Startzeile.

    Das erste Feld ist fuer die Meldung: "SUPER+E" sagt einem Nutzer, was
    er druecken kann, um es nachzustellen; "Zeile 327" sagt es nicht.

    Startzeilen kommen dazu, weil ein `exec-once` auf ein Programm, das
    es nicht gibt, genauso leise scheitert wie eine Taste - und zwar
    einmal pro Anmeldung, ohne dass jemand etwas gedrueckt hat.
    """
    found: list[tuple[str, str]] = []
    for binding in parse(text):
        for command in binding.commands:
            found.append((binding.where, command))
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        started = EXEC_LINE.match(line)
        if started:
            for command in command_words(started.group(1)):
                found.append(("exec-once", command))
    return found


def read(configs: Iterable[Iterable[str]] | None = None,
         *, root: Path | None = None) -> list[Binding]:
    """Die Bindungen der Konfiguration, die IN PLACE liegt.

    Nicht der Vorlagen. Der Unterschied ist der ganze Zweck: plugins.py
    laesst die Bindungen eines fehlenden Plugins weg, und eine
    Uebersicht, die aus den Vorlagen entsteht, verspricht auf jeder
    Maschine ohne Plugins neun HyprZones-Tasten, die es dort nicht gibt.
    """
    directory = root if root is not None else output_root()
    found: list[Binding] = []
    for where in (configs if configs is not None else OVERVIEW_CONFIGS):
        path = directory.joinpath(*where)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Eine Datei, die es nicht gibt, ist keine Ausnahme: die
            # Profildateien entstehen erst, wenn jemand ein Profil
            # gespeichert hat, und plugins.conf gibt es nur nach einem
            # Lauf des Generators.
            continue
        found.extend(parse(text, source=path.name))
    return found


def described(bindings: Iterable[Binding]) -> list[Binding]:
    """Nur die Bindungen, die etwas ueber sich sagen.

    Eine eigene Bindung aus profile-keybinds.conf hat keine Markierung -
    save-profile schreibt heraus, was hyprctl meldet, und das sind vier
    Felder ohne Kommentar. Sie stumm zu ueberspringen ist die richtige
    Antwort fuer die Uebersicht und ausdruecklich NICHT die richtige fuer
    die ausgelieferten Dateien: dass dort keine ohne Markierung steht,
    ist eine Zusicherung der Testsuite.
    """
    return [binding for binding in bindings if binding.description]


def groups(bindings: Iterable[Binding]) -> list[tuple[str, list[Binding]]]:
    """Nach Gruppen, in der Reihenfolge ihres ersten Auftretens.

    Und nicht alphabetisch. Die Reihenfolge der Konfiguration ist eine
    getroffene Entscheidung - Anwendungen zuerst, Notfalltasten zuletzt -
    und eine alphabetische Sortierung waere eine zweite, die diese
    stillschweigend ueberstimmt.
    """
    ordered: dict[str, list[Binding]] = {}
    for binding in described(bindings):
        ordered.setdefault(binding.group, []).append(binding)
    return list(ordered.items())


def as_json(bindings: Iterable[Binding]) -> str:
    """Dieselben Bindungen fuer einen Leser, der kein Python ist.

    Die Ueberlagerung in AGS ist GJS und kann dieses Modul nicht
    importieren. Sie ruft es also auf - genauso, wie die Leiste ihre
    Module aufruft - statt Hyprlands Konfigurationssyntax ein zweites Mal
    zu verstehen. Ein zweiter Auswerter waere eine zweite Wahrheit.
    """
    return json.dumps([
        {
            "group": group,
            "bindings": [
                {
                    "chord": binding.chord,
                    "description": binding.description,
                    "run": binding.runnable,
                    "source": binding.source,
                }
                for binding in members
            ],
        }
        for group, members in groups(bindings)
    ], ensure_ascii=False)


USAGE = """usage: keybinds.py [--json]

Liest die Tastenbelegung aus der Hyprland-Konfiguration, die in place
liegt, und schreibt sie heraus. Ohne Schalter als Text, mit --json als
Liste von Gruppen - das Format, das die Oberflaeche in AGS liest.

Keine Liste in diesem Programm: was hier herauskommt, steht in
~/.config/hypr/, und die Beschreibungen stehen als `# @Gruppe: Text`
ueber den bind-Zeilen selbst."""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    if argv not in ([], ["--json"]):
        print(USAGE, file=sys.stderr)
        return 2

    bindings = read()
    if argv == ["--json"]:
        print(as_json(bindings))
        return 0

    for group, members in groups(bindings):
        print(group)
        width = max(len(binding.chord) for binding in members)
        for binding in members:
            print(f"  {binding.chord:<{width}}  {binding.description}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
