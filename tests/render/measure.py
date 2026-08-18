# SPDX-License-Identifier: GPL-3.0-or-later
"""Nachrechnen, was auf einem Bild zu sehen ist.

WARUM DAS NEBEN DEN BILDERN STEHT
    "Der Rand links sieht so breit aus wie rechts" ist keine Aussage,
    sondern ein Eindruck. Ein Bild soll ihn nicht ersetzen, sondern
    pruefbar machen: die Flaeche, die die Leiste WIRKLICH bemalt, ist die
    Menge der Bildpunkte, an denen sich das Bild mit Oberflaeche vom
    Bild mit blosser Tapete unterscheidet.

    Damit werden aus "sitzt buendig" und "gleicher Randabstand" Zahlen,
    und zwar Zahlen aus dem BILD und nicht aus der Fensterverwaltung.
    Beides zusammen ist der Punkt: hyprctl sagt, wie gross die
    Layer-Shell-Flaeche IST; dieses Modul sagt, wie viel davon bemalt
    wird. Zwischen beiden liegen Aussenrand, Rundung und Schatten - also
    genau das, wonach gefragt wurde.

WARUM EIN EIGENER PNG-LESER
    Weder Pillow noch numpy liegen in .venv, und ImageMagick nachzuladen
    hiesse, fuer eine Rechteckmessung eine Bildbibliothek zur
    Voraussetzung dieses Zweiges zu machen. zlib und struct genuegen: die
    Bilder kommen aus grim, also 8 Bit je Kanal, keine Palette, kein
    Interlacing - und genau das wird unten geprueft statt angenommen.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path


class Image:
    """Ein entpacktes PNG: Breite, Hoehe und Bildpunkte als bytes."""

    def __init__(self, width: int, height: int, channels: int,
                 pixels: bytearray) -> None:
        self.width = width
        self.height = height
        self.channels = channels
        self.pixels = pixels

    def at(self, x: int, y: int) -> tuple[int, ...]:
        start = (y * self.width + x) * self.channels
        return tuple(self.pixels[start:start + self.channels])


def read_png(path: Path) -> Image:
    """Ein PNG, entpackt - ohne fremde Bibliothek."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} ist kein PNG"

    header = None
    idat = bytearray()
    offset = 8
    while offset < len(data):
        (length,) = struct.unpack(">I", data[offset:offset + 4])
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
        offset += 12 + length

    assert header, f"{path} hat keinen IHDR"
    width, height, depth, colour, compression, filtering, interlace = header
    assert depth == 8, f"{path} hat {depth} Bit je Kanal, erwartet 8"
    assert interlace == 0, f"{path} ist interlaced"
    assert compression == 0 and filtering == 0, f"{path} ist ungewoehnlich"
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(colour)
    assert channels, f"{path} hat Farbtyp {colour}"

    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = bytearray(height * stride)
    previous = bytearray(stride)
    position = 0
    for row in range(height):
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position:position + stride])
        position += stride
        # Die fuenf Filter aus RFC 2083 §6. Ohne sie liest man Rauschen.
        if filter_type == 1:                                   # Sub
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_type == 2:                                 # Up
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_type == 3:                                 # Average
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index]
                               + ((left + previous[index]) >> 1)) & 0xFF
        elif filter_type == 4:                                 # Paeth
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                up = previous[index]
                upleft = previous[index - channels] if index >= channels else 0
                estimate = left + up - upleft
                da, db, dc = (abs(estimate - left), abs(estimate - up),
                              abs(estimate - upleft))
                nearest = left if (da <= db and da <= dc) else (
                    up if db <= dc else upleft)
                line[index] = (line[index] + nearest) & 0xFF
        elif filter_type != 0:
            raise AssertionError(f"unbekannter Zeilenfilter {filter_type}")
        out[row * stride:(row + 1) * stride] = line
        previous = line

    return Image(width, height, channels, out)


