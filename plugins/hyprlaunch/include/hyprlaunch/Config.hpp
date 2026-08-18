// SPDX-License-Identifier: BSD-3-Clause
//
// Urspruenglich hyprlaunch von azzuriel, Commit
// 24e5c8b82f96f87ac25000353e36a8b17ced4b00. Urhebervermerk und
// Haftungsausschluss stehen in plugins/LICENSE.
//
// WAS ZEPOS HIER GEAENDERT HAT, UND WARUM (11.08.2026)
//     Upstream trug die drei Hoehen als `static constexpr` im Rumpf
//     dieser Struktur:
//
//         static constexpr int SEARCH_HEIGHT = 52;
//         static constexpr int ITEM_HEIGHT   = 45;
//         static constexpr int CHROME        = 9;
//
//     Das sind Pixel, die einen Text umschliessen - eine Zeilenhoehe
//     und eine Suchzeile -, und sie standen im UEBERSETZTEN Objekt.
//     Der Regler aus src/sizes.py haette sie nicht bewegen koennen,
//     und zwar prinzipiell nicht: `zepos-settings set sizes.scale 2.0`
//     haette die Schrift verdoppelt und die Zeile, die sie traegt,
//     stehen gelassen. Genau das ist der Fehler, den src/sizes.py fuer
//     die Leistenhoehe schon einmal aufgeschrieben hat ("50 px trugen
//     13 px Text, und 24 px Text in einer 50 px hohen Leiste werden
//     oben und unten beschnitten").
//
//     Also sind es Felder, und sie kommen aus der erzeugten Datei
//     ~/.config/hyprlaunch/config, die src/templates/
//     hyprlaunch-config.template schreibt.
//
// WARUM DIE GRUNDWERTE TROTZDEM HIER STEHEN
//     Weil die Datei fehlen kann. Ein Starter, der ohne sie gar nicht
//     aufgeht, ist auf SUPER+SPACE eine tote Taste - dieselbe
//     Abwaegung, die zepos-logout fuer sein style.css trifft: ohne die
//     erzeugte Datei ist die Oberflaeche haesslich und vollstaendig
//     bedienbar. Die Zahlen hier sind die von upstream, also die
//     Full-HD-Pixel, auf die sich auch src/sizes.py bezieht.
#pragma once
#include <map>
#include <string>

namespace hyprlaunch {

struct Config {
    // Wie viel vom Schirm ein Fenster hoechstens nimmt, das sich VOR
    // etwas anderes stellt.
    //
    // DER ABDRUCK EINER ZAHL, DIE IN src/sizes.py STEHT
    //     Dort heisst sie MEASURE_MODAL_SHARE und ist begruendet. Sie
    //     ist mit Absicht KEIN Platzhalter, und sizes.py sagt warum:
    //     "eine Anzahl und keine Laenge ... gelesen wird sie nicht von
    //     einer Vorlage, sondern von den Programmen, die ein solches
    //     Fenster aufziehen". Dies hier ist eines dieser Programme; die
    //     anderen sind menu/zepos_menu/window.py,
    //     src/templates/ags-overlay-utils.template und
    //     plugins/hyprclipx/include/hyprclipx/Config.hpp.
    //     tests/src/test_modal_rule.py haelt alle vier gegen die
    //     Groessentabelle und faellt um, sobald einer wandert.
    //
    // WARUM SIE ALS constexpr IM OBJEKT STEHEN DARF UND SEARCH_HEIGHT NICHT
    //     Der Kopf dieser Datei erklaert, warum die drei Hoehen den
    //     Weg durch ~/.config/hyprlaunch/config nehmen muessen: sie
    //     umschliessen Text, also muss der Regler aus src/sizes.py sie
    //     bewegen koennen. Ein ANTEIL des Schirms bewegt sich mit
    //     keinem Regler - er bleibt die Haelfte, ob die Schrift nun 13
    //     oder 24 Punkte hat. Er ist deshalb keine Einstellung, sondern
    //     eine Regel, und Regeln stehen im Programm.
    static constexpr double MODAL_SHARE = 0.5;

    int windowWidth = 530;
    int visibleItems = 20;

    // Die drei Hoehen, aus denen windowHeight() sich zusammensetzt.
    // Grundwerte wie oben begruendet; die erzeugte Datei ueberschreibt
    // sie.
    int searchHeight = 52;   // Innenabstand 10+10 + Eingabe ~30 + Rahmen 2
    int itemHeight = 45;     // 32 Mindesthoehe + 5+5 Innenabstand + Rahmen
    int chrome = 9;          // Listenrand 4+4 + Rahmen 1+1 - 1

    // Das Anwendungssymbol in einer Zeile. Ein BILD und keine Schrift,
    // also folgt es dem Faktor NICHT - die Grenze, die src/sizes.py
    // zwischen SCALED und FIXED zieht, gilt hier genauso wie fuer die
    // Symbole im Dock.
    int iconSize = 36;

