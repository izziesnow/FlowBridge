import hashlib
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditEvent
from apps.projects.access import can_view, get_project_for_user, get_role, visible_projects
from apps.projects.models import Role

from apps.discussion.services import can_post

from .forms import (
    DecisionForm,
    DocumentUploadForm,
    ReasonForm,
    ReassignForm,
    RequestContentForm,
    RequestCreateForm,
    StageForm,
    WorkflowVersionForm,
)
from .models import (
    ApprovalRequest,
    DocumentVersion,
    RequestState,
    RevisionDocument,
    StageTask,
    WorkflowVersion,
)
from .filters import filtered_requests
from .services import WorkflowError, WorkflowService, latest_published_workflow


def _error_messages(request, error):
    for message in getattr(error, "messages", [str(error)]):
        messages.error(request, message)


def decision_record(cycles):
    """Every decision on the request in the order it was made, with what changed between revisions."""
    rows, previous = [], {}
    for cycle in sorted(cycles, key=lambda c: c.number):
        docs = {rd.document_version.document.name: rd.document_version for rd in cycle.revision.revision_documents.all()}
        cycle.changes = [
            (name, previous[name].number if name in previous else None, v.number)
            for name, v in sorted(docs.items())
            if name not in previous or previous[name].pk != v.pk
        ] if cycle.number > 1 else []
        previous = docs
        for task in sorted(cycle.tasks.all(), key=lambda t: t.position):
            decision = getattr(task, "decision", None)
            if decision is not None:
                rows.append({"cycle": cycle, "task": task, "decision": decision})
    rows.sort(key=lambda r: r["decision"].created_at)
    return rows


def _get_request(user, code, number):
    project = get_project_for_user(user, code)
    approval_request = get_object_or_404(
        ApprovalRequest.objects.select_related("project", "requester", "current_revision", "workflow_version"),
        project=project, number=number,
    )
    return project, approval_request


# ---------------------------------------------------------------- dashboard


@login_required
def dashboard(request):
    user = request.user
    awaiting = (
        StageTask.objects.filter(approver=user, status=StageTask.Status.ACTIVE)
        .select_related("cycle__request__project", "cycle__request__requester")
        .order_by("due_at")
    )
    my_requests = (
        ApprovalRequest.objects.filter(requester=user)
        .select_related("project")
        .order_by("-updated_at")[:20]
    )
    projects = visible_projects(user).order_by("code")
    return render(request, "approvals/dashboard.html", {
        "awaiting": awaiting, "my_requests": my_requests, "projects": projects,
    })


@login_required
def request_search(request):
    """All requests in the projects the user can see, with the shared filters."""
    projects = visible_projects(request.user)
    form, requests_qs = filtered_requests(request, projects)
    return render(request, "approvals/request_search.html", {
        "filter_form": form, "requests": requests_qs[:300], "count": requests_qs.count(),
    })


# ---------------------------------------------------------------- requests


@login_required
def request_create(request, code):
    project = get_project_for_user(request.user, code)
    if get_role(request.user, project) != Role.REQUESTER:
        raise PermissionDenied("Only requesters can raise requests on this project.")
    form = RequestCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            with transaction.atomic():
                approval_request = WorkflowService.create_request(project, request.user, data["title"],
                                                                  data["description"])
                if data.get("document"):
                    WorkflowService.add_document_version(approval_request, request.user, data["document"])
        except WorkflowError as error:
            _error_messages(request, error)
        else:
            if request.POST.get("then") == "submit":
                try:
                    WorkflowService.submit(approval_request, request.user)
                    messages.success(request, f"{approval_request.reference} created and submitted for review.")
                except WorkflowError as error:
                    messages.warning(request, f"Draft {approval_request.reference} saved but not submitted:")
                    _error_messages(request, error)
            else:
                messages.success(request, f"Draft {approval_request.reference} saved. Submit it when it is ready.")
            return redirect(approval_request)
    return render(request, "approvals/request_form.html", {
        "project": project, "form": form, "workflow": latest_published_workflow(project), "creating": True,
    })


