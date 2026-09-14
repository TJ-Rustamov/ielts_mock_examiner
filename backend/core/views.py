import base64
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AIConfiguration, SpeakingConfiguration, SpeakingQuestion
from core.permissions import IsStaffOrSuperuser
from core.serializers import (
    AIConfigurationSerializer,
    AdminUserCreateSerializer,
    AdminUserSerializer,
    SpeakingConfigurationSerializer,
    SpeakingQuestionSerializer,
)
from speaking_app.models import SpeakingSession
from writing.models import WritingEvaluation, WritingTopic
from ai_services.tts_client import KokoroClient


User = get_user_model()
_TTS_PREVIEW_CLIENT: KokoroClient | None = None

MODEL_CATALOG = {
    "google": [
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
    "openai": [
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
    ],
}


def _available_kokoro_voices() -> list[str]:
    model_path = os.getenv("KOKORO_MODEL_PATH", "")
    base_dir = Path(model_path).parent if model_path.endswith(".pth") else Path(model_path or "/models/Kokoro-82M")
    voices_dir = base_dir / "voices"
    if not voices_dir.exists():
        fallback = Path("/models/Kokoro-82M/voices")
        voices_dir = fallback if fallback.exists() else voices_dir
    if not voices_dir.exists():
        return []
    return sorted(p.stem for p in voices_dir.glob("*.pt"))


def _get_tts_preview_client() -> KokoroClient:
    global _TTS_PREVIEW_CLIENT
    if _TTS_PREVIEW_CLIENT is None:
        _TTS_PREVIEW_CLIENT = KokoroClient()
    return _TTS_PREVIEW_CLIENT


@api_view(["GET"])
def health_check(_request):
    return Response({"status": "ok"})


class AdminOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, _request):
        return Response(
            {
                "total_users": User.objects.count(),
                "writing_topics": WritingTopic.objects.filter(is_active=True).count(),
                "speaking_questions": SpeakingQuestion.objects.filter(is_active=True).count(),
                "ai_requests_today": WritingEvaluation.objects.count() + SpeakingSession.objects.count(),
            }
        )


class AdminUserListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, request):
        search = (request.query_params.get("search") or "").strip()
        queryset = User.objects.all()
        if search:
            queryset = queryset.filter(Q(username__icontains=search) | Q(email__icontains=search))

        results = AdminUserSerializer(queryset.order_by("-date_joined")[:200], many=True).data
        return Response({"results": results})

    def post(self, request):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.create_user(
            username=data["username"],
            password=data["password"],
            email=data.get("email", ""),
        )
        user.is_staff = data.get("is_staff", False)
        user.save()

        payload = AdminUserSerializer(user).data
        return Response(payload, status=status.HTTP_201_CREATED)


class AdminUserDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def patch(self, request, user_id: int):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        if "is_active" in request.data:
            user.is_active = bool(request.data["is_active"])
        if "is_staff" in request.data:
            user.is_staff = bool(request.data["is_staff"])
        if "password" in request.data and request.data["password"]:
            user.set_password(str(request.data["password"]))
        user.save()

        payload = AdminUserSerializer(user).data
        return Response(payload)

    def delete(self, _request, user_id: int):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AIConfigurationAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, _request):
        obj, _ = AIConfiguration.objects.get_or_create(id=1)
        if not obj.enabled_models:
            provider_models = MODEL_CATALOG.get(obj.provider, MODEL_CATALOG["google"])
            obj.enabled_models = list(provider_models)
            if obj.writing_model not in obj.enabled_models:
                obj.writing_model = obj.enabled_models[0]
            if obj.speaking_model not in obj.enabled_models:
                obj.speaking_model = obj.enabled_models[0]
            obj.save()

        return Response({"config": AIConfigurationSerializer(obj).data, "model_catalog": MODEL_CATALOG})

    def put(self, request):
        if "writing_prompt" in request.data or "speaking_prompt" in request.data:
            return Response(
                {"error": "prompt_edit_disabled", "message": "Prompts are managed in code and cannot be edited from admin."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj, _ = AIConfiguration.objects.get_or_create(id=1)
        serializer = AIConfigurationSerializer(obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SpeakingConfigurationAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, _request):
        config, _ = SpeakingConfiguration.objects.get_or_create(id=1)
        questions = SpeakingQuestion.objects.all().order_by("part", "-created_at")
        return Response(
            {
                "voice": SpeakingConfigurationSerializer(config).data,
                "providers": ["kokoro"],
                "voices": _available_kokoro_voices(),
                "questions": SpeakingQuestionSerializer(questions, many=True).data,
            }
        )

    def put(self, request):
        config, _ = SpeakingConfiguration.objects.get_or_create(id=1)
        serializer = SpeakingConfigurationSerializer(config, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SpeakingQuestionImportAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def post(self, request):
        import json
        
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "missing_file"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            content = file_obj.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='replace')
            data = json.loads(content)
        except Exception as e:
            return Response({"error": "invalid_json", "details": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Assuming data structure matches q2_tst.json with parts
        added_count = 0
        try:
            for part_key, items in data.items():
                if part_key == "part1":
                    for item in items:
                        SpeakingQuestion.objects.create(
                            part=1,
                            topic=item.get("topic", ""),
                            questions=item.get("questions", []),
                            is_active=True
                        )
                        added_count += 1
                elif part_key == "part2":
                    for item in items:
                        SpeakingQuestion.objects.create(
                            part=2,
                            topic=item.get("topic", ""),
                            cue_card=item.get("cue_card", ""),
                            points=item.get("points", []),
                            is_active=True
                        )
                        added_count += 1
                elif part_key == "part3":
                    for item in items:
                        SpeakingQuestion.objects.create(
                            part=3,
                            topic=item.get("topic", ""),
                            questions=item.get("questions", []),
                            is_active=True
                        )
                        added_count += 1
        except Exception as e:
             return Response({"error": "import_failed", "details": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"status": "ok", "added_count": added_count})


class SpeakingQuestionListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, request):
        part = request.query_params.get("part")
        queryset = SpeakingQuestion.objects.all()
        if part:
            try:
                part_value = int(part)
            except ValueError:
                return Response({"error": "invalid_part"}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(part=part_value)
        return Response({"results": SpeakingQuestionSerializer(queryset, many=True).data})

    def post(self, request):
        serializer = SpeakingQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(SpeakingQuestionSerializer(item).data, status=status.HTTP_201_CREATED)


class SpeakingQuestionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def patch(self, request, question_id: int):
        try:
            question = SpeakingQuestion.objects.get(id=question_id)
        except SpeakingQuestion.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = SpeakingQuestionSerializer(question, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, _request, question_id: int):
        try:
            question = SpeakingQuestion.objects.get(id=question_id)
        except SpeakingQuestion.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        question.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TTSPreviewAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def post(self, request):
        text = str(request.data.get("text", "")).strip()
        voice = str(request.data.get("voice", "")).strip() or None
        try:
            speed = float(request.data.get("speed", 1.0))
        except (TypeError, ValueError):
            speed = 1.0

        if not text:
            return Response({"error": "missing_text"}, status=status.HTTP_400_BAD_REQUEST)

        client = _get_tts_preview_client()
        wav_bytes = client.generate_audio(text, voice=voice, speed=speed)
        return Response(
            {
                "mime_type": "audio/wav",
                "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
            }
        )
