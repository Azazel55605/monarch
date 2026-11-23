"""Shared client API for CLI and future Qt/tray entry points."""

import asyncio
import json
import os
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from monarch.backends.hyprland.session import Session
from monarch.domain.layout import Layout
from monarch.domain.quick_layout import connection_key
from monarch.errors import MonarchError
from monarch.services.state import TERMINAL, Paths
from monarch.storage.files import write_json
from monarch.storage.managed import Managed


class Preview:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process
        self.id = ""
        self.deadline = 0.0
        self.result: dict[str, Any] | None = None
        self._waiter: asyncio.Task[dict[str, Any]] | None = None

    async def receive(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        line = await self.process.stdout.readline()
        if not line:
            await self.process.wait()
            raise MonarchError("Recovery guard exited; inspect monarch transaction status.")
        message: dict[str, Any] = json.loads(line)
        if message["state"] == "armed":
            self.id = message["id"]
        if message["state"] == "pending":
            self.deadline = message["deadline"]
        return message

    async def wait(self) -> dict[str, Any]:
        if self._waiter is None:
            self._waiter = asyncio.create_task(self._collect())
        return await asyncio.shield(self._waiter)

    async def _collect(self) -> dict[str, Any]:
        if self.result is None:
            while True:
                message = await self.receive()
                if message["state"] not in ("armed", "pending"):
                    self.result = message
                    await self.process.wait()
                    if self.process.stdin:
                        self.process.stdin.close()
                    break
        return self.result

    async def decide(self, *, keep: bool, persist: bool = False) -> dict[str, Any]:
        if self.result:
            return self.result
        assert self.process.stdin is not None
        self.process.stdin.write(
            json.dumps(
                {"id": self.id, "action": "keep" if keep else "revert", "persist": persist}
            ).encode()
            + b"\n"
        )
        try:
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        return await self.wait()

    async def disconnect(self) -> dict[str, Any]:
        if self.process.stdin:
            self.process.stdin.close()
        return await self.wait()


class Coordinator:
    def __init__(
        self,
        session: Session,
        *,
        state_home: Path | None = None,
        executable: str = "hyprctl",
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.session = session
        self.env = dict(os.environ if env is None else env)
        self.env["XDG_RUNTIME_DIR"] = str(session.runtime_dir)
        self.env["HYPRLAND_INSTANCE_SIGNATURE"] = session.signature
        self.state_home = state_home or Path(
            self.env.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))
        )
        self.paths = Paths.for_session(session, self.state_home)
        self.executable = executable

    async def launch(self, request: dict[str, Any]) -> Preview:
        request.update(state_home=str(self.state_home), executable=self.executable)
        path = self.paths.state / f"request-{uuid.uuid4().hex}.json"
        write_json(path, request, create=True)
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "monarch.services.guard",
                str(path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=self.env,
                start_new_session=True,
                limit=8192,
            )
        except OSError as exc:
            path.unlink(missing_ok=True)
            raise MonarchError("Could not start the independent recovery guard.") from exc
        return Preview(process)

    async def preview(
        self,
        managed: Managed,
        layout: Layout,
        *,
        seconds: float = 15,
        automation: dict[str, str] | None = None,
        topology_snapshot: Layout | None = None,
    ) -> Preview:
        Layout.parse(layout.to_dict())
        if not 1 <= seconds <= 60:
            raise MonarchError("Preview duration must be between 1 and 60 seconds.")
        if automation is None:
            from monarch.storage.automation import pin

            pin(self.paths, connections=connection_key(layout.outputs))
            # Revocation is visible to the active automatic guard. Wait only for
            # automatic recovery, never steal a manual transaction's lock.
            for _ in range(100):
                active = self.paths.status()
                if not active or not active.get("automation") or active.get("status") in TERMINAL:
                    break
                await asyncio.sleep(0.1)
        handle = await self.launch(
            {
                "action": "preview",
                "root": str(managed.directory),
                "layout": layout.to_dict(),
                "seconds": seconds,
                "automation": automation,
                "topology_snapshot": topology_snapshot.to_dict() if topology_snapshot else None,
            }
        )
        try:
            async with asyncio.timeout(35):
                while True:
                    message = await handle.receive()
                    if message["state"] == "pending":
                        return handle
                    if message["state"] != "armed":
                        handle.result = message
                        await handle.process.wait()
                        raise MonarchError(
                            "Preview did not start: "
                            + message.get("reason", message["state"])
                            + " "
                            + message.get("detail", "")
                        )
        except BaseException:
            if handle.process.stdin:
                handle.process.stdin.close()  # EOF requests rollback; never kill the guard.
            raise

    async def recover(self) -> dict[str, Any]:
        handle = await self.launch({"action": "recover"})
        return await handle.wait()
