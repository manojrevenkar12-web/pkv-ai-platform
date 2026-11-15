"""The truth stays in the world: nothing the platform runs imports it or reads its files."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVING = [p for p in (ROOT / "src" / "pkvai").rglob("*.py") if "world" not in p.relative_to(ROOT / "src" / "pkvai").parts]


def test_nothing_that_serves_imports_the_world():
    for p in SERVING:
        text = p.read_text()
        assert not re.search(r"\bworld\b\s+import|from\s+\.+world|pkvai\.world", text), p


def test_nothing_that_serves_reads_the_worlds_files():
    for p in SERVING:
        assert "world.toml" not in p.read_text() and "heldout.toml" not in p.read_text(), p


def test_only_the_evaluation_imports_the_world():
    users = [p.name for p in (ROOT / "scripts").glob("*.py") if "pkvai.world" in p.read_text()]
    assert users == ["evaluate.py"]


def test_the_world_does_not_read_the_platforms_settings():
    text = (ROOT / "src" / "pkvai" / "world" / "sim.py").read_text()
    for name in ("platform.toml", "gate.toml", "usecases"):
        assert name not in text


def test_same_luck_for_every_design():
    from pkvai.world.sim import World

    w = World.load()
    e = w.emails[1234]
    assert w.route(e, "small") == w.route(e, "small")
    inv = w.invoices[777]
    assert w.read(inv, "small") == w.read(inv, "small")
