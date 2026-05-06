"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Play, TerminalSquare, Wrench } from "lucide-react";

type CommandResult = {
  name: string;
  ok: boolean;
  exit_code: number | null;
  duration_seconds: number;
  command: string;
  stdout: string;
  stderr: string;
  failed_items: string[];
  affected_features: string[];
  summary: string;
};

type TestSuiteResponse = {
  ok: boolean;
  ran_at: string;
  summary: string;
  results: CommandResult[];
  failing_steps: string[];
};

const STEP_LABELS: Record<string, string> = {
  backend_pytest: "Kiểm thử backend bằng pytest",
  frontend_build: "Build giao diện frontend production",
};

export default function DebugOnePage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<TestSuiteResponse | null>(null);

  const totalDuration = useMemo(() => {
    if (!report) return 0;
    return report.results.reduce((sum, item) => sum + item.duration_seconds, 0);
  }, [report]);

  const handleRunTests = async () => {
    setRunning(true);
    setError("");
    setReport(null);

    try {
      const normalizedBaseUrl = apiBaseUrl.replace(/\/$/, "");
      const candidates = Array.from(
        new Set([
          `${normalizedBaseUrl}/debug/test-suite`,
          `${normalizedBaseUrl}/api/debug/test-suite`,
          `${normalizedBaseUrl.replace(/\/api$/, "")}/debug/test-suite`,
          `${normalizedBaseUrl.replace(/\/api$/, "")}/api/debug/test-suite`,
        ]),
      );

      let response: Response | null = null;
      let lastErrorText = "";

      for (const endpoint of candidates) {
        const candidateResponse = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
        });
        if (candidateResponse.ok) {
          response = candidateResponse;
          break;
        }
        lastErrorText = await candidateResponse.text();
      }

      if (!response) {
        throw new Error(`Không thể chạy kiểm thử: ${lastErrorText.slice(0, 240)}`);
      }

      const data = (await response.json()) as TestSuiteResponse;
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể chạy kiểm thử.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="page-shell">
      <div className="page-container space-y-6">
        <section className="hero-panel overflow-hidden px-6 py-7 md:px-8 md:py-8">
          <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
            <div className="space-y-5">
              <div className="command-badge">
                <Wrench size={14} />
                Trung tâm kiểm thử
              </div>

              <div className="space-y-3">
                <h1 className="display-font text-4xl font-semibold leading-tight text-slate-950 md:text-5xl">
                  Chạy toàn bộ kiểm thử hệ thống chỉ với một nút.
                </h1>
                <p className="max-w-2xl text-base leading-8 text-slate-600">
                  Trang này sẽ gọi backend để chạy bộ test regression bằng <code>pytest</code> và build frontend production.
                  Nếu có lỗi, hệ thống sẽ trả ra bước hỏng, tên test lỗi và log chi tiết để bạn biết tính năng nào đang có vấn đề.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <button onClick={handleRunTests} disabled={running} className="app-btn-primary px-6">
                  {running ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />}
                  {running ? "Đang chạy kiểm thử..." : "Chạy kiểm thử ngay"}
                </button>
                <div className="rounded-full border border-white/70 bg-white/80 px-4 py-2 text-sm text-slate-600">
                  Backend: <span className="font-semibold text-slate-950">pytest</span> • Frontend:{" "}
                  <span className="font-semibold text-slate-950">build</span>
                </div>
              </div>

              {error ? (
                <div className="rounded-[1.4rem] border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700">
                  {error}
                </div>
              ) : null}
            </div>

            <div className="section-panel p-5 md:p-6">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[rgba(0,113,227,0.12)] text-[var(--brand)]">
                  <TerminalSquare size={20} />
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Kết quả gần nhất</p>
                  <h2 className="mt-1 text-2xl font-semibold text-slate-950">Tóm tắt kiểm thử</h2>
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <div className="metric-panel p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Trạng thái</p>
                  <p className={`mt-3 text-lg font-semibold ${report ? (report.ok ? "text-emerald-600" : "text-red-600") : "text-slate-500"}`}>
                    {report ? (report.ok ? "Đã pass" : "Có lỗi") : "Chưa chạy"}
                  </p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Tổng thời gian</p>
                  <p className="mt-3 text-lg font-semibold text-slate-950">{report ? `${totalDuration.toFixed(2)} giây` : "--"}</p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Số bước</p>
                  <p className="mt-3 text-lg font-semibold text-slate-950">{report ? report.results.length : 2}</p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Lần chạy</p>
                  <p className="mt-3 text-sm font-semibold text-slate-950">{report?.ran_at || "--"}</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {report ? (
          <section className="grid gap-5">
            <div className={`section-panel px-5 py-5 ${report.ok ? "border-emerald-100" : "border-red-100"}`}>
              <div className="flex items-start gap-3">
                {report.ok ? (
                  <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-5 w-5 text-red-600" />
                )}
                <div>
                  <p className="text-lg font-semibold text-slate-950">{report.summary}</p>
                  {!report.ok && report.failing_steps.length > 0 ? (
                    <p className="mt-2 text-sm leading-7 text-slate-600">
                      Các bước lỗi: {report.failing_steps.map((item) => STEP_LABELS[item] || item).join(", ")}.
                    </p>
                  ) : null}
                </div>
              </div>
            </div>

            {report.results.map((result) => (
              <article key={result.name} className="hero-panel overflow-hidden">
                <div className="flex flex-col gap-5 px-5 py-5 md:px-6 md:py-6">
                  <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        {result.ok ? (
                          <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                        ) : (
                          <AlertTriangle className="h-5 w-5 text-red-600" />
                        )}
                        <h3 className="text-xl font-semibold text-slate-950">{STEP_LABELS[result.name] || result.name}</h3>
                      </div>
                      <p className="text-sm leading-7 text-slate-600">{result.summary}</p>
                    </div>

                    <div className="grid gap-2 sm:grid-cols-3">
                      <div className="rounded-[1.2rem] bg-slate-50 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Trạng thái</p>
                        <p className={`mt-2 text-sm font-semibold ${result.ok ? "text-emerald-600" : "text-red-600"}`}>
                          {result.ok ? "Thành công" : "Thất bại"}
                        </p>
                      </div>
                      <div className="rounded-[1.2rem] bg-slate-50 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Mã thoát</p>
                        <p className="mt-2 text-sm font-semibold text-slate-950">{result.exit_code ?? "Timeout"}</p>
                      </div>
                      <div className="rounded-[1.2rem] bg-slate-50 px-4 py-3">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Thời gian</p>
                        <p className="mt-2 text-sm font-semibold text-slate-950">{result.duration_seconds.toFixed(2)} giây</p>
                      </div>
                    </div>
                  </div>

                  {result.affected_features.length > 0 ? (
                    <div className="rounded-[1.4rem] border border-red-100 bg-red-50 px-4 py-4">
                      <p className="text-sm font-semibold text-red-700">Tính năng có khả năng đang lỗi</p>
                      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-7 text-red-700">
                        {result.affected_features.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {result.failed_items.length > 0 ? (
                    <div className="rounded-[1.4rem] border border-slate-200 bg-slate-50 px-4 py-4">
                      <p className="text-sm font-semibold text-slate-950">Test lỗi</p>
                      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-7 text-slate-700">
                        {result.failed_items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  <details className="rounded-[1.4rem] border border-slate-200 bg-slate-50 px-4 py-4">
                    <summary className="cursor-pointer text-sm font-semibold text-slate-950">Xem lệnh và log chi tiết</summary>
                    <div className="mt-4 space-y-4">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Lệnh chạy</p>
                        <pre className="mt-2 overflow-x-auto rounded-[1rem] bg-slate-950 px-4 py-3 text-xs text-slate-100">{result.command}</pre>
                      </div>

                      <div className="grid gap-4 xl:grid-cols-2">
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Stdout</p>
                          <pre className="mt-2 max-h-[28rem] overflow-auto rounded-[1rem] bg-slate-950 px-4 py-3 text-xs text-slate-100">
                            {result.stdout || "Không có dữ liệu stdout."}
                          </pre>
                        </div>
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Stderr</p>
                          <pre className="mt-2 max-h-[28rem] overflow-auto rounded-[1rem] bg-slate-950 px-4 py-3 text-xs text-slate-100">
                            {result.stderr || "Không có dữ liệu stderr."}
                          </pre>
                        </div>
                      </div>
                    </div>
                  </details>
                </div>
              </article>
            ))}
          </section>
        ) : null}
      </div>
    </div>
  );
}
