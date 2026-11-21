from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.data.enrollment_repo import EnrollmentError
from app.domain.registration_rules import Verdict
from app.services.enrollment_service import Deps, _section_view, evaluate

router = APIRouter(prefix="/enrollment", tags=["enrollment"])


# TODO: replace with the real ones from M2 (login) and your app wiring
def get_current_user() -> str:
    raise NotImplementedError("use M2's login dependency; it must return the student id")


def get_deps() -> Deps:
    raise NotImplementedError("build Deps once at startup and return it here")


class SectionRequest(BaseModel):
    section_code: str          # the user comes from the login, never from the body


@router.get("/sections")
def list_sections(course: str = Query(...), user_id: str = Depends(get_current_user),
                  deps: Deps = Depends(get_deps)):
    term = deps.registration_term()
    sections = deps.repo.get_sections(course.strip().upper(), term)
    return {"term": term, "sections": [_section_view(s) for s in sections]}


@router.post("/register")
def register(body: SectionRequest, user_id: str = Depends(get_current_user),
             deps: Deps = Depends(get_deps)):
    section = deps.repo.get_section(body.section_code)
    if section is None:
        raise HTTPException(404, f"Section {body.section_code} does not exist.")
    course = deps.repo.get_course(section.course_code)

    # always re-check on the server: never trust the button
    result = evaluate(deps, user_id, course, section)
    if result.verdict != Verdict.ELIGIBLE:
        raise HTTPException(409, {"verdict": result.verdict.value, "reason": result.reason})

    try:
        updated = deps.repo.enroll(user_id, section.code)
    except EnrollmentError as e:
        raise HTTPException(409, {"verdict": e.code, "reason": e.message})

    # later (real-time step): bus.publish(SeatUpdate(updated.code, updated.seats_left, updated.status))
    return {"ok": True, "section": _section_view(updated), "status": updated.status}


@router.post("/drop")
def drop(body: SectionRequest, user_id: str = Depends(get_current_user),
         deps: Deps = Depends(get_deps)):
    try:
        updated = deps.repo.drop(user_id, body.section_code)
    except EnrollmentError as e:
        raise HTTPException(409, {"verdict": e.code, "reason": e.message})
    # later: bus.publish(SeatUpdate(...))
    return {"ok": True, "section": _section_view(updated), "status": updated.status}