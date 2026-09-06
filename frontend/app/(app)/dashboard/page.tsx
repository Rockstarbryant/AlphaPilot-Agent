"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, MarketSession, TradePlan } from "@/lib/api";
import { Panel, Stat, StatusPill, Button, EmptyState } from "@/components/ui";
import { useUserId } from "@/lib/use-user";
import { AccountState } from "@/components/account-state";

export default function DashboardPage() {
  const userId = useUserId();
  const [session, setSession] = useState<MarketSession | null>(null);
  const [plans, setPlans] = useState<TradePlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [sessions, tradePlans] = await Promise.all([
        api.listSessions(),
        api.listTradePlans("proposed"),
      ]);
      setSession(sessions[0] ?? null);
      setPlans(tradePlans);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach AlphaPilot backend");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runScan() {
    if (!userId) return;
    setScanning(true);
    try {
      await api.runMarketScan(userId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  if (error) {
    return (
      <Panel>
        <EmptyState
          message={`${error} — is the backend running at ${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}?`}
        />
      </Panel>
    );
  }

  return (
    <div className="space-y-5">
      {userId && <AccountState userId={userId} compact />}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Panel className="p-4">
          <Stat label="Opportunities awaiting approval" value={String(plans.length)} />
        </Panel>
        <Panel className="p-4">
          <Stat label="Gainers scanned" value={String(session?.gainers_scanned ?? 0)} />
        </Panel>
        <Panel className="p-4">
          <Stat label="Losers scanned" value={String(session?.losers_scanned ?? 0)} />
        </Panel>
        <Panel className="p-4">
          <Stat label="HOT candidates" value={String(session?.hot_candidates_found ?? 0)} />
        </Panel>
      </div>

      <Panel
        title="Latest market scan"
        action={
          <Button variant="ghost" onClick={runScan} disabled={scanning || !userId}>
            <span className="flex items-center gap-1.5">
              <RefreshCw size={13} className={scanning ? "animate-spin" : ""} />
              {scanning ? "Scanning…" : "Run scan"}
            </span>
          </Button>
        }
      >
        {loading ? (
          <EmptyState message="Loading…" />
        ) : session ? (
          <div className="px-4 py-4 space-y-3">
            <div className="text-xs text-muted">Runs automatically every hour across spot and futures markets — this button re-runs it now.</div>
            <div className="flex items-center gap-6 text-sm">
            <div>
              <div className="text-xs text-muted mb-1">Started</div>
              <div className="tnum">{new Date(session.started_at).toLocaleString()}</div>
            </div>
            <div>
              <div className="text-xs text-muted mb-1">Regime</div>
              {session.market_regime && (
                <StatusPill tone={session.market_regime === "BULLISH" ? "gain" : session.market_regime === "BEARISH" || session.market_regime === "RISK_OFF" ? "loss" : "watch"}>
                  {session.market_regime}
                </StatusPill>
              )}
            </div>
            <div>
              <div className="text-xs text-muted mb-1">Status</div>
              <StatusPill tone={session.status === "completed" ? "gain" : "watch"}>{session.status}</StatusPill>
            </div>
            </div>
          </div>
        ) : (
          <EmptyState message="No market data available. Run a scan to begin." />
        )}
      </Panel>

      <Panel title="Awaiting your approval">
        {plans.length === 0 ? (
          <EmptyState message="No qualifying opportunities right now." />
        ) : (
          <div>
            {plans.map((p) => (
              <div key={p.id} className="ledger-row flex items-center justify-between px-4 py-3 text-sm">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="tnum">{p.symbol}</span>
                    <StatusPill tone="watch">{p.strategy.replace("_", " ")}</StatusPill>
                  </div>
                  <div className="text-xs text-muted mt-1 max-w-md">{p.reason}</div>
                </div>
                <div className="text-right">
                  <div className="tnum text-gold">{p.opportunity_score.toFixed(0)}/100</div>
                  <div className="tnum text-xs text-muted">${p.position_size_usdt.toFixed(2)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
