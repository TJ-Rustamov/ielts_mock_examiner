"""Reading passages as images of the book's own pages.

Retyping a passage from its text layer loses what a reader actually relies on:
paragraph letters set in the margin, italic titles, footnotes and glossaries,
the spacing that separates one paragraph from the next. Showing the printed page
keeps all of it, and works identically for a scanned book with no text layer.

The questions are still parsed into real widgets; only the passage is a picture.

Region detection needs no page map. ``segment`` already routes every line that
comes after a "READING PASSAGE n" header and before the section's first
"Questions N-M" header to the section itself, and chrome stripping has already
removed running headers and page numbers. So the passage region on each page is
simply the box around the section's own lines there.
"""

from __future__ import annotations

from exams.importer import pdfsource

__all__ = ["passage_regions", "render_regions", "PASSAGE_DPI"]

#: Rendering resolution. The Cambridge scans are ~200 DPI, so 150 is sharp on a
#: laptop screen and keeps a page to a couple of hundred kilobytes as JPEG.
PASSAGE_DPI = 150

#: Breathing room around the text, in PDF points.
PADDING = 14.0


def passage_regions(
    section,
    pages: dict[int, list],
    page_sizes: dict[int, tuple[float, float]] | None = None,
    padding: float = PADDING,
) -> list[dict]:
    """The rectangle a passage occupies on each of its pages, in page order.

    `pages` is the page -> lines stream the section was segmented from; lines
    do not carry their page number, and the neighbouring lines are needed so
    padding never slices through the heading above or the questions below.
    Every page uses the same horizontal extent - the widest the passage gets
    anywhere - so the images stack into one column without the text jumping
    left and right between pages.
    """
    line_pages = {id(line): number for number, lines in pages.items() for line in lines}
    by_page: dict[int, list] = {}
    for line in section.lines:
        if not line.words or not line.text.strip():
            continue
        page = line_pages.get(id(line))
        if page is None:
            continue
        by_page.setdefault(page, []).append(line)

    if not by_page:
        return []

    left = min(line.x0 for lines in by_page.values() for line in lines) - padding
    right = max(line.x1 for lines in by_page.values() for line in lines) + padding

    regions: list[dict] = []
    for page in sorted(by_page):
        lines = by_page[page]
        first = min(line.y0 for line in lines)
        last = max(line.y1 for line in lines)
        top = first - padding
        bottom = last + padding

        # Pull the padding back from anything that is not the passage.
        own = {id(line) for line in lines}
        others = [line for line in pages.get(page, [])
                  if id(line) not in own and line.words and line.text.strip()]
        above = [line.y1 for line in others if line.y1 <= first + 1]
        below = [line.y0 for line in others if line.y0 >= last - 1]
        if above:
            top = max(top, max(above) + 1)
        if below:
            bottom = min(bottom, min(below) - 1)

        width, height = (page_sizes or {}).get(page, (None, None))
        x0, y0 = max(0.0, left), max(0.0, top)
        x1 = min(width, right) if width else right
        y1 = min(height, bottom) if height else bottom
        if x1 - x0 < 1 or y1 - y0 < 1:
            continue
        regions.append({"page": page, "bbox": [round(x0, 2), round(y0, 2),
                                               round(x1, 2), round(y1, 2)]})
    return regions


def render_regions(pdf_path: str, regions: list[dict], dpi: int = PASSAGE_DPI):
    """Yield ``(region, jpeg_bytes, width_px, height_px)`` for each region.

    Clip rectangles are in the page's *visible* coordinates - the same space
    ``pdfsource.extract_words`` maps words into - which is also what PyMuPDF's
    ``clip`` expects, so rotated pages (Cambridge 21 is /Rotate 90) need no
    extra transform.
    """
    fitz = pdfsource._fitz()
    document = pdfsource.open_document(pdf_path)
    try:
        for region in regions:
            index = int(region["page"]) - 1
            if not 0 <= index < document.page_count:
                continue
            page = document[index]
            clip = fitz.Rect(*region["bbox"]) & page.rect
            if clip.is_empty:
                continue
            pixmap = page.get_pixmap(dpi=dpi, clip=clip)
            yield region, pixmap.tobytes("jpeg", jpg_quality=85), pixmap.width, pixmap.height
    finally:
        document.close()
