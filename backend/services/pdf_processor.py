from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import numpy as np
from PIL import Image, ImageOps

from services.document_scanner import DocumentScannerService


@dataclass
class LoadedSubmissionImage:
    image: np.ndarray
    source_type: str
    debug: Dict[str, object] = field(default_factory=dict)
    debug_images: Dict[str, np.ndarray] = field(default_factory=dict)
    candidate_images: List[tuple[str, np.ndarray]] = field(default_factory=list)


class PDFProcessorService:
    SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

    def __init__(self):
        self.document_scanner = DocumentScannerService()

    def render_pdf_to_images(self, pdf_bytes: bytes, dpi: int = 200) -> List[np.ndarray]:
        try:
            import fitz  # type: ignore
        except Exception as exc:
            raise RuntimeError("Thiếu thư viện PyMuPDF (`fitz`). Hãy cài `PyMuPDF` để dùng chức năng OCR PDF.") from exc

        images: List[np.ndarray] = []
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            scale = max(dpi / 72.0, 1.0)
            matrix = fitz.Matrix(scale, scale)
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
                images.append(np.array(image))
        finally:
            document.close()
        return images

    def load_image_bytes(self, image_bytes: bytes) -> LoadedSubmissionImage:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            image = ImageOps.exif_transpose(image).convert("RGB")
        except Exception as exc:
            raise ValueError("Không đọc được file ảnh tải lên cho luồng chấm OMR.") from exc

        image_np = np.array(image)
        scan_result = self.document_scanner.scan_document(image_np)
        candidate_images: List[tuple[str, np.ndarray]] = []
        scanner_enhanced = scan_result.debug_images.get("scanner_enhanced")
        if scan_result.status == "paper_detected":
            candidate_images.append(("scanner_warped", scan_result.scanned_image))
        if isinstance(scanner_enhanced, np.ndarray) and scanner_enhanced.size:
            candidate_images.append(("scanner_enhanced", scanner_enhanced))
        candidate_images.append(("original", image_np))
        if scan_result.status == "fallback_original" and isinstance(scanner_enhanced, np.ndarray) and scanner_enhanced.size:
            candidate_images.append(("original_enhanced", scanner_enhanced))

        return LoadedSubmissionImage(
            image=scan_result.scanned_image if scan_result.status == "paper_detected" else image_np,
            source_type="image",
            debug=scan_result.debug,
            debug_images=scan_result.debug_images,
            candidate_images=candidate_images,
        )

    def load_submission_images(self, filename: str, payload: bytes) -> List[LoadedSubmissionImage]:
        normalized_name = (filename or "").strip().lower()
        if normalized_name.endswith(".pdf"):
            return [LoadedSubmissionImage(image=image, source_type="pdf") for image in self.render_pdf_to_images(payload)]

        suffix = Path(normalized_name).suffix.lower()
        if suffix in self.SUPPORTED_IMAGE_SUFFIXES or not suffix:
            return [self.load_image_bytes(payload)]

        raise ValueError("Chỉ hỗ trợ file PDF hoặc ảnh PNG/JPG/JPEG/BMP/TIFF/WEBP cho luồng chấm OMR.")

    def save_pdf(self, file_path: Path, pdf_bytes: bytes) -> None:
        file_path.write_bytes(pdf_bytes)
