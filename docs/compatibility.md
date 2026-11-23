# Compatibility research

Research date: 2026-11-23. This records upstream interfaces, not Monarch runtime
certification. Phase 1 adds read-only native discovery and isolated nested-session
evidence in the [feasibility report](phase-1-report.md). No parent-session monitor
settings were changed.

## Baseline and sources

The initial stable target is [Hyprland v0.57.2](https://github.com/hyprwm/Hyprland/releases/tag/v0.57.2).
The [versioned 0.57 documentation](https://wiki.hypr.land/0.57.0/configuring/core/)
provides a reproducible starting reference. The unversioned wiki tracks latest
git and may describe changes beyond the stable target. Recheck against the actual
installed version and tagged source before implementing each adapter feature.

| Upstream interface | Planned use | Verification still needed |
| --- | --- | --- |
| [Lua configuration](https://wiki.hypr.land/configuring/core/) | Dedicated generated monitor include | Include ordering, reload semantics, custom config paths |
| [Monitor rules](https://wiki.hypr.land/configuring/core/monitors/) | Generate `hl.monitor` tables | Rule replacement/removal and restoration of prior rules |
| [hyprctl](https://wiki.hypr.land/configuring/core/advanced-configuration/using-hyprctl/) | JSON discovery, `eval`, diagnostics | Phase 1 verifies version/status/monitor reads; writes remain disabled |
| [IPC events](https://wiki.hypr.land/ipc/) | Subscribe to topology events | Event payloads, framing, reconnect and restart behavior |
| [Modes and mirroring](https://wiki.hypr.land/configuring/core/monitors/modes/) | Mode choices, mirror groups, VRR | Fractional scale constraints and hardware-specific behavior |
| [Qt for Python](https://doc.qt.io/qtforpython-6/) | PySide6 GUI | Arch packages, Wayland plugin, distribution licenses |

The Lua monitor rule uses fields such as `output`, `mode`, `position`, `scale`,
`transform`, `disabled`, and `mirror`. Advanced fields include VRR, bit depth,
color management, and HDR-related settings. Their presence in documentation is
not evidence that a particular GPU/display combination can use them.

Monitor discovery reads `hyprctl -j monitors all`, retaining inactive
outputs, and inspects the compositor version. Provider/backend come from `hyprctl -j status`,
which avoids collecting the broader system information report. See the tagged
[status implementation](https://github.com/hyprwm/Hyprland/blob/v0.57.2/src/helpers/SystemInfo.cpp).
The inspector does not rely on the instances command. Runtime Lua changes use `hyprctl
eval`; keep the typed command generator separate from process execution. Control
requests are synchronous in the compositor: avoid continuous polling and
coalesce event-driven refreshes. Runtime overrides need persistence across reloads.

The event stream is exposed at
`$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock`.
Treat events as invalidation hints and re-query authoritative topology after
settling. A socket notification alone does not prove a monitor is ready.

## Phase 1 support policy

- Detect the actual session, compositor version, configuration provider, and
  capabilities. Do not infer provider solely from a filename or version.
- Do not execute configuration files to inspect them. Prefer supported metadata;
  if provider/config path remains uncertain, ask for an explicit selection.
- Test safe capabilities read-only; defer mutating probes to a controlled session.
- Maintain fixtures and native acceptance results for supported stable releases.
- Treat development builds as experimental and gate unknown mutation semantics.
- Offer actionable read-only diagnostics when the backend is unsupported.
- A legacy hyprlang writer is an open scope decision, not an MVP dependency.

## Main unresolved risks

A runtime monitor snapshot may not capture prior wildcard rules, disabled-output
rules, color settings, or user Lua logic. Prove reversible rule updates before
claiming safe preview. Changes spanning several outputs can partially succeed;
calling a batch or Lua chunk does not establish transactional atomicity.

Executing arbitrary Lua for import would execute user code. Monarch should only
serialize its own typed data, escape strings, and manage its own files. Existing
configuration conflicts should be surfaced rather than silently overridden.

## Implemented compatibility boundary

The read-only adapter accepts additive JSON fields and exposes missing values as
unknown with warnings. Broken version/status responses do not hide otherwise
valid monitor discovery. A malformed monitor topology fails with an actionable
error. Only a clean `v0.57.2` tag is classified as the stable baseline; other
versions remain inspectable without a support claim. `lua_advertised` reflects
the reported provider, not proof that all Lua operations are safe.

Custom paths are discovered from the selected compositor's command line or
`HYPRLAND_CONFIG` process environment when accessible. Safe mode has precedence.
The conventional XDG path is only a candidate because config search directories
may change which file wins. An explicit `--config` is a user selection, not a
verified active path. Sandboxed/inaccessible process metadata remains unknown.
No Lua file is opened or executed for detection.

Event reconnection targets the selected signature only. A fresh compositor
signature requires a new invocation; discovery never silently crosses sessions.
PySide6 6.12.0 is available on the native test host, but no GUI has been implemented
or tested. The planned GUI dependency range is 6.8 through Qt 6; this is not yet
a certified Qt-version matrix.

## Phase 2 write boundary

The inspection transport retains its read-only allowlist. A separate typed writer
is used by the independently locked guard; the CLI offers no raw Lua or reload
endpoint. Writes require a clean 0.57.2 tag, the reported Lua provider, a verified
active config path, and an exact generated owned root. Existing full desktop
configs are unsupported for mutation until explicit Phase 3 integration.

[Phase 2 acceptance](phase-2-report.md) verifies preview/revert, timeout, client
SIGKILL, persistence, failed persistence reload, guard SIGKILL/manual recovery,
and virtual hot-unplug using a real nested compositor. It does not certify
physical modes, mixed-GPU scanout, or recovery from hardware/compositor crashes.

## Phase 3 GUI and registered desktop configurations

The GUI uses PySide6/Qt Widgets and a separate asyncio worker thread. Qt 6.12.0 is
natively tested; the dependency range remains Qt 6.8–6.x. Desktop writes require
an explicit basic-monitor ownership/reload agreement, exact registration/source
hashes and the same clean Hyprland 0.57.2 gate. Unknown custom/debug flags remain
inspectable without claiming write support.

Default config lookup follows tagged hyprutils 0.14.3/0.14.4 and is coupled to
`reload full-reset` in the guard. Empty/relative XDG search entries that could
change selection stay unsupported when reached. Explicit paths retain ordinary
reload. A selected file alone still cannot authorize writes. See the
[Phase 3 guide](phase-3-guide.md) and [native evidence](phase-3-report.md).

## Phase 6 scope and evidence gates

[Phase 6](phase-6-guide.md) adds strict advanced observations and a known-state
filter, while deferring all advanced writes until per-option hardware recovery
evidence exists. VRR active state is not a VRR policy; current format is not a list
of supported depths; EDID HDR metadata is not validated HDR output; ICC rule/file
state is not reconstructible from monitor IPC. Unknown values remain unknown.
The basic writer requires known 8-bit sRGB/default SDR with inactive VRR on active
outputs. Hidden advanced/global rules still fall outside the ownership contract.

Legacy hyprlang writing/conversion and custom-modeline editing are out of scope
for this alpha. Layout/profile/policy schemas retain their documented versions and
refuse unsupported extensions. Tagged mirror IDs are normalized to observed names;
unresolved targets cannot be captured or applied as independent outputs. Read-only
diagnostics omit identifiers, paths, raw data/errors and unrecognized strings.
See the [implementation evidence](phase-6-report.md) for acceptance and deferrals.
