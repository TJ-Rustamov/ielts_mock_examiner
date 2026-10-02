"""Self-checks for an answer key: catch a misread key without reading it.

Pure module: no Django imports. It takes plain dicts - the JSON form of an
answer key, as stored in ``AnswerKeySheet.answers`` and in the import payload -
and returns a report per question.

Why this exists. A human checking 40 answers against the book is the last line
of defence, but someone who will sit the test cannot do it without spoiling
it. So every answer is checked against things that do not require knowing the
answer:

* does it fit the question at all - a letter the options actually offer, a
  TRUE/FALSE value for a TRUE/FALSE group, the number of letters the set needs;
* does it fit the rubric's word limit - an answer two words over "ONE WORD
  ONLY" is a misread or another row bleeding in;
* is it printed in the source - Reading completion answers are words taken from
  the passage, and Listening answers are words the speakers say, which the book
  prints in its audioscripts. An OCR'd answer that is not in the passage, but
  is one OCR shape-confusion away from a word that is ("rnachine"/"machine"),
  gets the passage spelling proposed - still flagged, because the passage text
  may be the misread side; one that is nowhere near is flagged with the nearest
  passage phrase as a suggestion;
* did two independent readings of the key page agree, and how sure was OCR.

Each answer ends up ``trusted``, ``check`` or ``missing``. Only the ``check``
and ``missing`` ones need a person - and the blind review screen shows those
one at a time, so nobody has to see the other 37.

There is no fuzzy matching on the *marking* path, and this module does not
change that: a correction here edits the key at import time, in the open,
where the admin can see it; it never loosens how candidates are marked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from exams.importer import boilerplate as bp
from exams.marking import (
    LETTER,
    LETTER_SET,
    TEXT,
    TFNG,
    WORD_LIMITS,
    YNNG,
    canonical,
    count_words,
    effective_word_limit,
    normalize,
)

__all__ = [
    "TRUSTED", "CHECK", "MISSING", "CONFIRMED",
    "PASS", "WARN", "FAIL",
    "GroupInfo", "Check", "CellReport",
    "groups_from_payload", "lexicons_from_payload",
    "check_answer", "check_module", "summarise",
    "shape_key",
]

TRUSTED = "trusted"
CHECK = "check"
MISSING = "missing"
#: Set by a person, not by this module: an answer they looked at and accepted.
CONFIRMED = "confirmed"

PASS = "pass"
WARN = "warn"
FAIL = "fail"

#: Below this, an OCR'd text answer is not trusted on its own merits.
TEXT_CONFIDENCE = 0.85
#: A single letter has no passage to be checked against, so without a second
#: reading to agree with it needs recognition to have been near-certain.
LETTER_CONFIDENCE = 0.95
#: rapidfuzz ratio above which a passage phrase is considered as a correction.
CORRECTION_SCORE = 85.0

_TFNG_VALUES = {"true", "false", "not given"}
_YNNG_VALUES = {"yes", "no", "not given"}
_ROMAN = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
          "xi", "xii", "xiii", "xiv", "xv")

#: Group types whose answers are words from the passage or recording.
_SOURCE_TYPES = frozenset({
    bp.NOTE_COMPLETION, bp.TABLE_COMPLETION, bp.FORM_COMPLETION,
    bp.FLOWCHART_COMPLETION, bp.SUMMARY_COMPLETION, bp.SENTENCE_COMPLETION,
    bp.SHORT_ANSWER, bp.DIAGRAM_LABELLING,
})

#: Letter-answer group types where the answer is one of several letters per
#: question rather than a set.
_SET_TYPES = frozenset({bp.MCQ_MULTI})


@dataclass
class GroupInfo:
    """What the checks need to know about the group a question belongs to."""

    type: str
    first: int
    last: int
    options: list[str] = field(default_factory=list)
    letter_range: tuple[str, str] | None = None
    word_limit: str = ""
    select_count: int | None = None
    section: int = 0

    def owns(self, number: int) -> bool:
        return self.first <= number <= self.last


@dataclass
class Check:
    name: str
    result: str
    note: str = ""
    #: A pass that is evidence rather than proof - for instance an answer found
    #: only inside run-together OCR text. It needs a second reading to agree.
    weak: bool = False

    def to_json(self) -> dict:
        return {"name": self.name, "result": self.result, "note": self.note}


@dataclass
class CellReport:
    number: int
    status: str
    checks: list[Check] = field(default_factory=list)
    #: {"from": [...], "to": [...], "explained": bool} when the passage or
    #: audioscript suggests a different spelling.
    correction: dict | None = None

    def result_of(self, name: str) -> str | None:
        for check in self.checks:
            if check.name == name:
                return check.result
        return None

    def to_json(self) -> dict:
        data = {
            "status": self.status,
            "checks": [check.to_json() for check in self.checks],
        }
        if self.correction:
            data["correction"] = self.correction
        return data


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def _letters(options) -> list[str]:
    out = []
    for option in options or []:
        letter = option.get("letter") if isinstance(option, dict) else option
        if letter:
            out.append(str(letter))
    return out


def groups_from_payload(module_payload: dict) -> list[GroupInfo]:
    """GroupInfo for every group in an import payload module."""
    groups: list[GroupInfo] = []
    for section in module_payload.get("sections") or []:
        for group in section.get("groups") or []:
            letter_range = group.get("letter_range")
            groups.append(GroupInfo(
                type=group.get("type") or bp.UNKNOWN,
                first=int(group.get("first_question") or 0),
                last=int(group.get("last_question") or 0),
                options=_letters(group.get("options")),
                letter_range=tuple(letter_range) if letter_range else None,
                word_limit=group.get("word_limit") or "",
                select_count=group.get("select_count"),
                section=int(section.get("order") or 0),
            ))
    return groups


def lexicons_from_payload(module_payload: dict) -> dict[int, str]:
    """Section order -> the text its answers should be found in."""
    out: dict[int, str] = {}
    for section in module_payload.get("sections") or []:
        text = section.get("passage_text") or section.get("transcript_text") or ""
        if text:
            out[int(section.get("order") or 0)] = text
    return out


def _group_for(groups: list[GroupInfo], number: int) -> GroupInfo | None:
    for group in groups:
        if group.owns(number):
            return group
    return None


# ---------------------------------------------------------------------------
# OCR shape confusions
# ---------------------------------------------------------------------------

#: Glyph shapes OCR swaps for one another. Applied to *both* strings being
#: compared, so a correction counts as explained only when every difference
#: between the OCR'd answer and the passage word is one of these. Case matters
#: before folding: a capital I and a lowercase l are the classic pair.
_SHAPES_BEFORE_FOLD = str.maketrans({"I": "l", "|": "l", "1": "l", "0": "o", "O": "o"})
_SHAPES_AFTER_FOLD = (
    ("rn", "m"),
    ("cl", "d"),
    ("vv", "w"),
    ("ii", "u"),
)


def shape_key(text: str) -> str:
    """A form of `text` in which OCR's systematic confusions collide."""
    folded = str(text).translate(_SHAPES_BEFORE_FOLD).casefold()
    for source, target in _SHAPES_AFTER_FOLD:
        folded = folded.replace(source, target)
    return " ".join(folded.split())


