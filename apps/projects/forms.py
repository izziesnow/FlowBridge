from django import forms

from apps.accounts.models import User

from .models import Project, Role


class _Bootstrap:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css)


class ProjectCreateForm(_Bootstrap, forms.ModelForm):
    project_manager = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("full_name"),
        help_text="This person can manage members and workflows for the project.",
    )

    class Meta:
        model = Project
        fields = ["code", "name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_code(self):
        return self.cleaned_data["code"].upper()


class MembershipForm(_Bootstrap, forms.Form):
    email = forms.EmailField(label="Member's email address")
    role = forms.ChoiceField(choices=Role.choices)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        try:
            self.user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            raise forms.ValidationError("No active account uses this email. Ask an administrator to create it.")
        return email
