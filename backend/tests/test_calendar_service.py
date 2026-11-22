"""
Tests for app/data/calendar_repo.py and app/services/calendar_service.py (M3).
Run from backend/:   python -m pytest -v

No real database is used. The repo functions get a tiny FAKE db, and the service's build_*
functions take plain data.
"""

import asyncio
from datetime import date, datetime, time

from app.data import calendar_repo
from app.domain.calendar_engine import CalendarEvent, ExamRules, ExamSlot
from app.services import calendar_service as svc

DEMO_TODAY = date(2026, 10, 27)


def make_event(term, event_type, name, start, end=None):
    if end is None:
        end = start
    return CalendarEvent("E", term, event_type, name, start, end)


def sample_events():
    return [
        make_event("Fall 2026", "registration_open", "Registration opens", date(2026, 4, 13)),
        make_event("Fall 2026", "registration_close", "Registration closes", date(2026, 8, 14)),
        make_event("Fall 2026", "semester_start", "Semester begins", date(2026, 8, 24)),
        make_event("Fall 2026", "add_drop_deadline", "Add/drop deadline", date(2026, 9, 4)),
        make_event("Fall 2026", "holiday", "Holiday", date(2026, 9, 7)),
        make_event("Fall 2026", "exam_period_start", "Exam period begins", date(2026, 12, 7)),
        make_event("Fall 2026", "exam_period_end", "Exam period ends", date(2026, 12, 18)),
        make_event("Fall 2026", "semester_end", "Semester ends", date(2026, 12, 18)),
        make_event("Spring 2027", "registration_open", "Registration opens", date(2026, 10, 26)),
        make_event("Spring 2027", "registration_close", "Registration closes", date(2026, 11, 20)),
        make_event("Spring 2027", "semester_start", "Semester begins", date(2027, 1, 12)),
        make_event("Spring 2027", "semester_end", "Semester ends", date(2027, 5, 8)),
    ]


# ---------- fake Mongo ----------

class FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, length=None):
        return list(self.docs)


class FakeCollection:
    def __init__(self, docs):
        self.docs = docs
        self.last_query = None

    def find(self, query=None, projection=None):
        self.last_query = query
        return FakeCursor(self.docs)

    async def find_one(self, query=None, projection=None):
        self.last_query = query
        if self.docs:
            return self.docs[0]
        return None


class FakeDb:
    def __init__(self, collections):
        self.collections = collections

    def __getitem__(self, name):
        return self.collections[name]


# ---------- converters ----------

def test_to_date_accepts_text_datetime_and_date():
    assert calendar_repo.to_date("2026-12-07") == date(2026, 12, 7)
    assert calendar_repo.to_date("2026-12-07T00:00:00") == date(2026, 12, 7)
    assert calendar_repo.to_date(datetime(2026, 12, 7, 9, 30)) == date(2026, 12, 7)
    assert calendar_repo.to_date(date(2026, 12, 7)) == date(2026, 12, 7)


def test_to_time_and_to_list():
    assert calendar_repo.to_time("09:05") == time(9, 5)
    assert calendar_repo.to_time(time(9, 5)) == time(9, 5)
    assert calendar_repo.to_list(["a", "b"]) == ["a", "b"]
    assert calendar_repo.to_list("pens|pencils| ") == ["pens", "pencils"]
    assert calendar_repo.to_list(None) == []


def test_event_exam_and_rules_from_doc():
    event = calendar_repo.event_from_doc({
        "event_id": "EV1", "term": "Fall 2026", "event_type": "holiday",
        "name": "Holiday", "start_date": "2026-09-07", "end_date": "2026-09-07",
    })
    assert event.start_date == date(2026, 9, 7)

    exam = calendar_repo.exam_from_doc({
        "section_code": "CS101-A", "term": "Fall 2026", "exam_date": "2026-12-07",
        "start_time": "09:00", "end_time": "11:00", "room": "PHY-131", "proctoring_type": "in_person",
    })
    assert exam.course_code == "CS101"
    assert exam.end_time == time(11, 0)

    rules = calendar_repo.rules_from_doc({
        "term": "Fall 2026", "allowed_items": ["pens"], "forbidden_items": ["phones"],
        "calculator_policy": "c", "open_book_policy": "o", "late_arrival_rule": "l",
        "scheduling_limit_exams_per_day": "3", "scheduling_limit_conflict_note": "n",
    })
    assert rules.scheduling_limit_exams_per_day == 3


# ---------- repo queries with a fake db ----------

def test_list_events_filters_by_type_case_insensitively():
    docs = [
        {"event_id": "1", "term": "Fall 2026", "event_type": "holiday", "name": "H",
         "start_date": "2026-09-07", "end_date": "2026-09-07"},
        {"event_id": "2", "term": "Fall 2026", "event_type": "semester_start", "name": "S",
         "start_date": "2026-08-24", "end_date": "2026-08-24"},
    ]
    db = FakeDb({"calendar_events": FakeCollection(docs)})
    result = asyncio.run(calendar_repo.list_events(db, term="Fall 2026", types=["HOLIDAY"]))
    assert len(result) == 1
    assert result[0].event_type == "holiday"
    assert db["calendar_events"].last_query == {"term": "Fall 2026"}


