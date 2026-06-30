"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import {
  Lightbulb,
  Loader2,
  Minimize2,
  Send,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "../services/api";

/* ───────── types ───────── */

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface EnrolledClassSummary {
  id?: number | null;
  subject?: string;
}

export interface StudentOrbitAgentProps {
  userId: number | null;
  classId?: number | null;
  documentId?: number | null;
  sourceFile?: string;
  selectedSubject?: string;
  enrolledClasses?: EnrolledClassSummary[];
  /** Hide on non-student pages (teacher, admin, test) */
  hidden?: boolean;
  /** Callback khi plan thay đổi (để trang cha refresh cột Planning) */
  onPlanChanged?: () => void;
}

/* ───────── suggestion map per route ───────── */

const SUGGESTIONS_BY_ROUTE: Record<string, string[]> = {
  adaptive: [
    "Tóm tắt tài liệu này",
    "Các ý chính trong tài liệu này là gì?",
    "Giải thích nội dung tài liệu này dễ hiểu hơn",
  ],
  planning: [
    "Đẩy các tài liệu môn Lập trình hướng đối tượng lên học trước",
    "Cho các tài liệu môn Cơ sở dữ liệu học sớm hơn",
    "Sắp xếp lại kế hoạch để ưu tiên các tài liệu sắp thi",
  ],
  "my-learning": [
    "Đẩy các tài liệu môn Lập trình hướng đối tượng lên học trước",
    "Thêm 2 tài liệu vào lịch học tuần này",
    "Ưu tiên các tài liệu chưa qua lên đầu lịch học",
  ],
  evaluation: [
    "Thành tích học tập của tôi hiện nay thế nào?",
    "Môn nào tôi đang yếu nhất?",
    "Tài liệu nào tôi nên ôn tập lại trước kỳ thi?",
  ],
  _default: [
    "Hôm nay, tôi nên học phần nào?",
    "Thành tích học của tôi thế nào?",
    "Mở cho tôi tài liệu môn Lập trình hướng đối tượng",
  ],
};

/* ───────── route detection helpers ───────── */

function getRouteKey(pathname: string | null): string {
  if (!pathname) return "_default";
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) return "_default";
  const first = segments[0];
  if (first in SUGGESTIONS_BY_ROUTE) return first;
  return "_default";
}

/* ───────── component ───────── */

