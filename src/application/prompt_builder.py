"""Prompt builder — constructs the text message sent to an agent for one turn.

Single responsibility: produce a well-formed prompt string.
No I/O, no subprocess calls.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.models import Task


class PromptBuilder:
    """
    Builds the turn prompt delivered to an agent via OpenCode.

    Separating this from the coordinator keeps prompt logic independently
    testable and swappable (e.g. to support different prompt strategies).

    Args:
        coordinator_dir: Absolute path to the coordinator's installation
            directory. Prompt files are resolved relative to this directory
            first, then relative to the workspace as a fallback.
    """

    def __init__(self, coordinator_dir: Path | None = None) -> None:
        self._coordinator_dir = coordinator_dir

    def build(
        self,
        role: str,
        workspace: Path,
        handoff_content: str,
        agent_cfg: dict,
        next_task: Task | None = None,
        first_turn: bool = False,
    ) -> str:
        """
        Build and return the full prompt string for one agent turn.

        Args:
            role:             Agent role name (e.g. "architect", "qa").
            workspace:        Absolute path to the project workspace directory.
            handoff_content:  Full text of handoff.md at the time of this turn.
            agent_cfg:        Agent config dict (from agents.json entry).
            next_task:        The next ready task, injected for the architect's
                              awareness. None if no task is auto-selected.
            first_turn:       True on the agent's first ever turn — includes the
                              full role prompt and shared rules preamble.
        """
        role_prompt = self._load_role_prompt(role, workspace, agent_cfg)
        shared_rules = self._load_shared_rules(workspace)
        task_hint = f"(current task: {next_task.id})" if next_task else ""
        task_context = self._task_context(next_task)

        project_rules = self._load_project_rules(workspace)
        project_docs = self._load_project_docs(workspace) if first_turn else ""

        if first_turn:
            project_section = (
                f"\n\n---\n\n## Project Rules (from AGENTS.md)\n\n{project_rules}\n"
                if project_rules else ""
            )
            docs_section = (
                f"\n\n---\n\n{project_docs}\n"
                if project_docs else ""
            )
            preamble = (
                f"You are the **{role.upper()} agent** for this project. "
                f"Your working directory is `{workspace}`.\n\n"
                f"{role_prompt}{project_section}{docs_section}\n\n---\n\n{shared_rules}\n\n---\n"
            )
        else:
            preamble = (
                f"You are the **{role.upper()} agent**. "
                f"Your working directory is `{workspace}`.\n\n"
            )

        return (
            f"{preamble}\n"
            f"## Current state of handoff.md {task_hint}\n\n"
            f"```\n{handoff_content}\n```\n\n"
            f"{task_context}"
            f"---\n\n"
            f"Read the latest `---HANDOFF---` block above. "
            f"`NEXT: {role}` — it is your turn.\n\n"
            f"Take your action now:\n"
            f"- Work in `{workspace}` (read and write files as needed)\n"
            f"- Append your handoff entry to `{workspace}/handoff.md`\n"
            f"- End with a valid `---HANDOFF---` … `---END---` block\n"
        )

    def _resolve_file(self, relative_path: str, workspace: Path) -> Path | None:
        """Resolve a file relative to coordinator_dir first, then workspace."""
        if self._coordinator_dir:
            candidate = self._coordinator_dir / relative_path
            if candidate.exists():
                return candidate
        candidate = workspace / relative_path
        if candidate.exists():
            return candidate
        return None

    def _load_role_prompt(self, role: str, workspace: Path, agent_cfg: dict) -> str:
        prompt_rel = agent_cfg.get("prompt_file", f"prompts/{role}.md")
        resolved = self._resolve_file(prompt_rel, workspace)
        if resolved:
            return resolved.read_text()
        return (
            f"You are the **{role.upper()} agent**. "
            f"Follow the shared rules and handoff protocol."
        )

    def _load_shared_rules(self, workspace: Path) -> str:
        resolved = self._resolve_file("prompts/shared_rules.md", workspace)
        return resolved.read_text() if resolved else ""

    def _load_project_rules(self, workspace: Path) -> str:
        """Load AGENTS.md or agents.md from the workspace if present."""
        for name in ("AGENTS.md", "agents.md"):
            path = workspace / name
            if path.exists():
                return path.read_text()
        return ""

    def _load_project_docs(self, workspace: Path) -> str:
        """Load specification and plan files from the workspace if present.

        Looks for common naming conventions: SPECIFICATION.md, spec.md,
        IMPLEMENTATION_PLAN.md, plan.md, etc. Returns concatenated content
        with section headers.
        """
        spec_names = (
            "SPECIFICATION.md", "specification.md", "spec.md", "SPEC.md",
            "PRD.md", "prd.md", "requirements.md", "REQUIREMENTS.md",
        )
        plan_names = (
            "IMPLEMENTATION_PLAN.md", "implementation_plan.md",
            "plan.md", "PLAN.md",
        )

        sections: list[str] = []

        for name in spec_names:
            path = workspace / name
            if path.exists():
                sections.append(
                    f"## Project Specification (from {name})\n\n"
                    f"{path.read_text().strip()}"
                )
                break

        for name in plan_names:
            path = workspace / name
            if path.exists():
                sections.append(
                    f"## Implementation Plan (from {name})\n\n"
                    f"{path.read_text().strip()}"
                )
                break

        return "\n\n---\n\n".join(sections)

    @staticmethod
    def _task_context(task: Task | None) -> str:
        if task is None:
            return ""
        rework_note = (
            f" (rework #{task.rework_count})" if task.rework_count > 0 else ""
        )
        return (
            f"### Next ready task{rework_note}\n\n"
            f"- **ID**: {task.id}\n"
            f"- **Title**: {task.title}\n"
            f"- **Status**: {task.status.value}\n\n"
        )
