"""Reading and Listening content, answer keys, and attempts.

One app for both skills: they share the whole shape (test -> section -> group ->
question -> key -> attempt -> answer -> mark -> band) and differ only in a
couple of nullable columns and a timing policy. Splitting them would duplicate
the marking engine, the band tables, the importer and the review UI.

Ownership links are real foreign keys with indexes. `SpeakingSession` reaches
its user through a JSON lookup, which means "show me this student's attempts" is
a table scan with no referential integrity; that is not repeated here.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

QUESTIONS_PER_MODULE = 40

READING = "reading"
LISTENING = "listening"
SKILL_CHOICES = ((READING, "Reading"), (LISTENING, "Listening"))


class Book(models.Model):
    """A source book, e.g. Cambridge IELTS 21."""

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    publisher = models.CharField(max_length=100, blank=True, default="Cambridge")
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    variant = models.CharField(max_length=20, default="academic")
    source_pdf = models.FileField(upload_to="exam-sources/", null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.title or self.slug


class ExamTest(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="tests")
    number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = [("book", "number")]
        ordering = ["book", "number"]

    def __str__(self) -> str:
        return f"{self.book.slug} Test {self.number}"


class Module(models.Model):
    """One skill of one test — the thing a student actually sits."""

    test = models.ForeignKey(ExamTest, on_delete=models.CASCADE, related_name="modules")
    skill = models.CharField(max_length=10, choices=SKILL_CHOICES)
    duration_seconds = models.PositiveIntegerField(default=3600)
    #: Listening only. 600 is the paper format; computer-delivered IELTS gives
    #: 2 minutes, so this is per-module rather than a constant.
    transfer_seconds = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveSmallIntegerField(default=QUESTIONS_PER_MODULE)
    is_published = models.BooleanField(default=False)
    band_table_version = models.CharField(max_length=20, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("test", "skill")]
        ordering = ["test", "skill"]
        indexes = [models.Index(fields=["skill", "is_published"])]

    def __str__(self) -> str:
        return f"{self.test} {self.get_skill_display()}"

    # -- publication gate ---------------------------------------------------

    def blocking_problems(self) -> list[str]:
        """Reasons this module cannot go live. Empty means it may be published.

        Deliberately conservative: a module with a missing or unverified answer
        key must never reach a student, because nothing downstream would catch a
        wrong key — it would simply mis-mark everyone, silently and forever.
        """
        problems: list[str] = []

        sheet = getattr(self, "answer_sheet", None)
        if sheet is None:
            problems.append("no answer sheet has been uploaded")
        elif not sheet.is_verified:
            problems.append("the answer sheet has not been verified")
        elif sheet.answered_count < self.total_questions:
            problems.append(
                f"the answer sheet has {sheet.answered_count} of "
                f"{self.total_questions} answers"
            )

        numbers = sorted(self.questions.values_list("number", flat=True))
        if numbers != list(range(1, self.total_questions + 1)):
            missing = sorted(set(range(1, self.total_questions + 1)) - set(numbers))
            problems.append(
                f"questions are not 1-{self.total_questions}"
                + (f" (missing {missing[:8]})" if missing else "")
            )

        if self.skill == LISTENING:
            silent = [
                s.order for s in self.sections.all()
                if not s.audio_id or not (s.audio and s.audio.duration_seconds)
            ]
            if silent:
                problems.append(f"no audio for part(s) {silent}")

        return problems

    @property
    def is_publishable(self) -> bool:
        return not self.blocking_problems()


class AudioAsset(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="audio")
    test_number = models.PositiveSmallIntegerField(null=True, blank=True)
    part_number = models.PositiveSmallIntegerField(null=True, blank=True)
    file = models.FileField(upload_to="exam-audio/")
    original_filename = models.CharField(max_length=255, blank=True)
    mime = models.CharField(max_length=60, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("book", "test_number", "part_number")]
        ordering = ["book", "test_number", "part_number"]

    def __str__(self) -> str:
        return f"{self.book.slug} T{self.test_number}P{self.part_number}"


class Section(models.Model):
    """Reading Passage n, or Listening Part n."""

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="sections")
    order = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=40, blank=True)
    title = models.CharField(max_length=255, blank=True)
    first_question = models.PositiveSmallIntegerField(default=1)
    last_question = models.PositiveSmallIntegerField(default=1)

    # reading
    passage_html = models.TextField(blank=True)
    passage_paragraphs = models.JSONField(default=list, blank=True)

    # listening
    audio = models.ForeignKey(
        AudioAsset, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="sections",
    )
    transcript_text = models.TextField(blank=True)

    class Meta:
        unique_together = [("module", "order")]
        ordering = ["module", "order"]

    def __str__(self) -> str:
        return f"{self.module} {self.label or self.order}"


class GroupImage(models.Model):
    """A cropped figure: a map, plan, diagram or flow-chart."""

    file = models.ImageField(upload_to="exam-images/")
    source_page = models.PositiveSmallIntegerField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class QuestionGroup(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="groups")
    order = models.PositiveSmallIntegerField()
    type = models.CharField(max_length=32)
    instruction_text = models.TextField(blank=True)
    first_question = models.PositiveSmallIntegerField()
    last_question = models.PositiveSmallIntegerField()
    word_limit = models.CharField(max_length=32, blank=True)
    select_count = models.PositiveSmallIntegerField(null=True, blank=True)
    #: [{"letter": "A", "text": "..."}] — a bank shared by the whole group.
    options = models.JSONField(default=list, blank=True)
    options_reusable = models.BooleanField(default=False)
    #: Renderable blocks; text may contain {{Qn}} placeholders.
    layout = models.JSONField(default=list, blank=True)
    image = models.ForeignKey(
        GroupImage, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="groups",
    )
    source_page = models.PositiveSmallIntegerField(null=True, blank=True)
    source_bbox = models.JSONField(null=True, blank=True)
    needs_review = models.BooleanField(default=False)
    is_excluded = models.BooleanField(default=False)
    warnings = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = [("section", "order")]
        ordering = ["section", "order"]

    def __str__(self) -> str:
        return f"{self.section} Q{self.first_question}-{self.last_question} {self.type}"


class Question(models.Model):
    #: Denormalised so ``unique_together("module", "number")`` is expressible.
    #: Both skills number 1-40, and uniqueness cannot be enforced through three
    #: levels of foreign key.
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="questions")
    group = models.ForeignKey(
        QuestionGroup, on_delete=models.CASCADE, related_name="questions"
    )
    number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(QUESTIONS_PER_MODULE)]
    )
    order = models.PositiveSmallIntegerField(default=0)
    prompt_text = models.TextField(blank=True)
    options = models.JSONField(default=list, blank=True)
    marks = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = [("module", "number")]
        ordering = ["module", "number"]

    def __str__(self) -> str:
        return f"{self.module} Q{self.number}"


class AnswerKeySheet(models.Model):
    """One module's answer key: a proposal, an image, and a human confirmation.

    The key is never taken on trust. Whatever fills the grid - the book's text
    layer, OCR of an uploaded image, or typing - the module stays unpublishable
    until someone sets `is_verified`, because a wrong key mis-marks every future
    candidate silently and nothing downstream would catch it.

    The uploaded image is the reference a human checks the grid against, and the
    input OCR reads when a book has no text layer to parse.
    """

    module = models.OneToOneField(
        Module, on_delete=models.CASCADE, related_name="answer_sheet"
    )
    image = models.ImageField(upload_to="exam-answer-sheets/")
    #: {"12": {"kind": "text", "accepted": ["cafe"], ...}} — keys are strings
    #: because JSON object keys always are. This is the confirmed key and the
    #: only thing marking reads.
    answers = models.JSONField(default=dict, blank=True)
    #: What was proposed before any human correction, kept so the review screen
    #: can show exactly which cells a person changed.
    proposed_answers = models.JSONField(default=dict, blank=True)
    #: pdf | ocr | manual. The book's own text layer is by far the best source
    #: where it exists - it reads 40/40 on seven of Cambridge 21's eight key
    #: pages, against roughly 13/40 for OCR of the same pages as images - so OCR
    #: is a fallback for scanned books, not the default.
    proposal_source = models.CharField(max_length=10, blank=True, default="")
    #: Verbatim per-question text, for audit.
    raw_text = models.JSONField(default=dict, blank=True)
    ocr_confidence = models.FloatField(null=True, blank=True)
    warnings = models.JSONField(default=list, blank=True)

    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="verified_answer_sheets",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        state = "verified" if self.is_verified else "unverified"
        return f"Answer sheet for {self.module} ({state})"

    @property
    def answered_count(self) -> int:
        return sum(
            1 for value in self.answers.values()
            if isinstance(value, dict) and value.get("accepted")
        )

    @property
    def missing_numbers(self) -> list[int]:
        total = self.module.total_questions if self.module_id else QUESTIONS_PER_MODULE
        present = {
            int(number) for number, value in self.answers.items()
            if isinstance(value, dict) and value.get("accepted")
        }
        return sorted(set(range(1, total + 1)) - present)

    def edited_numbers(self) -> list[int]:
        """Question numbers a human changed from the proposal — shown in review."""
        changed: list[int] = []
        for number, value in self.answers.items():
            proposed = self.proposed_answers.get(number)
            if proposed != value:
                changed.append(int(number))
        return sorted(changed)


class Attempt(models.Model):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    ABANDONED = "abandoned"
    STATUS_CHOICES = (
        (IN_PROGRESS, "In progress"), (SUBMITTED, "Submitted"),
        (EXPIRED, "Expired"), (ABANDONED, "Abandoned"),
    )

    EXAM = "exam"
    PRACTICE = "practice"
    MODE_CHOICES = ((EXAM, "Exam"), (PRACTICE, "Practice"))

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_attempts"
    )
    #: PROTECT so a published module cannot be deleted out from under history.
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="attempts")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=IN_PROGRESS)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=EXAM)

    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)

    current_section = models.PositiveSmallIntegerField(default=1)
    audio_started_at = models.DateTimeField(null=True, blank=True)
    audio_section_order = models.PositiveSmallIntegerField(null=True, blank=True)

    raw_score = models.PositiveSmallIntegerField(null=True, blank=True)
    band = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    marked_at = models.DateTimeField(null=True, blank=True)
    band_table_version = models.CharField(max_length=20, blank=True)

    integrity_events = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "module", "status"]),
            models.Index(fields=["user", "-submitted_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.module} ({self.status})"


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="+")
    question_number = models.PositiveSmallIntegerField()
    #: {"text": "..."} | {"letter": "B"} | {"letters": ["B", "D"]}
    value = models.JSONField(default=dict, blank=True)
    is_correct = models.BooleanField(null=True)
    awarded_marks = models.PositiveSmallIntegerField(default=0)
    #: correct | wrong | blank | over_word_limit | over_selected | partial
    mark_reason = models.CharField(max_length=24, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("attempt", "question")]
        ordering = ["attempt", "question_number"]

    def __str__(self) -> str:
        return f"{self.attempt_id} Q{self.question_number}"


class ImportJob(models.Model):
    """One run of the PDF importer, and the reviewable draft it produced."""

    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    FAILED = "failed"
    STATUS_CHOICES = (
        (QUEUED, "Queued"), (RUNNING, "Running"), (NEEDS_REVIEW, "Needs review"),
        (PUBLISHED, "Published"), (FAILED, "Failed"),
    )

    book = models.ForeignKey(
        Book, null=True, blank=True, on_delete=models.SET_NULL, related_name="import_jobs"
    )
    book_slug = models.SlugField(blank=True)
    source_file = models.FileField(upload_to="exam-sources/")
    #: sha256 of the uploaded file. Re-uploading the same book returns the
    #: existing job instead of redoing minutes of work.
    content_hash = models.CharField(max_length=64, db_index=True, blank=True)
    parser_version = models.CharField(max_length=20, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=QUEUED)
    stage = models.CharField(max_length=40, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)

    payload = models.JSONField(default=dict, blank=True)
    #: Bumped on every edit so concurrent review edits conflict loudly rather
    #: than silently overwriting one another.
    payload_version = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="exam_import_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ImportJob {self.pk} {self.book_slug} ({self.status})"
