"""Validated, database-backed tools exposed to the local Ollama model."""

import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

import dateparser
import psycopg
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb

from app.config import EVENT_TIMEZONE
from app import crud
from app.database import database_connection, json_safe


class ToolInputError(ValueError):
    """A tool request cannot safely be fulfilled with the supplied details."""


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceLookup(ToolArguments):
    room: str = Field(min_length=1, description="Room name")
    device: str = Field(min_length=1, description="Device name within that room")


class InventoryLookup(ToolArguments):
    item: str = Field(min_length=1, description="Inventory item name")


class ShoppingListAdd(ToolArguments):
    item: str = Field(min_length=1, description="Item to add")
    quantity: float = Field(default=1, gt=0, le=10000)
    unit: str = Field(default="item", min_length=1, max_length=40)


class CalendarEventAdd(ToolArguments):
    title: str = Field(min_length=1, max_length=200)
    date_text: str = Field(min_length=1, description="Date phrase as stated by the user")
    time_text: str | None = Field(default=None, description="Time phrase as stated by the user")
    participants: list[str] = Field(default_factory=list)


class DeviceStateSet(ToolArguments):
    room: str = Field(min_length=1)
    device: str = Field(min_length=1)
    state: str = Field(min_length=1, max_length=100)


def _device_state(connection: psycopg.Connection, args: DeviceLookup) -> dict[str, Any]:
    matches = _matching_devices(connection, args)
    if not matches:
        return {"found": False, "message": "No matching device was found. Ask the user to clarify the room or device."}
    if len(matches) > 1:
        return {
            "found": False,
            "ambiguous": True,
            "options": [f"{row['device']} in {row['room']}" for row in matches],
            "message": "More than one device matched. Ask the user which one they mean.",
        }
    return {"found": True, **matches[0]}


