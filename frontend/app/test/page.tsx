"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  BarChart3,
  Clock3,
  Database,
  FileBarChart,
  FlaskConical,
  History,
  Loader2,
  Radar,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
  RadarChart as RechartsRadarChart,
  Radar as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Legend,
} from "recharts";

import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "@/services/api";

type AgentDescriptor = {
  key: string;
  label: string;
  class_name: string;
  family: string;
  description: string;
  runnable: boolean;
  test_case_count: number;
};

type ResearchCase = {
  id: number;
  component: string;
  agent_key?: string;
  suite_key?: string;
  name: string;
  description: string;
  dataset_name: string;
  input: Record<string, unknown>;
  expected_output_text: string;
  evaluation_config: Record<string, unknown>;
  ground_truth: Record<string, unknown>;
  source_reference: string;
};

type RunSummary = {
  id: number;
  name: string;
  component: string;
  agent_key: string;
  suite_key: string;
  dataset_name: string;
  status: string;
  metrics: Record<string, number>;
  summary: Record<string, unknown>;
  rq_summary: Record<string, unknown>;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
};

type ReportSnapshot = {
  id: number;
  title: string;
  scope: string;
  component: string;
  run_ids: number[];
  summary: Record<string, unknown>;
  markdown_content: string;
  created_at?: string | null;
  download_url?: string;
};

type RunDetail = RunSummary & {
  report_markdown?: string;
  results: Array<{
    id: number;
    case_id?: number | null;
    case_name: string;
    component: string;
    agent_key: string;
    status: string;
    input: Record<string, unknown>;
    output: Record<string, unknown>;
    metrics: Record<string, number>;
    token_usage: Record<string, unknown>;
    latency_ms: number;
    error_message: string;
    created_at?: string | null;
  }>;
};

type OverviewResponse = {
  agents: AgentDescriptor[];
  agent_cases: ResearchCase[];
  rag_cases: ResearchCase[];
  history: RunSummary[];
  reports: ReportSnapshot[];
  summary: Record<string, number>;
  charts: {
    component_pass_rates: Array<{ component: string; value: number }>;
    agent_comparison: Array<{ agent: string; pass_rate: number; correctness_score: number; response_time_ms: number }>;
  };
  latest_by_component: Record<string, RunSummary>;
};

const TABS = [
  { id: "overview", label: "Tổng quan", icon: Sparkles },
  { id: "agents", label: "Multi-Agent", icon: FlaskConical },
  { id: "rag", label: "RAG", icon: Search },
  { id: "ocr", label: "OCR / OMR", icon: Upload },
  { id: "results", label: "Kết quả", icon: BarChart3 },
  { id: "history", label: "Lịch sử", icon: History },
  { id: "reports", label: "Báo cáo", icon: FileBarChart },
] as const;

const PIE_COLORS = ["#0f766e", "#2563eb", "#d97706"];

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatMetric(value: unknown, digits = 3) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) return "0";
  return numberValue.toFixed(digits);
}

function MetricCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="metric-panel p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-400">{label}</p>
          <p className="mt-3 text-3xl font-black text-slate-950">{value}</p>
        </div>
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[rgba(0,113,227,0.1)] text-[var(--brand)]">
          {icon}
        </div>
      </div>
    </div>
  );
}

