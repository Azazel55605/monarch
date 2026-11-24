import asyncio
import json
from dataclasses import replace

import pytest
from test_guard import guard_setup as guard_setup

from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.domain.profiles import resolve
from monarch.errors import MonarchError
from monarch.services.state import session_token
from monarch.storage.files import digest, write_json
from monarch.storage.profiles import ProfileStore


def enable_hdr_fixture(coordinator, managed, state):
    raw = json.loads(state.read_text())
    raw["monitors"][0]["hardwareDetails"].update(hdr=True, bt2020=True)
    raw["monitors"][1].update(disabled=False, x=2560)
    state.write_text(json.dumps(raw))
    layout = Layout.capture(parse_monitors(raw["monitors"]))
    _, disk = managed.read()
    write_json(
        coordinator.paths.confirmed,
        {
            "root": str(managed.directory),
            "disk_digest": digest(disk),
            "layout": layout.to_dict(),
            "session_token": session_token(coordinator.session),
        },
    )
    return layout, disk


@pytest.mark.parametrize("end", ["revert", "timeout", "disconnect", "keep"])
def test_hdr_guard_returns_to_sdr_without_saving(guard_setup, end):
    coordinator, managed, _, _, state = guard_setup
    layout, disk = enable_hdr_fixture(coordinator, managed, state)
    output = layout.outputs[0]

    async def run():
        handle = await coordinator.preview(managed, layout, seconds=4, hdr_target=output.name)
        live = parse_monitors(json.loads(state.read_text())["monitors"])
        assert live[0].advanced.color_preset == "hdr"
        assert live[0].advanced.bit_depth == 10
        assert live[1].advanced.color_preset == "srgb"
        assert layout.matches(live, check_color=False)
        if end == "disconnect":
            result = await handle.disconnect()
        elif end == "timeout":
            result = await handle.wait()
        else:
            result = await handle.decide(keep=end == "keep", persist=end == "keep")
        assert result["state"] == "reverted"
        if end == "timeout":
            assert result["reason"] == "deadline_elapsed"
        if end == "keep":
            assert "must return to SDR" in result["detail"]
        live = parse_monitors(json.loads(state.read_text())["monitors"])
        assert layout.matches(live)
        assert live[0].advanced.color_preset == "srgb" and live[0].advanced.bit_depth == 8
        assert managed.read()[1] == disk

    asyncio.run(run())


def test_hdr_guard_rejects_unverified_sink_and_recovers_after_failed_apply(guard_setup):
    coordinator, managed, _, _, state = guard_setup
    layout, disk = enable_hdr_fixture(coordinator, managed, state)
    raw = json.loads(state.read_text())
    raw["ignore_hdr"] = True
    state.write_text(json.dumps(raw))

    async def run():
        with pytest.raises(MonarchError, match="advertising HDR"):
            await coordinator.preview(managed, layout, hdr_target=layout.outputs[1].name)
        assert "mutations" not in json.loads(state.read_text())
        with pytest.raises(MonarchError, match="verify 10-bit HDR"):
            await coordinator.preview(managed, layout, hdr_target=layout.outputs[0].name)
        assert coordinator.paths.status()["status"] == "reverted"
        assert managed.read()[1] == disk

    asyncio.run(run())


def test_hdr_guard_never_replays_the_old_layout_on_a_replacement_display(guard_setup):
    coordinator, managed, _, _, state = guard_setup
    layout, disk = enable_hdr_fixture(coordinator, managed, state)

    async def run():
        handle = await coordinator.preview(managed, layout, hdr_target=layout.outputs[0].name)
        raw = json.loads(state.read_text())
        mutations = raw["mutations"]
        raw["monitors"][0].update(
            serial="replacement", colorManagementPreset="srgb", currentFormat="XRGB8888"
        )
        state.write_text(json.dumps(raw))
        assert (await handle.decide(keep=False))["state"] == "degraded"
        assert json.loads(state.read_text())["mutations"] == mutations
        assert managed.read()[1] == disk

    asyncio.run(run())


def test_hdr_policy_keeps_persists_round_trips_profiles_and_reverts_to_hdr(guard_setup, tmp_path):
    coordinator, managed, _, _, state = guard_setup
    sdr, disk = enable_hdr_fixture(coordinator, managed, state)
    hdr = Layout((replace(sdr.outputs[0], hdr=True), sdr.outputs[1]))
    profiles = ProfileStore(tmp_path / "profiles")
    profiles.save("HDR desk", hdr)
    profiles.save("SDR desk", sdr)

    def live():
        return parse_monitors(json.loads(state.read_text())["monitors"])

    async def run():
        loaded = resolve(profiles.get("HDR desk"), live())
        preview = await coordinator.preview(managed, loaded)
        assert (await preview.decide(keep=True))["reason"] == "runtime_only"
        assert hdr.matches(live())
        assert managed.read()[1] == disk

        preview = await coordinator.preview(managed, hdr)
        assert (await preview.decide(keep=True, persist=True))["reason"] == "persisted"
        saved, content = managed.read()
        assert saved == hdr and saved.to_dict()["schema_version"] == 3
        assert (
            b'output="desc:Example Panel DEMO-001"' in content
            and b'cm="hdr",bitdepth=10' in content
        )

        preview = await coordinator.preview(managed, resolve(profiles.get("SDR desk"), live()))
        assert sdr.matches(live())
        assert (await preview.decide(keep=False))["state"] == "reverted"
        assert hdr.matches(live())
        assert managed.read()[1] == content

        preview = await coordinator.preview(managed, sdr)
        assert (await preview.decide(keep=True, persist=True))["reason"] == "persisted"
        assert sdr.matches(live())
        assert managed.read()[0] == sdr
        assert b'cm="hdr"' not in managed.read()[1]

    asyncio.run(run())


def test_failed_hdr_depth_change_still_recovers_sdr(guard_setup):
    coordinator, managed, _, _, state = guard_setup
    sdr, disk = enable_hdr_fixture(coordinator, managed, state)
    raw = json.loads(state.read_text())
    raw["hdr_at_8bit"] = True
    state.write_text(json.dumps(raw))
    hdr = Layout((replace(sdr.outputs[0], hdr=True), sdr.outputs[1]))

    async def run():
        with pytest.raises(MonarchError, match="HDR/SDR preset or bit depth"):
            await coordinator.preview(managed, hdr)
        assert coordinator.paths.status()["status"] == "reverted"
        assert sdr.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        assert managed.read()[1] == disk

    asyncio.run(run())
