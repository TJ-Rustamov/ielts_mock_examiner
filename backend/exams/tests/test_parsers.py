"""Tests for per-type question-group parsing.

Fixtures are modelled on real Cambridge 21 groups. They run through the real
segmenter, so what is exercised is the whole path from page lines to a parsed
group — only the PDF reading itself is stubbed out.
"""

import unittest

from exams.importer import boilerplate as bp
from exams.importer.parsers import parse_group
from exams.importer.segment import LISTENING, READING, segment

from exams.importer.layout import Line
from exams.importer.pdfsource import Word


def page(*texts, width=600.0):
    """Build a page whose lines are split into per-word boxes.

    Unlike the segmentation fixtures, these tests need real word geometry: gap
    detection works on the spacing between words, so a line represented as one
    giant word box would never yield a blank.
    """
    lines = []
    for index, text in enumerate(texts):
        y = 50.0 + index * 20
        words = []
        x = 40.0
        for token in text.split(" "):
            if not token:
                continue
            width_of = 6.0 * len(token)
            words.append(Word(token, x, y, x + width_of, y + 12))
            x += width_of + 5.0
        if words:
            lines.append(Line(words))
    return lines


def first_group(pages, skill=READING, section=0, group=0):
    document = segment(pages)
    module = document.test(1).modules[skill]
    return module.sections[section].groups[group]


class CompletionTests(unittest.TestCase):
    """Cambridge 21 Test 1 Listening, questions 7-10."""

    def setUp(self):
        pages = {
            1: page(
                "Test 1", "LISTENING", "PART 1", "Questions 7-10",
                "Complete the notes below.",
                "Write ONE WORD ONLY for each answer.",
                "General information",
                "Participants must be able to swim.",
                "Bring suitable clothing, a 7 ........................ and toiletries.",
                "There is a 8 ........................ at the club.",
                "Online training 9 ........................ are recommended.",
                "10 ........................ are available for course participants.",
            ),
        }
        self.group = parse_group(first_group(pages, LISTENING))

    def test_type_and_word_limit(self):
        self.assertEqual(self.group.type, bp.NOTE_COMPLETION)
        self.assertEqual(self.group.word_limit, "one_word")

    def test_one_question_per_number_in_the_range(self):
        self.assertEqual(self.group.found_numbers, [7, 8, 9, 10])

    def test_layout_carries_inline_placeholders(self):
        joined = " ".join(block["text"] for block in self.group.layout)
        for number in (7, 8, 9, 10):
            self.assertIn(f"{{{{Q{number}}}}}", joined)

    def test_surrounding_prose_is_preserved(self):
        joined = " ".join(block["text"] for block in self.group.layout)
        self.assertIn("Participants must be able to swim.", joined)
        self.assertIn("at the club", joined)

    def test_clean_group_is_not_flagged(self):
        self.assertFalse(self.group.needs_review, self.group.warnings)


class TrueFalseTests(unittest.TestCase):
    def setUp(self):
        pages = {
            1: page(
                "Test 1", "READING", "READING PASSAGE 1", "Questions 8-10",
                "Do the following statements agree with the information given in "
                "Reading Passage 1?",
                "In boxes 8-10 on your answer sheet, write",
                "TRUE if the statement agrees with the information",
                "FALSE if the statement contradicts the information",
                "NOT GIVEN if there is no information on this",
                "8 The sisters' childhood influenced how they used their wealth.",
                "9 The Corot paintings were purchased from a gallery in France.",
                "10 Hugh Blaker opposed their decision to buy Impressionists.",
            ),
        }
        self.group = parse_group(first_group(pages))

    def test_type(self):
        self.assertEqual(self.group.type, bp.TFNG)

    def test_each_statement_becomes_a_question(self):
        self.assertEqual(self.group.found_numbers, [8, 9, 10])
        self.assertIn("childhood influenced", self.group.questions[0].prompt_text)

    def test_the_legend_is_dropped_not_parsed(self):
        # Three labels and three definitions are typeset as two columns, so
        # parsing them pairs the wrong ones. The UI renders a canonical legend.
        self.assertEqual(self.group.options, [])
        prompts = " ".join(q.prompt_text for q in self.group.questions).lower()
        self.assertNotIn("if the statement agrees", prompts)
        self.assertNotIn("answer sheet", prompts)


class MultipleChoiceTests(unittest.TestCase):
    def setUp(self):
        pages = {
            1: page(
                "Test 1", "LISTENING", "PART 2", "Questions 11-12",
                "Choose the correct letter, A, B or C.",
                "11 What should trainees always expect to get on low budget films?",
                "A travel expenses",
                "B a minimum wage",
                "C meals",
                "12 On big budget films trainees may get experience of",
                "A makeup for special effects.",
                "B working with different ethnicities.",
                "C creating a variety of hair styles.",
            ),
        }
        self.group = parse_group(first_group(pages, LISTENING))

    def test_type_and_select_count(self):
        self.assertEqual(self.group.type, bp.MCQ_SINGLE)
        self.assertEqual(self.group.select_count, 1)

    def test_each_question_gets_its_own_options(self):
        self.assertEqual(self.group.found_numbers, [11, 12])
        for question in self.group.questions:
            self.assertEqual([o["letter"] for o in question.options], ["A", "B", "C"])

    def test_stems_are_captured(self):
        self.assertIn("low budget films", self.group.questions[0].prompt_text)
        self.assertIn("travel expenses", self.group.questions[0].options[0]["text"])


