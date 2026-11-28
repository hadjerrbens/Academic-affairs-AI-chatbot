"""Load the seed CSVs into MongoDB. Used by scripts/seed_db.py and by the tests (with a fake db).
Values stay as the CSV strings: the repos already parse them (int/float/date/bool) when they read.
Only exam_rules lists are split, because M3's repo expects lists there."""
from __future__ import annotations

import csv
import json
from pathlib import Path

COLLECTIONS = [  # (collection, csv file, unique/lookup index)
    "users", "students", "student_courses", "programs", "requirement_groups", "requirement_group_courses",
    "standing_policies", "courses", "sections", "enrollments", "calendar_events", "exam_schedules",
    "exam_rules", "grading_scale", "substitution_rules", "proctoring_policies",
]
INDEXES = {
    "users": [("email", True), ("user_id", True)],
    "students": [("student_id", True)],
    "student_courses": [("student_id", False)],
    "enrollments": [("student_id", False), ("section_code", False)],
    "sections": [("section_code", True)],
    "courses": [("course_code", True)],
    "exam_schedules": [("section_code", False)],
    "calendar_events": [("term", False)],
}
LIST_FIELDS = {"exam_rules": ("allowed_items", "forbidden_items")}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def seed_all(db, seed_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in COLLECTIONS:
        rows = read_csv(seed_dir / f"{name}.csv")
        for field in LIST_FIELDS.get(name, ()):
            for row in rows:
                row[field] = [x.strip() for x in str(row.get(field, "")).split("|") if x.strip()]
        if name == "users":
            for row in rows:
                row["email"] = row["email"].strip().lower()
        db[name].delete_many({})
        if rows:
            db[name].insert_many(rows)
        for field, unique in INDEXES.get(name, []):
            db[name].create_index(field, unique=unique)
        counts[name] = len(rows)
    return counts


def check_against_manifest(counts: dict[str, int], seed_dir: Path) -> list[str]:
    manifest = json.loads((seed_dir / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    for name, expected in manifest.get("counts", {}).items():
        if counts.get(name) != expected:
            problems.append(f"{name}: expected {expected}, loaded {counts.get(name)}")
    return problems
