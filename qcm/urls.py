from django.urls import path

from . import views


app_name = "qcm"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("entrainement/", views.ConfigurationView.as_view(), name="configuration"),
    path(
        "entrainement/session/<int:pk>/",
        views.QuestionView.as_view(),
        name="question",
    ),
    path(
        "entrainement/session/<int:pk>/check/",
        views.CheckView.as_view(),
        name="check",
    ),
    path(
        "entrainement/session/<int:pk>/check-qroc/",
        views.CheckQROCSelfView.as_view(),
        name="check_qroc",
    ),
    path(
        "entrainement/session/<int:pk>/fin/",
        views.FinView.as_view(),
        name="fin",
    ),
    path("entrainement/tags/", views.TagsView.as_view(), name="tags"),
    path("entrainement/chapters/", views.ChaptersView.as_view(), name="chapters"),
    path("statistiques/", views.StatsView.as_view(), name="stats"),
    path("errata/", views.ErrataListView.as_view(), name="errata_list"),
    path(
        "errata/<int:pk>/accept/",
        views.ErrataAcceptView.as_view(),
        name="errata_accept",
    ),
    path(
        "errata/<int:pk>/reject/",
        views.ErrataRejectView.as_view(),
        name="errata_reject",
    ),
    path(
        "errata/<int:pk>/feedback/",
        views.ErrataFeedbackView.as_view(),
        name="errata_feedback",
    ),
    path(
        "notifications/<int:pk>/mark-read/",
        views.NotificationMarkReadView.as_view(),
        name="notification_mark_read",
    ),
    path(
        "errata/question/<int:question_id>/",
        views.ErrataSubmitView.as_view(),
        name="errata_submit",
    ),
    path("historique/", views.HistoryView.as_view(), name="history"),
    path(
        "historique/session/<int:pk>/",
        views.SessionDetailView.as_view(),
        name="session_detail",
    ),
    path(
        "statistiques/cours/<int:course_id>/",
        views.CourseStatsView.as_view(),
        name="course_stats",
    ),
    path(
        "questions/upload/",
        views.AdminQuestionsUploadView.as_view(),
        name="questions_upload",
    ),
    path(
        "questions/upload/preview/",
        views.AdminQuestionsPreviewView.as_view(),
        name="questions_preview",
    ),
    path(
        "questions/confirmer/",
        views.AdminQuestionsConfirmView.as_view(),
        name="questions_confirm",
    ),
    path("inscription/", views.InscriptionView.as_view(), name="inscription"),
    path(
        "inscription/merci/",
        views.InscriptionDoneView.as_view(),
        name="inscription_done",
    ),
]
