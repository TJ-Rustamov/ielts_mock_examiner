from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
import threading
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_services.gemini_client import GeminiClient
from ai_services.utils import average_score
from core.permissions import IsStaffOrSuperuser
from writing.models import WritingEvaluation, WritingTopic
from writing.serializers import WritingEvaluateRequestSerializer, WritingTopicSerializer


def _run_detailed_writing_evaluation(evaluation_id: int, task_type: str, prompt: str, essay: str, topic_image_url: str | None, topic_image_bytes: bytes | None, topic_image_mime_type: str | None):
    try:
        gemini = GeminiClient()
        result = gemini.evaluate_writing(
            task_type=task_type,
            prompt=prompt,
            essay=essay,
            topic_image_url=topic_image_url,
            topic_image_bytes=topic_image_bytes,
            topic_image_mime_type=topic_image_mime_type,
        )
        # Re-fetch the evaluation to ensure we have the latest instance
        evaluation = WritingEvaluation.objects.get(id=evaluation_id)
        evaluation.examiner_comments = result.get("examiner_comments", "")
        evaluation.corrections = _safe_json_list(result.get("corrections", []))
        evaluation.criteria_feedback = _safe_json_dict(result.get("criteria_feedback"))
        evaluation.inline_suggestions = _safe_json_list(result.get("inline_suggestions", []))
        evaluation.save()
    except Exception as exc:
        try:
            evaluation = WritingEvaluation.objects.get(id=evaluation_id)
            evaluation.examiner_comments = f"Detailed evaluation failed: {exc}"
            evaluation.save()
        except Exception:
            pass



def _safe_json_list(value):
    return value if isinstance(value, list) else []


def _safe_json_dict(value):
    return value if isinstance(value, dict) else {}


def _normalize_band_entry(value):
    if isinstance(value, str):
        return {"rewritten_essay": value, "coach_summary": "", "improvements": []}
    if not isinstance(value, dict):
        return {"rewritten_essay": "", "coach_summary": "", "improvements": []}

    rewritten = str(value.get("rewritten_essay", "")).strip()
    coach_summary = str(value.get("coach_summary", "")).strip()
    improvements_raw = value.get("improvements", [])
    improvements = []
    if isinstance(improvements_raw, list):
        for item in improvements_raw[:12]:
            if not isinstance(item, dict):
                continue
            enhanced_text = str(item.get("enhanced_text", "")).strip()
            why_better = str(item.get("why_better", "")).strip()
            if not enhanced_text and not why_better:
                continue
            improvements.append(
                {
                    "original_text": str(item.get("original_text", "")).strip(),
                    "enhanced_text": enhanced_text,
                    "why_better": why_better,
                    "criterion": str(item.get("criterion", "")).strip().lower(),
                }
            )
    return {"rewritten_essay": rewritten, "coach_summary": coach_summary, "improvements": improvements}


def _normalize_band_essays_dict(value):
    source = value if isinstance(value, dict) else {}
    return {
        "7": _normalize_band_entry(source.get("7")),
        "8": _normalize_band_entry(source.get("8")),
        "9": _normalize_band_entry(source.get("9")),
    }


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
            result = gemini.evaluate_writing_quick_scores(
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
            examiner_comments="", # Empty string indicates it's processing
            corrections=[],
            criteria_feedback={},
            inline_suggestions=[],
            word_count=int(result.get("word_count", 0)),
            band_essays={},
            band_essays_status="pending",
        )

        # Start detailed evaluation in the background
        threading.Thread(
            target=_run_detailed_writing_evaluation,
            args=(
                evaluation.id,
                data["task_type"],
                data["prompt"],
                data["essay"],
                topic_image_url,
                topic_image_bytes,
                topic_image_mime_type,
            )
        ).start()

        return Response(
            {
                "id": evaluation.id,
                "task_type": evaluation.task_type,
                "scores": evaluation.scores,
                "examiner_comments": evaluation.examiner_comments,
                "corrections": evaluation.corrections,
                "criteria_feedback": evaluation.criteria_feedback,
                "inline_suggestions": evaluation.inline_suggestions,
                "word_count": evaluation.word_count,
                "band_essays_status": evaluation.band_essays_status,
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
                "criteria_feedback": evaluation.criteria_feedback,
                "inline_suggestions": evaluation.inline_suggestions,
                "word_count": evaluation.word_count,
                "band_essays_status": evaluation.band_essays_status,
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


class WritingBandEssaysStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, evaluation_id: int):
        try:
            evaluation = WritingEvaluation.objects.get(id=evaluation_id, author=request.user)
        except WritingEvaluation.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        essays = _normalize_band_essays_dict(evaluation.band_essays)
        generated = [band for band, item in essays.items() if item.get("rewritten_essay")]
        return Response(
            {
                "status": evaluation.band_essays_status,
                "essays": essays,
                "generated_bands": generated,
                "error": evaluation.band_essays_error or "",
            }
        )

    def post(self, request, evaluation_id: int):
        try:
            evaluation = WritingEvaluation.objects.get(id=evaluation_id, author=request.user)
        except WritingEvaluation.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

        band = str(request.data.get("band", "")).strip()
        if band not in {"7", "8", "9"}:
            return Response({"error": "invalid_band", "message": "band must be one of 7, 8, 9"}, status=status.HTTP_400_BAD_REQUEST)

        force = bool(request.data.get("force", False))
        existing = _normalize_band_essays_dict(evaluation.band_essays)
        if not force and existing.get(band, {}).get("rewritten_essay"):
            generated = [b for b, item in existing.items() if item.get("rewritten_essay")]
            return Response(
                {
                    "status": evaluation.band_essays_status,
                    "essays": existing,
                    "generated_bands": generated,
                    "error": evaluation.band_essays_error or "",
                }
            )

        evaluation.band_essays_status = "processing"
        evaluation.band_essays_error = ""
        evaluation.save(update_fields=["band_essays_status", "band_essays_error"])

        try:
            gemini = GeminiClient()
            generated_entry = gemini.generate_band_rewrite(
                task_type=evaluation.task_type,
                prompt=evaluation.prompt,
                essay=evaluation.essay_text,
                target_band=int(band),
            )
            existing[band] = _normalize_band_entry(generated_entry)
            generated = [b for b, item in existing.items() if item.get("rewritten_essay")]
            evaluation.band_essays = existing
            evaluation.band_essays_status = "done" if generated else "pending"
            evaluation.band_essays_error = ""
            evaluation.save(update_fields=["band_essays", "band_essays_status", "band_essays_error"])
            return Response(
                {
                    "status": evaluation.band_essays_status,
                    "essays": existing,
                    "generated_bands": generated,
                    "error": "",
                }
            )
        except Exception as exc:
            evaluation.band_essays_status = "failed"
            evaluation.band_essays_error = str(exc)
            evaluation.save(update_fields=["band_essays_status", "band_essays_error"])
            return Response(
                {
                    "status": "failed",
                    "essays": existing,
                    "generated_bands": [b for b, item in existing.items() if item.get("rewritten_essay")],
                    "error": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


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
