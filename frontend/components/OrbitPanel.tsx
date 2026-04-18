import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Send, Minimize2, Flame, Smile, MessageSquare } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface PendingOrbitAction {
  action_type?: string;
  confirm_button_text?: string;
  should_auto_execute?: boolean;
  params?: Record<string, any>;
}

interface OrbitPanelProps {
  userId: number;
  classId?: number | null;
  documentId?: number | null;
  sourceFile?: string;
  selectedSubject?: string;
  onAction?: (actionMetadata: PendingOrbitAction) => Promise<void>;
  enrolledClasses?: any[];
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
  const [pendingOrbitAction, setPendingOrbitAction] = useState<PendingOrbitAction | null>(null);
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
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as {
        orbitCollapsed?: boolean;
        orbitMode?: 'angry' | 'happy';
        orbitStatusText?: string;
        messages?: Message[];
        input?: string;
        pendingOrbitAction?: PendingOrbitAction | null;
      };
      if (typeof parsed.orbitCollapsed === 'boolean') setOrbitCollapsed(parsed.orbitCollapsed);
      if (parsed.orbitMode === 'angry' || parsed.orbitMode === 'happy') setOrbitMode(parsed.orbitMode);
      if (typeof parsed.orbitStatusText === 'string' && parsed.orbitStatusText.trim()) setOrbitStatusText(parsed.orbitStatusText);
      if (Array.isArray(parsed.messages)) setMessages(parsed.messages.slice(-40));
      if (typeof parsed.input === 'string') setInput(parsed.input);
      if (parsed.pendingOrbitAction) setPendingOrbitAction(parsed.pendingOrbitAction);
    } catch {
      // ignore storage parse errors
    }
  }, [storageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify({
        orbitCollapsed,
        orbitMode,
        orbitStatusText,
        messages: messages.slice(-40),
        input,
        pendingOrbitAction,
      }));
    } catch {
      // ignore storage write failures
    }
  }, [storageKey, orbitCollapsed, orbitMode, orbitStatusText, messages, input, pendingOrbitAction]);

  const handleQuickPromptPaste = (prompt: string) => {
    if (loadingChat) return;
    setInput(prompt);
  };

  const sendChatMessage = async (message: string) => {
    setLoadingChat(true);
    try {
      const fallbackSubject = selectedSubject || enrolledClasses[0]?.subject || 'all';
      const fallbackClassId = enrolledClasses.find((c) => c.subject === fallbackSubject)?.id || classId || null;
      
      const res = await axios.post(`${apiBaseUrl}/api/orbit/chat`, {
        subject: fallbackSubject,
        message,
        user_id: userId,
        class_id: fallbackClassId,
        document_id: documentId || null,
        source_file: sourceFile || '',
      });
      
      setMessages((prev) => [...prev, { role: 'assistant', content: res.data.reply }]);
      if (res.data?.orbit_mode === 'angry' || res.data?.orbit_mode === 'happy') {
        setOrbitMode(res.data.orbit_mode);
      }
      if (res.data?.orbit_status_text) {
        setOrbitStatusText(String(res.data.orbit_status_text));
      }
      if (res.data?.action_metadata?.should_auto_execute) {
        await executeOrbitAction(res.data.action_metadata);
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
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center opacity-30 text-center">
                <MessageSquare size={48} className="mb-4" />
                <p className="text-xs font-bold uppercase tracking-widest">Không gian tri thức AI</p>
                <p className="text-[10px] font-medium mt-1">Bấm Gửi ở bên dưới để bắt đầu</p>
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
                    await executeOrbitAction(pendingOrbitAction);
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
    </>
  );
}
