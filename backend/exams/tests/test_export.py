"""The JSON export: complete, and publishable back into the database."""

import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from exams.importer.publish import publish_payload
from exams.management.commands.export_exams import export_book
from exams.models import AnswerKeySheet, Book, Module
from exams.tests.test_api import build_module


class ExportTests(TestCase):
    def setUp(self):
        self.module = build_module(total=4)
        self.book = self.module.test.book

    def test_export_carries_questions_and_confirmed_keys(self):
        data = export_book(self.book, "reading")
        module = data["tests"][0]["modules"][0]
        self.assertEqual(data["format"], "ielts-exams/v1")
        self.assertTrue(module["answer_key_verified"])
        questions = module["sections"][0]["groups"][0]["questions"]
        self.assertEqual([q["number"] for q in questions], [1, 2, 3, 4])
        self.assertEqual(questions[0]["answer_key"]["accepted"], ["secret1"])
        self.assertEqual(module["sections"][0]["passage_text"], "A short passage.")

    def test_a_skill_the_book_lacks_is_not_exported(self):
        self.assertIsNone(export_book(self.book, "listening"))

    def test_an_export_publishes_back_into_the_database(self):
        data = export_book(self.book, "reading")
        data["book"]["slug"] = "demo-copy"
        publish_payload(data)

        copy = Module.objects.get(test__book__slug="demo-copy", skill="reading")
        self.assertEqual(copy.questions.count(), 4)
        sheet = AnswerKeySheet.objects.get(module=copy)
        self.assertEqual(sheet.answers["2"]["accepted"], ["secret2"])
        # A republished key is a proposal: a person confirms it again.
        self.assertFalse(sheet.is_verified)

    def test_command_writes_one_file_per_book_and_skill(self):
        with tempfile.TemporaryDirectory() as out:
            call_command("export_exams", "--out", out, stdout=io.StringIO())
            files = sorted(p.relative_to(out).as_posix() for p in Path(out).rglob("*.json"))
            self.assertEqual(files, [f"reading/{self.book.slug}.json"])
            data = json.loads((Path(out) / files[0]).read_text(encoding="utf-8"))
            self.assertEqual(data["book"]["slug"], self.book.slug)

    def test_unknown_book_is_an_error(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("export_exams", "--book", "no-such-book")
        self.assertTrue(Book.objects.filter(slug=self.book.slug).exists())
