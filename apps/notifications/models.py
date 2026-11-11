from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """An in-app message to one user. Read or unread."""

    class Kind(models.TextChoices):
        ACTION_NEEDED = "ACTION_NEEDED", "Action needed"
        DECISION = "DECISION", "Decision recorded"
        OUTCOME = "OUTCOME", "Request outcome"
        COMMENT = "COMMENT", "New comment"
        DISCUSSION = "DISCUSSION", "Project discussion"
        REASSIGNED = "REASSIGNED", "Stage reassigned"
        OVERDUE = "OVERDUE", "Overdue reminder"
        WITHDRAWN = "WITHDRAWN", "Request withdrawn"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    request = models.ForeignKey(
        "approvals.ApprovalRequest", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "read_at"], name="notif_recipient_unread_idx")]

    def __str__(self):
        return f"To {self.recipient}: {self.message}"

    @property
    def is_unread(self):
        return self.read_at is None

    def mark_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at"])
