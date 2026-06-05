from __future__ import annotations

from pathlib import Path
from typing import Dict
import uuid


ROOT_DIR = Path(__file__).resolve().parents[2]
TEMP_UPLOADS_DIR = ROOT_DIR / "temp_uploads"
TEST_OCR_DIR = TEMP_UPLOADS_DIR / "test_ocr"
GENERATED_DIR = TEST_OCR_DIR / "generated"
RUNS_DIR = TEST_OCR_DIR / "runs"


def ensure_test_ocr_dirs() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def build_batch_code() -> str:
    return f"ocr-{uuid.uuid4().hex[:10]}"


def build_generated_docx_path(batch_code: str) -> Path:
    ensure_test_ocr_dirs()
    return GENERATED_DIR / f"{batch_code}.docx"


def build_generated_answer_xlsx_path(batch_code: str) -> Path:
    ensure_test_ocr_dirs()
    return GENERATED_DIR / f"{batch_code}-answers.xlsx"


def create_run_dir(batch_code: str) -> Path:
    ensure_test_ocr_dirs()
    run_dir = RUNS_DIR / f"{batch_code}-{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "pages").mkdir(exist_ok=True)
    (run_dir / "crops").mkdir(exist_ok=True)
    return run_dir


def to_public_temp_path(path: Path) -> str:
    relative = path.resolve().relative_to(TEMP_UPLOADS_DIR.resolve())
    return "/" + str(Path("temp_uploads") / relative).replace("\\", "/")


def default_omr_config(question_count: int, student_id_columns: int = 8, exam_code_columns: int = 3) -> Dict[str, int]:
    return {
        "student_id_columns": student_id_columns,
        "exam_code_columns": exam_code_columns,
        "question_count": question_count,
        "option_count": 4,
        "template_width": 2480,
        "template_height": 3508,
        "alignment_marker_size": 64,
    }
