import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from monarch.backends.hyprland.session import Session
from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.services.coordinator import Coordinator
from monarch.storage.managed import Managed


@pytest.fixture
def guard_setup(tmp_path, monitors):
    monitors[0]["scale"] = 1
    layout = Layout.capture(parse_monitors(monitors))
    store = Managed(tmp_path / "owned")
    store.create(layout)
    runtime = tmp_path / "r"
    runtime.mkdir(mode=0o700)
    session = Session(runtime, "test-session")
    session.directory.mkdir(parents=True)
    (session.directory / ".socket.sock").touch()
    # A real same-user process with Hyprland-shaped argv exercises /proc metadata
    # detection without bypassing any production guard verification.
    sleeper = tmp_path / "sleep.py"
    sleeper.write_text("import time\ntime.sleep(300)\n")
    process = subprocess.Popen(
        ["Hyprland", str(sleeper), "--config", str(store.root)],
        executable=str(Path(sys.executable).resolve()),
    )
    (session.directory / "hyprland.lock").write_text(f"{process.pid}\nwayland-test\n")
    state = tmp_path / "fake.json"
    state.write_text(json.dumps({"monitors": monitors, "root": str(store.directory)}))
    fake = tmp_path / "hyprctl"
    source = Path(__file__).with_name("fake_hyprctl.py").read_text()
    fake.write_text("#!/usr/bin/env python\n" + source)
    fake.chmod(0o700)
    env = dict(
        os.environ,
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        MONARCH_FAKE_STATE=str(state),
        PYTHONPATH=str(Path(__file__).parents[1] / "src"),
    )
    coordinator = Coordinator(session, state_home=tmp_path / "state", executable=str(fake), env=env)
    desired = Layout((replace(layout.outputs[0], scale=2, x=-1280), layout.outputs[1]))
    try:
        yield coordinator, store, layout, desired, state
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_guard_reverts_on_client_pipe_loss(guard_setup):
    coordinator, store, baseline, desired, state = guard_setup

    async def run():
        preview = await coordinator.preview(store, desired, seconds=5)
        assert desired.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        result = await preview.disconnect()
        assert result["state"] == "reverted"
        assert result["reason"] == "client_disconnected"
        assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))

    asyncio.run(run())


def test_guard_deadline_cannot_be_bypassed_by_open_client(guard_setup):
    coordinator, store, baseline, desired, state = guard_setup

    async def run():
        preview = await coordinator.preview(store, desired, seconds=4)
        result = await preview.wait()
        assert result["state"] == "reverted"
        assert result["reason"] == "deadline_elapsed"
        assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))

    asyncio.run(run())


def test_explicit_confirmation_persists_and_second_client_serialized(guard_setup):
    coordinator, store, baseline, desired, state = guard_setup

    async def run():
        preview = await coordinator.preview(store, desired, seconds=8)
        from monarch.errors import MonarchError

        with pytest.raises(MonarchError, match="did not start"):
            await coordinator.preview(store, desired, seconds=8)
        result = await preview.decide(keep=True, persist=True)
        assert result["state"] == "kept"
        assert store.read()[0] == desired
        assert coordinator.paths.status()["status"] == "kept"

    asyncio.run(run())


