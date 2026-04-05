"""Tests for src.application.prompt_builder (PromptBuilder)."""

import tempfile
import os
import unittest
from pathlib import Path

from src.application.prompt_builder import PromptBuilder
from src.domain.models import Task, TaskStatus


def _make_workspace() -> Path:
    d = Path(tempfile.mkdtemp())
    prompts = d / "prompts"
    prompts.mkdir()
    (prompts / "architect.md").write_text("You are the architect.")
    (prompts / "shared_rules.md").write_text("Rule 1: be helpful.")
    return d


class TestPromptBuilder(unittest.TestCase):

    def setUp(self):
        self._workspace = _make_workspace()
        self._builder = PromptBuilder()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._workspace, ignore_errors=True)

    def _cfg(self) -> dict:
        return {"prompt_file": "prompts/architect.md"}

    def test_first_turn_includes_role_prompt(self):
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="## handoff content",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("You are the architect.", prompt)

    def test_first_turn_includes_shared_rules(self):
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="## handoff",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Rule 1: be helpful.", prompt)

    def test_subsequent_turn_omits_role_prompt_body(self):
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="## handoff",
            agent_cfg=self._cfg(),
            first_turn=False,
        )
        self.assertNotIn("You are the architect.", prompt)

    def test_handoff_content_always_included(self):
        content = "## This is the handoff"
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content=content,
            agent_cfg=self._cfg(),
        )
        self.assertIn(content, prompt)

    def test_task_context_shown_when_task_provided(self):
        task = Task(id="task-001", title="Build parser", status=TaskStatus.PLANNED)
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            next_task=task,
        )
        self.assertIn("task-001", prompt)
        self.assertIn("Build parser", prompt)

    def test_rework_note_shown_when_rework_count_positive(self):
        task = Task(
            id="task-001", title="Build parser",
            status=TaskStatus.REWORK_REQUESTED, rework_count=2,
        )
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            next_task=task,
        )
        self.assertIn("rework #2", prompt)

    def test_no_task_context_when_task_is_none(self):
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            next_task=None,
        )
        self.assertNotIn("Next ready task", prompt)

    def test_missing_prompt_file_uses_fallback(self):
        prompt = self._builder.build(
            role="qa",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg={"prompt_file": "prompts/qa.md"},  # file doesn't exist
            first_turn=True,
        )
        self.assertIn("QA", prompt)

    def test_role_name_in_prompt(self):
        prompt = self._builder.build(
            role="engineer",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg={"prompt_file": "prompts/engineer.md"},
            first_turn=True,
        )
        self.assertIn("ENGINEER", prompt)


if __name__ == "__main__":
    unittest.main()
