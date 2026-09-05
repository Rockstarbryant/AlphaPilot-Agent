"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, TradePlan, AgentConfig, BinanceConnection } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState } from "@/components/ui";
import { AccountState } from "@/components/account-state";
import { useUserId } from "@/lib/use-user";

export default function AgentPage() {
  return <Suspense fallback={null}><AgentPageInner /></Suspense>;
}

function AgentPageInner() {
  const userId = useUserId();
  const searchParams = useSearchParams();
  const highlightedPlanId = searchParams.get("plan");
  const binanceResult = searchParams.get("binance");
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [connection, setConnection] = useState<BinanceConnection | null>(null);
  const [plans, setPlans] = useState<TradePlan[]>([]);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [message, setMessage] = useState<string>("");

  async function load() {
    const proposed = await api.listTradePlans();
    setPlans(proposed.filter((p) => ["proposed", "approved", "submitting"].includes(p.status)));
    if (userId) {
      setConfig(await api.getAgentConfig(userId));
      setConnection(await api.getBinanceConnection(userId));
    }
  }

  useEffect(() => { load(); }, [userId]);

  useEffect(() => {
    if (binanceResult === "connected") setMessage("Binance Agent OS authorization completed.");
    if (binanceResult === "error") setMessage("Binance Agent OS authorization was not completed.");
  }, [binanceResult]);

  async function connectBinance() {
    if (!userId) return;
    setMessage("");
    try {
      const { authorization_url } = await api.connectBinance(userId);
      window.location.href = authorization_url;
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not start Binance authorization.");
    }
  }

  async function execute(planId: string) {
    setBusyPlan(planId);
    setMessage("");
    try {
      const result = await api.executeTradePlan(planId);
      setMessage(`Binance Agent OS: ${result.status}${result.order_id ? ` — order ${result.order_id}` : ""}`);
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Execution failed.");
      await load();
    } finally {
      setBusyPlan(null);
    }
  }

  async function changeMode(mode: string) {
    if (!userId) return;
    setConfig(await api.setTradingMode(userId, mode));
  }

  return (
    <div className="space-y-4">
      <Panel title="Binance Agent OS">
        <div className="px-4 py-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">Direct MCP connection</div>
              <div className="text-xs text-muted mt-1">
                AlphaPilot is now the Binance MCP client. No API key is stored in AlphaPilot.
              </div>
            </div>
            <StatusPill tone={connection?.authorized ? "gain" : "watch"}>
              {connection?.authorized ? "connected" : "not connected"}
            </StatusPill>
          </div>
          {!connection?.authorized && (
            <Button onClick={connectBinance}>Connect Binance Agent OS</Button>
          )}
          {connection?.authorized && (
            <div className="text-xs text-muted">
              MCP authorization is active. Binance controls the granted scopes and any confirmation required for write actions.
            </div>
          )}
          {message && <div className="text-xs border border-line rounded-sm p-3 bg-surface-raised">{message}</div>}
        </div>
      </Panel>

      {connection?.authorized && <AccountState userId={userId} />}

      <Panel title="Trading mode">
        <div className="px-4 py-3 flex items-center gap-2">
          {["read_only", "approval_required", "autonomous"].map((mode) => (
            <button key={mode} onClick={() => changeMode(mode)} className={`px-3 py-1.5 rounded-sm text-sm border ${
              config?.trading_mode === mode ? "border-gold bg-gold/10 text-gold" : "border-line text-muted hover:text-text"
            }`}>
              {mode.replace("_", " ")}
            </button>
          ))}
        </div>
        <div className="px-4 pb-3 text-xs text-muted">
          AlphaPilot controls the orchestration and calls Binance Agent OS directly. Binance remains the final authorization/confirmation authority for write actions.
        </div>
      </Panel>

      <Panel title="Trade plans — direct execution">
        {plans.length === 0 ? (
          <EmptyState message="No trade plans awaiting direct execution." />
        ) : (
          <div>
            {plans.map((p) => (
              <div key={p.id} className={`ledger-row px-4 py-4 ${p.id === highlightedPlanId ? "bg-gold/5" : ""}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="tnum font-medium">{p.symbol}</span>
                    <StatusPill tone="watch">{p.strategy.replace("_", " ")}</StatusPill>
                    <StatusPill tone={p.risk_check_passed ? "gain" : "loss"}>
                      {p.risk_check_passed ? "risk passed" : "risk rejected"}
                    </StatusPill>
                  </div>
                  <span className="tnum text-gold text-sm">${p.position_size_usdt.toFixed(2)}</span>
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-muted">
                  <span>Reference entry ${p.entry_price}</span>
                  <span>{p.status}</span>
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <Button onClick={() => execute(p.id)} disabled={!connection?.authorized || !p.risk_check_passed || busyPlan === p.id}>
                    {busyPlan === p.id ? "Submitting…" : "Execute via Binance Agent OS"}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
