"""M5 tools: course substitution / waiver and proctoring. Handlers are (ctx, **args) so M4's registry can call them.
No Prolog: rules are plain Python over the CSV/Mongo tables (domain/policy_rules.py)."""
from __future__ import annotations

from app.data.policy_repo import PolicyRepo
from app.domain import policy_rules as rules
from app.domain.shared_models import parse_course_code


def _error(code: str, text: str) -> dict:
    return {"error": code, "message": text}


class PolicyService:
    def __init__(self, repo: PolicyRepo, student_repo) -> None:
        self.repo = repo
        self.student_repo = student_repo  # ProgressRepo: get_student_record(student_id)

    # ---------------------------------------------------------------- tools
    def explain_waiver_process(self, ctx) -> dict:
        docs: list[str] = []
        for rule in self.repo.substitution_rules().values():
            for d in rule["documents"]:
                if d not in docs:
                    docs.append(d)
        steps = ["Check that your substitute course is on the approved list for the course you want replaced.",
                 "Speak with your department advisor: every substitution or waiver needs advisor sign-off.",
                 "Bring: " + (", ".join(docs) if docs else "the documents your advisor asks for") + "."]
        summary = ("Substitutions and waivers are never automatic. Speak with your department advisor and bring "
                   + (", ".join(docs) if docs else "the documents your advisor asks for") + ".")
        return {"steps": steps, "required_documents": docs, "summary": summary}

    def check_waiver_eligibility(self, ctx, target_course: str, substitute_course: str) -> dict:
        try:
            target, substitute = parse_course_code(target_course), parse_course_code(substitute_course)
        except ValueError as exc:
            return _error("INVALID_COURSE", str(exc))
        record = self.student_repo.get_student_record(ctx.user.id)
        if record is None:
            return _error("STUDENT_NOT_FOUND", "Student record not found.")
        try:
            result = rules.evaluate_substitution(target, substitute, record.completed, self.repo.substitution_rules())
        except ValueError as exc:
            return _error("VALIDATION_ERROR", str(exc))
        summary = f"Verdict: {result['verdict']}. " + " ".join(result["reasons"])
        if result["required_documents"]:
            summary += " Documents needed: " + ", ".join(result["required_documents"]) + "."
        summary += " The final decision belongs to your department advisor."
        return {**result, "summary": summary}

    def get_proctoring_info(self, ctx, exam_type: str | None = None, course_code: str | None = None) -> dict:
        policies = self.repo.proctoring_policies()
        modes: list[str] = []
        if exam_type:
            modes = [rules.normalise_mode(exam_type)]
        elif course_code:
            try:
                code = parse_course_code(course_code)
            except ValueError as exc:
                return _error("INVALID_COURSE", str(exc))
            modes = self.repo.exam_modes_for_course(code, getattr(ctx, "current_term", None))
            if not modes:
                return _error("NOT_FOUND", f"No scheduled exam found for {code} this term.")
        else:
            modes = list(policies)  # no filter: describe every mode
        parts = [rules.describe_mode(m, policies) for m in modes]
        bad = [p for p in parts if "error" in p]
        if len(parts) == 1 and bad:
            return bad[0]
        good = [p for p in parts if "error" not in p]
        if len(good) == 1:
            return good[0]
        return {"policies": good, "summary": "\n".join(p["summary"] for p in good)}

    # ------------------------------------------------------------- registry
    def register(self, registry) -> None:
        registry.tool(
            name="explain_waiver_process",
            description="Explain how to ask for a course substitution or waiver and which documents to bring.",
            parameters={"type": "object", "properties": {}, "required": []},
            areas=["course_substitution"], public=True, safe_without_llm=True,
        )(self.explain_waiver_process)
        registry.tool(
            name="check_waiver_eligibility",
            description="Check whether the logged-in student's completed course can substitute a target course.",
            parameters={"type": "object", "properties": {
                "target_course": {"type": "string", "description": "Course to replace, e.g. BUS202"},
                "substitute_course": {"type": "string", "description": "Course already taken, e.g. BUS106"}},
                "required": ["target_course", "substitute_course"]},
            areas=["course_substitution"],
        )(self.check_waiver_eligibility)
        registry.tool(
            name="get_proctoring_info",
            description="Explain exam proctoring: ID rules, technical needs and rescheduling. Give an exam_type "
                        "(in_person, online, proctoring_centre) or a course_code; with neither, all modes are described.",
            parameters={"type": "object", "properties": {
                "exam_type": {"type": "string"}, "course_code": {"type": "string"}}, "required": []},
            areas=["proctoring"], public=True, safe_without_llm=True,
        )(self.get_proctoring_info)
