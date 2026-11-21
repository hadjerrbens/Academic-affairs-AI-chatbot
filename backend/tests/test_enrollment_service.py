import mongomock
import pytest

from app.data.enrollment_repo import EnrollmentRepo
from app.domain.shared_models import CompletedCourse, StudentRecord
from app.services.enrollment_service import (
    TOOL_SCHEMAS, Deps, check_registration_eligibility, detect_schedule_conflicts,
)


def make_deps(completed=("CS101",), open_=True, blocked=False, exam_conflicts=()):
    db = mongomock.MongoClient()["t"]
    db["courses"].insert_many([
        {"code": "CS201", "title": "DS", "credits": 3, "level": 2, "prereqs": "CS101", "terms_offered": ""},
        {"code": "MA101", "title": "Math", "credits": 3, "level": 1, "prereqs": "", "terms_offered": ""},
    ])
    db["sections"].insert_many([
        {"code": "CS201-A", "course_code": "CS201", "term": "Spring 2027", "instructor": "X",
         "schedule": "Sun 10:00-10:50 @A1", "capacity": 30, "enrolled_count": 0, "status": "OPEN"},
        {"code": "MA101-A", "course_code": "MA101", "term": "Spring 2027", "instructor": "Y",
         "schedule": "Sun 10:30-11:20 @A2", "capacity": 30, "enrolled_count": 0, "status": "OPEN"},
    ])
    repo = EnrollmentRepo(db)
    repo.ensure_indexes()
    record = StudentRecord(student_id="S1", completed=[
        CompletedCourse(student_id="S1", course_code=c, credits=3, grade="B", term="Fall 2026")
        for c in completed])
    return Deps(
        repo=repo,
        get_student_record=lambda sid: record,
        get_standing=lambda sid: (blocked, "On probation." if blocked else ""),
        is_registration_open=lambda: open_,
        registration_term=lambda: "Spring 2027",
        detect_exam_conflicts=lambda sid, term: list(exam_conflicts),
    )


def test_eligible():
    r = check_registration_eligibility(make_deps(), "S1", "cs201")
    assert r["verdict"] == "ELIGIBLE" and r["sections"][0]["seats_left"] == 30
    assert "summary" in r


def test_prereq_missing():
    r = check_registration_eligibility(make_deps(completed=()), "S1", "CS201")
    assert r["verdict"] == "PREREQ_MISSING"


def test_unknown_course_does_not_raise():
    r = check_registration_eligibility(make_deps(), "S1", "ZZ999")
    assert r["verdict"] == "COURSE_NOT_FOUND"


def test_bad_code_does_not_raise():
    assert check_registration_eligibility(make_deps(), "S1", "??")["verdict"] == "COURSE_NOT_FOUND"


def test_unknown_section():
    r = check_registration_eligibility(make_deps(), "S1", "CS201", "CS201-Z")
    assert r["verdict"] == "SECTION_NOT_FOUND"


def test_conflicts_class_overlap_and_exam():
    deps = make_deps(exam_conflicts=[{"course_a": "CS201", "course_b": "MA101", "detail": "same slot"}])
    deps.repo.enroll("S1", "CS201-A")
    deps.repo.enroll("S1", "MA101-A")
    r = detect_schedule_conflicts(deps, "S1")
    kinds = {c["kind"] for c in r["conflicts"]}
    assert kinds == {"CLASS_OVERLAP", "EXAM_CLASH"}


def test_no_conflicts():
    r = detect_schedule_conflicts(make_deps(), "S1")
    assert r["conflicts"] == [] and "No conflicts" in r["summary"]


def test_tool_never_raises_on_internal_error():
    deps = make_deps()
    deps.registration_term = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    assert check_registration_eligibility(deps, "S1", "CS201")["verdict"] == "ERROR"
    assert "summary" in detect_schedule_conflicts(deps, "S1")


def test_tool_schema_has_no_student_id():
    for tool in TOOL_SCHEMAS:
        assert "student_id" not in tool["parameters"]["properties"]