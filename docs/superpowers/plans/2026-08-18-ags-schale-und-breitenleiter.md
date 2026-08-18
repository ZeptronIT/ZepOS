# Die Schale und die Breitenleiter - Umsetzungsplan

> **Fuer arbeitende Agenten:** PFLICHT-UNTERFERTIGKEIT: superpowers:subagent-driven-development.
> Schritte tragen Kaestchen (`- [ ]`).

**Ziel:** Stufe 3 und Stufe 5 aus UI-1 - das Kontrollzentrum wird eine Schale
mit Seitenleiste, Netzwerk/Bluetooth/VPN werden Seiten darin, und die
geratenen Fensterbreiten weichen drei gemessenen Sprossen.

**Aufbau:** Erst die Sprossen (die Schale braucht eine), dann die tote
Groessen-Oberflaeche weg, dann die Schale selbst, dann die drei Fenster
Stueck fuer Stueck hinein.

**Technik:** AGS/Astal 4 auf GTK4, TypeScript-Vorlagen unter
`src/templates/`, Python-Erzeuger unter `src/`.

**Spezifikation:** `docs/superpowers/specs/2026-08-18-ags-gestaltungssystem-design.md`

---

## Globale Vorgaben

Jede Aufgabe erbt diese Liste. Ein Verstoss ist ein Fehler, kein Geschmack.

- **NIEMALS** `tests/render/`, `tests/lock/`, `tests/render/shoot.py` oder
  `iso/test-boot.py` ausfuehren. Sie oeffnen Fenster auf dem Bildschirm des
  Nutzers, der daran arbeitet. Der sichere Lauf ist
  `.venv/bin/python -m pytest -q --ignore=tests/render --ignore=tests/lock`,
  **im Vordergrund**, rund sechseinhalb Minuten.
- **NIEMALS** `generate_config.sh` ausfuehren - es beendet Waybar und AGS des
  Nutzers. Zum Erzeugungstest `src/template_processor.py` in ein temporaeres
  Verzeichnis, wie `tests/src/test_filemanager.py._render()` es vormacht.
- **NIEMALS** `git checkout`/`restore`/`reset`/`clean`/`stash`, **niemals**
  `git push`, **niemals** `git add -A` oder `git add .`.
- **NIEMALS** unter `/home/lmarzoll/.config/iconmanager` schreiben, **niemals**
  `/dev/sda` anfassen.
- **NIEMALS** einen Waechter aufweichen, damit Code durchgeht. Faellt ein Test,
  ist der Code falsch. Einzige Ausnahme: eine Ratschenzahl darf **sinken**.
- **`{{STYLE_*}}` wird AUCH IN KOMMENTAREN ersetzt.** In Kommentaren den
  blossen Namen ohne geschweifte Klammern schreiben.
- **Erzeugte Dateien werden nie bearbeitet**, nur Vorlagen unter
  `src/templates/` und `src/styles/`.
- Jeder neue Knopf kommt aus `ags-kit.template`, nie als eigene CSS-Klasse.
- Kommentare auf Deutsch, mit Datum und der Messung, auf der sie beruhen.
- Bei Abweichung zwischen Plan und Baum gilt **der Baum**, und die Abweichung
  gehoert in den Bericht.

---

## Die Messungen, auf denen dieser Plan steht

Alle am 18.08.2026 aus dem Baum gelesen, nicht geschaetzt.

**Die heutigen Fensterbreiten** (`const WIN_WIDTH` im jeweiligen Vorlagenkopf,
je aus Inhalt + Polsterung + Rahmen + Bildlaufleiste hergeleitet):

| Fenster | Vorlage | px |
|---|---|---|
| Meldungen | `ags-notifications.template:539` (`CENTER_WIDTH`) | 420 |
| Akku | `ags-battery.template:63` | 436 |
| Stil-Editor | `ags-style-editor.template:49` | 474 |
| VPN | `ags-vpn.template:39` | 476 |
| Kalender | `ags-calendar.template:72` | 496 |
| Bluetooth | `ags-bluetooth.template:157` | 500 |
| Netzwerk | `ags-network.template:171` | 500 |
| Kontrollzentrum | `ags-control-center.template:592` (`width:`) | 520 |
| Datentraeger | `ags-disk.template:39` | 556 |
| Hintergruende | `ags-wallpaper.template:45` | 616 |
| VPN-Einstellungen | `ags-vpn-settings.template:55` | 642 |
| Kuerzel | `ags-shortcuts.template:105` | 1076 |

**Der Deckel:** `MEASURE_MODAL_SHARE = 0.5` in `src/sizes.py:715`. Auf einem
1920er Schirm sind das 960 - der Grund, warum die Kuerzel 1076 wollen und 960
bekommen.

**Die tote Groessen-Kette** (geprueft mit `grep -rl` gegen `src/templates/`
UND `src/styles/`, beide Male null Treffer):

```
ags-style-editor.template (Reiter "widgets", 10 Fenster x 4 Aufloesungen)
  -> user-settings.json: widget_sizes.<breite>.<widget>.{width,height}
  -> style_definition.py:_monitor_style_variables()
  -> {{STYLE_EWW_WINDOW_<WIDGET>_MON<n>}}  ->  NULL LESER
  -> {{STYLE_EWW_SCROLL_<WIDGET>_MON<n>}}  ->  NULL LESER
```

