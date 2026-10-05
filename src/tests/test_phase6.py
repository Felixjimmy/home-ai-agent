"""Phase 6 coordinator safeguards without requiring Ollama or PostgreSQL."""

import unittest
from unittest.mock import patch

from app.multi_agent import RoutePlan, SpecialistTask, run_multi_agent


class Phase6CoordinatorTests(unittest.TestCase):
    def test_routes_two_domains_and_aggregates_pending_proposals(self):
        plan = RoutePlan(tasks=[
            SpecialistTask(specialist="household", request="Check the milk"),
            SpecialistTask(specialist="scheduler", request="Schedule a reminder"),
        ])
        calls = []

        def fake_runner(request, **kwargs):
            calls.append((request, kwargs["allowed_tools"], kwargs["max_tool_calls"]))
            if kwargs["allowed_tools"] == {"add_calendar_event"}:
                return "Reminder proposed.", 1, [{"id": "calendar-1", "tool_name": "add_calendar_event", "description": "Add reminder", "expires_at": "later"}]
            return "Milk is low.", 1, []

        trace = []
        with patch("app.multi_agent.route_request", return_value=plan), patch("app.multi_agent.llm.run_agent", side_effect=fake_runner):
            answer, _, pending = run_multi_agent("Check milk and schedule a reminder", trace=trace)

        self.assertIn("Milk is low", answer)
        self.assertIn("Reminder proposed", answer)
        self.assertIn("Pending explicit confirmation", answer)
        self.assertEqual(len(pending), 1)
        self.assertEqual(calls[0][1], {"get_device_state", "check_inventory", "add_to_shopping_list", "set_device_state", "crud_list_records", "crud_get_record", "crud_create_record", "crud_update_record", "crud_delete_record"})
        self.assertEqual(calls[1][1], {"add_calendar_event"})
        self.assertLessEqual(calls[1][2], 8)

    def test_clarification_does_not_dispatch_a_specialist(self):
        plan = RoutePlan(tasks=[SpecialistTask(specialist="household", request="unused")], needs_clarification=True, clarifying_question="Which device do you mean?")
        with patch("app.multi_agent.route_request", return_value=plan), patch("app.multi_agent.llm.run_agent") as runner:
            answer, _, pending = run_multi_agent("Check it")
        self.assertEqual(answer, "Which device do you mean?")
        self.assertEqual(pending, [])
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
