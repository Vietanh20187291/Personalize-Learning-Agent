from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class StudentNameOCRResult:
    text: str
    engine: str
    score: float = 0.0


class StudentNameOCRService:
    _easyocr_reader = None

    def _find_tesseract_cmd(self) -> Optional[str]:
        command = shutil.which("tesseract")
        if command:
            return command

        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if Path(candidate).exists():
                return candidate
        return None

    def _strip_accents(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", (value or "").replace("đ", "d").replace("Đ", "D"))
        return "".join(char for char in normalized if not unicodedata.combining(char))

    def _cleanup_name(self, text: str) -> str:
        normalized = " ".join(str(text or "").replace("\n", " ").split()).strip()
        if not normalized:
            return ""

        normalized = re.sub(r"(?i)\bho\s*(?:va)?\s*ten\b\s*:?", " ", normalized)
        normalized = re.sub(r"(?i)\b(vi[eế]t chu[\w\s]*in hoa)\b\s*:?", " ", normalized)
        normalized = re.sub(r"(?i)\bmon hoc\b.*$", " ", normalized)
        normalized = re.sub(r"(?i)\bmssv\b.*$", " ", normalized)
        normalized = re.sub(r"(?i)\blop\b.*$", " ", normalized)
        normalized = re.sub(r"[^0-9A-Za-zÀ-ỹà-ỹ\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        if not normalized:
            return ""

        accentless = self._strip_accents(normalized).upper()
        placeholder_tokens = {
            "HO",
            "VA",
            "TEN",
            "SINH",
            "VIEN",
            "VIET",
            "CHU",
            "IN",
            "HOA",
        }
        if all(token in placeholder_tokens for token in accentless.split()):
            return ""

        return normalized

    def _score_name(self, text: str) -> float:
        cleaned = self._cleanup_name(text)
        if not cleaned:
            return 0.0

        tokens = [token for token in cleaned.split() if token]
        accentless = self._strip_accents(cleaned).upper()
        alpha_count = sum(char.isalpha() for char in accentless)
        digit_count = sum(char.isdigit() for char in accentless)
        upper_ratio = sum(char.isupper() for char in accentless if char.isalpha()) / float(alpha_count or 1)
        token_bonus = min(len(tokens), 5) * 0.22
        length_bonus = min(len(cleaned), 32) / 32.0
        digit_penalty = min(digit_count, 6) * 0.35
        short_penalty = 0.8 if len(cleaned) < 4 else 0.0
        return round(max(0.0, token_bonus + length_bonus + upper_ratio - digit_penalty - short_penalty), 6)

    def _cv2(self):
        try:
            import cv2  # type: ignore
        except Exception:
            return None
        return cv2

    def _extract_text_region(self, image: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        if cv2 is None or image.size == 0:
            return image

        working = image.copy()
        if working.ndim == 3:
            gray = cv2.cvtColor(working, cv2.COLOR_RGB2GRAY)
        else:
            gray = working

        normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        blurred = cv2.GaussianBlur(normalized, (3, 3), 0)
        binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(image.shape[1] // 6, 24), 1))
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(image.shape[0] // 2, 16)))
        binary = cv2.subtract(binary, cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel))
        binary = cv2.subtract(binary, cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), dtype=np.uint8))
        binary = cv2.dilate(binary, np.ones((3, 3), dtype=np.uint8), iterations=1)

        points = cv2.findNonZero(binary)
        if points is None:
            return image

        x, y, w, h = cv2.boundingRect(points)
        pad_x = max(18, int(w * 0.08))
        pad_y = max(12, int(h * 0.28))
        x0 = max(x - pad_x, 0)
        y0 = max(y - pad_y, 0)
        x1 = min(x + w + pad_x, image.shape[1])
        y1 = min(y + h + pad_y, image.shape[0])
        extracted = image[y0:y1, x0:x1].copy()
        return extracted if extracted.size else image

    def _candidate_crops(self, image: np.ndarray) -> list[np.ndarray]:
        if image.size == 0:
            return [image]

        crops: list[np.ndarray] = []
        seen_shapes: set[tuple[int, int, int]] = set()

        def add(candidate: np.ndarray) -> None:
            if candidate.size == 0:
                return
            shape_key = tuple(int(value) for value in candidate.shape)
            if shape_key in seen_shapes and len(seen_shapes) > 2:
                return
            seen_shapes.add(shape_key)
            crops.append(candidate)

        add(image)
        add(self._extract_text_region(image))

        height, width = image.shape[:2]
        for shift in (-0.05, 0.05):
            x0 = max(int(width * max(0.0, 0.02 + shift)), 0)
            x1 = min(int(width * min(1.0, 0.98 + shift)), width)
            if x1 - x0 > max(48, width // 3):
                add(self._extract_text_region(image[:, x0:x1]))

        for top_ratio, bottom_ratio in ((0.08, 0.92), (0.18, 0.88)):
            y0 = int(height * top_ratio)
            y1 = int(height * bottom_ratio)
            if y1 - y0 > max(24, height // 3):
                add(self._extract_text_region(image[y0:y1, :]))

        return crops or [image]

    def _preprocess_variants(self, image: np.ndarray) -> list[np.ndarray]:
        cv2 = self._cv2()
        if cv2 is None:
            return [image]

        working = image.copy()
        if working.ndim == 3:
            gray = cv2.cvtColor(working, cv2.COLOR_RGB2GRAY)
        else:
            gray = working

        normalized = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
        gray = cv2.GaussianBlur(normalized, (3, 3), 0)
        gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        scaled = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(scaled)
        sharpened = cv2.addWeighted(clahe, 1.6, cv2.GaussianBlur(clahe, (0, 0), 1.2), -0.6, 0)
        otsu = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        adaptive = cv2.adaptiveThreshold(
            sharpened,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            9,
        )
        inverse = cv2.bitwise_not(
            cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        )
        contrast = cv2.equalizeHist(sharpened)
        return [scaled, clahe, sharpened, otsu, adaptive, inverse, contrast]

    def _recognize_with_easyocr(self, image: np.ndarray) -> Optional[StudentNameOCRResult]:
        try:
            import easyocr  # type: ignore
        except Exception:
            return None

        try:
            if self._easyocr_reader is None:
                self.__class__._easyocr_reader = easyocr.Reader(["vi", "en"], gpu=False, verbose=False)
            reader = self.__class__._easyocr_reader
        except Exception:
            return None

        best_result: Optional[StudentNameOCRResult] = None
        for crop in self._candidate_crops(image):
            for processed in self._preprocess_variants(crop):
                try:
                    lines = reader.readtext(processed, detail=1, paragraph=True)
                except Exception:
                    continue
                if not lines:
                    continue

                if isinstance(lines[0], (list, tuple)) and len(lines[0]) >= 3:
                    text = " ".join(str(item[1] or "").strip() for item in lines if len(item) >= 2)
                    confidence = float(
                        sum(float(item[2] or 0.0) for item in lines if len(item) >= 3) / float(len(lines) or 1)
                    )
                else:
                    text = " ".join(str(item or "").strip() for item in lines)
                    confidence = 0.0

                cleaned = self._cleanup_name(text)
                if not cleaned:
                    continue
                score = self._score_name(cleaned) + max(confidence, 0.0)
                candidate = StudentNameOCRResult(text=cleaned, engine="easyocr:vi+en", score=score)
                if best_result is None or candidate.score > best_result.score:
                    best_result = candidate
        return best_result

    def _tesseract_candidate(self, pytesseract, processed: np.ndarray, *, lang: str, config: str) -> Optional[StudentNameOCRResult]:
        try:
            data = pytesseract.image_to_data(
                processed,
                lang=lang,
                config=config,
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            return None

        tokens = []
        confidences = []
        for token, conf in zip(data.get("text", []), data.get("conf", [])):
            token_text = str(token or "").strip()
            if not token_text:
                continue
            try:
                confidence = float(conf)
            except Exception:
                confidence = -1.0
            if confidence >= 0:
                confidences.append(confidence)
            tokens.append(token_text)

        text = " ".join(tokens).strip()
        if not text:
            try:
                text = pytesseract.image_to_string(processed, lang=lang, config=config)
            except Exception:
                return None

        cleaned = self._cleanup_name(text)
        if not cleaned:
            return None

        mean_confidence = (sum(confidences) / (100.0 * len(confidences))) if confidences else 0.0
        return StudentNameOCRResult(
            text=cleaned,
            engine=f"tesseract:{lang}",
            score=self._score_name(cleaned) + max(mean_confidence, 0.0),
        )

    def _recognize_with_tesseract(self, image: np.ndarray, fast: bool = False) -> Optional[StudentNameOCRResult]:
        try:
            import pytesseract  # type: ignore
        except Exception:
            return None

        tesseract_cmd = self._find_tesseract_cmd()
        if tesseract_cmd is None:
            return None
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        # fast=True: dùng cho chấm thi OCR (tên chỉ để hiển thị, không ảnh hưởng điểm).
        # Giảm số tổ hợp crop×variant×config từ ~126 xuống ~2-3 lần gọi Tesseract.
        if fast:
            configs = [("vie+eng", "--oem 1 --psm 7 -c preserve_interword_spaces=1")]
            crops = self._candidate_crops(image)[:1]
            best_result: Optional[StudentNameOCRResult] = None
            for crop in crops:
                processed = self._preprocess_variants(crop)[1] if len(self._preprocess_variants(crop)) > 1 else crop
                for lang, config in configs:
                    candidate = self._tesseract_candidate(pytesseract, processed, lang=lang, config=config)
                    if candidate is None:
                        continue
                    if best_result is None or candidate.score > best_result.score:
                        best_result = candidate
            return best_result

        configs = [
            ("vie+eng", "--oem 1 --psm 7 -c preserve_interword_spaces=1"),
            ("vie+eng", "--oem 1 --psm 6 -c preserve_interword_spaces=1"),
            ("eng", "--oem 1 --psm 7 -c preserve_interword_spaces=1"),
        ]
        best_result = None

        for crop in self._candidate_crops(image):
            for processed in self._preprocess_variants(crop):
                for lang, config in configs:
                    candidate = self._tesseract_candidate(pytesseract, processed, lang=lang, config=config)
                    if candidate is None:
                        continue
                    if best_result is None or candidate.score > best_result.score:
                        best_result = candidate
        return best_result

    def recognize(self, image: np.ndarray, fallback_image: Optional[np.ndarray] = None, fast: bool = False) -> StudentNameOCRResult:
        # fast=True (mặc định khi chấm thi): chỉ nhận diện nhanh tên để hiển thị.
        images = [candidate for candidate in (image, fallback_image) if isinstance(candidate, np.ndarray) and candidate.size]
        best_result: Optional[StudentNameOCRResult] = None
        for source_image in images or [image]:
            tesseract_result = self._recognize_with_tesseract(source_image, fast=fast)
            if tesseract_result is None:
                continue
            if best_result is None or tesseract_result.score > best_result.score:
                best_result = tesseract_result
            # Trong chế độ fast: bỏ qua EasyOCR (nặng) — tên chỉ để hiển thị.
            if not fast:
                easyocr_result = self._recognize_with_easyocr(source_image)
                if easyocr_result is not None and (best_result is None or easyocr_result.score > best_result.score):
                    best_result = easyocr_result
        if best_result is not None:
            return best_result
        return StudentNameOCRResult(text="", engine="", score=0.0)
