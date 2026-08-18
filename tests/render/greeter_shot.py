#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ein Bild der Anmeldemaske - und eine Messung der Farben darauf.

WARUM ES DIESE DATEI GIBT, UND SIE HAT EINEN KONKRETEN ANLASS
    GEMELDET am 13.08.2026, zum zweiten Mal und sichtlich veraergert:
    "du hast die login felder und style dropdown und button immernoch
    nicht veraendert das sieht nicht gut aus ich sagte eigenens style".

    Davor war das Blatt der Anmeldung dreimal geaendert und KEIN EINZIGES
    MAL angesehen worden. tests/src/test_greeter.py hat dabei die ganze
    Zeit alles bestaetigt, was es zusichert - dass jede Farbe aus
    src/theme.py kommt, dass jeder Abstand eine Sprosse ist, dass GTK die
    Datei fehlerfrei liest. Alles davon stimmte. Und die Maske sah
    trotzdem aus wie GTKs Vorgabe, weil eine Regel, die kein Widget
    trifft, fehlerfrei geparst wird und nichts faerbt.

    GEMESSEN an iso/out/run-release-installed/key-07-03-anmeldung.png,
    aufgenommen am 13.08.2026 auf dem installierten System, mit dem
    Blatt vom 12.08. in Kraft:

        Anmeldekachel     #08262C   = theme INK          getroffen
        Anmeldeknopf      #0096C0   = theme CYAN         getroffen
        Benutzerfeld      #383838   = Adwaita-Grau       VERFEHLT
        Sitzungsfeld      #383838   = Adwaita-Grau       VERFEHLT
        Stiftknopf        #383838   = Adwaita-Grau       VERFEHLT
        "Login"-Schrift   #A9C6CF   = theme TEXT_DIM     FALSCH
        "Reboot"-Schrift  #DCEEF4   = theme TEXT         FALSCH (soll GELB)

    Eine Zusicherung, die eine Datei liest, kann das nicht sehen. Diese
    Datei sieht es, weil sie die Maske BAUT und danach ihre Pixel zaehlt.

WAS HIER GEBAUT WIRD, UND WARUM ES REGREET SEIN DARF
    regreet liegt auf dieser Entwicklungsmaschine nicht (`which regreet`
    am 13.08.2026: nichts) und laesst sich ohne $GREETD_SOCK auch nicht
    sinnvoll starten. Nachgebaut wird deshalb sein Widget-Baum - nicht
    aus dem Gedaechtnis, sondern aus src/gui/templates.rs des Tags 0.5.0,
    Zeile fuer Zeile: dieselben Widget-KLASSEN, dieselben CSS-Klassen,
    dieselben Raender, dieselbe Anordnung im Raster.

    Das ist genau so viel wert, wie es faithful ist, und deshalb steht
    neben jedem Widget unten die Zeile, aus der es kommt. Was fuer die
    FARBE zaehlt, ist ausschliesslich: welche Widget-Klasse traegt welche
    CSS-Klasse in welchem Elternteil. Das ist hier vollstaendig.

    Zwei Messungen stuetzen den Nachbau zusaetzlich:
      * regreet haengt NICHT an libadwaita. Cargo.toml des Tags 0.5.0
        nennt `gtk4 = "0.10"` und `relm4 = "0.10"` und kein adw. Die
        Maske steht also auf GTKs eigenem Adwaita, und dieses Skript
        setzt gtk-theme-name genauso.
      * Das Blatt haengt sich auf STYLE_PROVIDER_PRIORITY_APPLICATION
        (600) ein - component.rs Zeile 429 -, also ueber dem Thema (200).
        Dieses Skript nimmt dieselbe Prioritaet. Wo eine Regel hier
        gewinnt, gewinnt sie dort auch.

WIE GEMESSEN WIRD, UND WARUM NICHT AN FESTEN KOORDINATEN
    Feste Bildpunkte sind eine Messung, die beim naechsten Abstand
    danebenzeigt, ohne es zu sagen. Stattdessen meldet die Maske selbst,
    wo ihre Widgets liegen: compute_bounds() gegen das Fenster, in eine
    JSON-Datei. Das Bild wird danach GENAU in diesen Rechtecken
    ausgezaehlt, und was gemeldet wird, ist die haeufigste Farbe darin.

    Damit verschiebt sich die Messung mit dem Layout mit, und ein
    veraenderter Abstand kann kein falsches Ergebnis vortaeuschen.

