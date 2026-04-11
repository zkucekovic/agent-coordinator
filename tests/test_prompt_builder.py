"""Tests for src.application.prompt_builder (PromptBuilder)."""

import tempfile
import unittest
from pathlib import Path

from agent_coordinator.application.prompt_builder import PromptBuilder
from agent_coordinator.domain.models import Task, TaskStatus


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

    def test_first_turn_does_not_inject_shared_rules_separately(self):
        """shared_rules.md is no longer injected as a separate section (merged into role prompts)."""
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="## handoff",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        # The role prompt is included, but shared_rules.md content is NOT injected separately
        self.assertIn("You are the architect.", prompt)
        self.assertNotIn("Rule 1: be helpful.", prompt)

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
            id="task-001",
            title="Build parser",
            status=TaskStatus.REWORK_REQUESTED,
            rework_count=2,
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
            role="developer",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg={"prompt_file": "prompts/developer.md"},
            first_turn=True,
        )
        self.assertIn("DEVELOPER", prompt)

    def test_workspace_prompt_takes_priority_over_coordinator_dir(self):
        """P5: Workspace prompt files override coordinator_dir (package) defaults."""
        coord_dir = Path(tempfile.mkdtemp())
        try:
            coord_prompts = coord_dir / "prompts"
            coord_prompts.mkdir()
            (coord_prompts / "architect.md").write_text("Package-level architect prompt.")

            ws_prompts = self._workspace / "prompts"
            ws_prompts.mkdir(exist_ok=True)
            (ws_prompts / "architect.md").write_text("User-customised architect prompt.")

            builder = PromptBuilder(coordinator_dir=coord_dir)
            prompt = builder.build(
                role="architect",
                workspace=self._workspace,
                handoff_content="",
                agent_cfg={"prompt_file": "prompts/architect.md"},
                first_turn=True,
            )
            self.assertIn("User-customised architect prompt.", prompt)
            self.assertNotIn("Package-level architect prompt.", prompt)
        finally:
            import shutil

            shutil.rmtree(coord_dir, ignore_errors=True)

    def test_coordinator_dir_used_as_fallback_when_not_in_workspace(self):
        """P5: If file not in workspace, falls back to coordinator_dir."""
        coord_dir = Path(tempfile.mkdtemp())
        try:
            coord_prompts = coord_dir / "prompts"
            coord_prompts.mkdir()
            (coord_prompts / "special.md").write_text("Package-fallback prompt.")

            builder = PromptBuilder(coordinator_dir=coord_dir)
            prompt = builder.build(
                role="special",
                workspace=self._workspace,
                handoff_content="",
                agent_cfg={"prompt_file": "prompts/special.md"},
                first_turn=True,
            )
            self.assertIn("Package-fallback prompt.", prompt)
        finally:
            import shutil

            shutil.rmtree(coord_dir, ignore_errors=True)

    def test_workspace_prompt_used_when_no_coordinator_dir(self):
        """P5: Falls back to workspace when coordinator_dir is None."""
        builder = PromptBuilder(coordinator_dir=None)
        prompt = builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg={"prompt_file": "prompts/architect.md"},
            first_turn=True,
        )
        self.assertIn("You are the architect.", prompt)

    def test_workspace_prompt_used_when_file_only_in_workspace(self):
        """P5: If prompt only in workspace (not coordinator_dir), workspace is used."""
        coord_dir = Path(tempfile.mkdtemp())
        try:
            builder = PromptBuilder(coordinator_dir=coord_dir)
            prompt = builder.build(
                role="architect",
                workspace=self._workspace,
                handoff_content="",
                agent_cfg={"prompt_file": "prompts/architect.md"},
                first_turn=True,
            )
            self.assertIn("You are the architect.", prompt)
        finally:
            import shutil

            shutil.rmtree(coord_dir, ignore_errors=True)

    def test_project_rules_loaded_from_workspace(self):
        """AGENTS.md in workspace is injected on first turn."""
        (self._workspace / "AGENTS.md").write_text("Project rule: use TDD.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Project rule: use TDD.", prompt)

    def test_project_rules_not_on_subsequent_turns(self):
        """AGENTS.md is only injected on first turn."""
        (self._workspace / "AGENTS.md").write_text("Project rule: use TDD.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=False,
        )
        self.assertNotIn("Project rule: use TDD.", prompt)

    def test_specification_injected_on_first_turn(self):
        """SPECIFICATION.md in workspace is injected on first turn."""
        (self._workspace / "SPECIFICATION.md").write_text("Build a REST API.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Build a REST API.", prompt)
        self.assertIn("Specification", prompt)

    def test_spec_md_variant_detected(self):
        """spec.md is also detected as a specification file."""
        (self._workspace / "spec.md").write_text("Spec content here.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Spec content here.", prompt)

    def test_plan_injected_on_first_turn(self):
        """plan.md in workspace is injected on first turn."""
        (self._workspace / "plan.md").write_text("Step 1: do the thing.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Step 1: do the thing.", prompt)
        self.assertIn("Implementation Plan", prompt)

    def test_spec_and_plan_both_injected(self):
        """Both spec and plan are injected when both exist."""
        (self._workspace / "SPECIFICATION.md").write_text("The requirements.")
        (self._workspace / "IMPLEMENTATION_PLAN.md").write_text("The plan.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("The requirements.", prompt)
        self.assertIn("The plan.", prompt)

    def test_project_docs_not_on_subsequent_turns(self):
        """Spec and plan are only injected on first turn."""
        (self._workspace / "SPECIFICATION.md").write_text("The requirements.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=False,
        )
        self.assertNotIn("The requirements.", prompt)

    def test_no_docs_is_fine(self):
        """No spec or plan files — prompt still builds correctly."""
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="test",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("test", prompt)
        self.assertNotIn("Project Specification", prompt)
        self.assertNotIn("Implementation Plan", prompt)

    def test_specs_directory_loads_all_md_files(self):
        """specs/ directory: all .md files are injected on first turn."""
        specs_dir = self._workspace / "specs"
        specs_dir.mkdir()
        (specs_dir / "auth.md").write_text("Auth spec content.")
        (specs_dir / "payments.md").write_text("Payments spec content.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Auth spec content.", prompt)
        self.assertIn("Payments spec content.", prompt)
        self.assertIn("Specification", prompt)

    def test_plans_directory_loads_all_md_files(self):
        """plans/ directory: all .md files are injected on first turn."""
        plans_dir = self._workspace / "plans"
        plans_dir.mkdir()
        (plans_dir / "phase1.md").write_text("Phase 1 plan.")
        (plans_dir / "phase2.md").write_text("Phase 2 plan.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Phase 1 plan.", prompt)
        self.assertIn("Phase 2 plan.", prompt)
        self.assertIn("Implementation Plan", prompt)

    def test_specs_dir_takes_priority_over_single_spec_file(self):
        """specs/ directory takes priority over a root SPECIFICATION.md file."""
        (self._workspace / "SPECIFICATION.md").write_text("Root spec — should be ignored.")
        specs_dir = self._workspace / "specs"
        specs_dir.mkdir()
        (specs_dir / "api.md").write_text("API spec from directory.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("API spec from directory.", prompt)
        self.assertNotIn("Root spec — should be ignored.", prompt)

    def test_specs_dir_falls_back_to_root_file_when_dir_absent(self):
        """Falls back to SPECIFICATION.md when no specs directory exists."""
        (self._workspace / "SPECIFICATION.md").write_text("Fallback root spec.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Fallback root spec.", prompt)

    def test_specs_dir_alternative_names_detected(self):
        """spec/ and specifications/ directories are also recognised."""
        spec_dir = self._workspace / "specifications"
        spec_dir.mkdir()
        (spec_dir / "overview.md").write_text("Overview spec.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Overview spec.", prompt)

    def test_plans_dir_alternative_names_detected(self):
        """plan/ and implementation_plans/ directories are also recognised."""
        plans_dir = self._workspace / "implementation_plans"
        plans_dir.mkdir()
        (plans_dir / "milestone1.md").write_text("Milestone 1.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("Milestone 1.", prompt)

    def test_directory_docs_not_on_subsequent_turns(self):
        """Files in specs/ and plans/ are only injected on first turn."""
        specs_dir = self._workspace / "specs"
        specs_dir.mkdir()
        (specs_dir / "auth.md").write_text("Auth spec content.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=False,
        )
        self.assertNotIn("Auth spec content.", prompt)

    def test_specs_directory_section_includes_relative_path(self):
        """Section header includes the file's relative path for traceability."""
        specs_dir = self._workspace / "specs"
        specs_dir.mkdir()
        (specs_dir / "core.md").write_text("Core spec.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("specs/core.md", prompt)

    def test_large_spec_is_previewed_not_full(self):
        """Large spec files get a preview + pointer instead of full injection."""
        long_content = "\n".join([f"# Section {i}\nContent for section {i}." for i in range(60)])
        (self._workspace / "SPECIFICATION.md").write_text(long_content)
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("preview below", prompt)
        self.assertIn("Read the full file", prompt)
        # First few sections should be present
        self.assertIn("Section 0", prompt)
        # Later sections should NOT be in the prompt
        self.assertNotIn("Section 55", prompt)

    def test_small_spec_is_shown_in_full(self):
        """Small spec files are shown completely."""
        (self._workspace / "SPECIFICATION.md").write_text("# Spec\nSmall spec.")
        prompt = self._builder.build(
            role="architect",
            workspace=self._workspace,
            handoff_content="",
            agent_cfg=self._cfg(),
            first_turn=True,
        )
        self.assertIn("shown in full", prompt)
        self.assertIn("Small spec.", prompt)


if __name__ == "__main__":
    unittest.main()
