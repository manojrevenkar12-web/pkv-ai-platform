"""Fails (exit 1) when a report does not clear config/gate.toml.

python scripts/gate.py                       # reports/dev.json
python scripts/gate.py reports/heldout.json  # read only: the held-out result is a finding, not a release
"""

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(r: dict, g: dict) -> list[str]:
    out = []
    ro, v = r["routing"]["designs"]["platform"], r["routing"]["validation"]
    if ro["accuracy"] < g["routing"]["min_accuracy"]:
        out.append(f"routing accuracy {ro['accuracy']}")
    gap = v["grouped_by_time_and_customer"] - v["production_before_letter"]
    if abs(gap) > g["routing"]["max_estimate_gap"]:
        out.append(f"validation misses production by {gap:+.3f}")
    d = r["routing"]["drift"]["detected_after_days"]
    if d is None or d > g["routing"]["max_drift_detect_days"]:
        out.append(f"drift detected after {d} days")
    i = r["invoices"]["platform"]
    if i["overpaid_per_1000_eur"] > g["invoices"]["max_overpaid_per_1000_eur"]:
        out.append(f"overpaid {i['overpaid_per_1000_eur']} per 1000 invoices")
    if i["underpaid_per_1000_eur"] > g["invoices"]["max_underpaid_per_1000_eur"]:
        out.append(f"underpaid {i['underpaid_per_1000_eur']} per 1000 invoices")
    if i["settled_without_person"] < g["invoices"]["min_settled_without_person"]:
        out.append(f"only {i['settled_without_person']} settled without a person")
    a = r["assist"]["designs"]["platform"]
    if a["wrong_answers_per_1000"] > g["assist"]["max_wrong_answers_per_1000"]:
        out.append(f"{a['wrong_answers_per_1000']} wrong answers per 1000 chats")
    if a["drafts_used"] < g["assist"]["min_drafts_used"]:
        out.append(f"only {a['drafts_used']} drafts used")
    t = r["totals"]
    share = t["platform"]["model_eur_per_month"] / t["large_everywhere"]["model_eur_per_month"]
    if share > g["platform"]["max_cost_share_of_large_everywhere"]:
        out.append(f"model cost {share:.2f} of the large model everywhere")
    return out


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reports" / "dev.json"
    problems = check(json.loads(path.read_text()), tomllib.loads((ROOT / "config" / "gate.toml").read_text()))
    for p in problems:
        print("GATE:", p)
    if problems:
        sys.exit(1)
    print("Gate passed.")


if __name__ == "__main__":
    main()
