# Third-party notices

Monarch source code, documentation and the original Monarch SVG icon are licensed
under the MIT license in `LICENSE`. No third-party icon set is included.

Monarch uses separately supplied dependencies:

| Component | Role | Upstream licensing information |
| --- | --- | --- |
| Python | Runtime | Python Software Foundation License; https://docs.python.org/3/license.html |
| PySide6 / Shiboken6 | Qt bindings | LGPL-3.0-only / GPL-3.0-only / commercial options and applicable exceptions; https://doc.qt.io/qtforpython-6/licenses.html |
| Qt 6 | GUI libraries/plugins | Module-specific LGPL/GPL/commercial terms and third-party notices; https://doc.qt.io/qt-6/licensing.html |
| Hyprland | External compositor/IPC | BSD-3-Clause; https://github.com/hyprwm/Hyprland/blob/main/LICENSE |

The Monarch wheel and source archive contain Monarch code/assets, not copies of
Python, Qt, PySide6 or Hyprland. The Arch package depends on distro packages instead
of vendoring their libraries. Those distributions supply their own license texts
and notices (including `/usr/share/licenses/` on Arch). Installing the Python GUI
extra obtains separately distributed PySide/Qt wheels with their own notices.
Monarch's MIT license does not replace dependency licenses.

Redistributors who bundle additional libraries must retain their applicable
notices/source obligations and review the selected modules' terms. Monarch's
source and build recipe are available at https://github.com/Azazel55605/monarch.
There are no proprietary fonts, downloaded themes, embedded ICC profiles, or
redistributed monitor EDID data in the application artifacts.
