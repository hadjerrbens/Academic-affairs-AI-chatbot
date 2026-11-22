"""
Tests for app/domain/calendar_engine.py (M3).
Run from the backend/ folder:   python -m pytest -v
The events below mirror the 'contract' seed (20 events), so the tests also prove the
demo requirement: with today = 2026-10-27, current_term = Fall 2026 and
registration_term = Spring 2027.
"""

from datetime import date, time

from app.domain.calendar_engine import (
    CalendarEvent,
    ExamRules,
    ExamSlot,
    PHASE_ADD_DROP,
    PHASE_BEFORE_REGISTRATION,
    PHASE_EXAM_PERIOD,
    PHASE_IN_SESSION,
    PHASE_POST_EXAMS,
    PHASE_REGISTRATION_CLOSED,
    PHASE_REGISTRATION_OPEN,
    PHASE_TERM_ENDED,
    SEVERITY_HARD,
    SEVERITY_SOFT,
    current_term,
    detect_exam_conflicts,
    exams_overlap,
    format_exam_rules,
    is_registration_open,
    next_event,
    normalise_event_type,
    registration_term,
    resolve_phase,
    sort_events,
)

DEMO_TODAY = date(2026, 10, 27)


def build_events():
    rows = [
        ("Fall 2026", "semester_start", date(2026, 8, 24), date(2026, 8, 24)),
        ("Fall 2026", "registration_open", date(2026, 4, 13), date(2026, 4, 13)),
        ("Fall 2026", "registration_close", date(2026, 8, 14), date(2026, 8, 14)),
        ("Fall 2026", "add_drop_deadline", date(2026, 9, 4), date(2026, 9, 4)),
        ("Fall 2026", "holiday", date(2026, 9, 7), date(2026, 9, 7)),
        ("Fall 2026", "reading_day", date(2026, 12, 6), date(2026, 12, 6)),
        ("Fall 2026", "exam_period_start", date(2026, 12, 7), date(2026, 12, 7)),
        ("Fall 2026", "exam_period_end", date(2026, 12, 18), date(2026, 12, 18)),
        ("Fall 2026", "semester_end", date(2026, 12, 18), date(2026, 12, 18)),
        ("Fall 2026", "graduation", date(2026, 12, 21), date(2026, 12, 21)),
        ("Spring 2027", "semester_start", date(2027, 1, 12), date(2027, 1, 12)),
        ("Spring 2027", "registration_open", date(2026, 10, 26), date(2026, 10, 26)),
        ("Spring 2027", "registration_close", date(2026, 11, 20), date(2026, 11, 20)),
        ("Spring 2027", "add_drop_deadline", date(2027, 1, 30), date(2027, 1, 30)),
        ("Spring 2027", "exam_period_start", date(2027, 4, 20), date(2027, 4, 20)),
        ("Spring 2027", "exam_period_end", date(2027, 5, 6), date(2027, 5, 6)),
        ("Spring 2027", "semester_end", date(2027, 5, 8), date(2027, 5, 8)),
        ("Spring 2027", "graduation", date(2027, 5, 11), date(2027, 5, 11)),
        ("Fall 2027", "registration_open", date(2027, 4, 13), date(2027, 4, 13)),
        ("Fall 2027", "registration_close", date(2027, 8, 14), date(2027, 8, 14)),
    ]
    events = []
    counter = 1
    for row in rows:
        events.append(CalendarEvent(
            event_id="EV" + str(counter).zfill(5),
            term=row[0],
            event_type=row[1],
            name=row[1],
            start_date=row[2],
            end_date=row[3],
        ))
        counter = counter + 1
    return events


EVENTS = build_events()


# ---------- the demo requirement (contracts section 4) ----------

def test_demo_date_gives_fall_current_and_spring_registration():
    assert current_term(EVENTS, DEMO_TODAY) == "Fall 2026"
    assert registration_term(EVENTS, DEMO_TODAY) == "Spring 2027"


# ---------- registration_term: before / during / after ----------

def test_registration_term_before_spring_opens():
    assert registration_term(EVENTS, date(2026, 10, 20)) == "Spring 2027"  # next upcoming


def test_registration_term_during_spring_registration():
    assert registration_term(EVENTS, date(2026, 11, 1)) == "Spring 2027"
    assert registration_term(EVENTS, date(2026, 11, 20)) == "Spring 2027"  # close day itself


