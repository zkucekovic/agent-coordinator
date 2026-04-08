"""Interactive editor integration for human-friendly text editing.

Provides editor-based input for specifications, handoff tasks, and other multi-line content.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def get_editor() -> str:
    """Get the user's preferred text editor."""
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"


def edit_text(initial_text: str = "", comment_lines: list[str] | None = None) -> str:
    """
    Open the user's text editor for multi-line input.

    Args:
        initial_text: Pre-populated text in the editor
        comment_lines: Optional comment lines to show at top (will be stripped from result)

    Returns:
        The edited text with comment lines removed
    """
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".md", delete=False) as tf:
        temp_path = Path(tf.name)

        # Write comment lines
        if comment_lines:
            for line in comment_lines:
                tf.write(f"# {line}\n")
            if initial_text:
                tf.write("\n")

        # Write initial content
        tf.write(initial_text)
        tf.flush()

        # Get editor
        editor = get_editor()

        try:
            # Open editor
            subprocess.run([editor, str(temp_path)], check=True)

            # Read result
            content = temp_path.read_text()

            # Remove comment lines
            lines = content.split("\n")
            result_lines = [line for line in lines if not line.startswith("#")]

            return "\n".join(result_lines).strip()

        finally:
            # Cleanup
            temp_path.unlink(missing_ok=True)


def edit_specification() -> dict[str, str | list[str]]:
    """
    Edit a specification in the user's text editor.

    Returns:
        Dict with 'title', 'description', 'requirements', 'constraints'
    """
    template = """Specification Title Here

## Description

Write your description here...
Multiple lines are fine.

## Requirements

- Requirement 1
- Requirement 2
- Requirement 3

## Constraints

- Constraint 1
- Constraint 2
"""

    comment_lines = [
        "Edit the specification below",
        "Lines starting with # will be ignored",
        "Save and close the editor when done",
        "",
    ]

    content = edit_text(template, comment_lines)

    # Parse the result
    lines = content.split("\n")
    title = ""
    requirements: list[str] = []
    constraints: list[str] = []

    # First non-empty line is title
    for line in lines:
        if line.strip():
            title = line.strip().replace("#", "").strip()
            break

    # Parse sections
    current_section = None
    description_lines: list[str] = []

    for line in lines[1:]:
        line_stripped = line.strip()

        if line_stripped.startswith("## Description"):
            current_section = "description"
        elif line_stripped.startswith("## Requirements"):
            current_section = "requirements"
        elif line_stripped.startswith("## Constraints"):
            current_section = "constraints"
        elif line_stripped.startswith("##"):
            current_section = None
        elif current_section == "description" and line_stripped:
            description_lines.append(line_stripped)
        elif current_section == "requirements" and line_stripped.startswith("-"):
            requirements.append(line_stripped[1:].strip())
        elif current_section == "constraints" and line_stripped.startswith("-"):
            constraints.append(line_stripped[1:].strip())

    return {
        "title": title,
        "description": "\n".join(description_lines),
        "requirements": requirements,
        "constraints": constraints,
    }


def edit_task() -> dict[str, str | list[str]]:
    """
    Edit a task in the user's text editor.

    Returns:
        Dict with task fields
    """
    template = """task-001: Task Title Here

Description of the task...
Can be multiple lines.

## Acceptance Criteria

- Criterion 1
- Criterion 2
- Criterion 3

## Dependencies

- task-000
"""

    comment_lines = [
        "Edit the task below",
        "First line format: task-id: Task Title",
        "Lines starting with # will be ignored",
        "Save and close when done",
        "",
    ]

    content = edit_text(template, comment_lines)

    lines = content.split("\n")
    task_id = ""
    title = ""
    acceptance_criteria: list[str] = []
    dependencies: list[str] = []

    # First line: task-id: title
    if lines:
        first_line = lines[0].strip()
        if ":" in first_line:
            parts = first_line.split(":", 1)
            task_id = parts[0].strip()
            title = parts[1].strip()

    # Parse sections
    current_section = None
    description_lines: list[str] = []

    for line in lines[1:]:
        line_stripped = line.strip()

        if line_stripped.startswith("## Acceptance"):
            current_section = "acceptance"
        elif line_stripped.startswith("## Dependencies"):
            current_section = "dependencies"
        elif line_stripped.startswith("##"):
            current_section = None
        elif current_section is None and line_stripped:
            description_lines.append(line_stripped)
        elif current_section == "acceptance" and line_stripped.startswith("-"):
            acceptance_criteria.append(line_stripped[1:].strip())
        elif current_section == "dependencies" and line_stripped.startswith("-"):
            dependencies.append(line_stripped[1:].strip())

    return {
        "id": task_id,
        "title": title,
        "description": "\n".join(description_lines).strip(),
        "acceptance_criteria": acceptance_criteria,
        "dependencies": dependencies,
    }


def edit_handoff_message(current_handoff: str = "") -> str:
    """
    Edit a handoff message or update in the text editor.

    Args:
        current_handoff: Current handoff content to show for context

    Returns:
        The message/update to add to handoff
    """
    template = """Write your message or guidance here...

You can provide:
- Additional context for the agent
- Corrections or clarifications
- Specific instructions
- Questions or concerns
"""

    comment_lines = [
        "Edit your handoff message below",
        "This will be added to handoff.md",
        "Lines starting with # will be ignored",
        "",
    ]

    if current_handoff:
        comment_lines.extend(
            [
                "Current handoff context:",
                "=" * 50,
            ]
        )
        # Add current handoff as comments
        for line in current_handoff.split("\n")[:20]:
            comment_lines.append(line[:70])
        comment_lines.append("=" * 50)
        comment_lines.append("")

    return edit_text(template, comment_lines)
