'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';

import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from '../../../services/api';
import { confirmAlert } from '../../../services/alerts';
import {
  BookOpen,
  FileText,
  Loader2,
  Pencil,
  Plus,
  RefreshCcw,
  Save,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
} from 'lucide-react';

interface DocumentData {
  id: number;
  title?: string;
  filename?: string;
  subject: string;
  subject_id?: number;
  class_id?: number;
  upload_time?: string;
}

interface ClassroomItem {
  id: number;
  name: string;
  subject_id?: number;
}

interface SubjectItem {
  id: number;
  name: string;
  icon?: string;
}

interface QuestionBankItem {
  id: number;
  content: string;
  options: string[];
  correct_answer: string;
  explanation: string;
  difficulty: string;
}

const PAGE_SIZE = 20;

const initialFormState = {
  content: '',
  optionA: '',
  optionB: '',
  optionC: '',
  optionD: '',
  correct_answer: 'A',
  explanation: '',
  difficulty: 'Medium',
};

const normalizeOptions = (raw: unknown): string[] => {
  if (Array.isArray(raw)) return raw.map((item) => String(item));
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item));
      }
    } catch {
      return [];
    }
  }
  return [];
};

export default function TeacherQuestionBankPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8010';
  const subjectQuery = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search).get('subject')?.trim() || ''
    : '';
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [classrooms, setClassrooms] = useState<ClassroomItem[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<number | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<QuestionBankItem[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [appending, setAppending] = useState(false);
  const [slowAppendNotice, setSlowAppendNotice] = useState(false);
  const [savingQuestionId, setSavingQuestionId] = useState<number | null>(null);
  const [deletingQuestionId, setDeletingQuestionId] = useState<number | null>(null);
  const [editingQuestionId, setEditingQuestionId] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [editDraft, setEditDraft] = useState<Partial<QuestionBankItem>>({});
  const [newQuestion, setNewQuestion] = useState(initialFormState);
  const [uploading, setUploading] = useState(false);
  const [deletingDocId, setDeletingDocId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedSubject = useMemo(
    () => subjects.find((item) => item.id === selectedSubjectId) || null,
    [subjects, selectedSubjectId]
  );
  const subjectClassrooms = useMemo(
    () => classrooms.filter((c) => c.subject_id === selectedSubjectId),
    [classrooms, selectedSubjectId]
  );
  const activeClassId = subjectClassrooms[0]?.id ?? null;
  const selectedDocument = useMemo(
    () => documents.find((doc) => doc.id === selectedDocId) || null,
    [documents, selectedDocId]
  );
  const totalPages = Math.max(1, Math.ceil(questions.length / PAGE_SIZE));
  const paginatedQuestions = useMemo(
    () => questions.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [questions, currentPage]
  );

  const fetchSubjects = async () => {
    try {
      const res = await apiClient.get(`${apiBaseUrl}/api/subjects`);
      const payload = Array.isArray(res.data) ? res.data : [];
      const normalized = payload
        .map((item: any) => ({
          id: Number(item.id),
          name: String(item.name || '').trim(),
          icon: item.icon ? String(item.icon) : undefined,
        }))
        .filter((item: SubjectItem) => Number.isFinite(item.id) && !!item.name);

      setSubjects(normalized);
      setSelectedSubjectId((prev) =>
        prev && normalized.some((subject) => subject.id === prev)
          ? prev
          : normalized[0]?.id ?? null
      );
    } catch {
      toast.error('Không thể tải danh sách môn học');
      setSubjects([]);
      setSelectedSubjectId(null);
    }
  };

  const fetchClassrooms = async () => {
    try {
      const teacherId = (localStorage.getItem('userId') || '').trim();
      if (!teacherId) return;
      const res = await apiClient.get(`${apiBaseUrl}/api/classroom/teacher/${teacherId}`);
      const payload = Array.isArray(res.data) ? res.data : [];
      setClassrooms(
        payload.map((item: any) => ({
          id: Number(item.id),
          name: String(item.name || '').trim(),
          subject_id: item.subject_id != null ? Number(item.subject_id) : undefined,
        }))
      );
    } catch {
      setClassrooms([]);
    }
  };

  const handleUploadDocument = async (file: File) => {
    if (!selectedSubjectId || !activeClassId) {
      toast.error('Hãy chọn môn học (có lớp) trước khi tải tài liệu lên.');
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('class_id', String(activeClassId));
      const teacherId = (localStorage.getItem('userId') || '').trim();
      if (teacherId) formData.append('teacher_id', teacherId);
      await runLongRequest(
        () =>
          apiClient.post(`${apiBaseUrl}/api/documents/upload`, formData, {
            ...longRequestConfig,
            headers: { 'Content-Type': 'multipart/form-data' },
          }),
        { onSlowStateChange: setSlowAppendNotice, slowDelayMs: 4000 }
      );
      toast.success(`Đã tải lên "${file.name}".`);
      await fetchDocuments(selectedSubjectId);
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, 'Không thể tải tài liệu lên'));
    } finally {
      setUploading(false);
      setSlowAppendNotice(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDeleteDocument = async (doc: DocumentData) => {
    const confirmed = await confirmAlert({
      title: 'Xóa tài liệu',
      message: `Xóa tài liệu "${doc.title || doc.filename}"? Toàn bộ câu hỏi gắn với tài liệu này cũng sẽ bị ảnh hưởng.`,
      confirmText: 'Xóa ngay',
      cancelText: 'Hủy',
      tone: 'danger',
    });
    if (!confirmed) return;
    setDeletingDocId(doc.id);
    try {
      await apiClient.delete(`${apiBaseUrl}/api/documents/delete/${doc.id}`);
      toast.success('Đã xóa tài liệu');
      // Nếu đang xem câu hỏi của tài liệu vừa xóa thì dọn sạch
      if (selectedDocId === doc.id) {
        setSelectedDocId(null);
        setQuestions([]);
      }
      if (selectedSubjectId) await fetchDocuments(selectedSubjectId);
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, 'Không thể xóa tài liệu'));
    } finally {
      setDeletingDocId(null);
    }
  };

  const fetchDocuments = async (subjectId: number) => {
    try {
      setLoadingDocs(true);
      const teacherId = (localStorage.getItem('userId') || '').trim();
      const params = new URLSearchParams();
      if (teacherId) {
        params.set('teacher_id', teacherId);
      }

      const url = `${apiBaseUrl}/api/documents/by-subject/${subjectId}${
        params.toString() ? `?${params.toString()}` : ''
      }`;
      const res = await apiClient.get(url);
      const docs = Array.isArray(res.data) ? res.data : [];
      setDocuments(docs);
      setSelectedDocId((prev) =>
        prev && docs.some((doc: DocumentData) => doc.id === prev) ? prev : docs[0]?.id ?? null
      );

      if (!docs.length) {
        setQuestions([]);
      }
    } catch {
      toast.error('Không thể tải danh sách tài liệu');
      setDocuments([]);
      setSelectedDocId(null);
      setQuestions([]);
    } finally {
      setLoadingDocs(false);
    }
  };

  const fetchQuestionBank = async (docId: number) => {
    setLoadingQuestions(true);
    try {
      const res = await apiClient.get(`${apiBaseUrl}/api/documents/question-bank/${docId}`);
      const normalized: QuestionBankItem[] = Array.isArray(res.data)
        ? res.data.map((item: any) => ({
            id: Number(item.id),
            content: String(item.content || ''),
            options: normalizeOptions(item.options),
            correct_answer: String(item.correct_answer || 'A'),
            explanation: String(item.explanation || ''),
            difficulty: String(item.difficulty || 'Medium'),
          }))
        : [];
      setQuestions(normalized);
      setCurrentPage(1);
    } catch {
      toast.error('Không thể tải ngân hàng câu hỏi');
      setQuestions([]);
    } finally {
      setLoadingQuestions(false);
    }
  };

  useEffect(() => {
    void fetchSubjects();
    void fetchClassrooms();
  }, []);

  useEffect(() => {
    if (!selectedSubjectId) {
      setDocuments([]);
      setSelectedDocId(null);
      setQuestions([]);
      return;
    }
    void fetchDocuments(selectedSubjectId);
  }, [selectedSubjectId]);

  // Khi mở trang qua Nova (?subject=...), tự chọn môn khớp.
  useEffect(() => {
    if (!subjectQuery || selectedSubjectId || subjects.length === 0) return;
    const match = subjects.find(
      (s) => s.name.toLowerCase() === subjectQuery.toLowerCase() || s.name.toLowerCase().includes(subjectQuery.toLowerCase())
    );
    if (match) setSelectedSubjectId(match.id);
  }, [subjectQuery, subjects, selectedSubjectId]);

  useEffect(() => {
    if (!selectedDocId) {
      setQuestions([]);
      return;
    }
    void fetchQuestionBank(selectedDocId);
  }, [selectedDocId]);

  const handleSelectDocument = (docId: number) => {
    setSelectedDocId(docId);
    setEditingQuestionId(null);
    setEditDraft({});
    setCurrentPage(1);
  };

  const handleAppendQuestions = async () => {
    if (!selectedDocId || !selectedDocument) return;
    setAppending(true);
    try {
      const res = await runLongRequest(
        () =>
          apiClient.post(
            `${apiBaseUrl}/api/documents/generate-question-bank/${selectedDocId}/append?count=10`,
            undefined,
            longRequestConfig
          ),
        {
          onSlowStateChange: setSlowAppendNotice,
          slowDelayMs: 4000,
        }
      );
      const generatedQuestions: QuestionBankItem[] = Array.isArray(res.data?.generated_questions)
        ? res.data.generated_questions.map((item: any) => ({
            id: Number(item.id),
            content: String(item.content || ''),
            options: normalizeOptions(item.options),
            correct_answer: String(item.correct_answer || 'A'),
            explanation: String(item.explanation || ''),
            difficulty: String(item.difficulty || 'Basic'),
          }))
        : [];

      if (generatedQuestions.length > 0) {
        setQuestions((prev) => [...generatedQuestions, ...prev]);
        setCurrentPage(1);
      } else {
        await fetchQuestionBank(selectedDocId);
      }
      toast.success(`Đã sinh thêm ${res.data.generated_count ?? 0} câu hỏi`);
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, 'Không thể sinh thêm câu hỏi'));
    } finally {
      setAppending(false);
      setSlowAppendNotice(false);
    }
  };

  const handleAddQuestion = async () => {
    if (!selectedDocId) return;

    const options = [newQuestion.optionA, newQuestion.optionB, newQuestion.optionC, newQuestion.optionD]
      .map((item) => item.trim())
      .filter(Boolean);

    if (!newQuestion.content.trim()) {
      toast.error('Vui lòng nhập nội dung câu hỏi');
      return;
    }
    if (options.length < 2) {
      toast.error('Vui lòng nhập ít nhất 2 lựa chọn');
      return;
    }

    try {
      const res = await apiClient.post(`${apiBaseUrl}/api/documents/question-bank/${selectedDocId}`, {
        content: newQuestion.content.trim(),
        options,
        correct_answer: newQuestion.correct_answer,
        explanation: newQuestion.explanation.trim(),
        difficulty: newQuestion.difficulty,
      });
      setQuestions((prev) => [res.data, ...prev]);
      setCurrentPage(1);
      setNewQuestion(initialFormState);
      toast.success('Đã thêm câu hỏi mới');
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, 'Không thể thêm câu hỏi mới'));
    }
  };

  const handleStartEditing = (question: QuestionBankItem) => {
    setEditingQuestionId(question.id);
    setEditDraft({ ...question });
  };

  const handleCancelEditing = () => {
    setEditingQuestionId(null);
    setEditDraft({});
  };

  const handleSaveEdit = async (questionId: number) => {
    const payload = {
      content: editDraft.content?.trim() ?? '',
      options: editDraft.options ?? [],
      correct_answer: editDraft.correct_answer ?? '',
      explanation: editDraft.explanation?.trim() ?? '',
      difficulty: editDraft.difficulty ?? 'Medium',
    };

    if (!payload.content) {
      toast.error('Nội dung câu hỏi không được để trống');
      return;
    }
    if (!Array.isArray(payload.options) || payload.options.length < 2) {
      toast.error('Cần ít nhất 2 lựa chọn hợp lệ');
      return;
    }

    setSavingQuestionId(questionId);
    try {
      const res = await apiClient.put(`${apiBaseUrl}/api/documents/question-bank/${questionId}`, payload);
      setQuestions((prev) => prev.map((item) => (item.id === questionId ? res.data : item)));
      setEditingQuestionId(null);
      setEditDraft({});
      toast.success('Đã cập nhật câu hỏi');
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, 'Không thể cập nhật câu hỏi'));
    } finally {
      setSavingQuestionId(null);
    }
  };

  const handleDeleteQuestion = async (questionId: number) => {
    const confirmed = await confirmAlert({
      title: "Xóa câu hỏi",
      message: "Xóa câu hỏi này khỏi ngân hàng?",
      confirmText: "Xóa câu hỏi",
      cancelText: "Hủy",
      tone: "danger",
    });
    if (!confirmed) return;
    setDeletingQuestionId(questionId);
    try {
      await apiClient.delete(`${apiBaseUrl}/api/documents/question-bank/${questionId}`);
      const nextQuestions = questions.filter((item) => item.id !== questionId);
      setQuestions(nextQuestions);
      setCurrentPage((page) => Math.min(page, Math.max(1, Math.ceil(nextQuestions.length / PAGE_SIZE))));
      toast.success('Đã xóa câu hỏi');
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, 'Không thể xóa câu hỏi'));
    } finally {
      setDeletingQuestionId(null);
    }
  };

  const updateEditOption = (index: number, value: string) => {
    const currentOptions = Array.isArray(editDraft.options) ? [...editDraft.options] : [];
    currentOptions[index] = value;
    setEditDraft((prev) => ({ ...prev, options: currentOptions }));
  };

  const questionCountLabel = `${questions.length} câu hỏi`;
  const pageStart = questions.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(currentPage * PAGE_SIZE, questions.length);

  return (
    <div className="page-shell app-bg">
      <div className="page-container space-y-6">
        <section className="hero-panel overflow-hidden">
          <div className="grid gap-0 lg:grid-cols-[0.78fr_1.22fr]">
            <div className="section-panel rounded-none border-0 border-b border-r border-[rgba(24,24,27,0.08)] p-6 text-zinc-950 lg:border-b-0">
              <p className="text-[10px] font-black uppercase tracking-[0.34em] text-zinc-500">
                Câu hỏi & tài liệu
              </p>
              <h1 className="mt-3 text-3xl font-black uppercase md:text-4xl">
                Tổng kết câu hỏi
              </h1>

              <div className="mt-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">
                    Môn hiện tại
                  </p>
                  <p className="mt-2 text-sm font-black uppercase text-zinc-950">
                    {selectedSubject?.name || 'Chưa chọn'}
                  </p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">
                    Tài liệu khóa
                  </p>
                  <p className="mt-2 line-clamp-2 text-sm font-black uppercase text-zinc-950">
                    {selectedDocument?.title || selectedDocument?.filename || 'Chưa chọn'}
                  </p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.28em] text-zinc-500">
                    Tổng số
                  </p>
                  <p className="mt-2 text-3xl font-black text-zinc-950">{questions.length}</p>
                </div>
              </div>
            </div>

            <div className="soft-grid p-6 md:p-8">
              <div className="grid gap-4 xl:grid-cols-[0.86fr_1.14fr]">
                <div className="section-panel p-5">
                  <div className="mb-4 flex items-center gap-3">
                    <div className="flex h-11 w-11 items-center justify-center rounded-[1rem] bg-[var(--brand)] text-white">
                      <BookOpen className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">
                        Môn học & tài liệu
                      </p>
                      <h2 className="text-lg font-black uppercase text-[#251917]">
                        Chọn môn và tài liệu
                      </h2>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <select
                      value={selectedSubjectId ?? ''}
                      onChange={(event) =>
                        setSelectedSubjectId(event.target.value ? Number(event.target.value) : null)
                      }
                      className="app-input"
                    >
                      {subjects.length === 0 ? <option value="">Không có môn học</option> : null}
                      {subjects.map((subject) => (
                        <option key={subject.id} value={subject.id}>
                          {subject.icon ? `${subject.icon} ` : ''}
                          {subject.name}
                        </option>
                      ))}
                    </select>

                    {/* Tải tài liệu lên */}
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.doc,.docx,.ppt,.pptx,.txt"
                      className="hidden"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) void handleUploadDocument(file);
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={!selectedSubjectId || !activeClassId || uploading}
                      className="app-btn-primary w-full"
                    >
                      {uploading ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Đang tải lên
                        </>
                      ) : (
                        <>
                          <Upload className="h-4 w-4" />
                          Tải tài liệu lên
                        </>
                      )}
                    </button>
                    {!activeClassId && selectedSubjectId ? (
                      <p className="text-[11px] font-medium text-amber-600">
                        Môn này chưa có lớp học nào của bạn để gắn tài liệu.
                      </p>
                    ) : null}

                    <div className="ghost-panel p-3">
                      <p className="mb-3 text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">
                        Danh sách tài liệu
                      </p>
                      {loadingDocs ? (
                        <div className="flex items-center gap-2 px-2 py-3 text-sm text-slate-500">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Đang tải tài liệu...
                        </div>
                      ) : documents.length === 0 ? (
                        <div className="rounded-[1rem] border border-dashed border-slate-300 px-4 py-8 text-center text-sm text-slate-500">
                          Môn này chưa có tài liệu.
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {documents.map((doc) => {
                            const isActive = doc.id === selectedDocId;
                            return (
                              <div
                                key={doc.id}
                                className={`flex items-center gap-2 rounded-[1rem] border px-3 py-2 transition-all ${
                                  isActive
                                    ? 'border-[var(--brand)] bg-[linear-gradient(135deg,rgba(185,28,28,0.08),rgba(15,118,110,0.05))] shadow-[0_10px_24px_rgba(95,33,23,0.08)]'
                                    : 'border-slate-200 bg-white hover:border-[var(--accent)]'
                                }`}
                              >
                                <button
                                  type="button"
                                  onClick={() => handleSelectDocument(doc.id)}
                                  className="min-w-0 flex-1 text-left"
                                >
                                  <p className="line-clamp-2 text-sm font-black uppercase text-[#251917]">
                                    {doc.title || doc.filename || `Tài liệu #${doc.id}`}
                                  </p>
                                  <p className="mt-1 text-xs font-medium text-slate-500">
                                    {doc.subject}
                                  </p>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleDeleteDocument(doc)}
                                  disabled={deletingDocId === doc.id}
                                  title="Xóa tài liệu"
                                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-red-200 bg-red-50 text-red-600 transition hover:bg-red-100 disabled:opacity-50"
                                >
                                  {deletingDocId === doc.id ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <Trash2 className="h-4 w-4" />
                                  )}
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="nova-panel p-5 text-zinc-950">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.3em] text-zinc-500">
                        Tạo câu hỏi
                      </p>
                      <h2 className="mt-2 text-xl font-black uppercase">Sinh thêm 10 câu</h2>
                    </div>
                    <Sparkles className="h-5 w-5 text-[#fbd7ad]" />
                  </div>
                  {slowAppendNotice ? (
                    <div className="mt-3 rounded-xl border border-indigo-200 bg-white/80 px-3 py-2 text-[12px] font-semibold text-indigo-700">
                      Hệ thống vẫn đang sinh thêm câu hỏi, backend chưa mất kết nối. Vui lòng chờ thêm một chút.
                    </div>
                  ) : null}

                  <div className="mt-5 grid gap-3 sm:grid-cols-3">
                    <div className="metric-panel p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.24em] text-zinc-500">
                        Hiển thị
                      </p>
                      <p className="mt-2 text-2xl font-black">{questions.length}</p>
                    </div>
                    <div className="metric-panel p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.24em] text-zinc-500">
                        Trang
                      </p>
                      <p className="mt-2 text-2xl font-black">
                        {questions.length ? `${pageStart}-${pageEnd}` : '0'}
                      </p>
                    </div>
                    <div className="metric-panel p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.24em] text-zinc-500">
                        Target
                      </p>
                      <p className="mt-2 text-2xl font-black">+10</p>
                    </div>
                  </div>

                  <div className="mt-5 flex flex-wrap gap-3">
                    <button
                      onClick={handleAppendQuestions}
                      disabled={!selectedDocId || appending}
                      className="app-btn-primary"
                    >
                      {appending ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Đang sinh
                        </>
                      ) : (
                        <>
                          <Wand2 className="h-4 w-4" />
                          Sinh thêm 10 câu
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => selectedDocId && void fetchQuestionBank(selectedDocId)}
                      className="app-btn-dark"
                    >
                      <RefreshCcw className="h-4 w-4" />
                      Đồng bộ lại
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.18fr_0.82fr]">
          <div className="section-panel overflow-hidden">
            <div className="border-b border-[rgba(46,34,28,0.1)] px-6 py-5">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">
                    Stored questions
                  </p>
                  <h2 className="mt-2 text-2xl font-black uppercase text-[#251917]">
                    Ngân hàng câu hỏi
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">
                    {questionCountLabel} {selectedDocument ? 'cho tài liệu đang khóa.' : 'trong bộ nhớ hiện tại.'}
                  </p>
                </div>
                <div className="command-badge">
                  <FileText className="h-4 w-4" />
                  {selectedDocument?.title || selectedDocument?.filename || 'Chưa khóa tài liệu'}
                </div>
              </div>
            </div>

            <div className="p-5">
              {loadingQuestions ? (
                <div className="flex justify-center py-16 text-slate-500">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : questions.length === 0 ? (
                <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-[rgba(255,255,255,0.56)] px-6 py-14 text-center text-sm text-slate-500">
                  Chưa có câu hỏi nào cho tài liệu này.
                </div>
              ) : (
                <div className="space-y-4">
                  {paginatedQuestions.map((question) => {
                    const isEditing = editingQuestionId === question.id;
                    const optionSource = isEditing ? editDraft.options ?? [] : question.options;

                    return (
                      <article
                        key={question.id}
                        className="rounded-[1.6rem] border border-[rgba(24,24,27,0.08)] bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(248,250,252,0.92))] p-5 shadow-[0_12px_28px_rgba(15,23,42,0.04)]"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div>
                            <p className="text-[10px] font-black uppercase tracking-[0.28em] text-slate-400">
                              Question ID {question.id}
                            </p>
                            <p className="mt-2 text-xs font-bold uppercase text-[var(--brand)]">
                              Difficulty: {isEditing ? editDraft.difficulty ?? 'Medium' : question.difficulty}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {isEditing ? (
                              <>
                                <button
                                  onClick={() => void handleSaveEdit(question.id)}
                                  disabled={savingQuestionId === question.id}
                                  className="app-btn-primary !px-3 !py-2 !text-xs"
                                >
                                  {savingQuestionId === question.id ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <Save className="h-4 w-4" />
                                  )}
                                  Lưu
                                </button>
                                <button
                                  onClick={handleCancelEditing}
                                  className="app-btn-dark !px-3 !py-2 !text-xs"
                                >
                                  Hủy
                                </button>
                              </>
                            ) : (
                              <button
                                onClick={() => handleStartEditing(question)}
                                className="app-btn-dark !px-3 !py-2 !text-xs"
                              >
                                <Pencil className="h-4 w-4" />
                                Sửa
                              </button>
                            )}
                            <button
                              onClick={() => void handleDeleteQuestion(question.id)}
                              disabled={deletingQuestionId === question.id}
                              className="inline-flex items-center gap-2 rounded-[1rem] border border-red-200 bg-red-50 px-3 py-2 text-xs font-black uppercase tracking-[0.12em] text-red-700 disabled:opacity-50"
                            >
                              {deletingQuestionId === question.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                              Xóa
                            </button>
                          </div>
                        </div>

                        <div className="mt-4 space-y-4">
                          <textarea
                            disabled={!isEditing}
                            value={isEditing ? editDraft.content ?? '' : question.content}
                            onChange={(event) =>
                              setEditDraft((prev) => ({ ...prev, content: event.target.value }))
                            }
                            className="app-input min-h-[110px] resize-y disabled:bg-zinc-100"
                          />

                          <div className="grid gap-3 md:grid-cols-2">
                            {optionSource.map((option, index) => {
                              const label = String.fromCharCode(65 + index);
                              return (
                                <div
                                  key={`${question.id}-${label}`}
                                  className="rounded-[1.2rem] border border-[rgba(46,34,28,0.12)] bg-white p-3"
                                >
                                  <p className="mb-2 text-[10px] font-black uppercase tracking-[0.28em] text-slate-400">
                                    Option {label}
                                  </p>
                                  <textarea
                                    disabled={!isEditing}
                                    value={option}
                                    onChange={(event) => updateEditOption(index, event.target.value)}
                                  className="app-input min-h-[88px] resize-y disabled:bg-zinc-100"
                                  />
                                </div>
                              );
                            })}
                          </div>

                          <div className="grid gap-3 md:grid-cols-2">
                            <div className="rounded-[1.2rem] border border-[rgba(46,34,28,0.12)] bg-white p-4">
                              <p className="mb-2 text-[10px] font-black uppercase tracking-[0.28em] text-slate-400">
                                Đáp án đúng
                              </p>
                              <select
                                disabled={!isEditing}
                                value={isEditing ? editDraft.correct_answer ?? '' : question.correct_answer}
                                onChange={(event) =>
                                  setEditDraft((prev) => ({
                                    ...prev,
                                    correct_answer: event.target.value,
                                  }))
                                }
                                className="app-input"
                              >
                                {optionSource.map((_, index) => (
                                  <option key={index} value={String.fromCharCode(65 + index)}>
                                    {String.fromCharCode(65 + index)}
                                  </option>
                                ))}
                              </select>
                            </div>

                            <div className="rounded-[1.2rem] border border-[rgba(46,34,28,0.12)] bg-white p-4">
                              <p className="mb-2 text-[10px] font-black uppercase tracking-[0.28em] text-slate-400">
                                Giải thích
                              </p>
                              <textarea
                                disabled={!isEditing}
                                value={isEditing ? editDraft.explanation ?? '' : question.explanation ?? ''}
                                onChange={(event) =>
                                  setEditDraft((prev) => ({
                                    ...prev,
                                    explanation: event.target.value,
                                  }))
                                }
                                className="app-input min-h-[110px] resize-y disabled:bg-zinc-100"
                              />
                            </div>
                          </div>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}

              {questions.length > PAGE_SIZE ? (
                <div className="ghost-panel mt-5 flex items-center justify-between gap-3 px-4 py-3">
                  <p className="text-sm font-semibold text-slate-600">
                    Trang {currentPage}/{totalPages}
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                      disabled={currentPage === 1}
                      className="app-btn-dark !px-3 !py-2 !text-xs"
                    >
                      Trước
                    </button>
                    <button
                      onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                      disabled={currentPage === totalPages}
                      className="app-btn-dark !px-3 !py-2 !text-xs"
                    >
                      Sau
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <aside className="section-panel p-5">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-[1rem] bg-[var(--accent)] text-white">
                <Plus className="h-5 w-5" />
              </div>
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.3em] text-slate-400">
                  Manual insert
                </p>
                <h2 className="text-lg font-black uppercase text-[#251917]">
                  Thêm câu hỏi thủ công
                </h2>
              </div>
            </div>

            <div className="mt-5 space-y-4">
              <textarea
                value={newQuestion.content}
                onChange={(event) =>
                  setNewQuestion((prev) => ({ ...prev, content: event.target.value }))
                }
                placeholder="Nội dung câu hỏi"
                className="app-input min-h-[140px] resize-y"
              />

              {['A', 'B', 'C', 'D'].map((label) => (
                <input
                  key={label}
                  type="text"
                  value={newQuestion[`option${label}` as keyof typeof newQuestion]}
                  onChange={(event) =>
                    setNewQuestion((prev) => ({
                      ...prev,
                      [`option${label}`]: event.target.value,
                    }))
                  }
                  placeholder={`Lựa chọn ${label}`}
                  className="app-input"
                />
              ))}

              <div className="grid gap-3 sm:grid-cols-2">
                <select
                  value={newQuestion.correct_answer}
                  onChange={(event) =>
                    setNewQuestion((prev) => ({
                      ...prev,
                      correct_answer: event.target.value,
                    }))
                  }
                  className="app-input"
                >
                  <option value="A">Đáp án A</option>
                  <option value="B">Đáp án B</option>
                  <option value="C">Đáp án C</option>
                  <option value="D">Đáp án D</option>
                </select>

                <select
                  value={newQuestion.difficulty}
                  onChange={(event) =>
                    setNewQuestion((prev) => ({
                      ...prev,
                      difficulty: event.target.value,
                    }))
                  }
                  className="app-input"
                >
                  <option value="Easy">Easy</option>
                  <option value="Medium">Medium</option>
                  <option value="Hard">Hard</option>
                </select>
              </div>

              <textarea
                value={newQuestion.explanation}
                onChange={(event) =>
                  setNewQuestion((prev) => ({ ...prev, explanation: event.target.value }))
                }
                placeholder="Giải thích / lời giải"
                className="app-input min-h-[120px] resize-y"
              />

              <button onClick={handleAddQuestion} className="app-btn-primary w-full">
                <Plus className="h-4 w-4" />
                Thêm câu hỏi mới
              </button>
            </div>
          </aside>
        </section>
      </div>
    </div>
  );
}
