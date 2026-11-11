"""Private document storage, checksums and permission-checked downloads (FR08, NFR01)."""
import hashlib
from pathlib import Path

import pytest
from django.urls import reverse

from apps.approvals.services import WorkflowError, WorkflowService
from conftest import upload

pytestmark = pytest.mark.django_db


def test_upload_records_sha256_and_stores_privately(draft, private_media):
    version = draft.documents.get().versions.get()
    assert version.sha256 == hashlib.sha256(b"# Spec\nversion 1\n").hexdigest()
    stored = Path(version.file.path)
    assert stored.is_file() and stored.is_relative_to(Path(private_media))
    assert stored.name != "spec.md"  # user-supplied names never become storage paths


def test_new_upload_under_same_name_adds_a_version(draft, people):
    WorkflowService.add_document_version(draft, people["requester"], upload(content=b"v2"), name="spec")
    assert list(draft.documents.get().versions.values_list("number", flat=True)) == [1, 2]


def test_disallowed_file_type_is_rejected(draft, people):
    with pytest.raises(WorkflowError):
        WorkflowService.add_document_version(draft, people["requester"], upload("run.exe", b"MZ"))


def test_documents_frozen_once_in_review(submitted, people):
    with pytest.raises(WorkflowError):
        WorkflowService.add_document_version(submitted, people["requester"], upload(content=b"late"))


def test_member_can_download_and_non_member_gets_404(draft, people, client_for, client):
    version = draft.documents.get().versions.get()
    url = reverse("approvals:document_download", args=[version.pk])

    response = client_for(people["viewer"]).get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"# Spec\nversion 1\n"
    assert "attachment" in response["Content-Disposition"]

    client.logout()
    assert client.get(url).status_code == 302  # anonymous → sign-in page
    assert client_for(people["outsider"]).get(url).status_code == 404


def test_tampered_file_is_not_served(draft, people, client_for):
    version = draft.documents.get().versions.get()
    Path(version.file.path).write_bytes(b"tampered")
    url = reverse("approvals:document_download", args=[version.pk])
    assert client_for(people["viewer"]).get(url).status_code == 403
