from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np


@dataclass
class DocumentScannerResult:
    scanned_image: np.ndarray
    status: str
    contour_area_ratio: float
    used_perspective_warp: bool
    debug: Dict[str, object]
    debug_images: Dict[str, np.ndarray]


class DocumentScannerService:
    MIN_CONTOUR_AREA_RATIO = 0.18
    TARGET_WIDTH = 2480
    TARGET_HEIGHT = 3508

    def _cv2(self):
        try:
            import cv2  # type: ignore
        except Exception as exc:
            raise RuntimeError("Thiếu thư viện OpenCV (`cv2`). Hãy cài `opencv-python-headless` để dùng chức năng scan ảnh OMR.") from exc
        return cv2

    def _order_points(self, points: np.ndarray) -> np.ndarray:
        points = points.astype(np.float32)
        sums = points.sum(axis=1)
        diffs = np.diff(points, axis=1)
        ordered = np.zeros((4, 2), dtype=np.float32)
        ordered[0] = points[np.argmin(sums)]
        ordered[2] = points[np.argmax(sums)]
        ordered[1] = points[np.argmin(diffs)]
        ordered[3] = points[np.argmax(diffs)]
        return ordered

    def _normalize_illumination(self, gray: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        background = cv2.GaussianBlur(gray, (0, 0), 25)
        normalized = cv2.divide(gray, background, scale=255)
        return cv2.normalize(normalized, None, 0, 255, cv2.NORM_MINMAX)

    def _apply_clahe(self, gray: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _apply_unsharp_mask(self, gray: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        blurred = cv2.GaussianBlur(gray, (0, 0), 1.6)
        sharpened = cv2.addWeighted(gray, 1.75, blurred, -0.75, 0)
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    def _resize_for_detection(self, image: np.ndarray, target_max_side: int = 1600) -> Tuple[np.ndarray, float]:
        height, width = image.shape[:2]
        longest_side = max(height, width)
        if longest_side <= target_max_side:
            return image.copy(), 1.0
        scale = target_max_side / float(longest_side)
        cv2 = self._cv2()
        resized = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        return resized, scale

    def _build_detection_mask(self, gray: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 60, 180)
        adaptive = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            10,
        )
        adaptive = cv2.bitwise_not(adaptive)
        combined = cv2.bitwise_or(edges, adaptive)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8), iterations=2)
        combined = cv2.dilate(combined, np.ones((3, 3), dtype=np.uint8), iterations=1)
        return combined

    def _pick_document_contour(self, mask: np.ndarray, canvas_shape: Tuple[int, int]) -> Tuple[Optional[np.ndarray], float]:
        cv2 = self._cv2()
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, 0.0

        canvas_area = float(canvas_shape[0] * canvas_shape[1])
        candidates: list[tuple[float, float, np.ndarray]] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area <= 0:
                continue
            area_ratio = area / float(canvas_area or 1.0)
            if area_ratio < self.MIN_CONTOUR_AREA_RATIO:
                continue

            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                score = area_ratio + 0.2
                candidates.append((score, area_ratio, approx.reshape(4, 2)))
                continue

            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect)
            box_area = float(cv2.contourArea(box.astype(np.float32)))
            if box_area <= 0:
                continue
            fill_ratio = area / box_area
            width, height = rect[1]
            if min(width, height) <= 0:
                continue
            aspect_ratio = max(width, height) / float(min(width, height))
            if fill_ratio < 0.72 or aspect_ratio > 2.1:
                continue
            score = area_ratio + min(fill_ratio, 1.0) * 0.1
            candidates.append((score, area_ratio, box.reshape(4, 2)))

        if not candidates:
            return None, 0.0
        candidates.sort(key=lambda item: item[0], reverse=True)
        _, area_ratio, points = candidates[0]
        return points.astype(np.float32), area_ratio

    def _warp_document(self, image: np.ndarray, points: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        ordered = self._order_points(points)
        (top_left, top_right, bottom_right, bottom_left) = ordered

        width = self.TARGET_WIDTH
        height = self.TARGET_HEIGHT

        dst = np.array(
            [
                [0, 0],
                [width - 1, 0],
                [width - 1, height - 1],
                [0, height - 1],
            ],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(ordered, dst)
        return cv2.warpPerspective(image, matrix, (width, height), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))

    def _enhance_scanned_document(self, image: np.ndarray) -> np.ndarray:
        cv2 = self._cv2()
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image.copy()
        normalized = self._normalize_illumination(gray)
        clahe = self._apply_clahe(normalized)
        sharpened = self._apply_unsharp_mask(clahe)
        return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2RGB)

    def scan_document(self, image: np.ndarray) -> DocumentScannerResult:
        cv2 = self._cv2()
        input_image = image.astype(np.uint8).copy()
        detection_image, scale = self._resize_for_detection(input_image)
        gray = cv2.cvtColor(detection_image, cv2.COLOR_RGB2GRAY) if detection_image.ndim == 3 else detection_image.copy()
        mask = self._build_detection_mask(gray)
        detected_points, area_ratio = self._pick_document_contour(mask, gray.shape[:2])

        overlay_image = detection_image.copy()
        if overlay_image.ndim == 2:
            overlay_image = cv2.cvtColor(overlay_image, cv2.COLOR_GRAY2RGB)

        if detected_points is None:
            enhanced = self._enhance_scanned_document(input_image)
            return DocumentScannerResult(
                scanned_image=input_image,
                status="fallback_original",
                contour_area_ratio=0.0,
                used_perspective_warp=False,
                debug={
                    "scanner_status": "fallback_original",
                    "scanner_contour_area_ratio": 0.0,
                    "scanner_used_perspective_warp": False,
                    "scanner_detection_scale": scale,
                },
                debug_images={
                    "scanner_input": input_image,
                    "scanner_contour": overlay_image,
                    "scanner_warped": input_image,
                    "scanner_enhanced": enhanced,
                },
            )

        contour_x, contour_y, contour_w, contour_h = cv2.boundingRect(detected_points.astype(np.float32))
        frame_h, frame_w = detection_image.shape[:2]
        border_ratio_x = min(contour_x, frame_w - (contour_x + contour_w)) / float(max(frame_w, 1))
        border_ratio_y = min(contour_y, frame_h - (contour_y + contour_h)) / float(max(frame_h, 1))
        covers_full_frame = (
            area_ratio >= 0.82
            and border_ratio_x <= 0.025
            and border_ratio_y <= 0.025
        )
        if covers_full_frame:
            enhanced = self._enhance_scanned_document(input_image)
            return DocumentScannerResult(
                scanned_image=input_image,
                status="already_scanned",
                contour_area_ratio=float(round(area_ratio, 6)),
                used_perspective_warp=False,
                debug={
                    "scanner_status": "already_scanned",
                    "scanner_contour_area_ratio": float(round(area_ratio, 6)),
                    "scanner_used_perspective_warp": False,
                    "scanner_detection_scale": scale,
                },
                debug_images={
                    "scanner_input": input_image,
                    "scanner_contour": overlay_image,
                    "scanner_warped": input_image,
                    "scanner_enhanced": enhanced,
                },
            )

        scaled_points = (detected_points / float(scale or 1.0)).astype(np.float32)
        drawn_points = detected_points.astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(overlay_image, [drawn_points], True, (0, 255, 0), 6)
        warped = self._warp_document(input_image, scaled_points)
        enhanced = self._enhance_scanned_document(warped)

        return DocumentScannerResult(
            scanned_image=warped,
            status="paper_detected",
            contour_area_ratio=float(round(area_ratio, 6)),
            used_perspective_warp=True,
            debug={
                "scanner_status": "paper_detected",
                "scanner_contour_area_ratio": float(round(area_ratio, 6)),
                "scanner_used_perspective_warp": True,
                "scanner_detection_scale": scale,
                "scanner_points": scaled_points.astype(float).tolist(),
                "scanner_warped_shape": list(enhanced.shape[:2]),
            },
            debug_images={
                "scanner_input": input_image,
                "scanner_contour": overlay_image,
                "scanner_warped": warped,
                "scanner_enhanced": enhanced,
            },
        )
