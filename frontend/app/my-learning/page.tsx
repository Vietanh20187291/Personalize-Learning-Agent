"use client";

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  BookOpen,
  BookOpenCheck,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  Clock,
  GraduationCap,
  Loader2,
  RefreshCw,
  Sparkles,
  Target,
  XCircle,
  CheckCircle,
  AlertTriangle,
  ArrowLeft,
  BellRing,
  FileText,
  Flag,
  X,
} from "lucide-react";
import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "@/services/api";
import StudentOrbitAgent from "@/components/StudentOrbitAgent";

// ------------------------------------------------------------------ //
//  Types                                                              //
// ------------------------------------------------------------------ //
type DocumentItem = {
  document_id: number;
  title: string;
  filename: string;
  latest_score: number | null;
  attempts: number;
  is_completed: boolean;
  last_test_at: string | null;
  wrong_answer_count: number;
};

type SubjectItem = {
  subject_id: number;
  subject_name: string;
  subject_icon: string | null;
  class_id: number;
  class_name: string;
  documents: DocumentItem[];
};

type WrongAnswerItem = {
  id: number;
  question_text: string;
  options: string[] | null;
  student_choice: string;
  correct_answer: string;
  explanation: string | null;
  created_at: string | null;
};

type AIInsight = {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
  study_pattern: string;
  motivation: string;
};

type PlanStep = {
  id: number;
  step_order: number;
  planned_date: string | null;
  deadline_date: string | null;
  document_id: number;
  document_title: string | null;
  document_filename: string | null;
  subject_name: string | null;
  priority_group: string | null;
  latest_score: number | null;
  is_completed: boolean;
  reason: string | null;
};

type Plan = {
  id: number;
  notes: string | null;
  summary?: { total_steps: number; low_score_docs: number; missing_score_docs: number; completed_docs: number };
  steps: PlanStep[];
};

type NotificationItem = {
  id: number;
  type: string;
  title: string;
  body: string | null;
  metadata: Record<string, unknown>;
  is_read: boolean;
  created_at: string | null;
};

// ------------------------------------------------------------------ //
//  Simple Markdown → HTML converter                                   //
// ------------------------------------------------------------------ //
function markdownToHtml(md: string): string {
  let html = md
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-lg font-bold text-slate-800 mt-5 mb-2">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-xl font-bold text-indigo-700 mt-6 mb-3 pb-2 border-b border-indigo-100">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-2xl font-black text-slate-900 mb-4">$1</h1>')
    // Bold & italic
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Unordered lists
    .replace(/^- (.+)$/gm, '<li class="ml-4 text-slate-700">• $1</li>')
    // Ordered lists
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 text-slate-700 list-decimal">$1</li>')
    // Paragraphs (double newlines)
    .replace(/\n\n/g, "</p><p class='text-slate-700 mb-2'>")
    // Single newlines → <br>
    .replace(/\n/g, "<br/>");

  return `<div class="prose-custom"><p class="text-slate-700 mb-2">${html}</p></div>`;
}

