# ZepOS

*[Read in English →](README.md)*

ZepOS ist eine Arch-basierte Linux-Distribution mit einem Hyprland/Wayland-
Desktop, ausgeliefert als bootfähiges Live-Medium mit eigenem grafischen
Installer. Alles, was auf dem Bildschirm steht – Installer, Anmeldemaske,
Leiste, Dock, Starter, Sperrbildschirm, Abmeldemenü, Einstellungen – ist für
dieses Projekt geschrieben, ist GTK4, und bezieht Farben, Abstände und
Schriftgrößen aus einer einzigen Datei.

**Hinweis zur Sprache:** Diese Datei und [`README.md`](README.md) sind
dasselbe Dokument in zwei Sprachen; beide müssen bei jeder Änderung
synchron gehalten werden. Die Build-Skripte und die Entwicklerdokumentation
sind Englisch; Quelltextkommentare und die Designdokumente in `docs/` sind
größtenteils Deutsch. Die ausgelieferte Benutzeroberfläche ist Englisch und
Deutsch.

---

## Status: Vor-Release. Bitte diesen Teil lesen.

ZepOS startet, installiert sich und kommt als funktionierender Desktop hoch.
Man sollte es aber noch nicht auf eine Maschine legen, die einem wichtig
ist, und das sind die konkreten Gründe dafür:

- **Ein lokaler Bau ist mit einem Testschlüssel signiert; eine
  veröffentlichte Version nicht.** `packaging/build.sh` braucht weiterhin
  einen Schlüssel, dem niemand vertrauen sollte – `packaging/make-test-key.sh`
  erzeugt genau wie bisher einen, mit der Benutzer-ID
  `ZepOS TEST KEY - DO NOT TRUST`, ohne Passphrase, mit 90 Tagen Laufzeit –
  weil der echte Signierschlüssel nie die Maschine verlässt, auf der er
  erzeugt wurde, und nie in den Arbeitsbaum eines Mitwirkenden gelangt. Was
  der echte Schlüssel tatsächlich signiert, steht unter [Pakete](#pakete).
- **Der Update-Kanal ist live, aber nur in einem Container erprobt.** Das
  `[zepos]`-Repository unter `https://zeptronit.github.io/ZepOS/$arch` ist
  öffentlich und antwortet. Der heutige Test hat ein Paket daraus in einen
  sauberen Container installiert, mit echtem `pacman` und echter
  Signaturprüfung gegen den Release-Schlüssel, und das ist gelungen. Was das
  noch nicht abdeckt: eine Maschine, die niemand beobachtet, mit dem
  geplanten Update-Timer unbeaufsichtigt, auf echter Hardware.
- **Secure Boot funktioniert nicht.** Gemessen: Die Boot-Kette trägt keine
  Signaturen, und Firmware mit aktiviertem Secure Boot lehnt den Loader ab.
  Secure Boot muss ausgeschaltet werden.
- **Eine Netzwerkverbindung ist zur Installation erforderlich.** Die
  Offline-Paketquelle bringt nur die ZepOS-Pakete auf das Medium; die
  Arch-Basis kommt weiterhin aus dem Netz, sodass eine Installation ohne
  Netzwerk fehlschlägt.
- **Die Hardwareabdeckung ist eine Maschine plus QEMU.** Es gibt keine
  Hardware-Matrix.
- **Nur zwei Sprachen:** Deutsch und Englisch.
- **Zwei von ZepOS' eigenen Plugins patchen Upstream-Bäume ohne Lizenz.**
  Siehe [Lizenz](#lizenz) – ZepOS hat die Erlaubnis, sie zu bauen und zu
  patchen; man erbt dadurch nicht automatisch eine eigene. Ihre unveränderte
  Quelle ist nicht Teil dieses Repositorys; die beiden Rezepte holen sie
  sich selbst, aus dem eigenen Repository des Autors, auf einen
  festgenagelten Commit.

Was bewiesen ist, und wo die Belege liegen: `iso/README.md` hält fest, was
jeder Boot und jede Installation tatsächlich getan hat, `packaging/README.md`
hält fest, was vor einer ersten echten Veröffentlichung stimmen muss, und
`docs/specs/2026-08-11-weg-zum-eigenen-os.md` ist die Roadmap, die die
verbleibende Arbeit ordnet.

---

## Für wen das hier ist

- Menschen, die einen Hyprland-Desktop wollen, der konfiguriert, in sich
  stimmig und installierbar ist – statt an einem Wochenende aus einem
  Dotfiles-Repository zusammengesetzt.
- Menschen, die lesen wollen, warum ein System so aufgebaut ist, wie es
  aufgebaut ist. Fast jede Entscheidung in diesem Baum steht direkt neben
  dem Code, zusammen mit der Messung, aus der sie stammt.

## Für wen das hier nicht ist

Das sind erklärte Nicht-Ziele, keine Lücken:

- **Andere Architekturen als x86_64.** Arch Linux selbst liefert offiziell
  nur x86_64 aus – ARM hat eine eigene, separate Distribution, nicht diese
  hier –, und ZepOS baut direkt auf Archs eigenem Werkzeugkasten und
  Paketarchiv auf, erbt diese Grenze also, statt sie selbst zu ziehen. Um
  die eine CPU explizit zu nennen, nach der manchmal gefragt wird: Ein AMD
  Ryzen ist x86_64. Dafür braucht es keine ARM-Unterstützung.
- **Migration einer bestehenden Installation.** ZepOS wird installiert,
  nicht umgewandelt.
- **Wahl der Desktop-Umgebung.** Es gibt einen Desktop, und das ist
  Hyprland. Das ist der Sinn des Projekts.
- **Alle, die heute Secure Boot oder eine Offline-Installation brauchen.**
  Siehe den Status-Abschnitt.

---

## Ausprobieren

### Ein Medium herunterladen

Vor-Release-Images liegen auf der
[Releases-Seite](https://github.com/ZeptronIT/ZepOS/releases). Vor dem
Schreiben die Prüfsumme kontrollieren:

```bash
sha256sum -c zepos-<version>-x86_64.iso.sha256
```

Mit dem Werkzeug, dem man schon vertraut, auf einen USB-Stick schreiben, mit
deaktiviertem Secure Boot starten, und das Medium startet den Installer. Es
gibt keinen Live-Desktop zum Vorab-Ausprobieren – das Release-Medium startet
direkt in den Installer und sonst nichts.

Zwei Dinge vor dem Herunterladen: Ein veröffentlichtes Image hinkt `main` um
die Zeit seit dem letzten Release hinterher, und seine Pakete sind mit
ZepOS' echtem Schlüssel signiert, nicht mit dem Testschlüssel, den sich ein
lokaler Bau selbst erzeugt – siehe [Pakete](#pakete). Das Medium selbst zu
bauen ist der einzige Weg, an den heutigen Stand des Baums zu kommen.

### Ein Medium selbst bauen

Beide Bauten laufen in Docker-Containern, weil ein Paket, das gegen das
gebaut wird, was zufällig auf einer Workstation liegt, eine
Abhängigkeitsliste hat, die diese Workstation beschreibt.

Benötigt werden `git`, `gpg`, `rsync`, `repo-add` (aus `pacman`), sowie
Docker erreichbar als **`sudo -n docker`** – die Skripte fragen nie nach
einem Passwort, also muss passwortloses `sudo` für `docker` vorher
eingerichtet sein. Für einen Release-Bau sollten etwa 10 GB freier
Speicherplatz eingeplant werden: gemessen, ein 3,5 GB großes
archiso-Arbeitsverzeichnis, ein 1,3 GB großes Image, und die Build-Container
obendrauf.

```bash
git clone https://github.com/ZeptronIT/ZepOS.git
cd ZepOS

# 1. Ein Signierschluessel. Der echte Schluessel steckt nie in diesem
#    Repository, darum erzeugt man sich fuer einen lokalen Bau einen
#    Testschluessel. Er heisst absichtlich DO NOT TRUST, hat keine
#    Passphrase und laeuft nach 90 Tagen ab. Er gibt den genauen naechsten
#    Befehl aus.
./packaging/make-test-key.sh

# 2. Die Pakete und das pacman-Repository, aus dem sie ausgeliefert werden.
ZEPOS_GNUPGHOME=packaging/keys/gnupg ./packaging/build.sh --key <ausgegebene ID>

# 3. Das Installationsmedium, aus genau diesen Paketen.
./iso/build.sh --profile release
```

Das Image und sein Manifest landen in `iso/out/` als
`zepos-<YYYY.MM.DD>-x86_64.iso` und `manifest-release.txt`. Die letzte Zeile
des Baus ist der Befehl, der das eben Gebaute in QEMU startet:

```bash
./iso/test-boot.py --scenario release
```

Nützliche Varianten – jede davon steht auch in der eigenen `--help` des
jeweiligen Skripts:

```bash
./packaging/build.sh zepos-config        # ein Rezept statt aller
./packaging/build.sh --no-sign           # ein unsigniertes Repository
./packaging/build.sh --rebuild-image     # auch den Build-Container neu bauen
./iso/build.sh                           # das Smoke-ISO (siehe unten), nicht das Medium
./iso/build.sh --snapshot current        # gegen die heutigen Spiegelserver bauen
```

Zu beachten: `--no-sign` lässt `zepos-keyring` und `zepos-desktop` bei einem
vollständigen Bau stillschweigend weg – ein Keyring-Paket rund um keinen
Schlüssel und ein Metapaket, das davon abhängt, können nicht existieren.

**Es gibt zwei ISO-Profile, und sie sind nicht austauschbar.**
`iso/profile/` ist ein Testgeschirr: Es meldet einen Nutzer automatisch an,
liefert sein eigenes `/etc/shadow`, installiert unbeaufsichtigt aus einer
Antwortdatei mit einem Root-Passwort darin, und setzt `console=ttyS0` auf
die Kernel-Kommandozeile. `iso/profile-release/` ist das Image, das man
weitergeben kann. Das Auslieferungsprofil wird aus einer Positivliste
(`iso/shared-with-release.txt`) zusammengesetzt statt als zweite Kopie zu
existieren, damit eine neue Datei im Testgeschirr nicht durch Vergessen bis
zu einem Download durchreicht.

---

## Wie es aufgebaut ist

### Das Vorlagensystem ist der Kern

Nichts in einem laufenden ZepOS ist eine Konfigurationsdatei, die jemand
von Hand bearbeitet hat. Zwei Single Sources of Truth –
`src/icon_definition.py` für Icons sowie `src/style_definition.py`
zusammen mit `src/brand.py` für Farben, Größen und Abstände – speisen
einen Prozessor, der `{{ICON_*}}`- und `{{STYLE_*}}`-Platzhalter in 82
Vorlagen unter `src/templates/` und 8 Stylesheet-Vorlagen unter
`src/styles/` einsetzt. Das Ergebnis ist die Konfiguration, die Hyprland,
AGS, kitty und der Rest tatsächlich lesen.

```
icon_definition.py ─┐
brand.py ───────────┼─► template_processor.py ─► generate_config.sh ─► ~/.config/{hypr,ags,kitty,…}
style_definition.py ┘        (82 + 8 Vorlagen)      (zepos-generate)
user-settings.json ─┘
```

Daraus folgen zwei Dinge, und beide tragen Gewicht:

- **Erzeugte Dateien werden nie bearbeitet.** Sie tragen eine
  „DO NOT EDIT“-Kopfzeile und werden beim nächsten Lauf überschrieben. Die
  Änderung gehört in die Vorlage.
- **Die Erzeugung ist atomar.** In ein temporäres Verzeichnis schreiben,
  validieren, dann verschieben. Ein fehlgeschlagener Lauf lässt die vorher
  funktionierende Konfiguration unangetastet.

```bash
zepos-generate --all          # alles neu erzeugen
zepos-generate --help         # jedes einzelne Ziel
zepos-doctor                  # was eine erzeugte Konfiguration nicht selbst pruefen kann
zepos-settings get            # jede Einstellung, mit ihrem aktuellen Wert
```

### Der Installer ist drei Schichten, und die Oberfläche spricht nie direkt mit archinstall

| Schicht | Inhalt |
|---|---|
| `installer/core/` | Datenmodell, Validierung, Laufwerkserkennung, LUKS2-Verschlüsselung, WLAN, Übersetzung zu `archinstall` |
| `installer/gui/` | GTK4-/libadwaita-Assistent – neun Seiten: Sprache, Netzwerk, Laufwerk, Partitionierung, Verschlüsselung, Benutzer, Zeit, ZepOS, Zusammenfassung |
| `installer/tui/` | Textoberfläche, verwendet, wenn die grafische Sitzung nicht starten kann |

Die Oberfläche füllt ein serialisierbares Konfigurationsmodell; eine
Übersetzungsschicht wandelt das in `archinstall`s JSON-Format um; ein
Runner ruft dessen dokumentierte Kommandozeilenschnittstelle auf. Damit
sind die beiden Oberflächen austauschbar, und eine unbeaufsichtigte
Installation braucht keinen zweiten Codepfad – `InstallConfig.from_dict()`
zusammen mit `installer.core.runner.install()` ist alles, was dafür nötig
ist.

Partitionierung, Bootloader und Basisinstallation übernimmt
[`archinstall`](https://github.com/archlinux/archinstall). Einen eigenen
Partitionierer zu schreiben würde bedeuten, Code zu schreiben, dessen
Fehler fremde Festplatten löschen.

`zepos-install` nimmt **keine Kommandozeilenargumente** entgegen. Es wählt
eine Oberfläche und startet sie; es gibt kein `--config`-Flag bei einem
Werkzeug, das Festplatten löscht. `ZEPOS_INSTALLER_SURFACE=gui` oder
`=tui` zu setzen erzwingt eine der beiden, und der Rückfall auf Text
passiert immer, bevor irgendein Fenster gezeigt wird.

### Pakete

`packaging/` enthält 20 Rezepte, die 25 signierte Pakete erzeugen, gebaut
in Abhängigkeitsreihenfolge in einem Container, der auf denselben
Arch-Linux-Archive-Snapshot festgenagelt ist wie das ISO. `zepos-desktop`
ist ein Metapaket, und seine `depends`-Liste entscheidet über die Form
eines installierten ZepOS – die Regel dafür steht oben in seiner
PKGBUILD: *eine Abhängigkeit ist ein Programm, das die erzeugte
Konfiguration von selbst startet, oder eines, das eine
Standard-Tastenkombination braucht, um zu tun, was die Taste verspricht.*

Der private Signierschlüssel gelangt nie in den Build-Container. Pakete
werden dort gebaut; signiert wird danach auf dem Host.

**Seit dem 19.08.2026 ist dieser Schlüssel echt.** Das veröffentlichte
Repository und jedes Paket darin sind signiert mit
`FF2EB06C08A57FEA9E33FC46157C1725A578B80C`, Benutzer-ID
`LeonMarzollDev (ZepOS Release)`, gültig bis 18.08.2028. Der Hauptschlüssel
kann nur zertifizieren (`[C]`); ein eigener Unterschlüssel (`[S]`)
übernimmt das eigentliche Signieren – die übliche Trennung zwischen dem
Schlüssel, der für die anderen bürgt, und dem Schlüssel, der im Alltag
benutzt wird. Sein öffentlicher Teil steht unter
[`zeptronit.github.io/ZepOS/zepos-repo.pub`](https://zeptronit.github.io/ZepOS/zepos-repo.pub);
das Paket `zepos-keyring` trägt dieselbe Datei, und das ist es, was ein
frisch installiertes System dazu bringt, ihm zu vertrauen, ohne dass
jemand einen Fingerabdruck von Hand eintippt – die Mechanik dahinter steht
in `packaging/README.md`. Ein lokaler Bau ist davon unberührt:
`./packaging/make-test-key.sh` erzeugt weiterhin einen Testschlüssel, weil
der echte keiner ist, den ein Build-Skript – oder dieses Repository –
jemals herausgeben könnte.

### Was man nach einer frischen Installation bekommt

`zepos-desktop` zieht Hyprland mit fünf Plugins, die AGS-Leiste und das
AGS-Dock, die ZepOS-Programme Menü / Sperrbildschirm / Abmeldung /
Einstellungen, kitty als Terminal, sowie `zepos-apps` – die Auswahl an
Programmen *anderer Leute*, die ZepOS trifft: Firefox, Nautilus, Loupe,
Papers, Celluloid, GNOME-Texteditor, Taschenrechner, Baobab, File Roller,
btop, CUPS. Jedes wurde GTK4-first gewählt, wo eine GTK4-Version
existiert, und der Grund steht neben dem Namen in
`packaging/zepos-apps/PKGBUILD`.

Zwei optionale Gruppen werden standardmäßig nicht installiert:
`zepos-apps-office` (LibreOffice mit deutschen Wörterbüchern) und
`zepos-apps-devel` (`base-devel`, `git`).

`zepos-apps` enthält außerdem **Claude Code**, verpackt als
`zepos-claude-code` aus einem festgenagelten, per Prüfsumme abgesicherten
Upstream-Tarball, und im Dock angeheftet. Es ist Anthropics proprietäre
CLI unter ihrer eigenen Lizenz, nicht Teil von ZepOS' GPL, und braucht ein
Anthropic-Konto, um irgendetwas zu tun. Wer es nicht will, entfernt das
Paket.

### Was auf dem Bildschirm steht, und warum wir es selbst geschrieben haben

| | Ersetzt | Warum |
|---|---|---|
| `zepos-menu` | wofi | GTK3, und sechs erzeugte Aufrufstellen hängen von der Auswahl ab |
| `zepos-logout` | wlogout | GTK3, Upstream seit 2024 tot |
| `zepos-lock` | hyprlock | Rendert mit GLES und Cairo, seine Farben konnten daher nie aus `brand.py` kommen |
| AGS-Leiste und -Dock | waybar, nwg-dock-hyprland | waybar ist gtkmm-3; nwg-dock hat keine GTK4-Version |
| `zepos-settings-gui` | nwg-displays | GTK3, und sein „diese Einstellungen behalten?“-Timer stirbt mit dem Programm, das er schützen soll |
| `hyprlaunch`, `hyprclipx` | – | Gebaut aus [azzuriels](https://github.com/azzuriel) Plugins, von ZepOS gepatcht; 116 Zeilen fest verdrahtetes CSS durch erzeugte Stylesheets ersetzt. Siehe [Lizenz](#lizenz) |

GTK4 durchgehend ist eine harte Regel, keine Vorliebe: Eine GTK3-Komponente
ist eine Komponente, deren Farben und Abstände nie aus derselben Quelle
kommen können wie alles andere – und genau das ist die Eigenschaft, die
eine Distribution wie ein einziges System aussehen lässt.

Zwei weitere Oberflächen begegnen einem Nutzer, bevor der Desktop es tut:

- **Die Anmeldemaske** ist `greetd`, das `regreet` innerhalb von `cage`
  ausführt, gestylt aus demselben `brand.py` und demselben Hintergrund wie
  der Installer, mit `tuigreet` auf der Konsole als Rückfallebene, falls
  der grafische Versuch zweimal scheitert. Es gibt kein Autologin – sie
  fragt immer. Sie folgt der Sprache, in der die Maschine installiert
  wurde, mit dem ehrlichen Vorbehalt, dass `regreet` selbst nur zwei der
  acht Strings auf der Maske übersetzt; die übrigen sechs sind Englisch,
  egal was eingestellt ist.
- **Der Boot-Splash** ist ein erzeugtes Plymouth-Theme (`zepos.script` und
  seine Bilder, abgeleitet aus `brand.py` und dem Logo, eingecheckt und
  von einem Test neu abgeleitet). Er ist **nur bei verschlüsselten
  Installationen** aktiviert, wo er die Passphrase-Abfrage der Festplatte
  ist; auf einer unverschlüsselten Platte wäre er Dekoration über einem
  ungemessenen Pfad, darum schaltet der Installer ihn dort nicht ein. Ihn
  zu aktivieren schreibt `mkinitcpio.conf` um, prüft das Ergebnis, und
  macht es bei jedem Zweifel rückgängig.

---

## Gestaltungsentscheidungen, die man kennen sollte

- **Der Desktop muss auch starten, wenn Plugins ausfallen.**
  Hyprland-Plugins sind an eine exakte Hyprland-Version gebunden, sodass
  eine Minor-Version, die sich bewegt, bevor die Plugin-Pakete neu gebaut
  sind, eine Maschine erzeugt, deren Plugins nicht laden können. Alles,
  was ein geladenes Plugin braucht – die `plugin =`-Zeile, der
  Einstellungsblock des Plugins, jede Tastenkombination, deren Dispatcher
  aus einem Plugin kommt – lebt in einer einzigen erzeugten Datei. Ein
  Block wird nur geschrieben, wenn das kompilierte Objekt auf der
  Maschine liegt; sonst tritt an seine Stelle ein Kommentar, der das
  Objekt, das Paket, das es liefert, und den Befehl zum erneuten
  Ausführen nennt. Ganz ohne Plugins ist die Datei nichts als Kommentare –
  und das ist immer noch eine Konfiguration, die sich parsen lässt,
  gemessen mit `Hyprland --verify-config` und in beide Richtungen geprüft
  von `tests/src/test_plugins.py`. Eine Versionsabweichung kostet ein
  Feature, keine Sitzung.
- **WLAN-Zugangsdaten werden in das installierte System mitgenommen.**
  Sich in der Live-Umgebung zu verbinden gibt dem installierten System
  keinen Netzwerkzugang, darum wird das Verbindungsprofil explizit
  geschrieben. Sonst startet ein Laptop ohne Ethernet-Anschluss ohne jede
  Möglichkeit, online zu kommen.
- **Das Repository, mit dem eine Installation durchgeführt wird, ist
  nicht das, das danach bleibt.** Eine Offline-Installation liest ihre
  ZepOS-Pakete von `file:///opt/zepos-repo` auf dem Medium; sobald das
  Medium abgezogen wird, ist der Pfad weg. `installer/core/pacmanconf.py`
  entfernt jeden `[zepos]`-Abschnitt aus der `pacman.conf` des Ziels und
  hängt genau einen an, der auf das Online-Repository zeigt – zu
  ersetzen statt zu bearbeiten ist es, was das Ergebnis unabhängig davon
  macht, wie viele vorher da standen.
- **Updates sind absichtlich eng gefasst.** Ein täglicher Timer, verzögert
  nach dem Start und zufällig gestreut, aktualisiert nur das, was aus
  `[zepos]` kommt. Die Arch-Basis wird gezählt und gemeldet, nie
  angefasst, außer `update.scope=all` ist gesetzt. Ein unbeaufsichtigtes
  `pacman -Syu` auf einem Rolling Release ist eine Maschine, die eines
  Morgens nicht mehr startet. Der Updater erzeugt außerdem nie selbst
  Konfiguration neu und startet nichts neu: Er hinterlässt eine
  Markierung, und die nächste Anmeldung erzeugt neu, bevor der Compositor
  startet.
- **Deutsch und Englisch werden als gleichwertig gepflegt**, über
  gettext, in zwei Domänen – Installer und Desktop-Shell. Die englischen
  Quell-Strings sind die msgids; die deutschen Kataloge sind
  erstklassig, keine Übersetzung zweiter Klasse. Tests stellen sicher,
  dass jeder String in der Quelle einen Katalogeintrag hat und jeder
  Eintrag übersetzt ist, weil ein fehlender Eintrag bedeutet, dass ein
  deutscher Nutzer stillschweigend Englisch liest.
- **Kontrast ist eine Korrektheitsfrage, keine Geschmacksfrage.**
  `src/brand.py` hält ZeptronITs sechs Farben und alle 103 davon
  abgeleiteten Farbschlüssel. WCAG AA verlangt 4,5:1 für Text, und der
  eigene Akzent der Marke erreicht das nicht – `#0096C0` auf `#0D3D47`
  ergibt 3,45:1 –, darum ist der Farbton, der *gelesen* wird, derselbe
  Ton, aufgehellt auf 6,04:1, während das unangetastete `#0096C0` dort
  bleibt, wo es *gesehen* wird. Die Tests berechnen jedes Paar neu, statt
  den daneben geschriebenen Zahlen zu vertrauen. Grün und Rot liegen
  absichtlich **nicht** auf Marke: Eine Distribution, die ihre
  Fehlerzustände in das Firmen-Cyan umfärbt, versteckt Fehler, um
  ordentlich auszusehen.
- **Eine Marke auszuliefern heißt nicht, sie aufzuzwingen.** Jede dieser
  Farben ist über `zepos-settings set colors.<key>` erreichbar, und der
  erste Stil-Vorgabewert des Stil-Editors *ist* die ausgelieferte
  Palette, statt nur eine Kopie davon zu sein.

---

## Entwicklung

### Voraussetzungen

Python 3.14, `archinstall` 4.4, GTK4 mit libadwaita und PyGObject für die
grafischen Oberflächen, `iwd` für WLAN, `gettext` zum Kompilieren der
Kataloge, `docker` für die Paket- und ISO-Bauten.

### Tests

```bash
python -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

110 Testdateien, 2931 Tests, rund sieben Minuten. Die Suite hat eine
**Isolationswache**: Kein Test darf einen echten Prozess starten oder
außerhalb eines temporären Verzeichnisses schreiben. Der Installer
steuert `iwctl`, `archinstall` und NetworkManager – ohne diese Wache
könnte ein unachtsamer Test die WLAN-Verbindung kappen oder die eigenen
Netzwerkprofile überschreiben. Tests, die wirklich eine Ausnahme
brauchen, melden sich sichtbar mit `@pytest.mark.allow_subprocess` oder
`@pytest.mark.allow_system_writes` an.

### Aufbau

```
src/            der Desktop: Vorlagen, die zwei SSOTs, der Generator, die zepos-*-Befehle
installer/      der Installer, in drei Schichten
packaging/      20 PKGBUILD-Rezepte, der Container, die Signier- und Veroeffentlichungsskripte
iso/            zwei archiso-Profile und der Bau, der sie zusammensetzt
lock/ logout/   zepos-lock und zepos-logout (C, GTK4, gtk4-layer-shell)
menu/ settings/ zepos-menu und zepos-settings-gui (Python, GTK4)
plugins/        nur LICENSE - ZepOS' Patches fuer hyprlaunch und hyprclipx
                liegen neben ihren Rezepten in packaging/, nicht hier (siehe Lizenz)
po/             gettext-Kataloge: zepos-installer und zepos-desktop
tests/          110 Testdateien und eine Isolationswache
docs/specs/     das Designdokument und die Roadmap (Deutsch)
```

### Mitarbeiten

Siehe [CONTRIBUTING.md](CONTRIBUTING.md) (Englisch). Kurzfassung:
Änderungen gehören in Vorlagen, nicht in erzeugte Dateien; eine
Behauptung in einer Commit-Nachricht soll benennen, was sie gemessen hat;
und `pytest` wird erwartet, bevor ein Pull Request eingereicht wird.

### Eine Sicherheitslücke melden

Siehe [SECURITY.md](SECURITY.md) (Englisch). Bitte kein öffentliches
Issue für ein Sicherheitsproblem öffnen.

---

## Lizenz

GPL-3.0-or-later für ZepOS' eigenen Code. Siehe [LICENSE](LICENSE).

ZepOS' Desktop hängt von fünf Compositor-Plugins ab, deren Urheberrecht
nicht bei ZepOS selbst liegt. Ihre Lage ist nicht bei allen fünf gleich,
und diese Tabelle existiert, damit man sie auseinanderhalten kann, ohne
fünf PKGBUILDs lesen zu müssen:

| Plugin | Autor | Herkunft | Lizenz | Was ZepOS damit macht |
|---|---|---|---|---|
| `hyprbars` | [hyprwm](https://github.com/hyprwm) (das Hyprland-Projekt) | [hyprwm/hyprland-plugins](https://github.com/hyprwm/hyprland-plugins), auf einen Tag festgenagelt | BSD-3-Clause, echte `LICENSE`-Datei | Unverändert gebaut; nur auf der Konfigurationsebene mit ZepOS' eigenen Farben und Icons versehen |
| `borders-plus-plus` | [hyprwm](https://github.com/hyprwm) (das Hyprland-Projekt) | [hyprwm/hyprland-plugins](https://github.com/hyprwm/hyprland-plugins), auf einen Tag festgenagelt | BSD-3-Clause, echte `LICENSE`-Datei | Unverändert gebaut, ohne eigene Einstellungen geladen |
| `hyprzones` | Jan Ohlmann ([azzuriel](https://github.com/azzuriel)) | [azzuriel/hyprzones](https://github.com/azzuriel/hyprzones), auf einen Commit festgenagelt | **Keine** – GitHub meldet `license: null`; keine `LICENSE`-Datei, kein Copyright-Vermerk irgendwo im Baum | Unverändert gebaut, keine Änderungen von ZepOS |
| `hyprlaunch` | Jan Ohlmann ([azzuriel](https://github.com/azzuriel)) | [azzuriel/hyprlaunch](https://github.com/azzuriel/hyprlaunch), auf einen Commit festgenagelt | **Keine** – wie oben | Zur Bauzeit geholt und gepatcht (siehe unten); der Patch ist ZepOS' eigene Arbeit |
| `hyprclipx` | Jan Ohlmann ([azzuriel](https://github.com/azzuriel)) | [azzuriel/hyprclipx](https://github.com/azzuriel/hyprclipx), auf einen Commit festgenagelt | **Keine** – wie oben | Zur Bauzeit geholt und gepatcht (siehe unten); der Patch ist ZepOS' eigene Arbeit |

`hyprbars` und `borders-plus-plus` sind unauffällig: ein ernsthafter
Upstream, eine echte Lizenz, keine ZepOS-Änderungen am Plugin-Code
selbst. Die anderen drei sind es nicht, und der Grund ist bei allen
dreien derselbe – gemessen am 11.08.2026, an der GitHub-API und von Hand
in jedem Baum: keine `LICENSE`-Datei, keine `Copyright`-Zeile,
`"license": null`. Code ohne Lizenz ist urheberrechtlich „alle Rechte
vorbehalten“, ganz unabhängig davon, was ein Dateikopf behauptet.

**Was das bedeutet, und was ZepOS tatsächlich damit gemacht hat.** Leon
Marzoll (ZeptronIT) – der an genau diesen Upstream-Bäumen selbst als
Mitwirkender beteiligt war und daher an seinen eigenen Beiträgen dazu
das Urheberrecht hält – hat ZepOS am 11.08.2026 die Erlaubnis gegeben,
alle drei zu bauen und zu verändern. Diese Erlaubnis ist wortwörtlich,
mit den genauen Commits, in [`plugins/LICENSE`](plugins/LICENSE)
festgehalten. Es ist eine **Erlaubnis, keine Lizenz**: Sie sagt, was
*ZepOS* darf, und sagt nichts darüber, was *man selbst*, beim
Installieren von ZepOS, mit dem erhaltenen Code darf. Eine
Sicherheitsprüfung vor der Veröffentlichung dieses Repositorys
(`.superpowers/sdd/2026-08-18-ags-schale-und-breitenleiter/
sicherheitsanalyse.md`, Abschnitt 6) hat die schärfere Grenze gezogen,
die diese Erlaubnis nicht überschreitet: Sie deckt nicht, dass ZepOS eine
*Kopie* der lizenzlosen Quelle selbst weiterveröffentlicht. Daraus zu
bauen ist eine Sache; sie weiterzuverbreiten eine andere.

**Seit dem 19.08.2026 trägt dieses Repository darum die Quelle von
`hyprlaunch` oder `hyprclipx` überhaupt nicht mehr.**
`packaging/zepos-hyprlaunch/PKGBUILD` und
`packaging/zepos-hyprclipx/PKGBUILD` holen sie sich zur Bauzeit selbst,
aus dem eigenen Repository des Autors, festgenagelt auf genau den
Commit, den [`plugins/LICENSE`](plugins/LICENSE) nennt – nie ein
wandernder Branch, damit der Bau reproduzierbar bleibt –, genau so, wie
es ein AUR-Paket täte. `hyprzones` war nie in diesem Baum und
funktioniert genauso. ZepOS' eigene Änderungen an `hyprlaunch` und
`hyprclipx` – fest verdrahtetes CSS und Fenstergrößen durch ZepOS'
erzeugte Stylesheets ersetzt, der Zwischenablage-Sammler ergänzt, ein
Pfad korrigiert, der unter `$HOME` griff – sind ZepOS' eigene Diffs,
keine Kopien von Upstream-Code, und liegen als
`packaging/zepos-hyprlaunch/zepos-hyprlaunch.patch` und
`packaging/zepos-hyprclipx/zepos-hyprclipx.patch`, angewendet zur
Bauzeit und lizenziert unter GPL-3.0-or-later. Das gebaute,
veröffentlichte Paket ist von alldem unberührt – das ISO liefert
weiterhin das fertige Plugin aus –, nur die unveränderte
Upstream-*Quelle* wird von diesem Repository nicht mehr weiterverbreitet.

Alle drei Rezepte erklären darum `license=('custom')`, statt eine
Lizenz zu behaupten, die es nicht gibt. Die zugrunde liegende Lücke zu
schließen braucht einen einzigen Commit in Jan Ohlmanns eigenen
Repositories – eine `LICENSE`-Datei, einmal, und die Frage stellt sich
niemandem danach je wieder – und sie sollte geschlossen werden; bis
dahin ist `plugins/LICENSE` die ehrliche Auskunft über den aktuellen
Stand.
