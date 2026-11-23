"""Subprocess test compositor transport; never included in the application wheel."""

import fcntl
import json
import os
import re
import sys
from pathlib import Path

from monarch.domain.monitors import Mode
from monarch.storage.managed import Managed

path = Path(os.environ["MONARCH_FAKE_STATE"])
with path.open("r+") as stream:
    fcntl.flock(stream, fcntl.LOCK_EX)
    data = json.load(stream)
    args = sys.argv[1:]
    args = args[2:]  # -i signature
    if args and args[0] == "-j":
        args = args[1:]
    command = args[0]
    result = "ok"
    if data.get("gone"):
        raise SystemExit(1)
    if command == "version":
        result = json.dumps({"version": "0.57.2", "tag": "v0.57.2", "dirty": False})
    elif command == "status":
        result = json.dumps({"configProvider": "lua", "backend": "wayland"})
    elif command == "monitors":
        result = json.dumps(data["monitors"])
    elif command == "configerrors":
        result = "injected error" if data.get("errors") else ""
    else:
        if command == "reload":
            if data.get("reject_reload"):
                raise SystemExit(1)
            layout, _ = Managed(Path(data["root"])).read()
            updates = layout.outputs
        elif command == "eval":
            # Parse only this test's generated ASCII names and known scalar fields.
            from monarch.domain.layout import Output

            text = args[1]
            fields = dict(re.findall(r'(\w+)=("[^"\\]*"|true|false|-?[\d.]+)', text))
            values = {k: json.loads(v) for k, v in fields.items()}
            x, y = values["position"].split("x")
            name = values["output"]
            live = next(m for m in data["monitors"] if m["name"] == name)
            updates = [
                Output(
                    name,
                    live["make"],
                    live["model"],
                    live["serial"],
                    values["mode"],
                    values["scale"],
                    values["transform"],
                    int(x),
                    int(y),
                    not values["disabled"],
                    values["mirror"],
                    values.get("vrr", 0),
                )
            ]
        else:
            raise SystemExit(1)
        data["mutations"] = data.get("mutations", 0) + 1
        if data["mutations"] == data.get("fail_at"):
            stream.seek(0)
            json.dump(data, stream)
            stream.truncate()
            raise SystemExit(1)
        if data.get("vrr_rule_cache"):
            # Native 0.57.2 refreshes VRR using the old active rule before
            # adopting soft/hard changes; a VRR-only rule compares equal.
            for m in data["monitors"]:
                m["vrr"] = bool(m.get("cached_vrr", int(m.get("vrr", False))))
        for output in updates:
            for m in data["monitors"]:
                if m["name"] == output.name:
                    mode = (
                        Mode.parse(output.mode + "Hz")
                        if output.mode != "preferred"
                        else Mode.parse(m["availableModes"][0])
                    )
                    if data.get("vrr_rule_cache"):
                        changed = any(
                            (
                                m["width"] != mode.width,
                                m["height"] != mode.height,
                                abs(m["refreshRate"] - float(mode.refresh_hz)) > 0.02,
                                m["x"] != output.x,
                                m["y"] != output.y,
                                m["scale"] != output.scale,
                                m["transform"] != output.transform,
                                m["disabled"] == output.enabled,
                                (m.get("mirrorOf") or "none") != (output.mirror or "none"),
                            )
                        )
                        if changed:
                            m["cached_vrr"] = output.vrr
                    m.update(
                        width=mode.width,
                        height=mode.height,
                        refreshRate=float(mode.refresh_hz),
                        x=output.x,
                        y=output.y,
                        scale=output.scale,
                        transform=output.transform,
                        disabled=not output.enabled,
                        mirrorOf=output.mirror or "none",
                        vrr=m.get("vrr")
                        if data.get("ignore_vrr") or data.get("vrr_rule_cache")
                        else bool(output.vrr),
                    )
    stream.seek(0)
    json.dump(data, stream)
    stream.truncate()
print(result)
