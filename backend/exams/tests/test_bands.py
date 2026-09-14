"""Tests for raw-score to IELTS band conversion."""

import unittest
from decimal import Decimal

from exams import bands


class TableShapeTests(unittest.TestCase):
    def test_tables_cover_every_raw_score(self):
        for kind in ("reading", "listening"):
            with self.subTest(kind=kind):
                for raw in range(0, 41):
                    band = bands.raw_to_band(kind, raw)
                    self.assertIsInstance(band, Decimal)
                    self.assertGreaterEqual(band, Decimal("0"))
                    self.assertLessEqual(band, Decimal("9"))

    def test_bands_never_decrease_as_the_score_rises(self):
        for kind in ("reading", "listening"):
            with self.subTest(kind=kind):
                previous = Decimal("-1")
                for raw in range(0, 41):
                    band = bands.raw_to_band(kind, raw)
                    self.assertGreaterEqual(band, previous, f"raw={raw}")
                    previous = band

    def test_ranges_are_contiguous_and_non_overlapping(self):
        for table in (bands.READING_ACADEMIC_V1, bands.LISTENING_V1):
            covered = set()
            for low, high, _band in table:
                self.assertLessEqual(low, high)
                span = set(range(low, high + 1))
                self.assertFalse(covered & span, "overlapping ranges")
                covered |= span
            self.assertEqual(covered, set(range(0, 41)))

    def test_unknown_table_raises(self):
        with self.assertRaises(bands.UnknownBandTable):
            bands.raw_to_band("speaking", 30)


class BoundaryTests(unittest.TestCase):
    def test_academic_reading_boundaries(self):
        expected = {
            40: "9.0", 39: "9.0", 38: "8.5", 37: "8.5", 36: "8.0", 35: "8.0",
            34: "7.5", 33: "7.5", 32: "7.0", 30: "7.0", 29: "6.5", 27: "6.5",
            26: "6.0", 23: "6.0", 22: "5.5", 19: "5.5", 18: "5.0", 15: "5.0",
            14: "4.5", 13: "4.5", 12: "4.0", 10: "4.0", 0: "0.0",
        }
        for raw, band in expected.items():
            self.assertEqual(
                bands.raw_to_band("reading", raw), Decimal(band), f"raw={raw}"
            )

    def test_listening_boundaries(self):
        expected = {
            40: "9.0", 39: "9.0", 38: "8.5", 36: "8.0", 34: "7.5", 32: "7.5",
            31: "7.0", 30: "7.0", 29: "6.5", 26: "6.5", 25: "6.0", 23: "6.0",
            22: "5.5", 18: "5.5", 17: "5.0", 16: "5.0", 15: "4.5", 0: "0.0",
        }
        for raw, band in expected.items():
            self.assertEqual(
                bands.raw_to_band("listening", raw), Decimal(band), f"raw={raw}"
            )

    def test_reading_is_harsher_than_listening_in_the_middle(self):
        # 30/40 is band 7.0 in both, but 23/40 differs: Reading 6.0, Listening 6.0;
        # the tables diverge around 31-34.
        self.assertEqual(bands.raw_to_band("reading", 33), Decimal("7.5"))
        self.assertEqual(bands.raw_to_band("listening", 33), Decimal("7.5"))
        self.assertEqual(bands.raw_to_band("reading", 31), Decimal("7.0"))
        self.assertEqual(bands.raw_to_band("listening", 31), Decimal("7.0"))

    def test_out_of_range_is_clamped_not_rejected(self):
        self.assertEqual(bands.raw_to_band("reading", 99), Decimal("9.0"))
        self.assertEqual(bands.raw_to_band("reading", -5), Decimal("0.0"))


class RoundingTests(unittest.TestCase):
    """The official rule: .25 rounds up to .5, .75 rounds up to the next whole."""

    def test_official_thresholds(self):
        cases = {
            6.0: "6.0", 6.1: "6.0", 6.24: "6.0",
            6.25: "6.5", 6.4: "6.5", 6.5: "6.5", 6.74: "6.5",
            6.75: "7.0", 6.9: "7.0", 7.0: "7.0",
        }
        for value, expected in cases.items():
            self.assertEqual(
                bands.round_ielts_half(value), Decimal(expected), f"value={value}"
            )

    def test_the_case_the_old_frontend_helper_got_wrong(self):
        # formatBandScore in the React pages returned 6.0 for 6.25.
        self.assertEqual(bands.round_ielts_half(6.25), Decimal("6.5"))

    def test_zero_and_nine(self):
        self.assertEqual(bands.round_ielts_half(0), Decimal("0.0"))
        self.assertEqual(bands.round_ielts_half(9), Decimal("9.0"))


class OverallBandTests(unittest.TestCase):
    def test_mean_of_four_skills(self):
        self.assertEqual(bands.overall_band([6.5, 7.0, 6.0, 7.5]), Decimal("7.0"))

    def test_quarter_rounds_up(self):
        # mean 6.25 -> 6.5
        self.assertEqual(bands.overall_band([6.0, 6.0, 6.5, 6.5]), Decimal("6.5"))

    def test_missing_skills_are_skipped_not_zeroed(self):
        # A candidate who has only sat Reading should see their Reading band.
        self.assertEqual(bands.overall_band([7.0, None, None, None]), Decimal("7.0"))

    def test_no_scores_at_all(self):
        self.assertIsNone(bands.overall_band([None, None, None, None]))
        self.assertIsNone(bands.overall_band([]))


class ProrateTests(unittest.TestCase):
    def test_full_length_test_is_unchanged(self):
        self.assertEqual(bands.prorate(30, 40), 30)

    def test_short_test_is_scaled_up(self):
        self.assertEqual(bands.prorate(27, 36), 30)

    def test_zero_answerable_questions(self):
        self.assertEqual(bands.prorate(0, 0), 0)

    def test_never_exceeds_the_maximum(self):
        self.assertEqual(bands.prorate(36, 36), 40)
        self.assertLessEqual(bands.prorate(40, 20), 40)


if __name__ == "__main__":
    unittest.main()
