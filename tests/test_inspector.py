import asyncio
import json
from pathlib import Path

import pytest

from monarch.backends.hyprland.inspector import Inspector
from monarch.backends.hyprland.session import Session, config_location
from monarch.cli import main, report
from monarch.errors import MonarchError


class FakeClient:
    def __init__(self, tmp_path, monitors, *, version=None, status=None):
        self.session = Session(tmp_path, "test-session")
        self.data = {
            ("version",): version or {"version": "0.57.2", "tag": "v0.57.2", "dirty": False},
            ("status",): status
            if status is not None
            else {"configProvider": "lua", "backend": "drm"},
            ("monitors", "all"): monitors,
        }
        self.calls = []

    async def read(self, *command):
        self.calls.append(command)
        result = self.data[command]
        if isinstance(result, Exception):
            raise result
        return result


def test_capabilities_are_observed_but_writes_disabled(tmp_path, monitors):
    fake = FakeClient(tmp_path, monitors)
    result = asyncio.run(Inspector(fake).inspect())
    assert result.capabilities.lua_advertised
    assert result.capabilities.stable_baseline
    assert not result.capabilities.mutation_allowed
    assert result.config.path is None
    assert fake.calls == [("version",), ("status",), ("monitors", "all")]


@pytest.mark.parametrize(
    "status", [[], {"configProvider": "future"}, MonarchError("status unavailable")]
)
def test_unknown_provider_does_not_hide_monitors(tmp_path, monitors, status):
    result = asyncio.run(Inspector(FakeClient(tmp_path, monitors, status=status)).inspect())
    assert len(result.monitors) == 2
    assert result.capabilities.provider == "unknown"
    assert not result.capabilities.mutation_allowed


def test_future_version_is_not_supported_by_assumption(tmp_path, monitors):
    result = asyncio.run(
        Inspector(FakeClient(tmp_path, monitors, version={"version": "0.99.0"})).inspect()
    )
    assert not result.capabilities.stable_baseline
    assert result.monitors


def test_redaction_covers_identities_path_and_mirror_targets(tmp_path, monitors):
    monitors[0]["mirrorOf"] = monitors[1]["name"]
    result = asyncio.run(
        Inspector(FakeClient(tmp_path, monitors), Path("/private/config.lua")).inspect()
    )
    public = json.dumps(report(result))
    for private in ["DP-EXAMPLE", "HDMI-EXAMPLE", "DEMO-001", "Example", "/private/config.lua"]:
        assert private not in public
    assert report(result)["monitors"][0]["mirror_of"] == "display-2"
    assert "/private/config.lua" in json.dumps(report(result, identifiers=True))


def test_config_selection_does_not_execute_or_read_lua(tmp_path):
    path = tmp_path / "unknown.lua"
    location = config_location(Session(tmp_path, "session"), path)
    assert location.path == path
    assert not location.verified
    assert not path.exists()


@pytest.mark.parametrize("signature", ["", "../escape", "..", "bad/socket", "bad\0signature"])
def test_invalid_session(signature):
    with pytest.raises(MonarchError):
        Session.from_environment(
            {"HYPRLAND_INSTANCE_SIGNATURE": signature, "XDG_RUNTIME_DIR": "/tmp"}
        )


def test_relative_runtime_rejected():
    with pytest.raises(MonarchError):
        Session.from_environment(
            {"HYPRLAND_INSTANCE_SIGNATURE": "session", "XDG_RUNTIME_DIR": "relative"}
        )


def test_no_session_cli_exits_without_traceback(monkeypatch, capsys):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert main(["inspect"]) == 2
    output = capsys.readouterr()
    assert "running Hyprland session" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "61"])
def test_cli_timeout_validation(timeout):
    with pytest.raises(SystemExit) as error:
        main(["inspect", "--timeout", timeout])
    assert error.value.code == 2
