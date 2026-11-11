"""Project-based access control.

Every view that shows project data calls one of these helpers. A user who is
not a member of a project (and is not an administrator) gets a 404, so the
system does not reveal that the project or its records exist.
"""
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404

from .models import Membership, Project, Role


def get_role(user, project):
    """Return the user's role on the project, or None."""
    if not user.is_authenticated or not user.is_active:
        return None
    return (
        Membership.objects.filter(project=project, user=user).values_list("role", flat=True).first()
    )


def can_view(user, project):
    return user.is_authenticated and user.is_active and (user.is_staff or get_role(user, project) is not None)


def is_pm(user, project):
    return get_role(user, project) == Role.PM


def visible_projects(user):
    if not user.is_authenticated:
        return Project.objects.none()
    if user.is_staff:
        return Project.objects.all()
    return Project.objects.filter(memberships__user=user)


def get_project_for_user(user, code):
    """Fetch a project the user may see, or raise 404."""
    project = get_object_or_404(Project, code=code.upper())
    if not can_view(user, project):
        raise Http404("Project not found")
    return project


def require_pm(user, project):
    if not is_pm(user, project):
        raise PermissionDenied("Only the project manager can do this.")
