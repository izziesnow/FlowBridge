"""Integrity verification (used after restores, NFR08), the health check and mentions."""
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.db import connection
from django.urls import reverse

from apps.approvals.models import Decision, StageTask
from apps.approvals.services import WorkflowService
from apps.discussion.services import post_comment
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_verify_integrity_passes_on_healthy_data(submitted, people, capsys):
    WorkflowService.decide(submitted, people["approver1"], Decision.Outcome.APPROVE)
    call_command("verify_integrity")
    assert "Integrity check passed" in capsys.readouterr().out


def test_verify_integrity_detects_a_tampered_document(submitted):
    version = submitted.documents.get().versions.get()
    Path(version.file.path).write_bytes(b"changed on disk")
    with pytest.raises(CommandError):
        call_command("verify_integrity")


def test_verify_integrity_detects_a_disabled_trigger(submitted):
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE approvals_decision DISABLE TRIGGER approvals_decision_immutable")
    with pytest.raises(CommandError):
        call_command("verify_integrity")


def test_verify_integrity_detects_inconsistent_workflow_state(submitted):
    StageTask.objects.filter(cycle__request=submitted).update(status=StageTask.Status.PENDING)
    with pytest.raises(CommandError):
        call_command("verify_integrity")


def test_health_check(client):
    response = client.get(reverse("healthz"))
    assert response.status_code == 200 and response.content == b"ok"


def test_mentions_notify_the_member_once(submitted, people):
    post_comment(submitted, people["pm"], "@funmilayo can you look today? cc @tl and @nobody")
    approver = people["approver1"]  # email tl@ztl.example
    kinds = list(Notification.objects.filter(recipient=approver).values_list("kind", flat=True))
    assert kinds.count(Notification.Kind.MENTION) == 1
    assert Notification.Kind.COMMENT not in kinds  # mentioned people get one notification, not two


def test_mentions_ignore_email_addresses_and_non_members(submitted, people):
    post_comment(submitted, people["pm"], "Write to outsider@ztl.example, not @outsider")
    assert not Notification.objects.filter(recipient=people["outsider"]).exists()
