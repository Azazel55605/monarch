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
| 7 — Packaging/release | In progress | [Testing candidate](phase-7-report.md); installed-session/physical acceptance and stable release gates open |

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
| M7.1 | Desktop assets, notices, help and Arch PKGBUILD | Done | [Resources](../src/monarch/resources/guide.md), [native recipe](../packaging/arch/PKGBUILD.in), [testing guide](testing-guide.md); no AUR submission |
| M7.2 | Clean install/uninstall and full native acceptance | In progress | [Packaging evidence](phase-7-report.md); clean package checks delivered, installed physical-session acceptance pending |
| M7.3 | CI artifacts, changelog and release readiness | In progress | [CI artifacts](../.github/workflows/checks.yml), [changelog](../CHANGELOG.md), [release checklist](release-checklist.md); stable promotion awaits acceptance/authorization |

## Current next action

The user confirmed rc4 fixed the VRR toggle on their panel. Test rc5 sidebar
scaling, tray shortcuts and new-display previews using the [testing guide](testing-guide.md).
Record physical docking with eligible profiles and unfamiliar displays, along
with persistence and ordinary layout edits while VRR is On. Target-display, dock/resume
and fresh-login acceptance still precede stable promotion. Conditional VRR,
HDR/depth/color/ICC remain future work.
No stable tag/publication or AUR submission has been performed.

## TV hotplug follow-up

Physical feedback exposed a paused watcher and a replacement HDMI display that
inherited an unsupported timing. rc7 scopes implicit pauses to the current
display set and uses advertised timings for previews and recovery on a reused
connector. A read-only check against the reconnected TV selected an advertised
mode for both preview and recovery. Physical picture confirmation remains open.

## VRR-only physical feedback fix

The rc3 physical toggle failed and rolled back; the journal reported an unobserved
update. Global VRR re-enabling then produced an external/owned-baseline mismatch.
`0.1.0rc4` models the supported compositor's cached-rule behavior and adds a guarded
soft refresh. See the [compatibility fix](vrr-guide.md#hyprland-0572-vrr-only-update-fix-rc4).
[Final rc4 CI](https://github.com/Azazel55605/monarch/actions/runs/45241834537) on
`fe144db` passed all 266 tests on Python 3.12–3.14 and clean Arch build/install/removal.
Candidate checksums, source manifest and installed application payload verified;
native virtual position refresh/restoration passed. Physical VRR acceptance remains open.

## VRR follow-up

`0.1.0rc3` implements explicit per-monitor Off/On through the shared guard, layout
schema 2, profiles, preview, rollback and persistence. Legacy layouts/modules and
journals remain readable. [Current behavior and evidence](vrr-guide.md) supersede
the Phase 6 VRR deferral; target physical VRR acceptance remains **In progress**.
Conditional policies are not inferred from active state and remain deferred.
The software gate no longer rejects an owned and observed VRR On baseline.
[Hosted CI on `2ba3478`](https://github.com/Azazel55605/monarch/actions/runs/45237720816)
passed all 263 tests on Python 3.12–3.14 and the clean Arch install/removal job.
Candidate checksums, source manifest and installed application payload were verified;
native Lua parser and Qt draft/control checks passed without parent monitor writes.

## Tray and canvas feedback follow-up

`0.1.0rc2` implements close-to-tray lifetime, explicit Quit/no-host fallback,
contrasting monitor outlines, and live zoom-aware edge snapping. See the
[feedback changes and validation](rc2-feedback.md). All 242 tests passed on hosted
Python 3.12–3.14 and the clean Arch build/install/removal job on `3024b18`;
source/wheel/native artifacts were downloaded and verified. Automatic integration of newly
attached unknown external displays remains a future request; the existing watcher
continues discovery while hidden. The VRR follow-up above addresses the software
write-path blocker; physical acceptance gates remain open.

## User feedback

Target-session theme, icon/tray, help, discovery, diagnostics and status banner
are confirmed working by user testing. Active VRR blocks layout application with
the current basic recovery guard. The user confirms both Set up monitor management
and Preview changes are greyed out by that gate.
See the [feedback record](phase-7-report.md#user-feedback--2026-11-23).
This is the historical rc1/rc2 feedback; rc3 adds explicit owned VRR Off/On.
Physical preview/recovery acceptance remains open.

## Phase 7 candidate checks

See the [Phase 7 report](phase-7-report.md) for source/wheel assets, native Arch
package, clean install/removal, installed payload/native evidence and CI artifacts.
All 231 tests passed in hosted Python 3.12–3.14 and the clean Arch job;
[CI on `155bd79`](https://github.com/Azazel55605/monarch/actions/runs/45219136187)
uploaded source/wheel/native artifacts. Native packaged Qt help/icon startup passed,
but the complete nested probe hit output-creation/mirror timeouts. Packaging
availability is separate from the user's proper test and release gate.

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
