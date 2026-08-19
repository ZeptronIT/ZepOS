# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Entscheidung vom 11.08.2026: die Oberflaeche steht auf GTK4.

WARUM DIESE DATEI EXISTIERT
    Weil die Entscheidung an mehreren Stellen gleichzeitig gilt und an
    jeder einzelnen still zurueckgenommen werden kann. Ein Paket, das
    wieder gtk3 fordert, eine Bindung, die wieder wlogout aufruft, ein
    pinentry-program, das wieder auf den GTK3-Dialog zeigt - keins davon
    faellt beim Bauen auf, keins beim Starten, und das Ergebnis ist ein
    Desktop, der zur Haelfte auf dem alten Toolkit steht, ohne dass
    irgendwo ein Fehler stuende.

WAS SIE NICHT KANN
    Sie misst Text, keine Objekte. Ob das gebaute Binary wirklich gegen
    libgtk-4 gelinkt ist, kann nur `readelf -d` am fertigen Objekt sagen;
    das tun packaging/zepos-lock/PKGBUILD zur Paketzeit und
    packaging/verify-install.sh an der installierten Datei, und
    tests/packaging/test_recipes.py haelt fest, dass die beiden es
    ueberhaupt tun.

WAS GEMESSEN WURDE, UND WAS SICH DABEI ALS FALSCH ERWIESEN HAT
    * wlogout kann kein GTK4. HEAD 350fe88 vom 26.05.2024 fordert in
      meson.build `gtk+-wayland-3.0`; `git grep -i gtk4` findet im ganzen
      Baum nichts.
    * wleave KANN GTK4 - Cargo.toml von HEAD 0cc1a0b (25.07.2026) nennt
      gtk4 0.10, gtk4-layer-shell 0.7 und libadwaita 0.8. Die Vermutung
      war also richtig. Es steht trotzdem nicht hier: 295 Kisten aus
      Cargo.lock, die zur Bauzeit von crates.io geholt wuerden, sind das,
      was packaging/aylurs-gtk-shell/PKGBUILD unter "WHY THE NPM
      DEPENDENCY IS A SOURCE AND NOT A BUILD STEP" ausschliesst, und
      packaging/Dockerfile hat keine Rust-Werkzeugkette.
    * Es gibt KEIN GTK4-pinentry. pinentry HEAD 15b7e8a (03.07.2026)
      nennt gtk4 im ganzen Baum nicht, und gcr-4 4.4.0.1-1 bringt
      entgegen der Erwartung keinen Prompter mit - nur gcr-viewer-gtk4,
      gcr-ssh-agent und gcr4-ssh-askpass. Deshalb ist die Antwort dort
      "kein GTK3" und nicht "GTK4".
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PACKAGING = ROOT / "packaging"


@pytest.fixture
def ssot(monkeypatch):
    """brand.py und style_definition.py, so importiert, wie der Generator
    sie importiert.

    Dieselbe Fixture-Form wie in tests/src/test_brand.py und aus
    demselben Grund: src/ hat kein __init__.py, jedes Modul darin
    importiert flach, also muss das Verzeichnis auf den Pfad statt das
    Paket. monkeypatch nimmt ihn danach wieder herunter.

    Das ist hier nicht Formsache, sondern gemessen: mit einem `sys.path.
    insert`, das stehen blieb, fiel
    tests/src/test_placeholders.py::test_a_missing_style_ssot_stops_the
    _run_instead_of_emptying_it um - es kopiert template_processor.py in
    ein Verzeichnis OHNE style_definition.py und prueft, dass der Import
    abbricht, und ein liegengelassenes src/ auf dem Pfad laesst ihn
    gelingen.
    """
    monkeypatch.syspath_prepend(str(SRC))
    monkeypatch.delitem(__import__("sys").modules, "brand", raising=False)
    monkeypatch.delitem(__import__("sys").modules, "style_definition",
                        raising=False)
    import brand

    spec = importlib.util.spec_from_file_location(
        "zepos_style_definition_gtk4_probe", SRC / "style_definition.py")
    style = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(style)
    return brand, style


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} fehlt"
    return path.read_text(encoding="utf-8")


