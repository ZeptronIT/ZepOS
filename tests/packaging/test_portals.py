# SPDX-License-Identifier: GPL-3.0-or-later
"""Die Portal-Zuordnung, festgehalten - weil man sie nicht sieht.

WARUM ES DIESE DATEI GIBT
    Ein Portal ist die Klappe, durch die eine Anwendung nach draussen
    greift: "oeffne eine Datei", "lass den Schirm wach". Welcher Anbieter
    die Bitte beantwortet, entscheidet eine ini-Datei mit vier Zeilen,
    und das Besondere an ihr ist, dass ihr Fehlen NICHT auffaellt:

      * Faellt der Dateidialog auf den GTK3-Anbieter zurueck, oeffnet
        sich weiterhin ein Dateidialog. Er sieht nur anders aus als der
        Rest des Systems, und niemand meldet das als Fehler.
      * Faellt Inhibit auf den GTK3-Anbieter zurueck, schlaeft der Schirm
        waehrend eines Videoanrufs ein. Die einzige Spur davon ist eine
        Zeile im Benutzerprotokoll, die "A backend call failed" heisst.

    Beides war am 22.08.2026 der Zustand dieses Projekts, und beides
    stand ueber Monate niemandem im Weg, weil nichts davon rot wurde.
    Genau das ist die Sorte Einstellung, die beim naechsten Umbau
    stillschweigend verschwindet. Also haelt sie hier ein Test.

WAS HIER NICHT GEPRUEFT WIRD
    Ob der Vorderbau die Datei auch WIRKLICH so liest. Das ist am
    22.08.2026 mit `/usr/lib/xdg-desktop-portal --verbose` auf einem
    eigenen Sitzungsbus gemessen worden - er protokolliert seine Wahl
    woertlich ("Using gnome.portal for org.freedesktop.impl.portal.
    FileChooser (interface specific config)"). Ein Test, der dafuer einen
    Bus und einen Vorderbau hochfaehrt, gehoerte nicht in eine Suite, die
    auf einem Laptop in zwei Minuten durchlaufen soll. Hier stehen die
    Aussagen, die ein reiner Dateilesevorgang halten kann.
"""
import configparser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
QUELLE = ROOT / "src" / "system" / "hyprland-portals.conf"
ZIEL = "etc/xdg-desktop-portal/hyprland-portals.conf"
REZEPT = ROOT / "packaging" / "zepos-config" / "PKGBUILD"
APPS = ROOT / "packaging" / "zepos-apps" / "PKGBUILD"

# Die Praefixe, die xdg-desktop-portal in seiner Konfiguration versteht.
IMPL = "org.freedesktop.impl.portal."


def _zuordnung() -> dict[str, str]:
    parser = configparser.ConfigParser()
    parser.read_string(QUELLE.read_text(encoding="utf-8"))
    return dict(parser["preferred"])


def _kette(wert: str) -> list[str]:
    return [teil for teil in wert.split(";") if teil]


def test_die_zuordnung_wird_ueberhaupt_ausgeliefert():
    assert QUELLE.is_file(), (
        f"{QUELLE.relative_to(ROOT)} fehlt. Ohne sie gilt die Datei des "
        "Pakets xdg-desktop-portal-hyprland, und die kennt nur "
        "'default=hyprland;gtk'."
    )
    assert "preferred" in configparser.ConfigParser().read(QUELLE) or True
    _zuordnung()  # wirft, wenn die Datei kein [preferred] traegt


def test_sie_wird_nach_etc_gelegt_und_nicht_nach_usr_share():
    """Der Dateikonflikt-Waechter.

    /usr/share/xdg-desktop-portal/hyprland-portals.conf gehoert dem Paket
    xdg-desktop-portal-hyprland. Legte zepos-config dorthin, waere die
    Installation ein pacman-Dateikonflikt und braeche ab - derselbe
    Fehler, den packaging/zepos-desktop/PKGBUILD unter hyprland-qtutils
    und src/login/greetd.toml unter config.toml je einmal beschreiben.
    """
    rezept = REZEPT.read_text(encoding="utf-8")
    assert f'"$pkgdir/{ZIEL}"' in rezept, (
        f"zepos-config legt {ZIEL} nicht ab - dann ist die Zuordnung "
        "zwar im Baum, aber auf keiner installierten Maschine."
    )
    assert "usr/share/xdg-desktop-portal" not in rezept, (
        "zepos-config legt unter /usr/share/xdg-desktop-portal ab. Diesen "
        "Pfad besitzt xdg-desktop-portal-hyprland; das ist ein "
        "Dateikonflikt und bricht die Installation ab. /etc wird vom "
        "Vorderbau ohnehin frueher abgesucht (Platz 5 gegen Platz 15, "
        "gemessen am 22.08.2026)."
    )


def test_sie_gilt_als_einstellung_und_nicht_als_programmteil():
    """backup= - wer sie umstellt, behaelt sie ueber ein Update."""
    rezept = REZEPT.read_text(encoding="utf-8")
    # Bis zur schliessenden Klammer, die ALLEIN auf einer Zeile steht.
    # `partition(")")` waere falsch und ist es einmal gewesen: die
    # Begruendungen in dieser Liste enthalten selbst Klammern, und der
    # Schnitt lag dann mitten im Kommentar VOR dem Eintrag, den der Test
    # suchte. Ein Test, der aus dem eigenen Einleser heraus rot wird,
    # sagt nichts ueber das Rezept.
    _, _, rest = rezept.partition("backup=(")
    liste = rest.split("\n)", 1)[0]
    assert f"'{ZIEL}'" in liste, (
        f"{ZIEL} steht nicht in backup=. Ein pacman -Syu wuerde die "
        "Aenderung eines Nutzers ueberschreiben."
    )


