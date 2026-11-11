"""WorkflowService: the single place where request state changes.

Every operation:

* runs in one database transaction, so the change, its evidence and its audit
  event are recorded together or not at all;
* locks the request row with ``SELECT ... FOR UPDATE`` before reading its
  state, so two simultaneous actions on one request are applied one after the
  other and the second sees the first one's result;
* checks the actor's project role and the transition guard from Table 3.x
  (the state-transition table in Chapter Three) before changing anything.

Views never change ``ApprovalRequest.state`` themselves.
"""
import hashlib
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import record
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.projects.access import get_role
from apps.projects.models import Project, Role

from .models import (
    MAX_STAGES,
    ApprovalRequest,
    Decision,
    Document,
    DocumentVersion,
    Reassignment,
    RequestState,
    ReviewCycle,
    Revision,
    RevisionDocument,
    StageDefinition,
    StageTask,
    WorkflowVersion,
)


class WorkflowError(ValidationError):
    """A guard failed: the action is not allowed in the request's current state."""


def _require_role(user, project, *roles, message="You do not have permission to do this."):
    if get_role(user, project) not in roles:
        raise PermissionDenied(message)


def _require_reason(reason, action):
    reason = (reason or "").strip()
    if not reason:
        raise WorkflowError(f"A reason is required to {action}.")
    return reason


def _lock_request(request):
    """Re-read the request row under a row lock. Must be called inside a transaction."""
    return ApprovalRequest.objects.select_for_update().select_related("project").get(pk=request.pk)


def project_managers(project):
    return User.objects.filter(memberships__project=project, memberships__role=Role.PM, is_active=True)


def _notify_action_needed(request, task):
    notify([task.approver], Notification.Kind.ACTION_NEEDED,
           f"{request.reference} is awaiting your decision at stage {task.position}: {task.name}", request=request)


def latest_published_workflow(project):
    return (
        WorkflowVersion.objects.filter(project=project, status=WorkflowVersion.Status.PUBLISHED)
        .order_by("-number")
        .first()
    )


def _checksum(django_file):
    digest = hashlib.sha256()
    for chunk in django_file.chunks():
        digest.update(chunk)
    django_file.seek(0)
    return digest.hexdigest()


