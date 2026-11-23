# Validation and release gates

Status: Phase 1–5 automated and native checks have run; see the
[Phase 2 evidence](phase-2-report.md), [Phase 3 evidence](phase-3-report.md),
[Phase 4 evidence](phase-4-report.md), and [Phase 5 evidence](phase-5-report.md).
Native GUI/apply/recovery checks use a real nested compositor with virtual outputs.
Physical GUI startup/discovery is verified read-only; parent modesetting and the
full release matrix remain open. Automated Qt tests use offscreen rendering.
Every report must record application commit, Python/Qt and Hyprland versions,
Wayland session type, GPU/driver class, generic display topology, outcome, and
limitations. Keep serial numbers, home paths, private configs, and raw EDID out
of public reports. Use fabricated fixtures for repeatable automated tests.

## Automated layers

| Layer | Required coverage |
| --- | --- |
| Domain | Mode precision, logical size/rotation, negative positions, invalid scale, mirror cycles, all-disabled rejection |
| Backend | JSON variations/missing fields, inactive outputs, unsupported versions, command escaping, timeouts and response errors |
| Recovery | Partial success, client death, deadline expiry, guard loss, stale journal/session, changed topology, failed persistence/reload |
| Profiles | Duplicate/empty serials, connector changes, missing outputs, schema migration/future versions, import validation |
| Policy | Exact/subset matches, ties, no match, unknown extras, manual pin, cooldown, self-event loops, failure suppression |
| Qt | Selection, dragging and numeric parity, dirty/stale state, keyboard access, error visibility, countdown/confirmation |
| Integration | GUI/CLI/agent contention, no-tray operation, startup/shutdown/reconnect, opt-in autostart lifecycle |

A fake backend must allow injection of failure after each individual mutation.
Headless Qt tests and synthetic fixtures do not certify physical monitor behavior.
CI introduced in phase 1 should run lint, type checking and pytest, with headless
Qt checks when GUI code arrives. Build/package validation is added in phase 7.

## Native acceptance matrix

| Setup/scenario | Required evidence before the relevant feature ships |
| --- | --- |
| One display | Edit/confirm/revert; cannot disable the only usable output |
| Two displays | Drag/numeric layout, refresh/scale, rotation, negative coordinates |
| Mixed DPI/rotation | Correct logical geometry, usable Qt layout and identification |
| Mirror group | Valid target, expected output, recovery on target removal |
| Laptop and dock | Plug/unplug, changed connectors, disabled internal panel recovery |
| Missing/identical displays | Safe mismatch handling and explicit mapping |
| Preview timeout/client crash | Independent guard restores a visible usable layout |
| Failed apply/persistence | Partial-write recovery and file backup restoration |
| Hotplug during preview | Revalidation and safe degraded recovery |
| Session restart/resume | Fresh discovery, no stale-session replay or automation loop |
| External config/reload | Conflicts detected, managed include survives intended reload |
| CLI/tray/manual/auto race | Exactly one pending transaction; manual override respected |
| Advanced VRR/color/HDR | Per-option supported hardware check or documented deferral |
| Clean Arch-based install | Dependencies, Wayland Qt plugin, launch/uninstall and preserved user data |

Perform mutation tests in a recoverable session with a known way back to a TTY
and configuration backup. Run GPU/compositor crash cases only in a controlled
environment; never claim a guard can recover hardware failure. A test record may
be Not run/Unsupported with an explicit release scope reduction. Required basic
layout/recovery cases cannot be replaced by mocked evidence.

## Release checklist

- [ ] All shipped features have task evidence and documented compatibility.
- [ ] Core automated checks pass on the release commit.
- [ ] Native basic layout, persistence and recovery matrix is complete.
- [ ] No unverified advanced option is presented as supported.
- [ ] Profiles survive upgrades; backups and unfinished journals are recoverable.
- [ ] Automation is opt-in, explainable, and can be paused/disabled.
- [ ] Clean package installation and uninstallation work without root runtime.
- [ ] Public examples, reports and screenshots contain no personal identifiers.
- [ ] License notices, help, changelog and known limitations are included.
- [ ] Versioned source/artifacts are verified before release publication.
