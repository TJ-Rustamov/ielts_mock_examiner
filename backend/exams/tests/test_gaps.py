"""Tests for gap-slot detection.

The fixtures mirror real Cambridge 21 note- and table-completion lines,
including the OCR damage seen on the low-resolution scans.
"""

import unittest

from exams.importer.gaps import to_template, template_lines
from exams.importer.layout import Line
from exams.importer.pdfsource import Word


def line(*tokens, start=40.0, y=100.0, gap=6.0, char=7.0):
    """Build a Line from tokens, laying them out left to right.

    A token may be a plain string, or (text, leading_gap) to force a wide space.
    """
    words = []
    x = start
    for token in tokens:
        text, lead = token if isinstance(token, tuple) else (token, gap)
        x += lead
        width = char * len(text)
        words.append(Word(text, x, y, x + width, y + 12))
        x += width
    return Line(words)


class DotRunTests(unittest.TestCase):
    def test_number_then_dots(self):
        result = to_template(line("7", "...........................", "and", "toiletries"),
                             expected=range(1, 11))
        self.assertEqual(result.text, "{{Q7}} and toiletries")
        self.assertEqual(result.numbers, [7])

    def test_number_fused_to_dots(self):
        result = to_template(line("7...........................", "and", "toiletries"),
                             expected=range(1, 11))
        self.assertEqual(result.text, "{{Q7}} and toiletries")

    def test_blank_in_the_middle_of_a_sentence(self):
        result = to_template(
            line("basic", "theory", "e.g.", "understanding", "the", "2", ".........",
                 "and", "tides"),
            expected=range(1, 11),
        )
        self.assertEqual(
            result.text, "basic theory e.g. understanding the {{Q2}} and tides"
        )

    def test_several_blanks_on_one_line(self):
        result = to_template(
            line("1", ".........", "people", "and", "2", ".........", "tides"),
            expected=range(1, 11),
        )
        self.assertEqual(result.numbers, [1, 2])
        self.assertIn("{{Q1}}", result.text)
        self.assertIn("{{Q2}}", result.text)

    def test_dashes_and_underscores_count_as_answer_space(self):
        # OCR at 150 DPI regularly reads a dot run as dashes.
        for run in ("-----------", "___________", "————"):
            result = to_template(line("7", run, "towel"), expected=range(1, 11))
            self.assertEqual(result.text, "{{Q7}} towel", run)


class GeometricTests(unittest.TestCase):
    def test_wide_gap_is_a_blank_when_the_dots_are_lost(self):
        # The dots did not survive extraction, but the space they occupied did.
        result = to_template(
            line("Bring", "suitable", "clothing,", "a", "7", ("and", 120.0), "toiletries"),
            expected=range(1, 11),
        )
        self.assertEqual(result.text, "Bring suitable clothing, a {{Q7}} and toiletries")
        self.assertTrue(result.blanks[0].geometric)

    def test_trailing_number_at_the_end_of_a_line(self):
        result = to_template(line("Online", "training", "9"), expected=range(1, 11))
        self.assertEqual(result.text, "Online training {{Q9}}")

    def test_ordinary_spacing_is_not_a_blank(self):
        result = to_template(
            line("the", "course", "costs", "200", "pounds"), expected=range(1, 11)
        )
        self.assertEqual(result.text, "the course costs 200 pounds")
        self.assertEqual(result.numbers, [])


class NumberScopeTests(unittest.TestCase):
    def test_a_number_outside_the_group_range_is_not_a_blank(self):
        # "max 12 people" is content; the group only owns questions 1-10.
        result = to_template(
            line("small", "groups", "(max", "12", "people)"), expected=range(1, 11)
        )
        self.assertEqual(result.text, "small groups (max 12 people)")
        self.assertEqual(result.numbers, [])

    def test_the_same_number_inside_the_range_is_a_blank(self):
        result = to_template(
            line("small", "groups", "(max", "1", ".........", "people)"),
            expected=range(1, 11),
        )
        self.assertEqual(result.numbers, [1])

    def test_without_a_range_bare_trailing_numbers_still_resolve(self):
        result = to_template(line("cost", "5", "........."))
        self.assertEqual(result.numbers, [5])


class ProblemReportingTests(unittest.TestCase):
    def test_answer_space_with_no_number_is_flagged(self):
        result = to_template(line("something", "..........."), expected=range(1, 11))
        self.assertIn("{{Q?}}", result.text)
        self.assertTrue(result.warnings)

    def test_missing_question_numbers_are_reported(self):
        lines = [
            line("1", ".........", "people"),
            line("2", ".........", "tides"),
        ]
        _templates, warnings = template_lines(lines, expected=range(1, 7))
        joined = " ".join(warnings)
        self.assertIn("no answer space found", joined)
        for missing in (3, 4, 5, 6):
            self.assertIn(str(missing), joined)

    def test_complete_group_reports_nothing(self):
        lines = [line(str(n), ".........", "x") for n in range(1, 5)]
        _templates, warnings = template_lines(lines, expected=range(1, 5))
        self.assertEqual(warnings, [])

    def test_empty_line(self):
        self.assertEqual(to_template(Line([])).text, "")


class RealisticNoteCompletionTests(unittest.TestCase):
    """Cambridge 21 Test 1 Listening, questions 7-10."""

    def test_bulleted_notes_produce_one_blank_each(self):
        lines = [
            line("Participants", "must", "be", "able", "to", "swim."),
            line("Bring", "suitable", "clothing,", "a", "7", "...........", "and",
                 "toiletries", "(e.g.", "shampoo)."),
            line("There", "is", "a", "8", "...........", "at", "the", "club."),
            line("Online", "training", "9", "...........", "are", "recommended."),
            line("10", "...........", "are", "available", "for", "course",
                 "participants."),
        ]
        templates, warnings = template_lines(lines, expected=range(7, 11))
        self.assertEqual(warnings, [])
        found = [n for t in templates for n in t.numbers]
        self.assertEqual(found, [7, 8, 9, 10])
        self.assertEqual(
            templates[1].text,
            "Bring suitable clothing, a {{Q7}} and toiletries (e.g. shampoo).",
        )
        self.assertEqual(templates[4].text,
                         "{{Q10}} are available for course participants.")


if __name__ == "__main__":
    unittest.main()


class OcrBoxTests(unittest.TestCase):
    """RapidOCR can hand over a whole detected line as one box."""

    def ocr_line(self, *texts):
        words, x = [], 40.0
        for index, text in enumerate(texts):
            width = 7.0 * len(text)
            words.append(Word(text, x, 100, x + width, 112, confidence=0.9, segment=index))
            x += width + 6
        return Line(words)

    def test_number_and_dots_inside_one_box(self):
        result = to_template(self.ocr_line("7 ......... and toiletries"), range(1, 11))
        self.assertEqual(result.numbers, [7])
        self.assertIn("{{Q7}}", result.text)

    def test_number_glued_to_the_word_before_it(self):
        # "the 1 ......" with both the dots and the space lost.
        result = to_template(self.ocr_line("Itemisaboutthe1"), range(1, 11))
        self.assertEqual(result.numbers, [1])

    def test_native_text_is_never_unglued(self):
        native = Line([Word("COVID19", 40, 100, 90, 112)])
        self.assertEqual(to_template(native, range(1, 40)).numbers, [])
