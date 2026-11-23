import os

import pytest

from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.errors import MonarchError
from monarch.storage.files import atomic_write, digest, read_private
from monarch.storage.managed import Managed, render


@pytest.fixture
def managed(tmp_path, monitors):
    monitors[0]["scale"] = 1
    layout = Layout.capture(parse_monitors(monitors))
    store = Managed(tmp_path / "owned")
    store.create(layout)
    return store, layout


def test_owned_roundtrip_and_permissions(managed):
    store, layout = managed
    parsed, content = store.read()
    assert parsed == layout
    assert content == render(layout)
    assert store.directory.stat().st_mode & 0o777 == 0o700
    assert store.root.stat().st_mode & 0o777 == 0o600
    with pytest.raises(MonarchError, match="new directory"):
        store.create(layout)


def test_external_change_is_never_overwritten(managed):
    store, layout = managed
    original = read_private(store.monitors)
    store.monitors.write_bytes(original + b"-- external\n")
    with pytest.raises(MonarchError, match="changed externally"):
        atomic_write(store.monitors, render(layout), expected=digest(original))
    with pytest.raises(MonarchError, match="differs"):
        store.read()
    assert store.monitors.read_bytes().endswith(b"-- external\n")


def test_symlink_hardlink_and_permissive_files_rejected(managed, tmp_path):
    store, _ = managed
    external = tmp_path / "copy"
    external.write_bytes(store.monitors.read_bytes())
    external.chmod(0o600)
    store.monitors.unlink()
    store.monitors.symlink_to(external)
    with pytest.raises(MonarchError, match="Symlinks"):
        store.read()
    store.monitors.unlink()
    os.link(external, store.monitors)
    with pytest.raises(MonarchError, match="one link"):
        store.read()
    external.unlink()
    store.monitors.chmod(0o644)
    with pytest.raises(MonarchError, match="private"):
        store.read()


def test_modified_root_rejected(managed):
    store, _ = managed
    store.root.write_bytes(store.root.read_bytes() + b'os.execute("not executed")\n')
    with pytest.raises(MonarchError, match="exact"):
        store.read()


def test_exclusive_write_and_failed_replace_preserve_original(managed, monkeypatch):
    store, _ = managed
    content = read_private(store.monitors)
    with pytest.raises(MonarchError, match="existing"):
        atomic_write(store.monitors, b"no", create=True)

    def fail(*args):
        raise OSError("injected storage failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        atomic_write(store.monitors, b"candidate", expected=digest(content))
    assert read_private(store.monitors) == content
    assert not list(store.directory.glob(".monarch-*"))


def test_read_snapshot_survives_concurrent_atomic_replacement(managed, monkeypatch):
    store, _ = managed
    original = read_private(store.monitors)
    replacement = store.directory / "replacement"
    replacement.write_bytes(b"replacement")
    replacement.chmod(0o600)
    real_fstat = os.fstat
    replaced = False

    def replace_during_read(fd):
        nonlocal replaced
        if not replaced:
            replaced = True
            os.replace(replacement, store.monitors)
        return real_fstat(fd)

    monkeypatch.setattr(os, "fstat", replace_during_read)
    assert read_private(store.monitors) == original
    assert read_private(store.monitors) == b"replacement"
