from django.contrib import admin

from apps.approvals.admin import ReadOnlyAdmin

from .models import Comment, ProjectMessage

admin.site.register(Comment, ReadOnlyAdmin)
admin.site.register(ProjectMessage, ReadOnlyAdmin)