def _uncommented(text: str, marker: str = "#") -> list[str]:
    """Die Zeilen ohne die, die nur Kommentar sind.

    Der Grund ist die Falle, in die diese Aenderung selbst gelaufen ist:
    jede Datei in diesem Baum ERKLAERT, was sie nicht tut, und eine
    Pruefung der Form `"wlogout" in text` wird von der Erklaerung wahr,
    in der steht, dass wlogout entfernt wurde.
    """
    return [line.strip() for line in text.splitlines()
            if not line.lstrip().startswith(marker)]


# --------------------------------------------------------------------
# Die Sitzungsmaske
# --------------------------------------------------------------------
#
# BIS ZUM 19.08.2026 HIESS DIESER ABSCHNITT "Die Abmeldemaske" UND
# PRUEFTE EIN EIGENES C-PROGRAMM
#     zepos-logout war ein eigenstaendiges GTK4-Binary neben AGS - und
#     gehoerte damit in DIESE Datei, deren ganzer Zweck ist, dass ein
#     Programm nicht STILL auf GTK3 zurueckfaellt (siehe den Dateikopf).
#     Aufgabe 26 hat es entfernt (Regel 14 - geloescht, nicht als
#     veraltet markiert) und durch src/templates/ags-logout.template
#     ersetzt: ein Fenster IM LAUFENDEN AGS-Prozess, der ohnehin schon
#     auf GTK4 steht. Ein eigener Regressionstest "faellt es auf GTK3
#     zurueck" ergibt fuer diesen Nachfolger keinen Sinn mehr - AGS ist
#     bereits gepruefter GTK4-Bestand (test_the_bar_and_the_dock_are_
#     astal_windows_on_gtk4 unten).
#
#     Was bleibt UND WEITERHIN HIERHIN GEHOERT: dass wlogout nirgends
#     mehr installiert wird (der eigentliche GTK3-Regressionsfall), und
#     dass SUPER+M wirklich das neue Fenster erreicht - nicht mehr, weil
#     ein Rueckfall auf GTK3 drohte, sondern weil eine stumme Taste
#     derselbe Fehler waere, den dieser ganze Baum an keiner Stelle
#     duldet.

def test_super_m_toggles_the_ags_logout_window():
    """SUPER+M muss die Taste bleiben, und sie muss das AGS-Fenster
    erreichen - nicht mehr ein eigenes Programm starten.

    `ags request logout` und nicht `exec zepos-logout`: derselbe Weg wie
    `ags request dock` fuer SUPER+B (siehe test_super_b_toggles_the_
    gtk4_dock unten). Der Nutzer hatte gemeldet, SUPER+M oeffne bei
    jedem Druck ein neues Fenster ueber dem alten - genau der Unterschied
    zwischen einem PROZESSSTART (zepos-logout) und einer ANFRAGE an den
    laufenden Prozess, der die Sichtbarkeit umschaltet (toggleWidget()
    in ags-config.template).
    """
    lines = _uncommented(
        _read(SRC / "templates" / "hyprland-universal-config.template"))
    binds = [line for line in lines if line.startswith("bind")]

    assert "bind = $mainMod, M, exec, ags request logout" in binds, (
        "SUPER+M erreicht das AGS-Fenster nicht")
    assert not any("wlogout" in line for line in binds), (
        "eine Bindung ruft weiterhin wlogout auf")
    assert not any(re.search(r"\bzepos-logout\b", line) for line in binds), (
        "eine Bindung ruft weiterhin das entfernte zepos-logout auf")


def test_nothing_in_the_tree_still_installs_wlogout():
    """Der Vorgaenger ist weg, nicht bloss ueberholt.

    Beide nebeneinander waeren zwei Abmeldemasken, von denen eine
    libgtk-3 hereinzieht - und die Entscheidung waere formal erfuellt und
    tatsaechlich nicht.
    """
    offenders = []

    packages = _uncommented(_read(ROOT / "iso" / "profile" / "packages.x86_64"))
    if "wlogout" in packages:
        offenders.append("iso/profile/packages.x86_64")

    for recipe in sorted(PACKAGING.glob("*/PKGBUILD")):
        for line in _uncommented(_read(recipe)):
            if re.search(r"^\s*'wlogout'|pkgname=wlogout\b", line):
                offenders.append(f"packaging/{recipe.parent.name}/PKGBUILD")
                break

    assert not (PACKAGING / "wlogout").exists(), (
        "packaging/wlogout/ steht noch da und wird von build.sh gebaut")
    assert offenders == [], f"installieren weiterhin wlogout: {offenders}"


