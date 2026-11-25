# Architecture and intended behavior

Status: Phase 4 adds versioned profiles, explicit physical identity mapping,
guarded GUI/tray/CLI switching and native Qt appearance to the existing editor.
Phase 5 adds opt-in policy previews and login lifecycle; physical acceptance is
open. See the [automation contract](phase-5-guide.md), [profile guide](phase-4-guide.md),
[Phase 3 behavior](phase-3-guide.md), [evidence](phase-3-report.md),
and the historical [Phase 2 behavior](phase-2-guide.md),
[evidence](phase-2-report.md), [research](compatibility.md), and the
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

The `src/monarch/` package uses `domain/`, `backends/hyprland/`, `services/`,
`storage/`, `ui/`, and `cli/` modules. Prefer standard
library facilities where sufficient. Python 3.12+ and PySide6/Qt 6 Widgets are the
initial choices. Use QProcess/Qt socket integration or bounded worker operations;
no blocking subprocess or socket reads on the GUI thread. Tests use pytest,
pytest-qt, recorded synthetic fixtures, and a fake backend. Phase 1 pins tool and
runtime dependencies after checking supported Arch packages.

## GUI workflow

The implemented main window has a central display canvas, a display properties
panel, and an Apply/Revert bar. The profile selector and Profiles menu provide
capture, editing and guarded switching. Monitor rectangles reflect logical
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

Phase 1 established that named Lua monitor updates merge fields, and reload
removes runtime rules in a controlled configuration. Runtime output snapshots
cannot recover arbitrary prior rule definitions. Phase 2 uses an exact, generated minimal configuration root with a known monitor
baseline and backup/reload strategy. It rejects mutation when rule
ownership, external runtime overrides, or recoverable configuration state are
uncertain. General restoration of third-party Lua logic is outside the initial
write-path guarantee. A successful reload must also be checked for config errors
and observed output state; full reload can rerun unrelated configuration logic.


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

Phase 2's supported root is a new private directory containing an exact
`hyprland.lua` template and generated `monarch_monitors.lua`. The latter embeds
versioned layout data plus deterministic rules and a preferred-mode fallback for
new outputs. The guard verifies the active process's config path, exact root
bytes, regenerated monitor content, initial observed baseline, clean version,
and Lua provider. Unknown versions, inaccessible metadata, external file edits,
symlinks/hardlinks, and unfinished journals refuse mutation.

This is an exclusive-control contract for isolated/explicitly owned sessions, not
a parser or adoption tool for arbitrary Lua. External controllers are unsupported;
observations cannot detect every hidden rule or advanced runtime override. The
armed guard resets rules by reloading only the verified, side-effect-free owned
root. Phase 3 adds a second, explicitly registered contract for basic desktop monitor
configuration, described below.

Desktop registration appends a reviewed include and pins the root and every
operator-declared dependency. It preserves unrelated root bytes and permissions,
keeps private backups, and blocks changed files until explicit re-review. It is
not a Lua sandbox or automatic transitive import discovery. Advanced/dynamic
monitor rules are outside the registration contract. A transaction pins the
contract fingerprint as well as monitor content. The Qt worker performs I/O off
the GUI thread and uses the same guard API as the CLI.

For default XDG targets, tagged lookup is permitted only with verified hyprutils
versions and uses explicit `reload full-reset`; ordinary reload caches its path.
Explicit config arguments/environment paths keep ordinary reload. Full-reset
runs the reviewed Lua context again and is explained before integration approval.

The guard owns all mutations and the session `flock`. Its stdin control pipe uses
the transaction ID, Keep/Revert, and an explicit persistence boolean. Client EOF,
SIGTERM/SIGINT, deadline expiry, observed drift, or invalid control triggers
rollback. The process runs in a separate session and survives client SIGKILL.
SIGKILL of the guard itself retains an unfinished journal for explicit recovery.
The deadline covers apply and persistence as well as the pending preview.

Confirmed runtime-only layouts are remembered separately from disk. A later
preview restores that known runtime baseline on rollback; a deliberate config
reload can also return to the known disk baseline. Persistence compares hashes,
retains a private backup, atomically replaces the monitor file, reloads, and
checks errors and observed state before final confirmation. Uncooperative external
writers still require conflict handling; hashes are not a cross-process filesystem
compare-and-swap primitive. Cooperating Monarch clients share the session lock.

Journals bind to the session signature, boot and command-socket inode. Changed
sessions never receive stale recovery commands. Nonterminal journals from older
sessions block reuse of the same owned root and appear as a count in transaction
status. Other-session recovery requires manual backup review, not automatic replay.

The following paths and integration direction also apply to future phases:


