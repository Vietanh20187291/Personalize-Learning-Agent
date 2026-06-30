"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Cpu,
  Loader2,
  Network,
  Play,
  Send,
} from "lucide-react";
import { apiClient, normalizeApiError } from "@/services/api";

// ------------------------------------------------------------------ //
//  Read logged-in user role (mirrors components/Navbar.tsx)          //
// ------------------------------------------------------------------ //
function readUserRole(): string | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("role");
  return raw ? raw.toLowerCase() : null;
}

// Hub is derived from the logged-in role: teacher/admin → Nova, student → Orbit.
function deriveHub(role: string | null): "nova" | "orbit" {
  return role === "student" ? "orbit" : "nova";
}

// ------------------------------------------------------------------ //
//  Types                                                             //
// ------------------------------------------------------------------ //
type TraceEvent = {
  step: number;
  phase: string; // submitted | working | handoff | completed
  status: string;
  from_agent: string;
  to_agent: string;
  task_id: string;
  depends_on?: string | null;
  message: string;
  artifact: { name: string; payload: Record<string, unknown> } | null;
  ts: string;
};

type TraceResponse = {
  hub: string;
  hub_label: string;
  prompt: string;
  scenario_key: string;
  scenario_label: string;
  dag: { step: number; from_agent: string; to_agent: string; task_id: string; intent: string }[];
  events: TraceEvent[];
  final_reply: string;
  protocol: string;
};

type ScenarioSample = {
  key: string;
  label: string;
  sample_prompt: string;
};

// ------------------------------------------------------------------ //
//  Helpers                                                           //
// ------------------------------------------------------------------ //
const PHASE_META: Record<string, { label: string; color: string; dot: string }> = {
  submitted: { label: "Gửi yêu cầu", color: "text-blue-700 border-blue-200 bg-blue-50", dot: "bg-blue-500" },
  working: { label: "Đang xử lý", color: "text-amber-700 border-amber-200 bg-amber-50", dot: "bg-amber-500 animate-pulse" },
  handoff: { label: "Bàn giao artifact", color: "text-purple-700 border-purple-200 bg-purple-50", dot: "bg-purple-500" },
  completed: { label: "Hoàn thành", color: "text-emerald-700 border-emerald-200 bg-emerald-50", dot: "bg-emerald-500" },
  info: { label: "Liên kết", color: "text-slate-700 border-slate-200 bg-slate-50", dot: "bg-slate-400" },
};

const isHub = (name: string) => /Hub$/i.test(name);

const agentHex = (name: string): string => {
  if (isHub(name)) return "#dc2626";
  const map: Record<string, string> = {
    EvaluationAgent: "#d97706",
    PlanningAgent: "#2563eb",
    AssessmentAgent: "#7c3aed",
    TutorAgent: "#059669",
    ContentAgent: "#db2777",
  };
  return map[name] || "#475569";
};

// Badge style tuned for a light theme: colored text on a tinted background.
const agentBadgeStyle = (name: string): React.CSSProperties => {
  const hex = agentHex(name);
  return {
    color: hex,
    backgroundColor: `${hex}1a`,
    borderColor: `${hex}40`,
  };
};

