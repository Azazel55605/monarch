# Phase 7 packaging and testing handoff

Date: 2026-11-23. Version: `0.1.0rc1`.
Software packaging is delivered for testing. Physical/user acceptance keeps the
release gate open; no stable release tag, GitHub Release, PyPI upload or AUR submission
is performed by this phase's candidate handoff.

## Delivered

- Original MIT SVG icon, desktop launcher and matching Qt Wayland app ID; the tray
  uses the application's own icon while retaining normal Qt theme behavior.
- Bundled offline quick-start/recovery help and dependency notices in Qt Help and
  `monarch help`. The wheel installs desktop/icon/license/doc data under its prefix.
- Source/wheel candidate, changelog, checksum verification, generated source-pinned
  PKGBUILD, source manifest and native package. The recipe follows the PEP 517
  python-build/python-installer approach and uses distro pyside6/Qt rather than
  vendoring Qt wheels. Generation does not assume a future tag/remote release asset.
- CI artifact uploads for the Python matrix and a clean Arch package/build/install/
  removal job. Artifacts are candidate snapshots with limited retention, not releases.
- [Testing/feedback/removal guide](testing-guide.md) and [release checklist](release-checklist.md).

## Validation layers

Local validation: all **231 tests pass** on Python 3.13.12, with Ruff formatting/
lint and strict mypy (49 source files). Source/wheel assets and checksums pass.
An isolated wheel install verifies command, help and shared desktop/icon assets,
then verifies their removal. The full clean Arch suite also passes 231 tests on
distro Python 3.14. Hosted and final native evidence are recorded below once run.
These layers stay separate:

1. Automated/offscreen tests and source/wheel asset checks.
2. Actual makepkg build/check, pacman install and removal inside a disposable clean
   official Arch image with dependencies resolved from its package repositories.
3. Native Qt/Wayland and guarded basic behavior using the built package payload in
   an isolated nested compositor on the host; this is not a host pacman installation.
4. User's installed-session and physical hardware acceptance, which remains pending.

The builder base is pinned to official Arch image digest
`sha256:d4594bb2300cba11f41c2f27923eb56f63d9988909c402f9c95517d1e362c899`.
Its package repositories roll forward, so the image digest alone does not make the
entire dependency set immutable. The actual package/build metadata and dependency
versions accompany the evidence. No bit-for-bit reproducibility or signed-package
claim is made; SHA-256 manifests identify the concrete artifacts.

The clean environment runs the complete test suite through PKGBUILD `check()`,
validates the installed desktop entry/icon/help and Qt-free diagnostics, and then
removes the package. It checks application module/command/desktop/icon removal and
retention of separate user-data markers. No application install/remove hook edits
user Lua, profiles, journals or autostart. Manual integration cleanup and recovery
precautions are documented rather than hidden in a package-removal script.

## Packaging review

Namcap detects the required hicolor theme hierarchy dependency; it is explicitly
declared and packaging errors now fail the container check. Its remaining static
Python warnings refer to imported Monarch symbols inside the installed package,
the interpreter constraint, and dynamically loaded Qt SVG/Hyprland usage. These
are checked by installed runtime execution; the unfiltered report accompanies the
package. No warning is presented as a clean static report.

## Remaining gates and known limits

The Phase 5 physical dock/resume/fresh-login gate remains open. Phase 6 advanced
writes remain explicitly deferred. Current active VRR/10-bit/HDR or unknown required
state can block basic application; packaging does not override that gate or reset
those settings. The Phase 4 virtual disable/re-enable timeout remains recorded.

Physical mode switches, the user's actual installed-session menu/tray/login behavior,
and the broader GPU/recovery matrix still need acceptance. Candidate availability
is not evidence that these gates passed. The next action is a proper user test and
feedback cycle, followed by evidence-driven advanced-feature work. v0.1.0 tagging
and publication wait for explicit authorization and an accepted checklist.

## Primary references

[Arch Python packaging guidance](https://wiki.archlinux.org/title/Python_package_guidelines)
describes building wheels and staging with python-installer. The
[Arch pyside6 package](https://archlinux.org/packages/extra/x86_64/pyside6/) supplies
native bindings. [Qt's desktop file identity](https://doc.qt.io/qt-6/qguiapplication.html#desktopFileName-prop)
and [Qt for Python notices](https://doc.qt.io/qtforpython-6/licenses.html) inform the
launcher/notices. [GitHub workflow artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data)
provide download retention, independent of GitHub Releases.
