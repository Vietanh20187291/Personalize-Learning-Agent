import logging
import threading
from typing import Any, Optional

from config import settings


logger = logging.getLogger("app.rag.embedder")

_embeddings: Optional[Any] = None
_embeddings_lock = threading.Lock()
_disabled_warning_logged = False


def get_embeddings() -> Optional[Any]:
    """Lazy-init the embedding model once to avoid blocking bursts."""
    global _embeddings, _disabled_warning_logged
    if _embeddings is not None:
        return _embeddings

    if not getattr(settings, "RAG_EMBEDDINGS_ENABLED", True):
        if not _disabled_warning_logged:
            logger.warning(
                "RAG embeddings are disabled on this runtime. Falling back to non-vector behavior to keep the backend stable."
            )
            _disabled_warning_logged = True
        return None

    with _embeddings_lock:
        if _embeddings is not None:
            return _embeddings

        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings

            # Multilingual model: supports 50+ languages including Vietnamese.
            # Better semantic retrieval for Vietnamese learning materials than
            # the English-only all-MiniLM-L6-v2. NOTE: changing the embedding
            # model changes vector dimensions — the ChromaDB collection must be
            # re-indexed (see docs / re-upload documents) after this change.
            _embeddings = HuggingFaceEmbeddings(
                model_name="paraphrase-multilingual-MiniLM-L12-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": False},
            )
            logger.info("Embedding model initialized successfully (paraphrase-multilingual-MiniLM-L12-v2).")
        except Exception as exc:
            logger.exception("Failed to initialize embedding model: %s", exc)
            _embeddings = None

    return _embeddings


# Backward-compatible alias for older imports.
embeddings = None
