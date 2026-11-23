#!/usr/bin/env python3
"""Opt-in Lua VRR syntax check on owned virtual outputs, not hardware certification."""

import asyncio
import json
from dataclasses import replace

from probe_recovery import nested_session, prepare_baseline

from monarch.domain.layout import Layout


async def exercise(session, env, store):
    writer, baseline = await prepare_baseline(session, env, store)
    version = await writer.read("version")
    assert version.get("version") == "0.57.2" and version.get("dirty") is False
    target = next(o for o in baseline.outputs if o.name == "MONARCH-A")
    try:
        # Virtual displays cannot certify Adaptive Sync. Only validate the exact
        # generated Lua fields against the real parser on the owned compositor.
        intermediate = replace(target, x=target.x + 1, vrr=0)
        await writer.set_output(intermediate)
        for _ in range(20):
            selected = tuple(m for m in await writer.observe() if m.name == target.name)
            if Layout((intermediate,)).matches(selected):
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Native intermediate position refresh was not observed.")
        await writer.set_output(target)
        for _ in range(20):
            if baseline.matches(await writer.observe()):
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Native position restoration was not observed.")
        await writer.set_output(replace(target, vrr=1))
        await writer.check_errors()
        await writer.set_output(replace(target, vrr=0))
        await writer.check_errors()
        assert baseline.matches(await writer.observe())
    finally:
        await writer.reload()
    print(
        json.dumps(
            {
                "native_lua_vrr_off_on_fields": True,
                "native_soft_refresh_position_roundtrip": True,
                "hardware_vrr_certified": False,
                "parent_monitor_mutations": 0,
            }
        )
    )


if __name__ == "__main__":
    with nested_session() as (session, env, store, root):
        asyncio.run(exercise(session, env, store))
