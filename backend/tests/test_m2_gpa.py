"""Standalone tests for M2's only GPA implementation."""
import pytest

from app.domain.requirement_engine import best_attempts, calculate_gpa

POINTS = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "C+": 2.3,
          "C": 2.0, "C-": 1.7, "D+": 1.3, "D": 1.0, "F": 0.0}


def course(code, grade, credits=3, status="completed"):
    return {"course_code": code, "credits": credits, "grade": grade, "status": status}


def test_f_is_attempted_but_not_earned():
    gpa, earned, attempted = calculate_gpa([course("CS101", "F")], POINTS)
    assert (gpa, earned, attempted) == (0, 0, 3)


def test_i_and_w_are_ignored():
    gpa, earned, attempted = calculate_gpa(
        [course("CS101", "I"), course("CS102", "W"), course("CS103", "A")], POINTS)
    assert (gpa, earned, attempted) == (4.0, 3, 3)


def test_in_progress_not_counted_even_with_grade():
    assert calculate_gpa([course("CS100", "A", status="in_progress")], POINTS) == (0, 0, 0)


def test_best_repeat_counts_only_once():
    grades = [course("CS201", "C", 2), course("CS201", "A-", 2)]
    assert calculate_gpa(grades, POINTS) == (3.7, 2, 2)
    assert len(best_attempts(grades, POINTS)) == 1


def test_worse_repeat_does_not_reduce_gpa():
    grades = [course("CS201", "B+"), course("CS201", "C+")]
    gpa, earned, attempted = calculate_gpa(grades, POINTS)
    assert gpa == pytest.approx(3.3) and (earned, attempted) == (3, 3)


def test_zero_credits_has_zero_gpa():
    assert calculate_gpa([], POINTS) == (0.0, 0, 0)
    assert calculate_gpa([course("CS101", "A", credits=0)], POINTS) == (0.0, 0, 0)


def test_weighted_mean_and_passing_threshold_from_m4_map():
    gpa, earned, attempted = calculate_gpa(
        [course("CS101", "A", credits=2), course("CS102", "D", credits=3)], POINTS)
    assert gpa == pytest.approx((2 * 4 + 3 * 1) / 5)
    assert (earned, attempted) == (5, 5)


def test_bad_repeat_policy_and_unrecognised_grade_fail_clearly():
    with pytest.raises(ValueError, match="BEST"):
        calculate_gpa([course("CS101", "A")], POINTS, "LATEST")
    with pytest.raises(ValueError, match="Unknown grade"):
        calculate_gpa([course("CS101", "Z")], POINTS)
