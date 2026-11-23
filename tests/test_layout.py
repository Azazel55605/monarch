import copy
from dataclasses import replace

import pytest

from monarch.domain.layout import Layout, lua_string, ordered, rule
from monarch.domain.monitors import parse_monitors
from monarch.errors import MonarchError


def test_capture_validate_and_precision(monitors):
    monitors[0]["scale"] = 1
    live = parse_monitors(monitors)
    layout = Layout.capture(live)
    layout.validate(live)
    assert layout.matches(live)
    assert layout.outputs[0].size == (2560, 1440)
    assert layout.outputs[0].mode == "2560x1440@143.97"
    assert Layout.parse(layout.to_dict()) == layout


@pytest.fixture
def layout_data(monitors):
    # The fixture's 1.5 scale produces fractional width. Phase 2 rejects
    # that for writes even though the read-only inspector can describe it.
    monitors[0]["scale"] = 1
    return Layout.capture(parse_monitors(monitors)).to_dict()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scale", 0),
        ("scale", float("nan")),
        ("scale", float("inf")),
        ("scale", True),
        ("scale", 1.5),
        ("scale", 10**400),
        ("transform", 8),
        ("transform", False),
        ("x", 2**31),
        ("y", "0"),
        ("enabled", 1),
        ("mode", "modeline;os.execute()"),
        ("mode", "preferred"),
        ("mode", "0x0@60"),
        ("name", ""),
        ("serial", "bad\x00value"),
    ],
)
def test_invalid_settings_rejected(layout_data, field, value):
    layout_data["outputs"][0][field] = value
    with pytest.raises(MonarchError):
        Layout.parse(layout_data)


def test_disabled_preferred_and_no_usable_output(layout_data):
    layout_data["outputs"][0].update(enabled=False, mode="preferred")
    with pytest.raises(MonarchError, match="usable"):
        Layout.parse(layout_data)


def test_duplicate_identity_and_unadvertised_modes(layout_data, monitors):
    live = parse_monitors(monitors)
    duplicate = copy.deepcopy(layout_data)
    duplicate["outputs"].append(duplicate["outputs"][0])
    with pytest.raises(MonarchError, match="Duplicate"):
        Layout.parse(duplicate)
    layout_data["outputs"][0]["serial"] = "different"
    with pytest.raises(MonarchError, match="identity"):
        Layout.parse(layout_data).validate(live)
    layout_data["outputs"][0]["serial"] = monitors[0]["serial"]
    layout_data["outputs"][0]["mode"] = "1920x1080@60"
    with pytest.raises(MonarchError, match="advertised"):
        Layout.parse(layout_data).validate(live)


def test_mirror_validation_and_order(layout_data):
    a, b = layout_data["outputs"]
    a["mirror"] = b["name"]
    with pytest.raises(MonarchError, match="Mirror|usable"):
        Layout.parse(layout_data)
    b["enabled"] = True
    b["transform"] = 0
    layout = Layout.parse(layout_data)
    assert ordered(layout)[0].name == b["name"]
    b["mirror"] = a["name"]
    with pytest.raises(MonarchError, match="Mirror|usable"):
        Layout.parse(layout_data)


def test_rotation_negative_coordinates_and_lua_escape(layout_data):
    layout_data["outputs"][0].update(mode="1920x1080@60", scale=1.25, transform=1, x=-864)
    output = Layout.parse(layout_data).outputs[0]
    assert output.size == (864, 1536)
    malicious = 'DP-"\\\n雪;os.execute("oops")'
    encoded = lua_string(malicious)
    assert "\\u" not in encoded
    assert "\\010" in encoded and "\\034" in encoded and "\\092" in encoded
    assert "\n" not in encoded
    assert "雪" not in encoded
    generated = rule(replace(output, name=malicious))
    assert "output=" + encoded in generated


def test_serializer_revalidates_programmatic_scalar_injection(layout_data):
    output = Layout.parse(layout_data).outputs[0]
    with pytest.raises(MonarchError):
        rule(replace(output, transform='0});os.execute("injected")'))
