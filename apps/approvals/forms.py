from django import forms

from apps.accounts.models import User
from apps.projects.models import Role

from .models import Decision, StageTask


class BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.RadioSelect):
                continue
            css = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs.setdefault("class", css)


class RequestContentForm(BootstrapMixin, forms.Form):
    title = forms.CharField(max_length=200, help_text="A short summary of the change.")
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 8}),
        required=False,
        help_text="What will change, why, the risk and how it will be rolled back. Required before submission.",
    )


class DocumentUploadForm(BootstrapMixin, forms.Form):
    name = forms.CharField(
        max_length=150, required=False,
        help_text="Leave blank to use the file name. Uploading under an existing name adds a new version.",
    )
    file = forms.FileField()


class DecisionForm(BootstrapMixin, forms.Form):
    outcome = forms.ChoiceField(
        choices=[
            (Decision.Outcome.APPROVE, "Approve"),
            (Decision.Outcome.REQUEST_CHANGES, "Request changes"),
            (Decision.Outcome.REJECT, "Reject"),
        ],
        widget=forms.RadioSelect,
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
        help_text="Required when you reject or request changes.",
    )

    def clean(self):
        data = super().clean()
        if data.get("outcome") in (Decision.Outcome.REJECT, Decision.Outcome.REQUEST_CHANGES) and not (
            data.get("reason") or ""
        ).strip():
            self.add_error("reason", "Give a reason for this decision.")
        return data


class ReasonForm(BootstrapMixin, forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), help_text="Recorded in the request history.")


class WorkflowVersionForm(BootstrapMixin, forms.Form):
    name = forms.CharField(max_length=120, initial="Standard change approval")


class StageForm(BootstrapMixin, forms.Form):
    name = forms.CharField(max_length=80)
    approver = forms.ModelChoiceField(queryset=User.objects.none())
    due_hours = forms.IntegerField(min_value=1, max_value=24 * 30, initial=48, label="Due within (hours)")

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["approver"].queryset = User.objects.filter(
            memberships__project=project, memberships__role__in=[Role.APPROVER, Role.PM], is_active=True
        ).order_by("full_name")


class ReassignForm(BootstrapMixin, forms.Form):
    task = forms.ModelChoiceField(queryset=StageTask.objects.none(), label="Stage")
    new_approver = forms.ModelChoiceField(queryset=User.objects.none(), label="New approver")
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), help_text="Recorded in the request history.")

    def __init__(self, *args, approval_request, **kwargs):
        super().__init__(*args, **kwargs)
        cycle = approval_request.cycles.filter(ended_at__isnull=True).first()
        tasks = StageTask.objects.none()
        if cycle is not None:
            tasks = cycle.tasks.filter(status__in=[StageTask.Status.ACTIVE, StageTask.Status.PENDING])
        self.fields["task"].queryset = tasks.select_related("approver").order_by("position")
        self.fields["task"].label_from_instance = lambda t: f"{t.position}. {t.name} (now {t.approver})"
        self.fields["new_approver"].queryset = (
            User.objects.filter(
                memberships__project=approval_request.project,
                memberships__role__in=[Role.APPROVER, Role.PM], is_active=True,
            ).exclude(pk=approval_request.requester_id).order_by("full_name")
        )
