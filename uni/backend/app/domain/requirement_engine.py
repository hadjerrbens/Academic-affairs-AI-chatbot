"""Pure M2 GPA calculations and audit summary. All academic decisions live in Prolog.

This is the ONLY GPA calculator in the project.
"""
from __future__ import annotations


def _value(course, key, default=None):
    return course.get(key, default) if isinstance(course, dict) else getattr(course, key, default)


def best_attempts(courses, points_map, repeat_policy="BEST"):
    if repeat_policy != "BEST":
        raise ValueError("Only the approved BEST repeat policy is supported")
    selected = {}
    for course in courses:
        grade = str(_value(course, "grade", "")).strip().upper()
        status = str(_value(course, "status", "COMPLETED")).strip().upper()
        if grade in ("I", "W") or status in ("IN_PROGRESS", "INCOMPLETE", "WITHDRAWN"):
            continue
        if status != "COMPLETED":
            continue
        if grade not in points_map:
            raise ValueError("Unknown grade in transcript: " + grade)
        code = str(_value(course, "course_code"))
        credits = int(_value(course, "credits"))
        if credits < 0:
            raise ValueError("Course credits must not be negative")
        points = float(points_map[grade])
        # Stable tie-breaking: first attempt wins if grade points are equal.
        if code not in selected or points > selected[code]["points"]:
            selected[code] = {"code": code, "credits": credits, "points": points, "grade": grade}
    return list(selected.values())


def calculate_gpa(courses, points_map, repeat_policy="BEST"):
    """Return (GPA, credits earned, credits attempted). F is attempted, I/W excluded."""
    selected = best_attempts(courses, points_map, repeat_policy)
    attempted = sum(row["credits"] for row in selected)
    earned = sum(row["credits"] for row in selected if row["points"] >= float(points_map["D"]))
    if attempted == 0:
        return 0.0, 0, 0
    gpa = sum(row["credits"] * row["points"] for row in selected) / attempted
    return gpa, earned, attempted


def format_audit_summary(audit):
    """An answer-ready text block; the language model does no arithmetic."""
    lines = [
        f"Program: {audit['program_code']}.",
        f"Cumulative GPA: {audit['cumulative_gpa']:.2f} (minimum {audit['min_gpa']:.2f}).",
        f"Credits earned: {audit['credits_earned']} / {audit['credits_required']}.",
        f"Degree progress: {audit['percent_complete']:.1%}.",
    ]
    for group in audit["groups"]:
        state = "satisfied" if group["satisfied"] else "not satisfied"
        line = f"{group['group_id']}: {state}; used: {', '.join(group['used_courses']) or 'none'}."
        if group["missing_courses"]:
            line += " Missing: " + ", ".join(group["missing_courses"]) + "."
        lines.append(line)
    lines.append("Graduation eligibility: " + ("yes" if audit["eligible_to_graduate"] else "no") + ".")
    if audit["next_actions"]:
        lines.append("Next actions: " + "; ".join(audit["next_actions"]) + ".")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Standing and degree audit: plain Python (these two replaced the Prolog rules).
# --------------------------------------------------------------------------
def classify_standing(gpa: float, policy: dict) -> str:
    """Exact thresholds come from standing_policies.csv; a GPA on a threshold gets the better status."""
    if gpa >= policy["good_standing_min_gpa"]:
        return "GOOD_STANDING"
    if gpa >= policy["warning_min_gpa"]:
        return "WARNING"
    if gpa >= policy["probation_min_gpa"]:
        return "PROBATION"
    return "DISMISSAL"


def audit_groups(groups: list[dict], chosen: list[dict]) -> tuple[bool, list[dict]]:
    """Fill requirement groups in the given (CSV row) order. A passed course counts for ONE group only.

    groups: [{group_id, group_type: REQUIRED|ELECTIVE|CREDITS, min_courses, min_credits,
              min_grade_points, courses: [codes]}]
    chosen: best attempts from best_attempts(): [{code, credits, points, grade}]
    Returns (all_groups_satisfied, [{group, satisfied, used, missing}]).
    """
    by_code = {row["code"]: row for row in chosen}
    seen: set[str] = set()
    reports = []
    for group in groups:
        pool = group["courses"]
        candidates = [code for code in pool
                      if code in by_code and code not in seen
                      and by_code[code]["points"] >= group["min_grade_points"]]
        kind = group["group_type"]
        if kind == "REQUIRED":
            used = candidates
            satisfied = len(used) == len(pool)
        elif kind == "ELECTIVE":
            used = candidates[:group["min_courses"]]
            satisfied = len(used) >= group["min_courses"]
        else:  # CREDITS
            used, total = [], 0
            for code in candidates:
                if total >= group["min_credits"]:
                    break
                used.append(code)
                total += by_code[code]["credits"]
            satisfied = total >= group["min_credits"]
        seen.update(used)
        reports.append({"group": group, "satisfied": satisfied, "used": list(used),
                        "missing": [c for c in pool if c not in used]})
    return all(r["satisfied"] for r in reports), reports
