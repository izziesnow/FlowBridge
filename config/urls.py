from django.contrib import admin
from django.db import connection
from django.http import HttpResponse
from django.urls import include, path

from apps.approvals import views as approval_views

admin.site.site_header = "Flowbridge administration"
admin.site.site_title = "Flowbridge admin"



def healthz(request):
    """Liveness check for Docker and Nginx: the app is up and can reach the database."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("", approval_views.dashboard, name="dashboard"),
    path("accounts/", include("apps.accounts.urls")),
    path("projects/", include("apps.projects.urls")),
    path("", include("apps.approvals.urls")),
    path("", include("apps.discussion.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("admin/", admin.site.urls),
    path("evaluation/", include("apps.evaluation.urls")),
]
