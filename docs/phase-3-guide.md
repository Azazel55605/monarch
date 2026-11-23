# Qt manual editor

Launch from a Hyprland session:

```sh
uv run --extra gui monarch gui
```

An optional `--directory /path/to/managed-storage` selects an existing owned or
registered monitor directory. Otherwise the editor discovers registration beside
the resolved root. A regular desktop starts in inspection/draft mode until setup.
No monitor changes happen just by opening the window.

## Edit and preview

Select a display in the canvas or list. Drag active independent displays to arrange
them; edges align when released nearby. Arrow keys move the selected canvas item
one logical pixel, or ten with Shift. Exact X/Y controls use the same draft model.
Disabled displays occupy a separate canvas lane rather than obscuring active ones.

The side panel offers advertised resolution/refresh choices, scale, all eight
rotation/flip transforms, enabled state, and mirror targets. Canvas sizes reflect
scale and rotation. Refresh precision is retained, and unrelated edits preserve
the original scale even when its decimal expansion does not fit the spin box.
An unsupported current mode is shown as unsupported, not silently replaced by the
first advertised choice. Custom modelines are not editable in this alpha.

Inline validation explains invalid scale/geometry, missing or changed identities,
invalid mirror roots/chains, unadvertised modes and all-disabled layouts. Apply
stays unavailable for invalid or stale drafts. Identify labels use native windows
on the corresponding Qt screens, close automatically, and do not modify modes.

Preview changes disables editing while the independent guard applies and observes
the layout. Its deadline begins before mutation; the dialog shows the actual
remaining monotonic time. Keep confirms runtime state. Select **Save on login**
before preview if Keep should also persist the managed monitor file. An already
confirmed runtime layout can be saved later using **Save current layout**.
Revert, Escape, timeout, client exit or failed application requests restoration.
Closing the GUI while previewing closes the guard control pipe; the guard survives.

Discard edits returns to the latest observed layout. Refresh preserves drafts.
If a hotplug or external change occurs while editing, the draft remains visible
and becomes stale. Revalidate checks it against the latest topology; it cannot
make missing displays valid. Discard loads the new connected set. After a topology
change, review integration to establish the current connected baseline if needed.

## Desktop integration

**Set up monitor management** is an explicit ownership operation. It supports a
clean Hyprland 0.57.2 Lua release, a verified config target, user-owned regular
files, and basic monitor rules only. Symlinked paths, group/world-writable config
files, arbitrary dynamic monitor management, and advanced HDR/VRR/color/modeline
rules are outside this registration contract. Keep other display managers disabled.

1. Confirm the root file. Add every other config file loaded by that root, including
   transitive includes. Monarch does not parse or execute Lua to discover that set.
2. Preview the exact appended block, managed file path and current display baseline.
3. Review the files and basic-monitor ownership/reload agreement, then approve and
   install the reviewed include. Until that final action, setup only reads files.

Installation appends one clearly marked `require("monarch.monarch_monitors")`
block and retains every existing root byte in place. It preserves root permissions
and saves a private original backup. It creates a private `monarch` directory
beside the root with generated monitor data, registration hashes and backups.
The current observed layout becomes the initial saved baseline; existing draft
edits are still subject to preview and Keep. Appending an include can trigger
Hyprland's own automatic reload, so approval covers running the reviewed config.

Monitor semantics are delegated, not automatically migrated. Remove conflicting
monitor directives/controllers and do not register configs relying on unsupported
advanced monitor behavior. Unrelated desktop code is preserved byte-for-byte,
but reloading executes that code again. Registration is an operator-reviewed trust
contract, not a Lua sandbox or proof of deterministic configuration behavior.

The guard verifies root/dependency hashes before every transaction and recovery.
Edits to registered sources pause writes until reviewed. Reopen setup, preview the
current revision, approve it and install the review. The include is not appended a
second time. Re-review backs up the old managed settings and establishes the current
connected baseline. Root, dependency, registration or monitor-file changes between
preview and installation are rejected. Conflicts preserve external edits.

## Config lookup and reload

Explicit `--config`, `HYPRLAND_CONFIG` and safe-mode paths retain their existing
verification rules. For default paths, the editor follows the tagged 0.57.2 search:
XDG config home, HOME's `.config`, XDG config directories, then `/etc/xdg`, with the
`hypr/hyprland.lua` suffix. The verified search is enabled for hyprutils 0.14.3/0.14.4.
Unsupported or ambiguous metadata stays read-only.

Ordinary reload caches the config path. The guard therefore uses `reload full-reset`
for verified XDG targets, deliberately reinitializing the Lua context and selecting
the reviewed root. Explicit config paths use ordinary reload. The setup dialog
explains this distinction. No unconditional raw reload/eval GUI action is exposed.

## Recovery

The GUI exposes recovery when an unfinished transaction is detected. It uses the
same coordinator and journal as `monarch recover` and the CLI. The existing boot,
signature, socket-generation, file-conflict and session-lock safeguards still apply.
A transaction additionally pins the integration contract fingerprint. Changed
registration cannot authorize replay of an older transaction.

Backups/journals stay private under XDG state storage, and integration backups stay
inside the private registered directory. Foreign-session journals require manual
review and are not replayed. See the [recovery guide](phase-2-guide.md) for details.
A legacy Phase 2 exact-root journal remains compatible when its root is unchanged.

## Current boundaries

This is the manual-editor alpha. Profiles, quick switching and automation are later
phases; advanced monitor options remain unexposed. Basic behavior is tested through
synthetic Qt interactions, a real nested Wayland compositor and read-only physical
startup. Physical mode changes, real docking/suspend, arbitrary config programs
and hardware/GPU crash recovery are not certified. See [evidence](phase-3-report.md).
