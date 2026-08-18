<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Der Weg zum eigenen Betriebssystem

Stand 11.08.2026. Alle Zahlen hier sind gemessen, nicht geschaetzt; wo
etwas ungemessen ist, steht das dabei.

Der Nutzer am 11.08.2026: *"wir wollen ein OS erstellen vergleichbar mit
den anderen linux distro aber 100% custom"* und *"sozusagen ein eigenes
apple os"*.

## Was "Apple-OS" als Massstab wirklich bedeutet

Nicht: dass es aussieht wie macOS. Sondern dass **eine Stelle jede
Oberflaeche entwirft, ausliefert und aktualisiert** - und dass der Nutzer
nie merkt, wo ein Projekt aufhoert und das naechste anfaengt. Daraus
folgen drei Dinge, die ZepOS heute unterschiedlich weit erfuellt:

1. **Besitz** - der Code der Oberflaeche gehoert uns, wir muessen keinen
   fremden Upstream nachziehen.
2. **Zusammenhang** - alle Oberflaechen holen Farbe, Schrift und Groesse
   aus derselben Quelle, und das wird geprueft statt behauptet.
3. **Kette** - vom Quelltext ueber das signierte Paket bis zum Update auf
   der Maschine des Nutzers, ohne fremde Hand dazwischen.

Besitz steht bei 12 von 17 sichtbaren Oberflaechen. Zusammenhang ist
angefangen. Die Kette ist gebaut, aber nicht in Betrieb.

## Warum die Reihenfolge unten so ist

Die Versuchung ist, mit dem Aussehen weiterzumachen - das sieht man, und
es macht Freude. Die Reihenfolge hier ist trotzdem eine andere, und zwar
aus einem einzigen Grund:

> **Alles, was vor der Veroeffentlichung falsch ist, erbt jede installierte
> Maschine.**

Der Signierschluessel heisst heute "ZepOS TEST KEY - DO NOT TRUST" und
laeuft am 03.11.2026 ab. Jede Maschine, die vorher installiert wird, muss
ihn spaeter von Hand tauschen - eine Handlung, von der ein Nutzer nicht
wissen kann, dass er sie braucht. Deshalb steht Vertrauen vor Hardware
und Hardware vor Schoenheit.

Wer anders priorisieren will, kann Stufe 3 vorziehen. Stufe 1 vorzuziehen
kostet nichts; sie nachzuholen kostet jede bereits ausgelieferte
Installation.

---

## Stufe 1 - Ausliefern, dem man trauen kann

**Ziel:** ein Fremder installiert ZepOS und bekommt Aktualisierungen,
ohne dass wir ihm etwas erklaeren muessen.

| | Aufgabe | Fertig, wenn |
|---|---|---|
| REL-3 | Release-Schluessel erzeugen, Testschluessel ersetzen | `pacman-key -l` auf einer frischen Installation zeigt einen Schluessel, der nicht "DO NOT TRUST" heisst, und `packaging/verify-install.sh` prueft die Signatur dagegen |
| UP-1 | Auto-Update | Eine installierte Maschine holt sich eine neue `zepos-*`-Fassung ohne Zutun; `--scenario update` belegt es |
| REL-4 | ISO-Anhang vor dem Oeffentlichmachen ersetzen | Nichts im Anhang, was nicht ausgeliefert werden soll |
| | Veroeffentlichen | `packaging/publish.sh` hat gelaufen, die Seite traegt Repository und Schluessel, ein zweiter Rechner installiert davon |

**Warum zuerst:** siehe oben. Das ist der einzige Block, dessen
Verspaetung rueckwirkend schadet.

**Drei Entscheidungen, die dem Nutzer gehoeren** (UP-1):
- *Wann?* Vorschlag: taeglicher Timer, verzoegert nach dem Start.
- *Was?* Vorschlag: `zepos-*` automatisch, Arch-Basis nur melden. Ein
  unbeaufsichtigtes `pacman -Syu` auf einem Rolling Release ist ein
  Rechner, der eines Morgens nicht mehr startet.
- *Still oder mit Hinweis?* Vorschlag: Hinweis ueber die vorhandene
  Benachrichtigung, kein Zwang.

