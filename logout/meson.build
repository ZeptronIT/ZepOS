# Der Bau der Abmeldemaske.
#
# WARUM gtk4 UND NICHT gtk+-3.0
#     Das ist der ganze Zweck dieses Verzeichnisses. Die Entscheidung vom
#     11.08.2026 lautet, dass die Oberflaeche durchgehend auf GTK4 steht;
#     der Vorgaenger wlogout stand gemessen auf libgtk-3.so.0 und kann
#     nach Lage seines Ursprungs nicht davon herunter. Die Begruendung in
#     voller Laenge steht im Kopf von zepos-logout.c.
#
# WARUM gtk4-layer-shell KEINE OPTION IST, WIE SIE ES BEI wlogout WAR
#     wlogouts meson.build hatte `required : false` dafuer, und
#     packaging/wlogout/PKGBUILD musste deshalb nach dem Bau mit
#     `readelf -d` nachsehen, ob die Bibliothek wirklich verlinkt wurde:
#     ohne sie kompilierte wlogout weiter, nahm `--protocol layer-shell`
#     an und fiel dann still auf xdg zurueck. Eine Abhaengigkeit, die
#     ihr Fehlen nicht als Baufehler zeigt, geht irgendwann verloren,
#     ohne dass jemand es merkt. Hier ist sie erforderlich, also faellt
#     der Bau aus, statt ein Programm zu liefern, dessen Fenster der
#     Compositor wie ein gewoehnliches behandelt. Die Pruefung im
#     PKGBUILD bleibt trotzdem stehen - zwei unabhaengige Antworten auf
#     dieselbe Frage, und die zweite misst das fertige Objekt.
project('zepos-logout', 'c',
  version : run_command('cat', join_paths(meson.current_source_dir(), '..', 'VERSION'),
                        check : true).stdout().strip(),
  license : 'GPL-3.0-or-later',
  default_options : ['c_std=c11', 'warning_level=2'])

gtk = dependency('gtk4')
layershell = dependency('gtk4-layer-shell-0')
json = dependency('json-glib-1.0')

executable('zepos-logout', 'zepos-logout.c',
  dependencies : [gtk, layershell, json],
  c_args : ['-DZEPOS_LOGOUT_VERSION="' + meson.project_version() + '"'],
  install : true)
