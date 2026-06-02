"""Context processors for QCM app."""


def notifications(request):
    """Inject unread notifications and admin pending counts into all templates."""
    if not request.user.is_authenticated:
        return {
            "unread_notifications": [],
            "unread_notif_count": 0,
            "admin_alert_count": 0,
            "admin_pending_erratas": 0,
            "admin_pending_registrations": 0,
        }

    from .models import Notification

    unread = list(
        Notification.objects.filter(user=request.user, read=False).order_by(
            "-created_at"
        )[:10]
    )

    result: dict = {
        "unread_notifications": unread,
        "unread_notif_count": len(unread),
        "admin_alert_count": 0,
        "admin_pending_erratas": 0,
        "admin_pending_registrations": 0,
    }

    if request.user.is_staff:
        from .models import Errata, RegistrationRequest

        pending_erratas = Errata.objects.filter(status=Errata.PENDING).count()
        pending_registrations = RegistrationRequest.objects.filter(
            status=RegistrationRequest.PENDING
        ).count()
        result["admin_pending_erratas"] = pending_erratas
        result["admin_pending_registrations"] = pending_registrations
        result["admin_alert_count"] = pending_erratas + pending_registrations

    return result
