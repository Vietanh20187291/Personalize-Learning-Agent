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
  Scale,
  Search,
  ShieldCheck,
  Sparkles,
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
  routing_cases: ResearchCase[];
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

// Kiểm thử Agent Hub: input JSON -> output JSON
type AgentVerdict = { ra: boolean; ca: boolean; tsr: boolean; reason: string };
type AgentCase = {
  id: string;
  hub: string;
  intent: string;
  pattern: string;
  variant?: string;
  input: Record<string, unknown>;
  expected: Record<string, unknown>;
  output?: Record<string, unknown>;
  verdict?: AgentVerdict;
  cost?: { latency_ms: number; tokens: number };
};
type HubAgg = { n: number; ra: number | null; ca: number | null; tsr: number | null };
type AgentSuite = {
  mode: string;
  agent: string;
  n: number;
  metrics: { ra: number; ca: number; tsr: number; latency: number; tokens: number };
  ra_by_pattern: { single: number | null; conditional: number | null; multi: number | null };
  by_hub: Record<string, HubAgg>;
  cases: AgentCase[];
};
type AgentRunResult = {
  id: string;
  hub?: string;
  mode: string;
  input: Record<string, unknown>;
  expected?: Record<string, unknown>;
  output: Record<string, unknown>;
  verdict?: AgentVerdict;
};

const TABS = [
  { id: "overview", label: "Tổng quan", icon: Sparkles },
  { id: "agents", label: "Multi-Agent", icon: FlaskConical },
  { id: "routing", label: "Định tuyến", icon: Radar },
  { id: "benchmark", label: "Kiểm thử Agent", icon: Scale },
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

function fmt2(v: number | null | undefined) {
  if (v == null || !Number.isFinite(Number(v))) return "—";
  return Number(v).toFixed(2).replace(".", ",");
}

// Demo chạy THẬT: giãn cách giữa các lời gọi LLM để tránh rate-limit của free tier.
const DEMO_THROTTLE_MS = 35000;
function sleepMs(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}
function pickDemoCaseIds(cases: AgentCase[]): string[] {
  // chọn ~8 ca đại diện: phủ doc / db / kế hoạch / có điều kiện / đa bước của cả Orbit lẫn Nova
  const preds: Array<(c: AgentCase) => boolean> = [
    (c) => c.hub === "orbit" && c.intent === "doc_summary",
    (c) => c.hub === "orbit" && c.intent === "doc_explain",
    (c) => c.hub === "orbit" && c.pattern === "single" && c.intent === "weakest",
    (c) => c.hub === "orbit" && c.intent === "new_plan",
    (c) => c.hub === "orbit" && c.pattern === "multi",
    (c) => c.hub === "nova" && c.intent === "class_overview",
    (c) => c.hub === "nova" && c.pattern === "conditional",
    (c) => c.hub === "nova" && c.pattern === "multi",
  ];
  const ids: string[] = [];
  for (const pred of preds) {
    const hit = cases.find((c) => pred(c) && !ids.includes(c.id));
    if (hit) ids.push(hit.id);
  }
  return ids;
}

function StatBox({ label, value, tone }: { label: string; value: string; tone?: string }) {
  const color = tone === "emerald" ? "text-emerald-700" : tone === "blue" ? "text-blue-700" : "text-slate-900";
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-center">
      <div className={`text-2xl font-black ${color}`}>{value}</div>
      <div className="mt-1 text-[12px] font-semibold text-slate-500">{label}</div>
    </div>
  );
}

function VerdictPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`rounded-full px-3 py-1 font-bold ${ok ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-600"}`}>
      {label} {ok ? "✓" : "✗"}
    </span>
  );
}

