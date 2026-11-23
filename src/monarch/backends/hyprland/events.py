"""Bounded event framing and reconnecting, coalesced invalidations."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from monarch.backends.hyprland.session import Session
from monarch.errors import MonarchError

TOPOLOGY_EVENTS = frozenset(
    {
        "monitoradded",
        "monitoraddedv2",
        "monitorremoved",
        "monitorremovedv2",
        "configreloaded",
    }
)


@dataclass(frozen=True)
class Event:
    name: str
    payload: str


class EventFramer:
    def __init__(self, max_line: int = 65536) -> None:
        self.buffer = b""
        self.max_line = max_line

    def feed(self, chunk: bytes) -> tuple[Event, ...]:
        self.buffer += chunk
        lines = self.buffer.split(b"\n")
        self.buffer = lines.pop()
        if len(self.buffer) > self.max_line or any(len(line) > self.max_line for line in lines):
            self.buffer = b""
            raise MonarchError("Hyprland event line exceeds the size limit.")
        events = []
        for line in lines:
            try:
                name, separator, payload = line.decode("utf-8").partition(">>")
            except UnicodeError:
                continue
            if separator and name in TOPOLOGY_EVENTS:
                events.append(Event(name, payload))
        return tuple(events)


class EventWatcher:
    """One-session watcher; restart with a new environment for a new signature.

    Payloads can contain identifiers, so consumers receive only invalidations.
    A bounded queue, quiet period and maximum delay coalesce event storms.
    """

    def __init__(
        self,
        session: Session,
        *,
        debounce: float = 0.25,
        max_delay: float = 1.0,
        retry_min: float = 0.25,
        retry_max: float = 5.0,
    ) -> None:
        if not 0 < debounce <= max_delay or not 0 < retry_min <= retry_max:
            raise ValueError("Invalid event timing bounds")
        self.session = session
        self.debounce = debounce
        self.max_delay = max_delay
        self.retry_min = retry_min
        self.retry_max = retry_max

    async def _receive(self, queue: asyncio.Queue[str]) -> None:
        def offer(reason: str) -> None:
            if not queue.full():
                queue.put_nowait(reason)

        retry = self.retry_min
        while True:
            writer: asyncio.StreamWriter | None = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_unix_connection(self.session.event_socket),
                    timeout=3.0,
                )
                offer("connected")  # Reconnect always requires authoritative discovery.
                framer = EventFramer()
                while chunk := await reader.read(8192):
                    retry = self.retry_min
                    if framer.feed(chunk):
                        offer("topology")
            except (OSError, TimeoutError, MonarchError):
                pass
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass
            offer("disconnected")
            await asyncio.sleep(retry)
            retry = min(self.retry_max, retry * 2)

    async def invalidations(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        task = asyncio.create_task(self._receive(queue))
        try:
            while True:
                reason = await queue.get()
                deadline = asyncio.get_running_loop().time() + self.max_delay
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        reason = await asyncio.wait_for(queue.get(), min(self.debounce, remaining))
                    except TimeoutError:
                        break
                yield reason
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
