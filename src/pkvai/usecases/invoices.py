"""Invoice checking: a model reads the invoice, code applies the fee schedule and the tariff."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReadLine:
    code: str
    factor: float
    amount: float
    reason: bool
    agreement: bool
    count: int = 1


@dataclass
class Settlement:
    payable: float
    notes: list[str] = field(default_factory=list)


def expected_amount(line: ReadLine, fees: dict) -> float | None:
    c = fees["codes"].get(line.code)
    if c is None:
        return None
    return round(c["points"] * fees["point_value_eur"] * line.factor * line.count, 2)


def mismatched(lines: list[ReadLine], fees: dict, tolerance: float = 0.02) -> list[int]:
    """Lines whose amount is not points x point value x factor: a misreading or the doctor's own arithmetic."""
    out = []
    for i, x in enumerate(lines):
        exp = expected_amount(x, fees)
        if exp is None or abs(exp - x.amount) > tolerance:
            out.append(i)
    return out


def needs_reason(lines: list[ReadLine], fees: dict) -> list[int]:
    """Lines above the threshold factor for which no written reason was read."""
    out = []
    for i, x in enumerate(lines):
        c = fees["codes"].get(x.code)
        if c and x.factor > fees["sections"][c["section"]]["threshold"] and not x.reason and not x.agreement:
            out.append(i)
    return out


def settle(lines: list[ReadLine], fees: dict) -> Settlement:
    """Apply the fee schedule: reasons above the threshold, fee agreements above the maximum, pairs that exclude each
    other, and never more than the doctor billed."""
    notes: list[str] = []
    codes = [x.code for x in lines]
    drop: set[int] = set()
    for a, b in fees["excluded_pairs"]:
        if a in codes and b in codes:
            ia, ib = codes.index(a), codes.index(b)
            lower = ia if fees["codes"][a]["points"] < fees["codes"][b]["points"] else ib
            drop.add(lower)
            notes.append(f"GOÄ {codes[lower]} may not be billed next to GOÄ {b if codes[lower] == a else a}")
    total = 0.0
    for i, x in enumerate(lines):
        if i in drop:
            continue
        c = fees["codes"].get(x.code)
        if c is None:
            notes.append(f"GOÄ {x.code} is not in the fee schedule")
            continue
        sec = fees["sections"][c["section"]]
        fac = x.factor
        if fac > sec["maximum"]:
            if x.agreement:
                fac = min(fac, fees["tariff_max_factor"])
            else:
                fac = sec["maximum"] if x.reason else sec["threshold"]
                notes.append(f"GOÄ {x.code}: factor {x.factor} above the maximum without a fee agreement")
        elif fac > sec["threshold"] and not x.reason:
            fac = sec["threshold"]
            notes.append(f"GOÄ {x.code}: factor {x.factor} above the threshold without a written reason")
        allowed = round(c["points"] * fees["point_value_eur"] * fac * x.count, 2)
        if x.amount > allowed + 0.005:
            notes.append(f"GOÄ {x.code}: billed {x.amount:.2f}, allowed {allowed:.2f}")
        total += min(x.amount, allowed)
    return Settlement(round(total, 2), notes)