export default function StudentOrbitAgent({
  userId,
  classId,
  documentId,
  sourceFile,
  selectedSubject,
  enrolledClasses = [],
  hidden = false,
  onPlanChanged,
}: StudentOrbitAgentProps) {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  const pathname = usePathname();

  const routeKey = useMemo(() => getRouteKey(pathname), [pathname]);
  const suggestions = useMemo(() => SUGGESTIONS_BY_ROUTE[routeKey] || SUGGESTIONS_BY_ROUTE._default, [routeKey]);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [slowNotice, setSlowNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset messages and suggestions when route changes
  useEffect(() => {
    setMessages([]);
    setShowSuggestions(false);
    setInput("");
    setError(null);
  }, [routeKey]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input when opening
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  /* ── Dynamic suggestions: fetch from API for planning & evaluation ── */
  const [dynamicSuggestions, setDynamicSuggestions] = useState<string[] | null>(null);

  useEffect(() => {
    setDynamicSuggestions(null);
    if (routeKey === "planning") {
      apiClient.get("/api/planning/chat/examples", { baseURL: apiBaseUrl, timeout: 6000 })
        .then((res) => {
          const examples = Array.isArray(res.data?.examples) ? res.data.examples : null;
          if (examples && examples.length > 0) setDynamicSuggestions(examples);
        })
        .catch(() => {});
    } else if (routeKey === "evaluation") {
      apiClient.get("/api/evaluation/chat/examples", { baseURL: apiBaseUrl, timeout: 6000 })
        .then((res) => {
          const examples = Array.isArray(res.data?.examples) ? res.data.examples : null;
          if (examples && examples.length > 0) setDynamicSuggestions(examples);
        })
        .catch(() => {});
    }
  }, [routeKey, apiBaseUrl]);

  const activeSuggestions = dynamicSuggestions || suggestions;

  /* ── Send message to the right backend API ── */
  const sendMessage = useCallback(async (message: string) => {
    if (!message.trim() || !userId || loading) return;

    const userMsg = message.trim();
    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    const fallbackSubject = selectedSubject || enrolledClasses[0]?.subject || "";
    const fallbackClassId = enrolledClasses.find((c) => c.subject === fallbackSubject)?.id || classId || null;

    try {
      let res: { data: { reply?: string; [k: string]: unknown } };

      if (routeKey === "adaptive") {
        // Tutor Agent API
        res = await runLongRequest(
          () => apiClient.post("/api/adaptive/chat", {
            user_id: userId,
            subject: fallbackSubject,
            message: userMsg,
            document_id: documentId || null,
            source_file: sourceFile || "",
            roadmap_context: "",
            mode: "chat",
          }, { ...longRequestConfig, baseURL: apiBaseUrl }),
          { onSlowStateChange: setSlowNotice, slowDelayMs: 4500 },
        );
      } else if (routeKey === "planning" || routeKey === "my-learning") {
        // Planning Agent API — điều chỉnh lịch học (đẩy môn lên trước, thêm tài liệu tuần này, ...)
        res = await runLongRequest(
          () => apiClient.post("/api/planning/chat", {
            user_id: userId,
            message: userMsg,
          }, { ...longRequestConfig, baseURL: apiBaseUrl }),
          { onSlowStateChange: setSlowNotice, slowDelayMs: 4500 },
        );
      } else if (routeKey === "evaluation") {
        // Evaluation Agent API
        res = await runLongRequest(
          () => apiClient.post("/api/evaluation/chat", {
            user_id: userId,
            message: userMsg,
            subject: fallbackSubject || "",
          }, { ...longRequestConfig, baseURL: apiBaseUrl }),
          { onSlowStateChange: setSlowNotice, slowDelayMs: 4500 },
        );
      } else {
        // Default: Orbit Agent API
        res = await runLongRequest(
          () => apiClient.post("/api/orbit/chat", {
            user_id: userId,
            subject: fallbackSubject,
            message: userMsg,
            class_id: fallbackClassId,
            document_id: documentId || null,
            source_file: sourceFile || "",
          }, { ...longRequestConfig, baseURL: apiBaseUrl }),
          { onSlowStateChange: setSlowNotice, slowDelayMs: 4500 },
        );
      }

      const reply = typeof res.data?.reply === "string" ? res.data.reply : "Không có phản hồi.";
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      // Nếu vừa điều chỉnh lịch học → báo trang cha refresh cột Planning.
      if ((routeKey === "planning" || routeKey === "my-learning") && onPlanChanged) {
        onPlanChanged();
      }
    } catch (err: unknown) {
      const errMsg = normalizeApiError(err, "Agent tạm thời chưa thể phản hồi.");
      setError(errMsg);
      setMessages((prev) => [...prev, { role: "assistant", content: `❌ ${errMsg}` }]);
    } finally {
      setLoading(false);
    }
  }, [userId, routeKey, loading, selectedSubject, enrolledClasses, classId, documentId, sourceFile, apiBaseUrl, onPlanChanged]);

  const handleSend = () => {
    void sendMessage(input);
  };

  const handleSuggestionClick = (text: string) => {
    setInput(text);
    void sendMessage(text);
  };

  /* ── Hide on teacher/admin/test pages ── */
  const shouldHide = useMemo(() => {
    if (hidden || !userId) return true;
    if (!pathname) return false;
    return pathname.startsWith("/teacher") || pathname.startsWith("/admin") || pathname.startsWith("/test");
  }, [hidden, userId, pathname]);

  if (shouldHide) return null;

  /* ═══════════════════ RENDER ═══════════════════ */

  // Collapsed: floating black "O" button
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-[80] flex h-[62px] w-[62px] items-center justify-center rounded-full border border-white/10 bg-black shadow-[0_26px_72px_rgba(0,0,0,0.55)] transition-all hover:scale-105 active:scale-95"
        aria-label="Mở Orbit Agent"
        title="Mở Orbit Agent"
      >
        <span className="absolute inset-0 rounded-full border border-white/5" />
        <svg viewBox="0 0 32 32" className="relative z-10 h-8 w-8" fill="none">
          <circle cx="16" cy="16" r="12" stroke="white" strokeWidth="2.5" />
          <circle cx="16" cy="16" r="5" fill="white" />
        </svg>
      </button>
    );
  }

  // Expanded: chat panel
  return (
    <div className="fixed bottom-5 right-5 z-[80] flex h-[min(620px,calc(100vh-100px))] w-[400px] max-w-[94vw] flex-col overflow-hidden rounded-[1.35rem] border border-slate-700/20 bg-white shadow-[0_32px_80px_rgba(15,23,42,0.28)]">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-100 bg-[linear-gradient(135deg,#0f172a,#1e293b)] px-4 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10">
            <svg viewBox="0 0 32 32" className="h-5 w-5" fill="none">
              <circle cx="16" cy="16" r="12" stroke="white" strokeWidth="2.5" />
              <circle cx="16" cy="16" r="5" fill="white" />
            </svg>
          </div>
          <div>
            <h3 className="text-[13px] font-black tracking-[-0.02em] text-white">Orbit Agent</h3>
          </div>
        </div>
        <button
          onClick={() => setOpen(false)}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-600/30 text-slate-400 transition-all hover:bg-white/10 hover:text-white"
          title="Thu gọn"
          aria-label="Thu gọn Orbit Agent"
        >
          <Minimize2 size={14} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-slate-50/50 p-3">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center opacity-30 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-200/50">
              <svg viewBox="0 0 32 32" className="h-9 w-9" fill="none">
                <circle cx="16" cy="16" r="12" stroke="#94a3b8" strokeWidth="2.5" />
                <circle cx="16" cy="16" r="5" fill="#94a3b8" />
              </svg>
            </div>
            <p className="text-[13px] font-bold tracking-[0.03em] text-slate-500">Orbit Agent</p>
            <p className="mt-1 text-[11px] font-medium text-slate-400">Nhắn tin hoặc dùng gợi ý bên dưới</p>
          </div>
        ) : (
          <div className="space-y-3">
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "assistant" && (
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-slate-100 shadow-sm">
                    <svg viewBox="0 0 32 32" className="h-4 w-4" fill="none">
                      <circle cx="16" cy="16" r="12" stroke="#64748b" strokeWidth="2.5" />
                      <circle cx="16" cy="16" r="5" fill="#64748b" />
                    </svg>
                  </div>
                )}
                <div
                  className={`max-w-[88%] rounded-[1.05rem] px-3.5 py-2.5 text-sm leading-[1.6] shadow-sm ${
                    msg.role === "user"
                      ? "bg-slate-950 text-white rounded-tr-sm"
                      : "border border-slate-200 bg-white text-slate-700 rounded-tl-sm"
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <div className="prose prose-sm max-w-none prose-p:my-0 prose-ul:my-1.5 prose-li:my-0">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <p className="font-medium">{msg.content}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {loading && (
          <div className="mt-3 flex items-start gap-2">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-slate-100 shadow-sm">
              <svg viewBox="0 0 32 32" className="h-4 w-4" fill="none">
                <circle cx="16" cy="16" r="12" stroke="#64748b" strokeWidth="2.5" />
                <circle cx="16" cy="16" r="5" fill="#64748b" />
              </svg>
            </div>
            <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-slate-200 bg-white p-3 shadow-sm">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:75ms]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:150ms]" />
            </div>
          </div>
        )}

        {slowNotice && !loading && (
          <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] font-semibold text-amber-700">
            Yêu cầu vẫn đang xử lý, vui lòng chờ thêm một chút.
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions toggle + list */}
      <div className="shrink-0 border-t border-slate-100 bg-white px-3 pt-3">
        <button
          type="button"
          onClick={() => setShowSuggestions((prev) => !prev)}
          className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold text-slate-600 transition-colors hover:bg-slate-100"
        >
          <Lightbulb size={12} className={showSuggestions ? "text-amber-500" : "text-slate-400"} />
          Gợi ý câu hỏi
          <span className="text-[9px] text-slate-400">{showSuggestions ? "▲" : "▼"}</span>
        </button>

        {showSuggestions && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {activeSuggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => handleSuggestionClick(s)}
                disabled={loading}
                className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-[10px] font-semibold text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-slate-100 bg-white p-3">
        {error && !loading ? (
          <div className="mb-2 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-[10px] font-semibold text-rose-600">
            {error}
          </div>
        ) : null}
        <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-1.5 transition-all focus-within:border-slate-400 focus-within:ring-2 focus-within:ring-slate-100">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Nhắn tin cho Orbit Agent..."
            disabled={loading}
            className="h-9 flex-1 border-none bg-transparent px-3 text-[12px] font-medium text-slate-900 outline-none placeholder:text-slate-400 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white shadow-lg transition-all active:scale-90 disabled:opacity-30 disabled:active:scale-100"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          </button>
        </div>
      </div>
    </div>
  );
}
