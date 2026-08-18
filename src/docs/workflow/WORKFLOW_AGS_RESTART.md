# AGS Neu Starten

## Korrekte Methode

```bash
# AGS stoppen
pkill -9 -f "gjs.*ags"

# AGS im Hintergrund starten
cd ~/.config/ags && setsid -f ags run >/dev/null 2>&1
```

## Einzeiler

```bash
pkill -9 -f "gjs.*ags"; sleep 1; cd ~/.config/ags && setsid -f ags run >/dev/null 2>&1
```

## FALSCH - Nicht verwenden

```bash
# FALSCH: timeout killt AGS nach X Sekunden
timeout 5 ags run

# FALSCH: Ohne setsid bleibt es am Terminal hängen
ags run &

# FALSCH: nohup funktioniert nicht zuverlässig
nohup ags run &
```

## Warum setsid?

- `setsid -f` startet AGS als eigene Session, unabhängig vom Terminal
- AGS läuft weiter, auch wenn das Terminal geschlossen wird
- Kein Hängen, kein Blockieren

## Prüfen ob AGS läuft

```bash
pgrep -f "gjs.*ags"
```

## Wann AGS neu starten?

- Nach Installation neuer Apps (damit sie im Launcher erscheinen)
- Nach Änderungen an AGS-Widgets
- Nach Änderungen an AGS-Styles
