"""Request filtering, shared by the project list, the cross-project search, the dashboard and the exports.

Using one filter for all of them means an export always contains exactly the
requests the user was looking at.
"""
from django import forms
from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from apps.accounts.models import User

from .models import ApprovalRequest, RequestState, StageTask


def annotate_requests(queryset):
    """Add ``is_overdue`` and the current approver's name to each request."""
    now = timezone.now()
    active = StageTask.objects.filter(cycle__request=OuterRef("pk"), status=StageTask.Status.ACTIVE)
    return queryset.annotate(
        is_overdue=Exists(active.filter(due_at__lt=now)),
        current_approver_name=Subquery(active.values("approver__full_name")[:1]),
        current_due_at=Subquery(active.values("due_at")[:1]),
    )


class RequestFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search", widget=forms.TextInput(attrs={"placeholder": "Title or reference"}))
    state = forms.ChoiceField(required=False, choices=[("", "Any status"), *RequestState.choices], label="Status")
    requester = forms.ModelChoiceField(queryset=User.objects.none(), required=False, empty_label="Anyone")
    approver = forms.ModelChoiceField(
        queryset=User.objects.none(), required=False, empty_label="Anyone", label="Current approver"
    )
    raised_from = forms.DateField(required=False, label="Raised from", widget=forms.DateInput(attrs={"type": "date"}))
    raised_to = forms.DateField(required=False, label="Raised to", widget=forms.DateInput(attrs={"type": "date"}))
    overdue = forms.BooleanField(required=False, label="Overdue only")

    def __init__(self, *args, projects, **kwargs):
        super().__init__(*args, **kwargs)
        people = User.objects.filter(memberships__project__in=projects).distinct().order_by("full_name")
        self.fields["requester"].queryset = people
        self.fields["approver"].queryset = people
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = "form-select form-select-sm"
            else:
                field.widget.attrs["class"] = "form-control form-control-sm"

    def clean(self):
        data = super().clean()
        start, end = data.get("raised_from"), data.get("raised_to")
        if start and end and start > end:
            self.add_error("raised_to", "The end date must be on or after the start date.")
        return data

    @property
    def active_filters(self):
        if not self.is_bound or not self.is_valid():
            return {}
        return {k: v for k, v in self.cleaned_data.items() if v not in (None, "", False)}

    def apply(self, queryset):
        queryset = annotate_requests(queryset)
        if not self.is_bound or not self.is_valid():
            return queryset
        data = self.cleaned_data
        if data.get("q"):
            term = data["q"].strip()
            match = Q(title__icontains=term)
            code, _, number = term.upper().partition("-")
            if number.isdigit():
                match |= Q(project__code=code, number=int(number))
            queryset = queryset.filter(match)
        if data.get("state"):
            queryset = queryset.filter(state=data["state"])
        if data.get("requester"):
            queryset = queryset.filter(requester=data["requester"])
        if data.get("approver"):
            queryset = queryset.filter(
                Exists(StageTask.objects.filter(cycle__request=OuterRef("pk"), status=StageTask.Status.ACTIVE,
                                                approver=data["approver"]))
            )
        if data.get("raised_from"):
            queryset = queryset.filter(created_at__date__gte=data["raised_from"])
        if data.get("raised_to"):
            queryset = queryset.filter(created_at__date__lte=data["raised_to"])
        if data.get("overdue"):
            queryset = queryset.filter(is_overdue=True)
        return queryset


def filtered_requests(request, projects):
    """Bind the filter form to the query string and return (form, queryset)."""
    form = RequestFilterForm(request.GET or None, projects=projects)
    base = ApprovalRequest.objects.filter(project__in=projects).select_related("project", "requester")
    return form, form.apply(base).order_by("-updated_at")
