"""Tests for instruction-line classification.

Two groups matter here:

* rubrics taken verbatim from Cambridge 20/21, including OCR damage; and
* hand-written rubrics for the types those two books **do not contain**
  (list of headings, classification, pick-from-a-list, short answer).

The second group is the point. Cambridge 21 has no "list of headings" task, so
without these the claim that the parser generalises beyond the two sample books
would be untested rather than true.
"""

import unittest

from exams.importer import boilerplate as bp
from exams.importer.classify import classify, extract_word_limit, misses


class TypeFromRealBooksTests(unittest.TestCase):
    """Rubrics as they appear in Cambridge 20/21."""

    CASES = [
        ("Choose the correct letter, A, B or C.", bp.MCQ_SINGLE),
        ("Choose the correct letter, A, B, C or D.", bp.MCQ_SINGLE),
        ("Choose TWO letters, A-E.", bp.MCQ_MULTI),
        ("Choose THREE letters, A-G.", bp.MCQ_MULTI),
        ("Complete the table below. Write ONE WORD AND/OR A NUMBER for each answer.",
         bp.TABLE_COMPLETION),
        ("Complete the notes below. Write ONE WORD ONLY for each answer.",
         bp.NOTE_COMPLETION),
        ("Complete the notes below. Choose ONE WORD ONLY from the passage for each answer.",
         bp.NOTE_COMPLETION),
        ("Complete the flow-chart below. Choose NO MORE THAN TWO WORDS from the passage.",
         bp.FLOWCHART_COMPLETION),
        ("Complete the summary below. Write ONE WORD ONLY for each answer.",
         bp.SUMMARY_COMPLETION),
        ("Complete the summary using the list of words, A-I, below.",
         bp.SUMMARY_COMPLETION_BANK),
        ("Complete each sentence with the correct ending, A-F, below.",
         bp.SENTENCE_ENDINGS),
        ("Label the map below. Write the correct letter, A-I, next to Questions 15-20.",
         bp.MAP_LABELLING),
        ("Choose SIX answers from the box and write the correct letter, A-H, "
         "next to Questions 25-30.", bp.MATCHING_BANK),
        ("Which section contains the following information?", bp.MATCHING_PARAGRAPH),
        ("Reading Passage 2 has seven sections, A-G.", bp.MATCHING_PARAGRAPH),
        ("Look at the following statements and the list of people below.",
         bp.MATCHING_FEATURES),
    ]

    def test_types(self):
        for instruction, expected in self.CASES:
            with self.subTest(instruction=instruction[:50]):
                self.assertEqual(classify(instruction).type, expected)

    def test_true_false_not_given(self):
        rubric = ("Do the following statements agree with the information given in "
                  "Reading Passage 1?")
        self.assertEqual(classify(rubric).type, bp.TFNG)

    def test_yes_no_not_given_beats_true_false(self):
        # Both open with "Do the following statements agree with the"; only the
        # tail distinguishes an opinion task from a factual one.
        for rubric in (
            "Do the following statements agree with the claims of the writer in "
            "Reading Passage 3?",
            "Do the following statements agree with the views of the writer?",
        ):
            self.assertEqual(classify(rubric).type, bp.YNNG, rubric)


class TypesAbsentFromTheSampleBooksTests(unittest.TestCase):
    """Neither Cambridge 20 nor 21 contains these. They must still classify."""

    def test_list_of_headings(self):
        for rubric in (
            "Choose the correct heading for each paragraph from the list of "
            "headings below.",
            "Reading Passage 1 has six paragraphs, A-F. Choose the correct heading "
            "for each paragraph from the list of headings below.",
        ):
            self.assertEqual(classify(rubric).type, bp.LIST_OF_HEADINGS, rubric)

    def test_classification(self):
        rubric = "Classify the following events as occurring in A the 1960s, B the 1970s."
        self.assertEqual(classify(rubric).type, bp.CLASSIFICATION)

    def test_pick_from_a_list(self):
        rubric = "Which TWO of the following are mentioned by the speaker?"
        self.assertEqual(classify(rubric).type, bp.MCQ_MULTI)

    def test_short_answer(self):
        rubric = "Answer the questions below. Write NO MORE THAN THREE WORDS for each answer."
        result = classify(rubric)
        self.assertEqual(result.type, bp.SHORT_ANSWER)
        self.assertEqual(result.word_limit, "three_words")

    def test_diagram_and_plan_labelling(self):
        self.assertEqual(classify("Label the diagram below.").type, bp.DIAGRAM_LABELLING)
        self.assertEqual(classify("Label the plan below.").type, bp.PLAN_LABELLING)

    def test_form_completion(self):
        self.assertEqual(classify("Complete the form below.").type, bp.FORM_COMPLETION)

    def test_sentence_completion(self):
        rubric = "Complete the sentences below. Write ONE WORD ONLY for each answer."
        self.assertEqual(classify(rubric).type, bp.SENTENCE_COMPLETION)


class OcrDamageTests(unittest.TestCase):
    """Garbled rubrics should still land, via the fuzzy pass, and be flagged."""

    def test_mangled_rubrics_still_classify(self):
        cases = [
            ("Cornplete the notes below. Write ONE WORD ONLY for each answer.",
             bp.NOTE_COMPLETION),
            ("Choose the correct Ietter, A, B or C.", bp.MCQ_SINGLE),
            ("Complete the tabIe below.", bp.TABLE_COMPLETION),
        ]
        for rubric, expected in cases:
            with self.subTest(rubric=rubric):
                self.assertEqual(classify(rubric).type, expected)

    def test_a_fuzzy_hit_is_flagged_for_review(self):
        result = classify("Cornplete the surnmary beIow using the Iist of words")
        if result.type != bp.UNKNOWN:
            self.assertTrue(result.needs_review)

    def test_unrecognised_rubric_is_unknown_not_guessed(self):
        result = classify("Please enjoy this entirely unrelated sentence about otters.")
        self.assertEqual(result.type, bp.UNKNOWN)
        self.assertTrue(result.needs_review)

    def test_empty_instruction(self):
        self.assertEqual(classify("").type, bp.UNKNOWN)


