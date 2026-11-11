"""Workflow, request and evidence models.

These classes hold data and simple validation only. Every rule that changes a
request's state lives in ``apps.approvals.services.WorkflowService``.
"""
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse

from apps.core_immutable import ImmutableModel

from .storage import document_upload_to, private_storage

MAX_STAGES = 5


# ---------------------------------------------------------------- workflows


class WorkflowVersion(models.Model):
    """A numbered set of ordered stages. Frozen once published."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="workflow_versions")
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["project", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["project", "number"], name="approvals_workflow_number_per_project"),
        ]

    def __str__(self):
        return f"{self.project.code} workflow v{self.number}: {self.name}"

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    def save(self, *args, **kwargs):
        if not self._state.adding:
            previous = WorkflowVersion.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous == self.Status.PUBLISHED:
                raise ValueError("A published workflow version cannot be changed. Create a new version instead.")
        super().save(*args, **kwargs)


class StageDefinition(models.Model):
    """One ordered stage of a workflow version, with one named approver."""

    workflow_version = models.ForeignKey(WorkflowVersion, on_delete=models.CASCADE, related_name="stages")
    position = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(MAX_STAGES)])
    name = models.CharField(max_length=80)
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    due_hours = models.PositiveIntegerField(
        default=48, validators=[MinValueValidator(1), MaxValueValidator(24 * 30)],
        help_text="Hours the approver has to decide once the stage becomes active.",
    )

    class Meta:
        ordering = ["workflow_version", "position"]
        constraints = [
            models.UniqueConstraint(fields=["workflow_version", "position"], name="approvals_stage_position_unique"),
            models.CheckConstraint(
                condition=Q(position__gte=1) & Q(position__lte=MAX_STAGES), name="approvals_stage_position_1_to_5"
            ),
        ]

    def __str__(self):
        return f"Stage {self.position}: {self.name} ({self.approver})"

    def save(self, *args, **kwargs):
        if WorkflowVersion.objects.filter(pk=self.workflow_version_id, status=WorkflowVersion.Status.PUBLISHED).exists():
            raise ValueError("Stages of a published workflow version cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.workflow_version.is_published:
            raise ValueError("Stages of a published workflow version cannot be removed.")
        return super().delete(*args, **kwargs)


# ---------------------------------------------------------------- requests


class RequestState(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    IN_REVIEW = "IN_REVIEW", "In review"
    CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes requested"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


OPEN_STATES = {RequestState.DRAFT, RequestState.IN_REVIEW, RequestState.CHANGES_REQUESTED}
EDITABLE_STATES = {RequestState.DRAFT, RequestState.CHANGES_REQUESTED}


class ApprovalRequest(models.Model):
    """The case being approved (here, a software change request).

    ``title`` and ``description`` are the requester's working copy. Each
    submission freezes them into an immutable ``Revision``.
    """

    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="requests")
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requests")
    state = models.CharField(max_length=20, choices=RequestState.choices, default=RequestState.DRAFT, db_index=True)
    workflow_version = models.ForeignKey(
        WorkflowVersion, on_delete=models.PROTECT, null=True, blank=True, related_name="requests"
    )
    current_revision = models.ForeignKey(
        "Revision", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    closed_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["project", "number"], name="approvals_request_number_per_project"),
        ]

    def __str__(self):
        return f"{self.reference}: {self.title}"

    @property
    def reference(self):
        return f"{self.project.code}-{self.number:03d}"

    def get_absolute_url(self):
        return reverse("approvals:request_detail", args=[self.project.code, self.number])

    @property
    def is_open(self):
        return self.state in OPEN_STATES

    @property
    def is_editable(self):
        return self.state in EDITABLE_STATES

    def current_cycle(self):
        return self.cycles.order_by("-number").first()

    def active_task(self):
        if self.state != RequestState.IN_REVIEW:
            return None
        return (
            StageTask.objects.filter(cycle__request=self, status=StageTask.Status.ACTIVE)
            .select_related("approver", "stage_definition")
            .first()
        )


class Document(models.Model):
    """A named document attached to a request. Its content lives in versions."""

    request = models.ForeignKey(ApprovalRequest, on_delete=models.PROTECT, related_name="documents")
    name = models.CharField(max_length=150)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["request", "name"], name="approvals_document_name_per_request"),
        ]

    def __str__(self):
        return self.name

    def latest_version(self):
        return self.versions.order_by("-number").first()


class DocumentVersion(ImmutableModel):
    """One uploaded version of a document. Never overwritten."""

    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    file = models.FileField(storage=private_storage, upload_to=document_upload_to, max_length=255)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "number"]
        constraints = [
            models.UniqueConstraint(fields=["document", "number"], name="approvals_docversion_number_unique"),
        ]

    def __str__(self):
        return f"{self.document.name} v{self.number}"

    @property
    def short_checksum(self):
        return self.sha256[:12]


class Revision(ImmutableModel):
    """A frozen snapshot of the request content at submission."""

    request = models.ForeignKey(ApprovalRequest, on_delete=models.PROTECT, related_name="revisions")
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    document_versions = models.ManyToManyField(DocumentVersion, through="RevisionDocument", related_name="revisions")

    class Meta:
        ordering = ["request", "number"]
        constraints = [
            models.UniqueConstraint(fields=["request", "number"], name="approvals_revision_number_unique"),
        ]

    def __str__(self):
        return f"{self.request.reference} revision {self.number}"


class RevisionDocument(ImmutableModel):
    """Binds a revision to the exact document versions it includes."""

    revision = models.ForeignKey(Revision, on_delete=models.PROTECT, related_name="revision_documents")
    document_version = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["revision", "document_version"], name="approvals_revision_doc_unique"),
        ]


class ReviewCycle(models.Model):
    """One pass of a revision through the workflow's stages."""

    class Outcome(models.TextChoices):
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes requested"
        CANCELLED = "CANCELLED", "Cancelled"

    request = models.ForeignKey(ApprovalRequest, on_delete=models.PROTECT, related_name="cycles")
    number = models.PositiveIntegerField()
    revision = models.ForeignKey(Revision, on_delete=models.PROTECT, related_name="cycles")
    workflow_version = models.ForeignKey(WorkflowVersion, on_delete=models.PROTECT, related_name="+")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)

    class Meta:
        ordering = ["request", "number"]
        constraints = [
            models.UniqueConstraint(fields=["request", "number"], name="approvals_cycle_number_unique"),
        ]

    def __str__(self):
        return f"{self.request.reference} cycle {self.number}"

    @property
    def is_open(self):
        return self.ended_at is None


