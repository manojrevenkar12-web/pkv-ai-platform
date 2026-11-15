"""Write README.md and web/public/data/console.json from reports/dev.json (and reports/heldout.json once it exists)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/manojrevenkar12-web/pkv-ai-platform"

ROUTING = {
    "large_everywhere": "Large model routes every email",
    "small_everywhere": "Small model routes every email",
    "classical_static": "Classifier, never retrained",
    "platform_no_monitor": "Classifier retrained weekly, no monitor",
    "platform": "**Platform: retrained weekly, monitored, labels on alarm**",
}
INVOICES = {
    "llm_decides": "Large model reads and settles",
    "code_rules": "Small model reads, code settles",
    "platform": "**Platform: code settles, disputed lines read twice**",
}
ASSIST = {
    "memory_large": "Large model answers from memory",
    "rag_large": "Large model with retrieved clauses",
    "platform": "**Platform: rewrite, retrieve, check the draft**",
}
UC = {"routing": "Email routing", "invoices": "Invoice check", "assist": "Chat assist"}


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def eur(x, d=0):
    return f"€{x:,.{d}f}"


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] + ["--:"] * (len(head) - 1)) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def routing_rows(r):
    return [
        [
            n,
            pct(d["accuracy"]),
            pct(d["accuracy_on_letter_answers"]),
            d["misroutes_per_week"],
            pct(d["llm_share"]),
            eur(d["model_eur_per_month"], 2),
            d["people_hours_per_month"],
        ]
        for k, n in ROUTING.items()
        for d in [r["routing"]["designs"][k]]
    ]


def invoice_rows(r):
    return [
        [
            n,
            pct(d["settled_without_person"]),
            eur(d["overpaid_per_1000_eur"]),
            eur(d["underpaid_per_1000_eur"]),
            d["wrong_automatic_settlements"],
            eur(d["cost_per_invoice_eur"], 4),
        ]
        for k, n in INVOICES.items()
        for d in [r["invoices"][k]]
    ]


def assist_rows(r):
    return [
        [n, pct(d["drafts_used"]), d["wrong_answers_per_1000"], d["minutes_per_chat"], eur(d["cost_per_chat_eur"], 4)]
        for k, n in ASSIST.items()
        for d in [r["assist"]["designs"][k]]
    ]


def readme(r, h):
    t, v, dr = r["totals"], r["routing"]["validation"], r["routing"]["drift"]
    big, plat = t["large_everywhere"], t["platform"]
    ro, inv, asg = r["routing"]["designs"], r["invoices"], r["assist"]
    letter = dr["letter_week"]
    weekly = r["routing"]["designs"]
    lw = [letter - 1, letter, letter + 1, letter + 2, letter + 3]
    first = r["volume"]["live_from_week"]
    wk_rows = [
        [ROUTING[k].replace("**", "")] + [pct(weekly[k]["weekly"][w - first]) for w in lw]
        for k in ("classical_static", "platform_no_monitor", "platform")
    ]
    sel_rows = [
        [
            UC[k],
            s["chosen"],
            *[
                f"{tr['model']}: {pct(tr['quality'])}, {eur(tr['cost_per_case_eur'] + tr['people_and_leakage_per_case_eur'], 3)} all in{'' if tr['passes'] else ' (fails: ' + tr['why'] + ')'}"
                for tr in s["trials"]
            ][:3],
        ]
        for k, s in r["selection"].items()
    ]
    for row in sel_rows:
        row += [""] * (5 - len(row))
    feas_rows = [
        [
            UC[k],
            f["runtime"],
            f"{f['crossover_cases_per_day']:,}",
            f["concurrency"],
            pct(f["quota"]["quota_share"]),
            "yes" if f["input_via_s3"] else "no",
        ]
        for k, f in r["feasibility"].items()
    ]
    ex = inv["platform"]["example"]
    held = ""
    if h:
        ht = h["totals"]
        held = f"""Run once, with the code and settings the dev world ended on (`config/heldout.lock`): other customers, an earlier
premium letter (week {h["routing"]["drift"]["letter_week"]}), more English and more paraphrased chat questions.

{
            table(
                ["", "Routing accuracy", "After the letter", "Overpaid per 1,000 invoices", "Wrong chat answers per 1,000", "All in per month"],
                [
                    [
                        "Large model everywhere",
                        pct(h["routing"]["designs"]["large_everywhere"]["accuracy"]),
                        pct(h["routing"]["designs"]["large_everywhere"]["accuracy_on_letter_answers"]),
                        eur(h["invoices"]["llm_decides"]["overpaid_per_1000_eur"]),
                        h["assist"]["designs"]["rag_large"]["wrong_answers_per_1000"],
                        eur(ht["large_everywhere"]["all_in_eur_per_month"]),
                    ],
                    [
                        "Platform",
                        pct(h["routing"]["designs"]["platform"]["accuracy"]),
                        pct(h["routing"]["designs"]["platform"]["accuracy_on_letter_answers"]),
                        eur(h["invoices"]["platform"]["overpaid_per_1000_eur"]),
                        h["assist"]["designs"]["platform"]["wrong_answers_per_1000"],
                        eur(ht["platform"]["all_in_eur_per_month"]),
                    ],
                ],
            )
        }

