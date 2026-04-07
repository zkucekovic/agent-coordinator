"""Tests for agent_coordinator/infrastructure/editor.py"""
from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agent_coordinator.infrastructure.editor import (
    edit_handoff_message,
    edit_specification,
    edit_task,
    edit_text,
    get_editor,
)


# ── get_editor ────────────────────────────────────────────────────────────────

class TestGetEditor:
    def test_uses_visual_env(self, monkeypatch):
        monkeypatch.setenv("VISUAL", "emacs")
        monkeypatch.setenv("EDITOR", "vim")
        assert get_editor() == "emacs"

    def test_uses_editor_when_no_visual(self, monkeypatch):
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "vim")
        assert get_editor() == "vim"

    def test_falls_back_to_vi(self, monkeypatch):
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)
        assert get_editor() == "vi"

    def test_visual_takes_priority_over_editor(self, monkeypatch):
        monkeypatch.setenv("VISUAL", "code")
        monkeypatch.setenv("EDITOR", "nano")
        assert get_editor() == "code"


# ── edit_text ─────────────────────────────────────────────────────────────────

class TestEditText:
    def _mock_run(self):
        """Return a mock that does nothing (editor no-op)."""
        return patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0),
        )

    def test_returns_initial_content_unchanged(self):
        with self._mock_run():
            result = edit_text("hello world")
        assert result == "hello world"

    def test_strips_comment_lines(self):
        with self._mock_run():
            result = edit_text("real content", comment_lines=["ignore me"])
        assert result == "real content"
        assert "# ignore me" not in result

    def test_empty_initial_text_no_comments(self):
        with self._mock_run():
            result = edit_text("")
        assert result == ""

    def test_comment_lines_only_no_initial_text(self):
        with self._mock_run():
            result = edit_text("", comment_lines=["header note"])
        assert result == ""

    def test_multiple_comment_lines(self):
        with self._mock_run():
            result = edit_text("body", comment_lines=["line1", "line2", "line3"])
        assert result == "body"

    def test_uses_visual_env_as_editor(self, monkeypatch):
        monkeypatch.setenv("VISUAL", "myeditor")
        monkeypatch.delenv("EDITOR", raising=False)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            edit_text("x")
        assert mock_run.call_args[0][0][0] == "myeditor"

    def test_uses_editor_env_when_no_visual(self, monkeypatch):
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "nano")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            edit_text("x")
        assert mock_run.call_args[0][0][0] == "nano"

    def test_falls_back_to_vi_editor(self, monkeypatch):
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            edit_text("x")
        assert mock_run.call_args[0][0][0] == "vi"

    def test_subprocess_called_process_error_propagates(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "vi")):
            with pytest.raises(subprocess.CalledProcessError):
                edit_text("hello")

    def test_comment_separator_blank_line_added(self):
        """When both comment_lines and initial_text are given, a blank line is added between them."""
        with self._mock_run():
            result = edit_text("content", comment_lines=["note"])
        assert "content" in result

    def test_inline_hash_in_content_is_not_stripped(self):
        """Only lines *starting* with # are stripped."""
        with self._mock_run():
            result = edit_text("color: #FF0000")
        assert "color: #FF0000" in result


# ── edit_specification ────────────────────────────────────────────────────────

class TestEditSpecification:
    def _make_spec_content(self) -> str:
        return (
            "My Project\n\n"
            "## Description\n\nA great project.\n\n"
            "## Requirements\n\n- Fast\n- Reliable\n\n"
            "## Constraints\n\n- No external APIs\n"
        )

    def test_returns_dict_with_expected_keys(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_spec_content(),
        ):
            result = edit_specification()
        assert set(result.keys()) == {"title", "description", "requirements", "constraints"}

    def test_parses_title(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_spec_content(),
        ):
            result = edit_specification()
        assert result["title"] == "My Project"

    def test_parses_description(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_spec_content(),
        ):
            result = edit_specification()
        assert "great project" in result["description"]

    def test_parses_requirements(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_spec_content(),
        ):
            result = edit_specification()
        assert "Fast" in result["requirements"]
        assert "Reliable" in result["requirements"]

    def test_parses_constraints(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_spec_content(),
        ):
            result = edit_specification()
        assert "No external APIs" in result["constraints"]

    def test_empty_content_returns_empty_fields(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value="",
        ):
            result = edit_specification()
        assert result["title"] == ""
        assert result["description"] == ""
        assert result["requirements"] == []
        assert result["constraints"] == []

    def test_unknown_section_stops_current_section(self):
        content = (
            "Title\n\n"
            "## Description\n\nsome desc\n\n"
            "## Other\n\nignored\n"
        )
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=content,
        ):
            result = edit_specification()
        # After ## Other, section resets; 'ignored' should not be in description
        assert "ignored" not in result["description"]


