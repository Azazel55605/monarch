# Phased implementation plan

Created: 2026-11-23. Phase 1 feasibility findings incorporated on 2026-11-23.
Status is maintained in the [progress tracker](progress.md).
This plan scopes a Python/PySide6 application for Hyprland on Arch-based Linux.
[Architecture](architecture.md), [compatibility research](compatibility.md), and
[validation](validation.md) define the implementation boundaries.

Phases are dependency ordered. Do not call a phase complete without its exit
evidence. No calendar estimates are assigned before the compatibility spike.

## Phase 0 — Project definition and publication

Deliver the public repository, license, contributor guidance, researched baseline,
architecture, acceptance strategy, and task tracker. Keep all examples generic.

Exit: documentation links and tracker IDs verified; initial commit available on
the public default branch. This phase does not deliver application functionality.

## Phase 1 — Backend feasibility and read-only foundation

Create the Python package, development tools and CI. Build a read-only inspector
with typed monitor/mode data, bounded hyprctl calls, clear missing-session errors,
and synthetic JSON fixtures. Detect actual capabilities/config provider and custom
config roots. Prototype event reconnection and compare Lua behavior against the
stable target in a disposable session.

Prove rule update/removal behavior, include/reload ordering, and whether prior
rules/settings can be restored completely. Record unsupported cases and decide
which must block mutation. Document tested minimum versions, rather than assuming
all Lua-capable releases behave alike.

Exit: repeatable discovery and round-trip restoration evidence; unsupported
sessions degrade safely. If rule restoration cannot be made reliable, revise the
apply design before phase 2. Automated fixtures alone cannot satisfy this gate.

## Phase 2 — Validated apply, persistence primitive, and recovery

Phase 1 finding: omitted fields merge into named Lua rules; output snapshots
cannot restore arbitrary prior rules. Start by limiting mutation to an explicitly
owned, recoverable baseline, with conflict detection and backup/reload recovery.
Do not enable generic snapshot-only rollback. The
[feasibility report](phase-1-report.md) records the tested boundary.


Implement layout validation, logical geometry, Lua literal generation, one
transaction coordinator, independent recovery guard, journals, and explicit
confirmation. Add the managed-file writer with atomic replacement, backup,
conflict detection, and restore primitives before exposing persistence in the GUI.
Exercise partial command failure, rejected modes, timeout, GUI termination,
topology changes, and compositor loss. Never assume multi-monitor writes are atomic.

Exit: fake-backend fault injection passes and real-session preview/revert,
client-crash recovery, and managed-file rollback are demonstrated. Block any
layout which cannot leave or restore a usable output.

## Phase 3 — Usable Qt manual editor

Deliver the main window, proportional layout canvas, drag/snapping and numeric
positioning, monitor identification, enable/disable, mode/refresh, scale,
rotation, mirroring, and accessible properties controls. Surface stale topology,
validation errors, dirty edits, and Keep/Revert status. Add explicit save-on-login
integration with a preview of the managed include and conflict explanation.

Exit: a user can inspect, edit, preview, confirm, persist, reload, and restore a
layout from the GUI. Native Qt/Wayland mixed-DPI and multi-output checks pass.
**Milestone: manual-editor alpha.**

## Phase 4 — Profiles and fast switching

Add profile CRUD, capture from current/edited layout with clear semantics,
versioned storage/migration, generic import/export, stable identity matching,
missing/ambiguous display handling, a quick profile selector, optional tray menu,
and CLI/keybinding commands. Route all mutations through the same coordinator.
Define the confirmation flow for CLI and tray before enabling apply there.

Exit: at least three generic setups can be saved, switched, and recovered;
connector changes and identical-display ambiguity are covered. GUI/CLI races
cannot create concurrent transactions. **Milestone: profile beta.**

## Phase 5 — Opt-in topology automation

Implement the event-driven session watcher, debounce, reconnect, exact/subset
matching, priorities, tie handling, manual pin, no-match preservation, failure
backoff, and explainable selection. Offer explicit autostart enable/disable and
status in the GUI. Automatic applies retain rollback and confirmation safeguards.

Exit: docking, undocking, repeated events, start-after-hotplug, suspend/resume,
ambiguous matches, and failed applications do not loop or unexpectedly black out
all outputs. Manual switching consistently overrides policy.

## Phase 6 — Advanced settings and compatibility hardening

Add capability-gated VRR, bit depth, color/ICC and HDR options where their write
and recovery behavior can be validated. Keep unverified controls unavailable.
Decide custom-modeline and legacy-hyprlang scope separately; neither delays basic
manual editing. Improve diagnostics, schema evolution, unsupported-version UX,
and configuration-conflict reporting.

Exit: each shipped setting has validation and rollback evidence plus documented
hardware limitations. Explicitly defer options without adequate hardware coverage.

## Phase 7 — Arch packaging and first public release

Provide desktop entry, icon, user-facing help, license notices, clean environment
installation/uninstallation, release changelog, source packaging, and a reviewed
PKGBUILD. Document native dependency resolution and opt-in session startup.
Do not imply that a PKGBUILD has been submitted to or accepted by the AUR.

Exit: release checklist and native matrix completed, clean Arch-based install
validated, profile/config recovery documented, artifacts built in CI, and known
limitations published. Release tagging/publication is a future explicit action.
**Milestone: v0.1.0.**

## Scope boundary

First-release scope is monitor layout/settings, profiles, and optional topology
switching. Full desktop configuration, arbitrary Lua editing, brightness/DDC,
wallpaper management, workspace policy, multi-compositor support, root services,
and cloud profile synchronization are outside this plan. Advanced display options
may be deferred individually without misrepresenting hardware support.
