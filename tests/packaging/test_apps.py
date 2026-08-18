# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Anwendungsauswahl von ZepOS, gegen die Regeln, die sie erzeugt haben.

WARUM DIESE DATEI EXISTIERT
    Weil die Auswahl in packaging/zepos-apps/PKGBUILD eine ENTSCHEIDUNG
    ist und keine Ableitung. Nichts im Baum erzwingt sie, nichts faellt
    um, wenn jemand den Browser tauscht oder nautilus
    herausnimmt - die Installation gelingt weiterhin, das Medium baut
    weiterhin, und der Schaden zeigt sich erst auf dem Schreibtisch
    eines Nutzers, dem eine Taste nichts mehr tut oder dessen
    Dateimanager grau ist.

    Der Ausloeser ist gemessen. Der Nutzer am 11.08.2026: "ausserdem
    wurden alle install.sh pakete die dort aufgelistet wurden nicht
    installiert wie firefox browser usw." Bis dahin nannte
    zepos-desktop 37 Abhaengigkeiten, davon keine einzige Anwendung, und
    vier Bedienelemente zeigten auf Programme, die kein Paket
    installiert - SUPER+E auf thunars D-Bus-Namen, SUPER+T auf einen
    Symlink zu sublime-text-4 aus dem AUR, SUPER+SHIFT+T auf ferdium,
    der Drucker-Knopf auf ein `lpstat`, das es nicht gab.

WAS SIE MISST, UND WOGEGEN
    Vier Zusicherungen, jede gegen eine andere Art, die Auswahl still zu
    verlieren:

      * sie enthaelt, was sie enthalten soll - als GENAUE Menge, nicht
        als Teilmenge, damit auch ein zusaetzlicher Name auffaellt;
      * kein Name aus dem AUR ist hineingerutscht (Spec §4.3);
      * kein Programm, das ZepOS abgewaehlt hat, steht noch in einer
        Bindung oder einer Fensterregel;
      * jede Farbe, die fremde GTK4-Fenster bekommen, IST eine Farbe aus
        src/brand.py - nicht bloss "es steht ein Platzhalter da".

    Gemessen wird gegen den Code OHNE Kommentare und zeilengenau. Der
    Grund ist die Falle, in die diese Aenderung selbst gelaufen ist:
    jede Datei in diesem Baum ERKLAERT, was sie nicht tut, und eine
    Pruefung der Form `"firefox" in text` wird von dem Absatz wahr, der
    begruendet, warum firefox nicht mitkommt.
"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "packaging"
SRC = ROOT / "src"
INSTALLER = ROOT / "installer"


def _read(path: Path) -> str:
    assert path.is_file(), f"{path} fehlt"
    return path.read_text(encoding="utf-8")


def _code(text: str) -> str:
    """Der Text ohne die Zeilen, die nur Kommentar sind."""
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))


def _depends(recipe: str) -> list[str]:
    """Die depends-Liste eines Rezepts, ohne Kommentarzeilen.

    Als Liste und nicht als Menge: ein Name, der zweimal dastuende, ist
    ein Fehler, den eine Menge verschluckt.
    """
    text = _read(PACKAGING / recipe / "PKGBUILD")
    body = re.search(r"^depends=\((.*?)^\)", text, re.S | re.M)
    assert body, f"{recipe} hat keine depends-Liste"
    return re.findall(r"'([^']+)'", _code(body.group(1)))


def _uncommented_lines(path: Path, marker: str = "#") -> list[str]:
    return [line.strip() for line in _read(path).splitlines()
            if not line.lstrip().startswith(marker)]


# --------------------------------------------------------------------
# Die Auswahl selbst
# --------------------------------------------------------------------

