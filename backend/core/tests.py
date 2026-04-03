from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient


class HealthCheckTests(SimpleTestCase):
    def test_health(self):
        response = APIClient().get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")