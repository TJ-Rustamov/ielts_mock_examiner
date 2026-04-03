from django.contrib import admin

from core.models import AIConfiguration, SpeakingConfiguration, SpeakingQuestion


@admin.register(AIConfiguration)
class AIConfigurationAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "writing_model", "speaking_model", "updated_at")


@admin.register(SpeakingConfiguration)
class SpeakingConfigurationAdmin(admin.ModelAdmin):
    list_display = ("id", "tts_provider", "voice", "speed", "updated_at")


@admin.register(SpeakingQuestion)
class SpeakingQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "part", "is_active", "updated_at")
    list_filter = ("part", "is_active")
    search_fields = ("question", "follow_up")
