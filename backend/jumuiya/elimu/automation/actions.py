# backend/jumuiya/elimu/automation/actions.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


# ============================================================
# ACTION RESULT
# ============================================================

@dataclass(frozen=True)
class ActionResult:
    """
    Standard result returned by every automation action.
    """

    status: str
    action: str
    message: str = ""
    data: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "message": self.message,
            "data": self.data or {},
        }


# ============================================================
# ACTION DEFINITION
# ============================================================

@dataclass(frozen=True)
class ActionDefinition:
    """
    Metadata describing one automation action.
    """

    name: str
    description: str
    permission: str
    scope: str
    executor: Callable[..., ActionResult]


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _payload(
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}

    return context


def _required(
    payload: dict[str, Any],
    field: str,
) -> Any:
    value = payload.get(field)

    if value is None or value == "":
        raise ValueError(
            f"Automation action requires '{field}'."
        )

    return value


def _string(
    payload: dict[str, Any],
    field: str,
    default: str = "",
) -> str:
    value = payload.get(field, default)

    if value is None:
        return default

    return str(value).strip()


# ============================================================
# ACTION EXECUTORS
# ============================================================
#
# IMPORTANT:
#
# These executors intentionally remain thin.
#
# The automation engine decides:
#
#   - which action should run
#   - whether the user is authorized
#   - whether school scope is valid
#   - whether the job is idempotent
#
# The domain modules remain responsible for actual
# business operations.
#
# This prevents Automation from becoming a second backend.
# ============================================================


