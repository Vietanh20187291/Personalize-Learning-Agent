from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import copy
import io
import json
import logging
import random
import re
import time
import unicodedata
from typing import List

from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Pt

from db import models
from db.database import get_db

router = APIRouter()
logger = logging.getLogger("app.exam")


class ExamRequest(BaseModel):
    class_id: int
    subject: str
    exam_type: str
    num_questions: int
    num_versions: int
    level: str


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
    if req.exam_type == "trắc nghiệm":
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
    else:
        for idx in range(needed):
            sentence = sentences[idx % len(sentences)]
            result.append(
                {
                    "q": f"Trình bày và phân tích nội dung sau trong môn {req.subject}: {sentence[:160]}",
                    "ans": "Nêu đúng khái niệm, ý chính, cách vận dụng và kết luận.",
                    "exp": "Gợi ý chấm theo các ý chính của học liệu.",
                }
            )
    return result


def create_exam_header(doc: Document, subject: str, exam_type: str, exam_code: str) -> None:
    table = doc.add_table(rows=1, cols=2)
    table.autofit = True

    cell_left = table.cell(0, 0)
    p_left1 = cell_left.paragraphs[0]
    p_left1.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_left1 = p_left1.add_run("BỘ GIÁO DỤC VÀ ĐÀO TẠO\nTRƯỜNG ĐẠI HỌC XÂY DỰNG HÀ NỘI")
    run_left1.font.size = Pt(11)

    p_left2 = cell_left.add_paragraph()
    p_left2.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_left2 = p_left2.add_run("KHOA CÔNG NGHỆ THÔNG TIN")
    run_left2.font.size = Pt(12)
    run_left2.bold = True

    p_left3 = cell_left.add_paragraph()
    p_left3.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p_left3.add_run("-----------------------").bold = True

    cell_right = table.cell(0, 1)
    p_right1 = cell_right.paragraphs[0]
    p_right1.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_right1 = p_right1.add_run("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    run_right1.font.size = Pt(11)
    run_right1.bold = True

    p_right2 = cell_right.add_paragraph()
    p_right2.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_right2 = p_right2.add_run("Độc lập - Tự do - Hạnh phúc")
    run_right2.font.size = Pt(12)
    run_right2.bold = True

    p_right3 = cell_right.add_paragraph()
    p_right3.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p_right3.add_run("-----------------------").bold = True

    doc.add_paragraph()

    p_title = doc.add_paragraph()
    p_title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run_title = p_title.add_run("ĐỀ THI KẾT THÚC HỌC PHẦN")
    run_title.font.size = Pt(16)
    run_title.bold = True

    p_info = doc.add_paragraph()
    p_info.add_run("Môn thi: ").bold = True
    p_info.add_run(f"{subject}\n")
    p_info.add_run("Hình thức thi: ").bold = True
    p_info.add_run(f"{exam_type.title()}\n")
    p_info.add_run("Mã đề thi: ").bold = True
    p_info.add_run(f"{exam_code}\n")
    p_info.add_run("Họ và tên sinh viên: ..................................................... MSSV: ............................... Lớp: ..................")

    doc.add_paragraph("------------------------------------------------------------------------------------------------------------------------")


def remove_accents(input_str: str) -> str:
    safe = str(input_str or "").replace("đ", "d").replace("Đ", "D")
    nfkd_form = unicodedata.normalize("NFKD", safe)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def _safe_filename_fragment(value: str) -> str:
    ascii_value = remove_accents(value or "")
    ascii_value = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_value).strip("_")
    return ascii_value or "TaiLieu"


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
        )
        question_pool.extend(_build_fallback_exam_questions(fallback_req, context_summary, chunk_texts))

    return question_pool


@router.post("/generate-word")
def generate_exam_word(req: ExamRequest, db: Session = Depends(get_db)):
    started_at = time.perf_counter()
    logger.info(
        "generate_exam_word start class_id=%s subject=%s exam_type=%s num_questions=%s num_versions=%s",
        req.class_id,
        req.subject,
        req.exam_type,
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
        req=req,
        target_class=target_class,
        docs=docs,
        context_summary=context_summary,
        chunk_texts=chunk_texts,
    )
    if len(question_pool) < req.num_questions:
        raise HTTPException(status_code=500, detail="Không thể chuẩn bị đủ số câu hỏi để xuất đề thi Word.")

    doc = Document()
    exam_versions = []

    for _ in range(req.num_versions):
        exam_code = str(random.randint(101, 999))
        selected_questions = copy.deepcopy(random.sample(question_pool, req.num_questions))
        random.shuffle(selected_questions)
        exam_versions.append({"code": exam_code, "questions": selected_questions})

        create_exam_header(doc, req.subject, req.exam_type, exam_code)
        for idx, question in enumerate(selected_questions, start=1):
            paragraph = doc.add_paragraph()
            paragraph.add_run(f"Câu {idx}: ").bold = True
            paragraph.add_run(question.get("q", ""))

            if req.exam_type == "trắc nghiệm":
                options = copy.deepcopy(question.get("options", []))
                correct_idx = ord(question.get("ans", "A").upper()) - 65
                correct_text = options[correct_idx] if 0 <= correct_idx < len(options) else options[0]
                random.shuffle(options)
                labels = ["A", "B", "C", "D"]
                new_correct_label = "A"
                for option_idx, option_text in enumerate(options):
                    if option_text == correct_text:
                        new_correct_label = labels[option_idx]
                    doc.add_paragraph(f"{labels[option_idx]}. {option_text}")
                question["new_ans"] = new_correct_label
            else:
                for _line in range(4):
                    doc.add_paragraph("................................................................................................................................")
            doc.add_paragraph()

        doc.add_page_break()

    answer_heading = doc.add_heading("HƯỚNG DẪN CHẤM VÀ ĐÁP ÁN", 1)
    answer_heading.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    doc.add_paragraph()

    for version in exam_versions:
        doc.add_paragraph(f"MÃ ĐỀ: {version['code']}").bold = True
        if req.exam_type == "trắc nghiệm":
            table = doc.add_table(rows=1, cols=6)
            table.style = "Table Grid"
            for idx in range(6):
                table.rows[0].cells[idx].text = "Câu - Đáp án"

            row_cells = table.add_row().cells
            col_idx = 0
            for question_idx, question in enumerate(version["questions"], start=1):
                if col_idx > 5:
                    row_cells = table.add_row().cells
                    col_idx = 0
                row_cells[col_idx].text = f"Câu {question_idx}: {question.get('new_ans', question.get('ans', 'A'))}"
                col_idx += 1
            doc.add_paragraph()
        else:
            for question_idx, question in enumerate(version["questions"], start=1):
                paragraph = doc.add_paragraph()
                paragraph.add_run(f"Câu {question_idx}: ").bold = True
                doc.add_paragraph(question.get("ans", ""))
                doc.add_paragraph(f"Gợi ý chấm: {question.get('exp', '')}").italic = True
        doc.add_paragraph("----------------------------------------------------------------")

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)

    filename = f"DeThi_{_safe_filename_fragment(req.subject)}_{_safe_filename_fragment(req.exam_type)}.docx"
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
