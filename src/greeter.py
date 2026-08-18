# SPDX-License-Identifier: GPL-3.0-or-later
"""Das Stylesheet der Anmeldemaske, aus derselben Mitte wie der Rest.

WAS HIER BEHOBEN WIRD, UND WIE ES GEMESSEN WURDE
    iso/out/run-release-installed/key-01-01-anmeldung.png, aufgenommen am
    11.08.2026 auf dem installierten System. Der Hintergrund war richtig -
    dasselbe zepos-backdrop.png wie hinter dem Assistenten, dieselbe
    Roboto - und alles, was davor stand, war libadwaitas Vorgabe:

      * die Anmeldekachel und die Uhr darueber in libadwaita-Grau
        (#3a3a3a-artig), nicht im Petrol der Marke
      * "Login" in libadwaita-Blau #3584e4, nicht im Marken-Cyan
      * "Reboot" UND "Power Off" im selben libadwaita-Rot #c01c28 - zwei
        verschieden teure Aktionen in einer Farbe

    Der Grund stand in src/login/regreet.toml ausgeschrieben: das
    Stylesheet des Assistenten steht als Python-Zeichenkette in
    installer/gui/branding.py, gehoert dem Paket zepos-installer und ist
    auf einer Installation gar nicht da (Spec §4.2). Also hatte die
    Anmeldung keins.

    Der Satz dort - "regreet nimmt stattdessen libadwaita dunkel, was
    dieselbe Familie ist, aus der auch der Installer seine Widgets nimmt"
    - stimmte fuer die WIDGETS und nicht fuer ihre FARBEN. Dieselbe
    Widget-Bibliothek in ihren Vorgabefarben ist nicht dieselbe Marke;
    das Bild oben ist der Beweis.

WARUM EINE ERZEUGTE DATEI UND KEINE ZWEITE ZEICHENKETTE
    Eine Kopie des Assistenten-Stylesheets in src/login/ waere eine
    zweite Definition derselben Marke gewesen, und die zweite ist immer
    die, die veraltet - genau das Argument, mit dem brand.py anfaengt und
    das dort schon einmal 99 Werte gerettet hat.

    Also kommt jede Farbe aus src/theme.py und jeder Abstand aus
    sizes.py, und src/login/zepos-greeter-<thema>.css IST das Ergebnis
    von stylesheet(palette) - Byte fuer Byte von tests/src/test_greeter.py
    verglichen. Dieselbe Anordnung wie bei src/system/zepos-update.timer,
    und aus dem Grund, den der PKGBUILD dort nennt: ausgeliefert wird die
    DATEI, denn ein Paket, das seine Konfiguration zur Bauzeit aus Python
    erzeugt, ist eins, dessen Inhalt niemand vor dem Bauen lesen kann.

EINE DATEI JE THEMA, UND WARUM DAS DIE GANZE UMSCHALTUNG IST
    GEMELDET am 12.08.2026: "login bildschirm soll genauso dem theme
    angepasst sein" und "sofort umschaltbar".

    Der Schreibtisch wird erzeugt, wenn sich etwas geaendert hat - die
    Anmeldemaske kann das nicht: sie laeuft als Benutzer "greeter", und
    /etc/greetd gehoert root. Ein Themenwechsel, der sie erreichen
    soll, muesste also entweder mit Rechten neu erzeugen oder gar nicht
    wirken.

    Er tut weder das eine noch das andere: ALLE Themen werden zur
    Bauzeit des Pakets geschrieben und liegen nebeneinander unter
    /etc/greetd/. Umgeschaltet wird, indem src/bin/zepos-greeter beim
    Start /etc/zepos/theme liest und die passende Datei an `--style`
    reicht. Damit ist die neue Anmeldemaske beim NAECHSTEN
    Anmeldebildschirm da, ohne dass irgendetwas erzeugt wurde - die
    einzige Stelle des Systems, an der ein Themenwechsel wirklich
    sofort wirkt.

WAS DIESES STYLESHEET NICHT KANN, UND DAS IST GEMESSEN
    Am 12.08.2026 gegen GTK 4.22.4, mit GtkCssProvider selbst - also
    mit dem Parser, der diese Datei spaeter auch liest:

        halign      No property named "halign"
        valign      No property named "valign"
        display     No property named "display"
        visibility  No property named "visibility"
        position    No property named "position"
        margin: auto            Expected a number
        transform: translateY(%)  Percentages are not allowed here

        opacity, min-width/min-height, font-size, border-radius,
        background-image: url(...)   angenommen

    Daraus folgt, was der Nutzer an dieser Maske NICHT ueber CSS
    bekommen kann:

      "keine Beschriftungen"   Ein Label laesst sich nicht aus dem
                               Layout nehmen. `opacity: 0` malt es weg
                               und laesst die Luecke stehen, und einen
                               Selektor fuer "das Label, in dem 'User:'
                               steht" gibt es ohnehin nicht - GTK-CSS
                               kennt keine Textbedingung.
      "Symbole statt Knoepfe"  Die Beschriftung eines Knopfes ist im
                               Rust-Quelltext von regreet 0.5.0 eine
                               Zeichenkette (`set_label: "Reboot"`).
                               CSS erreicht keinen Text.

    Und was der Nutzer bereits HAT, obwohl das Messbild anders
    aussieht: die Kachel steht mittig. Auf key-01-01-anmeldung.png ist
    sie waagerecht wie senkrecht zentriert; "oben links" war eine
    Annahme und ist falsch.

    Was CSS kann und was hier deshalb getan ist: die Kachel auf der
    Sprosse PANEL, jedes Bedienelement - Feld, Auswahlfeld, Stiftknopf,
    Knopf und jede Zeile des Aufklappmenues - auf CONTROL, leisere
    Beschriftungen als die Werte, die sie beschriften, und leise
    Endknoepfe statt zweier roter Kaesten: flach, ohne Rahmen, in der
    Farbe, die sagt, was sie kosten.

    EINE Rundung und nicht zwei, und das ist eine Korrektur vom
    13.08.2026. Hier standen vorher 999px an den Feldern ("als Pille wie
    auf dem Sperrbildschirm") und 8px an den Knoepfen daneben - in
    derselben Zeile desselben Rasters. Beides war einzeln begruendet und
    zusammen war es eine Maske aus zwei Baukaesten;
    tests/src/test_greeter.py haelt sie seitdem auf der Leiter fest.

WAS BIS ZUM 13.08.2026 GAR NICHT GEWIRKT HAT
    Drei der Regeln hier haben ihr Widget nie erreicht, und keine
    Zusicherung konnte das sehen - sie lesen die erzeugte Datei, und
    eine Regel, die nichts trifft, ist fehlerfreies CSS. Gefunden hat es
    erst ein BILD: tests/render/greeter_shot.py baut regreets Widget-Baum
    nach und zaehlt die Bildpunkte aus.

      * `background-image` fehlte an der Feldregel, also blieben
        Auswahlfeld und Stiftknopf in GTKs Grau #383838 stehen.
      * `passwordentry` ist kein Knoten - eine GtkPasswordEntry heisst
        `entry` und traegt die Klasse `password`.
      * `label` hat jede KNOPFbeschriftung mitgefaerbt, womit "Login"
        auf 1,91:1 stand und die drei Kostenstufen unten unsichtbar
        waren.

    Die Einzelheiten samt Gegenprobe stehen bei _surfaces() unten.

    Das BILD dahinter gehoert weiterhin regreet und nicht diesem Blatt;
    _surfaces() unten fuehrt aus, warum eine CSS-Regel dafuer eine
    Farbe waere, die niemand sieht.

    Der Rest - ein Feld statt eines Formulars, ein Symbol statt eines
    Wortes - kostet einen zweiten Hinterbau fuer lock/zepos-lock.c
    gegen $GREETD_SOCK. Der Kopf von lock/zepos-lock-auth.h fuehrt die
    Naht aus.

WAS SICH AUCH DAMIT NICHT UEBERSETZEN LAESST
    "User:", "Session:", "Cancel", "Login", "Reboot", "Power Off" und
    die zwei Hinweisfaehnchen sind in ReGreet 0.5.0 gewoehnliche
    Rust-Zeichenketten in src/gui/templates.rs - `set_label: "User:"`.
    NACHGEMESSEN am 13.08.2026, diesmal an der GANZEN Quelle des Tags
    0.5.0 und nicht nur am GUI-Teil: 2695 Zeilen Rust, NULL Aufrufe von
    gettext, tr!, fl! oder irgendeiner anderen Uebersetzungsfunktion -
    und in Cargo.toml keine einzige Abhaengigkeit, die so etwas
    mitbraechte. Es gibt keinen Katalog, den man fuellen koennte, und
    CSS erreicht Text nicht.

    Und es gibt auch keine Einstellung dafuer: config.rs des Tags 0.5.0
    fuehrt in `AppearanceSettings` genau EIN Feld, `greeting_msg`. Die
    sechs Beschriftungen stehen daneben als feste Zeichenketten
    (templates.rs Z. 75, 83, 141, 148, 215, 220).

    Konfigurierbar sind damit genau zwei Zeichenketten, und beide sind
    in src/login/regreet.toml gesetzt: `[appearance] greeting_msg` und
    `[widget.clock] locale`.

    DAS IST DIE EINE ANFORDERUNG, DIE MIT REGREET NICHT ZU ERFUELLEN
    IST. Ein deutscher Anmeldebildschirm kostet einen eigenen Greeter
    gegen $GREETD_SOCK - dieselbe Naht, die lock/zepos-lock-auth.h
    beschreibt. Alles andere an dieser Maske ist ueber dieses Blatt
    erreichbar, und seit dem 13.08.2026 auch erreicht.
"""
from __future__ import annotations

