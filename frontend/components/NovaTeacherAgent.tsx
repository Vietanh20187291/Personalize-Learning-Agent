"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  AlertCircle,
  Bot,
  ChevronRight,
  Loader,
  Minimize2,
  Send,
  Sparkles,
  WandSparkles,
} from "lucide-react";

import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "../services/api";

const NOVA_AGENT_IMAGE = "https://cdn-icons-png.flaticon.com/512/4712/4712109.png";

interface Message {
  role: "user" | "agent";
  content: string;
  timestamp: Date;
}

interface ActionMetadata {
  action_type: string;
  target: string;
  tab_name?: string;
  params?: Record<string, unknown>;
  message?: string;
  should_auto_execute?: boolean;
}

function NovaAvatar({
  imageUrl,
  compact = false,
}: {
  imageUrl: string;
  compact?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const frameClass = compact ? "h-10 w-10" : "h-14 w-14";
  const innerClass = compact ? "h-8 w-8" : "h-11 w-11";

  return (
    <div
      className={`relative ${frameClass} overflow-hidden rounded-[1.1rem] border border-cyan-300/30 bg-[radial-gradient(circle_at_30%_20%,rgba(34,211,238,0.32),rgba(2,6,23,0.96)_70%)] shadow-[0_0_28px_rgba(34,211,238,0.18)]`}
    >
      <span className="absolute inset-[1px] rounded-[1rem] border border-cyan-200/10" />
      <span className="absolute inset-x-[-40%] top-0 h-full rotate-[28deg] bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.4),transparent)] opacity-80 animate-[nova-shimmer_3.2s_linear_infinite]" />
      <div className="relative z-10 flex h-full items-center justify-center">
        {failed ? (
          <div
            className={`flex ${innerClass} items-center justify-center rounded-[0.9rem] bg-[linear-gradient(135deg,#0f766e,#2563eb)] text-sm font-black text-white`}
          >
            N
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl}
            alt="Nova AI"
            className={`${innerClass} rounded-[0.9rem] object-cover`}
            onError={() => setFailed(true)}
          />
        )}
      </div>
    </div>
  );
}

