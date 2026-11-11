from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("new/", views.project_create, name="create"),
    path("<str:code>/", views.project_detail, name="detail"),
    path("<str:code>/members/", views.project_members, name="members"),
    path("<str:code>/members/<int:membership_id>/remove/", views.member_remove, name="member_remove"),
    path("<str:code>/history/", views.project_history, name="history"),
    path("<str:code>/dashboard/", views.project_dashboard, name="dashboard"),
    path("<str:code>/export/<str:kind>.csv", views.project_export, name="export"),
]