def execute_notify(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Queue/prepare a notification.

    Actual delivery should eventually be handled by the
    notification service/provider.
    """
    payload = _payload(context)

    message = _string(
        payload,
        "message",
    )

    if not message:
        message = (
            "An automated Elimu notification "
            "has been generated."
        )

    recipient = payload.get("recipient")
    recipients = payload.get("recipients")

    if recipient is None and recipients is None:
        raise ValueError(
            "notify requires recipient or recipients."
        )

    return ActionResult(
        status="accepted",
        action="notify",
        message="Notification accepted for delivery.",
        data={
            "school_id": str(school_id),
            "recipient": recipient,
            "recipients": recipients,
            "message": message,
            "channel": payload.get(
                "channel",
                "in_app",
            ),
        },
    )


def execute_create_report(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Request report generation.

    The actual report engine remains in the reports module.
    """
    payload = _payload(context)

    report_type = _string(
        payload,
        "report_type",
        "school_summary",
    )

    return ActionResult(
        status="accepted",
        action="create_report",
        message="Report generation requested.",
        data={
            "school_id": str(school_id),
            "report_type": report_type,
            "parameters": payload.get(
                "parameters",
                {},
            ),
        },
    )


def execute_publish_report(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Request report publication.

    Publication remains subject to the report module's own
    authorization and lifecycle rules.
    """
    payload = _payload(context)

    report_id = _required(
        payload,
        "report_id",
    )

    return ActionResult(
        status="accepted",
        action="publish_report",
        message="Report publication requested.",
        data={
            "school_id": str(school_id),
            "report_id": str(report_id),
        },
    )


def execute_send_reminder(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Request an automated reminder.
    """
    payload = _payload(context)

    recipient = (
        payload.get("recipient")
        or payload.get("student_id")
        or payload.get("teacher_id")
        or payload.get("parent_id")
    )

    if not recipient:
        raise ValueError(
            "send_reminder requires a recipient or target ID."
        )

    message = _string(
        payload,
        "message",
        "This is an automated reminder from Elimu.",
    )

    return ActionResult(
        status="accepted",
        action="send_reminder",
        message="Reminder accepted for delivery.",
        data={
            "school_id": str(school_id),
            "recipient": str(recipient),
            "message": message,
            "channel": payload.get(
                "channel",
                "in_app",
            ),
        },
    )


def execute_flag_student(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Create a student-risk/attention flag request.

    Actual persistence belongs to the student/domain layer.
    """
    payload = _payload(context)

    student_id = _required(
        payload,
        "student_id",
    )

    reason = _string(
        payload,
        "reason",
        "Automated Elimu flag.",
    )

    severity = _string(
        payload,
        "severity",
        "medium",
    ).lower()

    if severity not in {
        "low",
        "medium",
        "high",
        "critical",
    }:
        raise ValueError(
            "Invalid student flag severity."
        )

    return ActionResult(
        status="accepted",
        action="flag_student",
        message="Student flag request accepted.",
        data={
            "school_id": str(school_id),
            "student_id": str(student_id),
            "reason": reason,
            "severity": severity,
        },
    )


def execute_flag_class(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Create a class-risk/attention flag request.
    """
    payload = _payload(context)

    class_id = _required(
        payload,
        "class_id",
    )

    reason = _string(
        payload,
        "reason",
        "Automated Elimu class flag.",
    )

    severity = _string(
        payload,
        "severity",
        "medium",
    ).lower()

    if severity not in {
        "low",
        "medium",
        "high",
        "critical",
    }:
        raise ValueError(
            "Invalid class flag severity."
        )

    return ActionResult(
        status="accepted",
        action="flag_class",
        message="Class flag request accepted.",
        data={
            "school_id": str(school_id),
            "class_id": str(class_id),
            "reason": reason,
            "severity": severity,
        },
    )


def execute_generate_timetable(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Request timetable generation.

    Automation may request generation, but publication must
    remain an explicit controlled operation.
    """
    payload = _payload(context)

    term_id = payload.get("term_id")
    academic_year = payload.get(
        "academic_year"
    )

    return ActionResult(
        status="accepted",
        action="generate_timetable",
        message="Timetable generation requested.",
        data={
            "school_id": str(school_id),
            "term_id": term_id,
            "academic_year": academic_year,
            "publish": False,
            "parameters": payload.get(
                "parameters",
                {},
            ),
        },
    )


def execute_run_sync(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Request a school synchronization operation.

    The Sync engine remains authoritative for actual
    synchronization.
    """
    payload = _payload(context)

    connection_id = payload.get(
        "connection_id"
    )

    device_id = payload.get(
        "device_id"
    )

    return ActionResult(
        status="accepted",
        action="run_sync",
        message="Synchronization request accepted.",
        data={
            "school_id": str(school_id),
            "connection_id": connection_id,
            "device_id": device_id,
            "direction": payload.get(
                "direction",
                "bidirectional",
            ),
            "entity_types": payload.get(
                "entity_types",
                [],
            ),
        },
    )


def execute_retry_sync(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Request a retry of a failed synchronization job.
    """
    payload = _payload(context)

    job_id = _required(
        payload,
        "job_id",
    )

    return ActionResult(
        status="accepted",
        action="retry_sync",
        message="Synchronization retry requested.",
        data={
            "school_id": str(school_id),
            "job_id": str(job_id),
        },
    )


def execute_create_alert(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Create a school operational alert request.
    """
    payload = _payload(context)

    title = _string(
        payload,
        "title",
    )

    if not title:
        raise ValueError(
            "create_alert requires title."
        )

    message = _string(
        payload,
        "message",
    )

    severity = _string(
        payload,
        "severity",
        "info",
    ).lower()

    if severity not in {
        "info",
        "warning",
        "critical",
    }:
        raise ValueError(
            "Invalid alert severity."
        )

    return ActionResult(
        status="accepted",
        action="create_alert",
        message="School alert accepted.",
        data={
            "school_id": str(school_id),
            "title": title,
            "message": message,
            "severity": severity,
        },
    )


def execute_request_ai_analysis(
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    **_: Any,
) -> ActionResult:
    """
    Request RevelaAI analysis.

    RevelaAI is an intelligence layer, not the authoritative
    Elimu database or deterministic transaction engine.
    """
    payload = _payload(context)

    analysis_type = _string(
        payload,
        "analysis_type",
        "school_insights",
    )

    subject = payload.get(
        "subject"
    )

    data = payload.get(
        "data",
        {},
    )

    return ActionResult(
        status="accepted",
        action="request_ai_analysis",
        message="AI analysis request accepted.",
        data={
            "school_id": str(school_id),
            "analysis_type": analysis_type,
            "subject": subject,
            "data": data,
            "provider": "revelaai",
        },
    )


# ============================================================
# ACTION REGISTRY
# ============================================================

ACTION_REGISTRY: dict[str, ActionDefinition] = {
    "notify": ActionDefinition(
        name="notify",
        description="Send an automated notification.",
        permission="automation.manage",
        scope="school",
        executor=execute_notify,
    ),

    "create_report": ActionDefinition(
        name="create_report",
        description="Generate an Elimu report.",
        permission="automation.manage",
        scope="school",
        executor=execute_create_report,
    ),

    "publish_report": ActionDefinition(
        name="publish_report",
        description="Publish an existing report.",
        permission="automation.manage",
        scope="school",
        executor=execute_publish_report,
    ),

    "send_reminder": ActionDefinition(
        name="send_reminder",
        description="Send an automated reminder.",
        permission="automation.manage",
        scope="school",
        executor=execute_send_reminder,
    ),

    "flag_student": ActionDefinition(
        name="flag_student",
        description="Flag a student for attention.",
        permission="automation.manage",
        scope="student",
        executor=execute_flag_student,
    ),

    "flag_class": ActionDefinition(
        name="flag_class",
        description="Flag a class for attention.",
        permission="automation.manage",
        scope="class",
        executor=execute_flag_class,
    ),

    "generate_timetable": ActionDefinition(
        name="generate_timetable",
        description="Request timetable generation.",
        permission="automation.manage",
        scope="school",
        executor=execute_generate_timetable,
    ),

    "run_sync": ActionDefinition(
        name="run_sync",
        description="Request a school synchronization.",
        permission="sync.import",
        scope="school",
        executor=execute_run_sync,
    ),

    "retry_sync": ActionDefinition(
        name="retry_sync",
        description="Retry a failed synchronization job.",
        permission="sync.import",
        scope="school",
        executor=execute_retry_sync,
    ),

    "create_alert": ActionDefinition(
        name="create_alert",
        description="Create an operational school alert.",
        permission="automation.manage",
        scope="school",
        executor=execute_create_alert,
    ),

    "request_ai_analysis": ActionDefinition(
        name="request_ai_analysis",
        description="Request intelligence analysis from RevelaAI.",
        permission="automation.manage",
        scope="school",
        executor=execute_request_ai_analysis,
    ),
}


# ============================================================
# REGISTRY API
# ============================================================

def get_action(
    action: str,
) -> ActionDefinition:
    """
    Retrieve an action definition.
    """
    normalized = str(
        action or ""
    ).strip().lower()

    definition = ACTION_REGISTRY.get(
        normalized
    )

    if not definition:
        raise ValueError(
            f"Unsupported automation action: {normalized}"
        )

    return definition


def action_exists(
    action: str,
) -> bool:
    normalized = str(
        action or ""
    ).strip().lower()

    return normalized in ACTION_REGISTRY


def list_actions() -> list[dict[str, Any]]:
    """
    Return the public action catalog.

    Executors themselves are not exposed.
    """
    return [
        {
            "name": definition.name,
            "description": definition.description,
            "permission": definition.permission,
            "scope": definition.scope,
        }
        for definition in ACTION_REGISTRY.values()
    ]


# ============================================================
# ACTION VALIDATION
# ============================================================

def validate_action(
    action: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validate an action before execution.

    Context-specific required fields are validated by the
    executor.
    """
    definition = get_action(action)

    payload = _payload(context)

    # Basic target-scope validation.
    if definition.scope == "student":
        if not payload.get("student_id"):
            raise ValueError(
                "This action requires student_id."
            )

    if definition.scope == "class":
        if not payload.get("class_id"):
            raise ValueError(
                "This action requires class_id."
            )

    return {
        "valid": True,
        "action": definition.name,
        "permission": definition.permission,
        "scope": definition.scope,
    }


# ============================================================
# EXECUTION ENTRY POINT
# ============================================================

def execute_action(
    action: str,
    *,
    school_id: str,
    context: dict[str, Any] | None = None,
    user_id: str | None = None,
    membership: dict | None = None,
) -> dict[str, Any]:
    """
    Execute a registered automation action.

    Authorization is intentionally performed here as a second
    safety boundary.

    The caller may already have passed automation.manage, but
    actions such as run_sync have additional permission
    requirements.
    """
    definition = get_action(
        action
    )

    validate_action(
        definition.name,
        context,
    )

    if membership is not None:
        permissions = membership.get(
            "permissions",
            [],
        )

        # Owner-style memberships may expose a wildcard.
        is_owner = (
            membership.get("role") == "owner"
            or "*" in permissions
            or "all" in permissions
        )

        if not is_owner:
            if (
                definition.permission
                not in permissions
            ):
                raise PermissionError(
                    "The current Elimu membership does not "
                    f"have permission: {definition.permission}"
                )

    result = definition.executor(
        school_id=str(school_id),
        context=context or {},
        user_id=user_id,
        membership=membership,
    )

    if not isinstance(
        result,
        ActionResult,
    ):
        raise TypeError(
            f"Automation action '{definition.name}' "
            "returned an invalid result."
        )

    return result.as_dict()


# ============================================================
# ACTION HEALTH
# ============================================================

def registry_status() -> dict[str, Any]:
    """
    Return action registry health information.
    """
    actions = list_actions()

    return {
        "healthy": bool(actions),
        "count": len(actions),
        "actions": actions,
    }