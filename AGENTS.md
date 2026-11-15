# AGENTS.md

How to work in this repository, for people and coding agents.

## Fast feedback

```bash
python -m pytest -q                 # ~3 s
ruff check . && ruff format --check .
python scripts/evaluate.py          # ~40 s, writes reports/dev.json
python scripts/gate.py
python scripts/design.py            # docs/architecture/*.md and infra/live/usecases.auto.tfvars.json
python scripts/readme.py            # README.md and web/public/data/console.json
cd infra/live && terraform fmt -check -recursive .. && terraform init -backend=false && terraform validate
cd web && npm test && npm run build
```

Commit the regenerated files. CI fails when one does not match its source.

## Invariants

1. **Truth stays in the world.** `src/pkvai/world/` holds what each email really asks, what each invoice really owes,
   which clause answers each chat question, and the models' mistakes. Only `scripts/evaluate.py` and the tests import
   it; `tests/test_invariants.py` checks this.
2. **The world does not read the platform's settings.** `config/world.toml` and `config/heldout.toml` drive the world;
   `config/platform.toml`, `config/fees.toml` and `config/usecases/` drive the platform.
3. **Same luck for every design.** Every draw is keyed by the item and the mistake, never by the design.
4. **The model reads, code decides.** Settlement amounts, routing thresholds and whether a chat draft reaches the agent
   are code. The model never applies the fee schedule in the platform's design.
5. **Every use case is a contract.** A use case is added by writing `config/usecases/<name>.toml`; the platform refuses
   a contract it cannot check, and the model, runtime and Terraform inputs follow from it.
6. **Settings in config, results generated.** No number in README.md, docs/architecture or the console is typed by hand.

## Held-out rule

`python scripts/evaluate.py --heldout` runs the held-out world once and writes `config/heldout.lock`. After that,
changes are measured on the dev world only; findings go in `docs/heldout.md`. `config/gate.toml` is not moved.
