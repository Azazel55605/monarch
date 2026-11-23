#!/usr/bin/env python3
"""Opt-in feasibility probe in a new temporary nested Wayland compositor.

Never targets the invoking session. Requires Hyprland 0.57.2, render-device
access, and a parent Wayland compositor. No third-party Python dependencies.
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


class ProbeError(Exception):
    pass


def run_probe() -> dict[str, object]:
    parent = Path(os.environ.get("WAYLAND_DISPLAY", ""))
    if not os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("XDG_RUNTIME_DIR"):
        raise ProbeError("A parent Wayland session is required.")
    if not parent.is_absolute():
        parent = Path(os.environ["XDG_RUNTIME_DIR"]) / parent
    # Short paths matter: a Hyprland signature occupies most of sockaddr_un.
    with tempfile.TemporaryDirectory(prefix="mp", dir="/tmp") as directory:
        root = Path(directory)
        runtime = root / "r"
        runtime.mkdir(mode=0o700)
        config = root / "hyprland.lua"
        managed = root / "managed.lua"
        for name in ("cache", "state", "config"):
            (root / name).mkdir()
        original = (
            'hl.monitor({output="",mode="1280x720@60",scale=1,transform=0,position="0x0"})\n'
            'require("managed")\n'
        )
        config.write_text(original)
        managed.write_text("-- No specific output rules at baseline.\n")
        env = dict(os.environ)
        env.update(
            {
                "XDG_RUNTIME_DIR": str(runtime),
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_CACHE_HOME": str(root / "cache"),
                "XDG_STATE_HOME": str(root / "state"),
                "WAYLAND_DISPLAY": str(parent),
                "AQ_DRM_DEVICES": "/dev/null",
                "LIBSEAT_BACKEND": "noop",
                "HYPRLAND_NO_SD_NOTIFY": "1",
            }
        )
        env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
        env.pop("HYPRLAND_CONFIG", None)
        with (root / "log").open("w") as log:
            process = subprocess.Popen(
                ["Hyprland", "--config", str(config)],
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                signature = None
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and process.poll() is None:
                    sockets = list(runtime.glob("hypr/*/.socket.sock"))
                    if sockets:
                        signature = sockets[0].parent.name
                        env["HYPRLAND_INSTANCE_SIGNATURE"] = signature
                        try:
                            reply = subprocess.run(
                                ["hyprctl", "-i", signature, "-j", "status"],
                                env=env,
                                capture_output=True,
                                text=True,
                                timeout=1,
                            )
                            if (
                                reply.returncode == 0
                                and json.loads(reply.stdout).get("backend") == "wayland"
                            ):
                                break
                        except (subprocess.TimeoutExpired, ValueError):
                            pass
                    time.sleep(0.1)
                else:
                    raise ProbeError(
                        "Nested Wayland compositor could not start; check render access."
                    )
                assert signature is not None
                if signature == os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
                    raise ProbeError("Refusing to target the parent compositor.")

                def command(*args: str, json_output: bool = False):
                    flags = ["-j"] if json_output else []
                    response = subprocess.run(
                        ["hyprctl", "-i", signature, *flags, *args],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if response.returncode != 0:
                        raise ProbeError("Nested compositor command failed: " + args[0])
                    return json.loads(response.stdout) if json_output else response.stdout.strip()

                version = command("version", json_output=True)
                if version.get("version") != "0.57.2":
                    raise ProbeError("This feasibility probe is pinned to Hyprland 0.57.2.")
                monitors = command("monitors", "all", json_output=True)
                if len(monitors) != 1 or not monitors[0]["name"].startswith("WAYLAND-"):
                    raise ProbeError(
                        "Expected one nested WAYLAND output; refusing further mutations."
                    )
                # Parent tiling controls the nested window's dimensions. Use a
                # fixed-size headless output inside that verified nested session
                # so fractional scale checks have valid integer dimensions.
                command("output", "create", "headless", "MONARCH-PROBE")
                time.sleep(0.3)
                output = "MONARCH-PROBE"
                baseline = next(
                    m for m in command("monitors", "all", json_output=True) if m["name"] == output
                )
                output_lua = json.dumps(output)  # Generated ASCII backend name only.

                def check_scale(expected: float):
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        observed = next(
                            m
                            for m in command("monitors", "all", json_output=True)
                            if m["name"] == output
                        )
                        if abs(observed["scale"] - expected) < 0.001:
                            return observed
                        time.sleep(0.1)
                    raise ProbeError(f"Nested scale did not settle to {expected}.")

                def reload_config():
                    command("reload")
                    errors = command("configerrors")
                    if errors:
                        raise ProbeError("Nested config errors; no result accepted.")

                command("eval", f"hl.monitor({{output={output_lua},scale=1.25}})")
                check_scale(1.25)
                command("eval", f"hl.monitor({{output={output_lua},transform=0}})")
                check_scale(1.25)  # Omitted scale stays in the existing named rule.
                reload_config()
                restored = check_scale(1)
                for key in ("scale", "transform", "x", "y"):
                    if restored[key] != baseline[key]:
                        raise ProbeError("Baseline layout did not round-trip on reload.")

                managed.write_text(f"hl.monitor({{output={output_lua},scale=1.25}})\n")
                config.write_text(original + f"hl.monitor({{output={output_lua},scale=2}})\n")
                reload_config()
                check_scale(2)
                config.write_text(original)
                reload_config()
                check_scale(1.25)
                managed.write_text(f"hl.monitor({{output={output_lua},scale=1}})\n")
                reload_config()
                check_scale(1)
                managed.write_text("-- Specific rule removed; fallback should win again.\n")
                reload_config()
                check_scale(1)
                # A future fallback change must now take effect, proving that a
                # stale named override did not survive reload/removal.
                config.write_text(original.replace("scale=1,", "scale=1.25,"))
                reload_config()
                check_scale(1.25)
                config.write_text(original)
                reload_config()
                check_scale(1)
                return {
                    "hyprland": version["version"],
                    "backend": "nested-wayland",
                    "runtime_partial_update_merges": True,
                    "reload_removes_runtime_rule": True,
                    "include_order_last_named_update_wins": True,
                    "required_module_reexecuted_on_reload": True,
                    "removed_include_rule_releases_fallback": True,
                    "baseline_layout_round_trip": True,
                    "general_arbitrary_rule_restoration_proven": False,
                }
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    try:
        print(json.dumps(run_probe(), indent=2))
    except (ProbeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Probe unavailable: {error}")
        raise SystemExit(1) from None
