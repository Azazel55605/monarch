# Architecture and intended behavior

Status: proposed design. Phase 1 must validate backend assumptions before the
write path is implemented. See [research](compatibility.md) and the
[implementation plan](implementation-plan.md).

## Components

| Component | Responsibility |
| --- | --- |
| Domain | Immutable topology, display identities, modes, layouts, profiles, validation |
| Hyprland backend | Session/capability detection, JSON discovery, typed Lua generation, bounded commands, event stream |
| Apply coordinator | One serialized transaction for GUI, CLI, tray, and automation |
| Recovery guard | Separate process, monotonic deadline, durable recovery journal, rollback on client loss |
| Storage | Versioned JSON profiles/preferences, atomic replacement, migration and backups |
| Policy engine | Pure topology matching, priority, ambiguity handling, manual override |
| Qt presentation | Layout canvas, properties panel, profiles, transaction state, diagnostics |
| CLI/session agent | Quick switch commands, optional watcher, local authenticated control channel |

Use a `src/monarch/` package with `domain/`, `backends/hyprland/`, `services/`,
`storage/`, `ui/`, and `cli/` modules when implementation starts. Prefer standard
library facilities where sufficient. Python 3.12+ and PySide6/Qt 6 Widgets are the
initial choices. Use QProcess/Qt socket integration or bounded worker operations;
no blocking subprocess or socket reads on the GUI thread. Tests use pytest,
pytest-qt, recorded synthetic fixtures, and a fake backend. Phase 1 pins tool and
runtime dependencies after checking supported Arch packages.

## GUI workflow

The main window has a top profile selector, a central display canvas, a display
properties panel, and an Apply/Revert bar. Monitor rectangles reflect logical
size after scale and rotation; dragging supports edge snapping and alignment.
Numeric coordinates and keyboard controls offer the same actions without drag.
A selected monitor exposes enabled state, mode, refresh, scale, transform, and
mirror target. Unsupported controls explain why they are unavailable.

Show connected-but-disabled displays separately from missing displays referenced
by a profile. Keep observed, edited, and confirmed state distinct. Hotplug while
editing marks stale data and requires revalidation instead of silently dropping
edits. A visible pending-change state prevents confusing Save Profile with Apply.
Identification overlays, keyboard navigation, accessible labels, readable errors,
and light/dark system themes are part of the manual-editor milestone.

Hyprland does not need a generic desktop-style “primary monitor” abstraction for
this MVP. Workspace routing, if added later, must use explicit Hyprland semantics.

## Apply and recovery

1. Acquire a per-session transaction lock; re-read topology and config generation.
2. Validate settings, resolve monitor identity, reject missing required displays,
   mirror cycles, invalid modes/scales, and a layout with no usable output.
3. Capture restorable state, including relevant managed rules/files; write the
   recovery journal and arm an independent guard before the first mutation.
4. Apply a planned order that enables destinations before disabling sources.
   Commands can partially succeed: check responses and observed state after changes.
5. Show Keep/Revert for a proposed 15 seconds using a monotonic deadline. Timeout,
   client crash, failed commands, or invalidated topology trigger recovery.
6. Keep commits the confirmed runtime state. Save on login is a distinct, explicit
   persistence choice; profile storage alone does not rewrite compositor config.
7. On persistence, atomically replace only the managed file, validate reload and
   observed state, and retain backups. Disarm recovery only after final success.

The guard must survive GUI/CLI failure and share a transaction identifier with
the coordinator. If both fail, the next start detects an unfinished journal and
offers recovery; it must not replay stale commands into a different session.
If rollback cannot restore disconnected outputs, preserve an available output
with a preferred-mode fallback and report degraded recovery. No software timeout
can guarantee recovery from a compositor/GPU crash; native fault testing is required.

Manual previews and automatic profile application use the same recovery path.
The watcher pauses during a transaction, and self-generated events cannot start a
second apply. Never bypass confirmation by default for keybindings or automation.

## Configuration ownership

Profiles and preferences live under `$XDG_CONFIG_HOME/monarch/`; journals and logs
under `$XDG_STATE_HOME/monarch/`; locks and local IPC under `$XDG_RUNTIME_DIR`.
Use user-private permissions. Planned persistence is a dedicated managed Lua file
such as `$XDG_CONFIG_HOME/hypr/monarch/monitors.lua` loaded explicitly from the
active configuration. Confirm the exact include mechanism in phase 1. The UI
previews the integration and requests an explicit user action to install it.

Do not parse/rewrite arbitrary Lua or replace the main Hyprland config. Recognize
custom config paths, ownership conflicts, symlinks and external file changes;
stop for a reviewable conflict instead of overwriting. Generated content needs
proper Lua literal escaping and finite, validated numeric values. Invoke hyprctl
with an argument array, never through shell interpolation. Imported profiles are
data, never commands or Lua snippets.

## Profiles and quick switching

Each versioned JSON profile has a stable UUID, display name, display identity
selectors, desired per-display settings, optional matching rules, priority, and
an explicit unmatched-display policy. Store mode refresh with sufficient precision;
retain `preferred`/automatic choices as choices rather than resolved snapshots.
Support schema migrations, backup-before-migration, and validation on import.
Future-schema profiles remain intact and read-only with an explanatory error.

Prefer a unique make/model/serial identity when available. Serial numbers can be
empty or duplicated; description and connector are explicit fallback selectors.
Connector names are hints, not universal persistent identities. Ambiguous identical
displays require user mapping. Match each physical output at most once.

Planned CLI surface: `monarch profiles list`, `monarch profiles apply <id>`,
`monarch profiles cycle`, `monarch status`, `monarch recover`, and
`monarch watch`. These commands do not exist yet. Mutating CLI operations use the
same session coordinator as the GUI; a GUI-independent guard protects previews.
Without a visible confirmation surface, an unconfirmed apply expires and reverts.
Define an explicit confirmation protocol before enabling noninteractive switching.
Tray integration is optional; CLI and main-window actions remain available when
no tray host is running. Autostart is opt-in and user-scoped, never a root service.

## Automatic matching

After a debounced topology change, match the complete connected set, including
disabled displays. Exact-set matching is the default; subset matching and handling
of extras are explicit per-profile choices. Rank eligible matches by user priority,
then specificity. Ties produce a prompt/no action, not arbitrary selection.
No match preserves the current usable layout. Automation never disables an
unknown extra output by default. Suspend/reconnect triggers fresh discovery.

Manual selection pins the selected profile until the connected topology changes
or the user resumes automation. Repeated snapshots of the same topology do not
clear the pin. Apply settling windows, idempotence, cooldowns, and failure backoff
prevent feedback loops. Failed/declined auto applications are suppressed for that
profile/topology until user retry or a genuine topology change. Logs explain the
selection, conflict, or no-op without publishing monitor identifiers by default.

## Decisions still open

- Whether to support legacy hyprlang after the Lua MVP.
- Whether custom modelines belong in the first release or an expert extension.
- Whether lid state should be an optional matching input after topology matching.
- Exact minimum PySide6 version and packaging dependency bounds after phase 1.
- Whether workspace routing warrants a separate later feature.

The defaults above allow implementation to begin; these questions do not imply
additional first-release scope.
