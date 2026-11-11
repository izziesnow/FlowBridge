from django.urls import path

from . import views

app_name = "evaluation"

urlpatterns = [
    path("files/", views.participant_files, name="files"),
    path("files/<str:name>", views.participant_file, name="file"),
    path("reset/", views.reset_data, name="reset"),
]
