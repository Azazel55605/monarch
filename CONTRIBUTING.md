# Contributing to Monarch

Monarch has inspection and guarded CLI preview foundations. Start with the [implementation plan](docs/implementation-plan.md)
and [progress tracker](docs/progress.md). Keep changes focused on a task ID;
record the evidence required to mark it done. Discuss architectural departures
and new scope before treating them as accepted roadmap changes.

Once source code exists, keep domain logic independent of Qt and compositor I/O.
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

Use Python 3.12+ and uv 0.13.9 (the CI version). `uv sync --locked` installs the
package and development dependencies. Run `uv run ruff check .`, `uv run ruff
format --check .`, `uv run mypy`, `uv run pytest`, and `uv build` before submitting.
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
