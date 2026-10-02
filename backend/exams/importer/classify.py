"""Instruction line -> question type, word limit, letter range, select count.

Two-stage matching. First the catalogue regexes, which handle clean text. If
none hit, a fuzzy pass against the canonical phrasings catches lines OCR has
mangled ("Cornplete the notes below", "Choose the correct Ietter"). Anything
still unmatched becomes ``unknown`` and is flagged for the admin — never
guessed at.

Every unmatched instruction is recorded by :func:`misses`, and that log is how
a new book gets supported: read the misses, add phrasings to
``boilerplate.CATALOGUE``. No parser code should change.

rapidfuzz is used when available and ``difflib`` otherwise, so this module works
on a bare dev machine as well as inside the built image.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from exams.importer import boilerplate as bp

__all__ = ["Classification", "classify", "normalise_instruction", "extract_word_limit"]

#: Below this similarity a fuzzy match is not trusted and the group is flagged.
FUZZY_THRESHOLD = 88.0


def _fuzzy_score(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz
    except ImportError:  # pragma: no cover - depends on installed extras
        from difflib import SequenceMatcher

        return SequenceMatcher(None, a, b).ratio() * 100
    return float(fuzz.token_set_ratio(a, b))


@dataclass
class Classification:
    type: str = bp.UNKNOWN
    word_limit: str = ""
    allow_number: bool = False
    letter_range: tuple[str, str] | None = None
    select_count: int | None = None
    options_reusable: bool = False
    confidence: float = 0.0
    matched: str = ""
    needs_review: bool = True
    instruction: str = ""

    @property
    def expects_letters(self) -> bool:
        return self.type in bp.LETTER_ANSWER_TYPES

    @property
    def needs_figure(self) -> bool:
        return self.type in bp.FIGURE_TYPES


def normalise_instruction(text: str) -> str:
    """Flatten an instruction block to one comparable string.

    The rubric never arrives as a single span. PDF extraction hands it over in
    pieces — ``Write`` / ``ONE WORD ONLY`` / ``for each answer.`` — so matching
    has to happen on the joined, whitespace-normalised form or every pattern
    misses.
    """
    if not text:
        return ""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


#: Systematic OCR letter confusions, applied only to a throwaway copy used for
#: matching. These are shape collisions, not spelling guesses: a capital I reads
#: as a lowercase l, and the ligature-ish "rn" reads as "m".
_CONFUSIONS = (
    (re.compile(r"(?<=[a-z])I(?=[a-z])"), "l"),      # tabIe   -> table
    (re.compile(r"\bI(?=[a-z]{2,})"), "l"),          # Ietter  -> letter
    (re.compile(r"(?<=[a-z])0(?=[a-z])"), "o"),      # b0x     -> box
    (re.compile(r"(?<=[a-z])1(?=[a-z])"), "l"),      # comp1ete-> complete
    (re.compile(r"rn"), "m"),                        # Cornplete -> Complete
)


def deconfuse(text: str) -> str:
    """Undo systematic OCR letter confusions, for matching purposes only.

    Never applied to text that gets stored or shown — `rn -> m` would turn
    "learn" into "leam". It exists so a rubric the catalogue would otherwise
    miss gets a second, deterministic chance before falling back to fuzzy
    similarity, which is both weaker and harder to reason about.
    """
    for pattern, replacement in _CONFUSIONS:
        text = pattern.sub(replacement, text)
    return text


def extract_word_limit(text: str) -> tuple[str, bool]:
    """Return (word_limit key, whether a number may be added on top)."""
    normalised = normalise_instruction(text)
    for pattern, key in bp.WORD_LIMIT_PATTERNS:
        if re.search(pattern, normalised):
            return key, key.endswith("_number")
    return "", False


def _extract_select_count(normalised: str) -> int | None:
    match = bp.SELECT_COUNT.search(normalised)
    if not match:
        return None
    token = match.group(1).lower()
    if token.isdigit():
        return int(token)
    return bp.NUMBER_WORDS.get(token)


def _extract_letter_range(text: str) -> tuple[str, str] | None:
    match = bp.LETTER_RANGE.search(text)
    if not match:
        return None
    start, end = match.group(1).upper(), match.group(2).upper()
    if start >= end:
        return None
    return start, end


def classify(instruction: str) -> Classification:
    """Classify one question group's instruction block."""
    normalised = normalise_instruction(instruction)
    result = Classification(instruction=instruction.strip())
    if not normalised:
        return result

    result.word_limit, result.allow_number = extract_word_limit(normalised)
    result.letter_range = _extract_letter_range(instruction)
    result.options_reusable = bool(bp.REUSABLE.search(normalised))

    # Pass 1: the catalogue regexes on the text as extracted.
    # Pass 2: the same regexes after undoing systematic OCR letter confusions.
    #         Deterministic, so a hit here is as trustworthy as pass 1 — but it
    #         is flagged, because a garbled rubric means garbled content nearby.
    repaired = deconfuse(normalise_instruction(deconfuse(instruction)))
    matched_rubric = None
    for attempt, candidate in enumerate((normalised, repaired)):
        if attempt and candidate == normalised:
            break
        for rubric in bp.CATALOGUE:
            if re.search(rubric.pattern, candidate, re.IGNORECASE):
                matched_rubric = rubric
                result.type = rubric.type
                result.matched = rubric.canonical
                result.confidence = 100.0 if attempt == 0 else 95.0
                result.needs_review = attempt > 0
                break
        if matched_rubric is not None:
            # Re-run the independent extractors on the repaired text, since the
            # same confusions can damage "ONE WORD ONLY" and the letter range.
            if attempt > 0:
                if not result.word_limit:
                    result.word_limit, result.allow_number = extract_word_limit(candidate)
                if result.letter_range is None:
                    result.letter_range = _extract_letter_range(deconfuse(instruction))
            break

    if matched_rubric is None:
        best_score, best = 0.0, None
        for rubric in bp.CATALOGUE:
            score = _fuzzy_score(normalised, rubric.canonical.lower())
            if score > best_score:
                best_score, best = score, rubric
        if best is not None and best_score >= FUZZY_THRESHOLD:
            result.type = best.type
            result.matched = best.canonical
            result.confidence = best_score
            # A fuzzy hit is good enough to render, but the admin should still
            # glance at it, because it means the rubric was garbled.
            result.needs_review = True
        else:
            result.confidence = best_score
            return result

    if result.type == bp.MCQ_MULTI:
        result.select_count = _extract_select_count(normalised) or 2
    elif result.type == bp.MATCHING_BANK:
        result.select_count = _extract_select_count(normalised)

    # A single-answer MCQ that declares a letter range is still single-answer;
    # only the multi forms carry a count.
    if result.type == bp.MCQ_SINGLE:
        result.select_count = 1

    return result


def looks_like_rubric(text: str) -> bool:
    """True when a line carries rubric content rather than question content.

    Used to find where the instruction block ends. Cambridge rubrics are one or
    two sentences — the task ("Complete the notes below.") and the answer format
    ("Write ONE WORD ONLY for each answer.") — and the content starts on the
    next line. Without this terminator the instruction swallows the whole group
    body, which then vanishes from the rendered layout.
    """
    normalised = normalise_instruction(text)
    if not normalised:
        return False
    for candidate in (normalised, deconfuse(normalised)):
        for rubric in bp.CATALOGUE:
            if re.search(rubric.pattern, candidate, re.IGNORECASE):
                return True
        for pattern, _key in bp.WORD_LIMIT_PATTERNS:
            if re.search(pattern, candidate):
                return True
    return False


def misses(instructions: list[str]) -> list[tuple[str, float]]:
    """Instructions the catalogue could not place, with their best fuzzy score.

    Feed this from a real import run; it is the input to extending
    ``boilerplate.CATALOGUE`` for a new book.
    """
    out: list[tuple[str, float]] = []
    for instruction in instructions:
        result = classify(instruction)
        if result.type == bp.UNKNOWN:
            out.append((normalise_instruction(instruction), result.confidence))
    return out
