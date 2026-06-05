from __future__ import annotations

import copy
import io
import json
import logging
import random
import re
import time
import unicodedata
from typing import List, Optional

from docx import Document
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import models
from db.database import get_db
from services.exam_doc_utils import (
    DEFAULT_DEPARTMENT_NAME,
    DEFAULT_EXAM_TITLE,
    DEFAULT_EXAM_TYPE_LABEL,
    DEFAULT_SCHOOL_NAME,
    add_answer_key_section,
    add_answer_sheet,
    add_candidate_block,
    add_exam_info_table,
    add_exam_instruction_block,
    add_multiple_choice_questions,
    add_school_header,
    apply_document_style,
)

router = APIRouter()
logger = logging.getLogger("app.exam")
DEFAULT_EXAM_TYPE = "trắc nghiệm"


class ExamRequest(BaseModel):
    class_id: int
    subject: str
    exam_type: Optional[str] = None
    num_questions: int
    num_versions: int
    level: str
    duration_minutes: int = 60
    semester: str = "Học kỳ II"
    academic_year: str = "Năm học 2025 - 2026"
    exam_date: str = "....... / ....... / ............"
    school_name: str = DEFAULT_SCHOOL_NAME
    department_name: str = DEFAULT_DEPARTMENT_NAME
    exam_title: str = DEFAULT_EXAM_TITLE


