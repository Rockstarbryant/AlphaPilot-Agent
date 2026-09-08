const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.localStorage.getItem("alphapilot_token");
  return token ? { Authorization: "Bearer " + token } : {};
}

export class SessionExpiredError extends Error {
  constructor() {
    super("Your session has expired — please log in again.");
    this.name = "SessionExpiredError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_URL + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  if (res.status === 401) {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("alphapilot_token");
      window.localStorage.removeItem("alphapilot_user_id");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login?expired=1";
      }
    }
    throw new SessionExpiredError();
  }
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      detail = parsed.detail ?? body;
    } catch {
      // body wasn't JSON
    }
    throw new Error(typeof detail === "string" ? detail : res.status + " " + res.statusText);
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
    request<{ session_id: string; gainers_scanned: number }>(
      "/api/sessions/run?user_id=" + encodeURIComponent(userId),
      { method: "POST" }
    ),

  listSessions: () => request<MarketSession[]>("/api/sessions/"),

  listCandidates: (params?: {
    sessionId?: string;
    marketType?: "spot" | "futures";
    status?: string;
    strategy?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.sessionId) qs.set("session_id", params.sessionId);
    if (params?.marketType) qs.set("market_type", params.marketType);
    if (params?.status) qs.set("status", params.status);
    if (params?.strategy) qs.set("strategy", params.strategy);
    const query = qs.toString();
    const path = query ? "/api/candidates/?" + query : "/api/candidates/";
    return request<MarketCandidate[]>(path);
  },

  explainCandidate: (candidateId: string) =>
    request<{ candidate_id: string; explanation: string; ai_narrated: boolean }>(
      "/api/candidates/" + candidateId + "/explain",
      { method: "POST" }
    ),

  listTradePlans: (status?: string) => {
    const path = status
      ? "/api/trade-plans/?status=" + encodeURIComponent(status)
      : "/api/trade-plans/";
    return request<TradePlan[]>(path);
  },

  getApprovalBrief: (planId: string) =>
    request<{ plan_id: string; brief: string }>(
      "/api/trade-plans/" + planId + "/approval-brief"
    ),

  confirmExecution: (
    planId: string,
    binanceOrderId: string,
    fillPrice?: number,
    filledQuantity?: number
  ) =>
    request("/api/trade-plans/" + planId + "/confirm-execution", {
      method: "POST",
      body: JSON.stringify({
        binance_order_id: binanceOrderId,
        fill_price: fillPrice,
        filled_quantity: filledQuantity,
      }),
    }),

  listPositions: () => request<Position[]>("/api/positions/"),

  runPositionMonitor: () =>
    request<{ exit_signals_generated: number }>("/api/positions/monitor/run", {
      method: "POST",
    }),

  listExitSignals: (acknowledged?: boolean) => {
    const path =
      acknowledged !== undefined
        ? "/api/positions/exit-signals?acknowledged=" + String(acknowledged)
        : "/api/positions/exit-signals";
    return request<ExitSignal[]>(path);
  },

  confirmExitExecution: (id: string, binanceOrderId: string, fillPrice?: number) =>
    request("/api/positions/exit-signals/" + id + "/confirm-execution", {
      method: "POST",
      body: JSON.stringify({
        binance_order_id: binanceOrderId,
        fill_price: fillPrice,
      }),
    }),

  acknowledgeExitSignal: (id: string) =>
    request("/api/positions/exit-signals/" + id + "/acknowledge", {
      method: "POST",
    }),

  getAgentConfig: (userId: string) =>
    request<AgentConfig>("/api/agent/" + userId),

  setTradingMode: (userId: string, mode: string) =>
    request<AgentConfig>("/api/agent/" + userId + "/trading-mode", {
      method: "POST",
      body: JSON.stringify({ trading_mode: mode }),
    }),

  emergencyStop: (userId: string, reason: string) =>
    request<{ halted: boolean; note: string }>(
      "/api/agent/" + userId + "/emergency-stop",
      {
        method: "POST",
        body: JSON.stringify({ reason }),
      }
    ),

  resumeAgent: (userId: string) =>
    request<AgentConfig>("/api/agent/" + userId + "/resume", {
      method: "POST",
    }),

  submitAccountContext: (userId: string, payload: AccountContextPayload) =>
    request<{ ok: boolean; reported_at: string; portfolio_value_usdt: number }>(
      "/api/binance/account-context/" + userId,
      { method: "POST", body: JSON.stringify(payload) }
    ),

  getAccountContext: (userId: string) =>
    request<AccountContext>("/api/binance/account-context/" + userId),

  analyzeSymbol: (symbol: string, interval = "1h") =>
    request<CoinAnalysis>(
      "/api/market/analyze/" + symbol + "?interval=" + encodeURIComponent(interval)
    ),

  getEarnOpportunities: () => request<EarnScanResult>("/api/market/earn"),

  getMarginAnalysis: (symbol: string) =>
    request<MarginAnalysis>("/api/market/margin/" + symbol),

  createTradeProposal: (
    userId: string,
    payload: {
      symbol: string;
      intent: "long" | "short" | "spot_hold";
      requested_size_usdt?: number;
      requested_leverage?: number;
    }
  ) =>
    request<TradeProposalResult>("/api/market/proposal/" + userId, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getPanicExplanation: (positionId: string, question = "") =>
    request<PanicExplanation>(
      "/api/market/panic/" +
        positionId +
        "?question=" +
        encodeURIComponent(question)
    ),

  sendAgentChatMessage: (userId: string, message: string, positionId?: string) =>
    request<AgentChatResponse>("/api/agent-chat/" + userId + "/message", {
      method: "POST",
      body: JSON.stringify({ message, position_id: positionId }),
    }),

  getChatHistory: (userId: string) =>
    request<ChatHistoryMessage[]>("/api/agent-chat/" + userId + "/history"),

  getCopilotStatus: () =>
    request<{
      ai_provider: string;
      ai_configured: boolean;
      ai_working: boolean;
      model?: string;
      note: string | null;
    }>("/api/agent-chat/status"),

  listNotifications: (userId: string, unreadOnly = false) =>
    request<Notification[]>(
      "/api/notifications/" + userId + "?unread_only=" + String(unreadOnly)
    ),

  markNotificationRead: (id: string) =>
    request("/api/notifications/" + id + "/read", { method: "POST" }),

  markAllNotificationsRead: (userId: string) =>
    request("/api/notifications/" + userId + "/read-all", { method: "POST" }),

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

  getRiskPolicy: (userId: string) =>
    request<RiskPolicy>("/api/risk/" + userId),

  updateRiskPolicy: (
    userId: string,
    patch: Partial<Omit<RiskPolicy, "user_id">>
  ) =>
    request<RiskPolicy>("/api/risk/" + userId, {
      method: "PATCH",
      body: JSON.stringify(patch),
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
  market_type: "spot" | "futures";
  price: number;
  daily_change_pct: number;
  quote_volume_24h: number;
  spread_bps: number;
  opportunity_score: number | null;
  risk_score: number | null;
  score_breakdown: Record<string, number>;
  reason: string | null;
  ai_explanation: string | null;
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

export interface AccountContextPayload {
  portfolio_value_usdt: number;
  open_exposure_usdt?: number;
  margin_exposure_usdt?: number;
  realized_daily_loss_pct?: number;
  raw_snapshot?: Record<string, unknown>;
}

export interface AccountContext {
  status: string;
  reported_at?: string;
  portfolio_value_usdt?: number;
  open_exposure_usdt?: number;
  margin_exposure_usdt?: number;
  realized_daily_loss_pct?: number;
  raw_snapshot?: Record<string, unknown>;
}

export interface CoinAnalysis {
  symbol: string;
  interval: string;
  price: number;
  price_change_pct_24h: number;
  rsi: { value: number | null; period: number; signal: string };
  macd: {
    macd: number | null;
    signal_line: number | null;
    histogram: number | null;
    crossover: string;
  };
  momentum: { roc_pct: number | null; direction: string };
  moving_averages: {
    sma_20: number | null;
    sma_50: number | null;
    ema_20: number | null;
    ema_50: number | null;
    price_vs_sma20_pct: number | null;
    golden_cross: boolean;
    death_cross: boolean;
    trend: string;
  };
  bollinger: {
    upper: number | null;
    middle: number | null;
    lower: number | null;
    bandwidth_pct: number | null;
    percent_b: number | null;
    signal: string;
  };
  support_resistance: {
    support_levels: number[];
    resistance_levels: number[];
    nearest_support: number | null;
    nearest_resistance: number | null;
    distance_to_support_pct: number | null;
    distance_to_resistance_pct: number | null;
  };
  structure: {
    sequence: string;
    last_swing_high: number | null;
    last_swing_low: number | null;
    break_of_structure: string | null;
    change_of_character: string | null;
    notes: string;
  };
  vwap: {
    vwap: number | null;
    price_vs_vwap_pct: number | null;
    signal: string;
  };
  volume_profile: {
    point_of_control: number | null;
    value_area_low: number | null;
    value_area_high: number | null;
    price_vs_poc_pct: number | null;
    signal: string;
  };
  order_book: {
    spread_bps: number | null;
    bid_depth_usdt: number;
    ask_depth_usdt: number;
    imbalance_ratio: number | null;
    imbalance_signal: string;
    large_bid_walls: { price: number; qty: number; usdt_value: number }[];
    large_ask_walls: { price: number; qty: number; usdt_value: number }[];
    notes: string;
  };
  derivatives: {
    available: boolean;
    funding_rate_pct: number | null;
    funding_rate_annualized_pct: number | null;
    funding_trend: string;
    open_interest: number | null;
    basis_pct: number | null;
    positioning_signal: string;
    liquidation_data: string;
    notes: string;
  };
  onchain: {
    applicable: boolean;
    chain: string | null;
    tvl_usd: number | null;
    tvl_change_7d_pct: number | null;
    signal: string;
    whale_flow_data: string;
    notes: string;
  };
  fear_greed: {
    value: number | null;
    classification: string;
    signal: string;
    unavailable_reason: string | null;
  };
  news_sentiment: {
    available: boolean;
    headline_count: number;
    bullish_count: number;
    bearish_count: number;
    top_headlines: string[];
    unavailable_reason: string | null;
  };
  cross_market: {
    btc_dominance_pct: number | null;
    total_market_cap_usd: number | null;
    eth_btc_ratio: number | null;
    eth_btc_signal: string;
    macro_available: boolean;
    dxy_note: string | null;
    notes: string;
  };
  market_regime: string;
  regime_notes: string;
  bias: "LONG" | "SHORT" | "WAIT";
  confidence: number;
  composite_score: number;
  categories_used: string[];
  categories_missing: string[];
  coverage_pct: number;
  model_type: string;
  rationale: string[];
  spot_guidance: string;
  derivatives_guidance: string;
  data_quality: "full" | "partial" | "insufficient";
  klines_fetched: number;
  generated_at: string;
}

export interface EarnOpportunity {
  asset: string;
  product_id: string;
  latest_apy_pct: number;
  min_purchase_amount: number;
  is_hot: boolean;
}

export interface EarnScanResult {
  opportunities: EarnOpportunity[];
  unavailable_reason: string | null;
}

export interface MarginAnalysis {
  symbol: string;
  eligible: boolean;
  reasons: string[];
  bias: string;
  confidence: number;
  suggested_leverage: number;
  max_leverage_allowed: number;
  daily_interest_rate_pct: number;
  interest_rate_is_estimate: boolean;
  est_daily_cost_pct_of_position: number;
  notes: string;
  data_quality: "full" | "partial" | "insufficient";
}

export interface TradeProposalResult {
  ok: boolean;
  error?: string;
  plan_id?: string;
  symbol?: string;
  intent?: string;
  side?: string;
  is_margin?: boolean;
  suggested_margin_usdt?: number;
  suggested_leverage?: number | null;
  reference_entry_price?: number;
  stop_loss_pct?: number;
  take_profit_targets_pct?: Record<string, number>;
  risk_check_passed?: boolean;
  risk_check_notes?: Record<string, string>;
  bias?: string;
  confidence?: number;
  rationale?: string[];
  next_step?: string;
}

export interface PanicExplanation {
  position_id: string;
  symbol: string;
  entry_price: number;
  current_price: number;
  pnl_pct: number;
  stop_loss_pct: number;
  distance_to_stop_pct: number;
  current_bias: string;
  current_confidence: number;
  current_rationale: string[];
  thesis_still_valid: boolean;
  recommendation: "CLOSE" | "CONSIDER_CLOSING" | "HOLD";
  headline: string;
  note: string;
}

export interface AgentChatResponse {
  id: string;
  reply: string;
  tool_used: string | null;
  data: Record<string, any> | null;
  ai_narration_used: boolean;
}

export interface ChatHistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_used: string | null;
  tool_data: Record<string, any> | null;
  created_at: string;
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

export interface RiskPolicy {
  user_id: string;
  max_spot_trade_usdt: number;
  max_spot_allocation_pct: number;
  max_margin_trade_usdt: number;
  max_margin_allocation_pct: number;
  max_leverage: number;
  max_daily_loss_pct: number;
  max_slippage_bps: number;
  min_opportunity_score: number;
  min_recovery_score: number;
  hot_score_threshold: number;
  gainer_hard_stop_pct: number;
  recovery_hard_stop_pct: number;
  recovery_take_profit_pct: number;
  trading_reserve_pct: number;
}