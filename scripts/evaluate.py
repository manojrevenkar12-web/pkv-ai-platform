"""Run every use case on the simulated insurer, design against design on the same items and the same luck.

python scripts/evaluate.py             # dev world -> reports/dev.json
python scripts/evaluate.py --heldout   # the held-out world, once (writes config/heldout.lock)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import beta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pkvai import settings
from pkvai.keyed import u
from pkvai.platform import feasibility
from pkvai.platform.contract import load_all
from pkvai.platform.costs import per_case
from pkvai.platform.monitor import alarm, mix, psi
from pkvai.platform.select import choose, judge
from pkvai.usecases.assist import ClauseIndex, Embedder, grounded
from pkvai.usecases.invoices import (
    ReadLine,
    mismatched,
    needs_reason,
    settle,
)
from pkvai.usecases.routing import Router
from pkvai.world.sim import World
from pkvai.world.text import CLAUSES, TEAMS

PER_MONTH = 52 / 12


def r4(x: float) -> float:
    return round(float(x), 4)


class Run:
    def __init__(self, world_name: str):
        self.w = World.load(world_name)
        self.p = settings.platform()
        self.fees = settings.fees()
        self.models = self.p["models"]
        self.uc = load_all(settings.usecases(), self.models)
        v = self.p["validation"]
        self.train_weeks, self.hold_weeks = v["train_weeks"], v["holdout_weeks"]
        self.live_from = self.train_weeks + self.hold_weeks + 1
        self.weeks_live = self.w.cfg["weeks"] - self.live_from + 1

    def weeks(self, items, lo, hi):
        return [x for x in items if lo <= x.week <= hi]

    # ================================================================ routing
    def router(self, emails, warm: Router | None = None) -> Router:
        r = self.p["routing"]
        return Router(TEAMS, r["vocab_buckets"], r["epochs"], r["learning_rate"], r["l2"]).fit(
            [e.text for e in emails], [e.team for e in emails], warm, r["warm_epochs"] if warm else None
        )

    def routing_validation(self) -> dict:
        w, tw, hw = self.w, self.train_weeks, self.hold_weeks
        pool = self.weeks(w.emails, 1, tw + hw)
        test_r = [e for e in pool if u("split", e.id) < self.p["validation"]["random_test_share"]]
        train_r = [e for e in pool if u("split", e.id) >= self.p["validation"]["random_test_share"]]
        acc = lambda m, es: np.mean([a == e.team for a, e in zip(m.predict([e.text for e in es])[0], es, strict=True)])
        random_acc = acc(self.router(train_r), test_r)
        train_g = self.weeks(w.emails, 1, tw)
        seen = {e.customer for e in train_g}
        test_g = [e for e in self.weeks(w.emails, tw + 1, tw + hw) if e.customer not in seen]
        m = self.router(train_g)
        grouped_acc = acc(m, test_g)
        letter = w.cfg["emails"]["premium_letter_week"]
        prod = self.weeks(w.emails, self.live_from, letter - 1)
        return {
            "random_split": r4(random_acc),
            "grouped_by_time_and_customer": r4(grouped_acc),
            "production_before_letter": r4(acc(m, prod)),
            "random_test_emails": len(test_r),
            "grouped_test_emails": len(test_g),
        }

    def routing_trial(self, model: str) -> tuple[float, float, float, float]:
        """Quality, model cost per email, p95 latency and people's cost per email of a candidate on the holdout weeks."""
        hold = self.weeks(self.w.emails, self.train_weeks + 1, self.train_weeks + self.hold_weeks)
        c = self.uc["routing"]
        pp = self.p["people"]
        misroute = pp["minutes_per_misroute"] / 60 * pp["office_eur_per_hour"]
        if model != "classical":
            right = np.array([self.w.route(e, model) == e.team for e in hold])
            cost = per_case(model, c.tokens, self.models)
            self.cases["routing"][model] = cost + (~right) * misroute
            return right.mean(), cost, self.models[model]["p95_latency_s"], (1 - right.mean()) * misroute
        m = self.router(self.weeks(self.w.emails, 1, self.train_weeks))
        teams, conf = m.predict([e.text for e in hold])
        floor, fb = self.p["routing"]["confidence_floor"], c.fallback
        out = [self.w.route(e, fb) if cf < floor else t for e, t, cf in zip(hold, teams, conf, strict=True)]
        share = float(np.mean(conf < floor))
        right = np.array([t == e.team for t, e in zip(out, hold, strict=True)])
        q = right.mean()
        cost = per_case("classical", c.tokens, self.models) + share * per_case(fb, c.tokens, self.models)
        self.cases["routing"][model] = (
            per_case("classical", c.tokens, self.models) + (conf < floor) * per_case(fb, c.tokens, self.models) + (~right) * misroute
        )
        lat = self.models[fb]["p95_latency_s"] if share > 0.05 else self.models["classical"]["p95_latency_s"]
        return q, cost, lat, (1 - q) * misroute

    def routing_live(self, design: str) -> dict:
        """Weeks after go-live, day by day. Designs: large/small everywhere, classical_static, platform_no_monitor, platform.

        The platform retrains every week on the labels closed tickets give (a week late). Its monitor watches each day's
        share under the confidence floor and the predicted team mix; on an alarm, emails full of unseen words go to the
        large model, a person labels a few of them each day, and the classifier is retrained on those labels that night."""
        w, rc, mc = self.w, self.p["routing"], self.p["monitor"]
        c = self.uc["routing"]
        live = self.weeks(w.emails, self.live_from, w.cfg["weeks"])
        res = {"right": 0, "n": 0, "small": 0, "large": 0, "weekly": defaultdict(lambda: [0, 0]), "letter_right": 0, "letter_n": 0, "daily": []}
        model = None
        if design not in ("large_everywhere", "small_everywhere"):
            model = self.router(self.weeks(w.emails, 1, self.train_weeks))
            hold = self.weeks(w.emails, self.train_weeks + 1, self.train_weeks + self.hold_weeks)
            teams, conf = model.predict([e.text for e in hold])
            base_mix = mix(teams, TEAMS)
            base_low = float(np.mean(conf < rc["confidence_floor"]))
        alarm_open, alarm_since, alarms, retrains, reviewed = False, None, [], 0, []
        by_day = defaultdict(list)
        for e in live:
            by_day[(e.week, e.day)].append(e)
        for week in range(self.live_from, w.cfg["weeks"] + 1):
            upto = week - 1 - mc["label_delay_weeks"]
            if design.startswith("platform") and week > self.live_from:
                model = self.router(self.weeks(w.emails, 1, upto) + reviewed, warm=model)
                retrains += 1
                # the newest labelled week is the new normal the monitor compares against
                recent = self.weeks(w.emails, upto, upto)
                base_mix = mix(model.predict([e.text for e in recent])[0], TEAMS)
            for day in range(7):
                es = by_day.get((week, day), [])
                if not es:
                    continue
                if (
                    alarm_open
                    and alarm_since
                    and (week, day) >= alarm_since
                    and upto >= alarm_since[0]
                    and (week - alarm_since[0]) * 7 + day - alarm_since[1] >= rc["alarm_days_min"]
                ):
                    alarm_open = False
                if model is None:
                    big = design == "large_everywhere"
                    routed = [w.route(e, "large" if big else "small") for e in es]
                    res["large" if big else "small"] += len(es)
                else:
                    teams, conf = model.predict([e.text for e in es])
                    low = conf < rc["confidence_floor"]
                    new = model.unknown_share([e.text for e in es]) > rc["new_words_share"] if alarm_open else np.zeros(len(es), bool)
                    routed = []
                    for e, t, lo, nw in zip(es, teams, low, new, strict=True):
                        if nw:
                            routed.append(w.route(e, "large"))
                            res["large"] += 1
                        elif lo:
                            routed.append(w.route(e, c.fallback))
                            res["small"] += 1
                        else:
                            routed.append(t)
                    day_low, day_psi = float(np.mean(low)), psi(base_mix, mix(teams, TEAMS))
                    if design == "platform":
                        res["daily"].append({"week": week, "day": day, "low_confidence": r4(day_low), "psi": r4(day_psi), "alarm": alarm_open})
                        if not alarm_open and (why := alarm(int(low.sum()), len(es), day_psi, base_low, mc)):
                            alarm_open, alarm_since = True, (week, day)
                            alarms.append({"week": week, "day": day, "why": why})
                        if alarm_open:
                            flagged = [e for e, nw, lo in zip(es, new, low, strict=True) if nw or lo]
                            flagged.sort(key=lambda e: u("review", e.id))
                            reviewed += flagged[: mc["review_per_day"]]
                            model = self.router(self.weeks(w.emails, 1, upto) + reviewed, warm=model)
                            retrains += 1
                for e, t in zip(es, routed, strict=True):
                    ok = t == e.team
                    res["right"] += ok
                    res["n"] += 1
                    res["weekly"][week][0] += ok
                    res["weekly"][week][1] += 1
                    if e.kind == "premium":
                        res["letter_right"] += ok
                        res["letter_n"] += 1
        n = res["n"]
        cost = (per_case("classical", c.tokens, self.models) if model is not None else 0) + (
            res["small"] * per_case("small", c.tokens, self.models) + res["large"] * per_case("large", c.tokens, self.models)
        ) / n
        mis = n - res["right"]
        return {
            "accuracy": r4(res["right"] / n),
            "accuracy_on_letter_answers": r4(res["letter_right"] / max(1, res["letter_n"])),
            "misroutes": mis,
            "misroutes_per_week": round(mis / self.weeks_live, 1),
            "llm_share": r4((res["small"] + res["large"]) / n),
            "large_share": r4(res["large"] / n),
            "cost_per_email_eur": round(cost, 6),
            "model_eur_per_month": round(cost * n / self.weeks_live * PER_MONTH, 2),
            "people_hours_per_month": round((mis * self.p["people"]["minutes_per_misroute"] + len(reviewed)) / 60 / self.weeks_live * PER_MONTH, 1),
            "labels_from_people": len(reviewed),
            "weekly": [r4(res["weekly"][k][0] / res["weekly"][k][1]) for k in sorted(res["weekly"])],
            "alarms": alarms,
            "retrains": retrains,
            "daily": res["daily"],
        }

    # =============================================================== invoices
    def to_read(self, lines) -> list[ReadLine]:
        return [ReadLine(x.code, x.factor, x.amount, x.reason, x.agreement, x.count) for x in lines]

    def invoice_pipeline(self, inv, reader: str, design: str, seen: set) -> tuple[float | None, list[str], int]:
        """Returns (paid, notes, second_reads); paid None means a person settles it."""
        w = self.w
        high = self.w.cfg["invoices"]["high_value_eur"]
        if design == "llm_decides":
            return (None if inv.billed > high else w.llm_settles(inv, reader)), [], 0
        lines = self.to_read(w.read(inv, reader))
        key = (inv.customer, inv.doctor, inv.date, tuple(sorted(x.code for x in lines)))
        if key in seen:
            return 0.0, ["the same invoice was settled before"], 0
        seen.add(key)
        if sum(x.amount for x in lines) > high:
            return None, ["high value: a person settles it"], 0
        second = 0
        if design == "platform":
            bad = mismatched(lines, self.fees)
            ask = sorted(set(bad) | set(needs_reason(lines, self.fees)))
            if ask:
                second = 1
                again = self.to_read(w.read(inv, "small" if reader == "large" else "large"))
                for i in ask:
                    if i in bad and again[i] != lines[i] and mismatched([again[i]], self.fees):
                        return None, ["two readings disagree and neither adds up: a person settles it"], second
                    lines[i] = again[i]
        s = settle(lines, self.fees)
        return s.payable, s.notes, second

    def invoices_run(self, items, reader: str, design: str) -> dict:
        pp = self.p["people"]
        over = under = 0.0
        auto = wrong = people = seconds = 0
        # the claims system already holds everything settled before these invoices
        first = min(x.week for x in items)
        seen = {(x.customer, x.doctor, x.date, tuple(sorted(y.code for y in x.lines))) for x in self.w.invoices if x.week < first}
        example = None
        cases = []
        first_read = per_case("large" if design == "llm_decides" else reader, self.uc["invoices"].tokens, self.models)
        second_read = per_case("small" if reader == "large" else "large", self.uc["invoices"].spec["tokens_second_read"], self.models)
        person = pp["minutes_per_invoice_review"] / 60 * pp["office_eur_per_hour"]
        for inv in items:
            truth = self.w.payable(inv)
            paid, notes, second = self.invoice_pipeline(inv, reader, design, seen)
            seconds += second
            case = first_read + second * second_read
            if paid is None:
                people += 1
                paid = truth
                case += person
            else:
                auto += 1
                if abs(paid - truth) > 0.01:
                    wrong += 1
                if (
                    example is None
                    and design == "platform"
                    and notes
                    and abs(paid - truth) <= 0.01
                    and inv.billed - paid > 5
                    and not inv.duplicate_of
                ):
                    example = {"id": inv.id, "invoice": self.w.render(inv), "billed": inv.billed, "paid": paid, "notes": notes}
            over += max(0.0, paid - truth)
            under += max(0.0, truth - paid)
            cases.append(case + max(0.0, paid - truth))
        n = len(items)
        model_cost = per_case("large" if design == "llm_decides" else reader, self.uc["invoices"].tokens, self.models) + seconds / n * per_case(
            "small" if reader == "large" else "large", self.uc["invoices"].spec["tokens_second_read"], self.models
        )
        return {
            "invoices": n,
            "settled_without_person": r4(auto / n),
            "wrong_automatic_settlements": wrong,
            "overpaid_per_1000_eur": round(over / n * 1000, 2),
            "underpaid_per_1000_eur": round(under / n * 1000, 2),
            "second_reads": r4(seconds / n),
            "cost_per_invoice_eur": round(model_cost, 5),
            "model_eur_per_month": round(model_cost * n / self.weeks_live * PER_MONTH, 2) if n else 0,
            "people_hours_per_month": round(people * pp["minutes_per_invoice_review"] / 60 / self.weeks_live * PER_MONTH, 1),
            "people_minutes_per_invoice": round(people * pp["minutes_per_invoice_review"] / n, 4),
            "overpaid_eur_per_month": round(over / self.weeks_live * PER_MONTH, 2),
            "quality": r4(1 - wrong / n),
            "example": example,
            "_cases": np.array(cases),
        }

    # ================================================================= assist
    def assist_run(self, items, model: str, design: str, floor: float | None = None) -> dict:
        ac, pp, w = self.p["assist"], self.p["people"], self.w
        idx = self.index
        stats = defaultdict(int)
        example = None
        minutes = []
        for ch in items:
            before = stats["minutes"]
            if design == "memory_large":
                d, offered = w.draft(ch, "large", None), True
            else:
                hits = idx.search(ch.text, ac["top_k"])
                if design == "platform":
                    rw = w.rewrite(ch, model)
                    if rw != ch.text:
                        best = {}
                        for i, s in hits + idx.search(rw, ac["top_k"]):
                            best[i] = max(s, best.get(i, -1.0))
                        hits = sorted(best.items(), key=lambda kv: -kv[1])[: ac["top_k"]]
                ids = [i for i, _ in hits]
                if design == "platform" and hits[0][1] < floor:
                    d, offered = None, False
                    stats["below_floor"] += 1
                else:
                    d = w.draft(ch, model, ids)
                    offered = d.fact is not None
                    if design == "platform" and offered and not grounded(d.cites, d.fact, ids, idx.text):
                        offered = False
                        stats["blocked"] += 1
                        if example is None and d.kind in ("invented", "wrong_fact"):
                            example = {"question": ch.text, "draft_fact": d.fact, "cites": d.cites, "clause_text": idx.text[d.cites[0]]}
            if not offered:
                stats["written"] += 1
                stats["minutes"] += pp["minutes_per_chat_written"]
                minutes.append(stats["minutes"] - before)
                continue
            stats["offered"] += 1
            stats["minutes"] += pp["minutes_per_chat_draft_checked"]
            if w.right_answer(ch, d):
                stats["used"] += 1
            elif w.agent_catches(ch):
                stats["caught"] += 1
                stats["minutes"] += pp["minutes_per_chat_written"]
            else:
                stats["wrong_sent"] += 1
            minutes.append(stats["minutes"] - before)
        n = len(items)
        m = "large" if design != "platform" else model
        cost = (
            per_case(m, self.uc["assist"].tokens, self.models)
            * (stats["offered"] + stats["blocked"] + (n - stats["below_floor"] - stats["offered"] - stats["blocked"]))
            / n
        )
        if design == "platform":
            cost += per_case(m, {"in": 150, "out": 60}, self.models)  # the rewrite
        return {
            "chats": n,
            "drafts_used": r4(stats["used"] / n),
            "wrong_answers_per_1000": round(stats["wrong_sent"] / n * 1000, 2),
            "wrong_drafts_caught_by_agent": stats["caught"],
            "blocked_by_check": stats["blocked"],
            "below_floor": stats["below_floor"],
            "minutes_per_chat": round(stats["minutes"] / n, 2),
            "cost_per_chat_eur": round(cost, 5),
            "model_eur_per_month": round(cost * n / self.weeks_live * PER_MONTH, 2) if n else 0,
            "people_hours_per_month": round(stats["minutes"] / 60 / self.weeks_live * PER_MONTH, 1) if n else 0,
            "quality": r4(1 - stats["wrong_sent"] / n),
            "example": example,
            "_cases": cost + np.array(minutes) / 60 * pp["office_eur_per_hour"],
        }

    def calibrate_floor(self, model: str) -> float:
        """The lowest retrieval-score floor whose wrong-answer rate on the holdout weeks stays within the gate even at the
        90% upper bound (Clopper-Pearson): two weeks of chats are too few to trust the plain rate."""
        hold = self.weeks(self.w.chats, self.train_weeks + 1, self.train_weeks + self.hold_weeks)
        budget = settings.gate()["assist"]["max_wrong_answers_per_1000"] / 1000
        for floor in np.arange(0.0, 0.61, 0.025):
            r = self.assist_run(hold, model, "platform", float(floor))
            k = round(r["wrong_answers_per_1000"] * r["chats"] / 1000)
            if beta.ppf(0.9, k + 1, r["chats"] - k) <= budget:
                return round(float(floor), 3)
        return 0.6

    def retrieval(self) -> dict:
        k = self.p["assist"]["top_k"]
        out = {}
        for para in (False, True):
            ch = [c for c in self.w.chats if c.paraphrased == para][:3000]
            out["paraphrased" if para else "tariff_words"] = r4(np.mean([c.clause in [i for i, _ in self.index.search(c.text, k)] for c in ch]))
        ch = [c for c in self.w.chats if c.paraphrased][:3000]
        out["paraphrased_after_rewrite"] = r4(np.mean([c.clause in [i for i, _ in self.index.search(self.w.rewrite(c, "small"), k)] for c in ch]))
        return out

    # ================================================================ the run
    def run(self) -> dict:
        w, gate = self.w, settings.gate()
        self.index = ClauseIndex([c[:3] for c in CLAUSES], Embedder(self.p["assist"]["embed_dim"]))
        hold = lambda items: self.weeks(items, self.train_weeks + 1, self.train_weeks + self.hold_weeks)
        live = lambda items: self.weeks(items, self.live_from, w.cfg["weeks"])

        selection = {}
        self.cases = {"routing": {}, "invoices": {}, "assist": {}}
        trials = []
        for m in self.uc["routing"].candidates:
            q, cost, lat, people = self.routing_trial(m)
            trials.append(judge(m, q, cost, lat, self.uc["routing"].gate, people))
        selection["routing"] = trials
        inv_trials = []
        rate = self.p["people"]["office_eur_per_hour"]
        for m in self.uc["invoices"].candidates:
            r = self.invoices_run(hold(w.invoices), m, "platform")
            self.cases["invoices"][m] = r["_cases"]
            people = r["people_minutes_per_invoice"] / 60 * rate + r["overpaid_per_1000_eur"] / 1000
            inv_trials.append(
                judge(m, r["quality"], r["cost_per_invoice_eur"], self.models[m]["p95_latency_s"] * 2 + 20, self.uc["invoices"].gate, people)
            )
        selection["invoices"] = inv_trials
        as_trials, floors = [], {}
        for m in self.uc["assist"].candidates:
            floors[m] = self.calibrate_floor(m)
            r = self.assist_run(hold(w.chats), m, "platform", floors[m])
            self.cases["assist"][m] = r["_cases"]
            people = r["minutes_per_chat"] / 60 * rate
            as_trials.append(judge(m, r["quality"], r["cost_per_chat_eur"], self.models[m]["p95_latency_s"] * 2, self.uc["assist"].gate, people))
        selection["assist"] = as_trials
        chosen = {k: choose(v, self.cases[k]) for k, v in selection.items()}
        if any(v is None for v in chosen.values()):
            raise SystemExit(f"no candidate clears a use case's gate: {selection}")

        routing = {d: self.routing_live(d) for d in ("large_everywhere", "small_everywhere", "classical_static", "platform_no_monitor", "platform")}
        letter = w.cfg["emails"]["premium_letter_week"]
        a = routing["platform"]["alarms"]
        first = next((x for x in a if x["week"] >= letter), None)
        drift = {
            "letter_week": letter,
            "alarm": first,
            "detected_after_days": (first["week"] - letter) * 7 + first["day"] if first else None,
            "false_alarms_before_letter": sum(1 for x in a if x["week"] < letter),
        }

        invoices = {
            "llm_decides": self.invoices_run(live(w.invoices), "large", "llm_decides"),
            "code_rules": self.invoices_run(live(w.invoices), chosen["invoices"].model, "code_rules"),
            "platform": self.invoices_run(live(w.invoices), chosen["invoices"].model, "platform"),
        }
        m = chosen["assist"].model
        assist = {
            "memory_large": self.assist_run(live(w.chats), "large", "memory_large"),
            "rag_large": self.assist_run(live(w.chats), "large", "rag_large"),
            "platform": self.assist_run(live(w.chats), m, "platform", floors[m]),
        }

        def total(r, i, s):
            model = r["model_eur_per_month"] + i["model_eur_per_month"] + s["model_eur_per_month"]
            hours = r["people_hours_per_month"] + i["people_hours_per_month"] + s["people_hours_per_month"]
            people = hours * self.p["people"]["office_eur_per_hour"]
            return {
                "model_eur_per_month": round(model, 2),
                "people_hours_per_month": round(hours, 1),
                "people_eur_per_month": round(people, 2),
                "overpaid_eur_per_month": i["overpaid_eur_per_month"],
                "all_in_eur_per_month": round(model + people + i["overpaid_eur_per_month"], 2),
            }

        for d in list(invoices.values()) + list(assist.values()):
            d.pop("_cases", None)
        totals = {
            "large_everywhere": total(routing["large_everywhere"], invoices["llm_decides"], assist["rag_large"]),
            "platform": total(routing["platform"], invoices["platform"], assist["platform"]),
        }

        rt = self.p["runtime"]
        feas = {}
        llm_share = {"routing": routing["platform"]["llm_share"], "invoices": 1 + invoices["platform"]["second_reads"], "assist": 1.0}
        for k, c in self.uc.items():
            mdl = chosen[k].model
            lat = self.models[mdl]["p95_latency_s"]
            feas[k] = {
                **feasibility.runtime(c.spec, rt),
                "concurrency": feasibility.concurrency(c.spec, lat),
                "quota": feasibility.quota(c.spec, llm_share[k], rt),
                "data": feasibility.data_rules(c.spec, rt),
                "model": mdl,
                "bedrock_model_id": self.models[mdl]["bedrock_id"] or self.models[c.spec.get("fallback", mdl)]["bedrock_id"],
            }

        email_example = next(({"text": e.text, "team": e.team} for e in live(w.emails) if e.kind == "premium" and e.team == "tarif"), None)
        return {
            "world": w.cfg["name"],
            "volume": {
                "weeks": w.cfg["weeks"],
                "live_from_week": self.live_from,
                "emails": len(w.emails),
                "invoices": len(w.invoices),
                "chats": len(w.chats),
                "letter_week": letter,
                "invoices_billed_eur": round(sum(x.billed for x in w.invoices), 2),
                "invoices_payable_eur": round(sum(w.payable(x) for x in w.invoices), 2),
            },
            "contracts": {
                k: {"name": c.name, "owner": c.owner, "purpose": c.purpose, "candidates": c.candidates, "gate": c.gate} for k, c in self.uc.items()
            },
            "selection": {k: {"trials": [vars(t) for t in v], "chosen": chosen[k].model} for k, v in selection.items()},
            "routing": {"validation": self.routing_validation(), "designs": routing, "drift": drift, "example": email_example},
            "invoices": invoices,
            "assist": {"retrieval": self.retrieval(), "floor": floors[m], "designs": assist},
            "totals": totals,
            "feasibility": feas,
            "gate": gate,
        }


