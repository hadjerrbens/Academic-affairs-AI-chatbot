"""F5 grading and F6 transcripts. Three tools plus one service method.

Dependencies from other members are INJECTED, so nothing here imports their code:
  get_blocks_transcripts() -> list[str]   M2: standings that may not request transcripts
  propose(...)             -> str         M3: stores a pending action, returns its action_id
ASSUMPTION about M3's propose signature (agree it with M3):
  propose(user_id: str, action: str, payload: dict, summary: str) -> str"""
from __future__ import annotations

from typing import Any, Callable

from app.core.tools import ToolContext, ToolRegistry
from app.data.records_repo import RecordsRepo
from app.domain import records_engine as engine


class TranscriptNotAllowed(ValueError):
    """Raised by request_transcript when eligibility fails at confirm time."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class RecordsService:
    def __init__(
        self,
        repo: RecordsRepo,
        get_blocks_transcripts: Callable[[], list[str]],
        propose: Callable[[str, str, dict, str], str],
    ) -> None:
        self.repo = repo
        self._blocks = get_blocks_transcripts
        self._propose = propose

    # ---------------------------------------------------------- helpers
    def _eligibility(self, user: Any, today, kind: str | None = None, delivery: str | None = None) -> dict:
        return engine.check_transcript_eligibility(
            standing=getattr(user, "standing", None),
            blocks_transcripts=self._blocks(),
            has_unpaid_hold=bool(getattr(user, "has_unpaid_hold", False)),
            requests=self.repo.list_transcript_requests(user.id),
            today=today,
            kind=kind,
            delivery=delivery,
        )

    # ------------------------------------------------------------ tools
    def explain_grading_system(self, ctx: ToolContext, grade: str | None = None) -> dict:
        scale = self.repo.get_grade_scale()
        passing = self.repo.passing_points()
        if not grade:
            return engine.describe_scale(scale, passing)
        try:  # a letter ("A-") or a percentage ("91.5")
            try:
                letter = engine.band_for_percentage(float(grade), scale)
            except ValueError as not_a_number_or_range:
                if "between 0 and 100" in str(not_a_number_or_range):
                    raise
                letter = grade
            band = engine.explain_band(letter, scale, passing)
        except ValueError as exc:
            return {"error": "unknown_grade", "message": str(exc)}
        return {"bands": [band], "summary": band["summary"]}

    def check_transcript_eligibility(self, ctx: ToolContext) -> dict:
        result = self._eligibility(ctx.user, ctx.today)
        options = engine.transcript_options() if result["eligible"] else []
        if result["eligible"]:
            listing = "; ".join(
                f'{o["kind"]} by {o["delivery"]}: {o["fee"]} DZD, about {o["estimated_days"]} days'
                for o in options
            )
            summary = f"You can request a transcript. Options: {listing}."
        else:
            summary = "You cannot request a transcript right now: " + " ".join(result["blocking_reasons"])
        return {**result, "options": options, "summary": summary}

    def propose_transcript_request(self, ctx: ToolContext, kind: str, delivery: str) -> dict:
        """NEVER writes a request. It validates, checks eligibility and asks M3 to store a pending action."""
        try:
            fee = engine.transcript_fee(kind, delivery)
            days = engine.transcript_days(kind, delivery)
        except ValueError as exc:
            return {"error": "invalid_option", "message": str(exc)}

        eligibility = self._eligibility(ctx.user, ctx.today, kind, delivery)
        if not eligibility["eligible"]:
            return {
                "requires_confirmation": False,
                **eligibility,
                "summary": "This request cannot be made: " + " ".join(eligibility["blocking_reasons"]),
            }

        summary = f"Request an {kind} transcript by {delivery}: fee {fee} DZD, about {days} days."
        action_id = self._propose(ctx.user.id, "transcript_request", {"kind": kind, "delivery": delivery}, summary)
        return {
            "requires_confirmation": True,
            "action_id": action_id,
            "summary": summary,
            "fee": fee,
            "estimated_days": days,
        }

    # ----------------------------------------- service method (NOT a tool)
    def request_transcript(self, user: Any, kind: str, delivery: str, today) -> dict:
        """Called ONLY by M3's confirm endpoint. Re-runs eligibility, because things may have
        changed between the proposal and the confirmation."""
        eligibility = self._eligibility(user, today, kind, delivery)
        if not eligibility["eligible"]:
            raise TranscriptNotAllowed(eligibility["blocking_reasons"])
        fee = engine.transcript_fee(kind, delivery)  # raises ValueError for an invalid pair
        return self.repo.create_transcript_request(user.id, kind, delivery, fee, today)

    # ------------------------------------------------------ registration
    def register(self, registry: ToolRegistry) -> None:
        registry.tool(
            name="explain_grading_system",
            description="Explain the grading scale, or one grade (a letter like 'A-' or a percentage like '91.5').",
            parameters={
                "type": "object",
                "properties": {"grade": {"type": "string", "description": "Optional letter or percentage."}},
                "required": [],
            },
            areas=["grading"],
            public=True,
            safe_without_llm=True,
        )(self.explain_grading_system)

        registry.tool(
            name="check_transcript_eligibility",
            description="Check whether the logged-in student can request a transcript, and list the options with fees.",
            parameters={"type": "object", "properties": {}, "required": []},
            areas=["transcripts"],
            safe_without_llm=True,
        )(self.check_transcript_eligibility)

        registry.tool(
            name="propose_transcript_request",
            description="Prepare a transcript request for the student to confirm. It does NOT submit anything.",
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(engine.TRANSCRIPT_KINDS)},
                    "delivery": {"type": "string", "enum": list(engine.TRANSCRIPT_DELIVERIES)},
                },
                "required": ["kind", "delivery"],
            },
            areas=["transcripts"],
        )(self.propose_transcript_request)
