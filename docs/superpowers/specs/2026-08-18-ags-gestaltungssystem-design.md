# UI-1: Ein Gestaltungssystem fuer alle AGS-Fenster

Stand 18.08.2026. Gehoert zu Stufe 3 in
`docs/specs/2026-08-11-weg-zum-eigenen-os.md`.

---

## 1. Warum

Der Nutzer am 18.08.2026:

> "aktuell wirken sie sehr noch wie zusammengebastelt warum, ist das so
> vor allem die haupt funktionen wie bluetooth sind kleine fenster ohne
> viel width ausserdem wirken sie so billig durch die button wie sie
> dargestellt sind"

Das ist keine Geschmacksfrage, und die Ursache ist messbar.

**GEMESSEN am 18.08.2026** in `src/templates/ags-style.template`
(3087 Zeilen):

- **45 Knopf-Regeln in 41 verschiedenen Klassen.** `.bt-power-btn`,
  `.cc-mini-btn`, `.cc-pwr-btn`, `.cc-svc-btn`, `.net-back-btn`,
  `.vpn-add-btn`, `.wp-action-btn` und 34 weitere.
- **Keine einzige gemeinsame.** Es gibt kein `.zep-button`, kein
  `.ui-button`, nichts, was zwei Fenster teilen.

Allein im Bluetooth-Fenster stehen fuenf Knoepfe nebeneinander, die
sich in Radius (5 und 8), Schriftgrad (9, 11, 13), Hoehe und Rahmen
unterscheiden. Es WIRKT nicht nur zusammengebastelt - es ist es.

Dasselbe bei den Breiten. Jedes Fenster nennt eine eigene Zahl, und
keine davon ist hergeleitet:

| Fenster | heute |
|---|---|
| battery | 436 |
| style-editor | 474 |
| vpn | 476 |
| calendar | 496 |
| bluetooth | 500 |
| network | 500 |
| disk | 556 |
| wallpaper | 616 |
| vpn-settings | 642 |
| shortcuts | 1076 |

Zehn Fenster, zehn Zahlen, kein System. Deshalb ist Bluetooth - eine
Hauptfunktion - schmaler als die Hintergrundverwaltung.

---

## 2. Was gebaut wird

### 2.1 Die Bauteile (`ags-kit.template`, neu)

Eine neue Vorlage wird die einzige Quelle fuer die wiederkehrenden
Teile. Sie exportiert Funktionen, keine CSS-Klassen zum Selbst-
Anhaengen:

| Bauteil | Rollen / Masse |
|---|---|
| `zepButton(label, rolle, aktion)` | `voll`, `umrandet`, `still`, `kritisch`, `gesperrt` - alle 32 px hoch, Radius CONTROL (5), Schrift 13 |
| `zepRow({symbol, titel, unterzeile, aktion})` | 48 px hoch, Radius CARD (8), Symbol 18 px |
| `zepToggle(an, aktion)` | 44x24, Radius PILL |
| `zepSectionLabel(text)` | Schrift 11, Laufweite 0.06em, gedaempft |
| `zepDivider()` | 1 px, Randfarbe |

**WARUM FUNKTIONEN UND NICHT NUR CSS:** gemeinsame Klassen allein
haetten die 41 nie verhindert. Jedes Fenster baut heute sein eigenes
`Gtk.Button` und haengt eine eigene Klasse dran; eine Regel, an die man
sich halten SOLL, ist schwaecher als ein Bauteil, das man aufruft. Der
Unterschied ist derselbe wie zwischen einer Bitte und einer Schnittstelle.

Die 41 alten Klassen verschwinden **vollstaendig**. Keine bleibt "fuer
den Fall" liegen - das waere die zweite Antwort auf dieselbe Frage, an
der dieses Projekt schon dreimal an einem Tag gelitten hat.

### 2.2 Die Schale (`createShellWindow()` in `ags-overlay-utils.template`)

Neben `createOverlayWindow()` tritt ein zweiter Bauplan: ein Fenster mit
**Seitenleiste links** (208 px) und Inhaltsflaeche rechts.

