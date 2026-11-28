"""Enrollment lookups for the exam schedule (async, Motor). Seam M3 expects: get_student_sections(student_id, term)."""
from types import SimpleNamespace

from app.core import db as dbmod


async def get_student_sections(student_id: str, term: str):
    cursor = dbmod.get_db().enrollments.find({"student_id": student_id, "term": term, "status": "enrolled"}, {"_id": 0})
    rows = await cursor.to_list(length=None)
    return [SimpleNamespace(code=r["section_code"], term=r["term"]) for r in rows]
