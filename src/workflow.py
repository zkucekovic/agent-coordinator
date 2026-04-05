"""Workflow helper functions for the two-agent coordination system."""

from src.models import HandoffMessage, HandoffStatus, NextActor
from src.handoff_parser import extract_latest


def get_next_actor(message: HandoffMessage) -> NextActor:
    """Return the next actor declared in the handoff message."""
    return message.next


def is_plan_complete(message: HandoffMessage) -> bool:
    """Return True if the handoff message declares plan_complete status."""
    return message.status == HandoffStatus.PLAN_COMPLETE


def is_human_escalation(message: HandoffMessage) -> bool:
    """Return True if the next actor is human (escalation required)."""
    return message.next == NextActor.HUMAN


def is_blocked(message: HandoffMessage) -> bool:
    """Return True if the workflow is blocked or needs human intervention."""
    return message.status in (HandoffStatus.BLOCKED, HandoffStatus.NEEDS_HUMAN)


def get_workflow_state(handoff_file_path: str) -> dict:
    """
    Read a handoff file and return the current workflow state as a dict.

    Returns:
        {
            "valid": bool,
            "next_actor": str,   # NEXT field value or "unknown"
            "status": str,       # STATUS field value or "unknown"
            "task_id": str,      # TASK_ID value or "unknown"
            "is_complete": bool, # True if plan_complete
            "is_blocked": bool,  # True if blocked or needs_human
            "needs_human": bool, # True if next_actor is human
            "errors": list[str], # parse errors if any
        }
    """
    with open(handoff_file_path, 'r', encoding='utf-8') as f:
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

    return {
        "valid": True,
        "next_actor": message.next.value,
        "status": message.status.value,
        "task_id": message.task_id,
        "is_complete": is_plan_complete(message),
        "is_blocked": is_blocked(message),
        "needs_human": is_human_escalation(message),
        "errors": [],
    }
