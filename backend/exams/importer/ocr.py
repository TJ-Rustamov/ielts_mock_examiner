"""OCR for pages that have no text layer, and for uploaded answer sheets.

RapidOCR rather than Tesseract: it is pip-only, shipping its PP-OCRv4 ONNX
weights inside the wheel, so it behaves the same on a bare Windows host as in
`python:3.12-slim` — no system binary, no language-data volume, no apt step.

The engine is imported lazily and behind a Protocol, so the rest of the backend
runs in an image built without the exam extras, and a different engine can be
dropped in by setting EXAMS_OCR_ENGINE.

Scans are cleaned up before recognition (see :func:`preprocess`). Circulated
copies of the Cambridge books are phone photos and flatbed scans: a degree or
two of skew, grey paper, a shadow down the spine. Skew is the expensive one -
over a 500pt line, 2 degrees moves the far end by a whole line height, so the
layout code groups words from neighbouring rows together.
"""

from __future__ import annotations

import io
import os
from dataclasses import replace
from statistics import median
from typing import Protocol

from exams.importer.pdfsource import Word

__all__ = [
    "OcrEngine",
    "RapidOcrEngine",
    "get_engine",
    "try_get_engine",
    "OcrUnavailable",
    "preprocess",
    "estimate_skew",
    "words_from_fragments",
]

#: Skew search range and resolution, in degrees. Scans are rarely off by more
#: than a couple of degrees; anything beyond five is a photo that needs
#: retaking, not straightening.
MAX_SKEW = 5.0
SKEW_STEP = 0.25
#: Below this the rotation costs more (resampling blur) than it fixes.
MIN_SKEW = 0.3

#: A gap between two recognised characters wider than this fraction of the
#: typical character cell starts a new word. Recognition sometimes drops the
#: space itself ("13NOTGIVEN") while the gap it occupied survives.
WORD_GAP_RATIO = 0.8


class OcrUnavailable(RuntimeError):
    """Raised when no OCR engine can be loaded."""


class OcrEngine(Protocol):
    def recognise(
        self, png_bytes: bytes, page_width: float, page_height: float
    ) -> tuple[list[Word], float]:
        """Return (words in page-point coordinates, mean confidence 0..1)."""


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------


def preprocessing_enabled() -> bool:
    """EXAMS_OCR_PREPROCESS=0 turns cleanup off, for before/after comparisons."""
    return os.getenv("EXAMS_OCR_PREPROCESS", "1").strip().lower() not in ("0", "false", "no")


def _rotate(gray, angle: float, border: int = 255):
    import cv2

    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (width, height),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=border,
    )


def estimate_skew(gray) -> float:
    """Angle in degrees that straightens the text lines of a grayscale page.

    Projection-profile search: rotate the ink mask through candidate angles and
    keep the one whose row sums are the most "peaky". Text lines that run
    straight across the page stack their ink into a few rows with white rows
    between; a skewed page smears every line over many rows. Coarse pass, then
    a fine pass around the winner. Works on a downscaled copy - skew is a
    whole-page property and does not need full resolution.
    """
    import cv2
    import numpy as np

    height, width = gray.shape[:2]
    scale = min(1.0, 1200.0 / max(width, 1))
    small = cv2.resize(gray, (max(1, int(width * scale)), max(1, int(height * scale))),
                       interpolation=cv2.INTER_AREA) if scale < 1 else gray
    _, ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if not ink.any():
        return 0.0

    def score(angle: float) -> float:
        rotated = _rotate(ink, angle, border=0)
        profile = rotated.sum(axis=1, dtype=np.float64)
        return float(np.var(profile))

    def search(centre: float, span: float, step: float) -> float:
        best_angle, best_score = centre, -1.0
        steps = int(round(span / step))
        for i in range(-steps, steps + 1):
            angle = centre + i * step
            if abs(angle) > MAX_SKEW:
                continue
            value = score(angle)
            if value > best_score:
                best_angle, best_score = angle, value
        return best_angle

    coarse = search(0.0, MAX_SKEW, SKEW_STEP * 2)
    return round(search(coarse, SKEW_STEP * 2, SKEW_STEP / 2), 3)


