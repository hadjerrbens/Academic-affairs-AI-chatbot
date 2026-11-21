from dataclasses import dataclass
from typing import Callable

from app.data.enrollment_repo import EnrollmentRepo
from app.domain.registration_rules import (
    RegistrationResult, Verdict, detect_conflicts, evaluate_registration,
)
from app.domain.shared_models import (
    Course, MeetingSlot, Section, StudentRecord, normalise_course_code,
)


@dataclass
class Deps:
    """Everything that comes from other members. Wrap their functions to match."""
    repo: EnrollmentRepo
    get_student_record: Callable[[str], StudentRecord]          # M2
    get_standing: Callable[[str], tuple[bool, str]]             # M2 -> (blocks_registration, reason)
    is_registration_open: Callable[[], bool]                    # M3
    registration_term: Callable[[], str]                        # M3
    detect_exam_conflicts: Callable[[str, str], list[dict]]     # M3 (student_id, term)
    # each exam conflict dict: {"course_a", "course_b", "detail"}


# Tool schemas: NO student_id. The user is ctx.user.
TOOL_SCHEMAS = [
    {
        "name": "check_registration_eligibility",
        "description": "Tell the student if they can register for a course and why. "
                       "Lists the sections with instructor, schedule and seats left.",
        "parameters": {
            "type": "object",
            "properties": {
                "course_code": {"type": "string", "description": "Example: CS101"},
                "section_code": {"type": "string", "description": "Optional. Example: CS101-A"},
            },
            "required": ["course_code"],
        },
    },
    {
        "name": "detect_schedule_conflicts",
        "description": "Find class overlaps and exam clashes in the student's registered courses.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def _fmt_schedule(slots: list[MeetingSlot]) -> str:
    return " | ".join(f"{s.day} {s.start}-{s.end}" + (f" @{s.room}" if s.room else "") for s in slots)


def _section_view(s: Section) -> dict:
    return {
        "code": s.code,
        "instructor": s.instructor,
        "schedule": _fmt_schedule(s.schedule),
        "seats_left": s.seats_left,
    }


def evaluate(deps: Deps, student_id: str, course: Course, section: Section) -> RegistrationResult:
    """Load the facts, then call the pure rules. Used by the tool AND the Register route."""
    term = deps.registration_term()
    student = deps.get_student_record(student_id)
    current = deps.repo.get_student_sections(student_id, term)
    blocks, reason = deps.get_standing(student_id)
    return evaluate_registration(
        course, section, student, current,
        registration_open=deps.is_registration_open(),
        standing_blocks=blocks,
        standing_reason=reason,
    )


# ---------------- tool 1 ----------------
def check_registration_eligibility(deps: Deps, user_id: str, course_code: str,
                                   section_code: str | None = None) -> dict:
    try:
        code = normalise_course_code(course_code)
    except ValueError:
        return {"verdict": "COURSE_NOT_FOUND", "reason": f"'{course_code}' is not a valid course code.",
                "sections": [], "summary": f"'{course_code}' is not a valid course code."}
    try:
        course = deps.repo.get_course(code)
        if course is None:
            msg = f"Course {code} does not exist."
            return {"verdict": "COURSE_NOT_FOUND", "reason": msg, "sections": [], "summary": msg}

        term = deps.registration_term()          # registration_term, NOT current_term
        sections = deps.repo.get_sections(code, term)
        if not sections:
            msg = f"{code} has no sections in {term}."
            return {"verdict": "NO_SECTIONS", "reason": msg, "sections": [], "summary": msg}

        if section_code:
            chosen = [s for s in sections if s.code == section_code.strip().upper()]
            if not chosen:
                msg = f"Section {section_code} does not exist for {code} in {term}."
                return {"verdict": "SECTION_NOT_FOUND", "reason": msg,
                        "sections": [_section_view(s) for s in sections], "summary": msg}
            result = evaluate(deps, user_id, course, chosen[0])
        else:
            results = [evaluate(deps, user_id, course, s) for s in sections]
            # best case: any eligible section; otherwise the first problem found
            result = next((r for r in results if r.verdict == Verdict.ELIGIBLE), results[0])

        summary = f"{code} ({term}): {result.verdict.value}. {result.reason}"
        if result.warnings:
            summary += " " + " ".join(result.warnings)
        return {
            "verdict": result.verdict.value,
            "reason": result.reason,
            "sections": [_section_view(s) for s in sections],
            "summary": summary,
        }
    except Exception:
        msg = "I could not check registration right now. Please try again."
        return {"verdict": "ERROR", "reason": msg, "sections": [], "summary": msg}


# ---------------- tool 2 ----------------
def detect_schedule_conflicts(deps: Deps, user_id: str) -> dict:
    try:
        term = deps.registration_term()
        current = deps.repo.get_student_sections(user_id, term)
        conflicts: list[dict] = []

        # class overlaps: each pair once
        for i, a in enumerate(current):
            for c in detect_conflicts(a, current[i + 1:]):
                conflicts.append({
                    "kind": "CLASS_OVERLAP",
                    "severity": c.severity,
                    "course_a": a.course_code,
                    "course_b": next(s.course_code for s in current if s.code == c.section_b),
                    "detail": c.detail,
                })

        # exam clashes (M3)
        for e in deps.detect_exam_conflicts(user_id, term):
            conflicts.append({
                "kind": "EXAM_CLASH",
                "severity": "HARD",
                "course_a": e["course_a"],
                "course_b": e["course_b"],
                "detail": e["detail"],
            })

        if conflicts:
            summary = f"{len(conflicts)} conflict(s) found in {term}: " + "; ".join(
                f"{c['course_a']} / {c['course_b']} ({c['kind']}, {c['detail']})" for c in conflicts
            )
        else:
            summary = f"No conflicts in your {term} schedule."
        return {"conflicts": conflicts, "summary": summary}
    except Exception:
        msg = "I could not check your schedule right now. Please try again."
        return {"conflicts": [], "summary": msg}