"""Write a reviewed draft payload into real rows.

Upserts by natural key at every level, so re-publishing the same book updates in
place rather than creating a second copy. That matters beyond tidiness:
``Question`` ids stay stable, so an ``AttemptAnswer`` written last week still
points at the same question after a re-import.

Publishing content does **not** make it visible. A module only becomes available
to students when ``Module.blocking_problems()`` is empty, which requires a
human-verified answer sheet. Import fills in the questions; it never fills in
the key.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils.text import slugify

from exams.models import (
    LISTENING,
    READING,
    AnswerKeySheet,
    Book,
    ExamTest,
    Module,
    Question,
    QuestionGroup,
    Section,
)

__all__ = ["PublishResult", "publish_payload"]

#: An IELTS Reading module is an hour. Listening is however long its audio runs
#: plus transfer time, so it is computed when the audio is attached.
READING_SECONDS = 3600
LISTENING_TRANSFER_SECONDS = 600


@dataclass
class PublishResult:
    book: Book | None = None
    created_modules: list[int] = field(default_factory=list)
    updated_modules: list[int] = field(default_factory=list)
    questions_written: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def module_ids(self) -> list[int]:
        return sorted({*self.created_modules, *self.updated_modules})


@transaction.atomic
def publish_payload(payload: dict, book_slug: str = "") -> PublishResult:
    """Materialise a draft into Book/Test/Module/Section/Group/Question rows."""
    result = PublishResult()

    book_data = payload.get("book") or {}
    slug = book_slug or book_data.get("slug") or ""
    if not slug:
        slug = slugify(book_data.get("title") or "imported-book")

    book, _ = Book.objects.update_or_create(
        slug=slug,
        defaults={
            "title": book_data.get("title") or slug.replace("-", " ").title(),
            "variant": book_data.get("variant") or "academic",
            "content_hash": book_data.get("content_hash") or "",
        },
    )
    result.book = book

    for test_data in payload.get("tests") or []:
        number = test_data.get("number")
        if not number:
            result.warnings.append("a test with no number was skipped")
            continue
        test, _ = ExamTest.objects.update_or_create(
            book=book, number=number,
            defaults={"title": test_data.get("title") or ""},
        )

        for module_data in test_data.get("modules") or []:
            skill = module_data.get("kind")
            if skill not in (READING, LISTENING):
                continue
            _publish_module(test, skill, module_data, result)

    return result


def _publish_module(test: ExamTest, skill: str, data: dict, result: PublishResult) -> None:
    module, created = Module.objects.get_or_create(
        test=test, skill=skill,
        defaults={
            "duration_seconds": READING_SECONDS if skill == READING else 0,
            "transfer_seconds": 0 if skill == READING else LISTENING_TRANSFER_SECONDS,
        },
    )
    (result.created_modules if created else result.updated_modules).append(module.pk)

    # Replace the module's content wholesale. Questions are recreated rather than
    # diffed, but their (module, number) natural key is stable, so an attempt
    # answer keyed on question number still lines up after a re-import.
    kept_section_orders: list[int] = []

    for section_data in data.get("sections") or []:
        order = section_data.get("order") or (len(kept_section_orders) + 1)
        kept_section_orders.append(order)
        section, _ = Section.objects.update_or_create(
            module=module, order=order,
            defaults={
                "label": section_data.get("label") or "",
                "title": section_data.get("title") or "",
                "passage_html": section_data.get("passage_text") or "",
                "first_question": section_data.get("first_question") or 1,
                "last_question": section_data.get("last_question") or 1,
            },
        )

        section.groups.all().delete()
        for index, group_data in enumerate(section_data.get("groups") or [], start=1):
            _publish_group(module, section, index, group_data, result)

    Section.objects.filter(module=module).exclude(order__in=kept_section_orders).delete()

    numbers = set(module.questions.values_list("number", flat=True))
    module.total_questions = max(numbers) if numbers else 0
    module.save(update_fields=["total_questions", "updated_at"])

    _seed_answer_sheet(module, data, result)


def _seed_answer_sheet(module: Module, data: dict, result: PublishResult) -> None:
    """Pre-fill the answer grid from the book's own text layer.

    This is the best source available by a wide margin: on Cambridge 21 it reads
    40/40 on seven of the eight key pages, where OCR of the same pages as images
    manages about 13/40. The uploaded image is then what a human checks the grid
    against, and OCR only fills gaps for books with no text layer.

    It remains a proposal. `is_verified` stays False, so the module cannot be
    published until someone has actually looked.
    """
    proposal: dict[str, dict] = {}
    for section_data in data.get("sections") or []:
        for group_data in section_data.get("groups") or []:
            for question_data in group_data.get("questions") or []:
                key = question_data.get("answer_key")
                number = question_data.get("number")
                if not key or not number or not key.get("accepted"):
                    continue
                proposal[str(number)] = {
                    "kind": key.get("kind") or "text",
                    "accepted": list(key["accepted"]),
                    "word_limit": group_data.get("word_limit") or "",
                    "set_id": key.get("set_id"),
                    "set_numbers": list(key.get("set_numbers") or []),
                    "select_count": key.get("select_count"),
                }

    if not proposal:
        return

    sheet, _created = AnswerKeySheet.objects.get_or_create(module=module)
    if sheet.is_verified:
        # Never overwrite a key a human has already confirmed.
        result.warnings.append(
            f"module {module.pk}: answer sheet already verified, left untouched"
        )
        return

    merged = dict(sheet.answers or {})
    merged.update(proposal)
    sheet.answers = merged
    sheet.proposed_answers = dict(merged)
    sheet.proposal_source = "pdf"
    if not data.get("answer_key_reliable", True):
        sheet.warnings = (sheet.warnings or []) + [
            "the key pages for this module did not parse cleanly - check every "
            "answer against the sheet image"
        ]
    sheet.save()


def _publish_group(
    module: Module, section: Section, order: int, data: dict, result: PublishResult
) -> None:
    group = QuestionGroup.objects.create(
        section=section,
        order=order,
        type=data.get("type") or "unknown",
        instruction_text=data.get("instruction") or "",
        first_question=data.get("first_question") or 0,
        last_question=data.get("last_question") or 0,
        word_limit=data.get("word_limit") or "",
        select_count=data.get("select_count"),
        options=data.get("options") or [],
        options_reusable=bool(data.get("options_reusable")),
        layout=data.get("layout") or [],
        source_page=data.get("page_start"),
        source_bbox=data.get("source_bbox"),
        needs_review=bool(data.get("needs_review")),
        warnings=data.get("warnings") or [],
    )

    for index, question_data in enumerate(data.get("questions") or [], start=1):
        number = question_data.get("number")
        if not number:
            continue
        # update_or_create on (module, number): the same question may already
        # exist from a previous import, and re-using the row keeps its id.
        Question.objects.update_or_create(
            module=module, number=number,
            defaults={
                "group": group,
                "order": index,
                "prompt_text": question_data.get("prompt_text") or "",
                "options": question_data.get("options") or [],
            },
        )
        result.questions_written += 1