def normalise_background(gray):
    """Flatten grey paper, yellowing and spine shadow to white.

    Divides the page by an estimate of its own background - a heavily blurred
    copy, computed small for speed - so the paper comes out white and the ink
    keeps its relative darkness. Deliberately no contrast stretch and no
    binarisation: on a mostly white page any percentile-based stretch anchors
    on the paper and thickens every stroke into its neighbour, which measurably
    cost PP-OCR most of the digits on a test key page.
    """
    import cv2
    import numpy as np

    height, width = gray.shape[:2]
    small = cv2.resize(gray, (max(1, width // 8), max(1, height // 8)),
                       interpolation=cv2.INTER_AREA)
    kernel = max(3, (min(small.shape[:2]) // 12) | 1)
    background = cv2.medianBlur(small, min(kernel, 255))
    background = cv2.resize(background, (width, height), interpolation=cv2.INTER_LINEAR)
    return cv2.divide(gray, np.maximum(background, 1), scale=255)


def preprocess(image) -> tuple:
    """Clean a page render for OCR. Returns (RGB uint8 array, deskew angle).

    Accepts PNG/JPEG bytes or a numpy array (gray or RGB).
    """
    import cv2
    import numpy as np

    if isinstance(image, (bytes, bytearray)):
        from PIL import Image

        array = np.asarray(Image.open(io.BytesIO(image)).convert("L"))
    else:
        array = np.asarray(image)
        if array.ndim == 3:
            array = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    gray = array.astype(np.uint8)

    # Background first: on grey or shadowed paper, Otsu takes the dark side of
    # the page for ink, and the skew search then straightens the shadow.
    gray = normalise_background(gray)
    angle = estimate_skew(gray)
    if abs(angle) >= MIN_SKEW:
        gray = _rotate(gray, angle)
    else:
        angle = 0.0
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB), angle


def _load_rgb(image):
    import numpy as np

    if isinstance(image, (bytes, bytearray)):
        from PIL import Image

        return np.asarray(Image.open(io.BytesIO(image)).convert("RGB"))
    array = np.asarray(image)
    if array.ndim == 2:
        import cv2

        return cv2.cvtColor(array, cv2.COLOR_GRAY2RGB)
    return array


# ---------------------------------------------------------------------------
# Recognition output -> words
# ---------------------------------------------------------------------------


def _bounds(points) -> tuple[float, float, float, float]:
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def words_from_fragments(
    fragments: list[tuple[str, tuple[float, float, float, float], float]],
) -> list[tuple[str, tuple[float, float, float, float], float]]:
    """Join recognised characters (or word pieces) into words.

    RapidOCR's word boxes are per character for Latin text, positioned from
    the recogniser's own CTC alignment - measured, not interpolated. A word
    ends at an explicit space, or at a gap wider than a typical character
    cell, which recovers the spaces recognition sometimes drops.

    Returns (text, (x0, y0, x1, y1), min confidence) per word, in input units.
    """
    pieces = [(t, b, c) for t, b, c in fragments if t]
    widths = [b[2] - b[0] for t, b, _c in pieces if t.strip() and b[2] > b[0]]
    cell = median(widths) if widths else 0.0

    words: list[tuple[str, tuple[float, float, float, float], float]] = []
    text, box, confidence = "", None, 1.0
    previous_x1: float | None = None

    def flush() -> None:
        nonlocal text, box, confidence
        if text and box is not None:
            words.append((text, box, confidence))
        text, box, confidence = "", None, 1.0

    for piece, (x0, y0, x1, y1), conf in pieces:
        if not piece.strip():
            flush()
            previous_x1 = x1
            continue
        if (
            text
            and previous_x1 is not None
            and cell > 0
            and x0 - previous_x1 > cell * WORD_GAP_RATIO
        ):
            flush()
        if box is None:
            box = (x0, y0, x1, y1)
        else:
            box = (min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1))
        text += piece.strip()
        confidence = min(confidence, float(conf))
        previous_x1 = x1
    flush()
    return words


def _entry_words(entry, segment: int, scale_x: float, scale_y: float) -> list[Word]:
    """One RapidOCR result entry -> Words in page points.

    With ``return_word_box`` an entry is ``[box, text, conf, word_boxes,
    word_texts, word_confs]``; without it, ``[box, text, conf]``. Anything
    unexpected falls back to one Word for the whole detected line - the layout
    and gap code tolerate that, they just have less to work with.
    """
    box, text, line_conf = entry[0], (entry[1] or "").strip(), entry[2]
    try:
        line_conf = float(line_conf)
    except (TypeError, ValueError):
        line_conf = 0.0
    if not text:
        return []

    if len(entry) >= 6 and entry[3] and entry[4] and entry[5]:
        boxes, texts, confs = entry[3], entry[4], entry[5]
        if len(boxes) == len(texts) == len(confs):
            try:
                fragments = [
                    (str(t), _bounds(b), float(c)) for b, t, c in zip(boxes, texts, confs)
                ]
            except (TypeError, ValueError, IndexError):
                fragments = []
            joined = words_from_fragments(fragments) if fragments else []
            if joined:
                return [
                    Word(
                        text=word,
                        x0=x0 * scale_x, y0=y0 * scale_y,
                        x1=x1 * scale_x, y1=y1 * scale_y,
                        confidence=conf,
                        segment=segment,
                    )
                    for word, (x0, y0, x1, y1), conf in joined
                ]

    x0, y0, x1, y1 = _bounds(box)
    return [
        Word(
            text=text,
            x0=x0 * scale_x, y0=y0 * scale_y,
            x1=x1 * scale_x, y1=y1 * scale_y,
            confidence=line_conf,
            segment=segment,
        )
    ]


#: RapidOCR shrinks any image whose longer side exceeds this before reading it.
#: Its own default of 2000 turns a 300 DPI page into roughly 170 DPI, and at
#: that size the recogniser drops most word spaces ("Completethenotesbelow.");
#: 4000 keeps the render's resolution and roughly doubles the share of lines
#: that keep their spaces, at about three times the time per page.
DEFAULT_MAX_SIDE = 4000


def engine_options() -> dict:
    """RapidOCR constructor options, from the environment.

    EXAMS_OCR_MAX_SIDE overrides the size limit. EXAMS_OCR_REC_MODEL (and
    EXAMS_OCR_REC_KEYS, its character list) swap in a different recognition
    model - PaddleOCR's English model keeps word spaces better than the bundled
    Chinese+English one - for anyone who has downloaded it; it is not shipped.
    """
    options: dict = {}
    try:
        options["max_side_len"] = int(os.getenv("EXAMS_OCR_MAX_SIDE", DEFAULT_MAX_SIDE))
    except ValueError:
        options["max_side_len"] = DEFAULT_MAX_SIDE
    model = os.getenv("EXAMS_OCR_REC_MODEL", "").strip()
    if model:
        options["rec_model_path"] = model
        keys = os.getenv("EXAMS_OCR_REC_KEYS", "").strip()
        if keys:
            options["rec_keys_path"] = keys
    return options


class RapidOcrEngine:
    """RapidOCR (PP-OCRv4) wrapper.

    Returns one :class:`Word` per recognised word, cut from each detected line
    using the recogniser's own character positions. On a RapidOCR build that
    cannot report those, it falls back to one Word per detected line rather
    than inventing coordinates by guessing at character widths.
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
        self._engine = RapidOCR(**engine_options())
        self._word_boxes = True
        #: Angle the last call straightened its input by (see preprocess).
        self.last_deskew_angle = 0.0

    def _run(self, array):
        if self._word_boxes:
            try:
                return self._engine(array, return_word_box=True)
            except TypeError:  # pragma: no cover - older rapidocr
                self._word_boxes = False
        return self._engine(array)

    def recognise(
        self,
        png_bytes,
        page_width: float,
        page_height: float,
        preprocess_image: bool | None = None,
    ) -> tuple[list[Word], float]:
        """OCR an image (bytes or array) into words in page-point coordinates.

        `preprocess_image` defaults to the EXAMS_OCR_PREPROCESS setting; pass
        False for an image that has already been cleaned (a column strip cut
        from a preprocessed page).
        """
        if preprocess_image is None:
            preprocess_image = preprocessing_enabled()
        if preprocess_image:
            array, self.last_deskew_angle = preprocess(png_bytes)
        else:
            array, self.last_deskew_angle = _load_rgb(png_bytes), 0.0

        pixel_height, pixel_width = array.shape[:2]
        result, _elapsed = self._run(array)
        if not result:
            return [], 0.0

        # The render is at some DPI; the rest of the pipeline works in PDF
        # points, so scale back or every geometric threshold is wrong.
        scale_x = page_width / pixel_width if pixel_width else 1.0
        scale_y = page_height / pixel_height if pixel_height else 1.0

        words: list[Word] = []
        confidences: list[float] = []
        for segment, entry in enumerate(result):
            entry_words = _entry_words(entry, segment, scale_x, scale_y)
            if not entry_words:
                continue
            try:
                confidences.append(float(entry[2]))
            except (TypeError, ValueError):
                confidences.append(0.0)
            words.extend(entry_words)
        mean = sum(confidences) / len(confidences) if confidences else 0.0
        return words, mean


def offset_words(words: list[Word], dx: float = 0.0, dy: float = 0.0) -> list[Word]:
    """Shift words, e.g. from a cropped strip back into page coordinates."""
    if not dx and not dy:
        return list(words)
    return [replace(w, x0=w.x0 + dx, x1=w.x1 + dx, y0=w.y0 + dy, y1=w.y1 + dy) for w in words]


def get_engine(name: str = "") -> OcrEngine:
    """Load the configured OCR engine."""
    name = (name or os.getenv("EXAMS_OCR_ENGINE", "rapidocr")).lower()
    if name in ("rapidocr", "", "default"):
        return RapidOcrEngine()
    raise OcrUnavailable(f"unknown OCR engine: {name!r}")


def try_get_engine(name: str = ""):
    """(engine, None) or (None, reason) - for callers that must not fail.

    The importer needs OCR only for scanned pages, so a missing engine is a
    warning on the job rather than an error; the pages it would have read are
    reported by number instead.
    """
    try:
        return get_engine(name), None
    except Exception as exc:  # OcrUnavailable, or a broken ONNX runtime
        return None, f"OCR is unavailable: {exc}"
