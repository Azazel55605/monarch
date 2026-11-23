#!/usr/bin/env python3
"""Opt-in native acceptance using an extracted Arch package, without a host install.

Run with system Python and --prefix pointing to an extracted package root.
Requires the native distro dependencies and a parent Wayland compositor.
"""

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    prefix = parser.parse_args().prefix.resolve()
    site = prefix / f"usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    if not (site / "monarch/__init__.py").is_file():
        parser.error("Extracted package does not match this interpreter's Python version.")
    sys.path.insert(0, str(site))
    # The independent guard must import the same installed package, not the checkout.
    os.environ["PYTHONPATH"] = str(site)
    os.environ["MONARCH_PROBE_ARTIFACT_DIR"] = "/tmp/monarch-phase7"
    import monarch

    assert Path(monarch.__file__).resolve().is_relative_to(prefix)
    from probe_compatibility import run

    print(f"Testing extracted Arch package: Monarch {monarch.__version__}", flush=True)
    run()


if __name__ == "__main__":
    main()
