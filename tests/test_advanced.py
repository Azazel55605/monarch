import asyncio
import json
from dataclasses import replace

import pytest
from test_guard import guard_setup as guard_setup

from monarch.domain.advanced import basic_issues, features, require_basic
from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.domain.policy import Policy, Rule, choose
from monarch.domain.profiles import Profile
from monarch.errors import MonarchError
from monarch.storage.files import read_private


def test_observation_is_distinct_from_supported_writes(monitors):
    monitors[0].update(
        vrr=True,
        currentFormat="XRGB2101010",
        colorManagementPreset="hdr",
        hardwareDetails={"vrrCapable": True, "hdr": True, "bt2020": True},
    )
    state = parse_monitors(monitors)[0].advanced
    assert state.vrr_active and state.vrr_capable and state.hdr_metadata
    assert state.bit_depth == 10 and state.color_preset == "hdr"
    assert all(not feature.writable and feature.reason for feature in features(state)[1:])
    assert state.to_dict()["icc_state"] == "not_reported"
    with pytest.raises(MonarchError, match="cannot be restored"):
        require_basic(parse_monitors(monitors))


@pytest.mark.parametrize(
    "field,value",
    [
        ("vrr", None),
        ("vrr", 0),
        ("vrr", "false"),
        ("currentFormat", "future-private-format"),
        ("colorManagementPreset", "/private/icc.icm"),
        ("sdrBrightness", float("nan")),
        ("sdrSaturation", float("inf")),
        ("sdrMinLuminance", True),
        ("sdrMaxLuminance", 10**400),
    ],
)
def test_missing_invalid_and_future_state_never_fabricates_basic_support(monitors, field, value):
    monitors[0][field] = value
    parsed = parse_monitors(monitors)
    assert basic_issues(parsed)
    public = json.dumps(parsed[0].advanced.to_dict(), allow_nan=False)
    assert "private" not in public
    assert "future-private-format" not in public


def test_hardware_support_flag_does_not_block_basic_or_enable_control(monitors):
    monitors[0]["hardwareDetails"] = {"hdr": True, "vrrCapable": True}
    parsed = parse_monitors(monitors)
    require_basic(parsed)
    assert parsed[0].advanced.hdr_metadata
    assert features(parsed[0].advanced)[0].writable
    # Disabled outputs may carry stale/absent advanced observations.
    monitors[1].update(vrr=True, currentFormat="unknown", colorManagementPreset="wide")
    require_basic(parse_monitors(monitors))


def test_existing_schema_remains_strict_against_unsupported_advanced_imports(monitors):
    monitors[0]["scale"] = 1
    layout = Layout.capture(parse_monitors(monitors)).to_dict()
    for field in ("bitdepth", "icc", "cm"):
        candidate = json.loads(json.dumps(layout))
        candidate["outputs"][0][field] = "unverified"
        with pytest.raises(MonarchError, match="documented layout fields"):
            Layout.parse(candidate)
    layout["outputs"][0]["hdr"] = True
    with pytest.raises(MonarchError, match="Older layouts cannot contain HDR"):
        Layout.parse(layout)
    layout["schema_version"] = 4
    with pytest.raises(MonarchError, match="schema version"):
        Layout.parse(layout)


def test_advanced_state_prevents_automatic_offers(monitors):
    monitors[0]["scale"] = 1
    live = parse_monitors(monitors)
    profile = Profile("a" * 32, "Desk", Layout.capture(live))
    advanced = (replace(live[0], advanced=replace(live[0].advanced, color_preset="hdr")), live[1])
    result = choose(Policy(True, (Rule(profile.id),)), (profile,), advanced)
    assert result.layout is None and "Advanced state" in result.reason


@pytest.mark.parametrize(
    "field,value",
    [
        ("vrr", True),
        ("currentFormat", "XRGB2101010"),
        ("colorManagementPreset", "hdr"),
        ("sdrBrightness", 1.2),
    ],
)
def test_guard_refuses_before_mutation_and_preserves_files(guard_setup, field, value):
    coordinator, store, baseline, desired, state_path = guard_setup
    raw = json.loads(state_path.read_text())
    raw["monitors"][0][field] = value
    state_path.write_text(json.dumps(raw))
    original = read_private(store.monitors)

    async def run():
        with pytest.raises(MonarchError, match="did not start"):
            await coordinator.preview(store, desired, seconds=5)

    asyncio.run(run())
    assert json.loads(state_path.read_text()).get("mutations", 0) == 0
    assert read_private(store.monitors) == original
    assert coordinator.paths.status() is None


def test_external_advanced_change_blocks_reload_during_recovery_until_review(guard_setup):
    coordinator, store, baseline, desired, state_path = guard_setup

    async def run():
        preview = await coordinator.preview(store, desired, seconds=10)
        raw = json.loads(await asyncio.to_thread(state_path.read_text))
        raw["monitors"][0]["currentFormat"] = "XRGB2101010"
        count = raw["mutations"]
        await asyncio.to_thread(state_path.write_text, json.dumps(raw))
        result = await preview.wait()
        assert result["state"] == "recovery_required"
        current = json.loads(await asyncio.to_thread(state_path.read_text))
        assert current["mutations"] == count
        current["monitors"][0]["currentFormat"] = "XRGB8888"
        await asyncio.to_thread(state_path.write_text, json.dumps(current))
        assert (await coordinator.recover())["state"] == "reverted"

    asyncio.run(run())


def test_tagged_numeric_mirror_ids_resolve_and_unresolved_targets_are_never_captured(monitors):
    monitors[0].update(id=7, scale=1)
    monitors[1].update(id=9, disabled=False, mirrorOf="7")
    live = parse_monitors(monitors)
    assert live[1].mirror_of == monitors[0]["name"] and live[1].mirror_known
    layout = Layout.capture(live)
    assert layout.outputs[1].mirror == monitors[0]["name"]
    assert layout.matches(live)
    for unknown in ("404", {}, True):
        monitors[1]["mirrorOf"] = unknown
        unresolved = parse_monitors(monitors)
        assert not unresolved[1].mirror_known
        assert not layout.matches(unresolved)
        with pytest.raises(MonarchError, match="unresolved"):
            Layout.capture(unresolved)
        with pytest.raises(MonarchError, match="unresolved"):
            layout.validate(unresolved)
