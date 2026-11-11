"""The five evaluation tasks (T1-T5, Section 3.1.4) carried out in a real browser."""
import re

import pytest
from playwright.sync_api import expect

from apps.approvals.models import ApprovalRequest, Decision, RequestState
from apps.approvals.services import WorkflowService

pytestmark = pytest.mark.django_db(transaction=True)


def test_t1_raise_with_document_and_submit(login, live_server, people, workflow, tmp_path):
    page = login(people["requester"])
    page.get_by_role("link", name="PAY", exact=True).first.click()
    page.get_by_role("link", name="New change request").click()
    page.get_by_label("Title").fill("Add a daily spend cap to top-ups")
    page.get_by_label("Description").fill("Reject top-ups above the daily cap. Risk: low. Rollback: feature flag.")
    note = tmp_path / "spend-cap-design-note.md"
    note.write_text("# Design note\nDocument version: 1\n")
    page.get_by_label("Supporting document").set_input_files(str(note))
    page.get_by_role("button", name="Save and submit for review").click()
    expect(page.get_by_text("created and submitted for review")).to_be_visible()
    expect(page.locator(".fb-status-strip")).to_contain_text("In review")
    expect(page.locator(".fb-status-strip")).to_contain_text(people["approver1"].full_name)
    assert ApprovalRequest.objects.get().state == RequestState.IN_REVIEW


def test_t2_status_and_next_approver_are_on_the_request_page(login, journey, people):
    WorkflowService.update_content(journey, people["requester"], journey.title, "Now with a rollback plan.")
    WorkflowService.resubmit(journey, people["requester"])
    WorkflowService.decide(journey, people["approver1"], Decision.Outcome.APPROVE)
    page = login(people["viewer"])
    page.get_by_role("link", name="Requests").click()
    page.get_by_label("Search").fill(journey.reference)
    page.get_by_role("button", name="Apply filters").click()
    page.get_by_role("link", name=journey.reference).click()
    strip = page.locator(".fb-status-strip")
    expect(strip).to_contain_text("In review")
    expect(strip).to_contain_text(people["approver2"].full_name)
    expect(strip).to_contain_text("Product owner sign-off")


def test_t3_new_version_and_resubmit(login, journey, people, tmp_path):
    page = login(people["requester"])
    page.goto(f"{page.url.rstrip('/')}{journey.get_absolute_url()}")
    revised = tmp_path / "spec_v2.md"
    revised.write_text("# Spec\nDocument version: 2\nRollback plan added.\n")
    page.get_by_label("File").set_input_files(str(revised))
    page.get_by_role("button", name="Upload").click()
    expect(page.get_by_text("Uploaded as a new version of “spec”: now v2.")).to_be_visible()
    page.get_by_role("button", name=re.compile("Resubmit")).click()
    expect(page.get_by_text("Review restarts at stage 1")).to_be_visible()
    expect(page.get_by_text("Changed since revision 1")).to_be_visible()
    journey.refresh_from_db()
    assert journey.current_revision.number == 2


def test_t4_t5_versions_and_decision_record(login, journey, people, tmp_path):
    requester = people["requester"]
    from conftest import upload
    WorkflowService.add_document_version(journey, requester, upload("spec_v2.md", b"v2"))
    WorkflowService.resubmit(journey, requester)
    WorkflowService.decide(journey, people["approver1"], Decision.Outcome.APPROVE)
    WorkflowService.decide(journey, people["approver2"], Decision.Outcome.APPROVE, "Fine.")
    page = login(people["viewer"])
    page.goto(f"{page.url.rstrip('/')}{journey.get_absolute_url()}")
    record = page.get_by_role("table").filter(has_text="Decision")
    rows = page.locator("section[aria-labelledby=record-h] tbody tr")
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text("Changes requested")
    expect(rows.nth(0)).to_contain_text("Add the rollback plan")
    expect(rows.nth(2)).to_contain_text(people["approver2"].full_name)
    # The final approval was on revision 2, which froze spec v2.
    latest_cycle = page.locator(".card", has_text="Cycle 2 · revision 2")
    expect(latest_cycle).to_contain_text("spec v2")
    assert record is not None


def test_reject_asks_for_confirmation_and_needs_a_reason(login, live_server, journey, people):
    WorkflowService.update_content(journey, people["requester"], journey.title, "Revised.")
    WorkflowService.resubmit(journey, people["requester"])
    page = login(people["approver1"])
    page.goto(f"{live_server.url}{journey.get_absolute_url()}")
    page.get_by_label("Reject").check()
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.get_by_role("button", name="Record decision").click()
    expect(page.get_by_text("Give a reason for this decision.")).to_be_visible()
    page.get_by_label("Reject").check()
    page.get_by_label("Reason").fill("Not this quarter.")
    page.get_by_role("button", name="Record decision").click()
    expect(page.get_by_text("Decision recorded: Rejected.")).to_be_visible()
    assert any("cannot be undone" in m for m in dialogs)
    journey.refresh_from_db()
    assert journey.state == RequestState.REJECTED


def test_outsider_cannot_see_the_request(login, live_server, journey, people):
    page = login(people["outsider"])
    response = page.goto(f"{live_server.url}{journey.get_absolute_url()}")
    assert response.status == 404
