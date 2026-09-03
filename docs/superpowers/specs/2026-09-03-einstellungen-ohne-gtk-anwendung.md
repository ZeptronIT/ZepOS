# Die Einstellungen ohne GTK4-Anwendung

**Bestellt** am 03.09.2026, wörtlich: *„ich meine die zepos gtk4 anwendung
die sollte komplett ags sein selbst gebaut das bitte auch planen"*.

**Stand:** Plan. Nichts davon ist umgesetzt.

---

## Was heute da ist — gemessen, nicht geschätzt

| Modul | Zeilen | GTK-Bezüge | was es ist |
|---|---:|---:|---|
| `model.py` | 1 948 | **4** | die sieben Seiten, 93 Beschriftungen, Vorgaben |
| `bridge.py` | 1 326 | **4** | Prüfungen, JSON hinein und hinaus |
| `main.py` | 155 | **0** | die Befehlszeile |
| `screens.py` | 893 | 44 | die Seite „Bildschirme" |
| `app.py` | 803 | 91 | das Fenster |
| `bar.py` | 568 | 33 | die Seite „Leiste" |
| `style.py` | 397 | 8 | das Aussehen |

**Der wichtigste Befund steht in der zweiten Spalte:** die *Wahrheit*
(`model` + `bridge` + `main` = 3 429 Zeilen) hat **acht** GTK-Bezüge. Sie
ist kein Fenster, sie ist ein Backend. Das *Fenster*
(`app`/`screens`/`bar`/`style` = 2 661 Zeilen) trägt 176.

Und das AGS-Fenster gibt es bereits: `src/templates/ags-settings.template`,
1 225 Zeilen, bestellt am 18.08.2026 („ich will auch für unsere
einstellungen ein komplett eigenes ags fenster"). Es baut die Einstellungen
**nicht nach** — es fragt `zepos-settings-gui --json get` nach den sieben
Seiten und zeichnet sie. Eine Quelle, zwei Oberflächen.

## Was noch fehlt

**Fachlich nichts.** Die Bridge kennt sieben Arten von Bedienelementen:

    zahl  schalter  text  auswahl  farbe  reihenfolge  anordnung

Das AGS-Fenster zeichnet **alle sieben**, auf zwei Wegen: fünf als Zeile
neben ihrer Beschriftung (`case FARBE: ende = farbWidget(element)`), zwei
als eigene Seite (`reihenfolge` als Liste zum Umsortieren, `anordnung`
als Schirmbild) — eine Art, die keine Zeile ist, in eine Zeile zu
zwingen wäre schlechter und nicht besser.

> **Korrektur vom 03.09.2026.** Die erste Fassung dieses Absatzes
> behauptete, `farbe` fehle. Das war ein verunglücktes `grep` — gesucht
> nach „farben", im Quelltext steht „farbe". Es gab die Lücke nie.
> Damit die Frage künftig beantwortet und nicht geschätzt wird, misst
> sie jetzt `tests/src/test_einstellungen_abdeckung.py`: für jede Art
> aus `bridge.py` muss das Fenster eine Konstante mit demselben Wert
> und eine Stelle haben, die etwas baut — mitsamt Gegenbeweis, dass die
> Zusicherung eine fehlende Art auch sähe.

Alles Übrige — die sieben Seiten, die Prüfungen, die Vorgaben, die
Rechteabfragen, der Wächter der Bildschirmseite — liegt schon hinter
`--json` und wird von beiden Oberflächen geteilt.

## Der Weg

### Schritt 1 — die Abdeckung festnageln ✅

Erledigt am 03.09.2026: `tests/src/test_einstellungen_abdeckung.py`.
Fünf Zusicherungen, die aus `bridge.py` lesen, welche Arten es gibt, und
im Fenster nachsehen, ob jede gebaut wird. Sie ist die Bedingung, an der
der Rest dieses Plans hängt — fällt sie, fiele mit der GTK-Anwendung
eine Einstellung weg, die niemand vermisst, bis er sie sucht.

*Kein Abriss bisher.* Beide Oberflächen laufen weiter nebeneinander.

### Schritt 2 — der Eintrag zeigt auf AGS

`settings/zepos-settings.desktop` trägt heute
`Exec=/usr/bin/zepos-settings-gui`. Er zeigt künftig auf das AGS-Fenster
(`ags request settings`), mit demselben Rückfall, den das
Kontrollzentrum schon kennt: läuft kein AGS, kommt eine verständliche
Meldung statt eines Klicks ins Leere.

Dieselbe Umstellung für die vier Stellen, die heute das Fenster rufen:
`ags-control-center.template` (zwei), `list-profiles-config.template`,
und die Hilfe von `zepos-settings`.

### Schritt 3 — das Fenster fällt

`app.py`, `screens.py`, `bar.py`, `style.py` werden gelöscht — 2 661
Zeilen. `model.py`, `bridge.py`, `main.py` bleiben und heißen künftig,
was sie sind: das Backend hinter `zepos-settings` und hinter dem
AGS-Fenster.

Mit ihnen fallen die Abhängigkeiten `gtk4`, `libadwaita` und
`python-gobject` aus `zepos-settings-gui` — auf einer frischen
Installation ein Paket weniger, das nur für ein Fenster da war, das es
nicht mehr gibt.

### Schritt 4 — die Tests ziehen um

`tests/settings/` fährt heute die GTK-Anwendung (headless, über
broadwayd). Was das Modell prüft, bleibt und wird direkt gegen
`model`/`bridge` gefahren; was das Fenster prüft, wandert in die
Render-Läufe des AGS-Fensters.

## Was das kostet, und was nicht

**Es kostet nicht** die Befehlszeile: `zepos-settings get/set/apply`
läuft über `main.py`, und das hat null GTK-Bezüge.

**Es kostet nicht** den Installer: er benutzt `installer/`, nicht diese
Anwendung.

**Es kostet** die Möglichkeit, die Einstellungen ohne laufendes AGS zu
öffnen. Heute geht das; danach nicht mehr. Wer ein kaputtes AGS
reparieren will, hat weiterhin `zepos-settings` auf der Befehlszeile —
und `zepos-doctor`. Das ist eine bewusste Entscheidung und der einzige
echte Verlust dieses Umbaus.

## Reihenfolge und Abbruchstellen

Jeder Schritt ist für sich fertig und rückgängig zu machen:

1. Nach Schritt 1 gibt es zwei vollständige Oberflächen. Abbruch hier
   kostet nichts.
2. Nach Schritt 2 zeigen alle Wege auf AGS, die Anwendung liegt noch da.
   Abbruch hier heißt: eine Zeile im `.desktop` zurückdrehen.
3. Erst Schritt 3 löscht.

Zwischen 2 und 3 sollte eine Weile liegen, in der der Nutzer das
AGS-Fenster im Alltag benutzt. Was dabei auffällt, ist billiger zu
beheben, solange die alte Oberfläche noch da ist.
