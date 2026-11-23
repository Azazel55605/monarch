from decimal import Decimal

import pytest

from monarch.domain.monitors import Mode, parse_monitors
from monarch.errors import MonarchError


def test_inactive_identity_precision_geometry_and_duplicates(monitors):
    first, second = parse_monitors(monitors)
    assert first.refresh_hz == Decimal("143.970001")
    assert first.modes[0].refresh_hz == Decimal("143.97")
    assert len(first.modes) == 2
    assert first.x == -1707
    assert first.logical_size == (2560 / 1.5, 960)
    assert second.disabled is True
    assert second.logical_size == (1080, 1920)
    assert second.serial == ""
    assert first.mirror_of is None


@pytest.mark.parametrize("value", [None, {}, [None], [{"name": ""}], [{"name": 3}]])
def test_invalid_topology(value):
    with pytest.raises(MonarchError):
        parse_monitors(value)


def test_duplicate_outputs(monitors):
    with pytest.raises(MonarchError, match="duplicate"):
        parse_monitors([monitors[0], monitors[0]])


@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), float("inf"), "1.5", None])
def test_unknown_scale_is_not_fabricated(monitors, value):
    monitors[0]["scale"] = value
    monitor = parse_monitors(monitors)[0]
    assert monitor.scale is None
    assert monitor.logical_size is None


def test_missing_fields_and_future_modes_are_preserved_as_unknown():
    monitor = parse_monitors([{"name": "DP-DEMO", "availableModes": ["future mode", 7]}])[0]
    assert monitor.disabled is None
    assert monitor.refresh_hz is None
    assert monitor.width is None
    assert monitor.warnings
    assert monitor.modes == ()


@pytest.mark.parametrize("value", ["0x1080@60Hz", "1920x1080@0Hz", "preferred", "1x2@nanHz"])
def test_bad_modes(value):
    with pytest.raises(ValueError):
        Mode.parse(value)


def test_extreme_numeric_fields_do_not_crash_or_fabricate_geometry(monitors):
    monitors[0].update(width=10**400, refreshRate=10**400, scale=10**400)
    monitor = parse_monitors(monitors)[0]
    assert monitor.width is None
    assert monitor.refresh_hz is None
    assert monitor.scale is None
    monitors[1]["scale"] = 1e-310
    assert parse_monitors(monitors)[1].logical_size is None
