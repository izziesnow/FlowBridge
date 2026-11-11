from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("<int:pk>/open/", views.notification_open, name="open"),
    path("read-all/", views.notification_mark_all, name="mark_all"),
]