def validate_upload(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower().lstrip(".")
    if extension not in settings.DOCUMENT_ALLOWED_EXTENSIONS:
        allowed = ", ".join(settings.DOCUMENT_ALLOWED_EXTENSIONS)
        raise WorkflowError(f"Files of type .{extension or '?'} are not accepted. Allowed: {allowed}.")
    if uploaded_file.size > settings.DOCUMENT_MAX_UPLOAD_BYTES:
        limit = settings.DOCUMENT_MAX_UPLOAD_BYTES // (1024 * 1024)
        raise WorkflowError(f"Files must be {limit} MB or smaller.")
    if uploaded_file.size == 0:
        raise WorkflowError("The file is empty.")


class WorkflowService:
    """All operations that create or change workflow and request records."""

    # ------------------------------------------------------------ workflows

    @staticmethod
    @transaction.atomic
    def create_workflow_version(project, actor, name):
        _require_role(actor, project, Role.PM, message="Only the project manager can design workflows.")
        Project.objects.select_for_update().get(pk=project.pk)
        number = (project.workflow_versions.aggregate(n=Max("number"))["n"] or 0) + 1
        version = WorkflowVersion.objects.create(project=project, number=number, name=name.strip(), created_by=actor)
        record("workflow.created", f"Workflow v{number} '{version.name}' created", actor=actor, project=project,
               workflow_version=version.pk)
        return version

    @staticmethod
    @transaction.atomic
    def add_stage(version, actor, name, approver, due_hours=48):
        version = WorkflowVersion.objects.select_for_update().get(pk=version.pk)
        project = version.project
        _require_role(actor, project, Role.PM, message="Only the project manager can design workflows.")
        if version.is_published:
            raise WorkflowError("This workflow version is published and cannot be changed.")
        count = version.stages.count()
        if count >= MAX_STAGES:
            raise WorkflowError(f"A workflow can have at most {MAX_STAGES} stages.")
        if get_role(approver, project) not in (Role.APPROVER, Role.PM):
            raise WorkflowError(f"{approver} must be an approver (or the project manager) on {project.code}.")
        stage = StageDefinition.objects.create(
            workflow_version=version, position=count + 1, name=name.strip(), approver=approver, due_hours=due_hours
        )
        record("workflow.stage_added", f"Stage {stage.position} '{stage.name}' added to workflow v{version.number}",
               actor=actor, project=project, workflow_version=version.pk, approver=approver.email)
        return stage

    @staticmethod
    @transaction.atomic
    def remove_last_stage(version, actor):
        version = WorkflowVersion.objects.select_for_update().get(pk=version.pk)
        _require_role(actor, version.project, Role.PM, message="Only the project manager can design workflows.")
        if version.is_published:
            raise WorkflowError("This workflow version is published and cannot be changed.")
        stage = version.stages.order_by("-position").first()
        if stage is None:
            raise WorkflowError("This workflow has no stages to remove.")
        stage.delete()
        record("workflow.stage_removed", f"Stage {stage.position} removed from workflow v{version.number}",
               actor=actor, project=version.project, workflow_version=version.pk)

    @staticmethod
    @transaction.atomic
    def publish_workflow(version, actor):
        version = WorkflowVersion.objects.select_for_update().get(pk=version.pk)
        project = version.project
        _require_role(actor, project, Role.PM, message="Only the project manager can publish workflows.")
        if version.is_published:
            raise WorkflowError("This workflow version is already published.")
        stages = list(version.stages.order_by("position"))
        if not 1 <= len(stages) <= MAX_STAGES:
            raise WorkflowError(f"A workflow must have between 1 and {MAX_STAGES} stages before it is published.")
        if [s.position for s in stages] != list(range(1, len(stages) + 1)):
            raise WorkflowError("Stage positions must run 1, 2, 3 … without gaps.")
        for stage in stages:
            if get_role(stage.approver, project) not in (Role.APPROVER, Role.PM):
                raise WorkflowError(f"{stage.approver} is no longer an approver on {project.code}.")
        WorkflowVersion.objects.filter(pk=version.pk).update(
            status=WorkflowVersion.Status.PUBLISHED, published_by=actor, published_at=timezone.now()
        )
        version.refresh_from_db()
        record("workflow.published", f"Workflow v{version.number} '{version.name}' published with {len(stages)} stage(s)",
               actor=actor, project=project, workflow_version=version.pk,
               stages=[{"position": s.position, "name": s.name, "approver": s.approver.email} for s in stages])
        return version

    # ------------------------------------------------------------ drafts and documents

    @staticmethod
    @transaction.atomic
    def create_request(project, actor, title, description=""):
        _require_role(actor, project, Role.REQUESTER, message="Only requesters can raise requests on this project.")
        Project.objects.select_for_update().get(pk=project.pk)
        number = (project.requests.aggregate(n=Max("number"))["n"] or 0) + 1
        request = ApprovalRequest.objects.create(
            project=project, number=number, title=title.strip(), description=description.strip(), requester=actor
        )
        record("request.created", f"{request.reference} created as a draft", actor=actor, request=request)
        return request

    @staticmethod
    @transaction.atomic
    def update_content(request, actor, title, description):
        request = _lock_request(request)
        if actor != request.requester:
            raise PermissionDenied("Only the requester can edit this request.")
        if not request.is_editable:
            raise WorkflowError("The request can only be edited while it is a draft or after changes are requested.")
        request.title = title.strip()
        request.description = description.strip()
        request.save(update_fields=["title", "description", "updated_at"])
        record("request.edited", f"{request.reference} content edited", actor=actor, request=request)
        return request

    @staticmethod
    @transaction.atomic
    def add_document_version(request, actor, uploaded_file, name=None, document=None):
        """Upload a new document, or a new version of an existing one. Earlier versions are kept."""
        request = _lock_request(request)
        if actor != request.requester:
            raise PermissionDenied("Only the requester can attach documents to this request.")
        if not request.is_editable:
            raise WorkflowError("Documents can only be added while the request is a draft or after changes are requested.")
        validate_upload(uploaded_file)
        if document is None:
            name = (name or Path(uploaded_file.name).stem).strip()[:150]
            document, created = Document.objects.get_or_create(
                request=request, name=name, defaults={"created_by": actor}
            )
        elif document.request_id != request.pk:
            raise PermissionDenied("That document belongs to a different request.")
        number = (document.versions.aggregate(n=Max("number"))["n"] or 0) + 1
        version = DocumentVersion(
            document=document,
            number=number,
            original_filename=Path(uploaded_file.name).name[:255],
            content_type=(getattr(uploaded_file, "content_type", "") or mimetypes.guess_type(uploaded_file.name)[0] or "")[:120],
            size_bytes=uploaded_file.size,
            sha256=_checksum(uploaded_file),
            uploaded_by=actor,
        )
        version.file.save(uploaded_file.name, uploaded_file, save=False)
        version.save()
        record("document.uploaded", f"'{document.name}' v{number} uploaded to {request.reference}", actor=actor,
               request=request, document=document.pk, version=number, sha256=version.sha256,
               filename=version.original_filename)
        return version

    # ------------------------------------------------------------ transitions

    @staticmethod
    def _freeze_revision(request, actor):
        number = (request.revisions.aggregate(n=Max("number"))["n"] or 0) + 1
        revision = Revision.objects.create(
            request=request, number=number, title=request.title, description=request.description, created_by=actor
        )
        versions = [d.latest_version() for d in request.documents.all()]
        for version in versions:
            if version is not None:
                RevisionDocument.objects.create(revision=revision, document_version=version)
        return revision

    @staticmethod
    def _start_cycle(request, revision, workflow, now):
        number = (request.cycles.aggregate(n=Max("number"))["n"] or 0) + 1
        cycle = ReviewCycle.objects.create(request=request, number=number, revision=revision, workflow_version=workflow)
        stages = list(workflow.stages.order_by("position"))
        for stage in stages:
            task = StageTask(cycle=cycle, stage_definition=stage, position=stage.position, name=stage.name,
                             approver=stage.approver)
            if stage.position == 1:
                task.activate(now, stage.due_hours)
            task.save()
        return cycle

    @staticmethod
    def _check_separation_of_duties(request, workflow):
        if workflow.stages.filter(approver=request.requester).exists():
            raise WorkflowError(
                "You are a named approver in this workflow, and requesters cannot approve their own requests. "
                "Ask the project manager to publish a workflow with a different approver."
            )

    @classmethod
    @transaction.atomic
    def submit(cls, request, actor):
        """Draft → In review. Freezes revision 1 and activates stage 1."""
        request = _lock_request(request)
        if actor != request.requester or get_role(actor, request.project) != Role.REQUESTER:
            raise PermissionDenied("Only the requester can submit this request.")
        if request.state != RequestState.DRAFT:
            raise WorkflowError("Only a draft can be submitted.")
        if not request.title.strip() or not request.description.strip():
            raise WorkflowError("A title and a description are required before submission.")
        workflow = latest_published_workflow(request.project)
        if workflow is None:
            raise WorkflowError("This project has no published workflow yet. Ask the project manager to publish one.")
        cls._check_separation_of_duties(request, workflow)
        now = timezone.now()
        revision = cls._freeze_revision(request, actor)
        cycle = cls._start_cycle(request, revision, workflow, now)
        request.workflow_version = workflow
        request.current_revision = revision
        request.state = RequestState.IN_REVIEW
        request.save(update_fields=["workflow_version", "current_revision", "state", "updated_at"])
        record("request.submitted", f"{request.reference} submitted (revision {revision.number}, cycle {cycle.number})",
               actor=actor, request=request, revision=revision.number, cycle=cycle.number,
               workflow_version=workflow.number,
               documents=[{"id": rd.document_version_id} for rd in revision.revision_documents.all()])
        _notify_action_needed(request, cycle.tasks.get(position=1))
        return request

    @classmethod
    @transaction.atomic
    def decide(cls, request, actor, outcome, reason=""):
        """Record an approver's decision on the active stage.

        The request row is locked first. A second, simultaneous decision waits
        for the lock, then finds that the task is no longer active and is refused.
        """
        request = _lock_request(request)
        if request.state != RequestState.IN_REVIEW:
            raise WorkflowError("This request is not awaiting a decision.")
        task = (
            StageTask.objects.select_for_update()
            .select_related("cycle", "stage_definition")
            .filter(cycle__request=request, status=StageTask.Status.ACTIVE)
            .first()
        )
        if task is None:
            raise WorkflowError("There is no active stage to decide.")
        if actor == request.requester:
            raise PermissionDenied("Requesters cannot approve or reject their own requests.")
        if actor != task.approver or get_role(actor, request.project) not in (Role.APPROVER, Role.PM):
            raise PermissionDenied("Only the approver assigned to the active stage can decide.")
        if outcome not in Decision.Outcome.values:
            raise WorkflowError("Unknown decision.")
        if outcome != Decision.Outcome.APPROVE:
            verb = "reject" if outcome == Decision.Outcome.REJECT else "request changes"
            reason = _require_reason(reason, verb)
        else:
            reason = (reason or "").strip()

        now = timezone.now()
        decision = Decision.objects.create(task=task, actor=actor, outcome=outcome, reason=reason)
        task.status = StageTask.Status.COMPLETED
        task.completed_at = now
        task.save(update_fields=["status", "completed_at"])
        cycle = task.cycle

        if outcome == Decision.Outcome.APPROVE:
            next_task = cycle.tasks.filter(position=task.position + 1).select_related("stage_definition").first()
            if next_task is not None:
                next_task.activate(now, next_task.stage_definition.due_hours)
                next_task.save(update_fields=["status", "activated_at", "due_at"])
                summary = f"Stage {task.position} approved; stage {next_task.position} '{next_task.name}' now active"
                _notify_action_needed(request, next_task)
                notify([request.requester], Notification.Kind.DECISION,
                       f"{request.reference}: stage {task.position} approved by {actor}; now with {next_task.approver}",
                       request=request, exclude=[actor])
            else:
                cls._end_cycle(cycle, ReviewCycle.Outcome.APPROVED, now)
                request.state = RequestState.APPROVED
                summary = f"Final stage approved; {request.reference} approved"
                notify([request.requester, *project_managers(request.project)], Notification.Kind.OUTCOME,
                       f"{request.reference} has been approved", request=request, exclude=[actor])
        elif outcome == Decision.Outcome.REJECT:
            cls._end_cycle(cycle, ReviewCycle.Outcome.REJECTED, now)
            request.state = RequestState.REJECTED
            summary = f"Rejected at stage {task.position}"
            notify([request.requester, *project_managers(request.project)], Notification.Kind.OUTCOME,
                   f"{request.reference} was rejected by {actor}: {reason}", request=request, exclude=[actor])
        else:
            cls._end_cycle(cycle, ReviewCycle.Outcome.CHANGES_REQUESTED, now)
            request.state = RequestState.CHANGES_REQUESTED
            summary = f"Changes requested at stage {task.position}; cycle {cycle.number} ended"
            notify([request.requester], Notification.Kind.OUTCOME,
                   f"{actor} requested changes to {request.reference}: {reason}", request=request, exclude=[actor])

        request.save(update_fields=["state", "updated_at"])
        record(f"decision.{outcome.lower()}", f"{request.reference}: {summary}", actor=actor, request=request,
               cycle=cycle.number, stage=task.position, revision=cycle.revision.number, reason=reason,
               decision=decision.pk)
        return decision

    @staticmethod
    def _end_cycle(cycle, outcome, now):
        cycle.tasks.filter(status__in=[StageTask.Status.PENDING, StageTask.Status.ACTIVE]).update(
            status=StageTask.Status.CLOSED
        )
        cycle.outcome = outcome
        cycle.ended_at = now
        cycle.save(update_fields=["outcome", "ended_at"])

    @classmethod
    @transaction.atomic
    def resubmit(cls, request, actor):
        """Changes requested → In review. New revision, new cycle restarting at stage 1."""
        request = _lock_request(request)
        if actor != request.requester or get_role(actor, request.project) != Role.REQUESTER:
            raise PermissionDenied("Only the requester can resubmit this request.")
        if request.state != RequestState.CHANGES_REQUESTED:
            raise WorkflowError("Only a request with changes requested can be resubmitted.")
        previous = request.current_revision
        current_docs = {d.latest_version().pk for d in request.documents.all() if d.latest_version()}
        previous_docs = set(previous.revision_documents.values_list("document_version_id", flat=True))
        unchanged = (
            request.title == previous.title
            and request.description == previous.description
            and current_docs == previous_docs
        )
        if unchanged:
            raise WorkflowError("Make a change to the content or documents before resubmitting.")
        workflow = request.workflow_version
        cls._check_separation_of_duties(request, workflow)
        now = timezone.now()
        revision = cls._freeze_revision(request, actor)
        cycle = cls._start_cycle(request, revision, workflow, now)
        request.current_revision = revision
        request.state = RequestState.IN_REVIEW
        request.save(update_fields=["current_revision", "state", "updated_at"])
        record("request.resubmitted",
               f"{request.reference} resubmitted as revision {revision.number}; cycle {cycle.number} restarts at stage 1",
               actor=actor, request=request, revision=revision.number, cycle=cycle.number,
               previous_revision=previous.number)
        _notify_action_needed(request, cycle.tasks.get(position=1))
        return request

    @classmethod
    @transaction.atomic
    def withdraw(cls, request, actor, reason):
        """Draft, In review or Changes requested → Cancelled. Requester or PM, with a reason."""
        request = _lock_request(request)
        role = get_role(actor, request.project)
        if not (actor == request.requester or role == Role.PM):
            raise PermissionDenied("Only the requester or the project manager can withdraw this request.")
        if not request.is_open:
            raise WorkflowError("This request is already closed.")
        reason = _require_reason(reason, "withdraw a request")
        now = timezone.now()
        cycle = request.cycles.filter(ended_at__isnull=True).first()
        active = cycle.tasks.filter(status=StageTask.Status.ACTIVE).select_related("approver").first() if cycle else None
        if cycle is not None:
            cls._end_cycle(cycle, ReviewCycle.Outcome.CANCELLED, now)
        previous_state = request.state
        request.state = RequestState.CANCELLED
        request.closed_reason = reason
        request.save(update_fields=["state", "closed_reason", "updated_at"])
        record("request.withdrawn", f"{request.reference} withdrawn", actor=actor, request=request,
               reason=reason, previous_state=previous_state)
        notify([request.requester, active.approver if active else None], Notification.Kind.WITHDRAWN,
               f"{request.reference} was withdrawn by {actor}: {reason}", request=request, exclude=[actor])
        return request

    @classmethod
    @transaction.atomic
    def reassign_stage(cls, request, actor, task, new_approver, reason):
        """Project manager moves an active or waiting stage of the open cycle to another approver.

        Only the current cycle changes. The published workflow stays as it is, so
        later cycles use its named approvers again. The change is kept as an
        immutable Reassignment record and an audit event.
        """
        request = _lock_request(request)
        project = request.project
        if get_role(actor, project) != Role.PM:
            raise PermissionDenied("Only the project manager can reassign a stage.")
        if request.state != RequestState.IN_REVIEW:
            raise WorkflowError("Stages can only be reassigned while the request is in review.")
        task = StageTask.objects.select_for_update().select_related("cycle", "stage_definition", "approver").get(pk=task.pk)
        if task.cycle.request_id != request.pk or task.cycle.ended_at is not None:
            raise WorkflowError("That stage is not part of the request's open review cycle.")
        if task.status not in (StageTask.Status.ACTIVE, StageTask.Status.PENDING):
            raise WorkflowError("Only an active or waiting stage can be reassigned.")
        reason = _require_reason(reason, "reassign a stage")
        if new_approver == task.approver:
            raise WorkflowError(f"{new_approver} is already the approver for this stage.")
        if new_approver == request.requester:
            raise WorkflowError("The requester cannot approve their own request.")
        if not new_approver.is_active or get_role(new_approver, project) not in (Role.APPROVER, Role.PM):
            raise WorkflowError(f"{new_approver} must be an active approver (or the project manager) on {project.code}.")

        previous = task.approver
        now = timezone.now()
        task.approver = new_approver
        fields = ["approver"]
        if task.status == StageTask.Status.ACTIVE:
            # The new approver gets the stage's full decision window from now.
            task.activate(now, task.stage_definition.due_hours)
            task.last_reminded_at = None
            task.reminder_count = 0
            fields += ["status", "activated_at", "due_at", "last_reminded_at", "reminder_count"]
        task.save(update_fields=fields)
        Reassignment.objects.create(task=task, from_user=previous, to_user=new_approver, actor=actor, reason=reason)
        record("stage.reassigned",
               f"{request.reference}: stage {task.position} reassigned from {previous} to {new_approver}",
               actor=actor, request=request, cycle=task.cycle.number, stage=task.position,
               from_user=previous.email, to_user=new_approver.email, reason=reason)
        notify([new_approver], Notification.Kind.REASSIGNED,
               f"Stage {task.position} of {request.reference} has been assigned to you: {reason}", request=request)
        notify([previous], Notification.Kind.REASSIGNED,
               f"Stage {task.position} of {request.reference} was reassigned to {new_approver}", request=request,
               exclude=[actor])
        return task
