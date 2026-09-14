"""Deterministic marking for IELTS Reading and Listening answers.

Pure module: **no Django imports**. It takes plain dicts and returns dataclasses,
so the whole engine is unit-testable at thousands of cases a second with no
database. Views adapt between this and the ORM.

There is deliberately **no fuzzy or edit-distance matching anywhere**. Accepting
`whether` for `weather`, or `quite` for `quiet`, would be both wrong and
impossible to explain to a candidate. Every rule here is an exact equivalence.

Answer-key alternatives (`10/ten`) and optional parts (`metal(s)`, `(the) equator`)
are expanded into an explicit `accepted` list at *import* time by
``exams.keygrammar`` — not here. That keeps this matcher dumb and lets an admin
see and correct the literal accepted set in the review screen.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Mapping, Sequence

__all__ = [
    "MatchPolicy",
    "DEFAULT_POLICY",
    "STRICT_POLICY",
    "AnswerKey",
    "MarkResult",
    "ModuleResult",
    # answer kinds
    "TEXT",
    "LETTER",
    "LETTER_SET",
    "TFNG",
    "YNNG",
    # mark reasons
    "CORRECT",
    "WRONG",
    "BLANK",
    "OVER_WORD_LIMIT",
    "OVER_SELECTED",
    "WORD_LIMITS",
    "WORD_LIMIT_LABELS",
    "normalize",
    "canonical",
    "variants",
    "count_words",
    "effective_word_limit",
    "mark_one",
    "mark_set",
    "mark_module",
]


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchPolicy:
    """Which equivalences count as the same answer.

    Every rule is deterministic. Turning the first five off reduces matching to
    "case-insensitive, outer whitespace ignored, text only".
    """

    hyphen_space: bool = True          # well-known == well known  (never wellknown)
    number_words: bool = True          # 10 == ten, 1st == first
    contractions: bool = True          # don't == do not
    accents: bool = True               # café == cafe
    spelling_variants: bool = True     # colour == color  (curated list only)
    strip_trailing_punct: bool = True  # "apple." == "apple"
    enforce_word_limit: bool = True    # exceeding ONE WORD ONLY is wrong


DEFAULT_POLICY = MatchPolicy()

#: Case + outer whitespace only. Word limits still apply.
STRICT_POLICY = MatchPolicy(
    hyphen_space=False,
    number_words=False,
    contractions=False,
    accents=False,
    spelling_variants=False,
    strip_trailing_punct=False,
)


# ---------------------------------------------------------------------------
# Key / result types
# ---------------------------------------------------------------------------

TEXT = "text"
LETTER = "letter"
LETTER_SET = "letter_set"
TFNG = "tfng"
YNNG = "ynng"

CORRECT = "correct"
WRONG = "wrong"
BLANK = "blank"
OVER_WORD_LIMIT = "over_word_limit"
OVER_SELECTED = "over_selected"


@dataclass(frozen=True)
class AnswerKey:
    kind: str = TEXT
    accepted: tuple[str, ...] = ()
    word_limit: str = ""
    #: Shared by every member of an "IN EITHER ORDER" group.
    set_id: str | None = None
    set_numbers: tuple[int, ...] = ()
    select_count: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in (TEXT, LETTER, LETTER_SET, TFNG, YNNG):
            raise ValueError(f"unknown answer kind: {self.kind!r}")


@dataclass(frozen=True)
class MarkResult:
    is_correct: bool
    awarded: int
    reason: str
    matched: str | None = None
    detail: str = ""


@dataclass
class ModuleResult:
    raw_score: int = 0
    total: int = 0
    results: dict[int, MarkResult] = field(default_factory=dict)

    @property
    def correct_count(self) -> int:
        return sum(1 for r in self.results.values() if r.is_correct)

    @property
    def blank_count(self) -> int:
        return sum(1 for r in self.results.values() if r.reason == BLANK)

    @property
    def wrong_count(self) -> int:
        return sum(
            1 for r in self.results.values()
            if not r.is_correct and r.reason != BLANK
        )


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_QUOTE_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "´": "'", "`": "'",
}
_DASH_MAP = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-",
}
_SPACE_MAP = {
    " ": " ", " ": " ", " ": " ", " ": " ",
    " ": " ", "　": " ", "\t": " ", "\n": " ", "\r": " ",
}
_CHAR_MAP = {**_QUOTE_MAP, **_DASH_MAP, **_SPACE_MAP}
_TRANSLATION = str.maketrans(_CHAR_MAP)

_TRAILING_PUNCT = ".,;:!?"


def normalize(value: object, policy: MatchPolicy = DEFAULT_POLICY) -> str:
    """Light normalisation: case, unicode shape, whitespace, trailing punctuation.

    Hyphens, contractions and accents survive — this is also the form word
    counting uses, where `well-known` and `don't` must each count as one word.
    """
    if value is None:
        return ""
    text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_TRANSLATION)
    text = text.casefold()
    text = " ".join(text.split())
    if policy.strip_trailing_punct:
        text = text.strip(_TRAILING_PUNCT)
        text = " ".join(text.split())
    # Surrounding quotes a candidate may have typed around the whole answer.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1].strip()
    return text


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


# -- contractions -----------------------------------------------------------

_CONTRACTIONS = {
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "isn't": "is not", "aren't": "are not", "wasn't": "was not",
    "weren't": "were not", "hasn't": "has not", "haven't": "have not",
    "hadn't": "had not", "won't": "will not", "wouldn't": "would not",
    "shan't": "shall not", "shouldn't": "should not", "couldn't": "could not",
    "mustn't": "must not", "needn't": "need not", "oughtn't": "ought not",
    "can't": "cannot", "can not": "cannot",
    "it's": "it is", "that's": "that is", "there's": "there is",
    "here's": "here is", "what's": "what is", "who's": "who is",
    "he's": "he is", "she's": "she is", "let's": "let us",
    "i'm": "i am", "you're": "you are", "we're": "we are", "they're": "they are",
    "i've": "i have", "you've": "you have", "we've": "we have",
    "they've": "they have",
    "i'll": "i will", "you'll": "you will", "he'll": "he will",
    "she'll": "she will", "we'll": "we will", "they'll": "they will",
    "i'd": "i would", "you'd": "you would", "he'd": "he would",
    "she'd": "she would", "we'd": "we would", "they'd": "they would",
}

# -- curated British/American spellings (never a generic -ise/-ize rule, which
#    would wrongly rewrite exercise, advertise, surprise, compromise, ...) -----

_SPELLING = {
    # -our / -or
    "colour": "color", "colours": "colors", "coloured": "colored",
    "favour": "favor", "favours": "favors", "favourite": "favorite",
    "flavour": "flavor", "flavours": "flavors", "honour": "honor",
    "labour": "labor", "neighbour": "neighbor", "neighbours": "neighbors",
    "neighbourhood": "neighborhood", "behaviour": "behavior",
    "behaviours": "behaviors", "harbour": "harbor", "humour": "humor",
    "rumour": "rumor", "vapour": "vapor", "odour": "odor",
    "splendour": "splendor", "vigour": "vigor", "armour": "armor",
    "parlour": "parlor", "saviour": "savior", "endeavour": "endeavor",
    # -re / -er
    "centre": "center", "centres": "centers", "theatre": "theater",
    "metre": "meter", "metres": "meters", "litre": "liter", "litres": "liters",
    "fibre": "fiber", "fibres": "fibers", "calibre": "caliber",
    "sombre": "somber", "spectre": "specter",
    # -ise / -ize
    "organise": "organize", "organised": "organized", "organising": "organizing",
    "organisation": "organization", "organisations": "organizations",
    "realise": "realize", "realised": "realized", "realisation": "realization",
    "recognise": "recognize", "recognised": "recognized",
    "apologise": "apologize", "analyse": "analyze", "analysed": "analyzed",
    "criticise": "criticize", "emphasise": "emphasize",
    "specialise": "specialize", "specialised": "specialized",
    "specialisation": "specialization",
    "summarise": "summarize", "memorise": "memorize", "minimise": "minimize",
    "maximise": "maximize", "categorise": "categorize",
    "characterise": "characterize", "civilise": "civilize",
    "civilisation": "civilization", "colonise": "colonize",
    "familiarise": "familiarize", "generalise": "generalize",
    "modernise": "modernize", "urbanisation": "urbanization",
    # doubled -ll-
    "travelled": "traveled", "travelling": "traveling", "traveller": "traveler",
    "travellers": "travelers", "cancelled": "canceled", "cancelling": "canceling",
    "labelled": "labeled", "labelling": "labeling", "modelled": "modeled",
    "modelling": "modeling", "fuelled": "fueled", "marvellous": "marvelous",
    "jewellery": "jewelry",
    # -ce / -se
    "defence": "defense", "offence": "offense", "licence": "license",
    "pretence": "pretense",
    # miscellaneous
    "programme": "program", "programmes": "programs", "catalogue": "catalog",
    "dialogue": "dialog", "analogue": "analog", "aeroplane": "airplane",
    "grey": "gray", "tyre": "tire", "tyres": "tires", "plough": "plow",
    "cheque": "check", "storey": "story", "storeys": "stories",
    "mould": "mold", "moustache": "mustache", "sceptical": "skeptical",
    "aluminium": "aluminum", "draught": "draft", "kerb": "curb",
    "pyjamas": "pajamas", "ageing": "aging", "judgement": "judgment",
    "enrol": "enroll", "fulfil": "fulfill", "skilful": "skillful",
    "instalment": "installment", "sulphur": "sulfur",
    "archaeology": "archeology", "paediatric": "pediatric",
    "foetus": "fetus", "oestrogen": "estrogen", "anaemia": "anemia",
    "encyclopaedia": "encyclopedia", "manoeuvre": "maneuver",
    "woollen": "woolen", "practise": "practice", "practises": "practices",
}

# -- numbers ----------------------------------------------------------------

_UNITS = {
    "zero": 0, "nought": 0, "oh": 0,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}

_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
    "twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50,
    "sixtieth": 60, "seventieth": 70, "eightieth": 80, "ninetieth": 90,
    "hundredth": 100, "thousandth": 1000,
}

_NUMERIC_TOKEN = re.compile(r"^[+-]?\d+(?:[.,]\d+)*$")
_ORDINAL_DIGITS = re.compile(r"^(\d+)(?:st|nd|rd|th)$")


def _ordinal_suffix(value: int) -> str:
    if 10 <= value % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")


def _parse_number_run(tokens: Sequence[str], start: int) -> tuple[int, int] | None:
    """Parse a run of number words beginning at `start`.

    Returns (value, tokens_consumed) or None. Handles `twenty one`, `twenty-one`
    (already split by the hyphen rule), `two hundred`, `one hundred and fifty`.
    """
    total = 0
    current = 0
    consumed = 0
    seen = False
    i = start
    while i < len(tokens):
        tok = tokens[i]
        if tok in _UNITS:
            # "twenty five" — a unit may follow a tens word, but two bare units
            # in a row ("five six") are two separate numbers, not one.
            if seen and current % 10 != 0 and current < 100:
                break
            current += _UNITS[tok]
        elif tok in _TENS:
            if seen and current % 100 != 0:
                break
            current += _TENS[tok]
        elif tok == "hundred" and seen:
            current = max(current, 1) * 100
        elif tok in _SCALES and tok != "hundred" and seen:
            total += max(current, 1) * _SCALES[tok]
            current = 0
        elif tok == "and" and seen and i + 1 < len(tokens) and (
            tokens[i + 1] in _UNITS or tokens[i + 1] in _TENS
        ):
            # Only inside a number: "one hundred and fifty", never "bread and butter".
            i += 1
            consumed += 1
            continue
        else:
            break
        seen = True
        i += 1
        consumed += 1
    if not seen:
        return None
    return total + current, consumed


def _numbers_to_digits(tokens: Sequence[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _ORDINALS:
            out.append(f"{_ORDINALS[tok]}{_ordinal_suffix(_ORDINALS[tok])}")
            i += 1
            continue
        parsed = _parse_number_run(tokens, i)
        if parsed is not None:
            value, consumed = parsed
            out.append(str(value))
            i += consumed
            continue
        m = _ORDINAL_DIGITS.match(tok)
        if m:
            value = int(m.group(1))
            out.append(f"{value}{_ordinal_suffix(value)}")
            i += 1
            continue
        if _NUMERIC_TOKEN.match(tok):
            # Strip thousands separators so 1,500 == 1500; keep decimals.
            cleaned = tok.replace(",", "") if re.match(r"^\d{1,3}(,\d{3})+$", tok) else tok
            out.append(cleaned)
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


def canonical(value: object, policy: MatchPolicy = DEFAULT_POLICY) -> str:
    """The comparison form. Two answers match iff their canonical forms are equal.

    Applied identically to the candidate's response and to each accepted answer,
    so every rule is a two-sided equivalence rather than a one-way loosening.
    """
    text = normalize(value, policy)
    if not text:
        return ""
    if policy.accents:
        text = _strip_accents(text)
    if policy.contractions:
        # Multi-word contraction forms ("can not") before tokenising.
        for src, dst in _CONTRACTIONS.items():
            if " " in src and src in text:
                text = text.replace(src, dst)
    if policy.hyphen_space:
        text = text.replace("-", " ")
    tokens = text.split()
    if policy.contractions:
        expanded: list[str] = []
        for tok in tokens:
            expanded.extend(_CONTRACTIONS.get(tok, tok).split())
        tokens = expanded
    if policy.spelling_variants:
        tokens = [_SPELLING.get(tok, tok) for tok in tokens]
    if policy.number_words:
        tokens = _numbers_to_digits(tokens)
    return " ".join(tokens)


def variants(value: object, policy: MatchPolicy = DEFAULT_POLICY) -> frozenset[str]:
    """Comparison forms for `value`.

    Every equivalence is expressed as a two-sided canonicalisation, so this is
    normally a single form. Kept as a set because the review UI shows it, and so
    a genuinely ambiguous rule could be added later without changing callers.
    """
    return frozenset({canonical(value, policy)})


# ---------------------------------------------------------------------------
# Word limits
# ---------------------------------------------------------------------------

#: rubric key -> (max words, a number may be added on top)
WORD_LIMITS: dict[str, tuple[int, bool]] = {
    "one_word": (1, False),
    "one_word_number": (1, True),
    "two_words": (2, False),
    "two_words_number": (2, True),
    "three_words": (3, False),
    "three_words_number": (3, True),
}

WORD_LIMIT_LABELS = {
    "one_word": "ONE WORD ONLY",
    "one_word_number": "ONE WORD AND/OR A NUMBER",
    "two_words": "NO MORE THAN TWO WORDS",
    "two_words_number": "NO MORE THAN TWO WORDS AND/OR A NUMBER",
    "three_words": "NO MORE THAN THREE WORDS",
    "three_words_number": "NO MORE THAN THREE WORDS AND/OR A NUMBER",
}


def count_words(value: object, policy: MatchPolicy = DEFAULT_POLICY) -> int:
    """Count words the way Cambridge does.

    Split on whitespace only: a hyphenated compound, a number and a contraction
    are each **one** word. Counting runs on the lightly-normalised form for
    exactly that reason — the canonical form splits hyphens and expands
    contractions, which would inflate the count.
    """
    text = normalize(value, policy)
    return len(text.split()) if text else 0


def _is_pure_number(token: str) -> bool:
    return bool(_NUMERIC_TOKEN.match(token) or _ORDINAL_DIGITS.match(token))


def effective_word_limit(word_limit: str, value: object,
                         policy: MatchPolicy = DEFAULT_POLICY) -> int | None:
    """Max tokens permitted for this answer, or None when unlimited.

    "AND/OR A NUMBER" allows one extra token *only* when a numeric token is
    actually present, so "TWO WORDS AND/OR A NUMBER" permits `25 April 2019`
    but not three plain words.
    """
    spec = WORD_LIMITS.get(word_limit)
    if spec is None:
        return None
    max_words, number_allowed = spec
    if number_allowed:
        tokens = normalize(value, policy).split()
        if any(_is_pure_number(t) for t in tokens):
            return max_words + 1
    return max_words


# ---------------------------------------------------------------------------
# Response extraction
# ---------------------------------------------------------------------------

_TFNG_SYNONYMS = {
    "true": "true", "t": "true", "yes": "yes", "y": "yes",
    "false": "false", "f": "false", "no": "no", "n": "no",
    "not given": "not given", "notgiven": "not given", "ng": "not given",
    "not_given": "not given",
}


def _tfng_canonical(value: object) -> str:
    text = normalize(value).replace("-", " ")
    text = " ".join(text.split())
    return _TFNG_SYNONYMS.get(text, text)


def _letter_canonical(value: object) -> str:
    return normalize(value).strip().upper()


def _response_text(value: Mapping | str | None) -> str:
    """Pull the candidate's answer out of the stored JSON value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for field_name in ("text", "letter", "value"):
            got = value.get(field_name)
            if isinstance(got, str) and got.strip():
                return got
    return ""


