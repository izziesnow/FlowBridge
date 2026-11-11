"""Automated accessibility scan of the core pages against WCAG 2.2 level A and AA (NFR07).

Uses axe-core through Playwright. Each page's full axe result is saved to
e2e-reports/axe/ for the write-up. Automated checks find only part of all
accessibility problems, so a keyboard-only walkthrough is also done by hand.
"""
import json
from pathlib import Path

import pytest
from axe_playwright_python.sync_playwright import Axe

from apps.approvals.models import Decision
from apps.approvals.services import WorkflowService
from apps.discussion.services import post_comment, post_project_message

pytestmark = pytest.mark.django_db(transaction=True)
REPORTS = Path("e2e-reports/axe")
WCAG = {"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
        "resultTypes": ["violations", "incomplete"]}


def scan(page, name):
    results = Axe().run(page, options=WCAG)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{name}.json").write_text(json.dumps(results.response, indent=2))
    return results


def test_core_pages_have_no_wcag_violations(page, live_server, login, journey, people):
    WorkflowService.update_content(journey, people["requester"], journey.title, "Revised.")
    WorkflowService.resubmit(journey, people["requester"])
    post_comment(journey, people["approver1"], "Looks better. @req, thanks.")
    post_project_message(journey.project, people["pm"], "Release freeze on Friday.")
    ref = journey.get_absolute_url()

    failures = {}
    page.goto(f"{live_server.url}/accounts/login/")
    results = scan(page, "login")
    if results.violations_count:
        failures["login"] = results.generate_report()

    pages = {
        "approver": (people["approver1"], [("dashboard", "/"), ("request-decision-form", ref),
                                           ("notifications", "/notifications/?show=all")]),
        "pm": (people["pm"], [("project", "/projects/PAY/"), ("project-dashboard", "/projects/PAY/dashboard/"),
                              ("members", "/projects/PAY/members/"), ("audit-log", "/projects/PAY/history/"),
                              ("workflows", "/projects/PAY/workflows/"), ("workflow", "/projects/PAY/workflows/1/"),
                              ("request-reassign", ref)]),
        "requester": (people["requester"], [("new-request", "/projects/PAY/requests/new/"),
                                            ("requests-search", "/requests/?q=retry"),
                                            ("discussion", "/projects/PAY/discussion/"),
                                            ("preferences", "/accounts/preferences/")]),
    }
    for role, (user, urls) in pages.items():
        login(user)
        for name, path in urls:
            page.goto(f"{live_server.url}{path}")
            results = scan(page, f"{role}-{name}")
            if results.violations_count:
                failures[f"{role}-{name}"] = results.generate_report()

    assert not failures, "\n\n".join(f"== {k}\n{v}" for k, v in failures.items())


def test_keyboard_users_can_skip_to_content(page, live_server, login, people):
    login(people["viewer"])
    page.keyboard.press("Tab")
    focused = page.evaluate("document.activeElement.textContent.trim()")
    assert focused == "Skip to main content"
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"
