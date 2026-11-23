"""Packaged, offline help and original desktop artwork."""

from importlib.resources import files

APP_ID = "org.monarch.Monarch"


def text(name: str) -> str:
    if name not in {"guide.md", "notices.md"}:
        raise ValueError("Unknown bundled document")
    return files(__package__).joinpath(name).read_text(encoding="utf-8")


def icon_path() -> str:
    return str(files(__package__).joinpath("monarch.svg"))
