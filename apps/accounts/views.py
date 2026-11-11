from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.audit.models import record

from .forms import PreferencesForm


@login_required
def preferences(request):
    form = PreferencesForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        state = "on" if form.instance.email_notifications else "off"
        record("account.preferences", f"Email notifications switched {state}", actor=request.user)
        messages.success(request, f"Email notifications are now {state}.")
        return redirect("accounts:preferences")
    return render(request, "accounts/preferences.html", {"form": form})