SICHERHEIT
    Session.environment() lenkt HOME, alle XDG-Wurzeln und den
    Sitzungsbus auf eine Wegwerf-Sitzung um; refuse_the_real_session()
    haelt jeden Kindprozess dagegen. Diese Maske schreibt nichts, aber
    sie ist ein GTK-Programm im Hyprland des Nutzers - und ein
    verschachtelter Compositor ist der einzige Ort, an dem ein
    Anmeldebildschirm gefahrlos aufgehen darf. greetd, den Schirm und
    die laufende Sitzung fasst hier nichts an.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

BACKDROP = ROOT / "src" / "branding" / "zepos-backdrop.png"

# Die Groesse, in der das Vergleichsbild entstanden ist. Ein Bild in einer
# anderen Groesse waere neben key-07-03-anmeldung.png nicht zu halten.
WIDTH, HEIGHT = 1280, 800

# Die drei Zustaende, die dieser Bildschirm ueberhaupt hat.
#
# "passwort" war noch nie abgebildet, und genau dort sitzt das Feld, in
# das jemand sein Passwort tippt.
#
# "aufgeklappt" ist dazugekommen, weil der Nutzer am 13.08.2026
# ausdruecklich das AUFKLAPPFELD genannt hat ("style dropdown"). Das
# Aufklappmenue ist ein eigenes Fenster - ein `popover` mit
# `modelbutton`-Zeilen darin, GEMESSEN am selben Tag ueber
# get_css_name() -, also erreicht es KEINE der Regeln, die auf dem
# Feld sitzen. Wer nur das geschlossene Feld abbildet, hat die Haelfte
# des Bedienelements nie gesehen.
STATES = ("auswahl", "passwort", "aufgeklappt")


# ======================================================================
# Der Nachbau
# ======================================================================

