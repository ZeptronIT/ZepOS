# SPDX-License-Identifier: GPL-3.0-or-later
"""zepos-menu - das GTK4-Auswahlfenster von ZepOS.

WARUM ES DIESES PROGRAMM GIBT
    Der Nutzer hat am 11.08.2026 entschieden, dass ZepOS durchgehend GTK4
    benutzt und fehlende Stuecke selbst baut. wofi, das bis dahin sechs
    Helferskripte und den Rueckfall-Starter trug, ist GTK3 - gemessen am
    ausgelieferten Objekt:

        objdump -p /usr/bin/wofi | grep NEEDED | grep gtk
        NEEDED  libgtk-3.so.0

    Im angehefteten ALA-Schnappschuss 2026/08/04 (14860 Pakete in
    extra.db) steht kein GTK4-Ersatz: kein walker, kein tofi, kein
    anyrun, kein rofi-wayland. fuzzel ist da und benutzt gar kein GTK.
    Also baut ZepOS das Fenster selbst.

WIE ES AUFGETEILT IST
    options.py und entries.py kommen ohne `gi` aus. Das ist keine
    Ordnungsliebe, sondern die Bedingung dafuer, dass sie in der
    Testumgebung dieses Projekts ueberhaupt laufen: `gi` ist in .venv
    nicht installiert, und GTK4-Widgets ohne Anzeige zu bauen wirft keine
    Ausnahme, sondern SEGFAULTet den ganzen Prozess (Exit 139, gemessen
    in tests/installer/test_gui_headless.py). Alles, was GTK anfasst,
    liegt deshalb in apps.py und window.py und laeuft nur in einem Kind.
"""
