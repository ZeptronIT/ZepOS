# ZepOS — Design-Spezifikation

**Datum:** 2026-08-03
**Status:** Entwurf zur Freigabe
**Herkunft:** abgespalten vom Konfigurationssystem in `~/.config/iconmanager`
(Repo `azzuriel/iconmanager`). Das ist eine Tatsache über die Vergangenheit und
bleibt deshalb hier stehen — ein Projekt, das seine Herkunft verschweigt, sieht
schlechter aus, nicht besser, und `git log` zeigt sie ohnehin. Im Quellbaum
unter `src/` kommt der Name nirgends mehr vor; §6.4 hält fest, wie das geprüft
wird.

---

## 1. Ziel

ZepOS ist eine Arch-basierte Linux-Distribution mit Hyprland-Desktop, ausgeliefert
als bootbare Live-ISO mit Installer. Sie ist aus dem oben genannten
Ursprungsprojekt hervorgegangen, befreit von der Geschäftslogik des vorherigen
Arbeitgebers, und wird als Open-Source-Projekt unter GPL-3.0 veröffentlicht.

**Träger:** ZeptronIT. `ZepDesk` bleibt die kommerzielle Marke, `ZepOS` ist das
freie Projekt.

**Erfolgskriterium:** Eine ISO, die auf beliebiger x86_64-Hardware bootet,
installiert und beim ersten Start einen funktionsfähigen Hyprland-Desktop
zeigt, der sich an die tatsächlich angeschlossenen Monitore anpasst.

> **Richtigstellung 11.08.2026.** Hier stand „offline installiert“. Das
> war nie wahr und ist gemessen: archinstalls `--offline` überspringt das
> Warten auf reflector, den Erreichbarkeitstest und das Holen der
> Spiegelliste, und ZepOS' `PackageSource.OFFLINE` verschiebt allein das
> `[zepos]`-Repository aufs Medium — die **Arch-Basis kommt in beiden
> Fällen über das Netz**. Was das Medium mitbringen müsste, ist
> ausgerechnet: 390 Pakete, 1 061 018 061 Byte komprimiert, ein Medium
> von rund 2,23 GB statt 1,23 GB. Die Größe ist nicht das Hindernis;
> die vier Stellen, an denen die Paketquelle dafür umgebogen werden
> muss, sind es. Siehe `iso/README.md`, Abschnitt „Offline
> installieren“. Bis dahin ist „offline“ kein Erfolgskriterium, sondern
> eine offene Aufgabe (Stufe 2 in
> `docs/specs/2026-08-11-weg-zum-eigenen-os.md`).

### Nicht-Ziele

- Keine Unterstützung anderer Architekturen als x86_64
- Keine Migration bestehender Installationen des Ursprungsprojekts
- Keine Unterstützung für Aktualisierungen zwischen Hauptversionen ohne
  Neuinstallation (`pacman -Syu` hält den Stand aktuell, ein Sprung über
  eine gepinnte Hyprland-Minor-Version hinweg nicht)

---

## 2. Getroffene Entscheidungen

| Thema | Entscheidung | Begründung |
|---|---|---|
| Name | ZepOS | Eigenständiger Projektname neben der Marke ZepDesk; Forks tragen nicht die Firmenmarke |
| Lizenz | GPL-3.0 | Copyleft schützt vor kommerzieller Schließung; gilt auch für die drei Plugin-Repos, die heute *keine* Lizenz haben |
| Zielprodukt | Live-ISO mit Installer | Vom Nutzer gewählt gegenüber Disk-Image und reinem Bootstrap-Script |
| Auslieferung | Pacman-Pakete; online bevorzugt, Offline-Repo in der ISO als Rückfall | Nach dem WLAN-Schritt ist meist Netz vorhanden — dann aktuelle Pakete statt ISO-Stand. **Der Rückfall trägt nur die ZepOS-Pakete**, nicht die Arch-Basis; siehe die Richtigstellung in §1 und §8.4 |
| Installer-UI | GTK4/libadwaita, mit TUI als Rückfall | Der Installer ist das Erste, was von ZepOS zu sehen ist. Grafik kann auf fremder GPU ausfallen, deshalb ein textbasierter Weg, der immer funktioniert |
| Git-History | Frischer `git init`, **kein** Klon | Die Historie des Ursprungs-Repos enthält Firmeninterna (siehe §3) |
| VPN / Watchdog | Bleiben, werden generisch | Feature-Verlust vermeiden; Firmenspezifische Werte wandern in die Nutzerkonfiguration |
| Hyprland-Version | ZepOS liefert `zepos-hyprland` selbst aus | Solange Hyprland aus Arch kommt, bestimmt Arch, wann die fuenf ABI-gekoppelten Plugins brechen. Mit eigenem Paket entscheidet ZepOS, wann die Version steigt, und die Plugins ziehen im selben Zug nach |
| Aktualisierungsweg | Signiertes Pacman-Repo auf GitHub Pages | Ohne erreichbares Repository gibt es keine Aktualisierung, und ohne Aktualisierung ist es keine Distribution, sondern ein einmaliges Abbild. Die ursprüngliche Fassung führte "kein Online-Repo für v1" unter den Nicht-Zielen und übersah genau das. Pages verlangt keinen Server, kein Zertifikat und keine Verfügbarkeitszusage |
| Arch-Paketstand | Auf ALA-Stichtag gepinnt | Reproduzierbare Builds; Upstream-Bugs können die ISO nicht unbemerkt brechen |
| Build-Umgebung | Docker (`archlinux:latest`) | Verifiziert verfügbar; `sudo` dafür ausdrücklich freigegeben |
| Partitionierung | `archinstall`, nicht selbstgeschrieben | Eigener Partitionierer wäre Code, dessen Bugs fremde Festplatten löschen |

---

## 3. Warum kein `git clone`

Das Ursprungs-Repo hat 239 Commits. Eine Zaehlung ueber die gesamte Historie
fand in mehreren davon Interna des vorherigen Arbeitgebers: eine interne
Domain, zwei interne DNS-Server, einen Dateiserver-Hostnamen, Rechnernamen aus
der Firmen-Namenskonvention und einen personenbezogenen Benutzernamen.

Dateien zu loeschen entfernt diese Daten nicht aus der Historie. Fuer ein
oeffentliches Repository waere das die Veroeffentlichung interner
Infrastrukturdetails.

**Konsequenz:** ZepOS beginnt mit `git init`. Die 181 getrackten Dateien werden
kopiert, bereinigt und als erster Commit aufgenommen. Das Ursprungs-Repo bleibt
unangetastet — kein Schreibzugriff, keine Testläufe darin.

---

## 4. Architektur

Drei Schichten, klar getrennt:

```
zepos (Git)  ──build──▶  Pacman-Pakete  ──embed──▶  ZepOS.iso
   Quellen                 6 Pakete                Offline-Repo
```

### 4.1 Repo-Layout

