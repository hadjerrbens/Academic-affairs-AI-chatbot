import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Day = Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_COURSE_RE = re.compile(r"^([A-Z]{2,4})(\d{3})$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_SLOT_RE = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\s*(?:@\s*(.*))?$"
)


class MeetingSlot(BaseModel):
    day: Day
    start: str          # "10:00"
    end: str            # "10:50"
    room: str = ""


class Course(BaseModel):
    code: str                                   # "CS101"
    title: str
    credits: int
    level: int
    prereqs: list[str] = Field(default_factory=list)
    terms_offered: list[str] = Field(default_factory=list)


class Section(BaseModel):
    code: str                                   # "CS101-A"
    course_code: str
    term: str                                   # "Fall 2026"
    instructor: str
    schedule: list[MeetingSlot]
    capacity: int
    enrolled_count: int
    status: Literal["OPEN", "FULL", "CLOSED", "CANCELLED"] = "OPEN"

    @field_validator("status", mode="before")
    @classmethod
    def _upper_status(cls, v):
        return v.upper() if isinstance(v, str) else v

    @property
    def seats_left(self) -> int:
        return max(0, self.capacity - self.enrolled_count)


class CompletedCourse(BaseModel):
    student_id: str
    course_code: str
    credits: int
    grade: str
    grade_points: float | None = None
    term: str
    status: Literal["COMPLETED", "IN_PROGRESS", "WITHDRAWN", "INCOMPLETE"] = "COMPLETED"
    is_repeat: bool = False


class StudentRecord(BaseModel):
    student_id: str
    program_code: str | None = None
    year: int = 1
    completed: list[CompletedCourse] = Field(default_factory=list)
    current_section_codes: list[str] = Field(default_factory=list)


def parse_course_code(code: str) -> tuple[str, int]:
    m = _COURSE_RE.match(code.strip().upper().replace(" ", ""))
    if not m:
        raise ValueError(f"Invalid course code: {code!r}")
    return m.group(1), int(m.group(2))


def normalise_course_code(code: str) -> str:
    prefix, num = parse_course_code(code)
    return f"{prefix}{num}"


def time_to_minutes(t: str) -> int:
    m = _TIME_RE.match(t)
    if not m:
        raise ValueError(f"Invalid time: {t!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_schedule(text: str) -> list[MeetingSlot]:
    """'Sun 10:00-10:50 @A101 | Tue 08:00-09:30 @B2' -> [MeetingSlot, ...].
    Accepts spaces around '@' and '|' (both seed formats)."""
    slots = []
    for part in text.split("|"):
        part = part.strip()
        if not part:
            continue
        m = _SLOT_RE.match(part)
        if not m:
            raise ValueError(f"Invalid meeting slot: {part!r}")
        day, h1, m1, h2, m2, room = m.groups()
        slots.append(MeetingSlot(
            day=day, start=f"{int(h1):02d}:{m1}", end=f"{int(h2):02d}:{m2}",
            room=(room or "").strip(),
        ))
    return slots


def slots_overlap(a: MeetingSlot, b: MeetingSlot) -> bool:
    """Back-to-back (10:00-10:50 / 10:50-11:40) is NOT an overlap."""
    if a.day != b.day:
        return False
    return time_to_minutes(a.start) < time_to_minutes(b.end) and \
           time_to_minutes(b.start) < time_to_minutes(a.end)


def gap_minutes(a: MeetingSlot, b: MeetingSlot) -> int | None:
    """Minutes between two non-overlapping slots on the same day, else None."""
    if a.day != b.day or slots_overlap(a, b):
        return None
    first, second = sorted((a, b), key=lambda s: time_to_minutes(s.start))
    return time_to_minutes(second.start) - time_to_minutes(first.end)