import sizes
import theme


def _space(step: int) -> str:
    """Eine Sprosse der Abstandsleiter, in Pixeln.

    Ohne die Einstellungen des Nutzers, und das ist Absicht: diese Datei
    wird zur BAUZEIT des Pakets erzeugt und von einem Benutzer gelesen,
    der `greeter` heisst und kein Zuhause hat. Es gibt zu diesem
    Zeitpunkt niemanden, dessen Faktor gemeint sein koennte.

    Der ausgelieferte Faktor ist derselbe, auf den der Schreibtisch
    zielt, also steht die Maske auf derselben Leiter wie er - nur ohne
    den Regler.
    """
    return sizes.value_of(f"{sizes.SPACE_PREFIX}{step}", {})


def _radius(role: str) -> str:
    """Eine Sprosse der Rundungsleiter, aus demselben Grund ohne Regler.

    Die Leiter selbst gehoert NICHT zum Thema - der Kopf von
    src/theme.py fuehrt aus, warum eine Ecke eine Laenge ist und
    Laengen in sizes.TABLE stehen. Dass die Maske sie ueberhaupt
    benutzt, ist trotzdem neu: sie stand bis zum 12.08.2026 auf
    libadwaitas Vorgabe, waehrend Sperrbildschirm und Leiste daneben
    rund waren.
    """
    return sizes.value_of(f"{sizes.RADIUS_PREFIX}{role}", {})


