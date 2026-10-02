from django.urls import path

from exams import admin_views, views

urlpatterns = [
    # --- student ---------------------------------------------------------
    path("tests", views.TestListAPIView.as_view(), name="exam-tests"),
    path("overall-band", views.OverallBandAPIView.as_view(), name="exam-overall-band"),
    path("attempts", views.AttemptHistoryAPIView.as_view(), name="exam-attempts"),
    path(
        "modules/<int:module_id>/attempts",
        views.AttemptStartAPIView.as_view(), name="exam-attempt-start",
    ),
    path(
        "attempts/<int:attempt_id>",
        views.AttemptDetailAPIView.as_view(), name="exam-attempt-detail",
    ),
    path(
        "attempts/<int:attempt_id>/answers",
        views.AttemptAnswersAPIView.as_view(), name="exam-attempt-answers",
    ),
    path(
        "attempts/<int:attempt_id>/advance",
        views.AttemptAdvanceAPIView.as_view(), name="exam-attempt-advance",
    ),
    path(
        "attempts/<int:attempt_id>/submit",
        views.AttemptSubmitAPIView.as_view(), name="exam-attempt-submit",
    ),
    path(
        "attempts/<int:attempt_id>/result",
        views.AttemptResultAPIView.as_view(), name="exam-attempt-result",
    ),
    path(
        "attempts/<int:attempt_id>/audio/<int:section_id>",
        views.AttemptAudioAPIView.as_view(), name="exam-attempt-audio",
    ),

    # --- admin -----------------------------------------------------------
    path(
        "admin/import-jobs",
        admin_views.ImportJobListCreateAPIView.as_view(), name="exam-import-jobs",
    ),
    path(
        "admin/import-jobs/<int:job_id>",
        admin_views.ImportJobDetailAPIView.as_view(), name="exam-import-job",
    ),
    path(
        "admin/import-jobs/<int:job_id>/publish",
        admin_views.ImportJobPublishAPIView.as_view(), name="exam-import-publish",
    ),
    path(
        "admin/modules",
        admin_views.AdminModuleListAPIView.as_view(), name="exam-admin-modules",
    ),
    path(
        "admin/modules/<int:module_id>",
        admin_views.AdminModuleDetailAPIView.as_view(), name="exam-admin-module",
    ),
    path(
        "admin/modules/<int:module_id>/answer-sheet",
        admin_views.AnswerSheetAPIView.as_view(), name="exam-answer-sheet",
    ),
    path(
        "admin/modules/<int:module_id>/answer-sheet/verify",
        admin_views.AnswerSheetVerifyAPIView.as_view(), name="exam-answer-sheet-verify",
    ),
    path(
        "admin/modules/<int:module_id>/answer-sheet/cells/<int:number>/reveal",
        admin_views.AnswerSheetRevealAPIView.as_view(), name="exam-answer-sheet-reveal",
    ),
    path(
        "admin/modules/<int:module_id>/answer-sheet/cells/<int:number>/crop",
        admin_views.AnswerSheetCropAPIView.as_view(), name="exam-answer-sheet-crop",
    ),
    path(
        "admin/modules/<int:module_id>/answer-sheet/correct",
        admin_views.AnswerSheetCorrectAPIView.as_view(), name="exam-answer-sheet-correct",
    ),
    path("admin/audio", admin_views.AudioUploadAPIView.as_view(), name="exam-audio"),
    path(
        "admin/audio/<int:asset_id>",
        admin_views.AudioAssignAPIView.as_view(), name="exam-audio-assign",
    ),
]
