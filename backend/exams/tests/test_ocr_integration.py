"""End-to-end check of the scanned-book path with real OCR.

Slow (it OCRs six pages, about half a minute), so it runs only when asked:

    EXAMS_OCR_TESTS=1 python manage.py test exams.tests.test_ocr_integration

Before this work the same synthetic book imported with no tests found and
0/40 answers; the bar here is that nothing is ever wrong and almost nothing is
missing.
"""

import os
import tempfile
import unittest

from .fixtures import synthetic_book

ENABLED = os.getenv("EXAMS_OCR_TESTS") == "1"


@unittest.skipUnless(ENABLED, "set EXAMS_OCR_TESTS=1 to run the OCR integration test")
class ScannedBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from exams.importer import pipeline
        from exams.importer.ocr import get_engine

        cls.directory = tempfile.TemporaryDirectory()
        path = os.path.join(cls.directory.name, "scanned.pdf")
        synthetic_book.make_book(path)
        cls.result = pipeline.run(path, slug="synthetic", ocr_engine=get_engine())

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_book_is_segmented(self):
        self.assertEqual([t["number"] for t in self.result.tests], [1])
        modules = self.result.tests[0]["modules"]
        self.assertEqual([m["kind"] for m in modules], ["listening"])
        groups = [g for s in modules[0]["sections"] for g in s["groups"]]
        self.assertGreaterEqual(len(groups), 6)

    def test_answer_key_is_read_without_a_single_wrong_answer(self):
        correct, wrong, missing, bad = synthetic_book.score(self.result)
        self.assertEqual(wrong, 0, bad)
        self.assertGreaterEqual(correct, 38)

    def test_key_page_was_re_read_column_by_column(self):
        module = self.result.tests[0]["modules"][0]
        self.assertEqual(module["key_reads"]["source"], "ocr")
        self.assertIn("columns", module["key_reads"]["reads"])

    def test_self_checks_leave_only_a_few_answers_to_look_at(self):
        trust = self.result.tests[0]["modules"][0]["trust"]
        self.assertGreaterEqual(trust["trusted"], 25, trust)


if __name__ == "__main__":
    unittest.main()
