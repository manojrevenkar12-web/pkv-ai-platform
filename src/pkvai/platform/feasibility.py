"""Check a use case's assumptions before anyone builds it: where it runs, what it costs to host, whether the model
quota holds at peak, and what its data demands. The answers become the design note and the Terraform inputs."""

from __future__ import annotations

import math


def runtime(c: dict, rt: dict) -> dict:
    d = c["deploy"]
    limits = []
    if d["processing_s"] * rt["safety_factor"] > rt["lambda_max_s"]:
        limits.append("processing too long for Lambda")
    if d["memory_mb"] > rt["lambda_max_memory_mb"]:
        limits.append("needs more memory than Lambda offers")
    gb = d["memory_mb"] / 1024
    lam_day = d["volume_per_day"] * (d["processing_s"] * gb * rt["lambda_eur_per_gb_s"] + rt["lambda_eur_per_million_requests"] / 1e6)
    far_day = 24 * rt["fargate_min_tasks"] * (rt["fargate_vcpu"] * rt["fargate_eur_per_vcpu_hour"] + gb * rt["fargate_eur_per_gb_hour"])
    per_case_lam = lam_day / d["volume_per_day"]
    crossover = math.ceil(far_day / per_case_lam)
    choice = "fargate" if limits or lam_day > far_day else "lambda"
    return {
        "runtime": choice,
        "why": "; ".join(limits)
        or (f"Lambda is cheaper until about {crossover:,} cases a day" if choice == "lambda" else "steady volume is cheaper always on"),
        "lambda_eur_per_month": round(lam_day * 30, 2),
        "fargate_eur_per_month": round(far_day * 30, 2),
        "crossover_cases_per_day": crossover,
        "input_via_s3": d["max_input_mb"] > rt["lambda_max_sync_payload_mb"],
    }


def concurrency(c: dict, latency_s: float) -> int:
    d = c["deploy"]
    return max(1, math.ceil(d["peak_per_minute"] / 60 * (d["processing_s"] + latency_s) * 2))


def quota(c: dict, llm_share: float, rt: dict) -> dict:
    tpm = c["deploy"]["peak_per_minute"] * llm_share * (c["tokens"]["in"] + c["tokens"]["out"])
    share = tpm / rt["bedrock_tokens_per_minute_quota"]
    return {"tokens_per_minute_at_peak": round(tpm), "quota_share": round(share, 3), "ask_for_increase": share > rt["quota_headroom"]}


def data_rules(c: dict, rt: dict) -> list[str]:
    out = []
    if c["data"]["personal"]:
        out.append(f"model calls stay in {rt['region']}: no cross-region inference profile outside the EU")
        out.append("prompts and outputs are not logged in plain text; the audit log keeps ids and hashes")
    if c["data"]["health"]:
        out.append("health data: encrypted with a customer-managed KMS key, access only through the use case's own role")
    out.append(f"inputs and outputs deleted after {c['data']['retention_days']} days by an S3 lifecycle rule")
    return out
