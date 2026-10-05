"""Immutable prepared operations shared by REST and model-proposed writes."""
import json
from uuid import uuid4
from datetime import datetime
from psycopg.types.json import Jsonb
from app.database import database_connection, json_safe, request_id_context
from app import crud


def prepare_action(name: str, arguments: dict) -> dict:
    from app.tools import preflight_write_tool, resolve_event_datetime, _matching_devices, DeviceLookup
    preflight_write_tool(name, arguments)
    payload = {"arguments": json_safe(arguments), "preconditions": []}
    with database_connection() as conn:
        if name == "add_calendar_event":
            payload["start_time"] = resolve_event_datetime(arguments["date_text"],arguments.get("time_text")).isoformat()
            payload["participants"] = []
            for person in arguments.get("participants",[]):
                row = conn.execute("SELECT id,name FROM family_members WHERE lower(name)=lower(%s)",(person.strip(),)).fetchone()
                payload["participants"].append(dict(row))
        if name == "set_device_state":
            matches = _matching_devices(conn,DeviceLookup(room=arguments["room"],device=arguments["device"]))
            if len(matches)!=1:
                raise crud.CrudConflict("Device no longer matches uniquely. Request a new proposal.")
            row = conn.execute("SELECT * FROM devices WHERE id=%s",(matches[0]["id"],)).fetchone()
            payload["preconditions"].append({"entity":"devices","record_id":row["id"],"record":json_safe(row)})
        if name in ("crud_update_record","crud_delete_record"):
            record=crud.get_record(conn,crud.GetRecordArgs(entity=arguments["entity"],record_id=arguments["record_id"]))["record"]
            payload["preconditions"].append({"entity":arguments["entity"],"record_id":arguments["record_id"],"record":record})
        if name.startswith("crud_") and arguments.get("entity")=="calendar_events":
            for person in arguments.get("data",{}).get("participants",[]):
                row=conn.execute("SELECT * FROM family_members WHERE lower(name)=lower(%s)",(person.strip(),)).fetchone()
                payload["preconditions"].append({"entity":"family_members","record_id":row["id"],"record":json_safe(row)})
    return payload


def apply_prepared(conn,name,payload):
    from app.tools import TOOL_REGISTRY
    arguments=payload["arguments"]
    for condition in payload.get("preconditions",[]):
        current=crud._select_for_update(conn,condition["entity"],condition["record_id"])
        if json_safe(current)!=condition["record"]:
            raise crud.CrudConflict("The target changed since this proposal. Request a new proposal.")
    if name=="add_calendar_event":
        names=[]
        for person in payload["participants"]:
            row=conn.execute("SELECT id,name FROM family_members WHERE id=%s FOR SHARE",(person["id"],)).fetchone()
            if row is None or row["name"]!=person["name"]:
                raise crud.CrudConflict("A participant changed. Request a new proposal.")
            names.append(row["name"])
        when=datetime.fromisoformat(payload["start_time"])
        if when < datetime.now(when.tzinfo):
            raise crud.CrudConflict("The proposed event time is now in the past.")
        return dict(conn.execute("INSERT INTO calendar_events(title,start_time,participants) VALUES (%s,%s,%s) RETURNING *",(arguments["title"].strip(),when,names)).fetchone())
    if name=="set_device_state":
        target=payload["preconditions"][0]["record_id"]
        return dict(conn.execute("UPDATE devices SET state=%s,updated_at=NOW() WHERE id=%s RETURNING id,name,state",(Jsonb(arguments["state"].strip()),target)).fetchone())
    if name.startswith("crud_"):
        return crud.apply_crud_action(conn,name,arguments)
    entry=TOOL_REGISTRY[name]
    return entry["handler"](conn,entry["arguments"].model_validate(arguments))


def stage_action(name,arguments,idempotency_key=None):
    from app.tools import confirmation_description
    if idempotency_key:
        with database_connection() as conn:
            old=conn.execute("SELECT * FROM pending_actions WHERE idempotency_key=%s",(idempotency_key,)).fetchone()
        if old:
            if old["tool_name"]!=name or old["arguments"]["arguments"]!=json_safe(arguments):
                raise crud.CrudConflict("Idempotency key belongs to a different request.")
            return proposal_summary(old)
    prepared=prepare_action(name,arguments)
    description=confirmation_description(name,arguments)
    if "start_time" in prepared:
        description=f"Add calendar event '{arguments['title']}' at {prepared['start_time']}; participants: {', '.join(p['name'] for p in prepared['participants']) or 'none'}"
    if prepared.get("preconditions"):
        description += "; targets: " + ", ".join(f"{p['entity']} #{p['record_id']}" for p in prepared["preconditions"])
    prepared["description"]=description
    with database_connection() as conn:
        if idempotency_key:
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(idempotency_key,))
            old=conn.execute("SELECT * FROM pending_actions WHERE idempotency_key=%s",(idempotency_key,)).fetchone()
            if old:
                if old["tool_name"]!=name or old["arguments"]["arguments"]!=json_safe(arguments):
                    raise crud.CrudConflict("Idempotency key belongs to a different request.")
                return proposal_summary(old)
        row=conn.execute("INSERT INTO pending_actions(id,tool_name,arguments,payload_version,request_id,idempotency_key) VALUES (%s,%s,%s,2,%s,%s) RETURNING *",(str(uuid4()),name,Jsonb(json_safe(prepared)),request_id_context.get(),idempotency_key)).fetchone()
    return proposal_summary(row)


def proposal_summary(row):
    return {"id":str(row["id"]),"tool_name":row["tool_name"],"description":row["arguments"].get("description","Review action details"),"expires_at":str(row["expires_at"]),"status":row["status"]}
