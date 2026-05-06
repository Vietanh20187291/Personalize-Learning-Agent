"use client";

import React, { useEffect, useState } from "react";
import axios from "axios";
import toast from "react-hot-toast";
import { BookOpen, CheckCircle2, Download, FileText, Loader2, Settings2 } from "lucide-react";

import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "../../../services/api";

export default function ExamGeneratorPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  const shortTimeoutMs = 15000;
  const [classList, setClassList] = useState<Array<{ id: number; name: string; subject: string }>>([]);
  const [selectedClassId, setSelectedClassId] = useState<number | "">("");
  const [subject, setSubject] = useState("");
  const [examType, setExamType] = useState("trắc nghiệm");
  const [numQuestions, setNumQuestions] = useState<number>(20);
  const [numVersions, setNumVersions] = useState<number>(2);
  const [level, setLevel] = useState("Trung bình");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchClasses = async () => {
      const teacherId = localStorage.getItem("userId") || localStorage.getItem("user_id");
      if (!teacherId) return;
      try {
        const res = await axios.get(`${apiBaseUrl}/api/classroom/teacher/${teacherId}`, {
          timeout: shortTimeoutMs,
        });
        setClassList(res.data || []);
        if (res.data && res.data.length > 0) {
          setSelectedClassId(res.data[0].id);
          setSubject(res.data[0].subject);
        }
      } catch (error) {
        console.error("Lỗi lấy danh sách lớp:", error);
      }
    };
    void fetchClasses();
  }, [apiBaseUrl]);

  const handleClassChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setSelectedClassId(Number(val));
    const selected = classList.find((item) => item.id === Number(val));
    if (selected) setSubject(selected.subject);
  };

  const handleGenerateAndDownload = async () => {
    if (!selectedClassId || !subject) {
      toast.error("Vui lòng chọn lớp và môn học.");
      return;
    }

    setLoading(true);
    const toastId = toast.loading("Đang ghép đề từ ngân hàng câu hỏi và xáo trộn mã đề...");

    try {
      const response = await runLongRequest(
        () =>
          apiClient.post(
            `${apiBaseUrl}/api/exam/generate-word`,
            {
              class_id: selectedClassId,
              subject,
              exam_type: examType,
              num_questions: numQuestions,
              num_versions: numVersions,
              level,
            },
            {
              ...longRequestConfig,
              responseType: "blob",
            }
          ),
        { slowDelayMs: 3500 }
      );

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `DeThi_${subject.replace(/\s+/g, "")}_${examType}.docx`);
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);
      window.URL.revokeObjectURL(url);

      toast.success("Tạo và tải đề thi thành công.", { id: toastId });
    } catch (error) {
      console.error(error);
      if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
        try {
          const text = await error.response.data.text();
          const payload = JSON.parse(text);
          const detail =
            typeof payload?.detail === "string" ? payload.detail : "Không thể xuất đề thi Word. Vui lòng thử lại.";
          const requestId = typeof payload?.request_id === "string" ? payload.request_id : "";
          toast.error(requestId ? `${detail} (Mã yêu cầu: ${requestId})` : String(detail), { id: toastId });
        } catch {
          toast.error("Lỗi kết nối máy chủ khi xuất đề thi Word. Hãy chắc chắn backend đang chạy.", { id: toastId });
        }
      } else {
        toast.error(normalizeApiError(error, "Lỗi kết nối máy chủ khi xuất đề thi Word. Hãy chắc chắn backend đang chạy."), {
          id: toastId,
        });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[85vh] flex flex-col items-center justify-center p-4 sm:p-8 app-bg">
      <div className="w-full max-w-4xl hero-panel overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-700">
        <div className="flex flex-col items-start gap-5 border-b border-slate-100 bg-white px-8 py-6 sm:flex-row sm:items-center">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-indigo-100 bg-indigo-50 shadow-inner">
            <FileText className="h-7 w-7 text-indigo-600" />
          </div>
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-black tracking-tight text-slate-800">
              Tạo đề Word <span className="rounded-md bg-indigo-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-white">Mới</span>
            </h1>
            <p className="mt-1 text-sm font-medium text-slate-500">Sinh đề theo form có sẵn, lấy câu từ ngân hàng và chỉ bổ sung khi thiếu câu cho một mã đề.</p>
          </div>
        </div>

        <div className="space-y-8 bg-slate-50/30 p-8">
          <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="absolute left-0 top-0 h-full w-1 bg-blue-500" />
            <h2 className="mb-5 flex items-center gap-2 text-sm font-black uppercase tracking-widest text-slate-800">
              <BookOpen className="h-4 w-4 text-blue-500" /> Bối cảnh học phần
            </h2>

            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Chọn lớp học</label>
                <select
                  value={selectedClassId}
                  onChange={handleClassChange}
                  className="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700 shadow-sm outline-none transition-all focus:bg-white focus:ring-2 focus:ring-blue-500"
                >
                  {classList.length === 0 ? (
                    <option value="">Chưa có lớp</option>
                  ) : (
                    classList.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} - {item.subject}
                      </option>
                    ))
                  )}
                </select>
              </div>
              <div>
                <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Môn học đang chọn</label>
                <div className="w-full cursor-not-allowed rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm font-bold text-slate-500">
                  {subject || "Chưa chọn lớp"}
                </div>
              </div>
            </div>
          </div>

          <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="absolute left-0 top-0 h-full w-1 bg-indigo-500" />
            <h2 className="mb-5 flex items-center gap-2 text-sm font-black uppercase tracking-widest text-slate-800">
              <Settings2 className="h-4 w-4 text-indigo-500" /> Cấu hình sinh đề
            </h2>

            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
              <div>
                <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Loại đề</label>
                <select
                  value={examType}
                  onChange={(e) => setExamType(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="trắc nghiệm">Trắc nghiệm</option>
                  <option value="tự luận">Tự luận</option>
                </select>
              </div>

              <div>
                <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Mức độ</label>
                <select
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="Cơ bản">Cơ bản</option>
                  <option value="Trung bình">Trung bình</option>
                  <option value="Nâng cao">Nâng cao</option>
                </select>
              </div>

              <div>
                <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Số câu hỏi</label>
                <input
                  type="number"
                  min="1"
                  max="40"
                  value={numQuestions}
                  onChange={(e) => setNumQuestions(Number(e.target.value))}
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-sm font-bold text-slate-900 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="mb-2 block text-[11px] font-black uppercase tracking-wider text-indigo-600">Số mã đề</label>
                <select
                  value={numVersions}
                  onChange={(e) => setNumVersions(Number(e.target.value))}
                  className="w-full rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm font-black text-indigo-700 outline-none transition-all focus:ring-2 focus:ring-indigo-500"
                >
                  <option value={1}>1 mã đề</option>
                  <option value={2}>2 mã đề</option>
                  <option value={3}>3 mã đề</option>
                  <option value={4}>4 mã đề</option>
                </select>
              </div>
            </div>
          </div>

          <div className="flex flex-col items-start gap-5 rounded-2xl border border-indigo-100 bg-gradient-to-r from-blue-50 to-indigo-50 p-6 md:flex-row">
            <div className="rounded-xl bg-white p-3 shadow-sm">
              <FileText className="h-6 w-6 text-indigo-600" />
            </div>
            <div>
              <p className="mb-2 font-black text-slate-800">File Word xuất ra sẽ gồm:</p>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <InfoRow text="Template header chuẩn form hiện có." />
                <InfoRow text="Mỗi mã đề lấy ngẫu nhiên đúng số câu yêu cầu từ ngân hàng." />
                <InfoRow text="Tự xáo trộn thứ tự câu hỏi và đáp án trắc nghiệm." />
                <InfoRow text="Có bảng đáp án ở cuối file để in và đối chiếu." />
              </div>
            </div>
          </div>

          <button
            onClick={handleGenerateAndDownload}
            disabled={loading || classList.length === 0}
            className="flex w-full items-center justify-center gap-3 rounded-2xl bg-slate-900 py-4 text-sm font-black uppercase tracking-widest text-white transition-all hover:bg-indigo-600 hover:shadow-lg hover:shadow-indigo-200 disabled:opacity-50 disabled:hover:bg-slate-900"
          >
            {loading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" /> Đang ghép đề và xáo trộn mã đề...
              </>
            ) : (
              <>
                <Download className="h-5 w-5 text-indigo-300" /> Xuất file Word đề thi
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2">
      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
      <span className="text-xs font-medium text-slate-600">{text}</span>
    </div>
  );
}
