"""Fast, database-independent checks for Phase 2 tool contracts."""

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.tools import (
    CalendarEventAdd,
    ToolInputError,
    ollama_tool_definitions,
    resolve_event_datetime,
    validate_tool_call,
)
from app.llm import extract_calendar_event, sanitize_unverified_action_claim
from app import crud


class DateResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = datetime(2026, 10, 4, 10, 0, tzinfo=ZoneInfo("Europe/London"))

    def test_tomorrow_uses_injected_reference_and_timezone(self) -> None:
        resolved = resolve_event_datetime("tomorrow", "3 pm", self.reference)
        self.assertEqual(resolved.isoformat(), "2026-10-05T15:00:00+01:00")

    def test_bare_weekday_requires_clarification(self) -> None:
        with self.assertRaisesRegex(ToolInputError, "specific calendar date"):
            resolve_event_datetime("Friday", "3 pm", self.reference)

    def test_missing_time_requires_clarification(self) -> None:
        with self.assertRaisesRegex(ToolInputError, "What time"):
            resolve_event_datetime("8 October 2026", None, self.reference)

    def test_vague_week_requires_clarification(self) -> None:
        with self.assertRaises(ToolInputError):
            resolve_event_datetime("next week", "3 pm", self.reference)


class ToolContractTests(unittest.TestCase):
    def test_crud_and_phase2_tools_are_exposed(self) -> None:
        definitions = ollama_tool_definitions()
        self.assertEqual(len(definitions), len({d['function']['name'] for d in definitions}))
        self.assertTrue(all(item["type"] == "function" for item in definitions))
        names = {item["function"]["name"] for item in definitions}
        self.assertTrue({"crud_list_records", "crud_get_record", "crud_create_record", "crud_update_record", "crud_delete_record"} <= names)

    def test_every_write_is_marked_for_confirmation(self) -> None:
        writes = {
            "add_to_shopping_list",
            "add_calendar_event",
            "set_device_state",
        }
        for name in writes:
            _, requires_confirmation = validate_tool_call(
                name,
                {"item": "milk"} if name == "add_to_shopping_list" else (
                    {"title": "Dentist", "date_text": "8 October", "time_text": "3 pm", "participants": []}
                    if name == "add_calendar_event"
                    else {"room": "Hall", "device": "Light", "state": "off"}
                ),
            )
            self.assertTrue(requires_confirmation, name)

    def test_crud_write_contracts_are_confirmed_and_internal_tables_are_excluded(self) -> None:
        examples = {
            "crud_create_record": {"entity": "rooms", "data": {"name": "Study"}},
            "crud_update_record": {"entity": "rooms", "record_id": 1, "data": {"name": "Study"}},
            "crud_delete_record": {"entity": "rooms", "record_id": 1},
        }
        for tool_name, arguments in examples.items():
            _, requires_confirmation = validate_tool_call(tool_name, arguments)
            self.assertTrue(requires_confirmation, tool_name)
        for entity in ("pending_actions", "tool_call_logs"):
            with self.assertRaises((crud.CrudError, ValidationError)):
                crud.validate_action("crud_delete_record", {"entity": entity, "record_id": 1})

    def test_crud_records_reject_unknown_fields_and_timezone_free_calendar_time(self) -> None:
        with self.assertRaises((crud.CrudError, ValidationError)):
            crud.validate_action("crud_create_record", {"entity": "rooms", "data": {"name": "Hall", "owner": "Mum"}})
        with self.assertRaises((crud.CrudError, ValidationError)):
            crud.validate_action("crud_create_record", {
                "entity": "calendar_events", "data": {"title": "Visit", "start_time": "2030-01-01T10:00:00"},
            })

    def test_calendar_arguments_reject_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            CalendarEventAdd(title="Visit", date_text="8 October", unexpected="guess")

    def test_unverified_bolt_claim_is_replaced(self) -> None:
        answer = sanitize_unverified_action_claim(
            "Please bolt the back door.",
            "The back door is already bolted.",
            has_pending_action=False,
        )
        self.assertIn("I haven't changed anything", answer)

    def test_valid_pending_proposal_keeps_action_response(self) -> None:
        answer = "The action is pending confirmation."
        self.assertEqual(
            sanitize_unverified_action_claim("Add milk.", answer, has_pending_action=True),
            answer,
        )

    def test_device_status_answer_does_not_offer_an_unrequested_change(self) -> None:
        answer = sanitize_unverified_action_claim(
            "Is the hall light on?",
            "The hall light is off. Would you like me to turn it on?",
            has_pending_action=False,
        )
        self.assertEqual(answer, "The hall light is off.")

    def test_structured_extraction_retries_once_after_invalid_json(self) -> None:
        valid = (
            '{"status":"ready","title":"Plumber visit","date_text":"8 October",'
            '"time_text":null,"participants":[],"location":null,"clarifying_question":null}'
        )
        with patch("app.llm._client.chat") as fake_chat:
            fake_chat.side_effect = [
                SimpleNamespace(message=SimpleNamespace(content="not json")),
                SimpleNamespace(message=SimpleNamespace(content=valid)),
            ]
            event, _ = extract_calendar_event("Schedule a plumber visit on 8 October.", temperature=0)
        self.assertEqual(event.status, "ready")
        self.assertEqual(fake_chat.call_count, 2)


if __name__ == "__main__":
    unittest.main()
