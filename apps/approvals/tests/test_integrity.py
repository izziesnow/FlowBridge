"""Integration tests against PostgreSQL: immutability triggers and simultaneous decisions (NFR02, NFR04)."""
import threading

import pytest
from django.db import DatabaseError, connection, transaction
from django.db.models import F

from apps.approvals.models import ApprovalRequest, Decision, DocumentVersion, Revision
from apps.approvals.services import WorkflowError, WorkflowService
from apps.audit.models import AuditEvent
from apps.core_immutable import ImmutableRecordError

A = Decision.Outcome.APPROVE


@pytest.mark.django_db
def test_model_guard_refuses_changes_to_a_revision(submitted):
    revision = submitted.current_revision
    revision.title = "Tampered"
    with pytest.raises(ImmutableRecordError):
        revision.save()
    with pytest.raises(ImmutableRecordError):
        revision.delete()


@pytest.mark.django_db
@pytest.mark.parametrize("model", [Decision, DocumentVersion, AuditEvent, Revision])
def test_database_trigger_refuses_bulk_update_and_delete(submitted, people, model):
    WorkflowService.decide(submitted, people["approver1"], A)
    assert model.objects.exists()
    table = model._meta.db_table

    def raw(sql):
        with connection.cursor() as cursor:
            cursor.execute(sql)

    # Bulk ORM updates and raw SQL both bypass the model guard; the trigger still refuses them.
    operations = [
        lambda: model.objects.update(id=F("id")),
        lambda: raw(f"UPDATE {table} SET id = id"),
        lambda: raw(f"DELETE FROM {table}"),
    ]
    for operation in operations:
        with pytest.raises(DatabaseError, match="immutable"):
            with transaction.atomic():
                operation()
    assert model.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_simultaneous_decisions_on_one_stage_record_exactly_one(project, people):
    """Two approver sessions decide at the same moment. The row lock lets one through; the other is refused."""
    pm = people["pm"]
    version = WorkflowService.create_workflow_version(project, pm, "Single stage")
    WorkflowService.add_stage(version, pm, "Technical lead review", people["approver1"])
    WorkflowService.publish_workflow(version, pm)
    req = WorkflowService.create_request(project, people["requester"], "Race", "Two clicks at once")
    WorkflowService.submit(req, people["requester"])

    barrier = threading.Barrier(2)
    outcomes = []

    def attempt():
        try:
            barrier.wait()
            WorkflowService.decide(ApprovalRequest.objects.get(pk=req.pk), people["approver1"], A)
            outcomes.append("ok")
        except WorkflowError:
            outcomes.append("refused")
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == ["ok", "refused"]
    assert Decision.objects.filter(task__cycle__request=req).count() == 1
