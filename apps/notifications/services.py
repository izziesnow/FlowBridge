"""Creating notifications.

``notify`` is called inside the same transaction as the change it reports, so
a notification exists only if the change was committed (Section 3.4.4).
"""
from .models import Notification


def notify(recipients, kind, message, *, request=None, project=None, url="", exclude=None):
    """Create one notification per distinct, active recipient, skipping anyone in ``exclude``."""
    if request is not None:
        project = project or request.project
        url = url or request.get_absolute_url()
    skip = {u.pk for u in (exclude or []) if u is not None}
    seen = set()
    rows = []
    for user in recipients:
        if user is None or not user.is_active or user.pk in skip or user.pk in seen:
            continue
        seen.add(user.pk)
        rows.append(Notification(recipient=user, kind=kind, message=message[:255], url=url[:255],
                                 project=project, request=request))
    return Notification.objects.bulk_create(rows)


def unread_count(user):
    if not user.is_authenticated:
        return 0
    return Notification.objects.filter(recipient=user, read_at__isnull=True).count()
