"""Remote evaluation tools: participant downloads and the admin-only reset (apps/evaluation/ops.py)."""
import zipfile

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.approvals.models import ApprovalRequest
from apps.evaluation import ops

pytestmark = pytest.mark.django_db


@pytest.fixture
def tools(settings, tmp_path, monkeypatch):
    settings.EVALUATION_TOOLS = True
    monkeypatch.setattr(ops, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(ops, "STATUS_FILE", tmp_path / "work" / "reset-status.json")


def test_tools_are_hidden_unless_switched_on(client):
    assert client.get(reverse("evaluation:files")).status_code == 404
    assert client.get(reverse("evaluation:file", args=["baseline.zip"])).status_code == 404


def test_participants_can_download_the_sandbox_but_never_the_answer_keys(tools, client):
    assert client.get(reverse("evaluation:files")).status_code == 200  # no sign-in needed
    response = client.get(reverse("evaluation:file", args=["baseline.zip"]))
    assert response.status_code == 200
    names = zipfile.ZipFile(ops.WORK_DIR / "bundles" / "baseline.zip").namelist()
    assert "baseline/mail/inbox.html" in names
    assert any(name.startswith("baseline/spreadsheet/") for name in names)
    for bundle in ops.BUNDLES:
        listed = zipfile.ZipFile(ops.WORK_DIR / "bundles" / bundle).namelist()
        assert listed and not any("ground" in name or "answer-key" in name for name in listed)
    materials = zipfile.ZipFile(ops.WORK_DIR / "bundles" / "materials-A.zip").namelist()
    assert "materials/T3-design-note_v2.md" in materials
    assert client.get(reverse("evaluation:file", args=["ground_truth.json"])).status_code == 404


def test_only_administrators_can_reset(tools, client, people):
    url = reverse("evaluation:reset")
    assert client.get(url).status_code == 302  # anonymous: to the sign-in page
    client.force_login(people["pm"])
    assert client.get(url).status_code == 302
    client.force_login(people["admin"])
    assert client.get(url).status_code == 200
    assert client.post(url, {"confirm": "yes"}).status_code == 400


def test_reset_reloads_the_evaluation_dataset(tools, client, people, monkeypatch):
    monkeypatch.setenv("HOSTED_PASSWORD", "session-pass-2026")
    monkeypatch.setattr(ops.threading, "Thread", _InlineThread)
    client.force_login(people["admin"])
    client.post(reverse("evaluation:reset"), {"confirm": "RESET"})
    assert ops.read_status()["state"] == "done"
    assert ApprovalRequest.objects.count() == 120
    assert User.objects.get(email="ozioma.nwachukwu@ztl.example").check_password("session-pass-2026")
    assert not User.objects.filter(email="pm@ztl.example").exists()  # earlier data are gone


class _InlineThread:
    """Runs the reset in the test's own thread, so it shares the test database transaction."""

    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)
