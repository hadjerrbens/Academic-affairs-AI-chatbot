"""
calendar_engine.py  (M3, domain layer, PURE)

"Pure" means three things:
  1. No I/O: it never touches the database, files or the network.
  2. No clock: it never calls date.today(). The caller passes `today` in.
     (Only core/config.py:get_today() may read the clock - contracts section 4.)
  3. Same input -> same output. That makes it very easy to test.

The service layer (calendar_service.py) loads the rows from Mongo, turns them
into the dataclasses below, and calls these functions.

NOTE: no list/dict comprehensions on purpose - plain loops only.
"""

from dataclasses import dataclass
from datetime import date, time


# ---------------------------------------------------------------------------
# 1. Names used everywhere (constants, so we never mistype a string)
# ---------------------------------------------------------------------------

# Event types as they appear in calendar_events.csv (always compared in lower case)
SEMESTER_START = "semester_start"
SEMESTER_END = "semester_end"
REGISTRATION_OPEN = "registration_open"
REGISTRATION_CLOSE = "registration_close"
ADD_DROP_DEADLINE = "add_drop_deadline"
EXAM_PERIOD_START = "exam_period_start"
EXAM_PERIOD_END = "exam_period_end"

# Phases of a term, in the order they happen
PHASE_BEFORE_REGISTRATION = "BEFORE_REGISTRATION"
PHASE_REGISTRATION_OPEN = "REGISTRATION_OPEN"
PHASE_REGISTRATION_CLOSED = "REGISTRATION_CLOSED"  # closed, classes not started yet
PHASE_ADD_DROP = "ADD_DROP"  # classes started, add/drop still allowed
PHASE_IN_SESSION = "IN_SESSION"
PHASE_EXAM_PERIOD = "EXAM_PERIOD"
PHASE_POST_EXAMS = "POST_EXAMS"  # exams over, semester not officially ended
PHASE_TERM_ENDED = "TERM_ENDED"

# One human sentence per phase (the tool's "summary" can reuse these)
PHASE_DESCRIPTIONS = {
    PHASE_BEFORE_REGISTRATION: "Registration for this term has not opened yet.",
    PHASE_REGISTRATION_OPEN: "Registration for this term is open.",
    PHASE_REGISTRATION_CLOSED: "Registration is closed and classes have not started yet.",
    PHASE_ADD_DROP: "Classes have started and the add/drop period is still running.",
    PHASE_IN_SESSION: "The term is in session.",
    PHASE_EXAM_PERIOD: "The exam period is running.",
    PHASE_POST_EXAMS: "Exams are over; the term has not officially ended yet.",
    PHASE_TERM_ENDED: "The term has ended.",
}

# Exam conflict labels
EXAM_CLASH = "EXAM_CLASH"
SEVERITY_HARD = "HARD"  # two exams overlap in time: impossible
SEVERITY_SOFT = "SOFT"  # too many exams on one day: only a warning


# ---------------------------------------------------------------------------
# 2. Data shapes (dataclasses = small, typed containers)
# ---------------------------------------------------------------------------
# frozen=True makes them read-only, so a function cannot change them by accident.

@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    term: str  # "Fall 2026"
    event_type: str  # "registration_open", ...
    name: str
    start_date: date
    end_date: date  # same as start_date for one-day events


@dataclass(frozen=True)
class ExamSlot:
    section_code: str  # "CS101-A"
    term: str
    exam_date: date
    start_time: time
    end_time: time
    room: str
    proctoring_type: str  # M5's get_proctoring_info joins on this

    @property
    def course_code(self):
        # "CS101-A" -> "CS101"
        return self.section_code.split("-")[0]