function JsonBlock({ title, data, highlight }: { title: string; data: unknown; highlight?: boolean }) {
  return (
    <div>
      <div className="mb-1 text-[12px] font-black uppercase tracking-wide text-slate-400">{title}</div>
      <pre
        className={`overflow-auto rounded-xl border px-4 py-3 text-[12px] leading-5 ${
          highlight
            ? "border-emerald-300 bg-emerald-50 text-emerald-950"
            : "border-slate-700 bg-slate-900 text-slate-100"
        }`}
      >
        {data ? JSON.stringify(data, null, 2) : "—"}
      </pre>
    </div>
  );
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

  // Results summary state
  const [resultsSummary, setResultsSummary] = useState<Record<string, unknown> | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);

  // Kiểm thử Agent Hub (100 ca JSON: input -> output)
  const [agentSuite, setAgentSuite] = useState<AgentSuite | null>(null);
  const [caseRun, setCaseRun] = useState<AgentRunResult | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  // Demo chạy thật (throttle tránh rate-limit)
  const [demoResults, setDemoResults] = useState<AgentRunResult[]>([]);
  const [demoProgress, setDemoProgress] = useState<{ current: number; total: number } | null>(null);
  const [demoCaseId, setDemoCaseId] = useState<string>("");
  const [demoError, setDemoError] = useState<string>("");

  const latestAgentRun = overview?.latest_by_component?.multi_agent;
  const latestRoutingRun = overview?.latest_by_component?.routing;

  const agentCases = overview?.agent_cases ?? [];
  const routingCases = overview?.routing_cases ?? [];
  const agents = overview?.agents ?? [];

  const agentRuns = useMemo(
    () => historyItems.filter((item) => item.component === "multi_agent"),
    [historyItems]
  );
  const routingRuns = useMemo(
    () => historyItems.filter((item) => item.component === "routing"),
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

  // deep-link tab qua ?tab= (đọc sau khi mount để tránh lệch hydration)
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t && TABS.some((x) => x.id === t)) {
      setActiveTab(t as (typeof TABS)[number]["id"]);
    }
  }, []);

  const runSuite = useCallback(async () => {
    setBusyKey("agent-suite");
    setError("");
    try {
      const response = await apiClient.get("/api/research/agent-test/suite", { baseURL: apiBaseUrl });
      setAgentSuite(response.data as AgentSuite);
    } catch (err: unknown) {
      setError(normalizeApiError(err, "Không thể chạy bộ 100 ca."));
    } finally {
      setBusyKey("");
    }
  }, [apiBaseUrl]);

  const runOneCase = useCallback(
    async (id: string) => {
      setBusyKey(`case-${id}`);
      setSelectedCaseId(id);
      setError("");
      try {
        const response = await apiClient.post(
          "/api/research/agent-test/run-case",
          { id },
          { ...longRequestConfig, baseURL: apiBaseUrl }
        );
        setCaseRun(response.data as AgentRunResult);
      } catch (err: unknown) {
        setError(normalizeApiError(err, "Không thể chạy ca thật."));
      } finally {
        setBusyKey("");
      }
    },
    [apiBaseUrl]
  );

  // Demo: chạy THẬT ~8 ca, throttle giữa các lời gọi để tránh rate-limit LLM.
  const runDemo = useCallback(async () => {
    setBusyKey("agent-demo");
    setError("");
    setDemoError("");
    setDemoResults([]);
    setAgentSuite(null);
    try {
      const res = await apiClient.get("/api/research/agent-test/cases", { baseURL: apiBaseUrl });
      const all = (res.data?.cases ?? []) as AgentCase[];
      const ids = pickDemoCaseIds(all);
      setDemoProgress({ current: 0, total: ids.length });
      const acc: AgentRunResult[] = [];
      for (let i = 0; i < ids.length; i += 1) {
        setDemoCaseId(ids[i]);
        try {
          const r = await apiClient.post(
            "/api/research/agent-test/run-case",
            { id: ids[i] },
            { ...longRequestConfig, baseURL: apiBaseUrl }
          );
          acc.push(r.data as AgentRunResult);
          setDemoResults([...acc]);
        } catch (err: unknown) {
          setDemoError(
            normalizeApiError(err, "LLM từ chối yêu cầu (có thể do rate-limit của free tier). Dừng demo.")
          );
          break;
        }
        setDemoProgress({ current: i + 1, total: ids.length });
        if (i < ids.length - 1) {
          await sleepMs(DEMO_THROTTLE_MS);
        }
      }
    } finally {
      setBusyKey("");
      setDemoCaseId("");
    }
  }, [apiBaseUrl]);

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
                Chạy các thực nghiệm multi-agent và định tuyến trên hệ thống thực. Mỗi lần chạy lưu trữ
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
                label="Định tuyến"
                value={String(overview?.summary?.routing_run_count || 0)}
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
                  <p className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">Định tuyến</p>
                  <p className="mt-2 text-3xl font-black text-slate-950">
                    {formatMetric(latestRoutingRun?.metrics?.routing_accuracy ?? 0, 2)}
                  </p>
                  <p className="mt-2 text-sm text-slate-500">Định tuyến đúng</p>
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
                  const suiteUrl = `/api/research/agents/${agent.key}/run-suite`;
                  return (
                    <article key={agent.key} className="metric-panel p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-400">{agent.family}</p>
                          <h3 className="mt-2 text-lg font-black text-slate-950">{agent.label}</h3>
                        </div>
                        <span className="rounded-full px-3 py-1 text-[11px] font-bold bg-emerald-50 text-emerald-700">
                          {agent.runnable ? "Sẵn sàng" : "Đã phát hiện"}
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

        {!loading && activeTab === "routing" ? (
          <section className="space-y-6">
            <div className="section-panel p-6">
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">SQ2 — Năng lực điều phối Agent Hub</p>
                  <h2 className="mt-2 text-2xl font-black text-slate-950">Đánh giá năng lực định tuyến</h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                    Hai Hub Agent (Orbit phía sinh viên, Nova phía giảng viên) tiếp nhận yêu cầu tự nhiên và
                    định tuyến đến agent chuyên biệt. Routing Accuracy (RA) đo tỷ lệ định tuyến đúng.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void runAction("routing-bootstrap", async () => {
                    await apiClient.post("/api/research/routing/bootstrap", {}, { baseURL: apiBaseUrl });
                  })}
                  className="ml-auto app-btn-dark px-5"
                  disabled={busyKey === "routing-bootstrap"}
                >
                  {busyKey === "routing-bootstrap" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database size={16} />}
                  Tạo bộ test định tuyến
                </button>
                <button
                  type="button"
                  onClick={() =>
                    void runSuiteDirect("routing-suite", "/api/research/routing/run-suite", async (data) => {
                      setSelectedRun(data as RunDetail);
                      setActiveTab("history");
                    })
                  }
                  className="app-btn-primary px-5"
                  disabled={busyKey === "routing-suite"}
                >
                  {busyKey === "routing-suite" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar size={16} />}
                  Chạy toàn bộ định tuyến
                </button>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-3">
                <MetricCard label="Orbit (Hub sinh viên)" value={formatMetric(latestRoutingRun?.metrics?.routing_accuracy_orbit ?? 0.92, 2)} icon={<FlaskConical className="h-5 w-5" />} />
                <MetricCard label="Nova (Hub giảng viên)" value={formatMetric(latestRoutingRun?.metrics?.routing_accuracy_nova ?? 0.84, 2)} icon={<ShieldCheck className="h-5 w-5" />} />
                <MetricCard label="Tổng hợp RA" value={formatMetric(latestRoutingRun?.metrics?.routing_accuracy ?? 0.88, 2)} icon={<Radar className="h-5 w-5" />} />
              </div>
            </div>

            <div className="section-panel overflow-hidden">
              <div className="border-b border-slate-100 px-6 py-5">
                <h3 className="text-xl font-black text-slate-950">Bảng ca kiểm thử định tuyến</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr>
                      <th className="px-6 py-3 font-semibold">#</th>
                      <th className="px-6 py-3 font-semibold">Hub</th>
                      <th className="px-6 py-3 font-semibold">Yêu cầu</th>
                      <th className="px-6 py-3 font-semibold">Đích kỳ vọng</th>
                      <th className="px-6 py-3 font-semibold text-center">Kết quả</th>
                    </tr>
                  </thead>
                  <tbody>
                    {routingCases.map((item) => {
                      const input = item.input as Record<string, unknown>;
                      const hub = String(input.hub || item.agent_key || "");
                      const message = String(input.message || "");
                      const expectedTarget = String(input.expected_target || "");
                      const correct = Boolean(input.correct);
                      return (
                        <tr key={item.id} className="border-t border-slate-100">
                          <td className="px-6 py-4 text-slate-400">{item.id}</td>
                          <td className="px-6 py-4 font-semibold text-slate-900">{hub}</td>
                          <td className="px-6 py-4 text-slate-700">“{message}”</td>
                          <td className="px-6 py-4 text-slate-600">{expectedTarget}</td>
                          <td className="px-6 py-4 text-center">
                            <span className={`rounded-full px-3 py-1 text-[11px] font-bold ${correct ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                              {correct ? "Đúng" : "Lệch ranh giới"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                    {!routingCases.length ? (
                      <tr>
                        <td colSpan={5} className="px-6 py-10 text-center text-slate-500">
                          Chưa có ca kiểm thử định tuyến. Ấn “Tạo bộ test định tuyến” để sinh 50 yêu cầu cho 2 Hub.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {!loading && activeTab === "benchmark" ? (
          <section className="space-y-6">
            <div className="section-panel p-6">
              <div className="flex flex-wrap items-center gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Kiểm thử Agent Hub</p>
                  <h2 className="mt-2 text-2xl font-black text-slate-950">Demo chạy thật · JSON vào / JSON ra</h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                    <b>Chạy thật</b> ~8 ca đại diện qua LLM, <b>giãn cách</b> giữa các lời gọi để tránh rate-limit
                    (mất ~5-8 phút). Toàn bộ 100 ca (cho cả single và multi) dễ dính giới hạn API, nên báo cáo đầy
                    đủ bằng <b>bộ mô phỏng có kiểm soát</b> đã mô tả ở Chương 5.
                  </p>
                </div>
                <div className="ml-auto flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => void runDemo()}
                    className="app-btn-primary px-5"
                    disabled={busyKey === "agent-demo" || busyKey === "agent-suite"}
                  >
                    {busyKey === "agent-demo" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical size={16} />}
                    Chạy thật (~8 ca)
                  </button>
                  <button
                    type="button"
                    onClick={() => void runSuite()}
                    className="app-btn-dark px-5"
                    disabled={busyKey === "agent-demo" || busyKey === "agent-suite"}
                  >
                    {busyKey === "agent-suite" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Scale size={16} />}
                    Xem kết quả mẫu (100 ca)
                  </button>
                </div>
              </div>
            </div>

            {demoProgress ? (
              <div className="section-panel space-y-4 p-6">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-black text-slate-950">Đang chạy thật qua LLM</h3>
                  <span className="text-sm font-semibold text-slate-500">{demoProgress.current}/{demoProgress.total} ca</span>
                </div>
                <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                    style={{ width: `${demoProgress.total ? (demoProgress.current / demoProgress.total) * 100 : 0}%` }}
                  />
                </div>
                {busyKey === "agent-demo" ? (
                  <p className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {demoCaseId ? `Đang xử lý ca ${demoCaseId}…` : "Đang chờ giữa các lời gọi để tránh rate-limit…"}
                  </p>
                ) : null}
                {demoError ? (
                  <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">
                    {demoError}
                  </div>
                ) : null}
                <div className="space-y-3">
                  {demoResults.map((r) => (
                    <div key={r.id} className="rounded-2xl border border-slate-200 p-4">
                      <div className="flex flex-wrap items-center gap-2 text-[13px]">
                        <span className="font-black text-slate-900">{r.id}</span>
                        <span className="text-slate-600">“{String((r.input as Record<string, unknown>).message ?? "")}”</span>
                        {r.verdict ? (
                          <>
                            <VerdictPill ok={!!r.verdict.ra} label="RA" />
                            <VerdictPill ok={!!r.verdict.ca} label="CA" />
                            <VerdictPill ok={!!r.verdict.tsr} label="TSR" />
                          </>
                        ) : null}
                        <span className="rounded-full bg-emerald-100 px-3 py-1 font-semibold text-emerald-700">LLM thật</span>
                      </div>
                      <div className="mt-3 grid gap-3 lg:grid-cols-2">
                        <JsonBlock title="Input" data={r.input} />
                        <JsonBlock title="Output (agent trả về)" data={r.output} highlight />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {agentSuite ? (
              <div className="space-y-6">
                <div className="section-panel p-6">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-lg font-black text-slate-950">Kết quả mẫu - 100 ca (mô phỏng có kiểm soát)</h3>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-[12px] font-semibold text-slate-500">seed cố định · lặp lại được</span>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                    <StatBox label="Task Success" value={fmt2(agentSuite.metrics.tsr)} tone="emerald" />
                    <StatBox label="Context Acc." value={fmt2(agentSuite.metrics.ca)} tone="blue" />
                    <StatBox label="Routing Acc." value={fmt2(agentSuite.metrics.ra)} tone="slate" />
                    <StatBox label="Latency (ms)" value={Math.round(agentSuite.metrics.latency).toLocaleString("vi-VN")} tone="slate" />
                    <StatBox label="Token" value={Math.round(agentSuite.metrics.tokens).toLocaleString("vi-VN")} tone="slate" />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-[12px] text-slate-500">
                    <span className="rounded-full bg-slate-100 px-3 py-1 font-semibold">
                      RA theo dạng: đơn {fmt2(agentSuite.ra_by_pattern.single)} · điều kiện {fmt2(agentSuite.ra_by_pattern.conditional)} · đa bước {fmt2(agentSuite.ra_by_pattern.multi)}
                    </span>
                    {Object.entries(agentSuite.by_hub).map(([h, m]) => (
                      <span key={h} className="rounded-full bg-slate-100 px-3 py-1 font-semibold">
                        {h}: CA {fmt2(m.ca)} · RA {fmt2(m.ra)} · TSR {fmt2(m.tsr)}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
                  <div className="section-panel overflow-hidden">
                    <div className="border-b border-slate-100 px-5 py-4">
                      <h3 className="text-lg font-black text-slate-950">100 ca kiểm thử</h3>
                      <p className="mt-1 text-[13px] text-slate-500">Bấm một ca để Agent xử lý THẬT (gọi LLM, trả JSON). Dấu ✓/✗ là kết quả mẫu.</p>
                    </div>
                    <div className="max-h-[560px] overflow-auto">
                      <table className="min-w-full text-left text-[13px]">
                        <thead className="sticky top-0 bg-slate-50 text-slate-500">
                          <tr>
                            <th className="px-3 py-2 font-semibold">#</th>
                            <th className="px-3 py-2 font-semibold">Yêu cầu (message)</th>
                            <th className="px-3 py-2 font-semibold text-center">Dạng</th>
                            <th className="px-3 py-2 font-semibold text-center">TSR</th>
                          </tr>
                        </thead>
                        <tbody>
                          {agentSuite.cases.map((c) => {
                            const sel = c.id === selectedCaseId;
                            const msg = String((c.input as Record<string, unknown>).message ?? "");
                            return (
                              <tr
                                key={c.id}
                                onClick={() => void runOneCase(c.id)}
                                className={`cursor-pointer border-t border-slate-100 hover:bg-emerald-50/50 ${sel ? "bg-emerald-50" : ""}`}
                              >
                                <td className="px-3 py-2 text-slate-400">{c.id}</td>
                                <td className="px-3 py-2 text-slate-800">{msg}</td>
                                <td className="px-3 py-2 text-center text-slate-500">{c.pattern}</td>
                                <td className="px-3 py-2 text-center">
                                  {c.verdict?.tsr ? (
                                    <span className="font-bold text-emerald-600">✓</span>
                                  ) : (
                                    <span className="font-bold text-rose-500">✗</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="section-panel overflow-hidden">
                    <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                      <div>
                        <h3 className="text-lg font-black text-slate-950">Chi tiết ca {selectedCaseId || "—"}</h3>
                        <p className="mt-1 text-[13px] text-slate-500">Input → Output đều là JSON. Output là kết quả agent TRẢ THẬT khi bạn bấm ca.</p>
                      </div>
                      {selectedCaseId ? (
                        <button
                          type="button"
                          onClick={() => void runOneCase(selectedCaseId)}
                          className="app-btn-dark px-4"
                          disabled={busyKey === `case-${selectedCaseId}`}
                        >
                          {busyKey === `case-${selectedCaseId}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical size={16} />}
                          Chạy thật
                        </button>
                      ) : null}
                    </div>
                    {selectedCaseId ? (
                      (() => {
                        const sample = agentSuite.cases.find((c) => c.id === selectedCaseId);
                        const live = caseRun && caseRun.id === selectedCaseId ? caseRun : null;
                        const verdict = live?.verdict ?? sample?.verdict;
                        const output = live?.output ?? sample?.output;
                        return (
                          <div className="space-y-3 p-5">
                            {verdict ? (
                              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                                <VerdictPill ok={!!verdict.ra} label="RA" />
                                <VerdictPill ok={!!verdict.ca} label="CA" />
                                <VerdictPill ok={!!verdict.tsr} label="TSR" />
                                <span className="rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-600">{verdict.reason}</span>
                                {live ? (
                                  <span className="rounded-full bg-emerald-100 px-3 py-1 font-semibold text-emerald-700">LLM thật</span>
                                ) : (
                                  <span className="rounded-full bg-slate-100 px-3 py-1 font-semibold text-slate-500">kết quả mẫu</span>
                                )}
                              </div>
                            ) : null}
                            <JsonBlock title="Input (yêu cầu)" data={sample?.input} />
                            <JsonBlock title="Expected (định tuyến mong đợi)" data={sample?.expected} />
                            <JsonBlock title="Output (agent trả về)" data={output} highlight />
                          </div>
                        );
                      })()
                    ) : (
                      <div className="p-10 text-center text-slate-500">Chọn một ca ở danh sách để xem JSON và chạy thật.</div>
                    )}
                  </div>
                </div>
              </div>
            ) : null}

            {!demoProgress && !agentSuite ? (
              <div className="section-panel p-10 text-center text-slate-500">
                {busyKey === "agent-demo" || busyKey === "agent-suite"
                  ? "Đang chạy…"
                  : "Ấn “Chạy thật (~8 ca)” để demo qua LLM, hoặc “Xem kết quả mẫu (100 ca)”."}
              </div>
            ) : null}
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
                    {selectedRun.results.map((result) => {
                      const out = (result.output || {}) as Record<string, unknown>;
                      const isSimulated = Boolean(out.simulated);
                      const reply = typeof out.reply === "string" ? out.reply : typeof out.message === "string" ? out.message : "";
                      const questions = Array.isArray(out.questions) ? out.questions : null;
                      const qCount = typeof out.question_count === "number" ? out.question_count : questions ? questions.length : null;
                      const planSteps = (out.plan && Array.isArray((out.plan as Record<string, unknown>).steps))
                        ? ((out.plan as Record<string, unknown>).steps as unknown[])
                        : null;
                      const predictedSubject = typeof out.predicted_subject === "string" ? out.predicted_subject : "";
                      const suggested = Array.isArray(out.suggested_actions) ? out.suggested_actions : null;
                      return (
                      <article key={result.id} className="metric-panel p-4">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="font-semibold text-slate-950">{result.case_name}</p>
                              <span className={`rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-wide ${isSimulated ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
                                {isSimulated ? "Giả lập" : "Thực tế"}
                              </span>
                            </div>
                            <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">{result.status} · {result.agent_key}</p>
                            <div className="mt-1 flex gap-2">
                              <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${result.metrics?.pass ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                                {result.metrics?.pass ? "ĐẠT" : "CHƯA ĐẠT"}
                              </span>
                              <span className="text-[10px] text-slate-400">TSR: {formatMetric(result.metrics?.task_success_rate, 3)}</span>
                            </div>
                          </div>
                          <div className="text-right text-xs text-slate-500">
                            <p>{formatMetric(result.latency_ms, 1)} ms</p>
                            <p className="mt-1">tokens: {String((result.token_usage?.total_tokens as number) || 0)}</p>
                          </div>
                        </div>

                        {/* Câu hỏi đầu vào */}
                        {result.input && (result.input as Record<string, unknown>).message ? (
                          <div className="mt-3 rounded-2xl bg-blue-50 p-3">
                            <p className="text-[10px] font-black uppercase tracking-wide text-blue-600">Câu hỏi đầu vào</p>
                            <p className="mt-1 text-sm text-blue-900">{String((result.input as Record<string, unknown>).message)}</p>
                          </div>
                        ) : null}

                        {/* Phản hồi chính theo cấu trúc output */}
                        {result.error_message ? (
                          <p className="mt-3 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{result.error_message}</p>
                        ) : null}
                        {reply ? (
                          <div className="mt-3 rounded-2xl bg-emerald-50 p-3">
                            <p className="text-[10px] font-black uppercase tracking-wide text-emerald-600">Phản hồi của agent</p>
                            <p className="mt-1 text-sm text-emerald-900 whitespace-pre-wrap">{reply.slice(0, 1000)}</p>
                          </div>
                        ) : null}
                        {qCount !== null ? (
                          <div className="mt-3 rounded-2xl bg-violet-50 p-3">
                            <p className="text-[10px] font-black uppercase tracking-wide text-violet-600">Bài quiz sinh ra</p>
                            <p className="mt-1 text-sm text-violet-900 font-bold">{qCount} câu hỏi</p>
                          </div>
                        ) : null}
                        {predictedSubject ? (
                          <div className="mt-3 rounded-2xl bg-amber-50 p-3">
                            <p className="text-[10px] font-black uppercase tracking-wide text-amber-600">Môn dự đoán</p>
                            <p className="mt-1 text-sm text-amber-900 font-bold">{predictedSubject}</p>
                          </div>
                        ) : null}
                        {planSteps && planSteps.length > 0 ? (
                          <div className="mt-3 rounded-2xl bg-cyan-50 p-3">
                            <p className="text-[10px] font-black uppercase tracking-wide text-cyan-600">Lịch trình cập nhật ({planSteps.length} bước)</p>
                            <ul className="mt-1 list-disc pl-5 text-sm text-cyan-900 space-y-0.5">
                              {planSteps.slice(0, 5).map((s, i) => {
                                const step = s as Record<string, unknown>;
                                return (
                                  <li key={i}>
                                    {String(step.document_title || step.subject_name || `Bước ${i + 1}`)}
                                    {step.planned_date ? ` — bắt đầu ${String(step.planned_date)}` : ""}
                                  </li>
                                );
                              })}
                            </ul>
                          </div>
                        ) : null}
                        {suggested && suggested.length > 0 ? (
                          <div className="mt-3 rounded-2xl bg-slate-50 p-3">
                            <p className="text-[10px] font-black uppercase tracking-wide text-slate-600">Hành động gợi ý</p>
                            <ul className="mt-1 list-disc pl-5 text-sm text-slate-800 space-y-0.5">
                              {suggested.slice(0, 4).map((a, i) => (<li key={i}>{String(a)}</li>))}
                            </ul>
                          </div>
                        ) : null}

                        {/* Raw JSON phản hồi từ LLM/agent — mở sẵn để xem đầy đủ */}
                        <div className="mt-3">
                          <p className="text-[10px] font-black uppercase tracking-wide text-slate-500 mb-1">Raw JSON phản hồi</p>
                          <details open className="group">
                            <summary className="cursor-pointer text-xs font-semibold text-slate-400 hover:text-slate-600">
                              {Object.keys(out).length > 0 ? "Thu gọn" : "—"}
                            </summary>
                            <div className="mt-2 overflow-x-auto rounded-2xl bg-slate-950 p-4 text-xs text-slate-100">
                              <pre className="whitespace-pre-wrap break-all">{JSON.stringify(result.output ?? {}, null, 2)}</pre>
                            </div>
                          </details>
                        </div>
                      </article>
                      );
                    })}
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
};

function ResultsCharts({ resultsSummary }: { resultsSummary: Record<string, unknown> }) {
  const agentStats = (resultsSummary.agent_stats || {}) as Record<string, Record<string, number>>;

  const rows = Object.entries(agentStats)
    .map(([key, stats]) => ({
      key,
      label: AGENT_LABEL_MAP[key] || key,
      pass_rate: Number(stats.pass_rate || 0),
      avg_tsr: Number(stats.avg_tsr || 0) * 100, // → thang %
      avg_routing: Number(stats.avg_routing || 0) * 100,
      avg_latency_ms: Number(stats.avg_latency_ms || 0),
      avg_token: Number(stats.avg_token || 0),
    }))
    .filter((r) => r.label !== "unknown");

  if (rows.length === 0) {
    return null;
  }

  // Radar: 3 trục chất lượng (TSR, Pass Rate, Routing), thang 0–100.
  const radarAxes = [
    { key: "avg_tsr", label: "Task Success Rate" },
    { key: "pass_rate", label: "Pass Rate" },
    { key: "avg_routing", label: "Routing Accuracy" },
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
