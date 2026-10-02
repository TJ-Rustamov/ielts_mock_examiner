"""API tests for the attempt lifecycle, answer-key gating and key secrecy.

These need the database, so run them through Django:

    python manage.py test exams
"""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from exams.importer.publish import publish_payload
from exams.models import (
    AnswerKeySheet,
    Attempt,
    AttemptAnswer,
    Book,
    ExamTest,
    Module,
    Question,
    QuestionGroup,
    Section,
)

User = get_user_model()


def build_module(total=4, verified=True, published=True):
    book = Book.objects.create(slug="demo-book", title="Demo Book")
    test = ExamTest.objects.create(book=book, number=1)
    module = Module.objects.create(
        test=test, skill="reading", total_questions=total, duration_seconds=3600,
    )
    section = Section.objects.create(
        module=module, order=1, label="Reading Passage 1",
        first_question=1, last_question=total, passage_html="A short passage.",
    )
    group = QuestionGroup.objects.create(
        section=section, order=1, type="note_completion",
        first_question=1, last_question=total, word_limit="one_word",
        layout=[{"kind": "line", "text": " ".join(f"{{{{Q{n}}}}}" for n in range(1, total + 1))}],
    )
    for number in range(1, total + 1):
        Question.objects.create(module=module, group=group, number=number)
    answers = {str(n): {"kind": "text", "accepted": [f"secret{n}"]} for n in range(1, total + 1)}
    AnswerKeySheet.objects.create(
        module=module, answers=answers, proposed_answers=answers, is_verified=verified,
    )
    module.is_published = published
    module.save()
    return module


class AttemptLifecycleTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user("student", password="pass-12345")
        self.client.force_authenticate(self.student)
        self.module = build_module()

    def start(self):
        response = self.client.post(
            f"/api/exams/modules/{self.module.pk}/attempts", {"mode": "exam"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def test_content_never_contains_the_answer_key(self):
        payload = json.dumps(self.start().data)
        self.assertNotIn("accepted", payload)
        self.assertNotIn("answer_key", payload)
        self.assertNotIn("secret1", payload)

    def test_starting_twice_returns_the_same_attempt(self):
        first = self.start().data["attempt"]["id"]
        second = self.start().data["attempt"]["id"]
        self.assertEqual(first, second)

    def test_result_is_hidden_until_submission(self):
        attempt_id = self.start().data["attempt"]["id"]
        response = self.client.get(f"/api/exams/attempts/{attempt_id}/result")
        self.assertEqual(response.status_code, 403)

    def test_submit_marks_and_bands(self):
        attempt_id = self.start().data["attempt"]["id"]
        answers = [
            {"question_number": 1, "value": {"text": "SECRET1 "}},   # case and space ignored
            {"question_number": 2, "value": {"text": "secret2"}},
            {"question_number": 3, "value": {"text": "the secret3"}},  # over ONE WORD ONLY
        ]
        saved = self.client.patch(
            f"/api/exams/attempts/{attempt_id}/answers", {"answers": answers}, format="json",
        )
        self.assertEqual(saved.data["saved"], 3)

        result = self.client.post(f"/api/exams/attempts/{attempt_id}/submit").data
        self.assertEqual(result["raw_score"], 2)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["blank"], 1)
        reasons = {row["number"]: row["reason"] for row in result["rows"]}
        self.assertEqual(reasons[3], "over_word_limit")
        self.assertEqual(reasons[4], "blank")
        # Keys are revealed only now, after submission.
        self.assertEqual(result["rows"][0]["accepted"], ["secret1"])

    def test_double_submit_is_rejected(self):
        attempt_id = self.start().data["attempt"]["id"]
        self.client.post(f"/api/exams/attempts/{attempt_id}/submit")
        again = self.client.post(f"/api/exams/attempts/{attempt_id}/submit")
        self.assertEqual(again.status_code, 409)

    def test_questions_remain_viewable_after_submission(self):
        attempt_id = self.start().data["attempt"]["id"]
        self.client.post(f"/api/exams/attempts/{attempt_id}/submit")
        detail = self.client.get(f"/api/exams/attempts/{attempt_id}").data
        self.assertIn("content", detail)
        self.assertNotIn("secret1", json.dumps(detail))

    def test_answers_cannot_be_saved_after_submission(self):
        attempt_id = self.start().data["attempt"]["id"]
        self.client.post(f"/api/exams/attempts/{attempt_id}/submit")
        response = self.client.patch(
            f"/api/exams/attempts/{attempt_id}/answers",
            {"answers": [{"question_number": 1, "value": {"text": "x"}}]}, format="json",
        )
        self.assertEqual(response.status_code, 409)

    def test_another_users_attempt_is_not_found(self):
        attempt_id = self.start().data["attempt"]["id"]
        intruder = User.objects.create_user("intruder", password="pass-12345")
        self.client.force_authenticate(intruder)
        self.assertEqual(self.client.get(f"/api/exams/attempts/{attempt_id}").status_code, 404)


class PublicationGateTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin-user", password="pass-12345", is_staff=True)

    def test_unverified_key_blocks_students(self):
        module = build_module(verified=False, published=True)
        student = User.objects.create_user("student", password="pass-12345")
        self.client.force_authenticate(student)
        response = self.client.post(f"/api/exams/modules/{module.pk}/attempts", {}, format="json")
        self.assertEqual(response.status_code, 409)

    def test_admin_cannot_publish_an_unverified_module(self):
        module = build_module(verified=False, published=False)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/exams/admin/modules/{module.pk}", {"is_published": True}, format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("not been verified", response.data["message"])

    def test_unpublished_modules_are_not_listed(self):
        build_module(verified=True, published=False)
        student = User.objects.create_user("student", password="pass-12345")
        self.client.force_authenticate(student)
        self.assertEqual(self.client.get("/api/exams/tests").data["tests"], [])

    def test_students_cannot_use_admin_endpoints(self):
        module = build_module()
        student = User.objects.create_user("student", password="pass-12345")
        self.client.force_authenticate(student)
        response = self.client.get(f"/api/exams/admin/modules/{module.pk}/answer-sheet")
        self.assertEqual(response.status_code, 403)


class AnswerGridTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin-user", password="pass-12345", is_staff=True)
        self.client.force_authenticate(self.admin)
        self.module = build_module(verified=True)

    def patch_grid(self, answers):
        return self.client.patch(
            f"/api/exams/admin/modules/{self.module.pk}/answer-sheet",
            {"answers": answers}, format="json",
        )

    def test_typed_true_false_keeps_its_kind(self):
        # Stored as plain text, "TRUE" would reject a candidate's "T".
        self.patch_grid({"1": "TRUE", "2": "B", "3": "10 / ten"})
        sheet = AnswerKeySheet.objects.get(module=self.module)
        self.assertEqual(sheet.answers["1"]["kind"], "tfng")
        self.assertEqual(sheet.answers["2"]["kind"], "letter")
        self.assertEqual(sheet.answers["3"]["accepted"], ["10", "ten"])

    def test_any_edit_clears_verification(self):
        self.patch_grid({"1": "changed"})
        self.assertFalse(AnswerKeySheet.objects.get(module=self.module).is_verified)

    def test_verify_refuses_an_incomplete_grid(self):
        self.patch_grid({"1": "only one"})
        response = self.client.post(
            f"/api/exams/admin/modules/{self.module.pk}/answer-sheet/verify",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "incomplete")

    def test_verifying_a_changed_key_remarks_existing_attempts(self):
        student = User.objects.create_user("student", password="pass-12345")
        self.client.force_authenticate(student)
        attempt_id = self.client.post(
            f"/api/exams/modules/{self.module.pk}/attempts", {}, format="json",
        ).data["attempt"]["id"]
        self.client.patch(
            f"/api/exams/attempts/{attempt_id}/answers",
            {"answers": [{"question_number": 1, "value": {"text": "corrected"}}]}, format="json",
        )
        self.assertEqual(
            self.client.post(f"/api/exams/attempts/{attempt_id}/submit").data["raw_score"], 0,
        )

        self.client.force_authenticate(self.admin)
        self.patch_grid({str(n): ("corrected" if n == 1 else f"secret{n}") for n in range(1, 5)})
        verified = self.client.post(
            f"/api/exams/admin/modules/{self.module.pk}/answer-sheet/verify",
        ).data
        self.assertEqual(verified["remarked_attempts"], 1)

        self.client.force_authenticate(student)
        result = self.client.get(f"/api/exams/attempts/{attempt_id}/result").data
        self.assertEqual(result["raw_score"], 1)


def book_payload(numbers):
    return {
        "book": {"slug": "republish-book", "title": "Republish Book"},
        "tests": [{
            "number": 1,
            "modules": [{
                "kind": "reading",
                "sections": [{
                    "order": 1,
                    "label": "Reading Passage 1",
                    "groups": [{
                        "type": "note_completion",
                        "instruction": "Complete the notes below.",
                        "first_question": min(numbers),
                        "last_question": max(numbers),
                        "word_limit": "one_word",
                        "layout": [],
                        "questions": [
                            {"number": n, "answer_key": {"kind": "text", "accepted": [f"w{n}"]}}
                            for n in numbers
                        ],
                    }],
                }],
            }],
        }],
    }


class RepublishTests(APITestCase):
    """Re-importing a book must never touch what students have already done."""

    def setUp(self):
        publish_payload(book_payload([1, 2]))
        self.module = Module.objects.get(test__book__slug="republish-book")
        student = User.objects.create_user("student", password="pass-12345")
        self.attempt = Attempt.objects.create(
            user=student, module=self.module,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.question = Question.objects.get(module=self.module, number=1)
        AttemptAnswer.objects.create(
            attempt=self.attempt, question=self.question,
            question_number=1, value={"text": "w1"},
        )

    def test_republishing_keeps_saved_answers_and_question_ids(self):
        publish_payload(book_payload([1, 2]))
        self.assertEqual(AttemptAnswer.objects.filter(attempt=self.attempt).count(), 1)
        self.assertEqual(Question.objects.get(module=self.module, number=1).pk, self.question.pk)

    def test_an_answered_question_dropped_from_the_import_is_kept(self):
        result = publish_payload(book_payload([2]))
        self.assertTrue(Question.objects.filter(pk=self.question.pk).exists())
        self.assertEqual(AttemptAnswer.objects.filter(attempt=self.attempt).count(), 1)
        self.assertTrue(any("students have answered" in w for w in result.warnings))

    def test_an_unanswered_question_dropped_from_the_import_is_removed(self):
        publish_payload(book_payload([1]))
        self.assertFalse(Question.objects.filter(module=self.module, number=2).exists())
