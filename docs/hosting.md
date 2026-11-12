# Hosting a test copy online

This sets up a public test copy of Flowbridge that supervisors and other stakeholders can open from a link, sign in to and try. It uses two free services:

- **[Render](https://render.com)** runs the application, built from this repository's Dockerfile.
- **[Neon](https://neon.com)** provides the PostgreSQL database. Render's own free database is deleted after 30 days, while Neon's free database does not expire.

The copy holds synthetic data for the fictional organisation ZTL only. Do not enter real personal or company data into it.

## What is different from the Docker Compose stack

| Docker Compose (Section 4.1) | Hosted test copy |
|---|---|
| Nginx terminates HTTPS and adds the security headers | Render terminates HTTPS; the application adds the same headers (`SECURITY_HEADERS_IN_APP=1`) |
| Nginx serves static files | WhiteNoise serves them from the application |
| Documents are files in a private volume | Documents are stored in PostgreSQL (`DOCUMENT_STORAGE=database`), because Render's free disk is wiped on every restart. Checksums are still verified on every download. |
| A scheduler sends overdue reminders every 15 minutes | No scheduler: Render's free plan has no background workers. Overdue flags still appear on the dashboards. |
| A daily backup service | No automatic backup beyond Neon's six-hour restore window |

The free plans also bring two limits worth telling testers about:

- **The first visit after a quiet spell is slow.** Render puts the app to sleep after 15 minutes without visitors, and waking it takes about a minute. Neon's database also sleeps after five minutes and wakes in about a second.
- **Monthly allowances.** Render gives 750 free hours a month, enough for one app running all the time. Neon gives 100 compute-hours a month, which a test copy that sleeps when idle stays well within.

## One-time set-up (about 10 minutes)

### 1. Create the database on Neon

1. Sign up at [neon.com](https://neon.com) (signing in with GitHub is quickest).
2. Create a project named `flowbridge` in the region **AWS Europe Central 1 (Frankfurt)**, close to the app. Neon currently creates PostgreSQL 18 databases; the app runs on them unchanged, although the Compose stack and CI use version 16.
3. On the project dashboard, click **Connect** and copy the connection string. It looks like `postgresql://user:password@ep-…eu-central-1.aws.neon.tech/neondb?sslmode=require`.

### 2. Create the app on Render

1. Open **[Deploy to Render](https://render.com/deploy?repo=https://github.com/izziesnow/FlowBridge)** and sign in with GitHub.
2. Render reads `render.yaml` from the repository and asks for two values:
   - `DATABASE_URL`: paste the Neon connection string.
   - `HOSTED_PASSWORD`: choose the password every test account will use. Leave it blank to use the demo password in the README. Since this repository is public, choose your own.
3. Click **Deploy Blueprint**. The first build takes about five to ten minutes.
4. When the service shows **Live**, its address appears at the top of its page, for example `https://flowbridge.onrender.com` (Render adds a suffix if the name is taken). That is the link to share.

On first start-up the app creates its tables and loads the demo data. Later restarts and redeploys keep everything testers have done.

### 3. Share it

Send testers the link, the password you chose and the accounts below. Each person can sign in as any of them, and two people can test as different users at the same time.

| Email | Role |
|---|---|
| aisha.bello@ztl.example | Requester, PAY |
| chinedu.eze@ztl.example | Project manager, PAY (also stage 1 approver) |
| funmilayo.ogunleye@ztl.example | Approver, PAY (technical lead) |
| ibrahim.musa@ztl.example | Approver, PAY (product owner) |
| ngozi.obi@ztl.example | Viewer, PAY |
| bola.adekunle@ztl.example | Project manager of another project; cannot see PAY |
| admin@ztl.example | Administrator |

## Choosing the dataset

`HOSTED_DATASET` decides what is loaded into an empty database:

- `demo` (the default): the small PAY project, with six requests that cover every state.
- `evaluation`: the 120-request evaluation dataset across six projects, with 48 accounts listed in `evaluation/accounts.csv`.

Data are loaded only when the database has no accounts. To switch datasets or start again, reset the database (next section).

## Resetting the data

Render's free plan has no console, so the reset is done from the database side:

1. In the Neon console, open **SQL Editor** and run:
   ```sql
   DROP SCHEMA public CASCADE;
   CREATE SCHEMA public;
   ```
   This deletes every table and record in the test copy.
2. On Render, change `HOSTED_DATASET` or `HOSTED_PASSWORD` under **Environment** if you want to, then choose **Manual Deploy → Deploy latest commit**.

On start-up the app finds an empty database, recreates the tables and loads the chosen dataset.

## A second copy for the evaluation sessions

`render.yaml` also defines `flowbridge-uat`, a separate copy for the user acceptance test, so sessions never disturb the demo copy. It loads the 120-request evaluation dataset and switches on two extras (`EVALUATION_TOOLS=1`):

- `/evaluation/files/`: public downloads of the baseline sandbox and the task materials for sets A and B. The answer keys are never offered.
- `/evaluation/reset/`: administrators only. It reloads the evaluation dataset before each participant.

It needs its own database. In the Neon console, open the project, go to **Databases → New database**, and name it `flowbridge_uat`. Copy its connection string; it is the same as the first one except for the database name at the end. On Render, add it as `DATABASE_URL` on `flowbridge-uat`, together with `HOSTED_PASSWORD`. How to run the sessions: `evaluation/protocol/remote-sessions.md`.

## Updating the app

Every push to the `main` branch redeploys the app automatically. Data are kept, and new database migrations run on start-up.
