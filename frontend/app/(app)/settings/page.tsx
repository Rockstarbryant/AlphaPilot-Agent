"use client";

import { useState } from "react";
import { api, CapitalEvaluation } from "@/lib/api";
import { Panel, Button, EmptyState } from "@/components/ui";
import { useUserId, clearSession } from "@/lib/use-user";
import { useRouter } from "next/navigation";

export default function SettingsPage() {
  const userId = useUserId();
  const router = useRouter();
  const [totalCapital, setTotalCapital] = useState("1000");
  const [openValue, setOpenValue] = useState("0");
  const [pendingValue, setPendingValue] = useState("0");
  const [result, setResult] = useState<CapitalEvaluation | null>(null);

  async function evaluate() {
    if (!userId) return;
    const r = await api.evaluateCapital({
      user_id: userId,
      total_capital_usdt: parseFloat(totalCapital) || 0,
      open_positions_value_usdt: parseFloat(openValue) || 0,
      pending_proposals_value_usdt: parseFloat(pendingValue) || 0,
    });
    setResult(r);
  }

  function logout() {
    clearSession();
    router.replace("/login");
  }

  return (
    <div className="space-y-4">
      <Panel title="Capital Optimizer">
        <div className="px-4 py-4 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-muted mb-1">Total capital ($)</label>
              <input
                value={totalCapital}
                onChange={(e) => setTotalCapital(e.target.value)}
                className="w-full bg-surface-raised border border-line rounded-sm px-3 py-1.5 text-sm outline-none focus:border-gold tnum"
              />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">In open positions ($)</label>
              <input
                value={openValue}
                onChange={(e) => setOpenValue(e.target.value)}
                className="w-full bg-surface-raised border border-line rounded-sm px-3 py-1.5 text-sm outline-none focus:border-gold tnum"
              />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">In pending proposals ($)</label>
              <input
                value={pendingValue}
                onChange={(e) => setPendingValue(e.target.value)}
                className="w-full bg-surface-raised border border-line rounded-sm px-3 py-1.5 text-sm outline-none focus:border-gold tnum"
              />
            </div>
          </div>
          <Button onClick={evaluate}>Evaluate idle capital</Button>

          {result && (
            <div className="border border-line rounded-sm p-3 text-sm space-y-1 bg-surface-raised">
              <div>
                Idle capital: <span className="tnum text-gold">${result.idle_capital_usdt.toFixed(2)}</span>
              </div>
              <div className="text-xs text-muted">{result.reason}</div>
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Account">
        <div className="px-4 py-3">
          <Button variant="ghost" onClick={logout}>
            Log out
          </Button>
        </div>
      </Panel>
    </div>
  );
}
