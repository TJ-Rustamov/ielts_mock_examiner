"""Parse Cambridge answer-key pages into structured answer keys.

Pure module: no Django imports.

This is the highest-consequence parser in the project. A mis-read key marks
every future candidate wrong and nothing downstream would ever notice, which is
why it refuses to guess: anything it cannot read cleanly is reported as missing
and unreliable rather than turned into an answer.

The grammar, taken from real key pages::

    1 mining 2 education 3 notes 4 journals 5 Venice
    8 TRUE 9 NOTGIVEN 10 FALSE 11 NOT GIVEN
    11 A 12 B 13 A
    21 &22 IN EITHER ORDER  B  D
    31 metal(s) 32 slow 33 demand
    1 10/ten 2 weather
    8 cafe I cafe                 <- OCR read the alternatives pipe as capital I
    1 (the) 13(th) (of) January/ 13.01 / 13.1

Alternatives (/, OR, |) and optional parts (metal(s), (the) equator) are
expanded here, at import time, into an explicit list of accepted answers. That
keeps ``exams.marking`` dumb and lets an admin see and correct the literal
accepted set in the review screen.

**On column interleaving.** Key pages are typeset in two or three narrow
columns. Read as a flat stream they can interleave - Cambridge 21 page 119 puts
the Part 3 letters *inside* the Part 1 answers. No amount of regex fixes that;
it needs coordinate-aware extraction upstream. What this module does is detect
the contamination and set ``reliable = False``, so the importer stops rather
than publishing a plausible-looking but wrong key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from exams.marking import LETTER, LETTER_SET, TEXT, TFNG, YNNG, AnswerKey

__all__ = [
    "KeyParseResult",
    "KeyRow",
    "expand_alternatives",
    "detect_kind",
    "parse_answer_key",
    "parse_answer_rows",
    "repair_question_number",
    "MAX_VARIANTS",
    "MAX_ANSWER_TOKENS",
]

#: Upper bound on accepted forms for one question. Expansion is round-robin
#: across the top-level alternatives, so a long bracketed date cannot crowd out
#: the numeric forms that follow it.
MAX_VARIANTS = 12

#: Real answers are short. This bounds one alternative, not the whole entry.
MAX_ANSWER_TOKENS = 6

DEFAULT_TOTAL = 40

# --- noise that is interleaved with the answers on real key pages -----------

# The "If you score ..." band sidebar is typeset in a column beside the answers,
# so it lands *inside* the answer stream. It cannot be removed sentence by
# sentence, because the same sentence also contains real answers; each sidebar
# passage is removed as a span running from a trigger phrase to a terminator.
#
# The span also stops short of the next section heading. Without that, a
# sidebar whose closing sentence OCR lost ran to the end of the text and took
# every answer after it - a whole Part 3 and 4 - with it.
_SIDEBAR_SPAN = re.compile(
    r"(?:If you score"
    r"|you (?:are|may) (?:unlikely|likely|get)\b"
    r"|we recommend that you"
    r"|\bCEFR\b)"
    r".*?"
    r"(?:take IELTS\.|scores? acceptable\.|\Z"
    r"|(?=\b(?:Part|Section|Reading\s*Passage)\s*\d+\s*,?\s*Questions?\s*\d))",
    re.IGNORECASE | re.DOTALL,
)

# Residual sidebar wording. Because the sidebar is a narrow column, OCR
# interleaves its clauses and one span match leaves fragments behind. This is
# edition-specific *data*, not logic - extend it when a new book leaks prose
# into the answers, rather than changing the parser.
_SIDEBAR_FRAGMENTS = re.compile(
    r"\b(?:"
    r"scores? acceptable"
    r"|acceptable score"
    r"|under examination"
    r"|examination conditions"
    r"|institutions will find different"
    r"|more practice or lessons"
    r"|think about having"
    r"|improving your English"
    r"|before you take IELTS"
    r"|but we recommend"
    r"|you may get an"
    r"|you are likely to get an"
    r"|conditions but"
    r"|but remember that different"
    r")\b\.?",
    re.IGNORECASE,
)

# Section headings, removed before scanning because they carry digits that would
# otherwise look like question numbers.
_HEADINGS = re.compile(
    r"(?:Listening\s*and\s*Reading\s*answer\s*keys?)"
    r"|(?:Answer\s*keys?(?:\s*with\s*extra\s*explanations)?(?:\s*in\s*Resource\s*Bank)?)"
    r"|(?:\bTEST\s*\d+(?!\d))"
    r"|(?:\b(?:Part|Section)\s*\d+\s*,?\s*Questions?\s*\d+\s*[-–]\s*\d+)"
    r"|(?:\bReading\s*Passage\s*\d+\s*,?\s*Questions?\s*\d+\s*[-–]\s*\d+)"
    r"|(?:\bQuestions?\s*\d+\s*[-–]\s*\d+)"
    r"|(?:\b(?:Part|Section)\s*\d+(?!\d))"
    r"|(?:\bReading\s*Passage\s*\d+(?!\d))"
    # Anchor with a word boundary, NOT with (?:^|\s). A leading whitespace
    # class makes the match start one character earlier than the "Reading
    # Passage N, Questions N-M" alternative above, and the engine prefers the
    # earliest start position - so it would strip only the word "Reading" and
    # leave a stray "Passage 1," whose digit then reads as question 1.
    r"|(?:\b(?:LISTENING|READING)\b(?!\s*Passage))"
    r"|(?:\bPassage\s*\d+(?!\d))"
    r"|(?:in\s*Resource\s*Bank)",
    re.IGNORECASE,
)

#: Text that proves an answer span has absorbed content from another column.
_CONTAMINATION = re.compile(
    r"IN\s+(?:EITHER|ANY)\s+ORDER|&\s*\d|\bQuestions?\s+\d",
    re.IGNORECASE,
)

#: Two or more bare option letters with no set declaration - either a set whose
#: header was lost, or letters that bled in from an adjacent column.
_BARE_LETTER_RUN = re.compile(r"^(?:[A-J]\s+)+[A-J]$", re.IGNORECASE)

_SET_DECL = re.compile(
    r"\s*(?:&\s*(\d+)\s*)+IN\s+(?:EITHER|ANY)\s+ORDER\b",
    re.IGNORECASE,
)
_SET_PARTNERS = re.compile(r"&\s*(\d+)")

_ALT_SPLIT = re.compile(r"\s*(?:/|\||\bOR\b)\s*", re.IGNORECASE)
_PAREN = re.compile(r"\(([^()]*)\)")
_SINGLE_LETTER = re.compile(r"^[A-J]$", re.IGNORECASE)
_LOOSE_LETTER = re.compile(r"(?<![\w])([A-J])(?![\w])")

_TFNG_WORDS = {"true", "false", "not given"}
_YNNG_WORDS = {"yes", "no", "not given"}


@dataclass
class KeyParseResult:
    keys: dict[int, AnswerKey] = field(default_factory=dict)
    raw: dict[int, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)
    #: False when something was detected that makes the whole section
    #: untrustworthy (column bleed, ambiguous letter runs, gaps). The importer
    #: must not publish a module whose key section is unreliable.
    reliable: bool = True
    #: Row parser only: lowest OCR confidence among the rows of each answer,
    #: and where on the page the answer was printed (for the review crop).
    confidence: dict[int, float] = field(default_factory=dict)
    crops: dict[int, dict] = field(default_factory=dict)
    #: Row parser only: numbers withheld because two rows claimed them.
    conflicts: set[int] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return self.reliable and not self.missing


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------


def _clean(text: str, total: int = DEFAULT_TOTAL) -> str:
    """Strip the band sidebar, headings and OCR artefacts from a key page."""
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace("‘", "'")

    # Headings first: they carry digits that would otherwise look like question
    # numbers, and removing them makes the bare-range pass below unambiguous.
    text = _HEADINGS.sub(" ", text)

    # Then each sidebar passage, as a span. Sentence-level filtering does not
    # work here: the sentence containing "If you score" also contains the
    # answers to questions 1-20, because the sidebar is a parallel column.
    text = _SIDEBAR_SPAN.sub(" ", text)
    text = _SIDEBAR_FRAGMENTS.sub(" ", text)

    # A bare score band left over from the sidebar ("0-19", "29-40").
    text = re.sub(r"(?<![\w-])\d{1,2}\s*-\s*\d{1,2}(?![\w-])", " ", text)

    # OCR runs these together; the \s* also covers the unspaced NOTGIVEN form.
    text = re.sub(r"\bNOT\s*GIVEN\b", "NOT GIVEN", text, flags=re.IGNORECASE)

    text = " ".join(text.split())

    # A trailing page number. Only stripped when it cannot be a question number,
    # so a legitimate numeric answer at the end of the key is never eaten.
    trailing = re.search(r"\s(\d{1,4})\s*\Z", text)
    if trailing and int(trailing.group(1)) > total:
        text = text[: trailing.start()].rstrip()

    return text


def _resolve_ocr_pipe(raw: str, letters_expected: bool) -> str:
    """Turn OCR's capital ``I`` back into the alternatives pipe.

    Type-aware on purpose: ``I`` is a legitimate answer wherever the option
    range runs to A-I (map labelling), so this applies only where the question
    group expects a text answer.
    """
    if letters_expected:
        return raw
    return re.sub(r"(?<=\s)I(?=\s)", "|", raw)


# ---------------------------------------------------------------------------
# Expansion
# ---------------------------------------------------------------------------


def _expand_parens(value: str) -> list[str]:
    """metal(s) -> [metal, metals];  (the) equator -> [the equator, equator]."""
    match = _PAREN.search(value)
    if not match:
        collapsed = " ".join(value.split())
        return [collapsed] if collapsed else []
    inner = match.group(1)
    branches = (
        value[: match.start()] + inner + value[match.end():],
        value[: match.start()] + value[match.end():],
    )
    out: list[str] = []
    for branch in branches:
        for expanded in _expand_parens(branch):
            if expanded and expanded not in out:
                out.append(expanded)
    return out


def expand_alternatives(raw: str, letters_expected: bool = False) -> tuple[str, ...]:
    """Expand one raw key string into every accepted answer.

    Splits on ``/``, ``|`` and ``OR``, expands optional bracketed parts, then
    interleaves the results **round-robin across the top-level alternatives**.
    That ordering matters: ``(the) 13(th) (of) January/ 13.01 / 13.1`` yields
    eight bracket forms for the first alternative alone, so a simple
    head-of-list cap would discard ``13.01`` and ``13.1`` entirely.
    """
    raw = _resolve_ocr_pipe(raw.strip(), letters_expected)
    if not raw:
        return ()

    groups: list[list[str]] = []
    for part in _ALT_SPLIT.split(raw):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) > MAX_ANSWER_TOKENS:
            part = " ".join(tokens[:MAX_ANSWER_TOKENS])
        expanded = _expand_parens(part)
        if expanded:
            groups.append(expanded)

    out: list[str] = []
    seen: set[str] = set()
    depth = 0
    while len(out) < MAX_VARIANTS and any(depth < len(g) for g in groups):
        for group in groups:
            if depth < len(group) and len(out) < MAX_VARIANTS:
                candidate = group[depth]
                if candidate not in seen:
                    seen.add(candidate)
                    out.append(candidate)
        depth += 1
    return tuple(out)


def detect_kind(accepted: tuple[str, ...], hint: str | None = None) -> str:
    """Infer the answer kind from its accepted values.

    `hint` is the kind the parsed question group expects; it wins whenever the
    values are consistent with it, because TRUE/FALSE/NOT GIVEN and
    YES/NO/NOT GIVEN share "NOT GIVEN" and a bare "NOT GIVEN" is otherwise
    indistinguishable between them.
    """
    if not accepted:
        return TEXT
    lowered = {" ".join(a.lower().split()) for a in accepted}

    if hint in (TFNG, YNNG) and lowered <= (_TFNG_WORDS | _YNNG_WORDS):
        return hint
    if lowered <= {"not given"}:
        return hint if hint in (TFNG, YNNG) else TFNG
    if lowered <= _TFNG_WORDS:
        return TFNG
    if lowered <= _YNNG_WORDS:
        return YNNG
    if all(_SINGLE_LETTER.match(a) for a in accepted):
        return LETTER
    return TEXT


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _find_number(text: str, start: int, number: int) -> re.Match | None:
    """Locate `number` as a standalone token at or after `start`."""
    return re.compile(r"(?<![\w.&-])" + str(number) + r"(?![\w.-])").search(text, start)


def _finish_slot(
    result: KeyParseResult,
    num: int,
    partners: list[int],
    raw: str,
    expected_kinds: dict[int, str],
    total: int,
) -> bool:
    """Turn one question's raw key text into an AnswerKey, or refuse it.

    Shared by the flat scanner and the row parser, so both apply exactly the
    same refusals. Returns True when a key was stored.
    """
    members = [num, *partners]
    label = "Q" + "&".join(str(m) for m in members)

    if not raw:
        result.warnings.append(f"{label}: no answer text found")
        result.missing.extend(members)
        result.reliable = False
        return False

    # Content from a neighbouring column has bled into this answer. Refuse
    # it: a missing key is recoverable in review, a wrong one is not.
    if _CONTAMINATION.search(raw):
        result.warnings.append(
            f"{label}: answer contains text from another column ({raw[:60]!r}). "
            "This key page needs column-aware extraction."
        )
        result.missing.extend(members)
        result.reliable = False
        return False

    if partners:
        letters = [m.group(1).upper() for m in _LOOSE_LETTER.finditer(raw)]
        unique = list(dict.fromkeys(letters))
        if len(unique) != len(members):
            result.warnings.append(
                f"{label}: found {len(unique)} letters for {len(members)} "
                f"questions ({raw[:60]!r})"
            )
            result.missing.extend(members)
            result.reliable = False
            return False
        key = AnswerKey(
            kind=LETTER_SET,
            accepted=tuple(unique),
            set_id=f"set-{num}",
            set_numbers=tuple(members),
            select_count=len(members),
        )
        for member in members:
            result.keys[member] = key
            result.raw[member] = raw
        return True

    # A run of bare letters with no set declaration is ambiguous: either a
    # set whose header was lost, or letters bled in from an adjacent column.
    if _BARE_LETTER_RUN.match(raw):
        result.warnings.append(
            f"{label}: {raw!r} is several option letters with no "
            "'IN EITHER ORDER' header - ambiguous, needs checking."
        )
        result.missing.append(num)
        result.reliable = False
        return False

    # A page number can end up glued to the last answer of a column
    # ("wellbeing 118"). Strip a trailing bare integer that is too large to
    # be a question number, but say so: an answer legitimately ending in a
    # number ("Room 101") would be damaged by this, and the admin should see
    # which ones were touched.
    tokens = raw.split()
    if len(tokens) > 1 and tokens[-1].isdigit() and int(tokens[-1]) > total:
        result.warnings.append(
            f"{label}: dropped a trailing {tokens[-1]!r} that looks like a "
            f"page number (was {raw!r}) - check this one"
        )
        raw = " ".join(tokens[:-1])

    hint = expected_kinds.get(num)
    accepted = expand_alternatives(
        raw, letters_expected=hint in (LETTER, LETTER_SET)
    )
    if not accepted:
        result.warnings.append(f"{label}: empty after expansion ({raw!r})")
        result.missing.append(num)
        result.reliable = False
        return False

    kind = detect_kind(accepted, hint)
    if hint and kind != hint and not (hint in (TFNG, YNNG) and kind in (TFNG, YNNG)):
        result.warnings.append(
            f"{label}: key looks like {kind} but the question group "
            f"expects {hint} ({raw!r})"
        )
    result.keys[num] = AnswerKey(kind=kind, accepted=accepted)
    result.raw[num] = raw
    return True


def parse_answer_key(
    text: str,
    total: int = DEFAULT_TOTAL,
    expected_kinds: dict[int, str] | None = None,
) -> KeyParseResult:
    """Parse an answer-key section into ``{question_number: AnswerKey}``.

    Question numbers are located **sequentially** - the scanner looks for 1, then
    2, then 3. This matters: ``1 10/ten 2 weather`` must give Q1 = "10/ten", and a
    scanner that grabbed any integer would read the answer's own "10" as a
    question number.
    """
    expected_kinds = expected_kinds or {}
    result = KeyParseResult()
    cleaned = _clean(text, total)
    if not cleaned:
        result.warnings.append("answer key section is empty after cleaning")
        result.missing = list(range(1, total + 1))
        result.reliable = False
        return result

    # Locate every question number first, so each answer's extent is bounded by
    # the start of the next one.
    slots: list[tuple[int, int, list[int]]] = []  # (number, value_start, partners)
    cursor = 0
    number = 1
    while number <= total:
        match = _find_number(cleaned, cursor, number)
        if match is None:
            result.missing.append(number)
            number += 1
            continue
        partners: list[int] = []
        value_start = match.end()
        set_match = _SET_DECL.match(cleaned, match.end())
        if set_match:
            partners = [int(p) for p in _SET_PARTNERS.findall(set_match.group(0))]
            value_start = set_match.end()
        slots.append((number, value_start, partners))
        cursor = value_start
        number = (max(partners) if partners else number) + 1

    for index, (num, value_start, partners) in enumerate(slots):
        end = len(cleaned)
        if index + 1 < len(slots):
            next_match = _find_number(cleaned, value_start, slots[index + 1][0])
            end = next_match.start() if next_match else len(cleaned)
        raw = " ".join(cleaned[value_start:end].strip(" .,;:").split())
        _finish_slot(result, num, partners, raw, expected_kinds, total)

    result.missing = sorted(set(result.missing) - set(result.keys))
    if result.missing:
        result.reliable = False
    return result


# ---------------------------------------------------------------------------
# Row parsing - for keys read column by column from an image
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeyRow:
    """One printed line of a key page, as OCR delivered it.

    Plain data so this module stays free of layout and Django imports. `bbox`
    is in page points; `column` is the strip the row was read from.
    """

    text: str
    confidence: float = 1.0
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    column: int = 0


#: Shapes OCR substitutes for digits. Applied to the question-number token at
#: the start of a row and *nowhere else* - an answer is never "repaired".
_DIGIT_CONFUSIONS = str.maketrans({
    "O": "0", "o": "0", "D": "0",
    "l": "1", "I": "1", "i": "1", "|": "1",
    "S": "5", "B": "8", "Z": "2",
})
_CONFUSABLE = "".join(sorted(set("OoDlIi|SBZ")))

#: A row's leading question number: one or two digits (or digit look-alikes),
#: optionally followed by "." or ")", and then a space, "&" or the end. The
#: lookahead keeps "13.01" and "13th" from reading as question 13.
_ROW_NUMBER = re.compile(
    r"^\s*([0-9" + re.escape(_CONFUSABLE) + r"]{1,2})(?:[.)](?=\s|$))?(?=\s|&|$)\s*(.*)$"
)

#: "IN EITHER ORDER" as OCR actually delivers it: spaces dropped
#: ("INEITHERORDER"), the I lost or merged into the partner number
#: ("21&2NEITHER ORDER"), an l or 1 for the I in EITHER.
_EITHER_ORDER = re.compile(
    r"(?:I?N\s*)?E[Il1]?THER\s*ORDER|\bANY\s*ORDER", re.IGNORECASE
)
#: The set declaration at the start of a row's remainder: "&22", "& 22 & 23",
#: "&2NEITHER ORDER", "-27 IN EITHER ORDER".
_ROW_SET_AMP = re.compile(r"^((?:\s*&\s*\d{0,2})+)", re.IGNORECASE)
_ROW_SET_DASH = re.compile(r"^\s*-\s*(\d{1,2})\b", re.IGNORECASE)

#: Evidence that an answer absorbed another row or column, tolerant of the
#: dropped spaces OCR produces.
_ROW_CONTAMINATION = re.compile(
    r"(?:I?N\s*)?E[Il1]THER\s*ORDER|\bANY\s*ORDER|&\s*\d|questions?\s*\d",
    re.IGNORECASE,
)

#: A row made only of key-page headings, compared with every space and
#: punctuation mark removed - OCR routinely reads "Part 2, Questions 11-20" as
#: "Part2,Questions11-20", and the column cut can leave half a heading.
_COMPACT_HEADING = re.compile(
    r"^(?:listening|reading|and|answer|keys?|with|extra|explanations?|in|resource|bank"
    r"|test\d{1,2}|part\d{1,2}|section\d{1,2}|passage\d{1,2}"
    r"|questions?\d{1,2}\d{1,2})+$"
)

#: The band-score sidebar, compared compact for the same reason.
_COMPACT_SIDEBAR = re.compile(
    r"ifyouscore|youare(?:un)?likely|youmayget|examinationconditions|acceptablescore"
    r"|werecommend|takeielts|institutionswill|morepractice|improvingyourenglish"
)


#: A bare one- or two-digit number inside an answer ("10/ten" and "13th" are
#: not bare).
_STANDALONE_NUMBER = re.compile(r"(?<![\w./&-])(\d{1,2})(?![\w./-])")


def repair_question_number(token: str, total: int = DEFAULT_TOTAL) -> tuple[int | None, bool]:
    """Read a row-leading token as a question number.

    Returns (number or None, whether it contained at least one real digit).
    ``l1`` -> 11, ``2O`` -> 20, ``I7`` -> 17. A token made only of look-alikes
    (``B``, ``ll``) is returned too, flagged ``False``, so the caller can
    accept it only where that exact number is the one expected next - a row
    reading "B" on its own is far more likely to be the letter B.
    """
    if not token:
        return None, False
    has_digit = any(ch.isdigit() for ch in token)
    repaired = token.translate(_DIGIT_CONFUSIONS)
    if not repaired.isdigit():
        return None, has_digit
    number = int(repaired)
    if not 1 <= number <= total:
        return None, has_digit
    return number, has_digit


def _clean_row_text(text: str) -> str:
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace("‘", "'")
    return " ".join(text.split())


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _is_heading_row(text: str) -> bool:
    """A row that is nothing but section headings ("Part 2, Questions 11-20")."""
    compact = _compact(text)
    if compact and _COMPACT_HEADING.match(compact):
        return True
    remainder = _HEADINGS.sub(" ", text)
    return bool(text.strip()) and not remainder.strip(" ,.:;-|")


def _is_sidebar_row(text: str) -> bool:
    return bool(
        _SIDEBAR_SPAN.search(text)
        or _SIDEBAR_FRAGMENTS.search(text)
        or _COMPACT_SIDEBAR.search(_compact(text))
    )


def _strip_set_phrase(text: str) -> tuple[str, bool]:
    """Remove a leading "IN EITHER ORDER" (in any OCR spelling)."""
    match = _EITHER_ORDER.search(text)
    # Whatever precedes the phrase may only be the tail of the set
    # declaration: "&", digits, or one of the shapes OCR makes of a digit
    # ("21&22 IN" has come back as "21&2DNEITHER").
    if match and len(text[: match.start()].strip(" &-0123456789")) <= 1 \
            and not text[: match.start()].strip(" &-0123456789" + _CONFUSABLE):
        return text[match.end():].strip(), True
    return text, False


def _clean_slot(raw: str) -> str:
    """Remove sidebar wording and headings that wrapped into an answer."""
    raw = _HEADINGS.sub(" ", raw)
    raw = _SIDEBAR_SPAN.sub(" ", raw)
    raw = _SIDEBAR_FRAGMENTS.sub(" ", raw)
    raw = re.sub(r"\bNOT\s*GIVEN\b", "NOT GIVEN", raw, flags=re.IGNORECASE)
    return " ".join(raw.split()).strip(" .,;:")


def _union(boxes: list[tuple[float, float, float, float]]) -> list[float]:
    return [
        round(min(b[0] for b in boxes), 2), round(min(b[1] for b in boxes), 2),
        round(max(b[2] for b in boxes), 2), round(max(b[3] for b in boxes), 2),
    ]


@dataclass
class _Slot:
    number: int
    partners: list[int]
    parts: list[str]
    rows: list[KeyRow]


def parse_answer_rows(
    rows: list[KeyRow],
    total: int = DEFAULT_TOTAL,
    expected_kinds: dict[int, str] | None = None,
) -> KeyParseResult:
    """Parse key rows - one printed line each - into answer keys.

    Unlike :func:`parse_answer_key`, which scans one flattened string for 1, 2,
    3..., this works row by row, because on a column-cropped image every answer
    begins its own line with its own number:

        1   (the) 13(th) (of) January/
            13.01 / 13.1                <- continuation: no number, indented
        2   48 / forty-eight

    That makes it **order-independent** - rows can arrive column by column or
    interleaved and each still carries its own number - which is exactly what
    defeats the flat scanner on interleaved pages.

    Safety rules, all in favour of a missing key over a wrong one:

    * the number is repaired from OCR look-alikes only in the row-leading
      token, and a token with no real digit counts only if it is exactly the
      number expected next;
    * where geometry is known, a number counts only at the column's number
      margin - a continuation line that happens to start with digits sits at
      the answer indent instead;
    * a number seen twice is withheld, with both readings reported;
    * heading and band-score sidebar rows end the current answer, so prose
      cannot drift into it.
    """
    expected_kinds = expected_kinds or {}
    result = KeyParseResult()

    # --- pass 1: what each row looks like ---------------------------------
    parsed: list[tuple[KeyRow, str, int | None, bool, str]] = []
    for row in rows:
        text = _clean_row_text(row.text)
        if not text:
            continue
        number, real_digit, rest = None, False, text
        match = _ROW_NUMBER.match(text)
        if match:
            number, real_digit = repair_question_number(match.group(1), total)
            if number is not None:
                rest = match.group(2)
        parsed.append((row, text, number, real_digit, rest))

    # --- the number margin of each column ---------------------------------
    margins: dict[int, float] = {}
    heights: dict[int, float] = {}
    by_column: dict[int, list[KeyRow]] = {}
    for row, _text, number, real_digit, _rest in parsed:
        if number is not None and real_digit and row.bbox:
            by_column.setdefault(row.column, []).append(row)
    for column, column_rows in by_column.items():
        lefts = sorted(r.bbox[0] for r in column_rows)
        margins[column] = lefts[len(lefts) // 5]
        row_heights = sorted(r.bbox[3] - r.bbox[1] for r in column_rows)
        heights[column] = max(row_heights[len(row_heights) // 2], 1.0)

    def at_margin(row: KeyRow) -> bool:
        if not row.bbox or row.column not in margins:
            return True
        return row.bbox[0] <= margins[row.column] + 1.5 * heights[row.column]

    # --- pass 2: build slots ----------------------------------------------
    slots: dict[int, _Slot] = {}
    duplicates: dict[int, list[str]] = {}
    current: _Slot | None = None
    last_number = 0
    dropped = 0

    def close_enough(row: KeyRow) -> bool:
        """A continuation must sit right under the answer it continues."""
        if current is None or not row.bbox or not current.rows[-1].bbox:
            return current is not None
        previous = current.rows[-1]
        if previous.column != row.column or previous.page != row.page:
            return False
        height = max(previous.bbox[3] - previous.bbox[1], 1.0)
        return row.bbox[1] - previous.bbox[3] <= 1.2 * height

    for row, text, number, real_digit, rest in parsed:
        if _is_heading_row(text) or _is_sidebar_row(text):
            current = None
            continue

        accept = False
        if number is not None and at_margin(row):
            if real_digit:
                accept = True
            elif number == last_number + 1 and rest.strip():
                accept = True

        if accept:
            if number in slots or any(number in s.partners for s in slots.values()):
                duplicates.setdefault(number, []).append(rest)
                current = None
                continue
            partners: list[int] = []
            amp = _ROW_SET_AMP.match(rest)
            dash = _ROW_SET_DASH.match(rest)
            if amp:
                # Sets are always consecutive ("21&22", "25&26&27"), so the
                # partners follow from how many "&" there are. The digits
                # after each "&" are the part OCR mangles - "21&22 IN" comes
                # back as "21&2NEITHER" - so they are not trusted for this.
                count = amp.group(1).count("&")
                partners = list(range(number + 1, min(number + count, total) + 1))
                rest = rest[amp.end():]
            elif dash:
                after, has_phrase = _strip_set_phrase(rest[dash.end():])
                last = int(dash.group(1))
                if has_phrase and number < last <= min(number + 4, total):
                    partners = list(range(number + 1, last + 1))
                    rest = after
            if partners:
                rest, _ = _strip_set_phrase(rest)
            current = _Slot(number, partners, [rest] if rest.strip() else [], [row])
            slots[number] = current
            last_number = max([number, *partners])
            continue

        if current is not None and close_enough(row):
            # "IN EITHER ORDER" can wrap onto the line under "21&22".
            if current.partners and not current.parts:
                text, _ = _strip_set_phrase(text)
            if text.strip():
                current.parts.append(text)
            current.rows.append(row)
            continue
        if number is not None and real_digit:
            # Looked like an answer row but sat off the number margin, or came
            # with nothing to attach to.
            dropped += 1

    # --- pass 3: each slot through the shared refusals ---------------------
    for number in sorted(slots):
        slot = slots[number]
        raw = _clean_slot(" ".join(slot.parts))
        members = [number, *slot.partners]
        if _ROW_CONTAMINATION.search(raw):
            result.warnings.append(
                f"Q{'&'.join(str(m) for m in members)}: answer contains text from "
                f"another row or column ({raw[:60]!r}) - withheld"
            )
            result.missing.extend(members)
            result.reliable = False
            continue
        claimed = {n for s in slots.values() for n in (s.number, *s.partners)}
        stray = [
            int(m.group(1)) for m in _STANDALONE_NUMBER.finditer(raw)
            if 1 <= int(m.group(1)) <= total and int(m.group(1)) not in claimed
        ]
        if stray:
            # "1 10/ten 21 B": two rows welded together, and Q21 never got a
            # row of its own. A number that is also another question's own
            # row ("2 weeks" while Q2 exists) is just part of the answer.
            result.warnings.append(
                f"Q{number}: answer contains question number {stray[0]}, which has "
                f"no row of its own - two rows merged? ({raw[:60]!r}) - withheld"
            )
            result.missing.extend(members)
            result.reliable = False
            continue
        if number in duplicates:
            result.warnings.append(
                f"Q{number}: read twice ({raw!r} and {duplicates[number][0]!r}) - "
                "withheld"
            )
            result.missing.extend(members)
            result.conflicts.update(members)
            result.reliable = False
            continue
        if not _finish_slot(result, number, slot.partners, raw, expected_kinds, total):
            continue
        confidence = min((r.confidence for r in slot.rows), default=1.0)
        first = slot.rows[0]
        boxes = [r.bbox for r in slot.rows if r.bbox and r.page == first.page]
        for member in members:
            result.confidence[member] = round(float(confidence), 4)
            if boxes:
                result.crops[member] = {"page": first.page, "bbox": _union(boxes)}
        if len(slot.rows) > 1 and number + 1 <= total and number + 1 not in slots \
                and not slot.partners:
            # The next number never turned up and this answer ran onto a
            # second line: possibly that number was lost and its answer merged
            # in here. Not refused - wrapped answers are real - but said.
            result.warnings.append(
                f"Q{number}: answer runs over {len(slot.rows)} lines and "
                f"Q{number + 1} is missing - they may have merged ({raw!r})"
            )

    if dropped:
        result.warnings.append(
            f"{dropped} numbered row(s) could not be placed - check the crop"
        )

    seen = set(result.keys)
    for number in range(1, total + 1):
        if number not in seen and number not in result.missing:
            result.missing.append(number)
    result.missing = sorted(set(result.missing) - set(result.keys))
    if result.missing:
        result.reliable = False
    return result
