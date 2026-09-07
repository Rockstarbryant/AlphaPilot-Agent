"use client";

import { useEffect, useState } from "react";
import { api, MarketCandidate, CoinAnalysis, TradeProposalResult } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState, TextInput } from "@/components/ui";
import { useUserId } from "@/lib/use-user";

function biasTone(bias: string): "gain" | "loss" | "watch" | "gold" | "muted" {
  if (bias === "LONG") return "gain";
  if (bias === "SHORT") return "loss";
  return "watch";
}

function CategoryCard({ title, available, tone, stats, notes }: {
  title: string;
  available: boolean;
  tone: "gain" | "loss" | "watch" | "gold" | "muted";
  stats: { label: string; value: string }[];
  notes: string;
}) {
  return (
    <div className={`border rounded-sm p-2.5 space-y-1.5 ${available ? "border-line" : "border-line opacity-50"}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">{title}</span>
        {!available && <StatusPill tone="muted">no data</StatusPill>}
        {available && tone !== "muted" && <StatusPill tone={tone}>{tone === "gain" ? "bullish" : tone === "loss" ? "bearish" : "neutral"}</StatusPill>}
      </div>
      {stats.length > 0 && (
        <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px] text-muted">
          {stats.map((s, i) => (
            <div key={i}>{s.label}: <span className="text-text">{s.value}</span></div>
          ))}
        </div>
      )}
      <div className="text-[11px] text-muted leading-snug">{notes}</div>
    </div>
  );
}

function toneFromScore(score: number): "gain" | "loss" | "muted" {
  if (score > 0.15) return "gain";
  if (score < -0.15) return "loss";
  return "muted";
}

function SymbolAnalyzer() {
  const userId = useUserId();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<CoinAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [proposing, setProposing] = useState<string | null>(null);
  const [proposal, setProposal] = useState<TradeProposalResult | null>(null);

  async function analyze() {
    if (!symbol) return;
    setLoading(true);
    setError(null);
    setProposal(null);
    try {
      setAnalysis(await api.analyzeSymbol(symbol.toUpperCase()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not analyze symbol.");
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }

  async function propose(intent: "long" | "short" | "spot_hold") {
    if (!userId || !analysis) return;
    setProposing(intent);
    setProposal(null);
    try {
      setProposal(await api.createTradeProposal(userId, { symbol: analysis.symbol, intent }));
    } catch (e) {
      setProposal({ ok: false, error: e instanceof Error ? e.message : "Could not build proposal." });
    } finally {
      setProposing(null);
    }
  }

  return (
    <Panel title="Ask AlphaPilot about a symbol">
      <div className="px-4 py-4 space-y-3">
        <div className="text-xs text-muted">
          Multi-factor analysis — technicals, market structure, volume, order book, derivatives positioning,
          on-chain, sentiment, and cross-market — combined with full transparency about which categories
          actually had data for this symbol. Public data only; no account connection needed.
        </div>
        <div className="flex items-center gap-2">
          <TextInput value={symbol} onChange={setSymbol} placeholder="BTCUSDT" onKeyDown={(e) => e.key === "Enter" && analyze()} />
          <Button onClick={analyze} disabled={loading}>{loading ? "Analyzing…" : "Analyze"}</Button>
        </div>
        {error && <div className="text-xs text-loss">{error}</div>}

        {analysis && (
          <div className="space-y-3">
            {analysis.data_quality === "insufficient" && (
              <div className="border border-loss/40 bg-loss/5 rounded-sm p-2 text-xs text-loss">
                Not enough live price history came back from Binance for this symbol ({analysis.klines_fetched} candles) —
                technicals are unreliable right now. This is a data availability issue, not a real signal.
              </div>
            )}

            <div className="border border-line rounded-sm p-3 space-y-2">
              <div className="flex items-center justify-between flex-wrap gap-1">
                <div className="flex items-center gap-2">
                  <span className="tnum font-medium text-sm">{analysis.symbol}</span>
                  <StatusPill tone={biasTone(analysis.bias)}>{analysis.bias}</StatusPill>
                  <span className="text-xs text-muted">{analysis.confidence}% confidence</span>
                </div>
                <span className="tnum text-sm">${analysis.price}</span>
              </div>
              <div className="text-[11px] text-muted">
                Based on {analysis.categories_used.length}/8 categories ({analysis.coverage_pct}% weighted coverage)
                {analysis.categories_missing.length > 0 && <> — missing: {analysis.categories_missing.join(", ")}</>}.
                {" "}Regime: {analysis.market_regime}.
              </div>
              <div className="text-[10px] text-muted italic">{analysis.model_type}</div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <CategoryCard
                title="Technical"
                available={analysis.data_quality !== "insufficient"}
                tone={analysis.macd.crossover.includes("BULLISH") ? "gain" : analysis.macd.crossover.includes("BEARISH") ? "loss" : "muted"}
                stats={[
                  { label: "RSI", value: analysis.rsi.value !== null ? `${analysis.rsi.value} (${analysis.rsi.signal})` : "—" },
                  { label: "MACD", value: analysis.macd.crossover },
                  { label: "Trend", value: analysis.moving_averages.trend },
                  { label: "Bollinger", value: analysis.bollinger.signal },
                ]}
                notes={
                  analysis.support_resistance.nearest_support || analysis.support_resistance.nearest_resistance
                    ? `Support ${analysis.support_resistance.nearest_support ?? "—"} / Resistance ${analysis.support_resistance.nearest_resistance ?? "—"}`
                    : "No clear support/resistance levels yet."
                }
              />
              <CategoryCard
                title="Market structure"
                available={analysis.structure.sequence !== "UNKNOWN"}
                tone={analysis.structure.sequence === "UPTREND" ? "gain" : analysis.structure.sequence === "DOWNTREND" ? "loss" : "muted"}
                stats={[
                  { label: "Sequence", value: analysis.structure.sequence },
                  { label: "Break", value: analysis.structure.break_of_structure ?? analysis.structure.change_of_character ?? "none" },
                ]}
                notes={analysis.structure.notes}
              />
              <CategoryCard
                title="Volume & liquidity"
                available={analysis.vwap.signal !== "UNKNOWN"}
                tone={analysis.vwap.signal === "ABOVE_VWAP" ? "gain" : analysis.vwap.signal === "BELOW_VWAP" ? "loss" : "muted"}
                stats={[
                  { label: "VWAP", value: analysis.vwap.vwap !== null ? `${analysis.vwap.vwap} (${analysis.vwap.signal})` : "—" },
                  { label: "Vol. profile", value: analysis.volume_profile.signal },
                ]}
                notes={analysis.volume_profile.point_of_control ? `Point of control: ${analysis.volume_profile.point_of_control}` : "Not enough volume data."}
              />
              <CategoryCard
                title="Order book"
                available={analysis.order_book.imbalance_signal !== "UNKNOWN"}
                tone={analysis.order_book.imbalance_signal === "BID_HEAVY" ? "gain" : analysis.order_book.imbalance_signal === "ASK_HEAVY" ? "loss" : "muted"}
                stats={[
                  { label: "Spread", value: analysis.order_book.spread_bps !== null ? `${analysis.order_book.spread_bps}bps` : "—" },
                  { label: "Imbalance", value: analysis.order_book.imbalance_signal },
                ]}
                notes={analysis.order_book.notes}
              />
              <CategoryCard
                title="Derivatives"
                available={analysis.derivatives.available}
                tone={analysis.derivatives.positioning_signal === "OVERHEATED_SHORT" ? "gain" : analysis.derivatives.positioning_signal === "OVERHEATED_LONG" ? "loss" : "muted"}
                stats={[
                  { label: "Funding", value: analysis.derivatives.funding_rate_pct !== null ? `${analysis.derivatives.funding_rate_pct}%/8h` : "—" },
                  { label: "Positioning", value: analysis.derivatives.positioning_signal },
                ]}
                notes={analysis.derivatives.notes}
              />
              <CategoryCard
                title="On-chain"
                available={analysis.onchain.applicable && analysis.onchain.signal !== "UNAVAILABLE"}
                tone={analysis.onchain.signal === "RISING_TVL" ? "gain" : analysis.onchain.signal === "FALLING_TVL" ? "loss" : "muted"}
                stats={
                  analysis.onchain.applicable
                    ? [{ label: "Chain", value: analysis.onchain.chain ?? "—" }, { label: "TVL 7d", value: analysis.onchain.tvl_change_7d_pct !== null ? `${analysis.onchain.tvl_change_7d_pct}%` : "—" }]
                    : []
                }
                notes={analysis.onchain.notes}
              />
              <CategoryCard
                title="Sentiment"
                available={analysis.fear_greed.value !== null}
                tone={analysis.fear_greed.signal === "CONTRARIAN_BUY" ? "gain" : analysis.fear_greed.signal === "CONTRARIAN_CAUTION" ? "loss" : "muted"}
                stats={[
                  { label: "Fear & Greed", value: analysis.fear_greed.value !== null ? `${analysis.fear_greed.value} (${analysis.fear_greed.classification})` : "—" },
                  { label: "News", value: analysis.news_sentiment.available ? `${analysis.news_sentiment.bullish_count}↑ / ${analysis.news_sentiment.bearish_count}↓` : "not configured" },
                ]}
                notes={analysis.news_sentiment.available ? analysis.news_sentiment.top_headlines[0] ?? "No recent headlines." : analysis.news_sentiment.unavailable_reason ?? ""}
              />
              <CategoryCard
                title="Cross-market"
                available={analysis.cross_market.btc_dominance_pct !== null}
                tone={analysis.cross_market.eth_btc_signal === "ALTS_LEADING" ? "gain" : analysis.cross_market.eth_btc_signal === "BTC_LEADING" ? "loss" : "muted"}
                stats={[
                  { label: "BTC dom.", value: analysis.cross_market.btc_dominance_pct !== null ? `${analysis.cross_market.btc_dominance_pct}%` : "—" },
                  { label: "ETH/BTC", value: analysis.cross_market.eth_btc_signal },
                ]}
                notes={analysis.cross_market.notes}
              />
            </div>

            <details className="text-xs">
              <summary className="text-gold cursor-pointer">Full reasoning ({analysis.rationale.length} points)</summary>
              <ul className="text-muted list-disc list-inside space-y-0.5 mt-2">
                {analysis.rationale.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </details>

            <div className="text-xs pt-1"><span className="text-muted">Spot: </span>{analysis.spot_guidance}</div>
            <div className="text-xs"><span className="text-muted">Derivatives: </span>{analysis.derivatives_guidance}</div>

            {userId && (
              <div className="flex items-center gap-2 pt-2">
                <Button variant="ghost" onClick={() => propose("spot_hold")} disabled={proposing !== null}>
                  {proposing === "spot_hold" ? "…" : "Propose spot buy"}
                </Button>
                <Button variant="ghost" onClick={() => propose("long")} disabled={proposing !== null}>
                  {proposing === "long" ? "…" : "Propose long"}
                </Button>
                <Button variant="ghost" onClick={() => propose("short")} disabled={proposing !== null}>
                  {proposing === "short" ? "…" : "Propose short"}
                </Button>
              </div>
            )}
          </div>
        )}

        {proposal && (
          proposal.ok ? (
            <div className="border border-gold/40 bg-gold/5 rounded-sm p-3 text-xs space-y-1">
              <div className="font-medium text-gold">Proposal built — plan {proposal.plan_id}</div>
              <div>Suggested size: ${proposal.suggested_margin_usdt?.toFixed(2)} {proposal.suggested_leverage ? `at ${proposal.suggested_leverage}x` : "(spot)"}</div>
              <div>Stop: {proposal.stop_loss_pct}% — Targets: {Object.entries(proposal.take_profit_targets_pct ?? {}).map(([k, v]) => `+${k}%→${(Number(v) * 100).toFixed(0)}%`).join(", ")}</div>
              <div className="text-muted">{proposal.next_step}</div>
            </div>
          ) : (
            <div className="border border-loss/40 bg-loss/5 rounded-sm p-3 text-xs text-loss">{proposal.error}</div>
          )
        )}
      </div>
    </Panel>
  );
}

export default function MarketPage() {
  const [candidates, setCandidates] = useState<MarketCandidate[]>([]);
  useEffect(() => {
    api.listCandidates().then(setCandidates).catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <SymbolAnalyzer />
      <Panel title="Market universe — most recent scan">
        {candidates.length === 0 ? (
          <EmptyState message="No market data available. Run a scan from the Dashboard." />
        ) : (
          <div>
            {candidates.map((c) => (
              <div key={c.id} className="ledger-row px-4 py-2.5 flex items-center justify-between text-sm">
                <span className="tnum">{c.symbol}</span>
                <div className="flex items-center gap-4">
                  <span className={`tnum ${c.daily_change_pct >= 0 ? "text-gain" : "text-loss"}`}>
                    {c.daily_change_pct >= 0 ? "+" : ""}{c.daily_change_pct.toFixed(1)}%
                  </span>
                  <span className="tnum text-text">${c.price}</span>
                  <span className="tnum text-muted">{(c.quote_volume_24h / 1_000_000).toFixed(1)}M vol</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
