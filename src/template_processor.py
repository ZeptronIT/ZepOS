#!/usr/bin/env python3
"""
Template processor for ZepOS configuration files.
"""

import json
import os
import re
import sys
import signal
from pathlib import Path
from typing import Dict, List, Optional
import argparse

# Handle broken pipe error (when output is piped to closed process)
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

# The two SSOT modules. A failed import here is a broken installation,
# never a configuration choice, so both stop the run.
#
# style_definition used to fall back to an empty STYLE_VARIABLES. That
# turned one missing file into configuration written with literal
# {{STYLE_*}} text in it, reported as a success, and discovered by the
# user as a broken bar with nothing in the log to explain it. The
# fallback became far easier to trigger once style_definition started
# importing paths.py: from then on a single file left out of a package
# list was enough.
try:
    from icons_db import ALL_ICONS, get_icon
except ImportError as exc:
    raise SystemExit(
        f"icons_db could not be imported: {exc}\n"
        "This is a broken installation, not a configuration problem."
    ) from exc

try:
    from settings import UnusableSettings
except ImportError as exc:
    raise SystemExit(
        f"settings could not be imported: {exc}\n"
        "This is a broken installation, not a configuration problem."
    ) from exc

# UnusableSettings is the other thing that can come out of this import,
# and it is the opposite kind of failure: the installation is fine and
# the user's settings file is not. It arrives here because
# style_definition reads that file while it is being imported, and it is
# turned into a message rather than a traceback because the person who
# has to act on it is the one who edited the file - a stack ending in
# json/decoder.py tells them nothing about which file to repair.
try:
    from style_definition import STYLE_VARIABLES
except UnusableSettings as exc:
    raise SystemExit(str(exc)) from exc
except ImportError as exc:
    raise SystemExit(
        f"style_definition could not be imported: {exc}\n"
        "This is a broken installation, not a configuration problem. "
        "Continuing would write configuration files containing literal "
        "{{STYLE_*}} placeholders while reporting success."
    ) from exc


# What fetch_icons.py stores for an icon whose Nerd Font name it could
# not find upstream (see fetch_icons.py:90). The name is defined but the
# glyph is not, which is just as unusable as no definition at all.
UNRESOLVED_ICON = "?"


class UnresolvedPlaceholders(Exception):
    """A placeholder survived substitution.

    Whatever the placeholder was for - an icon, a style value, a root -
    the generated file now carries literal "{{...}}" text where a value
    belongs. Waybar and AGS do not reject that; they render it, or fail
    to parse and start with nothing. Reporting success over it is the
    failure mode this exception exists to prevent.
    """


def path_variables() -> Dict[str, str]:
    """The roots that have to be resolved while generating, not at run time.

    A generated artifact ends up somewhere else entirely - ~/.local/bin,
    ~/.config/ags/scripts - and cannot work out which package it came
    from. A shell default cannot either: it has to guess between an
    installed /usr/share/zepos and a checkout, and guessing wrong makes
    the artifact abort with nothing but "cd: no such file or directory".

    The generator does know, so the value is substituted here, exactly
    the way {{ICON_*}} and {{STYLE_*}} already are. A package build bakes
    in the installed path, a developer's run bakes in the checkout, and
    neither has to be told which.

    Only the SYSTEM root is baked in. The user root deliberately stays a
    run-time default in the artifacts: it follows XDG_CONFIG_HOME, which
    an artifact can read for itself and which may legitimately differ
    between generating and running.
    """
    root = os.environ.get("ZEPOS_SYSTEM_ROOT")
    if not root:
        # This module lives IN the system root, so its own directory is
        # the answer whenever the generator did not pass one.
        root = str(Path(__file__).resolve().parent)
    return {"ZEPOS_SYSTEM_ROOT": root}


