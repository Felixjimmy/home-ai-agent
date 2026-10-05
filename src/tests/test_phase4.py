import unittest

from app.memory import _memory_payload, context_for_session, memory_description


class Phase4MemoryUnitTests(unittest.TestCase):
    def test_memory_save_payload_is_confirmation_described(self):
        payload = _memory_payload("save", {
            "key": "thermostat_winter_temperature",
            "value": {"temperature_c": 21},
            "display_text": "The family prefers 21°C in winter.",
        })
        self.assertEqual(payload["arguments"]["value"]["temperature_c"], 21)
        self.assertIn("Remember:", payload["description"])

    def test_memory_operations_have_clear_descriptions(self):
        self.assertEqual(memory_description("forget", {"memory_id": "abc"}), "Forget memory abc")
        self.assertIn("Update memory", memory_description("update", {"memory_id": "abc", "display_text": "new"}))

    def test_missing_session_is_a_new_empty_context(self):
        messages, refs, summary = context_for_session(None)
        self.assertEqual(messages, [])
        self.assertEqual(refs, [])
        self.assertIsNone(summary)


if __name__ == "__main__":
    unittest.main()
