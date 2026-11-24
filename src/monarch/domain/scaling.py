"""Scale choices that give a mode whole logical pixel dimensions."""

from math import gcd

from monarch.domain.monitors import Mode


def scale_fits(mode: Mode, scale: float) -> bool:
    return all(abs(n / scale - round(n / scale)) <= 0.001 for n in (mode.width, mode.height))


def valid_scales(mode: Mode) -> tuple[float, ...]:
    # Wayland fractional scales use 120ths. The numerator must divide both dimensions.
    pixels = gcd(mode.width, mode.height) * 120
    return tuple(step / 120 for step in range(30, 961) if pixels % step == 0)


def nearest_scale(choices: tuple[float, ...], preferred: float) -> float:
    return min(choices, key=lambda scale: (abs(scale - preferred), -scale))