def test_guard_survives_parent_sigkill(guard_setup, tmp_path):
    coordinator, store, baseline, desired, state = guard_setup
    request = tmp_path / "desired.json"
    request.write_text(json.dumps(desired.to_dict()))
    script = tmp_path / "client.py"
    script.write_text("""import asyncio,json,os,time
from pathlib import Path
from monarch.backends.hyprland.session import Session
from monarch.services.coordinator import Coordinator
from monarch.domain.layout import Layout
from monarch.storage.managed import Managed
async def run():
 c=Coordinator(Session.from_environment(),state_home=Path(os.environ['TEST_STATE']),executable=os.environ['TEST_HYPRCTL'])
 layout=Layout.parse(json.loads(Path(os.environ['TEST_LAYOUT']).read_text()))
 h=await c.preview(Managed(Path(os.environ['TEST_ROOT'])),layout,seconds=8)
 print('PENDING',flush=True)
 await h.wait()
asyncio.run(run())
""")
    env = dict(
        coordinator.env,
        TEST_STATE=str(coordinator.state_home),
        TEST_HYPRCTL=coordinator.executable,
        TEST_ROOT=str(store.directory),
        TEST_LAYOUT=str(request),
    )
    process = subprocess.Popen(
        [sys.executable, str(script)], env=env, stdout=subprocess.PIPE, text=True
    )
    try:
        assert process.stdout.readline().strip() == "PENDING"
        process.kill()
        process.wait(timeout=3)
        import time

        for _ in range(80):
            status = coordinator.paths.status()
            if status and status["status"] == "reverted":
                break
            time.sleep(0.1)
        assert coordinator.paths.status()["status"] == "reverted"
        assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def cli_environment(coordinator, store):
    env = dict(coordinator.env)
    env["XDG_STATE_HOME"] = str(coordinator.state_home)
    env["PATH"] = str(Path(coordinator.executable).parent) + os.pathsep + env["PATH"]
    return env


def test_cli_without_terminal_cannot_confirm_keep(guard_setup, tmp_path):
    coordinator, store, baseline, desired, state = guard_setup
    from monarch.storage.files import write_json

    layout_file = tmp_path / "preview.json"
    write_json(layout_file, desired.to_dict())
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "monarch",
            "preview",
            str(layout_file),
            "--directory",
            str(store.directory),
            "--seconds",
            "4",
        ],
        env=cli_environment(coordinator, store),
        input="keep\n",
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 0, process.stderr
    assert "No interactive terminal" in process.stdout
    assert json.loads(process.stdout.splitlines()[-1])["state"] == "reverted"
    assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))


def test_cli_terminal_keep_persists_explicitly(guard_setup, tmp_path):
    import pty

    coordinator, store, baseline, desired, state = guard_setup
    from monarch.storage.files import write_json

    layout_file = tmp_path / "preview.json"
    write_json(layout_file, desired.to_dict())
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "monarch",
            "preview",
            str(layout_file),
            "--directory",
            str(store.directory),
            "--seconds",
            "10",
            "--persist",
        ],
        env=cli_environment(coordinator, store),
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    os.close(slave)
    try:
        assert "Preview active" in process.stdout.readline()
        os.write(master, b"keep\n")
        output, error = process.communicate(timeout=15)
        assert process.returncode == 0, error
        assert json.loads(output.splitlines()[-1])["state"] == "kept"
        assert store.read()[0] == desired
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
            process.wait()


def test_profile_terminal_switch_keep_and_noninteractive_refusal(guard_setup, tmp_path):
    import pty

    from monarch.storage.profiles import ProfileStore

    coordinator, store, baseline, desired, state = guard_setup
    profiles = ProfileStore(tmp_path / "profiles")
    profiles.save("Presentation", desired)
    command = [
        sys.executable,
        "-m",
        "monarch",
        "profile",
        "--store",
        str(profiles.directory),
        "switch",
        "Presentation",
        "--terminal",
        "--persist",
        "--directory",
        str(store.directory),
    ]
    env = cli_environment(coordinator, store)
    result = subprocess.run(
        command, env=env, input="keep\n", capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 2
    assert "interactive terminal" in result.stderr
    assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
    master, slave = pty.openpty()
    process = subprocess.Popen(
        command, env=env, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    os.close(slave)
    try:
        assert "Preview active" in process.stdout.readline()
        os.write(master, b"keep\n")
        output, error = process.communicate(timeout=15)
        assert process.returncode == 0, error
        assert json.loads(output.splitlines()[-1])["state"] == "kept"
        assert store.read()[0] == desired
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
            process.wait()
