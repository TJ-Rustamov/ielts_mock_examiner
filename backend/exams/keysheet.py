"""Turn an uploaded answer-sheet image into a module's 40 answers.

Why this exists rather than reading the key out of the book's PDF: Cambridge
typesets its key pages in columns that sometimes interleave when the PDF text is
flattened â€” Cambridge 21 page 120 puts the Part 3 option letters inside the
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
import re
from dataclasses import dataclass, field

from exams import keygrammar
from exams.importer.layout import Line, read_page
from exams.marking import AnswerKey

__all__ = [
    "SheetParse",
    "ColumnRead",
    "parse_sheet",
    "ocr_columns",
    "rows_from_columns",
    "find_image_gutters",
    "estimate_divider",
    "estimate_dividers",
    "line_boxes",
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


#: A column needs at least this many rows that start with a digit. Key columns
#: always do; a strip of answers cut away from its numbers never does, which
#: is what stops a recursive split between a number column and its answers.
MIN_NUMBERED_ROWS = 3

#: Key pages run to three columns at most (landscape spreads).
MAX_COLUMNS = 3


def line_boxes(words) -> list[tuple[float, float, str]]:
    """Collapse words into (x0, x1, text) per detected line.

    Column detection clusters on left edges, which only works on whole lines:
    every line in a column starts at its margin, whereas the words inside a
    line start anywhere. OCR words are grouped by the detection box they were
    cut from, native words by PyMuPDF's (block, line); anything else stands
    alone.
    """
    groups: dict[tuple, list] = {}
    order: list[tuple] = []
    for index, word in enumerate(words):
        if getattr(word, "segment", -1) >= 0:
            key = ("s", word.segment)
        elif getattr(word, "has_structure", False):
            key = ("b", word.block, word.line)
        else:
            key = ("w", index)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(word)
    out = []
    for key in order:
        members = sorted(groups[key], key=lambda w: w.x0)
        out.append((
            min(w.x0 for w in members),
            max(w.x1 for w in members),
            " ".join(w.text for w in members),
        ))
    return out


def _starts_with_number(text: str) -> bool:
    token = (text or "").split()[0] if (text or "").split() else ""
    number, real_digit = keygrammar.repair_question_number(token.rstrip(".)&"), 99)
    return number is not None and real_digit


def estimate_dividers(
    boxes: list[tuple[float, float, str]],
    left: float,
    right: float,
    max_columns: int = MAX_COLUMNS,
) -> list[float]:
    """Column dividers between `left` and `right`, found recursively.

    Each split must leave real key columns on both sides - at least
    ``MIN_NUMBERED_ROWS`` lines starting with a question number - so a gap
    between the numbers and their answers is never mistaken for a gutter.
    """
    if max_columns < 2:
        return []
    inside = [b for b in boxes if left <= b[0] < right]
    width = right - left
    at = estimate_divider([(b[0] - left, b[1] - left) for b in inside], width)
    if at is None:
        return []
    return _split_at(boxes, left, right, at + left, inside, max_columns)


def _split_at(boxes, left, right, at, inside, max_columns) -> list[float]:
    """Accept a divider at `at` if both sides are real key columns; recurse."""
    left_side = [b for b in inside if b[0] <= at]
    right_side = [b for b in inside if b[0] > at]
    if any(b[2] for b in inside):
        if sum(_starts_with_number(b[2]) for b in left_side) < MIN_NUMBERED_ROWS:
            return []
        if sum(_starts_with_number(b[2]) for b in right_side) < MIN_NUMBERED_ROWS:
            return []
    found = [at]
    remaining = max_columns - 2
    for side_left, side_right in ((left, at), (at, right)):
        if remaining <= 0:
            break
        extra = estimate_dividers(boxes, side_left, side_right, remaining + 1)
        found.extend(extra)
        remaining -= len(extra)
    return sorted(found)


_NUMBER_TOKEN = re.compile(r"^(\d{1,2})(?:&\d{1,2})*$")


def number_dividers(words, page_width: float, total: int = 40) -> list[float]:
    """Column dividers from where the question numbers sit.

    The fallback for a page whose detected lines run across the gutter - OCR
    read "1 69 / ten   21&22 IN EITHER ORDER" as one line, so every line box
    starts at the left margin and the line-based search finds nothing. The
    individual number tokens still carry their own x position, and the
    numbers of each column line up on its margin.
    """
    xs = []
    for word in words:
        match = _NUMBER_TOKEN.match(word.text.strip())
        if match and 1 <= int(match.group(1)) <= total:
            xs.append(word.x0)
    if len(xs) < 2 * MIN_NUMBERED_ROWS or page_width <= 0:
        return []
    xs.sort()
    # Columns: runs of number positions closer than this to each other.
    join = page_width * 0.05
    clusters: list[list[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] <= join:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    # A column has many numbers; a number inside an answer is a stray.
    columns = [c for c in clusters if len(c) >= MIN_NUMBERED_ROWS * 2]
    if len(columns) < 2:
        return []
    columns = columns[:MAX_COLUMNS]
    # Cut just left of each later column's numbers.
    return [max(c[0] - page_width * 0.015, 0.0) for c in columns[1:]]


def _recognise(engine, image, page_width: float, page_height: float, preprocess: bool):
    """Call an engine on an array, falling back to the plain PNG protocol.

    :class:`~exams.importer.ocr.RapidOcrEngine` takes arrays and a
    preprocessing switch; the :class:`~exams.importer.ocr.OcrEngine` protocol
    only promises PNG bytes, so anything else gets those.
    """
    try:
        return engine.recognise(image, page_width, page_height, preprocess_image=preprocess)
    except TypeError:
        return engine.recognise(_to_png(image), page_width, page_height)


def _to_png(array) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class ColumnRead:
    """A page read strip by strip. Lines are in page points, columns left to right."""

    columns: list[list[Line]] = field(default_factory=list)
    dividers: list[float] = field(default_factory=list)
    confidence: float = 0.0
    deskew_angle: float = 0.0


def ocr_columns(
    image_bytes: bytes,
    engine,
    page_width: float,
    page_height: float,
    words=None,
) -> ColumnRead:
    """OCR a key page one column strip at a time.

    The page is cleaned once (deskew first, so the gutters are vertical), the
    dividers are found from line boxes - `words` if the caller already has an
    OCR pass of this exact render, otherwise a fresh pass - and each strip is
    recognised on its own. Nothing can merge across a gutter that was cut
    before recognition ran.

    Never raises for a bad image; an unreadable page returns no columns.
    """
    read = ColumnRead()
    try:
        from exams.importer import ocr as ocr_module

        if ocr_module.preprocessing_enabled():
            array, read.deskew_angle = ocr_module.preprocess(image_bytes)
        else:
            array = ocr_module._load_rgb(image_bytes)
    except Exception:  # pragma: no cover - missing cv2/numpy
        return read

    pixel_height, pixel_width = array.shape[:2]
    if not pixel_width or page_width <= 0:
        return read
    px_per_pt = pixel_width / page_width

    try:
        if words is None:
            words, _confidence = _recognise(engine, array, page_width, page_height, False)
        # Number positions first: they still show the columns when OCR has
        # run whole rows across the gutter. Line edges otherwise.
        dividers = number_dividers(words, page_width) or estimate_dividers(
            line_boxes(words), 0.0, page_width
        )
    except Exception:  # pragma: no cover - engine/runtime dependent
        return read
    read.dividers = dividers

    edges = [0.0, *dividers, page_width]
    confidences: list[float] = []
    for x0_pt, x1_pt in zip(edges[:-1], edges[1:]):
        x0_px, x1_px = int(round(x0_pt * px_per_pt)), int(round(x1_pt * px_per_pt))
        if x1_px - x0_px < max(8, pixel_width * 0.08):
            continue
        strip = array[:, x0_px:x1_px]
        strip_width = (x1_px - x0_px) / px_per_pt
        try:
            local, confidence = _recognise(engine, strip, strip_width, page_height, False)
        except Exception:  # pragma: no cover - engine/runtime dependent
            continue
        if not local:
            read.columns.append([])
            continue
        confidences.append(confidence)
        lines = read_page(local, strip_width)
        offset = x0_px / px_per_pt
        read.columns.append([
            Line([_shift(word, offset) for word in line.words]) for line in lines
        ])
    read.confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return read


def _shift(word, dx: float):
    from dataclasses import replace

    return replace(word, x0=word.x0 + dx, x1=word.x1 + dx)


def rows_from_columns(read: ColumnRead, page: int | None = None) -> list[keygrammar.KeyRow]:
    """Flatten a column read into key rows, column by column."""
    rows: list[keygrammar.KeyRow] = []
    for column, lines in enumerate(read.columns):
        for line in lines:
            if not line.words or not line.text.strip():
                continue
            rows.append(keygrammar.KeyRow(
                text=line.text,
                confidence=min(w.confidence for w in line.words),
                page=page,
                bbox=(line.x0, line.y0, line.x1, line.y1),
                column=column,
            ))
    return rows


@dataclass
class SheetParse:
    answers: dict[int, AnswerKey] = field(default_factory=dict)
    raw: dict[int, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)
    confidence: float = 0.0
    text: str = ""
    #: Per answer: lowest OCR confidence of its rows, and where it sits in
    #: the image (in the page-point space of ``page_width``).
    row_confidence: dict[int, float] = field(default_factory=dict)
    crops: dict[int, dict] = field(default_factory=dict)

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

    `page_height` is accepted for compatibility; the height actually used
    follows the image's aspect ratio at `page_width`.

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
    # The page size keeps the image's own aspect ratio, so geometry in points
    # means the same thing as on a PDF page.
    try:
        from PIL import Image

        pixel_width, pixel_height = Image.open(io.BytesIO(image_bytes)).size
        page_height = page_width * pixel_height / max(pixel_width, 1)
    except Exception:
        result.warnings.append("the image could not be opened")
        result.missing = list(range(1, total + 1))
        return result

    read = ocr_columns(image_bytes, engine, page_width, page_height)
    if len(read.columns) > 1:
        result.warnings.append(f"read as {len(read.columns)} columns")
    rows = rows_from_columns(read)
    result.confidence = read.confidence
    if not rows:
        result.warnings.append("no text was found in the image")
        result.missing = list(range(1, total + 1))
        return result

    result.text = chr(10).join(row.text for row in rows)

    # Row by row first - it is order-independent and knows where each answer
    # sits - then the flat scanner for anything the rows could not place.
    parsed = keygrammar.parse_answer_rows(rows, total=total, expected_kinds=expected_kinds)
    flat = keygrammar.parse_answer_key(result.text, total=total, expected_kinds=expected_kinds)
    for number, key in flat.keys.items():
        if number not in parsed.keys and number not in parsed.conflicts:
            parsed.keys[number] = key
            parsed.raw[number] = flat.raw.get(number, "")
    result.answers = parsed.keys
    result.raw = parsed.raw
    result.row_confidence = parsed.confidence
    result.crops = parsed.crops
    result.warnings.extend(parsed.warnings)
    result.missing = sorted(set(range(1, total + 1)) - set(parsed.keys))

    if result.missing:
        result.warnings.append(
            f"{len(result.missing)} answer(s) could not be read and need typing in: "
            f"{result.missing[:12]}"
        )
    return result


def same_answer(a: dict, b: dict) -> bool:
    """Whether two stored answers (JSON form) accept the same thing."""
    def signature(value: dict) -> tuple:
        accepted = {" ".join(str(x).lower().split()) for x in (value or {}).get("accepted") or []}
        return ((value or {}).get("kind") == "letter_set", tuple(sorted(accepted)))

    return signature(a) == signature(b)


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
