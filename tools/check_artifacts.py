#!/usr/bin/env python3
"""Verify application wheel assets and source packaging, and write SHA-256 checksums."""

import hashlib
import tarfile
import zipfile
from pathlib import Path


def check(directory: Path) -> None:
    wheels = list(directory.glob("*.whl"))
    sources = list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError(
            "Use a clean artifact directory with exactly one wheel and source archive."
        )
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        for suffix in (
            "monarch/resources/guide.md",
            "monarch/resources/notices.md",
            "monarch/resources/monarch.svg",
            "share/applications/org.monarch.Monarch.desktop",
            "share/icons/hicolor/scalable/apps/org.monarch.Monarch.svg",
            "share/licenses/monarch-displays/LICENSE",
            "share/doc/monarch-displays/CHANGELOG.md",
        ):
            if not any(name.endswith(suffix) for name in names):
                raise ValueError(f"Wheel is missing {suffix}")
        if any("/tests/" in name or name.endswith("PKGBUILD") for name in names):
            raise ValueError("Build/test files must not be application modules.")
    with tarfile.open(sources[0]) as source:
        names = source.getnames()
        for suffix in (
            "pyproject.toml",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "CHANGELOG.md",
            "packaging/arch/PKGBUILD.in",
            "packaging/org.monarch.Monarch.desktop",
        ):
            if not any(name.endswith("/" + suffix) for name in names):
                raise ValueError(f"Source is missing {suffix}")
    paths = sorted(
        p
        for p in directory.rglob("*")
        if p.is_file() and not p.name.startswith(".") and p.name != "SHA256SUMS"
    )
    (directory / "SHA256SUMS").write_text(
        "".join(
            hashlib.sha256(path.read_bytes()).hexdigest()
            + "  "
            + path.relative_to(directory).as_posix()
            + "\n"
            for path in paths
        )
    )
    print(f"Verified {len(paths)} artifact files and wrote SHA256SUMS")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    check(parser.parse_args().directory)