def _strip_option_prefix(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^[\u2022\-\*]+\s*", "", text)
    text = re.sub(r"^(?:[A-Da-d])[\.\)\:\-]\s*", "", text)
    text = re.sub(r"\s+#\d+\b", "", text)
    text = re.sub(
        r"\s*(?:Trọng tâm|Trong ngữ cảnh|Khi xét|Trong phạm vi)\s*:\s*[^.?!;]+[.?!;:]*\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip()


def _normalize_question_bank_options(raw_options) -> List[str]:
    if isinstance(raw_options, list):
        return [_strip_option_prefix(str(item or "")) for item in raw_options if _strip_option_prefix(str(item or ""))]
    if isinstance(raw_options, str):
        try:
            parsed = json.loads(raw_options)
            if isinstance(parsed, list):
                return [_strip_option_prefix(str(item or "")) for item in parsed if _strip_option_prefix(str(item or ""))]
        except Exception:
            pass
    return []


def _resolve_correct_label(correct_answer: str, options: List[str]) -> str:
    normalized = str(correct_answer or "").strip().upper()
    if normalized in {"A", "B", "C", "D"}:
        return normalized

    clean_answer = re.sub(r"\s+", " ", str(correct_answer or "")).strip().lower()
    for idx, option in enumerate(options[:4]):
        if re.sub(r"\s+", " ", str(option or "")).strip().lower() == clean_answer:
            return ["A", "B", "C", "D"][idx]
    return "A"


def _collect_chunk_texts(db: Session, allowed_filenames: List[str], limit: int = 200) -> List[str]:
    if not allowed_filenames:
        return []
    rows = (
        db.query(models.Chunk)
        .filter(models.Chunk.source_file.in_(allowed_filenames))
        .order_by(models.Chunk.id.asc())
        .limit(limit)
        .all()
    )
    return [re.sub(r"\s+", " ", str(row.content or "")).strip() for row in rows if str(row.content or "").strip()]


def _build_fallback_exam_questions(req: ExamRequest, context_summary: str, chunk_texts: List[str]) -> List[dict]:
    needed = max(1, int(req.num_questions or 1))
    source_text = "\n".join(chunk_texts[:120]) if chunk_texts else context_summary
    source_text = re.sub(r"\s+", " ", source_text or "").strip()

    sentences = []
    for item in re.split(r"(?<=[\.\!\?\;\:])\s+", source_text):
        clean = re.sub(r"\s+", " ", item or "").strip()
        if 45 <= len(clean) <= 220:
            sentences.append(clean)
    if not sentences:
        sentences = [f"Môn {req.subject} yêu cầu nắm chắc các khái niệm và nguyên lý cốt lõi."]

    result: List[dict] = []
    for idx in range(needed):
        sentence = sentences[idx % len(sentences)]
        question = f"Theo học liệu môn {req.subject}, phát biểu nào đúng nhất với ý sau: \"{sentence[:120]}\"?"
        correct = sentence[:180]
        distractors = [
            (sentence[:120] + " nhưng áp dụng trong ngữ cảnh khác của môn học.")[:180],
            f"Nội dung này không liên quan trực tiếp đến trọng tâm của {req.subject}.",
            f"Đây chỉ là một ví dụ phụ, không phải kết luận chính về {req.subject}.",
        ]
        result.append(
            {
                "q": question,
                "options": [correct] + distractors,
                "ans": "A",
                "exp": "Câu bổ sung tự động khi ngân hàng câu hỏi chưa đủ.",
            }
        )
    return result


def remove_accents(input_str: str) -> str:
    safe = str(input_str or "").replace("đ", "d").replace("Đ", "D")
    nfkd_form = unicodedata.normalize("NFKD", safe)
    return "".join([char for char in nfkd_form if not unicodedata.combining(char)])


def _safe_filename_fragment(value: str) -> str:
    ascii_value = remove_accents(value or "")
    ascii_value = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_value).strip("_")
    return ascii_value or "TaiLieu"


def _normalize_exam_type(_: Optional[str]) -> str:
    return DEFAULT_EXAM_TYPE


def _copy_exam_request(req: ExamRequest, **updates) -> ExamRequest:
    if hasattr(req, "model_copy"):
        return req.model_copy(update=updates)
    return req.copy(update=updates)


def _build_question_pool(
    db: Session,
    req: ExamRequest,
    target_class: models.Classroom,
    docs: List[models.Document],
    context_summary: str,
    chunk_texts: List[str],
) -> List[dict]:
    allowed_filenames = {str(doc.filename or "").strip() for doc in docs if str(doc.filename or "").strip()}
    subject_id = int(target_class.subject_id)

    rows = (
        db.query(models.QuestionBank)
        .filter(
            models.QuestionBank.subject_id == subject_id,
            models.QuestionBank.source_file.in_(allowed_filenames),
        )
        .order_by(models.QuestionBank.id.asc())
        .all()
    )
    if len(rows) < req.num_questions:
        fallback_rows = (
            db.query(models.QuestionBank)
            .filter(models.QuestionBank.subject_id == subject_id)
            .order_by(models.QuestionBank.id.asc())
            .all()
        )
        seen_ids = {int(item.id) for item in rows}
        rows.extend([row for row in fallback_rows if int(row.id) not in seen_ids])

    question_pool: List[dict] = []
    for row in rows:
        options = _normalize_question_bank_options(getattr(row, "options", []))
        if len(options) < 4:
            continue
        question_text = re.sub(r"\s+", " ", str(getattr(row, "content", "") or "")).strip()
        if not question_text:
            continue
        question_pool.append(
            {
                "q": question_text,
                "options": options[:4],
                "ans": _resolve_correct_label(str(getattr(row, "correct_answer", "") or ""), options),
                "exp": re.sub(r"\s+", " ", str(getattr(row, "explanation", "") or "")).strip(),
            }
        )

    if len(question_pool) < req.num_questions:
        missing_count = req.num_questions - len(question_pool)
        fallback_req = ExamRequest(
            class_id=req.class_id,
            subject=req.subject,
            exam_type=req.exam_type,
            num_questions=missing_count,
            num_versions=1,
            level=req.level,
            duration_minutes=req.duration_minutes,
            semester=req.semester,
            academic_year=req.academic_year,
            exam_date=req.exam_date,
            school_name=req.school_name,
            department_name=req.department_name,
            exam_title=req.exam_title,
        )
        question_pool.extend(_build_fallback_exam_questions(fallback_req, context_summary, chunk_texts))

    return question_pool


def _next_exam_code(used_codes: set[str]) -> str:
    while True:
        exam_code = str(random.randint(101, 999))
        if exam_code not in used_codes:
            used_codes.add(exam_code)
            return exam_code


@router.post("/generate-word")
def generate_exam_word(req: ExamRequest, db: Session = Depends(get_db)):
    started_at = time.perf_counter()
    exam_type = _normalize_exam_type(req.exam_type)
    logger.info(
        "generate_exam_word start class_id=%s subject=%s exam_type=%s num_questions=%s num_versions=%s",
        req.class_id,
        req.subject,
        exam_type,
        req.num_questions,
        req.num_versions,
    )

    if req.num_questions < 1 or req.num_questions > 40:
        raise HTTPException(status_code=400, detail="Số câu hỏi phải nằm trong khoảng 1-40.")
    if req.num_versions < 1 or req.num_versions > 4:
        raise HTTPException(status_code=400, detail="Số mã đề phải nằm trong khoảng 1-4.")

    target_class = db.query(models.Classroom).filter_by(id=req.class_id).first()
    if not target_class:
        raise HTTPException(status_code=404, detail="Lớp học không tồn tại.")

    docs = (
        db.query(models.Document)
        .filter(
            models.Document.class_id == req.class_id,
            models.Document.subject_id == target_class.subject_id,
        )
        .all()
    )
    if not docs:
        raise HTTPException(status_code=400, detail="Lớp học này chưa có tài liệu phù hợp để sinh đề thi.")

    allowed_filenames = [doc.filename for doc in docs if doc.filename]
    chunk_texts = _collect_chunk_texts(db, allowed_filenames, limit=240)
    context_summary = "\n".join(chunk_texts[:80])[:14000] if chunk_texts else f"Học liệu môn {req.subject}"

    question_pool = _build_question_pool(
        db=db,
        req=_copy_exam_request(req, exam_type=exam_type),
        target_class=target_class,
        docs=docs,
        context_summary=context_summary,
        chunk_texts=chunk_texts,
    )
    if len(question_pool) < req.num_questions:
        raise HTTPException(status_code=500, detail="Không thể chuẩn bị đủ số câu hỏi để xuất đề thi Word.")

    doc = Document()
    apply_document_style(doc)

    exam_versions = []
    used_codes: set[str] = set()

    for version_index in range(req.num_versions):
        exam_code = _next_exam_code(used_codes)
        selected_questions = copy.deepcopy(random.sample(question_pool, req.num_questions))
        random.shuffle(selected_questions)

        for question in selected_questions:
            options = copy.deepcopy(question.get("options", []))
            correct_idx = ord(question.get("ans", "A").upper()) - 65
            correct_text = options[correct_idx] if 0 <= correct_idx < len(options) else options[0]
            random.shuffle(options)
            question["options"] = options
            question["new_ans"] = ["A", "B", "C", "D"][options.index(correct_text)]

        exam_versions.append({"code": exam_code, "questions": selected_questions})

        add_school_header(
            doc,
            school_name=req.school_name,
            department_name=req.department_name,
            exam_title=req.exam_title,
            section_title="ĐỀ THI TRẮC NGHIỆM",
        )
        add_exam_info_table(
            doc,
            subject=req.subject,
            class_name=target_class.name,
            exam_code=exam_code,
            exam_type_label=DEFAULT_EXAM_TYPE_LABEL,
            semester=req.semester,
            academic_year=req.academic_year,
            exam_date=req.exam_date,
            duration_minutes=req.duration_minutes,
        )
        add_candidate_block(doc)
        add_exam_instruction_block(doc, exam_type_label=DEFAULT_EXAM_TYPE_LABEL)
        add_multiple_choice_questions(doc, selected_questions)
        add_answer_sheet(
            doc,
            school_name=req.school_name,
            department_name=req.department_name,
            exam_title=req.exam_title,
            subject=req.subject,
            class_name=target_class.name,
            exam_code=exam_code,
            exam_type_label=DEFAULT_EXAM_TYPE_LABEL,
            semester=req.semester,
            academic_year=req.academic_year,
            exam_date=req.exam_date,
            duration_minutes=req.duration_minutes,
            num_questions=req.num_questions,
        )

        if version_index < req.num_versions - 1:
            doc.add_page_break()

    add_answer_key_section(doc, exam_versions, exam_type_label=DEFAULT_EXAM_TYPE_LABEL)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    filename = f"DeThi_{_safe_filename_fragment(req.subject)}_TracNghiem.docx"
    logger.info(
        "generate_exam_word done class_id=%s subject=%s duration_ms=%.2f pool_size=%s versions=%s",
        req.class_id,
        req.subject,
        (time.perf_counter() - started_at) * 1000,
        len(question_pool),
        req.num_versions,
    )
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
