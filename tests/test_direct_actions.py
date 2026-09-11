"""Tests for the DirectActionExecutor fast path (mocked tools)."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from jarvis.actions.direct import DirectActionExecutor
from jarvis.intent import ActionIntent, IntentType
from jarvis.models import ToolResult
from jarvis.research.workflow import ResearchOutcome, ResearchWorkflow


def _tool_result(success=True, verified=True, output=None, error=None, method="mock"):
    return ToolResult(
        success=success, verified=verified,
        output=output or {}, error=error,
        duration_ms=1, verification_method=method,
    )


def _intent(kind, **kw):
    base = dict(intent=kind, confidence=1.0, goal="goal", raw="raw request")
    base.update(kw)
    return ActionIntent(**base)


class DirectActionExecutorTests(unittest.TestCase):
    def _executor(self) -> DirectActionExecutor:
        computer = Mock()
        browser = Mock()
        vision = Mock()
        discovery = Mock()
        discovery.resolve_for_intent.return_value = None
        workflow = Mock()
        executor = DirectActionExecutor(computer, browser, vision, discovery, workflow=workflow)
        return executor, computer, browser, vision, workflow

    def _executor_with_terminal(self, terminal: Mock) -> DirectActionExecutor:
        computer, browser, vision, discovery = Mock(), Mock(), Mock(), Mock()
        workflow = Mock()
        return DirectActionExecutor(computer, browser, vision, discovery, workflow=workflow,
                                    terminal=terminal)

    def test_open_application(self) -> None:
        executor, computer, *_ = self._executor()
        computer.open_app.return_value = _tool_result(output={"message": "Notepad is now open."})
        result = executor.execute(_intent(IntentType.OPEN_APPLICATION, app="notepad"))
        self.assertTrue(result.verified)
        self.assertIn("Notepad", result.message)
        computer.open_app.assert_called_once_with("notepad")

    def test_open_application_failure_is_honest(self) -> None:
        executor, computer, *_ = self._executor()
        computer.open_app.return_value = _tool_result(False, False, error="no process found")
        result = executor.execute(_intent(IntentType.OPEN_APPLICATION, app="notepad"))
        self.assertFalse(result.success)
        self.assertFalse(result.verified)
        self.assertIn("no process", result.message)

    def test_open_url(self) -> None:
        executor, _, browser, *_ = self._executor()
        with patch("jarvis.actions.direct.webbrowser.open", return_value=True) as open_url:
            result = executor.execute(_intent(IntentType.OPEN_URL, url="https://github.com"))
        self.assertTrue(result.verified)
        open_url.assert_called_once_with("https://github.com", new=2)
        self.assertNotIn("github.com", result.message)  # link never revealed in reply

    def test_site_search(self) -> None:
        executor, _, _, _, workflow = self._executor()
        workflow.registry.match.return_value = Mock(id="youtube", name="YouTube", domain="youtube.com")
        workflow.registry.build_search_url.return_value = "https://www.youtube.com/results?search_query=x"
        with patch("jarvis.actions.direct.webbrowser.open", return_value=True) as open_url:
            result = executor.execute(_intent(IntentType.SITE_SEARCH, destination="youtube", query="blender"))
        self.assertTrue(result.verified)
        self.assertIn("YouTube", result.message)
        open_url.assert_called_once_with("https://www.youtube.com/results?search_query=x", new=2)

    def test_open_falls_back_to_chrome_active_profile(self) -> None:
        executor, *_ = self._executor()
        with patch("jarvis.actions.direct.webbrowser.open", return_value=False), \
             patch("jarvis.actions.direct.find_chrome", return_value=r"C:\Program Files\Google\Chrome\Application\chrome.exe"), \
             patch("jarvis.actions.direct.subprocess.Popen") as popen:
            result = executor.execute(_intent(IntentType.OPEN_URL, url="https://github.com"))
        self.assertTrue(result.verified)
        popen.assert_called_once_with(
            [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "https://github.com"])
        self.assertIn("Chrome", result.message)
        self.assertNotIn("github.com", result.message)  # link never revealed in reply

    def test_open_no_browser_and_no_chrome_is_honest(self) -> None:
        executor, *_ = self._executor()
        with patch("jarvis.actions.direct.webbrowser.open", return_value=False), \
             patch("jarvis.actions.direct.find_chrome", return_value=None):
            result = executor.execute(_intent(IntentType.OPEN_URL, url="https://github.com"))
        self.assertFalse(result.success)
        self.assertFalse(result.verified)

    def test_research(self) -> None:
        executor, _, _, _, workflow = self._executor()
        outcome = ResearchOutcome(goal="g", site="youtube", opened_url="https://youtu.be/x", verified=True,
                                  message="Opened a result on YouTube — verified.")
        workflow.research.return_value = outcome
        result = executor.execute(_intent(IntentType.RESEARCH_AND_OPEN, destination="youtube", query="q"))
        self.assertTrue(result.verified)
        self.assertIn("YouTube", result.message)
        self.assertEqual(result.data["opened_url"], "https://youtu.be/x")

    def test_research_failure(self) -> None:
        executor, _, _, _, workflow = self._executor()
        outcome = ResearchOutcome(goal="g", site="youtube", error="No results found.")
        workflow.research.return_value = outcome
        result = executor.execute(_intent(IntentType.RESEARCH))
        self.assertFalse(result.success)

    def test_screen_query(self) -> None:
        executor, _, _, vision, _ = self._executor()
        vision.analyze.return_value = "A dark IDE with main.py open."
        result = executor.execute(_intent(IntentType.SCREEN_QUERY, query="what's open"))
        self.assertTrue(result.verified)
        self.assertIn("IDE", result.message)

    def test_open_file(self) -> None:
        executor, *_ = self._executor()
        with unittest.mock.patch("os.path.isfile", return_value=True), \
             unittest.mock.patch("os.startfile") as startfile:
            result = executor.execute(_intent(IntentType.OPEN_FILE, path="C:\\x\\notes.txt"))
        startfile.assert_called_once()
        self.assertTrue(result.verified)

    def test_open_missing_file_is_honest(self) -> None:
        executor, *_ = self._executor()
        with unittest.mock.patch("os.path.isfile", return_value=False):
            result = executor.execute(_intent(IntentType.OPEN_FILE, path="C:\\x\\missing.txt"))
        self.assertFalse(result.success)
        self.assertIn("not found", result.message)

    def test_create_note(self) -> None:
        executor, computer, *_ = self._executor()
        computer.open_app.return_value = _tool_result()
        computer.type_text.return_value = _tool_result(output={"message": "typed"})
        computer.active_window_title.return_value = "Notepad"
        result = executor.execute(_intent(IntentType.CREATE_NOTE, goal="Explain fusion"))
        self.assertTrue(result.verified)
        self.assertIn("Notepad", result.message)

    def test_terminal_exec_runs_shell_command(self) -> None:
        terminal = Mock()
        terminal.execute.return_value = _tool_result(
            output={"stdout": "hello from jarvis", "stderr": "", "returncode": 0},
            method="terminal_exit_code",
        )
        executor = self._executor_with_terminal(terminal)
        result = executor.execute(_intent(
            IntentType.TERMINAL_EXEC, goal="echo hello",
            constraints={"command": "echo hello"},
        ))
        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertIn("hello from jarvis", result.message)
        terminal.execute.assert_called_once()

    def test_terminal_exec_python_snippet(self) -> None:
        terminal = Mock()
        terminal.execute.return_value = _tool_result(
            output={"stdout": "42\n", "stderr": "", "returncode": 0},
            method="terminal_exit_code",
        )
        executor = self._executor_with_terminal(terminal)
        result = executor.execute(_intent(
            IntentType.TERMINAL_EXEC, goal="print(6 * 7)",
            constraints={"command": "print(6 * 7)"},
        ))
        self.assertTrue(result.success)
        self.assertIn("42", result.message)
        command_used = terminal.execute.call_args.args[0]
        self.assertTrue(command_used.startswith("python "))  # temp script, not inline
        self.assertNotIn("print(6 * 7)", command_used)

    def test_terminal_exec_failure_is_honest(self) -> None:
        terminal = Mock()
        terminal.execute.return_value = _tool_result(
            False, False,
            output={"stdout": "", "stderr": "'dir' is not recognized", "returncode": 1},
            error="Command exited with code 1.", method="terminal_exit_code",
        )
        executor = self._executor_with_terminal(terminal)
        result = executor.execute(_intent(
            IntentType.TERMINAL_EXEC, goal="dir", constraints={"command": "dir"},
        ))
        self.assertFalse(result.success)
        self.assertFalse(result.verified)
        self.assertIn("is not recognized", result.message)

    def test_terminal_exec_requires_terminal_tool(self) -> None:
        executor, *_ = self._executor()
        result = executor.execute(_intent(
            IntentType.TERMINAL_EXEC, goal="dir", constraints={"command": "dir"},
        ))
        self.assertFalse(result.success)

    def test_unknown_intent(self) -> None:
        executor, *_ = self._executor()
        result = executor.execute(_intent(IntentType.TASK_CONTROL))
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()