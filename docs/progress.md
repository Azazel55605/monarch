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
| 2 — Apply and recovery | Planned | None |
| 3 — Qt manual editor | Planned | None |
| 4 — Profiles/quick switch | Planned | None |
| 5 — Automatic switching | Planned | None |
| 6 — Advanced settings | Planned | None |
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
| M2.1 | Layout/identity/mode validation and geometry | Planned | Mixed scale, transforms, mirroring and no-output rejection |
| M2.2 | Typed Lua serialization and bounded execution | Planned | Escaping, malformed input, timeout and partial failure tests |
| M2.3 | Shared coordinator and independent recovery guard | Planned | Timeout, client death, serialization and stale-session tests |
| M2.4 | Managed-file writer, backup and recovery journal | Planned | Atomic writes, concurrent edits, symlink policy, failed reload recovery |
| M2.5 | Native apply/revert fault acceptance | Planned | [Required recovery cases](validation.md) |
| M3.1 | Window, canvas, snapping, keyboard/numeric editing | Planned | Qt interaction and native mixed-DPI checks |
| M3.2 | Display controls, identification and validation UI | Planned | Native multi-output editing scenario |
| M3.3 | Keep/Revert, stale topology and dirty-state UX | Planned | Visible countdown, accessible recovery, hotplug during edit |
| M3.4 | Explicit save-on-login/config integration | Planned | Preview include, conflict detection, reload and restore |
| M4.1 | Versioned profile CRUD, migration, import/export | Planned | Invalid/future-schema, atomic storage and migration fixtures |
| M4.2 | Stable identity mapping and missing/ambiguous outputs | Planned | Connector rename and duplicate/absent serial scenarios |
| M4.3 | GUI/tray quick switching and CLI/keybinding interface | Planned | Shared transaction and confirmation across entry points |
| M5.1 | Policy matching, priority, ambiguity and manual pin | Planned | Deterministic topology matrix |
| M5.2 | Watcher, debounce, backoff and feedback suppression | Planned | Reconnect, storms, no match and failure tests |
| M5.3 | Opt-in autostart and native dock/resume acceptance | Planned | Enable/disable lifecycle and real-session report |
| M6.1 | Capability-gated advanced controls and recovery | Planned | Per-option hardware evidence or explicit deferral |
| M6.2 | Compatibility policy and scope decisions | Planned | Legacy/modeline decisions; tested release matrix |
| M6.3 | Redacted diagnostics and error/help polish | Planned | Useful report without default identifiers/config leakage |
| M7.1 | Desktop assets, notices, help and Arch PKGBUILD | Planned | Packaging review; no implied AUR publication |
| M7.2 | Clean install/uninstall and full native acceptance | Planned | [Validation matrix](validation.md), limitations recorded |
| M7.3 | CI artifacts, changelog and release readiness | Planned | Reproducible artifacts and completed release checklist |

## Current next action

Start Phase 2 with an ownership/conflict contract and a recoverable managed
configuration baseline. M1.5 rules out generic snapshot-only rollback; do not add
monitor mutations until this boundary and the independent guard are implemented.
Physical apply/revert and native Qt editor acceptance have not run.

## Phase 1 checks

See the [Phase 1 report](phase-1-report.md): 63 tests passed on Python 3.12.16,
3.13.12 and 3.14.10; Ruff, strict mypy, wheel/source builds, read-only native
three-output comparison, event subscription, and isolated nested Lua checks pass.
Hosted CI status is tracked independently in GitHub Actions.

## Repository preparation checks

On 2026-11-23, verified local links and whitespace across seven Markdown files,
30 unique tracker task IDs, staged whitespace checks, and public-content review.
The initial publication was verified through GitHub metadata and the remote branch
SHA. These are documentation/repository checks, not application test results.