// ------------------------------------------------------------------ //
//  Component                                                          //
// ------------------------------------------------------------------ //
export default function MyLearningPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  const [userId, setUserId] = useState<number | null>(null);
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Drill-down state
  const [expandedSubjectId, setExpandedSubjectId] = useState<number | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<{ id: number; title: string } | null>(null);
  const [wrongAnswers, setWrongAnswers] = useState<WrongAnswerItem[]>([]);
  const [loadingWrong, setLoadingWrong] = useState(false);

  // Review generation state
  const [reviewContent, setReviewContent] = useState<string | null>(null);
  const [generatingReview, setGeneratingReview] = useState(false);
  const [slowNotice, setSlowNotice] = useState(false);

  // AI Insights state
  const [aiInsights, setAiInsights] = useState<AIInsight | null>(null);
  const [loadingInsights, setLoadingInsights] = useState(false);

  // Planning plan (cột phải) + directive popup
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [directivePopup, setDirectivePopup] = useState<NotificationItem | null>(null);

  // Fetch userId from localStorage
  useEffect(() => {
    const rawId = localStorage.getItem("userId") || localStorage.getItem("user_id");
    const uid = rawId ? Number(rawId) : null;
    if (!uid) {
      setLoading(false);
      return;
    }
    setUserId(uid);
  }, []);

  // Fetch subjects when userId is available
  useEffect(() => {
    if (!userId) return;
    const fetchSubjects = async () => {
      setLoading(true);
      try {
        const res = await axios.get(`${apiBaseUrl}/api/my-learning/subjects`, {
          params: { user_id: userId },
        });
        setSubjects(Array.isArray(res.data?.subjects) ? res.data.subjects : []);
      } catch {
        setSubjects([]);
      } finally {
        setLoading(false);
      }
    };
    void fetchSubjects();
  }, [apiBaseUrl, userId]);

  // Fetch AI Insights
  useEffect(() => {
    if (!userId) return;
    const fetchInsights = async () => {
      setLoadingInsights(true);
      try {
        const res = await axios.get(`${apiBaseUrl}/api/my-learning/ai-insights`, {
          params: { user_id: userId },
          timeout: 25000,
        });
        if (res.data?.insights) {
          setAiInsights(res.data.insights);
        }
      } catch {
        // ignore — insights are optional
      } finally {
        setLoadingInsights(false);
      }
    };
    void fetchInsights();
  }, [apiBaseUrl, userId]);

  // Fetch planning plan (GET plan tự áp dụng chỉ thị của giảng viên phía backend).
  const refreshPlan = useCallback(async () => {
    if (!userId) return;
    setLoadingPlan(true);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/planning/plan/${userId}`, {
        timeout: 30000,
      });
      if (res.data?.plan) {
        setPlan(res.data.plan as Plan);
      } else if (res.data?.ok === false) {
        // backend trả error_json_response khi lỗi — giữ plan cũ
      }
    } catch {
      // plan là tùy chọn — không báo lỗi
    } finally {
      setLoadingPlan(false);
    }
  }, [apiBaseUrl, userId]);

  useEffect(() => {
    void refreshPlan();
  }, [refreshPlan]);

  // Kiểm tra notification teacher_assignment chưa đọc có target_document_ids → popup.
  useEffect(() => {
    if (!userId) return;
    void (async () => {
      try {
        const res = await axios.get(`${apiBaseUrl}/api/notifications/${userId}`);
        const items: NotificationItem[] = Array.isArray(res.data?.items) ? res.data.items : [];
        const directiveNotif = items.find(
          (n) =>
            n.type === "teacher_assignment" &&
            !n.is_read &&
            Array.isArray((n.metadata as Record<string, unknown>)?.target_document_ids) &&
            ((n.metadata as Record<string, unknown>).target_document_ids as unknown[]).length > 0
        );
        if (directiveNotif) {
          setDirectivePopup(directiveNotif);
        }
      } catch {
        // bỏ qua
      }
    })();
  }, [apiBaseUrl, userId]);

  const dismissDirectivePopup = async () => {
    if (!directivePopup) return;
    try {
      await axios.post(`${apiBaseUrl}/api/notifications/mark-read`, {
        notification_id: directivePopup.id,
      });
    } catch {
      // bỏ qua
    }
    setDirectivePopup(null);
    void refreshPlan();
  };
  const fetchWrongAnswers = async (documentId: number, docTitle: string) => {
    if (!userId) return;
    setSelectedDocument({ id: documentId, title: docTitle });
    setReviewContent(null);
    setLoadingWrong(true);
    setWrongAnswers([]);

    try {
      const res = await axios.get(
        `${apiBaseUrl}/api/my-learning/documents/${documentId}/wrong-answers`,
        { params: { user_id: userId } }
      );
      setWrongAnswers(Array.isArray(res.data?.wrong_answers) ? res.data.wrong_answers : []);
    } catch {
      setWrongAnswers([]);
    } finally {
      setLoadingWrong(false);
    }
  };

  // Generate review from wrong answers
  const generateReview = async () => {
    if (!userId || !selectedDocument) return;
    setGeneratingReview(true);
    setSlowNotice(false);
    setReviewContent(null);

    try {
      const res = await runLongRequest(
        () =>
          apiClient.post(
            "/api/my-learning/generate-review",
            { user_id: userId, document_id: selectedDocument.id },
            { ...longRequestConfig, baseURL: apiBaseUrl }
          ),
        { onSlowStateChange: setSlowNotice, slowDelayMs: 3500 }
      );
      setReviewContent(String(res.data?.review_content || ""));
    } catch (error: unknown) {
      const msg = normalizeApiError(error, "Không thể sinh tài liệu ôn tập lúc này.");
      setReviewContent(`**Lỗi:** ${msg}`);
    } finally {
      setGeneratingReview(false);
    }
  };

  // ------------------------------------------------------------------ //
  //  Score badge color                                                  //
  // ------------------------------------------------------------------ //
  const scoreColor = (score: number | null) => {
    if (score === null) return "bg-slate-100 text-slate-500";
    if (score >= 80) return "bg-emerald-50 text-emerald-700 ring-emerald-200";
    if (score >= 60) return "bg-blue-50 text-blue-700 ring-blue-200";
    if (score >= 40) return "bg-amber-50 text-amber-700 ring-amber-200";
    return "bg-red-50 text-red-700 ring-red-200";
  };

  // Trạng thái học tập của tài liệu: đã qua / chưa qua / chưa học.
  const docStatus = (doc: DocumentItem): { label: string; cls: string; icon: React.ReactNode } => {
    if (doc.attempts > 0 || doc.latest_score !== null) {
      const passed = (doc.latest_score ?? 0) >= 50 || doc.is_completed;
      return passed
        ? {
            label: "Đã qua",
            cls: "bg-emerald-50 text-emerald-700 ring-emerald-200",
            icon: <CheckCircle size={11} />,
          }
        : {
            label: "Chưa qua",
            cls: "bg-amber-50 text-amber-700 ring-amber-200",
            icon: <AlertTriangle size={11} />,
          };
    }
    return {
      label: "Chưa học",
      cls: "bg-slate-100 text-slate-500 ring-slate-200",
      icon: <Clock size={11} />,
    };
  };

  // ------------------------------------------------------------------ //
  //  Render: Wrong Answers Panel                                        //
  // ------------------------------------------------------------------ //
  if (selectedDocument) {
    return (
      <div className="page-shell px-4 pb-8 text-slate-800">
        <div className="mx-auto max-w-5xl space-y-5">
          {/* Header */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setSelectedDocument(null);
                setWrongAnswers([]);
                setReviewContent(null);
              }}
              className="flex h-10 w-10 items-center justify-center rounded-full border border-white/70 bg-white/82 text-slate-600 shadow-sm transition-all hover:text-slate-950"
            >
              <ArrowLeft size={18} />
            </button>
            <div>
              <p className="text-xs font-semibold text-slate-500">Câu làm sai</p>
              <h1 className="text-lg font-bold text-slate-900">{selectedDocument.title}</h1>
            </div>
          </div>

          {/* Loading */}
          {loadingWrong ? (
            <div className="flex flex-col items-center justify-center rounded-[2rem] border border-slate-200 bg-white py-16 shadow-sm">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
              <p className="mt-3 text-sm font-medium text-slate-500">Đang tải câu sai...</p>
            </div>
          ) : wrongAnswers.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-[2rem] border border-slate-200 bg-white py-16 shadow-sm">
              <CheckCircle className="h-12 w-12 text-emerald-300" />
              <p className="mt-3 text-lg font-bold text-slate-700">Không có câu sai!</p>
              <p className="mt-1 text-sm text-slate-500">Bạn chưa làm sai câu nào cho tài liệu này.</p>
            </div>
          ) : (
            <>
              {/* Wrong answers count + generate button */}
              <div className="flex items-center justify-between rounded-[1.6rem] border border-slate-200 bg-white px-5 py-4 shadow-sm">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-red-50 p-2.5">
                    <XCircle className="h-5 w-5 text-red-500" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-slate-900">
                      {wrongAnswers.length} câu làm sai
                    </p>
                    <p className="text-xs text-slate-500">Xem chi tiết hoặc sinh tài liệu ôn tập</p>
                  </div>
                </div>
                <button
                  onClick={() => void generateReview()}
                  disabled={generatingReview}
                  className="flex items-center gap-2 rounded-full bg-[linear-gradient(180deg,#1d4ed8,#0f172a)] px-5 py-2.5 text-sm font-bold text-white shadow-[0_10px_24px_rgba(29,78,216,0.25)] transition-all hover:shadow-lg disabled:opacity-50"
                >
                  {generatingReview ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      {slowNotice ? "Đang tạo..." : "Chờ Groq..."}
                    </>
                  ) : (
                    <>
                      <Sparkles size={16} />
                      Sinh tài liệu ôn tập
                    </>
                  )}
                </button>
              </div>

              {/* Review content */}
              {reviewContent && (
                <div className="overflow-hidden rounded-[2rem] border border-indigo-100 bg-[linear-gradient(135deg,#eff6ff,white_40%,#eef2ff)] shadow-sm">
                  <div className="flex items-center gap-2 border-b border-indigo-50 px-6 py-4">
                    <Sparkles className="h-5 w-5 text-indigo-600" />
                    <h3 className="text-lg font-bold text-indigo-900">Tài liệu ôn tập</h3>
                  </div>
                  <div
                    className="px-6 py-5 leading-relaxed"
                    dangerouslySetInnerHTML={{ __html: markdownToHtml(reviewContent) }}
                  />
                </div>
              )}

              {/* List of wrong answers */}
              <div className="space-y-3">
                {wrongAnswers.map((wa, idx) => (
                  <div
                    key={wa.id || idx}
                    className="rounded-[1.6rem] border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-50 text-sm font-bold text-red-600">
                        {idx + 1}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-slate-800">{wa.question_text}</p>

                        {/* Options */}
                        {wa.options && wa.options.length > 0 && (
                          <div className="mt-2 space-y-1">
                            {wa.options.map((opt, oi) => {
                              const optLabel = opt.trim().charAt(0).toUpperCase();
                              const isStudentChoice = optLabel === wa.student_choice?.toUpperCase();
                              const isCorrect = optLabel === wa.correct_answer?.toUpperCase();
                              return (
                                <div
                                  key={oi}
                                  className={`rounded-lg px-3 py-1.5 text-sm ${
                                    isCorrect
                                      ? "bg-emerald-50 font-semibold text-emerald-700"
                                      : isStudentChoice
                                        ? "bg-red-50 font-semibold text-red-600 line-through"
                                        : "bg-slate-50 text-slate-600"
                                  }`}
                                >
                                  {opt}
                                  {isCorrect && " ✓"}
                                  {isStudentChoice && !isCorrect && " ✗"}
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* Answer summary if no options */}
                        {(!wa.options || wa.options.length === 0) && (
                          <div className="mt-2 flex items-center gap-4 text-sm">
                            <span className="text-red-600">
                              Bạn chọn: <strong>{wa.student_choice}</strong>
                            </span>
                            <span className="text-emerald-600">
                              Đáp án đúng: <strong>{wa.correct_answer}</strong>
                            </span>
                          </div>
                        )}

                        {/* Explanation */}
                        {wa.explanation && (
                          <div className="mt-2 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
                            💡 {wa.explanation}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------ //
  //  Render: Main Subject / Document View                               //
  // ------------------------------------------------------------------ //
  return (
    <div className="page-shell px-4 pb-8 text-slate-800">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Hero header */}
        <section className="overflow-hidden rounded-[2.25rem] border border-slate-200 bg-[linear-gradient(135deg,#dbeafe,white_42%,#eef2ff)] shadow-[0_30px_80px_rgba(15,23,42,0.08)]">
          <div className="px-6 py-7">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-indigo-800">
              <BookOpenCheck size={13} />
              Tab lộ trình
            </div>
            <h1 className="mt-4 text-2xl font-black tracking-tight text-slate-950">
              Lộ trình học tập cá nhân
            </h1>
            <p className="mt-2 max-w-2xl text-[13px] font-medium leading-6 text-slate-600">
              Lịch học tuần, điểm theo tài liệu và các câu cần ôn lại.
            </p>
          </div>
        </section>

        {/* Popup: giáo viên yêu cầu học thêm tài liệu (Nova → Orbit → Planning) */}
        {directivePopup && (
          <DirectivePopup
            notification={directivePopup}
            onClose={() => void dismissDirectivePopup()}
          />
        )}

        <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        {/* CỘT TRÁI: môn học, tài liệu, nhận xét AI */}
        <div className="space-y-6">

        {/* AI Insights — Nhận xét cá nhân hóa */}
        {loadingInsights ? (
          <div className="overflow-hidden rounded-[2rem] border border-indigo-100 bg-gradient-to-r from-indigo-50/80 via-white to-purple-50/80 p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
              <span className="text-sm font-semibold text-indigo-700">Đang phân tích dữ liệu học tập...</span>
            </div>
          </div>
        ) : aiInsights ? (
          <section className="overflow-hidden rounded-[2rem] border border-indigo-100 bg-gradient-to-br from-indigo-50/80 via-white to-purple-50/80 shadow-sm">
            <div className="flex items-center gap-3 border-b border-indigo-100/60 px-6 py-4">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-md">
                <Sparkles size={18} />
              </div>
              <div>
                <h2 className="text-base font-black text-indigo-900">AI Nhận xét học tập</h2>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-indigo-400">Phân tích dựa trên dữ liệu thực tế của bạn</p>
              </div>
            </div>
            <div className="space-y-4 px-6 py-5">
              {/* Summary */}
              <p className="text-sm font-semibold leading-relaxed text-slate-800">{aiInsights.summary}</p>

              {/* Strengths & Weaknesses — 2 columns */}
              <div className="grid gap-4 sm:grid-cols-2">
                {aiInsights.strengths.length > 0 && (
                  <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 px-4 py-3">
                    <p className="mb-2 text-[10px] font-black uppercase tracking-[0.14em] text-emerald-700">✦ Điểm mạnh</p>
                    <ul className="space-y-1.5">
                      {aiInsights.strengths.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 text-[12px] font-medium text-emerald-900">
                          <span className="mt-0.5 text-emerald-500">✓</span>
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {aiInsights.weaknesses.length > 0 && (
                  <div className="rounded-xl border border-amber-100 bg-amber-50/60 px-4 py-3">
                    <p className="mb-2 text-[10px] font-black uppercase tracking-[0.14em] text-amber-700">⚠ Cần cải thiện</p>
                    <ul className="space-y-1.5">
                      {aiInsights.weaknesses.map((w, i) => (
                        <li key={i} className="flex items-start gap-2 text-[12px] font-medium text-amber-900">
                          <span className="mt-0.5 text-amber-500">!</span>
                          {w}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Recommendations */}
              {aiInsights.recommendations.length > 0 && (
                <div className="rounded-xl border border-blue-100 bg-blue-50/50 px-4 py-3">
                  <p className="mb-2 text-[10px] font-black uppercase tracking-[0.14em] text-blue-700">💡 Đề xuất hành động</p>
                  <ul className="space-y-1.5">
                    {aiInsights.recommendations.map((r, i) => (
                      <li key={i} className="flex items-start gap-2 text-[12px] font-medium text-blue-900">
                        <span className="mt-0.5 text-blue-500">→</span>
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Study pattern + motivation */}
              <div className="flex flex-wrap gap-3">
                {aiInsights.study_pattern && (
                  <div className="rounded-lg border border-slate-200 bg-white/70 px-3 py-2 text-[11px] font-medium text-slate-600">
                    📊 {aiInsights.study_pattern}
                  </div>
                )}
                {aiInsights.motivation && (
                  <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 px-3 py-2 text-[11px] font-bold text-indigo-700">
                    🎯 {aiInsights.motivation}
                  </div>
                )}
              </div>
            </div>
          </section>
        ) : null}

        {/* Loading */}
        {loading ? (
          <div className="flex flex-col items-center justify-center rounded-[2rem] border border-slate-200 bg-white py-16 shadow-sm">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
            <p className="mt-3 text-sm font-medium text-slate-500">Đang tải dữ liệu học tập...</p>
          </div>
        ) : subjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-[2rem] border border-dashed border-slate-300 bg-white px-6 py-16 text-center shadow-sm">
            <GraduationCap className="mb-4 h-14 w-14 text-slate-300" />
            <h2 className="text-xl font-black text-slate-700">Chưa có môn học nào</h2>
            <p className="mt-2 max-w-xl text-sm font-medium text-slate-500">
              Bạn cần tham gia lớp học trước. Sau khi làm bài kiểm tra, điểm số và câu sai sẽ hiện ở đây.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {subjects.map((subject) => {
              const isExpanded = expandedSubjectId === subject.subject_id;
              const totalDocs = subject.documents.length;
              const avgScore =
                totalDocs > 0
                  ? subject.documents
                      .filter((d) => d.latest_score !== null)
                      .reduce((sum, d) => sum + (d.latest_score || 0), 0) /
                    Math.max(1, subject.documents.filter((d) => d.latest_score !== null).length)
                  : null;
              const totalWrong = subject.documents.reduce((s, d) => s + d.wrong_answer_count, 0);

              return (
                <div
                  key={subject.subject_id}
                  className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-sm transition-all"
                >
                  {/* Subject header */}
                  <button
                    onClick={() =>
                      setExpandedSubjectId(isExpanded ? null : subject.subject_id)
                    }
                    className="flex w-full items-center justify-between px-6 py-5 text-left transition hover:bg-slate-50/50"
                  >
                    <div className="flex items-center gap-4">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,#dbeafe,#ede9fe)] text-2xl">
                        {subject.subject_icon || "📚"}
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-slate-900">{subject.subject_name}</h3>
                        <div className="mt-1 flex items-center gap-3 text-xs font-medium text-slate-500">
                          <span className="flex items-center gap-1">
                            <FileText size={12} /> {totalDocs} tài liệu
                          </span>
                          {avgScore !== null && (
                            <span className="flex items-center gap-1">
                              <Target size={12} /> TB {Math.round(avgScore)}đ
                            </span>
                          )}
                          {totalWrong > 0 && (
                            <span className="flex items-center gap-1 text-red-500">
                              <XCircle size={12} /> {totalWrong} câu sai
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {isExpanded ? (
                        <ChevronDown size={20} className="text-slate-400" />
                      ) : (
                        <ChevronRight size={20} className="text-slate-400" />
                      )}
                    </div>
                  </button>

                  {/* Documents list (expanded) */}
                  {isExpanded && (
                    <div className="border-t border-slate-100 px-6 pb-5">
                      {subject.documents.length === 0 ? (
                        <div className="py-8 text-center text-sm text-slate-500">
                          Lớp học chưa có tài liệu nào.
                        </div>
                      ) : (
                        <div className="mt-4 space-y-2">
                          {subject.documents.map((doc) => (
                            <div
                              key={doc.document_id}
                              className="group flex items-center justify-between rounded-[1.4rem] border border-slate-100 bg-slate-50/50 px-4 py-3.5 transition hover:border-indigo-100 hover:bg-indigo-50/30"
                            >
                              <div className="flex items-center gap-3 min-w-0">
                                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-slate-400 shadow-sm">
                                  <FileText size={16} />
                                </div>
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-semibold text-slate-800">
                                    {doc.title}
                                  </p>
                                  <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                                    {doc.attempts > 0 && (
                                      <span className="flex items-center gap-1">
                                        <RefreshCw size={10} /> {doc.attempts} lần thi
                                      </span>
                                    )}
                                    {doc.last_test_at && (
                                      <span className="flex items-center gap-1">
                                        <Clock size={10} />{" "}
                                        {new Date(doc.last_test_at).toLocaleDateString("vi-VN")}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>

                              <div className="flex items-center gap-3">
                                {/* Wrong answer count badge */}
                                {doc.wrong_answer_count > 0 && (
                                  <span className="flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-[10px] font-bold text-red-600 ring-1 ring-red-100">
                                    <XCircle size={10} />
                                    {doc.wrong_answer_count} sai
                                  </span>
                                )}

                                {/* Status badge: Đã qua / Chưa qua / Chưa học */}
                                {(() => {
                                  const st = docStatus(doc);
                                  return (
                                    <span
                                      className={`flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-bold ring-1 ${st.cls}`}
                                    >
                                      {st.icon}
                                      {st.label}
                                    </span>
                                  );
                                })()}

                                {/* Score badge (chỉ hiện khi có điểm) */}
                                {doc.latest_score !== null && (
                                  <span
                                    className={`flex items-center gap-1 rounded-full px-2.5 py-1.5 text-[11px] font-bold ring-1 ${scoreColor(doc.latest_score)}`}
                                  >
                                    {Math.round(doc.latest_score)}đ
                                  </span>
                                )}

                                {/* View wrong answers button */}
                                {doc.wrong_answer_count > 0 && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      void fetchWrongAnswers(doc.document_id, doc.title);
                                    }}
                                    className="flex items-center gap-1.5 rounded-full bg-[linear-gradient(180deg,#1d4ed8,#0f172a)] px-4 py-2 text-xs font-bold text-white shadow-sm transition hover:shadow-md"
                                  >
                                    <AlertTriangle size={12} />
                                    Xem câu sai
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        </div>

        {/* CỘT PHẢI: Lịch trình tuần (Planning plan) */}
        <aside className="space-y-4">
          <div className="sticky top-4">
            <PlanColumn
              plan={plan}
              loading={loadingPlan}
              onRefresh={() => void refreshPlan()}
              userId={userId}
            />
          </div>
        </aside>
        </div>
      </div>

      <StudentOrbitAgent
        userId={userId}
        onPlanChanged={() => void refreshPlan()}
      />
    </div>
  );
}

// ------------------------------------------------------------------ //
//  Cột phải: Lịch trình tuần (Planning plan)                          //
// ------------------------------------------------------------------ //
function priorityBadgeCls(group: string | null): string {
  switch (group) {
    case "teacher_directive":
      return "bg-amber-50 text-amber-700 ring-amber-200";
    case "low_score":
      return "bg-red-50 text-red-700 ring-red-200";
    case "no_score":
      return "bg-slate-100 text-slate-600 ring-slate-200";
    default:
      return "bg-blue-50 text-blue-700 ring-blue-200";
  }
}

function priorityLabel(group: string | null): string {
  switch (group) {
    case "teacher_directive":
      return "Yêu cầu GV";
    case "low_score":
      return "Điểm thấp";
    case "no_score":
      return "Chưa có điểm";
    default:
      return group || "";
  }
}

function PlanColumn({
  plan,
  loading,
  onRefresh,
  userId,
}: {
  plan: Plan | null;
  loading: boolean;
  onRefresh: () => void;
  userId: number | null;
}) {
  const [regenerating, setRegenerating] = useState(false);
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  const handleRegenerate = async () => {
    if (!userId) return;
    setRegenerating(true);
    try {
      await axios.post(
        `${apiBaseUrl}/api/planning/plan/regenerate`,
        { user_id: userId, reason: "manual" },
        { ...longRequestConfig }
      );
      onRefresh();
    } catch {
      // bỏ qua
    } finally {
      setRegenerating(false);
    }
  };

  // Mở tài liệu được chọn sang tab Gia sư (/adaptive) để học luôn.
  const openInTutor = (step: PlanStep) => {
    if (!userId || !step.document_id) return;
    localStorage.setItem(
      `tutor_pending_document_${userId}`,
      JSON.stringify({
        subject: step.subject_name || "",
        document_id: step.document_id,
        note: step.reason || "",
        latest_score: step.latest_score ?? null,
      })
    );
    window.location.href = `/adaptive?subject=${encodeURIComponent(step.subject_name || "")}&document_id=${encodeURIComponent(
      String(step.document_id)
    )}`;
  };

  const steps = plan?.steps ?? [];
  const total = plan?.summary?.total_steps ?? steps.length;

  return (
    <div className="overflow-hidden rounded-[2rem] border border-cyan-100 bg-[linear-gradient(135deg,#ecfeff,white_60%,#eff6ff)] shadow-[0_20px_50px_rgba(15,23,42,0.06)]">
      <div className="flex items-center justify-between gap-3 border-b border-cyan-100/70 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 text-white shadow-md">
            <CalendarDays size={18} />
          </div>
          <div>
            <h2 className="text-base font-black text-cyan-900">Lịch trình tuần</h2>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-cyan-500">
              Sinh bởi Planning Agent
            </p>
          </div>
        </div>
        <button
          onClick={() => void handleRegenerate()}
          disabled={regenerating}
          className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-bold text-cyan-700 shadow-sm ring-1 ring-cyan-100 transition hover:bg-cyan-50 disabled:opacity-50"
        >
          {regenerating ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Tạo lại
        </button>
      </div>

      <div className="px-5 py-4">
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-cyan-600">
            <Loader2 size={14} className="animate-spin" />
            Đang tải lịch học...
          </div>
        ) : steps.length === 0 ? (
          <div className="py-6 text-center text-sm text-slate-500">
            Chưa có lịch học. Ấn &quot;Tạo lại&quot; để Planning Agent sinh lịch từ các tài liệu chưa có điểm.
          </div>
        ) : (
          <>
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-cyan-700">
              <Flag size={12} />
              {total} mục cần học — Ưu tiên tài liệu chưa qua / điểm thấp
            </div>
            <ol className="space-y-2.5">
              {steps.map((step) => {
                const isPriority =
                  step.priority_group === "teacher_directive" ||
                  step.priority_group === "low_score" ||
                  step.priority_group === "no_score";
                return (
                  <li
                    key={step.id}
                    className={`rounded-2xl border px-3.5 py-3 shadow-sm transition ${
                      isPriority
                        ? "border-cyan-300 bg-gradient-to-r from-cyan-50 to-white ring-1 ring-cyan-100"
                        : "border-slate-100 bg-white/80"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-bold text-slate-800">
                          <span className="mr-1.5 text-cyan-500">{step.step_order}.</span>
                          {step.document_title || step.document_filename || `Tài liệu #${step.document_id}`}
                        </p>
                        {step.subject_name && (
                          <p className="mt-0.5 truncate text-[11px] font-medium text-slate-500">
                            {step.subject_name}
                          </p>
                        )}
                        {step.deadline_date && (
                          <p className="mt-1 flex items-center gap-1 text-[11px] text-slate-500">
                            <Clock size={10} />
                            Hạn: {new Date(step.deadline_date).toLocaleDateString("vi-VN")}
                          </p>
                        )}
                      </div>
                      <span
                        className={`shrink-0 rounded-full px-2 py-0.5 text-[9px] font-bold ring-1 ${priorityBadgeCls(
                          step.priority_group
                        )}`}
                      >
                        {priorityLabel(step.priority_group)}
                      </span>
                    </div>
                    {step.reason && step.priority_group === "teacher_directive" && (
                      <p className="mt-1.5 rounded-lg bg-amber-50 px-2 py-1 text-[10px] font-medium text-amber-700">
                        {step.reason}
                      </p>
                    )}
                    <button
                      onClick={() => openInTutor(step)}
                      className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.1em] text-white shadow-sm transition hover:from-cyan-500 hover:to-blue-500"
                    >
                      <BookOpen size={12} />
                      Học tài liệu
                    </button>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
//  Popup: Giáo viên yêu cầu học thêm tài liệu                          //
// ------------------------------------------------------------------ //
function DirectivePopup({
  notification,
  onClose,
}: {
  notification: NotificationItem;
  onClose: () => void;
}) {
  const docCount = (
    (notification.metadata as Record<string, unknown>)?.target_document_ids as unknown[]
  )?.length ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md overflow-hidden rounded-[1.8rem] bg-white shadow-2xl">
        <div className="relative bg-[linear-gradient(135deg,#f59e0b,#ef4444)] px-6 py-6 text-white">
          <button
            onClick={onClose}
            className="absolute right-4 top-4 rounded-full bg-white/20 p-1.5 transition hover:bg-white/30"
            aria-label="Đóng"
          >
            <X size={16} />
          </button>
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/20">
            <BellRing size={24} />
          </div>
          <h2 className="mt-4 text-xl font-black">{notification.title}</h2>
        </div>
        <div className="px-6 py-5">
          <p className="text-sm leading-relaxed text-slate-700">
            {notification.body}
          </p>
          <div className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
            ✓ Lịch học tuần đã được cập nhật tự động: {docCount} tài liệu đã được thêm vào lịch trình.
          </div>
          <button
            onClick={onClose}
            className="mt-5 w-full rounded-full bg-[linear-gradient(180deg,#1d4ed8,#0f172a)] py-3 text-sm font-bold text-white shadow-lg transition hover:shadow-xl"
          >
            Xem lịch học
          </button>
        </div>
      </div>
    </div>
  );
}
