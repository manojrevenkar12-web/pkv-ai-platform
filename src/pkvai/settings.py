"""Settings the platform reads. The world's files are read only by the evaluation and the tests."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"


def load(name: str) -> dict:
    return tomllib.loads((CONFIG / f"{name}.toml").read_text())


def platform() -> dict:
    return load("platform")


def fees() -> dict:
    return load("fees")


def gate() -> dict:
    return load("gate")


def usecases() -> dict[str, dict]:
    return {p.stem: tomllib.loads(p.read_text()) for p in sorted((CONFIG / "usecases").glob("*.toml"))}