@dataclass(frozen=True)
class ExamConflict:
    kind: str  # always EXAM_CLASH here
    severity: str  # HARD or SOFT
    exam_date: date
    sections: tuple  # section codes involved
    detail: str  # one human sentence

    def to_dict(self):
        # Plain dict so the tool result is JSON-serialisable (contracts section 2)
        return {
            "kind": self.kind,
            "severity": self.severity,
            "exam_date": self.exam_date.isoformat(),
            "sections": list(self.sections),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ExamRules:
    term: str
    allowed_items: list
    forbidden_items: list
    calculator_policy: str
    open_book_policy: str
    late_arrival_rule: str
    scheduling_limit_exams_per_day: int  # warn when a student has this many or more
    scheduling_limit_conflict_note: str


# ---------------------------------------------------------------------------
# 3. Small helpers
# ---------------------------------------------------------------------------

def normalise_event_type(raw):
    """'Registration Open', 'REGISTRATION_OPEN ' and 'registration_open' -> same key."""
    return raw.strip().lower().replace(" ", "_")


def find_event(events, term, event_type):
    """First event of this term and type, or None if the calendar has no such event."""
    wanted = normalise_event_type(event_type)
    for event in events:
        if event.term == term and normalise_event_type(event.event_type) == wanted:
            return event
    return None


def _start_of(events, term, event_type):
    event = find_event(events, term, event_type)
    if event is None:
        return None
    return event.start_date


def _end_of(events, term, event_type):
    # For a multi-day event (e.g. a break) the LAST day is end_date.
    event = find_event(events, term, event_type)
    if event is None:
        return None
    return event.end_date


def list_terms(events):
    """
    All distinct terms, oldest first. 'Oldest' = the term whose earliest event is earliest.
    Example: Fall 2026 (Apr 2026), Spring 2027 (Oct 2026), Fall 2027 (Apr 2027).
    """
    earliest = {}  # term -> earliest date we saw
    for event in events:
        if event.term not in earliest or event.start_date < earliest[event.term]:
            earliest[event.term] = event.start_date

    pairs = []
    for term in earliest:
        pairs.append((term, earliest[term]))
    pairs.sort(key=lambda pair: pair[1])  # sort by the date

    terms = []
    for pair in pairs:
        terms.append(pair[0])
    return terms


def get_term_window(events, term):
    """(first day of classes, last day of semester), or None if either date is missing."""
    start = _start_of(events, term, SEMESTER_START)
    end = _end_of(events, term, SEMESTER_END)
    if start is None or end is None:
        return None
    return (start, end)


def get_registration_window(events, term):
    """(first day registration is open, LAST day it is open), or None."""
    opens = _start_of(events, term, REGISTRATION_OPEN)
    closes = _end_of(events, term, REGISTRATION_CLOSE)
    if opens is None or closes is None:
        return None
    return (opens, closes)


# ---------------------------------------------------------------------------
# 4. The two kinds of "current term"  (M3 rules, first bullet)
# ---------------------------------------------------------------------------

def current_term(events, today):
    """
    The term whose SEMESTER window (start..end, both days included) contains today.
    Used for calendar questions ("when is the add/drop deadline?").

    Between two semesters no window contains today. Rule I chose (agree it with the team):
      1) a window contains today -> that term
      2) otherwise the NEXT term that starts after today
      3) otherwise (everything is over) the most recent term
      4) no term has a window at all -> None
    """
    terms = list_terms(events)

    for term in terms:
        window = get_term_window(events, term)
        if window is not None and window[0] <= today <= window[1]:
            return term

    next_term = None
    next_start = None
    for term in terms:
        window = get_term_window(events, term)
        if window is not None and window[0] > today:
            if next_start is None or window[0] < next_start:
                next_term = term
                next_start = window[0]
    if next_term is not None:
        return next_term

    last_term = None
    last_end = None
    for term in terms:
        window = get_term_window(events, term)
        if window is not None:
            if last_end is None or window[1] > last_end:
                last_term = term
                last_end = window[1]
    return last_term


def registration_term(events, today):
    """
    The term students are registering FOR (M1 uses this, not current_term).
      1) a term whose registration window is open today -> that term
      2) otherwise the term whose registration opens next
      3) nothing upcoming -> None
    """
    terms = list_terms(events)

    for term in terms:
        window = get_registration_window(events, term)
        if window is not None and window[0] <= today <= window[1]:
            return term

    best_term = None
    best_open = None
    for term in terms:
        window = get_registration_window(events, term)
        if window is not None and window[0] > today:
            if best_open is None or window[0] < best_open:
                best_term = term
                best_open = window[0]
    return best_term


def is_registration_open(events, term, today):
    """
    True only from the open date to the close date, BOTH days included.
    NO GRACE DAYS: the day after the close date is closed.
    The service wraps this as is_registration_open(term, today) for M1.
    """
    window = get_registration_window(events, term)
    if window is None:
        return False  # no dates published -> not open
    return window[0] <= today <= window[1]


# ---------------------------------------------------------------------------
# 5. Phase of a term
# ---------------------------------------------------------------------------

def resolve_phase(events, term, today):
    """
    Where are we in `term` today? Checked from the earliest phase to the latest;
    the first test that matches wins. Every boundary date is inclusive on the
    LAST day of a phase (close date -> still open, add/drop day -> still add/drop).
    """
    reg_open = _start_of(events, term, REGISTRATION_OPEN)
    reg_close = _end_of(events, term, REGISTRATION_CLOSE)
    sem_start = _start_of(events, term, SEMESTER_START)
    add_drop = _end_of(events, term, ADD_DROP_DEADLINE)
    exam_start = _start_of(events, term, EXAM_PERIOD_START)
    exam_end = _end_of(events, term, EXAM_PERIOD_END)
    sem_end = _end_of(events, term, SEMESTER_END)

    if reg_open is not None and reg_close is not None:
        if today < reg_open:
            return PHASE_BEFORE_REGISTRATION
        if today <= reg_close:
            return PHASE_REGISTRATION_OPEN

    # Semester dates not published yet (e.g. Fall 2027) -> registration closed, nothing more known
    if sem_start is None or today < sem_start:
        return PHASE_REGISTRATION_CLOSED

    if add_drop is not None and today <= add_drop:
        return PHASE_ADD_DROP
    if exam_start is not None and today < exam_start:
        return PHASE_IN_SESSION
    if exam_end is not None and today <= exam_end:
        return PHASE_EXAM_PERIOD
    if sem_end is not None and today <= sem_end:
        return PHASE_POST_EXAMS
    return PHASE_TERM_ENDED


def next_event(events, term, today):
    """The nearest event of this term that starts today or later, or None."""
    best = None
    for event in events:
        if event.term != term:
            continue
        if event.start_date < today:
            continue
        if best is None or event.start_date < best.start_date:
            best = event
    return best


def sort_events(events):
    """Events by start date (the calendar tool returns them sorted)."""
    result = list(events)
    result.sort(key=lambda event: (event.start_date, event.event_id))
    return result


# ---------------------------------------------------------------------------
# 6. Exam conflicts
# ---------------------------------------------------------------------------

def _minutes(clock):
    return clock.hour * 60 + clock.minute


def exams_overlap(a, b):
    """
    Same date AND the time ranges intersect.
    Strict '<' means back-to-back exams (10:00-11:00 then 11:00-12:00) do NOT overlap.
    """
    if a.exam_date != b.exam_date:
        return False
    return _minutes(a.start_time) < _minutes(b.end_time) and _minutes(b.start_time) < _minutes(a.end_time)


def _clock_text(clock):
    return clock.strftime("%H:%M")


def detect_exam_conflicts(exams, max_exams_per_day):
    """
    exams: ExamSlot list for ONE student.
    max_exams_per_day: from exam_rules.csv (scheduling_limit_exams_per_day) - never hard-coded.

    HARD: two exams on the same date with overlapping times.
    SOFT: max_exams_per_day or more exams on the same date.
    """
    ordered = list(exams)
    ordered.sort(key=lambda exam: (exam.exam_date, _minutes(exam.start_time), exam.section_code))

    conflicts = []

    # HARD: compare every pair once (i < j)
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            first = ordered[i]
            second = ordered[j]
            if exams_overlap(first, second):
                detail = (
                    first.section_code + " (" + _clock_text(first.start_time) + "-" + _clock_text(first.end_time)
                    + ") overlaps " + second.section_code + " (" + _clock_text(second.start_time) + "-"
                    + _clock_text(second.end_time) + ") on " + first.exam_date.isoformat() + "."
                )
                conflicts.append(ExamConflict(
                    kind=EXAM_CLASH,
                    severity=SEVERITY_HARD,
                    exam_date=first.exam_date,
                    sections=(first.section_code, second.section_code),
                    detail=detail,
                ))

    # SOFT: group exams by date, then count
    by_date = {}
    for exam in ordered:
        if exam.exam_date not in by_date:
            by_date[exam.exam_date] = []
        by_date[exam.exam_date].append(exam)

    if max_exams_per_day > 0:
        for day in sorted(by_date):
            todays = by_date[day]
            if len(todays) >= max_exams_per_day:
                codes = []
                for exam in todays:
                    codes.append(exam.section_code)
                detail = (
                    str(len(todays)) + " exams on " + day.isoformat() + " (" + ", ".join(codes)
                    + "); " + str(max_exams_per_day) + " or more in one day is flagged as a scheduling warning."
                )
                conflicts.append(ExamConflict(
                    kind=EXAM_CLASH,
                    severity=SEVERITY_SOFT,
                    exam_date=day,
                    sections=tuple(codes),
                    detail=detail,
                ))

    return conflicts


# ---------------------------------------------------------------------------
# 7. Exam rules text
# ---------------------------------------------------------------------------

def _join(items):
    return ", ".join(items)


def format_exam_rules(rules):
    """
    ONE text block with every fact the bot may state about exam-day rules.
    ID requirements are NOT here: they belong to M5's proctoring policy.
    """
    lines = []
    lines.append("Exam-day rules for " + rules.term + ":")
    lines.append("- Allowed items: " + _join(rules.allowed_items) + ".")
    lines.append("- Forbidden items: " + _join(rules.forbidden_items) + ".")
    lines.append("- Calculators: " + rules.calculator_policy)
    lines.append("- Open-book: " + rules.open_book_policy)
    lines.append("- Late arrival: " + rules.late_arrival_rule)
    if rules.scheduling_limit_conflict_note:
        lines.append("- Scheduling: " + rules.scheduling_limit_conflict_note)
    else:
        lines.append(
            "- Scheduling: " + str(rules.scheduling_limit_exams_per_day)
            + " or more exams on one day is flagged as a scheduling warning."
        )
    return "\n".join(lines)
