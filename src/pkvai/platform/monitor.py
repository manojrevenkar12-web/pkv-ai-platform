"""Watch a deployed use case before its labels arrive: the input mix, the share it is unsure of, and later the
accuracy of a small daily sample a person labels."""

from __future__ import annotations

import numpy as np
from scipy.stats import binom


def psi(expected: np.ndarray, actual: np.ndarray, eps: float = 1e-4) -> float:
    """Population stability index between two distributions over the same categories."""
    e = np.clip(expected / expected.sum(), eps, None)
    a = np.clip(actual / actual.sum(), eps, None)
    return float(((a - e) * np.log(a / e)).sum())


def mix(labels: list[str], categories: list[str]) -> np.ndarray:
    return np.array([sum(1 for x in labels if x == c) for c in categories], dtype=float)


def alarm(low: int, n: int, day_psi: float, base_low_conf: float, cfg: dict) -> list[str]:
    """Raise an alarm when today's unsure share is too high to be chance at the baseline rate, or the mix moved."""
    out = []
    if n and binom.sf(low - 1, n, base_low_conf) < cfg["low_confidence_p"]:
        out.append(f"{low / n:.0%} of emails under the confidence floor, against {base_low_conf:.0%} usually")
    if day_psi > cfg["psi_alarm"]:
        out.append(f"predicted team mix shifted (PSI {day_psi:.2f})")
    return out
