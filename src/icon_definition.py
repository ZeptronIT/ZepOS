#!/usr/bin/env python3
"""
icon_definitions.py - Single Source of Truth (SSOT) für alle Icon-Definitionen
Diese Datei enthält NUR die Mappings von Icon-Namen zu Nerd Font Codes.
"""

# EINE FAMILIE FUER DIE OBERFLAECHE: MATERIAL DESIGN (nf-md)
#
# BESTELLT am 12.08.2026: "bitte andere icons verwenden welche die
# freundlicher aussehen".
#
# GEMESSEN am selben Tag ueber src/icons_db.py: 404 Zeichen aus NEUN
# Familien - 224 nf-md, 138 nf-fa, 32 nf-dev, dazu nf-pl, nf-ple,
# nf-custom, nf-oct, nf-linux, nf-seti. Auf der Leiste selbst lagen 18
# Platzhalter (14 nf-md, 4 nf-fa), und rechnet man die Skripte dazu, die
# ihre Zeichen auf dieselbe Leiste schreiben, waren es 73 Zeichen mit 13
# nf-fa und einem nf-dev darunter.
#
# WARUM AUSGERECHNET nf-md
#     Sie ist mit 224 von 404 ohnehin schon die Mehrheit, also ist jede
#     andere Wahl eine groessere Aenderung. Und sie sieht anders aus:
#     ihre Striche sind ueberall gleich stark und ihre Ecken gerundet,
#     waehrend Font Awesome aus einer aelteren, kantigeren Zeichnung
#     stammt - genau der Unterschied, den der Nutzer "freundlicher"
#     nennt. Nebeneinander auf einer Leiste faellt es auf: das eckige
#     Kalenderblatt aus nf-fa neben den runden Lautstaerkezeichen aus
#     nf-md sah aus wie zwei Programme in einer Zeile.
#
#     Sie kostet nichts. Die Nerd-Font-Schrift liegt ohnehin auf jeder
#     Installation, und am 11.08.2026 stand die Vorgabe, "gratis symbole
#     zu nutzen die jeder zur verfuegung hat" - ein eigener Zeichensatz
#     ist damit ausgeschlossen.
#
# DIE AUSNAHME, UND SIE IST KEINE AUFWEICHUNG: MARKENZEICHEN
#     nf-fa-apple, nf-dev-debian, nf-linux-archlinux, nf-dev-aws,
#     nf-md-spotify - ein Logo IST das Zeichen einer Marke und hat kein
#     Material-Design-Gegenstueck, weil es keines geben kann. Die Regel
#     gilt fuer BEDIENZEICHEN: was eine Handlung, ein Geraet oder einen
#     Zustand meint. Wer den naechsten Umbau macht, soll nicht
#     versuchen, Firefox in Material Design zu zeichnen.
#
# WAS BEIM UMSTELLEN ZU PRUEFEN IST
#     Dass es das Zeichen in der ausgelieferten Schrift WIRKLICH gibt.
#     fetch_icons.py liest die CSS des Nerd-Fonts-Projekts, und die
#     kennt auch Namen, die in einer bestimmten Schrift keinen Glyph
#     haben - heraus kaeme ein leerer Kasten, und den sieht man erst auf
#     der Hardware. Geprueft wird gegen die cmap von
#     /usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf.
#
# WIE WEIT ES AM 12.08.2026 GEKOMMEN IST, MIT ZAHLEN
#     Umgestellt: 47 Zeichen - 14 auf der Leiste und in ihren Skripten,
#     33 auf den uebrigen Oberflaechen.
#
#     Danach noch einmal ueber alle Vorlagen gemessen: 174 Zeichen
#     stehen auf irgendeiner Oberflaeche, davon 172 nf-md und ZWEI
#     nicht - nf-fa-firefox und nf-fa-chrome, also genau die zwei
#     Markenzeichen, die die Ausnahme oben nennt.
#
#     STEHEN GEBLIEBEN sind 94 nf-fa und 30 nf-dev in dieser Tabelle,
#     und die 124 haben eines gemeinsam: KEINE Vorlage nennt sie. Sie
#     sind Vorrat und keine Oberflaeche. Wer einen davon in eine Vorlage
#     schreibt, stellt ihn vorher um - sonst steht wieder ein eckiges
#     Zeichen zwischen runden.
#
# WICHTIG: Keine doppelten Keys! Jeder Key darf nur EINMAL vorkommen!
ICON_DEFINITIONS = {
    # ===== SYSTEM & CORE =====
    "ICON_POWER": "nf-md-power",
    "ICON_POWER_PROFILE": "nf-md-speedometer",
    "ICON_SETTINGS": "nf-md-cog",
    "ICON_GEAR": "nf-md-cog",
    "ICON_EXPAND": "nf-md-arrow_expand",
    "ICON_PALETTE": "nf-md-palette",
    "ICON_THEME": "nf-md-theme_light_dark",
    "ICON_APPLY": "nf-md-content_save_check",
    "ICON_REBUILD": "nf-md-cached",
    "ICON_DASHBOARD": "nf-md-view_dashboard",
    "ICON_HOME": "nf-md-home",
    "ICON_USER": "nf-md-account",
    "ICON_USER_CIRCLE": "nf-md-account_circle",
    "ICON_USERS": "nf-md-account_group",
    "ICON_SHIELD": "nf-md-shield",
    "ICON_KEY": "nf-md-key",
    "ICON_LOCK": "nf-md-lock",
    "ICON_UNLOCK": "nf-md-lock_open",
    "ICON_FINGERPRINT": "nf-md-fingerprint",
    "ICON_CERTIFICATE": "nf-fa-certificate",
    "ICON_VPNKEY": "nf-md-key_variant",
    "ICON_FIREWALL": "nf-md-wall_fire",
    "ICON_ANTIVIRUS": "nf-md-shield_bug",
    "ICON_VPN_CONNECTED": "nf-md-shield_lock",
    "ICON_VPN_DISCONNECTED": "nf-md-shield_off",
    "ICON_VPN_ERROR": "nf-md-shield_alert",

    # ===== DATENSCHUTZ: WER GERADE AUFNIMMT =====
    # Der Punkt und die Kamera. macOS zeigt einen gefuellten Punkt,
    # sobald irgendein Programm Mikrofon oder Kamera OEFFNET - nicht,
    # wenn eine Lautstaerke verstellt ist.
    #
    # ICON_MIC gibt es schon (nf-md-microphone) und es bleibt das
    # Zeichen fuer das Mikrofon. Neu sind nur die zwei, fuer die es
    # bisher keins gab: der Punkt selbst und die Kamera als GERAET.
    # ICON_CAMERA (nf-fa-camera) ist ein Fotoapparat und meint in diesem
    # Baum das Bildschirmfoto - eine Webcam ist etwas anderes, und zwei
    # Bedeutungen an einem Zeichen sind zwei Zeichen.
    "ICON_RECORDING": "nf-md-record_circle",
    "ICON_WEBCAM": "nf-md-webcam",

    # ===== TIME & DATE =====
    "ICON_CLOCK": "nf-md-clock",
    "ICON_CLOCK_O": "nf-md-clock",  # Alias
    "ICON_CALENDAR": "nf-md-calendar",
    "ICON_CALENDAR_CHECK": "nf-fa-calendar_check_o",
    "ICON_HISTORY": "nf-fa-history",
    "ICON_TIMER": "nf-md-timer",
    "ICON_UPTIME": "nf-md-timer",

    # ===== AUDIO & MEDIA =====
    "ICON_VOLUME": "nf-md-volume_high",
    "ICON_VOLUME_HIGH": "nf-md-volume_high",
    "ICON_VOLUME_MID": "nf-md-volume_medium",
    "ICON_VOLUME_LOW": "nf-md-volume_low",
    "ICON_VOLUME_MUTE": "nf-md-volume_off",
    "ICON_MIC": "nf-md-microphone",
    "ICON_MIC_MUTE": "nf-md-microphone_off",
    "ICON_HEADPHONE": "nf-md-headphones",
    "ICON_MUSIC": "nf-md-music",
    "ICON_SPOTIFY": "nf-md-spotify",
    # Die zwei Sprungtasten der Wiedergabe. ICON_PLAY und ICON_PAUSE
    # standen schon unter SYSTEM ACTIONS - dort sind sie seit jeher, und
    # sie bleiben dort, weil ein Umzug jede Vorlage aendern wuerde, die
    # sie benutzt. Vor und Zurueck gab es nicht: ICON_ARROW_LEFT/RIGHT
    # sind blanke Pfeile und heissen "voriger Monat" im Kalender.
    "ICON_MEDIA_NEXT": "nf-md-skip_next",
    "ICON_MEDIA_PREV": "nf-md-skip_previous",

    # ===== NETWORK & CONNECTIVITY =====
    "ICON_WIFI": "nf-md-wifi",
    "ICON_WIFI_OFF": "nf-md-wifi_off",
    "ICON_WIFI_1": "nf-md-wifi_strength_1",
    "ICON_WIFI_2": "nf-md-wifi_strength_2",
    "ICON_WIFI_3": "nf-md-wifi_strength_3",
    "ICON_WIFI_4": "nf-md-wifi_strength_4",
    "ICON_WIFI_LOCK": "nf-md-wifi_lock",
    "ICON_ETHERNET": "nf-md-ethernet",
    "ICON_NETWORK": "nf-md-wifi",
    "ICON_NETWORK_OFF": "nf-md-network_off",
    "ICON_BLUETOOTH": "nf-md-bluetooth",
    "ICON_BLUETOOTH_CONNECTED": "nf-md-bluetooth_connect",
    "ICON_DISCONNECTED": "nf-md-wifi_off",
    "ICON_SIGNAL": "nf-md-signal",
    "ICON_DISCONNECT": "nf-md-close_network",
    "ICON_IP": "nf-md-ip_network",

    # ===== BATTERY & POWER =====
    "ICON_BATTERY": "nf-md-battery",
    "ICON_BATTERY_FULL": "nf-md-battery",
    "ICON_BATTERY_CHARGING": "nf-md-battery_charging",
    "ICON_BATTERY_PLUGGED": "nf-md-power_plug",
    "ICON_BATTERY_EMPTY": "nf-md-battery_outline",
    "ICON_BATTERY_LOW": "nf-md-battery_20",
    "ICON_BATTERY_MID": "nf-md-battery_50",
    "ICON_BATTERY_HIGH": "nf-md-battery_80",
    "ICON_PLUG": "nf-md-power_plug",
    "ICON_BOLT": "nf-md-lightning_bolt",
    "ICON_BATTERY_0": "nf-md-battery_outline",
    "ICON_BATTERY_10": "nf-md-battery_10",
    "ICON_BATTERY_20": "nf-md-battery_20",
    "ICON_BATTERY_30": "nf-md-battery_30",
    "ICON_BATTERY_40": "nf-md-battery_40",
    "ICON_BATTERY_50": "nf-md-battery_50",
    "ICON_BATTERY_60": "nf-md-battery_60",
    "ICON_BATTERY_70": "nf-md-battery_70",
    "ICON_BATTERY_80": "nf-md-battery_80",
    "ICON_BATTERY_90": "nf-md-battery_90",
    "ICON_BATTERY_100": "nf-md-battery",

    # ===== BRIGHTNESS =====
    "ICON_BRIGHTNESS_LOW": "nf-md-brightness_3",
    "ICON_BRIGHTNESS_MID": "nf-md-brightness_5",
    "ICON_BRIGHTNESS_HIGH": "nf-md-brightness_7",

    # ===== TEMPERATURE & WEATHER =====
    "ICON_TEMP": "nf-md-thermometer",
    "ICON_TEMP_HIGH": "nf-md-thermometer_high",
    "ICON_TEMP_LOW": "nf-md-thermometer_low",
    "ICON_TEMP_LIQUID": "nf-md-water",
    "ICON_WEATHER_SUN": "nf-fa-sun_o",
    "ICON_WEATHER_CLOUD": "nf-fa-cloud",
    "ICON_WEATHER_RAIN": "nf-fa-umbrella",
    "ICON_WEATHER_NIGHT": "nf-fa-moon_o",
    "ICON_WEATHER_CLOUDY": "nf-md-weather_cloudy",
    "ICON_WEATHER_FOG": "nf-md-weather_fog",
    "ICON_WEATHER_HAIL": "nf-md-weather_hail",
    "ICON_WEATHER_LIGHTNING": "nf-md-weather_lightning",
    "ICON_WEATHER_PARTLY_CLOUDY": "nf-md-weather_partly_cloudy",
    "ICON_WEATHER_POURING": "nf-md-weather_pouring",
    "ICON_WEATHER_RAINY": "nf-md-weather_rainy",
    "ICON_WEATHER_SNOWY": "nf-md-weather_snowy",
    "ICON_WEATHER_SUNNY": "nf-md-weather_sunny",
    "ICON_WEATHER_WINDY": "nf-md-weather_windy",
    "ICON_WEATHER_HURRICANE": "nf-md-weather_hurricane",
    "ICON_WEATHER_TORNADO": "nf-md-weather_tornado",
    # Weder ein Wetter noch ein Fehler: das Wetter-Modul zeigt dieses
    # Zeichen, wenn der Dienst einen Code liefert, den die Tabelle im
    # Template nicht kennt, und wenn er gar nicht geantwortet hat. Beides
    # sind Zustände, die eine Leiste darstellen können muss - die
    # Alternative ist ein leeres Modul, aus dem niemand etwas ablesen
    # kann.
    "ICON_WEATHER_UNKNOWN": "nf-md-weather_cloudy_alert",

    # ===== FILES & FOLDERS =====
    "ICON_FOLDER": "nf-md-folder",
    "ICON_FOLDER_OPEN": "nf-fa-folder_open",
    "ICON_FILE": "nf-md-file_outline",
    "ICON_FILE_ARCHIVE": "nf-fa-file_archive_o",
    "ICON_DOWNLOAD": "nf-fa-download",
    "ICON_UPLOAD": "nf-fa-upload",
    "ICON_CLOUD": "nf-fa-cloud",
    "ICON_SAVE": "nf-md-content_save",
    "ICON_RESET": "nf-md-undo",
    "ICON_ADD": "nf-md-plus_circle",
    "ICON_DNS": "nf-md-dns",
    "ICON_TRASH": "nf-md-delete",
    "ICON_DELETE": "nf-md-close_circle",
    "ICON_ARCHIVE": "nf-fa-archive",
    "ICON_INBOX": "nf-fa-inbox",

    # ===== SYSTEM ACTIONS =====
    "ICON_LOGOUT": "nf-md-logout",
    "ICON_LOGIN": "nf-md-login",
    "ICON_REBOOT": "nf-md-restart",
    "ICON_SHUTDOWN": "nf-md-power",
    "ICON_SUSPEND": "nf-md-sleep",
    "ICON_HIBERNATE": "nf-md-power_sleep",
    "ICON_PLAY": "nf-md-play",
    "ICON_PAUSE": "nf-md-pause",
    "ICON_RESTART": "nf-md-restart",
    "ICON_GRAPH": "nf-md-chart_line",

    # ===== MONITORING & DETECTION =====
    "ICON_MONITOR": "nf-md-monitor",
    # Mehrere Schirme, und das ist die Zeile im Kontrollzentrum, die zur
    # Seite "Bildschirme" fuehrt. ICON_MONITOR ist EIN Schirm und steht
    # in hardware-monitor.py fuer die Anzeige - die Anordnung MEHRERER
    # ist das, was der Nutzer sucht, wenn er "ich finde den display
    # manager nicht" meldet.
    "ICON_MONITOR_MULTIPLE": "nf-md-monitor_multiple",
    "ICON_DETECT": "nf-md-magnify_scan",
    "ICON_COMPUTER": "nf-md-desktop_classic",
    "ICON_GAMING": "nf-md-gamepad_variant",
    "ICON_OFFICE": "nf-md-office_building",
    "ICON_START": "nf-md-play",
    "ICON_SUCCESS": "nf-fa-check",
    "ICON_BACKUP": "nf-md-backup_restore",
    "ICON_WRITE": "nf-md-pencil",
    "ICON_TIP": "nf-md-lightbulb_outline",
    "ICON_WATCHDOG": "nf-md-shield_check",
    "ICON_HELPERS": "nf-md-tools",
    "ICON_LAUNCH": "nf-md-rocket_launch",

    # ===== WINDOW CONTROLS =====
    "ICON_CLOSE": "nf-md-close",
    "ICON_MINIMIZE": "nf-md-window_minimize",
    "ICON_MAXIMIZE": "nf-md-window_maximize",
    "ICON_WINDOW_FLOATING": "nf-md-window_restore",
    "ICON_WINDOW_TILED": "nf-fa-th_large",
    "ICON_LAYOUT": "nf-md-view_grid",
    "ICON_LAYOUT_MASTER": "nf-md-view_column",
    "ICON_WINDOW_MAXIMIZE": "nf-fa-window_maximize",
    "ICON_WINDOW_MINIMIZE": "nf-fa-window_minimize",
    "ICON_WINDOW_CLOSE": "nf-fa-times",

    # ===== APPLICATIONS =====
    # SECHS PUNKTE - das Rastersymbol des Anwendungsstarters, bestellt am
    # 20.08.2026: "will ich ein icon ganz unten rechts genauso, nur mit 6
    # punkten, was im Prinzip wie SUPER+SPACE macht".
    #
    # DIE FAMILIENREGEL OBEN SAGT nf-md FUER BEDIENZEICHEN, UND HIER STEHT
    # nf-fa. Das ist keine Bequemlichkeit, das ist gemessen.
    #
    #     Am 20.08.2026 wurden ALLE 6896 nf-md-Zeichen der ausgelieferten
    #     Schrift (/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf,
    #     bei 64 px gezeichnet) auf zusammenhaengende Flecken abgesucht.
    #     Genau SECHS gleich grosse Flecken haben davon sechs Zeichen, und
    #     kein einziges davon ist ein Raster:
    #
    #         nf-md-camera_iris        Blende
    #         nf-md-dots_triangle      sechs Punkte, aber als Dreieck
    #         nf-md-table_merge_cells  Tabellenzellen
    #         nf-md-turtle             eine Schildkroete
    #         nf-md-view_module        sechs RECHTECKE, keine Punkte
    #         nf-md-volleyball         ein Ball
    #
    #     Die naechstliegenden nf-md-Kandidaten haben die falsche ANZAHL:
    #     nf-md-dots_grid und nf-md-apps sind NEUN (3x3), nf-md-view_grid
    #     ist VIER, nf-md-dots_square und nf-md-dots_circle sind ACHT.
    #
    #     In nf-fa sind es bei derselben Messung (1818 Zeichen) drei, und
    #     zwei davon sind genau das Gesuchte: nf-fa-grip (3 Spalten x 2
    #     Reihen) und nf-fa-grip_vertical (2 x 3). Gewaehlt ist die
    #     waagerechte Anordnung - dieselbe, die Anwendungsuebersichten
    #     ueblicherweise tragen.
    #
    #     nf-fa-grip ist ausserdem der vertraeglichste Nachbar, den nf-fa
    #     zu bieten hat: seine sechs Flecken sind abgerundete Quadrate,
    #     nicht die scharfen Ecken, wegen derer die Familienregel oben
    #     ueberhaupt entstanden ist ("das eckige Kalenderblatt aus nf-fa
    #     neben den runden Lautstaerkezeichen aus nf-md").
    #
    # Die Bestellung nennt die ANZAHL, nicht die Familie. Ein neun-Punkte-
    # Zeichen waere die Regel eingehalten und die Bestellung verfehlt.
    "ICON_APPS_GRID": "nf-fa-grip",
    "ICON_TERMINAL": "nf-md-console",
    "ICON_TERMINAL_ACTIVE": "nf-md-console_line",
    "ICON_BROWSER": "nf-md-web",
    "ICON_FIREFOX": "nf-fa-firefox",
    "ICON_CHROME": "nf-fa-chrome",
    "ICON_EDGE": "nf-md-microsoft_edge",
    "ICON_SAFARI": "nf-dev-safari",
    "ICON_OPERA": "nf-fa-opera",
    "ICON_BRAVE": "nf-md-web",
    "ICON_TOR": "nf-md-web_box",
    "ICON_CODE": "nf-md-code_tags",
    "ICON_VSCODE": "nf-md-microsoft_visual_studio_code",
    "ICON_VIM": "nf-dev-vim",
    "ICON_DOCKER": "nf-dev-docker",
    "ICON_KUBERNETES": "nf-md-kubernetes",
    "ICON_VM": "nf-fa-desktop",

    # ===== COMMUNICATION =====
    "ICON_MAIL": "nf-fa-envelope",
    "ICON_MAIL_OPEN": "nf-fa-envelope_open",
    "ICON_CHAT": "nf-fa-comment",
    "ICON_MESSAGE": "nf-fa-comments",
    "ICON_PHONE": "nf-fa-phone",
    "ICON_DISCORD": "nf-fa-discord",
    "ICON_SLACK": "nf-fa-slack",
    "ICON_TEAMS": "nf-md-microsoft_teams",
    "ICON_TELEGRAM": "nf-fa-telegram",
    "ICON_WHATSAPP": "nf-fa-whatsapp",
    "ICON_SKYPE": "nf-fa-skype",

    # ===== CLOUD & SYNC =====
    "ICON_ONEDRIVE": "nf-md-microsoft_onedrive",
    "ICON_REFRESH": "nf-md-refresh",
    "ICON_SYNC": "nf-fa-refresh",

    # ===== STATUS INDICATORS =====
    "ICON_SUCCESS": "nf-md-check_circle",
    "ICON_ERROR": "nf-md-alert",
    "ICON_WARNING": "nf-md-alert",
    "ICON_INFO": "nf-md-information",
    "ICON_ALERT": "nf-md-alert",
    "ICON_CHECK": "nf-md-check_circle",
    "ICON_CANCEL": "nf-md-cancel",
    "ICON_QUESTION": "nf-md-help_circle",
    "ICON_EXCLAMATION": "nf-fa-exclamation",
    "ICON_BELL": "nf-md-bell",
    "ICON_BELL_SLASH": "nf-md-bell_off",
    # Die Glocke MIT Punkt: "es liegt etwas im Verlauf, das du nicht
    # gesehen hast". ICON_BELL allein kann das nicht sagen - sie ist der
    # Ruhezustand, und ein Modul, das im Ruhezustand dasselbe zeigt wie
    # im Meldezustand, meldet nichts.
    "ICON_BELL_BADGE": "nf-md-bell_badge",

    # ===== UI ELEMENTS =====
    "ICON_SEARCH": "nf-md-magnify",
    "ICON_EDIT": "nf-md-square_edit_outline",
    "ICON_COPY": "nf-md-content_copy",
    "ICON_PASTE": "nf-fa-paste",
    "ICON_CLIPBOARD": "nf-md-clipboard",
    "ICON_LIST": "nf-md-format_list_bulleted",
    "ICON_CUT": "nf-fa-cut",
    "ICON_PLUS": "nf-md-plus",
    "ICON_MINUS": "nf-fa-minus",
    "ICON_TIMES": "nf-fa-times",
    "ICON_SPINNER": "nf-md-loading",
    "ICON_RUN": "nf-md-play_circle",
    "ICON_PRINT": "nf-md-printer",
    "ICON_SCRIPT": "nf-md-script",
    "ICON_TOOL": "nf-md-wrench",
    "ICON_COUNTER": "nf-md-pound",
    "ICON_PRINTER": "nf-md-printer",
    "ICON_PRINTER_OFF": "nf-md-printer_off",
    "ICON_PRINTER_PRINTING": "nf-md-printer_3d",
    "ICON_PRINTER_ERROR": "nf-md-printer_alert",
    "ICON_ZOOM_IN": "nf-fa-search_plus",
    "ICON_ZOOM_OUT": "nf-fa-search_minus",
    "ICON_EYE": "nf-md-eye",
    "ICON_EYE_SLASH": "nf-md-eye_off",
    "ICON_FILTER": "nf-fa-filter",
    "ICON_SORT": "nf-fa-sort",

    # ===== MEDIA & IMAGES =====
    "ICON_IMAGE": "nf-md-image",
    "ICON_CAMERA": "nf-md-camera",
    "ICON_WALLPAPER": "nf-md-wallpaper",
    "ICON_LANDSCAPE": "nf-md-crop_landscape",
    "ICON_PORTRAIT": "nf-md-crop_portrait",
    "ICON_SHUFFLE": "nf-md-shuffle_variant",
    "ICON_IMPORT": "nf-md-import",

    # ===== SPECIAL & MISC =====
    "ICON_POWERLINE_RIGHT_TRIANGLE": "nf-pl-left_hard_divider",
    "ICON_POWERLINE_LEFT_TRIANGLE": "nf-pl-right_hard_divider",
    "ICON_POWERLINE_RIGHT_ROUND": "nf-ple-right_half_circle_thick",
    "ICON_POWERLINE_LEFT_ROUND": "nf-ple-left_half_circle_thick",
    "ICON_POWERLINE_BRANCH": "nf-pl-branch",
    "ICON_ARCH_LOGO": "nf-linux-archlinux",

    # ===== WORKSPACE NUMBERS =====
    "ICON_WORKSPACE_1": "nf-md-numeric_1_circle",
    "ICON_WORKSPACE_2": "nf-md-numeric_2_circle",
    "ICON_WORKSPACE_3": "nf-md-numeric_3_circle",
    "ICON_WORKSPACE_4": "nf-md-numeric_4_circle",
    "ICON_WORKSPACE_5": "nf-md-numeric_5_circle",
    "ICON_WORKSPACE_6": "nf-md-numeric_6_circle",
    "ICON_WORKSPACE_7": "nf-md-numeric_7_circle",
    "ICON_WORKSPACE_8": "nf-md-numeric_8_circle",
    "ICON_WORKSPACE_9": "nf-md-numeric_9_circle",
    "ICON_WORKSPACE_10": "nf-md-numeric_10_circle",
    "ICON_WORKSPACE_ACTIVE": "nf-fa-circle",
    "ICON_WORKSPACE_DEFAULT": "nf-md-help_circle",
    "ICON_WORKSPACE_URGENT": "nf-md-alert_circle",

    # ===== HELPERS =====
    "ICON_KEYBOARD": "nf-md-keyboard",
    "ICON_CAPS": "nf-fa-arrow_up",
    "ICON_ARROW_LEFT": "nf-md-arrow_left",
    "ICON_ARROW_RIGHT": "nf-md-arrow_right",
    "ICON_BACK": "nf-md-arrow_left",
    "ICON_CONNECT": "nf-md-connection",
    "ICON_LEAF": "nf-md-leaf",
    "ICON_SPEEDOMETER": "nf-md-speedometer",
    "ICON_GAUGE": "nf-md-gauge",
    "ICON_CLEAN": "nf-md-broom",
    "ICON_CLEAR": "nf-fa-times_circle",
    "ICON_FERDIUM": "nf-md-forum",
    "ICON_RGB": "nf-md-led_strip",
    "ICON_CHART": "nf-md-chart_bar",
    "ICON_SYSTEM": "nf-md-cog",

    # ===== HARDWARE CONTROL =====
    "ICON_COOLER": "nf-md-fan",
    "ICON_MOTHERBOARD": "nf-md-chip",
    "ICON_PUMP": "nf-md-pump",
    "ICON_FAN": "nf-fa-fan",
    "ICON_SENSOR": "nf-md-thermometer_lines",
    "ICON_USB": "nf-fa-usb",
    "ICON_SERVER_RACK": "nf-md-server",
    "ICON_CPU": "nf-md-cpu_64_bit",
    "ICON_INTEL": "nf-md-cpu_64_bit",
    "ICON_RAM": "nf-md-memory",
    "ICON_MEMORY": "nf-fa-memory",
    "ICON_DISK": "nf-md-harddisk",
    "ICON_GPU": "nf-seti-graphql",
    "ICON_SWAP": "nf-md-swap_horizontal",
    "ICON_PROCESSES": "nf-md-application",
    "ICON_LOAD": "nf-md-gauge",
    "ICON_LAPTOP": "nf-md-laptop",
    "ICON_THINKPAD": "nf-md-laptop",

    # ===== DEVELOPMENT =====
    "ICON_GIT": "nf-fa-git",
    "ICON_GITHUB": "nf-fa-github",
    "ICON_GITLAB": "nf-fa-gitlab",
    "ICON_BITBUCKET": "nf-fa-bitbucket",
    "ICON_DATABASE": "nf-fa-database",
    "ICON_SERVER": "nf-md-server",
    "ICON_BUG": "nf-fa-bug",
    "ICON_BRANCH": "nf-md-source_branch",
    "ICON_MERGE": "nf-dev-git_merge",
    "ICON_PULL_REQUEST": "nf-dev-git_pull_request",
    "ICON_COMMIT": "nf-dev-git_commit",

    # ===== PROGRAMMING LANGUAGES =====
    "ICON_PYTHON": "nf-dev-python",
    "ICON_JAVASCRIPT": "nf-dev-javascript",
    "ICON_REACT": "nf-dev-react",
    "ICON_VUE": "nf-md-vuejs",
    "ICON_ANGULAR": "nf-dev-angular",
    "ICON_NODEJS": "nf-dev-nodejs",
    "ICON_PHP": "nf-dev-php",
    "ICON_RUBY": "nf-dev-ruby",
    "ICON_GO": "nf-dev-go",
    "ICON_RUST": "nf-dev-rust",
    "ICON_JAVA": "nf-dev-java",
    "ICON_C": "nf-custom-c",
    "ICON_CPP": "nf-custom-cpp",
    "ICON_CSHARP": "nf-dev-csharp",
    "ICON_SWIFT": "nf-dev-swift",
    "ICON_KOTLIN": "nf-dev-kotlin",

    # ===== MEDIA PLATFORMS =====
    "ICON_YOUTUBE": "nf-fa-youtube",
    "ICON_NETFLIX": "nf-md-netflix",
    "ICON_TWITCH": "nf-fa-twitch",
    "ICON_SOUNDCLOUD": "nf-fa-soundcloud",
    "ICON_APPLE_MUSIC": "nf-fa-apple",
    "ICON_AMAZON_MUSIC": "nf-fa-amazon",
    "ICON_TIDAL": "nf-md-music",
    "ICON_DEEZER": "nf-fa-music",
    "ICON_PLEX": "nf-md-plex",
    "ICON_JELLYFIN": "nf-md-jellyfish",
    "ICON_KODI": "nf-md-kodi",

    # ===== SOCIAL MEDIA =====
    "ICON_FACEBOOK": "nf-fa-facebook",
    "ICON_TWITTER": "nf-fa-twitter",
    "ICON_INSTAGRAM": "nf-fa-instagram",
    "ICON_LINKEDIN": "nf-fa-linkedin",
    "ICON_REDDIT": "nf-fa-reddit",
    "ICON_PINTEREST": "nf-fa-pinterest",
    "ICON_TUMBLR": "nf-fa-tumblr",
    "ICON_MASTODON": "nf-fa-mastodon",
    "ICON_TIKTOK": "nf-md-music_note",
    "ICON_SNAPCHAT": "nf-fa-snapchat",

    # ===== PACKAGE MANAGERS =====
    "ICON_PACKAGE": "nf-fa-cube",
    # Ein Paket mit einem Pfeil nach OBEN: es steht eine Aktualisierung
    # an. ICON_PACKAGE ist ein Wuerfel und sagt nur "Paket";
    # ICON_DOWNLOAD sagt "wird geholt" und stimmt fuer den Zustand
    # "liegt bereit" nicht.
    "ICON_UPDATE": "nf-md-package_up",
    "ICON_NPM": "nf-dev-npm",
    "ICON_YARN": "nf-fa-yarn",
    "ICON_COMPOSER": "nf-dev-composer",
    "ICON_HOMEBREW": "nf-dev-homebrew",
    "ICON_APT": "nf-dev-debian",
    "ICON_YUM": "nf-dev-redhat",
    "ICON_PACMAN": "nf-dev-archlinux",
    "ICON_SNAP": "nf-dev-ubuntu",
    "ICON_FLATPAK": "nf-dev-linux",

    # ===== CLOUD SERVICES =====
    "ICON_AWS": "nf-dev-aws",
    "ICON_AZURE": "nf-md-microsoft_azure",
    "ICON_GOOGLE_CLOUD": "nf-md-google_cloud",
    "ICON_DIGITALOCEAN": "nf-dev-digitalocean",
    "ICON_HEROKU": "nf-dev-heroku",
    "ICON_LINODE": "nf-md-cloud",
    "ICON_VULTR": "nf-md-cloud_outline",

    # ===== OFFICE & PRODUCTIVITY =====
    "ICON_WORD": "nf-md-microsoft_word",
    "ICON_EXCEL": "nf-md-microsoft_excel",
    "ICON_POWERPOINT": "nf-md-microsoft_powerpoint",
    "ICON_ONENOTE": "nf-md-microsoft_onenote",
    "ICON_OUTLOOK": "nf-md-microsoft_outlook",
    "ICON_GOOGLE_DOCS": "nf-md-file_document",
    "ICON_GOOGLE_SHEETS": "nf-md-file_excel",
    "ICON_GOOGLE_SLIDES": "nf-md-file_presentation_box",

    # ===== GAMING =====
    "ICON_STEAM": "nf-fa-steam",
    "ICON_EPIC_GAMES": "nf-md-gamepad_variant",
    "ICON_ORIGIN": "nf-md-origin",
    "ICON_UPLAY": "nf-md-ubisoft",
    "ICON_GOG": "nf-md-gog",
    "ICON_BATTLENET": "nf-md-sword_cross",
    "ICON_XBOX": "nf-fa-xbox",
    "ICON_PLAYSTATION": "nf-fa-playstation",
    "ICON_NINTENDO": "nf-md-nintendo_switch",

    # ===== DOCK =====
    "ICON_DOCK": "nf-md-dock_bottom",
    "ICON_DOCK_WINDOW": "nf-md-dock_window",

    # ===== MOUSE & CURSOR =====
    "ICON_CURSOR": "nf-md-cursor_default",
    "ICON_CURSOR_POINTER": "nf-md-cursor_pointer",
    "ICON_MOUSE": "nf-md-mouse",

    # ===== MISC ACTIONS =====
    "ICON_BOOKMARK": "nf-fa-bookmark",
    "ICON_STAR": "nf-md-star",
    "ICON_STAR_FILLED": "nf-fa-star",
    "ICON_HEART": "nf-fa-heart",
    "ICON_FLAG": "nf-fa-flag",
    "ICON_TAG": "nf-fa-tag",
    "ICON_LINK": "nf-fa-link",
    "ICON_UNLINK": "nf-fa-unlink",
    "ICON_EXTERNAL": "nf-fa-external_link",
    "ICON_GLOBE": "nf-fa-globe",
    "ICON_MAP": "nf-fa-map",
    "ICON_LOCATION": "nf-fa-map_marker",
    "ICON_PIN": "nf-fa-thumb_tack",
    "ICON_UNDO": "nf-md-undo",
    "ICON_REDO": "nf-fa-repeat",
    "ICON_CALCULATOR": "nf-fa-calculator",
    "ICON_TASKS": "nf-fa-tasks",
    "ICON_QR_CODE": "nf-fa-qrcode",
    "ICON_BARCODE": "nf-fa-barcode",
    "ICON_RSS": "nf-fa-rss",
    "ICON_SHARE": "nf-fa-share",
    "ICON_TEXT": "nf-fa-file_text_o",

    # ===== USED BY TEMPLATES BUT NEVER DEFINED =====
    # These twelve were referenced by templates while absent from this
    # SSOT. get_icon() has a "?" fallback, so each rendered as a literal
    # question mark and the generator reported success - the checked-in
    # src/helpers/network-watchdog.sh carried exactly that, a rendered
    # "?" where its template says {{ICON_REPAIR}}. Unresolved
    # placeholders are fatal now, so the definitions have to exist.
    "ICON_ACTIVE": "nf-md-check_circle",
    "ICON_CONFIG": "nf-md-file_cog",
    "ICON_EMAIL": "nf-md-email",
    "ICON_HASHTAG": "nf-md-pound",
    "ICON_LOG": "nf-md-text_box_outline",
    "ICON_NEW": "nf-md-plus_circle",
    "ICON_PROFILE": "nf-md-account_box",
    "ICON_RELOAD": "nf-md-reload",
    "ICON_REPAIR": "nf-md-wrench",
    "ICON_WINDOW": "nf-md-window_restore",
    "ICON_WRENCH": "nf-md-wrench",
}


# Validation function
def validate_definitions():
    """Check for duplicate keys in definitions"""
    keys = list(ICON_DEFINITIONS.keys())
    duplicates = []
    for i, key in enumerate(keys):
        if key in keys[i + 1:]:
            duplicates.append(key)

    if duplicates:
        print(f"ERROR: Found {len(duplicates)} duplicate keys:")
        for dup in duplicates:
            print(f"  - {dup}")
        return False

    print(f"✓ All {len(ICON_DEFINITIONS)} keys are unique")
    return True


if __name__ == "__main__":
    validate_definitions()