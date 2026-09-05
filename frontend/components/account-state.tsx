"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, WalletCards } from "lucide-react";
import { api } from "@/lib/api";
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

export function AccountState({ userId, compact = false }: { userId: string | null; compact?: boolean }) {
  const [raw, setRaw] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const account = await api.getBinanceAccount(userId);
      setRaw(account);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read Binance Agent OS account state.");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { refresh(); }, [refresh]);

  const balances = useMemo(() => collectBalances(raw).filter((b) => b.total !== 0).sort((a, b) => b.total - a.total), [raw]);
  const positions = useMemo(() => collectItems(raw, ["positions", "openPositions"]), [raw]);
  const orders = useMemo(() => collectItems(raw, ["orders", "openOrders"]), [raw]);
  const usdt = balances.find((b) => b.asset === "USDT");
  const portfolioValue = numberValue(raw?.portfolio_value_usdt ?? raw?.portfolioValueUsdt ?? raw?.totalPortfolioValue);

  if (!userId) return null;

  return (
    <Panel
      title="Binance Agentic account"
      action={
        <Button variant="ghost" onClick={refresh} disabled={loading}>
          <span className="flex items-center gap-1.5"><RefreshCw size={13} className={loading ? "animate-spin" : ""} />{loading ? "Refreshing…" : "Refresh"}</span>
        </Button>
      }
    >
      <div className="px-4 py-4 space-y-4">
        {error ? (
          <div className="border border-loss/40 bg-loss/5 rounded-sm p-3 text-xs text-loss">{error}</div>
        ) : !raw && loading ? (
          <EmptyState message="Reading account state from Binance Agent OS…" />
        ) : !raw ? (
          <EmptyState message="No account state available yet. Connect Binance Agent OS first." />
        ) : (
          <>
            <div className={`grid ${compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-4"} gap-4`}>
              <Stat label="Portfolio value" value={portfolioValue !== null ? `$${portfolioValue.toFixed(2)}` : "—"} sub="reported by Agent OS" />
              <Stat label="USDT available" value={`$${(usdt?.free ?? 0).toFixed(2)}`} />
              <Stat label="USDT total" value={`$${(usdt?.total ?? 0).toFixed(2)}`} />
              <Stat label="Assets" value={String(balances.length)} />
              <Stat label="Open positions" value={String(positions.length)} />
            </div>

            {balances.length > 0 && (
              <div className="border border-line rounded-sm overflow-hidden">
                <div className="px-3 py-2 border-b border-line text-xs text-muted flex items-center gap-2"><WalletCards size={13} />Balances returned by Agent OS</div>
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
              <StatusPill tone="gain">live Agent OS state</StatusPill>
              {orders.length > 0 && <StatusPill tone="watch">{orders.length} open orders</StatusPill>}
              {lastUpdated && <span>read {lastUpdated.toLocaleTimeString()}</span>}
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}