// ------------------------------------------------------------------ //
//  Page                                                              //
// ------------------------------------------------------------------ //
export default function AgentCommunicationPage() {
  const [prompt, setPrompt] = useState("");
  // Hub is fixed by the logged-in role (teacher → Nova, student → Orbit),
  // mirroring how the real system already routes users. No manual toggle.
  const [hub, setHub] = useState<"nova" | "orbit">("nova");
  const [scenarios, setScenarios] = useState<ScenarioSample[]>([]);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [meta, setMeta] = useState<Omit<TraceResponse, "events"> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [streaming, setStreaming] = useState(false);

  const streamTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derive the coordinating hub from the logged-in role on mount.
  useEffect(() => {
    setHub(deriveHub(readUserRole()));
  }, []);

  // Load one-click sample prompts.
  useEffect(() => {
    let alive = true;
    apiClient
      .get("/api/agent-communication/scenarios")
      .then((res) => {
        if (alive) setScenarios(res.data?.scenarios ?? []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // Cleanup any pending stream timer on unmount.
  useEffect(() => {
    return () => {
      if (streamTimer.current) clearTimeout(streamTimer.current);
    };
  }, []);

  const handleTrace = useCallback(async () => {
    const text = prompt.trim();
    if (!text) {
      setError("Vui lòng nhập yêu cầu cần xử lý.");
      return;
    }
    setLoading(true);
    setError("");
    setEvents([]);
    setMeta(null);
    setStreaming(true);

    try {
      const res = await apiClient.post<TraceResponse>("/api/agent-communication/trace", {
        prompt: text,
        hub,
      });
      const data = res.data;
      setMeta(data);

      // Simulate realtime: reveal events one by one.
      const all = data.events ?? [];
      let i = 0;
      const reveal = () => {
        if (i >= all.length) {
          setStreaming(false);
          return;
        }
        setEvents((prev) => [...prev, all[i]]);
        i += 1;
        streamTimer.current = setTimeout(reveal, 650);
      };
      reveal();
    } catch (err) {
      setStreaming(false);
      setError(normalizeApiError(err, "Không thể mô phỏng luồng giao tiếp lúc này."));
    } finally {
      setLoading(false);
    }
  }, [prompt, hub]);

  const useSample = (text: string) => {
    setPrompt(text);
    setError("");
  };

  return (
    <div className="page-shell app-bg">
      <div className="page-container space-y-5">
        {/* Header */}
        <div className="hero-panel flex items-start gap-4 rounded-2xl p-5 md:p-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-[1.15rem] bg-[rgba(0,113,227,0.1)] text-[var(--brand)]">
            <Network size={26} />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900 md:text-2xl">Mô phỏng giao tiếp liên-Agent</h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-600">
              Kiến trúc <span className="font-semibold text-[var(--brand)]">Dual-Hub A2A Mesh</span> (Agent2Agent Protocol).
              Nhập một yêu cầu phức hợp và xem cách các tác tử phụ phối hợp qua{" "}
              <span className="font-semibold text-slate-800">task lifecycle</span> và{" "}
              <span className="font-semibold text-slate-800">artifact</span>. Đây là bản mô phỏng trực quan (không gọi agent thật).
            </p>
          </div>
        </div>

        {/* Hub selector + prompt */}
        <section className="rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Hub điều phối
            </span>
            <span
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ring-1 ${
                hub === "nova"
                  ? "bg-red-50 text-red-700 ring-red-200"
                  : "bg-sky-50 text-sky-700 ring-sky-200"
              }`}
            >
              {hub === "nova" ? "Nova (Giảng viên)" : "Orbit (Sinh viên)"}
            </span>
            <span className="text-xs text-slate-400">
              — tự động theo vai trò đăng nhập của bạn
            </span>
          </div>

          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={3}
            placeholder="VD: Đánh giá sinh viên A rồi lập kế hoạch cải thiện các môn điểm thấp"
            className="w-full resize-none rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-[var(--brand)] focus:ring-2 focus:ring-[rgba(0,113,227,0.25)]"
          />

          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="text-xs text-slate-500">
              Mẹo: dùng một trong các kịch bản mẫu bên dưới để xem DAG phối hợp.
            </p>
            <button
              type="button"
              onClick={handleTrace}
              disabled={loading || streaming}
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--brand)] px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-[rgba(0,113,227,0.25)] transition hover:bg-[var(--brand-strong)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : streaming ? (
                <Play size={16} />
              ) : (
                <Send size={16} />
              )}
              {loading ? "Đang lập kế hoạch…" : streaming ? "Đang mô phỏng…" : "Mô phỏng giao tiếp"}
            </button>
          </div>
        </section>

        {/* Scenario samples */}
        {scenarios.length > 0 && (
          <section>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Kịch bản mẫu
            </p>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {scenarios.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => useSample(s.sample_prompt)}
                  className="group rounded-xl border border-slate-200 bg-white p-3 text-left shadow-sm transition hover:border-[var(--brand)] hover:shadow-md"
                >
                  <p className="text-sm font-semibold text-slate-800 group-hover:text-[var(--brand)]">{s.label}</p>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500">&ldquo;{s.sample_prompt}&rdquo;</p>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* DAG overview */}
        {meta && (
          <section className="rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-wider text-slate-500">Kịch bản được chọn</p>
                <p className="text-base font-semibold text-slate-900">{meta.scenario_label}</p>
              </div>
              <div className="flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                <Cpu size={13} /> {meta.hub_label} · {meta.protocol}
              </div>
            </div>

            {/* DAG chain */}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="rounded-lg bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-700 ring-1 ring-red-200">
                {meta.hub_label}
              </span>
              {meta.dag.map((d, idx) => (
                <span key={d.task_id} className="flex items-center gap-2">
                  <ArrowRight size={14} className="text-slate-400" />
                  <span
                    className="rounded-lg px-2.5 py-1 text-xs font-semibold ring-1"
                    style={agentBadgeStyle(d.to_agent)}
                  >
                    {d.to_agent}
                  </span>
                  {idx === meta.dag.length - 1 && (
                    <>
                      <ArrowRight size={14} className="text-slate-400" />
                      <span className="rounded-lg bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-700 ring-1 ring-red-200">
                        {meta.hub_label}
                      </span>
                    </>
                  )}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Timeline of events */}
        {events.length > 0 && (
          <section>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
              Luồng giao tiếp (A2A lifecycle)
            </h2>
            <ol className="space-y-3">
              {events.map((ev, idx) => (
                <EventCard key={`${ev.task_id}-${ev.phase}-${idx}`} ev={ev} />
              ))}
            </ol>
          </section>
        )}

        {/* Final reply */}
        {meta && !streaming && (
          <section className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-emerald-700">
              Phản hồi cuối cùng từ Hub
            </p>
            <p className="text-sm text-emerald-900">{meta.final_reply}</p>
          </section>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
//  Event card                                                        //
// ------------------------------------------------------------------ //
function EventCard({ ev }: { ev: TraceEvent }) {
  const pm = PHASE_META[ev.phase] || PHASE_META.info;
  const sameAgent = ev.from_agent === ev.to_agent;
  return (
    <li className={`rounded-xl border p-4 shadow-sm ${pm.color}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${pm.dot}`} />
        <span className="rounded-md bg-white/70 px-2 py-0.5 text-[11px] font-bold text-slate-700 ring-1 ring-slate-200">
          {ev.task_id}
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-wide opacity-80">{pm.label}</span>
        {ev.depends_on && (
          <span className="rounded-md bg-purple-100 px-2 py-0.5 text-[11px] font-medium text-purple-700">
            kế thừa {ev.depends_on}
          </span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <AgentBadge name={ev.from_agent} />
        {!sameAgent && <ArrowRight size={14} className="text-slate-400" />}
        {!sameAgent && <AgentBadge name={ev.to_agent} />}
        {sameAgent && <span className="text-xs text-slate-500">({ev.to_agent} tự xử lý)</span>}
      </div>

      <p className="mt-2 text-sm text-slate-700">{ev.message}</p>

      {ev.artifact && (
        <div className="mt-3 rounded-lg border border-slate-200 bg-white/80 p-3">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Artifact trả về: {ev.artifact.name}
          </p>
          <pre className="overflow-x-auto text-xs text-slate-700">
            {JSON.stringify(ev.artifact.payload, null, 2)}
          </pre>
        </div>
      )}
    </li>
  );
}

function AgentBadge({ name }: { name: string }) {
  const hex = agentHex(name);
  return (
    <span
      className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold ring-1"
      style={{ color: hex, backgroundColor: `${hex}1a`, borderColor: `${hex}40` }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: hex }} />
      {name}
    </span>
  );
}
