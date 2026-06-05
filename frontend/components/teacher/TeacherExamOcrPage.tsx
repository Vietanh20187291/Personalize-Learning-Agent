"use client";

import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import toast from "react-hot-toast";
import {
  BookOpen,
  CheckCircle2,
  Download,
  FileImage,
  FileScan,
  Files,
  Loader2,
  ScanSearch,
  Settings2,
  UserSquare2,
} from "lucide-react";

import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "../../services/api";

type ClassroomItem = {
  id: number;
  name: string;
  subject: string;
};

type BatchSummary = {
  id: number;
  batch_code: string;
  class_id: number;
  subject_name: string;
  num_questions: number;
  num_versions: number;
  exam_codes: string[];
  created_at: string | null;
  has_generated_docx: boolean;
  has_answer_key_xlsx: boolean;
  download_urls: {
    docx: string | null;
    answer_xlsx: string | null;
    test_sheet_pdf: string | null;
  };
};

type GradingResult = {
  id: number;
  page_number: number;
  student_name_image_url: string;
  predicted_student_name: string;
  predicted_student_name_engine: string;
  edited_student_name?: string;
  display_student_name?: string;
  detected_student_id: string;
  detected_exam_code: string;
  detected_answers: string[];
  correct_count: number;
  total_questions: number;
  score: number;
  grading_status: string;
};

type SubmissionMode = "pdf" | "image";

function formatStatus(status: string) {
  switch (status) {
    case "graded":
      return "Đã chấm";
    case "missing_exam_code":
      return "Thiếu mã đề";
    case "missing_student_id":
      return "Thiếu MSSV";
    case "ambiguous_answers":
      return "Tô mờ / nhiều lựa chọn";
    case "unknown_exam_code":
      return "Không khớp mã đề";
    default:
      return status || "Chờ xử lý";
  }
}

