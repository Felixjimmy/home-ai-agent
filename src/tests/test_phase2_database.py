"""PostgreSQL-backed confirmation tests; skipped when the local DB is offline."""

import unittest
from uuid import uuid4

from app.database import check_database, create_pending_action, database_connection, ensure_phase2_tables


@unittest.skipUnless(check_database(), "local PostgreSQL is unavailable")
class DatabaseConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_phase2_tables()

    def test_write_waits_for_confirmation_and_replays_idempotently(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        marker = f"phase2-test-{uuid4()}"
        shopping_action_id = str(uuid4())
        reject_action_id = str(uuid4())
        calendar_action_id = str(uuid4())
        device_action_id = str(uuid4())
        room_name = f"Phase2 Test Room {uuid4()}"
        device_name = "Test Lamp"
        room_id = None
        calendar_event_id = None
        shopping_item_id = None
        tool_log_ids: list[int] = []

        with database_connection() as connection:
            room = connection.execute(
                "INSERT INTO rooms (name) VALUES (%s) RETURNING id", (room_name,)
            ).fetchone()
            room_id = room["id"]
            connection.execute(
                "INSERT INTO devices (room_id, name, type, state) VALUES (%s,%s,'light','{\"state\":\"before\"}')",
                (room_id, device_name),
            )

        create_pending_action(shopping_action_id, "add_to_shopping_list", {
            "item": marker, "quantity": 2, "unit": "item",
        })
        create_pending_action(reject_action_id, "add_to_shopping_list", {
            "item": marker + "-rejected", "quantity": 1, "unit": "item",
        })
        create_pending_action(calendar_action_id, "add_calendar_event", {
            "title": marker, "date_text": "tomorrow", "time_text": "3 pm", "participants": [],
        })
        create_pending_action(device_action_id, "set_device_state", {
            "room": room_name, "device": device_name, "state": "after-confirmation",
        })

        try:
            with TestClient(app) as client:
                with database_connection() as connection:
                    count_before = connection.execute(
                        "SELECT count(*) AS n FROM shopping_list_items WHERE name = %s",
                        (marker + "-rejected",),
                    ).fetchone()["n"]
                self.assertEqual(count_before, 0)
                before = client.post(f"/actions/{shopping_action_id}/decision", json={"confirm": False})
                self.assertEqual(before.status_code, 200)
                self.assertEqual(before.json()["status"], "rejected")
                with database_connection() as connection:
                    count = connection.execute(
                        "SELECT count(*) AS n FROM shopping_list_items WHERE name = %s",
                        (marker,),
                    ).fetchone()["n"]
                self.assertEqual(count, 0)

                confirmed = client.post(f"/actions/{reject_action_id}/decision", json={"confirm": True})
                self.assertEqual(confirmed.status_code, 200, confirmed.text)
                shopping_item_id = confirmed.json()["result"]["id"]
                repeated = client.post(f"/actions/{reject_action_id}/decision", json={"confirm": True})
                self.assertTrue(repeated.json()["already_completed"])

                event_result = client.post(f"/actions/{calendar_action_id}/decision", json={"confirm": True})
                self.assertEqual(event_result.status_code, 200, event_result.text)
                calendar_event_id = event_result.json()["result"]["id"]

                state_result = client.post(f"/actions/{device_action_id}/decision", json={"confirm": True})
                self.assertEqual(state_result.status_code, 200, state_result.text)
                with database_connection() as connection:
                    state = connection.execute(
                        "SELECT state FROM devices WHERE room_id = %s AND name = %s",
                        (room_id, device_name),
                    ).fetchone()["state"]
                    self.assertEqual(state, "after-confirmation")
                    tool_log_ids = [row["id"] for row in connection.execute(
                        "SELECT id FROM tool_call_logs WHERE arguments->>'item' LIKE %s OR arguments->>'title' = %s OR arguments->>'room' = %s",
                        (marker + "%", marker, room_name),
                    ).fetchall()]
        finally:
            with database_connection() as connection:
                if shopping_item_id is not None:
                    connection.execute("DELETE FROM shopping_list_items WHERE id = %s", (shopping_item_id,))
                if calendar_event_id is not None:
                    connection.execute("DELETE FROM calendar_events WHERE id = %s", (calendar_event_id,))
                if room_id is not None:
                    connection.execute("DELETE FROM devices WHERE room_id = %s", (room_id,))
                    connection.execute("DELETE FROM rooms WHERE id = %s", (room_id,))
                connection.execute(
                    "DELETE FROM pending_actions WHERE id = ANY(%s)",
                    ([shopping_action_id, reject_action_id, calendar_action_id, device_action_id],),
                )
                if tool_log_ids:
                    connection.execute("DELETE FROM tool_call_logs WHERE id = ANY(%s)", (tool_log_ids,))

    def test_rest_crud_for_every_household_entity_is_confirmation_gated(self) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        token = str(uuid4())
        room_name = f"CRUD Room {token}"
        family_name = f"CRUD Person {token}"
        inventory_name = f"CRUD Inventory {token}"
        shopping_name = f"CRUD Shopping {token}"
        preference_key = f"crud.preference.{token}"
        identifiers: dict[str, int] = {}
        pending_ids: list[str] = []

        with TestClient(app) as client:
            def create(entity: str, data: dict) -> int:
                response = client.post(f"/data/{entity}", json={"data": data})
                self.assertEqual(response.status_code, 202, response.text)
                proposal = response.json()
                pending_ids.append(proposal["id"])
                # The proposal has not changed the target table yet.
                if entity == "rooms":
                    with database_connection() as connection:
                        self.assertIsNone(connection.execute("SELECT 1 FROM rooms WHERE name=%s", (data["name"],)).fetchone())
                result = client.post(f"/actions/{proposal['id']}/decision", json={"confirm": True})
                self.assertEqual(result.status_code, 200, result.text)
                return result.json()["result"]["record"]["id"]

            def update(entity: str, record_id: int, data: dict) -> None:
                response = client.patch(f"/data/{entity}/{record_id}", json={"data": data})
                self.assertEqual(response.status_code, 202, response.text)
                proposal_id = response.json()["id"]
                pending_ids.append(proposal_id)
                result = client.post(f"/actions/{proposal_id}/decision", json={"confirm": True})
                self.assertEqual(result.status_code, 200, result.text)

            def delete(entity: str, record_id: int) -> None:
                response = client.delete(f"/data/{entity}/{record_id}")
                self.assertEqual(response.status_code, 202, response.text)
                proposal_id = response.json()["id"]
                pending_ids.append(proposal_id)
                result = client.post(f"/actions/{proposal_id}/decision", json={"confirm": True})
                self.assertEqual(result.status_code, 200, result.text)

            try:
                identifiers["rooms"] = create("rooms", {"name": room_name})
                identifiers["family_members"] = create("family_members", {"name": family_name})
                identifiers["devices"] = create("devices", {
                    "room_id": identifiers["rooms"], "name": "CRUD Lamp", "type": "light", "state": {"on": False},
                })
                identifiers["inventory_items"] = create("inventory_items", {"name": inventory_name, "quantity": 4})
                identifiers["shopping_list_items"] = create("shopping_list_items", {"name": shopping_name, "quantity": 2})
                identifiers["preferences"] = create("preferences", {"key": preference_key, "value": {"theme": "dark"}})
                identifiers["calendar_events"] = create("calendar_events", {
                    "title": f"CRUD Event {token}", "start_time": "2030-05-10T10:00:00+01:00",
                    "participants": [family_name],
                })

                for entity, record_id in identifiers.items():
                    self.assertEqual(client.get(f"/data/{entity}/{record_id}").status_code, 200)
                    self.assertEqual(client.get(f"/data/{entity}?limit=2").status_code, 200)

                update("rooms", identifiers["rooms"], {"name": room_name + " Updated"})
                update("devices", identifiers["devices"], {"state": {"on": True}})
                update("inventory_items", identifiers["inventory_items"], {"quantity": 3})
                update("shopping_list_items", identifiers["shopping_list_items"], {"is_complete": True})
                update("family_members", identifiers["family_members"], {"preferences": {"quiet": True}})
                update("preferences", identifiers["preferences"], {"value": {"theme": "light"}})
                update("calendar_events", identifiers["calendar_events"], {"title": f"Updated {token}"})

                delete("calendar_events", identifiers["calendar_events"])
                # A referenced room cannot be deleted while its device exists.
                blocked_room_delete = client.delete(f"/data/rooms/{identifiers['rooms']}")
                self.assertEqual(blocked_room_delete.status_code, 409, blocked_room_delete.text)
                delete("devices", identifiers["devices"])
                delete("rooms", identifiers["rooms"])
                for entity in ("inventory_items", "family_members", "preferences", "shopping_list_items"):
                    delete(entity, identifiers[entity])
            finally:
                with database_connection() as connection:
                    # Defensive cleanup also covers a failed assertion halfway through.
                    if "calendar_events" in identifiers:
                        connection.execute("DELETE FROM calendar_events WHERE id=%s", (identifiers["calendar_events"],))
                    if "devices" in identifiers:
                        connection.execute("DELETE FROM devices WHERE id=%s", (identifiers["devices"],))
                    for entity in ("rooms", "inventory_items", "family_members", "preferences", "shopping_list_items"):
                        if entity in identifiers:
                            connection.execute(f"DELETE FROM {entity} WHERE id=%s", (identifiers[entity],))
                    if pending_ids:
                        connection.execute("DELETE FROM pending_actions WHERE id = ANY(%s)", (pending_ids,))


if __name__ == "__main__":
    unittest.main()
