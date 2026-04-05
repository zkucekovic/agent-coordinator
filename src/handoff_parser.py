"""Parser for structured handoff blocks in the two-agent coordination workflow."""

import re
from src.models import (
    AgentRole, HandoffStatus, NextActor,
    HandoffMessage, ValidationResult
)

# Regex to extract all ---HANDOFF--- ... ---END--- blocks
_BLOCK_RE = re.compile(r'---HANDOFF---(.*?)---END---', re.DOTALL)

# Required scalar fields
_SCALAR_FIELDS = ['ROLE', 'STATUS', 'NEXT', 'TASK_ID', 'TITLE', 'SUMMARY']

# List fields (bullet-list sections)
_LIST_FIELDS = [
    'ACCEPTANCE', 'CONSTRAINTS', 'FILES_TO_TOUCH',
    'CHANGED_FILES', 'VALIDATION', 'BLOCKERS'
]

# All section headers (used to detect where a section ends)
_ALL_FIELDS = _SCALAR_FIELDS + _LIST_FIELDS


def _parse_scalar(block_text: str, field: str) -> tuple[str | None, str | None]:
    """Extract a scalar field value. Returns (value, error)."""
    pattern = re.compile(rf'^{field}:\s*(.+)$', re.MULTILINE)
    match = pattern.search(block_text)
    if not match:
        return None, f"Missing required field: {field}"
    return match.group(1).strip(), None


def _parse_list_field(block_text: str, field: str) -> list[str]:
    """Extract a bullet-list field. Returns list of items (strips leading '- ')."""
    header_pattern = re.compile(rf'^{field}:\s*$', re.MULTILINE)
    header_match = header_pattern.search(block_text)
    if not header_match:
        inline = re.search(rf'^{field}:\s*(.+)$', block_text, re.MULTILINE)
        if inline:
            val = inline.group(1).strip()
            return [] if val.lower() in ('none', 'n/a', '') else [val]
        return []

    start = header_match.end()
    next_field_pattern = re.compile(
        r'^(' + '|'.join(_ALL_FIELDS) + r'):', re.MULTILINE
    )
    next_match = next_field_pattern.search(block_text, start)
    section_text = block_text[start: next_match.start() if next_match else len(block_text)]

    items = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('- '):
            items.append(stripped[2:].strip())
        elif stripped and not stripped.startswith('#'):
            items.append(stripped)
    return [i for i in items if i.lower() not in ('none', 'n/a')]


def parse_block(block_text: str) -> tuple[HandoffMessage | None, list[str]]:
    """
    Parse a single handoff block text (content between ---HANDOFF--- and ---END---).
    Returns (HandoffMessage, []) on success or (None, [errors]) on failure.
    """
    errors = []

    scalars = {}
    for field in _SCALAR_FIELDS:
        value, err = _parse_scalar(block_text, field)
        if err:
            errors.append(err)
        else:
            scalars[field] = value

    if errors:
        return None, errors

    try:
        role = AgentRole(scalars['ROLE'].lower())
    except ValueError:
        errors.append(f"Invalid ROLE value: {scalars['ROLE']!r}")

    try:
        status = HandoffStatus(scalars['STATUS'].lower())
    except ValueError:
        errors.append(f"Invalid STATUS value: {scalars['STATUS']!r}")

    try:
        next_actor = NextActor(scalars['NEXT'].lower())
    except ValueError:
        errors.append(f"Invalid NEXT value: {scalars['NEXT']!r}")

    if errors:
        return None, errors

    ftt = _parse_list_field(block_text, 'FILES_TO_TOUCH')
    cf = _parse_list_field(block_text, 'CHANGED_FILES')

    msg = HandoffMessage(
        role=role,
        status=status,
        next=next_actor,
        task_id=scalars['TASK_ID'],
        title=scalars['TITLE'],
        summary=scalars['SUMMARY'],
        acceptance=_parse_list_field(block_text, 'ACCEPTANCE'),
        constraints=_parse_list_field(block_text, 'CONSTRAINTS'),
        files_to_touch=ftt,
        changed_files=cf,
        validation=_parse_list_field(block_text, 'VALIDATION'),
        blockers=_parse_list_field(block_text, 'BLOCKERS'),
    )
    return msg, []


def extract_latest(content: str) -> tuple[HandoffMessage | None, list[str]]:
    """
    Find and parse the latest valid ---HANDOFF--- block from full file content.
    Returns (HandoffMessage, []) for last valid block, or (None, [errors]) if none found.
    """
    blocks = _BLOCK_RE.findall(content)
    if not blocks:
        return None, ["No ---HANDOFF--- blocks found in content"]

    last_errors: list[str] = []
    for block_text in reversed(blocks):
        msg, errors = parse_block(block_text)
        if msg is not None:
            return msg, []
        last_errors = errors

    return None, last_errors or ["No valid handoff block found"]

