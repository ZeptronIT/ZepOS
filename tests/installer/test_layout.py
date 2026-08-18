# SPDX-License-Identifier: GPL-3.0-or-later
"""Die geplante Einteilung einer Platte.

Jede Pruefung in installer/core/layout.py hat ein Gegenstueck in
archinstall 4.4-1 oder im Bootvorgang, und der Unterschied ist der
Zeitpunkt: archinstalls eigene laufen, nachdem der Assistent zugemacht
hat und die Installation angefangen hat zu loeschen. Was hier gemessen
wird, ist, dass die Einteilung vorher abgelehnt wird - auf der Seite, auf
der sie noch jemand aendern kann.

Die Zahlen in diesem Modul sind nicht ausgedacht. Sie kommen aus
lib/models/device.py der Fassung aus dem angehefteten ALA-Schnappschuss
2026/08/04, und die Stellen sind jeweils genannt.
"""
from __future__ import annotations

import pytest

from installer.core.i18n import activate
from installer.core.layout import (
    ALIGNMENT_MIB, ESP_FILESYSTEM, ESP_FLAGS, ESP_MOUNTPOINT, GPT_TAIL_MIB,
    MIN_DISK_MIB, MIN_ESP_MIB, MIN_ROOT_MIB, PlannedPartition, allocated_mib,
    disk_mib, first_fit, free_mib, free_regions, human_mib, largest_free_mib,
    last_usable_mib, layout_errors, parse_size_mib, suggested_layout,
)

GIB = 1024 ** 3
FORTY_GIB = 40 * GIB


@pytest.fixture(autouse=True)
def _reset_catalogue():
    """layout_errors() geht durch _(). Bliebe ein deutscher Katalog aktiv,
    laesen die Tests anderer Module ihre englischen msgids nicht mehr -
    dieselbe Vorkehrung wie in test_gui.py und test_tui.py."""
    yield
    activate("en")


def _esp(start: int = ALIGNMENT_MIB, size: int = 512) -> PlannedPartition:
    return PlannedPartition(
        start_mib=start, size_mib=size, filesystem=ESP_FILESYSTEM,
        mountpoint=ESP_MOUNTPOINT, flags=ESP_FLAGS)


def _root(start: int = 513, size: int = 8192,
          filesystem: str = "ext4") -> PlannedPartition:
    return PlannedPartition(
        start_mib=start, size_mib=size, filesystem=filesystem, mountpoint="/")


# --- der Vorschlag ----------------------------------------------------


def test_the_suggestion_is_an_esp_and_a_root():
    esp, root = suggested_layout(FORTY_GIB)
    assert esp.mountpoint == ESP_MOUNTPOINT
    assert esp.filesystem == ESP_FILESYSTEM
    assert root.mountpoint == "/"
    assert root.filesystem == "ext4"


def test_the_suggestion_has_no_swap_and_no_separate_home():
    """Auslagerung gibt es schon als zram (installer.core.translate setzt
    "swap": {"enabled": True}, und archinstall macht daraus
    systemd-zram-setup@zram0), und ein eigenes /home legt die Aufteilung
    auf einer Maschine fest, von der niemand weiss, wofuer sie benutzt
    wird. Beides steht ausfuehrlich in suggested_layout()."""
    plan = suggested_layout(FORTY_GIB)
    assert len(plan) == 2
    assert not any(partition.is_swap() for partition in plan)
    assert not any(partition.mountpoint == "/home" for partition in plan)


def test_the_esp_carries_both_flags():
    """archinstall braucht beide und aus zwei verschiedenen Gruenden:
    get_efi_partition() filtert auf is_efi() (Flagge esp),
    get_boot_partition() auf is_boot() (Flagge boot), und
    Installer.add_bootloader() wirft ohne die zweite "Could not detect
    boot at mountpoint"."""
    esp, _root_part = suggested_layout(FORTY_GIB)
    assert "esp" in esp.flags
    assert "boot" in esp.flags


