#!/usr/bin/env python3
"""
Task creation helper - makes it easy for humans to create tasks or specifications.

Usage:
    python -m agent_coordinator.helpers.create_task --workspace /path/to/workspace
    python -m agent_coordinator.helpers.create_spec --workspace /path/to/workspace
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def create_task_interactive(_workspace: Path, use_editor: bool = True) -> dict[str, Any]:
    """Interactively create a task."""
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).isoformat()

    if use_editor:
        from agent_coordinator.infrastructure.editor import edit_task

        print("\nOpening text editor for task creation...")
        print(f"(Using: {os.environ.get('EDITOR', 'vi')})")
        print("Save and close the editor when done.\n")

        task_data = edit_task()

        if not task_data["id"] or not task_data["title"]:
            print("ERROR: Task ID and title are required")
            sys.exit(1)

        return {
            "id": task_data["id"],
            "title": task_data["title"],
            "description": task_data["description"],
            "status": "planned",
            "acceptance_criteria": task_data["acceptance_criteria"],
            "dependencies": task_data["dependencies"],
            "assigned_to": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    # Fallback to enhanced interactive method
    from agent_coordinator.infrastructure.enhanced_input import Colors, enhanced_input

    print("\n=== Create New Task ===\n")

    task_id = enhanced_input(Colors.prompt("Task ID (e.g., task-001): ")).strip()
    if not task_id:
        print(Colors.error("ERROR: Task ID is required"))
        sys.exit(1)

    title = enhanced_input(Colors.prompt("Title: ")).strip()
    if not title:
        print(Colors.error("ERROR: Title is required"))
        sys.exit(1)

    description = enhanced_input(Colors.prompt("Description: ")).strip()

    print(Colors.info("\nAcceptance criteria (one per line, empty line to finish):"))
    acceptance = []
    while True:
        line = enhanced_input(Colors.prompt("  - ")).strip()
        if not line:
            break
        acceptance.append(line)

    print(Colors.info("\nDependencies (task IDs, one per line, empty line to finish):"))
    dependencies = []
    while True:
        line = enhanced_input(Colors.prompt("  - ")).strip()
        if not line:
            break
        dependencies.append(line)

    return {
        "id": task_id,
        "title": title,
        "description": description,
        "status": "planned",
        "acceptance_criteria": acceptance,
        "dependencies": dependencies,
        "assigned_to": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def add_task_to_file(workspace: Path, task: dict[str, Any]) -> None:
    """Add task to tasks.json file."""
    tasks_file = workspace / "tasks.json"

    if tasks_file.exists():
        with open(tasks_file) as f:
            data = json.load(f)
        tasks = data.get("tasks", [])
    else:
        tasks = []

    # Check for duplicate ID
    if any(t["id"] == task["id"] for t in tasks):
        print(f"ERROR:  Task with ID '{task['id']}' already exists")
        sys.exit(1)

    tasks.append(task)

    # Write back
    with open(tasks_file, "w") as f:
        json.dump({"tasks": tasks}, f, indent=4)

    print(f"\nSUCCESS:  Task '{task['id']}' added to {tasks_file}")


def create_specification_interactive(_workspace: Path, use_editor: bool = True) -> str:
    """Interactively create a specification."""
    if use_editor:
        from agent_coordinator.infrastructure.editor import edit_specification

        print("\nOpening text editor for specification...")
        print(f"(Using: {os.environ.get('EDITOR', 'vi')})")
        print("Save and close the editor when done.\n")

        spec_data = edit_specification()

        if not spec_data["title"]:
            print("ERROR: Title is required")
            sys.exit(1)

        # Build specification from parsed data
        spec = f"""# {spec_data["title"]}

## Description

{spec_data["description"] or "(No description provided)"}

## Requirements

"""
        for req in spec_data["requirements"]:
            spec += f"- {req}\n"

        if not spec_data["requirements"]:
            spec += "- (No requirements specified)\n"

        if spec_data["constraints"]:
            spec += "\n## Constraints\n\n"
            for constraint in spec_data["constraints"]:
                spec += f"- {constraint}\n"

        spec += """
## Implementation Notes

(To be filled in during planning)

## Acceptance Criteria

(To be defined by architect)
"""
        return spec

    # Fallback to enhanced interactive method
    from agent_coordinator.infrastructure.enhanced_input import Colors, enhanced_input, enhanced_multiline

    print("\n=== Create New Specification ===\n")

    title = enhanced_input(Colors.prompt("Title: ")).strip()
    if not title:
        print(Colors.error("ERROR: Title is required"))
        sys.exit(1)

    print(Colors.info("\nDescription (multiple lines, empty line to finish):"))
    description = enhanced_multiline("", Colors.prompt(""))

    print(Colors.info("\nRequirements (one per line, empty line to finish):"))
    requirements = []
    while True:
        line = enhanced_input(Colors.prompt("  - ")).strip()
        if not line:
            break
        requirements.append(line)

    print(Colors.info("\nConstraints (one per line, empty line to finish):"))
    constraints = []
    while True:
        line = enhanced_input(Colors.prompt("  - ")).strip()
        if not line:
            break
        constraints.append(line)

    # Build specification document
    spec = f"""# {title}