```
~/zepos/
├── LICENSE                     GPL-3.0
├── README.md
├── src/                        Konfigurations-Quellen
│   ├── icon_definition.py      Icon-SSOT
│   ├── style_definition.py     Style-SSOT
│   ├── icons_db.py             generiert, nie von Hand editieren
│   ├── template_processor.py   Template-Prozessor
│   ├── user_settings.py        Settings-CLI
│   ├── fetch_icons.py
│   ├── generate_config.sh      Generator
│   ├── templates/              Templates
│   ├── styles/                 Style-Templates
│   ├── system/                 System-Templates (sudoers-Drop-in)
│   └── profiles/               generische Beispielprofile
├── packaging/
│   ├── zepos-config/PKGBUILD
│   ├── zepos-keyring/PKGBUILD
│   ├── zepos-hyprlaunch/PKGBUILD
│   ├── zepos-hyprclipx/PKGBUILD
│   ├── zepos-hyprzones/PKGBUILD
│   └── zepos-desktop/PKGBUILD
├── iso/
│   ├── profiledef.sh
│   ├── packages.x86_64
│   ├── pacman.conf
│   └── airootfs/
├── installer/
│   ├── core/                   Datenmodell + archinstall-Übersetzung
│   ├── gui/                    GTK4/libadwaita
│   └── tui/                    Rückfall-Oberfläche
├── build/                      Docker-Build-Skripte
├── tests/
└── docs/
```

### 4.2 Pakete

| Paket | Inhalt | Kern-Abhängigkeit |
|---|---|---|
| `zepos-config` | Templates, Generator, Python-SSOT, Styles | `python`, `bash` |
| `zepos-keyring` | GPG-Schlüssel des ZepOS-Repos | — |
| `zepos-hyprland` | Hyprland 0.56.1, `provides`/`conflicts` gegen `hyprland` | — |
| `zepos-hyprlaunch` | Launcher-Plugin (C++) | `zepos-hyprland>=0.56.1`, `zepos-hyprland<0.57.0` |
| `zepos-hyprclipx` | Clipboard-Plugin (C++) | dito |
| `zepos-hyprzones` | Zonen-Tiling-Plugin (C++) | dito |
| `zepos-hyprbars` | Titelleisten-Plugin (C++, aus `hyprwm/hyprland-plugins`) | dito |
| `zepos-borders-plus-plus` | Zusatzrahmen-Plugin (C++, gleiche Quelle) | dito |
| `zepos-installer` | Installer-Kern + Datenmodell + archinstall-Übersetzung | `archinstall`, `python` |
| `zepos-installer-gui` | GTK4-Oberfläche | `zepos-installer`, `gtk4`, `libadwaita`, `python-gobject` |
| `zepos-installer-tui` | Textoberfläche (Rückfall) | `zepos-installer` |
| `zepos-desktop` | Meta-Paket | `zepos-config`, `zepos-hyprland`, die fünf Plugin-Pakete, AGS, Waybar, Kitty |

Die drei Installer-Pakete liegen nur in der ISO, nicht im installierten System.

**Korrektur der Plugin-Abhängigkeit.** Hier stand `hyprland>=0.55.4`,
`hyprland<0.56.0`, während §4.3 Hyprland auf 0.56.1 pinnt und die drei eigenen
Plugins auf 0.56.1 portiert wurden (`Monitor.hpp` verschoben,
`getMonitorFromCursor` entfallen, `m_realPosition` protected). Kein
Plugin-Paket haette mit dieser Zeile bauen koennen: der Bereich schliesst genau
die Version aus, gegen die der Quellcode uebersetzt. Der Name ist ausserdem
`zepos-hyprland` und nicht `hyprland` — die Revision zu §7 hat Hyprland in ein
eigenes Paket verlegt, und eine Abhaengigkeit auf das Arch-Paket wuerde die
Kopplung, die dort aufgeloest wurde, wieder einfuehren.

Jedes Plugin-Paket legt genau eine Datei ab:

```
/usr/lib/hyprland/plugins/<name>.so
```

Das ist der Pfad, den `zepos-generate` prueft, den es in die erzeugte
`plugins.conf` schreibt und den `zepos-doctor` gegen die Wirklichkeit haelt
(§7.4). Er ist in `src/plugins.py` einmal definiert; ein Paket, das woanders
ablegt, ist ein Paket, dessen Plugin nie geladen wird.

### 4.3 Nachtrag: fuenf Bestandteile liegen nur im AUR

Bei der Vorbereitung der Paketierung gegen einen Container mit reinen
Arch-Repos zeigte sich, dass fuenf Bestandteile des Desktops dort nicht
existieren. Sie waren auf dem Entwicklungsrechner installiert und deshalb in
der urspruenglichen Fassung dieser Spec als vorhanden abgehakt worden:

| Fehlt in extra/core | Wofuer ZepOS es braucht |
|---|---|
| `hyprbars` | Titelleisten, im `plugin { }`-Block konfiguriert |
| `borders-plus-plus` | geladen, ohne ZepOS-Vorgaben (§7.4) |
| `aylurs-gtk-shell` (AGS) | traegt 15 Templates |
| `hyprland-qtutils` | Hyprlands eigene Dialoge |
| `wlogout` | 3 Templates — seit 11.08.2026 durch ZepOS' eigenes `zepos-logout` ersetzt: wlogout steht gemessen auf `libgtk-3.so.0`, und sein Ursprung (HEAD 350fe88, 26.05.2024) nennt GTK4 nirgends. Die Zeile bleibt, weil die Aussage der Tabelle - in extra/core fehlt es - unveraendert stimmt. |

Ein sechster Eintrag, `hyprland-plugins`, stand hier als „Sammelrepo der
ersten beiden". Das war ein hyprpm-Begriff: hyprpm fuegt ein Repo hinzu und
aktiviert Plugins daraus. Ohne hyprpm (§7.2) ist `hyprwm/hyprland-plugins`
eine Quelle, aus der zwei Pakete gebaut werden, und kein drittes Paket.

Fuer einen Arbeitsplatz reicht dafuer ein AUR-Helfer. Fuer eine Distribution,
die reproduzierbar aus einem gepinnten Stand baut, nicht: AUR-Pakete haben
keinen Stichtag, keine Signatur und keine Zusage, morgen noch zu bauen.

**Entscheidung: ZepOS paketiert alle fuenf selbst**, mit gepinnter Version und
Signatur wie die eigenen Pakete. Zusammen mit `zepos-hyprland` steht die
Paketzahl damit bei zwoelf (§4.2). Die fuenf sind Uebersetzungen bestehender
AUR-Rezepte, keine Neuentwicklung.

### 4.3 Nachtrag zum Nachtrag: das Auswahlfenster ist das sechste

Am 11.08.2026 entschieden: **ZepOS benutzt durchgehend GTK4, und was es dafuer
nicht gibt, baut ZepOS selbst.** Der erste Fall davon ist das Auswahlfenster.

Gemessen: `wofi` ist GTK3 — `objdump -p /usr/bin/wofi | grep NEEDED` nennt
`libgtk-3.so.0` und sonst kein Toolkit. Es trug sechs erzeugte Stellen, darunter
beide Ersatzbloecke aus §7.4. Ein GTK4-Ersatz existiert im angehefteten
ALA-Schnappschuss 2026/08/04 nicht: `tar tzf extra.db` zaehlt 14860 Pakete und
darunter ist kein `walker`, kein `tofi`, kein `anyrun` und kein
`rofi-wayland`; `fuzzel` (1.14.1) ist da und benutzt gar kein GTK, sondern
zeichnet selbst — womit es von dem Stylesheet abgeschnitten waere, das
`src/brand.py` fuellt.

