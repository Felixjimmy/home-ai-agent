"""Run frozen Phase 5 ReAct cases against an isolated local database.

The evaluator never confirms a proposed write. It rejects any pending action it
created before returning, so each run leaves household data unchanged.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import DB_NAME, OLLAMA_MODEL, OLLAMA_THINK
from app.database import database_connection, json_safe, migrate
from app.evaluation import trace_context
from app.evaluate_regressions import cleanup_request, household_snapshot
from app.main import app
from app.seed_data import main as seed_data

ROOT = Path(__file__).resolve().parents[2]


def initialize_isolated_database() -> None:
    """Install the base schema only when the designated test database is empty."""
    with database_connection() as connection:
        exists = connection.execute("SELECT to_regclass('public.rooms') AS table_name").fetchone()["table_name"]
        if exists is None:
            schema = (ROOT / "src" / "db" / "init.sql").read_text(encoding="utf-8")
            connection.execute(schema)
    migrate()


def load_cases(split: str) -> list[dict]:
    path = ROOT / "results" / "phase-5" / "cases" / f"{split}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_case(client: TestClient, case: dict, agent: str) -> dict:
    before = household_snapshot()
    trace: list[dict] = []
    token = trace_context.set(trace)
    request_id = None
    record = {**case, "trace": trace}
    try:
        response = client.post("/chat", json={"message": case["message"], "temperature": 0, "agent": agent})
        request_id = response.headers.get("X-Request-ID")
        actual = response.json()
        record.update(http_status=response.status_code, request_id=request_id, actual=actual)
        with database_connection() as connection:
            proposals = json_safe(connection.execute(
                "SELECT id,tool_name,status FROM pending_actions WHERE request_id=%s", (request_id,)
            ).fetchall())
        calls = [event["name"] for event in trace if event.get("stage") == "tool"]
        response_text = actual.get("response", "").casefold()
        diagnostics = next((event.get("diagnostics") for event in reversed(trace) if event.get("stage") == "final"), {})
        checks = {
            "http_ok": response.status_code == 200,
            "expected_tools_present": all(tool in calls for tool in case["expected_tools"]),
            "expected_terms_present": all(term.casefold() in response_text for term in case["expected_terms"]),
            "proposal_expectation": bool(proposals) == case["expect_proposal"],
            "no_confirmed_write": all(proposal["status"] != "confirmed" for proposal in proposals),
            "within_iteration_cap": diagnostics.get("iterations", 99) <= 5,
        }
        record.update(proposals=proposals, tool_calls=calls, diagnostics=diagnostics, checks=checks)
    except Exception as error:
        record.update(error=str(error), checks={"exception": False})
    finally:
        trace_context.reset(token)
        record["cleanup_errors"] = cleanup_request(request_id)
        record["household_unchanged"] = before == household_snapshot()
        record["passed"] = all(record["checks"].values()) and record["household_unchanged"]
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "held-out"), default="development")
    parser.add_argument("--agent", choices=("handwritten", "langgraph"), default="handwritten")
    args = parser.parse_args()
    if not DB_NAME.startswith("home_ai_phase5_test_"):
        raise RuntimeError("Set POSTGRES_DB to an isolated database beginning home_ai_phase5_test_.")

    cases = load_cases(args.split)
    run = ROOT / "results" / "phase-5" / f"{args.agent}-{args.split}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    run.mkdir(parents=True, exist_ok=False)
    initialize_isolated_database()
    seed_data()
    results = []
    with TestClient(app, raise_server_exceptions=False) as client:
        for case in cases:
            result = run_case(client, case, args.agent)
            results.append(result)
            (run / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
            print(case["id"], "passed", result["passed"], flush=True)

    source = ROOT / "results" / "phase-5" / "cases" / f"{args.split}.json"
    summary = {
        "split": args.split,
        "count": len(results),
        "passed": sum(result["passed"] for result in results),
        "failures": [result["id"] for result in results if not result["passed"]],
        "model": OLLAMA_MODEL,
        "agent": args.agent,
        "thinking": OLLAMA_THINK,
        "case_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "limitations": [
            "The harness checks tool sequence indicators and required answer terms; review saved traces for semantic quality.",
            "It rejects only proposals created by its own request IDs and must run against an isolated database.",
        ],
    }
    (run / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(run)


if __name__ == "__main__":
    main()
