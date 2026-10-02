"""Tests for book segmentation.

Includes an older-edition fixture that says SECTION instead of PART and
Tapescript instead of Audioscript. That one exists to prove no
Cambridge-21-ism has crept into the anchors: the parser has to work on books
other than the two that happened to be on hand.
"""

import unittest

from exams.importer.layout import Line, build_lines
from exams.importer.pdfsource import Word
from exams.importer.segment import LISTENING, READING, segment


def page(*texts, width=600.0):
    """Build one page of single-line rows from plain strings."""
    lines = []
    for index, text in enumerate(texts):
        y = 50.0 + index * 20
        lines.append(Line([Word(text, 40.0, y, 40.0 + 8 * len(text), y + 12)]))
    return lines


def modern_book():
    """Cambridge-21-style wording."""
    return {
        1: page("Introduction", "Complete the notes below. This is explanatory prose."),
        2: page("Test 1", "LISTENING", "PART 1", "Questions 1-10",
                "Complete the table below.", "Write ONE WORD AND/OR A NUMBER for each answer.",
                "1 ......", "2 ......"),
        3: page("PART 2", "Questions 11-20", "Choose the correct letter, A, B or C.",
                "11 What should trainees expect?"),
        4: page("PART 3", "Questions 21-30", "Choose TWO letters, A-E."),
        5: page("PART 4", "Questions 31-40", "Complete the notes below."),
        6: page("READING", "READING PASSAGE 1",
                "You should spend about 20 minutes on Questions 1-13.",
                "The Davies Sisters", "Body text of the passage."),
        7: page("Questions 1-7", "Complete the notes below.",
                "Choose ONE WORD ONLY from the passage for each answer."),
        8: page("Questions 8-13",
                "Do the following statements agree with the information given in "
                "Reading Passage 1?",
                "8 The Davies sisters' childhood influenced them."),
        9: page("READING PASSAGE 2", "Questions 14-26", "Choose the correct letter, A, B or C."),
        10: page("READING PASSAGE 3", "Questions 27-40", "Choose the correct letter, A, B or C."),
        11: page("Test 2", "LISTENING", "PART 1", "Questions 1-10", "Complete the form below."),
        12: page("Audioscripts", "TEST 1", "PART 1", "You will hear ..."),
        13: page("Listening and Reading answer keys", "TEST 1", "1 mining 2 education"),
    }


def older_book():
    """Pre-2010 wording: SECTION for listening, Tapescript for the audio."""
    return {
        1: page("Test 1", "LISTENING", "SECTION 1", "Questions 1-10",
                "Complete the form below."),
        2: page("SECTION 2", "Questions 11-20", "Choose the correct letter, A, B or C."),
        3: page("SECTION 3", "Questions 21-30", "Complete the notes below."),
        4: page("SECTION 4", "Questions 31-40", "Complete the summary below."),
        5: page("READING", "READING PASSAGE 1",
                "You should spend about 20 minutes on Questions 1-13.",
                "Passage body."),
        6: page("Questions 1-13",
                "Choose the correct heading for each paragraph from the list of "
                "headings below."),
        7: page("Tapescript", "SECTION 1", "You will hear ..."),
    }


class ModernBookTests(unittest.TestCase):
    def setUp(self):
        self.doc = segment(modern_book())

    def test_finds_both_tests(self):
        self.assertEqual([t.number for t in self.doc.tests], [1, 2])

    def test_front_matter_is_skipped(self):
        """The Introduction discusses rubrics, so it must not create groups."""
        first = self.doc.test(1)
        self.assertIn(LISTENING, first.modules)
        # Nothing from page 1 leaked into the first test.
        listening = first.modules[LISTENING]
        self.assertEqual(len(listening.sections), 4)

    def test_listening_has_four_parts_numbered_1_to_40(self):
        listening = self.doc.test(1).modules[LISTENING]
        self.assertEqual([s.order for s in listening.sections], [1, 2, 3, 4])
        self.assertEqual(listening.question_numbers, list(range(1, 41)))

    def test_reading_has_three_passages_numbered_1_to_40(self):
        reading = self.doc.test(1).modules[READING]
        self.assertEqual([s.order for s in reading.sections], [1, 2, 3])
        self.assertEqual(reading.question_numbers, list(range(1, 41)))

    def test_groups_are_attached_to_the_right_section(self):
        reading = self.doc.test(1).modules[READING]
        first_passage = reading.sections[0]
        self.assertEqual(
            [(g.first_question, g.last_question) for g in first_passage.groups],
            [(1, 7), (8, 13)],
        )

    def test_instruction_block_is_joined(self):
        listening = self.doc.test(1).modules[LISTENING]
        instruction = listening.sections[0].groups[0].instruction
        # The rubric arrives as separate lines and must be joined before any
        # pattern can match it.
        self.assertIn("Complete the table below", instruction)
        self.assertIn("ONE WORD AND/OR A NUMBER", instruction)

    def test_back_matter_is_separated_from_the_tests(self):
        self.assertIn("scripts", self.doc.back_matter)
        self.assertIn("keys", self.doc.back_matter)
        # ...and the "TEST 1" heading inside the audioscripts did not start a
        # third test.
        self.assertEqual(len(self.doc.tests), 2)

    def test_no_structural_warnings_for_a_well_formed_test(self):
        relevant = [w for w in self.doc.warnings if "Test 1" in w]
        self.assertEqual(relevant, [], relevant)


