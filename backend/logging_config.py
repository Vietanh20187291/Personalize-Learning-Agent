import logging
import time
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from config import settings


_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_current_request_id() -> str:
    return _request_id_ctx.get("-")


def error_json_response(status_code: int, detail: str, retryable: bool = False) -> JSONResponse:
    payload = {
        "detail": str(detail or "Đã xảy ra lỗi khi xử lý yêu cầu."),
        "request_id": get_current_request_id(),
        "retryable": bool(retryable),
    }
    return JSONResponse(status_code=status_code, content=payload)


class _RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get("-")
        return True


def setup_logging() -> Path:
    logs_dir = Path(__file__).resolve().parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    if getattr(root_logger, "_ai_learning_logging_configured", False):
        return logs_dir

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
    )
    context_filter = _RequestContextFilter()

    app_handler = RotatingFileHandler(
        logs_dir / "app.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    app_handler.addFilter(context_filter)

    error_handler = RotatingFileHandler(
        logs_dir / "error.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler.addFilter(context_filter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)
    root_logger._ai_learning_logging_configured = True  # type: ignore[attr-defined]

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True

    logging.getLogger("app").info("Logging initialized at %s", logs_dir)
    return logs_dir


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = uuid.uuid4().hex[:8]
        token = _request_id_ctx.set(request_id)
        logger = logging.getLogger("app.request")
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "Unhandled request error method=%s path=%s query=%s duration_ms=%s",
                request.method,
                request.url.path,
                request.url.query,
                duration_ms,
            )
            _request_id_ctx.reset(token)
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        slow_threshold_ms = max(
            1000,
            int(float(getattr(settings, "REQUEST_SLOW_LOG_SECONDS", 30)) * 1000),
        )
        if duration_ms >= slow_threshold_ms:
            logger.warning(
                "slow_request method=%s path=%s status=%s duration_ms=%s threshold_ms=%s",
                request.method,
                request.url.path,
                getattr(response, "status_code", "unknown"),
                duration_ms,
                slow_threshold_ms,
            )
        logger.info(
            "method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            getattr(response, "status_code", "unknown"),
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        _request_id_ctx.reset(token)
        return response
