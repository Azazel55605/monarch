import asyncio
from contextlib import aclosing

import pytest

from monarch.backends.hyprland.events import EventFramer, EventWatcher
from monarch.backends.hyprland.session import Session
from monarch.errors import MonarchError


def test_split_coalesced_and_unrelated_events():
    framer = EventFramer()
    assert framer.feed(b"monitoradd") == ()
    events = framer.feed(
        b"edv2>>3,DP-DEMO,Example\nactivewindow>>private title\nconfigreloaded>>\n"
    )
    assert [x.name for x in events] == ["monitoraddedv2", "configreloaded"]
    assert events[0].payload == "3,DP-DEMO,Example"
    assert framer.feed(b"broken\n\xff>>bad\n") == ()


@pytest.mark.parametrize("data", [b"x" * 65, b"x" * 65 + b"\n"])
def test_oversized_lines(data):
    with pytest.raises(MonarchError, match="size limit"):
        EventFramer(max_line=64).feed(data)


def test_socket_reconnect_refresh_and_cancellation(tmp_path):
    async def run():
        session = Session(tmp_path, "session")
        session.directory.mkdir(parents=True)
        connections = 0
        handlers = []

        async def handle(reader, writer):
            nonlocal connections
            handlers.append(asyncio.current_task())
            connections += 1
            try:
                if connections == 1:
                    # Multiple writes, split frame, and a burst must coalesce.
                    writer.write(b"monitoradd")
                    await writer.drain()
                    writer.write(b"ed>>DP-DEMO\n" * 1 + b"configreloaded>>\n" * 100)
                    await writer.drain()
                    await asyncio.sleep(0.03)
                else:
                    await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(handle, path=session.event_socket)
        watcher = EventWatcher(
            session, debounce=0.01, max_delay=0.03, retry_min=0.01, retry_max=0.02
        )
        try:
            async with aclosing(watcher.invalidations()) as events:
                await asyncio.wait_for(anext(events), 1)
                for _ in range(10):
                    reason = await asyncio.wait_for(anext(events), 1)
                    if connections >= 2 and reason == "connected":
                        break
                assert connections >= 2
        finally:
            server.close()
            await server.wait_closed()
            await asyncio.gather(*handlers)

    asyncio.run(run())


def test_missing_socket_retries_without_leaking_task(tmp_path):
    async def run():
        watcher = EventWatcher(
            Session(tmp_path, "missing"),
            debounce=0.001,
            max_delay=0.002,
            retry_min=0.005,
            retry_max=0.01,
        )
        async with aclosing(watcher.invalidations()) as events:
            assert await asyncio.wait_for(anext(events), 0.5) == "disconnected"

    asyncio.run(run())
