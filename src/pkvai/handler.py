"""One container image for every use case. On Lambda, `lambda_handler` takes an SQS batch; on Fargate, `worker`
polls the same queue. USECASE picks the use case; the model reads, code decides, and the result goes to S3."""

from __future__ import annotations

import json
import os
import pickle

from . import settings
from .usecases.assist import ClauseIndex, Embedder, grounded
from .usecases.invoices import ReadLine, mismatched, needs_reason, settle


def handle(usecase: str, body: dict, deps: dict) -> dict:
    p = settings.platform()
    if usecase == "email-routing":
        router = deps["router"]
        teams, conf = router.predict([body["text"]])
        if conf[0] >= p["routing"]["confidence_floor"]:
            return {"team": teams[0], "by": "classifier", "confidence": round(float(conf[0]), 3)}
        return {"team": deps["small"].route(body["text"]), "by": "small model"}
    if usecase == "invoice-check":
        read = deps["small"].read_invoice(deps["fetch"](body["key"]))
        lines = [ReadLine(x["code"], x["factor"], x["amount"], x["reason"], read["fee_agreement"], x.get("count") or 1) for x in read["lines"]]
        if any(None in (x.code, x.factor, x.amount) for x in lines) or sum(x.amount for x in lines) > body.get("high_value_eur", 1500):
            return {"to_person": True, "why": "unreadable or high value"}
        fees = settings.fees()
        if mismatched(lines, fees) or needs_reason(lines, fees):
            again = deps["large"].read_invoice(deps["fetch"](body["key"]))
            lines = [ReadLine(x["code"], x["factor"], x["amount"], x["reason"], again["fee_agreement"], x.get("count") or 1) for x in again["lines"]]
            if mismatched(lines, fees) and again["lines"] != read["lines"]:
                return {"to_person": True, "why": "two readings disagree and neither adds up"}
        s = settle(lines, fees)
        return {"to_person": False, "payable": s.payable, "notes": s.notes}
    if usecase == "chat-assist":
        idx: ClauseIndex = deps["index"]
        k = p["assist"]["top_k"]
        rw = deps["small"].rewrite(body["question"])
        best: dict[str, float] = {}
        for i, score in idx.search(body["question"], k) + idx.search(rw, k):
            best[i] = max(score, best.get(i, -1.0))
        hits = sorted(best.items(), key=lambda kv: -kv[1])[:k]
        if hits[0][1] < body.get("floor", 0.125):
            return {"draft": None, "why": "no clause close enough"}
        ids = [i for i, _ in hits]
        d = deps["small"].draft(body["question"], {i: idx.text[i] for i in ids})
        if not grounded(d["cites"], d["fact"], ids, idx.text):
            return {"draft": None, "why": "draft not backed by the clauses it was given"}
        return {"draft": d["answer"], "cites": d["cites"]}
    raise ValueError(f"unknown use case {usecase}")


def _deps() -> dict:  # pragma: no cover - only in the deployed image
    import boto3

    from .llm import Bedrock

    s3 = boto3.client("s3")
    bucket = os.environ["BUCKET"]
    small, large = os.environ["MODEL_IDS"].split(",")[:2]
    deps = {"small": Bedrock(small), "large": Bedrock(large), "fetch": lambda key: s3.get_object(Bucket=bucket, Key=key)["Body"].read()}
    if os.environ["USECASE"] == "email-routing":
        deps["router"] = pickle.loads(s3.get_object(Bucket=bucket, Key="model/router.pkl")["Body"].read())
    if os.environ["USECASE"] == "chat-assist":
        clauses = json.loads(s3.get_object(Bucket=bucket, Key="tariff/clauses.json")["Body"].read())
        deps["index"] = ClauseIndex([tuple(c) for c in clauses], Embedder(settings.platform()["assist"]["embed_dim"]))
    return deps


def lambda_handler(event: dict, context=None) -> dict:  # pragma: no cover
    deps, out = _deps(), []
    for record in event.get("Records", []):
        out.append(handle(os.environ["USECASE"], json.loads(record["body"]), deps))
    return {"results": out}
