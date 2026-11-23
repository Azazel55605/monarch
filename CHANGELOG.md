# Changelog

## 0.1.0rc5

- Display controls grow with the sidebar and scroll when window height is limited.
- Eligible automatic profiles take priority. An optional fallback extends unfamiliar
  external displays to the right at the largest advertised resolution and fastest
  refresh rate at that resolution.
- A tray click opens quick controls for profiles and external displays. The external
  layout bar previews four directions of extension or duplication.
- Automatic previews and tray actions use the existing Keep/Revert guard.

## 0.1.0rc4 — VRR-only cached-rule refresh

- Fix VRR-only updates on the supported Hyprland 0.57.2 baseline, whose active
  monitor-rule comparison omits VRR. The guard uses an observed one-pixel soft
  refresh and restores the requested position before accepting the final state.
- Keep session/config/topology checks between refresh stages and mandatory final
  VRR readback. No global VRR or hard mode changes are used for the workaround.
- Add upstream-shaped cached-rule regression coverage for Keep/Revert/persistence,
  partial failure, and config conflicts between stages. Report requested/observed
  VRR state when an acknowledged update remains ineffective.
- External global VRR changes still require restoring/reviewing the owned baseline;
  physical validation of this compatibility fix remains pending.

## 0.1.0rc3 — explicit VRR Off/On

- Per-monitor VRR Off/On in the editor, guarded previews, profiles, rollback and
  Save on login. Every generated output rule carries an explicit policy.
- Layout schema 2 with strict integer VRR values. Basic-only schema-1 layouts are
  interpreted as Off; legacy module bytes and old recovery journals stay readable.
  Old profile data is backed up before a layout-schema migration is written.
- Active VRR is permitted when it matches an owned Off/On baseline. Unknown state,
  unadvertised On capability and an unobserved write still fail closed. Conditional
  modes are not inferred from an active boolean and remain unavailable.
- Software and virtual parser validation are separate from target physical VRR
  acceptance. HDR, bit depth and color/ICC writes remain deferred.

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
