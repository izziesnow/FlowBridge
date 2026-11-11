"""Tools for running remote evaluation sessions on a hosted copy (evaluation/protocol/README.md).

Switched on with EVALUATION_TOOLS=1, only on the copy used for the user acceptance test:

- the participants' files (baseline sandbox and task materials) are built from the same fixed
  seed as the loaded data and offered as zip downloads. The answer keys are never included;
- an administrator can reset the system data between participants, because tasks T1 and T3
  change it.

The reset runs in a background thread, because reloading 120 requests into a hosted database can
take longer than a web request may last. Its progress is kept in a small file shared by all
worker processes.
"""
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command

from apps.evaluation.system import DEFAULT_PASSWORD

WORK_DIR = Path(tempfile.gettempdir()) / "flowbridge-evaluation"
STATUS_FILE = WORK_DIR / "reset-status.json"
RESET_TIMEOUT_SECONDS = 15 * 60

# Download name -> folder inside the generated output. Ground truth is deliberately absent.
BUNDLES = {
    "baseline.zip": "baseline",
    "materials-A.zip": "scenario-sets/A/materials",
    "materials-B.zip": "scenario-sets/B/materials",
}

_build_lock = threading.Lock()


def hosted_password():
    return os.environ.get("HOSTED_PASSWORD", "").strip() or DEFAULT_PASSWORD


def _zip_folder(source, target):
    partial = target.with_suffix(".part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source.parent))
    partial.replace(target)


def build_bundles(force=False):
    """Write the participant zip files, unless they already exist. Returns the folder holding them."""
    bundles = WORK_DIR / "bundles"
    with _build_lock:
        if not force and all((bundles / name).is_file() for name in BUNDLES):
            return bundles
        out = WORK_DIR / "generated"
        shutil.rmtree(out, ignore_errors=True)
        # Without --load this writes files only; the same seed gives the same files as the loaded data.
        call_command("generate_evaluation_data", out=str(out), stdout=StringIO())
        bundles.mkdir(parents=True, exist_ok=True)
        for name, folder in BUNDLES.items():
            _zip_folder(out / folder, bundles / name)
        shutil.rmtree(out, ignore_errors=True)
        return bundles


def read_status():
    try:
        return json.loads(STATUS_FILE.read_text())
    except (OSError, ValueError):
        return {"state": "idle"}


def _write_status(**status):
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    partial = STATUS_FILE.with_suffix(".part")
    partial.write_text(json.dumps(status))
    partial.replace(STATUS_FILE)


def reset_running():
    status = read_status()
    return status.get("state") == "running" and time.time() - status.get("started", 0) < RESET_TIMEOUT_SECONDS


def _reset(requested_by):
    started = time.time()
    try:
        call_command(
            "generate_evaluation_data", load=True, flush=True, password=hosted_password(),
            out=tempfile.mkdtemp(prefix="flowbridge-eval-"), stdout=StringIO(),
        )
    except Exception as error:  # reported on the reset page; the moderator can try again
        _write_status(state="failed", started=started, finished=time.time(), requested_by=requested_by,
                      error=f"{type(error).__name__}: {error}")
    else:
        _write_status(state="done", started=started, finished=time.time(), requested_by=requested_by)


def start_reset(requested_by, run_in_thread=True):
    """Start reloading the evaluation dataset. Returns False if a reset is already running."""
    if reset_running():
        return False
    _write_status(state="running", started=time.time(), requested_by=requested_by)
    if run_in_thread:
        threading.Thread(target=_reset, args=(requested_by,), daemon=True).start()
    else:
        _reset(requested_by)
    return True
