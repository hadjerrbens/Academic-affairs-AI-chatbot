"""M2 degree requirements and standing tools.

M4 owns the grade scale and tool registry. No business decision is made by the LLM:
GPA, standing and the degree audit are plain Python (requirement_engine.py).
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Callable

from app.data.progress_repo import ProgressRepo
from app.domain.requirement_engine import (
    audit_groups, best_attempts, calculate_gpa, classify_standing, format_audit_summary,
)


def _default_grade_points() -> dict[str, float]:
    from app.data.records_repo import get_grade_points_map  # M4 owns the scale
    return get_grade_points_map()


def _default_passing_points() -> float:
    from app.data.records_repo import passing_points  # M4 owns pass threshold
    return passing_points()


def _truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _text(value: Any) -> str:
    return str(value).upper()


def _student_id(user: Any) -> str | None:
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get("student_id") or user.get("id")
    return getattr(user, "student_id", None) or getattr(user, "id", None)


def _error(code: str, text: str) -> dict:
    return {"error": code, "message": text}


class ProgressService:
    def __init__(
        self,
        repo: ProgressRepo | None = None,
        *,
        grade_points_provider: Callable[[], dict[str, float]] | None = None,
        passing_points_provider: Callable[[], float] | None = None,
    ) -> None:
        self.repo = repo or ProgressRepo()
        self.grade_points_provider = grade_points_provider or _default_grade_points
        self.passing_points_provider = passing_points_provider or _default_passing_points

    def _gpa_data(self, record) -> tuple[float, int, int, list[dict]]:
        points_map = self.grade_points_provider()
        chosen = best_attempts(record.completed, points_map)
        gpa, earned, attempted = calculate_gpa(record.completed, points_map)
        return gpa, earned, attempted, chosen

    def get_standing_status(self, student_id: str) -> dict:
        """Sync hand-off for M1/M4; call outside the event loop when possible."""
        record = self.repo.get_student_record(student_id)
        if record is None:
            return _error("STUDENT_NOT_FOUND", "Student record not found.")
        if not record.program_code:
            return _error("NO_PROGRAM", "No degree program is assigned to this student.")
        policy = self.repo.get_standing_policy()
        gpa, earned, attempted, _ = self._gpa_data(record)
        status = classify_standing(gpa, policy)
        if status not in ("GOOD_STANDING", "WARNING", "PROBATION", "DISMISSAL"):
            return _error("RULES_ERROR", "Academic standing returned an unknown status.")
        blocked_reg = status in policy["blocks_registration"]
        blocked_tx = status in policy["blocks_transcripts"]
        return {
            "status": status,
            "cumulative_gpa": gpa,
            "credits_earned": earned,
            "credits_attempted": attempted,
            "blocks_registration": blocked_reg,
            "blocks_transcripts": blocked_tx,
            "message": f"Your standing is {status.replace('_', ' ').title()} (GPA {gpa:.2f}).",
            "appeal_window_days": policy["appeal_window_days"],
        }

    def get_standing_for_registration(self, student_id: str) -> tuple[bool, str]:
        """Adapter for M1's expected (blocks_registration, reason) callback."""
        result = self.get_standing_status(student_id)
        if "error" in result:
            # Fail closed; an unknown status should not silently allow registration.
            return True, result["message"]
        return result["blocks_registration"], result["message"]

    def get_blocks_transcripts(self) -> list[str]:
        """M4 hand-off: standings that block transcript requests, from the seed policy."""
        return list(self.repo.get_standing_policy()["blocks_transcripts"])

    async def get_major_requirements(self, ctx, program_code: str) -> dict:
        try:
            code = program_code.strip().upper()
            program = self.repo.get_program(code)
            if not program:
                return _error("PROGRAM_NOT_FOUND", f"Unknown program: {code}.")
            groups = self.repo.get_requirement_groups(code)
            lines = [
                f"{program['name']} ({code}) requires {int(program['total_credits_required'])} credits "
                f"and a minimum GPA of {float(program['min_gpa']):.2f}."
            ]
            for group in groups:
                kind = group["group_type"]
                count = group["min_courses"] if kind == "ELECTIVE" else len(group["courses"])
                rule = (
                    f"all {count} courses" if kind == "REQUIRED" else
                    f"at least {count} courses" if kind == "ELECTIVE" else
                    f"at least {group['min_credits']} credits"
                )
                lines.append(f"{group['title']} ({kind}): {rule}; pool: {', '.join(group['courses'])}.")
            return {"program": program, "groups": groups, "summary": "\n".join(lines)}
        except Exception:
            return _error("REQUIREMENTS_ERROR", "Unable to load program requirements.")

    def _audit(self, student_id: str) -> dict:
        record = self.repo.get_student_record(student_id)
        if record is None:
            return _error("STUDENT_NOT_FOUND", "Student record not found.")
        if not record.program_code:
            return _error("NO_PROGRAM", "No degree program is assigned to this student.")
        program = self.repo.get_program(record.program_code)
        if program is None:
            return _error("PROGRAM_NOT_FOUND", "The student's degree program does not exist.")
        groups = self.repo.get_requirement_groups(record.program_code)
        gpa, earned, attempted, chosen = self._gpa_data(record)
        # The approved CSV has no 'priority' column: groups are filled in CSV row order.
        eligible, reports = audit_groups(groups, chosen)
        group_views = []
        next_actions = []
        for row in reports:
            group = row["group"]
            gtype = group["group_type"]
            used_codes = [_text(c) for c in row["used"]]
            all_missing = [_text(c) for c in row["missing"]]
            result_group = {
                "group_id": group["group_id"],
                "title": group["title"],
                "group_type": gtype,
                "satisfied": row["satisfied"],
                "used_courses": used_codes,
                "missing_courses": all_missing if gtype == "REQUIRED" else [],
                "remaining_options": all_missing if gtype != "REQUIRED" else [],
            }
            if not result_group["satisfied"]:
                if gtype == "REQUIRED":
                    next_actions.append("Complete required courses: " + ", ".join(all_missing))
                elif gtype == "ELECTIVE":
                    needed = max(0, group["min_courses"] - len(used_codes))
                    next_actions.append(f"Complete {needed} more elective course(s) in {group['title']}")
                else:
                    used_credits = sum(int(c["credits"]) for c in chosen if c["code"] in set(used_codes))
                    needed = max(0, group["min_credits"] - used_credits)
                    next_actions.append(f"Earn {needed} more credits in {group['title']}")
            group_views.append(result_group)
        required = int(program["total_credits_required"])
        minimum_gpa = float(program["min_gpa"])
        if gpa < minimum_gpa:
            next_actions.append(f"Raise cumulative GPA to at least {minimum_gpa:.2f}")
        if earned < required:
            next_actions.append(f"Earn {required - earned} more total credits")
        audit = {
            "program_code": record.program_code,
            "percent_complete": min(1.0, earned / required) if required else 1.0,
            "cumulative_gpa": gpa,
            "credits_earned": earned,
            "credits_attempted": attempted,
            "credits_required": required,
            "min_gpa": minimum_gpa,
            "eligible_to_graduate": _truth(eligible),
            "groups": group_views,
            "next_actions": next_actions,
        }
        # Defense in depth: do not expose 'eligible' if no group or GPA/credits fails.
        audit["eligible_to_graduate"] = bool(
            audit["eligible_to_graduate"] and all(g["satisfied"] for g in group_views)
            and gpa >= minimum_gpa and earned >= required
        )
        audit["summary"] = format_audit_summary(audit)
        return audit

    async def audit_degree_progress(self, ctx) -> dict:
        student_id = _student_id(getattr(ctx, "user", None))
        if not student_id:
            return _error("LOGIN_REQUIRED", "Please log in to see your degree progress.")
        try:
            return await asyncio.to_thread(self._audit, student_id)
        except Exception:
            return _error("RULES_ERROR", "Unable to audit degree progress. Please try again later.")

    async def get_academic_standing(self, ctx) -> dict:
        student_id = _student_id(getattr(ctx, "user", None))
        if not student_id:
            return _error("LOGIN_REQUIRED", "Please log in to see your academic standing.")
        try:
            result = await asyncio.to_thread(self.get_standing_status, student_id)
            if "error" in result:
                return result
            appeal_date = None
            if result["status"] != "GOOD_STANDING":
                appeal_date = (
                    ctx.today + timedelta(days=result["appeal_window_days"])
                ).isoformat()
            message = result["message"]
            summary = (
                f"Academic standing: {result['status']}. Cumulative GPA: {result['cumulative_gpa']:.2f}. "
                f"Credits earned: {result['credits_earned']}; attempted: {result['credits_attempted']}. "
                f"Registration blocked: {'yes' if result['blocks_registration'] else 'no'}. "
                f"Transcripts blocked: {'yes' if result['blocks_transcripts'] else 'no'}."
            )
            if appeal_date:
                summary += f" Appeal deadline: {appeal_date}."
            return {**result, "appeal_deadline": appeal_date, "summary": summary, "message": message}
        except Exception:
            return _error("RULES_ERROR", "Unable to determine academic standing. Please try again later.")

    def register(self, registry) -> None:
        """Register exactly the three M2 tools in M4's existing ToolRegistry."""
        registry.tool(
            name="get_major_requirements",
            description="List the degree requirements for a program code (for example BS_CS).",
            parameters={
                "type": "object", "properties": {"program_code": {"type": "string"}},
                "required": ["program_code"],
            },
            areas=["degree_requirements"], public=True,
        )(self.get_major_requirements)
        registry.tool(
            name="audit_degree_progress",
            description="Audit the logged-in student's graduation progress and missing requirements.",
            parameters={"type": "object", "properties": {}, "required": []},
            areas=["degree_requirements"], safe_without_llm=True,
        )(self.audit_degree_progress)
        registry.tool(
            name="get_academic_standing",
            description="Show the logged-in student's GPA, academic standing and appeal deadline.",
            parameters={"type": "object", "properties": {}, "required": []},
            areas=["academic_standing"], safe_without_llm=True,
        )(self.get_academic_standing)


_DEFAULT = ProgressService()


def configure_progress_service(service: ProgressService) -> None:
    """M3 calls this at startup so M1 and M4 share the live, injected M2 service."""
    global _DEFAULT
    _DEFAULT = service


def get_standing_status(student_id: str) -> dict:
    """Public M2 hand-off. M1 may wrap get_standing_for_registration for tuple form."""
    return _DEFAULT.get_standing_status(student_id)


def get_standing_for_registration(student_id: str) -> tuple[bool, str]:
    return _DEFAULT.get_standing_for_registration(student_id)


def get_blocks_transcripts() -> list[str]:
    return _DEFAULT.get_blocks_transcripts()
