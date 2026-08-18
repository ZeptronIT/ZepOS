# UI-1, Stufe 4: die uebrigen elf Fenster auf das Kit

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development. Steps use checkbox
> (`- [ ]`) syntax.

**Goal:** Jedes AGS-Fenster benutzt das Bauteil-Kit; von den 50
Knopf-Klassen bleiben die fuenf des Kits.

**Architecture:** Gleichfoermige Umstellung nach dem an Bluetooth
erprobten Muster, in fuenf Gruppen nach Aufwand geschnitten. Die Ratsche
in `tests/src/test_button_kit.py` misst den Fortschritt und faellt, wenn
jemand eine neue Klasse erfindet.

**Tech Stack:** AGS/Astal 4 auf GTK4, `.template`-Dateien mit
`{{STYLE_*}}`-Platzhaltern, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-ags-gestaltungssystem-design.md`

## Global Constraints

- **NIEMALS** `tests/render/` oder `tests/lock/` laufen lassen, **nie**
  `tests/render/shoot.py` oder `iso/test-boot.py`: sie oeffnen Fenster
  auf dem Bildschirm des Nutzers. Testlauf ausschliesslich
  `pytest -q --ignore=tests/render --ignore=tests/lock`, und davon
  einmal den VOLLEN Lauf vor jedem Commit.
- **NIEMALS** `generate_config.sh` ausfuehren.
- Keine nackte Zahl, keine neue Farbe (UI-2 ist vertagt), sichtbarer
  Text durch `_()`.
- Kein Waechter aufgeweicht. Einzige Ausnahme: `ERLAUBT` in der Ratsche
  darf SINKEN, mit Historie-Zeile.
- Kommentare auf Deutsch, mit Datum und Messung.
- Bei Abweichung zwischen Plan und Baum gilt der BAUM.

---

## Das Muster (gilt fuer jede Gruppe)

An Bluetooth erprobt, Commit `0bbd57c`. Jede Gruppe arbeitet es ab:

1. **Zaehlen, was faellt.** Fuer jede genannte Klasse repo-weit pruefen,
   dass sie nach dem Umbau niemand mehr benutzt - `grep` ueber den
   GANZEN Baum, nicht nur ueber die eine Vorlage.
2. **Ratsche senken**, um die Zahl der wirklich entfernten Klassen. Die
   neue Zahl vom Zaehler ausgeben lassen, nicht abschreiben. Historie-
   Zeile dazu.
3. **Importieren:** `import { zepButton, zepRow, zepToggle,
   zepSectionLabel, zepDivider } from "../utils/kit"` - nur, was
   gebraucht wird.
4. **Ersetzen:** jedes `new Gtk.Button` durch `zepButton(...)`, jede
   Listenzeile durch `zepRow(...)`, jeden Ein-/Ausschalter durch
   `zepToggle(...)`, jede Abschnittsmarke durch `zepSectionLabel(...)`,
   jeden Trenner durch `zepDivider()`.
5. **Rollen zuteilen:** genau EIN `voll` je Ansicht (die Hauptsache),
   `umrandet` fuer die uebrigen Handlungen, `still` fuer Nebenwege,
   `kritisch` nur fuer Zerstoerendes (loeschen, trennen, vergessen).
   Zwei `voll` nebeneinander heissen, dass keiner die Hauptsache ist.
6. **Alte Regeln entfernen** aus `src/templates/ags-style.template`,
   jede einzeln nach der Pruefung aus Schritt 1.
7. **Loeschprotokoll** als Kommentar, mit Datum. Klassennamen **ohne
   fuehrenden Punkt** schreiben - sonst zaehlt der Waechter sie mit.
   (Nach Task 6 blendet er Kommentare aus; die Konvention bleibt
   trotzdem, weil sie auch anderswo gilt.)
8. **Voller sicherer Lauf**, dann EIN Commit je Gruppe.

**Was NICHT dazugehoert:** die Breitenleiter (Stufe 5), die Schale mit
der Seitenleiste (Stufe 3), neue Farben (UI-2). Wer beim Umbau merkt,
dass ein Fenster zu schmal ist, schreibt es in den Bericht statt es zu
aendern.

---

### Task A: die sechs mit je einer Klasse

**Files:**
- Modify: `src/templates/ags-battery.template` (`battery-profile-btn`)
- Modify: `src/templates/ags-calendar.template` (`calendar-action-btn`)
- Modify: `src/templates/ags-disk.template` (`disk-action-btn`)
- Modify: `src/templates/ags-notifications.template` (`notif-close-btn`)
- Modify: `src/templates/ags-shortcuts.template` (`sc-edit-btn`)
- Modify: `src/templates/ags-overlay-utils.template` (`overlay-close-btn`)
- Modify: `src/templates/ags-style.template`, `tests/src/test_button_kit.py`

**Interfaces:**
- Consumes: das Kit aus `../utils/kit`, die Rollen aus `.zep-btn-*`.
- Produces: nichts. Sechs Fenster weniger mit eigenen Knoepfen.

- [ ] **Schritt 1: Das Muster oben abarbeiten**, Punkt 1 bis 7, fuer
      alle sechs Klassen.

  **`overlay-close-btn` ist der besondere Fall:** er sitzt in der
  FABRIK (`createOverlayWindow`) und ist damit das `x` in der Kopfzeile
  JEDES Fensters. Er ist kein gewoehnlicher Knopf - er traegt ein
  Zeichen statt Text und steht am Rand. Pruef, ob `zepButton` mit der
  Rolle `still` ihn traegt, ohne dass er seine Groesse oder seinen
  Platz aendert. **Wenn nicht: lass ihn stehen und melde es** - ein
  veraendertes `x` in zwoelf Fenstern ist ein groesserer Eingriff als
  dieser Auftrag hergibt.

- [ ] **Schritt 2: Voller sicherer Lauf**

Run: `.venv/bin/python -m pytest -q --ignore=tests/render --ignore=tests/lock`
Expected: gruen. Rot heisst: der Code wird repariert, nie der Test.

- [ ] **Schritt 3: Commit**

```bash
git add src/templates/ags-battery.template src/templates/ags-calendar.template \
        src/templates/ags-disk.template src/templates/ags-notifications.template \
        src/templates/ags-shortcuts.template src/templates/ags-overlay-utils.template \
        src/templates/ags-style.template tests/src/test_button_kit.py
