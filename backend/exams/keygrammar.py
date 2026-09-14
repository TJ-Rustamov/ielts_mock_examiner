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
    "expand_alternatives",
    "detect_kind",
    "parse_answer_key",
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
_SIDEBAR_SPAN = re.compile(
    r"(?:If you score"
    r"|you (?:are|may) (?:unlikely|likely|get)\b"
    r"|we recommend that you"
    r"|\bCEFR\b)"
    r".*?"
    r"(?:take IELTS\.|scores? acceptable\.|\Z)",
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
    r"(?:Listening and Reading answer keys?)"
    r"|(?:Answer key(?:s)?(?: with extra explanations)?(?: in Resource Bank)?)"
    r"|(?:\bTEST\s+\d+\b)"
    r"|(?:\b(?:Part|Section)\s+\d+\s*,?\s*Questions?\s+\d+\s*[-–]\s*\d+)"
    r"|(?:\bReading Passage\s+\d+\s*,?\s*Questions?\s+\d+\s*[-–]\s*\d+)"
    r"|(?:\bQuestions?\s+\d+\s*[-–]\s*\d+)"
    r"|(?:\b(?:Part|Section)\s+\d+\b)"
    r"|(?:\bReading Passage\s+\d+\b)"
    # Anchor with a word boundary, NOT with (?:^|\s). A leading whitespace
    # class makes the match start one character earlier than the "Reading
    # Passage N, Questions N-M" alternative above, and the engine prefers the
    # earliest start position - so it would strip only the word "Reading" and
    # leave a stray "Passage 1," whose digit then reads as question 1.
    r"|(?:\b(?:LISTENING|READING)\b(?!\s+Passage))"
    r"|(?:\bPassage\s+\d+\b)"
    r"|(?:in Resource Bank)",
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
        members = [num, *partners]
        label = "Q" + "&".join(str(m) for m in members)

        if not raw:
            result.warnings.append(f"{label}: no answer text found")
            result.missing.extend(members)
            result.reliable = False
            continue

        # Content from a neighbouring column has bled into this answer. Refuse
        # it: a missing key is recoverable in review, a wrong one is not.
        if _CONTAMINATION.search(raw):
            result.warnings.append(
                f"{label}: answer contains text from another column ({raw[:60]!r}). "
                "This key page needs column-aware extraction."
            )
            result.missing.extend(members)
            result.reliable = False
            continue

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
                continue
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
            continue

        # A run of bare letters with no set declaration is ambiguous: either a
        # set whose header was lost, or letters bled in from an adjacent column.
        if _BARE_LETTER_RUN.match(raw):
            result.warnings.append(
                f"{label}: {raw!r} is several option letters with no "
                "'IN EITHER ORDER' header - ambiguous, needs checking."
            )
            result.missing.append(num)
            result.reliable = False
            continue

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
            continue

        kind = detect_kind(accepted, hint)
        if hint and kind != hint and not (hint in (TFNG, YNNG) and kind in (TFNG, YNNG)):
            result.warnings.append(
                f"{label}: key looks like {kind} but the question group "
                f"expects {hint} ({raw!r})"
            )
        result.keys[num] = AnswerKey(kind=kind, accepted=accepted)
        result.raw[num] = raw

    result.missing = sorted(set(result.missing) - set(result.keys))
    if result.missing:
        result.reliable = False
    return result
