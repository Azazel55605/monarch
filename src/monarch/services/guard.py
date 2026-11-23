"""Independent process: holds the lock and restores on deadline or client EOF."""

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Any

from monarch.backends.hyprland.inspector import Inspector
from monarch.backends.hyprland.session import Session, config_location
from monarch.backends.hyprland.writer import Writer
from monarch.domain.layout import Layout
from monarch.errors import MonarchError
from monarch.services.state import Paths, SessionLock, session_token
from monarch.services.transaction import Transaction
from monarch.storage.files import read_json
from monarch.storage.managed import Managed


def notify(state: str, **extra: object) -> None:
    try:
        print(json.dumps({"state": state, **extra}), flush=True)
    except (BrokenPipeError, OSError):
        # Recovery is independent of the parent's output/terminal lifetime.
        pass


async def input_reader() -> asyncio.StreamReader:
    reader = asyncio.StreamReader(limit=4096)
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)
    return reader


async def controlled(transaction: Transaction, seconds: float) -> None:
    reader = await input_reader()
    action: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()

    async def control() -> None:
        while True:
            line = await reader.readline()
            if not line:
                raise MonarchError("client_disconnected")
            try:
                message = json.loads(line)
            except ValueError as exc:
                raise MonarchError("invalid_confirmation") from exc
            if (
                not isinstance(message, dict)
                or set(message) != {"action", "persist", "id"}
                or transaction.record is None
                or message["id"] != transaction.record["id"]
                or message["action"] not in ("keep", "revert")
                or type(message["persist"]) is not bool
                or not transaction.pending
                or action.done()
            ):
                raise MonarchError("invalid_confirmation")
            action.set_result(message)

    async def operation() -> None:
        await transaction.apply()
        assert transaction.record is not None
        notify("pending", id=transaction.record["id"], deadline=transaction.record["deadline"])
        message = await action
        if message["action"] == "revert":
            raise MonarchError("user_revert")
        if transaction.authorize is not None and message["persist"]:
            raise MonarchError("Automatic previews cannot persist configuration.")
        await transaction.keep(message["persist"])

    async def monitor() -> None:
        while True:
            await asyncio.sleep(0.4)
            if transaction.authorize is not None:
                transaction.authorize()
            if transaction.pending:
                await transaction.check_pending()

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    tasks = [
        asyncio.create_task(operation()),
        asyncio.create_task(control()),
        asyncio.create_task(monitor()),
        asyncio.create_task(asyncio.sleep(seconds)),
        asyncio.create_task(stopped.wait()),
    ]
    reason = "preview_failed"
    success = False
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        # Deadline/client loss wins ties with a confirmation.
        if tasks[3] in done:
            reason = "deadline_elapsed"
        elif tasks[4] in done:
            reason = "guard_interrupted"
        elif tasks[1] in done:
            reason = "client_disconnected"
        elif tasks[2] in done:
            reason = "preview_invalidated"
        elif tasks[0] in done:
            if tasks[0].exception() is None:
                success = True
            else:
                reason = (
                    "user_revert" if str(tasks[0].exception()) == "user_revert" else "apply_failed"
                )
        for task in (tasks[0], tasks[2]):
            if task in done and not task.cancelled() and task.exception() is not None:
                error = task.exception()
                assert transaction.record is not None
                transaction.record["failure"] = (
                    str(error) if isinstance(error, MonarchError) else type(error).__name__
                )
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if not success:
        await transaction.rollback(reason)


def load_request(request_path: Path) -> Any:
    request = read_json(request_path)
    request_path.unlink()
    return request


async def run(request_path: Path) -> int:
    request = load_request(request_path)
    if not isinstance(request, dict) or request.get("action") not in ("preview", "recover"):
        raise MonarchError("Invalid guard request.")
    session = Session.from_environment()
    # Guard re-derives session paths rather than trusting a client-provided runtime lock.
    paths = Paths.for_session(session, Path(request["state_home"]))
    writer = Writer(session, executable=request.get("executable", "hyprctl"))
    transaction = Transaction(writer, paths, lambda: session_token(session))

    allow_xdg = False

    def verified_token() -> str:
        if transaction.record is not None:
            location = config_location(session, resolve_xdg=allow_xdg)
            if not location.verified or location.path != transaction.managed.root:
                raise MonarchError("Active configuration ownership changed; refusing replay.")
        return session_token(session)

    transaction.token = verified_token
    with SessionLock(paths):
        inspection = await Inspector(writer).inspect()
        if (
            not inspection.capabilities.stable_baseline
            or not inspection.capabilities.lua_advertised
        ):
            raise MonarchError("Mutations require the clean Hyprland 0.57.2 Lua baseline.")
        allow_xdg = inspection.config.source == "compositor XDG reload search"
        writer.full_reset = allow_xdg
        if request["action"] == "recover":
            await transaction.recover()
        else:
            seconds = request["seconds"]
            if type(seconds) not in (int, float) or not 1 <= seconds <= 60:
                raise MonarchError("Preview duration must be between 1 and 60 seconds.")
            authorization = request.get("automation")
            if authorization is not None:
                from monarch.storage.automation import permit

                if (
                    not isinstance(authorization, dict)
                    or set(authorization)
                    != {
                        "generation",
                        "policy_path",
                        "policy_digest",
                        "profiles_path",
                        "profiles_digest",
                    }
                    or not all(isinstance(v, str) for v in authorization.values())
                ):
                    raise MonarchError("Invalid automatic preview authorization.")
                transaction.authorize = lambda: permit(
                    paths,
                    authorization["generation"],
                    Path(authorization["policy_path"]),
                    authorization["policy_digest"],
                    Path(authorization["profiles_path"]),
                    authorization["profiles_digest"],
                )
                transaction.authorize()
            managed = Managed(Path(request["root"]))
            location = config_location(session, resolve_xdg=allow_xdg)
            active = location.path if location.verified else None
            snapshot = request.get("topology_snapshot")
            async with asyncio.timeout(20):
                await transaction.prepare(
                    managed,
                    Layout.parse(request["layout"]),
                    active,
                    seconds,
                    allow_topology_rebase=authorization is not None or snapshot is not None,
                    topology_snapshot=Layout.parse(snapshot) if snapshot is not None else None,
                )
            assert transaction.record is not None
            if authorization is not None:
                transaction.record["automation"] = authorization
                transaction.save("armed")
            notify("armed", id=transaction.record["id"])
            await controlled(transaction, seconds)
        assert transaction.record is not None
        notify(
            transaction.record["status"],
            id=transaction.record["id"],
            reason=transaction.record["reason"],
            detail=transaction.record.get("failure", ""),
        )
        return 0 if transaction.record["status"] in ("kept", "reverted", "degraded") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Internal Monarch recovery guard")
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        return asyncio.run(run(args.request))
    except (MonarchError, OSError, ValueError, KeyError, TypeError, TimeoutError):
        # Unexpected failures before mutation leave the journal intact. Controlled
        # operation exceptions after arming always enter rollback in controlled().
        notify(
            "failed", reason="Guard setup failed; inspect ownership, session, and recovery status."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
