"""
Simple Earn opportunity scanner.

Per docs/BINANCE_CAPABILITY_MATRIX.md, Simple Earn subscribe/redeem is not
part of Agent OS's documented trading scope, so AlphaPilot never subscribes
or redeems anything here either (same rule app/services/capital_optimizer.py
already follows) — this module only *reads* flexible-product APY so
AlphaPilot can recommend where idle capital could go.

Binance's flexible-product list (``GET /sapi/v1/simple-earn/flexible/list``)
is a SIGNED endpoint (security type USER_DATA) — unlike the plain public
market-data endpoints this project otherwise uses, it requires a full
HMAC-SHA256 signature over the query string (timestamp + recvWindow), not
just an API-key header. An earlier version of this module assumed a bare
API key would work and got a raw 400 back from Binance for every call. If
you see "no API key" as the failure reason, both BINANCE_EARN_API_KEY and
BINANCE_EARN_API_SECRET must be set — a key alone is not enough. Use a
read-only key (no trading/withdrawal permission needed for Simple Earn read
access) generated specifically for this; AlphaPilot never sends this
secret anywhere except in the local HMAC computation below.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import urlencode

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


def _signed_params(extra: dict) -> dict:
    params = {**extra, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
    query = urlencode(params)
    signature = hmac.new(
        settings.binance_earn_api_secret.encode(), query.encode(), hashlib.sha256
    ).hexdigest()
    params["signature"] = signature
    return params


async def scan_earn_opportunities(quote_assets: tuple[str, ...] = ("USDT", "USDC", "BTC", "ETH")) -> dict:
    """
    Returns a dict with either populated ``opportunities`` (best APY first)
    or an ``unavailable_reason`` explaining why none could be fetched —
    callers must show the reason, never silently show an empty list as "no
    opportunities exist".
    """
    api_key = getattr(settings, "binance_earn_api_key", "") or ""
    api_secret = getattr(settings, "binance_earn_api_secret", "") or ""
    if not api_key or not api_secret:
        return {
            "opportunities": [],
            "unavailable_reason": (
                "Binance's Simple Earn flexible-product list is a signed endpoint — it needs BOTH "
                "BINANCE_EARN_API_KEY and BINANCE_EARN_API_SECRET set (a key alone isn't enough). "
                "Generate a read-only Binance API key/secret pair (no trading or withdrawal permission "
                "required) and set both env vars, or ask your connected AI client to read current APYs "
                "from Binance Agent OS if it exposes an Earn tool."
            ),
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                EARN_LIST_URL,
                params=_signed_params({}),
                headers={"X-MBX-APIKEY": api_key},
            )
        if not resp.is_success:
            # Any non-2xx here — 400 (bad/missing params), 401 (bad key),
            # 403 (IP/permission) — means this call isn't working, and the
            # specific Binance error code is more useful to the user than a
            # generic message, so it's included rather than swallowed.
            return {
                "opportunities": [],
                "unavailable_reason": (
                    f"Binance rejected the Simple Earn list request (HTTP {resp.status_code}): "
                    f"{resp.text[:300]}. Double-check BINANCE_EARN_API_KEY/BINANCE_EARN_API_SECRET are a "
                    "valid, currently-enabled key pair — Simple Earn read access does not require "
                    "trading permission, but the key must still be active and IP-unrestricted (or your "
                    "server's IP must be on the key's allowlist)."
                ),
            }
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