Profiles live under `$XDG_CONFIG_HOME/monarch/`; native Qt appearance preferences
use Qt user settings. Journals and logs live
under `$XDG_STATE_HOME/monarch/`; locks and local IPC under `$XDG_RUNTIME_DIR`.
Use user-private permissions. Persistence uses a dedicated managed Lua file
such as `$XDG_CONFIG_HOME/hypr/monarch/monarch_monitors.lua` loaded explicitly
from the active configuration. The UI previews the integration and requires
an explicit user action to install it.

Do not parse/rewrite arbitrary Lua or replace the main Hyprland config. Recognize
custom config paths, ownership conflicts, symlinks and external file changes;
stop for a reviewable conflict instead of overwriting. Generated content needs
proper Lua literal escaping and finite, validated numeric values. Invoke hyprctl
with an argument array, never through shell interpolation. Imported profiles are
data, never commands or Lua snippets.

## Profiles and quick switching

Profiles contain a stable UUID, a unique name and a concrete layout snapshot.
Manual profile switches require an exact physical set and advertised modes;
automatic rules can explicitly select subsets while preserving extras. Schema-1 interchange
migrates on the next successful edit. Future schemas remain unchanged. See the
[profile guide](phase-4-guide.md) for the schema and confirmation contract.

`monarch profile` provides offline CRUD/import/export, fresh capture and switching.
Keybinding switches open visible Qt confirmation; `--terminal` requires a real TTY
and typed Keep. Tray actions also open the editor and clear persistence. Every
apply goes through the existing independent guard and per-session lock. Unknown
runtime baselines after topology changes still require integration re-review.
A profile resolver cannot bypass recovery ownership. Cycle remains unimplemented.
Phase 5 adds opt-in automatic previews and explicit XDG autostart; physical dock/resume/fresh-login acceptance remains open.

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

## Profile persistence and identity

`storage/profiles.py` maintains a private schema-2 catalog under XDG config, with
atomic writes and a cooperative lock separate from the session transaction lock.
Schema-1 interchange migrates on the next edit; unknown versions remain unchanged.
Import/export is strictly data-only. `domain/profiles.py` resolves the exact physical
set before generating a session layout, remaps mirror references, and requires
explicit bindings for ambiguous identities or absent-serial connector changes.
The worker repeats live discovery before loading; the guard validates again before
mutation. GUI, tray and terminal clients use the same coordinator and session lock.

Appearance uses the Qt platform theme and QStyleFactory rather than a global
stylesheet/palette. Same-major/minor system plugin trees augment wheel discovery;
Qt validates individual plugins. Optional tray actions surface visible GUI
confirmation and never imply Keep or save-on-login. Closing the editor hides it
when the tray or login runner is active.

## Implemented automatic preview lifecycle

The Qt worker hosts the event watcher and authoritative polling. A private
session lock elects one enabled automatic owner. Pure rules select by priority,
exactness and specificity; ties/no match preserve state. Subset rules retain extras.
Explicit saved-port bindings are separate from default physical identity matching.
Session runtime controls carry a manual pin/generation, durable attempt history
and heartbeat. Draft editing defers automatic offers. A manual coordinator client
can revoke an active automatic guard without setting a session pause.
Automatic guards pin both the policy and catalog revision and never persist.
Only authorized topology changes can capture a new basic recovery baseline;
same-set unexplained drift remains refused. A revoked permit cancels apply but
never blocks recovery. UI offers retain their original authorization snapshot.

The XDG desktop entry is opt-in, receipt/hash protected and points to the current
interpreter/catalog. It starts with the editor hidden and opens a confirmation
window when an automatic preview is offered. Plain Hyprland needs a session autostart host or
an explicit existing-session launcher. Physical dock/resume/login acceptance is
separate from the implemented software and native virtual-output checks.

## Phase 6 observation and support boundary

`domain/advanced.py` parses whitelisted state and produces read-only feature gates.
The guard checks known basic state before and during writes; unsupported external
advanced drift pauses physical recovery and retains its journal. Disabled-output
metadata is not treated as current active state. ICC/global dynamics still require
the existing operator-reviewed exclusive basic contract. No advanced layout schema
or writer is introduced; unverified writes remain unavailable. Tagged mirror IDs
resolve through the full topology; unknown targets are explicitly unresolved.

`services/diagnostics.py` collects categorized support snapshots without creating
missing storage. `services/reporting.py` allowlists values and omits free-form
private data. CLI and Qt Help share the collector and private/no-clobber exporter.
[Phase 6 behavior and decisions](phase-6-guide.md) apply in addition to historical
guides; their earlier basic-setting promises do not cover advanced active state.
