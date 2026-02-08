import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Loader2, RotateCcw, Send, User } from "lucide-react";

import { historian as historianApi } from "../api.ts";

type HistorianChatRole = "user" | "assistant";

interface HistorianChatMessage {
  id: string;
  role: HistorianChatRole;
  content: string;
  createdAt: number;
  ragRefreshed?: boolean;
  ragCompileStatus?: string | null;
  ragCompileError?: string | null;
}

interface HistorianPanelState {
  threadId: string | null;
  messages: HistorianChatMessage[];
}

interface HistorianPanelProps {
  worldId: string;
}

const HISTORY_LIMIT = 100;

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function isHistorianRole(role: unknown): role is HistorianChatRole {
  return role === "user" || role === "assistant";
}

export default function HistorianPanel({ worldId }: HistorianPanelProps) {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<HistorianChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesViewportRef = useRef<HTMLDivElement | null>(null);
  const storageKey = useMemo(() => `historian_panel:${worldId}`, [worldId]);

  useEffect(() => {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      setThreadId(null);
      setMessages([]);
      setError(null);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as HistorianPanelState;
      const savedMessages = Array.isArray(parsed.messages)
        ? parsed.messages
            .filter((message) => isHistorianRole(message?.role))
            .slice(-HISTORY_LIMIT)
        : [];
      setThreadId(parsed.threadId || null);
      setMessages(savedMessages);
      setError(null);
    } catch {
      setThreadId(null);
      setMessages([]);
      setError(null);
    }
  }, [storageKey]);

  useEffect(() => {
    const state: HistorianPanelState = { threadId, messages };
    window.localStorage.setItem(storageKey, JSON.stringify(state));
  }, [messages, storageKey, threadId]);

  useEffect(() => {
    const viewport = messagesViewportRef.current;
    if (!viewport) return;
    viewport.scrollTo({
      top: viewport.scrollHeight,
      behavior: "auto",
    });
  }, [messages, sending]);

  async function handleSend(): Promise<void> {
    if (sending) return;
    const text = input.trim();
    if (!text) return;

    const userMessage: HistorianChatMessage = {
      id: makeId(),
      role: "user",
      content: text,
      createdAt: Date.now(),
    };

    setMessages((prev) => [...prev.slice(-(HISTORY_LIMIT - 1)), userMessage]);
    setInput("");
    setSending(true);
    setError(null);

    try {
      const response = await historianApi.message(worldId, {
        message: text,
        thread_id: threadId ?? undefined,
      });
      setThreadId(response.thread_id);
      const assistantMessage: HistorianChatMessage = {
        id: makeId(),
        role: "assistant",
        content: response.response,
        createdAt: Date.now(),
        ragRefreshed: response.rag_refreshed,
        ragCompileStatus: response.rag_compile_status,
        ragCompileError: response.rag_compile_error,
      };
      setMessages((prev) => [...prev.slice(-(HISTORY_LIMIT - 1)), assistantMessage]);
    } catch (requestError) {
      const message =
        requestError instanceof Error ? requestError.message : "Failed to contact Historian";
      setError(message);
    } finally {
      setSending(false);
    }
  }

  function handleResetConversation(): void {
    setThreadId(null);
    setMessages([]);
    setError(null);
    window.localStorage.removeItem(storageKey);
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-text-muted">
          Thread: <span className="font-mono text-text">{threadId ? threadId.slice(0, 16) : "(new)"}</span>
        </div>
        <button
          onClick={handleResetConversation}
          disabled={sending}
          className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-xs text-text-muted hover:bg-surface-hover hover:text-text disabled:opacity-50"
        >
          <RotateCcw size={12} />
          New Chat
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-panel">
        <div ref={messagesViewportRef} className="h-full min-h-0 overflow-y-auto p-3">
          <div className="space-y-2">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`rounded-lg border px-3 py-2 text-sm ${
                  message.role === "assistant"
                    ? "border-cyan-900/50 bg-cyan-900/15"
                    : "border-accent/40 bg-accent/15"
                }`}
              >
                <div className="mb-1 flex items-center gap-1 text-xs font-medium text-text-muted">
                  {message.role === "assistant" ? <Bot size={12} /> : <User size={12} />}
                  {message.role === "assistant" ? "Historian" : "You"}
                </div>
                <div className="whitespace-pre-wrap text-text">{message.content}</div>
                {message.role === "assistant" && (
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-muted">
                    {message.ragRefreshed && (
                      <span className="rounded border border-green-800 bg-green-900/20 px-1.5 py-0.5 text-green-400">
                        RAG refreshed
                      </span>
                    )}
                    {message.ragCompileStatus && (
                      <span className="rounded border border-border px-1.5 py-0.5">
                        compile: {message.ragCompileStatus}
                      </span>
                    )}
                    {message.ragCompileError && (
                      <span className="rounded border border-red-800 bg-red-900/20 px-1.5 py-0.5 text-red-400">
                        {message.ragCompileError}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
            {sending && (
              <div className="flex items-center gap-2 text-xs text-text-muted">
                <Loader2 size={12} className="animate-spin" />
                Historian is thinking...
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="shrink-0 space-y-2">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void handleSend();
            }
          }}
          rows={4}
          placeholder="Ask the Historian anything about your world..."
          className="block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-accent focus:outline-none"
        />
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs text-text-muted">
            {error ? <span className="text-red-400">{error}</span> : "Enter to send, Shift+Enter for new line."}
          </div>
          <button
            onClick={() => void handleSend()}
            disabled={sending || !input.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
