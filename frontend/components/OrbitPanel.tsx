import React, { useState, useEffect, useRef } from 'react';
import { Send, Minimize2, Flame, Smile, MessageSquare } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

import { apiClient, longRequestConfig, normalizeApiError, runLongRequest } from '../services/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface PendingOrbitAction {
  action_type?: string;
  confirm_button_text?: string;
  should_auto_execute?: boolean;
  session_id?: number | null;
  params?: Record<string, unknown>;
}

interface OrbitPanelSnapshot {
  orbitCollapsed?: boolean;
  orbitMode?: 'angry' | 'happy';
  orbitStatusText?: string;
  messages?: Message[];
  input?: string;
  pendingOrbitAction?: PendingOrbitAction | null;
  sessionId?: number | null;
}

const orbitPanelCache = new Map<string, OrbitPanelSnapshot>();

interface EnrolledClassSummary {
  id?: number | null;
  subject?: string;
}

interface OrbitPanelProps {
  userId: number;
  classId?: number | null;
  documentId?: number | null;
  sourceFile?: string;
  selectedSubject?: string;
  onAction?: (actionMetadata: PendingOrbitAction) => Promise<void>;
  enrolledClasses?: EnrolledClassSummary[];
  apiBaseUrl: string;
}

export default function OrbitPanel({
  userId,
  classId,
  documentId,
  sourceFile,
  selectedSubject,
  onAction,
  enrolledClasses = [],
  apiBaseUrl,
}: OrbitPanelProps) {
  const storageKey = `orbit_panel_state_${userId || 'guest'}`;
  const [orbitCollapsed, setOrbitCollapsed] = useState(false);
  const [orbitMode, setOrbitMode] = useState<'angry' | 'happy'>('happy');
  const [orbitStatusText, setOrbitStatusText] = useState('Đang vui vẻ');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loadingChat, setLoadingChat] = useState(false);
  const [slowChatNotice, setSlowChatNotice] = useState(false);
  const [pendingOrbitAction, setPendingOrbitAction] = useState<PendingOrbitAction | null>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const quickOrbitPrompts = [
    'Hôm nay, tôi nên học phần nào',
    'Thành tích học của tôi thế nào',
    'Mở cho tôi tài liệu môn Lập trình hướng đối tượng',
  ];

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loadingChat]);

  const executeOrbitAction = async (actionMetadata: PendingOrbitAction) => {
    if (!actionMetadata) return;
    if (actionMetadata.action_type === 'open_route') {
      const route = String(actionMetadata.params?.route || '').trim();
      if (route && typeof window !== 'undefined') {
        window.location.href = route;
      }
      return;
    }

    if (onAction) {
      await onAction(actionMetadata);
      return;
    }

    if (actionMetadata.action_type === 'open_document' && typeof window !== 'undefined') {
      try {
        localStorage.setItem(`orbit_pending_action_${userId}`, JSON.stringify(actionMetadata));
      } catch {
        // ignore storage failures
      }
      window.location.href = '/adaptive';
    }
  };

  useEffect(() => {
    try {
      const cached = orbitPanelCache.get(storageKey);
      if (cached) {
        if (typeof cached.orbitCollapsed === 'boolean') setOrbitCollapsed(cached.orbitCollapsed);
        if (cached.orbitMode === 'angry' || cached.orbitMode === 'happy') setOrbitMode(cached.orbitMode);
        if (typeof cached.orbitStatusText === 'string' && cached.orbitStatusText.trim()) setOrbitStatusText(cached.orbitStatusText);
        if (Array.isArray(cached.messages)) setMessages(cached.messages.slice(-40));
        if (typeof cached.input === 'string') setInput(cached.input);
        if (cached.pendingOrbitAction) setPendingOrbitAction(cached.pendingOrbitAction);
        if (typeof cached.sessionId === 'number') setSessionId(cached.sessionId);
        setHydrated(true);
        return;
      }

      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as OrbitPanelSnapshot;
      orbitPanelCache.set(storageKey, parsed);
      if (typeof parsed.orbitCollapsed === 'boolean') setOrbitCollapsed(parsed.orbitCollapsed);
      if (parsed.orbitMode === 'angry' || parsed.orbitMode === 'happy') setOrbitMode(parsed.orbitMode);
      if (typeof parsed.orbitStatusText === 'string' && parsed.orbitStatusText.trim()) setOrbitStatusText(parsed.orbitStatusText);
      if (Array.isArray(parsed.messages)) setMessages(parsed.messages.slice(-40));
      if (typeof parsed.input === 'string') setInput(parsed.input);
      if (parsed.pendingOrbitAction) setPendingOrbitAction(parsed.pendingOrbitAction);
      if (typeof parsed.sessionId === 'number') setSessionId(parsed.sessionId);
    } catch {
      // ignore storage parse errors
    } finally {
      setHydrated(true);
    }
  }, [storageKey]);

  useEffect(() => {
    if (!hydrated || !userId) return;
    if (messages.length > 0) return;

    const fetchHistory = async () => {
      try {
        const params = sessionId ? { session_id: sessionId, limit: 40 } : { limit: 40 };
        const res = await apiClient.get(`/api/orbit/history/${userId}`, {
          params,
          baseURL: apiBaseUrl,
          timeout: 12000,
        });
        const rawMessages = Array.isArray(res.data?.messages)
          ? (res.data.messages as Array<{ role?: unknown; content?: unknown }>)
          : [];
        const serverMessages = rawMessages
          .map((item) => ({ role: item?.role, content: item?.content }))
          .filter(
            (item): item is Message =>
              (item.role === 'user' || item.role === 'assistant') && typeof item.content === 'string'
          );
        if (serverMessages.length > 0) {
          setMessages(serverMessages.slice(-40));
        }
        if (typeof res.data?.session_id === 'number') {
          setSessionId(res.data.session_id);
        }
      } catch {
        // ignore history fetch failures
      }
    };

    void fetchHistory();
  }, [hydrated, userId, sessionId, messages.length, apiBaseUrl]);

  useEffect(() => {
    setHydrated(false);
  }, [storageKey]);

  useEffect(() => {
    if (!hydrated) return;
    const snapshot: OrbitPanelSnapshot = {
      orbitCollapsed,
      orbitMode,
      orbitStatusText,
      messages: messages.slice(-40),
      input,
      pendingOrbitAction,
      sessionId,
    };
    orbitPanelCache.set(storageKey, snapshot);
    try {
      localStorage.setItem(storageKey, JSON.stringify(snapshot));
    } catch {
      // ignore storage write failures
    }
  }, [storageKey, hydrated, orbitCollapsed, orbitMode, orbitStatusText, messages, input, pendingOrbitAction, sessionId]);

  const handleQuickPromptPaste = (prompt: string) => {
    if (loadingChat) return;
    setInput(prompt);
  };

  const sendChatMessage = async (message: string) => {
    setLoadingChat(true);
    try {
      const fallbackSubject = selectedSubject || enrolledClasses[0]?.subject || 'all';
      const fallbackClassId = enrolledClasses.find((c) => c.subject === fallbackSubject)?.id || classId || null;

      const res = await runLongRequest(
        () =>
          apiClient.post(
            '/api/orbit/chat',
            {
              subject: fallbackSubject,
              message,
              user_id: userId,
              class_id: fallbackClassId,
              document_id: documentId || null,
              source_file: sourceFile || '',
              session_id: sessionId,
            },
            {
              ...longRequestConfig,
              baseURL: apiBaseUrl,
            }
          ),
        {
          onSlowStateChange: setSlowChatNotice,
          slowDelayMs: 4500,
        }
      );

      const nextSessionId = typeof res.data?.session_id === 'number' ? res.data.session_id : sessionId;
      if (typeof res.data?.session_id === 'number') {
        setSessionId(res.data.session_id);
      }

      setMessages((prev) => [...prev, { role: 'assistant', content: res.data.reply }]);
      if (res.data?.orbit_mode === 'angry' || res.data?.orbit_mode === 'happy') {
        setOrbitMode(res.data.orbit_mode);
      }
      if (res.data?.orbit_status_text) {
        setOrbitStatusText(String(res.data.orbit_status_text));
      }
      const actionMetadata = res.data?.action_metadata
        ? { ...res.data.action_metadata, session_id: nextSessionId }
        : null;
      if (actionMetadata?.should_auto_execute) {
        await executeOrbitAction(actionMetadata);
        setPendingOrbitAction(null);
      } else if (actionMetadata?.action_type === 'open_document') {
        setPendingOrbitAction(actionMetadata);
      } else {
        setPendingOrbitAction(null);
      }
    } catch (e: unknown) {
      const realError = normalizeApiError(e, 'Orbit tạm thời chưa thể phản hồi.');
      setMessages((prev) => [...prev, { role: 'assistant', content: `❌ **Hệ thống báo lỗi:** ${String(realError)}` }]);
    } finally {
      setLoadingChat(false);
    }
  };

  const handleSendMessage = async () => {
    if (!input.trim() || !userId) return;
    const userMsg = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }]);
    await sendChatMessage(userMsg);
  };

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

  return (
    <>
      {orbitCollapsed && (
        <button
          onClick={() => setOrbitCollapsed(false)}
          className={`agent-launcher fixed bottom-5 right-5 z-[80] ${isOrbitAngry ? 'agent-launcher--orbit-angry' : 'agent-launcher--orbit'}`}
          title="Mở Orbit"
          aria-label="Mở Orbit"
        >
          <span className="agent-launcher-shimmer" />
          <span className="agent-launcher-core" />
          <img
            src={orbitMascot}
            alt="Orbit"
            className="agent-launcher-image h-10 w-10 rounded-full border border-white/65 object-cover shadow-[0_0_18px_rgba(255,255,255,0.18)]"
          />
          <span className="sr-only">Mở Orbit</span>
        </button>
      )}

      {!orbitCollapsed && (
        <div className={`fixed right-4 top-[96px] z-30 flex h-[calc(100vh-136px)] w-[372px] max-w-[90vw] flex-col overflow-hidden rounded-[1.35rem] border bg-white shadow-2xl ${orbitPanelClass}`}>
          <div className={`border-b flex items-center justify-between px-4 py-3 bg-gradient-to-r shrink-0 ${orbitHeaderBg}`}>
            <div className="flex items-center gap-3">
              <img
                src={orbitMascot}
                alt="Orbit Teacher"
                className="h-9 w-auto object-contain"
              />
              <div>
                <h3 className={`text-[13px] font-black tracking-[-0.02em] ${orbitHeaderTitle}`}>Orbit Agent</h3>
                <p className={`text-[9px] font-semibold uppercase tracking-[0.14em] flex items-center gap-1.5 ${orbitStatusTextClass}`}>
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

          <div className={`flex-1 overflow-y-auto p-3 space-y-2.5 custom-scrollbar ${orbitBodyBg}`}>
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center opacity-30 text-center">
                <MessageSquare size={42} className="mb-4" />
                <p className="text-[14px] font-bold tracking-[0.03em]">Không gian tri thức AI</p>
                <p className="mt-1 text-[11px] font-medium">Bấm Gửi ở bên dưới để bắt đầu</p>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {msg.role === 'assistant' && (
                    <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-xl border shadow-sm ${orbitAssistantAvatar}`}>
                      {isOrbitAngry ? <Flame size={15} /> : <Smile size={15} />}
                    </div>
                  )}
                  <div className={`max-w-[88%] rounded-[1.05rem] px-3 py-2.5 text-[12px] leading-5 shadow-sm ${msg.role === 'user' ? orbitUserBubble : orbitAssistantBubble}`}>
                    {msg.role === 'assistant' ? (
                      <ReactMarkdown components={{ strong: ({ ...props }) => <span className={`font-bold ${isOrbitAngry ? 'text-red-700' : 'text-emerald-700'}`} {...props} />, ul: ({ ...props }) => <ul className="my-2 list-disc space-y-1 pl-4" {...props} />, p: ({ ...props }) => <p className="mb-2 last:mb-0" {...props} /> }}>
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
              <div className="flex flex-col items-start gap-2">
                <div className={`flex items-center gap-1.5 rounded-2xl rounded-tl-none border bg-white p-3 shadow-sm ${isOrbitAngry ? 'border-red-100' : 'border-emerald-100'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full animate-bounce ${isOrbitAngry ? 'bg-red-400' : 'bg-emerald-400'}`}></span>
                  <span className={`w-1.5 h-1.5 rounded-full animate-bounce delay-75 ${isOrbitAngry ? 'bg-red-400' : 'bg-emerald-400'}`}></span>
                  <span className={`w-1.5 h-1.5 rounded-full animate-bounce delay-150 ${isOrbitAngry ? 'bg-red-400' : 'bg-emerald-400'}`}></span>
                </div>
                {slowChatNotice && (
                  <div className={`rounded-xl border px-3 py-2 text-[10px] font-semibold ${isOrbitAngry ? 'border-red-200 bg-white text-red-700' : 'border-emerald-200 bg-white text-emerald-700'}`}>
                    Yêu cầu vẫn đang được xử lý, Orbit chưa mất kết nối. Vui lòng chờ thêm một chút.
                  </div>
                )}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className={`p-3 bg-white border-t shrink-0 ${isOrbitAngry ? 'border-red-100' : 'border-emerald-100'}`}>
            <div className={`flex gap-2 items-center p-1.5 rounded-2xl border focus-within:ring-2 transition-all ${orbitInputWrap}`}>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                placeholder={'Nhắn cho Orbit Agent...'}
                disabled={loadingChat}
                className="h-9 flex-1 border-none bg-transparent px-3 text-[12px] font-medium text-slate-900 outline-none placeholder:text-slate-400 disabled:opacity-50"
              />
              <button onClick={handleSendMessage} disabled={loadingChat || !input.trim()} className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-white shadow-lg transition-all active:scale-90 disabled:opacity-30 disabled:active:scale-100 ${orbitSendBtn}`}>
                <Send size={14} />
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {quickOrbitPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => handleQuickPromptPaste(prompt)}
                  disabled={loadingChat}
                  className={`rounded-2xl bg-white px-2.5 py-1.5 text-[10px] font-semibold transition-all disabled:opacity-50 ${isOrbitAngry ? 'border border-red-200 text-red-700 hover:bg-red-100' : 'border border-emerald-200 text-emerald-700 hover:bg-emerald-100'}`}
                >
                  {prompt}
                </button>
              ))}
            </div>
            {pendingOrbitAction?.action_type === 'open_document' && (
              <div className={`mt-2 rounded-xl border p-2.5 ${isOrbitAngry ? 'border-red-200 bg-red-50' : 'border-emerald-200 bg-emerald-50'}`}>
                <p className={`mb-2 text-[10px] font-black uppercase tracking-[0.14em] ${isOrbitAngry ? 'text-red-700' : 'text-emerald-700'}`}>Orbit đề xuất tài liệu học</p>
                <button
                  onClick={async () => {
                    await executeOrbitAction(pendingOrbitAction);
                    setPendingOrbitAction(null);
                    setMessages((prev) => [
                      ...prev,
                      { role: 'assistant', content: '✅ Đã mở tài liệu đề xuất. Bắt đầu học thôi.' },
                    ]);
                  }}
                  disabled={loadingChat}
                  className={`w-full rounded-2xl px-3 py-2 text-[11px] font-bold tracking-[0.02em] text-white disabled:opacity-50 ${isOrbitAngry ? 'bg-red-600 hover:bg-red-700' : 'bg-emerald-600 hover:bg-emerald-700'}`}
                >
                  {String(pendingOrbitAction?.confirm_button_text || 'OK, mở tài liệu đề xuất')}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