Also **`zepos-menu`**, als eigenes Paket wie die fuenf oben: GTK4 ueber
PyGObject, `gtk4-layer-shell` 1.3.0, zwei Betriebsarten (`--show drun` und
`--dmenu`) und genau die neun Schalter, die die sechs Aufrufer benutzt haben.
Die Paketzahl steht damit bei dreizehn.

Nebenbefund, der zeigt, wie unsichtbar so etwas bleibt: wofis erzeugtes
`style.css` hat nie funktioniert. Es setzte seine Farben ueber CSS-Variablen,
die GTK3 nicht kennt — 39 Parserfehler, jede betroffene Regel verworfen, der
Starter seit jeher in GTKs Standardgrau. `zepos-menu` ist damit nicht der
Nachbau eines Aussehens, sondern das erste.

Selbst gebaut und gepinnt: **Hyprland 0.56.1**, als `zepos-hyprland`. Es stand
hier in der Liste der aus Arch nutzbaren Pakete; die Revision zu §7 hat das
aufgehoben, und ein Hyprland aus `extra` wuerde genau die Kopplung
zuruecksetzen, gegen die dort entschieden wurde.

Gepinnt und aus den Arch-Repos nutzbar bleiben: Waybar 0.15.0, Kitty 0.48.2,
GTK4 4.22.4, libadwaita 1.9.2, PyGObject 3.56.3, iwd 3.12,
NetworkManager 1.58.0, archinstall 4.4, PipeWire 1.6.8.

`zepos-config` legt ab:

```
/usr/share/zepos/templates/                  Templates, read-only
/usr/share/zepos/styles/                     Style-Templates
/usr/share/zepos/system/                     System-Templates (sudoers-Drop-in)
/usr/share/zepos/*.py                        SSOT + Prozessor
/usr/bin/zepos-generate                      Generator-CLI
/usr/bin/zepos-settings                      Settings-CLI
/usr/bin/zepos-doctor                        Diagnose
/etc/skel/.config/zepos/user-settings.json   Default für neue Nutzer
```

`/etc/skel` sorgt dafür, dass jeder neu angelegte Nutzer automatisch eine
funktionierende Konfiguration erhält, ohne dass der Installer etwas kopiert.

In beiden Auflistungen stand hinter jedem Verzeichnis eine Anzahl — „82
Templates" im Repo-Layout (§4.1), „75 Templates / 20 Style-Templates /
1 Template" hier.
Die erste war zweimal still veraltet: gezählt wurden zuletzt 75. Eine Zahl in
einem Entwurfsdokument ist eine Behauptung über den Arbeitsbaum von genau einem
Tag, und kein Test kann sie halten — der Baum ändert sich mit jedem Template,
das Dokument nicht. Sie steht deshalb nicht mehr da. Wer die aktuelle Zahl
braucht, zählt sie: `ls src/templates/*.template | wc -l`.

Die Rechnung in §6.1 bleibt davon unberührt. Sie ist kein Zustand des Baums,
sondern das Protokoll einer Entscheidung: 96 vorgefunden, 16 gelöscht, 2 neu.

---

## 5. Konfigurationsmodell

Im Ursprungsprojekt war ein einziges Verzeichnis unterhalb von `~/.config`
gleichzeitig Quellcode, Konfiguration und Arbeitsverzeichnis. Ein Pacman-Paket
darf nichts unterhalb von `~` besitzen, deshalb wird getrennt:

| Ort | Inhalt | Eigentümer |
|---|---|---|
| `/usr/share/zepos/` | Templates, Generator, SSOT | Paket, read-only |
| `~/.config/zepos/user-settings.json` | Nutzereinstellungen | Nutzer |
| `~/.config/zepos/templates/` | Template-Overrides | Nutzer |
| `~/.config/hypr`, `waybar`, `kitty`, … | generierte Konfiguration | `zepos-generate` |

**Effekt:** `pacman -Syu` aktualisiert Templates, ohne Nutzeranpassungen zu
überschreiben. Beim Aufbau des Ursprungsprojekts hätte ein Update lokale
Änderungen zerstört.

### 5.1 Template-Overrides (ab Tag 1)

Der Generator sucht jedes Template in dieser Reihenfolge:

1. `~/.config/zepos/templates/<name>.template`
2. `/usr/share/zepos/templates/<name>.template`

Der erste Treffer gewinnt. Diese Auflösung muss von Anfang an im Generator
stecken — sie später nachzurüsten hieße, jede einzelne Template-Suche
anzufassen.

### 5.2 Versionierte Konfiguration (ab Tag 1)

`user-settings.json` enthält `"schema_version": 1`. Ohne dieses Feld wäre bei
der ersten Migration unbekannt, welche Struktur eine Datei auf einem fremden
System hat.

---

## 6. Entkernung

### 6.1 Ersatzlos gelöscht

| Gruppe | Dateien |
|---|---|
| Interne Projekte | `internal-terminals`, `internal-assistant`, `internal-logs`, `internal-service-terminals`, `ide-workspace-layout` |
| OneDrive | `onedrive-control`, `onedrive-status`, `onedrive-debug` |
| Hardwaregebunden | `printer-install-modelA`, `printer-install-modelB`, `printer-status`, `kvm-switch`, `kvm-profile` |
| Standortgebunden | `waybar-wttr-cityA`, `waybar-wttr-cityB` |
| Hypervisor | `network-repair-hypervisor` + Verzeichnis `hypervisor-scripts/` |
| Firmen-Profile | `profiles/workstation-01`, `workstation-02`, `workstation-03`, `workstation-04` |
| Toter Code | `templates/deprecated/` (6 Dateien) |

Verifiziert: 96 Templates im Wurzelverzeichnis, 16 davon zum Löschen
identifiziert, 80 bleiben.

Das Verzeichnis `deprecated/` wird gelöscht statt mitgenommen — toter Code wird
nicht konserviert.

### 6.2 Neu, generisch

| Neu | Ersetzt |
|---|---|
| `printer-manager-config.template` | `printer-install-modelA`, `printer-install-modelB`, `printer-status` — CUPS-Dialog ohne Modellbindung |
| `waybar-weather-config.template` | `waybar-wttr-cityA`, `waybar-wttr-cityB` — Ort aus `user-settings.json` |

**Endstand dieser Inventur: 82 Templates** (80 + 2). Eine Zahl von genau diesem
Tag, nicht der heutige Stand des Baums — seither ist weiter gelöscht und
zusammengelegt worden. §4.3 erklärt, warum in den Layout-Auflistungen keine
Anzahl mehr steht.

### 6.3 Entkoppelt, Funktion bleibt

Vierzehn VPN- und Netzwerk-Templates sowie drei Styles bleiben vollständig
erhalten, verlieren aber jeden Bezug zum vorherigen Arbeitgeber:

`vpn-connect-script`, `vpn-control-config`, `vpn-status-config`,
`vpn-watcher-config`, `ags-vpn`, `ags-vpn-settings`, `network-watchdog-config`,
`network-watchdog-service`, `network-watchdog-waybar-config`,
`network-diagnostic-config`, `network-repair-config`,
`network-manager-gui-config`, `ags-network`, `ags-network-scripts`

Diese Werte wandern in `user-settings.json`:

| Heute hardcodiert | Fundort | Wird zu |
|---|---|---|
| `example.com` | `style_definition.py:1190`, `user_settings.py:257`, `ags-vpn-settings.template:93` | `vpn.dns.search_domain` |
| `10.0.0.1`, `10.0.0.2` | `vpn-connect-script.template` | `vpn.dns.servers[]` |
| `fileserver01` | `vpn-connect-script.template` | `vpn.test_host` |
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | drei fest ausgeschriebene Child-SAs | `vpn.routed_networks[]`, beliebige Anzahl |

Der letzte Punkt ist mehr als Textersatz: der swanctl-Block wird aus der Liste
**generiert**. Ein Netz ergibt eine Child-SA, fünf Netze ergeben fünf.

### 6.4 Umbenennung

Im vorgefundenen Baum kam der Name des Ursprungsprojekts — die Herkunftszeile
oben nennt ihn — 232× in 107 getrackten Dateien vor, die Schreibweise mit
Leerzeichen weitere 96×. Davon waren 30 Vorkommen ein Pfad unterhalb von
`$HOME/.config`.

Diese 30 waren **keine** einfache Ersetzung: je nach Zugriffsart wurde daraus
`/usr/share/zepos` (lesend) oder `~/.config/zepos` (schreibend). Handarbeit pro
Treffer.

Hier stand: „Hardcodierte Vorkommen von `~` gibt es nicht — das Repo ist bereits
pfad-portabel." Beide Hälften waren falsch, und die zweite folgte aus der ersten
ohnehin nicht.

Schon die Zählung stimmt nicht: `~/` steht 123× unter `src/`. Schwerer wiegt der
Schluss. Gesucht wurde nach `~`, also nach der **portablen** Schreibweise. Der
unportable Fall schreibt sich anders — als Absolutpfad in ein fremdes
Home-Verzeichnis, und den findet diese Suche nie:
`restore-latest-backup-config.template` hatte
`CONFIG_PATH="/home/<nutzer>/.config/hypr/hyprland.conf"` — mit dem echten
Anmeldenamen des Autors darin — und die Entsprechungen für Waybar und Kitty an
sechs Stellen fest verdrahtet, `zshrc-config.template` denselben fremden Pfad
ein siebtes Mal, und zwei weitere Zeilen zeigten auf ein Quellverzeichnis unter
`/mnt/<quellwurzel>`.

Getroffen hat es ausgerechnet das Werkzeug, mit dem sich eine misslungene
Generierung rückgängig machen lässt — `validate_output.py:96-98` nennt es als den
Grund, warum überhaupt Backups geschrieben werden. Auf jedem anderen Rechner
meldete `restore-latest-backup hyprland` „Config file not found" und beendete
sich mit 1, während das Backup unberührt daneben lag. Die Pfade kommen jetzt aus
`${XDG_CONFIG_HOME:-$HOME/.config}`, derselben Regel, der `generate_config.sh:30`
folgt; `tests/src/test_restore_backup.py` führt das Werkzeug in einer Sandbox
aus, statt seinen Text zu prüfen.

Zuletzt trug ein einziges Modul den Namen noch: der Template-Prozessor. Er heißt
jetzt `template_processor.py` — benannt nach dem, was er tut, statt nach dem
Projekt, aus dem er stammt. Damit ist unter `src/` kein Vorkommen mehr übrig.
`tests/src/test_naming.py` hält das fest und kennt seit dieser Umbenennung auch
die Schreibweise mit Unterstrich; genau an der hatte sein Muster zuvor
vorbeigesehen, weshalb dieses eine Modul übrig bleiben konnte, während der
Wächter grün meldete.

### 6.5 Monitor-Erkennung

`hypr-monitor-detect-config.template` erkennt Monitore heute über `$(hostname)`
und lädt ein vorgefertigtes Profil mit fest verdrahteten Seriennummern
(z. B. `Hersteller Modell Seriennummer`). Auf fremder Hardware
greift das ins Leere.

ZepOS dreht das um: Erkennung über EDID der tatsächlich angeschlossenen Ausgänge
via `hyprctl monitors -j`. Beim ersten Start wird ein Profil **erzeugt** statt
eines bekannten geladen. Der Hostname spielt keine Rolle mehr.

Profile bleiben als Konzept erhalten — mehrere speicherbar und umschaltbar — sie
entstehen nur nicht mehr aus einer Liste bekannter Firmenrechner.

### 6.6 Entkernung im Dateiinneren

Die Liste in 6.1 ist nach **Dateinamen** gebaut. Das genügt nicht, und der
teuerste Beweis dafür stand in der größten verbliebenen Vorlage: sie trug den
Werkzeugkasten des vorherigen Arbeitgebers _in sich_.

`zshrc-config.template` umfasste 772 Zeilen. 485 davon waren eine Shell-Funktion
`zepos()` mit dem Produktportfolio, den Repository-Namen je Modul, einer
Quellwurzel unter `/mnt/<quellwurzel>`, Dienstports und einem Conda-Interpreter
unter `/opt/internal-data`; 76 weitere hoben deren Flags in der Shell farbig hervor. Die Datei
ist keine Karteileiche — `generate_config.sh:514` schreibt sie nach
`$HOME/.zshrc`, sie läuft also bei jedem Terminalstart. Zwei Zeilen ihrer Hilfe
warben mit einem Modus, der einen Build durch einen cgroup-gebundenen
WireGuard-Tunnel schickt, und nannten das kommerzielle Intrusion-Detection-System,
für das er unsichtbar sein soll, beim Namen.

Entfernt: 595 Zeilen, dazu die Ticket-Kennungen zweier interner Vorgänge, der
Pfad eines GPG-verschlüsselten sudo-Passworts in einem `pass`-Store und die
SSH-Haltung um einen bestimmten YubiKey. Übrig bleiben 181 Zeilen: Oh-My-Zsh,
Prompt, PATH, die Profil-Aliase — und der Drop-in-Lader für `~/.zshrc.d/*.zsh`,
der ausdrücklich stehen bleibt. Ohne ihn verschwinden die eigenen Befehle des
Nutzers bei der nächsten Generierung, ohne dass etwas sichtbar kaputtgeht.

Drei weitere Vorlagen trugen Reste desselben Werkzeugkastens, die eine
Namenssuche ebenfalls nicht findet: `hyprland-universal-config.template`
(Fensterregeln für zwei seiner Binaries), `vpn-connect-script.template`
(Kommentare mit seiner Netzkomponente, einer internen Ticketnummer und dem
WLAN-Interface einer bestimmten Maschine) und `ags-style.template` (Themenname).

Gehalten wird der Zustand von `tests/src/test_inventory.py`, nach dem Muster der
Monitor-Prüfung: Regeln auf die **Form** eines fremden Werkzeugkastens —
Kommandoname, Modulschema `<produkt>-client-<fläche>`, Ticket-Kennung,
Tunnel-Vokabular, Absolutpfade genau einer Maschine — plus ein Meta-Test, der
jede Regel gegen eine Zeile prüft, die sie fangen muss, und gegen eine, die sie
in Ruhe lassen muss. Ohne diese zweite Hälfte lässt sich jede Prüfung so lange
verschärfen, bis sie nichts mehr trifft; genau in diesem Zustand meldete die
Namensliste die Entkernung als erledigt.

Was `~/.zshrc` betrifft, prüft `tests/src/test_zshrc.py` das Ergebnis mit
`zsh -n`. Der Staging-Validator kann das nicht: er lässt `bash -n` über einer
zsh-Datei bewusst aus — festgehalten in
`test_a_shell_script_without_the_suffix_is_still_checked` —, weshalb die erzeugte
Login-Shell sonst das einzige Artefakt ohne jede Syntaxprüfung wäre.

