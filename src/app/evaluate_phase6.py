"""Run frozen Phase 6 routing cases against an isolated local database."""

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
    with database_connection() as connection:
        exists = connection.execute("SELECT to_regclass('public.rooms') AS table_name").fetchone()["table_name"]
        if exists is None:
            connection.execute((ROOT / "src" / "db" / "init.sql").read_text(encoding="utf-8"))
    migrate()


def run_case(client: TestClient, case: dict) -> dict:
    before = household_snapshot()
    trace: list[dict] = []
    token = trace_context.set(trace)
    request_id = None
    record = {**case, "trace": trace}
    try:
        response = client.post("/chat", json={"message": case["message"], "temperature": 0, "agent": "multi_agent"})
        request_id = response.headers.get("X-Request-ID")
        actual = response.json()
        with database_connection() as connection:
            proposals = json_safe(connection.execute("SELECT id,tool_name,status FROM pending_actions WHERE request_id=%s", (request_id,)).fetchall())
        specialists = [event.get("specialist") for event in trace if event.get("stage") == "specialist"]
        text = actual.get("response", "").casefold()
        checks = {
            "http_ok": response.status_code == 200,
            "specialists_present": all(name in specialists for name in case["expected_specialists"]),
            "terms_present": all(term.casefold() in text for term in case["expected_terms"]),
            "proposal_expectation": bool(proposals) == case["expect_proposal"],
            "no_confirmed_write": all(row["status"] != "confirmed" for row in proposals),
        }
        record.update(actual=actual, specialists=specialists, proposals=proposals, checks=checks)
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
    args = parser.parse_args()
    if not DB_NAME.startswith("home_ai_phase6_test_"):
        raise RuntimeError("Set POSTGRES_DB to an isolated database beginning with home_ai_phase6_test_.")
    source = ROOT / "results" / "phase-6" / "cases" / f"{args.split}.json"
    cases = json.loads(source.read_text(encoding="utf-8"))
    run_dir = ROOT / "results" / "phase-6" / f"multi-agent-{args.split}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=False)
    initialize_isolated_database()
    seed_data()
    with TestClient(app, raise_server_exceptions=False) as client:
        results = [run_case(client, case) for case in cases]
    (run_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    summary = {
        "split": args.split,
        "count": len(results),
        "passed": sum(row["passed"] for row in results),
        "failures": [row["id"] for row in results if not row["passed"]],
        "model": OLLAMA_MODEL,
        "thinking": OLLAMA_THINK,
        "case_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "limitations": ["Small synthetic local set; inspect traces for semantic quality.", "Proposals are cleaned up and never confirmed."],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(run_dir)


if __name__ == "__main__":
    main()
