from django.urls import path

from speaking_app.views import SpeakingSessionDetailAPIView, SpeakingSessionListAPIView

urlpatterns = [
    path("sessions", SpeakingSessionListAPIView.as_view(), name="speaking-session-list"),
    path("sessions/<int:session_id>", SpeakingSessionDetailAPIView.as_view(), name="speaking-session-detail"),
]

