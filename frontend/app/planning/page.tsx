"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import { toast } from "react-hot-toast";
import {
  ArrowRightCircle,
  CalendarDays,
  CircleCheck,
  Clock3,
  Columns3,
  GripVertical,
  RefreshCw,
  Target,
  TriangleAlert,
} from "lucide-react";

import StudentOrbitAgent from "@/components/StudentOrbitAgent";
import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "@/services/api";
import { confirmAlert } from "@/services/alerts";

type PlanStep = {
  id: number;
  plan_id: number;
  document_id: number;
  subject_id: number;
  class_id: number | null;
  step_order: number;
  planned_date: string;
  deadline_date: string | null;
  planned_duration_minutes: number | null;
  priority_group: "low_score" | "no_score" | "incomplete" | string;
  latest_score: number | null;
  reason: string;
  subject_name: string;
  document_title: string;
  document_filename: string;
  is_completed: boolean;
};

type CompletedItem = {
  document_id: number;
  subject_id: number;
  class_id: number | null;
  subject_name: string;
  document_title: string;
  document_filename: string;
  latest_score: number;
  completion_date: string;
  due_date: string;
  is_late: boolean;
  completion_label: string;
  improve_note: string;
};

type PlanData = {
  id: number;
  user_id: number;
  generated_at: string | null;
  generated_for_login_at: string | null;
  generation_reason: string;
  status: string;
  notes: string;
  summary: {
    total_steps: number;
    low_score_docs: number;
    missing_score_docs: number;
    completed_docs: number;
  };
  steps: PlanStep[];
  completed_items: CompletedItem[];
};

type ChatItem = {
  role: "user" | "assistant";
  content: string;
};

