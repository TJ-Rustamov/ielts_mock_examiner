import io
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import SpeakingQuestion


class HealthCheckTests(SimpleTestCase):
    def test_health(self):
        response = APIClient().get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


SAMPLE = {
    "part1": [{"id": 1, "topic": "Hometown", "questions": [{"id": 1, "text": "Where is your hometown?"}]}],
    "part2": [{"id": 1, "topic": "A book", "cue_card": "Describe a book you read. You should say:",
               "points": [{"id": 1, "text": "what it is"}]}],
    "part3": [{"id": 1, "topic": "A book", "questions": [{"id": 1, "text": "Do people read less now?"}]}],
}


class LoadSpeakingQuestionsTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "sample_tests.json"
        self.path.write_text(json.dumps(SAMPLE), encoding="utf-8")

    def tearDown(self):
        self.folder.cleanup()

    def load(self, *args):
        call_command("load_speaking_questions", str(self.path), *args, stdout=io.StringIO())

    def test_loads_every_part(self):
        self.load()
        self.assertEqual(sorted(SpeakingQuestion.objects.values_list("part", flat=True)), [1, 2, 3])
        card = SpeakingQuestion.objects.get(part=2)
        self.assertEqual(card.points[0]["text"], "what it is")

    def test_running_again_adds_nothing(self):
        self.load()
        self.load()
        self.assertEqual(SpeakingQuestion.objects.count(), 3)

    def test_replace_clears_hand_added_questions(self):
        SpeakingQuestion.objects.create(part=1, topic="Added by hand", questions=["?"])
        self.load("--replace")
        self.assertFalse(SpeakingQuestion.objects.filter(topic="Added by hand").exists())
        self.assertEqual(SpeakingQuestion.objects.count(), 3)

    def test_the_shipped_files_load(self):
        """The real files in question_bank/speaking parse and load cleanly."""
        call_command("load_speaking_questions", stdout=io.StringIO())
        self.assertGreater(SpeakingQuestion.objects.filter(part=2).count(), 100)
        self.assertFalse(SpeakingQuestion.objects.filter(part=2, points=[]).exists())