def test_the_suggestion_starts_at_one_mib():
    """Size.is_valid_start() ist `self >= Size(1, Unit.MiB, ...)`, und
    parse_arg wirft sonst "First partition must start at no less than
    1 MiB"."""
    esp, _root_part = suggested_layout(FORTY_GIB)
    assert esp.start_mib == ALIGNMENT_MIB == 1


def test_the_suggestion_stops_one_mib_before_the_end():
    """Size.gpt_end() ist `self - Size(1, Unit.MiB, ...)`, und parse_arg
    wirft darueber hinaus "Partition overlaps backup GPT header"."""
    _esp_part, root = suggested_layout(FORTY_GIB)
    assert root.end_mib == disk_mib(FORTY_GIB) - GPT_TAIL_MIB


def test_the_suggestion_fills_the_disk_without_a_gap():
    assert free_mib(suggested_layout(FORTY_GIB), FORTY_GIB) == 0


def test_the_chosen_filesystem_reaches_the_root_of_the_suggestion():
    _esp_part, root = suggested_layout(FORTY_GIB, filesystem="btrfs")
    assert root.filesystem == "btrfs"


def test_a_disk_that_cannot_hold_the_suggestion_gets_none():
    """Eine Wurzel mit negativer Groesse waere die Alternative, und die
    kaeme erst bei archinstall an."""
    too_small = (MIN_DISK_MIB - 1) * 1024 * 1024
    assert suggested_layout(too_small) == []


def test_the_smallest_allowed_disk_still_gets_a_suggestion():
    """Die Grenze selbst, nicht "offensichtlich zu klein": MIN_DISK_MIB
    ist genau ESP + Ausrichtung + GPT-Schwanz + MIN_ROOT_MIB, also muss
    die Wurzel dort auf das MiB genau MIN_ROOT_MIB gross werden."""
    plan = suggested_layout(MIN_DISK_MIB * 1024 * 1024)
    assert len(plan) == 2
    assert plan[1].size_mib == MIN_ROOT_MIB


def test_the_suggestion_is_what_the_translation_used_to_compute():
    """Der Vorschlag hat frueher in installer/core/translate.py gestanden
    und dort ESP ab 1 MiB mit 512 MiB und die Wurzel bis 1 MiB vor
    Schluss ergeben. Der Textassistent und jede vorhandene
    Konfigurationsdatei laufen weiter darueber, also muss er Byte fuer
    Byte derselbe geblieben sein."""
    esp, root = suggested_layout(64 * GIB)
    assert (esp.start_mib, esp.size_mib) == (1, 512)
    assert (root.start_mib, root.size_mib) == (513, 64 * 1024 - 513 - 1)


# --- Luecken und Platz ------------------------------------------------


def test_a_hole_in_the_middle_is_free_space():
    plan = [_esp(), _root(start=4096, size=4096)]
    assert free_regions(plan, FORTY_GIB)[0] == (513, 4096 - 513)


def test_the_space_after_the_last_partition_is_free():
    plan = [_esp(), _root(size=1024)]
    start, size = free_regions(plan, FORTY_GIB)[-1]
    assert start == 513 + 1024
    assert start + size == last_usable_mib(FORTY_GIB)


def test_the_gpt_tail_is_not_free_space():
    """Das letzte MiB gehoert der Sicherungskopie des GPT-Kopfes. Waere es
    frei, passte eine Partition genau ein MiB zu weit."""
    assert last_usable_mib(FORTY_GIB) == disk_mib(FORTY_GIB) - 1
    plan = [_esp()]
    _start, size = free_regions(plan, FORTY_GIB)[-1]
    assert 513 + size == disk_mib(FORTY_GIB) - 1


def test_first_fit_takes_the_first_hole_that_is_big_enough():
    """Die erste passende und nicht die groesste: eine neue Partition soll
    die vorhandene Luecke schliessen, statt eine zweite aufzumachen."""
    plan = [_esp(), _root(start=4096, size=1024)]
    assert first_fit(plan, FORTY_GIB, 1000) == 513


