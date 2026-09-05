"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, Position, ExitSignal } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState } from "@/components/ui";

export default function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [signals, setSignals] = useState<ExitSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [executingSignal, setExecutingSignal] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [pos, sig] = await Promise.all([api.listPositions(), api.listExitSignals(false)]);
      setPositions(pos);
      setSignals(sig);
    } catch {
      // handled by empty states below
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runMonitor() {
    setChecking(true);
    try {
      await api.runPositionMonitor();
      await load();
    } finally {
      setChecking(false);
    }
  }

  async function executeExit(id: string) {
    setExecutingSignal(id);
    setMessage(null);
    try {
      const result = await api.executeExitSignal(id);
      setMessage(`Binance Agent OS: ${result.status}${result.order_id ? ` — order ${result.order_id}` : ""}`);
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Exit execution failed.");
      await load();
    } finally {
      setExecutingSignal(null);
    }
  }

  return (
    <div className="space-y-4">
      {message && <div className="text-xs border border-line rounded-sm p-3 bg-surface-raised">{message}</div>}

      {signals.length > 0 && (
        <Panel title="Exit signals — Agent OS execution" className="border-loss/50">
          {signals.map((s) => (
            <div key={s.id} className="ledger-row px-4 py-3 flex items-center justify-between text-sm">
              <div>
                <StatusPill tone={s.reason === "hard_stop" ? "loss" : s.reason === "profit_target" ? "gain" : "gold"}>
                  {s.reason.replace("_", " ")}
                </StatusPill>
                <div className="text-xs text-muted mt-1">{s.detail}</div>
              </div>
              <div className="flex items-center gap-2">
                <StatusPill tone={s.execution_status === "filled" ? "gain" : s.execution_status === "failed" ? "loss" : "watch"}>
                  {s.execution_status.replace("_", " ")}
                </StatusPill>
                {s.execution_status !== "filled" && (
                  <Button onClick={() => executeExit(s.id)} disabled={executingSignal === s.id}>
                    {executingSignal === s.id ? "Submitting…" : "Execute via Agent OS"}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </Panel>
      )}

      <Panel
        title="Open positions"
        action={
          <Button variant="ghost" onClick={runMonitor} disabled={checking}>
            <span className="flex items-center gap-1.5">
              <RefreshCw size={13} className={checking ? "animate-spin" : ""} />
              {checking ? "Checking…" : "Check now"}
            </span>
          </Button>
        }
      >
        {loading ? (
          <EmptyState message="Loading…" />
        ) : positions.length === 0 ? (
          <EmptyState message="No open positions." />
        ) : (
          <div>
            {positions.map((p) => {
              const pnlPct = p.last_checked_price
                ? ((p.last_checked_price - p.entry_price) / p.entry_price) * 100
                : null;
              return (
                <div key={p.id} className="ledger-row px-4 py-3 flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className="tnum font-medium">{p.symbol}</span>
                    <StatusPill tone="watch">{p.strategy.replace("_", " ")}</StatusPill>
                    <StatusPill tone={p.status === "open" ? "gain" : p.status === "closed" ? "muted" : "gold"}>
                      {p.status.replace("_", " ")}
                    </StatusPill>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="tnum text-muted">entry ${p.entry_price}</span>
                    {pnlPct !== null && (
                      <span className={`tnum ${pnlPct >= 0 ? "text-gain" : "text-loss"}`}>
                        {pnlPct >= 0 ? "+" : ""}
                        {pnlPct.toFixed(1)}%
                      </span>
                    )}
                    <span className="tnum text-xs text-muted">
                      {(p.remaining_fraction * 100).toFixed(0)}% remaining
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