## Stufe 2 - Auf Rechnern starten, die uns nicht gehoeren

**Ziel:** das Medium startet auf fremder Hardware, nicht nur auf der
einen Maschine und in QEMU.

| | Aufgabe | Fertig, wenn |
|---|---|---|
| REL-5 | Secure Boot | Das Medium startet auf einer Firmware mit aktivem Secure Boot. **Gemessen am 11.08.2026** (`--scenario secure-boot`): alle drei Stufen der Startkette tragen 0 Byte Signatur, und OVMF lehnt `\EFI\BOOT\BOOTx64.EFI` mit `Access Denied -- rejected probably by Secure Boot` ab, waehrend dieselbe Firmware ohne Plattformschluessel dasselbe Medium startet. Fertig ist erst ein signierter Loader - siehe die drei Wege in `iso/README.md` |
| — | BIOS/Legacy | Ein installiertes ZepOS startet einmal im BIOS-Modus. **Der Startweg ist gemessen** (11.08.2026, `iso/test-bios-chain.py`): ZepOS' eigene Einteilung als MBR, `grub-install --target=i386-pc`, Start unter SeaBIOS bis zum Anmeldezeichen; core.img belegt 61 577 Byte der Luecke. Der GPT-Einwand ist erledigt (`DeviceHandler.__init__` nimmt `PartitionTable.default()`, und die ist MBR ohne UEFI). Offen bleibt archinstalls eigener Weg: dort partitioniert der Installer, nicht ein Skript |
| — | Offline-Installation | Gemessen: `--offline` ueberspringt das Warten auf reflector, den Erreichbarkeitstest und das Holen der Spiegelliste; `OFFLINE` verschiebt allein das `[zepos]`-Repository aufs Medium. Die Arch-Basis kommt in **beiden** Faellen ueber das Netz. **Was fehlt, ist ausgerechnet** (11.08.2026): 390 Pakete, 1 061 018 061 Byte komprimiert, Medium dann rund 2,23 GB statt 1,23 GB. Die Groesse traegt; die vier Stellen, an denen die Paketquelle umgebogen werden muss, sind die Arbeit. Fertig, wenn eine Installation ohne Netzwerk durchlaeuft |
| — | Hardware-Matrix | Drei verschiedene Maschinen, dokumentiert: was ging, was nicht |

**Warum hier:** ein Betriebssystem, das nur auf dem Rechner seines
Erbauers startet, ist kein Betriebssystem. Und jeder Fehler, den man erst
auf fremder Hardware findet, ist teurer, je mehr Oberflaeche darauf
aufbaut.

**Was ein Fremder heute bekommt**, gemessen und nicht geschaetzt: eine
UEFI-Maschine ohne Secure Boot startet und installiert. Eine mit Secure
Boot zeigt den PXE-Start und keinen Hinweis, dass es an ZepOS lag. Eine
BIOS-Maschine startet das Medium, zeigt das gethemte syslinux-Menue und
den Installer, und der sagt auf seiner ersten Seite, warum er nicht
weitermacht. Ohne Netzwerk bricht jede von ihnen ab. Drei von vier
Faellen sagen also inzwischen etwas; einer sagt nichts, und das ist der
Secure-Boot-Fall.

## Stufe 3 - Jede Oberflaeche unsere

**Ziel:** kein fremdes Programm mehr auf dem Bildschirm, und alles auf
GTK4.

| | Aufgabe | Stand |
|---|---|---|
| GK-1c | Leiste und Dock nach AGS (ersetzt waybar, nwg-dock) | **in Arbeit** |
| — | Monitorkonfiguration (ersetzt nwg-displays, GTK3/Python) | **erledigt** 12.08.2026 |
| ST-2 | Anmeldemaske an die Marke: regreet traegt libadwaita-Grau, englische Beschriftungen, rote Knoepfe | offen |
| — | `zepos-lock` - Sperrbildschirm (ersetzt hyprlock) | **erledigt** 12.08.2026 |
| — | Terminal (ersetzt kitty) | offen, **Entscheidung** |
| UI-1 | Alle zwoelf AGS-Fenster auf EIN Gestaltungssystem: ein Knopf, eine Zeile, eine Breitenleiter, Seitenleiste fuer die Hauptfunktionen. Das Kontrollzentrum ist dabei die Schale. | offen, **in Planung** 18.08.2026 |
| UI-2 | Farben global und an EINER Stelle einstellbar, rund zehn statt der heutigen 69. Der Stil-Editor listet sie heute einzeln auf; gebraucht wird eine kleine Zahl benannter Rollen, aus denen sich der Rest ableitet. | offen, **vertagt** 18.08.2026 |

