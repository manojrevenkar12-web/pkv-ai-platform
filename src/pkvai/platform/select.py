"""Pick the model for a use case. Of the candidates that clear the contract's gate on the holdout weeks, start from the
cheapest model; move to another only if it saves money per case all in (model calls, people's time, money paid out
wrongly) and a paired bootstrap over the same holdout cases says the saving is real at 90%."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Trial:
    model: str
    quality: float
    cost_per_case_eur: float
    people_and_leakage_per_case_eur: float
    p95_latency_s: float
    passes: bool
    why: str
    saving_vs_cheapest: float | None = None
    saving_low: float | None = None


def choose(trials: list[Trial], cases: dict[str, np.ndarray] | None = None, confidence: float = 0.9, resamples: int = 2000) -> Trial | None:
    passing = [t for t in trials if t.passes]
    if not passing:
        return None
    if cases is None:
        return min(passing, key=lambda t: (t.cost_per_case_eur + t.people_and_leakage_per_case_eur, -t.quality))
    base = min(passing, key=lambda t: (t.cost_per_case_eur, -t.quality))
    best, best_saving = base, 0.0
    rng = np.random.default_rng(0)
    for t in passing:
        if t is base:
            continue
        d = np.asarray(cases[base.model]) - np.asarray(cases[t.model])  # positive: t is cheaper all in
        idx = rng.integers(0, len(d), size=(resamples, len(d)))
        low = float(np.quantile(d[idx].mean(axis=1), 1 - confidence))
        t.saving_vs_cheapest, t.saving_low = round(float(d.mean()), 5), round(low, 5)
        if low > 0 and d.mean() > best_saving:
            best, best_saving = t, float(d.mean())
    return best


def judge(model: str, quality: float, cost: float, latency: float, gate: dict, people: float = 0.0) -> Trial:
    why = []
    if quality < gate["min_quality"]:
        why.append(f"quality {quality:.3f} under {gate['min_quality']}")
    if cost > gate["max_cost_per_case_eur"]:
        why.append(f"cost {cost:.4f} over {gate['max_cost_per_case_eur']}")
    if latency > gate["max_p95_latency_s"]:
        why.append(f"p95 latency {latency}s over {gate['max_p95_latency_s']}s")
    return Trial(model, round(quality, 4), round(cost, 5), round(people, 5), latency, not why, "; ".join(why) or "clears the gate")
