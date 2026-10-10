from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar_url = models.TextField(blank=True, null=True)
    #: The user's own test-security switches; see accounts.security for the
    #: keys and their defaults. Only keys the user has changed are stored.
    security_settings = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.user.username + " Profile"
