"""Attempt lifecycle: start, autosave, submit, mark, report.

The marking itself lives in ``exams.marking`` and has no Django dependency.
This module is the thin layer that reads rows, hands plain dicts to the engine,
and writes the result back.

Marking runs **synchronously** on submit. It is pure Python over at most forty
answers — well under a millisecond — so a background job would add latency and
failure modes for nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from exams import bands
from exams.keysheet import answers_from_json
from exams.marking import BLANK, TEXT, AnswerKey, mark_module
from exams.models import (
    LISTENING,
    Attempt,
    AttemptAnswer,
    Module,
    Question,
)

__all__ = [
    "ModuleNotAvailable",
    "AttemptClosed",
    "start_attempt",
    "save_answers",
    "submit_attempt",
    "remark_module",
    "module_duration",
    "answer_keys_for",
]

#: Grace given to a submit that arrives just after the deadline, covering clock
#: skew and a slow final request rather than punishing the candidate for it.
SUBMIT_GRACE = timedelta(seconds=30)


class ModuleNotAvailable(Exception):
    """The module cannot be sat: unpublished, or missing its verified key."""


class AttemptClosed(Exception):
    """The attempt has already been submitted or has expired."""


def module_duration(module: Module) -> int:
    """Total seconds allowed, including listening transfer time."""
    if module.skill != LISTENING:
        return module.duration_seconds or 3600
    audio = sum(
        section.audio.duration_seconds or 0
        for section in module.sections.select_related("audio")
        if section.audio_id
    )
    return (audio or module.duration_seconds or 1800) + (module.transfer_seconds or 0)


def answer_keys_for(module: Module) -> dict[int, AnswerKey]:
    """The module's confirmed answer key, or empty if it has none.

    Word limits come from the question's rubric, not from the key. Only the
    group knows "ONE WORD ONLY" for certain: a key typed into the admin grid or
    read from an image never carries it, and relying on the key meant an
    over-long answer was marked plain wrong instead of over the word limit.
    """
    sheet = getattr(module, "answer_sheet", None)
    if sheet is None or not sheet.is_verified:
        return {}
    keys = answers_from_json(sheet.answers)
    limits = dict(
        Question.objects.filter(module=module).values_list("number", "group__word_limit")
    )
    for number, key in list(keys.items()):
        limit = limits.get(number) or ""
        if limit and key.kind == TEXT and key.word_limit != limit:
            keys[number] = replace(key, word_limit=limit)
    return keys


@transaction.atomic
def start_attempt(user, module: Module, mode: str = Attempt.EXAM) -> Attempt:
    """Begin an attempt, or return the one already in progress.

    Idempotent on purpose: a double-click, a refresh or a flaky connection must
    not create a second attempt and silently halve the candidate's time.
    """
    if not module.is_published:
        raise ModuleNotAvailable("this test is not available")
    problems = module.blocking_problems()
    if problems:
        raise ModuleNotAvailable("; ".join(problems))

    existing = (
        Attempt.objects.select_for_update()
        .filter(user=user, module=module, status=Attempt.IN_PROGRESS)
        .first()
    )
    if existing is not None:
        if existing.expires_at <= timezone.now():
            submit_attempt(existing, expired=True)
            raise AttemptClosed("your previous attempt expired and was submitted")
        return existing

    now = timezone.now()
    return Attempt.objects.create(
        user=user,
        module=module,
        mode=mode if mode in dict(Attempt.MODE_CHOICES) else Attempt.EXAM,
        expires_at=now + timedelta(seconds=module_duration(module)),
    )


@transaction.atomic
def save_answers(attempt: Attempt, answers: list[dict]) -> int:
    """Upsert answers. Returns how many rows were touched.

    Idempotent: the client re-sends whatever is dirty, and may re-send the same
    value after a retry.
    """
    if attempt.status != Attempt.IN_PROGRESS:
        raise AttemptClosed("this attempt is no longer open")
    if attempt.expires_at + SUBMIT_GRACE <= timezone.now():
        raise AttemptClosed("time is up")

    by_number = {
        q.number: q for q in Question.objects.filter(module_id=attempt.module_id)
    }
    saved = 0
    for entry in answers or []:
        number = entry.get("question_number")
        question = by_number.get(number)
        if question is None:
            continue
        value = entry.get("value")
        if not isinstance(value, dict):
            value = {"text": "" if value is None else str(value)}
        AttemptAnswer.objects.update_or_create(
            attempt=attempt, question=question,
            defaults={"question_number": number, "value": value},
        )
        saved += 1
    return saved


@transaction.atomic
def submit_attempt(attempt: Attempt, expired: bool = False) -> Attempt:
    """Mark the attempt and store the raw score and band."""
    if attempt.status != Attempt.IN_PROGRESS:
        return attempt

    module = attempt.module
    keys = answer_keys_for(module)
    responses = {
        answer.question_number: answer.value
        for answer in attempt.answers.all()
    }

    result = mark_module(keys, responses) if keys else None

    if result is not None:
        rows = {a.question_number: a for a in attempt.answers.all()}
        for number, marked in result.results.items():
            row = rows.get(number)
            if row is None:
                continue
            row.is_correct = marked.is_correct
            row.awarded_marks = marked.awarded
            row.mark_reason = marked.reason
            row.save(update_fields=["is_correct", "awarded_marks", "mark_reason"])
        attempt.raw_score = result.raw_score
        attempt.band = bands.raw_to_band(
            module.skill, result.raw_score,
            variant=module.test.book.variant or "academic",
            version=module.band_table_version or bands.CURRENT_VERSION,
        )
        attempt.band_table_version = module.band_table_version or bands.CURRENT_VERSION

    attempt.status = Attempt.EXPIRED if expired else Attempt.SUBMITTED
    attempt.submitted_at = timezone.now()
    attempt.marked_at = timezone.now()
    attempt.save(update_fields=[
        "status", "submitted_at", "marked_at", "raw_score", "band",
        "band_table_version",
    ])
    return attempt


@transaction.atomic
def remark_module(module: Module) -> int:
    """Re-mark every submitted attempt after the answer key changed.

    The first imports of any book will have key mistakes, so this is needed from
    the start rather than bolted on later. It is a pure function over answers
    already stored, so it costs milliseconds.
    """
    keys = answer_keys_for(module)
    if not keys:
        return 0

    changed = 0
    for attempt in module.attempts.filter(status__in=[Attempt.SUBMITTED, Attempt.EXPIRED]):
        responses = {a.question_number: a.value for a in attempt.answers.all()}
        result = mark_module(keys, responses)
        rows = {a.question_number: a for a in attempt.answers.all()}
        for number, marked in result.results.items():
            row = rows.get(number)
            if row is None:
                continue
            row.is_correct = marked.is_correct
            row.awarded_marks = marked.awarded
            row.mark_reason = marked.reason
            row.save(update_fields=["is_correct", "awarded_marks", "mark_reason"])
        attempt.raw_score = result.raw_score
        attempt.band = bands.raw_to_band(
            module.skill, result.raw_score,
            variant=module.test.book.variant or "academic",
            version=module.band_table_version or bands.CURRENT_VERSION,
        )
        attempt.marked_at = timezone.now()
        attempt.save(update_fields=["raw_score", "band", "marked_at"])
        changed += 1
    return changed


@dataclass
class ResultRow:
    number: int
    response: str
    is_correct: bool
    reason: str
    accepted: list[str]


def result_rows(attempt: Attempt) -> list[ResultRow]:
    """Per-question review, revealed only after submission."""
    keys = answer_keys_for(attempt.module)
    rows: list[ResultRow] = []
    answers = {a.question_number: a for a in attempt.answers.all()}
    for number in range(1, (attempt.module.total_questions or 40) + 1):
        answer = answers.get(number)
        key = keys.get(number)
        value = answer.value if answer else {}
        response = ""
        if isinstance(value, dict):
            response = (
                value.get("text")
                or value.get("letter")
                or ", ".join(value.get("letters") or [])
                or ""
            )
        rows.append(
            ResultRow(
                number=number,
                response=response,
                is_correct=bool(answer.is_correct) if answer else False,
                reason=(answer.mark_reason if answer else BLANK) or BLANK,
                accepted=list(key.accepted) if key else [],
            )
        )
    return rows
