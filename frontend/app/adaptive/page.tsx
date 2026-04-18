"use client";
import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { toast } from 'react-hot-toast';
import ReactMarkdown from 'react-markdown';
import {
  Send,
  Flame,
  Smile,
  Minimize2,
  MessageSquare,
  UserPlus,
  Loader2,
  CheckCircle2,
  PlayCircle,
  BookOpen,
  FileText,
  Presentation,
  ExternalLink,
} from 'lucide-react';

interface EnrolledClass {
  id: number;
  name: string;
  subject: string;
  teacher_name: string;
}

interface LessonItem {
  session: number;
  topic: string;
  description: string;
}

interface StudentDoc {
  id: number;
  filename: string;
  subject: string;
  class_id: number;
}

interface PreviewSegment {
  title: string;
  content: string;
}

interface InlineQuizQuestion {
  id: number;
  content: string;
  options: string[];
}

interface InlineQuizResult {
  score: number;
  correct_count: number;
  total_questions: number;
  message: string;
  is_passed: boolean;
  chapter_feedback?: {
    weak_topics?: string[];
  };
}

export default function AdaptiveLearningPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8010';
  const [enrolledClasses, setEnrolledClasses] = useState<EnrolledClass[]>([]);
  const [selectedSubject, setSelectedSubject] = useState('');

  const [roadmap, setRoadmap] = useState<LessonItem[]>([]);
  const [loadingContext, setLoadingContext] = useState(false);
  const [currentSessionIndex, setCurrentSessionIndex] = useState(1);
  const [learnerLevel, setLearnerLevel] = useState('BEGINNER');
  const [documents, setDocuments] = useState<StudentDoc[]>([]);
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null);

  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState('');
  const [loadingChat, setLoadingChat] = useState(false);
  const [activeLessonContext, setActiveLessonContext] = useState<string>('');
  const [activeLessonNumber, setActiveLessonNumber] = useState<number>(0);
  const [activeLessonTopic, setActiveLessonTopic] = useState<string>('');
  const [chapterSummary, setChapterSummary] = useState<string>('');
  const [suggestedPrompts, setSuggestedPrompts] = useState<string[]>([]);
  const [previewSegments, setPreviewSegments] = useState<PreviewSegment[]>([]);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [quizMode, setQuizMode] = useState(false);
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizSubmitting, setQuizSubmitting] = useState(false);
  const [quizQuestions, setQuizQuestions] = useState<InlineQuizQuestion[]>([]);
  const [quizAnswers, setQuizAnswers] = useState<Record<number, string>>({});
  const [quizIndex, setQuizIndex] = useState(0);
  const [quizResult, setQuizResult] = useState<InlineQuizResult | null>(null);

  const [userId, setUserId] = useState<number | null>(null);
  const [classCode, setClassCode] = useState('');
  const [joining, setJoining] = useState(false);

  const [triggerInitialMessage, setTriggerInitialMessage] = useState(false);
  const [pendingOrbitAction, setPendingOrbitAction] = useState<any | null>(null);
  const [orbitMode, setOrbitMode] = useState<'angry' | 'happy'>('happy');
  const [orbitStatusText, setOrbitStatusText] = useState('Đang vui vẻ');
  const [showDocumentSummary, setShowDocumentSummary] = useState(false);
  const [orbitCollapsed, setOrbitCollapsed] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const userIdRef = useRef<number | null>(null);

  useEffect(() => {
    userIdRef.current = userId;
  }, [userId]);

  useEffect(() => {
    if (!selectedSubject) return;
    const startTime = new Date();
    const subjectToLog = selectedSubject;

    const saveStudySession = () => {
      if (!userIdRef.current) return;
      const endTime = new Date();
      const durationMinutes = Math.floor((endTime.getTime() - startTime.getTime()) / 60000);
      if (durationMinutes < 1) return;

      fetch(`${apiBaseUrl}/api/adaptive/log-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userIdRef.current,
          subject: subjectToLog,
          duration_minutes: durationMinutes,
        }),
        keepalive: true,
      }).catch(() => {});
    };

    window.addEventListener('beforeunload', saveStudySession);
    return () => {
      window.removeEventListener('beforeunload', saveStudySession);
      saveStudySession();
    };
  }, [selectedSubject]);

  const getFileExt = (filename: string) => {
    const parts = filename.split('.');
    return parts.length > 1 ? parts.pop()!.toLowerCase() : '';
  };

  const getActiveDocument = () => documents.find((d) => d.id === activeDocumentId) || null;

  const getLessonByIndex = (idx: number) => {
    const fallback = idx + 1;
    return roadmap.find((item) => item.session === fallback) || null;
  };

  const loadDocumentPreview = async (docId: number) => {
    setLoadingPreview(true);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/documents/preview/${docId}`, {
        params: { user_id: userIdRef.current || userId || 0 },
      });
      setPreviewSegments((res.data?.segments || []) as PreviewSegment[]);
    } catch {
      setPreviewSegments([]);
    } finally {
      setLoadingPreview(false);
    }
  };

  const loadMaterialSummary = async (subject: string, sourceFile: string, topic: string, documentId?: number | null) => {
    if (!userIdRef.current || !subject) return;
    setLoadingSummary(true);
    try {
      const res = await axios.post(`${apiBaseUrl}/api/adaptive/material-summary`, {
        user_id: userIdRef.current,
        subject,
        source_file: sourceFile,
        session_topic: topic,
        document_id: documentId || null,
      });

      const aiTitle = String(res.data?.rewritten_title || '').trim();
      const aiSummary = String(res.data?.rewritten_material || res.data?.summary || '').trim();
      const aiKeyPoints = Array.isArray(res.data?.key_points) ? res.data.key_points : [];
      const aiNotes = Array.isArray(res.data?.important_notes) ? res.data.important_notes : [];
      const aiPrompts = Array.isArray(res.data?.suggested_prompts) ? res.data.suggested_prompts : [];

      const summaryParts: string[] = [];
      if (aiTitle) summaryParts.push(`Tài liệu đã biên tập: ${aiTitle}`);
      if (aiSummary) summaryParts.push(aiSummary);
      if (aiKeyPoints.length > 0) {
        summaryParts.push(`Ý chính:\n- ${aiKeyPoints.slice(0, 5).join('\n- ')}`);
      }
      if (aiNotes.length > 0) {
        summaryParts.push(`Lưu ý quan trọng:\n- ${aiNotes.slice(0, 5).join('\n- ')}`);
      }

      const renderedSummary = summaryParts.join('\n\n').trim();
      if (renderedSummary) {
        setChapterSummary(renderedSummary);
      }
      if (aiPrompts.length > 0) {
        setSuggestedPrompts(aiPrompts.slice(0, 4));
      }
    } catch {
      // fallback summary vẫn hiển thị
    } finally {
      setLoadingSummary(false);
    }
  };

  const activateDocumentContext = (doc: StudentDoc, lesson: LessonItem | null, autoAsk = false) => {
    const lessonNo = lesson?.session || 0;
    const topic = lesson?.topic || doc.filename.replace(/\.[^/.]+$/, '');
    const desc = lesson?.description || `Nội dung tài liệu ${doc.filename}`;
    const context = `BUỔI ${lessonNo || '?'}: ${topic} - Mô tả: ${desc}`;

    setActiveDocumentId(doc.id);
    setActiveLessonNumber(lessonNo);
    setActiveLessonTopic(topic);
    setActiveLessonContext(context);
    setChapterSummary('');
    setShowDocumentSummary(false);
    setSuggestedPrompts([
      `Tóm tắt ngắn nội dung chính của tài liệu ${doc.filename}`,
      `Nêu 3 ý quan trọng nhất trong phần ${topic}`,
      `Đặt 3 câu hỏi tự kiểm tra theo nội dung ${topic}`,
    ]);

    void loadDocumentPreview(doc.id);
    const summaryPromise = loadMaterialSummary(selectedSubject, doc.filename, topic, doc.id);

    if (autoAsk) {
      void summaryPromise.finally(() => {
        setTriggerInitialMessage(true);
      });
    }
  };

  const autoLoadLearningContext = async (
    uid: number,
    subj: string,
    autoStart = false,
    isManualClick = false,
    classesSnapshot?: EnrolledClass[],
    targetDocumentId?: number | null
  ) => {
    if (!subj) {
      if (isManualClick) toast.error('Vui lòng chọn môn học!');
      return;
    }

    setLoadingContext(true);
    setRoadmap([]);
    setDocuments([]);
    setActiveDocumentId(null);
    setMessages([]);
    setActiveLessonContext('');
    setActiveLessonNumber(0);
    setActiveLessonTopic('');
    setChapterSummary('');
    setSuggestedPrompts([]);
    setPreviewSegments([]);
    setQuizMode(false);
    setQuizLoading(false);
    setQuizSubmitting(false);
    setQuizQuestions([]);
    setQuizAnswers({});
    setQuizIndex(0);
    setQuizResult(null);

    try {
      const res = await axios.get(`${apiBaseUrl}/api/assessment/roadmap/${subj}?user_id=${uid}`);
      let loadedRoadmap: LessonItem[] = [];
      let currentSess = 1;

      if (res.data?.has_roadmap) {
        loadedRoadmap = res.data.roadmap_data || [];
        currentSess = res.data.current_session || 1;
        setRoadmap(loadedRoadmap);
        setCurrentSessionIndex(currentSess);
        setLearnerLevel((res.data.level_assigned || 'Beginner').toUpperCase());
      } else {
        try {
          await axios.get(`${apiBaseUrl}/api/adaptive/recommend/${encodeURIComponent(subj)}?user_id=${uid}`);
          const refresh = await axios.get(`${apiBaseUrl}/api/assessment/roadmap/${encodeURIComponent(subj)}?user_id=${uid}`);
          if (refresh.data?.has_roadmap) {
            loadedRoadmap = refresh.data.roadmap_data || [];
            currentSess = refresh.data.current_session || 1;
            setRoadmap(loadedRoadmap);
            setCurrentSessionIndex(currentSess);
            setLearnerLevel((refresh.data.level_assigned || 'Beginner').toUpperCase());
            toast.success('Đã tự động tạo lộ trình học cho bạn.');
          } else if (isManualClick) {
            toast.error('Bạn chưa làm bài test đánh giá năng lực môn này.');
          }
        } catch {
          if (isManualClick) toast.error('Chưa thể tạo lộ trình tự động. Vui lòng thử lại sau ít phút.');
        }
      }

      const docRes = await axios.get(`${apiBaseUrl}/api/documents/student/${uid}`);
      const rawDocs: StudentDoc[] = docRes.data || [];
      const classesToUse = classesSnapshot || enrolledClasses;
      const classIds = classesToUse.filter((c) => c.subject === subj).map((c) => c.id);
      const docs = rawDocs.filter((d) => classIds.includes(d.class_id));
      setDocuments(docs);

      if (docs.length > 0) {
        const preferredIdx = targetDocumentId ? docs.findIndex((item) => item.id === targetDocumentId) : -1;
        const targetIdx = preferredIdx >= 0
          ? preferredIdx
          : Math.max(0, Math.min((currentSess || 1) - 1, docs.length - 1));
        const targetDoc = docs[targetIdx];
        const lesson = loadedRoadmap.find((l) => l.session === currentSess) || getLessonByIndex(targetIdx);
        activateDocumentContext(targetDoc, lesson, autoStart);
      }
    } catch {
      if (isManualClick) toast.error('Lỗi khi tải dữ liệu học tập.');
    } finally {
      setLoadingContext(false);
    }
  };

  useEffect(() => {
    const initData = async () => {
      const id = localStorage.getItem('userId') || localStorage.getItem('user_id');
      if (!id) return;

      const uid = parseInt(id, 10);
      setUserId(uid);

      try {
        const res = await axios.get(`${apiBaseUrl}/api/auth/me/${uid}`);
        const classes: EnrolledClass[] = res.data.enrolled_classes || [];
        setEnrolledClasses(classes);

        let targetSubject = '';
        if (classes.length > 0) {
          targetSubject = classes[0].subject;
          try {
            const docsRes = await axios.get(`${apiBaseUrl}/api/documents/student/${uid}`);
            const docs: StudentDoc[] = docsRes.data || [];
            const subjectsWithDocs = new Set(docs.map((item) => item.subject));
            const preferred = classes.find((item) => subjectsWithDocs.has(item.subject));
            if (preferred?.subject) {
              targetSubject = preferred.subject;
            }
          } catch {
            // fallback to subject đầu tiên trong lớp đã tham gia
          }
        }

        const params = new URLSearchParams(window.location.search);
        const urlSubject = params.get('subject');
        const autoStart = params.get('auto_start') === 'true';

        if (urlSubject && classes.find((c) => c.subject === urlSubject)) {
          targetSubject = urlSubject;
        }

        if (targetSubject) {
          setSelectedSubject(targetSubject);
          autoLoadLearningContext(uid, targetSubject, true, false, classes);
        }
      } catch {
        toast.error('Không thể lấy thông tin học sinh.');
      }
    };

    initData();
  }, []);

  const handleLoadRoadmap = () => {
    if (!userId) {
      toast.error('Vui lòng đăng nhập lại!');
      return;
    }
    autoLoadLearningContext(userId, selectedSubject, false, true);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loadingChat]);

  const handleJoinClass = async () => {
    if (!classCode.trim() || !userId) return;
    setJoining(true);
    try {
      const joinRes = await axios.post(`${apiBaseUrl}/api/classroom/join`, {
        class_code: classCode.trim().toUpperCase(),
        user_id: userId,
      });

      toast.success(joinRes.data.message || 'Tham gia lớp học thành công!');
      const meRes = await axios.get(`${apiBaseUrl}/api/auth/me/${userId}`);
      const updatedClasses: EnrolledClass[] = meRes.data.enrolled_classes || [];
      setEnrolledClasses(updatedClasses);

      const joinedSubject = joinRes.data.subject;
      setSelectedSubject(joinedSubject);
      autoLoadLearningContext(userId, joinedSubject, false, false, updatedClasses);
      setClassCode('');
    } catch (e: unknown) {
      const message = axios.isAxiosError(e)
        ? (e.response?.data?.detail as string) || 'Mã lớp không hợp lệ'
        : 'Mã lớp không hợp lệ';
      toast.error(message);
    } finally {
      setJoining(false);
    }
  };

  useEffect(() => {
    if (!userId || enrolledClasses.length === 0) return;
    const pendingKey = `orbit_pending_action_${userId}`;
    const raw = localStorage.getItem(pendingKey);
    if (!raw) return;

    try {
      const actionMetadata = JSON.parse(raw);
      localStorage.removeItem(pendingKey);
      void handleOrbitAction(actionMetadata);
    } catch {
      localStorage.removeItem(pendingKey);
    }
  }, [userId, enrolledClasses.length]);

  const handleSwitchDocument = (doc: StudentDoc, idx: number) => {
    const lesson = getLessonByIndex(idx);
    activateDocumentContext(doc, lesson, true);
    
    // Đảm bảo cũng gọi openDocumentFlow để nhất quán với Orbit flow
    const currentId = Number(localStorage.getItem('userId') || localStorage.getItem('user_id') || userId || 0);
    // Không cần gọi lại openDocumentFlow vì activateDocumentContext đã xử lý preview loading
    // Nhưng đảm bảo loading state được set đúng cách
    setLoadingPreview(true);
    setLoadingSummary(true);
  };

  useEffect(() => {
    if (!triggerInitialMessage || !activeLessonContext) return;
    sendChatMessage('Chào Orbit, hãy bắt đầu bài học hôm nay nhé.');
    setTriggerInitialMessage(false);
  }, [triggerInitialMessage, activeLessonContext]);

  const handleTakeTest = () => {
    void startInlineQuiz();
  };

  const startInlineQuiz = async () => {
    const activeDoc = getActiveDocument();
    const currentUserId = userIdRef.current;
    if (!activeDoc || !currentUserId) {
      toast.error('Bạn chưa chọn tài liệu để kiểm tra.');
      return;
    }

    const topic = activeLessonTopic || activeDoc.filename;
    setQuizLoading(true);
    setQuizResult(null);
    setQuizAnswers({});
    setQuizQuestions([]);
    setQuizIndex(0);

    try {
      const res = await axios.post(`${apiBaseUrl}/api/assessment/generate-session`, {
        subject: selectedSubject,
        user_id: currentUserId,
        session_topic: topic,
        level: learnerLevel,
        source_file: activeDoc.filename,
      });

      const questions = (res.data?.questions || []) as InlineQuizQuestion[];
      if (!questions.length) {
        toast.error('Hệ thống chưa sinh được đề. Vui lòng thử lại.');
        return;
      }

      setQuizQuestions(questions);
      setQuizMode(true);
      toast.success('Đã sinh đề trắc nghiệm theo tài liệu hiện tại.');
    } catch (e: unknown) {
      const message = axios.isAxiosError(e)
        ? (e.response?.data?.detail as string) || 'Lỗi hệ thống khi sinh đề trắc nghiệm.'
        : 'Lỗi hệ thống khi sinh đề trắc nghiệm.';
      toast.error(message);
    } finally {
      setQuizLoading(false);
    }
  };

  const normalizeOptionLabel = (option: string, index: number) => {
    const match = String(option || '').trim().match(/^([A-D])[\.\:\-\)]/i);
    if (match) return match[1].toUpperCase();
    return ['A', 'B', 'C', 'D'][index] || 'A';
  };

  const submitInlineQuiz = async () => {
    const activeDoc = getActiveDocument();
    const currentUserId = userIdRef.current;
    if (!activeDoc || !currentUserId) return;
    if (!quizQuestions.length) return;

    const missing = quizQuestions.filter((q) => !quizAnswers[q.id]);
    if (missing.length > 0) {
      toast.error('Bạn cần trả lời hết câu hỏi trước khi nộp bài.');
      return;
    }

    setQuizSubmitting(true);
    try {
      const res = await axios.post(`${apiBaseUrl}/api/assessment/submit`, {
        subject: selectedSubject,
        user_id: currentUserId,
        answers: quizQuestions.map((q) => ({
          question_id: q.id,
          selected_option: quizAnswers[q.id],
        })),
        duration_seconds: 0,
        is_session_quiz: true,
        test_type: 'chapter',
        session_topic: activeLessonTopic || activeDoc.filename,
        session_number: activeLessonNumber || currentSessionIndex || 1,
        source_file: activeDoc.filename,
      });

      setQuizResult(res.data);
      const refresh = await axios.get(`${apiBaseUrl}/api/assessment/roadmap/${encodeURIComponent(selectedSubject)}?user_id=${currentUserId}`);
      if (refresh.data?.has_roadmap) {
        setCurrentSessionIndex(refresh.data.current_session || currentSessionIndex);
      }
    } catch (e: unknown) {
      const message = axios.isAxiosError(e)
        ? (e.response?.data?.detail as string) || 'Lỗi hệ thống khi nộp bài.'
        : 'Lỗi hệ thống khi nộp bài.';
      toast.error(message);
    } finally {
      setQuizSubmitting(false);
    }
  };

  const handleRelearnWrong = () => {
    const weakTopics: string[] = quizResult?.chapter_feedback?.weak_topics || [];
    const prompt = weakTopics.length
      ? `Giải thích lại các phần em làm sai: ${weakTopics.join('; ')}`
      : `Giải thích lại các nội dung em làm sai trong bài ${activeLessonTopic || 'hiện tại'}`;
    const context = activeLessonContext;
    setQuizMode(false);
    setQuizResult(null);
    setQuizAnswers({});
    setQuizQuestions([]);
    void handleSuggestedPromptClick(prompt);
    if (context) {
      toast.success('Đã quay lại chế độ học lại phần sai.');
    }
  };

  const handleContinueNextDocument = () => {
    const activeDoc = getActiveDocument();
    if (!activeDoc) return;
    const idx = documents.findIndex((d) => d.id === activeDoc.id);
    if (idx >= 0 && idx < documents.length - 1) {
      handleSwitchDocument(documents[idx + 1], idx + 1);
      setQuizMode(false);
      setQuizResult(null);
      setQuizAnswers({});
      setQuizQuestions([]);
      toast.success('Đã chuyển sang tài liệu kế tiếp.');
      return;
    }
    toast('Bạn đã ở tài liệu cuối cùng của môn này.');
  };

  const handleSendMessage = async () => {
    if (!input.trim() || !userId) return;
    const userMsg = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }]);
    await sendChatMessage(userMsg);
  };

  const handleSuggestedPromptClick = async (prompt: string) => {
    if (!userId || loadingChat) return;
    setMessages((prev) => [...prev, { role: 'user', content: prompt }]);
    await sendChatMessage(prompt);
  };

  const handleQuickPromptPaste = (prompt: string) => {
    if (loadingChat) return;
    setInput(prompt);
  };

  // Unified document opening flow - dùng chung cho cả Orbit recommendation và manual opening
  const openDocumentFlow = async (
    targetDocId: number,
    targetSubject: string,
    currentId: number,
    summary?: any
  ) => {
    if (!currentId || !targetSubject || !targetDocId) return;
    setSelectedSubject(targetSubject);
    await autoLoadLearningContext(currentId, targetSubject, false, false, enrolledClasses, targetDocId);

    if (summary && typeof summary === 'object') {
      const title = String(summary.title || '').trim();
      const body = String(summary.summary || '').trim();
      const keyPoints: string[] = Array.isArray(summary.key_points) ? summary.key_points : [];
      const nextSummary = [
        title ? `Tài liệu đề xuất: ${title}` : '',
        body,
        keyPoints.length > 0 ? `Ý chính:\n- ${keyPoints.slice(0, 4).join('\n- ')}` : '',
      ].filter(Boolean).join('\n\n');
      if (nextSummary) {
        setChapterSummary(nextSummary);
        setShowDocumentSummary(true);
      }
    }
  };

  const handleOrbitAction = async (actionMetadata: any) => {
    if (!actionMetadata) return;
    if (actionMetadata.action_type === 'open_route') {
      const route = String(actionMetadata.params?.route || '').trim();
      if (route) {
        window.location.href = route;
      }
      return;
    }
    if (actionMetadata.action_type !== 'open_document') return;
    const params = actionMetadata.params || {};
    const targetSubject = String(params.subject || '').trim();
    const targetDocId = Number(params.document_id || 0);
    const currentId = Number(localStorage.getItem('userId') || localStorage.getItem('user_id') || userId || 0);

    await openDocumentFlow(targetDocId, targetSubject, currentId, params.summary);
  };

  const sendChatMessage = async (message: string) => {
    setLoadingChat(true);
    try {
      const currentId = localStorage.getItem('userId') || localStorage.getItem('user_id');
      const fallbackSubject = selectedSubject || enrolledClasses[0]?.subject || 'all';
      const fallbackClassId = enrolledClasses.find((c) => c.subject === fallbackSubject)?.id || null;
      const res = await axios.post(`${apiBaseUrl}/api/orbit/chat`, {
        subject: fallbackSubject,
        message,
        user_id: Number(currentId),
        class_id: fallbackClassId,
        document_id: getActiveDocument()?.id || null,
        source_file: getActiveDocument()?.filename || '',
      });
      setMessages((prev) => [...prev, { role: 'assistant', content: res.data.reply }]);
      if (res.data?.orbit_mode === 'angry' || res.data?.orbit_mode === 'happy') {
        setOrbitMode(res.data.orbit_mode);
      }
      if (res.data?.orbit_status_text) {
        setOrbitStatusText(String(res.data.orbit_status_text));
      }
      if (res.data?.action_metadata?.should_auto_execute) {
        await handleOrbitAction(res.data.action_metadata);
        setPendingOrbitAction(null);
      } else if (res.data?.action_metadata?.action_type === 'open_document') {
        setPendingOrbitAction(res.data.action_metadata);
      } else {
        setPendingOrbitAction(null);
      }
    } catch (e: unknown) {
      const realError = axios.isAxiosError(e)
        ? (e.response?.data?.detail as string) || e.message || 'Lỗi đường truyền API'
        : 'Lỗi đường truyền API';
      setMessages((prev) => [...prev, { role: 'assistant', content: `❌ **Hệ thống báo lỗi:** ${String(realError)}` }]);
    } finally {
      setLoadingChat(false);
    }
  };

  const handleSubjectNavClick = (subject: string) => {
    if (!userId || !subject) return;
    setSelectedSubject(subject);
    autoLoadLearningContext(userId, subject, false, false);
  };

  const activeDoc = getActiveDocument();
  const activeDocExt = activeDoc ? getFileExt(activeDoc.filename) : '';
  const currentUserId = userId || userIdRef.current || 0;
  const isOrbitAngry = orbitMode === 'angry';
  const orbitMascot = isOrbitAngry ? '/Orbit Angry.png' : '/Orbit Happy.png';
  const orbitPanelClass = isOrbitAngry ? 'border-red-200' : 'border-emerald-200';
  const orbitHeaderBg = isOrbitAngry ? 'from-red-50 to-red-100 border-red-100' : 'from-emerald-50 to-emerald-100 border-emerald-100';
  const orbitHeaderTitle = isOrbitAngry ? 'text-red-800' : 'text-emerald-800';
  const orbitStatusDot = isOrbitAngry ? 'bg-red-500' : 'bg-emerald-500';
  const orbitStatusTextClass = isOrbitAngry ? 'text-red-600' : 'text-emerald-600';
  const orbitBodyBg = isOrbitAngry ? 'bg-red-50/40' : 'bg-emerald-50/40';
  const orbitAssistantAvatar = isOrbitAngry ? 'bg-red-100 border-red-200 text-red-600' : 'bg-emerald-100 border-emerald-200 text-emerald-600';
  const orbitAssistantBubble = isOrbitAngry ? 'bg-white text-slate-700 border border-red-100 rounded-tl-none' : 'bg-white text-slate-700 border border-emerald-100 rounded-tl-none';
  const orbitUserBubble = isOrbitAngry ? 'bg-red-600 text-white rounded-tr-none' : 'bg-emerald-600 text-white rounded-tr-none';
  const orbitInputWrap = isOrbitAngry ? 'bg-red-50 border-red-200 focus-within:border-red-500 ring-red-50' : 'bg-emerald-50 border-emerald-200 focus-within:border-emerald-500 ring-emerald-50';
  const orbitSendBtn = isOrbitAngry ? 'bg-red-600 shadow-red-100' : 'bg-emerald-600 shadow-emerald-100';
  const subjectNavItems = Array.from(new Set(enrolledClasses.map((c) => c.subject).filter(Boolean)));
  const quickOrbitPrompts = [
    'Hôm nay, tôi nên học phần nào',
    'Thành tích học của tôi thế nào',
    'Mở cho tôi tài liệu môn Lập trình hướng đối tượng',
  ];

  return (
    <div className="min-h-screen text-slate-800 flex flex-col pt-[80px] pb-4 px-4 sm:px-6 overflow-y-auto app-bg">
      <div className="max-w-[1600px] w-full mx-auto mb-4 shrink-0">
        <div className="hero-panel p-3 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3 w-full md:w-auto">
            {enrolledClasses.length === 0 ? (
              <div className="flex items-center gap-2 text-amber-600 bg-amber-50 px-3 py-1.5 rounded-xl border border-amber-100 font-black text-[10px] uppercase shrink-0">
                <UserPlus size={14} /> Chưa tham gia lớp nào
              </div>
            ) : (
              <div className="flex items-center gap-2 shrink-0">
                <div className="bg-emerald-50 p-1.5 rounded-lg text-emerald-600 border border-emerald-100 shadow-sm">
                  <CheckCircle2 size={16} />
                </div>
                <span className="text-[10px] font-black text-emerald-700 bg-emerald-50 px-2.5 py-1.5 rounded-lg uppercase tracking-wider border border-emerald-100 whitespace-nowrap">
                  Đã tham gia {enrolledClasses.length} lớp học
                </span>
              </div>
            )}
          </div>

          <div className="flex gap-2 w-full md:w-auto md:max-w-sm shrink-0">
            <input
              type="text"
              placeholder="Nhập mã CODE lớp học..."
              value={classCode}
              onChange={(e) => setClassCode(e.target.value)}
              className="flex-1 bg-slate-50 border border-slate-200 outline-none text-[11px] font-bold px-4 py-2 rounded-xl focus:ring-2 ring-indigo-500 transition-all uppercase placeholder:normal-case text-slate-900 placeholder:text-slate-400"
            />
            <button
              onClick={handleJoinClass}
              disabled={joining || !classCode.trim()}
              className="bg-slate-900 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-black disabled:opacity-50 flex items-center gap-2 transition-transform active:scale-95 shadow-sm"
            >
              {joining ? <Loader2 className="animate-spin" size={14} /> : 'Tham gia'}
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 grid grid-cols-1 xl:grid-cols-12 gap-6 min-h-0 w-full max-w-[1600px] mx-auto">
        <div className="xl:col-span-12 flex flex-col gap-4 h-full min-h-0">
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm shrink-0 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg border border-indigo-100 shadow-sm">
                <BookOpen className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-sm font-black text-slate-800 uppercase">Bài Đang Học</h2>
                <p className="text-[10px] text-slate-500 font-medium tracking-tight mt-0.5">Tài liệu PDF/PPTX của buổi học hiện tại</p>
              </div>
            </div>

            <div className="flex w-full sm:w-auto gap-2 items-center">
              <div className="px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-[10px] font-black uppercase tracking-widest text-slate-600">
                {selectedSubject || 'Chưa chọn môn học'}
              </div>
            </div>
          </div>

          <div className="flex-1 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col min-h-0 relative">
            {enrolledClasses.length === 0 ? (
              <div className="absolute inset-y-0 left-0 right-0 lg:right-[276px] flex flex-col items-center justify-center text-slate-400">
                <BookOpen className="w-12 h-12 mb-3 opacity-20" />
                <p className="text-xs font-bold uppercase tracking-widest">Bạn cần tham gia lớp học trước</p>
              </div>
            ) : loadingContext ? (
              <div className="absolute inset-y-0 left-0 right-0 lg:right-[276px] flex flex-col items-center justify-center text-indigo-600">
                <Loader2 className="w-10 h-10 mb-4 animate-spin" />
                <p className="text-xs font-bold uppercase tracking-widest animate-pulse">Đang tải tài liệu...</p>
              </div>
            ) : documents.length === 0 ? (
              <div className="absolute inset-y-0 left-0 right-0 lg:right-[276px] flex flex-col items-center justify-center text-slate-400 px-5">
                <FileText className="w-12 h-12 mb-3 opacity-20" />
                <p className="text-xs font-bold uppercase tracking-widest">Giáo viên chưa upload tài liệu cho môn này</p>
                <p className="text-[11px] mt-2 text-center max-w-md">Xin lỗi, hiện chưa có học liệu để mở buổi học. Bạn hãy liên hệ giáo viên để được cập nhật tài liệu PDF/PPTX.</p>
              </div>
            ) : (
              <>
                <div className="shrink-0 border-b border-slate-100 px-4 py-3 bg-slate-50/70">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <span className="text-[10px] font-black uppercase tracking-wider text-indigo-600">Trình độ: {learnerLevel}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-bold text-slate-500 uppercase">Buổi {activeLessonNumber || currentSessionIndex}</span>
                      <button
                        onClick={handleLoadRoadmap}
                        disabled={loadingContext || enrolledClasses.length === 0}
                        className="px-3 py-1.5 bg-slate-900 text-white text-[10px] font-black uppercase tracking-widest rounded-lg hover:bg-indigo-600 transition-all flex items-center gap-2 disabled:opacity-50 shadow-sm"
                      >
                        {loadingContext ? <Loader2 className="animate-spin" size={12} /> : <>Đồng bộ</>}
                      </button>
                    </div>
                  </div>
                  <div className="flex gap-2 overflow-x-auto custom-scrollbar pb-1">
                    {documents.map((doc, idx) => (
                      <button
                        key={doc.id}
                        onClick={() => handleSwitchDocument(doc, idx)}
                        className={`px-3 py-2 rounded-lg text-[10px] font-black uppercase whitespace-nowrap border transition-all ${
                          activeDocumentId === doc.id
                            ? 'bg-indigo-600 text-white border-indigo-600'
                            : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'
                        }`}
                      >
                        Tài liệu {idx + 1}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex-1 min-h-0 p-4 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-4">
                  <div className="min-h-0 flex flex-col gap-3">
                    {activeDoc && (
                      <div className="shrink-0 px-3 py-2 rounded-lg border border-indigo-100 bg-indigo-50/50">
                        <p className="text-xs font-black text-slate-800 truncate">{activeDoc.filename}</p>
                        <p className="text-[11px] text-slate-600 mt-1">{activeLessonTopic || 'Đang học theo nội dung tài liệu đã chọn'}</p>
                      </div>
                    )}

                    <div className="rounded-xl border border-slate-200 overflow-visible bg-slate-50">
                      {!activeDoc ? (
                        <div className="h-full flex flex-col items-center justify-center text-slate-400">
                          <FileText className="w-12 h-12 mb-2 opacity-25" />
                          <p className="text-xs font-bold uppercase">Chọn tài liệu để bắt đầu học</p>
                        </div>
                      ) : (
                        <div className="h-full flex flex-col p-0">
                          {activeDocExt === 'pdf' ? (
                            <div className="bg-white overflow-visible">
                              <iframe
                                title={`PDF ${activeDoc.filename}`}
                                src={`${apiBaseUrl}/api/documents/view/${activeDoc.id}?user_id=${currentUserId}#page=1&zoom=page-width`}
                                className="w-full h-[140vh]"
                              />
                            </div>
                          ) : (
                            <div className="flex-1 min-h-0 overflow-y-auto bg-white border border-slate-200 rounded-lg p-3 space-y-3 custom-scrollbar">
                              {loadingPreview ? (
                                <div className="h-full flex items-center justify-center text-slate-500 text-xs font-bold">
                                  Đang tải nội dung tài liệu...
                                </div>
                              ) : previewSegments.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-slate-400 text-xs font-bold gap-2">
                                  <p>Hệ thống chưa đọc được nội dung từ file gốc.</p>
                                  <p>Vui lòng thử đồng bộ lại hoặc liên hệ giáo viên upload lại file.</p>
                                </div>
                              ) : (
                                previewSegments.map((seg, idx) => (
                                  <div key={`${seg.title}-${idx}`} className="border border-slate-100 rounded-lg p-3">
                                    <p className="text-[10px] font-black uppercase text-indigo-600 mb-1">{seg.title}</p>
                                    <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap">{seg.content}</p>
                                  </div>
                                ))
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <aside className="min-h-0 flex flex-col gap-4">
                    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm flex flex-col gap-2">
                      <button
                        onClick={handleTakeTest}
                        disabled={!activeDoc || quizLoading}
                        className="w-full px-4 py-3 bg-indigo-600 text-white text-xs font-black uppercase tracking-wider rounded-xl flex items-center justify-center gap-2 hover:bg-indigo-700 disabled:opacity-50 transition-all"
                      >
                        {quizLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlayCircle className="w-4 h-4" />} Làm bài kiểm tra theo tài liệu này
                      </button>
                      {activeDoc && (
                        <a href={`${apiBaseUrl}/api/documents/download/${activeDoc.id}`} target="_blank" className="px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-slate-700 text-[10px] font-bold inline-flex items-center justify-center gap-1">
                          <ExternalLink size={12} /> Tải file
                        </a>
                      )}
                    </div>

                    <div className="flex-1 min-h-0 rounded-xl border border-slate-200 bg-slate-50 p-3 flex flex-col gap-2">
                      <p className="text-[11px] font-black uppercase tracking-widest text-slate-600 px-1">📚 Danh sách môn học</p>
                    <div className="overflow-y-auto custom-scrollbar flex-1 pr-1 space-y-2">
                      {subjectNavItems.map((subject) => {
                        const isActive = selectedSubject === subject;
                        const relatedClasses = enrolledClasses.filter((c) => c.subject === subject);
                        return (
                          <button
                            key={subject}
                            onClick={() => handleSubjectNavClick(subject)}
                            className={`w-full text-left rounded-lg border px-3 py-2.5 transition-all ${isActive ? 'bg-indigo-600 border-indigo-600 text-white shadow-md' : 'bg-white border-slate-200 hover:border-indigo-400 text-slate-700'}`}
                          >
                            <p className="text-[11px] font-black uppercase leading-tight">{subject}</p>
                            <p className={`text-[10px] mt-1.5 font-semibold ${isActive ? 'text-indigo-100' : 'text-slate-500'}`}>
                              {relatedClasses.length} lớp học
                            </p>
                          </button>
                        );
                      })}
                    </div>
                    </div>
                  </aside>
                </div>
              </>
            )}

            {(enrolledClasses.length === 0 || loadingContext || documents.length === 0) && (
              <aside className="absolute right-3 top-3 bottom-3 w-[260px] rounded-xl border border-slate-200 bg-slate-50 p-3 hidden lg:flex flex-col gap-2">
                    <p className="text-[11px] font-black uppercase tracking-widest text-slate-600 px-1">📚 Danh sách môn học</p>
                <div className="overflow-y-auto custom-scrollbar flex-1 pr-1 space-y-2">
                  {subjectNavItems.map((subject) => {
                    const isActive = selectedSubject === subject;
                    const relatedClasses = enrolledClasses.filter((c) => c.subject === subject);
                    return (
                      <button
                        key={subject}
                        onClick={() => handleSubjectNavClick(subject)}
                        className={`w-full text-left rounded-lg border px-3 py-2 transition-all ${isActive ? 'bg-indigo-600 border-indigo-600 text-white shadow-sm' : 'bg-white border-slate-200 hover:border-indigo-300 text-slate-700'}`}
                      >
                        <p className="text-[11px] font-black uppercase leading-tight">{subject}</p>
                        <p className={`text-[10px] mt-1 ${isActive ? 'text-indigo-100' : 'text-slate-500'}`}>
                          {relatedClasses.length} lớp học
                        </p>
                      </button>
                    );
                  })}
                </div>
              </aside>
            )}
          </div>
        </div>

        {orbitCollapsed && (
          <button
            onClick={() => setOrbitCollapsed(false)}
            className="nova-launcher fixed bottom-5 right-5 z-[80]"
            title="Mở Orbit"
            aria-label="Mở Orbit"
          >
            <span className="nova-launcher-glow" />
            <img
              src={orbitMascot}
              alt="Orbit"
              className="h-11 w-11 rounded-full object-cover border border-white/70"
            />
            <span className="sr-only">Mở Orbit</span>
          </button>
        )}

        {!orbitCollapsed && (
        <div className={`fixed right-4 top-[96px] z-30 w-[430px] max-w-[92vw] h-[calc(100vh-120px)] flex flex-col bg-white rounded-2xl border shadow-2xl overflow-hidden ${orbitPanelClass}`}>
          <div className={`border-b flex items-end justify-between px-3 py-2 bg-gradient-to-r shrink-0 ${orbitHeaderBg}`}>
            <div className="flex items-end gap-2">
              <img
                src={orbitMascot}
                alt="Orbit Teacher" 
                className="h-12 w-auto object-contain"
              />
              <div>
                <h3 className={`text-xs font-black uppercase tracking-tight ${orbitHeaderTitle}`}>Orbit Agent</h3>
                <p className={`text-[9px] font-bold uppercase tracking-widest flex items-center gap-1 ${orbitStatusTextClass}`}>
                  <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${orbitStatusDot}`}></span> {orbitStatusText}
                </p>
              </div>
            </div>
            <button
              onClick={() => setOrbitCollapsed(true)}
              className={`h-8 w-8 rounded-lg border flex items-center justify-center transition-all ${isOrbitAngry ? 'border-red-200 text-red-700 hover:bg-red-100' : 'border-emerald-200 text-emerald-700 hover:bg-emerald-100'}`}
              title="Thu gọn Orbit"
              aria-label="Thu gọn Orbit"
            >
              <Minimize2 size={14} />
            </button>
          </div>

          <div className={`flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar ${orbitBodyBg}`}>
            {activeLessonContext && showDocumentSummary && (loadingSummary || !!chapterSummary) && (
              <div className={`rounded-xl p-3 space-y-2 ${isOrbitAngry ? 'bg-red-50 border border-red-100' : 'bg-emerald-50 border border-emerald-100'}`}>
                <p className={`text-[10px] font-black uppercase tracking-wider ${isOrbitAngry ? 'text-red-700' : 'text-emerald-700'}`}>Tóm tắt kiến thức tài liệu</p>
                <p className="text-xs text-slate-700 font-medium leading-relaxed whitespace-pre-line">
                  {loadingSummary ? 'AI đang tóm tắt toàn bộ tài liệu, vui lòng chờ...' : chapterSummary}
                </p>
                {suggestedPrompts.length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {suggestedPrompts.map((prompt, idx) => (
                      <button
                        key={`${idx}-${prompt}`}
                        onClick={() => handleSuggestedPromptClick(prompt)}
                        disabled={loadingChat}
                        className={`px-2.5 py-1.5 rounded-lg bg-white text-[10px] font-bold transition-all disabled:opacity-50 ${isOrbitAngry ? 'border border-red-200 text-red-700 hover:bg-red-100' : 'border border-emerald-200 text-emerald-700 hover:bg-emerald-100'}`}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center opacity-30 text-center">
                <MessageSquare size={48} className="mb-4" />
                <p className="text-xs font-bold uppercase tracking-widest">Không gian tri thức AI</p>
                <p className="text-[10px] font-medium mt-1">Bấm Học với AI ở bài học bên trái để bắt đầu</p>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'assistant' && (
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 shadow-sm border ${orbitAssistantAvatar}`}>
                      {isOrbitAngry ? <Flame size={16} /> : <Smile size={16} />}
                    </div>
                  )}
                  <div className={`max-w-[85%] p-4 rounded-2xl text-[13px] leading-relaxed shadow-sm ${msg.role === 'user' ? orbitUserBubble : orbitAssistantBubble}`}>
                    {msg.role === 'assistant' ? (
                      <ReactMarkdown components={{ strong: ({ ...props }) => <span className={`font-bold ${isOrbitAngry ? 'text-red-700' : 'text-emerald-700'}`} {...props} />, ul: ({ ...props }) => <ul className="list-disc pl-4 space-y-1.5 my-2" {...props} />, p: ({ ...props }) => <p className="mb-2 last:mb-0" {...props} /> }}>
                        {msg.content}
                      </ReactMarkdown>
                    ) : (
                      <p className="font-medium">{msg.content}</p>
                    )}
                  </div>
                </div>
              ))
            )}
            {loadingChat && (
              <div className="flex justify-start">
                <div className={`bg-white rounded-2xl rounded-tl-none p-3 shadow-sm flex items-center gap-1.5 border ${isOrbitAngry ? 'border-red-100' : 'border-emerald-100'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full animate-bounce ${isOrbitAngry ? 'bg-red-400' : 'bg-emerald-400'}`}></span>
                  <span className={`w-1.5 h-1.5 rounded-full animate-bounce delay-75 ${isOrbitAngry ? 'bg-red-400' : 'bg-emerald-400'}`}></span>
                  <span className={`w-1.5 h-1.5 rounded-full animate-bounce delay-150 ${isOrbitAngry ? 'bg-red-400' : 'bg-emerald-400'}`}></span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className={`p-4 bg-white border-t shrink-0 ${isOrbitAngry ? 'border-red-100' : 'border-emerald-100'}`}>
            <div className={`flex gap-2 items-center p-1.5 rounded-2xl border focus-within:ring-2 transition-all ${orbitInputWrap}`}>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                placeholder={'Nhắn cho Orbit Agent...'}
                disabled={loadingChat}
                className="flex-1 bg-transparent border-none outline-none text-[13px] font-medium px-3 h-10 disabled:opacity-50 text-slate-900 placeholder:text-slate-400"
              />
              <button onClick={handleSendMessage} disabled={loadingChat || !input.trim()} className={`w-10 h-10 text-white rounded-xl flex items-center justify-center shadow-lg active:scale-90 transition-all disabled:opacity-30 disabled:active:scale-100 shrink-0 ${orbitSendBtn}`}>
                <Send size={16} />
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {quickOrbitPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => handleQuickPromptPaste(prompt)}
                  disabled={loadingChat}
                  className={`px-2.5 py-1.5 rounded-lg bg-white text-[10px] font-bold transition-all disabled:opacity-50 ${isOrbitAngry ? 'border border-red-200 text-red-700 hover:bg-red-100' : 'border border-emerald-200 text-emerald-700 hover:bg-emerald-100'}`}
                >
                  {prompt}
                </button>
              ))}
            </div>
            {pendingOrbitAction?.action_type === 'open_document' && (
              <div className={`mt-2 rounded-xl border p-2.5 ${isOrbitAngry ? 'border-red-200 bg-red-50' : 'border-emerald-200 bg-emerald-50'}`}>
                <p className={`text-[10px] font-black uppercase tracking-wider mb-2 ${isOrbitAngry ? 'text-red-700' : 'text-emerald-700'}`}>Orbit đề xuất tài liệu học</p>
                <button
                  onClick={async () => {
                    await handleOrbitAction(pendingOrbitAction);
                    setPendingOrbitAction(null);
                    setMessages((prev) => [
                      ...prev,
                      { role: 'assistant', content: '✅ Đã mở tài liệu đề xuất. Bắt đầu học thôi.' },
                    ]);
                  }}
                  disabled={loadingChat}
                  className={`w-full px-3 py-2 rounded-lg text-white text-[11px] font-black uppercase tracking-wide disabled:opacity-50 ${isOrbitAngry ? 'bg-red-600 hover:bg-red-700' : 'bg-emerald-600 hover:bg-emerald-700'}`}
                >
                  {String(pendingOrbitAction?.confirm_button_text || 'OK, mở tài liệu đề xuất')}
                </button>
              </div>
            )}
          </div>
        </div>
        )}
      </div>

      {quizMode && quizQuestions.length > 0 && (
        <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-4xl max-h-[90vh] overflow-hidden bg-white rounded-2xl border border-slate-200 shadow-2xl flex flex-col">
            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <p className="text-[10px] uppercase font-black text-indigo-600 tracking-wider">Trắc nghiệm theo tài liệu</p>
                <p className="text-sm font-bold text-slate-800">Câu {quizIndex + 1}/{quizQuestions.length}</p>
              </div>
              {!quizResult && (
                <button
                  onClick={() => setQuizMode(false)}
                  className="px-3 py-1.5 text-[10px] font-black uppercase rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-100"
                >
                  Đóng
                </button>
              )}
            </div>

            {!quizResult ? (
              <>
                <div className="p-5 overflow-y-auto custom-scrollbar space-y-4">
                  <h4 className="text-base font-bold text-slate-800 whitespace-pre-wrap">{quizQuestions[quizIndex].content}</h4>
                  <div className="space-y-2">
                    {(quizQuestions[quizIndex].options || []).map((opt, idx) => {
                      const label = normalizeOptionLabel(opt, idx);
                      const chosen = quizAnswers[quizQuestions[quizIndex].id] === label;
                      return (
                        <button
                          key={`${label}-${idx}`}
                          onClick={() => setQuizAnswers((prev) => ({ ...prev, [quizQuestions[quizIndex].id]: label }))}
                          className={`w-full text-left p-3 rounded-xl border transition-all ${chosen ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:border-indigo-300'}`}
                        >
                          <span className="text-xs font-black text-indigo-600 mr-2">{label}.</span>
                          <span className="text-sm text-slate-700">{String(opt).replace(/^[A-D][\.\:\-\)]\s*/i, '')}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="px-5 py-4 border-t border-slate-100 flex gap-3">
                  <button
                    onClick={() => setQuizIndex((v) => Math.max(0, v - 1))}
                    disabled={quizIndex === 0}
                    className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-black uppercase text-slate-600 disabled:opacity-40"
                  >
                    Câu trước
                  </button>
                  {quizIndex < quizQuestions.length - 1 ? (
                    <button
                      onClick={() => setQuizIndex((v) => Math.min(quizQuestions.length - 1, v + 1))}
                      className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-black uppercase"
                    >
                      Câu tiếp
                    </button>
                  ) : (
                    <button
                      onClick={submitInlineQuiz}
                      disabled={quizSubmitting}
                      className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-xs font-black uppercase disabled:opacity-50"
                    >
                      {quizSubmitting ? 'Đang nộp...' : 'Nộp bài'}
                    </button>
                  )}
                </div>
              </>
            ) : (
              <div className="p-6 overflow-y-auto custom-scrollbar space-y-4">
                <p className="text-lg font-black text-slate-800">Kết quả: {Math.round(Number(quizResult.score || 0))}% ({quizResult.correct_count}/{quizResult.total_questions})</p>
                <p className="text-sm text-slate-700">{quizResult.message}</p>

                {quizResult?.chapter_feedback?.weak_topics && Array.isArray(quizResult.chapter_feedback.weak_topics) && quizResult.chapter_feedback.weak_topics.length > 0 && (
                  <div className="bg-red-50 border border-red-100 rounded-xl p-3">
                    <p className="text-[10px] uppercase font-black text-red-600 mb-2">Các phần cần học lại</p>
                    {quizResult.chapter_feedback.weak_topics.map((w: string, i: number) => (
                      <p key={`${i}-${w}`} className="text-xs text-red-800">- {w}</p>
                    ))}
                  </div>
                )}

                <div className="flex flex-wrap gap-2 pt-2">
                  {quizResult?.is_passed ? (
                    <>
                      <button onClick={handleRelearnWrong} className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-black uppercase text-slate-700">Học lại chỗ sai</button>
                      <button onClick={handleContinueNextDocument} className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-black uppercase">Sang tài liệu khác</button>
                      <button onClick={() => { setQuizMode(false); setQuizResult(null); }} className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-xs font-black uppercase">Hoàn tất</button>
                    </>
                  ) : (
                    <>
                      <button onClick={handleRelearnWrong} className="px-4 py-2 rounded-lg border border-slate-300 text-xs font-black uppercase text-slate-700">Học lại phần sai</button>
                      <button onClick={startInlineQuiz} className="px-4 py-2 rounded-lg bg-red-600 text-white text-xs font-black uppercase">Làm lại bài trắc nghiệm</button>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}