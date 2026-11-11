"""End-to-end journeys through the web interface with the Django test client."""
import pytest
from django.urls import reverse

from apps.approvals.models import ApprovalRequest, RequestState
from apps.approvals.services import WorkflowService
from conftest import upload

pytestmark = pytest.mark.django_db


def test_full_journey_through_the_interface(project, people, workflow, client_for):
    requester = client_for(people["requester"])
    response = requester.post(reverse("approvals:request_create", args=["PAY"]),
                              {"title": "Rotate API keys", "description": "Rotate merchant keys quarterly."})
    req = ApprovalRequest.objects.get(project=project, number=1)
    assert response.status_code == 302 and response.url == req.get_absolute_url()

    requester.post(reverse("approvals:document_upload", args=["PAY", 1]), {"name": "", "file": upload("plan.md")})
    requester.post(reverse("approvals:request_submit", args=["PAY", 1]))
    req.refresh_from_db()
    assert req.state == RequestState.IN_REVIEW

    approver = client_for(people["approver1"])
    page = approver.get(req.get_absolute_url())
    assert page.status_code == 200 and b"Your decision" in page.content
    approver.post(reverse("approvals:request_decide", args=["PAY", 1]),
                  {"outcome": "REQUEST_CHANGES", "reason": "Add the rollback steps"})
    req.refresh_from_db()
    assert req.state == RequestState.CHANGES_REQUESTED

    requester = client_for(people["requester"])
    requester.post(reverse("approvals:request_edit", args=["PAY", 1]),
                   {"title": "Rotate API keys", "description": "Rotate keys quarterly. Rollback: restore old keys."})
    requester.post(reverse("approvals:request_resubmit", args=["PAY", 1]))
    req.refresh_from_db()
    assert req.state == RequestState.IN_REVIEW and req.current_revision.number == 2

    approver = client_for(people["approver1"])
    approver.post(reverse("approvals:request_decide", args=["PAY", 1]), {"outcome": "APPROVE", "reason": ""})
    client_for(people["approver2"]).post(reverse("approvals:request_decide", args=["PAY", 1]),
                                         {"outcome": "APPROVE", "reason": ""})
    req.refresh_from_db()
    assert req.state == RequestState.APPROVED


def test_decision_without_reason_is_refused_in_the_form(submitted, people, client_for):
    client = client_for(people["approver1"])
    client.post(reverse("approvals:request_decide", args=["PAY", submitted.number]), {"outcome": "REJECT", "reason": ""})
    submitted.refresh_from_db()
    assert submitted.state == RequestState.IN_REVIEW


def test_request_page_shows_status_current_approver_and_reviewed_versions(submitted, people, client_for):
    page = client_for(people["viewer"]).get(submitted.get_absolute_url())
    content = page.content.decode()
    assert page.status_code == 200
    assert "In review" in content and people["approver1"].full_name in content
    assert "spec v1" in content  # the exact document version bound to revision 1
    assert "Your decision" not in content  # viewers have no actions


def test_non_member_gets_404_for_project_and_request(submitted, people, client_for):
    client = client_for(people["outsider"])
    assert client.get(reverse("projects:detail", args=["PAY"])).status_code == 404
    assert client.get(submitted.get_absolute_url()).status_code == 404


def test_administrator_can_view_any_project(submitted, people, client_for):
    assert client_for(people["admin"]).get(submitted.get_absolute_url()).status_code == 200


def test_dashboard_lists_tasks_awaiting_the_user(submitted, people, client_for):
    WorkflowService.decide(submitted, people["approver1"], "APPROVE")
    page = client_for(people["approver2"]).get(reverse("dashboard"))
    assert submitted.reference.encode() in page.content


def test_anonymous_users_are_sent_to_sign_in(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302 and reverse("accounts:login") in response.url


def test_only_pm_can_manage_members(project, people, client_for):
    url = reverse("projects:members", args=["PAY"])
    data = {"email": people["outsider"].email, "role": "VIEWER"}
    assert client_for(people["requester"]).post(url, data).status_code == 403
    client_for(people["pm"]).post(url, data)
    assert project.memberships.filter(user=people["outsider"], role="VIEWER").exists()
    assert project.audit_events.filter(action="membership.added").exists()
