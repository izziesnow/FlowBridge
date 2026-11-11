"""Load test for NFR05: 95th-percentile page response under 1 second with 20 concurrent users.

Each simulated user signs in as a different synthetic ZTL account from the evaluation
dataset and works the way people do: mostly reading their dashboard, project lists and
requests, sometimes searching or commenting.

    locust -f loadtest/locustfile.py --host https://localhost:8443 --headless -u 20 -r 5 -t 3m \
        --csv loadtest/results/run --html loadtest/results/report.html
    python loadtest/check_results.py loadtest/results/run_stats.csv

Environment: LOAD_ACCOUNTS (default evaluation/accounts.csv), LOAD_PASSWORD (default ztl-eval-2026).
"""
import csv
import itertools
import os
import random
import re

import urllib3
from locust import HttpUser, between, task

urllib3.disable_warnings()  # the demo stack uses a self-signed certificate

ACCOUNTS_FILE = os.environ.get("LOAD_ACCOUNTS", "evaluation/accounts.csv")
PASSWORD = os.environ.get("LOAD_PASSWORD", "ztl-eval-2026")
REQUESTS_PER_PROJECT = int(os.environ.get("LOAD_REQUESTS_PER_PROJECT", "20"))

with open(ACCOUNTS_FILE, newline="", encoding="utf-8") as fh:
    ACCOUNTS = [row for row in csv.DictReader(fh) if row["role"] in ("PM", "APPROVER", "REQUESTER")]
random.Random(7).shuffle(ACCOUNTS)
NEXT_ACCOUNT = itertools.cycle(ACCOUNTS)
CSRF = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')


class ProjectMember(HttpUser):
    wait_time = between(1, 4)  # think time between page views

    def on_start(self):
        self.client.verify = False
        self.account = next(NEXT_ACCOUNT)
        self.project = self.account["project"]
        page = self.client.get("/accounts/login/", name="login page")
        token = CSRF.search(page.text).group(1)
        self.client.post("/accounts/login/", name="sign in",
                         data={"username": self.account["email"], "password": PASSWORD,
                               "csrfmiddlewaretoken": token},
                         headers={"Referer": f"{self.host}/accounts/login/"})

    def ref_number(self):
        return random.randint(1, REQUESTS_PER_PROJECT)

    @task(4)
    def open_request(self):
        self.client.get(f"/projects/{self.project}/requests/{self.ref_number()}/", name="request page")

    @task(3)
    def dashboard(self):
        self.client.get("/", name="my work")

    @task(2)
    def project_list(self):
        state = random.choice(["", "IN_REVIEW", "APPROVED"])
        self.client.get(f"/projects/{self.project}/?state={state}", name="project requests (filtered)")

    @task(1)
    def project_dashboard(self):
        self.client.get(f"/projects/{self.project}/dashboard/", name="project dashboard")

    @task(1)
    def search(self):
        self.client.get(f"/requests/?q={random.choice(['retry', 'cache', 'audit', 'export'])}", name="search")

    @task(1)
    def notifications(self):
        self.client.get("/notifications/", name="notifications")

    @task(1)
    def comment(self):
        url = f"/projects/{self.project}/requests/{self.ref_number()}/"
        page = self.client.get(url, name="request page")
        match = CSRF.search(page.text)
        if match:
            self.client.post(f"{url}comments/", name="post comment",
                             data={"body": "Load-test comment (synthetic).", "csrfmiddlewaretoken": match.group(1)},
                             headers={"Referer": f"{self.host}{url}"})
