"""Chunk data/policy_docs/*.md into MongoDB policy_chunks (with Voyage embeddings if VOYAGE_API_KEY is set).
Run:  python scripts/ingest_policy.py"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_sync_db  # noqa: E402

AREA_BY_FILE = {
    "grading_system.md": "grading",
    "transcript_requests.md": "transcripts",
    "academic_standing.md": "academic_standing",
    "degree_requirements.md": "degree_requirements",
    "course_substitution.md": "course_substitution",
    "proctoring.md": "proctoring",
}


def chunk_markdown(text: str) -> tuple[str, list[tuple[str, str]]]:
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    title = title_match.group(1).strip() if title_match else "Policy"
    body = re.sub(r"^#\s+.+$", "", text, count=1, flags=re.M)
    parts = re.split(r"^##\s+(.+)$", body, flags=re.M)
    chunks = []
    intro = parts[0].strip()
    if intro:
        chunks.append(("Overview", intro))
    for i in range(1, len(parts), 2):
        section, content = parts[i].strip(), parts[i + 1].strip()
        if content:
            chunks.append((section, content))
    return title, chunks


def main() -> None:
    db = get_sync_db()
    settings = get_settings()
    vo = None
    if settings.voyage_api_key:
        import voyageai
        vo = voyageai.Client(api_key=settings.voyage_api_key)
    db.policy_chunks.delete_many({})
    total = 0
    for path in sorted((ROOT / "data" / "policy_docs").glob("*.md")):
        area = AREA_BY_FILE.get(path.name)
        if not area:
            print(f"skip {path.name} (no feature area mapped)")
            continue
        title, chunks = chunk_markdown(path.read_text(encoding="utf-8"))
        docs = [{"doc": path.name, "title": title, "section": s, "text": t, "feature_area": area} for s, t in chunks]
        if vo and docs:
            vectors = vo.embed([d["text"] for d in docs], model="voyage-3", input_type="document").embeddings
            for d, v in zip(docs, vectors):
                d["embedding"] = v
        if docs:
            db.policy_chunks.insert_many(docs)
        total += len(docs)
        print(f"{path.name}: {len(docs)} chunks ({area})")
    print(f"done: {total} chunks, embeddings={'yes' if vo else 'no (keyword search)'}")


if __name__ == "__main__":
    main()
