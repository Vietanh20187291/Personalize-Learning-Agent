from datetime import datetime
from typing import Optional


def _now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _safe_emit_request(prompt: str, system_prompt: str) -> None:
    try:
        from debug_stream import emit_llm_request
        emit_llm_request(prompt=prompt, system_prompt=system_prompt)
    except Exception:
        pass


def _safe_emit_response(response: str, duration_ms: float) -> None:
    try:
        from debug_stream import emit_llm_response
        emit_llm_response(response=response, duration_ms=duration_ms)
    except Exception:
        pass


def _safe_emit_error(error_message: str, duration_ms: float) -> None:
    try:
        from debug_stream import emit_llm_error
        emit_llm_error(error_message=error_message, duration_ms=duration_ms)
    except Exception:
        pass


def log_llm_request(provider: str, model: str, prompt: str, system_prompt: Optional[str] = None) -> None:
    timestamp = _now_hms()
    print(f"[LLM][{timestamp}] SEND provider={provider} model={model}")
    if system_prompt:
        print(f"[LLM][{timestamp}] SYSTEM: {system_prompt}")
    print(f"[LLM][{timestamp}] PROMPT: {prompt}")
    _safe_emit_request(prompt=f"[{provider}:{model}] {prompt}", system_prompt=system_prompt or "")


def log_llm_response(provider: str, model: str, response: str, duration_ms: float) -> None:
    timestamp = _now_hms()
    safe_response = response if str(response or "").strip() else "<EMPTY_RESPONSE>"
    print(f"[LLM][{timestamp}] RECV provider={provider} model={model} duration_ms={round(duration_ms, 2)}")
    print(f"[LLM][{timestamp}] RESPONSE: {safe_response}")
    _safe_emit_response(response=f"[{provider}:{model}] {safe_response}", duration_ms=duration_ms)


def log_llm_error(provider: str, model: str, error_message: str, duration_ms: float) -> None:
    timestamp = _now_hms()
    print(f"[LLM][{timestamp}] ERROR provider={provider} model={model} duration_ms={round(duration_ms, 2)}")
    print(f"[LLM][{timestamp}] ERROR_DETAIL: {error_message}")
    _safe_emit_error(error_message=f"[{provider}:{model}] {error_message}", duration_ms=duration_ms)
