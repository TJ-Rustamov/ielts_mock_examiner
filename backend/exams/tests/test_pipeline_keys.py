"""Tests for how the importer combines readings of a key page.

Covers the policy, not the OCR: which reading supplies an answer for each kind
of page, when a second reading may fill a gap, how agreement is recorded, and
that nothing quoting an answer reaches the job-level warnings.
"""

import unittest
from unittest import mock

from exams import keygrammar
from exams.importer import boilerplate as bp
from exams.importer import pdfsource, pipeline
from exams.importer.layout import Line
from exams.importer.pdfsource import Word
from exams.importer.segment import Document

PAGE = 120


def key_lines(*texts, x=40.0, top=100.0, conf=0.97):
    lines = []
    for index, text in enumerate(texts):
        y = top + index * 14
        lines.append(Line([Word(text, x, y, x + 6 * len(text), y + 10, confidence=conf)]))
    return lines


def module_payload():
    return {
        "kind": "listening",
        "sections": [{
            "order": 1,
            "transcript_text": "We spoke about mining, then education, then notes.",
            "groups": [
                {"type": bp.NOTE_COMPLETION, "first_question": 1, "last_question": 3,
                 "word_limit": "one_word", "letter_range": None, "options": [],
                 "select_count": None,
                 "questions": [{"number": n} for n in (1, 2, 3)]},
                {"type": bp.MCQ_SINGLE, "first_question": 4, "last_question": 4,
                 "word_limit": "", "letter_range": ["A", "C"], "options": [],
                 "select_count": 1, "questions": [{"number": 4}]},
            ],
        }],
    }


def run_keys(lines, source, column_rows=None):
    """Bind `lines` (one key page) to a one-module result, as the pipeline would."""
    document = Document()
    document.back_matter["keys"] = key_lines("TEST 1", "LISTENING") + lines
    pages = {PAGE: document.back_matter["keys"]}
    result = pipeline.ImportResult()
    result.tests = [{"number": 1, "modules": [module_payload()]}]
    chunks = {(1, "listening"): column_rows} if column_rows else {}
    with mock.patch.object(pipeline, "_reread_key_pages", return_value=chunks):
        pipeline._attach_answer_keys(document, result, pages, {PAGE: source}, "x.pdf",
                                     object(), {})
    pipeline._check_answer_keys(result)
    module = result.tests[0]["modules"][0]
    keys = {
        q["number"]: q.get("answer_key")
        for section in module["sections"] for group in section["groups"]
        for q in group["questions"]
    }
    return result, module, keys


def column(*texts, conf=0.96):
    return [
        keygrammar.KeyRow(text, conf, PAGE, (40.0, 100.0 + i * 14, 160.0, 110.0 + i * 14), 0)
        for i, text in enumerate(texts)
    ]


class ReadPriorityTests(unittest.TestCase):
    def test_typeset_page_uses_only_the_flat_reading(self):
        result, module, keys = run_keys(
            key_lines("1 mining", "2 education", "3 notes", "4 B"), pdfsource.NATIVE,
        )
        self.assertEqual(module["key_reads"]["source"], pipeline.KEY_TEXT)
        self.assertEqual(module["key_reads"]["primary"], "layer")
        self.assertEqual(keys[1]["accepted"], ["mining"])
        self.assertEqual(keys[1]["evidence"]["source"], "text")
        self.assertIsNone(keys[1]["evidence"]["confidence"])
        self.assertEqual(module["key_reads"]["reads"], ["layer", "layer_rows"])

    def test_scanned_page_reads_rows_and_the_columns_fill_welded_ones(self):
        result, module, keys = run_keys(
            # Whole-page OCR welded a row from the next column onto Q3.
            key_lines("1 mining", "2 education", "3 notes 4 B"),
            pdfsource.OCR,
            column_rows=column("1 mining", "2 education", "3 notes", "4 B"),
        )
        self.assertEqual(module["key_reads"]["primary"], "layer_rows")
        self.assertEqual(keys[3]["accepted"], ["notes"])
        self.assertEqual(keys[3]["evidence"]["read"], "columns")
        self.assertEqual(keys[4]["accepted"], ["B"])
        self.assertEqual(keys[1]["evidence"]["agreement"], "agree")
        self.assertFalse(keys[1]["evidence"]["independent"])
        self.assertEqual(keys[1]["evidence"]["crop"]["page"], PAGE)
        self.assertEqual(keys[1]["evidence"]["confidence"], 0.97)

    def test_embedded_layer_leads_and_the_column_reading_fills_gaps(self):
        result, module, keys = run_keys(
            # The layer read "2" as "Z" (no digit), so Q2 is missing from it.
            key_lines("1 mining", "Zeducation", "3 notes", "4 B"),
            pdfsource.EMBEDDED,
            column_rows=column("1 mining", "2 education", "3 notes", "4 B"),
        )
        self.assertEqual(module["key_reads"]["primary"], "layer")
        self.assertEqual(keys[2]["accepted"], ["education"])
        self.assertEqual(keys[2]["evidence"]["read"], "columns")
        self.assertTrue(keys[2]["evidence"]["filled"])
        self.assertIn(2, module["key_reads"]["filled"])
        # Different engines agreeing is independent evidence.
        self.assertTrue(keys[1]["evidence"]["independent"])

    def test_disagreement_is_recorded_and_the_module_flagged(self):
        result, module, keys = run_keys(
            key_lines("1 mining", "2 education", "3 notes", "4 B"),
            pdfsource.OCR,
            column_rows=column("1 mining", "2 education", "3 notes", "4 C"),
        )
        self.assertEqual(keys[4]["evidence"]["agreement"], "disagree")
        self.assertIn(4, module["key_reads"]["disagreements"])
        self.assertFalse(module["answer_key_reliable"])
        self.assertEqual(keys[4]["check"]["status"], "check")


