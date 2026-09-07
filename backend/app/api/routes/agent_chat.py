"""
Standalone AlphaPilot chat surface (the "Copilot" page) — talks directly to
OpenRouter free models, independent of any MCP client. For a user who isn't
running Claude/ChatGPT with Binance Agent OS connected and just wants
AlphaPilot's own market view.

Because it has no Binance Agent OS connection of its own, this surface can
give market analysis, earn/margin scans, and panic explanations for
positions AlphaPilot already knows about — but it cannot read live account
balances or place trades. If the user wants the full propose-here/
execute-through-Binance-Agent-OS loop, they need the dual-MCP setup
documented in app/mcp_server.py's wiring_instructions().

Design: deterministic tool routing (keyword + symbol extraction) gathers
real numbers first; the AI model only phrases the final answer around those
numbers — it never invents a price, RSI value, or APY. Same discipline as
app/agent/ai_provider.py's own docstring. Every turn (both sides) is
persisted to ChatMessage so the page has real history across reloads.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.ai_provider import AIProviderError, get_ai_provider
from app.core.config import get_settings
from app.db.base import get_db
from app.earn.scanner import scan_earn_opportunities
from app.margin.analysis import analyze_margin_symbol
from app.market.coin_analysis import analyze_symbol
from app.models.models import ChatMessage
from app.services.panic_advisor import PositionNotFound, explain_position

router = APIRouter()
settings = get_settings()

_PAIR_RE = re.compile(r"\b([A-Za-z]{2,10})\s*[/\-]?\s*(USDT|USDC|BUSD|BTC|ETH)\b", re.IGNORECASE)

# Common tickers so a bare mention ("what about SOL?") still resolves — the
# pair regex above only catches explicit pairs like "SOL/USDT" or "SOLUSDT".
# Not exhaustive; analyze_symbol still validates against real Binance data,
# so an unrecognized bare ticker just falls through to the generic reply
# instead of guessing.
_KNOWN_BASES = {
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
    "MATIC", "POL", "LTC", "TRX", "SHIB", "TON", "NEAR", "ATOM", "UNI", "ICP",
    "ETC", "FIL", "APT", "ARB", "OP", "SUI", "INJ", "RENDER", "RNDR", "PEPE",
    "WIF", "TIA", "SEI", "STX", "HBAR", "VET", "ALGO", "XLM", "AAVE", "MKR",
    "RUNE", "GRT", "SAND", "MANA", "AXS", "FTM", "EGLD", "BONK", "JUP", "PYTH",
}
_QUOTES = ("USDT", "USDC", "BUSD")
_BARE_TICKER_RE = re.compile(r"\b([A-Za-z]{2,10})\b")


def _extract_symbol(text: str) -> str | None:
    match = _PAIR_RE.search(text)
    if match:
        base, quote = match.groups()
        base, quote = base.upper(), quote.upper()
        if base != quote:
            return f"{base}{quote}"

    for m in _BARE_TICKER_RE.finditer(text):
        token = m.group(1).upper()
        if token in _KNOWN_BASES:
            return f"{token}USDT"
    return None


class ChatRequest(BaseModel):
    message: str
    position_id: str | None = None  # set by the UI when the user is asking about a specific open position


class ChatResponse(BaseModel):
    id: str
    reply: str
    tool_used: str | None
    data: dict | None
    ai_narration_used: bool  # False means OpenRouter is unavailable/misconfigured and this is the deterministic fallback


class ChatHistoryMessage(BaseModel):
    id: str
    role: str
    content: str
    tool_used: str | None
    tool_data: dict | None
    created_at: str


async def _narrate(prompt: str, fallback: str) -> tuple[str, bool]:
    """Ask the configured free model to phrase `prompt` in plain language.
    Falls back to a deterministic templated reply if OpenRouter isn't
    configured or fails — the chat must never go silent just because the
    optional narration layer is down. Returns (text, ai_was_used) so the
    caller/UI can be honest about which one happened."""
    try:
        provider = get_ai_provider()
        result = await provider.analyze(prompt, max_tokens=350)
        text = result.text.strip()
        return (text, True) if text else (fallback, False)
    except AIProviderError:
        return fallback, False


async def _save(db: AsyncSession, user_id: str, role: str, content: str, tool_used=None, tool_data=None) -> ChatMessage:
    msg = ChatMessage(user_id=user_id, role=role, content=content, tool_used=tool_used, tool_data=tool_data)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


@router.get("/status")
async def copilot_status():
    """
    Whether AI narration is ACTUALLY working, not just configured — a set
    but invalid OPENROUTER_API_KEY/OPENROUTER_MODEL previously reported
    "online" here while every real reply silently fell back to templated
    text, with no visible signal why. This does a real round-trip call.
    """
    if not settings.openrouter_api_key or not settings.openrouter_model:
        return {
            "ai_provider": settings.ai_provider,
            "ai_configured": False,
            "ai_working": False,
            "note": "OPENROUTER_API_KEY and/or OPENROUTER_MODEL are not set — Copilot will still answer "
                    "using deterministic analysis, but replies use plain templated text instead of "
                    "AI-phrased language until this is configured.",
        }
    try:
        provider = get_ai_provider()
        result = await provider.analyze("Reply with exactly: OK", max_tokens=5)
        return {
            "ai_provider": settings.ai_provider,
            "ai_configured": True,
            "ai_working": True,
            "model": result.model,
            "note": None,
        }
    except AIProviderError as exc:
        return {
            "ai_provider": settings.ai_provider,
            "ai_configured": True,
            "ai_working": False,
            "note": (
                f"OPENROUTER_API_KEY/OPENROUTER_MODEL are set, but a live test call failed: {exc}. "
                "Common causes: OPENROUTER_MODEL isn't a real model id (must include the provider "
                "prefix, e.g. 'meta-llama/llama-3.1-8b-instruct:free'), the API key is invalid/expired, "
                "or the account has no credit. Replies will use templated text until this is fixed."
            ),
        }


@router.get("/{user_id}/history")
async def get_history(user_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc()).limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return [
        ChatHistoryMessage(
            id=m.id, role=m.role, content=m.content, tool_used=m.tool_used,
            tool_data=m.tool_data, created_at=m.created_at.isoformat(),
        )
        for m in rows
    ]


@router.post("/{user_id}/message", response_model=ChatResponse)
async def send_message(user_id: str, payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    text = payload.message.strip()
    lower = text.lower()
    await _save(db, user_id, "user", text)

    async def respond(reply: str, ai_used: bool, tool_used: str | None = None, data: dict | None = None) -> ChatResponse:
        saved = await _save(db, user_id, "assistant", reply, tool_used=tool_used, tool_data=data)
        return ChatResponse(id=saved.id, reply=reply, tool_used=tool_used, data=data, ai_narration_used=ai_used)

    if payload.position_id or "panic" in lower or "should i close" in lower or "going against" in lower:
        if not payload.position_id:
            return await respond(
                "Which position? Open it from the Positions page and ask from there, or tell me the position id.",
                ai_used=False,
            )
        try:
            data = await explain_position(db, position_id=payload.position_id, question=text)
        except PositionNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        reply, ai_used = await _narrate(
            f"A user is worried about an open trade and asked: \"{text}\". Here is AlphaPilot's "
            f"deterministic analysis, respond in plain, reassuring, non-alarmist language grounded "
            f"strictly in these numbers, and end with the recommendation: {data}",
            fallback=data["headline"] + f" Recommendation: {data['recommendation']}.",
        )
        return await respond(reply, ai_used, tool_used="explain_panic", data=data)

    if any(word in lower for word in ("earn", "apy", "yield", "flexible product")):
        data = await scan_earn_opportunities()
        reply, ai_used = await _narrate(
            f"A user asked about Binance Earn opportunities: \"{text}\". Summarize this scan result "
            f"in 3-4 sentences, in plain language, using only these figures: {data}",
            fallback=(
                "; ".join(f"{o['asset']}: {o['latest_apy_pct']}% APY" for o in data["opportunities"][:5])
                if data["opportunities"] else data["unavailable_reason"]
            ),
        )
        return await respond(reply, ai_used, tool_used="get_earn_opportunities", data=data)

    symbol = _extract_symbol(text)
    if symbol and "margin" in lower:
        data = (await analyze_margin_symbol(symbol)).__dict__
        reply, ai_used = await _narrate(
            f"A user asked about margin trading {symbol}: \"{text}\". Explain this margin analysis "
            f"in plain language, grounded strictly in these numbers: {data}",
            fallback=data["notes"],
        )
        return await respond(reply, ai_used, tool_used="get_margin_analysis", data=data)

    if symbol:
        analysis = await analyze_symbol(symbol)
        data = analysis.__dict__
        reply, ai_used = await _narrate(
            f"A user asked: \"{text}\" about {symbol}. Here is AlphaPilot's multi-factor analysis — "
            f"technical indicators, market structure, volume, order book, derivatives positioning, "
            f"on-chain, sentiment, and cross-market, combined into one composite bias/confidence. "
            f"Explain it in plain, direct language, mention which categories actually had data "
            f"({len(analysis.categories_used)}/8), and give a clear recommendation for spot "
            f"buy-and-hold vs long/short vs waiting, grounded strictly in this data (never invent "
            f"numbers not present here): {data}",
            fallback=(
                f"{symbol}: bias {analysis.bias} ({analysis.confidence}% confidence, based on "
                f"{len(analysis.categories_used)}/8 analysis categories — missing: "
                f"{', '.join(analysis.categories_missing) or 'none'}). "
                f"{analysis.spot_guidance} {analysis.derivatives_guidance}"
            ),
        )
        return await respond(reply, ai_used, tool_used="analyze_symbol", data=data)

    reply, ai_used = await _narrate(
        f"A user of a Binance trading-advisory assistant called AlphaPilot said: \"{text}\". "
        "AlphaPilot cannot see this user's live Binance balance from this chat surface (that "
        "requires connecting Claude/ChatGPT to both AlphaPilot's MCP server and Binance Agent OS "
        "MCP — see the Agent page). Reply helpfully and specifically to what they said; if they're "
        "asking about a coin, ask which symbol; if they want to trade, point them at the dual-MCP setup.",
        fallback=(
            "Ask me about a specific symbol (e.g. \"what do you think about BTC/USDT\"), Binance "
            "Earn APY, or margin trading a symbol. For live balances and executing trades, connect "
            "an AI client (like Claude) to both AlphaPilot's MCP server and Binance Agent OS MCP — "
            "see the Agent page for setup."
        ),
    )
    return await respond(reply, ai_used, tool_used=None, data=None)
