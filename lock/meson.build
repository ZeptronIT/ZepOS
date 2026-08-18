# Der Bau des Sperrbildschirms.
#
# WARUM gtk4-layer-shell-0 HIER STEHT, OBWOHL DAS PROGRAMM KEIN
# LAYER-SHELL-FENSTER BAUT
#     Weil dieselbe Bibliothek beides liefert. gtk4-layer-shell 1.3.0
#     installiert neben gtk4-layer-shell.h auch gtk4-session-lock.h, und
#     `strings /usr/lib/libgtk4-layer-shell.so.0` nennt
#     ext_session_lock_manager_v1, ext_session_lock_v1 und
#     ext_session_lock_surface_v1 samt der gtk_session_lock_instance_*-
#     Funktionen. Es gibt kein eigenes pkg-config-Modul dafuer.
#
#     Das ist der Grund, aus dem dieses Programm ueberhaupt GTK4 sein
#     kann. Der Kopf von zepos-lock.c fuehrt die Messung, mit der die
#     gegenteilige Vermutung widerlegt wurde.
#
# WARUM ERFORDERLICH UND NICHT OPTIONAL
#     Dieselbe Lehre wie bei logout/meson.build, hier aber mit einer
#     Folge, die schlimmer ist als ein falsch platziertes Fenster: ohne
#     die Bibliothek uebersetzt zepos-lock nicht, denn es gibt dann
#     keinen anderen Weg zu ext-session-lock-v1. Faellt sie weg und waere
#     sie optional, muesste an ihrer Stelle irgendein Rueckfall stehen -
#     und jeder denkbare Rueckfall ist ein Fenster, das wie eine Sperre
#     aussieht und keine ist.
#
# WARUM libpam UEBER cc.find_library UND NICHT UEBER dependency()
#     Linux-PAM legt keine .pc-Datei ab; `pkg-config --exists pam`
#     antwortet auf dieser Maschine zwar mit Erfolg, das kommt aber aus
#     einem Paket, das nicht ueberall dasselbe ist. Der Header wird
#     zusaetzlich gesucht, damit ein Bau ohne die Entwicklungsdateien
#     hier ausfaellt und nicht erst am ersten #include.
project('zepos-lock', 'c',
  version : run_command('cat', join_paths(meson.current_source_dir(), '..', 'VERSION'),
                        check : true).stdout().strip(),
  license : 'GPL-3.0-or-later',
  default_options : ['c_std=c11', 'warning_level=2'])

cc = meson.get_compiler('c')

gtk = dependency('gtk4')
sessionlock = dependency('gtk4-layer-shell-0')
pam = cc.find_library('pam', required : true)

if not cc.has_header('security/pam_appl.h')
  error('security/pam_appl.h fehlt - ohne PAM gaebe es keine Pruefung des Passworts')
endif

# Der Kopf, den nur die Sperre kennt. Ohne ihn baute dieses Programm ein
# gewoehnliches Fenster, und das waere kein Sperrbildschirm.
if not cc.has_header('gtk4-session-lock.h', dependencies : [gtk, sessionlock])
  error('gtk4-session-lock.h fehlt - gtk4-layer-shell ist zu alt fuer ext-session-lock-v1')
endif

# Die Quelldateiliste IST die Auswahl des Hinterbaus.
#
# zepos-lock.c ist die Oberflaeche und kennt nur zepos-lock-auth.h;
# zepos-lock-pam.c ist die eine Antwort auf "gehoert dieses Passwort zu
# diesem Menschen?", die dieses Programm braucht. Ein kuenftiger
# Anmeldebildschirm baute DIESELBE Oberflaeche gegen eine andere Datei -
# eine, die greetd ueber $GREETD_SOCK fragt statt PAM direkt. Der Kopf
# von zepos-lock-auth.h fuehrt die Aufteilung aus.
executable('zepos-lock',
  ['zepos-lock.c', 'zepos-lock-pam.c'],
  dependencies : [gtk, sessionlock, pam],
  c_args : ['-DZEPOS_LOCK_VERSION="' + meson.project_version() + '"'],
  install : true)

# Die eigene PAM-Datei. Ihr Kopf begruendet jede Zeile darin.
#
# install_dir ist /etc/pam.d und nicht get_option('sysconfdir'), weil
# Linux-PAM den Pfad fest kennt: eine Bibliothek liest ihn nicht aus dem
# Prefix des Programms, das sie ruft.
install_data('zepos-lock.pam',
  install_dir : '/etc/pam.d',
  rename : 'zepos-lock',
  install_mode : 'rw-r--r--')
