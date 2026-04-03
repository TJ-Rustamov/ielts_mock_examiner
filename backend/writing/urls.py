from django.urls import path

from writing.views import (
    AdminWritingTopicDetailAPIView,
    AdminWritingTopicListCreateAPIView,
    RandomWritingTopicAPIView,
    WritingEvaluateAPIView,
    WritingEvaluationDetailAPIView,
    WritingEvaluationListAPIView,
    WritingTopicImageUploadAPIView,
)

urlpatterns = [
    path("sessions", WritingEvaluationListAPIView.as_view(), name="writing-evaluate-list"),
    path("evaluate", WritingEvaluateAPIView.as_view(), name="writing-evaluate"),
    path("evaluate/<int:evaluation_id>", WritingEvaluationDetailAPIView.as_view(), name="writing-evaluate-detail"),
    path("upload-topic-image", WritingTopicImageUploadAPIView.as_view(), name="writing-upload-topic-image"),
    path("topics/random", RandomWritingTopicAPIView.as_view(), name="writing-topic-random"),
    path("admin/topics", AdminWritingTopicListCreateAPIView.as_view(), name="writing-admin-topic-list-create"),
    path("admin/topics/<int:topic_id>", AdminWritingTopicDetailAPIView.as_view(), name="writing-admin-topic-detail"),
]
