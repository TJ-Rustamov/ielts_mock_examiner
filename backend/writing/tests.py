from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from writing.models import WritingEvaluation, WritingTopic


class WritingEvaluateAPITests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="writer", password="secret123")
        token = Token.objects.create(user=user)
        self.auth_header = {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    @patch("writing.views.GeminiClient.evaluate_writing")
    def test_evaluate_writing_success_and_persistence(self, mock_eval):
        mock_eval.return_value = {
            "scores": {"tr": 7.0, "cc": 6.5, "lr": 7.0, "gra": 6.5, "overall_band": 6.8},
            "examiner_comments": "Well developed argument.",
            "corrections": [{"error": "bad phrase", "correction": "better phrase"}],
            "word_count": 260,
        }

        payload = {
            "task_type": "task2",
            "prompt": "Discuss whether technology improves education.",
            "essay": "word " * 260,
        }
        response = self.client.post(reverse("writing-evaluate"), data=payload, format="json", **self.auth_header)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WritingEvaluation.objects.count(), 1)
        saved = WritingEvaluation.objects.first()
        self.assertEqual(saved.task_type, "task2")
        self.assertEqual(saved.scores["overall_band"], 6.8)
        detail = self.client.get(reverse("writing-evaluate-detail", kwargs={"evaluation_id": saved.id}), **self.auth_header)
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["id"], saved.id)

    def test_evaluate_requires_auth(self):
        payload = {"task_type": "task2", "prompt": "x", "essay": "word " * 260}
        response = self.client.post(reverse("writing-evaluate"), data=payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("writing.views.GeminiClient.evaluate_writing")
    def test_evaluate_writing_llm_error(self, mock_eval):
        mock_eval.side_effect = RuntimeError("Gemini timeout")

        payload = {
            "task_type": "task1",
            "prompt": "Describe the chart.",
            "essay": "word " * 160,
        }
        response = self.client.post(reverse("writing-evaluate"), data=payload, format="json", **self.auth_header)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["error"], "llm_evaluation_failed")


class WritingTopicModelTests(APITestCase):
    def test_task1_requires_image(self):
        topic = WritingTopic(task_type="task1", title="Bar chart", prompt="Describe the chart.")
        with self.assertRaises(ValidationError):
            topic.full_clean()

    def test_task2_clears_image(self):
        topic = WritingTopic.objects.create(
            task_type="task2",
            title="Essay prompt",
            prompt="Some people think...",
            topic_image_url="https://example.com/image.png",
        )
        self.assertIsNone(topic.topic_image_url)


class WritingTopicAPITests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="student", password="secret123")
        self.admin = user_model.objects.create_user(
            username="admin",
            password="secret123",
            is_staff=True,
            is_superuser=True,
        )

        self.user_token = Token.objects.create(user=self.user)
        self.admin_token = Token.objects.create(user=self.admin)
        self.user_auth = {"HTTP_AUTHORIZATION": f"Token {self.user_token.key}"}
        self.admin_auth = {"HTTP_AUTHORIZATION": f"Token {self.admin_token.key}"}

    def test_admin_endpoints_require_admin(self):
        response = self.client.get(reverse("writing-admin-topic-list-create"), **self.user_auth)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        payload = {
            "task_type": "task2",
            "title": "Technology and education",
            "prompt": "To what extent do you agree?",
            "is_active": True,
        }
        response = self.client.post(reverse("writing-admin-topic-list-create"), payload, format="json", **self.user_auth)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_crud_topics(self):
        create_payload = {
            "task_type": "task1",
            "title": "Bar chart",
            "topic_image_url": "https://example.com/chart.png",
            "is_active": True,
        }
        created = self.client.post(reverse("writing-admin-topic-list-create"), create_payload, format="json", **self.admin_auth)
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        topic_id = created.data["id"]
        self.assertEqual(created.data["prompt"], "Bar chart")

        listed = self.client.get(f"{reverse('writing-admin-topic-list-create')}?task_type=task1", **self.admin_auth)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data["results"]), 1)

        patched = self.client.patch(
            reverse("writing-admin-topic-detail", kwargs={"topic_id": topic_id}),
            {"is_active": False},
            format="json",
            **self.admin_auth,
        )
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        self.assertFalse(patched.data["is_active"])

        deleted = self.client.delete(reverse("writing-admin-topic-detail", kwargs={"topic_id": topic_id}), **self.admin_auth)
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

    def test_random_topic_task1_requires_active_with_image(self):
        WritingTopic.objects.create(task_type="task1", title="B", prompt="B", topic_image_url="https://example.com/b.png", is_active=False)
        valid = WritingTopic.objects.create(
            task_type="task1",
            title="C",
            prompt="C",
            topic_image_url="https://example.com/c.png",
            is_active=True,
        )

        response = self.client.get(f"{reverse('writing-topic-random')}?task_type=task1", **self.user_auth)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], valid.id)
        self.assertTrue(response.data["topic_image_url"])

    def test_random_topic_task2_works_without_image(self):
        topic = WritingTopic.objects.create(task_type="task2", title="Essay", prompt="Discuss both views.", is_active=True)
        response = self.client.get(f"{reverse('writing-topic-random')}?task_type=task2", **self.user_auth)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], topic.id)
        self.assertIsNone(response.data["topic_image_url"])

    def test_random_topic_returns_404_when_empty(self):
        response = self.client.get(f"{reverse('writing-topic-random')}?task_type=task2", **self.user_auth)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
