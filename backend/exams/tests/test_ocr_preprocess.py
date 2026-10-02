"""Tests for scan cleanup before OCR: deskew and background flattening."""

import unittest

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover - exam extras not installed
    cv2 = None

from exams.importer import ocr


def synthetic_page(skew: float, shadow: bool = True):
    """Text-like bars on a page, rotated by `skew` degrees, on grey paper."""
    page = np.full((1400, 1000), 255, np.uint8)
    for row in range(30):
        y = 80 + row * 42
        for column in range(2):
            x = 80 + column * 460
            # A "word" every so often, so rows look like text, not stripes.
            for word in range(6):
                cv2.rectangle(page, (x + word * 65, y), (x + word * 65 + 50, y + 14), 0, -1)
    matrix = cv2.getRotationMatrix2D((500, 700), skew, 1.0)
    page = cv2.warpAffine(page, matrix, (1000, 1400), borderValue=255)
    if shadow:
        page = (page.astype(np.float32) * np.linspace(0.55, 0.95, 1000)[None, :]).astype(np.uint8)
    return page


@unittest.skipIf(cv2 is None, "OpenCV not installed")
class DeskewTests(unittest.TestCase):
    def test_skew_is_found_and_undone(self):
        for skew in (-3.0, -1.5, 2.0):
            with self.subTest(skew=skew):
                page = ocr.normalise_background(synthetic_page(skew))
                self.assertAlmostEqual(ocr.estimate_skew(page), -skew, delta=0.3)

    def test_straight_page_is_left_alone(self):
        _, angle = ocr.preprocess(synthetic_page(0.0))
        self.assertEqual(angle, 0.0)

    def test_shadow_does_not_fool_the_skew_search(self):
        # Without flattening, Otsu takes the dark side of the page for ink.
        _, angle = ocr.preprocess(synthetic_page(2.0, shadow=True))
        self.assertAlmostEqual(angle, -2.0, delta=0.3)

    def test_background_is_flattened_to_white(self):
        flat = ocr.normalise_background(synthetic_page(0.0, shadow=True))
        # The darkest paper (left edge, no ink) comes out near white.
        self.assertGreater(int(np.median(flat[:, :60])), 230)


class WordAssemblyTests(unittest.TestCase):
    """Characters from the recogniser -> words, recovering dropped spaces."""

    @staticmethod
    def chars(text, start=0, width=10, gap=2, word_gap=None):
        out, x = [], start
        for ch in text:
            if ch == "_":  # a gap with no space character in the output
                x += word_gap or width
                continue
            out.append((ch, (x, 0, x + width, 20), 0.99))
            x += width + gap
        return out

    def test_explicit_space_splits(self):
        words = ocr.words_from_fragments(self.chars("11") + [(" ", (24, 0, 30, 20), 1.0)]
                                         + self.chars("mining", start=32))
        self.assertEqual([w[0] for w in words], ["11", "mining"])

    def test_wide_gap_splits_when_the_space_was_dropped(self):
        words = ocr.words_from_fragments(self.chars("13_NOT"))
        self.assertEqual([w[0] for w in words], ["13", "NOT"])

    def test_confidence_is_the_weakest_character(self):
        fragments = self.chars("cafe")
        fragments[1] = ("a", fragments[1][1], 0.4)
        self.assertEqual(ocr.words_from_fragments(fragments)[0][2], 0.4)


if __name__ == "__main__":
    unittest.main()
