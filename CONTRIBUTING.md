# Contributing to Monarch

Monarch is in the planning stage. Start with the [implementation plan](docs/implementation-plan.md)
and [progress tracker](docs/progress.md). Keep changes focused on a task ID;
record the evidence required to mark it done. Discuss architectural departures
and new scope before treating them as accepted roadmap changes.

Once source code exists, keep domain logic independent of Qt and compositor I/O.
Use typed models, bounded subprocess calls, explicit configuration ownership, and
the shared apply/recovery coordinator. Do not add an alternate mutation path for
a CLI, tray action, or automation rule.

Add meaningful tests for validation, matching, serialization, state transitions,
and recovery. Report automated, headless Qt, and native Wayland results separately.
Do not mark a hardware feature validated using only a fake backend.

Use synthetic monitor names and identities in fixtures. Before publishing reports,
remove home directories, usernames, serial numbers, EDID, private config contents,
and unrelated process/window information. Bug reports should include software
versions, a generic topology, reproduction steps, expected/observed behavior,
and redacted errors. Never include credentials.

There is no supported developer setup or application command yet. Phase 1 will
add those instructions alongside the package and CI configuration.
