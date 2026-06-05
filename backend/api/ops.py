from __future__ import annotations

from fastapi import APIRouter, HTTPException

from config import settings
from services.system_health import build_health_snapshot


router = APIRouter()


@router.get("/health")
def detailed_health_check():
    snapshot = build_health_snapshot()
    snapshot.update(
        {
            "message": "Backend dang hoat dong",
            "rag_embeddings_enabled": getattr(settings, "RAG_EMBEDDINGS_ENABLED", True),
        }
    )
    return snapshot


@router.get("/readiness")
def readiness_check():
    snapshot = build_health_snapshot()
    if not snapshot.get("ok"):
        raise HTTPException(status_code=503, detail="Readiness check failed")
    return snapshot
