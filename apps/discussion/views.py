from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.approvals.models import ApprovalRequest
from apps.projects.access import get_project_for_user

from .services import DiscussionError, can_post, post_comment, post_project_message


@login_required
@require_POST
def comment_create(request, code, number):
    project = get_project_for_user(request.user, code)
    approval_request = get_object_or_404(ApprovalRequest, project=project, number=number)
    try:
        comment = post_comment(approval_request, request.user, request.POST.get("body"))
        return redirect(f"{approval_request.get_absolute_url()}#comment-{comment.pk}")
    except DiscussionError as error:
        messages.error(request, str(error))
    return redirect(approval_request)


@login_required
def project_discussion(request, code):
    project = get_project_for_user(request.user, code)
    if request.method == "POST":
        try:
            post_project_message(project, request.user, request.POST.get("body"))
            messages.success(request, "Message posted.")
        except DiscussionError as error:
            messages.error(request, str(error))
        return redirect("discussion:project", project.code)
    thread = project.messages.select_related("author")[:200]
    return render(request, "discussion/project.html", {
        "project": project, "thread": thread, "can_post": can_post(request.user, project),
    })
