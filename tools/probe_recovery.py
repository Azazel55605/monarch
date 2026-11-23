#!/usr/bin/env python3
"""Opt-in Phase 2 recovery acceptance in an isolated native nested compositor."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from monarch.backends.hyprland.session import Session
from monarch.backends.hyprland.writer import Writer
from monarch.domain.layout import Layout, Output
from monarch.errors import MonarchError
from monarch.services.coordinator import Coordinator
from monarch.storage.files import atomic_write, digest, read_private, write_json
from monarch.storage.managed import Managed, render


async def exercise(session: Session, env: dict[str, str], store: Managed, root: Path):
    writer = Writer(session, env=env, timeout=5)
    await writer.read("version")
    await writer.observe()
    await asyncio.sleep(0.5)
    for name in ("MONARCH-A", "MONARCH-B"):
        result = await asyncio.to_thread(
            subprocess.run,
            ["hyprctl", "-i", session.signature, "output", "create", "headless", name],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode:
            raise MonarchError("Could not create isolated virtual outputs.")
    await asyncio.sleep(0.3)
    live = await writer.observe()
    outputs = []
    for monitor in live:
        enabled = monitor.name.startswith("MONARCH-")
        if enabled and not monitor.modes:
            raise MonarchError(
                "Virtual backend did not advertise modes; cannot certify write validation."
            )
        mode = monitor.modes[0] if enabled else None
        outputs.append(
            Output(
                monitor.name,
                monitor.make,
                monitor.model,
                monitor.serial,
                f"{mode.width}x{mode.height}@{mode.refresh_hz}" if mode else "preferred",
                1,
                0,
                1920 if monitor.name == "MONARCH-B" else 0,
                0,
                enabled,
            )
        )
    baseline = Layout.parse(Layout(tuple(outputs)).to_dict())
    old = read_private(store.monitors)
    atomic_write(store.monitors, render(baseline), expected=digest(old))
    await asyncio.sleep(0.5)
    await writer.reload()
    print("native: prepared owned virtual baseline", file=sys.stderr, flush=True)
    for _ in range(30):
        if baseline.matches(await writer.observe()):
            break
        await asyncio.sleep(0.1)
    else:
        raise MonarchError("Owned virtual baseline did not settle.")
    baseline.validate(await writer.observe())
    desired = Layout(
        tuple(replace(o, scale=1.25) if o.name == "MONARCH-A" else o for o in baseline.outputs)
    )
    desired.validate(await writer.observe())
    coordinator = Coordinator(session, state_home=root / "state", env=env)

    async def restored():
        if not baseline.matches(await writer.observe()):
            raise MonarchError("Native recovery did not restore the baseline.")
        if store.read()[0] != baseline:
            raise MonarchError("Managed baseline file was not restored.")

    preview = await coordinator.preview(store, desired, seconds=10)
    assert desired.matches(await writer.observe())
    assert (await preview.decide(keep=False))["state"] == "reverted"
    await restored()
    print("native: recovery case passed", file=sys.stderr, flush=True)
    preview = await coordinator.preview(store, desired, seconds=5)
    assert (await preview.wait())["state"] == "reverted"
    await restored()
    print("native: recovery case passed", file=sys.stderr, flush=True)
    preview = await coordinator.preview(store, desired, seconds=10)
    assert (await preview.disconnect())["state"] == "reverted"
    await restored()
    print("native: recovery case passed", file=sys.stderr, flush=True)

    # Kill an actual client process. The guard has a separate session/process.
    request = root / "layout.json"
    write_json(request, desired.to_dict())
    client = root / "client.py"
    client.write_text("""import asyncio,json,os
from pathlib import Path
from monarch.backends.hyprland.session import Session
from monarch.domain.layout import Layout
from monarch.services.coordinator import Coordinator
from monarch.storage.managed import Managed
async def run():
 c=Coordinator(Session.from_environment(),state_home=Path(os.environ['PROBE_STATE']))
 layout=Layout.parse(json.loads(Path(os.environ['PROBE_LAYOUT']).read_text()))
 h=await c.preview(Managed(Path(os.environ['PROBE_ROOT'])),layout,seconds=10)
 print('PENDING',flush=True)
 await h.wait()
