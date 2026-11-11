from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.approvals import exports
from apps.approvals.filters import filtered_requests
from apps.approvals.metrics import project_metrics
from apps.approvals.models import RequestState
from apps.approvals.services import latest_published_workflow
from apps.audit.models import AuditEvent, record

from .access import get_project_for_user, get_role, require_pm, visible_projects
from .forms import MembershipForm, ProjectCreateForm
from .models import Membership, Role


@login_required
def project_list(request):
    projects = visible_projects(request.user).annotate(
        open_requests=Count(
            "requests",
            filter=Q(requests__state__in=[RequestState.DRAFT, RequestState.IN_REVIEW, RequestState.CHANGES_REQUESTED]),
            distinct=True,
        )
    ).order_by("code")
    return render(request, "projects/project_list.html", {"projects": projects})


@login_required
def project_create(request):
    if not request.user.is_staff:
        raise PermissionDenied("Only administrators can create projects.")
    form = ProjectCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()
            pm = form.cleaned_data["project_manager"]
            Membership.objects.create(project=project, user=pm, role=Role.PM, added_by=request.user)
            record("project.created", f"Project {project.code} created; {pm} is project manager",
                   actor=request.user, project=project, project_manager=pm.email)
        messages.success(request, f"Project {project.code} created.")
        return redirect("projects:detail", project.code)
    return render(request, "projects/project_form.html", {"form": form})


@login_required
def project_detail(request, code):
    project = get_project_for_user(request.user, code)
    role = get_role(request.user, project)
    form, requests_qs = filtered_requests(request, [project])
    return render(request, "projects/project_detail.html", {
        "project": project,
        "role": role,
        "role_label": Role(role).label if role else None,
        "requests": requests_qs,
        "filter_form": form,
        "query": request.GET.urlencode(),
        "workflow": latest_published_workflow(project),
        "can_raise": role == Role.REQUESTER,
        "is_pm": role == Role.PM,
        "can_export": can_export(request.user, project),
    })


@login_required
def project_dashboard(request, code):
    project = get_project_for_user(request.user, code)
    form, requests_qs = filtered_requests(request, [project])
    return render(request, "projects/project_dashboard.html", {
        "project": project, "filter_form": form, "m": project_metrics(requests_qs),
        "query": request.GET.urlencode(), "can_export": can_export(request.user, project),
    })


def can_export(user, project):
    return user.is_staff or get_role(user, project) == Role.PM


@login_required
def project_export(request, code, kind):
    """Authorised CSV export. PM and administrators only; every export is audited (NFR03)."""
    project = get_project_for_user(request.user, code)
    if not can_export(request.user, project):
        raise PermissionDenied("Only the project manager and administrators can export history.")
    if kind not in exports.EXPORTS:
        raise Http404("Unknown export")
    label, builder = exports.EXPORTS[kind]
    form, requests_qs = filtered_requests(request, [project])
    if kind == "audit":
        content, rows = exports.audit_log(project)
    else:
        content, rows = builder(requests_qs)
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    filename = f"flowbridge-{project.code.lower()}-{kind}-{stamp}.csv"
    record("export.created", f"{label} exported ({rows} rows)", actor=request.user, project=project,
           kind=kind, rows=rows, filters={k: str(v) for k, v in form.active_filters.items()}, filename=filename)
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


@login_required
def project_members(request, code):
    project = get_project_for_user(request.user, code)
    is_pm = get_role(request.user, project) == Role.PM
    form = MembershipForm(request.POST or None)
    if request.method == "POST":
        require_pm(request.user, project)
        if form.is_valid():
            user, role = form.user, form.cleaned_data["role"]
            with transaction.atomic():
                membership, created = Membership.objects.select_for_update().get_or_create(
                    project=project, user=user, defaults={"role": role, "added_by": request.user}
                )
                if not created:
                    if membership.user == request.user and role != Role.PM:
                        messages.error(request, "You cannot remove your own project manager role.")
                        return redirect("projects:members", project.code)
                    old = membership.role
                    membership.role = role
                    membership.save(update_fields=["role"])
                    record("membership.changed", f"{user} changed from {old} to {role}", actor=request.user,
                           project=project, user=user.email, old_role=old, new_role=role)
                else:
                    record("membership.added", f"{user} added as {role}", actor=request.user, project=project,
                           user=user.email, role=role)
            messages.success(request, f"{user} is now {Role(role).label.lower()} on {project.code}.")
            return redirect("projects:members", project.code)
    members = project.memberships.select_related("user").order_by("role", "user__full_name")
    return render(request, "projects/project_members.html", {
        "project": project, "members": members, "form": form, "is_pm": is_pm,
    })


@login_required
@require_POST
def member_remove(request, code, membership_id):
    project = get_project_for_user(request.user, code)
    require_pm(request.user, project)
    membership = get_object_or_404(Membership, pk=membership_id, project=project)
    if membership.user == request.user:
        messages.error(request, "You cannot remove yourself from the project.")
        return redirect("projects:members", project.code)
    with transaction.atomic():
        record("membership.removed", f"{membership.user} removed (was {membership.role})", actor=request.user,
               project=project, user=membership.user.email, role=membership.role)
        membership.delete()
    messages.success(request, f"{membership.user} removed from {project.code}.")
    return redirect("projects:members", project.code)


@login_required
def project_history(request, code):
    project = get_project_for_user(request.user, code)
    role = get_role(request.user, project)
    if not (request.user.is_staff or role == Role.PM):
        raise PermissionDenied("Only the project manager and administrators can view the project audit log.")
    events = AuditEvent.objects.filter(project=project).select_related("actor", "request").order_by("-created_at")[:500]
    return render(request, "projects/project_history.html", {"project": project, "events": events})
