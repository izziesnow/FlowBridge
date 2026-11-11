"""Settings used by a hosted test copy without Nginx or a persistent disk (docs/hosting.md)."""
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.accounts.models import User
from apps.approvals.models import StoredFile
from apps.approvals.services import WorkflowService
from conftest import upload

pytestmark = pytest.mark.django_db


@pytest.fixture
def database_storage(settings):
    settings.DOCUMENT_STORAGE = "database"


def test_database_storage_keeps_documents_in_postgresql(database_storage, draft, private_media):
    version = draft.documents.get().versions.get()
    stored = StoredFile.objects.get(name=version.file.name)
    assert bytes(stored.content) == b"# Spec\nversion 1\n"
    assert stored.size == version.size_bytes
    assert not Path(private_media).exists()  # nothing written to the local disk


def test_database_storage_serves_and_checks_downloads(database_storage, draft, people, client_for):
    version = draft.documents.get().versions.get()
    url = reverse("approvals:document_download", args=[version.pk])
    response = client_for(people["viewer"]).get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"# Spec\nversion 1\n"

    StoredFile.objects.filter(name=version.file.name).update(content=b"tampered")
    assert client_for(people["viewer"]).get(url).status_code == 403


def test_database_storage_versions_and_integrity_check(database_storage, draft, people, capsys):
    WorkflowService.add_document_version(draft, people["requester"], upload(content=b"v2"), name="spec")
    assert StoredFile.objects.count() == 2
    call_command("verify_integrity")
    assert "Document versions checked: 2" in capsys.readouterr().out

    StoredFile.objects.filter(name=draft.documents.get().versions.get(number=2).file.name).update(content=b"x")
    with pytest.raises(CommandError):
        call_command("verify_integrity")


def test_health_check_answers_before_host_validation(client, settings):
    settings.ALLOWED_HOSTS = ["flowbridge.example"]
    response = client.get("/healthz", HTTP_HOST="10.0.0.7:10000")
    assert response.status_code == 200 and response.content == b"ok"


def test_security_headers_added_only_when_switched_on(client, settings):
    login = reverse("accounts:login")
    assert "Content-Security-Policy" not in client.get(login)  # Nginx adds it in the Compose stack
    settings.SECURITY_HEADERS_IN_APP = True
    response = client.get(login)
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert response["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response["Referrer-Policy"] == "same-origin"


def test_prepare_hosted_data_loads_once_with_chosen_password(monkeypatch):
    monkeypatch.setenv("HOSTED_DATASET", "demo")
    monkeypatch.setenv("HOSTED_PASSWORD", "supervisor-test-2026")
    call_command("prepare_hosted_data")
    admin = User.objects.get(email="admin@ztl.example")
    assert admin.check_password("supervisor-test-2026")
    count = User.objects.count()

    call_command("prepare_hosted_data")  # a restart must not reload or wipe the data
    assert User.objects.count() == count
