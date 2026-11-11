"""Integrity checks on the evaluation datasets (Section 3.1.3, "Validating the scenario").

They confirm that the scenario is reproducible, that every injected pattern appears exactly
as specified, that the system dataset holds exactly the scenario's facts, and that the
baseline artefacts contain what the patterns say they should.
"""
import csv
import email
import json
import mailbox
from email import policy
from collections import Counter
from pathlib import Path

import pytest
from django.core.management import call_command
from openpyxl import load_workbook

from apps.approvals.models import ApprovalRequest
from apps.evaluation.privacy import check_folder
from apps.evaluation.scenario import OUTCOME_MIX, PATTERNS, TASK_DESIGNS, build_scenario
from apps.evaluation.system import compare_with_system


@pytest.fixture(scope="module")
def scenario():
    return build_scenario()


def test_same_seed_same_scenario_and_different_seed_differs(scenario):
    again, other = build_scenario(), build_scenario(seed=7)
    fingerprint = lambda s: [(x.ref, x.title, x.state, [v.sha256 for v in x.versions]) for x in s.stories]  # noqa: E731
    assert fingerprint(again) == fingerprint(scenario)
    assert fingerprint(other) != fingerprint(scenario)


def test_outcome_mix_and_spread(scenario):
    kinds = Counter(s.kind for s in scenario.stories)
    assert sum(kinds.values()) == 120
    assert kinds == {"APPROVED_1": 42, "APPROVED_2": 18, "REJECTED": 15, "CHANGES": 12, "CANCELLED": 9,
                     "IN_REVIEW": 18, "DRAFT": 6}
    assert set(Counter(s.project for s in scenario.stories).values()) == {20}
    assert {k for k, _ in OUTCOME_MIX} == set(kinds)
    assert all(s.events_end() < scenario.anchor for s in scenario.stories)


def test_patterns_are_injected_at_the_documented_rates(scenario):
    for code, (_, _, rate) in PATTERNS.items():
        assert scenario.pattern_counts[code] == round(rate * scenario.eligible_counts[code])


def test_sets_a_and_b_are_matched(scenario):
    shape = lambda s: (s.kind, sorted(s.patterns), len(s.cycles),  # noqa: E731
                       [(d.stage, d.outcome) for c in s.cycles for d in c.decisions],
                       len({v.doc for v in s.versions}), len(s.versions))
    for name, _, _ in TASK_DESIGNS:
        assert shape(scenario.tasks["A"][name]) == shape(scenario.tasks["B"][name]), name
    assert scenario.tasks["A"]["T3"].requester == scenario.tasks["A"]["persona"]


@pytest.mark.django_db(transaction=True)
def test_full_generation_matches_across_conditions(tmp_path, settings):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "media"
    out = tmp_path / "evaluation"
    call_command("generate_evaluation_data", "--out", str(out), "--load", "--flush")
    s = build_scenario()

    # System condition: exactly the scenario's facts, with a clean integrity check.
    assert compare_with_system(s) == []
    assert ApprovalRequest.objects.count() == 120
    call_command("verify_integrity")

    truth = json.loads((out / "ground_truth/ground_truth.json").read_text())
    assert len(truth["requests"]) == 120
    by_ref = {r["ref"]: r for r in truth["requests"]}

    # Baseline condition: the same requests in the change log...
    book = load_workbook(out / "baseline/spreadsheet/change-log.xlsx")
    log = {row[0]: row for ws in book.worksheets for row in ws.iter_rows(min_row=2, values_only=True)}
    assert set(log) == set(by_ref)
    for story in s.stories:
        status = log[story.ref][4]
        if "P2" in story.patterns:
            assert status.startswith("Awaiting")  # out of date
        elif story.state == "APPROVED":
            assert status == "Approved"

    # ...and in the mailbox, where P4 reasons never appear and P3 documents are never attached.
    mails = list(mailbox.mbox(str(out / "baseline/mail/ztl-change-requests.mbox"),
                              factory=lambda f: email.message_from_binary_file(f, policy=policy.default)))
    assert mails and all("ztl.example" in m["From"] for m in mails)
    for story in s.stories:
        thread = [m for m in mails if f"[{story.ref}]" in (m["Subject"] or "")]
        text = "\n".join(part.get_content() for m in thread for part in m.walk()
                         if part.get_content_type() == "text/plain" and not part.get_filename())
        attached = [part.get_filename() for m in thread for part in m.walk() if part.get_filename()]
        if "P4" in story.patterns:
            for c in story.cycles:
                for d in c.decisions:
                    if d.reason:
                        assert d.reason not in text, story.ref
        if "P3" in story.patterns:
            assert attached == [], story.ref
            folder = next((out / "baseline/shared-drive" / story.project).glob(f"{story.ref} *"))
            assert any("_FINAL" in f.name for f in folder.iterdir())

    # Scenario sets and keys exist for both sets, and nothing private leaked.
    for set_name in "AB":
        assert (out / f"scenario-sets/{set_name}/tasks.md").exists()
        assert len(list((out / f"scenario-sets/{set_name}/materials").iterdir())) == 2
        assert (out / f"ground_truth/answer-key-{set_name}.md").exists()
    assert check_folder(out) == []
    with open(out / "accounts.csv", newline="") as fh:
        assert len(list(csv.DictReader(fh))) == 48  # 36 project staff + 12 viewer memberships
    assert (out / "GENERATION-SPEC.md").read_text().count("| P") >= 4
    assert Path(out / "baseline/mail/inbox.html").stat().st_size > 10_000
