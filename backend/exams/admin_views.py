"""Admin APIs: import a book, verify its answer keys, publish modules.

The shape of this follows the one rule that matters: **a module cannot go live
until a human has confirmed its answer key.** The importer fills in questions;
only an admin fills in the key, and `Module.blocking_problems()` is the gate.
"""

from __future__ import annotations

import hashlib
import re
import threading
import traceback

from django.core.files.base import ContentFile
from django.db import connection, models, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsStaffOrSuperuser
from exams import keyreview, keysheet, services
from exams.importer import pipeline
from exams.importer.ocr import try_get_engine
from exams.importer.publish import publish_payload
from exams.models import (
    LISTENING,
    AnswerKeySheet,
    AudioAsset,
    Book,
    ImportJob,
    Module,
    Section,
)
from exams.serializers import (
    AdminModuleSerializer,
    AnswerKeySheetSerializer,
    BlindAnswerKeySheetSerializer,
    AudioAssetSerializer,
    ImportJobSerializer,
)
from exams.views import ALLOWED_IMAGE_TYPES, MAX_SHEET_BYTES, _error

ADMIN = [IsAuthenticated, IsStaffOrSuperuser]

#: Imports are deliberately serialised. OCR already saturates every core, and
#: two concurrent book imports would thrash a 16GB machine for no gain.
_IMPORT_LOCK = threading.Lock()


def _run_import(job_id: int) -> None:
    """Worker body. Never lets an exception vanish silently."""
    with _IMPORT_LOCK:
        try:
            job = ImportJob.objects.get(pk=job_id)
            job.status = ImportJob.RUNNING
            job.save(update_fields=["status", "updated_at"])

            def progress(message: str) -> None:
                ImportJob.objects.filter(pk=job_id).update(stage=message)

            # Scanned books are the common case, so OCR is always offered. The
            # pipeline only spends it on pages with no text layer and on key
            # pages that need a second, column-aware read; a book with a real
            # text layer never touches it.
            engine, ocr_warning = try_get_engine()
            result = pipeline.run(
                job.source_file.path, slug=job.book_slug, ocr_engine=engine,
                progress=progress,
            )
            if ocr_warning:
                result.warnings.insert(0, ocr_warning)
            job.refresh_from_db()
            job.payload = result.payload
            job.payload_version += 1
            job.warnings = result.warnings[:200]
            job.parser_version = pipeline.PARSER_VERSION
            job.status = ImportJob.NEEDS_REVIEW
            job.stage = "done"
            job.progress = 100
            job.save()
        except Exception:
            ImportJob.objects.filter(pk=job_id).update(
                status=ImportJob.FAILED, error=traceback.format_exc()[:8000]
            )
        finally:
            connection.close()


