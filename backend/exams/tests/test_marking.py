"""Tests for the deterministic marking engine.

Plain `unittest` — the engine has no Django dependency, so these run without a
database and without settings configured.
"""

import unittest

from exams.marking import (
    BLANK,
    CORRECT,
    LETTER,
    LETTER_SET,
    OVER_SELECTED,
    OVER_WORD_LIMIT,
    STRICT_POLICY,
    TEXT,
    TFNG,
    WRONG,
    YNNG,
    AnswerKey,
    canonical,
    count_words,
    mark_module,
    mark_one,
    mark_set,
    normalize,
)


def _mark(accepted, response, kind=TEXT, word_limit="", policy=None):
    key = AnswerKey(kind=kind, accepted=tuple(accepted), word_limit=word_limit)
    kwargs = {"policy": policy} if policy else {}
    return mark_one(key, {"text": response}, **kwargs)


class NormalisationTests(unittest.TestCase):
    def test_case_and_outer_whitespace_ignored(self):
        # The explicit requirement: "apple " must equal "apple".
        for response in ("apple ", " apple", "  APPLE  ", "Apple"):
            self.assertTrue(_mark(["apple"], response).is_correct, response)

    def test_internal_whitespace_collapsed(self):
        self.assertTrue(_mark(["train station"], "train    station").is_correct)

    def test_trailing_punctuation_stripped(self):
        self.assertTrue(_mark(["apple"], "apple.").is_correct)
        self.assertTrue(_mark(["apple"], "apple,").is_correct)

    def test_curly_apostrophe_matches_straight(self):
        self.assertTrue(_mark(["children's"], "children’s").is_correct)

    def test_surrounding_quotes_ignored(self):
        self.assertTrue(_mark(["apple"], '"apple"').is_correct)


class EquivalenceTests(unittest.TestCase):
    def test_numerals_and_words(self):
        self.assertTrue(_mark(["10", "ten"], "Ten").is_correct)
        self.assertTrue(_mark(["ten"], "10").is_correct)
        self.assertTrue(_mark(["21"], "twenty one").is_correct)
        self.assertTrue(_mark(["twenty-one"], "21").is_correct)
        self.assertTrue(_mark(["150"], "one hundred and fifty").is_correct)

    def test_ordinals(self):
        self.assertTrue(_mark(["first"], "1st").is_correct)
        self.assertTrue(_mark(["1st"], "first").is_correct)

    def test_hyphen_equals_space_but_not_joined(self):
        self.assertTrue(_mark(["well-known"], "well known").is_correct)
        self.assertTrue(_mark(["well known"], "well-known").is_correct)
        # Removing the separator altogether is a spelling error, not a variant.
        self.assertFalse(_mark(["well-known"], "wellknown").is_correct)

    def test_contractions(self):
        self.assertTrue(_mark(["do not"], "don't").is_correct)
        self.assertTrue(_mark(["cannot"], "can't").is_correct)

    def test_accents(self):
        self.assertTrue(_mark(["cafe"], "café").is_correct)
        self.assertTrue(_mark(["café"], "cafe").is_correct)

    def test_british_american_spelling(self):
        self.assertTrue(_mark(["colour"], "color").is_correct)
        self.assertTrue(_mark(["organisation"], "organization").is_correct)
        self.assertTrue(_mark(["centre"], "center").is_correct)

    def test_spelling_rule_is_curated_not_generic(self):
        # A generic -ise/-ize rule would wrongly rewrite these.
        self.assertEqual(canonical("exercise"), "exercise")
        self.assertEqual(canonical("surprise"), "surprise")
        self.assertEqual(canonical("advertise"), "advertise")