def test_registration_term_after_spring_closes_moves_to_next_upcoming():
    assert registration_term(EVENTS, date(2026, 11, 21)) == "Fall 2027"


def test_registration_term_none_when_nothing_upcoming():
    assert registration_term(EVENTS, date(2027, 9, 1)) is None


# ---------- is_registration_open: open date, close date, day after (NO grace days) ----------

def test_is_registration_open_boundaries():
    assert is_registration_open(EVENTS, "Spring 2027", date(2026, 10, 25)) is False  # day before
    assert is_registration_open(EVENTS, "Spring 2027", date(2026, 10, 26)) is True  # open date
    assert is_registration_open(EVENTS, "Spring 2027", date(2026, 11, 20)) is True  # close date
    assert is_registration_open(EVENTS, "Spring 2027", date(2026, 11, 21)) is False  # day after


def test_is_registration_open_unknown_term_is_false():
    assert is_registration_open(EVENTS, "Winter 2030", date(2026, 11, 1)) is False


# ---------- current_term between semesters ----------

def test_current_term_edges_and_gaps():
    assert current_term(EVENTS, date(2026, 8, 24)) == "Fall 2026"  # first day
    assert current_term(EVENTS, date(2026, 12, 18)) == "Fall 2026"  # last day
    assert current_term(EVENTS, date(2026, 12, 19)) == "Spring 2027"  # gap -> next term
    assert current_term(EVENTS, date(2027, 6, 1)) == "Spring 2027"  # all over -> latest with a window
    assert current_term(EVENTS, date(2026, 6, 1)) == "Fall 2026"  # before everything -> next


# ---------- resolve_phase: every boundary date of Fall 2026 ----------

def test_resolve_phase_fall_2026_boundaries():
    cases = [
        (date(2026, 4, 12), PHASE_BEFORE_REGISTRATION),
        (date(2026, 4, 13), PHASE_REGISTRATION_OPEN),  # open date
        (date(2026, 8, 14), PHASE_REGISTRATION_OPEN),  # close date: still open
        (date(2026, 8, 15), PHASE_REGISTRATION_CLOSED),  # day after: closed
        (date(2026, 8, 23), PHASE_REGISTRATION_CLOSED),
        (date(2026, 8, 24), PHASE_ADD_DROP),  # semester start
        (date(2026, 9, 4), PHASE_ADD_DROP),  # add/drop deadline day
        (date(2026, 9, 5), PHASE_IN_SESSION),
        (date(2026, 12, 6), PHASE_IN_SESSION),  # reading day is still "in session"
        (date(2026, 12, 7), PHASE_EXAM_PERIOD),
        (date(2026, 12, 18), PHASE_EXAM_PERIOD),  # exam end == semester end
        (date(2026, 12, 19), PHASE_TERM_ENDED),
    ]
    for case in cases:
        assert resolve_phase(EVENTS, "Fall 2026", case[0]) == case[1], str(case[0])


def test_resolve_phase_spring_has_post_exams_gap():
    # Spring: exams end 6 May, semester ends 8 May
    assert resolve_phase(EVENTS, "Spring 2027", date(2027, 5, 6)) == PHASE_EXAM_PERIOD
    assert resolve_phase(EVENTS, "Spring 2027", date(2027, 5, 7)) == PHASE_POST_EXAMS
    assert resolve_phase(EVENTS, "Spring 2027", date(2027, 5, 8)) == PHASE_POST_EXAMS
    assert resolve_phase(EVENTS, "Spring 2027", date(2027, 5, 9)) == PHASE_TERM_ENDED


def test_resolve_phase_term_without_semester_dates():
    # Fall 2027 only has registration dates in the seed
    assert resolve_phase(EVENTS, "Fall 2027", date(2027, 5, 1)) == PHASE_REGISTRATION_OPEN
    assert resolve_phase(EVENTS, "Fall 2027", date(2027, 9, 1)) == PHASE_REGISTRATION_CLOSED


# ---------- small helpers ----------

