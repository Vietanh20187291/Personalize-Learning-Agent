"use client";

import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "react-hot-toast";
import { BookOpen, FileCheck2, FileText, GraduationCap, Loader2, PlusCircle, Sparkles } from "lucide-react";

import AgentConversationCard from "@/components/AgentConversationCard";
import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from "@/services/api";

type EnrolledClass = {
  id: number;
  name: string;
  subject: string;
  teacher_name: string;
};

type StudentDoc = {
  id: number;
  filename: string;
  subject: string;
  class_id: number;
  upload_time?: string;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const buildWelcomeMessage = (documentName: string): ChatMessage => ({
  role: "assistant",
  content: `Mình là Tutor Agent. Bạn đang mở **${documentName}**. Hãy hỏi mình tóm tắt, giải thích, nêu ý chính hoặc cách ôn tập của tài liệu này.`,
});

export default function AdaptiveLearningPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  const [userId, setUserId] = useState<number | null>(null);
  const [enrolledClasses, setEnrolledClasses] = useState<EnrolledClass[]>([]);
  const [selectedSubject, setSelectedSubject] = useState("");
  const [documents, setDocuments] = useState<StudentDoc[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);
  const [loadingPage, setLoadingPage] = useState(true);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);
  const [slowNotice, setSlowNotice] = useState(false);
  const [classCode, setClassCode] = useState("");
  const [joining, setJoining] = useState(false);
  const [documentMessages, setDocumentMessages] = useState<Record<number, ChatMessage[]>>({});

  const subjectOptions = useMemo(
    () => Array.from(new Set(enrolledClasses.map((item) => item.subject).filter(Boolean))),
    [enrolledClasses]
  );

  const activeDocument = useMemo(
    () => documents.find((item) => item.id === activeDocumentId) || null,
    [documents, activeDocumentId]
  );

  const activeMessages = activeDocumentId
    ? documentMessages[activeDocumentId] || (activeDocument ? [buildWelcomeMessage(activeDocument.filename)] : [])
    : [];

  const activeViewerUrl =
    userId && activeDocument
      ? `${apiBaseUrl}/api/documents/view/${activeDocument.id}?user_id=${userId}`
      : "";

  const ensureConversationForDocument = (doc: StudentDoc) => {
    setDocumentMessages((prev) => {
      if (prev[doc.id]?.length) return prev;
      return { ...prev, [doc.id]: [buildWelcomeMessage(doc.filename)] };
    });
  };

  const readPendingTutorAction = (uid: number) => {
    if (typeof window === "undefined") return { subject: "", documentId: null as number | null };

    const newKey = `tutor_pending_document_${uid}`;
    const newRaw = localStorage.getItem(newKey);
    if (newRaw) {
      localStorage.removeItem(newKey);
      try {
        const parsed = JSON.parse(newRaw);
        return {
          subject: String(parsed.subject || ""),
          documentId: Number(parsed.document_id || 0) || null,
        };
      } catch {
        return { subject: "", documentId: null };
      }
    }

    const legacyKey = `orbit_pending_action_${uid}`;
    const legacyRaw = localStorage.getItem(legacyKey);
    if (!legacyRaw) return { subject: "", documentId: null };
    localStorage.removeItem(legacyKey);

    try {
      const parsed = JSON.parse(legacyRaw);
      return {
        subject: String(parsed?.params?.subject || ""),
        documentId: Number(parsed?.params?.document_id || 0) || null,
      };
    } catch {
      return { subject: "", documentId: null };
    }
  };

  const loadDocuments = async (uid: number, subject: string, preferredDocumentId?: number | null) => {
    if (!subject) return;
    setLoadingDocuments(true);
    try {
      const res = await axios.get<StudentDoc[]>(`${apiBaseUrl}/api/documents/student/${uid}`, {
        params: { subject },
      });
      const docs = Array.isArray(res.data) ? res.data : [];
      setDocuments(docs);

      if (!docs.length) {
        setActiveDocumentId(null);
        return;
      }

      const nextDoc =
        docs.find((item) => item.id === preferredDocumentId) ||
        docs.find((item) => item.id === activeDocumentId) ||
        docs[0];

      setActiveDocumentId(nextDoc.id);
      ensureConversationForDocument(nextDoc);
    } catch (error: unknown) {
      setDocuments([]);
      setActiveDocumentId(null);
      toast.error(normalizeApiError(error, "Không thể tải tài liệu học tập"));
    } finally {
      setLoadingDocuments(false);
    }
  };

  useEffect(() => {
    const init = async () => {
      const rawId = localStorage.getItem("userId") || localStorage.getItem("user_id");
      if (!rawId) {
        setLoadingPage(false);
        toast.error("Không tìm thấy phiên đăng nhập.");
        return;
      }

      const uid = Number(rawId);
      if (!uid) {
        setLoadingPage(false);
        toast.error("ID người dùng không hợp lệ.");
        return;
      }
      setUserId(uid);

      try {
        const res = await axios.get(`${apiBaseUrl}/api/auth/me/${uid}`);
        const classes: EnrolledClass[] = Array.isArray(res.data?.enrolled_classes) ? res.data.enrolled_classes : [];
        setEnrolledClasses(classes);

        const pending = readPendingTutorAction(uid);
        const params = new URLSearchParams(window.location.search);
        const subjectFromUrl = params.get("subject") || "";
        const documentFromUrl = Number(params.get("document_id") || 0) || null;
        const initialSubject = subjectFromUrl || pending.subject || classes[0]?.subject || "";

        setSelectedSubject(initialSubject);
        if (initialSubject) {
          await loadDocuments(uid, initialSubject, documentFromUrl || pending.documentId);
        }
      } catch {
        toast.error("Không thể lấy thông tin học sinh.");
      } finally {
        setLoadingPage(false);
      }
    };

    void init();
  }, [apiBaseUrl]);

  useEffect(() => {
    if (!userId || !selectedSubject) return;
    void loadDocuments(userId, selectedSubject, null);
  }, [selectedSubject]);

  const handleJoinClass = async () => {
    if (!classCode.trim() || !userId) return;
    setJoining(true);
    try {
      const res = await axios.post(`${apiBaseUrl}/api/classroom/join`, {
        class_code: classCode.trim().toUpperCase(),
        user_id: userId,
      });
      toast.success(res.data?.message || "Tham gia lớp học thành công.");

      const meRes = await axios.get(`${apiBaseUrl}/api/auth/me/${userId}`);
      const classes: EnrolledClass[] = Array.isArray(meRes.data?.enrolled_classes) ? meRes.data.enrolled_classes : [];
      setEnrolledClasses(classes);

      const subject = String(res.data?.subject || classes[0]?.subject || "");
      setSelectedSubject(subject);
      if (subject) {
        await loadDocuments(userId, subject, null);
      }
      setClassCode("");
    } catch (error: unknown) {
      toast.error(normalizeApiError(error, "Mã lớp không hợp lệ"));
    } finally {
      setJoining(false);
    }
  };

  const openAssessmentForDocument = () => {
    if (!activeDocument || !selectedSubject) return;
    const query = new URLSearchParams({
      subject: selectedSubject,
      source_file: activeDocument.filename,
      topic: activeDocument.filename,
      level: "Intermediate",
    });
    window.location.href = `/assessment?${query.toString()}`;
  };

  const sendTutorMessage = async (messageText?: string) => {
    if (!userId || !activeDocument || !selectedSubject) return;
    const message = (messageText ?? chatInput).trim();
    if (!message) return;

    ensureConversationForDocument(activeDocument);
    const currentMessages = activeMessages;
    setDocumentMessages((prev) => ({
      ...prev,
      [activeDocument.id]: [...currentMessages, { role: "user", content: message }],
    }));
    setChatInput("");
    setSending(true);

    try {
      const res = await runLongRequest(
        () =>
          apiClient.post(
            "/api/adaptive/chat",
            {
              subject: selectedSubject,
              message,
              roadmap_context: `Tài liệu đang mở: ${activeDocument.filename}`,
              user_id: userId,
              session_topic: activeDocument.filename.replace(/\.[^/.]+$/, ""),
              source_file: activeDocument.filename,
              document_id: activeDocument.id,
              history: currentMessages,
            },
            {
              ...longRequestConfig,
              baseURL: apiBaseUrl,
            }
          ),
        {
          onSlowStateChange: setSlowNotice,
          slowDelayMs: 3500,
        }
      );

      const reply = String(res.data?.reply || "Tutor Agent đã phản hồi.");
      setDocumentMessages((prev) => ({
        ...prev,
        [activeDocument.id]: [...(prev[activeDocument.id] || []), { role: "assistant", content: reply }],
      }));
    } catch (error: unknown) {
      const fallback = normalizeApiError(error, "Tutor Agent chưa thể trả lời lúc này.");
      setDocumentMessages((prev) => ({
        ...prev,
        [activeDocument.id]: [...(prev[activeDocument.id] || []), { role: "assistant", content: `Lỗi: ${fallback}` }],
      }));
    } finally {
      setSending(false);
    }
  };

  if (loadingPage) {
    return (
      <div className="page-shell px-4 pb-8">
        <div className="mx-auto max-w-7xl rounded-[2rem] border border-slate-200 bg-white p-8 text-sm font-semibold text-slate-600 shadow-sm">
          Đang tải không gian Gia sư...
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell px-4 pb-8 text-slate-800">
      <div className="mx-auto max-w-7xl space-y-6">
        <section className="overflow-hidden rounded-[2.2rem] border border-slate-200 bg-[linear-gradient(135deg,#dff7ff,white_45%,#ecfeff)] shadow-[0_30px_80px_rgba(15,23,42,0.08)]">
          <div className="grid gap-6 px-6 py-7 lg:grid-cols-[1.2fr_0.8fr]">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/75 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-cyan-800">
                <Sparkles size={13} />
                Tab Gia sư
              </div>
              <h1 className="mt-4 text-2xl font-black tracking-tight text-slate-950">Tutor Agent theo từng môn và từng tài liệu</h1>
              <p className="mt-2 max-w-2xl text-[13px] font-medium leading-6 text-slate-600">
                Bên trái là tài liệu đang mở. Bên phải là Tutor Agent và danh sách môn học. Khi bạn hỏi, hệ thống sẽ gửi prompt của bạn kèm đúng tài liệu đang hiển thị cho AI để trả lời.
              </p>
            </div>

            <div className="rounded-[1.8rem] border border-white/80 bg-white/75 p-4 backdrop-blur">
              <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">Tham gia thêm lớp học</p>
              <div className="mt-3 flex gap-2">
                <input
                  value={classCode}
                  onChange={(event) => setClassCode(event.target.value)}
                  placeholder="Nhập mã lớp"
                  className="h-11 flex-1 rounded-2xl border border-slate-200 px-4 text-sm font-semibold outline-none focus:border-cyan-500"
                />
                <button
                  type="button"
                  onClick={handleJoinClass}
                  disabled={joining}
                  className="inline-flex items-center gap-2 rounded-2xl bg-slate-950 px-3.5 text-[11px] font-black uppercase tracking-[0.14em] text-white disabled:opacity-50"
                >
                  <PlusCircle size={14} />
                  {joining ? "Đang vào..." : "Tham gia"}
                </button>
              </div>
            </div>
          </div>
        </section>

        {!enrolledClasses.length ? (
          <section className="flex flex-col items-center rounded-[2rem] border border-dashed border-slate-300 bg-white px-6 py-16 text-center shadow-sm">
            <GraduationCap className="mb-4 h-14 w-14 text-slate-300" />
            <h2 className="text-xl font-black text-slate-700">Bạn chưa tham gia lớp học nào</h2>
            <p className="mt-2 max-w-xl text-sm font-medium text-slate-500">
              Hãy nhập mã lớp ở phía trên để mở tài liệu và bắt đầu sử dụng Tutor Agent.
            </p>
          </section>
        ) : (
          <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
            <section className="space-y-4">
              <div className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2">
                    <FileText size={18} className="text-cyan-700" />
                    <h2 className="text-lg font-black text-slate-900">Tài liệu học tập</h2>
                  </div>
                  {loadingDocuments ? <Loader2 size={16} className="ml-auto animate-spin text-slate-500" /> : null}
                  {activeDocument ? (
                    <button
                      type="button"
                      onClick={openAssessmentForDocument}
                      className="ml-auto inline-flex items-center gap-2 rounded-2xl bg-[linear-gradient(135deg,#0891b2,#2563eb)] px-4 py-2 text-[11px] font-black uppercase tracking-[0.14em] text-white shadow-[0_16px_32px_rgba(37,99,235,0.22)]"
                    >
                      <FileCheck2 size={14} />
                      Kiểm tra
                    </button>
                  ) : null}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {documents.map((doc, index) => {
                    const active = doc.id === activeDocumentId;
                    return (
                      <button
                        key={doc.id}
                        type="button"
                        onClick={() => {
                          setActiveDocumentId(doc.id);
                          ensureConversationForDocument(doc);
                        }}
                        className={`rounded-full px-4 py-2 text-[11px] font-black uppercase tracking-[0.12em] transition ${
                          active
                            ? "bg-cyan-600 text-white shadow-[0_14px_28px_rgba(8,145,178,0.22)]"
                            : "border border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white"
                        }`}
                      >
                        Tài liệu {index + 1}
                      </button>
                    );
                  })}
                </div>

                <div className="mt-4 overflow-hidden rounded-[1.6rem] border border-slate-200 bg-slate-50">
                  {activeDocument && userId ? (
                    <>
                      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">{selectedSubject}</p>
                          <p className="mt-1 text-sm font-bold text-slate-900">{activeDocument.filename}</p>
                        </div>
                        <a
                          href={activeViewerUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-black uppercase tracking-[0.12em] text-slate-700"
                        >
                          Mở riêng
                        </a>
                      </div>
                      <iframe
                        key={activeViewerUrl}
                        src={activeViewerUrl}
                        title={activeDocument.filename}
                        className="h-[78vh] min-h-[720px] w-full bg-white"
                      />
                    </>
                  ) : (
                    <div className="flex h-[62vh] min-h-[520px] items-center justify-center px-6 text-center text-sm font-medium text-slate-500">
                      Chọn một tài liệu để hiển thị nội dung ở đây.
                    </div>
                  )}
                </div>
              </div>
            </section>

            <aside className="space-y-5">
              <AgentConversationCard
                badge="Tutor Agent"
                title="Hỏi theo tài liệu đang hiển thị"
                subtitle="Prompt của bạn sẽ đi kèm tài liệu đang mở, không tự tóm tắt trước khi bạn yêu cầu."
                accentClassName="bg-[linear-gradient(135deg,#cffafe,#ecfeff_45%,#e2e8f0)]"
                placeholder="Ví dụ: Tóm tắt tài liệu này, nêu các ý chính trong tài liệu này, giải thích đoạn này..."
                inputValue={chatInput}
                sending={sending}
                slowNotice={slowNotice}
                messages={activeMessages}
                suggestions={[
                  "Tóm tắt tài liệu này",
                  "Các ý chính trong tài liệu này là gì?",
                  "Giải thích nội dung tài liệu này dễ hiểu hơn",
                ]}
                onInputChange={setChatInput}
                onSuggestionClick={(value) => setChatInput(value)}
                onSend={() => void sendTutorMessage(chatInput)}
              />

              <div className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center gap-2">
                  <BookOpen size={18} className="text-slate-700" />
                  <h2 className="text-lg font-black text-slate-900">Môn học của bạn</h2>
                </div>

                <div className="mt-4 space-y-2">
                  {subjectOptions.map((subject) => {
                    const active = subject === selectedSubject;
                    return (
                      <button
                        key={subject}
                        type="button"
                        onClick={() => setSelectedSubject(subject)}
                        className={`flex w-full items-center justify-between rounded-[1.3rem] px-4 py-3 text-left transition ${
                          active
                            ? "bg-slate-950 text-white shadow-[0_18px_34px_rgba(15,23,42,0.18)]"
                            : "border border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300 hover:bg-white"
                        }`}
                      >
                        <span className="text-[13px] font-black">{subject}</span>
                        <span className={`text-[10px] font-black uppercase tracking-[0.14em] ${active ? "text-cyan-200" : "text-slate-400"}`}>
                          {subject === selectedSubject ? "Đang mở" : "Chọn"}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
