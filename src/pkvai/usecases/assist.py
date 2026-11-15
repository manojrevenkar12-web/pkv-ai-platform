"""Chat assist: find the tariff clauses for a question, let a model draft, and check the draft against the clauses."""

from __future__ import annotations

import re
import zlib

import numpy as np

WORD = re.compile(r"\w+", re.UNICODE)


class Embedder:
    """Hashed character n-grams and words: small, deterministic, good enough to show where retrieval fails.
    In production the same interface wraps a Bedrock embedding model and pgvector."""

    def __init__(self, dim: int):
        self.dim = dim

    def __call__(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        t = f" {text.lower()} "
        grams = [t[i : i + n] for n in (3, 4, 5) for i in range(len(t) - n + 1)] + WORD.findall(t)
        for g in grams:
            h = zlib.crc32(g.encode())
            v[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        return v / (np.linalg.norm(v) + 1e-9)


class ClauseIndex:
    def __init__(self, clauses: list[tuple[str, str, str]], embed: Embedder):
        self.ids = [c[0] for c in clauses]
        self.text = {c[0]: f"{c[1]}. {c[2]}" for c in clauses}
        self.embed = embed
        self.M = np.stack([embed(self.text[i]) for i in self.ids])

    def search(self, question: str, k: int) -> list[tuple[str, float]]:
        s = self.M @ self.embed(question)
        order = np.argsort(-s)[:k]
        return [(self.ids[i], float(s[i])) for i in order]


def grounded(cites: list[str], fact: str | None, retrieved: list[str], text: dict[str, str]) -> bool:
    """A draft goes to the agent only if it cites a clause it was given and states what that clause says."""
    return bool(fact) and bool(cites) and all(c in retrieved for c in cites) and any(fact in text[c] for c in cites)
