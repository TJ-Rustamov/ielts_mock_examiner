from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from speaking_app.models import SpeakingSession


class SpeakingSessionListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = SpeakingSession.objects.filter(candidate_metadata__user_id=request.user.id).order_by("-created_at")[:100]
        items = [
            {
                "id": item.id,
                "part": item.part,
                "status": item.status,
                "scores": item.scores,
                "transcript": item.transcript,
                "created_at": item.created_at,
            }
            for item in sessions
        ]
        return Response({"results": items})


class SpeakingSessionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id: int):
        try:
            session = SpeakingSession.objects.get(id=session_id, candidate_metadata__user_id=request.user.id)
        except SpeakingSession.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "id": session.id,
                "part": session.part,
                "status": session.status,
                "scores": session.scores,
                "final_report": session.final_report,
                "transcript": session.transcript,
                "conversation_history": session.conversation_history,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }
        )
