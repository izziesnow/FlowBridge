"""Pages for running remote evaluation sessions; available only when EVALUATION_TOOLS is on (ops.py)."""
from datetime import datetime, timezone

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from . import ops


def _require_tools():
    if not settings.EVALUATION_TOOLS:
        raise Http404("Evaluation tools are not enabled on this copy.")


def participant_files(request):
    """Public page: the files a participant needs. Synthetic data only; no answer keys."""
    _require_tools()
    return render(request, "evaluation/files.html", {"bundles": ops.BUNDLES})


def participant_file(request, name):
    _require_tools()
    if name not in ops.BUNDLES:
        raise Http404("No such file")
    path = ops.build_bundles() / name
    return FileResponse(path.open("rb"), as_attachment=True, filename=name)


def _when(timestamp):
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().strftime("%d %b %Y, %H:%M:%S")


@user_passes_test(lambda user: user.is_active and user.is_superuser)
@require_http_methods(["GET", "POST"])
def reset_data(request):
    """Administrators only: reload the evaluation dataset before the next participant."""
    _require_tools()
    if request.method == "POST":
        if request.POST.get("confirm") != "RESET":
            return render(request, "evaluation/reset.html", {
                "status": ops.read_status(), "error": "Type RESET in capitals to confirm.",
            }, status=400)
        ops.start_reset(request.user.email)
        # The reset empties the sessions table too, so this redirect may land on the sign-in page.
        return redirect("evaluation:reset")
    status = ops.read_status()
    return render(request, "evaluation/reset.html", {
        "status": status,
        "started": _when(status.get("started")),
        "finished": _when(status.get("finished")),
        "running": ops.reset_running(),
    })
