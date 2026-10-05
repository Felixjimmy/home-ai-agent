"""Phase 5 ReAct-loop safeguards without requiring Ollama or PostgreSQL."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ollama import Message

from app.llm import MAX_AGENT_ITERATIONS, run_agent


def tool_call(name: str, arguments: dict) -> Message:
    return Message(role="assistant", content="", tool_calls=[{
        "function": {"name": name, "arguments": arguments}
    }])


class Phase5AgentLoopTests(unittest.TestCase):
    def test_duplicate_tool_call_is_refused_and_the_loop_can_finish(self):
        repeated = Message(role="assistant", content="", tool_calls=[
            {"function": {"name": "get_device_state", "arguments": {"room": "hall", "device": "light"}}},
            {"function": {"name": "get_device_state", "arguments": {"room": "hall", "device": "light"}}},
        ])
        final = Message(role="assistant", content="The hall light is off.")
        trace = []
        with patch("app.llm._client.chat", side_effect=[SimpleNamespace(message=repeated), SimpleNamespace(message=final)]), \
             patch("app.llm.execute_read_tool", return_value=({"found": True, "state": "off"}, 1)) as execute, \
             patch("app.llm.log_tool_call"):
            answer, _, proposals = run_agent("Is the hall light on?", trace=trace)
        self.assertEqual(answer, "The hall light is off.")
        self.assertEqual(proposals, [])
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(trace[-1]["diagnostics"]["duplicate_calls"], 1)

    def test_iteration_limit_returns_a_truthful_safe_failure(self):
        call = tool_call("get_device_state", {"room": "hall", "device": "light"})
        trace = []
        with patch("app.llm._client.chat", side_effect=[SimpleNamespace(message=call), SimpleNamespace(message=call)]), \
             patch("app.llm.execute_read_tool", return_value=({"found": True, "state": "off"}, 1)), \
             patch("app.llm.log_tool_call"):
            answer, _, proposals = run_agent("Check the hall light", trace=trace, max_iterations=2)
        self.assertIn("iteration limit", answer)
        self.assertEqual(proposals, [])
        self.assertEqual(trace[-1]["diagnostics"]["stop_reason"], "iteration_limit")

    def test_iteration_limit_cannot_exceed_application_cap(self):
        with self.assertRaises(ValueError):
            run_agent("Hello", max_iterations=MAX_AGENT_ITERATIONS + 1)


if __name__ == "__main__":
    unittest.main()
