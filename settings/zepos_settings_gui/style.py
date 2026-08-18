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

WAS DANN NOCH UEBRIG BLEIBT
    Die Groesse. libadwaita hat dafuer keine benannte Zusage - es gibt
    keine @define-color fuer eine Schrifthoehe -, und ein
    Einstellungsfenster, das den Massstab einstellt, den es selbst nicht
    traegt, ist die unglaubwuerdigste Oberflaeche, die man dafuer bauen
    kann. Also genau eine Regel, aus derselben Zahl, die auch die Leiste
    bekommt: die Rolle BODY der Schriftleiter.

    Sie wirkt beim naechsten Start dieses Fensters und nicht sofort -
    dieselbe Antwort, die die Anwendung auch fuer den Schreibtisch gibt,
    und aus demselben Grund: die Zahl steht in der Einstellungsdatei,
    und gelesen wird sie beim Aufbau.

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
    Bei den INNEREN Knoten. Ein AlertDialog besteht aus
    AdwBreakpointBin > AdwGizmo > GtkWindowHandle > GtkBox >
    GtkScrolledWindow > GtkViewport > GtkBox.message-area, und darin
    Labels mit den Klassen `title-2`, `title-4` und `body`. Die Namen
    gehoeren libadwaita, nicht uns; sie sind erreichbar, aber jede Regel
    darauf ist eine Wette auf die naechste libadwaita-Fassung. Die
    Knopfanordnung sitzt ganz in der Bibliothek und hat ueberhaupt
    keinen Knoten.

    Deshalb hier nur die zwei Masse, die die Marke traegt: die
    Schrifthoehe und die Ecke. Alles andere bleibt libadwaitas
    Entscheidung, und das ist ein Ergebnis und kein Versaeumnis - eine
    Rueckfrage, die aussieht wie jede andere Rueckfrage auf diesem
    Rechner, ist besser als eine, die aussieht wie unsere und sich beim
    naechsten Aktualisieren verschiebt.

WARUM DIE ABSTAENDE NICHT HIER STEHEN
    Weil sie keine Regel brauchen. Adw.PreferencesPage setzt seine
    eigenen Abstaende zwischen Gruppen und Zeilen; was diese Anwendung
    selbst platziert, sind eine Handvoll Kaesten, und die bekommen ihre
    Raender als Widget-Eigenschaft aus sizes.SPACE_LADDER. Ein
    CSS-Selektor daneben waere ein zweiter Ort fuer dasselbe Mass.
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
    Schrift wird vererbt, also reicht die Wurzel.
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
"""
