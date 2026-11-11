"""Filtered dashboards, cross-project search and authorised history export (FR12, NFR01, NFR03)."""
import csv
import io
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.approvals.models import Decision, StageTask
from apps.approvals.services import WorkflowService
from apps.audit.models import AuditEvent
from apps.projects.models import Membership, Project, Role
from conftest import upload

pytestmark = pytest.mark.django_db
A, C = Decision.Outcome.APPROVE, Decision.Outcome.REQUEST_CHANGES


def rows(response):
    text = b"".join(response.streaming_content if response.streaming else [response.content]).decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


@pytest.fixture
def history(project, people, workflow):
    """Three requests: approved after two cycles, in review, and a draft."""
    requester = people["requester"]
    done = WorkflowService.create_request(project, requester, "Retry callbacks", "Body")
    WorkflowService.add_document_version(done, requester, upload())
    WorkflowService.submit(done, requester)
    WorkflowService.decide(done, people["approver1"], C, "Add a rollback plan")
    WorkflowService.add_document_version(done, requester, upload(content=b"v2"), document=done.documents.get())
    WorkflowService.resubmit(done, requester)
    WorkflowService.decide(done, people["approver1"], A)
    WorkflowService.decide(done, people["approver2"], A)

    waiting = WorkflowService.create_request(project, requester, "Upgrade TLS library", "Body")
    WorkflowService.submit(waiting, requester)

    draft = WorkflowService.create_request(project, requester, "=HYPERLINK(\"http://evil\")", "Formula title")
    return {"done": done, "waiting": waiting, "draft": draft}


def test_filters_by_text_reference_state_and_current_approver(history, people, client_for):
    client = client_for(people["viewer"])
    url = reverse("projects:detail", args=["PAY"])
    refs = lambda q: [r.reference for r in client.get(url, q).context["requests"]]  # noqa: E731
    assert refs({"q": "tls"}) == ["PAY-002"]
    assert refs({"q": "pay-001"}) == ["PAY-001"]
    assert refs({"state": "APPROVED"}) == ["PAY-001"]
    assert refs({"approver": people["approver1"].pk}) == ["PAY-002"]
    assert refs({"approver": people["approver2"].pk}) == []


def test_date_range_filter_and_validation(history, people, client_for):
    client = client_for(people["viewer"])
    url = reverse("projects:detail", args=["PAY"])
    today = timezone.localdate()
    assert len(client.get(url, {"raised_from": today, "raised_to": today}).context["requests"]) == 3
    assert len(client.get(url, {"raised_to": today - timedelta(days=1)}).context["requests"]) == 0
    page = client.get(url, {"raised_from": today, "raised_to": today - timedelta(days=1)})
    assert page.context["filter_form"].errors


def test_dashboard_figures(history, people, client_for):
    task = StageTask.objects.get(cycle__request=history["waiting"], status=StageTask.Status.ACTIVE)
    task.due_at = timezone.now() - timedelta(hours=1)
    task.save(update_fields=["due_at"])
    m = client_for(people["viewer"]).get(reverse("projects:dashboard", args=["PAY"])).context["m"]
    assert (m["total"], m["open"], m["in_review"], m["overdue"]) == (3, 2, 1, 1)
    assert m["approved"] == 1 and m["first_pass_rate"] == 0  # approved only in its second cycle
    assert m["cycles_per_closed"] == 2.0
    assert m["waiting"][0]["approver"] == people["approver1"].full_name and m["waiting"][0]["overdue"] == 1
    assert [s["decisions"] for s in m["stages"]] == [2, 1]


def test_dashboard_respects_filters(history, people, client_for):
    m = client_for(people["viewer"]).get(reverse("projects:dashboard", args=["PAY"]), {"state": "DRAFT"}).context["m"]
    assert m["total"] == 1 and m["approved"] == 0


def test_search_covers_only_the_users_projects(history, people, client_for):
    other = Project.objects.create(code="HRM", name="HR Mobile", created_by=people["admin"])
    Membership.objects.create(project=other, user=people["outsider"], role=Role.REQUESTER)
    WorkflowService.create_request(other, people["outsider"], "Secret HR change", "Body")
    mine = client_for(people["viewer"]).get(reverse("approvals:request_search"))
    assert b"Secret HR change" not in mine.content and b"Upgrade TLS library" in mine.content
    theirs = client_for(people["outsider"]).get(reverse("approvals:request_search"))
    assert b"Secret HR change" in theirs.content and b"Upgrade TLS library" not in theirs.content


def test_only_pm_and_admin_can_export(history, people, client_for):
    url = reverse("projects:export", args=["PAY", "requests"])
    assert client_for(people["requester"]).get(url).status_code == 403
    assert client_for(people["viewer"]).get(url).status_code == 403
    assert client_for(people["outsider"]).get(url).status_code == 404
    assert client_for(people["admin"]).get(url).status_code == 200
    assert client_for(people["pm"]).get(reverse("projects:export", args=["PAY", "unknown"])).status_code == 404


def test_request_register_export_is_audited_and_filtered(history, people, client_for):
    client = client_for(people["pm"])
    response = client.get(reverse("projects:export", args=["PAY", "requests"]), {"state": "IN_REVIEW"})
    assert response["Content-Type"].startswith("text/csv") and "attachment" in response["Content-Disposition"]
    data = rows(response)
    assert data[0][0] == "Reference" and [r[0] for r in data[1:]] == ["PAY-002"]
    assert data[1][4] == people["approver1"].full_name
    event = AuditEvent.objects.get(action="export.created")
    assert event.actor == people["pm"] and event.data["rows"] == 1 and event.data["filters"] == {"state": "IN_REVIEW"}


def test_decision_export_binds_each_decision_to_the_reviewed_versions(history, people, client_for):
    data = rows(client_for(people["pm"]).get(reverse("projects:export", args=["PAY", "decisions"])))
    header, body = data[0], data[1:]
    assert len(body) == 3
    first, second = body[0], body[1]
    assert (first[2], first[3], first[7], first[8]) == ("1", "1", "Changes requested", "Add a rollback plan")
    assert " v1 " in first[10] and " v2 " in second[10]  # cycle 1 reviewed v1, cycle 2 reviewed v2
    version = history["done"].documents.get().versions.get(number=2)
    assert version.sha256 in second[10]


def test_exports_neutralise_spreadsheet_formulas(history, people, client_for):
    data = rows(client_for(people["pm"]).get(reverse("projects:export", args=["PAY", "requests"])))
    titles = [r[1] for r in data[1:]]
    assert "'=HYPERLINK(\"http://evil\")" in titles


def test_audit_log_export(history, people, client_for):
    data = rows(client_for(people["pm"]).get(reverse("projects:export", args=["PAY", "audit"])))
    actions = [r[2] for r in data[1:]]
    assert "request.submitted" in actions and "decision.request_changes" in actions
