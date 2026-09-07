"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, MarketCandidate, TradePlan } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState } from "@/components/ui";

const STRATEGY_TABS = [
  { key: "gainer_hunter", label: "Gainers" },
  { key: "recovery_hunter", label: "Recovery" },
  { key: "hot_market_margin", label: "HOT" },
] as const;

const MARKET_TABS = [
  { key: "all", label: "All markets" },
  { key: "spot", label: "Spot" },
  { key: "futures", label: "Futures" },
] as const;

const STATUS_TONE: Record<string, "gain" | "loss" | "watch" | "gold" | "muted"> = {
  analyzing: "watch",
  watching: "muted",
  qualified: "gold",
  rejected: "loss",
  trade_proposed: "gain",
  executed: "gain",
};

// Plain-language status labels for non-technical users — the raw enum
// value ("trade_proposed") means nothing to someone who isn't reading the code.
const STATUS_PLAIN: Record<string, string> = {
  analyzing: "Still analyzing",
  watching: "Watching — no trade yet",
  qualified: "Qualified",
  rejected: "Not trading this",
  trade_proposed: "Trade proposed — awaiting approval",
  executed: "Executed",
};

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m ago`;
}

export default function OpportunitiesPage() {
  const router = useRouter();
  const [strategyTab, setStrategyTab] = useState<(typeof STRATEGY_TABS)[number]["key"]>("gainer_hunter");
  const [marketTab, setMarketTab] = useState<(typeof MARKET_TABS)[number]["key"]>("all");
  const [candidates, setCandidates] = useState<MarketCandidate[]>([]);
  const [plansBySymbol, setPlansBySymbol] = useState<Record<string, TradePlan>>({});
  const [loading, setLoading] = useState(true);
  const [explaining, setExplaining] = useState<string | null>(null);
  const [explanations, setExplanations] = useState<Record<string, { text: string; aiNarrated: boolean }>>({});

  function load() {
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
  }

  useEffect(load, []);

  async function explainSimply(candidate: MarketCandidate) {
    if (candidate.ai_explanation) {
      setExplanations((e) => ({ ...e, [candidate.id]: { text: candidate.ai_explanation!, aiNarrated: true } }));
      return;
    }
    setExplaining(candidate.id);
    try {
      const result = await api.explainCandidate(candidate.id);
      setExplanations((e) => ({ ...e, [candidate.id]: { text: result.explanation, aiNarrated: result.ai_narrated } }));
    } catch {
      setExplanations((e) => ({ ...e, [candidate.id]: { text: "Couldn't generate an explanation right now.", aiNarrated: false } }));
    } finally {
      setExplaining(null);
    }
  }

  const filtered = candidates
    .filter((c) => c.strategy === strategyTab)
    .filter((c) => marketTab === "all" || c.market_type === marketTab)
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1 border border-line rounded-sm p-1 w-fit bg-surface">
          {STRATEGY_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setStrategyTab(t.key)}
              className={`px-3 py-1.5 text-sm rounded-sm ${strategyTab === t.key ? "bg-gold text-ink" : "text-muted hover:text-text"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1 border border-line rounded-sm p-1 w-fit bg-surface">
          {MARKET_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setMarketTab(t.key)}
              className={`px-3 py-1.5 text-sm rounded-sm ${marketTab === t.key ? "bg-gold text-ink" : "text-muted hover:text-text"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="text-xs text-muted">
        Coins scanned in the last 6 hours. AlphaPilot re-scans spot and futures markets every hour —
        anything older is automatically removed.
      </div>

      <Panel>
        {loading ? (
          <EmptyState message="Loading…" />
        ) : filtered.length === 0 ? (
          <EmptyState message="No candidates from the last 6 hours for this filter. The next scan runs within the hour." />
        ) : (
          <div>
            {filtered.map((c) => {
              const plan = plansBySymbol[`${c.symbol}:${c.strategy}`];
              return (
                <div key={c.id} className="ledger-row px-4 py-3">
                  <div className="flex items-center justify-between flex-wrap gap-1">
                    <div className="flex items-center gap-2">
                      <span className="tnum font-medium">{c.symbol}</span>
                      <StatusPill tone={c.market_type === "futures" ? "gold" : "watch"}>{c.market_type}</StatusPill>
                      <StatusPill tone={STATUS_TONE[c.status] ?? "muted"}>{STATUS_PLAIN[c.status] ?? c.status}</StatusPill>
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

                  <div className="mt-1 text-[11px] text-muted">scanned {timeAgo(c.created_at)}</div>

                  {c.reason && <div className="mt-2 text-xs text-muted">{c.reason}</div>}

                  {explanations[c.id] ? (
                    <div className="mt-2 text-sm border border-line rounded-sm p-2 bg-surface-raised space-y-1">
                      <div>{explanations[c.id].text}</div>
                      {!explanations[c.id].aiNarrated && (
                        <div className="text-[10px] text-muted italic">templated explanation — AI narration unavailable right now</div>
                      )}
                    </div>
                  ) : (
                    <button
                      onClick={() => explainSimply(c)}
                      disabled={explaining === c.id}
                      className="mt-2 text-xs text-gold hover:underline"
                    >
                      {explaining === c.id ? "Explaining…" : "Explain this in plain English"}
                    </button>
                  )}

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
