# Operating Flowbridge

This guide covers running the production-like stack, backups and restores, and the checks that show the evidence store is intact.

> Flowbridge is demonstrated with the fictional organisation Zenkora Technologies Limited (ZTL). All demo data are synthetic.

## The stack

`docker compose up --build -d` starts five services.

| Service | Image | Role |
|---|---|---|
| `db` | postgres:16 | Relational storage, transactions, row locks and immutability triggers |
| `web` | this repository | Migrates, collects static files, then runs Django under Gunicorn (3 workers) |
| `nginx` | nginx:1.27-alpine | Terminates HTTPS on port 8443, redirects port 8080 to HTTPS, serves static files, adds security headers |
| `scheduler` | this repository | Every 15 minutes: `send_reminders` (overdue stages) and `send_emails` (pending or failed emails) |
| `backup` | postgres:16 | Daily backup of the database and documents into `./backups`, kept for 14 days |

Nginx uses a certificate mounted at `/etc/nginx/certs/server.crt` and `server.key`. If none is mounted, it generates a self-signed one, so browsers will warn on first visit. For a shared server, mount a real certificate and set `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `SITE_URL` in a `.env` file.

Private documents are never served by Nginx. They live in the `private_media` volume and reach users only through Django's permission-checked download view, which re-verifies each file's SHA-256 checksum.

## Health and integrity

- `GET /healthz` returns `ok` when the application can reach the database. Docker uses it to decide when `web` is ready.
- `python manage.py verify_integrity` checks that:
  - every document file exists and matches its checksum;
  - the immutability trigger is installed on all eight evidence tables;
  - every request in review has exactly one open cycle and one active stage;
  - every completed stage has a decision by that stage's approver;
  - each request points at its latest revision.

  It exits with status 1 if anything is wrong.

## Backups (NFR08)

`scripts/backup.sh` writes `backups/flowbridge-YYYYMMDD-HHMMSS/` containing:

- `db.dump`: a PostgreSQL custom-format dump;
- `media.tar.gz`: the private document store;
- `SHA256SUMS`: checksums of both files;
- `manifest.txt`: time, source and row counts for the key tables.

Run one on demand with:

```bash
docker compose run --rm backup /scripts/backup.sh
```

## Restoring

1. Stop the services that write data: `docker compose stop web scheduler`.
2. Restore: `docker compose run --rm backup /scripts/restore.sh /backups/flowbridge-YYYYMMDD-HHMMSS`.
   The script first checks both files against `SHA256SUMS` and refuses a damaged backup.
3. Start again: `docker compose start web scheduler`.
4. Verify: `docker compose exec web python manage.py verify_integrity`.

## Restore test record

The restore procedure is tested in two places.

**Automated, on every push.** The `compose-smoke` job in `.github/workflows/ci.yml`:

1. brings up the stack and checks HTTPS, the HTTP→HTTPS redirect and the security headers;
2. loads the demo data and takes a backup;
3. wipes the database, restores the backup and runs `verify_integrity`;
4. confirms all six PAY requests are back.

**Manual, 11 November 2026, development workspace (PostgreSQL 16.15, scripts run directly against the database).**

| Step | Result |
|---|---|
| Backup of demo data | 6 requests, 6 revisions, 8 document versions, 13 decisions, 46 audit events |
| Simulated loss | Database flushed and document folder emptied (0 requests) |
| Restore from a deliberately corrupted copy | Refused: `media.tar.gz` failed its SHA-256 check |
| Restore from the intact backup | Completed |
| `verify_integrity` | Passed: 8/8 document checksums, 8/8 triggers, 6 requests, 13 decisions consistent |

## Email (optional, FR13)

Users switch email on from their preferences page. The default backend prints messages to the `web` and `scheduler` logs. To send real mail, set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and `DEFAULT_FROM_EMAIL`. Emails are sent only after the action that caused them commits. Failures are recorded on the notification and retried up to three times by the scheduler.
