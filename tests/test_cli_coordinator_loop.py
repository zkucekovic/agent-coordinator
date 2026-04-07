"""Unit tests for run_coordinator in agent_coordinator/cli.py."""
import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from agent_coordinator.domain.models import RunResult

# ── Helpers ───────────────────────────────────────────────────────────────────

_HANDOFF_PLAN_COMPLETE = textwrap.dedent("""\
    ---HANDOFF---
    ROLE: architect
    STATUS: plan_complete
    NEXT: architect
    TASK_ID: task-000
    TITLE: Test
    SUMMARY: test
    ACCEPTANCE:
    - done
    CONSTRAINTS:
    - none
    ---END---
""")

_HANDOFF_CONTINUE = textwrap.dedent("""\
    ---HANDOFF---
    ROLE: architect
    STATUS: continue
    NEXT: architect
    TASK_ID: task-000
    TITLE: Test
    SUMMARY: test
    ACCEPTANCE:
    - done
    CONSTRAINTS:
    - none
    ---END---
""")

_AGENTS_JSON = json.dumps({
    "default_backend": "copilot",
    "agents": {
        "architect": {"prompt_file": "prompts/architect.md"},
    },
})


def _make_workspace(handoff_content: str = _HANDOFF_PLAN_COMPLETE) -> Path:
    """Create a temp directory with a minimal workspace."""
    tmp = tempfile.mkdtemp()
    ws = Path(tmp)
    (ws / "handoff.md").write_text(handoff_content)
    (ws / "agents.json").write_text(_AGENTS_JSON)
    return ws


def _mock_display() -> MagicMock:
    """Build a MagicMock that quacks like a Screen / SimpleProgressDisplay."""
    d = MagicMock()
    d._theme = MagicMock()
    d._theme.color_warning = ""
    d._theme.color_success = ""
    d._active = False
    d.max_output_lines = 10
    d.stream_delay = 0.0
    return d


# ── Common patches applied to all tests ───────────────────────────────────────

def _common_patches():
    """Return context managers that suppress I/O & logging side-effects."""
    return [
        patch("agent_coordinator.cli.setup_log", return_value=None),
        patch("agent_coordinator.cli.get_logger", return_value=MagicMock()),
        patch("agent_coordinator.cli.log_crash"),
        # InterruptMenu imported inside run_coordinator
        patch("agent_coordinator.infrastructure.tui.InterruptMenu", return_value=MagicMock()),
        # Suppress the sleep between turns
        patch("agent_coordinator.cli.time.sleep"),
    ]


# ── Test cases ─────────────────────────────────────────────────────────────────

class TestRunCoordinatorTerminalWorkflow(unittest.TestCase):
    """plan_complete status → router detects terminal → loop stops immediately."""

    def test_plan_complete_exits_cleanly(self):
        ws = _make_workspace(_HANDOFF_PLAN_COMPLETE)
        display = _mock_display()

        patches = _common_patches() + [
            patch("agent_coordinator.infrastructure.tui.create_display", return_value=display),
        ]
        with _apply_patches(patches):
            from agent_coordinator.cli import run_coordinator
            run_coordinator(
                workspace=ws,
                max_turns=5,
                reset=False,
                verbose=False,
            )

        # close() must always be called (finally block)
        display.close.assert_called_once()

    def test_start_run_called_before_loop(self):
        ws = _make_workspace(_HANDOFF_PLAN_COMPLETE)
        display = _mock_display()

        patches = _common_patches() + [
            patch("agent_coordinator.infrastructure.tui.create_display", return_value=display),
        ]
        with _apply_patches(patches):
            from agent_coordinator.cli import run_coordinator
            run_coordinator(workspace=ws, max_turns=5, reset=False, verbose=False)

        display.start_run.assert_called_once()


