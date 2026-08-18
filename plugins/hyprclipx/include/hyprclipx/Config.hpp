// SPDX-License-Identifier: BSD-3-Clause
//
// Urspruenglich hyprclipx von azzuriel, Commit
// 1eed6ee90a1c3e48ec76510377f8b05f27a4e650. Urhebervermerk und
// Haftungsausschluss stehen in plugins/LICENSE.
//
// WAS ZEPOS HIER GEAENDERT HAT (11.08.2026)
//     Dieselbe Aenderung wie in plugins/hyprlaunch/include/hyprlaunch/
//     Config.hpp, mit derselben Begruendung: die Fenstermasse und die
//     Abstaende stehen nicht mehr im uebersetzten Objekt, sondern
//     kommen aus der erzeugten Datei ~/.config/hyprclipx/config. Was
//     Text umschliesst, muss dem Regler aus src/sizes.py folgen
//     koennen, und ein Wert im Objekt kann das nicht.
//
//     Die Grundwerte bleiben stehen, weil die Datei fehlen kann und
//     SUPER+SHIFT+V dann trotzdem eine Zwischenablage aufmachen soll.
#pragma once
#include <map>
#include <string>

namespace hyprclipx {

// Wo das Paket den Schreibmarken-Helfer ablegt.
//
// WARUM /usr/lib UND NICHT /usr/bin
//     Weil es kein Programm ist, das ein Mensch aufruft: es druckt ein
//     Koordinatenpaar als JSON und wird von genau einer Stelle
//     gestartet, dem geforkten Kind in Globals.cpp. Was in /usr/bin
//     liegt, steht in jeder Vervollstaendigung jeder Shell und
//     verspricht damit, dass man es benutzen kann.
//
// WARUM ES TROTZDEM UEBERSCHREIBBAR IST
//     Weil derselbe Quellbaum ohne Paket laeuft - wer aus dem
//     Arbeitsbaum baut, hat kein /usr/lib/hyprclipx. Der Schluessel
//     caret_helper in ~/.config/hyprclipx/config nimmt dann den Pfad
//     dorthin, wo die Datei wirklich liegt.
inline constexpr const char* CARET_HELPER_DEFAULT =
    "/usr/lib/hyprclipx/caret-position.py";

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
    //     plugins/hyprlaunch/include/hyprlaunch/Config.hpp.
    //     tests/src/test_modal_rule.py haelt alle vier gegen die
    //     Groessentabelle und faellt um, sobald einer wandert.
    //
    // WARUM SIE ALS constexpr IM OBJEKT STEHEN DARF UND DIE MASSE NICHT
    //     Der Kopf dieser Datei erklaert, warum windowWidth und
    //     windowHeight den Weg durch ~/.config/hyprclipx/config nehmen:
    //     sie umschliessen Text, also muss der Regler aus src/sizes.py
    //     sie bewegen koennen. Ein ANTEIL des Schirms bewegt sich mit
    //     keinem Regler - er bleibt die Haelfte, ob die Schrift nun 13
    //     oder 24 Punkte hat. Er ist keine Einstellung, sondern eine
    //     Regel, und Regeln stehen im Programm.
    static constexpr double MODAL_SHARE = 0.5;

    // Die Fenstermasse (kompakte, liegende Anordnung)
    int windowWidth = 600;
    int windowHeight = 220;

    // Wieviele Zeichen der Vorschautext einer Zeile hoechstens zeigt.
    //
    // Eine ANZAHL und keine Groesse: sie steht hier statt in
    // src/sizes.py, weil ein Zeichen bei jedem Faktor ein Zeichen
    // bleibt. Was sich mit dem Faktor aendert, ist die Breite, die
    // sechzig Zeichen einnehmen - und die ist genau deshalb keine
    // zweite Einstellung.
    int previewChars = 60;

    // Der Versatz zur Schreibmarke (steht in user-settings.json)
    int offsetX = 0;
    int offsetY = 0;

    // Verhalten
    int maxItems = 50;
    std::string hotkey = "SUPER V";

    // Pfade
    //
    // WAS SICH AM 12.08.2026 GEAENDERT HAT
    //     clipmanClient stand hier und zeigte auf clipman-client.py.
    //     GEMESSEN: zwei Zuweisungen, NULL Leser - die C++-Haelfte
    //     spricht den Socket in ClipboardManager::sendCommand() selbst
    //     an. Geloescht statt kommentiert; plugins/hyprclipx/src/
    //     Globals.cpp fuehrt die Messung.
    //
    //     caretHelper und userSettingsFile wurden an ZWEI Stellen
    //     gesetzt, in Globals.cpp und in main_ui.cpp, beide Male auf
    //     einen Pfad unter ~. Jetzt setzt loadConfig() sie, also die
    //     eine Stelle, durch die beide Haelften ohnehin gehen - und der
    //     Helfer liegt dort, wo ein Paket ihn ablegen darf.
    std::string caretHelper = CARET_HELPER_DEFAULT;
    std::string userSettingsFile;  // <configdir>/settings.json
    std::string styleSheet;        // ~/.config/hyprclipx/style.css
    std::string caretPosFile = "/tmp/clipboard-manager-caret-pos";
    std::string prevWindowFile = "/tmp/clipboard-manager-prev-window";
    std::string socketPath = "/tmp/clipman.sock";

    // Die Abstandsleiter aus src/sizes.py, Sprosse -> Pixel. Warum sie
    // nicht aus dem Stylesheet kommen kann, steht im Config.hpp von
    // hyprlaunch: GtkBox nimmt ihren Abstand als Konstruktorargument,
    // und GTK4 hat dafuer keinen Selektor.
    std::map<int, int> spacing;

    int space(int rung) const {
        auto found = spacing.find(rung);
        return found == spacing.end() ? rung : found->second;
    }

    // Der Platz, den dieses Fenster auf einer Schirmkante dieser Laenge
    // ueberhaupt beanspruchen darf.
    //
    // DER NAME IST IN BEIDEN EIGENEN PROGRAMMEN DERSELBE
    //     plugins/hyprlaunch/include/hyprlaunch/Config.hpp fuehrt
    //     dieselbe Funktion unter demselben Namen. Zwei Namen fuer eine
    //     Regel sind der Anfang von zwei Regeln.
    //
    // WARUM ES DEN VERLAUF UEBERHAUPT TRIFFT, GERECHNET am 12.08.2026
    //     Die Grundwerte 600x220 lassen die Grenze nie greifen, aber
    //     sie sind Grundwerte: STYLE_CLIPBOARD_WIDTH und
    //     STYLE_CLIPBOARD_HEIGHT folgen dem Regler, und bei dem
    //     ausgelieferten Faktor 1.85 schreibt die erzeugte Datei
    //     1110x407. Auf einem 1366x768-Notebook sind die Deckel 683 und
    //     384 - beide greifen. Das Fenster wuchs also mit der Schrift
    //     ueber den Schirm hinaus, und zwar genau auf den Geraeten, auf
    //     denen es am wenigsten Platz gibt.
    int modalCap(int screenEdge) const {
        return static_cast<int>(screenEdge * MODAL_SHARE);
    }
};

} // namespace hyprclipx
