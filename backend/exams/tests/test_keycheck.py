"""Tests for the answer-key self-checks.

The property that matters most: a wrong key must never come out ``trusted``.
A check that flags a correct answer costs one reveal; a check that vouches for
a wrong one mis-marks every candidate. So most of these feed in the kinds of
damage OCR really does - letter-shape swaps, a neighbouring row bleeding in, a
letter the options do not offer - and assert the verdict is not ``trusted``.
"""

import unittest

from exams import keycheck
from exams.importer import boilerplate as bp
from exams.keycheck import CHECK, MISSING, TRUSTED, GroupInfo, check_answer, check_module

PASSAGE = (
    "The first mines were dug for copper. Mining spread quickly, and education "
    "followed the railway. Visitors to Venice kept careful notes in their journals. "
    "The weather that spring was unusually slow to warm."
)

OCR = {"source": "ocr", "confidence": 0.97, "agreement": "agree", "independent": False}
OCR_ALONE = {"source": "ocr", "confidence": 0.97, "agreement": None}


def text(*accepted):
    return {"kind": "text", "accepted": list(accepted)}


def letter(value):
    return {"kind": "letter", "accepted": [value]}


NOTES = GroupInfo(type=bp.NOTE_COMPLETION, first=1, last=10, word_limit="one_word", section=1)
MCQ = GroupInfo(type=bp.MCQ_SINGLE, first=11, last=15, letter_range=("A", "C"), section=2)
TFNG = GroupInfo(type=bp.TFNG, first=16, last=20, section=2)
PAIR = GroupInfo(type=bp.MCQ_MULTI, first=21, last=22, letter_range=("A", "E"),
                 select_count=2, section=3)


class TrustedWhenEverythingFitsTests(unittest.TestCase):
    def test_ocr_text_found_in_the_passage_is_trusted(self):
        report = check_answer(2, text("education"), NOTES, PASSAGE, OCR_ALONE)
        self.assertEqual(report.status, TRUSTED, report.to_json())

    def test_letters_that_two_readings_agree_on_are_trusted(self):
        report = check_answer(12, letter("B"), MCQ, None, OCR)
        self.assertEqual(report.status, TRUSTED, report.to_json())

    def test_typeset_key_is_trusted_on_structure_alone(self):
        report = check_answer(5, text("Venice"), NOTES, "", {"source": "text"})
        self.assertEqual(report.status, TRUSTED)

    def test_number_words_count_as_found(self):
        passage = "There were ten of them."
        report = check_answer(1, text("10", "ten"), NOTES, passage, OCR_ALONE)
        self.assertEqual(report.result_of("in_source"), keycheck.PASS)


class WrongKeysAreNeverTrustedTests(unittest.TestCase):
    def test_letter_outside_the_options(self):
        report = check_answer(12, letter("G"), MCQ, None, OCR)
        self.assertEqual(report.status, CHECK)
        self.assertEqual(report.result_of("option_range"), keycheck.FAIL)

    def test_neighbouring_row_bled_into_the_answer(self):
        # "cafe 6 metal(s)": the "9" was misread and its row ran into Q8.
        report = check_answer(8, text("cafe 6 metals"), NOTES, PASSAGE, OCR)
        self.assertEqual(report.status, CHECK)
        self.assertEqual(report.result_of("word_limit"), keycheck.FAIL)

    def test_true_false_value_in_a_yes_no_group(self):
        group = GroupInfo(type=bp.YNNG, first=16, last=20)
        report = check_answer(16, {"kind": "tfng", "accepted": ["TRUE"]}, group, None, OCR)
        self.assertEqual(report.status, CHECK)

    def test_text_where_the_group_expects_a_letter(self):
        report = check_answer(13, text("NEITHER ORDER B D"), MCQ, None, OCR)
        self.assertEqual(report.status, CHECK)

    def test_unexplained_misread_is_suggested_not_applied(self):
        # "weathen" is near "weather" but n/r is not a known shape confusion.
        report = check_answer(7, text("weathen"), NOTES, PASSAGE, OCR_ALONE)
        self.assertEqual(report.status, CHECK)
        self.assertEqual(report.correction["to"], ["weather"])
        self.assertFalse(report.correction["explained"])

    def test_disagreeing_readings_are_flagged(self):
        evidence = dict(OCR, agreement="disagree", reads={"columns": "B", "layer": "D"})
        report = check_answer(12, letter("B"), MCQ, None, evidence)
        self.assertEqual(report.status, CHECK)

    def test_low_confidence_letter_alone_is_not_trusted(self):
        report = check_answer(12, letter("B"), MCQ, None,
                              {"source": "ocr", "confidence": 0.9, "agreement": None})
        self.assertEqual(report.status, CHECK)

    def test_ocr_text_not_in_the_passage_is_not_trusted(self):
        report = check_answer(3, text("harbour"), NOTES, PASSAGE, OCR)
        self.assertEqual(report.status, CHECK)

    def test_answer_from_a_second_reading_needs_agreement(self):
        evidence = dict(OCR_ALONE, filled=True)
        report = check_answer(2, text("education"), NOTES, PASSAGE, evidence)
        self.assertEqual(report.status, CHECK)

    def test_set_with_the_wrong_number_of_letters(self):
        answer = {"kind": "letter_set", "accepted": ["B"], "set_numbers": [21, 22]}
        report = check_answer(21, answer, PAIR, None, OCR)
        self.assertEqual(report.status, CHECK)
        self.assertEqual(report.result_of("set_size"), keycheck.FAIL)

    def test_missing_answer(self):
        self.assertEqual(check_answer(4, None, NOTES).status, MISSING)
        self.assertEqual(check_answer(4, text(), NOTES).status, MISSING)

    def test_unknown_question_type_needs_a_look(self):
        group = GroupInfo(type=bp.UNKNOWN, first=1, last=10)
        report = check_answer(1, text("mining"), group, PASSAGE, OCR)
        self.assertEqual(report.status, CHECK)


