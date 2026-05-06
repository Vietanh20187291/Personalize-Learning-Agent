"""
Debug streaming API endpoints.
Provides Server-Sent Events (SSE) stream for real-time LLM debugging.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from groq import Groq
from dotenv import load_dotenv

load_dotenv(override=True)

# Import debug_stream from parent directory
try:
    from debug_stream import get_debug_stream_manager
except ImportError:
    import sys
    import os
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)
    from debug_stream import get_debug_stream_manager

router = APIRouter(prefix="/debug", tags=["debug"])

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"

TEST_CASE_LABELS = {
    "test_register_and_login_creates_login_session_and_plan_refresh": "Đăng ký, đăng nhập và làm mới kế hoạch học tập",
    "test_admin_create_user_and_list_users": "Quản trị viên tạo và xem tài khoản",
    "test_subject_crud_and_classroom_join_rejects_second_class_same_subject": "Quản lý môn học và chặn tham gia 2 lớp cùng môn",
    "test_planning_regenerate_and_chat_adjustment_reorders_steps": "Planning agent tạo lại và điều chỉnh lộ trình",
    "test_orbit_document_followup_uses_open_document_context_and_persists_history": "Orbit xử lý câu hỏi bám tài liệu đang mở",
    "test_orbit_open_document_request_returns_recommendation_and_teacher_directive": "Orbit gợi ý mở tài liệu và lưu chỉ đạo giảng viên",
    "test_nova_exam_flow_keeps_pending_request_and_routes_to_exam_tab": "Nova xử lý luồng sinh đề thi và chuyển tab xuất đề",
    "test_append_question_bank_and_manual_crud": "Ngân hàng câu hỏi thêm mới và CRUD thủ công",
    "test_assessment_generate_session_and_submit_persists_scores": "Sinh bài kiểm tra theo buổi và lưu điểm nộp bài",
    "test_assessment_agent_falls_back_when_llm_generation_returns_empty": "Assessment agent fallback khi AI không sinh được câu hỏi",
}


class DebugChatRequest(BaseModel):
    message: str
    provider: str = "ollama"
    model: str = ""
    system_prompt: str = ""


def _tail_text(value: str, limit: int = 20000) -> str:
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[-limit:]


def _resolve_python_command() -> str:
    candidates = [
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _resolve_npm_command() -> str:
    return (
        shutil.which("npm.cmd")
        or shutil.which("npm")
        or "npm"
    )


def _describe_failed_tests(failed_items: list[str]) -> list[str]:
    features: list[str] = []
    for item in failed_items:
        for test_name, label in TEST_CASE_LABELS.items():
            if test_name in item and label not in features:
                features.append(label)
    return features


def _extract_failed_items(output: str) -> list[str]:
    failed_items: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAILED ") or stripped.startswith("ERROR "):
            failed_items.append(stripped)
    return failed_items


def _build_command_summary(name: str, ok: bool, output: str, failed_items: list[str]) -> str:
    if ok and name == "backend_pytest":
        match = re.search(r"(\d+)\s+passed", output)
        if match:
            return f"Pytest thành công: {match.group(1)} test đã pass."
        return "Pytest đã chạy thành công."

    if ok and name == "frontend_build":
        return "Build frontend thành công."

    if failed_items:
        return failed_items[0]

    if "timed out" in output.lower():
        return "Tác vụ bị timeout."

    return "Tác vụ thất bại, cần xem log chi tiết."


def _run_command(name: str, command: list[str], cwd: Path, timeout_sec: int) -> dict:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
        duration_seconds = round(time.perf_counter() - started, 2)
        combined_output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
        failed_items = _extract_failed_items(combined_output)
        return {
            "name": name,
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "duration_seconds": duration_seconds,
            "command": " ".join(command),
            "stdout": _tail_text(completed.stdout),
            "stderr": _tail_text(completed.stderr),
            "failed_items": failed_items,
            "affected_features": _describe_failed_tests(failed_items),
            "summary": _build_command_summary(name, completed.returncode == 0, combined_output, failed_items),
        }
    except subprocess.TimeoutExpired as exc:
        duration_seconds = round(time.perf_counter() - started, 2)
        stdout = _tail_text((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        stderr = _tail_text((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        output = "\n".join(part for part in [stdout, stderr] if part).strip()
        return {
            "name": name,
            "ok": False,
            "exit_code": None,
            "duration_seconds": duration_seconds,
            "command": " ".join(command),
            "stdout": stdout,
            "stderr": stderr,
            "failed_items": _extract_failed_items(output),
            "affected_features": [],
            "summary": f"Tác vụ bị timeout sau {timeout_sec} giây.",
        }


def _execute_full_test_suite() -> dict:
    python_command = _resolve_python_command()
    npm_command = _resolve_npm_command()

    results = [
        _run_command(
            name="backend_pytest",
            command=[python_command, "-m", "pytest", "tests", "-q"],
            cwd=REPO_ROOT,
            timeout_sec=240,
        ),
        _run_command(
            name="frontend_build",
            command=[npm_command, "run", "build"],
            cwd=FRONTEND_DIR,
            timeout_sec=240,
        ),
    ]

    overall_ok = all(item["ok"] for item in results)
    failing = [item for item in results if not item["ok"]]
    return {
        "ok": overall_ok,
        "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": "Tất cả kiểm thử đều ổn." if overall_ok else "Có lỗi trong quá trình kiểm thử.",
        "results": results,
        "failing_steps": [item["name"] for item in failing],
    }


@router.get("/stream")
async def debug_stream():
    """
    SSE endpoint for streaming debug events.
    
    Returns:
        Server-Sent Events stream with real-time LLM request/response data
    """
    manager = get_debug_stream_manager()
    client_queue = manager.register_client()

    async def event_generator():
        try:
            while True:
                # Get any pending events (non-blocking)
                events = manager.get_pending_events(client_queue)

                if events:
                    for event in events:
                        # SSE format: data: <json>\n\n
                        event_data = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                        yield event_data
                else:
                    # Send heartbeat every 5 seconds to keep connection alive
                    yield ":\n\n"

                # Small delay to avoid busy waiting
                await asyncio.sleep(0.1)

        except GeneratorExit:
            pass
        finally:
            manager.unregister_client(client_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/test")
async def debug_test():
    """Test endpoint - emit a test event."""
    from debug_stream import emit_llm_request, emit_llm_response
    
    emit_llm_request(
        prompt="Test user message",
        system_prompt="Test system prompt"
    )
    
    import time
    time.sleep(0.5)
    
    emit_llm_response(
        response='{"test": "response"}',
        duration_ms=500.0
    )
    
    return {"status": "Test events emitted"}


@router.get("/health")
async def debug_health():
    """Health check for debug endpoint."""
    return {"status": "ok", "service": "debug-stream"}


@router.post("/test-suite")
async def debug_test_suite():
    """Run backend regression tests and a frontend production build."""
    return await asyncio.to_thread(_execute_full_test_suite)


@router.post("/chat")
async def debug_chat(req: DebugChatRequest):
    """Send a direct debug request to Ollama/OpenAI and emit SSE events."""
    from debug_stream import emit_llm_request, emit_llm_response, emit_llm_error

    provider = (req.provider or "ollama").strip().lower()
    groq_timeout = int(os.getenv("DEBUG_CHAT_GROQ_TIMEOUT_SEC", "120") or 120)
    openai_timeout = int(os.getenv("DEBUG_CHAT_OPENAI_TIMEOUT_SEC", "120") or 120)
    ollama_timeout = int(os.getenv("DEBUG_CHAT_OLLAMA_TIMEOUT_SEC", "240") or 240)
    message = (req.message or "").strip()
    if not message:
        return {"ok": False, "error": "message is required"}

    system_prompt = (req.system_prompt or "").strip() or "Bạn là trợ lý test LLM. Trả lời ngắn gọn, chính xác."
    started = time.perf_counter()

    if provider == "groq":
        model = (req.model or os.getenv("GROQ_DEBUG_MODEL", "llama-3.1-8b-instant")).strip()
        api_key = (os.getenv("GROQ_KEY_ASSESSMENT") or os.getenv("GROQ_KEY_DEBUG") or os.getenv("GROQ_KEY_CONTENT") or "").strip()
        if api_key and api_key.strip().upper().startswith("PASTE_"):
            api_key = ((os.getenv("GROQ_KEY_ASSESSMENT") or os.getenv("GROQ_KEY_CONTENT") or "")).strip()
        if not api_key:
            return {"ok": False, "error": "GROQ_KEY_DEBUG / GROQ_KEY_ASSESSMENT / GROQ_KEY_CONTENT is missing"}

        emit_llm_request(prompt=f"[groq:{model}] {message}", system_prompt=system_prompt)
        try:
            client = Groq(api_key=api_key)
            res = client.chat.completions.create(
                model=model,
                temperature=0.2,
                max_tokens=300,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
            )
            content = str(((res.choices or [None])[0].message.content if (res.choices and res.choices[0] and res.choices[0].message) else "") or "").strip()
            duration_ms = (time.perf_counter() - started) * 1000.0
            emit_llm_response(response=f"[groq:{model}] {content}", duration_ms=duration_ms)
            return {"ok": True, "provider": "groq", "model": model, "response": content, "duration_ms": round(duration_ms, 2), "path": "groq-sdk"}
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            emit_llm_error(error_message=f"[groq:{model}] {exc}", duration_ms=duration_ms)
            return {"ok": False, "provider": "groq", "model": model, "error": str(exc), "duration_ms": round(duration_ms, 2), "path": "groq-sdk"}

    if provider == "openai":
        model = (req.model or "gpt-4o-mini").strip()
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ASSESSMENT_OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", os.getenv("ASSESSMENT_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        if not api_key:
            return {"ok": False, "error": "OPENAI_API_KEY is missing"}

        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 300,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
        }
        emit_llm_request(prompt=f"[openai:{model}] {message}", system_prompt=system_prompt)
        try:
            request = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=openai_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = str(((data.get("choices") or [{}])[0].get("message", {}) or {}).get("content", "")).strip()
            duration_ms = (time.perf_counter() - started) * 1000.0
            emit_llm_response(response=f"[openai:{model}] {content}", duration_ms=duration_ms)
            return {"ok": True, "provider": "openai", "model": model, "response": content, "duration_ms": round(duration_ms, 2)}
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            emit_llm_error(error_message=f"[openai:{model}] {exc}", duration_ms=duration_ms)
            return {"ok": False, "provider": "openai", "model": model, "error": str(exc), "duration_ms": round(duration_ms, 2)}

    model = (req.model or os.getenv("ASSESSMENT_OLLAMA_MODEL", "qwen2.5:14b")).strip()
    host = os.getenv("ASSESSMENT_OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        "options": {
            "temperature": 0.2,
            "num_predict": 300,
        },
    }
    emit_llm_request(prompt=f"[ollama:{model}] {message}", system_prompt=system_prompt)
    try:
        request = urllib.request.Request(
            f"{host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=ollama_timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = str((data.get("message") or {}).get("content", "")).strip()
        duration_ms = (time.perf_counter() - started) * 1000.0
        emit_llm_response(response=f"[ollama:{model}] {content}", duration_ms=duration_ms)
        return {"ok": True, "provider": "ollama", "model": model, "response": content, "duration_ms": round(duration_ms, 2)}
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        emit_llm_error(error_message=f"[ollama:{model}] {exc}", duration_ms=duration_ms)
        return {"ok": False, "provider": "ollama", "model": model, "error": str(exc), "duration_ms": round(duration_ms, 2)}
