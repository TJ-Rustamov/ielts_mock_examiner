from django.db import models


class AIConfiguration(models.Model):
    provider = models.CharField(max_length=50, default="google")
    enabled_models = models.JSONField(default=list)
    writing_model = models.CharField(max_length=120, default="gemini-3.1-flash-lite-preview")
    speaking_model = models.CharField(max_length=120, default="gemini-3.1-flash-lite-preview")
    writing_prompt = models.TextField(blank=True, default="")
    speaking_prompt = models.TextField(blank=True, default="")
    temperature = models.FloatField(default=0.2)
    max_tokens = models.PositiveIntegerField(default=2048)
    streaming_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "AIConfiguration"


class SpeakingConfiguration(models.Model):
    tts_provider = models.CharField(max_length=50, default="kokoro")
    voice = models.CharField(max_length=100, default="af_heart")
    speed = models.FloatField(default=1.0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return "SpeakingConfiguration"


class SpeakingQuestion(models.Model):
    part = models.PositiveSmallIntegerField()
    question = models.TextField()
    follow_up = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["part", "-created_at"]

    def __str__(self) -> str:
        return f"SpeakingQuestion(id={self.id}, part={self.part})"
