'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Download,
  FileText,
  FolderOpen,
  Loader2,
  Search,
  Sparkles,
  Trash2,
  Wand2,
} from 'lucide-react';
import toast from 'react-hot-toast';

import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from '../../../services/api';
import { confirmAlert } from '../../../services/alerts';

interface DocumentData {
  id: number;
  title: string;
  subject: string;
  file_path: string;
  created_at: string;
  is_visible_to_students?: boolean;
}

export default function DocumentLibrary() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8010';
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [generatingId, setGeneratingId] = useState<number | null>(null);
  const [slowGeneratingId, setSlowGeneratingId] = useState<number | null>(null);

  const fetchDocs = async () => {
    try {
      const classId = localStorage.getItem('classId') || '2';
      const res = await apiClient.get(`${apiBaseUrl}/api/documents/class-documents/${classId}`);
      setDocuments(Array.isArray(res.data) ? res.data : []);
    } catch {
      toast.error('Lỗi khi tải kho tài liệu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchDocs();
  }, []);

  const handleDelete = async (id: number, title: string) => {
    const confirmed = await confirmAlert({
      title: "Xóa tài liệu",
      message: `Xóa tài liệu "${title}"?`,
      confirmText: "Xóa ngay",
      cancelText: "Hủy",
      tone: "danger",
    });
    if (!confirmed) return;
    setDeleteId(id);
    try {
      await apiClient.delete(`${apiBaseUrl}/api/documents/delete/${id}`);
      setDocuments((prev) => prev.filter((doc) => doc.id !== id));
      toast.success('Đã xóa tài liệu');
    } catch {
      toast.error('Không thể xóa tài liệu');
    } finally {
      setDeleteId(null);
    }
  };

  const handleGenerateQuestionBank = async (doc: DocumentData) => {
    const confirmed = await confirmAlert({
      title: "Tạo lại bộ câu hỏi",
      message: `Tạo lại nhanh 20 câu cho tài liệu "${doc.title}"? Hệ thống sẽ thay thế bộ câu hỏi cũ.`,
      confirmText: "Tạo lại",
      cancelText: "Hủy",
      tone: "danger",
    });
    if (!confirmed) {
      return;
    }

    setGeneratingId(doc.id);
    try {
      const res = await runLongRequest(
        () =>
          apiClient.post(
            `${apiBaseUrl}/api/documents/generate-question-bank/${doc.id}?target_count=20`,
            undefined,
            longRequestConfig
          ),
        {
          onSlowStateChange: (isSlow) => setSlowGeneratingId(isSlow ? doc.id : null),
          slowDelayMs: 4000,
        }
      );
      toast.success(
        `Đã tạo ${res.data?.generated_count ?? 0}/${res.data?.target_count ?? 20} câu cho ${doc.title}`
      );
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, 'Không thể tạo bộ đề cho tài liệu này'));
    } finally {
      setGeneratingId(null);
      setSlowGeneratingId(null);
    }
  };

  const filteredDocuments = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) return documents;
    return documents.filter((doc) => {
      const title = String(doc.title || '').toLowerCase();
      const subject = String(doc.subject || '').toLowerCase();
      return title.includes(keyword) || subject.includes(keyword);
    });
  }, [documents, searchTerm]);

  return (
    <div className="page-shell app-bg">
      <div className="page-container space-y-6">
        <section className="hero-panel overflow-hidden">
          <div className="grid gap-0 lg:grid-cols-[0.92fr_1.08fr]">
            <div className="section-panel rounded-none border-0 border-r border-[rgba(24,24,27,0.08)] p-6 text-zinc-950 md:p-8">
              <p className="text-[10px] font-black uppercase tracking-[0.34em] text-zinc-500">
                Document dock
              </p>
              <h1 className="mt-3 text-3xl font-black uppercase md:text-5xl">
                Xưởng tài liệu của lớp
              </h1>
              <p className="mt-4 max-w-xl text-sm leading-7 text-zinc-700">
                Thay vì list cũ, màn này chuyển sang dạng inventory deck: tìm nhanh, tải xuống,
                xóa tài liệu và sinh lại nhanh bộ câu hỏi từ từng file mà không cần bật hiển thị thủ công.
              </p>

              <div className="mt-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">
                    Tổng tài liệu
                  </p>
                  <p className="mt-2 text-3xl font-black text-zinc-950">{documents.length}</p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">
                    Hiển thị cho SV
                  </p>
                  <p className="mt-2 text-3xl font-black text-zinc-950">
                    {documents.length}
                  </p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">
                    Kết quả lọc
                  </p>
                  <p className="mt-2 text-3xl font-black text-zinc-950">{filteredDocuments.length}</p>
                </div>
              </div>
            </div>

            <div className="soft-grid p-6 md:p-8">
              <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
                <div className="section-panel p-5">
                  <div className="mb-4 flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-[1rem] bg-[var(--accent)] text-white">
                      <Search className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">
                        Search channel
                      </p>
                      <h2 className="text-lg font-black uppercase text-[#251917]">
                        Tìm tài liệu
                      </h2>
                    </div>
                  </div>
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                    <input
                      type="text"
                      value={searchTerm}
                      onChange={(event) => setSearchTerm(event.target.value)}
                      placeholder="Gõ tên tài liệu hoặc môn học"
                      className="app-input pl-11"
                    />
                  </div>
                </div>

                <div className="nova-panel p-5 text-zinc-950">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.3em] text-zinc-500">
                        Question sync
                      </p>
                      <h2 className="mt-2 text-xl font-black uppercase">Kích hoạt bộ đề</h2>
                    </div>
                    <Sparkles className="h-5 w-5 text-[#fbd7ad]" />
                  </div>
                  <p className="mt-3 text-sm leading-7 text-zinc-700">
                    Mỗi tài liệu có thể gọi trực tiếp tác vụ tái sinh nhanh 20 câu hỏi. Khi có treo
                    hay lỗi, log backend sẽ lưu lại request tương ứng để dễ truy vết.
                  </p>
                  {slowGeneratingId ? (
                    <div className="mt-3 rounded-xl border border-indigo-200 bg-white/80 px-3 py-2 text-[12px] font-semibold text-indigo-700">
                      Hệ thống vẫn đang sinh bộ câu hỏi, backend chưa mất kết nối. Vui lòng chờ thêm một chút.
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="section-panel p-5 md:p-6">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-8 w-8 animate-spin text-[var(--brand)]" />
            </div>
          ) : filteredDocuments.length > 0 ? (
            <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
              {filteredDocuments.map((doc) => {
                return (
                  <article
                    key={doc.id}
                    className="group rounded-[1.7rem] border border-[rgba(24,24,27,0.08)] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.92))] p-5 shadow-[0_16px_32px_rgba(15,23,42,0.05)] transition-all hover:-translate-y-1 hover:shadow-[0_24px_44px_rgba(15,23,42,0.1)]"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-start gap-3">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[1.1rem] bg-[rgba(14,116,144,0.12)] text-[var(--accent)]">
                          <FileText className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <p className="line-clamp-2 text-lg font-black uppercase text-[#251917]">
                            {doc.title}
                          </p>
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <span className="rounded-full bg-[linear-gradient(135deg,rgba(185,28,28,0.08),rgba(15,118,110,0.08))] px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-[var(--brand)]">
                              {doc.subject}
                            </span>
                            <span className="rounded-full bg-slate-900/6 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-600">
                              {doc.created_at}
                            </span>
                          </div>
                        </div>
                      </div>

                      <span className="inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-700">
                        Tự hiển thị
                      </span>
                    </div>

                    <div className="mt-5 grid gap-2 sm:grid-cols-2">
                      <a
                        href={`${apiBaseUrl}/${doc.file_path}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center justify-center gap-2 rounded-[1rem] border border-slate-200 bg-white px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-slate-700 transition-all hover:border-[var(--accent)] hover:text-[var(--accent)]"
                      >
                        <FolderOpen className="h-4 w-4" />
                        Mở file
                      </a>
                      <a
                        href={`${apiBaseUrl}/${doc.file_path}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        download={doc.title}
                        className="inline-flex items-center justify-center gap-2 rounded-[1rem] border border-slate-200 bg-white px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-slate-700 transition-all hover:border-[var(--accent)] hover:text-[var(--accent)]"
                      >
                        <Download className="h-4 w-4" />
                        Tải xuống
                      </a>
                    </div>

                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <button
                        onClick={() => void handleGenerateQuestionBank(doc)}
                        disabled={generatingId === doc.id}
                        className="app-btn-primary w-full !justify-center !text-xs"
                      >
                        {generatingId === doc.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Wand2 className="h-4 w-4" />
                        )}
                        Tạo lại 20 câu
                      </button>

                      <button
                        onClick={() => void handleDelete(doc.id, doc.title)}
                        disabled={deleteId === doc.id}
                        className="inline-flex w-full items-center justify-center gap-2 rounded-[1rem] border border-red-200 bg-red-50 px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-red-700 disabled:opacity-50"
                      >
                        {deleteId === doc.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                        Xóa tài liệu
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="rounded-[1.8rem] border border-dashed border-slate-300 bg-[rgba(255,255,255,0.5)] px-6 py-20 text-center">
              <FileText className="mx-auto h-12 w-12 text-slate-300" />
              <p className="mt-4 text-lg font-black uppercase text-slate-500">Không có tài liệu phù hợp</p>
              <p className="mt-2 text-sm text-slate-500">
                Hãy đổi từ khóa tìm kiếm hoặc tải thêm tài liệu cho lớp học này.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
