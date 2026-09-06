"use client";

import { useEffect, useState } from "react";
import { api, MarketCandidate, MarginAnalysis } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState, TextInput } from "@/components/ui";

function SymbolMarginAnalyzer() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<MarginAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function analyze() {
    if (!symbol) return;
    setLoading(true);
    setError(null);
    try {
      setAnalysis(await api.getMarginAnalysis(symbol.toUpperCase()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not analyze margin for this symbol.");
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Panel title="Margin-trade a specific symbol">
      <div className="px-4 py-4 space-y-3">
        <div className="flex items-center gap-2">
          <TextInput value={symbol} onChange={setSymbol} placeholder="SOLUSDT" onKeyDown={(e) => e.key === "Enter" && analyze()} />
          <Button onClick={analyze} disabled={loading}>{loading ? "Analyzing…" : "Analyze"}</Button>
        </div>
        {error && <div className="text-xs text-loss">{error}</div>}
        {analysis && (
          <div className="border border-line rounded-sm p-3 space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="tnum font-medium">{analysis.symbol}</span>
              <StatusPill tone={analysis.eligible ? "gain" : "loss"}>
                {analysis.eligible ? "MARGIN ELIGIBLE" : "MARGIN BLOCKED"}
              </StatusPill>
            </div>
            <div className="text-xs text-muted">bias {analysis.bias} ({analysis.confidence}% confidence)</div>
            <ul className="text-xs text-muted list-disc list-inside">
              {analysis.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
            {analysis.eligible && (
              <div className="text-xs">
                Suggested leverage <span className="text-gold">{analysis.suggested_leverage}x</span> (ceiling {analysis.max_leverage_allowed}x)
                {" — "}
                {analysis.interest_rate_is_estimate ? "estimated" : "reported"} cost ≈{analysis.est_daily_cost_pct_of_position.toFixed(4)}%/day
              </div>
            )}
            <div className="text-xs text-muted italic">{analysis.notes}</div>
          </div>
        )}
      </div>
    </Panel>
  );
}

export default function MarginPage() {
  const [candidates, setCandidates] = useState<MarketCandidate[]>([]);
  useEffect(() => {
    api.listCandidates().then((all) => {
      setCandidates(all.filter((c) => c.strategy === "hot_market_margin"));
    }).catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <SymbolMarginAnalyzer />
      <Panel title="HOT candidates &amp; margin eligibility — scheduled scan">
        {candidates.length === 0 ? (
          <EmptyState message="No HOT candidates from the most recent scan." />
        ) : (
          <div>
            {candidates.map((c) => (
              <div key={c.id} className="ledger-row px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="tnum font-medium">{c.symbol}</span>
                  <div className="flex items-center gap-3">
                    <span className="tnum text-gold">{(c.opportunity_score ?? 0).toFixed(0)}/100</span>
                    <StatusPill tone={c.status === "qualified" ? "gain" : "loss"}>
                      {c.status === "qualified" ? "MARGIN ELIGIBLE" : "MARGIN BLOCKED"}
                    </StatusPill>
                  </div>
                </div>
                {c.reason && <div className="mt-1 text-xs text-muted">{c.reason}</div>}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
