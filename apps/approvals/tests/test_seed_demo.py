import pytest
from django.core.management import call_command

from apps.approvals.models import ApprovalRequest, RequestState
from apps.projects.models import Project

pytestmark = pytest.mark.django_db


def test_seed_demo_loads_fictional_ztl_data(private_media):
    call_command("seed_demo")
    pay = Project.objects.get(code="PAY")
    states = dict(ApprovalRequest.objects.filter(project=pay).values_list("number", "state"))
    assert states == {
        1: RequestState.APPROVED,
        2: RequestState.IN_REVIEW,
        3: RequestState.APPROVED,
        4: RequestState.REJECTED,
        5: RequestState.CHANGES_REQUESTED,
        6: RequestState.DRAFT,
    }
    # PAY-003 went through two review cycles and kept both.
    assert ApprovalRequest.objects.get(project=pay, number=3).cycles.count() == 2
