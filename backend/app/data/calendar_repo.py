"""
calendar_repo.py  (M3, data layer)

The ONLY place that talks to MongoDB for calendar / exam data. Its job is small:
  1. ask Mongo for documents,
  2. convert each document (a plain dict) into the dataclasses from calendar_engine.

No business rules here. The rules live in domain/calendar_engine.py.

How the documents look in Mongo (written by the seed loader):
  calendar_events: {event_id, term, event_type, name, start_date: "2026-12-07", end_date, description}
  exam_schedules : {section_code, term, exam_date: "2026-12-07", start_time: "09:00", end_time, room, proctoring_type}
  exam_rules     : {rule_id, term, allowed_items: [...], forbidden_items: [...], calculator_policy, ...}

Every function takes `db` (the Mongo database object) as its first argument. That keeps this
file free of global state, and lets tests pass a fake `db`.

NOTE: no list/dict comprehensions on purpose - plain loops only.
"""

from datetime import date, datetime, time

from app.domain.calendar_engine import (
    CalendarEvent,
    ExamRules,
    ExamSlot,
    normalise_event_type,
)

EVENTS_COLLECTION = "calendar_events"
EXAMS_COLLECTION = "exam_schedules"
RULES_COLLECTION = "exam_rules"


# ---------------------------------------------------------------------------
# Converters: Mongo document (dict) -> dataclass.
# Pure functions, so they are easy to test without a database.
# ---------------------------------------------------------------------------

def to_date(value):
    """Accepts a date, a datetime, or text like '2026-12-07' (or '2026-12-07T00:00:00')."""
    if isinstance(value, datetime):  # check datetime FIRST: datetime is also a date
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def to_time(value):
    """Accepts a time or text like '09:00'."""
    if isinstance(value, time):
        return value
    parts = str(value).strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def to_list(value):
    """Mongo already holds a list; but accept 'a|b|c' text too (the CSV format)."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    items = []
    for piece in str(value).split("|"):
        piece = piece.strip()
        if piece:
            items.append(piece)
    return items


def event_from_doc(doc):
    return CalendarEvent(
        event_id=doc.get("event_id", ""),
        term=doc["term"],
        event_type=doc["event_type"],
        name=doc.get("name", ""),
        start_date=to_date(doc["start_date"]),
        end_date=to_date(doc.get("end_date") or doc["start_date"]),
    )


def exam_from_doc(doc):
    return ExamSlot(
        section_code=doc["section_code"],
        term=doc["term"],
        exam_date=to_date(doc["exam_date"]),
        start_time=to_time(doc["start_time"]),
        end_time=to_time(doc["end_time"]),
        room=doc.get("room", ""),
        proctoring_type=doc.get("proctoring_type", ""),
    )


def rules_from_doc(doc):
    return ExamRules(
        term=doc["term"],
        allowed_items=to_list(doc.get("allowed_items")),
        forbidden_items=to_list(doc.get("forbidden_items")),
        calculator_policy=doc.get("calculator_policy", ""),
        open_book_policy=doc.get("open_book_policy", ""),
        late_arrival_rule=doc.get("late_arrival_rule", ""),
        scheduling_limit_exams_per_day=int(doc.get("scheduling_limit_exams_per_day", 0)),
        scheduling_limit_conflict_note=doc.get("scheduling_limit_conflict_note", ""),
    )


# ---------------------------------------------------------------------------
# Queries (async: Mongo calls wait for the network, so we use await)
# ---------------------------------------------------------------------------

async def list_events(db, term=None, types=None):
    """
    Calendar events, optionally for one term and/or some event types.
    With term=None you get ALL terms - the engine needs that to work out
    current_term and registration_term.
    The calendar is tiny (about 20 rows), so filtering by type is done here in Python.
    """
    query = {}
    if term is not None:
        query["term"] = term

    cursor = db[EVENTS_COLLECTION].find(query, {"_id": 0})  # {"_id": 0} = leave Mongo's internal id out
    docs = await cursor.to_list(length=None)  # length=None = everything

    wanted = None
    if types:
        wanted = []
        for event_type in types:
            wanted.append(normalise_event_type(event_type))

    events = []
    for doc in docs:
        event = event_from_doc(doc)
        if wanted is not None and normalise_event_type(event.event_type) not in wanted:
            continue
        events.append(event)
    return events


async def get_exam_schedule(db, section_codes):
    """Exams for these section codes (the student's registered sections), earliest first."""
    if not section_codes:
        return []  # no sections -> no query needed

    query = {"section_code": {"$in": list(section_codes)}}  # $in = "any of these values"
    cursor = db[EXAMS_COLLECTION].find(query, {"_id": 0})
    docs = await cursor.to_list(length=None)

    exams = []
    for doc in docs:
        exams.append(exam_from_doc(doc))
    exams.sort(key=lambda exam: (exam.exam_date, exam.start_time, exam.section_code))
    return exams


async def get_exam_rules(db, term):
    """The exam-day rules for a term, or None if none were published."""
    doc = await db[RULES_COLLECTION].find_one({"term": term}, {"_id": 0})
    if doc is None:
        return None
    return rules_from_doc(doc)
