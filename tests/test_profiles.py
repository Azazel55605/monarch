import json
from dataclasses import replace
from pathlib import Path

import pytest

from monarch.cli import main
from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.domain.profiles import Profile, resolve
from monarch.errors import MonarchError
from monarch.services.profiles import parse_bindings
from monarch.storage.files import atomic_write, read_private
from monarch.storage.profiles import ProfileStore, config_home


@pytest.fixture
def setup(monitors, tmp_path):
    monitors[0]["scale"] = 1
    live = parse_monitors(monitors)
    return ProfileStore(tmp_path / "profiles"), Layout.capture(live), live


def test_three_profiles_crud_and_duplicate_conflict(setup):
    store, layout, _ = setup
    profiles = [
        store.save(name, Layout(tuple(replace(o, x=o.x + x) for o in layout.outputs)))
        for name, x in [("Desk", 0), ("Presentation", 100), ("Portrait", -100)]
    ]
    assert len(store.list()) == 3
    store.rename(profiles[0].id, "Office")
    assert store.get("office").layout == layout
    with pytest.raises(MonarchError, match="Duplicate"):
        store.save("OFFICE", layout)
    assert len(store.list()) == 3
    updated = store.save("Office", profiles[1].layout, identifier=profiles[0].id)
    assert store.get(updated.id).layout == profiles[1].layout
    store.delete(updated.id)
    assert len(store.list()) == 2
    with pytest.raises(MonarchError, match="no longer"):
        store.rename(updated.id, "gone")
    assert (store.path.stat().st_mode & 0o777) == 0o600


def test_portable_import_export_no_clobber_and_private_permissions(setup, tmp_path):
    store, layout, _ = setup
    saved = store.save("Desk", layout)
    exported = tmp_path / "public-parent" / "profiles.json"
    exported.parent.mkdir(mode=0o755)
    store.export_file(exported)
    assert exported.stat().st_mode & 0o777 == 0o600
    other = ProfileStore(tmp_path / "other")
    imported = other.import_file(exported)
    assert imported[0].id != saved.id
    assert imported[0].layout == layout
    before = read_private(other.path)
    with pytest.raises(MonarchError, match="already exists"):
        other.import_file(exported)
    assert read_private(other.path) == before
    with pytest.raises(MonarchError, match="target exists"):
        store.export_file(exported)
    assert json.loads(exported.read_text())["schema_version"] == 2


def test_migration_future_malformed_and_failed_update_preserve_source(setup):
    store, layout, _ = setup
    legacy = {"schema_version": 1, "profiles": [{"name": "Legacy", "layout": layout.to_dict()}]}
    atomic_write(store.path, json.dumps(legacy).encode())
    profile = store.list()[0]
    assert profile == store.list()[0]  # Stable deterministic migrated ID.
    assert json.loads(read_private(store.path))["schema_version"] == 1  # Reads are read-only.
    original = read_private(store.path)
    store.rename(profile.id, "Migrated")
    assert next(store.directory.glob("schema-1-backup-*.json")).read_bytes() == original
    assert json.loads(read_private(store.path))["schema_version"] == 2
    for invalid in [
        {"schema_version": 99, "profiles": []},
        {"schema_version": True, "profiles": []},
        {"schema_version": 2, "profiles": [{"name": "bad"}]},
        {"schema_version": 2, "profiles": [], "lua": "do not execute"},
    ]:
        data = json.dumps(invalid).encode()
        atomic_write(store.path, data)
        with pytest.raises(MonarchError):
            store.save("Desk", layout)
        assert read_private(store.path) == data


def test_lock_symlink_and_missing_update_refuse(setup, tmp_path):
    store, layout, _ = setup
    saved = store.save("Desk", layout)
    with store.locked():
        with pytest.raises(MonarchError, match="Another client"):
            ProfileStore(store.directory).delete(saved.id)
    with pytest.raises(MonarchError, match="deleted"):
        store.save("Gone", layout, identifier="a" * 32)
    store.path.unlink()
    store.path.symlink_to(tmp_path / "outside")
    with pytest.raises(MonarchError, match="Symlinks"):
        store.list()


@pytest.mark.parametrize("name", ["", "  ", "x" * 81, "bad\nname", "bad\x1bname"])
def test_profile_name_limits(setup, name):
    store, layout, _ = setup
    with pytest.raises(MonarchError):
        store.save(name, layout)


