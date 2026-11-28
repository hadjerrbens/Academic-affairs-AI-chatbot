"""
calendar_service.py  (M3, service layer)

Glue between the data layer (calendar_repo) and the rules (calendar_engine).
It does two jobs:
  A) builds TermInfo for M1 (current term, registration term, is registration open?)
  B) exposes the 3 tools:  get_academic_calendar, get_my_exam_schedule, get_exam_rules_summary

Structure used on purpose, so the logic is testable without a database:
  - build_*  functions: SYNC, take plain data, return the tool's dict.  <- tested
  - tool functions     : ASYNC, load data from Mongo, then call a build_* function.

Tool rules from the contract (section 2):
  - signature:  async def tool(ctx, args) -> dict
  - NO student_id / user_id argument (the user is ctx.user)
  - the result has a "summary" string holding every date/number the answer needs
  - never raises: on failure return {"error": CODE, "message": "one sentence"}
  - no writes to the database

TODO when M4 pushes core/tools.py: put  @register_tool(feature_area="...", requires_auth=...)
above each tool function (see the comments above each one).

NOTE: no list/dict comprehensions on purpose - plain loops only.
"""

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field

from app.data import calendar_repo
from app.domain import calendar_engine as engine


# ---------------------------------------------------------------------------
# A) TermInfo for M1
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TermInfo:
    today: date
    current_term: str | None  # semester we are in ("Fall 2026")
    registration_term: str | None  # term students register for ("Spring 2027")
    registration_open: bool  # is registration_term's window open today?
    current_phase: str | None  # e.g. "IN_SESSION"


def build_term_info(events, today):
    """Pure: events in, TermInfo out."""
    current = engine.current_term(events, today)
    registering = engine.registration_term(events, today)

    reg_open = False
    if registering is not None:
        reg_open = engine.is_registration_open(events, registering, today)

    phase = None
    if current is not None:
        phase = engine.resolve_phase(events, current, today)

    return TermInfo(
        today=today,
        current_term=current,
        registration_term=registering,
        registration_open=reg_open,
        current_phase=phase,
    )


async def get_term_info(db, today):
    """The chat route calls this once per message to fill ToolContext(current_term, registration_term)."""
    events = await calendar_repo.list_events(db)
    return build_term_info(events, today)


async def is_registration_open(db, term, today):
    """For M1 (contract name: is_registration_open). NOTE: db comes first. No grace days."""
    events = await calendar_repo.list_events(db)
    return engine.is_registration_open(events, term, today)


async def get_registration_term(db, today):
    """For M1 (contract name: registration_term)."""
    events = await calendar_repo.list_events(db)
    return engine.registration_term(events, today)


# ---------------------------------------------------------------------------
# B) Tool argument models (pydantic validates what the LLM sends us)
# NO student_id / user_id fields - a test scans for them.
# ---------------------------------------------------------------------------

class GetAcademicCalendarArgs(BaseModel):
    term: str | None = Field(default=None, description="Term such as 'Fall 2026'. Defaults to the current term.")
    event_type: str | None = Field(
        default=None,
        description="Optional filter, e.g. 'registration_close', 'add_drop_deadline', 'holiday', 'exam_period_start'.",
    )


class NoArgs(BaseModel):
    """For tools that take no arguments."""


# ---------------------------------------------------------------------------
# Helpers for building summaries
# ---------------------------------------------------------------------------

def _event_to_dict(event):
    return {
        "event_type": event.event_type,
        "name": event.name,
        "start_date": event.start_date.isoformat(),
        "end_date": event.end_date.isoformat(),
    }


def _date_text(event):
    if event.start_date == event.end_date:
        return event.start_date.isoformat()
    return event.start_date.isoformat() + " to " + event.end_date.isoformat()


def _error(code, message):
    return {"error": code, "message": message}


# ---------------------------------------------------------------------------
# Tool 1: get_academic_calendar (public)
# ---------------------------------------------------------------------------

