"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api, EarnScanResult } from "@/lib/api";
import { Panel, StatusPill, Button, EmptyState } from "@/components/ui";

export default function EarnPage() {
  const [result, setResult] = useState<EarnScanResult | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setResult(await api.getEarnOpportunities());
    } catch {
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-4">
      <Panel
        title="Simple Earn — flexible product APY scan"
        action={
          <Button variant="ghost" onClick={load} disabled={loading}>
            <span className="flex items-center gap-1.5"><RefreshCw size={13} className={loading ? "animate-spin" : ""} />{loading ? "Scanning…" : "Rescan"}</span>
          </Button>
        }
      >
        <div className="px-4 py-3 text-xs text-muted border-b border-line">
          Read-only. AlphaPilot never subscribes or redeems Earn products automatically — this only
          surfaces where idle capital could go; use Binance directly (or your connected AI client via
          Binance Agent OS) to act on it.
        </div>
        {loading ? (
          <EmptyState message="Scanning Binance Simple Earn…" />
        ) : !result || result.opportunities.length === 0 ? (
          <EmptyState message={result?.unavailable_reason ?? "No opportunities found."} />
        ) : (
          <div>
            {result.opportunities.map((o) => (
              <div key={o.product_id} className="ledger-row px-4 py-2.5 flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span className="tnum font-medium">{o.asset}</span>
                  {o.is_hot && <StatusPill tone="gold">hot</StatusPill>}
                </div>
                <div className="flex items-center gap-4">
                  <span className="tnum text-gain">{o.latest_apy_pct.toFixed(2)}% APY</span>
                  <span className="tnum text-muted text-xs">min {o.min_purchase_amount}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