---

## 7. Plugin-ABI und Failsafe

> **Revision nach Abschluss des Installers.** Die urspruengliche Fassung dieses
> Abschnitts liess Hyprland aus den Arch-Repos kommen und pinnte nur die Plugins
> dagegen. Das loest die Kopplung nicht auf, es verschiebt sie: Arch entscheidet
> weiterhin, wann eine neue Hyprland-Version erscheint, und damit wann die fuenf
> Plugins brechen. Der Nutzer sieht davon nichts, bis sein Desktop haelt.
>
> ZepOS liefert Hyprland deshalb selbst als `zepos-hyprland` aus, mit `provides`
> und `conflicts` gegen das Arch-Paket. Die Plugin-Pakete haengen an diesem, nicht
> an Arch. Ein Versionssprung ist damit eine bewusste Entscheidung, die Hyprland
> und alle fuenf Plugins in einem Zug bewegt, statt eines Ereignisses, das dem
> Projekt zustoesst.
>
> Preis, ehrlich benannt: ZepOS verfolgt Hyprland-Releases selbst und baut sie
> nach. Das ist Pflegeaufwand, den ein Distributionsprojekt aber ohnehin traegt -
> und er faellt an einer Stelle an, wo er sichtbar ist, statt bei jedem Nutzer
> einzeln.

### 7.1 Ausgangslage

ZepOS hängt an **fünf** ABI-gekoppelten Hyprland-Plugins:

| Plugin | Herkunft | Kontrolle |
|---|---|---|
| `hyprlaunch` | `plugins/hyprlaunch/` in diesem Baum | eigen |
| `hyprclipx` | `plugins/hyprclipx/` in diesem Baum | eigen |
| `hyprzones` | `azzuriel/hyprzones`, Commit gepinnt | fremd, gepflegt |
| `hyprbars` | `hyprwm/hyprland-plugins` | fremd |
| `borders-plus-plus` | `hyprwm/hyprland-plugins` | fremd |

> **Am 11.08.2026 hat sich die mittlere Spalte fuer drei Zeilen geaendert, und
> die rechte fuer eine.** Hier stand dreimal "eigen" fuer Baeume, die auf einem
> fremden Konto lagen und zur Bauzeit heruntergeladen wurden — "eigen" hiess
> also "von uns benutzt", nicht "von uns gehalten".
>
> GEMESSEN an der GitHub-API: alle drei haben 0 Tags, 0 Forks, einen
> Beitragenden und `"license": null`; `hyprlaunch` hatte seinen letzten Commit
> am 10.02.2026, also vier Hyprland-Minor-Versionen vorher. Die Portierung auf
> 0.56 steht in diesem Baum, nicht dort — ZepOS war schon der Pfleger und besass
> die Quelle nur nicht.
>
> `hyprlaunch` und `hyprclipx` liegen deshalb jetzt unter `plugins/`. Der
> Auslöser war nicht die Verfuegbarkeit, sondern die Anpassung: ihr Aussehen
> stand als `static const char* ...CSS` im uebersetzten Objekt (116 und 168
> Zeilen, 20 und 37 Farbliterale), ihre Fenstermasse als `static constexpr`
> daneben. Beides konnte `src/brand.py` und `src/sizes.py` grundsaetzlich nicht
> erreichen, und eine Anpassung in einem fremden Baum ist bei der naechsten
> Commit-Anhebung wieder weg.
>
> `hyprzones` bleibt draussen, mit Begruendung: es hat keine eigene GTK4-
> Oberflaeche (sein AGS-Editor wird nicht ausgeliefert), es haengt am tiefsten
> am Compositor (52 API-Zeilen in `main.cpp`, gegen 17 bei `hyprlaunch`), und
> sein Ausfall kostet keine Taste, die der Nutzer braucht — §7.4 gibt ihm
> bewusst keinen `zepos-plugin-missing`-Zweig. Was offen bleibt, ist die
> Verfuegbarkeit seines Ursprungskontos.

Die beiden hyprwm-Plugins werden im Gleichschritt mit Hyprland veröffentlicht,
das Risiko ist gering. `hyprbars` ist mit ZepOS-Icons und -Farben konfiguriert —
inzwischen in `hyprland-plugins-config.template`, siehe §7.4.

Referenzstand: **Hyprland 0.56.1** (§4.3), AGS 3.1.2, Waybar 0.15.0,
Kitty 0.48.2. Hier stand 0.55.4 und Kitty 0.47.4, beides aelter als der
Pin in §4.3 — und 0.55.4 ist genau die Version, gegen die die drei eigenen
Plugins nicht mehr uebersetzen.

Nicht auf dieser Liste und damit auch nicht ausgeliefert: `hyprexpo`,
`hyprtrails`, `hyprWorkspaceLayouts`, `hyprscrolling`, `xtra-dispatchers`.
Fuer die ersten drei stand eine Konfiguration im `plugin { }`-Block, das
Layout `workspacelayout` aus dem dritten war sogar als
`general:layout` gesetzt, und alle sechs standen in der hyprpm-Liste von
`install-system.sh`. Konfiguration fuer ein Plugin, das das Projekt nicht
ausliefert, ist auf jeder Installation wirkungslos; sie ist entfernt.

`hy3` wird **nicht** benötigt: es erscheint nur in der Dokumentation und in
`ide-workspace-layout-config.template`, das gelöscht wird, und ist nicht installiert.

### 7.2 Abkehr von hyprpm

Heute lädt hyprpm die Plugins und baut sie **pro Nutzer** nach
`~/.local/share/hyprpm/`. Für eine Distribution ist das falsch herum.

ZepOS liefert die `.so`-Dateien fertig gebaut nach
`/usr/lib/hyprland/plugins/` aus. Die generierte Konfiguration lädt sie direkt:

```
plugin = /usr/lib/hyprland/plugins/hyprlaunch.so
```

Nicht in `hyprland.conf`, sondern in dem Include aus §7.4 — und nicht als
Template-Zeile, sondern von `src/plugins.py` geschrieben, damit der Pfad in
der Datei zwangslaeufig der Pfad ist, der gerade geprueft wurde.

Kein Kompilieren beim Nutzer, kein hyprpm im Spiel. **Umgesetzt:**
`setup_hyprpm()` in `install-system.sh` ist entfernt — vier
`hyprpm add <GitHub-URL>` ohne jeden Ref und sechs `hyprpm enable`, drei davon
fuer Plugins, die ZepOS gar nicht konfiguriert. Ebenso entfernt sind
`exec-once = hyprpm reload -n` und `exec-once = mkdir -p /run/user/1000/hyprpm`
(letzteres mit fest verdrahteter UID 1000) aus
`hyprland-universal-config.template`, und die Rebuild-Anweisung
`hyprpm update` aus `zepos-doctor`. `install-system.sh` installierte damit
**keine** Plugins mehr: es richtete einen bestehenden Arch-Rechner ein, auf dem
es die ZepOS-Pakete nicht gibt. Das ist kein Verlust, sondern der Normalfall,
fuer den §7.4 gebaut ist.

### 7.2.1 Nachtrag: `install-system.sh` ist geloescht

