"""Discussion beside the structured record (Section 2.1.2: a structured approval with an attached thread).

Comments and project messages are append-only: they cannot be edited or
deleted, so the conversation around a decision stays as it was when the
decision was made.
"""
from django.conf import settings
from django.db import models

from apps.core_immutable import ImmutableModel


class Comment(ImmutableModel):
    """A discussion entry on a request, linked to the revision being discussed."""

    request = models.ForeignKey("approvals.ApprovalRequest", on_delete=models.PROTECT, related_name="comments")
    revision = models.ForeignKey(
        "approvals.Revision", on_delete=models.PROTECT, null=True, blank=True, related_name="comments",
        help_text="The revision current when the comment was written; empty while the request is a draft.",
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Comment by {self.author} on {self.request.reference}"


class ProjectMessage(ImmutableModel):
    """A message in a project's general discussion."""

    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Message by {self.author} in {self.project.code}"
