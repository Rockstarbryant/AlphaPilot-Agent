"""
Turns a MarketCandidate's numeric score_breakdown + reason into a short,
plain-language explanation a non-technical user can actually act on — not a
restatement of numbers already shown elsewhere in the UI (price, % change),
but the *mechanism*: what AlphaPilot actually checked, how those checks
combine into the score, why that produced this status, and — for a
watching/rejected coin — what would need to change for it to become an
actual proposal. Purely a narration layer — see app/agent/ai_provider.py's
own docstring: nothing here feeds back into scoring, risk, or status.

If OpenRouter is unavailable, falls back to a deterministic templated
sentence — less specific than a real AI explanation but still mechanism-
focused, not just a restatement — so the UI never breaks, and callers get
an `ai_narrated` flag so they can be honest about which one the user got.
"""
from __future__ import annotations

from app.agent.ai_provider import AIProviderError, get_ai_provider
from app.models.models import MarketCandidate

STRATEGY_MECHANISM = {
    "gainer_hunter": (
        "The Gainer Hunter strategy looks for coins that already jumped in the last 24 hours and checks "
        "whether that move has real strength behind it — enough trading volume that a real trade could "
        "get in and out without moving the price much, and a tight enough gap between buy and sell prices."
    ),
    "recovery_hunter": (
        "The Recovery Hunter strategy looks for coins that dropped in the last 24 hours and tries to tell "
        "the difference between 'still falling' and 'starting to stabilize' — using recent price behavior, "
        "trading volume, and how wide the buy/sell price gap is."
    ),
    "hot_market_margin": (
        "The Hot Market strategy looks for unusually strong price and volume moves, then separately checks "
        "whether it's actually safe to trade this on margin (borrowed money) — liquidity, price-gap "
        "tightness, and overall market mood all have to pass before margin is allowed."
    ),
    "user_requested": "This was analyzed on request using RSI, MACD, and momentum against recent price history.",
}

STATUS_MECHANISM = {
    "qualified": "It passed every one of those checks, so AlphaPilot turned it into an actual trade proposal.",
    "trade_proposed": "It passed every one of those checks, so AlphaPilot turned it into an actual trade proposal.",
    "watching": (
        "It passed some checks but not all of them — usually the score from those checks landed below the "
        "bar AlphaPilot requires before it will suggest real money. It stays on the list so the next hourly "
        "scan can catch it if conditions improve."
    ),
    "rejected": (
        "It failed a check AlphaPilot treats as a hard no for right now — most often that the move looks "
        "like continued weakness rather than stabilization, or that trading it wouldn't be safe/liquid "
        "enough. It will only reappear as a proposal if a later scan reads it differently."
    ),
    "analyzing": "AlphaPilot hasn't finished evaluating it yet.",
}


def _fallback_explanation(candidate: MarketCandidate) -> str:
    status = candidate.status.value if hasattr(candidate.status, "value") else str(candidate.status)
    strategy = candidate.strategy.value if hasattr(candidate.strategy, "value") else str(candidate.strategy)
    mechanism = STRATEGY_MECHANISM.get(strategy, "AlphaPilot scored this using its strategy's own checks.")
    outcome = STATUS_MECHANISM.get(status, "AlphaPilot evaluated it against that strategy's checks.")
    return f"{mechanism} {outcome}"


async def explain_candidate(candidate: MarketCandidate) -> tuple[str, bool]:
    """Returns (explanation, ai_narrated) — ai_narrated=False means this is
    the deterministic fallback, not a real AI-generated explanation."""
    if candidate.ai_explanation:
        return candidate.ai_explanation, True

    status = candidate.status.value if hasattr(candidate.status, "value") else str(candidate.status)
    strategy = candidate.strategy.value if hasattr(candidate.strategy, "value") else str(candidate.strategy)
    fallback = _fallback_explanation(candidate)
    try:
        provider = get_ai_provider()
        result = await provider.analyze(
            "Explain HOW and WHY a trading bot reached its conclusion about this coin, to someone with "
            "zero trading background. Do NOT just restate the price, percent change, or score — those are "
            "already shown elsewhere on screen. Instead explain: (1) what the strategy actually checks and "
            "why, in everyday terms (no jargon like 'RSI', 'spread bps', 'momentum score' — translate them "
            "to plain concepts like 'how easily you could buy and sell without moving the price'), (2) which "
            "of those checks this specific coin passed or failed and why that mattered, (3) if it's not an "
            "active proposal, what would specifically need to change for AlphaPilot to reconsider it. "
            "3-4 short sentences, plain everyday words. Never invent a number not given here.\n\n"
            f"Strategy: {strategy} — {STRATEGY_MECHANISM.get(strategy, '')}\n"
            f"Symbol: {candidate.symbol} ({candidate.market_type} market)\n"
            f"Status: {status}\n"
            f"Opportunity score: {candidate.opportunity_score:.0f}/100\n"
            f"Score breakdown (each component's contribution): {candidate.score_breakdown}\n"
            f"AlphaPilot's own recorded reason: {candidate.reason or 'none recorded'}\n",
            max_tokens=260,
        )
        text = result.text.strip()
        return (text, True) if text else (fallback, False)
    except AIProviderError:
        return fallback, False
