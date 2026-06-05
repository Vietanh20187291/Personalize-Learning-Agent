from __future__ import annotations

import time
from typing import Any, Dict

from sqlalchemy import text

from config import settings
from db.database import SessionLocal, engine
from memory.conversation_memory import get_conversation_memory


def _database_health() -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        payload: Dict[str, Any] = {
            "ok": True,
            "url_scheme": str(settings.DATABASE_URL).split(":", 1)[0],
            "latency_ms": latency_ms,
        }
        pool = getattr(engine, "pool", None)
        if pool is not None:
            try:
                payload["pool"] = {
                    "size": int(pool.size()),
                    "checked_in": int(pool.checkedin()),
                    "checked_out": int(pool.checkedout()),
                    "overflow": int(pool.overflow()),
                }
            except Exception:
                payload["pool"] = {"type": pool.__class__.__name__}
        return payload
    except Exception as exc:
        return {
            "ok": False,
            "url_scheme": str(settings.DATABASE_URL).split(":", 1)[0],
            "error": str(exc),
        }


def _vector_store_health() -> Dict[str, Any]:
    if not bool(getattr(settings, "HEALTHCHECK_INCLUDE_VECTOR_STORE", False)):
        return {"ok": True, "enabled_check": False, "status": "skipped"}
    try:
        from rag.vector_store import get_vector_store

        vector_store = get_vector_store()
        collection = getattr(vector_store, "_collection", None)
        count = collection.count() if collection is not None else None
        return {
            "ok": True,
            "enabled_check": True,
            "collection_count": count,
        }
    except Exception as exc:
        return {
            "ok": False,
            "enabled_check": True,
            "error": str(exc),
        }


def build_health_snapshot() -> Dict[str, Any]:
    database = _database_health()
    memory = get_conversation_memory().health_status()
    vector_store = _vector_store_health()
    ok = bool(database.get("ok")) and bool(memory.get("ok")) and bool(vector_store.get("ok"))
    return {
        "ok": ok,
        "instance": str(getattr(settings, "APP_INSTANCE_NAME", "backend-instance")),
        "database": database,
        "conversation_memory": memory,
        "vector_store": vector_store,
    }
