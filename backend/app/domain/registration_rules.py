from enum import Enum

from pydantic import BaseModel, Field

from app.domain.shared_models import (
    Course, MeetingSlot, Section, StudentRecord, gap_minutes, slots_overlap,
)

# Grades that do not satisfy a prerequisite. Ideally this comes from the grading policy data;
# keep it as a default parameter so the caller can override it.
FAILING_GRADES = frozenset({"F"})
SOFT_GAP_MINUTES = 15


class Verdict(str, Enum):
    ALREADY_ENROLLED = "ALREADY_ENROLLED"
    REGISTRATION_CLOSED = "REGISTRATION_CLOSED"
    SECTION_FULL = "SECTION_FULL"
    PREREQ_MISSING = "PREREQ_MISSING"
    CONFLICT = "CONFLICT"
    STANDING_BLOCKED = "STANDING_BLOCKED"
    ELIGIBLE = "ELIGIBLE"


class Conflict(BaseModel):
    severity: str                      # "HARD" or "SOFT"
    section_a: str
    section_b: str
    detail: str


class RegistrationResult(BaseModel):
    verdict: Verdict
    reason: str
    missing_prereqs: list[str] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)   # HARD and SOFT
    warnings: list[str] = Field(default_factory=list)


def check_prerequisites(
    course: Course,
    student: StudentRecord,
    failing_grades: frozenset[str] = FAILING_GRADES,
) -> list[str]:
    """Return the MISSING prerequisite codes (empty list = all met)."""
    passed = {
        c.course_code
        for c in student.completed
        if c.status == "COMPLETED" and c.grade.upper() not in failing_grades
    }
    return [p for p in course.prereqs if p not in passed]


def _fmt(s: MeetingSlot) -> str:
    return f"{s.day} {s.start}-{s.end}"


def detect_conflicts(
    candidate: Section,
    others: list[Section],
    soft_gap: int = SOFT_GAP_MINUTES,
) -> list[Conflict]:
    """Compare one section against others. One result per pair (HARD wins over SOFT)."""
    found: list[Conflict] = []
    for other in others:
        if other.code == candidate.code:
            continue
        worst: Conflict | None = None
        for a in candidate.schedule:
            for b in other.schedule:
                if slots_overlap(a, b):
                    worst = Conflict(
                        severity="HARD", section_a=candidate.code, section_b=other.code,
                        detail=f"{_fmt(a)} overlaps {_fmt(b)}",
                    )
                    break
                g = gap_minutes(a, b)
                if g is not None and g < soft_gap and worst is None:
                    worst = Conflict(
                        severity="SOFT", section_a=candidate.code, section_b=other.code,
                        detail=f"only {g} min between {_fmt(a)} and {_fmt(b)}",
                    )
            if worst and worst.severity == "HARD":
                break
        if worst:
            found.append(worst)
    return found


def evaluate_registration(
    course: Course,
    section: Section,
    student: StudentRecord,
    current_sections: list[Section],
    registration_open: bool,
    standing_blocks: bool,
    standing_reason: str = "",
) -> RegistrationResult:
    """Return the FIRST problem found, in this order:
    ALREADY_ENROLLED -> REGISTRATION_CLOSED -> SECTION_FULL -> PREREQ_MISSING
    -> CONFLICT -> STANDING_BLOCKED, else ELIGIBLE.
    Pure function: no I/O, no clock. Callers pass in the facts from M2 and M3."""
    enrolled_courses = {s.course_code for s in current_sections}
    if section.code in student.current_section_codes or course.code in enrolled_courses:
        return RegistrationResult(
            verdict=Verdict.ALREADY_ENROLLED,
            reason=f"You are already enrolled in {course.code}.",
        )

    if not registration_open:
        return RegistrationResult(
            verdict=Verdict.REGISTRATION_CLOSED,
            reason="Registration is not open right now.",
        )

    if section.status != "OPEN" or section.seats_left <= 0:
        return RegistrationResult(
            verdict=Verdict.SECTION_FULL,
            reason=f"Section {section.code} has no seats available.",
        )

    missing = check_prerequisites(course, student)
    if missing:
        return RegistrationResult(
            verdict=Verdict.PREREQ_MISSING,
            reason=f"Missing prerequisites for {course.code}: {', '.join(missing)}.",
            missing_prereqs=missing,
        )

    conflicts = detect_conflicts(section, current_sections)
    hard = [c for c in conflicts if c.severity == "HARD"]
    soft = [c for c in conflicts if c.severity == "SOFT"]
    if hard:
        c = hard[0]
        return RegistrationResult(
            verdict=Verdict.CONFLICT,
            reason=f"{section.code} conflicts with {c.section_b}: {c.detail}.",
            conflicts=conflicts,
        )

    if standing_blocks:
        return RegistrationResult(
            verdict=Verdict.STANDING_BLOCKED,
            reason=standing_reason or "Your academic standing does not allow registration.",
        )

    return RegistrationResult(
        verdict=Verdict.ELIGIBLE,
        reason=f"You can register for {section.code}.",
        conflicts=soft,
        warnings=[f"Tight schedule: {c.detail}" for c in soft],
    )