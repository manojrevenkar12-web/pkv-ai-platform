"""Generated files match their sources, and the dev report clears the gate."""

import json
import tomllib
from pathlib import Path

import design
import gate
import readme

ROOT = Path(__file__).resolve().parents[1]
R = json.loads((ROOT / "reports" / "dev.json").read_text())


def test_dev_report_clears_the_gate():
    assert gate.check(R, tomllib.loads((ROOT / "config" / "gate.toml").read_text())) == []


def test_readme_and_console_match_the_reports():
    h = ROOT / "reports" / "heldout.json"
    held = json.loads(h.read_text()) if h.exists() else None
    assert (ROOT / "README.md").read_text() == readme.readme(R, held)
    console = json.loads((ROOT / "web" / "public" / "data" / "console.json").read_text())
    assert console["dev"] == json.loads(json.dumps(readme.slim(R)))


def test_design_notes_and_terraform_inputs_match(tmp_path, monkeypatch):
    for p in (ROOT / "docs" / "architecture").glob("*.md"):
        key = p.stem
        c = tomllib.loads((ROOT / "config" / "usecases" / f"{key}.toml").read_text())
        tf = json.loads((ROOT / "infra" / "live" / "usecases.auto.tfvars.json").read_text())["usecases"][c["name"]]
        assert p.read_text() == design.note(key, c, R["feasibility"][key], R["selection"][key], tf["bedrock_model_ids"])
        assert tf["runtime"] == R["feasibility"][key]["runtime"]
        assert tf["min_quality"] == c["gate"]["min_quality"]
