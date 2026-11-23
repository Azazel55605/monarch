# Guarded CLI previews and ownership

Phase 2 provides backend and recovery primitives for the future Qt editor.
Inspection remains safe to use in a normal Hyprland session. The write path is
currently restricted to an explicitly owned, minimal configuration session.

## Ownership contract

A supported write session uses a new private directory with two generated files:

- `hyprland.lua`: the exact minimal root that requires `monarch_monitors`.
- `monarch_monitors.lua`: versioned JSON data in a comment, a safe fallback rule,
  and deterministically generated typed monitor rules.

The root contains no desktop keybindings, startup commands, or other desktop
settings. It is not a replacement login configuration or a migration tool.
Phase 3 adds the GUI and must design normal desktop integration explicitly.
External monitor controllers and arbitrary runtime rule edits are outside this
exclusive-control contract. Comparing visible settings cannot prove the absence
of every hidden rule; reload clears runtime rules only in this known owned root.

The guard independently verifies the actual compositor config path, clean
Hyprland 0.57.2/Lua provider, exact file contents, private ownership/permissions,
known observed baseline, topology and display identities. A CLI `--config` hint
cannot authorize mutation. Inaccessible process metadata, other versions, existing
Lua roots, external edits, symlinks/hardlinks, and unfinished recovery block writes.
No command automatically adopts or rewrites an existing desktop configuration.

## Layout data

Capture current settings, or validate an edited private layout against live outputs:

```sh
uv run monarch layout capture --output ~/.config/monarch/layouts/current.json
uv run monarch layout validate ~/.config/monarch/layouts/current.json
```

Capture contains monitor identities, unlike the redacted inspector report. Its
output file must be new; parent storage must be private. The CLI creates missing
private leaf directories and writes files with mode 0600. Without `--output`,
capture prints the explicit identity-bearing layout to stdout.

Schema version 1 is a data-only object with `schema_version` and `outputs`. Every
output provides `name`, `make`, `model`, `serial`, `mode`, `scale`, `transform`,
`x`, `y`, `enabled`, and `mirror`. Mode is `WIDTHxHEIGHT@HZ` without `Hz` at the end;
`preferred` is allowed for disabled entries and emergency recovery only. Empty
`mirror` means an independent output. Identity values come from capture, not
invented aliases. Unknown fields/versions and missing fields are rejected.

Each connected output, including disabled outputs, must appear exactly once.
Enabled modes must be advertised; scale must be finite, 0.25–8, and produce whole
logical pixels. Transform is 0–7 and positions are signed integers. At least one
enabled, independent root must remain. Mirrors require enabled roots; chains,
cycles, missing targets, topology changes, and identity changes are rejected.
Custom modelines and advanced settings are deferred.

## Prepare an owned configuration

```sh
uv run monarch managed create \
  --directory ~/.config/monarch/owned-example \
  --layout ~/.config/monarch/layouts/current.json
```

This only creates files in a new directory. It does not change the running
compositor, install an include, or alter login startup. An isolated compositor
must have been explicitly started with that generated root before preview can
work. For a reproducible controlled session, use the native probe below rather
than changing a normal desktop config to satisfy the check.

## Preview and confirm

In an already running, verified owned session:

```sh
uv run monarch preview ~/.config/monarch/layouts/edited.json \
  --directory ~/.config/monarch/owned-example
```

The independent guard locks the session, saves a durable recovery journal and
backup, and arms a monotonic deadline before the first monitor mutation. It
resets sticky runtime rules by reloading the owned baseline, then enables roots,
enables mirrors, and disables sources in that order. Each change is observed
before proceeding, so a silently rejected destination cannot lead directly to
source disablement. Successful command replies alone are insufficient.

Type `keep` in the interactive terminal to confirm runtime state. Any other line
reverts. Use `--persist` when invoking preview to request disk persistence *only
if Keep is confirmed*. Runtime-only Keep leaves the monitor file unchanged;
later previews recognize that confirmed runtime baseline. The default deadline
is 15 seconds, including apply and persistence; `--seconds` accepts 1–60.

Without an interactive terminal, the preview always expires and reverts. Piping
`keep` does not bypass confirmation. Ctrl+C/client termination closes the control
pipe and requests recovery. There is no unattended confirmation CLI switch.
Future GUI clients use the same asynchronous `Coordinator`/`Preview` API and
must explicitly send a transaction-ID-bound confirmation before the deadline.

## Recovery and conflicts

```sh
uv run monarch transaction status
uv run monarch recover
```

A guard process runs in a separate session from the client and holds the session
lock throughout recovery. Client EOF, deadline expiry, drift/hotplug, a failed
command, configuration errors, and guard SIGTERM/SIGINT cause rollback. SIGKILL
of the guard or a machine crash leaves a journal for explicit recovery.

Backups and journals are private under
`$XDG_STATE_HOME/monarch/<session-key>/` (default `~/.local/state`); session locks
are under `$XDG_RUNTIME_DIR/monarch/<session-key>/`. Atomic writes use temporary
files, fsync, replacement and directory fsync. Expected hashes detect external
changes; cooperating clients share a lock. This does not provide atomic CAS
against arbitrary uncooperative filesystem writers.

Persistence rollback restores the exact known monitor file before reloading and
restoring the known runtime baseline. External edits are preserved, not replaced
by a forced backup. Conflicts or unavailable compositor state leave
`recovery_required` and block another preview until resolved. Keep the journal
and backup. After reviewing a same-session conflict, restoring the exact known
managed bytes permits an explicit retry of `recover`.

If displays disappear, recovery does not apply their old settings to replacement
hardware. It enables a preferred-mode independent root on an available output,
disables no further outputs, and reports `degraded`. The old layout file remains
available; capture a new valid plan before attempting more topology-specific edits.

Recovery binds to signature, boot and command-socket inode, and rechecks active
config ownership. A replacement compositor never receives stale commands. Status
counts unfinished journals from other sessions; such journals block reuse of the
same owned root. They require manual backup review outside a running mutation
transaction, not `recover` replay into the new session. Do not delete unfinished
journals merely to bypass that check.

## Isolated acceptance probe

```sh
uv run python tools/probe_recovery.py
```

The probe needs Hyprland 0.57.2, a parent Wayland session, and GPU render-device
access. It starts a temporary nested compositor, verifies the Wayland backend and
new signature, creates two virtual outputs, and runs the recovery matrix. It
terminates only its own compositor on completion. The parent monitor layout is
not changed. See the [evidence report](phase-2-report.md) for results and limits.
