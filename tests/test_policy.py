from dataclasses import replace

import pytest

from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.domain.policy import Policy, Rule, choose, topology
from monarch.domain.profiles import Profile
from monarch.errors import MonarchError


def test_policy_loads_older_files_with_scale_defaults_and_round_trips_custom_values():
    legacy = {"schema_version": 1, "enabled": True, "rules": [], "new_displays": True}
    assert Policy.parse(legacy) == Policy(enabled=True, new_displays=True)
    custom = Policy.parse(dict(legacy, scale_1440p=1.25, scale_4k=2))
    assert custom.scale_1440p == 1.25
    assert custom.scale_4k == 2
    assert Policy.parse(custom.to_dict()) == custom
    with pytest.raises(MonarchError, match="scale preferences"):
        Policy.parse(dict(legacy, scale_4k=float("nan")))


@pytest.fixture
def data(monitors):
    monitors[0]["scale"] = 1
    live = parse_monitors(monitors)
    profile = Profile("a" * 32, "Desk", Layout.capture(live))
    other = Profile(
        "b" * 32,
        "Presentation",
        Layout(tuple(replace(o, x=o.x - 100) for o in profile.layout.outputs)),
    )
    return live, profile, other


def test_default_no_match_tie_and_priority_preserve_or_choose_deterministically(data):
    live, desk, talk = data
    assert choose(Policy(), (desk,), live).layout is None
    assert choose(Policy(True), (desk,), live).layout is None
    tied = Policy(True, (Rule(desk.id), Rule(talk.id)))
    assert "tie" in choose(tied, (talk, desk), live).reason
    ranked = replace(tied, rules=(Rule(desk.id, priority=1), Rule(talk.id)))
    assert choose(ranked, (talk, desk), live).profile == desk
    assert choose(ranked, (desk, talk), live).profile == desk


def test_subset_preserves_unknown_extras_exactness_specificity_and_no_implicit_disable(data):
    live, desk, _ = data
    subset = Profile("c" * 32, "Single", Layout((replace(desk.layout.outputs[0], scale=2),)))
    rules = Policy(True, (Rule(subset.id, "subset", 2), Rule(desk.id, "exact", 1)))
    selected = choose(rules, (desk, subset), live)
    assert selected.profile == subset
    assert selected.layout.outputs[1] == desk.layout.outputs[1]
    # Same priority: exact wins; with both subset, more required outputs wins.
    for exactness in ("exact", "subset"):
        rules = Policy(True, (Rule(subset.id, "subset"), Rule(desk.id, exactness)))
        assert choose(rules, (subset, desk), live).profile == desk


@pytest.mark.parametrize("serial", ["", "duplicate", "unknown"])
def test_identical_displays_never_auto_bind_even_with_same_connector(data, serial):
    live, desk, _ = data
    live = tuple(replace(m, make="Twins", model="Twins", serial=serial) for m in live)
    desk = replace(
        desk,
        layout=Layout(
            tuple(
                replace(o, make="Twins", model="Twins", serial=serial) for o in desk.layout.outputs
            )
        ),
    )
    selection = choose(Policy(True, (Rule(desk.id),)), (desk,), live)
    assert selection.layout is None
    assert "ambiguous" in selection.rejected[0]


def test_missing_extra_and_connector_rename_are_authoritatively_checked(data):
    live, desk, _ = data
    policy = Policy(True, (Rule(desk.id),))
    assert choose(policy, (desk,), live[:-1]).layout is None
    assert choose(policy, (), live).layout is None
    desk = replace(
        desk,
        layout=Layout(
            tuple(replace(o, serial=f"SERIAL-{i}") for i, o in enumerate(desk.layout.outputs))
        ),
    )
    renamed = tuple(replace(m, name=f"NEW-{i}", serial=f"SERIAL-{i}") for i, m in enumerate(live))
    result = choose(policy, (desk,), renamed)
    assert result.layout.outputs[0].name == "NEW-0"
    assert choose(policy, (desk,), (replace(renamed[0], modes=()), renamed[1])).layout is None


def test_topology_ignores_self_generated_settings_but_not_identity_or_capabilities(data):
    live, _, _ = data
    changed = tuple(replace(m, scale=2, x=-100, disabled=not m.disabled) for m in live)
    assert topology(live) == topology(changed)
    assert topology(live) != topology((replace(live[0], serial="changed"), live[1]))
    assert topology(live) != topology((replace(live[0], modes=()), live[1]))


@pytest.mark.parametrize(
    "value",
    [
        {"schema_version": 2, "enabled": True, "rules": []},
        {"schema_version": True, "enabled": True, "rules": []},
        {"schema_version": 1, "enabled": 1, "rules": []},
        {
            "schema_version": 1,
            "enabled": True,
            "rules": [{"profile": "a" * 32, "mode": "wild", "priority": 0}],
        },
        {"schema_version": 1, "enabled": True, "rules": [Rule("a" * 32, priority=1001).to_dict()]},
        {"schema_version": 1, "enabled": True, "rules": [Rule("a" * 32).to_dict()] * 2},
    ],
)
def test_invalid_future_and_duplicate_rules_rejected(value):
    with pytest.raises(MonarchError):
        Policy.parse(value)


def test_explicit_saved_port_binding_is_opt_in_and_cannot_override_known_serial(data):
    live, desk, _ = data
    twins = tuple(replace(m, make="Twins", model="Twins", serial="") for m in live)
    desk = replace(
        desk,
        layout=Layout(
            tuple(replace(o, make="Twins", model="Twins", serial="") for o in desk.layout.outputs)
        ),
    )
    assert choose(Policy(True, (Rule(desk.id),)), (desk,), twins).layout is None
    assert choose(Policy(True, (Rule(desk.id, connectors=True),)), (desk,), twins).profile == desk
    changed_port = (replace(twins[0], name="NEW-PORT"), twins[1])
    assert (
        choose(Policy(True, (Rule(desk.id, connectors=True),)), (desk,), changed_port).layout
        is None
    )
    with_serial = replace(
        desk, layout=Layout(tuple(replace(o, serial="EXPECTED") for o in desk.layout.outputs))
    )
    assert (
        choose(Policy(True, (Rule(desk.id, connectors=True),)), (with_serial,), twins).layout
        is None
    )
