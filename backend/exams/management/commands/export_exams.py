"""Export Reading and Listening tests from the database to raw JSON.

    python manage.py export_exams                       # every book
    python manage.py export_exams --book cambridge-19   # one book (repeatable)
    python manage.py export_exams --out /tmp/exports

Writes one file per book and skill:

    question_bank/reading/<book>.json
    question_bank/listening/<book>.json

The shape is the importer's draft payload (see exams.importer.pipeline), so an
export can be published back with exams.importer.publish.publish_payload - for
example into a fresh database, without re-running OCR on the book. Each
question carries the module's *confirmed* answer key; answer sheets still come
back unverified after such a publish, so a person confirms them again.

These files hold the books' full passages and answer keys, which is why the
question_bank/reading and question_bank/listening folders are not committed.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from exams.models import LISTENING, READING, Book, Module

FORMAT = "ielts-exams/v1"
DEFAULT_OUT = Path(settings.BASE_DIR) / "question_bank"


def _module_payload(module: Module) -> dict:
    sheet = getattr(module, "answer_sheet", None)
    keys = (sheet.answers or {}) if sheet else {}

    sections = []
    for section in module.sections.all().prefetch_related("groups__questions", "passage_pages"):
        section_data = {
            "order": section.order,
            "label": section.label,
            "title": section.title,
            "first_question": section.first_question,
            "last_question": section.last_question,
            "groups": [],
        }
        if module.skill == READING:
            section_data["passage_text"] = section.passage_html
            section_data["passage_pages"] = [
                {"page": page.source_page, "bbox": page.bbox, "file": Path(page.image.name).name}
                for page in section.passage_pages.all()
            ]
        else:
            section_data["audio"] = (
                {"file": section.audio.original_filename,
                 "duration_seconds": section.audio.duration_seconds}
                if section.audio_id else None
            )

        for group in section.groups.all():
            section_data["groups"].append({
                "type": group.type,
                "instruction": group.instruction_text,
                "first_question": group.first_question,
                "last_question": group.last_question,
                "word_limit": group.word_limit,
                "select_count": group.select_count,
                "options": group.options,
                "options_reusable": group.options_reusable,
                "layout": group.layout,
                "page_start": group.source_page,
                "questions": [
                    {
                        "number": question.number,
                        "prompt_text": question.prompt_text,
                        "options": question.options,
                        "answer_key": keys.get(str(question.number)),
                    }
                    for question in group.questions.all()
                ],
            })
        sections.append(section_data)

    return {
        "kind": module.skill,
        "total_questions": module.total_questions,
        "duration_seconds": module.duration_seconds,
        "transfer_seconds": module.transfer_seconds,
        "is_published": module.is_published,
        "answer_key_verified": bool(sheet and sheet.is_verified),
        "sections": sections,
    }


def export_book(book: Book, skill: str) -> dict | None:
    """One book's tests for one skill, or None if the book has none."""
    tests = []
    for test in book.tests.all().order_by("number"):
        module = (
            test.modules.filter(skill=skill)
            .select_related("answer_sheet")
            .first()
        )
        if module is not None:
            tests.append({"number": test.number, "title": test.title,
                          "modules": [_module_payload(module)]})
    if not tests:
        return None
    return {
        "format": FORMAT,
        "exported_at": timezone.now().isoformat(),
        "book": {"slug": book.slug, "title": book.title, "variant": book.variant,
                 "publisher": book.publisher, "year": book.year},
        "tests": tests,
    }


class Command(BaseCommand):
    help = "Export Reading and Listening tests to raw JSON files, one per book and skill."

    def add_arguments(self, parser):
        parser.add_argument("--book", action="append", dest="books", default=[],
                            help="Book slug to export (repeatable). Default: every book")
        parser.add_argument("--out", default=str(DEFAULT_OUT),
                            help=f"Output folder (default: {DEFAULT_OUT})")

    def handle(self, *args, **options):
        books = Book.objects.all().order_by("slug")
        if options["books"]:
            books = books.filter(slug__in=options["books"])
            missing = set(options["books"]) - set(books.values_list("slug", flat=True))
            if missing:
                raise CommandError(f"no such book: {', '.join(sorted(missing))}")

        out = Path(options["out"])
        written = 0
        for book in books:
            for skill in (READING, LISTENING):
                data = export_book(book, skill)
                if data is None:
                    continue
                folder = out / skill
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{book.slug}.json"
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                questions = sum(
                    len(group["questions"])
                    for t in data["tests"] for m in t["modules"]
                    for s in m["sections"] for group in s["groups"]
                )
                self.stdout.write(
                    f"{path}  {len(data['tests'])} test(s), {questions} questions, "
                    f"{path.stat().st_size // 1024} KB"
                )
                written += 1
        if not written:
            self.stdout.write("nothing to export")
