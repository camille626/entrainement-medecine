"""Context processors for QCM app."""


def notifications(request):
    """Inject unread notifications count into all templates."""
    if not request.user.is_authenticated:
        return {"unread_notifications": [], "unread_notif_count": 0}
    from .models import Notification

    unread = list(
        Notification.objects.filter(user=request.user, read=False).order_by(
            "-created_at"
        )[:10]
    )
    return {
        "unread_notifications": unread,
        "unread_notif_count": len(unread),
    }