Das Skript stammte strukturell unveraendert aus dem Ursprungsprojekt und
richtete den Arbeitsplatz seines Autors ein. Es widersprach jeder Entscheidung
dieses Dokuments: `sudo pacman -Syu` auf dem Rechner des Nutzers, ein
`git clone` des AUR-Helfers ohne jeden Ref und `makepkg -si` daraus, vier
`libastal-*-git`, die bei jedem Lauf aus dem jeweiligen HEAD neu uebersetzen
(§4.3 pinnt und signiert stattdessen), eine 60-Sekunden-Schleife, die die
sudo-Freigabe wachhielt, `chmod +x` und ein `fetch_icons.sh` **im
Paketwurzelverzeichnis** (§5: ein Paket ist read-only), PATH-Zeilen angehaengt
an `~/.bashrc` und `~/.zshrc`, und vierzehn Verzeichnisse unter `$HOME`, die
§4.2 `/etc/skel` zuweist.

Eine Distribution installiert aus Paketen, nicht aus einem Shell-Skript. Was
das Skript sonst noch tat und was heute weder ein Paket noch ein Template
abdeckt, ist damit die Liste fuer TP3:

| Was | Wohin es gehoert |
|---|---|
| Paketinventar (~104 aus den Repos + 12 aus dem AUR, in 21 Gruppen) | `depends` von `zepos-desktop` (TP3-1) |
| `systemctl enable` fuer bluetooth, NetworkManager, cups, power-profiles-daemon | Paket-Presets oder Installer |
| `gsettings set org.blueman.general notification-daemon false` | Template oder Paket-Postinstall |
| `sensors-detect --auto` (davon lebt das Waybar-Temperaturmodul) | Installer oder Erstlauf |
| vierzehn Verzeichnisse unter `$HOME` | `/etc/skel` (§4.2) |
| `export PATH` in `~/.bashrc` | `/etc/skel/.bashrc`; fuer zsh erledigt das `zshrc-config.template` |
| `--check`: welche Pakete fehlen | `zepos-doctor` |

Der letzte Stand des Skripts steht in `git show 298e887:src/install-system.sh`.

### 7.3 Versionsbereich statt Punkt-Pin

Ein exakter Pin (`hyprland=0.55.4`) wäre ein schwerer Fehler: Arch unterstützt
keine Teil-Updates, ein zurückgehaltenes Hyprland friert praktisch das gesamte
System ein. Nach Monaten ohne Rebuild hätten Nutzer ein nicht mehr
aktualisierbares System.

Stattdessen `zepos-hyprland>=0.56.1` **und** `zepos-hyprland<0.57.0`.
Patch-Updates laufen durch, nur Minor-Spruenge halten an — genau dort bricht
das Plugin-ABI tatsaechlich. Hier stand `hyprland>=0.55.4` /
`hyprland<0.56.0`: falscher Bereich (die Plugins sind auf 0.56.1 portiert)
und falsches Paket (§4.2).

### 7.4 Der Desktop muss ohne Plugins starten

Das ist die eigentliche Absicherung. Umgesetzt als `src/plugins.py` plus
`src/templates/hyprland-plugins-config.template`, erzeugt nach
`~/.config/hypr/plugins.conf`, das `hyprland.conf` sourcet.

**Nicht nur die `plugin=`-Zeilen.** Drei Formen hoeren auf zu funktionieren,
sobald ein Plugin nicht geladen ist, und alle drei sind Fehler in der einen
Datei, deren Scheitern die Sitzung kostet:

| Form | Beispiel |
|---|---|
| die Ladezeile | `plugin = /usr/lib/hyprland/plugins/hyprbars.so` |
| der Einstellungsblock | `plugin { hyprbars { bar_height = 25 } }` |
| ein Bind mit Plugin-Dispatcher | `bind = SUPER, SPACE, hyprlaunch:toggle,` |

Gemessen mit `Hyprland --verify-config` gegen eine Konfiguration, die auf einer
Maschine ohne jedes Plugin-Objekt erzeugt wurde: die dritte Form ist die, die
Hyprland ablehnt — drei `Invalid dispatcher`-Fehler, Exit 1. Die anderen beiden
laufen bei 0.55.4 stumm durch, was sie nicht besser macht: ein
`general:layout = workspacelayout` ohne das Plugin ist ein Layout, das niemand
registriert hat, und niemand erfaehrt es.

Alle drei stehen deshalb in `plugins.conf` und nirgendwo sonst. Ein Block
kommt hinein, wenn das dazugehoerige `.so` da ist; sonst steht dort ein
Kommentar mit Grund, Paketname und dem Befehl zum Nachziehen. Fuer die zwei
Tasten, deren Ausfall am meisten weh tut, gibt es einen Ersatzblock: SUPER+SPACE
(Starter) faellt auf `zepos-menu --show drun` zurueck, SUPER+SHIFT+V
(Zwischenablage) auf `cliphist-menu.sh`. Hier stand bis zum 11.08.2026 `wofi`
in beiden Zeilen — siehe den Nachtrag in §4.3. Eine Datei aus lauter Kommentaren ist
eine gueltige Hyprland-Konfiguration — gemessen: **`config ok`, Exit 0**.

Schlimmster Fall damit: „meine Zonen fehlen heute" statt „schwarzer Bildschirm".

**Zu welchem Zeitpunkt „vorhanden"?** Beim Erzeugen — und das Erzeugen ist an
den Sitzungsstart gerueckt. Spaeter geht nicht: Hyprland liest `plugin=` beim
Parsen der Konfiguration, bevor irgendetwas von ZepOS in der Sitzung laufen
koennte, also kann „beim Start pruefen" nur „vor dem Compositor pruefen"
heissen. `start-hyprland` erzeugt die Datei unmittelbar vor dem `exec` neu, so
dass die Antwort auf dem unterstuetzten Startweg hoechstens ein `exec` alt ist.

Was das offen laesst — ein `pacman -Syu` mitten in der Sitzung, ein Login ueber
einen Display-Manager an `start-hyprland` vorbei — bleibt nicht stumm, und das
ist die Bedingung, unter der der Zeitpunkt ueberhaupt vertretbar ist:

* die Datei benennt jedes uebersprungene Plugin, das gesuchte Objekt, das Paket
  und den Befehl;
* `zepos-doctor` liest die **liegende** Datei und meldet eine Ladezeile, deren
  Objekt nicht mehr da ist (`check_plugin_objects`);
* `zepos-doctor` meldet eine ABI-Abweichung aus der laufenden Sitzung
  (`check_plugin_abi`, braucht `hyprctl version -j` und ist damit ueberhaupt
  nur dort zu beantworten).

Die ABI gehoert damit ausdruecklich **nicht** in den Generator: vor dem Start
gibt es keinen Compositor, den man fragen koennte. Der Generator beantwortet,
was er beantworten kann — liegt das Objekt da —, und `pacman` haelt den Rest
zusammen, weil die Plugin-Pakete auf `zepos-hyprland>=0.56.1,<0.57.0` haengen
(§4.2).

Ob der Nutzer Plugins ueberhaupt will, entscheidet `plugins.enabled` aus
`user-settings.json`. Der Installer fragt das (§8.2 Schritt 6) und schreibt es
seit jeher in das Zielsystem — gelesen hat es bis hierher nichts.

Als Rückfallebene dient das vorhandene `hyprland-failsafe-config.template`
(`monitor=,preferred,auto,1`, alle Workspaces auf Monitor 0, Notfall-Keybinds).
Es wird ausgebaut statt neu erfunden.

