"""Typed mutation primitives, used only by the locked recovery guard."""

from monarch.backends.hyprland.commands import Hyprctl
from monarch.domain.layout import Output, rule
from monarch.domain.monitors import Monitor, parse_monitors
from monarch.errors import MonarchError


class Writer(Hyprctl):
    full_reset: bool = False

    async def observe(self) -> tuple[Monitor, ...]:
        return parse_monitors(await self.read("monitors", "all"))

    async def set_output(self, output: Output) -> None:
        response = await self._request(("eval", rule(output)))
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
