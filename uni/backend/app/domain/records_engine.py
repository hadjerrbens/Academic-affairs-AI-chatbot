"""Pure functions for grading and transcripts: no database, no LLM, no clock.
Everything is passed in, so every function can be tested with plain values.

A GPA function does NOT belong here: M2's calculate_gpa is the only one."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable, Sequence

# ---- Transcript fees and delivery times: ONE source. Docs never quote these numbers.
# PLACEHOLDER values (DZD, days): set the real ones here.
TRANSCRIPT_TABLE: dict[tuple[str, str], tuple[int, int]] = {
    # (kind, delivery): (fee, estimated_days)
    ("official", "pickup"): (200, 3),
    ("official", "post"): (500, 7),
    ("unofficial", "email"): (0, 1),
    ("unofficial", "pickup"): (0, 1),
}
TRANSCRIPT_KINDS = ("official", "unofficial")
TRANSCRIPT_DELIVERIES = ("pickup", "email", "post")


# ---------------------------------------------------------------- grading
def normalise_letter(text: str) -> str:
    """'a-', 'A -', 'A−' (unicode minus) all become 'A-'."""
    cleaned = re.sub(r"\s+", "", str(text))
    cleaned = cleaned.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    return cleaned.upper()


def _sorted_scale(scale: Sequence[dict]) -> list[dict]:
    return sorted(scale, key=lambda band: -band["min_pct"])


def band_for_percentage(pct: float, scale: Sequence[dict]) -> str:
    """Highest band whose minimum is <= pct. A boundary value belongs to the HIGHER band
    (exactly 90.0 -> 'A-'). Values in the small gaps of the table (89.95) fall to the lower band."""
    if isinstance(pct, bool) or not isinstance(pct, (int, float)):
        raise ValueError("percentage must be a number")
    if pct != pct or pct < 0 or pct > 100:  # pct != pct catches NaN
        raise ValueError("percentage must be between 0 and 100")
    for band in _sorted_scale(scale):
        if pct >= band["min_pct"]:
            return band["letter"]
    raise ValueError("scale has no band for this percentage")


def explain_band(letter: str, scale: Sequence[dict], passing_points: float = 1.0) -> dict[str, Any]:
    key = normalise_letter(letter)
    band = next((b for b in scale if normalise_letter(b["letter"]) == key), None)
    if band is None:
        raise ValueError(f"unknown grade '{letter}'")
    passed = band["points"] >= passing_points
    range_text = f'{band["min_pct"]:.1f}\u2013{band["max_pct"]:.1f}'
    summary = (
        f'{band["letter"]} is {range_text} percent and is worth {band["points"]:.1f} grade points. '
        f'{"This is a passing grade." if passed else "This is a failing grade."}'
    )
    return {
        "letter": band["letter"],
        "range": range_text,
        "points": band["points"],
        "passing": passed,
        "summary": summary,
    }


def describe_scale(scale: Sequence[dict], passing_points: float = 1.0) -> dict[str, Any]:
    bands = [
        {
            "letter": b["letter"],
            "range": f'{b["min_pct"]:.1f}\u2013{b["max_pct"]:.1f}',
            "points": b["points"],
        }
        for b in _sorted_scale(scale)
    ]
    listing = "; ".join(f'{b["letter"]} {b["range"]} ({b["points"]:.1f})' for b in bands)
    summary = (
        f"Grading scale (percentage, grade points): {listing}. "
        f"A grade is passing from {passing_points:.1f} grade points. "
        "A boundary value belongs to the higher band."
    )
    return {"bands": bands, "summary": summary}


# ------------------------------------------------------------- transcripts
def transcript_fee(kind: str, delivery: str) -> int:
    try:
        return TRANSCRIPT_TABLE[(kind, delivery)][0]
    except KeyError:
        raise ValueError(f"'{kind}' transcripts cannot be delivered by '{delivery}'") from None


def transcript_days(kind: str, delivery: str) -> int:
    try:
        return TRANSCRIPT_TABLE[(kind, delivery)][1]
    except KeyError:
        raise ValueError(f"'{kind}' transcripts cannot be delivered by '{delivery}'") from None


def transcript_options() -> list[dict[str, Any]]:
    return [
        {"kind": k, "delivery": d, "fee": fee, "estimated_days": days}
        for (k, d), (fee, days) in TRANSCRIPT_TABLE.items()
    ]


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def check_transcript_eligibility(
    standing: str | None,
    blocks_transcripts: Iterable[str],
    has_unpaid_hold: bool,
    requests: Sequence[dict],
    today: date,
    kind: str | None = None,
    delivery: str | None = None,
) -> dict[str, Any]:
    """blocks_transcripts comes from M2's standing policy. Never hard-code a standing here."""
    reasons: list[str] = []
    blocked = {s.casefold() for s in blocks_transcripts}
    if standing and standing.casefold() in blocked:
        reasons.append(f"Your academic standing ({standing}) does not allow transcript requests.")
    if has_unpaid_hold:
        reasons.append("There is an unpaid hold on your account.")
    if kind and delivery:
        duplicate = any(
            r.get("kind") == kind and r.get("delivery") == delivery and _as_date(r.get("date")) == today
            for r in requests
        )
        if duplicate:
            reasons.append("You already made this exact request today.")
    return {"eligible": not reasons, "blocking_reasons": reasons}
