# Monarch

A Python and Qt monitor manager for Hyprland. The CLI currently provides
read-only inspection and guarded monitor previews in explicitly owned sessions.
The visual editor, saved profiles, and quick setup switching are planned.

**Status: Phase 2 implemented — validated apply and independent recovery.**
There is no Qt monitor editor or stable release yet. Normal desktop configuration
integration belongs to Phase 3; the current write path requires a dedicated
Monarch-owned configuration. The inspector works independently of that restriction.

## Planned features

- Arrange displays visually, with snapping and precise numeric positioning.
- Configure resolution, refresh rate, scale, rotation, mirroring, and enablement.
- Preview changes with a timed Keep/Revert dialog and independent rollback guard.
- Save named profiles and switch through the GUI, a tray menu, or CLI commands
  suitable for Hyprland keybindings.
- Optionally select profiles when monitors connect or disconnect, with clear
  matching rules, manual override, and protection against repeated switching.
- Persist monitor settings through a dedicated, generated Lua include without
  rewriting unrelated desktop configuration.
- Expose advanced display options only after compatibility and hardware validation.

## Direction

Monarch targets Linux/Wayland with Hyprland, initially focusing on Arch Linux and
Arch-based distributions, including Garuda Linux. The proposed stack is Python
3.12+ and PySide6 (Qt 6 Widgets), with a Qt Graphics View layout editor. Core
models and policy logic will remain independent of Qt.

Lua is the primary configuration path. Read-only discovery is verified on
Hyprland 0.57.2, with isolated Lua feasibility tests in a nested Wayland session.
Guarded apply/revert, client-crash recovery, persistence failure, and virtual
hot-unplug are verified in a nested compositor. Physical mode changes and general
rule restoration are not certified. See [Phase 2 evidence](docs/phase-2-report.md)
and [compatibility research](docs/compatibility.md).

## Project documents

- [Phased implementation plan](docs/implementation-plan.md)
- [Progress tracker](docs/progress.md) — task status and evidence
- [Architecture and behavior](docs/architecture.md)
- [Compatibility research](docs/compatibility.md)
- [Validation strategy](docs/validation.md)
- [Guarded CLI and ownership contract](docs/phase-2-guide.md)
- [Phase 2 implementation evidence](docs/phase-2-report.md)
- [Contributing](CONTRIBUTING.md)

The first usable milestone is safe manual monitor editing (phases 1–3).
The profile milestone follows in phase 4; automatic switching is phase 5 and
remains opt-in. Packaging and a public release require the phase 7 acceptance gates.

## Run the inspector

Requires Python 3.12+ and `hyprctl` in a running Hyprland session. From a checkout,
using [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run monarch inspect
uv run monarch inspect --json
uv run monarch inspect --watch
```

Alternatively, create a virtual environment and install the checkout with
`python -m pip install .`. The distribution name is `monarch-displays`; the command
is `monarch`. Nothing is installed from PyPI by that project name in these steps.
No Qt dependency is required for this CLI. The future GUI uses the optional
`gui` extra (`PySide6>=6.8,<7`); no GUI is available yet.

The inspector includes connected-but-disabled outputs, advertised modes and
precise refresh rates. Default reports redact display identities and config
paths. Use `--show-identifiers` to include them in JSON for local inspection.
`--config /path/to/hyprland.lua` records an explicit path selection without reading
or executing it. Unverified paths/providers remain clearly marked. Inspection never applies or reloads configuration. Guarded writes use a separate
coordinator and independently verify ownership; profile switching is not available.

Watch mode refreshes after topology/config events and reconnects to the selected
instance with bounded backoff. It remains bound to the startup session signature;
a replacement compositor with a new signature requires restarting Monarch from
that session. `--json --watch` emits one JSON object per line. Ctrl+C stops it.

## Guarded previews

Phase 2 adds strict layout validation, typed Lua generation, a separate recovery
guard process, session locking, private journals/backups, atomic persistence, and
explicit terminal confirmation. These primitives are shared with the future GUI.

```sh
uv run monarch layout capture --output ~/.config/monarch/layouts/current.json
uv run monarch layout validate ~/.config/monarch/layouts/current.json
uv run monarch transaction status
```

Captured layouts contain monitor identities and are stored privately. Mutation is
restricted to a clean Hyprland 0.57.2 Lua session running an exact Monarch-owned
minimal root. An existing desktop config is never adopted or overwritten. See the
[guarded CLI guide](docs/phase-2-guide.md) before using `managed create`, `preview`,
or `recover`.

For the reproducible isolated acceptance test, with Wayland and render access:

```sh
uv run python tools/probe_recovery.py
```

It creates its own nested compositor and virtual outputs, exercises failure and
recovery, then terminates that compositor. It does not change parent monitor
settings. The GUI and normal save-on-login integration follow in Phase 3.

## Development

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

The lock file pins the development tools. CI checks Python 3.12, 3.13 and 3.14.
See [contributing](CONTRIBUTING.md) and the [Phase 1 report](docs/phase-1-report.md)
and [Phase 2 evidence](docs/phase-2-report.md) for the opt-in native probes and the distinction between automated,
nested-session, and physical-hardware evidence.

## License

[MIT](LICENSE). Third-party dependencies retain their own licenses; packaging
must include the applicable Qt/PySide notices and comply with their terms.