class StageTask(models.Model):
    """One stage within a cycle, with its approver and due time."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Waiting"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        CLOSED = "CLOSED", "Not reached"

    cycle = models.ForeignKey(ReviewCycle, on_delete=models.PROTECT, related_name="tasks")
    stage_definition = models.ForeignKey(StageDefinition, on_delete=models.PROTECT, related_name="+")
    position = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80)
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stage_tasks")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["cycle", "position"]
        constraints = [
            models.UniqueConstraint(fields=["cycle", "position"], name="approvals_task_position_unique"),
            models.UniqueConstraint(
                fields=["cycle"], condition=Q(status="ACTIVE"), name="approvals_one_active_task_per_cycle"
            ),
        ]

    def __str__(self):
        return f"{self.cycle} — stage {self.position} ({self.get_status_display()})"

    def activate(self, now, due_hours):
        self.status = self.Status.ACTIVE
        self.activated_at = now
        self.due_at = now + timedelta(hours=due_hours)

    @property
    def is_overdue(self):
        from django.utils import timezone

        return self.status == self.Status.ACTIVE and self.due_at is not None and self.due_at < timezone.now()


class Decision(ImmutableModel):
    """An approver's outcome on a stage task. One per task; never changed."""

    class Outcome(models.TextChoices):
        APPROVE = "APPROVE", "Approved"
        REJECT = "REJECT", "Rejected"
        REQUEST_CHANGES = "REQUEST_CHANGES", "Changes requested"

    task = models.OneToOneField(StageTask, on_delete=models.PROTECT, related_name="decision")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="decisions")
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(outcome="APPROVE") | ~Q(reason=""),
                name="approvals_decision_reason_required",
            ),
        ]

    def __str__(self):
        return f"{self.get_outcome_display()} by {self.actor} on {self.task}"