Der Nutzer kann vierzig Zahlen einstellen, sie werden gespeichert, und kein
Fenster liest eine davon. Das `EWW` im Namen ist der Rest einer Leiste, die
dieses Projekt nicht mehr hat.

---

## Zwei Entscheidungen, die vor der ersten Aufgabe fallen

**Entscheidung 1: Die Sprossen kommen aus den Messungen, nicht aus der
Spezifikation.** Abschnitt 2.5 der Spezifikation nennt S=420/M=560/L=720/XL=880.
Gegen die Tabelle oben gehalten schneidet das: der Akku misst 436 und der
Kalender 496, beide verloeren an einer 420er Sprosse Inhalt - genau der Fehler,
den `ags-vpn.template:18-38` fuer 420 bereits einmal ausgemessen hat. Die
Sprossen wurden geschrieben, bevor die Fenster vermessen waren.
**Es gilt der Baum.** Aufgerundet auf die naechste Sprosse, kein Fenster
verliert etwas:

| Sprosse | px | traegt |
|---|---|---|
| **S** | 500 | Meldungen 420, Akku 436, Stil-Editor 474, Kalender 496 |
| **M** | 660 | Datentraeger 556, Hintergruende 616, VPN-Einstellungen 642 |
| **L** | 880 | Kuerzel (heute 1076), die Schale |

**Drei Sprossen, nicht vier**: die Spezifikation trennt L=720 und XL=880, aber
nach dem Umzug von Netzwerk, Bluetooth und VPN in die Schale steht auf 720
niemand mehr. Eine Sprosse ohne Bewohner ist eine geratene Zahl mit besserem
Namen.

**Entscheidung 2: Die Kuerzel bleiben ein Aufklappfenster.** Die Spezifikation
widerspricht sich - 2.4 zaehlt sie unter "was Panel bleibt", 2.5 nennt sie
"als Seite der Schale". Die Seitenleiste in 2.2 hat keinen Kuerzel-Eintrag,
also ist 2.4 die Aussage, die zum Rest passt. Das eigentliche Problem - 1076
gewollt, 960 bekommen - loest der Zweispalter auf Sprosse L, nicht der Umzug.

Beides gehoert ins Register, bevor Aufgabe 1 losgeht.

---

## Dateien

**Neu:**
- `tests/src/test_breitenleiter.py` - der Waechter der Sprossen
- `tests/src/test_schale.py` - der Waechter der Schale

**Geaendert:**
- `src/sizes.py` - die drei Sprossen
- `src/style_definition.py` - die tote Groessen-Kette faellt
- `src/user_settings.py` - dito
- `src/templates/ags-kit.template` - `zepSidebar`, `zepNavItem`, `zepStateHeader`
- `src/templates/ags-style.template` - die Regeln dazu
- `src/templates/ags-overlay-utils.template` - `createShellWindow()`
- `src/templates/ags-control-center.template` - wird die Schale
- `src/templates/ags-network.template` - wird eine Seite
- `src/templates/ags-bluetooth.template` - wird eine Seite
- `src/templates/ags-vpn.template` - wird eine Seite
- `src/templates/ags-shortcuts.template` - Zweispalter, Sprosse L
- `src/templates/ags-battery.template`, `ags-calendar.template`,
  `ags-disk.template`, `ags-wallpaper.template`,
  `ags-notifications.template`, `ags-style-editor.template`,
  `ags-vpn-settings.template` - nennen ihre Sprosse
- `src/templates/ags-config.template` - Fensterverzeichnis und Anfragen
- `src/templates/ags-bar.template` - die Leiste oeffnet die Schale auf der Seite
- `tests/src/test_style_definition.py`, `tests/src/test_user_settings.py` -
  die Behauptungen ueber die tote Kette fallen mit ihr

---

# STUFE 5 - DIE BREITENLEITER

Zuerst, obwohl die Spezifikation sie zuletzt nennt: die Schale braucht eine
Sprosse, und eine Sprosse zu erfinden, waehrend man ein Fenster baut, ist
genau das Raten, das die Leiter abschaffen soll. Die Inhalte stehen seit
Stufe 4, die Voraussetzung der Spezifikation ist damit erfuellt.

---

### Aufgabe 1: Die drei Sprossen

**Dateien:**
- Aendern: `src/sizes.py` (neben `MEASURE_MODAL_SHARE`, Zeile ~715)
- Test: `tests/src/test_breitenleiter.py` (neu)

**Schnittstellen:**
- Liefert: `MODAL_WIDTHS: dict[str, int]` mit den Schluesseln `"S"`, `"M"`,
  `"L"` und `MODAL_WIDTH(sprosse: str) -> int`. Alle spaeteren Aufgaben lesen
  ausschliesslich darueber.

- [ ] **Schritt 1: Den fallenden Test schreiben**

`tests/src/test_breitenleiter.py`:

```python
"""Die Breitenleiter - drei Sprossen statt zwoelf gegriffener Zahlen.

Der Waechter prueft nicht, dass die Zahlen SCHOEN sind, sondern dass
keine von ihnen ein Fenster beschneidet und keine ueber den Deckel
laeuft. Beides ist am 18.08.2026 einzeln ausgemessen worden; die
Messungen stehen im Plan.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import sizes


# Was jedes Fenster am 18.08.2026 tatsaechlich brauchte, aus seinem
# eigenen WIN_WIDTH gelesen. KEINE dieser Zahlen darf durch die Leiter
# kleiner werden - ein Fenster, das seine Zahl nicht mehr bekommt,
# verliert Inhalt hinter der Kante, und das ist der Fehler, den
# ags-vpn.template im Kopf beschreibt.
GEMESSEN = {
    "notifications": 420,
    "battery": 436,
    "style_settings": 474,
    "calendar": 496,
    "disk": 556,
    "wallpaper": 616,
    "vpn_settings": 642,
}


def test_es_gibt_genau_drei_sprossen():
    assert sorted(sizes.MODAL_WIDTHS) == ["L", "M", "S"]


def test_keine_sprosse_beschneidet_ihr_engstes_fenster():
    for name, gemessen in GEMESSEN.items():
        passend = min(w for w in sizes.MODAL_WIDTHS.values() if w >= gemessen)
        assert passend >= gemessen, (
            f"{name} misst {gemessen}, bekaeme aber nur {passend}")


def test_die_groesste_sprosse_bleibt_unter_dem_deckel():
    # Der Deckel greift auf dem schmalsten unterstuetzten Schirm, 1920.
    deckel = int(1920 * sizes.MEASURE_MODAL_SHARE)
    assert max(sizes.MODAL_WIDTHS.values()) <= deckel


def test_die_sprossen_steigen():
    werte = [sizes.MODAL_WIDTHS[k] for k in ("S", "M", "L")]
    assert werte == sorted(set(werte))


def test_eine_unbekannte_sprosse_ist_ein_fehler_und_keine_null():
    # Ein Tippfehler im Fenster darf nicht in einer Breite 0 enden.
    try:
        sizes.MODAL_WIDTH("XL")
    except KeyError:
        return
    raise AssertionError("MODAL_WIDTH schluckt eine unbekannte Sprosse")
```

- [ ] **Schritt 2: Den Test laufen lassen und das Fallen sehen**

```bash
.venv/bin/python -m pytest tests/src/test_breitenleiter.py -q
```
Erwartet: `AttributeError: module 'sizes' has no attribute 'MODAL_WIDTHS'`

- [ ] **Schritt 3: Die Sprossen setzen**

In `src/sizes.py`, unmittelbar unter `MEASURE_MODAL_SHARE`:

```python
# =====================================================================
# DIE BREITENLEITER - drei Sprossen fuer alle Aufklappfenster
# =====================================================================
#
# WARUM ES SIE GIBT
#     Am 18.08.2026 trugen zwoelf Fenster zwoelf einzeln gegriffene
#     Breiten, von 420 bis 1076. Jede war fuer sich richtig - sie kamen
#     aus echten Messungen, siehe die Kommentarkoepfe von
#     ags-vpn.template und ags-calendar.template -, aber zusammen ergaben
#     sie kein Bild: zwei Fenster mit fast demselben Inhalt standen 24
#     Punkte verschieden breit nebeneinander.
#
# WIE DIE ZAHLEN ENTSTANDEN SIND
#     Nicht gewaehlt, sondern aufgerundet. Jedes Fenster brachte seine
#     gemessene Breite mit, und jede Sprosse ist die naechste runde Zahl
#     ueber dem breitesten Fenster, das sie traegt:
#
#         S   500   Meldungen 420, Akku 436, Stil-Editor 474,
#                   Kalender 496
#         M   660   Datentraeger 556, Hintergruende 616,
#                   VPN-Einstellungen 642
#         L   880   Kuerzel (heute 1076, zweispaltig), die Schale
#
#     DREI und nicht vier: die Spezifikation trennt L=720 und XL=880.
#     Nachdem Netzwerk, Bluetooth und VPN in die Schale gezogen sind,
#     wohnt auf 720 niemand mehr, und eine leere Sprosse ist eine
#     geratene Zahl mit besserem Namen.
#
# DER DECKEL BLEIBT
#     MEASURE_MODAL_SHARE deckelt weiterhin auf die halbe Schirmbreite.
#     Auf 1920 sind das 960, L passt also mit 80 Punkten Luft. Genau
#     dieser Deckel ist der Grund, warum die Kuerzel bisher 1076 wollten
#     und 960 bekamen.
MODAL_WIDTHS = {
    "S": 500,
    "M": 660,
    "L": 880,
}


def MODAL_WIDTH(sprosse):
    """Die Breite einer Sprosse, in Punkten.

    Wirft bei einem unbekannten Namen, statt eine Ersatzzahl zu
    erfinden - ein Tippfehler im Fenster soll auffallen, solange er
    noch billig ist, und nicht als 0 Punkte breites Fenster enden.
    """
    return MODAL_WIDTHS[sprosse]
```

- [ ] **Schritt 4: Den Test laufen lassen**

```bash
.venv/bin/python -m pytest tests/src/test_breitenleiter.py -q
```
Erwartet: alle gruen.

- [ ] **Schritt 5: Den vollen sicheren Lauf, im Vordergrund**

```bash
.venv/bin/python -m pytest -q --ignore=tests/render --ignore=tests/lock
```

- [ ] **Schritt 6: Einchecken**

```bash
git add src/sizes.py tests/src/test_breitenleiter.py
git commit -m "feat(UI-1): drei gemessene Sprossen statt zwoelf gegriffener Breiten"
```

---

### Aufgabe 2: Die tote Groessen-Kette faellt