def changed_bounds(before: Image, after: Image, region: tuple[int, int, int, int],
                   threshold: int = 2) -> tuple[int, int, int, int] | None:
    """Das kleinste Rechteck, in dem sich `after` von `before` unterscheidet.

    `region` grenzt die Suche ein (x, y, Breite, Hoehe) - sonst faende ein
    Bild mit Leiste UND Dock ein Rechteck, das beide umschliesst und
    ueber keines etwas sagt.

    DIE SCHWELLE IST 2 UND NICHT 8, UND DAS IST GEMESSEN
        Mit 8 meldete diese Funktion fuer die Leiste einen linken Rand
        von 24 und einen rechten von 26 - eine Unsymmetrie, die es nicht
        gibt. Die Ursache ist keine Kante, sondern der KONTRAST: die
        rechten acht Spalten der Leiste liegen ueber einer flachen
        Stelle der Tapete, und dort hebt der Glasfilm die Farbe nur um
        vier bis fuenf Werte an statt um dreizehn. Nachgezaehlt ergibt
        sich links 24 und rechts 24.

        Eine zu hohe Schwelle erfindet also Befunde. Zwei liegt oberhalb
        der Rundungsfehler des Weichzeichners und unterhalb des
        schwaechsten echten Glasfilms.
    """
    assert (before.width, before.height) == (after.width, after.height), (
        "die beiden Bilder sind verschieden gross")
    left, top, width, height = region
    minimum_x = minimum_y = None
    maximum_x = maximum_y = None
    for y in range(top, min(top + height, after.height)):
        for x in range(left, min(left + width, after.width)):
            a = before.at(x, y)
            b = after.at(x, y)
            if max(abs(one - two) for one, two in zip(a[:3], b[:3])) <= threshold:
                continue
            if minimum_x is None or x < minimum_x:
                minimum_x = x
            if maximum_x is None or x > maximum_x:
                maximum_x = x
            if minimum_y is None or y < minimum_y:
                minimum_y = y
            if maximum_y is None or y > maximum_y:
                maximum_y = y
    if minimum_x is None:
        return None
    return (minimum_x, minimum_y,
            maximum_x - minimum_x + 1, maximum_y - minimum_y + 1)


def changed_pixels(before: Image, after: Image,
                   region: tuple[int, int, int, int],
                   threshold: int = 2) -> set[tuple[int, int]]:
    """Dieselbe Frage wie changed_bounds, aber punktweise.

    WARUM EIN RECHTECK DAFUER NICHT REICHT, UND DAS IST GEMESSEN
        Die Frage, um derentwillen diese Funktion am 13.08.2026
        entstanden ist, lautet: bemalt der Zeigergrund eines Moduls
        Punkte, an denen die PLATTE nichts malt? Die Platte hat runde
        Ecken (STYLE_RADIUS_PANEL), der Grund eines Moduls ist ein
        Rechteck - der Ueberstand liegt also genau dort, wo sich die
        beiden UMRISSE unterscheiden, und nicht dort, wo sich ihre
        Rechtecke unterscheiden.

        Nachgemessen ohne die Beschneidung in ags-bar.template
        (1920x1080, Vorgabegroesse, Zeiger auf dem Zahnrad): 60 Punkte
        ausserhalb, verteilt auf die Zeilen y=27..37 und y=70..80, bis
        zu 8 px weit. Ihr gemeinsames Rechteck ist 8x54 - eine Zahl, aus
        der niemand ablesen kann, dass es um zwei Ecken geht.

    Die Schwelle ist dieselbe 2 wie oben, aus demselben Grund.
    """
    assert (before.width, before.height) == (after.width, after.height), (
        "die beiden Bilder sind verschieden gross")
    left, top, width, height = region
    found: set[tuple[int, int]] = set()
    for y in range(max(top, 0), min(top + height, after.height)):
        for x in range(max(left, 0), min(left + width, after.width)):
            a = before.at(x, y)
            b = after.at(x, y)
            if max(abs(one - two) for one, two in zip(a[:3], b[:3])) > threshold:
                found.add((x, y))
    return found


def bounds_of(points: set[tuple[int, int]]) -> tuple[int, int, int, int] | None:
    """Das Rechteck um eine Punktmenge - fuer die Fehlermeldung."""
    if not points:
        return None
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


