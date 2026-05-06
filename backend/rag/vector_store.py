import logging
import os
import threading
from typing import Optional

from langchain_chroma import Chroma

from rag.embedder import get_embeddings


logger = logging.getLogger("app.rag.vector_store")

ABS_PATH = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(ABS_PATH, "../chroma_db")
COLLECTION_NAME = "ai_learning_collection"

_vector_store: Optional[Chroma] = None
_vector_store_lock = threading.Lock()


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is not None:
        return _vector_store

    with _vector_store_lock:
        if _vector_store is not None:
            return _vector_store

        if not os.path.exists(DB_DIR):
            os.makedirs(DB_DIR)

        embedding_fn = get_embeddings()
        if embedding_fn is None:
            raise RuntimeError(
                "Vector store is disabled or embedding model is unavailable in this runtime."
            )

        _vector_store = Chroma(
            persist_directory=DB_DIR,
            embedding_function=embedding_fn,
            collection_name=COLLECTION_NAME,
        )
        logger.info(
            "Vector store initialized. collection=%s persist_directory=%s",
            COLLECTION_NAME,
            DB_DIR,
        )

    return _vector_store


def add_documents_to_db(docs):
    if not docs:
        return

    vector_store = get_vector_store()
    vector_store.add_documents(docs)
    logger.info("Added %s document chunks to ChromaDB.", len(docs))
