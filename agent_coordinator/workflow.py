"""Backwards-compatibility shim — prefers structured workflow state when present.

New code should use WorkflowRouter directly.
"""

import json
from pathlib import Path

from agent_coordinator.application.router import WorkflowRouter
from agent_coordinator.domain.models import HandoffMessage, HandoffStatus
from agent_coordinator.handoff_parser import extract_latest

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
    handoff_path = Path(handoff_file_path)
    state_path = handoff_path.parent / ".agent-coordinator" / "workflow_state.json"
    tasks_path = handoff_path.parent / "tasks.json"
    if state_path.exists() and tasks_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            tasks = json.loads(tasks_path.read_text(encoding="utf-8")).get("tasks", [])
            by_id = {task["id"]: task for task in tasks}
            pending_id = state.get("pending_task_id", "")
            pending_actor = state.get("pending_actor", "")
            pending_task = by_id.get(pending_id, {})
            return {
                "valid": True,
                "next_actor": pending_actor or "none",
                "status": pending_task.get("status", state.get("pending_status", "unknown")),
                "task_id": pending_id or "unknown",
                "is_complete": not pending_actor and all(task.get("status") == "done" for task in tasks),
                "is_blocked": pending_task.get("status") in {"blocked", "needs_human"},
                "needs_human": pending_actor == "human",
                "errors": [],
            }
        except Exception:
            pass
    with open(handoff_file_path, encoding="utf-8") as f:
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

    _router.route(message)
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