asyncio.run(run())
""")
    child_env = dict(
        env,
        PROBE_STATE=str(root / "state"),
        PROBE_LAYOUT=str(request),
        PROBE_ROOT=str(store.directory),
    )
    child = await asyncio.create_subprocess_exec(
        sys.executable, str(client), env=child_env, stdout=asyncio.subprocess.PIPE
    )
    try:
        assert child.stdout is not None
        assert (await asyncio.wait_for(child.stdout.readline(), 15)).strip() == b"PENDING"
        child.kill()
        await child.wait()
        for _ in range(50):
            status = coordinator.paths.status()
            if status and status["status"] == "reverted":
                break
            await asyncio.sleep(0.1)
        else:
            raise MonarchError("Guard did not survive native client SIGKILL.")
        await restored()
        print("native: client SIGKILL recovered", file=sys.stderr, flush=True)
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()

    preview = await coordinator.preview(store, desired, seconds=10)
    assert (await preview.decide(keep=True, persist=True))["state"] == "kept"
    assert store.read()[0] == desired
    assert desired.matches(await writer.observe())
    preview = await coordinator.preview(store, baseline, seconds=10)
    assert (await preview.decide(keep=True, persist=True))["state"] == "kept"
    await restored()
    print("native: recovery case passed", file=sys.stderr, flush=True)
    # Fail the first real reload after candidate persistence. The filesystem and
    # all other compositor calls remain real, and the guard must restore both.
    import shutil

    executable = shutil.which("hyprctl")
    assert executable
    marker = root / "fail-once"
    marker.touch(mode=0o600)
    wrapper = root / "hyprctl-fault"
    wrapper.write_text(
        f"#!{await asyncio.to_thread(Path(sys.executable).resolve)}\n"
        + "import os,sys,hashlib\nfrom pathlib import Path\n"
        + f"marker=Path({str(marker)!r})\nfile=Path({str(store.monitors)!r})\n"
        + f"original={digest(read_private(store.monitors))!r}\n"
        + 'if (sys.argv[-1]=="reload" and marker.exists()\n'
        + "    and hashlib.sha256(file.read_bytes()).hexdigest()!=original):\n"
        + " marker.unlink()\n sys.exit(1)\n"
        + f"os.execv({executable!r},[{executable!r},*sys.argv[1:]])\n"
    )
    wrapper.chmod(0o700)
    faulty = Coordinator(session, state_home=root / "state", env=env, executable=str(wrapper))
    preview = await faulty.preview(store, desired, seconds=10)
    assert (await preview.decide(keep=True, persist=True))["state"] == "reverted"
    assert not marker.exists()
    await restored()
    print("native: failed persistence reload recovered", file=sys.stderr, flush=True)
    # Kill the guard itself to exercise durable, explicit recovery.
    preview = await coordinator.preview(store, desired, seconds=10)
    preview.process.kill()
    await preview.process.wait()
    assert coordinator.paths.status()["status"] == "pending"
    result = await coordinator.recover()
    assert result["state"] == "reverted"
    await restored()
    print("native: recovery case passed", file=sys.stderr, flush=True)
    preview = await coordinator.preview(store, desired, seconds=10)
    result = await asyncio.to_thread(
        subprocess.run,
        ["hyprctl", "-i", session.signature, "output", "remove", "MONARCH-B"],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert (await preview.wait())["state"] == "degraded"
    assert any(m.disabled is False and not m.mirror_of for m in await writer.observe())
    print("native: virtual hot-unplug recovered", file=sys.stderr, flush=True)
    return {
        "hyprland": "0.57.2",
        "backend": "nested-wayland/virtual",
        "preview_revert": True,
        "deadline_recovery": True,
        "client_eof_recovery": True,
        "client_sigkill_recovery": True,
        "explicit_persistence": True,
        "failed_persistence_reload_restores_file": True,
        "virtual_hot_unplug_degraded_recovery": True,
        "guard_sigkill_manual_recovery": True,
        "parent_monitor_mutations": 0,
    }


def run():
    if not os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("XDG_RUNTIME_DIR"):
        raise MonarchError("A parent Wayland session is required.")
    parent = Path(os.environ["WAYLAND_DISPLAY"])
    if not parent.is_absolute():
        parent = Path(os.environ["XDG_RUNTIME_DIR"]) / parent
    with tempfile.TemporaryDirectory(prefix="mr", dir="/tmp") as temporary:
        root = Path(temporary)
        runtime = root / "r"
        runtime.mkdir(mode=0o700)
        for directory in ("cache", "state", "xdg"):
            (root / directory).mkdir(mode=0o700)
        store = Managed(root / "owned")
        seed = Layout((Output("WAYLAND-1", "", "", "", "1280x720@60", 1, 0, 0, 0),))
        store.create(seed)
        env = dict(
            os.environ,
            XDG_RUNTIME_DIR=str(runtime),
            XDG_CONFIG_HOME=str(root / "xdg"),
            XDG_CACHE_HOME=str(root / "cache"),
            XDG_STATE_HOME=str(root / "state"),
            WAYLAND_DISPLAY=str(parent),
            AQ_DRM_DEVICES="/dev/null",
            LIBSEAT_BACKEND="noop",
            HYPRLAND_NO_SD_NOTIFY="1",
        )
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        env.pop("HYPRLAND_CONFIG", None)
        with (root / "log").open("w") as log:
            process = subprocess.Popen(
                ["Hyprland", "--config", str(store.root)], env=env, stdout=log, stderr=log
            )
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and process.poll() is None:
                    sockets = list(runtime.glob("hypr/*/.socket.sock"))
                    if sockets:
                        signature = sockets[0].parent.name
                        if signature == os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
                            raise MonarchError("Refusing to target the parent compositor.")
                        env["HYPRLAND_INSTANCE_SIGNATURE"] = signature
                        try:
                            status = subprocess.run(
                                ["hyprctl", "-i", signature, "-j", "status"],
                                env=env,
                                capture_output=True,
                                text=True,
                                timeout=1,
                            )
                            if (
                                status.returncode == 0
                                and json.loads(status.stdout)["backend"] == "wayland"
                            ):
                                break
                        except (ValueError, subprocess.TimeoutExpired):
                            pass
                    time.sleep(0.1)
                else:
                    raise MonarchError("Nested compositor unavailable; check render-device access.")
                result = asyncio.run(exercise(Session(runtime, signature), env, store, root))
                print(json.dumps(result, indent=2))
            except BaseException:
                logs = list(runtime.glob("hypr/*/hyprland.log"))
                if logs:
                    Path("/tmp/monarch-recovery-probe.log").write_bytes(logs[0].read_bytes())
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    run()
