"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, WalletCards } from "lucide-react";
import { api, AccountContext } from "@/lib/api";
import { Panel, Stat, StatusPill, Button, EmptyState } from "@/components/ui";

export type AccountBalance = {
  asset: string;
  free: number;
  locked: number;
  total: number;
};

function numberValue(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function collectBalances(value: unknown, out: AccountBalance[] = []): AccountBalance[] {
  if (Array.isArray(value)) {
    for (const item of value) collectBalances(item, out);
    return out;
  }
  if (!value || typeof value !== "object") return out;
  const record = value as Record<string, unknown>;
  const asset = String(record.asset ?? record.currency ?? record.coin ?? "").toUpperCase();
  if (asset) {
    const free = numberValue(record.free ?? record.available ?? record.availableBalance);
    const locked = numberValue(record.locked ?? record.hold ?? record.reserved) ?? 0;
    const total = numberValue(record.total ?? record.balance ?? record.walletBalance ?? record.equity) ??
      ((free ?? 0) + locked);
    if (free !== null || total !== 0) {
      const existing = out.find((b) => b.asset === asset);
      if (existing) {
        existing.free += free ?? 0;
        existing.locked += locked;
        existing.total += total;
      } else {
        out.push({ asset, free: free ?? Math.max(0, total - locked), locked, total });
      }
    }
  }
  for (const child of Object.values(record)) collectBalances(child, out);
  return out;
}

function collectItems(value: unknown, keys: string[]): unknown[] {
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  for (const key of keys) if (Array.isArray(record[key])) return record[key] as unknown[];
  for (const child of Object.values(record)) {
    const found = collectItems(child, keys);
    if (found.length) return found;
  }
  return [];
}

// AlphaPilot cannot read Binance Agent OS itself (it's not on Binance's
// agent allowlist — see BINANCE_AGENT_OS_REFACTOR.md). This panel shows the
// account state most recently REPORTED by whichever AI client the user is
// chatting with (via submit_account_context), not a live read.
export function AccountState({ userId, compact = false }: { userId: string | null; compact?: boolean }) {
  const [context, setContext] = useState<AccountContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.getAccountContext(userId);
      setContext(result.status === "none_reported" ? null : result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load reported account context.");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { refresh(); }, [refresh]);

  const raw = context?.raw_snapshot ?? null;
  const balances = useMemo(() => collectBalances(raw).filter((b) => b.total !== 0).sort((a, b) => b.total - a.total), [raw]);
  const positions = useMemo(() => collectItems(raw, ["positions", "openPositions"]), [raw]);
  const orders = useMemo(() => collectItems(raw, ["orders", "openOrders"]), [raw]);
  const usdt = balances.find((b) => b.asset === "USDT");

  if (!userId) return null;

  const reportedAt = context?.reported_at ? new Date(context.reported_at) : null;
  const ageMinutes = reportedAt ? (Date.now() - reportedAt.getTime()) / 60000 : null;

  return (
    <Panel
      title="Reported Binance account context"
      action={
        <Button variant="ghost" onClick={refresh} disabled={loading}>
          <span className="flex items-center gap-1.5"><RefreshCw size={13} className={loading ? "animate-spin" : ""} />{loading ? "Refreshing…" : "Refresh"}</span>
        </Button>
      }
    >
      <div className="px-4 py-4 space-y-4">
        {error ? (
          <div className="border border-loss/40 bg-loss/5 rounded-sm p-3 text-xs text-loss">{error}</div>
        ) : !context && loading ? (
          <EmptyState message="Loading last reported account context…" />
        ) : !context ? (
          <EmptyState message="No account context reported yet. Ask your connected AI client (with Binance Agent OS access) to read your balance and call submit_account_context — see the Agent page for setup." />
        ) : (
          <>
            <div className={`grid ${compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-4"} gap-4`}>
              <Stat label="Portfolio value" value={context.portfolio_value_usdt !== undefined ? `$${context.portfolio_value_usdt.toFixed(2)}` : "—"} sub="as last reported" />
              <Stat label="USDT available" value={`$${(usdt?.free ?? 0).toFixed(2)}`} />
              <Stat label="Open exposure" value={`$${(context.open_exposure_usdt ?? 0).toFixed(2)}`} />
              <Stat label="Margin exposure" value={`$${(context.margin_exposure_usdt ?? 0).toFixed(2)}`} />
              <Stat label="Open positions" value={String(positions.length)} />
            </div>

            {balances.length > 0 && (
              <div className="border border-line rounded-sm overflow-hidden">
                <div className="px-3 py-2 border-b border-line text-xs text-muted flex items-center gap-2"><WalletCards size={13} />Balances included in the reported snapshot</div>
                {balances.slice(0, compact ? 4 : 8).map((balance) => (
                  <div key={balance.asset} className="ledger-row px-3 py-2.5 flex items-center justify-between text-sm">
                    <span className="tnum font-medium">{balance.asset}</span>
                    <div className="text-right">
                      <div className="tnum">{balance.total.toLocaleString(undefined, { maximumFractionDigits: 8 })}</div>
                      <div className="tnum text-xs text-muted">available {balance.free.toLocaleString(undefined, { maximumFractionDigits: 8 })}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <StatusPill tone={ageMinutes !== null && ageMinutes > 10 ? "loss" : "gain"}>
                {ageMinutes !== null && ageMinutes > 10 ? "stale — re-report before sizing a trade" : "fresh"}
              </StatusPill>
              {orders.length > 0 && <StatusPill tone="watch">{orders.length} open orders</StatusPill>}
              {reportedAt && <span>reported {reportedAt.toLocaleTimeString()}</span>}
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}
