"""Tests for turning positioned words back into reading order.

Uses hand-built word boxes rather than real PDFs, so it runs without PyMuPDF
and without committing a 44MB book.
"""

import unittest

from exams.importer.layout import (
    build_lines,
    find_gutters,
    read_page,
    split_columns,
    strip_repeated_chrome,
)
from exams.importer.pdfsource import Word

PAGE_W = 600.0
PAGE_H = 800.0


def row(y, items, height=10.0):
    """Build a row of words: items is a list of (x0, x1, text)."""
    return [Word(text, x0, y, x1, y + height) for x0, x1, text in items]


class BuildLinesTests(unittest.TestCase):
    def test_words_group_into_lines_by_vertical_position(self):
        words = row(100, [(10, 40, "the"), (45, 90, "quick"), (95, 130, "fox")])
        words += row(120, [(10, 50, "jumped")])
        lines = build_lines(words)
        self.assertEqual([ln.text for ln in lines], ["the quick fox", "jumped"])

    def test_line_is_sorted_by_x_not_extraction_order(self):
        # This is the map-labelling repair: the numbers and their labels are
        # emitted as two separate runs, and must be interleaved by position.
        words = [
            Word("15", 60, 100, 75, 110),
            Word("16", 60, 130, 75, 140),
            Word("Engine", 200, 100, 250, 110),
            Word("Exhibition", 200, 130, 270, 140),
        ]
        lines = build_lines(words)
        self.assertEqual([ln.text for ln in lines], ["15 Engine", "16 Exhibition"])

    def test_empty_input(self):
        self.assertEqual(build_lines([]), [])


class GutterTests(unittest.TestCase):
    def _two_column_page(self):
        words = []
        for index in range(20):
            y = 100 + index * 20
            words += row(y, [(40, 240, f"left{index}")])
            words += row(y, [(340, 540, f"right{index}")])
        return words

    def test_finds_the_channel_between_two_columns(self):
        gutters = find_gutters(self._two_column_page(), PAGE_W)
        self.assertEqual(len(gutters), 1)
        x0, x1 = gutters[0]
        self.assertGreaterEqual(x0, 240 - 4)
        self.assertLessEqual(x1, 340 + 4)

    def test_single_column_page_has_no_gutter(self):
        words = []
        for index in range(20):
            words += row(100 + index * 20, [(40, 540, f"full{index}")])
        self.assertEqual(find_gutters(words, PAGE_W), [])

    def test_ordinary_word_spacing_is_not_a_gutter(self):
        words = []
        for index in range(20):
            y = 100 + index * 20
            words += row(y, [(40, 200, "a"), (210, 380, "b"), (390, 540, "c")])
        self.assertEqual(find_gutters(words, PAGE_W), [])

    def test_margins_are_not_gutters(self):
        words = []
        for index in range(20):
            words += row(100 + index * 20, [(200, 400, f"mid{index}")])
        self.assertEqual(find_gutters(words, PAGE_W), [])


class ColumnOrderTests(unittest.TestCase):
    def test_columns_are_read_one_after_the_other(self):
        """The Cambridge 21 page 119 failure, in miniature.

        Left column holds answers 1..3, right column holds a Part 3 block. Read
        as a flat stream they interleave; read by column they do not.
        """
        words = []
        left = ["1 January", "2 forty-eight", "3 pizza"]
        right = ["Part 3", "21 B", "22 D"]
        for index, (l, r) in enumerate(zip(left, right)):
            y = 200 + index * 20
            words += row(y, [(40, 240, l)])
            words += row(y, [(340, 540, r)])

        flat = " ".join(w.text for w in sorted(words, key=lambda w: (w.y0, w.x0)))
        self.assertIn("1 January Part 3", flat)  # the interleaving we must undo

        ordered = read_page(words, PAGE_W)
        text = " ".join(ln.text for ln in ordered)
        self.assertIn("1 January 2 forty-eight 3 pizza", text)
        self.assertIn("Part 3 21 B 22 D", text)
        self.assertNotIn("1 January Part 3", text)

    def test_full_width_heading_separates_column_blocks(self):
        words = row(50, [(40, 540, "TEST 2 LISTENING")])
        for index in range(6):
            y = 150 + index * 20
            words += row(y, [(40, 240, f"L{index}")])
            words += row(y, [(340, 540, f"R{index}")])

        ordered = [ln.text for ln in read_page(words, PAGE_W)]
        self.assertEqual(ordered[0], "TEST 2 LISTENING")
        self.assertEqual(ordered[1:7], [f"L{i}" for i in range(6)])
        self.assertEqual(ordered[7:13], [f"R{i}" for i in range(6)])

    def test_single_column_page_is_unchanged(self):
        words = []
        for index in range(5):
            words += row(100 + index * 20, [(40, 540, f"line{index}")])
        ordered = [ln.text for ln in read_page(words, PAGE_W)]
        self.assertEqual(ordered, [f"line{i}" for i in range(5)])


class ChromeStrippingTests(unittest.TestCase):
    def _book(self, pages=10):
        out = {}
        for number in range(1, pages + 1):
            words = row(20, [(40, 120, f"Test {number % 4 + 1}")])       # header
            words += row(400, [(40, 300, f"body text page {number}")])   # content
            words += row(770, [(40, 70, str(number))])                   # page number
            out[number] = build_lines(words)
        return out

    def test_running_header_and_page_number_removed(self):
        cleaned = strip_repeated_chrome(self._book(), PAGE_H)
        for number, lines in cleaned.items():
            texts = [ln.text for ln in lines]
            self.assertEqual(texts, [f"body text page {number}"])

    def test_body_text_in_the_middle_of_the_page_is_kept(self):
        cleaned = strip_repeated_chrome(self._book(), PAGE_H)
        self.assertTrue(all(len(lines) == 1 for lines in cleaned.values()))

    def test_digits_collapse_so_varying_numbers_still_match(self):
        # "Test 1" and "Test 3" are the same running header; 16 and 17 are the
        # same page-number element.
        cleaned = strip_repeated_chrome(self._book(), PAGE_H)
        joined = " ".join(ln.text for lines in cleaned.values() for ln in lines)
        self.assertNotIn("Test", joined)

    def test_a_one_off_line_in_the_header_band_survives(self):
        book = self._book()
        extra = build_lines(row(20, [(200, 400, "unique banner")]))
        book[1] = book[1] + extra
        cleaned = strip_repeated_chrome(book, PAGE_H)
        self.assertIn("unique banner", [ln.text for ln in cleaned[1]])

    def test_empty_input(self):
        self.assertEqual(strip_repeated_chrome({}, PAGE_H), {})


if __name__ == "__main__":
    unittest.main()