def _font(role: str) -> str:
    """Eine Sprosse der Schriftleiter, aus demselben Grund ohne Regler.

    WARUM DIE MASKE SIE SEIT DEM 13.08.2026 UEBERHAUPT BRAUCHT
        Weil sie sonst auf einer Zahl steht, die niemand als Groesse
        gemeint hat. src/login/regreet.toml setzt `font_name = "Roboto
        16"`, und die 16 ist eine PUNKTgroesse - GTK rechnet sie bei 96
        dpi in 21,3 px um. Das war die Schrift der ganzen Maske: nicht
        von der Leiter, sondern aus der Umrechnung einer Punktangabe,
        die dort steht, damit die FAMILIE gesetzt ist.

        Die Leiter nennt daneben STYLE_FONT_BODY = 20 px. Der
        Unterschied ist mit 1,3 px klein genug, dass sich am Aufbau
        nichts verschiebt, und gross genug, dass er den Unterschied
        ausmacht, um den es hier geht: 20 px sind eine Entscheidung,
        21,3 px sind ein Rest.
    """
    return sizes.value_of(f"{sizes.FONT_PREFIX}{role}", {})


def stylesheet(palette: theme.Palette | None = None) -> str:
    """Das ganze Stylesheet, wie es nach /etc/greetd/ geht.

    regreet(1) nimmt es ueber "-s, --style <PATH>" - nachgelesen an
    src/main.rs des Tags 0.5.0, wo der Schalter als
    `#[arg(short, long, value_name = "PATH", default_value = CSS_PATH)]`
    steht und als `css_path` in GreeterInit landet. src/gui/component.rs
    laedt ihn mit einem GtkCssProvider auf
    STYLE_PROVIDER_PRIORITY_APPLICATION, also OBERHALB von libadwaitas
    eigenem Blatt - was der Grund ist, dass die Regeln unten ueberhaupt
    gewinnen koennen.

    Es laedt ihn allerdings nur, WENN es die Datei gibt
    (`if input.css_path.exists()`), und einen Parse-Fehler meldet
    GtkCssProvider ueber ein Signal, an dem regreet nicht haengt. Beides
    zusammen heisst: eine kaputte Datei ist eine graue Maske und keine
    Fehlermeldung. Deshalb faehrt tests/src/test_greeter.py sie durch
    einen echten GTK4-Parser und besteht auf null Fehlern - fuer JEDES
    Thema.
    """
    if palette is None:
        palette = theme.palette(theme.DEFAULT)
    return "\n".join([
        _header(palette),
        _colours(palette),
        _typography(palette),
        _surfaces(palette),
        _menu(palette),
        _cost_ladder(palette),
        "",
    ])


