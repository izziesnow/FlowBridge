from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Project(models.Model):
    """A unit of work with its own members, workflows and requests."""

    code = models.CharField(
        max_length=10,
        unique=True,
        validators=[RegexValidator(r"^[A-Z][A-Z0-9]{1,9}$", "Use 2–10 capital letters or digits, starting with a letter.")],
        help_text="Short unique code used in request references, e.g. PAY.",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        super().save(*args, **kwargs)


class Role(models.TextChoices):
    PM = "PM", "Project manager"
    REQUESTER = "REQUESTER", "Requester"
    APPROVER = "APPROVER", "Approver"
    VIEWER = "VIEWER", "Viewer"


class Membership(models.Model):
    """A user's single role within one project."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=12, choices=Role.choices)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["project__code", "user__full_name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="projects_one_role_per_user_per_project"),
        ]

    def __str__(self):
        return f"{self.user} — {self.get_role_display()} on {self.project.code}"
