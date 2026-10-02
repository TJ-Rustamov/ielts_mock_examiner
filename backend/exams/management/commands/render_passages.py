"""Re-crop reading passage pages for a book that is already imported.

    python manage.py render_passages "/materials/cambridge21/Cambridge 21.pdf" --book cambridge-21

Only the passage images are replaced. Questions, answer sheets and attempts are
not touched, so this is safe to run on a book students are already using.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exams.importer import pipeline
from exams.importer.publish import publish_passage_pages
from exams.models import READING, Section


class Command(BaseCommand):
    help = "Render reading passage pages from the book PDF for an imported book."

    def add_arguments(self, parser):
        parser.add_argument("pdf", help="Path to the book PDF")
        parser.add_argument("--book", dest="slug", required=True, help="Book slug, e.g. cambridge-21")
        parser.add_argument("--ocr", action="store_true", default=False,
                            help="Enable OCR for pages with no text layer")

    def handle(self, *args, **options):
        pdf = options["pdf"]
        if not os.path.exists(pdf):
            raise CommandError(f"no such file: {pdf}")

        ocr_engine = None
        if options["ocr"]:
            from exams.importer.ocr import get_engine

            ocr_engine = get_engine()

        result = pipeline.run(pdf, slug=options["slug"], ocr_engine=ocr_engine,
                              progress=lambda message: self.stdout.write(f"  ... {message}"))

        for test in result.tests:
            for module in test["modules"]:
                if module["kind"] != READING:
                    continue
                for section_data in module["sections"]:
                    section = Section.objects.filter(
                        module__test__book__slug=options["slug"],
                        module__test__number=test["number"],
                        module__skill=READING,
                        order=section_data["order"],
                    ).select_related("module__test__book").first()
                    label = f"Test {test['number']} Passage {section_data['order']}"
                    if section is None:
                        self.stdout.write(self.style.WARNING(f"{label}: not in the database, skipped"))
                        continue
                    with transaction.atomic():
                        written, warnings = publish_passage_pages(
                            section, section_data.get("passage_regions") or [], pdf
                        )
                    pages = ", ".join(str(r["page"]) for r in section_data.get("passage_regions") or [])
                    self.stdout.write(f"{label}: {written} page image(s) from PDF page(s) {pages or '-'}")
                    for warning in warnings:
                        self.stdout.write(self.style.WARNING(f"    {warning}"))
