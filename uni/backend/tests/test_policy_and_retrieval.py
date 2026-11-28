from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.retrieval import keyword_score, rank
from app.data.policy_repo import PolicyRepo
from app.domain import policy_rules as rules
from app.services.policy_service import PolicyService

SEED = Path(__file__).resolve().parents[2] / "data" / "seed"
REPO = PolicyRepo(seed_dir=SEED)


def done(code, points, credits):
    return {"course_code": code, "grade_points": points, "credits": credits, "status": "completed"}


def test_golden_m5_01_bus106_cannot_replace_bus202_credits():
    r = rules.evaluate_substitution("BUS202", "BUS106", [done("BUS106", 3.7, 1)], REPO.substitution_rules())
    assert r["verdict"] == "likely_ineligible"
    assert "credits" in " ".join(r["reasons"])


def test_eligible_and_documents_come_from_csv():
    r = rules.evaluate_substitution("BUS202", "BUS207", [done("BUS207", 3.0, 3)], REPO.substitution_rules())
    assert r["verdict"] == "likely_eligible"
    assert r["required_documents"] == ["official transcript", "signed substitution form"]


def test_not_on_list_not_taken_low_grade_same_course():
    rs = REPO.substitution_rules()
    assert rules.evaluate_substitution("BUS202", "CS101", [done("CS101", 4.0, 3)], rs)["verdict"] == "likely_ineligible"
    assert "not completed" in rules.evaluate_substitution("BUS202", "BUS207", [], rs)["reasons"][0]
    assert rules.evaluate_substitution("BUS202", "BUS207", [done("BUS207", 1.0, 3)], rs)["verdict"] == "likely_ineligible"
    assert rules.evaluate_substitution("ZZZ999", "BUS207", [], rs)["verdict"] == "needs_advisor_review"
    with pytest.raises(ValueError):
        rules.evaluate_substitution("BUS202", "bus202", [], rs)


def test_waiver_process_summary_has_the_documents():
    s = PolicyService(REPO, student_repo=None).explain_waiver_process(None)
    for word in ("advisor", "official transcript", "signed substitution form"):
        assert word in s["summary"]


def test_proctoring_modes_and_aliases():
    svc = PolicyService(REPO, student_repo=None)
    out = svc.get_proctoring_info(None, exam_type="in-person")
    assert out["mode"] == "in_person" and "photo ID" in out["summary"]
    assert svc.get_proctoring_info(None, exam_type="Proctoring Centre")["mode"] == "proctoring_centre"
    assert len(svc.get_proctoring_info(None)["policies"]) == 3
    assert svc.get_proctoring_info(None, exam_type="telepathy")["error"] == "NOT_FOUND"


def test_check_waiver_uses_the_real_student_record():
    record = SimpleNamespace(completed=[done("BUS106", 3.7, 1)])
    svc = PolicyService(REPO, SimpleNamespace(get_student_record=lambda sid: record))
    out = svc.check_waiver_eligibility(SimpleNamespace(user=SimpleNamespace(id="S1")), "bus202", "bus106")
    assert out["verdict"] == "likely_ineligible" and "advisor" in out["summary"]
    assert svc.check_waiver_eligibility(SimpleNamespace(user=SimpleNamespace(id="S1")), "nonsense", "BUS106")["error"] == "INVALID_COURSE"


def test_retrieval_ranks_by_keywords_without_voyage():
    chunks = [{"text": "Online proctoring needs a webcam and a desk scan.", "title": "P", "section": "Online"},
              {"text": "Grades are percentages from 0 to 100.", "title": "G", "section": "Scale"}]
    assert rank("what do I need for online proctoring webcam", chunks)[0]["section"] == "Online"
    assert rank("something unrelated xyz", chunks) == []
    assert keyword_score("BUS202 waiver", "waiver for BUS202") > keyword_score("BUS202 waiver", "waiver for others")


def test_ingest_chunking_splits_on_headings():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ingest", Path(__file__).resolve().parents[1] / "scripts" / "ingest_policy.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    title, chunks = mod.chunk_markdown("# T\n\nintro\n\n## A\nalpha\n\n## B\nbeta\n")
    assert title == "T" and [c[0] for c in chunks] == ["Overview", "A", "B"]
