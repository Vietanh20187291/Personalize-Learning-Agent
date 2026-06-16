import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load file .env and let it override stale shell variables.
load_dotenv(override=True)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
   
    
    # Database
    _raw_database_url = os.getenv("DATABASE_URL", "sqlite:///./sql_db/app.db")
    # Cố định đường dẫn sqlite theo project root để tránh phát sinh nhiều DB khi đổi CWD.
    if _raw_database_url.startswith("sqlite:///./"):
        project_root = Path(__file__).resolve().parent.parent
        rel_path = _raw_database_url.replace("sqlite:///./", "", 1)
        abs_db_path = (project_root / rel_path).resolve().as_posix()
        DATABASE_URL = f"sqlite:///{abs_db_path}"
    else:
        DATABASE_URL = _raw_database_url
    CHROMA_DB_DIR = "chroma_db"
    APP_INSTANCE_NAME = os.getenv("APP_INSTANCE_NAME", os.getenv("HOSTNAME", "backend-instance")).strip() or "backend-instance"
    REQUEST_SLOW_LOG_SECONDS = float(
        os.getenv("REQUEST_SLOW_LOG_SECONDS", os.getenv("REQUEST_TIMEOUT_SECONDS", "75"))
    )
    PREVIEW_CACHE_TTL_SECONDS = int(os.getenv("PREVIEW_CACHE_TTL_SECONDS", "900"))
    ADAPTIVE_AGENT_TIMEOUT_SECONDS = float(os.getenv("ADAPTIVE_AGENT_TIMEOUT_SECONDS", "18") or 18)
    DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "20") or 20)
    DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "40") or 40)
    DATABASE_POOL_TIMEOUT_SECONDS = int(os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "30") or 30)
    DATABASE_POOL_RECYCLE_SECONDS = int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800") or 1800)
    DATABASE_POOL_PRE_PING = _env_flag("DATABASE_POOL_PRE_PING", True)
    REDIS_URL = (os.getenv("REDIS_URL") or "").strip()
    CONVERSATION_MEMORY_TTL_HOURS = int(os.getenv("CONVERSATION_MEMORY_TTL_HOURS", "8") or 8)
    HEALTHCHECK_INCLUDE_VECTOR_STORE = _env_flag("HEALTHCHECK_INCLUDE_VECTOR_STORE", False)
    RAG_EMBEDDINGS_ENABLED = _env_flag(
        "RAG_EMBEDDINGS_ENABLED",
        default=not sys.platform.startswith("win"),
    )

settings = Settings()
