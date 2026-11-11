"""Browser tests (Playwright) against a live Flowbridge server.

Run with:  pytest e2e                         (uses Playwright's Chromium)
           pytest e2e --browser-channel chrome (uses an installed Google Chrome)
"""
import os

import pytest

from apps.approvals.models import Decision
from apps.approvals.services import WorkflowService
from conftest import PASSWORD, upload

# Playwright's sync API runs an event loop; Django's ORM is still used synchronously here.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture
def login(page, live_server):
    def _login(user):
        page.context.clear_cookies()
        page.goto(f"{live_server.url}/accounts/login/")
        page.get_by_label("Email address").fill(user.email)
        page.get_by_label("Password").fill(PASSWORD)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url(f"{live_server.url}/")
        return page
    return _login


@pytest.fixture
def journey(transactional_db, people, project, workflow):
    """A request that went through one request for changes and was then approved."""
    requester = people["requester"]
    req = WorkflowService.create_request(project, requester, "Add retry to callbacks", "Retry failed callbacks.")
    WorkflowService.add_document_version(req, requester, upload())
    WorkflowService.submit(req, requester)
    WorkflowService.decide(req, people["approver1"], Decision.Outcome.REQUEST_CHANGES, "Add the rollback plan")
    return req
