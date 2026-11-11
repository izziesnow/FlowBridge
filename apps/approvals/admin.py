"""Admin is read-only for workflow evidence: state changes go through WorkflowService."""
from django.contrib import admin

from .models import (
    ApprovalRequest,
    Decision,
    Document,
    DocumentVersion,
    ReviewCycle,
    Revision,
    StageDefinition,
    StageTask,
    WorkflowVersion,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StageInline(admin.TabularInline):
    model = StageDefinition
    extra = 0
    can_delete = False

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WorkflowVersion)
class WorkflowVersionAdmin(ReadOnlyAdmin):
    list_display = ("project", "number", "name", "status", "published_at")
    list_filter = ("status", "project")
    inlines = [StageInline]


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(ReadOnlyAdmin):
    list_display = ("reference", "title", "state", "requester", "updated_at")
    list_filter = ("state", "project")
    search_fields = ("title", "requester__email")


for model in (Document, DocumentVersion, Revision, ReviewCycle, StageTask, Decision):
    admin.site.register(model, ReadOnlyAdmin)
