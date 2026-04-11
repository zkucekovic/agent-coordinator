"""import_plan.py — import an existing specification or implementation plan into a workspace.

Copies the document to the workspace with the canonical filename, extracts
tasks from plans into tasks.json, and writes an initial handoff.md that
directs the architect to start working.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_coordinator.application.task_classifier import infer_task_mode
from agent_coordinator.domain.models import TaskMode

# ── Document type detection ────────────────────────────────────────────────────

_SPEC_KEYWORDS = re.compile(
    r"\b(requirement|specification|constraint|acceptance.criteria|overview|prd|use.case)\b",
    re.IGNORECASE,
)
_PLAN_KEYWORDS = re.compile(
    r"\b(phase|task-\d+|implementation.plan|milestone|step \d+|sprint)\b",
    re.IGNORECASE,
)


def detect_doc_type(content: str) -> str:
    """Return 'plan', 'spec', or 'unknown' based on document content."""
    spec_hits = len(_SPEC_KEYWORDS.findall(content))
    plan_hits = len(_PLAN_KEYWORDS.findall(content))

    # Boost plan score: if the parser can extract tasks, it's structured as a plan
    if extract_tasks_from_plan(content):
        plan_hits += 3

    if plan_hits > spec_hits:
        return "plan"
    if spec_hits > 0:
        return "spec"
    return "unknown"


# ── Markdown extraction helpers ────────────────────────────────────────────────


def extract_title(content: str) -> str:
    """Return the first H1 heading, or 'Imported Document'."""
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return "Imported Document"


def extract_tasks_from_plan(content: str) -> list[dict[str, Any]]:
    """
    Extract tasks from a markdown plan document.

    Supports three common formats:
    1. Phase headers with task IDs:
       ### Phase 1 — Title (task-001)
    2. Explicit task headings:
       ### task-001: Title
       ## task-001 — Title
    3. Numbered phases without IDs (auto-assigned task-NNN):
       ### Phase 1: Title
       ### 1. Title
    """
    tasks: list[dict[str, Any]] = []
    lines = content.splitlines()
    ts = datetime.now(timezone.utc).isoformat()

    # Pattern 1: any heading containing (task-NNN) or task-NNN
    explicit_id_re = re.compile(
        r"^#{1,4}\s+.*?(?:\(?(task-\d+)\)?)",
        re.IGNORECASE,
    )
    # Pattern 2: heading that is itself a task-NNN title
    task_heading_re = re.compile(
        r"^#{1,4}\s+(task-\d+)[:\s—\-]+(.+)",
        re.IGNORECASE,
    )
    # Pattern 3: numbered phase / step heading (fallback)
    numbered_heading_re = re.compile(
        r"^#{1,4}\s+(?:phase|step|sprint|milestone|part)\s*(\d+)[:\s—\-]+(.+)",
        re.IGNORECASE,
    )
    # Pattern 4: simple numbered heading  "### 1. Title" or "### 1 — Title"
    simple_numbered_re = re.compile(
        r"^#{1,4}\s+(\d+)[.\s—\-]+(.+)",
    )

    seen_ids: set[str] = set()
    auto_counter = 1

    i = 0
    while i < len(lines):
        line = lines[i]

        task_id: str | None = None
        title: str | None = None

        m = task_heading_re.match(line)
        if m:
            task_id = m.group(1).lower()
            title = m.group(2).strip()
        else:
            m2 = explicit_id_re.match(line)
            if m2:
                task_id = m2.group(1).lower()
                # Title is the heading text minus the parenthesised id
                heading_text = re.sub(r"\(?task-\d+\)?", "", line, flags=re.IGNORECASE)
                heading_text = re.sub(r"^#+\s*", "", heading_text).strip()
                heading_text = heading_text.strip(" —-:")
                title = heading_text or task_id
            else:
                m3 = numbered_heading_re.match(line)
                if m3:
                    task_id = f"task-{int(m3.group(1)):03d}"
                    title = m3.group(2).strip()
                else:
                    m4 = simple_numbered_re.match(line)
                    if m4 and int(m4.group(1)) <= 50:  # sanity cap
                        task_id = f"task-{int(m4.group(1)):03d}"
                        title = m4.group(2).strip()

        if task_id and title:
            # Deduplicate
            if task_id in seen_ids:
                task_id = f"{task_id}-{auto_counter}"
                auto_counter += 1
            seen_ids.add(task_id)

            # Collect the body lines until the next same-or-higher heading
            heading_depth = len(line) - len(line.lstrip("#"))
            body_lines: list[str] = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if re.match(r"^#{1," + str(heading_depth) + r"}\s", next_line):
                    break
                body_lines.append(next_line)
                j += 1

            body = "\n".join(body_lines).strip()
            acceptance = _extract_bullets(body, section_hint="acceptance")
            constraints = _extract_bullets(body, section_hint="constraint")
            description = _first_paragraph(body)

            tasks.append(
                {
                    "id": task_id,
                    "title": _clean_title(title),
                    "description": description,
                    "status": "planned",
                    "mode": infer_task_mode(title, description, acceptance).value,
                    "priority": len(tasks),
                    "owner": "",
                    "acceptance_criteria": acceptance,
                    "constraints": constraints,
                    "files_to_touch": [],
                    "changed_files": [],
                    "artifacts": [],
                    "validation_results": [],
                    "validation_status": "pending",
                    "unresolved_issues": [],
                    "follow_up_tasks": [],
                    "depends_on": [],
                    "rework_count": 0,
                    "created_at": ts,
                    "updated_at": ts,
                }
            )

        i += 1

    return tasks


def _first_paragraph(text: str) -> str:
    """Return the first non-empty paragraph from a block of text."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    for p in paragraphs:
        clean = p.strip()
        # Skip lines that look like sub-headings or bullet sections
        if clean and not clean.startswith("#") and not re.match(r"^[-*•]\s", clean[:3]):
            return clean
    return ""