def test_first_fit_skips_a_hole_that_is_too_small():
    plan = [_esp(), _root(start=1000, size=1024)]
    assert first_fit(plan, FORTY_GIB, 2000) == 1000 + 1024


def test_first_fit_answers_none_when_nothing_fits():
    assert first_fit(suggested_layout(FORTY_GIB), FORTY_GIB, 1) is None


def test_the_largest_hole_is_not_the_sum_of_the_holes():
    """Zwei Luecken von je 1000 MiB sind 2000 MiB frei und tragen
    trotzdem keine Partition von 1500 MiB. Das ist der Unterschied, aus
    dem die Eingabepruefung ihre Obergrenze nimmt."""
    # Zwei Luecken von je genau 1000 MiB: eine vor der ersten Partition,
    # eine zwischen den beiden. Die zweite Partition reicht bis ans
    # letzte nutzbare MiB, damit hinten keine dritte entsteht.
    plan = [
        _esp(start=1001, size=1),
        _root(start=2002, size=last_usable_mib(FORTY_GIB) - 2002),
    ]
    assert free_mib(plan, FORTY_GIB) == 2000
    assert largest_free_mib(plan, FORTY_GIB) == 1000


def test_allocated_is_the_sum_of_the_partitions():
    assert allocated_mib([_esp(), _root(size=8192)]) == 512 + 8192


def test_free_space_is_never_negative_when_the_layout_is_too_big():
    """"Platte minus Partitionen" waere hier negativ und wuerde eine
    Ueberbelegung als freien Platz melden. free_mib() zaehlt die
    Luecken."""
    plan = [_root(start=1, size=disk_mib(FORTY_GIB) * 2)]
    assert free_mib(plan, FORTY_GIB) == 0


# --- Groessen lesen ---------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("20G", 20 * 1024),
    ("512M", 512),
    ("1T", 1024 * 1024),
    ("2GiB", 2048),
    ("2 GB", 2048),
    ("1,5G", 1536),
    ("1.5G", 1536),
    ("  8g  ", 8192),
])
def test_a_size_with_a_unit_is_read(text: str, expected: int):
    assert parse_size_mib(text, available_mib=10 ** 9) == (expected, "")


def test_binary_units_even_where_the_letter_says_decimal():
    """"20GB" heisst hier 20 GiB und nicht 20 Milliarden Byte. Der Rest
    des Programms rechnet in KiB/MiB/GiB (installer.core.disks.
    human_size), und eine Seite, auf der man 20G eingibt und 18,6 GiB
    zurueckbekommt, sieht nach einem Fehler aus."""
    assert parse_size_mib("20GB", available_mib=10 ** 9)[0] == 20 * 1024


def test_a_size_without_a_unit_is_refused_and_says_why():
    """"20" ist auf dieser Seite nicht eindeutig, und zwischen 20 MiB und
    20 GiB liegt der Faktor tausend."""
    size, problem = parse_size_mib("20", available_mib=10 ** 9)
    assert size == 0
    assert "unit" in problem


def test_nonsense_is_refused():
    assert parse_size_mib("zepos-test", available_mib=10 ** 9)[0] == 0


def test_an_empty_size_asks_for_one_instead_of_complaining():
    _size, problem = parse_size_mib("   ", available_mib=10 ** 9)
    assert "enter a size" in problem


def test_the_word_rest_takes_everything_that_is_left():
    assert parse_size_mib("rest", available_mib=4711) == (4711, "")


def test_rest_on_a_full_disk_says_there_is_nothing_left():
    _size, problem = parse_size_mib("rest", available_mib=0)
    assert "no free space" in problem


def test_a_size_that_does_not_fit_names_both_numbers():
    """Die Meldung muss beantworten, was der Nutzer als naechstes wissen
    will: wie viel denn noch geht."""
    size, problem = parse_size_mib("20G", available_mib=1024)
    assert size == 0
    assert "20.0 GiB" in problem
    assert "1.0 GiB" in problem


