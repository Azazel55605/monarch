import json
from dataclasses import replace
from pathlib import Path

from monarch.backends.hyprland.drm import disabled_links, read_connector_states
from monarch.domain.monitors import parse_monitors


def test_connector_readback_requires_unique_connected_output_and_awake_display(tmp_path):
    raw = json.loads((Path(__file__).parent / "fixtures/monitors.json").read_text())
    raw[0]["dpmsStatus"] = True
    live = parse_monitors(raw)
    name = live[0].name
    connector = tmp_path / f"card1-{name}"
    connector.mkdir()
    (connector / "status").write_text("connected\n")
    (connector / "enabled").write_text("disabled\n")
    observed = read_connector_states(live, tmp_path)
    assert disabled_links(observed) == (name,)
    assert not disabled_links((replace(observed[0], dpms_on=False),))
    (connector / "enabled").write_text("enabled\n")
    assert not disabled_links(read_connector_states(live, tmp_path))
    (connector / "enabled").write_text("disabled\n")
    (tmp_path / f"card2-{name}").mkdir()
    assert not disabled_links(read_connector_states(live, tmp_path))
