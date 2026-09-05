const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("alphapilot_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; env: string }>("/api/health"),

  register: (email: string, password: string) =>
    request<{ access_token: string; user_id: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; user_id: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  runMarketScan: (userId: string) =>
    request<{ session_id: string; gainers_scanned: number }>(`/api/sessions/run?user_id=${userId}`, {
      method: "POST",
    }),
  listSessions: () => request<MarketSession[]>("/api/sessions/"),

  listCandidates: (sessionId?: string) =>
    request<MarketCandidate[]>(`/api/candidates/${sessionId ? `?session_id=${sessionId}` : ""}`),

  listTradePlans: (status?: string) =>
    request<TradePlan[]>(`/api/trade-plans/${status ? `?status=${status}` : ""}`),
  getApprovalBrief: (planId: string) =>
    request<{ plan_id: string; brief: string }>(`/api/trade-plans/${planId}/approval-brief`),
  executeTradePlan: (planId: string) =>
    request<any>(`/api/trade-plans/${planId}/execute`, { method: "POST" }),
  confirmExecution: (planId: string, binanceOrderId: string) =>
    request(`/api/trade-plans/${planId}/confirm-execution`, {
      method: "POST",
      body: JSON.stringify({ binance_order_id: binanceOrderId }),
    }),

  listPositions: () => request<Position[]>("/api/positions/"),
  runPositionMonitor: () =>
    request<{ exit_signals_generated: number }>("/api/positions/monitor/run", { method: "POST" }),
  listExitSignals: (acknowledged?: boolean) =>
    request<ExitSignal[]>(
      `/api/positions/exit-signals${acknowledged !== undefined ? `?acknowledged=${acknowledged}` : ""}`
    ),
  executeExitSignal: (id: string) =>
    request<any>(`/api/positions/exit-signals/${id}/execute`, { method: "POST" }),
  acknowledgeExitSignal: (id: string) =>
    request(`/api/positions/exit-signals/${id}/acknowledge`, { method: "POST" }),

  getAgentConfig: (userId: string) => request<AgentConfig>(`/api/agent/${userId}`),
  setTradingMode: (userId: string, mode: string) =>
    request<AgentConfig>(`/api/agent/${userId}/trading-mode`, {
      method: "POST",
      body: JSON.stringify({ trading_mode: mode }),
    }),
  emergencyStop: (userId: string, reason: string) =>
    request<{ halted: boolean; note: string }>(`/api/agent/${userId}/emergency-stop`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  resumeAgent: (userId: string) =>
    request<AgentConfig>(`/api/agent/${userId}/resume`, { method: "POST" }),

  getBinanceConnection: (userId: string) =>
    request<BinanceConnection>(`/api/binance/connection/${userId}`),
  connectBinance: (userId: string) =>
    request<{ authorization_url: string }>(`/api/binance/connect/${userId}`, { method: "POST" }),
  getBinanceCapabilities: (userId: string) =>
    request<{ tools: any[] }>(`/api/binance/capabilities/${userId}`),
  getBinanceTicker: (userId: string, symbol: string) =>
    request<any>(`/api/binance/ticker/${userId}/${encodeURIComponent(symbol)}`),
  getBinanceAccount: (userId: string) =>
    request<any>(`/api/binance/account/${userId}`),
  syncBinanceAccount: (userId: string) =>
    request<{ portfolio_value_usdt: number; raw: any }>(`/api/binance/account/${userId}/sync`, { method: "POST" }),

  listNotifications: (userId: string, unreadOnly = false) =>
    request<Notification[]>(`/api/notifications/${userId}?unread_only=${unreadOnly}`),
  markNotificationRead: (id: string) =>
    request(`/api/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: (userId: string) =>
    request(`/api/notifications/${userId}/read-all`, { method: "POST" }),

  evaluateCapital: (payload: {
    user_id: string;
    total_capital_usdt: number;
    open_positions_value_usdt?: number;
    pending_proposals_value_usdt?: number;
  }) =>
    request<CapitalEvaluation>("/api/capital/evaluate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export interface MarketSession {
  id: string;
  session_date: string;
  started_at: string;
  completed_at: string | null;
  market_regime: string | null;
  gainers_scanned: number;
  losers_scanned: number;
  hot_candidates_found: number;
  status: string;
}

export interface MarketCandidate {
  id: string;
  session_id: string;
  symbol: string;
  strategy: string;
  status: string;
  price: number;
  daily_change_pct: number;
  quote_volume_24h: number;
  spread_bps: number;
  opportunity_score: number | null;
  risk_score: number | null;
  score_breakdown: Record<string, number>;
  reason: string | null;
  data_source_timestamp: string;
  created_at: string;
}

export interface TradePlan {
  id: string;
  candidate_id: string;
  user_id: string;
  symbol: string;
  strategy: string;
  side: string;
  entry_price: number;
  position_size_usdt: number;
  estimated_slippage_bps: number;
  stop_loss_pct: number;
  profit_targets_pct: Record<string, number>;
  opportunity_score: number;
  risk_score: number;
  reason: string;
  market_conditions: Record<string, number>;
  risk_check_passed: boolean;
  risk_check_notes: Record<string, string>;
  status: string;
  binance_order_id: string | null;
  created_at: string;
}

export interface Position {
  id: string;
  trade_plan_id: string;
  symbol: string;
  strategy: string;
  entry_price: number;
  quantity: number;
  remaining_fraction: number;
  stop_loss_pct: number;
  profit_targets_pct: Record<string, number>;
  targets_hit: Record<string, boolean>;
  status: string;
  opened_at: string;
  last_checked_price: number | null;
}

export interface ExitSignal {
  id: string;
  position_id: string;
  triggered_at: string;
  reason: string;
  detail: string;
  sell_fraction: number;
  price_at_trigger: number;
  acknowledged: boolean;
  execution_status: string;
  binance_order_id: string | null;
  target_pct: number | null;
}

export interface BinanceConnection {
  status: string;
  authorized: boolean;
  connected_at: string | null;
  last_error: string | null;
  token_expires_at: number | null;
}

export interface AgentConfig {
  id: string;
  user_id: string;
  trading_mode: string;
  emergency_halted: boolean;
  halted_reason: string | null;
}

export interface CapitalEvaluation {
  idle_capital_usdt: number;
  trading_reserve_usdt: number;
  emergency_reserve_usdt: number;
  recommended_earn_usdt: number;
  reason: string;
}

export interface Notification {
  id: string;
  user_id: string;
  created_at: string;
  kind: string;
  title: string;
  detail: string;
  read: boolean;
}
