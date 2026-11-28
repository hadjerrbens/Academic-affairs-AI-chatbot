"""Shared data shapes (contract section 3) and tiny helpers. Pure: no I/O, no clock."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MeetingSlot:
    day: str
    start: str  # "HH:MM"
    end: str
    room: str = ""


@dataclass(frozen=True)
class Course:
    code: str
    title: str
    credits: int
    level: int = 0
    prereqs: list[str] = field(default_factory=list)
    terms_offered: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Section:
    code: str
    course_code: str
    term: str
    instructor: str = ""
    schedule: list[MeetingSlot] = field(default_factory=list)
    capacity: int = 0
    enrolled_count: int = 0
    status: str = "open"


@dataclass
class CompletedCourse:
    student_id: str
    course_code: str
    credits: int
    grade: str
    term: str
    grade_points: float | None = None
    status: str = "COMPLETED"
    is_repeat: bool = False


@dataclass
class StudentRecord:
    student_id: str
    program_code: str | None
    year: int
    completed: list[CompletedCourse] = field(default_factory=list)
    current_section_codes: list[str] = field(default_factory=list)


_COURSE = re.compile(r"^([A-Z]{2,4})(\d{3})$")


def parse_course_code(text: str) -> str:
    code = re.sub(r"\s+", "", str(text)).upper()
    if not _COURSE.match(code):
        raise ValueError(f"'{text}' is not a course code like CS101")
    return code


def time_to_minutes(value: str) -> int:
    hours, minutes = str(value).split(":")
    return int(hours) * 60 + int(minutes)


def slots_overlap(a: MeetingSlot, b: MeetingSlot) -> bool:
    return (a.day == b.day
            and time_to_minutes(a.start) < time_to_minutes(b.end)
            and time_to_minutes(b.start) < time_to_minutes(a.end))
