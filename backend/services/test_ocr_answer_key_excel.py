from __future__ import annotations

import io
import unicodedata
import zipfile
from datetime import datetime
from typing import Dict, List, Tuple
from xml.etree import ElementTree as ET


QUESTION_NUMBER_HEADER_ALIASES = {
    "question_number",
    "stt",
    "so_cau",
    "socau",
    "cau_so",
    "causo",
    "so_thu_tu",
}
CORRECT_ANSWER_HEADER_ALIASES = {
    "correct_answer",
    "dap_an",
    "dapan",
    "dap_an_dung",
    "dapandung",
    "lua_chon_dung",
}
EXAM_CODE_HEADER_ALIASES = {
    "exam_code",
    "ma_de",
    "made",
    "de_so",
}


def _safe_sheet_name(value: str, fallback_index: int) -> str:
    cleaned = str(value or "").strip() or f"Sheet{fallback_index}"
    cleaned = cleaned.translate(str.maketrans({char: "_" for char in '[]:*?/\\'}))
    return cleaned[:31] or f"Sheet{fallback_index}"


def _normalize_header(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    safe = stripped.replace("đ", "d").replace("Đ", "D")
    return "_".join(part for part in safe.replace("-", " ").replace(":", " ").split())


def _excel_column_index(column_name: str) -> int:
    index = 0
    for char in str(column_name or "").upper():
        if "A" <= char <= "Z":
            index = (index * 26) + (ord(char) - 64)
    return index


def build_answer_key_workbook(answer_key_json: List[Dict[str, object]]) -> bytes:
    try:
        import xlsxwriter  # type: ignore
    except Exception as exc:
        raise RuntimeError("Thiếu thư viện `xlsxwriter` để tạo file đáp án Excel.") from exc

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    workbook.set_properties(
        {
            "title": "Bảng đáp án trắc nghiệm OCR",
            "subject": "Biểu mẫu đáp án chấm trắc nghiệm tự động",
            "author": "Nova Teacher Assessment Suite",
            "company": "Nova Teacher Assessment Suite",
            "comments": "Biểu mẫu đáp án dành cho chấm trắc nghiệm OCR",
            "created": datetime.utcnow(),
        }
    )

    title_format = workbook.add_format(
        {
            "bold": True,
            "font_name": "Times New Roman",
            "font_size": 16,
            "font_color": "#FFFFFF",
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#1F4E78",
        }
    )
    section_format = workbook.add_format(
        {
            "bold": True,
            "font_name": "Times New Roman",
            "font_size": 12,
            "font_color": "#1F1F1F",
            "bg_color": "#D9EAF7",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        }
    )
    label_format = workbook.add_format(
        {
            "bold": True,
            "font_name": "Times New Roman",
            "font_size": 11,
            "bg_color": "#E2F0D9",
            "border": 1,
            "valign": "vcenter",
        }
    )
    value_format = workbook.add_format(
        {
            "font_name": "Times New Roman",
            "font_size": 11,
            "border": 1,
            "valign": "vcenter",
        }
    )
    instruction_format = workbook.add_format(
        {
            "font_name": "Times New Roman",
            "font_size": 11,
            "text_wrap": True,
            "valign": "top",
            "border": 1,
        }
    )
    answer_format = workbook.add_format(
        {
            "font_name": "Times New Roman",
            "font_size": 11,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        }
    )
    note_format = workbook.add_format(
        {
            "font_name": "Times New Roman",
            "font_size": 10,
            "italic": True,
            "font_color": "#555555",
        }
    )

    guide_sheet = workbook.add_worksheet("HUONG_DAN")
    guide_sheet.hide_gridlines(2)
    guide_sheet.set_default_row(22)
    guide_sheet.set_column("A:A", 5)
    guide_sheet.set_column("B:B", 28)
    guide_sheet.set_column("C:C", 62)
    guide_sheet.merge_range("A1:C1", "BẢNG ĐÁP ÁN CHẤM TRẮC NGHIỆM OCR", title_format)
    guide_sheet.write("A3", "1", section_format)
    guide_sheet.write("B3", "Mục", section_format)
    guide_sheet.write("C3", "Hướng dẫn sử dụng", section_format)
    guide_sheet.write("A4", "1", value_format)
    guide_sheet.write("B4", "Nhập đáp án", value_format)
    guide_sheet.write(
        "C4",
        "Chỉ nhập một trong bốn lựa chọn A, B, C hoặc D tại cột 'Đáp án đúng'.",
        instruction_format,
    )
    guide_sheet.write("A5", "2", value_format)
    guide_sheet.write("B5", "Giữ nguyên mã đề", value_format)
    guide_sheet.write(
        "C5",
        "Không đổi mã đề trong tên sheet hoặc ô thông tin 'Mã đề' để hệ thống đối chiếu chính xác khi chấm.",
        instruction_format,
    )
    guide_sheet.write("A6", "3", value_format)
    guide_sheet.write("B6", "Bỏ qua sheet hướng dẫn", value_format)
    guide_sheet.write(
        "C6",
        "Hệ thống chỉ đọc các sheet có bảng đáp án hợp lệ. Sheet hướng dẫn này sẽ tự động được bỏ qua.",
        instruction_format,
    )
    guide_sheet.write("A8", "Ghi chú", label_format)
    guide_sheet.merge_range(
        "B8:C8",
        "Biểu mẫu này dành cho luồng chấm trắc nghiệm OCR. Nên giữ nguyên cấu trúc cột để tránh lỗi khi tải lên.",
        note_format,
    )

    for index, version in enumerate(answer_key_json or [], start=1):
        exam_code = str(version.get("exam_code", "") or "").strip() or str(index)
        answers = [str(item or "").strip().upper() for item in list(version.get("answer_key", []) or [])]

        sheet = workbook.add_worksheet(_safe_sheet_name(exam_code, index))
        sheet.hide_gridlines(2)
        sheet.freeze_panes(6, 0)
        sheet.set_default_row(22)
        sheet.set_column("A:A", 10)
        sheet.set_column("B:B", 18)
        sheet.set_column("C:C", 26)
        sheet.set_column("D:D", 18)

        sheet.merge_range("A1:D1", f"BẢNG ĐÁP ÁN MÃ ĐỀ {exam_code}", title_format)
        sheet.merge_range("A2:D2", f"PHIẾU ĐÁP ÁN MÃ ĐỀ {exam_code} - DÙNG CHO CHẤM TRẮC NGHIỆM OCR", note_format)
        sheet.write("A3", "Mã đề", label_format)
        sheet.write("B3", exam_code, value_format)
        sheet.write("C3", "Số câu", label_format)
        sheet.write("D3", len(answers), value_format)
        sheet.write("A4", "Ngày tạo", label_format)
        sheet.write("B4", datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC"), value_format)
        sheet.write("C4", "Lưu ý", label_format)
        sheet.write("D4", "Chỉ dùng A/B/C/D", value_format)

        table_rows = [[question_number, answer, "", exam_code] for question_number, answer in enumerate(answers, start=1)]
        last_row = max(6, 5 + len(table_rows))
        sheet.add_table(
            5,
            0,
            last_row,
            3,
            {
                "style": "Table Style Medium 2",
                "data": table_rows or [[None, None, None, exam_code]],
                "columns": [
                    {"header": "STT", "format": answer_format},
                    {"header": "Đáp án đúng", "format": answer_format},
                    {"header": "Ghi chú", "format": value_format},
                    {"header": "Mã đề", "format": answer_format},
                ],
            },
        )
        if table_rows:
            sheet.data_validation(
                6,
                1,
                5 + len(table_rows),
                1,
                {
                    "validate": "list",
                    "source": ["A", "B", "C", "D"],
                    "input_title": "Đáp án hợp lệ",
                    "input_message": "Chỉ nhập A, B, C hoặc D.",
                    "error_title": "Dữ liệu không hợp lệ",
                    "error_message": "Cột đáp án chỉ chấp nhận A, B, C hoặc D.",
                },
            )
        sheet.write(
            last_row + 2,
            0,
            "Mẹo: nếu cần chỉnh sửa, chỉ cập nhật cột 'Đáp án đúng'. Không nên thay đổi tên cột hoặc xóa cột 'Mã đề'.",
            note_format,
        )

    workbook.close()
    buffer.seek(0)
    return buffer.getvalue()


def _read_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        xml_data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(xml_data)
    values: List[str] = []
    for string_item in root.findall("s:si", namespace):
        values.append("".join(node.text or "" for node in string_item.findall(".//s:t", namespace)))
    return values


def _cell_text(cell: ET.Element, shared_strings: List[str], namespace: Dict[str, str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//s:t", namespace))

    value_node = cell.find("s:v", namespace)
    raw_value = value_node.text.strip() if value_node is not None and value_node.text else ""
    if cell_type == "s" and raw_value.isdigit():
        index = int(raw_value)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    return raw_value


def parse_answer_key_workbook(xlsx_bytes: bytes) -> Dict[str, List[str]]:
    namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_namespace = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r") as archive:
        shared_strings = _read_shared_strings(archive)
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        workbook_rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relation_targets = {
            relation.attrib.get("Id", ""): relation.attrib.get("Target", "")
            for relation in workbook_rels_xml.findall("r:Relationship", rel_namespace)
        }
        sheet_entries: List[Tuple[str, str]] = []
        for sheet_node in workbook_xml.findall(".//s:sheets/s:sheet", namespace):
            sheet_name = str(sheet_node.attrib.get("name", "") or "").strip()
            relation_id = sheet_node.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
            target = relation_targets.get(relation_id, "")
            if sheet_name and target:
                sheet_entries.append((sheet_name, f"xl/{target}"))

        if not sheet_entries:
            raise ValueError("File Excel khong co worksheet hop le.")

        answers_by_code: Dict[str, Dict[int, str]] = {}
        valid_sheet_count = 0
        for sheet_name, sheet_path in sheet_entries:
            sheet_root = ET.fromstring(archive.read(sheet_path))
            header_map: Dict[str, str] = {}
            rows: List[Dict[str, str]] = []
            detected_exam_code = sheet_name

            for row in sheet_root.findall(".//s:sheetData/s:row", namespace):
                cell_map: Dict[str, str] = {}
                for cell in row.findall("s:c", namespace):
                    ref = cell.attrib.get("r", "")
                    column_name = "".join(ch for ch in ref if ch.isalpha())
                    cell_map[column_name] = _cell_text(cell, shared_strings, namespace)

                if not cell_map:
                    continue

                ordered_cells = sorted(cell_map.items(), key=lambda item: _excel_column_index(item[0]))
                if not header_map:
                    for cell_index, (_, value) in enumerate(ordered_cells[:-1]):
                        normalized_header = _normalize_header(value)
                        if normalized_header in EXAM_CODE_HEADER_ALIASES:
                            candidate_exam_code = str(ordered_cells[cell_index + 1][1] or "").strip()
                            if candidate_exam_code:
                                detected_exam_code = candidate_exam_code

                    question_column = None
                    answer_column = None
                    for column_name, value in ordered_cells:
                        normalized_header = _normalize_header(value)
                        if normalized_header in QUESTION_NUMBER_HEADER_ALIASES:
                            question_column = column_name
                        elif normalized_header in CORRECT_ANSWER_HEADER_ALIASES:
                            answer_column = column_name
                    if question_column and answer_column:
                        header_map[question_column] = "question_number"
                        header_map[answer_column] = "correct_answer"
                        valid_sheet_count += 1
                    continue

                rows.append({header_map.get(column_name, column_name): value for column_name, value in cell_map.items()})

            if not header_map:
                continue

            for row in rows:
                question_number_raw = str(row.get("question_number", "") or "").strip()
                answer = str(row.get("correct_answer", "") or "").strip().upper()
                if not question_number_raw or answer not in {"A", "B", "C", "D"}:
                    continue
                try:
                    question_number = int(float(question_number_raw))
                except ValueError:
                    continue
                if question_number < 1:
                    continue
                answers_by_code.setdefault(detected_exam_code, {})[question_number] = answer

        if valid_sheet_count == 0:
            raise ValueError("File Excel khong tim thay bang dap an hop le.")

    normalized: Dict[str, List[str]] = {}
    for exam_code, answer_map in answers_by_code.items():
        max_question = max(answer_map.keys(), default=0)
        normalized[exam_code] = [answer_map.get(index, "") for index in range(1, max_question + 1)]
    return normalized