**Warum vor dem Umbau der Fenster:** solange die Oberflaeche vierzig Zahlen
anbietet, die niemand liest, weiss beim naechsten Schritt keiner, welches der
beiden Systeme gilt. Zwei Antworten auf dieselbe Frage sind der Fehler, an dem
dieses Projekt an einem Tag dreimal gelitten hat.

**Dateien:**
- Aendern: `src/templates/ags-style-editor.template` (Reiter "widgets" faellt)
- Aendern: `src/style_definition.py` (`_monitor_style_variables()`,
  `get_widget_size*`, `_WIDGET_WINDOW_WIDTHS`, `_WIDGET_SCROLL_HEIGHTS`)
- Aendern: `src/user_settings.py` (`widget_sizes` in `DEFAULT_SETTINGS`,
  `reset_widget_sizes_resolution`, `reset_all_widget_sizes`, die Zeilen um 967
  und 994)
- Aendern: `tests/src/test_style_definition.py` (Zeilen um 246, 279, 280)
- Aendern: `tests/src/test_user_settings.py`

- [ ] **Schritt 1: Vor jeder Aenderung die Leser einzeln zaehlen**

Das ist keine Formalie - es ist die Abnahme dafuer, dass hier wirklich
nichts Lebendes faellt. Fuer JEDEN Platzhalter einzeln:

```bash
for p in STYLE_EWW_WINDOW STYLE_EWW_SCROLL; do
  echo -n "$p: "
  grep -rl "$p" src/templates/ src/styles/ 2>/dev/null | wc -l
done
```
Erwartet: beide `0`. Kommt irgendwo etwas anderes als 0 heraus, **halt an** und
melde es - dann ist die Kette nicht tot und dieser Auftrag ist falsch.

- [ ] **Schritt 2: Den Reiter aus dem Stil-Editor nehmen**

In `ags-style-editor.template` faellt:
- `DEFAULT_WIDGET_SIZES` (die vier Aufloesungsbloecke, ~Zeile 150-198)
- die Eintraege `minW`/`maxW`/`minH`/`maxH` in der Fensterliste
- `widget_sizes` aus `interface StyleSettings`
- `currentTab: "colors" | "widgets" | "themes"` wird
  `"colors" | "themes"`, und der Reiter selbst samt seinem Inhaltsbauer

Der Kommentar, der an seine Stelle tritt:

```typescript
// DEN REITER "FENSTERGROESSEN" GAB ES, UND ER HAT NIE ETWAS BEWIRKT
//
//     Er bot zehn Fenster mal vier Aufloesungen an, schrieb sie nach
//     user-settings.json unter widget_sizes, und style_definition.py
//     machte daraus die Platzhalter STYLE_EWW_WINDOW_<WIDGET>_MON<n>
//     und STYLE_EWW_SCROLL_<WIDGET>_MON<n>.
//
//     GEMESSEN am 18.08.2026, `grep -rl` gegen src/templates/ UND
//     src/styles/: NULL Vorlagen lasen einen dieser Platzhalter. Die
//     Fenster nahmen stattdessen ihre eigene, ausgemessene WIN_WIDTH.
//     Vierzig Regler ohne Wirkung.
//
//     Das EWW im Namen ist der Rest einer Leiste, die dieses Projekt
//     nicht mehr hat. An ihre Stelle tritt die Breitenleiter in
//     sizes.py - drei Sprossen, die das Fenster selbst nennt.
```

- [ ] **Schritt 3: Die Erzeuger-Seite loeschen**

In `src/style_definition.py`: `get_widget_size`, `get_widget_size_for_monitor`,
`get_widget_scroll_for_monitor`, `_WIDGET_WINDOW_WIDTHS`,
`_WIDGET_SCROLL_HEIGHTS` und die beiden `for widget, default in ...`-Schleifen
in `_monitor_style_variables()`. Was dort stehen bleibt, sind
`STYLE_SCALE_INFO` und `STYLE_SCALE_FACTOR_MON<n>`.

In `src/user_settings.py`: `widget_sizes` aus `DEFAULT_SETTINGS`,
`reset_widget_sizes_resolution`, `reset_all_widget_sizes` und die Lese- und
Schreibpfade um Zeile 967 und 994. **Ruft die Kommandozeile eine dieser
Funktionen auf, faellt der Aufruf mit** - eine Unterkommando-Hilfe, die eine
Einstellung ohne Wirkung anbietet, ist dieselbe Luege eine Ebene tiefer.

- [ ] **Schritt 4: Die Behauptungen ueber die tote Kette loeschen**

`tests/src/test_style_definition.py:246,279,280` und die entsprechenden Stellen
in `tests/src/test_user_settings.py` behaupten, dass die Platzhalter existieren.
Sie existieren dann nicht mehr, also fallen sie mit.

**Das ist KEIN Aufweichen eines Waechters** und muss im Bericht ausdruecklich so
begruendet werden: ein Test, dessen Gegenstand geloescht ist, wird geloescht -
ein Test, der rot wird, weil neuer Code falsch ist, wird repariert. Bleibt nach
dem Loeschen irgendein Test rot, ist das der zweite Fall.

- [ ] **Schritt 5: Erzeugungsprobe**

Ueber `src/template_processor.py` in ein temporaeres Verzeichnis alle beruehrten
Vorlagen erzeugen. Erwartet: kein uebrig gebliebener `{{...}}`-Platzhalter,
`node --check` auf dem erzeugten `StyleEditor.ts` mit Ausgang 0.

