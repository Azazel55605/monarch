import asyncio
import sys
from pathlib import Path

import pytest

from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.session import Session
from monarch.errors import MonarchError


def executable(tmp_path: Path, body: str) -> str:
    path = tmp_path / "fake-hyprctl"
    path.write_text(f"#!{Path(sys.executable).resolve()}\n" + body)
    path.chmod(0o700)
    return str(path)


def client(tmp_path, body, **kwargs):
    return Hyprctl(
        Session(tmp_path, "test-session"), executable=executable(tmp_path, body), **kwargs
    )


def test_argv_and_bound_session(tmp_path):
    transport = client(
        tmp_path,
        "import json,sys,os\n"
        "print(json.dumps([sys.argv[1:],os.environ['HYPRLAND_INSTANCE_SIGNATURE']]))",
    )
    result = asyncio.run(transport.read("monitors", "all"))
    assert result == [["-i", "test-session", "-j", "monitors", "all"], "test-session"]


@pytest.mark.parametrize(
    "command", [("eval", "malicious"), ("reload",), ("keyword", "monitor"), ("monitors;kill",)]
)
def test_mutation_and_shell_commands_rejected_before_spawn(tmp_path, command):
    transport = Hyprctl(Session(tmp_path, "session"), executable="/nonexistent")
    with pytest.raises(MonarchError, match="read-only"):
        asyncio.run(transport.read(*command))


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ('print("not JSON")', "invalid JSON"),
        ('import sys\nprint("private serial",file=sys.stderr)\nsys.exit(1)', "request failed"),
        ("import time\ntime.sleep(5)", "timed out"),
        ('print("x"*10000)', "size limit"),
        ('import sys\nprint("x"*10000,file=sys.stderr)', "size limit"),
    ],
)
def test_bad_commands_are_bounded_and_redacted(tmp_path, body, match):
    transport = client(tmp_path, body, timeout=0.15, max_output=1024)
    with pytest.raises(MonarchError, match=match) as error:
        asyncio.run(transport.read("version"))
    assert "private serial" not in str(error.value)


def test_missing_executable(tmp_path):
    with pytest.raises(MonarchError, match="not found"):
        asyncio.run(
            Hyprctl(Session(tmp_path, "session"), executable="/nonexistent").read("version")
        )


def test_cancelled_command_is_reaped(tmp_path):
    pid_file = tmp_path / "child.pid"
    transport = client(
        tmp_path,
        f'import os,time\nopen({str(pid_file)!r},"w").write(str(os.getpid()))\ntime.sleep(20)',
    )

    async def run():
        task = asyncio.create_task(transport.read("version"))
        for _ in range(100):
            if pid_file.exists():
                break
            await asyncio.sleep(0.01)
        assert pid_file.exists()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    import os

    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
