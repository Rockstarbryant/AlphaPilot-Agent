"""
Simple Earn opportunity scanner.

Per docs/BINANCE_CAPABILITY_MATRIX.md, Simple Earn subscribe/redeem is not
part of Agent OS's documented trading scope, so AlphaPilot never subscribes
or redeems anything here either (same rule app/services/capital_optimizer.py
already follows) — this module only *reads* flexible-product APY so
AlphaPilot can recommend where idle capital could go.

Binance's flexible-product list is served from
``GET /sapi/v1/simple-earn/flexible/list`` on the *signed* SAPI host
(api.binance.com), which historically requires an API-key header even for
the "list" endpoint on some accounts, and is NOT reachable from the
unauthenticated ``data-api.binance.vision`` mirror AlphaPilot otherwise uses
for market data. AlphaPilot holds no Binance API key (see core/config.py),
so this scanner calls the endpoint unauthenticated and degrades to a clear,
empty-but-explained result if Binance rejects it — it must never invent APY
figures. If your Binance account has a read-only API key available, set it
via BINANCE_EARN_API_KEY and this module will send it as a plain header;
no secret/signature is required for a read-only list call in that case.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings

settings = get_settings()

EARN_LIST_URL = "https://api.binance.com/sapi/v1/simple-earn/flexible/list"


@dataclass
class EarnOpportunity:
    asset: str
    product_id: str
    latest_apy_pct: float
    min_purchase_amount: float
    is_hot: bool


class EarnScanUnavailable(RuntimeError):
    pass


async def scan_earn_opportunities(quote_assets: tuple[str, ...] = ("USDT", "USDC", "BTC", "ETH")) -> dict:
    """
    Returns a dict with either populated ``opportunities`` (best APY first)
    or an ``unavailable_reason`` explaining why none could be fetched —
    callers must show the reason, never silently show an empty list as "no
    opportunities exist".
    """
    headers = {}
    api_key = getattr(settings, "binance_earn_api_key", "") or ""
    if api_key:
        headers["X-MBX-APIKEY"] = api_key

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(EARN_LIST_URL, headers=headers)
        if resp.status_code == 401:
            return {
                "opportunities": [],
                "unavailable_reason": (
                    "Binance requires an API key for the Simple Earn flexible-product list on this "
                    "account. AlphaPilot holds no Binance API key by design (see core/config.py). "
                    "Set BINANCE_EARN_API_KEY to a read-only key to enable this scan, or ask your "
                    "connected AI client to read current APYs from Binance Agent OS if it exposes "
                    "an Earn tool."
                ),
            }
        resp.raise_for_status()
        raw = resp.json()
    except httpx.HTTPError as exc:
        return {"opportunities": [], "unavailable_reason": f"Binance Earn list request failed: {exc}"}

    rows = raw.get("rows", raw) if isinstance(raw, dict) else raw
    opportunities: list[EarnOpportunity] = []
    for row in rows or []:
        try:
            asset = row["asset"]
            if quote_assets and asset not in quote_assets:
                continue
            apy = float(row.get("latestAnnualPercentageRate", row.get("latestApy", 0.0))) * (
                100 if float(row.get("latestAnnualPercentageRate", row.get("latestApy", 0.0))) < 1 else 1
            )
            opportunities.append(
                EarnOpportunity(
                    asset=asset,
                    product_id=str(row.get("productId", asset)),
                    latest_apy_pct=round(apy, 2),
                    min_purchase_amount=float(row.get("minPurchaseAmount", 0.0)),
                    is_hot=bool(row.get("isSoldOut", False) is False and row.get("hot", False)),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    opportunities.sort(key=lambda o: o.latest_apy_pct, reverse=True)
    return {
        "opportunities": [o.__dict__ for o in opportunities],
        "unavailable_reason": None if opportunities else "No flexible products matched the requested assets.",
    }