def build_calendar_answer(events, term, event_type, today):
    """events: ALL events (the phase needs the whole term). Returns the tool dict."""
    if term is None:
        return _error("TERM_UNKNOWN", "I could not work out which term you mean. Please name one, e.g. Fall 2026.")

    in_term = []
    for event in events:
        if event.term == term:
            in_term.append(event)
    if not in_term:
        return _error("TERM_NOT_FOUND", "The calendar has no events for " + term + ".")

    chosen = []
    if event_type:
        wanted = engine.normalise_event_type(event_type)
        for event in in_term:
            if engine.normalise_event_type(event.event_type) == wanted:
                chosen.append(event)
        if not chosen:
            return _error("NO_MATCHING_EVENTS", "No '" + event_type + "' event is listed for " + term + ".")
    else:
        chosen = in_term
    chosen = engine.sort_events(chosen)

    phase = engine.resolve_phase(events, term, today)
    upcoming = engine.next_event(events, term, today)

    lines = []
    lines.append(term + " - today is " + today.isoformat() + ". Phase: " + phase + " - " + engine.PHASE_DESCRIPTIONS[phase])
    if upcoming is not None:
        lines.append("Next event: " + upcoming.name + " on " + _date_text(upcoming) + ".")
    else:
        lines.append("There are no more events listed for " + term + ".")
    lines.append("Events:")
    for event in chosen:
        lines.append("- " + _date_text(event) + ": " + event.name + " (" + event.event_type + ")")

    event_dicts = []
    for event in chosen:
        event_dicts.append(_event_to_dict(event))

    next_dict = None
    if upcoming is not None:
        next_dict = _event_to_dict(upcoming)

    return {
        "term": term,
        "phase": phase,
        "next_event": next_dict,
        "events": event_dicts,
        "summary": "\n".join(lines),
    }


# @register_tool(feature_area="academic_calendar", requires_auth=False)   <- add when M4's tools.py lands
async def get_academic_calendar(ctx, args):
    try:
        db = _get_db()
        events = await calendar_repo.list_events(db)
        term = args.term or ctx.current_term
        return build_calendar_answer(events, term, args.event_type, ctx.today)
    except Exception:  # tools must never raise (contract); M4's execute() also guards
        return _error("CALENDAR_UNAVAILABLE", "I could not load the academic calendar right now.")


# ---------------------------------------------------------------------------
# Tool 2: get_my_exam_schedule (login required)
# ---------------------------------------------------------------------------

def build_exam_schedule_answer(exams, max_exams_per_day, term):
    """exams: the student's ExamSlot list for `term`. max_exams_per_day comes from exam_rules (0 = no soft warning)."""
    conflicts = engine.detect_exam_conflicts(exams, max_exams_per_day)

    exam_dicts = []
    lines = []
    for exam in exams:
        exam_dicts.append({
            "section_code": exam.section_code,
            "course_code": exam.course_code,
            "date": exam.exam_date.isoformat(),
            "start_time": exam.start_time.strftime("%H:%M"),
            "end_time": exam.end_time.strftime("%H:%M"),
            "room": exam.room,
            "proctoring_type": exam.proctoring_type,
        })
        lines.append(
            "- " + exam.exam_date.isoformat() + " " + exam.start_time.strftime("%H:%M") + "-"
            + exam.end_time.strftime("%H:%M") + ": " + exam.course_code + " (" + exam.section_code
            + "), room " + exam.room + ", " + exam.proctoring_type
        )

    conflict_dicts = []
    conflict_lines = []
    for conflict in conflicts:
        conflict_dicts.append(conflict.to_dict())
        conflict_lines.append("- " + conflict.severity + ": " + conflict.detail)

    if not exams:
        summary = "You have no exams scheduled for " + term + "."
    else:
        summary = "Your exams for " + term + ":\n" + "\n".join(lines)
        if conflict_lines:
            summary = summary + "\nConflicts:\n" + "\n".join(conflict_lines)
        else:
            summary = summary + "\nNo exam conflicts."

    return {"term": term, "exams": exam_dicts, "conflicts": conflict_dicts, "summary": summary}


