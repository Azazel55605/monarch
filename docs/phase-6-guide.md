# Advanced observations, compatibility and diagnostics

Phase 6 adds an **Advanced settings…** observation panel, stricter recovery gates,
redacted diagnostics and compatibility decisions. **No advanced write control is
enabled in this build.** The plan explicitly defers settings without adequate
hardware write/rollback evidence; it does not make an unverified toggle available.

## Advanced settings panel

Select a connected display and open **Advanced settings…**. The snapshot shows:

| Setting | Observed evidence | Write/recovery status |
| --- | --- | --- |
| VRR | Current adaptive-sync state and the driver capability flag | Deferred: active state does not reveal the prior policy |
| Bit depth | Recognized current DRM format and its channel precision | Deferred: current format is not a supported-depth list or saved rule |
| Color preset | Recognized reported preset | Deferred: complete color/EOTF/rule restoration lacks hardware acceptance |
| HDR | Presence of reported EDID HDR metadata | Deferred: metadata alone does not prove working HDR output/recovery |
| ICC | Not reported by this monitor IPC snapshot | Deferred: active file identity/contents and restore behavior are unavailable |

Missing, malformed or future values remain unknown. Hardware flags never enable
controls on their own. The panel is read-only, with a reason for each unavailable
control. Reopen it for a new snapshot. No ICC files or raw EDID are read to populate it.

## Basic-state safety gate

The existing writer only manages basic monitor settings. It now requires known
inactive VRR, a recognized 8-bit format, sRGB, and default observed SDR parameters
on active outputs. Disabled outputs may carry stale/unknown observations; an output
that becomes enabled must pass the checks before further application proceeds.
Hardware VRR/HDR capability flags alone do not block basic editing.

Known active advanced settings or missing required state block guarded application,
automatic proposals and integration setup. Inspection, drafting, profile management
and diagnostics remain available. Opening Monarch never turns advanced settings off.
An existing VRR/10-bit/HDR setup can therefore become inspection-only under this
stricter boundary. The UI explains the observed blocker instead of claiming it can
restore that state. The stored profile/layout schemas remain unchanged. Profiles capture basic fields;
advanced observations are not saved as restorable profile settings.

The guard rechecks during application and confirmation. If external advanced state
appears mid-preview, recovery avoids further compositor reload/eval and retains a
`recovery_required` journal. Review the external state first; once the known basic
state is restored, `monarch recover` can retry using the original protections.
The guard may restore its own candidate monitor file from its backup, but never
replaces externally changed files. Do not delete the journal to bypass review.

This is a known-hazard filter, **not** proof that no hidden advanced rules exist.
IPC does not reveal ICC files or every global/dynamic color setting. The reviewed
exclusive basic-monitor configuration contract still applies; competing controllers,
ICC/advanced rules and dynamic HDR behavior remain outside it. No automatic
migration or reset of third-party advanced configuration is performed.

## Supported configuration and schema scope

- Writes retain the clean Hyprland 0.57.2 Lua baseline and verified active root.
  Unknown releases, dirty/custom builds and unverified roots remain inspectable.
- Legacy hyprlang is inspection-only. Monarch will not write or automatically
  convert legacy configurations in this product version.
- Custom modeline editing is deferred. Enabled outputs use advertised numeric
  resolution/refresh choices; raw modelines or Lua are not imported as settings.
- Layout schema 1, profile catalog schema 2 (schema-1 migration), and policy schema 1
  remain supported. Advanced layout fields and future schema versions are rejected,
  rather than ignored or rewritten. A later advanced writer needs an explicit schema
  and backup/migration design along with per-option hardware evidence.
- Tagged monitor IPC returns mirror references as IDs. Monarch resolves those IDs
  against the full observation before matching names. Unresolved/ambiguous references
  remain unknown and cannot be captured or applied as independent displays.

## Redacted support reports

From **Help → Redacted diagnostics…**, review the JSON snapshot and use Copy or Save.
Collection runs in the worker. Saving is explicit, creates a new mode-0600 file,
and refuses existing targets. Nothing is automatically uploaded or sent anywhere.

The Qt-free CLI also works outside a compositor session:

```sh
uv run monarch diagnose
uv run monarch diagnose --output /path/to/new-report.json
uv run monarch diagnose --directory /path/to/existing/managed-storage
```

Collection is read-only: it does not create missing config/state directories, apply
monitor settings, execute Lua, install integration or autostart, or replay recovery.
Existing owned sources may be read to verify their hashes. A report includes runtime
versions, anonymous display labels, geometry/modes, whitelisted advanced observations,
compatibility blockers, integration status/actions, profile/rule counts, session pin
and transaction-state categories. A missing session or invalid storage produces an
actionable diagnostic code rather than a raw exception or partial setup operation.

Reports omit connector names, descriptions, make/model/serial, profile names/IDs,
config and ICC paths/content, session/boot identifiers, raw logs, journal details,
and arbitrary compositor strings. Unknown free-form diagnostics are omitted;
version build suffixes are excluded. Geometry, modes and capability flags remain
for debugging, so review the report before sharing it. `inspect --show-identifiers`
remains a separate explicit local inspection option; support reports are always redacted.

Integration conflicts are classified as a changed root/dependency, target mismatch,
unsafe storage, unavailable storage, or invalid managed data. Review the existing
files/backups through setup instead of overwriting conflicts or deleting journals.
Unsupported-version/provider explanations retain read-only inspection and draft access.

## Remaining acceptance

The [Phase 6 report](phase-6-report.md) records automated privacy/gate tests and
native basic recovery, virtual hotplug, mirroring and Qt observations. A read-only
physical check verifies report behavior and unchanged settings; it is not advanced
modesetting evidence. Advanced writes are explicitly deferred. The Phase 5 physical
dock/resume/fresh-login gate and broader release matrix remain open.
