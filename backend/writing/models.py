from django.db import models
from django.core.exceptions import ValidationError


class WritingEvaluation(models.Model):
    TASK_CHOICES = (("task1", "Task 1"), ("task2", "Task 2"))

    task_type = models.CharField(max_length=10, choices=TASK_CHOICES)
    author = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="writing_evaluations")
    prompt = models.TextField()
    essay_text = models.TextField()
    topic_image_url = models.URLField(blank=True, null=True)

    scores = models.JSONField(default=dict)
    examiner_comments = models.TextField(blank=True)
    corrections = models.JSONField(default=list)
    criteria_feedback = models.JSONField(default=dict)
    inline_suggestions = models.JSONField(default=list)
    band_essays = models.JSONField(default=dict)
    band_essays_status = models.CharField(max_length=20, default="pending")
    band_essays_error = models.TextField(blank=True)
    word_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"WritingEvaluation(id={self.id}, task_type={self.task_type})"


class WritingTopic(models.Model):
    TASK_CHOICES = (("task1", "Task 1"), ("task2", "Task 2"))

    task_type = models.CharField(max_length=10, choices=TASK_CHOICES)
    title = models.CharField(max_length=255)
    prompt = models.TextField()
    topic_image_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        image_url = (self.topic_image_url or "").strip()
        if self.task_type == "task1" and not image_url:
            raise ValidationError({"topic_image_url": "Task 1 topics require an image."})
        if self.task_type == "task2":
            self.topic_image_url = None

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"WritingTopic(id={self.id}, task_type={self.task_type}, title={self.title})"