function formatTime(value: Date) {
  return value.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function NovaTeacherAgent() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  const pathname = usePathname();
  const router = useRouter();
  const isTeacherZone = useMemo(() => pathname?.startsWith("/teacher"), [pathname]);

  const [bootstrapped, setBootstrapped] = useState(false);
  const [open, setOpen] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [slowNotice, setSlowNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [teacherId, setTeacherId] = useState<number | null>(null);
  const [classId, setClassId] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestedQuestions = [
    "Tóm tắt nhanh tình hình lớp IT1",
    "Tình hình học tập sinh viên ABX thế nào",
    "Môn Lập trình hướng đối tượng hiện có những lớp nào",
    "Xuất đề trắc nghiệm 20 câu cho môn Lập trình hướng đối tượng",
  ];

  useEffect(() => {
    setBootstrapped(false);

    if (!isTeacherZone) {
      setTeacherId(null);
      setClassId(null);
      setBootstrapped(true);
      return;
    }

    const userIdRaw = localStorage.getItem("userId");
    const parsedUserId = userIdRaw ? Number(userIdRaw) : Number.NaN;
    const userId = Number.isFinite(parsedUserId) && parsedUserId > 0 ? parsedUserId : null;
    setTeacherId(userId);

    let resolvedClassId: number | null = null;
    const pathParts = pathname?.split("/").filter(Boolean) || [];
    if (pathParts.length > 2) {
      const potentialId = pathParts[pathParts.length - 1];
      if (!Number.isNaN(Number(potentialId))) {
        resolvedClassId = Number(potentialId);
      }
    }

    if (!resolvedClassId) {
      const storedClassId = localStorage.getItem("currentClassId");
      if (storedClassId) {
        resolvedClassId = Number(storedClassId);
      }
    }

    setClassId(resolvedClassId);

    if (!resolvedClassId && userId) {
      const controller = new AbortController();
      fetch(`${apiBaseUrl}/api/classroom/teacher/${encodeURIComponent(String(userId))}`, {
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok) {
            const text = await response.text();
            throw new Error(text.slice(0, 120));
          }
          return response.json();
        })
        .then((classes) => {
          if (Array.isArray(classes) && classes.length > 0 && Number(classes[0]?.id) > 0) {
            const firstClassId = Number(classes[0].id);
            setClassId(firstClassId);
            localStorage.setItem("currentClassId", firstClassId.toString());
          }
        })
        .catch((err) => {
          if (err?.name !== "AbortError") {
            console.error("Không thể lấy lớp cho Nova:", err);
          }
        })
        .finally(() => {
          setBootstrapped(true);
        });

      return () => controller.abort();
    }

    setBootstrapped(true);
  }, [apiBaseUrl, isTeacherZone, pathname]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    let storedSessionId = localStorage.getItem("nova_session_id");
    if (!storedSessionId) {
      storedSessionId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
      localStorage.setItem("nova_session_id", storedSessionId);
    }
    setSessionId(storedSessionId);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    const stored = localStorage.getItem(`nova_messages_${sessionId}`);
    if (!stored) return;

    try {
      const parsed = JSON.parse(stored) as Array<Omit<Message, "timestamp"> & { timestamp: string }>;
      setMessages(
        parsed.map((item) => ({
          ...item,
          timestamp: new Date(item.timestamp),
        })),
      );
    } catch (err) {
      console.error("Không thể đọc lịch sử Nova:", err);
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || messages.length === 0) return;
    localStorage.setItem(`nova_messages_${sessionId}`, JSON.stringify(messages));
  }, [messages, sessionId]);

  const handleNavigation = (action: ActionMetadata) => {
    if (action.action_type !== "open_tab") return;

    const actionClassId = Number(action.params?.classroom_id);
    const resolvedClassId = Number.isFinite(actionClassId) && actionClassId > 0 ? actionClassId : classId;

    switch (action.target) {
      case "learning_results":
        if (resolvedClassId) {
          localStorage.setItem("currentClassId", resolvedClassId.toString());
        }
        router.push("/teacher/members");
        break;
      case "admin":
        if (action.tab_name === "subjects") {
          router.push("/admin/subjects");
        }
        break;
      case "teacher":
        if (action.tab_name === "subjects") {
          const subjectName = String(action.params?.subject_name || "").trim();
          const className = String(action.params?.class_name || "").trim();
          const documentName = String(action.params?.document_name || "").trim();
          const mode = String(action.params?.mode || "").trim();
          const subjectId = Number(action.params?.subject_id);
          const classroomId = Number(action.params?.classroom_id);

          if (subjectName) localStorage.setItem("novaTargetSubject", subjectName);
          if (className) localStorage.setItem("novaTargetClass", className);
          if (documentName) localStorage.setItem("novaTargetDocument", documentName);
          if (Number.isFinite(subjectId) && subjectId > 0) localStorage.setItem("novaTargetSubjectId", subjectId.toString());
          if (Number.isFinite(classroomId) && classroomId > 0) localStorage.setItem("novaTargetClassId", classroomId.toString());
          if (mode) localStorage.setItem("novaManagementMode", mode);

          const query = new URLSearchParams();
          if (subjectName) query.set("subject", subjectName);
          if (className) query.set("class_name", className);
          if (documentName) query.set("document_name", documentName);
          if (Number.isFinite(subjectId) && subjectId > 0) query.set("subject_id", subjectId.toString());
          if (Number.isFinite(classroomId) && classroomId > 0) query.set("class_id", classroomId.toString());
          if (mode) query.set("mode", mode);

          router.push(query.toString() ? `/teacher/subjects?${query.toString()}` : "/teacher/subjects");
        } else if (action.tab_name === "exam") {
          router.push("/teacher/exam");
        } else if (action.tab_name === "documents") {
          router.push("/teacher/documents");
        }
        break;
      default:
        break;
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim()) {
      setError("Vui lòng nhập tin nhắn.");
      return;
    }
    if (!teacherId) {
      setError("Vui lòng đăng nhập lại.");
      return;
    }
    if (!classId) {
      setError("Vui lòng chọn một lớp học trước khi dùng Nova.");
      return;
    }

    const userMessage = inputValue.trim();
    setInputValue("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: userMessage, timestamp: new Date() }]);
    setLoading(true);

    try {
      const response = await runLongRequest(
        () =>
          apiClient.post(
            "/api/teacher/nova-interactive",
            {
              teacher_id: teacherId,
              class_id: classId,
              message: userMessage,
              session_id: sessionId,
            },
            {
              ...longRequestConfig,
              baseURL: apiBaseUrl,
            },
          ),
        {
          onSlowStateChange: setSlowNotice,
          slowDelayMs: 4500,
        },
      );

      const data = response.data;
      setMessages((prev) => [...prev, { role: "agent", content: String(data.reply || ""), timestamp: new Date() }]);

      if (data.action_metadata) {
        handleNavigation(data.action_metadata as ActionMetadata);
      }
    } catch (err) {
      const message = normalizeApiError(err, "Nova tạm thời chưa thể phản hồi.");
      setError(message);
      console.error("Nova lỗi:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectSuggestedQuestion = (question: string) => {
    setInputValue(question);
    setError(null);
    inputRef.current?.focus();
  };

  if (!isTeacherZone || !bootstrapped) return null;

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-[80] flex h-[74px] w-[74px] items-center justify-center rounded-full border border-cyan-300/28 bg-[radial-gradient(circle_at_28%_22%,rgba(34,211,238,0.42),rgba(8,15,32,0.98)_60%)] shadow-[0_0_0_1px_rgba(103,232,249,0.14),0_26px_72px_rgba(2,8,23,0.55)]"
        aria-label="Mở Nova"
        title="Mở Nova"
      >
        <span className="absolute inset-0 rounded-full border border-cyan-300/20" />
        <span className="absolute inset-[7px] rounded-full border border-cyan-200/12 bg-slate-950/90" />
        <span className="absolute inset-y-[18px] left-0 right-0 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.92),transparent)] opacity-90 blur-[0.5px] animate-[agent-scan_2.25s_linear_infinite]" />
        <span className="absolute inset-0 rounded-full bg-[conic-gradient(from_180deg_at_50%_50%,rgba(34,211,238,0)_0deg,rgba(34,211,238,0.82)_58deg,rgba(59,130,246,0.14)_118deg,rgba(34,211,238,0)_220deg,rgba(34,211,238,0.58)_318deg,rgba(34,211,238,0)_360deg)] animate-[spin_4.8s_linear_infinite]" />
        <span className="absolute right-3 top-3 rounded-full border border-cyan-200/20 bg-cyan-400/18 p-1 text-cyan-100">
          <Sparkles size={10} />
        </span>
        <div className="relative z-10">
          <NovaAvatar imageUrl={NOVA_AGENT_IMAGE} compact />
        </div>
      </button>
    );
  }

  return (
    <section
      className="fixed bottom-5 right-5 z-[80] flex max-h-[82vh] w-[420px] max-w-[94vw] flex-col overflow-hidden rounded-[2rem] border border-cyan-300/18 bg-[linear-gradient(180deg,rgba(5,10,24,0.98),rgba(7,18,39,0.98))] shadow-[0_36px_96px_rgba(2,8,23,0.62)] backdrop-blur-2xl"
      aria-label="Nova Agent"
    >
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.16),transparent_26%),radial-gradient(circle_at_top_right,rgba(37,99,235,0.18),transparent_28%)]" />
        <div className="absolute inset-0 opacity-45 [background-image:linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:26px_26px]" />
        <div className="absolute left-0 top-0 h-full w-[90px] bg-[linear-gradient(180deg,rgba(34,211,238,0.08),transparent_70%)]" />
      </div>

      <header className="relative border-b border-cyan-300/12 px-4 pb-4 pt-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 gap-3">
            <NovaAvatar imageUrl={NOVA_AGENT_IMAGE} />
            <div className="min-w-0">
              <div className="inline-flex items-center gap-1 rounded-full border border-cyan-300/16 bg-cyan-400/10 px-2.5 py-1 text-[9px] font-black uppercase tracking-[0.24em] text-cyan-100/85">
                <WandSparkles size={10} />
                Nova Console
              </div>
              <h3 className="mt-2 text-[16px] font-black tracking-[-0.03em] text-white">Nova Teacher Agent</h3>
            </div>
          </div>

          <button
            className="inline-flex h-10 w-10 items-center justify-center rounded-[1rem] border border-cyan-300/16 bg-white/8 text-cyan-100 shadow-[0_0_20px_rgba(34,211,238,0.12)] transition-colors hover:bg-white/12"
            onClick={() => setOpen(false)}
            aria-label="Thu gọn Nova"
            title="Thu gọn"
          >
            <Minimize2 size={16} />
          </button>
        </div>
      </header>

      <div className="relative flex-1 overflow-hidden">
        <div className="absolute inset-y-0 left-0 w-[3px] bg-[linear-gradient(180deg,rgba(34,211,238,0.9),rgba(59,130,246,0.14),transparent)]" />

        <div className="h-full space-y-3 overflow-y-auto px-4 py-4">
          {messages.length === 0 ? (
            <div className="rounded-[1.6rem] border border-cyan-300/14 bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.04))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
              <div className="flex items-center gap-2 text-cyan-50">
                <Bot size={16} className="text-cyan-300" />
                <p className="nova-copy-compact text-[12px] font-semibold leading-6">
                  Nova đang đứng trong ngữ cảnh lớp hiện tại và chỉ chờ yêu cầu từ giảng viên.
                </p>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {suggestedQuestions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => handleSelectSuggestedQuestion(question)}
                    className="group rounded-[1.15rem] border border-cyan-300/12 bg-slate-950/42 px-3 py-3 text-left transition hover:border-cyan-300/22 hover:bg-slate-900/60"
                  >
                    <span className="flex items-start justify-between gap-3">
                      <span className="nova-copy-compact text-[11px] font-semibold leading-5 text-cyan-50">{question}</span>
                      <ChevronRight size={14} className="mt-0.5 shrink-0 text-cyan-300/62 transition-transform group-hover:translate-x-0.5" />
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {error ? (
            <div className="flex gap-2 rounded-[1.2rem] border border-red-400/40 bg-red-500/14 p-3">
              <AlertCircle size={16} className="mt-0.5 shrink-0 text-red-300" />
              <p className="nova-copy-compact text-[12px] leading-6 text-red-100">{error}</p>
            </div>
          ) : null}

          {messages.map((msg, idx) => {
            const isUser = msg.role === "user";
            return (
              <div key={idx} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[88%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1.5`}>
                  <span className="px-1 text-[9px] font-bold uppercase tracking-[0.16em] text-cyan-100/38">
                    {isUser ? "Giảng viên" : "Nova"}
                  </span>
                  <div
                    className={`rounded-[1.3rem] px-3.5 py-3 text-[13px] leading-6 ${
                      isUser
                        ? "rounded-br-sm bg-[linear-gradient(135deg,rgba(6,182,212,0.92),rgba(37,99,235,0.88))] text-white shadow-[0_16px_34px_rgba(6,182,212,0.2)]"
                        : "rounded-bl-sm border border-cyan-300/14 bg-white/8 font-medium text-cyan-50"
                    }`}
                  >
                    {msg.content}
                  </div>
                  <span className="px-1 text-[9px] font-medium text-cyan-100/30">{formatTime(msg.timestamp)}</span>
                </div>
              </div>
            );
          })}

          {loading ? (
            <div className="flex flex-col items-start gap-2">
              <div className="flex items-center gap-2 rounded-[1.2rem] border border-cyan-300/14 bg-white/8 px-3 py-2.5 text-cyan-50">
                <Loader size={14} className="animate-spin" />
                <span className="nova-copy-compact text-[12px] font-medium">Nova đang xử lý yêu cầu...</span>
              </div>
              {slowNotice ? (
                <div className="nova-copy-compact rounded-[1rem] border border-cyan-300/14 bg-white/8 px-3 py-2 text-[11px] font-semibold text-cyan-50">
                  Yêu cầu vẫn đang được xử lý. Nova chưa mất kết nối, vui lòng đợi thêm một chút.
                </div>
              ) : null}
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>
      </div>

      <footer className="relative border-t border-cyan-300/12 px-4 py-4">
        <div className="mb-3 flex flex-wrap gap-2">
          {suggestedQuestions.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => handleSelectSuggestedQuestion(question)}
              disabled={loading}
              className="nova-chip-compact rounded-full border border-cyan-300/16 bg-white/7 px-2.5 py-1.5 text-[9.5px] font-semibold leading-4 text-cyan-100 transition-colors hover:bg-white/12 disabled:opacity-50"
              title={question}
            >
              {question}
            </button>
          ))}
        </div>

        <div className="rounded-[1.6rem] border border-cyan-300/14 bg-[linear-gradient(180deg,rgba(2,6,23,0.82),rgba(15,23,42,0.74))] p-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
          <div className="flex items-end gap-2">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void handleSendMessage();
                }
              }}
              placeholder="Nhập yêu cầu cho Nova..."
              className="nova-input-compact flex-1 rounded-[1.1rem] border border-transparent bg-transparent px-3 py-3 text-[11px] font-medium text-white outline-none placeholder:text-[10px] placeholder:font-medium placeholder:text-cyan-100/42"
              disabled={loading}
            />
            <button
              onClick={() => void handleSendMessage()}
              disabled={loading || !inputValue.trim()}
              className="inline-flex h-11 w-11 items-center justify-center rounded-[1.15rem] bg-[linear-gradient(135deg,rgba(34,211,238,0.94),rgba(37,99,235,0.9))] text-white shadow-[0_16px_34px_rgba(34,211,238,0.24)] transition hover:brightness-110 disabled:opacity-50"
              title="Gửi"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </footer>
    </section>
  );
}
