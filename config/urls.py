from django.contrib import admin
from django.urls import include, path

from apps.approvals import views as approval_views

admin.site.site_header = "Flowbridge administration"
admin.site.site_title = "Flowbridge admin"

urlpatterns = [
    path("", approval_views.dashboard, name="dashboard"),
    path("accounts/", include("apps.accounts.urls")),
    path("projects/", include("apps.projects.urls")),
    path("", include("apps.approvals.urls")),
    path("admin/", admin.site.urls),
]