class ImportJobListCreateAPIView(APIView):
    permission_classes = ADMIN
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        jobs = ImportJob.objects.all()[:50]
        return Response({"jobs": ImportJobSerializer(jobs, many=True).data})

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return _error("missing_file", "upload a PDF as 'file'")
        slug = (request.data.get("book_slug") or "").strip()
        if not slug:
            return _error("missing_book_slug", "book_slug is required")

        payload = upload.read()
        digest = hashlib.sha256(payload).hexdigest()

        # Re-uploading the same book returns the existing job rather than
        # spending minutes redoing identical work - unless the parser has
        # improved since, in which case the old draft is exactly what the
        # re-upload is meant to replace.
        existing = ImportJob.objects.filter(
            content_hash=digest,
            status__in=[ImportJob.NEEDS_REVIEW, ImportJob.PUBLISHED, ImportJob.RUNNING],
        ).filter(
            models.Q(status=ImportJob.RUNNING) | models.Q(parser_version=pipeline.PARSER_VERSION)
        ).first()
        if existing is not None:
            return Response(ImportJobSerializer(existing).data)

        job = ImportJob.objects.create(
            book_slug=slug, content_hash=digest, created_by=request.user,
        )
        job.source_file.save(upload.name, ContentFile(payload), save=True)

        threading.Thread(target=_run_import, args=(job.pk,), daemon=True).start()
        return Response(ImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class ImportJobDetailAPIView(APIView):
    permission_classes = ADMIN

    def get(self, request, job_id: int):
        job = get_object_or_404(ImportJob, pk=job_id)
        data = ImportJobSerializer(job).data
        if request.query_params.get("payload") == "1":
            data["payload"] = job.payload
        return Response(data)


class ImportJobPublishAPIView(APIView):
    permission_classes = ADMIN

    def post(self, request, job_id: int):
        job = get_object_or_404(ImportJob, pk=job_id)
        if not job.payload:
            return _error("empty_payload", "this job has no parsed content")
        result = publish_payload(job.payload, job.book_slug, source_pdf=job.source_file.path)
        job.status = ImportJob.PUBLISHED
        job.book = result.book
        job.save(update_fields=["status", "book", "updated_at"])
        return Response({
            "book": result.book.slug if result.book else None,
            "modules": result.module_ids,
            "questions": result.questions_written,
            "warnings": result.warnings,
            # Publishing content does not publish the test: each module still
            # needs its answer sheet verified.
            "note": "Modules are created as drafts. Upload and verify an answer "
                    "sheet for each before it becomes available to students.",
        })


# ---------------------------------------------------------------------------
# Answer sheets
# ---------------------------------------------------------------------------


def _is_blind(request) -> bool:
    value = request.query_params.get("blind") or (
        request.data.get("blind") if hasattr(request, "data") and isinstance(request.data, dict)
        else None
    )
    return str(value).lower() in ("1", "true", "yes")


def _sheet_payload(request, sheet, blind: bool) -> dict:
    serializer = BlindAnswerKeySheetSerializer if blind else AnswerKeySheetSerializer
    return serializer(sheet, context={"request": request}).data


class AnswerSheetAPIView(APIView):
    """Upload, read and correct one module's answer sheet.

    POST an image -> OCR proposes answers -> PATCH corrections -> POST verify.
    Nothing here trusts OCR: `answers` starts as OCR's proposal but the module
    stays unpublishable until `is_verified` is set by a human.

    ``?blind=1`` (or ``blind: true`` in a body) swaps every response for the
    spoiler-free serializer: statuses and check names, never an answer.
    """

    permission_classes = ADMIN
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, module_id: int):
        module = get_object_or_404(Module, pk=module_id)
        sheet = getattr(module, "answer_sheet", None)
        module_data = AdminModuleSerializer(module, context={"request": request}).data
        if sheet is None:
            return Response({"sheet": None, "module": module_data})
        if not (sheet.evidence or {}) and sheet.answers:
            # A sheet from before the self-checks existed: give it verdicts.
            keyreview.recheck(sheet)
        return Response({
            "sheet": _sheet_payload(request, sheet, _is_blind(request)),
            "module": module_data,
            "blind": _is_blind(request),
        })

    def post(self, request, module_id: int):
        module = get_object_or_404(Module, pk=module_id)
        upload = request.FILES.get("image")
        if upload is None:
            return _error("missing_image", "upload the answer sheet as 'image'")
        if upload.size > MAX_SHEET_BYTES:
            return _error("image_too_large", "the image must be 10MB or smaller")
        if upload.content_type not in ALLOWED_IMAGE_TYPES:
            return _error("bad_image_type", "upload a PNG, JPEG or WebP image")

        data = upload.read()
        total = module.total_questions or 40
        sheet, _created = AnswerKeySheet.objects.get_or_create(module=module)
        sheet.image.save(upload.name, ContentFile(data), save=False)

        existing = dict(sheet.answers or {})
        evidence = {k: dict(v) for k, v in (sheet.evidence or {}).items() if isinstance(v, dict)}
        filled = 0
        ocr_used = False

        # The image is read every time, but it only *fills gaps*. Where the
        # book had a text layer the importer has already filled this grid, and
        # that is far more accurate than OCR of the same page as an image -
        # 40/40 against roughly 13/40 on Cambridge 21 - so re-reading must
        # never replace good answers with worse ones. What the read does for
        # answers already present is vote: agreeing with an OCR'd key is
        # evidence for it, disagreeing flags it.
        expected = {
            int(n): v.get("kind") for n, v in existing.items()
            if isinstance(v, dict) and str(n).isdigit()
        }
        parsed = keysheet.parse_sheet(data, total=total, expected_kinds=expected)
        ocr_used = True
        page_width = keysheet.ASSUMED_PAGE_WIDTH
        for number, key in keysheet.answers_to_json(parsed.answers).items():
            n = int(number)
            raw = parsed.raw.get(n, "")
            entry = evidence.setdefault(number, {})
            reads = dict(entry.get("reads") or {})
            reads["sheet"] = raw
            entry["reads"] = reads
            if number not in existing:
                existing[number] = key
                filled += 1
                entry.update({
                    "source": "sheet",
                    "read": "sheet",
                    "confidence": parsed.row_confidence.get(n),
                    "agreement": None,
                    "independent": None,
                    "filled": False,
                })
                crop = parsed.crops.get(n)
                entry["crop"] = (
                    {**crop, "image": True, "page_width": page_width} if crop else None
                )
            elif entry.get("source") in ("ocr", "embedded", "sheet"):
                same = keysheet.same_answer(existing[number], key)
                if entry.get("agreement") != "disagree":
                    entry["agreement"] = "agree" if same else "disagree"
                    # A photo read by this engine is independent of a scan's
                    # embedded layer, not of this engine's own PDF read.
                    entry["independent"] = entry.get("source") == "embedded"
        sheet.raw_text = {**(sheet.raw_text or {}),
                          **{str(k): v for k, v in parsed.raw.items()}}
        sheet.ocr_confidence = parsed.confidence
        sheet.warnings = list(dict.fromkeys((sheet.warnings or []) + parsed.warnings))[-60:]

        sheet.answers = existing
        sheet.evidence = evidence
        if not sheet.proposed_answers:
            sheet.proposed_answers = dict(existing)
        if not sheet.proposal_source:
            sheet.proposal_source = "ocr" if ocr_used else "manual"
        # A fresh upload always needs confirming again.
        sheet.is_verified = False
        sheet.verified_by = None
        sheet.verified_at = None
        sheet.verification_method = ""
        sheet.save()
        keyreview.recheck(sheet)

        blind = _is_blind(request)
        return Response({
            "sheet": _sheet_payload(request, sheet, blind),
            "read": len(existing),
            "filled_by_ocr": filled,
            "total": total,
            "missing": sheet.missing_numbers,
            "blind": blind,
        }, status=status.HTTP_201_CREATED)

    def patch(self, request, module_id: int):
        """Apply the admin's corrections and/or confirmations to the grid."""
        module = get_object_or_404(Module, pk=module_id)
        sheet = getattr(module, "answer_sheet", None)
        if sheet is None:
            return _error("no_sheet", "upload an answer sheet first",
                          status.HTTP_404_NOT_FOUND)

        answers = request.data.get("answers")
        confirm = request.data.get("confirm")
        if answers is None and confirm is None:
            return _error("invalid_answers", "send 'answers' and/or 'confirm'")
        if answers is not None and not isinstance(answers, dict):
            return _error("invalid_answers", "answers must be an object keyed by "
                                             "question number")
        if confirm is not None and not isinstance(confirm, list):
            return _error("invalid_confirm", "confirm must be a list of question numbers")

        if answers is not None:
            cleaned, problems = _clean_answer_grid(answers, module.total_questions or 40)
            if problems:
                return _error("invalid_answers", "; ".join(problems[:5]))
            if _is_blind(request):
                # Blind edits arrive one cell at a time; keep the rest.
                cleaned = {**(sheet.answers or {}), **cleaned}
            before = dict(sheet.answers or {})
            sheet.answers = cleaned
            keyreview.record_edits(sheet, before, request.user)
            # Any edit invalidates a previous confirmation.
            sheet.is_verified = False
            sheet.verified_by = None
            sheet.verified_at = None
            sheet.verification_method = ""
        if confirm is not None:
            keyreview.confirm(sheet, confirm)
        keyreview.recheck(sheet, save=False)
        sheet.save()
        return Response(_sheet_payload(request, sheet, _is_blind(request)))


