"use client";

import { useMemo, useState, useRef, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { MessageCircle, Minimize2, Sparkles, Send, Loader, AlertCircle } from "lucide-react";

const NOVA_AGENT_IMAGES = [
  "https://cdn-icons-png.flaticon.com/512/4712/4712109.png",
  "https://api.dicebear.com/9.x/bottts-neutral/png?seed=Nova&backgroundColor=b6e3f4,c0aede,d1d4f9",
];

interface Message {
  role: "user" | "agent";
  content: string;
  timestamp: Date;
}

interface ActionMetadata {
  action_type: string;
  target: string;
  tab_name?: string;
  params?: Record<string, any>;
  message?: string;
  should_auto_execute?: boolean;
}

export default function NovaTeacherAgent() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const pathname = usePathname();
  const router = useRouter();
  const isTeacherZone = useMemo(() => pathname?.startsWith("/teacher"), [pathname]);

  const [open, setOpen] = useState(true);
  const [imageIdx, setImageIdx] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestedQuestions = [
    "Tóm tắt tình hình lớp IT1",
    "Tình hình học tập sinh viên ABX thế nào",
    "Môn học Giải tích có những lớp nào",
    "Xuất đề thi trắc nghiệm cơ sở hệ điều hành 20 câu 2 mã đề",
  ];

  // Extract class_id and teacher_id from localStorage or URL
  const [teacherId, setTeacherId] = useState<number | null>(null);
  const [classId, setClassId] = useState<number | null>(null);

  useEffect(() => {
    // Get teacher_id from localStorage
    const userId = localStorage.getItem("userId");
    setTeacherId(userId ? parseInt(userId) : null);

    // Try to get class_id from multiple sources:
    // 1. URL path (e.g., /teacher/classrooms/1)
    let cid: number | null = null;
    const pathParts = pathname?.split("/").filter(Boolean) || [];
    
    // Check if classId is in URL (typically at last position if numeric)
    if (pathParts.length > 2) {
      const potentialId = pathParts[pathParts.length - 1];
      if (!isNaN(Number(potentialId))) {
        cid = parseInt(potentialId);
      }
    }
    
    // 2. Fallback to localStorage if not in URL
    if (!cid) {
      const storedClassId = localStorage.getItem("currentClassId");
      if (storedClassId) {
        cid = parseInt(storedClassId);
      }
    }
    
    setClassId(cid);

    // 3. If still no classId and we have userId, fetch first class from API
    if (!cid && userId) {
      fetch(`${apiBaseUrl}/api/classroom/teacher/${userId}`)
        .then((r) => r.json())
        .then((classes) => {
          if (classes && classes.length > 0) {
            const firstClassId = classes[0].id;
            setClassId(firstClassId);
            localStorage.setItem("currentClassId", firstClassId.toString());
          }
        })
        .catch((err) => console.error("Failed to fetch classes:", err));
    }
  }, [apiBaseUrl, pathname, teacherId]);

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Initialize and persist sessionId
  useEffect(() => {
    let sid = localStorage.getItem("nova_session_id");
    if (!sid) {
      sid = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem("nova_session_id", sid);
    }
    setSessionId(sid);
  }, []);

  // Load messages from localStorage on mount
  useEffect(() => {
    if (sessionId) {
      const key = `nova_messages_${sessionId}`;
      const stored = localStorage.getItem(key);
      if (stored) {
        try {
          const parsed = JSON.parse(stored) as Message[];
          // Convert timestamp strings back to Date objects
          const messagesWithDates = parsed.map(msg => ({
            ...msg,
            timestamp: new Date(msg.timestamp)
          }));
          setMessages(messagesWithDates);
        } catch (e) {
          console.error("Failed to parse stored messages:", e);
        }
      }
    }
  }, [sessionId]);

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    if (sessionId && messages.length > 0) {
      const key = `nova_messages_${sessionId}`;
      localStorage.setItem(key, JSON.stringify(messages));
    }
  }, [messages, sessionId]);

  // Handle navigation based on action_metadata
  const handleNavigation = (action: ActionMetadata) => {
    if (action.action_type !== "open_tab") return;

    const actionClassId = Number(action.params?.classroom_id);
    const resolvedClassId = Number.isFinite(actionClassId) && actionClassId > 0 ? actionClassId : classId;

    switch (action.target) {
      case "learning_results":
        if (action.tab_name === "class_analytics") {
          if (resolvedClassId) {
            localStorage.setItem("currentClassId", resolvedClassId.toString());
          }
          router.push("/teacher/members");
        } else if (action.tab_name === "student_detailed") {
          if (resolvedClassId) {
            localStorage.setItem("currentClassId", resolvedClassId.toString());
          }
          router.push("/teacher/members");
        }
        break;

      case "admin":
        if (action.tab_name === "subjects") {
          router.push("/admin/subjects");
        }
        break;

      case "teacher":
        if (action.tab_name === "subjects") {
          const subjectName = String(action.params?.subject_name || "").trim();
          if (subjectName) {
            localStorage.setItem("novaTargetSubject", subjectName);
            router.push(`/teacher/subjects?subject=${encodeURIComponent(subjectName)}`);
          } else {
            router.push("/teacher/subjects");
          }
        } else
        if (action.tab_name === "exam") {
          router.push(`/teacher/exam`);
        } else if (action.tab_name === "documents") {
          router.push(`/teacher/documents`);
        }
        break;

      default:
        break;
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim()) {
      setError("Vui lòng nhập tin nhắn");
      return;
    }

    if (!teacherId) {
      setError("Vui lòng đăng nhập lại");
      return;
    }

    if (!classId) {
      setError("Vui lòng chọn một lớp học trước. Truy cập tab 'Quản lý thành viên' để chọn lớp.");
      return;
    }

    const userMessage = inputValue.trim();
    setInputValue("");
    setError(null);

    // Add user message to conversation
    const newUserMessage: Message = {
      role: "user",
      content: userMessage,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, newUserMessage]);
    setLoading(true);

    try {
      // Call the Nova interactive API
      const response = await fetch(`${apiBaseUrl}/api/teacher/nova-interactive`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          teacher_id: teacherId,
          class_id: classId,
          message: userMessage,
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const error = await response.json();
          throw new Error(error.detail || "Lỗi từ Nova Agent");
        }
        const text = await response.text();
        throw new Error(`Lỗi từ Nova Agent (${response.status}): ${text.slice(0, 120)}`);
      }

      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        const text = await response.text();
        throw new Error(`Nova trả về định dạng không hợp lệ: ${text.slice(0, 120)}`);
      }

      const data = await response.json();

      // Add agent message to conversation
      const agentMessage: Message = {
        role: "agent",
        content: data.reply,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, agentMessage]);

      // Handle navigation if needed
      if (data.action_metadata) {
        handleNavigation(data.action_metadata);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Lỗi kết nối";
      setError(errorMsg);
      console.error("Nova error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectSuggestedQuestion = (question: string) => {
    setInputValue(question);
    setError(null);
    inputRef.current?.focus();
  };

  if (!isTeacherZone) return null;

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="nova-launcher fixed bottom-5 right-5 z-[80]"
        aria-label="Mở Nova"
        title="Mở Nova"
      >
        <span className="nova-launcher-glow" />
        <img
          src={NOVA_AGENT_IMAGES[imageIdx]}
          alt="Nova"
          className="h-11 w-11 rounded-full object-cover border border-white/70"
          onError={() => setImageIdx((i) => (i + 1) % NOVA_AGENT_IMAGES.length)}
        />
        <span className="ml-2 font-extrabold tracking-wide">Nova</span>
      </button>
    );
  }

  return (
    <section
      className="nova-panel fixed bottom-5 right-5 z-[80] w-[420px] max-w-[92vw] flex flex-col max-h-[80vh]"
      aria-label="Nova Agent"
    >
      {/* Header */}
      <header className="flex items-center justify-between border-b border-white/25 px-4 py-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="relative">
            <span className="nova-avatar-ring" />
            <img
              src={NOVA_AGENT_IMAGES[imageIdx]}
              alt="Nova AI"
              className="relative h-12 w-12 rounded-full object-cover border border-white/70"
              onError={() => setImageIdx((i) => (i + 1) % NOVA_AGENT_IMAGES.length)}
            />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-100/90">Teacher Copilot</p>
            <h3 className="text-lg font-black leading-none text-white">Nova</h3>
          </div>
        </div>
        <button
          className="rounded-lg border border-white/20 bg-white/10 p-2 text-white hover:bg-white/20"
          onClick={() => setOpen(false)}
          aria-label="Thu gọn Nova"
          title="Thu gọn"
        >
          <Minimize2 size={16} />
        </button>
      </header>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 min-h-[300px]">
        {messages.length === 0 && (
          <div className="rounded-2xl border border-cyan-200/30 bg-white/10 p-3 backdrop-blur-sm mb-4">
            <p className="text-sm leading-relaxed text-cyan-50">
              <Sparkles size={14} className="inline mr-2 text-cyan-400" />
              Chào bạn! Tôi là Nova, trợ lý thông minh của giảng viên. Bạn có thể:
            </p>
            <ul className="text-xs text-cyan-100 mt-2 space-y-1 ml-6">
              <li>• Yêu cầu tóm tắt tình hình lớp học</li>
              <li>• Hỏi về tiến độ học tập của sinh viên cụ thể</li>
              <li>• Quản lý môn học, tài liệu</li>
              <li>• Tạo hoặc xuất đề thi</li>
            </ul>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-400/50 bg-red-500/20 p-3 flex gap-2">
            <AlertCircle size={16} className="text-red-300 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-100">{error}</p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-xs px-3 py-2 rounded-lg text-sm ${
                msg.role === "user"
                  ? "bg-cyan-500/70 text-white rounded-br-none"
                  : "bg-white/20 text-cyan-50 rounded-bl-none border border-white/30"
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-white/20 text-cyan-50 border border-white/30 rounded-lg rounded-bl-none px-3 py-2 flex gap-2">
              <Loader size={14} className="animate-spin" />
              <span className="text-sm">Nova đang suy nghĩ...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-white/25 px-4 py-3 flex-shrink-0">
        <div className="mb-2 flex flex-wrap gap-2">
          {suggestedQuestions.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => handleSelectSuggestedQuestion(question)}
              disabled={loading}
              className="rounded-full border border-cyan-200/40 bg-white/10 px-3 py-1 text-xs text-cyan-100 hover:bg-white/20 disabled:opacity-50"
              title={question}
            >
              {question}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
            placeholder="Nhập yêu cầu..."
            className="flex-1 rounded-lg border border-white/30 bg-white/10 px-3 py-2 text-sm text-white placeholder-white/50 focus:outline-none focus:border-cyan-400"
            disabled={loading}
          />
          <button
            onClick={handleSendMessage}
            disabled={loading || !inputValue.trim()}
            className="rounded-lg bg-cyan-500/70 hover:bg-cyan-500/90 text-white p-2 transition-colors disabled:opacity-50"
            title="Gửi"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </section>
  );
}
