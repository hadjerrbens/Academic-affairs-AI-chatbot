"""Data access for grading and transcripts.

The grade scale comes from data/seed/grading_scale.csv. Transcript requests are kept in memory
by default; to use MongoDB, change ONLY the two transcript methods and keep their signatures."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from app.domain.records_engine import normalise_letter

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = REPO_ROOT / "data" / "seed"
PASSING_POINTS = 1.0  # "Pass at 1.0"


def load_grade_scale(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or SEED_DIR / "grading_scale.csv"
    with open(path, newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel adds a hidden marker
        rows = [
            {
                "letter": normalise_letter(row["letter"]),
                "min_pct": float(row["min_percentage"]),
                "max_pct": float(row["max_percentage"]),
                "points": float(row["grade_points"]),
            }
            for row in csv.DictReader(f)
        ]
    return sorted(rows, key=lambda r: -r["min_pct"])


class RecordsRepo:
    def __init__(self, scale_path: Path | None = None) -> None:
        self._scale = load_grade_scale(scale_path)
        self._requests: list[dict[str, Any]] = []
        self._next_id = 1

    # ---- grading
    def get_grade_scale(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._scale]

    def get_grade_points_map(self) -> dict[str, float]:
        """For M2's calculate_gpa: {'A': 4.0, 'A-': 3.7, ...}."""
        return {row["letter"]: row["points"] for row in self._scale}

    @staticmethod
    def passing_points() -> float:
        return PASSING_POINTS

    # ---- transcripts
    def create_transcript_request(
        self, student_id: str, kind: str, delivery: str, fee: int, today: date
    ) -> dict[str, Any]:
        record = {
            "id": self._next_id,
            "student_id": student_id,
            "kind": kind,
            "delivery": delivery,
            "fee": fee,
            "date": today,
            "status": "pending",
        }
        self._next_id += 1
        self._requests.append(record)
        return dict(record)

    def list_transcript_requests(self, student_id: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self._requests if r["student_id"] == student_id]


# ---- module-level functions with the names from the M4 brief, backed by one default repo.
_DEFAULT = RecordsRepo()


def get_grade_scale() -> list[dict[str, Any]]:
    return _DEFAULT.get_grade_scale()


def get_grade_points_map() -> dict[str, float]:
    return _DEFAULT.get_grade_points_map()


def passing_points() -> float:
    return PASSING_POINTS


def create_transcript_request(student_id: str, kind: str, delivery: str, fee: int, today: date):
    return _DEFAULT.create_transcript_request(student_id, kind, delivery, fee, today)


def list_transcript_requests(student_id: str):
    return _DEFAULT.list_transcript_requests(student_id)
