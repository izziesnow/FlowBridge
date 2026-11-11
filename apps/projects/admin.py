from django.contrib import admin

from .models import Membership, Project


class MembershipInline(admin.TabularInline):
    model = Membership
    fk_name = "project"
    extra = 0
    autocomplete_fields = ["user"]
    readonly_fields = ["added_by", "added_at"]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at")
    search_fields = ("code", "name")
    inlines = [MembershipInline]
    readonly_fields = ["created_by", "created_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "role", "added_at")
    list_filter = ("role", "project")
    search_fields = ("user__email", "user__full_name", "project__code")
    autocomplete_fields = ["user", "project"]
