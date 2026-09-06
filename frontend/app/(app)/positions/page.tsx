"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, Position, ExitSignal, PanicExplanation } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState, TextInput } from "@/components/ui";

export default function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [signals, setSignals] = useState<ExitSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [confirmingSignal, setConfirmingSignal] = useState<string | null>(null);
  const [signalOrderIds, setSignalOrderIds] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const [panicPosition, setPanicPosition] = useState<string | null>(null);
  const [panicQuestion, setPanicQuestion] = useState("");
  const [panicResult, setPanicResult] = useState<PanicExplanation | null>(null);
  const [panicLoading, setPanicLoading] = useState(false);

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

  async function confirmSignalExecuted(id: string) {
    const orderId = signalOrderIds[id];
    if (!orderId) {
      setMessage("Enter the Binance order id for this exit first.");
      return;
    }
    setConfirmingSignal(id);
    setMessage(null);
    try {
      await api.confirmExitExecution(id, orderId);
      setMessage(`Exit signal ${id} confirmed — position updated.`);
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not confirm exit execution.");
      await load();
    } finally {
      setConfirmingSignal(null);
    }
  }

  async function askAlphaPilot(positionId: string) {
    setPanicLoading(true);
    setPanicResult(null);
    try {
      const result = await api.getPanicExplanation(positionId, panicQuestion);
      setPanicResult(result);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not get an explanation.");
    } finally {
      setPanicLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      {message && <div className="text-xs border border-line rounded-sm p-3 bg-surface-raised">{message}</div>}

      {signals.length > 0 && (
        <Panel title="Exit signals — detected, awaiting Binance Agent OS execution" className="border-loss/50">
          {signals.map((s) => (
            <div key={s.id} className="ledger-row px-4 py-3 text-sm space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <StatusPill tone={s.reason === "hard_stop" ? "loss" : s.reason === "profit_target" ? "gain" : "gold"}>
                    {s.reason.replace("_", " ")}
                  </StatusPill>
                  <div className="text-xs text-muted mt-1">{s.detail}</div>
                </div>
                <StatusPill tone={s.execution_status === "filled" ? "gain" : s.execution_status === "failed" ? "loss" : "watch"}>
                  {s.execution_status.replace("_", " ")}
                </StatusPill>
              </div>
              {s.execution_status !== "filled" && (
                <div className="flex items-center gap-2">
                  <TextInput
                    value={signalOrderIds[s.id] ?? ""}
                    onChange={(v) => setSignalOrderIds((m) => ({ ...m, [s.id]: v }))}
                    placeholder="Binance order id (after executing via Agent OS)"
                  />
                  <Button onClick={() => confirmSignalExecuted(s.id)} disabled={confirmingSignal === s.id}>
                    {confirmingSignal === s.id ? "Confirming…" : "Confirm executed"}
                  </Button>
                </div>
              )}
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
              const isPanicOpen = panicPosition === p.id;
              return (
                <div key={p.id} className="ledger-row px-4 py-3 text-sm space-y-2">
                  <div className="flex items-center justify-between">
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
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setPanicPosition(isPanicOpen ? null : p.id);
                          setPanicResult(null);
                          setPanicQuestion("");
                        }}
                      >
                        {isPanicOpen ? "Close" : "Ask AlphaPilot"}
                      </Button>
                    </div>
                  </div>

                  {isPanicOpen && (
                    <div className="border border-line rounded-sm p-3 space-y-2 bg-surface-raised">
                      <div className="flex items-center gap-2">
                        <TextInput
                          value={panicQuestion}
                          onChange={setPanicQuestion}
                          placeholder="e.g. it's going against me, should I close it?"
                          onKeyDown={(e) => e.key === "Enter" && askAlphaPilot(p.id)}
                        />
                        <Button onClick={() => askAlphaPilot(p.id)} disabled={panicLoading}>
                          {panicLoading ? "Thinking…" : "Ask"}
                        </Button>
                      </div>
                      {panicResult && panicResult.position_id === p.id && (
                        <div className="text-xs space-y-1.5 pt-1">
                          <div className="flex items-center gap-2">
                            <StatusPill tone={panicResult.recommendation === "HOLD" ? "gain" : panicResult.recommendation === "CLOSE" ? "loss" : "gold"}>
                              {panicResult.recommendation.replace("_", " ")}
                            </StatusPill>
                            <span className="text-muted">current bias: {panicResult.current_bias} ({panicResult.current_confidence}%)</span>
                          </div>
                          <div>{panicResult.headline}</div>
                          <div className="text-muted italic">{panicResult.note}</div>
                        </div>
                      )}
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
