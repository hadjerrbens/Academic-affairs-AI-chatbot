from datetime import date

import pytest

from app.data.records_repo import load_grade_scale
from app.domain import records_engine as eng

SCALE = load_grade_scale()
TODAY = date(2026, 11, 21)


@pytest.mark.parametrize("pct,letter", [
    (89.9, "B+"), (90.0, "A-"), (92.9, "A-"), (93.0, "A"),
    (59.9, "F"), (60.0, "D"), (100, "A"), (0, "F"),
    (89.95, "B+"),  # falls in the gap of the table: lower band
])
def test_band_boundaries(pct, letter):
    assert eng.band_for_percentage(pct, SCALE) == letter


@pytest.mark.parametrize("bad", [-0.1, 100.1, float("nan"), "90", None, True])
def test_band_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        eng.band_for_percentage(bad, SCALE)


def test_explain_band_matches_the_table():
    band = eng.explain_band("A-", SCALE)
    assert band["range"] == "90.0\u201392.9"
    assert "90.0\u201392.9" in band["summary"]
    assert band["points"] == 3.7 and band["passing"] is True


def test_explain_band_failing_and_unknown():
    assert eng.explain_band("F", SCALE)["passing"] is False
    with pytest.raises(ValueError):
        eng.explain_band("Z", SCALE)


def test_every_row_of_the_table_is_explained_consistently():
    for row in SCALE:
        band = eng.explain_band(row["letter"], SCALE)
        assert band["range"] == f'{row["min_pct"]:.1f}\u2013{row["max_pct"]:.1f}'


def test_scale_has_11_bands_and_passes_at_1_0():
    assert len(SCALE) == 11
    assert eng.explain_band("D", SCALE)["passing"] is True  # D = 1.0 is the lowest pass


@pytest.mark.parametrize("raw", ["a-", "A -", "A-", " a - ", "A\u2212", "a\u2013"])
def test_normalise_letter_same_key(raw):
    assert eng.normalise_letter(raw) == "A-"


def test_eligibility_blocks_listed_standing_only():
    blocked = eng.check_transcript_eligibility("Academic probation", ["Academic probation"], False, [], TODAY)
    assert blocked["eligible"] is False and blocked["blocking_reasons"]
    ok = eng.check_transcript_eligibility("Good standing", ["Academic probation"], False, [], TODAY)
    assert ok["eligible"] is True
    # nothing is hard-coded: with an empty blocks list, probation is fine
    assert eng.check_transcript_eligibility("Academic probation", [], False, [], TODAY)["eligible"] is True


def test_eligibility_is_case_insensitive_on_standing():
    res = eng.check_transcript_eligibility("academic PROBATION", ["Academic probation"], False, [], TODAY)
    assert res["eligible"] is False


def test_eligibility_unpaid_hold():
    res = eng.check_transcript_eligibility("Good standing", [], True, [], TODAY)
    assert res["eligible"] is False


def test_duplicate_same_day_only():
    today_req = [{"kind": "official", "delivery": "pickup", "date": TODAY}]
    yesterday_req = [{"kind": "official", "delivery": "pickup", "date": date(2026, 11, 20)}]
    assert eng.check_transcript_eligibility("x", [], False, today_req, TODAY, "official", "pickup")["eligible"] is False
    assert eng.check_transcript_eligibility("x", [], False, yesterday_req, TODAY, "official", "pickup")["eligible"] is True
    # a different delivery method is not a duplicate
    assert eng.check_transcript_eligibility("x", [], False, today_req, TODAY, "official", "post")["eligible"] is True


def test_fee_table_is_the_single_source():
    assert eng.transcript_fee("official", "pickup") == 200
    assert eng.transcript_days("official", "post") == 7
    with pytest.raises(ValueError):
        eng.transcript_fee("official", "email")
    assert {(o["kind"], o["delivery"]) for o in eng.transcript_options()} == set(eng.TRANSCRIPT_TABLE)