def test_unique_serial_connector_rename_remaps_mirror_and_layout(setup):
    _, layout, live = setup
    # A distinct serial identity must move together with its mirror references.
    layout = Layout(
        tuple(
            replace(o, enabled=True, mirror=layout.outputs[0].name if i else "")
            for i, o in enumerate(layout.outputs)
        )
    )
    layout = Layout(tuple(replace(o, serial=f"SERIAL-{i}") for i, o in enumerate(layout.outputs)))
    renamed = tuple(replace(m, name=f"NEW-{i}", serial=f"SERIAL-{i}") for i, m in enumerate(live))
    resolved = resolve(Profile("a" * 32, "Desk", layout), renamed)
    assert [o.name for o in resolved.outputs] == [m.name for m in renamed]
    assert resolved.outputs[1].mirror == renamed[0].name


def test_missing_extra_and_changed_modes_are_blocked(setup):
    _, layout, live = setup
    profile = Profile("a" * 32, "Desk", layout)
    for connected in [live[:-1], live + (replace(live[0], name="EXTRA"),)]:
        with pytest.raises(MonarchError, match="exact display set"):
            resolve(profile, connected)
    with pytest.raises(MonarchError, match="advertised"):
        resolve(profile, (replace(live[0], modes=()), live[1]))


def test_absent_serial_connector_stability_and_explicit_mapping(setup):
    _, layout, live = setup
    layout = Layout(tuple(replace(o, serial="") for o in layout.outputs))
    live = tuple(replace(m, serial="") for m in live)
    profile = Profile("a" * 32, "Desk", layout)
    assert resolve(profile, live) == layout
    renamed = tuple(replace(m, name="NEW-" + m.name) for m in live)
    with pytest.raises(MonarchError, match="without a serial"):
        resolve(profile, renamed)
    bindings = {o.name: m.name for o, m in zip(layout.outputs, renamed, strict=True)}
    assert resolve(profile, renamed, bindings).outputs[0].name.startswith("NEW-")


@pytest.mark.parametrize("serial", ["", "duplicate", "0", "unknown"])
def test_identical_display_ambiguity_never_uses_connector_as_identity(setup, serial):
    _, layout, live = setup
    layout = Layout(
        tuple(replace(o, make="Same", model="Twins", serial=serial) for o in layout.outputs)
    )
    live = tuple(replace(m, make="Same", model="Twins", serial=serial) for m in live)
    profile = Profile("a" * 32, "Twins", layout)
    with pytest.raises(MonarchError, match="ambiguous"):
        resolve(profile, live)
    bindings = {o.name: m.name for o, m in zip(layout.outputs, live, strict=True)}
    assert resolve(profile, live, bindings) == layout
    with pytest.raises(MonarchError, match="one-to-one"):
        resolve(profile, live, {o.name: live[0].name for o in layout.outputs})


def test_explicit_mapping_cannot_override_identity_or_unknown_outputs(setup):
    _, layout, live = setup
    profile = Profile("a" * 32, "Desk", layout)
    with pytest.raises(MonarchError):
        resolve(profile, live, {layout.outputs[0].name: live[1].name})
    with pytest.raises(MonarchError, match="unknown"):
        resolve(profile, live, {"OTHER": live[0].name})
    with pytest.raises(MonarchError):
        parse_bindings(["DP=X", "DP=Y"])
    assert parse_bindings(["DP=X"]) == {"DP": "X"}


def test_cli_offline_crud_and_invalid_import(setup, capsys, tmp_path, monkeypatch):
    store, layout, _ = setup
    store.save("Desk", layout)
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    prefix = ["profile", "--store", str(store.directory)]
    assert main(prefix + ["list"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "Desk"
    assert main(prefix + ["rename", "Desk", "Office"]) == 0
    assert main(prefix + ["export", str(tmp_path / "export.json")]) == 0
    assert main(prefix + ["delete", "Office"]) == 0
    assert main(prefix + ["import", str(tmp_path / "export.json")]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version":999,"profiles":[]}')
    assert main(prefix + ["import", str(bad)]) == 2
    assert len(store.list()) == 1
    assert config_home({"HOME": "/tmp/example"}) == Path("/tmp/example/.config/monarch")


def test_external_catalog_edit_is_preserved_before_replace(setup):
    store, layout, _ = setup
    store.save("Desk", layout)
    with store.locked() as expected:
        # An editor outside the cooperative lock changes valid data after review.
        profiles = store.list()
        changed = json.loads(read_private(store.path))
        changed["profiles"][0]["name"] = "External edit"
        external = json.dumps(changed).encode()
        atomic_write(store.path, external)
        with pytest.raises(MonarchError, match="changed externally"):
            store._write(profiles, expected=expected)
        assert read_private(store.path) == external
