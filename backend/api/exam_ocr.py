from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from services.ocr_exam_generator import OCRExamGeneratorService
from services.test_ocr_service import TestOCRService


router = APIRouter()


class ExamOcrGenerateRequest(BaseModel):
    teacher_id: int | None = None
    class_id: int
    subject: str
    exam_type: str = "trac nghiem"
    num_questions: int
    num_versions: int
    level: str = "Trung binh"
    student_id_columns: int = 8


class ExamOcrInitBatchRequest(BaseModel):
    teacher_id: int | None = None
    class_id: int
    num_questions: int
    student_id_columns: int = 8


class ExamOcrStudentNameUpdateRequest(BaseModel):
    student_name: str = ""


@router.post("/generate-word")
def generate_exam_ocr_word(req: ExamOcrGenerateRequest, db: Session = Depends(get_db)):
    try:
        bundle = OCRExamGeneratorService(db).generate_exam_bundle(
            teacher_id=req.teacher_id,
            class_id=req.class_id,
            subject=req.subject,
            exam_type=req.exam_type,
            num_questions=req.num_questions,
            num_versions=req.num_versions,
            level=req.level,
            student_id_columns=req.student_id_columns,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    file_handle = open(bundle.file_path, "rb")
    headers = {
        "Content-Disposition": f"attachment; filename={bundle.download_filename}",
        "X-Exam-Ocr-Batch-Id": str(bundle.batch.id),
        "Access-Control-Expose-Headers": "Content-Disposition, X-Exam-Ocr-Batch-Id",
    }
    return StreamingResponse(
        file_handle,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@router.post("/init-batch")
def init_exam_ocr_batch(req: ExamOcrInitBatchRequest, db: Session = Depends(get_db)):
    service = TestOCRService(db)
    try:
        batch = service.create_grading_batch(
            teacher_id=req.teacher_id,
            class_id=req.class_id,
            num_questions=req.num_questions,
            student_id_columns=req.student_id_columns,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return service.serialize_batch(batch)


@router.get("/batches/{batch_id}")
def get_exam_ocr_batch(batch_id: int, db: Session = Depends(get_db)):
    service = TestOCRService(db)
    batch = service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Khong tim thay batch OCR.")
    return service.serialize_batch(batch)


@router.get("/batches/{batch_id}/download/docx")
def download_exam_ocr_docx(batch_id: int, db: Session = Depends(get_db)):
    service = TestOCRService(db)
    batch = service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Khong tim thay batch OCR.")

    file_path = service.get_docx_path(batch)
    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay file Word OCR.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/batches/{batch_id}/download/answer-xlsx")
def download_exam_ocr_answer_xlsx(batch_id: int, db: Session = Depends(get_db)):
    service = TestOCRService(db)
    batch = service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Khong tim thay batch OCR.")

    file_path = service.get_answer_xlsx_path(batch)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay file Excel dap an.")

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/batches/{batch_id}/download/test-sheet")
def download_exam_ocr_test_sheet(batch_id: int, db: Session = Depends(get_db)):
    service = TestOCRService(db)
    batch = service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Khong tim thay batch OCR.")

    pdf_bytes = service.build_test_sheet_pdf(batch)
    headers = {
        "Content-Disposition": f'attachment; filename="{batch.batch_code}-test-sheet.pdf"',
    }
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@router.post("/grade-pdf")
async def grade_exam_ocr_submission(
    batch_id: int = Form(...),
    pdf_file: UploadFile | None = File(default=None),
    image_files: list[UploadFile] | None = File(default=None),
    answer_key_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    submissions: list[tuple[str, bytes]] = []

    if pdf_file is not None and image_files:
        raise HTTPException(status_code=400, detail="Chi duoc chon mot kieu tep cham: PDF hoac anh.")

    uploads: list[UploadFile] = []
    if pdf_file is not None:
        uploads.append(pdf_file)
    if image_files:
        uploads.extend(image_files)

    if not uploads:
        raise HTTPException(status_code=400, detail="Vui long tai len file PDF hoac it nhat mot file anh de cham OCR.")

    for upload in uploads:
        filename = (upload.filename or "submission").strip()
        payload = await upload.read()
        if not payload:
            raise HTTPException(status_code=400, detail=f"Tep {filename} rong.")

        suffix = Path(filename).suffix.lower()
        if pdf_file is not None:
            if suffix != ".pdf":
                raise HTTPException(status_code=400, detail="Chi ho tro file PDF cho luong cham PDF.")
        else:
            if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
                raise HTTPException(status_code=400, detail="Chi ho tro anh PNG/JPG/JPEG/BMP/TIFF/WEBP cho luong cham bang anh.")

        submissions.append((filename, payload))

    answer_key_payload = None
    if answer_key_file is not None:
        answer_key_filename = (answer_key_file.filename or "answer-keys.xlsx").strip()
        if not answer_key_filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail="Chi ho tro file Excel .xlsx cho dap an.")
        answer_key_payload = await answer_key_file.read()
        if not answer_key_payload:
            raise HTTPException(status_code=400, detail="File Excel dap an rong.")

    try:
        return TestOCRService(db).grade_submission(
            batch_id=batch_id,
            submissions=submissions,
            answer_key_bytes=answer_key_payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/results/{result_id}/student-name")
def update_exam_ocr_student_name(
    result_id: int,
    req: ExamOcrStudentNameUpdateRequest,
    db: Session = Depends(get_db),
):
    try:
        return TestOCRService(db).update_student_name(result_id=result_id, student_name=req.student_name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
