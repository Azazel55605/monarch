# Phase 5 implementation and evidence

Date: 2026-11-23. Package: `0.1.0.dev5`.
Scope: M5.1–M5.3. Software implementation is complete; the physical dock/resume
acceptance gate remains open.

## Delivered software

- Pure exact/subset matching, priority/exactness/specificity ranking, tie/no-match
  preservation and per-profile rejection reasons. Unknown extras retain their
  current basic settings. Physical ambiguity is refused by default; explicitly
  saved-port rules provide an opt-in fixed-cabling contract.
- A session-scoped owner, event-driven discovery plus authoritative polling,
  stable-topology debounce, reconnect/resume invalidation and generation checks.
- Shared manual pin/resume across GUI/tray/CLI, including editor changes and
  preemption of active automatic previews. The independent guard retains the
  session mutation lock; manual clients never bypass it.
- Durable same-input suppression and bounded failure backoff. Self-generated
  reload/settings events do not loop. Keep/Revert remains mandatory, and automatic
  previews cannot persist compositor startup configuration.
- Explicit Qt policy/rule controls, status/explanations, CLI control/run commands,
  and separate opt-in XDG login-entry installation/removal with conflict protection.

## Recovery contract extension

For an authorized automatic transaction only, a changed connected identity set
can use a freshly captured basic runtime layout as the rollback baseline. The
root/dependency/monitor hashes, session identity and error checks remain enforced.
Unexplained drift on an unchanged physical set still refuses adoption. The journal
records the snapshot and original startup content before mutation. Revoking policy
or manual control cancels apply/confirmation but permits rollback.

Automatic guards pin the session control generation plus exact policy and catalog
content. A queued GUI offer retains those same authorization values instead of
using whichever policy happens to be current when the GUI handles it.
The [guide](phase-5-guide.md) describes the operator's basic-monitor delegation.

## Automated and package evidence

| Layer | Result |
| --- | --- |
| Python 3.13.12, development environment | 198 tests passed |
| Python 3.12.16, installed GUI wheel | 198 tests passed; installed wheel |
| Python 3.14.10, installed GUI wheel | 198 tests passed; installed wheel |
| Ruff / formatting / strict mypy | Passed; 42 typed source files |
| Source distribution / wheel | Built successfully |

Coverage includes pure
ranking, ties, subset extras, absent/duplicate serials, connector changes, fixed-port
opt-in, invalid/future policy preservation, stability/storms, owner contention,
manual preemption, policy/catalog revocation, retry limits, durable suppression,
resume/reconnect invalidation, compositor-generation replacement, topology snapshot
revert, refusal of same-set drift, real Qt offers/confirmation, dirty edits, and
private autostart create/remove/conflict/quoting. Qt tests use the offscreen backend.

The generated desktop entry also passes the host's `desktop-file-validate`,
including interpreter/catalog paths with spaces and percent characters. This is
file-format validation, not proof that a session autostart host executes it.

## Native virtual hotplug acceptance

Command: `uv run --extra gui --group gui-dev python tools/probe_automation.py`.
The probe creates an isolated nested Hyprland 0.57.2 and checks its backend/signature.
It uses actual virtual output create/remove, production Qt/worker/coordinator/guard,
private profiles and policy, and the default guard deadline. PySide6/Qt is 6.12.0;
the host is Arch-based Linux with hybrid AMD/NVIDIA graphics.

Observed:

- Unmatched initial topology preserved without applying.
- Removing a virtual display selected the eligible profile, presented confirmation,
  and kept runtime settings after Keep.
- The guard used a snapshot for the changed topology and retained the original
  startup monitor file byte-for-byte.
- A manual GUI change/Keep pinned automation; no conflicting auto preview followed.
- Resume selected again. Revert restored the manual layout and did not repeat.
- Adding a virtual output produced no match and preserved state. Removing it again
  selected once, presented a fresh confirmation and kept successfully.
- Parent physical monitor mutations: zero. No login autostart was enabled on the host.

Virtual outputs expose empty make/model/serial fields. The initial unbound fixture
correctly remained ambiguous and made no changes. The successful probe explicitly
configures saved-port bindings for these synthetic connectors. It is native IPC/
hotplug/recovery evidence, not hardware-identity or EDID acceptance. Physical identity
ambiguity and unique-serial remapping have separate automated tests.

Qt emitted empty-font-description and Wayland text-input diagnostics; the listed
interactions completed. The synthetic editor screenshot is
[automation status](assets/monarch-automation.png).

## Open acceptance gate

Real dock/undock, physical display modesetting, suspend/resume on the host's driver
stack, and a fresh login through its actual startup host remain unverified. Reconnect
and long-gap handling are tested synthetically; virtual output removal/addition is
not physical docking. The Phase 4 virtual disable/re-enable timeout remains recorded.
M5.3 and the overall Phase 5 gate remain **In progress** for that hardware/session
acceptance, rather than claiming an unobserved release gate passed.

Automatic matching and login startup remain disabled by default. The work does not
change physical monitor settings or enable a host startup entry. Advanced monitor
options and release packaging remain later phases.

## Upstream references

[Hyprland IPC events](https://wiki.hypr.land/ipc/) define socket2 monitor/config events.
The [XDG autostart specification](https://specifications.freedesktop.org/autostart/latest/)
and [Desktop Entry Exec quoting](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html)
define login-entry behavior and argument escaping. Having a valid entry does not
imply that a plain Hyprland session runs an XDG autostart host.
