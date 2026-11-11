from .services import unread_count


def notifications(request):
    """Unread count for the bell in the navigation bar."""
    return {"unread_notifications": unread_count(request.user) if hasattr(request, "user") else 0}
