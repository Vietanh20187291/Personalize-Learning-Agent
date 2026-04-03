import os
from pathlib import Path
from dotenv import load_dotenv

# Load file .env
load_dotenv()

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

settings = Settings()

