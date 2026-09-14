"""OCR for pages that have no text layer, and for uploaded answer sheets.

RapidOCR rather than Tesseract: it is pip-only, shipping its PP-OCRv4 ONNX
weights inside the wheel, so it behaves the same on a bare Windows host as in
`python:3.12-slim` — no system binary, no language-data volume, no apt step.

The engine is imported lazily and behind a Protocol, so the rest of the backend
runs in an image built without the exam extras, and a different engine can be
dropped in by setting EXAMS_OCR_ENGINE.
"""

from __future__ import annotations

import io
import os
from typing import Protocol

from exams.importer.pdfsource import Word

__all__ = ["OcrEngine", "RapidOcrEngine", "get_engine", "OcrUnavailable"]


class OcrUnavailable(RuntimeError):
    """Raised when no OCR engine can be loaded."""


class OcrEngine(Protocol):
    def recognise(
        self, png_bytes: bytes, page_width: float, page_height: float
    ) -> tuple[list[Word], float]:
        """Return (words in page-point coordinates, mean confidence 0..1)."""


class RapidOcrEngine:
    """RapidOCR (PP-OCRv4) wrapper.

    Returns one :class:`Word` per recognised text line rather than per word.
    RapidOCR detects lines, and splitting a line back into words by guessing at
    character positions would invent coordinates that were never measured. The
    layout code copes: it groups by geometry, and a line is simply an already
    grouped set.
    """

    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:  # pragma: no cover - depends on build flags
            raise OcrUnavailable(
                "rapidocr-onnxruntime is not installed. Rebuild the backend "
                "image with INSTALL_EXAMS=true, or pip install "
                "-r requirements-exams.txt."
            ) from exc
        self._engine = RapidOCR()

    def recognise(
        self, png_bytes: bytes, page_width: float, page_height: float
    ) -> tuple[list[Word], float]:
        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        pixel_width, pixel_height = image.size
        result, _elapsed = self._engine(np.asarray(image))
        if not result:
            return [], 0.0

        # The render is at some DPI; the rest of the pipeline works in PDF
        # points, so scale back or every geometric threshold is wrong.
        scale_x = page_width / pixel_width if pixel_width else 1.0
        scale_y = page_height / pixel_height if pixel_height else 1.0

        words: list[Word] = []
        confidences: list[float] = []
        for index, entry in enumerate(result):
            box, text, confidence = entry[0], entry[1], entry[2]
            text = (text or "").strip()
            if not text:
                continue
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            confidences.append(confidence)
            words.append(
                Word(
                    text=text,
                    x0=min(xs) * scale_x,
                    y0=min(ys) * scale_y,
                    x1=max(xs) * scale_x,
                    y1=max(ys) * scale_y,
                    confidence=confidence,
                    # No block structure from OCR: the layout module falls back
                    # to its geometric path, which is what those -1s select.
                )
            )
        mean = sum(confidences) / len(confidences) if confidences else 0.0
        return words, mean


def get_engine(name: str = "") -> OcrEngine:
    """Load the configured OCR engine."""
    name = (name or os.getenv("EXAMS_OCR_ENGINE", "rapidocr")).lower()
    if name in ("rapidocr", "", "default"):
        return RapidOcrEngine()
    raise OcrUnavailable(f"unknown OCR engine: {name!r}")
