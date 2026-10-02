"""Tests for the answer-key parser, driven by the real Cambridge 21 key pages.

The most valuable test here is `RoundTripTests`: every answer Cambridge itself
publishes is fed back through the marking engine and must score 1/1. If the
book's own answer does not mark itself correct, either the key parse or the word
limit is wrong — and that is a bug that would otherwise reach live candidates.
"""

import unittest

from exams.keygrammar import (
    MAX_VARIANTS,
    detect_kind,
    expand_alternatives,
    parse_answer_key,
)
from exams.marking import (
    LETTER,
    LETTER_SET,
    TEXT,
    TFNG,
    YNNG,
    mark_one,
    mark_set,
)

from .fixtures.c21_answer_keys import ALL_KEY_PAGES

#: Page 119 interleaves its columns in the source text, so it is expected to be
#: rejected rather than parsed. See the module docstring in keygrammar.py.
INTERLEAVED_PAGE = 119
CLEAN_PAGES = [p for p in ALL_KEY_PAGES if p != INTERLEAVED_PAGE]


class ExpansionTests(unittest.TestCase):
    def test_slash_alternatives(self):
        self.assertEqual(expand_alternatives("10/ten"), ("10", "ten"))

    def test_or_alternatives(self):
        self.assertEqual(expand_alternatives("lift OR elevator"), ("lift", "elevator"))

    def test_optional_plural(self):
        self.assertEqual(set(expand_alternatives("metal(s)")), {"metal", "metals"})

    def test_optional_article(self):
        self.assertEqual(
            set(expand_alternatives("(the) equator")), {"the equator", "equator"}
        )

    def test_ocr_pipe_resolved_for_text_answers(self):
        # "cafe I cafe" is really "café | cafe"; OCR lost both the accent and
        # the pipe. Marking strips accents, so one form is enough.
        self.assertEqual(expand_alternatives("cafe I cafe"), ("cafe",))
        self.assertEqual(
            expand_alternatives("67.50 I sixty-seven fifty"),
            ("67.50", "sixty-seven fifty"),
        )

    def test_ocr_pipe_not_applied_where_letters_are_expected(self):
        # "I" is a real option letter when the range runs A-I.
        self.assertIn("I", expand_alternatives("I", letters_expected=True))

    def test_round_robin_keeps_every_top_level_alternative(self):
        # The bracketed date expands to eight forms on its own; a naive cap
        # would discard 13.01 and 13.1 completely.
        got = expand_alternatives("(the) 13(th) (of) January/ 13.01 / 13.1")
        self.assertIn("13.01", got)
        self.assertIn("13.1", got)
        self.assertIn("the 13th of January", got)
        self.assertLessEqual(len(got), MAX_VARIANTS)

    def test_variants_are_bounded(self):
        self.assertLessEqual(
            len(expand_alternatives("(a) (b) (c) (d) (e) (f) thing")), MAX_VARIANTS
        )


class DetectKindTests(unittest.TestCase):
    def test_true_false(self):
        self.assertEqual(detect_kind(("TRUE",)), TFNG)
        self.assertEqual(detect_kind(("FALSE",)), TFNG)

    def test_yes_no(self):
        self.assertEqual(detect_kind(("YES",)), YNNG)
        self.assertEqual(detect_kind(("NO",)), YNNG)

    def test_bare_not_given_follows_the_group_hint(self):
        # Ambiguous in isolation: it belongs to both scales.
        self.assertEqual(detect_kind(("NOT GIVEN",), hint=YNNG), YNNG)
        self.assertEqual(detect_kind(("NOT GIVEN",), hint=TFNG), TFNG)
        self.assertEqual(detect_kind(("NOT GIVEN",)), TFNG)

    def test_single_letter(self):
        self.assertEqual(detect_kind(("B",)), LETTER)

    def test_words(self):
        self.assertEqual(detect_kind(("mining",)), TEXT)
        self.assertEqual(detect_kind(("10", "ten")), TEXT)


class CleanPageTests(unittest.TestCase):
    """The seven key pages whose columns do not interleave."""

    def test_all_clean_pages_parse_completely(self):
        for page in CLEAN_PAGES:
            with self.subTest(page=page):
                result = parse_answer_key(ALL_KEY_PAGES[page], total=40)
                self.assertEqual(
                    len(result.keys), 40,
                    f"page {page}: missing {result.missing}; {result.warnings}",
                )
                self.assertTrue(result.reliable, f"page {page}: {result.warnings}")
                self.assertTrue(result.ok)

    def test_no_answer_retains_sidebar_or_heading_text(self):
        for page in CLEAN_PAGES:
            result = parse_answer_key(ALL_KEY_PAGES[page], total=40)
            for number, raw in result.raw.items():
                lowered = raw.lower()
                for noise in ("if you score", "ielts", "questions", "part ", "answer key"):
                    self.assertNotIn(lowered, (noise,), f"p{page} Q{number}: {raw!r}")
                    self.assertNotIn(noise, lowered, f"p{page} Q{number}: {raw!r}")

    def test_answers_are_short(self):
        # A long "answer" means prose leaked in.
        for page in CLEAN_PAGES:
            result = parse_answer_key(ALL_KEY_PAGES[page], total=40)
            for number, raw in result.raw.items():
                self.assertLessEqual(
                    len(raw.split()), 12, f"p{page} Q{number}: {raw!r}"
                )

    def test_trailing_page_number_is_not_treated_as_an_answer(self):
        result = parse_answer_key(ALL_KEY_PAGES[117], total=40)
        self.assertEqual(result.raw[40], "soil")