class AnswerSheetRevealAPIView(APIView):
    """Show one answer, with its evidence. Every reveal is recorded."""

    permission_classes = ADMIN

    def post(self, request, module_id: int, number: int):
        module = get_object_or_404(Module, pk=module_id)
        sheet = getattr(module, "answer_sheet", None)
        if sheet is None:
            return _error("no_sheet", "this module has no answer sheet",
                          status.HTTP_404_NOT_FOUND)
        if not 1 <= number <= (module.total_questions or 40):
            return _error("bad_number", "no such question", status.HTTP_404_NOT_FOUND)
        return Response(keyreview.reveal(sheet, number))


class AnswerSheetCropAPIView(APIView):
    """The printed key row for one question, cut from the book PDF."""

    permission_classes = ADMIN

    def get(self, request, module_id: int, number: int):
        module = get_object_or_404(Module, pk=module_id)
        sheet = getattr(module, "answer_sheet", None)
        if sheet is None:
            return _error("no_sheet", "this module has no answer sheet",
                          status.HTTP_404_NOT_FOUND)
        try:
            png = keyreview.render_crop(sheet, number)
        except Exception:  # a damaged or missing PDF is a 404, not a 500
            png = None
        if not png:
            return _error("no_crop", "no picture of this key row is available",
                          status.HTTP_404_NOT_FOUND)
        response = HttpResponse(png, content_type="image/png")
        response["Cache-Control"] = "private, max-age=300"
        return response