class OlderEditionTests(unittest.TestCase):
    """Different wording, same structure. No anchor may assume Cambridge 21."""

    def setUp(self):
        self.doc = segment(older_book())

    def test_section_is_accepted_for_listening_parts(self):
        listening = self.doc.test(1).modules[LISTENING]
        self.assertEqual([s.order for s in listening.sections], [1, 2, 3, 4])
        self.assertEqual(listening.question_numbers, list(range(1, 41)))

    def test_tapescript_is_recognised_as_back_matter(self):
        self.assertIn("scripts", self.doc.back_matter)

    def test_list_of_headings_group_is_found(self):
        reading = self.doc.test(1).modules[READING]
        self.assertEqual(
            [(g.first_question, g.last_question) for g in reading.sections[0].groups],
            [(1, 13)],
        )


class ValidationTests(unittest.TestCase):
    def test_missing_question_numbers_are_reported_with_the_numbers(self):
        pages = {
            1: page("Test 1", "LISTENING", "PART 1", "Questions 1-10", "Complete the form."),
            2: page("PART 2", "Questions 15-40", "Choose the correct letter, A, B or C."),
        }
        warnings = " ".join(segment(pages).warnings)
        self.assertIn("not contiguous", warnings)
        self.assertIn("11", warnings)

    def test_short_module_is_reported(self):
        pages = {
            1: page("Test 1", "READING", "READING PASSAGE 1", "Questions 1-13",
                    "Complete the notes below."),
        }
        warnings = " ".join(segment(pages).warnings)
        self.assertIn("highest question number is 13", warnings)

    def test_book_with_no_test_heading_warns_instead_of_crashing(self):
        doc = segment({1: page("Some unrelated document.")})
        self.assertEqual(doc.tests, [])
        self.assertIn("no 'Test N' heading", " ".join(doc.warnings))

    def test_group_before_any_section_header_is_kept(self):
        pages = {
            1: page("Test 1", "READING", "Questions 1-13", "Complete the notes below."),
        }
        doc = segment(pages)
        reading = doc.test(1).modules[READING]
        self.assertEqual(len(reading.sections), 1)
        self.assertIn("synthesised", " ".join(doc.warnings))

    def test_empty_input(self):
        doc = segment({})
        self.assertEqual(doc.tests, [])


class LegendDroppingTests(unittest.TestCase):
    def test_true_false_legend_is_not_treated_as_instruction(self):
        pages = {
            1: page(
                "Test 1", "READING", "READING PASSAGE 1", "Questions 8-13",
                "Do the following statements agree with the information given in "
                "Reading Passage 1?",
                "In boxes 8-13 on your answer sheet, write",
                "TRUE if the statement agrees with the information",
                "FALSE if the statement contradicts the information",
                "NOT GIVEN if there is no information on this",
                "8 A statement about the sisters.",
            ),
        }
        doc = segment(pages)
        group = doc.test(1).modules[READING].sections[0].groups[0]
        self.assertIn("Do the following statements agree", group.instruction)
        # The two-column legend mispairs when parsed, so it is dropped and the
        # frontend renders a canonical one instead.
        self.assertNotIn("impossible", group.instruction.lower())
        self.assertNotIn("contradicts", group.instruction.lower())
        self.assertNotIn("answer sheet", group.instruction.lower())


if __name__ == "__main__":
    unittest.main()


class OcrSpacingTests(unittest.TestCase):
    """RapidOCR drops narrow spaces; the anchors must survive that."""

    def test_glued_headings_still_segment(self):
        pages = {
            1: page("Test1", "LISTENING", "PART1Questions1-10", "Complete the notes below.",
                    "1 ......", "PART 2 Questions11-20"),
            2: page("Listening and Reading answerkeys", "TEST1", "LISTENING", "1 mining"),
        }
        document = segment(pages)
        self.assertEqual([t.number for t in document.tests], [1])
        module = document.tests[0].modules[LISTENING]
        self.assertEqual([s.order for s in module.sections], [1, 2])
        self.assertIn("keys", document.back_matter)

    def test_a_space_inserted_inside_a_heading(self):
        pages = {1: page("Test 1", "LISTENIN G", "PART 1", "Questions 1-10",
                         "Complete the notes below.", "1 ......")}
        self.assertIn(LISTENING, segment(pages).tests[0].modules)

    def test_long_content_lines_are_never_compacted(self):
        from exams.importer.segment import is_structural_anchor

        self.assertFalse(is_structural_anchor("Section 2 of the report covers the history"))
        self.assertTrue(is_structural_anchor("TEST 1"))

    def test_questions_n_and_m_header_opens_a_group(self):
        pages = {1: page("Test 1", "LISTENING", "PART 3", "Questions 21 and 22",
                         "Choose TWO letters, A-E.", "A one", "B two")}
        module = segment(pages).tests[0].modules[LISTENING]
        groups = module.sections[0].groups
        self.assertEqual((groups[0].first_question, groups[0].last_question), (21, 22))


class ContentsPageTests(unittest.TestCase):
    """OCR splits a contents page's page numbers off into their own column."""

    def test_contents_page_does_not_start_the_back_matter(self):
        pages = {
            3: page("Contents", "Test 1", "Test 2", "Audioscripts",
                    "Listening and Reading answer keys 120", "Acknowledgements"),
            4: page("Introduction", "The answer keys are at the back.", "Audioscripts"),
            9: page("Test 1", "LISTENING", "PART 1 Questions 1-10",
                    "Complete the notes below.", "1 ......"),
            90: page("Audioscripts", "TEST 1", "PART 1", "WOMAN: Hello."),
        }
        document = segment(pages)
        module = document.tests[0].modules[LISTENING]
        self.assertEqual(module.sections[0].groups[0].first_question, 1)
        self.assertEqual([line.text for line in document.back_matter["scripts"]][:1], ["TEST 1"])
