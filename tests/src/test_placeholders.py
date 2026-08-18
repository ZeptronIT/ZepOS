# SPDX-License-Identifier: GPL-3.0-or-later
"""Nothing broken may be written, and no success may be reported over it.

The template processor used to treat an unknown placeholder as a warning
printed AFTER the file had been written, and a failed import of the style
SSOT as a reason to carry on with no styles at all. Both end the same
way: the generator says "successfully generated", the user restarts their
bar, and the theme is broken with nothing in the log pointing at the
cause.

These tests hold both doors shut.
"""
import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture
def processor(monkeypatch):
    """The real ConfigProcessor, imported the way the generator imports it.

    src/ has no __init__.py and template_processor.py uses flat imports
    (`from icons_db import ...`), because the generator runs it as a
    script from the system root. Importing it as `src.template_processor` would
    therefore fail on its own first import line.
    """
    monkeypatch.syspath_prepend(str(SRC))
    import template_processor

    return template_processor


def _template(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "broken.template"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "placeholder",
    [
        "STYLE_DOES_NOT_EXIST",
        "ICON_DOES_NOT_EXIST",
        "ZEPOS_DOES_NOT_EXIST",
        # No known prefix at all - a typo nobody defined either, and it
        # survives into the output exactly like the three above.
        "TYPO_WITH_NO_PREFIX",
    ],
)
def test_an_undefined_placeholder_fails_the_generation(processor, tmp_path, placeholder):
    template = _template(tmp_path, f"value: {{{{{placeholder}}}}}\n")
    output = tmp_path / "out" / "config.css"

    with pytest.raises(processor.UnresolvedPlaceholders) as excinfo:
        processor.ConfigProcessor().apply_template(template, output)

    assert placeholder in str(excinfo.value)


def test_a_failed_generation_leaves_the_output_directory_untouched(processor, tmp_path):
    """Not merely "no new file": the previous config must survive.

    Writing first and raising afterwards would have replaced a working
    configuration with a broken one and then complained about it.
    """
    outdir = tmp_path / "out"
    outdir.mkdir()
    existing = outdir / "config.css"
    existing.write_text("the configuration that already worked\n", encoding="utf-8")

    template = _template(tmp_path, "value: {{STYLE_DOES_NOT_EXIST}}\n")

    with pytest.raises(processor.UnresolvedPlaceholders):
        processor.ConfigProcessor().apply_template(template, existing)

    assert existing.read_text(encoding="utf-8") == "the configuration that already worked\n"
    assert sorted(p.name for p in outdir.iterdir()) == ["config.css"]


def test_an_icon_defined_without_a_glyph_fails_the_generation_too(processor,
                                                                   tmp_path):
    """The regression the comment beside that branch describes, measured.

    fetch_icons.py stores "?" for a name it could not find upstream, so
    the icon is DEFINED and unusable at the same time - a membership test
    finds it and a user gets a literal question mark in their bar. That
    is how twelve placeholders came to ship rendering as "?", and it is
    why apply_template compares the value rather than only the key.

    Nothing exercised the comparison. `if icon and icon != UNRESOLVED_ICON`
    could be written `if icon is not None` and the whole suite stayed
    green, which puts the shipped defect back exactly as it was.
    """
    template = _template(tmp_path, "glyph: {{ICON_NEVER_FETCHED}}\n")
    output = tmp_path / "out" / "config"
    output.parent.mkdir()

    with pytest.raises(processor.UnresolvedPlaceholders) as excinfo:
        processor.ConfigProcessor(
            icons={"ICON_NEVER_FETCHED": processor.UNRESOLVED_ICON}
        ).apply_template(template, output)

    assert "ICON_NEVER_FETCHED" in str(excinfo.value)
    assert not output.exists(), (
        "a literal question mark was written where a glyph belongs")


def test_an_icon_that_does_have_a_glyph_is_substituted(processor, tmp_path):
    """The other half: refusing "?" must not mean refusing icons.

    Without this, the test above is satisfied by an icon branch that
    rejects everything.
    """
    template = _template(tmp_path, "glyph: {{ICON_PRESENT}}\n")
    output = tmp_path / "out" / "config"
    output.parent.mkdir()

    processor.ConfigProcessor(
        icons={"ICON_PRESENT": ""}).apply_template(template, output)

    assert output.read_text(encoding="utf-8") == "glyph: \n"


def test_a_template_whose_placeholders_all_resolve_still_generates(processor, tmp_path):
    """The guard has to refuse the broken case, not every case."""
    template = _template(tmp_path, "root={{ZEPOS_SYSTEM_ROOT}}\n")
    output = tmp_path / "out" / "config"
    output.parent.mkdir()

    processor.ConfigProcessor().apply_template(template, output)

    written = output.read_text(encoding="utf-8")
    assert "{{" not in written
    assert written.startswith("root=/")


def test_every_placeholder_the_templates_use_is_defined_somewhere(processor):
    """Catches the gap before generation does, and without running it.

    Twelve ICON_ placeholders were referenced by templates while missing
    from the SSOT. Nothing noticed, because get_icon() answered "?" and
    the branch meant to catch it compared against a sentinel it could
    never receive. Generation is fatal about this now, but a static check
    names every offender at once instead of stopping at the first.
    """
    processor_cls = processor.ConfigProcessor
    known = set(processor_cls().icons) | set(processor_cls().styles)
    known |= set(processor.path_variables())
    unresolvable = {
        name for name, value in processor_cls().icons.items()
        if value == processor.UNRESOLVED_ICON
    }

    scanned = 0
    offenders = {}
    for directory in ("templates", "styles"):
        for path in sorted((SRC / directory).glob("*.template")):
            text = path.read_text(encoding="utf-8")
            for placeholder in sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text))):
                scanned += 1
                if placeholder not in known or placeholder in unresolvable:
                    offenders.setdefault(placeholder, []).append(path.name)

    # A scan that read no template answers "no offenders" too.
    assert scanned > 100, (
        f"only {scanned} placeholder uses found under {SRC} - the scan is "
        "not reading the templates, so its result means nothing")
    assert len(known) > 100, f"the SSOT answered {len(known)} names"

    assert offenders == {}, "placeholders no SSOT defines: " + ", ".join(
        f"{name} ({len(files)} template(s), e.g. {files[0]})"
        for name, files in sorted(offenders.items())
    )


