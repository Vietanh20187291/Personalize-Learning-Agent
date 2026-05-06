"""
Real-time debug streaming for LLM requests/responses.
Uses a thread-safe queue to broadcast events to all connected SSE clients.
"""

import json
import threading
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional


class DebugStreamManager:
    """
    Thread-safe manager for debug events.
    Maintains a queue of recent events and a list of connected clients.
    """

    def __init__(self, max_queue_size: int = 100):
        self.event_queue: deque = deque(maxlen=max_queue_size)
        self.clients: List[deque] = []
        self.lock = threading.RLock()

    def register_client(self) -> deque:
        """
        Register a new SSE client.
        Returns a deque that will receive events.
        """
        with self.lock:
            client_queue = deque(maxlen=100)
            self.clients.append(client_queue)
            # Send all recent events to new client
            for event in self.event_queue:
                client_queue.append(event)
            return client_queue

    def unregister_client(self, client_queue: deque) -> None:
        """Unregister a client."""
        with self.lock:
            if client_queue in self.clients:
                self.clients.remove(client_queue)

    def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Emit a debug event to all connected clients.
        """
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            **data,
        }

        with self.lock:
            self.event_queue.append(event)
            # Broadcast to all connected clients
            for client_queue in self.clients:
                client_queue.append(event)

    def get_pending_events(self, client_queue: deque) -> List[Dict[str, Any]]:
        """
        Get all pending events for a client.
        This is non-blocking and returns immediately.
        """
        events = []
        while len(client_queue) > 0:
            try:
                events.append(client_queue.popleft())
            except IndexError:
                break
        return events


# Global debug stream manager instance
_debug_stream_manager: Optional[DebugStreamManager] = None


def get_debug_stream_manager() -> DebugStreamManager:
    """Get or create the global debug stream manager."""
    global _debug_stream_manager
    if _debug_stream_manager is None:
        _debug_stream_manager = DebugStreamManager()
    return _debug_stream_manager


def emit_llm_request(prompt: str, system_prompt: Optional[str] = None) -> None:
    """
    Emit an LLM request event.
    
    Args:
        prompt: The user prompt sent to LLM
        system_prompt: Optional system prompt
    """
    manager = get_debug_stream_manager()
    manager.emit_event(
        "llm_request",
        {
            "prompt": prompt,
            "system_prompt": system_prompt or "",
        },
    )


def emit_llm_response(response: str, duration_ms: float) -> None:
    """
    Emit an LLM response event.
    
    Args:
        response: The response from LLM
        duration_ms: Duration of the LLM call in milliseconds
    """
    manager = get_debug_stream_manager()
    manager.emit_event(
        "llm_response",
        {
            "response": response,
            "duration_ms": round(duration_ms, 2),
        },
    )


def emit_llm_error(error_message: str, duration_ms: float) -> None:
    """
    Emit an LLM error event.
    
    Args:
        error_message: Error message
        duration_ms: Duration until error occurred
    """
    manager = get_debug_stream_manager()
    manager.emit_event(
        "llm_error",
        {
            "error": error_message,
            "duration_ms": round(duration_ms, 2),
        },
    )
