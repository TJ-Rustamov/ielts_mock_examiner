"""Turn an uploaded answer-sheet image into a module's 40 answers.

Why this exists rather than reading the key out of the book's PDF: Cambridge
typesets its key pages in columns that sometimes interleave when the PDF text is
flattened — Cambridge 21 page 120 puts the Part 3 option letters inside the
Part 1 answers. Every ordering heuristic tried against that page either failed
on it or regressed the seven pages that already worked, and the cost of being
wrong is a wrong key that silently mis-marks every future candidate.

An image is a better input for this, but not for the reason you might expect.
RapidOCR happily merges across the gutter - it read "2 48 / forty-eight" and the
"B" beside it as the single line "48 forty-eight B" - and once merged, no
downstream geometry can separate them, because the merged box has one bounding
box. What the image gives that the PDF does not is the *white channel itself*:
the columns are cropped apart before OCR ever runs, so nothing can merge across
them.

The result is still only a *proposal*. It pre-fills a grid an admin confirms,
and ``Module.blocking_problems`` refuses to publish until they have.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from exams import keygrammar
from exams.importer.layout import read_page
from exams.marking import AnswerKey

__all__ = [
    "SheetParse",
    "parse_sheet",
    "find_image_gutters",
    "estimate_divider",
    "answers_to_json",
    "answers_from_json",
]

#: Answer sheets are rendered/uploaded at roughly this size in "points" so the
#: geometric thresholds in layout.py (gutter width as a fraction of page width)
#: mean the same thing as they do for a PDF page.
ASSUMED_PAGE_WIDTH = 595.0
ASSUMED_PAGE_HEIGHT = 842.0



def find_image_gutters(
    image_bytes: bytes,
    min_ratio: float = 0.03,
    ink_threshold: float = 0.004,
) -> list[int]:
    """Find vertical white channels in the image, as x pixel positions.

    A printed answer key has a genuinely white channel between its columns,
    which shows up as a run of pixel columns with almost no dark pixels. That
    channel is the one piece of information the PDF text layer does not give
    you, and it is what makes splitting reliable here.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:  # pragma: no cover - depends on build flags
        return []

    image = Image.open(io.BytesIO(image_bytes)).convert("L")
    pixels = np.asarray(image)
    height, width = pixels.shape
    if width < 50:
        return []

    dark = (pixels < 200).sum(axis=0) / float(height)
    empty = dark <= ink_threshold

    minimum = max(4, int(width * min_ratio))
    gutters: list[int] = []
    start: int | None = None
    for index, is_empty in enumerate(empty):
        if is_empty and start is None:
            start = index
        elif not is_empty and start is not None:
            if index - start >= minimum:
                gutters.append((start + index) // 2)
            start = None
    if start is not None and width - start >= minimum:
        gutters.append((start + width) // 2)

    # Only interior channels are column separators; the page margins are not.
    margin = width * 0.12
    return [x for x in gutters if margin < x < width - margin]


def estimate_divider(boxes: list[tuple[float, float]], width: float) -> float | None:
    """Pick the column divider from OCR line boxes, given (x0, x1) per line.

    Clusters on **left edges**. A column sets a left margin that every line in
    it shares, whereas line widths - and therefore centres - vary wildly with
    the length of each answer. The widest gap is not automatically the divider
    either: a single stray box near the margin can out-gap the real channel, so
    candidates are tried widest-first and the first one that splits the lines
    sensibly wins.
    """
    if len(boxes) < 6 or width <= 0:
        return None
    lefts = sorted(x0 for x0, _x1 in boxes)
    minimum = width * 0.12
    candidates = sorted(
        ((right - left, (left + right) / 2)
         for left, right in zip(lefts[:-1], lefts[1:])),
        reverse=True,
    )
    for gap, at in candidates:
        if gap < minimum:
            break
        if not (width * 0.2 < at < width * 0.8):
            continue
        left_count = sum(1 for x in lefts if x <= at)
        if left_count >= 3 and len(lefts) - left_count >= 3:
            return at
    return None


def _crop_columns(image_bytes: bytes, divider: float) -> list[bytes]:
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))
    width, height = image.size
    cut = int(divider)
    strips: list[bytes] = []
    for left, right in ((0, cut), (cut, width)):
        if right - left < width * 0.15:
            continue
        buffer = io.BytesIO()
        image.crop((left, 0, right, height)).save(buffer, format="PNG")
        strips.append(buffer.getvalue())
    return strips or [image_bytes]


