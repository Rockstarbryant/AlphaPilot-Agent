"""
Composite scoring — combines every category (technical, structure, volume,
order book, derivatives, on-chain, sentiment, cross-market) into one
bias/confidence, the way the user's requested matrix's "machine learning"
row implies a model would.

Being straight about what this is: it's a weighted-vote composite over
hand-specified category weights, not a trained statistical/ML model — there
is no historical labeled dataset or training pipeline in this project to
fit one against. Every category here reports a score in [-1, +1] PLUS
whether it actually had data; unavailable categories are excluded and the
remaining weights are renormalized (not treated as neutral/0), and the
`coverage` report is returned alongside the result so a caller always knows
exactly how much of the matrix a given analysis actually drew on — this is
the direct fix for "our analysis is too shallow to depend on": you can now
see precisely which categories were used and which weren't, every time.

The category weights below are a reasonable starting allocation, not a
calibrated finding — see CATEGORY_WEIGHTS for exactly what they are, and
treat them as a place to tune, not a scientific result.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CATEGORY_WEIGHTS: dict[str, float] = {
    "technical": 0.30,
    "structure": 0.20,
    "volume": 0.10,
    "orderbook": 0.05,
    "derivatives": 0.10,
    "onchain": 0.05,
    "sentiment": 0.10,
    "cross_market": 0.10,
}

MIN_CATEGORIES_FOR_DIRECTIONAL_CALL = 4
MIN_COVERAGE_WEIGHT_FOR_DIRECTIONAL_CALL = 0.5  # at least half the total weight must be represented


@dataclass
class CategoryScore:
    name: str
    available: bool
    score: float  # -1 (bearish) .. +1 (bullish), meaningless if available=False
    summary: str


@dataclass
class CompositeResult:
    bias: str  # LONG | SHORT | WAIT
    confidence: float  # 0-100
    composite_score: float  # -1..1, the raw weighted vote before bias/confidence mapping
    categories_used: list[str]
    categories_missing: list[str]
    coverage_weight_pct: float  # what fraction of total possible weight was actually represented
    model_type: str
    rationale: list[str]


def build_composite(categories: list[CategoryScore]) -> CompositeResult:
    available = [c for c in categories if c.available]
    missing = [c.name for c in categories if not c.available]

    total_possible_weight = sum(CATEGORY_WEIGHTS.get(c.name, 0.0) for c in categories)
    available_weight = sum(CATEGORY_WEIGHTS.get(c.name, 0.0) for c in available)
    coverage_weight_pct = round((available_weight / total_possible_weight * 100), 1) if total_possible_weight else 0.0

    rationale = [f"{c.name}: {c.summary}" for c in available]
    if missing:
        rationale.append(f"Not included (no data): {', '.join(missing)}.")

    if len(available) < MIN_CATEGORIES_FOR_DIRECTIONAL_CALL or available_weight < total_possible_weight * MIN_COVERAGE_WEIGHT_FOR_DIRECTIONAL_CALL:
        rationale.append(
            f"Only {len(available)}/{len(categories)} categories ({coverage_weight_pct}% of weighted "
            f"coverage) had usable data — below the bar for a directional call, so this stays WAIT "
            "regardless of what the available categories lean toward."
        )
        return CompositeResult(
            bias="WAIT", confidence=0.0, composite_score=0.0,
            categories_used=[c.name for c in available], categories_missing=missing,
            coverage_weight_pct=coverage_weight_pct,
            model_type="weighted_heuristic_composite (not a trained ML model)",
            rationale=rationale,
        )

    composite_score = sum(CATEGORY_WEIGHTS.get(c.name, 0.0) * c.score for c in available) / available_weight
    confidence = round(min(100.0, abs(composite_score) * 100), 1)

    if composite_score > 0.15:
        bias = "LONG"
    elif composite_score < -0.15:
        bias = "SHORT"
    else:
        bias = "WAIT"
        rationale.append(f"Weighted composite score {composite_score:+.2f} is too close to neutral for a directional call.")

    return CompositeResult(
        bias=bias, confidence=confidence, composite_score=round(composite_score, 3),
        categories_used=[c.name for c in available], categories_missing=missing,
        coverage_weight_pct=coverage_weight_pct,
        model_type="weighted_heuristic_composite (not a trained ML model)",
        rationale=rationale,
    )
