"""Load the speaking question bank from JSON files.

    python manage.py load_speaking_questions              # every *_tests.json in question_bank/speaking
    python manage.py load_speaking_questions a.json b.json
    python manage.py load_speaking_questions --replace    # clear the bank first, then load

The files have the shape the parsers in question_bank/speaking write, which is
also what Admin > Speaking Questions > Import accepts:

    {"part1": [{"topic", "questions": [{"id", "text"}]}],
     "part2": [{"topic", "cue_card", "points": [{"id", "text"}]}],
     "part3": [{"topic", "questions": [...]}]}

Safe to run again: an entry already in the bank is skipped, not duplicated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import SpeakingQuestion

DEFAULT_FOLDER = Path(settings.BASE_DIR) / "question_bank" / "speaking"
PARTS = (("part1", 1), ("part2", 2), ("part3", 3))


def _norm(text) -> str:
    return re.sub(r"\W+", " ", str(text or "")).strip().lower()


def _identity(part: int, topic, questions, cue_card) -> tuple:
    """What makes two entries the same, ignoring case, spacing and punctuation."""
    if part == 2:
        return (2, _norm(cue_card))
    texts = [q.get("text", "") if isinstance(q, dict) else q for q in questions or []]
    return (part, _norm(topic), _norm(" ".join(map(str, texts))))


class Command(BaseCommand):
    help = "Load speaking questions (Part 1/2/3) from JSON files into the question bank."

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="*",
                            help=f"JSON files (default: every *_tests.json in {DEFAULT_FOLDER})")
        parser.add_argument("--replace", action="store_true",
                            help="Delete every speaking question first, including ones added by hand")

    @transaction.atomic
    def handle(self, *args, **options):
        files = [Path(f) for f in options["files"]] or sorted(DEFAULT_FOLDER.glob("*_tests.json"))
        if not files:
            raise CommandError(f"no question files found in {DEFAULT_FOLDER}")
        for path in files:
            if not path.exists():
                raise CommandError(f"no such file: {path}")

        if options["replace"]:
            removed, _ = SpeakingQuestion.objects.all().delete()
            self.stdout.write(f"removed {removed} existing question(s)")

        seen = {
            _identity(row.part, row.topic, row.questions, row.cue_card)
            for row in SpeakingQuestion.objects.all()
        }

        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise CommandError(f"{path.name} is not valid JSON: {exc}") from exc

            added = skipped = 0
            for key, part in PARTS:
                for item in data.get(key) or []:
                    identity = _identity(part, item.get("topic"), item.get("questions"),
                                         item.get("cue_card"))
                    if identity in seen:
                        skipped += 1
                        continue
                    seen.add(identity)
                    SpeakingQuestion.objects.create(
                        part=part,
                        topic=item.get("topic") or "General",
                        questions=item.get("questions") or [],
                        cue_card=item.get("cue_card") or "",
                        points=item.get("points") or [],
                        is_active=True,
                    )
                    added += 1
            self.stdout.write(f"{path.name}: added {added}, skipped {skipped} already in the bank")

        for _key, part in PARTS:
            entries = SpeakingQuestion.objects.filter(part=part, is_active=True)
            self.stdout.write(
                f"part {part}: {entries.count()} active, "
                f"{entries.values('topic').distinct().count()} topics"
            )
