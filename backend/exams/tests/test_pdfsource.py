"""Tests for page-source classification - typeset, scanned, or scanned with a layer.

Builds tiny PDFs in memory with PyMuPDF, so no book needs committing.
"""

import io
import unittest

try:
    import pymupdf
except ImportError:  # pragma: no cover - exam extras not installed
    pymupdf = None

from exams.importer import pdfsource


def _png(width=400, height=560):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("L", (width, height), 235).save(buffer, format="PNG")
    return buffer.getvalue()


def _words(page, count=80, render_mode=0):
    """`count` words in rows of ten, well inside the page."""
    for row in range(0, count, 10):
        text = " ".join(f"word{n}" for n in range(row, min(row + 10, count)))
        page.insert_text((40, 60 + row * 1.5), text, fontsize=8, render_mode=render_mode)


@unittest.skipIf(pymupdf is None, "PyMuPDF not installed")
class PageSourceTests(unittest.TestCase):
    def document(self):
        return pymupdf.open()

    def test_typeset_page_is_native(self):
        doc = self.document()
        page = doc.new_page(width=595, height=842)
        _words(page)
        self.assertEqual(pdfsource.classify_page(page), pdfsource.NATIVE)

    def test_scan_with_a_text_layer_is_embedded_ocr(self):
        doc = self.document()
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=_png())
        # The invisible layer an OCR tool adds over the picture.
        _words(page, render_mode=3)
        self.assertGreater(pdfsource.image_coverage(page), 0.95)
        self.assertEqual(pdfsource.classify_page(page), pdfsource.EMBEDDED)

    def test_scan_without_text_needs_ocr(self):
        doc = self.document()
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=_png())
        self.assertEqual(pdfsource.classify_page(page), pdfsource.OCR)

    def test_a_figure_on_a_typeset_page_is_not_a_scan(self):
        doc = self.document()
        page = doc.new_page(width=595, height=842)
        _words(page)
        page.insert_image(pymupdf.Rect(100, 300, 300, 450), stream=_png(200, 150))
        self.assertEqual(pdfsource.classify_page(page), pdfsource.NATIVE)

    def test_describe_counts_each_kind(self):
        doc = self.document()
        typeset = doc.new_page(width=595, height=842)
        _words(typeset)
        scan = doc.new_page(width=595, height=842)
        scan.insert_image(scan.rect, stream=_png())
        layered = doc.new_page(width=595, height=842)
        layered.insert_image(layered.rect, stream=_png())
        _words(layered)
        path = self.enterContext(_temp_pdf(doc))
        summary = pdfsource.describe(path)
        self.assertEqual(
            (summary["pages_with_text"], summary["pages_embedded_ocr"],
             summary["pages_needing_ocr"]),
            (1, 1, 1),
        )


class _temp_pdf:
    def __init__(self, doc):
        self.doc = doc

    def __enter__(self):
        import tempfile

        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        handle.close()
        self.doc.save(handle.name)
        self.path = handle.name
        return handle.name

    def __exit__(self, *exc):
        import os

        os.unlink(self.path)
        return False


if __name__ == "__main__":
    unittest.main()
