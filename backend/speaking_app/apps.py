from django.apps import AppConfig


class SpeakingAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "speaking_app"
    label = "speaking"
    verbose_name = "Speaking"