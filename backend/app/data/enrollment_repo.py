from pymongo.errors import DuplicateKeyError

from app.domain.shared_models import Course, Section, parse_schedule


class EnrollmentError(Exception):
    """Business error with a stable code. The service layer turns it into a summary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _split_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    parts = str(value).replace("|", ";").split(";")
    return [p.strip() for p in parts if p.strip()]


def _to_course(doc: dict) -> Course:
    return Course(
        code=doc["code"],
        title=doc["title"],
        credits=int(doc["credits"]),
        level=int(doc["level"]),
        prereqs=_split_list(doc.get("prereqs")),
        terms_offered=_split_list(doc.get("terms_offered")),
    )


def _to_section(doc: dict) -> Section:
    schedule = doc.get("schedule", [])
    if isinstance(schedule, str):          # CSV-style string
        schedule = parse_schedule(schedule)
    return Section(
        code=doc["code"],
        course_code=doc["course_code"],
        term=doc["term"],
        instructor=doc.get("instructor", ""),
        schedule=schedule,
        capacity=int(doc["capacity"]),
        enrolled_count=int(doc.get("enrolled_count", 0)),
        status=doc.get("status", "OPEN"),
    )


class EnrollmentRepo:
    def __init__(self, db):
        self.courses = db["courses"]
        self.sections = db["sections"]
        self.enrollments = db["enrollments"]

    def ensure_indexes(self) -> None:
        """Call once at startup. One enrollment per student per course per term."""
        self.enrollments.create_index(
            [("student_id", 1), ("course_code", 1), ("term", 1)],
            unique=True,
            name="uniq_student_course_term",
        )
        self.sections.create_index("code", unique=True)

    # ---------- reads ----------
    def get_course(self, course_code: str) -> Course | None:
        doc = self.courses.find_one({"code": course_code})
        return _to_course(doc) if doc else None

    def get_section(self, section_code: str) -> Section | None:
        doc = self.sections.find_one({"code": section_code})
        return _to_section(doc) if doc else None

    def get_sections(self, course_code: str, term: str) -> list[Section]:
        docs = self.sections.find({"course_code": course_code, "term": term})
        return [_to_section(d) for d in docs]

    def get_student_sections(self, student_id: str, term: str) -> list[Section]:
        """Sections the student is registered in for this term (M3 needs this)."""
        rows = list(self.enrollments.find(
            {"student_id": student_id, "term": term, "status": "enrolled"}
        ))
        codes = [r["section_code"] for r in rows]
        if not codes:
            return []
        docs = self.sections.find({"code": {"$in": codes}})
        return [_to_section(d) for d in docs]

    # ---------- writes ----------
    def enroll(self, student_id: str, section_code: str) -> Section:
        """Register the student. Raises EnrollmentError. Seats never exceed capacity."""
        doc = self.sections.find_one({"code": section_code})
        if not doc:
            raise EnrollmentError("SECTION_NOT_FOUND", f"Section {section_code} does not exist.")
        sec = _to_section(doc)
        if sec.status in ("CLOSED", "CANCELLED") or sec.seats_left <= 0:
            raise EnrollmentError("SECTION_FULL", f"Section {section_code} has no seats available.")

        # 1) enrollment row first: the unique index blocks a second registration
        try:
            ins = self.enrollments.insert_one({
                "student_id": student_id,
                "section_code": sec.code,
                "course_code": sec.course_code,
                "term": sec.term,
                "status": "enrolled",
            })
        except DuplicateKeyError:
            raise EnrollmentError(
                "ALREADY_ENROLLED", f"You are already enrolled in {sec.course_code}."
            )

        # 2) take a seat atomically; the filter is the capacity guard
        res = self.sections.update_one(
            {"code": sec.code, "enrolled_count": {"$lt": sec.capacity}},
            {"$inc": {"enrolled_count": 1}},
        )
        if res.modified_count == 0:
            self.enrollments.delete_one({"_id": ins.inserted_id})   # roll back
            raise EnrollmentError("SECTION_FULL", f"Section {section_code} has no seats available.")

        # 3) mark FULL if that was the last seat
        self.sections.update_one(
            {"code": sec.code, "enrolled_count": {"$gte": sec.capacity}, "status": "OPEN"},
            {"$set": {"status": "FULL"}},
        )
        return self.get_section(sec.code)

    def drop(self, student_id: str, section_code: str) -> Section:
        """Unregister. Raises EnrollmentError if the student is not in that section."""
        doc = self.sections.find_one({"code": section_code})
        if not doc:
            raise EnrollmentError("SECTION_NOT_FOUND", f"Section {section_code} does not exist.")
        sec = _to_section(doc)

        res = self.enrollments.delete_one({
            "student_id": student_id, "section_code": sec.code, "status": "enrolled",
        })
        if res.deleted_count == 0:
            raise EnrollmentError("NOT_ENROLLED", f"You are not enrolled in {section_code}.")

        self.sections.update_one(
            {"code": sec.code, "enrolled_count": {"$gt": 0}},
            {"$inc": {"enrolled_count": -1}},
        )
        self.sections.update_one(
            {"code": sec.code, "status": "FULL", "enrolled_count": {"$lt": sec.capacity}},
            {"$set": {"status": "OPEN"}},
        )
        return self.get_section(sec.code)