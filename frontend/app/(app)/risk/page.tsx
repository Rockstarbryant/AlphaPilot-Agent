"use client";

import { useEffect, useState } from "react";
import { api, TradePlan } from "@/lib/api";
import { Panel, Stat, EmptyState, StatusPill } from "@/components/ui";
import { useUserId } from "@/lib/use-user";

export default function RiskPage() {
  useUserId();
  const [rejected, setRejected] = useState<TradePlan[]>([]);

  useEffect(() => {
    api.listTradePlans("risk_rejected").then(setRejected).catch(() => {});
  }, []);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <Panel className="p-4">
          <Stat label="Max Spot trade" value="$100.00" />
        </Panel>
        <Panel className="p-4">
          <Stat label="Max Spot allocation" value="10%" />
        </Panel>
        <Panel className="p-4">
          <Stat label="Max Margin allocation" value="3%" />
        </Panel>
        <Panel className="p-4">
          <Stat label="Max leverage" value="3x" />
        </Panel>
        <Panel className="p-4">
          <Stat label="Max daily loss" value="5%" tone="loss" />
        </Panel>
        <Panel className="p-4">
          <Stat label="Gainer hard stop" value="-20%" tone="loss" />
        </Panel>
      </div>

      <Panel title="Recently risk-rejected proposals">
        {rejected.length === 0 ? (
          <EmptyState message="No proposals have been rejected by the risk engine." />
        ) : (
          <div>
            {rejected.map((p) => (
              <div key={p.id} className="ledger-row px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="tnum font-medium">{p.symbol}</span>
                  <StatusPill tone="loss">risk rejected</StatusPill>
                </div>
                <div className="mt-1 space-y-0.5">
                  {Object.entries(p.risk_check_notes).map(([check, note]) => (
                    <div key={check} className="text-xs text-muted">
                      <span className="text-loss">{check.replace(/_/g, " ")}:</span> {note}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <div className="text-xs text-muted px-1">
        Limits shown reflect server defaults. Edit yours in Settings — every value here is enforced
        deterministically in app/risk/engine.py and never overridden by the AI layer.
      </div>
    </div>
  );
}
