from django.urls import path

from . import views

app_name = "approvals"

urlpatterns = [
    path("projects/<str:code>/requests/new/", views.request_create, name="request_create"),
    path("projects/<str:code>/requests/<int:number>/", views.request_detail, name="request_detail"),
    path("projects/<str:code>/requests/<int:number>/edit/", views.request_edit, name="request_edit"),
    path("projects/<str:code>/requests/<int:number>/documents/", views.document_upload, name="document_upload"),
    path("projects/<str:code>/requests/<int:number>/submit/", views.request_submit, name="request_submit"),
    path("projects/<str:code>/requests/<int:number>/decide/", views.request_decide, name="request_decide"),
    path("projects/<str:code>/requests/<int:number>/resubmit/", views.request_resubmit, name="request_resubmit"),
    path("projects/<str:code>/requests/<int:number>/withdraw/", views.request_withdraw, name="request_withdraw"),
    path("documents/<int:version_id>/download/", views.document_download, name="document_download"),
    path("projects/<str:code>/workflows/", views.workflow_list, name="workflow_list"),
    path("projects/<str:code>/workflows/<int:number>/", views.workflow_detail, name="workflow_detail"),
]
