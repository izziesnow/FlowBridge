from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Read-only: audit events can be inspected but never changed."""

    list_display = ("created_at", "action", "actor", "project", "request", "summary")
    list_filter = ("action", "project")
    search_fields = ("summary", "actor__email")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