class AnswerSheetCorrectAPIView(APIView):
    """Fix one answer after sitting the test, and re-mark everyone.

    For the results screen: the answers are already revealed there, and the
    person is looking at the book's key row. The sheet stays verified.
    """

    permission_classes = ADMIN

    def post(self, request, module_id: int):
        module = get_object_or_404(Module, pk=module_id)
        sheet = getattr(module, "answer_sheet", None)
        if sheet is None:
            return _error("no_sheet", "this module has no answer sheet",
                          status.HTTP_404_NOT_FOUND)
        try:
            number = int(request.data.get("number"))
        except (TypeError, ValueError):
            return _error("bad_number", "number is required")
        if not 1 <= number <= (module.total_questions or 40):
            return _error("bad_number", "no such question")
        accepted = request.data.get("accepted")
        if isinstance(accepted, str):
            from exams.keygrammar import expand_alternatives

            accepted = list(expand_alternatives(accepted))
        if not isinstance(accepted, list) or not [a for a in accepted if str(a).strip()]:
            return _error("invalid_answers", "accepted must be a non-empty answer")

        answer = keyreview.correct_after_attempt(sheet, number, accepted, request.user)
        remarked = services.remark_module(module)
        return Response({
            "number": number,
            "answer": answer,
            "remarked_attempts": remarked,
        })


