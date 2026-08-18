# SPDX-License-Identifier: GPL-3.0-or-later
"""The installation log, rendered the way a terminal would show it.

REPORTED FROM THE MEDIUM: "die installations auflistung ist teilweise
buggy und zeigt komische Zeichen und alles nicht korrekt eingerückt".

The log was inserted into a text view exactly as it came off the
process, and it is not text: it is a stream written FOR a terminal.
pacman colours it, hides the cursor, returns to the start of a line to
redraw a progress bar, and moves the cursor two lines UP to redraw both
lines of a download. A text view understands none of that, so every
escape came out as a box and every redraw added another line.

The samples below are the real shapes, taken from the log of an
installation that ran in QEMU on 10.08.2026 - the same one whose
screenshot showed `[1m[32m==>` and `[?25l:: Synchronizing package
databases`.
"""
from installer.gui.pages import TerminalLog


def render(*chunks: str) -> str:
    log = TerminalLog()
    for chunk in chunks:
        log.feed(chunk)
    return log.text()


def test_colour_and_cursor_escapes_do_not_reach_the_screen():
    """The boxes. Every one of these appeared in the shipped log."""
    text = render(
        "\x1b[1m\x1b[32m==>\x1b[0m\x1b[1m Creating install root\x1b[0m\n"
        "\x1b[?25l:: Synchronizing package databases...\n")

    assert "\x1b" not in text
    assert text.splitlines() == [
        "==> Creating install root",
        ":: Synchronizing package databases...",
    ]


def test_a_carriage_return_redraws_the_line_instead_of_adding_one():
    """A download counter writes the same line over and over."""
    text = render("core   0.0 B\rcore   1.2 MiB\rcore   4.4 MiB  100%\n")

    assert text.splitlines() == ["core   4.4 MiB  100%"]


def test_cursor_up_redraws_the_lines_above():
    """pacman draws two lines per download and moves back over both.

    Without this the log grew by two lines for every refresh - which is
    what "nicht korrekt eingerückt" looked like from the outside: a
    page of half-finished progress bars.
    """
    text = render(
        "core     10%\nextra     0%\n"
        "\x1b[2Fcore     60%\nextra    30%\n"
        "\x1b[2Fcore    100%\nextra   100%\n")

    assert text.splitlines() == ["core    100%", "extra   100%"]


def test_an_escape_split_across_two_chunks_is_still_understood():
    """Chunks arrive at whatever size the process flushed, and the log is
    read on a 250 ms timer - so a sequence can be cut in half. Handled by
    keeping the unfinished line between calls."""
    text = render("core  50%", "\rcore 100%\n")

    assert text.splitlines() == ["core 100%"]


def test_a_line_clear_empties_the_line():
    text = render("etwas Altes\x1b[2K\rNeues\n")

    assert text.splitlines() == ["Neues"]


def test_the_log_does_not_grow_without_bound():
    """An installation writes tens of thousands of lines and the window
    can show forty.

    This is not a memory limit but a per-tick one: the whole text is
    handed to the view four times a second, and every line in it is
    laid out again. Four thousand lines of monospace was enough to make
    a modest machine look like it had stopped - reported from the medium
    as an installer hanging at "Starting device modifications".
    """
    log = TerminalLog(max_lines=100)
    for number in range(1000):
        log.feed(f"Zeile {number}\n")

    lines = log.text().splitlines()
    assert len(lines) <= 100, len(lines)
    assert lines[-1] == "Zeile 999", "the newest line was dropped instead"


# --- the number in the bar -------------------------------------------------


def test_progress_comes_from_pacmans_own_counter():
    """The one honest number in the run.

    An earlier version of this page pulsed instead, and its comment gave
    the reason: "a fake percentage that stalls at 40% is worse than an
    honest still-working". That argument is against INVENTED numbers.
    This one is read out of the log.
    """
    log = TerminalLog()
    log.feed("Installing packages\n")
    before = log.progress()
    log.feed("(1/200) installing linux\n")
    early = log.progress()
    log.feed("(100/200) installing hyprland\n")
    half = log.progress()
    log.feed("(200/200) installing zepos-config\n")
    done = log.progress()

    assert before < early < half < done
    assert done <= 0.80, "the package phase must leave room for what follows"


def test_progress_only_ever_moves_forward():
    """A phase marker arriving after the counter has started must not
    pull the bar backwards - a bar that jumps back reads as a failure."""
    log = TerminalLog()
    log.feed("(150/200) installing something\n")
    high = log.progress()
    log.feed("Creating install root\n")

    assert log.progress() >= high


def test_progress_before_anything_is_zero_rather_than_a_guess():
    assert TerminalLog().progress() == 0.0


def test_a_package_name_containing_a_counter_is_not_mistaken_for_one():
    """The pattern is anchored at the start of the line for this."""
    log = TerminalLog()
    log.feed("installing weird-(9/9)-package\n")

    assert log.progress() == 0.0


def test_the_default_bound_is_small_enough_to_redraw_four_times_a_second():
    """The number itself, because it is a performance decision and the
    only place it is written down is a default argument."""
    log = TerminalLog()
    for number in range(2000):
        log.feed(f"Zeile {number}\n")

    assert len(log.text().splitlines()) <= 5000
