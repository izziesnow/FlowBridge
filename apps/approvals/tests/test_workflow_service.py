"""Unit and integration tests for WorkflowService transitions and guards (Table of permitted transitions, Ch. 3)."""
import pytest
from django.core.exceptions import PermissionDenied

from apps.approvals.models import Decision, RequestState, ReviewCycle, StageTask, WorkflowVersion
from apps.approvals.services import WorkflowError, WorkflowService
from apps.audit.models import AuditEvent
from conftest import upload

A, R, C = Decision.Outcome.APPROVE, Decision.Outcome.REJECT, Decision.Outcome.REQUEST_CHANGES
pytestmark = pytest.mark.django_db


# ------------------------------------------------------------ publishing workflows


def test_publish_requires_at_least_one_stage(project, people):
    version = WorkflowService.create_workflow_version(project, people["pm"], "Empty")
    with pytest.raises(WorkflowError):
        WorkflowService.publish_workflow(version, people["pm"])


def test_workflow_allows_at_most_five_stages(project, people):
    version = WorkflowService.create_workflow_version(project, people["pm"], "Long")
    for i in range(5):
        WorkflowService.add_stage(version, people["pm"], f"Stage {i + 1}", people["approver1"])
    with pytest.raises(WorkflowError):
        WorkflowService.add_stage(version, people["pm"], "Sixth", people["approver1"])


def test_published_workflow_cannot_change(workflow, people):
    with pytest.raises(WorkflowError):
        WorkflowService.add_stage(workflow, people["pm"], "Late stage", people["approver1"])
    workflow.name = "Renamed"
    with pytest.raises(ValueError):
        workflow.save()


def test_stage_approver_must_hold_approver_role(project, people):
    version = WorkflowService.create_workflow_version(project, people["pm"], "Bad")
    with pytest.raises(WorkflowError):
        WorkflowService.add_stage(version, people["pm"], "Viewer stage", people["viewer"])


def test_only_project_manager_can_design_or_publish(project, people):
    with pytest.raises(PermissionDenied):
        WorkflowService.create_workflow_version(project, people["requester"], "Mine")
    version = WorkflowService.create_workflow_version(project, people["pm"], "Ok")
    WorkflowService.add_stage(version, people["pm"], "Review", people["approver1"])
    with pytest.raises(PermissionDenied):
        WorkflowService.publish_workflow(version, people["approver1"])
    assert WorkflowService.publish_workflow(version, people["pm"]).status == WorkflowVersion.Status.PUBLISHED


# ------------------------------------------------------------ submit


def test_submit_freezes_revision_and_activates_stage_one(submitted):
    submitted.refresh_from_db()
    assert submitted.state == RequestState.IN_REVIEW
    revision = submitted.current_revision
    assert revision.number == 1
    assert revision.title == submitted.title
    bound = [rd.document_version for rd in revision.revision_documents.all()]
    assert [v.number for v in bound] == [1]
    tasks = list(submitted.current_cycle().tasks.order_by("position"))
    assert [t.status for t in tasks] == [StageTask.Status.ACTIVE, StageTask.Status.PENDING]
    assert tasks[0].due_at is not None


def test_submit_requires_description(project, people, workflow):
    req = WorkflowService.create_request(project, people["requester"], "No description")
    with pytest.raises(WorkflowError):
        WorkflowService.submit(req, people["requester"])


def test_submit_requires_published_workflow(project, people):
    req = WorkflowService.create_request(project, people["requester"], "Title", "Body")
    with pytest.raises(WorkflowError):
        WorkflowService.submit(req, people["requester"])


def test_only_requester_can_submit(draft, people):
    with pytest.raises(PermissionDenied):
        WorkflowService.submit(draft, people["pm"])


def test_requester_named_as_approver_cannot_submit(project, people):
    """Separation of duty: a requester can never be an approver of their own request."""
    pm = people["pm"]
    version = WorkflowService.create_workflow_version(project, pm, "Self review")
    WorkflowService.add_stage(version, pm, "PM review", pm)
    WorkflowService.publish_workflow(version, pm)
    pm.memberships.update(role="REQUESTER")
    req = WorkflowService.create_request(project, pm, "Own change", "Body")
    with pytest.raises(WorkflowError):
        WorkflowService.submit(req, pm)


def test_viewer_cannot_create_requests(project, people, workflow):
    with pytest.raises(PermissionDenied):
        WorkflowService.create_request(project, people["viewer"], "Title", "Body")


# ------------------------------------------------------------ decide


def test_approve_advances_to_next_stage(submitted, people):
    WorkflowService.decide(submitted, people["approver1"], A)
    submitted.refresh_from_db()
    assert submitted.state == RequestState.IN_REVIEW
    assert submitted.active_task().position == 2
    assert submitted.active_task().approver == people["approver2"]


