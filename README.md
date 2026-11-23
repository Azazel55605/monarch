# Monarch

A planned Python and Qt monitor manager for Hyprland, with visual layout editing,
Lua configuration support, saved profiles, and quick setup switching.

**Status: planning. No application or installable release exists yet.**
The repository currently contains the design, implementation roadmap, and progress
tracker. Feature descriptions below describe intended behavior.

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

Lua is the primary configuration path. The initial compatibility target is
Hyprland 0.57.2; this is a research baseline, **not a tested support claim**.
Upstream documents Lua configuration and runtime evaluation through `hyprctl`;
see the [compatibility research](docs/compatibility.md) for sources and limitations.

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

## Development

There are no installation or launch commands yet. Phase 1 introduces the Python
package, development environment, CI, and a read-only monitor inspector. Follow
progress in the tracker rather than assuming planned commands already exist.

## License

[MIT](LICENSE). Third-party dependencies retain their own licenses; packaging
must include the applicable Qt/PySide notices and comply with their terms.