def filename(name: str) -> str:
    """Wie die Datei dieses Themas heisst - an beiden Enden dieselbe.

    src/login/ traegt sie unter diesem Namen, /etc/greetd/ bekommt sie
    unter demselben, und src/bin/zepos-greeter setzt ihn aus dem
    Themennamen zusammen. Eine Funktion und keine drei Zeichenketten,
    weil die drei sonst genau die Sorte Paar waeren, das
    test_the_package_installs_the_stylesheet_where_the_greeter_looks
    schon einmal gegeneinander halten musste.
    """
    return f"zepos-greeter-{name}.css"


def _header(palette: theme.Palette) -> str:
    return f"""/* Die Anmeldemaske von ZepOS im Thema "{palette.name}" -
 * installiert nach /etc/greetd/{filename(palette.name)}
 *
 * ERZEUGT AUS src/greeter.py stylesheet(). NICHT VON HAND AENDERN.
 * tests/src/test_greeter.py vergleicht diese Datei Byte fuer Byte mit
 * dem, was das Modul baut, und faellt um, sobald die beiden auseinander
 * sind. Wer hier etwas aendern will, aendert src/greeter.py.
 *
 * Jede Farbe kommt aus src/theme.py, jeder Abstand und jede Ecke aus
 * src/sizes.py. Dieselbe Marke, aus derselben Mitte, wie der
 * Assistent - der sie aus installer/gui/branding.py bezieht, weil er
 * dieses Paket nicht importieren darf (Spec 4.2).
 */
"""


def _colours(palette: theme.Palette) -> str:
    """libadwaitas eigene Farbnamen, wortgleich zum Assistenten.

    Der Kopf von installer/gui/branding.py hat die Begruendung in voller
    Laenge, und sie gilt hier genauso: regreet baut seine Maske aus
    GTK4-Widgets, die sich aus diesen Namen zeichnen. Sie umzudefinieren
    erreicht JEDES davon, auch die, von denen diese Datei nie gehoert
    hat. Ein Stylesheet, das stattdessen einzelne Widgets von Hand
    faerbte, liesse jedes Aufklappmenue und jeden Dialog in libadwaitas
    Vorgabe stehen - was genau der Zustand ist, den das Messbild zeigt.
    """
    return f"""
/* ------------------------------------------------------------------
   Die Marke, in libadwaitas eigenen Namen
   ------------------------------------------------------------------ */
@define-color window_bg_color {palette.PETROL};
@define-color window_fg_color {palette.TEXT};
@define-color view_bg_color {palette.INK};
@define-color view_fg_color {palette.TEXT};
@define-color headerbar_bg_color {palette.INK};
@define-color headerbar_fg_color {palette.TEXT};
@define-color popover_bg_color {palette.INK};
@define-color popover_fg_color {palette.TEXT};
@define-color card_bg_color {palette.SHADE_1};
@define-color card_fg_color {palette.TEXT};
@define-color dialog_bg_color {palette.INK};
@define-color dialog_fg_color {palette.TEXT};

/* Der Anmeldeknopf. Das Marken-Cyan in voller Staerke mit der Tinte
   darauf. Weiss auf derselben Flaeche waere schlechter lesbar - und ist
   das, was libadwaita getan hat. Dieselbe Messung wie im Assistenten,
   und tests/src/test_greeter.py rechnet sie fuer jedes Thema nach. */
@define-color accent_bg_color {palette.CYAN};
@define-color accent_fg_color {palette.INK};
@define-color accent_color {palette.CYAN_TEXT};

@define-color success_color {palette.GREEN};
@define-color warning_color {palette.YELLOW};
@define-color error_color {palette.RED};
"""


def _typography(palette: theme.Palette) -> str:
    """Die Schrift des Themas, und die Groesse, mit der gelesen wird.

    Die FAMILIE steht auch in src/login/regreet.toml als "Roboto 16" -
    das ist GTKs gtk-font-name und setzt die Grundschrift, aus der ein
    rem gerechnet wird. Hier steht sie ein zweites Mal, weil das eine die
    Grundschrift ist und das andere die Regel, die auf jedes Widget
    greift; ohne die Regel behielten die Knopfbeschriftungen die
    Vorgabefamilie, die fontconfig fuer sie aufloest.

    Dass regreet.toml damit die Familie des AUSGELIEFERTEN Themas nennt
    und diese Regel die des eingestellten, ist kein Widerspruch: die
    eine setzt die Groesse eines rem, die andere zeichnet den Text. Ein
    zweites regreet.toml je Thema waere eine zweite Datei mit einer
    Zeile Unterschied.
    """
    return f"""
/* ------------------------------------------------------------------
   Die Schrift
   ------------------------------------------------------------------ */
* {{
    font-family: "{palette.FONT_TEXT}", "Cantarell", sans-serif;
}}
"""


