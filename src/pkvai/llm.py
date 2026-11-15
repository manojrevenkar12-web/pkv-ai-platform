"""The live model calls, through Amazon Bedrock's Converse API with a forced tool, so every answer is structured.
The evaluation simulates these calls; this module is what a deployed use case runs."""

from __future__ import annotations

import json
from pathlib import Path

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"

ROUTE = {
    "type": "object",
    "properties": {"team": {"type": "string", "enum": ["leistung", "beitrag", "vertrag", "tarif", "kuendigung", "beschwerde", "gesundheit"]}},
    "required": ["team"],
}
INVOICE = {
    "type": "object",
    "properties": {
        "doctor": {"type": "string"},
        "date": {"type": "string"},
        "fee_agreement": {"type": "boolean"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": ["string", "null"]},
                    "count": {"type": ["integer", "null"]},
                    "factor": {"type": ["number", "null"]},
                    "amount": {"type": ["number", "null"]},
                    "reason": {"type": "boolean"},
                },
                "required": ["code", "count", "factor", "amount", "reason"],
            },
        },
    },
    "required": ["lines", "fee_agreement"],
}
DRAFT = {
    "type": "object",
    "properties": {
        "answer": {"type": ["string", "null"]},
        "cites": {"type": "array", "items": {"type": "string"}},
        "fact": {"type": ["string", "null"]},
    },
    "required": ["answer", "cites", "fact"],
}
REWRITE = {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}


class Bedrock:
    def __init__(self, model_id: str, region: str = "eu-central-1", client=None):
        if client is None:
            import boto3  # only where it runs for real

            client = boto3.client("bedrock-runtime", region_name=region)
        self.client, self.model_id = client, model_id

    def call(self, prompt: str, content: list[dict], tool: str, schema: dict, max_tokens: int = 800) -> dict:
        r = self.client.converse(
            modelId=self.model_id,
            system=[{"text": (PROMPTS / f"{prompt}.md").read_text()}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"temperature": 0, "maxTokens": max_tokens},
            toolConfig={"tools": [{"toolSpec": {"name": tool, "inputSchema": {"json": schema}}}], "toolChoice": {"tool": {"name": tool}}},
        )
        for block in r["output"]["message"]["content"]:
            if "toolUse" in block:
                return block["toolUse"]["input"]
        raise ValueError(f"no {tool} call in the response: {json.dumps(r)[:300]}")

    def route(self, email: str) -> str:
        return self.call("route", [{"text": f"<email>\n{email}\n</email>"}], "route", ROUTE, 50)["team"]

    def read_invoice(self, image: bytes, fmt: str = "png") -> dict:
        return self.call("read_invoice", [{"image": {"format": fmt, "source": {"bytes": image}}}], "invoice", INVOICE, 1500)

    def rewrite(self, question: str) -> str:
        return self.call("rewrite", [{"text": question}], "rewrite", REWRITE, 120)["question"]

    def draft(self, question: str, clauses: dict[str, str]) -> dict:
        given = "\n".join(f"<clause id='{k}'>{v}</clause>" for k, v in clauses.items())
        return self.call("draft", [{"text": f"{given}\n<question>{question}</question>"}], "draft", DRAFT, 400)
