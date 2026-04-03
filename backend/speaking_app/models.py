from django.db import models


class SpeakingSession(models.Model):
    part = models.CharField(max_length=10, default="all")
    candidate_metadata = models.JSONField(default=dict)

    transcript = models.TextField(blank=True)
    conversation_history = models.JSONField(default=list)

    scores = models.JSONField(default=dict)
    final_report = models.JSONField(default=dict)

    status = models.CharField(max_length=20, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"SpeakingSession(id={self.id}, status={self.status})"