## Description

{description}

## Requirements

"""
    for req in requirements:
        spec += f"- {req}\n"

    if constraints:
        spec += "\n## Constraints\n\n"
        for constraint in constraints:
            spec += f"- {constraint}\n"

    spec += """
## Implementation Notes

(To be filled in during planning)

## Acceptance Criteria

(To be defined by architect)
"""

    return spec


def write_specification(workspace: Path, spec: str, filename: str = "SPECIFICATION.md") -> None:
    """Write specification to file."""
    spec_file = workspace / filename

    if spec_file.exists():
        response = input(f"\n⚠  {filename} already exists. Overwrite? (y/N): ")
        if response.lower() != "y":
            print("Cancelled.")
            sys.exit(0)

    spec_file.write_text(spec)
    print(f"\nSUCCESS:  Specification written to {spec_file}")


def create_handoff_template(workspace: Path, task_id: str, title: str) -> None:
    """Create initial handoff for a new task or spec."""
    handoff_file = workspace / "handoff.md"

    template = f"""---HANDOFF---
ROLE: architect
STATUS: continue
NEXT: architect
TASK_ID: {task_id}
TITLE: {title}
SUMMARY: Read the specification or task details and create an implementation plan. Decompose into concrete tasks and begin coordinating work.
ACCEPTANCE:
- Specification/requirements understood
- Implementation plan created
- Tasks decomposed with clear acceptance criteria
CONSTRAINTS:
- None yet
FILES_TO_TOUCH:
- handoff.md
- plan.md (if creating)
- tasks.json (if creating tasks)
CHANGED_FILES:
- None
VALIDATION:
- None
BLOCKERS:
- None
---END---
"""

    handoff_file.write_text(template)
    print(f"\nSUCCESS:  Initial handoff created at {handoff_file}")


def main_task() -> None:
    """Main entry point for task creation."""
    parser = argparse.ArgumentParser(description="Create a new task interactively")
    parser.add_argument("--workspace", type=Path, required=True, help="Workspace directory")
    parser.add_argument("--no-handoff", action="store_true", help="Don't create handoff.md")
    parser.add_argument("--no-editor", action="store_true", help="Use prompts instead of text editor")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    task = create_task_interactive(workspace, use_editor=not args.no_editor)
    add_task_to_file(workspace, task)

    if not args.no_handoff:
        create_handoff_template(workspace, task["id"], task["title"])

    print("\nCOMPLETE: Task creation complete!")
    print("\nNext steps:")
    print(f"  1. Review the task in {workspace}/tasks.json")
    if not args.no_handoff:
        print(f"  2. Run: agent-coordinator --workspace {workspace}")
    else:
        print("  2. Create or update handoff.md")
        print(f"  3. Run: agent-coordinator --workspace {workspace}")


def main_spec() -> None:
    """Main entry point for specification creation."""
    parser = argparse.ArgumentParser(description="Create a new specification interactively")
    parser.add_argument("--workspace", type=Path, required=True, help="Workspace directory")
    parser.add_argument("--filename", default="SPECIFICATION.md", help="Specification filename")
    parser.add_argument("--no-handoff", action="store_true", help="Don't create handoff.md")
    parser.add_argument("--no-editor", action="store_true", help="Use prompts instead of text editor")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    spec = create_specification_interactive(workspace, use_editor=not args.no_editor)
    write_specification(workspace, spec, args.filename)

    if not args.no_handoff:
        # Extract title from spec
        lines = spec.split("\n")
        title = lines[0].replace("#", "").strip() if lines else "New Specification"
        create_handoff_template(workspace, "spec-001", title)

    print("\nCOMPLETE: Specification creation complete!")
    print("\nNext steps:")
    print(f"  1. Review the specification in {workspace}/{args.filename}")
    if not args.no_handoff:
        print(f"  2. Run: agent-coordinator --workspace {workspace}")
    else:
        print("  2. Create handoff.md")
        print(f"  3. Run: agent-coordinator --workspace {workspace}")


if __name__ == "__main__":
    if "create_task" in sys.argv[0]:
        main_task()
    elif "create_spec" in sys.argv[0]:
        main_spec()
    else:
        print("Usage: python -m agent_coordinator.helpers.create_task")
        print("   or: python -m agent_coordinator.helpers.create_spec")
        sys.exit(1)