# ---------------------------------------------------------------------------
# Lexicon search
# ---------------------------------------------------------------------------


_WORD = re.compile(r"[\w'’-]+", re.UNICODE)


class _Lexicon:
    """Normalised passage or audioscript text, searchable by phrase."""

    def __init__(self, text: str) -> None:
        self.raw_tokens = _WORD.findall(text or "")
        self.tokens = [normalize(t) for t in self.raw_tokens]
        self.text = " " + " ".join(self.tokens) + " "
        self.canonical = " " + canonical(" ".join(self.tokens)) + " "

    def __bool__(self) -> bool:
        return bool(self.tokens)

    def contains_glued(self, phrase: str) -> bool:
        """Found inside the text once every space is removed.

        OCR of an audioscript often runs words together ("aboutmining"), so
        a word-boundary search misses answers that are plainly there. With
        the boundaries gone a short answer could hide inside a longer word,
        so this only counts for answers of five or more letters, and only as
        weak evidence.
        """
        target = re.sub(r"[^0-9a-z]", "", normalize(phrase))
        if len(target) < 5:
            return False
        if not hasattr(self, "_compact"):
            self._compact = re.sub(r"[^0-9a-z]", "", "".join(self.tokens))
        return target in self._compact

    def contains(self, phrase: str) -> bool:
        norm = " ".join(_WORD.findall(normalize(phrase)))
        if not norm:
            return False
        if f" {norm} " in self.text:
            return True
        canon = canonical(norm)
        return bool(canon) and f" {canon} " in self.canonical

    def by_shape(self, phrase: str) -> str | None:
        """The lexicon n-gram that OCR shape confusions make identical to `phrase`.

        "rnining" and "Mining" differ by too much for a plain similarity score
        (rn for m changes the length), yet are the same word to OCR. Comparing
        shape keys finds exactly those, and nothing else.
        """
        words = _WORD.findall(str(phrase))
        if not words or not self.tokens:
            return None
        n = len(words)
        target = shape_key(" ".join(words))
        for start in range(0, len(self.raw_tokens) - n + 1):
            candidate = " ".join(self.raw_tokens[start:start + n])
            if shape_key(candidate) == target:
                return candidate
        return None

    def closest(self, phrase: str) -> tuple[str, float] | None:
        """The lexicon n-gram most like `phrase`, as printed, with its score."""
        words = _WORD.findall(normalize(phrase))
        if not words or not self.tokens:
            return None
        n = len(words)
        target = " ".join(words)
        best: tuple[str, float] | None = None
        try:
            from rapidfuzz import fuzz

            def score(a: str, b: str) -> float:
                return float(fuzz.ratio(a, b))
        except ImportError:  # pragma: no cover - extras not installed
            from difflib import SequenceMatcher

            def score(a: str, b: str) -> float:
                return SequenceMatcher(None, a, b).ratio() * 100

        seen: set[str] = set()
        for start in range(0, len(self.tokens) - n + 1):
            candidate = " ".join(self.tokens[start:start + n])
            if candidate in seen:
                continue
            seen.add(candidate)
            value = score(target, candidate)
            if best is None or value > best[1]:
                best = (" ".join(self.raw_tokens[start:start + n]), value)
        return best


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _expected_kind(group: GroupInfo | None) -> str | None:
    if group is None or group.type == bp.UNKNOWN:
        return None
    if group.type == bp.TFNG:
        return TFNG
    if group.type == bp.YNNG:
        return YNNG
    if group.type in bp.LETTER_ANSWER_TYPES:
        return LETTER
    return TEXT


