"use client";

import { useEffect, useState } from "react";
import { api, TradePlan } from "@/lib/api";
import { Panel, StatusPill, EmptyState } from "@/components/ui";

export default function ActivityPage() {
  const [plans, setPlans] = useState<TradePlan[]>([]);
  useEffect(() => {
    api.listTradePlans().then(setPlans).catch(() => {});
  }, []);

  const sorted = [...plans].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <Panel title="Activity">
      {sorted.length === 0 ? (
        <EmptyState message="No agent activity yet." />
      ) : (
        <div>
          {sorted.map((p) => (
            <div key={p.id} className="ledger-row px-4 py-3 flex items-center justify-between text-sm">
              <div>
                <span className="tnum">{p.symbol}</span>{" "}
                <span className="text-muted text-xs">— {p.strategy.replace("_", " ")}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="tnum text-xs text-muted">
                  {new Date(p.created_at).toLocaleString()}
                </span>
                <StatusPill tone={p.status === "risk_rejected" ? "loss" : p.status === "open" ? "gain" : "watch"}>
                  {p.status.replace("_", " ")}
                </StatusPill>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
