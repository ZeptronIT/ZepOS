<!--
Thanks for the change. CONTRIBUTING.md has the three non-negotiable rules;
the short version is: edit templates, never generated files; no hardcoded
values a placeholder could carry; do not weaken a guard to get green.
-->

## What this changes

<!-- One paragraph. What was wrong or missing, and what it does now. -->

## How you know it works

<!--
A measurement, not an intention. A test name, a command and its output, a
byte count, a boot you watched. "Should fix it" is not an answer this
project accepts of itself either.
-->

## Checklist

- [ ] `.venv/bin/python -m pytest` passes
- [ ] No generated file was edited by hand — the change is in the template or in one of the SSOTs (`brand.py`, `sizes.py`, `style_definition.py`, `icon_definition.py`)
- [ ] No colour, size or path was hardcoded where a `{{STYLE_*}}` / `{{ICON_*}}` placeholder belongs
- [ ] New source files carry `SPDX-License-Identifier: GPL-3.0-or-later`
- [ ] No key material, build output, screenshot or machine-specific value is in the diff

If the change touches one of these, tick the ones you ran:

- [ ] `packaging/` — `./packaging/build.sh <recipe>`, `./packaging/check-current.py`, `./packaging/verify-install.sh`
- [ ] `iso/` — `./iso/build.sh --profile release`, `./iso/test-boot.py --scenario release`
- [ ] User-visible strings — `./po/desktop/extract.sh` and/or `./po/build.sh`, both i18n test modules pass
- [ ] Nothing above applies

## Anything a reviewer should be sceptical about

<!--
Optional, and the most useful field on this form. What you are unsure of,
what you could not measure, what you chose against and why.
-->
