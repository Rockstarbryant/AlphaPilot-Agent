"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, MarketCandidate, TradePlan } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState } from "@/components/ui";

const TABS = [
  { key: "gainer_hunter", label: "Gainers" },
  { key: "recovery_hunter", label: "Recovery" },
  { key: "hot_market_margin", label: "HOT" },
] as const;

const STATUS_TONE: Record<string, "gain" | "loss" | "watch" | "gold" | "muted"> = {
  analyzing: "watch",
  watching: "muted",
  qualified: "gold",
  rejected: "loss",
  trade_proposed: "gain",
  executed: "gain",
};

export default function OpportunitiesPage() {
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("gainer_hunter");
  const [candidates, setCandidates] = useState<MarketCandidate[]>([]);
  const [plansBySymbol, setPlansBySymbol] = useState<Record<string, TradePlan>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([api.listCandidates(), api.listTradePlans()])
      .then(([cands, plans]) => {
        setCandidates(cands);
        const bySymbol: Record<string, TradePlan> = {};
        for (const p of plans) bySymbol[`${p.symbol}:${p.strategy}`] = p;
        setPlansBySymbol(bySymbol);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = candidates
    .filter((c) => c.strategy === tab)
    .sort((a, b) => (b.opportunity_score ?? 0) - (a.opportunity_score ?? 0));

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border border-line rounded-sm p-1 w-fit bg-surface">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-sm rounded-sm ${
              tab === t.key ? "bg-gold text-ink" : "text-muted hover:text-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <Panel>
        {loading ? (
          <EmptyState message="Loading…" />
        ) : filtered.length === 0 ? (
          <EmptyState message="No candidates from the most recent scan for this strategy." />
        ) : (
          <div>
            {filtered.map((c) => {
              const plan = plansBySymbol[`${c.symbol}:${c.strategy}`];
              return (
                <div key={c.id} className="ledger-row px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="tnum font-medium">{c.symbol}</span>
                      <StatusPill tone={STATUS_TONE[c.status] ?? "muted"}>{c.status.replace("_", " ")}</StatusPill>
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                      <span className={`tnum ${c.daily_change_pct >= 0 ? "text-gain" : "text-loss"}`}>
                        {c.daily_change_pct >= 0 ? "+" : ""}
                        {c.daily_change_pct.toFixed(1)}%
                      </span>
                      <span className="tnum text-text">${c.price}</span>
                      <span className="tnum text-gold">{(c.opportunity_score ?? 0).toFixed(0)}/100</span>
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-4 gap-3 text-xs text-muted">
                    <div>
                      24h vol{" "}
                      <span className="tnum text-text">${(c.quote_volume_24h / 1_000_000).toFixed(1)}M</span>
                    </div>
                    <div>
                      Spread <span className="tnum text-text">{c.spread_bps.toFixed(1)}bps</span>
                    </div>
                    {Object.entries(c.score_breakdown)
                      .slice(0, 2)
                      .map(([k, v]) => (
                        <div key={k}>
                          {k.replace(/_/g, " ")} <span className="tnum text-text">{v}</span>
                        </div>
                      ))}
                  </div>
                  {c.reason && <div className="mt-2 text-xs text-muted">{c.reason}</div>}
                  {plan && plan.status === "proposed" && (
                    <div className="mt-3">
                      <Button variant="ghost" onClick={() => router.push(`/agent?plan=${plan.id}`)}>
                        Open trade plan
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
