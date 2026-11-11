from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User


class FlowbridgeUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name", "job_title")


class FlowbridgeUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = FlowbridgeUserChangeForm
    add_form = FlowbridgeUserCreationForm
    ordering = ("full_name",)
    list_display = ("email", "full_name", "job_title", "is_staff", "is_active", "last_login")
    list_filter = ("is_staff", "is_active")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "job_title")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "job_title", "password1", "password2"),
        }),
    )
    readonly_fields = ("last_login", "date_joined")
