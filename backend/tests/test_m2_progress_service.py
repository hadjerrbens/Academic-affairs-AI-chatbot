"""Service tests with a fake M3 bridge. Actual Prolog parity is in tests/kb/."""
from __future__ import annotations

import asyncio
import sys
import types
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.data.progress_repo import ProgressRepo
from app.services.progress_service import ProgressService

SEED = Path(__file__).resolve().parents[2] / "data" / "seed"
POINTS = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7,
          "C+": 2.3, "C": 2.0, "C-": 1.7, "D+": 1.3, "D": 1.0, "F": 0.0}


@dataclass
class CompletedCourse:
    student_id: str
    course_code: str
    credits: int
    grade: str
    term: str
    grade_points: float | None = None
    status: str = "COMPLETED"
    is_repeat: bool = False


@dataclass
class StudentRecord:
    student_id: str
    program_code: str | None
    year: int
    completed: list[CompletedCourse] = field(default_factory=list)
    current_section_codes: list[str] = field(default_factory=list)


def create_service(monkeypatch):
    # M1 will supply this exact interface when merged. No M1 source is shipped by M2.
    fake_module = types.ModuleType("app.domain.shared_models")
    fake_module.StudentRecord = StudentRecord
    fake_module.CompletedCourse = CompletedCourse
    monkeypatch.setitem(sys.modules, "app.domain.shared_models", fake_module)
    repo = ProgressRepo(seed_dir=SEED)

    def fake_ask(goal, **params):
        if goal.startswith("standing_classify"):
            gpa = params["gpa"]
            policy = repo.get_standing_policy()
            answer = (
                "good_standing" if gpa >= policy["good_standing_min_gpa"] else
                "warning" if gpa >= policy["warning_min_gpa"] else
                "probation" if gpa >= policy["probation_min_gpa"] else
                "dismissal"
            )
            return [{"Status": answer}]
        assert goal.startswith("req_audit")
        seen = set()
        reports = []
        selected = {code: (credits, points) for code, credits, points in params["completed"]}
        for gid, kind, n, pool in params["groups"]:
            candidates = [(code, selected[code][0]) for code, minimum in pool
                          if code in selected and code not in seen and selected[code][1] >= minimum]
            if kind == "required":
                used = [code for code, _ in candidates]
                satisfied = len(used) == len(pool)
            elif kind == "elective":
                used = [code for code, _ in candidates[:n]]
                satisfied = len(used) >= n
            else:
                used = []
                credits = 0
                for code, count in candidates:
                    if credits >= n:
                        break
                    used.append(code)
                    credits += count
                satisfied = credits >= n
            seen.update(used)
            reports.append([gid.lower(), "true" if satisfied else "false", [c.lower() for c in used],
                            [c.lower() for c, _ in pool if c not in used]])
        program = repo.get_program(params["program"])
        all_ok = all(row[1] == "true" for row in reports)
        eligible = all_ok and params["gpa"] >= float(program["min_gpa"]) and params["earned"] >= int(program["total_credits_required"])
        return [{"Result": ["true" if eligible else "false", reports]}]

    return ProgressService(repo, kb_query=fake_ask, grade_points_provider=lambda: POINTS)


def context(sid):
    return SimpleNamespace(user=SimpleNamespace(student_id=sid), today=date(2026, 11, 23))


def test_loader_counts_and_in_progress(monkeypatch):
    service = create_service(monkeypatch)
    assert len(service.repo.get_requirement_groups("BS_CS")) == 4
    assert len(service.repo.get_requirement_groups("BS_MATH")) == 4
    record = service.repo.get_student_record("S0000002")
    assert record is not None and record.program_code == "BS_CS"
    assert any(c.status == "IN_PROGRESS" for c in record.completed)
    assert service.repo.get_student_record("UNKNOWN") is None


def test_standing_seed_scenarios(monkeypatch):
    service = create_service(monkeypatch)
    assert service.get_standing_status("S0000003")["status"] == "PROBATION"
    assert service.get_standing_status("S0000004")["status"] == "WARNING"
    assert service.get_standing_status("S0000010")["status"] == "DISMISSAL"
    assert service.get_standing_status("S0000001")["status"] == "GOOD_STANDING"
    assert service.get_standing_status("S0000003")["blocks_registration"] is True
    assert service.get_standing_status("S0000003")["blocks_transcripts"] is False
    assert service.get_standing_status("S0000010")["blocks_transcripts"] is True


def test_standing_exact_thresholds_from_approved_policy(monkeypatch):
    service = create_service(monkeypatch)
    policy = service.repo.get_standing_policy()
    def check(gpa):
        return service.kb_query("standing_classify({gpa}, Status)", gpa=gpa)[0]["Status"]
    assert check(policy["good_standing_min_gpa"]) == "good_standing"
    assert check(policy["warning_min_gpa"]) == "warning"
    assert check(policy["probation_min_gpa"]) == "probation"
    assert check(policy["probation_min_gpa"] - 0.001) == "dismissal"


def test_progress_demo_eligible_and_near_graduation(monkeypatch):
    service = create_service(monkeypatch)
    eligible = asyncio.run(service.audit_degree_progress(context("S0000001")))
    assert "error" not in eligible
    assert eligible["eligible_to_graduate"] is True
    assert eligible["percent_complete"] == 1.0
    assert all(g["satisfied"] for g in eligible["groups"])
    assert len({course for g in eligible["groups"] for course in g["used_courses"]}) == sum(len(g["used_courses"]) for g in eligible["groups"])
    near = asyncio.run(service.audit_degree_progress(context("S0000002")))
    assert near["eligible_to_graduate"] is False
    assert any(not g["satisfied"] for g in near["groups"])
    assert any("CS404" in a for a in near["next_actions"])
    assert "Cumulative GPA" in eligible["summary"]


def test_public_tool_private_tools_and_appeal_deadline(monkeypatch):
    service = create_service(monkeypatch)
    public = asyncio.run(service.get_major_requirements(context("UNKNOWN"), "BS_CS"))
    assert len(public["groups"]) == 4 and "summary" in public
    assert asyncio.run(service.get_major_requirements(context("UNKNOWN"), "UNKNOWN"))["error"] == "PROGRAM_NOT_FOUND"
    anonymous = SimpleNamespace(user=None, today=date(2026, 11, 23))
    assert (asyncio.run(service.audit_degree_progress(anonymous)))["error"] == "LOGIN_REQUIRED"
    standing = asyncio.run(service.get_academic_standing(context("S0000003")))
    assert standing["status"] == "PROBATION"
    assert standing["appeal_deadline"] == "2026-12-07"
    assert "2026-12-07" in standing["summary"]


def test_missing_student_returns_clear_error(monkeypatch):
    service = create_service(monkeypatch)
    result = asyncio.run(service.audit_degree_progress(context("NOT_A_STUDENT")))
    assert result["error"] == "STUDENT_NOT_FOUND"


def test_m4_tool_signatures_contain_no_student_id(monkeypatch):
    service = create_service(monkeypatch)
    class FakeRegistry:
        def __init__(self): self.tools = []
        def tool(self, **kwargs):
            self.tools.append(kwargs)
            return lambda callback: callback
    registry = FakeRegistry()
    service.register(registry)
    assert len(registry.tools) == 3
    assert all("student_id" not in str(t["parameters"]) and "user_id" not in str(t["parameters"])
               for t in registry.tools)
    assert [t["name"] for t in registry.tools] == [
        "get_major_requirements", "audit_degree_progress", "get_academic_standing"
    ]