def _surfaces(palette: theme.Palette) -> str:
    """Die Anmeldekachel, die Uhr und der Grund, auf dem sie stehen.

    regreet gibt Kachel und Uhr die Klasse "background" - nachgelesen in
    src/gui/templates.rs des Tags 0.5.0, wo `add_css_class: "background"`
    einmal am Rahmen der Anmeldung und einmal am Rahmen der Uhr steht.
    Ueber diese eine Klasse sind also genau die zwei Flaechen
    erreichbar, die im Messbild grau waren.

    WAS DAS BILD DAHINTER ANGEHT: ES GEHOERT NICHT DIESEM BLATT
        Der naheliegende Griff waere `window { background-image:
        url(...) }` mit dem Bild des Themas, so wie
        src/styles/lock-style.template es fuer den Sperrbildschirm tut.
        Er ist hier falsch, und der Grund ist die Schichtung: regreet
        zeichnet seinen Hintergrund als WIDGET aus seiner eigenen
        Konfiguration (`[background] path` in src/login/regreet.toml),
        und ein Widget liegt ueber dem CSS-Grund des Fensters. Eine
        Regel hier waere also eine Farbe, die niemand je sieht - die
        leiseste Sorte Fehler, die dieses Projekt kennt.

        Das Bild der Anmeldung folgt dem Thema deshalb NICHT. Was es
        kosten wuerde, ist gemessen und nicht geschaetzt: regreet.toml
        traegt genau zwei Zeilen, die ein Thema betreffen -
        `[background] path` und `font_name` -, und regreet kennt keine
        zweite Konfigurationsdatei, die die erste ergaenzt. Es waere
        also eine vollstaendige TOML je Thema, mit 4,5 kB Begruendung
        darin, von der sich zwei Zeilen unterscheiden. Solange die
        Anmeldekachel deckend ist - und sie ist es, siehe
        frame.background unten -, kostet das Bild dahinter keine
        Lesbarkeit, sondern nur Stimmigkeit.

    Der Innenabstand der Kachel kommt von HIER und nicht von regreet:
    das Raster darin setzt seine 15 px ueber set_margin_* im Rust-Code,
    und eine Widget-Eigenschaft laesst sich mit CSS nicht
    ueberschreiben. Was CSS kann, ist am Rahmen aussen herum etwas
    dazugeben.

    ------------------------------------------------------------------
    DIE DREI FEHLER VOM 12.08.2026, UND WIE SIE GEMESSEN WURDEN
    ------------------------------------------------------------------
    GEMELDET am 13.08.2026, zum zweiten Mal: "du hast die login felder
    und style dropdown und button immernoch nicht veraendert das sieht
    nicht gut aus".

    Er hatte recht, und die Zusicherungen dieses Moduls hatten es nicht
    gemerkt: sie lesen die erzeugte DATEI und pruefen, dass jede Farbe
    von der Marke und jeder Abstand von der Leiter kommt. Das stimmte
    die ganze Zeit. Eine Regel, die kein Widget trifft, wird trotzdem
    fehlerfrei geparst und faerbt nichts.

    Gemessen wurde mit tests/render/greeter_shot.py - dem Nachbau von
    regreets Widget-Baum aus src/gui/templates.rs des Tags 0.5.0, mit
    DIESEM Blatt darauf, abgebildet in einem verschachtelten Hyprland.
    Der Nachbau zeigt Bildpunkt fuer Bildpunkt dasselbe wie
    iso/out/run-release-installed/key-07-03-anmeldung.png vom
    installierten System, also misst er das Richtige.

    FEHLER 1 - background-image, und es ist der teuerste
        `entry, combobox button` traf sein Widget die ganze Zeit. Was
        fehlte, war eine Zeile: GTKs eigenes Adwaita malt Knoepfe mit
        einem background-IMAGE, und ein Bild liegt ueber der Farbe.
        Das Auswahlfeld blieb deshalb im Adwaita-Grau #383838 stehen,
        obwohl die Regel griff.

        GEGENPROBE am 13.08.2026, zwei Laeufe, sonst gleich:
            nur `background-image: none` dazu   -> #0D3D47  richtig
            nur den Selektor auf `button.combo` -> #393939  unveraendert
        Also nicht der Selektor. Die fehlende Zeile.

        Dieselbe Zeile stand bei suggested-action und
        destructive-action von Anfang an da - dort war sie bekannt und
        hier vergessen. Das Passwortfeld war zufaellig richtig, weil
        ein `entry` in GTK kein background-image bekommt.

    FEHLER 2 - `passwordentry` ist kein Knoten
        GEMESSEN am 13.08.2026 ueber get_css_name() an einem echten
        GTK 4.22.4: eine GtkPasswordEntry heisst im Baum `entry` und
        traegt die Klasse `password`. Einen Knoten `passwordentry` gibt
        es nicht, der Selektor hat nie etwas getroffen. Er ist weg -
        `entry` deckt das Feld nachweislich mit ab.

    FEHLER 3 - `label` hat jede Knopfbeschriftung uebermalt
        Die zwei Regeln `label {{ color: TEXT }}` und
        `frame.background label {{ color: TEXT_DIM }}` waren fuer die
        Beschriftungen NEBEN den Feldern gedacht. Ein Knopf traegt
        seinen Text aber ebenfalls in einem `label`, und eine Regel auf
        dem Kind schlaegt die geerbte Farbe des Elternteils. Gemessen:

            "Login"      #A9C6CF auf #0096C0 = 1,91:1   unlesbar
            "Reboot"     #DCEEF4  statt Gelb
            "Power Off"  #DCEEF4  statt Rot

        Die ganze Kostenleiter unten war damit unsichtbar - drei
        sorgfaeltig begruendete Stufen, von denen keine je zu sehen war.
        Die Beschriftungen sind jetzt ueber `grid > label` erreicht,
        also nur die direkten Kinder des Rasters. Eine Knopfbeschriftung
        sitzt in `button > label` und ist damit ausser Reichweite.

    WAS DER NUTZER AUSSERDEM VERLANGT HAT: EINE HANDSCHRIFT
        "ich sagte eigenes style", und als Massstab nennt er den
        Assistenten. Der macht seine Felder nicht ueber Selektoren,
        sondern gross: `row {{ min-height: 4rem }}`, `font-size:
        1.35rem` (installer/gui/branding.py). Hier ist beides von der
        Leiter genommen statt in rem geschaetzt - Hoehe aus der
        Abstandsleiter, Schrift aus der Schriftleiter.

        UND EINE RUNDUNG STATT ZWEIER: hier standen 999px an den
        Feldern und 8px an den Knoepfen, nebeneinander in derselben
        Zeile des Rasters. Zwei Formen, die nichts unterscheiden.
        Beide stehen jetzt auf STYLE_RADIUS_CONTROL - der Sprosse, die
        sizes.py woertlich fuer "Knopf, Eingabe, Reiter" fuehrt.
    """
    return f"""
/* ------------------------------------------------------------------
   Die zwei Flaechen, die regreet ".background" nennt
   ------------------------------------------------------------------ */
frame.background {{
    background-color: {palette.INK};
    border: 1px solid {palette.SHADE_1};
    border-radius: {_radius("PANEL")};
    padding: {_space(8)};
}}

/* ------------------------------------------------------------------
   Die Bedienelemente: Feld, Auswahlfeld, Stiftknopf, Knopf
   ------------------------------------------------------------------
   Sie sitzen AUF der Kachel und muessen sich davon abheben - dieselbe
   Staffelung wie bei den Ueberlagerungen des Schreibtischs.

   `background-image: none` ist die Zeile, an der das haengt, und sie
   steht ZUERST: GTKs Adwaita malt jeden Knopf mit einem Verlauf, und
   ohne diese Zeile faerbt die Farbe darunter nichts. Gemessen am
   13.08.2026 - siehe der Kopf dieser Funktion.

   `box-shadow: none` aus demselben Grund: Adwaita setzt eine helle
   Kante an die Oberseite jedes Knopfes, die auf dunklem Petrol wie ein
   Kratzer aussitzt. */
entry, combobox button, button {{
    background-image: none;
    background-color: {palette.PETROL};
    color: {palette.TEXT};
    border: 1px solid {palette.SHADE_1};
    border-radius: {_radius("CONTROL")};
    box-shadow: none;
    padding: {_space(4)} {_space(12)};
    min-height: {_space(24)};
    font-size: {_font("BODY")};
}}

/* Der Fokus. Auf einem Anmeldebildschirm ist das die wichtigste
   Auskunft, die die Maske gibt - sie sagt, wohin das Getippte geht,
   und zwar bevor jemand ein Passwort in das falsche Feld schreibt.
   Adwaita zeichnet dafuer einen blauen Ring; hier ist es der der
   Marke, an Rahmen UND Ring, damit er auch dort auffaellt, wo der
   Rahmen ohnehin dunkel ist. */
entry:focus, entry:focus-within, combobox button:focus,
button:focus, button:focus-visible {{
    border-color: {palette.CYAN};
    outline-color: {palette.CYAN};
}}

/* Die Beschriftungen NEBEN den Feldern, und der Gruss darueber.
   `grid > label` und nicht `label`: eine Knopfbeschriftung ist auch
   ein Label, und die Regel hat sie bis zum 13.08.2026 alle
   uebermalt - der Anmeldeknopf stand dadurch auf 1,91:1.

   Der Gruss ist das erste Kind des Rasters (templates.rs haengt
   message_label vor jede andere Zelle) und das einzige, das laut sein
   darf: er ist die Ueberschrift und stand vorher leiser als die Werte
   darunter. */
frame.background grid > label {{
    color: {palette.TEXT_DIM};
}}

frame.background grid > label:first-child {{
    color: {palette.TEXT};
}}

/* Die Meldungsleiste, in der ein "Login failed" erscheint. */
infobar {{
    background-color: {palette.INK};
    color: {palette.TEXT};
}}
"""