def test_final_approval_approves_request_and_ends_cycle(submitted, people):
    WorkflowService.decide(submitted, people["approver1"], A)
    WorkflowService.decide(submitted, people["approver2"], A, "Fine.")
    submitted.refresh_from_db()
    cycle = submitted.current_cycle()
    assert submitted.state == RequestState.APPROVED
    assert cycle.outcome == ReviewCycle.Outcome.APPROVED and cycle.ended_at is not None


def test_reject_requires_reason_and_closes_remaining_stages(submitted, people):
    with pytest.raises(WorkflowError):
        WorkflowService.decide(submitted, people["approver1"], R, "   ")
    WorkflowService.decide(submitted, people["approver1"], R, "Too risky")
    submitted.refresh_from_db()
    assert submitted.state == RequestState.REJECTED
    statuses = list(submitted.current_cycle().tasks.order_by("position").values_list("status", flat=True))
    assert statuses == [StageTask.Status.COMPLETED, StageTask.Status.CLOSED]


def test_request_changes_requires_reason(submitted, people):
    with pytest.raises(WorkflowError):
        WorkflowService.decide(submitted, people["approver1"], C, "")
    WorkflowService.decide(submitted, people["approver1"], C, "Add the rollback plan")
    submitted.refresh_from_db()
    assert submitted.state == RequestState.CHANGES_REQUESTED
    assert submitted.current_cycle().outcome == ReviewCycle.Outcome.CHANGES_REQUESTED


def test_only_active_stage_approver_can_decide(submitted, people):
    with pytest.raises(PermissionDenied):
        WorkflowService.decide(submitted, people["approver2"], A)
    with pytest.raises(PermissionDenied):
        WorkflowService.decide(submitted, people["requester"], A)
    with pytest.raises(PermissionDenied):
        WorkflowService.decide(submitted, people["outsider"], A)


def test_cannot_decide_when_not_in_review(draft, people):
    with pytest.raises(WorkflowError):
        WorkflowService.decide(draft, people["approver1"], A)


# ------------------------------------------------------------ resubmit


def test_resubmit_without_change_is_refused(submitted, people):
    WorkflowService.decide(submitted, people["approver1"], C, "Needs detail")
    with pytest.raises(WorkflowError):
        WorkflowService.resubmit(submitted, people["requester"])


def test_resubmit_creates_new_revision_and_cycle_restarting_at_stage_one(submitted, people):
    requester = people["requester"]
    WorkflowService.decide(submitted, people["approver1"], A)
    WorkflowService.decide(submitted, people["approver2"], C, "Mask card numbers")
    document = submitted.documents.get()
    WorkflowService.add_document_version(submitted, requester, upload(content=b"# Spec\nversion 2\n"), document=document)
    WorkflowService.resubmit(submitted, requester)
    submitted.refresh_from_db()

    assert submitted.state == RequestState.IN_REVIEW
    assert submitted.current_revision.number == 2
    cycles = list(submitted.cycles.order_by("number"))
    assert [c.number for c in cycles] == [1, 2]
    # The old cycle keeps its decisions and its evidence.
    assert Decision.objects.filter(task__cycle=cycles[0]).count() == 2
    assert [rd.document_version.number for rd in cycles[0].revision.revision_documents.all()] == [1]
    # The new cycle reviews the new evidence from stage 1.
    assert [rd.document_version.number for rd in cycles[1].revision.revision_documents.all()] == [2]
    assert submitted.active_task().position == 1


# ------------------------------------------------------------ withdraw


def test_withdraw_requires_reason(submitted, people):
    with pytest.raises(WorkflowError):
        WorkflowService.withdraw(submitted, people["requester"], "")


def test_project_manager_can_withdraw_in_review(submitted, people):
    WorkflowService.withdraw(submitted, people["pm"], "Superseded by PAY-009")
    submitted.refresh_from_db()
    assert submitted.state == RequestState.CANCELLED
    assert submitted.current_cycle().outcome == ReviewCycle.Outcome.CANCELLED
    assert not StageTask.objects.filter(cycle__request=submitted, status=StageTask.Status.ACTIVE).exists()


def test_viewer_cannot_withdraw_and_closed_requests_cannot_be_withdrawn(submitted, people):
    with pytest.raises(PermissionDenied):
        WorkflowService.withdraw(submitted, people["viewer"], "No")
    WorkflowService.decide(submitted, people["approver1"], R, "No")
    with pytest.raises(WorkflowError):
        WorkflowService.withdraw(submitted, people["requester"], "Too late")


# ------------------------------------------------------------ audit


def test_every_transition_writes_an_audit_event(submitted, people):
    WorkflowService.decide(submitted, people["approver1"], C, "More detail")
    WorkflowService.update_content(submitted, people["requester"], submitted.title, "Revised body")
    WorkflowService.resubmit(submitted, people["requester"])
    WorkflowService.withdraw(submitted, people["requester"], "No longer needed")
    actions = list(AuditEvent.objects.filter(request=submitted).order_by("id").values_list("action", flat=True))
    for expected in ["request.created", "document.uploaded", "request.submitted", "decision.request_changes",
                     "request.edited", "request.resubmitted", "request.withdrawn"]:
        assert expected in actions