class NeverFuzzyTests(unittest.TestCase):
    """One edit apart, completely different words. These must stay wrong."""

    def test_near_misses_are_wrong(self):
        for accepted, response in [
            ("weather", "whether"),
            ("quiet", "quite"),
            ("desert", "dessert"),
            ("affect", "effect"),
            ("form", "from"),
        ]:
            self.assertFalse(_mark([accepted], response).is_correct, response)

    def test_no_automatic_pluralisation(self):
        # "(s)" in the key encodes this explicitly; inferring it would accept
        # "note" for "notes".
        self.assertFalse(_mark(["notes"], "note").is_correct)
        self.assertFalse(_mark(["note"], "notes").is_correct)

    def test_no_automatic_article_stripping(self):
        # "(the)" in the key encodes this explicitly.
        self.assertFalse(_mark(["the library"], "library").is_correct)


class WordLimitTests(unittest.TestCase):
    def test_exceeding_limit_is_wrong_with_its_own_reason(self):
        result = _mark(["library"], "the library", word_limit="one_word")
        self.assertFalse(result.is_correct)
        self.assertEqual(result.reason, OVER_WORD_LIMIT)
        self.assertIn("ONE WORD ONLY", result.detail)

    def test_within_limit_passes(self):
        self.assertTrue(_mark(["the library"], "the library", word_limit="two_words").is_correct)

    def test_hyphenated_compound_counts_as_one_word(self):
        self.assertEqual(count_words("well-known"), 1)
        self.assertTrue(_mark(["well-known"], "well-known", word_limit="one_word").is_correct)

    def test_contraction_counts_as_one_word(self):
        self.assertEqual(count_words("don't"), 1)

    def test_and_or_a_number_allows_one_extra_token(self):
        self.assertTrue(
            _mark(["25 april"], "25 April", word_limit="one_word_number").is_correct
        )
        # ...but only for a number, not a third plain word.
        result = _mark(["big red bus"], "big red bus", word_limit="two_words_number")
        self.assertEqual(result.reason, OVER_WORD_LIMIT)

    def test_limit_can_be_disabled_by_policy(self):
        key = AnswerKey(accepted=("the library",), word_limit="one_word")
        from exams.marking import MatchPolicy

        relaxed = MatchPolicy(enforce_word_limit=False)
        self.assertTrue(mark_one(key, {"text": "the library"}, relaxed).is_correct)


class BlankVersusWrongTests(unittest.TestCase):
    def test_blank_has_its_own_reason(self):
        for empty in ("", "   ", None):
            result = mark_one(AnswerKey(accepted=("x",)), {"text": empty} if empty is not None else None)
            self.assertEqual(result.reason, BLANK)
            self.assertEqual(result.awarded, 0)

    def test_wrong_is_distinct_from_blank(self):
        self.assertEqual(_mark(["x"], "y").reason, WRONG)


class TrueFalseTests(unittest.TestCase):
    def test_synonyms(self):
        self.assertTrue(_mark(["TRUE"], "t", kind=TFNG).is_correct)
        self.assertTrue(_mark(["TRUE"], "True", kind=TFNG).is_correct)
        self.assertTrue(_mark(["FALSE"], "f", kind=TFNG).is_correct)
        self.assertTrue(_mark(["NOT GIVEN"], "ng", kind=TFNG).is_correct)
        self.assertTrue(_mark(["NOT GIVEN"], "notgiven", kind=TFNG).is_correct)
        self.assertTrue(_mark(["NOT GIVEN"], "NOT  GIVEN", kind=TFNG).is_correct)

    def test_yes_no_not_given(self):
        self.assertTrue(_mark(["YES"], "y", kind=YNNG).is_correct)
        self.assertTrue(_mark(["NO"], "n", kind=YNNG).is_correct)

    def test_wrong_choice(self):
        self.assertFalse(_mark(["TRUE"], "false", kind=TFNG).is_correct)


class LetterTests(unittest.TestCase):
    def test_case_insensitive(self):
        self.assertTrue(_mark(["B"], "b", kind=LETTER).is_correct)

    def test_wrong_letter(self):
        self.assertFalse(_mark(["B"], "C", kind=LETTER).is_correct)