def _allowed_letters(group: GroupInfo) -> set[str] | None:
    # The rubric's own range ("Choose TWO letters, A-E") first: it is one short
    # line, whereas the option list is many lines and the one OCR damages -
    # an option whose letter got glued to its text drops out of the list.
    if group.letter_range:
        start, end = group.letter_range
        return {chr(c) for c in range(ord(start.upper()), ord(end.upper()) + 1)}
    letters = [o for o in group.options if len(o) == 1 and o.isalpha()]
    if letters:
        return {o.upper() for o in letters}
    return None


def _check_kind(answer: dict, group: GroupInfo | None, checks: list[Check]) -> None:
    expected = _expected_kind(group)
    kind = answer.get("kind") or TEXT
    values = {" ".join(str(a).lower().split()) for a in answer.get("accepted") or []}
    if expected is None:
        checks.append(Check("kind", WARN, "the question type is unknown"))
        return
    if expected in (TFNG, YNNG):
        scale = _TFNG_VALUES if expected == TFNG else _YNNG_VALUES
        if kind in (TFNG, YNNG) and values <= scale:
            checks.append(Check("kind", PASS))
        else:
            label = "TRUE/FALSE/NOT GIVEN" if expected == TFNG else "YES/NO/NOT GIVEN"
            checks.append(Check("kind", FAIL, f"the group expects {label}"))
        return
    if expected == LETTER:
        if group.type == bp.LIST_OF_HEADINGS:
            ok = all(v in _ROMAN for v in values) or kind in (LETTER, LETTER_SET)
        else:
            ok = kind in (LETTER, LETTER_SET)
        checks.append(Check("kind", PASS) if ok
                      else Check("kind", FAIL, "the group expects a letter"))
        return
    if kind == TEXT:
        checks.append(Check("kind", PASS))
    else:
        checks.append(Check("kind", FAIL, f"the group expects words, not {kind}"))


