from django.urls import path

from speaking_app.views import SpeakingSessionDetailAPIView, SpeakingSessionListAPIView, SpeakingTurnRewriteAPIView, TTSSynthesizeAPIView

urlpatterns = [
    path("sessions", SpeakingSessionListAPIView.as_view(), name="speaking-session-list"),
    path("sessions/<int:session_id>", SpeakingSessionDetailAPIView.as_view(), name="speaking-session-detail"),
    path("sessions/<int:session_id>/turn-rewrite", SpeakingTurnRewriteAPIView.as_view(), name="speaking-turn-rewrite"),
    path("tts/synthesize", TTSSynthesizeAPIView.as_view(), name="tts-synthesize"),
]