# Was ZepOS ausliefert, und wofuer. Der zweite Eintrag ist keine
# Verzierung: er ist die Aufgabe, und die Regel von zepos-apps lautet
# EINE Anwendung je Aufgabe. Zwei Namen unter derselben Aufgabe waeren
# der Bruch, den diese Tabelle sichtbar macht.
SHIPPED = {
    "firefox": "der Browser",
    "nautilus": "der Dateimanager",
    "xdg-desktop-portal-gnome": "der Dateiauswahldialog",
    "file-roller": "Archive",
    "loupe": "Bilder",
    "papers": "Dokumente",
    "celluloid": "Medien",
    "gnome-text-editor": "Text",
    "baobab": "Datentraeger",
    # Am 13.08.2026 dazugekommen: "kann man claude code auch bei ZepOS
    # immer direkt vor installieren". Ein eigenes Rezept, weil das
    # npm-Paket @anthropic-ai/claude-code die Binaerdatei nicht enthaelt
    # (24606 Bytes, ein Nachlader) - geholt wird deshalb gleich
    # @anthropic-ai/claude-code-linux-x64, mit fester Version und
    # Pruefsumme, wie aylurs-gtk-shell es mit gnim vormacht.
    "zepos-claude-code": "der Assistent",
    # Am 13.08.2026 dazugekommen: "es fehlt ein calculator". GTK4 und
    # libadwaita - `pacman -Si gnome-calculator` nennt gtk4, libadwaita
    # und gtksourceview5 und kein gtk3 -, also ohne die Ausnahme, die
    # firefox braucht. Die uebrigen Rechner der offiziellen Quellen sind
    # GTK3 (galculator, qalculate-gtk) oder zoegen halb KDE nach (kcalc).
    "gnome-calculator": "der Rechner",
    # Am 12.08.2026 dazugekommen, nachdem der Nutzer ihn zweimal
    # vermisst hat. Er stand schon in ags-bar.template als Ziel des
    # Hardware-Moduls und in keinem Rezept - eine Taste ohne Programm,
    # nur an einem Klick statt an einer Taste.
    "btop": "die Systemueberwachung",
    # Am 17.08.2026 dazugekommen: "es fehlt auch noch ein terminal icon".
    #
    # kitty WAR immer installiert - als Abhaengigkeit von zepos-desktop,
    # "the terminal every terminal bind opens". Im Dock stand es nie,
    # denn die angeheftete Liste liest src/apps.py aus dem depends-Block
    # von zepos-apps und aus keinem anderen Rezept. Es dort ein zweites
    # Mal zu nennen ist die eine Zeile, die darueber entscheidet; pacman
    # stoert eine Abhaengigkeit nicht, die zwei Pakete zugleich
    # erklaeren.
    #
    # KEIN BRUCH DER REGEL "eine Anwendung je Aufgabe": das Terminal ist
    # eine eigene Aufgabe, und btop darueber ist die Systemueberwachung,
    # die IN einem Terminal zeichnet - deshalb stehen die beiden
    # nebeneinander. ZepOS liefert genau ein Terminal aus.
    "kitty": "das Terminal",
    "cups": "der Drucker",
}

# Namen aus dem AUR, die der Ursprung installierte und die Spec §4.3
# ausschliesst. Gemessen am angehefteten ALA-Schnappschuss 2026/08/04:
# `tar tzf extra.db` zaehlt 14860 Namen und keinen davon.
AUR_NAMES = (
    "brave-bin", "microsoft-edge-stable-bin", "sublime-text-4",
    "ferdium-bin", "onlyoffice-bin", "onedrive-abraunegg",
    "intune-portal-bin", "microsoft-identity-broker-bin", "yay",
    "nwg-shell-config", "overskride",
)

# Programme mit einer Oberflaeche, die NICHT auf GTK4 steht, und die
# ZepOS deshalb nicht ausliefert. Jeder Name hier ist am angehefteten
# Schnappschuss gemessen worden - siehe packaging/zepos-apps/PKGBUILD.
NOT_ON_GTK4 = (
    "firefox", "chromium", "thunar", "dolphin", "ark", "gwenview",
    "eog", "xarchiver", "gnome-disk-utility", "gparted",
    "system-config-printer", "evince", "vlc", "virt-manager",
    "gnome-boxes",
)


def test_the_selection_is_exactly_what_zepos_decided_to_ship():
    """Als genaue Menge und nicht als Teilmenge.

    "enthaelt nautilus" bliebe wahr, wenn jemand thunar danebenstellte -
    und zwei Dateimanager sind keine Auswahl, sondern der Zustand, aus
    dem diese Auswahl entstanden ist.
    """
    listed = _depends("zepos-apps")

    assert len(listed) == len(set(listed)), (
        f"zepos-apps nennt einen Namen doppelt: {sorted(listed)}")
    assert set(listed) == set(SHIPPED), (
        "zepos-apps liefert nicht mehr die entschiedene Auswahl aus.\n"
        f"  fehlt:      {sorted(set(SHIPPED) - set(listed))}\n"
        f"  zusaetzlich: {sorted(set(listed) - set(SHIPPED))}")


