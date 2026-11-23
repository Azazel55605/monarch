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
distro Python 3.14. [Hosted CI](https://github.com/Azazel55605/monarch/actions/runs/45219136187)
on `155bd79` passed all 231 tests on Python 3.12, 3.13 and 3.14, plus the
Arch package build/install/removal job. All four candidate artifacts uploaded.
The downloaded Arch candidate and Python artifacts passed SHA-256 verification;
its application modules/resources match the payload used for the native checks.
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
versions accompany the evidence. The local clean builder resolved Python
3.14.10-1, PySide6 6.12.0-3, qt6-base 6.12.0-5, qt6-svg 6.12.0-1,
Hyprland 0.57.2-1 and namcap 3.6.0-3. No bit-for-bit reproducibility or signed-package
claim is made; SHA-256 manifests identify the concrete artifacts.

The clean environment runs the complete test suite through PKGBUILD `check()`,
validates the installed desktop entry/icon/help and Qt-free diagnostics, and then
removes the package. It checks application module/command/desktop/icon removal and
retention of separate user-data markers. No application install/remove hook edits
user Lua, profiles, journals or autostart. Manual integration cleanup and recovery
precautions are documented rather than hidden in a package-removal script.

## Native candidate results

The extracted Arch payload imported from its staged system site-packages (not
the checkout), using system Python 3.14.10 and PySide6 6.12.0. A native Wayland Qt
window, desktop ID, rendered icon and both offline help/notices documents passed;
the standalone UI check started no monitor worker. No host package was installed
and no parent monitor setting was changed.

The full packaged nested-compositor probe is **not a pass**: one attempt timed
out creating a headless output; a retry passed basic guarded apply/revert and then
timed out during mirror application (`apply_failed`, hyprctl timeout). This is
recorded as an unresolved virtual/native acceptance result, alongside the earlier
Phase 4 disable/re-enable timeout. Prior Phase 6 mirror success does not certify
this candidate run. Do not claim the complete native matrix or stable gate closed.

Clean Arch makepkg/check, actual pacman install, installed command/help/icon/Qt/
diagnostics, and pacman removal all passed. Application files were removed while
external simulated user data remained. Namcap reports no packaging errors after
the hicolor dependency correction; remaining warnings are retained for review.

## Packaging review

Namcap detects the required hicolor theme hierarchy dependency; it is explicitly
declared and packaging errors now fail the container check. Its remaining static
Python warnings refer to imported Monarch symbols inside the installed package,
the interpreter constraint, and dynamically loaded Qt SVG/Hyprland usage. These
are checked by installed runtime execution; the unfiltered report accompanies the
package. No warning is presented as a clean static report.

## User feedback — 2026-11-23

User testing confirms system theme, icon/tray, offline help, display discovery,
diagnostics and the status banner work in the target desktop session. This is
user-reported native-session evidence, separate from automated/container results;
it does not establish package installation provenance or fresh-login acceptance.

The reported blocker is inability to apply layout edits with existing advanced
state. Two supplied observation snapshots show 8-bit XRGB8888 and sRGB; one has
active VRR, the other has inactive VRR and advertised HDR metadata. Active VRR is
a confirmed blocker in the current guard. HDR metadata alone is not a blocker,
and these screenshots do not establish every SDR parameter checked by the guard.

Clarification confirms that Set up monitor management and Preview changes are
greyed out. Both use the same advanced-state blocker. This prevents the normal
setup/apply workflow even though basic draft controls are enabled independently
of write readiness. Physical Keep/Revert, persistence, docking,
resume and startup acceptance remain untested. The follow-up investigation is
preserving existing VRR policy through basic edits and recovery, rather than
requiring the user to turn it off or simply removing the recovery gate. No
advanced write support or hardware rollback validation is implied by this report.

## Remaining gates and known limits

The Phase 5 physical dock/resume/fresh-login gate remains open. Phase 6 advanced
writes remain explicitly deferred. Current active VRR/10-bit/HDR or unknown required
state can block basic application; packaging does not override that gate or reset
those settings. The Phase 4 virtual disable/re-enable timeout remains recorded.

Physical mode switches, actual menu/login behavior, and the broader GPU/recovery
matrix still need acceptance; the target-session tray and startup UI checks above
are confirmed separately. Candidate availability
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