class KnownValueTests(unittest.TestCase):
    """Spot-checks against answers read by eye from the book."""

    def setUp(self):
        self.listening = parse_answer_key(ALL_KEY_PAGES[117], total=40)
        self.reading = parse_answer_key(ALL_KEY_PAGES[118], total=40)

    def test_number_word_alternatives(self):
        self.assertEqual(set(self.listening.keys[1].accepted), {"10", "ten"})

    def test_optional_plural_expanded_at_import(self):
        self.assertEqual(set(self.listening.keys[31].accepted), {"metal", "metals"})

    def test_plain_words(self):
        self.assertEqual(self.listening.keys[2].accepted, ("weather",))
        self.assertEqual(self.reading.keys[1].accepted, ("mining",))

    def test_letters(self):
        self.assertEqual(self.listening.keys[11].kind, LETTER)
        self.assertEqual(self.listening.keys[11].accepted, ("A",))

    def test_either_order_sets(self):
        key = self.listening.keys[21]
        self.assertEqual(key.kind, LETTER_SET)
        self.assertEqual(set(key.accepted), {"B", "D"})
        self.assertEqual(key.set_numbers, (21, 22))
        self.assertEqual(key.select_count, 2)
        # Both members share the same key object's values.
        self.assertEqual(self.listening.keys[22].set_id, key.set_id)

    def test_unspaced_not_given_is_recovered(self):
        self.assertEqual(self.reading.keys[9].kind, TFNG)
        self.assertEqual(self.reading.keys[9].accepted, ("NOT GIVEN",))

    def test_yes_no_not_given_passage_three(self):
        self.assertEqual(self.reading.keys[37].accepted, ("YES",))


class InterleavedPageTests(unittest.TestCase):
    """Page 119 must be refused, not guessed at.

    Its Part 1 and Part 3 columns interleave in the extracted text, so the Part 3
    option letters land inside the Part 1 answers. Producing a plausible-looking
    key from that would silently mis-mark every candidate.
    """

    def setUp(self):
        self.result = parse_answer_key(ALL_KEY_PAGES[INTERLEAVED_PAGE], total=40)

    def test_marked_unreliable(self):
        self.assertFalse(self.result.reliable)
        self.assertFalse(self.result.ok)

    def test_contaminated_questions_are_withheld_not_guessed(self):
        for number in (2, 5, 7, 20, 21, 22, 23, 24, 25, 26):
            self.assertNotIn(number, self.result.keys, f"Q{number} should be withheld")
            self.assertIn(number, self.result.missing)

    def test_explains_why(self):
        joined = " ".join(self.result.warnings).lower()
        self.assertIn("column", joined)

    def test_uncontaminated_answers_on_the_page_still_parse(self):
        self.assertEqual(self.result.keys[3].accepted, ("pizza",))
        self.assertEqual(self.result.keys[9].accepted, ("shirt",))
        self.assertEqual(self.result.keys[31].accepted, ("Pollution",))


class RoundTripTests(unittest.TestCase):
    """Cambridge's own published answers must mark themselves correct.

    This is the cheapest high-value check in the project: it validates the key
    parser, the variant expansion and the marking engine against each other
    across every question in the book, with no hand-written expectations.
    """

    def test_every_published_answer_scores_full_marks(self):
        checked = 0
        failures = []
        for page, text in ALL_KEY_PAGES.items():
            result = parse_answer_key(text, total=40)
            seen_sets = set()
            for number, key in sorted(result.keys.items()):
                if key.kind == LETTER_SET:
                    if key.set_id in seen_sets:
                        continue
                    seen_sets.add(key.set_id)
                    values = {m: {"letters": list(key.accepted)} for m in key.set_numbers}
                    for member, marked in mark_set(
                        [key] * len(key.set_numbers), values
                    ).items():
                        checked += 1
                        if not marked.is_correct:
                            failures.append((page, member, key.accepted, marked.reason))
                    continue
                for accepted in key.accepted:
                    checked += 1
                    marked = mark_one(key, {"text": accepted})
                    if not marked.is_correct:
                        failures.append((page, number, accepted, marked.reason))
        self.assertGreater(checked, 300, "fixture should cover the whole book")
        self.assertEqual(failures, [], f"{len(failures)} published answers failed")

    def test_case_and_spacing_variations_of_published_answers(self):
        """The same answers typed sloppily must still be accepted."""
        failures = []
        for page, text in ALL_KEY_PAGES.items():
            result = parse_answer_key(text, total=40)
            for number, key in sorted(result.keys.items()):
                if key.kind == LETTER_SET:
                    continue
                accepted = key.accepted[0]
                for typed in (f"  {accepted}", f"{accepted}  ", accepted.upper(), accepted.lower()):
                    if not mark_one(key, {"text": typed}).is_correct:
                        failures.append((page, number, typed))
        self.assertEqual(failures, [], f"{len(failures)} sloppy-but-correct answers failed")


if __name__ == "__main__":
    unittest.main()
