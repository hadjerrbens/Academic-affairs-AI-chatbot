"""Real SWI-Prolog parity tests. They skip when swipl is not installed.

For full integration, M3 must consult generated CSV facts through its shared bridge.
These small tests validate the two M2-owned rule files without M3's generator.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SWIPL = shutil.which("swipl")
RULES = Path(__file__).resolve().parents[4] / "kb" / "rules"
pytestmark = pytest.mark.skipif(SWIPL is None, reason="SWI-Prolog is not installed")


def run_query(tmp_path, goal: str, facts: str = "") -> None:
    facts_file = tmp_path / "test_facts.pl"
    facts_file.write_text(facts, encoding="utf-8")
    commands = [SWIPL, "-q", "-s", str(RULES / "requirements.pl"),
                "-s", str(RULES / "standing.pl"), "-s", str(facts_file),
                "-g", f"(({goal}) -> halt(0) ; halt(1))"]
    result = subprocess.run(commands, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr or result.stdout


def test_standing_exact_thresholds(tmp_path):
    run_query(tmp_path,
        "standing_classify(3.0, good_standing), "
        "standing_classify(2.5, warning), "
        "standing_classify(2.0, probation), "
        "standing_classify(1.99, dismissal), "
        "\\+ standing_classify(2.5, probation)",
        "standing_policy(sp_default, 'Demo Policy', 3.0, 2.5, 2.0, '', '', 14, '').\n")


def test_required_elective_credit_groups(tmp_path):
    run_query(tmp_path,
        "req_group_status(required, 0, [[a,1.0]], [[a,3,2.0]], [], true, [a]), "
        "req_group_status(elective, 2, [[a,1.0],[b,1.0]], [[a,3,2.0]], [], false, [a]), "
        "req_group_status(credits, 4, [[a,1.0],[b,1.0]], [[a,3,2.0],[b,2,2.0]], [], true, [a,b])")


def test_no_course_can_be_allocated_to_two_groups(tmp_path):
    facts = "program(bs_cs, 'Computer Science', bs, 3, 2.0, cs).\n"
    run_query(tmp_path,
        "req_audit(bs_cs, [[a,3,3.0]], "
        "[[r1,required,0,[[a,1.0]]],[e1,elective,1,[[a,1.0]]]], "
        "3.0, 3, [false, [[r1,true,[a],[]],[e1,false,[],[a]]]])",
        facts)


def test_unknown_program_has_no_solution(tmp_path):
    run_query(tmp_path,
        "\\+ req_audit(unknown, [], [], 3.0, 6, _)",
        "program(bs_cs, 'Computer Science', bs, 6, 2.0, cs).\n")
