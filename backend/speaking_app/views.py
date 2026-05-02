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


class SpeakingTurnRewriteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id: int):
        try:
            session = SpeakingSession.objects.get(id=session_id, candidate_metadata__user_id=request.user.id)
        except SpeakingSession.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        band = request.data.get("band", 7)
        examiner_question = request.data.get("examiner_question", "")
        candidate_response = request.data.get("candidate_response", "")

        if not candidate_response:
            return Response({"error": "candidate_response is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_band = int(band)
        except ValueError:
            target_band = 7

        from ai_services.gemini_client import GeminiClient
        client = GeminiClient()
        try:
            result = client.generate_speaking_turn_rewrite(examiner_question, candidate_response, target_band)
            return Response(result)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TTSSynthesizeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        text = str(request.data.get("text", "")).strip()
        if not text:
            return Response({"error": "text is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        from core.models import SpeakingConfiguration
        config, _ = SpeakingConfiguration.objects.get_or_create(id=1)
        voice = config.voice or "af_heart"
        speed = float(config.speed or 1.0)
        
        from ai_services.tts_client import KokoroClient
        client = KokoroClient()
        try:
            import base64
            wav_bytes = client.generate_audio(text, voice=voice, speed=speed)
            return Response({
                "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
                "mime_type": "audio/wav"
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
