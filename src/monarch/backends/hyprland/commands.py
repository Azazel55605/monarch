"""Bounded subprocess transport with a read-only command allowlist."""

import asyncio
import json
import math
import os
from collections.abc import Mapping
from typing import Any

from monarch.backends.hyprland.session import Session
from monarch.errors import MonarchError

READ_COMMANDS = frozenset({("version",), ("status",), ("monitors", "all")})


class Hyprctl:
    def __init__(
        self,
        session: Session,
        *,
        executable: str = "hyprctl",
        timeout: float = 3.0,
        max_output: int = 4 * 1024 * 1024,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0 or max_output < 1:
            raise ValueError("Command bounds must be positive and finite")
        self.session = session
        self.executable = executable
        self.timeout = timeout
        self.max_output = max_output
        self.env = dict(os.environ if env is None else env)
        self.env["XDG_RUNTIME_DIR"] = str(session.runtime_dir)
        self.env["HYPRLAND_INSTANCE_SIGNATURE"] = session.signature

    async def read(self, *command: str) -> Any:
        if command not in READ_COMMANDS:
            raise MonarchError(
                "Command rejected: the inspection transport permits read-only discovery only."
            )
        raw = await self._request(command, json_output=True)
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise MonarchError(
                "hyprctl returned invalid JSON for " + " ".join(command) + "."
            ) from exc

    async def _request(self, command: tuple[str, ...], *, json_output: bool = False) -> bytes:
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-i",
                self.session.signature,
                *(["-j"] if json_output else []),
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
        except FileNotFoundError as exc:
            raise MonarchError("hyprctl was not found. Install Hyprland and check PATH.") from exc
        except OSError as exc:
            raise MonarchError("Cannot start hyprctl. Check executable permissions.") from exc
        size = 0

        async def drain(stream: asyncio.StreamReader | None) -> bytes:
            nonlocal size
            assert stream is not None
            chunks = []
            while chunk := await stream.read(65536):
                size += len(chunk)
                if size > self.max_output:
                    raise MonarchError("hyprctl response exceeded the configured size limit.")
                chunks.append(chunk)
            return b"".join(chunks)

        tasks = [
            asyncio.create_task(drain(process.stdout)),
            asyncio.create_task(drain(process.stderr)),
        ]
        try:
            async with asyncio.timeout(self.timeout):
                stdout, _ = await asyncio.gather(*tasks)
                await process.wait()
            if process.returncode != 0:
                raise MonarchError("hyprctl request failed. Check the selected Hyprland session.")
            return stdout
        except TimeoutError as exc:
            raise MonarchError("hyprctl timed out; the compositor may be unavailable.") from exc
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
