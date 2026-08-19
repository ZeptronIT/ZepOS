# Security policy

## Reporting a vulnerability

**Please do not open a public issue.**

Report it privately through GitHub:
[**Report a vulnerability**](https://github.com/ZeptronIT/ZepOS/security/advisories/new).
That opens a private advisory visible only to you and the maintainers.

Useful things to include: which component (installer, package build, ISO
profile, a `zepos-*` command, the desktop shell), the version or commit,
what an attacker gets out of it, and the smallest reproduction you have.
A proof of concept is welcome; it is not a requirement.

ZepOS is maintained by a very small team. You will get an acknowledgement as
soon as a human has read the report, and an assessment after that. If the issue
is real we will agree a disclosure date with you rather than sitting on it.

## Supported versions

| Version | Supported |
|---|---|
| `main` | Yes |
| Tagged pre-releases | Only through the current `main` |

ZepOS is pre-release software. There is no long-term support branch and no
backporting; a fix lands on `main` and reaches users through the next build.

## Already known, and not a finding

These are documented properties of the current pre-release, not
vulnerabilities we are unaware of. Reporting them is not necessary; if you can
show one is *worse* than described here, that very much is.

- **A locally built medium is signed with your own key, not ours.** Since
  19.08.2026 the published packages carry a real release key:
  `FF2EB06C08A57FEA9E33FC46157C1725A578B80C`, user id
  `LeonMarzollDev (ZepOS Release)`, passphrase-protected, a certification
  primary with a separate signing subkey, expiring 2028-08-18. Its public half
  is served at `https://zeptronit.github.io/ZepOS/zepos-repo.pub` and ships in
  the `zepos-keyring` package, so an installed system trusts it without anyone
  importing anything by hand.
  If you build ZepOS yourself, `packaging/make-test-key.sh` still gives you a
  throwaway key that says `DO NOT TRUST` on purpose. A medium built that way is
  signed with a key whose private half sits in your own working directory —
  treat it as unsigned. `packaging/publish.sh` refuses to publish such a tree,
  and there is no override.
- **The boot chain carries no Secure Boot signatures.** Measured: firmware with
  Secure Boot enabled rejects the loader. Installing requires disabling Secure
  Boot. `iso/README.md` records the measurement and the three possible routes
  out of it.
- **The update path is young.** Installed systems point at
  `https://zeptronit.github.io/ZepOS/$arch`, which has served the signed
  repository since 19.08.2026. That it works was measured the same day in a
  container against the live URL: `pacman -Sy` fetched the database, verified
  its signature against the published key, and installed a package. What has
  *not* been measured is a delivery under load, over months, or a key
  rollover — none of that has happened yet, because nothing has been in the
  field long enough.
- **The smoke-test ISO profile (`iso/profile/`) deliberately contains a known
  root password, an autologin and an unattended answer file.** It is a
  measuring harness and must never be handed to anyone.
  `iso/shared-with-release.txt` is the allow-list that keeps its files out of
  the shipping image, and it is an allow-list precisely so that this mistake
  produces a failed build rather than a quiet leak. A route by which harness
  content reaches `iso/profile-release/` **is** a finding.

## Scope

In scope: this repository — the installer, the package recipes, the ISO
profiles, the configuration generator and the templates it expands, and the
programs under `src/`, `lock/`, `logout/`, `menu/`, `settings/` and `plugins/`.

Out of scope: vulnerabilities in Arch Linux, Hyprland, `archinstall`, GTK or
any other upstream project — report those to their maintainers. If ZepOS ships
a *configuration* of an upstream component that is insecure, that is in scope
and we want to hear about it.