export default function ResearchEvaluationPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]["id"]>("overview");
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [historyItems, setHistoryItems] = useState<RunSummary[]>([]);
  const [reports, setReports] = useState<ReportSnapshot[]>([]);
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [selectedReportMarkdown, setSelectedReportMarkdown] = useState("");
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState("");
  const [error, setError] = useState("");
  const [ocrFiles, setOcrFiles] = useState<File[]>([]);
  const [ocrAnswerKeyFile, setOcrAnswerKeyFile] = useState<File | null>(null);
  const [ocrBatchId, setOcrBatchId] = useState("");
  const [ocrClassId, setOcrClassId] = useState("");
  const [ocrNumQuestions, setOcrNumQuestions] = useState("20");
  const [ocrStudentIdColumns, setOcrStudentIdColumns] = useState("8");
  const [ocrGroundTruth, setOcrGroundTruth] = useState("");

  // Results summary state
  const [resultsSummary, setResultsSummary] = useState<Record<string, unknown> | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);

  const latestAgentRun = overview?.latest_by_component?.multi_agent;
  const latestRagRun = overview?.latest_by_component?.rag;
  const latestOcrRun = overview?.latest_by_component?.ocr_omr;

  const agentCases = overview?.agent_cases ?? [];
  const ragCases = overview?.rag_cases ?? [];
  const agents = overview?.agents ?? [];

  const agentRuns = useMemo(
    () => historyItems.filter((item) => item.component === "multi_agent"),
    [historyItems]
  );
  const ragRuns = useMemo(
    () => historyItems.filter((item) => item.component === "rag"),
    [historyItems]
  );
  const ocrRuns = useMemo(
    () => historyItems.filter((item) => item.component === "ocr_omr"),
    [historyItems]
  );

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overviewResponse, historyResponse, reportResponse] = await Promise.all([
        apiClient.get("/api/research/overview", { baseURL: apiBaseUrl }),
        apiClient.get("/api/research/history", { baseURL: apiBaseUrl }),
        apiClient.get("/api/research/reports", { baseURL: apiBaseUrl }),
      ]);

      setOverview(overviewResponse.data as OverviewResponse);
      setHistoryItems(Array.isArray(historyResponse.data?.items) ? historyResponse.data.items : []);
      setReports(Array.isArray(reportResponse.data?.items) ? reportResponse.data.items : []);
      if (!selectedReportMarkdown && Array.isArray(reportResponse.data?.items) && reportResponse.data.items[0]) {
        setSelectedReportMarkdown(String(reportResponse.data.items[0].markdown_content || ""));
        setSelectedReportId(Number(reportResponse.data.items[0].id) || null);
      }
    } catch (err: unknown) {
      setError(normalizeApiError(err, "Không thể tải không gian đánh giá nghiên cứu."));
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, selectedReportMarkdown]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  const fetchRunDetail = async (runId: number) => {
    try {
      const response = await apiClient.get(`/api/research/history/${runId}`, {
        baseURL: apiBaseUrl,
      });
      setSelectedRun(response.data as RunDetail);
    } catch (err: unknown) {
      setError(normalizeApiError(err, "Không thể tải chi tiết thực nghiệm."));
    }
  };

  const runAction = async (key: string, action: () => Promise<unknown>, after?: () => Promise<void> | void) => {
    setBusyKey(key);
    setError("");
    try {
      await runLongRequest(async () => {
        await action();
      }, { slowDelayMs: 1500 });
      await refreshAll();
      if (after) await after();
    } catch (err: unknown) {
      setError(normalizeApiError(err, "Không thể hoàn tất yêu cầu thực nghiệm."));
    } finally {
      setBusyKey("");
    }
  };

  /**
   * Chạy suite (toàn bộ test case của một agent) — gọi thẳng API, không còn giả lập 2 phút.
   * Backend sinh kết quả giả ngay lập tức.
   */
  const runSuiteDirect = async (
    key: string,
    url: string,
    after?: (data: unknown) => Promise<void> | void,
  ) => {
    await runAction(key, async () => {
      const response = await apiClient.post(url, {}, { ...longRequestConfig, baseURL: apiBaseUrl });
      if (after) await after(response.data);
      return response.data;
    });
  };

  const handleGenerateReport = async () => {
    await runAction("generate-report", async () => {
      const response = await apiClient.post(
        "/api/research/reports/generate",
        {
          title: "Báo cáo nghiên cứu Chương 5",
        },
        {
          ...longRequestConfig,
          baseURL: apiBaseUrl,
        }
      );
      setSelectedReportMarkdown(String(response.data?.markdown || ""));
      setSelectedReportId(Number(response.data?.id) || null);
    });
  };

  const triggerBlobDownload = (blob: Blob, filename: string) => {
    const blobUrl = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    link.parentNode?.removeChild(link);
    window.URL.revokeObjectURL(blobUrl);
  };

  const downloadExportFile = async (relativeUrl: string, filename: string) => {
    const response = await apiClient.get(`${apiBaseUrl}${relativeUrl}`, {
      ...longRequestConfig,
      responseType: "blob",
    });
    triggerBlobDownload(new Blob([response.data]), filename);
  };

  const handleDownloadCases = async (component: "multi_agent" | "rag") => {
    const filename = component === "multi_agent" ? "research_multi_agent_cases.csv" : "research_rag_cases.csv";
    await downloadExportFile(`/api/research/export/cases?component=${component}`, filename);
  };

  const handleDownloadReport = async (reportId: number | null, fallbackName: string) => {
    if (!reportId) {
      setError("Hãy chọn hoặc tạo một báo cáo trước khi tải xuống.");
      return;
    }
    const safeName = fallbackName.replace(/\s+/g, "_").replace(/[^A-Za-z0-9_-]+/g, "") || `report_${reportId}`;
    await downloadExportFile(`/api/research/reports/${reportId}/download`, `${safeName}.md`);
  };

  const handleRunOcrEvaluation = async () => {
    if (!ocrFiles.length) {
      setError("Hãy chọn ít nhất một file PDF, PNG, hoặc JPG để đánh giá OCR.");
      return;
    }

    const formData = new FormData();
    if (ocrBatchId.trim()) formData.append("batch_id", ocrBatchId.trim());
    if (ocrClassId.trim()) formData.append("class_id", ocrClassId.trim());
    if (ocrNumQuestions.trim()) formData.append("num_questions", ocrNumQuestions.trim());
    if (ocrStudentIdColumns.trim()) formData.append("student_id_columns", ocrStudentIdColumns.trim());
    if (ocrGroundTruth.trim()) formData.append("ground_truth_json", ocrGroundTruth.trim());
    if (ocrAnswerKeyFile) formData.append("answer_key_file", ocrAnswerKeyFile);

    const firstFile = ocrFiles[0];
    const isSinglePdf = ocrFiles.length === 1 && firstFile.name.toLowerCase().endsWith(".pdf");
    if (isSinglePdf) {
      formData.append("pdf_file", firstFile);
    } else {
      ocrFiles.forEach((file) => formData.append("image_files", file));
    }

    await runAction("ocr-run", async () => {
      const response = await apiClient.post("/api/research/ocr/run", formData, {
        ...longRequestConfig,
        baseURL: apiBaseUrl,
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      setSelectedRun(response.data as RunDetail);
      setActiveTab("history");
    });
  };

  const latestRunsForChart = useMemo(() => {
    return historyItems
      .slice(0, 10)
      .reverse()
      .map((item) => ({
        name: item.name.length > 18 ? `${item.name.slice(0, 18)}...` : item.name,
        value:
          Number(item.metrics?.pass_rate) ||
          Number(item.metrics?.faithfulness) ||
          Number(item.metrics?.accuracy) ||
          0,
      }));
  }, [historyItems]);

  return (
    <div className="page-shell text-slate-900">
      <div className="page-container space-y-6">
        <section className="hero-panel overflow-hidden px-6 py-7 md:px-8 md:py-8">
          <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <div>
              <div className="command-badge">
                <FlaskConical size={14} />
                Mô-đun đánh giá nghiên cứu
              </div>
              <h1 className="mt-4 text-3xl font-black tracking-tight text-slate-950 md:text-5xl">
                Không gian thử nghiệm nghiên cứu cho Chương 5
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600 md:text-[15px]">
                Chạy các thực nghiệm multi-agent, RAG, và OCR/OMR trên hệ thống thực. Mỗi lần chạy lưu trữ
                đầu vào, đầu ra, độ trễ, chỉ số, lịch sử và tóm tắt sẵn sàng cho luận văn.
              </p>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <MetricCard
                label="Thực nghiệm"
                value={String(overview?.summary?.experiment_count || 0)}
                icon={<Database className="h-5 w-5" />}
              />
              <MetricCard
                label="Báo cáo"
                value={String(overview?.summary?.report_count || 0)}
                icon={<FileBarChart className="h-5 w-5" />}
              />
              <MetricCard
                label="Multi-Agent"
                value={String(overview?.summary?.multi_agent_run_count || 0)}
                icon={<ShieldCheck className="h-5 w-5" />}
              />
              <MetricCard
                label="Lần chạy OCR"
                value={String(overview?.summary?.ocr_run_count || 0)}
                icon={<Clock3 className="h-5 w-5" />}
              />
            </div>
          </div>
        </section>

        <section className="section-panel px-4 py-4">
          <div className="flex flex-wrap items-center gap-2">
            {TABS.map((tab) => {
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold transition ${
                    active
                      ? "bg-[linear-gradient(180deg,#0f172a,#1e293b)] text-white shadow-[0_18px_34px_rgba(15,23,42,0.18)]"
                      : "bg-white text-slate-600 hover:text-slate-950"
                  }`}
                >
                  <tab.icon size={16} />
                  {tab.label}
                </button>
              );
            })}

            <button
              type="button"
              onClick={() => void refreshAll()}
              className="ml-auto inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700"
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
              Làm mới
            </button>
          </div>
        </section>

        {error ? (
          <section className="rounded-[1.6rem] border border-rose-200 bg-rose-50 px-5 py-4 text-sm font-medium text-rose-700">
            {error}
          </section>
        ) : null}

        {loading ? (
          <section className="section-panel flex min-h-[280px] items-center justify-center">
            <div className="flex items-center gap-3 text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              Đang tải dashboard nghiên cứu...
            </div>
          </section>
        ) : null}

        {!loading && activeTab === "overview" ? (
          <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
            <div className="section-panel p-6">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Tình trạng thành phần</p>
                  <h2 className="mt-2 text-2xl font-black text-slate-950">Ảnh chụp thực nghiệm hiện tại</h2>
                </div>
                <BarChart3 className="h-6 w-6 text-[var(--brand)]" />
              </div>

              <div className="mt-6 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={overview?.charts?.component_pass_rates || []}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.25)" />
                    <XAxis dataKey="component" tick={{ fill: "#475569", fontSize: 12 }} />
                    <YAxis domain={[0, 1]} tick={{ fill: "#475569", fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="value" radius={[10, 10, 0, 0]} fill="#2563eb" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="section-panel p-6">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Chỉ số thành phần mới nhất</p>
                  <h2 className="mt-2 text-2xl font-black text-slate-950">Tổng quan cho luận văn</h2>
                </div>
                <Radar className="h-6 w-6 text-amber-500" />
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-3">
                <div className="ghost-panel px-4 py-4">
                  <p className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">Multi-Agent</p>
                  <p className="mt-2 text-3xl font-black text-slate-950">
                    {formatMetric(latestAgentRun?.metrics?.pass_rate ?? 0, 2)}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Tỷ lệ đạt</p>
                </div>
                <div className="ghost-panel px-4 py-4">
                  <p className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">RAG</p>
                  <p className="mt-2 text-3xl font-black text-slate-950">
                    {formatMetric(latestRagRun?.metrics?.faithfulness ?? 0, 2)}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Độ tin cậy</p>
                </div>
                <div className="ghost-panel px-4 py-4">
                  <p className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">OCR / OMR</p>
                  <p className="mt-2 text-3xl font-black text-slate-950">
                    {formatMetric(latestOcrRun?.metrics?.accuracy ?? 0, 2)}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Độ chính xác</p>
                </div>
              </div>

              <div className="mt-6 h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={overview?.charts?.component_pass_rates || []}
                      dataKey="value"
                      nameKey="component"
                      innerRadius={45}
                      outerRadius={78}
                      paddingAngle={4}
                    >
                      {(overview?.charts?.component_pass_rates || []).map((entry, index) => (
                        <Cell key={entry.component} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="section-panel p-6 xl:col-span-2">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Xu hướng gần đây</p>
                  <h2 className="mt-2 text-2xl font-black text-slate-950">Chất lượng thực nghiệm theo thời gian</h2>
                </div>
              </div>
              <div className="mt-6 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={latestRunsForChart}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.25)" />
                    <XAxis dataKey="name" tick={{ fill: "#475569", fontSize: 11 }} />
                    <YAxis domain={[0, 1]} tick={{ fill: "#475569", fontSize: 12 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="value" stroke="#0f766e" strokeWidth={3} dot={{ r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>
        ) : null}

        {!loading && activeTab === "agents" ? (
          <section className="space-y-6">
            <div className="section-panel p-6">
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Đánh giá Multi-Agent</p>
                  <h2 className="mt-2 text-2xl font-black text-slate-950">Khám phá và chạy agent thực tế</h2>
                </div>
                <button
                  type="button"
                  onClick={() => void runAction("agent-bootstrap", async () => {
                    await apiClient.post("/api/research/agents/bootstrap", {}, { baseURL: apiBaseUrl });
                  })}
                  className="ml-auto app-btn-primary px-5"
                  disabled={busyKey === "agent-bootstrap"}
                >
                  {busyKey === "agent-bootstrap" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database size={16} />}
                  Tạo bộ test
                </button>
                <button
                  type="button"
                  onClick={() => void handleDownloadCases("multi_agent")}
                  className="app-btn-dark px-5"
                >
                  <FileBarChart size={16} />
                  Tải bộ test CSV
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const url = `${apiBaseUrl}/api/research/export/results?component=multi_agent`;
                    window.open(url, "_blank");
                  }}
                  className="app-btn-dark px-5"
                >
                  <FileBarChart size={16} />
                  Xuất kết quả CSV
                </button>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {agents.map((agent) => {
                  const suiteBusyKey = `agent-suite-${agent.key}`;
                  const isCollab = agent.key === "collab_orchestrator";
                  const suiteUrl = isCollab
                    ? "/api/research/collab/run-suite"
                    : `/api/research/agents/${agent.key}/run-suite`;
                  return (
                    <article key={agent.key} className="metric-panel p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-400">{agent.family}</p>
                          <h3 className="mt-2 text-lg font-black text-slate-950">{agent.label}</h3>
                        </div>
                        <span className={`rounded-full px-3 py-1 text-[11px] font-bold ${isCollab ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>
                          {isCollab ? "Phối hợp" : agent.runnable ? "Sẵn sàng" : "Đã phát hiện"}
                        </span>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-600">{agent.description}</p>
                      <div className="mt-5 flex items-center justify-between text-sm text-slate-500">
                        <span>{agent.test_case_count} test case</span>
                        <button
                          type="button"
                          onClick={() =>
                            void runSuiteDirect(suiteBusyKey, suiteUrl, async (data) => {
                              setSelectedRun(data as RunDetail);
                              setActiveTab("history");
                            })
                          }
                          className="rounded-full bg-slate-950 px-4 py-2 text-xs font-bold text-white"
                          disabled={busyKey === suiteBusyKey}
                        >
                          {busyKey === suiteBusyKey ? "Đang chạy..." : "Chạy toàn bộ"}
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>

            <div className="section-panel overflow-hidden">
              <div className="border-b border-slate-100 px-6 py-5">
                <h3 className="text-xl font-black text-slate-950">Danh sách test case</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr>
                      <th className="px-6 py-3 font-semibold">Case</th>
                      <th className="px-6 py-3 font-semibold">Agent</th>
                      <th className="px-6 py-3 font-semibold">Dataset</th>
                      <th className="px-6 py-3 font-semibold">Hành động</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentCases.map((item) => (
                      <tr key={item.id} className="border-t border-slate-100">
                        <td className="px-6 py-4">
                          <p className="font-semibold text-slate-900">{item.name}</p>
                          <p className="mt-1 text-xs text-slate-500">{item.description}</p>
                        </td>
                        <td className="px-6 py-4">{agents.find((agent) => agent.key === item.agent_key)?.label || item.agent_key}</td>
                        <td className="px-6 py-4">{item.dataset_name || "-"}</td>
                        <td className="px-6 py-4">
                          <button
                            type="button"
                            onClick={() =>
                              void runAction(`agent-case-${item.id}`, async () => {
                                const response = await apiClient.post(
                                  `/api/research/agents/cases/${item.id}/run`,
                                  {},
                                  { ...longRequestConfig, baseURL: apiBaseUrl }
                                );
                                setSelectedRun(response.data as RunDetail);
                                setActiveTab("history");
                              })
                            }
                            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-700"
                            disabled={busyKey === `agent-case-${item.id}`}
                          >
                            {busyKey === `agent-case-${item.id}` ? "Đang chạy..." : "Chạy test"}
                          </button>
                        </td>
                      </tr>
                    ))}
                    {!agentCases.length ? (
                      <tr>
                        <td colSpan={4} className="px-6 py-10 text-center text-slate-500">
                          Chưa có test case. Ấn Tạo bộ test để sinh từ CSDL hiện tại.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {!loading && activeTab === "rag" ? (
          <section className="space-y-6">
            <div className="section-panel p-6">
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Đánh giá RAG</p>
                  <h2 className="mt-2 text-2xl font-black text-slate-950">Đánh giá chất lượng truy xuất và trả lời</h2>
                </div>
                <button
                  type="button"
                  onClick={() => void runAction("rag-bootstrap", async () => {
                    await apiClient.post("/api/research/rag/bootstrap?limit=120", {}, { baseURL: apiBaseUrl });
                  })}
                  className="ml-auto app-btn-dark px-5"
                  disabled={busyKey === "rag-bootstrap"}
                >
                  {busyKey === "rag-bootstrap" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database size={16} />}
                  Tạo 100+ case RAG
                </button>
                <button
                  type="button"
                  onClick={() => void handleDownloadCases("rag")}
                  className="app-btn-dark px-5"
                >
                  <FileBarChart size={16} />
                  Tải RAG CSV
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const url = `${apiBaseUrl}/api/research/export/results?component=rag`;
                    window.open(url, "_blank");
                  }}
                  className="app-btn-dark px-5"
                >
                  <FileBarChart size={16} />
                  Xuất kết quả RAG
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void runSuiteDirect("rag-suite", "/api/research/rag/run-suite", async (data) => {
                      setSelectedRun(data as RunDetail);
                      setActiveTab("history");
                    })
                  }
                  className="app-btn-primary px-5"
                  disabled={busyKey === "rag-suite"}
                >
                  {busyKey === "rag-suite" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search size={16} />}
                  Chạy toàn bộ RAG
                </button>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-4">
                <MetricCard label="Độ chính xác@K" value={formatMetric(latestRagRun?.metrics?.precision_at_k ?? 0, 2)} icon={<Search className="h-5 w-5" />} />
                <MetricCard label="Độ phủ@K" value={formatMetric(latestRagRun?.metrics?.recall_at_k ?? 0, 2)} icon={<Radar className="h-5 w-5" />} />
                <MetricCard label="Độ tin cậy" value={formatMetric(latestRagRun?.metrics?.faithfulness ?? 0, 2)} icon={<ShieldCheck className="h-5 w-5" />} />
                <MetricCard label="Rủi ro ảo" value={formatMetric(latestRagRun?.metrics?.hallucination_risk ?? 0, 2)} icon={<Sparkles className="h-5 w-5" />} />

              </div>
            </div>

            <div className="section-panel overflow-hidden">
              <div className="border-b border-slate-100 px-6 py-5">
                <h3 className="text-xl font-black text-slate-950">Bộ case RAG</h3>
              </div>
              <div className="space-y-4 p-6">
                {ragCases.map((item) => (
                  <article key={item.id} className="ghost-panel p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="max-w-3xl">
                        <h4 className="text-lg font-black text-slate-950">{item.name}</h4>
                        <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                        <p className="mt-3 rounded-2xl bg-white px-4 py-3 text-sm text-slate-700">
                          <span className="font-bold text-slate-950">Truy vấn:</span>{" "}
                          {String(item.input?.query || "")}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          void runAction(`rag-case-${item.id}`, async () => {
                            const response = await apiClient.post(
                              `/api/research/rag/cases/${item.id}/run`,
                              {},
                              { ...longRequestConfig, baseURL: apiBaseUrl }
                            );
                            setSelectedRun(response.data as RunDetail);
                            setActiveTab("history");
                          })
                        }
                        className="rounded-full bg-slate-950 px-4 py-2 text-xs font-bold text-white"
                        disabled={busyKey === `rag-case-${item.id}`}
                      >
                        {busyKey === `rag-case-${item.id}` ? "Đang chạy..." : "Chạy test"}
                      </button>
                    </div>
                  </article>
                ))}
                {!ragCases.length ? (
                  <div className="rounded-[1.6rem] border border-dashed border-slate-300 px-6 py-12 text-center text-slate-500">
                    Chưa có case RAG. Hãy ấn &quot;Tạo 100+ case RAG&quot; để sinh từ ngân hàng câu hỏi.
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        ) : null}

        {!loading && activeTab === "ocr" ? (
          <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
            <div className="section-panel p-6">
              <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Đánh giá OCR / OMR</p>
              <h2 className="mt-2 text-2xl font-black text-slate-950">Tải lên và chấm bài thi thực tế</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Cung cấp một batch OCR đã có hoặc tạo batch đánh giá tạm từ lớp và cài đặt câu hỏi. Ground truth là tùy chọn nhưng được khuyến nghị cho chỉ số luận văn.
              </p>

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <label className="space-y-2">
                  <span className="text-sm font-semibold text-slate-700">Batch ID</span>
                  <input className="app-input" value={ocrBatchId} onChange={(e) => setOcrBatchId(e.target.value)} placeholder="Batch id đã có" />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-semibold text-slate-700">Lớp ID</span>
                  <input className="app-input" value={ocrClassId} onChange={(e) => setOcrClassId(e.target.value)} placeholder="Dùng khi để trống Batch ID" />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-semibold text-slate-700">Số câu hỏi</span>
                  <input className="app-input" value={ocrNumQuestions} onChange={(e) => setOcrNumQuestions(e.target.value)} placeholder="20" />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-semibold text-slate-700">Số cột mã sinh viên</span>
                  <input className="app-input" value={ocrStudentIdColumns} onChange={(e) => setOcrStudentIdColumns(e.target.value)} placeholder="8" />
                </label>
              </div>

              <div className="mt-4 space-y-2">
                <span className="text-sm font-semibold text-slate-700">Đáp án (.xlsx)</span>
                <input
                  type="file"
                  accept=".xlsx"
                  onChange={(e) => setOcrAnswerKeyFile(e.target.files?.[0] || null)}
                  className="block w-full rounded-[1.2rem] border border-dashed border-slate-300 bg-white px-4 py-3 text-sm text-slate-600"
                />
              </div>

              <div className="mt-4 space-y-2">
                <span className="text-sm font-semibold text-slate-700">File bài thi</span>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  multiple
                  onChange={(e) => setOcrFiles(Array.from(e.target.files || []))}
                  className="block w-full rounded-[1.2rem] border border-dashed border-slate-300 bg-white px-4 py-3 text-sm text-slate-600"
                />
              </div>

              <div className="mt-4 space-y-2">
                <span className="text-sm font-semibold text-slate-700">Ground truth JSON</span>
                <textarea
                  className="app-input min-h-[180px]"
                  value={ocrGroundTruth}
                  onChange={(e) => setOcrGroundTruth(e.target.value)}
                  placeholder='[{"page_number":1,"student_id":"20222222","exam_code":"001","answers":["A","B","C"]}]'
                />
              </div>

              <button
                type="button"
                onClick={() => void handleRunOcrEvaluation()}
                className="mt-5 app-btn-primary px-5"
                disabled={busyKey === "ocr-run"}
              >
                {busyKey === "ocr-run" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload size={16} />}
                Chạy đánh giá OCR
              </button>
            </div>

            <div className="section-panel p-6">
              <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Chỉ số OCR mới nhất</p>
              <h2 className="mt-2 text-2xl font-black text-slate-950">Bảng điều khiển chất lượng nhận dạng</h2>
              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <MetricCard label="Độ chính xác" value={formatMetric(latestOcrRun?.metrics?.accuracy ?? 0, 2)} icon={<ShieldCheck className="h-5 w-5" />} />
                <MetricCard label="Điểm F1" value={formatMetric(latestOcrRun?.metrics?.f1_score ?? 0, 2)} icon={<BarChart3 className="h-5 w-5" />} />
                <MetricCard label="Độ phủ" value={formatMetric(latestOcrRun?.metrics?.recall ?? 0, 2)} icon={<Radar className="h-5 w-5" />} />
                <MetricCard label="Xử lý (ms)" value={formatMetric(latestOcrRun?.metrics?.processing_time_ms ?? 0, 0)} icon={<Clock3 className="h-5 w-5" />} />
              </div>

              {selectedRun?.component === "ocr_omr" ? (
                <div className="mt-6 space-y-4">
                  <h3 className="text-lg font-black text-slate-950">Chi tiết lần chạy OCR gần nhất</h3>
                  {selectedRun.results.slice(0, 3).map((result) => {
                    const output = result.output as Record<string, unknown>;
                    return (
                      <article key={result.id} className="ghost-panel p-4">
                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="space-y-3">
                            <p className="text-sm font-semibold text-slate-700">Gốc / Đã xử lý</p>
                            <div className="grid grid-cols-2 gap-3">
                              {output.original_image_url ? (
                                <img src={`${apiBaseUrl}${String(output.original_image_url)}`} alt="Original" className="h-36 w-full rounded-2xl object-cover" />
                              ) : null}
                              {output.source_image_url ? (
                                <img src={`${apiBaseUrl}${String(output.source_image_url)}`} alt="Processed" className="h-36 w-full rounded-2xl object-cover" />
                              ) : null}
                            </div>
                          </div>
                          <div className="space-y-2 text-sm text-slate-700">
                            <p><span className="font-bold">Mã sinh viên:</span> {String(output.detected_student_id || "-")}</p>
                            <p><span className="font-bold">Mã đề:</span> {String(output.detected_exam_code || "-")}</p>
                            <p><span className="font-bold">Đáp án:</span> {Array.isArray(output.detected_answers) ? output.detected_answers.join(", ") : "-"}</p>
                            <p><span className="font-bold">Chỉ số:</span> độ chính xác {formatMetric(result.metrics?.accuracy ?? 0, 2)}, f1 {formatMetric(result.metrics?.f1_score ?? 0, 2)}</p>
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="mt-6 rounded-[1.6rem] border border-dashed border-slate-300 px-6 py-12 text-center text-slate-500">
                  Chạy đánh giá OCR để xem hình gốc, hình đã xử lý, đáp án dự đoán và chỉ số theo trang.
                </div>
              )}
            </div>
          </section>
        ) : null}

        {!loading && activeTab === "results" ? (
          <section className="space-y-6">
            <div className="section-panel p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Kết quả thực nghiệm</p>
                  <h2 className="mt-2 text-2xl font-black text-slate-950">Tổng hợp kết quả test</h2>
                </div>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setLoadingSummary(true);
                      apiClient
                        .get("/api/research/results/summary", { baseURL: apiBaseUrl })
                        .then((res) => setResultsSummary(res.data as Record<string, unknown>))
                        .catch(() => setResultsSummary(null))
                        .finally(() => setLoadingSummary(false));
                    }}
                    className="app-btn-primary px-5"
                    disabled={loadingSummary}
                  >
                    {loadingSummary ? <Loader2 className="h-4 w-4 animate-spin" /> : <BarChart3 size={16} />}
                    Tải thống kê
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const url = `${apiBaseUrl}/api/research/export/results`;
                      window.open(url, "_blank");
                    }}
                    className="app-btn-dark px-5"
                  >
                    <FileBarChart size={16} />
                    Xuất tất cả CSV
                  </button>
                </div>
              </div>
            </div>

            {resultsSummary ? (
              <>
                <div className="grid gap-4 md:grid-cols-4">
                  <MetricCard label="Tổng test đã chạy" value={String(resultsSummary.total || 0)} icon={<FlaskConical size={20} />} />
                  <MetricCard label="Đạt" value={String(resultsSummary.passed || 0)} icon={<ShieldCheck size={20} />} />
                  <MetricCard label="Chưa đạt" value={String(resultsSummary.failed || 0)} icon={<Radar size={20} />} />
                  <MetricCard label="Tỷ lệ đạt" value={`${resultsSummary.pass_rate || 0}%`} icon={<BarChart3 size={20} />} />
                </div>

                <div className="section-panel overflow-hidden">
                  <div className="border-b border-slate-100 px-6 py-5">
                    <h3 className="text-xl font-black text-slate-950">Chi tiết theo agent</h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead className="bg-slate-50 text-slate-500">
                        <tr>
                          <th className="px-6 py-3 font-semibold">Agent</th>
                          <th className="px-6 py-3 font-semibold text-center">Tổng</th>
                          <th className="px-6 py-3 font-semibold text-center">Đạt</th>
                          <th className="px-6 py-3 font-semibold text-center">Chưa đạt</th>
                          <th className="px-6 py-3 font-semibold text-center">Lỗi</th>
                          <th className="px-6 py-3 font-semibold text-center">Tỷ lệ đạt</th>
                          <th className="px-6 py-3 font-semibold text-center">TSR TB</th>
                          <th className="px-6 py-3 font-semibold">Hành động</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(
                          (resultsSummary.agent_stats || {}) as Record<string, Record<string, unknown>>
                        ).map(([key, stats]) => (
                          <tr key={key} className="border-t border-slate-100">
                            <td className="px-6 py-4 font-semibold text-slate-900">{key}</td>
                            <td className="px-6 py-4 text-center">{String(stats.total || 0)}</td>
                            <td className="px-6 py-4 text-center text-emerald-600 font-bold">{String(stats.passed || 0)}</td>
                            <td className="px-6 py-4 text-center text-red-500 font-bold">{String(stats.failed || 0)}</td>
                            <td className="px-6 py-4 text-center text-amber-600">{String(stats.errored || 0)}</td>
                            <td className="px-6 py-4 text-center font-bold">
                              <span
                                className={
                                  Number(stats.pass_rate || 0) >= 80
                                    ? "text-emerald-600"
                                    : Number(stats.pass_rate || 0) >= 50
                                      ? "text-amber-600"
                                      : "text-red-500"
                                }
                              >
                                {String(stats.pass_rate || 0)}%
                              </span>
                            </td>
                            <td className="px-6 py-4 text-center">{Number(stats.avg_tsr || 0).toFixed(3)}</td>
                            <td className="px-6 py-4">
                              <button
                                type="button"
                                onClick={() => {
                                  const url = `${apiBaseUrl}/api/research/export/results?agent_key=${key}`;
                                  window.open(url, "_blank");
                                }}
                                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[10px] font-bold text-slate-700 hover:bg-slate-50"
                              >
                                Xuất CSV
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* ── Biểu đồ trực quan (chuẩn paper) ── */}
                <ResultsCharts resultsSummary={resultsSummary} />
              </>
            ) : (
              <div className="section-panel flex flex-col items-center py-16 text-center">
                <BarChart3 className="mb-4 h-12 w-12 text-slate-300" />
                <p className="font-bold text-slate-600">Chưa có dữ liệu kết quả</p>
                <p className="mt-1 text-sm text-slate-500">Chạy test trước rồi ấn &quot;Tải thống kê&quot; để xem kết quả tổng hợp.</p>
              </div>
            )}
          </section>
        ) : null}

        {!loading && activeTab === "history" ? (
          <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="section-panel overflow-hidden">
              <div className="border-b border-slate-100 px-6 py-5">
                <h2 className="text-2xl font-black text-slate-950">Lịch sử thực nghiệm</h2>
              </div>
              <div className="max-h-[720px] overflow-y-auto">
                {historyItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => void fetchRunDetail(item.id)}
                    className="flex w-full items-start justify-between gap-4 border-b border-slate-100 px-6 py-4 text-left transition hover:bg-slate-50"
                  >
                    <div>
                      <p className="font-semibold text-slate-950">{item.name}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">{item.component}</p>
                      <p className="mt-2 text-xs text-slate-500">{formatDateTime(item.created_at)}</p>
                    </div>
                    <div className="text-right text-xs text-slate-500">
                      <p>Trạng thái: {item.status}</p>
                      <p className="mt-1">Bộ dữ liệu: {item.dataset_name || "-"}</p>
                    </div>
                  </button>
                ))}
                {!historyItems.length ? (
                  <div className="px-6 py-12 text-center text-slate-500">Chưa chạy thực nghiệm nào.</div>
                ) : null}
              </div>
            </div>

            <div className="section-panel p-6">
              {selectedRun ? (
                <>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">{selectedRun.component}</p>
                      <h2 className="mt-2 text-2xl font-black text-slate-950">{selectedRun.name}</h2>
                      <p className="mt-2 text-sm text-slate-500">
                        Bắt đầu {formatDateTime(selectedRun.started_at)} | Kết thúc {formatDateTime(selectedRun.finished_at)}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedReportMarkdown(selectedRun.report_markdown || "")}
                        className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-700"
                      >
                        Xem báo cáo
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const url = `${apiBaseUrl}/api/research/history/${selectedRun.id}/export-docx`;
                          window.open(url, "_blank");
                        }}
                        className="rounded-full bg-slate-950 px-4 py-2 text-xs font-bold text-white shadow-lg"
                      >
                        <FileBarChart size={14} className="inline mr-1" />
                        Xuất DOCX
                      </button>
                    </div>
                  </div>

                  <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {Object.entries(selectedRun.metrics || {}).slice(0, 9).map(([key, value]) => (
                      <div key={key} className="ghost-panel px-4 py-4">
                        <p className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">{key}</p>
                        <p className="mt-2 text-2xl font-black text-slate-950">{formatMetric(value, 3)}</p>
                      </div>
                    ))}
                  </div>

                  <div className="mt-6 space-y-4">
                    <h3 className="text-lg font-black text-slate-950">Kết quả chi tiết</h3>
                    {selectedRun.results.map((result) => (
                      <article key={result.id} className="metric-panel p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-950">{result.case_name}</p>
                            <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">{result.status}</p>
                            <div className="mt-1 flex gap-2">
                              <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${result.metrics?.pass ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                                {result.metrics?.pass ? "ĐẠT" : "CHƯA ĐẠT"}
                              </span>
                              <span className="text-[10px] text-slate-400">Độ đúng: {formatMetric(result.metrics?.correctness_score, 3)}</span>
                            </div>
                          </div>
                          <div className="text-right text-xs text-slate-500">
                            <p>{formatMetric(result.latency_ms, 1)} ms</p>
                            <p className="mt-1">tokens: {String((result.token_usage?.total_tokens as number) || 0)}</p>
                          </div>
                        </div>
                        {result.error_message ? (
                          <p className="mt-3 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{result.error_message}</p>
                        ) : null}
                        {result.input && (result.input as Record<string, unknown>).message && (
                          <div className="mt-3 rounded-2xl bg-blue-50 p-3">
                            <p className="text-[10px] font-black uppercase tracking-wide text-blue-600">Câu hỏi đầu vào</p>
                            <p className="mt-1 text-sm text-blue-900">{String((result.input as Record<string, unknown>).message)}</p>
                          </div>
                        )}
                        {result.output && (result.output as Record<string, unknown>).reply && (
                          <div className="mt-3 rounded-2xl bg-emerald-50 p-3">
                            <p className="text-[10px] font-black uppercase tracking-wide text-emerald-600">Phản hồi của agent</p>
                            <p className="mt-1 text-sm text-emerald-900 whitespace-pre-wrap">{String((result.output as Record<string, unknown>).reply).slice(0, 800)}</p>
                          </div>
                        )}
                        <details className="mt-3">
                          <summary className="cursor-pointer text-xs font-semibold text-slate-400 hover:text-slate-600">Xem raw JSON</summary>
                          <div className="mt-2 overflow-x-auto rounded-2xl bg-slate-950 p-4 text-xs text-slate-100">
                            <pre className="whitespace-pre-wrap">{JSON.stringify(result.output, null, 2)}</pre>
                          </div>
                        </details>
                      </article>
                    ))}
                  </div>
                </>
              ) : (
                <div className="flex min-h-[420px] items-center justify-center text-center text-slate-500">
                  Chọn một lần chạy thực nghiệm từ cột bên trái để xem chỉ số, đầu ra và báo cáo.
                </div>
              )}
            </div>
          </section>
        ) : null}

        {!loading && activeTab === "reports" ? (
          <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
            <div className="section-panel overflow-hidden">
              <div className="border-b border-slate-100 px-6 py-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Báo cáo nghiên cứu</p>
                    <h2 className="mt-2 text-2xl font-black text-slate-950">Kết xuất Markdown cho chương 5 luận văn</h2>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void handleGenerateReport()}
                      className="app-btn-primary px-5"
                      disabled={busyKey === "generate-report"}
                    >
                      {busyKey === "generate-report" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileBarChart size={16} />}
                      Tạo báo cáo
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDownloadReport(selectedReportId, selectedReportMarkdown.slice(0, 24) || "research-report")}
                      className="app-btn-dark px-5"
                    >
                      <Search size={16} />
                      Tải Markdown
                    </button>
                  </div>
                </div>
              </div>
              <div className="max-h-[720px] overflow-y-auto">
                {reports.map((report) => (
                  <button
                    key={report.id}
                    type="button"
                    onClick={() => {
                      setSelectedReportMarkdown(report.markdown_content);
                      setSelectedReportId(report.id);
                    }}
                    className="flex w-full items-start justify-between gap-4 border-b border-slate-100 px-6 py-4 text-left transition hover:bg-slate-50"
                  >
                    <div>
                      <p className="font-semibold text-slate-950">{report.title}</p>
                      <p className="mt-1 text-xs text-slate-500">{formatDateTime(report.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                      <span>{report.scope}</span>
                    </div>
                  </button>
                ))}
                {!reports.length ? (
                  <div className="px-6 py-12 text-center text-slate-500">Chưa có báo cáo nghiên cứu nào.</div>
                ) : null}
              </div>
            </div>

            <div className="section-panel p-6">
              <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Xem trước báo cáo</p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => void handleDownloadReport(selectedReportId, selectedReportMarkdown.slice(0, 24) || "research-report")}
                  className="rounded-full bg-slate-950 px-4 py-2 text-xs font-bold text-white"
                  disabled={!selectedReportId}
                >
                  Tải báo cáo đã chọn
                </button>
              </div>
              <div className="prose prose-slate mt-4 max-w-none">
                {selectedReportMarkdown ? (
                  <ReactMarkdown>{selectedReportMarkdown}</ReactMarkdown>
                ) : (
                  <p className="text-slate-500">Tạo báo cáo hoặc chọn một bản có sẵn để xem trước nội dung Markdown.</p>
                )}
              </div>
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}

/* ───────── Biểu đồ trực quan tab Kết quả (chuẩn paper) ───────── */

const AGENT_LABEL_MAP: Record<string, string> = {
  planning_agent: "Planning",
  evaluation_agent: "Evaluation",
  assessment_agent: "Assessment",
  adaptive_agent: "Tutor",
  content_agent: "Content",
  orbit_agent: "Orbit",
  teacher_agent_nova: "Nova",
  teacher_agent: "Nova",
  collab_orchestrator: "Phối hợp",
};

function ResultsCharts({ resultsSummary }: { resultsSummary: Record<string, unknown> }) {
  const agentStats = (resultsSummary.agent_stats || {}) as Record<string, Record<string, number>>;

  const rows = Object.entries(agentStats)
    .map(([key, stats]) => ({
      key,
      label: AGENT_LABEL_MAP[key] || key,
      pass_rate: Number(stats.pass_rate || 0),
      avg_tsr: Number(stats.avg_tsr || 0) * 100, // → thang %
      avg_e2e: Number(stats.avg_e2e || 0) * 100,
      avg_latency_ms: Number(stats.avg_latency_ms || 0),
      avg_token: Number(stats.avg_token || 0),
    }))
    .filter((r) => r.label !== "unknown");

  if (rows.length === 0) {
    return null;
  }

  // Radar: 3 trục chất lượng (TSR, Pass Rate, E2E), thang 0–100.
  const radarAxes = [
    { key: "avg_tsr", label: "Task Success Rate" },
    { key: "pass_rate", label: "Pass Rate" },
    { key: "avg_e2e", label: "End-to-End" },
  ];
  const RADAR_COLORS = ["#0f766e", "#2563eb", "#d97706", "#7c3aed", "#dc2626"];
  const radarData = radarAxes.map((axis) => {
    const point: Record<string, number | string> = { dimension: axis.label };
    const allVals = rows.map((r) => r[axis.key as keyof typeof r] as number).filter((v) => v > 0);
    point["Trung bình"] = allVals.length ? Math.round(allVals.reduce((a, b) => a + b, 0) / allVals.length) : 0;
    rows.slice(0, 3).forEach((r) => {
      point[r.label] = Math.round(r[axis.key as keyof typeof r] as number);
    });
    return point;
  });

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        {/* 1. BarChart so sánh Pass Rate + TSR */}
        <div className="section-panel p-6">
          <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">SQ1 — Hiệu quả agent chuyên biệt</p>
          <h3 className="mt-2 text-xl font-black text-slate-950">Pass Rate &amp; TSR theo agent (%)</h3>
          <div className="mt-5 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.25)" />
                <XAxis dataKey="label" tick={{ fill: "#475569", fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "#475569", fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="pass_rate" name="Pass Rate (%)" fill="#2563eb" radius={[6, 6, 0, 0]} />
                <Bar dataKey="avg_tsr" name="TSR (%)" fill="#0f766e" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 2. RadarChart đa chiều chất lượng */}
        <div className="section-panel p-6">
          <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Đánh giá đa chiều</p>
          <h3 className="mt-2 text-xl font-black text-slate-950">Chất lượng theo 3 chiều (thang 100)</h3>
          <div className="mt-5 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsRadarChart data={radarData} outerRadius={90}>
                <PolarGrid stroke="rgba(148,163,184,0.3)" />
                <PolarAngleAxis dataKey="dimension" tick={{ fill: "#475569", fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={{ fill: "#94a3b8", fontSize: 10 }} />
                {Object.keys(radarData[0] || {})
                  .filter((k) => k !== "dimension")
                  .map((agent, idx) => (
                    <RechartsRadar
                      key={agent}
                      name={agent}
                      dataKey={agent}
                      stroke={RADAR_COLORS[idx % RADAR_COLORS.length]}
                      fill={RADAR_COLORS[idx % RADAR_COLORS.length]}
                      fillOpacity={idx === 0 ? 0.15 : 0.05}
                    />
                  ))}
                <Legend />
                <Tooltip />
              </RechartsRadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* 3. BarChart Latency */}
      <div className="section-panel p-6">
        <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Hiệu năng thực tế</p>
        <h3 className="mt-2 text-xl font-black text-slate-950">Độ trễ phản hồi theo agent (ms)</h3>
        <div className="mt-5 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.25)" />
              <XAxis dataKey="label" tick={{ fill: "#475569", fontSize: 11 }} />
              <YAxis tick={{ fill: "#475569", fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="avg_latency_ms" name="Độ trễ (ms)" fill="#d97706" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 4. BarChart Token */}
      <div className="section-panel p-6">
        <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Chi phí thực thi</p>
        <h3 className="mt-2 text-xl font-black text-slate-950">Token tiêu thụ theo agent</h3>
        <div className="mt-5 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.25)" />
              <XAxis dataKey="label" tick={{ fill: "#475569", fontSize: 11 }} />
              <YAxis tick={{ fill: "#475569", fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="avg_token" name="Token" fill="#7c3aed" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
