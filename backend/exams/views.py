"""Student and admin APIs for Reading and Listening.

House style throughout: plain DRF ``APIView`` classes, explicit
``permission_classes``, and ``{"error": code, "message": ...}`` error bodies,
matching ``core`` and ``writing``.
"""

from __future__ import annotations

import hashlib
import threading
import traceback

from django.db import connection, models
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsStaffOrSuperuser
from exams import bands, keysheet, services
from exams.models import (
    LISTENING,
    READING,
    AnswerKeySheet,
    Attempt,
    ImportJob,
    Module,
    Section,
)
from exams.serializers import (
    AdminModuleSerializer,
    AnswerKeySheetSerializer,
    AttemptSerializer,
    ImportJobSerializer,
    ModuleContentSerializer,
    ModuleSummarySerializer,
)

MAX_SHEET_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


def _error(code: str, message: str, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"error": code, "message": message}, status=http_status)


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------


class TestListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        skill = request.query_params.get("skill")
        modules = (
            Module.objects.filter(is_published=True)
            .select_related("test", "test__book")
            .prefetch_related("sections__audio")
        )
        if skill in (READING, LISTENING):
            modules = modules.filter(skill=skill)

        best = dict(
            Attempt.objects.filter(
                user=request.user, module__in=modules, status=Attempt.SUBMITTED
            )
            .values_list("module_id")
            .annotate(best=models.Max("band"))
        )
        serializer = ModuleSummarySerializer(
            modules, many=True,
            context={"request": request, "best_bands": best},
        )
        return Response({"tests": serializer.data})


class AttemptStartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, module_id: int):
        module = get_object_or_404(
            Module.objects.select_related("test", "test__book"), pk=module_id
        )
        mode = request.data.get("mode") or Attempt.EXAM
        try:
            attempt = services.start_attempt(request.user, module, mode)
        except services.ModuleNotAvailable as exc:
            return _error("module_not_available", str(exc), status.HTTP_409_CONFLICT)
        except services.AttemptClosed as exc:
            return _error("attempt_closed", str(exc), status.HTTP_409_CONFLICT)

        content = ModuleContentSerializer(module, context={"request": request}).data
        return Response(
            {
                "attempt": AttemptSerializer(attempt, context={"request": request}).data,
                "content": content,
            },
            status=status.HTTP_201_CREATED,
        )


class AttemptDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id: int):
        attempt = get_object_or_404(
            Attempt.objects.select_related("module", "module__test", "module__test__book"),
            pk=attempt_id, user=request.user,
        )
        payload = {
            "attempt": AttemptSerializer(attempt, context={"request": request}).data,
        }
        if attempt.status == Attempt.IN_PROGRESS:
            payload["content"] = ModuleContentSerializer(
                attempt.module, context={"request": request}
            ).data
        return Response(payload)


class AttemptAnswersAPIView(APIView):
    """The autosave endpoint. Idempotent, and cheap enough to call often."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, attempt_id: int):
        attempt = get_object_or_404(Attempt, pk=attempt_id, user=request.user)
        answers = request.data.get("answers") or []
        if not isinstance(answers, list):
            return _error("invalid_answers", "answers must be a list")
        try:
            saved = services.save_answers(attempt, answers)
        except services.AttemptClosed as exc:
            return _error("attempt_closed", str(exc), status.HTTP_409_CONFLICT)
        return Response({
            "saved": saved,
            "server_now": timezone.now().isoformat(),
            "expires_at": attempt.expires_at.isoformat(),
        })


class AttemptAdvanceAPIView(APIView):
    """Listening only: the client reports, the server's clock decides."""

    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_id: int):
        attempt = get_object_or_404(Attempt, pk=attempt_id, user=request.user)
        if attempt.status != Attempt.IN_PROGRESS:
            return _error("attempt_closed", "this attempt is closed", status.HTTP_409_CONFLICT)
        requested = int(request.data.get("section") or 0)
        sections = attempt.module.sections.count()
        attempt.current_section = max(1, min(requested or attempt.current_section, sections))
        if attempt.audio_started_at is None:
            attempt.audio_started_at = timezone.now()
        attempt.audio_section_order = attempt.current_section
        attempt.save(update_fields=[
            "current_section", "audio_started_at", "audio_section_order",
        ])
        return Response({
            "current_section": attempt.current_section,
            "server_now": timezone.now().isoformat(),
        })


class AttemptSubmitAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_id: int):
        attempt = get_object_or_404(
            Attempt.objects.select_related("module", "module__test", "module__test__book"),
            pk=attempt_id, user=request.user,
        )
        if attempt.status != Attempt.IN_PROGRESS:
            return _error("already_submitted", "this attempt is already submitted",
                          status.HTTP_409_CONFLICT)
        attempt = services.submit_attempt(attempt)
        return Response(_result_payload(attempt))


class AttemptResultAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id: int):
        attempt = get_object_or_404(
            Attempt.objects.select_related("module", "module__test", "module__test__book"),
            pk=attempt_id, user=request.user,
        )
        if attempt.status == Attempt.IN_PROGRESS:
            # Revealing the key before submission would hand the candidate the
            # answers mid-test.
            return _error("not_submitted", "results are available after you submit",
                          status.HTTP_403_FORBIDDEN)
        return Response(_result_payload(attempt))


def _result_payload(attempt: Attempt) -> dict:
    rows = services.result_rows(attempt)
    correct = sum(1 for row in rows if row.is_correct)
    blank = sum(1 for row in rows if row.reason == "blank")
    return {
        "attempt_id": attempt.pk,
        "status": attempt.status,
        "mode": attempt.mode,
        "raw_score": attempt.raw_score,
        "band": str(attempt.band) if attempt.band is not None else None,
        "total_questions": attempt.module.total_questions,
        "correct": correct,
        "blank": blank,
        "wrong": len(rows) - correct - blank,
        # Cambridge does not publish exact raw-to-band conversions; the tables
        # used are the standard indicative ones and the UI must say so.
        "indicative": True,
        "rows": [
            {
                "number": row.number,
                "response": row.response,
                "is_correct": row.is_correct,
                "reason": row.reason,
                "accepted": row.accepted,
            }
            for row in rows
        ],
    }


class AttemptHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        attempts = (
            Attempt.objects.filter(user=request.user)
            .select_related("module", "module__test", "module__test__book")
            .order_by("-started_at")[:50]
        )
        return Response({
            "attempts": AttemptSerializer(
                attempts, many=True, context={"request": request}
            ).data
        })


class AttemptAudioAPIView(APIView):
    """Serve listening audio for a live attempt.

    Exists because MEDIA_URL is only served when DEBUG is on, so there is no
    production path for these files otherwise — and because it puts the server
    in charge of when a part may be played.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id: int, section_id: int):
        attempt = get_object_or_404(Attempt, pk=attempt_id, user=request.user)
        section = get_object_or_404(Section, pk=section_id, module_id=attempt.module_id)
        if not section.audio_id or not section.audio.file:
            raise Http404("no audio for this section")
        if attempt.status != Attempt.IN_PROGRESS:
            return _error("attempt_closed", "this attempt is closed",
                          status.HTTP_403_FORBIDDEN)

        response = FileResponse(section.audio.file.open("rb"))
        response["Cache-Control"] = "no-store"
        response["Accept-Ranges"] = "bytes"
        return response


class OverallBandAPIView(APIView):
    """The four-skill aggregate, computed rather than stored."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        latest = {}
        for skill in (READING, LISTENING):
            attempt = (
                Attempt.objects.filter(
                    user=request.user, module__skill=skill, status=Attempt.SUBMITTED
                )
                .order_by("-submitted_at")
                .first()
            )
            latest[skill] = float(attempt.band) if attempt and attempt.band else None

        writing = speaking = None
        try:
            from writing.models import WritingEvaluation

            row = WritingEvaluation.objects.filter(author=request.user).first()
            if row:
                writing = row.scores.get("overall_band")
        except Exception:
            pass
        try:
            from speaking_app.models import SpeakingSession

            row = SpeakingSession.objects.filter(
                candidate_metadata__user_id=request.user.id, status="finished"
            ).first()
            if row:
                speaking = row.scores.get("overall_band")
        except Exception:
            pass

        overall = bands.overall_band([
            latest[READING], latest[LISTENING], writing, speaking
        ])
        return Response({
            "reading": latest[READING],
            "listening": latest[LISTENING],
            "writing": writing,
            "speaking": speaking,
            "overall": str(overall) if overall is not None else None,
        })