`zepos-doctor` meldet einen Mismatch im Klartext samt Rebuild-Anweisung.

---

## 8. ISO und Installer

```
iso/
  profiledef.sh        iso_label=ZEPOS_<YYYYMM>, UEFI + BIOS
  packages.x86_64      base, linux, linux-firmware, zepos-keyring,
                       zepos-installer, zepos-installer-gui, zepos-installer-tui
  pacman.conf          [zepos] Server = file:///opt/zepos-repo  +  ALA-Stichtag
  airootfs/
    opt/zepos-repo/    die sechs signierten System-Pakete
```

### 8.1 Aufbau des Installers

Der Installer ist keine Hülle um `archinstall`, sondern eine eigene Komponente
in drei Schichten:

```
   UI  (GTK4 oder TUI)
        │  füllt
   ZepOS-Installkonfiguration   validiertes Datenmodell, als JSON speicherbar
        │  übersetzt nach
   archinstall-Config  →  archinstall führt aus
```

Die Oberfläche spricht **nie** direkt mit `archinstall`, sondern füllt
ausschließlich das Datenmodell. Das hat drei Folgen:

- Die Oberfläche ist austauschbar, ohne die Installationslogik anzufassen —
  GTK4 und TUI liegen auf demselben Kern, ohne doppelte Logik
- Das Modell ist serialisierbar, womit unbeaufsichtigte Installationen
  (`zepos-install --config datei.json`) ohne Zusatzaufwand möglich werden
- Die Logik ist ohne Oberfläche testbar

Ohne diese Trennung säße die Installationslogik in Dialog-Callbacks fest, und
ein späterer Oberflächenwechsel wäre ein Neuschreiben.

**Partitionierung, Bootloader und Basisinstallation übernimmt ausschließlich
`archinstall` (extra 4.4).** Ein eigener Partitionierer wäre Code, dessen Fehler
fremde Festplatten löschen.

### 8.2 Ablauf

1. Sprache und Tastaturlayout
2. **Netzwerk** — WLAN suchen, verbinden, Verbindung prüfen; alternativ
   Ethernet/DHCP
3. Festplatte — Ziel und Partitionsschema
4. Benutzer, Passwörter, Rechnername
5. Zeitzone und Locale
6. ZepOS-Optionen — Plugins, VPN-Vorkonfiguration, Wetterort
7. Zusammenfassung, Bestätigung, Installation

Beim ersten Login erzeugt `zepos-generate --init` die Konfiguration aus den
tatsächlich angeschlossenen Monitoren.

### 8.3 WLAN muss in das Zielsystem übertragen werden

Eine Verbindung in der Live-Umgebung bedeutet **nicht**, dass das installierte
System danach Netz hat. Der Installer schreibt das Verbindungsprofil ausdrücklich
in das Ziel:

```
/etc/NetworkManager/system-connections/<SSID>.nmconnection    Modus 600, root:root
```

Unterbleibt das, startet der Nutzer ein frisch installiertes System ohne
Netzwerk — auf einem Laptop ohne Ethernet-Anschluss ist er damit handlungsunfähig.
Dieser Fall gehört zwingend in die Testfälle (§11).

### 8.4 Paketquelle: online bevorzugt, offline als Rückfall

Nach Schritt 2 prüft der Installer die Verbindung:

| Lage | Verhalten |
|---|---|
| Netz vorhanden | Basissystem von den Arch-Spiegeln (ALA-Stichtag), ZepOS-Pakete aus dem ISO-Repo |
| ZepOS-Repo unerreichbar | Basissystem von den Arch-Spiegeln (ALA-Stichtag), ZepOS-Pakete aus dem ISO-Repo |
| Kein Netz | **Die Installation läuft nicht durch** |

Das Offline-Repo bleibt damit erhalten, verliert aber seine Rolle als Hauptweg.
Es kostet nichts zusätzlich, weil die Pakete ohnehin gebaut werden, und rettet
den Fall fehlender WLAN-Firmware.

> **Richtigstellung 11.08.2026.** Die zweite Zeile dieser Tabelle hieß
> „Kein Netz | Alles aus dem ISO-Repo“, und das war nie gebaut. Gemessen
> und im Quelltext nachgelesen: `probe()` entscheidet nur, wo die
> **ZepOS**-Pakete herkommen (`installer/core/source.py`, dessen Kopf es
> selbst sagt), und `mirror_config()` lässt `mirror_regions` in beiden
> Fällen leer — `pacstrap` zieht die Arch-Basis also immer über das Netz
> vom angehefteten ALA-Stichtag. Der Fall, den diese Zeile beschreibt,
> ist keine Rückfallebene, sondern eine Installation, die am ersten
> Paket abbricht. Was fehlt, ist ausgerechnet: 390 Pakete,
> 1 061 018 061 Byte komprimiert; siehe `iso/README.md`, Abschnitt
> „Offline installieren“.

### 8.5 Rückfall von GTK4 auf TUI

Die Live-Umgebung startet eine minimale Wayland-Sitzung für die grafische
Oberfläche. Kommt diese nicht hoch — fehlender Treiber, unbekannte GPU — startet
automatisch die TUI. Erkennung über den Rückgabewert des Sitzungsstarts, nicht
über eine Hardware-Liste.

Ohne diesen Rückfall wäre die ISO auf betroffener Hardware wertlos.

### 8.5b Was im Zielsystem stehen bleibt

Die Repository-Definition, mit der **installiert** wird, ist nicht die, die im
installierten System **stehen bleiben** darf.

Eine Offline-Installation nutzt `file:///opt/zepos-repo` — ein Verzeichnis der
Live-Umgebung. Nach dem Neustart existiert es nicht mehr, und jedes
`pacman -Syu` scheitert an einem unerreichbaren Repository. Das ist kein
Randfall: es ist der Normalfall jeder Installation ohne Netz.

**Zwingend für Teilprojekt 5:** Nach erfolgreichem `archinstall` trägt die
`pacman.conf` des Zielsystems genau eine `[zepos]`-Sektion, und die zeigt auf
das Online-Repository. Ein lokaler Eintrag, der nur der Installation diente,
wird entfernt. `runner.install()` hat dafür bereits einen Nachbereitungsschritt
(`_finish_target`), der heute das WLAN-Profil schreibt.

Der Testfall dazu gehört in denselben Schritt wie der WLAN-Profil-Test aus
§8.3: nach der Installation prüfen, dass die `pacman.conf` des Ziels keine
`file://`-Quelle enthält.

### 8.6 Signierung ab der ersten ISO

Das Offline-Repo würde auch unsigniert funktionieren. Wird jedoch später
signiert, muss **jedes bereits installierte System** den Schlüssel von Hand
importieren. Deshalb: Schlüsselpaar von Anfang an, ausgeliefert als
`zepos-keyring`.

### 8.7 Reproduzierbarkeit

`pacman.conf` der ISO pinnt einen Arch-Linux-Archive-Stichtag. Zwei Builds
desselben Commits ergeben dasselbe System. Ohne das ist eine Fehlermeldung eines
Nutzers nicht nachstellbar.

---

## 9. Fehlerbehandlung

### 9.1 Atomare Generierung

Der heutige Generator schreibt direkt nach `~/.config/hypr/`. Ein Abbruch auf
halber Strecke hinterlässt eine kaputte `hyprland.conf` — also einen nicht
startenden Desktop.