def test_the_desktop_pulls_the_selection_in():
    """Ohne diese Kante ist eine Installation moeglich, in der SUPER+E,
    SUPER+T, SUPER+SHIFT+B und die Druckerzeile der Kontrollzentrale auf
    Programme zeigen, die nicht da sind - der Fehler, den Spec §7.4 fuer
    den schlimmsten haelt, weil ihn nichts meldet."""
    assert "zepos-apps" in _depends("zepos-desktop"), (
        "zepos-desktop zieht die Anwendungsauswahl nicht herein")


def test_no_recipe_carries_a_name_from_the_aur():
    """Spec §4.3. Ein AUR-Name in einem Rezept ist ein Bau, der auf der
    Maschine des Entwicklers gelingt und nirgends sonst - makepkg
    --syncdeps findet ihn dort, weil dort ein AUR-Helfer lief."""
    offenders = []
    for recipe in sorted(PACKAGING.glob("*/PKGBUILD")):
        code = _code(_read(recipe))
        for name in AUR_NAMES:
            # Zeilengenau und wortgenau: "yay" steckt sonst in jedem
            # Wort, das die drei Buchstaben enthaelt.
            if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", code):
                offenders.append(f"packaging/{recipe.parent.name}/PKGBUILD -> {name}")
    assert offenders == [], "Namen aus dem AUR in den Rezepten: " + "; ".join(offenders)


# Fremde Anwendungen, die GTK3 tragen und trotzdem ausgeliefert werden -
# jede mit dem Grund, aus dem sie hier stehen darf. Absichtlich kurz und
# absichtlich ausgeschrieben: das ist die Ausnahmeliste zur GTK4-Regel,
# und eine Ausnahme, die niemand hinschreiben muss, ist keine Ausnahme
# mehr, sondern das neue Normal.
GTK3_ERLAUBT = {
    "firefox":
        "Vom Nutzer zweimal beim Namen genannt. Er hat die Regel am "
        "11.08.2026 dafuer praezisiert: 'was externe dienste und pakete "
        "angeht koennen wir das nicht verhindern daher darf dort gtk3 "
        "verwendet werden'. Preis: sein Fenster nimmt die 45 "
        "libadwaita-Farben nicht an und sieht anders aus als der Rest.",
}


def test_the_selection_ships_no_unlisted_gtk3_surface():
    """Die Entscheidung vom 11.08.2026, in der Fassung, die der Nutzer am
    selben Tag praezisiert hat.

    ZUERST STAND HIER "GAR KEIN GTK3"
        Diese Datei lieferte deshalb epiphany statt firefox aus. Der
        Nutzer hat daraufhin klargestellt, dass die Regel den
        Oberflaechen gilt, die ZepOS SELBST baut - Installer, Anmeldung,
        Leiste, Dock, Auswahlfenster, Abmeldemaske - und nicht fremden
        Anwendungen, die es nur in GTK3 gibt.

    WARUM DIE ZUSICHERUNG TROTZDEM BLEIBT
        Eine GTK3-Anwendung liest ~/.config/gtk-4.0/gtk.css nicht. Sie
        steht grau vor einem petrolfarbenen Schreibtisch, dauerhaft, und
        keine Einstellung zieht das nachtraeglich gerade. Das ist ein
        Preis, kein Nichts - er darf bezahlt werden, aber jedes Mal
        bewusst. Der Test prueft deshalb nicht mehr auf Null, sondern
        darauf, dass jede GTK3-Flaeche in GTK3_ERLAUBT steht und dort
        eine Begruendung traegt.
    """
    listed = set(_depends("zepos-apps")) | set(_depends("zepos-desktop"))
    offenders = sorted((listed & set(NOT_ON_GTK4)) - set(GTK3_ERLAUBT))

    assert offenders == [], (
        f"GTK3-Anwendungen in der Auslieferung ohne Eintrag in "
        f"GTK3_ERLAUBT: {offenders}. Entweder einen GTK4-Ersatz nehmen "
        f"oder die Ausnahme mit Begruendung hinschreiben.")


