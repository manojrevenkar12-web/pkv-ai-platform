"""Email routing: a word-counting classifier first, a small LLM for what it is unsure of."""

from __future__ import annotations

import re
import zlib

import numpy as np
from scipy import sparse

TOKEN = re.compile(r"\w+", re.UNICODE)
_HASHES: dict[tuple[str, int], list[int]] = {}


def tokens(text: str) -> list[str]:
    words = TOKEN.findall(text.lower())
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]


class Router:
    """Hashed unigrams and bigrams, tf-idf, multinomial logistic regression trained by gradient descent."""

    def __init__(self, teams: list[str], buckets: int, epochs: int, learning_rate: float, l2: float):
        self.teams, self.buckets, self.epochs, self.lr, self.l2 = list(teams), buckets, epochs, learning_rate, l2
        self.idf = np.ones(buckets, dtype=np.float32)
        self.W = np.zeros((buckets, len(teams)), dtype=np.float32)
        self.b = np.zeros(len(teams), dtype=np.float32)
        self.known = np.zeros(buckets, dtype=bool)

    def _hashes(self, text: str) -> list[int]:
        key = (text, self.buckets)
        if key not in _HASHES:
            _HASHES[key] = [zlib.crc32(tok.encode()) % self.buckets for tok in tokens(text)]
        return _HASHES[key]

    def _counts(self, texts: list[str]) -> sparse.csr_matrix:
        rows, cols = [], []
        for i, t in enumerate(texts):
            h = self._hashes(t)
            rows.extend([i] * len(h))
            cols.extend(h)
        data = np.ones(len(rows), dtype=np.float32)
        return sparse.csr_matrix((data, (rows, cols)), shape=(len(texts), self.buckets))

    def _features(self, counts: sparse.csr_matrix) -> sparse.csr_matrix:
        x = counts.multiply(self.idf).tocsr()
        norm = np.sqrt(np.asarray(x.multiply(x).sum(axis=1)).ravel()) + 1e-9
        return sparse.diags(1 / norm) @ x

    def fit(self, texts: list[str], labels: list[str], warm: Router | None = None, epochs: int | None = None) -> Router:
        """Train; with warm, start from another model's weights and run fewer epochs (a nightly retrain)."""
        if warm is not None:
            self.W, self.b = warm.W.copy(), warm.b.copy()
        counts = self._counts(texts)
        df = np.asarray((counts > 0).sum(axis=0)).ravel()
        self.known = df > 0
        self.idf = (np.log((1 + len(texts)) / (1 + df)) + 1).astype(np.float32)
        x = self._features(counts)
        y = np.zeros((len(texts), len(self.teams)), dtype=np.float32)
        y[np.arange(len(texts)), [self.teams.index(t) for t in labels]] = 1
        for _ in range(epochs or self.epochs):
            p = self._softmax(x @ self.W + self.b)
            g = (p - y) / len(texts)
            self.W -= self.lr * (np.asarray(x.T @ g) + self.l2 * self.W)
            self.b -= self.lr * g.sum(axis=0)
        return self

    @staticmethod
    def _softmax(z: np.ndarray) -> np.ndarray:
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def proba(self, texts: list[str]) -> np.ndarray:
        return self._softmax(self._features(self._counts(texts)) @ self.W + self.b)

    def predict(self, texts: list[str]) -> tuple[list[str], np.ndarray]:
        p = self.proba(texts)
        return [self.teams[i] for i in p.argmax(axis=1)], p.max(axis=1)

    def unknown_share(self, texts: list[str]) -> np.ndarray:
        """Share of each email's tokens the model never saw in training: new words show up here before labels do."""
        out = []
        for t in texts:
            idx = self._hashes(t)
            out.append(1 - self.known[idx].mean() if idx else 0.0)
        return np.array(out)
