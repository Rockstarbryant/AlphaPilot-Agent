"use client";

import { useEffect, useState } from "react";
import { api, MarketCandidate } from "@/lib/api";
import { Panel, StatusPill, EmptyState } from "@/components/ui";

export default function MarginPage() {
  const [candidates, setCandidates] = useState<MarketCandidate[]>([]);
  useEffect(() => {
    api.listCandidates().then((all) => {
      setCandidates(all.filter((c) => c.strategy === "hot_market_margin"));
    }).catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <Panel>
        <div className="px-4 py-3 text-xs text-muted">
          Margin execution proposals are a Phase 2 addition, pending verification of isolated-margin
          specifics through official Binance documentation (see docs/BINANCE_CAPABILITY_MATRIX.md).
          HOT/margin-eligibility scanning is live below — eligibility reasons are shown for every
          candidate, including why a candidate was blocked.
        </div>
      </Panel>
      <Panel title="HOT candidates &amp; margin eligibility">
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
