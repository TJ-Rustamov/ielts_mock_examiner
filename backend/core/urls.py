from django.urls import path

from core.views import (
    AIConfigurationAPIView,
    AdminOverviewAPIView,
    AdminUserDetailAPIView,
    AdminUserListCreateAPIView,
    SpeakingConfigurationAPIView,
    SpeakingQuestionDetailAPIView,
    SpeakingQuestionListCreateAPIView,
    SpeakingQuestionImportAPIView,
    TTSPreviewAPIView,
    health_check,
)

urlpatterns = [
    path("health", health_check, name="health"),
    path("admin/overview", AdminOverviewAPIView.as_view(), name="admin-overview"),
    path("admin/users", AdminUserListCreateAPIView.as_view(), name="admin-users-list-create"),
    path("admin/users/<int:user_id>", AdminUserDetailAPIView.as_view(), name="admin-users-detail"),
    path("admin/ai-config", AIConfigurationAPIView.as_view(), name="admin-ai-config"),
    path("admin/speaking-config", SpeakingConfigurationAPIView.as_view(), name="admin-speaking-config"),
    path("admin/speaking-questions", SpeakingQuestionListCreateAPIView.as_view(), name="admin-speaking-question-list-create"),
    path("admin/speaking-questions/import", SpeakingQuestionImportAPIView.as_view(), name="admin-speaking-question-import"),
    path("admin/speaking-questions/<int:question_id>", SpeakingQuestionDetailAPIView.as_view(), name="admin-speaking-question-detail"),
    path("admin/tts/preview", TTSPreviewAPIView.as_view(), name="admin-tts-preview"),
]
