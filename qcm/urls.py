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
        "entrainement/session/<int:pk>/fin/",
        views.FinView.as_view(),
        name="fin",
    ),
]