@login_required
def request_detail(request, code, number):
    project, approval_request = _get_request(request.user, code, number)
    user = request.user
    role = get_role(user, project)
    cycles = (
        approval_request.cycles.select_related("revision", "workflow_version")
        .prefetch_related(
            Prefetch("tasks", queryset=StageTask.objects.select_related("approver", "decision__actor")
                     .prefetch_related("reassignments__from_user", "reassignments__to_user", "reassignments__actor")),
            Prefetch(
                "revision__revision_documents",
                queryset=RevisionDocument.objects.select_related("document_version__document"),
            ),
        )
        .order_by("-number")
    )
    documents = approval_request.documents.prefetch_related("versions__uploaded_by")
    active_task = approval_request.active_task()
    is_requester = user == approval_request.requester
    context = {
        "project": project,
        "req": approval_request,
        "role": role,
        "cycles": cycles,
        "documents": documents,
        "active_task": active_task,
        "history": AuditEvent.objects.filter(request=approval_request).select_related("actor").order_by("created_at"),
        "can_edit": is_requester and approval_request.is_editable,
        "can_submit": is_requester and approval_request.state == RequestState.DRAFT,
        "can_resubmit": is_requester and approval_request.state == RequestState.CHANGES_REQUESTED,
        "can_decide": active_task is not None and active_task.approver == user and not is_requester,
        "can_withdraw": approval_request.is_open and (is_requester or role == Role.PM),
        "decision_form": DecisionForm(),
        "reason_form": ReasonForm(auto_id="withdraw_%s"),
        "upload_form": DocumentUploadForm(approval_request=approval_request, auto_id="upload_%s"),
        "decision_record": decision_record(cycles),
        "comments": approval_request.comments.select_related("author", "revision"),
        "can_comment": can_post(user, project),
        "can_reassign": role == Role.PM and approval_request.state == RequestState.IN_REVIEW,
        "reassign_form": ReassignForm(approval_request=approval_request, auto_id="reassign_%s"),
    }
    return render(request, "approvals/request_detail.html", context)


@login_required
def request_edit(request, code, number):
    project, approval_request = _get_request(request.user, code, number)
    if request.user != approval_request.requester or not approval_request.is_editable:
        raise PermissionDenied("This request cannot be edited now.")
    form = RequestContentForm(
        request.POST or None,
        initial={"title": approval_request.title, "description": approval_request.description},
    )
    if request.method == "POST" and form.is_valid():
        try:
            WorkflowService.update_content(
                approval_request, request.user, form.cleaned_data["title"], form.cleaned_data["description"]
            )
            messages.success(request, "Changes saved.")
            return redirect(approval_request)
        except WorkflowError as error:
            _error_messages(request, error)
    return render(request, "approvals/request_form.html", {"project": project, "form": form, "req": approval_request})


@login_required
@require_POST
def document_upload(request, code, number):
    project, approval_request = _get_request(request.user, code, number)
    form = DocumentUploadForm(request.POST, request.FILES, approval_request=approval_request)
    if form.is_valid():
        target, name = form.cleaned_data["target"], form.cleaned_data["name"].strip()
        document = None
        if target and target != "new":
            document = get_object_or_404(approval_request.documents, pk=target)
        elif target == "new" and not name:
            name = Path(form.cleaned_data["file"].name).stem
        try:
            version = WorkflowService.add_document_version(
                approval_request, request.user, form.cleaned_data["file"], name=name or None, document=document
            )
            how = "a new version of" if version.number > 1 else "a new document,"
            messages.success(request, f"Uploaded as {how} “{version.document.name}”: now v{version.number}.")
        except WorkflowError as error:
            _error_messages(request, error)
    else:
        messages.error(request, "Choose a file to upload.")
    return redirect(approval_request)


@login_required
@require_POST
def request_submit(request, code, number):
    project, approval_request = _get_request(request.user, code, number)
    try:
        WorkflowService.submit(approval_request, request.user)
        messages.success(request, f"{approval_request.reference} submitted for review.")
    except WorkflowError as error:
        _error_messages(request, error)
    return redirect(approval_request)


@login_required
@require_POST
def request_decide(request, code, number):
    project, approval_request = _get_request(request.user, code, number)
    form = DecisionForm(request.POST)
    if form.is_valid():
        try:
            decision = WorkflowService.decide(
                approval_request, request.user, form.cleaned_data["outcome"], form.cleaned_data["reason"]
            )
            messages.success(request, f"Decision recorded: {decision.get_outcome_display()}.")
        except WorkflowError as error:
            _error_messages(request, error)
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect(approval_request)


@login_required
@require_POST
def request_resubmit(request, code, number):
    project, approval_request = _get_request(request.user, code, number)
    try:
        WorkflowService.resubmit(approval_request, request.user)
        messages.success(request, f"{approval_request.reference} resubmitted. Review restarts at stage 1.")
    except WorkflowError as error:
        _error_messages(request, error)
    return redirect(approval_request)


