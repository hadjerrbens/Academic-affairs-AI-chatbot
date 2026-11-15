import pytest
from app.domain.shared_models import (
    MeetingSlot, Section, slots_overlap, gap_minutes,
    parse_course_code, parse_schedule, time_to_minutes,
)


def S(day, a, b):
    return MeetingSlot(day=day, start=a, end=b)


def test_overlap_true():
    assert slots_overlap(S("Mon", "10:00", "10:50"), S("Mon", "10:30", "11:20"))

def test_back_to_back_is_not_overlap():
    assert not slots_overlap(S("Mon", "10:00", "10:50"), S("Mon", "10:50", "11:40"))

def test_different_day():
    assert not slots_overlap(S("Mon", "10:00", "10:50"), S("Tue", "10:00", "10:50"))

def test_gap():
    assert gap_minutes(S("Mon", "10:00", "10:50"), S("Mon", "11:00", "11:50")) == 10
    assert gap_minutes(S("Mon", "10:00", "10:50"), S("Mon", "10:30", "11:20")) is None

def test_parse_course_code():
    assert parse_course_code("cs101") == ("CS", 101)
    with pytest.raises(ValueError):
        parse_course_code("CS10")

def test_time():
    assert time_to_minutes("10:50") == 650

def test_parse_schedule_both_formats():
    a = parse_schedule("Sun 10:00-10:50 @A101 | Tue 8:00-09:30 @B2")
    assert a[0] == S("Sun", "10:00", "10:50").model_copy(update={"room": "A101"})
    assert a[1].start == "08:00" and a[1].room == "B2"
    b = parse_schedule("Mon 10:00-10:50@SCI-204|Wed 10:00-10:50@SCI-204")
    assert len(b) == 2 and b[1].room == "SCI-204"

def test_parse_schedule_bad():
    with pytest.raises(ValueError):
        parse_schedule("Funday 10:00-11:00")

def test_section_status_case_and_seats():
    sec = Section(code="CS101-A", course_code="CS101", term="Fall 2026", instructor="X",
                  schedule=[], capacity=30, enrolled_count=30, status="open")
    assert sec.status == "OPEN" and sec.seats_left == 0