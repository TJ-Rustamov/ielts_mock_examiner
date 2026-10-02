"""The instruction-line catalogue: rubric wording -> question type.

Cambridge question papers are typeset from a rigid template, and the line above
every question group *declares its own type*::

    Choose the correct letter, A, B or C.
    Do the following statements agree with the information given in Reading Passage 1?
    Complete the notes below. Write ONE WORD ONLY for each answer.
    Label the map below.

So classification is a lookup table, not an inference problem. This module is
that table, and it is **data, not logic**: supporting a new book means adding
phrasings here, never editing the parser. If you find yourself writing
``if book.slug == ...`` anywhere in this package, this file is what should have
changed instead.

Coverage is the whole IELTS question-type universe, not merely the types that
happen to appear in Cambridge 20/21. Several entries below (list of headings,
classification, pick-from-a-list, short answer) appear in *neither* of those
books; they are here because other editions use them, and the test suite feeds
them hand-written rubrics so the claim is checked rather than asserted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "TYPES",
    "CATALOGUE",
    "Rubric",
    "WORD_LIMIT_PATTERNS",
    "LETTER_RANGE",
    "SELECT_COUNT",
    "REUSABLE",
    "NUMBER_WORDS",
]

# --- question types --------------------------------------------------------

MCQ_SINGLE = "mcq_single"
MCQ_MULTI = "mcq_multi"
TFNG = "tfng"
YNNG = "ynng"
LIST_OF_HEADINGS = "list_of_headings"
MATCHING_PARAGRAPH = "matching_paragraph"
MATCHING_FEATURES = "matching_features"
MATCHING_BANK = "matching_bank"
SENTENCE_ENDINGS = "sentence_endings"
CLASSIFICATION = "classification"
SHORT_ANSWER = "short_answer"
NOTE_COMPLETION = "note_completion"
TABLE_COMPLETION = "table_completion"
FORM_COMPLETION = "form_completion"
FLOWCHART_COMPLETION = "flowchart_completion"
SUMMARY_COMPLETION = "summary_completion"
SUMMARY_COMPLETION_BANK = "summary_completion_bank"
SENTENCE_COMPLETION = "sentence_completion"
DIAGRAM_LABELLING = "diagram_labelling"
MAP_LABELLING = "map_labelling"
PLAN_LABELLING = "plan_labelling"
UNKNOWN = "unknown"

TYPES = (
    MCQ_SINGLE, MCQ_MULTI, TFNG, YNNG, LIST_OF_HEADINGS, MATCHING_PARAGRAPH,
    MATCHING_FEATURES, MATCHING_BANK, SENTENCE_ENDINGS, CLASSIFICATION,
    SHORT_ANSWER, NOTE_COMPLETION, TABLE_COMPLETION, FORM_COMPLETION,
    FLOWCHART_COMPLETION, SUMMARY_COMPLETION, SUMMARY_COMPLETION_BANK,
    SENTENCE_COMPLETION, DIAGRAM_LABELLING, MAP_LABELLING, PLAN_LABELLING,
    UNKNOWN,
)

#: Types whose answers are option letters rather than free text. The answer-key
#: parser needs this to know that a bare "I" is the letter I and not an OCR'd
#: alternatives pipe.
LETTER_ANSWER_TYPES = frozenset({
    MCQ_SINGLE, MCQ_MULTI, LIST_OF_HEADINGS, MATCHING_PARAGRAPH,
    MATCHING_FEATURES, MATCHING_BANK, SENTENCE_ENDINGS, CLASSIFICATION,
    DIAGRAM_LABELLING, MAP_LABELLING, PLAN_LABELLING,
})

#: Types that need a cropped figure from the page to be answerable at all.
FIGURE_TYPES = frozenset({
    DIAGRAM_LABELLING, MAP_LABELLING, PLAN_LABELLING, FLOWCHART_COMPLETION,
})


@dataclass(frozen=True)
class Rubric:
    """One catalogue entry: a canonical phrasing and the type it declares."""

    type: str
    #: Regex matched against the normalised instruction text. Ordered most
    #: specific first within a type, because the first hit wins.
    pattern: str
    #: Plain-language phrasing, used for fuzzy matching when OCR has mangled the
    #: line badly enough that the regex misses.
    canonical: str
    note: str = ""


# Order matters: the classifier tries these top to bottom and takes the first
# match, so narrower rubrics must precede broader ones. In particular
# "Complete the summary ... list of words" must beat plain "Complete the
# summary", and YES/NO must beat TRUE/FALSE (both open "Do the following
# statements agree ...").
CATALOGUE: tuple[Rubric, ...] = (
    # --- opinion vs fact: these two share an opening clause -----------------
    Rubric(
        YNNG,
        r"do the following statements agree with the (?:claims|views)\b",
        "Do the following statements agree with the claims of the writer",
        "YES / NO / NOT GIVEN - about the writer's opinion",
    ),
    Rubric(
        YNNG,
        r"\byes\b.{0,20}\bno\b.{0,20}not\s*given",
        "YES NO NOT GIVEN",
        "matched from the legend when the lead-in line was lost",
    ),
    Rubric(
        TFNG,
        r"do the following statements agree with the information\b",
        "Do the following statements agree with the information given in the passage",
        "TRUE / FALSE / NOT GIVEN - about facts in the passage",
    ),
    Rubric(
        TFNG,
        r"\btrue\b.{0,20}\bfalse\b.{0,20}not\s*given",
        "TRUE FALSE NOT GIVEN",
        "matched from the legend when the lead-in line was lost",
    ),

    # --- multiple choice ----------------------------------------------------
    Rubric(
        MCQ_MULTI,
        r"choose\s+(two|three|four|2|3|4)\s+letters",
        "Choose TWO letters, A-E.",
    ),
    Rubric(
        MCQ_MULTI,
        r"which\s+(two|three|2|3)\s+(?:of the following|.{0,30}\?)",
        "Which TWO of the following ...?",
        "pick-from-a-list; marked as multi-answer MCQ",
    ),
    Rubric(
        MCQ_SINGLE,
        r"choose\s+the\s+correct\s+letter",
        "Choose the correct letter, A, B or C.",
    ),

    # --- labelling (needs a cropped figure) ---------------------------------
    # These come before the matching rubrics on purpose: a map-labelling
    # instruction also says "Write the correct letter, A-I, next to Questions
    # 15-20", which would otherwise be captured by MATCHING_BANK below.
    Rubric(MAP_LABELLING, r"label\s+the\s+map", "Label the map below."),
    Rubric(PLAN_LABELLING, r"label\s+the\s+plan", "Label the plan below."),
    Rubric(DIAGRAM_LABELLING, r"label\s+the\s+diagram", "Label the diagram below."),

    # --- completion ---------------------------------------------------------
    # Also before the matching rubrics: a flow-chart task can say "Choose FOUR
    # answers from the box", and it is a flow-chart first and a bank second -
    # it needs the figure rendered, which MATCHING_BANK would not do.
    Rubric(
        SUMMARY_COMPLETION_BANK,
        r"complete\s+the\s+summary\s+(?:below\s+)?using\s+the\s+list\s+of\s+(?:words|phrases)",
        "Complete the summary using the list of words, A-I, below.",
    ),
    Rubric(
        SUMMARY_COMPLETION,
        r"complete\s+the\s+summary",
        "Complete the summary below.",
    ),
    Rubric(
        FLOWCHART_COMPLETION,
        r"complete\s+the\s+flow[\s-]*chart",
        "Complete the flow-chart below.",
    ),
    Rubric(NOTE_COMPLETION, r"complete\s+the\s+notes", "Complete the notes below."),
    Rubric(TABLE_COMPLETION, r"complete\s+the\s+table", "Complete the table below."),
    Rubric(FORM_COMPLETION, r"complete\s+the\s+form", "Complete the form below."),
    Rubric(
        SENTENCE_ENDINGS,
        r"complete\s+each\s+sentence\s+with\s+the\s+correct\s+ending",
        "Complete each sentence with the correct ending, A-F, below.",
    ),
    Rubric(
        SENTENCE_COMPLETION,
        r"complete\s+the\s+sentences",
        "Complete the sentences below.",
    ),

    # --- matching -----------------------------------------------------------
    Rubric(
        LIST_OF_HEADINGS,
        r"choose\s+the\s+correct\s+heading",
        "Choose the correct heading for each paragraph from the list of headings below.",
        "absent from Cambridge 21 - covered by hand-written test rubrics",
    ),
    Rubric(
        LIST_OF_HEADINGS,
        r"list\s+of\s+headings",
        "List of Headings",
    ),
    Rubric(
        MATCHING_PARAGRAPH,
        r"which\s+(?:paragraph|section)\s+contains",
        "Which paragraph contains the following information?",
    ),
    Rubric(
        MATCHING_PARAGRAPH,
        r"has\s+(?:\w+|\d+)\s+(?:paragraphs|sections)\s*,?\s*[a-j]\s*[-–]\s*[a-j]",
        "Reading Passage 1 has seven paragraphs, A-G.",
    ),
    Rubric(
        MATCHING_FEATURES,
        r"look\s+at\s+the\s+following\s+.{0,40}\band\s+the\s+list\s+of\b",
        "Look at the following statements and the list of people below.",
    ),
    Rubric(
        MATCHING_FEATURES,
        r"match\s+each\b",
        "Match each statement with the correct person.",
    ),
    Rubric(
        CLASSIFICATION,
        r"classify\s+the\s+following",
        "Classify the following as ...",
        "absent from Cambridge 21 - covered by hand-written test rubrics",
    ),
    Rubric(
        MATCHING_BANK,
        r"choose\s+(?:\w+|\d+)\s+answers?\s+from\s+the\s+box",
        "Choose SIX answers from the box.",
    ),
    Rubric(
        MATCHING_BANK,
        r"write\s+the\s+correct\s+letter\s*,?\s*[a-j]\s*[-–]\s*[a-j]\s*,?\s*next\s+to",
        "Write the correct letter, A-H, next to Questions 25-30.",
    ),

    Rubric(
        SHORT_ANSWER,
        r"answer\s+the\s+questions?\s+below",
        "Answer the questions below.",
    ),
)


# --- independent extractors -------------------------------------------------
#
# Word limit, letter range, select count and reusability vary independently of
# the type phrasing - "ONE WORD ONLY" turns up under every completion type - so
# each gets its own extractor rather than being folded into the catalogue.

#: Ordered longest-first: "TWO WORDS AND/OR A NUMBER" must beat "TWO WORDS".
WORD_LIMIT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"one\s+word\s+and\s*/?\s*or\s+a\s+number", "one_word_number"),
    (r"(?:no\s+more\s+than\s+)?two\s+words\s+and\s*/?\s*or\s+a\s+number", "two_words_number"),
    (r"(?:no\s+more\s+than\s+)?three\s+words\s+and\s*/?\s*or\s+a\s+number", "three_words_number"),
    (r"one\s+word\s+only", "one_word"),
    (r"(?:no\s+more\s+than\s+)?\bone\s+word\b", "one_word"),
    (r"(?:no\s+more\s+than\s+)?\btwo\s+words\b", "two_words"),
    (r"(?:no\s+more\s+than\s+)?\bthree\s+words\b", "three_words"),
)

#: "A-E", "A - J", "A to H", and the en-dash OCR sometimes produces.
LETTER_RANGE = re.compile(
    r"\b([A-J])\s*(?:[-–—]|to)\s*([A-J])\b",
    re.IGNORECASE,
)

SELECT_COUNT = re.compile(
    r"\b(?:choose|select|write|which)\s+(one|two|three|four|five|six|seven|eight|\d+)\b",
    re.IGNORECASE,
)

REUSABLE = re.compile(
    r"you\s+may\s+use\s+any\s+(?:letter|answer)\s+more\s+than\s+once",
    re.IGNORECASE,
)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


#: Blocks that are pure boilerplate and should be recognised and **dropped**,
#: never parsed. The TRUE/FALSE/NOT GIVEN legend is the important one: it is
#: typeset as two columns (three labels, then three definitions), so a parser
#: that tries to read it pairs the wrong label with the wrong definition. The
#: frontend renders a canonical legend instead, which makes the mispairing
#: problem disappear rather than needing to be solved.
DROPPABLE_LEGEND = re.compile(
    r"if\s+the\s+statement\s+agrees\s+with"
    r"|if\s+it\s+is\s+impossible\s+to\s+say"
    r"|if\s+there\s+is\s+no\s+information\s+on\s+this"
    r"|if\s+the\s+statement\s+contradicts",
    re.IGNORECASE,
)

#: The standard lead-in to a reading passage; marks where passage text ends.
PASSAGE_LEAD_IN = re.compile(
    r"you\s+should\s+spend\s+about\s+\d+\s+minutes\s+on\s+questions?\s+\d+",
    re.IGNORECASE,
)

#: Answer-sheet housekeeping, which carries digits and would otherwise confuse
#: question-number scanning. Editions phrase it at least two ways - "Write your
#: answers in boxes 1-7 on your answer sheet." and "In boxes 8-13 on your answer
#: sheet, write" - so match the stable part instead of enumerating variants.
#: The phrase never occurs in passage or question content.
ANSWER_SHEET_NOTE = re.compile(r"\bon\s+your\s+answer\s+sheet\b", re.IGNORECASE)
