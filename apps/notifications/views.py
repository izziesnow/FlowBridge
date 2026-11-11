from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    show = request.GET.get("show", "unread")
    items = Notification.objects.filter(recipient=request.user).select_related("request__project")
    if show != "all":
        items = items.filter(read_at__isnull=True)
    return render(request, "notifications/list.html", {"items": items[:200], "show": show})


@login_required
@require_POST
def notification_open(request, pk):
    """Mark one notification read and go to what it is about. Other users' notifications are 404."""
    item = get_object_or_404(Notification, pk=pk, recipient=request.user)
    item.mark_read()
    if item.url and url_has_allowed_host_and_scheme(item.url, allowed_hosts={request.get_host()}):
        return redirect(item.url)
    return redirect("notifications:list")


@login_required
@require_POST
def notification_mark_all(request):
    Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return redirect("notifications:list")
