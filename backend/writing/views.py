from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_services.gemini_client import GeminiClient
from ai_services.utils import average_score
from writing.models import WritingEvaluation, WritingTopic
from writing.serializers import WritingEvaluateRequestSerializer, WritingTopicSerializer


class IsStaffOrSuperuser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


class WritingEvaluateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request):
        serializer = WritingEvaluateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        topic_image = data.get("topic_image")
        if topic_image:
            content_type = (getattr(topic_image, "content_type", "") or "").lower()
            if content_type not in {"image/jpeg", "image/png"}:
                return Response(
                    {"error": "unsupported_type", "message": "Only JPG and PNG are allowed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if topic_image.size > 5 * 1024 * 1024:
                return Response(
                    {"error": "image_too_large", "message": "Max image size is 5MB."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        topic_image_bytes = topic_image.read() if topic_image else None
        topic_image_mime_type = (getattr(topic_image, "content_type", "") or "").lower() or None

        topic_image_url = data.get("topic_image_url") or None
        if topic_image and not topic_image_url:
            from django.core.files.storage import default_storage

            topic_image.seek(0)
            path = default_storage.save(f"topic-images/{topic_image.name}", topic_image)
            topic_image_url = request.build_absolute_uri(default_storage.url(path))

        gemini = GeminiClient()
        try:
            result = gemini.evaluate_writing(
                task_type=data["task_type"],
                prompt=data["prompt"],
                essay=data["essay"],
                topic_image_url=topic_image_url,
                topic_image_bytes=topic_image_bytes,
                topic_image_mime_type=topic_image_mime_type,
            )
        except Exception as exc:
            return Response(
                {
                    "error": "llm_evaluation_failed",
                    "message": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        score_key = "ta" if data["task_type"] == "task1" else "tr"
        scores = result.get("scores", {})
        normalized_scores = {
            score_key: float(scores.get(score_key, 0)),
            "cc": float(scores.get("cc", 0)),
            "lr": float(scores.get("lr", 0)),
            "gra": float(scores.get("gra", 0)),
        }
        normalized_scores["overall_band"] = float(
            scores.get("overall_band", average_score([normalized_scores[score_key], normalized_scores["cc"], normalized_scores["lr"], normalized_scores["gra"]]))
        )

        evaluation = WritingEvaluation.objects.create(
            author=request.user,
            task_type=data["task_type"],
            prompt=data["prompt"],
            essay_text=data["essay"],
            topic_image_url=topic_image_url,
            scores=normalized_scores,
            examiner_comments=result.get("examiner_comments", ""),
            corrections=result.get("corrections", []),
            word_count=int(result.get("word_count", 0)),
        )

        return Response(
            {
                "id": evaluation.id,
                "task_type": evaluation.task_type,
                "scores": evaluation.scores,
                "examiner_comments": evaluation.examiner_comments,
                "corrections": evaluation.corrections,
                "word_count": evaluation.word_count,
                "created_at": evaluation.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class WritingEvaluationDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, evaluation_id: int):
        try:
            evaluation = WritingEvaluation.objects.get(id=evaluation_id, author=request.user)
        except WritingEvaluation.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "id": evaluation.id,
                "task_type": evaluation.task_type,
                "prompt": evaluation.prompt,
                "essay_text": evaluation.essay_text,
                "scores": evaluation.scores,
                "examiner_comments": evaluation.examiner_comments,
                "corrections": evaluation.corrections,
                "word_count": evaluation.word_count,
                "created_at": evaluation.created_at,
            }
        )


class WritingEvaluationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        evaluations = WritingEvaluation.objects.filter(author=request.user).order_by("-created_at")[:100]
        items = [
            {
                "id": item.id,
                "task_type": item.task_type,
                "prompt": item.prompt,
                "scores": item.scores,
                "word_count": item.word_count,
                "created_at": item.created_at,
            }
            for item in evaluations
        ]
        return Response({"results": items})


class WritingTopicImageUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded = request.FILES.get("image")
        if not uploaded:
            return Response({"error": "missing_image"}, status=status.HTTP_400_BAD_REQUEST)

        content_type = (uploaded.content_type or "").lower()
        if content_type not in {"image/jpeg", "image/png"}:
            return Response({"error": "unsupported_type", "message": "Only JPG and PNG are allowed."}, status=status.HTTP_400_BAD_REQUEST)

        if uploaded.size > 5 * 1024 * 1024:
            return Response({"error": "image_too_large", "message": "Max image size is 5MB."}, status=status.HTTP_400_BAD_REQUEST)

        from django.core.files.storage import default_storage

        path = default_storage.save(f"topic-images/{uploaded.name}", uploaded)
        image_url = request.build_absolute_uri(default_storage.url(path))
        return Response({"image_url": image_url}, status=status.HTTP_201_CREATED)


class AdminWritingTopicListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, request):
        task_type = request.query_params.get("task_type")
        queryset = WritingTopic.objects.all()
        if task_type:
            if task_type not in {"task1", "task2"}:
                return Response({"error": "invalid_task_type"}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(task_type=task_type)

        serializer = WritingTopicSerializer(queryset, many=True)
        return Response({"results": serializer.data})

    def post(self, request):
        serializer = WritingTopicSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topic = serializer.save()
        return Response(WritingTopicSerializer(topic).data, status=status.HTTP_201_CREATED)


class AdminWritingTopicDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def patch(self, request, topic_id: int):
        topic = get_object_or_404(WritingTopic, id=topic_id)
        serializer = WritingTopicSerializer(topic, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(WritingTopicSerializer(updated).data)

    def delete(self, request, topic_id: int):
        topic = get_object_or_404(WritingTopic, id=topic_id)
        topic.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RandomWritingTopicAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        task_type = request.query_params.get("task_type")
        if task_type not in {"task1", "task2"}:
            return Response({"error": "invalid_task_type"}, status=status.HTTP_400_BAD_REQUEST)

        queryset = WritingTopic.objects.filter(task_type=task_type, is_active=True)
        if task_type == "task1":
            queryset = queryset.exclude(topic_image_url__isnull=True).exclude(topic_image_url="")

        topic = queryset.order_by("?").first()
        if not topic:
            return Response(
                {"error": "topic_not_found", "message": f"No active {task_type} topics available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = WritingTopicSerializer(topic)
        return Response(serializer.data)
