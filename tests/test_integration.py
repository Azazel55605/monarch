from dataclasses import replace

import pytest

from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.errors import MonarchError
from monarch.storage.files import read_private
from monarch.storage.integration import BLOCK, IntegrationPlan
from monarch.storage.managed import Managed


@pytest.fixture
def desktop(tmp_path, monitors):
    root = tmp_path / "hyprland.lua"
    root.write_text("-- Example desktop\nhl.config({general={gaps_in=4}})\n")
    root.chmod(0o644)
    dependency = tmp_path / "bindings.lua"
    dependency.write_text("-- Example bindings\n")
    dependency.chmod(0o644)
    monitors[0]["scale"] = 1
    layout = Layout.capture(parse_monitors(monitors))
    return root, dependency, layout


def test_reviewed_include_preserves_unrelated_bytes_permissions_and_backup(desktop):
    root, dependency, layout = desktop
    original = root.read_bytes()
    plan = IntegrationPlan.prepare(root, (dependency,))
    assert root.read_bytes() == original
    assert '+require("monarch.monarch_monitors")' in plan.diff()
    directory = plan.install(layout)
    store = Managed(directory)
    assert store.root == root
    assert store.read()[0] == layout
    assert root.read_bytes() == original + BLOCK
    assert root.stat().st_mode & 0o777 == 0o644
    assert read_private(directory / "root-before-integration.lua") == original


def test_dependency_conflict_blocks_guarded_reads_and_requires_review(desktop):
    root, dependency, layout = desktop
    store = Managed(IntegrationPlan.prepare(root, (dependency,)).install(layout))
    dependency.write_text("-- reviewed change needed\n")
    with pytest.raises(MonarchError, match="dependency"):
        store.read()
    plan = IntegrationPlan.prepare(root, (dependency,))
    assert plan.diff() == ""
    plan.install(layout)
    assert store.read()[0] == layout
    assert list(store.directory.glob("root-reviewed-*.lua"))


def test_root_conflict_between_preview_and_install_is_preserved(desktop):
    root, dependency, layout = desktop
    plan = IntegrationPlan.prepare(root, (dependency,))
    root.write_bytes(root.read_bytes() + b"-- external edit\n")
    with pytest.raises(MonarchError, match="changed after preview"):
        plan.install(layout)
    assert root.read_bytes().endswith(b"-- external edit\n")
    assert not (root.parent / "monarch").exists()


def test_review_changed_root_preserves_single_include(desktop):
    root, dependency, layout = desktop
    directory = IntegrationPlan.prepare(root, (dependency,)).install(layout)
    root.write_bytes(b"-- new settings\n" + root.read_bytes())
    with pytest.raises(MonarchError, match="root changed"):
        Managed(directory).read()
    plan = IntegrationPlan.prepare(root, (dependency,))
    plan.install(layout)
    assert Managed(directory).read()[0] == layout
    assert root.read_bytes().count(BLOCK) == 1


def test_no_implicit_adoption_or_symlink_sources(desktop, tmp_path):
    root, dependency, layout = desktop
    link = tmp_path / "linked.lua"
    link.symlink_to(dependency)
    with pytest.raises(MonarchError, match="Symlink"):
        IntegrationPlan.prepare(root, (link,))
    (root.parent / "monarch").mkdir()
    with pytest.raises(MonarchError, match="unregistered"):
        IntegrationPlan.prepare(root)


def test_review_preserves_a_concurrent_monitor_file_change(desktop):
    from monarch.storage.files import atomic_write, digest
    from monarch.storage.managed import render

    root, dependency, layout = desktop
    store = Managed(IntegrationPlan.prepare(root, (dependency,)).install(layout))
    plan = IntegrationPlan.prepare(root, (dependency,))
    changed = Layout((replace(layout.outputs[0], scale=2), layout.outputs[1]))
    atomic_write(store.monitors, render(changed), expected=digest(read_private(store.monitors)))
    with pytest.raises(MonarchError, match="changed after preview"):
        plan.install(layout)
    assert store.read()[0] == changed
