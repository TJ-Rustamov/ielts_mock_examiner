"""Turn positioned words back into reading order.

This is the module page 119 of Cambridge 21 exists to justify. Read as a flat
stream, that page interleaves its Part 1 and Part 3 columns so badly that the
Part 3 option letters land inside the Part 1 answers, and no regex can undo it.
Given per-word bounding boxes, though, it is ordinary geometry: find the
vertical gutters, assign each line to a column, read the columns in order.

Pure module - no Django, no PyMuPDF. It takes :class:`Word` objects and returns
text, so it is testable with hand-built fixtures and no PDF at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

from exams.importer.pdfsource import Word

__all__ = [
    "Line",
    "Column",
    "build_lines",
    "find_gutters",
    "split_columns",
    "read_page",
    "strip_repeated_chrome",
]

#: A gutter must be at least this fraction of the page width to count as a
#: column separator rather than ordinary word spacing.
MIN_GUTTER_RATIO = 0.035

#: ...and must be clear over at least this fraction of the page's text height,
#: so a single short line's indentation is not mistaken for a column break.
MIN_GUTTER_COVERAGE = 0.55

#: Two words belong to the same line when their vertical centres are within
#: this fraction of the line height.
LINE_TOLERANCE = 0.6

#: A word must reach this far into a gutter (as a fraction of its width, from
#: either edge) before its line counts as crossing the columns.
GUTTER_CORE_MARGIN = 0.25

#: A block must cover this much of the page width before it counts as spanning
#: the columns rather than being a long entry in one of them.
FULL_WIDTH_RATIO = 0.6


@dataclass
class Line:
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return min(w.x0 for w in self.words)

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def y0(self) -> float:
        return min(w.y0 for w in self.words)

    @property
    def y1(self) -> float:
        return max(w.y1 for w in self.words)

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Column:
    x0: float
    x1: float
    lines: list[Line] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def build_lines(words: list[Word]) -> list[Line]:
    """Group words into visual lines by vertical position, then sort by x.

    Sorting each line by x is what repairs the "15 16 17 18 19 20" /
    "Engine house ... Ponies" split seen on the map-labelling page, where the
    numbers and their labels arrive as two separate runs.
    """
    if not words:
        return []

    heights = [w.height for w in words if w.height > 0]
    tolerance = (median(heights) if heights else 10.0) * LINE_TOLERANCE

    lines: list[Line] = []
    for word in sorted(words, key=lambda w: (w.cy, w.x0)):
        placed = False
        for line in reversed(lines):
            if abs(line.cy - word.cy) <= tolerance:
                line.words.append(word)
                placed = True
                break
        if not placed:
            lines.append(Line([word]))

    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    lines.sort(key=lambda ln: (ln.y0, ln.x0))
    return lines


def find_gutters(
    words: list[Word],
    page_width: float,
    bin_size: float = 2.0,
) -> list[tuple[float, float]]:
    """Locate vertical whitespace channels that separate columns.

    Works on x-occupancy: bin the page horizontally, mark every bin any word
    overlaps, then look for unmarked runs that are both wide enough and clear
    over most of the page's text height.
    """
    if not words or page_width <= 0:
        return []

    bins = max(1, int(page_width / bin_size) + 1)
    # For each x bin, the total vertical extent covered by words in it.
    coverage: list[float] = [0.0] * bins
    top = min(w.y0 for w in words)
    bottom = max(w.y1 for w in words)
    text_height = max(1.0, bottom - top)

    for word in words:
        start = max(0, int(word.x0 / bin_size))
        stop = min(bins - 1, int(word.x1 / bin_size))
        for index in range(start, stop + 1):
            coverage[index] += word.height

    # A bin counts as occupied only when text stacks up in it to a decent
    # fraction of the densest column. An absolute threshold fails here: one
    # full-width heading crosses the channel and would mark every bin occupied,
    # hiding the gutter on exactly the pages that have section headings.
    densest = max(coverage)
    threshold = densest * 0.15
    occupied = [c > threshold for c in coverage]

    min_width = page_width * MIN_GUTTER_RATIO
    gutters: list[tuple[float, float]] = []
    run_start: int | None = None
    for index, is_occupied in enumerate(occupied):
        if not is_occupied and run_start is None:
            run_start = index
        elif is_occupied and run_start is not None:
            gutters.append((run_start, index))
            run_start = None
    if run_start is not None:
        gutters.append((run_start, bins))

    out: list[tuple[float, float]] = []
    for start, stop in gutters:
        x0, x1 = start * bin_size, stop * bin_size
        if x1 - x0 < min_width:
            continue
        # Ignore the page margins; only interior channels split columns.
        if x0 <= bin_size or x1 >= page_width - bin_size:
            continue
        if _gutter_is_clear(words, x0, x1, top, bottom):
            out.append((x0, x1))
    return out


def _gutter_is_clear(
    words: list[Word],
    x0: float,
    x1: float,
    top: float,
    bottom: float,
) -> bool:
    """True when the channel is uninterrupted down most of the page.

    A heading that spans the full width crosses every gutter, so a handful of
    crossings is tolerated; a channel that is repeatedly crossed is just word
    spacing and must not be treated as a column break.
    """
    height = max(1.0, bottom - top)
    crossing_height = sum(
        w.height for w in words if w.x0 < x1 and w.x1 > x0
    )
    return (1 - crossing_height / height) >= MIN_GUTTER_COVERAGE


def split_columns(lines: list[Line], gutters: list[tuple[float, float]],
                  page_width: float) -> list[Column]:
    """Assign lines to columns. Full-width lines become their own block.

    Returned in reading order: a full-width line (a heading) is emitted where it
    occurs, and the column blocks between headings are read left to right.
    """
    if not gutters:
        return [Column(0.0, page_width, list(lines))]

    boundaries = [0.0]
    for x0, x1 in gutters:
        boundaries.append((x0 + x1) / 2)
    boundaries.append(page_width)
    spans = list(zip(boundaries[:-1], boundaries[1:]))

    blocks: list[Column] = []
    pending: list[list[Line]] = [[] for _ in spans]

    def flush() -> None:
        for (cx0, cx1), bucket in zip(spans, pending):
            if bucket:
                blocks.append(Column(cx0, cx1, list(bucket)))
        for bucket in pending:
            bucket.clear()

    def crosses_gutter(word: Word) -> bool:
        # Only the middle of the channel counts. A heading that really spans
        # the columns runs straight through it, whereas the longest answer in
        # a column routinely pokes a few points past where the occupancy
        # histogram put the channel's edge - and treating that row as
        # full-width welds it to the row beside it in the other column.
        for gx0, gx1 in gutters:
            margin = (gx1 - gx0) * GUTTER_CORE_MARGIN
            if word.x0 < gx1 - margin and word.x1 > gx0 + margin:
                return True
        return False

    for line in lines:
        # A line built across the page may be two side-by-side column rows that
        # merely share a baseline. The discriminator is the gutter itself: real
        # full-width text has a word sitting in or across the channel, whereas
        # parallel column rows leave it empty. Without this split, the two
        # columns are welded together exactly as the flat text stream does.
        if any(crosses_gutter(word) for word in line.words):
            flush()
            blocks.append(Column(line.x0, line.x1, [line]))
            continue

        for index, (cx0, cx1) in enumerate(spans):
            part = [w for w in line.words if cx0 <= w.cx < cx1]
            if part:
                pending[index].append(Line(part))

    flush()
    return blocks


def _block_boxes(words: list[Word]) -> tuple[list[int], dict[int, list[Word]]]:
    blocks: dict[int, list[Word]] = {}
    order: list[int] = []
    for word in words:
        if word.block not in blocks:
            blocks[word.block] = []
            order.append(word.block)
        blocks[word.block].append(word)
    return order, blocks


def lines_from_structure(words: list[Word], page_width: float = 0.0) -> list[Line]:
    """Group words using PyMuPDF's own block segmentation.

    Lines are rebuilt geometrically *within* each block, because PyMuPDF's line
    splitting inside a block is finer than a reader's idea of a line - on a
    two-column key page it emits "1" and "10/ten" separately, and on a question
    page it separates an item number from its text. A block sits within one
    column, so geometry inside one is safe and rejoins those.

    Block ORDER is PyMuPDF's, deliberately.

    I tried reordering blocks into columns (cluster block left edges, read the
    left column before the right). It did fix Cambridge 21 page 120, whose Part
    1 and Part 3 columns interleave - but it regressed the other seven key
    pages, taking reliable answer keys from 7 of 8 down to 0 of 8. PyMuPDF's own
    ordering is right far more often than any clustering heuristic I produced,
    and the cost of being wrong here is a wrong answer key.

    So page 120 stays unparsed and is reported as unreliable rather than
    guessed at. The dependable fix for it is the admin-uploaded answer sheet,
    not a cleverer heuristic.
    """
    order, blocks = _block_boxes(words)
    lines: list[Line] = []
    for block in order:
        lines.extend(build_lines(blocks[block]))
    return lines


def read_page(words: list[Word], page_width: float) -> list[Line]:
    """Words -> lines in reading order.

    Uses the PDF's own text structure when present; falls back to geometry
    (line clustering plus gutter detection) for OCR output, which has none.
    """
    if not words:
        return []
    if any(word.has_structure for word in words):
        return lines_from_structure(
            [w for w in words if w.has_structure], page_width
        )

    lines = build_lines(words)
    if not lines:
        return []
    gutters = find_gutters(words, page_width)
    columns = split_columns(lines, gutters, page_width)
    ordered: list[Line] = []
    for column in columns:
        ordered.extend(column.lines)
    return ordered


# ---------------------------------------------------------------------------
# Running headers and footers
# ---------------------------------------------------------------------------

#: Chrome is looked for among this many lines at the top and bottom of a page.
#: Position-in-page beats an absolute margin band: Cambridge 21's running header
#: sits around y=170-207 on an 842pt page (~22% down), because the rotated
#: landscape layout leaves wide margins. An 8%-of-height band missed it
#: entirely, so every "Test 1" header was read as the start of a new test.
CHROME_LINES = 2

#: A line must repeat on at least this share of pages to count as chrome. Low,
#: because a per-skill header ("Listening") only appears on its own module's
#: pages - roughly a sixth of the book.
CHROME_FREQUENCY = 0.12

_NORMALISE = re.compile(r"\d+")


def _chrome_key(text: str) -> str:
    """Normalised form for comparing running headers across pages.

    Digits collapse to '#' so "Test 1" and "Test 3", or page numbers 16 and 17,
    are recognised as the same repeated element.
    """
    return _NORMALISE.sub("#", " ".join(text.split()).lower())


def strip_repeated_chrome(
    pages: dict[int, list[Line]],
    page_height: float,
    protect=None,
) -> dict[int, list[Line]]:
    """Drop running headers, footers and page numbers.

    Frequency-based rather than pattern-based on purpose: matching ``^Test \\d$``
    only works for books that say "Test", and breaks the moment OCR renders it
    "Tesl". Anything that appears in the same band on a third of the pages is
    chrome, whatever it says.
    """
    if not pages:
        return pages

    def edge_indexes(lines: list[Line]) -> set[int]:
        count = len(lines)
        # On a sparse page, "first two and last two" would cover every line and
        # body text could be mistaken for chrome. Narrow the span so the middle
        # of a short page is never a candidate.
        span = CHROME_LINES if count > 2 * CHROME_LINES else 1
        return set(range(min(span, count))) | set(range(max(0, count - span), count))

    def is_protected(line: Line) -> bool:
        return bool(protect and protect(line.text))

    counts: dict[str, set[int]] = {}
    for number, lines in pages.items():
        edges = edge_indexes(lines)
        for index, line in enumerate(lines):
            if index in edges and not is_protected(line):
                counts.setdefault(_chrome_key(line.text), set()).add(number)

    threshold = max(3, int(len(pages) * CHROME_FREQUENCY))
    chrome = {key for key, seen in counts.items() if len(seen) >= threshold}

    cleaned: dict[int, list[Line]] = {}
    for number, lines in pages.items():
        edges = edge_indexes(lines)
        kept = [
            line for index, line in enumerate(lines)
            if is_protected(line)
            or not (index in edges and _chrome_key(line.text) in chrome)
        ]
        cleaned[number] = kept
    return cleaned
