#!/usr/bin/env python3
"""Prepare an exact-source PKGBUILD, optionally build in a space-free temporary path."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(sdist: Path, output: Path) -> dict[str, str]:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version):
        raise ValueError("The Arch candidate requires a normal release/prerelease version.")
    expected_name = f"monarch_displays-{version}.tar.gz"
    if sdist.name != expected_name:
        raise ValueError(f"Build the matching source archive: {expected_name}")
    with tarfile.open(sdist, "r:gz") as archive:
        metadata = archive.extractfile(f"monarch_displays-{version}/PKG-INFO")
        if metadata is None or f"Version: {version}\n" not in metadata.read(1024 * 1024).decode():
            raise ValueError("Source archive metadata does not match the recipe version.")
    checksum = hashlib.sha256(sdist.read_bytes()).hexdigest()
    recipe = (
        (ROOT / "packaging/arch/PKGBUILD.in")
        .read_text()
        .replace("@VERSION@", version)
        .replace("@SHA256@", checksum)
    )
    output.mkdir(parents=True, exist_ok=True)
    target = output / expected_name
    if sdist.resolve() != target.resolve():
        shutil.copy2(sdist, target)
    (output / "PKGBUILD").write_text(recipe)
    manifest = {
        "version": version,
        "source": expected_name,
        "sha256": checksum,
        "status": "local testing candidate; not an AUR submission or signed release",
    }
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdist", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/arch")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Stage source and checksum-pinned recipe without makepkg",
    )
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    sdist = (args.sdist or ROOT / f"dist/monarch_displays-{version}.tar.gz").absolute()
    output = args.output.absolute()
    if args.prepare_only:
        prepare(sdist, output)
    else:
        if shutil.which("makepkg") is None:
            parser.error("makepkg is required; use --prepare-only for a separate Arch builder.")
        with tempfile.TemporaryDirectory(prefix="monarch-arch-") as temporary:
            stage = Path(temporary)
            prepare(sdist, stage)
            subprocess.run(
                ["makepkg", "--cleanbuild", "--force", "--noconfirm"], cwd=stage, check=True
            )
            output.mkdir(parents=True, exist_ok=True)
            for path in stage.glob("*.pkg.tar.*"):
                shutil.copy2(path, output / path.name)
            for name in ("PKGBUILD", "source-manifest.json", sdist.name):
                shutil.copy2(stage / name, output / name)
            result = subprocess.run(
                ["makepkg", "--printsrcinfo"], cwd=stage, check=True, capture_output=True, text=True
            )
            (output / ".SRCINFO").write_text(result.stdout)
    print(f"Prepared Arch candidate in {output}")


if __name__ == "__main__":
    main()