class OcrShapeCorrectionTests(unittest.TestCase):
    def test_rn_for_m_is_corrected_to_the_passage_spelling(self):
        report = check_answer(1, text("rnining"), NOTES, PASSAGE, OCR)
        self.assertTrue(report.correction["explained"])
        self.assertEqual(report.correction["to"], ["Mining"])

    def test_a_correction_still_needs_a_person(self):
        # The passage OCR could be the misread side ("clam" read as "dam").
        report = check_answer(1, text("rnining"), NOTES, PASSAGE, OCR)
        self.assertEqual(report.status, CHECK)

    def test_capital_i_for_lowercase_l(self):
        self.assertEqual(keycheck.shape_key("joumaIs"), keycheck.shape_key("journals"))

    def test_shape_key_does_not_merge_real_differences(self):
        self.assertNotEqual(keycheck.shape_key("ruin"), keycheck.shape_key("rain"))
        self.assertNotEqual(keycheck.shape_key("weathen"), keycheck.shape_key("weather"))


class GluedSourceTextTests(unittest.TestCase):
    """OCR of an audioscript runs words together; that is weak evidence only."""

    SCRIPT = "WOMAN:We talked aboutmining and then about education today."

    def test_found_only_in_glued_text_is_trusted_when_readings_agree(self):
        report = check_answer(1, text("mining"), NOTES, self.SCRIPT, OCR)
        self.assertEqual(report.status, TRUSTED)

    def test_found_only_in_glued_text_is_not_enough_alone(self):
        report = check_answer(1, text("mining"), NOTES, self.SCRIPT, OCR_ALONE)
        self.assertEqual(report.status, CHECK)

    def test_short_answers_are_never_matched_inside_glued_words(self):
        script = "Theyspent the summer training"
        report = check_answer(1, text("rain"), NOTES, script, OCR)
        self.assertNotEqual(report.result_of("in_source"), keycheck.PASS)


class ModuleTests(unittest.TestCase):
    def test_check_module_covers_every_number_and_summarises(self):
        answers = {"1": text("mining"), "11": letter("A"), "12": letter("Z")}
        evidence = {"1": OCR_ALONE, "11": OCR, "12": OCR}
        reports = check_module([NOTES, MCQ], answers, evidence, {1: PASSAGE}, total=15)
        self.assertEqual(len(reports), 15)
        self.assertEqual(reports[1].status, TRUSTED)
        self.assertEqual(reports[11].status, TRUSTED)
        self.assertEqual(reports[12].status, CHECK)
        counts = keycheck.summarise(reports, confirmed={12})
        self.assertEqual(counts[keycheck.CONFIRMED], 1)
        self.assertEqual(counts[TRUSTED], 2)
        self.assertEqual(counts[MISSING], 12)

    def test_groups_from_payload(self):
        payload = {"sections": [{"order": 2, "passage_text": "x", "groups": [{
            "type": bp.MCQ_MULTI, "first_question": 21, "last_question": 22,
            "letter_range": ["A", "E"], "options": [{"letter": "A", "text": "a"}],
            "word_limit": "", "select_count": 2,
        }]}]}
        group = keycheck.groups_from_payload(payload)[0]
        self.assertEqual((group.first, group.last, group.section), (21, 22, 2))
        self.assertEqual(group.letter_range, ("A", "E"))
        self.assertEqual(keycheck.lexicons_from_payload(payload), {2: "x"})

    def test_rubric_range_beats_a_damaged_option_list(self):
        # OCR glued "D option d" into "Doptiond", so only A-C were parsed.
        group = GroupInfo(type=bp.MCQ_MULTI, first=21, last=22, letter_range=("A", "E"),
                          options=["A", "B", "C"], select_count=2)
        answer = {"kind": "letter_set", "accepted": ["B", "D"], "set_numbers": [21, 22]}
        report = check_answer(21, answer, group, None, OCR)
        self.assertEqual(report.result_of("option_range"), keycheck.PASS)


if __name__ == "__main__":
    unittest.main()
