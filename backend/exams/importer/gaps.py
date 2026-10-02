"""Gap-slot detection: turn "7 ........." into the placeholder ``{{Q7}}``.

The single most reused primitive in the importer. Note completion, table
completion, form completion, flow-chart completion, summary completion and
sentence completion all reduce to "text with numbered holes in it", and the
frontend renders every one of them with the same component by splitting on
``{{Qn}}``. Getting this right once makes all six types work.

Detection is **geometric first, characters second**. On a page with a text
layer the blank arrives as a run of periods, but OCR at 150 DPI frequently
reads that run as dashes, as a single long dash, or drops it entirely while
leaving the whitespace. A wide horizontal gap after a question number is the
signal that survives all three.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from exams.importer.layout import Line
from exams.importer.pdfsource import Word

__all__ = ["BlankSlot", "TemplateLine", "to_template", "template_lines"]

#: A run of dots, underscores or dashes standing in for the answer space.
DOT_RUN = re.compile(r"^[.…_–—\-]{3,}$")

#: A token that is only a question number.
NUMBER = re.compile(r"^(\d{1,2})$")

#: A number immediately followed by its dot run, with no space between them.
NUMBER_THEN_DOTS = re.compile(r"^(\d{1,2})[.…_–—\-]{3,}$")

#: A gap this many times the line's typical word spacing counts as a blank even
#: when no dot characters survived extraction.
GAP_FACTOR = 3.0


@dataclass
class BlankSlot:
    number: int | None
    #: Index into the line's token list where the blank was found.
    position: int
    #: True when inferred from spacing rather than read from dot characters.
    geometric: bool = False


@dataclass
class TemplateLine:
    text: str
    blanks: list[BlankSlot] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def numbers(self) -> list[int]:
        return [b.number for b in self.blanks if b.number is not None]


def _median_gap(words: list[Word]) -> float:
    gaps = [
        words[i + 1].x0 - words[i].x1
        for i in range(len(words) - 1)
        if words[i + 1].x0 > words[i].x1
    ]
    if not gaps:
        return 0.0
    gaps.sort()
    return gaps[len(gaps) // 2]


def _tokens(words: list[Word]) -> list[tuple[str, Word, bool]]:
    """Split each word box into its whitespace tokens.

    Native words are single tokens. An OCR box can hold several - on a RapidOCR
    build without character positions a whole detected line arrives as one
    box ("7 ......... toiletries"). Splitting the text recovers the dot-run and
    trailing-number rules; the geometric-gap rule then applies only *between*
    boxes, where the gap was actually measured. Nothing inside a box gets a
    made-up coordinate.

    Returns (token, source word, token ends its box).
    """
    out: list[tuple[str, Word, bool]] = []
    for word in words:
        parts = word.text.split() or [word.text]
        if word.segment >= 0:
            parts = [piece for part in parts for piece in _unglue(part)]
        for index, part in enumerate(parts):
            out.append((part, word, index == len(parts) - 1))
    return out


#: A word with a question number glued to its end - "the1", "visit12" - which
#: is how OCR delivers "the 1 ........" once it has dropped both the dots and
#: the space. Letters first, so "10/ten" and "13th" are untouched.
_GLUED_NUMBER = re.compile(r"^([A-Za-z][A-Za-z'’]*)(\d{1,2})$")


def _unglue(token: str) -> list[str]:
    """Split a trailing glued number off an OCR token. Native text never is."""
    match = _GLUED_NUMBER.match(token)
    if not match:
        return [token]
    return [match.group(1), match.group(2)]


def to_template(
    line: Line,
    expected: range | set[int] | None = None,
) -> TemplateLine:
    """Rewrite one line, replacing each answer space with ``{{Qn}}``.

    `expected` is the group's question range. Supplying it is what stops a
    number inside the prose ("a maximum of 12 people") being mistaken for a
    question number: only numbers the group actually owns become blanks.
    """
    words = line.words
    if not words:
        return TemplateLine("")

    def in_range(value: int) -> bool:
        return expected is None or value in expected

    median = _median_gap(words)
    wide_gap = median * GAP_FACTOR if median > 0 else None
    tokens = _tokens(words)

    def gap_after(index: int) -> float | None:
        """Measured gap after token `index`, or None inside one box."""
        _text, word, ends_box = tokens[index]
        if not ends_box or index + 1 >= len(tokens):
            return None
        return tokens[index + 1][1].x0 - word.x1

    parts: list[str] = []
    blanks: list[BlankSlot] = []
    warnings: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index][0]

        # "7..........." - number and dots fused into one token.
        fused = NUMBER_THEN_DOTS.match(token)
        if fused and in_range(int(fused.group(1))):
            number = int(fused.group(1))
            parts.append(f"{{{{Q{number}}}}}")
            blanks.append(BlankSlot(number, index))
            index += 1
            continue

        number_match = NUMBER.match(token)
        if number_match and in_range(int(number_match.group(1))):
            number = int(number_match.group(1))
            following = tokens[index + 1][0] if index + 1 < len(tokens) else None

            # "7 ..........."
            if following is not None and DOT_RUN.match(following):
                parts.append(f"{{{{Q{number}}}}}")
                blanks.append(BlankSlot(number, index))
                index += 2
                continue

            # "7      and toiletries" - the dots did not survive extraction but
            # the space they occupied did.
            gap = gap_after(index)
            if following is not None and wide_gap is not None and gap is not None \
                    and gap >= wide_gap:
                parts.append(f"{{{{Q{number}}}}}")
                blanks.append(BlankSlot(number, index, geometric=True))
                index += 1
                continue

            # A trailing number at the end of a line is a blank whose answer
            # space runs to the margin.
            if following is None:
                parts.append(f"{{{{Q{number}}}}}")
                blanks.append(BlankSlot(number, index, geometric=True))
                index += 1
                continue

        # A dot run with no question number in front of it.
        if DOT_RUN.match(token):
            previous = parts[-1] if parts else ""
            if not previous.startswith("{{Q"):
                warnings.append(
                    f"answer space with no question number before it "
                    f"(after {previous!r})"
                )
                parts.append("{{Q?}}")
                blanks.append(BlankSlot(None, index))
            index += 1
            continue

        parts.append(token)
        index += 1

    return TemplateLine(" ".join(parts), blanks, warnings)


def template_lines(
    lines: list[Line],
    expected: range | set[int] | None = None,
) -> tuple[list[TemplateLine], list[str]]:
    """Apply :func:`to_template` across a group's lines.

    Also reports which of the expected question numbers never produced a blank,
    which is the check that catches a completion group whose layout defeated the
    parser: the numbers are known from the "Questions 1-10" header, so a missing
    one is detectable without any knowledge of the content.
    """
    out = [to_template(line, expected) for line in lines]
    warnings: list[str] = []
    for template in out:
        warnings.extend(template.warnings)

    if expected is not None:
        found = {n for template in out for n in template.numbers}
        missing = sorted(set(expected) - found)
        if missing:
            warnings.append(
                f"no answer space found for question(s) {missing} - the layout "
                "needs checking"
            )
    return out, warnings