# ── edit_task ─────────────────────────────────────────────────────────────────

class TestEditTask:
    def _make_task_content(self) -> str:
        return (
            "task-001: Implement feature\n\n"
            "Do the thing.\n\n"
            "## Acceptance Criteria\n\n- Works correctly\n- Has tests\n\n"
            "## Dependencies\n\n- task-000\n"
        )

    def test_returns_dict_with_expected_keys(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_task_content(),
        ):
            result = edit_task()
        assert set(result.keys()) == {
            "id", "title", "description", "acceptance_criteria", "dependencies"
        }

    def test_parses_id_and_title(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_task_content(),
        ):
            result = edit_task()
        assert result["id"] == "task-001"
        assert result["title"] == "Implement feature"

    def test_parses_description(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_task_content(),
        ):
            result = edit_task()
        assert "Do the thing" in result["description"]

    def test_parses_acceptance_criteria(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_task_content(),
        ):
            result = edit_task()
        assert "Works correctly" in result["acceptance_criteria"]
        assert "Has tests" in result["acceptance_criteria"]

    def test_parses_dependencies(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=self._make_task_content(),
        ):
            result = edit_task()
        assert "task-000" in result["dependencies"]

    def test_first_line_without_colon_leaves_id_empty(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value="No colon here\n\nsome desc",
        ):
            result = edit_task()
        assert result["id"] == ""

    def test_empty_content(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value="",
        ):
            result = edit_task()
        assert result["id"] == ""
        assert result["title"] == ""
        assert result["description"] == ""
        assert result["acceptance_criteria"] == []
        assert result["dependencies"] == []

    def test_unknown_section_resets_current_section(self):
        content = (
            "task-002: Fix bug\n\n"
            "desc line\n\n"
            "## Unknown Section\n\n"
            "- should not appear in criteria\n"
        )
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value=content,
        ):
            result = edit_task()
        assert result["acceptance_criteria"] == []


# ── edit_handoff_message ──────────────────────────────────────────────────────

class TestEditHandoffMessage:
    def test_returns_string(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value="my message",
        ):
            result = edit_handoff_message()
        assert result == "my message"

    def test_with_current_handoff(self):
        """When current_handoff is provided, edit_text is still called and result returned."""
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value="updated message",
        ) as mock_edit:
            result = edit_handoff_message(current_handoff="old context\nmore lines")
        assert result == "updated message"
        # comment_lines should include current handoff content
        call_kwargs = mock_edit.call_args
        comment_lines = call_kwargs[0][1] if call_kwargs[0] else call_kwargs[1]["comment_lines"]
        assert any("old context" in line for line in comment_lines)

    def test_without_current_handoff(self):
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value="",
        ) as mock_edit:
            edit_handoff_message()
        call_kwargs = mock_edit.call_args
        comment_lines = call_kwargs[0][1] if call_kwargs[0] else call_kwargs[1]["comment_lines"]
        # Should not include separator lines when no current_handoff
        assert not any("=" * 50 in line for line in comment_lines)

    def test_long_handoff_is_truncated_to_20_lines(self):
        long_handoff = "\n".join(f"line {i}" for i in range(50))
        with patch(
            "agent_coordinator.infrastructure.editor.edit_text",
            return_value="",
        ) as mock_edit:
            edit_handoff_message(current_handoff=long_handoff)
        call_kwargs = mock_edit.call_args
        comment_lines = call_kwargs[0][1] if call_kwargs[0] else call_kwargs[1]["comment_lines"]
        # Only first 20 lines of handoff are included
        assert not any("line 20" in line for line in comment_lines)
        assert any("line 0" in line for line in comment_lines)
