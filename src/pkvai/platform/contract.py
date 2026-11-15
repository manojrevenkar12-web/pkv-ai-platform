"""A use case is a contract: what it reads and returns, which models may serve it, the bar it must clear, how much
traffic it brings and what data it touches. The platform refuses a contract it cannot check."""

from __future__ import annotations

from dataclasses import dataclass

REQUIRED = {
    "name": str,
    "owner": str,
    "purpose": str,
    "input": str,
    "output": str,
    "candidates": list,
    "gate": dict,
    "deploy": dict,
    "data": dict,
    "tokens": dict,
}
GATE = {"min_quality": float, "max_cost_per_case_eur": float, "max_p95_latency_s": float}
DEPLOY = {"volume_per_day": int, "peak_per_minute": int, "max_input_mb": (int, float), "processing_s": (int, float), "memory_mb": int}
DATA = {"personal": bool, "health": bool, "retention_days": int}


@dataclass(frozen=True)
class Contract:
    key: str
    spec: dict

    def __getattr__(self, item):
        try:
            return self.spec[item]
        except KeyError as e:
            raise AttributeError(item) from e


def problems(spec: dict, models: dict) -> list[str]:
    out = []
    for k, t in REQUIRED.items():
        if not isinstance(spec.get(k), t):
            out.append(f"{k} is missing or not a {t.__name__}")
    for section, fields in (("gate", GATE), ("deploy", DEPLOY), ("data", DATA)):
        for k, t in fields.items():
            v = spec.get(section, {}).get(k)
            if not isinstance(v, t) or isinstance(v, bool) and t is not bool:
                out.append(f"{section}.{k} is missing or has the wrong type")
    for m in spec.get("candidates", []) + ([spec["fallback"]] if "fallback" in spec else []):
        if m not in models:
            out.append(f"model {m} is not offered by the platform")
    if spec.get("data", {}).get("health") and spec.get("data", {}).get("retention_days", 0) < 1:
        out.append("health data needs a retention period")
    return out


def load_all(specs: dict[str, dict], models: dict) -> dict[str, Contract]:
    bad = {k: p for k, s in specs.items() if (p := problems(s, models))}
    if bad:
        raise ValueError(f"contracts the platform cannot run: {bad}")
    return {k: Contract(k, s) for k, s in specs.items()}
