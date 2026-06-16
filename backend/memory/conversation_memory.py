"""
Conversation memory cho teacher agent.

Production note:
- Khi REDIS_URL duoc cau hinh, memory se duoc luu tren Redis de nhieu backend
  instance co the chia se state va scale ngang sau load balancer.
- Neu Redis khong san sang, he thong tu dong fallback ve in-memory de tranh
  lam dung toan bo luong Nova trong moi truong dev/test.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config import settings


class ConversationMemory:
    """Luu tru va quan ly ngu canh hoi thoai cua giao vien."""

    def __init__(self, max_history: int = 20, ttl_hours: Optional[int] = None):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.max_history = max_history
        self.ttl_hours = ttl_hours or int(getattr(settings, "CONVERSATION_MEMORY_TTL_HOURS", 8) or 8)
        self.ttl_seconds = max(300, int(self.ttl_hours * 3600))
        self._lock = threading.RLock()
        self._redis_client = None
        self._backend = "local"
        self._init_redis_backend()

    def _init_redis_backend(self) -> None:
        redis_url = str(getattr(settings, "REDIS_URL", "") or "").strip()
        if not redis_url:
            return
        try:
            from redis import Redis  # type: ignore

            client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
            client.ping()
            self._redis_client = client
            self._backend = "redis"
        except Exception:
            self._redis_client = None
            self._backend = "local"

    def backend_name(self) -> str:
        return self._backend

    def is_distributed(self) -> bool:
        return self._backend == "redis"

    def _default_memory(self, class_id: int) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        return {
            "created_at": now,
            "last_accessed": now,
            "conversation_history": [],
            "context": {
                "last_subject": None,
                "last_subject_id": None,
                "last_subject_name": None,
                "last_class": None,
                "last_class_id": class_id,
                "last_class_name": None,
                "last_student_asked": None,
                "last_student_id": None,
                "last_student_name": None,
                "last_action_type": None,
                "last_intent": None,
                "last_entities": {},
                "pending_request": None,
                "pending_fields": [],
                "pending_exam_info": {
                    "subject": None,
                    "type": None,
                    "exam_type": None,
                    "num_questions": None,
                    "num_versions": None,
                    "difficulty": None,
                },
            },
        }

    def get_session_key(self, teacher_id: int, class_id: int) -> str:
        return f"teacher_{teacher_id}_class_{class_id}"

    def _redis_key(self, session_key: str) -> str:
        return f"conversation_memory:{session_key}"

    def _touch_memory(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        memory["last_accessed"] = datetime.utcnow().isoformat()
        return memory

    def _load_from_local(self, session_key: str, class_id: int) -> Dict[str, Any]:
        with self._lock:
            memory = self.sessions.get(session_key)
            if memory is None:
                memory = self._default_memory(class_id)
                self.sessions[session_key] = memory
            return self._touch_memory(memory)

    def _save_to_local(self, session_key: str, memory: Dict[str, Any]) -> None:
        with self._lock:
            self.sessions[session_key] = self._touch_memory(memory)

    def _load_from_redis(self, session_key: str, class_id: int) -> Dict[str, Any]:
        if self._redis_client is None:
            return self._load_from_local(session_key, class_id)
        try:
            payload = self._redis_client.get(self._redis_key(session_key))
            if payload:
                try:
                    memory = json.loads(payload)
                except Exception:
                    memory = self._default_memory(class_id)
            else:
                memory = self._default_memory(class_id)
            memory = self._touch_memory(memory)
            self._save_to_redis(session_key, memory)
            return memory
        except Exception:
            return self._load_from_local(session_key, class_id)

    def _save_to_redis(self, session_key: str, memory: Dict[str, Any]) -> None:
        if self._redis_client is None:
            self._save_to_local(session_key, memory)
            return
        try:
            self._redis_client.setex(self._redis_key(session_key), self.ttl_seconds, json.dumps(self._touch_memory(memory), ensure_ascii=False))
        except Exception:
            self._save_to_local(session_key, memory)

    def get_or_create_memory(self, teacher_id: int, class_id: int) -> Dict[str, Any]:
        session_key = self.get_session_key(teacher_id, class_id)
        if self.is_distributed():
            return self._load_from_redis(session_key, class_id)
        return self._load_from_local(session_key, class_id)

    def add_message(self, teacher_id: int, class_id: int, role: str, content: str, metadata: Dict = None):
        session_key = self.get_session_key(teacher_id, class_id)
        memory = self.get_or_create_memory(teacher_id, class_id)
        message = {
            "timestamp": datetime.utcnow().isoformat(),
            "role": role,
            "content": content,
            "metadata": metadata or {},
        }
        history = list(memory.get("conversation_history", []))
        history.append(message)
        if len(history) > self.max_history:
            history = history[-self.max_history :]
        memory["conversation_history"] = history
        if self.is_distributed():
            self._save_to_redis(session_key, memory)
        else:
            self._save_to_local(session_key, memory)

    def update_context(self, teacher_id: int, class_id: int, context_updates: Dict):
        session_key = self.get_session_key(teacher_id, class_id)
        memory = self.get_or_create_memory(teacher_id, class_id)
        context = dict(memory.get("context", {}))
        context.update(context_updates)
        memory["context"] = context
        if self.is_distributed():
            self._save_to_redis(session_key, memory)
        else:
            self._save_to_local(session_key, memory)

    def set_pending_request(self, teacher_id: int, class_id: int, pending_request: Dict):
        memory = self.get_or_create_memory(teacher_id, class_id)
        context = dict(memory.get("context", {}))
        context["pending_request"] = pending_request
        context["pending_fields"] = pending_request.get("missing_fields", [])
        self.update_context(teacher_id, class_id, context)

    def clear_pending_request(self, teacher_id: int, class_id: int):
        context = dict(self.get_context(teacher_id, class_id))
        context["pending_request"] = None
        context["pending_fields"] = []
        self.update_context(teacher_id, class_id, context)

    def get_pending_request(self, teacher_id: int, class_id: int) -> Optional[Dict]:
        memory = self.get_or_create_memory(teacher_id, class_id)
        return memory.get("context", {}).get("pending_request")

    def get_context(self, teacher_id: int, class_id: int) -> Dict:
        memory = self.get_or_create_memory(teacher_id, class_id)
        return dict(memory.get("context", {}))

    def get_history_summary(self, teacher_id: int, class_id: int, limit: int = 5) -> List[str]:
        memory = self.get_or_create_memory(teacher_id, class_id)
        history = list(memory.get("conversation_history", []))[-limit:]
        summary = []
        for msg in history:
            role = "Giảng viên" if msg["role"] == "user" else "Nova"
            content = str(msg.get("content", ""))[:100]
            summary.append(f"{role}: {content}")
        return summary

    def clear_session(self, teacher_id: int, class_id: int):
        session_key = self.get_session_key(teacher_id, class_id)
        if self.is_distributed() and self._redis_client is not None:
            self._redis_client.delete(self._redis_key(session_key))
            return
        with self._lock:
            self.sessions.pop(session_key, None)

    def cleanup_expired_sessions(self):
        if self.is_distributed():
            return
        expired_keys = []
        cutoff_time = datetime.utcnow() - timedelta(hours=self.ttl_hours)
        with self._lock:
            for session_key, session_data in self.sessions.items():
                last_accessed_raw = session_data.get("last_accessed", datetime.utcnow().isoformat())
                last_accessed = datetime.fromisoformat(last_accessed_raw)
                if last_accessed < cutoff_time:
                    expired_keys.append(session_key)
            for key in expired_keys:
                self.sessions.pop(key, None)

    def health_status(self) -> Dict[str, Any]:
        if self.is_distributed() and self._redis_client is not None:
            try:
                pong = self._redis_client.ping()
                return {
                    "backend": "redis",
                    "ok": bool(pong),
                    "distributed": True,
                    "ttl_seconds": self.ttl_seconds,
                }
            except Exception as exc:
                return {
                    "backend": "redis",
                    "ok": False,
                    "distributed": True,
                    "ttl_seconds": self.ttl_seconds,
                    "error": str(exc),
                }
        with self._lock:
            return {
                "backend": "local",
                "ok": True,
                "distributed": False,
                "ttl_seconds": self.ttl_seconds,
                "active_sessions": len(self.sessions),
            }


_memory = ConversationMemory()


def get_conversation_memory() -> ConversationMemory:
    return _memory
