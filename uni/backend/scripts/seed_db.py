"""Load data/seed/*.csv into MongoDB, then check the counts against manifest.json.
Run from the repo root:
    python backend/scripts/seed_db.py
    python backend/scripts/ingest_policy.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.db import get_sync_db  # noqa: E402
from app.data.seed_loader import check_against_manifest, seed_all  # noqa: E402

SEED = ROOT / "data" / "seed"

if __name__ == "__main__":
    counts = seed_all(get_sync_db(), SEED)
    for name, n in counts.items():
        print(f"{name:28s} {n}")
    problems = check_against_manifest(counts, SEED)
    if problems:
        print("\nMANIFEST MISMATCH:\n  " + "\n  ".join(problems))
        sys.exit(1)
    print("\nOK: all counts match manifest.json")