def test_event_type_is_case_insensitive():
    upper = CalendarEvent("X1", "Fall 2030", "REGISTRATION_OPEN", "n", date(2030, 1, 1), date(2030, 1, 1))
    lower_close = CalendarEvent("X2", "Fall 2030", "registration_close", "n", date(2030, 1, 5), date(2030, 1, 5))
    events = [upper, lower_close]
    assert normalise_event_type(" Registration Open ") == "registration_open"
    assert is_registration_open(events, "Fall 2030", date(2030, 1, 3)) is True


def test_next_event_and_sort():
    nxt = next_event(EVENTS, "Fall 2026", DEMO_TODAY)
    assert nxt.event_type == "reading_day"
    assert nxt.start_date == date(2026, 12, 6)
    assert next_event(EVENTS, "Fall 2026", date(2027, 1, 1)) is None
    ordered = sort_events(EVENTS)
    previous = None
    for event in ordered:
        if previous is not None:
            assert previous <= event.start_date
        previous = event.start_date


# ---------- exam conflicts ----------

def make_exam(code, day, start, end):
    return ExamSlot(code, "Fall 2026", day, start, end, "R1", "in_person")


def test_same_date_overlap_is_hard():
    a = make_exam("CS101-A", date(2026, 12, 7), time(9, 0), time(11, 0))
    b = make_exam("CS210-A", date(2026, 12, 7), time(10, 0), time(12, 0))
    assert exams_overlap(a, b) is True
    result = detect_exam_conflicts([a, b], 3)
    assert len(result) == 1
    assert result[0].severity == SEVERITY_HARD
    assert result[0].sections == ("CS101-A", "CS210-A")


def test_back_to_back_is_not_a_conflict():
    a = make_exam("CS101-A", date(2026, 12, 7), time(9, 0), time(10, 0))
    b = make_exam("CS210-A", date(2026, 12, 7), time(10, 0), time(11, 0))  # starts exactly when a ends
    assert exams_overlap(a, b) is False
    assert detect_exam_conflicts([a, b], 3) == []


def test_different_dates_never_overlap():
    a = make_exam("CS101-A", date(2026, 12, 7), time(9, 0), time(11, 0))
    b = make_exam("CS210-A", date(2026, 12, 8), time(9, 0), time(11, 0))
    assert detect_exam_conflicts([a, b], 3) == []


def test_three_exams_in_one_day_is_soft_warning():
    day = date(2026, 12, 9)
    exams = [
        make_exam("A-A", day, time(8, 0), time(9, 0)),
        make_exam("B-A", day, time(10, 0), time(11, 0)),
        make_exam("C-A", day, time(13, 0), time(14, 0)),
    ]
    result = detect_exam_conflicts(exams, 3)
    assert len(result) == 1
    assert result[0].severity == SEVERITY_SOFT
    assert len(result[0].sections) == 3


def test_two_exams_below_limit_is_fine_and_limit_comes_from_data():
    day = date(2026, 12, 9)
    exams = [
        make_exam("A-A", day, time(8, 0), time(9, 0)),
        make_exam("B-A", day, time(10, 0), time(11, 0)),
    ]
    assert detect_exam_conflicts(exams, 3) == []
    assert len(detect_exam_conflicts(exams, 2)) == 1  # a stricter limit from the CSV


def test_conflict_to_dict_is_json_friendly():
    a = make_exam("CS101-A", date(2026, 12, 7), time(9, 0), time(11, 0))
    b = make_exam("CS210-A", date(2026, 12, 7), time(10, 0), time(12, 0))
    data = detect_exam_conflicts([a, b], 3)[0].to_dict()
    assert data["exam_date"] == "2026-12-07"
    assert data["sections"] == ["CS101-A", "CS210-A"]


# ---------- exam rules text ----------

def test_format_exam_rules_contains_every_fact():
    rules = ExamRules(
        term="Fall 2026",
        allowed_items=["pens", "pencils"],
        forbidden_items=["personal phones", "notes"],
        calculator_policy="Department-approved calculators only.",
        open_book_policy="Closed book unless declared in writing.",
        late_arrival_rule="Admitted up to 30 minutes after the start.",
        scheduling_limit_exams_per_day=3,
        scheduling_limit_conflict_note="Three or more exams on one day is flagged.",
    )
    text = format_exam_rules(rules)
    for expected in ["Fall 2026", "pens, pencils", "personal phones, notes", "Department-approved",
                     "Closed book", "30 minutes", "Three or more exams"]:
        assert expected in text