def test_nothing_in_the_tree_still_installs_zepos_logout():
    """Und der EIGENE Vorgaenger ist ebenso weg - Regel 14, keine
    veraltete Datei stehengelassen.

    Beide nebeneinander (das alte C-Programm und das neue AGS-Fenster)
    waeren die Doppelung, die Aufgabe 26 an vier Stellen desselben
    Projekttags abgeraeumt hat.
    """
    assert not (Path(__file__).resolve().parents[2]
                / "logout").exists(), (
        "logout/ steht noch da - zepos-logout.c ist nicht wirklich weg")
    assert not (PACKAGING / "zepos-logout").exists(), (
        "packaging/zepos-logout/ steht noch da und wird von build.sh "
        "gebaut")
    assert not (SRC / "templates" / "logout-config.template").exists(), (
        "logout-config.template steht noch da")
    assert not (SRC / "styles" / "logout-style.template").exists(), (
        "logout-style.template steht noch da")

    generator = "\n".join(_uncommented(_read(SRC / "generate_config.sh")))
    assert "logout-config" not in generator, (
        "der Generator hat weiterhin eine Route fuer logout-config")
    assert "logout-style" not in generator, (
        "der Generator hat weiterhin eine Route fuer logout-style")


# --------------------------------------------------------------------
# Der Sperrbildschirm
# --------------------------------------------------------------------
#
# WAS AM 12.08.2026 GEMESSEN WURDE
#     hyprlock ist kein GTK3-Programm, sondern gar keins:
#
#         objdump -p /usr/bin/hyprlock | grep NEEDED
#           NEEDED  libpam.so.0
#           NEEDED  libEGL.so.1
#           NEEDED  libGLESv2.so.2
#           NEEDED  libcairo.so.2
#           ... und keine Zeile mit gtk
#
#     Es zeichnet sich mit GLES und Cairo selbst. Die GTK4-Regel griff
#     also nicht - die Besitz-Regel schon, und der Nutzer hat sie am
#     11.08.2026 angewandt: "4 sollten wir selber machen also
#     sperrbildschirm gtk4".
#
#     Die offene Frage war, ob GTK4 ext-session-lock-v1 hergibt, ohne
#     das ein Sperrbildschirm nur ein Fenster ist. Antwort: ja.
#     gtk4-layer-shell 1.3.0 liefert gtk4-session-lock.h mit. Die
#     Messungen dazu stehen im Kopf von lock/zepos-lock.c, und
#     tests/lock/ faehrt sie in einem verschachtelten Compositor nach -
#     diese Datei misst weiterhin Text.


def test_super_l_calls_the_gtk4_lock_screen():
    """SUPER+L muss die Taste bleiben, und sie muss auf das eigene
    Programm zeigen.

    Zeilengenau und ohne Kommentare, weil die Vorlage ueber der Bindung
    ausdruecklich ERKLAERT, was dort einmal stand - ein
    Teilzeichenketten-Test waere von der Erklaerung wahr geworden.
    """
    lines = _uncommented(
        _read(SRC / "templates" / "hyprland-universal-config.template"))
    binds = [line for line in lines if line.startswith("bind")]

    assert "bind = $mainMod, L, exec, zepos-lock" in binds, (
        "SUPER+L ruft zepos-lock nicht auf")
    assert not any("hyprlock" in line for line in binds), (
        "eine Bindung ruft weiterhin hyprlock auf")


