"""Backwards-compatibility shim — delegates to src.application.router and src.infrastructure.

New code should use WorkflowRouter directly.
"""

from src.domain.models import HandoffMessage, HandoffStatus
from src.application.router import WorkflowRouter
from src.handoff_parser import extract_latest

_router = WorkflowRouter()


def get_next_actor(message: HandoffMessage) -> str:
    """Return the next actor declared in the handoff message."""
    return message.next


def is_plan_complete(message: HandoffMessage) -> bool:
    return message.status == HandoffStatus.PLAN_COMPLETE


def is_human_escalation(message: HandoffMessage) -> bool:
    return message.next == "human"


def is_blocked(message: HandoffMessage) -> bool:
    return message.status in (HandoffStatus.BLOCKED, HandoffStatus.NEEDS_HUMAN)


def get_workflow_state(handoff_file_path: str) -> dict:
    with open(handoff_file_path, "r", encoding="utf-8") as f:
        content = f.read()

    message, errors = extract_latest(content)
    if message is None:
        return {
            "valid": False,
            "next_actor": "unknown",
            "status": "unknown",
            "task_id": "unknown",
            "is_complete": False,
            "is_blocked": False,
            "needs_human": False,
            "errors": errors,
        }

    decision = _router.route(message)
    return {
        "valid": True,
        "next_actor": message.next,
        "status": message.status.value,
        "task_id": message.task_id,
        "is_complete": is_plan_complete(message),
        "is_blocked": is_blocked(message),
        "needs_human": is_human_escalation(message),
        "errors": [],
    }