def test_every_listed_exception_is_really_shipped_and_really_gtk3():
    """Die Gegenrichtung. Eine Ausnahme fuer etwas, das gar nicht mehr
    ausgeliefert wird oder inzwischen GTK4 traegt, ist eine Erlaubnis,
    die niemand braucht - und beim naechsten Lesen ein Freibrief, den
    jemand fuer gueltig haelt."""
    listed = set(_depends("zepos-apps")) | set(_depends("zepos-desktop"))

    for name, grund in GTK3_ERLAUBT.items():
        assert name in listed, (
            f"{name} steht in GTK3_ERLAUBT, wird aber nicht ausgeliefert")
        assert name in NOT_ON_GTK4, (
            f"{name} steht in GTK3_ERLAUBT, ist aber nicht als GTK3 "
            f"gemessen - die Ausnahme ist gegenstandslos")
        assert len(grund) > 40, f"{name} traegt keine Begruendung"


# --------------------------------------------------------------------
# Die Bedienelemente, die auf die Auswahl zeigen
# --------------------------------------------------------------------

UNIVERSAL = SRC / "templates" / "hyprland-universal-config.template"

# Was der Ursprung startete und ZepOS nicht ausliefert. Ein Name hier in
# einer Bindung ist eine Taste, die nichts tut.
DROPPED_FROM_THE_BINDS = ("thunar", "Thunar", "ferdium", "ncspot",
                          "sublime", "smerge", "chromium")


def test_every_application_bind_points_at_something_zepos_installs():
    """Die Zusicherung, die es am 11.08.2026 noch nicht gab.

    Drei der fuenf Anwendungsbindungen zeigten auf Programme, die kein
    Paket dieses Projekts installiert, und keine davon hat sich je
    gemeldet: Hyprland fuehrt `exec` aus, die Shell findet nichts, und
    das war es.
    """
    binds = [line for line in _uncommented_lines(UNIVERSAL)
             if line.startswith("bind")]
    assert binds, "die Vorlage enthaelt keine Bindungen mehr"

    shipped = set(_depends("zepos-apps")) | set(_depends("zepos-desktop"))
    for key, program in (("$mainMod, E", "nautilus"),
                         ("$mainMod, T", "gnome-text-editor"),
                         ("$mainMod SHIFT, B", "firefox")):
        expected = f"bind = {key}, exec, {program}"
        assert any(line.startswith(expected) for line in binds), (
            f"{key} ruft nicht {program} auf")
        assert program in shipped, (
            f"{key} ruft {program} auf, und kein Paket installiert es")


def test_no_bind_and_no_windowrule_names_a_program_zepos_dropped():
    """Die Gegenrichtung, und sie ist die, die stillschweigend
    zurueckfaellt: eine Fensterregel auf ein Fenster, das es nicht gibt,
    ist kein Fehler, sondern eine Zeile, die nie greift."""
    lines = [line for line in _uncommented_lines(UNIVERSAL)
             if line.startswith(("bind", "windowrule", "exec-once"))]
    offenders = [f"{name}: {line}"
                 for line in lines for name in DROPPED_FROM_THE_BINDS
                 if re.search(rf"(?<![\w-]){name}(?![\w-])", line)]
    assert offenders == [], (
        "die Sitzung nennt weiterhin abgewaehlte Programme: " + "; ".join(offenders))


def test_the_disk_widget_opens_the_file_manager_zepos_ships():
    """Der Knopf hiess "Dateien" und rief thunar. Ein Knopf in einem
    Widget, das ZepOS selbst zeichnet, auf ein Programm, das ZepOS nicht
    installiert - dieselbe Luecke wie bei den Bindungen, nur eine Ebene
    tiefer, wo noch weniger hinsieht."""
    disk = _read(SRC / "templates" / "ags-disk.template")
    body = re.sub(r"^\s*//.*$", "", disk, flags=re.MULTILINE)
    assert 'launchApp("nautilus / &")' in body, (
        "der Dateien-Knopf des Datentraeger-Widgets oeffnet nicht nautilus")
    assert "gnome-disks" not in body, (
        "das Widget ruft weiterhin gnome-disks, das GTK3 ist und nicht "
        "installiert wird")


# --------------------------------------------------------------------
# Die Marke auf den fremden Fenstern
# --------------------------------------------------------------------

GTK4_COLOURS = SRC / "templates" / "gtk4-colors-config.template"