- [ ] **Schritt 6: Der volle sichere Lauf, im Vordergrund**

- [ ] **Schritt 7: Einchecken**

```bash
git add src/style_definition.py src/user_settings.py \
        src/templates/ags-style-editor.template \
        tests/src/test_style_definition.py tests/src/test_user_settings.py
git commit -m "refactor(UI-1): die wirkungslose Fenstergroessen-Kette faellt"
```

---

### Aufgabe 3: Jedes Fenster nennt seine Sprosse

**Dateien:**
- Aendern: `src/templates/ags-battery.template:63`,
  `ags-calendar.template:72`, `ags-notifications.template:539`,
  `ags-style-editor.template:49`, `ags-disk.template:39`,
  `ags-wallpaper.template:45`, `ags-vpn-settings.template:55`
- Aendern: `src/templates/ags-shortcuts.template:105` (**Sonderfall**, siehe
  Schritt 3)

**`src/generate_config.sh` wird NICHT angefasst**, und das ist geprueft:
`template_processor.py:52` liest `STYLE_VARIABLES` aus `style_definition`
geschlossen, ein neuer `{{STYLE_*}}`-Name braucht keine Anmeldung. Die
Schleife um `generate_config.sh:1317`, die "placeholder" heisst, legt
Hyprland-`.conf`-Dateien an und hat mit Platzhaltern im Vorlagensinn nichts
zu tun. Wer sie hier anfasst, sucht am falschen Ort.

**Schnittstellen:**
- Verbraucht: `MODAL_WIDTH` aus Aufgabe 1, ueber einen neuen Platzhalter
  `{{STYLE_MODAL_WIDTH_S}}`, `_M`, `_L` aus `style_definition.py`.

- [ ] **Schritt 1: Die drei Platzhalter bereitstellen**

In `src/style_definition.py`, bei den festen Werten (nicht bei den
monitorabhaengigen - eine Sprosse haengt an keinem Schirm):

```python
    **{f"STYLE_MODAL_WIDTH_{name}": f"{px}px"
       for name, px in sizes.MODAL_WIDTHS.items()},
```

- [ ] **Schritt 2: Sieben Fenster umstellen**

Je Vorlage die Zeile `const WIN_WIDTH = <zahl>` ersetzen durch
`const WIN_WIDTH = {{STYLE_MODAL_WIDTH_S}}` (bzw. `_M`), und den vorhandenen
Messkommentar **stehen lassen** - er erklaert weiterhin, woher die Zahl
darunter kommt, und bekommt eine Schlusszeile:

```
//     SEIT DEM 18.08.2026 nennt dieses Fenster nicht mehr seine
//     Rechnung, sondern die Sprosse darueber: die gemessenen <zahl>
//     passen in S/M (siehe MODAL_WIDTHS in sizes.py). Die Rechnung
//     bleibt hier stehen, weil sie begruendet, WARUM diese Sprosse und
//     nicht die kleinere.
```

Zuordnung (aus der Messtabelle oben, nicht neu raten):

| Vorlage | gemessen | Sprosse |
|---|---|---|
| `ags-notifications.template` (`CENTER_WIDTH`) | 420 | S |
| `ags-battery.template` | 436 | S |
| `ags-style-editor.template` | 474 | S |
| `ags-calendar.template` | 496 | S |
| `ags-disk.template` | 556 | M |
| `ags-wallpaper.template` | 616 | M |
| `ags-vpn-settings.template` | 642 | M |

- [ ] **Schritt 3: Die Kuerzel auf zwei Spalten und Sprosse L**

`ags-shortcuts.template` will 1076 und bekommt 960, weil der Deckel greift -
das ist der einzige Fall, in dem die Leiter nicht nur aufraeumt, sondern einen
Fehler behebt. Das Raster von drei auf zwei Spalten stellen, dann
`const WIN_WIDTH = {{STYLE_MODAL_WIDTH_L}}`.

**Nachrechnen und im Bericht nennen:** zwei Spalten Inhalt + Polsterung +
Rahmen + Bildlaufleiste muessen <= 880 ergeben. Kommt mehr heraus, ist die
Sprosse falsch und **nicht** der Deckel - dann anhalten und melden, statt eine
vierte Sprosse zu erfinden.

- [ ] **Schritt 4: Erzeugungsprobe fuer alle acht Vorlagen**

- [ ] **Schritt 5: Der volle sichere Lauf, im Vordergrund**

- [ ] **Schritt 6: Einchecken**

```bash
git commit -m "feat(UI-1): acht Fenster nennen ihre Sprosse statt ihrer Zahl"
```

---

# STUFE 3 - DIE SCHALE

---

### Aufgabe 4: Die Bauteile der Schale

Noch kein Fenster geaendert - erst die Teile, dann der Umbau. Dieselbe
Reihenfolge wie bei Stufe 1, und aus demselben Grund: ein Bauteil, das man
waehrend eines Umbaus erfindet, wird nach dem Umbau geformt sein und nicht
nach der Aufgabe.

**Dateien:**
- Aendern: `src/templates/ags-kit.template`
- Aendern: `src/templates/ags-style.template`
- Test: `tests/src/test_schale.py` (neu)

**Schnittstellen:**
- Liefert, und alle folgenden Aufgaben rufen genau das auf:

```typescript
export interface ZepNavEintrag {
  id: string
  titel: string
  symbol: string
}

export interface ZepNavGruppe {
  titel: string          // "VERBINDUNGEN", "SYSTEM", "EINSTELLUNGEN"
  eintraege: ZepNavEintrag[]
}

/** Die Seitenleiste. 208 px breit, Gruppen mit Zwischenueberschrift. */
export function zepSidebar(
  gruppen: ZepNavGruppe[],
  aktiv: string,
  aufSeite: (id: string) => void,
): Gtk.Widget

/**
 * Der Kopf einer Seite. Er IST der Zustand, nicht eine Titelzeile
 * darueber: "Bluetooth ist an" als Ueberschrift, darunter die Nebenzeile
 * "1 von 2 Geraeten verbunden", rechts das Bedienelement.
 *
 * `ende` ist frei - ein zepToggle, ein zepButton, oder nichts.
 */
export function zepStateHeader(opts: {
  titel: string
  unterzeile?: string
  ende?: Gtk.Widget
}): Gtk.Widget
```

- [ ] **Schritt 1: Den fallenden Test schreiben**

`tests/src/test_schale.py` prueft die Vorlage als **Text**, wie
`tests/src/test_button_kit.py` es tut - AGS laeuft in diesem Lauf nicht:

```python
"""Die Schale - Seitenleiste und Zustandskopf kommen aus dem Kit.

Derselbe Ansatz wie test_button_kit.py: geprueft wird die VORLAGE, nicht
ein laufendes AGS. Ein Fenster, das sich seine Seitenleiste selbst baut,
faellt hier auf, solange es billig ist.
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
KIT = WURZEL / "src" / "templates" / "ags-kit.template"
STIL = WURZEL / "src" / "templates" / "ags-style.template"


def test_das_kit_liefert_die_drei_bauteile():
    text = KIT.read_text(encoding="utf-8")
    for name in ("zepSidebar", "zepStateHeader"):
        assert f"export function {name}" in text, f"{name} fehlt im Kit"


def test_die_seitenleiste_ist_208_breit():
    # Die Zahl steht in der Spezifikation, Abschnitt 2.2, und sie ist
    # der einzige Ort, an dem sie stehen darf.
    text = STIL.read_text(encoding="utf-8")
    block = re.search(r"\.zep-sidebar\s*\{[^}]*\}", text, re.S)
    assert block, ".zep-sidebar fehlt im Stylesheet"
    assert "208px" in block.group(0)


def test_kein_fenster_baut_sich_eine_eigene_seitenleiste():
    # Wer eine Navigationsspalte braucht, ruft zepSidebar auf. Eine
    # zweite Antwort auf dieselbe Frage ist der Fehler, den dieses
    # Vorhaben gerade fuer Knoepfe abgeraeumt hat.
    #
    # WORAUF DIESER AUSDRUCK ZIELT, UND WARUM NICHT AUF class="..."
    #     GEMESSEN am 18.08.2026: die AGS-Vorlagen setzen ihre Klassen
    #     ueber add_css_class("...") und cssClass:/cssClasses: - ein
    #     class="..."-Attribut kommt in keiner einzigen von ihnen vor.
    #     Ein Waechter, der darauf zielt, behauptet nichts.
    verboten = re.compile(
        r"(?:add_css_class\s*\(\s*|cssClass(?:es)?\s*:\s*\[?\s*)"
        r"[\"'`][^\"'`]*(?:sidebar|nav-col|side-nav)")
    for vorlage in (WURZEL / "src" / "templates").glob("ags-*.template"):
        if vorlage.name == "ags-kit.template":
            continue
        text = vorlage.read_text(encoding="utf-8")
        assert not verboten.search(text), (
            f"{vorlage.name} baut sich eine eigene Seitenleiste")


def test_dieser_waechter_wuerde_ueberhaupt_ausloesen():
    # Ein Waechter, der nie ausloest, ist kein Waechter. Der Ausdruck
    # oben wird hier einmal gegen eine Zeile gehalten, die genau so in
    # einer Vorlage stehen wuerde, wenn sich jemand eine eigene
    # Seitenleiste baut.
    verboten = re.compile(
        r"(?:add_css_class\s*\(\s*|cssClass(?:es)?\s*:\s*\[?\s*)"
        r"[\"'`][^\"'`]*(?:sidebar|nav-col|side-nav)")
    assert verboten.search('spalte.add_css_class("cc-sidebar")')
    assert verboten.search('  cssClass: "net-side-nav",')
    assert not verboten.search('const sidebarBreite = 208')