**UI-2 ist bewusst vertagt** - der Nutzer am 18.08.2026: "das bitte
irgendwie besser machen bzw als task anlegen das machen wir spaeter
erstmal die UI verbessern". Die Reihenfolge ist richtig herum: welche
Farbrollen es geben MUSS, zeigt sich erst, wenn die Fenster aus
gemeinsamen Bauteilen bestehen. Heute traegt jedes Fenster eigene
Knoepfe, und jeder eigene Knopf erfindet seine eigene Farbe - eine
Reduktion vor UI-1 waere geraten statt hergeleitet.

GEMESSEN am 18.08.2026: `brand.COLORS` fuehrt 69 Eintraege, und
`src/templates/ags-style.template` traegt 41 verschiedene Knopf-Klassen
ohne eine einzige gemeinsame.

**Die Entscheidung zum Sperrbildschirm ist gefallen** - der Nutzer am
11.08.2026: "4 sollten wir selber machen also sperrbildschirm gtk4".
Umgesetzt am 12.08.2026 als `lock/zepos-lock.c`.

Die offene Frage dabei war, ob GTK4 das Protokoll ueberhaupt hergibt, das
einen Sperrbildschirm von einem Fenster ganz oben unterscheidet
(`ext-session-lock-v1`). GEMESSEN: ja. gtk4-layer-shell 1.3.0 - dieselbe
Bibliothek, an der zepos-logout schon haengt - liefert
gtk4-session-lock.h mit. Im verschachtelten Hyprland 0.55.4 hat ein
zweiter, unabhaengiger Sperr-Client waehrend der Sperre `::failed`
bekommen und nach einem SIGKILL auf den ersten immer noch; die Sitzung
bleibt also auch beim Absturz zu. Der Kopf von lock/zepos-lock.c fuehrt
alle Messungen.

**Die Monitorkonfiguration ist KEIN eigenes Programm geworden**, anders
als die Zeile hier bis zum 12.08.2026 vorsah ("`zepos-displays`"). Sie
ist eine SEITE in `zepos-settings-gui`, und die Begruendung steht im Kopf
von `settings/zepos_settings_gui/screens.py`:

  * `settings/zepos_settings_gui/model.py` hatte die Monitore
    ausdruecklich ausgelassen, weil sie "schon eine Oberflaeche" hatten -
    nwg-displays. Faellt die weg, faellt der Grund fuer das Auslassen,
    nicht der Grund fuer eine eigene Anwendung.
  * Ein eigenes Programm waere ein zweiter Ort zum Suchen, eine zweite
    .desktop-Datei, ein zweites Paket und ein zweiter GTK4-Stapel -
    gegen alles davon argumentiert dieselbe model.py an drei Stellen.
  * Und fuer das einzige, was an dieser Aufgabe wirklich zaehlt, haette
    es nichts gebracht: der Rueckfall liegt ohnehin in einem eigenen
    Prozess (`src/bin/zepos-displays-guard`), weil er den Absturz DES
    PROGRAMMS ueberleben muss - egal, ob dieses Programm ein
    Einstellungsfenster ist oder ein eigenes.

Was dabei ueber die Vorlage hinausgeht, ist der Rueckfall. nwg-displays
fragt zwar nach ("Keep current settings?", 10 Sekunden), aber sein
Zeitgeber haengt an `GLib.timeout_add_seconds` in seiner eigenen
Hauptschleife und stirbt mit dem Programm, und sein Rueckweg fuer
Hyprland legt nur die Datei zurueck und wartet darauf, dass der
Compositor sie bemerkt (main.py:1017, im Kommentar woertlich). Hier
laeuft der Rueckfall in einem abgetrennten Prozess an einer Pipe: bricht
sie, ist das Programm tot, und zurueckgestellt wird SOFORT - mit
`hyprctl keyword monitor` und nicht durch Hoffen.