What it showed and what changed afterwards: [docs/heldout.md](docs/heldout.md)."""
    else:
        held = "Not run yet. `python scripts/evaluate.py --heldout` runs it once and writes `config/heldout.lock`."

    return f"""# pkv-ai-platform

[![ci]({REPO}/actions/workflows/ci.yml/badge.svg)]({REPO}/actions/workflows/ci.yml)

A digital private health insurer's AI team runs a handful of use cases (email routing, reading doctors' invoices,
helping chat agents) and wants them on **one platform** instead of three projects. This repository is that platform,
with those three use cases on it:

- **Every use case is a contract** (`config/usecases/*.toml`): what it reads and returns, which models may serve it,
  the bar it must clear, its traffic, and the data it touches. The platform refuses a contract it cannot check.
- **The model is chosen, not assumed.** Each candidate (a word-counting classifier, a small and a large Bedrock model)
  runs on the holdout weeks; the platform keeps the one with the lowest cost per case once people's time and money
  paid out wrongly are counted, among those that clear the gate.
- **Validation that predicts production.** A random split leaks a customer's follow-up emails into the test set;
  the platform splits by time and by customer.
- **Monitoring before labels arrive.** A daily test on the share of emails the classifier is unsure of catches a new
  kind of email the day it starts; people label a few of them, and the classifier is retrained that night.
- **The model reads, code decides.** Invoice settlement applies the fee schedule (GOÄ) in code; a chat draft reaches
  the agent only if it cites a clause it was given and states what that clause says.
- **Feasibility before building.** Each contract is checked for runtime (Lambda or Fargate), Bedrock quota at peak,
  and data rules; the result is a design note per use case and the Terraform inputs.

![Console](docs/console.png)

## Results on the dev world

{r["volume"]["emails"]:,} emails, {r["volume"]["invoices"]:,} invoices and {r["volume"]["chats"]:,} chat questions over {
        r["volume"]["weeks"]
    } weeks, simulated;
weeks 1–10 train, 11–12 decide the gate, {first}–{r["volume"]["weeks"]} are live. In week {letter} the premium-adjustment letters go out.

**Per month, all three use cases, on the simulated volume:**

{
        table(
            ["", "Model cost", "People hours", "Overpaid on invoices", "All in"],
            [
                [
                    "Large model everywhere",
                    eur(big["model_eur_per_month"], 2),
                    big["people_hours_per_month"],
                    eur(big["overpaid_eur_per_month"]),
                    eur(big["all_in_eur_per_month"]),
                ],
                [
                    "**Platform**",
                    eur(plat["model_eur_per_month"], 2),
                    plat["people_hours_per_month"],
                    eur(plat["overpaid_eur_per_month"]),
                    f"**{eur(plat['all_in_eur_per_month'])}**",
                ],
            ],
        )
    }

People's time is costed at {eur(42)} an hour (`config/platform.toml`).

### Email routing

{
        table(
            ["Design", "Accuracy", "On answers to the letter", "Misroutes a week", "Sent to an LLM", "Model cost a month", "People hours a month"],
            routing_rows(r),
        )
    }

The monitor raised its alarm {dr["detected_after_days"]} days after the letters went out ({
        "; ".join(dr["alarm"]["why"]) if dr["alarm"] else "no alarm"
    }),
with {dr["false_alarms_before_letter"]} false alarms in the weeks before. People labelled {ro["platform"]["labels_from_people"]} emails in all.

{table(["Accuracy by week", *[f"Week {w}" for w in lw]], wk_rows)}

**Validation that predicts production** (the classifier alone, trained on weeks 1–10):

{
        table(
            ["Estimate", "Accuracy", "Off by"],
            [
                ["Random 20% split of weeks 1–12", pct(v["random_split"]), f"{(v['random_split'] - v['production_before_letter']) * 100:+.1f} pts"],
                [
                    "Weeks 11–12, customers not seen in training",
                    pct(v["grouped_by_time_and_customer"]),
                    f"{(v['grouped_by_time_and_customer'] - v['production_before_letter']) * 100:+.1f} pts",
                ],
                [f"Production, weeks {first}–{letter - 1}", pct(v["production_before_letter"]), ""],
            ],
        )
    }

### Invoice check

{
        table(
            [
                "Design",
                "Settled without a person",
                "Overpaid per 1,000 invoices",
                "Underpaid per 1,000",
                "Wrong automatic settlements",
                "Model cost per invoice",
            ],
            invoice_rows(r),
        )
    }

Example the platform settled (`{ex["id"]}`): billed {eur(ex["billed"], 2)}, paid {eur(ex["paid"], 2)}, because {"; ".join(ex["notes"])}.

### Chat assist

{
        table(
            ["Design", "Drafts the agent sends as they are", "Wrong answers to customers per 1,000", "Agent minutes per chat", "Model cost per chat"],
            assist_rows(r),
        )
    }