def _split_image_columns(image_bytes: bytes, engine) -> list[bytes]:
    """Crop the image into column strips before the real OCR pass.

    Costs one extra OCR pass, and is worth it. RapidOCR merges across the gutter
    - it read "2  48 / forty-eight" together with the "B" beside it as the single
    line "48 forty-eight B" - and once two columns are inside one detected box,
    nothing downstream can separate them. Cropping first makes that impossible.

    A pure-white-channel test is not enough on its own: on a real key page the
    long entries ("1 (the) 13(th) (of) January/ 13.01 / 13.1") reach into the
    channel, so it is a valley rather than a gap. The line boxes say where the
    columns actually start.
    """
    try:
        from PIL import Image

        width = Image.open(io.BytesIO(image_bytes)).size[0]
    except Exception:  # pragma: no cover - depends on build flags
        return [image_bytes]

    try:
        # Ask for coordinates in pixels by passing the pixel size as the page size.
        words, _confidence = engine.recognise(image_bytes, float(width), 1.0)
    except Exception:  # pragma: no cover - engine dependent
        return [image_bytes]

    divider = estimate_divider([(w.x0, w.x1) for w in words], float(width))
    if divider is None:
        return [image_bytes]
    return _crop_columns(image_bytes, divider)


@dataclass
class SheetParse:
    answers: dict[int, AnswerKey] = field(default_factory=dict)
    raw: dict[int, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)
    confidence: float = 0.0
    text: str = ""

    @property
    def found(self) -> int:
        return len(self.answers)


def parse_sheet(
    image_bytes: bytes,
    total: int = 40,
    expected_kinds: dict[int, str] | None = None,
    engine=None,
    page_width: float = ASSUMED_PAGE_WIDTH,
    page_height: float = ASSUMED_PAGE_HEIGHT,
) -> SheetParse:
    """OCR an answer-sheet image and parse it into answers.

    Never raises for a bad image: an unreadable sheet comes back with no answers
    and a warning saying so, which the admin sees as an empty grid to fill in by
    hand rather than as a 500.
    """
    result = SheetParse()

    if engine is None:
        try:
            from exams.importer.ocr import get_engine

            engine = get_engine()
        except Exception as exc:  # pragma: no cover - environment dependent
            result.warnings.append(f"OCR is unavailable: {exc}")
            result.missing = list(range(1, total + 1))
            return result

    # Split the columns in the image before OCR, then read each strip in order.
    strips = _split_image_columns(image_bytes, engine)
    if len(strips) > 1:
        result.warnings.append(f"read as {len(strips)} columns")

    chunks: list[str] = []
    confidences: list[float] = []
    for strip in strips:
        try:
            words, confidence = engine.recognise(strip, page_width, page_height)
        except Exception as exc:  # pragma: no cover - engine/runtime dependent
            result.warnings.append(f"could not read the image: {exc}")
            result.missing = list(range(1, total + 1))
            return result
        if not words:
            continue
        confidences.append(confidence)
        chunks.append(chr(10).join(line.text for line in read_page(words, page_width)))

    result.confidence = sum(confidences) / len(confidences) if confidences else 0.0
    if not chunks:
        result.warnings.append("no text was found in the image")
        result.missing = list(range(1, total + 1))
        return result

    result.text = chr(10).join(chunks)

    parsed = keygrammar.parse_answer_key(
        result.text, total=total, expected_kinds=expected_kinds
    )
    result.answers = parsed.keys
    result.raw = parsed.raw
    result.warnings.extend(parsed.warnings)
    result.missing = parsed.missing

    if parsed.missing:
        result.warnings.append(
            f"{len(parsed.missing)} answer(s) could not be read and need typing in: "
            f"{parsed.missing[:12]}"
        )
    return result


# ---------------------------------------------------------------------------
# JSON round-tripping, for the AnswerKeySheet.answers field
# ---------------------------------------------------------------------------


def answers_to_json(answers: dict[int, AnswerKey]) -> dict[str, dict]:
    """Serialise for storage. JSON object keys are always strings."""
    return {
        str(number): {
            "kind": key.kind,
            "accepted": list(key.accepted),
            "word_limit": key.word_limit,
            "set_id": key.set_id,
            "set_numbers": list(key.set_numbers),
            "select_count": key.select_count,
        }
        for number, key in answers.items()
    }


def answers_from_json(data: dict) -> dict[int, AnswerKey]:
    """Rebuild marking keys from storage, skipping anything malformed.

    Tolerant on purpose: this is read on the marking path, and one bad row
    should cost that question rather than the whole attempt.
    """
    out: dict[int, AnswerKey] = {}
    for number, value in (data or {}).items():
        try:
            index = int(number)
        except (TypeError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        accepted = value.get("accepted") or []
        if not isinstance(accepted, (list, tuple)) or not accepted:
            continue
        try:
            out[index] = AnswerKey(
                kind=value.get("kind") or "text",
                accepted=tuple(str(a) for a in accepted),
                word_limit=value.get("word_limit") or "",
                set_id=value.get("set_id"),
                set_numbers=tuple(value.get("set_numbers") or ()),
                select_count=value.get("select_count"),
            )
        except ValueError:
            continue
    return out
