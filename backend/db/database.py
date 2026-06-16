from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False}
if is_sqlite:
    connect_args["timeout"] = 30

engine_kwargs = {
    "connect_args": connect_args,
    "pool_pre_ping": bool(getattr(settings, "DATABASE_POOL_PRE_PING", True)),
}
if not is_sqlite:
    engine_kwargs.update(
        {
            "pool_size": max(1, int(getattr(settings, "DATABASE_POOL_SIZE", 20) or 20)),
            "max_overflow": max(0, int(getattr(settings, "DATABASE_MAX_OVERFLOW", 40) or 40)),
            "pool_timeout": max(5, int(getattr(settings, "DATABASE_POOL_TIMEOUT_SECONDS", 30) or 30)),
            "pool_recycle": max(60, int(getattr(settings, "DATABASE_POOL_RECYCLE_SECONDS", 1800) or 1800)),
            "pool_use_lifo": True,
        }
    )

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)


if is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