def _check_options(answer: dict, group: GroupInfo | None, checks: list[Check]) -> None:
    if group is None or _expected_kind(group) != LETTER:
        return
    values = [str(a).strip() for a in answer.get("accepted") or []]
    if group.type == bp.LIST_OF_HEADINGS:
        allowed = {o.lower() for o in group.options} or set(_ROMAN)
        bad = [v for v in values if v.lower() not in allowed]
    else:
        allowed = _allowed_letters(group)
        if allowed is None:
            checks.append(Check("option_range", WARN, "the options could not be read"))
            return
        bad = [v for v in values if v.upper() not in allowed]
    if bad:
        checks.append(Check(
            "option_range", FAIL,
            f"{', '.join(bad)} is not one of the options",
        ))
    else:
        checks.append(Check("option_range", PASS))


def _check_set(answer: dict, group: GroupInfo | None, checks: list[Check]) -> None:
    kind = answer.get("kind")
    if kind == LETTER_SET:
        members = list(answer.get("set_numbers") or [])
        letters = list(answer.get("accepted") or [])
        wanted = (group.select_count if group and group.select_count else None) or len(members)
        if len(set(letters)) == len(members) == wanted:
            checks.append(Check("set_size", PASS))
        else:
            checks.append(Check(
                "set_size", FAIL,
                f"{len(set(letters))} letter(s) for {len(members)} question(s)",
            ))
    elif group is not None and group.type in _SET_TYPES and kind == LETTER:
        checks.append(Check(
            "set_size", WARN, "a choose-several question keyed as a single letter",
        ))


def _check_word_limit(answer: dict, group: GroupInfo | None, checks: list[Check]) -> None:
    if group is None or (answer.get("kind") or TEXT) != TEXT:
        return
    if group.word_limit not in WORD_LIMITS:
        return
    accepted = [str(a) for a in answer.get("accepted") or []]
    fitting = [
        a for a in accepted
        if count_words(a) <= (effective_word_limit(group.word_limit, a) or 99)
    ]
    if not fitting:
        shortest = min(accepted, key=count_words) if accepted else ""
        checks.append(Check(
            "word_limit", FAIL,
            f"{count_words(shortest)} words is over the limit - another row may "
            "have run into this answer",
        ))
    else:
        checks.append(Check("word_limit", PASS))


def _check_source(
    answer: dict,
    group: GroupInfo | None,
    lexicon: _Lexicon | None,
    checks: list[Check],
) -> dict | None:
    """Passage/audioscript check. Returns a correction proposal, if any."""
    if group is None or group.type not in _SOURCE_TYPES:
        return None
    if (answer.get("kind") or TEXT) != TEXT or not lexicon:
        return None
    accepted = [str(a) for a in answer.get("accepted") or []]
    if not accepted:
        return None
    if any(lexicon.contains(a) for a in accepted):
        checks.append(Check("in_source", PASS))
        return None
    if any(lexicon.contains_glued(a) for a in accepted):
        checks.append(Check(
            "in_source", PASS, "found in run-together text", weak=True,
        ))
        return None

    corrected: list[str] = []
    explained = True
    for value in accepted:
        shaped = lexicon.by_shape(value)
        if shaped is not None:
            corrected.append(shaped)
            continue
        explained = False
        found = lexicon.closest(value)
        if found is None or found[1] < CORRECTION_SCORE:
            corrected.append(value)
            continue
        corrected.append(found[0])

    if corrected != accepted and explained:
        # Proposed, not trusted: the passage text may itself be the OCR'd side
        # of the confusion, so a person confirms the one-line fix.
        checks.append(Check(
            "in_source", WARN,
            "corrected to the passage spelling (an OCR letter-shape confusion) - confirm it",
        ))
        return {"from": accepted, "to": _dedupe(corrected), "explained": True}
    if corrected != accepted:
        checks.append(Check(
            "in_source", WARN,
            f"not found as written; the text has {corrected[0]!r}",
        ))
        return {"from": accepted, "to": _dedupe(corrected), "explained": False}
    checks.append(Check("in_source", WARN, "not found in the passage or audioscript"))
    return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _check_evidence(evidence: dict | None, checks: list[Check]) -> None:
    if not evidence:
        return
    agreement = evidence.get("agreement")
    if agreement == "agree":
        note = ("two independent readings agree" if evidence.get("independent")
                else "two readings of the key page agree")
        checks.append(Check("agreement", PASS, note))
    elif agreement == "disagree":
        reads = evidence.get("reads") or {}
        shown = "; ".join(f"{k}: {v!r}" for k, v in reads.items())
        checks.append(Check("agreement", FAIL, f"the readings disagree ({shown})"))
    confidence = evidence.get("confidence")
    if confidence is not None:
        if confidence >= TEXT_CONFIDENCE:
            checks.append(Check("confidence", PASS, f"{confidence:.2f}"))
        else:
            checks.append(Check("confidence", WARN, f"OCR confidence {confidence:.2f}"))
    if evidence.get("filled"):
        checks.append(Check("second_reading", WARN,
                            "the first reading had no answer here"))