class ConfigProcessor:
    """Processes configuration files carrying icon placeholders."""

    def __init__(self, icons: Dict[str, str] = None, styles: Dict[str, str] = None,
                 paths: Dict[str, str] = None):
        self.icons = icons or ALL_ICONS
        self.styles = styles or STYLE_VARIABLES
        self.paths = paths if paths is not None else path_variables()

    def create_template(self, config_path: Path, output_path: Path = None) -> Path:
        """Builds a template with placeholders out of a configuration file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Config nicht gefunden: {config_path}")
            
        content = config_path.read_text(encoding='utf-8')
        replacements = 0
        
        # Replace every known icon with its placeholder
        for key, icon in self.icons.items():
            if icon in content:
                content = content.replace(icon, f"{{{{{key}}}}}")
                replacements += 1
        
        # Determine the output path
        if output_path is None:
            output_path = config_path.with_suffix('.template')
            
        output_path.write_text(content, encoding='utf-8')
        print(f"✓ Template erstellt: {output_path} ({replacements} Icons ersetzt)")
        
        return output_path
    
    def apply_template(self, template_path: Path, output_path: Path = None) -> Path:
        """Applies icons and styles to a template."""
        if not template_path.exists():
            raise FileNotFoundError(f"Template nicht gefunden: {template_path}")
            
        content = template_path.read_text(encoding='utf-8')
        
        # Find every placeholder
        placeholders = re.findall(r'\{\{([A-Z0-9_]+)\}\}', content)
        applied = 0
        missing = []
        
        # Replace icon placeholders
        for placeholder in set(placeholders):
            if placeholder.startswith('ICON_'):
                # Membership, not get_icon()'s return value. Its fallback
                # is "?" - a perfectly printable character - so it can
                # never equal the "[NAME]" sentinel this branch used to
                # compare against, and the branch therefore never fired.
                # Twelve placeholders had been rendering as a literal "?"
                # in shipped configuration because of it.
                icon = self.icons.get(placeholder)
                if icon and icon != UNRESOLVED_ICON:
                    content = content.replace(f"{{{{{placeholder}}}}}", icon)
                    applied += 1
                else:
                    missing.append(placeholder)
            elif placeholder.startswith('STYLE_'):
                # Replace style placeholders
                if placeholder in self.styles:
                    content = content.replace(f"{{{{{placeholder}}}}}", self.styles[placeholder])
                    applied += 1
                else:
                    missing.append(placeholder)
            elif placeholder.startswith('ZEPOS_'):
                # Replace path placeholders
                if placeholder in self.paths:
                    content = content.replace(f"{{{{{placeholder}}}}}", self.paths[placeholder])
                    applied += 1
                else:
                    missing.append(placeholder)

        # Any placeholder the SSOTs did not define also counts as
        # unresolved: the regex above only finds {{NAME}} shapes, so a
        # name outside the three known prefixes is a typo nobody defined
        # either, and it survives into the output exactly the same way.
        missing.extend(
            p for p in set(placeholders)
            if not p.startswith(('ICON_', 'STYLE_', 'ZEPOS_'))
        )

        # Checked BEFORE anything is written. This used to be a warning
        # for icons and styles, printed after the file had already been
        # written: the run reported success, the user restarted their bar
        # and found a broken theme, and nothing in the log said why.
        if missing:
            raise UnresolvedPlaceholders(
                f"{len(missing)} placeholder(s) no SSOT defines: "
                + ", ".join(sorted(set(missing)))
                + f" (in {template_path}). The existing configuration was"
                " left unchanged."
            )

        # Determine the output path
        if output_path is None:
            output_path = template_path.with_suffix('')
            if output_path.suffix == '':
                output_path = output_path.with_suffix('.conf')

        output_path.write_text(content, encoding='utf-8')
        print(f"✓ Config generiert: {output_path} ({applied}/{len(set(placeholders))} Platzhalter angewendet)")

        return output_path

def main():
    parser = argparse.ArgumentParser(
        description="Template processor for ZepOS configuration files"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Verfügbare Befehle')
    
    # Create a template
    template_parser = subparsers.add_parser('template', 
                                           help='Erstellt ein Template aus einer Config')
    template_parser.add_argument('config', type=Path, 
                                help='Input Config-Datei')
    template_parser.add_argument('-o', '--output', type=Path, 
                                help='Output Template-Datei')
    
    # Apply a template
    apply_parser = subparsers.add_parser('apply', 
                                        help='Wendet Icons auf ein Template an')
    apply_parser.add_argument('template', type=Path, 
                             help='Template-Datei')
    apply_parser.add_argument('-o', '--output', type=Path, 
                             help='Output Config-Datei')
    
    # List icons. Ohne --group: die drei Gruppen, die der Schalter
    # anbot, waren dreimal dieselbe Sammlung - siehe icons_db.py.
    subparsers.add_parser('list', help='Listet Icons')
    
    # Show a single icon
    show_parser = subparsers.add_parser('show', 
                                       help='Zeigt ein spezifisches Icon')
    show_parser.add_argument('name', 
                            help='Icon-Name')
    
    args = parser.parse_args()
    
    # Run the requested command
    if args.command == 'template':
        processor = ConfigProcessor()
        try:
            processor.create_template(args.config, args.output)
        except Exception as e:
            print(f"Fehler: {e}")
            sys.exit(1)
            
    elif args.command == 'apply':
        processor = ConfigProcessor()
        try:
            processor.apply_template(args.template, args.output)
        except Exception as e:
            print(f"Fehler: {e}")
            sys.exit(1)
            
    elif args.command == 'list':
        icons = ALL_ICONS
        print(f"=== Alle Icons ({len(icons)}) ===")
        
        for key, icon in sorted(icons.items()):
            print(f"{key:30} {icon}")
            
    elif args.command == 'show':
        icon = get_icon(args.name)
        print(f"{args.name}: {icon}")
        
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Silently handle broken pipe (e.g., when piped to head/tail)
        sys.stderr.close()
        sys.exit(0)