Der Kopf der Inhaltsflaeche IST der Zustand, nicht eine Titelzeile
darueber: "Bluetooth ist an" als Ueberschrift (19 px), darunter eine
Nebenzeile ("1 von 2 Geraeten verbunden"), rechts der Schalter. Das
spart gegenueber einer getrennten Titel- und Statuszeile rund 60 px
Hoehe, und der Fenstertitel waere ohnehin redundant - die Seitenleiste
sagt bereits, wo man ist.

**Das Kontrollzentrum WIRD diese Schale.** Es ist kein Fenster daneben,
sondern das Fenster. Netzwerk, Bluetooth und VPN hoeren auf, eigene
Fenster zu sein, und werden Seiten darin.

Die Seitenleiste traegt drei Gruppen:

```
VERBINDUNGEN    Netzwerk, Bluetooth, VPN
SYSTEM          Ton, Anzeige
EINSTELLUNGEN   (Platz - siehe 4.1)
```

### 2.3 Die Leiste bleibt der kurze Weg

Die Symbole oben behalten ihren Klick. Er oeffnet die Schale **auf der
passenden Seite**, statt ein eigenes Fenster zu bauen. Damit bleibt die
Zusage vom 17.08.2026 erfuellt - "alle funktionen auch im control panel
aber auch ausserhalb" -, ohne dass dieselbe Sache zwoelfmal verschieden
gebaut ist.

### 2.4 Was Panel bleibt

Kalender, Meldungen, Akku, Datentraeger, Hintergruende und Kuerzel
bleiben Aufklappfenster an der Leiste - mit denselben Bauteilen, aber
ohne Seitenleiste.

**Begruendung:** ein Kalender, fuer den man ein Fenster mit Navigation
oeffnet, ist langsamer als einer, der aufklappt und wieder zugeht. Die
Trennung ist nicht Groesse, sondern Verweildauer: was man ANSIEHT,
bleibt Panel; was man BEDIENT, zieht in die Schale.

### 2.5 Die Breitenleiter

Vier Sprossen ersetzen die zehn geratenen Zahlen:

| Sprosse | px | fuer |
|---|---|---|
| S | 420 | Akku, Kalender |
| M | 560 | Meldungen, Datentraeger |
| L | 720 | Hintergruende, Kuerzel |
| XL | 880 | die Schale |

Jedes Fenster nennt seine Sprosse, nicht seine Pixel. Der Deckel aus
`MEASURE_MODAL_SHARE` (halbe Schirmbreite) bleibt und greift weiter -
auf 1920 sind das 960, XL passt also.

**Damit loest sich zugleich der Fall `shortcuts`:** es wollte 1076 und
bekam 960, weil die Entwurfsregel deckelt. Als Seite der Schale in
zwei Spalten statt drei braucht es die Breite nicht mehr.

---

## 3. Was das ersetzt

| heute | danach |
|---|---|
| 41 Knopf-Klassen | ein `zepButton` mit fuenf Rollen |
| 10 geratene Breiten | vier Sprossen |
| 12 Fenster aus der Fabrik | 6 Panels + 1 Schale mit 5 Seiten |
| Kontrollzentrum als eigenes Fenster | Kontrollzentrum IST die Schale |

---

## 4. Entscheidungen, die getroffen sind

### 4.1 Die Einstellungen bekommen Platz, aber noch keinen Inhalt

Die Seitenleiste sieht die Gruppe `EINSTELLUNGEN` vor. UI-1 baut sie
**nicht**. Der Platz kostet nichts und erspart den Umbau, wenn das
eigene Einstellungsfenster spaeter einzieht; ihn wegzulassen hiesse,
die Schale zweimal zu bauen.

Ob das heutige Programm (`settings/zepos_settings_gui`, 3627 Zeilen)
dabei ersetzt oder ergaenzt wird, entscheidet ein eigener Auftrag. Fuer
UI-1 ist es ohne Belang.

### 4.2 Farben bleiben, wie sie sind