export default function TeacherExamOcrPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  const examOcrApiBase = `${apiBaseUrl}/api/exam/ocr`;
  const shortTimeoutMs = 15000;

  const [classList, setClassList] = useState<ClassroomItem[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<number | "">("");
  const [subject, setSubject] = useState("");
  const [numQuestions, setNumQuestions] = useState<number>(20);
  const [numVersions, setNumVersions] = useState<number>(2);
  const [level, setLevel] = useState("Trung bình");
  const [studentIdColumns, setStudentIdColumns] = useState<number>(8);
  const [generating, setGenerating] = useState(false);
  const [grading, setGrading] = useState(false);
  const [batchSummary, setBatchSummary] = useState<BatchSummary | null>(null);
  const [submissionMode, setSubmissionMode] = useState<SubmissionMode>("pdf");
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [answerKeyFile, setAnswerKeyFile] = useState<File | null>(null);
  const [gradingResults, setGradingResults] = useState<GradingResult[]>([]);
  const [editedNames, setEditedNames] = useState<Record<number, string>>({});
  const [savingNameIds, setSavingNameIds] = useState<Record<number, boolean>>({});

  useEffect(() => {
    const fetchClasses = async () => {
      const teacherId = localStorage.getItem("userId") || localStorage.getItem("user_id");
      if (!teacherId) return;

      try {
        const response = await axios.get(`${apiBaseUrl}/api/classroom/teacher/${teacherId}`, {
          timeout: shortTimeoutMs,
        });
        const classes = Array.isArray(response.data) ? response.data : [];
        setClassList(classes);
        if (classes.length > 0) {
          setSelectedClassId(classes[0].id);
          setSubject(classes[0].subject);
        }
      } catch (error) {
        console.error("Không lấy được danh sách lớp tạo đề thi:", error);
      }
    };

    void fetchClasses();
  }, [apiBaseUrl]);

  useEffect(() => {
    setEditedNames(
      gradingResults.reduce<Record<number, string>>((accumulator, item) => {
        accumulator[item.id] = item.display_student_name || item.edited_student_name || item.predicted_student_name || "";
        return accumulator;
      }, {}),
    );
  }, [gradingResults]);

  const canGenerate = selectedClassId && subject && classList.length > 0;
  const scoreAverage = useMemo(() => {
    if (gradingResults.length === 0) return null;
    const total = gradingResults.reduce((sum, item) => sum + Number(item.score || 0), 0);
    return (total / gradingResults.length).toFixed(2);
  }, [gradingResults]);

  const selectedImageNames = useMemo(() => imageFiles.map((file) => file.name).join(", "), [imageFiles]);

  const handleClassChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const classId = Number(event.target.value);
    setSelectedClassId(classId);
    const selected = classList.find((item) => item.id === classId);
    if (selected) setSubject(selected.subject);
  };

  const fetchBatchSummary = async (batchId: string | number) => {
    const response = await apiClient.get(`${examOcrApiBase}/batches/${batchId}`, {
      ...longRequestConfig,
    });
    const summary = response.data as BatchSummary;
    setBatchSummary(summary);
    return summary;
  };

  const initBatchForGrading = async () => {
    if (!selectedClassId) {
      throw new Error("Vui lòng chọn lớp học trước khi chấm OCR.");
    }

    const teacherIdRaw = localStorage.getItem("userId") || localStorage.getItem("user_id");
    const teacherId = teacherIdRaw ? Number(teacherIdRaw) : null;
    const response = await apiClient.post(
      `${examOcrApiBase}/init-batch`,
      {
        teacher_id: Number.isFinite(teacherId) ? teacherId : null,
        class_id: selectedClassId,
        num_questions: numQuestions,
        student_id_columns: studentIdColumns,
      },
      {
        ...longRequestConfig,
      },
    );

    const summary = response.data as BatchSummary;
    setBatchSummary(summary);
    return summary;
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

  const downloadBatchFile = async (relativeUrl: string | null, fallbackFilename: string) => {
    if (!relativeUrl) {
      toast.error("Batch hiện tại chưa có file này để tải.");
      return;
    }

    const response = await apiClient.get(`${apiBaseUrl}${relativeUrl}`, {
      ...longRequestConfig,
      responseType: "blob",
    });
    triggerBlobDownload(new Blob([response.data]), fallbackFilename);
  };

  const handleGenerateAndDownload = async () => {
    if (!canGenerate) {
      toast.error("Vui lòng chọn lớp và môn học.");
      return;
    }

    setGenerating(true);
    const toastId = toast.loading("Đang sinh đề trắc nghiệm OCR...");

    try {
      const teacherIdRaw = localStorage.getItem("userId") || localStorage.getItem("user_id");
      const teacherId = teacherIdRaw ? Number(teacherIdRaw) : null;

      const response = await runLongRequest(
        () =>
          apiClient.post(
            `${examOcrApiBase}/generate-word`,
            {
              teacher_id: Number.isFinite(teacherId) ? teacherId : null,
              class_id: selectedClassId,
              subject,
              exam_type: "trac nghiem",
              num_questions: numQuestions,
              num_versions: numVersions,
              level,
              student_id_columns: studentIdColumns,
            },
            {
              ...longRequestConfig,
              responseType: "blob",
            },
          ),
        { slowDelayMs: 3500 },
      );

      triggerBlobDownload(new Blob([response.data]), `DeThiOCR_${subject.replace(/\s+/g, "")}.docx`);

      const batchId = response.headers["x-exam-ocr-batch-id"];
      if (batchId) {
        const summary = await fetchBatchSummary(batchId);
        if (summary.download_urls.answer_xlsx) {
          await downloadBatchFile(summary.download_urls.answer_xlsx, `DapAnOCR_${summary.batch_code}.xlsx`);
        }
        setGradingResults([]);
        setPdfFile(null);
        setImageFiles([]);
        setAnswerKeyFile(null);
      }

      toast.success("Đã tạo file Word đề thi OCR.", { id: toastId });
    } catch (error) {
      console.error(error);
      if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
        try {
          const text = await error.response.data.text();
          const payload = JSON.parse(text);
          toast.error(String(payload?.detail || "Không thể sinh đề OCR."), { id: toastId });
        } catch {
          toast.error("Lỗi kết nối máy chủ khi sinh đề OCR.", { id: toastId });
        }
      } else {
        toast.error(normalizeApiError(error, "Không thể sinh đề OCR."), { id: toastId });
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleGradeSubmission = async () => {
    if (submissionMode === "pdf" && !pdfFile) {
      toast.error("Vui lòng chọn file PDF để chấm.");
      return;
    }
    if (submissionMode === "image" && imageFiles.length === 0) {
      toast.error("Vui lòng chọn ít nhất một ảnh để chấm.");
      return;
    }
    if (!batchSummary && !answerKeyFile) {
      toast.error("Nếu chưa sinh đề trước đó, bạn cần tải lên file Excel đáp án để hệ thống khởi tạo batch chấm.");
      return;
    }

    setGrading(true);
    const loadingText = submissionMode === "pdf" ? "Đang đọc PDF và chấm OMR..." : "Đang xử lý ảnh và chấm OMR...";
    const toastId = toast.loading(loadingText);

    try {
      const activeBatch = batchSummary ?? (await initBatchForGrading());
      const formData = new FormData();
      formData.append("batch_id", String(activeBatch.id));
      if (submissionMode === "pdf" && pdfFile) {
        formData.append("pdf_file", pdfFile);
      }
      if (submissionMode === "image") {
        imageFiles.forEach((file) => formData.append("image_files", file));
      }
      if (answerKeyFile) {
        formData.append("answer_key_file", answerKeyFile);
      }

      const response = await runLongRequest(
        () =>
          apiClient.post(`${examOcrApiBase}/grade-pdf`, formData, {
            ...longRequestConfig,
            headers: {
              "Content-Type": "multipart/form-data",
            },
          }),
        { slowDelayMs: 3500 },
      );

      const results = Array.isArray(response.data?.results) ? (response.data.results as GradingResult[]) : [];
      setGradingResults(results);
      if (response.data?.batch) {
        setBatchSummary(response.data.batch as BatchSummary);
      }
      toast.success(`Đã xử lý ${results.length} phiếu trả lời.`, { id: toastId });
    } catch (error) {
      console.error(error);
      toast.error(normalizeApiError(error, "Không thể chấm OCR từ tệp đã tải lên."), { id: toastId });
    } finally {
      setGrading(false);
    }
  };

  const handleEditedNameChange = (resultId: number, value: string) => {
    setEditedNames((current) => ({
      ...current,
      [resultId]: value,
    }));
  };

  const handleEditedNameBlur = async (result: GradingResult) => {
    const nextValue = (editedNames[result.id] ?? "").trim();
    const previousValue = (result.display_student_name || result.edited_student_name || result.predicted_student_name || "").trim();
    if (nextValue === previousValue) {
      return;
    }

    setSavingNameIds((current) => ({
      ...current,
      [result.id]: true,
    }));

    try {
      const response = await apiClient.patch(
        `${examOcrApiBase}/results/${result.id}/student-name`,
        { student_name: nextValue },
        { timeout: shortTimeoutMs },
      );
      const updated = response.data as Partial<GradingResult>;
      setGradingResults((current) =>
        current.map((item) =>
          item.id === result.id
            ? {
                ...item,
                ...updated,
              }
            : item,
        ),
      );
      toast.success("Đã lưu tên sinh viên.");
    } catch (error) {
      console.error(error);
      toast.error(normalizeApiError(error, "Không lưu được tên sinh viên."));
    } finally {
      setSavingNameIds((current) => ({
        ...current,
        [result.id]: false,
      }));
    }
  };

  return (
    <div className="min-h-[85vh] p-4 sm:p-8 app-bg">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <div className="hero-panel overflow-hidden">
          <div className="flex flex-col items-start gap-5 border-b border-slate-100 bg-white px-8 py-6 sm:flex-row sm:items-center">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-emerald-100 bg-emerald-50 shadow-inner">
              <ScanSearch className="h-7 w-7 text-emerald-600" />
            </div>
            <div>
              <h1 className="flex items-center gap-2 text-2xl font-black tracking-tight text-slate-800">
                Đề thi trắc nghiệm & OMR
                <span className="rounded-md bg-emerald-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-white">giảng viên</span>
              </h1>
              <p className="mt-1 text-sm font-medium text-slate-500">
                Tạo đề trắc nghiệm, tải phiếu OMR dùng chung, tải file đáp án Excel và chấm bài bằng PDF hoặc ảnh ngay trên một trang.
              </p>
            </div>
          </div>

          <div className="grid gap-6 p-6 lg:grid-cols-[1.15fr_0.85fr]">
            <section className="space-y-6 rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="absolute left-0 top-0 h-full w-1 bg-emerald-500" />
                <h2 className="mb-5 flex items-center gap-2 text-sm font-black uppercase tracking-widest text-slate-800">
                  <BookOpen className="h-4 w-4 text-emerald-500" /> Bối cảnh học phần
                </h2>

                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  <div>
                    <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Chọn lớp học</label>
                    <select
                      value={selectedClassId}
                      onChange={handleClassChange}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700 outline-none transition-all focus:ring-2 focus:ring-emerald-500"
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
                    <div className="rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-sm font-bold text-slate-500">
                      {subject || "Chưa chọn lớp"}
                    </div>
                  </div>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <div className="absolute left-0 top-0 h-full w-1 bg-cyan-500" />
                <h2 className="mb-5 flex items-center gap-2 text-sm font-black uppercase tracking-widest text-slate-800">
                  <Settings2 className="h-4 w-4 text-cyan-500" /> Cấu hình sinh đề trắc nghiệm OCR
                </h2>

                <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-4">
                  <div>
                    <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Mức độ</label>
                    <select
                      value={level}
                      onChange={(event) => setLevel(event.target.value)}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-700 outline-none transition-all focus:ring-2 focus:ring-cyan-500"
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
                      min={1}
                      max={120}
                      value={numQuestions}
                      onChange={(event) => setNumQuestions(Number(event.target.value))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-sm font-bold text-slate-900 outline-none transition-all focus:ring-2 focus:ring-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Số mã đề</label>
                    <input
                      type="number"
                      min={1}
                      max={8}
                      value={numVersions}
                      onChange={(event) => setNumVersions(Number(event.target.value))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-sm font-bold text-slate-900 outline-none transition-all focus:ring-2 focus:ring-cyan-500"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-[11px] font-bold uppercase tracking-wider text-slate-500">Cột MSSV</label>
                    <input
                      type="number"
                      min={4}
                      max={12}
                      value={studentIdColumns}
                      onChange={(event) => setStudentIdColumns(Number(event.target.value))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-center text-sm font-bold text-slate-900 outline-none transition-all focus:ring-2 focus:ring-cyan-500"
                    />
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-emerald-100 bg-gradient-to-r from-emerald-50 to-cyan-50 p-6">
                <p className="mb-2 font-black text-slate-800">Luồng tạo đề và chấm OMR sẽ hỗ trợ:</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <InfoRow text="Sinh đề trắc nghiệm theo lớp học, số câu, số mã đề và mức độ mong muốn." />
                  <InfoRow text="Tự tạo 1 phiếu trả lời OMR dùng chung cho toàn bộ batch đề." />
                  <InfoRow text="Tải kèm file đáp án Excel chuyên dụng để in, lưu trữ hoặc upload lại khi chấm." />
                  <InfoRow text="Chấm bài từ PDF scan hoặc ảnh chụp với đầy đủ bước xử lý OMR nâng cao." />
                </div>
              </div>

              <button
                onClick={() => void handleGenerateAndDownload()}
                disabled={generating || !canGenerate}
                className="flex w-full items-center justify-center gap-3 rounded-2xl bg-slate-900 py-4 text-sm font-black uppercase tracking-widest text-white transition-all hover:bg-emerald-600 disabled:opacity-50 disabled:hover:bg-slate-900"
              >
                {generating ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" /> Đang sinh đề và phiếu OMR...
                  </>
                ) : (
                  <>
                    <Download className="h-5 w-5 text-emerald-300" /> Tạo và tải bộ đề thi OCR
                  </>
                )}
              </button>
            </section>

            <section className="space-y-6 rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center gap-3">
                <Files className="h-5 w-5 text-emerald-600" />
                <h2 className="text-lg font-black text-slate-900">Batch đề thi hiện tại</h2>
              </div>

              {batchSummary ? (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Batch</p>
                    <p className="mt-1 text-base font-black text-slate-900">{batchSummary.batch_code}</p>
                    <p className="mt-2 text-sm font-medium text-slate-600">
                      {batchSummary.subject_name} - {batchSummary.num_questions} câu - {batchSummary.num_versions} mã đề
                    </p>
                    <p className="mt-2 text-xs font-medium text-slate-500">
                      {batchSummary.has_generated_docx
                        ? "Batch này đã có file Word đề thi OCR để tải lại."
                        : "Đây là batch chấm tạm thời để dùng layout OMR và nhận đáp án từ file Excel tải lên."}
                    </p>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-3">
                    {batchSummary.download_urls.docx ? (
                      <button
                        onClick={() => void downloadBatchFile(batchSummary.download_urls.docx, `DeThiOCR_${batchSummary.batch_code}.docx`)}
                        className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-black text-slate-800 transition hover:border-emerald-300 hover:text-emerald-700"
                      >
                        <Download className="h-4 w-4" /> Tải file Word đề thi
                      </button>
                    ) : (
                      <div className="flex items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-center text-xs font-semibold text-slate-400">
                        Chưa có file Word
                      </div>
                    )}
                    {batchSummary.download_urls.answer_xlsx ? (
                      <button
                        onClick={() => void downloadBatchFile(batchSummary.download_urls.answer_xlsx, `DapAnOCR_${batchSummary.batch_code}.xlsx`)}
                        className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-black text-slate-800 transition hover:border-cyan-300 hover:text-cyan-700"
                      >
                        <Files className="h-4 w-4" /> Tải biểu mẫu đáp án Excel
                      </button>
                    ) : (
                      <div className="flex items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-center text-xs font-semibold text-slate-400">
                        Chưa có đáp án lưu sẵn
                      </div>
                    )}
                    <button
                      onClick={() => void downloadBatchFile(batchSummary.download_urls.test_sheet_pdf, `TestSheet_${batchSummary.batch_code}.pdf`)}
                      className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-black text-slate-800 transition hover:border-amber-300 hover:text-amber-700"
                    >
                      <CheckCircle2 className="h-4 w-4" /> Tải phiếu mẫu OMR
                    </button>
                  </div>

                  <button
                    onClick={() => void downloadBatchFile(batchSummary.download_urls.test_sheet_pdf, `TestSheet_${batchSummary.batch_code}.pdf`)}
                    className="flex w-full items-center justify-center gap-3 rounded-2xl bg-amber-500 py-4 text-sm font-black uppercase tracking-widest text-white transition hover:bg-amber-600"
                  >
                    <CheckCircle2 className="h-5 w-5" /> Tải 1 phiếu mẫu trả lời trắc nghiệm
                  </button>
                  <p className="-mt-2 text-xs font-medium text-slate-500">
                    Phiếu này đã được tô sẵn MSSV ngẫu nhiên và đáp án ngẫu nhiên. Bạn chỉ cần in ra và tự tô thêm mã đề để kiểm tra luồng chấm.
                  </p>

                  {batchSummary.exam_codes.length > 0 ? (
                    <div>
                      <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Mã đề đã sinh</p>
                      <div className="flex flex-wrap gap-2">
                        {batchSummary.exam_codes.map((code) => (
                          <span key={code} className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-black text-emerald-700">
                            {code}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm font-medium text-slate-500">
                  Chưa có batch nào trong phiên này. Bạn vẫn có thể tải lên file đáp án Excel và chấm ngay; hệ thống sẽ tự khởi tạo batch chấm tạm thời.
                </div>
              )}

              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center gap-2 text-slate-800">
                  <FileScan className="h-4 w-4 text-emerald-600" />
                  <p className="text-sm font-black">Chấm bài từ PDF hoặc ảnh</p>
                </div>
                <p className="mt-2 text-xs font-medium text-slate-500">
                  Bạn có thể chấm ngay cả khi chưa sinh đề trước đó, miễn là tải lên file đáp án Excel để hệ thống đối chiếu.
                </p>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => {
                      setSubmissionMode("pdf");
                      setImageFiles([]);
                    }}
                    className={`flex items-center justify-center gap-2 rounded-2xl border px-4 py-3 text-sm font-black transition ${
                      submissionMode === "pdf"
                        ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                        : "border-slate-200 bg-slate-50 text-slate-600 hover:border-emerald-200"
                    }`}
                  >
                    <FileScan className="h-4 w-4" /> Chấm bằng PDF
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSubmissionMode("image");
                      setPdfFile(null);
                    }}
                    className={`flex items-center justify-center gap-2 rounded-2xl border px-4 py-3 text-sm font-black transition ${
                      submissionMode === "image"
                        ? "border-cyan-300 bg-cyan-50 text-cyan-700"
                        : "border-slate-200 bg-slate-50 text-slate-600 hover:border-cyan-200"
                    }`}
                  >
                    <FileImage className="h-4 w-4" /> Chấm bằng ảnh
                  </button>
                </div>

                {submissionMode === "pdf" ? (
                  <div>
                    <label className="mb-2 mt-4 block text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Tải lên PDF scan</label>
                    <input
                      type="file"
                      accept="application/pdf"
                      onChange={(event) => {
                        setPdfFile(event.target.files?.[0] || null);
                        setImageFiles([]);
                      }}
                      className="block w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-medium text-slate-700"
                    />
                    <p className="mt-2 text-xs font-medium text-slate-500">
                      Mỗi trang PDF tương ứng 1 phiếu trả lời OMR đã scan.
                    </p>
                  </div>
                ) : (
                  <div>
                    <label className="mb-2 mt-4 block text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Tải lên ảnh phiếu trả lời</label>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={(event) => {
                        setImageFiles(Array.from(event.target.files || []));
                        setPdfFile(null);
                      }}
                      className="block w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-medium text-slate-700"
                    />
                    <p className="mt-2 text-xs font-medium text-slate-500">
                      Hỗ trợ chọn một hoặc nhiều ảnh. Hệ thống sẽ tăng cường xử lý cho ảnh mờ, nhiễu, sáng tối không đều và tô chưa kín trước khi đọc OMR.
                    </p>
                    {imageFiles.length > 0 ? (
                      <div className="mt-2 rounded-xl border border-cyan-100 bg-cyan-50 px-3 py-2 text-xs font-medium text-cyan-700">
                        Đã chọn {imageFiles.length} ảnh: {selectedImageNames}
                      </div>
                    ) : null}
                  </div>
                )}

                <label className="mb-2 mt-4 block text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
                  Tải biểu mẫu đáp án Excel {batchSummary ? "(tuỳ chọn)" : "(bắt buộc nếu chưa sinh đề)"}
                </label>
                <input
                  type="file"
                  accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={(event) => setAnswerKeyFile(event.target.files?.[0] || null)}
                  className="block w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-medium text-slate-700"
                />
                <p className="mt-2 text-xs font-medium text-slate-500">
                  Nếu tải lên Excel, hệ thống sẽ chấm theo file đáp án này thay vì đáp án lưu sẵn trong batch.
                </p>

                <button
                  onClick={() => void handleGradeSubmission()}
                  disabled={grading || (submissionMode === "pdf" ? !pdfFile : imageFiles.length === 0)}
                  className="mt-4 flex w-full items-center justify-center gap-3 rounded-2xl bg-emerald-600 py-3 text-sm font-black uppercase tracking-widest text-white transition hover:bg-emerald-700 disabled:opacity-50"
                >
                  {grading ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" /> Đang chấm OCR...
                    </>
                  ) : (
                    <>
                      <FileScan className="h-5 w-5" /> Tải lên và chấm bài
                    </>
                  )}
                </button>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center gap-2 text-slate-800">
                  <UserSquare2 className="h-4 w-4 text-cyan-600" />
                  <p className="text-sm font-black">Tóm tắt lần chấm gần nhất</p>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <MetricCard label="Số phiếu" value={String(gradingResults.length)} />
                  <MetricCard label="Điểm TB" value={scoreAverage ?? "--"} />
                </div>
              </div>
            </section>
          </div>
        </div>

        <section className="hero-panel overflow-hidden">
          <div className="border-b border-slate-100 bg-white px-6 py-5">
            <h2 className="text-xl font-black text-slate-900">Kết quả chấm OCR</h2>
            <p className="mt-1 text-sm font-medium text-slate-500">
              Hiển thị ảnh crop tên, MSSV, mã đề, đáp án nhận diện và điểm chấm tự động.
            </p>
          </div>

          <div className="overflow-x-auto bg-white">
            {gradingResults.length === 0 ? (
              <div className="px-6 py-12 text-center text-sm font-medium text-slate-500">
                Chưa có kết quả chấm nào để hiển thị.
              </div>
            ) : (
              <table className="min-w-full border-collapse">
                <thead>
                  <tr className="bg-slate-50 text-left text-[11px] font-black uppercase tracking-[0.18em] text-slate-500">
                    <th className="border-b border-slate-200 px-4 py-3">Trang</th>
                    <th className="border-b border-slate-200 px-4 py-3">Ảnh tên SV</th>
                    <th className="border-b border-slate-200 px-4 py-3">Tên sinh viên</th>
                    <th className="border-b border-slate-200 px-4 py-3">MSSV</th>
                    <th className="border-b border-slate-200 px-4 py-3">Mã đề</th>
                    <th className="border-b border-slate-200 px-4 py-3">Đáp án nhận diện</th>
                    <th className="border-b border-slate-200 px-4 py-3">Điểm</th>
                    <th className="border-b border-slate-200 px-4 py-3">Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {gradingResults.map((result) => (
                    <tr key={result.id} className="align-top text-sm text-slate-700">
                      <td className="border-b border-slate-100 px-4 py-4 font-black text-slate-900">{result.page_number}</td>
                      <td className="border-b border-slate-100 px-4 py-4">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={`${apiBaseUrl}${result.student_name_image_url}`}
                          alt={`Tên sinh viên trang ${result.page_number}`}
                          className="h-20 w-52 rounded-xl border border-slate-200 object-cover"
                        />
                      </td>
                      <td className="border-b border-slate-100 px-4 py-4">
                        <input
                          type="text"
                          value={editedNames[result.id] ?? result.predicted_student_name ?? ""}
                          onChange={(event) => handleEditedNameChange(result.id, event.target.value)}
                          onBlur={() => void handleEditedNameBlur(result)}
                          placeholder="Nhập họ tên nếu cần sửa"
                          spellCheck={false}
                          className="min-w-40 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-semibold text-slate-700 outline-none transition focus:border-emerald-400 focus:bg-white focus:ring-2 focus:ring-emerald-100"
                        />
                        <div className="mt-2 text-xs font-medium text-slate-500">
                          {savingNameIds[result.id] ? "Đang lưu..." : `OCR: ${result.predicted_student_name_engine || "-"}`}
                        </div>
                      </td>
                      <td className="border-b border-slate-100 px-4 py-4 font-bold">{result.detected_student_id || "-"}</td>
                      <td className="border-b border-slate-100 px-4 py-4 font-bold">{result.detected_exam_code || "-"}</td>
                      <td className="border-b border-slate-100 px-4 py-4">
                        <div className="max-w-[28rem] text-xs leading-6 text-slate-600">
                          {result.detected_answers.map((answer, index) => (
                            <span key={`${result.id}_${index}`} className="mr-2 inline-block rounded-full bg-slate-100 px-2 py-0.5 font-semibold text-slate-700">
                              {index + 1}:{answer || "-"}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="border-b border-slate-100 px-4 py-4">
                        <div className="font-black text-emerald-700">{result.score.toFixed(2)}</div>
                        <div className="text-xs font-medium text-slate-500">
                          {result.correct_count}/{result.total_questions} đúng
                        </div>
                      </td>
                      <td className="border-b border-slate-100 px-4 py-4">
                        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-bold text-slate-700">
                          {formatStatus(result.grading_status)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
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

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-black text-slate-900">{value}</p>
    </div>
  );
}
