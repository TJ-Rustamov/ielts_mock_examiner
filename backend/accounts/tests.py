from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class AuthAPITests(APITestCase):
    def test_register_login_me_logout(self):
        register = self.client.post(reverse("auth-register"), {"username": "demo", "password": "password123"}, format="json")
        self.assertEqual(register.status_code, status.HTTP_201_CREATED)
        token = register.data["token"]

        me = self.client.get(reverse("auth-me"), HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["username"], "demo")
        self.assertFalse(me.data["is_staff"])
        self.assertFalse(me.data["is_superuser"])

        login = self.client.post(reverse("auth-login"), {"username": "demo", "password": "password123"}, format="json")
        self.assertEqual(login.status_code, status.HTTP_200_OK)

        logout = self.client.post(reverse("auth-logout"), {}, format="json", HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(logout.status_code, status.HTTP_200_OK)
