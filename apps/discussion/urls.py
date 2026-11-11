from django.urls import path

from . import views

app_name = "discussion"

urlpatterns = [
    path("projects/<str:code>/discussion/", views.project_discussion, name="project"),
    path("projects/<str:code>/requests/<int:number>/comments/", views.comment_create, name="comment_create"),
]
