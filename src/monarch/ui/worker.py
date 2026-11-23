"""Persistent asyncio worker thread; Qt's main thread never waits on compositor I/O."""

import asyncio
import time
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.events import EventWatcher
from monarch.backends.hyprland.inspector import Inspection, Inspector
from monarch.backends.hyprland.session import Session
from monarch.domain.layout import Layout
from monarch.domain.policy import Policy
from monarch.domain.profiles import MappingRequired, resolve
from monarch.errors import MonarchError
from monarch.services.automation import Automation
from monarch.services.coordinator import Coordinator, Preview
from monarch.services.state import TERMINAL
from monarch.storage.automation import Autostart, PolicyStore, control, pin
from monarch.storage.integration import IntegrationPlan
from monarch.storage.managed import Managed
from monarch.storage.profiles import ProfileStore, config_home


class BackendThread(QThread):
    automation_state = Signal(object)
    automation_settings = Signal(object, bool)
    automation_offer = Signal(object, object)
    automation_saved = Signal()
    automation_failed = Signal(str)
    observed = Signal(object)
    failed = Signal(str)
    pending = Signal(float)
    completed = Signal(object)
    integration_ready = Signal(object)
    installed = Signal(object)
    ownership = Signal(object)
    profiles = Signal(object)
    profile_loaded = Signal(object, bool)
    profile_notice = Signal(str)
    profile_failed = Signal(str)
    profile_mapping = Signal(object, object, bool, str)

    def __init__(
        self,
        *,
        session: Session | None = None,
        env: dict[str, str] | None = None,
        managed: Path | None = None,
        executable: str = "hyprctl",
    ) -> None:
        super().__init__()
        self.session = session
        self.env = env
        self.directory = managed
        self.executable = executable
        self.loop: asyncio.AbstractEventLoop | None = None
        self.handle: Preview | None = None
        self.closing = False
        self.previewing = False
        self._ready = False
        self._tasks: set[asyncio.Task[Any]] = set()
        self._plan: IntegrationPlan | None = None
        self._plan_layout: Layout | None = None
        self.automation: Automation | None = None
        self.ui_idle = False
        self.management_ready = False
        self.auto_authorization: dict[str, str] | None = None
        self.automatic_preview = False
        self.profile_store = ProfileStore(config_home(env))
        self.latest_inspection: Inspection | None = None
        self.inspector: Inspector | None = None
        self.coordinator: Coordinator | None = None

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        self.loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        self._stop = stop
        if self.closing:
            self.loop = None
            return
        try:
            self.session = self.session or Session.from_environment(self.env)
            self.inspector = Inspector(
                Hyprctl(self.session, executable=self.executable, env=self.env)
            )
            self.coordinator = Coordinator(self.session, env=self.env, executable=self.executable)
            await self._refresh()
            try:
                self.profiles.emit(self.profile_store.list())
            except (MonarchError, OSError) as exc:
                self.profile_failed.emit(str(exc))
            try:
                self.automation = Automation(self.coordinator, self.profile_store)
            except (MonarchError, OSError) as exc:
                self.automation_state.emit({"reason": str(exc), "pinned": False})
            else:
                timer = asyncio.create_task(self._automatic_loop())
                self._tasks.add(timer)
            self._ready = True
            task = asyncio.create_task(self._watch())
            self._tasks.add(task)
            await stop.wait()
        except (MonarchError, OSError) as exc:
            self.failed.emit(str(exc))
            self._ready = True
            await stop.wait()
        finally:
            if self.handle is not None:
                await self.handle.disconnect()
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            if self.automation is not None:
                self.automation.close()
            self.loop = None

    def submit(self, operation: str, *args: object) -> None:
        if self.loop is None or self.closing:
            return

        async def dispatch() -> None:
            try:
                if operation == "ui-state":
                    self.ui_idle = bool(args[0])
                    if (
                        len(args) > 1
                        and args[1]
                        and not self.automatic_preview
                        and self.coordinator
                    ):
                        if not control(self.coordinator.paths)["pinned"]:
                            pin(self.coordinator.paths)
                elif operation in {
                    "automation-settings",
                    "automation-save",
                    "automation-resume",
                    "automation-pin",
                }:
                    try:
                        self._automation_action(operation, *args)
                    except (MonarchError, OSError, ValueError) as exc:
                        self.automation_failed.emit(str(exc))
                elif operation == "automatic-preview":
                    await self._automatic_preview(*args)
                elif operation == "automatic-decline":
                    if self.automation:
                        self.automation.finish({"reason": "user_revert"})
                elif operation == "profile":
                    try:
                        await self._profile(*args)
                    except (MonarchError, OSError, ValueError) as exc:
                        self.profile_failed.emit(str(exc))
                elif operation == "refresh":
                    await self._refresh()
                elif operation == "preview":
                    await self._preview(*args)
                elif operation == "decide":
                    await self._decide(*args)
                elif operation == "prepare":
                    await self._prepare(*args)
                elif operation == "install":
                    await self._install(*args)
                elif operation == "recover":
                    assert self.coordinator is not None
                    self.completed.emit(await self.coordinator.recover())
                    await self._refresh()
            except (MonarchError, OSError, ValueError) as exc:
                if operation == "automatic-preview":
                    self.completed.emit({"state": "failed", "automatic": True})
                self.failed.emit(str(exc))
                await self._refresh()

        future = asyncio.run_coroutine_threadsafe(dispatch(), self.loop)
        future.add_done_callback(self._report_future)

    def _report_future(self, future: Future[None]) -> None:
        if not future.cancelled() and future.exception() is not None:
            self.failed.emit("The background operation failed. Refresh before trying again.")

    async def _watch(self) -> None:
        assert self.session is not None
        async for reason in EventWatcher(self.session).invalidations():
            if reason in {"connected", "disconnected"} and self.automation is not None:
                self.automation.stable_key = ""
            if self.handle is None and not self.previewing:
                try:
                    await self._refresh()
                except (MonarchError, OSError) as exc:
                    self.failed.emit(str(exc))

    async def _refresh(self) -> None:
        if self.inspector is None or self.handle is not None or self.previewing:
            return
        inspection = await self.inspector.inspect()
        self.latest_inspection = inspection
        if self.directory is None and inspection.config.path:
            candidate = inspection.config.path.parent / "monarch"
            if (candidate / "integration.json").is_file():
                self.directory = candidate
            elif inspection.config.path.name == "hyprland.lua":
                minimal = Managed(inspection.config.path.parent)
                try:
                    minimal.read()
                    self.directory = minimal.directory
                except (MonarchError, OSError):
                    pass
        ready = False
        reason = "Set up monitor management to enable guarded changes."
        if self.directory is not None:
            try:
                store = Managed(self.directory)
                store.read()
                if not inspection.config.verified or inspection.config.path != store.root:
                    raise MonarchError(
                        "The active configuration path cannot be verified for this integration."
                    )
                if (
                    not inspection.capabilities.stable_baseline
                    or not inspection.capabilities.lua_advertised
                ):
                    raise MonarchError("Guarded changes require Hyprland 0.57.2 with Lua.")
                assert self.coordinator is not None
                status = self.coordinator.paths.status()
                if status and status.get("status") not in TERMINAL:
                    raise MonarchError("An unfinished transaction needs recovery before editing.")
                if self.coordinator.paths.foreign_unfinished(store.directory):
                    raise MonarchError(
                        "An older session has unfinished recovery for this configuration."
                    )
                ready = True
                reason = "Monitor management is ready."
            except (MonarchError, OSError) as exc:
                reason = str(exc)
        self.management_ready = ready
        self.ownership.emit({"ready": ready, "reason": reason, "directory": self.directory})
        self.observed.emit(inspection)

    async def _preview(self, *args: object) -> None:
        layout = args[0]
        if (
            not isinstance(layout, Layout)
            or self.directory is None
            or self.handle is not None
            or self.previewing
        ):
            raise MonarchError("Monitor management is not ready for a preview.")
        assert self.coordinator is not None
        self.previewing = True
        try:
            self.handle = await self.coordinator.preview(
                Managed(self.directory),
                layout,
                automation=self.auto_authorization if self.automatic_preview else None,
            )
            self.pending.emit(self.handle.deadline)
            result = await self.handle.wait()
        finally:
            self.handle = None
            self.previewing = False
        if self.automatic_preview and self.automation:
            self.automation.finish(result)
            self.automation_state.emit(
                self.automation.status(
                    f"Automatic preview {result['state']}.", now=time.monotonic()
                )
            )
        self.completed.emit(dict(result, automatic=self.automatic_preview))
        await self._refresh()

    async def _decide(self, *args: object) -> None:
        if self.handle is not None:
            await self.handle.decide(keep=bool(args[0]), persist=bool(args[1]))

    async def _prepare(self, *args: object) -> None:
        root, dependencies = args
        assert isinstance(root, Path) and isinstance(dependencies, tuple)
        assert self.inspector is not None
        inspection = await self.inspector.inspect()
        if (
            not inspection.capabilities.stable_baseline
            or not inspection.capabilities.lua_advertised
        ):
            raise MonarchError("Desktop integration requires the supported Hyprland Lua baseline.")
        if not inspection.config.verified or inspection.config.path != root:
            raise MonarchError("Select the verified configuration root used by this compositor.")
        self._plan = IntegrationPlan.prepare(root, dependencies)
        self._plan_layout = Layout.capture(inspection.monitors)
        self._plan = replace(self._plan, baseline_preview=self._plan_layout)
        self.integration_ready.emit(self._plan)

    async def _install(self, *args: object) -> None:
        if self._plan is None:
            raise MonarchError("Prepare the integration preview first.")
        assert self.inspector is not None and self.coordinator is not None
        inspection = await self.inspector.inspect()
        if (
            not inspection.config.verified
            or inspection.config.path != self._plan.root
            or not inspection.capabilities.stable_baseline
            or not inspection.capabilities.lua_advertised
        ):
            raise MonarchError("The configuration target changed after preview; prepare it again.")
        layout = Layout.capture(inspection.monitors)
        if self._plan_layout is None or not self._plan_layout.matches(inspection.monitors):
            raise MonarchError("Monitor state changed after integration preview; preview it again.")
        from monarch.services.state import SessionLock

        with SessionLock(self.coordinator.paths):
            status = self.coordinator.paths.status()
            if status and status["status"] not in TERMINAL:
                raise MonarchError("Resolve unfinished recovery before changing integration.")
            if self.coordinator.paths.foreign_unfinished(self._plan.root.parent / "monarch"):
                raise MonarchError("An older session has unfinished recovery for this integration.")
            self.directory = self._plan.install(layout)
        self._plan = None
        self.installed.emit(self.directory)
        await self._refresh()

    async def _profile(self, *args: object) -> None:
        operation, payload = args
        assert isinstance(operation, str) and isinstance(payload, dict)
        if self.previewing or self.handle is not None:
            raise MonarchError("Wait for the active preview before using profiles.")
        store = self.profile_store
        key = str(payload.get("key", ""))
        if operation in {"load", "switch"} and self.coordinator:
            pin(self.coordinator.paths)
        if operation in {"load", "switch", "capture"}:
            assert self.inspector is not None
            inspection = await self.inspector.inspect()
            if operation == "capture":
                store.save(str(payload["name"]), Layout.capture(inspection.monitors))
            else:
                profile = store.get(key)
                try:
                    layout = resolve(profile, inspection.monitors, payload.get("bindings"))
                except MappingRequired as exc:
                    self.profile_mapping.emit(
                        profile, inspection.monitors, operation == "switch", str(exc)
                    )
                    return
                self.observed.emit(inspection)
                self.profile_loaded.emit(layout, operation == "switch")
                return
        elif operation in {"save", "update"}:
            layout = payload["layout"]
            if not isinstance(layout, Layout):
                raise MonarchError("No valid edited layout is available.")
            # Saving a draft does not require the displays to stay connected, but
            # the data must be structurally valid and never silently changed.
            store.save(
                str(payload.get("name", "")) if operation == "save" else store.get(key).name,
                layout,
                identifier=key if operation == "update" else None,
            )
        elif operation == "rename":
            profile = store.get(key)
            store.rename(profile.id, str(payload["name"]))
        elif operation == "delete":
            store.delete(key)
        elif operation == "import":
            store.import_file(Path(str(payload["path"])))
        elif operation == "export":
            store.export_file(Path(str(payload["path"])), key)
        elif operation != "list":
            raise MonarchError("Unknown profile operation.")
        self.profiles.emit(store.list())
        if operation != "list":
            self.profile_notice.emit(
                "Profile operation completed. Saving profiles does not apply settings."
            )

    def _automation_action(self, operation: str, *args: object) -> None:
        store = PolicyStore(self.profile_store.directory)
        autostart = Autostart(config_home(self.env))
        if operation == "automation-settings":
            settings_policy = store.read()
            try:
                registered_login = autostart.active()
            except (MonarchError, OSError) as exc:
                self.automation_settings.emit(settings_policy, False)
                self.automation_failed.emit(str(exc))
            else:
                self.automation_settings.emit(settings_policy, registered_login)
        elif operation == "automation-save":
            policy, login = args
            assert isinstance(policy, Policy) and isinstance(login, bool)
            # Validate both actions before treating the editor as saved. Policy
            # disable/revision invalidation also revokes a running auto guard.
            Policy.parse(policy.to_dict())
            if not policy.enabled:
                store.write(policy)
            autostart.set(login, profiles_directory=self.profile_store.directory)
            if policy.enabled:
                store.write(policy)
            self.automation_saved.emit()
        else:
            assert self.coordinator is not None
            pin(self.coordinator.paths, operation == "automation-pin")

    async def _automatic_loop(self) -> None:
        assert self.automation is not None and self.inspector is not None
        previous_wall = time.time()
        while True:
            try:
                wall = time.time()
                if abs(wall - previous_wall) > 5:
                    self.automation.stable_key = ""
                previous_wall = wall
                if not self.previewing and self.handle is None:
                    enabled = self.automation.store.read().enabled
                    inspection = (
                        (await self.inspector.inspect())
                        if enabled or self.latest_inspection is None
                        else self.latest_inspection
                    )
                    if inspection != self.latest_inspection:
                        self.latest_inspection = inspection
                        self.observed.emit(inspection)
                    status, offer = self.automation.evaluate(
                        inspection, idle=self.ui_idle, ready=self.management_ready
                    )
                    self.automation_state.emit(status)
                    if offer is not None and offer.layout is not None:
                        self.observed.emit(inspection)
                        self.automation_offer.emit(offer.layout, self.automation.authorize())
                elif self.automation.owner is not None:
                    self.automation_state.emit(
                        self.automation.status(
                            "Automatic preview pending confirmation."
                            if self.automatic_preview
                            else "Waiting for the active manual transaction.",
                            now=time.monotonic(),
                        )
                    )
            except (MonarchError, OSError, ValueError) as exc:
                self.automation.stable_key = ""
                self.automation_state.emit({"reason": str(exc), "pinned": False})
            await asyncio.sleep(1)

    async def _automatic_preview(self, *args: object) -> None:
        assert self.automation is not None
        self.automatic_preview = True
        try:
            authorization = args[1]
            if not isinstance(authorization, dict) or authorization != self.automation.authorize():
                raise MonarchError(
                    "Automatic selection changed before preview; waiting for fresh policy."
                )
            self.auto_authorization = authorization
            await self._preview(args[0])
        except (MonarchError, OSError, ValueError):
            self.automation.finish({"state": "failed"})
            raise
        finally:
            self.auto_authorization = None
            self.automatic_preview = False

    def shutdown(self) -> None:
        self.closing = True
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._stop.set)
