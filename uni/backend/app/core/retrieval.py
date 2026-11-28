"""RAG over policy docs. Chunks live in MongoDB (policy_chunks); scripts/ingest_policy.py fills them.
retrieve(query, area) -> [{"text", "source", "title", "section"}]   (sync, the shape ChatService expects)"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

log = logging.getLogger(__name__)
_WORD = re.compile(r"[a-z0-9]+")
_COURSE = re.compile(r"\b[A-Z]{2,4}\d{3}\b")
_STOP = {"the", "a", "an", "of", "to", "and", "or", "is", "are", "in", "on", "for", "i", "my", "me", "can", "do", "how", "what"}
MIN_VECTOR_SCORE = 0.3
TOP_K = 3


def keyword_score(query: str, text: str) -> float:
    q = {w for w in _WORD.findall(query.lower()) if w not in _STOP}
    if not q:
        return 0.0
    t = set(_WORD.findall(text.lower()))
    score = len(q & t) / len(q)
    codes = _COURSE.findall(query.upper())
    if codes and any(c in text.upper() for c in codes):
        score += 1.0
    return score


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rank(query: str, chunks: list[dict], query_vector: list[float] | None = None, k: int = TOP_K) -> list[dict]:
    scored = []
    for c in chunks:
        if query_vector is not None and c.get("embedding"):
            s = cosine(query_vector, c["embedding"])
            if s < MIN_VECTOR_SCORE:
                continue
            s += 0.5 * (keyword_score(query, c["text"]) > 1.0)  # exact course code boost
        else:
            s = keyword_score(query, c["text"])
            if s <= 0:
                continue
        scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


class PolicyRetriever:
    def __init__(self, db, voyage_api_key: str = "") -> None:
        self.db = db  # sync PyMongo database
        self._vo = None
        if voyage_api_key:
            try:
                import voyageai
                self._vo = voyageai.Client(api_key=voyage_api_key)
            except Exception:
                log.warning("Voyage unavailable; retrieval is keyword-only")

    def embed_query(self, query: str) -> list[float] | None:
        if self._vo is None:
            return None
        try:
            return self._vo.embed([query], model="voyage-3", input_type="query").embeddings[0]
        except Exception:
            log.warning("Voyage embedding failed; falling back to keyword search")
            return None

    def retrieve(self, query: str, area: str) -> list[dict[str, Any]]:
        filt = {"feature_area": area} if area else {}
        chunks = list(self.db.policy_chunks.find(filt, {"_id": 0}))
        best = rank(query, chunks, self.embed_query(query) if chunks else None)
        return [{"text": c["text"], "source": f"{c['title']} - {c['section']}",
                 "title": c["title"], "section": c["section"]} for c in best]

    __call__ = retrieve
