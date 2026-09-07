"""
On-chain data — chain-level TVL trend (free, via DeFiLlama) plus a
pluggable interface for exchange inflow/outflow and whale-wallet tracking,
which genuinely have no free/keyless reliable source (Glassnode, Nansen,
Arkham, and Whale Alert are all paid or heavily-limited). Same honest
degrade-not-fake pattern as app/earn/scanner.py.

TVL isn't meaningful for every symbol — it's a chain/protocol metric, not a
per-token one. This module maps a handful of major base assets to their
native chain on DeFiLlama and reports "not applicable" for anything else,
rather than pretending every token has an on-chain TVL story.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings

settings = get_settings()

DEFILLAMA_CHAINS_URL = "https://api.llama.fi/v2/chains"

# Base asset -> DeFiLlama chain name, for assets where "this chain's TVL
# trend" is a meaningful proxy for demand for the asset itself. Deliberately
# small and explicit rather than a guessed mapping.
BASE_TO_CHAIN = {
    "ETH": "Ethereum", "SOL": "Solana", "BNB": "BSC", "AVAX": "Avalanche",
    "MATIC": "Polygon", "POL": "Polygon", "FTM": "Fantom", "NEAR": "Near",
    "ATOM": "Cosmos", "TON": "Ton", "TRX": "Tron", "ETC": "Ethereum Classic",
    "ARB": "Arbitrum", "OP": "Optimism", "SUI": "Sui", "APT": "Aptos",
}


@dataclass
class OnChainResult:
    applicable: bool
    chain: str | None
    tvl_usd: float | None
    tvl_change_7d_pct: float | None
    signal: str  # RISING_TVL | FALLING_TVL | STABLE | NOT_APPLICABLE | UNAVAILABLE
    whale_flow_data: str  # always "unavailable" in this build — see module docstring
    notes: str


async def analyze_onchain(symbol_base: str) -> OnChainResult:
    chain = BASE_TO_CHAIN.get(symbol_base.upper())
    if chain is None:
        return OnChainResult(
            applicable=False, chain=None, tvl_usd=None, tvl_change_7d_pct=None,
            signal="NOT_APPLICABLE", whale_flow_data="unavailable",
            notes=f"{symbol_base} isn't mapped to a chain with a meaningful TVL story in this build.",
        )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(DEFILLAMA_CHAINS_URL)
        resp.raise_for_status()
        chains = resp.json()
    except httpx.HTTPError as exc:
        return OnChainResult(
            applicable=True, chain=chain, tvl_usd=None, tvl_change_7d_pct=None,
            signal="UNAVAILABLE", whale_flow_data="unavailable",
            notes=f"DeFiLlama TVL request failed: {exc}",
        )

    entry = next((c for c in chains if c.get("name") == chain), None)
    if entry is None:
        return OnChainResult(
            applicable=True, chain=chain, tvl_usd=None, tvl_change_7d_pct=None,
            signal="UNAVAILABLE", whale_flow_data="unavailable",
            notes=f"DeFiLlama has no entry for chain '{chain}'.",
        )

    tvl = entry.get("tvl")
    change_7d = entry.get("change_7d")  # DeFiLlama returns this directly on /v2/chains

    if change_7d is None:
        signal = "UNAVAILABLE"
    elif change_7d > 2:
        signal = "RISING_TVL"
    elif change_7d < -2:
        signal = "FALLING_TVL"
    else:
        signal = "STABLE"

    notes = (
        f"{chain} TVL is ${tvl:,.0f}" if tvl else f"{chain} TVL unavailable"
    ) + (
        f", {change_7d:+.1f}% over 7 days — {'capital is flowing into the ecosystem' if signal == 'RISING_TVL' else 'capital is leaving the ecosystem' if signal == 'FALLING_TVL' else 'roughly flat'}."
        if change_7d is not None else "."
    ) + (
        " Exchange inflow/outflow and whale-wallet tracking need a paid provider (Glassnode/Nansen/Arkham/"
        "Whale Alert) — not available in this build."
    )

    return OnChainResult(
        applicable=True, chain=chain,
        tvl_usd=round(tvl, 0) if tvl else None,
        tvl_change_7d_pct=round(change_7d, 2) if change_7d is not None else None,
        signal=signal, whale_flow_data="unavailable", notes=notes,
    )
