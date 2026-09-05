"""
Optional qualitative layer on top of already-scored, already-risk-validated
TradePlans. Never called from the risk engine or strategy scoring path —
from an explicit dashboard/API request when qualitative comparison is needed. If the AI provider is unavailable, this degrades to
"AI unavailable" rather than guessing or blocking anything else the app
does (see app/agent/ai_provider.py and docs/RISK_ENGINE.md #62).
"""
from __future__ import annotations

from app.agent.ai_provider import AIProviderError, get_ai_provider
from app.models.models import TradePlan


async def compare_candidates(plans: list[TradePlan]) -> str:
    if not plans:
        return "No candidates to compare."
    if len(plans) == 1:
        p = plans[0]
        return f"Only one candidate ({p.symbol}) — nothing to compare it against."

    try:
        provider = get_ai_provider()
    except AIProviderError as e:
        return f"AI unavailable: {e}"

    summary_lines = []
    for p in plans:
        summary_lines.append(
            f"- {p.symbol} ({p.strategy}): opportunity score {p.opportunity_score:.1f}/100, "
            f"risk score {p.risk_score:.1f}/100, proposed size ${p.position_size_usdt:.2f}, "
            f"reason: {p.reason}"
        )
    prompt = (
        "You are comparing already-risk-validated trade proposals for a market operations "
        "dashboard. These numbers are final and were computed deterministically — do not "
        "recompute or second-guess the scores. Just explain in 2-3 sentences, in plain "
        "language, which candidate looks most compelling to a human reviewer and why, based "
        "only on the given data. Do not recommend a position size or override any risk limit.\n\n"
        + "\n".join(summary_lines)
    )

    try:
        result = await provider.analyze(prompt, max_tokens=250)
        return result.text
    except AIProviderError as e:
        return f"AI unavailable: {e}"
