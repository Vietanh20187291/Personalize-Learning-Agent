import io
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from api import exam_ocr
from db import models
from services.ocr_exam_generator import OCRExamGeneratorService, _build_omr_layout, _draw_bubble, _render_omr_sheet
from services.document_scanner import DocumentScannerService
from services.omr_processor import OMRProcessorService
from services.test_ocr_answer_key_excel import build_answer_key_workbook, parse_answer_key_workbook
from services.pdf_processor import PDFProcessorService
from services.test_ocr_service import TestOCRService as OCRGradingService


def test_generate_test_ocr_word_creates_batch_and_docx(client_factory, db_session, seed):
    teacher = seed.user(db_session, "teacher.ocr@example.com", role="teacher", full_name="OCR Teacher")
    subject = seed.subject(db_session, "Nhap mon OOP")
    classroom = seed.classroom(db_session, "IT-OCR-01", subject, teacher)
    seed.document(db_session, subject, classroom, teacher, filename="oop-ocr.pdf")

    for index in range(1, 25):
        seed.question(
            db_session,
            subject,
            content=f"Cau hoi {index}?",
            options=[
                f"A. Lua chon dung {index}",
                f"B. Lua chon sai 1-{index}",
                f"C. Lua chon sai 2-{index}",
                f"D. Lua chon sai 3-{index}",
            ],
            correct_answer="A",
            source_file="oop-ocr.pdf",
        )

    client = client_factory((exam_ocr.router, "/api/exam/ocr"))
    response = client.post(
        "/api/exam/ocr/generate-word",
        json={
            "teacher_id": teacher.id,
            "class_id": classroom.id,
            "subject": subject.name,
            "exam_type": "trắc nghiệm",
            "num_questions": 20,
            "num_versions": 2,
            "level": "Trung bình",
            "student_id_columns": 8,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert response.headers.get("x-exam-ocr-batch-id")
    assert response.content[:2] == b"PK"

    batch_id = int(response.headers["x-exam-ocr-batch-id"])
    batch = db_session.query(models.TestOCRExamBatch).filter_by(id=batch_id).first()
    assert batch is not None
    assert batch.num_versions == 2
    assert len(batch.answer_key_json or []) == 2

    summary_response = client.get(f"/api/exam/ocr/batches/{batch_id}")
    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["id"] == batch_id
    assert payload["num_questions"] == 20
    assert len(payload["exam_codes"]) == 2
    assert payload["has_generated_docx"] is True
    assert payload["has_answer_key_xlsx"] is True
    assert payload["download_urls"]["answer_xlsx"].endswith("/download/answer-xlsx")

    answer_xlsx_path = OCRGradingService(db_session).get_answer_xlsx_path(batch)
    assert answer_xlsx_path.exists()
    parsed_answer_keys = parse_answer_key_workbook(answer_xlsx_path.read_bytes())
    assert set(parsed_answer_keys.keys()) == set(payload["exam_codes"])
    assert all(len(answer_list) == 20 for answer_list in parsed_answer_keys.values())

    with zipfile.ZipFile(answer_xlsx_path, "r") as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        shared_strings_xml = archive.read("xl/sharedStrings.xml").decode("utf-8")
        first_sheet_xml = shared_strings_xml
        table_xml = archive.read("xl/tables/table1.xml").decode("utf-8")
        core_xml = archive.read("docProps/core.xml").decode("utf-8")
    for exam_code in payload["exam_codes"]:
        assert f'name="{exam_code}"' in workbook_xml
    assert 'name="HUONG_DAN"' in workbook_xml
    assert "PHIẾU ĐÁP ÁN MÃ ĐỀ" in first_sheet_xml
    assert "Đáp án đúng" in first_sheet_xml
    assert "TableStyleMedium2" in table_xml
    assert "Nova Teacher Assessment Suite" in core_xml


def test_init_test_ocr_batch_supports_grading_before_generate(client_factory, db_session, seed):
    teacher = seed.user(db_session, "teacher.init@example.com", role="teacher", full_name="OCR Init Teacher")
    subject = seed.subject(db_session, "Thi nghiem OCR")
    classroom = seed.classroom(db_session, "OCR-INIT-01", subject, teacher)

    client = client_factory((exam_ocr.router, "/api/exam/ocr"))
    response = client.post(
        "/api/exam/ocr/init-batch",
        json={
            "teacher_id": teacher.id,
            "class_id": classroom.id,
            "num_questions": 25,
            "student_id_columns": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["class_id"] == classroom.id
    assert payload["subject_name"] == subject.name
    assert payload["num_questions"] == 25
    assert payload["num_versions"] == 1
    assert payload["has_generated_docx"] is False
    assert payload["has_answer_key_xlsx"] is False
    assert payload["download_urls"]["docx"] is None
    assert payload["download_urls"]["answer_xlsx"] is None
    assert payload["download_urls"]["test_sheet_pdf"].endswith("/download/test-sheet")

    batch = db_session.query(models.TestOCRExamBatch).filter_by(id=payload["id"]).first()
    assert batch is not None
    assert batch.generated_docx_path is None
    assert batch.answer_key_json == []
    assert batch.omr_layout_json["question_count"] == 25
    assert batch.omr_layout_json["student_id_columns"] == 10


def test_omr_processor_detects_marked_exam_code_on_blank_sheet():
    layout = _build_omr_layout(question_count=20, student_id_columns=8, exam_code_columns=3)
    sheet_stream = _render_omr_sheet(version_code=None, question_count=20, layout=layout)
    image = Image.open(sheet_stream).convert("RGB")
    draw = ImageDraw.Draw(image)
    digit_rows = [int(value) for value in layout["digit_row_centers"]]
    digit_radius = int(layout["digit_bubble_radius"])
    for column_index, digit in enumerate("314"):
        center_x = int(layout["exam_code_x_centers"][column_index])
        _draw_bubble(draw, center_x, digit_rows[int(digit)], digit_radius, filled=True)
    image_np = np.array(image)

    result = OMRProcessorService(layout).process_page(image_np)

    assert result.exam_code == "314"
    assert len(result.answers) == 20
    assert result.student_id == ""
    assert result.status in {"missing_student_id", "ok"}


def test_omr_processor_tightens_student_name_crop():
    layout = _build_omr_layout(question_count=20, student_id_columns=8, exam_code_columns=3)
    width = int(layout["template_bounds"]["width"])
    height = int(layout["template_bounds"]["height"])
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    name_box = layout["name_box"]
    draw.rectangle(
        (
            name_box["x"],
            name_box["y"],
            name_box["x"] + name_box["w"],
            name_box["y"] + name_box["h"],
        ),
        outline="black",
        width=3,
    )
    draw.text((name_box["x"] + 120, name_box["y"] + 48), "NGUYEN VAN A", fill="black")

    result = OMRProcessorService(layout).process_page(np.array(image))

    assert result.name_crop.shape[1] < name_box["w"] - 120
    assert result.name_crop.shape[0] < name_box["h"] - 20


def test_generated_docx_places_omr_page_before_exam_content(db_session, seed):
    root = Path(__file__).resolve().parents[1]
    backend_dir = root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from services.ocr_exam_generator import OCRExamGeneratorService

    teacher = seed.user(db_session, "teacher.order@example.com", role="teacher", full_name="OCR Order Teacher")
    subject = seed.subject(db_session, "Machine Vision")
    classroom = seed.classroom(db_session, "VISION-01", subject, teacher)
    seed.document(db_session, subject, classroom, teacher, filename="vision.pdf")

    for index in range(1, 25):
        seed.question(
            db_session,
            subject,
            content=f"Vision question {index}?",
            options=[
                f"A. Correct {index}",
                f"B. Wrong 1-{index}",
                f"C. Wrong 2-{index}",
                f"D. Wrong 3-{index}",
            ],
            correct_answer="A",
            source_file="vision.pdf",
        )

    bundle = OCRExamGeneratorService(db_session).generate_exam_bundle(
        teacher_id=teacher.id,
        class_id=classroom.id,
        subject=subject.name,
        exam_type="trac nghiem",
        num_questions=20,
        num_versions=1,
        level="Trung binh",
        student_id_columns=8,
    )

    with zipfile.ZipFile(bundle.file_path, "r") as archive:
        xml_data = archive.read("word/document.xml")

    root_xml = ET.fromstring(xml_data)
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    }
    body = root_xml.find("w:body", ns)
    body_children = list(body)
    first_child = body_children[0]
    drawing_nodes = root_xml.findall(".//wp:inline", ns)
    exam_header_index = next(
        index
        for index, child in enumerate(body_children)
        if any((node.text or "").strip() == "ĐỀ THI TRẮC NGHIỆM" for node in child.findall(".//w:t", ns))
    )
    page_break_before_exam = [
        child
        for child in body_children[: exam_header_index + 1]
        if any(
            node.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type") == "page"
            for node in child.findall(".//w:br", ns)
        )
    ]

    assert first_child.tag.endswith("p")
    assert first_child.find(".//wp:inline", ns) is not None
    assert len(drawing_nodes) == 1
    assert page_break_before_exam == []


def _build_filled_omr_pdf_bytes(layout, version_code: str, student_id: str, answers: list[str]) -> bytes:
    stream = _render_omr_sheet(version_code=None, question_count=len(answers), layout=layout)
    image = Image.open(stream).convert("RGB")
    draw = ImageDraw.Draw(image)

    digit_radius = int(layout["digit_bubble_radius"])
    answer_radius = int(layout["answer_bubble_radius"])
    digit_rows = [int(value) for value in layout["digit_row_centers"]]
    student_id_x_centers = [int(value) for value in layout["student_id_x_centers"]]
    exam_code_x_centers = [int(value) for value in layout["exam_code_x_centers"]]
    answer_lookup = {}
    for column_meta in layout["answer_columns_meta"]:
        for row_meta in column_meta["question_rows"]:
            answer_lookup[int(row_meta["question_number"])] = (
                [int(value) for value in column_meta["option_centers"]],
                int(row_meta["y"]),
            )

    for column_index, digit in enumerate(student_id):
        if column_index >= len(student_id_x_centers) or not digit.isdigit():
            continue
        _draw_bubble(draw, student_id_x_centers[column_index], digit_rows[int(digit)], digit_radius, filled=True)

    for column_index, digit in enumerate(version_code):
        if column_index >= len(exam_code_x_centers) or not digit.isdigit():
            continue
        _draw_bubble(draw, exam_code_x_centers[column_index], digit_rows[int(digit)], digit_radius, filled=True)

    option_index_by_label = {"A": 0, "B": 1, "C": 2, "D": 3}
    for question_number, answer in enumerate(answers, start=1):
        option_centers, center_y = answer_lookup[question_number]
        option_index = option_index_by_label.get(str(answer or "").upper())
        if option_index is None:
            continue
        _draw_bubble(draw, option_centers[option_index], center_y, answer_radius, filled=True)

    pdf_buffer = io.BytesIO()
    image.save(pdf_buffer, format="PDF", resolution=200.0)
    return pdf_buffer.getvalue()



def _build_filled_omr_image_bytes(
    layout,
    version_code: str,
    student_id: str,
    answers: list[str],
    *,
    with_artifacts: bool = True,
    exam_code_fill: tuple[int, int, int] | None = None,
    student_name: str = "",
) -> bytes:
    stream = _render_omr_sheet(version_code=None, question_count=len(answers), layout=layout)
    image = Image.open(stream).convert("RGB")
    draw = ImageDraw.Draw(image)

    digit_radius = int(layout["digit_bubble_radius"])
    answer_radius = int(layout["answer_bubble_radius"])
    digit_rows = [int(value) for value in layout["digit_row_centers"]]
    student_id_x_centers = [int(value) for value in layout["student_id_x_centers"]]
    exam_code_x_centers = [int(value) for value in layout["exam_code_x_centers"]]
    answer_lookup = {}
    for column_meta in layout["answer_columns_meta"]:
        for row_meta in column_meta["question_rows"]:
            answer_lookup[int(row_meta["question_number"])] = (
                [int(value) for value in column_meta["option_centers"]],
                int(row_meta["y"]),
            )

    for column_index, digit in enumerate(student_id):
        if column_index >= len(student_id_x_centers) or not digit.isdigit():
            continue
        _draw_bubble(draw, student_id_x_centers[column_index], digit_rows[int(digit)], digit_radius, filled=True)

    for column_index, digit in enumerate(version_code):
        if column_index >= len(exam_code_x_centers) or not digit.isdigit():
            continue
        center_x = exam_code_x_centers[column_index]
        center_y = digit_rows[int(digit)]
        if exam_code_fill is None:
            _draw_bubble(draw, center_x, center_y, digit_radius, filled=True)
        else:
            draw.ellipse(
                (
                    center_x - digit_radius,
                    center_y - digit_radius,
                    center_x + digit_radius,
                    center_y + digit_radius,
                ),
                outline="black",
                width=3,
                fill=exam_code_fill,
            )

    option_index_by_label = {"A": 0, "B": 1, "C": 2, "D": 3}
    for question_number, answer in enumerate(answers, start=1):
        option_centers, center_y = answer_lookup[question_number]
        option_index = option_index_by_label.get(str(answer or "").upper())
        if option_index is None:
            continue
        _draw_bubble(draw, option_centers[option_index], center_y, answer_radius, filled=True)

    if student_name:
        name_box = layout["name_box"]
        draw.text((name_box["x"] + 80, name_box["y"] + 42), student_name, fill=(110, 110, 110))

    if with_artifacts:
        import cv2  # type: ignore

        image_np = np.array(image)
        height, width = image_np.shape[:2]
        canvas = np.full((height + 900, width + 900, 3), 206, dtype=np.uint8)
        offset_x, offset_y = 260, 220
        canvas[offset_y:offset_y + height, offset_x:offset_x + width] = image_np

        rotation_matrix = cv2.getRotationMatrix2D((canvas.shape[1] / 2.0, canvas.shape[0] / 2.0), -1.2, 1.0)
        rotated = cv2.warpAffine(canvas, rotation_matrix, (canvas.shape[1], canvas.shape[0]), borderValue=(195, 195, 195))

        image = Image.fromarray(rotated)
        image = ImageEnhance.Contrast(image).enhance(0.99)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.05))

    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    return image_buffer.getvalue()


def test_test_ocr_service_grades_generated_pdf(db_session, seed):
    teacher = seed.user(db_session, "teacher.grade@example.com", role="teacher", full_name="OCR Grade Teacher")
    subject = seed.subject(db_session, "Xu ly anh")
    classroom = seed.classroom(db_session, "VISION-GRADE-01", subject, teacher)
    seed.document(db_session, subject, classroom, teacher, filename="vision-grade.pdf")

    for index in range(1, 31):
        seed.question(
            db_session,
            subject,
            content=f"Image processing question {index}?",
            options=[
                f"A. Correct {index}",
                f"B. Wrong 1-{index}",
                f"C. Wrong 2-{index}",
                f"D. Wrong 3-{index}",
            ],
            correct_answer="A",
            source_file="vision-grade.pdf",
        )

    bundle = OCRExamGeneratorService(db_session).generate_exam_bundle(
        teacher_id=teacher.id,
        class_id=classroom.id,
        subject=subject.name,
        exam_type="trac nghiem",
        num_questions=20,
        num_versions=1,
        level="Trung binh",
        student_id_columns=8,
    )

    batch = db_session.query(models.TestOCRExamBatch).filter_by(id=bundle.batch.id).first()
    assert batch is not None
    version = batch.answer_key_json[0]
    expected_answers = list(version["answer_key"])
    expected_exam_code = str(version["exam_code"])
    expected_student_id = "12345678"
    answer_key_bytes = Path(bundle.answer_key_file_path).read_bytes()
    pdf_bytes = _build_filled_omr_pdf_bytes(
        layout=batch.omr_layout_json,
        version_code=expected_exam_code,
        student_id=expected_student_id,
        answers=expected_answers,
    )

    payload = OCRGradingService(db_session).grade_pdf(
        batch_id=batch.id,
        filename="filled-sheet.pdf",
        pdf_bytes=pdf_bytes,
        answer_key_bytes=answer_key_bytes,
    )

    assert payload["run_id"]
    assert len(payload["results"]) == 1
    result = payload["results"][0]
    assert result["detected_student_id"] == expected_student_id
    assert result["detected_exam_code"] == expected_exam_code
    assert "predicted_student_name" in result
    assert "predicted_student_name_engine" in result
    assert result["detected_answers"] == expected_answers
    assert result["correct_count"] == len(expected_answers)
    assert result["score"] == 10.0
    assert result["grading_status"] == "graded"


def test_grade_image_with_uploaded_excel_before_generate(client_factory, db_session, seed):
    teacher = seed.user(db_session, "teacher.image@example.com", role="teacher", full_name="OCR Image Teacher")
    subject = seed.subject(db_session, "Thi OCR bang anh")
    classroom = seed.classroom(db_session, "OCR-IMAGE-01", subject, teacher)

    client = client_factory((exam_ocr.router, "/api/exam/ocr"))
    init_response = client.post(
        "/api/exam/ocr/init-batch",
        json={
            "teacher_id": teacher.id,
            "class_id": classroom.id,
            "num_questions": 20,
            "student_id_columns": 8,
        },
    )
    assert init_response.status_code == 200
    batch_id = init_response.json()["id"]

    batch = db_session.query(models.TestOCRExamBatch).filter_by(id=batch_id).first()
    assert batch is not None

    answer_key_json = [
        {
            "version_index": 1,
            "exam_code": "314",
            "question_count": 20,
            "answer_key": ["A"] * 20,
        }
    ]
    answer_key_bytes = build_answer_key_workbook(answer_key_json)
    image_bytes = _build_filled_omr_image_bytes(
        layout=batch.omr_layout_json,
        version_code="314",
        student_id="12345678",
        answers=["A"] * 20,
        with_artifacts=False,
    )

    grade_response = client.post(
        "/api/exam/ocr/grade-pdf",
        data={"batch_id": str(batch_id)},
        files=[
            ("image_files", ("filled-sheet.png", image_bytes, "image/png")),
            (
                "answer_key_file",
                (
                    "answer-keys.xlsx",
                    answer_key_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
        ],
    )

    assert grade_response.status_code == 200
    payload = grade_response.json()
    assert payload["batch"]["id"] == batch_id
    assert payload["batch"]["has_generated_docx"] is False
    assert len(payload["results"]) == 1
    result = payload["results"][0]
    assert result["detected_student_id"] == "12345678"
    assert result["detected_exam_code"] == "314"
    assert result["detected_answers"] == ["A"] * 20
    assert result["correct_count"] == 20
    assert result["score"] == 10.0
    assert result["grading_status"] == "graded"

    stored_result = (
        db_session.query(models.TestOCRGradingResult)
        .filter_by(id=result["id"])
        .first()
    )
    assert stored_result is not None
    debug_payload = dict(stored_result.debug_json or {})
    assert debug_payload.get("submission_source_type") == "image"
    assert debug_payload.get("selected_image_candidate") in {"original", "scanner_enhanced", "original_enhanced"}
    assert "predicted_student_name_score" in debug_payload


def test_grade_canvas_photo_with_colored_exam_code_marks(db_session, seed):
    teacher = seed.user(db_session, "teacher.photo@example.com", role="teacher", full_name="OCR Photo Teacher")
    subject = seed.subject(db_session, "Thi OCR anh chup")
    classroom = seed.classroom(db_session, "OCR-PHOTO-01", subject, teacher)

    batch = OCRGradingService(db_session).create_grading_batch(
        teacher_id=teacher.id,
        class_id=classroom.id,
        num_questions=20,
        student_id_columns=8,
    )

    answer_key_json = [
        {
            "version_index": 1,
            "exam_code": "314",
            "question_count": 20,
            "answer_key": ["A"] * 20,
        }
    ]
    answer_key_bytes = build_answer_key_workbook(answer_key_json)
    image_bytes = _build_filled_omr_image_bytes(
        layout=batch.omr_layout_json,
        version_code="314",
        student_id="12345678",
        answers=["A"] * 20,
        with_artifacts=True,
        exam_code_fill=(96, 72, 178),
        student_name="NGUYEN VAN A",
    )

    payload = OCRGradingService(db_session).grade_submission(
        batch_id=batch.id,
        submissions=[("canvas-photo.png", image_bytes)],
        answer_key_bytes=answer_key_bytes,
    )

    assert payload["run_id"]
    assert len(payload["results"]) == 1
    result = payload["results"][0]
    assert result["detected_student_id"] == "12345678"
    assert result["detected_exam_code"] == "314"
    assert result["detected_answers"] == ["A"] * 20
    assert result["correct_count"] == 20
    assert result["score"] == 10.0
    assert result["grading_status"] == "graded"

    stored_result = db_session.query(models.TestOCRGradingResult).filter_by(id=result["id"]).first()
    assert stored_result is not None
    debug_payload = dict(stored_result.debug_json or {})
    assert debug_payload.get("submission_source_type") == "image"
    assert debug_payload.get("selected_binary_variant") in {
        "raw_otsu",
        "raw_adaptive",
        "raw_filled",
        "normalized_otsu",
        "normalized_adaptive",
        "normalized_filled",
        "clahe_otsu",
        "clahe_adaptive",
        "clahe_filled",
        "sharpened_otsu",
        "sharpened_adaptive",
        "sharpened_filled",
        "ink_relaxed",
        "ink_strict",
    }


def test_document_scanner_detects_paper_on_canvas_photo():
    layout = _build_omr_layout(question_count=20, student_id_columns=8, exam_code_columns=3)
    image_bytes = _build_filled_omr_image_bytes(
        layout=layout,
        version_code="314",
        student_id="12345678",
        answers=["A"] * 20,
        with_artifacts=True,
    )
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    result = DocumentScannerService().scan_document(np.array(image))

    assert result.status == "paper_detected"
    assert result.used_perspective_warp is True
    assert result.contour_area_ratio > 0.18
    assert result.debug_images["scanner_warped"].shape[:2] == (3508, 2480)


def test_document_scanner_falls_back_when_no_paper_detected():
    scanner = DocumentScannerService()
    image = np.full((900, 900, 3), 126, dtype=np.uint8)
    image[:, :, 1] = 118
    image[:, :, 2] = 132

    result = scanner.scan_document(image)

    assert result.status == "fallback_original"
    assert result.used_perspective_warp is False
    assert result.contour_area_ratio == 0.0
    assert result.scanned_image.shape == image.shape
    assert set(result.debug_images.keys()) == {"scanner_input", "scanner_contour", "scanner_warped", "scanner_enhanced"}


def test_update_edited_student_name_endpoint(client_factory, db_session, seed):
    teacher = seed.user(db_session, "teacher.rename@example.com", role="teacher", full_name="OCR Rename Teacher")
    subject = seed.subject(db_session, "Nhan dang ky tu")
    classroom = seed.classroom(db_session, "OCR-EDIT-01", subject, teacher)
    seed.document(db_session, subject, classroom, teacher, filename="ocr-edit.pdf")

    for index in range(1, 21):
        seed.question(
            db_session,
            subject,
            content=f"Character question {index}?",
            options=[
                f"A. Correct {index}",
                f"B. Wrong 1-{index}",
                f"C. Wrong 2-{index}",
                f"D. Wrong 3-{index}",
            ],
            correct_answer="A",
            source_file="ocr-edit.pdf",
        )

    bundle = OCRExamGeneratorService(db_session).generate_exam_bundle(
        teacher_id=teacher.id,
        class_id=classroom.id,
        subject=subject.name,
        exam_type="trac nghiem",
        num_questions=20,
        num_versions=1,
        level="Trung binh",
        student_id_columns=8,
    )
    batch = db_session.query(models.TestOCRExamBatch).filter_by(id=bundle.batch.id).first()
    assert batch is not None

    version = batch.answer_key_json[0]
    pdf_bytes = _build_filled_omr_pdf_bytes(
        layout=batch.omr_layout_json,
        version_code=str(version["exam_code"]),
        student_id="87654321",
        answers=list(version["answer_key"]),
    )
    payload = OCRGradingService(db_session).grade_pdf(
        batch_id=batch.id,
        filename="rename-sheet.pdf",
        pdf_bytes=pdf_bytes,
    )
    result_id = int(payload["results"][0]["id"])

    client = client_factory((exam_ocr.router, "/api/exam/ocr"))
    response = client.patch(
        f"/api/exam/ocr/results/{result_id}/student-name",
        json={"student_name": "Nguyen Van B"},
    )

    assert response.status_code == 200
    result_payload = response.json()
    assert result_payload["edited_student_name"] == "Nguyen Van B"
    assert result_payload["display_student_name"] == "Nguyen Van B"


def test_test_sheet_download_payload_has_single_page(db_session, seed):
    teacher = seed.user(db_session, "teacher.sheet@example.com", role="teacher", full_name="OCR Sheet Teacher")
    subject = seed.subject(db_session, "Nhap mon OCR")
    classroom = seed.classroom(db_session, "OCR-SHEET-01", subject, teacher)
    seed.document(db_session, subject, classroom, teacher, filename="ocr-sheet.pdf")

    for index in range(1, 26):
        seed.question(
            db_session,
            subject,
            content=f"OCR sheet question {index}?",
            options=[
                f"A. Correct {index}",
                f"B. Wrong 1-{index}",
                f"C. Wrong 2-{index}",
                f"D. Wrong 3-{index}",
            ],
            correct_answer="A",
            source_file="ocr-sheet.pdf",
        )

    bundle = OCRExamGeneratorService(db_session).generate_exam_bundle(
        teacher_id=teacher.id,
        class_id=classroom.id,
        subject=subject.name,
        exam_type="trac nghiem",
        num_questions=20,
        num_versions=2,
        level="Trung binh",
        student_id_columns=8,
    )
    batch = db_session.query(models.TestOCRExamBatch).filter_by(id=bundle.batch.id).first()
    assert batch is not None

    pdf_bytes = OCRGradingService(db_session).build_test_sheet_pdf(batch)
    page_images = PDFProcessorService().render_pdf_to_images(pdf_bytes)

    assert len(page_images) == 1