def _matching_devices(connection: psycopg.Connection, args: DeviceLookup) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT d.id, r.name AS room, d.name AS device, d.type, d.state
           FROM devices d JOIN rooms r ON r.id = d.room_id"""
    ).fetchall()
    room_terms = set(re.findall(r"[a-z0-9]+", args.room.casefold()))
    device_terms = set(re.findall(r"[a-z0-9]+", args.device.casefold()))
    matches = []
    for row in rows:
        candidate_room_terms = set(re.findall(r"[a-z0-9]+", row["room"].casefold()))
        candidate_device_terms = set(re.findall(r"[a-z0-9]+", f"{row['device']} {row['type']}".casefold()))
        # A model may add a harmless room qualifier (for example, "Front Hall")
        # while naming the device exactly. Require the device terms plus at least
        # one room term; do not match a room qualifier by itself.
        direct_match = device_terms and device_terms.issubset(candidate_device_terms) and room_terms.intersection(candidate_room_terms)
        # Some models split a compound device name across both arguments, such
        # as room="front door", device="lock". Accept it only when every term
        # from both fields identifies the same stored device.
        compound_device_match = (
            device_terms
            and device_terms.issubset(candidate_device_terms)
            and room_terms.issubset(candidate_device_terms)
        )
        if direct_match or compound_device_match:
            matches.append(dict(row))
    return matches


def _check_inventory(connection: psycopg.Connection, args: InventoryLookup) -> dict[str, Any]:
    row = connection.execute(
        """SELECT name, quantity, unit, low_stock_threshold,
                  quantity <= low_stock_threshold AS low_stock
           FROM inventory_items WHERE lower(name) = lower(%s)""",
        (args.item.strip(),),
    ).fetchone()
    return {"found": True, **row} if row else {"found": False, "message": "No matching inventory item was found."}


def _add_shopping_item(connection: psycopg.Connection, args: ShoppingListAdd) -> dict[str, Any]:
    row = connection.execute(
        """INSERT INTO shopping_list_items (name, quantity, unit)
           VALUES (%s, %s, %s) RETURNING id, name, quantity, unit, created_at""",
        (args.item.strip(), args.quantity, args.unit.strip()),
    ).fetchone()
    return dict(row)


_BARE_WEEKDAY = re.compile(
    r"^(?:(?:this|next)\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
    re.IGNORECASE,
)
_VAGUE_DATE = re.compile(
    r"^(?:next week|this week|the weekend|next weekend|sometime|soon)$", re.IGNORECASE
)
def resolve_event_datetime(
    date_text: str,
    time_text: str | None,
    reference_date: datetime | None = None,
) -> datetime:
    """Resolve event date and time with an injectable reference date."""
    phrase = date_text.strip()
    if _BARE_WEEKDAY.fullmatch(phrase) or _VAGUE_DATE.fullmatch(phrase):
        raise ToolInputError("Please provide a specific calendar date for the event.")
    if not time_text or not time_text.strip():
        raise ToolInputError("What time should I put this event on the calendar?")

    zone = ZoneInfo(EVENT_TIMEZONE)
    now = reference_date or datetime.now(zone)
    if now.tzinfo is None:
        now = now.replace(tzinfo=zone)
    settings = {
        "RELATIVE_BASE": now,
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": EVENT_TIMEZONE,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "DATE_ORDER": "DMY",
    }
    resolved_date = dateparser.parse(phrase, settings=settings)
    if resolved_date is None:
        raise ToolInputError("I could not resolve that date. Please give a specific date.")

    time_phrase = time_text.strip()
    combined = dateparser.parse(f"{phrase} {time_phrase}", settings=settings)
    if combined is None:
        raise ToolInputError("I could not resolve that time. Please give a time such as 3 pm.")
    resolved = resolved_date.replace(
        hour=combined.hour,
        minute=combined.minute,
        second=0,
        microsecond=0,
        tzinfo=zone,
    )
    wall = resolved.replace(tzinfo=None)
    possibilities = {wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                     for fold in (0, 1)
                     if wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == wall}
    if len(possibilities) != 1:
        raise ToolInputError("That local time is ambiguous or nonexistent because of daylight saving. Choose another time.")
    if resolved < now:
        raise ToolInputError("That date and time is in the past. Please confirm the intended date.")
    return resolved


def _add_calendar_event(connection: psycopg.Connection, args: CalendarEventAdd) -> dict[str, Any]:
    start_time = resolve_event_datetime(args.date_text, args.time_text)
    participants: list[str] = []
    for name in args.participants:
        row = connection.execute(
            "SELECT name FROM family_members WHERE lower(name) = lower(%s)",
            (name.strip(),),
        ).fetchone()
        if row is None:
            raise ToolInputError(f"'{name}' does not match a family member. Ask which person was intended.")
        participants.append(row["name"])
    row = connection.execute(
        """INSERT INTO calendar_events (title, start_time, participants)
           VALUES (%s, %s, %s) RETURNING id, title, start_time, participants""",
        (args.title.strip(), start_time, participants),
    ).fetchone()
    return dict(row)


def _set_device_state(connection: psycopg.Connection, args: DeviceStateSet) -> dict[str, Any]:
    matches = _matching_devices(connection, DeviceLookup(room=args.room, device=args.device))
    if not matches:
        raise ToolInputError("No matching device was found; no state was changed.")
    if len(matches) > 1:
        raise ToolInputError("More than one device matched; ask the user which room/device they mean.")
    row = connection.execute(
        """UPDATE devices SET state = %s, updated_at = NOW() WHERE id = %s
           RETURNING name AS device, state""",
        (Jsonb(args.state.strip()), matches[0]["id"]),
    ).fetchone()
    return {"room": matches[0]["room"], **dict(row)}


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "get_device_state": {"description": "Read one device's reported state in a room.", "arguments": DeviceLookup, "handler": _device_state, "write": False},
    "check_inventory": {"description": "Read the stored quantity and low-stock status of an inventory item.", "arguments": InventoryLookup, "handler": _check_inventory, "write": False},
    "add_to_shopping_list": {"description": "Propose adding an item to the shopping list; this requires user confirmation.", "arguments": ShoppingListAdd, "handler": _add_shopping_item, "write": True},
    "add_calendar_event": {"description": "Propose adding a calendar event; this requires user confirmation. Preserve date and time phrases as stated.", "arguments": CalendarEventAdd, "handler": _add_calendar_event, "write": True},
    "set_device_state": {"description": "Propose changing a simulated device state; this requires user confirmation.", "arguments": DeviceStateSet, "handler": _set_device_state, "write": True},
    "crud_list_records": {"description": "List records of one household data type: rooms, devices, inventory_items, calendar_events, family_members, preferences, or shopping_list_items.", "arguments": crud.ListRecordsArgs, "handler": crud.list_records, "write": False},
    "crud_get_record": {"description": "Read one household record by entity and numeric record_id.", "arguments": crud.GetRecordArgs, "handler": crud.get_record, "write": False},
    "crud_create_record": {"description": "Propose creating one household record. Always requires explicit user confirmation.", "arguments": crud.CreateRecordArgs, "handler": None, "write": True},
    "crud_update_record": {"description": "Propose updating fields on one household record. Always requires explicit user confirmation.", "arguments": crud.UpdateRecordArgs, "handler": None, "write": True},
    "crud_delete_record": {"description": "Propose deleting one household record. Always requires explicit user confirmation.", "arguments": crud.DeleteRecordArgs, "handler": None, "write": True},
}


def ollama_tool_definitions(allowed_names: set[str] | None = None) -> list[dict[str, Any]]:
    from app.document_tools import entries
    TOOL_REGISTRY.update(entries())
    return [
        {"type": "function", "function": {
            "name": name,
            "description": entry["description"],
            "parameters": entry["arguments"].model_json_schema(),
        }}
        for name, entry in TOOL_REGISTRY.items()
        if allowed_names is None or name in allowed_names
    ]


def validate_tool_call(name: str, raw_arguments: Any) -> tuple[dict[str, Any], bool]:
    if name not in TOOL_REGISTRY:
        from app.document_tools import entries
        TOOL_REGISTRY.update(entries())
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        raise ToolInputError(f"Unknown tool: {name}")
    if name.startswith("crud_"):
        if entry["write"]:
            return crud.validate_action(name, raw_arguments), True
        return crud.validate_read_args(name, raw_arguments), False
    validated = entry["arguments"].model_validate(raw_arguments)
    return validated.model_dump(mode="json"), entry["write"]


def execute_read_tool(name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], int]:
    entry = TOOL_REGISTRY[name]
    started = perf_counter()
    with database_connection() as connection:
        result = entry["handler"](connection, entry["arguments"].model_validate(arguments))
    return result, round((perf_counter() - started) * 1000)


def preflight_write_tool(name: str, arguments: dict[str, Any]) -> None:
    """Check required records/date details without performing a write."""
    entry = TOOL_REGISTRY[name]
    args = entry["arguments"].model_validate(arguments)
    with database_connection() as connection:
        if name.startswith("crud_"):
            crud.preflight_action(connection, name, arguments)
        elif name == "add_calendar_event":
            resolve_event_datetime(args.date_text, args.time_text)
            for participant in args.participants:
                match = connection.execute(
                    "SELECT 1 FROM family_members WHERE lower(name) = lower(%s)",
                    (participant.strip(),),
                ).fetchone()
                if match is None:
                    raise ToolInputError(
                        f"'{participant}' does not match a family member. Ask which person was intended."
                    )
        elif name == "set_device_state":
            matches = _matching_devices(connection, DeviceLookup(room=args.room, device=args.device))
            if not matches:
                raise ToolInputError("No matching device was found; no state was changed.")
            if len(matches) > 1:
                raise ToolInputError("More than one device matched; ask the user which room/device they mean.")


def execute_pending_action(action_id: str, confirm: bool) -> dict[str, Any]:
    """Roll back failed mutations before recording an execution failure."""
    try:
        return _execute_pending_action(action_id, confirm)
    except (ValueError, LookupError, psycopg.Error) as error:
        with database_connection() as connection:
            connection.execute("UPDATE pending_actions SET status='failed',completed_at=NOW(),result=%s WHERE id=%s AND status='pending'",(Jsonb({"error": type(error).__name__,"message":"Execution failed; no changes committed. Request a new proposal."}),action_id))
        raise


def _execute_pending_action(action_id: str, confirm: bool) -> dict[str, Any]:
    """Execute or reject one pending action exactly once under a row lock."""
    with database_connection() as connection:
        action = connection.execute(
            "SELECT * FROM pending_actions WHERE id = %s FOR UPDATE", (action_id,)
        ).fetchone()
        if action is None:
            raise LookupError("Pending action was not found.")
        if action["status"] == "confirmed":
            return {"status": "confirmed", "result": action["result"], "already_completed": True}
        if action["status"] == "rejected":
            return {"status": "rejected", "already_completed": True}
        if action["status"] == "failed":
            return {"status": "failed", "result": action["result"], "already_completed": True}
        if action["status"] == "expired":
            return {"status": "expired"}
        expired = connection.execute(
            "SELECT expires_at <= NOW() AS expired FROM pending_actions WHERE id = %s",
            (action_id,),
        ).fetchone()["expired"]
        if expired:
            connection.execute(
                "UPDATE pending_actions SET status = 'expired', completed_at = NOW() WHERE id = %s",
                (action_id,),
            )
            return {"status": "expired"}
        if not confirm:
            connection.execute(
                "UPDATE pending_actions SET status = 'rejected', completed_at = NOW() WHERE id = %s",
                (action_id,),
            )
            connection.execute(
                "INSERT INTO tool_call_logs (tool_name, arguments, outcome, latency_ms) VALUES (%s,%s,%s,0)",
            (action["tool_name"], Jsonb(json_safe(action["arguments"])), Jsonb({"status": "rejected"})),
            )
            return {"status": "rejected"}

        started = perf_counter()
        if action["payload_version"] != 2:
            raise ToolInputError("Legacy proposal: request a new action with stable details.")
        if action["tool_name"].startswith("document_"):
            from app.documents import apply_document_action
            result = apply_document_action(connection, action)
        elif action["tool_name"].startswith("memory_"):
            from app.memory import apply_memory_action
            result = apply_memory_action(connection, action)
        else:
            from app.actions import apply_prepared
            result = apply_prepared(connection,action["tool_name"],action["arguments"])
        elapsed_ms = round((perf_counter() - started) * 1000)
        connection.execute(
            "UPDATE pending_actions SET status = 'confirmed', result = %s, completed_at = NOW() WHERE id = %s",
            (Jsonb(json_safe(result)), action_id),
        )
        connection.execute(
            "INSERT INTO tool_call_logs (tool_name, arguments, outcome, latency_ms) VALUES (%s,%s,%s,%s)",
            (action["tool_name"], Jsonb(json_safe(action["arguments"])), Jsonb(json_safe({"status": "confirmed", "result": result})), elapsed_ms),
        )
        return {"status": "confirmed", "result": result, "already_completed": False}


def confirmation_description(name: str, arguments: dict[str, Any]) -> str:
    if name.startswith("crud_"):
        return crud.describe_action(name, arguments)
    if name == "add_to_shopping_list":
        return f"Add {arguments['quantity']} {arguments['unit']} of {arguments['item']} to the shopping list"
    if name == "add_calendar_event":
        return f"Add calendar event '{arguments['title']}' on {arguments['date_text']} at {arguments['time_text']}"
    if name == "set_device_state":
        return f"Set {arguments['device']} in {arguments['room']} to {arguments['state']}"
    return f"Run {name}"