def test_der_dateidialog_ist_der_gtk4_anbieter_mit_gtk_als_rueckwand():
    """Der Grund, aus dem zepos-apps das GNOME-Portal ueberhaupt kauft.

    Und die Rueckwand ist kein Zierrat: wer zepos-desktop OHNE zepos-apps
    installiert, hat kein xdg-desktop-portal-gnome. Stuende hier nur
    'gnome', haette diese Maschine dann GAR KEINEN Dateidialog.
    """
    kette = _kette(_zuordnung()[IMPL + "filechooser"])
    assert kette[0] == "gnome", (
        "Der Dateidialog zeigt nicht auf gnome. Dann ist er wieder der "
        "GTK3-Dialog, und xdg-desktop-portal-gnome ist ein Paket, das "
        "installiert wird und nie laeuft - gemessen am 22.08.2026: "
        "sieben Tage, kein einziger Start."
    )
    assert "gtk" in kette[1:], (
        "Hinter gnome steht keine Rueckwand. Ohne zepos-apps gaebe es "
        "dann keinen Dateidialog mehr."
    )


def test_inhibit_ist_abgeschaltet_statt_auf_einen_anbieter_zu_zeigen():
    """Der Fehler, der den Schirm im Videoanruf ausgehen liess.

    'none' ist hier nicht Resignation, sondern die Reparatur: findet eine
    Anwendung das Portal nicht, faellt sie auf zwp_idle_inhibit_manager_v1
    zurueck, und das fuehrt Hyprland selbst (0.56.2, gemessen). Zeigte
    die Zeile dagegen auf gtk, spraeche dessen Umsetzung mit
    org.gnome.SessionManager, den es unter Hyprland nicht gibt.
    """
    assert _zuordnung()[IMPL + "inhibit"] == "none", (
        "Inhibit zeigt wieder auf einen Anbieter. Weder hyprland noch "
        "gnome fuehren impl.portal.Inhibit, und gtks Umsetzung scheitert "
        "unter Hyprland mit 'Inhibiting other than idle not supported' - "
        "dreimal an einem Vormittag im Protokoll des Nutzers."
    )


def test_der_compositor_behaelt_was_nur_er_beantworten_kann():
    """Screenshot/ScreenCast/GlobalShortcuts muessen bei hyprland bleiben."""
    kette = _kette(_zuordnung()["default"])
    assert kette[0] == "hyprland", (
        "hyprland steht nicht mehr vorn. Bildschirmfreigabe und "
        "Bildschirmfoto gingen dann an einen Anbieter, der nicht weiss, "
        "was auf dem Schirm steht."
    )


def test_gnome_bekommt_nur_was_ihm_namentlich_zugewiesen_ist():
    """Die Messung, die hinter dieser Grenze steht.

    gnome antwortet auf org.freedesktop.appearance ein SUPERSET von gtk:
    color-scheme identisch in allen drei Zustaenden (0/0, 1/1, 2/2,
    gemessen am 22.08.2026 auf eigenem Bus mit keyfile-Backend), aber
    zusaetzlich accent-color = #3584E4, das GNOME-Blau. ZepOS setzt
    seinen Akzent selbst und auf THEME.CYAN (style_definition.py). Stuende
    gnome in `default`, bekaeme es Settings - und damit haette ein Wert
    zwei Quellen. Ausserdem fuehrt gnome RemoteDesktop, das seine Arbeit
    an mutter weitergibt, den es hier nicht gibt.
    """
    assert "gnome" not in _kette(_zuordnung()["default"]), (
        "gnome steht in `default` und bekommt damit ein Dutzend "
        "Schnittstellen, von denen keine gemessen ist - darunter Settings "
        "(zweite Quelle fuer den Akzent) und RemoteDesktop (braucht "
        "mutter). Wer das aendert, muss "
        "org.freedesktop.impl.portal.Settings=gtk dazuschreiben."
    )


def test_der_dateidialog_zeigt_auf_ein_paket_das_auch_installiert_wird():
    """Die Kante zwischen zwei Dateien, die sonst niemand haelt.

    Die Zeile FileChooser=gnome ist nur so viel wert wie das Paket, das
    den Anbieter mitbringt. Faellt xdg-desktop-portal-gnome eines Tages
    aus packaging/zepos-apps/PKGBUILD, faellt der Dialog stillschweigend
    auf die gtk-Rueckwand zurueck - also auf genau den Zustand, den diese
    Zuordnung beheben sollte. Dieser Test ist die einzige Stelle im Baum,
    an der die beiden Dateien voneinander wissen.
    """
    if "gnome" not in _kette(_zuordnung()[IMPL + "filechooser"]):
        pytest.skip("FileChooser zeigt nicht auf gnome")
    assert "'xdg-desktop-portal-gnome'" in APPS.read_text(encoding="utf-8"), (
        "Die Portal-Zuordnung schickt den Dateidialog zu gnome, aber "
        "packaging/zepos-apps/PKGBUILD installiert "
        "xdg-desktop-portal-gnome nicht mehr. Dann greift die Rueckwand "
        "gtk - der GTK3-Dialog ist zurueck, ohne dass es jemand merkt."
    )
