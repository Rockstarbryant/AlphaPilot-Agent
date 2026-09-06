"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Circle, ExternalLink } from "lucide-react";
import { api, TradePlan, AgentConfig, AccountContext } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState, TextInput } from "@/components/ui";
import { AccountState } from "@/components/account-state";
import { useUserId } from "@/lib/use-user";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MCP_URL_STORAGE_KEY = "alphapilot_mcp_url";

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

  const [backendUp, setBackendUp] = useState<boolean | null>(null);

  const [mcpUrl, setMcpUrl] = useState("");
  const [mcpCheck, setMcpCheck] = useState<"idle" | "checking" | "reachable" | "unreachable">("idle");

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

  useEffect(() => {
    load();
    api.health().then(() => setBackendUp(true)).catch(() => setBackendUp(false));
    const stored = window.localStorage.getItem(MCP_URL_STORAGE_KEY);
    if (stored) setMcpUrl(stored);
  }, [userId]);

  async function checkMcpUrl() {
    if (!mcpUrl) return;
    window.localStorage.setItem(MCP_URL_STORAGE_KEY, mcpUrl);
    setMcpCheck("checking");
    try {
      // Best-effort reachability check — the MCP transport itself expects a
      // streamable-http session, not a plain GET, so a network-level
      // response (even a 4xx from the MCP handler) means the service is up;
      // only a network failure means it's actually unreachable.
      await fetch(mcpUrl, { method: "GET", mode: "no-cors" });
      setMcpCheck("reachable");
    } catch {
      setMcpCheck("unreachable");
    }
  }

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
      <Panel
        title={
          <span className="flex items-center gap-2">
            AlphaPilot backend
            <span className="flex items-center gap-1 text-xs font-normal">
              <Circle size={7} className={backendUp === null ? "fill-muted text-muted" : backendUp ? "fill-gain text-gain" : "fill-loss text-loss"} />
              <span className="text-muted">
                {backendUp === null ? "checking…" : backendUp ? "reachable" : "unreachable"} — {API_URL}
              </span>
            </span>
          </span>
        }
      >
        {backendUp === false && (
          <div className="px-4 py-3 text-xs text-loss">
            Can't reach the backend at this URL. If it's on Render's free tier, it may be asleep — the
            first request after inactivity can take up to a minute. Also confirm NEXT_PUBLIC_API_URL
            in the frontend deployment matches your actual backend URL.
          </div>
        )}
      </Panel>

      <Panel title="Step 1 — Binance Agent OS (in Claude, not here)">
        <div className="px-4 py-4 space-y-2 text-xs text-muted leading-relaxed">
          <div>
            In Claude Desktop or Claude Code: <strong className="text-text">Settings → Connectors → Add custom connector</strong>.
            Add <code className="text-gold">https://agent.binance.com/mcp/agentic</code> and complete Binance's
            authorization in the browser. AlphaPilot is never part of this step — Binance's agent allowlist
            only covers Claude, ChatGPT, Codex, VS Code, and Grok Bot, not self-built backends.
          </div>
          <a
            href="https://developers.binance.com/en/docs/agent-native/mcp-server/agentic"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-gold hover:underline"
          >
            Binance Agent OS docs <ExternalLink size={11} />
          </a>
        </div>
      </Panel>

      <Panel title="Step 2 — AlphaPilot MCP (your second connector in Claude)">
        <div className="px-4 py-4 space-y-3">
          <div className="text-xs text-muted leading-relaxed">
            This is a <em>different</em> deployed service from the backend above — check your hosting
            dashboard for a service separate from the main API (e.g. named "alphapilot-mcp-server"), copy
            its URL, and add it as a second custom connector in Claude alongside Binance Agent OS. Paste it
            below to save it here and do a basic reachability check.
          </div>
          <div className="flex items-center gap-2">
            <TextInput value={mcpUrl} onChange={setMcpUrl} placeholder="https://your-mcp-service.onrender.com/mcp" />
            <Button variant="ghost" onClick={checkMcpUrl} disabled={!mcpUrl || mcpCheck === "checking"}>
              {mcpCheck === "checking" ? "Checking…" : "Check"}
            </Button>
          </div>
          {mcpCheck === "reachable" && (
            <div className="text-xs text-gain">
              Reached the host. Add this exact URL in Claude as a custom connector, then ask Claude to
              call <code>wiring_instructions</code> to confirm AlphaPilot's tools are visible.
            </div>
          )}
          {mcpCheck === "unreachable" && (
            <div className="text-xs text-loss">
              Couldn't reach this URL at all. If it's on a free hosting tier it may just be asleep — try
              again in a minute. If it still fails, confirm the service is actually deployed and running.
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Step 3 — Relay your Binance balance">
        <div className="px-4 py-4 space-y-3">
          <div className="text-xs text-muted leading-relaxed">
            Once both connectors are added, ask Claude something like <em>"check my Binance balance and
            send it to AlphaPilot"</em> — it reads your account via Binance Agent OS and calls
            AlphaPilot's <code>submit_account_context</code> automatically. No AI client wired up yet? Report
            it manually below so proposals can still be sized (numbers go stale after 10 minutes either way).
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
          {config?.trading_mode === "read_only" && "AlphaPilot's scheduled strategies (Gainer/Recovery/HOT) won't propose new trades."}
          {config?.trading_mode === "approval_required" && "AlphaPilot proposes trades but every one needs your explicit approval — the normal setting."}
          {config?.trading_mode === "autonomous" && "AlphaPilot proposes trades without waiting for a manual approve step, but Binance execution still always requires your connected AI client and, per Binance's own policy, your confirmation on the Binance side."}
          {" "}This setting never lets AlphaPilot place or close a Binance order itself in any mode —
          execution is always through Binance Agent OS MCP, confirmed back below.
        </div>
      </Panel>

      <Panel title="Step 4 — Confirm execution (after Claude places the order)">
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
