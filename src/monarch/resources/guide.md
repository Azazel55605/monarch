# Monarch quick start and recovery

This is a 0.1.0 release candidate for testing, not a completed hardware-certified
release. Python 3.12+ is required. The native Arch package uses distro PySide6/Qt.

## Start and inspect

Launch Monarch from the application menu or run `monarch gui --tray` in Hyprland.
Opening the editor never applies settings. Appearance follows the system Qt theme;
use the Appearance menu to choose another available style.

Read the status banner first. Monitor writes require the clean Hyprland 0.57.2 Lua
release, a verified owned/registered config, and known basic state on active outputs:
8-bit sRGB/default SDR with inactive VRR. Advanced settings shows observations and
why advanced writes are unavailable. Active VRR/10-bit/HDR or unknown observations
can make the editor inspection-only. Monarch does not turn those settings off.

## Set up, preview, and save

Use Set up monitor management to review the include, current baseline and every
operator-declared config dependency before approving integration. Registration
assumes exclusive basic monitor control. Arbitrary Lua/ICC/global dynamic color
rules and other display controllers are outside its recovery contract.

Arrange displays or edit numeric settings. Apply starts a guarded preview; use
Keep only if the layout works. Revert, timeout or client exit requests restoration.
Save on login persists only after Keep. A profile saved in the catalog does not
by itself change startup monitor settings.

Profiles offers observed/draft capture, update, rename, delete and import/export.
Load to editor keeps mutation separate; Switch profile starts visible confirmation.
Missing displays and ambiguous identities need explicit resolution.

## Optional automation

Automation is disabled by default. Automation… selects eligible profiles and
priority/exact/subset matching. Every automatic preview still needs Keep; automatic
changes never persist the startup file. Manual editing/switching pins the session.
Use Resume automatic switching to release that override. Saved ports is an explicit
fixed-cabling option for otherwise ambiguous displays.

Start at login is a separate opt-in XDG entry. A session autostart host must run it;
plain Hyprland alone does not guarantee that. `monarch automation run` starts a
minimized editor/tray without enabling the policy. Closing the editor hides it to
an available tray and preserves drafts and the running monitor watcher. Open it
again from the tray; use Quit Monarch to exit. During a preview, finish Keep/Revert
before hiding. Without a tray host, closing exits normally. `monarch gui --no-tray`
also exits on close. Tray/background operation does not enable automatic switching.

## Problems and recovery

Help → Redacted diagnostics collects an offline/shareable snapshot. Review before
sharing: geometry and capability flags remain, but identifiers, paths, profile
names, config contents and raw logs are omitted. `monarch diagnose` works in a
terminal; `--output NEW.json` writes a new private file and never replaces an old one.

If a preview fails, inspect `monarch transaction status`. The GUI recovery button
or `monarch recover` can retry retained recovery for the SAME compositor session.
External config or advanced-state changes can require local review first. Never
delete journals, overwrite changed configs, or replay a foreign-session journal
as a shortcut. The independent guard survives client death; guard/compositor/GPU
failure cannot guarantee an automatic display restoration.

Before uninstalling: close previews, resolve current-session recovery, disable
login startup with `monarch automation autostart disable`, and choose Quit Monarch from the tray.
Package removal preserves user profiles, config integration, backups and journals.
The generated Lua include can remain without Python installed. If removing that
integration, review/remove its marked root block before deleting the referenced
module; do not blindly restore an old full-root backup over newer edits.

## Testing feedback

Record the package/version, generic display topology, exact steps, expected/actual
behavior, whether Keep/Revert worked, and whether this was offscreen, nested or
physical hardware. Attach a reviewed redacted report; do not share raw serials,
EDID, private configs or logs. Physical docking/resume/fresh-login and advanced
VRR/HDR/ICC/depth rollback remain open acceptance, not claims of this candidate.

Full guides and the acceptance tracker: https://github.com/Azazel55605/monarch/tree/main/docs