def _clean_answer_grid(answers: dict, total: int) -> tuple[dict, list[str]]:
    """Validate and normalise the grid the admin submits."""
    from exams.keygrammar import detect_kind, expand_alternatives

    cleaned: dict[str, dict] = {}
    problems: list[str] = []
    for key, value in answers.items():
        try:
            number = int(key)
        except (TypeError, ValueError):
            problems.append(f"{key!r} is not a question number")
            continue
        if not 1 <= number <= total:
            problems.append(f"question {number} is outside 1-{total}")
            continue

        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                continue
            accepted = list(expand_alternatives(raw))
            # Infer the kind rather than defaulting to text: a TRUE/FALSE key
            # stored as text would reject a candidate's "T", and a letter stored
            # as text would reject nothing it should but also flag nothing.
            entry = {"kind": detect_kind(tuple(accepted)), "accepted": accepted}
        elif isinstance(value, dict):
            accepted = value.get("accepted") or []
            if isinstance(accepted, str):
                accepted = list(expand_alternatives(accepted))
            accepted = [str(a).strip() for a in accepted if str(a).strip()]
            if not accepted:
                continue
            entry = {
                "kind": value.get("kind") or detect_kind(tuple(accepted)),
                "accepted": accepted,
                "word_limit": value.get("word_limit") or "",
                "set_id": value.get("set_id"),
                "set_numbers": value.get("set_numbers") or [],
                "select_count": value.get("select_count"),
            }
        else:
            problems.append(f"question {number} has an unsupported value")
            continue
        cleaned[str(number)] = entry
    return cleaned, problems


class AnswerSheetVerifyAPIView(APIView):
    """Confirm the grid. This is what unlocks publishing."""

    permission_classes = ADMIN

    def post(self, request, module_id: int):
        module = get_object_or_404(Module, pk=module_id)
        sheet = getattr(module, "answer_sheet", None)
        if sheet is None:
            return _error("no_sheet", "upload an answer sheet first",
                          status.HTTP_404_NOT_FOUND)

        missing = sheet.missing_numbers
        if missing:
            return _error(
                "incomplete",
                f"{len(missing)} answer(s) are still empty: {missing[:10]}",
            )

        mode = (request.data.get("mode") if isinstance(request.data, dict) else None) or "human"
        if mode == AnswerKeySheet.BLIND:
            # Blind verification: the person vouches for what they looked at,
            # and the self-checks must vouch for everything else.
            keyreview.recheck(sheet, save=False)
            blockers = keyreview.blind_blockers(sheet)
            if blockers:
                sheet.save(update_fields=["evidence", "updated_at"])
                return _error(
                    "unchecked",
                    f"{len(blockers)} answer(s) still need a look: {blockers[:12]}",
                )
        elif mode != AnswerKeySheet.HUMAN:
            return _error("bad_mode", "mode must be 'human' or 'blind'")

        sheet.is_verified = True
        sheet.verified_by = request.user
        sheet.verified_at = timezone.now()
        sheet.verification_method = mode
        sheet.save(update_fields=[
            "is_verified", "verified_by", "verified_at", "verification_method",
            "evidence", "updated_at",
        ])

        # A key change means anything already submitted was marked against the
        # old key. Re-marking is a pure function over stored answers.
        remarked = services.remark_module(module)
        return Response({
            "verified": True,
            "remarked_attempts": remarked,
            "module": AdminModuleSerializer(module, context={"request": request}).data,
        })


# ---------------------------------------------------------------------------
# Modules and audio
# ---------------------------------------------------------------------------


class AdminModuleListAPIView(APIView):
    permission_classes = ADMIN

    def get(self, request):
        modules = (
            Module.objects.select_related("test", "test__book", "answer_sheet")
            .prefetch_related("sections__audio")
        )
        book = request.query_params.get("book")
        if book:
            modules = modules.filter(test__book__slug=book)
        return Response({"modules": AdminModuleSerializer(
            modules, many=True, context={"request": request}).data})


class AdminModuleDetailAPIView(APIView):
    permission_classes = ADMIN

    def patch(self, request, module_id: int):
        module = get_object_or_404(
            Module.objects.select_related("test", "test__book"), pk=module_id
        )
        if "is_published" in request.data:
            wanted = bool(request.data["is_published"])
            if wanted:
                problems = module.blocking_problems()
                if problems:
                    return _error("not_publishable", "; ".join(problems),
                                  status.HTTP_409_CONFLICT)
            module.is_published = wanted
        for field in ("duration_seconds", "transfer_seconds"):
            if field in request.data:
                setattr(module, field, int(request.data[field]))
        module.save()
        return Response(
            AdminModuleSerializer(module, context={"request": request}).data
        )