async def load_student_section_codes(ctx, term):
    """
    SEAM WITH M1 / M2 - adjust when their code lands.
    Assumes: M1's enrollment_repo.get_student_sections(student_id, term) returns Section objects
    with a .code, and ctx.user has a .student_id. Lazy import because that file does not exist yet.
    """
    from app.data import enrollment_repo

    sections = await enrollment_repo.get_student_sections(ctx.user.student_id, term)
    codes = []
    for section in sections:
        codes.append(section.code)
    return codes


# @register_tool(feature_area="exam_schedules", requires_auth=True)   <- add when M4's tools.py lands
async def get_my_exam_schedule(ctx, args):
    try:
        db = _get_db()
        term = ctx.current_term
        codes = await load_student_section_codes(ctx, term)
        exams = await calendar_repo.get_exam_schedule(db, codes)
        rules = await calendar_repo.get_exam_rules(db, term)
        limit = 0
        if rules is not None:
            limit = rules.scheduling_limit_exams_per_day
        return build_exam_schedule_answer(exams, limit, term)
    except Exception:
        return _error("EXAMS_UNAVAILABLE", "I could not load your exam schedule right now.")


# ---------------------------------------------------------------------------
# Tool 3: get_exam_rules_summary (public)
# ---------------------------------------------------------------------------

def build_exam_rules_answer(rules, term):
    if rules is None:
        return _error("NO_EXAM_RULES", "No exam-day rules are published for " + str(term) + ".")
    return {
        "term": rules.term,
        "allowed_items": rules.allowed_items,
        "forbidden_items": rules.forbidden_items,
        "calculator_policy": rules.calculator_policy,
        "open_book_policy": rules.open_book_policy,
        "late_arrival_rule": rules.late_arrival_rule,
        "summary": engine.format_exam_rules(rules),
    }


# @register_tool(feature_area="exam_schedules", requires_auth=False)   <- add when M4's tools.py lands
async def get_exam_rules_summary(ctx, args):
    try:
        db = _get_db()
        rules = await calendar_repo.get_exam_rules(db, ctx.current_term)
        return build_exam_rules_answer(rules, ctx.current_term)
    except Exception:
        return _error("EXAM_RULES_UNAVAILABLE", "I could not load the exam rules right now.")


def _get_db():
    # Lazy import: core/db.py needs the `motor` package; importing it only when a tool
    # actually runs keeps this file importable (and testable) without a database driver.
    from app.core.db import get_db

    return get_db()


# ---------------------------------------------------------------------------
# Registration in M4's ToolRegistry (handlers are (ctx, **args); wrap the pydantic-style tools)
# ---------------------------------------------------------------------------

def _adapt(fn, args_model):
    async def handler(ctx, **kwargs):
        return await fn(ctx, args_model(**kwargs))
    return handler


def register(registry) -> None:
    registry.tool(
        name="get_academic_calendar",
        description="Academic calendar events (registration windows, deadlines, holidays, exam periods). "
                    "Optional term like 'Fall 2026' and event_type.",
        parameters={"type": "object", "properties": {
            "term": {"type": "string"}, "event_type": {"type": "string"}}, "required": []},
        areas=["academic_calendar"], public=True, safe_without_llm=True,
    )(_adapt(get_academic_calendar, GetAcademicCalendarArgs))
    registry.tool(
        name="get_my_exam_schedule",
        description="The logged-in student's exam timetable for the current term, with conflicts.",
        parameters={"type": "object", "properties": {}, "required": []},
        areas=["exam_schedules"], safe_without_llm=True,
    )(_adapt(get_my_exam_schedule, NoArgs))
    registry.tool(
        name="get_exam_rules_summary",
        description="Exam-day rules: allowed and forbidden items, calculators, open book, late arrival.",
        parameters={"type": "object", "properties": {}, "required": []},
        areas=["exam_schedules"], public=True, safe_without_llm=True,
    )(_adapt(get_exam_rules_summary, NoArgs))
