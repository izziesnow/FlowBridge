"""Optional email notifications (FR13)."""
import pytest
from django.core import mail
from django.core.management import call_command
from django.urls import reverse

from apps.approvals.services import WorkflowService
from apps.notifications.models import Notification
from apps.notifications.services import deliver_emails

pytestmark = pytest.mark.django_db
Email = Notification.Email


def opt_in(user):
    user.email_notifications = True
    user.save(update_fields=["email_notifications"])


def test_no_email_unless_the_user_opts_in(draft, people, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        WorkflowService.submit(draft, people["requester"])
    assert mail.outbox == []
    assert Notification.objects.get(recipient=people["approver1"]).email_status == Email.NONE


def test_opted_in_user_gets_email_after_commit(draft, people, django_capture_on_commit_callbacks):
    opt_in(people["approver1"])
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        WorkflowService.submit(draft, people["requester"])
    assert mail.outbox == [] and len(callbacks) == 1  # nothing is sent before the transaction commits
    callbacks[0]()
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == [people["approver1"].email] and draft.reference in message.subject
    assert "fictional" in message.body
    assert Notification.objects.get(recipient=people["approver1"]).email_status == Email.SENT


def test_failed_email_is_recorded_and_retried(draft, people, settings, django_capture_on_commit_callbacks):
    opt_in(people["approver1"])
    settings.EMAIL_BACKEND = "apps.notifications.tests.failing_backend.FailingBackend"
    with django_capture_on_commit_callbacks(execute=True):
        WorkflowService.submit(draft, people["requester"])
    note = Notification.objects.get(recipient=people["approver1"])
    assert note.email_status == Email.FAILED and note.email_attempts == 1 and "unreachable" in note.email_error

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    call_command("send_emails")
    note.refresh_from_db()
    assert note.email_status == Email.SENT and note.email_attempts == 2 and len(mail.outbox) == 1


def test_retries_stop_after_the_limit(draft, people, settings, django_capture_on_commit_callbacks):
    opt_in(people["approver1"])
    settings.EMAIL_BACKEND = "apps.notifications.tests.failing_backend.FailingBackend"
    with django_capture_on_commit_callbacks(execute=True):
        WorkflowService.submit(draft, people["requester"])
    for _ in range(5):
        deliver_emails()
    assert Notification.objects.get(recipient=people["approver1"]).email_attempts == settings.EMAIL_MAX_ATTEMPTS


def test_preferences_page_switches_email_on_and_is_audited(people, client_for):
    client = client_for(people["viewer"])
    client.post(reverse("accounts:preferences"), {"email_notifications": "on"})
    people["viewer"].refresh_from_db()
    assert people["viewer"].email_notifications
    from apps.audit.models import AuditEvent
    assert AuditEvent.objects.filter(action="account.preferences", actor=people["viewer"]).exists()
