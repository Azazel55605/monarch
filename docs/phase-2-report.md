# Phase 2 implementation and recovery evidence

Date: 2026-11-23. Scope: M2.1–M2.5. Package: `0.1.0.dev2`.
Phase 2 implements guarded CLI monitor previews and storage/recovery primitives.
The Qt editor and normal desktop config integration remain Phase 3 work.

## Delivered behavior

- Strict versioned layout data, advertised-mode and identity validation, finite
  scale/whole-pixel geometry, transforms/negative coordinates, complete topology,
  mirror-root validation, and rejection of layouts without a usable output.
- Revalidated typed Lua generation with decimal byte escaping; no shell or raw
  Lua CLI. The inspection transport keeps its read-only command allowlist.
- A shared asynchronous coordinator with an independent guard process. The guard
  holds the session lock, journals/backs up before mutation, owns the monotonic
  deadline, observes each update before proceeding, and handles explicit Keep/Revert.
- Roots are enabled before mirrors, and sources are disabled last. A rejected
  destination stops later writes before source disablement.
- Explicit runtime-only Keep versus confirmed persistence. Known runtime and disk
  baselines remain separate and can be recognized on subsequent previews.
- Private managed storage with regenerated content checks, hash conflicts,
  exclusive creation, atomic replacement, file/directory fsync, and unique backups.
  External edits and unsupported roots are preserved rather than overwritten.
- Deadline, client EOF/SIGKILL, command failure, topology drift, persistence/reload
  failure, and stale-session recovery handling. Guard SIGKILL leaves a journal for
  explicit recovery. Foreign unfinished journals block reuse of the same owned root.
- CLI layout capture/validate, owned-root creation, guarded preview, recovery, and
  redacted transaction status. Keep requires a terminal; piped input cannot confirm.

## Ownership and compatibility decision

Mutation requires a clean Hyprland 0.57.2 Lua session whose actual config path is
verified from compositor process metadata. Both root and monitor content must
match Monarch's exact minimal generated format. This is a dedicated owned-session
contract; no arbitrary desktop Lua is imported, rewritten, or automatically
adopted. The initial rule reset reload executes only this known root.

External controllers are unsupported. Basic observed-state checks cannot detect
every hidden advanced/runtime rule. That limitation is not presented as solved by
snapshot rollback. Ordinary desktop integration must extend the ownership model
explicitly in Phase 3. The read-only inspector remains usable without ownership.
See the [CLI guide](phase-2-guide.md) and [architecture](architecture.md).

## Automated and packaging results

| Environment | Result |
| --- | --- |
| Python 3.12.16, installed wheel | 117 tests passed; CLI version verified |
| Python 3.13.12, development environment | 117 tests passed; Ruff lint/format and strict mypy passed |
| Python 3.14.10, installed wheel | 117 tests passed; CLI version verified |
| Source distribution and wheel | Built successfully with `uv build` |

The suite includes real subprocess guard lifecycle tests with a synthetic transport,
Linux `/proc` verification, session locks, actual parent SIGKILL, monotonic timeout,
PTY confirmation/persistence, and rejection of piped Keep. It does not require a
live compositor or GPU. Fault injection covers individual mutations, silently
rejected destinations, changed identities/topology, compositor loss, stale sessions,
foreign journals, external edits, symlinks/hardlinks, failed persistence reload,
manual recovery, and atomic replacement during a concurrent journal read.

The concurrent-read regression permits an already-open old snapshot with zero
links after replacement; linked copies with more than one link remain rejected.
No claim of cross-process filesystem CAS is made against uncooperative writers.
Cooperating Monarch clients serialize through the guard's session lock.

Hosted CI is tracked independently; a local pass is not a hosted pass. The first
published Phase 2 commit's Actions run will provide the hosted matrix evidence.

## Native isolated acceptance

Command: `uv run python tools/probe_recovery.py`.

Environment: Garuda/Arch-based Linux, kernel 7.3.5, Hyprland 0.57.2, Python 3.13.12,
Wayland parent session, hybrid AMD integrated/NVIDIA mobile graphics. The test
uses the nested Wayland backend and two virtual outputs at advertised modes.
Qt is not involved. GPU render-device access was needed outside the sandbox.
No parent monitor settings, normal config files, or session startup were changed.

The probe verifies a new session signature and the nested Wayland backend before
creating virtual outputs. It generates a private minimal owned root and uses the
production coordinator, guard, typed writer, journal, and managed-file storage.
A local wrapper rejects exactly one reload after persistence for the injected
failure case; the file write, restore, subsequent reload, and observed-state
checks remain real. It terminates only the compositor it started.

Observed final result:

```json
{
  "hyprland": "0.57.2",
  "backend": "nested-wayland/virtual",
  "preview_revert": true,
  "deadline_recovery": true,
  "client_eof_recovery": true,
  "client_sigkill_recovery": true,
  "explicit_persistence": true,
  "failed_persistence_reload_restores_file": true,
  "virtual_hot_unplug_degraded_recovery": true,
  "guard_sigkill_manual_recovery": true,
  "parent_monitor_mutations": 0
}
```

Successful recovery checks compare observed settings with the known baseline and
verify the monitor file, not merely command exit status. After virtual hot-unplug,
the test verifies a usable independent output and the `degraded` result. After
client SIGKILL, the independent guard finishes without its parent. After guard
SIGKILL, a new recovery process uses the durable journal in the same compositor
generation. A normal three-output read-only inspection also still works.

## Acceptance boundaries

This resolves Phase 2's real-session recovery gate within the owned configuration
contract. It does not certify physical connector/mode changes, mixed-GPU scanout,
DPMS/lid behavior, real docking/suspend, hardware/GPU/compositor crash recovery,
or any native Qt flow. The physical acceptance matrix remains open for the editor
and release phases. A software guard cannot guarantee recovery from hardware
failure. Config conflicts and unavailable sessions remain visibly unfinished;
no forced overwrite or stale-session replay is used to make tests pass.
