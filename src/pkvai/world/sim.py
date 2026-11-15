"""The simulated insurer: emails, invoices and chat questions over 26 weeks, the true answer for each, and how the
models misread them. Every draw is keyed by the item and the mistake, never by the design that asks."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

from ..keyed import pick, u
from ..settings import CONFIG
from .text import CLAUSES, CLOSING, FILLER, GREETING, PHRASES, PREMIUM, QUESTIONS, TEAMS

DOCTORS = ["Dr. Weber", "Dr. Schmidt", "Dr. Yilmaz", "Dr. Hoffmann", "Dr. Nowak", "Dr. Becker", "Praxis am Markt", "MVZ Isartor"]
REASONS = [
    "erhöhter Zeitaufwand wegen komplexer Anamnese",
    "schwierige Untersuchung bei Mehrfacherkrankung",
    "überdurchschnittlicher Schwierigkeitsgrad",
    "erschwerte Bedingungen bei Angstpatientin",
]


@dataclass
class Email:
    id: str
    week: int
    day: int
    customer: str
    lang: str
    text: str
    team: str
    kind: str  # "usual" or "premium" (answers the premium-adjustment letter)


@dataclass
class Line:
    code: str
    factor: float
    amount: float
    reason: bool
    agreement: bool
    count: int = 1


@dataclass
class Invoice:
    id: str
    week: int
    customer: str
    doctor: str
    date: str
    lines: list[Line]
    duplicate_of: str | None = None
    excluded_pair: bool = False

    @property
    def billed(self) -> float:
        return round(sum(line.amount for line in self.lines), 2)


@dataclass
class Chat:
    id: str
    week: int
    text: str
    clause: str
    paraphrased: bool


@dataclass
class Draft:
    cites: list[str]
    fact: str | None  # None: the model declined to answer
    kind: str  # "right", "wrong_fact", "invented", "wrong_source", "declined", "memory"


@dataclass
class World:
    cfg: dict
    fees: dict
    emails: list[Email] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)
    chats: list[Chat] = field(default_factory=list)

    @classmethod
    def load(cls, name: str = "world") -> World:
        cfg = tomllib.loads((CONFIG / f"{name}.toml").read_text())
        fees = tomllib.loads((CONFIG / "fees.toml").read_text())
        w = cls(cfg, fees)
        w._emails()
        w._invoices()
        w._chats()
        return w

    # ------------------------------------------------------------------ emails
    def _emails(self) -> None:
        c, s = self.cfg["emails"], self.cfg["seed"]
        n = 0
        threads: list[tuple[str, str, str, str, str]] = []  # customer, lang, team, kind, text
        for week in range(1, self.cfg["weeks"] + 1):
            for k in range(c["per_week"]):
                key = (s, "email", week, k)
                day = int(u(*key, "day") * 7)
                if threads and u(*key, "follow") < c["thread_follow_up"]:
                    cust, lang, team, kind, text = pick(threads[-400:], *key, "thread")
                    text = self._follow_up(text, lang, key)
                else:
                    cust = f"K{int(u(*key, 'cust') * 60000):05d}"
                    lang = "en" if u(*key, "lang") < c["english_share"] else "de"
                    if week >= c["premium_letter_week"] and u(*key, "premium") < c["premium_letter_share"]:
                        kind = "premium"
                        team = self._choose(c["premium_intents"], *key, "intent")
                        text = self._premium_text(lang, team, key)
                    else:
                        kind = "usual"
                        team = pick(TEAMS, *key, "team")
                        text = self._usual_text(lang, team, key)
                threads.append((cust, lang, team, kind, text))
                self.emails.append(Email(f"E{n:06d}", week, day, cust, lang, text, team, kind))
                n += 1

    @staticmethod
    def _choose(weights: dict, *key) -> str:
        r, acc = u(*key), 0.0
        for k, w in weights.items():
            acc += w
            if r < acc:
                return k
        return k

    def _usual_text(self, lang: str, team: str, key) -> str:
        parts = [pick(GREETING[lang], *key, "g") + ","]
        for i in range(1 + int(u(*key, "np") * 2)):
            parts.append(pick(PHRASES[lang][team], *key, "p", i) + ".")
        if u(*key, "distract") < self.cfg["emails"]["distractor_phrases"]:
            other = pick([t for t in TEAMS if t != team], *key, "dt")
            parts.insert(1 if u(*key, "dpos") < 0.5 else len(parts), pick(PHRASES[lang][other], *key, "dp") + ", aber")
        parts.append(pick(FILLER[lang], *key, "f") + ".")
        parts.append(pick(CLOSING[lang], *key, "c"))
        return " ".join(parts)

    def _premium_text(self, lang: str, team: str, key) -> str:
        p = PREMIUM[lang]
        parts = [pick(GREETING[lang], *key, "g") + ",", pick(p["opener"], *key, "o") + ":", pick(p[team], *key, "i") + "."]
        if u(*key, "second") < 0.4:
            parts.append(pick(p[team], *key, "i2") + ".")
        parts.append(pick(CLOSING[lang], *key, "c"))
        return " ".join(parts)

    @staticmethod
    def _follow_up(text: str, lang: str, key) -> str:
        add = {"de": ["Ich frage noch einmal nach.", "Nachtrag:", "Bitte melden Sie sich."], "en": ["Following up.", "Again:", "Please reply."]}
        return f"{pick(add[lang], *key, 'fu')} {text}"

    # ---------------------------------------------------------------- invoices
    def _invoices(self) -> None:
        c, s, f = self.cfg["invoices"], self.cfg["seed"], self.fees
        codes = list(f["codes"])
        n = 0
        for week in range(1, self.cfg["weeks"] + 1):
            for k in range(c["per_week"]):
                key = (s, "inv", week, k)
                inv_id = f"R{n:06d}"
                if self.invoices and u(*key, "dup") < c["duplicate_share"]:
                    orig = pick(self.invoices[-300:], *key, "dupof")
                    self.invoices.append(
                        Invoice(
                            inv_id,
                            week,
                            orig.customer,
                            orig.doctor,
                            orig.date,
                            [Line(**vars(x)) for x in orig.lines],
                            duplicate_of=orig.id,
                            excluded_pair=orig.excluded_pair,
                        )
                    )
                    n += 1
                    continue
                nlines = c["lines_min"] + int(u(*key, "nl") * (c["lines_max"] - c["lines_min"] + 1))
                chosen: list[str] = []
                for i in range(nlines * 3):
                    code = pick(codes, *key, "code", i)
                    if code not in chosen and not any({code, o} == set(p) for p in f["excluded_pairs"] for o in chosen):
                        chosen.append(code)
                    if len(chosen) == nlines:
                        break
                excluded = False
                if u(*key, "excl") < c["excluded_pair_share"]:
                    pair = pick(f["excluded_pairs"], *key, "pair")
                    chosen = [x for x in chosen if x not in pair] + list(pair)
                    excluded = True
                big = u(*key, "big") < 0.03  # a long course of treatment, billed at once
                lines = [self._line(code, key, i, 8 + int(u(*key, "cnt", i) * 18) if big else 1) for i, code in enumerate(chosen)]
                date = f"2026-{1 + (week - 1) // 4 % 12:02d}-{1 + int(u(*key, 'd') * 27):02d}"
                self.invoices.append(
                    Invoice(inv_id, week, f"K{int(u(*key, 'cust') * 60000):05d}", pick(DOCTORS, *key, "doc"), date, lines, excluded_pair=excluded)
                )
                n += 1

    def _line(self, code: str, key, i: int, count: int) -> Line:
        c, f = self.cfg["invoices"], self.fees
        sec = f["sections"][f["codes"][code]["section"]]
        factor, reason, agreement = sec["threshold"], False, False
        if u(*key, "above", i) < c["above_threshold_share"]:
            factor = round(sec["threshold"] + (sec["maximum"] - sec["threshold"]) * (0.4 + 0.6 * u(*key, "fac", i)), 1)
            reason = u(*key, "reason", i) >= c["missing_reason_share"]
        if u(*key, "abovemax", i) < c["above_max_share"]:
            factor = round(sec["maximum"] + (f["tariff_max_factor"] - sec["maximum"]) * u(*key, "facmax", i), 1)
            agreement = u(*key, "agree", i) < c["fee_agreement_share"]
            reason = True
        amount = round(f["codes"][code]["points"] * f["point_value_eur"] * factor * count, 2)
        if u(*key, "arith", i) < c["arithmetic_error_share"]:
            amount = round(amount * (1.1 + 0.4 * u(*key, "arithx", i)), 2)
        return Line(code, factor, amount, reason, agreement, count)

    def payable(self, inv: Invoice) -> float:
        """What the tariff really owes for an invoice."""
        if inv.duplicate_of:
            return 0.0
        f = self.fees
        drop: set[int] = set()
        codes = [x.code for x in inv.lines]
        for a, b in f["excluded_pairs"]:
            if a in codes and b in codes:
                ia, ib = codes.index(a), codes.index(b)
                drop.add(ia if f["codes"][a]["points"] < f["codes"][b]["points"] else ib)
        total = 0.0
        for i, x in enumerate(inv.lines):
            if i in drop:
                continue
            sec = f["sections"][f["codes"][x.code]["section"]]
            fac = x.factor
            if fac > sec["maximum"]:
                fac = min(fac, f["tariff_max_factor"]) if x.agreement else (sec["maximum"] if x.reason else sec["threshold"])
            elif fac > sec["threshold"] and not x.reason:
                fac = sec["threshold"]
            total += min(x.amount, round(f["codes"][x.code]["points"] * f["point_value_eur"] * fac * x.count, 2))
        return round(total, 2)

    def render(self, inv: Invoice) -> str:
        rows = [f"Rechnung {inv.doctor}, Behandlung am {inv.date}"]
        for x in inv.lines:
            times = f"{x.count} x " if x.count > 1 else ""
            rows.append(f"GOÄ {x.code}  {times}Faktor {str(x.factor).replace('.', ',')}  {x.amount:.2f} €".replace(".", ",", 1))
            if x.reason:
                rows.append(f"  Begründung: {REASONS[int(float(x.factor) * 10) % len(REASONS)]}")
        if any(x.agreement for x in inv.lines):
            rows.append("Honorarvereinbarung nach § 2 GOÄ liegt bei.")
        rows.append(f"Summe {inv.billed:.2f} €".replace(".", ","))
        return "\n".join(rows)

    # ------------------------------------------------------------------- chats
    def _chats(self) -> None:
        c, s = self.cfg["chats"], self.cfg["seed"]
        ids = [x[0] for x in CLAUSES]
        n = 0
        for week in range(1, self.cfg["weeks"] + 1):
            for k in range(c["per_week"]):
                key = (s, "chat", week, k)
                clause = pick(ids, *key, "clause")
                para = u(*key, "para") < c["paraphrase"]
                self.chats.append(Chat(f"C{n:06d}", week, QUESTIONS[clause][1 if para else 0], clause, para))
                n += 1

    # ------------------------------------------------------- the models' work
    def _llm(self, model: str) -> dict:
        return self.cfg["llm"][model]

    def route(self, e: Email, model: str) -> str:
        """The team a model sends an email to."""
        err = self._llm(model)["route_error_new_kind" if e.kind == "premium" else "route_error"]
        if u(self.cfg["seed"], "route", e.id, model) < err:
            return pick([t for t in TEAMS if t != e.team], self.cfg["seed"], "route_to", e.id, model)
        return e.team

    def read(self, inv: Invoice, model: str) -> list[Line]:
        """The lines a model reads off an invoice's image."""
        g, s, out = self._llm(model), self.cfg["seed"], []
        codes = list(self.fees["codes"])
        for i, x in enumerate(inv.lines):
            code, factor, amount, reason = x.code, x.factor, x.amount, x.reason
            if u(s, "code", inv.id, i, model) < g["code_misread"]:
                code = pick([c for c in codes if c != x.code], s, "code_to", inv.id, i, model)
            if u(s, "factor", inv.id, i, model) < g["factor_misread"]:
                factor = {2.3: 3.2, 1.8: 1.3, 1.15: 1.5}.get(x.factor, round(x.factor + 0.5, 1))
            if u(s, "amount", inv.id, i, model) < g["amount_misread"]:
                amount = round(amount * 10, 2) if u(s, "amtx", inv.id, i) < 0.5 else round(amount / 10, 2)
            if x.reason and u(s, "reason", inv.id, i, model) < g["reason_missed"]:
                reason = False
            out.append(Line(code, factor, amount, reason, x.agreement, x.count))
        return out

    def llm_settles(self, inv: Invoice, model: str) -> float:
        """The amount a model pays when it reads the invoice and applies the fee rules itself."""
        g, s = self._llm(model), self.cfg["seed"]
        if inv.duplicate_of and u(s, "dupslip", inv.id, model) < 0.5:
            return inv.billed
        truth = self.payable(inv)
        if u(s, "ruleslip", inv.id, model) < g["rule_slip"] and truth != inv.billed:
            if u(s, "slipway", inv.id) < 0.5:
                return inv.billed  # waved the whole invoice through
            f = self.fees  # too strict: every line cut back to the threshold factor, reasons or not
            return round(
                sum(
                    min(
                        x.amount,
                        round(
                            f["codes"][x.code]["points"] * f["point_value_eur"] * f["sections"][f["codes"][x.code]["section"]]["threshold"] * x.count,
                            2,
                        ),
                    )
                    for x in inv.lines
                ),
                2,
            )
        lines = self.read(inv, model)
        misread = sum(abs(a.amount - b.amount) for a, b in zip(lines, inv.lines, strict=True))
        return round(truth + (misread if u(s, "misreadpay", inv.id) < 0.5 else 0.0), 2)

    def draft(self, chat: Chat, model: str, retrieved: list[str] | None) -> Draft:
        """A model's answer to a chat question, from the clauses it was given or from memory."""
        g, s = self._llm(model), self.cfg["seed"]
        facts = {x[0]: x[3] for x in CLAUSES}
        if retrieved is None:
            if u(s, "memory", chat.id, model) < g["answer_from_memory_right"]:
                return Draft([], facts[chat.clause], "memory")
            return Draft([], pick([f for c, f in facts.items() if c != chat.clause], s, "memwrong", chat.id, model), "invented")
        if chat.clause in retrieved:
            if u(s, "groundedwrong", chat.id, model) < g["answer_wrong_when_grounded"]:
                return Draft([chat.clause], pick([f for c, f in facts.items() if c != chat.clause], s, "gw", chat.id), "wrong_fact")
            return Draft([chat.clause], facts[chat.clause], "right")
        r = u(s, "ungrounded", chat.id, model)
        h = g["hallucinate_when_ungrounded"]
        if r < h * 0.6:
            return Draft([retrieved[0]], pick([f for c, f in facts.items() if c not in retrieved], s, "inv", chat.id), "invented")
        if r < h:
            return Draft([retrieved[0]], facts[retrieved[0]], "wrong_source")
        return Draft([], None, "declined")

    def rewrite(self, chat: Chat, model: str) -> str:
        """A model asked to restate the customer's question in the tariff's own words."""
        if chat.paraphrased and u(self.cfg["seed"], "rewrite", chat.id, model) < self._llm(model)["rewrites_in_tariff_words"]:
            return QUESTIONS[chat.clause][0]
        return chat.text

    def right_answer(self, chat: Chat, draft: Draft) -> bool:
        return draft.fact == dict((x[0], x[3]) for x in CLAUSES)[chat.clause]

    def agent_catches(self, chat: Chat) -> bool:
        return u(self.cfg["seed"], "agentcatch", chat.id) < self.cfg["people"]["agent_catches_wrong_draft"]
