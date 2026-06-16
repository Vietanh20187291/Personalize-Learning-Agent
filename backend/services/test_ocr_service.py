from __future__ import annotations

import io
import random
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from db import models
from services.ocr_exam_generator import _build_omr_layout, _render_omr_sheet
from services.omr_processor import OMRProcessorService
from services.pdf_processor import LoadedSubmissionImage, PDFProcessorService
from services.student_name_ocr import StudentNameOCRService
from services.test_ocr_answer_key_excel import parse_answer_key_workbook
from services.test_ocr_storage import (
    build_batch_code,
    build_generated_answer_xlsx_path,
    create_run_dir,
    to_public_temp_path,
)


class TestOCRService:
    def __init__(self, db: Session):
        self.db = db
        self.pdf_processor = PDFProcessorService()
        self.student_name_ocr = StudentNameOCRService()

    def get_batch(self, batch_id: int) -> models.TestOCRExamBatch | None:
        return self.db.query(models.TestOCRExamBatch).filter(models.TestOCRExamBatch.id == batch_id).first()

    def get_grading_result(self, result_id: int) -> models.TestOCRGradingResult | None:
        return self.db.query(models.TestOCRGradingResult).filter(models.TestOCRGradingResult.id == result_id).first()

    def get_docx_path(self, batch: models.TestOCRExamBatch) -> Path | None:
        if not batch.generated_docx_path:
            return None
        return Path(str(batch.generated_docx_path)).resolve()

    def get_answer_xlsx_path(self, batch: models.TestOCRExamBatch) -> Path:
        return build_generated_answer_xlsx_path(batch.batch_code).resolve()

    def serialize_batch(self, batch: models.TestOCRExamBatch) -> Dict[str, object]:
        docx_path = self.get_docx_path(batch)
        answer_xlsx_path = self.get_answer_xlsx_path(batch)
        has_generated_docx = docx_path is not None and docx_path.exists()
        has_answer_key_xlsx = answer_xlsx_path.exists()
        return {
            "id": batch.id,
            "batch_code": batch.batch_code,
            "class_id": batch.class_id,
            "subject_id": batch.subject_id,
            "subject_name": batch.subject_name,
            "exam_type": batch.exam_type,
            "level": batch.level,
            "num_questions": batch.num_questions,
            "num_versions": batch.num_versions,
            "exam_codes": [item.get("exam_code", "") for item in (batch.answer_key_json or [])],
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "omr_layout": batch.omr_layout_json or {},
            "has_generated_docx": has_generated_docx,
            "has_answer_key_xlsx": has_answer_key_xlsx,
            "download_urls": {
                "docx": f"/api/exam/ocr/batches/{batch.id}/download/docx" if has_generated_docx else None,
                "answer_xlsx": f"/api/exam/ocr/batches/{batch.id}/download/answer-xlsx" if has_answer_key_xlsx else None,
                "test_sheet_pdf": f"/api/exam/ocr/batches/{batch.id}/download/test-sheet",
            },
        }

    def serialize_grading_result(self, result_row: models.TestOCRGradingResult) -> Dict[str, object]:
        debug_payload = dict(result_row.debug_json or {})
        predicted_name = str(debug_payload.get("predicted_student_name", "") or "")
        edited_name = str(debug_payload.get("edited_student_name", "") or "")
        display_name = edited_name or predicted_name
        return {
            "id": result_row.id,
            "page_number": result_row.page_number,
            "original_image_url": to_public_temp_path(Path(str(debug_payload.get("original_image_path") or result_row.source_image_path or ""))),
            "student_name_image_url": to_public_temp_path(Path(str(result_row.student_name_image_path or ""))),
            "source_image_url": to_public_temp_path(Path(str(result_row.source_image_path or ""))),
            "detected_student_id": result_row.detected_student_id or "",
            "detected_exam_code": result_row.detected_exam_code or "",
            "predicted_student_name": predicted_name,
            "predicted_student_name_engine": str(debug_payload.get("predicted_student_name_engine", "") or ""),
            "edited_student_name": edited_name,
            "display_student_name": display_name,
            "detected_answers": list(result_row.detected_answers_json or []),
            "correct_count": int(result_row.correct_count or 0),
            "total_questions": int(result_row.total_questions or 0),
            "score": float(result_row.score or 0.0),
            "grading_status": result_row.grading_status or "",
        }

    def create_grading_batch(
        self,
        *,
        teacher_id: int | None,
        class_id: int,
        num_questions: int,
        student_id_columns: int = 8,
    ) -> models.TestOCRExamBatch:
        if num_questions < 1 or num_questions > 120:
            raise ValueError("Số câu hỏi phải nằm trong khoảng 1-120.")
        if student_id_columns < 4 or student_id_columns > 12:
            raise ValueError("Số cột MSSV phải nằm trong khoảng 4-12.")

        target_class = self.db.query(models.Classroom).filter_by(id=class_id).first()
        if target_class is None:
            raise LookupError("Không tìm thấy lớp học để khởi tạo batch OCR.")

        subject_name = str(
            getattr(getattr(target_class, "subject_obj", None), "name", None)
            or getattr(target_class, "subject", None)
            or ""
        ).strip()
        if not subject_name:
            raise LookupError("Không xác định được môn học của lớp đã chọn.")

        layout = _build_omr_layout(question_count=num_questions, student_id_columns=student_id_columns, exam_code_columns=3)
        layout["sheet_meta"] = {
            "school_name": "",
            "department_name": "",
            "subject_name": subject_name,
            "class_name": str(target_class.name or ""),
            "exam_date": "....... / ....... / ............",
        }

        batch = models.TestOCRExamBatch(
            teacher_id=teacher_id,
            class_id=class_id,
            subject_id=target_class.subject_id,
            subject_name=subject_name,
            exam_type="trac_nghiem",
            level=None,
            num_questions=num_questions,
            num_versions=1,
            batch_code=build_batch_code(),
            generated_docx_path=None,
            answer_key_json=[],
            omr_layout_json=layout,
        )
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def update_student_name(self, result_id: int, student_name: str) -> Dict[str, object]:
        result_row = self.get_grading_result(result_id)
        if result_row is None:
            raise LookupError("Khong tim thay ket qua OCR can cap nhat.")

        debug_payload = dict(result_row.debug_json or {})
        normalized_name = " ".join(str(student_name or "").split()).strip()
        debug_payload["edited_student_name"] = normalized_name
        result_row.debug_json = debug_payload
        self.db.add(result_row)
        self.db.commit()
        self.db.refresh(result_row)
        return self.serialize_grading_result(result_row)

    def _score_answers(self, answer_key: List[str], detected_answers: List[str]) -> Dict[str, object]:
        total = len(answer_key)
        correct = 0
        normalized_answers: List[str] = []
        for index in range(total):
            detected = detected_answers[index] if index < len(detected_answers) else ""
            normalized_answers.append(detected)
            if detected and detected == answer_key[index]:
                correct += 1
        score = round((correct / total) * 10.0, 2) if total else 0.0
        return {
            "detected_answers": normalized_answers,
            "correct_count": correct,
            "total_questions": total,
            "score": score,
        }

    def _answer_key_by_code_from_batch(self, batch: models.TestOCRExamBatch) -> Dict[str, List[str]]:
        return {
            str(item.get("exam_code", "")).strip(): list(item.get("answer_key", []))
            for item in (batch.answer_key_json or [])
            if str(item.get("exam_code", "")).strip()
        }

    def resolve_answer_key_by_code(
        self,
        batch: models.TestOCRExamBatch,
        *,
        answer_key_bytes: Optional[bytes] = None,
    ) -> Dict[str, List[str]]:
        if answer_key_bytes:
            parsed = parse_answer_key_workbook(answer_key_bytes)
            if parsed:
                normalized: Dict[str, List[str]] = {}
                for exam_code, answers in parsed.items():
                    answer_list = list(answers[: batch.num_questions])
                    if len(answer_list) < batch.num_questions:
                        answer_list.extend([""] * (batch.num_questions - len(answer_list)))
                    normalized[exam_code] = answer_list
                return normalized
            raise RuntimeError("Khong doc duoc dap an hop le tu file Excel.")

        answer_key_by_code = self._answer_key_by_code_from_batch(batch)
        if not answer_key_by_code:
            raise RuntimeError("Batch OCR khong co dap an de cham.")
        return answer_key_by_code

    def build_test_sheet_pdf(self, batch: models.TestOCRExamBatch) -> bytes:
        layout = batch.omr_layout_json or {}
        sheet_meta = dict(layout.get("sheet_meta") or {})
        student_id_columns = int(layout.get("student_id_columns", 8))
        question_count = int(layout.get("question_count", batch.num_questions or 0))
        random_student_id = "".join(str(random.randint(0, 9)) for _ in range(student_id_columns))
        random_answers = [random.choice(["A", "B", "C", "D"]) for _ in range(question_count)]

        image_stream = _render_omr_sheet(
            version_code=None,
            question_count=question_count,
            layout=layout,
            prefilled_student_id=random_student_id,
            prefilled_answers=random_answers,
            school_name=str(sheet_meta.get("school_name", "") or ""),
            department_name=str(sheet_meta.get("department_name", "") or ""),
            subject_name=str(sheet_meta.get("subject_name", batch.subject_name or "") or ""),
            class_name=str(sheet_meta.get("class_name", "") or ""),
            exam_date=str(sheet_meta.get("exam_date", "....... / ....... / ............") or ""),
        )
        image = Image.open(image_stream).convert("RGB")
        pdf_buffer = io.BytesIO()
        image.save(pdf_buffer, format="PDF", resolution=200.0)
        return pdf_buffer.getvalue()

    def _persist_uploaded_sources(self, run_dir: Path, submissions: Sequence[Tuple[str, bytes]]) -> str:
        if not submissions:
            return ""

        if len(submissions) == 1 and submissions[0][0].lower().endswith(".pdf"):
            pdf_path = run_dir / Path(submissions[0][0]).name
            self.pdf_processor.save_pdf(pdf_path, submissions[0][1])
            return str(pdf_path)

        uploads_dir = run_dir / "uploads"
        uploads_dir.mkdir(exist_ok=True)
        saved_paths: List[Path] = []
        for index, (filename, payload) in enumerate(submissions, start=1):
            safe_name = Path(filename or f"upload_{index}").name or f"upload_{index}"
            stored_path = uploads_dir / f"{index:03d}_{safe_name}"
            stored_path.write_bytes(payload)
            saved_paths.append(stored_path)

        if len(saved_paths) == 1:
            return str(saved_paths[0])

        manifest_path = run_dir / "submission_manifest.txt"
        manifest_path.write_text("\n".join(str(path) for path in saved_paths), encoding="utf-8")
        return str(manifest_path)

    def _load_submission_images(self, submissions: Sequence[Tuple[str, bytes]]) -> List[LoadedSubmissionImage]:
        page_images: List[LoadedSubmissionImage] = []
        for filename, payload in submissions:
            page_images.extend(self.pdf_processor.load_submission_images(filename, payload))
        if not page_images:
            raise ValueError("Không đọc được trang nào từ tệp đã tải lên.")
        return page_images

    def _processed_candidate_quality(
        self,
        status: str,
        student_id: str,
        exam_code: str,
        answers: Sequence[str],
        predicted_name_score: float = 0.0,
    ) -> tuple[int, int, int, int, int, float]:
        status_rank = {
            "ok": 4,
            "missing_student_id": 3,
            "ambiguous_answers": 2,
            "missing_exam_code": 1,
        }.get(status, 0)
        answered_count = sum(1 for answer in answers if answer in {"A", "B", "C", "D"})
        multi_count = sum(1 for answer in answers if answer == "MULTI")
        return (
            status_rank,
            int(bool(exam_code.strip())),
            int(bool(student_id.strip())),
            answered_count,
            -multi_count,
            round(float(predicted_name_score or 0.0), 6),
        )

    def grade_submission(
        self,
        *,
        batch_id: int,
        submissions: Sequence[Tuple[str, bytes]],
        answer_key_bytes: Optional[bytes] = None,
    ) -> Dict[str, object]:
        batch = self.get_batch(batch_id)
        if batch is None:
            raise LookupError("Khong tim thay batch OCR da sinh.")

        answer_key_by_code = self.resolve_answer_key_by_code(batch, answer_key_bytes=answer_key_bytes)

        run_dir = create_run_dir(batch.batch_code)
        source_path = self._persist_uploaded_sources(run_dir, submissions)
        loaded_pages = self._load_submission_images(submissions)

        grading_run = models.TestOCRGradingRun(
            batch_id=batch.id,
            uploaded_pdf_path=source_path,
            page_count=len(loaded_pages),
        )
        self.db.add(grading_run)
        self.db.commit()
        self.db.refresh(grading_run)

        processor = OMRProcessorService(batch.omr_layout_json or {})
        results: List[Dict[str, object]] = []
        debug_dir = run_dir / "debug"
        debug_dir.mkdir(exist_ok=True)
        original_dir = run_dir / "originals"
        original_dir.mkdir(exist_ok=True)

        for page_number, loaded_page in enumerate(loaded_pages, start=1):
            candidate_images = loaded_page.candidate_images or [("default", loaded_page.image)]
            original_candidate = next((item for name, item in candidate_images if name == "original"), None)
            original_image = original_candidate if original_candidate is not None else loaded_page.image
            best_processed = None
            best_predicted_name = None
            best_candidate_name = "default"
            best_quality = None
            for candidate_name, candidate_image in candidate_images:
                current_processed = processor.process_page(candidate_image)
                current_predicted_name = self.student_name_ocr.recognize(
                    current_processed.name_crop,
                    fallback_image=current_processed.name_box_crop,
                )
                current_quality = self._processed_candidate_quality(
                    current_processed.status,
                    current_processed.student_id,
                    current_processed.exam_code,
                    current_processed.answers,
                    predicted_name_score=current_predicted_name.score,
                )
                if best_processed is None or current_quality > best_quality:
                    best_processed = current_processed
                    best_predicted_name = current_predicted_name
                    best_candidate_name = candidate_name
                    best_quality = current_quality

            processed = best_processed
            predicted_name = best_predicted_name or self.student_name_ocr.recognize(
                processed.name_crop,
                fallback_image=processed.name_box_crop,
            )

            page_image_path = run_dir / "pages" / f"page_{page_number:03d}.png"
            name_crop_path = run_dir / "crops" / f"name_{page_number:03d}.png"
            original_image_path = original_dir / f"original_{page_number:03d}.png"
            Image.fromarray(original_image.astype(np.uint8)).save(original_image_path)
            Image.fromarray(processed.aligned_image.astype(np.uint8)).save(page_image_path)
            Image.fromarray(processed.name_crop.astype(np.uint8)).save(name_crop_path)

            if loaded_page.source_type == "image":
                for debug_name, debug_image in loaded_page.debug_images.items():
                    debug_path = debug_dir / f"{debug_name}_{page_number:03d}.png"
                    Image.fromarray(debug_image.astype(np.uint8)).save(debug_path)

            exam_code = processed.exam_code.strip()
            grading_status = processed.status
            answer_key = answer_key_by_code.get(exam_code)
            if answer_key is None:
                grading_status = "unknown_exam_code"
                scored = {
                    "detected_answers": processed.answers,
                    "correct_count": 0,
                    "total_questions": batch.num_questions,
                    "score": 0.0,
                }
            else:
                scored = self._score_answers(answer_key, processed.answers)
                if grading_status == "ok":
                    grading_status = "graded"

            result_row = models.TestOCRGradingResult(
                run_id=grading_run.id,
                batch_id=batch.id,
                page_number=page_number,
                source_image_path=str(page_image_path),
                student_name_image_path=str(name_crop_path),
                detected_student_id=processed.student_id,
                detected_exam_code=exam_code,
                detected_answers_json=scored["detected_answers"],
                correct_count=int(scored["correct_count"]),
                total_questions=int(scored["total_questions"]),
                score=float(scored["score"]),
                grading_status=grading_status,
                debug_json={
                    **loaded_page.debug,
                    **processed.debug,
                    "submission_source_type": loaded_page.source_type,
                    "original_image_path": str(original_image_path),
                    "selected_image_candidate": best_candidate_name,
                    "predicted_student_name": predicted_name.text,
                    "predicted_student_name_engine": predicted_name.engine,
                    "predicted_student_name_score": predicted_name.score,
                },
            )
            self.db.add(result_row)
            self.db.flush()

            results.append(self.serialize_grading_result(result_row))

        self.db.commit()
        return {
            "run_id": grading_run.id,
            "batch": self.serialize_batch(batch),
            "results": results,
        }

    def grade_pdf(
        self,
        batch_id: int,
        filename: str,
        pdf_bytes: bytes,
        *,
        answer_key_bytes: Optional[bytes] = None,
    ) -> Dict[str, object]:
        return self.grade_submission(
            batch_id=batch_id,
            submissions=[(filename, pdf_bytes)],
            answer_key_bytes=answer_key_bytes,
        )