def _menu(palette: theme.Palette) -> str:
    """Das Aufklappmenue - die andere Haelfte des Auswahlfeldes.

    WARUM ES DIESEN ABSCHNITT SEIT DEM 13.08.2026 GIBT
        Der Nutzer hat das Aufklappfeld ausdruecklich genannt ("style
        dropdown"), und bis hierher war nur seine geschlossene Seite
        gefaerbt. GEMESSEN am 13.08.2026 mit tests/render/
        greeter_shot.py im Zustand "aufgeklappt": das offene Menue stand
        auf #202020 - GTKs eigenem Menuegrau - mitten auf einer
        petrolfarbenen Maske. Wer nur das geschlossene Feld abbildet,
        hat die Haelfte des Bedienelements nie gesehen; genau das war
        hier drei Fassungen lang der Fall.

    WARUM @define-color popover_bg_color OBEN NICHT GEREICHT HAT
        Weil regreet NICHT an libadwaita haengt. GEMESSEN an seiner
        Cargo.toml des Tags 0.5.0: `gtk4 = "0.10"` und `relm4 = "0.10"`,
        und kein adw. Die Maske steht also auf GTKs eigenem Adwaita, und
        dessen Menue holt seinen Grund nicht aus diesem Namen. Die Namen
        oben sind trotzdem richtig - der Anmeldeknopf beweist, dass
        accent_bg_color ankommt -, sie decken nur nicht alles ab.

        Deshalb hier die gemessenen Knoten statt eines geratenen Namens.
        Der Baum eines GtkComboBoxText-Menues, abgefragt mit
        get_css_name() an GTK 4.22.4:

            popover.background.menu
              contents
                scrolledwindow > viewport > stack > box
                  modelbutton.flat        (eine Zeile je Eintrag)

    WARUM DIE ZEILEN DIESELBE ECKE HABEN WIE DIE FELDER
        Weil es dasselbe Bedienelement ist. Ein Menue, das sich anders
        rundet als das Feld, aus dem es aufgeht, sieht aus wie ein
        zweites Programm - und der Satz, der diese ganze Sitzung
        ausgeloest hat, war "das sieht nicht gut aus".
    """
    return f"""
/* ------------------------------------------------------------------
   Das Aufklappmenue der Auswahlfelder
   ------------------------------------------------------------------ */
popover > contents {{
    background-color: {palette.INK};
    color: {palette.TEXT};
    border: 1px solid {palette.SHADE_1};
    border-radius: {_radius("CARD")};
    padding: {_space(4)};
}}

/* Eine Zeile des Menues. `background-image: none` aus demselben Grund
   wie bei den Knoepfen - GTKs Adwaita legt auch hier ein Bild an, und
   eine Farbe darunter saehe niemand. */
modelbutton {{
    background-image: none;
    background-color: transparent;
    color: {palette.TEXT};
    border-radius: {_radius("CONTROL")};
    padding: {_space(4)} {_space(12)};
    min-height: {_space(24)};
    font-size: {_font("BODY")};
}}

modelbutton:hover {{
    background-color: {palette.INK_HOVER};
}}

/* Die Zeile, auf der die Auswahl steht. Das Marken-Cyan mit der Tinte
   darauf - dieselbe Paarung wie am Anmeldeknopf, damit "ausgewaehlt"
   auf diesem Bildschirm ueberall dasselbe aussieht. */
modelbutton:checked, modelbutton:selected {{
    background-color: {palette.CYAN};
    color: {palette.INK};
}}
"""


