"""Shared pytest fixtures. All data are synthetic; ZTL is a fictional organisation."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.approvals.services import WorkflowService
from apps.projects.models import Membership, Project, Role

PASSWORD = "test-pass-2026!"


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private_media"
    return settings.PRIVATE_MEDIA_ROOT


def make_user(email, name, **extra):
    return User.objects.create_user(email, PASSWORD, full_name=name, **extra)


def upload(name="spec.md", content=b"# Spec\nversion 1\n"):
    return SimpleUploadedFile(name, content, content_type="text/markdown")


@pytest.fixture
def people(db):
    return {
        "admin": User.objects.create_superuser("admin@ztl.example", PASSWORD, full_name="Tolulope Adeyemi"),
        "pm": make_user("pm@ztl.example", "Chinedu Eze"),
        "requester": make_user("req@ztl.example", "Aisha Bello"),
        "approver1": make_user("tl@ztl.example", "Funmilayo Ogunleye"),
        "approver2": make_user("po@ztl.example", "Ibrahim Musa"),
        "viewer": make_user("viewer@ztl.example", "Ngozi Obi"),
        "outsider": make_user("outsider@ztl.example", "Bola Adekunle"),
    }


@pytest.fixture
def project(people):
    project = Project.objects.create(code="PAY", name="Payments Gateway Upgrade", created_by=people["admin"])
    roles = {
        "pm": Role.PM, "requester": Role.REQUESTER, "approver1": Role.APPROVER,
        "approver2": Role.APPROVER, "viewer": Role.VIEWER,
    }
    for key, role in roles.items():
        Membership.objects.create(project=project, user=people[key], role=role)
    return project


@pytest.fixture
def workflow(project, people):
    """A published two-stage workflow: technical lead, then product owner."""
    pm = people["pm"]
    version = WorkflowService.create_workflow_version(project, pm, "Standard change")
    WorkflowService.add_stage(version, pm, "Technical lead review", people["approver1"], 48)
    WorkflowService.add_stage(version, pm, "Product owner sign-off", people["approver2"], 48)
    return WorkflowService.publish_workflow(version, pm)


@pytest.fixture
def draft(project, people, workflow):
    req = WorkflowService.create_request(project, people["requester"], "Add retry to callbacks", "Retry failed callbacks.")
    WorkflowService.add_document_version(req, people["requester"], upload())
    return req


@pytest.fixture
def submitted(draft, people):
    return WorkflowService.submit(draft, people["requester"])


@pytest.fixture
def client_for(client):
    def _login(user):
        client.force_login(user)
        return client
    return _login
