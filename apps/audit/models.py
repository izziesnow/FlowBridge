from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core_immutable import ImmutableModel


class AuditEvent(ImmutableModel):
    """An append-only record of who did what, and when.

    Rows can be inserted but never changed or deleted. The model refuses
    updates and deletes, and a PostgreSQL trigger (see the migration) refuses
    them at database level as well, including bulk queryset operations.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    action = models.CharField(max_length=60, db_index=True)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, null=True, blank=True, related_name="audit_events"
    )
    request = models.ForeignKey(
        "approvals.ApprovalRequest", on_delete=models.PROTECT, null=True, blank=True, related_name="audit_events"
    )
    summary = models.CharField(max_length=255)
    data = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["project", "-created_at"]), models.Index(fields=["request", "-created_at"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action}: {self.summary}"


def record(action, summary, *, actor=None, project=None, request=None, **data):
    """Write one audit event. Call inside the same transaction as the change it records."""
    if request is not None and project is None:
        project = request.project
    return AuditEvent.objects.create(
        actor=actor, action=action, summary=summary[:255], project=project, request=request, data=data
    )