def _cost_ladder(palette: theme.Palette) -> str:
    """Was die Aktion KOSTET, in drei Stufen - wie in zepos-logout.

    Die Begruendung steht in src/styles/logout-style.template und gilt
    hier woertlich: das Wort auf dem Knopf sagt schon, WELCHE Aktion es
    ist; wofuer die Farbe gut ist, ist wieviel sie kostet.

    WAS REGREET SELBST TUT UND WARUM DAS ZU WENIG IST
        src/gui/templates.rs gibt BEIDEN Endknoepfen dieselbe Klasse:
        `EndButton` traegt `add_css_class: "destructive-action"`, und
        "Reboot" wie "Power Off" sind EndButtons. Im Messbild sind beide
        dasselbe Rot. Ein Neustart und ein Ausschalten kosten aber nicht
        dasselbe - der eine kommt von allein wieder, der andere nicht.

    UND WARUM SIE SEIT DEM 12.08.2026 FLACH SIND
        GEMELDET am selben Tag: "neustart und ausschalten klein und
        leise". Rot heisst Gefahr, und Ausschalten ist keine Gefahr.
        Zwei gefuellte Kaesten am unteren Rand sind das Zweitlauteste
        im Bild, gleich hinter der Anmeldekachel - dabei ist das
        Ausschalten das, was am seltensten gemeint ist.

        Also: kein Grund, kein Rahmen, nur die Farbe der Schrift. Erst
        wenn der Zeiger darauf steht, kommt die Flaeche - dann ist es
        eine Absicht und keine Verzierung. Ein SYMBOL statt des Wortes
        waere der naechste Schritt und liegt nicht in CSS: die
        Beschriftung ist eine Rust-Zeichenkette.

    WIE DIE ZWEI AUSEINANDERGEHALTEN WERDEN
        Ueber die Reihenfolge, und die ist gemessen: dieselbe Datei legt
        beide in eine gtk::Box mit `set_homogeneous: true`, "Reboot"
        zuerst, "Power Off" danach. Also ist das letzte Kind das
        Ausschalten.

        Die Regel ist bewusst so gebaut, dass ein Irrtum darueber billig
        bleibt: ALLE destructive-action-Knoepfe bekommen zuerst die
        mittlere Stufe, und nur das letzte Kind wird auf die teuerste
        gehoben. Kehrt eine kuenftige Fassung von regreet die Reihenfolge
        um, steht die Maske schlimmstenfalls zweimal auf Gelb - und nicht
        auf einer Regel, die ins Leere zeigt.

    DIE DRITTE STUFE IST DER ANMELDEKNOPF
        Er traegt "suggested-action" und ist das, wofuer dieser
        Bildschirm da ist. Er kommt ueber accent_bg_color oben schon in
        das Marken-Cyan; hier steht nur noch, dass er es auch beim
        Ueberfahren bleibt und nicht in libadwaitas Blau zurueckfaellt.
    """
    return f"""
/* ------------------------------------------------------------------
   Die Kostenleiter: sicher / Neustart / Ausschalten
   ------------------------------------------------------------------ */

/* SICHER - der Knopf, fuer den dieser Bildschirm da ist. */
button.suggested-action {{
    background-color: {palette.CYAN};
    background-image: none;
    color: {palette.INK};
    border: 1px solid {palette.CYAN};
}}

button.suggested-action:hover {{
    background-color: {palette.CYAN_BRIGHT};
    color: {palette.INK};
}}

/* NEUSTART - die Maschine kommt wieder, alles Ungesicherte nicht.
   Zuerst fuer JEDEN Endknopf, damit die Regel darunter nur noch
   verschaerft und nichts freilegt. */
button.destructive-action {{
    background-color: transparent;
    background-image: none;
    color: {palette.YELLOW};
    border: 1px solid transparent;
}}

button.destructive-action:hover {{
    background-color: {palette.STATE_WARNING_BG};
    border-color: {palette.YELLOW_DIM};
}}

/* AUSSCHALTEN - und die Maschine kommt nicht von allein wieder. */
box > button.destructive-action:last-child {{
    color: {palette.RED};
}}

box > button.destructive-action:last-child:hover {{
    background-color: {palette.STATE_CRITICAL_BG};
    border-color: {palette.RED_DEEP};
}}
"""