# Die benannten Farben von libadwaita, die ZepOS setzt. Der Satz ist
# vollstaendig gegenueber dem, was eine Anwendung aus zepos-apps auf den
# Schirm bringt: Flaechen, Akzent, die drei Zustaende, die Schatten und
# die zweite Textstufe. Was libadwaita darueber hinaus kennt und hier
# fehlt, faellt auf seinen eigenen Wert zurueck - deshalb ist dies eine
# genaue Menge und keine Untergrenze.
LIBADWAITA_COLOURS = {
    "window_bg_color", "window_fg_color",
    "view_bg_color", "view_fg_color",
    "headerbar_bg_color", "headerbar_fg_color", "headerbar_border_color",
    "headerbar_backdrop_color", "headerbar_shade_color",
    "sidebar_bg_color", "sidebar_fg_color", "sidebar_backdrop_color",
    "sidebar_border_color", "sidebar_shade_color",
    "secondary_sidebar_bg_color", "secondary_sidebar_fg_color",
    "secondary_sidebar_border_color", "secondary_sidebar_shade_color",
    "card_bg_color", "card_fg_color", "card_shade_color",
    "dialog_bg_color", "dialog_fg_color",
    "popover_bg_color", "popover_fg_color",
    "thumbnail_bg_color", "thumbnail_fg_color",
    "accent_color", "accent_bg_color", "accent_fg_color",
    "success_color", "success_bg_color", "success_fg_color",
    "warning_color", "warning_bg_color", "warning_fg_color",
    "error_color", "error_bg_color", "error_fg_color",
    "destructive_color", "destructive_bg_color", "destructive_fg_color",
    "shade_color", "scrollbar_outline_color", "dimmed_color",
}


@pytest.fixture
def brand():
    """src/brand.py, so importiert, wie der Generator es importiert.

    Dieselbe Form wie in tests/src/test_gtk4_only.py und aus demselben
    Grund: src/ hat kein __init__.py.
    """
    spec = importlib.util.spec_from_file_location(
        "zepos_brand_apps_probe", SRC / "brand.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_foreign_windows_are_dressed_from_the_brand_and_nowhere_else(brand):
    """Der Mechanismus, ohne den die ganze Auswahl nichts nuetzt.

    Neun Anwendungen, die dieses Projekt nicht geschrieben hat, erfahren
    die Farben von ZepOS aus genau einer Datei. Steht dort ein Literal,
    dann ist es eine Farbe, die brand.py nicht kennt und die beim
    naechsten Umbau der Marke stehenbleibt - derselbe Fehler, an dem der
    Ursprung mit drei Kopien von Catppuccin gescheitert ist.
    """
    text = _read(GTK4_COLOURS)
    body = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    literals = re.findall(r"#[0-9A-Fa-f]{3,8}\b", body)
    assert literals == [], f"Farbliterale in der GTK4-Vorlage: {literals}"

    # Und die Gegenrichtung, denn "keine Literale" ist auch wahr fuer
    # eine leere Datei.
    #
    # ALS GENAUE MENGE, UND DAS IST GEMESSEN NACHGEBESSERT
    #     Die erste Fassung zaehlte neun Farben auf, die dastehen
    #     mussten. Die Mutationspruefung hat sie damit ueberlebt: das
    #     Loeschen von dimmed_color - der zweiten Textstufe, also jeder
    #     Einheit und jedem Datum in jedem dieser Fenster - liess sie
    #     gruen. Eine Aufzaehlung der wichtigsten Farben prueft die
    #     wichtigsten Farben und nichts sonst; libadwaitas Zusage ist
    #     aber der ganze Satz, und eine Farbe, die hier fehlt, faellt auf
    #     libadwaitas eigenen Wert zurueck - ein Grau, das niemand
    #     bestellt hat, mitten auf der Marke.
    defined = re.findall(r"^@define-color ([a-z_0-9]+) ", body, re.M)
    assert len(defined) == len(set(defined)), (
        f"eine Farbe ist doppelt gesetzt: {sorted(defined)}")
    assert set(defined) == LIBADWAITA_COLOURS, (
        "die Marke deckt nicht mehr denselben Satz benannter Farben ab.\n"
        f"  fehlt:       {sorted(LIBADWAITA_COLOURS - set(defined))}\n"
        f"  zusaetzlich: {sorted(set(defined) - LIBADWAITA_COLOURS)}")

    # Und jede einzelne muss aus dem Stil-SSOT kommen. Ohne das waere
    # `@define-color accent_color @window_bg_color` - ein Verweis auf
    # eine andere benannte Farbe - eine gueltige Zeile, die die
    # Mengengleichheit oben erfuellt und den Akzent verschwinden laesst.
    for colour in sorted(LIBADWAITA_COLOURS):
        assert re.search(rf"^@define-color {colour} \{{\{{STYLE_GTK4_\w+\}}\}};$",
                         body, re.M), (
            f"{colour} bekommt keinen Wert aus dem Stil-SSOT")


def test_every_colour_the_foreign_windows_get_is_a_colour_of_the_brand(brand):
    """Geprueft wird, dass jeder Wert eine Farbe der Marke IST - nicht
    bloss, dass ein Platzhalter dasteht. Ein STYLE_GTK4_*, das auf ein
    frei erfundenes Grau zeigt, erfuellt die Zusicherung darueber und
    faerbt die Fenster trotzdem falsch."""
    spec = importlib.util.spec_from_file_location(
        "zepos_style_apps_probe", SRC / "style_definition.py")
    style = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(SRC))
    try:
        spec.loader.exec_module(style)
    finally:
        sys.path.remove(str(SRC))

    palette = {value for name, value in vars(brand).items()
               if name.isupper() and isinstance(value, str)
               and re.fullmatch(r"#[0-9A-Fa-f]{6}", value)}
    palette |= set(brand.COLORS.values())

    used = {name: value for name, value in style._FIXED_STYLE_VARIABLES.items()
            if name.startswith("STYLE_GTK4_")}
    assert len(used) >= 20, (
        f"nur {len(used)} GTK4-Farben im Stil-SSOT - die Pruefung misst nichts")

    outside = {name: value for name, value in used.items() if value not in palette}
    assert outside == {}, f"Farben ausserhalb der Marke: {outside}"


