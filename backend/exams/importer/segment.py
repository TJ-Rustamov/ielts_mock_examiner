"""Split a book into tests -> skills -> sections -> question groups.

Driven **entirely by anchors found in the document**. No page maps, no page
counts, no assumed number of tests: the Cambridge 21 page map recorded in the
plan is a test fixture and a cross-check, never an input. A book with three
tests, or one whose listening sections are called "Section" instead of "Part",
must work without touching this file.

Where the structure is not what IELTS requires (a module that does not reach 40
questions, numbering with a hole in it), the discrepancy is recorded as a
warning with the exact numbers and carried forward for the admin. Nothing here
raises: a malformed book should produce a reviewable draft, not a traceback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from exams.importer import boilerplate as bp
from exams.importer.layout import Line

__all__ = [
    "GroupSpan", "SectionSpan", "ModuleSpan", "TestSpan", "Document",
    "segment", "READING", "LISTENING",
]

READING = "reading"
LISTENING = "listening"
WRITING = "writing"
SPEAKING = "speaking"

_SPELLED = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# A test heading. Tolerates "Practice Test 2" and spelled-out numbers, which
# older editions and non-Cambridge books use.
_TEST = re.compile(
    r"^(?:practice\s+)?test\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s*$",
    re.IGNORECASE,
)

# The skill header, optionally qualified ("ACADEMIC READING", "READING MODULE").
_SKILL = re.compile(
    r"^(?:academic\s+|general\s+training\s+)?"
    r"(listening|reading|writing|speaking)"
    r"(?:\s+module)?\s*$",
    re.IGNORECASE,
)

# Listening subsections. Older books say SECTION where newer ones say PART.
#
# The trailing range is the subsection's overall span, typeset on the same line
# as the header ("PART 4 Questions 31-40"). It must be CAPTURED, not discarded:
# when a part has several groups the range is merely a summary and the real
# groups follow as their own "Questions 1-6" lines, but when a part is a single
# group - which is most Part 1s and Part 4s - this line is the only place that
# range ever appears. Discarding it lost all ten questions of those parts.
# Captured here and turned into a provisional group, which is dropped later
# only if narrower groups turn out to cover it.
_PART = re.compile(
    r"^(?:part|section)\s+(\d+)\b"
    r"(?:\s+questions?\s+(\d+)\s*[-–—]\s*(\d+))?\s*$",
    re.IGNORECASE,
)

# Reading subsections. General Training uses SECTION here too, which is why the
# skill context decides how a bare "SECTION n" is interpreted.
_PASSAGE = re.compile(
    r"^reading\s+passage\s+(\d+)\b"
    r"(?:\s+questions?\s+(\d+)\s*[-–—]\s*(\d+))?\s*$",
    re.IGNORECASE,
)

_QUESTIONS = re.compile(
    r"^questions?\s+(\d+)\s*[-–—]\s*(\d+)\s*$", re.IGNORECASE
)
_QUESTION_ONE = re.compile(r"^question\s+(\d+)\s*$", re.IGNORECASE)

# Back matter. "Tapescript" is what pre-2010 Cambridge editions call the
# audioscript; missing it would swallow the answer keys into the last test.
_BACK_MATTER = re.compile(
    r"^(?:"
    r"(?P<keys>listening and reading answer keys?|answer keys?)"
    r"|(?P<scripts>audioscripts?|tapescripts?|transcripts?)"
    r"|(?P<writing>sample (?:writing )?answers?)"
    r"|(?P<end>acknowledgements?|acknowledgments?)"
    r")\s*$",
    re.IGNORECASE,
)


@dataclass
class GroupSpan:
    first_question: int
    last_question: int
    instruction: str = ""
    lines: list[Line] = field(default_factory=list)
    page_start: int = 0
    page_end: int = 0
    #: True for a "Questions 1-10" line that restates a part's whole span. Kept
    #: only if no narrower groups turn up to cover it.
    provisional: bool = False

    @property
    def count(self) -> int:
        return self.last_question - self.first_question + 1


@dataclass
class SectionSpan:
    kind: str           # "part" (listening) | "passage" (reading)
    order: int
    lines: list[Line] = field(default_factory=list)
    groups: list[GroupSpan] = field(default_factory=list)
    page_start: int = 0
    page_end: int = 0
    title: str = ""
    first_question: int = 0
    last_question: int = 0


@dataclass
class ModuleSpan:
    skill: str
    sections: list[SectionSpan] = field(default_factory=list)

    @property
    def question_numbers(self) -> list[int]:
        numbers: list[int] = []
        for section in self.sections:
            for group in section.groups:
                numbers.extend(range(group.first_question, group.last_question + 1))
        return sorted(numbers)


@dataclass
class TestSpan:
    number: int
    modules: dict[str, ModuleSpan] = field(default_factory=dict)


@dataclass
class Document:
    tests: list[TestSpan] = field(default_factory=list)
    back_matter: dict[str, list[Line]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def test(self, number: int) -> TestSpan | None:
        for candidate in self.tests:
            if candidate.number == number:
                return candidate
        return None


def is_structural_anchor(text: str) -> bool:
    """True for a line the segmenter needs in order to find structure.

    Chrome removal must never delete these. The running header and the real
    section heading are the *same text* ("Test 1" appears both at the top of
    every page of that test and as its title), so frequency alone cannot tell
    them apart. Protecting anchors and making the segmenter idempotent — it
    re-selects an existing test rather than creating a duplicate — handles both
    roles without having to distinguish them.
    """
    stripped = " ".join(text.split())
    if not stripped:
        return False
    return bool(
        _test_number(stripped)
        or _SKILL.match(stripped)
        or _PART.match(stripped)
        or _PASSAGE.match(stripped)
        or _QUESTIONS.match(stripped)
        or _QUESTION_ONE.match(stripped)
        or _BACK_MATTER.match(stripped)
    )


def _test_number(text: str) -> int | None:
    match = _TEST.match(text.strip())
    if not match:
        return None
    token = match.group(1).lower()
    return int(token) if token.isdigit() else _SPELLED.get(token)


def segment(pages: dict[int, list[Line]]) -> Document:
    """Walk the page/line stream and build the structure.

    `pages` maps page number -> lines in reading order (see ``layout.read_page``
    and ``layout.strip_repeated_chrome``).
    """
    document = Document()
    test: TestSpan | None = None
    module: ModuleSpan | None = None
    section: SectionSpan | None = None
    group: GroupSpan | None = None
    back_matter_key: str | None = None
    seen_first_test = False
    expect_section_range = False

    def close_group() -> None:
        nonlocal group
        group = None

    for page_number in sorted(pages):
        for line in pages[page_number]:
            text = " ".join(line.text.split())
            if not text:
                continue

            # --- back matter: everything after this belongs to the book, not
            # --- to a test, so close the current test out entirely.
            matter = _BACK_MATTER.match(text)
            if matter:
                back_matter_key = next(
                    key for key, value in matter.groupdict().items() if value
                )
                document.back_matter.setdefault(back_matter_key, [])
                test = module = section = None
                close_group()
                continue
            if back_matter_key:
                # A new test heading after the back matter starts would be odd;
                # treat the rest of the book as back matter.
                document.back_matter[back_matter_key].append(line)
                continue

            number = _test_number(text)
            if number is not None:
                seen_first_test = True
                existing = document.test(number)
                if existing is not None:
                    # "Test 1" also runs as a header on every page of that test.
                    # Re-selecting rather than recreating makes those headers
                    # harmless: creating a new TestSpan each time fragmented one
                    # test into twenty, each with no question groups.
                    test = existing
                else:
                    test = TestSpan(number=number)
                    document.tests.append(test)
                    module = section = None
                    close_group()
                continue

            # Everything before the first "Test N" is front matter. The
            # Introduction discusses rubrics at length, so parsing it would
            # invent question groups that do not exist.
            if not seen_first_test:
                continue

            skill_match = _SKILL.match(text)
            if skill_match and test is not None:
                skill = skill_match.group(1).lower()
                existing_module = test.modules.get(skill)
                if existing_module is not None:
                    # Same reasoning as the test heading: "Listening" / "Reading"
                    # repeat as running headers, so re-select the module and keep
                    # the current section instead of starting an empty new one.
                    module = existing_module
                else:
                    module = ModuleSpan(skill=skill)
                    test.modules[skill] = module
                    section = None
                    close_group()
                continue

            if module is None:
                continue

            passage_match = _PASSAGE.match(text)
            part_match = _PART.match(text)
            header_match = passage_match or (
                part_match if module.skill == READING else None
            )
            if header_match is None and part_match and module.skill == LISTENING:
                header_match = part_match
            if header_match is not None:
                kind = "part" if (
                    part_match is header_match and module.skill == LISTENING
                ) else "passage"
                section = SectionSpan(
                    kind=kind, order=int(header_match.group(1)),
                    page_start=page_number, page_end=page_number,
                )
                module.sections.append(section)
                close_group()

                inline_first, inline_last = header_match.group(2), header_match.group(3)
                if inline_first and inline_last:
                    # The range was on the header line itself. Open a provisional
                    # group for it right away and let the following lines attach,
                    # so a single-group part keeps its questions instead of
                    # losing them with the discarded range.
                    section.first_question = int(inline_first)
                    section.last_question = int(inline_last)
                    group = GroupSpan(
                        first_question=section.first_question,
                        last_question=section.last_question,
                        page_start=page_number, page_end=page_number,
                        provisional=True,
                    )
                    section.groups.append(group)
                    expect_section_range = False
                else:
                    expect_section_range = True
                continue

            questions_match = _QUESTIONS.match(text)
            single_match = _QUESTION_ONE.match(text)

            # "PART 1" is followed by "Questions 1-10" - the part's overall span.
            # Usually that is a summary and the real groups follow as narrower
            # "Questions 1-6" lines, in which case counting it as a group
            # duplicates every question in the part (a module reporting 62
            # answers out of 40). But a part with a single group spanning the
            # whole range produces the identical line. So record it as
            # provisional and drop it later only if other groups cover it.
            provisional = expect_section_range and bool(questions_match)
            if provisional and section is not None:
                section.first_question = int(questions_match.group(1))
                section.last_question = int(questions_match.group(2))
            expect_section_range = False

            if questions_match or single_match:
                if section is None:
                    # A group before any section header: synthesise one rather
                    # than dropping the questions on the floor.
                    section = SectionSpan(
                        kind="part" if module.skill == LISTENING else "passage",
                        order=len(module.sections) + 1,
                        page_start=page_number, page_end=page_number,
                    )
                    module.sections.append(section)
                    document.warnings.append(
                        f"page {page_number}: '{text}' appears before any section "
                        f"header in {module.skill}; a section was synthesised"
                    )
                if questions_match:
                    first, last = (int(questions_match.group(1)),
                                   int(questions_match.group(2)))
                else:
                    first = last = int(single_match.group(1))
                group = GroupSpan(
                    first_question=first, last_question=last,
                    page_start=page_number, page_end=page_number,
                    provisional=provisional,
                )
                section.groups.append(group)
                continue

            # Ordinary content.
            if group is not None:
                group.lines.append(line)
                group.page_end = page_number
            elif section is not None:
                section.lines.append(line)
                section.page_end = page_number

    _drop_redundant_provisional_groups(document)
    _attach_instructions(document)
    _validate(document)
    return document


def _drop_redundant_provisional_groups(document: Document) -> None:
    """Reconcile a part's summary range against the groups actually found.

    A provisional group comes from a "PART 4 Questions 31-40" header. Three
    outcomes, and the middle one matters:

    * every number is covered by real groups -> the summary is redundant, drop it;
    * only some are covered -> the uncovered questions are real but their own
      group header was missed, so trim the summary to just those rather than
      dropping it (which loses questions) or keeping it whole (which duplicates
      the covered ones, and is why a module reported 52 answers for 40);
    * nothing covered -> the part is a single group, keep it as is.
    """
    for test in document.tests:
        for module in test.modules.values():
            for section in module.sections:
                provisional = [g for g in section.groups if g.provisional]
                if not provisional:
                    continue
                covered = {
                    n for g in section.groups if not g.provisional
                    for n in range(g.first_question, g.last_question + 1)
                }
                if not covered:
                    continue

                kept: list[GroupSpan] = []
                for group in section.groups:
                    if not group.provisional:
                        kept.append(group)
                        continue
                    remaining = sorted(
                        set(range(group.first_question, group.last_question + 1))
                        - covered
                    )
                    if not remaining:
                        continue
                    if remaining[-1] - remaining[0] + 1 != len(remaining):
                        # A gapped remainder cannot be expressed as one range;
                        # keeping min..max would re-introduce the duplicates.
                        document.warnings.append(
                            f"Test {test.number} {module.skill} "
                            f"{section.kind} {section.order}: questions "
                            f"{remaining} have no group header of their own"
                        )
                        continue
                    group.first_question = remaining[0]
                    group.last_question = remaining[-1]
                    kept.append(group)
                section.groups = kept


def _attach_instructions(document: Document) -> None:
    """Take each group's leading lines as its instruction block.

    The rubric is whatever precedes the first question item, joined into one
    string — classification has to run on the joined form because extraction
    hands the rubric over in fragments ("Write" / "ONE WORD ONLY" / "for each
    answer."), and no pattern survives that split.
    """
    from exams.importer.classify import looks_like_rubric

    item_start = re.compile(r"^(?:\d{1,2}[\s.)\]]|[A-J][\s.)\]])")

    for test in document.tests:
        for module in test.modules.values():
            for section in module.sections:
                for group in section.groups:
                    rubric: list[str] = []
                    fallback: list[str] = []
                    for line in group.lines:
                        text = " ".join(line.text.split())
                        if not text:
                            continue
                        if bp.DROPPABLE_LEGEND.search(text):
                            # The TRUE/FALSE/NOT GIVEN legend is two-column
                            # boilerplate that mispairs when parsed. Recognise
                            # and drop it; the UI renders a canonical legend.
                            continue
                        if bp.ANSWER_SHEET_NOTE.search(text):
                            continue
                        if looks_like_rubric(text):
                            rubric.append(text)
                            continue
                        # First line that is not rubric ends the instruction.
                        if rubric:
                            break
                        if item_start.match(text):
                            break
                        # Nothing matched yet: keep a couple of leading lines so
                        # an unrecognised rubric still reaches the classifier's
                        # fuzzy pass and the admin can see what it was.
                        if len(fallback) < 3:
                            fallback.append(text)
                        else:
                            break
                    group.instruction = " ".join(rubric or fallback)


def _validate(document: Document) -> None:
    """Record structural problems as warnings. Never raises."""
    if not document.tests:
        document.warnings.append(
            "no 'Test N' heading was found - the book may use different wording, "
            "or the pages may need OCR"
        )

    for test in document.tests:
        for skill, module in test.modules.items():
            if skill not in (READING, LISTENING):
                continue
            numbers = module.question_numbers
            if not numbers:
                document.warnings.append(
                    f"Test {test.number} {skill}: no question groups found"
                )
                continue
            duplicates = {n for n in numbers if numbers.count(n) > 1}
            if duplicates:
                document.warnings.append(
                    f"Test {test.number} {skill}: duplicate question numbers "
                    f"{sorted(duplicates)}"
                )
            expected = set(range(1, max(numbers) + 1))
            missing = sorted(expected - set(numbers))
            if missing:
                document.warnings.append(
                    f"Test {test.number} {skill}: question numbers not contiguous, "
                    f"missing {missing}"
                )
            if max(numbers) != 40:
                document.warnings.append(
                    f"Test {test.number} {skill}: highest question number is "
                    f"{max(numbers)}, expected 40"
                )