def test_nothing_in_the_tree_still_installs_hyprlock():
    """Der Vorgaenger ist weg, nicht bloss ueberholt.

    Beide nebeneinander waeren zwei Sperrbildschirme, von denen einer
    nicht auf der Marke steht und keine Taste mehr hat. Derselbe Test
    wie bei wlogout oben, in beide Richtungen - und zusaetzlich die
    Vorlage, denn hyprlock war das einzige Programm im Baum, dessen
    Farben nicht aus brand.py kommen KONNTEN.
    """
    offenders = []

    packages = _uncommented(_read(ROOT / "iso" / "profile" / "packages.x86_64"))
    if "hyprlock" in packages:
        offenders.append("iso/profile/packages.x86_64")

    for recipe in sorted(PACKAGING.glob("*/PKGBUILD")):
        for line in _uncommented(_read(recipe)):
            # conflicts=('hyprlock') im eigenen Rezept ist das Gegenteil
            # einer Installation und darf stehen bleiben.
            if line.startswith("conflicts="):
                continue
            if re.search(r"^\s*'hyprlock'|pkgname=hyprlock\b", line):
                offenders.append(f"packaging/{recipe.parent.name}/PKGBUILD")
                break

    assert not (SRC / "templates" / "hyprlock-config.template").exists(), (
        "die Vorlage von hyprlock steht noch da und wird erzeugt")
    assert "hyprlock-config" not in "\n".join(
        _uncommented(_read(SRC / "generate_config.sh"))), (
        "der Generator hat weiterhin eine Route fuer hyprlock")
    assert offenders == [], f"installieren weiterhin hyprlock: {offenders}"


def test_the_lock_screen_replaced_hyprlock_everywhere_it_was_called():
    """Nicht nur die Taste. hyprlock stand an mehreren Stellen.

    BIS ZUM 19.08.2026 WAREN ES DREI: die Taste, ein `lock`-Knopf in
    logout-config.template (dem alten zepos-logout) und einer im
    Kontrollzentrum von AGS - beide riefen `pidof hyprlock || hyprlock`.
    Aufgabe 26 hat logout-config.template mit zepos-logout geloescht und
    das Kontrollzentrum umgebaut: sein "Sitzung"-Knopf oeffnet seither
    NUR NOCH das AGS-Fenster (ags-logout.template), statt selbst einen
    Befehl zu kennen - siehe opens("logout") dort. Es bleibt also EINE
    Stelle neben der Taste, die "zepos-lock" wirklich noch kennen muss:
    das neue Fenster selbst.
    """
    body = "\n".join(_uncommented(
        _read(SRC / "templates" / "ags-logout.template")))
    assert "hyprlock" not in body, "ags-logout.template ruft weiterhin hyprlock"
    assert "zepos-lock" in body, (
        "ags-logout.template kennt den Sperrbildschirm nicht mehr")

    # Und das Kontrollzentrum ruft "zepos-lock" NICHT MEHR SELBST - tut
    # es das doch, ist die Doppelung zurueck, die dieser Umbau gerade
    # abgeraeumt hat.
    control = "\n".join(_uncommented(
        _read(SRC / "templates" / "ags-control-center.template")))
    assert "zepos-lock" not in control, (
        "ags-control-center.template ruft zepos-lock wieder selbst auf, "
        "statt das Sitzungsfenster zu oeffnen")


def test_the_lock_screen_stylesheet_is_generated_before_every_session():
    """Es ist die einzige erzeugte Datei, die dieser Bildschirm liest.

    Ohne sie sperrt er trotzdem - das ist der Unterschied zur
    Abmeldemaske und der Grund, aus dem er keine Layout-Datei hat. Diese
    Zeile sorgt also nicht dafuer, dass SUPER+L funktioniert, sondern
    dafuer, dass es dabei nach ZepOS aussieht.
    """
    status = _uncommented(
        _read(SRC / "templates" / "hyprland-status-config.template"))
    assert "./generate_config.sh -lock-style" in status, (
        "der Stil des Sperrbildschirms wird beim Sitzungsstart nicht erzeugt")


