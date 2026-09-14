"""Per-type question-group parsers.

Each parser turns a :class:`~exams.importer.segment.GroupSpan` into a
:class:`ParsedGroup`: an option bank, a layout of renderable blocks, and one
entry per question number.

The layout grammar is deliberately tiny — heading / line / bullets / table /
flow — because the frontend renders every completion type with one component by
splitting each block's text on ``{{Qn}}``. One regex, one input component, the
same behaviour inside a table cell, a bullet and a flow step.

Degradation is the design, not an afterthought. Three levels:

1. type known but layout uncertain -> emit flat ``line`` blocks, still fully
   answerable, just less pretty;
2. type unknown -> keep the raw lines, flag for the admin to classify;
3. hopeless -> the group is flagged and can be excluded, without blocking the
   other 37 questions in the module.

Nothing here raises on bad input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from exams.importer import boilerplate as bp
from exams.importer.classify import Classification, classify
from exams.importer.gaps import template_lines
from exams.importer.layout import Line
from exams.importer.segment import GroupSpan

__all__ = ["ParsedGroup", "ParsedQuestion", "parse_group"]

#: "A  travel expenses" - an option in a lettered bank or an MCQ choice.
OPTION_LINE = re.compile(r"^([A-J])[\s.)\]]+(.+)$")

#: "11 What should trainees expect?" - a numbered question item.
ITEM_LINE = re.compile(r"^(\d{1,2})[\s.)\]]+(.+)$")

#: A bare number on its own line (labelling tasks list them beside the figure).
BARE_NUMBER = re.compile(r"^(\d{1,2})$")

#: Roman numerals are how headings banks are lettered in many books.
ROMAN_OPTION = re.compile(r"^(i{1,3}|iv|v|vi{1,3}|ix|x{1,3})[\s.)\]]+(.+)$", re.IGNORECASE)

COMPLETION_TYPES = frozenset({
    bp.NOTE_COMPLETION, bp.TABLE_COMPLETION, bp.FORM_COMPLETION,
    bp.FLOWCHART_COMPLETION, bp.SUMMARY_COMPLETION, bp.SUMMARY_COMPLETION_BANK,
    bp.SENTENCE_COMPLETION, bp.SHORT_ANSWER,
})

ITEM_TYPES = frozenset({
    bp.TFNG, bp.YNNG, bp.MATCHING_PARAGRAPH, bp.MATCHING_FEATURES,
    bp.MATCHING_BANK, bp.SENTENCE_ENDINGS, bp.LIST_OF_HEADINGS,
    bp.CLASSIFICATION,
})

LABELLING_TYPES = frozenset({
    bp.MAP_LABELLING, bp.PLAN_LABELLING, bp.DIAGRAM_LABELLING,
})


@dataclass
class ParsedQuestion:
    number: int
    prompt_text: str = ""
    options: list[dict] = field(default_factory=list)


@dataclass
class ParsedGroup:
    type: str
    instruction: str
    first_question: int
    last_question: int
    word_limit: str = ""
    select_count: int | None = None
    letter_range: tuple[str, str] | None = None
    options_reusable: bool = False
    options: list[dict] = field(default_factory=list)
    layout: list[dict] = field(default_factory=list)
    questions: list[ParsedQuestion] = field(default_factory=list)
    needs_figure: bool = False
    needs_review: bool = False
    warnings: list[str] = field(default_factory=list)
    page_start: int = 0
    page_end: int = 0

    @property
    def expected_numbers(self) -> list[int]:
        return list(range(self.first_question, self.last_question + 1))

    @property
    def found_numbers(self) -> list[int]:
        return [q.number for q in self.questions]


def _clean(line: Line) -> str:
    return " ".join(line.text.split())


def _split_bank_and_items(
    lines: list[Line], expected: set[int]
) -> tuple[list[dict], list[tuple[int, str]], list[Line]]:
    """Separate a lettered option bank from the numbered question items."""
    options: list[dict] = []
    items: list[tuple[int, str]] = []
    other: list[Line] = []

    for line in lines:
        text = _clean(line)
        if not text:
            continue

        item = ITEM_LINE.match(text)
        if item and int(item.group(1)) in expected:
            items.append((int(item.group(1)), item.group(2).strip()))
            continue

        bare = BARE_NUMBER.match(text)
        if bare and int(bare.group(1)) in expected:
            items.append((int(bare.group(1)), ""))
            continue

        option = OPTION_LINE.match(text)
        if option:
            options.append({"letter": option.group(1).upper(),
                            "text": option.group(2).strip()})
            continue

        roman = ROMAN_OPTION.match(text)
        if roman:
            options.append({"letter": roman.group(1).lower(),
                            "text": roman.group(2).strip()})
            continue

        other.append(line)

    return options, items, other


def _contiguous_from_a(options: list[dict]) -> list[dict]:
    """Keep only the leading run A, B, C... .

    A stray capital letter elsewhere on the page ("A shortage of buses...")
    would otherwise be swallowed into the bank. The run must start at A and
    ascend without gaps; the first break ends it.
    """
    kept: list[dict] = []
    expected = "A"
    for option in options:
        letter = option["letter"]
        if len(letter) == 1 and letter.isalpha() and letter.upper() == expected:
            kept.append(option)
            expected = chr(ord(expected) + 1)
        elif not kept:
            continue
        else:
            break
    if kept:
        return kept
    # Roman-numeral banks (headings lists) keep their own order.
    return [o for o in options if not (len(o["letter"]) == 1 and o["letter"].isalpha())]


def _completion_layout(lines: list[Line], expected: range) -> tuple[list[dict], list[int], list[str]]:
    templates, warnings = template_lines(lines, expected)
    blocks: list[dict] = []
    numbers: list[int] = []
    for template in templates:
        if not template.text.strip():
            continue
        blocks.append({"kind": "line", "text": template.text})
        numbers.extend(n for n in template.numbers if n is not None)
    return blocks, numbers, warnings


def parse_group(
    span: GroupSpan,
    classification: Classification | None = None,
) -> ParsedGroup:
    """Parse one question group. Never raises."""
    classification = classification or classify(span.instruction)
    expected_range = range(span.first_question, span.last_question + 1)
    expected = set(expected_range)

    group = ParsedGroup(
        type=classification.type,
        instruction=span.instruction,
        first_question=span.first_question,
        last_question=span.last_question,
        word_limit=classification.word_limit,
        select_count=classification.select_count,
        letter_range=classification.letter_range,
        options_reusable=classification.options_reusable,
        needs_figure=classification.needs_figure,
        needs_review=classification.needs_review,
        page_start=span.page_start,
        page_end=span.page_end,
    )

    # Drop the rubric itself from the body, so it is not rendered twice.
    body = [
        line for line in span.lines
        if not (classification.instruction
                and _clean(line) and _clean(line) in classification.instruction)
    ]
    body = [
        line for line in body
        if not bp.DROPPABLE_LEGEND.search(_clean(line))
        and not bp.ANSWER_SHEET_NOTE.search(_clean(line))
    ]

    if classification.type == bp.UNKNOWN:
        group.warnings.append(
            "instruction not recognised - an admin must choose the question type"
        )
        group.layout = [{"kind": "line", "text": _clean(line)} for line in body if _clean(line)]
        group.questions = [ParsedQuestion(number=n) for n in expected_range]
        group.needs_review = True
        return group

    options, items, other = _split_bank_and_items(body, expected)
    options = _contiguous_from_a(options)

    if classification.type in COMPLETION_TYPES:
        blocks, numbers, warnings = _completion_layout(body, expected_range)
        group.layout = blocks
        group.warnings.extend(warnings)
        found = sorted(set(numbers))
        group.questions = [ParsedQuestion(number=n) for n in expected_range]
        if classification.type == bp.SUMMARY_COMPLETION_BANK and options:
            group.options = options
        if not found:
            group.warnings.append(
                "no answer spaces were detected in this group's layout"
            )
            group.needs_review = True

    elif classification.type in (bp.MCQ_SINGLE, bp.MCQ_MULTI):
        group.questions = _parse_mcq(body, expected, group)

    elif classification.type in LABELLING_TYPES:
        group.options = options
        group.questions = [
            ParsedQuestion(number=number, prompt_text=text)
            for number, text in items
        ] or [ParsedQuestion(number=n) for n in expected_range]
        group.needs_figure = True
        if not items:
            group.warnings.append(
                "labels could not be paired with question numbers - check the "
                "cropped figure and the label list"
            )

    elif classification.type in ITEM_TYPES:
        group.options = options
        group.questions = [
            ParsedQuestion(number=number, prompt_text=text)
            for number, text in items
        ]
        if classification.type in (bp.TFNG, bp.YNNG):
            group.options = []

    else:  # pragma: no cover - every catalogue type is covered above
        group.layout = [{"kind": "line", "text": _clean(line)} for line in body if _clean(line)]
        group.questions = [ParsedQuestion(number=n) for n in expected_range]

    # Completion groups consume their whole body as layout, so there is nothing
    # left over to report; only the item/option-based types can strand a line.
    leftover = [] if classification.type in COMPLETION_TYPES else other
    _finalise(group, expected_range, leftover)
    return group


def _parse_mcq(body: list[Line], expected: set[int], group: ParsedGroup) -> list[ParsedQuestion]:
    """MCQ items: a numbered stem followed by its lettered choices."""
    questions: list[ParsedQuestion] = []
    current: ParsedQuestion | None = None
    shared: list[dict] = []

    for line in body:
        text = _clean(line)
        if not text:
            continue
        item = ITEM_LINE.match(text)
        if item and int(item.group(1)) in expected:
            current = ParsedQuestion(number=int(item.group(1)),
                                     prompt_text=item.group(2).strip())
            questions.append(current)
            continue
        option = OPTION_LINE.match(text)
        if option:
            entry = {"letter": option.group(1).upper(), "text": option.group(2).strip()}
            if current is not None:
                current.options.append(entry)
            else:
                shared.append(entry)
            continue
        if current is not None:
            current.prompt_text = f"{current.prompt_text} {text}".strip()

    # A multi-answer MCQ has one shared list of choices rather than per-item ones.
    if shared and not any(q.options for q in questions):
        group.options = _contiguous_from_a(shared)
    return questions


def _finalise(group: ParsedGroup, expected: range, leftover: list[Line]) -> None:
    """Fill gaps, cross-check numbering, and record anything unexplained."""
    found = {q.number for q in group.questions}
    missing = [n for n in expected if n not in found]
    if missing:
        group.warnings.append(
            f"no content found for question(s) {missing} in this group"
        )
        group.needs_review = True
        for number in missing:
            group.questions.append(ParsedQuestion(number=number))

    unexpected = sorted(found - set(expected))
    if unexpected:
        group.warnings.append(
            f"question number(s) {unexpected} are outside this group's range "
            f"{expected.start}-{expected.stop - 1}"
        )
        group.needs_review = True

    group.questions.sort(key=lambda q: q.number)

    if group.letter_range and group.options:
        start, end = group.letter_range
        wanted = ord(end) - ord(start) + 1
        if len(group.options) != wanted:
            group.warnings.append(
                f"instruction declares options {start}-{end} ({wanted}) but "
                f"{len(group.options)} were found"
            )
            group.needs_review = True

    if leftover:
        # Not an error: figure captions and stray artwork land here. Kept so the
        # admin can see what was set aside rather than wondering what was lost.
        group.warnings.append(
            f"{len(leftover)} line(s) were not attributed to a question or option"
        )

    if group.warnings:
        group.needs_review = True
