"""Audited stage reassignment by the project manager (Section 3.2.1; NFR03)."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from apps.approvals.models import Decision, Reassignment, RequestState, StageTask
from apps.approvals.services import WorkflowError, WorkflowService
from apps.audit.models import AuditEvent
from apps.core_immutable import ImmutableRecordError
from apps.notifications.models import Notification
from apps.projects.models import Membership, Role
from conftest import make_user

pytestmark = pytest.mark.django_db
A = Decision.Outcome.APPROVE


@pytest.fixture
def standby(project):
    user = make_user("standby@ztl.example", "Kemi Lawal")
    Membership.objects.create(project=project, user=user, role=Role.APPROVER)
    return user


def active(req):
    return StageTask.objects.get(cycle__request=req, status=StageTask.Status.ACTIVE)


def test_pm_reassigns_active_stage_and_new_approver_decides(submitted, people, standby):
    task = active(submitted)
    task.due_at = timezone.now() - timedelta(hours=5)
    task.save(update_fields=["due_at"])

    WorkflowService.reassign_stage(submitted, people["pm"], task, standby, "Funmilayo is on leave")
    task.refresh_from_db()
    assert task.approver == standby
    assert task.due_at > timezone.now()  # fresh decision window

    with pytest.raises(PermissionDenied):
        WorkflowService.decide(submitted, people["approver1"], A)
    WorkflowService.decide(submitted, standby, A)
    assert active(submitted).position == 2


def test_reassignment_is_recorded_audited_and_notified(submitted, people, standby):
    task = active(submitted)
    WorkflowService.reassign_stage(submitted, people["pm"], task, standby, "Workload")
    move = Reassignment.objects.get(task=task)
    assert (move.from_user, move.to_user, move.actor, move.reason) == (
        people["approver1"], standby, people["pm"], "Workload")
    assert AuditEvent.objects.filter(request=submitted, action="stage.reassigned").exists()
    assert Notification.objects.filter(recipient=standby, kind=Notification.Kind.REASSIGNED).exists()
    assert Notification.objects.filter(recipient=people["approver1"], kind=Notification.Kind.REASSIGNED).exists()
    with pytest.raises(ImmutableRecordError):
        move.save()


def test_waiting_stage_can_be_reassigned_for_this_cycle_only(submitted, people, standby, workflow):
    waiting = StageTask.objects.get(cycle__request=submitted, position=2)
    WorkflowService.reassign_stage(submitted, people["pm"], waiting, standby, "Product owner travelling")
    waiting.refresh_from_db()
    assert waiting.approver == standby and waiting.status == StageTask.Status.PENDING
    assert workflow.stages.get(position=2).approver == people["approver2"]  # published workflow unchanged


def test_reassignment_guards(submitted, people, standby):
    task = active(submitted)
    with pytest.raises(PermissionDenied):
        WorkflowService.reassign_stage(submitted, people["approver1"], task, standby, "Swap")
    with pytest.raises(WorkflowError):
        WorkflowService.reassign_stage(submitted, people["pm"], task, standby, "  ")
    with pytest.raises(WorkflowError):
        WorkflowService.reassign_stage(submitted, people["pm"], task, people["viewer"], "Viewer")
    with pytest.raises(WorkflowError):
        WorkflowService.reassign_stage(submitted, people["pm"], task, people["approver1"], "Same person")


def test_requester_can_never_be_given_their_own_stage(submitted, people):
    people["requester"].memberships.update(role=Role.APPROVER)
    with pytest.raises(WorkflowError):
        WorkflowService.reassign_stage(submitted, people["pm"], active(submitted), people["requester"], "Cover")


def test_closed_requests_cannot_be_reassigned(submitted, people, standby):
    task = active(submitted)
    WorkflowService.decide(submitted, people["approver1"], Decision.Outcome.REJECT, "No")
    submitted.refresh_from_db()
    assert submitted.state == RequestState.REJECTED
    with pytest.raises(WorkflowError):
        WorkflowService.reassign_stage(submitted, people["pm"], task, standby, "Late")


def test_reassign_through_the_interface(submitted, people, standby, client_for):
    url = reverse("approvals:request_reassign", args=["PAY", submitted.number])
    data = {"task": active(submitted).pk, "new_approver": standby.pk, "reason": "Leave cover"}
    assert client_for(people["requester"]).post(url, data).status_code == 403
    client_for(people["pm"]).post(url, data)
    assert active(submitted).approver == standby
