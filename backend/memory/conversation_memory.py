"""
Conversation Memory System - nhớ ngữ cảnh giữa các câu hỏi của giảng viên
Giúp agent hiểu được câu hỏi tiếp theo liên quan đến câu hỏi trước
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

class ConversationMemory:
    """Lưu trữ và quản lý ngữ cảnh hội thoại"""
    
    def __init__(self, max_history: int = 20, ttl_hours: int = 8):
        # {session_id: {teacher_id: {class_id: memory_data}}}
        self.sessions: Dict[str, Dict[int, Dict[int, Dict]]] = {}
        self.max_history = max_history
        self.ttl_hours = ttl_hours
    
    def get_session_key(self, teacher_id: int, class_id: int) -> str:
        """Tạo khóa session duy nhất"""
        return f"teacher_{teacher_id}_class_{class_id}"
    
    def get_or_create_memory(self, teacher_id: int, class_id: int) -> Dict[str, Any]:
        """Lấy hoặc tạo bộ nhớ cho một phiên hội thoại"""
        session_key = self.get_session_key(teacher_id, class_id)
        
        if session_key not in self.sessions:
            self.sessions[session_key] = {
                "created_at": datetime.utcnow().isoformat(),
                "last_accessed": datetime.utcnow().isoformat(),
                "conversation_history": [],
                "context": {
                    "last_subject": None,
                    "last_subject_id": None,
                    "last_subject_name": None,
                    "last_class": None,
                    "last_class_id": class_id,
                    "last_class_name": None,
                    "last_student_asked": None,  # {id, name, student_id}
                    "last_student_id": None,
                    "last_student_name": None,
                    "last_action_type": None,
                    "last_intent": None,
                    "last_entities": {},
                    "pending_request": None,
                    "pending_fields": [],
                    "pending_exam_info": {  # Để hỏi lại nếu user chưa cung cấp đủ thông tin
                        "subject": None,
                        "type": None,
                        "exam_type": None,  # "multiple_choice", "essay", "mixed"
                        "num_questions": None,
                        "num_versions": None,
                        "difficulty": None,
                    },
                },
            }
        
        self.sessions[session_key]["last_accessed"] = datetime.utcnow().isoformat()
        return self.sessions[session_key]
    
    def add_message(self, teacher_id: int, class_id: int, role: str, content: str, metadata: Dict = None):
        """Thêm một tin nhắn vào lịch sử hội thoại"""
        memory = self.get_or_create_memory(teacher_id, class_id)
        session_key = self.get_session_key(teacher_id, class_id)
        
        message = {
            "timestamp": datetime.utcnow().isoformat(),
            "role": role,  # "user" hoặc "agent"
            "content": content,
            "metadata": metadata or {},
        }
        
        memory["conversation_history"].append(message)
        
        # Giữ lịch sử trong phạm vi max_history
        if len(memory["conversation_history"]) > self.max_history:
            memory["conversation_history"] = memory["conversation_history"][-self.max_history:]
        
        self.sessions[session_key] = memory
    
    def update_context(self, teacher_id: int, class_id: int, context_updates: Dict):
        """Cập nhật ngữ cảnh (môn học hiện tại, sinh viên được hỏi, v.v.)"""
        memory = self.get_or_create_memory(teacher_id, class_id)
        session_key = self.get_session_key(teacher_id, class_id)
        
        memory["context"].update(context_updates)
        self.sessions[session_key] = memory

    def set_pending_request(self, teacher_id: int, class_id: int, pending_request: Dict):
        """Lưu yêu cầu đang thiếu dữ liệu để tiếp tục ở lượt sau"""
        memory = self.get_or_create_memory(teacher_id, class_id)
        session_key = self.get_session_key(teacher_id, class_id)
        memory["context"]["pending_request"] = pending_request
        memory["context"]["pending_fields"] = pending_request.get("missing_fields", [])
        self.sessions[session_key] = memory

    def clear_pending_request(self, teacher_id: int, class_id: int):
        """Xóa yêu cầu đang chờ bổ sung thông tin"""
        memory = self.get_or_create_memory(teacher_id, class_id)
        session_key = self.get_session_key(teacher_id, class_id)
        memory["context"]["pending_request"] = None
        memory["context"]["pending_fields"] = []
        self.sessions[session_key] = memory

    def get_pending_request(self, teacher_id: int, class_id: int) -> Optional[Dict]:
        """Lấy yêu cầu đang chờ bổ sung thông tin"""
        memory = self.get_or_create_memory(teacher_id, class_id)
        return memory.get("context", {}).get("pending_request")
    
    def get_context(self, teacher_id: int, class_id: int) -> Dict:
        """Lấy ngữ cảnh hiện tại"""
        memory = self.get_or_create_memory(teacher_id, class_id)
        return memory.get("context", {})
    
    def get_history_summary(self, teacher_id: int, class_id: int, limit: int = 5) -> List[str]:
        """Lấy tóm tắt các tin nhắn gần nhất (để đưa vào prompt)"""
        memory = self.get_or_create_memory(teacher_id, class_id)
        history = memory.get("conversation_history", [])[-limit:]
        
        summary = []
        for msg in history:
            role = "Giảng viên" if msg["role"] == "user" else "Nova"
            content = msg["content"][:100]
            summary.append(f"{role}: {content}")
        
        return summary
    
    def clear_session(self, teacher_id: int, class_id: int):
        """Xóa phiên hội thoại"""
        session_key = self.get_session_key(teacher_id, class_id)
        if session_key in self.sessions:
            del self.sessions[session_key]
    
    def cleanup_expired_sessions(self):
        """Xóa các phiên hết hạn"""
        expired_keys = []
        cutoff_time = datetime.utcnow() - timedelta(hours=self.ttl_hours)
        
        for session_key, session_data in self.sessions.items():
            last_accessed = datetime.fromisoformat(session_data.get("last_accessed", datetime.utcnow().isoformat()))
            if last_accessed < cutoff_time:
                expired_keys.append(session_key)
        
        for key in expired_keys:
            del self.sessions[key]

# Global instance
_memory = ConversationMemory()

def get_conversation_memory() -> ConversationMemory:
    """Lấy instance toàn cục của Conversation Memory"""
    return _memory
