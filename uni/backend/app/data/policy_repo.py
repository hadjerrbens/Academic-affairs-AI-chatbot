"""Data access for substitutions and proctoring (M5). Reads MongoDB when given a sync db, else the seed CSVs."""
from __future__ import annotations

import csv
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed"


def _split(value) -> list[str]:
    return [x.strip() for x in str(value or "").split("|") if x.strip()]


class PolicyRepo:
    def __init__(self, db=None, seed_dir: Path | None = None) -> None:
        self.db = db
        self.seed_dir = Path(seed_dir) if seed_dir else SEED_DIR

    def _rows(self, name: str) -> list[dict]:
        if self.db is not None:
            return list(self.db[name].find({}, {"_id": 0}))
        path = self.seed_dir / f"{name}.csv"
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def substitution_rules(self) -> dict[str, dict]:
        rules = {}
        for row in self._rows("substitution_rules"):
            rules[row["target_course"].upper()] = {
                "rule_id": row.get("rule_id"),
                "target": row["target_course"].upper(),
                "accepted": [c.upper() for c in _split(row["accepted_substitutes"])],
                "min_grade_points": float(row["min_grade_points"]),
                "min_grade_letter": row.get("min_grade_letter", ""),
                "min_credits": int(float(row["min_credits"])),
                "advisor_note": row.get("advisor_note", ""),
                "documents": _split(row.get("required_documents")),
            }
        return rules

    def proctoring_policies(self) -> dict[str, dict]:
        return {row["mode"]: row for row in self._rows("proctoring_policies")}

    def exam_modes_for_course(self, course_code: str, term: str | None = None) -> list[str]:
        """Proctoring modes of a course's exams, e.g. ['online'] (from exam_schedules)."""
        modes: list[str] = []
        for row in self._rows("exam_schedules"):
            if row["section_code"].upper().split("-")[0] != course_code.upper():
                continue
            if term and row.get("term") != term:
                continue
            if row["proctoring_type"] not in modes:
                modes.append(row["proctoring_type"])
        return modes
