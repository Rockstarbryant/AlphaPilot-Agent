"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, TradePlan, AgentConfig, AccountContext } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState, TextInput } from "@/components/ui";
import { AccountState } from "@/components/account-state";
import { useUserId } from "@/lib/use-user";

export default function AgentPage() {
  return <Suspense fallback={null}><AgentPageInner /></Suspense>;
}

function AgentPageInner() {
  const userId = useUserId();
  const searchParams = useSearchParams();
  const highlightedPlanId = searchParams.get("plan");
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [context, setContext] = useState<AccountContext | null>(null);
  const [plans, setPlans] = useState<TradePlan[]>([]);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [message, setMessage] = useState<string>("");

  // Manual account-context form — for when there's no AI client wired up yet.
  const [portfolioValue, setPortfolioValue] = useState("");
  const [openExposure, setOpenExposure] = useState("");
  const [marginExposure, setMarginExposure] = useState("");
  const [submittingContext, setSubmittingContext] = useState(false);

  // Confirm-execution form state, keyed by plan id.
  const [confirmForms, setConfirmForms] = useState<Record<string, { orderId: string; fillPrice: string }>>({});

  async function load() {
    const proposed = await api.listTradePlans();
    setPlans(proposed.filter((p) => ["proposed", "approved", "submitting"].includes(p.status)));
    if (userId) {
      setConfig(await api.getAgentConfig(userId));
      const acct = await api.getAccountContext(userId);
      setContext(acct.status === "none_reported" ? null : acct);
    }
  }

  useEffect(() => { load(); }, [userId]);

  async function submitContext() {
    if (!userId || !portfolioValue) return;
    setSubmittingContext(true);
    setMessage("");
    try {
      await api.submitAccountContext(userId, {
        portfolio_value_usdt: Number(portfolioValue),
        open_exposure_usdt: openExposure ? Number(openExposure) : 0,
        margin_exposure_usdt: marginExposure ? Number(marginExposure) : 0,
      });
      setMessage("Account context saved.");
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not save account context.");
    } finally {
      setSubmittingContext(false);
    }
  }

  async function confirmExecuted(planId: string) {
    const form = confirmForms[planId];
    if (!form?.orderId) {
      setMessage("Enter the Binance order id first.");
      return;
    }
    setBusyPlan(planId);
    setMessage("");
    try {
      await api.confirmExecution(planId, form.orderId, form.fillPrice ? Number(form.fillPrice) : undefined);
      setMessage(`Plan ${planId} confirmed executed — AlphaPilot is now monitoring the position.`);
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not confirm execution.");
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
          <div className="text-sm font-medium">AlphaPilot is not on Binance's agent allowlist</div>
          <div className="text-xs text-muted leading-relaxed">
            Binance Agent OS only allows Claude Desktop/Code, ChatGPT, Codex, VS Code, and Grok Bot to
            connect directly — AlphaPilot's own backend is not on that list, so it never holds a Binance
            credential. Instead: connect one of those AI clients to <em>both</em> Binance Agent OS MCP and
            AlphaPilot's MCP server (see the wiring_instructions tool). That client reads your Binance
            balance and relays it here, gets a risk-validated proposal from AlphaPilot, and — once you
            approve — places the order through Binance Agent OS MCP directly.
          </div>
          <div className="text-xs text-muted">
            No AI client wired up yet? You can report your balance manually below so proposals can still be sized.
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 pt-1">
            <TextInput type="number" value={portfolioValue} onChange={setPortfolioValue} placeholder="Portfolio value (USDT)" />
            <TextInput type="number" value={openExposure} onChange={setOpenExposure} placeholder="Open exposure (USDT)" />
            <TextInput type="number" value={marginExposure} onChange={setMarginExposure} placeholder="Margin exposure (USDT)" />
          </div>
          <Button onClick={submitContext} disabled={!portfolioValue || submittingContext}>
            {submittingContext ? "Saving…" : "Report account context"}
          </Button>
          {message && <div className="text-xs border border-line rounded-sm p-3 bg-surface-raised">{message}</div>}
        </div>
      </Panel>

      {context && <AccountState userId={userId} />}

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
          "Autonomous" only affects whether AlphaPilot's scheduled strategies keep proposing new plans —
          AlphaPilot never places or closes a Binance order itself in any mode. Execution is always through
          Binance Agent OS MCP, confirmed back below.
        </div>
      </Panel>

      <Panel title="Trade plans awaiting Binance Agent OS execution">
        {plans.length === 0 ? (
          <EmptyState message="No trade plans awaiting execution." />
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
                {p.risk_check_passed && (
                  <div className="mt-3 flex items-center gap-2">
                    <TextInput
                      value={confirmForms[p.id]?.orderId ?? ""}
                      onChange={(v) => setConfirmForms((f) => ({ ...f, [p.id]: { ...f[p.id], orderId: v, fillPrice: f[p.id]?.fillPrice ?? "" } }))}
                      placeholder="Binance order id (after placing via Agent OS)"
                    />
                    <TextInput
                      type="number"
                      value={confirmForms[p.id]?.fillPrice ?? ""}
                      onChange={(v) => setConfirmForms((f) => ({ ...f, [p.id]: { ...f[p.id], fillPrice: v, orderId: f[p.id]?.orderId ?? "" } }))}
                      placeholder="Fill price (optional)"
                    />
                    <Button onClick={() => confirmExecuted(p.id)} disabled={busyPlan === p.id}>
                      {busyPlan === p.id ? "Confirming…" : "Confirm executed"}
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
