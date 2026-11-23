# Profiles, quick switching and Qt appearance

Phase 4 reference. Opt-in matching is now described in the [Phase 5 guide](phase-5-guide.md).

Run the editor with `uv run --extra gui monarch gui`. Profiles are data snapshots;
saving, renaming, importing, deleting or loading one into the editor does not apply
monitor settings. Automatic topology selection remains Phase 5.

## Qt appearance

Monarch uses native Qt widget rendering, fonts and palettes. **Appearance → System
theme** follows the session's Qt platform theme, including `QT_QPA_PLATFORMTHEME`
(such as `qt6ct`) and `QT_STYLE_OVERRIDE`. Before creating QApplication, Monarch
also searches conventional system Qt 6 plugin roots for theme/style plugins whose
metadata matches the runtime's Qt major/minor version. Explicit Qt plugin paths
remain available. Qt still decides whether an individual plugin can load.

The Appearance menu lists styles actually reported by `QStyleFactory`, such as
Kvantum or Breeze when installed and loadable. Selecting a style takes effect
immediately and is remembered using Qt's user settings (`Monarch/Monarch.conf`
under the Qt config location on Linux). Selecting System theme restores the
startup style and palette. An unavailable saved style falls back to the current
system theme with a notice. Platform-theme/environment changes require restarting
the app; changing a widget style does not edit global qt6ct/Kvantum settings.
Monarch does not install themes or force a global light/dark palette.

A PySide wheel and a distro Qt installation can use different Qt versions.
Unmatched system plugin trees are not automatically added. If only Fusion and
Windows appear, check the Qt version used by the running Python environment;
installing a theme for another Qt version does not make it compatible.

## Save and manage profiles

The Profiles menu offers:

- **Save observed layout as…**: freshly inspect the compositor and capture what is
  actually running, independently of unsaved editor changes.
- **Save edited layout as…**: save the structurally valid draft exactly as shown,
  without applying it. Unsupported/stale settings can still fail live validation
  when the profile is later loaded.
- **Update selected from edited layout…**, **Rename selected…**, and
  **Delete selected…**: explicit actions on the selected saved profile.
- **Import profiles…**, **Export selected…**, and **Refresh profiles**.

Use **Load to editor** to inspect or change a saved layout. Dirty edits require
explicit discard before replacement. **Switch profile…** loads, validates and
starts a guarded preview. Keep/Revert, timeout and client-loss rollback are the
same as manual edits. **Save on login** only persists compositor configuration
after Keep; a saved profile alone never changes the startup configuration.
Existing [desktop integration requirements](phase-3-guide.md) still apply.
After docking or a connector change, explicitly re-review integration to establish
the current recoverable baseline before switching. Profile identity resolution
does not authorize adopting an unknown runtime baseline or bypass the guard.

All connected outputs, including disabled ones, belong to a profile's topology.
A profile requires its exact connected physical set; missing or extra displays
block loading/switching. This prevents an imported layout from silently disabling
an unrecognized display. Capture another profile for a different connected set.

Unique make/model/serial identities survive connector renames. Without a usable
serial, automatic matching additionally requires a unique make/model and the
original connector. Duplicate serials, identical displays or a changed connector
without a stable serial require an explicit one-to-one mapping dialog. Every
choice is checked against the physical identity and current topology again;
mapping cannot override a different serial or an unadvertised mode. The bindings
apply to this load only and do not silently rewrite the saved profile.

## Storage and interchange

Profiles live in `$XDG_CONFIG_HOME/monarch/profiles.json` (default
`~/.config/monarch/profiles.json`). The directory is private, files are mode 0600,
updates are atomic, and cooperating GUI/CLI writers use a nonblocking file lock.
Hash checks also reject detected external edits before replacement; they are not
a filesystem compare-and-swap against an uncooperative writer at the rename instant.
Names are case-insensitively unique; up to 128 profiles and 32 outputs per layout
are supported. Unknown schemas, malformed fields, invalid layouts, symlinks and
insecure local storage are rejected.

Schema 2 has exactly `schema_version` and `profiles`. Each profile contains a
32-character hexadecimal UUID `id`, `name`, and the existing schema-1 `layout`.
The supported schema-1 interchange has entries containing `name` and `layout`;
its IDs are derived deterministically. Reading does not migrate files. The next
successful edit retains a private schema-1 backup and writes schema 2. Future schema versions are rejected unchanged.

Import validates the whole document before writing, assigns fresh local IDs, and
rejects name conflicts without partial import or replacement. Export writes a
new private JSON file and refuses existing targets. Explicitly selected import
files must be user-owned regular files, not group/world-writable or symlinked.
Exports contain monitor make/model/serial and connector names: review them before
sharing. Imports contain data only, never Lua or executable commands.

## CLI and keybindings

These operations need no Qt or running compositor unless they capture/switch:

```sh
uv run monarch profile list
uv run monarch profile capture Desk
uv run monarch profile save Presentation /path/to/layout.json
uv run monarch profile update Presentation /path/to/another-layout.json
uv run monarch profile rename Desk Office
uv run monarch profile export /path/to/new-profiles.json
uv run monarch profile import /path/to/profiles.json
uv run monarch profile delete Presentation
```

Use `profile --store /private/directory ...` to select another catalog. `profile
show NAME` prints full stored identities. Default list output includes names/IDs
only. Names or IDs may be used as selectors.

For Hyprland keybindings, invoke an installed `monarch` executable:

```sh
monarch profile switch Office
```

This opens the Qt editor, resolves the profile and presents visible Keep/Revert.
It never treats a keypress as Keep. The GUI retains the normal 15-second guard
window and offers the explicit mapping dialog if needed. `--directory` selects
owned/registered monitor storage; otherwise it is discovered. `--persist` opts
into save-on-login only after Keep. Multiple clients remain serialized by the
existing per-session guard lock, not by separate per-entry-point locks.

For terminal confirmation:

```sh
monarch profile switch Office --terminal --seconds 15
monarch profile switch Office --terminal --map OLD-DP=DP-2 --map OLD-HDMI=HDMI-A-1
```

`--terminal` requires a real interactive terminal and types `keep` to confirm.
Redirected input is rejected before mutation; use GUI confirmation for keybindings.
`--map` and `--seconds` belong to terminal switching. Revert/timeout returns exit
status 1; invalid requests return 2. A confirmed switch returns 0.

## Optional tray

Launch `monarch gui --tray` for a profile menu on a compatible system tray host
(such as a StatusNotifier tray). It offers Open Monarch, saved profiles and Quit.
Selecting a profile brings up the editor, clears save-on-login and starts the
normal mapping/confirmation flow. It never confirms or persists silently.
The tray is optional; closing the editor exits and hides its tray icon. It is not
a background watcher, autostart service, or automatic profile switcher. Without
a tray host the normal editor and CLI remain available.

See the [Phase 4 evidence](phase-4-report.md) and [progress tracker](progress.md).
