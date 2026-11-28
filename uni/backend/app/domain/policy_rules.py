"""Substitution and proctoring rules: pure functions, no I/O, no Prolog.
The rule tables come from substitution_rules.csv / proctoring_policies.csv (via PolicyRepo)."""
from __future__ import annotations

from typing import Any, Iterable

LIKELY_ELIGIBLE = "likely_eligible"
LIKELY_INELIGIBLE = "likely_ineligible"
NEEDS_ADVISOR = "needs_advisor_review"


def _get(course: Any, key: str, default=None):
    return course.get(key, default) if isinstance(course, dict) else getattr(course, key, default)


def _best_attempt(completed: Iterable[Any], code: str) -> dict | None:
    best = None
    for c in completed:
        if str(_get(c, "course_code", "")).upper() != code:
            continue
        if str(_get(c, "status", "completed")).lower() != "completed":
            continue
        points = _get(c, "grade_points")
        points = float(points) if points not in (None, "") else 0.0
        if best is None or points > best["points"]:
            best = {"points": points, "credits": int(_get(c, "credits", 0))}
    return best


def evaluate_substitution(target: str, substitute: str, completed: Iterable[Any], rules: dict[str, dict]) -> dict:
    target, substitute = target.upper(), substitute.upper()
    if target == substitute:
        raise ValueError("Target course and substitute course cannot be the same.")
    rule = rules.get(target)
    if rule is None:
        return {"verdict": NEEDS_ADVISOR, "reasons": [f"There is no pre-approved substitution rule for {target}."],
                "required_documents": []}
    docs = list(rule["documents"])
    if substitute not in rule["accepted"]:
        return {"verdict": LIKELY_INELIGIBLE, "required_documents": docs,
                "reasons": [f"{substitute} is not on the approved substitute list for {target}."]}
    taken = _best_attempt(completed, substitute)
    if taken is None:
        return {"verdict": LIKELY_INELIGIBLE, "required_documents": docs,
                "reasons": [f"You have not completed {substitute}."]}
    reasons = []
    if taken["points"] < rule["min_grade_points"]:
        reasons.append(f"Your grade in {substitute} ({taken['points']:.1f} points) is below the minimum "
                       f"{rule['min_grade_points']:.1f} ({rule['min_grade_letter']}).")
    if taken["credits"] < rule["min_credits"]:
        reasons.append(f"{substitute} is worth {taken['credits']} credits; at least {rule['min_credits']} credits are required.")
    if reasons:
        return {"verdict": LIKELY_INELIGIBLE, "reasons": reasons, "required_documents": docs}
    return {"verdict": LIKELY_ELIGIBLE, "required_documents": docs,
            "reasons": [f"{substitute} meets the grade and credit minimums for {target}. {rule['advisor_note']}".strip()]}


_MODE_ALIASES = {"inperson": "in_person", "onsite": "in_person", "oncampus": "in_person",
                 "online": "online", "remote": "online",
                 "proctoringcentre": "proctoring_centre", "proctoringcenter": "proctoring_centre",
                 "centre": "proctoring_centre", "center": "proctoring_centre", "testingcentre": "proctoring_centre"}


def normalise_mode(text: str) -> str:
    key = "".join(ch for ch in str(text).lower() if ch.isalpha())
    return _MODE_ALIASES.get(key, str(text).strip().lower().replace("-", "_").replace(" ", "_"))


def describe_mode(mode: str, policies: dict[str, dict]) -> dict:
    row = policies.get(mode)
    if row is None:
        return {"error": "NOT_FOUND", "message": f"No proctoring policy found for mode '{mode}'."}
    tech = row.get("technical_requirements", "")
    tech = "" if str(tech).strip().lower() == "none" else str(tech)
    summary = (f"{mode.replace('_', ' ').title()} proctoring ({row['provider']}), at: {row['location']}. "
               f"ID: {row['id_requirements']} " + (f"Technical: {tech} " if tech else "") +
               f"Rescheduling: {row['reschedule_policy']}")
    return {"mode": mode, "provider": row["provider"], "location": row["location"],
            "id_requirements": row["id_requirements"], "technical_requirements": tech or None,
            "reschedule_policy": row["reschedule_policy"], "summary": summary.strip()}
