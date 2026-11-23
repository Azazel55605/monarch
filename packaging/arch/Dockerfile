# Official Arch base pulled and recorded for this testing candidate.
FROM archlinux@sha256:d4594bb2300cba11f41c2f27923eb56f63d9988909c402f9c95517d1e362c899
RUN pacman -Syu --noconfirm --needed \
    base-devel python-build python-installer python-hatchling python-pytest python-pytest-qt \
    pyside6 qt6-svg hicolor-icon-theme hyprland desktop-file-utils namcap ttf-dejavu \
    && pacman -Scc --noconfirm \
    && useradd --create-home --uid 1000 builder
RUN printf '%s\n' 'PACKAGER="Monarch contributors <monarch@example.invalid>"' >> /etc/makepkg.conf
ENV QT_QPA_PLATFORM=offscreen PYTEST_QT_API=pyside6
COPY verify.sh /usr/local/bin/monarch-package-check
CMD ["bash", "/usr/local/bin/monarch-package-check"]
