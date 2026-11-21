from app.domain.registration_rules import (
    Verdict, check_prerequisites, detect_conflicts, evaluate_registration,
)
from app.domain.shared_models import (
    CompletedCourse, Course, MeetingSlot, Section, StudentRecord,
)


def sec(code, course, slots, cap=30, enrolled=0, status="OPEN"):
    return Section(
        code=code, course_code=course, term="Spring 2027", instructor="X",
        schedule=[MeetingSlot(day=d, start=a, end=b) for d, a, b in slots],
        capacity=cap, enrolled_count=enrolled, status=status,
    )


def done(code, grade="B"):
    return CompletedCourse(student_id="S1", course_code=code, credits=3, grade=grade, term="Fall 2026")


COURSE = Course(code="CS201", title="DS", credits=3, level=2, prereqs=["CS101"])
STUDENT = StudentRecord(student_id="S1", completed=[done("CS101")])
A = sec("CS201-A", "CS201", [("Mon", "10:00", "10:50")])


def run(course=COURSE, section=A, student=STUDENT, current=None, open_=True, blocked=False):
    return evaluate_registration(course, section, student, current or [], open_, blocked)


def test_prereq_met():
    assert check_prerequisites(COURSE, STUDENT) == []

def test_prereq_missing():
    assert check_prerequisites(COURSE, StudentRecord(student_id="S1")) == ["CS101"]

def test_prereq_failed_does_not_count():
    s = StudentRecord(student_id="S1", completed=[done("CS101", "F")])
    assert check_prerequisites(COURSE, s) == ["CS101"]

def test_overlap_is_hard():
    other = sec("MA101-A", "MA101", [("Mon", "10:30", "11:20")])
    assert detect_conflicts(A, [other])[0].severity == "HARD"

def test_back_to_back_no_conflict():
    other = sec("MA101-A", "MA101", [("Mon", "10:50", "11:40")])
    assert [c for c in detect_conflicts(A, [other]) if c.severity == "HARD"] == []

def test_soft_gap():
    other = sec("MA101-A", "MA101", [("Mon", "11:00", "11:50")])   # 10 min gap
    assert detect_conflicts(A, [other])[0].severity == "SOFT"

def test_eligible():
    assert run().verdict == Verdict.ELIGIBLE

def test_already_enrolled_first():
    s = StudentRecord(student_id="S1", completed=[done("CS101")], current_section_codes=["CS201-A"])
    assert run(student=s, open_=False).verdict == Verdict.ALREADY_ENROLLED

def test_closed_before_full():
    full = sec("CS201-A", "CS201", [("Mon", "10:00", "10:50")], cap=1, enrolled=1)
    assert run(section=full, open_=False).verdict == Verdict.REGISTRATION_CLOSED

def test_full_and_prereq_missing_gives_full():
    full = sec("CS201-A", "CS201", [("Mon", "10:00", "10:50")], cap=1, enrolled=1)
    assert run(section=full, student=StudentRecord(student_id="S1")).verdict == Verdict.SECTION_FULL

def test_prereq_before_conflict():
    other = sec("MA101-A", "MA101", [("Mon", "10:30", "11:20")])
    r = run(student=StudentRecord(student_id="S1"), current=[other])
    assert r.verdict == Verdict.PREREQ_MISSING

def test_conflict_before_standing():
    other = sec("MA101-A", "MA101", [("Mon", "10:30", "11:20")])
    assert run(current=[other], blocked=True).verdict == Verdict.CONFLICT

def test_standing_blocked():
    assert run(blocked=True).verdict == Verdict.STANDING_BLOCKED