# Compatibility research

Research date: 2026-11-23. This records upstream interfaces, not Monarch runtime
certification. No monitor settings were changed during repository preparation.

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
| [hyprctl](https://wiki.hypr.land/configuring/core/advanced-configuration/using-hyprctl/) | JSON discovery, `eval`, diagnostics | Output shapes, capability detection, runtime error handling |
| [IPC events](https://wiki.hypr.land/ipc/) | Subscribe to topology events | Event payloads, framing, reconnect and restart behavior |
| [Modes and mirroring](https://wiki.hypr.land/configuring/core/monitors/modes/) | Mode choices, mirror groups, VRR | Fractional scale constraints and hardware-specific behavior |
| [Qt for Python](https://doc.qt.io/qtforpython-6/) | PySide6 GUI | Arch packages, Wayland plugin, distribution licenses |

The Lua monitor rule uses fields such as `output`, `mode`, `position`, `scale`,
`transform`, `disabled`, and `mirror`. Advanced fields include VRR, bit depth,
color management, and HDR-related settings. Their presence in documentation is
not evidence that a particular GPU/display combination can use them.

Monitor discovery should read `hyprctl -j monitors all`, retaining inactive
outputs, and inspect the compositor version. Runtime Lua changes use `hyprctl
eval`; keep the typed command generator separate from process execution. Control
requests are synchronous in the compositor: avoid continuous polling and
coalesce event-driven refreshes. Runtime overrides need persistence across reloads.

The event stream is exposed at
`$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock`.
Treat events as invalidation hints and re-query authoritative topology after
settling. A socket notification alone does not prove a monitor is ready.

## Support policy to establish in phase 1

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
