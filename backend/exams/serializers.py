"""Serializers for exam content, attempts and admin review.

The single most important rule here: **student-facing serializers never emit an
answer key.** `AnswerKeySheet.answers` is the only place keys live, and only
`ResultSerializer` (which is gated on a submitted attempt) may reveal them.
There is a test asserting the strings "answer_key" and "accepted" do not appear
in a serialised content payload, because this is exactly the kind of leak that
is invisible until someone opens devtools.
"""

from __future__ import annotations

from rest_framework import serializers

from exams.models import (
    AnswerKeySheet,
    Attempt,
    AudioAsset,
    ImportJob,
    Module,
    Question,
    QuestionGroup,
    Section,
)


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ["number", "prompt_text", "options"]


class QuestionGroupSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = QuestionGroup
        fields = [
            "id", "order", "type", "instruction_text", "first_question",
            "last_question", "word_limit", "select_count", "options",
            "options_reusable", "layout", "image_url", "questions",
        ]

    def get_image_url(self, group) -> str | None:
        if not group.image_id or not group.image.file:
            return None
        request = self.context.get("request")
        url = group.image.file.url
        return request.build_absolute_uri(url) if request else url


class SectionSerializer(serializers.ModelSerializer):
    groups = QuestionGroupSerializer(many=True, read_only=True)
    has_audio = serializers.SerializerMethodField()
    audio_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = [
            "id", "order", "label", "title", "first_question", "last_question",
            "passage_html", "passage_paragraphs", "has_audio", "audio_seconds",
            "groups",
        ]

    def get_has_audio(self, section) -> bool:
        return bool(section.audio_id)

    def get_audio_seconds(self, section) -> int | None:
        return section.audio.duration_seconds if section.audio_id else None


class ModuleSummarySerializer(serializers.ModelSerializer):
    """Listing shape — metadata only, never the questions."""

    book = serializers.CharField(source="test.book.title", read_only=True)
    book_slug = serializers.CharField(source="test.book.slug", read_only=True)
    test_number = serializers.IntegerField(source="test.number", read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    best_band = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            "id", "skill", "book", "book_slug", "test_number", "total_questions",
            "duration_seconds", "is_published", "best_band",
        ]

    def get_duration_seconds(self, module) -> int:
        from exams.services import module_duration

        return module_duration(module)

    def get_best_band(self, module):
        best = self.context.get("best_bands", {}).get(module.pk)
        return str(best) if best is not None else None


class ModuleContentSerializer(ModuleSummarySerializer):
    """What a candidate sees while sitting the test. No keys, ever."""

    sections = SectionSerializer(many=True, read_only=True)

    class Meta(ModuleSummarySerializer.Meta):
        fields = ModuleSummarySerializer.Meta.fields + ["transfer_seconds", "sections"]


class AttemptAnswerSerializer(serializers.Serializer):
    question_number = serializers.IntegerField()
    value = serializers.JSONField()


class AttemptSerializer(serializers.ModelSerializer):
    module = ModuleSummarySerializer(read_only=True)
    answers = serializers.SerializerMethodField()
    server_now = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = [
            "id", "status", "mode", "module", "started_at", "expires_at",
            "submitted_at", "current_section", "raw_score", "band",
            "answers", "server_now",
        ]

    def get_answers(self, attempt) -> dict:
        return {
            str(answer.question_number): answer.value
            for answer in attempt.answers.all()
        }

    def get_server_now(self, _attempt) -> str:
        from django.utils import timezone

        return timezone.now().isoformat()


class ResultSerializer(serializers.Serializer):
    """Post-submission review. The only place accepted answers are revealed."""

    attempt_id = serializers.IntegerField()
    status = serializers.CharField()
    mode = serializers.CharField()
    raw_score = serializers.IntegerField(allow_null=True)
    band = serializers.CharField(allow_null=True)
    total_questions = serializers.IntegerField()
    correct = serializers.IntegerField()
    blank = serializers.IntegerField()
    wrong = serializers.IntegerField()
    rows = serializers.ListField(child=serializers.DictField())
    indicative = serializers.BooleanField(default=True)


# --- admin -----------------------------------------------------------------


class AnswerKeySheetSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    answered_count = serializers.IntegerField(read_only=True)
    missing_numbers = serializers.ListField(read_only=True)
    edited_numbers = serializers.SerializerMethodField()

    class Meta:
        model = AnswerKeySheet
        fields = [
            "id", "module", "image_url", "answers", "proposed_answers",
            "proposal_source", "raw_text",
            "ocr_confidence", "warnings", "is_verified", "verified_at",
            "answered_count", "missing_numbers", "edited_numbers",
        ]
        read_only_fields = [
            "module", "proposed_answers", "proposal_source", "raw_text",
            "ocr_confidence",
        ]

    def get_image_url(self, sheet) -> str | None:
        if not sheet.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(sheet.image.url) if request else sheet.image.url

    def get_edited_numbers(self, sheet) -> list[int]:
        return sheet.edited_numbers()


class AudioAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = AudioAsset
        fields = [
            "id", "book", "test_number", "part_number", "original_filename",
            "mime", "duration_seconds", "url",
        ]

    def get_url(self, asset) -> str | None:
        if not asset.file:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(asset.file.url) if request else asset.file.url


class ImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportJob
        fields = [
            "id", "book_slug", "status", "stage", "progress", "warnings",
            "error", "payload_version", "created_at", "updated_at",
        ]


class AdminModuleSerializer(ModuleSummarySerializer):
    """Adds the publication gate, so the admin sees exactly what is blocking."""

    blocking_problems = serializers.SerializerMethodField()
    has_answer_sheet = serializers.SerializerMethodField()
    answer_sheet_verified = serializers.SerializerMethodField()

    class Meta(ModuleSummarySerializer.Meta):
        fields = ModuleSummarySerializer.Meta.fields + [
            "blocking_problems", "has_answer_sheet", "answer_sheet_verified",
        ]

    def get_blocking_problems(self, module) -> list[str]:
        return module.blocking_problems()

    def get_has_answer_sheet(self, module) -> bool:
        return getattr(module, "answer_sheet", None) is not None

    def get_answer_sheet_verified(self, module) -> bool:
        sheet = getattr(module, "answer_sheet", None)
        return bool(sheet and sheet.is_verified)
