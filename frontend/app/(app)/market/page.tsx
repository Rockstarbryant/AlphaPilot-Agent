"use client";

import { useEffect, useState } from "react";
import { api, MarketCandidate } from "@/lib/api";
import { Panel, EmptyState } from "@/components/ui";

export default function MarketPage() {
  const [candidates, setCandidates] = useState<MarketCandidate[]>([]);
  useEffect(() => {
    api.listCandidates().then(setCandidates).catch(() => {});
  }, []);

  return (
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
  );
}