@login_required
@require_POST
def request_withdraw(request, code, number):
    project, approval_request = _get_request(request.user, code, number)
    form = ReasonForm(request.POST)
    if form.is_valid():
        try:
            WorkflowService.withdraw(approval_request, request.user, form.cleaned_data["reason"])
            messages.success(request, f"{approval_request.reference} withdrawn.")
        except WorkflowError as error:
            _error_messages(request, error)
    else:
        messages.error(request, "A reason is required to withdraw a request.")
    return redirect(approval_request)


@login_required
@require_POST
def request_reassign(request, code, number):
    project, approval_request = _get_request(request.user, code, number)
    if get_role(request.user, project) != Role.PM:
        raise PermissionDenied("Only the project manager can reassign a stage.")
    form = ReassignForm(request.POST, approval_request=approval_request)
    if form.is_valid():
        try:
            task = WorkflowService.reassign_stage(
                approval_request, request.user, form.cleaned_data["task"], form.cleaned_data["new_approver"],
                form.cleaned_data["reason"],
            )
            messages.success(request, f"Stage {task.position} reassigned to {task.approver}.")
        except WorkflowError as error:
            _error_messages(request, error)
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect(approval_request)


# ---------------------------------------------------------------- documents


@login_required
def document_download(request, version_id):
    """Serve a document only to members of its project. Everyone else gets 404."""
    version = get_object_or_404(
        DocumentVersion.objects.select_related("document__request__project"), pk=version_id
    )
    project = version.document.request.project
    if not can_view(request.user, project):
        raise Http404("Document not found")
    try:
        handle = version.file.open("rb")
    except FileNotFoundError as missing:
        raise Http404("Document file is missing") from missing
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(64 * 1024), b""):
        digest.update(chunk)
    if digest.hexdigest() != version.sha256:
        handle.close()
        raise PermissionDenied("The stored file does not match its recorded checksum.")
    handle.seek(0)
    response = FileResponse(handle, as_attachment=True, filename=version.original_filename)
    response["X-Content-Type-Options"] = "nosniff"
    return response


# ---------------------------------------------------------------- workflows


@login_required
def workflow_list(request, code):
    project = get_project_for_user(request.user, code)
    is_pm = get_role(request.user, project) == Role.PM
    form = WorkflowVersionForm(request.POST or None)
    if request.method == "POST":
        if not is_pm:
            raise PermissionDenied("Only the project manager can design workflows.")
        if form.is_valid():
            version = WorkflowService.create_workflow_version(project, request.user, form.cleaned_data["name"])
            messages.success(request, f"Workflow v{version.number} created. Add its stages, then publish it.")
            return redirect("approvals:workflow_detail", project.code, version.number)
    versions = project.workflow_versions.prefetch_related("stages__approver")
    return render(request, "approvals/workflow_list.html", {
        "project": project, "versions": versions, "form": form, "is_pm": is_pm,
        "current": latest_published_workflow(project),
    })


@login_required
def workflow_detail(request, code, number):
    project = get_project_for_user(request.user, code)
    version = get_object_or_404(WorkflowVersion, project=project, number=number)
    is_pm = get_role(request.user, project) == Role.PM
    form = StageForm(request.POST or None, project=project)
    if request.method == "POST":
        if not is_pm:
            raise PermissionDenied("Only the project manager can design workflows.")
        action = request.POST.get("action")
        try:
            if action == "add_stage":
                if form.is_valid():
                    WorkflowService.add_stage(
                        version, request.user, form.cleaned_data["name"], form.cleaned_data["approver"],
                        form.cleaned_data["due_hours"],
                    )
                    messages.success(request, "Stage added.")
                    return redirect("approvals:workflow_detail", project.code, version.number)
            elif action == "remove_stage":
                WorkflowService.remove_last_stage(version, request.user)
                messages.success(request, "Last stage removed.")
                return redirect("approvals:workflow_detail", project.code, version.number)
            elif action == "publish":
                WorkflowService.publish_workflow(version, request.user)
                messages.success(request, f"Workflow v{version.number} published. New submissions will use it.")
                return redirect("approvals:workflow_detail", project.code, version.number)
        except WorkflowError as error:
            _error_messages(request, error)
    return render(request, "approvals/workflow_detail.html", {
        "project": project, "version": version, "stages": version.stages.select_related("approver"),
        "form": form, "is_pm": is_pm,
    })

