"""
Standalone AlphaPilot chat surface — the "separate Agent UI" that talks
directly to OpenRouter free models, independent of any MCP client. This is
for a user who isn't running Claude/ChatGPT with Binance Agent OS connected
and just wants AlphaPilot's own market view.

Because it has no Binance Agent OS connection of its own, this surface can
give market analysis, earn/margin scans, and panic explanations for
positions AlphaPilot already knows about — but it cannot read live account
balances or place trades. If the user wants the full propose-here/
execute-through-Binance-Agent-OS loop, they need the dual-MCP setup
documented in app/mcp_server.py's wiring_instructions().

Design: deterministic tool routing (keyword + symbol extraction) gathers
real numbers first; the AI model only phrases the final answer around those
numbers — it never invents a price, RSI value, or APY. Same discipline as
app/agent/ai_provider.py's own docstring.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.ai_provider import AIProviderError, get_ai_provider
from app.db.base import get_db
from app.earn.scanner import scan_earn_opportunities
from app.margin.analysis import analyze_margin_symbol
from app.market.coin_analysis import analyze_symbol
from app.services.panic_advisor import PositionNotFound, explain_position

router = APIRouter()

_SYMBOL_RE = re.compile(r"\b([A-Za-z]{2,10})\s*[/\-]?\s*(USDT|USDC|BUSD|BTC|ETH)\b", re.IGNORECASE)
_KNOWN_QUOTES = ("USDT", "USDC", "BUSD", "BTC", "ETH")


def _extract_symbol(text: str) -> str | None:
    match = _SYMBOL_RE.search(text)
    if not match:
        return None
    base, quote = match.groups()
    base, quote = base.upper(), quote.upper()
    if base in _KNOWN_QUOTES and base == quote:
        return None
    return f"{base}{quote}"


class ChatRequest(BaseModel):
    message: str
    position_id: str | None = None  # set by the UI when the user is asking about a specific open position


class ChatResponse(BaseModel):
    reply: str
    tool_used: str | None
    data: dict | None


async def _narrate(prompt: str, fallback: str) -> str:
    """Ask the configured free model to phrase `prompt` in plain language.
    Falls back to a deterministic templated reply if OpenRouter isn't
    configured or fails — the chat must never go silent just because the
    optional narration layer is down."""
    try:
        provider = get_ai_provider()
        result = await provider.analyze(prompt, max_tokens=350)
        return result.text.strip()
    except AIProviderError:
        return fallback


@router.post("/{user_id}/message", response_model=ChatResponse)
async def send_message(user_id: str, payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    text = payload.message.strip()
    lower = text.lower()

    if payload.position_id or "panic" in lower or "should i close" in lower or "going against" in lower:
        if not payload.position_id:
            return ChatResponse(
                reply="Which position? Open the position from the Positions page and ask from there, "
                "or tell me the position id.",
                tool_used=None,
                data=None,
            )
        try:
            data = await explain_position(db, position_id=payload.position_id, question=text)
        except PositionNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        reply = await _narrate(
            f"A user is worried about an open trade and asked: \"{text}\". Here is AlphaPilot's "
            f"deterministic analysis, respond in plain, reassuring, non-alarmist language grounded "
            f"strictly in these numbers, and end with the recommendation: {data}",
            fallback=data["headline"] + f" Recommendation: {data['recommendation']}.",
        )
        return ChatResponse(reply=reply, tool_used="explain_panic", data=data)

    if any(word in lower for word in ("earn", "apy", "yield", "flexible product")):
        data = await scan_earn_opportunities()
        reply = await _narrate(
            f"A user asked about Binance Earn opportunities: \"{text}\". Summarize this scan result "
            f"in 3-4 sentences, in plain language, using only these figures: {data}",
            fallback=(
                "; ".join(
                    f"{o['asset']}: {o['latest_apy_pct']}% APY" for o in data["opportunities"][:5]
                )
                if data["opportunities"]
                else data["unavailable_reason"]
            ),
        )
        return ChatResponse(reply=reply, tool_used="get_earn_opportunities", data=data)

    symbol = _extract_symbol(text)
    if symbol and "margin" in lower:
        data = (await analyze_margin_symbol(symbol)).__dict__
        reply = await _narrate(
            f"A user asked about margin trading {symbol}: \"{text}\". Explain this margin analysis "
            f"in plain language, grounded strictly in these numbers: {data}",
            fallback=data["notes"],
        )
        return ChatResponse(reply=reply, tool_used="get_margin_analysis", data=data)

    if symbol:
        analysis = await analyze_symbol(symbol)
        data = analysis.__dict__
        reply = await _narrate(
            f"A user asked: \"{text}\" about {symbol}. Here is AlphaPilot's deterministic technical "
            f"analysis — RSI, MACD, momentum, market regime, and a bias/confidence score. Explain it "
            f"in plain, direct language and give a clear recommendation for spot buy-and-hold vs "
            f"long/short vs waiting, grounded strictly in this data (never invent numbers not present "
            f"here): {data}",
            fallback=(
                f"{symbol}: bias {analysis.bias} ({analysis.confidence}% confidence). "
                f"{analysis.spot_guidance} {analysis.derivatives_guidance}"
            ),
        )
        return ChatResponse(reply=reply, tool_used="analyze_symbol", data=data)

    reply = await _narrate(
        f"A user of a Binance trading-advisory assistant called AlphaPilot said: \"{text}\". "
        "AlphaPilot cannot see this user's live Binance balance from this chat surface (that "
        "requires connecting Claude/ChatGPT to both AlphaPilot's MCP server and Binance Agent OS "
        "MCP — see the Agent page). Reply helpfully; if they're asking about a coin, ask which "
        "symbol; if they want to trade, point them at the dual-MCP setup.",
        fallback=(
            "Ask me about a specific symbol (e.g. \"what do you think about BTC/USDT\"), Binance "
            "Earn APY, or margin trading a symbol. For live balances and executing trades, connect "
            "an AI client (like Claude) to both AlphaPilot's MCP server and Binance Agent OS MCP — "
            "see the Agent page for setup."
        ),
    )
    return ChatResponse(reply=reply, tool_used=None, data=None)