def _extract_bullets(text: str, section_hint: str = "") -> list[str]:
    """
    Extract bullet list items from text, optionally scoped to a named section.
    """
    if section_hint:
        # Look for a subsection heading matching the hint
        pattern = re.compile(
            r"(?:^|\n)#{1,6}\s+[^\n]*" + re.escape(section_hint) + r"[^\n]*\n(.*?)(?=\n#{1,6}\s|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(text)
        scope = m.group(1) if m else text
    else:
        scope = text

    items = []
    for raw_line in scope.splitlines():
        line = raw_line.strip()
        if re.match(r"^[-*•]\s+", line):
            items.append(re.sub(r"^[-*•]\s+", "", line).strip())
        elif re.match(r"^\d+\.\s+", line):
            items.append(re.sub(r"^\d+\.\s+", "", line).strip())
    return [item for item in items if item]


def _clean_title(title: str) -> str:
    """Strip trailing punctuation and common noise from a title string."""
    return re.sub(r"[`*_]", "", title).strip(" :-—")


# ── tasks.json builder ─────────────────────────────────────────────────────────


def build_tasks_json(tasks: list[dict[str, Any]]) -> dict:
    return {"version": 1, "tasks": tasks}


# ── handoff.md builders ────────────────────────────────────────────────────────


def build_handoff_from_spec(title: str) -> str:
    """Create the initial handoff block for an imported specification."""
    return f"""\
## {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")} — Import

Specification imported: `SPECIFICATION.md`

---HANDOFF---
ROLE: human
STATUS: continue
NEXT: architect
TASK_ID: task-000
TITLE: {title}
SUMMARY: A project specification has been imported into SPECIFICATION.md. Read it carefully, write an implementation plan to plan.md, decompose the work into tasks in tasks.json, and assign the first task to the developer.
ACCEPTANCE:
- SPECIFICATION.md has been read and understood
- Implementation plan written to plan.md
- Tasks decomposed into tasks.json with acceptance criteria
- First task assigned to developer
CONSTRAINTS:
- Follow all requirements in SPECIFICATION.md
FILES_TO_TOUCH:
- handoff.md
- plan.md
- tasks.json
CHANGED_FILES:
- n/a
VALIDATION:
- n/a
BLOCKERS:
- none
---END---
"""


def build_handoff_from_plan(title: str, tasks: list[dict[str, Any]]) -> str:
    """Create the initial handoff block for an imported implementation plan."""
    task_count = len(tasks)
    first_task = tasks[0] if tasks else None
    first_task_id = first_task["id"] if first_task else "task-001"
    first_task_title = first_task["title"] if first_task else "first task"
    task_summary = (
        f"{task_count} tasks imported ({', '.join(t['id'] for t in tasks[:5])}"
        + (", …" if task_count > 5 else "")
        + ")"
        if tasks
        else "no tasks detected — decompose manually"
    )

    return f"""\
## {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")} — Import

Implementation plan imported: `plan.md`
Tasks loaded into `tasks.json`: {task_summary}

---HANDOFF---
ROLE: human
STATUS: continue
NEXT: architect
TASK_ID: {first_task_id}
TITLE: {title}
SUMMARY: An implementation plan has been imported into plan.md and tasks have been loaded into tasks.json. Read plan.md and tasks.json to understand the full scope. Assign {first_task_id} ({first_task_title}) to the developer with explicit acceptance criteria. Work through all tasks in order.
ACCEPTANCE:
- plan.md has been read and understood
- tasks.json reflects the imported task list
- First task assigned to developer with explicit acceptance criteria
CONSTRAINTS:
- Work through tasks in the order defined in plan.md
- Do not skip tasks or combine multiple tasks in one turn
FILES_TO_TOUCH:
- handoff.md
- tasks.json
CHANGED_FILES:
- n/a
VALIDATION:
- n/a
BLOCKERS:
- none
---END---
"""


# ── Handoff builders for folder imports ──────────────────────────────────────


def build_handoff_from_specs_folder(files: list[Path], workspace: Path) -> str:
    """Create the initial handoff block after importing a specs directory."""
    rel = [str(f.relative_to(workspace)) for f in files]
    listing = "\n".join(f"- {r}" for r in rel)
    return f"""\
## {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")} — Import

Specifications imported into specs/:
{listing}

---HANDOFF---
ROLE: human
STATUS: continue
NEXT: architect
TASK_ID: task-000
TITLE: Specifications imported
SUMMARY: Multiple specification files have been imported into the specs/ directory. Read each file carefully, write an implementation plan to plan.md, decompose the work into tasks in tasks.json, and assign the first task to the developer.
ACCEPTANCE:
- All files in specs/ have been read and understood
- Implementation plan written to plan.md
- Tasks decomposed into tasks.json with acceptance criteria
- First task assigned to developer
CONSTRAINTS:
- Follow all requirements found in specs/
FILES_TO_TOUCH:
- handoff.md
- plan.md
- tasks.json
CHANGED_FILES:
- n/a
VALIDATION:
- n/a
BLOCKERS:
- none
---END---
"""


def build_handoff_from_plans_folder(files: list[Path], workspace: Path, tasks: list[dict[str, Any]]) -> str:
    """Create the initial handoff block after importing a plans directory."""
    rel = [str(f.relative_to(workspace)) for f in files]
    listing = "\n".join(f"- {r}" for r in rel)
    task_count = len(tasks)
    first_task = tasks[0] if tasks else None
    first_task_id = first_task["id"] if first_task else "task-001"
    first_task_title = first_task["title"] if first_task else "first task"
    task_summary = (
        f"{task_count} tasks imported ({', '.join(t['id'] for t in tasks[:5])}"
        + (", …" if task_count > 5 else "")
        + ")"
        if tasks
        else "no tasks detected — decompose manually"
    )
    return f"""\
## {datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")} — Import

Implementation plans imported into plans/:
{listing}
Tasks loaded into tasks.json: {task_summary}

---HANDOFF---
ROLE: human
STATUS: continue
NEXT: architect
TASK_ID: {first_task_id}
TITLE: Implementation plans imported
SUMMARY: Implementation plan files have been imported into the plans/ directory and tasks have been loaded into tasks.json. Read every file in plans/ and tasks.json to understand the full scope. Assign {first_task_id} ({first_task_title}) to the developer with explicit acceptance criteria. Work through all tasks in order.
ACCEPTANCE:
- All files in plans/ have been read and understood
- tasks.json reflects the imported task list
- First task assigned to developer with explicit acceptance criteria
CONSTRAINTS:
- Work through tasks in the order defined in plans/
- Do not skip tasks or combine multiple tasks in one turn
FILES_TO_TOUCH:
- handoff.md
- tasks.json
CHANGED_FILES:
- n/a
VALIDATION:
- n/a
BLOCKERS:
- none
---END---
"""


# ── Folder import ─────────────────────────────────────────────────────────────


def import_folder(
    source: Path,
    workspace: Path,
    doc_type: str,
    force: bool = False,
    no_handoff: bool = False,
    no_tasks: bool = False,
    verbose: bool = True,
    interactive: bool = True,
) -> None:
    """Import all .md files from *source* (a directory or single file) into the
    appropriate subdirectory of the workspace.

    ``doc_type`` must be ``'spec'`` or ``'plan'``.  Files are written to
    ``<workspace>/specs/`` or ``<workspace>/plans/`` respectively.
    Tasks are extracted from every plan file and merged into ``tasks.json``.
    """
    if doc_type not in ("spec", "plan"):
        raise ValueError(f"doc_type must be 'spec' or 'plan', got {doc_type!r}")

    subdir_name = "specs" if doc_type == "spec" else "plans"
    dest_dir = workspace / subdir_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Collect source files
    if source.is_dir():
        source_files = sorted(p for p in source.rglob("*.md") if p.is_file())
    elif source.is_file():
        source_files = [source]
    else:
        print(f"ERROR: Path not found: {source}")
        sys.exit(1)

    if not source_files:
        if verbose:
            print(f"  No .md files found in {source}")
        return

    written: list[Path] = []
    for src_file in source_files:
        # Preserve relative structure when source is a directory
        if source.is_dir():
            rel = src_file.relative_to(source)
        else:
            rel = Path(src_file.name)
        dest_file = dest_dir / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        _write_file(dest_file, src_file.read_text(encoding="utf-8"), force, verbose, interactive)
        if dest_file.exists():
            written.append(dest_file)

    if doc_type == "plan" and not no_tasks:
        all_tasks: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for dest_file in sorted(dest_dir.rglob("*.md")):
            for task in extract_tasks_from_plan(dest_file.read_text(encoding="utf-8")):
                if task["id"] not in seen_ids:
                    all_tasks.append(task)
                    seen_ids.add(task["id"])
        if all_tasks:
            if verbose:
                print(f"  Extracted {len(all_tasks)} task(s) from plans/")
            tasks_path = workspace / "tasks.json"
            _write_file(
                tasks_path,
                json.dumps(build_tasks_json(all_tasks), indent=2),
                force,
                verbose,
                interactive,
            )
        elif verbose:
            print("  No tasks detected in imported plan files")

    if not no_handoff:
        handoff_path = workspace / "handoff.md"
        dest_files = sorted(dest_dir.rglob("*.md"))
        if handoff_path.exists() and not force:
            if verbose:
                print(f"  Skipped: {handoff_path} already exists (use --force to overwrite)")
        else:
            if doc_type == "spec":
                handoff = build_handoff_from_specs_folder(dest_files, workspace)
            else:
                all_tasks_for_hoff = []
                tasks_path = workspace / "tasks.json"
                if tasks_path.exists():
                    import json as _json
                    data = _json.loads(tasks_path.read_text())
                    all_tasks_for_hoff = data.get("tasks", [])
                handoff = build_handoff_from_plans_folder(dest_files, workspace, all_tasks_for_hoff)
            _write_file(handoff_path, handoff, force, verbose, interactive)

    if verbose:
        print()
        print(f"  Imported {len(source_files)} file(s) → {dest_dir}")
        print(f"  Next:   agent-coordinator --workspace {workspace}")


# ── Import orchestration ───────────────────────────────────────────────────────


def import_document(
    source_path: Path,
    workspace: Path,
    doc_type: str | None = None,
    force: bool = False,
    no_handoff: bool = False,
    no_tasks: bool = False,
    verbose: bool = True,
    interactive: bool = True,
) -> None:
    """
    Import a specification or plan into the workspace.

    Args:
        source_path:  Path to the source markdown document.
        workspace:    Target workspace directory.
        doc_type:     'spec', 'plan', or None (auto-detect).
        force:        Overwrite existing files without asking.
        no_handoff:   Skip creating handoff.md.
        no_tasks:     Skip creating tasks.json (plan imports only).
        verbose:      Print progress messages.
        interactive:  Prompt before overwriting existing files (default True).
                      Pass False when calling programmatically (e.g. from tests).
    """
    if not source_path.exists():
        print(f"ERROR: File not found: {source_path}")
        sys.exit(1)

    content = source_path.read_text(encoding="utf-8")
    title = extract_title(content)

    # Determine document type
    if doc_type is None:
        doc_type = detect_doc_type(content)
        if doc_type == "unknown":
            if interactive and sys.stdin.isatty():
                from agent_coordinator.infrastructure.enhanced_input import Colors, enhanced_choice

                print()
                choice = enhanced_choice(
                    Colors.prompt("Could not auto-detect document type. Is this a (s)pec or (p)lan? [s/p]: "),
                    choices=["s", "p"],
                    default="s",
                )
                doc_type = "spec" if choice == "s" else "plan"
            else:
                doc_type = "spec"
        if verbose:
            print(f"  Detected type: {doc_type}")

    workspace.mkdir(parents=True, exist_ok=True)

    if doc_type == "spec":
        _import_spec(content, title, workspace, force, no_handoff, verbose, interactive)
    else:
        _import_plan(content, title, workspace, force, no_handoff, no_tasks, verbose, interactive)


def _import_spec(
    content: str,
    title: str,
    workspace: Path,
    force: bool,
    no_handoff: bool,
    verbose: bool,
    interactive: bool = True,
) -> None:
    dest = workspace / "SPECIFICATION.md"
    _write_file(dest, content, force, verbose, interactive)

    tasks_path = workspace / "tasks.json"
    if not tasks_path.exists() or force:
        ts = datetime.now(timezone.utc).isoformat()
        bootstrap_tasks = build_tasks_json(
            [
                {
                    "id": "task-000",
                    "title": "Create implementation plan",
                    "description": "Read the specification, define scope, and create executable implementation tasks.",
                    "status": "planned",
                    "mode": TaskMode.PLANNING.value,
                    "priority": 0,
                    "owner": "",
                    "acceptance_criteria": [
                        "Scope is clear enough to begin building",
                        "Dependencies are identified",
                        "At least one executable implementation task exists",
                    ],
                    "constraints": [],
                    "files_to_touch": ["plan.md", "tasks.json"],
                    "changed_files": [],
                    "artifacts": [],
                    "validation_results": [],
                    "validation_status": "pending",
                    "unresolved_issues": [],
                    "follow_up_tasks": [],
                    "depends_on": [],
                    "rework_count": 0,
                    "created_at": ts,
                    "updated_at": ts,
                }
            ]
        )
        _write_file(tasks_path, json.dumps(bootstrap_tasks, indent=2), force, verbose, interactive)

    if not no_handoff:
        handoff_path = workspace / "handoff.md"
        if handoff_path.exists() and not force:
            if verbose:
                print(f"  Skipped: {handoff_path} already exists (use --force to overwrite)")
        else:
            _write_file(handoff_path, build_handoff_from_spec(title), force, verbose, interactive)

    if verbose:
        print()
        print(f"  Title:  {title}")
        print(f"  Next:   agent-coordinator --workspace {workspace}")


def _import_plan(
    content: str,
    title: str,
    workspace: Path,
    force: bool,
    no_handoff: bool,
    no_tasks: bool,
    verbose: bool,
    interactive: bool = True,
) -> None:
    dest = workspace / "plan.md"
    _write_file(dest, content, force, verbose, interactive)

    tasks = extract_tasks_from_plan(content)
    if verbose:
        print(f"  Extracted {len(tasks)} task(s) from plan")

    if tasks and not no_tasks:
        tasks_path = workspace / "tasks.json"
        if tasks_path.exists() and not force:
            if verbose:
                print(f"  Skipped: {tasks_path} already exists (use --force to overwrite)")
        else:
            _write_file(
                tasks_path,
                json.dumps(build_tasks_json(tasks), indent=2),
                force,
                verbose,
                interactive,
            )

    if not no_handoff:
        handoff_path = workspace / "handoff.md"
        if handoff_path.exists() and not force:
            if verbose:
                print(f"  Skipped: {handoff_path} already exists (use --force to overwrite)")
        else:
            _write_file(handoff_path, build_handoff_from_plan(title, tasks), force, verbose, interactive)

    if verbose:
        print()
        print(f"  Title:  {title}")
        if tasks:
            print(f"  Tasks:  {', '.join(t['id'] for t in tasks)}")
        print(f"  Next:   agent-coordinator --workspace {workspace}")


def _write_file(path: Path, content: str, force: bool, verbose: bool, interactive: bool = True) -> None:
    if path.exists() and not force:
        if interactive and sys.stdin.isatty():
            response = input(f"\n  {path.name} already exists. Overwrite? [y/N]: ").strip().lower()
            if response != "y":
                if verbose:
                    print(f"  Skipped: {path}")
                return
        else:
            if verbose:
                print(f"  Skipped: {path} (use --force to overwrite)")
            return
    path.write_text(content, encoding="utf-8")
    if verbose:
        print(f"  Written: {path}")


# ── CLI ────────────────────────────────────────────────────────────────────────


def main_import() -> None:
    parser = argparse.ArgumentParser(
        description="Import a specification or implementation plan into a workspace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import a specification (auto-detected):
  python -m agent_coordinator.helpers import SPECIFICATION.md --workspace ./my-project

  # Import an implementation plan explicitly:
  python -m agent_coordinator.helpers import plan.md --workspace ./my-project --type plan

  # Import without creating handoff.md:
  python -m agent_coordinator.helpers import SPEC.md --workspace ./my-project --no-handoff

  # Overwrite existing files:
  python -m agent_coordinator.helpers import plan.md --workspace ./my-project --force
""",
    )
    parser.add_argument("file", type=Path, help="Path to the specification or plan file to import")
    parser.add_argument("--workspace", type=Path, required=True, help="Target workspace directory")
    parser.add_argument(
        "--type",
        choices=["spec", "plan"],
        default=None,
        dest="doc_type",
        help="Document type (default: auto-detect from content)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--no-handoff", action="store_true", help="Do not create handoff.md")
    parser.add_argument("--no-tasks", action="store_true", help="Do not create tasks.json (plan imports only)")
    parser.add_argument("--quiet", action="store_true", help="Suppress output")
    args = parser.parse_args()

    source = args.file.resolve()
    workspace = args.workspace.resolve()

    if not args.quiet:
        print(f"\nImporting: {source}")
        print(f"Workspace: {workspace}")
        print()

    import_document(
        source_path=source,
        workspace=workspace,
        doc_type=args.doc_type,
        force=args.force,
        no_handoff=args.no_handoff,
        no_tasks=args.no_tasks,
        verbose=not args.quiet,
    )

    if not args.quiet:
        print()
        print("Done. Run the coordinator to start:")
        print(f"  agent-coordinator --workspace {workspace}")


if __name__ == "__main__":
    main_import()