ZepOS arbeitet dreistufig: **Temp-Verzeichnis → validieren → verschieben.**
Schlägt die Validierung fehl, bleibt die alte funktionierende Konfiguration
unangetastet, und `zepos-generate` meldet den Grund.

### 9.2 Validierungen

- Keine unaufgelösten `{{PLATZHALTER}}` im Ergebnis
- Generierte Shell-Skripte bestehen `bash -n`
- Waybar- und AGS-JSON ist parsebar
- Plugin-Zeilen nur, wenn die `.so`-Dateien tatsächlich vorhanden sind

---

## 10. Build-Umgebung

Docker mit `archlinux:latest`. Verifizierter Stand:

- `sudo` ist mit NOPASSWD konfiguriert, `sudo -n` funktioniert
- Der Benutzer ist in `wheel`, **nicht** in `docker` — Docker erfordert `sudo`
- Docker Server 29.6.1, Daemon aktiv
- 710 GB frei
- Das Image `archlinux:latest` bringt `makepkg` und `repo-add` mit, aber **kein**
  `base-devel` — `fakeroot`, `gcc`, `cmake` und `git` müssen im Build-Schritt
  nachinstalliert werden

Der Nutzer hat `sudo` im Zusammenhang mit Docker ausdrücklich freigegeben.

Gebaut wird in einem Container mit `makepkg --syncdeps`; die fertigen Pakete
werden per `repo-add` in das Offline-Repo aufgenommen und signiert.

### 10.1 Container brauchen `--network host`

Bei der Verifikation trat ein Konflikt zutage, der jeden Bridge-Container ohne
Netzwerk lässt.

Der aktive IPsec-Tunnel routet **alle drei RFC1918-Bereiche** in die
Firmenumgebung:

```
10.0.0.0/8       dev wlan0 src <VPN-Adresse>
172.16.0.0/12    dev wlan0 src <VPN-Adresse>
192.168.0.0/16   dev wlan0 src <VPN-Adresse>
```

Die Docker-Bridge liegt bei `<Docker-Bridge>` und damit innerhalb von
`10.0.0.0/8`. Sämtlicher Container-Verkehr wird von den IPsec-Policies erfasst
und in den Tunnel geschickt, wo er verfällt. Zusätzlich erbt der Container den
per strongSwan injizierten Firmen-DNS `10.0.0.2`, der aus dem
Container-Namespace nicht erreichbar ist.

Ausweichen ist nicht möglich: da alle drei privaten Bereiche geroutet werden,
bleibt kein Subnetz übrig, in das die Bridge verschoben werden könnte.

**Vorgabe:** Alle Build-Container laufen mit `--network host`. Verifiziert
funktionsfähig, während der Tunnel steht. Alternative wäre, nur bei getrenntem
VPN zu bauen — als Vorgabe zu fragil.

### 10.2 Folgerung für ZepOS selbst

Dieser Konflikt ist kein lokales Ärgernis, sondern ein Konfigurationsfehler, den
ZepOS reproduzieren würde: `vpn.routed_networks` erlaubt es, den gesamten
RFC1918-Raum in einen Tunnel zu legen, und bricht damit still Docker, libvirt,
Podman und jedes andere Werkzeug mit eigenem Bridge-Netz.

`zepos-doctor` prüft deshalb, ob `vpn.routed_networks` Subnetze überdeckt, die
lokal von Container- oder Virtualisierungs-Bridges belegt sind, und warnt im
Klartext.

---

## 11. Testen

| Was | Wie | root nötig |
|---|---|---|
| ISO bootet | `qemu-system-x86_64 -cdrom ZepOS.iso -m 4G` | nein |
| Template-Rendering | Generator gegen Temp-Verzeichnis, Validierungen aus §9.2 | nein |
| Paketbau | `makepkg --syncdeps` im Container, **`--network host`** (§10.1) | nur für Docker |
| Installation | archinstall in QEMU gegen virtuelle Platte | nein |
| Installer-Kern | Datenmodell füllen, erzeugte archinstall-Config prüfen — ohne Oberfläche | nein |
| **WLAN im Zielsystem** | Nach der Installation prüfen, dass `/etc/NetworkManager/system-connections/<SSID>.nmconnection` existiert und Modus 600 hat (§8.3) | nein |
| TUI-Rückfall | ISO in QEMU ohne Grafikbeschleunigung starten, TUI muss erscheinen | nein |
| Offline-Installation | QEMU-Gast ohne Netzwerkgerät, Installation muss durchlaufen | nein |

Alle Arbeiten finden in `~/zepos/` statt. Das Repo `~/.config/iconmanager`
bleibt unangetastet — es ist die **laufende Konfiguration dieses Rechners**, und
deshalb steht sein Pfad hier ausgeschrieben: eine Regel, die ein Verzeichnis
nicht beim Namen nennt, kann niemand befolgen.

---

## 12. Offene Punkte

| Punkt | Status |
|---|---|
| GPG-Schlüsselpaar für `zepos-keyring` | muss erzeugt werden, Aufbewahrungsort offen |
| LICENSE in `hyprzones` | fehlt im Ursprungsrepo. Fuer `hyprlaunch` und `hyprclipx` am 11.08.2026 erledigt: `plugins/LICENSE`, und die Rezepte legen sie unter `/usr/share/licenses` ab. **GPL-3.0 war hier falsch** — die READMEs aller drei Repos nennen BSD-3-Clause, und fremden BSD-3-Code als GPL auszuliefern waere eine falsche Auskunft. Was die Lizenz verlangt, ist der Urhebervermerk, und den gab es nirgends; er ist in `plugins/LICENSE` zum ersten Mal ausgeschrieben. |
| Ziel-Repo auf GitHub | `ZeptronIT/zepos` oder `azzuriel/zepos` — offen |
| ALA-Stichtag für das erste Release | offen |
| Rebuild-Auslöser bei Hyprland-Minor-Update | manuell für v1; CI-Automatisierung später |

---

## 13. Teilprojekte

Diese Spezifikation beschreibt das Gesamtsystem. Die Umsetzung erfolgt in vier
Schritten mit je eigenem Implementierungsplan:

1. **ZepOS-Basis** — Fork, Entkernung, Umbenennung, Konfigurationsmodell
   (§3, §5, §6)
2. **Generisierung** — VPN/Netzwerk entkoppeln, Monitor-Autoerkennung, die zwei
   neuen Templates (§6.3, §6.5)
3. **Paketierung** — neun PKGBUILDs, Docker-Build, Signierung (§4.2, §7, §10)
4. **Installer** — Datenmodell, archinstall-Übersetzung, GTK4-Oberfläche,
   TUI-Rückfall, WLAN-Übertragung (§8.1 – §8.5)
5. **ISO** — archiso-Profil, Offline-Repo, Einbindung des Installers, Hyprland
   als Sitzung der Live-Umgebung, automatisierter Oberflaechentest in QEMU (§8, §8.6,
   §8.7)

Reihenfolge ist bindend: jeder Schritt setzt den vorherigen voraus.

Schritt 4 ist der umfangreichste Einzelposten. Er ist von Schritt 1 und 2
unabhängig — der Installer hängt nur an den fertigen Paketen aus Schritt 3 —
und ließe sich bei Bedarf parallel bearbeiten.