export default function PlanningPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  const [userId, setUserId] = useState<number | null>(null);
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [inProgressDocIds, setInProgressDocIds] = useState<number[]>([]);
  const [draggingDocId, setDraggingDocId] = useState<number | null>(null);
  const [dragSourceColumn, setDragSourceColumn] = useState<"todo" | "inprogress" | null>(null);
  const [examples, setExamples] = useState<string[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatItem[]>([
    {
      role: "assistant",
      content:
        "Planning Agent đã sẵn sàng. Bạn có thể yêu cầu đổi thứ tự môn học, ưu tiên tài liệu sớm hơn hoặc sắp xếp lại kế hoạch theo kỳ thi.",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);
  const [slowNotice, setSlowNotice] = useState(false);

  const requestPlan = async (uid: number, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);

      const res = await apiClient.get(`/api/planning/plan/${uid}`, {
        params: { refresh },
        baseURL: apiBaseUrl,
        ...(refresh ? longRequestConfig : {}),
      });
      setPlan(res.data?.plan || null);
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, "Lỗi tải kế hoạch học tập"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    const raw = localStorage.getItem("userId") || localStorage.getItem("user_id");
    if (!raw) {
      setLoading(false);
      toast.error("Không tìm thấy phiên đăng nhập.");
      return;
    }
    const uid = Number(raw);
    if (!uid) {
      setLoading(false);
      toast.error("ID người dùng không hợp lệ.");
      return;
    }
    setUserId(uid);
  }, []);

  useEffect(() => {
    if (!userId) return;
    void requestPlan(userId, false);
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    const key = `planning_kanban_in_progress_${userId}`;
    const raw = localStorage.getItem(key);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setInProgressDocIds(parsed.map((item) => Number(item)).filter((item) => Number.isFinite(item)));
      }
    } catch {
      setInProgressDocIds([]);
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    localStorage.setItem(`planning_kanban_in_progress_${userId}`, JSON.stringify(inProgressDocIds));
  }, [userId, inProgressDocIds]);

  useEffect(() => {
    if (!plan) return;
    const validIds = new Set((plan.steps || []).map((step) => step.document_id));
    setInProgressDocIds((prev) => prev.filter((id) => validIds.has(id)));
  }, [plan]);

  useEffect(() => {
    const loadExamples = async () => {
      try {
        const res = await apiClient.get("/api/planning/chat/examples", {
          baseURL: apiBaseUrl,
        });
        setExamples(Array.isArray(res.data?.examples) ? res.data.examples : []);
      } catch {
        setExamples([
          "Đẩy các tài liệu môn Lập trình hướng đối tượng lên học trước",
          "Cho các tài liệu môn Cơ sở dữ liệu học sớm hơn",
          "Sắp xếp lại kế hoạch để ưu tiên các tài liệu sắp thi",
        ]);
      }
    };
    void loadExamples();
  }, [apiBaseUrl]);

  const todoSteps = useMemo(() => {
    const all = [...(plan?.steps || [])].sort((a, b) => a.step_order - b.step_order);
    return all.filter((step) => !inProgressDocIds.includes(step.document_id));
  }, [plan, inProgressDocIds]);

  const inProgressSteps = useMemo(() => {
    const byDocId = new Map((plan?.steps || []).map((step) => [step.document_id, step]));
    return inProgressDocIds.map((docId) => byDocId.get(docId)).filter(Boolean) as PlanStep[];
  }, [plan, inProgressDocIds]);

  const doneItems = useMemo(() => {
    return [...(plan?.completed_items || [])].sort((a, b) => {
      if (a.is_late !== b.is_late) return a.is_late ? -1 : 1;
      return (b.completion_date || "").localeCompare(a.completion_date || "");
    });
  }, [plan]);

  const formatDate = (value: string | null | undefined) => {
    if (!value) return "Chưa xác định";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("vi-VN", {
      weekday: "short",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  };

  const handleRegenerate = async () => {
    if (!userId) return;
    const confirmed = await confirmAlert({
      title: "Làm mới kế hoạch",
      message: "Bạn có chắc muốn làm mới kế hoạch học tập?",
      confirmText: "Làm mới",
      cancelText: "Hủy",
      tone: "danger",
    });
    if (!confirmed) return;

    try {
      setRefreshing(true);
      const res = await runLongRequest(
        () =>
          apiClient.post(
            "/api/planning/plan/regenerate",
            {
              user_id: userId,
              reason: `manual_regenerate_${Date.now()}`,
            },
            {
              ...longRequestConfig,
              baseURL: apiBaseUrl,
            }
          ),
        { onSlowStateChange: setSlowNotice, slowDelayMs: 3500 }
      );
      setPlan(res.data?.plan || null);
      setInProgressDocIds([]);
      toast.success("Đã cập nhật lại kế hoạch học tập.");
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, "Không thể tạo lại kế hoạch"));
    } finally {
      setRefreshing(false);
    }
  };

  const openInTutor = (item: {
    subject_name: string;
    document_id: number;
    reason?: string;
    latest_score?: number | null;
  }) => {
    if (!userId) return;
    localStorage.setItem(
      `tutor_pending_document_${userId}`,
      JSON.stringify({
        subject: item.subject_name,
        document_id: item.document_id,
        note: item.reason || "",
        latest_score: item.latest_score ?? null,
      })
    );
    window.location.href = `/adaptive?subject=${encodeURIComponent(item.subject_name || "")}&document_id=${encodeURIComponent(
      String(item.document_id)
    )}`;
  };

  const sendPlanningMessage = async (content: string) => {
    if (!userId || !content.trim()) return;
    const message = content.trim();
    setChatMessages((prev) => [...prev, { role: "user", content: message }]);
    setChatInput("");
    setSending(true);

    try {
      const res = await runLongRequest(
        () =>
          apiClient.post(
            "/api/planning/chat",
            {
              user_id: userId,
              message,
            },
            {
              ...longRequestConfig,
              baseURL: apiBaseUrl,
            }
          ),
        { onSlowStateChange: setSlowNotice, slowDelayMs: 3500 }
      );
      const reply = String(res.data?.reply || "Đã cập nhật kế hoạch.");
      setChatMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      if (res.data?.plan) setPlan(res.data.plan);
      else await requestPlan(userId, false);
    } catch (error: unknown) {
      const messageText = normalizeApiError(error, "Không thể xử lý yêu cầu");
      setChatMessages((prev) => [...prev, { role: "assistant", content: `Lỗi: ${messageText}` }]);
    } finally {
      setSending(false);
    }
  };

  const onTodoDragStart = (docId: number) => {
    setDraggingDocId(docId);
    setDragSourceColumn("todo");
  };

  const onInProgressDragStart = (docId: number) => {
    setDraggingDocId(docId);
    setDragSourceColumn("inprogress");
  };

  const onDropToInProgress = () => {
    if (!draggingDocId || dragSourceColumn !== "todo") return;
    if (!todoSteps.some((step) => step.document_id === draggingDocId)) return;
    setInProgressDocIds((prev) => (prev.includes(draggingDocId) ? prev : [...prev, draggingDocId]));
    setDraggingDocId(null);
    setDragSourceColumn(null);
  };

  const onDropToTodo = () => {
    if (!draggingDocId || dragSourceColumn !== "inprogress") return;
    setInProgressDocIds((prev) => prev.filter((id) => id !== draggingDocId));
    setDraggingDocId(null);
    setDragSourceColumn(null);
  };

  if (loading) {
    return (
      <div className="page-shell px-4 pb-8">
        <div className="mx-auto max-w-7xl rounded-[2rem] border border-slate-200 bg-white p-8 text-sm font-semibold text-slate-600 shadow-sm">
          Đang tải kế hoạch học tập...
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell px-4 pb-8">
      <div className="mx-auto grid max-w-7xl gap-6 grid-cols-1">
        <section className="space-y-5">
          <div className="rounded-[2.2rem] border border-slate-200 bg-[linear-gradient(135deg,#ecfeff,white_44%,#ecfdf5)] p-6 shadow-[0_28px_80px_rgba(15,23,42,0.08)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.22em] text-cyan-700">Tab lộ trình</p>
                <h1 className="mt-2 text-2xl font-black tracking-tight text-slate-950">Planning Agent và Kanban học tập</h1>
                <p className="mt-2 max-w-2xl text-[13px] font-medium leading-6 text-slate-600">
                  Kế hoạch được tạo trên các tài liệu chưa hoàn thành. Khi bạn bấm làm mới hoặc chat điều chỉnh, hệ thống sẽ cập nhật lại ngày học và hạn dự kiến cho từng tài liệu.
                </p>
              </div>
              <button
                onClick={handleRegenerate}
                disabled={refreshing || !userId}
                className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-3.5 py-2.5 text-[10px] font-black uppercase tracking-[0.14em] text-white disabled:opacity-50"
              >
                <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
                Làm mới kế hoạch
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <SummaryCard label="Cần học" value={todoSteps.length} tone="cyan" />
              <SummaryCard label="Đang học" value={inProgressSteps.length} tone="indigo" />
              <SummaryCard label="Hoàn thành" value={doneItems.length} tone="emerald" />
              <SummaryCard label="Điểm thấp" value={plan?.summary?.low_score_docs || 0} tone="rose" />
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-2">
              <Columns3 size={18} className="text-slate-700" />
              <h2 className="text-lg font-black text-slate-900">Kanban học tập</h2>
              <span className="ml-auto text-[11px] font-semibold text-slate-500">Kéo thả giữa các cột</span>
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <div onDragOver={(event) => event.preventDefault()} onDrop={onDropToTodo} className="min-h-[420px] rounded-[1.7rem] border border-slate-200 bg-slate-50 p-3">
                <ColumnHeader label="Cần học" count={todoSteps.length} tone="slate" />
                <div className="space-y-3">
                  {todoSteps.map((step) => (
                    <article
                      key={`todo_${step.id}`}
                      draggable
                      onDragStart={() => onTodoDragStart(step.document_id)}
                      className="cursor-grab rounded-[1.4rem] border border-slate-200 bg-white p-3 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-black text-slate-900">{step.document_title || step.document_filename}</p>
                        <GripVertical size={14} className="shrink-0 text-slate-400" />
                      </div>
                      <p className="mt-1 text-xs font-medium text-slate-600">
                        Môn: <span className="font-black">{step.subject_name || "Chưa rõ"}</span>
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        <Tag icon={<CalendarDays size={12} />} tone="cyan">
                          Bắt đầu: {formatDate(step.planned_date)}
                        </Tag>
                        <Tag icon={<Clock3 size={12} />} tone="amber">
                          Hạn: {formatDate(step.deadline_date || step.planned_date)}
                        </Tag>
                        <Tag icon={<Target size={12} />} tone="slate">
                          {step.planned_duration_minutes || 60} phút
                        </Tag>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        {step.priority_group === "low_score" ? (
                          <Tag icon={<TriangleAlert size={12} />} tone="rose">
                            Điểm thấp {step.latest_score != null ? `(${step.latest_score.toFixed(1)})` : ""}
                          </Tag>
                        ) : step.priority_group === "no_score" ? (
                          <Tag icon={<Clock3 size={12} />} tone="yellow">
                            Chưa có điểm
                          </Tag>
                        ) : (
                          <Tag icon={<Clock3 size={12} />} tone="indigo">
                            Chưa hoàn thành
                          </Tag>
                        )}
                      </div>
                      <button
                        onClick={() => openInTutor(step)}
                        className="mt-3 inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-3 py-2 text-[10px] font-black uppercase tracking-[0.12em] text-white"
                      >
                        Học tài liệu
                        <ArrowRightCircle size={13} />
                      </button>
                    </article>
                  ))}
                  {!todoSteps.length ? (
                    <div className="rounded-[1.4rem] border border-dashed border-slate-300 p-4 text-center text-xs font-semibold text-slate-500">
                      Không còn tài liệu nào trong cột này.
                    </div>
                  ) : null}
                </div>
              </div>

              <div onDragOver={(event) => event.preventDefault()} onDrop={onDropToInProgress} className="min-h-[420px] rounded-[1.7rem] border border-indigo-200 bg-indigo-50/50 p-3">
                <ColumnHeader label="Đang học" count={inProgressSteps.length} tone="indigo" />
                <div className="space-y-3">
                  {inProgressSteps.map((step) => (
                    <article
                      key={`progress_${step.id}`}
                      draggable
                      onDragStart={() => onInProgressDragStart(step.document_id)}
                      className="cursor-grab rounded-[1.4rem] border border-indigo-200 bg-white p-3 shadow-sm"
                    >
                      <p className="text-sm font-black text-slate-900">{step.document_title || step.document_filename}</p>
                      <p className="mt-1 text-xs font-medium text-slate-600">
                        Môn: <span className="font-black">{step.subject_name || "Chưa rõ"}</span>
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        <Tag icon={<Clock3 size={12} />} tone="indigo">
                          Đang học
                        </Tag>
                        <Tag icon={<CalendarDays size={12} />} tone="slate">
                          Hạn: {formatDate(step.deadline_date || step.planned_date)}
                        </Tag>
                      </div>
                      <button
                        onClick={() => openInTutor(step)}
                        className="mt-3 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-3 py-2 text-[10px] font-black uppercase tracking-[0.12em] text-white"
                      >
                        Mở Gia sư
                        <ArrowRightCircle size={13} />
                      </button>
                    </article>
                  ))}
                  {!inProgressSteps.length ? (
                    <div className="rounded-[1.4rem] border border-dashed border-indigo-300 p-4 text-center text-xs font-semibold text-indigo-700">
                      Kéo thả tài liệu từ cột Cần học vào đây.
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="min-h-[420px] rounded-[1.7rem] border border-emerald-200 bg-emerald-50/50 p-3">
                <ColumnHeader label="Hoàn thành" count={doneItems.length} tone="emerald" />
                <div className="space-y-3">
                  {doneItems.map((item) => (
                    <article key={`done_${item.document_id}`} className="rounded-[1.4rem] border border-emerald-200 bg-white p-3 shadow-sm">
                      <p className="text-sm font-black text-slate-900">{item.document_title || item.document_filename}</p>
                      <p className="mt-1 text-xs font-medium text-slate-600">
                        Môn: <span className="font-black">{item.subject_name || "Chưa rõ"}</span>
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        <Tag icon={<CircleCheck size={12} />} tone="emerald">
                          Điểm: {item.latest_score.toFixed(1)}
                        </Tag>
                        <Tag icon={item.is_late ? <TriangleAlert size={12} /> : <CircleCheck size={12} />} tone={item.is_late ? "rose" : "emerald"}>
                          {item.completion_label}
                        </Tag>
                      </div>
                      <p className="mt-2 text-xs font-medium text-slate-500">
                        Hoàn thành: <span className="font-black">{formatDate(item.completion_date)}</span> | Hạn kế hoạch:{" "}
                        <span className="font-black">{formatDate(item.due_date)}</span>
                      </p>
                      <button
                        onClick={() =>
                          openInTutor({
                            subject_name: item.subject_name,
                            document_id: item.document_id,
                            reason: item.improve_note,
                            latest_score: item.latest_score,
                          })
                        }
                        className="mt-3 inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-3 py-2 text-[10px] font-black uppercase tracking-[0.12em] text-white"
                      >
                        Học cải thiện
                        <ArrowRightCircle size={13} />
                      </button>
                    </article>
                  ))}
                  {!doneItems.length ? (
                    <div className="rounded-[1.4rem] border border-dashed border-emerald-300 p-4 text-center text-xs font-semibold text-emerald-700">
                      Chưa có tài liệu hoàn thành.
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <StudentOrbitAgent
        userId={userId}
      />
    </div>
  );
}

function SummaryCard({ label, value, tone }: { label: string; value: number; tone: "cyan" | "indigo" | "emerald" | "rose" }) {
  const toneClass =
    tone === "cyan"
      ? "border-cyan-200 text-cyan-700"
      : tone === "indigo"
        ? "border-indigo-200 text-indigo-700"
        : tone === "emerald"
          ? "border-emerald-200 text-emerald-700"
          : "border-rose-200 text-rose-700";

  return (
    <div className={`rounded-[1.5rem] border bg-white p-4 ${toneClass}`}>
      <p className="text-[10px] font-black uppercase tracking-[0.18em]">{label}</p>
      <p className="mt-1 text-2xl font-black text-slate-900">{value}</p>
    </div>
  );
}

function ColumnHeader({ label, count, tone }: { label: string; count: number; tone: "slate" | "indigo" | "emerald" }) {
  const textClass = tone === "indigo" ? "text-indigo-700" : tone === "emerald" ? "text-emerald-700" : "text-slate-600";
  const countClass = tone === "indigo" ? "text-indigo-500" : tone === "emerald" ? "text-emerald-600" : "text-slate-500";

  return (
    <div className="flex items-center justify-between px-1 pb-2">
      <p className={`text-[10px] font-black uppercase tracking-[0.18em] ${textClass}`}>{label}</p>
      <span className={`text-xs font-bold ${countClass}`}>{count}</span>
    </div>
  );
}

function Tag({
  children,
  icon,
  tone,
}: {
  children: ReactNode;
  icon: ReactNode;
  tone: "cyan" | "amber" | "slate" | "rose" | "yellow" | "indigo" | "emerald";
}) {
  const toneClass =
    tone === "cyan"
      ? "border-cyan-200 bg-cyan-50 text-cyan-700"
      : tone === "amber"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : tone === "rose"
          ? "border-rose-200 bg-rose-50 text-rose-700"
          : tone === "yellow"
            ? "border-yellow-200 bg-yellow-50 text-yellow-700"
            : tone === "indigo"
              ? "border-indigo-200 bg-indigo-50 text-indigo-700"
              : tone === "emerald"
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-slate-200 bg-slate-100 text-slate-700";

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 font-semibold ${toneClass}`}>
      {icon}
      {children}
    </span>
  );
}
