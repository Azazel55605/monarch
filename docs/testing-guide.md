# Testing the 0.1.0rc6 candidate

This candidate is for installation and user feedback. It is not a tagged stable
release, a PyPI publication, or an AUR submission. Physical docking/resume/login
acceptance and physical VRR verification remain open; other advanced writes are deferred. The candidate nested probe
also hit virtual-output creation/mirror timeouts; see the [evidence report](phase-7-report.md).

## Install on Arch/Garuda

The package uses distro Python and PySide6/Qt instead of bundling Qt wheels.
Update the system through its normal package-management workflow before building.
Before upgrading an existing installation, use Quit Monarch from each running
tray instance. Reopen after installation to load the new version. From a checkout:

```sh
sudo pacman -S --needed base-devel python-build python-installer python-hatchling python-pytest python-pytest-qt pyside6 qt6-svg hicolor-icon-theme hyprland desktop-file-utils
uv build --out-dir dist/candidate
python tools/build_arch_package.py --sdist dist/candidate/monarch_displays-0.1.0rc6.tar.gz
sudo pacman -U dist/arch/monarch-displays-0.1.0rc6-1-any.pkg.tar.zst
```

Review `packaging/arch/PKGBUILD.in` and the generated `dist/arch/PKGBUILD` first.
The helper pins the actual source archive SHA-256, builds as the current non-root
user in a temporary path without spaces, runs the full checks, and copies the
package plus recipe/source metadata to `dist/arch`. It does not install packages,
use sudo, disable tests, or change the pacman database by itself. If dependencies
are missing, makepkg stops; install them explicitly before retrying.

