from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse

from apps.accounts.models import User
from apps.audit.models import record
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.projects.access import get_role
from apps.projects.models import Role

from .models import Comment, ProjectMessage

CAN_POST = (Role.PM, Role.REQUESTER, Role.APPROVER)
MAX_LENGTH = 4000


class DiscussionError(ValueError):
    pass


def _clean(body):
    body = (body or "").strip()
    if not body:
        raise DiscussionError("Write a message first.")
    if len(body) > MAX_LENGTH:
        raise DiscussionError(f"Messages are limited to {MAX_LENGTH} characters.")
    return body


def can_post(user, project):
    return get_role(user, project) in CAN_POST


@transaction.atomic
def post_comment(request, author, body):
    """Add a comment to a request. Viewers and non-members cannot comment."""
    if not can_post(author, request.project):
        raise PermissionDenied("Your role on this project does not allow comments.")
    body = _clean(body)
    comment = Comment.objects.create(request=request, revision=request.current_revision, author=author, body=body)
    record("comment.added", f"Comment on {request.reference}", actor=author, request=request,
           comment=comment.pk, revision=request.current_revision.number if request.current_revision else None)

    active = request.active_task()
    earlier = User.objects.filter(pk__in=request.comments.values("author"))
    preview = body if len(body) <= 80 else body[:77] + "…"
    notify([request.requester, active.approver if active else None, *earlier], Notification.Kind.COMMENT,
           f"{author} commented on {request.reference}: {preview}", request=request, exclude=[author],
           url=f"{request.get_absolute_url()}#comment-{comment.pk}")
    return comment


@transaction.atomic
def post_project_message(project, author, body):
    if not can_post(author, project):
        raise PermissionDenied("Your role on this project does not allow posting.")
    body = _clean(body)
    message = ProjectMessage.objects.create(project=project, author=author, body=body)
    record("discussion.posted", f"Message posted in {project.code} discussion", actor=author, project=project,
           message=message.pk)
    members = User.objects.filter(memberships__project=project)
    preview = body if len(body) <= 80 else body[:77] + "…"
    notify(members, Notification.Kind.DISCUSSION, f"{author} in {project.code}: {preview}", project=project,
           exclude=[author], url=f"{reverse('discussion:project', args=[project.code])}#message-{message.pk}")
    return message
