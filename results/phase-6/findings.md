# Phase 6 findings — bounded multi-agent orchestration

**Run date:** 5 October 2026  
**Status:** Implementation slice complete; live model/database evaluation pending  
**Model:** Not exercised in this verification run

## What was implemented

Phase 5 is now marked complete in the roadmap and README. Phase 6 is marked in
progress and adds an optional `agent: "multi_agent"` path to `/chat`.

The implementation contains:

- a strict coordinator route contract with Household and Scheduler specialists;
- a maximum of two specialists per request;
- sequential specialist execution;
- application-enforced specialist tool subsets;
- a shared maximum of eight specialist tool calls;
- the existing five-iteration specialist limit;
- reuse of the Phase 5 hand-written loop;
- aggregation of specialist responses and pending proposals; and
- no change to the explicit confirmation endpoint or write boundary.

The detailed design and step-by-step implementation record are in
[Version 6 — Multi-Agent Orchestration](../../docs/plans/home-ai-agent-project-plan%20v6.md).

## Files added or changed

| Area | Location |
|---|---|
| Coordinator and specialists | `src/app/multi_agent.py` |
| Tool subset support | `src/app/tools.py`, `src/app/llm.py` |
| API selector | `src/app/main.py` |
| Unit safeguards | `src/tests/test_phase6.py` |
| Evaluation runner | `src/app/evaluate_phase6.py` |
| Frozen cases | `results/phase-6/cases/` |

## Verification

Focused command:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest src/tests/test_phase5.py src/tests/test_phase6.py -v
```

Result: **5/5 passed**.

The focused tests verified:

1. a mixed request is dispatched to Household and Scheduler;
2. each specialist receives only its allowed tool set;
3. pending proposals are aggregated without execution;
4. clarification stops dispatch; and
5. existing Phase 5 duplicate-call and iteration-limit safeguards remain green.

All changed Python modules passed `py_compile`.

## Full-suite result

The full discovery run executed 50 tests. The Phase 2, Phase 4, Phase 5, and
Phase 6 non-database tests passed. Nineteen database-dependent tests were
skipped because local PostgreSQL was unavailable.

Two unrelated Phase 3 temporary-file tests errored because the Windows sandbox
denied writes and cleanup under its temporary directory. Those failures were
not caused by the Phase 6 changes and should be rerun in a normal writable
test environment before making a full regression claim.

## Live evaluation status

The Phase 6 evaluator and frozen cases are present, but no live Ollama/PostgreSQL
Phase 6 score is claimed in this document. The evaluator requires an isolated
database named with the `home_ai_phase6_test_` prefix:

```powershell
$env:PYTHONPATH = "src"
$env:POSTGRES_DB = "home_ai_phase6_test_local"
.\.venv\Scripts\python.exe -m app.evaluate_phase6 --split development
.\.venv\Scripts\python.exe -m app.evaluate_phase6 --split held-out
```

Those runs are the next gate. They should compare routing accuracy, specialist
tool evidence, pending-action safety, latency, model-call overhead, partial
failure behavior, and household snapshots before and after each case.

## Current limitations

- The initial Scheduler specialist supports calendar proposals but not narrow
  calendar reads.
- Household document-retrieval delegation is not yet included in the restricted
  tool set.
- The coordinator and specialists have not yet been compared against the live
  single-agent baseline.
- The current held-out set is only three synthetic cases.
- The global budget is enforced, but richer failure-specific tests remain to be
  added after the first live run.

Phase 6 should not be marked complete until the live development and held-out
runs succeed and their evidence is reviewed.

