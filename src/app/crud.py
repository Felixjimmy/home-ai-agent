"""Allowlisted CRUD services for user-managed household database records."""

from datetime import datetime
from typing import Any, Literal

import psycopg
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator
from psycopg import sql
from psycopg.types.json import Jsonb

from app.database import json_safe

Entity = Literal[
    "rooms",
    "devices",
    "inventory_items",
    "calendar_events",
    "family_members",
    "preferences",
    "shopping_list_items",
]


class CrudError(ValueError):
    pass


class CrudNotFound(CrudError):
    pass


class CrudConflict(CrudError):
    pass


class RecordData(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoomRecord(RecordData):
    name: str = Field(min_length=1, max_length=120)


class DeviceRecord(RecordData):
    room_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=80)
    state: Any = Field(default_factory=dict)


class InventoryRecord(RecordData):
    name: str = Field(min_length=1, max_length=160)
    quantity: float = Field(default=0, ge=0)
    unit: str = Field(default="item", min_length=1, max_length=40)
    low_stock_threshold: float = Field(default=0, ge=0)


class CalendarRecord(RecordData):
    title: str = Field(min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime | None = None
    participants: list[str] = Field(default_factory=list)

    @field_validator("start_time", "end_time")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Calendar times must include a timezone offset.")
        return value

    @model_validator(mode="after")
    def validate_event_range(self) -> "CalendarRecord":
        if self.end_time is not None and self.end_time < self.start_time:
            raise ValueError("Event end_time must be at or after start_time.")
        return self


class FamilyRecord(RecordData):
    name: str = Field(min_length=1, max_length=120)
    preferences: dict[str, Any] = Field(default_factory=dict)


class PreferenceRecord(RecordData):
    key: str = Field(min_length=1, max_length=160)
    value: Any


class ShoppingItemRecord(RecordData):
    name: str = Field(min_length=1, max_length=160)
    quantity: float = Field(default=1, gt=0)
    unit: str = Field(default="item", min_length=1, max_length=40)
    is_complete: bool = False


_RECORD_MODELS: dict[str, type[RecordData]] = {
    "rooms": RoomRecord,
    "devices": DeviceRecord,
    "inventory_items": InventoryRecord,
    "calendar_events": CalendarRecord,
    "family_members": FamilyRecord,
    "preferences": PreferenceRecord,
    "shopping_list_items": ShoppingItemRecord,
}
_TABLES = set(_RECORD_MODELS)
_UPDATED_AT = {"devices", "inventory_items", "preferences"}
_JSON_COLUMNS = {
    ("devices", "state"),
    ("family_members", "preferences"),
    ("preferences", "value"),
}


class ListRecordsArgs(RecordData):
    entity: Entity
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class GetRecordArgs(RecordData):
    entity: Entity
    record_id: int = Field(gt=0)


class CreateRecordArgs(RecordData):
    entity: Entity
    data: dict[str, Any]


class UpdateRecordArgs(RecordData):
    entity: Entity
    record_id: int = Field(gt=0)
    data: dict[str, Any]


class DeleteRecordArgs(RecordData):
    entity: Entity
    record_id: int = Field(gt=0)


def validate_data(entity: str, data: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    model = _RECORD_MODELS.get(entity)
    if model is None:
        raise CrudError(f"CRUD is not enabled for entity '{entity}'.")
    if not isinstance(data, dict) or not data:
        raise CrudError("Record data must be a non-empty JSON object.")
    if not partial:
        return model.model_validate(data).model_dump(mode="json", exclude_unset=True)

    fields = model.model_fields
    unknown = set(data) - set(fields)
    if unknown:
        raise CrudError(f"Fields cannot be updated: {', '.join(sorted(unknown))}.")
    validated = {}
    for name, value in data.items():
        validated[name] = TypeAdapter(fields[name].annotation).validate_python(value)
    # Run model-level validation on the complete record at the update boundary
    # after applying the patch to the existing row (in apply_crud_action).
    return validated


def _table(entity: str) -> sql.Identifier:
    if entity not in _TABLES:
        raise CrudError(f"CRUD is not enabled for entity '{entity}'.")
    return sql.Identifier(entity)


def list_records(connection: psycopg.Connection, args: ListRecordsArgs) -> dict[str, Any]:
    rows = connection.execute(
        sql.SQL("SELECT * FROM {} ORDER BY id LIMIT %s OFFSET %s").format(_table(args.entity)),
        (args.limit, args.offset),
    ).fetchall()
    return {"entity": args.entity, "items": [json_safe(dict(row)) for row in rows], "limit": args.limit, "offset": args.offset}


def get_record(connection: psycopg.Connection, args: GetRecordArgs) -> dict[str, Any]:
    row = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE id = %s").format(_table(args.entity)),
        (args.record_id,),
    ).fetchone()
    if row is None:
        raise CrudNotFound(f"No {args.entity} record exists with id {args.record_id}.")
    return {"entity": args.entity, "record": json_safe(dict(row))}


def _select_for_update(connection: psycopg.Connection, entity: str, record_id: int) -> dict[str, Any]:
    row = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE id = %s FOR UPDATE").format(_table(entity)),
        (record_id,),
    ).fetchone()
    if row is None:
        raise CrudNotFound(f"No {entity} record exists with id {record_id}.")
    return dict(row)


