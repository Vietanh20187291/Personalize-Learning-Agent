"use client";

import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "react-hot-toast";
import {
  Sparkles,
  ArrowRightCircle,
  RefreshCw,
  Send,
  MessageSquare,
  Clock3,
  Target,
  TriangleAlert,
  CircleCheck,
  Columns3,
  GripVertical,
  CalendarDays,
} from "lucide-react";

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
  priority_group: "low_score" | "no_score" | string;
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
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

  const [userId, setUserId] = useState<number | null>(null);
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [inProgressDocIds, setInProgressDocIds] = useState<number[]>([]);
  const [draggingDocId, setDraggingDocId] = useState<number | null>(null);

  const [examples, setExamples] = useState<string[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatItem[]>([
    {
      role: "assistant",
      content:
        "Planning Agent đã sẵn sàng. Bạn có thể yêu cầu đổi thứ tự môn học, đẩy tài liệu vào hôm nay hoặc tuần này.",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);

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

  const loadPlan = async (uid: number, refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);

      const res = await axios.get(`${apiBaseUrl}/api/planning/plan/${uid}`, {
        params: { refresh },
      });
      setPlan(res.data?.plan || null);
    } catch (e: unknown) {
      const msg = axios.isAxiosError(e)
        ? String(e.response?.data?.detail || e.message || "Lỗi tải kế hoạch")
        : "Lỗi tải kế hoạch";
      toast.error(msg);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (!userId) return;
    void loadPlan(userId, false);
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    const key = `planning_kanban_in_progress_${userId}`;
    const raw = localStorage.getItem(key);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        const ids = parsed.map((x) => Number(x)).filter((x) => Number.isFinite(x));
        setInProgressDocIds(Array.from(new Set(ids)));
      }
    } catch {
      // ignore invalid local cache
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    const key = `planning_kanban_in_progress_${userId}`;
    localStorage.setItem(key, JSON.stringify(inProgressDocIds));
  }, [userId, inProgressDocIds]);

  useEffect(() => {
    if (!plan) return;
    const validTodoIds = new Set((plan.steps || []).map((step) => step.document_id));
    setInProgressDocIds((prev) => prev.filter((id) => validTodoIds.has(id)));
  }, [plan]);

  useEffect(() => {
    const loadExamples = async () => {
      try {
        const res = await axios.get(`${apiBaseUrl}/api/planning/chat/examples`);
        setExamples(Array.isArray(res.data?.examples) ? res.data.examples : []);
      } catch {
        setExamples([
          "Đẩy các tài liệu môn Lập trình hướng đối tượng lên học trước",
          "Đưa các tài liệu môn Lưu trữ và phân tích dữ liệu ra học sau",
          "Thêm 2 tài liệu học cho tuần này",
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

  const handleRegenerate = async () => {
    if (!userId) return;
    try {
      setRefreshing(true);
      const res = await axios.post(`${apiBaseUrl}/api/planning/plan/regenerate`, {
        user_id: userId,
        reason: "manual_regenerate",
      });
      setPlan(res.data?.plan || null);
      setInProgressDocIds([]);
      toast.success("Đã cập nhật lại kế hoạch học tập.");
    } catch (e: unknown) {
      const msg = axios.isAxiosError(e)
        ? String(e.response?.data?.detail || e.message || "Không thể tạo lại kế hoạch")
        : "Không thể tạo lại kế hoạch";
      toast.error(msg);
    } finally {
      setRefreshing(false);
    }
  };

  const openInTutor = (item: {
    subject_name: string;
    document_id: number;
    document_title?: string;
    reason?: string;
    latest_score?: number | null;
  }) => {
    if (!userId) return;
    const pendingKey = `orbit_pending_action_${userId}`;
    const scoreText = item.latest_score != null ? `Điểm hiện tại: ${item.latest_score.toFixed(1)}.` : "";
    const payload = {
      action_type: "open_document",
      should_auto_execute: true,
      params: {
        subject: item.subject_name,
        document_id: item.document_id,
        summary: {
          title: item.document_title || "Tài liệu học",
          summary: `${item.reason || "Mở tài liệu trong gia sư AI"} ${scoreText}`.trim(),
          key_points: [],
        },
      },
    };
    localStorage.setItem(pendingKey, JSON.stringify(payload));
    window.location.href = `/adaptive?subject=${encodeURIComponent(item.subject_name || "")}`;
  };

  const onTodoDragStart = (docId: number) => {
    setDraggingDocId(docId);
  };

  const onDropToInProgress = () => {
    if (!draggingDocId) return;
    const canMove = todoSteps.some((step) => step.document_id === draggingDocId);
    if (!canMove) return;
    setInProgressDocIds((prev) => (prev.includes(draggingDocId) ? prev : [...prev, draggingDocId]));
    setDraggingDocId(null);
  };

  const sendPlanningMessage = async (content: string) => {
    if (!userId || !content.trim()) return;
    const message = content.trim();
    setChatMessages((prev) => [...prev, { role: "user", content: message }]);
    setChatInput("");
    setSending(true);
    try {
      const res = await axios.post(`${apiBaseUrl}/api/planning/chat`, {
        user_id: userId,
        message,
      });
      const reply = String(res.data?.reply || "Đã cập nhật kế hoạch.");
      setChatMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      if (res.data?.plan) {
        setPlan(res.data.plan);
      } else {
        await loadPlan(userId, false);
      }
    } catch (e: unknown) {
      const msg = axios.isAxiosError(e)
        ? String(e.response?.data?.detail || e.message || "Không thể xử lý yêu cầu")
        : "Không thể xử lý yêu cầu";
      setChatMessages((prev) => [...prev, { role: "assistant", content: `Lỗi: ${msg}` }]);
    } finally {
      setSending(false);
    }
  };

  const formatDate = (value: string | null | undefined) => {
    if (!value) return "Không xác định";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleDateString("vi-VN", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" });
  };

  if (loading) {
    return (
      <div className="min-h-screen pt-[92px] px-4 pb-8 app-bg">
        <div className="max-w-7xl mx-auto rounded-3xl border border-slate-200 bg-white p-8 shadow-sm text-slate-600 font-semibold">
          Đang tải kế hoạch học tập...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pt-[92px] px-4 pb-8 app-bg">
      <div className="max-w-7xl mx-auto grid grid-cols-1 xl:grid-cols-4 gap-6">
        <section className="xl:col-span-3 space-y-5">
          <div className="rounded-3xl border border-slate-200 bg-gradient-to-r from-cyan-50 via-white to-emerald-50 p-6 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] font-black text-cyan-700">Kế hoạch học tập cá nhân</p>
                <h1 className="text-2xl font-black text-slate-800 mt-2">Kanban học tập: Done - To Do - In Progress</h1>
                <p className="text-sm text-slate-600 mt-2">
                  Kế hoạch chỉ tự tạo 1 lần khi đăng nhập. Sau đó hệ thống chỉ đổi khi bạn chủ động làm mới hoặc chat yêu cầu cập nhật.
                </p>
              </div>
              <button
                onClick={handleRegenerate}
                disabled={refreshing || !userId}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-black uppercase tracking-wider disabled:opacity-50"
              >
                <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
                Làm mới kế hoạch
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 mt-5">
              <div className="rounded-2xl border border-cyan-200 bg-white p-4">
                <p className="text-[11px] uppercase font-black tracking-widest text-cyan-700">To Do</p>
                <p className="text-2xl font-black text-slate-800 mt-1">{todoSteps.length}</p>
              </div>
              <div className="rounded-2xl border border-indigo-200 bg-white p-4">
                <p className="text-[11px] uppercase font-black tracking-widest text-indigo-700">In Progress</p>
                <p className="text-2xl font-black text-slate-800 mt-1">{inProgressSteps.length}</p>
              </div>
              <div className="rounded-2xl border border-emerald-200 bg-white p-4">
                <p className="text-[11px] uppercase font-black tracking-widest text-emerald-700">Done</p>
                <p className="text-2xl font-black text-slate-800 mt-1">{doneItems.length}</p>
              </div>
              <div className="rounded-2xl border border-rose-200 bg-white p-4">
                <p className="text-[11px] uppercase font-black tracking-widest text-rose-700">Điểm thấp</p>
                <p className="text-2xl font-black text-slate-800 mt-1">{plan?.summary?.low_score_docs || 0}</p>
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <Columns3 size={18} className="text-slate-700" />
              <h2 className="text-lg font-black text-slate-800">Kanban Board</h2>
              <span className="ml-auto text-xs font-semibold text-slate-500">
                Chỉ cho phép kéo từ To Do sang In Progress
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 min-h-[420px]">
                <div className="flex items-center justify-between px-1 pb-2">
                  <p className="text-xs uppercase tracking-[0.18em] font-black text-slate-600">To Do</p>
                  <span className="text-xs font-bold text-slate-500">{todoSteps.length}</span>
                </div>
                <div className="space-y-3">
                  {todoSteps.map((step) => (
                    <div
                      key={`todo_${step.id}`}
                      draggable
                      onDragStart={() => onTodoDragStart(step.document_id)}
                      className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm cursor-grab"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-black text-slate-800">{step.document_title || step.document_filename}</p>
                        <GripVertical size={14} className="text-slate-400 shrink-0" />
                      </div>
                      <p className="text-xs text-slate-600 mt-1">Môn: <span className="font-bold">{step.subject_name || "Chưa rõ"}</span></p>
                      <div className="flex flex-wrap gap-2 mt-2 text-xs">
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-cyan-50 border border-cyan-200 text-cyan-700 font-semibold">
                          <CalendarDays size={12} /> Bắt đầu: {formatDate(step.planned_date)}
                        </span>
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 font-semibold">
                          <Clock3 size={12} /> Hạn: {formatDate(step.deadline_date || step.planned_date)}
                        </span>
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-slate-100 border border-slate-200 text-slate-700 font-semibold">
                          <Target size={12} /> Dự kiến {step.planned_duration_minutes || 60} phút
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        {step.priority_group === "low_score" ? (
                          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-bold">
                            <TriangleAlert size={12} /> Điểm thấp {step.latest_score != null ? `(${step.latest_score.toFixed(1)})` : ""}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-yellow-50 text-yellow-700 border border-yellow-200 font-bold">
                            <Clock3 size={12} /> Chưa có điểm
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => openInTutor(step)}
                        className="mt-3 inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-700 text-white text-[11px] font-black uppercase tracking-wider"
                      >
                        Học tài liệu
                        <ArrowRightCircle size={13} />
                      </button>
                    </div>
                  ))}
                  {!todoSteps.length && (
                    <div className="rounded-xl border border-dashed border-slate-300 p-4 text-xs text-slate-500 font-semibold text-center">
                      Không còn học phần trong To Do.
                    </div>
                  )}
                </div>
              </div>

              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDropToInProgress}
                className="rounded-2xl border border-indigo-200 bg-indigo-50/40 p-3 min-h-[420px]"
              >
                <div className="flex items-center justify-between px-1 pb-2">
                  <p className="text-xs uppercase tracking-[0.18em] font-black text-indigo-700">In Progress</p>
                  <span className="text-xs font-bold text-indigo-500">{inProgressSteps.length}</span>
                </div>
                <div className="space-y-3">
                  {inProgressSteps.map((step) => (
                    <div key={`progress_${step.id}`} className="rounded-xl border border-indigo-200 bg-white p-3 shadow-sm">
                      <p className="text-sm font-black text-slate-800">{step.document_title || step.document_filename}</p>
                      <p className="text-xs text-slate-600 mt-1">Môn: <span className="font-bold">{step.subject_name || "Chưa rõ"}</span></p>
                      <div className="flex flex-wrap gap-2 mt-2 text-xs">
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 font-semibold">
                          <Clock3 size={12} /> Đang học
                        </span>
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-slate-100 border border-slate-200 text-slate-700 font-semibold">
                          <CalendarDays size={12} /> Hạn: {formatDate(step.deadline_date || step.planned_date)}
                        </span>
                      </div>
                      <button
                        onClick={() => openInTutor(step)}
                        className="mt-3 inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-[11px] font-black uppercase tracking-wider"
                      >
                        Mở Gia sư AI
                        <ArrowRightCircle size={13} />
                      </button>
                    </div>
                  ))}
                  {!inProgressSteps.length && (
                    <div className="rounded-xl border border-dashed border-indigo-300 p-4 text-xs text-indigo-600 font-semibold text-center">
                      Kéo thả học phần từ cột To Do vào đây.
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-3 min-h-[420px]">
                <div className="flex items-center justify-between px-1 pb-2">
                  <p className="text-xs uppercase tracking-[0.18em] font-black text-emerald-700">Done</p>
                  <span className="text-xs font-bold text-emerald-600">{doneItems.length}</span>
                </div>
                <div className="space-y-3">
                  {doneItems.map((item) => (
                    <div key={`done_${item.document_id}`} className="rounded-xl border border-emerald-200 bg-white p-3 shadow-sm">
                      <p className="text-sm font-black text-slate-800">{item.document_title || item.document_filename}</p>
                      <p className="text-xs text-slate-600 mt-1">Môn: <span className="font-bold">{item.subject_name || "Chưa rõ"}</span></p>
                      <div className="flex flex-wrap gap-2 mt-2 text-xs">
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 font-semibold">
                          <CircleCheck size={12} /> Điểm: {item.latest_score.toFixed(1)}
                        </span>
                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full border font-semibold ${
                          item.is_late
                            ? "bg-rose-50 border-rose-200 text-rose-700"
                            : "bg-emerald-50 border-emerald-200 text-emerald-700"
                        }`}>
                          {item.is_late ? <TriangleAlert size={12} /> : <CircleCheck size={12} />} {item.completion_label}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-2">
                        Hoàn thành: <span className="font-semibold">{formatDate(item.completion_date)}</span> | Hạn kế hoạch: <span className="font-semibold">{formatDate(item.due_date)}</span>
                      </p>
                      <button
                        onClick={() =>
                          openInTutor({
                            subject_name: item.subject_name,
                            document_id: item.document_id,
                            document_title: item.document_title,
                            reason: item.improve_note,
                            latest_score: item.latest_score,
                          })
                        }
                        className="mt-3 inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-black uppercase tracking-wider"
                      >
                        Học cải thiện
                        <ArrowRightCircle size={13} />
                      </button>
                    </div>
                  ))}
                  {!doneItems.length && (
                    <div className="rounded-xl border border-dashed border-emerald-300 p-4 text-xs text-emerald-700 font-semibold text-center">
                      Chưa có học phần hoàn thành.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>

        <aside className="space-y-5">
          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sticky top-[92px]">
            <div className="flex items-center gap-2 mb-4">
              <MessageSquare size={18} className="text-indigo-700" />
              <h3 className="text-lg font-black text-slate-800">Planning Agent</h3>
            </div>

            <div className="space-y-2 mb-4">
              <p className="text-[11px] uppercase tracking-[0.18em] font-black text-slate-500">Ví dụ nhanh</p>
              <div className="flex flex-wrap gap-2">
                {examples.map((sample) => (
                  <button
                    key={sample}
                    onClick={() => setChatInput(sample)}
                    className="text-left px-3 py-2 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-700"
                  >
                    {sample}
                  </button>
                ))}
              </div>
            </div>

            <div className="h-[300px] overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-3 space-y-3 mb-3">
              {chatMessages.map((item, idx) => (
                <div
                  key={`${item.role}_${idx}`}
                  className={`max-w-[95%] px-3 py-2 rounded-xl text-sm whitespace-pre-wrap ${
                    item.role === "assistant"
                      ? "bg-white border border-slate-200 text-slate-700"
                      : "ml-auto bg-indigo-600 text-white"
                  }`}
                >
                  {item.content}
                </div>
              ))}
              {sending && (
                <div className="inline-flex items-center gap-2 text-xs font-semibold text-slate-500">
                  <Sparkles size={14} className="animate-pulse" /> Đang cập nhật kế hoạch...
                </div>
              )}
            </div>

            <div className="flex items-center gap-2">
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendPlanningMessage(chatInput);
                  }
                }}
                placeholder="Nhập yêu cầu thay đổi kế hoạch..."
                className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-100 focus:border-indigo-400"
              />
              <button
                onClick={() => void sendPlanningMessage(chatInput)}
                disabled={sending || !chatInput.trim()}
                className="h-10 w-10 inline-flex items-center justify-center rounded-xl bg-indigo-600 text-white disabled:opacity-50"
              >
                <Send size={16} />
              </button>
            </div>

            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800 font-semibold">
              <div className="inline-flex items-center gap-2 mb-1">
                <CircleCheck size={14} /> Mẹo sử dụng
              </div>
              <p>
                Bạn có thể chat để đổi thứ tự môn học, thêm tải học tuần này hoặc làm mới kế hoạch thủ công. Kanban sẽ phản ánh ngay trên tab hiện tại.
              </p>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