*Zum Terminal bleibt es bei: nein - kitty stattdessen vollstaendig an
brand.py binden. Es ist viel Arbeit fuer wenig Sichtbarkeit, weil kitty
gut ist und sich vollstaendig einfaerben laesst.*

## Stufe 4 - Die Anwendungen, die ein Betriebssystem ausmachen

**Ziel:** was man bei Apple klickt, klickt man bei uns auch.

| Aufgabe | Warum |
|---|---|
| **Einstellungen als Anwendung** | Heute: `zepos-settings set sizes.scale 1.2` auf der Kommandozeile plus ein AGS-Widget fuer Farben. Das ist der groesste Einzelunterschied zu einem fertigen Betriebssystem |
| **Software-Verwaltung** | Pakete suchen, installieren, entfernen - ohne pacman zu kennen |
| **Dateimanager** | Wir liefern heute **gar keinen**. Ein Projekt fuer sich |
| **Ueber diesen Rechner** | Fassung, Baustempel, Hardware. Klein, und das Erste, wonach jemand sucht |
| **Erstinbetriebnahme** | Nach der ersten Anmeldung: Sprache bestaetigen, Monitore einrichten, Profil waehlen. Heute sieht der Nutzer 30 s nichts, waehrend `zepos-generate --all` laeuft |

## Stufe 5 - Zusammenhang, der geprueft wird

**Ziel:** dass "einheitlich" eine Zusicherung ist und keine Absicht.

| Aufgabe | Fertig, wenn |
|---|---|
| Die toten Platzhalter aufraeumen | Zuletzt gemessen am 11.08.2026: **335 von 559** Stilnamen werden von keiner Vorlage gelesen (von 479/679, ueber 383/600). Der letzte Schritt hat die 48 der toten Abstandsleiter `STYLE_EWW_SPACE_*` geloescht. Fertig, wenn ein Test jeden Namen entweder benutzt oder verbietet - die naechsten 133 sind `STYLE_EWW_MIN_WIDTH_*` und `_MIN_HEIGHT_*`, eine Groessenleiter mit denselben zwei Fehlern, die die Abstandsleiter hatte: Namen nach Groessenklassen statt nach Zahlen, und fuenf unbenutzbare Kopien pro Bildschirmplatz |
| Ein Designsystem als Dokument | Abstaende, Schriftstufen, Zustandsfarben - einmal beschrieben, von allen Oberflaechen bezogen. **Abstaende und Schriftstufen stehen** (`src/sizes.py`, `AGS_FONT_LADDER` und `SPACE_LADDER`, bewacht von `tests/src/test_spacing.py`); Schreibtisch, Assistent und Anmeldung beziehen dieselbe Leiter, in px beziehungsweise rem. Offen sind die Groessen und die Eckenradien |
| Ein Waechter ueber alle Oberflaechen | Ein Test, der JEDE ausgelieferte Oberflaeche gegen brand.py prueft. Heute gibt es das nur fuer die Bootmenues - und dort wurde bis 11.08.2026 genau **1 von 26** Farbwerten geprueft |
| Datensicherung und Wiederherstellung | Ein Betriebssystem ohne Weg zurueck ist ein Versuchsaufbau |

---

## Wie iterativ das wirklich ist

Jede Stufe ist fuer sich auslieferbar. Nach Stufe 1 hat ZepOS Nutzer, die
Updates bekommen; nach Stufe 2 Nutzer auf eigener Hardware; nach Stufe 3
sieht nichts mehr fremd aus; nach Stufe 4 braucht niemand mehr ein
Terminal; nach Stufe 5 kann man das Aussehen an einer Stelle aendern und
sich darauf verlassen.

Der Fehler waere, Stufe 3 bis 5 vor Stufe 1 zu bauen: dann steht am Ende
ein sehr schoenes System, das niemand aktualisieren kann.
