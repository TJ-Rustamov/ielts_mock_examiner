"""Tests for locating reading passages on the page."""

import unittest

from exams.importer.layout import Line
from exams.importer.passages import passage_regions
from exams.importer.pdfsource import Word
from exams.importer.segment import READING, segment


def line(text, x0, y0, x1=None):
    return Line([Word(text, x0, y0, x1 if x1 is not None else x0 + 8 * len(text), y0 + 12)])


def book():
    return {
        1: [line("Test 1", 40, 30), line("READING", 40, 50), line("READING PASSAGE 1", 40, 70),
            line("The Davies Sisters", 60, 100), line("A Body text starts here.", 40, 400, 520)],
        2: [line("B More passage text on the next page.", 40, 60, 540),
            line("Final paragraph.", 40, 300),
            line("Questions 1-7", 40, 340), line("Complete the notes below.", 40, 360)],
        3: [line("Questions 8-13", 40, 60),
            line("Do the following statements agree with the information given in "
                 "Reading Passage 1?", 40, 80)],
    }


def regions_for(pages, padding=10):
    document = segment(pages)
    section = document.tests[0].modules[READING].sections[0]
    return passage_regions(section, pages, {n: (600.0, 800.0) for n in pages}, padding=padding)


class PassageRegionTests(unittest.TestCase):
    def test_passage_spans_its_pages_and_stops_at_the_questions(self):
        regions = regions_for(book())
        self.assertEqual([r["page"] for r in regions], [1, 2])
        # Page 1 starts at the title, below the "READING PASSAGE 1" header.
        self.assertEqual(regions[0]["bbox"][1], 90)
        self.assertEqual(regions[0]["bbox"][3], 422)
        # Page 2 ends with the passage, above "Questions 1-7".
        self.assertEqual(regions[1]["bbox"][3], 322)

    def test_every_page_shares_one_horizontal_extent(self):
        regions = regions_for(book())
        self.assertEqual({(r["bbox"][0], r["bbox"][2]) for r in regions}, {(30, 550)})

    def test_padding_never_cuts_into_the_heading_or_the_questions(self):
        regions = regions_for(book(), padding=30)
        # "READING PASSAGE 1" ends at y=82; "Questions 1-7" starts at y=340.
        self.assertEqual(regions[0]["bbox"][1], 83)
        self.assertEqual(regions[1]["bbox"][3], 339)

    def test_regions_are_clamped_to_the_page(self):
        pages = book()
        pages[1].append(line("wide", -5, 790, 700))
        section = segment(pages).tests[0].modules[READING].sections[0]
        region = passage_regions(section, pages, {1: (600.0, 800.0), 2: (600.0, 800.0)})[0]
        self.assertEqual(region["bbox"][0], 0)
        self.assertEqual(region["bbox"][2], 600)
        self.assertEqual(region["bbox"][3], 800)

    def test_no_lines_means_no_regions(self):
        pages = {1: [line("Test 1", 40, 30), line("READING", 40, 50),
                     line("READING PASSAGE 1", 40, 70), line("Questions 1-5", 40, 90)]}
        self.assertEqual(regions_for(pages), [])


if __name__ == "__main__":
    unittest.main()
