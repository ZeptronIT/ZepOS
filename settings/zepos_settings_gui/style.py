# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Stylesheet dieser Anwendung - und warum es so kurz ist.

WARUM HIER KEINE EINZIGE FARBE STEHT
    Weil sie schon woanders steht. Diese Anwendung ist eine
    GTK4/libadwaita-Anwendung auf einem ZepOS, und ZepOS erzeugt
    ~/.config/gtk-4.0/gtk.css aus src/brand.py - 45 benannte
    libadwaita-Farben, die GTK beim Start JEDER GTK4-Anwendung liest
    (Route gtk4-colors-config). Die neun Anwendungen aus
    packaging/zepos-apps haengen daran, und diese haengt genauso daran.

    Ein eigenes Farbblatt hier waere die 46. bis 90. Kopie derselben
    Werte, in einer Datei, die niemand mitpflegt - genau der Fehler, an
    dem die Vorgabefarben dieses Projekts schon einmal gescheitert sind
    (drei Kopien, `warning` an zweien #f9e2af und an der dritten
    #fab387; der Kopf von src/brand.py erzaehlt es).

    Der Unterschied zu installer/gui/branding.py, das seine Farben
    ausschreibt: der Assistent laeuft auf einem Medium, auf dem es weder
    ZepOS noch eine erzeugte gtk.css gibt, und darf zepos-config nach
    Spec §4.2 nicht einmal als Abhaengigkeit nennen. Diese Anwendung
    LEBT auf dem installierten System und importiert src/ ohnehin.

    NACHGETRAGEN am 18.08.2026: das gilt weiterhin fuer jede Zeile
    unten, auch fuer die Knopf-Rollen. `alpha(@destructive_color, ...)`
    nimmt eine BENANNTE Farbe aus genau dieser gtk.css und veraendert
    nur ihren Deckkraftkanal - das ist keine neue Farbe, sondern
    dieselbe unter einem anderen Kanal. Ein eigener Hexwert steht hier
    weiterhin nirgends.

WAS DANN NOCH UEBRIG BLEIBT
    Die Groesse. libadwaita hat dafuer keine benannte Zusage - es gibt
    keine @define-color fuer eine Schrifthoehe -, und ein
    Einstellungsfenster, das den Massstab einstellt, den es selbst nicht
    traegt, ist die unglaubwuerdigste Oberflaeche, die man dafuer bauen
    kann. Also die Rolle BODY der Schriftleiter, dieselbe Zahl, die auch
    die Leiste bekommt.

    Sie wirkt beim naechsten Start dieses Fensters und nicht sofort -
    dieselbe Antwort, die die Anwendung auch fuer den Schreibtisch gibt,
    und aus demselben Grund: die Zahl steht in der Einstellungsdatei,
    und gelesen wird sie beim Aufbau.

    NACHGETRAGEN am 18.08.2026, GEMELDET: "Die Einstellungen ... nur
    teilweise [folgen ZepOS]" - eine Abnahme fand, dass Abstaende,
    Rundungen und vor allem die Knopf-Rollen weiterhin libadwaitas
    eigene Vorgabe trugen. Was seither dazukommt, steht in den beiden
    Abschnitten unten; was NICHT dazukommt, steht in "WAS DIE ABNAHME
    NOCH NANNTE, UND WARUM ES HIER NICHT STEHT" ganz unten.

WARUM `dialog` NEBEN `window` STEHT
    GEMELDET am 12.08.2026: "was ist mit gtk4 modale sind die alle in
    ordnung oder umgestylt auf rund statt eckig ??? ist alles auf ein
    design system zurueck zu fuehren".

    GEMESSEN am selben Tag gegen gtk4-broadwayd: ein Adw.AlertDialog
    traegt den CSS-Namen `dialog` und die Klassen `alert floating`, und
    er haengt NICHT unter dem `window`, das ihn zeigt - er ist ein
    eigener, schwebender Knoten. Eine Regel auf `window` erreicht ihn
    also nicht, und genau deshalb blieben die sechs Rueckfragen dieser
    Anwendung und des Assistenten bei GTKs Vorgabegroesse, waehrend das
    Fenster dahinter auf das 1.85-fache gewachsen war.

    Dass der Knoten ueberhaupt erreichbar ist, ist ebenfalls gemessen
    und nicht angenommen: mit `dialog.alert { min-width: 700px; }`
    springt `measure(HORIZONTAL, -1)` von 0 auf 700.

WO ES AUFHOERT
    Bei den INNEREN Knoten eines Adw.AlertDialog. Er besteht aus
    AdwBreakpointBin > AdwGizmo > GtkWindowHandle > GtkBox >
    GtkScrolledWindow > GtkViewport > GtkBox.message-area, und darin
    Labels mit den Klassen `title-2`, `title-4` und `body`. Die Namen
    gehoeren libadwaita, nicht uns; sie sind erreichbar, aber jede Regel
    darauf ist eine Wette auf die naechste libadwaita-Fassung. Die
    Knopfanordnung sitzt ganz in der Bibliothek und hat ueberhaupt
    keinen Knoten.

    Deshalb dort nur die zwei Masse, die die Marke traegt: die
    Schrifthoehe und die Ecke. Alles andere in einem AlertDialog bleibt
    libadwaitas Entscheidung, und das ist ein Ergebnis und kein
    Versaeumnis - eine Rueckfrage, die aussieht wie jede andere
    Rueckfrage auf diesem Rechner, ist besser als eine, die aussieht
    wie unsere und sich beim naechsten Aktualisieren verschiebt.

    NACHGETRAGEN am 18.08.2026: das gilt fuer PRIVATE Knoten wie
    `.message-area` und `title-2` - Namen, die libadwaita niemandem
    zusagt und jederzeit umbauen darf. Ein Knopf mit der Klasse
    `suggested-action`, `destructive-action` oder `flat` ist etwas
    anderes: das sind libadwaitas eigene, OEFFENTLICHE Rollennamen,
    dieselben, die schon in dieser Anwendung stehen (app.py, screens.py,
    bar.py - `add_css_class("suggested-action")` etc.), und dieselbe
    Zusage, auf der jede GTK4-Anwendung im ganzen Oekosystem seit Jahren
    aufbaut. Eine Regel darauf ist keine Wette auf die naechste Fassung,
    sondern die Konvention selbst.

WARUM DIE ABSTAENDE NICHT HIER STEHEN
    Weil sie keine Regel brauchen. Adw.PreferencesPage setzt seine
    eigenen Abstaende zwischen Gruppen und Zeilen; was diese Anwendung
    selbst platziert, sind eine Handvoll Kaesten, und die bekommen ihre
    Raender als Widget-Eigenschaft aus sizes.SPACE_LADDER - siehe
    model.space(), model.SPACE_RUNG und screens._rung(). Ein
    CSS-Selektor daneben waere ein zweiter Ort fuer dasselbe Mass.

    GEPRUEFT am 18.08.2026, weil der Auftrag genau das forderte: die
    Abstandsleiter IST bereits durchgaengig verdrahtet, nur nicht hier
    - `grep -nE "SPACE_RUNG|sizes.SPACE" *.py` findet sie in model.py,
    screens.py und ueber model.space() in bar.py und app.py, ueberall
    ueber sizes.value_of() und damit mit demselben Regler wie jede
    andere Groesse dieses Fensters. Diese Datei bleibt darum ohne
    Abstandsregel - eine haette dieselbe Zahl ein zweites Mal
    geschrieben, in der Sprache, gegen die dieser Abschnitt seit
    12.08.2026 schon einmal argumentiert.

DIE RUNDUNGEN - CONTROL, CARD, PANEL
    GEMESSEN am 18.08.2026 gegen src/sizes.py, RADIUS_ROLES: CONTROL
    ist die Sprosse eines Bedienelements (Knopf, Eingabe, Reiter), CARD
    die einer Flaeche, die AUF einer Scheibe liegt, PANEL die der
    Scheibe selbst. `dialog.alert` traegt PANEL schon seit dieser Datei
    besteht - dieselbe Sprosse wie screens._radius() fuer die
    Bildschirm-Zeichnung, also keine neue Entscheidung.

    Neu ist CONTROL fuer jeden `button`-Knoten (siehe css() unten) und
    CARD fuer `frame.view`, den Rahmen um die Bildschirm-Zeichnung in
    screens.py (Gtk.Frame().add_css_class("view")) - eine Flaeche, die
    AUF dem Fenster liegt, in ihrer eigenen Klasse also CARD und nicht
    PANEL.

    NICHT ANGEFASST: Adw.PreferencesGroup zeichnet seine eigene
    "Kachel" (die abgerundete Liste aus Adw.ActionRow) ueber private
    Knoten, nicht ueber die oeffentliche Utility-Klasse `.boxed-list` -
    GEPRUEFT am 18.08.2026 mit `grep -rn boxed-list settings/`: kein
    Treffer, im Unterschied zu installer/gui/app.py, das `.boxed-list`
    tatsaechlich selbst an eine Gtk.ListBox haengt. Eine Regel auf
    `.boxed-list` haette hier also NICHTS getroffen, und der private
    Name, den PreferencesGroup wirklich benutzt, ist genau die Wette,
    von der der Abschnitt "WO ES AUFHOERT" oben spricht. Diese Kachel
    bleibt darum bei libadwaitas eigener Rundung - GEMELDET, nicht
    geloest.

    `window` selbst bekommt HIER keine Rundung. src/sizes.py fuehrt
    unter RADIUS_ROLES ausdruecklich vor, dass ein FENSTER
    (`decoration:rounding`) auf CARD steht und nicht auf PANEL - PANEL
    ist "eine Flaeche, die FUER SICH auf dem Schreibtisch steht"
    (Ueberlagerung, Leiste, Starter), waehrend ein normales
    Programmfenster wie dieses die Rundung vom Compositor bekommt
    (Hyprland-`windowrule`, ausserhalb dieser Datei und ausserhalb
    dieses Auftrags). Eine `window { border-radius }`-Regel hier waere
    entweder wirkungslos (Wayland rundet ueber den Compositor, nicht
    ueber GTKs CSS-Box) oder, wenn doch wirksam, die falsche Sprosse.

DIE KNOPF-ROLLEN - DIE ENTSPRECHUNG ZU ags-kit.template
    GELESEN am 18.08.2026: src/templates/ags-kit.template (Zeile 20)
    kennt genau VIER Rollen als Klasse - `ZepRolle = "voll" |
    "umrandet" | "still" | "kritisch"` -, keine fuenfte. Eine
    fruehere Fassung dieses Auftrags nannte zusaetzlich "gesperrt";
    src/templates/ags-style.template (Zeile 78, `.zep-btn:disabled`)
    zeigt, dass das keine eigene Rolle ist, sondern der `:disabled`-
    Zustand, den jede der vier Rollen annehmen kann. Der Baum gilt vor
    dem Auftrag (CLAUDE.md, Rolle 10) - unten also vier Rollenregeln
    plus eine gemeinsame :disabled-Regel, keine fuenfte Klasse.

    GTK kennt drei der vier Namen schon als eigene Konvention -
    `suggested-action` (voll), `destructive-action` (kritisch), `flat`
    (still) -, alle drei stehen in dieser Anwendung bereits an
    Knoepfen (app.py, screens.py, bar.py). Fuer "umrandet" gibt es
    keinen eigenen Namen: ein Knopf ohne eine der drei Klassen traegt
    libadwaitas eigene Randlinie, berechnet relativ zu `currentColor`
    (also relativ zu @window_fg_color, das schon die Marke traegt) -
    das ist bereits die Erscheinung von zep-btn-umrandet, und eine
    weitere Regel darauf ist nicht verifizierbar ohne die Anwendung zu
    starten (verboten fuer diesen Auftrag) und wuerde, falls libadwaita
    den Rand ueber box-shadow statt border zeichnet, wirkungslos oder
    doppelt gezeichnet - beides schlechter als keine Regel. GEMELDET,
    nicht geaendert.

    Fuer "voll" (`suggested-action`) kommt die Farbe schon an:
    @accent-bg-color/@accent-fg-color sind THEME.CYAN/THEME.INK, siehe
    src/style_definition.py. GEMESSEN am 18.08.2026, mit derselben
    Formel wie tests/src/test_brand.py (WCAG 2.1, relative Luminanz):
    #08262C auf #0096C0 sind 4.625:1 - ueber der 4.5:1-Schwelle, aber
    NICHT die 6,79:1, die der Kommentar bei STYLE_GTK4_ACCENT_FG in
    style_definition.py behauptet, und weit unter den 8,1:1, die ein
    frueherer Auftrag fuer "voll" als Groessenordnung nennt. Das ist
    eine bestehende Eigenschaft von src/style_definition.py und
    src/brand.py, keine Zeile davon liegt unter settings/ - GEMELDET,
    nicht repariert. Was hier fehlt und in diesem Auftrag liegt, ist
    nur das Gewicht: zep-btn-voll traegt font-weight 500
    (ags-style.template Zeile 47-53), ein unklassifizierter Adwaita-
    Knopf nicht.

    Fuer "kritisch" (`destructive-action`) fuellt libadwaita DECKEND;
    zep-btn-kritisch ist eine getoente Flaeche (ags-style.template
    Zeile 70-76: rgba($red, 0.14), Rand rgba($red, 0.5), Text $red,
    Reiz beim Zeiger rgba($red, 0.24)). GEMESSEN am 18.08.2026 gegen
    die tatsaechlichen Flaechen dieses Fensters (window/headerbar/
    dialog/popover/sidebar_bg_color = PETROL, der hellste - und damit
    kontrastaermste - der drei, siehe unten) haetten AGS' eigene Werte
    hier nicht gereicht:

        Deckkraft  Text auf zusammengesetzter Flaeche (PETROL, schlechtester Fall)
        0.14 (AGS-Ruhezustand)   4.28:1  UNTER 4.5:1
        0.24 (AGS-Zeiger)        3.67:1  UNTER 4.5:1

    Herunterskaliert auf 0.07 Ruhe / 0.09 Zeiger bleibt dieselbe
    Sprache (eine getoente Flaeche, kein deckendes Rot) und haelt die
    Schwelle mit Abstand:

        0.07 (Ruhe)   4.77:1 auf PETROL, 5.36:1 auf card_bg_color
                      (INK_HOVER), 6.32:1 auf view_bg_color (INK)
        0.09 (Zeiger) 4.62:1 auf PETROL, 5.18:1 auf INK_HOVER,
                      6.12:1 auf INK

    Der Rand ist OPAK und nicht getoent: GEMESSEN, dieselbe Flaeche,
    reicht selbst eine Deckkraft von 0.9 nur zu 4.46:1 und 0.6 nur zu
    2.70:1 - unter der 3:1-Grenze aus WCAG 1.4.11 fuer den Umriss eines
    Bedienelements. Erst deckend (#FF8A8A auf PETROL) stehen die schon
    in src/brand.py dokumentierten 5,21:1, weit ueber 3:1. Ein
    getoenter Rand haette hier ausgesehen wie ein Kompromiss und waere
    einer gewesen, der die eigene Kennzeichnungsgrenze verfehlt.

    Fuer "still" (`flat`) traegt zep-btn-still gedaempften Text in
    Ruhe und vollen Text beim Zeiger (ags-style.template Zeile 63-68).
    @dimmed_color GEMESSEN: 6.57:1 auf PETROL, 8.81:1 auf INK, 7.48:1
    auf card_bg_color - in jedem Fall weit ueber 4.5:1, also ohne
    weitere Abwaegung uebernommen.

    Der `:disabled`-Zustand (oben als "gesperrt" bezeichnet) ist nach
    WCAG 2.1 Verstaendnis zu SC 1.4.3 von der Kontrastpflicht
    ausdruecklich AUSGENOMMEN (inaktive Bedienelemente); die Regel
    unten uebernimmt trotzdem zep-btn:disabled aus ags-style.template
    (Flaeche 0.3, Rand 0.5, Text $subtext) fuer dieselbe Erscheinung
    ueber alle vier Rollen hinweg. GEMESSEN als Handreichung, nicht als
    Pflicht: @dimmed_color liegt in jedem realistischen Fall dieses
    Fensters ohnehin ueber 6.5:1.

WAS DIE ABNAHME NOCH NANNTE, UND WARUM ES HIER NICHT STEHT
    Ein "Loeschen-Knopf, der aussieht wie jeder andere" war der
    konkrete Befund. GEPRUEFT am 18.08.2026: kein Knopf in app.py,
    screens.py oder bar.py traegt heute `destructive-action` - auch
    nicht der "Zuruecksetzen"-Knopf (bar.py, RESET_LABEL) und auch
    nicht "Herunternehmen" (bar.py, `buttons["remove"]`). Fuer beide
    steht das dort mit eigener Begruendung: der Zuruecksetzen-Knopf
    ABSICHTLICH ("Rot heisst auf jedem Schreibtisch 'Vorsicht' ... wer
    ihn braucht, hat sich schon verlaufen"), und "Herunternehmen"
    ABSICHTLICH gleich behandelt wie seine Nachbarn "Weiter nach
    vorn/hinten" ("drei Knoepfe unmittelbar nebeneinander sehen aus wie
    einer mit drei Symbolen"). Beides sind Entscheidungen in Zeilen,
    die dieser Auftrag ausdruecklich nicht anfassen soll ("Kein Umbau
    der Anwendung"; nur style.py aendert sich). Die Regel unten baut
    darum die ENTSPRECHUNG - `button.destructive-action` sieht ab jetzt
    aus wie zep-btn-kritisch, sobald irgendein Knopf diese Klasse
    traegt -, ohne selbst zu entscheiden, welcher Knopf das sein
    sollte. GEMELDET.
"""
from __future__ import annotations

import brand
import sizes


def radius(section: dict) -> str:
    """Die Ecke einer Scheibe, mit Einheit.

    Die Rolle PANEL der Rundungsleiter - dieselbe, auf der die
    Ueberlagerungsfenster des Schreibtischs und die Leiste stehen.
    """
    return sizes.value_of(f"{sizes.RADIUS_PREFIX}PANEL", section)


def radius_control(section: dict) -> str:
    """Die Ecke eines Bedienelements, mit Einheit.

    Die Rolle CONTROL der Rundungsleiter - dieselbe, auf der jeder
    Knopf des Bauteil-Kits steht (ags-kit.template, zepButton;
    ags-style.template Zeile 35-41, .zep-btn). NACHGETRAGEN am
    18.08.2026.
    """
    return sizes.value_of(f"{sizes.RADIUS_PREFIX}CONTROL", section)


def radius_card(section: dict) -> str:
    """Die Ecke einer Kachel, mit Einheit.

    Die Rolle CARD der Rundungsleiter - etwas, das AUF einer Scheibe
    liegt (src/sizes.py, RADIUS_ROLES). NACHGETRAGEN am 18.08.2026 fuer
    frame.view, den Rahmen um die Bildschirm-Zeichnung in screens.py.
    """
    return sizes.value_of(f"{sizes.RADIUS_PREFIX}CARD", section)


def font_size(section: dict) -> str:
    """Die Grundschrift des Schreibtischs, mit Einheit.

    Die Rolle BODY der Schriftleiter, also dieselbe Sprosse, auf der
    jede gelesene Zeile des Schreibtischs steht. Sie hiess bis zum
    12.08.2026 STYLE_FONT_SIZE und sagte damit nur, DASS sie eine
    Schriftgroesse ist.
    """
    return sizes.value_of(f"{sizes.FONT_PREFIX}BODY", section)


def css(section: dict) -> str:
    """Das ganze Blatt.

    `window` und nicht `*`: ein Stern ueberschreibt auch die Groessen,
    die libadwaita seinen eigenen Teilen gibt - die kleinere Zeile unter
    einem Titel etwa -, und dann traegt jede Zeile dieselbe Hoehe. Die
    Schrift wird vererbt, also reicht die Wurzel. Aus demselben Grund
    steht unten `button`/`frame.view` und nicht `*`: beide sind
    oeffentliche, benannte Knoten mit einer klar begrenzten Wirkung
    (Rand und Rundung), keine Eigenschaft, die an libadwaitas eigene
    Kinder weitervererbt wuerde.
    """
    return f"""
window, dialog {{
    font-size: {font_size(section)};
}}

/* Die Rueckfragen. Dieselbe Sprosse wie eine Glasscheibe des
   Schreibtischs, weil ein Modal genau das ist: eine Flaeche ueber
   allem anderen. Ohne diese Regel traegt es libadwaitas Ecke, und die
   passt heute zufaellig - aber sie folgt nicht mit, wenn die Leiter
   sich bewegt. */
dialog.alert {{
    border-radius: {radius(section)};
}}

/* Die Farbwerte selbst, als #rrggbb. Das eine, was in diesem Fenster
   eine Spalte aus Zeichen ist und in einer Proportionalschrift falsch
   liest - dieselbe Begruendung, aus der der Assistent seine
   Plattengroessen und sein Protokoll in Fira Code setzt. */
.zepos-hex {{
    font-family: {brand.FONT_FAMILY_CODE};
}}

/* ---------------------------------------------------------------
   NACHGETRAGEN am 18.08.2026: die Knopf-Rollen des AGS-Bauteil-Kits
   (ags-kit.template, ZepRolle), uebersetzt auf libadwaitas eigene,
   OEFFENTLICHE Klassennamen. Die Rechnung fuer jede Zeile steht im
   Modul-Kommentar oben unter "DIE KNOPF-ROLLEN".
   --------------------------------------------------------------- */

/* EINE Rundung fuer jeden Knopf, gleich welcher Rolle - dieselbe
   Sprache wie "EINE Höhe, EIN Radius, vier Rollen" im Kommentar von
   zepButton (ags-kit.template Zeile 22). */
button {{
    border-radius: {radius_control(section)};
}}

/* voll: die Flaeche kommt schon an (@accent-bg-color/@accent-fg-color,
   siehe gtk4-colors-config.template) - hier fehlt nur das Gewicht, das
   zep-btn-voll traegt. */
button.suggested-action {{
    font-weight: 500;
}}

/* kritisch: zep-btn-kritisch ist eine getoente Flaeche, keine
   deckende - die genauen Deckkraefte und ihre Messung stehen oben im
   Modul-Kommentar. Der Rand ist bewusst OPAK (dieselbe Begruendung
   dort). */
button.destructive-action {{
    background-color: alpha(@destructive_color, 0.07);
    border-color: @destructive_color;
    color: @destructive_color;
}}
button.destructive-action:hover,
button.destructive-action:focus {{
    background-color: alpha(@destructive_color, 0.09);
}}

/* still: gedaempfter Text in Ruhe, voller Text beim Zeiger oder mit
   der Tastatur im Fokus - dieselbe Umkehr wie zep-btn-still. */
button.flat {{
    color: @dimmed_color;
}}
button.flat:hover,
button.flat:focus {{
    color: @window_fg_color;
}}

/* :disabled statt einer fuenften Rolle "gesperrt" - siehe den
   Modul-Kommentar dazu. Eine Regel fuer alle vier, wie in
   ags-style.template (.zep-btn:disabled), damit eine gesperrte
   Schaltflaeche nicht die Farbe ihrer Rolle behaelt. */
button:disabled {{
    background-color: alpha(@window_bg_color, 0.3);
    border-color: alpha(@headerbar_border_color, 0.5);
    color: @dimmed_color;
}}

/* Die Kachel um die Bildschirm-Zeichnung (screens.py, Gtk.Frame mit
   der Klasse "view") - eine Flaeche, die AUF dem Fenster liegt, also
   CARD und nicht PANEL. */
frame.view {{
    border-radius: {radius_card(section)};
}}
"""