class WeldedRowTests(unittest.TestCase):
    """Whole-page OCR joins a row to the one level with it in the next column."""

    def test_a_letter_welded_from_the_next_column_is_cut_off(self):
        lines = []
        for index in range(8):
            y = 100 + index * 14
            left = [Word(str(index + 1), 40, y, 48, y + 10), Word(f"word{index + 1}", 60, y, 110, y + 10)]
            right = [Word(str(index + 21), 300, y, 312, y + 10), Word("B", 320, y, 328, y + 10)]
            if index == 1:
                # "2 word2" welded to a bare set letter in the other column.
                right = [Word("B", 320, y, 328, y + 10)]
            lines.append(Line(left + right))
        rows = pipeline._line_rows(lines, page_of=lambda line: PAGE)
        texts = [row.text for row in rows]
        self.assertIn("2 word2", texts)
        self.assertIn("B", texts)
        self.assertEqual({row.column for row in rows if row.text.startswith("2")}, {0, 1})
        parsed = keygrammar.parse_answer_rows(rows, total=28)
        self.assertEqual(parsed.keys[2].accepted, ("word2",))
        self.assertEqual(parsed.keys[23].accepted, ("B",))


class SelfCheckTests(unittest.TestCase):
    def test_checks_and_trust_counts_are_attached(self):
        result, module, keys = run_keys(
            key_lines("1 mining", "2 education", "3 notes", "4 B"),
            pdfsource.OCR,
            column_rows=column("1 mining", "2 education", "3 notes", "4 B"),
        )
        self.assertEqual(keys[1]["check"]["status"], "trusted")
        self.assertEqual(module["trust"]["trusted"], 4)

    def test_ocr_shape_confusion_is_corrected_on_a_scan(self):
        result, module, keys = run_keys(
            key_lines("1 rnining", "2 education", "3 notes", "4 B"),
            pdfsource.OCR,
            column_rows=column("1 rnining", "2 education", "3 notes", "4 B"),
        )
        self.assertEqual(keys[1]["accepted"], ["mining"])
        self.assertEqual(keys[1]["evidence"]["ocr_accepted"], ["rnining"])
        self.assertEqual(keys[1]["check"]["status"], "check")

    def test_typeset_key_is_never_auto_corrected(self):
        result, module, keys = run_keys(
            key_lines("1 rnining", "2 education", "3 notes", "4 B"), pdfsource.NATIVE,
        )
        self.assertEqual(keys[1]["accepted"], ["rnining"])


class SpoilerTests(unittest.TestCase):
    def test_job_warnings_never_quote_an_answer(self):
        result, module, keys = run_keys(
            key_lines("1 mining", "2 education", "3 notes", "2 weather"),
            pdfsource.OCR,
            column_rows=column("1 mining", "2 education", "3 notes", "2 weather"),
        )
        joined = " ".join(result.warnings).lower()
        for answer in ("mining", "education", "notes", "weather"):
            self.assertNotIn(answer, joined)
        # ...but the module keeps them for the answer sheet.
        self.assertTrue(any("weather" in note for note in module["key_notes"]))


class SplitTests(unittest.TestCase):
    def test_second_reading_starts_each_page_where_the_first_did(self):
        first = key_lines("TEST 2", "READING", "1 alpha")
        line_page = {id(line): 7 for line in first}
        _, starts = pipeline._split_key_items(first, page_of=lambda l: line_page[id(l)])
        self.assertEqual(starts, {7: (2, "reading")})
        # The column re-read lost the headings entirely.
        rows = column("1 alpha", "2 beta")
        rows = [keygrammar.KeyRow(r.text, r.confidence, 7, r.bbox, 0) for r in rows]
        chunks, _ = pipeline._split_key_items(rows, page_of=lambda r: r.page, start_states=starts)
        self.assertEqual(list(chunks), [(2, "reading")])
        self.assertEqual(len(chunks[(2, "reading")]), 2)


if __name__ == "__main__":
    unittest.main()
