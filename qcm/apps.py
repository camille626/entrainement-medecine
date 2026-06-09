from django.apps import AppConfig


class QcmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "qcm"
    verbose_name = "QCM Médecine"

    def ready(self) -> None:
        from django.contrib.auth.signals import user_logged_in

        def on_user_logged_in(sender, request, user, **kwargs):  # type: ignore[no-untyped-def]
            from qcm.models import LoginEvent
            from qcm.trophies import award_login_trophies

            LoginEvent.objects.create(user=user)
            if request is not None:
                award_login_trophies(request, user)

        user_logged_in.connect(on_user_logged_in)
