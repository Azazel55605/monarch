# Implementation progress

Updated: 2026-11-23. This file is the canonical tracker; the
[plan](implementation-plan.md) explains scope and exit gates.

Statuses: **Done** requires linked evidence; **In progress** means active work;
**Planned** means not started; **Blocked** requires a named dependency/reason.
Update task rows and phase summaries together in the same change. Keep native
acceptance separate from automated checks. Planning completion is not product
completion. GitHub issues may mirror task IDs but must link back here.

## Phase summary

| Phase | Status | Exit evidence |
| --- | --- | --- |
| 0 — Definition/publication | Done | [Public repository](https://github.com/Azazel55605/monarch), `main`; initial local/remote commit verified: `a7cd9bf` |
| 1 — Read-only foundation | Done | [Phase 1 implementation and feasibility report](phase-1-report.md); read-only native discovery and nested Lua round-trip |
| 2 — Apply and recovery | Done | [Phase 2 evidence](phase-2-report.md); guarded CLI and native nested recovery matrix |
| 3 — Qt manual editor | Done | [Phase 3 evidence](phase-3-report.md); Qt tests, native fractional-scale GUI and read-only physical startup |
| 4 — Profiles/quick switch | Done | [Phase 4 evidence](phase-4-report.md) |
| 5 — Automatic switching | In progress | [Software and virtual-hotplug evidence](phase-5-report.md); physical dock/resume/login gate open |
| 6 — Advanced settings | Done | [Phase 6 evidence](phase-6-report.md); read-only gates/diagnostics and explicit advanced-write deferrals |
| 7 — Packaging/release | Planned | None |

## Tasks

| ID | Task | Status | Evidence / completion requirement |
| --- | --- | --- | --- |
| M0.1 | Define product scope and public documentation | Done | [README](../README.md), [plan](implementation-plan.md) |
| M0.2 | Research current Lua interfaces and risks | Done | [Research and upstream sources](compatibility.md) |
| M0.3 | Define architecture and acceptance gates | Done | [Architecture](architecture.md), [validation](validation.md) |
| M0.4 | Initialize and publish public Git repository | Done | [Initial commit](https://github.com/Azazel55605/monarch/commit/a7cd9bf5ba0ff4d667acde197fe776f20a656e50); PUBLIC visibility, `main`, and matching local/remote SHA verified |
| M1.1 | Package skeleton, dependency bounds, lint/type/test CI | Done | [Package](../pyproject.toml), [CI](../.github/workflows/checks.yml), [local Python 3.12–3.14 checks](phase-1-report.md) |
| M1.2 | Typed discovery, modes, inactive outputs, diagnostics | Done | [Parser](../src/monarch/domain/monitors.py), [fixtures/tests](../tests/test_monitors.py), [native comparison](phase-1-report.md) |
| M1.3 | Version/provider/config-path capability detection | Done | [Inspector](../src/monarch/backends/hyprland/inspector.py), [metadata tests](../tests/test_config.py); unknown paths/providers remain explicit |
| M1.4 | Event subscription, framing, reconnect and refresh | Done | [Watcher](../src/monarch/backends/hyprland/events.py), [socket tests](../tests/test_events.py), [native subscription](phase-1-report.md); instance-bound reconnect |
| M1.5 | Prove Lua update/remove/restore and include semantics | Done | [Nested probe](../tools/probe_lua.py), [results and restricted recovery decision](phase-1-report.md); arbitrary-rule restoration unsupported |
| M2.1 | Layout/identity/mode validation and geometry | Done | [Layout validation](../src/monarch/domain/layout.py), [domain tests](../tests/test_layout.py); complete topology, identity, geometry and mirror checks |
| M2.2 | Typed Lua serialization and bounded execution | Done | [Typed writer](../src/monarch/backends/hyprland/writer.py), [bounded transport](../src/monarch/backends/hyprland/commands.py); escaping and mutation fault tests |
| M2.3 | Shared coordinator and independent recovery guard | Done | [Coordinator](../src/monarch/services/coordinator.py), [independent guard](../src/monarch/services/guard.py), [process/PTY tests](../tests/test_guard.py) |
| M2.4 | Managed-file writer, backup and recovery journal | Done | [Managed storage](../src/monarch/storage/managed.py), [transaction recovery](../src/monarch/services/transaction.py), [storage tests](../tests/test_storage.py); stale/foreign journal and conflict checks |
| M2.5 | Native apply/revert fault acceptance | Done | [Native recovery probe](../tools/probe_recovery.py), [observed results and limits](phase-2-report.md); parent physical outputs unchanged |
| M3.1 | Window, canvas, snapping, keyboard/numeric editing | Done | [Qt window/canvas](../src/monarch/ui/window.py), [model](../src/monarch/ui/model.py), [Qt interaction tests](../tests/test_ui.py) |
| M3.2 | Display controls, identification and validation UI | Done | [Display controls](../src/monarch/ui/window.py), [native identification](../src/monarch/ui/identify.py), [mapped-output evidence](phase-3-report.md) |
| M3.3 | Keep/Revert, stale topology and dirty-state UX | Done | [Confirmation dialog](../src/monarch/ui/dialogs.py), [worker](../src/monarch/ui/worker.py); deadline, stale edits and GUI-close guard recovery tests |
| M3.4 | Explicit save-on-login/config integration | Done | [Reviewed desktop integration](../src/monarch/storage/integration.py), [guide](phase-3-guide.md), [native GUI probe](../tools/probe_gui.py); pinned sources and conflict handling |
| M4.1 | Versioned profile CRUD, migration, import/export | Done | [Catalog](../src/monarch/storage/profiles.py), [tests](../tests/test_profiles.py) |
| M4.2 | Stable identity mapping and missing/ambiguous outputs | Done | [Resolver](../src/monarch/domain/profiles.py), [explicit mapping UI](../src/monarch/ui/profiles.py) |
| M4.3 | GUI/tray quick switching and CLI/keybinding interface | Done | [Guide](phase-4-guide.md), [native probe](../tools/probe_profiles.py), shared guard and PTY tests |
| M5.1 | Policy matching, priority, ambiguity and manual pin | Done | [Policy](../src/monarch/domain/policy.py), [matching tests](../tests/test_policy.py), shared session overrides |
| M5.2 | Watcher, debounce, backoff and feedback suppression | Done | [Engine](../src/monarch/services/automation.py), [fault/timing tests](../tests/test_automation.py), [native virtual hotplug](phase-5-report.md) |
| M5.3 | Opt-in autostart and native dock/resume acceptance | In progress | [Autostart controls](../src/monarch/storage/automation.py) and virtual lifecycle pass; physical dock/resume/fresh-login acceptance pending |
| M6.1 | Capability-gated advanced controls and recovery | Done | [Observed state/gates](../src/monarch/domain/advanced.py), [guard tests](../tests/test_advanced.py); advanced writes explicitly deferred with evidence requirements |
| M6.2 | Compatibility policy and scope decisions | Done | [Compatibility guide](phase-6-guide.md), tagged mirror-ID normalization; legacy writer/modelines deferred |
| M6.3 | Redacted diagnostics and error/help polish | Done | [Read-only collector](../src/monarch/services/diagnostics.py), [privacy/export tests](../tests/test_diagnostics.py), native Qt/physical read-only report checks |
| M7.1 | Desktop assets, notices, help and Arch PKGBUILD | Planned | Packaging review; no implied AUR publication |
| M7.2 | Clean install/uninstall and full native acceptance | Planned | [Validation matrix](validation.md), limitations recorded |
| M7.3 | CI artifacts, changelog and release readiness | Planned | Reproducible artifacts and completed release checklist |

## Current next action

Complete the Phase 5 physical dock/resume/fresh-login gate on a reviewed basic
monitor configuration. Software is implemented and opt-in; no host settings were
enabled or changed during implementation. See the [guide](phase-5-guide.md) and
[report](phase-5-report.md). Phase 6 observation/compatibility work is complete with
advanced writes explicitly deferred. Phase 7 packaging remains planned.

## Phase 6 checks

See the [Phase 6 report](phase-6-report.md) and [guide](phase-6-guide.md).
Advanced settings remain read-only. Known non-basic/unknown active state blocks
unsafe basic transactions; diagnostics and conflict reporting are redacted and
read-only. All 228 tests pass on local Python 3.12–3.14, including installed
GUI wheels on 3.12/3.14. Native basic recovery, virtual automation, mirror and Qt checks are
separate from a read-only physical report check. [Hosted CI](https://github.com/Azazel55605/monarch/actions/runs/45204554520)
passed all three versions on `d9b7d6e`. Hardware write gates remain open.

## Phase 5 checks

See the [Phase 5 report](phase-5-report.md): automated policy/guard/Qt/lifecycle
checks plus real virtual dock/undock, automatic Keep/Revert, topology-snapshot
recovery and shared manual pin/resume. Physical hardware and fresh-login acceptance
remain separate open gates. Default matching refuses ambiguous identities;
explicit saved-port rules require fixed cabling. All 198 tests passed on local
Python 3.12–3.14, including installed GUI wheels on 3.12/3.14. [Hosted CI](https://github.com/Azazel55605/monarch/actions/runs/45175992066)
passed all three versions on `1993de6`.

## Phase 4 checks

See the [Phase 4 report](phase-4-report.md) and [guide](phase-4-guide.md).
Native qt6ct/style discovery, three generic profiles, import/export, explicit
mapping, GUI Keep/Revert/persistence, tray action confirmation, client-close
recovery and PTY CLI switching passed in a disposable compositor. Parent monitor
settings were not changed. All 166 tests passed on local Python 3.12–3.14,
including installed GUI wheels on 3.12/3.14. [Hosted CI](https://github.com/Azazel55605/monarch/actions/runs/45169702883)
also passed all three versions on `6bafcae`.

## Phase 3 checks

See the [Phase 3 report](phase-3-report.md) for automated/installed-wheel results,
real native Qt/Wayland integration, fractional scaling, Keep/persistence, Revert,
per-output placement and hotplug checks. A read-only physical three-output startup
also passed without monitor changes. All 141 tests passed locally on Python
3.12–3.14, including installed-wheel checks. [Hosted CI](https://github.com/Azazel55605/monarch/actions/runs/45164889581)
passed all three versions on `550aa0a`. The GUI is a manual-editor alpha.

## Phase 2 checks

See the [Phase 2 report](phase-2-report.md) for automated and installed-wheel
results, real nested Wayland preview/recovery/persistence/fault checks, and the
owned-session compatibility boundary. [Hosted CI](https://github.com/Azazel55605/monarch/actions/runs/45157196053)
also passed all three Python versions on `a048e09`. The independent guard survives client death;
guard death retains durable manual recovery. No parent monitor settings changed.

## Phase 1 checks

See the [Phase 1 report](phase-1-report.md): 63 tests passed on Python 3.12.16,
3.13.12 and 3.14.10; Ruff, strict mypy, wheel/source builds, read-only native
three-output comparison, event subscription, and isolated nested Lua checks pass.
Hosted CI passed for all three versions on `58b58b2`: [Checks](https://github.com/Azazel55605/monarch/actions/runs/45152448774).
Later commit status is tracked independently in GitHub Actions.

## Repository preparation checks

On 2026-11-23, verified local links and whitespace across seven Markdown files,
30 unique tracker task IDs, staged whitespace checks, and public-content review.
The initial publication was verified through GitHub metadata and the remote branch
SHA. These are documentation/repository checks, not application test results.
