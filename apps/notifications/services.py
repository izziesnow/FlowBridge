"""Creating and delivering notifications.

``notify`` is called inside the same transaction as the change it reports, so
a notification exists only if the change was committed (Section 3.4.4).

Email is optional (FR13). It is sent only to users who switched it on, and
only after the transaction commits, so a rolled-back action never sends mail.
A failed send is retried by ``python manage.py send_emails`` up to
``EMAIL_MAX_ATTEMPTS`` times.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Notification

log = logging.getLogger(__name__)


def email_enabled():
    return getattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)


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
        wants_email = email_enabled() and user.email_notifications
        rows.append(Notification(
            recipient=user, kind=kind, message=message[:255], url=url[:255], project=project, request=request,
            email_status=Notification.Email.PENDING if wants_email else Notification.Email.NONE,
        ))
    created = Notification.objects.bulk_create(rows)
    pending = [n.pk for n in created if n.email_status == Notification.Email.PENDING]
    if pending:
        transaction.on_commit(lambda: deliver_emails(pending))
    return created


def _absolute(url):
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    return f"{base}{url}" if base and url.startswith("/") else url


def deliver_emails(ids=None):
    """Send pending (or previously failed) notification emails. Returns (sent, failed)."""
    queue = Notification.objects.filter(
        email_status__in=[Notification.Email.PENDING, Notification.Email.FAILED],
        email_attempts__lt=settings.EMAIL_MAX_ATTEMPTS,
    ).select_related("recipient")
    if ids is not None:
        queue = queue.filter(pk__in=ids)
    sent = failed = 0
    for item in queue:
        Notification.objects.filter(pk=item.pk).update(email_attempts=F("email_attempts") + 1)
        body = (
            f"{item.message}\n\nOpen in Flowbridge: {_absolute(item.url)}\n\n"
            "You receive this because email notifications are switched on in your Flowbridge preferences.\n"
            "Flowbridge demonstration system. Zenkora Technologies Limited (ZTL) is a fictional organisation."
        )
        try:
            send_mail(f"[Flowbridge] {item.get_kind_display()}: {item.message[:80]}", body,
                      settings.DEFAULT_FROM_EMAIL, [item.recipient.email])
        except Exception as error:  # noqa: BLE001 - any transport error is recorded and retried later
            log.warning("Email for notification %s failed: %s", item.pk, error)
            Notification.objects.filter(pk=item.pk).update(
                email_status=Notification.Email.FAILED, email_error=str(error)[:255])
            failed += 1
        else:
            Notification.objects.filter(pk=item.pk).update(
                email_status=Notification.Email.SENT, email_sent_at=timezone.now(), email_error="")
            sent += 1
    return sent, failed


def unread_count(user):
    if not user.is_authenticated:
        return 0
    return Notification.objects.filter(recipient=user, read_at__isnull=True).count()