def test_the_session_writes_the_gtk4_colours_before_it_starts():
    """GTK 4 liest die Datei EINMAL, beim Start jeder Anwendung. Eine
    Farbe, die der Nutzer geaendert hat, erreicht die Anwendungen also
    erst mit der naechsten Anmeldung - und genau dort muss die Datei neu
    geschrieben werden, sonst nie."""
    start = _uncommented_lines(
        SRC / "templates" / "start-hyprland-config.template")
    assert "./generate_config.sh -gtk4-colors-config" in start, (
        "die Marke fuer fremde GTK4-Fenster wird beim Sitzungsstart nicht "
        "erzeugt")


# --------------------------------------------------------------------
# Was der Installer zusaetzlich anbietet
# --------------------------------------------------------------------

def test_every_optional_bundle_the_installer_offers_can_be_installed():
    """Ein Haken, hinter dem kein Paket steht, ist eine Installation, die
    mitten im pacstrap mit "target not found" abbricht - nachdem die
    Platte geloescht ist."""
    translate = _read(INSTALLER / "core" / "translate.py")
    body = re.search(r"OPTIONAL_PACKAGES[^=]*=\s*\((.*?)\n\)", translate, re.S)
    assert body, "installer/core/translate.py hat keine OPTIONAL_PACKAGES"
    pairs = re.findall(r'\("(\w+)",\s*"([\w-]+)"\)', _code(body.group(1)))
    assert len(pairs) == 2, f"erwartet zwei Zusatzpakete, gefunden: {pairs}"

    known = {"install_office", "install_devel"}
    for field, package in pairs:
        assert field in known, f"{field} ist kein bekanntes Feld von ZeposOptions"
        if package.startswith("zepos-"):
            assert (PACKAGING / package / "PKGBUILD").is_file(), (
                f"der Installer bietet {package} an und es gibt kein Rezept dafuer")

    # HIER STAND EIN DRITTER: ("install_firefox", "firefox").
    #
    # Er war der Ausweg, solange diese Auswahl epiphany auslieferte und
    # firefox fuer unvereinbar mit der GTK4-Regel hielt. Der Nutzer hat
    # die Regel am 11.08.2026 praezisiert - sie gilt den Oberflaechen,
    # die ZepOS selbst baut, nicht fremden Anwendungen - und seither ist
    # firefox harte Abhaengigkeit von zepos-apps. Ein Haken fuer etwas,
    # das ohnehin mitkommt, waere ein Bedienelement ohne Wirkung.
    assert "install_firefox" not in {field for field, _ in pairs}, (
        "firefox steht wieder als Haken im Installer, obwohl "
        "zepos-apps ihn hart mitbringt - der Haken taete nichts")


