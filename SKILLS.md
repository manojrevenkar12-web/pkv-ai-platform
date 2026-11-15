# SKILLS.md

## Add a use case

1. Write `config/usecases/<name>.toml`: purpose, owner, input and output, candidate models, gate, traffic, data.
2. Put its logic in `src/pkvai/usecases/<name>.py`: the model reads, code decides.
3. Add its trial and its designs to `scripts/evaluate.py`, then run evaluate, design and readme.
4. Read `docs/architecture/<name>.md` before building anything else: runtime, quota at peak, data rules.

## Change a model or a prompt

Change `config/platform.toml` or `prompts/`, run `python scripts/evaluate.py` and `python scripts/gate.py`. The
selection table in each design note shows whether the choice moved and why.

## When a monitor alarm fires

Look at the alarm's reason in `reports/dev.json` (`routing.drift`) or CloudWatch (`PkvAi/ReviewedQuality`). The
platform already sends emails full of new words to the large model and asks for labels; check the next night's
retrain in the daily log, and close the alarm only when the delayed labels cover it.

## Update the fee schedule

Edit `config/fees.toml` from the official schedule, add a test in `tests/test_usecases.py` for the changed rule, and
rerun the evaluation: the invoice table shows the effect on overpaid and underpaid amounts.
