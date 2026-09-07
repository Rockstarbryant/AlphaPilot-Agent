"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Circle, Loader2 } from "lucide-react";
import { api, ChatHistoryMessage } from "@/lib/api";
import { Panel, Button, TextInput, StatusPill } from "@/components/ui";
import { useUserId } from "@/lib/use-user";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  toolUsed?: string | null;
  toolData?: Record<string, any> | null;
  aiNarrated?: boolean;
  pending?: boolean;
};

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Ask me about a symbol (\"what do you think about BTC/USDT?\"), Binance Earn APY, or margin trading a symbol. For live balances and executing trades, use the Agent page to connect an AI client to both AlphaPilot and Binance Agent OS.",
};

const TOOL_LABELS: Record<string, string> = {
  analyze_symbol: "looked up live market data + RSI/MACD/momentum",
  get_earn_opportunities: "scanned Binance Simple Earn APY",
  get_margin_analysis: "checked margin eligibility",
  explain_panic: "re-analyzed your open position",
};

function toolLabel(tool: string | null | undefined): string | null {
  if (!tool) return null;
  return TOOL_LABELS[tool] ?? tool;
}

// Mirrors the backend's routing heuristic (app/api/routes/agent_chat.py)
// closely enough to show an honest "what AlphaPilot is doing right now"
// placeholder while the request is in flight — the server's actual answer,
// including its real tool_used, always overwrites this once it arrives.
const KNOWN_BASES = new Set([
  "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
  "MATIC", "POL", "LTC", "TRX", "SHIB", "TON", "NEAR", "ATOM", "UNI", "ICP",
  "ETC", "FIL", "APT", "ARB", "OP", "SUI", "INJ", "RENDER", "RNDR", "PEPE",
  "WIF", "TIA", "SEI", "STX", "HBAR", "VET", "ALGO", "XLM", "AAVE", "MKR",
  "RUNE", "GRT", "SAND", "MANA", "AXS", "FTM", "EGLD", "BONK", "JUP", "PYTH",
]);

function guessPendingLabel(text: string): string {
  const lower = text.toLowerCase();
  if (lower.includes("panic") || lower.includes("should i close") || lower.includes("going against")) {
    return "Re-analyzing your position…";
  }
  if (["earn", "apy", "yield"].some((w) => lower.includes(w))) {
    return "Scanning Binance Simple Earn APY…";
  }
  const pairMatch = text.match(/\b([A-Za-z]{2,10})\s*[/\-]?\s*(USDT|USDC|BUSD|BTC|ETH)\b/i);
  const bareMatch = text.match(/\b([A-Za-z]{2,10})\b/g)?.find((w) => KNOWN_BASES.has(w.toUpperCase()));
  const symbol = pairMatch ? `${pairMatch[1].toUpperCase()}${pairMatch[2].toUpperCase()}` : bareMatch ? `${bareMatch.toUpperCase()}USDT` : null;
  if (symbol && lower.includes("margin")) return `Checking margin eligibility for ${symbol}…`;
  if (symbol) return `Looking up live data + RSI/MACD/momentum for ${symbol}…`;
  return "Thinking…";
}

export default function CopilotPage() {
  const userId = useUserId();
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [status, setStatus] = useState<{ ai_configured: boolean; ai_working: boolean; note: string | null } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getCopilotStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (!userId) return;
    setLoadingHistory(true);
    api
      .getChatHistory(userId)
      .then((history: ChatHistoryMessage[]) => {
        if (history.length === 0) return;
        setMessages(
          history.map((m) => ({
            id: m.id,
            role: m.role,
            text: m.content,
            toolUsed: m.tool_used,
            toolData: m.tool_data,
          }))
        );
      })
      .catch(() => {})
      .finally(() => setLoadingHistory(false));
  }, [userId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || !userId) return;
    const userMsg: ChatMessage = { id: `local-${Date.now()}`, role: "user", text };
    const pendingId = `pending-${Date.now()}`;
    setMessages((m) => [...m, userMsg, { id: pendingId, role: "assistant", text: guessPendingLabel(text), pending: true }]);
    setInput("");
    setSending(true);
    try {
      const result = await api.sendAgentChatMessage(userId, text);
      setMessages((m) =>
        m.map((msg) =>
          msg.id === pendingId
            ? {
                id: result.id,
                role: "assistant",
                text: result.reply,
                toolUsed: result.tool_used,
                toolData: result.data,
                aiNarrated: result.ai_narration_used,
              }
            : msg
        )
      );
    } catch (e) {
      setMessages((m) =>
        m.map((msg) =>
          msg.id === pendingId
            ? { id: `error-${Date.now()}`, role: "assistant", text: e instanceof Error ? e.message : "Something went wrong reaching AlphaPilot's backend." }
            : msg
        )
      );
    } finally {
      setSending(false);
    }
  }

  if (!userId) {
    return <Panel title="Copilot"><div className="px-4 py-6 text-sm text-muted">Sign in to chat with AlphaPilot.</div></Panel>;
  }

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          AlphaPilot Copilot
          {status && (
            <span className="flex items-center gap-1 text-xs font-normal">
              <Circle size={7} className={status.ai_working ? "fill-gain text-gain" : "fill-loss text-loss"} />
              <span className="text-muted">{status.ai_working ? "AI narration online" : "AI narration offline — using templated replies"}</span>
            </span>
          )}
        </span>
      }
    >
      {status && !status.ai_working && status.note && (
        <div className="mx-4 mt-3 border border-gold/40 bg-gold/5 rounded-sm p-2 text-xs text-muted">{status.note}</div>
      )}
      <div className="flex flex-col h-[65vh]">
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {loadingHistory && <div className="text-xs text-muted">Loading conversation…</div>}
          {messages.map((m) => (
            <div key={m.id} className={`max-w-[85%] ${m.role === "user" ? "ml-auto text-right" : ""}`}>
              <div
                className={`inline-flex items-center gap-2 rounded-sm px-3 py-2 text-sm text-left whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-gold/10 text-text border border-gold/30"
                    : m.pending
                    ? "bg-surface-raised border border-line text-muted italic"
                    : "bg-surface-raised border border-line"
                }`}
              >
                {m.pending && <Loader2 size={13} className="animate-spin shrink-0" />}
                {m.text}
              </div>
              {m.role === "assistant" && !m.pending && (m.toolUsed || m.aiNarrated === false) && (
                <div className="flex items-center gap-2 mt-1 text-[10px] text-muted">
                  {m.toolUsed && <StatusPill tone="watch">{toolLabel(m.toolUsed)}</StatusPill>}
                  {m.aiNarrated === false && <span className="italic">templated reply — AI narration unavailable</span>}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <div className="border-t border-line px-4 py-3 flex items-center gap-2">
          <TextInput
            value={input}
            onChange={setInput}
            placeholder="Ask about a symbol, Earn APY, or margin…"
            onKeyDown={(e) => e.key === "Enter" && !sending && send()}
          />
          <Button onClick={send} disabled={sending || !input.trim()}>
            <span className="flex items-center gap-1.5"><Send size={13} />{sending ? "…" : "Send"}</span>
          </Button>
        </div>
      </div>
    </Panel>
  );
}
