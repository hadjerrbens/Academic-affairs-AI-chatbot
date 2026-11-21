import asyncio
from dataclasses import dataclass
from datetime import date

import pytest

from app.core.tools import ToolContext, ToolRegistry
from app.data import records_repo
from app.data.records_repo import RecordsRepo
from app.services.records_service import RecordsService, TranscriptNotAllowed

TODAY = date(2026, 11, 21)


@dataclass
class User:
    id: str = "s1"
    standing: str = "Good standing"
    has_unpaid_hold: bool = False


def make(blocks=("Academic probation",)):
    repo = RecordsRepo()
    proposals = []

    def propose(user_id, action, payload, summary):
        proposals.append((user_id, action, payload, summary))
        return "act-1"

    service = RecordsService(repo, lambda: list(blocks), propose)
    return service, repo, proposals


def ctx(user=None):
    return ToolContext(user=user, today=TODAY, registration_term="2027S", current_term="2026F")


def test_grade_points_map_and_passing_points_for_m2():
    points = records_repo.get_grade_points_map()
    assert points["A"] == 4.0 and points["A-"] == 3.7 and points["F"] == 0.0 and len(points) == 11
    assert records_repo.passing_points() == 1.0


def test_explain_whole_scale_and_one_grade_and_percentage():
    service, _, _ = make()
    scale = service.explain_grading_system(ctx())
    assert len(scale["bands"]) == 11 and "A-" in scale["summary"]
    assert "90.0\u201392.9" in service.explain_grading_system(ctx(), "a-")["summary"]
    assert service.explain_grading_system(ctx(), "91.5")["bands"][0]["letter"] == "A-"
    assert service.explain_grading_system(ctx(), "Z")["error"] == "unknown_grade"
    assert service.explain_grading_system(ctx(), "150")["error"] == "unknown_grade"


def test_check_eligibility_tool():
    service, _, _ = make()
    ok = service.check_transcript_eligibility(ctx(User()))
    assert ok["eligible"] and ok["options"] and "DZD" in ok["summary"]
    blocked = service.check_transcript_eligibility(ctx(User(standing="Academic probation")))
    assert not blocked["eligible"] and blocked["options"] == [] and blocked["blocking_reasons"]


def test_propose_creates_nothing_and_calls_m3_propose():
    service, repo, proposals = make()
    result = service.propose_transcript_request(ctx(User()), "official", "pickup")
    assert result["requires_confirmation"] is True and result["action_id"] == "act-1"
    assert result["fee"] == 200 and result["estimated_days"] == 3
    assert repo.list_transcript_requests("s1") == []  # nothing written
    assert proposals == [("s1", "transcript_request", {"kind": "official", "delivery": "pickup"}, result["summary"])]


def test_propose_rejects_invalid_and_ineligible_without_calling_propose():
    service, repo, proposals = make()
    assert service.propose_transcript_request(ctx(User()), "official", "email")["error"] == "invalid_option"
    blocked = service.propose_transcript_request(ctx(User(standing="Academic probation")), "official", "pickup")
    assert blocked["requires_confirmation"] is False and blocked["blocking_reasons"]
    assert proposals == [] and repo.list_transcript_requests("s1") == []


def test_request_transcript_writes_and_blocks_duplicates():
    service, repo, _ = make()
    record = service.request_transcript(User(), "official", "pickup", TODAY)
    assert record["fee"] == 200 and len(repo.list_transcript_requests("s1")) == 1
    with pytest.raises(TranscriptNotAllowed):  # same request again the same day
        service.request_transcript(User(), "official", "pickup", TODAY)


def test_request_transcript_rechecks_eligibility_at_confirm_time():
    blocks: list[str] = []
    repo = RecordsRepo()
    service = RecordsService(repo, lambda: blocks, lambda *a: "act-1")
    user = User(standing="Academic probation")
    assert service.propose_transcript_request(ctx(user), "official", "pickup")["requires_confirmation"]
    blocks.append("Academic probation")  # policy changed between proposal and confirmation
    with pytest.raises(TranscriptNotAllowed):
        service.request_transcript(user, "official", "pickup", TODAY)
    assert repo.list_transcript_requests("s1") == []


def test_tools_register_without_student_id_and_work_through_the_registry():
    service, _, _ = make()
    registry = ToolRegistry()
    service.register(registry)
    assert {t.name for t in registry.all_tools()} == {
        "explain_grading_system", "check_transcript_eligibility", "propose_transcript_request"}
    assert "student_id" not in str([t.spec() for t in registry.all_tools()])
    out = asyncio.run(registry.execute("propose_transcript_request", '{"kind": "official", "delivery": "pickup"}',
                                       ctx(User())))
    assert out["requires_confirmation"]
    # not logged in -> login_required, and nothing is proposed
    out = asyncio.run(registry.execute("check_transcript_eligibility", {}, ctx(None)))
    assert out["error"] == "login_required"