Retrieval finds the right clause in the top {3} for {pct(asg["retrieval"]["tariff_words"], 0)} of questions asked in the tariff's own words and
{pct(asg["retrieval"]["paraphrased"], 0)} of questions in the customer's own words; asking the model to restate the question first lifts that to
{pct(asg["retrieval"]["paraphrased_after_rewrite"], 0)}. The retrieval-score floor ({
        asg["floor"]
    }) is calibrated on the holdout weeks so the 90% upper bound of
the wrong-answer rate stays within the gate.

### Model chosen per use case

{table(["Use case", "Chosen", "Candidate", "Candidate", "Candidate"], sel_rows)}

### Where each use case runs

{
        table(
            [
                "Use case",
                "Runtime",
                "Lambda cheaper until (cases a day)",
                "Concurrency at peak",
                "Share of Bedrock quota at peak",
                "Input through S3",
            ],
            feas_rows,
        )
    }

Design notes: [routing](docs/architecture/routing.md), [invoices](docs/architecture/invoices.md), [assist](docs/architecture/assist.md).

## Held-out world

{held}

## How it is built

| Part | Files | What it does |
|---|---|---|
| Contracts | `config/usecases/*.toml`, `src/pkvai/platform/contract.py` | One file per use case; validated before anything runs. |
| Model choice | `src/pkvai/platform/select.py` | Candidates on the holdout weeks; the gate, then the lowest cost all in. |
| Monitoring | `src/pkvai/platform/monitor.py` | Binomial test on the unsure share, PSI on the predicted mix, reviewed quality. |
| Feasibility | `src/pkvai/platform/feasibility.py`, `scripts/design.py` | Lambda or Fargate, quota at peak, data rules; writes the design notes and Terraform inputs. |
| Routing | `src/pkvai/usecases/routing.py` | Hashed n-grams, tf-idf, logistic regression; LLM for the unsure tail. |
| Invoices | `src/pkvai/usecases/invoices.py`, `config/fees.toml` | Arithmetic self-check, reasons above the threshold, fee agreements, excluded pairs. |
| Assist | `src/pkvai/usecases/assist.py` | Clause index, retrieval, grounding check. |
| Live calls | `src/pkvai/llm.py`, `prompts/` | Bedrock Converse with a forced tool for every call. |
| Infrastructure | `infra/modules/usecase`, `infra/live` | Per use case: SQS with a dead-letter queue, S3 with retention, KMS, a role limited to its models, Lambda or Fargate, alarms on dead letters and reviewed quality. |
| Evaluation | `scripts/evaluate.py`, `scripts/gate.py` | Designs on the same items and the same luck; the gate in CI. |
| Console | `web/` | React, Vite, React Query, Framer Motion. |

## Run it

```bash
pip install -e ".[dev]"
python -m pytest -q
python scripts/evaluate.py      # dev world -> reports/dev.json (about 40 s)
python scripts/gate.py
python scripts/design.py        # design notes and infra/live/usecases.auto.tfvars.json
python scripts/readme.py        # this README and the console data
cd infra/live && terraform init -backend=false && terraform validate
cd web && npm ci && npm run build
```

## Limits

- The insurer, its customers, invoices, chat questions and the models' mistakes are simulated (`config/world.toml`).
  The tariff in `src/pkvai/world/text.py` is fictional; the fee schedule in `config/fees.toml` is an illustrative
  excerpt in the shape of the GOÄ and has to be checked against the official schedule before any real use.
- The Bedrock client and prompts are written for the live calls and have not been run against Bedrock here; the
  Terraform is validated in CI, not applied. Prices in `config/platform.toml` are illustrative.
- The embedder is a small hashed n-gram model so the evaluation runs anywhere; in production the same interface wraps
  a Bedrock embedding model and pgvector.
"""


def slim(r):
    keep = ("world", "volume", "totals", "selection", "feasibility")
    out = {k: r[k] for k in keep}
    out["routing"] = {
        "validation": r["routing"]["validation"],
        "drift": r["routing"]["drift"],
        "example": r["routing"]["example"],
        "designs": {k: {kk: vv for kk, vv in v.items() if kk != "daily"} for k, v in r["routing"]["designs"].items()},
        "daily": r["routing"]["designs"]["platform"]["daily"],
    }
    out["invoices"] = r["invoices"]
    out["assist"] = r["assist"]
    return out


def main():
    r = json.loads((ROOT / "reports" / "dev.json").read_text())
    hp = ROOT / "reports" / "heldout.json"
    h = json.loads(hp.read_text()) if hp.exists() else None
    (ROOT / "README.md").write_text(readme(r, h))
    out = ROOT / "web" / "public" / "data"
    out.mkdir(parents=True, exist_ok=True)
    names = {"routing": ROUTING, "invoices": INVOICES, "assist": ASSIST, "usecases": UC}
    names = {g: {k: v.replace("**", "") for k, v in m.items()} for g, m in names.items()}
    (out / "console.json").write_text(json.dumps({"dev": slim(r), "heldout": slim(h) if h else None, "names": names}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
