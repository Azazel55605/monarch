# Phase 3 implementation and evidence

Date: 2026-11-23. Scope: M3.1–M3.4. Package: `0.1.0.dev3`.
Milestone: native Qt manual-editor alpha.

## Implementation

The optional PySide6 GUI provides a proportional graphics canvas, edge snapping,
keyboard/numeric positioning, connected/disabled/missing display states, advertised
mode/refresh choices, scale, transforms and mirroring. The draft model is independent
of Qt and keeps observed, edited and stale state separate. Unknown current modes
are not silently substituted, and unrelated edits preserve scale precision.

Compositor discovery, event watching, integration I/O and the asynchronous coordinator
run on a dedicated worker thread. The GUI thread only renders and handles input.
Discovery pauses for the complete guarded transaction, including startup application.
The Keep/Revert dialog displays the guard's deadline; controls lock during previews.
Closing or killing the client retains the independent recovery behavior from Phase 2.

Desktop setup previews the root diff and baseline before approval. It appends one
managed include, pins the reviewed root and operator-declared dependencies, preserves
root mode/unrelated bytes, keeps private backups, and requires explicit re-review
after changes. Re-review detects concurrent monitor/manifest edits. The transaction
pins a registration fingerprint, so replacing a contract cannot authorize old recovery.

This deliberately supports reviewed **basic** monitor configuration. It does not
semantically parse arbitrary Lua, discover its complete dynamic import closure,
preserve arbitrary advanced rule semantics, or promise that user code is deterministic.
The operator delegates monitor control and approves executing reviewed config on reload.
See the [integration guide](phase-3-guide.md) for the exact contract.

## Automated and package evidence

| Layer | Result |
| --- | --- |
| Python 3.13.12, development environment | 141 passed |
| Python 3.12.16, installed wheel with GUI | 141 passed; installed `monarch --version` reports dev3 |
| Python 3.14.10, installed wheel with GUI | 141 passed; installed `monarch --version` reports dev3 |
| Ruff / strict mypy | Passed, including GUI code and Qt stubs |
| Source distribution / wheel | Built successfully |

New coverage includes real drag events, repeated UI/model updates, arrow-key/numeric
parity, invalid and all-disabled layouts, mode/refresh/transform/mirror controls,
nonterminating scale precision, unsupported observed modes, dirty/stale hotplug,
countdown and explicit confirmation, dark palette rendering, reviewed integration,
concurrent source/monitor changes, config search ordering, worker startup/close and
GUI-close rollback through an actual independent guard with synthetic transport.
The prior recovery/subprocess/PTY suite remains included.

Qt automated tests run with `QT_QPA_PLATFORM=offscreen`; they do not certify Wayland
placement or physical monitor changes. Hosted CI is tracked separately from local
results, including its Qt installation and package build steps. The first hosted
run exposed missing `libEGL.so.1` on the Ubuntu runner before test collection;
the workflow explicitly installs the Qt graphics libraries. Local Arch checks
were unaffected.

## Native Qt/Wayland acceptance

Command: `uv run --extra gui --group gui-dev python tools/probe_gui.py`.
The probe starts its own Hyprland 0.57.2 using a default XDG root, verifies the nested
Wayland backend/new signature, creates two virtual outputs and runs the actual GUI.
It uses PySide6/Qt 6.12.0 with the production worker, coordinator, guard and storage.
The test host is Arch-based Linux with hybrid AMD/NVIDIA graphics; render access
outside the sandbox was required.

Observed checks:

- Reviewed desktop include installation and pinned dependency registration.
- GUI Keep with real persistence and observed matching output state.
- A second GUI preview followed by Revert and observed restoration.
- Two native outputs configured at 1.25× and 1.5×, with a rotated output.
- Native per-output identification windows, with placement checked after mapping.
- Dirty draft preserved and apply disabled after actual virtual hot-unplug.
- Clean worker/application shutdown without leaving an active preview.
- Zero parent monitor mutations.

Qt reported integer screen DPR 2.0 for both outputs while the editor window's DPR
was 1.25; the compositor settings were 1.25 and 1.5. This is not treated as a failed
fractional-scale observation: Qt documents that screen and window DPR can differ
on Wayland and recommends using the window value for a target window.
[Qt QScreen documentation](https://doc.qt.io/qt-6/qscreen.html#devicePixelRatio-prop).

The visible placement check caught a genuine identification issue: creating each
native handle and setting its screen/transient parent explicitly was needed to
place labels on different outputs. The final probe checks actual mapped screens,
not merely the number of created widgets. A public screenshot contains synthetic
output names only: [editor image](assets/monarch-editor.png).

Qt emitted text-input focus diagnostics during dialog transitions and passive-window
activation diagnostics during identification; the tested interactions and shutdown
completed. These logs are not presented as proof of physical input/platform coverage.

## Physical desktop read-only check

A separate native `wayland` GUI startup discovered three connected physical outputs,
reported an unmodified draft, and closed cleanly. Dimensions, scale, transform,
position and enabled state were compared before and after; they were unchanged.
No integration was installed and no preview was requested on that desktop.
This is startup/discovery evidence, not physical modesetting acceptance.

## Verified reload semantics

Tagged [Hyprland reload code](https://github.com/hyprwm/Hyprland/blob/v0.57.2/src/ipc/s1/Commands.cpp)
keeps the cached config path on ordinary reload and flushes it on `full-reset`.
The default-path guard uses that explicit full reset so the reviewed XDG target
is selected. Explicit paths use ordinary reload. The resolver follows
[hyprutils 0.14.3](https://github.com/hyprwm/hyprutils/blob/v0.14.3/src/path/Path.cpp)
and [0.14.4](https://github.com/hyprwm/hyprutils/blob/v0.14.4/src/path/Path.cpp).
Other library versions keep XDG write verification disabled; explicit known paths
retain their existing policy. Debug/custom build flags do not claim the clean baseline.

## Limits and next phase

Phase 3's native Qt/mixed-output gate is met within the basic registered-config
contract. Physical mode switches, real dock/resume behavior, advanced HDR/VRR/color,
symlinked/dynamic config graphs, and hardware/compositor crash recovery remain
outside this alpha's acceptance. The broader release matrix remains open.
Phase 4 adds named profiles, import/export and fast switching; it is not implemented
or represented by placeholder GUI controls here.
