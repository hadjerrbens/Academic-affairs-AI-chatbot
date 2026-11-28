"""One loader for M2 degree progress and standing.

The CSVs are the approved seed source. Passing db enables MongoDB reads after seeding.
StudentRecord/CompletedCourse are imported from M1's shared_models at call time.
"""
from __future__ import annotations

import csv
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed"


def _csv(name: str, directory: Path):
    with (directory / name).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _as_bool(value):
    return value is True or str(value).strip().lower() == "true"


class ProgressRepo:
    def __init__(self, db=None, seed_dir: Path | None = None):
        self.db = db
        self.seed_dir = Path(seed_dir) if seed_dir else SEED_DIR

    def _read(self, collection: str, filters=None):
        filters = filters or {}
        if self.db is not None:
            return list(self.db[collection].find(filters, {"_id": 0}))
        # M5 owns enrollments.csv: M2 can be tested before that slice is merged.
        if collection == "enrollments" and not (self.seed_dir / "enrollments.csv").exists():
            return []
        return [row for row in _csv(collection + ".csv", self.seed_dir)
                if all(str(row.get(key)) == str(value) for key, value in filters.items())]

    def get_program(self, program_code: str):
        rows = self._read("programs", {"program_code": program_code})
        return rows[0] if rows else None

    def get_requirement_groups(self, program_code: str):
        """Groups stay in the approved CSV row order; no invented priority column."""
        memberships = self._read("requirement_group_courses")
        by_group = {}
        for row in memberships:
            by_group.setdefault(row["group_id"], []).append(row["course_code"])
        result = []
        for row in self._read("requirement_groups", {"program_code": program_code}):
            group = dict(row)
            group["courses"] = by_group.get(row["group_id"], [])
            group["min_courses"] = int(row["min_courses"])
            group["min_credits"] = int(row["min_credits"])
            group["min_grade_points"] = float(row["min_grade_points"])
            result.append(group)
        return result

    def get_standing_policy(self):
        rows = self._read("standing_policies")
        if not rows:
            raise ValueError("Standing policy is missing")
        policy = dict(rows[0])
        for key in ("good_standing_min_gpa", "warning_min_gpa", "probation_min_gpa"):
            policy[key] = float(policy[key])
        policy["appeal_window_days"] = int(policy["appeal_window_days"])
        for key in ("blocks_registration", "blocks_transcripts"):
            policy[key] = [s.strip() for s in str(policy.get(key, "")).split(",") if s.strip()]
        return policy

    def get_student_record(self, student_id: str):
        from app.domain.shared_models import StudentRecord, CompletedCourse

        rows = self._read("students", {"student_id": student_id})
        if not rows:
            return None
        student = rows[0]
        completed = [CompletedCourse(
            student_id=student_id,
            course_code=row["course_code"],
            credits=int(row["credits"]),
            grade=str(row["grade"]),
            grade_points=(float(row["grade_points"]) if str(row.get("grade_points", "")).strip() else None),
            term=row["term"],
            status=str(row["status"]).upper(),
            is_repeat=_as_bool(row.get("is_repeat", False)),
        ) for row in self._read("student_courses", {"student_id": student_id})]
        enrolled = self._read("enrollments", {"student_id": student_id})
        sections = [row["section_code"] for row in enrolled
                    if str(row.get("status", "")).lower() in ("enrolled", "active")]
        return StudentRecord(
            student_id=student_id, program_code=student.get("program_code") or None,
            year=int(student.get("year") or 1), completed=completed,
            current_section_codes=list(dict.fromkeys(sections)),
        )


_DEFAULT = ProgressRepo()


def get_program(program_code):
    return _DEFAULT.get_program(program_code)


def get_requirement_groups(program_code):
    return _DEFAULT.get_requirement_groups(program_code)


def get_standing_policy():
    return _DEFAULT.get_standing_policy()


def get_student_record(student_id):
    return _DEFAULT.get_student_record(student_id)