```

- [ ] **Schritt 2: Den Test laufen lassen und das Fallen sehen**

- [ ] **Schritt 3: Die Bauteile bauen**

`zepSidebar` benutzt fuer jeden Eintrag `zepRow` mit `ausgewaehlt` - das Bauteil
gibt es seit Stufe 1 und es traegt die aktive Markierung bereits. Nichts
Zweites dafuer bauen.

Die neuen CSS-Regeln in `ags-style.template`, **nur diese drei**:
`.zep-sidebar` (208px, Randfarbe rechts), `.zep-sidebar-group` (Abstand nach
oben), `.zep-state-head` (Polsterung, Schrift 19 fuer den Titel).

- [ ] **Schritt 4: Den Test laufen lassen**

- [ ] **Schritt 5: Die Ratsche pruefen**

Die neuen Klassen enden nicht auf `-btn`/`-button`, die Ratschenzahl darf sich
also **nicht** bewegen. Bewegt sie sich, ist ein Knopf entstanden, der keiner
sein sollte.

- [ ] **Schritt 6: Der volle sichere Lauf, im Vordergrund**

- [ ] **Schritt 7: Einchecken**

---

### Aufgabe 5: `createShellWindow()`

**Dateien:**
- Aendern: `src/templates/ags-overlay-utils.template`

**Schnittstellen:**
- Verbraucht: `zepSidebar`, `zepStateHeader` aus Aufgabe 4;
  `{{STYLE_MODAL_WIDTH_L}}` aus Aufgabe 3.
- Liefert:

```typescript
export interface ShellSeite {
  id: string
  titel: string
  symbol: string
  gruppe: string                        // "VERBINDUNGEN" | "SYSTEM" | ...
  bauen: (win: Astal.Window, schliessen: () => void) => Gtk.Widget
}

export interface ShellConfig {
  name: string
  cssClass: string
  seiten: ShellSeite[]
  startSeite: string
}

export interface ShellWidget extends OverlayWidget {
  /** Oeffnet die Schale und springt auf diese Seite. */
  zeigeSeite: (id: string, at?: OverlayAnchor) => void
}

