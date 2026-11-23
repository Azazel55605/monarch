# Contributing to Monarch

Monarch has a native Qt manual-editor alpha and guarded CLI foundations. Start with the [implementation plan](docs/implementation-plan.md)
and [progress tracker](docs/progress.md). Keep changes focused on a task ID;
record the evidence required to mark it done. Discuss architectural departures
and new scope before treating them as accepted roadmap changes.

Keep domain logic independent of Qt and compositor I/O.
Use typed models, bounded subprocess calls, explicit configuration ownership, and
the shared apply/recovery coordinator. Do not add an alternate mutation path for
a CLI, tray action, or automation rule.

Add meaningful tests for validation, matching, serialization, state transitions,
and recovery. Report automated, headless Qt, and native Wayland results separately.
Do not mark a hardware feature validated using only a fake backend.

Use synthetic monitor names and identities in fixtures. Before publishing reports,
remove home directories, usernames, serial numbers, EDID, private config contents,
and unrelated process/window information. Bug reports should include software
versions, a generic topology, reproduction steps, expected/observed behavior,
and redacted errors. Never include credentials.

Use Python 3.12+ and uv 0.13.9 (the CI version). `uv sync --locked --extra gui --group gui-dev` installs the
package and development dependencies. Use `uv run --extra gui --group gui-dev` for Ruff and mypy, and set
`QT_QPA_PLATFORM=offscreen` when running pytest. Build with `uv build`.
The automated tests require Linux (including `/proc` and PTYs), but no live
compositor, Qt installation, or GPU. Guard integration tests launch an independent
process and exercise client death, deadline enforcement, locking and terminal
confirmation using a synthetic subprocess transport.

For read-only native checks, run `uv run monarch inspect` in Hyprland. Reports
redact identifying fields unless `--show-identifiers` is explicitly requested.
Do not commit raw local captures. The optional `python tools/probe_lua.py` starts
and terminates its own temporary nested Hyprland instance; it requires version
0.57.2, Wayland and render-device access and briefly opens a nested window. It
performs mutations only after verifying that the new instance uses the Wayland
backend and has a different signature from the parent. See the
[Phase 1 report](docs/phase-1-report.md) for scope and limitations.

The Phase 2 opt-in test is `uv run python tools/probe_recovery.py`. It uses a
verified nested Wayland backend and virtual outputs, exercises real guarded
previews/persistence/recovery, and includes an intentionally failed reload via a
local subprocess wrapper. It requires render-device access, which may be absent
in a sandbox. Keep that evidence separate from physical-output acceptance. See
[Phase 2 evidence](docs/phase-2-report.md) and the [ownership contract](docs/phase-2-guide.md).
Never remove or relax the owned-root check to make an arbitrary local config pass.


Phase 3 GUI checks use pytest-qt, synthetic inspection fixtures and an actual
independent guard process with a fake transport. `tools/probe_gui.py` additionally
checks the real Qt/Wayland editor in a disposable default-XDG compositor with
mixed fractional scales, reviewed integration, persistence/revert, identification
placement and hotplug. Never substitute offscreen tests for that native evidence.

The root ownership check now accepts an explicit, hashed registration as well as
the minimal owned root. Do not weaken either contract. Config source closure and
basic-monitor delegation are operator-reviewed; arbitrary Lua is not parsed or
executed for discovery. See the [Phase 3 guide](docs/phase-3-guide.md).

Phase 4 adds `tools/probe_profiles.py` for native themes, three generic profiles,
explicit mappings, GUI/tray confirmation and terminal switching in a disposable
compositor. Catalog tests must cover unknown/future schema preservation, private
storage and import conflicts; matching tests must never rely on connector equality
to distinguish physically identical displays. Keep Qt offscreen, nested Wayland
and physical-device evidence separate.

Phase 5 uses `tools/probe_automation.py` for virtual hotplug and real automatic
confirmation. Virtual outputs require explicit saved-port bindings because their
hardware identity fields are empty; do not weaken physical ambiguity checks to
make fixtures pass. Autostart tests use temporary XDG roots and must not install a
host entry. Record physical docking/resume/login acceptance separately.

Phase 6 uses `tools/probe_compatibility.py` for native read-only feature gates,
redacted export, basic apply/revert and tagged mirror-ID resolution. Tests must
distinguish observations, hardware advertisements and validated writes. Advanced
writes remain deferred; do not use virtual-output success to enable physical
VRR/HDR/ICC/depth controls. Public diagnostic fixtures must test injected secrets,
unknown strings and no collection-time directory creation.

Phase 7 builds source/wheel assets with `tools/check_artifacts.py` and native Arch
packages with `tools/build_arch_package.py`. The disposable container exercises
makepkg checks, actual pacman install/removal and installed Qt/help resources.
`/usr/bin/python tools/probe_package.py --prefix /path/to/extracted/package` runs
the native compatibility probe against that package payload and independent guard,
without installing it on the host. Keep container lifecycle, staged native Wayland
and physical installed-session acceptance distinct. See the
[testing guide](docs/testing-guide.md) and [release checklist](docs/release-checklist.md).