A built testing package is also available in the CI `arch-candidate-<commit>`
artifact on a successful [Checks run](https://github.com/Azazel55605/monarch/actions).
Artifacts are retained for 14 days and may require GitHub sign-in to download.
Extract it, enter its `arch` directory, verify `sha256sum -c SHA256SUMS`, review the
included manifest/recipe, then use `sudo pacman -U` on its package. Its `arch-source`
directory contains the source archive and matching PKGBUILD for rebuilding.
Checksums detect changes; they are not package signatures or a release attestation.

Arch Python minor upgrades require rebuilding local Python packages; do not reuse
an old binary package after the distro changes its Python installation layout.
The tested native dependency stack is recorded in the Phase 7 report. On tested
Qt 6.12, the Wayland platform plugin is supplied by qt6-base (a pyside6 dependency),
and the SVG icon plugin by qt6-svg. A distro package upgrade can change that layout.

The launcher appears as **Monarch** in the application menu, with the editor and
tray enabled. Closing hides to the tray when a host is available; Quit Monarch
exits. Use `monarch gui --no-tray` for exit on close. Terminal launch is `monarch gui --tray`. It matches Qt's Wayland app ID
and includes an original SVG icon. Installing does not enable startup or automation.

## Alternative: isolated Python installation

For testing without a system package, create a virtual environment and install
this checkout's built wheel:

```sh
python -m venv /path/to/monarch-test
/path/to/monarch-test/bin/python -m pip install 'dist/candidate/monarch_displays-0.1.0rc6-py3-none-any.whl[gui]'
/path/to/monarch-test/bin/monarch gui --tray
```

This uses separately supplied PySide/Qt wheels. Desktop assets live under that
virtual environment's prefix and are not automatically installed into the global
application menu. The Arch package is the recommended native test path for this
project. Do not install both variants into the same Python environment or use
`sudo pip` over distro Python.

## Test in stages

1. Start without applying anything. Check theme, icon/tray, help, display discovery,
   diagnostics, and the status banner. Reopening the app must not apply settings.
2. Follow the [VRR guide](vrr-guide.md) for initial Off-baseline migration, per-monitor
   Off/On, Preview → Revert and Preview → Keep. With Save on login checked, verify
   the per-monitor policy after a fresh login separately. Conditional VRR, HDR,
   depth/color/ICC and unknown required state remain outside supported writes.
3. Exercise draft editing and profiles: canvas/numeric parity, snapping, scale/mode/
   rotation/mirror validation, capture observed vs edited, import/export and dirty
   drafts. Catalog changes alone must not apply a display layout.
4. On a verified, explicitly owned basic configuration only, test Preview → Revert,
   Preview → Keep, timeout, explicit Quit/client loss, and explicit Save on login. Verify both
   visible output state and saved configuration. Keep a way to reach another session
   for manual recovery; compositor/GPU failure is outside software-timeout guarantees.
5. Test manual/tray/keybinding profile switching and identity/missing-display prompts.
6. Opt in to Automation only after manual recovery works. Test eligible exact/subset
   matches, tie/no-match preservation, unknown extras, manual pin/resume, and repeated
   docking/undocking. Every automatic preview must still show Keep/Revert.
7. Separately opt in to login startup, verify it through the session's actual startup
   host and test disabling it again. Plain Hyprland does not itself guarantee an XDG
   autostart runner. Suspend/resume and physical docking remain hardware acceptance.

Use Help → Quick start and recovery or `monarch help` offline. Detailed contracts:
[editor](phase-3-guide.md), [profiles](phase-4-guide.md), [automation](phase-5-guide.md),
and [advanced state/diagnostics](phase-6-guide.md). Follow their ownership and conflict
rules; do not silently adopt arbitrary Lua or overwrite changed config sources.

## Feedback

Send the candidate version/package source, generic display count/topology, exact
steps, expected vs actual result, and whether Keep/Revert and recovery worked.
State whether evidence is offscreen, nested Wayland, or physical hardware. Include
which acceptance step failed and any reproducibility/timing details.

Attach a reviewed `monarch diagnose` report or use Help → Redacted diagnostics.
Reports omit names/serials/paths/config contents, but geometry and capabilities remain.
Never attach raw EDID, private Lua, raw logs or credentials by default. The GitHub
bug form follows this structure. Feedback can also be given in the ongoing project
conversation. Advanced feature priorities can be selected after this test cycle;
VRR Off/On is now implemented; conditional VRR and other advanced writes remain deferred.

## Remove or reinstall

1. Resolve a pending preview/recovery while Monarch is still installed. Inspect
   `monarch transaction status`, use current-session `monarch recover` if needed,
   and preserve foreign-session journals for manual review.
2. Disable automation and any explicitly installed startup entry:
   `monarch automation disable` and `monarch automation autostart disable`. Close
   every Monarch instance using Quit Monarch in the tray so no watcher remains.
3. Remove only the application package: `sudo pacman -R monarch-displays`.
   Its command, desktop entry, icon, code, notices and packaged help are removed.
   User profiles, Lua integration, backups and recovery data are retained.

The generated Lua module is independent of the Python package and can stay loaded
at login. If removing integration too, review/remove only its marked include block
before deleting the referenced module. Restore earlier monitor rules from the
reviewed private backup as appropriate; do not overwrite a newly edited whole root
with a stale backup. Never delete journals to clear an error. Reinstall the same
candidate before attempting recovery if the application was already removed.

For a virtual environment, use its Python's pip to uninstall monarch-displays, or
remove that dedicated environment after the same startup/recovery steps. Those
operations do not remove external user config data. No uninstaller runs a raw reload
or automatically changes a monitor layout.


To test the new tray controls, click the tray icon once for the profile picker.
Open **External displays**, choose the external and reference displays, then
choose an extend direction or **Duplicate**. The editor opens for Keep/Revert.
You can also open both panels from the tray context menu. A double-click opens
the full editor. Directions that overlap another independent display are refused.

In **Automation**, enable automatic display previews and mark the profiles that
should load for each setup. Optionally enable **Use the best advertised mode for
new external displays**. Eligible profile matches take priority. When there is
no eligible match, the fallback handles newly seen external displays absent
from the owned baseline and unrecognized by the profile catalog. It extends them
to the right and ranks modes by pixel area, then refresh rate. A saved display
with no eligible profile and a tie between eligible profiles retain their
current settings. Keep applies the automatic suggestion for this session.


Use `monarch quick` to open the profile panel from a terminal, or
`monarch quick --external` for the Extend/Duplicate bar. If Monarch is running
in the current Hyprland session, the command opens the panel in that instance.

Hyprland 0.57.2 Lua keybind examples:

```lua
hl.bind("SUPER + P", hl.dsp.exec_cmd("monarch quick"))
hl.bind("SUPER + SHIFT + P", hl.dsp.exec_cmd("monarch quick --external"))
```

The panels size themselves to their contents and Hyprland floats them by default.
If your existing window rules force tiling, add a more specific rule:

```lua
hl.window_rule({
    name = "monarch-quick-panels",
    match = {
        class = "^org[.]monarch[.]Monarch$",
        initial_title = "^(Monarch quick controls|External display layout)$",
    },
    float = true,
    center = true,
})
```
