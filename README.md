# Monarch

A Python and Qt monitor manager for Hyprland, starting with a read-only monitor
inspector. Visual layout editing, Lua configuration, saved profiles, and quick
setup switching are planned.

**Status: Phase 1 implemented — read-only CLI foundation.**
There is no monitor editor or stable release yet. The inspector can run from a
source checkout; the features below describe later implementation phases.

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
Physical monitor editing and general rule restoration are not certified. See
[Phase 1 evidence](docs/phase-1-report.md) and [compatibility research](docs/compatibility.md).

## Project documents

- [Phased implementation plan](docs/implementation-plan.md)
- [Progress tracker](docs/progress.md) — task status and evidence
- [Architecture and behavior](docs/architecture.md)
- [Compatibility research](docs/compatibility.md)
- [Validation strategy](docs/validation.md)
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
or executing it. Unverified paths/providers remain clearly marked. No apply,
reload, profile-switching or configuration-writing command is exposed.

Watch mode refreshes after topology/config events and reconnects to the selected
instance with bounded backoff. It remains bound to the startup session signature;
a replacement compositor with a new signature requires restarting Monarch from
that session. `--json --watch` emits one JSON object per line. Ctrl+C stops it.

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
for the opt-in nested compositor probe and the distinction between automated,
nested-session, and physical-hardware evidence.

## License

[MIT](LICENSE). Third-party dependencies retain their own licenses; packaging
must include the applicable Qt/PySide notices and comply with their terms.
