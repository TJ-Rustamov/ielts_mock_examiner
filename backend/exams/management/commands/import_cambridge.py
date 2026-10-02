"""Parse an IELTS book into a draft, without touching the database.

    python manage.py import_cambridge "/materials/cambridge21/Cambridge 21.pdf" \
        --book cambridge-21 --dry-run --out /app/data/c21-draft

``--dry-run`` writes the draft JSON plus a per-page text dump and a readable
report, and writes nothing to the database. It is meant to be run over and over
while the parsers are being tuned: re-running after a rule change costs seconds,
so the loop is "change a rule, re-run, read the report".

The report is the artefact to read first. It lists, per module, how many
questions were found, the question-type histogram, whether the answer key parsed
reliably, and every flagged group with the reason.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from exams.importer import pipeline


class Command(BaseCommand):
    help = "Parse an IELTS book PDF into a reviewable draft (use --dry-run first)."

    def add_arguments(self, parser):
        parser.add_argument("pdf", help="Path to the book PDF")
        parser.add_argument("--book", dest="slug", default="",
                            help="Book slug, e.g. cambridge-21")
        parser.add_argument("--dry-run", action="store_true", default=True,
                            help="Write files only; never touch the database (default)")
        parser.add_argument("--out", default="",
                            help="Output directory (default: alongside the PDF)")
        parser.add_argument("--first-page", type=int, default=None)
        parser.add_argument("--last-page", type=int, default=None)
        parser.add_argument("--no-ocr", dest="ocr", action="store_false", default=True,
                            help="Disable OCR. By default it runs on pages with no "
                                 "text layer and re-reads scanned answer-key pages")
        # Accepted for old scripts; OCR is on by default now.
        parser.add_argument("--ocr", dest="ocr", action="store_true", default=True,
                            help=argparse.SUPPRESS)

    def handle(self, *args, **options):
        pdf = options["pdf"]
        if not os.path.exists(pdf):
            raise CommandError(f"no such file: {pdf}")

        out_dir = options["out"] or os.path.join(
            os.path.dirname(os.path.abspath(pdf)), "_import"
        )
        os.makedirs(out_dir, exist_ok=True)

        ocr_engine = None
        if options["ocr"]:
            from exams.importer.ocr import try_get_engine

            ocr_engine, warning = try_get_engine()
            if warning:  # pragma: no cover - environment dependent
                self.stderr.write(self.style.WARNING(warning))

        result = pipeline.run(
            pdf,
            slug=options["slug"],
            ocr_engine=ocr_engine,
            first_page=options["first_page"],
            last_page=options["last_page"],
            progress=lambda message: self.stdout.write(f"  ... {message}"),
        )

        draft_path = os.path.join(out_dir, "draft.json")
        with open(draft_path, "w", encoding="utf-8") as handle:
            json.dump(result.payload, handle, ensure_ascii=False, indent=2)

        report = self._report(result)
        report_path = os.path.join(out_dir, "report.txt")
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(report)

        self.stdout.write("")
        self.stdout.write(report)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"draft  -> {draft_path}"))
        self.stdout.write(self.style.SUCCESS(f"report -> {report_path}"))
        if options["dry_run"]:
            self.stdout.write("dry run: nothing was written to the database.")

    # -- reporting ----------------------------------------------------------

    def _report(self, result: pipeline.ImportResult) -> str:
        lines: list[str] = []
        stats = result.stats
        lines.append("=" * 72)
        lines.append("IMPORT REPORT")
        lines.append("=" * 72)
        lines.append(
            f"pages {stats.get('pages', 0)}  "
            f"(text layer {stats.get('pages_with_text', 0)}, "
            f"scan with embedded OCR layer {stats.get('pages_embedded_ocr', 0)}, "
            f"needed OCR {stats.get('pages_ocr', 0)})"
        )
        lines.append(
            f"tests {stats.get('tests', 0)}   "
            f"question groups {stats.get('groups', 0)}   "
            f"flagged {stats.get('groups_flagged', 0)}"
        )
        lines.append("")

        for test in result.tests:
            for module in test["modules"]:
                numbers: list[int] = []
                types: Counter = Counter()
                flagged: list[tuple[str, list[str]]] = []
                with_key = 0
                for section in module["sections"]:
                    for group in section["groups"]:
                        types[group["type"]] += 1
                        label = (f"Q{group['first_question']}-{group['last_question']}"
                                 f" {group['type']}")
                        if group["needs_review"]:
                            flagged.append((label, group["warnings"]))
                        for question in group["questions"]:
                            numbers.append(question["number"])
                            if question.get("answer_key"):
                                with_key += 1

                unique = sorted(set(numbers))
                contiguous = unique == list(range(1, len(unique) + 1))
                key_ok = module.get("answer_key_reliable")
                key_label = (
                    "reliable" if key_ok else
                    ("UNRELIABLE" if key_ok is False else "not parsed")
                )

                lines.append(f"Test {test['number']} {module['kind'].upper()}")
                lines.append(
                    f"    questions {len(unique)}/40"
                    f"{'' if contiguous else '  NOT CONTIGUOUS'}"
                    f"    answers {with_key}/{len(unique) or 1}"
                    f"    key: {key_label}"
                )
                trust = module.get("trust")
                reads = module.get("key_reads") or {}
                if trust:
                    lines.append(
                        f"    self-check: {trust.get('trusted', 0)} trusted, "
                        f"{trust.get('check', 0)} to check, {trust.get('missing', 0)} missing"
                        f"    (key from {reads.get('source', '?')}, "
                        f"read: {', '.join(reads.get('reads', [])) or '-'})"
                    )
                lines.append(
                    "    types: "
                    + ", ".join(f"{name} x{count}" for name, count in types.most_common())
                )
                if flagged:
                    lines.append(f"    flagged groups ({len(flagged)}):")
                    for label, warnings in flagged:
                        lines.append(f"      - {label}")
                        for warning in warnings[:3]:
                            lines.append(f"          {warning}")
                lines.append("")

        if result.unmatched_instructions:
            lines.append("-" * 72)
            lines.append("UNRECOGNISED INSTRUCTIONS")
            lines.append(
                "Add phrasings for these to exams/importer/boilerplate.py - this is "
                "how a new book gets supported, without changing parser code."
            )
            for instruction in result.unmatched_instructions[:25]:
                lines.append(f"  - {instruction[:110]}")
            lines.append("")

        if result.warnings:
            lines.append("-" * 72)
            lines.append(f"WARNINGS ({len(result.warnings)})")
            for warning in result.warnings[:40]:
                lines.append(f"  - {warning[:140]}")
            if len(result.warnings) > 40:
                lines.append(f"  ... and {len(result.warnings) - 40} more")
        return "\n".join(lines)
