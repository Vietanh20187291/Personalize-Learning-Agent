"use client";

import { type ReactNode, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Award,
  BarChart3,
  Calendar,
  ChevronDown,
  History,
  LockKeyhole,
  Minus,
  Sparkles,
  Target,
  Timer,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";

import StudentOrbitAgent from "@/components/StudentOrbitAgent";
import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "@/services/api";

type AssessmentItem = {
  id: number;
  date: string;
  duration: string | number;
  score: number;
  subject: string;
  level?: string;
  trend?: number;
  test_type?: string;
};

type StatsData = {
  avg: number;
  total: number;
  best: number;
};

type EvaluationScores = {
  test_score: number;
  effort_score: number;
  progress_score: number;
  final_score: number;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type StatCardProps = {
  icon: ReactNode;
  label: string;
  value: string | number;
  bg: string;
};

export default function EvaluationPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  const [userId, setUserId] = useState<number | null>(null);
  const [selectedSubject, setSelectedSubject] = useState("");
  const [enrolledSubjects, setEnrolledSubjects] = useState<string[]>([]);
  const [classIdMap, setClassIdMap] = useState<Record<string, number>>({});
  const [loadingSubjects, setLoadingSubjects] = useState(true);
  const [loadingStats, setLoadingStats] = useState(false);
  const [history, setHistory] = useState<AssessmentItem[]>([]);
  const [stats, setStats] = useState<StatsData>({ avg: 0, total: 0, best: 0 });
  const [evalScores, setEvalScores] = useState<EvaluationScores | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Evaluation Agent đã sẵn sàng. Bạn có thể hỏi về thành tích học tập, môn đang yếu, xu hướng tiến bộ hoặc tài liệu nên ôn tập lại.",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);
  const [slowNotice, setSlowNotice] = useState(false);
  const [examples, setExamples] = useState<string[]>([]);

  useEffect(() => {
    const rawId = localStorage.getItem("userId") || localStorage.getItem("user_id");
    const uid = rawId ? Number(rawId) : null;
    if (!uid) {
      setLoadingSubjects(false);
      return;
    }
    setUserId(uid);
  }, []);

  useEffect(() => {
    const fetchEnrolledClasses = async () => {
      if (!userId) return;
      try {
        const res = await axios.get(`${apiBaseUrl}/api/auth/me/${userId}`);
        const classes = Array.isArray(res.data?.enrolled_classes) ? res.data.enrolled_classes : [];

        const subjectList: string[] = [];
        const nextMap: Record<string, number> = {};
        classes.forEach((item: { subject?: string; id?: number }) => {
          if (!item.subject || typeof item.id !== "number") return;
          if (!subjectList.includes(item.subject)) subjectList.push(item.subject);
          nextMap[item.subject] = item.id;
        });

        setEnrolledSubjects(subjectList);
        setClassIdMap(nextMap);
        if (subjectList.length) {
          setSelectedSubject((prev) => prev || subjectList[0]);
        }
      } catch {
        setEnrolledSubjects([]);
      } finally {
        setLoadingSubjects(false);
      }
    };
    void fetchEnrolledClasses();
  }, [apiBaseUrl, userId]);

  useEffect(() => {
    const loadExamples = async () => {
      try {
        const res = await apiClient.get("/api/evaluation/chat/examples", {
          baseURL: apiBaseUrl,
        });
        setExamples(Array.isArray(res.data?.examples) ? res.data.examples : []);
      } catch {
        setExamples([
          "Thành tích học tập của tôi hiện nay thế nào?",
          "Môn nào tôi đang yếu nhất?",
          "Tài liệu nào tôi nên ôn tập lại trước kỳ thi?",
        ]);
      }
    };
    void loadExamples();
  }, [apiBaseUrl]);

  const fetchHistory = async () => {
    if (!userId || !selectedSubject) return;
    setLoadingStats(true);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/stats/learning-stats`, {
        params: {
          user_id: userId,
          subject: selectedSubject,
        },
      });
      const data = Array.isArray(res.data?.history_list) ? res.data.history_list : [];
      setHistory(data);
      setStats({
        avg: Number(res.data?.avgScore || 0),
        total: Number(res.data?.totalTests || 0),
        best: Number(res.data?.bestScore || 0),
      });
    } catch {
      setHistory([]);
      setStats({ avg: 0, total: 0, best: 0 });
    } finally {
      setLoadingStats(false);
    }
  };

  const fetchEvaluationScores = async () => {
    if (!userId || !selectedSubject) return;
    const classId = classIdMap[selectedSubject];
    if (!classId) {
      setEvalScores(null);
      return;
    }

    try {
      const res = await axios.get(`${apiBaseUrl}/api/classroom/members/${classId}`);
      const members = Array.isArray(res.data) ? res.data : [];
      const me = members.find((member: { id?: number }) => member.id === userId);
      if (me && me.final_score !== undefined) {
        setEvalScores({
          test_score: Number(me.test_score || 0),
          effort_score: Number(me.effort_score || 0),
          progress_score: Number(me.progress_score || 0),
          final_score: Number(me.final_score || 0),
        });
      } else {
        setEvalScores(null);
      }
    } catch {
      setEvalScores(null);
    }
  };

  useEffect(() => {
    if (!userId || !selectedSubject) return;
    void fetchHistory();
    void fetchEvaluationScores();
  }, [selectedSubject, userId]);

  const sendEvaluationMessage = async (content: string) => {
    if (!userId || !content.trim()) return;
    const message = content.trim();
    setChatMessages((prev) => [...prev, { role: "user", content: message }]);
    setChatInput("");
    setSending(true);

    try {
      const res = await runLongRequest(
        () =>
          apiClient.post(
            "/api/evaluation/chat",
            {
              user_id: userId,
              subject: null,
              message,
            },
            {
              ...longRequestConfig,
              baseURL: apiBaseUrl,
            }
          ),
        { onSlowStateChange: setSlowNotice, slowDelayMs: 3500 }
      );
      const reply = String(res.data?.reply || "Evaluation Agent đã phản hồi.");
      setChatMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (error: unknown) {
      const fallback = normalizeApiError(error, "Evaluation Agent chưa thể phân tích lúc này.");
      setChatMessages((prev) => [...prev, { role: "assistant", content: `Lỗi: ${fallback}` }]);
    } finally {
      setSending(false);
    }
  };

  const formatDateTime = (value: string) => {
    if (!value) return "N/A";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  };

  const formatDuration = (value: string | number) => {
    if (!value) return "0 giây";
    if (typeof value === "string") return value;
    const numberValue = Number(value);
    const minutes = Math.floor(numberValue / 60);
    const seconds = numberValue % 60;
    if (minutes > 0) return `${minutes} phút ${seconds} giây`;
    return `${seconds} giây`;
  };

  const performanceLabel = useMemo(() => {
    const score = Number(evalScores?.final_score || 0);
    if (score >= 80) return "Xuất sắc. Bạn đang duy trì phong độ rất tốt.";
    if (score >= 50) return "Khá ổn, nhưng vẫn còn dư địa để tăng tốc.";
    return "Cần tập trung ôn tập và cải thiện những môn đang yếu.";
  }, [evalScores]);

  return (
    <div className="page-shell px-4 pb-8 text-slate-800">
      <div className="mx-auto max-w-7xl space-y-6">
        <section className="overflow-hidden rounded-[2.25rem] border border-slate-200 bg-[linear-gradient(135deg,#dbeafe,white_42%,#eef2ff)] shadow-[0_30px_80px_rgba(15,23,42,0.08)]">
          <div className="grid gap-6 px-6 py-7 lg:grid-cols-[1.25fr_0.75fr]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-indigo-800">
                <Sparkles size={13} />
                Tab đánh giá
              </div>
              <h1 className="mt-4 text-2xl font-black tracking-tight text-slate-950">Evaluation Agent và phân tích kết quả học tập</h1>
              <p className="mt-2 max-w-2xl text-[13px] font-medium leading-6 text-slate-600">
                Agent đánh giá nhận lịch sử điểm số, ngày thi và trạng thái tài liệu để phân tích thành tích của bạn, chỉ ra môn đang yếu và gợi ý cách ôn tập tiếp theo.
              </p>
            </div>

            <div className="relative min-w-[250px] self-end">
              <select
                value={selectedSubject}
                onChange={(event) => setSelectedSubject(event.target.value)}
                disabled={enrolledSubjects.length === 0 || loadingSubjects}
                className="h-12 w-full appearance-none rounded-2xl border border-white/70 bg-white/82 px-4 pr-10 text-sm font-bold text-slate-800 outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                {loadingSubjects ? (
                  <option value="">Đang tải...</option>
                ) : enrolledSubjects.length === 0 ? (
                  <option value="">Chưa có môn học</option>
                ) : (
                  enrolledSubjects.map((subject) => (
                    <option key={subject} value={subject}>
                      {subject}
                    </option>
                  ))
                )}
              </select>
              <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            </div>
          </div>
        </section>

        {!loadingSubjects && enrolledSubjects.length === 0 ? (
          <section className="mx-auto flex max-w-3xl flex-col items-center justify-center rounded-[2rem] border border-dashed border-slate-300 bg-white px-6 py-16 text-center shadow-sm">
            <LockKeyhole className="mb-4 h-14 w-14 text-slate-300" />
            <h2 className="text-xl font-black text-slate-700">Chưa có dữ liệu để đánh giá</h2>
            <p className="mt-2 max-w-xl text-sm font-medium text-slate-500">
              Bạn cần tham gia ít nhất một lớp học và làm bài kiểm tra để hệ thống có thể theo dõi năng lực học tập của bạn.
            </p>
          </section>
        ) : (
          <section className="grid gap-6 grid-cols-1">
            <div className="space-y-5">
              {evalScores ? (
                <div className="relative overflow-hidden rounded-[2rem] bg-[linear-gradient(135deg,#0f172a,#312e81,#0f172a)] p-7 text-white shadow-[0_24px_64px_rgba(15,23,42,0.25)]">
                  <Sparkles className="absolute right-5 top-5 h-20 w-20 text-indigo-300/25" />
                  <div className="grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
                    <div className="border-b border-white/10 pb-4 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-6">
                      <p className="text-[10px] font-black uppercase tracking-[0.22em] text-indigo-200">Evaluation score</p>
                      <h2 className="mt-3 text-5xl font-black text-amber-300">
                        {evalScores.final_score}
                        <span className="ml-2 text-lg text-indigo-100">/ 100</span>
                      </h2>
                      <p className="mt-3 text-sm font-medium text-indigo-100">{performanceLabel}</p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <MetricCard label="Học lực" value={evalScores.test_score} accent="text-sky-300" />
                      <MetricCard label="Nỗ lực" value={evalScores.effort_score} accent="text-emerald-300" />
                      <MetricCard label="Tiến bộ" value={evalScores.progress_score} accent="text-fuchsia-300" />
                    </div>
                  </div>
                </div>
              ) : null}

              <div className="grid gap-4 md:grid-cols-3">
                <StatCard icon={<History className="h-5 w-5 text-blue-600" />} label="Tổng số bài thi" value={stats.total} bg="bg-blue-50" />
                <StatCard icon={<BarChart3 className="h-5 w-5 text-indigo-600" />} label="Điểm trung bình" value={`${stats.avg}%`} bg="bg-indigo-50" />
                <StatCard icon={<Award className="h-5 w-5 text-emerald-600" />} label="Thành tích tốt nhất" value={`${stats.best}%`} bg="bg-emerald-50" />
              </div>

              <div className="overflow-hidden rounded-[2rem] border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
                  <h3 className="flex items-center gap-2 text-lg font-black text-slate-900">
                    <Calendar size={16} className="text-slate-400" />
                    Nhật ký làm bài {selectedSubject ? `- ${selectedSubject}` : ""}
                  </h3>
                </div>

                {loadingStats ? (
                  <div className="p-12 text-center text-sm font-semibold text-slate-500">Đang tải dữ liệu phân tích...</div>
                ) : history.length === 0 ? (
                  <div className="flex flex-col items-center p-12 text-center">
                    <div className="mb-4 rounded-2xl bg-slate-50 p-4">
                      <Target className="h-8 w-8 text-slate-300" />
                    </div>
                    <p className="font-bold text-slate-600">Chưa có bài kiểm tra nào.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="min-w-[680px] w-full border-collapse text-left text-sm">
                      <thead>
                        <tr className="border-b border-slate-100 bg-slate-50/80 text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">
                          <th className="p-4">Thời điểm</th>
                          <th className="p-4">Loại bài</th>
                          <th className="p-4">Thời gian</th>
                          <th className="p-4">Cấp độ</th>
                          <th className="p-4">Tiến bộ</th>
                          <th className="p-4 text-right">Điểm số</th>
                        </tr>
                      </thead>
                      <tbody>
                        {history.map((item, index) => (
                          <tr key={item.id || index} className="border-b border-slate-50 transition hover:bg-slate-50/50">
                            <td className="p-4">
                              <div className="flex items-center gap-2 font-medium text-slate-600">
                                <Calendar className="h-3.5 w-3.5 text-slate-400" />
                                {formatDateTime(item.date)}
                              </div>
                            </td>
                            <td className="p-4">
                              <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-black uppercase text-slate-500">
                                {item.test_type === "baseline" ? "Đầu vào" : item.test_type === "final" ? "Cuối kỳ" : "Qua bài"}
                              </span>
                            </td>
                            <td className="p-4">
                              <div className="flex items-center gap-2 font-bold text-slate-700">
                                <Timer className="h-3.5 w-3.5 text-indigo-500" />
                                {formatDuration(item.duration)}
                              </div>
                            </td>
                            <td className="p-4">
                              <span
                                className={`rounded-full border px-2 py-1 text-[10px] font-black uppercase ${
                                  item.level === "Advanced"
                                    ? "border-purple-100 bg-purple-50 text-purple-600"
                                    : item.level === "Intermediate"
                                      ? "border-blue-100 bg-blue-50 text-blue-600"
                                      : "border-slate-200 bg-slate-100 text-slate-500"
                                }`}
                              >
                                {item.level || "Beginner"}
                              </span>
                            </td>
                            <td className="p-4">
                              {index === history.length - 1 ? (
                                <span className="flex items-center gap-1 text-xs font-bold text-slate-400">
                                  <Minus className="h-4 w-4" /> Bài đầu tiên
                                </span>
                              ) : (
                                <div
                                  className={`flex items-center gap-2 font-bold ${
                                    (item.trend || 0) > 0 ? "text-emerald-600" : (item.trend || 0) < 0 ? "text-red-500" : "text-slate-400"
                                  }`}
                                >
                                  {(item.trend || 0) > 0 ? (
                                    <ArrowUpRight className="h-4 w-4" />
                                  ) : (item.trend || 0) < 0 ? (
                                    <ArrowDownRight className="h-4 w-4" />
                                  ) : (
                                    <Minus className="h-4 w-4" />
                                  )}
                                  {(item.trend || 0) > 0
                                    ? `Tăng ${item.trend}đ`
                                    : (item.trend || 0) < 0
                                      ? `Giảm ${Math.abs(item.trend || 0)}đ`
                                      : "Không đổi"}
                                </div>
                              )}
                            </td>
                            <td className="p-4 text-right">
                              <span
                                className={`text-xl font-black ${
                                  item.score >= 80 ? "text-emerald-600" : item.score >= 50 ? "text-indigo-600" : "text-red-500"
                                }`}
                              >
                                {Math.round(item.score)}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </section>
        )}
      </div>

      <StudentOrbitAgent
        userId={userId}
        selectedSubject={selectedSubject}
      />
    </div>
  );
}

function StatCard({ icon, label, value, bg }: StatCardProps) {
  return (
    <div className="flex items-center gap-4 rounded-[1.6rem] border border-slate-200 bg-white p-5 shadow-sm">
      <div className={`rounded-2xl p-3 ${bg}`}>{icon}</div>
      <div>
        <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">{label}</p>
        <p className="text-2xl font-black text-slate-900">{value}</p>
      </div>
    </div>
  );
}

function MetricCard({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-[1.4rem] border border-white/10 bg-white/5 p-4 text-center backdrop-blur">
      <p className="text-[10px] font-black uppercase tracking-[0.16em] text-indigo-200">{label}</p>
      <p className={`mt-2 text-2xl font-black ${accent}`}>{value}</p>
    </div>
  );
}