class SharedOptionBankTests(unittest.TestCase):
    def setUp(self):
        pages = {
            1: page(
                "Test 1", "LISTENING", "PART 3", "Questions 25-27",
                "Choose THREE answers from the box and write the correct letter, "
                "A-E, next to Questions 25-27.",
                "A funding",
                "B equipment",
                "C location",
                "D staffing",
                "E timing",
                "25 the main problem",
                "26 the second problem",
                "27 the third problem",
            ),
        }
        self.group = parse_group(first_group(pages, LISTENING))

    def test_type_and_bank(self):
        self.assertEqual(self.group.type, bp.MATCHING_BANK)
        self.assertEqual([o["letter"] for o in self.group.options],
                         ["A", "B", "C", "D", "E"])

    def test_items(self):
        self.assertEqual(self.group.found_numbers, [25, 26, 27])
        self.assertIn("main problem", self.group.questions[0].prompt_text)

    def test_declared_letter_range_matches_the_bank(self):
        self.assertEqual(self.group.letter_range, ("A", "E"))
        self.assertNotIn("declares options", " ".join(self.group.warnings))


class LabellingTests(unittest.TestCase):
    def setUp(self):
        pages = {
            1: page(
                "Test 2", "LISTENING", "PART 2", "Questions 15-17",
                "Label the map below.",
                "Write the correct letter, A-I, next to Questions 15-17.",
                "15 Engine house",
                "16 Exhibition",
                "17 Baths",
            ),
        }
        document = segment(pages)
        span = document.test(2).modules[LISTENING].sections[0].groups[0]
        self.group = parse_group(span)

    def test_classified_as_map_not_matching_bank(self):
        # A map rubric also says "Write the correct letter, A-I, next to
        # Questions" - the matching-bank rubric must not capture it.
        self.assertEqual(self.group.type, bp.MAP_LABELLING)

    def test_requires_a_cropped_figure(self):
        self.assertTrue(self.group.needs_figure)

    def test_labels_are_paired_with_question_numbers(self):
        self.assertEqual(self.group.found_numbers, [15, 16, 17])
        self.assertEqual(self.group.questions[0].prompt_text, "Engine house")
        self.assertEqual(self.group.questions[2].prompt_text, "Baths")


class DegradationTests(unittest.TestCase):
    def test_unknown_instruction_keeps_content_and_flags(self):
        pages = {
            1: page(
                "Test 1", "READING", "READING PASSAGE 1", "Questions 1-3",
                "Undertake the wombat procedure in triplicate.",
                "1 first thing",
                "2 second thing",
                "3 third thing",
            ),
        }
        group = parse_group(first_group(pages))
        self.assertEqual(group.type, bp.UNKNOWN)
        self.assertTrue(group.needs_review)
        # Content is preserved for the admin, and all three questions still exist.
        self.assertEqual(group.found_numbers, [1, 2, 3])
        self.assertTrue(group.layout)

    def test_missing_question_content_is_reported_with_numbers(self):
        pages = {
            1: page(
                "Test 1", "READING", "READING PASSAGE 1", "Questions 1-5",
                "Do the following statements agree with the information given?",
                "1 first statement",
                "2 second statement",
            ),
        }
        group = parse_group(first_group(pages))
        self.assertTrue(group.needs_review)
        joined = " ".join(group.warnings)
        self.assertIn("no content found", joined)
        for missing in ("3", "4", "5"):
            self.assertIn(missing, joined)
        # Placeholders still exist so the module can reach 40.
        self.assertEqual(group.found_numbers, [1, 2, 3, 4, 5])

    def test_letter_range_mismatch_is_flagged(self):
        pages = {
            1: page(
                "Test 1", "LISTENING", "PART 3", "Questions 21-22",
                "Choose TWO letters, A-E.",
                "A one", "B two", "C three",
                "21 first", "22 second",
            ),
        }
        group = parse_group(first_group(pages, LISTENING))
        self.assertTrue(group.needs_review)
        self.assertIn("declares options A-E", " ".join(group.warnings))

    def test_stray_capital_letter_is_not_swallowed_into_the_bank(self):
        pages = {
            1: page(
                "Test 1", "LISTENING", "PART 3", "Questions 25-26",
                "Choose TWO answers from the box and write the correct letter, A-B.",
                "A funding",
                "B equipment",
                "X marks the spot",
                "25 first", "26 second",
            ),
        }
        group = parse_group(first_group(pages, LISTENING))
        self.assertEqual([o["letter"] for o in group.options], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