#: Matches both conventions seen so far: "T1S1.m4a" and
#: "cambridge-ielts-21-academic-listening-test-1-3 (2).mp3".
_AUDIO_PATTERNS = (
    re.compile(r"\bT(\d+)\s*S(\d+)\b", re.IGNORECASE),
    re.compile(r"test[\s_-]*(\d+)[\s_-]+(?:part[\s_-]*)?(\d+)", re.IGNORECASE),
    re.compile(r"\b(\d+)[\s_-]+(\d+)\b"),
)


def guess_audio_slot(filename: str) -> tuple[int | None, int | None]:
    """Guess (test, part) from a filename. Only ever a suggestion."""
    name = re.sub(r"\(\d+\)", " ", filename)
    name = re.sub(r"\.[A-Za-z0-9]+$", " ", name)
    for pattern in _AUDIO_PATTERNS:
        match = pattern.search(name)
        if match:
            test, part = int(match.group(1)), int(match.group(2))
            if 1 <= test <= 20 and 1 <= part <= 10:
                return test, part
    return None, None


class AudioUploadAPIView(APIView):
    permission_classes = ADMIN
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        assets = AudioAsset.objects.select_related("book")
        book_slug = request.query_params.get("book")
        if book_slug:
            assets = assets.filter(book__slug=book_slug)
        return Response({"assets": AudioAssetSerializer(
            assets, many=True, context={"request": request}).data})

    def post(self, request):
        book_slug = (request.data.get("book_slug") or "").strip()
        book = get_object_or_404(Book, slug=book_slug)
        files = request.FILES.getlist("files") or (
            [request.FILES["file"]] if "file" in request.FILES else []
        )
        if not files:
            return _error("missing_files", "upload one or more audio files")

        created = []
        for upload in files:
            test_number, part_number = guess_audio_slot(upload.name)
            asset = AudioAsset(
                book=book, test_number=test_number, part_number=part_number,
                original_filename=upload.name, mime=upload.content_type or "",
            )
            asset.file.save(upload.name, upload, save=False)
            asset.duration_seconds = _probe_duration(asset.file.path)
            asset.save()
            created.append(asset)

        return Response({
            "created": AudioAssetSerializer(
                created, many=True, context={"request": request}).data,
            "note": "Mapping is guessed from the filename - confirm it in the grid.",
        }, status=status.HTTP_201_CREATED)


def _probe_duration(path: str) -> int | None:
    """Read a media file's duration with ffprobe (already in the image)."""
    import json
    import subprocess

    try:
        output = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout
        return int(float(json.loads(output)["format"]["duration"]))
    except Exception:
        return None


class AudioAssignAPIView(APIView):
    """Confirm or correct which (test, part) an audio file belongs to."""

    permission_classes = ADMIN

    def patch(self, request, asset_id: int):
        asset = get_object_or_404(AudioAsset, pk=asset_id)
        for field in ("test_number", "part_number"):
            if field in request.data:
                value = request.data[field]
                setattr(asset, field, int(value) if value is not None else None)
        asset.save(update_fields=["test_number", "part_number"])

        # Attach it to the matching listening section, if that module exists.
        attached = None
        if asset.test_number and asset.part_number:
            section = Section.objects.filter(
                module__test__book=asset.book,
                module__test__number=asset.test_number,
                module__skill=LISTENING,
                order=asset.part_number,
            ).first()
            if section is not None:
                section.audio = asset
                section.save(update_fields=["audio"])
                attached = section.pk

        return Response({
            "asset": AudioAssetSerializer(asset, context={"request": request}).data,
            "attached_to_section": attached,
        })
