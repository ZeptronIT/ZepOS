# UI-1, Stufe 1+2: Bauteile und das erste umgestellte Fenster

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein aufrufbares Bauteil-Kit fuer die AGS-Fenster, und das
Bluetooth-Fenster als erstes darauf umgestellt.

**Architecture:** Eine neue Vorlage `ags-kit.template` erzeugt
`ags/utils/kit.ts` - Funktionen, die fertige Widgets zurueckgeben, nicht
CSS-Klassen zum Selbst-Anhaengen. Im Stylesheet tritt EINE Knopfregel mit
Varianten neben die 41 vorhandenen; ein Ratschen-Test haelt fest, dass
deren Zahl nur noch sinkt. Bluetooth wird das erste Fenster ohne eigene
Knopf-Klassen.

**Tech Stack:** AGS/Astal 4 auf GTK4, TypeScript in `.template`-Dateien
mit `{{STYLE_*}}`-Platzhaltern, Python-Vorlagenverarbeitung
(`src/template_processor.py`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-ags-gestaltungssystem-design.md`

## Global Constraints

- **Keine erzeugte Datei bearbeiten.** Nur `src/templates/*.template`
  und `src/styles/*.template`. Erzeugte Dateien tragen "DO NOT EDIT".
- **`generate_config.sh` NIE ausfuehren** - es macht `pkill -x waybar`
  und `ags quit` und trifft die Prozesse des Nutzers. Zum Pruefen
  `src/template_processor.py` direkt in ein temporaeres Verzeichnis.
- **Keine Zahl im CSS.** Alle Masse als `{{STYLE_*}}`-Platzhalter aus
  `src/sizes.py`. Radien 5 / 8 / 13, Abstaende 2 / 4 / 8 / 12 / 16 / 20 /
  24, Schrift 9 / 11 / 13 / 16 / 19 / 22.
- **Keine neue Farbe.** UI-2 ist vertagt; benutzt wird, was `brand.py`
  heute fuehrt.
- **Sichtbarer Text durch `_()`** - `tests/src/test_ags_i18n.py` prueft
  das und kennt keine Ausnahme fuer neue Dateien.
- **Kein Wächter aufweichen.** Bricht ein Test, wird der Code repariert.
- Volle Suite: `.venv/bin/python -m pytest -q` (~7 min). Waehrend der
  Nutzer am Rechner ist, ohne die Bild-Tests:
  `--ignore=tests/render --ignore=tests/lock`.
- Kommentare auf Deutsch, mit Datum und Messung.

---

### Task 1: Zwei neue Sprossen in der Groessenleiter

Knopfhoehe und Zeilenhoehe sind die einzigen neuen Masse des ganzen
Vorhabens. Sie gehoeren als Sprossen nach `src/sizes.py`, nicht als
Literale ins CSS - sonst folgen sie dem Groessenregler nicht.

**Files:**
- Modify: `src/sizes.py`
- Test: `tests/src/test_sizes.py`

**Interfaces:**
- Produces: `sizes.CONTROL_HEIGHT_PX` (int, 32 bei Faktor 1.0),
  `sizes.ROW_HEIGHT_PX` (int, 48 bei Faktor 1.0), und die Platzhalter
  `STYLE_CONTROL_HEIGHT` / `STYLE_ROW_HEIGHT`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

An das Ende von `tests/src/test_sizes.py`:

```python
def test_the_control_and_row_heights_follow_the_scale():
    """Knopf und Zeile folgen dem Groessenregler.

    GEMESSEN am 18.08.2026: das Stylesheet trug 45 Knopfregeln, und
    ihre Hoehen ergaben sich aus Polstern statt aus einem Mass. Ein
    Knopf, der bei Faktor 1.85 gleich hoch bleibt, ist dort ein Knopf
    fuer Ameisen.

    Geprueft wird die DEKLARATION, nicht eine Rechnung: sizes fuehrt
    seine Masse als Size(wert, einheit, folgt-dem-faktor), und SCALED
    ist die Zusicherung, um die es hier geht.
    """
    for name, wert in (("STYLE_CONTROL_HEIGHT", 32),
                       ("STYLE_ROW_HEIGHT", 48)):
        mass = sizes.TABLE[name]
        assert mass.base == wert, f"{name} steht auf {mass.base}"
        assert mass.unit == "px", f"{name} ist in {mass.unit}"
        assert mass.scales is True, (
            f"{name} folgt dem Groessenregler nicht")
```

Die Namen sind am 18.08.2026 nachgesehen und nicht geraten:
`sizes.TABLE` ist das Verzeichnis, ein Eintrag traegt `base`, `unit`
und `scales`. Beim ersten Schreiben dieses Plans stand hier
`sizes.scaled(...)` - eine Funktion, die es nicht gibt.

- [ ] **Step 2: Lauf, der scheitert**

Run: `.venv/bin/python -m pytest tests/src/test_sizes.py -k control_and_row -v`
Expected: FAIL mit `AttributeError: module 'sizes' has no attribute 'CONTROL_HEIGHT_PX'`

- [ ] **Step 3: Die Sprossen anlegen**

In `src/sizes.py`, bei den uebrigen Masszahlen (die Datei fuehrt sie
gruppiert - such `RADIUS_ANCHOR` und leg die neuen daneben):

In das Verzeichnis, in dem `"STYLE_MODULE_SPACING": Size(10, PX, SCALED)`
bei Zeile 1198 steht, und im selben Stil:

```python
    # Die zwei Masse, die UI-1 gebraucht hat und die es vorher nicht
    # gab. Beide SCALED, aus demselben Grund wie STYLE_MODULE_SPACING:
    # sie umschliessen Text.
    #
    # GEMESSEN am 18.08.2026: im Stylesheet standen 45 Knopfregeln, und
    # ihre Hoehen ergaben sich aus Polstern - 8+8, 9+9, 4+4 plus
    # Schriftgrad. Deshalb war kein Knopf so hoch wie der daneben, und
    # deshalb wirkte die Reihe zusammengewuerfelt.
    #
    # 32 und 48 sind nicht gewaehlt, sondern nachgerechnet: 32 =
    # Schrift 13 plus zweimal Abstand 8 plus Rand; 48 = Symbol 18 plus
    # zweimal Abstand 12 plus Rand. Sie stehen trotzdem als eigene
    # Eintraege da, weil sie an zwei Dutzend Stellen gebraucht werden
    # und eine Rechnung im CSS kein Mass ist.
    "STYLE_CONTROL_HEIGHT": Size(32, PX, SCALED),
    "STYLE_ROW_HEIGHT": Size(48, PX, SCALED),
```

- [ ] **Step 4: Lauf, der besteht**

Run: `.venv/bin/python -m pytest tests/src/test_sizes.py -q`
Expected: PASS

- [ ] **Step 5: Und die Platzhalter kommen wirklich an**

Run: `.venv/bin/python -m pytest tests/src/test_placeholders.py -q`
Expected: PASS. Dieser Test haelt fest, dass jeder Platzhalter, den eine
Vorlage benutzt, auch erzeugt wird - und umgekehrt. Zwei neue Namen
ohne Leser sind hier noch in Ordnung; sie bekommen ihn in Task 3.

- [ ] **Step 6: Commit**

```bash
git add src/sizes.py tests/src/test_sizes.py
git commit -m "feat(sizes): Sprossen fuer Knopf- und Zeilenhoehe"
```

---

### Task 2: Die Ratsche auf die Knopf-Klassen

Der Test, der das ganze Vorhaben zusammenhaelt. Er kommt VOR den
Bauteilen, damit die Zahl von Anfang an festgehalten ist - danach wuerde
niemand mehr wissen, wie viele es waren.

**Files:**
- Create: `tests/src/test_button_kit.py`

**Interfaces:**
- Produces: nichts fuer andere Tasks. Ein Waechter.

- [ ] **Step 1: Den Test schreiben**

```python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Ratsche auf den Knoepfen.

GEMELDET am 18.08.2026: "ausserdem wirken sie so billig durch die button
wie sie dargestellt sind weisst du was ich meine".

GEMESSEN am selben Tag in src/templates/ags-style.template: 45
Knopfregeln in 41 verschiedenen Klassen, und keine einzige gemeinsame.
Jedes Fenster hatte sich seine Knoepfe selbst erfunden.

WARUM EINE RATSCHE UND NICHT "GENAU EINE": UI-1 stellt zwoelf Fenster
um, und das geht nicht in einem Zug (siehe Abschnitt 6 der
Spezifikation). Ein Test, der sofort genau eine verlangt, waere von der
ersten bis zur letzten Stufe rot - und ein Test, der monatelang rot ist,
ist ein Test, den jemand abschaltet.

Die Ratsche laesst die Zahl nur SINKEN. Wer eine Klasse hinzufuegt,
faellt sofort auf; wer eine entfernt, muss die Zahl hier senken und
sieht dabei, wie weit es noch ist. Die letzte Stufe von UI-1 setzt sie
auf 1.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STIL = ROOT / "src" / "templates" / "ags-style.template"

# Am 18.08.2026 gezaehlt, bevor irgendetwas umgestellt war.
AUSGANGSZAHL = 41

# Die Zahl, die HEUTE gilt. Sie darf nur kleiner werden, und wer sie
# senkt, schreibt dazu, welches Fenster er umgestellt hat.
#
#   41  18.08.2026  Ausgangszustand
ERLAUBT = 41


def _knopfklassen(text: str) -> set[str]:
    """Jede Klasse, deren Name auf einen Knopf hindeutet.

    Ueber den NAMEN und nicht ueber den Inhalt: eine Regel, die zufaellig
    wie ein Knopf aussieht, ist keine; eine, die -btn heisst, ist eine -
    und genau die Benennung ist es, die dieses Projekt durchgehalten hat.
    """
    return set(re.findall(r"^\.([a-z0-9-]*btn[a-z0-9-]*)", text, re.M))


def test_no_window_invents_another_button():
    gefunden = _knopfklassen(STIL.read_text(encoding="utf-8"))
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
    """Der Selbsttest. Ein Zaehler, der nichts findet, zaehlt auch nichts."""
    beispiel = ".a-btn {\n  color: red;\n}\n.b {\n  color: blue;\n}\n"
    assert _knopfklassen(beispiel) == {"a-btn"}
```

- [ ] **Step 2: Lauf**

Run: `.venv/bin/python -m pytest tests/src/test_button_kit.py -q`
Expected: PASS (3 Tests). Er haelt den Ausgangszustand fest, er
verlangt noch nichts.

- [ ] **Step 3: Die Ratsche gegen eine Verfaelschung pruefen**

Fuege in `src/templates/ags-style.template` voruebergehend eine Zeile
`.probe-btn {` mit `}` an, lauf den Test, sieh ihn rot werden, und
nimm sie wieder heraus.

Run: `.venv/bin/python -m pytest tests/src/test_button_kit.py -q`
Expected: erst FAIL mit "42 Knopf-Klassen, erlaubt sind 41", nach dem
Zuruecknehmen PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/src/test_button_kit.py
git commit -m "test(UI-1): Ratsche auf die Knopf-Klassen, Ausgangswert 41"
```

---

### Task 3: Die Bauteil-Vorlage

**Files:**
- Create: `src/templates/ags-kit.template`
- Modify: `src/generate_config.sh` (Erzeugerfall)
- Modify: `tests/src/test_inventory.py:342` (Vorlagenzahl 82 -> 83)
- Test: `tests/src/test_ags_kit.py` (neu)

**Interfaces:**
- Consumes: `STYLE_CONTROL_HEIGHT`, `STYLE_ROW_HEIGHT` aus Task 1.
- Produces: `ags/utils/kit.ts` mit
  `zepButton(label: string, rolle: ZepRolle, aktion: () => void): Gtk.Button`,
  `ZepRolle = "voll" | "umrandet" | "still" | "kritisch"`,
  `zepRow(opts: {symbol: string, titel: string, unterzeile?: string, ende?: Gtk.Widget}): Gtk.Box`,
  `zepToggle(an: boolean, aktion: (an: boolean) => void): Gtk.Widget`,
  `zepSectionLabel(text: string): Gtk.Label`,
  `zepDivider(): Gtk.Widget`.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`tests/src/test_ags_kit.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Bauteil-Kit: was es exportiert und was es NICHT tut."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "src" / "templates" / "ags-kit.template"

ERWARTETE_BAUTEILE = (
    "zepButton", "zepRow", "zepToggle", "zepSectionLabel", "zepDivider",
)


def test_the_kit_exports_every_part():
    text = KIT.read_text(encoding="utf-8")
    fehlend = [n for n in ERWARTETE_BAUTEILE
               if not re.search(rf"^export function {n}\b", text, re.M)]
    assert fehlend == [], f"das Kit exportiert nicht: {fehlend}"


def test_the_kit_carries_no_bare_numbers():
    """Jedes Mass als Platzhalter.

    Ein Bauteil mit einer festen 32 folgt dem Groessenregler nicht - und
    es waere genau die Sorte Zahl, aus der die 41 Knopf-Klassen
    entstanden sind.
    """
    text = KIT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("//"))
    nackt = re.findall(r"(?:padding|margin|height|width|font-size|"
                       r"border-radius)\s*[:=]\s*[\"']?\d+", rumpf)
    assert nackt == [], f"nackte Masse im Kit: {nackt}"


def test_the_kit_defines_no_colour_of_its_own():
    """UI-2 ist vertagt - das Kit fuehrt keine neue Farbe ein."""
    text = KIT.read_text(encoding="utf-8")
    rumpf = "\n".join(z for z in text.splitlines()
                      if not z.lstrip().startswith("//"))
    assert not re.search(r"#[0-9a-fA-F]{6}\b", rumpf), (
        "eine Hexfarbe im Kit - Farben kommen aus brand.py")
```

- [ ] **Step 2: Lauf, der scheitert**

Run: `.venv/bin/python -m pytest tests/src/test_ags_kit.py -q`
Expected: FAIL mit `FileNotFoundError` auf `ags-kit.template`

- [ ] **Step 3: Die Vorlage schreiben**

`src/templates/ags-kit.template`. Der Kopf traegt die Begruendung, der
Rumpf die fuenf Bauteile:

```typescript
// DIE BAUTEILE DER ZEPOS-FENSTER
//
// Erzeugt nach ags/utils/kit.ts. Wer ein Fenster baut, ruft von hier -
// er baut keinen Gtk.Button und haengt keine eigene Klasse dran.
//
// WARUM FUNKTIONEN UND NICHT NUR CSS-KLASSEN
//     GEMESSEN am 18.08.2026: ags-style.template trug 45 Knopfregeln in
//     41 Klassen, ohne eine einzige gemeinsame. Es gab keine Regel, die
//     das verboten haette - es gab nur keine, die es leicht gemacht
//     haette. Eine Klasse, an die man sich halten SOLL, ist schwaecher
//     als eine Funktion, die man aufruft; die eine ist eine Bitte, die
//     andere eine Schnittstelle.
//
// WAS HIER NICHT HINEINGEHOERT: alles, was ein Fenster besonders macht.
// Das Kit kennt Knopf, Zeile, Schalter, Abschnittsmarke und Trenner -
// mehr nicht. Ein Bauteil, das nur ein Fenster braucht, gehoert in
// dieses Fenster.
import { Gtk } from "ags/gtk4"

export type ZepRolle = "voll" | "umrandet" | "still" | "kritisch"

// Ein Knopf. EINE Hoehe, EIN Radius, vier Rollen.
//
// Die Rolle steht in der Klasse und nicht im Aufruf des Aussehens: das
// Stylesheet entscheidet, wie "kritisch" aussieht, nicht diese Datei.
export function zepButton(
  label: string,
  rolle: ZepRolle,
  aktion: () => void,
): Gtk.Button {
  const knopf = new Gtk.Button({ can_focus: true })
  knopf.set_child(new Gtk.Label({ label }))
  knopf.add_css_class("zep-btn")
  knopf.add_css_class(`zep-btn-${rolle}`)
  knopf.connect("clicked", aktion)
  return knopf
}

// Eine Zeile: Symbol, Titel, optionale Nebenzeile, optionales Ende.
//
// Der Titel kuerzt. Das ist keine Kosmetik - am 17.08.2026 hat eine
// Beschriftung ohne Kuerzen das Netzfenster auf 660 Punkte
// aufgeblasen, weil die Mindestbreite einer solchen Beschriftung ihre
// GANZE Zeile ist.
export function zepRow(opts: {
  symbol: string
  titel: string
  unterzeile?: string
  ende?: Gtk.Widget
}): Gtk.Box {
  const zeile = new Gtk.Box({ spacing: 0 })
  zeile.add_css_class("zep-row")

  const symbol = new Gtk.Label({ label: opts.symbol })
  symbol.add_css_class("zep-row-icon")
  zeile.append(symbol)

  const texte = new Gtk.Box({
    orientation: Gtk.Orientation.VERTICAL,
    spacing: 0,
  })
  texte.add_css_class("zep-row-texts")

  const titel = new Gtk.Label({ label: opts.titel, xalign: 0 })
  titel.add_css_class("zep-row-title")
  titel.set_ellipsize(3)  // Pango.EllipsizeMode.END
  texte.append(titel)

  if (opts.unterzeile) {
    const unter = new Gtk.Label({ label: opts.unterzeile, xalign: 0 })
    unter.add_css_class("zep-row-sub")
    unter.set_ellipsize(3)
    texte.append(unter)
  }
  zeile.append(texte)

  const luecke = new Gtk.Box({ hexpand: true })
  zeile.append(luecke)

  if (opts.ende) zeile.append(opts.ende)
  return zeile
}

// Der Schalter. Gtk.Switch und kein selbstgebauter Knopf: er bringt
// seine Barrierefreiheit und seine Tastaturbedienung mit.
export function zepToggle(
  an: boolean,
  aktion: (an: boolean) => void,
): Gtk.Widget {
  const schalter = new Gtk.Switch({ active: an, valign: Gtk.Align.CENTER })
  schalter.add_css_class("zep-toggle")
  schalter.connect("notify::active", () => aktion(schalter.get_active()))
  return schalter
}

// Die Marke ueber einer Gruppe. Klein, gedaempft, gesperrt gesetzt.
export function zepSectionLabel(text: string): Gtk.Label {
  const marke = new Gtk.Label({ label: text, xalign: 0 })
  marke.add_css_class("zep-section")
  return marke
}

// Der Trenner. Ein Gtk.Separator und keine 1-px-Box: er meldet sich
// den Hilfsmitteln als Trenner.
export function zepDivider(): Gtk.Widget {
  const trenner = new Gtk.Separator({
    orientation: Gtk.Orientation.HORIZONTAL,
  })
  trenner.add_css_class("zep-divider")
  return trenner
}
```

- [ ] **Step 4: Den Erzeugerfall eintragen**

In `src/generate_config.sh`, neben `ags-overlay-utils)`:

```bash
    # Das Bauteil-Kit. Neben overlay.ts und i18n.ts der dritte Baustein
    # unter ags/utils/ - kein Fenster, sondern das, woraus Fenster
    # gebaut werden.
    ags-kit)
        CONFIG_DIR="$ZEPOS_OUTPUT_ROOT/ags/utils"
        CONFIG_FILE="kit.ts"
        ;;
```

- [ ] **Step 5: Die Vorlagenzahl nachziehen**

In `tests/src/test_inventory.py`, am Ende des Docstrings von
`test_template_count_is_seventy_seven` und in der Zusicherung:

```python
    83 STATT 82, am 18.08.2026: ags-kit. Der Nutzer hat gemeldet, die
    Fenster wirkten "zusammengebastelt" und die Knoepfe "billig", und
    das war zu messen: 45 Knopfregeln in 41 Klassen, keine gemeinsame.
    Die neue Vorlage erzeugt ags/utils/kit.ts - Funktionen, die fertige
    Widgets zurueckgeben, damit ein Fenster gar nicht erst in die Lage
    kommt, sich einen eigenen Knopf zu bauen.
    """
    assert len(list((SRC / "templates").glob("*.template"))) == 83
```

- [ ] **Step 6: Laufen lassen**

Run: `.venv/bin/python -m pytest tests/src/test_ags_kit.py tests/src/test_inventory.py tests/src/test_placeholders.py -q`
Expected: PASS

- [ ] **Step 7: Und die Vorlage muss sich wirklich erzeugen lassen**

Run:
```bash
.venv/bin/python -c "
import sys, tempfile, pathlib; sys.path.insert(0,'src')
import template_processor as tp
ziel = pathlib.Path(tempfile.mkdtemp()) / 'kit.ts'
tp.process(pathlib.Path('src/templates/ags-kit.template'), ziel)
print(ziel.read_text()[:200])
"
```
Expected: TypeScript ohne uebrig gebliebene `{{...}}`. Passt die
Aufrufform von `template_processor` nicht, lies ihren Kopf - sie ist die
Stelle, an der `generate_config.sh` selbst hineingeht.

- [ ] **Step 8: Commit**

```bash
git add src/templates/ags-kit.template src/generate_config.sh \
        tests/src/test_ags_kit.py tests/src/test_inventory.py
git commit -m "feat(UI-1): das Bauteil-Kit als aufrufbare Funktionen"
```

---

### Task 4: Die eine Knopfregel im Stylesheet

**Files:**
- Modify: `src/templates/ags-style.template`
- Test: `tests/src/test_button_kit.py` (erweitern)

**Interfaces:**
- Consumes: `STYLE_CONTROL_HEIGHT`, `STYLE_ROW_HEIGHT` (Task 1),
  die Klassennamen aus Task 3.
- Produces: `.zep-btn` mit vier Rollen, `.zep-row`, `.zep-toggle`,
  `.zep-section`, `.zep-divider`.

- [ ] **Step 1: Den Test erweitern**

An `tests/src/test_button_kit.py` anhaengen:

```python
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
```

- [ ] **Step 2: Lauf, der scheitert**

Run: `.venv/bin/python -m pytest tests/src/test_button_kit.py -q`
Expected: FAIL mit "die gemeinsame Knopfregel fehlt"

- [ ] **Step 3: Die Regel schreiben**

In `src/templates/ags-style.template`, VOR den 41 alten Regeln (damit
beim Lesen klar ist, was die Zukunft ist):

```scss
// ── DIE BAUTEILE ────────────────────────────────────────────────────
//
// Was hier steht, gehoert zu ags-kit.template. Die Regeln darunter mit
// eigenen Praefixen (.cc-, .net-, .vpn- …) sind der Bestand, der nach
// und nach hierher wandert - siehe die Ratsche in
// tests/src/test_button_kit.py.

.zep-btn {
  min-height: {{STYLE_CONTROL_HEIGHT}};
  padding: 0 {{STYLE_SPACE_16}};
  border-radius: {{STYLE_RADIUS_CONTROL}};
  font-size: {{STYLE_FONT_BODY}};
  border: 1px solid transparent;
  transition: background-color {{STYLE_MOTION_INSTANT}} {{STYLE_MOTION_CURVE}},
              border-color {{STYLE_MOTION_INSTANT}} {{STYLE_MOTION_CURVE}};
}

// Die Hauptsache je Fenster. Genau EINE je Ansicht - zwei volle Knoepfe
// nebeneinander heissen, dass keiner die Hauptsache ist.
.zep-btn-voll {
  background: $accent;
  color: $bg;
  font-weight: 500;

  &:hover { background: $control-accent; }
}

.zep-btn-umrandet {
  background: rgba($surface, 0.55);
  border-color: $border;
  color: $text;

  &:hover { background: rgba($surface, 0.75); }
}

.zep-btn-still {
  background: transparent;
  color: $subtext;

  &:hover { background: rgba($surface, 0.4); color: $text; }
}

.zep-btn-kritisch {
  background: rgba($red, 0.14);
  border-color: rgba($red, 0.5);
  color: $red;

  &:hover { background: rgba($red, 0.24); }
}

.zep-btn:disabled {
  background: rgba($surface, 0.3);
  border-color: rgba($border, 0.5);
  color: $subtext;
}

.zep-row {
  min-height: {{STYLE_ROW_HEIGHT}};
  padding: 0 {{STYLE_SPACE_12}};
  border-radius: {{STYLE_RADIUS_CARD}};

  &:hover { background: $item-hover; }
}

.zep-row-icon { font-size: {{STYLE_ICON_CAPTION}}; color: $subtext; }
.zep-row-texts { margin-left: {{STYLE_SPACE_12}}; }
.zep-row-title { font-size: {{STYLE_FONT_BODY}}; color: $text; }
.zep-row-sub { font-size: {{STYLE_FONT_CAPTION}}; color: $subtext; }

.zep-section {
  font-size: {{STYLE_FONT_CAPTION}};
  color: $subtext;
  margin: {{STYLE_SPACE_8}} 0 {{STYLE_SPACE_4}} 0;
}

.zep-divider { background: $border; margin: {{STYLE_SPACE_8}} 0; }
```

**Die Farbnamen sind am 18.08.2026 gegen die Datei geprueft** und
kommen alle darin vor: `$accent`, `$control-accent`, `$surface`,
`$border`, `$text`, `$subtext`, `$red`, `$bg`, `$item-hover`.

Beim ersten Schreiben dieses Plans standen hier `$critical`,
`$inactive` und `$overlay-item-hover` - drei Namen, die es NICHT gibt.
Das Stylesheet fuehrt genau 24 Farbnamen; `grep -oE "\\$[a-z][a-z0-9-]*"`
listet sie. Einen neuen einzufuehren waere UI-2, und die ist vertagt.

- [ ] **Step 4: Lauf, der besteht**

Run: `.venv/bin/python -m pytest tests/src/test_button_kit.py tests/src/test_design.py -q`
Expected: PASS. `test_design.py` prueft die Sprossen im Stylesheet -
faellt es, steht dort eine Zahl statt einer Sprosse.

- [ ] **Step 5: Commit**

```bash
git add src/templates/ags-style.template tests/src/test_button_kit.py
git commit -m "feat(UI-1): eine Knopfregel mit vier Rollen"
```

---

### Task 5: Bluetooth auf die Bauteile

Das erste Fenster. Bluetooth, weil es die Meldung ausgeloest hat und
weil es alle fuenf Bauteile braucht.

**Files:**
- Modify: `src/templates/ags-bluetooth.template`
- Modify: `src/templates/ags-style.template` (die bt-Klassen entfernen)
- Modify: `tests/src/test_button_kit.py` (Ratsche senken)

**Interfaces:**
- Consumes: alle Bauteile aus Task 3, die Regeln aus Task 4.
- Produces: nichts. Ein Fenster.

- [ ] **Step 1: Zaehlen, was Bluetooth heute an eigenen Knoepfen hat**

Run: `grep -oE "^\.bt-[a-z-]*btn[a-z-]*" src/templates/ags-style.template | sort -u`
Notier die Zahl - um sie senkt sich die Ratsche.

- [ ] **Step 2: Die Ratsche schon senken, damit der Test rot wird**

In `tests/src/test_button_kit.py`, `ERLAUBT` um die gezaehlte Zahl
senken und die Zeile in die Liste im Kommentar eintragen:

```python
#   41  18.08.2026  Ausgangszustand
#   40  18.08.2026  Bluetooth auf zepButton
ERLAUBT = 40
```

- [ ] **Step 3: Lauf, der scheitert**

Run: `.venv/bin/python -m pytest tests/src/test_button_kit.py -q`
Expected: FAIL mit "41 Knopf-Klassen, erlaubt sind 40"

- [ ] **Step 4: Das Fenster umstellen**

In `src/templates/ags-bluetooth.template`:

```typescript
import { zepButton, zepRow, zepToggle, zepSectionLabel, zepDivider }
  from "../utils/kit"
```

Dann jeden `new Gtk.Button` durch `zepButton(...)` ersetzen, jede
Geraetezeile durch `zepRow(...)`, den Ein-/Ausschalter durch
`zepToggle(...)`, die Marke "GERAETE" durch `zepSectionLabel(_("DEVICES"))`.

Die Rollen: "Geraete suchen" ist `voll` (die Hauptsache), "Neu lesen"
und "Verbinden"/"Trennen" sind `umrandet`, "Blueman oeffnen" ist
`still`. Es gibt keinen `kritisch` in diesem Fenster.

**Der Zustandskopf** ersetzt `.bt-current`: statt eines Kastens mit
linkem Akzentstreifen eine Zeile aus Punkt, Ueberschrift, Nebenzeile
und `zepToggle` rechts. Die Beschriftungen bleiben, wie sie sind -
`_("Bluetooth is on")` und die uebrigen sind schon im Katalog.

- [ ] **Step 5: Die alten Klassen entfernen**

Aus `src/templates/ags-style.template` alle `.bt-*`-Regeln loeschen,
die jetzt niemand mehr benutzt. Pruef jede einzeln:

Run: `grep -c "bt-power-btn" src/templates/ags-bluetooth.template`
Expected: 0, bevor die Regel faellt.

- [ ] **Step 6: Laufen lassen**

Run: `.venv/bin/python -m pytest tests/src/test_button_kit.py tests/src/test_overlay_windows.py tests/src/test_ags_i18n.py -q`
Expected: PASS

- [ ] **Step 7: Und ein Bild, weil der Quelltext das nicht beantwortet**

Run: `./tests/render/shoot.py --out /tmp/ui1-bluetooth`
Dann `session.request("bluetooth")` und die Aufnahme ansehen.

**ACHTUNG:** dieser Lauf oeffnet ein Fenster in der Sitzung des
Nutzers. Nur ausfuehren, wenn er nicht am Rechner ist, oder vorher
fragen.

Expected: das Fenster zeigt vier Knoepfe gleicher Hoehe, gleicher
Rundung, gleicher Schrift. Der Zustandskopf traegt den Schalter.

- [ ] **Step 8: Commit**

```bash
git add src/templates/ags-bluetooth.template \
        src/templates/ags-style.template tests/src/test_button_kit.py
git commit -m "feat(UI-1): Bluetooth auf die Bauteile, Ratsche auf 40"
```

---

## Danach

Der Baum ist hier lieferbar: das Kit steht, ein Fenster benutzt es, die
Ratsche haelt fest, dass es nicht wieder auseinanderlaeuft. Die
naechsten Stufen - die Schale, die uebrigen Panels, die Breitenleiter -
bekommen ihre eigenen Plaene, wenn dieser durch ist. Ihre Reihenfolge
steht in Abschnitt 6 der Spezifikation.
