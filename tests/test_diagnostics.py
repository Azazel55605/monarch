import asyncio
import json
from dataclasses import replace

import pytest
from test_guard import guard_setup as guard_setup
from test_inspector import FakeClient

from monarch.backends.hyprland.inspector import Inspector
from monarch.backends.hyprland.session import ConfigLocation
from monarch.backends.hyprland.support import blockers
from monarch.cli import main, report
from monarch.errors import MonarchError
from monarch.services.diagnostics import collect, integration, save
from monarch.services.state import Paths
from monarch.storage.files import write_json
from monarch.storage.profiles import ProfileStore


def test_report_drops_freeform_secrets_and_unknown_advanced_strings(tmp_path, monitors):
    secret = "PRIVATE_PERSONAL_TOKEN"
    monitors[0].update(
        name=secret,
        description=secret,
        make=secret,
        serial=secret,
        currentFormat=secret,
        colorManagementPreset=secret,
        icc="/home/private/profile.icc",
    )
    fake = FakeClient(tmp_path, monitors)
    result = asyncio.run(Inspector(fake).inspect())
    result = replace(
        result,
        diagnostics=(secret,),
        monitors=(replace(result.monitors[0], warnings=(secret,)), result.monitors[1]),
        config=ConfigLocation(tmp_path / secret, secret, True),
        capabilities=replace(
            result.capabilities, mutation_reason=secret, version="0.57.2+" + secret
        ),
    )
    public = json.dumps(report(result))
    assert secret not in public and "/home/private" not in public
    assert "omitted" in public
    assert secret in json.dumps(report(result, identifiers=True))


def test_offline_collect_and_export_are_private_and_non_clobbering(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "missing-config"))
    original = set(tmp_path.rglob("*"))
    assert main(["diagnose"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["session"] == "unavailable" and data["redacted"]
    assert data["checks"][0]["code"] == "no_session"
    assert set(tmp_path.rglob("*")) == original
    path = tmp_path / "report.json"
    save(path, data)
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(MonarchError, match="exists"):
        save(path, {"overwritten": True})
    assert json.loads(path.read_text()) == data


def test_collection_omits_profile_names_policy_ids_journal_details_and_never_creates_paths(
    guard_setup, tmp_path
):
    coordinator, store, baseline, desired, state = guard_setup
    config = tmp_path / "config" / "monarch"
    profile = ProfileStore(config).save("SECRET_PROFILE_NAME", baseline)
    fake = FakeClient(tmp_path, json.loads(state.read_text())["monitors"])
    inspection = asyncio.run(Inspector(fake).inspect())
    inspection = replace(
        inspection, config=ConfigLocation(store.root, "compositor command line", True)
    )
    write_json(
        coordinator.paths.journal,
        {"schema_version": 1, "status": "kept", "reason": "SECRET_REASON", "root": "SECRET_ROOT"},
    )
    env = dict(coordinator.env, XDG_STATE_HOME=str(coordinator.state_home))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    data = asyncio.run(
        collect(
            session=coordinator.session, env=env, directory=store.directory, inspection=inspection
        )
    )
    rendered = json.dumps(data)
    for secret in [
        profile.id,
        "SECRET_PROFILE_NAME",
        "SECRET_REASON",
        "SECRET_ROOT",
        str(tmp_path),
        "DEMO-001",
        "DP-EXAMPLE",
    ]:
        assert secret not in rendered
    assert data["profiles"]["count"] == 1
    assert data["integration"]["code"] == "verified"
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    paths = Paths.for_session(coordinator.session, tmp_path / "never-create", create=False)
    assert not paths.state.exists()


def test_conflict_is_explained_without_exposing_changed_root(guard_setup, tmp_path):
    coordinator, store, baseline, desired, state = guard_setup
    fake = FakeClient(tmp_path, json.loads(state.read_text())["monitors"])
    inspection = asyncio.run(Inspector(fake).inspect())
    store.root.write_bytes(b"-- PRIVATE_UNTRUSTED_ROOT\n")
    diagnostic = integration(inspection, store.directory)
    assert diagnostic["code"] == "invalid_managed_data"
    assert "PRIVATE_UNTRUSTED_ROOT" not in json.dumps(diagnostic)
    result = integration(inspection, tmp_path / "does-not-exist")
    assert result["code"] == "not_registered"
    assert not (tmp_path / "does-not-exist").exists()


@pytest.mark.parametrize(
    "provider,stable,expected",
    [
        ("hyprlang", True, "legacy_provider"),
        ("unknown", True, "unknown_provider"),
        ("lua", False, "unsupported_build"),
    ],
)
def test_unsupported_provider_build_remains_inspectable(
    tmp_path, monitors, provider, stable, expected
):
    inspection = asyncio.run(Inspector(FakeClient(tmp_path, monitors)).inspect())
    inspection = replace(
        inspection,
        capabilities=replace(inspection.capabilities, provider=provider, stable_baseline=stable),
    )
    assert expected in [code for code, reason in blockers(inspection)]
    assert len(report(inspection)["monitors"]) == 2


def test_identifier_opt_in_still_escapes_terminal_control_text(tmp_path, monitors, capsys):
    from monarch.cli import render

    inspection = asyncio.run(Inspector(FakeClient(tmp_path, monitors)).inspect())
    inspection = replace(
        inspection, capabilities=replace(inspection.capabilities, version="0.57.2\x1b[31m")
    )
    render(inspection, json_output=False, identifiers=True)
    output = capsys.readouterr().out
    assert "\x1b" not in output and "\\u001b" in output