def test_the_scan_above_would_catch_an_icon_that_has_no_glyph():
    """`placeholder in unresolvable` against a set that is empty today.

    Every icon in the shipped database currently has a glyph, so that
    half of the condition has never once been true and cannot be shown to
    work by running the scan over the real tree - it is dead text that
    reads like a check. The rule is therefore exercised against a
    database built here, with one fetched icon and one that was not.

    This is the same defect the scan exists to catch: a name that is
    present and unusable, which a membership test alone waves through.
    """
    icons = {"ICON_FETCHED": "", "ICON_NEVER_FETCHED": "?"}
    unresolvable = {name for name, value in icons.items() if value == "?"}
    known = set(icons)

    def offends(placeholder: str) -> bool:
        return placeholder not in known or placeholder in unresolvable

    assert offends("ICON_NEVER_FETCHED"), (
        "an icon defined as '?' is reported as present")
    assert offends("ICON_NOBODY_DEFINED"), "an undefined name is not reported"
    assert not offends("ICON_FETCHED"), (
        "a perfectly good icon is reported - a rule that fires on "
        "everything gets switched off")


def test_a_missing_style_ssot_stops_the_run_instead_of_emptying_it(tmp_path, monkeypatch):
    """The hazard this whole round exists for.

    style_definition.py imports paths.py since the system/user split, so
    ONE file left out of a package list is enough to make that import
    fail. It used to be caught and turned into STYLE_VARIABLES = {}, at
    which point every {{STYLE_*}} was merely "missing" - a warning - and
    the generator wrote CSS full of literal placeholder text and reported
    success.

    Reproduced honestly: template_processor.py and icons_db.py are copied into
    a directory that has no style_definition.py, and imported from there.
    Renaming the real file aside would mean writing into the work tree,
    which the isolation guard forbids - correctly.
    """
    package = tmp_path / "pkg"
    package.mkdir()
    # settings.py MUSS mitkommen, obwohl diese Zusicherung es nicht prueft.
    #
    # GEMESSEN am 13.08.2026: template_processor.py holt in Zeile 37
    # `from settings import UnusableSettings` und erst in Zeile 52
    # `from style_definition import STYLE_VARIABLES`. Ohne settings.py im
    # Paket bricht der Lauf eine Stufe FRUEHER ab, und die Meldung lautet
    # "settings could not be imported" - richtig, aber nicht das, was
    # hier gemessen werden soll.
    #
    # Verschaerft hat es das Verzeichnis settings/ in der Wurzel dieses
    # Baums - die Einstellungs-Anwendung, seit dem 12.08.2026. `import
    # settings` findet es als Namensraumpaket, scheitert dann an
    # UnusableSettings und meldet "unknown location". Unvollstaendig war
    # also die NACHSTELLUNG und nicht die Behauptung darunter; deshalb
    # steht hier eine Datei mehr und keine weichere Zusicherung.
    for name in ("template_processor.py", "icons_db.py", "settings.py"):
        shutil.copy(SRC / name, package / name)
    assert not (package / "style_definition.py").exists()

    # A style_definition left in sys.modules by another test would be
    # found by the import below and hide exactly what is being tested.
    monkeypatch.delitem(sys.modules, "style_definition", raising=False)
    monkeypatch.delitem(sys.modules, "icons_db", raising=False)
    monkeypatch.delitem(sys.modules, "settings", raising=False)

    # UND src/ MUSS AUS DEM SUCHPFAD, sonst prueft dieser Test nichts.
    #
    # GEMESSEN am 13.08.2026: allein lief er gruen, im vollen Lauf fiel
    # er mit "DID NOT RAISE SystemExit" um. Der Unterschied ist der
    # Suchpfad - irgendein anderer Test legt src/ hinein und raeumt es
    # nicht weg. Dann findet `from style_definition import ...` die
    # ECHTE Datei, der Lauf bricht nicht ab, und diese Zusicherung misst
    # das Gegenteil dessen, was sie behauptet, ohne es zu merken.
    #
    # Eine Zusicherung, deren Ergebnis von der Reihenfolge der anderen
    # abhaengt, ist keine. Sie stellt den Pfad deshalb selbst her,
    # statt sich auf die Sauberkeit der uebrigen zu verlassen.
    fremd = SRC.resolve()
    monkeypatch.setattr(
        sys, "path",
        [eintrag for eintrag in sys.path
         if Path(eintrag).resolve() != fremd] if sys.path else [])
    monkeypatch.syspath_prepend(str(package))

    spec = importlib.util.spec_from_file_location(
        "template_processor_without_styles", package / "template_processor.py"
    )
    module = importlib.util.module_from_spec(spec)

    with pytest.raises(SystemExit) as excinfo:
        spec.loader.exec_module(module)

    message = str(excinfo.value)
    assert "style_definition" in message
    assert "broken installation" in message
    assert not hasattr(module, "STYLE_VARIABLES"), (
        "the module carried on past the failed import"
    )
