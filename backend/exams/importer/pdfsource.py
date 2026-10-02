"""Thin PyMuPDF wrapper: words with coordinates, page rendering, figure crops.

PyMuPDF is imported **lazily**, inside the functions that need it, so the rest
of the backend keeps working when the optional exam-import dependencies are not
installed (see requirements-exams.txt and the INSTALL_EXAMS build arg).

Why coordinates matter: Cambridge pages are typeset in columns, and read as a
flat character stream those columns interleave. Cambridge 21 page 119 puts the
Part 3 option letters *inside* the Part 1 answers. Only the per-word bounding
boxes let ``layout.py`` put them back in reading order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:  # pragma: no cover
    import fitz

#: A page with fewer real words than this is treated as having no usable text
#: layer, and is sent to OCR instead. Cambridge 20 has literally zero.
MIN_NATIVE_WORDS = 50

#: Render DPI for OCR and for the page images shown in the admin review screen.
RENDER_DPI = 300

NATIVE = "native"
OCR = "ocr"


class MissingDependency(RuntimeError):
    """Raised when the exam-import extras are not installed."""


def _fitz():
    # `pymupdf` is the current module name; `fitz` is the legacy alias and warns
    # on import from 1.24 onwards. Prefer the new name, fall back for old pins.
    try:
        import pymupdf

        return pymupdf
    except ImportError:
        pass
    try:
        import fitz

        return fitz
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise MissingDependency(
            "PyMuPDF is required for exam import. Install the extras with "
            "`pip install -r requirements-exams.txt`, or rebuild the backend "
            "image with --build-arg INSTALL_EXAMS=true."
        ) from exc


@dataclass(frozen=True)
class Word:
    """One word with its bounding box, in PDF points, origin top-left.

    `block`/`line`/`order` come from PyMuPDF's own text segmentation, which
    already resolves reading order across columns. They are -1 for words that
    came from OCR, where no such structure exists and geometry is all there is.
    """

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float = 1.0
    block: int = -1
    line: int = -1
    order: int = -1

    @property
    def has_structure(self) -> bool:
        return self.block >= 0 and self.line >= 0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass
class Page:
    number: int                 # 1-based, matches the PDF page number
    width: float
    height: float
    words: list[Word] = field(default_factory=list)
    source: str = NATIVE        # NATIVE | OCR
    rotation: int = 0
    mean_confidence: float = 1.0

    @property
    def text(self) -> str:
        """Words joined in raw extraction order.

        Deliberately NOT reading order — use ``layout.read_page`` for that. This
        exists for quick greps and for the parser-miss log.
        """
        return " ".join(w.text for w in self.words)


def open_document(path: str):
    """Open a PDF. The caller is responsible for closing it."""
    return _fitz().open(path)


def page_has_text_layer(page) -> bool:
    return len(page.get_text("words")) >= MIN_NATIVE_WORDS


def extract_words(page) -> list[Word]:
    """Per-word boxes from the native text layer, in *visible* page coordinates.

    ``get_text("words")`` returns ``(x0, y0, x1, y1, word, block, line, word_no)``
    with coordinates in the **unrotated** mediabox space. Cambridge 21 is a
    landscape mediabox with /Rotate 90, so those coordinates are transposed
    relative to what a reader sees: grouping them by y groups words down a
    column instead of across a line, and the extracted text comes out as word
    salad ("Introduction help the Your Score which Score needed and Listening").

    Mapping each box through ``page.rotation_matrix`` puts it into the same
    space as ``page.rect``, after which x really is horizontal.

    The block/line/word indices are kept, not discarded. PyMuPDF has already
    worked out reading order — on a two-column answer-key page it reads the left
    column top to bottom before the right, which is exactly the problem that
    made the flattened text unusable. Re-deriving that from coordinates is
    strictly worse than using the answer it already has.
    """
    fitz = _fitz()
    matrix = page.rotation_matrix if page.rotation else None
    words: list[Word] = []
    for x0, y0, x1, y1, text, block_no, line_no, word_no in page.get_text("words"):
        text = text.strip()
        if not text:
            continue
        if matrix is not None:
            rect = fitz.Rect(x0, y0, x1, y1) * matrix
            rect.normalize()
            x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
        words.append(
            Word(text, x0, y0, x1, y1,
                 block=int(block_no), line=int(line_no), order=int(word_no))
        )
    return words


def render_page(page, dpi: int = RENDER_DPI) -> bytes:
    """Render a whole page to PNG bytes."""
    pixmap = page.get_pixmap(dpi=dpi)
    return pixmap.tobytes("png")


def render_clip(page, bbox: tuple[float, float, float, float], dpi: int = 200) -> bytes:
    """Render a rectangular region to PNG bytes.

    This is how map/diagram/flow-chart figures are captured, and how the admin
    re-crop works: the new bbox is sent to the server and the region is clipped
    again from the stored PDF, so no image editing happens in the browser.
    """
    rect = _fitz().Rect(*bbox)
    pixmap = page.get_pixmap(clip=rect, dpi=dpi)
    return pixmap.tobytes("png")


def load_pages(
    path: str,
    ocr_engine=None,
    first: int | None = None,
    last: int | None = None,
) -> Iterator[Page]:
    """Yield a :class:`Page` per PDF page, using OCR only where necessary.

    `first`/`last` are 1-based inclusive and let the importer work on one test
    at a time while a parser is being tuned, instead of re-reading the book.
    """
    document = open_document(path)
    try:
        start = (first or 1) - 1
        stop = last if last is not None else document.page_count
        for index in range(start, min(stop, document.page_count)):
            page = document[index]
            rect = page.rect
            if page_has_text_layer(page):
                yield Page(
                    number=index + 1,
                    width=rect.width,
                    height=rect.height,
                    words=extract_words(page),
                    source=NATIVE,
                    rotation=page.rotation,
                )
                continue

            if ocr_engine is None:
                # No text and no OCR available: emit an empty page rather than
                # failing, so the importer can report exactly which pages need
                # OCR instead of dying on the first scanned one.
                yield Page(
                    number=index + 1,
                    width=rect.width,
                    height=rect.height,
                    words=[],
                    source=OCR,
                    rotation=page.rotation,
                )
                continue

            png = render_page(page, RENDER_DPI)
            words, confidence = ocr_engine.recognise(png, rect.width, rect.height)
            yield Page(
                number=index + 1,
                width=rect.width,
                height=rect.height,
                words=words,
                source=OCR,
                rotation=page.rotation,
                mean_confidence=confidence,
            )
    finally:
        document.close()


def describe(path: str) -> dict:
    """Cheap summary used by the import job's first stage and by diagnostics."""
    document = open_document(path)
    try:
        native = 0
        for index in range(document.page_count):
            if page_has_text_layer(document[index]):
                native += 1
        first = document[0].rect if document.page_count else None
        return {
            "pages": document.page_count,
            "pages_with_text": native,
            "pages_needing_ocr": document.page_count - native,
            "width": first.width if first else 0,
            "height": first.height if first else 0,
            "rotation": document[0].rotation if document.page_count else 0,
        }
    finally:
        document.close()
