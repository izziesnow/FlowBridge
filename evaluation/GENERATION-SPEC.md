# Evaluation dataset: generation specification

Zenkora Technologies Limited (ZTL) is a fictional organisation. Every person, project, request, message and
document in this dataset is synthetic.

## Reproducing it

```bash
python manage.py generate_evaluation_data --seed 2026 --load --flush
```

The same seed always produces the same scenario, files and ground truth.
Ground-truth fingerprint (SHA-256 of `ground_truth/ground_truth.json`): `3e2ea0318212674a41b45eb785d6b680c9fc5845c552921cc00a7bc78d57f552`

| Parameter | Value |
|---|---|
| Seed | 2026 |
| Scenario "today" | 02 November 2026, 09:00 (Africa/Lagos) |
| Projects | 6 (PAY, CRM, HRM, LND, TEL, GOV), 20 requests each |
| Staff | 40 coded synthetic users (6 PMs, 6 technical leads, 6 product owners, 18 requesters, 4 QA viewers) plus one administrator |
| Requests | 120 software change requests raised over about five months |
| Approval chain | Project manager review → technical lead review → product owner sign-off (sequential) |
| Names | Faker locales yo_NG, ig_NG, ha_NG, en_NG, seeded |
| Text | Request, document, comment and email text from fixed English templates, chosen with the same seed |

## Outcome mix

| Outcome | Target share | Requests |
|---|---|---|
| APPROVED_1 | 35.0% | 42 |
| APPROVED_2 | 15.0% | 18 |
| REJECTED | 12.5% | 15 |
| CHANGES | 10.0% | 12 |
| CANCELLED | 7.5% | 9 |
| IN_REVIEW | 15.0% | 18 |
| DRAFT | 5.0% | 6 |

## Problem patterns injected into the baseline

Patterns are injected into the baseline artefacts only. The system dataset holds the same facts without them.
Each pattern applies to an exact number of eligible requests: round(rate × eligible).

| Code | Pattern | Description | Rate | Eligible | Injected |
|---|---|---|---|---|---|
| P1 | Unclear ownership | No single record shows who must act next | 30% | 112 | 34 |
| P2 | Status divergence | Status differs between email, chat and spreadsheet | 25% | 104 | 26 |
| P3 | Version confusion | Several copies of a document circulate under misleading names | 50% | 42 | 21 |
| P4 | Lost rationale | A decision's reason is missing from email and the spreadsheet | 30% | 98 | 29 |

Eligibility: P1, any submitted request; P2, any request with at least one decision; P3, any submitted request
with more than one version of a document; P4, any submitted request with at least one decision reason.

How each pattern appears:

- **P1**: approval emails say "Passing it along" instead of naming the next approver, and the log's *With*
  column is blank, "TBC" or wrong. For requests in review, the chat also names the wrong person.
- **P2**: the log keeps the status from soon after first submission. For half of these, the chat claims the
  request is approved when it is not.
- **P3**: emails say the documents are on the drive instead of attaching them, and the drive folder also holds
  misleading copies (`*_FINAL.md` holds version 1, `* (1).md` duplicates the latest,
  `*_final_reviewed.md` holds the previous version).
- **P4**: rejection and change emails say the comments were given "on the call". For about half, the reason
  survives only in the chat; otherwise it is recorded nowhere. Approval notes are also left out.

## Matched task requests (scenario sets A and B)

Both sets use the same task designs:

| Task | Request kind | Fixed design |
|---|---|---|
| T2 | IN_REVIEW | approvals_before_wait=1, two_cycles=False, n_docs=1, extra_draft=False |
| T3 | CHANGES | fail_stage=2, two_cycles=False, n_docs=1, extra_draft=False, persona=True |
| T4 | APPROVED_2 | fail_stage=2, n_docs=2, extra_draft=False |
| T5 | APPROVED_2 | fail_stage=3, n_docs=1, extra_draft=False |

| Set | Project | Persona | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|---|
| A | LND | Ozioma Nwachukwu | LND-017 (P1, P2) | LND-019 (none) | LND-008 (P3) | LND-003 (P4) |
| B | TEL | Blessing Adetokunbo | TEL-018 (P1, P2) | TEL-014 (none) | TEL-005 (P3) | TEL-003 (P4) |

## Files

- `baseline/`: the manual-process sandbox (email, chat, spreadsheet, shared drive)
- `scenario-sets/A`, `scenario-sets/B`: task cards and the files participants need
- `ground_truth/`: scoring keys (not for participants)
- The system dataset is loaded into Flowbridge with `--load`; every record goes through `WorkflowService`
  on a simulated clock, so it has the same evidence and audit trail as real use.
