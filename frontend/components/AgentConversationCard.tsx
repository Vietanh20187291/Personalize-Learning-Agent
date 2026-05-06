"use client";

import { FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { Loader2, Send, Sparkles } from "lucide-react";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type AgentConversationCardProps = {
  badge: string;
  title: string;
  subtitle: string;
  accentClassName: string;
  placeholder: string;
  inputValue: string;
  sending?: boolean;
  slowNotice?: boolean;
  messages: ChatMessage[];
  suggestions?: string[];
  onInputChange: (value: string) => void;
  onSend: () => void;
  onSuggestionClick?: (value: string) => void;
};

export default function AgentConversationCard({
  badge,
  title,
  subtitle,
  accentClassName,
  placeholder,
  inputValue,
  sending = false,
  slowNotice = false,
  messages,
  suggestions = [],
  onInputChange,
  onSend,
  onSuggestionClick,
}: AgentConversationCardProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!sending) onSend();
  };

  return (
    <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white/95 shadow-[0_28px_80px_rgba(15,23,42,0.10)] backdrop-blur">
      <div className={`relative overflow-hidden border-b border-white/60 px-5 py-5 ${accentClassName}`}>
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.75),transparent_45%)]" />
        <div className="relative">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/60 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-slate-700">
            <Sparkles size={13} className="text-cyan-700" />
            {badge}
          </div>
          <h2 className="mt-3 text-lg font-black tracking-tight text-slate-950">{title}</h2>
          <p className="mt-1 text-[13px] font-medium leading-6 text-slate-600">{subtitle}</p>
        </div>
      </div>

      {suggestions.length > 0 ? (
        <div className="flex flex-wrap gap-2 border-b border-slate-100 px-5 py-4">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => onSuggestionClick?.(suggestion)}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-100"
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}

      <div className="space-y-4 px-5 py-5">
        <div className="max-h-[26rem] space-y-3 overflow-y-auto pr-1">
          {messages.map((message, index) => (
            <div
              key={`${message.role}_${index}`}
              className={message.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              <div
                className={
                  message.role === "user"
                    ? "max-w-[85%] rounded-[1.35rem] rounded-br-md bg-slate-950 px-4 py-3 text-[13px] font-medium text-white shadow-[0_16px_36px_rgba(15,23,42,0.22)]"
                    : "max-w-[88%] rounded-[1.35rem] rounded-bl-md border border-slate-200 bg-slate-50 px-4 py-3 text-[13px] font-medium text-slate-700"
                }
              >
                <div className="prose prose-sm max-w-none prose-p:my-0 prose-ul:my-2 prose-li:my-0">
                  <ReactMarkdown>{message.content}</ReactMarkdown>
                </div>
              </div>
            </div>
          ))}
          {sending ? (
            <div className="flex justify-start">
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-[13px] font-semibold text-slate-600">
                <Loader2 size={15} className="animate-spin" />
                Agent đang xử lý...
              </div>
            </div>
          ) : null}
        </div>

        {slowNotice ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[11px] font-semibold text-amber-800">
            Hệ thống đang xử lý dữ liệu và gọi AI. Vui lòng đợi thêm một chút.
          </div>
        ) : null}

        <form onSubmit={handleSubmit} className="rounded-[1.6rem] border border-slate-200 bg-white p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.75)]">
          <div className="flex items-end gap-2">
            <textarea
              value={inputValue}
              onChange={(event) => onInputChange(event.target.value)}
              rows={3}
              placeholder={placeholder}
              className="min-h-[96px] flex-1 resize-none rounded-[1.2rem] border-0 bg-transparent px-3 py-3 text-[13px] font-medium text-slate-800 outline-none placeholder:text-slate-400"
            />
            <button
              type="submit"
              disabled={sending || !inputValue.trim()}
              className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-[0_18px_34px_rgba(15,23,42,0.18)] transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Send size={16} />
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
