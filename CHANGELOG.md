# Changelog

## 0.1.0rc2 — tray and canvas feedback

- Close to an available tray by default, retaining drafts and the monitor watcher;
  explicit Quit exits, and `--no-tray` or no tray host retains exit-on-close.
  Active previews stay reachable; background operation enables no new automation.
- Keep display outlines visible with flat system palettes, including theme colors
  that make the normal border indistinguishable from the monitor fill.
- Snap during dragging within a consistent 12 screen-pixel tolerance at any zoom;
  ignore distant displays and hold Alt for free placement.
- Existing VRR setup/apply restrictions and native timeout gates remain open.
  Automatically configuring unknown external displays is future work.

## 0.1.0rc1 — testing candidate

This candidate packages the implemented manual editor, profiles and opt-in automatic
previews for feedback. It is not a tagged stable release or an AUR publication.
Physical dock/resume/fresh-login acceptance and advanced-write recovery remain open.

- Native Python/PySide6 editor with canvas, numeric settings, identity/mirror checks,
  guarded Keep/Revert and explicitly reviewed Lua integration.
- Named profiles, import/export, GUI/tray/terminal switching and optional topology
  matching with priorities, shared manual pin/resume and bounded failure handling.
- Native Qt theme discovery/style selection, a bundled original SVG icon, desktop
  launcher, offline quick-start/recovery help and dependency notices.
- Read-only advanced-state panel, conservative basic-state guards, tagged mirror-ID
  normalization and redacted GUI/CLI diagnostics with private/no-clobber exports.
- Source/wheel and native Arch packaging, CI artifacts and installation/removal checks.

### Boundaries carried into this candidate

Writes require clean Hyprland 0.57.2 Lua, verified configuration ownership, and known
8-bit sRGB/default SDR with inactive VRR on active outputs. Existing VRR/10-bit/HDR
or unknown state can make the editor inspection-only. Advanced VRR, depth, color/HDR
and ICC writes are explicitly deferred. No settings are automatically reset.
Legacy hyprlang writing/conversion and custom-modeline editing are out of scope.
The Phase 4 virtual disable/re-enable timeout, candidate nested output-creation/
mirror timeouts and physical release matrix remain open.
Automation and login startup are disabled by default; all previews require Keep.
