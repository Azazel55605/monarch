# Phase 4 implementation and evidence

Date: 2026-11-23. Scope: Qt appearance and M4.1–M4.3.
Package: `0.1.0.dev4`. Milestone: profile beta within the existing basic monitor contract.

## Delivered behavior

Profiles provide observed/draft capture, create/update/rename/delete, versioned
private atomic storage, original backups on schema-1 migration, and strict data-only import/export.
The Qt selector supports draft loading and guarded quick switching. Physical
identity matching survives unique-serial connector changes, refuses missing/extra
outputs and offers explicit per-load mappings for twins or absent serials. Mappings
remain identity-checked and one-to-one. Unadvertised modes are not substituted.

CLI catalog commands work offline. Keybinding-style switches open visible GUI
confirmation; terminal switches require an interactive terminal and use the shared
Keep/Revert helper. The optional tray surfaces the same editor and guard. Profile
storage locks and compositor transaction locks serve different purposes: catalog
edits cannot corrupt each other, and multiple entry points cannot run simultaneous
monitor transactions. Profiles never imply save-on-login or automation.

Qt appearance preserves native widget rendering/fonts/palettes, discovers installed
same-major/minor theme/style plugin roots, lists available QStyleFactory styles and
remembers a per-app selection. A missing saved style falls back with a notice.
Explicit session theme/style variables remain effective.

## Automated/package checks

| Layer | Result |
| --- | --- |
| Python 3.13.12, development environment | 166 tests passed |
| Python 3.12.16, installed GUI wheel | 166 tests passed; installed wheel |
| Python 3.14.10, installed GUI wheel | 166 tests passed; installed wheel |
| Ruff / formatting / strict mypy | Passed; 37 typed source files |
| Wheel / source distribution | Built successfully |

Offscreen Qt tests are distinct from native
Wayland acceptance. Coverage includes catalog CRUD, no-clobber exports, import
conflicts, private permissions, locks/external-edit conflicts, migration backups/future schemas,
malformed data, control characters, unique/absent/duplicate serials, changed modes,
missing/extra outputs, explicit mappings, real profile GUI confirmation and client
close, GUI/CLI races, native-style fallback/selection, and PTY profile Keep/persistence.

## Native acceptance

Command: `uv run --extra gui --group gui-dev python tools/probe_profiles.py`.
The probe creates a new nested compositor, verifies its Wayland backend and signature,
and changes only virtual outputs. It saves three generic profiles (Desk,
Presentation and Portrait), exports/imports them, then uses the production GUI,
worker, coordinator, storage and independent guard.

Observed on Hyprland 0.57.2 with PySide6/Qt 6.12.0:

- qt6ct-style active, with Kvantum, Breeze and other installed styles discoverable.
- Three saved profiles exported/imported; explicit virtual-identity mappings used.
- Presentation kept; Portrait reverted, then kept and persisted.
- Actual tray menu action surfaced visible GUI confirmation with persistence off.
- Closing that preview restored the previous Portrait layout.
- A real CLI process with a PTY switched to Desk and required typed Keep.
- Compatible tray host detected; no parent monitor mutations.

The synthetic screenshot is [themed profile editor](assets/monarch-profiles.png).
Qt emitted empty-font-description and Wayland text-input focus diagnostics; the
listed interactions completed. These are not claims that every theme setting or
host panel interaction was checked.

An initial variant disabled MONARCH-B in Presentation and timed out in hyprctl
while attempting the next profile. The exact cause has not been established.
The default successful probe keeps both virtual outputs enabled; the earlier
variant remains reproducible with `--cycle-disabled-output`. Native disable/re-enable
cycling is therefore **not certified** by the passing run. Automated profile tests
cover enabled-state data and guarded rollback independently.

Physical mode switches,
real dock/resume behavior and the broader hardware release matrix remain untested.
A tray menu action test is distinct from desktop panel integration.

The existing recovery probe's generated client script had a malformed declaration
introduced during the Phase 3 helper refactor. This change restores `async def run()`;
that correction does not change the production recovery implementation. The full
native recovery probe subsequently passed preview Revert, deadline, client EOF and
SIGKILL, explicit persistence, failed persistence reload, virtual hot-unplug degraded
recovery, and guard-SIGKILL manual recovery. Parent monitor mutations remained zero.

## References and limits

[Qt QStyleFactory](https://doc.qt.io/qt-6.12/qstylefactory.html) supplies the available
style list; [Qt platform integration](https://doc.qt.io/qt-6/qpa.html) owns platform
themes; [Qt QSystemTrayIcon](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html)
describes tray-host requirements. Loading a compatible style here is not validation
of every system theme/plugin combination.

The Phase 3 basic-config/reload ownership contract still applies. Advanced
HDR/VRR/color controls, automatic switching, background lifecycle, autostart and
release packaging remain later phases. Explicit mappings must be reviewed on each
ambiguous load; profiles are never automatically rebound based on connector names.