def test_a_size_is_rounded_down_and_never_up():
    """Aufrunden koennte die letzte Partition ueber gpt_end() schieben,
    und archinstall lehnt dann die ganze Konfiguration ab. 0,5 MiB sind
    deshalb 0 MiB - und damit zu klein, nicht zu gross."""
    assert parse_size_mib("1536K", available_mib=10 ** 9)[0] == 1
    assert parse_size_mib("512K", available_mib=10 ** 9)[0] == 0


def test_a_size_below_one_mib_is_refused():
    _size, problem = parse_size_mib("100K", available_mib=10 ** 9)
    assert "at least 1 MiB" in problem


# --- was gar nicht erst weitergereicht werden darf --------------------


def test_the_suggestion_itself_is_accepted():
    assert layout_errors(suggested_layout(FORTY_GIB), FORTY_GIB) == []


def test_an_empty_layout_is_refused():
    """wipe=True mit einer leeren Partitionsliste loescht die Platte und
    legt nichts an - der Fall, den installer/core/translate.py schon
    einmal als toedlich beschrieben hat."""
    problems = layout_errors([], FORTY_GIB)
    assert problems and "empty" in problems[0]


def test_a_layout_without_an_esp_is_refused():
    problems = layout_errors([_root()], FORTY_GIB)
    assert any("EFI system partition" in problem for problem in problems)


def test_a_layout_without_a_root_is_refused():
    problems = layout_errors([_esp()], FORTY_GIB)
    assert any("root partition" in problem for problem in problems)


def test_two_roots_are_refused():
    plan = [_esp(), _root(size=1024), _root(start=2048, size=1024)]
    assert any("more than one root" in problem
               for problem in layout_errors(plan, FORTY_GIB))


def test_two_esps_are_refused():
    plan = [_esp(), _esp(start=1024), _root(start=2048)]
    assert any("more than one EFI" in problem
               for problem in layout_errors(plan, FORTY_GIB))


def test_the_same_mount_point_twice_is_refused():
    """Eine der beiden waere im installierten System nicht erreichbar,
    und welche das ist, haengt an der Reihenfolge in der fstab.

    Die vier Partitionen ueberschneiden sich ausdruecklich NICHT. Ein
    frueherer Entwurf dieses Tests liess die Wurzel bis 8705 laufen und
    /home bei 8192 anfangen - die Meldung, die er dann fand, war die
    ueber die Ueberschneidung, in der "/home" auch vorkommt, und der Test
    blieb gruen, als die Pruefung auf doppelte Einhaengepunkte
    ausgeschaltet wurde. Gemessen im Mutationslauf zu dieser Aufgabe.
    """
    home = PlannedPartition(
        start_mib=8705, size_mib=1024, filesystem="ext4", mountpoint="/home")
    other = PlannedPartition(
        start_mib=16384, size_mib=1024, filesystem="ext4", mountpoint="/home")
    plan = [_esp(), _root(), home, other]
    problems = layout_errors(plan, FORTY_GIB)
    assert not any("overlap" in problem for problem in problems), problems
    assert any("Two partitions are mounted at /home" in problem
               for problem in problems)


def test_an_esp_that_is_not_fat32_is_refused():
    """Die Firmware liest FAT, und nur FAT."""
    wrong = PlannedPartition(
        start_mib=1, size_mib=512, filesystem="ext4",
        mountpoint=ESP_MOUNTPOINT, flags=ESP_FLAGS)
    problems = layout_errors([wrong, _root()], FORTY_GIB)
    assert any("fat32" in problem for problem in problems)


