"""Overdue stage reminders (FR10).

A stage is overdue when it is active and its due time has passed. Each run of
``send_reminders`` reminds the approver of every overdue stage, at most once
per ``REMINDER_INTERVAL_HOURS``. The first reminder for a stage also tells the
project manager, who can reassign it.

Rows are locked with ``SKIP LOCKED`` so two runs started together (for
example, a cron overlap) never remind the same stage twice.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.approvals.models import RequestState, StageTask
from apps.audit.models import record

from .models import Notification
from .services import notify


@dataclass
class ReminderRun:
    overdue: int = 0
    reminded: list = field(default_factory=list)


def interval():
    return timedelta(hours=getattr(settings, "REMINDER_INTERVAL_HOURS", 24))


def overdue_tasks(now=None):
    now = now or timezone.now()
    return StageTask.objects.filter(
        status=StageTask.Status.ACTIVE, due_at__lt=now, cycle__request__state=RequestState.IN_REVIEW
    )


def send_overdue_reminders(now=None, dry_run=False):
    from apps.approvals.services import project_managers

    now = now or timezone.now()
    run = ReminderRun()
    due_for_reminder = Q(last_reminded_at__isnull=True) | Q(last_reminded_at__lte=now - interval())
    with transaction.atomic():
        tasks = (
            overdue_tasks(now).filter(due_for_reminder)
            .select_for_update(skip_locked=True, of=("self",))
            .select_related("approver", "cycle__request__project")
            .order_by("due_at")
        )
        run.overdue = overdue_tasks(now).count()
        for task in tasks:
            request = task.cycle.request
            hours_late = max(1, int((now - task.due_at).total_seconds() // 3600))
            run.reminded.append((request.reference, task.position, task.approver.email, hours_late))
            if dry_run:
                continue
            first = task.reminder_count == 0
            task.last_reminded_at = now
            task.reminder_count += 1
            task.save(update_fields=["last_reminded_at", "reminder_count"])
            notify([task.approver], Notification.Kind.OVERDUE,
                   f"Reminder: {request.reference} stage {task.position} ({task.name}) is overdue by "
                   f"{hours_late} h and awaits your decision", request=request)
            if first:
                notify(project_managers(request.project), Notification.Kind.OVERDUE,
                       f"{request.reference} stage {task.position} is overdue with {task.approver}. "
                       f"You can reassign it from the request page.", request=request, exclude=[task.approver])
            record("stage.overdue_reminder",
                   f"{request.reference}: reminder {task.reminder_count} sent for overdue stage {task.position}",
                   request=request, stage=task.position, cycle=task.cycle.number, approver=task.approver.email,
                   hours_late=hours_late)
        if dry_run:
            transaction.set_rollback(True)
    return run