def test_the_optional_bundles_are_built_before_the_desktop_that_may_need_them():
    """packaging/build.sh baut in Reihenfolge, und ein Metapaket wird
    ueber `makepkg --syncdeps` aufgeloest - was der Beweis dafuer ist,
    dass jeder Name darin in irgendeiner Ablage existiert."""
    build = _read(PACKAGING / "build.sh")
    body = re.search(r"readonly PACKAGES=\((.*?)\n\)", build, re.S)
    assert body, "packaging/build.sh hat keine PACKAGES-Liste"
    order = [line.strip() for line in body.group(1).splitlines() if line.strip()]

    for package in ("zepos-apps", "zepos-apps-office", "zepos-apps-devel"):
        assert package in order, f"packaging/build.sh baut {package} nicht"
    assert order.index("zepos-apps") < order.index("zepos-desktop"), (
        "zepos-apps wird nach zepos-desktop gebaut, das davon abhaengt")


def test_the_ticked_extras_reach_the_package_list_archinstall_gets():
    """Die Zusicherung, die zwischen allen anderen durchgefallen waere.

    OPTIONAL_PACKAGES kann vollstaendig und richtig sein, die Haken
    koennen auf der Seite stehen, das Modell kann sie tragen - und wenn
    `"packages"` in to_archinstall_config() wieder auf die einelementige
    Liste zurueckfaellt, ist alles davon wirkungslos. Nichts wuerde
    scheitern: die Installation gelaenge, nur ohne das, was der Nutzer
    angekreuzt hat. Genau die Form von Fehler, aus der dieses
    Teilprojekt entstanden ist.
    """
    from installer.core.model import (DiskChoice, InstallConfig, UserAccount,
                                      ZeposOptions)
    from installer.core.source import PackageSource
    from installer.core.translate import to_archinstall_config

    def _config(**extras):
        return InstallConfig(
            language="de", keymap="de-latin1", timezone="Europe/Berlin",
            locale="de_DE", hostname="zepos",
            disk=DiskChoice(device="/dev/vda", wipe=True, filesystem="ext4",
                            size_bytes=64 * 1024 ** 3),
            users=[UserAccount(username="lars", password="langgenug", sudo=True)],
            zepos=ZeposOptions(**extras),
        )

    plain = to_archinstall_config(_config(), PackageSource.OFFLINE)["packages"]
    assert plain == ["zepos-desktop"], (
        f"eine Installation ohne Haken bekommt nicht nur das Metapaket: {plain}")

    everything = to_archinstall_config(
        _config(install_office=True, install_devel=True),
        PackageSource.OFFLINE)["packages"]
    assert everything == ["zepos-desktop", "zepos-apps-office",
                          "zepos-apps-devel"], (
        f"die angehakten Zusatzpakete erreichen archinstall nicht: {everything}")

    # Einzeln, damit nicht drei Haken zusammen richtig sein koennen und
    # jeder fuer sich falsch.
    for field, package in (("install_office", "zepos-apps-office"),
                           ("install_devel", "zepos-apps-devel")):
        one = to_archinstall_config(_config(**{field: True}),
                                    PackageSource.OFFLINE)["packages"]
        assert one == ["zepos-desktop", package], (
            f"{field} allein ergibt {one}")


def test_a_default_installation_asks_for_none_of_the_extras():
    """Die Vorgabe IST die Aussage. Waere einer der drei an, wuerde ZepOS
    ein Buero oder einen zweiten Browser ausliefern, ohne dass jemand
    danach gefragt hat - und die Begruendung in zepos-apps, dass eine
    Distribution auswaehlt, waere eine Behauptung."""
    # Als Paket importiert und nicht ueber den Dateipfad: model.py
    # schreibt `from .i18n import _`, und ein Modul, das ueber
    # spec_from_file_location geladen wird, hat kein Paket, in dem der
    # Punkt etwas bedeutet. Die erste Fassung dieser Pruefung fing den
    # ImportError mit pytest.skip() ab und mass damit nichts - ein
    # uebersprungener Test ist ein gruener Balken ohne Aussage.
    # pyproject.toml setzt pythonpath = ["."], also ist der Import hier
    # derselbe wie in tests/installer/test_translate.py.
    from installer.core.model import ZeposOptions

    options = ZeposOptions()
    assert options.install_office is False
    assert options.install_devel is False