git commit -m "feat(UI-1): sechs Fenster auf die Bauteile"
```

---

### Task B: Hintergruende und Stil-Editor

**Files:**
- Modify: `src/templates/ags-wallpaper.template` (`wp-action-btn`,
  `wp-import-btn`, `wp-monitor-btn`)
- Modify: `src/templates/ags-style-editor.template` (`se-action-btn`,
  `se-edit-btn`, `se-tab-btn`, und der Farbwaehler: `cp-apply-btn`,
  `cp-cancel-btn`, `cp-preset-btn`)
- Modify: `src/templates/ags-style.template`, `tests/src/test_button_kit.py`

**Interfaces:**
- Consumes: das Kit.
- Produces: nichts.

- [ ] **Schritt 1: Das Muster abarbeiten**, Punkt 1 bis 7.

  **`se-tab-btn` ist ein Reiter, kein Knopf.** Ein Reiter hat einen
  ausgewaehlten Zustand und sitzt in einer Leiste. Pruef, ob
  `zepButton` mit `still`/`umrandet` plus der `active`-Klasse das
  traegt. **Traegt es nicht, lass die Reiter stehen und melde es** -
  ein Reiter ist ein eigenes Bauteil, und es zu erfinden ist nicht Teil
  dieses Auftrags.

  Dasselbe fuer `cp-preset-btn`: eine Farbkachel ist kein Knopf mit
  Text. Pruefen, im Zweifel stehenlassen und melden.

- [ ] **Schritt 2: Voller sicherer Lauf**
- [ ] **Schritt 3: Commit** — `feat(UI-1): Hintergruende und Stil-Editor auf die Bauteile`

---

### Task C: Netzwerk

**Files:**
- Modify: `src/templates/ags-network.template` (`net-back-btn`,
  `net-connect-btn`, `net-detail-btn`, `net-disconnect-btn`,
  `net-nm-btn`, `net-refresh-btn`)
- Modify: `src/templates/ags-style.template`, `tests/src/test_button_kit.py`

**Interfaces:**
- Consumes: das Kit, insbesondere `zepRow` mit `ausgewaehlt` und der
  Kuerzung aus Task 6.
- Produces: nichts.

- [ ] **Schritt 1: Das Muster abarbeiten**, Punkt 1 bis 7.

  **Dieses Fenster ist der Grund, warum `zepRow` kuerzen muss.**
  GEMESSEN am 17.08.2026: eine Beschriftung ohne Kuerzung blies es auf
  660 Punkte auf, weil die Mindestbreite einer solchen Beschriftung
  ihre ganze Zeile ist. WLAN-Namen sind beliebig lang. Nach dem Umbau
  **miss die Mindestbreite des Inhalts** und schreib sie in den
  Bericht - sie muss unter der Fensterbreite liegen.

  `net-disconnect-btn` ist die Rolle `kritisch`, nicht `umrandet`:
  Trennen ist zerstoerend.

- [ ] **Schritt 2: Voller sicherer Lauf**
- [ ] **Schritt 3: Commit** — `feat(UI-1): Netzwerk auf die Bauteile`

---

### Task D: Kontrollzentrum

**Files:**
- Modify: `src/templates/ags-control-center.template` (`cc-action-btn`,
  `cc-button`, `cc-expand-btn`, `cc-icon-btn`, `cc-mini-btn`,
  `cc-power-btn`, `cc-pwr-btn`, `cc-service-btn`, `cc-svc-btn`,
  `cc-toggle-btn`)
- Modify: `src/templates/ags-style.template`, `tests/src/test_button_kit.py`

**Interfaces:**
- Consumes: das Kit.
- Produces: nichts.

- [ ] **Schritt 1: Das Muster abarbeiten**, Punkt 1 bis 7.

  **Zehn Klassen fuer ein Fenster, und einige sehen nach Dubletten
  aus:** `cc-power-btn` neben `cc-pwr-btn`, `cc-service-btn` neben
  `cc-svc-btn`. Pruef, ob beide wirklich benutzt werden oder ob eine
  davon schon tot ist. Eine tote Klasse wird einfach entfernt und im
  Bericht genannt.

  Die Abschaltknoepfe (Neustart, Herunterfahren, Abmelden) sind
  `kritisch`. Es gibt genau EIN `voll` in diesem Fenster - entscheide,
  welches, und begruende es im Bericht.

- [ ] **Schritt 2: Voller sicherer Lauf**
- [ ] **Schritt 3: Commit** — `feat(UI-1): Kontrollzentrum auf die Bauteile`

---

### Task E: VPN und VPN-Einstellungen

**Files:**
- Modify: `src/templates/ags-vpn.template`,
  `src/templates/ags-vpn-settings.template` (`vpn-add-btn`,
  `vpn-back-btn`, `vpn-cancel-btn`, `vpn-connect-btn`,
  `vpn-delete-btn`, `vpn-disconnect-btn`, `vpn-list-btn`,
  `vpn-reset-btn`, `vpn-save-btn`, `vpn-save-psk-btn`,
  `vpn-settings-btn`, `vpn-tab-btn`, `vpn-toggle-btn`,
  `vpn-visibility-btn`)
- Modify: `src/templates/ags-style.template`, `tests/src/test_button_kit.py`

**Interfaces:**
- Consumes: das Kit.
- Produces: **die Ratsche steht danach auf 5.**

- [ ] **Schritt 1: Das Muster abarbeiten**, Punkt 1 bis 7.

  **Vierzehn Klassen, die groesste Gruppe.** `vpn-delete-btn` und
  `vpn-reset-btn` sind `kritisch`. `vpn-visibility-btn` (Passwort
  zeigen) ist ein Zeichen-Knopf wie das `x` - pruefen, im Zweifel
  stehenlassen und melden. `vpn-tab-btn` ist ein Reiter, siehe Task B.

  VPN-Profilnamen sind Fremdtexte beliebiger Laenge - die Kuerzung aus
  Task 6 ist hier Pflicht, nicht Kuer.

- [ ] **Schritt 2: Voller sicherer Lauf**

- [ ] **Schritt 3: Die Ratsche auf ihren Endstand**

  Bleiben genau die fuenf `zep-`Namen uebrig, setz `ERLAUBT = 5` und
  schreib in den Kommentar, dass das der Endstand ist. Bleiben mehr,
  **setz die Zahl auf das, was der Zaehler sagt**, und nenne im
  Bericht, welche Klassen uebrig sind und warum.

- [ ] **Schritt 4: Commit** — `feat(UI-1): VPN auf die Bauteile, Ratsche auf 5`

---

## Danach

Stufe 3 (die Schale mit der Seitenleiste) und Stufe 5 (die
Breitenleiter) bekommen eigene Plaene. Erst dann sieht es aus wie im
Entwurf; bis hierher ist es einheitlich gebaut.