def glass_probe(before: Image, after: Image,
                region: tuple[int, int, int, int]) -> str:
    """Wie viel Tapete durch eine Flaeche noch zu sehen ist.

    DIE FRAGE, DIE EIN BILD ALLEIN NICHT BEANTWORTET
        Eine halbdurchsichtige Flaeche ueber einer EINFARBIGEN Stelle der
        Tapete sieht aus wie eine undurchsichtige. Ob Glas Glas ist,
        entscheidet sich dort, wo die Tapete Struktur hat: eine Linie,
        ein Punkt, eine Kante. Also wird genau das gezaehlt - wie viele
        Bildpunkte unter der Flaeche in der Tapete auffaellig sind, und
        wie viele davon es unter der Flaeche noch sind.

        UND ES SIND ZWEI VERSCHIEDENE URSACHEN, die dasselbe Ergebnis
        haben koennen: eine deckende Flaeche loescht die Struktur, und
        ein Weichzeichner tut es auch. Die Zeile unten trennt sie nicht -
        sie sagt, WIE VIEL durchkommt. Was davon Deckkraft und was
        Unschaerfe ist, steht in bar.css und in der layerrule.

    ZWEI FALLEN, BEIDE BEIM ERSTEN ANLAUF HINEINGETRETEN
        * "noch sichtbar" heisst: der Punkt zeigt SEINE EIGENE FARBE
          noch. Die erste Fassung fragte statt dessen, ob er sich vom
          flachen Grund unterscheidet - und das tut ein Symbol des Docks
          auch. Sie meldete daraufhin fuer das Dock einmal 0 % und
          einmal 67 %, je nachdem, wie viele Symbole zufaellig ueber
          einer Linie der Tapete lagen.
        * Der Farbauftrag wird ueber den HAEUFIGSTEN Wert gebildet und
          weder ueber den Mittelwert noch ueber den Median. Beide messen
          Beschriftungen und Symbole mit: der Mittelwert meldete fuer das
          Dock +49, der Median +10, und der Glasfilm betraegt +0.

          Der Grund, aus dem der haeufigste Wert es trifft: die sechs
          Symbole des Docks bedecken zwar mehr Flaeche als der Grund
          zwischen ihnen, aber sie haben VIELE verschiedene Farben,
          waehrend der Grund genau eine hat. Der groesste gleichfarbige
          Haufen ist der Hintergrund, auch wenn er nicht die Mehrheit
          hat.
    """
    left, top, width, height = region
    base_x, base_y = left + width // 2, top + height // 2
    ground = before.at(base_x, base_y)[:3]

    structured = kept = 0
    lift = []
    for y in range(top, min(top + height, after.height)):
        for x in range(left, min(left + width, after.width)):
            plain = before.at(x, y)[:3]
            dressed = after.at(x, y)[:3]
            if max(abs(one - two) for one, two in zip(plain, ground)) > 25:
                structured += 1
                if max(abs(one - two)
                       for one, two in zip(dressed, plain)) <= 25:
                    kept += 1
            else:
                lift.append(sum(dressed) / 3 - sum(plain) / 3)

    tally: dict[int, int] = {}
    for value in lift:
        step = int(round(value))
        tally[step] = tally.get(step, 0) + 1
    common = max(tally, key=lambda step: tally[step]) if tally else 0
    share = (100.0 * kept / structured) if structured else 0.0
    return (f"Tapete darunter: {structured} Punkte mit Struktur, davon "
            f"{kept} unveraendert ({share:.0f} %); flacher Grund "
            f"{common:+d} Helligkeit")


def describe(before: Path, after: Path,
             regions: dict[str, tuple[int, int, int, int]]) -> list[str]:
    """Je Bereich eine Zeile: was dort bemalt wurde, und wie weit vom Rand."""
    plain = read_png(before)
    dressed = read_png(after)
    lines = []
    for name, region in regions.items():
        bounds = changed_bounds(plain, dressed, region)
        if bounds is None:
            lines.append(f"    {name:12s} nichts bemalt")
            continue
        x, y, width, height = bounds
        lines.append(
            f"    {name:12s} bemalt x={x} y={y} b={width} h={height}"
            f"   Rand links={x} rechts={dressed.width - (x + width)}"
            f" oben={y} unten={dressed.height - (y + height)}")
    return lines
