from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import User


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email", "class": "form-control"}),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": "form-control"}),
    )

    def clean_username(self):
        return self.cleaned_data["username"].lower()


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email_notifications"]
        labels = {"email_notifications": "Email me my notifications"}
        widgets = {"email_notifications": forms.CheckboxInput(attrs={"class": "form-check-input"})}
