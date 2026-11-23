# Opt-in automatic profile previews

Launch `uv run --extra gui monarch gui --tray`, then open **Automation…**.
Automatic switching and login startup are **off by default**. Select eligible
profiles, matching mode and priority, then explicitly enable previews and Save.
Existing [basic monitor ownership/integration](phase-3-guide.md) requirements apply.

## Matching and confirmation

Rules rank by higher priority, then exact matching, then more required displays.
A tie makes no changes. Neither a missing profile nor an absent/ambiguous identity
is guessed. The status row explains the outcome; its tooltip includes rejection
reasons. Profiles referencing unavailable modes are ineligible.

**Exact** requires the full connected set, including disabled outputs. **Subset**
requires the profile's displays and preserves every extra output's current basic
settings, including whether it is enabled. It never silently disables an unknown
extra. The resulting complete layout still passes normal geometry/mirror/mode
validation, including keeping a usable unmirrored display.

Physical identity matching is the default. Unique serials can follow connector
renames. Missing or duplicate serials retain Phase 4's conservative rules.
**Saved ports** is a separate, explicit per-rule option: bind each stored display
to its stored connector name, while still checking make/model/serial. Use this
only with fixed cabling when physically identical displays cannot be distinguished.
It does not follow renamed connectors or override a different known serial.
Without that option, identical displays remain ambiguous and are not switched.

The watcher waits for a stable topology before a preview. The editor is shown and requests focus, with the real guard deadline visible. **Keep** confirms runtime state;
Revert, timeout or client exit restores the captured baseline. Automatic previews
never persist the startup monitor file. To save on login, make an explicit manual
preview with that option selected. A selected layout already matching the session
needs no preview and makes no changes.

## Recovery when the connected set changes

Enabling automation delegates exclusive basic monitor control for eligible
setups. On a topology/identity change, the guard can capture the current connected
basic layout as its recovery baseline. It still verifies the registered root and
dependencies, monitor file, session generation and config errors before mutation.
It records the baseline and arms recovery before reloading/applying. The original
startup file is retained; rollback can restore the newly connected baseline even
when the disk layout describes an earlier connected set.

This narrow permission does **not** adopt unexplained runtime changes on the same
physical set, arbitrary advanced monitor state, dynamic Lua graphs, HDR/VRR/color
rules, or other display controllers. The existing basic-config contract remains
in force. Manual previews keep their ownership rules. If a new topology already
matches a profile and no automatic transaction ran, a subsequent manual edit may
still require explicit integration review to establish a recoverable baseline.

Policy changes, disabling automation, catalog edits and manual session overrides
revoke an active automatic preview. Revocation requests rollback; it does not stop
rollback from restoring its baseline. Root/dependency conflicts and foreign
sessions retain the existing fail-closed recovery rules.

## Manual control, storms and failures

Manual editing, loading/switching a profile, or starting a manual preview pins the
session. Other Monarch windows share that override. **Resume automatic switching**
in the editor/tray clears it explicitly. A manual client revokes an automatic
preview and waits briefly for its recovery; it never steals a transaction lock.
If recovery cannot finish, resolve the journal before retrying a manual change.
Pins last for this compositor session, across Monarch restarts, until Resume.

There is at most one automatic owner per session. Other windows remain usable for
manual changes and show that another window owns automation. The event socket
coalesces storms; authoritative periodic discovery also catches missed events.
Reconnect and long wall-clock gaps require fresh settling. A replacement compositor
generation is never silently adopted: restart Monarch in the new session.

Own apply/reload events do not create another selection cycle. A kept, already
satisfied, declined or interrupted attempt is not repeated for an unchanged
policy/catalog/topology/control generation. Revert or timeout is treated as a
rejection. A real topology change (including leaving and returning), rule/catalog
revision, or Resume permits a new attempt. A failed application retries after
30 seconds, then 60 seconds, and blocks after the third failure until that input
changes. These counters persist under the session runtime directory so restarting
Monarch does not clear a rejected preview or bypass the retry bound.

Dirty drafts and modal dialogs are preserved. Closing the application stops its
watcher/tray and rolls back a pending preview; it does not disable the saved policy
or remove an explicitly installed login entry.

## CLI and login startup

```sh
monarch automation set-rule Desk --match exact --priority 10
monarch automation set-rule Presentation --match subset --priority 5
monarch automation enable
monarch automation status
monarch automation run
monarch automation pin
monarch automation resume
monarch automation disable
monarch automation remove-rule Presentation
```

Use `--bind-connectors` on `set-rule` only for explicitly reviewed fixed-port
bindings. `automation --store /private/catalog ...` selects another profile/policy
directory. The runner requires the Qt extra and a Hyprland environment; it starts
the editor minimized with the optional tray and surfaces each confirmation.
It does not turn the policy on by itself. Keeping the normal editor open also
runs the watcher when the saved policy is enabled. Policy commands work offline;
session pin/resume requires a running session. Status reports the configured policy,
login entry, session pin, last decision and heartbeat freshness.

Login startup is a separate explicit choice:

```sh
monarch automation autostart enable
monarch automation autostart status
monarch automation autostart disable
```

The GUI checkbox performs the same operation. It creates a private, owned
`$XDG_CONFIG_HOME/autostart/monarch-automation.desktop` pointing to the current
absolute Python interpreter and selected catalog. A private receipt records its
hash. Existing or externally edited entries are preserved rather than overwritten
or deleted. Moving/removing the virtual environment invalidates its command;
disable the entry before moving it and re-enable from the new installation.

This uses the [XDG autostart specification](https://specifications.freedesktop.org/autostart/latest/),
which requires a session autostart host. Plain Hyprland does not itself guarantee
that desktop entries run. If the session has no such host, configure its existing
session launcher to execute `monarch automation run` once; Monarch does not edit
the desktop Lua root to install another startup command. The runner exits before
creating a window when no Hyprland environment is present. No root service,
background daemon without confirmation, or default autostart is installed.

## Storage and current evidence

`automation.json` sits beside the profile catalog, is private schema-1 JSON and
contains `enabled` plus rules (`profile`, `mode`, `priority`, `connectors`).
Missing `connectors` means false. Unknown schema versions/fields and invalid rules
are rejected unchanged. Policy/catalog edits share the catalog lock and use atomic
writes with conflict checks. Autostart receipts remain in the default XDG Monarch
directory even for a custom catalog. Session controls, attempt history and heartbeat
status live under `$XDG_RUNTIME_DIR/monarch/<session-key>/`.

See the [Phase 5 report](phase-5-report.md). Automated and native virtual-hotplug
checks are complete. Physical dock/undock, suspend/resume and fresh-login execution
on the user's session still need hardware/session acceptance; these are not implied
by virtual-output or synthetic timing tests. The Phase 4 virtual-output
re-enable timeout remains a separate recorded limit.