def _record_fields(entity: str, record: dict[str, Any]) -> dict[str, Any]:
    fields = _RECORD_MODELS[entity].model_fields
    return {name: value for name, value in record.items() if name in fields}


def _db_value(entity: str, column: str, value: Any) -> Any:
    return Jsonb(value) if (entity, column) in _JSON_COLUMNS else value


def _canonicalize_participants(connection: psycopg.Connection, data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    if "participants" in normalized:
        canonical = []
        for participant in normalized["participants"]:
            row = connection.execute(
                "SELECT name FROM family_members WHERE lower(name) = lower(%s)", (participant.strip(),)
            ).fetchone()
            if row is None:
                raise CrudNotFound(f"No family member matches participant '{participant}'.")
            canonical.append(row["name"])
        normalized["participants"] = canonical
    return normalized


def validate_action(tool_name: str, raw_arguments: Any) -> dict[str, Any]:
    if tool_name == "crud_create_record":
        args = CreateRecordArgs.model_validate(raw_arguments)
        return {"entity": args.entity, "data": validate_data(args.entity, args.data)}
    if tool_name == "crud_update_record":
        args = UpdateRecordArgs.model_validate(raw_arguments)
        return {"entity": args.entity, "record_id": args.record_id, "data": validate_data(args.entity, args.data, partial=True)}
    if tool_name == "crud_delete_record":
        return DeleteRecordArgs.model_validate(raw_arguments).model_dump(mode="json")
    raise CrudError(f"Unknown CRUD operation '{tool_name}'.")


def preflight_action(connection: psycopg.Connection, tool_name: str, arguments: dict[str, Any]) -> None:
    validated = validate_action(tool_name, arguments)
    if validated["entity"] == "devices" and tool_name in {"crud_create_record", "crud_update_record"}:
        device_data = validated["data"]
        room_id = device_data.get("room_id")
        if room_id is not None:
            room = connection.execute("SELECT 1 FROM rooms WHERE id = %s", (room_id,)).fetchone()
            if room is None:
                raise CrudNotFound(f"No rooms record exists with id {room_id}.")
    if validated["entity"] == "calendar_events" and tool_name in {"crud_create_record", "crud_update_record"}:
        record = validated["data"]
        if tool_name == "crud_update_record":
            current = _select_for_update(connection, validated["entity"], validated["record_id"])
            record = {**_record_fields(validated["entity"], current), **record}
        for participant in record.get("participants", []):
            found = connection.execute(
                "SELECT 1 FROM family_members WHERE lower(name) = lower(%s)", (participant.strip(),)
            ).fetchone()
            if found is None:
                raise CrudNotFound(f"No family member matches participant '{participant}'.")
    if tool_name in {"crud_update_record", "crud_delete_record"}:
        record = _select_for_update(connection, validated["entity"], validated["record_id"])
        if tool_name == "crud_update_record":
            model = _RECORD_MODELS[validated["entity"]]
            model.model_validate({**_record_fields(validated["entity"], record), **validated["data"]})
        if tool_name == "crud_delete_record":
            _check_delete_constraints(connection, validated["entity"], record)


def _check_delete_constraints(connection: psycopg.Connection, entity: str, record: dict[str, Any]) -> None:
    if entity == "rooms":
        used = connection.execute("SELECT 1 FROM devices WHERE room_id = %s LIMIT 1", (record["id"],)).fetchone()
        if used:
            raise CrudConflict("This room contains devices. Move or delete them before deleting the room.")
    if entity == "family_members":
        used = connection.execute(
            "SELECT 1 FROM calendar_events WHERE %s = ANY(participants) LIMIT 1",
            (record["name"],),
        ).fetchone()
        if used:
            raise CrudConflict("This family member is named in a calendar event and cannot be deleted yet.")


def apply_crud_action(connection: psycopg.Connection, tool_name: str, raw_arguments: Any) -> dict[str, Any]:
    arguments = validate_action(tool_name, raw_arguments)
    operation = tool_name.removeprefix("crud_").removesuffix("_record")
    entity = arguments["entity"]
    table = _table(entity)

    if operation == "create":
        data = validate_data(entity, arguments["data"])
        if entity == "calendar_events":
            data = _canonicalize_participants(connection, data)
        columns = list(data)
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
            table,
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        row = connection.execute(query, [_db_value(entity, column, data[column]) for column in columns]).fetchone()
        return {"status": "created", "entity": entity, "record": json_safe(dict(row))}

    record_id = arguments["record_id"]
    current = _select_for_update(connection, entity, record_id)
    if operation == "update":
        data = validate_data(entity, arguments["data"], partial=True)
        if entity == "calendar_events":
            data = _canonicalize_participants(connection, data)
        _RECORD_MODELS[entity].model_validate({**_record_fields(entity, current), **data})
        # Only fields explicitly supplied by the caller are changed.
        columns = list(data)
        assignments = [sql.SQL("{} = %s").format(sql.Identifier(column)) for column in columns]
        values = [_db_value(entity, column, data[column]) for column in columns]
        if entity in _UPDATED_AT:
            assignments.append(sql.SQL("updated_at = NOW()"))
        row = connection.execute(
            sql.SQL("UPDATE {} SET {} WHERE id = %s RETURNING *").format(table, sql.SQL(", ").join(assignments)),
            [*values, record_id],
        ).fetchone()
        return {"status": "updated", "entity": entity, "record": json_safe(dict(row))}

    if operation == "delete":
        _check_delete_constraints(connection, entity, current)
        row = connection.execute(
            sql.SQL("DELETE FROM {} WHERE id = %s RETURNING *").format(table),
            (record_id,),
        ).fetchone()
        return {"status": "deleted", "entity": entity, "record": json_safe(dict(row))}
    raise CrudError(f"Unknown CRUD operation '{tool_name}'.")


def describe_action(tool_name: str, args: dict[str, Any]) -> str:
    entity = args["entity"]
    if tool_name == "crud_create_record":
        return f"Create a {entity} record"
    if tool_name == "crud_update_record":
        return f"Update {entity} record {args['record_id']}"
    return f"Delete {entity} record {args['record_id']}"


def validate_read_args(tool_name: str, raw_arguments: Any) -> dict[str, Any]:
    model = ListRecordsArgs if tool_name == "crud_list_records" else GetRecordArgs
    return model.model_validate(raw_arguments).model_dump(mode="json")
