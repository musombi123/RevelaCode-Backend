from __future__ import annotations


# =========================================================
# AUTOMATION COLLECTIONS
# =========================================================

RULES = "jumuiya_elimu_automation_rules"
LOGS = "jumuiya_elimu_automation_logs"
JOBS = "jumuiya_elimu_automation_jobs"


# =========================================================
# JOB CONFIGURATION
# =========================================================

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 60
DEFAULT_LOCK_SECONDS = 300


# =========================================================
# JOB STATUSES
# =========================================================

JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_RETRYING = "retrying"
JOB_CANCELLED = "cancelled"


JOB_STATUSES = (
    JOB_PENDING,
    JOB_RUNNING,
    JOB_SUCCEEDED,
    JOB_FAILED,
    JOB_RETRYING,
    JOB_CANCELLED,
)