class LetterSetTests(unittest.TestCase):
    """"21 &22 IN EITHER ORDER  B  D" - one mark per correct letter, any order."""

    def setUp(self):
        self.key = AnswerKey(
            kind=LETTER_SET,
            accepted=("B", "D"),
            set_id="s1",
            set_numbers=(21, 22),
            select_count=2,
        )

    def _run(self, letters):
        values = {21: {"letters": letters}, 22: {"letters": letters}}
        return mark_set([self.key, self.key], values)

    def test_both_correct_in_either_order(self):
        for letters in (["B", "D"], ["D", "B"]):
            results = self._run(letters)
            self.assertEqual(sum(r.awarded for r in results.values()), 2, letters)

    def test_partial_credit(self):
        results = self._run(["B", "C"])
        self.assertEqual(sum(r.awarded for r in results.values()), 1)

    def test_none_correct(self):
        results = self._run(["A", "C"])
        self.assertEqual(sum(r.awarded for r in results.values()), 0)

    def test_over_selection_scores_zero_for_the_whole_set(self):
        results = self._run(["B", "C", "D"])
        self.assertEqual(sum(r.awarded for r in results.values()), 0)
        self.assertTrue(all(r.reason == OVER_SELECTED for r in results.values()))

    def test_blank(self):
        results = mark_set([self.key, self.key], {21: None, 22: None})
        self.assertTrue(all(r.reason == BLANK for r in results.values()))

    def test_duplicate_selection_is_not_two_marks(self):
        results = self._run(["B", "B"])
        self.assertEqual(sum(r.awarded for r in results.values()), 1)


class StrictPolicyTests(unittest.TestCase):
    """The narrow reading of the brief: case + outer whitespace only."""

    def test_strict_still_ignores_case_and_outer_space(self):
        self.assertTrue(_mark(["apple"], " Apple ", policy=STRICT_POLICY).is_correct)

    def test_strict_rejects_the_looser_equivalences(self):
        for accepted, response in [
            ("well-known", "well known"),
            ("ten", "10"),
            ("colour", "color"),
            ("café", "cafe"),
            ("do not", "don't"),
        ]:
            self.assertFalse(
                _mark([accepted], response, policy=STRICT_POLICY).is_correct,
                f"{accepted} vs {response}",
            )


class ModuleScoringTests(unittest.TestCase):
    def test_raw_score_counts_and_categories(self):
        keys = {
            1: AnswerKey(accepted=("apple",)),
            2: AnswerKey(accepted=("pear",)),
            3: AnswerKey(accepted=("plum",)),
            4: AnswerKey(kind=TFNG, accepted=("TRUE",)),
            5: AnswerKey(accepted=("library",), word_limit="one_word"),
        }
        answers = {
            1: {"text": "apple "},      # correct
            2: {"text": "banana"},      # wrong
            3: {"text": ""},            # blank
            4: {"text": "T"},           # correct
            5: {"text": "the library"}, # over word limit
        }
        result = mark_module(keys, answers)
        self.assertEqual(result.raw_score, 2)
        self.assertEqual(result.total, 5)
        self.assertEqual(result.correct_count, 2)
        self.assertEqual(result.blank_count, 1)
        self.assertEqual(result.wrong_count, 2)

    def test_sets_are_marked_once_across_their_members(self):
        set_key = AnswerKey(
            kind=LETTER_SET, accepted=("B", "D"),
            set_id="s1", set_numbers=(1, 2), select_count=2,
        )
        keys = {1: set_key, 2: set_key, 3: AnswerKey(accepted=("apple",))}
        answers = {1: {"letters": ["D", "B"]}, 2: {"letters": ["D", "B"]}, 3: {"text": "apple"}}
        result = mark_module(keys, answers)
        self.assertEqual(result.raw_score, 3)


if __name__ == "__main__":
    unittest.main()
