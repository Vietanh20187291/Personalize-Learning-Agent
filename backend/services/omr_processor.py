from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class OMRProcessResult:
    aligned_image: np.ndarray
    name_crop: np.ndarray
    name_box_crop: np.ndarray
    student_id: str
    exam_code: str
    answers: List[str]
    status: str
    debug: Dict[str, object]


class OMRProcessorService:
    def __init__(self, layout: Dict[str, object]):
        self.layout = layout

    def _cv2(self):
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("Thiếu thư viện OpenCV (`cv2`). Hãy cài `opencv-python-headless` để dùng chức năng OMR.") from exc
        return cv2

    def _marker_centers(self) -> Dict[str, Tuple[float, float]]:
        marker_cfg = self.layout["alignment_markers"]
        template = self.layout["template_bounds"]
        size = float(marker_cfg["size"])
        margin = float(marker_cfg["margin"])
        width = float(template["width"])
        height = float(template["height"])
        half = size / 2.0
        return {
            "top_left": (margin + half, margin + half),
            "top_right": (width - margin - half, margin + half),
            "bottom_left": (margin + half, height - margin - half),
            "bottom_right": (width - margin - half, height - margin - half),
        }

    def _normalize_illumination(self, gray: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        background = cv2.GaussianBlur(gray, (0, 0), 21)
        normalized = cv2.divide(gray, background, scale=255)
        return cv2.normalize(normalized, None, 0, 255, cv2.NORM_MINMAX)

    def _apply_clahe(self, gray: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _apply_unsharp_mask(self, gray: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        blurred = cv2.GaussianBlur(gray, (0, 0), 1.4)
        sharpened = cv2.addWeighted(gray, 1.6, blurred, -0.6, 0)
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    def _gray_variants(self, image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        cv2 = self._cv2()
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image.copy()
        normalized = self._normalize_illumination(gray)
        clahe = self._apply_clahe(normalized)
        sharpened = self._apply_unsharp_mask(clahe)
        return [
            ("raw", gray),
            ("normalized", normalized),
            ("clahe", clahe),
            ("sharpened", sharpened),
        ]

    def _prepare_binary_from_gray(self, gray: np.ndarray, strategy: str = "otsu") -> np.ndarray:
        cv2 = self._cv2()
        if strategy == "adaptive":
            denoised = cv2.medianBlur(gray, 5)
            binary = cv2.adaptiveThreshold(
                denoised,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,
                31,
                8,
            )
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), dtype=np.uint8))
            return binary

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        if strategy == "filled":
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8), iterations=1)
            binary = cv2.dilate(binary, np.ones((2, 2), dtype=np.uint8), iterations=1)
        return binary

    def _prepare_binary(self, image: np.ndarray, strategy: str = "otsu") -> Tuple[np.ndarray, np.ndarray]:
        gray = self._gray_variants(image)[0][1]
        binary = self._prepare_binary_from_gray(gray, strategy=strategy)
        return gray, binary

    def _find_marker_center(self, binary: np.ndarray, region: Tuple[int, int, int, int]) -> Optional[Tuple[float, float]]:
        cv2 = self._cv2()
        x0, y0, x1, y1 = region
        window = binary[y0:y1, x0:x1]
        contours, _ = cv2.findContours(window, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best_box = None
        best_area = 0.0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 500:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            ratio = w / float(h or 1)
            if ratio < 0.65 or ratio > 1.35:
                continue
            if area > best_area:
                best_area = area
                best_box = (x, y, w, h)
        if best_box is None:
            return None
        x, y, w, h = best_box
        return (x0 + x + (w / 2.0), y0 + y + (h / 2.0))

    def align_page(self, image: np.ndarray) -> Tuple[np.ndarray, Dict[str, object]]:
        cv2 = self._cv2()
        template = self.layout["template_bounds"]
        target_width = int(template["width"])
        target_height = int(template["height"])

        probe_variants = self._gray_variants(image)
        height, width = probe_variants[0][1].shape[:2]
        window_w = max(int(width * 0.24), 180)
        window_h = max(int(height * 0.24), 180)

        best_partial: Dict[str, object] | None = None
        for variant_name, gray in probe_variants:
            for strategy in ("otsu", "adaptive", "filled"):
                binary = self._prepare_binary_from_gray(gray, strategy=strategy)
                found = {
                    "top_left": self._find_marker_center(binary, (0, 0, window_w, window_h)),
                    "top_right": self._find_marker_center(binary, (width - window_w, 0, width, window_h)),
                    "bottom_left": self._find_marker_center(binary, (0, height - window_h, window_w, height)),
                    "bottom_right": self._find_marker_center(binary, (width - window_w, height - window_h, width, height)),
                }
                found_count = sum(1 for value in found.values() if value is not None)
                if best_partial is None or found_count > int(best_partial.get("found_count", 0)):
                    best_partial = {
                        "variant": variant_name,
                        "strategy": strategy,
                        "marker_centers": found,
                        "found_count": found_count,
                    }

                if all(found.values()):
                    src = np.array(
                        [
                            found["top_left"],
                            found["top_right"],
                            found["bottom_left"],
                            found["bottom_right"],
                        ],
                        dtype=np.float32,
                    )
                    expected = self._marker_centers()
                    dst = np.array(
                        [
                            expected["top_left"],
                            expected["top_right"],
                            expected["bottom_left"],
                            expected["bottom_right"],
                        ],
                        dtype=np.float32,
                    )
                    matrix = cv2.getPerspectiveTransform(src, dst)
                    aligned = cv2.warpPerspective(image, matrix, (target_width, target_height), borderValue=(255, 255, 255))
                    debug = {
                        "marker_centers": found,
                        "alignment": "perspective",
                        "alignment_variant": variant_name,
                        "alignment_strategy": strategy,
                    }
                    return aligned, debug

        aligned = cv2.resize(image, (target_width, target_height))
        debug = {
            "marker_centers": dict(best_partial.get("marker_centers", {})) if best_partial else {},
            "alignment": "resized_fallback",
            "alignment_variant": best_partial.get("variant") if best_partial else "raw",
            "alignment_strategy": best_partial.get("strategy") if best_partial else "otsu",
            "marker_count": int(best_partial.get("found_count", 0)) if best_partial else 0,
        }
        return aligned, debug

    def _crop_rect(self, image: np.ndarray, rect: Dict[str, int]) -> np.ndarray:
        x = int(rect["x"])
        y = int(rect["y"])
        w = int(rect["w"])
        h = int(rect["h"])
        return image[y:y + h, x:x + w].copy()

    def _crop_name_box_inner(self, image: np.ndarray, rect: Dict[str, int]) -> np.ndarray:
        name_crop = self._crop_rect(image, rect)
        if name_crop.size == 0:
            return name_crop

        height, width = name_crop.shape[:2]
        margin_x = min(max(24, int(width * 0.035)), max(width // 3, 1))
        margin_y = min(max(18, int(height * 0.18)), max(height // 3, 1))
        inner_left = min(margin_x, max(width - 1, 0))
        inner_top = min(margin_y, max(height - 1, 0))
        inner_right = max(width - margin_x, inner_left + 1)
        inner_bottom = max(height - margin_y, inner_top + 1)
        inner_crop = name_crop[inner_top:inner_bottom, inner_left:inner_right].copy()
        if inner_crop.size == 0:
            return name_crop
        return inner_crop

    def _crop_name_tight(self, image: np.ndarray, rect: Dict[str, int]) -> np.ndarray:
        cv2 = self._cv2()
        inner_crop = self._crop_name_box_inner(image, rect)
        if inner_crop.size == 0:
            return inner_crop

        if inner_crop.ndim == 3:
            gray = cv2.cvtColor(inner_crop, cv2.COLOR_RGB2GRAY)
        else:
            gray = inner_crop
        normalized = self._normalize_illumination(gray)
        gray = self._apply_unsharp_mask(self._apply_clahe(normalized))
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        horizontal_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (max(inner_crop.shape[1] // 7, 28), 1),
        )
        vertical_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (1, max(inner_crop.shape[0] // 2, 18)),
        )
        horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
        vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
        binary = cv2.subtract(binary, horizontal_lines)
        binary = cv2.subtract(binary, vertical_lines)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), dtype=np.uint8))
        binary = cv2.dilate(binary, np.ones((3, 3), dtype=np.uint8), iterations=1)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask = np.zeros_like(binary)
        min_area = max(10, int((inner_crop.shape[0] * inner_crop.shape[1]) * 0.00004))
        min_height = max(8, int(inner_crop.shape[0] * 0.12))
        min_width = max(6, int(inner_crop.shape[1] * 0.01))

        for contour in contours:
            area = cv2.contourArea(contour)
            x, y, w, h = cv2.boundingRect(contour)
            if area < min_area and h < min_height and w < min_width:
                continue
            cv2.drawContours(mask, [contour], -1, 255, thickness=cv2.FILLED)

        points = cv2.findNonZero(mask)
        if points is None:
            return inner_crop

        x, y, w, h = cv2.boundingRect(points)
        pad_x = max(12, int(w * 0.08))
        pad_y = max(10, int(h * 0.2))
        x0 = max(x - pad_x, 0)
        y0 = max(y - pad_y, 0)
        x1 = min(x + w + pad_x, inner_crop.shape[1])
        y1 = min(y + h + pad_y, inner_crop.shape[0])
        return inner_crop[y0:y1, x0:x1].copy()

    def _prepare_color_ink_binary(self, image: np.ndarray, *, strict: bool) -> np.ndarray:
        cv2 = self._cv2()
        rgb = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)

        saturation = hsv[:, :, 1].astype(np.uint8)
        value = hsv[:, :, 2].astype(np.uint8)
        lab_a = lab[:, :, 1].astype(np.int16)
        lab_b = lab[:, :, 2].astype(np.int16)
        chroma_distance = np.abs(lab_a - 128) + np.abs(lab_b - 128)

        if strict:
            dark_mask = gray < 178
            colored_mask = (saturation > 52) & (value < 232) & (chroma_distance > 18)
        else:
            dark_mask = gray < 194
            colored_mask = (saturation > 30) & (value < 244) & (chroma_distance > 10)

        binary = np.where(dark_mask | colored_mask, 255, 0).astype(np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), dtype=np.uint8))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8))
        return binary

    def _bubble_fill_ratio(self, binary: np.ndarray, center_x: int, center_y: int, radius: int) -> float:
        fill_radius = max(int(radius * 0.55), 6)
        y0 = max(center_y - fill_radius, 0)
        y1 = min(center_y + fill_radius, binary.shape[0] - 1)
        x0 = max(center_x - fill_radius, 0)
        x1 = min(center_x + fill_radius, binary.shape[1] - 1)
        region = binary[y0:y1 + 1, x0:x1 + 1]
        if region.size == 0:
            return 0.0

        yy, xx = np.ogrid[y0:y1 + 1, x0:x1 + 1]
        mask = ((xx - center_x) ** 2 + (yy - center_y) ** 2) <= (fill_radius * fill_radius)
        if not np.any(mask):
            return 0.0
        filled = np.count_nonzero(region[mask] > 0)
        total = int(np.count_nonzero(mask))
        return filled / float(total or 1)

    def _decode_digit_columns(self, binary: np.ndarray, x_centers: List[int], row_centers: List[int], radius: int) -> Tuple[str, List[List[float]]]:
        digits: List[str] = []
        debug_scores: List[List[float]] = []

        for center_x in x_centers:
            column_scores = []
            for center_y in row_centers:
                column_scores.append(self._bubble_fill_ratio(binary, center_x, center_y, radius))
            debug_scores.append(column_scores)

            best_digit = int(np.argmax(column_scores))
            sorted_scores = sorted(column_scores, reverse=True)
            best_score = column_scores[best_digit]
            second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
            if best_score >= 0.28 and (best_score - second_score) >= 0.03:
                digits.append(str(best_digit))
            else:
                digits.append("")

        return "".join(digits).strip(), debug_scores

    def _decode_answers(self, binary: np.ndarray, radius: int) -> Tuple[List[str], List[List[float]]]:
        question_count = int(self.layout["question_count"])
        answer_columns_meta = list(self.layout["answer_columns_meta"])
        labels = ["A", "B", "C", "D"]

        answers: List[str] = []
        debug_scores: List[List[float]] = []
        for question_index in range(question_count):
            column_index = 0
            row_meta = None
            for meta_index, column_meta in enumerate(answer_columns_meta):
                rows = list(column_meta["question_rows"])
                matched = next((item for item in rows if int(item["question_number"]) == question_index + 1), None)
                if matched is not None:
                    column_index = meta_index
                    row_meta = matched
                    break

            if row_meta is None:
                answers.append("")
                debug_scores.append([0.0, 0.0, 0.0, 0.0])
                continue

            column_meta = answer_columns_meta[column_index]
            center_y = int(row_meta["y"])
            option_scores = []
            for center_x in column_meta["option_centers"]:
                option_scores.append(self._bubble_fill_ratio(binary, center_x, center_y, radius))
            debug_scores.append(option_scores)

            best_idx = int(np.argmax(option_scores))
            best_score = option_scores[best_idx]
            above_threshold = [idx for idx, score in enumerate(option_scores) if score >= 0.25]
            sorted_scores = sorted(option_scores, reverse=True)
            second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
            if best_score >= 0.25 and len(above_threshold) == 1 and (best_score - second_score) >= 0.025:
                answers.append(labels[best_idx])
            elif best_score >= 0.25 and len(above_threshold) > 1:
                answers.append("MULTI")
            else:
                answers.append("")
        return answers, debug_scores

    def _average_margin(self, score_rows: List[List[float]]) -> float:
        margins: List[float] = []
        for row in score_rows:
            if not row:
                continue
            sorted_scores = sorted(float(value) for value in row)
            if not sorted_scores:
                continue
            best = sorted_scores[-1]
            second = sorted_scores[-2] if len(sorted_scores) > 1 else 0.0
            margins.append(best - second)
        return float(sum(margins) / len(margins)) if margins else 0.0

    def _candidate_quality(
        self,
        *,
        status: str,
        student_id: str,
        exam_code: str,
        answers: List[str],
        student_id_scores: List[List[float]],
        exam_code_scores: List[List[float]],
        answer_scores: List[List[float]],
    ) -> Tuple[int, int, int, int, int, float]:
        status_rank = {
            "ok": 4,
            "missing_student_id": 3,
            "ambiguous_answers": 2,
            "missing_exam_code": 1,
        }.get(status, 0)
        answered_count = sum(1 for answer in answers if answer in {"A", "B", "C", "D"})
        multi_count = sum(1 for answer in answers if answer == "MULTI")
        combined_margin = (
            self._average_margin(student_id_scores)
            + self._average_margin(exam_code_scores)
            + self._average_margin(answer_scores)
        )
        return (
            status_rank,
            int(bool(exam_code)),
            int(bool(student_id)),
            answered_count,
            -multi_count,
            round(combined_margin, 6),
        )

    def _binary_candidates(self, aligned: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        candidates: List[Tuple[str, np.ndarray]] = []
        seen: set[str] = set()
        for variant_name, gray in self._gray_variants(aligned):
            for strategy in ("otsu", "adaptive", "filled"):
                key = f"{variant_name}_{strategy}"
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((key, self._prepare_binary_from_gray(gray, strategy=strategy)))
        for key, binary in (
            ("ink_relaxed", self._prepare_color_ink_binary(aligned, strict=False)),
            ("ink_strict", self._prepare_color_ink_binary(aligned, strict=True)),
        ):
            if key in seen:
                continue
            seen.add(key)
            candidates.append((key, binary))
        return candidates

    def process_page(self, image: np.ndarray) -> OMRProcessResult:
        aligned, alignment_debug = self.align_page(image)
        name_box_crop = self._crop_name_box_inner(aligned, self.layout["name_box"])
        name_crop = self._crop_name_tight(aligned, self.layout["name_box"])
        digit_radius = int(self.layout.get("digit_bubble_radius", self.layout.get("bubble_radius", 22)))
        answer_radius = int(self.layout.get("answer_bubble_radius", self.layout.get("bubble_radius", 22)))
        digit_row_centers = [int(value) for value in self.layout["digit_row_centers"]]

        best_candidate: Dict[str, object] | None = None
        for variant_name, binary in self._binary_candidates(aligned):
            student_id, student_id_scores = self._decode_digit_columns(
                binary,
                [int(value) for value in self.layout["student_id_x_centers"]],
                digit_row_centers,
                digit_radius,
            )
            exam_code, exam_code_scores = self._decode_digit_columns(
                binary,
                [int(value) for value in self.layout["exam_code_x_centers"]],
                digit_row_centers,
                digit_radius,
            )
            answers, answer_scores = self._decode_answers(binary, answer_radius)

            status = "ok"
            if not exam_code:
                status = "missing_exam_code"
            elif not student_id:
                status = "missing_student_id"
            elif any(answer == "MULTI" for answer in answers):
                status = "ambiguous_answers"

            quality = self._candidate_quality(
                status=status,
                student_id=student_id,
                exam_code=exam_code,
                answers=answers,
                student_id_scores=student_id_scores,
                exam_code_scores=exam_code_scores,
                answer_scores=answer_scores,
            )
            if best_candidate is None or quality > tuple(best_candidate["quality"]):
                best_candidate = {
                    "variant": variant_name,
                    "student_id": student_id,
                    "exam_code": exam_code,
                    "answers": answers,
                    "status": status,
                    "student_id_scores": student_id_scores,
                    "exam_code_scores": exam_code_scores,
                    "answer_scores": answer_scores,
                    "quality": quality,
                }

        if best_candidate is None:
            return OMRProcessResult(
                aligned_image=aligned,
                name_crop=name_crop,
                name_box_crop=name_box_crop,
                student_id="",
                exam_code="",
                answers=[],
                status="missing_exam_code",
                debug={"alignment": alignment_debug, "selected_binary_variant": "none"},
            )

        return OMRProcessResult(
            aligned_image=aligned,
            name_crop=name_crop,
            name_box_crop=name_box_crop,
            student_id=str(best_candidate["student_id"]),
            exam_code=str(best_candidate["exam_code"]),
            answers=list(best_candidate["answers"]),
            status=str(best_candidate["status"]),
            debug={
                "alignment": alignment_debug,
                "selected_binary_variant": best_candidate["variant"],
                "candidate_quality": list(best_candidate["quality"]),
                "student_id_scores": best_candidate["student_id_scores"],
                "exam_code_scores": best_candidate["exam_code_scores"],
                "answer_scores": best_candidate["answer_scores"],
            },
        )