export function createShellWindow(config: ShellConfig): ShellWidget
```

- [ ] **Schritt 1: Bauen, auf `createOverlayWindow` aufsetzend**

`createShellWindow` baut **kein zweites Astal.Window von Hand**. Es ruft
`createOverlayWindow` mit `width: {{STYLE_MODAL_WIDTH_L}}` und einem
`buildContent`, das die Seitenleiste links und die aktive Seite rechts setzt.

**Der Grund steht im Baum:** `OverlayConfig.onEscape` gibt es nur deshalb, weil
`ags-network.template` sich sein Fenster bis zum 12.08.2026 selbst gebaut hat -
und dabei die Bildlaufdeckelung verlor, 721 Punkte hoch auf einem 540er Deckel.
Wer die Fabrik umgeht, verliert alles andere gleich mit.

- [ ] **Schritt 2: ESC hat zwei Stufen**

Die Schale reicht ESC **zuerst an die aktive Seite** (`onEscape` der Seite),
dann an sich selbst. Eine Seite mit Unteransicht - das Passwortfeld im
Netzwerk - geht damit eine Stufe zurueck, statt die ganze Schale zuzuwerfen.
Genau dieser Fall ist der dokumentierte Ursprung von `onEscape`.

- [ ] **Schritt 3: Der Kopf ist der Zustand**

Kein Fenstertitel ueber der Seitenleiste. Die Seite liefert ihren
`zepStateHeader` selbst. Die Spezifikation rechnet dafuer rund 60 Punkte
Hoehe gegenueber getrennter Titel- und Statuszeile - **nachmessen und die
Zahl in den Bericht schreiben**, nicht abschreiben.

- [ ] **Schritt 4: Erzeugungsprobe, `node --check`**

- [ ] **Schritt 5: Der volle sichere Lauf, im Vordergrund**

- [ ] **Schritt 6: Einchecken**

---

### Aufgabe 6: Das Kontrollzentrum wird die Schale

**Dateien:**
- Aendern: `src/templates/ags-control-center.template`
- Aendern: `src/templates/ags-config.template`

- [ ] **Schritt 1: Der heutige Inhalt wird die erste Seite**

Was das Kontrollzentrum heute zeigt, wird eine Seite unter `SYSTEM`. Es wird
nichts weggenommen - die Zusage vom 17.08.2026 lautet "alle funktionen auch im
control panel aber auch ausserhalb", und sie gilt weiter.

- [ ] **Schritt 2: Die Seitenleiste mit den drei Gruppen**

```
VERBINDUNGEN    Netzwerk, Bluetooth, VPN      (noch leer - Aufgaben 7-9)
SYSTEM          Ton, Anzeige
EINSTELLUNGEN   (Platz)
```

Die drei Eintraege unter VERBINDUNGEN werden **jetzt schon angelegt** und
zeigen bis zu ihrer Aufgabe eine Seite mit einer Zeile: `zepStateHeader` mit
dem Titel und der Unterzeile "Diese Seite zieht gerade um." Ein Eintrag, der
ins Leere fuehrt, ist schlimmer als einer, der sagt, was los ist.

- [ ] **Schritt 3: `widgets.control` auf `createShellWindow` umstellen**

Der Zweig `reqStr.includes("control")` in `ags-config.template` bleibt und ruft
weiterhin `toggleWidget(widgets.control)`.

- [ ] **Schritt 4: Erzeugungsprobe, voller Lauf, einchecken**

---

### Aufgabe 7: Bluetooth wird eine Seite

**Zuerst Bluetooth**, weil es die Meldung ausgeloest hat, weil es die kuerzeste
der drei ist und weil es keine Unteransicht mit eigener ESC-Behandlung hat.

**Dateien:**
- Aendern: `src/templates/ags-bluetooth.template`
- Aendern: `src/templates/ags-control-center.template`
- Aendern: `src/templates/ags-config.template`, `ags-bar.template`

- [ ] **Schritt 1: `ags-bluetooth.template` exportiert eine Seite statt eines Fensters**

Aus `createOverlayWindow({...})` wird ein exportiertes `bluetoothSeite:
ShellSeite`. Der Inhaltsbauer bleibt derselbe - **was faellt, ist nur die
Fensterhuelle**, nicht die Logik.

Der Kopf der Seite wird `zepStateHeader` mit
titel: "Bluetooth ist an"/"Bluetooth ist aus", unterzeile: "1 von 2 Geraeten
verbunden", ende: `zepToggle`.

- [ ] **Schritt 2: Der Leisteneintrag oeffnet die Schale auf der Seite**

In `ags-bar.template` wird aus `toggles: "bluetooth"` ein Aufruf, der
`widgets.control.zeigeSeite("bluetooth", anker)` erreicht. Der Klick fuehrt
weiterhin genau einen Handgriff aus - er landet nur woanders.

- [ ] **Schritt 3: `widgets.bluetooth` und sein Anfragezweig fallen**

In `ags-config.template` faellt `toggleWidget(widgets.bluetooth)`. **Der Zweig
`reqStr.includes("bluetooth")` bleibt** und leitet auf die Schale um - eine
Tastenbindung, die es gab, darf nicht stumm werden.

- [ ] **Schritt 4: Pruefen, dass die Breite nicht mehr gilt**

`const WIN_WIDTH = 500` in `ags-bluetooth.template` faellt: eine Seite hat keine
eigene Fensterbreite mehr, sie bekommt die der Schale. **Im Bericht nennen**,
dass die 500 damit erledigt sind und nicht nur unbenutzt herumliegen.

- [ ] **Schritt 5: Erzeugungsprobe, voller Lauf, einchecken**

---

### Aufgabe 8: Netzwerk wird eine Seite

**Die schwierigste der drei.** Netzwerk hat zwei Unteransichten - Passwort und
Details - und ihr ESC muss zurueck zur Liste, nicht zu. Genau dafuer gibt es
`onEscape`, und genau dafuer hat Aufgabe 5 die zweistufige Weitergabe gebaut.

**Dateien:** wie Aufgabe 7, plus `src/templates/ags-network-scripts.template`
nur lesen (nicht aendern).

- [ ] **Schritt 1: Vor dem Umbau die ESC-Wege aufschreiben**

Welche Ansichten gibt es, was tut ESC in jeder? Die Liste gehoert in den
Bericht, **bevor** etwas umgebaut wird. Ein ESC-Weg, den man erst nach dem
Umbau vermisst, ist teuer.

- [ ] **Schritt 2: Als Seite mit eigenem `onEscape` einhaengen**

- [ ] **Schritt 3: Jeden aufgeschriebenen ESC-Weg einzeln nachpruefen**

- [ ] **Schritt 4: Leiste, Anfragezweig, `WIN_WIDTH` - wie Aufgabe 7**

- [ ] **Schritt 5: Erzeugungsprobe, voller Lauf, einchecken**

---

### Aufgabe 9: VPN wird eine Seite, die drei Fenster fallen

**Dateien:** wie Aufgabe 7, plus Aufraeumen.

- [ ] **Schritt 1: VPN als Seite** (wie Aufgabe 7)

- [ ] **Schritt 2: Die VPN-Einstellungen bleiben ein eigenes Fenster**

Sie sind kein Verbindungsziel, sondern ein Formular, und die Seitenleiste hat
keinen Eintrag dafuer. Das Zahnrad auf der VPN-Seite oeffnet sie weiterhin -
auf Sprosse M, wie in Aufgabe 3 gesetzt.

- [ ] **Schritt 3: Aufraeumen, vollstaendig**

Nach diesem Schritt darf **kein** Rest der drei Einzelfenster mehr im Baum
stehen: keine `widgets.network`/`.bluetooth`/`.vpn`, keine verwaisten
CSS-Klassen ihrer Fensterhuellen, keine toten `WIN_WIDTH`. Nach Regel 14 wird
geloescht, nicht als "veraltet" markiert.

- [ ] **Schritt 4: Die Ratsche ein letztes Mal ausgeben lassen**

Sie darf gefallen sein (Fensterhuellen nehmen Klassen mit) und **nicht**
gestiegen. Ist sie gefallen, `ERLAUBT` senken, mit Historie-Zeile.

- [ ] **Schritt 5: Erzeugungsprobe fuer ALLE AGS-Vorlagen, nicht nur die
      beruehrten**

- [ ] **Schritt 6: Der volle sichere Lauf, im Vordergrund**

- [ ] **Schritt 7: Einchecken**

```bash
git commit -m "feat(UI-1): VPN als Seite, die drei Einzelfenster fallen"
```

---

## Was NICHT dazugehoert

- **UI-2**, die Farbreduktion von 69 auf ~10. Vertagt, im Register.
- **UI-3**, die 67 Klassen in 11 wiederkehrenden Formen. Vertagt, im Register.
- Die zwanzig toten CSS-Regeln aus dem Kontrollzentrum. Eigener Auftrag,
  im Register.
- Der Kuerzel-Editor mit Tastenaufnahme. Eigene Aufgabe, im Register.
- **Ton und Anzeige** als Seiten unter SYSTEM. Die Seitenleiste nennt sie,
  weil die Spezifikation sie nennt; gebaut werden sie hier nicht. Bis dahin
  tragen sie denselben Umzugshinweis wie in Aufgabe 6.
