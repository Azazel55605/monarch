# Phase 1 implementation and feasibility evidence

Date: 2026-11-23. Scope: M1.1–M1.5. The runtime application is read-only.

## Delivered

- Installable `src/monarch` package, `monarch` CLI, development lock file, and
  GitHub Actions matrix for Python 3.12–3.14.
- Immutable monitor/mode observations with inactive outputs, optional fields,
  exact decimal refresh rates, mode deduplication, and scale/rotation geometry.
- An explicit read-only command allowlist: version, status, and monitors all.
  Requests use argument arrays, a selected instance, timeouts, combined output
  limits, cancellation cleanup, and errors without raw private compositor output.
- Version/provider/backend detection; custom config path metadata or an explicit
  unknown/unverified result. Configuration is never evaluated for detection.
- Bounded event framing, topology-event filtering, coalesced refreshes, socket
  reconnect/backoff, and cancellation cleanup. No automatic profile switching.
- Redacted JSON/text reports, missing-session guidance, and optional identifiers.
- An opt-in, reproducible nested-compositor Lua probe with temporary config,
  runtime, cache and state directories. It never sends mutations to the parent.

## Automated and packaging checks

| Environment | Result |
| --- | --- |
| Python 3.12.16, clean venv, installed wheel | 63 tests passed; CLI version works |
| Python 3.13.12, development environment | 63 tests passed; Ruff lint/format and strict mypy pass |
| Python 3.14.10, clean venv, installed wheel | 63 tests passed; CLI version works |
| Source distribution and wheel | Built successfully with `uv build` |

Tests cover malformed JSON/schema, unknown fields/provider/version, disabled and
missing monitor data, refresh precision, geometry, invalid/extreme numbers,
command injection rejection, subprocess timeout/output limits/cancellation,
identity/path redaction, process metadata precedence, split/oversized event
frames, event bursts, reconnect, missing sockets, and CLI validation.

Hosted CI also passed on implementation commit `58b58b2` for all three Python
versions: [Checks run 45152448774](https://github.com/Azazel55605/monarch/actions/runs/45152448774).
The workflow pins reviewed checkout/setup-uv action revisions and uv 0.13.9.
Later commit status remains visible in the repository's Actions tab.

## Read-only native evidence

On an Arch-based Linux Wayland session with Hyprland 0.57.2 and three connected
outputs, inspection matched direct hyprctl observations for dimensions, position,
scale, transform, enabled state, and available mode handling. Provider `lua` and
backend `drm` were reported through the status endpoint. Native event subscription
connected successfully, and CLI watch mode exited cleanly on Ctrl+C without a
traceback. No parent output settings were changed.

The sandbox could access session IPC but could not resolve the compositor process
in `/proc`; configuration detection correctly returned unknown. Custom paths,
relative paths, safe-mode precedence, and inaccessible metadata were exercised
with synthetic process fixtures. Default XDG paths remain candidates, not proof
of the active config. No private monitor identities or config files are published.

## Isolated Lua feasibility

Run, with a parent Wayland session and render-device access:

```sh
python tools/probe_lua.py
```

The probe is pinned to Hyprland 0.57.2. It forces an unusable DRM device selection,
requires the newly created compositor to report the Wayland backend, verifies a
new instance signature and one nested Wayland output, then creates a fixed-size
virtual output inside that compositor. The invoking desktop's tiling dimensions
cannot interfere with fractional-scale checks on that virtual output. Cleanup
terminates only the child process, including on failure.

The sandbox lacked GPU render-device access; the successful test used host access.
This is native compositor execution on a nested/virtual output, not physical
monitor or GPU crash recovery certification. Results:

```json
{
  "hyprland": "0.57.2",
  "backend": "nested-wayland",
  "runtime_partial_update_merges": true,
  "reload_removes_runtime_rule": true,
  "include_order_last_named_update_wins": true,
  "required_module_reexecuted_on_reload": true,
  "removed_include_rule_releases_fallback": true,
  "baseline_layout_round_trip": true,
  "general_arbitrary_rule_restoration_proven": false
}
```

The probe changes scale, applies a second partial update, observes the retained
scale, and reloads the original config to restore baseline scale/transform/position.
It then changes same-output include ordering, edits the required module, removes
its named rule, verifies fallback changes take effect, and restores the original
configuration. These are observed state checks, not command-success-only checks.

Tagged-source review agrees with those results:

- [`hlMonitor`](https://github.com/hyprwm/Hyprland/blob/v0.57.2/src/config/lua/bindings/LuaBindingsConfigRules.cpp)
  seeds an update from the existing same-output rule before applying supplied fields.
- [`MonitorRuleManager`](https://github.com/hyprwm/Hyprland/blob/v0.57.2/src/config/shared/monitor/MonitorRuleManager.cpp)
  replaces same-name entries and resolves matching rules in reverse order.
- [Lua reload](https://github.com/hyprwm/Hyprland/blob/v0.57.2/src/config/lua/ConfigManager.cpp)
  clears monitor rules and refreshes required user modules before reloading config.

## Decision for Phase 2

Proceed with a restricted, explicitly owned configuration baseline plus backup and
reload recovery. Do not implement generic rollback by replaying output snapshots:
omitted fields can survive a partial update, and observations do not reconstruct
prior wildcard/specific rules or arbitrary Lua logic. Mutation must remain blocked
where ownership, external overrides, or recoverability cannot be established.
Full reload can run unrelated user logic and requires explicit integration and
conflict handling; it is not an unconditional safe undo command.

Phase 1's feasibility gate is resolved with this narrowed architecture. The
read-only CLI always reports `mutation_allowed: false`. No mutation endpoint,
monitor editor, guard process, persistent config writer, or profile system is
included in this phase. Physical apply/revert and native Qt acceptance remain
Phase 2/3 work. Reconnection to a new compositor signature is deliberately not
automatic; restart from the new session to avoid crossing session boundaries.
