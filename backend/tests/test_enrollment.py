import threading

import mongomock
import pytest

from app.data.enrollment_repo import EnrollmentError, EnrollmentRepo


@pytest.fixture
def repo():
    db = mongomock.MongoClient()["test"]
    db["courses"].insert_one({
        "code": "CS201", "title": "Data Structures", "credits": 3, "level": 2,
        "prereqs": "CS101", "terms_offered": "Spring 2027",
    })
    db["sections"].insert_many([
        {"code": "CS201-A", "course_code": "CS201", "term": "Spring 2027", "instructor": "X",
         "schedule": "Sun 10:00-10:50 @A101 | Tue 10:00-10:50 @A101",
         "capacity": 2, "enrolled_count": 0, "status": "OPEN"},
    ])
    r = EnrollmentRepo(db)
    r.ensure_indexes()
    return r


def test_course_prereqs_parsed(repo):
    assert repo.get_course("CS201").prereqs == ["CS101"]


def test_enroll_updates_seats(repo):
    sec = repo.enroll("S1", "CS201-A")
    assert sec.enrolled_count == 1 and sec.seats_left == 1
    assert [s.code for s in repo.get_student_sections("S1", "Spring 2027")] == ["CS201-A"]


def test_register_twice_gives_one_enrollment(repo):
    repo.enroll("S1", "CS201-A")
    with pytest.raises(EnrollmentError) as e:
        repo.enroll("S1", "CS201-A")
    assert e.value.code == "ALREADY_ENROLLED"
    assert repo.get_section("CS201-A").enrolled_count == 1
    assert repo.enrollments.count_documents({"student_id": "S1"}) == 1


def test_full_section_refused_and_marked_full(repo):
    repo.enroll("S1", "CS201-A")
    repo.enroll("S2", "CS201-A")
    assert repo.get_section("CS201-A").status == "FULL"
    with pytest.raises(EnrollmentError) as e:
        repo.enroll("S3", "CS201-A")
    assert e.value.code == "SECTION_FULL"
    assert repo.get_section("CS201-A").enrolled_count == 2


def test_drop_frees_seat_and_reopens(repo):
    repo.enroll("S1", "CS201-A")
    repo.enroll("S2", "CS201-A")
    sec = repo.drop("S1", "CS201-A")
    assert sec.enrolled_count == 1 and sec.status == "OPEN"


def test_drop_when_not_enrolled(repo):
    with pytest.raises(EnrollmentError) as e:
        repo.drop("S1", "CS201-A")
    assert e.value.code == "NOT_ENROLLED"


def test_seats_never_exceed_capacity_under_race(repo):
    results = []

    def go(i):
        try:
            repo.enroll(f"S{i}", "CS201-A")
            results.append("ok")
        except EnrollmentError:
            results.append("refused")

    threads = [threading.Thread(target=go, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()

    sec = repo.get_section("CS201-A")
    assert sec.enrolled_count <= sec.capacity
    assert results.count("ok") == 2
    assert repo.enrollments.count_documents({"section_code": "CS201-A"}) == 2