UI-2 (69 Farben auf rund zehn) ist ausdruecklich vertagt. Die
Begruendung steht bei der Aufgabe: welche Farbrollen es geben MUSS,
zeigt sich erst, wenn die Fenster aus gemeinsamen Bauteilen bestehen.

UI-1 fuehrt deshalb **keine neuen Farben ein** und benennt keine um. Es
benutzt, was `brand.py` heute fuehrt.

### 4.3 Keine neuen Masse

Alle Werte kommen aus den vorhandenen Leitern in `src/sizes.py`:
Radien 5 / 8 / 13, Abstaende 2 / 4 / 8 / 12 / 16 / 20 / 24, Schrift
9 / 11 / 13 / 16 / 19 / 22. Die 32 px Knopfhoehe und die 48 px
Zeilenhoehe sind die einzigen neuen Zahlen - beide gehoeren als
Sprossen in `sizes.py`, nicht als Literale ins CSS.

---

## 5. Wie geprueft wird

Der Entwurf ist nur so viel wert wie sein Nachweis. Drei Ebenen:

**Quelltext.** Ein Test zaehlt die Knopf-Klassen in
`ags-style.template` und verlangt, dass es genau eine gibt. Er faellt,
sobald jemand die zweiundvierzigste erfindet - das ist der eigentliche
Zweck von UI-1, und ohne diesen Test waere er in einem Monat wieder weg.

**Geometrie.** `tests/src/test_overlay_windows.py` prueft heute schon
Breiten gegen Inhalte. Es bekommt die Breitenleiter dazu: jedes Fenster
nennt eine Sprosse, und keine Sprosse ist schmaler als der Inhalt, der
darin steht.

**Bild.** Die 59 Tests in `tests/render/` und `tests/lock/` machen
Aufnahmen im verschachtelten Compositor. Sie sind die einzige Ebene,
die "sieht aus wie zusammengebastelt" wirklich beantwortet - und die
einzige, die heute nicht im Hintergrund laufen kann, weil sie ein
Fenster in der Sitzung des Nutzers oeffnen (gemessen am 18.08.2026:
Hyprland verlangt vom Wirt `xdg_wm_base` in Fassung 6, wlroots bietet
5, und aquamarine faellt nicht auf seinen kopflosen Ruecken zurueck).

---

## 6. Reihenfolge

1. **Bauteile** - `ags-kit.template` plus die eine CSS-Regel, mit dem
   Zaehl-Test. Noch kein Fenster geaendert.
2. **Ein Fenster umstellen** - Bluetooth, weil es die Meldung ausgeloest
   hat und alle Bauteile braucht. Bild als Abnahme.
3. **Die Schale** - `createShellWindow()`, das Kontrollzentrum darauf,
   Netzwerk und VPN als Seiten.
4. **Die uebrigen Panels** - Kalender, Meldungen, Akku, Datentraeger,
   Hintergruende, Kuerzel auf die Bauteile.
5. **Die Breitenleiter** - erst zuletzt, wenn alle Inhalte stehen; vorher
   waeren die Sprossen geraten.

Nach Schritt 1 und nach Schritt 3 ist der Baum lieferbar. Ein
Zwischenstand, in dem die Haelfte der Fenster alt und die Haelfte neu
aussieht, ist ausdruecklich in Kauf genommen - alles auf einmal
umzustellen waere ein Aenderungsblock, den niemand mehr pruefen kann.

---

## 7. Was NICHT dazugehoert

- **UI-2**, die Farbreduktion. Vertagt, mit Begruendung.
- **Das Einstellungsfenster.** Nur der Platz, nicht der Inhalt.
- **Die Leiste und das Dock.** Sie bauen ihre Fenster selbst und sind
  nicht Teil der Fabrik. Ihre Bauteile duerfen aus dem Kit kommen,
  ihre Form bleibt.
- **`accentCssClass`**, die tote Klasse in zehn Fenstern. Sie faellt
  beim Umbau von selbst weg; sie ist kein eigener Auftrag.
