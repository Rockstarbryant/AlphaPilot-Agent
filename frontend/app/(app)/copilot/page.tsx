"use client";

import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { api } from "@/lib/api";
import { Panel, Button, TextInput } from "@/components/ui";
import { useUserId } from "@/lib/use-user";

type ChatMessage = { role: "user" | "assistant"; text: string; toolUsed?: string | null };

// Standalone AlphaPilot chat — talks directly to an OpenRouter free model
// (see OPENROUTER_MODEL in .env.example), independent of any MCP client.
// It can give market analysis, Earn/margin scans, and panic explanations
// for positions AlphaPilot already knows about, but it cannot read live
// Binance balances or place trades — that needs the dual-MCP setup on the
// Agent page (Claude/ChatGPT connected to both Binance Agent OS and
// AlphaPilot's MCP server).
export default function CopilotPage() {
  const userId = useUserId();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "Ask me about a symbol (\"what do you think about BTC/USDT?\"), Binance Earn APY, or margin trading a symbol. For live balances and executing trades, use the Agent page to connect an AI client to both AlphaPilot and Binance Agent OS.",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || !userId) return;
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const result = await api.sendAgentChatMessage(userId, text);
      setMessages((m) => [...m, { role: "assistant", text: result.reply, toolUsed: result.tool_used }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: e instanceof Error ? e.message : "Something went wrong." }]);
    } finally {
      setSending(false);
    }
  }

  if (!userId) {
    return <Panel title="Copilot"><div className="px-4 py-6 text-sm text-muted">Sign in to chat with AlphaPilot.</div></Panel>;
  }

  return (
    <Panel title="AlphaPilot Copilot — standalone chat">
      <div className="flex flex-col h-[65vh]">
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`max-w-[85%] ${m.role === "user" ? "ml-auto text-right" : ""}`}>
              <div
                className={`inline-block rounded-sm px-3 py-2 text-sm text-left whitespace-pre-wrap ${
                  m.role === "user" ? "bg-gold/10 text-text border border-gold/30" : "bg-surface-raised border border-line"
                }`}
              >
                {m.text}
              </div>
              {m.toolUsed && <div className="text-[10px] text-muted mt-1">via {m.toolUsed}</div>}
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
