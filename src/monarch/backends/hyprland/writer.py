"""Typed mutation primitives, used only by the locked recovery guard."""

from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.drm import read_connector_states
from monarch.domain.layout import Output, rule
from monarch.domain.monitors import Monitor, parse_monitors
from monarch.errors import MonarchError


class Writer(Hyprctl):
    full_reset: bool = False
    native_drm: bool = False
    # 0.57.2 ignores VRR in monitor-rule comparison. The guard must adopt the
    # new policy via an observed soft-property refresh before triggering VRR.
    vrr_refresh_required: bool = True

    async def observe(self) -> tuple[Monitor, ...]:
        monitors = parse_monitors(await self.read("monitors", "all"))
        return read_connector_states(monitors) if self.native_drm else monitors

    async def set_output(self, output: Output) -> None:
        await self._set_rule(rule(output))

    async def set_hdr(self, output: Output, enabled: bool) -> None:
        await self._set_rule(rule(output, hdr=enabled))

    async def _set_rule(self, command: str) -> None:
        response = await self._request(("eval", command))
        if response.strip() != b"ok":
            raise MonarchError("Hyprland rejected a monitor update.")
        await self.check_errors()

    async def reload(self) -> None:
        response = await self._request(("reload", "full-reset") if self.full_reset else ("reload",))
        if response.strip() != b"ok":
            raise MonarchError("Hyprland rejected the configuration reload.")
        await self.check_errors()

    async def check_errors(self) -> None:
        if (await self._request(("configerrors",))).strip():
            raise MonarchError("Hyprland reported configuration errors.")
