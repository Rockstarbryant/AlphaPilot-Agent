"use client";

import { useEffect, useState } from "react";
import { api, RiskPolicy, TradePlan } from "@/lib/api";
import { Panel, Stat, EmptyState, StatusPill, Button } from "@/components/ui";
import { useUserId } from "@/lib/use-user";

type FieldKey = keyof Omit<RiskPolicy, "user_id">;

const FIELDS: { key: FieldKey; label: string; suffix?: string; step?: string }[] = [
  { key: "max_spot_trade_usdt", label: "Max Spot trade", suffix: "USDT", step: "1" },
  { key: "max_spot_allocation_pct", label: "Max Spot allocation", suffix: "%", step: "0.1" },
  { key: "max_margin_trade_usdt", label: "Max Margin trade", suffix: "USDT", step: "1" },
  { key: "max_margin_allocation_pct", label: "Max Margin allocation", suffix: "%", step: "0.1" },
  { key: "max_leverage", label: "Max leverage", suffix: "x", step: "0.5" },
  { key: "max_daily_loss_pct", label: "Max daily loss", suffix: "%", step: "0.1" },
  { key: "max_slippage_bps", label: "Max slippage", suffix: "bps", step: "1" },
  { key: "min_opportunity_score", label: "Min opportunity score", step: "1" },
  { key: "min_recovery_score", label: "Min recovery score", step: "1" },
  { key: "hot_score_threshold", label: "Hot score threshold", step: "1" },
  { key: "gainer_hard_stop_pct", label: "Gainer hard stop", suffix: "%", step: "0.5" },
  { key: "recovery_hard_stop_pct", label: "Recovery hard stop", suffix: "%", step: "0.5" },
  { key: "recovery_take_profit_pct", label: "Recovery take profit", suffix: "%", step: "0.5" },
  { key: "trading_reserve_pct", label: "Trading reserve", suffix: "%", step: "1" },
];

export default function RiskPage() {
  const userId = useUserId();
  const [policy, setPolicy] = useState<RiskPolicy | null>(null);
  const [draft, setDraft] = useState<Partial<RiskPolicy>>({});
  const [rejected, setRejected] = useState<TradePlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;
    setLoading(true);
    Promise.all([
      api.getRiskPolicy(userId),
      api.listTradePlans("risk_rejected"),
    ])
      .then(([p, plans]) => {
        setPolicy(p);
        setDraft({ ...p });
        setRejected(plans);
      })
      .catch((e) => setError(e.message || "Failed to load risk policy"))
      .finally(() => setLoading(false));
  }, [userId]);

  function updateField(key: FieldKey, value: string) {
    const num = parseFloat(value);
    if (Number.isNaN(num)) return;
    setDraft((prev) => ({ ...prev, [key]: num }));
    setMessage(null);
  }

  async function handleSave() {
    if (!userId || !policy) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      // Only send fields that actually changed
      const patch: Partial<RiskPolicy> = {};
      for (const { key } of FIELDS) {
        if (draft[key] !== undefined && draft[key] !== policy[key]) {
          (patch as any)[key] = draft[key];
        }
      }
      if (Object.keys(patch).length === 0) {
        setMessage("No changes to save.");
        setSaving(false);
        return;
      }
      const updated = await api.updateRiskPolicy(userId, patch);
      setPolicy(updated);
      setDraft({ ...updated });
      setMessage("Risk policy updated. New limits apply to the next proposal.");
    } catch (e: any) {
      setError(e.message || "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    if (policy) {
      setDraft({ ...policy });
      setMessage(null);
      setError(null);
    }
  }

  if (loading) {
    return (
      <div className="text-sm text-muted px-1 py-8">Loading risk policy…</div>
    );
  }

  return (
    <div className="space-y-4">
      <Panel
        title="Risk policy (editable)"
        action={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={handleReset} disabled={saving}>
              Reset
            </Button>
            <Button onClick={handleSave} disabled={saving || !userId}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        }
      >
        {error && (
          <div className="px-4 py-2 text-sm text-loss border-b border-line">{error}</div>
        )}
        {message && (
          <div className="px-4 py-2 text-sm text-gain border-b border-line">{message}</div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
          {FIELDS.map(({ key, label, suffix, step }) => (
            <label key={key} className="block">
              <div className="text-xs text-muted mb-1">{label}</div>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  step={step || "any"}
                  className="w-full bg-surface-raised border border-line rounded-sm px-3 py-2 text-sm tnum text-text focus:outline-none focus:border-gold"
                  value={draft[key] ?? ""}
                  onChange={(e) => updateField(key, e.target.value)}
                />
                {suffix && <span className="text-xs text-muted shrink-0">{suffix}</span>}
              </div>
            </label>
          ))}
        </div>

        <div className="px-4 pb-4 text-xs text-muted">
          These values are enforced by the deterministic risk engine. The AI layer cannot override them.
          After saving, the next trade proposal will use the new limits.
        </div>
      </Panel>

      {/* Quick read-only summary */}
      {policy && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <Panel className="p-4">
            <Stat label="Max Margin allocation" value={`${policy.max_margin_allocation_pct}%`} />
          </Panel>
          <Panel className="p-4">
            <Stat label="Max leverage" value={`${policy.max_leverage}x`} />
          </Panel>
          <Panel className="p-4">
            <Stat label="Max daily loss" value={`${policy.max_daily_loss_pct}%`} tone="loss" />
          </Panel>
        </div>
      )}

      <Panel title="Recently risk-rejected proposals">
        {rejected.length === 0 ? (
          <EmptyState message="No proposals have been rejected by the risk engine." />
        ) : (
          <div>
            {rejected.map((p) => (
              <div key={p.id} className="ledger-row px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="tnum font-medium">{p.symbol}</span>
                  <StatusPill tone="loss">risk rejected</StatusPill>
                </div>
                <div className="mt-1 space-y-0.5">
                  {Object.entries(p.risk_check_notes || {}).map(([check, note]) => (
                    <div key={check} className="text-xs text-muted">
                      <span className="text-loss">{check.replace(/_/g, " ")}:</span> {note}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}