class WordLimitTests(unittest.TestCase):
    CASES = [
        ("Write ONE WORD ONLY for each answer.", "one_word"),
        ("Write ONE WORD AND/OR A NUMBER for each answer.", "one_word_number"),
        ("Write NO MORE THAN TWO WORDS for each answer.", "two_words"),
        ("Write NO MORE THAN TWO WORDS AND/OR A NUMBER for each answer.",
         "two_words_number"),
        ("Write NO MORE THAN THREE WORDS for each answer.", "three_words"),
        ("Choose NO MORE THAN THREE WORDS AND/OR A NUMBER from the passage.",
         "three_words_number"),
        ("Choose ONE WORD ONLY from the passage for each answer.", "one_word"),
    ]

    def test_word_limits(self):
        for rubric, expected in self.CASES:
            with self.subTest(rubric=rubric):
                self.assertEqual(extract_word_limit(rubric)[0], expected)

    def test_and_or_a_number_beats_the_plain_form(self):
        # "TWO WORDS AND/OR A NUMBER" must not match the shorter "TWO WORDS".
        limit, allows = extract_word_limit("NO MORE THAN TWO WORDS AND/OR A NUMBER")
        self.assertEqual(limit, "two_words_number")
        self.assertTrue(allows)

    def test_no_limit_stated(self):
        self.assertEqual(extract_word_limit("Choose the correct letter, A, B or C.")[0], "")

    def test_limit_is_found_under_any_completion_type(self):
        for stem in ("notes", "table", "form", "summary", "sentences"):
            rubric = f"Complete the {stem} below. Write ONE WORD ONLY for each answer."
            self.assertEqual(classify(rubric).word_limit, "one_word", stem)


class ExtractorTests(unittest.TestCase):
    def test_letter_range(self):
        self.assertEqual(classify("Choose TWO letters, A-E.").letter_range, ("A", "E"))
        self.assertEqual(
            classify("Write the correct letter, A-I, next to Questions 15-20.").letter_range,
            ("A", "I"),
        )

    def test_letter_range_accepts_en_dash_and_to(self):
        self.assertEqual(classify("Choose TWO letters, A – E.").letter_range, ("A", "E"))
        self.assertEqual(classify("Choose TWO letters, A to E.").letter_range, ("A", "E"))

    def test_select_count(self):
        self.assertEqual(classify("Choose TWO letters, A-E.").select_count, 2)
        self.assertEqual(classify("Choose THREE letters, A-G.").select_count, 3)
        self.assertEqual(
            classify("Choose SIX answers from the box.").select_count, 6
        )

    def test_single_mcq_has_count_one(self):
        self.assertEqual(classify("Choose the correct letter, A, B or C.").select_count, 1)

    def test_reusable_options(self):
        rubric = ("Which section contains the following information? "
                  "You may use any letter more than once.")
        self.assertTrue(classify(rubric).options_reusable)

    def test_not_reusable_by_default(self):
        self.assertFalse(classify("Which section contains the following information?").options_reusable)


class FlagTests(unittest.TestCase):
    def test_letter_answer_types_are_marked(self):
        self.assertTrue(classify("Choose the correct letter, A, B or C.").expects_letters)
        self.assertTrue(classify("Label the map below.").expects_letters)
        self.assertFalse(
            classify("Complete the notes below. Write ONE WORD ONLY for each answer.")
            .expects_letters
        )

    def test_figure_types_are_marked(self):
        self.assertTrue(classify("Label the map below.").needs_figure)
        self.assertTrue(classify("Complete the flow-chart below.").needs_figure)
        self.assertFalse(classify("Complete the notes below.").needs_figure)

    def test_clean_match_is_not_flagged(self):
        self.assertFalse(classify("Choose the correct letter, A, B or C.").needs_review)


class MissLogTests(unittest.TestCase):
    def test_misses_reports_only_unrecognised_lines(self):
        got = misses([
            "Choose the correct letter, A, B or C.",
            "Something the catalogue has never seen about penguins.",
        ])
        self.assertEqual(len(got), 1)
        self.assertIn("penguins", got[0][0])


if __name__ == "__main__":
    unittest.main()


class GluedRubricTests(unittest.TestCase):
    """Rubrics whose spaces the recogniser dropped."""

    def test_glued_rubrics_classify(self):
        cases = [
            ("Completethenotesbelow. WriteONEWORDAND/ORANUMBERforeachanswer.",
             bp.NOTE_COMPLETION, "one_word_number"),
            ("ChooseTWoletters,A-E.", bp.MCQ_MULTI, ""),
            ("Complete thenotes below.", bp.NOTE_COMPLETION, ""),
        ]
        for text, kind, limit in cases:
            with self.subTest(text=text):
                result = classify(text)
                self.assertEqual(result.type, kind)
                self.assertEqual(result.word_limit, limit)
                self.assertTrue(result.needs_review)

    def test_letter_list_gives_a_range(self):
        self.assertEqual(classify("Choose the correct letter, A, B or C.").letter_range,
                         ("A", "C"))
        self.assertEqual(classify("Choose thecorrectletter,A,Bor C.").letter_range, ("A", "C"))

    def test_spaced_prose_is_not_read_glued(self):
        from exams.importer.classify import looks_like_rubric

        self.assertFalse(looks_like_rubric("The museum has someone worded badly."))
        self.assertTrue(looks_like_rubric("Complete thenotes below."))
