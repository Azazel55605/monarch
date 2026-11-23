from pathlib import Path

import pytest

from monarch.backends.hyprland.session import Session, config_location


def metadata(tmp_path, args, env=None):
    session = Session(tmp_path / "runtime", "session")
    session.directory.mkdir(parents=True)
    (session.directory / "hyprland.lock").write_text("1234\nwayland-test\n")
    proc_root = tmp_path / "proc"
    process = proc_root / "1234"
    process.mkdir(parents=True)
    (process / "cmdline").write_bytes("\0".join(["Hyprland", *args, ""]).encode())
    (process / "environ").write_bytes(
        "\0".join(f"{k}={v}" for k, v in (env or {}).items()).encode()
    )
    (process / "cwd").symlink_to(tmp_path, target_is_directory=True)
    return session, proc_root


@pytest.mark.parametrize("flag", ["--config", "-c"])
def test_compositor_custom_config_wins_over_environment(tmp_path, flag):
    session, proc_root = metadata(
        tmp_path, [flag, "/generic/custom.lua"], {"HYPRLAND_CONFIG": "/ignored.lua"}
    )
    location = config_location(session, proc_root=proc_root)
    assert location.path == Path("/generic/custom.lua")
    assert location.source == "compositor command line"
    assert location.verified


def test_relative_compositor_config(tmp_path):
    session, proc_root = metadata(tmp_path, ["--config", "relative.lua"])
    assert config_location(session, proc_root=proc_root).path == tmp_path / "relative.lua"


def test_safe_mode_precedes_explicit_config(tmp_path):
    session, proc_root = metadata(tmp_path, ["--safe-mode", "--config", "/ignored.lua"])
    assert (
        config_location(session, proc_root=proc_root).path == session.directory / "recoverycfg.lua"
    )


def test_compositor_environment_custom_path(tmp_path):
    session, proc_root = metadata(tmp_path, [], {"HYPRLAND_CONFIG": "/generic/from-env.lua"})
    location = config_location(session, proc_root=proc_root)
    assert location.verified
    assert location.path == Path("/generic/from-env.lua")


def test_xdg_is_a_candidate_not_a_verified_path(tmp_path):
    session, proc_root = metadata(
        tmp_path, [], {"XDG_CONFIG_HOME": "/generic/xdg", "HOME": "/ignored"}
    )
    location = config_location(session, proc_root=proc_root)
    assert location.path == Path("/generic/xdg/hypr/hyprland.lua")
    assert not location.verified


def test_inaccessible_process_metadata_stays_unknown(tmp_path):
    session, proc_root = metadata(tmp_path, [])
    (proc_root / "1234" / "cmdline").unlink()
    location = config_location(session, proc_root=proc_root)
    assert location.path is None
    assert not location.verified