    // Wie lang die Beschreibung einer Anwendung hoechstens wird, IN
    // ZEICHEN. Hier stand 60 als Literal im Renderer - eine
    // Lesbarkeitsgrenze, die niemand begruendet hatte und die der
    // Zwischenablage-Verlauf daneben ein zweites Mal traegt.
    // src/sizes.py nennt die Quelle (Bringhurst, 45 bis 75 Zeichen, 66
    // als Vorgabe) und haelt beide auf derselben Zahl.
    //
    // In Zeichen und nicht in Pixeln, und das ist auch der Grund, aus
    // dem dieser Wert dem Faktor NICHT folgt: waechst die Schrift,
    // waechst die Spalte von selbst mit, und die Zeile bleibt 66
    // Zeichen lang.
    int descriptionChars = 66;

    std::string hotkey = "SUPER D";

    // Die Pfade. Sie stehen erst zur Laufzeit fest, aus $HOME.
    std::string recentFile;   // ~/.cache/hyprlaunch-recent.json
    std::string helpersDir;   // ~/.local/bin/helpers
    std::string styleSheet;   // ~/.config/hyprlaunch/style.css

    // Die Abstandsleiter aus src/sizes.py, Sprosse -> Pixel.
    //
    // WARUM DER ABSTAND NICHT AUS DEM STYLESHEET KOMMEN KANN
    //     GtkBox nimmt seinen Abstand zwischen den Kindern als
    //     Konstruktorargument, nicht als CSS-Eigenschaft: `gtk_box_new
    //     (GTK_ORIENTATION_HORIZONTAL, 12)`. GTK4 kennt fuer diese Zahl
    //     keinen Selektor. Sie muss also durch die Konfigurationsdatei,
    //     und dort steht dieselbe Sprosse, die auch das Stylesheet
    //     bekommt - ein Wert, zwei Leser.
    std::map<int, int> spacing;

    // Die Sprosse in Pixeln, oder ihr Grundwert, wenn die erzeugte
    // Datei fehlt. Der Grundwert IST die Sprossennummer: die Leiter ist
    // in Full-HD-Pixeln definiert, und ohne Faktor ist ein Full-HD-Pixel
    // ein Pixel.
    int space(int rung) const {
        auto found = spacing.find(rung);
        return found == spacing.end() ? rung : found->second;
    }

    int windowHeight() const {
        return searchHeight + (visibleItems * itemHeight) + chrome;
    }

    // Wieviele Zeilen auf eine Flaeche dieser Hoehe passen.
    //
    // WARUM ES DIESE ZWEITE RECHNUNG GIBT
    //     GEMESSEN am 11.08.2026: bei dem ausgelieferten Faktor 1.85
    //     ergibt windowHeight() aus 20 Zeilen 52*1.85 + 20*45*1.85 + 9
    //     = 1762 Pixel. Auf einem 1080er Schirm ist das anderthalbmal
    //     die Bildschirmhoehe. Der Starter waere also mit dem Regler
    //     mitgewachsen und dabei aus dem Bild gelaufen - und das ist
    //     kein kleinerer Fehler als der, nicht mitzuwachsen.
    //
    //     Die Zeilenzahl in der Konfiguration bleibt trotzdem eine
    //     OBERGRENZE und keine Vorgabe: wer 20 einstellt, bekommt auf
    //     einem hohen Schirm 20. min() und nicht Ersetzen.
    int rowsThatFit(int availableHeight) const {
        if (itemHeight <= 0)
            return visibleItems;
        int room = (availableHeight - searchHeight - chrome) / itemHeight;
        if (room < 1)
            room = 1;
        return room < visibleItems ? room : visibleItems;
    }

    // Der Platz, den dieses Fenster auf einer Schirmkante dieser Laenge
    // ueberhaupt beanspruchen darf.
    //
    // DER NAME IST IN BEIDEN EIGENEN PROGRAMMEN DERSELBE
    //     plugins/hyprclipx/include/hyprclipx/Config.hpp fuehrt
    //     dieselbe Funktion unter demselben Namen. Zwei Namen fuer eine
    //     Regel sind der Anfang von zwei Regeln.
    //
    // SEIT DEM 12.08.2026 IST DAS DIE HAELFTE UND NICHT DER GANZE SCHIRM
    //     Bis dahin rechnete LauncherRenderer::fittingHeight() mit der
    //     vollen Bildschirmhoehe. Der Starter passte damit zwar auf den
    //     Schirm - er lief nicht mehr unten heraus -, aber er durfte
    //     ihn ausfuellen, und ein Fenster, das man UEBER seiner Arbeit
    //     aufmacht, ist dann kein Fenster mehr, das sich vorstellt.
    //     src/sizes.py schreibt genau das bei MEASURE_MODAL_SHARE auf,
    //     und es galt bis dahin nur fuer das Auswahlmenue und die
    //     Aufklappfenster der Leiste. Drei Programme mit derselben
    //     Aufgabe und zwei Regeln sind zwei Regeln.
    //
    //     GERECHNET fuer 1080 Zeilen und den ausgelieferten Faktor
    //     1.85 (searchHeight 96, itemHeight 83, chrome 9): aus 1080
    //     wurden 11 Zeilen und 1018 Punkte, aus 540 werden 5 Zeilen und
    //     520 Punkte.
    int modalCap(int screenEdge) const {
        return static_cast<int>(screenEdge * MODAL_SHARE);
    }
};

} // namespace hyprlaunch