def build_and_run(css: Path, state: str, greeting: str,
                  bounds_file: Path) -> int:
    """Die Maske aufbauen, zeigen und ihre Rechtecke melden.

    Laeuft NUR im Kindprozess (--maske). `gi` fehlt in .venv und ist
    systemweit da; welcher Interpreter beides kann, sucht
    gtk4_headless.gi_interpreter() - dieselbe Frage, die schon
    tests/installer/ und tests/menu/ stellen mussten.
    """
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk, Pango

    # --- Die Umgebung, die regreet.toml [GTK] setzt -------------------
    # Wortgleich zu src/login/regreet.toml. Ohne diese vier Zeilen misst
    # dieses Skript ein anderes Thema als die Maschine.
    settings = Gtk.Settings.get_default()
    settings.props.gtk_theme_name = "Adwaita"
    settings.props.gtk_application_prefer_dark_theme = True
    settings.props.gtk_font_name = "Roboto 16"
    settings.props.gtk_cursor_theme_name = "Adwaita"

    window = Gtk.Window()
    window.set_default_size(WIDTH, HEIGHT)
    window.set_decorated(False)

    # --- Das Blatt, auf derselben Sprosse wie bei regreet -------------
    provider = Gtk.CssProvider()
    provider.load_from_path(str(css))
    Gtk.StyleContext.add_provider_for_display(
        window.get_display(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    tracked: dict[str, Gtk.Widget] = {}

    # --- templates.rs, Ui: gtk::Overlay ------------------------------
    overlay = Gtk.Overlay()

    # templates.rs Z. 40: `gtk::Picture` als Kind, nicht als Overlay.
    # Es ist der Grund, aus dem eine CSS-Regel fuer den Fensterhintergrund
    # niemand je sieht - ein Widget liegt ueber dem CSS-Grund.
    picture = Gtk.Picture()
    if BACKDROP.is_file():
        picture.set_filename(str(BACKDROP))
    picture.set_content_fit(Gtk.ContentFit.COVER)
    overlay.set_child(picture)

    # --- Die Anmeldekachel: gtk::Frame + css "background" (Z. 43-46) --
    card = Gtk.Frame()
    card.set_halign(Gtk.Align.CENTER)
    card.set_valign(Gtk.Align.CENTER)
    card.add_css_class("background")
    tracked["kachel"] = card

    # templates.rs Z. 48-56
    grid = Gtk.Grid()
    grid.set_column_spacing(15)
    grid.set_row_spacing(15)
    grid.set_margin_top(15)
    grid.set_margin_bottom(15)
    grid.set_margin_start(15)
    grid.set_margin_end(15)
    grid.set_size_request(500, -1)
    card.set_child(grid)

    # templates.rs Z. 59-71: message_label, fett ueber Pango-Attribute -
    # also NICHT ueber CSS. Eine font-weight-Regel im Blatt erreicht
    # diese Zeile nicht.
    message = Gtk.Label(label=greeting)
    message.set_margin_bottom(15)
    attributes = Pango.AttrList()
    description = Pango.FontDescription()
    description.set_weight(Pango.Weight.BOLD)
    attributes.insert(Pango.attr_font_desc_new(description))
    message.set_attributes(attributes)
    grid.attach(message, 0, 0, 3, 1)
    tracked["begruessung"] = message

    def entry_label(text: str) -> Gtk.Label:
        """templates.rs Z. 24-30, EntryLabel: 100 breit, rechtsbuendig."""
        label = Gtk.Label(label=text)
        label.set_size_request(100, 45)
        label.set_xalign(1.0)
        return label

    user_label = entry_label("User:")
    grid.attach(user_label, 0, 1, 1, 1)
    tracked["beschriftung-benutzer"] = user_label

    # templates.rs Z. 89: gtk::ComboBoxText. In GTK 4.22 abgekuendigt und
    # vorhanden - und es ist das Widget, um das der Nutzer bittet.
    usernames = Gtk.ComboBoxText()
    usernames.set_hexpand(True)
    # Drei Konten, weil eine Auswahlliste mit einem Eintrag nicht zeigt,
    # dass sie eine ist. Der mittlere hiess bis zum 17.08.2026 nach dem
    # Konto des Autors auf seinem eigenen Rechner; ein Bild, das in die
    # Veroeffentlichung geht, nennt keinen Anmeldenamen. "zweiter" tut
    # dasselbe: er ist weder der Erste noch der Gast.
    for entry in ("tester", "zweiter", "gast"):
        usernames.append_text(entry)
    usernames.set_active(0)
    grid.attach(usernames, 1, 1, 1, 1)
    tracked["feld-benutzer"] = usernames

    # templates.rs Z. 120-125: gtk::ToggleButton mit Stiftsymbol.
    user_toggle = Gtk.ToggleButton()
    user_toggle.set_icon_name("document-edit-symbolic")
    grid.attach(user_toggle, 2, 1, 1, 1)
    tracked["stift-benutzer"] = user_toggle

    # Die Sitzungszeile UND die Passwortzeile liegen im SELBEN Feld des
    # Rasters - (0,2) und (1,2). Das ist keine Vereinfachung dieses
    # Nachbaus, sondern steht so in templates.rs (Z. 82/97 gegen
    # Z. 106/112): im Passwortzustand ERSETZT das Passwort die Sitzung.
    session_label = entry_label("Session:")
    sessions = Gtk.ComboBoxText()
    sessions.append_text("ZepOS")
    sessions.set_active(0)
    sess_toggle = Gtk.ToggleButton()
    sess_toggle.set_icon_name("document-edit-symbolic")

    input_label = entry_label("Password:")
    secret = Gtk.PasswordEntry()
    secret.set_show_peek_icon(True)
    secret.set_hexpand(True)
    secret.set_text("geheim")

    if state == "passwort":
        grid.attach(input_label, 0, 2, 1, 1)
        grid.attach(secret, 1, 2, 1, 1)
        tracked["beschriftung-passwort"] = input_label
        tracked["feld-passwort"] = secret
    else:
        grid.attach(session_label, 0, 2, 1, 1)
        grid.attach(sessions, 1, 2, 1, 1)
        grid.attach(sess_toggle, 2, 2, 1, 1)
        tracked["beschriftung-sitzung"] = session_label
        tracked["feld-sitzung"] = sessions
        tracked["stift-sitzung"] = sess_toggle

    # templates.rs Z. 133-152: die Knopfzeile, rechtsbuendig.
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
    actions.set_halign(Gtk.Align.END)
    # component.rs Z. 309-311: "Cancel" ist NUR im Eingabezustand da.
    cancel = Gtk.Button(label="Cancel")
    if state == "passwort":
        actions.append(cancel)
        tracked["knopf-abbrechen"] = cancel
    login = Gtk.Button(label="Login")
    login.add_css_class("suggested-action")
    actions.append(login)
    tracked["knopf-login"] = login
    grid.attach(actions, 1, 3, 2, 1)

    overlay.add_overlay(card)

    # --- Die Uhr: Frame + "background", oben mittig (Z. 158-170) ------
    clock_frame = Gtk.Frame()
    clock_frame.set_halign(Gtk.Align.CENTER)
    clock_frame.set_valign(Gtk.Align.START)
    clock_frame.add_css_class("background")
    # Z. 164-169 setzt genau diese drei Zeilen als inline_css. Inline
    # schlaegt JEDE Regel eines Providers - was hier steht, ist mit dem
    # Blatt nicht zu erreichen.
    clock_css = Gtk.CssProvider()
    clock_css.load_from_string(
        "frame { border-top-right-radius: 0px;"
        " border-top-left-radius: 0px; border-top-width: 0px; }")
    clock_frame.get_style_context().add_provider(
        clock_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    clock_label = Gtk.Label(label=time.strftime("Do %H:%M"))
    clock_label.set_justify(Gtk.Justification.CENTER)
    clock_frame.set_child(clock_label)
    overlay.add_overlay(clock_frame)
    tracked["uhr"] = clock_frame

    # --- Der untere Streifen (Z. 173-222) -----------------------------
    bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
    bottom.set_halign(Gtk.Align.CENTER)
    bottom.set_valign(Gtk.Align.END)
    bottom.set_margin_bottom(15)

    ends = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
    ends.set_halign(Gtk.Align.CENTER)
    ends.set_homogeneous(True)
    # templates.rs Z. 15-18, EndButton: gtk::Button + "destructive-action".
    # BEIDE tragen dieselbe Klasse - der Grund, aus dem src/greeter.py
    # das Ausschalten ueber :last-child auseinanderhaelt.
    reboot = Gtk.Button(label="Reboot")
    reboot.add_css_class("destructive-action")
    poweroff = Gtk.Button(label="Power Off")
    poweroff.add_css_class("destructive-action")
    ends.append(reboot)
    ends.append(poweroff)
    bottom.append(ends)
    tracked["knopf-neustart"] = reboot
    tracked["knopf-ausschalten"] = poweroff
    overlay.add_overlay(bottom)

    window.set_child(overlay)
    window.present()

    def report() -> bool:
        """Wo jedes Widget liegt - erst, wenn wirklich gezeichnet wurde."""
        boxes = {}
        for name, widget in tracked.items():
            ok, rect = widget.compute_bounds(window)
            if not ok:
                continue
            if rect.size.width < 1 or rect.size.height < 1:
                continue
            boxes[name] = [round(rect.origin.x), round(rect.origin.y),
                           round(rect.size.width), round(rect.size.height)]
        bounds_file.write_text(json.dumps(boxes, indent=2), encoding="utf-8")
        return False

    def open_then_report() -> bool:
        # popup() ist in GTK 4.22 abgekuendigt und da - dasselbe gilt
        # fuer die GtkComboBoxText darunter, die regreet benutzt. Ein
        # Klick liesse sich hier nicht schicken: Hyprland 0.55.4 hat
        # keinen Druck-Dispatcher (siehe der Kopf von settings_shot.py).
        usernames.popup()
        GLib.timeout_add(700, report)
        return False

    # Ein Herzschlag nach dem ersten Rahmen. Vorher liefert
    # compute_bounds() Rechtecke der Groesse Null, und die JSON-Datei
    # waere da, bevor irgendetwas darin stimmt.
    GLib.timeout_add(1500,
                     open_then_report if state == "aufgeklappt" else report)
    GLib.MainLoop().run()
    return 0


# ======================================================================
# Das Auszaehlen
# ======================================================================

def dominant(image, box: list[int], inset: int = 3) -> tuple[str, float]:
    """Die haeufigste Farbe in einem Rechteck, und ihr Anteil.

    `inset` schneidet den Rand weg. Ohne ihn zaehlt jede Messung die
    Rahmenlinie und die Kantenglaettung mit, und ein 1px-Rand in einer
    anderen Farbe verschoebe das Ergebnis eines schmalen Knopfes.
    """
    x, y, w, h = box
    x0, y0 = x + inset, y + inset
    x1, y1 = x + w - inset, y + h - inset
    if x1 <= x0 or y1 <= y0:
        x0, y0, x1, y1 = x, y, x + w, y + h
    counter: Counter = Counter()
    for py in range(max(0, y0), min(image.height, y1)):
        for px in range(max(0, x0), min(image.width, x1)):
            counter[image.getpixel((px, py))] += 1
    if not counter:
        return "-", 0.0
    (colour, count), = counter.most_common(1)
    return "#%02X%02X%02X" % colour, count / sum(counter.values())


def measure(shot: Path, bounds: Path) -> list[str]:
    from PIL import Image
    image = Image.open(shot).convert("RGB")
    boxes = json.loads(bounds.read_text(encoding="utf-8"))
    lines = []
    for name in sorted(boxes):
        colour, share = dominant(image, boxes[name])
        x, y, w, h = boxes[name]
        lines.append(f"    {name:24s} {colour}  {share:5.0%}"
                     f"   {w}x{h} bei {x},{y}")
    return lines


# ======================================================================
# Der Aufbau
# ======================================================================

def shoot(session, css: Path, state: str, greeting: str,
          out: Path, theme_name: str) -> str:
    from gtk4_headless import gi_interpreter

    found = gi_interpreter({"Gtk": "4.0"})
    assert found is not None, "Kein Interpreter dieser Maschine kann Gtk 4.0"
    executable, extra = found

    bounds = out / f"anmeldung-{theme_name}-{state}.json"
    bounds.unlink(missing_ok=True)
    environment = {}
    if extra:
        environment["PYTHONPATH"] = ":".join(extra)

    process = session.spawn(
        [executable, str(Path(__file__).resolve()), "--maske",
         "--css", str(css), "--zustand", state, "--gruss", greeting,
         "--rechtecke", str(bounds)],
        log=out / f"anmeldung-{theme_name}-{state}.log",
        **environment)

    # Auf die Rechteck-Datei warten, nicht auf eine Uhr: die Maske sagt
    # selbst, wann sie gezeichnet hat.
    deadline = time.monotonic() + 60
    client = None
    while time.monotonic() < deadline:
        if bounds.is_file():
            clients = session.hyprctl_json("clients") or []
            # Das GROESSTE Fenster, nicht das erste. Im Zustand
            # "aufgeklappt" liegt das Aufklappmenue als eigene Flaeche
            # daneben, und ein Bild davon allein waere ein Bild ohne die
            # Maske, zu der es gehoert.
            mapped = [c for c in clients if c.get("mapped")
                      and c.get("size", [0, 0])[0] > 1]
            if mapped:
                client = max(mapped,
                             key=lambda c: c["size"][0] * c["size"][1])
                break
        if process.poll() is not None:
            break
        time.sleep(0.3)

    if client is None:
        process.terminate()
        return (f"{theme_name}/{state}: kein Fenster - siehe "
                f"anmeldung-{theme_name}-{state}.log")

    x, y = client["at"]
    width, height = client["size"]
    shot = out / f"anmeldung-{theme_name}-{state}.png"
    session.shoot(shot, geometry=f"{x},{y} {width}x{height}")

    process.terminate()
    try:
        process.wait(timeout=10)
    except Exception:
        process.kill()

    report = [f"{theme_name}/{state}: {shot.name} ({width}x{height})"]
    report += measure(shot, bounds)
    return "\n".join(report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maske", action="store_true",
                        help="Kindmodus: die Maske selbst (nicht von Hand)")
    parser.add_argument("--css", type=Path)
    parser.add_argument("--zustand", default="auswahl", choices=STATES)
    parser.add_argument("--gruss", default="Willkommen bei ZepOS")
    parser.add_argument("--rechtecke", type=Path)
    parser.add_argument("--thema", action="append", dest="themes")
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "anmeldung")
    arguments = parser.parse_args()

    if arguments.maske:
        return build_and_run(arguments.css, arguments.zustand,
                             arguments.gruss, arguments.rechtecke)

    import greeter
    import theme as theme_module
    from render.desktop_session import Session

    themes = tuple(arguments.themes or sorted(theme_module.THEMES))
    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)

    # Kein start(): __enter__ ruft es bereits. Ein zweiter Aufruf setzt
    # einen zweiten Compositor ueber den ersten.
    with Session(WIDTH, HEIGHT) as session:
        session.start_bus()
        for name in themes:
            css = ROOT / "src" / "login" / greeter.filename(name)
            if not css.is_file():
                print(f"{name}: {css} fehlt")
                continue
            for state in STATES:
                print(shoot(session, css, state,
                            "Willkommen bei ZepOS", out, name))

    print(f"\nBilder und Messungen in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
