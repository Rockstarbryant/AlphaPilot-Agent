"use client";

import { useEffect, useState } from "react";
import { Circle, Octagon } from "lucide-react";
import { api, AgentConfig, MarketSession } from "@/lib/api";
import { StatusPill } from "@/components/ui";
import { NotificationBell } from "@/components/notification-bell";
import { useUserId } from "@/lib/use-user";

const REGIME_TONE: Record<string, "gain" | "loss" | "watch" | "gold" | "muted"> = {
  BULLISH: "gain",
  BEARISH: "loss",
  NEUTRAL: "watch",
  HIGH_VOLATILITY: "gold",
  RISK_OFF: "loss",
  UNKNOWN: "muted",
};

export function TopBar() {
  const userId = useUserId();
  const [session, setSession] = useState<MarketSession | null>(null);
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listSessions().then((s) => setSession(s[0] ?? null)).catch(() => {});
    if (userId) api.getAgentConfig(userId).then(setConfig).catch(() => {});
  }, [userId]);

  async function handleEmergencyStop() {
    if (!userId) return;
    setBusy(true);
    try {
      await api.emergencyStop(userId, "Manual stop from dashboard");
      const updated = await api.getAgentConfig(userId);
      setConfig(updated);
    } finally {
      setBusy(false);
    }
  }

  async function handleResume() {
    if (!userId) return;
    setBusy(true);
    try {
      const updated = await api.resumeAgent(userId);
      setConfig(updated);
    } finally {
      setBusy(false);
    }
  }

  return (
    <header className="flex items-center justify-between border-b border-line bg-surface px-4 py-3">
      <div className="flex items-center gap-4 text-xs">
        {session ? (
          <>
            <span className="text-muted">
              Session{" "}
              <span className="tnum text-text">
                {new Date(session.session_date).toLocaleDateString(undefined, {
                  month: "short", day: "numeric",
                })}
              </span>
            </span>
            {session.market_regime && (
              <StatusPill tone={REGIME_TONE[session.market_regime] ?? "muted"}>
                {session.market_regime}
              </StatusPill>
            )}
          </>
        ) : (
          <span className="text-muted">No market session yet</span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <NotificationBell />
        {config?.emergency_halted ? (
          <>
            <StatusPill tone="loss">
              <Octagon size={12} /> HALTED
            </StatusPill>
            <button
              onClick={handleResume}
              disabled={busy}
              className="text-xs border border-line px-2.5 py-1 rounded-sm text-muted hover:text-text disabled:opacity-40"
            >
              Resume agent
            </button>
          </>
        ) : (
          <>
            <StatusPill tone="gain">
              <Circle size={8} fill="currentColor" /> {config?.trading_mode?.replace("_", " ") ?? "—"}
            </StatusPill>
            <button
              onClick={handleEmergencyStop}
              disabled={busy || !userId}
              className="text-xs bg-loss text-white px-3 py-1.5 rounded-sm hover:bg-loss/80 disabled:opacity-40"
            >
              Emergency Stop
            </button>
          </>
        )}
      </div>
    </header>
  );
}