def test_get_exam_schedule_builds_in_query_and_sorts():
    docs = [
        {"section_code": "B-A", "term": "Fall 2026", "exam_date": "2026-12-09",
         "start_time": "09:00", "end_time": "10:00", "room": "R", "proctoring_type": "in_person"},
        {"section_code": "A-A", "term": "Fall 2026", "exam_date": "2026-12-07",
         "start_time": "09:00", "end_time": "10:00", "room": "R", "proctoring_type": "in_person"},
    ]
    db = FakeDb({"exam_schedules": FakeCollection(docs)})
    result = asyncio.run(calendar_repo.get_exam_schedule(db, ["A-A", "B-A"]))
    assert db["exam_schedules"].last_query == {"section_code": {"$in": ["A-A", "B-A"]}}
    assert result[0].section_code == "A-A"  # earliest first


def test_get_exam_schedule_without_sections_returns_empty_without_querying():
    db = FakeDb({"exam_schedules": FakeCollection([])})
    assert asyncio.run(calendar_repo.get_exam_schedule(db, [])) == []
    assert db["exam_schedules"].last_query is None


def test_get_exam_rules_none_when_missing():
    db = FakeDb({"exam_rules": FakeCollection([])})
    assert asyncio.run(calendar_repo.get_exam_rules(db, "Fall 2026")) is None


# ---------- TermInfo ----------

def test_term_info_on_demo_date():
    info = svc.build_term_info(sample_events(), DEMO_TODAY)
    assert info.current_term == "Fall 2026"
    assert info.registration_term == "Spring 2027"
    assert info.registration_open is True
    assert info.current_phase == "IN_SESSION"


def test_term_info_day_after_registration_closes():
    info = svc.build_term_info(sample_events(), date(2026, 11, 21))
    assert info.registration_open is False  # no grace days


# ---------- tool 1: calendar ----------

def test_calendar_answer_has_dates_phase_and_next_event():
    result = svc.build_calendar_answer(sample_events(), "Fall 2026", None, DEMO_TODAY)
    assert result["phase"] == "IN_SESSION"
    assert result["next_event"]["event_type"] == "exam_period_start"
    assert "2026-12-07" in result["summary"]
    assert "Add/drop deadline" in result["summary"]


def test_calendar_answer_filters_by_event_type():
    result = svc.build_calendar_answer(sample_events(), "Fall 2026", "Holiday", DEMO_TODAY)
    assert len(result["events"]) == 1
    assert result["events"][0]["start_date"] == "2026-09-07"


def test_calendar_answer_errors_are_dicts_not_exceptions():
    assert svc.build_calendar_answer(sample_events(), None, None, DEMO_TODAY)["error"] == "TERM_UNKNOWN"
    assert svc.build_calendar_answer(sample_events(), "Winter 2030", None, DEMO_TODAY)["error"] == "TERM_NOT_FOUND"
    assert svc.build_calendar_answer(sample_events(), "Fall 2026", "graduation", DEMO_TODAY)["error"] == "NO_MATCHING_EVENTS"


# ---------- tool 2: exam schedule ----------

def make_exam(code, day, start, end):
    return ExamSlot(code, "Fall 2026", day, start, end, "R1", "in_person")


def test_exam_schedule_answer_reports_hard_clash():
    exams = [
        make_exam("CS101-A", date(2026, 12, 7), time(9, 0), time(11, 0)),
        make_exam("CS210-A", date(2026, 12, 7), time(10, 0), time(12, 0)),
    ]
    result = svc.build_exam_schedule_answer(exams, 3, "Fall 2026")
    assert len(result["exams"]) == 2
    assert result["exams"][0]["proctoring_type"] == "in_person"  # M5 joins on this
    assert result["conflicts"][0]["severity"] == "HARD"
    assert "HARD" in result["summary"]


def test_exam_schedule_answer_no_conflicts_and_no_exams():
    exams = [make_exam("CS101-A", date(2026, 12, 7), time(9, 0), time(11, 0))]
    assert "No exam conflicts." in svc.build_exam_schedule_answer(exams, 3, "Fall 2026")["summary"]
    empty = svc.build_exam_schedule_answer([], 3, "Fall 2026")
    assert empty["exams"] == []
    assert "no exams" in empty["summary"]


# ---------- tool 3: exam rules ----------

def test_exam_rules_answer():
    rules = ExamRules("Fall 2026", ["pens"], ["phones"], "calc", "closed", "late", 3, "note")
    result = svc.build_exam_rules_answer(rules, "Fall 2026")
    assert "pens" in result["summary"]
    assert svc.build_exam_rules_answer(None, "Spring 2027")["error"] == "NO_EXAM_RULES"


# ---------- contract: no tool takes student_id / user_id ----------

def test_tool_argument_models_have_no_student_or_user_id():
    models = [svc.GetAcademicCalendarArgs, svc.NoArgs]
    for model in models:
        schema_text = str(model.model_json_schema())
        assert "student_id" not in schema_text
        assert "user_id" not in schema_text
