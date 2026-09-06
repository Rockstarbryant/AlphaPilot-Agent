"""
Turns a MarketCandidate's numeric score_breakdown + reason into a short,
plain-language explanation a non-technical user can actually act on. Purely
a narration layer — see app/agent/ai_provider.py's own docstring: nothing
here feeds back into scoring, risk, or status. If OpenRouter is unavailable,
falls back to a deterministic templated sentence so the UI never breaks.
"""
from __future__ import annotations

from app.agent.ai_provider import AIProviderError, get_ai_provider
from app.models.models import MarketCandidate

STATUS_PLAIN = {
    "qualified": "AlphaPilot proposed a trade for this",
    "trade_proposed": "AlphaPilot proposed a trade for this",
    "watching": "AlphaPilot is watching this but hasn't proposed a trade yet",
    "rejected": "AlphaPilot looked at this and decided not to trade it",
    "analyzing": "AlphaPilot is still analyzing this",
}


def _fallback_explanation(candidate: MarketCandidate) -> str:
    status_text = STATUS_PLAIN.get(
        candidate.status.value if hasattr(candidate.status, "value") else str(candidate.status),
        "AlphaPilot evaluated this",
    )
    direction = "up" if candidate.daily_change_pct >= 0 else "down"
    parts = [
        f"{candidate.symbol} ({candidate.market_type}) is {direction} "
        f"{abs(candidate.daily_change_pct):.1f}% in the last 24 hours, trading around ${candidate.price}.",
        f"{status_text} — scored {candidate.opportunity_score:.0f}/100 by the "
        f"{candidate.strategy.value.replace('_', ' ')} strategy.",
    ]
    if candidate.reason:
        parts.append(candidate.reason)
    return " ".join(parts)


async def explain_candidate(candidate: MarketCandidate) -> str:
    if candidate.ai_explanation:
        return candidate.ai_explanation

    fallback = _fallback_explanation(candidate)
    try:
        provider = get_ai_provider()
        result = await provider.analyze(
            "Explain this Binance market screening result to someone with no trading background. "
            "2-3 short sentences, plain everyday words, no jargon (avoid saying things like 'RSI', "
            "'spread bps', 'momentum score' — translate them). Be concrete about what happened and "
            "why AlphaPilot did or didn't propose a trade. Do not invent any numbers not given here.\n\n"
            f"Symbol: {candidate.symbol} ({candidate.market_type} market)\n"
            f"24h change: {candidate.daily_change_pct:.1f}%\n"
            f"Price: {candidate.price}\n"
            f"Strategy: {candidate.strategy.value}\n"
            f"Status: {candidate.status.value if hasattr(candidate.status, 'value') else candidate.status}\n"
            f"Opportunity score: {candidate.opportunity_score:.0f}/100\n"
            f"Score breakdown: {candidate.score_breakdown}\n"
            f"AlphaPilot's own reason: {candidate.reason or 'none recorded'}\n",
            max_tokens=220,
        )
        return result.text.strip() or fallback
    except AIProviderError:
        return fallback
