# Test records for the evaluation build

Results gathered while building the evaluation release, for Chapter Five. CI repeats every automated check on
each push. See the latest run on the repository's Actions tab.

> All data are synthetic. Zenkora Technologies Limited (ZTL) is a fictional organisation.

## Environment (development workspace, 11 November 2026)

Python 3.13.18 · Django 5.2.19 · PostgreSQL 16.15 · Gunicorn 27 · Google Chrome for Testing 153 · axe-core 4.12.1 ·
Locust 2.x · 2 vCPUs.

## Unit and integration tests

`pytest` runs the whole suite against PostgreSQL. It covers:
- every workflow transition and guard;
- permissions on pages, downloads and exports;
- immutability (model guard and database trigger) and simultaneous decisions;
- notifications, email retries, reminders, reassignment, dashboards and exports;
- the integrity check and the evaluation-data generator.

The count and coverage for each commit are in its CI run.

## End-to-end tests (Playwright)

`pytest e2e` drives a real browser through the five evaluation tasks:
- T1: raise a request with a document and submit it;
- T2: find a request's status and who acts next;
- T3: upload a new version and resubmit;
- T4 and T5: the versions approved, and the decision record.

It also checks three behaviours:
- rejecting asks for confirmation and needs a reason;
- a non-member gets 404;
- keyboard users can skip to the main content.

## Accessibility (NFR07, WCAG 2.2 level AA)

axe-core scanned 15 core pages as four kinds of user, with tags wcag2a, wcag2aa, wcag21a, wcag21aa and wcag22aa.

| Round | Violations | What was fixed |
|---|---|---|
| First scan | 25 colour-contrast nodes on 14 pages; 2 scrollable tables not keyboard-focusable | |
| After fixes | **0 violations** | Links and buttons darkened (#0d6efd → #0a58ca; #6c757d → #565e64), giving at least 4.5:1 on the page background. Scrollable tables made focusable. A visible focus outline added. |

The "needs review" results also exposed two real defects, which were fixed:
- the withdraw, decision and reassign forms on the request page shared one element ID;
- help-text links pointed at IDs that did not exist.

The 13 remaining "needs review" items are select boxes whose contrast axe cannot compute because of
Bootstrap's arrow image. They were checked by hand: dark text (#212529) on white, about 16:1.

Automated tools find only part of all accessibility problems. A keyboard-only walkthrough of the five tasks is
part of the pilot.

## Load (NFR05: 95th percentile under 1 second with 20 concurrent users)

`loadtest/locustfile.py` simulates 20 users signed in as different synthetic accounts, with 1 to 4 seconds of
think time. Each user reads requests, dashboards, filtered lists, search and notifications, and sometimes posts a
comment. The run used the 120-request evaluation dataset.

| Run | Requests | Failures | Median | 95th percentile | Result |
|---|---|---|---|---|---|
| Workspace: Gunicorn (3 workers) over HTTPS, `DEBUG` off, 2 minutes | 1,020 | 0 | 45 ms | 100 ms | Pass |
| CI: full Compose stack through Nginx (HTTPS), GitHub-hosted runner, 3 minutes (run 43083966017) | 1,556 | 0 | 29 ms | 46 ms | Pass |

Signing in is the slowest step (median 580 ms), because password hashing is deliberately slow (PBKDF2).
The CI job repeats the test through Nginx against the full Docker Compose stack on every push and keeps the
Locust report as an artifact.

## Backup and restore (NFR08)

See `docs/operations.md`, "Restore test record". In summary:
- a corrupted backup was refused;
- a clean restore passed `verify_integrity`;
- CI repeats the test against the Compose stack on every push.

## Evaluation dataset checks (Section 3.1.3)

`apps/evaluation/tests` confirms that:
- the same seed gives the same scenario (and a manual comparison found two full runs byte-identical);
- the outcome mix and each problem pattern match the specification exactly;
- sets A and B are matched task for task;
- the loaded system data agree with the scenario for every request, cycle, decision and reviewed document version;
- the baseline artefacts contain the injected patterns;
- the privacy check passes.