def code_hash() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "src" / "pkvai").rglob("*.py")):
        if "world" not in p.parts:
            h.update(p.read_bytes())
    for p in ["platform.toml", "fees.toml"] + [f"usecases/{x.name}" for x in sorted((ROOT / "config" / "usecases").glob("*.toml"))]:
        h.update((ROOT / "config" / p).read_bytes())
    return h.hexdigest()[:12]


def main() -> None:
    heldout = "--heldout" in sys.argv
    lock = ROOT / "config" / "heldout.lock"
    if heldout and lock.exists():
        raise SystemExit(f"The held-out world was already run ({lock.read_text().strip()}). Measure changes on the dev world.")
    r = Run("heldout" if heldout else "world").run()
    out = ROOT / "reports" / ("heldout.json" if heldout else "dev.json")
    out.write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n")
    if heldout:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "uncommitted"
        lock.write_text(f"commit {rev} code {code_hash()}\n")
    print(
        json.dumps(
            {
                "selection": {k: v["chosen"] for k, v in r["selection"].items()},
                "totals": r["totals"],
                "routing": {k: (v["accuracy"], v["accuracy_on_letter_answers"], v["llm_share"]) for k, v in r["routing"]["designs"].items()},
                "validation": r["routing"]["validation"],
                "drift": r["routing"]["drift"],
                "invoices": {k: {kk: vv for kk, vv in v.items() if kk != "example"} for k, v in r["invoices"].items()},
                "assist": {k: {kk: vv for kk, vv in v.items() if kk != "example"} for k, v in r["assist"]["designs"].items()},
                "retrieval": r["assist"]["retrieval"],
                "floor": r["assist"]["floor"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
