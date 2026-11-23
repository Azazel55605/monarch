# Candidate and release checklist

Version: `0.1.0rc9`. This is the testing handoff; **v0.1.0 is not tagged or published**.
The implementation plan reserves release tagging/publication for a later explicit
instruction. AUR and PyPI publication are separate, unperformed actions.

## Candidate preparation

- [x] Source/wheel metadata and original icon/desktop assets included.
- [x] Native dependency recipe, source checksums and build helper reviewed.
- [x] Offline help, notices, changelog, testing and removal/recovery guides supplied.
- [x] CI builds Python artifacts and a native Arch package with install/remove checks.
- [x] Existing hardware limitations and advanced-write deferrals documented.
- [x] Final local/hosted evidence recorded in the [Phase 7 report](phase-7-report.md).

## Stable release gates

- [ ] User feedback from this testing candidate reviewed and blocking defects resolved.
- [ ] Physical basic-setting Keep/Revert/persistence and client-loss acceptance recorded.
- [ ] Physical dock/undock, repeated events and suspend/resume accepted (Phase 5 gate).
- [ ] Fresh login/startup enable-disable accepted on the target session host.
- [ ] Current virtual disable/re-enable and candidate mirror/output-creation timeouts resolved or explicitly scoped for release.
- [ ] Package accepted on the target installed Arch/Garuda session; desktop/tray behavior checked.
- [ ] Final license/dependency notices and the exact artifacts selected for publication reviewed.
- [ ] Explicit authorization to promote/tag/publish a stable release received.

VRR Off/On is implemented in the rc3 testing candidate with explicit policies,
observed-state checks and software recovery coverage. Physical target-display
Keep/Revert, persistence and recovery acceptance remains a release gate. Conditional
VRR, depth, color/HDR and ICC writes remain deferred pending their own design and
hardware evidence. Legacy writing and custom-modeline editing remain deferred.