def test_the_minimum_sizes_are_the_ones_that_were_measured():
    """Die drei Zahlen ausgeschrieben, und zwar hier und nicht als
    MIN_ESP_MIB in jeder Zusicherung darunter.

    Ein Test, der seine Eingabe aus derselben Konstante rechnet, die er
    prueft, geht mit ihr mit: MIN_ESP_MIB auf 1 gesetzt macht aus
    "MIN_ESP_MIB - 1" die Null, und die ist immer noch zu klein. Gemessen
    - der Mutationslauf zu dieser Aufgabe hat genau das nicht gefangen.

    Woher die Zahlen kommen:
      * 200 MiB nennt archinstall selbst (Installer._verify_boot_part:
        "not large enough to install a boot loader");
      * 2048 MiB ist Platz fuer ein Basissystem plus zepos-desktop;
      * 2562 MiB stand vor dieser Aufgabe als Literal in
        installer/core/model.py und ist die Summe der vier.
    """
    assert MIN_ESP_MIB == 200
    assert MIN_ROOT_MIB == 2048
    assert MIN_DISK_MIB == 2562
    assert MIN_DISK_MIB == 512 + ALIGNMENT_MIB + GPT_TAIL_MIB + MIN_ROOT_MIB


def test_an_esp_below_the_boot_loader_minimum_is_refused():
    """archinstall nennt selbst 200 MiB (Installer._verify_boot_part:
    "not large enough to install a boot loader"), prueft es in 4.4-1 aber
    nicht - der Aufruf steht in sanity_check() auskommentiert. Faellt es
    hier nicht auf, faellt es auf, wenn grub-install auf einer schon
    geloeschten Platte keinen Platz mehr findet."""
    problems = layout_errors([_esp(size=64), _root()], FORTY_GIB)
    assert any("boot loader" in problem for problem in problems)


def test_an_esp_exactly_at_the_minimum_is_accepted():
    """Die Grenze selbst, mit der Zahl ausgeschrieben: >= und nicht >."""
    assert layout_errors([_esp(size=200), _root(start=201)], FORTY_GIB) == []
    assert any("boot loader" in problem for problem
               in layout_errors([_esp(size=199), _root(start=201)], FORTY_GIB))


def test_a_root_that_is_too_small_is_refused():
    problems = layout_errors([_esp(), _root(size=1024)], FORTY_GIB)
    assert any("root partition is only" in problem for problem in problems)


def test_a_root_exactly_at_the_minimum_is_accepted():
    assert layout_errors([_esp(), _root(size=2048)], FORTY_GIB) == []
    assert any("root partition is only" in problem for problem
               in layout_errors([_esp(), _root(size=2047)], FORTY_GIB))


def test_a_root_on_swap_is_refused():
    """is_swap() haengt am Dateisystem, is_root() am Einhaengepunkt -
    beides zugleich ist eine Partition, die archinstall mit swapon()
    einbindet und als Wurzel sucht."""
    swap_root = PlannedPartition(
        start_mib=513, size_mib=8192, filesystem="linux-swap", mountpoint="/")
    problems = layout_errors([_esp(), swap_root], FORTY_GIB)
    assert any("cannot be swap" in problem for problem in problems)


def test_overlapping_partitions_are_refused_and_both_are_named():
    """archinstall wirft dafuer "Partitions overlap" - nachdem es
    angefangen hat zu loeschen. Hier steht es auf der Seite, und es steht
    dabei, WELCHE zwei sich ueberschneiden, weil man sonst raten muss."""
    plan = [_esp(), _root(start=256, size=8192)]
    problems = layout_errors(plan, FORTY_GIB)
    overlap = [problem for problem in problems if "overlap" in problem]
    assert overlap
    assert ESP_MOUNTPOINT in overlap[0]
    assert "/" in overlap[0]


def test_partitions_that_only_touch_do_not_overlap():
    """Die Grenze selbst: end_mib ist das erste MiB, das schon NICHT mehr
    dazugehoert - dieselbe Rechnung wie archinstalls
    PartitionModification.end. Eine Partition, die genau dort anfaengt,
    ist erlaubt, und der Vorschlag baut genau das."""
    assert layout_errors([_esp(), _root(start=513)], FORTY_GIB) == []