def test_the_lock_screen_style_has_no_colour_of_its_own(ssot):
    """Jede Farbe aus der Mitte, keine im Stylesheet.

    hyprlocks Vorlage trug zwoelf rgb()- und rgba()-Literale in
    Terminalgruen auf einem #0c0c0c. Genau das ist der Zustand, den
    dieser Ersatz beenden sollte; ein Literal, das hier wieder auftaucht,
    stellt ihn her.
    """
    text = _read(SRC / "styles" / "lock-style.template")
    body = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    literals = re.findall(r"#[0-9A-Fa-f]{3,8}\b", body)
    # Die Knotennamen sind CSS-Selektoren wie box#card, keine Farben.
    literals = [lit for lit in literals if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", lit)]
    assert literals == [], f"Farbliterale in der Stilvorlage: {literals}"
    assert not re.search(r"\brgba?\(", body), (
        "eine rgb()- oder rgba()-Zeile ist zurueck - genau die Form, in der "
        "hyprlocks Farben standen")

    # Und die Gegenrichtung, denn "keine Literale" ist auch fuer eine
    # leere Datei wahr: die tragenden Flaechen muessen benannt sein.
    for name in ("BACKDROP", "SCRIM", "AVATAR_BG", "FIELD_BG",
                 "FAILURE_COLOR"):
        assert f"{{{{STYLE_LOCK_{name}}}}}" in body, (
            f"STYLE_LOCK_{name} steht nicht in der Stilvorlage")

    # Und die Kachel ist WEG, nicht bloss ungenutzt. Sie war das
    # Auffaelligste im Bild und der Grund, aus dem der Bildschirm wie
    # ein Formular aussah; ein Schluessel, der sie beschreibt und den
    # niemand liest, holt sie beim naechsten Lesen zurueck.
    _brand, style = ssot
    leftovers = [key for key in style.STYLE_VARIABLES
                 if key.startswith("STYLE_LOCK_CARD")]
    assert leftovers == [], f"Schluessel der geloeschten Kachel: {leftovers}"


def test_the_lock_screen_gets_no_glass(ssot):
    """Ein Sperrbildschirm soll den Schreibtisch VERBERGEN.

    Zwei Wege, auf denen Glas hierher kaeme, und beide sind zu:
    GLASS_LAYERS darf diesen Namensraum nicht nennen, und
    misc:session_lock_xray - Hyprlands eigener Schalter, um den
    Schreibtisch DURCH die Sperre zu zeigen - darf nirgends
    eingeschaltet werden.

    Technisch koennte eine layerrule ohnehin nicht greifen: eine
    ext_session_lock_surface_v1 hat keinen Layer-Shell-Namensraum.
    tests/lock/test_lock_screen.py misst das am laufenden Compositor.
    """
    _brand, style = ssot

    assert "zepos-lock" not in style.GLASS_LAYERS, (
        "der Sperrbildschirm steht in GLASS_LAYERS - eine Sperre, durch die "
        "man den Schreibtisch sieht")

    universal = _read(SRC / "templates" / "hyprland-universal-config.template")
    lines = _uncommented(universal)
    assert not any("session_lock_xray" in line for line in lines), (
        "misc:session_lock_xray steht in der Vorlage - damit zeigt der "
        "Compositor den Schreibtisch durch die Sperre hindurch")


# --------------------------------------------------------------------
# Die Passphrasen-Abfrage
# --------------------------------------------------------------------

def test_the_pinentry_is_chosen_explicitly_and_is_not_the_gtk3_one():
    """Ohne diese Zeile waehlt das Wrapper-Skript, und es waehlt GTK3.

    Gemessen in einem Container auf dem angehefteten Schnappschuss
    2026/08/04 mit genau dem, was die ZepOS-Huelle enthaelt (gnupg, gtk3,
    kein gcr): von den fuenf Kandidaten des Skripts faellt gnome3 aus
    (libgcr-base-3.so.1 nicht gefunden) und qt faellt aus (Qt6 nicht
    gefunden), also nimmt es gtk - und `objdump -p /usr/bin/pinentry-gtk`
    nennt libgtk-3.so.0.
    """
    lines = _uncommented(_read(SRC / "system" / "gpg-agent-config.template"))
    programs = [line for line in lines if line.startswith("pinentry-program")]

    assert programs == ["pinentry-program /usr/bin/pinentry-bemenu"], (
        "gpg-agent.conf waehlt das pinentry nicht eindeutig aus: "
        f"{programs}")
    # Zeilengenau statt als Teilzeichenkette, weil der Kopf der Datei
    # pinentry-gtk und pinentry-gnome3 ausdruecklich NENNT, um zu
    # begruenden, warum sie es nicht sind.
    for gtk3 in ("pinentry-gtk", "pinentry-gnome3"):
        assert not any(line.startswith(f"pinentry-program /usr/bin/{gtk3}")
                       for line in lines), (
            f"gpg-agent zeigt wieder auf {gtk3}, das auf libgtk-3 steht")


def test_the_desktop_installs_the_pinentry_it_names():
    """Ein pinentry-program, das nicht existiert, ist schlimmer als der
    GTK3-Dialog: gpg-agent bricht dann bei jeder Passphrase ab.

    Und der Renderer muss namentlich dastehen. bemenu haengt auf das
    virtuelle `bemenu-renderer`, das bemenu-wayland und bemenu-x11
    gleichermassen erfuellen; welchen pacman naehme, entschiede pacman.
    """
    lines = _uncommented(_read(PACKAGING / "zepos-desktop" / "PKGBUILD"))
    assert "'pinentry-bemenu'" in lines, (
        "zepos-desktop installiert das pinentry nicht, auf das es zeigt")
    assert "'bemenu-wayland'" in lines, (
        "der bemenu-Renderer ist der Auswahl von pacman ueberlassen")


def test_the_passphrase_prompt_is_masked_and_on_the_brand(ssot):
    """Zwei Dinge an einer Zeichenkette, und das erste ist kein Aussehen.

    bemenu zeigt ohne -x die Eingabe im Klartext. Bei einem Menue ist das
    der Sinn; bei einer Passphrase ist es die Passphrase auf dem
    Bildschirm. Die Flagge kommt aus derselben Zeichenkette wie die
    Farben, also wird sie hier mitgehalten - sonst faellt sie mit dem
    naechsten Umbau der Farben heraus.
    """
    brand, style_definition = ssot
    opts = style_definition._FIXED_STYLE_VARIABLES["STYLE_PINENTRY_BEMENU_OPTS"]

    assert re.search(r"(^|\s)-x(\s|$)", opts), (
        "ohne -x zeigt bemenu die Passphrase im Klartext")

    # Und die Farben kommen aus der Mitte. Geprueft wird, dass jedes Hex
    # in der Zeichenkette eine Farbe der Marke IST - nicht bloss, dass
    # irgendein brand-Name vorkommt.
    palette = {value for name, value in vars(brand).items()
               if name.isupper() and isinstance(value, str)
               and re.fullmatch(r"#[0-9A-Fa-f]{6}", value)}
    used = set(re.findall(r"#[0-9A-Fa-f]{6}", opts))
    assert used, "die Abfrage traegt ueberhaupt keine Farbe"
    assert used <= palette, (
        f"Farben ausserhalb der Marke: {sorted(used - palette)}")


# --------------------------------------------------------------------
# Die Leiste und das Dock
# --------------------------------------------------------------------
#
# WAS AM 11.08.2026 GEMESSEN WURDE
#     * waybar ist GTK3 und bleibt es. meson.build von HEAD verlangt
#       `gtkmm-3.0`; ein GTK4-Zweig existiert nicht.
#     * nwg-dock-hyprland hat gar keine GTK4-Fassung - `git grep -i gtk4`
#       in seinem Baum findet nichts.
#     * Astals eigene Ablage waere der naheliegende Ersatz gewesen und
#       ist es nicht: lib/tray/meson.build des angehefteten Archivs
#       verlangt `dependency('appmenu-glib-translator')`, und
#       `pacman -Si appmenu-glib-translator` antwortet "Paket wurde nicht
#       gefunden". Das Paket ist im AUR, das Spec §4.3 ausgeschlossen
#       hat. Deshalb ist die Ablage in ags-tray.template unsere.
#
# Diese Datei misst weiterhin Text. Ob die fertige Leiste wirklich auf
# libgtk-4 laeuft, misst tests/src/test_bar_headless.py am
# /proc/self/maps des Prozesses, der sie gezeichnet hat.

BAR_DIRECTORY_PATTERN = re.compile(r'ZEPOS_OUTPUT_ROOT/(?:waybar|nwg-dock)')


def test_nothing_in_the_tree_still_installs_the_gtk3_bar():
    """Die Vorgaenger sind weg, nicht bloss ueberholt.

    Beide nebeneinander waeren zwei Leisten, von denen eine libgtk-3
    hereinzieht - und die Entscheidung waere formal erfuellt und
    tatsaechlich nicht. Dasselbe Argument wie bei wlogout oben, und
    derselbe Test in beide Richtungen.
    """
    offenders = []

    packages = _uncommented(_read(ROOT / "iso" / "profile" / "packages.x86_64"))
    for name in ("waybar", "nwg-dock-hyprland"):
        if name in packages:
            offenders.append(f"iso/profile/packages.x86_64 -> {name}")

    for recipe in sorted(PACKAGING.glob("*/PKGBUILD")):
        for line in _uncommented(_read(recipe)):
            if re.search(r"^\s*'(waybar|nwg-dock-hyprland)'", line):
                offenders.append(f"packaging/{recipe.parent.name}/PKGBUILD -> {line}")

    verify = _uncommented(_read(PACKAGING / "verify-install.sh"))
    for line in verify:
        if re.search(r"(?<![\w-])(waybar|nwg-dock-hyprland)(?![\w-])", line):
            offenders.append(f"packaging/verify-install.sh -> {line}")

    assert offenders == [], (
        "installieren oder erwarten weiterhin die GTK3-Leiste: "
        + "; ".join(offenders))


def test_no_line_of_the_session_starts_the_gtk3_bar_or_dock():
    """Ein exec-once, das keiner mehr liest, ist der teuerste Rueckfall:
    er kostet kein Paket, sondern einen Prozess auf jedem Schreibtisch.

    Zeilengenau und ohne Kommentare, weil die Datei ausdruecklich
    ERKLAERT, was dort einmal stand.
    """
    lines = _uncommented(
        _read(SRC / "templates" / "hyprland-universal-config.template"))
    starting = [line for line in lines
                if line.startswith(("exec-once", "exec ", "bind"))]

    offenders = [line for line in starting
                 if re.search(r"(?<![\w-])(waybar|nwg-dock-hyprland|"
                              r"nwg-dock-toggle|waybar-launcher)(?![\w-])", line)]
    assert offenders == [], f"die Sitzung startet weiterhin: {offenders}"


def test_super_b_toggles_the_gtk4_dock():
    """Die Taste bleibt, und sie muss auf den Prozess zeigen, in dem das
    Dock jetzt liegt.

    `ags request dock` und nicht ein Skript, das `pgrep -f
    nwg-dock-hyprland` fragt und den Prozess je nachdem startet oder
    abschiesst: das Dock ist ein Fenster in AGS, also ist Umschalten eine
    Sichtbarkeit und kein Prozesswechsel.
    """
    lines = _uncommented(
        _read(SRC / "templates" / "hyprland-universal-config.template"))
    binds = [line for line in lines if line.startswith("bind")]

    assert "bind = $mainMod, B, exec, ags request dock" in binds, (
        "SUPER+B erreicht das Dock nicht")


def test_the_generator_writes_nothing_into_a_waybar_directory():
    """Zweiunddreissig Routen lagen unter ~/.config/waybar, eine unter
    ~/.config/nwg-dock-hyprland.

    Eine davon stehenzulassen hiesse: eine erzeugte Datei in einem
    Verzeichnis eines Programms, das nicht mehr installiert ist. Sie
    faellt niemandem auf - der Generator meldet Erfolg, die Datei ist da,
    und gelesen wird sie nie.
    """
    lines = _uncommented(_read(SRC / "generate_config.sh"))
    offenders = [line for line in lines if BAR_DIRECTORY_PATTERN.search(line)]

    assert offenders == [], (
        "der Generator schreibt weiterhin in ein Verzeichnis der "
        f"GTK3-Leiste: {offenders}")


def test_the_bar_and_the_dock_are_astal_windows_on_gtk4():
    """Das eine Stueck, das ein Compositor braucht, und wo es steht.

    Astal.Window IST die Layer-Shell-Flaeche - libastal-4 gegen
    gtk4-layer-shell. Steht sie in BarContent() statt in Bar(), laesst
    sich der Inhalt nicht mehr ohne Wayland bauen, und
    tests/src/test_bar_headless.py hoert auf, irgendetwas zu messen -
    lautlos, denn er wuerde uebersprungen und nicht rot.
    """
    for name, content_function in (("ags-bar", "BarContent"),
                                   ("ags-dock", "DockContent")):
        source = _read(SRC / "templates" / f"{name}.template")
        body = re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)

        assert "new Astal.Window({" in body, (
            f"{name} baut kein Layer-Shell-Fenster")

        content = body.index(f"function {content_function}")
        window = body.index("new Astal.Window({")
        assert window > content, (
            f"{name}: die Layer-Shell-Flaeche steht in {content_function}(), "
            "also ist der Inhalt ohne Compositor nicht mehr baubar")
