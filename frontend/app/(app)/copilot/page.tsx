"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Circle } from "lucide-react";
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
};

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Ask me about a symbol (\"what do you think about BTC/USDT?\"), Binance Earn APY, or margin trading a symbol. For live balances and executing trades, use the Agent page to connect an AI client to both AlphaPilot and Binance Agent OS.",
};

function toolLabel(tool: string | null | undefined): string | null {
  if (!tool) return null;
  const labels: Record<string, string> = {
    analyze_symbol: "looked up live market data + RSI/MACD/momentum",
    get_earn_opportunities: "scanned Binance Simple Earn APY",
    get_margin_analysis: "checked margin eligibility",
    explain_panic: "re-analyzed your open position",
  };
  return labels[tool] ?? tool;
}

export default function CopilotPage() {
  const userId = useUserId();
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [status, setStatus] = useState<{ ai_configured: boolean; note: string | null } | null>(null);
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
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setSending(true);
    try {
      const result = await api.sendAgentChatMessage(userId, text);
      setMessages((m) => [
        ...m,
        {
          id: result.id,
          role: "assistant",
          text: result.reply,
          toolUsed: result.tool_used,
          toolData: result.data,
          aiNarrated: result.ai_narration_used,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { id: `error-${Date.now()}`, role: "assistant", text: e instanceof Error ? e.message : "Something went wrong reaching AlphaPilot's backend." },
      ]);
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
              <Circle size={7} className={status.ai_configured ? "fill-gain text-gain" : "fill-loss text-loss"} />
              <span className="text-muted">{status.ai_configured ? "AI narration online" : "AI narration offline — using templated replies"}</span>
            </span>
          )}
        </span>
      }
    >
      {status && !status.ai_configured && status.note && (
        <div className="mx-4 mt-3 border border-gold/40 bg-gold/5 rounded-sm p-2 text-xs text-muted">{status.note}</div>
      )}
      <div className="flex flex-col h-[65vh]">
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {loadingHistory && <div className="text-xs text-muted">Loading conversation…</div>}
          {messages.map((m) => (
            <div key={m.id} className={`max-w-[85%] ${m.role === "user" ? "ml-auto text-right" : ""}`}>
              <div
                className={`inline-block rounded-sm px-3 py-2 text-sm text-left whitespace-pre-wrap ${
                  m.role === "user" ? "bg-gold/10 text-text border border-gold/30" : "bg-surface-raised border border-line"
                }`}
              >
                {m.text}
              </div>
              {m.role === "assistant" && (m.toolUsed || m.aiNarrated === false) && (
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
