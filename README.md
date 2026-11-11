# Flowbridge

A web-based information management system that keeps an IT project's change requests, review stages, versioned documents and decisions in one traceable record.

Flowbridge is the artefact for a Professional Master of Information Technology (MIT) project at MIVA Open University: *Design and Implementation of a Web-Based Information Management System for Streamlining Communication and Approval Workflows in IT Project Management*.

> **Fictional setting.** The system is demonstrated at **Zenkora Technologies Limited (ZTL)**, a fictional Lagos-based IT services firm created for this project. ZTL is not a real company, and every user, project, request and document in the demo data is synthetic.

## What it does (increments 1 and 2)

- **Accounts.** Email sign-in with administrator-managed accounts. Passwords are stored as salted hashes.
- **Projects and roles.** Each person holds one role per project: project manager, requester, approver or viewer. Non-members get a 404 for every project page, request and document.
- **Sequential workflows.** A project manager designs and publishes workflow versions of one to five stages, with one named approver and a due time per stage. Published versions never change.
- **Requests and revisions.** Submitting a draft freezes an immutable revision that binds the exact document versions under review, then activates stage 1.
- **Decisions.** Approvers approve, reject or request changes. A reason is required to reject, request changes or withdraw. Requesters can never approve their own requests.
- **Review cycles.** Requesting changes ends the cycle. Resubmitting creates a new revision and a new cycle that restarts at stage 1. Earlier cycles keep their decisions and evidence.
- **Documents.** Every upload is a new immutable version with a SHA-256 checksum. Files sit in private storage and are served only through a permission-checked view that re-verifies the checksum.
- **Audit history.** Every state change, decision, upload, comment, reassignment and membership change writes an append-only audit event.
- **Discussion.** Each request has a comment thread, and each comment records the revision it was written about. Each project also has a general discussion page. Comments and messages cannot be edited or deleted. Viewers can read but not post.
- **Notifications.** In-app notifications tell approvers when a stage needs them and tell requesters about decisions and outcomes. They also cover comments, project messages, reassignments, withdrawals and overdue stages. The person who acted is never notified of their own action.
- **Overdue flags and reminders.** A stage is overdue once its due time passes. Overdue requests are flagged and can be filtered on the project page. `python manage.py send_reminders` reminds the approver at most once every 24 hours, and the project manager is told the first time.
- **Stage reassignment.** The project manager can move an active or waiting stage of the open cycle to another approver, with a reason. An active stage gets a fresh due time. The published workflow does not change, and each move is kept as an immutable record and an audit event.

### Request states

`Draft → In review → Approved`, with `Rejected`, `Changes requested` and `Cancelled` as the other outcomes.

| From | Action | Actor | To | Guard |
|---|---|---|---|---|
| Draft | Submit | Requester | In review | Title and description present; workflow published |
| In review | Approve (more stages) | Stage approver | In review | Approver is not the requester |
| In review | Approve (last stage) | Stage approver | Approved | Approver is not the requester |
| In review | Reject | Stage approver | Rejected | Reason required |
| In review | Request changes | Stage approver | Changes requested | Reason required |
| Changes requested | Resubmit | Requester | In review | Content or documents changed |
| Draft, In review, Changes requested | Withdraw | Requester or PM | Cancelled | Reason required |

## Design rules worth knowing

- **One place for state changes.** Views never change a request's state. Every transition goes through `apps/approvals/services.py` (`WorkflowService`). Each operation runs in a single transaction and locks the request row with `SELECT … FOR UPDATE`, so two simultaneous decisions on one stage cannot both succeed.
- **Evidence cannot be edited.** Revisions, revision–document links, document versions, decisions and audit events are immutable twice over: the model refuses updates and deletes, and a PostgreSQL trigger refuses them at database level, including bulk ORM updates and raw SQL. See `apps/core_immutable.py`.
- **Limits.** The audit trail supports internal accountability. It is not a legal signature service and does not protect against a database superuser who drops the triggers.

## Stack

Python 3.13 · Django 5.2 LTS · PostgreSQL 16 · Bootstrap 5 (server-rendered) · pytest + pytest-django · Docker Compose · GitHub Actions

## Run it

### With Docker Compose

```bash
docker compose up --build
docker compose exec web python manage.py seed_demo
```

Open http://localhost:8000. The `scheduler` service runs `send_reminders` every 15 minutes.

### Without Docker

You need Python 3.13 and a running PostgreSQL 16 server.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # then export the variables, or set them in your shell
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

### Demo accounts

All demo accounts use the password `ztl-demo-2026`. The `.example` domain is reserved, so these addresses can never reach a real inbox.

| Email | Role |
|---|---|
| admin@ztl.example | Administrator |
| chinedu.eze@ztl.example | Project manager, PAY (also stage 1 approver) |
| aisha.bello@ztl.example | Requester, PAY |
| emeka.nwosu@ztl.example | Requester, PAY |
| funmilayo.ogunleye@ztl.example | Approver, PAY (technical lead) |
| ibrahim.musa@ztl.example | Approver, PAY (product owner) |
| ngozi.obi@ztl.example | Viewer, PAY |
| bola.adekunle@ztl.example | Project manager, HRM only (cannot see PAY) |

Project **PAY** holds six requests covering each state. PAY-003 went through two review cycles with comments in each. PAY-002 is overdue at stage 2, and its stage 3 has been reassigned. Run `python manage.py send_reminders` to see the reminder job flag PAY-002. Run `python manage.py seed_demo --flush` to reset everything.

## Tests

```bash
pytest                       # needs PostgreSQL: the triggers and row locks are tested for real
pytest --cov                 # with coverage
```

The suite covers every workflow transition and guard and the permission checks on pages and downloads. It also covers immutability (model guard and database trigger), simultaneous decisions, document checksums, comments, notifications, reminders, reassignment and the demo seed. CI runs it on every push against a PostgreSQL 16 service container.

## Project layout

```
config/            settings and URLs
apps/accounts/     custom User model with email sign-in
apps/projects/     Project, Membership and project-based access control
apps/approvals/    workflows, requests, revisions, documents, cycles, decisions; WorkflowService
apps/audit/        append-only AuditEvent
apps/discussion/   request comments and project discussion
apps/notifications/ in-app notifications and the overdue reminder job
apps/core_immutable.py   immutable model base and PostgreSQL trigger SQL
templates/, static/      Bootstrap 5 interface
```

## Roadmap

1. **Increment 1 (done):** accounts, projects, membership, sequential workflows, revisions, documents, decisions, audit.
2. **Increment 2 (done):** request comments and project discussion, in-app notifications, overdue flags with a reminder command, audited stage reassignment by the project manager.
3. **Increment 3:** dashboards and filters, history export, optional email, Nginx and Gunicorn in Compose, backup and restore.
4. **Increment 4:** synthetic evaluation datasets and the manual baseline, usability fixes, frozen evaluation build.
