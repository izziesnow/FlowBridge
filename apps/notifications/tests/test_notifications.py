"""In-app notifications (FR10) and overdue reminders."""
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.approvals.models import Decision, StageTask
from apps.approvals.services import WorkflowService
from apps.audit.models import AuditEvent
from apps.notifications.models import Notification
from apps.notifications.reminders import send_overdue_reminders

pytestmark = pytest.mark.django_db
A, C = Decision.Outcome.APPROVE, Decision.Outcome.REQUEST_CHANGES
Kind = Notification.Kind


def kinds_for(user):
    return list(Notification.objects.filter(recipient=user).values_list("kind", flat=True))


def test_submission_notifies_first_approver_only(submitted, people):
    assert kinds_for(people["approver1"]) == [Kind.ACTION_NEEDED]
    assert kinds_for(people["approver2"]) == []
    assert kinds_for(people["requester"]) == []


def test_approval_moves_the_action_to_the_next_approver_and_updates_requester(submitted, people):
    WorkflowService.decide(submitted, people["approver1"], A)
    assert Kind.ACTION_NEEDED in kinds_for(people["approver2"])
    assert Kind.DECISION in kinds_for(people["requester"])
    assert Kind.DECISION not in kinds_for(people["approver1"])  # the actor is never notified of their own act


def test_outcomes_reach_the_requester(submitted, people):
    WorkflowService.decide(submitted, people["approver1"], C, "Add rollback")
    note = Notification.objects.get(recipient=people["requester"], kind=Kind.OUTCOME)
    assert "Add rollback" in note.message and note.url == submitted.get_absolute_url()


def test_final_approval_notifies_requester_and_project_manager(submitted, people):
    WorkflowService.decide(submitted, people["approver1"], A)
    WorkflowService.decide(submitted, people["approver2"], A)
    assert Kind.OUTCOME in kinds_for(people["requester"])
    assert Kind.OUTCOME in kinds_for(people["pm"])


def test_unread_count_and_opening_marks_read(submitted, people, client_for):
    client = client_for(people["approver1"])
    page = client.get(reverse("dashboard"))
    assert page.context["unread_notifications"] == 1
    note = Notification.objects.get(recipient=people["approver1"])
    response = client.post(reverse("notifications:open", args=[note.pk]))
    assert response.status_code == 302 and response.url == submitted.get_absolute_url()
    note.refresh_from_db()
    assert note.read_at is not None


def test_users_cannot_open_other_peoples_notifications(submitted, people, client_for):
    note = Notification.objects.get(recipient=people["approver1"])
    assert client_for(people["outsider"]).post(reverse("notifications:open", args=[note.pk])).status_code == 404


def test_mark_all_read(submitted, people, client_for):
    WorkflowService.decide(submitted, people["approver1"], A)
    client = client_for(people["requester"])
    client.post(reverse("notifications:mark_all"))
    assert not Notification.objects.filter(recipient=people["requester"], read_at__isnull=True).exists()


# ------------------------------------------------------------ overdue reminders


def make_overdue(req, hours=5):
    task = StageTask.objects.get(cycle__request=req, status=StageTask.Status.ACTIVE)
    task.due_at = timezone.now() - timedelta(hours=hours)
    task.save(update_fields=["due_at"])
    return task


def test_stage_not_yet_due_gets_no_reminder(submitted):
    assert send_overdue_reminders().reminded == []


def test_overdue_stage_reminds_approver_and_first_reminder_tells_pm(submitted, people):
    make_overdue(submitted)
    run = send_overdue_reminders()
    assert len(run.reminded) == 1
    assert Kind.OVERDUE in kinds_for(people["approver1"])
    assert Kind.OVERDUE in kinds_for(people["pm"])
    assert AuditEvent.objects.filter(request=submitted, action="stage.overdue_reminder").count() == 1


def test_reminders_respect_the_interval(submitted, people, settings):
    settings.REMINDER_INTERVAL_HOURS = 24
    task = make_overdue(submitted)
    send_overdue_reminders()
    assert send_overdue_reminders().reminded == []  # a second run straight away sends nothing
    later = timezone.now() + timedelta(hours=25)
    send_overdue_reminders(now=later)
    task.refresh_from_db()
    assert task.reminder_count == 2
    assert kinds_for(people["pm"]).count(Kind.OVERDUE) == 1  # the PM is told only the first time


def test_dry_run_changes_nothing(submitted, capsys):
    task = make_overdue(submitted)
    call_command("send_reminders", "--dry-run")
    task.refresh_from_db()
    assert task.reminder_count == 0 and task.last_reminded_at is None
    assert not Notification.objects.filter(kind=Kind.OVERDUE).exists()
    assert "Would remind" in capsys.readouterr().out


def test_overdue_requests_are_flagged_and_filterable(submitted, draft, people, client_for):
    make_overdue(submitted)
    page = client_for(people["pm"]).get(reverse("projects:detail", args=["PAY"]) + "?overdue=1")
    rows = list(page.context["requests"])
    assert [r.pk for r in rows] == [submitted.pk] and rows[0].is_overdue