class TestRunCoordinatorSingleAgentTurn(unittest.TestCase):
    """Handoff starts as 'continue → architect', mock runner writes plan_complete."""

    def _make_mock_runner(self, ws: Path) -> MagicMock:
        """Runner that writes plan_complete handoff on first call."""

        def _run_side_effect(**kwargs):
            (ws / "handoff.md").write_text(_HANDOFF_PLAN_COMPLETE)
            return RunResult(session_id="test-session-1", text="done")

        runner = MagicMock()
        runner.run.side_effect = _run_side_effect
        return runner

    def test_start_agent_turn_called_once(self):
        ws = _make_workspace(_HANDOFF_CONTINUE)
        display = _mock_display()
        runner = self._make_mock_runner(ws)

        patches = _common_patches() + [
            patch("agent_coordinator.infrastructure.tui.create_display", return_value=display),
            patch("agent_coordinator.cli.create_runner_for_agent", return_value=runner),
            patch("agent_coordinator.cli.PromptBuilder", return_value=MagicMock(
                **{"build.return_value": "test prompt"}
            )),
        ]
        with _apply_patches(patches):
            from agent_coordinator.cli import run_coordinator
            run_coordinator(workspace=ws, max_turns=5, reset=False, verbose=False)

        display.start_agent_turn.assert_called_once()

    def test_finish_agent_turn_called_with_success(self):
        ws = _make_workspace(_HANDOFF_CONTINUE)
        display = _mock_display()
        runner = self._make_mock_runner(ws)

        patches = _common_patches() + [
            patch("agent_coordinator.infrastructure.tui.create_display", return_value=display),
            patch("agent_coordinator.cli.create_runner_for_agent", return_value=runner),
            patch("agent_coordinator.cli.PromptBuilder", return_value=MagicMock(
                **{"build.return_value": "test prompt"}
            )),
        ]
        with _apply_patches(patches):
            from agent_coordinator.cli import run_coordinator
            run_coordinator(workspace=ws, max_turns=5, reset=False, verbose=False)

        # finish_agent_turn(success=True, ...) must be called
        finish_calls = display.finish_agent_turn.call_args_list
        self.assertTrue(any(
            (c.args[0] if c.args else None) is True or c.kwargs.get("success") is True
            for c in finish_calls
        ))


class TestRunCoordinatorReset(unittest.TestCase):
    """reset=True should clear the session store."""

    def test_reset_calls_session_store_clear(self):
        ws = _make_workspace(_HANDOFF_PLAN_COMPLETE)
        display = _mock_display()
        mock_store = MagicMock()

        patches = _common_patches() + [
            patch("agent_coordinator.infrastructure.tui.create_display", return_value=display),
            patch("agent_coordinator.cli.SessionStore", return_value=mock_store),
        ]
        with _apply_patches(patches):
            from agent_coordinator.cli import run_coordinator
            run_coordinator(workspace=ws, max_turns=5, reset=True, verbose=False)

        mock_store.clear.assert_called_once()

    def test_no_reset_does_not_call_clear(self):
        ws = _make_workspace(_HANDOFF_PLAN_COMPLETE)
        display = _mock_display()
        mock_store = MagicMock()

        patches = _common_patches() + [
            patch("agent_coordinator.infrastructure.tui.create_display", return_value=display),
            patch("agent_coordinator.cli.SessionStore", return_value=mock_store),
        ]
        with _apply_patches(patches):
            from agent_coordinator.cli import run_coordinator
            run_coordinator(workspace=ws, max_turns=5, reset=False, verbose=False)

        mock_store.clear.assert_not_called()


class TestRunCoordinatorPassedDisplay(unittest.TestCase):
    """When display= is provided, create_display must NOT be called."""

    def test_passed_display_is_reused(self):
        ws = _make_workspace(_HANDOFF_PLAN_COMPLETE)
        display = _mock_display()

        base_patches = _common_patches()
        with _apply_patches(base_patches):
            with patch("agent_coordinator.infrastructure.tui.create_display") as mock_factory:
                from agent_coordinator.cli import run_coordinator
                run_coordinator(workspace=ws, max_turns=5, reset=False, verbose=False,
                                display=display)
                mock_factory.assert_not_called()

    def test_passed_display_close_is_called(self):
        ws = _make_workspace(_HANDOFF_PLAN_COMPLETE)
        display = _mock_display()

        base_patches = _common_patches()
        with _apply_patches(base_patches):
            with patch("agent_coordinator.infrastructure.tui.create_display"):
                from agent_coordinator.cli import run_coordinator
                run_coordinator(workspace=ws, max_turns=5, reset=False, verbose=False,
                                display=display)

        display.close.assert_called_once()


# ── Utility ────────────────────────────────────────────────────────────────────

class _PatchStack:
    """Context manager that enters a list of patch() objects and exposes their mocks."""

    def __init__(self, patches):
        self._patches = patches
        self._mocks: list = []

    def __enter__(self):
        for p in self._patches:
            self._mocks.append(p.__enter__())
        return self._mocks

    def __exit__(self, *args):
        for p in reversed(self._patches):
            p.__exit__(*args)


def _apply_patches(patches) -> "_PatchStack":
    return _PatchStack(patches)


if __name__ == "__main__":
    unittest.main()