def _status(answer: dict, evidence: dict | None, checks: list[Check]) -> str:
    results = {c.name: c.result for c in checks}
    if any(r == FAIL for r in results.values()):
        return CHECK
    source = (evidence or {}).get("source") or "manual"
    kind = answer.get("kind") or TEXT

    if source in ("text", "manual"):
        # A typeset key, or one a person typed: structure is all that is left
        # to check. A passage miss is not held against it - the passage text
        # itself may be the OCR'd part.
        blocking = [n for n, r in results.items() if r == WARN
                    and n not in ("in_source", "confidence")]
        return CHECK if blocking else TRUSTED

    confidence = (evidence or {}).get("confidence")
    agreed = results.get("agreement") == PASS
    independent = bool((evidence or {}).get("independent"))
    if results.get("second_reading") == WARN and not agreed:
        return CHECK
    if results.get("kind") == WARN or results.get("option_range") == WARN \
            or results.get("set_size") == WARN:
        return CHECK

    if kind in (LETTER, LETTER_SET, TFNG, YNNG):
        if agreed:
            return TRUSTED
        if confidence is not None and confidence >= LETTER_CONFIDENCE:
            return TRUSTED
        return CHECK

    if confidence is not None and confidence < TEXT_CONFIDENCE:
        return CHECK
    source_check = next((c for c in checks if c.name == "in_source"), None)
    if source_check is not None and source_check.result == PASS:
        if not source_check.weak or agreed:
            return TRUSTED
    if agreed and independent:
        return TRUSTED
    return CHECK


def check_answer(
    number: int,
    answer: dict | None,
    group: GroupInfo | None = None,
    lexicon_text: str | _Lexicon | None = None,
    evidence: dict | None = None,
) -> CellReport:
    """Check one answer (JSON form). Never raises."""
    if not answer or not answer.get("accepted"):
        return CellReport(number, MISSING, [Check("present", FAIL, "no answer")])
    lexicon = lexicon_text if isinstance(lexicon_text, _Lexicon) else (
        _Lexicon(lexicon_text) if lexicon_text else None
    )
    checks: list[Check] = [Check("present", PASS)]
    _check_kind(answer, group, checks)
    _check_options(answer, group, checks)
    _check_set(answer, group, checks)
    _check_word_limit(answer, group, checks)
    correction = _check_source(answer, group, lexicon, checks)
    _check_evidence(evidence, checks)
    return CellReport(number, _status(answer, evidence, checks), checks, correction)


def check_module(
    groups: list[GroupInfo],
    answers: dict,
    evidence: dict | None = None,
    lexicons: dict[int, str] | None = None,
    total: int = 40,
) -> dict[int, CellReport]:
    """Check every question 1..total. Keys of `answers`/`evidence` may be str or int."""
    evidence = evidence or {}
    built = {order: _Lexicon(text) for order, text in (lexicons or {}).items() if text}
    reports: dict[int, CellReport] = {}
    for number in range(1, total + 1):
        answer = answers.get(str(number)) or answers.get(number)
        group = _group_for(groups, number)
        lexicon = built.get(group.section) if group else None
        cell_evidence = evidence.get(str(number)) or evidence.get(number)
        if isinstance(cell_evidence, dict) and "evidence" in cell_evidence \
                and "source" not in cell_evidence:
            cell_evidence = cell_evidence.get("evidence")
        reports[number] = check_answer(number, answer, group, lexicon, cell_evidence)
    return reports


def summarise(reports: dict[int, CellReport], confirmed: set[int] | None = None) -> dict:
    """{trusted, check, missing, confirmed} counts, honouring confirmations."""
    confirmed = confirmed or set()
    counts = {TRUSTED: 0, CHECK: 0, MISSING: 0, CONFIRMED: 0}
    for number, report in reports.items():
        if number in confirmed and report.status != MISSING:
            counts[CONFIRMED] += 1
        else:
            counts[report.status] = counts.get(report.status, 0) + 1
    return counts
