"""Pick the model for a use case: of the candidates that clear the contract's gate on the validation weeks, the one with
the lowest cost per case once people's time and money paid out wrongly are counted, not the cheapest model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Trial:
    model: str
    quality: float
    cost_per_case_eur: float
    people_and_leakage_per_case_eur: float
    p95_latency_s: float
    passes: bool
    why: str


def choose(trials: list[Trial]) -> Trial | None:
    passing = [t for t in trials if t.passes]
    return min(passing, key=lambda t: (t.cost_per_case_eur + t.people_and_leakage_per_case_eur, -t.quality)) if passing else None


def judge(model: str, quality: float, cost: float, latency: float, gate: dict, people: float = 0.0) -> Trial:
    why = []
    if quality < gate["min_quality"]:
        why.append(f"quality {quality:.3f} under {gate['min_quality']}")
    if cost > gate["max_cost_per_case_eur"]:
        why.append(f"cost {cost:.4f} over {gate['max_cost_per_case_eur']}")
    if latency > gate["max_p95_latency_s"]:
        why.append(f"p95 latency {latency}s over {gate['max_p95_latency_s']}s")
    return Trial(model, round(quality, 4), round(cost, 5), round(people, 5), latency, not why, "; ".join(why) or "clears the gate")
