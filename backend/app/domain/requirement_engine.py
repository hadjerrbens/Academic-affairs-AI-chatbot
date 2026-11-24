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
