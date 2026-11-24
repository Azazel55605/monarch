import asyncio
import json

import pytest
from test_guard import guard_setup as guard_setup

from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.errors import MonarchError
from monarch.services.state import session_token
from monarch.storage.files import digest, write_json


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
        assert layout.matches(live)
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
