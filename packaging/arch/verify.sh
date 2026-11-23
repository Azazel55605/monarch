#!/bin/bash
# Runs only inside the disposable Arch container. /input is read-only; /output holds artifacts.
set -euo pipefail
install -d -o builder -g builder /build
cp /input/PKGBUILD /input/monarch_displays-*.tar.gz /input/source-manifest.json /build/
chown -R builder:builder /build
cd /build
runuser -u builder -- makepkg --cleanbuild --force --noconfirm
runuser -u builder -- makepkg --printsrcinfo > /build/.SRCINFO
mapfile -t packages < <(find /build -maxdepth 1 -name '*.pkg.tar.zst')
[[ ${#packages[@]} == 1 ]]
package=${packages[0]}
namcap "$package" > /build/namcap.txt 2>&1
if grep -q " E: " /build/namcap.txt; then
    cat /build/namcap.txt
    exit 1
fi
pacman -U --noconfirm "$package"
# All execution below uses the installed package from /usr, outside the build tree.
cd /tmp
monarch --version
monarch help > /build/installed-help.txt
monarch help --notices > /build/installed-notices.txt
XDG_CONFIG_HOME=/tmp/monarch-clean-config XDG_STATE_HOME=/tmp/monarch-clean-state monarch diagnose > /build/installed-diagnostics.json
[[ ! -e /tmp/monarch-clean-config && ! -e /tmp/monarch-clean-state ]]
desktop-file-validate /usr/share/applications/org.monarch.Monarch.desktop
python - <<'PY'
from pathlib import Path
from PySide6.QtWidgets import QApplication
from monarch.resources import APP_ID, icon_path
from monarch.ui.app import configure_app
from monarch.ui.help import HelpDialog
from monarch.ui.window import MainWindow
app = QApplication([])
configure_app(app)
assert app.desktopFileName() == APP_ID
assert not app.windowIcon().pixmap(48, 48).isNull()
assert Path(icon_path()).is_file()
window = MainWindow(tray_enabled=False)
window.show()
app.processEvents()
for notices in (False, True):
    dialog = HelpDialog(notices=notices, parent=window)
    assert len(dialog.document.toPlainText()) > 500
    dialog.close()
window.close()
# Simulated user data must survive removing application files.
state = Path('/tmp/monarch-removal-user-data')
state.mkdir(mode=0o700)
(state / 'profiles.json').write_text('preserve profiles')
(state / 'monarch_monitors.lua').write_text('-- preserve config')
PY
pacman -Ql monarch-displays > /build/installed-files.txt
pacman -R --noconfirm monarch-displays
hash -r
! command -v monarch
[[ ! -e /usr/share/applications/org.monarch.Monarch.desktop ]]
[[ ! -e /usr/share/icons/hicolor/scalable/apps/org.monarch.Monarch.svg ]]
[[ $(cat /tmp/monarch-removal-user-data/profiles.json) == 'preserve profiles' ]]
[[ $(cat /tmp/monarch-removal-user-data/monarch_monitors.lua) == '-- preserve config' ]]
python - <<'PY'
from importlib.util import find_spec
assert find_spec('monarch') is None
PY
cp "$package" /build/PKGBUILD /build/source-manifest.json /build/namcap.txt /build/installed-files.txt /output/
cp /build/.SRCINFO /output/SRCINFO
printf '%s\n' 'Clean Arch package build/check/install/help/icon/diagnostics/uninstall passed.' > /output/arch-install-check.txt

chown -R "${OUT_UID:-1000}:${OUT_GID:-1000}" /output