def test_a_partition_past_the_end_of_the_disk_is_refused():
    beyond = _root(start=513, size=disk_mib(FORTY_GIB))
    problems = layout_errors([_esp(), beyond], FORTY_GIB)
    assert any("past the end" in problem for problem in problems)


def test_the_last_mib_of_the_disk_is_already_past_the_end():
    """Ein MiB zu weit, nicht zwei: dort liegt die Sicherungskopie des
    GPT-Kopfes, und archinstall nennt das "Partition overlaps backup GPT
    header"."""
    total = disk_mib(FORTY_GIB)
    fits = _root(start=513, size=total - GPT_TAIL_MIB - 513)
    one_too_far = _root(start=513, size=total - 513)
    assert layout_errors([_esp(), fits], FORTY_GIB) == []
    assert any("past the end" in problem
               for problem in layout_errors([_esp(), one_too_far], FORTY_GIB))


def test_a_partition_starting_before_one_mib_is_refused():
    """Dort steht der primaere GPT-Kopf. archinstall: "First partition
    must start at no less than 1 MiB"."""
    problems = layout_errors([_esp(start=0), _root()], FORTY_GIB)
    assert any("GPT header" in problem for problem in problems)


def test_a_partition_without_a_size_is_refused():
    empty = PlannedPartition(
        start_mib=8192, size_mib=0, filesystem="ext4", mountpoint="/home")
    problems = layout_errors([_esp(), _root(), empty], FORTY_GIB)
    assert any("at least 1 MiB" in problem for problem in problems)


def test_a_swap_partition_alongside_root_is_accepted():
    """Der Ruhezustand auf die Platte braucht eine, und sie hat keinen
    Einhaengepunkt - archinstall erkennt sie am Dateisystem
    (PartitionModification.is_swap) und bindet sie mit swapon() ein."""
    swap = PlannedPartition(
        start_mib=513, size_mib=4096, filesystem="linux-swap")
    assert layout_errors([_esp(), swap, _root(start=4609)], FORTY_GIB) == []


def test_the_findings_are_ordered_so_the_first_one_is_worth_showing():
    """Die Seite zeigt eine Zeile. Bei einer Einteilung, der die Wurzel
    fehlt UND deren ESP zu klein ist, ist die fehlende Wurzel die
    Meldung, die zuerst etwas aendert."""
    problems = layout_errors([_esp(size=1)], FORTY_GIB)
    assert "root partition" in problems[0]


# --- Anzeige ----------------------------------------------------------


def test_a_planned_partition_names_its_mount_point_and_size():
    assert "/home" in PlannedPartition(
        start_mib=1, size_mib=2048, filesystem="ext4",
        mountpoint="/home").describe()


def test_the_esp_is_named_as_what_it_is():
    """"/boot - 512 MiB" sagt nicht, dass daraus die EFI-Systempartition
    wird, und das ist die eine Partition, ohne die nichts startet."""
    assert "EFI" in _esp().describe()


def test_swap_is_named_although_it_has_no_mount_point():
    swap = PlannedPartition(start_mib=1, size_mib=2048, filesystem="linux-swap")
    assert "Swap" in swap.describe()


def test_a_partition_shows_where_it_lies():
    """Die Lage ist das Einzige, woran man auf der Seite sieht, dass
    zwischen zwei Partitionen eine Luecke steht."""
    contents = _root(start=1024, size=1024).describe_contents()
    assert "1.0 GiB" in contents and "2.0 GiB" in contents


def test_a_planned_partition_shows_its_filesystem():
    assert "btrfs" in _root(filesystem="btrfs").describe_contents()


def test_sizes_are_written_the_way_the_disk_list_writes_them():
    """Kein zweites Zahlenformat auf derselben Seite - human_mib() geht
    durch dasselbe installer.core.disks.human_size wie die Plattenliste
    eine Seite vorher."""
    assert human_mib(1024) == "1.0 GiB"
    assert human_mib(512) == "512.0 MiB"
