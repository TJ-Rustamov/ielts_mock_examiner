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


class SecuritySettingsAPITests(APITestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user("student", password="password123")
        self.client.force_authenticate(self.user)
        self.url = reverse("auth-security-settings")

    def test_everything_is_on_until_the_user_changes_it(self):
        settings = self.client.get(self.url).data["settings"]
        self.assertEqual(set(settings), {
            "leave_window_cancels_speaking", "count_leaving_window",
            "block_copying", "warn_before_leaving_page",
        })
        self.assertTrue(all(settings.values()))

    def test_a_change_is_saved_and_the_rest_keep_their_defaults(self):
        response = self.client.patch(
            self.url, {"settings": {"leave_window_cancels_speaking": False}}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        settings = self.client.get(self.url).data["settings"]
        self.assertFalse(settings["leave_window_cancels_speaking"])
        self.assertTrue(settings["block_copying"])

    def test_unknown_keys_and_non_booleans_are_rejected(self):
        for bad in ({"made_up": True}, {"block_copying": "no"}):
            response = self.client.patch(self.url, {"settings": bad}, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(self.client.get(self.url).data["settings"]["block_copying"])

    def test_settings_are_per_user(self):
        from django.contrib.auth import get_user_model

        self.client.patch(self.url, {"settings": {"block_copying": False}}, format="json")
        other = get_user_model().objects.create_user("other", password="password123")
        self.client.force_authenticate(other)
        self.assertTrue(self.client.get(self.url).data["settings"]["block_copying"])

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
