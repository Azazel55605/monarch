import importlib.util
from pathlib import Path

import pytest

from monarch.cli import main
from monarch.resources import APP_ID, icon_path, text


def test_bundled_offline_help_and_notices_need_no_session(monkeypatch, capsys):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert main(["help"]) == 0
    assert "recovery" in capsys.readouterr().out.lower()
    assert main(["help", "--notices"]) == 0
    assert "LGPL" in capsys.readouterr().out
    assert "Advanced" in text("guide.md")
    assert Path(icon_path()).is_file()
    with pytest.raises(ValueError):
        text("../../private")


def test_desktop_identity_icon_and_offline_dialog(qapp, qtbot):
    from monarch.ui.app import configure_app
    from monarch.ui.help import HelpDialog

    configure_app(qapp)
    assert qapp.desktopFileName() == APP_ID
    assert not qapp.windowIcon().pixmap(48, 48).isNull()
    dialog = HelpDialog(notices=False)
    qtbot.addWidget(dialog)
    assert "Keep" in dialog.document.toPlainText()
    assert "0.1.0" in dialog.document.toPlainText()
    notices = HelpDialog(notices=True)
    qtbot.addWidget(notices)
    assert "MIT" in notices.document.toPlainText()


def test_arch_template_uses_actual_source_checksum_and_native_dependencies(tmp_path):
    import hashlib
    import io
    import tarfile
    import tomllib

    root = Path(__file__).parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    archive = tmp_path / f"monarch_displays-{version}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = f"Metadata-Version: 2.4\nVersion: {version}\n".encode()
        member = tarfile.TarInfo(f"monarch_displays-{version}/PKG-INFO")
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))
    spec = importlib.util.spec_from_file_location(
        "build_arch_package", root / "tools/build_arch_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "staged"
    manifest = module.prepare(archive, output)
    recipe = (output / "PKGBUILD").read_text()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() in recipe
    assert manifest["sha256"] in recipe
    assert "SKIP" not in recipe and "@VERSION@" not in recipe
    assert "pyside6" in recipe and "qt6-svg" in recipe and "python-hatchling" in recipe
    assert "--no-isolation" in recipe and "--destdir" in recipe
    assert not (output / "src").exists()  # Preparing a recipe executes no build backend.
