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
          "What do you think about trading BTC/USDT — should I long or short, or buy on spot and hold?"
          Public Binance data only — no account connection needed for this part.
        </div>
        <div className="flex items-center gap-2">
          <TextInput value={symbol} onChange={setSymbol} placeholder="BTCUSDT" onKeyDown={(e) => e.key === "Enter" && analyze()} />
          <Button onClick={analyze} disabled={loading}>{loading ? "Analyzing…" : "Analyze"}</Button>
        </div>
        {error && <div className="text-xs text-loss">{error}</div>}

        {analysis && (
          <div className="border border-line rounded-sm p-3 space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="tnum font-medium">{analysis.symbol}</span>
                <StatusPill tone={biasTone(analysis.bias)}>{analysis.bias}</StatusPill>
                <span className="text-xs text-muted">{analysis.confidence}% confidence</span>
              </div>
              <span className="tnum">${analysis.price}</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-xs text-muted">
              <div>RSI({analysis.rsi.period}): <span className="text-text">{analysis.rsi.value ?? "—"}</span> ({analysis.rsi.signal})</div>
              <div>MACD: <span className="text-text">{analysis.macd.crossover}</span></div>
              <div>Momentum: <span className="text-text">{analysis.momentum.direction}</span> ({analysis.momentum.roc_pct ?? "—"}%)</div>
            </div>
            <div className="text-xs text-muted">Regime: {analysis.market_regime} — {analysis.regime_notes}</div>
            <ul className="text-xs text-muted list-disc list-inside space-y-0.5">
              {analysis.rationale.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
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
