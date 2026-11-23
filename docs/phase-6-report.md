# Phase 6 implementation and evidence

Date: 2026-11-23. Package: `0.1.0.dev6`. Scope: M6.1–M6.3.
Phase 6 completes the capability/compatibility/diagnostics work with explicit
advanced-write deferrals permitted by its exit gate.

## Delivered behavior and deferrals

The native Advanced panel distinguishes observed state, advertised hardware flags
and validated write capability. It shows current VRR state, recognized pixel format/
bit depth, color preset and HDR metadata, plus the lack of active ICC information.
No advanced setting is editable. Unknown values are not fabricated as defaults.

| Option | Write decision | Evidence required before promotion |
| --- | --- | --- |
| VRR | Deferred | Restorable policy, actual adaptive-sync behavior, Keep/Revert/client-loss tests on capable hardware |
| Bit depth | Deferred | Supported formats and saved policy, visible-output verification, driver fallback and rollback on physical outputs |
| Color/SDR/EOTF | Deferred | Complete owned-rule representation and verified color restoration on hardware |
| HDR | Deferred | Working HDR signaling/output, global/fullscreen interactions and rollback on supported displays |
| ICC | Deferred | Private file identity/content handling and reproducible transform/rollback evidence |

The basic guard now rejects known non-basic or missing active-state observations
before mutation, rechecks during apply/confirmation, and pauses recovery without
further compositor mutation when unsupported external state appears. The journal
remains available for recovery after review. This filter does not claim to discover
hidden ICC/global/dynamic settings; the exclusive basic-config contract remains.

Legacy-hyprlang writing/conversion and custom-modeline editing are explicitly out
of scope for this alpha. Existing schemas stay strict, with future/advanced fields
rejected intact. No new profile data is silently omitted during import.

Read-only diagnostics are available through Qt Help and `monarch diagnose`, including
offline use and explicit private/no-clobber export. Reports use whitelisted values,
anonymous display labels and categorized conflicts; they omit identifiers, paths,
config contents, names, journal details, logs and arbitrary backend messages.
Collection does not create missing storage or alter compositor settings.

## Tagged-source compatibility correction

Review of the 0.57.2 monitor IPC implementation showed that `mirrorOf` contains a
monitor ID string. Discovery now resolves IDs against the full monitor list before
layout validation. Unknown or ambiguous references remain unresolved and cannot be
silently captured as unmirrored outputs. Existing connector-name observations remain
accepted when they refer to a known named output. Tests cover resolution and refusal.

## Automated/package evidence

| Layer | Result |
| --- | --- |
| Python 3.13.12, development environment | 228 tests passed |
| Python 3.12.16, installed GUI wheel | 228 tests passed; reports dev6 |
| Python 3.14.10, installed GUI wheel | 228 tests passed; reports dev6 |
| Ruff / formatting / strict mypy | Passed; 47 typed source files |
| Source distribution / wheel | Built successfully |
| Hosted Ubuntu CI, Python 3.12 / 3.13 / 3.14 | All jobs passed on `d9b7d6e` |

[Passing hosted CI](https://github.com/Azazel55605/monarch/actions/runs/45204554520)
includes all 228 tests per Python version, lint/formatting, strict types and builds.
Later commit status remains independently visible in GitHub Actions.

New tests cover strict
advanced observations, missing/invalid/nonfinite values, hardware flags vs write
gates, pre-mutation refusal and unchanged files, advanced drift during recovery,
resumption after review, automatic no-action, dirty draft staleness, read-only UI,
mirror ID resolution, unsupported provider/build behavior, future schema refusal,
redaction of injected secrets/build suffixes, offline diagnostics, no created storage,
private exports and no-clobber behavior. Existing recovery/profile/automation tests remain.

## Native observations

`tools/probe_compatibility.py` uses a disposable nested Hyprland 0.57.2 compositor
and actual virtual outputs with the production worker/coordinator/guard. It verifies
basic apply/Revert, mirror-ID normalization/apply/Revert, a native read-only Advanced
table, redacted diagnostics/private export and no parent monitor mutations.
PySide6/Qt is 6.12.0 on an Arch-based hybrid AMD/NVIDIA host.

The full native recovery regression also passed explicit Revert, deadline, client
EOF and SIGKILL, persistence, failed persistence reload, virtual hot-unplug degraded
recovery, and guard-SIGKILL manual recovery. The Phase 5 native automation probe
passed virtual dock/undock, automatic Keep/Revert, startup-file preservation,
manual pin/resume and repeated-cycle suppression under the new basic-state gate.
Those tests use explicit saved-port bindings for empty virtual hardware identities.

A separate read-only physical check collected a redacted report from three connected
outputs, detected existing advanced state, and compared before/after mode, position,
scale, transform, enabled state, VRR, pixel format and color preset. They were unchanged.
No physical display mode, color setting, login entry or application configuration
was changed for these checks. This does not certify any advanced write or rollback.

The native screenshot contains only synthetic observations:
[Advanced settings panel](assets/monarch-advanced.png). Qt emitted font-description
and Wayland text-input diagnostics; the listed native interactions completed.

## Limits and exit decision

No advanced write is shipped without hardware acceptance. Explicit per-option
deferral therefore satisfies Phase 6's stated gate; it does not claim those settings
are implemented as writable features. The Phase 5 physical dock/resume/fresh-login
gate remains open, as do physical modesetting, the Phase 4 virtual re-enable timeout
and the broader release matrix. Phase 7 packaging/release work remains planned.

## Primary sources

The tagged [monitor IPC implementation](https://github.com/hyprwm/Hyprland/blob/v0.57.2/src/ipc/s1/Commands.cpp)
defines observation fields and mirror IDs. The tagged
[Lua monitor bindings](https://github.com/hyprwm/Hyprland/blob/v0.57.2/src/config/lua/bindings/LuaBindingsConfigRules.cpp)
show separate rule fields for VRR, bit depth, color and ICC. The
[color preset mapping](https://github.com/hyprwm/Hyprland/blob/v0.57.2/src/helpers/CMType.cpp)
defines known presets. Observing an IPC field is not evidence of safe hardware
restoration; the write deferrals above are Monarch's evidence-based decisions.