def _response_letters(value: Mapping | Sequence | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        letters = value.get("letters")
        if isinstance(letters, (list, tuple)):
            return [_letter_canonical(x) for x in letters if str(x).strip()]
        single = _response_text(value)
        return [_letter_canonical(single)] if single.strip() else []
    if isinstance(value, (list, tuple)):
        return [_letter_canonical(x) for x in value if str(x).strip()]
    return []


# ---------------------------------------------------------------------------
# Marking
# ---------------------------------------------------------------------------


def mark_one(key: AnswerKey, value: Mapping | str | None,
             policy: MatchPolicy = DEFAULT_POLICY) -> MarkResult:
    """Mark a single (non-set) answer."""
    if key.kind == LETTER_SET:
        raise ValueError("use mark_set() for letter_set answers")

    if key.kind in (TFNG, YNNG):
        raw = _response_text(value)
        if not raw.strip():
            return MarkResult(False, 0, BLANK)
        got = _tfng_canonical(raw)
        for accepted in key.accepted:
            if _tfng_canonical(accepted) == got:
                return MarkResult(True, 1, CORRECT, accepted)
        return MarkResult(False, 0, WRONG)

    if key.kind == LETTER:
        raw = _response_text(value)
        if not raw.strip():
            return MarkResult(False, 0, BLANK)
        got = _letter_canonical(raw)
        for accepted in key.accepted:
            if _letter_canonical(accepted) == got:
                return MarkResult(True, 1, CORRECT, accepted)
        return MarkResult(False, 0, WRONG)

    # text
    raw = _response_text(value)
    if not raw.strip():
        return MarkResult(False, 0, BLANK)

    if policy.enforce_word_limit and key.word_limit:
        limit = effective_word_limit(key.word_limit, raw, policy)
        if limit is not None and count_words(raw, policy) > limit:
            label = WORD_LIMIT_LABELS.get(key.word_limit, key.word_limit)
            return MarkResult(
                False, 0, OVER_WORD_LIMIT, None,
                detail=f"Exceeded {label}",
            )

    got = canonical(raw, policy)
    if not got:
        return MarkResult(False, 0, BLANK)
    for accepted in key.accepted:
        if canonical(accepted, policy) == got:
            return MarkResult(True, 1, CORRECT, accepted)
    return MarkResult(False, 0, WRONG)


def mark_set(keys: Sequence[AnswerKey], values: Mapping[int, Mapping | Sequence | None],
             policy: MatchPolicy = DEFAULT_POLICY) -> dict[int, MarkResult]:
    """Mark an "IN EITHER ORDER" group jointly.

    Every member carries the same accepted set, and the UI writes the same list
    of letters to each. One mark per correct letter, order irrelevant. Selecting
    more letters than asked for scores **zero for the whole set**, which is real
    exam behaviour (the UI also prevents it).
    """
    if not keys:
        return {}
    key = keys[0]
    numbers = list(key.set_numbers) or [n for n in values]
    numbers = sorted(numbers)

    selected: list[str] = []
    for number in numbers:
        got = _response_letters(values.get(number))
        if got:
            selected = got
            break

    accepted = {_letter_canonical(a) for a in key.accepted}
    required = key.select_count or len(accepted) or len(numbers)

    if not selected:
        return {n: MarkResult(False, 0, BLANK) for n in numbers}

    unique = list(dict.fromkeys(selected))
    if len(unique) > required:
        return {
            n: MarkResult(
                False, 0, OVER_SELECTED, None,
                detail=f"Selected {len(unique)} of {required} required",
            )
            for n in numbers
        }

    hits = [letter for letter in unique if letter in accepted]
    awarded = len(hits)
    ordered_accepted = sorted(accepted)

    results: dict[int, MarkResult] = {}
    for index, number in enumerate(numbers):
        if index < awarded:
            results[number] = MarkResult(
                True, 1, CORRECT,
                hits[index] if index < len(hits) else None,
            )
        else:
            reason = WRONG if awarded == 0 else "partial"
            results[number] = MarkResult(
                False, 0, reason, None,
                detail=f"Accepted: {', '.join(ordered_accepted)}",
            )
    return results


def mark_module(keys: Mapping[int, AnswerKey],
                answers: Mapping[int, Mapping | Sequence | None],
                policy: MatchPolicy = DEFAULT_POLICY) -> ModuleResult:
    """Mark a whole module. `keys` and `answers` are indexed by question number."""
    result = ModuleResult(total=len(keys))

    # Group the "IN EITHER ORDER" questions so each set is marked once.
    sets: dict[str, list[AnswerKey]] = {}
    singles: list[tuple[int, AnswerKey]] = []
    for number, key in sorted(keys.items()):
        if key.kind == LETTER_SET and key.set_id:
            sets.setdefault(key.set_id, []).append(key)
        else:
            singles.append((number, key))

    for number, key in singles:
        result.results[number] = mark_one(key, answers.get(number), policy)

    for set_keys in sets.values():
        for number, marked in mark_set(set_keys, answers, policy).items():
            result.results[number] = marked

    result.raw_score = sum(r.awarded for r in result.results.values())
    return result
