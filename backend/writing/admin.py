from django.contrib import admin

from writing.models import WritingEvaluation, WritingTopic


@admin.register(WritingEvaluation)
class WritingEvaluationAdmin(admin.ModelAdmin):
    list_display = ("id", "task_type", "author", "word_count", "created_at")
    list_filter = ("task_type", "created_at")
    search_fields = ("prompt", "essay_text", "author__username")


@admin.register(WritingTopic)
class WritingTopicAdmin(admin.ModelAdmin):
    list_display = ("id", "task_type", "title", "is_active", "created_at", "updated_at")
    list_filter = ("task_type", "is_active", "created_at")
    search_fields = ("title", "prompt")
